import numpy as np
import pandas as pd

from backend.app.gap_scanner import score_ticker_gap


def _base_df(n=140, base_volume=1_000_000):
    """A mild, gap-free uptrend to build gap scenarios on top of."""
    rng = np.random.default_rng(5)
    closes = 40 + np.linspace(0, 10, n) + rng.normal(0, 0.3, n)
    idx = pd.date_range("2023-06-01", periods=n, freq="B")
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) + 0.3
    lows = np.minimum(opens, closes) - 0.3
    volume = np.full(n, float(base_volume))
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volume}, index=idx
    )


def _append_day(df, open_, high, low, close, volume):
    new_row = pd.DataFrame(
        {"Open": [open_], "High": [high], "Low": [low], "Close": [close], "Volume": [volume]},
        index=[df.index[-1] + pd.offsets.BDay(1)],
    )
    return pd.concat([df, new_row])


def _gap_up_to_band_scenario():
    """Gaps up 5% on 3x average volume, closes strong near the day's high --
    the clean "gap and go" the scanner is meant to catch."""
    df = _base_df()
    prior_close = df["Close"].iloc[-1]
    gap_open = prior_close * 1.05
    gap_close = gap_open * 1.02
    return _append_day(
        df,
        open_=gap_open,
        high=gap_close * 1.005,
        low=gap_open * 0.995,
        close=gap_close,
        volume=df["Volume"].tail(20).mean() * 3,
    )


def _no_gap_scenario():
    return _base_df()


def _gap_fully_faded_scenario():
    """Gaps up, then the next session fades hard back through the pre-gap
    close and closes well below the upper band -- no longer a live setup."""
    df = _gap_up_to_band_scenario()
    pre_gap_close = df["Close"].iloc[-2]
    return _append_day(
        df,
        open_=df["Close"].iloc[-1] * 0.99,
        high=df["Close"].iloc[-1] * 0.995,
        low=pre_gap_close * 0.95,
        close=pre_gap_close * 0.97,
        volume=df["Volume"].iloc[-1] * 0.8,
    )


def _gap_shallow_undercut_scenario():
    """Gaps up, then the next session dips just below the pre-gap close
    intraday but closes back up near the band -- gap "filled" on a technicality
    but the setup is still live, just weaker."""
    df = _gap_up_to_band_scenario()
    pre_gap_close = df["Close"].iloc[-2]
    gap_close = df["Close"].iloc[-1]
    return _append_day(
        df,
        open_=gap_close * 0.995,
        high=gap_close * 1.015,
        low=pre_gap_close * 0.995,
        close=gap_close * 1.01,
        volume=df["Volume"].iloc[-1] * 0.7,
    )


def test_gap_to_band_scores_high():
    result = score_ticker_gap("GAP", _gap_up_to_band_scenario())
    assert result is not None
    assert result.score >= 70
    assert result.verdict == "Strong gap-and-go breakout"
    assert not result.gap_filled


def test_no_gap_is_excluded():
    assert score_ticker_gap("FLAT", _no_gap_scenario()) is None


def test_fully_faded_gap_is_excluded():
    """Once price has fallen back well off the upper band, it's no longer a
    "hitting the upper band" candidate even though a gap happened recently."""
    assert score_ticker_gap("FADED", _gap_fully_faded_scenario()) is None


def test_shallow_undercut_still_qualifies_but_scores_lower():
    clean = score_ticker_gap("CLEAN", _gap_up_to_band_scenario())
    undercut = score_ticker_gap("UNDERCUT", _gap_shallow_undercut_scenario())
    assert clean is not None
    assert undercut is not None
    assert undercut.gap_filled
    assert undercut.score < clean.score


def test_score_components_sum_to_score():
    result = score_ticker_gap("GAP", _gap_up_to_band_scenario())
    assert result is not None
    assert abs(sum(result.components.values()) - result.score) < 0.5


def test_insufficient_data_returns_none():
    short_df = _base_df(n=50)
    assert score_ticker_gap("SHORT", short_df) is None


def test_penny_stock_filtered_out():
    rng = np.random.default_rng(9)
    n = 140
    closes = 2 + np.linspace(0, 0.5, n) + rng.normal(0, 0.02, n)
    idx = pd.date_range("2023-06-01", periods=n, freq="B")
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    df = pd.DataFrame(
        {
            "Open": opens,
            "High": np.maximum(opens, closes) + 0.05,
            "Low": np.minimum(opens, closes) - 0.05,
            "Close": closes,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )
    prior_close = df["Close"].iloc[-1]
    penny = _append_day(
        df,
        open_=prior_close * 1.05,
        high=prior_close * 1.08,
        low=prior_close * 1.04,
        close=prior_close * 1.07,
        volume=3_000_000.0,
    )
    assert score_ticker_gap("PENNY", penny) is None

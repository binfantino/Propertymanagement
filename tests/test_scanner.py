import numpy as np
import pandas as pd

from backend.app.scanner import score_ticker


def _ohlcv_from_close(closes, base_volume=1_000_000, extra_up_volume=0):
    idx = pd.date_range("2023-01-02", periods=len(closes), freq="B")
    closes = np.asarray(closes, dtype=float)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) + 0.3
    lows = np.minimum(opens, closes) - 0.3
    up_day = closes > opens
    volume = np.full(len(closes), float(base_volume))
    volume[up_day] += extra_up_volume
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volume},
        index=idx,
    )


def _bottoming_scenario():
    """~4 months of decline, a month-long base, then an early, modest turn up
    with a bullish engulfing candle and rising volume right at the low --
    exactly the setup the scanner is meant to catch."""
    rng = np.random.default_rng(42)
    decline = np.linspace(100, 55, 90) + rng.normal(0, 0.3, 90)
    t = np.linspace(0, 6 * np.pi, 30)
    base = 54 + 1.5 * np.exp(-t / 10) * np.sin(t)
    recovery = np.linspace(base[-1], 58, 10) + rng.normal(0, 0.15, 10)
    closes = np.concatenate([decline, base, recovery])
    df = _ohlcv_from_close(closes)

    # Craft a bullish engulfing right at the recovery kickoff (near the base low).
    idx = df.index
    pos = 90 + 29  # last bar of the base / first bar of recovery
    df.loc[idx[pos - 1], ["Open", "High", "Low", "Close"]] = [55.0, 55.1, 53.8, 54.2]
    df.loc[idx[pos], ["Open", "High", "Low", "Close"]] = [54.1, 56.2, 54.0, 56.0]

    # Boost volume on the most recent up days to signal accumulation.
    recent_up = df["Close"].tail(8) > df["Open"].tail(8)
    df.loc[df.tail(8).index[recent_up.values], "Volume"] *= 3
    return df


def _extended_uptrend_scenario():
    """Already trending up in a straight line -- not a bottom, just extended."""
    closes = np.linspace(60, 150, 130)
    return _ohlcv_from_close(closes)


def _freefall_scenario():
    """Still making new lows with no basing, contraction, or reversal signal."""
    rng = np.random.default_rng(7)
    closes = np.linspace(150, 40, 130) + rng.normal(0, 0.3, 130)
    return _ohlcv_from_close(closes)


def test_bottoming_scenario_scores_higher_than_extended_uptrend():
    bottoming = score_ticker("BOT", _bottoming_scenario())
    extended = score_ticker("EXT", _extended_uptrend_scenario())
    assert bottoming is not None
    assert extended is not None
    assert bottoming.score > extended.score


def test_bottoming_scenario_scores_higher_than_freefall():
    bottoming = score_ticker("BOT", _bottoming_scenario())
    freefall = score_ticker("FALL", _freefall_scenario())
    assert bottoming is not None
    assert freefall is not None
    assert bottoming.score > freefall.score


def test_score_components_sum_to_score():
    result = score_ticker("BOT", _bottoming_scenario())
    assert result is not None
    assert abs(sum(result.components.values()) - result.score) < 0.5


def test_insufficient_data_returns_none():
    short_df = _ohlcv_from_close(np.linspace(100, 90, 30))
    assert score_ticker("SHORT", short_df) is None


def test_penny_stock_filtered_out():
    penny = _ohlcv_from_close(np.linspace(4.0, 3.5, 120))
    assert score_ticker("PENNY", penny) is None

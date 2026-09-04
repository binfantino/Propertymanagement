import numpy as np
import pandas as pd

from backend.app.gap_fill_scanner import score_ticker_gap_fill


def _flat_base(n=120, level=50.0, base_volume=1_000_000):
    rng = np.random.default_rng(11)
    closes = level + rng.normal(0, 0.3, n)
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
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


def _gap_down_then_fill_scenario():
    """Gaps down 8%, drifts sideways at the lower level for two weeks
    (leaving the gap open), then gaps back up enough to reclaim the
    pre-gap-down close on strong volume -- the reversal this scanner
    is meant to catch."""
    df = _flat_base()
    pre_gap_close = df["Close"].iloc[-1]
    down_open = pre_gap_close * 0.92
    down_close = down_open * 0.99
    df = _append_day(df, down_open, down_open * 1.01, down_close * 0.98, down_close, 1_500_000)

    rng = np.random.default_rng(3)
    for _ in range(10):
        last_close = df["Close"].iloc[-1]
        c = last_close * (1 + rng.normal(0, 0.003))
        df = _append_day(df, last_close, max(c, last_close) * 1.005, min(c, last_close) * 0.995, c, 900_000)

    up_open = pre_gap_close * 1.02
    up_close = up_open * 1.01
    return _append_day(df, up_open, up_close * 1.005, up_open * 0.995, up_close, df["Volume"].tail(20).mean() * 3)


def _no_down_gap_scenario():
    """A gap up with no preceding down-gap to fill -- not this setup."""
    df = _flat_base()
    last_close = df["Close"].iloc[-1]
    up_open = last_close * 1.06
    up_close = up_open * 1.01
    return _append_day(df, up_open, up_close * 1.005, up_open * 0.995, up_close, df["Volume"].tail(20).mean() * 3)


def _already_filled_before_up_gap_scenario():
    """Gaps down, then rallies back above the old ceiling through ordinary
    drift -- so a later, unrelated gap up isn't the event that closed it."""
    df = _flat_base()
    pre_gap_close = df["Close"].iloc[-1]
    down_open = pre_gap_close * 0.92
    down_close = down_open * 0.99
    df = _append_day(df, down_open, down_open * 1.01, down_close * 0.98, down_close, 1_500_000)

    for _ in range(8):
        last_close = df["Close"].iloc[-1]
        c = last_close * 1.02
        df = _append_day(df, last_close, c * 1.01, last_close * 0.995, c, 900_000)

    last_close = df["Close"].iloc[-1]
    up_open = last_close * 1.05
    up_close = up_open * 1.01
    return _append_day(df, up_open, up_close * 1.005, up_open * 0.995, up_close, df["Volume"].tail(20).mean() * 3)


def _gap_not_yet_closed_scenario():
    """Gaps down 15%, then only gaps back up 3% -- nowhere near closing it."""
    df = _flat_base()
    pre_gap_close = df["Close"].iloc[-1]
    down_open = pre_gap_close * 0.85
    down_close = down_open * 0.99
    df = _append_day(df, down_open, down_open * 1.01, down_close * 0.98, down_close, 1_500_000)

    for _ in range(5):
        last_close = df["Close"].iloc[-1]
        c = last_close * 1.001
        df = _append_day(df, last_close, c * 1.005, last_close * 0.995, c, 900_000)

    last_close = df["Close"].iloc[-1]
    up_open = last_close * 1.03
    up_close = up_open * 1.005
    return _append_day(df, up_open, up_close * 1.005, up_open * 0.995, up_close, df["Volume"].tail(20).mean() * 2)


def test_gap_down_then_fill_scores_high():
    result = score_ticker_gap_fill("FILL", _gap_down_then_fill_scenario())
    assert result is not None
    assert result.score >= 70
    assert result.verdict == "Strong gap-fill reversal"
    assert result.fill_ratio >= 97.0
    assert result.down_gap_pct < 0
    assert result.up_gap_pct > 0


def test_no_down_gap_is_excluded():
    assert score_ticker_gap_fill("NODOWN", _no_down_gap_scenario()) is None


def test_gap_already_filled_before_up_gap_is_excluded():
    """The down-gap has to stay open until the up-gap closes it -- if
    ordinary drift already closed it first, this isn't a fresh event."""
    assert score_ticker_gap_fill("EARLYFILL", _already_filled_before_up_gap_scenario()) is None


def test_gap_not_yet_closed_is_excluded():
    assert score_ticker_gap_fill("NOTYET", _gap_not_yet_closed_scenario()) is None


def test_score_components_sum_to_score():
    result = score_ticker_gap_fill("FILL", _gap_down_then_fill_scenario())
    assert result is not None
    assert abs(sum(result.components.values()) - result.score) < 0.5


def test_insufficient_data_returns_none():
    assert score_ticker_gap_fill("SHORT", _flat_base(n=50)) is None


def test_penny_stock_filtered_out():
    df = _flat_base(n=120, level=3.0)
    pre_gap_close = df["Close"].iloc[-1]
    down_open = pre_gap_close * 0.9
    df = _append_day(df, down_open, down_open * 1.02, down_open * 0.97, down_open * 0.99, 1_200_000)
    for _ in range(5):
        last_close = df["Close"].iloc[-1]
        df = _append_day(df, last_close, last_close * 1.005, last_close * 0.995, last_close, 800_000)
    last_close = df["Close"].iloc[-1]
    up_open = pre_gap_close * 1.02
    penny = _append_day(df, up_open, up_open * 1.03, up_open * 0.99, up_open * 1.02, 3_000_000)
    assert score_ticker_gap_fill("PENNY", penny) is None

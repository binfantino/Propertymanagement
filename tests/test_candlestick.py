import pandas as pd

from backend.app.candlestick import (
    detect_bullish_engulfing,
    detect_dragonfly_doji,
    detect_hammer,
    detect_inverted_hammer,
    detect_morning_star,
    detect_piercing_line,
    detect_three_white_soldiers,
)


def make_df(bars):
    """bars: list of (open, high, low, close) tuples, oldest first."""
    idx = pd.date_range("2024-01-01", periods=len(bars), freq="B")
    return pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"], index=idx)


def test_detect_hammer():
    df = make_df([(10, 10.2, 8.5, 10.0)])
    assert detect_hammer(df).iloc[-1]


def test_detect_hammer_rejects_normal_candle():
    df = make_df([(10, 11, 9, 10.5)])
    assert not detect_hammer(df).iloc[-1]


def test_detect_inverted_hammer():
    df = make_df([(10, 11.6, 9.9, 10.1)])
    assert detect_inverted_hammer(df).iloc[-1]


def test_detect_dragonfly_doji():
    df = make_df([(10.0, 10.05, 8.5, 10.0)])
    assert detect_dragonfly_doji(df).iloc[-1]


def test_detect_bullish_engulfing():
    df = make_df(
        [
            (10.0, 10.1, 9.0, 9.2),   # bearish
            (9.0, 10.5, 8.9, 10.4),   # bullish, engulfs prior body
        ]
    )
    result = detect_bullish_engulfing(df)
    assert result.iloc[-1]
    assert not result.iloc[0]


def test_detect_piercing_line():
    df = make_df(
        [
            (10.0, 10.1, 9.0, 9.2),   # long bearish
            (8.8, 9.8, 8.7, 9.7),     # opens below prior close, closes above midpoint (9.6)
        ]
    )
    assert detect_piercing_line(df).iloc[-1]


def test_detect_morning_star():
    df = make_df(
        [
            (10.0, 10.1, 8.5, 8.6),   # long bearish
            (8.3, 8.4, 8.1, 8.35),    # small body, gapped down
            (8.5, 9.8, 8.4, 9.7),     # long bullish closing back into first body
        ]
    )
    assert detect_morning_star(df).iloc[-1]


def test_detect_three_white_soldiers():
    df = make_df(
        [
            (8.0, 8.6, 7.9, 8.5),
            (8.2, 9.1, 8.1, 9.0),
            (8.6, 9.6, 8.5, 9.5),
        ]
    )
    assert detect_three_white_soldiers(df).iloc[-1]


def test_no_false_positive_on_steady_uptrend():
    bars = [(10 + i * 0.05, 10.3 + i * 0.05, 9.9 + i * 0.05, 10.2 + i * 0.05) for i in range(10)]
    df = make_df(bars)
    assert not detect_hammer(df).any()
    assert not detect_morning_star(df).any()

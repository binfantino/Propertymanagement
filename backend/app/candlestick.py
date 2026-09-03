"""
Bullish reversal candlestick pattern detection.

Implemented from scratch on plain OHLC arithmetic (no TA-Lib). Each
`detect_*` function is vectorized over a DataFrame with Open/High/Low/Close
columns and returns a boolean Series aligned to the input index, True on the
bar where the pattern completes.

Patterns are only meaningful as *reversal* signals when they occur after a
decline, but that context is applied by the caller (scanner.py) rather than
baked in here, so these stay simple, reusable pattern-shape detectors.
"""

from __future__ import annotations

import pandas as pd


def _body(df: pd.DataFrame) -> pd.Series:
    return (df["Close"] - df["Open"]).abs()


def _range(df: pd.DataFrame) -> pd.Series:
    return (df["High"] - df["Low"]).replace(0, 1e-9)


def _upper_shadow(df: pd.DataFrame) -> pd.Series:
    return df["High"] - df[["Open", "Close"]].max(axis=1)


def _lower_shadow(df: pd.DataFrame) -> pd.Series:
    return df[["Open", "Close"]].min(axis=1) - df["Low"]


def _is_bullish(df: pd.DataFrame) -> pd.Series:
    return df["Close"] > df["Open"]


def _is_bearish(df: pd.DataFrame) -> pd.Series:
    return df["Close"] < df["Open"]


def detect_hammer(df: pd.DataFrame) -> pd.Series:
    """Small body near the top of the range, long lower shadow, tiny/no upper shadow."""
    body = _body(df)
    rng = _range(df)
    lower = _lower_shadow(df)
    upper = _upper_shadow(df)
    return (body <= 0.35 * rng) & (lower >= 2 * body) & (upper <= 0.15 * rng)


def detect_inverted_hammer(df: pd.DataFrame) -> pd.Series:
    """Small body near the bottom of the range, long upper shadow, tiny/no lower shadow."""
    body = _body(df)
    rng = _range(df)
    lower = _lower_shadow(df)
    upper = _upper_shadow(df)
    return (body <= 0.35 * rng) & (upper >= 2 * body) & (lower <= 0.15 * rng)


def detect_dragonfly_doji(df: pd.DataFrame, doji_tol: float = 0.1) -> pd.Series:
    """Open ~= Close ~= High, long lower shadow -- an extreme hammer variant."""
    body = _body(df)
    rng = _range(df)
    lower = _lower_shadow(df)
    upper = _upper_shadow(df)
    return (body <= doji_tol * rng) & (lower >= 0.6 * rng) & (upper <= 0.1 * rng)


def detect_bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    """Prior candle bearish; current candle bullish and its body engulfs the prior body."""
    prev_open = df["Open"].shift(1)
    prev_close = df["Close"].shift(1)
    prev_bearish = prev_close < prev_open
    curr_bullish = _is_bullish(df)
    engulfs = (df["Open"] <= prev_close) & (df["Close"] >= prev_open)
    return prev_bearish & curr_bullish & engulfs


def detect_piercing_line(df: pd.DataFrame) -> pd.Series:
    """Prior long bearish candle; current opens below prior low, closes above the midpoint of prior body."""
    prev_open = df["Open"].shift(1)
    prev_close = df["Close"].shift(1)
    prev_bearish = prev_close < prev_open
    prev_midpoint = (prev_open + prev_close) / 2
    curr_bullish = _is_bullish(df)
    opens_lower = df["Open"] < prev_close
    closes_above_mid = df["Close"] > prev_midpoint
    closes_below_prev_open = df["Close"] < prev_open
    return prev_bearish & curr_bullish & opens_lower & closes_above_mid & closes_below_prev_open


def detect_morning_star(df: pd.DataFrame) -> pd.Series:
    """3-bar pattern: long bearish, small-bodied middle candle (gap down), long bullish closing into first candle's body."""
    open1, close1 = df["Open"].shift(2), df["Close"].shift(2)
    open2, close2 = df["Open"].shift(1), df["Close"].shift(1)
    open3, close3 = df["Open"], df["Close"]

    body1 = (close1 - open1).abs()
    body2 = (close2 - open2).abs()
    body3 = (close3 - open3).abs()

    first_bearish = close1 < open1
    third_bullish = close3 > open3
    middle_small = body2 < 0.5 * body1
    gap_down = df[["Open", "Close"]].shift(1).max(axis=1) < open1
    closes_into_first_body = close3 > (open1 + close1) / 2
    third_strong = body3 > 0.5 * body1

    return first_bearish & middle_small & gap_down.fillna(False) & third_bullish & closes_into_first_body & third_strong


def detect_three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    """3 consecutive bullish candles, each opening within the prior body and closing higher than the prior close."""
    o0, c0 = df["Open"].shift(2), df["Close"].shift(2)
    o1, c1 = df["Open"].shift(1), df["Close"].shift(1)
    o2, c2 = df["Open"], df["Close"]

    all_bullish = (c0 > o0) & (c1 > o1) & (c2 > o2)
    progressive_closes = (c1 > c0) & (c2 > c1)
    opens_within_prior_body = (o1 >= o0) & (o1 <= c0) & (o2 >= o1) & (o2 <= c1)
    return all_bullish & progressive_closes & opens_within_prior_body


PATTERN_DETECTORS = {
    "hammer": detect_hammer,
    "inverted_hammer": detect_inverted_hammer,
    "dragonfly_doji": detect_dragonfly_doji,
    "bullish_engulfing": detect_bullish_engulfing,
    "piercing_line": detect_piercing_line,
    "morning_star": detect_morning_star,
    "three_white_soldiers": detect_three_white_soldiers,
}

# Relative confidence weight of each pattern as a bottom-reversal signal,
# used by the scanner to score detections instead of treating all hits equally.
PATTERN_WEIGHTS = {
    "hammer": 0.6,
    "inverted_hammer": 0.5,
    "dragonfly_doji": 0.7,
    "bullish_engulfing": 0.8,
    "piercing_line": 0.75,
    "morning_star": 1.0,
    "three_white_soldiers": 0.9,
}


def detect_all_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame of boolean columns, one per pattern, aligned to df's index."""
    return pd.DataFrame({name: fn(df) for name, fn in PATTERN_DETECTORS.items()}, index=df.index)

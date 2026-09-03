"""
Technical indicators computed with pandas/numpy only (no TA-Lib dependency).

Every function takes and returns pandas Series/DataFrames aligned to the
input OHLCV DataFrame's index, so callers can attach results as new columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.mask(avg_loss == 0, 100.0)
    result = result.mask((avg_gain == 0) & (avg_loss == 0), 50.0)
    return result.fillna(50)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": histogram})


def bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid.replace(0, np.nan)
    return pd.DataFrame({"bb_mid": mid, "bb_upper": upper, "bb_lower": lower, "bb_width": width})


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_window: int = 14, d_window: int = 3) -> pd.DataFrame:
    lowest_low = low.rolling(window=k_window, min_periods=k_window).min()
    highest_high = high.rolling(window=k_window, min_periods=k_window).max()
    percent_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    percent_d = percent_k.rolling(window=d_window, min_periods=d_window).mean()
    return pd.DataFrame({"stoch_k": percent_k, "stoch_d": percent_d})


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).fillna(0).cumsum()


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given an OHLCV DataFrame with columns Open/High/Low/Close/Volume,
    return a copy with all indicator columns attached.
    """
    out = df.copy()
    out["sma20"] = sma(out["Close"], 20)
    out["sma50"] = sma(out["Close"], 50)
    out["sma200"] = sma(out["Close"], 200)
    out["rsi14"] = rsi(out["Close"], 14)

    macd_df = macd(out["Close"])
    out = out.join(macd_df)

    bb_df = bollinger_bands(out["Close"])
    out = out.join(bb_df)

    out["atr14"] = atr(out["High"], out["Low"], out["Close"], 14)

    stoch_df = stochastic(out["High"], out["Low"], out["Close"])
    out = out.join(stoch_df)

    out["obv"] = obv(out["Close"], out["Volume"])
    return out

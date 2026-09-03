"""
Core "bottoming out" scanner: turns a single ticker's OHLCV history into a
0-100 score estimating how likely the stock is basing after a decline and
setting up for a move higher, plus turns a whole universe into a ranked list.

The score is a weighted blend of independent technical signals. None of them
alone is reliable (that's normal for TA), so weight is spread across trend
context, momentum recovery, volatility contraction, volume behavior,
candlestick reversal patterns, and price structure. Weights are a judgment
call, not a fitted model -- treat the score as a screening heuristic, not a
prediction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .candlestick import PATTERN_WEIGHTS, detect_all_patterns
from .indicators import add_all_indicators

# Component weights, must sum to 100.
WEIGHTS = {
    "downtrend_context": 8,
    "proximity_to_low": 12,
    "rsi_recovery": 20,
    "macd_turn": 15,
    "volatility_contraction": 8,
    "volume_accumulation": 15,
    "candlestick_pattern": 15,
    "higher_low_structure": 7,
}
assert sum(WEIGHTS.values()) == 100

MIN_BARS = 80
MIN_PRICE = 5.0
RECENT_LOW_WINDOW = 60
PATTERN_LOOKBACK = 5


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if np.isnan(x):
        return 0.0
    return max(lo, min(hi, x))


@dataclass
class ScoreResult:
    ticker: str
    score: float
    components: dict = field(default_factory=dict)
    patterns: list = field(default_factory=list)
    last_close: float = 0.0
    pct_off_low: float = 0.0
    rsi14: float = 0.0
    as_of: str = ""
    verdict: str = ""


def _downtrend_context(df: pd.DataFrame) -> float:
    lookback = min(63, len(df) - 1)
    price_then = df["Close"].iloc[-lookback - 1]
    price_now = df["Close"].iloc[-1]
    if price_then <= 0:
        return 0.0
    decline_pct = (price_then - price_now) / price_then
    score = _clamp(decline_pct / 0.20)
    sma50 = df["sma50"].iloc[-1]
    if not np.isnan(sma50) and price_now > sma50 * 1.05:
        score *= 0.3
    return score


def _proximity_to_low(df: pd.DataFrame) -> tuple[float, float]:
    window = df["Low"].tail(RECENT_LOW_WINDOW)
    recent_low = window.min()
    price_now = df["Close"].iloc[-1]
    if recent_low <= 0:
        return 0.0, 0.0
    pct_off_low = (price_now - recent_low) / recent_low
    score = _clamp(1 - pct_off_low / 0.15)
    return score, pct_off_low


def _rsi_recovery(df: pd.DataFrame) -> float:
    recent_rsi = df["rsi14"].tail(10)
    min_rsi = recent_rsi.min()
    current_rsi = df["rsi14"].iloc[-1]
    oversold = _clamp((35 - min_rsi) / 20)
    recovery = _clamp((current_rsi - min_rsi) / 15)
    return 0.5 * oversold + 0.5 * recovery


def _macd_turn(df: pd.DataFrame) -> float:
    hist = df["hist"].tail(5)
    if len(hist) < 3 or hist.isna().any():
        return 0.0
    if hist.iloc[-1] > hist.iloc[-2] > hist.iloc[-3]:
        rising = 1.0
    elif hist.iloc[-1] > hist.iloc[-3]:
        rising = 0.5
    else:
        rising = 0.0

    macd_minus_signal = (df["macd"] - df["signal"]).tail(6)
    crossed_up = bool(
        ((macd_minus_signal.shift(1) < 0) & (macd_minus_signal > 0)).fillna(False).any()
    )

    return 0.5 * rising + 0.5 * (1.0 if crossed_up else 0.0)


def _volatility_contraction(df: pd.DataFrame) -> float:
    bb_width = df["bb_width"].tail(120).dropna()
    if len(bb_width) < 20:
        return 0.0
    current = bb_width.iloc[-1]
    pct_rank = (bb_width <= current).mean()
    return _clamp(1 - pct_rank)


def _volume_accumulation(df: pd.DataFrame) -> float:
    recent = df.tail(10)
    up_vol = recent.loc[recent["Close"] > recent["Open"], "Volume"].sum()
    down_vol = recent.loc[recent["Close"] < recent["Open"], "Volume"].sum()
    total = up_vol + down_vol
    if total <= 0:
        return 0.0
    ratio = up_vol / total
    return _clamp((ratio - 0.4) / 0.35)


def _candlestick_pattern(df: pd.DataFrame, recent_low: float) -> tuple[float, list[dict]]:
    patterns_df = detect_all_patterns(df)
    recent = patterns_df.tail(PATTERN_LOOKBACK)
    detected = []
    best_weight = 0.0
    for date, row in recent.iterrows():
        for name, is_hit in row.items():
            if bool(is_hit):
                weight = PATTERN_WEIGHTS[name]
                bar_low = df.loc[date, "Low"]
                near_low = recent_low > 0 and (bar_low - recent_low) / recent_low <= 0.05
                effective = weight * (1.0 if near_low else 0.7)
                detected.append(
                    {
                        "name": name,
                        "date": str(date.date()) if hasattr(date, "date") else str(date),
                        "near_low": near_low,
                    }
                )
                best_weight = max(best_weight, effective)
    return _clamp(best_weight), detected


def _higher_low_structure(df: pd.DataFrame) -> float:
    if len(df) < 40:
        return 0.0
    first_half = df["Low"].iloc[-40:-20]
    second_half = df["Low"].iloc[-20:]
    if first_half.empty or second_half.empty:
        return 0.0
    low1, low2 = first_half.min(), second_half.min()
    if low1 <= 0:
        return 0.0
    ratio = (low2 - low1) / low1
    return _clamp(ratio / 0.05)


def score_ticker(ticker: str, raw_df: pd.DataFrame) -> ScoreResult | None:
    """
    Compute a bottoming score for one ticker given its raw OHLCV history
    (columns: Open, High, Low, Close, Volume; DatetimeIndex ascending).
    Returns None if there isn't enough clean data to score.
    """
    if raw_df is None or len(raw_df) < MIN_BARS:
        return None

    df = add_all_indicators(raw_df)
    last = df.iloc[-1]
    if last[["Close", "rsi14", "macd", "signal", "bb_width", "atr14"]].isna().any():
        return None
    if last["Close"] < MIN_PRICE:
        return None

    proximity_score, pct_off_low = _proximity_to_low(df)
    recent_low = df["Low"].tail(RECENT_LOW_WINDOW).min()
    pattern_score, patterns = _candlestick_pattern(df, recent_low)

    components = {
        "downtrend_context": _downtrend_context(df),
        "proximity_to_low": proximity_score,
        "rsi_recovery": _rsi_recovery(df),
        "macd_turn": _macd_turn(df),
        "volatility_contraction": _volatility_contraction(df),
        "volume_accumulation": _volume_accumulation(df),
        "candlestick_pattern": pattern_score,
        "higher_low_structure": _higher_low_structure(df),
    }

    weighted = {k: round(v * WEIGHTS[k], 2) for k, v in components.items()}
    total = round(sum(weighted.values()), 1)
    total = max(0.0, min(100.0, total))

    if total >= 70:
        verdict = "Strong bottoming setup"
    elif total >= 55:
        verdict = "Emerging setup"
    elif total >= 40:
        verdict = "Early / watchlist"
    else:
        verdict = "No clear setup"

    return ScoreResult(
        ticker=ticker,
        score=total,
        components=weighted,
        patterns=patterns,
        last_close=round(float(last["Close"]), 2),
        pct_off_low=round(pct_off_low * 100, 1),
        rsi14=round(float(last["rsi14"]), 1),
        as_of=str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        verdict=verdict,
    )

"""
"Uptrend pullback" scanner: turns a ticker's OHLCV history into a 0-100
score estimating how well it fits the classic "buy the dip" setup --
an established uptrend that has pulled back to the bottom of its recent
trading range, often right into a rising moving average, without breaking
trend.

This is a different setup from scanner.py's "bottoming out" scan (which
looks for reversals *after* a decline). Here the stock must already be in
a confirmed uptrend; the signal is a healthy, low-volume dip toward support
rather than a reversal from a downtrend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .candlestick import PATTERN_WEIGHTS, detect_all_patterns
from .indicators import add_all_indicators

# Component weights, must sum to 100.
WEIGHTS = {
    "uptrend_strength": 25,
    "support_proximity": 25,
    "pullback_depth": 15,
    "rsi_pullback_zone": 15,
    "volume_contraction": 10,
    "candlestick_pattern": 10,
}
assert sum(WEIGHTS.values()) == 100

MIN_BARS = 220  # SMA200 needs 200 bars to exist at all, plus room to check its slope
MIN_PRICE = 5.0
RANGE_WINDOW = 40  # ~2 months, defines the "trading range" for this scan
RECENT_HIGH_WINDOW = 60
PATTERN_LOOKBACK = 5
MA_TOUCH_TOLERANCE = 0.04  # within 4% of a rising MA counts as "testing" it


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if np.isnan(x):
        return 0.0
    return max(lo, min(hi, x))


def _triangular(x: float, low: float, peak: float, high: float) -> float:
    """0 at/outside [low, high], rising to 1 at peak. Used for "sweet spot" ranges."""
    if np.isnan(x) or x <= low or x >= high:
        return 0.0
    if x <= peak:
        return (x - low) / (peak - low)
    return (high - x) / (high - peak)


def _series_then_now(series: pd.Series, lookback: int) -> tuple[float, float] | None:
    """
    Value `lookback` valid (non-NaN) points ago vs. the latest valid value.
    Uses however many valid points are actually available rather than a
    fixed positional offset, so a series with a long NaN warm-up (e.g. a
    slow-moving-average column) still gives a usable slope from a shorter
    history instead of silently returning NaN.
    """
    valid = series.dropna()
    if len(valid) < 2:
        return None
    idx = min(lookback, len(valid) - 1)
    return float(valid.iloc[-idx - 1]), float(valid.iloc[-1])


@dataclass
class PullbackScoreResult:
    ticker: str
    score: float
    components: dict = field(default_factory=dict)
    patterns: list = field(default_factory=list)
    last_close: float = 0.0
    position_in_range: float = 0.0  # 0 = at the bottom of the range, 100 = at the top
    pct_below_high: float = 0.0
    near_ma: str | None = None
    rsi14: float = 0.0
    as_of: str = ""
    verdict: str = ""


def _is_established_uptrend(df: pd.DataFrame) -> bool:
    """Hard gate: this scan only makes sense for stocks already trending up."""
    last = df.iloc[-1]
    if np.isnan(last["sma200"]) or np.isnan(last["sma50"]):
        return False
    then_now = _series_then_now(df["sma200"], lookback=40)
    if then_now is None:
        return False
    sma200_then, sma200_now = then_now
    if sma200_then <= 0:
        return False
    return bool(last["Close"] > last["sma200"] and sma200_now > sma200_then)


def _uptrend_strength(df: pd.DataFrame) -> float:
    last = df.iloc[-1]

    alignment = _clamp((last["sma50"] - last["sma200"]) / last["sma200"] / 0.08)

    then_now = _series_then_now(df["sma200"], lookback=40)
    if then_now is None or then_now[0] <= 0:
        slope_score = 0.0
    else:
        sma200_then, sma200_now = then_now
        slope_score = _clamp((sma200_now - sma200_then) / sma200_then / 0.05)

    window = min(120, len(df))
    lows = df["Low"].tail(window)
    thirds = np.array_split(lows, 3)
    mins = [t.min() for t in thirds if len(t)]
    structure_score = 1.0 if len(mins) == 3 and mins[0] < mins[1] < mins[2] else (
        0.5 if len(mins) == 3 and mins[2] > mins[0] else 0.0
    )

    return 0.4 * alignment + 0.4 * slope_score + 0.2 * structure_score


def _support_proximity(df: pd.DataFrame) -> tuple[float, float, str | None]:
    last = df.iloc[-1]
    close = last["Close"]

    range_low = df["Low"].tail(RANGE_WINDOW).min()
    range_high = df["High"].tail(RANGE_WINDOW).max()
    if range_high <= range_low:
        position_in_range = 0.5
    else:
        position_in_range = (close - range_low) / (range_high - range_low)
    range_score = _clamp(1 - position_in_range / 0.35)

    best_ma_score = 0.0
    best_ma_name = None
    for name, lookback in (("sma20", 15), ("sma50", 25), ("sma200", 40)):
        then_now = _series_then_now(df[name], lookback)
        if then_now is None:
            continue
        ma_then, ma_now = then_now
        if ma_now <= 0 or ma_then <= 0 or ma_now <= ma_then:
            continue  # only a *rising* MA counts as support worth bouncing off
        distance = abs(close - ma_now) / ma_now
        touch_score = _clamp(1 - distance / MA_TOUCH_TOLERANCE)
        if touch_score > best_ma_score:
            best_ma_score = touch_score
            best_ma_name = name

    combined = 0.5 * range_score + 0.5 * best_ma_score
    return combined, position_in_range, best_ma_name


def _pullback_depth(df: pd.DataFrame) -> float:
    recent_high = df["High"].tail(RECENT_HIGH_WINDOW).max()
    close = df["Close"].iloc[-1]
    if recent_high <= 0:
        return 0.0
    pullback_pct = (recent_high - close) / recent_high
    return _triangular(pullback_pct, low=0.0, peak=0.10, high=0.25)


def _rsi_pullback_zone(df: pd.DataFrame) -> float:
    return _triangular(df["rsi14"].iloc[-1], low=25, peak=45, high=62)


def _volume_contraction(df: pd.DataFrame) -> float:
    recent_avg = df["Volume"].tail(10).mean()
    prior_avg = df["Volume"].iloc[-40:-10].mean()
    if not prior_avg or np.isnan(prior_avg) or prior_avg <= 0:
        return 0.0
    ratio = recent_avg / prior_avg
    return _clamp((1.2 - ratio) / 0.5)


def _candlestick_pattern(df: pd.DataFrame, range_low: float) -> tuple[float, list[dict]]:
    patterns_df = detect_all_patterns(df)
    recent = patterns_df.tail(PATTERN_LOOKBACK)
    detected = []
    best_weight = 0.0
    for date, row in recent.iterrows():
        for name, is_hit in row.items():
            if bool(is_hit):
                weight = PATTERN_WEIGHTS[name]
                bar_low = df.loc[date, "Low"]
                near_low = range_low > 0 and (bar_low - range_low) / range_low <= 0.05
                effective = weight * (1.0 if near_low else 0.6)
                detected.append(
                    {
                        "name": name,
                        "date": str(date.date()) if hasattr(date, "date") else str(date),
                        "near_low": near_low,
                    }
                )
                best_weight = max(best_weight, effective)
    return _clamp(best_weight), detected


def score_ticker_pullback(ticker: str, raw_df: pd.DataFrame) -> PullbackScoreResult | None:
    """
    Compute an uptrend-pullback score for one ticker given its raw OHLCV
    history. Returns None if there isn't enough data, the price is too low,
    or the stock isn't in an established uptrend to begin with (this scan
    is specifically for dips within an uptrend, not reversals).
    """
    if raw_df is None or len(raw_df) < MIN_BARS:
        return None

    df = add_all_indicators(raw_df)
    last = df.iloc[-1]
    if last[["Close", "rsi14", "sma20", "sma50", "sma200"]].isna().any():
        return None
    if last["Close"] < MIN_PRICE:
        return None
    if not _is_established_uptrend(df):
        return None

    support_score, position_in_range, near_ma = _support_proximity(df)
    range_low = df["Low"].tail(RANGE_WINDOW).min()
    pattern_score, patterns = _candlestick_pattern(df, range_low)
    recent_high = df["High"].tail(RECENT_HIGH_WINDOW).max()
    pct_below_high = (recent_high - last["Close"]) / recent_high if recent_high > 0 else 0.0

    components = {
        "uptrend_strength": _uptrend_strength(df),
        "support_proximity": support_score,
        "pullback_depth": _pullback_depth(df),
        "rsi_pullback_zone": _rsi_pullback_zone(df),
        "volume_contraction": _volume_contraction(df),
        "candlestick_pattern": pattern_score,
    }

    weighted = {k: round(v * WEIGHTS[k], 2) for k, v in components.items()}
    total = round(sum(weighted.values()), 1)
    total = max(0.0, min(100.0, total))

    if total >= 70:
        verdict = "Strong pullback buy setup"
    elif total >= 55:
        verdict = "Pulling into support"
    elif total >= 40:
        verdict = "Early pullback / watchlist"
    else:
        verdict = "No clear setup"

    return PullbackScoreResult(
        ticker=ticker,
        score=total,
        components=weighted,
        patterns=patterns,
        last_close=round(float(last["Close"]), 2),
        position_in_range=round(position_in_range * 100, 1),
        pct_below_high=round(pct_below_high * 100, 1),
        near_ma=near_ma,
        rsi14=round(float(last["rsi14"]), 1),
        as_of=str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        verdict=verdict,
    )

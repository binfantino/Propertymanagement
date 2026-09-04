"""
"Gap and go" scanner: turns a ticker's OHLCV history into a 0-100 score
estimating how well it fits a bullish gap-up breakout that's pressing into
(or riding) the upper Bollinger Band on the daily chart.

This is a momentum/breakout setup, unlike scanner.py's "bottoming out"
scan (a reversal after a decline) or pullback_scanner.py's "buy the dip"
scan (a pause within an uptrend). Here the stock has already made an
aggressive move -- a gap up on above-average volume -- and the signal is
that it's holding those gains near the top of its volatility band rather
than fading back down.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import add_all_indicators
from .scoring_utils import clamp as _clamp
from .scoring_utils import series_then_now as _series_then_now
from .scoring_utils import triangular as _triangular

# Component weights, must sum to 100.
WEIGHTS = {
    "gap_magnitude": 25,
    "upper_band_position": 25,
    "volume_confirmation": 20,
    "follow_through": 15,
    "trend_context": 15,
}
assert sum(WEIGHTS.values()) == 100

MIN_BARS = 100
MIN_PRICE = 5.0
GAP_LOOKBACK = 3  # how many recent sessions can count as "the" gap day
MIN_GAP_PCT = 0.02  # below this isn't really a gap, just noise
MIN_PERCENT_B = 0.85  # must still be at/near the upper band today to qualify
VOLUME_LOOKBACK = 20


@dataclass
class GapScoreResult:
    ticker: str
    score: float
    components: dict = field(default_factory=dict)
    patterns: list = field(default_factory=list)
    last_close: float = 0.0
    gap_pct: float = 0.0
    gap_date: str = ""
    percent_b: float = 0.0
    gap_filled: bool = False
    rsi14: float = 0.0
    as_of: str = ""
    verdict: str = ""


def _find_gap(df: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """
    The largest up-gap (open vs. prior close) within the last GAP_LOOKBACK
    sessions. Returns None if nothing in that window qualifies as a real gap.
    """
    opens = df["Open"].tail(GAP_LOOKBACK + 1)
    prev_closes = df["Close"].shift(1).reindex(opens.index)
    gap_pct = ((opens - prev_closes) / prev_closes).dropna()
    if gap_pct.empty:
        return None
    gap_date = gap_pct.idxmax()
    best_gap = gap_pct.loc[gap_date]
    if best_gap < MIN_GAP_PCT:
        return None
    return float(best_gap), gap_date


def _upper_band_position(df: pd.DataFrame) -> float:
    last = df.iloc[-1]
    band_range = last["bb_upper"] - last["bb_lower"]
    if band_range <= 0:
        return 0.5
    return float((last["Close"] - last["bb_lower"]) / band_range)


def _gap_magnitude_score(gap_pct: float) -> float:
    return _triangular(gap_pct, low=MIN_GAP_PCT, peak=0.06, high=0.20)


def _upper_band_score(percent_b: float) -> float:
    return _clamp((percent_b - 0.7) / 0.3)


def _volume_confirmation(df: pd.DataFrame, gap_date: pd.Timestamp) -> float:
    pos = df.index.get_loc(gap_date)
    window_start = max(0, pos - VOLUME_LOOKBACK)
    prior_avg = df["Volume"].iloc[window_start:pos].mean()
    gap_day_volume = df["Volume"].iloc[pos]
    if not prior_avg or np.isnan(prior_avg) or prior_avg <= 0:
        return 0.0
    ratio = gap_day_volume / prior_avg
    return _clamp((ratio - 1.0) / 1.5)


def _gap_filled(df: pd.DataFrame, gap_date: pd.Timestamp) -> bool:
    pos = df.index.get_loc(gap_date)
    pre_gap_close = df["Close"].iloc[pos - 1] if pos > 0 else df["Open"].iloc[pos]
    lows_since_gap = df["Low"].iloc[pos:]
    return bool((lows_since_gap < pre_gap_close).any())


def _follow_through(df: pd.DataFrame, gap_date: pd.Timestamp) -> float:
    last = df.iloc[-1]
    day_range = last["High"] - last["Low"]
    close_position = (last["Close"] - last["Low"]) / day_range if day_range > 0 else 0.5
    held = not _gap_filled(df, gap_date)
    return 0.6 * _clamp(close_position) + 0.4 * (1.0 if held else 0.0)


def _trend_context(df: pd.DataFrame) -> float:
    last = df.iloc[-1]
    if np.isnan(last["sma50"]):
        return 0.5  # not enough history to judge -- neutral, don't punish or reward
    above_sma50 = 1.0 if last["Close"] > last["sma50"] else 0.0

    then_now = _series_then_now(df["sma50"], lookback=20)
    if then_now is None or then_now[0] <= 0:
        slope_score = 0.5
    else:
        sma50_then, sma50_now = then_now
        slope_score = _clamp((sma50_now - sma50_then) / sma50_then / 0.05)

    return 0.5 * above_sma50 + 0.5 * slope_score


def score_ticker_gap(ticker: str, raw_df: pd.DataFrame) -> GapScoreResult | None:
    """
    Compute a gap-and-go score for one ticker given its raw OHLCV history.
    Returns None if there isn't enough data, the price is too low, there's
    no qualifying gap in the last few sessions, or price has since fallen
    back well off the upper Bollinger Band.
    """
    if raw_df is None or len(raw_df) < MIN_BARS:
        return None

    df = add_all_indicators(raw_df)
    last = df.iloc[-1]
    if last[["Close", "rsi14", "bb_upper", "bb_lower"]].isna().any():
        return None
    if last["Close"] < MIN_PRICE:
        return None

    gap = _find_gap(df)
    if gap is None:
        return None
    gap_pct, gap_date = gap

    percent_b = _upper_band_position(df)
    if percent_b < MIN_PERCENT_B:
        return None

    components = {
        "gap_magnitude": _gap_magnitude_score(gap_pct),
        "upper_band_position": _upper_band_score(percent_b),
        "volume_confirmation": _volume_confirmation(df, gap_date),
        "follow_through": _follow_through(df, gap_date),
        "trend_context": _trend_context(df),
    }

    weighted = {k: round(v * WEIGHTS[k], 2) for k, v in components.items()}
    total = round(sum(weighted.values()), 1)
    total = max(0.0, min(100.0, total))

    if total >= 70:
        verdict = "Strong gap-and-go breakout"
    elif total >= 55:
        verdict = "Gap holding near the upper band"
    elif total >= 40:
        verdict = "Early / marginal gap"
    else:
        verdict = "No clear setup"

    return GapScoreResult(
        ticker=ticker,
        score=total,
        components=weighted,
        patterns=[],
        last_close=round(float(last["Close"]), 2),
        gap_pct=round(gap_pct * 100, 1),
        gap_date=str(gap_date.date()) if hasattr(gap_date, "date") else str(gap_date),
        percent_b=round(percent_b * 100, 1),
        gap_filled=_gap_filled(df, gap_date),
        rsi14=round(float(last["rsi14"]), 1),
        as_of=str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        verdict=verdict,
    )

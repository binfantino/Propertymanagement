"""
"Gap fill reversal" scanner: turns a ticker's OHLCV history into a 0-100
score estimating how well it fits a bullish reversal where a stock gapped
down at some point, left that gap unfilled through a decline, and has now
gapped back up and closed (filled) it.

Unlike gap_scanner.py (which looks for a *fresh* gap up riding the upper
Bollinger Band), this mode is specifically about reclaiming old overhead
supply: the down-gap has to have stayed open until the more recent up-gap
closes it, which is a structurally different -- and less common -- event.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import add_all_indicators
from .scoring_utils import clamp as _clamp
from .scoring_utils import triangular as _triangular

# Component weights, must sum to 100.
WEIGHTS = {
    "gap_closure": 30,
    "up_gap_magnitude": 20,
    "volume_confirmation": 20,
    "follow_through": 15,
    "down_gap_severity": 15,
}
assert sum(WEIGHTS.values()) == 100

MIN_BARS = 100
MIN_PRICE = 5.0
UP_GAP_LOOKBACK = 3  # how recent the up-gap that does the filling must be
DOWN_GAP_LOOKBACK = 60  # how far back to look for the down-gap it's filling
MIN_GAP_PCT = 0.02  # below this isn't really a gap in either direction
MIN_FILL_RATIO = 0.97  # must have closed at least this much of the down-gap's void
VOLUME_LOOKBACK = 20


@dataclass
class GapFillScoreResult:
    ticker: str
    score: float
    components: dict = field(default_factory=dict)
    patterns: list = field(default_factory=list)
    last_close: float = 0.0
    up_gap_pct: float = 0.0
    up_gap_date: str = ""
    down_gap_pct: float = 0.0
    down_gap_date: str = ""
    fill_ratio: float = 0.0
    rsi14: float = 0.0
    as_of: str = ""
    verdict: str = ""


def _gap_pct_series(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    return (df["Open"] - prev_close) / prev_close


def _find_up_gap(gap_pct: pd.Series) -> tuple[float, pd.Timestamp] | None:
    recent = gap_pct.tail(UP_GAP_LOOKBACK).dropna()
    candidates = recent[recent >= MIN_GAP_PCT]
    if candidates.empty:
        return None
    up_gap_date = candidates.idxmax()
    return float(candidates.loc[up_gap_date]), up_gap_date


def _find_down_gap(gap_pct: pd.Series, before: pd.Timestamp) -> tuple[float, pd.Timestamp] | None:
    window = gap_pct.loc[:before].iloc[-(DOWN_GAP_LOOKBACK + 1) : -1].dropna()
    candidates = window[window <= -MIN_GAP_PCT]
    if candidates.empty:
        return None
    down_gap_date = candidates.index[-1]  # most recent qualifying down-gap before the up-gap
    return float(candidates.loc[down_gap_date]), down_gap_date


def _already_filled_before(df: pd.DataFrame, down_gap_date: pd.Timestamp, up_gap_date: pd.Timestamp, ceiling: float) -> bool:
    """True if the down-gap was reclaimed at some point before the up-gap --
    i.e. this isn't the event that actually closes it."""
    pos_down = df.index.get_loc(down_gap_date)
    pos_up = df.index.get_loc(up_gap_date)
    if pos_up <= pos_down:
        return True
    window = df["High"].iloc[pos_down:pos_up]
    return bool((window >= ceiling).any())


def score_ticker_gap_fill(ticker: str, raw_df: pd.DataFrame) -> GapFillScoreResult | None:
    """
    Compute a gap-fill-reversal score for one ticker given its raw OHLCV
    history. Returns None unless there's a down-gap in the lookback window
    that stayed unfilled until a more recent up-gap, and price has now
    closed at least MIN_FILL_RATIO of the way back to the pre-down-gap
    close level.
    """
    if raw_df is None or len(raw_df) < MIN_BARS:
        return None

    df = add_all_indicators(raw_df)
    last = df.iloc[-1]
    if last[["Close", "rsi14"]].isna().any():
        return None
    if last["Close"] < MIN_PRICE:
        return None

    gap_pct = _gap_pct_series(df)

    up_gap = _find_up_gap(gap_pct)
    if up_gap is None:
        return None
    up_gap_pct, up_gap_date = up_gap

    down_gap = _find_down_gap(gap_pct, before=up_gap_date)
    if down_gap is None:
        return None
    down_gap_pct, down_gap_date = down_gap

    down_gap_pos = df.index.get_loc(down_gap_date)
    if down_gap_pos == 0:
        return None
    ceiling = float(df["Close"].iloc[down_gap_pos - 1])  # pre-down-gap close: top of the void
    floor = float(df["Open"].iloc[down_gap_pos])  # the down-gap day's open: bottom of the void
    void_height = ceiling - floor
    if void_height <= 0:
        return None

    if _already_filled_before(df, down_gap_date, up_gap_date, ceiling):
        return None

    last_close = float(last["Close"])
    fill_ratio = (last_close - floor) / void_height
    if fill_ratio < MIN_FILL_RATIO:
        return None

    up_gap_pos = df.index.get_loc(up_gap_date)
    volume_window_start = max(0, up_gap_pos - VOLUME_LOOKBACK)
    prior_avg_volume = df["Volume"].iloc[volume_window_start:up_gap_pos].mean()
    up_gap_volume = df["Volume"].iloc[up_gap_pos]
    if prior_avg_volume and not np.isnan(prior_avg_volume) and prior_avg_volume > 0:
        volume_score = _clamp((up_gap_volume / prior_avg_volume - 1.0) / 1.5)
    else:
        volume_score = 0.0

    day_range = last["High"] - last["Low"]
    close_position = (last["Close"] - last["Low"]) / day_range if day_range > 0 else 0.5
    held_since_fill = not bool((df["Low"].iloc[up_gap_pos:-1] < ceiling).any())
    follow_through_score = 0.6 * _clamp(close_position) + 0.4 * (1.0 if held_since_fill else 0.0)

    overshoot_in_void_heights = (last_close - ceiling) / void_height
    closure_score = _clamp(0.5 + overshoot_in_void_heights / 0.5)

    components = {
        "gap_closure": closure_score,
        "up_gap_magnitude": _triangular(up_gap_pct, low=MIN_GAP_PCT, peak=0.06, high=0.20),
        "volume_confirmation": volume_score,
        "follow_through": follow_through_score,
        "down_gap_severity": _clamp(abs(down_gap_pct) / 0.12),
    }

    weighted = {k: round(v * WEIGHTS[k], 2) for k, v in components.items()}
    total = round(sum(weighted.values()), 1)
    total = max(0.0, min(100.0, total))

    if total >= 70:
        verdict = "Strong gap-fill reversal"
    elif total >= 55:
        verdict = "Reclaiming the gap"
    elif total >= 40:
        verdict = "Early / marginal reclaim"
    else:
        verdict = "No clear setup"

    return GapFillScoreResult(
        ticker=ticker,
        score=total,
        components=weighted,
        patterns=[],
        last_close=round(last_close, 2),
        up_gap_pct=round(up_gap_pct * 100, 1),
        up_gap_date=str(up_gap_date.date()) if hasattr(up_gap_date, "date") else str(up_gap_date),
        down_gap_pct=round(down_gap_pct * 100, 1),
        down_gap_date=str(down_gap_date.date()) if hasattr(down_gap_date, "date") else str(down_gap_date),
        fill_ratio=round(fill_ratio * 100, 1),
        rsi14=round(float(last["rsi14"]), 1),
        as_of=str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        verdict=verdict,
    )

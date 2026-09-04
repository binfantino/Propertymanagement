"""Small numeric helpers shared by the scanner scoring modules."""

from __future__ import annotations

import numpy as np
import pandas as pd


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if np.isnan(x):
        return 0.0
    return max(lo, min(hi, x))


def triangular(x: float, low: float, peak: float, high: float) -> float:
    """0 at/outside [low, high], rising to 1 at peak. Used for "sweet spot" ranges."""
    if np.isnan(x) or x <= low or x >= high:
        return 0.0
    if x <= peak:
        return (x - low) / (peak - low)
    return (high - x) / (high - peak)


def series_then_now(series: pd.Series, lookback: int) -> tuple[float, float] | None:
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

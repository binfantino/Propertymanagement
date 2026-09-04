from __future__ import annotations

from pydantic import BaseModel


class PatternHit(BaseModel):
    name: str
    date: str
    near_low: bool


class ScanResultOut(BaseModel):
    ticker: str
    score: float
    verdict: str
    mode: str
    last_close: float
    metric_label: str
    metric_value: float
    near_ma: str | None = None
    rsi14: float
    as_of: str
    components: dict[str, float]
    patterns: list[PatternHit]


class ScanResponse(BaseModel):
    universe_size: int
    universe_source: str
    scanned: int
    period: str
    results: list[ScanResultOut]


class Candle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class IndicatorPoint(BaseModel):
    date: str
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    rsi14: float | None = None
    macd: float | None = None
    signal: float | None = None
    hist: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None


class StockDetailResponse(BaseModel):
    ticker: str
    period: str
    result: ScanResultOut | None
    candles: list[Candle]
    indicators: list[IndicatorPoint]

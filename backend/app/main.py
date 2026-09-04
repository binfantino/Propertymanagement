from __future__ import annotations

import logging
import math

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import data
from .gap_scanner import GapScoreResult, score_ticker_gap
from .indicators import add_all_indicators
from .pullback_scanner import PullbackScoreResult, score_ticker_pullback
from .scanner import ScoreResult, score_ticker
from .schemas import (
    Candle,
    IndicatorPoint,
    PatternHit,
    ScanResponse,
    ScanResultOut,
    StockDetailResponse,
)
from .universe import DEFAULT_UNIVERSE

# Uptrend-pullback scoring needs a valid, slope-able SMA200, which needs more
# bars than "6mo" of daily data provides -- silently upgrade to "1y" so that
# mode doesn't just come back empty.
MODE_MIN_PERIOD = {"pullback": "1y"}
_PERIOD_ORDER = ["6mo", "1y", "2y"]


def _effective_period(mode: str, period: str) -> str:
    floor = MODE_MIN_PERIOD.get(mode)
    if floor and _PERIOD_ORDER.index(period) < _PERIOD_ORDER.index(floor):
        return floor
    return period

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Bottoming Scanner", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_out(r: ScoreResult | PullbackScoreResult | GapScoreResult) -> ScanResultOut:
    if isinstance(r, PullbackScoreResult):
        mode = "pullback"
        metric_label = "Position in range"
        metric_value = r.position_in_range
        near_ma = r.near_ma
    elif isinstance(r, GapScoreResult):
        mode = "gap_up"
        metric_label = "Gap %"
        metric_value = r.gap_pct
        near_ma = None
    else:
        mode = "bottoming"
        metric_label = "% off low"
        metric_value = r.pct_off_low
        near_ma = None

    return ScanResultOut(
        ticker=r.ticker,
        score=r.score,
        verdict=r.verdict,
        mode=mode,
        last_close=r.last_close,
        metric_label=metric_label,
        metric_value=metric_value,
        near_ma=near_ma,
        rsi14=r.rsi14,
        as_of=r.as_of,
        components=r.components,
        patterns=[PatternHit(**p) for p in r.patterns],
    )


def _score(mode: str, ticker: str, df) -> ScoreResult | PullbackScoreResult | GapScoreResult | None:
    if mode == "pullback":
        return score_ticker_pullback(ticker, df)
    if mode == "gap_up":
        return score_ticker_gap(ticker, df)
    return score_ticker(ticker, df)


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/universe")
def get_universe():
    return {"count": len(DEFAULT_UNIVERSE), "tickers": DEFAULT_UNIVERSE}


@app.get("/api/scan", response_model=ScanResponse)
def scan(
    limit: int = Query(25, ge=1, le=200),
    min_score: float = Query(40.0, ge=0, le=100),
    period: str = Query("1y", pattern="^(6mo|1y|2y)$"),
    mode: str = Query("bottoming", pattern="^(bottoming|pullback|gap_up)$"),
    tickers: str | None = Query(
        None, description="Comma-separated ticker list to scan instead of the default universe"
    ),
):
    period = _effective_period(mode, period)
    universe = [t.strip().upper() for t in tickers.split(",")] if tickers else DEFAULT_UNIVERSE
    histories = data.fetch_batch(universe, period=period)

    results: list[ScoreResult | PullbackScoreResult | GapScoreResult] = []
    for ticker, df in histories.items():
        result = _score(mode, ticker, df)
        if result is not None and result.score >= min_score:
            results.append(result)

    results.sort(key=lambda r: r.score, reverse=True)
    top = results[:limit]

    return ScanResponse(
        universe_size=len(universe),
        scanned=len(histories),
        period=period,
        results=[_to_out(r) for r in top],
    )


@app.get("/api/stock/{ticker}", response_model=StockDetailResponse)
def stock_detail(
    ticker: str,
    period: str = Query("1y", pattern="^(6mo|1y|2y)$"),
    mode: str = Query("bottoming", pattern="^(bottoming|pullback|gap_up)$"),
):
    ticker = ticker.upper()
    period = _effective_period(mode, period)
    raw_df = data.fetch_history(ticker, period=period)
    if raw_df is None or raw_df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {ticker}")

    result = _score(mode, ticker, raw_df)
    df = add_all_indicators(raw_df)

    candles = [
        Candle(
            date=str(idx.date()) if hasattr(idx, "date") else str(idx),
            open=round(float(row["Open"]), 2),
            high=round(float(row["High"]), 2),
            low=round(float(row["Low"]), 2),
            close=round(float(row["Close"]), 2),
            volume=float(row["Volume"]),
        )
        for idx, row in raw_df.iterrows()
    ]

    indicator_points = [
        IndicatorPoint(
            date=str(idx.date()) if hasattr(idx, "date") else str(idx),
            sma20=_safe_float(row.get("sma20")),
            sma50=_safe_float(row.get("sma50")),
            sma200=_safe_float(row.get("sma200")),
            rsi14=_safe_float(row.get("rsi14")),
            macd=_safe_float(row.get("macd")),
            signal=_safe_float(row.get("signal")),
            hist=_safe_float(row.get("hist")),
            bb_upper=_safe_float(row.get("bb_upper")),
            bb_lower=_safe_float(row.get("bb_lower")),
        )
        for idx, row in df.iterrows()
    ]

    return StockDetailResponse(
        ticker=ticker,
        period=period,
        result=_to_out(result) if result else None,
        candles=candles,
        indicators=indicator_points,
    )


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

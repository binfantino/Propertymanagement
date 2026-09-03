"""
Market data access via yfinance, with a short-lived in-memory cache so a
scan of a couple hundred tickers doesn't refetch on every request and
repeated single-stock lookups don't hammer Yahoo Finance.
"""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# Cache raw histories for 15 minutes -- plenty fresh for an end-of-day/swing
# scanner, and avoids re-downloading the whole universe on every page load.
_history_cache: TTLCache = TTLCache(maxsize=1000, ttl=15 * 60)

BATCH_SIZE = 60


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[_OHLCV_COLUMNS].dropna(how="all")
    df = df.dropna(subset=["Close"])
    return df


def fetch_history(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    """Fetch OHLCV history for a single ticker, using the cache when possible."""
    cache_key = (ticker, period)
    if cache_key in _history_cache:
        return _history_cache[cache_key]

    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if df is None or df.empty:
            return None
        df = _clean(df)
    except Exception:
        logger.exception("Failed to fetch history for %s", ticker)
        return None

    _history_cache[cache_key] = df
    return df


def fetch_batch(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV history for many tickers at once. Uses yfinance's
    multi-ticker download in batches (faster than one request per ticker)
    and falls back to per-ticker caching so a partial failure in one batch
    doesn't lose data already fetched for others.
    """
    results: dict[str, pd.DataFrame] = {}
    to_fetch = [t for t in tickers if (t, period) not in _history_cache]

    for t in tickers:
        if (t, period) in _history_cache:
            results[t] = _history_cache[(t, period)]

    for i in range(0, len(to_fetch), BATCH_SIZE):
        batch = to_fetch[i : i + BATCH_SIZE]
        try:
            data = yf.download(
                batch,
                period=period,
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception:
            logger.exception("Batch download failed for %s", batch)
            continue

        for t in batch:
            try:
                if len(batch) == 1:
                    df = data
                else:
                    df = data[t]
                df = _clean(df)
                if df.empty:
                    continue
                _history_cache[(t, period)] = df
                results[t] = df
            except Exception:
                logger.warning("No data returned for %s", t)

    return results

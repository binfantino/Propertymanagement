"""
Default scan universe: the S&P 500 and Nasdaq-100 constituents.

`get_universe()` is what callers should use: it tries to fetch the current,
complete constituent lists straight from Wikipedia (cached for a day, since
index membership rarely changes), and falls back to a curated static
snapshot below if that fetch fails for any reason -- no internet access in
this environment, Wikipedia's table layout changing, etc. The static
snapshot is a best-effort, point-in-time approximation and *will* drift out
of date; it exists only so the app still works offline, not as the source
of truth.
"""

from __future__ import annotations

import logging

import pandas as pd
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# --- Static fallback snapshot -----------------------------------------------
# Approximate S&P 500 constituents, broad sector coverage. Not guaranteed to
# be complete or current -- see module docstring.
SP500_FALLBACK: list[str] = [
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "BRK-B", "TSLA", "AVGO",
    "JPM", "LLY", "V", "UNH", "XOM", "MA", "COST", "HD", "PG", "JNJ", "NFLX",
    "MRK", "ABBV", "CVX", "BAC", "CRM", "AMD", "PEP", "KO", "TMO", "WMT",
    "ADBE", "MCD", "CSCO", "ABT", "ACN", "LIN", "DIS", "WFC", "TXN", "DHR",
    "PM", "NEE", "GE", "VZ", "CMCSA", "INTU", "IBM", "NOW", "CAT", "AMAT",
    "UNP", "AMGN", "SPGI", "COP", "LOW", "HON", "BA", "QCOM", "GS", "PFE",
    "RTX", "T", "ELV", "SYK", "ISRG", "BLK", "SBUX", "DE", "PLD", "MDT",
    "ADP", "GILD", "MS", "LMT", "BKNG", "TJX", "AXP", "MDLZ", "VRTX", "C",
    "SCHW", "ADI", "CB", "MMC", "REGN", "ETN", "PANW", "CI", "SO", "ZTS",
    "BSX", "MU", "PGR", "FI", "DUK", "SLB", "APD", "BMY", "EOG", "SNPS",
    "ITW", "CDNS", "AON", "TGT", "NOC", "CME", "WM", "MO", "GD", "CSX",
    "HUM", "EQIX", "PYPL", "CL", "MCK", "COR", "ORLY", "MPC", "FCX", "APH", "EMR",
    "PSX", "NSC", "MAR", "AJG", "ROP", "FTNT", "PSA", "TT", "MSI",
    "PCAR", "AZO", "ADSK", "MCO", "TDG", "HCA", "CARR", "NXPI", "USB",
    "TFC", "AIG", "SRE", "OXY", "MNST", "KLAC", "CPRT", "F", "GM", "DXCM",
    "PCG", "AFL", "ALL", "PRU", "MET", "SPG", "O", "D", "EXC", "AEP",
    "XEL", "ED", "PEG", "WEC", "ES", "FE", "ETR", "AWK", "PPL", "CMS",
    "STZ", "HSY", "MKC", "SYY", "KR", "ADM", "TSN", "HRL", "CHD", "CLX",
    "CAG", "CPB", "SJM", "TAP", "KDP", "KHC", "EL", "WBA", "DG", "DLTR",
    "WMB", "KMI", "OKE", "HES", "HAL", "BKR", "DVN", "FANG", "CTRA", "MRO", "APA", "TRGP", "EQT",
    "IVZ", "BEN", "MTB", "ZION", "CBOE", "NDAQ", "MKTX", "TROW", "RJF", "STT", "NTRS",
    "FITB", "HBAN", "RF", "KEY", "CFG", "DFS", "SYF", "WTW", "GL", "L", "GPN", "AMP",
    "IQV", "A", "BIIB", "MRNA", "RMD", "EW", "ALGN", "BAX", "BDX", "WAT", "MTD",
    "WST", "STE", "ZBH", "HOLX", "CAH", "CNC", "MOH", "VTRS", "DVA", "XRAY", "INCY", "GEHC",
    "PH", "CMI", "ROK", "DOV", "XYL", "AME", "IR", "SWK", "PWR", "JCI", "OTIS",
    "IEX", "FAST", "RSG", "UAL", "DAL", "LUV", "AAL", "EFX", "VRSK", "GWW", "URI",
    "MAS", "ALLE", "HWM", "TXT", "LHX", "LDOS", "HII", "GNRC", "NDSN", "PNR", "J",
    "SHW", "ECL", "NEM", "DOW", "DD", "PPG", "NUE", "VMC", "MLM", "ALB", "CTVA",
    "IFF", "LYB", "CE", "AVY", "PKG", "IP", "BALL", "AMCR", "STLD", "EMN", "MOS", "FMC",
    "AMT", "WELL", "DLR", "AVB", "EQR", "VTR", "SBAC", "ARE", "VICI", "INVH",
    "MAA", "ESS", "UDR", "KIM", "REG", "HST", "BXP", "IRM", "EXR", "CPT", "NNN",
    "EIX", "AEE", "CNP", "ATO", "PNW", "NI", "LNT", "EVRG",
    "NKE", "ABNB", "CMG", "HLT", "YUM", "ROST", "DHI", "LEN", "NVR", "PHM",
    "BBY", "EBAY", "ETSY", "EXPE", "DPZ", "POOL", "ULTA", "RL", "TSCO", "LVS", "WYNN",
    "MGM", "CCL", "RCL", "NCLH", "APTV", "LKQ", "GPC", "KMX", "DECK",
    "CVS", "GEN", "AKAM", "EPAM", "GDDY", "TYL", "PTC", "TDY", "ZBRA",
    "TER", "ENPH", "ON", "MPWR", "SWKS", "QRVO", "KEYS", "MCHP", "CTSH", "IT",
    "FICO", "GLW", "TEL", "VRSN", "PAYC", "PAYX", "FIS", "JKHY", "DXC",
    "NWSA", "NWS", "FOXA", "FOX", "PARA", "WBD", "OMC", "IPG", "EA", "TTWO", "MTCH", "LYV",
]

# Approximate Nasdaq-100 constituents. Heavily overlaps with SP500_FALLBACK
# (most Nasdaq-100 names are also S&P 500 members) -- DEFAULT_UNIVERSE dedupes.
NASDAQ100_FALLBACK: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA", "COST",
    "NFLX", "ASML", "AMD", "PEP", "ADBE", "LIN", "CSCO", "TMUS", "QCOM", "INTU",
    "AMAT", "TXN", "ISRG", "CMCSA", "AMGN", "HON", "BKNG", "VRTX", "PANW", "ADP",
    "GILD", "SBUX", "MU", "ADI", "LRCX", "MDLZ", "REGN", "PYPL", "KLAC", "SNPS",
    "CDNS", "MELI", "CRWD", "MAR", "CSX", "ORLY", "CTAS", "ABNB", "PCAR", "ROP",
    "NXPI", "WDAY", "FTNT", "DASH", "MNST", "PAYX", "CPRT", "ROST", "ODFL", "AEP",
    "KDP", "EA", "FAST", "KHC", "VRSK", "GEHC", "XEL", "BKR", "EXC", "CCEP",
    "DDOG", "TTD", "CTSH", "ANSS", "ZS", "ON", "FANG", "GFS", "MCHP", "CDW",
    "TEAM", "IDXX", "DXCM", "ILMN", "WBD", "LULU", "SIRI", "MRVL", "ARM", "DLTR",
    "MDB", "BIIB", "ALGN", "JD", "PDD", "CSGP", "CHTR", "APP",
]

DEFAULT_UNIVERSE: list[str] = sorted(set(SP500_FALLBACK) | set(NASDAQ100_FALLBACK))


# --- Live fetch + cache ------------------------------------------------------

_universe_cache: TTLCache = TTLCache(maxsize=1, ttl=24 * 60 * 60)


def _find_ticker_column(table: pd.DataFrame) -> str | None:
    for candidate in ("Symbol", "Ticker"):
        if candidate in table.columns:
            return candidate
    return None


def _fetch_tickers(url: str) -> set[str]:
    for table in pd.read_html(url):
        column = _find_ticker_column(table)
        if column is not None:
            return {str(t).strip().replace(".", "-") for t in table[column].dropna()}
    raise ValueError(f"no ticker column found in any table at {url}")


def fetch_live_universe() -> list[str]:
    """
    Fetch the current S&P 500 and Nasdaq-100 constituent lists from
    Wikipedia. Raises on any failure (no internet, page layout changed,
    etc.) -- use get_universe() for a cached, fallback-safe version.
    """
    sp500 = _fetch_tickers("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    nasdaq100 = _fetch_tickers("https://en.wikipedia.org/wiki/Nasdaq-100")
    tickers = sp500 | nasdaq100
    if not tickers:
        raise ValueError("parsed zero tickers from Wikipedia")
    return sorted(tickers)


def get_universe_info() -> dict:
    """
    Cached (~1 day) universe lookup. Tries the live Wikipedia fetch first;
    on failure, logs the reason and falls back to the static snapshot. The
    "source" field tells callers which one they got.
    """
    cached = _universe_cache.get("current")
    if cached is not None:
        return cached

    try:
        tickers = fetch_live_universe()
        info = {"tickers": tickers, "source": "live", "count": len(tickers)}
    except Exception:
        logger.warning("Live universe fetch failed, using static fallback snapshot", exc_info=True)
        info = {"tickers": DEFAULT_UNIVERSE, "source": "fallback_snapshot", "count": len(DEFAULT_UNIVERSE)}

    _universe_cache["current"] = info
    return info


def get_universe() -> list[str]:
    return get_universe_info()["tickers"]

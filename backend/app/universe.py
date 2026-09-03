"""
Default scan universe: US mid-cap and large-cap common stocks.

This is a curated, static snapshot spanning S&P 500 (large-cap) and S&P 400
(mid-cap) constituents across sectors. It intentionally avoids depending on a
live web scrape at import time (fragile, and this environment's network
policy may block it) but `fetch_live_universe()` below can refresh it from
Wikipedia when internet access is available, with the static list used as a
fallback if that fetch fails for any reason.
"""

from __future__ import annotations

# Large-cap (S&P 500 style) names, broad sector coverage.
LARGE_CAP: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "BRK-B", "TSLA", "AVGO",
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
    "HUM", "EQIX", "PYPL", "CL", "MCK", "ORLY", "MPC", "FCX", "APH", "EMR",
    "PSX", "NSC", "MAR", "PXD", "AJG", "ROP", "FTNT", "PSA", "TT", "MSI",
    "PCAR", "AZO", "ADSK", "MCO", "TDG", "HCA", "CARR", "NXPI", "USB",
    "TFC", "AIG", "SRE", "OXY", "MNST", "KLAC", "CPRT", "F", "GM", "DXCM",
    "PCG", "AFL", "ALL", "PRU", "MET", "SPG", "O", "D", "EXC", "AEP",
    "XEL", "ED", "PEG", "WEC", "ES", "FE", "ETR", "AWK", "PPL", "CMS",
]

# Mid-cap (S&P 400 style) names, broad sector coverage.
MID_CAP: list[str] = [
    "DECK", "BJ", "RRX", "OVV", "TOL", "PNFP", "GGG", "AXTA", "SSD", "WMS",
    "FND", "MAT", "CHDN", "BLD", "CASY", "CHE", "SAIA", "EXP", "MEDP",
    "FIVE", "AAON", "UFPI", "RGA", "WTS", "EME", "MKSI", "BRBR", "FN",
    "POOL", "RBC", "GNTX", "CR", "SFM", "LNTH", "SAIC", "WEX", "ENSG",
    "ITT", "KNSL", "MTG", "AVT", "JXN", "RHI", "OGE", "CVLT", "SLM",
    "UGI", "THG", "CACI", "FLS", "HRB", "WWD", "SPSC", "BWXT", "CBSH",
    "CRUS", "GATX", "IBOC", "NOV", "TREX", "AGCO", "M", "KBR", "SEIC",
    "OLED", "CHRD", "ALSN", "CROX", "HGV", "GXO", "HUBG", "RGLD", "ELS",
    "STAG", "SKX", "TPX", "WSC", "EGP", "NNN", "ALV", "SNX", "CNM", "ATR",
    "WCC", "IEX", "TXT", "ORI", "PB", "GPK", "APAM", "AN", "CE", "JLL",
    "R", "SWX", "WTRG", "NYT", "MUR", "LII", "AYI", "FBIN", "MHK", "SON",
    "OSK", "CFR", "VMI", "MTZ", "UHS", "CNH", "CLH", "SEE", "ARW", "JBL",
    "PNW", "CIEN", "X", "NVT", "BIO", "CCK", "AA", "TAP", "HAS", "IPG",
    "FOXA", "PARA", "WBA", "GT", "HII", "LDOS", "JNPR", "AKAM", "ZBRA",
    "TER", "PFG", "L", "CFG", "KEY", "HBAN", "RF", "FITB", "SNA", "DOV",
]

DEFAULT_UNIVERSE: list[str] = sorted(set(LARGE_CAP) | set(MID_CAP))


def fetch_live_universe() -> list[str]:
    """
    Best-effort refresh of the universe from Wikipedia's S&P 500 / S&P 400
    constituent tables. Falls back to DEFAULT_UNIVERSE on any failure
    (no internet access, table layout change, etc.) so callers can always
    rely on getting a non-empty list back.
    """
    try:
        import pandas as pd

        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        sp400 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")[0]
        tickers = set(sp500["Symbol"]) | set(sp400["Symbol"])
        tickers = {t.replace(".", "-") for t in tickers}
        if tickers:
            return sorted(tickers)
    except Exception:
        pass
    return DEFAULT_UNIVERSE

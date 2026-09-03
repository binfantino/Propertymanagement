# Bottoming Scanner

Scans US mid- and large-cap stocks for technical setups that look like they're
basing after a decline and turning up -- using classic technical analysis and
candlestick pattern recognition. It's a screening heuristic to narrow down a
watchlist, not a trading signal or financial advice.

## How it scores a stock

For each ticker, ~1 year of daily OHLCV data is pulled and combined into a
0-100 "bottoming score" from eight independent signals:

| Signal | Weight | What it looks for |
|---|---|---|
| Prior downtrend context | 8 | Stock actually declined over the last ~3 months (so it's plausible this is a bottom, not just noise) |
| Proximity to recent low | 12 | Price is still near its 60-day low, not already off to the races |
| RSI oversold recovery | 20 | RSI(14) dipped below ~35 recently and is now curling back up |
| MACD turning up | 15 | MACD histogram rising, and/or a bullish MACD/signal crossover in the last few sessions |
| Volatility contraction | 8 | Bollinger Band width is narrow relative to its own recent history (a base forming) |
| Volume accumulation | 15 | Up-day volume outweighs down-day volume over the last two weeks |
| Candlestick reversal pattern | 15 | Hammer, inverted hammer, dragonfly doji, bullish engulfing, piercing line, morning star, or three white soldiers within the last 5 sessions, weighted higher if it printed right at the low |
| Higher-low structure | 7 | The most recent swing low sits above the prior swing low |

Stocks trading under $5, or without enough history to compute the
indicators, are filtered out. See `backend/app/scanner.py` for the exact
formulas and `backend/app/candlestick.py` for the pattern definitions.

The default scan universe (`backend/app/universe.py`) is a curated static
list of ~300 S&P 500 / S&P 400 style large- and mid-cap tickers. It can
optionally be refreshed live from Wikipedia's index constituent tables via
`fetch_live_universe()`, with the static list as a fallback.

## Running it

Requires Python 3.10+ and internet access (for Yahoo Finance data and the
frontend's charting library CDN).

```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

Then open http://localhost:8000 in a browser. Click "Scan market" to run the
scan (scanning the full ~300-ticker universe can take up to a minute or two
the first time; results are cached for 15 minutes), then click any row to see
its candlestick chart, RSI/MACD panes, and score breakdown.

### API

- `GET /api/scan?limit=25&min_score=40&period=1y` -- ranked scan results
- `GET /api/stock/{ticker}?period=1y` -- OHLCV history, indicators, and score
  breakdown for one ticker
- `GET /api/universe` -- the default ticker list

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Tests cover the indicator math, each candlestick pattern detector, and the
scanner's scoring behavior against synthetic OHLCV data (a crafted
decline-base-reversal scenario should outscore both an already-extended
uptrend and a stock still in freefall).

## Disclaimer

This tool is for research and educational purposes only. Technical analysis
does not predict future price movement with certainty. Nothing here is
investment advice -- do your own due diligence before trading.

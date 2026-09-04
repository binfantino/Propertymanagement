# Bottoming Scanner

Scans the S&P 500 and Nasdaq-100 for four different technical setups --
using classic technical analysis and candlestick pattern recognition. These
are screening heuristics to narrow down a watchlist, not trading signals or
financial advice.

- **Bottoming Reversal** -- stocks basing *after a decline* and showing signs
  of turning up.
- **Uptrend Pullback** -- stocks already in an *established uptrend* that
  have dipped to the bottom of their trading range (often right into a
  rising moving average) without breaking trend.
- **Gap Up / Upper Band** -- stocks that gapped up on strong volume and are
  still holding near or above the upper daily Bollinger Band, rather than
  having already faded back and filled the gap.
- **Gap Fill Reversal** -- stocks that gapped *down* at some point, left that
  gap unfilled through a decline, and have now gapped back *up* and reclaimed
  it -- an island-style reversal, distinct from a fresh gap-up breakout.

All four are exposed as separate scan modes in the app (toggle at the top
of the page) and share the same data pipeline and indicator math, but score
completely different things -- see below.

## How it scores a stock

### Bottoming Reversal mode

For each ticker, ~1 year of daily OHLCV data is combined into a 0-100
"bottoming score" from eight independent signals:

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

See `backend/app/scanner.py` for the exact formulas.

### Uptrend Pullback mode

This mode first **gates** on the stock actually being in an established
uptrend -- price above a rising 200-day SMA -- and excludes everything else
(a stock in a downtrend is never a "pullback" candidate). Candidates that
pass are scored 0-100 from six signals:

| Signal | Weight | What it looks for |
|---|---|---|
| Uptrend strength | 25 | 50-day SMA above a rising 200-day SMA, plus a persistent higher-low structure over the last ~6 months |
| Near range bottom / rising MA | 25 | Price sits in the lower ~35% of its last-40-session trading range, and/or within ~4% of a rising 20-, 50-, or 200-day moving average it could be bouncing off of |
| Healthy pullback depth | 15 | Pulled back roughly 5-20% off its recent high -- enough to be a real dip, not so much it looks like a trend break |
| RSI in pullback zone | 15 | RSI(14) has cooled to the ~30-55 range (a normal pullback), rather than staying overbought or collapsing into oversold |
| Volume drying up | 10 | Volume over the last 2 weeks is lower than during the preceding rally -- a low-conviction pullback, not distribution |
| Candlestick reversal pattern | 10 | A bullish reversal candle near the range low, same pattern set as the Bottoming Reversal mode |

Needs ~1 year+ of history for a meaningful 200-day SMA, so this mode
auto-upgrades a "6 months" period request to "1 year". See
`backend/app/pullback_scanner.py` for the exact formulas.

### Gap Up / Upper Band mode

This mode looks for the largest up-gap (today's open vs. the prior close) in
the last 3 sessions and **gates** on two things: the gap must be at least 2%,
and the stock must currently be trading in the top 30% of its Bollinger Band
width (%B >= 0.85) -- i.e. it's still up near the band today, not a gap that
already faded. Candidates that pass are scored 0-100 from five signals:

| Signal | Weight | What it looks for |
|---|---|---|
| Gap magnitude | 25 | The qualifying gap is in a "real but not exhausted" 2-20% sweet spot, peaking around 6% |
| At/above upper band | 25 | How far into (or past) the upper Bollinger Band the current close sits -- full credit at or above the band |
| Volume confirmation | 20 | Volume on the gap day vs. its own 20-day average -- a real gap should come with a volume surge |
| Follow-through / gap held | 15 | Closing near the day's high, and the gap not having been filled (price trading back below the pre-gap close) since |
| Trend context | 15 | Price above a rising 50-day SMA -- a supportive but not required tailwind |

A gap that gets partially undercut intraday but still closes back up near
the band still qualifies (with a lower follow-through score); one that fades
all the way back below the band is excluded outright, since it's no longer
a live "at the upper band" setup. See `backend/app/gap_scanner.py` for the
exact formulas.

### Gap Fill Reversal mode

This mode looks for the most recent up-gap (in the last 3 sessions, >=2%),
then looks further back (up to 60 sessions) for a down-gap that happened
*before* it. It **gates** on the down-gap having stayed unfilled the whole
way until the up-gap -- if price had already rallied back above the old
gap's ceiling through ordinary drift, that up-gap isn't closing anything and
the ticker is excluded -- and on price having now closed at least 97% of the
way back to that ceiling. Candidates that pass are scored 0-100 from five
signals:

| Signal | Weight | What it looks for |
|---|---|---|
| Gap closure completeness | 30 | How decisively price has reclaimed the old down-gap's ceiling, rather than just barely scraping it |
| Up-gap magnitude | 20 | The reclaiming gap is in the same 2-20% sweet spot as Gap Up mode, peaking around 6% |
| Volume confirmation | 20 | Volume on the up-gap day vs. its own 20-day average |
| Follow-through | 15 | Closing near the day's high, and price not having slipped back under the old ceiling since reclaiming it |
| Original down-gap severity | 15 | How large the initial down-gap was -- a bigger hole being filled is a more significant reversal |

A shallow, partial reclaim still qualifies once it crosses the 97% fill
threshold, just with a lower closure score; a down-gap that was already
filled by ordinary price action before any new gap up is excluded outright,
since there's no fresh reversal event to flag. See
`backend/app/gap_fill_scanner.py` for the exact formulas.

---

All four modes filter out stocks trading under $5, or without enough
history to compute their indicators. See `backend/app/candlestick.py` for
the candlestick pattern definitions shared by the first two.

### Scan universe

The app scans the S&P 500 and Nasdaq-100 (`backend/app/universe.py`). On
each scan it tries to fetch the current, complete constituent lists live
from Wikipedia (cached for ~24 hours, since index membership rarely
changes) and falls back to a bundled static snapshot of ~430 tickers if
that fetch fails -- no internet access, Wikipedia's page layout changing,
etc. (this is expected, for instance, in network-restricted sandboxes).
`GET /api/universe` and the scan status line report which one was actually
used (`live` or `fallback_snapshot`) so it's never ambiguous which universe
a scan ran against. The static snapshot is a best-effort, point-in-time
approximation and will drift out of date -- it exists only so the app keeps
working offline.

## Running it

Requires Python 3.10+ and internet access (for Yahoo Finance data and the
frontend's charting library CDN).

```bash
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

**Windows + a brand-new Python version:** if `pip install` tries to compile
pandas from source (a `meson setup` / `vswhere.exe` error), it means pip
can't find a prebuilt wheel for your Python version yet -- pandas/numpy
publish wheels for a new Python release a bit after it comes out.
`requirements.txt` uses minimum-version constraints so pip should pick a
newer, wheel-available release automatically; if it still fails, the
simplest fix is installing Python 3.11, 3.12, or 3.13 instead (all have
solid wheel coverage today) and creating your virtualenv with that version.

Then open http://localhost:8000 in a browser. Pick a scan mode at the top,
click "Scan market" to run it (scanning the full S&P 500 + Nasdaq-100
universe -- ~430-550+ tickers depending on whether the live fetch succeeds --
can take a minute or two the first time; results are cached for 15 minutes),
then click any row to see its candlestick chart, RSI/MACD panes, and score
breakdown.

### API

- `GET /api/scan?limit=25&min_score=40&period=1y&mode=bottoming` -- ranked
  scan results. `mode` is `bottoming` (default), `pullback`, `gap_up`, or
  `gap_fill`. Response includes `universe_source` (`live`, `fallback_snapshot`,
  or `custom`) and `universe_size`.
- `GET /api/stock/{ticker}?period=1y&mode=bottoming` -- OHLCV history,
  indicators, and score breakdown for one ticker, scored under the given mode.
- `GET /api/universe` -- the current scan universe, plus its `source` and
  `count`.

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Tests cover the indicator math, each candlestick pattern detector, the
universe live-fetch/cache/fallback behavior, and all four scanners' scoring
behavior against synthetic OHLCV data -- e.g. a crafted decline-base-reversal
scenario should outscore an already-extended uptrend and a stock still in
freefall (Bottoming Reversal mode); a stock that pulled back to a rising
moving average should outscore one that's still in an uptrend but hasn't
pulled back yet, while a stock below a declining 200-day average is excluded
outright (Uptrend Pullback mode); a clean gap-and-hold should outscore one
that got partially undercut, while a gap that fully faded back below the
band is excluded outright (Gap Up / Upper Band mode); and a down-gap that
stayed open until a later up-gap reclaims it should score well, while a
down-gap already closed by ordinary drift, or one not yet reclaimed, is
excluded outright (Gap Fill Reversal mode).

## Disclaimer

This tool is for research and educational purposes only. Technical analysis
does not predict future price movement with certainty. Nothing here is
investment advice -- do your own due diligence before trading.

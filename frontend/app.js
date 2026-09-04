const API_BASE = "";

const MODES = {
  bottoming: {
    subtitle:
      'Scans US mid &amp; large-cap stocks for technical bases that look ready to turn up &mdash; ' +
      "oversold RSI recovering, MACD curling higher, volatility contracting, accumulation volume, " +
      "and bullish reversal candlesticks near a recent low.",
    metricHeader: "% Off Low",
  },
  pullback: {
    subtitle:
      "Scans US mid &amp; large-cap stocks already in an established uptrend that have pulled back " +
      "to the bottom of their trading range &mdash; often right into a rising 20/50/200-day moving " +
      "average &mdash; on healthy, contracting volume without breaking trend.",
    metricHeader: "Position in Range",
  },
  gap_up: {
    subtitle:
      "Scans US mid &amp; large-cap stocks that gapped up in the last few sessions on above-average " +
      "volume and are still holding near or above the upper daily Bollinger Band &mdash; a bullish " +
      "gap-and-go breakout, as opposed to one that has already faded back and filled the gap.",
    metricHeader: "Gap %",
  },
};

const state = {
  mode: "bottoming",
  results: [],
  sortKey: "score",
  sortDir: -1,
  selectedTicker: null,
};

const el = (id) => document.getElementById(id);

const minScoreInput = el("minScore");
const minScoreValue = el("minScoreValue");
const limitSelect = el("limit");
const periodSelect = el("period");
const scanBtn = el("scanBtn");
const statusEl = el("status");
const resultsBody = el("resultsBody");
const emptyState = el("emptyState");
const detailPanel = el("detailPanel");

minScoreInput.addEventListener("input", () => {
  minScoreValue.textContent = minScoreInput.value;
});

scanBtn.addEventListener("click", runScan);

document.querySelectorAll("#modeToggle .mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.mode === state.mode) return;
    state.mode = btn.dataset.mode;
    document.querySelectorAll("#modeToggle .mode-btn").forEach((b) => b.classList.toggle("active", b === btn));
    el("subtitle").innerHTML = MODES[state.mode].subtitle;
    el("metricHeader").textContent = MODES[state.mode].metricHeader;
    state.results = [];
    state.selectedTicker = null;
    renderTable();
    detailPanel.hidden = true;
    emptyState.hidden = false;
    emptyState.textContent = 'Click "Scan market" to run the scan.';
    statusEl.textContent = "";
  });
});

document.querySelectorAll("#resultsTable thead th[data-key]").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (state.sortKey === key) {
      state.sortDir *= -1;
    } else {
      state.sortKey = key;
      state.sortDir = -1;
    }
    renderTable();
  });
});

function scoreColor(score) {
  if (score >= 70) return "#3fb950";
  if (score >= 55) return "#7ee787";
  if (score >= 40) return "#d29922";
  return "#6e7789";
}

async function runScan() {
  scanBtn.disabled = true;
  statusEl.textContent = "Scanning market (this can take a little while for the full universe)...";
  resultsBody.innerHTML = "";
  emptyState.hidden = true;

  const params = new URLSearchParams({
    min_score: minScoreInput.value,
    limit: limitSelect.value,
    period: periodSelect.value,
    mode: state.mode,
  });

  try {
    const res = await fetch(`${API_BASE}/api/scan?${params.toString()}`);
    if (!res.ok) throw new Error(`Scan failed: ${res.status}`);
    const data = await res.json();
    state.results = data.results;
    statusEl.textContent = `Scanned ${data.scanned}/${data.universe_size} tickers, ${data.results.length} setups shown.`;
    if (data.results.length === 0) {
      emptyState.hidden = false;
      emptyState.textContent = "No setups matched the current filters. Try lowering the min score.";
    }
    renderTable();
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
    emptyState.hidden = false;
    emptyState.textContent = "Scan failed. Is the backend running?";
  } finally {
    scanBtn.disabled = false;
  }
}

function renderTable() {
  const rows = [...state.results].sort((a, b) => {
    const av = a[state.sortKey];
    const bv = b[state.sortKey];
    if (typeof av === "string") return state.sortDir * av.localeCompare(bv);
    return state.sortDir * (av - bv);
  });

  resultsBody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.className = r.ticker === state.selectedTicker ? "selected" : "";
    tr.innerHTML = `
      <td><span class="score-pill" style="background:${scoreColor(r.score)}22;color:${scoreColor(r.score)}">${r.score.toFixed(0)}</span></td>
      <td><strong>${r.ticker}</strong></td>
      <td>${r.verdict}</td>
      <td>$${r.last_close.toFixed(2)}</td>
      <td>${r.metric_value.toFixed(1)}%${r.near_ma ? ` <span class="pattern-tag">${r.near_ma}</span>` : ""}</td>
      <td>${r.rsi14.toFixed(0)}</td>
      <td>${r.patterns.map((p) => `<span class="pattern-tag">${p.name.replace(/_/g, " ")}</span>`).join("")}</td>
    `;
    tr.addEventListener("click", () => selectTicker(r.ticker));
    resultsBody.appendChild(tr);
  }
}

let charts = { main: null, rsi: null, macd: null, series: {} };

function destroyCharts() {
  for (const key of ["main", "rsi", "macd"]) {
    if (charts[key]) {
      charts[key].remove();
      charts[key] = null;
    }
  }
  charts.series = {};
}

async function selectTicker(ticker) {
  state.selectedTicker = ticker;
  renderTable();
  detailPanel.hidden = false;
  el("detailTicker").textContent = ticker;
  el("detailVerdict").textContent = "Loading...";
  el("componentBars").innerHTML = "";
  el("patternList").innerHTML = "";

  const params = new URLSearchParams({ period: periodSelect.value, mode: state.mode });
  const res = await fetch(`${API_BASE}/api/stock/${ticker}?${params.toString()}`);
  if (!res.ok) {
    el("detailVerdict").textContent = "Failed to load";
    return;
  }
  const data = await res.json();
  renderDetail(data);
}

function renderDetail(data) {
  const { result, candles, indicators } = data;

  if (result) {
    el("detailVerdict").textContent = result.verdict + (result.near_ma ? ` · near rising ${result.near_ma}` : "");
    el("detailScore").textContent = result.score.toFixed(0);
    el("detailScore").style.color = scoreColor(result.score);
    renderComponents(result.mode, result.components);
    renderPatterns(result.patterns);
  } else {
    el("detailVerdict").textContent = "Insufficient data";
    el("detailScore").textContent = "";
  }

  destroyCharts();

  const mainChart = LightweightCharts.createChart(el("chartContainer"), chartOptions("chartContainer"));
  const candleSeries = mainChart.addCandlestickSeries({
    upColor: "#3fb950",
    downColor: "#f85149",
    borderVisible: false,
    wickUpColor: "#3fb950",
    wickDownColor: "#f85149",
  });
  candleSeries.setData(candles.map((c) => ({ time: c.date, open: c.open, high: c.high, low: c.low, close: c.close })));

  const sma20 = mainChart.addLineSeries({ color: "#58a6ff", lineWidth: 1 });
  sma20.setData(indicators.filter((i) => i.sma20 != null).map((i) => ({ time: i.date, value: i.sma20 })));
  const sma50 = mainChart.addLineSeries({ color: "#d29922", lineWidth: 1 });
  sma50.setData(indicators.filter((i) => i.sma50 != null).map((i) => ({ time: i.date, value: i.sma50 })));

  mainChart.timeScale().fitContent();
  charts.main = mainChart;

  const rsiChart = LightweightCharts.createChart(el("rsiContainer"), chartOptions("rsiContainer"));
  const rsiSeries = rsiChart.addLineSeries({ color: "#a371f7", lineWidth: 1 });
  rsiSeries.setData(indicators.filter((i) => i.rsi14 != null).map((i) => ({ time: i.date, value: i.rsi14 })));
  rsiChart.timeScale().fitContent();
  charts.rsi = rsiChart;

  const macdChart = LightweightCharts.createChart(el("macdContainer"), chartOptions("macdContainer"));
  const macdSeries = macdChart.addLineSeries({ color: "#58a6ff", lineWidth: 1 });
  macdSeries.setData(indicators.filter((i) => i.macd != null).map((i) => ({ time: i.date, value: i.macd })));
  const signalSeries = macdChart.addLineSeries({ color: "#d29922", lineWidth: 1 });
  signalSeries.setData(indicators.filter((i) => i.signal != null).map((i) => ({ time: i.date, value: i.signal })));
  macdChart.timeScale().fitContent();
  charts.macd = macdChart;

  syncTimeScales([mainChart, rsiChart, macdChart]);
}

function chartOptions(containerId) {
  const container = el(containerId);
  return {
    layout: { background: { color: "#171e2e" }, textColor: "#8a93a8" },
    grid: { vertLines: { color: "#2a3348" }, horzLines: { color: "#2a3348" } },
    rightPriceScale: { borderColor: "#2a3348" },
    timeScale: { borderColor: "#2a3348" },
    width: container.clientWidth,
    height: container.clientHeight,
  };
}

function syncTimeScales(chartList) {
  chartList.forEach((chart) => {
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      chartList.forEach((other) => {
        if (other !== chart) other.timeScale().setVisibleLogicalRange(range);
      });
    });
  });
}

const COMPONENT_INFO = {
  bottoming: {
    downtrend_context: ["Prior downtrend", 8],
    proximity_to_low: ["Near recent low", 12],
    rsi_recovery: ["RSI oversold recovery", 20],
    macd_turn: ["MACD turning up", 15],
    volatility_contraction: ["Volatility contraction", 8],
    volume_accumulation: ["Volume accumulation", 15],
    candlestick_pattern: ["Candlestick reversal", 15],
    higher_low_structure: ["Higher-low structure", 7],
  },
  pullback: {
    uptrend_strength: ["Uptrend strength", 25],
    support_proximity: ["Near range bottom / rising MA", 25],
    pullback_depth: ["Healthy pullback depth", 15],
    rsi_pullback_zone: ["RSI in pullback zone", 15],
    volume_contraction: ["Volume drying up", 10],
    candlestick_pattern: ["Candlestick reversal", 10],
  },
  gap_up: {
    gap_magnitude: ["Gap magnitude", 25],
    upper_band_position: ["At/above upper band", 25],
    volume_confirmation: ["Volume confirmation", 20],
    follow_through: ["Follow-through / gap held", 15],
    trend_context: ["Trend context", 15],
  },
};

function renderComponents(mode, components) {
  const info = COMPONENT_INFO[mode] || COMPONENT_INFO.bottoming;
  const container = el("componentBars");
  container.innerHTML = "";
  for (const [key, value] of Object.entries(components)) {
    const [label, max] = info[key] || [key, 1];
    const pct = Math.max(0, Math.min(100, (value / max) * 100));
    const row = document.createElement("div");
    row.className = "component-row";
    row.innerHTML = `
      <span>${label}</span>
      <div class="component-track"><div class="component-fill" style="width:${pct}%"></div></div>
      <span>${value.toFixed(1)}</span>
    `;
    container.appendChild(row);
  }
}

function renderPatterns(patterns) {
  const list = el("patternList");
  list.innerHTML = "";
  if (patterns.length === 0) {
    list.innerHTML = "<li>No reversal candlestick pattern in the last 5 sessions.</li>";
    return;
  }
  for (const p of patterns) {
    const li = document.createElement("li");
    li.textContent = `${p.date} — ${p.name.replace(/_/g, " ")}${p.near_low ? " (near recent low)" : ""}`;
    list.appendChild(li);
  }
}

window.addEventListener("resize", () => {
  if (charts.main) charts.main.applyOptions({ width: el("chartContainer").clientWidth });
  if (charts.rsi) charts.rsi.applyOptions({ width: el("rsiContainer").clientWidth });
  if (charts.macd) charts.macd.applyOptions({ width: el("macdContainer").clientWidth });
});

const API_BASE = "";

const state = {
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
      <td>${r.pct_off_low.toFixed(1)}%</td>
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

  const params = new URLSearchParams({ period: periodSelect.value });
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
    el("detailVerdict").textContent = result.verdict;
    el("detailScore").textContent = result.score.toFixed(0);
    el("detailScore").style.color = scoreColor(result.score);
    renderComponents(result.components);
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

const COMPONENT_LABELS = {
  downtrend_context: "Prior downtrend",
  proximity_to_low: "Near recent low",
  rsi_recovery: "RSI oversold recovery",
  macd_turn: "MACD turning up",
  volatility_contraction: "Volatility contraction",
  volume_accumulation: "Volume accumulation",
  candlestick_pattern: "Candlestick reversal",
  higher_low_structure: "Higher-low structure",
};

const COMPONENT_MAX = {
  downtrend_context: 8,
  proximity_to_low: 12,
  rsi_recovery: 20,
  macd_turn: 15,
  volatility_contraction: 8,
  volume_accumulation: 15,
  candlestick_pattern: 15,
  higher_low_structure: 7,
};

function renderComponents(components) {
  const container = el("componentBars");
  container.innerHTML = "";
  for (const [key, value] of Object.entries(components)) {
    const max = COMPONENT_MAX[key] || 1;
    const pct = Math.max(0, Math.min(100, (value / max) * 100));
    const row = document.createElement("div");
    row.className = "component-row";
    row.innerHTML = `
      <span>${COMPONENT_LABELS[key] || key}</span>
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

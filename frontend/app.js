const form = document.getElementById("reconcile-form");
const submitBtn = document.getElementById("submit-btn");
const errorBanner = document.getElementById("error-banner");
const resultsSection = document.getElementById("results");
const summaryCards = document.getElementById("summary-cards");
const exportBtn = document.getElementById("export-btn");

let lastResult = null;

function fmtMoney(value) {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.hidden = false;
}

function clearError() {
  errorBanner.hidden = true;
  errorBanner.textContent = "";
}

function renderSummary(summary) {
  const diffGood = Math.abs(summary.difference) < 0.01;
  const cards = [
    { label: "GL total", value: fmtMoney(summary.gl_total) },
    { label: "Bank total", value: fmtMoney(summary.bank_total) },
    {
      label: "Difference",
      value: fmtMoney(summary.difference),
      cls: diffGood ? "good" : "bad",
    },
    { label: "Matched", value: `${summary.matched_count}` },
    { label: "Unmatched GL", value: `${summary.unmatched_gl_count}` },
    { label: "Unmatched Bank", value: `${summary.unmatched_bank_count}` },
  ];
  summaryCards.innerHTML = cards
    .map(
      (c) => `
      <div class="card">
        <div class="label">${c.label}</div>
        <div class="value ${c.cls || ""}">${c.value}</div>
      </div>`
    )
    .join("");
}

function renderMatches(matches) {
  const panel = document.getElementById("tab-matches");
  if (!matches.length) {
    panel.innerHTML = `<div class="empty-state">No matches found.</div>`;
    return;
  }
  panel.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Tier</th><th>GL date</th><th>GL description</th><th class="amount">GL amount</th>
          <th>Bank date</th><th>Bank description</th><th class="amount">Bank amount</th><th>Why</th>
        </tr>
      </thead>
      <tbody>
        ${matches
          .map(
            (m) => `
          <tr>
            <td><span class="badge ${m.tier}">${m.tier}</span></td>
            <td>${m.gl_entry.date ?? ""}</td>
            <td>${m.gl_entry.description}</td>
            <td class="amount">${fmtMoney(m.gl_entry.amount)}</td>
            <td>${m.bank_entry.date ?? ""}</td>
            <td>${m.bank_entry.description}</td>
            <td class="amount">${fmtMoney(m.bank_entry.amount)}</td>
            <td>${m.reason}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

function renderUnmatched(elId, entries) {
  const panel = document.getElementById(elId);
  if (!entries.length) {
    panel.innerHTML = `<div class="empty-state">Nothing unmatched here.</div>`;
    return;
  }
  panel.innerHTML = `
    <table>
      <thead><tr><th>Date</th><th>Description</th><th>Reference</th><th class="amount">Amount</th></tr></thead>
      <tbody>
        ${entries
          .map(
            (e) => `
          <tr>
            <td>${e.date ?? ""}</td>
            <td>${e.description}</td>
            <td>${e.reference}</td>
            <td class="amount">${fmtMoney(e.amount)}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

function renderResult(result) {
  lastResult = result;
  renderSummary(result.summary);
  renderMatches(result.matches);
  renderUnmatched("tab-unmatched-gl", result.unmatched_gl);
  renderUnmatched("tab-unmatched-bank", result.unmatched_bank);
  resultsSection.hidden = false;
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = true));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).hidden = false;
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  submitBtn.disabled = true;
  submitBtn.textContent = "Reconciling...";

  const formData = new FormData();
  formData.append("gl_file", document.getElementById("gl_file").files[0]);
  formData.append("bank_file", document.getElementById("bank_file").files[0]);

  try {
    const res = await fetch("/api/reconcile", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Reconciliation failed.");
    }
    renderResult(data);
  } catch (err) {
    showError(err.message);
    resultsSection.hidden = true;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Reconcile";
  }
});

function toCsv(rows, headers) {
  const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [headers.map(escape).join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => escape(row[h])).join(","));
  }
  return lines.join("\n");
}

exportBtn.addEventListener("click", () => {
  if (!lastResult) return;
  const rows = [
    ...lastResult.matches.map((m) => ({
      status: `matched (${m.tier})`,
      gl_date: m.gl_entry.date,
      gl_description: m.gl_entry.description,
      gl_amount: m.gl_entry.amount,
      bank_date: m.bank_entry.date,
      bank_description: m.bank_entry.description,
      bank_amount: m.bank_entry.amount,
      reason: m.reason,
    })),
    ...lastResult.unmatched_gl.map((e) => ({
      status: "unmatched (GL only)",
      gl_date: e.date,
      gl_description: e.description,
      gl_amount: e.amount,
      bank_date: "",
      bank_description: "",
      bank_amount: "",
      reason: "",
    })),
    ...lastResult.unmatched_bank.map((e) => ({
      status: "unmatched (bank only)",
      gl_date: "",
      gl_description: "",
      gl_amount: "",
      bank_date: e.date,
      bank_description: e.description,
      bank_amount: e.amount,
      reason: "",
    })),
  ];
  const csv = toCsv(rows, [
    "status",
    "gl_date",
    "gl_description",
    "gl_amount",
    "bank_date",
    "bank_description",
    "bank_amount",
    "reason",
  ]);
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "reconciliation_report.csv";
  a.click();
  URL.revokeObjectURL(url);
});

// --- Push to QuickBooks ---

const qboBanner = document.getElementById("qbo-banner");
const qboNotConfigured = document.getElementById("qbo-not-configured");
const qboDisconnected = document.getElementById("qbo-disconnected");
const qboConnected = document.getElementById("qbo-connected");
const qboConnectBtn = document.getElementById("qbo-connect-btn");
const qboDisconnectBtn = document.getElementById("qbo-disconnect-btn");
const qboCompanyName = document.getElementById("qbo-company-name");
const qboEnvironment = document.getElementById("qbo-environment");
const qboPushForm = document.getElementById("qbo-push-form");
const qboPushBtn = document.getElementById("qbo-push-btn");
const qboPushError = document.getElementById("qbo-push-error");
const qboPushResults = document.getElementById("qbo-push-results");
const qboBankAccount = document.getElementById("qbo_bank_account");
const qboIncomeAccount = document.getElementById("qbo_income_account");
const qboExpenseAccount = document.getElementById("qbo_expense_account");

function showQboBanner(message, isError) {
  qboBanner.textContent = message;
  qboBanner.classList.toggle("bad", !!isError);
  qboBanner.hidden = false;
}

function populateAccountSelect(select, accounts) {
  select.innerHTML = accounts
    .map((a) => `<option value="${a.id}">${a.name} (${a.account_type})</option>`)
    .join("");
}

async function loadQboAccounts() {
  const res = await fetch("/api/qbo/accounts");
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Could not load QuickBooks accounts.");
  }
  const accounts = await res.json();
  populateAccountSelect(qboBankAccount, accounts);
  populateAccountSelect(qboIncomeAccount, accounts);
  populateAccountSelect(qboExpenseAccount, accounts);
}

async function refreshQboStatus() {
  const res = await fetch("/api/qbo/status");
  const status = await res.json();

  qboNotConfigured.hidden = status.configured;
  qboDisconnected.hidden = !status.configured || status.connected;
  qboConnected.hidden = !status.connected;

  if (status.connected) {
    qboCompanyName.textContent = status.company_name || "QuickBooks";
    qboEnvironment.textContent = status.environment || "";
    try {
      await loadQboAccounts();
    } catch (err) {
      showQboBanner(err.message, true);
    }
  }
}

qboConnectBtn?.addEventListener("click", () => {
  window.location.href = "/api/qbo/connect";
});

qboDisconnectBtn?.addEventListener("click", async () => {
  await fetch("/api/qbo/disconnect", { method: "POST" });
  qboPushResults.hidden = true;
  await refreshQboStatus();
});

function renderPushResults(summary) {
  const pills = [
    { key: "created", label: "Created" },
    { key: "skipped_duplicate", label: "Already in QuickBooks" },
    { key: "errors", label: "Errors" },
  ];
  const summaryHtml = `
    <div class="push-summary">
      ${pills.map((p) => `<span class="pill ${p.key}">${p.label}: ${summary[p.key]}</span>`).join("")}
    </div>`;

  const rowsHtml = `
    <table>
      <thead><tr><th>Status</th><th>Date</th><th>Description</th><th class="amount">Amount</th><th>Detail</th></tr></thead>
      <tbody>
        ${summary.results
          .map(
            (r) => `
          <tr>
            <td><span class="status-pill ${r.status}">${r.status.replace("_", " ")}</span></td>
            <td>${r.date ?? ""}</td>
            <td>${r.description}</td>
            <td class="amount">${fmtMoney(r.amount)}</td>
            <td>${r.detail || (r.qbo_id ? `${r.qbo_txn_type} #${r.qbo_id}` : "")}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;

  qboPushResults.innerHTML = summaryHtml + rowsHtml;
  qboPushResults.hidden = false;
}

qboPushForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  qboPushError.hidden = true;
  qboPushResults.hidden = true;
  qboPushBtn.disabled = true;
  qboPushBtn.textContent = "Pushing...";

  const formData = new FormData();
  formData.append("spreadsheet", document.getElementById("qbo_spreadsheet").files[0]);
  formData.append("bank_account_id", qboBankAccount.value);
  formData.append("income_account_id", qboIncomeAccount.value);
  formData.append("expense_account_id", qboExpenseAccount.value);

  try {
    const res = await fetch("/api/qbo/push", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Push to QuickBooks failed.");
    }
    renderPushResults(data);
  } catch (err) {
    qboPushError.textContent = err.message;
    qboPushError.hidden = false;
  } finally {
    qboPushBtn.disabled = false;
    qboPushBtn.textContent = "Push to QuickBooks";
  }
});

(function initQbo() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("qbo_connected")) {
    showQboBanner("Connected to QuickBooks.", false);
  } else if (params.get("qbo_error")) {
    showQboBanner(`QuickBooks connection failed: ${params.get("qbo_error")}`, true);
  }
  if (params.has("qbo_connected") || params.has("qbo_error")) {
    params.delete("qbo_connected");
    params.delete("qbo_error");
    const query = params.toString();
    window.history.replaceState({}, "", window.location.pathname + (query ? `?${query}` : ""));
  }

  refreshQboStatus();
})();

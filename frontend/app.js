// --- Shared state: one uploaded transactions file feeds preview, QBO push, and Desktop export ---

let currentFile = null;

function fmtMoney(value) {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function updateActionButtonsState() {
  qboPushBtn.disabled = !currentFile;
  desktopBtn.disabled = !currentFile;
}

// --- Upload + preview ---

const loadForm = document.getElementById("load-form");
const loadBtn = document.getElementById("load-btn");
const errorBanner = document.getElementById("error-banner");
const resultsSection = document.getElementById("results");
const summaryCards = document.getElementById("summary-cards");
const exportBtn = document.getElementById("export-btn");

let lastPreview = null;

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.hidden = false;
}

function clearError() {
  errorBanner.hidden = true;
  errorBanner.textContent = "";
}

function renderSummary(summary) {
  const cards = [
    { label: "Transactions", value: `${summary.entry_count}` },
    { label: "Total", value: fmtMoney(summary.total) },
    { label: "Date range", value: summary.start_date ? `${summary.start_date} - ${summary.end_date}` : "-" },
  ];
  summaryCards.innerHTML = cards
    .map(
      (c) => `
      <div class="card">
        <div class="label">${c.label}</div>
        <div class="value">${c.value}</div>
      </div>`
    )
    .join("");
}

function renderTransactions(entries) {
  const panel = document.getElementById("tab-transactions");
  if (!entries.length) {
    panel.innerHTML = `<div class="empty-state">No transactions found.</div>`;
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

function renderPreview(preview) {
  lastPreview = preview;
  renderSummary(preview.summary);
  renderTransactions(preview.entries);
  resultsSection.hidden = false;
}

loadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  loadBtn.disabled = true;
  loadBtn.textContent = "Loading...";

  const file = document.getElementById("txn_file").files[0];
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/transactions/preview", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Could not read that file.");
    }
    renderPreview(data);
    currentFile = file;
    updateActionButtonsState();
  } catch (err) {
    showError(err.message);
    resultsSection.hidden = true;
    currentFile = null;
    updateActionButtonsState();
  } finally {
    loadBtn.disabled = false;
    loadBtn.textContent = "Load transactions";
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
  if (!lastPreview) return;
  const csv = toCsv(lastPreview.entries, ["date", "description", "reference", "amount"]);
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "transactions.csv";
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

  if (!currentFile) {
    qboPushError.textContent = "Load a transactions file above first.";
    qboPushError.hidden = false;
    return;
  }

  qboPushBtn.disabled = true;
  qboPushBtn.textContent = "Pushing...";

  const formData = new FormData();
  formData.append("spreadsheet", currentFile);
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
    qboPushBtn.disabled = !currentFile;
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

// --- Export for QuickBooks Desktop (.qbo / Web Connect) ---

const desktopForm = document.getElementById("desktop-export-form");
const desktopBtn = document.getElementById("desktop-export-btn");
const desktopError = document.getElementById("desktop-export-error");
const desktopAccountType = document.getElementById("desktop_account_type");
const desktopBankIdField = document.getElementById("desktop-bank-id-field");

function updateDesktopFieldsVisibility() {
  desktopBankIdField.hidden = desktopAccountType.value === "CREDITCARD";
}
desktopAccountType?.addEventListener("change", updateDesktopFieldsVisibility);
updateDesktopFieldsVisibility();

desktopForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  desktopError.hidden = true;

  if (!currentFile) {
    desktopError.textContent = "Load a transactions file above first.";
    desktopError.hidden = false;
    return;
  }

  desktopBtn.disabled = true;
  desktopBtn.textContent = "Generating...";

  const formData = new FormData();
  formData.append("spreadsheet", currentFile);
  formData.append("account_type", desktopAccountType.value);
  formData.append("account_id", document.getElementById("desktop_account_id").value);
  formData.append("bank_id", document.getElementById("desktop_bank_id").value || "0");

  try {
    const res = await fetch("/api/export/qbo-desktop", { method: "POST", body: formData });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Export failed.");
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : "transactions.qbo";

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    desktopError.textContent = err.message;
    desktopError.hidden = false;
  } finally {
    desktopBtn.disabled = !currentFile;
    desktopBtn.textContent = "Download .qbo file";
  }
});

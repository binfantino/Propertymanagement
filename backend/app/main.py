"""FastAPI app: reconciliation API + static frontend for the property
management reconciliation agent."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from quickbooks.objects.account import Account

from .matching import reconcile
from .parsing import LedgerParseError, parse_ledger_spreadsheet
from .qbo import auth as qbo_auth
from .qbo import client as qbo_client_mod
from .qbo.config import QBOSettings
from .qbo.push import push_transactions, summarize
from .qbo.store import TokenStore
from .schemas import ReconciliationResult

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

app = FastAPI(
    title="Property Management Reconciliation Agent",
    description="Reconciles general ledger entries against bank statement transactions.",
    version="0.1.0",
)

_qbo_settings = QBOSettings.from_env()
_qbo_store = TokenStore(_qbo_settings.token_store_path)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/reconcile", response_model=ReconciliationResult)
async def reconcile_files(
    gl_file: UploadFile = File(..., description="General ledger CSV or Excel file"),
    bank_file: UploadFile = File(..., description="Bank statement CSV or Excel file"),
) -> dict:
    gl_bytes = await gl_file.read()
    bank_bytes = await bank_file.read()

    try:
        gl_df = parse_ledger_spreadsheet(gl_bytes, gl_file.filename or "ledger.csv")
        bank_df = parse_ledger_spreadsheet(bank_bytes, bank_file.filename or "bank.csv")
    except LedgerParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return reconcile(gl_df, bank_df)


@app.get("/api/qbo/status")
def qbo_status() -> dict:
    data = _qbo_store.load()
    return {
        "configured": _qbo_settings.is_configured(),
        "connected": data is not None,
        "company_name": data.get("company_name") if data else None,
        "environment": data.get("environment") if data else None,
    }


@app.get("/api/qbo/connect")
def qbo_connect() -> RedirectResponse:
    try:
        url = qbo_auth.get_authorization_url(_qbo_settings)
    except qbo_auth.QBONotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url)


@app.get("/api/qbo/callback")
def qbo_callback(code: str, realmId: str, state: str) -> RedirectResponse:
    try:
        qbo_auth.handle_callback(_qbo_settings, _qbo_store, code=code, realm_id=realmId, state=state)
    except Exception as exc:  # noqa: BLE001 - surface any failure back to the UI
        return RedirectResponse(f"/?qbo_error={quote(str(exc))}")
    return RedirectResponse("/?qbo_connected=1")


@app.post("/api/qbo/disconnect")
def qbo_disconnect() -> dict:
    _qbo_store.clear()
    return {"connected": False}


@app.get("/api/qbo/accounts")
def qbo_accounts() -> list[dict]:
    try:
        client = qbo_client_mod.get_client(_qbo_settings, _qbo_store)
    except qbo_client_mod.QBONotConnectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    accounts = Account.filter(Active=True, qb=client)
    return [
        {"id": a.Id, "name": a.Name, "account_type": a.AccountType, "account_sub_type": a.AccountSubType}
        for a in accounts
    ]


@app.post("/api/qbo/push")
async def qbo_push(
    spreadsheet: UploadFile = File(..., description="Transactions CSV or Excel file"),
    bank_account_id: str = Form(..., description="QBO bank/asset account the money moved through"),
    income_account_id: str = Form(..., description="QBO income account for deposits"),
    expense_account_id: str = Form(..., description="QBO expense account for purchases"),
) -> dict:
    raw = await spreadsheet.read()
    try:
        df = parse_ledger_spreadsheet(raw, spreadsheet.filename or "upload")
    except LedgerParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        client = qbo_client_mod.get_client(_qbo_settings, _qbo_store)
    except qbo_client_mod.QBONotConnectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    results = push_transactions(
        df,
        qb_client=client,
        bank_account_id=bank_account_id,
        income_account_id=income_account_id,
        expense_account_id=expense_account_id,
    )
    return summarize(results)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

"""FastAPI app: reconciliation API + static frontend for the property
management reconciliation agent."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .matching import reconcile
from .parsing import LedgerParseError, parse_ledger_csv
from .schemas import ReconciliationResult

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

app = FastAPI(
    title="Property Management Reconciliation Agent",
    description="Reconciles general ledger entries against bank statement transactions.",
    version="0.1.0",
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/reconcile", response_model=ReconciliationResult)
async def reconcile_files(
    gl_file: UploadFile = File(..., description="General ledger CSV"),
    bank_file: UploadFile = File(..., description="Bank statement CSV"),
) -> dict:
    gl_bytes = await gl_file.read()
    bank_bytes = await bank_file.read()

    try:
        gl_df = parse_ledger_csv(gl_bytes, gl_file.filename or "ledger.csv")
        bank_df = parse_ledger_csv(bank_bytes, bank_file.filename or "bank.csv")
    except LedgerParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return reconcile(gl_df, bank_df)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

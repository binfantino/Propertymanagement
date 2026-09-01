"""CSV ingestion and column normalization for ledger/bank statement files."""
from __future__ import annotations

import io

import pandas as pd

DATE_HEADERS = {"date", "transaction_date", "posted_date", "trans_date", "post_date"}
DESCRIPTION_HEADERS = {"description", "desc", "memo", "payee", "details", "narrative"}
AMOUNT_HEADERS = {"amount", "amt", "net_amount", "value"}
DEBIT_HEADERS = {"debit", "withdrawal", "out", "money_out", "debit_amount"}
CREDIT_HEADERS = {"credit", "deposit", "in", "money_in", "credit_amount"}
REFERENCE_HEADERS = {
    "reference",
    "ref",
    "check_number",
    "check_no",
    "checkno",
    "transaction_id",
    "trans_id",
    "id",
}


class LedgerParseError(ValueError):
    """Raised when an uploaded file cannot be parsed into a usable ledger."""


def _find_column(columns: list[str], candidates: set[str]) -> str | None:
    lookup = {c.strip().lower().replace(" ", "_"): c for c in columns}
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    return None


def _to_clean_string(series: pd.Series) -> pd.Series:
    return series.where(series.notna(), "").astype(str).str.strip()


def _to_amount_series(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(r"[,$]", "", regex=True)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def parse_ledger_csv(raw_bytes: bytes, source_name: str) -> pd.DataFrame:
    """Parse an uploaded CSV into a DataFrame with columns: date, description, reference, amount."""
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:  # pragma: no cover - pandas raises many error types
        raise LedgerParseError(f"Could not read '{source_name}' as CSV: {exc}") from exc

    if df.empty:
        raise LedgerParseError(f"'{source_name}' has no rows.")

    columns = list(df.columns)
    date_col = _find_column(columns, DATE_HEADERS)
    desc_col = _find_column(columns, DESCRIPTION_HEADERS)
    ref_col = _find_column(columns, REFERENCE_HEADERS)
    amount_col = _find_column(columns, AMOUNT_HEADERS)
    debit_col = _find_column(columns, DEBIT_HEADERS)
    credit_col = _find_column(columns, CREDIT_HEADERS)

    if amount_col is None and (debit_col is None and credit_col is None):
        raise LedgerParseError(
            f"'{source_name}' needs an amount column, or separate debit/credit columns. "
            f"Found columns: {columns}"
        )

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT
    out["description"] = _to_clean_string(df[desc_col]) if desc_col else ""
    out["reference"] = _to_clean_string(df[ref_col]) if ref_col else ""

    if amount_col is not None:
        out["amount"] = _to_amount_series(df[amount_col])
    else:
        debit = _to_amount_series(df[debit_col]).fillna(0) if debit_col else 0
        credit = _to_amount_series(df[credit_col]).fillna(0) if credit_col else 0
        out["amount"] = credit - debit.abs()

    out = out.dropna(subset=["amount"]).reset_index(drop=True)
    if out.empty:
        raise LedgerParseError(f"'{source_name}' has no rows with a usable amount.")

    out["row_id"] = out.index
    return out[["row_id", "date", "description", "reference", "amount"]]

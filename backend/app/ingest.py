"""Dispatches an uploaded transactions file to the right parser by extension."""
from __future__ import annotations

import pandas as pd

from .parsing import LedgerParseError, parse_ledger_spreadsheet
from .pdf_statement import PdfStatementParseError, extract_wells_fargo_transactions


class TransactionsParseError(ValueError):
    """Raised when an uploaded file can't be parsed into transactions."""


def parse_transactions_file(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(".pdf"):
        try:
            return extract_wells_fargo_transactions(raw_bytes)
        except PdfStatementParseError as exc:
            raise TransactionsParseError(str(exc)) from exc

    try:
        return parse_ledger_spreadsheet(raw_bytes, filename)
    except LedgerParseError as exc:
        raise TransactionsParseError(str(exc)) from exc

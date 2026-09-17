"""Pydantic models for the transactions API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LedgerEntry(BaseModel):
    row_id: int
    date: Optional[str] = None
    description: Optional[str] = None
    reference: Optional[str] = None
    amount: float


class TransactionsSummary(BaseModel):
    entry_count: int
    total: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class TransactionsPreview(BaseModel):
    summary: TransactionsSummary
    entries: list[LedgerEntry]

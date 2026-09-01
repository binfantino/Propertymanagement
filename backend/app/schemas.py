"""Pydantic models for the reconciliation API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LedgerEntry(BaseModel):
    row_id: int
    date: Optional[str] = None
    description: Optional[str] = None
    reference: Optional[str] = None
    amount: float


class MatchedPair(BaseModel):
    gl_entry: LedgerEntry
    bank_entry: LedgerEntry
    tier: str
    confidence: float
    reason: str


class ReconciliationSummary(BaseModel):
    gl_total: float
    bank_total: float
    difference: float
    gl_entry_count: int
    bank_entry_count: int
    matched_count: int
    unmatched_gl_count: int
    unmatched_bank_count: int
    matched_gl_total: float
    matched_bank_total: float
    unmatched_gl_total: float
    unmatched_bank_total: float


class ReconciliationResult(BaseModel):
    summary: ReconciliationSummary
    matches: list[MatchedPair]
    unmatched_gl: list[LedgerEntry]
    unmatched_bank: list[LedgerEntry]

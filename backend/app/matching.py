"""Reconciliation engine: matches GL entries against bank statement entries.

Matching runs in descending-confidence tiers, greedily consuming candidates so
each ledger row and bank row is used in at most one match (one-to-one for v1):

1. exact       - same amount and same non-empty reference
2. strong      - same amount and dates within DATE_TOLERANCE_DAYS
3. fuzzy       - amount within AMOUNT_TOLERANCE and dates within a wider
                 window, with a similar description (SequenceMatcher ratio)

Anything left over is reported as unmatched on its respective side.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

import pandas as pd

AMOUNT_TOLERANCE = 0.01
DATE_TOLERANCE_DAYS = 3
FUZZY_DATE_WINDOW_DAYS = 7
FUZZY_DESCRIPTION_THRESHOLD = 0.55


@dataclass
class Candidate:
    gl_idx: int
    bank_idx: int
    tier: str
    confidence: float
    reason: str


def _description_similarity(a: str, b: str) -> float:
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _days_apart(a, b) -> float:
    if pd.isna(a) or pd.isna(b):
        return float("inf")
    return abs((a - b).days)


def _build_candidates(gl: pd.DataFrame, bank: pd.DataFrame) -> list[Candidate]:
    candidates: list[Candidate] = []
    for gl_row in gl.itertuples():
        for bank_row in bank.itertuples():
            amount_diff = abs(gl_row.amount - bank_row.amount)
            if amount_diff > AMOUNT_TOLERANCE:
                continue

            gl_ref = (gl_row.reference or "").strip().lower()
            bank_ref = (bank_row.reference or "").strip().lower()
            days = _days_apart(gl_row.date, bank_row.date)

            if gl_ref and bank_ref and gl_ref == bank_ref:
                candidates.append(
                    Candidate(
                        gl_row.row_id, bank_row.row_id, "exact", 1.0,
                        f"Matching reference '{gl_row.reference}' and amount",
                    )
                )
                continue

            if days <= DATE_TOLERANCE_DAYS:
                candidates.append(
                    Candidate(
                        gl_row.row_id, bank_row.row_id, "strong", 0.9,
                        f"Same amount, dates within {DATE_TOLERANCE_DAYS} days",
                    )
                )
                continue

            if days <= FUZZY_DATE_WINDOW_DAYS:
                similarity = _description_similarity(gl_row.description, bank_row.description)
                if similarity >= FUZZY_DESCRIPTION_THRESHOLD:
                    confidence = round(0.5 + 0.3 * similarity, 3)
                    candidates.append(
                        Candidate(
                            gl_row.row_id, bank_row.row_id, "fuzzy", confidence,
                            f"Same amount, similar description ({similarity:.0%} match), "
                            f"dates within {FUZZY_DATE_WINDOW_DAYS} days",
                        )
                    )
    return candidates


def reconcile(gl: pd.DataFrame, bank: pd.DataFrame) -> dict:
    """Reconcile a GL DataFrame against a bank statement DataFrame.

    Both DataFrames must have columns: row_id, date, description, reference, amount
    (as produced by parsing.parse_ledger_spreadsheet). Returns a plain dict matching
    schemas.ReconciliationResult's shape.
    """
    candidates = _build_candidates(gl, bank)
    candidates.sort(key=lambda c: c.confidence, reverse=True)

    gl_by_id = gl.set_index("row_id")
    bank_by_id = bank.set_index("row_id")

    matched_gl_ids: set[int] = set()
    matched_bank_ids: set[int] = set()
    matches = []

    for c in candidates:
        if c.gl_idx in matched_gl_ids or c.bank_idx in matched_bank_ids:
            continue
        matched_gl_ids.add(c.gl_idx)
        matched_bank_ids.add(c.bank_idx)
        matches.append(
            {
                "gl_entry": _entry_dict(gl_by_id.loc[c.gl_idx], c.gl_idx),
                "bank_entry": _entry_dict(bank_by_id.loc[c.bank_idx], c.bank_idx),
                "tier": c.tier,
                "confidence": c.confidence,
                "reason": c.reason,
            }
        )

    unmatched_gl = [
        _entry_dict(row, row_id)
        for row_id, row in gl_by_id.iterrows()
        if row_id not in matched_gl_ids
    ]
    unmatched_bank = [
        _entry_dict(row, row_id)
        for row_id, row in bank_by_id.iterrows()
        if row_id not in matched_bank_ids
    ]

    gl_total = round(float(gl["amount"].sum()), 2)
    bank_total = round(float(bank["amount"].sum()), 2)
    matched_gl_total = round(sum(m["gl_entry"]["amount"] for m in matches), 2)
    matched_bank_total = round(sum(m["bank_entry"]["amount"] for m in matches), 2)
    unmatched_gl_total = round(sum(e["amount"] for e in unmatched_gl), 2)
    unmatched_bank_total = round(sum(e["amount"] for e in unmatched_bank), 2)

    summary = {
        "gl_total": gl_total,
        "bank_total": bank_total,
        "difference": round(gl_total - bank_total, 2),
        "gl_entry_count": len(gl),
        "bank_entry_count": len(bank),
        "matched_count": len(matches),
        "unmatched_gl_count": len(unmatched_gl),
        "unmatched_bank_count": len(unmatched_bank),
        "matched_gl_total": matched_gl_total,
        "matched_bank_total": matched_bank_total,
        "unmatched_gl_total": unmatched_gl_total,
        "unmatched_bank_total": unmatched_bank_total,
    }

    return {
        "summary": summary,
        "matches": matches,
        "unmatched_gl": unmatched_gl,
        "unmatched_bank": unmatched_bank,
    }


def _entry_dict(row: pd.Series, row_id: int) -> dict:
    date = row["date"]
    return {
        "row_id": int(row_id),
        "date": None if pd.isna(date) else date.strftime("%Y-%m-%d"),
        "description": row["description"] or "",
        "reference": row["reference"] or "",
        "amount": round(float(row["amount"]), 2),
    }

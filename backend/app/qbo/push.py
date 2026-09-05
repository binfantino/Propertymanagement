"""Pushes a parsed ledger DataFrame into QuickBooks as Deposit/Purchase
transactions, skipping any row whose dedupe DocNumber already exists."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd
from quickbooks.exceptions import QuickbooksException
from quickbooks.objects.deposit import Deposit
from quickbooks.objects.purchase import Purchase

from .mapping import build_dedupe_doc_number, build_deposit, build_purchase


@dataclass
class PushResult:
    row_id: int
    date: str | None
    description: str
    amount: float
    status: str  # "created" | "skipped_duplicate" | "error"
    detail: str = ""
    qbo_id: str | None = None
    qbo_txn_type: str | None = None


def push_transactions(
    df: pd.DataFrame,
    *,
    qb_client,
    bank_account_id: str,
    income_account_id: str,
    expense_account_id: str,
) -> list[PushResult]:
    results: list[PushResult] = []

    for row in df.itertuples():
        date_str = None if pd.isna(row.date) else row.date.strftime("%Y-%m-%d")
        description = row.description or ""
        amount = round(float(row.amount), 2)
        doc_number = build_dedupe_doc_number(date_str or "", description, amount)
        txn_type = "Deposit" if amount >= 0 else "Purchase"

        try:
            model = Deposit if txn_type == "Deposit" else Purchase
            existing = model.filter(DocNumber=doc_number, qb=qb_client)
        except QuickbooksException as exc:
            results.append(
                PushResult(row.row_id, date_str, description, amount, "error", f"Duplicate check failed: {exc}")
            )
            continue

        if existing:
            results.append(
                PushResult(
                    row.row_id, date_str, description, amount, "skipped_duplicate",
                    "Already pushed to QuickBooks (matching date/description/amount).",
                    qbo_id=str(existing[0].Id), qbo_txn_type=txn_type,
                )
            )
            continue

        try:
            if txn_type == "Deposit":
                obj = build_deposit(
                    date=date_str, description=description, amount=amount,
                    bank_account_id=bank_account_id, income_account_id=income_account_id,
                    doc_number=doc_number,
                )
            else:
                obj = build_purchase(
                    date=date_str, description=description, amount=amount,
                    bank_account_id=bank_account_id, expense_account_id=expense_account_id,
                    doc_number=doc_number,
                )
            obj.save(qb=qb_client)
            results.append(
                PushResult(row.row_id, date_str, description, amount, "created", qbo_id=str(obj.Id), qbo_txn_type=txn_type)
            )
        except QuickbooksException as exc:
            results.append(PushResult(row.row_id, date_str, description, amount, "error", f"Create failed: {exc}"))

    return results


def summarize(results: list[PushResult]) -> dict:
    return {
        "created": sum(1 for r in results if r.status == "created"),
        "skipped_duplicate": sum(1 for r in results if r.status == "skipped_duplicate"),
        "errors": sum(1 for r in results if r.status == "error"),
        "results": [asdict(r) for r in results],
    }

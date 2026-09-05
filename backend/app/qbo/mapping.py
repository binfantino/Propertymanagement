"""Maps a normalized ledger row into QuickBooks Deposit/Purchase objects.

Positive amounts become a Deposit (money in); negative amounts become a
Purchase (money out, PaymentType=Cash - a generic "money left the bank"
record since we only have a bank line, not a real check/card distinction).

Every transaction gets a DocNumber derived from a hash of its date,
description and amount. That's the dedupe key push.py checks against before
creating anything, so re-uploading the same spreadsheet twice is a no-op
instead of creating duplicate transactions in QuickBooks.
"""
from __future__ import annotations

import hashlib

from quickbooks.objects.base import Ref
from quickbooks.objects.deposit import Deposit, DepositLine, DepositLineDetail
from quickbooks.objects.detailline import AccountBasedExpenseLine, AccountBasedExpenseLineDetail
from quickbooks.objects.purchase import Purchase

DOC_NUMBER_MAX_LENGTH = 21


def build_dedupe_doc_number(date: str, description: str, amount: float) -> str:
    key = f"{date}|{description.strip().lower()}|{amount:.2f}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    doc_number = f"R-{digest}"
    return doc_number[:DOC_NUMBER_MAX_LENGTH]


def _account_ref(account_id: str) -> Ref:
    ref = Ref()
    ref.value = account_id
    ref.type = "Account"
    return ref


def build_deposit(
    *, date: str | None, description: str, amount: float, bank_account_id: str,
    income_account_id: str, doc_number: str,
) -> Deposit:
    deposit = Deposit()
    if date:
        deposit.TxnDate = date
    deposit.DocNumber = doc_number
    deposit.PrivateNote = description
    deposit.DepositToAccountRef = _account_ref(bank_account_id)

    line = DepositLine()
    line.Amount = amount
    line.Description = description
    line.DetailType = "DepositLineDetail"
    line.DepositLineDetail = DepositLineDetail()
    line.DepositLineDetail.AccountRef = _account_ref(income_account_id)
    deposit.Line = [line]
    return deposit


def build_purchase(
    *, date: str | None, description: str, amount: float, bank_account_id: str,
    expense_account_id: str, doc_number: str,
) -> Purchase:
    purchase = Purchase()
    if date:
        purchase.TxnDate = date
    purchase.DocNumber = doc_number
    purchase.PrivateNote = description
    purchase.PaymentType = "Cash"
    purchase.AccountRef = _account_ref(bank_account_id)

    line = AccountBasedExpenseLine()
    line.Amount = abs(amount)
    line.Description = description
    line.AccountBasedExpenseLineDetail = AccountBasedExpenseLineDetail()
    line.AccountBasedExpenseLineDetail.AccountRef = _account_ref(expense_account_id)
    purchase.Line = [line]
    return purchase

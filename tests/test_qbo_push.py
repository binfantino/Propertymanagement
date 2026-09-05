"""Tests for the QBO push orchestration, with the QuickBooks SDK's network
calls (Deposit.filter/save, Purchase.filter/save) replaced by fakes so these
run without any real QuickBooks connection or credentials."""
from quickbooks.exceptions import QuickbooksException
from quickbooks.objects.deposit import Deposit
from quickbooks.objects.purchase import Purchase

from backend.app.parsing import parse_ledger_spreadsheet
from backend.app.qbo.push import push_transactions

ACCOUNTS = dict(bank_account_id="35", income_account_id="90", expense_account_id="70")


def _df(csv: bytes):
    return parse_ledger_spreadsheet(csv, "test.csv")


class _FakeExisting:
    def __init__(self, id_):
        self.Id = id_


def test_creates_deposit_for_positive_amount_and_purchase_for_negative(monkeypatch):
    monkeypatch.setattr(Deposit, "filter", classmethod(lambda cls, **kw: []))
    monkeypatch.setattr(Purchase, "filter", classmethod(lambda cls, **kw: []))

    def fake_save(self, qb=None):
        self.Id = "999"
        return self

    monkeypatch.setattr(Deposit, "save", fake_save)
    monkeypatch.setattr(Purchase, "save", fake_save)

    df = _df(
        b"date,description,amount\n"
        b"2026-06-25,Owner deposit,3998.82\n"
        b"2026-06-04,Bill Pay Vendor,-100.00\n"
    )
    results = push_transactions(df, qb_client=None, **ACCOUNTS)

    assert [r.status for r in results] == ["created", "created"]
    assert results[0].qbo_txn_type == "Deposit"
    assert results[0].amount == 3998.82
    assert results[1].qbo_txn_type == "Purchase"
    assert results[1].amount == -100.0
    assert all(r.qbo_id == "999" for r in results)


def test_skips_row_that_already_exists_in_quickbooks(monkeypatch):
    monkeypatch.setattr(Deposit, "filter", classmethod(lambda cls, **kw: [_FakeExisting("55")]))

    def fail_save(self, qb=None):
        raise AssertionError("save() should not be called for a duplicate row")

    monkeypatch.setattr(Deposit, "save", fail_save)

    df = _df(b"date,description,amount\n2026-06-25,Owner deposit,3998.82\n")
    results = push_transactions(df, qb_client=None, **ACCOUNTS)

    assert results[0].status == "skipped_duplicate"
    assert results[0].qbo_id == "55"


def test_records_error_when_create_fails(monkeypatch):
    monkeypatch.setattr(Deposit, "filter", classmethod(lambda cls, **kw: []))

    def raising_save(self, qb=None):
        raise QuickbooksException("boom")

    monkeypatch.setattr(Deposit, "save", raising_save)

    df = _df(b"date,description,amount\n2026-06-25,Owner deposit,3998.82\n")
    results = push_transactions(df, qb_client=None, **ACCOUNTS)

    assert results[0].status == "error"
    assert "boom" in results[0].detail


def test_records_error_when_duplicate_check_fails(monkeypatch):
    def raising_filter(cls, **kw):
        raise QuickbooksException("lookup boom")

    monkeypatch.setattr(Deposit, "filter", classmethod(raising_filter))

    df = _df(b"date,description,amount\n2026-06-25,Owner deposit,3998.82\n")
    results = push_transactions(df, qb_client=None, **ACCOUNTS)

    assert results[0].status == "error"
    assert "lookup boom" in results[0].detail

import pytest

from backend.app.ofx_export import build_qbo_file
from backend.app.parsing import parse_ledger_spreadsheet


def _df(csv: bytes):
    return parse_ledger_spreadsheet(csv, "test.csv")


def test_checking_account_uses_bank_message_set():
    df = _df(b"date,description,amount\n2026-06-04,Bill Pay Vendor,-100.00\n")
    ofx = build_qbo_file(df, account_id="12345", account_type="CHECKING", bank_id="111000025")

    assert "OFXHEADER:100" in ofx
    assert "<BANKMSGSRSV1>" in ofx
    assert "<BANKACCTFROM>" in ofx
    assert "<BANKID>111000025" in ofx
    assert "<ACCTID>12345" in ofx
    assert "<ACCTTYPE>CHECKING" in ofx
    assert "<CCACCTFROM>" not in ofx


def test_credit_card_account_uses_credit_card_message_set_without_bank_id():
    df = _df(b"date,description,amount\n2026-06-04,Office Supplies,-45.00\n")
    ofx = build_qbo_file(df, account_id="98765", account_type="CREDITCARD", bank_id="ignored")

    assert "<CREDITCARDMSGSRSV1>" in ofx
    assert "<CCACCTFROM>" in ofx
    assert "<ACCTID>98765" in ofx
    assert "<BANKACCTFROM>" not in ofx
    assert "<BANKID>" not in ofx


def test_transaction_type_follows_amount_sign():
    df = _df(
        b"date,description,amount\n"
        b"2026-06-04,Bill Pay Vendor,-100.00\n"
        b"2026-06-25,Owner Deposit,3998.82\n"
    )
    ofx = build_qbo_file(df, account_id="12345", account_type="CHECKING")

    assert "<TRNTYPE>DEBIT" in ofx
    assert "<TRNAMT>-100.00" in ofx
    assert "<TRNTYPE>CREDIT" in ofx
    assert "<TRNAMT>3998.82" in ofx


def test_date_range_spans_min_and_max_transaction_dates():
    df = _df(
        b"date,description,amount\n"
        b"2026-06-04,A,-100.00\n"
        b"2026-06-25,B,50.00\n"
    )
    ofx = build_qbo_file(df, account_id="12345", account_type="CHECKING")

    assert "<DTSTART>20260604" in ofx
    assert "<DTEND>20260625" in ofx


def test_duplicate_transactions_get_distinct_fitids():
    df = _df(
        b"date,description,amount\n"
        b"2026-06-04,Late Fee,50.00\n"
        b"2026-06-04,Late Fee,50.00\n"
    )
    ofx = build_qbo_file(df, account_id="12345", account_type="CHECKING")

    fitids = [line.split(">", 1)[1] for line in ofx.splitlines() if line.startswith("<FITID>")]
    assert len(fitids) == 2
    assert len(set(fitids)) == 2


def test_unsafe_characters_in_description_are_stripped():
    df = _df(b"date,description,amount\n2026-06-04,Vendor <Corp> & Co,-10.00\n")
    ofx = build_qbo_file(df, account_id="12345", account_type="CHECKING")

    assert "<" not in ofx.split("<NAME>")[1].splitlines()[0]
    assert "Vendor" in ofx


def test_invalid_account_type_raises():
    df = _df(b"date,description,amount\n2026-06-04,A,-10.00\n")
    with pytest.raises(ValueError):
        build_qbo_file(df, account_id="12345", account_type="MONEY_MARKET")


def test_missing_account_id_raises():
    df = _df(b"date,description,amount\n2026-06-04,A,-10.00\n")
    with pytest.raises(ValueError):
        build_qbo_file(df, account_id="", account_type="CHECKING")


def test_no_dated_rows_raises():
    df = _df(b"date,description,amount\n2026-06-04,A,-10.00\n")
    df = df.assign(date=None)
    with pytest.raises(ValueError):
        build_qbo_file(df, account_id="12345", account_type="CHECKING")

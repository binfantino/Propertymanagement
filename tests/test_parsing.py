import pytest

from backend.app.parsing import LedgerParseError, parse_ledger_csv


def test_parses_standard_amount_column():
    csv = b"date,description,reference,amount\n2026-01-01,Rent,REF1,100.00\n"
    df = parse_ledger_csv(csv, "test.csv")
    assert len(df) == 1
    assert df.iloc[0]["amount"] == 100.0
    assert df.iloc[0]["reference"] == "REF1"


def test_parses_debit_credit_columns():
    csv = b"date,description,debit,credit\n2026-01-01,Deposit,,250.00\n2026-01-02,Withdrawal,40.00,\n"
    df = parse_ledger_csv(csv, "test.csv")
    assert df.iloc[0]["amount"] == 250.0
    assert df.iloc[1]["amount"] == -40.0


def test_handles_parenthesized_negatives_and_currency_symbols():
    csv = b"date,description,amount\n2026-01-01,Fee,\"$(15.00)\"\n"
    df = parse_ledger_csv(csv, "test.csv")
    assert df.iloc[0]["amount"] == -15.0


def test_missing_amount_column_raises():
    csv = b"date,description\n2026-01-01,No amount here\n"
    with pytest.raises(LedgerParseError):
        parse_ledger_csv(csv, "test.csv")


def test_empty_file_raises():
    csv = b"date,description,amount\n"
    with pytest.raises(LedgerParseError):
        parse_ledger_csv(csv, "test.csv")

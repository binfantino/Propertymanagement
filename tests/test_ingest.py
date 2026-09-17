import io

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.app.ingest import TransactionsParseError, parse_transactions_file
from tests.test_pdf_statement import _build_synthetic_statement


def test_csv_filename_uses_spreadsheet_parser():
    csv_bytes = b"date,description,amount\n2026-01-01,Rent,100.00\n"
    df = parse_transactions_file(csv_bytes, "transactions.csv")
    assert len(df) == 1
    assert df.iloc[0]["amount"] == 100.0


def test_pdf_filename_uses_pdf_parser():
    df = parse_transactions_file(_build_synthetic_statement(), "statement.pdf")
    assert len(df) == 4


def test_bad_pdf_raises_transactions_parse_error():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 700, "Not a statement.")
    c.showPage()
    c.save()

    with pytest.raises(TransactionsParseError):
        parse_transactions_file(buf.getvalue(), "not_a_statement.pdf")


def test_bad_csv_raises_transactions_parse_error():
    with pytest.raises(TransactionsParseError):
        parse_transactions_file(b"not,a,valid,ledger\n", "bad.csv")

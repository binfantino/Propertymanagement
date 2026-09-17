"""Tests for the Wells Fargo Business Checking PDF parser.

These build a synthetic PDF with reportlab, reusing the real column x0
positions the parser expects (that's just layout, not sensitive) but with
entirely fabricated names/amounts - no real statement data is used here.
"""
import io

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.app.pdf_statement import PdfStatementParseError, extract_wells_fargo_transactions


def _draw(c, page_height, x, top, text, size=9):
    c.setFont("Helvetica", size)
    c.drawString(x, page_height - top - size, text)


def _build_synthetic_statement(*, credit_total="1,025.00", debit_total="250.00") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    _, page_height = letter

    def draw(x, top, text, size=9):
        _draw(c, page_height, x, top, text, size)

    draw(36, 40, "September 30, 2026 Page 1 of 1")
    draw(36, 249.7, "Transaction history")

    # Header rows (x0 positions match the real statement's column layout).
    draw(123.8, 272.2, "Check")
    draw(404.2, 272.2, "Deposits/")
    draw(458.2, 272.2, "Withdrawals/")
    draw(525.0, 272.2, "Ending")
    draw(549.0, 272.2, "daily")
    draw(63.0, 282.0, "Date")
    draw(117.0, 282.0, "Number")
    draw(150.0, 282.0, "Description")
    draw(413.2, 282.0, "Credits")
    draw(483.0, 282.0, "Debits")
    draw(540.0, 282.0, "balance")

    # Row A: plain debit.
    draw(61.5, 291.7, "9/2")
    draw(150.0, 291.7, "Fake Vendor Payment Test")
    draw(474.0, 291.7, "50.00")
    draw(533.2, 291.7, "9,950.00")

    # Row B: debit with a check number.
    draw(61.5, 309.7, "9/10")
    draw(126.0, 309.7, "2001")
    draw(150.0, 309.7, "Test Check")
    draw(474.0, 309.7, "200.00")
    draw(533.2, 309.7, "9,750.00")

    # Row C: credit with a wrapped description continuation line.
    draw(61.5, 327.7, "9/15")
    draw(150.0, 327.7, "Test Wire Transfer From Someone")
    draw(405.8, 327.7, "1,000.00")
    draw(533.2, 327.7, "10,750.00")
    draw(150.0, 336.7, "Continuation Of Description Line")

    # Row D: plain credit.
    draw(61.5, 354.7, "9/28")
    draw(150.0, 354.7, "Fake Deposit")
    draw(405.8, 354.7, "25.00")
    draw(533.2, 354.7, "10,775.00")

    # Totals line.
    draw(61.5, 372.7, "Totals")
    draw(399.8, 372.7, f"${credit_total}")
    draw(463.5, 372.7, f"${debit_total}")

    c.showPage()
    c.save()
    return buf.getvalue()


def test_extracts_transactions_with_correct_signs_and_dates():
    df = extract_wells_fargo_transactions(_build_synthetic_statement())

    assert len(df) == 4
    assert df.iloc[0]["date"] == pd_timestamp("2026-09-02")
    assert df.iloc[0]["amount"] == -50.0
    assert df.iloc[1]["reference"] == "2001"
    assert df.iloc[1]["amount"] == -200.0
    assert df.iloc[2]["amount"] == 1000.0
    assert "Continuation Of Description Line" in df.iloc[2]["description"]
    assert df.iloc[3]["amount"] == 25.0


def test_total_amount_matches_declared_totals():
    df = extract_wells_fargo_transactions(_build_synthetic_statement())
    assert round(df["amount"].sum(), 2) == round(1025.00 - 250.00, 2)


def test_mismatched_totals_raise_instead_of_returning_bad_data():
    bad_pdf = _build_synthetic_statement(credit_total="9,999.00", debit_total="250.00")
    with pytest.raises(PdfStatementParseError):
        extract_wells_fargo_transactions(bad_pdf)


def test_non_statement_pdf_raises():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 700, "This is not a bank statement.")
    c.showPage()
    c.save()

    with pytest.raises(PdfStatementParseError):
        extract_wells_fargo_transactions(buf.getvalue())


def pd_timestamp(value):
    import pandas as pd

    return pd.Timestamp(value)

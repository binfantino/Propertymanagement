"""Extracts the transaction table from a Wells Fargo Business Checking
statement PDF.

This is intentionally scoped to that one layout ("Transaction history":
Date / Check Number / Description / Deposits-Credits / Withdrawals-Debits /
Ending daily balance) rather than claiming to parse "any bank PDF" - bank
statement layouts vary too much for a generic parser to be reliable, and
misreading a debit as a credit (or vice versa) would corrupt real accounting
data. Column boundaries below are the x0 pixel ranges of each column's
header word on the page, read directly off a real statement.

As a safety net, the parsed credit/debit totals are checked against the
statement's own printed "Totals" line - if they don't match, parsing is
considered unreliable and raises rather than returning silently-wrong data.
"""
from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd
import pdfplumber

# Column x0 ranges, from the "Transaction history" header row's word
# positions on a Wells Fargo Business Checking statement.
_CHECK_NUMBER_X = (110, 149)
_CREDIT_X = (390, 460)
_DEBIT_X = (460, 525)

_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")
_MONEY_RE = re.compile(r"^-?\$?[\d,]+\.\d{2}$")
_STATEMENT_DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})")
_MONTHS = {
    name: i
    for i, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
_AMOUNT_TOLERANCE = 0.01


class PdfStatementParseError(ValueError):
    """Raised when a PDF doesn't look like a supported statement layout,
    or its printed totals don't match what was parsed."""


def _money_to_float(text: str) -> float:
    return float(text.replace("$", "").replace(",", ""))


def _find_statement_end_date(pdf: pdfplumber.PDF) -> date:
    for page in pdf.pages[:2]:
        text = page.extract_text() or ""
        match = _STATEMENT_DATE_RE.search(text)
        if match:
            month_name, day, year = match.groups()
            month = _MONTHS.get(month_name)
            if month:
                return date(int(year), month, int(day))
    raise PdfStatementParseError(
        "Could not find a statement date on this PDF - is it a Wells Fargo "
        "Business Checking statement?"
    )


def _resolve_year(month: int, statement_end: date) -> int:
    # A statement can span a year boundary (e.g. a Dec 20 - Jan 19 cycle);
    # a transaction month later than the statement's end month must be from
    # the prior year.
    return statement_end.year - 1 if month > statement_end.month else statement_end.year


def _classify_line_words(current: dict, words: list[dict]) -> None:
    for w in words:
        text, x0 = w["text"], w["x0"]
        if _CHECK_NUMBER_X[0] <= x0 < _CHECK_NUMBER_X[1] and text.isdigit():
            current["reference"] = text
        elif _MONEY_RE.match(text):
            amount = _money_to_float(text)
            if _CREDIT_X[0] <= x0 < _CREDIT_X[1]:
                current["credit"] = amount
            elif _DEBIT_X[0] <= x0 < _DEBIT_X[1]:
                current["debit"] = amount
            # else: falls in the "Ending daily balance" column - not needed.
        elif x0 >= _CREDIT_X[0]:
            continue  # unrecognized token in the numeric area - drop it
        else:
            current["description_parts"].append(text)


def _extract_page(page) -> tuple[list[dict], tuple[float, float] | None]:
    """Returns (transaction rows, declared (credit_total, debit_total))
    for one page, or ([], None) if this page has no transaction table."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return [], None

    lines: dict[int, list[dict]] = {}
    for w in words:
        lines.setdefault(round(w["top"]), []).append(w)

    header_found = False
    rows: list[dict] = []
    current: dict | None = None
    declared_totals: tuple[float, float] | None = None

    for top in sorted(lines):
        line_words = sorted(lines[top], key=lambda w: w["x0"])
        line_text = " ".join(w["text"] for w in line_words)

        if not header_found:
            if line_words[0]["text"] == "Date" and "Description" in line_text:
                header_found = True
            continue

        first_word = line_words[0]["text"]

        if first_word == "Totals":
            if current:
                rows.append(current)
                current = None
            totals_row = {"credit": None, "debit": None, "description_parts": [], "reference": ""}
            _classify_line_words(totals_row, line_words[1:])
            declared_totals = (totals_row["credit"] or 0.0, totals_row["debit"] or 0.0)
            break

        date_match = _DATE_RE.match(first_word)
        if date_match:
            if current:
                rows.append(current)
            current = {
                "month": int(date_match.group(1)),
                "day": int(date_match.group(2)),
                "reference": "",
                "description_parts": [],
                "credit": None,
                "debit": None,
            }
            _classify_line_words(current, line_words[1:])
        elif current is not None:
            _classify_line_words(current, line_words)

    if current:
        rows.append(current)

    return (rows, declared_totals) if header_found else ([], None)


def extract_wells_fargo_transactions(raw_bytes: bytes) -> pd.DataFrame:
    """Parses a Wells Fargo Business Checking statement PDF into a DataFrame
    with columns: row_id, date, description, reference, amount (matching
    parsing.parse_ledger_spreadsheet's output, so it plugs into the same
    preview/push/export flows)."""
    try:
        pdf = pdfplumber.open(io.BytesIO(raw_bytes))
    except Exception as exc:  # pragma: no cover - pdfplumber raises many error types
        raise PdfStatementParseError(f"Could not read this file as a PDF: {exc}") from exc

    with pdf:
        statement_end = _find_statement_end_date(pdf)

        all_rows: list[dict] = []
        all_declared_totals: list[tuple[float, float]] = []
        for page in pdf.pages:
            rows, declared_totals = _extract_page(page)
            all_rows.extend(rows)
            if declared_totals:
                all_declared_totals.append(declared_totals)

    if not all_rows:
        raise PdfStatementParseError(
            "Could not find a 'Transaction history' table in this PDF - this parser "
            "currently only supports Wells Fargo Business Checking statements."
        )

    entries = []
    for i, row in enumerate(all_rows):
        year = _resolve_year(row["month"], statement_end)
        txn_date = pd.Timestamp(year=year, month=row["month"], day=row["day"])
        credit = row["credit"] or 0.0
        debit = row["debit"] or 0.0
        description = " ".join(part for part in row["description_parts"] if part).strip()
        entries.append(
            {
                "row_id": i,
                "date": txn_date,
                "description": description,
                "reference": row["reference"],
                "amount": round(credit - debit, 2),
            }
        )

    df = pd.DataFrame(entries, columns=["row_id", "date", "description", "reference", "amount"])

    if all_declared_totals:
        declared_credit = round(sum(t[0] for t in all_declared_totals), 2)
        declared_debit = round(sum(t[1] for t in all_declared_totals), 2)
        parsed_credit = round(sum(e["amount"] for e in entries if e["amount"] > 0), 2)
        parsed_debit = round(-sum(e["amount"] for e in entries if e["amount"] < 0), 2)
        if (
            abs(declared_credit - parsed_credit) > _AMOUNT_TOLERANCE
            or abs(declared_debit - parsed_debit) > _AMOUNT_TOLERANCE
        ):
            raise PdfStatementParseError(
                "Parsed transactions don't match this statement's printed totals "
                f"(statement says credits ${declared_credit:,.2f} / debits ${declared_debit:,.2f}, "
                f"parsed credits ${parsed_credit:,.2f} / debits ${parsed_debit:,.2f}). "
                "Refusing to return possibly-incorrect data - this PDF's layout may "
                "differ from what this parser expects."
            )

    return df

"""Exports a parsed ledger DataFrame as a QuickBooks Web Connect (.qbo) file.

QuickBooks Desktop doesn't have a public REST API the way QuickBooks Online
does - it imports bank transactions from a "Web Connect" file instead
(File > Utilities > Import > Web Connect Files). That file is OFX 1.02 SGML
(leaf elements aren't closed, unlike XML), a format QuickBooks Desktop has
supported unchanged for decades, so this works the same on QuickBooks
Desktop 2015 as any newer version.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd

from .qbo.mapping import build_dedupe_doc_number

ALLOWED_ACCOUNT_TYPES = {"CHECKING", "SAVINGS", "CREDITCARD"}

# OFX SGML has no escaping mechanism for these characters inside a value -
# an embedded "<" in particular would look like the start of a new tag to a
# parser expecting unclosed leaf elements, so they're stripped rather than
# escaped.
_UNSAFE_CHARS = re.compile(r"[<>&\r\n\t]")


def _sanitize(value: str, max_length: int | None = None) -> str:
    cleaned = _UNSAFE_CHARS.sub(" ", value or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def _fmt_date(value: pd.Timestamp) -> str:
    return value.strftime("%Y%m%d")


def build_qbo_file(
    df: pd.DataFrame,
    *,
    account_id: str,
    account_type: str,
    bank_id: str = "0",
) -> str:
    """Build an OFX 1.02 SGML "Web Connect" document for the given transactions.

    df must have columns: row_id, date, description, reference, amount (as
    produced by parsing.parse_ledger_spreadsheet). Raises ValueError for bad
    inputs (empty file, no dated rows, bad account_type).
    """
    account_type = (account_type or "").upper()
    if account_type not in ALLOWED_ACCOUNT_TYPES:
        raise ValueError(f"account_type must be one of {sorted(ALLOWED_ACCOUNT_TYPES)}")
    if not account_id or not account_id.strip():
        raise ValueError("account_id is required.")

    dated = df.dropna(subset=["date"])
    if dated.empty:
        raise ValueError("None of the transactions have a usable date.")

    dtstart = _fmt_date(dated["date"].min())
    dtend = _fmt_date(dated["date"].max())
    dtserver = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    seen_fitids: dict[str, int] = {}
    transaction_blocks = []
    for row in dated.itertuples():
        amount = round(float(row.amount), 2)
        date_str = _fmt_date(row.date)
        description = row.description or "Transaction"

        base_fitid = build_dedupe_doc_number(date_str, description, amount)
        seen_fitids[base_fitid] = seen_fitids.get(base_fitid, 0) + 1
        occurrence = seen_fitids[base_fitid]
        fitid = base_fitid if occurrence == 1 else f"{base_fitid}-{occurrence}"

        trntype = "CREDIT" if amount >= 0 else "DEBIT"
        transaction_blocks.append(
            "\r\n".join(
                [
                    "<STMTTRN>",
                    f"<TRNTYPE>{trntype}",
                    f"<DTPOSTED>{date_str}",
                    f"<TRNAMT>{amount:.2f}",
                    f"<FITID>{fitid}",
                    f"<NAME>{_sanitize(description, 32)}",
                    f"<MEMO>{_sanitize(description, 255)}",
                    "</STMTTRN>",
                ]
            )
        )

    if account_type == "CREDITCARD":
        acct_block = "\r\n".join(
            ["<CCACCTFROM>", f"<ACCTID>{_sanitize(account_id, 40)}", "</CCACCTFROM>"]
        )
        outer_tag, inner_tag, stmtrs_tag = "CREDITCARDMSGSRSV1", "CCSTMTTRNRS", "CCSTMTRS"
    else:
        acct_block = "\r\n".join(
            [
                "<BANKACCTFROM>",
                f"<BANKID>{_sanitize(bank_id, 20) or '0'}",
                f"<ACCTID>{_sanitize(account_id, 40)}",
                f"<ACCTTYPE>{account_type}",
                "</BANKACCTFROM>",
            ]
        )
        outer_tag, inner_tag, stmtrs_tag = "BANKMSGSRSV1", "STMTTRNRS", "STMTRS"

    total = round(float(dated["amount"].sum()), 2)

    lines = [
        "OFXHEADER:100",
        "DATA:OFXSGML",
        "VERSION:102",
        "SECURITY:NONE",
        "ENCODING:USASCII",
        "CHARSET:1252",
        "COMPRESSION:NONE",
        "OLDFILEUID:NONE",
        "NEWFILEUID:NONE",
        "",
        "<OFX>",
        "<SIGNONMSGSRSV1>",
        "<SONRS>",
        "<STATUS>",
        "<CODE>0",
        "<SEVERITY>INFO",
        "</STATUS>",
        f"<DTSERVER>{dtserver}",
        "<LANGUAGE>ENG",
        "</SONRS>",
        "</SIGNONMSGSRSV1>",
        f"<{outer_tag}>",
        f"<{inner_tag}>",
        "<TRNUID>1",
        "<STATUS>",
        "<CODE>0",
        "<SEVERITY>INFO",
        "</STATUS>",
        f"<{stmtrs_tag}>",
        "<CURDEF>USD",
        acct_block,
        "<BANKTRANLIST>",
        f"<DTSTART>{dtstart}",
        f"<DTEND>{dtend}",
        *transaction_blocks,
        "</BANKTRANLIST>",
        "<LEDGERBAL>",
        f"<BALAMT>{total:.2f}",
        f"<DTASOF>{dtend}",
        "</LEDGERBAL>",
        f"</{stmtrs_tag}>",
        f"</{inner_tag}>",
        f"</{outer_tag}>",
        "</OFX>",
    ]
    return "\r\n".join(lines)

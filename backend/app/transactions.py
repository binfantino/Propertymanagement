"""Turns a parsed ledger DataFrame (see parsing.py) into API-friendly entries."""
from __future__ import annotations

import pandas as pd


def to_entries(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "row_id": int(row.row_id),
            "date": None if pd.isna(row.date) else row.date.strftime("%Y-%m-%d"),
            "description": row.description or "",
            "reference": row.reference or "",
            "amount": round(float(row.amount), 2),
        }
        for row in df.itertuples()
    ]


def summarize(df: pd.DataFrame) -> dict:
    dated = df.dropna(subset=["date"])
    return {
        "entry_count": len(df),
        "total": round(float(df["amount"].sum()), 2),
        "start_date": dated["date"].min().strftime("%Y-%m-%d") if not dated.empty else None,
        "end_date": dated["date"].max().strftime("%Y-%m-%d") if not dated.empty else None,
    }

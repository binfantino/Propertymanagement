# Property Management Reconciliation Agent

A small web app that reconciles a property management **general ledger**
against a **bank statement**, so book-keeping staff don't have to eyeball two
spreadsheets line by line every month.

Upload two CSVs, get back:
- Matched transactions, grouped by confidence tier (`exact`, `strong`, `fuzzy`)
- Unmatched GL entries and unmatched bank entries, so you know exactly what
  still needs investigation
- Summary totals and the outstanding difference between the two ledgers
- A CSV export of the full reconciliation report

## How matching works

For each GL row the engine looks for a bank row with the same amount
(within $0.01), then picks the best match in this order:

1. **exact** — same amount and the same reference/check number
2. **strong** — same amount, dates within 3 days
3. **fuzzy** — same amount, dates within 7 days, and a similar description
   (string-similarity match, e.g. `"Rent - Unit 305 - T. Brooks"` vs.
   `"ACH DEPOSIT RENT 305 BROOKS"`)

Matches are assigned greedily by confidence so a row is never matched twice.
See `backend/app/matching.py` for the implementation.

## CSV format

Any of these header names are auto-detected (case-insensitive):

| Field | Accepted headers |
|---|---|
| Date | `date`, `transaction_date`, `posted_date`, `trans_date` |
| Description | `description`, `desc`, `memo`, `payee`, `details` |
| Reference | `reference`, `ref`, `check_number`, `transaction_id`, `id` |
| Amount | `amount`, `amt` — **or** separate `debit`/`credit` columns |

Amounts should be signed (positive = money in, negative = money out).
Currency symbols, commas, and parenthesized negatives (`$(15.00)`) are
handled automatically.

Sample files are in `sample_data/` if you want to try it out immediately.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn backend.app.main:app --reload
```

Then open http://127.0.0.1:8000 and upload `sample_data/general_ledger.csv`
and `sample_data/bank_statement.csv`.

## API

`POST /api/reconcile` — multipart form with `gl_file` and `bank_file` CSV
uploads, returns a JSON `ReconciliationResult` (see `backend/app/schemas.py`).

## Tests

```bash
pytest
```

## Roadmap / not yet implemented

- Persistence (reconciliations are currently stateless, per-request)
- One-to-many matching (e.g. a single bank deposit covering multiple rent
  payments)
- Per-property / per-unit filtering and multi-property batch reconciliation
- Vendor invoice and rent-roll reconciliation modes, reusing the same engine

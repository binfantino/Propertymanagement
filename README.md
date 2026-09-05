# Property Management Reconciliation Agent

A small web app that reconciles a property management **general ledger**
against a **bank statement**, so book-keeping staff don't have to eyeball two
spreadsheets line by line every month.

Upload two CSV or Excel files, get back:
- Matched transactions, grouped by confidence tier (`exact`, `strong`, `fuzzy`)
- Unmatched GL entries and unmatched bank entries, so you know exactly what
  still needs investigation
- Summary totals and the outstanding difference between the two ledgers
- A CSV export of the full reconciliation report

It can also **push a transactions spreadsheet straight into QuickBooks Online**
as Deposits/Purchases, so you don't have to hand-enter what you just reconciled
- see [Push to QuickBooks](#push-to-quickbooks) below.

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

## File format

CSV (`.csv`) or Excel (`.xlsx`, `.xls`) are both accepted. Any of these header
names are auto-detected (case-insensitive):

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

`POST /api/reconcile` — multipart form with `gl_file` and `bank_file` uploads
(CSV or Excel), returns a JSON `ReconciliationResult` (see `backend/app/schemas.py`).

## Push to QuickBooks

Takes a transactions spreadsheet (the same CSV/Excel format as above) and
creates matching **Deposit** (positive amounts) or **Purchase** (negative
amounts) transactions directly in QuickBooks Online, via the official QBO
API. Re-uploading the same file is safe: every transaction gets a dedupe key
derived from its date/description/amount, so already-pushed rows are
skipped instead of duplicated.

**What this does not do:** it doesn't touch QuickBooks' own "Reconcile"
screen (matching transactions against a bank statement's ending balance) -
that's an internal feature of the QBO UI with no public API. This tool gets
your transactions *into* QuickBooks; the final reconcile-and-lock step still
happens by hand in QBO, same as it would for anything else already in your
books.

### One-time setup: create an Intuit Developer app

1. Sign up / log in at https://developer.intuit.com and create a new app
   (choose "QuickBooks Online and Payments").
2. In the app's **Keys & OAuth** page, grab the **Client ID** and
   **Client Secret** for the **Sandbox** environment (use a sandbox company
   first - don't point this at production books until you trust it).
3. Under **Redirect URIs**, add `http://localhost:8000/api/qbo/callback`
   (or wherever you're running this app).
4. Set these environment variables before starting the server:

   ```bash
   export QBO_CLIENT_ID="your-client-id"
   export QBO_CLIENT_SECRET="your-client-secret"
   export QBO_REDIRECT_URI="http://localhost:8000/api/qbo/callback"
   export QBO_ENVIRONMENT="sandbox"   # switch to "production" when you're ready
   ```

5. Start the app (`uvicorn backend.app.main:app --reload`), open
   http://127.0.0.1:8000, and click **Connect to QuickBooks** in the "Push to
   QuickBooks" panel. You'll be sent to Intuit's login/consent screen, then
   redirected back once connected.

Tokens are stored locally in `.qbo_tokens.json` (gitignored) - this app is
built for one person/company at a time, not multi-tenant use.

### Using it

1. Once connected, pick the **bank account** (where the money moves through),
   an **income account** (used for all Deposits), and an **expense account**
   (used for all Purchases) from your QuickBooks chart of accounts.
2. Upload a transactions file and click **Push to QuickBooks**.
3. You'll get a per-row result: created, already in QuickBooks (skipped), or
   error, plus the QuickBooks transaction ID for anything created.

This is intentionally simple for v1: every deposit goes to one income
account and every purchase to one expense account, rather than
per-row categorization - see Roadmap below.

## Tests

```bash
pytest
```

Note: the QuickBooks push logic is tested against fakes/mocks of the
`python-quickbooks` SDK objects (see `tests/test_qbo_push.py`), not a live
QuickBooks connection - there's no sandbox company wired into CI.

## Roadmap / not yet implemented

- Persistence for reconciliation results (reconciliation itself is stateless,
  per-request)
- One-to-many matching (e.g. a single bank deposit covering multiple rent
  payments)
- Per-property / per-unit filtering and multi-property batch reconciliation
- Vendor invoice and rent-roll reconciliation modes, reusing the same engine
- Per-row QuickBooks account/category selection (a "category" column in the
  spreadsheet mapped to QBO accounts by name), instead of one default income
  and one default expense account for the whole push
- Multi-company QuickBooks support (current token storage is single-company)

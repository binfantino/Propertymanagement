# Property Management QuickBooks Agent

A small web app that takes a property management bank statement (CSV,
Excel, or a Wells Fargo Business Checking PDF statement) and gets it into
QuickBooks, so book-keeping staff don't have to hand-enter every
transaction:

- **QuickBooks Online**: push straight in as Deposits/Purchases via the API -
  see [Push to QuickBooks](#push-to-quickbooks) below.
- **QuickBooks Desktop**: download a Web Connect (`.qbo`) file to import by
  hand - see [Export for QuickBooks Desktop](#export-for-quickbooks-desktop)
  below.

You upload the file once; both QuickBooks actions reuse it, so there's no
re-picking the same file per action.

## File format

### CSV / Excel

`.csv`, `.xlsx`, and `.xls` are accepted. Any of these header names are
auto-detected (case-insensitive):

| Field | Accepted headers |
|---|---|
| Date | `date`, `transaction_date`, `posted_date`, `trans_date` |
| Description | `description`, `desc`, `memo`, `payee`, `details` |
| Reference | `reference`, `ref`, `check_number`, `transaction_id`, `id` |
| Amount | `amount`, `amt` — **or** separate `debit`/`credit` columns |

Amounts should be signed (positive = money in, negative = money out).
Currency symbols, commas, and parenthesized negatives (`$(15.00)`) are
handled automatically.

A sample file is in `sample_data/bank_statement.csv` if you want to try it
out immediately.

### PDF

`.pdf` is accepted too, but scoped narrowly: it currently only understands
**Wells Fargo Business Checking** statements' "Transaction history" table
(Date / Check Number / Description / Deposits-Credits / Withdrawals-Debits /
Ending daily balance). PDF layouts vary enormously between banks, and a
generic "any bank PDF" parser would risk silently misreading a debit as a
credit - not something to guess at with real accounting data. See
`backend/app/pdf_statement.py` for the implementation and its column-position
approach, and the Roadmap below for extending it to other banks/formats.

As a safety check, the parser sums what it extracted and compares that
against the statement's own printed "Totals" line; if they don't match, it
refuses to return data rather than risk returning something silently wrong.
It also can't read scanned/image-only PDFs (no OCR) - only ones with
selectable text, which is how Wells Fargo's own statements are generated.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn backend.app.main:app --reload
```

Then open http://127.0.0.1:8000, upload `sample_data/bank_statement.csv`,
and click **Load transactions** to see it previewed before pushing/exporting.

## API

`POST /api/transactions/preview` — multipart form with a `file` upload (CSV,
Excel, or PDF), returns a JSON `TransactionsPreview` (see
`backend/app/schemas.py`) with a summary and the parsed entries.

## Push to QuickBooks

Takes the loaded transactions and creates matching **Deposit** (positive
amounts) or **Purchase** (negative amounts) transactions directly in
QuickBooks Online, via the official QBO API. Re-uploading the same file is
safe: every transaction gets a dedupe key derived from its
date/description/amount, so already-pushed rows are skipped instead of
duplicated.

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

1. Upload a transactions file above and click **Load transactions**.
2. Once connected to QuickBooks, pick the **bank account** (where the money
   moves through), an **income account** (used for all Deposits), and an
   **expense account** (used for all Purchases) from your QuickBooks chart
   of accounts.
3. Click **Push to QuickBooks**.
4. You'll get a per-row result: created, already in QuickBooks (skipped), or
   error, plus the QuickBooks transaction ID for anything created.

This is intentionally simple for v1: every deposit goes to one income
account and every purchase to one expense account, rather than
per-row categorization - see Roadmap below.

## Export for QuickBooks Desktop

QuickBooks Desktop (Pro, Premier, etc.) doesn't have a public REST API like
QuickBooks Online does, so there's no "connect" flow for it here - instead,
`POST /api/export/qbo-desktop` (or the "Export for QuickBooks Desktop" panel
in the UI) turns the loaded transactions into a **Web Connect (`.qbo`) file**,
the same OFX-based format banks have used for "download to QuickBooks" for
decades. It works identically on QuickBooks Desktop 2015 through the newest
release, since that file format hasn't changed.

1. Upload a transactions file above and click **Load transactions**.
2. Pick the account type (Checking, Savings, or Credit Card) and enter the
   account number as it's set up in QuickBooks (and routing number, for
   Checking/Savings).
3. Click **Download .qbo file**, then in QuickBooks Desktop go to
   **File → Utilities → Import → Web Connect Files** and select it.

QuickBooks will bring the transactions into its Online Banking Center as
unmatched items you Match/Add from there - same as connecting a bank feed
live, just via a file instead of a direct connection. Every transaction gets
a `FITID` derived from a hash of its date/description/amount (the same
dedupe key the QuickBooks Online push uses), so re-importing the same file
won't create duplicates within that account.

## Tests

```bash
pytest
```

Note: the QuickBooks Online push logic is tested against fakes/mocks of the
`python-quickbooks` SDK objects (see `tests/test_qbo_push.py`), not a live
QuickBooks connection - there's no sandbox company wired into CI. The
QuickBooks Desktop export (`tests/test_ofx_export.py`,
`tests/test_main_export_endpoint.py`) and the transactions preview
(`tests/test_main_preview_endpoint.py`) need no external service, so those
run for real, including through the actual FastAPI endpoints. The PDF parser
(`tests/test_pdf_statement.py`, `tests/test_ingest.py`) is tested against a
synthetic statement PDF generated with `reportlab` at test time - real bank
statement data is never checked into this repo.

## Roadmap / not yet implemented

- PDF support for other banks - `backend/app/pdf_statement.py`'s column
  positions are specific to Wells Fargo Business Checking; another bank
  would need its own column-position map (or a more general table-detection
  approach) and its own totals-line format to validate against
- OCR for scanned/image-only statement PDFs (current PDF support needs
  selectable text)
- Per-row QuickBooks account/category selection (a "category" column in the
  spreadsheet mapped to QBO accounts by name), instead of one default income
  and one default expense account for the whole push
- Multi-company QuickBooks support (current token storage is single-company)
- IIF export for QuickBooks Desktop, as an alternative to Web Connect that
  can post fully-categorized transactions directly instead of leaving them
  as unmatched bank-feed items
- Matching a transactions file against a separate general ledger/rent-roll
  export (the original two-file "reconcile" flow) - dropped in favor of a
  single-file upload since QuickBooks itself is the ledger for most users of
  this tool; the matching engine can be resurrected from git history
  (`backend/app/matching.py` as of the commit that removed it) if needed

from backend.app.parsing import parse_ledger_csv
from backend.app.matching import reconcile


def _df(csv: bytes):
    return parse_ledger_csv(csv, "test.csv")


def test_exact_reference_match():
    gl = _df(b"date,description,reference,amount\n2026-01-01,Rent 101,RENT-101,1000.00\n")
    bank = _df(b"date,description,reference,amount\n2026-01-03,ACH RENT,RENT-101,1000.00\n")
    result = reconcile(gl, bank)
    assert result["summary"]["matched_count"] == 1
    assert result["matches"][0]["tier"] == "exact"
    assert not result["unmatched_gl"]
    assert not result["unmatched_bank"]


def test_strong_match_same_amount_close_date_no_reference():
    gl = _df(b"date,description,amount\n2026-01-01,Landscaping,-320.00\n")
    bank = _df(b"date,description,amount\n2026-01-02,CHECK 5521,-320.00\n")
    result = reconcile(gl, bank)
    assert result["summary"]["matched_count"] == 1
    assert result["matches"][0]["tier"] == "strong"


def test_fuzzy_match_similar_description_wider_date_window():
    gl = _df(b"date,description,amount\n2026-01-01,Rent - Unit 305 - T. Brooks,275.00\n")
    bank = _df(b"date,description,amount\n2026-01-06,ACH DEPOSIT RENT 305 BROOKS,275.00\n")
    result = reconcile(gl, bank)
    assert result["summary"]["matched_count"] == 1
    assert result["matches"][0]["tier"] == "fuzzy"


def test_unmatched_entries_reported_on_each_side():
    gl = _df(b"date,description,amount\n2026-01-01,Rent,500.00\n2026-01-02,Fee,25.00\n")
    bank = _df(b"date,description,amount\n2026-01-01,ACH Rent,500.00\n2026-01-10,Bank service fee,-15.00\n")
    result = reconcile(gl, bank)
    assert result["summary"]["matched_count"] == 1
    assert len(result["unmatched_gl"]) == 1
    assert result["unmatched_gl"][0]["description"] == "Fee"
    assert len(result["unmatched_bank"]) == 1
    assert result["unmatched_bank"][0]["description"] == "Bank service fee"


def test_no_double_matching_same_row_twice():
    gl = _df(
        b"date,description,amount\n2026-01-01,Rent A,500.00\n2026-01-01,Rent B,500.00\n"
    )
    bank = _df(b"date,description,amount\n2026-01-01,ACH Deposit,500.00\n")
    result = reconcile(gl, bank)
    assert result["summary"]["matched_count"] == 1
    assert len(result["unmatched_gl"]) == 1
    assert len(result["unmatched_bank"]) == 0


def test_summary_totals_and_difference():
    gl = _df(b"date,description,amount\n2026-01-01,A,100.00\n2026-01-02,B,-40.00\n")
    bank = _df(b"date,description,amount\n2026-01-01,A,100.00\n")
    result = reconcile(gl, bank)
    summary = result["summary"]
    assert summary["gl_total"] == 60.0
    assert summary["bank_total"] == 100.0
    assert summary["difference"] == -40.0

from backend.app.qbo.mapping import (
    DOC_NUMBER_MAX_LENGTH,
    build_dedupe_doc_number,
    build_deposit,
    build_purchase,
)


def test_doc_number_is_deterministic_and_within_length_limit():
    a = build_dedupe_doc_number("2026-06-04", "Bill Pay Salvador Hernandez", -100.0)
    b = build_dedupe_doc_number("2026-06-04", "Bill Pay Salvador Hernandez", -100.0)
    assert a == b
    assert len(a) <= DOC_NUMBER_MAX_LENGTH


def test_doc_number_differs_for_different_transactions():
    a = build_dedupe_doc_number("2026-06-04", "Bill Pay A", -100.0)
    b = build_dedupe_doc_number("2026-06-04", "Bill Pay B", -100.0)
    assert a != b


def test_doc_number_ignores_description_case_and_whitespace():
    a = build_dedupe_doc_number("2026-06-04", "Bill Pay", -100.0)
    b = build_dedupe_doc_number("2026-06-04", "  bill pay  ", -100.0)
    assert a == b


def test_build_deposit_maps_fields_onto_qbo_object():
    deposit = build_deposit(
        date="2026-06-25", description="Legal One Realty Ownerfunds", amount=3998.82,
        bank_account_id="35", income_account_id="90", doc_number="R-abc123",
    )
    assert deposit.TxnDate == "2026-06-25"
    assert deposit.DocNumber == "R-abc123"
    assert deposit.DepositToAccountRef.value == "35"
    assert len(deposit.Line) == 1
    assert deposit.Line[0].Amount == 3998.82
    assert deposit.Line[0].DepositLineDetail.AccountRef.value == "90"


def test_build_purchase_maps_fields_and_uses_absolute_amount():
    purchase = build_purchase(
        date="2026-06-04", description="Bill Pay Salvador Hernandez", amount=-100.0,
        bank_account_id="35", expense_account_id="70", doc_number="R-def456",
    )
    assert purchase.TxnDate == "2026-06-04"
    assert purchase.DocNumber == "R-def456"
    assert purchase.AccountRef.value == "35"
    assert len(purchase.Line) == 1
    assert purchase.Line[0].Amount == 100.0
    assert purchase.Line[0].AccountBasedExpenseLineDetail.AccountRef.value == "70"

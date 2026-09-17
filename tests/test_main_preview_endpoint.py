import io

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_preview_endpoint_returns_entries_and_summary():
    csv_bytes = (
        b"date,description,amount\n"
        b"2026-06-04,Bill Pay Vendor,-100.00\n"
        b"2026-06-25,Owner Deposit,3998.82\n"
    )
    files = {"file": ("transactions.csv", io.BytesIO(csv_bytes), "text/csv")}

    response = client.post("/api/transactions/preview", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["entry_count"] == 2
    assert data["summary"]["total"] == 3898.82
    assert data["summary"]["start_date"] == "2026-06-04"
    assert data["summary"]["end_date"] == "2026-06-25"
    assert len(data["entries"]) == 2
    assert data["entries"][0]["description"] == "Bill Pay Vendor"


def test_preview_endpoint_rejects_bad_file():
    files = {"file": ("transactions.csv", io.BytesIO(b"not,a,valid,ledger\n"), "text/csv")}

    response = client.post("/api/transactions/preview", files=files)

    assert response.status_code == 422

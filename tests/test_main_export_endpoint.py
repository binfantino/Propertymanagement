import io

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_export_qbo_desktop_endpoint_returns_qbo_file():
    csv_bytes = b"date,description,amount\n2026-06-04,Bill Pay Vendor,-100.00\n"
    files = {"spreadsheet": ("transactions.csv", io.BytesIO(csv_bytes), "text/csv")}
    data = {"account_id": "12345", "account_type": "CHECKING", "bank_id": "111000025"}

    response = client.post("/api/export/qbo-desktop", files=files, data=data)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.intu.qbo")
    assert "transactions.qbo" in response.headers["content-disposition"]
    assert "<BANKACCTFROM>" in response.text
    assert "<TRNAMT>-100.00" in response.text


def test_export_qbo_desktop_endpoint_rejects_bad_account_type():
    csv_bytes = b"date,description,amount\n2026-06-04,Bill Pay Vendor,-100.00\n"
    files = {"spreadsheet": ("transactions.csv", io.BytesIO(csv_bytes), "text/csv")}
    data = {"account_id": "12345", "account_type": "MONEY_MARKET"}

    response = client.post("/api/export/qbo-desktop", files=files, data=data)

    assert response.status_code == 422


def test_export_qbo_desktop_endpoint_rejects_bad_spreadsheet():
    files = {"spreadsheet": ("transactions.csv", io.BytesIO(b"not,a,valid,ledger\n"), "text/csv")}
    data = {"account_id": "12345", "account_type": "CHECKING"}

    response = client.post("/api/export/qbo-desktop", files=files, data=data)

    assert response.status_code == 422

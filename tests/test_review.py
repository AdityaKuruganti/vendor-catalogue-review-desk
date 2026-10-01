import io

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_review_flow(client):
    csv_bytes = b"sku,raw_row\nA1,Men shirt blue\nA2,BAD ROW men shirt\n"
    req = client.post("/requests", files={"file": ("v.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    ok, bad = req["listings"]
    assert (ok["status"], bad["status"]) == ("pending", "error")

    r = client.patch(f"/listings/{ok['id']}", json={"title": "Linen Shirt"}).json()
    assert r["listing"]["title"] == "Linen Shirt" and r["status"] == "pending"

    r = client.post(f"/listings/{ok['id']}/decision", json={"decision": "approved", "note": "ok"}).json()
    assert r["status"] == "approved"
    assert client.post(f"/listings/{bad['id']}/decision", json={"decision": "approved"}).status_code == 409

    assert "Linen Shirt" in client.get(f"/requests/{req['id']}/export.csv").text
    assert client.get("/requests").json()[0]["approved"] == 1
    assert client.get("/services").json()["stages"]
    assert ok["listing"]["english_description"]


def test_ui_is_served(client):
    assert "Listing review desk" in client.get("/").text


def test_remove_request(client):
    csv_bytes = b"raw_row\nMen shirt blue\n"
    rid = client.post("/requests", files={"file": ("v.csv", io.BytesIO(csv_bytes), "text/csv")}).json()["id"]
    assert client.delete(f"/requests/{rid}").json() == {"deleted": rid}
    assert client.get(f"/requests/{rid}").status_code == 404
    assert client.get("/requests").json() == []
    assert client.delete(f"/requests/{rid}").status_code == 404

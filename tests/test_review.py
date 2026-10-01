import io

from app import db

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


def test_remove_request_deletes_its_listings(client, fake_supabase):
    csv_bytes = b"raw_row\nMen shirt blue\nMen shirt red\n"
    rid = client.post("/requests", files={"file": ("v.csv", io.BytesIO(csv_bytes), "text/csv")}).json()["id"]
    other = client.post("/requests", files={"file": ("w.csv", io.BytesIO(csv_bytes), "text/csv")}).json()["id"]
    assert len(fake_supabase.tables["listings"]) == 4
    client.delete(f"/requests/{rid}")
    assert len(fake_supabase.tables["listings"]) == 2
    assert client.get(f"/requests/{other}").json()["total"] == 2


def test_supabase_not_configured_returns_503(client, monkeypatch):
    def boom():
        raise db.SupabaseConfigError("Supabase is not configured.")
    monkeypatch.setattr(db, "get_client", boom)
    r = client.get("/requests")
    assert r.status_code == 503 and "Supabase" in r.json()["detail"]


def test_missing_tables_gives_helpful_503(client, monkeypatch):
    from postgrest.exceptions import APIError

    def boom():
        raise APIError({"message": "Could not find the table 'public.requests'", "code": "PGRST205"})
    monkeypatch.setattr(db, "get_client", boom)
    r = client.get("/requests")
    assert r.status_code == 503 and "schema.sql" in r.json()["detail"]


def test_request_counts_need_no_sql_view(client, fake_supabase):
    csv_bytes = b"sku,raw_row\nA1,Men shirt blue\nA2,BAD ROW men shirt\n"
    rid = client.post("/requests", files={"file": ("v.csv", io.BytesIO(csv_bytes), "text/csv")}).json()["id"]
    row = client.get("/requests").json()[0]
    assert (row["id"], row["pending"], row["errors"], row["approved"]) == (rid, 1, 1, 0)


def test_other_supabase_errors_do_not_blame_the_schema(client, monkeypatch):
    from postgrest.exceptions import APIError

    def boom():
        raise APIError({"message": "permission denied", "code": "42501"})
    monkeypatch.setattr(db, "get_client", boom)
    r = client.get("/requests")
    assert r.status_code == 503 and "schema.sql" not in r.json()["detail"]

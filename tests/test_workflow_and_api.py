import io

from app.schemas import ApprovedListingObject


def test_workflow_fan_in(fake_workflow):
    out = fake_workflow.invoke({"raw_row": "Gents navy blue formal shirt linen XL"})
    assert isinstance(out, ApprovedListingObject)
    assert (out.color, out.fabric, out.demographic, out.size) == ("Navy", "Linen", "MEN", "XL")
    assert out.hinglish_description


def test_health(client):
    assert client.get("/health").status_code == 200


def test_sample_preview_needs_no_llm(client):
    r = client.get("/listings/sample/preview")
    assert r.status_code == 200 and r.json()["total_rows"] == 10


def test_single(client):
    r = client.post("/listings/single", json={"raw_row": "Gents navy shirt linen XL"})
    assert r.status_code == 200 and r.json()["demographic"] == "MEN"


def test_sample_batch(client):
    r = client.post("/listings/sample")
    body = r.json()
    assert r.status_code == 200 and body["total"] == 10 and body["failed"] == 0


def test_csv_upload_partial_failure(client):
    csv_bytes = b"sku,raw_row\nA1,Men shirt blue\nA2,BAD ROW men shirt\n"
    r = client.post("/listings/csv", files={"file": ("v.csv", io.BytesIO(csv_bytes), "text/csv")})
    body = r.json()
    assert r.status_code == 200
    assert (body["succeeded"], body["failed"]) == (1, 1)
    assert body["results"][1]["status"] == "error"


def test_csv_upload_rejects_bad_file(client):
    r = client.post("/listings/csv", files={"file": ("v.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 400
    r = client.post("/listings/csv", files={"file": ("v.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert r.status_code == 422

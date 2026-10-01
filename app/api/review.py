"""Endpoints behind the review desk UI: services catalogue, requests, edits, approvals."""
import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from langchain_core.runnables import Runnable

from app import db
from app.config import Settings, get_settings
from app.schemas import ApprovedListingObject, Decision, ListingEdit, VendorRow
from app.services.csv_loader import CsvValidationError, load_csv_file, parse_csv_bytes
from app.services.processor import process_rows
from app.workflow.pipeline import get_workflow

router = APIRouter(tags=["review"])

STAGES = [
    ("Color extract", "Standardises the primary colour to one word", "runs in parallel"),
    ("Fabric extract", "Standardises the main fabric to an industry label", "runs in parallel"),
    ("Demographic router", "Routes to Women, Kids or Men, then extracts title and size", "runs in parallel"),
    ("Hinglish description and fit", "Writes the description and fit guidance from the merged details", "runs after merge"),
]


async def _run(name: str, rows: list[VendorRow], workflow: Runnable, s: Settings) -> dict:
    batch = await process_rows(workflow, rows, s.batch_max_concurrency)
    return db.get_request(db.create_request(name, rows, batch))


@router.get("/services")
def services(s: Settings = Depends(get_settings)):
    return {
        "health": {"status": "ok", "model": s.llm_model, "api_key_configured": bool(s.openrouter_api_key),
                   "database": s.database_path, "concurrency": s.batch_max_concurrency},
        "stages": [{"name": n, "what": w, "mode": m} for n, w, m in STAGES],
    }


@router.get("/requests")
def requests_list():
    """List uploaded vendor documents with review counts."""
    return db.list_requests()


@router.post("/requests")
async def create_request(file: UploadFile = File(...), workflow: Runnable = Depends(get_workflow),
                         s: Settings = Depends(get_settings)):
    """Upload a vendor CSV, generate listings and save them for review."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file.")
    try:
        rows = parse_csv_bytes(await file.read(), s.max_upload_rows)
    except CsvValidationError as e:
        raise HTTPException(422, str(e))
    return await _run(file.filename, rows, workflow, s)


@router.post("/requests/sample")
async def create_sample_request(workflow: Runnable = Depends(get_workflow), s: Settings = Depends(get_settings)):
    """Generate listings from the bundled sample CSV and save them for review."""
    try:
        rows = load_csv_file(s.sample_csv_path, s.max_upload_rows)
    except CsvValidationError as e:
        raise HTTPException(422, str(e))
    return await _run("sample_vendor_rows.csv", rows, workflow, s)


@router.get("/requests/{rid}")
def request_detail(rid: int):
    """One request with all of its generated listings."""
    r = db.get_request(rid)
    if not r:
        raise HTTPException(404, "Request not found.")
    return r


@router.delete("/requests/{rid}")
def remove_request(rid: int):
    """Remove a request and all of its listings."""
    if not db.delete_request(rid):
        raise HTTPException(404, "Request not found.")
    return {"deleted": rid}


@router.get("/requests/{rid}/export.csv")
def export_approved(rid: int):
    """Download the approved listings of a request as CSV."""
    r = db.get_request(rid)
    if not r:
        raise HTTPException(404, "Request not found.")
    cols = list(ApprovedListingObject.model_fields)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["sku", "vendor", *cols])
    for l in r["listings"]:
        if l["status"] == "approved":
            w.writerow([l["sku"], l["vendor"], *[l["listing"].get(c, "") for c in cols]])
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="approved_request_{rid}.csv"'})


@router.patch("/listings/{lid}")
def edit_listing(lid: int, body: ListingEdit):
    """Correct a generated listing. An edited listing goes back to pending."""
    cur = db.get_listing(lid)
    if not cur or not cur["listing"]:
        raise HTTPException(404, "Listing not found or has no generated content.")
    merged = ApprovedListingObject(**{**cur["listing"], **body.model_dump(exclude_none=True)})
    db.save_listing(lid, merged.model_dump(), status="pending")
    return db.get_listing(lid)


@router.post("/listings/{lid}/decision")
def decide(lid: int, body: Decision):
    """Approve, reject or reopen a listing."""
    cur = db.get_listing(lid)
    if not cur:
        raise HTTPException(404, "Listing not found.")
    if cur["status"] == "error":
        raise HTTPException(409, "This row failed to generate, so it can't be reviewed.")
    db.save_listing(lid, status=body.decision, note=body.note)
    return db.get_listing(lid)

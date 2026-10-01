from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from langchain_core.runnables import Runnable

from app.config import Settings, get_settings
from app.schemas import (
    ApprovedListingObject,
    BatchResponse,
    CsvPreviewResponse,
    SingleListingRequest,
)
from app.services.csv_loader import CsvValidationError, load_csv_file, parse_csv_bytes
from app.services.processor import process_rows
from app.workflow.pipeline import get_workflow

router = APIRouter()


@router.get("/health", tags=["meta"])
def health(settings: Settings = Depends(get_settings)):
    return {"status": "ok", "model": settings.llm_model, "api_key_configured": bool(settings.openrouter_api_key)}


@router.get("/listings/sample/preview", response_model=CsvPreviewResponse, tags=["listings"])
def preview_sample(settings: Settings = Depends(get_settings)):
    """Load the bundled sample CSV and show parsed rows (no LLM call, no API key needed)."""
    try:
        rows = load_csv_file(settings.sample_csv_path, settings.max_upload_rows)
    except CsvValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return CsvPreviewResponse(total_rows=len(rows), rows=rows)


@router.post("/listings/single", response_model=ApprovedListingObject, tags=["listings"])
async def create_single_listing(body: SingleListingRequest, workflow: Runnable = Depends(get_workflow)):
    """Run one raw vendor row through the workflow."""
    return await workflow.ainvoke({"raw_row": body.raw_row})


@router.post("/listings/sample", response_model=BatchResponse, tags=["listings"])
async def run_sample_csv(
    workflow: Runnable = Depends(get_workflow),
    settings: Settings = Depends(get_settings),
):
    """Run every row of the bundled sample CSV through the workflow."""
    try:
        rows = load_csv_file(settings.sample_csv_path, settings.max_upload_rows)
    except CsvValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return await process_rows(workflow, rows, settings.batch_max_concurrency)


@router.post("/listings/csv", response_model=BatchResponse, tags=["listings"])
async def run_uploaded_csv(
    file: UploadFile = File(..., description="CSV with a 'raw_row' column (optional: sku, vendor)"),
    workflow: Runnable = Depends(get_workflow),
    settings: Settings = Depends(get_settings),
):
    """Upload a vendor CSV and run every row through the workflow."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")
    try:
        rows = parse_csv_bytes(await file.read(), settings.max_upload_rows)
    except CsvValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return await process_rows(workflow, rows, settings.batch_max_concurrency)

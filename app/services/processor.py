"""Runs the workflow over many rows; one bad row never fails the whole batch."""
from langchain_core.runnables import Runnable

from app.schemas import ApprovedListingObject, BatchResponse, RowResult, VendorRow


async def process_rows(workflow: Runnable, rows: list[VendorRow], max_concurrency: int) -> BatchResponse:
    inputs = [{"raw_row": r.raw_row} for r in rows]
    outputs = await workflow.abatch(
        inputs, config={"max_concurrency": max_concurrency}, return_exceptions=True
    )

    results: list[RowResult] = []
    for i, (row, out) in enumerate(zip(rows, outputs)):
        if isinstance(out, ApprovedListingObject):
            results.append(RowResult(row_index=i, sku=row.sku, status="success", listing=out))
        else:
            results.append(
                RowResult(row_index=i, sku=row.sku, status="error", error=f"{type(out).__name__}: {out}")
            )

    ok = sum(r.status == "success" for r in results)
    return BatchResponse(total=len(results), succeeded=ok, failed=len(results) - ok, results=results)

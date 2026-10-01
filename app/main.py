from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.review import router as review_router
from app.api.routes import router
from app.llm import MissingApiKeyError

app = FastAPI(
    title="Vendor Listing Pipeline",
    description="Raw vendor rows -> parallel extraction -> demographic routing -> Hinglish listing -> human review.",
    version="0.2.0",
)
app.include_router(router)
app.include_router(review_router)


@app.exception_handler(MissingApiKeyError)
async def missing_key_handler(_: Request, exc: MissingApiKeyError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# Review desk UI at "/" (mounted last so API routes and /docs take priority)
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="ui")

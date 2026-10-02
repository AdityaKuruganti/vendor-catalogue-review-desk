from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from postgrest.exceptions import APIError

from app.api.cx import router as cx_router
from app.api.review import router as review_router
from app.api.routes import router
from app.db import SupabaseConfigError
from app.llm import MissingApiKeyError

app = FastAPI(
    title="Vendor Listing Pipeline",
    description="Raw vendor rows -> parallel extraction -> demographic routing -> Hinglish listing -> human review.",
    version="0.2.0",
)
app.include_router(router)
app.include_router(review_router)
app.include_router(cx_router)


@app.exception_handler(MissingApiKeyError)
async def missing_key_handler(_: Request, exc: MissingApiKeyError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(SupabaseConfigError)
async def supabase_config_handler(_: Request, exc: SupabaseConfigError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(APIError)
async def supabase_api_error_handler(_: Request, exc: APIError):
    msg = getattr(exc, "message", None) or str(exc)
    hint = ""
    if getattr(exc, "code", None) in ("PGRST205", "42P01"):
        hint = " Run supabase/schema.sql in the Supabase SQL Editor (it also reloads the API schema cache)."
    return JSONResponse(status_code=503, content={"detail": f"Supabase error: {msg}.{hint}"})


# Review desk UI at "/" (mounted last so API routes and /docs take priority)
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="ui")

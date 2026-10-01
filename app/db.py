"""Supabase (Postgres) store: requests = uploaded vendor documents, listings = generated rows + review status.

Tables are defined in supabase/schema.sql. The server uses the
service-role key (never expose it to the browser).
"""
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlparse

from app.config import get_settings
from app.schemas import BatchResponse, VendorRow

_CHUNK = 500


class SupabaseConfigError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def host_label() -> str:
    return urlparse(get_settings().supabase_url).hostname or "not configured"


@lru_cache
def get_client():
    """Lazily build the Supabase client so the app (and CSV preview) starts without credentials."""
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_key):
        raise SupabaseConfigError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in your .env file.")
    from supabase import create_client

    return create_client(s.supabase_url, s.supabase_service_key)


def create_request(filename: str, rows: list[VendorRow], batch: BatchResponse) -> int:
    sb = get_client()
    rid = sb.table("requests").insert({"filename": filename, "total": len(rows)}).execute().data[0]["id"]
    now = _now()
    records = []
    for row, res in zip(rows, batch.results):
        ok = res.status == "success"
        records.append({
            "request_id": rid, "row_index": res.row_index, "sku": row.sku, "vendor": row.vendor,
            "raw_row": row.raw_row, "listing": res.listing.model_dump() if ok else None,
            "status": "pending" if ok else "error", "error": res.error, "updated_at": now,
        })
    try:
        for i in range(0, len(records), _CHUNK):
            sb.table("listings").insert(records[i:i + _CHUNK]).execute()
    except Exception:
        sb.table("requests").delete().eq("id", rid).execute()  # don't leave a half-saved request behind
        raise
    return rid


def _fetch_all(query_factory, page: int = 1000) -> list[dict]:
    """PostgREST caps a response at ~1000 rows, so read big tables page by page."""
    out: list[dict] = []
    while True:
        chunk = query_factory().range(len(out), len(out) + page - 1).execute().data
        out += chunk
        if len(chunk) < page:
            return out


def list_requests() -> list[dict]:
    sb = get_client()
    reqs = _fetch_all(lambda: sb.table("requests").select("*").order("id", desc=True))
    counts: dict[int, dict[str, int]] = {}
    for l in _fetch_all(lambda: sb.table("listings").select("request_id,status").order("id")):
        c = counts.setdefault(l["request_id"], {})
        c[l["status"]] = c.get(l["status"], 0) + 1
    return [{**r, "pending": counts.get(r["id"], {}).get("pending", 0),
             "approved": counts.get(r["id"], {}).get("approved", 0),
             "rejected": counts.get(r["id"], {}).get("rejected", 0),
             "errors": counts.get(r["id"], {}).get("error", 0)} for r in reqs]


def get_request(rid: int) -> dict | None:
    sb = get_client()
    found = sb.table("requests").select("*").eq("id", rid).limit(1).execute().data
    if not found:
        return None
    rows = sb.table("listings").select("*").eq("request_id", rid).order("row_index").execute().data
    return {**found[0], "listings": rows}


def get_listing(lid: int) -> dict | None:
    rows = get_client().table("listings").select("*").eq("id", lid).limit(1).execute().data
    return rows[0] if rows else None


def save_listing(lid: int, listing: dict | None = None, status: str | None = None, note: str | None = None):
    changes: dict = {"updated_at": _now()}
    if listing is not None:
        changes["listing"] = listing
    if status is not None:
        changes["status"] = status
    if note is not None:
        changes["note"] = note
    get_client().table("listings").update(changes).eq("id", lid).execute()


def delete_request(rid: int) -> bool:
    """Deleting the request also deletes its listings (ON DELETE CASCADE)."""
    return bool(get_client().table("requests").delete().eq("id", rid).execute().data)

"""SQLite store (stdlib only): requests = uploaded vendor documents, listings = generated rows + review status."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.schemas import BatchResponse, VendorRow

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, created_at TEXT, total INTEGER);
CREATE TABLE IF NOT EXISTS listings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER, row_index INTEGER,
  sku TEXT, vendor TEXT, raw_row TEXT, listing TEXT,
  status TEXT, error TEXT, note TEXT, updated_at TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    path = Path(get_settings().database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _listing(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["listing"] = json.loads(d["listing"]) if d["listing"] else None
    return d


def create_request(filename: str, rows: list[VendorRow], batch: BatchResponse) -> int:
    with conn() as c:
        rid = c.execute(
            "INSERT INTO requests(filename, created_at, total) VALUES (?,?,?)",
            (filename, _now(), len(rows)),
        ).lastrowid
        for row, res in zip(rows, batch.results):
            ok = res.status == "success"
            c.execute(
                "INSERT INTO listings(request_id,row_index,sku,vendor,raw_row,listing,status,error,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, res.row_index, row.sku, row.vendor, row.raw_row,
                 res.listing.model_dump_json() if ok else None,
                 "pending" if ok else "error", res.error, _now()),
            )
    return rid


def list_requests() -> list[dict]:
    with conn() as c:
        q = """SELECT r.*,
          COALESCE(SUM(l.status='pending'),0) pending, COALESCE(SUM(l.status='approved'),0) approved,
          COALESCE(SUM(l.status='rejected'),0) rejected, COALESCE(SUM(l.status='error'),0) errors
          FROM requests r LEFT JOIN listings l ON l.request_id=r.id GROUP BY r.id ORDER BY r.id DESC"""
        return [dict(r) for r in c.execute(q)]


def get_request(rid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
        if not r:
            return None
        rows = c.execute("SELECT * FROM listings WHERE request_id=? ORDER BY row_index", (rid,))
        return {**dict(r), "listings": [_listing(x) for x in rows]}


def get_listing(lid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
        return _listing(r) if r else None


def save_listing(lid: int, listing: dict | None = None, status: str | None = None, note: str | None = None):
    with conn() as c:
        cur = get_listing(lid)
        c.execute(
            "UPDATE listings SET listing=?, status=?, note=?, updated_at=? WHERE id=?",
            (json.dumps(listing if listing is not None else cur["listing"]),
             status or cur["status"], note if note is not None else cur["note"], _now(), lid),
        )


def delete_request(rid: int) -> bool:
    with conn() as c:
        c.execute("DELETE FROM listings WHERE request_id=?", (rid,))
        return c.execute("DELETE FROM requests WHERE id=?", (rid,)).rowcount > 0

"""Streamlit front end for the Vendor Catalogue Review Desk.

Reuses the existing workflow, CSV loader and Supabase store directly (no FastAPI needed).
Run locally:  streamlit run streamlit_app.py
"""
import asyncio
import csv
import io
import os
from pathlib import Path

import streamlit as st

# Streamlit secrets -> environment variables, so pydantic Settings picks them up.
# Must run before get_settings() is first called. Locally, .env is used instead.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k.upper(), _v)
except Exception:
    pass

os.chdir(Path(__file__).resolve().parent)  # so data/sample_vendor_rows.csv resolves anywhere

from app import db  # noqa: E402
from app.api.review import STAGES  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.schemas import ApprovedListingObject  # noqa: E402
from app.services.csv_loader import CsvValidationError, load_csv_file, parse_csv_bytes  # noqa: E402
from app.services.processor import process_rows  # noqa: E402
from app.llm import get_llm  # noqa: E402
from app.workflow.pipeline import build_workflow  # noqa: E402

DEMOGRAPHICS = ["MEN", "WOMEN", "KIDS"]
BADGE = {"pending": "🟡 Needs review", "approved": "🟢 Approved", "rejected": "🔴 Rejected", "error": "⚠️ Error"}

st.set_page_config(page_title="Vendor Catalogue Review Desk", page_icon="🧵", layout="wide")
s = get_settings()


def fresh_workflow():
    """New LLM client + workflow for every run.

    The cached get_workflow()/get_llm() keep an async HTTP client bound to the first event loop.
    Streamlit runs each action in a new asyncio.run() loop and closes it afterwards, so reusing
    that client raises "RuntimeError: Event loop is closed". __wrapped__ bypasses the lru_cache
    (it still validates the API key and reads the same settings).
    """
    return build_workflow(get_llm.__wrapped__())


def guarded(action):
    """Run an action and show friendly errors instead of a stack trace."""
    try:
        action()
    except CsvValidationError as e:
        st.error(str(e))
    except Exception as e:  # missing keys, Supabase errors, LLM errors
        st.error(f"{type(e).__name__}: {e}")


def generate(name: str, rows):
    with st.spinner(f"Generating {len(rows)} listings…"):
        batch = asyncio.run(process_rows(fresh_workflow(), rows, s.batch_max_concurrency))
        rid = db.create_request(name, rows, batch)
    st.session_state["open_rid"] = rid
    st.toast(f"{batch.succeeded} of {batch.total} listings generated")


def approved_csv(req: dict) -> str:
    cols = list(ApprovedListingObject.model_fields)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["sku", "vendor", *cols])
    for l in req["listings"]:
        if l["status"] == "approved" and l["listing"]:
            w.writerow([l["sku"], l["vendor"], *[l["listing"].get(c, "") for c in cols]])
    return buf.getvalue()


# ---------------------------------------------------------------- navigation
st.sidebar.title("Vendor Catalogue Review Desk")
page = st.sidebar.radio("Go to", ["Requests", "Services", "Docs"], key="page", label_visibility="collapsed")
st.sidebar.divider()

# ---------------------------------------------------------------- services page
if page == "Services":
    st.title("Services")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Model", s.llm_model)
    m2.metric("LLM API key", "configured" if s.openrouter_api_key else "missing")
    m3.metric("Database", f"Supabase ({db.host_label()})")
    m4.metric("Concurrency", s.batch_max_concurrency)

    st.subheader("Workflow stages")
    for i, (name, what, mode) in enumerate(STAGES, 1):
        st.markdown(f"**{i}. {name}** — {what} · _{mode}_")

    st.subheader("Try one vendor row")
    raw = st.text_area(
        "Raw vendor text",
        "Gents navy blue formal shirt made of pure linen fabric. Size XL available.",
        height=100,
    )
    if st.button("Generate listing", type="primary"):
        def _try():
            with st.spinner("Running workflow…"):
                out = asyncio.run(fresh_workflow().ainvoke({"raw_row": raw}))
            st.json(out.model_dump())
        guarded(_try)
    st.stop()

# ---------------------------------------------------------------- docs page
if page == "Docs":
    st.title("Docs")
    st.markdown(
        """
**What this app does.** A raw vendor CSV row goes through parallel extraction (color, fabric,
demographic router) → fan-in → Hinglish description and fit generator → an approved listing
object, saved to Supabase for human review. Nothing is approved automatically.

### CSV format
| Column | Required | Notes |
|---|---|---|
| `raw_row` | yes | The vendor's messy product text |
| `sku` | no | Shown in the review list and in the export |
| `vendor` | no | Included in the export |

UTF-8 only. Blank rows are skipped. The row limit is set by `MAX_UPLOAD_ROWS`.

### Review workflow
1. **Requests → upload a CSV** (or use the sample). Listings are generated and saved.
2. Open a request and compare the vendor text with the generated listing.
3. Edit any field and click **Save edits**. An edited listing returns to *Needs review*.
4. **Approve**, **Reject** or **Reopen**, with an optional note.
5. **Download approved CSV** for the approved rows.

### Settings (secrets / environment variables)
`OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (secret key), `LLM_MODEL`,
`LLM_BASE_URL`, `LLM_TEMPERATURE`, `BATCH_MAX_CONCURRENCY`, `MAX_UPLOAD_ROWS`, `SAMPLE_CSV_PATH`.
        """
    )
    st.subheader("Listing fields")
    st.table(
        [{"field": n, "description": f.description or ""} for n, f in ApprovedListingObject.model_fields.items()]
    )
    st.info(
        "The interactive Swagger page (`/docs`) and REST endpoints belong to the FastAPI app, which this "
        "Streamlit deployment does not run. To get them, run `uvicorn app.main:app` (see the README); "
        "its endpoints are listed in the README."
    )
    st.stop()

# ---------------------------------------------------------------- requests sidebar
with st.sidebar:
    st.header("Requests")
    up = st.file_uploader("Vendor CSV (needs a raw_row column)", type="csv")
    if up and st.button("Generate listings", type="primary"):
        guarded(lambda: generate(up.name, parse_csv_bytes(up.getvalue(), s.max_upload_rows)))
    if st.button("Use sample CSV"):
        guarded(lambda: generate("sample_vendor_rows.csv", load_csv_file(s.sample_csv_path, s.max_upload_rows)))

    try:
        reqs = db.list_requests()
    except Exception as e:
        st.error(f"{type(e).__name__}: {e}")
        reqs = []
    by_id = {r["id"]: r for r in reqs}
    if by_id and st.session_state.get("open_rid") not in by_id:
        st.session_state["open_rid"] = next(iter(by_id))
    rid = st.selectbox(
        "Open request", list(by_id), key="open_rid",
        format_func=lambda i: f"#{i} · {by_id[i]['filename']} ({by_id[i]['pending']} pending)",
    ) if by_id else None

# ---------------------------------------------------------------- main
st.title("Requests")
if rid is None:
    st.info("Upload a vendor CSV or use the sample to get started.")
    st.stop()

req = db.get_request(rid)
if not req:
    st.warning("Request not found.")
    st.stop()

meta = by_id[rid]
st.subheader(req["filename"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Needs review", meta["pending"])
c2.metric("Approved", meta["approved"])
c3.metric("Rejected", meta["rejected"])
c4.metric("Errors", meta["errors"])

d1, d2 = st.columns([1, 1])
d1.download_button("Download approved CSV", approved_csv(req), f"approved_request_{rid}.csv", "text/csv")
with d2.popover("Delete request"):
    st.write("This also deletes all of its listings.")
    if st.button("Yes, delete", key=f"del{rid}"):
        db.delete_request(rid)
        st.rerun()

for l in req["listings"]:
    with st.expander(f"{l['sku'] or 'row ' + str(l['row_index'] + 1)} · {BADGE.get(l['status'], l['status'])}"):
        left, right = st.columns(2)
        left.caption("Vendor's original text")
        left.write(l["raw_row"])

        if not l["listing"]:
            right.error(l["error"] or "This row failed to generate.")
            continue

        cur = l["listing"]
        with right.form(f"edit{l['id']}"):
            st.caption("Generated listing (editable)")
            vals = {f: st.text_input(f.title(), cur.get(f, "")) for f in ("title", "color", "fabric", "size")}
            demo = cur.get("demographic", "MEN")
            vals["demographic"] = st.selectbox("Demographic", DEMOGRAPHICS, index=DEMOGRAPHICS.index(demo) if demo in DEMOGRAPHICS else 0)
            for f in ("english_description", "hinglish_description", "fit_guidance"):
                vals[f] = st.text_area(f.replace("_", " ").title(), cur.get(f, ""))
            if st.form_submit_button("Save edits (returns to review)"):
                merged = ApprovedListingObject(**{**cur, **vals}).model_dump()
                if merged != cur:
                    guarded(lambda: db.save_listing(l["id"], merged, status="pending"))
                    st.rerun()

        note = st.text_input("Note (optional)", l.get("note") or "", key=f"note{l['id']}")
        b1, b2, b3 = st.columns(3)
        for col, label, decision in ((b1, "Approve", "approved"), (b2, "Reject", "rejected"), (b3, "Reopen", "pending")):
            if col.button(label, key=f"{decision}{l['id']}", disabled=l["status"] == decision):
                guarded(lambda: db.save_listing(l["id"], status=decision, note=note))
                st.rerun()

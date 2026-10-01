# Vendor Catalogue Review Desk

Raw vendor CSV row → **parallel extraction** (color, fabric, demographic router) → **fan-in** → **Hinglish description & fit generator** → `ApprovedListingObject`, served through **FastAPI**.

## Project structure

```
vendor-catalogue-review-desk/
├── .vscode/                    settings.json · launch.json (debug API/tests) · tasks.json
├── frontend/                   Review desk UI (index.html, styles.css, app.js)
├── app/
│   ├── main.py                 FastAPI app + error handler
│   ├── config.py               Settings loaded from .env
│   ├── llm.py                  Lazy ChatOpenAI (OpenRouter) factory
│   ├── db.py                   SQLite store for requests, listings and review status
│   ├── schemas.py              All Pydantic models (input, stage output, final object, API responses)
│   ├── api/routes.py           Stateless endpoints
│   ├── api/review.py           Requests, edits, approvals, services
│   ├── services/
│   │   ├── csv_loader.py       CSV file / upload parsing + validation
│   │   └── processor.py        Batch runner (per-row error isolation)
│   └── workflow/
│       ├── extractors.py       Stage 1 Color · Stage 2 Fabric
│       ├── router.py           Stage 3 Demographic router (WOMEN / KIDS / MEN branches)
│       ├── generator.py        Stage 4 Hinglish description & fit generator
│       └── pipeline.py         RunnableParallel fan-out → fan-in → generator → approved object
├── data/sample_vendor_rows.csv Sample vendor data (10 rows)
├── tests/                      pytest suite using a fake LLM (no API key / network needed)
├── .env.example
├── pytest.ini
└── requirements.txt
```

## Setup (VS Code)

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
# edit .env and set OPENROUTER_API_KEY
```

In VS Code: `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `.venv`.
Run with **F5** (config "FastAPI: uvicorn (debug)") or:

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

## Review desk (frontend)

Open http://localhost:8000/ after starting the API. No build step; the UI lives in `frontend/` and is served by FastAPI.

- **Requests**: upload a vendor CSV (or use the sample). Listings are generated and saved to SQLite (`data/listings.db`).
- **Review**: the vendor's original text sits beside the generated listing. The representative can edit any field, then approve, reject or reopen it, with an optional note. Editing a listing returns it to *Needs review*. Nothing is approved automatically.
- **Services**: LLM key and model status, the workflow stages, and a box to try one row.
- Each listing has an English description, a Hinglish description and fit guidance.
- Requests can be removed from the Requests screen (this deletes their listings too).
- Approved listings can be downloaded as CSV per request.

Review endpoints: `GET/POST /requests`, `DELETE /requests/{id}`, `POST /requests/sample`, `GET /requests/{id}`, `GET /requests/{id}/export.csv`, `PATCH /listings/{id}`, `POST /listings/{id}/decision`, `GET /services`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Status + whether an API key is configured |
| GET | `/listings/sample/preview` | Parse `data/sample_vendor_rows.csv` and show rows (no LLM, no key needed) |
| POST | `/listings/single` | Run one raw row through the workflow |
| POST | `/listings/sample` | Run the whole sample CSV through the workflow |
| POST | `/listings/csv` | Upload your own CSV (`raw_row` column required; `sku`, `vendor` optional) |

```bash
curl http://localhost:8000/listings/sample/preview

curl -X POST http://localhost:8000/listings/single \
  -H "Content-Type: application/json" \
  -d '{"raw_row": "Gents navy blue formal shirt made of pure linen fabric. Size XL available."}'

curl -X POST http://localhost:8000/listings/csv -F "file=@data/sample_vendor_rows.csv"
```

Batch responses report `succeeded` / `failed` counts, and one failing row never fails the rest.

## Tests

```bash
pytest -v
```

## Changes vs. the original `miniProject` script

- `llm` is created in `app/llm.py` from env vars (the script had it commented out → `NameError`).
- API key is read from `.env`; it is not stored in code.
- Stage 3 uses a real `RunnableBranch` (WOMEN / KIDS / MEN) and returns structured `{title, size}` JSON instead of the `"Title: … | Size: …"` string.
- Regex word-boundary routing, so "men" is never confused with "women".
- Final object now includes `size`. Title, color, fabric and demographic come from the extractors; the Stage 4 LLM only writes `hinglish_description` and `fit_guidance`, so it can't silently rewrite them.
- Batch runs use `abatch` with `max_concurrency` (`BATCH_MAX_CONCURRENCY`) to respect API rate limits.

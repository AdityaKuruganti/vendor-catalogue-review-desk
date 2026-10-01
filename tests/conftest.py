import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app import db
from app.main import app
from app.workflow.pipeline import build_workflow, get_workflow


def _fake_llm_fn(prompt_value) -> AIMessage:
    """Answers each stage based on what the prompt asks for. Deterministic, no network."""
    text = prompt_value.to_string()
    if "primary product color" in text:
        return AIMessage(content="Navy")
    if "main fabric" in text:
        return AIMessage(content="Linen.")
    if "demographic category" in text:
        if "BAD ROW" in text:
            raise ValueError("simulated LLM failure")
        return AIMessage(content=json.dumps({"title": "Formal Shirt", "size": "XL"}))
    if "copywriter" in text:
        return AIMessage(content=json.dumps({
            "english_description": "A breathable linen shirt for summer.",
            "hinglish_description": "Garmi mein bhi stylish!",
            "fit_guidance": "True to size; take one size up for a relaxed fit.",
        }))
    raise AssertionError("unexpected prompt")


@pytest.fixture
def fake_workflow():
    return build_workflow(RunnableLambda(_fake_llm_fn))


@pytest.fixture
def client(fake_workflow):
    app.dependency_overrides[get_workflow] = lambda: fake_workflow
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- minimal in-memory Supabase (only the calls app/db.py makes) ----------
class _Query:
    def __init__(self, fake, name):
        self.f, self.name, self.op = fake, name, "select"
        self.filters, self.order_by, self.max, self.payload, self.slice = [], None, None, None, None

    def select(self, _cols="*"):
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def order(self, col, desc=False):
        self.order_by = (col, desc)
        return self

    def limit(self, n):
        self.max = n
        return self

    def range(self, start, end):
        self.slice = (start, end)
        return self

    def _match(self, rows):
        return [r for r in rows if all(r.get(c) == v for c, v in self.filters)]

    def execute(self):
        f = self.f
        if True:
            rows = f.tables[self.name]
            if self.op == "insert":
                items = self.payload if isinstance(self.payload, list) else [self.payload]
                made = []
                for it in items:
                    f.seq[self.name] += 1
                    row = {"id": f.seq[self.name], "note": None, "error": None, **it}
                    if self.name == "requests":
                        row.setdefault("created_at", "2026-10-01T12:00:00.000000+00:00")
                    rows.append(row)
                    made.append(dict(row))
                return SimpleNamespace(data=made)
            hit = self._match(rows)
            if self.op == "update":
                for r in hit:
                    r.update(self.payload)
                return SimpleNamespace(data=[dict(r) for r in hit])
            if self.op == "delete":
                ids = {r["id"] for r in hit}
                rows[:] = [r for r in rows if r["id"] not in ids]
                if self.name == "requests":  # ON DELETE CASCADE
                    f.tables["listings"][:] = [l for l in f.tables["listings"] if l["request_id"] not in ids]
                return SimpleNamespace(data=[dict(r) for r in hit])
            rows = hit
        if self.order_by:
            col, desc = self.order_by
            rows = sorted(rows, key=lambda r: r[col], reverse=desc)
        if self.slice:
            rows = rows[self.slice[0]: self.slice[1] + 1]
        if self.max is not None:
            rows = rows[: self.max]
        return SimpleNamespace(data=[dict(r) for r in rows])


class FakeSupabase:
    def __init__(self):
        self.tables = {"requests": [], "listings": []}
        self.seq = {"requests": 0, "listings": 0}

    def table(self, name):
        return _Query(self, name)


@pytest.fixture(autouse=True)
def fake_supabase(monkeypatch):
    """Every test gets an empty in-memory database; nothing can reach a real Supabase project."""
    fake = FakeSupabase()
    monkeypatch.setattr(db, "get_client", lambda: fake)
    return fake

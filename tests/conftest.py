import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

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

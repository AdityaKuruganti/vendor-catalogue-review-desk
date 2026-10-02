from types import SimpleNamespace

import pytest

from app import db
from app.cx import pipeline
from app.cx.chains import build_cx_chains
from app.main import app
from tests.cx_helpers import GOOD_REPLY, ScriptedLLM, intent, seed_cx


@pytest.fixture(autouse=True)
def cx_seed(fake_supabase):
    seed_cx(fake_supabase)


def run(llm, phone="9876543210", message="Mera order kahan hai? ORD-10001"):
    chains = build_cx_chains(llm.runnable, llm.runnable, llm.runnable)
    return pipeline.run_copilot(phone, message, chains)


def test_order_status_happy_path():
    llm = ScriptedLLM(intent(), [{"reply_text": GOOD_REPLY}])
    res = run(llm)
    assert not res.needs_human and res.rewrites == 0 and res.order_id == "ORD-10001"
    assert "DL4455667788" in res.facts and "fabric:" not in res.facts  # routed: order facts only
    assert llm.calls == {"classify": 1, "draft": 1, "eval": 1}


def test_invented_date_triggers_one_rewrite():
    bad = GOOD_REPLY.replace("05 Oct 2026", "03 Oct 2026")
    llm = ScriptedLLM(intent(), [{"reply_text": bad}, {"reply_text": GOOD_REPLY}])
    res = run(llm)
    assert res.rewrites == 1 and not res.needs_human and res.reply_text == GOOD_REPLY
    assert "03" in llm.draft_prompts[1]  # the rewrite prompt carried the issue


def test_still_ungrounded_after_rewrite_goes_to_human():
    bad = GOOD_REPLY.replace("05 Oct 2026", "03 Oct 2026")
    res = run(ScriptedLLM(intent(), [{"reply_text": bad}]))
    assert res.needs_human and res.rewrites == 1 and res.issues


def test_evaluator_failure_is_surfaced():
    verdicts = [{"grounded": False, "answers_question": True, "issues": ["claims free returns"]}]
    res = run(ScriptedLLM(intent(), [{"reply_text": GOOD_REPLY}], verdicts))
    assert res.needs_human and "claims free returns" in res.issues


def test_return_request_escalates_without_drafting():
    llm = ScriptedLLM(intent("RETURN_EXCHANGE", None), [{"reply_text": "x"}])
    res = run(llm, message="Return karna hai")
    assert res.needs_human and llm.calls["draft"] == 0 and res.reply_text == ""


def test_low_confidence_escalates():
    llm = ScriptedLLM(intent(confidence=0.3), [{"reply_text": "x"}])
    assert run(llm).needs_human and llm.calls["draft"] == 0


def test_unknown_customer_and_customer_without_orders():
    llm = ScriptedLLM(intent(), [{"reply_text": "x"}])
    assert run(llm, phone="9000000000").human_reason == "customer_not_found_ask_for_order_number"
    assert run(llm, phone="9988776655").human_reason == "no_orders_for_customer"
    assert llm.calls["classify"] == 0


def test_order_id_of_another_customer_is_ignored():
    # model "returns" Anita's order for Priya: it must be dropped and both of Priya's orders offered
    llm = ScriptedLLM(intent(order_id="ORD-10003"), [{"reply_text": "Priya ji, kaun sa order? ORD-10001 ya ORD-10005?"}])
    res = run(llm, message="Mera order kab aayega?")
    assert res.order_id is None
    assert "ORD-10001" in res.facts and "ORD-10005" in res.facts and "ORD-10003" not in res.facts


def test_fit_question_without_approved_listing_gets_no_guessing_facts():
    llm = ScriptedLLM(intent("FIT_SIZE", "ORD-10005"),
                      [{"reply_text": "Priya ji, main team se confirm karke batati hoon.",
                        "needs_human": True, "human_reason": "no catalogue data"}])
    res = run(llm, message="ORD-10005 mein blouse piece hai?")
    assert "NOT AVAILABLE" in res.facts and "UNREVIEWED" not in res.facts and res.needs_human


def test_llm_crash_hands_over_to_a_human():
    llm = ScriptedLLM(intent(), [{"reply_text": GOOD_REPLY}])
    chains = build_cx_chains(llm.runnable, llm.runnable, llm.runnable)
    def boom(*_):
        raise RuntimeError("boom")
    chains.draft = SimpleNamespace(invoke=boom)
    res = pipeline.run_copilot("9876543210", "kahan hai?", chains)
    assert res.needs_human and res.human_reason == "system_error"


def test_supabase_config_error_is_not_swallowed(monkeypatch):
    def boom():
        raise db.SupabaseConfigError("Supabase is not configured.")
    monkeypatch.setattr(db, "get_client", boom)
    llm = ScriptedLLM(intent(), [{"reply_text": GOOD_REPLY}])
    with pytest.raises(db.SupabaseConfigError):
        run(llm)


def test_api_draft_and_approve(client, fake_supabase):
    llm = ScriptedLLM(intent(), [{"reply_text": GOOD_REPLY}])
    chains = build_cx_chains(llm.runnable, llm.runnable, llm.runnable)
    app.dependency_overrides[pipeline.get_cx_chains] = lambda: chains
    r = client.post("/cx/draft", json={"phone": "+91 98765 43210", "message": "ORD-10001 kahan hai?"})
    body = r.json()
    assert r.status_code == 200 and body["reply_text"] == GOOD_REPLY and body["customer_id"] == "1"

    r = client.post("/cx/approve", json={"customer_id": "1", "phone": "+91 98765 43210", "category": body["category"],
                                         "draft": body["reply_text"], "final": body["reply_text"] + " Thanks!"})
    assert r.status_code == 200
    row = fake_supabase.tables["cx_reply_log"][0]
    assert row["phone_masked"] == "******3210" and row["edited"] is True

"""Fixed pipeline (a chain, not an agent):
identify -> classify -> guard -> retrieve -> routed draft -> verify (+1 rewrite) -> result.
Everything that touches data or sets policy is deterministic; the LLM only classifies
and writes. Sync on purpose: Streamlit and FastAPI (threadpool) can both call it
without the event-loop issue described in streamlit_app.py."""
import logging
import uuid
from functools import lru_cache

from postgrest.exceptions import APIError

from app import db
from app.cx import store
from app.cx.chains import CxChains, build_cx_chains
from app.cx.guards import mask_phone, should_escalate, ungrounded_numbers, valid_order_id
from app.cx.schemas import CopilotResult
from app.llm import get_llm_for

log = logging.getLogger("cx_copilot")
MAX_REWRITES = 1


@lru_cache
def get_cx_chains() -> CxChains:
    """FastAPI dependency. Raises MissingApiKeyError if no key is configured."""
    from app.config import get_settings
    s = get_settings()
    cheap = get_llm_for(s.cx_classifier_model or s.llm_model, 0.0)
    strong = get_llm_for(s.cx_draft_model or s.llm_model, 0.3)
    judge = get_llm_for(s.cx_eval_model or s.cx_draft_model or s.llm_model, 0.0)
    return build_cx_chains(cheap, strong, judge)


def _escalate(run_id: str, reason: str, **kw) -> CopilotResult:
    return CopilotResult(run_id=run_id, needs_human=True, human_reason=reason, **kw)


def run_copilot(phone: str, message: str, chains: CxChains, sb=None) -> CopilotResult:
    run_id = uuid.uuid4().hex[:8]
    try:
        sb = sb or db.get_client()

        customer = store.find_customer(sb, phone)
        if not customer:
            return _escalate(run_id, "customer_not_found_ask_for_order_number")
        base = dict(customer_id=str(customer["customer_id"]), customer_name=customer["name"])
        orders = store.get_orders_with_fit(sb, customer["customer_id"])
        if not orders:
            return _escalate(run_id, "no_orders_for_customer", **base)

        intent = chains.classify.invoke({
            "message": message,
            "order_ids": ", ".join(o["order_id"] for o in orders),
        })
        order_id = valid_order_id(intent.order_id, orders)  # drop invented / foreign ids
        base.update(category=intent.category, confidence=intent.confidence, order_id=order_id)

        reason = should_escalate(intent.category, intent.confidence)
        if reason:
            return _escalate(run_id, reason, **base)

        scoped = [o for o in orders if o["order_id"] == order_id] or orders
        include = {"ORDER_STATUS": ("order",), "FIT_SIZE": ("fit",)}.get(intent.category, ("order", "fit"))
        facts = store.facts_text(customer, scoped, include)

        payload = {"category": intent.category, "facts": facts, "message": message, "fix_notes": ""}
        draft = chains.draft.invoke(payload)
        rewrites = 0
        while True:
            issues = [f"Reply contains value not found in facts: {t}"
                      for t in ungrounded_numbers(draft.reply_text, facts, message)]
            verdict = chains.evaluate.invoke({"facts": facts, "message": message, "draft": draft.reply_text})
            if not verdict.grounded:
                issues += verdict.issues or ["Evaluator: draft not grounded in facts"]
            if not verdict.answers_question:
                issues.append("Evaluator: draft does not answer the question")
            if not issues or rewrites >= MAX_REWRITES:
                break
            rewrites += 1
            payload["fix_notes"] = ("<fix>\nYour previous draft had these problems. Rewrite it using only the facts:\n- "
                                    + "\n- ".join(issues) + "\n</fix>")
            draft = chains.draft.invoke(payload)

        needs_human = draft.needs_human or bool(issues)
        human_reason = draft.human_reason or ("; ".join(issues) if issues else "")
        log.info("run=%s phone=%s category=%s rewrites=%s needs_human=%s",
                 run_id, mask_phone(phone), intent.category, rewrites, needs_human)
        return CopilotResult(run_id=run_id, facts=facts, reply_text=draft.reply_text,
                             needs_human=needs_human, human_reason=human_reason,
                             issues=issues, rewrites=rewrites, **base)
    except (db.SupabaseConfigError, APIError):
        raise  # setup / database problems: let the API return its helpful 503 instead of hiding them
    except Exception:  # LLM or parsing failure: never fail silently into a wrong reply, hand to a human
        log.exception("run=%s failed", run_id)
        return _escalate(run_id, "system_error")

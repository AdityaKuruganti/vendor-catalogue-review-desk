"""Shared test helpers for the CX copilot (imported by test_cx_*.py)."""
import json

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


def seed_cx(fake):
    """Add the CX tables to the in-memory Supabase fake and insert demo rows."""
    for t in ("cx_customers", "cx_orders", "cx_reply_log"):
        fake.tables[t] = []
        fake.seq[t] = 0
    fake.tables["cx_customers"] += [
        {"customer_id": 1, "phone": "9876543210", "name": "Priya Sharma"},
        {"customer_id": 2, "phone": "9123456780", "name": "Anita Iyer"},
        {"customer_id": 3, "phone": "9988776655", "name": "Rohan Mehta"},  # no orders
    ]
    fake.tables["cx_orders"] += [
        {"order_id": "ORD-10001", "customer_id": 1, "sku_code": "W-KRT-GRN-M", "size_ordered": "M",
         "status": "IN_TRANSIT", "carrier": "Delhivery", "awb": "DL4455667788",
         "ordered_at": "2026-09-28T00:00:00+00:00", "expected_delivery": "2026-10-05"},
        {"order_id": "ORD-10005", "customer_id": 1, "sku_code": "W-SAR-MRN-FS", "size_ordered": "Free Size",
         "status": "PLACED", "carrier": None, "awb": None,
         "ordered_at": "2026-10-01T00:00:00+00:00", "expected_delivery": "2026-10-08"},
        {"order_id": "ORD-10003", "customer_id": 2, "sku_code": "K-FRK-PNK-67", "size_ordered": "6-7Y",
         "status": "SHIPPED", "carrier": "Xpressbees", "awb": "XB9988776655",
         "ordered_at": "2026-09-29T00:00:00+00:00", "expected_delivery": "2026-10-06"},
    ]
    listing = lambda **kw: {"title": "Green Chikankari Kurta", "color": "Green", "fabric": "Georgette",
                            "demographic": "WOMEN", "size": "M", "english_description": "x",
                            "hinglish_description": "y", "fit_guidance": "Regular fit; true to size.", **kw}
    fake.tables["listings"] += [
        # approved (older) and approved (newer) for the same SKU: newest must win
        {"id": 1, "request_id": 1, "sku": "W-KRT-GRN-M", "status": "approved", "updated_at": "2026-09-20T00:00:00",
         "listing": listing(fit_guidance="OLD guidance")},
        {"id": 2, "request_id": 2, "sku": "W-KRT-GRN-M", "status": "approved", "updated_at": "2026-09-25T00:00:00",
         "listing": listing()},
        # not approved: must never be used
        {"id": 3, "request_id": 2, "sku": "W-SAR-MRN-FS", "status": "pending", "updated_at": "2026-09-25T00:00:00",
         "listing": listing(title="Maroon Banarasi Saree", fit_guidance="UNREVIEWED")},
        {"id": 4, "request_id": 2, "sku": "K-FRK-PNK-67", "status": "rejected", "updated_at": "2026-09-25T00:00:00",
         "listing": listing(title="Pink Frock")},
    ]


class ScriptedLLM:
    """Fake chat model. Answers classifier / drafter / judge prompts from a script and records calls."""

    def __init__(self, intent, drafts, verdicts=None):
        self.intent = intent
        self.drafts = drafts
        self.verdicts = verdicts or [{"grounded": True, "answers_question": True, "issues": []}]
        self.calls = {"classify": 0, "draft": 0, "eval": 0}
        self.draft_prompts = []
        self.runnable = RunnableLambda(self._fn)

    def _fn(self, pv):
        text = pv.to_string()
        if "strict QA reviewer" in text:
            i = self.calls["eval"]; self.calls["eval"] += 1
            return AIMessage(content=json.dumps(self.verdicts[min(i, len(self.verdicts) - 1)]))
        if "classify customer support" in text:
            self.calls["classify"] += 1
            return AIMessage(content=json.dumps(self.intent))
        i = self.calls["draft"]; self.calls["draft"] += 1
        self.draft_prompts.append(text)
        d = self.drafts[min(i, len(self.drafts) - 1)]
        return AIMessage(content=json.dumps({"facts_used": [], "needs_human": False, "human_reason": "", **d}))


def intent(category="ORDER_STATUS", order_id="ORD-10001", confidence=0.9):
    return {"category": category, "order_id": order_id, "confidence": confidence, "reason": "test"}


GOOD_REPLY = ("Priya ji, aapka order ORD-10001 Delhivery ke saath in transit hai. "
              "Tracking DL4455667788, 05 Oct 2026 tak deliver ho jayega.")

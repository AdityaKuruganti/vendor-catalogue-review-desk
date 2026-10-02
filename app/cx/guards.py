"""Deterministic guards for the CX copilot: no LLM, no third-party imports."""
import re
from datetime import date, datetime
from typing import Optional

MIN_CONFIDENCE = 0.6
HUMAN_ONLY_CATEGORIES = {"RETURN_EXCHANGE", "OTHER"}


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """'+91 98765-43210' / '098765 43210' -> '9876543210' (last 10 digits)."""
    digits = re.sub(r"\D", "", raw or "")
    return digits[-10:] if len(digits) >= 10 else None


def mask_phone(phone: Optional[str]) -> str:
    p = normalize_phone(phone)
    return f"******{p[-4:]}" if p else "unknown"


def fmt_date(value) -> str:
    """Accepts 'YYYY-MM-DD', a full ISO timestamp, a date, or None -> '05 Oct 2026'."""
    if not value:
        return "not available"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d %b %Y")
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d %b %Y")


def valid_order_id(order_id: Optional[str], orders: list) -> Optional[str]:
    """The LLM may only point at orders that belong to THIS customer."""
    if not order_id:
        return None
    allowed = {o["order_id"] for o in orders}
    return order_id if order_id in allowed else None


def should_escalate(category: str, confidence: float) -> Optional[str]:
    """Reason string if a human must handle the ticket, else None."""
    if category in HUMAN_ONLY_CATEGORIES:
        return f"category_{category.lower()}_needs_human"
    if confidence < MIN_CONFIDENCE:
        return "low_classifier_confidence"
    return None


_TOKEN = re.compile(r"[A-Za-z0-9]*\d[A-Za-z0-9]*")


def _tokens(text: Optional[str]) -> set:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def ungrounded_numbers(reply: str, *allowed_texts: str) -> list:
    """Digit-bearing tokens (dates, AWBs, sizes, amounts) in the reply that appear
    in neither the facts nor the customer's own message."""
    allowed = set()
    for t in allowed_texts:
        allowed |= _tokens(t)
    return sorted(_tokens(reply) - allowed)

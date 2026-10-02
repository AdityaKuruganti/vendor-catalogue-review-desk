"""Supabase access for the CX copilot. Every function takes the client explicitly
(`sb`), so tests can pass the in-memory fake and nothing here imports app.config.

Tables: cx_customers, cx_orders, cx_reply_log (supabase/schema_cx.sql).
Catalogue: the review desk's existing `listings` table. Only rows with
status = 'approved' are used, so unreviewed or rejected AI output never reaches a customer.
"""
from typing import Optional

from app.cx.guards import fmt_date, mask_phone, normalize_phone

CATALOGUE_FIELDS = ("title", "color", "fabric", "demographic", "size", "fit_guidance")


def find_customer(sb, phone_raw: str) -> Optional[dict]:
    phone = normalize_phone(phone_raw)
    if not phone:
        return None
    rows = sb.table("cx_customers").select("*").eq("phone", phone).limit(1).execute().data
    return rows[0] if rows else None


def approved_listing_for_sku(sb, sku: Optional[str]) -> Optional[dict]:
    """Latest APPROVED listing for a SKU (a SKU can appear in several uploads)."""
    if not sku:
        return None
    rows = (sb.table("listings").select("*").eq("sku", sku).eq("status", "approved")
            .order("updated_at", desc=True).limit(1).execute().data)
    return (rows[0].get("listing") or None) if rows else None


def get_orders_with_fit(sb, customer_id, limit: int = 5) -> list:
    """Orders for ONE customer, each with its approved catalogue listing (or None).
    The customer scoping lives here, in code - never let the LLM choose it."""
    orders = (sb.table("cx_orders").select("*").eq("customer_id", customer_id)
              .order("ordered_at", desc=True).limit(limit).execute().data)
    out = []
    for o in orders:
        out.append({**o, "catalogue": approved_listing_for_sku(sb, o.get("sku_code"))})
    return out


def facts_text(customer: dict, orders: list, include=("order", "fit")) -> str:
    """The ONLY source of truth the drafting model sees. Stable format, so the
    grounding check can compare the reply against it."""
    lines = [f"Customer first name: {customer['name'].split()[0]}"]
    for o in orders:
        cat = o.get("catalogue")
        item = (cat or {}).get("title") or o["sku_code"]
        lines.append(f"Order {o['order_id']} | item: {item} | SKU {o['sku_code']} | size ordered: {o.get('size_ordered') or 'not recorded'}")
        if "order" in include:
            lines.append(
                f"  status: {o['status']}; carrier: {o.get('carrier') or 'not assigned yet'}; "
                f"tracking no: {o.get('awb') or 'not available yet'}; "
                f"expected delivery: {fmt_date(o.get('expected_delivery'))}"
            )
        if "fit" in include:
            if not cat:
                lines.append("  catalogue: NOT AVAILABLE for this SKU (do not guess fit, fabric, stretch or care)")
            else:
                lines.append(f"  fabric: {cat.get('fabric') or 'not specified'}; colour: {cat.get('color') or 'not specified'}; "
                             f"standard size: {cat.get('size') or 'not specified'}")
                lines.append(f"  fit guidance: {cat.get('fit_guidance') or 'not specified'}")
                lines.append("  stretch, care and shrinkage: only what the fabric and fit guidance above state; otherwise not specified")
    return "\n".join(lines)


def log_reply(sb, *, customer_id, phone, category, draft, final, needs_human, reason) -> None:
    sb.table("cx_reply_log").insert({
        "customer_id": customer_id, "phone_masked": mask_phone(phone), "category": category,
        "draft": draft, "final": final, "edited": draft.strip() != final.strip(),
        "needs_human": needs_human, "reason": reason,
    }).execute()

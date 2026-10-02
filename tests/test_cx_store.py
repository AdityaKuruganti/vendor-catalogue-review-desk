import pytest

from app.cx import store
from tests.cx_helpers import seed_cx


@pytest.fixture
def sb(fake_supabase):
    seed_cx(fake_supabase)
    return fake_supabase


def test_customer_lookup_by_any_phone_format(sb):
    assert store.find_customer(sb, "+91 98765 43210")["customer_id"] == 1
    assert store.find_customer(sb, "9000000000") is None
    assert store.find_customer(sb, "abc") is None


def test_orders_are_scoped_to_the_customer(sb):
    ids = {o["order_id"] for o in store.get_orders_with_fit(sb, 1)}
    assert ids == {"ORD-10001", "ORD-10005"}  # Anita's ORD-10003 never leaks


def test_only_latest_approved_listing_is_used(sb):
    orders = {o["order_id"]: o for o in store.get_orders_with_fit(sb, 1)}
    assert orders["ORD-10001"]["catalogue"]["fit_guidance"] == "Regular fit; true to size."  # newest approved
    assert orders["ORD-10005"]["catalogue"] is None  # only a pending listing exists
    anita = store.get_orders_with_fit(sb, 2)[0]
    assert anita["catalogue"] is None  # rejected listing


def test_facts_text_sections_and_missing_catalogue(sb):
    cust = store.find_customer(sb, "9876543210")
    orders = {o["order_id"]: o for o in store.get_orders_with_fit(sb, 1)}
    full = store.facts_text(cust, [orders["ORD-10001"]])
    assert "Georgette" in full and "05 Oct 2026" in full and "DL4455667788" in full
    assert "UNREVIEWED" not in full
    assert "NOT AVAILABLE" in store.facts_text(cust, [orders["ORD-10005"]])
    assert "fabric:" not in store.facts_text(cust, [orders["ORD-10001"]], ("order",))
    assert "tracking no:" not in store.facts_text(cust, [orders["ORD-10001"]], ("fit",))


def test_log_reply_masks_phone_and_flags_edit(sb):
    store.log_reply(sb, customer_id="1", phone="+91 98765 43210", category="ORDER_STATUS",
                    draft="a", final="b", needs_human=False, reason="")
    row = sb.tables["cx_reply_log"][0]
    assert row["phone_masked"] == "******3210" and row["edited"] is True

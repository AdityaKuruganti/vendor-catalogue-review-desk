from app.cx import guards


def test_phone_normalisation():
    for raw in ["+91 98765 43210", "09876543210", "98765-43210", "91 9876543210"]:
        assert guards.normalize_phone(raw) == "9876543210"
    assert guards.normalize_phone("12345") is None
    assert guards.normalize_phone("") is None
    assert guards.mask_phone("+91 98765 43210") == "******3210"


def test_fmt_date_accepts_supabase_formats():
    assert guards.fmt_date("2026-10-05") == "05 Oct 2026"
    assert guards.fmt_date("2026-10-05T00:00:00+00:00") == "05 Oct 2026"
    assert guards.fmt_date(None) == "not available"


def test_foreign_or_invented_order_id_is_dropped():
    orders = [{"order_id": "ORD-1"}, {"order_id": "ORD-2"}]
    assert guards.valid_order_id("ORD-1", orders) == "ORD-1"
    assert guards.valid_order_id("ORD-9", orders) is None
    assert guards.valid_order_id(None, orders) is None


def test_escalation_rules():
    assert guards.should_escalate("RETURN_EXCHANGE", 0.99)
    assert guards.should_escalate("OTHER", 0.99)
    assert guards.should_escalate("ORDER_STATUS", 0.4)
    assert guards.should_escalate("ORDER_STATUS", 0.9) is None


def test_grounding_check():
    facts = "tracking no: DL4455667788; expected delivery: 05 Oct 2026; bust 36"
    ok = "Order 05 Oct 2026 tak aayega, tracking DL4455667788."
    assert guards.ungrounded_numbers(ok, facts, "ORD-10001 kahan hai") == []
    bad = "Order 03 Oct 2026 tak aayega, tracking DL9999999999."
    assert guards.ungrounded_numbers(bad, facts, "") == ["03", "dl9999999999"]

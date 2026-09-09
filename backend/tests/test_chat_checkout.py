"""Coverage for offering a pay-now link inside a WhatsApp order.

Online payment only ever existed on the storefront, so a customer who
ordered by chat was given a total and left to pay by hand even when the
business had Paystack connected. The rule is that a business which set up
online payment gets a link, and one which did not is left exactly as it
was — no link, no error, no change to the conversation.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chat_checkout  # noqa: E402
from chat_checkout import _receipt_email, checkout_link_for_order  # noqa: E402

ORDER = {
    "_id": "o1",
    "order_number": "ORD-1",
    "total_amount": 2500,
    "currency": "KES",
    "customer_id": "c1",
    "customer_name": "Mary",
}
USER = {"_id": "u1"}


@pytest.fixture
def paystack(monkeypatch):
    """Control whether the business is connected and what Paystack returns."""
    state = {"connected": True, "result": {"authorization_url": "https://pay/x"}, "calls": []}

    import paystack_credentials
    import paystack_service

    monkeypatch.setattr(paystack_credentials, "paystack_connected", lambda doc: state["connected"])

    async def fake_init(db, user_doc, **kw):
        state["calls"].append(kw)
        if isinstance(state["result"], Exception):
            raise state["result"]
        return state["result"]

    monkeypatch.setattr(paystack_service, "initialize_checkout_for_user", fake_init)
    return state


@pytest.mark.asyncio
async def test_a_connected_business_gets_a_pay_link(paystack):
    link = await checkout_link_for_order(None, USER, ORDER, customer={}, phone="+254110400963")
    assert link == "https://pay/x"
    assert paystack["calls"][0]["amount_major"] == 2500
    assert paystack["calls"][0]["external_reference"] == "ORD-1"


@pytest.mark.asyncio
async def test_a_business_without_online_payment_gets_no_link(paystack):
    # The manual flow must be untouched: no link, and nothing raised.
    paystack["connected"] = False
    assert await checkout_link_for_order(None, USER, ORDER, customer={}, phone="+254110400963") is None
    assert paystack["calls"] == []


@pytest.mark.asyncio
async def test_paystack_failing_never_costs_the_customer_their_reply(paystack):
    paystack["result"] = RuntimeError("Paystack is down")
    assert await checkout_link_for_order(None, USER, ORDER, customer={}, phone="+254110400963") is None


@pytest.mark.asyncio
async def test_a_zero_total_is_not_sent_to_checkout(paystack):
    for bad in ({**ORDER, "total_amount": 0}, {**ORDER, "total_amount": None},
                {**ORDER, "total_amount": "abc"}):
        assert await checkout_link_for_order(None, USER, bad, customer={}, phone="+254") is None
    assert paystack["calls"] == []


# ── the email Paystack insists on ────────────────────────────────────────

def test_a_real_customer_email_is_used_when_we_have_one():
    assert _receipt_email({"email": "mary@example.com"}, "+254110400963") == "mary@example.com"


def test_otherwise_one_is_derived_from_the_phone():
    # Not a claim that we know their email — a routing address for a receipt.
    assert _receipt_email({}, "+254 110 400 963") == "254110400963@wa.zilo.pro"
    assert _receipt_email(None, "") == "customer@wa.zilo.pro"

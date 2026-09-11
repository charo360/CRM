"""A customer saying they paid is not a payment received.

A customer replied "Samuel Mweni, 3000" on a manual payment method, and the AI
answered "Payment of USD 3,000 received. Your order will be ready for pickup
tomorrow at 4pm." Nobody had seen the money. Five prompts told the model to
say "Payment received", and the reply embellished past even that.
"""
import asyncio
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from payment_claims import (  # noqa: E402
    claims_payment_received, guard_payment_claim, no_payment_reply, safe_claim_reply,
)

THE_INCIDENT = ("Thank you Samuel Mweni! 🙏 Payment of USD 3,000 received. "
                "Your order will be ready for pickup tomorrow at 4pm.")


# ------------------------------------------------------------- the claim

@pytest.mark.parametrize("text", [
    THE_INCIDENT,
    "Thank you! 🙏 Payment received. We are preparing your order!",
    "We've received your payment, thanks.",
    "Payment confirmed ✅",
    "Your payment was successful.",
    "Asante! Malipo yako yamepokelewa.",
    "Tumepokea malipo yako, asante sana.",
    "Payment received, we will prepare your order now.",
])
def test_an_assertion_of_receipt_is_caught(text):
    assert claims_payment_received(text)


@pytest.mark.parametrize("text", [
    "Once your payment is received, we'll get your order ready.",
    "I've passed your payment of USD 3,000 to the owner to check.",
    "You'll get a confirmation here as soon as it's verified.",
    "Please pay via M-Pesa 0796148903 and reply with your name and amount paid.",
    "The payment will be confirmed by the owner shortly.",
    "Your order is confirmed for pickup tomorrow at 4pm.",
    "Your payment hasn't been confirmed yet.",
    "We have not received your payment yet.",
    "Please send the payment to complete your order.",
    "",
])
def test_conditional_or_unrelated_wording_is_left_alone(text):
    assert not claims_payment_received(text)


def test_the_truthful_replies_are_not_themselves_claims():
    for sw in (False, True):
        assert not claims_payment_received(safe_claim_reply("Samuel", 3000, "USD", sw))
        assert not claims_payment_received(no_payment_reply(sw))


# ------------------------------------------------------------- the guard

class _Orders:
    def __init__(self, order):
        self.order = order

    async def find_one(self, *a, **k):
        return self.order


class _DB:
    def __init__(self, order=None):
        self.orders = _Orders(order)


CLAIM = [{"type": "set_payment_pending", "payee_name": "Samuel Mweni", "amount_paid": 3000}]


def _guard(reply, db=None, actions=CLAIM, message="Samuel Mweni, 3000"):
    return asyncio.run(guard_payment_claim(
        db or _DB(), reply, actions=actions, user_id="u", customer_id="c",
        customer_message=message, currency="USD"))


def test_the_incident_is_replaced_with_the_truth():
    out = _guard(THE_INCIDENT)
    assert not claims_payment_received(out)
    assert "Samuel Mweni" in out and "USD 3,000" in out
    assert "owner" in out.lower()
    assert "ready for pickup" not in out, "the order must not be described as settled"


def test_a_swahili_customer_is_answered_in_swahili():
    out = _guard("Asante! Malipo yako yamepokelewa.", message="Nimetuma 3000")
    assert out.startswith("Asante")
    assert not claims_payment_received(out)


def test_a_payment_the_owner_marked_paid_may_be_confirmed():
    paid = _DB({"payment_status": "paid"})
    text = "Yes, your payment was received. Thank you!"
    assert _guard(text, db=paid, actions=[]) == text


@pytest.mark.parametrize("status", ["pending_verification", "unpaid", "pending", None])
def test_an_unverified_order_may_not_be_confirmed_later_either(status):
    """A customer asking "did you get it?" before the owner has checked."""
    db = _DB({"payment_status": status})
    out = _guard("Yes, your payment was received!", db=db, actions=[], message="did you get my money")
    assert not claims_payment_received(out)
    if status == "pending_verification":
        assert out.startswith("Your payment is with the owner to check")


@pytest.mark.parametrize("order", [{"payment_status": "unpaid"}, None])
def test_a_receipt_nobody_claimed_is_not_passed_to_the_owner_either(order):
    """The AI invented a payment outright: saying it went to the owner would
    be a second invention."""
    out = _guard("Payment received, thank you!", db=_DB(order), actions=[], message="hello")
    assert out == no_payment_reply(False)


def test_a_claim_made_this_turn_is_never_confirmed_even_if_an_older_order_is_paid():
    db = _DB({"payment_status": "paid"})
    assert not claims_payment_received(_guard(THE_INCIDENT, db=db))


def test_an_ordinary_reply_passes_untouched():
    text = "Great 😊 Your order is confirmed for pickup tomorrow at 4pm."
    assert _guard(text, actions=[]) == text


# ------------------------------------------------------------- the prompts

PROMPTS = (BACKEND / "autoreply" / "prompt_builder.py").read_text(encoding="utf-8")


def test_no_prompt_tells_the_ai_to_say_payment_received():
    offenders = [line.strip() for line in PROMPTS.splitlines()
                 if "Reply:" in line and re.search(r"Payment (of \[amount\] )?received", line)]
    assert not offenders, "prompts still instruct a false receipt:\n" + "\n".join(offenders)


def test_the_shared_rule_forbids_the_claim_outright():
    assert "NEVER say a payment was received, confirmed or successful" in PROMPTS


def test_the_action_schema_asks_for_the_name_and_amount():
    """The model copies the example; without these fields the owner's alert
    said "WhatsApp contact" instead of the name the customer gave."""
    line = next(l for l in PROMPTS.splitlines() if '"type": "set_payment_pending"' in l)
    assert '"payee_name"' in line and '"amount_paid"' in line


# ------------------------------------------------------------- the owner's alert

class _WA:
    def __init__(self):
        self.sent = []

    async def send_message(self, *, user_id, to_number, message, send_context, customer_name=""):
        self.sent.append(message)
        return {"status": "success"}


def _alert(monkeypatch, **kw):
    import whatsapp_service
    from payment_notifications import notify_payment_claimed
    wa = _WA()
    monkeypatch.setattr(whatsapp_service, "get_whatsapp_service", lambda db: wa)
    user = {"_id": "u1", "whatsapp": {"phone_number": "254700000001"}}
    order = {"order_number": "ORD-8781F4", "total_amount": 3000}   # orders carry no currency
    asyncio.run(notify_payment_claimed(None, user, order=order, **kw))
    return wa.sent[0]


def test_the_alert_says_who_how_much_and_in_what_currency(monkeypatch):
    msg = _alert(monkeypatch, customer_name="Samuel Mweni", amount_claimed=3000, currency="USD")
    assert "Samuel Mweni says they have paid" in msg
    assert "USD 3,000" in msg
    assert "order total" not in msg, "the amounts agree -- nothing to flag"


def test_a_claim_that_does_not_match_the_order_is_flagged(monkeypatch):
    msg = _alert(monkeypatch, customer_name="Samuel", amount_claimed=2500, currency="USD")
    assert "USD 2,500" in msg
    assert "order total is USD 3,000" in msg


# ------------------------------------------------------------- the wiring

def _fn(path, name):
    import ast
    src = (BACKEND / path).read_text(encoding="utf-8-sig", errors="replace")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(name)


def test_the_engine_checks_the_reply_before_sending():
    body = _fn("autoreply/engine.py", "process_message")
    guard = body.index("guard_payment_claim")
    # Earlier sends in this function are product photos and their captions;
    # the model's written reply goes out in the send carrying reply_text.
    send = body.index("message=reply_text")
    assert guard < send, "the reply is sent before it is checked"

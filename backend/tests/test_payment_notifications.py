"""Coverage for telling people when money moves.

Both payment paths ended in silence. A buyer who paid online got a web page
and nothing on WhatsApp, while the buyer who did *not* pay got a friendly
confirmation — the paying customer was treated worse than the browsing one.
A customer paying by M-Pesa had their order marked pending_verification with
nothing telling the owner to check.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import payment_notifications as pn  # noqa: E402
from payment_notifications import (  # noqa: E402
    OWNER_ALERT_CONTEXT,
    RECEIPT_CONTEXT,
    notify_payment_claimed,
    notify_payment_received,
)

ORDER = {
    "order_number": "ZILO-260909-F20D94",
    "currency": "KES",
    "total_amount": 3600,
    "items": [{"quantity": 3, "product_name": "Cotton T-shirt"}],
}
USER = {"_id": "u1", "whatsapp": {"phone_number": "254700000001"}}


class FakeWA:
    def __init__(self, fail_on=None):
        self.sent = []
        self.fail_on = fail_on

    async def send_message(self, *, user_id, to_number, message, send_context, customer_name=""):
        if self.fail_on and self.fail_on in to_number:
            raise RuntimeError("WhatsApp is down")
        self.sent.append({"to": to_number, "message": message, "context": send_context})
        return {"status": "success"}


@pytest.fixture
def wa(monkeypatch):
    fake = FakeWA()
    import whatsapp_service

    monkeypatch.setattr(whatsapp_service, "get_whatsapp_service", lambda db: fake)
    monkeypatch.setattr(whatsapp_service, "owner_whatsapp_number", lambda u: "254700000001")
    return fake


@pytest.mark.asyncio
async def test_the_buyer_gets_a_receipt_and_the_owner_hears_the_money_landed(wa):
    await notify_payment_received(
        None, USER, order=ORDER, customer_name="Mary", customer_phone="254110400963",
        amount=3600, currency="KES", reference="ref1",
    )
    to = [m["to"] for m in wa.sent]
    assert "254110400963" in to, "the customer who paid must be told"
    assert "254700000001" in to, "the owner must be told money arrived"

    receipt = next(m for m in wa.sent if m["to"] == "254110400963")
    assert "Payment received" in receipt["message"]
    assert "KES 3,600" in receipt["message"]
    assert "ZILO-260909-F20D94" in receipt["message"]
    assert receipt["context"] == RECEIPT_CONTEXT

    alert = next(m for m in wa.sent if m["to"] == "254700000001")
    assert "3,600 received" in alert["message"]
    assert "Mary" in alert["message"]
    assert alert["context"] == OWNER_ALERT_CONTEXT


@pytest.mark.asyncio
async def test_a_failed_receipt_does_not_stop_the_owner_being_told(monkeypatch):
    fake = FakeWA(fail_on="254110400963")
    import whatsapp_service

    monkeypatch.setattr(whatsapp_service, "get_whatsapp_service", lambda db: fake)
    monkeypatch.setattr(whatsapp_service, "owner_whatsapp_number", lambda u: "254700000001")

    await notify_payment_received(
        None, USER, order=ORDER, customer_name="Mary", customer_phone="254110400963",
        amount=3600, currency="KES",
    )
    assert [m["to"] for m in fake.sent] == ["254700000001"]


@pytest.mark.asyncio
async def test_a_customer_paying_themselves_is_not_sent_their_own_alert(wa):
    # The owner buying from their own shop should not get both messages.
    await notify_payment_received(
        None, USER, order=ORDER, customer_name="Sam", customer_phone="254700000001",
        amount=3600, currency="KES",
    )
    assert len(wa.sent) == 1


@pytest.mark.asyncio
async def test_a_claimed_manual_payment_reaches_the_owner(wa):
    await notify_payment_claimed(None, USER, order=ORDER, customer_name="Mary")
    assert len(wa.sent) == 1
    msg = wa.sent[0]["message"]
    assert "says they have paid" in msg
    assert "Not confirmed yet" in msg, "the owner must know this is unverified"
    assert wa.sent[0]["context"] == OWNER_ALERT_CONTEXT


@pytest.mark.asyncio
async def test_notifications_never_raise(monkeypatch):
    # A payment must be recorded even when nothing can be sent.
    import whatsapp_service

    def boom(db):
        raise RuntimeError("no whatsapp service")

    monkeypatch.setattr(whatsapp_service, "get_whatsapp_service", boom)
    await notify_payment_received(None, USER, order=ORDER, customer_name="M",
                                  customer_phone="2547", amount=1, currency="KES")
    await notify_payment_claimed(None, USER, order=ORDER, customer_name="M")


def test_alerts_are_templated_so_they_cost_one_message():
    from ai_service import AI_GENERATED_CONTEXTS

    assert RECEIPT_CONTEXT not in AI_GENERATED_CONTEXTS
    assert OWNER_ALERT_CONTEXT not in AI_GENERATED_CONTEXTS


@pytest.mark.asyncio
async def test_the_owner_is_recognised_however_their_number_is_written(monkeypatch):
    # Stored as +254700000001 in one place and 254700000001 in another.
    fake = FakeWA()
    import whatsapp_service

    monkeypatch.setattr(whatsapp_service, "get_whatsapp_service", lambda db: fake)
    monkeypatch.setattr(whatsapp_service, "owner_whatsapp_number", lambda u: "254700000001")

    await notify_payment_received(
        None, USER, order=ORDER, customer_name="Sam",
        customer_phone="+254 700 000 001", amount=3600, currency="KES",
    )
    assert len(fake.sent) == 1, "the owner must not be sent their own receipt twice"

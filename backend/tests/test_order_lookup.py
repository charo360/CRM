"""Coverage for recognising the order a customer is asking about.

From a real conversation: a buyer arrived from the storefront with the
number already typed —

    "Hi Lex, I just placed order ZILO-260909-F20D94 on your shop."

— and the AI replied "let me flag this to the team so they can check on it",
for an order sitting in the database with its items, total and payment
status. The customer did everything right and was put in a queue.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from order_lookup import (  # noqa: E402
    describe_order,
    find_referenced_order,
    is_unpaid,
    referenced_order_numbers,
)

ORDER = {
    "order_number": "ZILO-260909-F20D94",
    "user_id": "u1",
    "customer_id": "c1",
    "total_amount": 3600,
    "currency": "KES",
    "payment_status": "pending",
    "items": [{"quantity": 3, "product_name": "Cotton T-shirt"}],
}


class FakeOrders:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    async def find_one(self, query, sort=None):
        self.queries.append(query)
        for row in self.rows:
            if all(row.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return row
        return None


class FakeDB:
    def __init__(self, rows):
        self.orders = FakeOrders(rows)


# ── spotting the number ──────────────────────────────────────────────────

def test_the_storefront_message_is_recognised():
    msg = "Hi Lex, I just placed order ZILO-260909-F20D94 on your shop."
    assert referenced_order_numbers(msg) == ["ZILO-260909-F20D94"]


def test_a_chat_order_number_is_recognised_in_any_case():
    assert referenced_order_numbers("whats up with ord-a1b2c3") == ["ORD-A1B2C3"]


def test_ordinary_shopping_talk_is_not_mistaken_for_an_order():
    for msg in ("Niaje, bei ya hoodie?", "I want to order 2 shirts", "", "ORDER"):
        assert referenced_order_numbers(msg) == [], msg


@pytest.mark.asyncio
async def test_the_named_order_is_found():
    db = FakeDB([ORDER])
    found = await find_referenced_order(db, "u1", "c1", "about ZILO-260909-F20D94 please")
    assert found["order_number"] == "ZILO-260909-F20D94"


@pytest.mark.asyncio
async def test_asking_vaguely_falls_back_to_their_latest_order():
    db = FakeDB([ORDER])
    found = await find_referenced_order(db, "u1", "c1", "any update on my order?")
    assert found is not None


@pytest.mark.asyncio
async def test_an_unrelated_message_looks_nothing_up():
    db = FakeDB([ORDER])
    assert await find_referenced_order(db, "u1", "c1", "do you have hoodies?") is None
    assert db.orders.queries == []


@pytest.mark.asyncio
async def test_a_database_failure_never_costs_the_customer_their_reply():
    class Broken:
        orders = type("O", (), {"find_one": staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))})()

    assert await find_referenced_order(Broken(), "u1", "c1", "ZILO-260909-F20D94") is None


# ── what the model is told ───────────────────────────────────────────────

def test_an_unpaid_order_with_a_link_tells_it_to_finish_the_sale():
    text = describe_order(ORDER, "https://checkout.paystack.com/abc")
    assert "NOT PAID YET" in text
    assert "https://checkout.paystack.com/abc" in text
    assert "3x Cotton T-shirt" in text
    assert "do not ask the team" in text.lower()


def test_an_unpaid_order_without_a_link_still_refuses_to_escalate():
    text = describe_order(ORDER, None)
    assert "manually" in text
    assert "Do not escalate to a team." in text


def test_a_paid_order_is_never_asked_to_pay_again():
    text = describe_order({**ORDER, "payment_status": "paid"}, None)
    assert "Already paid" in text
    assert "Do not ask them to pay again." in text


def test_payment_status_reading():
    assert is_unpaid(ORDER)
    assert not is_unpaid({**ORDER, "payment_status": "PAID"})
    assert not is_unpaid({**ORDER, "payment_status": "refunded"})
    assert is_unpaid({})  # no status recorded means not yet paid

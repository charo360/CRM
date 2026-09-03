"""Tests for the public shop — the one part of Zilo a customer touches directly.

The rules covered here are the ones somebody notices when they break: which
link a shop gets and whether links already shared still answer, how much of a
catalog a lapsed trial may show, whether stock held by an abandoned payment
ever comes back, and whether a salon is asked to book rather than to add a
haircut to a cart.

Mongo is faked rather than mocked call by call, so each test reads as the
state before and the state after.
"""
from __future__ import annotations

import asyncio
import re
import sys
import types
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

# The module reaches for the payment providers at import time; the shop rules
# under test never call them.
for _name, _attrs in (
    ("paystack_credentials", {"paystack_connected": lambda user: False}),
    ("paystack_service", {"initialize_checkout_for_user": None}),
):
    if _name not in sys.modules:
        _module = types.ModuleType(_name)
        for _key, _value in _attrs.items():
            setattr(_module, _key, _value)
        sys.modules[_name] = _module

import storefront_routes as sf  # noqa: E402


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# A Mongo stand-in supporting only what these routes actually use.
# --------------------------------------------------------------------------

def _matches(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for field, expected in query.items():
        if field == "$or":
            if not any(_matches(doc, clause) for clause in expected):
                return False
            continue
        actual = doc.get(field)
        if isinstance(expected, dict):
            for operator, value in expected.items():
                if operator == "$ne" and actual == value:
                    return False
                if operator == "$in" and actual not in value:
                    return False
                if operator == "$nin" and actual in value:
                    return False
                if operator == "$lt" and not (actual is not None and actual < value):
                    return False
                if operator == "$gt" and not (actual is not None and actual > value):
                    return False
                if operator == "$gte" and not (actual is not None and actual >= value):
                    return False
                if operator == "$exists" and (actual is not None) != value:
                    return False
        elif isinstance(actual, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, docs: List[dict]):
        self._docs = docs

    def sort(self, field: str, direction: int = 1):
        self._docs = sorted(
            self._docs,
            key=lambda d: (d.get(field) is None, d.get(field)),
            reverse=direction < 0,
        )
        return self

    async def to_list(self, limit: int):
        return list(self._docs[:limit])


class FakeCollection:
    def __init__(self, docs: List[dict] | None = None):
        self.docs = docs if docs is not None else []

    async def find_one(self, query, projection=None):
        return next((d for d in self.docs if _matches(d, query)), None)

    def find(self, query, projection=None):
        return FakeCursor([d for d in self.docs if _matches(d, query)])

    async def insert_one(self, doc):
        self.docs.append(doc)

    async def update_one(self, query, update, upsert: bool = False):
        # Yield first so concurrent callers genuinely interleave, which is how
        # the "two backends" tests catch a lost update.
        await asyncio.sleep(0)
        for doc in self.docs:
            if not _matches(doc, query):
                continue
            doc.update(update.get("$set") or {})
            for field, amount in (update.get("$inc") or {}).items():
                doc[field] = (doc.get(field) or 0) + amount
            for field, value in (update.get("$addToSet") or {}).items():
                doc.setdefault(field, [])
                if value not in doc[field]:
                    doc[field].append(value)
            return types.SimpleNamespace(modified_count=1, matched_count=1)
        return types.SimpleNamespace(modified_count=0, matched_count=0)


class FakeDB:
    def __init__(self, users=None, products=None, orders=None, bookings=None, reports=None):
        self.users = FakeCollection(users or [])
        self.products = FakeCollection(products or [])
        self.orders = FakeCollection(orders or [])
        self.bookings = FakeCollection(bookings or [])
        self.customers = FakeCollection([])
        self.shop_reports = FakeCollection(reports or [])


def business(**overrides) -> dict:
    doc = {
        "_id": "biz-1",
        "business_name": "Corner Cafe",
        "public_store_slug": "corner-cafe",
        "currency": "USD",
    }
    doc.update(overrides)
    return doc


def product(pid="p1", owner="biz-1", **overrides) -> dict:
    doc = {
        "_id": pid,
        "user_id": owner,
        "name": "Latte",
        "price": 5.0,
        "in_stock": True,
        "images": [],
        "image_url": "",
        "created_at": datetime(2026, 1, 1),
    }
    doc.update(overrides)
    return doc


# --------------------------------------------------------------------------
# The shop's link
# --------------------------------------------------------------------------

def test_a_new_shop_takes_the_plain_business_name():
    shop = business(public_store_slug=None)
    db = FakeDB(users=[shop])
    assert run(sf._ensure_store_slug(db, shop)) == "corner-cafe"


def test_a_second_shop_of_the_same_name_gets_its_own_link():
    taken = business(_id="biz-1", public_store_slug="corner-cafe")
    newcomer = business(_id="biz-2", public_store_slug=None)
    db = FakeDB(users=[taken, newcomer])
    slug = run(sf._ensure_store_slug(db, newcomer))
    assert slug != "corner-cafe"
    assert slug.startswith("corner-cafe-")


def test_a_name_matching_a_zilo_page_cannot_take_that_link():
    # Shops sit at the site root, so "dashboard" would be unreachable.
    shop = business(business_name="Dashboard", public_store_slug=None)
    db = FakeDB(users=[shop])
    assert run(sf._ensure_store_slug(db, shop)) != "dashboard"


def test_an_old_suffixed_link_upgrades_but_still_answers():
    shop = business(public_store_slug="corner-cafe-a1b2c3")
    db = FakeDB(users=[shop])

    assert run(sf._ensure_store_slug(db, shop)) == "corner-cafe"
    # Anything a merchant already shared has to keep working.
    assert run(sf._business_doc(db, "corner-cafe-a1b2c3"))["_id"] == "biz-1"
    assert run(sf._business_doc(db, "corner-cafe"))["_id"] == "biz-1"


def test_the_notice_explains_a_link_that_is_not_the_business_name():
    shop = business()
    plain = run(sf._name_taken_notice(None, shop, "corner-cafe"))
    assert plain["name_taken"] is False

    fell_back = run(sf._name_taken_notice(None, shop, "corner-cafe-a1b2c3"))
    assert fell_back["name_taken"] is True
    assert fell_back["preferred_slug"] == "corner-cafe"


# --------------------------------------------------------------------------
# What a plan lets a shop show
# --------------------------------------------------------------------------

def _catalog_of(count: int, owner="biz-1") -> List[dict]:
    return [
        product(pid=f"p{i}", owner=owner, created_at=datetime(2026, 1, i + 1))
        for i in range(count)
    ]


def test_a_lapsed_trial_shows_only_the_free_allowance():
    lapsed = business(
        trial_started_at=datetime.utcnow() - timedelta(days=30),
        trial_ends_at=datetime.utcnow() - timedelta(days=16),
    )
    db = FakeDB(users=[lapsed], products=_catalog_of(12))
    assert len(run(sf._listable_products(db, lapsed))) == 5


def test_a_shop_inside_its_trial_shows_everything():
    trialling = business(
        trial_started_at=datetime.utcnow() - timedelta(days=2),
        trial_ends_at=datetime.utcnow() + timedelta(days=12),
    )
    db = FakeDB(users=[trialling], products=_catalog_of(12))
    assert len(run(sf._listable_products(db, trialling))) == 12


def test_a_paid_shop_shows_everything():
    paid = business(
        subscription_active=True,
        subscription_plan="standard",
        subscription_current_period_end=datetime.utcnow() + timedelta(days=20),
    )
    db = FakeDB(users=[paid], products=_catalog_of(12))
    assert len(run(sf._listable_products(db, paid))) == 12


# --------------------------------------------------------------------------
# Stock held by an unfinished payment
# --------------------------------------------------------------------------

def _reserved_order(oid: str, provider: str, minutes_old: int, status="Pending") -> dict:
    return {
        "_id": oid,
        "user_id": "biz-1",
        "created_by": "storefront",
        "stock_reserved": True,
        "payment_provider": provider,
        "payment_status": status,
        "created_at": datetime.utcnow() - timedelta(minutes=minutes_old),
        "items": [{"product_id": "p1", "quantity": 2, "product_name": "Latte"}],
    }


def test_an_abandoned_payment_gives_its_stock_back():
    stock = product(stock_quantity=3)
    db = FakeDB(products=[stock], orders=[_reserved_order("abandoned", "paystack", 60)])

    assert run(sf.release_expired_storefront_reservations(db)) == 1
    assert stock["stock_quantity"] == 5
    assert db.orders.docs[0]["payment_status"] == "Expired"


def test_a_cash_order_keeps_its_stock():
    # Not a pending payment — a commitment the merchant intends to fulfil.
    stock = product(stock_quantity=3)
    db = FakeDB(products=[stock], orders=[_reserved_order("cash", "manual", 60)])

    assert run(sf.release_expired_storefront_reservations(db)) == 0
    assert stock["stock_quantity"] == 3


def test_a_payment_still_in_progress_keeps_its_stock():
    stock = product(stock_quantity=3)
    db = FakeDB(products=[stock], orders=[_reserved_order("fresh", "paystack", 2)])

    assert run(sf.release_expired_storefront_reservations(db)) == 0
    assert stock["stock_quantity"] == 3


def test_two_backends_release_the_same_stock_only_once():
    stock = product(stock_quantity=5)
    db = FakeDB(products=[stock], orders=[_reserved_order("abandoned", "paystack", 60)])

    async def both():
        return await asyncio.gather(
            sf.release_expired_storefront_reservations(db),
            sf.release_expired_storefront_reservations(db),
        )

    assert sorted(run(both())) == [0, 1]
    assert stock["stock_quantity"] == 7, "stock was handed back twice"


# --------------------------------------------------------------------------
# Orders left unconfirmed
# --------------------------------------------------------------------------

def _waiting_order(oid: str, hours_old: int) -> dict:
    return {
        "_id": oid,
        "user_id": "biz-1",
        "created_by": "storefront",
        "status": "pending",
        "payment_status": "Pending",
        "customer_name": "Ada",
        "created_at": datetime.utcnow() - timedelta(hours=hours_old),
    }


def test_a_merchant_is_reminded_once_about_a_waiting_order(monkeypatch):
    pushes = _capture_pushes(monkeypatch)
    db = FakeDB(users=[business(push_token="tok")], orders=[_waiting_order("o1", 5)])

    assert run(sf.remind_unconfirmed_storefront_orders(db)) == 1
    assert len(pushes) == 1
    # And never again for the same order.
    assert run(sf.remind_unconfirmed_storefront_orders(db)) == 0
    assert len(pushes) == 1


def test_several_waiting_orders_are_one_reminder(monkeypatch):
    pushes = _capture_pushes(monkeypatch)
    db = FakeDB(
        users=[business(push_token="tok")],
        orders=[_waiting_order("o1", 5), _waiting_order("o2", 4), _waiting_order("o3", 3)],
    )

    assert run(sf.remind_unconfirmed_storefront_orders(db)) == 3
    assert len(pushes) == 1, "a busy shop should not get one push per order"


def test_two_backends_send_one_reminder(monkeypatch):
    pushes = _capture_pushes(monkeypatch)
    db = FakeDB(users=[business(push_token="tok")], orders=[_waiting_order("o1", 5)])

    async def both():
        return await asyncio.gather(
            sf.remind_unconfirmed_storefront_orders(db),
            sf.remind_unconfirmed_storefront_orders(db),
        )

    assert sorted(run(both())) == [0, 1]
    assert len(pushes) == 1, "the merchant was told twice about one order"


def _capture_pushes(monkeypatch):
    sent: List[dict] = []

    class _Service:
        async def send_notification(self, **kwargs):
            sent.append(kwargs)
            return True

    module = types.ModuleType("notification_service")
    module.get_notification_service = lambda: _Service()
    monkeypatch.setitem(sys.modules, "notification_service", module)
    return sent


# --------------------------------------------------------------------------
# Which kind of shop a business gets
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "business_type, expected_mode, expected_kind",
    [
        ("retail", "shop", None),
        ("wholesale", "shop", None),
        ("grocery", "shop", None),
        ("restaurant", "shop", None),
        ("bakery", "shop", None),
        ("creator", "shop", None),
        ("salon", "booking", "appointment"),
        ("spa", "booking", "appointment"),
        ("fitness", "booking", "appointment"),
        ("healthcare", "booking", "appointment"),
        ("repair", "booking", "appointment"),
        ("cleaning", "booking", "appointment"),
        ("events", "booking", "appointment"),
        ("hotel", "booking", "stay"),
        ("rental", "booking", "stay"),
        ("", "shop", None),
    ],
)
def test_each_business_type_gets_the_right_kind_of_link(business_type, expected_mode, expected_kind):
    mode = sf._shop_mode({"business_knowledge": {"business_type": business_type}})
    assert mode["mode"] == expected_mode
    assert mode["booking_kind"] == expected_kind


def test_a_restaurant_keeps_its_cart_and_can_also_hold_a_table():
    # Ordering and reserving are different jobs; one must not replace the other.
    mode = sf._shop_mode({"business_knowledge": {"business_type": "restaurant"}})
    assert mode["mode"] == "shop"
    assert mode["takes_table_bookings"] is True


@pytest.mark.parametrize(
    "business_type, word",
    [
        ("salon", "Appointment"),
        ("healthcare", "Appointment"),
        ("spa", "Appointment"),
        ("fitness", "Class"),
        ("hotel", "Reservation"),
        ("restaurant", "Reservation"),
        ("cleaning", "Booking"),
        ("rental", "Booking"),
        ("retail", "Booking"),
    ],
)
def test_a_trade_gets_its_own_word_for_a_booking(business_type, word):
    # A hotel says reservation and a clinic says appointment; the customer
    # should read the same word the merchant does.
    mode = sf._shop_mode({"business_knowledge": {"business_type": business_type}})
    assert mode["booking_label"] == word


def test_buyers_are_sent_to_the_number_that_is_on_whatsapp():
    # A business often signs up on one number and runs WhatsApp on another;
    # the button has to open the one somebody is actually watching.
    linked = {
        "phone_number": "+254700000000",
        "whatsapp": {"instance_name": "zilo_abc", "phone_number": "254733111222"},
    }
    assert sf._public_whatsapp(linked) == "254733111222"


def test_a_configured_whatsapp_number_beats_the_signup_one():
    configured = {
        "phone_number": "+254700000000",
        "settings": {"whatsapp_phone_number": "+254 733 999 888"},
        "whatsapp": {"instance_name": "zilo_abc"},
    }
    assert sf._public_whatsapp(configured) == "254733999888"


def test_the_signup_number_is_only_a_last_resort():
    only_signup = {"phone_number": "+254700000000", "whatsapp": {"instance_name": "zilo_abc"}}
    assert sf._public_whatsapp(only_signup) == "254700000000"


def test_no_button_at_all_until_whatsapp_is_linked():
    assert sf._public_whatsapp({"phone_number": "+254700000000"}) is None
    assert sf._public_whatsapp({"phone_number": "+254700000000", "whatsapp": {}}) is None


def test_the_shop_shows_the_hours_the_merchant_wrote():
    hours = "Tue-Sat 9am-6pm, closed Sunday"
    assert sf._opening_hours({"business_knowledge": {"business_hours": hours}}) == hours
    assert sf._opening_hours({}) == ""


def test_a_salon_is_not_offered_a_table():
    mode = sf._shop_mode({"business_knowledge": {"business_type": "salon"}})
    assert mode["takes_table_bookings"] is False


def test_a_plain_shop_is_not_offered_a_table():
    mode = sf._shop_mode({"business_knowledge": {"business_type": "retail"}})
    assert mode["takes_table_bookings"] is False


def test_the_type_comes_from_business_knowledge_not_the_signup_default():
    # settings.business_type is written once at sign-up as "retail" and never
    # updated; Business Knowledge is where the merchant actually chooses.
    switched = {
        "settings": {"business_type": "retail"},
        "business_knowledge": {"business_type": "salon"},
    }
    assert sf._shop_mode(switched)["mode"] == "booking"


# --------------------------------------------------------------------------
# Taking a booking
# --------------------------------------------------------------------------

def _booking_app(db):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    router = APIRouter(prefix="/api")
    sf.register_storefront_routes(router, db, lambda: {"_id": "biz-1"})
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _salon_db():
    salon = business(
        business_name="Glow Salon",
        public_store_slug="glow-salon",
        business_knowledge={"business_type": "salon"},
    )
    service = product(pid="s1", name="Haircut", price=25.0, duration=45)
    return FakeDB(users=[salon], products=[service]), salon


def _soon() -> str:
    return (datetime.utcnow() + timedelta(days=3)).date().isoformat()


def test_a_booking_is_stored_the_way_the_app_writes_one(monkeypatch):
    _capture_pushes(monkeypatch)
    db, _ = _salon_db()
    client = _booking_app(db)

    response = client.post(
        "/api/storefront/public/glow-salon/bookings",
        json={
            "service_id": "s1", "date": _soon(), "time": "14:30",
            "customer_name": "Ada", "phone": "+254700000000",
        },
    )
    assert response.status_code == 200

    stored = db.bookings.docs[0]
    assert stored["service_name"] == "Haircut"
    assert stored["time"] == "14:30"
    assert stored["end_time"] == "15:15", "end time should follow the service duration"
    assert stored["status"] == "pending"
    assert stored["payment_status"] == "unpaid"
    assert stored["source"] == "storefront"
    assert stored["booking_number"].startswith("BK-")


def test_a_booking_needs_a_real_date_and_time(monkeypatch):
    _capture_pushes(monkeypatch)
    db, _ = _salon_db()
    client = _booking_app(db)
    base = {"service_id": "s1", "customer_name": "Ada", "phone": "+254700000000"}

    assert client.post("/api/storefront/public/glow-salon/bookings",
                       json={**base, "date": "next tuesday", "time": "14:30"}).status_code == 400
    assert client.post("/api/storefront/public/glow-salon/bookings",
                       json={**base, "date": _soon()}).status_code == 400


def test_a_booking_cannot_name_a_service_the_shop_does_not_offer(monkeypatch):
    _capture_pushes(monkeypatch)
    db, _ = _salon_db()
    client = _booking_app(db)

    response = client.post(
        "/api/storefront/public/glow-salon/bookings",
        json={"service_id": "nope", "date": _soon(), "time": "14:30",
              "customer_name": "Ada", "phone": "+254700000000"},
    )
    assert response.status_code == 409


def test_a_shop_that_sells_goods_refuses_bookings(monkeypatch):
    _capture_pushes(monkeypatch)
    db = FakeDB(users=[business(business_knowledge={"business_type": "retail"})],
                products=[product()])
    client = _booking_app(db)

    response = client.post(
        "/api/storefront/public/corner-cafe/bookings",
        json={"service_id": "p1", "date": _soon(), "time": "14:30",
              "customer_name": "Ada", "phone": "+254700000000"},
    )
    assert response.status_code == 400


def _restaurant_db():
    place = business(
        business_name="Corner Cafe",
        business_knowledge={"business_type": "restaurant"},
    )
    return FakeDB(users=[place], products=[product()])


def test_a_restaurant_books_a_table_without_naming_a_dish(monkeypatch):
    _capture_pushes(monkeypatch)
    db = _restaurant_db()
    client = _booking_app(db)

    response = client.post(
        "/api/storefront/public/corner-cafe/bookings",
        json={"date": _soon(), "time": "19:00", "party_size": 4,
              "customer_name": "Ada", "phone": "+254700000000"},
    )
    assert response.status_code == 200

    stored = db.bookings.docs[0]
    assert stored["service_name"] == "Table booking"
    assert stored["service_id"] == "manual", "the app reads 'manual' for a booking with no catalog entry"
    assert stored["capacity"] == 4
    assert stored["total_price"] == 0.0


def test_a_table_needs_to_say_how_many_people(monkeypatch):
    _capture_pushes(monkeypatch)
    client = _booking_app(_restaurant_db())

    response = client.post(
        "/api/storefront/public/corner-cafe/bookings",
        json={"date": _soon(), "time": "19:00", "party_size": "a few",
              "customer_name": "Ada", "phone": "+254700000000"},
    )
    assert response.status_code == 400


def test_a_party_size_cannot_be_absurd(monkeypatch):
    _capture_pushes(monkeypatch)
    db = _restaurant_db()
    client = _booking_app(db)

    client.post(
        "/api/storefront/public/corner-cafe/bookings",
        json={"date": _soon(), "time": "19:00", "party_size": 9999,
              "customer_name": "Ada", "phone": "+254700000000"},
    )
    assert db.bookings.docs[0]["capacity"] == 50


def _bakery_db(advance_days=2):
    shop = business(
        business_name="Sweet Things",
        public_store_slug="sweet-things",
        business_knowledge={"business_type": "bakery", "bakery_advance_days": advance_days},
    )
    return FakeDB(users=[shop], products=[product(name="Birthday Cake", price=40.0)])


def _order_body(**extra):
    body = {"customer_name": "Ada", "phone": "+254700000000",
            "delivery_type": "pickup", "items": [{"product_id": "p1", "quantity": 1}]}
    body.update(extra)
    return body


def test_a_bakery_is_asked_when_the_order_is_wanted():
    mode = sf._shop_mode({"business_knowledge": {"business_type": "bakery",
                                                 "bakery_advance_days": 3}})
    assert mode["mode"] == "shop", "a bakery still sells from a cart"
    assert mode["needs_wanted_date"] is True
    assert mode["min_notice_days"] == 3


def test_other_shops_are_not_asked_for_a_date():
    mode = sf._shop_mode({"business_knowledge": {"business_type": "retail"}})
    assert mode["needs_wanted_date"] is False
    assert mode["min_notice_days"] == 0


def test_a_bakery_order_records_the_day_it_is_wanted(monkeypatch):
    _capture_pushes(monkeypatch)
    db = _bakery_db()
    client = _booking_app(db)
    wanted = (datetime.utcnow() + timedelta(days=5)).date().isoformat()

    response = client.post("/api/storefront/public/sweet-things/orders",
                           json=_order_body(wanted_date=wanted))
    assert response.status_code == 200
    assert db.orders.docs[0]["wanted_date"] == wanted


def test_a_bakery_order_must_say_which_day(monkeypatch):
    _capture_pushes(monkeypatch)
    client = _booking_app(_bakery_db())

    assert client.post("/api/storefront/public/sweet-things/orders",
                       json=_order_body()).status_code == 400


def test_a_bakery_will_not_take_an_order_inside_its_notice(monkeypatch):
    _capture_pushes(monkeypatch)
    client = _booking_app(_bakery_db(advance_days=3))
    tomorrow = (datetime.utcnow() + timedelta(days=1)).date().isoformat()

    response = client.post("/api/storefront/public/sweet-things/orders",
                           json=_order_body(wanted_date=tomorrow))
    assert response.status_code == 400
    assert "notice" in response.json()["detail"]


# --------------------------------------------------------------------------
# Reporting a shop
# --------------------------------------------------------------------------

def test_a_buyer_can_report_a_shop():
    db = FakeDB(users=[business()])
    client = _booking_app(db)

    response = client.post("/api/storefront/public/corner-cafe/report",
                           json={"reason": "scam", "detail": "took my money"})
    assert response.status_code == 200
    assert len(db.shop_reports.docs) == 1
    assert db.shop_reports.docs[0]["reviewed"] is False


def test_one_reporter_cannot_manufacture_a_pattern():
    db = FakeDB(users=[business()])
    client = _booking_app(db)

    client.post("/api/storefront/public/corner-cafe/report", json={"reason": "scam"})
    second = client.post("/api/storefront/public/corner-cafe/report", json={"reason": "scam"})

    # Answered the same way either time, so the cap cannot be probed.
    assert second.status_code == 200
    assert len(db.shop_reports.docs) == 1


def test_a_report_needs_a_reason_we_recognise():
    db = FakeDB(users=[business()])
    client = _booking_app(db)

    assert client.post("/api/storefront/public/corner-cafe/report",
                       json={"reason": "banana"}).status_code == 400


def test_reporting_an_unknown_shop_is_a_miss():
    db = FakeDB(users=[business()])
    client = _booking_app(db)

    assert client.post("/api/storefront/public/no-such-shop/report",
                       json={"reason": "scam"}).status_code == 404


# --------------------------------------------------------------------------
# The name a merchant is offered at sign-up
# --------------------------------------------------------------------------

def test_a_free_name_is_offered_with_the_link_it_will_give():
    db = FakeDB(users=[business()])
    client = _booking_app(db)

    body = client.get("/api/storefront/name-available", params={"name": "Jane's Boutique"}).json()
    assert body == {"slug": "jane-s-boutique", "available": True, "reason": ""}


@pytest.mark.parametrize(
    "name, reason",
    [("Corner Cafe", "taken"), ("Dashboard", "reserved"), ("ab", "invalid"), ("", "invalid")],
)
def test_a_name_that_cannot_be_used_says_why(name, reason):
    db = FakeDB(users=[business()])
    client = _booking_app(db)

    body = client.get("/api/storefront/name-available", params={"name": name}).json()
    assert body["available"] is False
    assert body["reason"] == reason

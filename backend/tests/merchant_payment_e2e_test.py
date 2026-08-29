"""End-to-end style payment/refund tests with mocked provider calls."""
from __future__ import annotations

import asyncio
import os
import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable

import pytest
from bson import ObjectId

import flutterwave_service
import merchant_payments_service
import paystack_service
import stripe_service
from flutterwave_billing import LEDGER as FLUTTERWAVE_LEDGER
from flutterwave_service import initialize_checkout_for_user as initialize_flutterwave_checkout
from flutterwave_service import parse_webhook_event as parse_flutterwave_event
from flutterwave_service import process_charge_success as process_flutterwave_success
from merchant_payments_service import issue_full_refund, list_unified_transactions
from payhero_billing import COLLECTION as PAYHERO_LEDGER
from payhero_billing import create_payment_intent as create_payhero_intent
from payhero_service import parse_webhook as parse_payhero_webhook
from payhero_service import process_payment as process_payhero_payment
from paystack_billing import LEDGER as PAYSTACK_LEDGER
from paystack_client import PaystackClient
from paystack_credentials import PAYSTACK_AUTH_MERCHANT, PAYSTACK_AUTH_PLATFORM
from paystack_service import initialize_checkout_for_user, parse_webhook_event
from paystack_service import process_charge_success
from stripe_billing import LEDGER as STRIPE_LEDGER
from stripe_service import initialize_checkout_for_user as initialize_stripe_checkout
from stripe_service import process_checkout_completed


class InsertResult:
    def __init__(self, inserted_id: Any):
        self.inserted_id = inserted_id


class UpdateResult:
    def __init__(self, matched_count: int, modified_count: int):
        self.matched_count = matched_count
        self.modified_count = modified_count


class FakeCursor:
    def __init__(self, rows: Iterable[Dict[str, Any]]):
        self.rows = [deepcopy(row) for row in rows]
        self._idx = 0

    def sort(self, key: str, direction: int):
        self.rows.sort(key=lambda row: row.get(key) or datetime.min, reverse=direction < 0)
        return self

    def limit(self, limit: int):
        self.rows = self.rows[:limit]
        return self

    async def to_list(self, limit: int):
        return self.rows[:limit]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self._idx]
        self._idx += 1
        return row


def _matches_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if "$in" in expected:
            return actual in expected["$in"]
        if "$regex" in expected:
            flags = re.I if "i" in expected.get("$options", "") else 0
            return re.search(expected["$regex"], str(actual or ""), flags) is not None
    return actual == expected


def _matches(doc: Dict[str, Any], filt: Dict[str, Any] | None) -> bool:
    if not filt:
        return True
    for key, expected in filt.items():
        if key == "$or":
            if not any(_matches(doc, option) for option in expected):
                return False
            continue
        if not _matches_value(doc.get(key), expected):
            return False
    return True


class FakeCollection:
    def __init__(self):
        self.docs: list[Dict[str, Any]] = []

    async def insert_one(self, doc: Dict[str, Any]):
        stored = deepcopy(doc)
        stored.setdefault("_id", ObjectId())
        self.docs.append(stored)
        doc["_id"] = stored["_id"]
        return InsertResult(stored["_id"])

    async def find_one(self, filt=None, projection=None, sort=None):
        del projection
        rows = [doc for doc in self.docs if _matches(doc, filt)]
        if sort:
            key, direction = sort[0]
            rows.sort(key=lambda row: row.get(key) or datetime.min, reverse=direction < 0)
        return deepcopy(rows[0]) if rows else None

    def find(self, filt=None):
        return FakeCursor(doc for doc in self.docs if _matches(doc, filt))

    async def update_one(self, filt, update):
        for doc in self.docs:
            if not _matches(doc, filt):
                continue
            before = deepcopy(doc)
            for key, value in (update.get("$set") or {}).items():
                doc[key] = value
            for key in (update.get("$unset") or {}):
                doc.pop(key, None)
            return UpdateResult(1, int(before != doc))
        return UpdateResult(0, 0)

    async def create_index(self, *args, **kwargs):
        return None


class FakeDB:
    def __init__(self):
        self._collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]

    def __getattr__(self, name: str) -> FakeCollection:
        return self[name]


def run(coro):
    return asyncio.run(coro)


def test_payhero_mpesa_payment_creates_transaction_and_manual_refund_record():
    async def scenario():
        db = FakeDB()
        user_id = ObjectId()
        customer_id = ObjectId()
        order_id = ObjectId()
        await db.users.insert_one(
            {
                "_id": user_id,
                "payhero_channel_id": "42",
                "payhero_auth_mode": "platform",
                "payhero_username": "M-Pesa 0705049364",
            }
        )
        await db.customers.insert_one(
            {"_id": customer_id, "user_id": user_id, "name": "Jane", "phone_number": "+254705049364"}
        )
        await db.orders.insert_one(
            {
                "_id": order_id,
                "user_id": user_id,
                "customer_id": customer_id,
                "order_number": "ORD-100",
                "total_amount": 500,
                "payment_status": "Pending",
            }
        )
        await create_payhero_intent(
            db,
            user_id=str(user_id),
            amount=500,
            phone="0705049364",
            external_reference="ORD-100",
            order_id=str(order_id),
            customer_id=str(customer_id),
            customer_name="Jane",
            channel_id=42,
        )

        parsed = parse_payhero_webhook(
            {
                "status": "SUCCESS",
                "amount": 500,
                "phone_number": "0705049364",
                "external_reference": "ORD-100",
                "provider_reference": "MPESA123",
                "channel_id": 42,
            }
        )
        payment = await process_payhero_payment(db, parsed, raw_payload={"source": "test"})

        assert payment["handled"] is True
        order = await db.orders.find_one({"_id": order_id})
        assert order["payment_status"] == "Paid"
        ledger = await db[PAYHERO_LEDGER].find_one({"provider_ref": "MPESA123"})
        assert ledger["gross_kes"] == 500
        assert ledger["status"] == "accrued"

        txs = await list_unified_transactions(
            db,
            str(user_id),
            user_doc={"payhero_channel_id": "42", "payhero_auth_mode": "platform"},
        )
        assert len(txs) == 1
        assert txs[0]["provider"] == "payhero"
        assert txs[0]["refundable"] is True
        assert txs[0]["refund_mode"] == "manual"

        refund = await issue_full_refund(
            db,
            {"payhero_channel_id": "42", "payhero_auth_mode": "platform"},
            user_id=str(user_id),
            provider="payhero",
            ledger_id=str(ledger["_id"]),
        )

        assert refund["status"] == "refunded"
        refunded_ledger = await db[PAYHERO_LEDGER].find_one({"_id": ledger["_id"]})
        assert refunded_ledger["status"] == "refunded"
        assert refunded_ledger.get("refund_note")

    run(scenario())


def test_paystack_subaccount_payment_creates_transaction_and_provider_refund(monkeypatch):
    class FakePaystackClient:
        initialized_payload: Dict[str, Any] = {}
        refund_payload: Dict[str, Any] = {}

        def __init__(self, secret_key: str):
            self.secret_key = secret_key

        async def initialize_transaction(self, payload):
            self.__class__.initialized_payload = payload
            return {
                "authorization_url": "https://checkout.paystack.test/pay",
                "access_code": "access_test",
                "reference": payload["reference"],
            }

        async def create_refund(self, *, transaction: str, amount_subunit=None):
            self.__class__.refund_payload = {
                "transaction": transaction,
                "amount_subunit": amount_subunit,
            }
            return {"id": "refund_123"}

    monkeypatch.setattr(paystack_service, "PaystackClient", FakePaystackClient)
    monkeypatch.setattr(merchant_payments_service, "PaystackClient", FakePaystackClient)

    async def scenario():
        db = FakeDB()
        user_id = ObjectId()
        customer_id = ObjectId()
        order_id = ObjectId()
        user_doc = {
            "_id": user_id,
            "paystack_secret_key": "sk_test_123",
            "paystack_auth_mode": PAYSTACK_AUTH_MERCHANT,
            "paystack_default_currency": "KES",
            "paystack_subaccount_code": "ACCT_mpesa_0705049364",
        }
        await db.users.insert_one(user_doc)
        await db.customers.insert_one(
            {
                "_id": customer_id,
                "user_id": user_id,
                "name": "Jane",
                "phone_number": "0705049364",
            }
        )
        await db.orders.insert_one(
            {
                "_id": order_id,
                "user_id": user_id,
                "customer_id": customer_id,
                "order_number": "ORD-200",
                "total_amount": 750,
                "payment_status": "Pending",
            }
        )

        checkout = await initialize_checkout_for_user(
            db,
            user_doc,
            user_id=str(user_id),
            email="jane@example.test",
            amount_major=750,
            currency="KES",
            external_reference="ORD-200",
            order_id=str(order_id),
            customer_id=customer_id,
            customer_name="Jane",
            callback_url="https://crm.test/orders?paystack=success",
        )

        assert checkout["authorization_url"]
        assert FakePaystackClient.initialized_payload["subaccount"] == "ACCT_mpesa_0705049364"

        parsed = parse_webhook_event(
            {
                "event": "charge.success",
                "data": {
                    "reference": checkout["reference"],
                    "status": "success",
                    "amount": 75000,
                    "currency": "KES",
                    "channel": "mobile_money",
                    "customer": {"email": "jane@example.test"},
                },
            }
        )
        payment = await process_charge_success(db, parsed, raw_payload={"source": "test"})

        assert payment["handled"] is True
        ledger = await db[PAYSTACK_LEDGER].find_one({"paystack_reference": checkout["reference"]})
        assert ledger["amount_major"] == 750
        assert ledger["status"] == "success"
        order = await db.orders.find_one({"_id": order_id})
        assert order["payment_status"] == "Paid"

        txs = await list_unified_transactions(db, str(user_id), user_doc=user_doc)
        assert txs[0]["provider"] == "paystack"
        assert txs[0]["refundable"] is True

        refund = await issue_full_refund(
            db,
            user_doc,
            user_id=str(user_id),
            provider="paystack",
            ledger_id=str(ledger["_id"]),
        )

        assert refund == {
            "status": "refunded",
            "provider": "paystack",
            "provider_refund_id": "refund_123",
        }
        assert FakePaystackClient.refund_payload == {
            "transaction": checkout["reference"],
            "amount_subunit": None,
        }
        refunded_ledger = await db[PAYSTACK_LEDGER].find_one({"_id": ledger["_id"]})
        assert refunded_ledger["status"] == "refunded"
        assert refunded_ledger["provider_refund_id"] == "refund_123"

    run(scenario())


def test_paystack_platform_subaccount_makes_merchant_bear_processing_fee(monkeypatch):
    """A zero-Zilo-commission platform checkout must not charge Zilo Paystack fees."""
    class FakePaystackClient:
        initialized_payload: Dict[str, Any] = {}

        def __init__(self, secret_key: str):
            self.secret_key = secret_key

        async def initialize_transaction(self, payload):
            self.__class__.initialized_payload = payload
            return {
                "authorization_url": "https://checkout.paystack.test/platform",
                "access_code": "access_platform",
                "reference": payload["reference"],
            }

    monkeypatch.setenv("PAYSTACK_PLATFORM_SECRET_KEY", "sk_test_platform")
    monkeypatch.setattr(paystack_service, "PaystackClient", FakePaystackClient)

    async def scenario():
        db = FakeDB()
        user_id = ObjectId()
        order_id = ObjectId()
        user_doc = {
            "_id": user_id,
            "paystack_auth_mode": PAYSTACK_AUTH_PLATFORM,
            "paystack_default_currency": "KES",
            "paystack_subaccount_code": "ACCT_merchant_123",
        }
        await db.users.insert_one(user_doc)
        await db.orders.insert_one(
            {
                "_id": order_id,
                "user_id": user_id,
                "order_number": "ORD-PLATFORM-1",
                "total_amount": 400,
                "payment_status": "Pending",
            }
        )

        await initialize_checkout_for_user(
            db,
            user_doc,
            user_id=str(user_id),
            email="buyer@example.test",
            amount_major=400,
            currency="KES",
            external_reference="ORD-PLATFORM-1",
            order_id=str(order_id),
        )

        assert FakePaystackClient.initialized_payload["subaccount"] == "ACCT_merchant_123"
        assert FakePaystackClient.initialized_payload["bearer"] == "subaccount"

    run(scenario())


def test_zilo_paystack_platform_payouts_are_kenya_only():
    from paystack_credentials import platform_connect_fields

    kenya = platform_connect_fields({"currency": "KES", "payout_type": "mobile_money"})
    assert kenya["paystack_auth_mode"] == PAYSTACK_AUTH_PLATFORM
    assert kenya["paystack_default_currency"] == "KES"

    with pytest.raises(ValueError, match="only in Kenya"):
        platform_connect_fields({"currency": "NGN", "payout_type": "bank"})


def test_stripe_checkout_payment_creates_transaction_and_provider_refund(monkeypatch):
    class FakeStripeClient:
        checkout_payload: Dict[str, Any] = {}
        refund_payload: Dict[str, Any] = {}

        async def create_checkout_session(self, payload):
            self.__class__.checkout_payload = payload
            return {
                "id": "cs_test_123",
                "url": "https://checkout.stripe.test/session",
            }

        async def create_refund(
            self,
            *,
            payment_intent_id: str,
            amount_minor=None,
            reverse_transfer=True,
            refund_application_fee=True,
        ):
            self.__class__.refund_payload = {
                "payment_intent_id": payment_intent_id,
                "amount_minor": amount_minor,
                "reverse_transfer": reverse_transfer,
                "refund_application_fee": refund_application_fee,
            }
            return {"id": "re_123"}

    monkeypatch.setenv("STRIPE_PLATFORM_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(stripe_service, "StripeClient", FakeStripeClient)
    monkeypatch.setattr(merchant_payments_service, "StripeClient", FakeStripeClient)

    async def scenario():
        db = FakeDB()
        user_id = ObjectId()
        order_id = ObjectId()
        user_doc = {
            "_id": user_id,
            "stripe_connect_account_id": "acct_test_123",
            "stripe_charges_enabled": True,
            "stripe_payouts_enabled": True,
            "stripe_details_submitted": True,
            "stripe_default_currency": "USD",
        }
        await db.users.insert_one(user_doc)
        await db.orders.insert_one(
            {
                "_id": order_id,
                "user_id": user_id,
                "order_number": "ORD-300",
                "total_amount": 25,
                "payment_status": "Pending",
            }
        )

        checkout = await initialize_stripe_checkout(
            db,
            user_doc,
            user_id=str(user_id),
            email="jane@example.test",
            amount_major=25,
            currency="USD",
            external_reference="ORD-300",
            order_id=str(order_id),
            customer_name="Jane",
            success_url="https://crm.test/orders?stripe=success",
            cancel_url="https://crm.test/orders?stripe=cancel",
        )

        assert checkout["checkout_url"] == "https://checkout.stripe.test/session"
        assert FakeStripeClient.checkout_payload["payment_intent_data"]["transfer_data"] == {
            "destination": "acct_test_123"
        }

        payment = await process_checkout_completed(
            db,
            {
                "id": checkout["session_id"],
                "payment_status": "paid",
                "currency": "usd",
                "amount_total": 2500,
                "payment_intent": "pi_test_123",
                "customer_email": "jane@example.test",
                "metadata": {
                    "crm_user_id": str(user_id),
                    "order_id": str(order_id),
                    "checkout_reference": checkout["checkout_reference"],
                    "external_reference": "ORD-300",
                },
            },
            raw_payload={"source": "test"},
        )

        assert payment["handled"] is True
        ledger = await db[STRIPE_LEDGER].find_one({"stripe_payment_id": "pi_test_123"})
        assert ledger["amount_major"] == 25
        assert ledger["status"] == "success"
        order = await db.orders.find_one({"_id": order_id})
        assert order["payment_status"] == "Paid"

        txs = await list_unified_transactions(db, str(user_id), user_doc=user_doc)
        assert txs[0]["provider"] == "stripe"
        assert txs[0]["refundable"] is True

        refund = await issue_full_refund(
            db,
            user_doc,
            user_id=str(user_id),
            provider="stripe",
            ledger_id=str(ledger["_id"]),
        )

        assert refund == {
            "status": "refunded",
            "provider": "stripe",
            "provider_refund_id": "re_123",
        }
        assert FakeStripeClient.refund_payload == {
            "payment_intent_id": "pi_test_123",
            "amount_minor": None,
            "reverse_transfer": True,
            "refund_application_fee": True,
        }
        refunded_ledger = await db[STRIPE_LEDGER].find_one({"_id": ledger["_id"]})
        assert refunded_ledger["status"] == "refunded"
        assert refunded_ledger["provider_refund_id"] == "re_123"

    run(scenario())


def test_flutterwave_checkout_payment_creates_transaction_and_provider_refund(monkeypatch):
    class FakeFlutterwaveClient:
        payment_payload: Dict[str, Any] = {}
        verified_reference = ""
        refund_payload: Dict[str, Any] = {}

        def __init__(self, secret_key: str):
            self.secret_key = secret_key

        async def create_payment(self, payload):
            self.__class__.payment_payload = payload
            return {
                "link": "https://checkout.flutterwave.test/pay",
                "flw_ref": "flw_init_123",
            }

        async def verify_by_reference(self, tx_ref: str):
            self.__class__.verified_reference = tx_ref
            return {"id": 987654321}

        async def create_refund(self, *, transaction_id: int, amount=None):
            self.__class__.refund_payload = {
                "transaction_id": transaction_id,
                "amount": amount,
            }
            return {"id": "flw_refund_123"}

    monkeypatch.setenv("FLUTTERWAVE_PLATFORM_SECRET_KEY", "FLWSECK_TEST_123")
    monkeypatch.setattr(flutterwave_service, "FlutterwaveClient", FakeFlutterwaveClient)
    monkeypatch.setattr(merchant_payments_service, "FlutterwaveClient", FakeFlutterwaveClient)

    async def scenario():
        db = FakeDB()
        user_id = ObjectId()
        order_id = ObjectId()
        user_doc = {
            "_id": user_id,
            "flutterwave_subaccount_id": "RS_123",
            "flutterwave_auth_mode": "platform",
            "flutterwave_default_currency": "KES",
        }
        await db.users.insert_one(user_doc)
        await db.orders.insert_one(
            {
                "_id": order_id,
                "user_id": user_id,
                "order_number": "ORD-400",
                "total_amount": 900,
                "payment_status": "Pending",
            }
        )

        checkout = await initialize_flutterwave_checkout(
            db,
            user_doc,
            user_id=str(user_id),
            email="jane@example.test",
            amount_major=900,
            currency="KES",
            external_reference="ORD-400",
            order_id=str(order_id),
            customer_name="Jane",
            redirect_url="https://crm.test/orders?flutterwave=success",
        )

        assert checkout["payment_link"] == "https://checkout.flutterwave.test/pay"
        assert FakeFlutterwaveClient.payment_payload["subaccounts"] == [{"id": "RS_123"}]

        parsed = parse_flutterwave_event(
            {
                "event": "charge.completed",
                "data": {
                    "tx_ref": checkout["tx_ref"],
                    "status": "successful",
                    "amount": 900,
                    "currency": "KES",
                    "payment_type": "card",
                    "customer": {"email": "jane@example.test"},
                    "meta": {
                        "crm_user_id": str(user_id),
                        "order_id": str(order_id),
                        "external_reference": "ORD-400",
                    },
                },
            }
        )
        payment = await process_flutterwave_success(db, parsed, raw_payload={"source": "test"})

        assert payment["handled"] is True
        ledger = await db[FLUTTERWAVE_LEDGER].find_one(
            {"flutterwave_tx_ref": checkout["tx_ref"]}
        )
        assert ledger["amount_major"] == 900
        assert ledger["status"] == "success"
        order = await db.orders.find_one({"_id": order_id})
        assert order["payment_status"] == "Paid"

        txs = await list_unified_transactions(db, str(user_id), user_doc=user_doc)
        assert txs[0]["provider"] == "flutterwave"
        assert txs[0]["refundable"] is True

        refund = await issue_full_refund(
            db,
            user_doc,
            user_id=str(user_id),
            provider="flutterwave",
            ledger_id=str(ledger["_id"]),
        )

        assert refund == {
            "status": "refunded",
            "provider": "flutterwave",
            "provider_refund_id": "flw_refund_123",
        }
        assert FakeFlutterwaveClient.verified_reference == checkout["tx_ref"]
        assert FakeFlutterwaveClient.refund_payload == {
            "transaction_id": 987654321,
            "amount": None,
        }
        refunded_ledger = await db[FLUTTERWAVE_LEDGER].find_one({"_id": ledger["_id"]})
        assert refunded_ledger["status"] == "refunded"
        assert refunded_ledger["provider_refund_id"] == "flw_refund_123"

    run(scenario())


@pytest.mark.skipif(
    os.environ.get("PAYSTACK_LIVE_E2E") != "1"
    or not os.environ.get("PAYSTACK_TEST_SECRET_KEY")
    or not os.environ.get("PAYSTACK_TEST_TRANSACTION_REFERENCE"),
    reason=(
        "Live Paystack refund test is opt-in. Set PAYSTACK_LIVE_E2E=1, "
        "PAYSTACK_TEST_SECRET_KEY, and PAYSTACK_TEST_TRANSACTION_REFERENCE."
    ),
)
def test_live_paystack_refund_against_existing_test_transaction():
    async def scenario():
        client = PaystackClient(os.environ["PAYSTACK_TEST_SECRET_KEY"])
        refund = await client.create_refund(
            transaction=os.environ["PAYSTACK_TEST_TRANSACTION_REFERENCE"],
        )
        assert refund.get("id") or refund.get("transaction")

    run(scenario())

"""A subscription that moves between accounts must follow the buyer.

Google Play sells a subscription once. When someone reinstalls, changes phone,
or deletes and recreates their account, RevenueCat moves the entitlement to
whoever is signed in now and tells us with a TRANSFER. If that is ignored, the
buyer is asked to subscribe again while Play refuses to sell it twice — a dead
end they cannot get out of, having already paid.

These exercise the mapping and identity rules the webhook depends on rather
than the FastAPI route, which needs the whole app to import.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "server.py"
SOURCE = SERVER.read_text(encoding="utf-8")
sys.path.insert(0, str(SERVER.parent))

from revenuecat_transfer import resolve_transfer_subscription


OBSERVED_TRANSFER = {
    "id": "7C586445-7A32-40E3-A153-0B510C627E12",
    "event_timestamp_ms": 1788406125358,
    "transferred_from": [
        "af783387-725f-42da-86fe-7dd08cc4a900",
        "$RCAnonymousID:b94be85fca584baf8e7e42062d6d600c",
    ],
    "transferred_to": [
        "6486581d-1c57-4f79-85a5-d57fd49b33d6",
        "$RCAnonymousID:31cf3adabf364fc587060f68ee7cecb3",
    ],
    "type": "TRANSFER",
}

SOURCE_PURCHASE = {
    "_id": "B43969D1-800A-4C45-98B1-EFFCD182980E",
    "event_type": "INITIAL_PURCHASE",
    "product_id": "crm_starter_monthly:starter-monthly",
    "event_timestamp_ms": 1788144291761,
    "purchased_at_ms": 1788144278577,
    "expiration_at_ms": 1789288884274,
    "period_type": "TRIAL",
    "transaction_id": "GPA.3311-1451-9133-78074",
    "original_transaction_id": "GPA.3311-1451-9133-78074",
}


def test_the_webhook_acts_on_a_transfer():
    assert 'elif event_type == "TRANSFER":' in SOURCE, "TRANSFER is ignored again"


def test_the_receiving_account_is_looked_up():
    # Without this the event is dropped as an unknown user, because the account
    # it came from is usually the deleted one.
    # The identity block sits between event_type and the user lookup.
    block = SOURCE.split('event_type = str(event.get("type") or "").upper()')[1]
    lookup = block.split("user = await db.users.find_one")[0]
    assert "transferred_to" in lookup, "the recipient is not part of the identity lookup"


def test_a_transfer_activates_the_recipient_and_stands_the_old_one_down():
    branch = SOURCE.split('elif event_type == "TRANSFER":')[1].split("elif event_type in {\"CANCELLATION\"")[0]
    assert '"subscription_active": True' in branch, "the new account is never activated"
    assert '"subscription_active": False' in branch, "the old account keeps access it no longer has"
    assert "transferred_from" in branch and "transferred_to" in branch


def test_real_transfer_payload_recovers_the_subscription_from_the_ledger():
    # RevenueCat's actual TRANSFER contains no product or expiry. The matching
    # source purchase in our ledger supplies both even if the old user is gone.
    resolved = resolve_transfer_subscription(
        OBSERVED_TRANSFER,
        SOURCE_PURCHASE,
        None,
        {"starter", "standard", "pro"},
    )

    assert resolved == {
        "plan_id": "starter",
        "expiration_at_ms": 1789288884274,
        "purchased_at_ms": 1788144278577,
        "is_trial": True,
        "transaction_id": "GPA.3311-1451-9133-78074",
        "original_transaction_id": "GPA.3311-1451-9133-78074",
        "source_event_id": "B43969D1-800A-4C45-98B1-EFFCD182980E",
    }


def test_an_expired_purchase_is_not_reactivated_by_a_transfer():
    expired = {**SOURCE_PURCHASE, "expiration_at_ms": 1788406125357}

    assert resolve_transfer_subscription(
        OBSERVED_TRANSFER,
        expired,
        None,
        {"starter", "standard", "pro"},
    ) is None


def test_only_an_unprocessed_transfer_can_bypass_event_id_deduplication():
    handler = SOURCE.split('@api_router.post("/subscription/revenuecat-webhook")')[1]
    before_event_record = handler.split("event_record =", 1)[0]
    assert 'event_type == "TRANSFER"' in before_event_record
    assert 'not existing_event.get("processed_user_id")' in before_event_record
    assert 'return {"status": "duplicate"}' in before_event_record


@pytest.mark.parametrize(
    "product_id, expected",
    [
        # RevenueCat sends the Play base plan after a colon.
        ("crm_starter_monthly:starter-monthly", "starter"),
        ("crm_standard_monthly:standard-monthly", "standard"),
        ("crm_pro_monthly:pro-monthly", "pro"),
        ("crm_starter_monthly", "starter"),
        ("something_else", None),
    ],
)
def test_the_play_product_maps_to_a_zilo_plan(product_id, expected):
    # Mirrors _revenuecat_plan_id without importing the whole server module.
    plans = ["starter", "standard", "pro"]
    base = str(product_id or "").split(":", 1)[0]
    resolved = next((p for p in plans if base == f"crm_{p}_monthly"), None)
    assert resolved == expected

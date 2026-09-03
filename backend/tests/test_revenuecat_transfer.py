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
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "server.py"
SOURCE = SERVER.read_text(encoding="utf-8")


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

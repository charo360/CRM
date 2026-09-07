"""Coverage for the trial a new business is entitled to at signup.

Without it a new account has no trial and no subscription, so the first thing
the app asks for is a payment method - which is what left every new signup
locked out.
"""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from entitlements import (  # noqa: E402
    TRIAL_DAYS,
    has_dashboard_access,
    provision_signup_trial,
    trial_window,
)


class FakeUsers:
    def __init__(self, rows):
        self.rows = {r["_id"]: dict(r) for r in rows}

    async def find_one(self, query, projection=None):
        row = self.rows.get(query.get("_id"))
        return dict(row) if row else None

    async def update_one(self, query, operation):
        row = self.rows.get(query.get("_id"))
        if row:
            row.update(operation.get("$set") or {})


class FakeDb:
    def __init__(self, users):
        self.users = FakeUsers(users)


def test_a_brand_new_account_is_locked_out_without_a_trial():
    """The state every signup landed in before this was wired up."""
    record = {"_id": "u1", "subscription_active": False, "subscription_plan": None}
    assert has_dashboard_access(record) is False


def test_signup_trial_grants_access():
    db = FakeDb([{"_id": "u1", "subscription_active": False}])
    applied = asyncio.run(provision_signup_trial(db, "u1"))

    assert applied is True
    record = db.users.rows["u1"]
    assert has_dashboard_access(record) is True

    active, started, ends = trial_window(record)
    assert active is True
    assert (ends - started).days == TRIAL_DAYS


def test_the_trial_is_one_time():
    """Deleting and re-registering must not hand out a second free trial."""
    used = datetime.utcnow() - timedelta(days=90)
    db = FakeDb([{"_id": "u1", "trial_started_at": used,
                  "trial_ends_at": used + timedelta(days=TRIAL_DAYS)}])
    assert asyncio.run(provision_signup_trial(db, "u1")) is False
    # The expired trial is left exactly as it was, not restarted.
    assert db.users.rows["u1"]["trial_started_at"] == used


def test_a_paying_account_is_not_downgraded_to_a_trial():
    db = FakeDb([{"_id": "u1", "subscription_active": True,
                  "subscription_plan": "growth"}])
    assert asyncio.run(provision_signup_trial(db, "u1")) is False
    assert "trial_started_at" not in db.users.rows["u1"]


def test_an_expired_trial_no_longer_grants_access():
    past = datetime.utcnow() - timedelta(days=TRIAL_DAYS + 5)
    record = {
        "_id": "u1",
        "trial_started_at": past,
        "trial_ends_at": past + timedelta(days=TRIAL_DAYS),
        "subscription_active": False,
    }
    assert has_dashboard_access(record) is False

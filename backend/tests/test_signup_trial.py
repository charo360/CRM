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
    TRIAL_GRANTS_COLLECTION,
    has_dashboard_access,
    provision_signup_trial,
    trial_claim_id,
    trial_window,
)


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = {r["_id"]: dict(r) for r in (rows or [])}

    async def find_one(self, query, projection=None):
        row = self.rows.get(query.get("_id"))
        return dict(row) if row else None

    async def update_one(self, query, operation, upsert=False):
        key = query.get("_id")
        row = self.rows.get(key)
        if row is None:
            if not upsert:
                return
            row = self.rows[key] = {"_id": key}
        row.update(operation.get("$set") or {})

    async def delete_one(self, query):
        self.rows.pop(query.get("_id"), None)


class FakeDb:
    def __init__(self, users):
        self.users = FakeCollection(users)
        self._extra = {}

    def __getitem__(self, name):
        if name == "users":
            return self.users
        return self._extra.setdefault(name, FakeCollection())


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


def test_a_trial_is_enough_to_connect_whatsapp():
    """The WhatsApp gates check dashboard_access, not paid_active.

    Requiring a card first meant a trial unlocked a CRM with no WhatsApp in
    it - the one thing the product is for.
    """
    started = datetime.utcnow()
    trial_only = {
        "_id": "u1",
        "trial_started_at": started,
        "trial_ends_at": started + timedelta(days=TRIAL_DAYS),
        "subscription_active": False,
        "subscription_plan": "trial",
    }
    assert has_dashboard_access(trial_only) is True


def test_whatsapp_closes_again_when_the_trial_runs_out():
    """Access has to end, or the gate is not a gate."""
    past = datetime.utcnow() - timedelta(days=TRIAL_DAYS + 1)
    expired = {
        "_id": "u1",
        "trial_started_at": past,
        "trial_ends_at": past + timedelta(days=TRIAL_DAYS),
        "subscription_active": False,
    }
    assert has_dashboard_access(expired) is False


# ── One trial per person, not per account ──────────────────────────────────

PHONE = "+16505553434"


def test_returning_mid_trial_resumes_with_the_days_that_were_left():
    """Delete on day two, come back on day three: eleven days remain.

    The trial is a window belonging to the person, not a token. Restarting it
    would hand out free time for a couple of taps; refusing outright would take
    back days they had not used.
    """
    two_days_ago = datetime.utcnow() - timedelta(days=2)
    db = FakeDb([{"_id": "first", "phone_number": PHONE}])
    db[TRIAL_GRANTS_COLLECTION].rows[trial_claim_id(PHONE)] = {
        "_id": trial_claim_id(PHONE),
        "trial_started_at": two_days_ago,
        "trial_ends_at": two_days_ago + timedelta(days=TRIAL_DAYS),
    }
    # The account was deleted; this is a new one on the same number.
    assert asyncio.run(provision_signup_trial(db, "first")) is True

    record = db.users.rows["first"]
    assert has_dashboard_access(record) is True
    # The clock kept running rather than restarting: same start, same deadline.
    assert record["trial_started_at"] == two_days_ago
    assert record["trial_ends_at"] == two_days_ago + timedelta(days=TRIAL_DAYS)


def test_signing_up_again_does_not_restart_the_clock():
    """The abuse path: a fresh fourteen days for anyone willing to tap twice."""
    db = FakeDb([{"_id": "first", "phone_number": PHONE}])
    assert asyncio.run(provision_signup_trial(db, "first")) is True
    first_end = db.users.rows["first"]["trial_ends_at"]

    db.users.rows.pop("first")
    db.users.rows["second"] = {"_id": "second", "phone_number": PHONE}
    assert asyncio.run(provision_signup_trial(db, "second")) is True

    # Same deadline as the original trial, not a new one.
    assert db.users.rows["second"]["trial_ends_at"] == first_end


def test_a_window_that_has_run_out_is_not_reopened():
    used = datetime.utcnow() - timedelta(days=TRIAL_DAYS + 3)
    db = FakeDb([{"_id": "u1", "phone_number": PHONE}])
    db[TRIAL_GRANTS_COLLECTION].rows[trial_claim_id(PHONE)] = {
        "_id": trial_claim_id(PHONE),
        "trial_started_at": used,
        "trial_ends_at": used + timedelta(days=TRIAL_DAYS),
    }
    assert asyncio.run(provision_signup_trial(db, "u1")) is False
    assert "trial_started_at" not in db.users.rows["u1"]


def test_the_claim_survives_deletion_of_everything_else():
    db = FakeDb([{"_id": "u1", "phone_number": PHONE}])
    asyncio.run(provision_signup_trial(db, "u1"))
    # Account deletion clears user data; the claim is deliberately not part of it.
    db.users.rows.clear()
    assert len(db[TRIAL_GRANTS_COLLECTION].rows) == 1


def test_the_claim_does_not_store_the_phone_number():
    """Deletion has to really delete, so the claim keeps only a hash."""
    db = FakeDb([{"_id": "u1", "phone_number": PHONE}])
    asyncio.run(provision_signup_trial(db, "u1"))

    stored = str(db[TRIAL_GRANTS_COLLECTION].rows)
    assert PHONE not in stored
    assert "6505553434" not in stored


def test_the_same_number_written_differently_is_the_same_person():
    assert trial_claim_id("+1 650-555-3434") == trial_claim_id("16505553434")
    assert trial_claim_id("+16505553434") == trial_claim_id("1 (650) 555 3434")
    assert trial_claim_id("+16505553434") != trial_claim_id("+16505553435")


def test_a_different_person_still_gets_their_trial():
    db = FakeDb([
        {"_id": "u1", "phone_number": PHONE},
        {"_id": "u2", "phone_number": "+254712345678"},
    ])
    assert asyncio.run(provision_signup_trial(db, "u1")) is True
    assert asyncio.run(provision_signup_trial(db, "u2")) is True


def test_an_account_with_no_usable_number_is_not_refused():
    """A missing number must not cost someone their trial."""
    db = FakeDb([{"_id": "u1", "phone_number": ""}])
    assert asyncio.run(provision_signup_trial(db, "u1")) is True
    assert db[TRIAL_GRANTS_COLLECTION].rows == {}

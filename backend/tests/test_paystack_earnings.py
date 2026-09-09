"""Coverage for what a business has earned versus what has reached them.

Two numbers people routinely confuse. Our ledger knows what customers paid;
only Paystack knows what it has actually paid out. The gap is money the
business has earned and cannot yet spend, and it is the whole reason for
this screen.

The rule that matters most here: when Paystack will not tell us what it has
settled, say so. "Nothing settled yet" and "we could not ask" look identical
to a worried owner, and only one of them is a reason to contact support.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paystack_earnings as pe  # noqa: E402
from paystack_earnings import earnings_summary, recent_transactions  # noqa: E402


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def __aiter__(self):
        async def gen():
            for row in self.rows:
                yield row
        return gen()


class FakeColl:
    def __init__(self, agg=None, docs=None):
        self._agg = agg or []
        self._docs = docs or []

    def aggregate(self, pipeline):
        return FakeCursor(self._agg)

    def find(self, *a, **k):
        return FakeCursor(self._docs)


class FakeDB:
    def __init__(self, agg=None, docs=None):
        self.coll = FakeColl(agg, docs)

    def __getitem__(self, name):
        return self.coll


USER = {"_id": "u1", "paystack_subaccount_code": "ACCT_x"}


@pytest.mark.asyncio
async def test_received_and_settled_produce_the_held_figure(monkeypatch):
    db = FakeDB(agg=[{"_id": "KES", "count": 3, "amount": 9000.0}])

    async def settled(user):
        return {"KES": 6000.0}

    monkeypatch.setattr(pe, "_settled", settled)
    out = await earnings_summary(db, USER)
    row = out["currencies"][0]
    assert out["settlement_data"] is True
    assert row == {"currency": "KES", "payments": 3, "received": 9000.0,
                   "settled": 6000.0, "held": 3000.0}


@pytest.mark.asyncio
async def test_when_paystack_will_not_say_we_do_not_invent_a_split(monkeypatch):
    db = FakeDB(agg=[{"_id": "KES", "count": 3, "amount": 9000.0}])

    async def settled(user):
        return None

    monkeypatch.setattr(pe, "_settled", settled)
    out = await earnings_summary(db, USER)
    row = out["currencies"][0]
    assert out["settlement_data"] is False
    assert row["received"] == 9000.0
    # Absent, not zero: showing "settled 0" would be a claim we cannot make.
    assert "settled" not in row
    assert "held" not in row


@pytest.mark.asyncio
async def test_a_settlement_larger_than_our_ledger_never_shows_a_negative(monkeypatch):
    # A webhook we missed means Paystack settled more than we recorded. A
    # minus sign on "still held" reads as a bug, or a debt.
    db = FakeDB(agg=[{"_id": "KES", "count": 1, "amount": 1000.0}])

    async def settled(user):
        return {"KES": 2500.0}

    monkeypatch.setattr(pe, "_settled", settled)
    row = (await earnings_summary(db, USER))["currencies"][0]
    assert row["held"] == 0.0


@pytest.mark.asyncio
async def test_several_currencies_are_kept_apart(monkeypatch):
    db = FakeDB(agg=[{"_id": "KES", "count": 2, "amount": 5000.0},
                     {"_id": "USD", "count": 1, "amount": 40.0}])

    async def settled(user):
        return {"KES": 5000.0}

    monkeypatch.setattr(pe, "_settled", settled)
    rows = {r["currency"]: r for r in (await earnings_summary(db, USER))["currencies"]}
    assert rows["KES"]["held"] == 0.0
    assert rows["USD"]["held"] == 40.0, "an unsettled currency is still held"


@pytest.mark.asyncio
async def test_a_business_with_no_payments_yet_reports_cleanly(monkeypatch):
    async def settled(user):
        return {}

    monkeypatch.setattr(pe, "_settled", settled)
    out = await earnings_summary(FakeDB(agg=[]), USER)
    assert out["currencies"] == []
    assert out["connected"] is True


@pytest.mark.asyncio
async def test_transactions_carry_what_the_screen_needs():
    db = FakeDB(docs=[{"paystack_reference": "ref1", "amount_major": 2500,
                       "currency": "KES", "status": "success", "channel": "mobile_money",
                       "customer_email": "m@x.com", "order_id": "o1"}])
    rows = await recent_transactions(db, USER)
    assert rows[0]["reference"] == "ref1"
    assert rows[0]["amount"] == 2500
    assert rows[0]["status"] == "success"


@pytest.mark.asyncio
async def test_a_refund_is_shown_as_refunded_not_success():
    db = FakeDB(docs=[{"paystack_reference": "r", "amount_major": 100, "currency": "KES",
                       "status": "success", "refunded": True}])
    rows = await recent_transactions(db, USER)
    assert rows[0]["status"] == "refunded"


@pytest.mark.asyncio
async def test_settlement_failure_is_reported_as_unknown_not_zero(monkeypatch):
    # The real failure mode: Paystack errors, or the key is rejected.
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("Invalid key")

    monkeypatch.setattr(pe, "_settled", pe._settled)
    import paystack_client

    monkeypatch.setattr(paystack_client, "PaystackClient", Boom)
    assert await pe._settled({"_id": "u1", "paystack_secret_key": "sk_x"}) is None


@pytest.mark.asyncio
async def test_only_successful_settlements_count_as_paid_out(monkeypatch):
    # Paystack's statuses are success, processing, pending and failed. Only
    # success has reached the business; the rest are still in flight and
    # belong in "still held", not in "paid out to you".
    class Client:
        def __init__(self, *a, **k):
            pass

        async def list_settlements(self, **k):
            return [
                {"status": "success", "currency": "KES", "total_amount": 500000,
                 "effective_amount": 492500, "total_fees": 7500},
                {"status": "processing", "currency": "KES", "total_amount": 300000,
                 "effective_amount": 295000},
                {"status": "pending", "currency": "KES", "total_amount": 100000,
                 "effective_amount": 98000},
                {"status": "failed", "currency": "KES", "total_amount": 50000,
                 "effective_amount": 0},
            ]

    import paystack_client
    import paystack_auth

    monkeypatch.setattr(paystack_client, "PaystackClient", Client)
    monkeypatch.setattr(paystack_auth, "secret_key_from_doc", lambda u: "sk_x")

    # 492,500 subunits = KES 4,925 — net of fees, not the KES 5,000 gross.
    assert await pe._settled({"_id": "u1"}) == {"KES": 4925.0}


@pytest.mark.asyncio
async def test_the_amount_shown_is_what_lands_not_the_gross(monkeypatch):
    # total_amount is before total_fees. Showing the gross would tell a
    # business it had been paid more than its bank will ever show.
    class Client:
        def __init__(self, *a, **k):
            pass

        async def list_settlements(self, **k):
            return [{"status": "success", "currency": "KES",
                     "total_amount": 100000, "effective_amount": 97000}]

    import paystack_client
    import paystack_auth

    monkeypatch.setattr(paystack_client, "PaystackClient", Client)
    monkeypatch.setattr(paystack_auth, "secret_key_from_doc", lambda u: "sk_x")
    assert await pe._settled({"_id": "u1"}) == {"KES": 970.0}


@pytest.mark.asyncio
async def test_a_settlement_without_effective_amount_falls_back_to_total(monkeypatch):
    class Client:
        def __init__(self, *a, **k):
            pass

        async def list_settlements(self, **k):
            return [{"status": "success", "currency": "KES", "total_amount": 250000}]

    import paystack_client
    import paystack_auth

    monkeypatch.setattr(paystack_client, "PaystackClient", Client)
    monkeypatch.setattr(paystack_auth, "secret_key_from_doc", lambda u: "sk_x")
    assert await pe._settled({"_id": "u1"}) == {"KES": 2500.0}

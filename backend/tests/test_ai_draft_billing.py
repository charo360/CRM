"""Writing with AI is charged, and both counters know about it.

A broadcast draft has no send of its own to carry a charge. The broadcast costs
one per recipient however it was written, so drafting on an expensive model was
free and could be repeated all day -- each press being a real API call.

It is not charged through db.messages. One press produces one piece of text
that may go to four hundred people or to nobody, and inventing a message that
was never sent would corrupt delivery statistics, exports, and anything else
that counts what the business has actually sent. So the charges have their own
ledger, and both usage counters add it in.

Both. entitlements.count_monthly_outbound and
plan_enforcement.get_monthly_message_count are separate answers to the same
question and have disagreed before -- one excluded provider-rejected sends and
the other did not, so the same month billed differently depending on which was
asked. A source of usage only one of them knows about is that bug again.
"""
import ast
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import ai_draft_billing  # noqa: E402
from ai_service import MODEL_MESSAGE_COST  # noqa: E402


# ------------------------------------------------------- a tiny fake Mongo

class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("_id")})()

    def aggregate(self, pipeline):
        match = next((s["$match"] for s in pipeline if "$match" in s), {})
        since = (match.get("created_at") or {}).get("$gte")
        uid = match.get("user_id")
        rows = [d for d in self.docs
                if d.get("user_id") == uid
                and (since is None or d.get("created_at") >= since)]
        if not rows:
            return FakeCursor([])
        return FakeCursor([{"_id": None, "total": sum(d.get("cost", 1) for d in rows)}])


class FakeDB:
    def __init__(self):
        self._cols = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, FakeCollection())

    def __getattr__(self, name):
        return self[name]


@pytest.fixture
def db():
    return FakeDB()


LAST_MONTH = datetime.utcnow() - timedelta(days=45)
MONTH_START = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@pytest.mark.parametrize("model,expected", sorted(MODEL_MESSAGE_COST.items()))
def test_a_draft_costs_what_that_model_costs(db, model, expected):
    cost = asyncio.run(ai_draft_billing.charge_draft(db, "biz", model))
    assert cost == expected, f"{model} draft should cost {expected}"
    assert asyncio.run(
        ai_draft_billing.monthly_draft_cost(db, "biz", MONTH_START)) == expected


def test_charges_are_counted_per_business(db):
    asyncio.run(ai_draft_billing.charge_draft(db, "biz-a", "claude"))
    asyncio.run(ai_draft_billing.charge_draft(db, "biz-b", "standard"))
    a = asyncio.run(ai_draft_billing.monthly_draft_cost(db, "biz-a", MONTH_START))
    b = asyncio.run(ai_draft_billing.monthly_draft_cost(db, "biz-b", MONTH_START))
    assert (a, b) == (MODEL_MESSAGE_COST["claude"], MODEL_MESSAGE_COST["standard"]), (
        "one business's drafting must never land on another's allowance"
    )


def test_last_months_drafting_does_not_count_against_this_month(db):
    db[ai_draft_billing.COLLECTION].docs.append(
        {"user_id": "biz", "cost": 12, "created_at": LAST_MONTH})
    assert asyncio.run(
        ai_draft_billing.monthly_draft_cost(db, "biz", MONTH_START)) == 0


def test_a_ledger_failure_never_breaks_the_feature_it_measures(db):
    """Losing a charge beats losing the draft the owner asked for."""
    class Broken(FakeCollection):
        async def insert_one(self, doc):
            raise RuntimeError("mongo down")

        def aggregate(self, pipeline):
            raise RuntimeError("mongo down")

    db._cols[ai_draft_billing.COLLECTION] = Broken()
    assert asyncio.run(ai_draft_billing.charge_draft(db, "biz", "claude")) == 0
    assert asyncio.run(ai_draft_billing.monthly_draft_cost(db, "biz", MONTH_START)) == 0


# --------------------------------------------- both counters must agree

def _source(path, name):
    src = (BACKEND / path).read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found in {path}")


@pytest.mark.parametrize("path,fn", [
    ("entitlements.py", "count_monthly_outbound"),
    ("plan_enforcement.py", "get_monthly_message_count"),
])
def test_every_usage_counter_includes_draft_charges(path, fn):
    body = _source(path, fn)
    assert "monthly_draft_cost" in body, (
        f"{path}:{fn} does not count AI draft charges. The two counters would "
        "then answer the same question differently, which is a bug that has "
        "already happened once in this file's history."
    )


def test_the_endpoint_charges_after_generating_not_before():
    """A draft that failed to generate is not something to bill for."""
    body = _source("server.py", "generate_broadcast_message")
    charge_at = body.index("charge_draft(")
    # the call, not the import
    generate_at = body.index("draft_broadcast_message(")
    assert charge_at > generate_at, (
        "the charge must come after the model has answered, or a failed "
        "generation costs the owner messages for nothing"
    )
    assert "enforce_message_limit" in body, (
        "the allowance must be checked before calling the model, so someone "
        "who has run out is told plainly instead of being charged"
    )
    empty_guard = body.index("if not (generated_message")
    assert empty_guard < charge_at, (
        "an empty answer must be rejected before it is charged for"
    )

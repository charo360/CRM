"""The AI must never state a policy the business did not give it.

Deposits, check-in times and notice periods are promises about money and
access. A default that looks harmless in code becomes the business's own word
to a paying customer, and walking one back costs the merchant a refund
argument. So: say nothing unless the merchant said it.
"""
from __future__ import annotations

import asyncio
import re
import sys

import pytest

sys.path.insert(0, "backend") if "backend" not in sys.path[0] else None

from autoreply.context_loader import load_context  # noqa: E402
from autoreply.prompt_builder import build_system_prompt  # noqa: E402

# A percentage of money, or a time of day stated as fact.
ASSERTS_POLICY = re.compile(r"\d+% deposit|at \d{1,2}:\d{2}\s*(?:AM|PM)", re.I)


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, *a, **k): return self
    def limit(self, *a, **k): return self
    async def to_list(self, n=None): return self._docs


class _Collection:
    def __init__(self, docs=None): self.docs = docs or []
    def find(self, *a, **k): return _Cursor(self.docs)
    async def find_one(self, *a, **k): return self.docs[0] if self.docs else None
    async def count_documents(self, *a, **k): return len(self.docs)


class _DB:
    def __getattr__(self, name): return _Collection()


def _prompt_for(business_type: str, knowledge: dict | None = None) -> str:
    bk = {"business_type": business_type, **(knowledge or {})}
    user = {"_id": "b1", "business_name": "Test", "settings": {}, "business_knowledge": bk}
    ctx = asyncio.run(load_context(_DB(), "b1", "c1", user, "hello"))
    return build_system_prompt(ctx["business_config"], [], [], ctx.get("mini_state") or {})


@pytest.mark.parametrize("business_type", ["hotel", "rental", "spa", "events", "salon", "bakery"])
def test_an_unconfigured_business_promises_nothing(business_type):
    stated = ASSERTS_POLICY.findall(_prompt_for(business_type))
    assert not stated, f"{business_type} would tell customers: {stated}"


def test_a_hotel_that_set_its_policy_still_states_it():
    prompt = _prompt_for("hotel", {
        "hotel_checkin_time": "12:00 PM",
        "hotel_checkout_time": "10:00 AM",
        "hotel_deposit_required": True,
        "hotel_deposit_pct": 20,
    })
    assert "20% deposit" in prompt
    assert "12:00 PM" in prompt and "10:00 AM" in prompt


def test_an_events_business_that_wants_a_deposit_still_asks():
    prompt = _prompt_for("events", {"events_deposit_required": True, "events_deposit_pct": 40})
    assert "40% deposit" in prompt

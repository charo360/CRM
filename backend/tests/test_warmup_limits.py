"""A newly linked number fans out less until it has settled in.

Taking a number that was linked an hour ago and pushing a few hundred messages
through it is the shape of a throwaway bought for bulk sending, and the case
least likely to survive.

The important half of this is what it does NOT limit. Replying to somebody who
messaged first is the safest thing this product does. Counting replies against
a warm-up ceiling would silence the auto-reply on exactly the accounts that
just connected -- the live account this was built against had sent 43 messages
in a day, nearly all of them replies, against a first-day ceiling of 20.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from warmup_limits import (  # noqa: E402
    WARMUP_SCHEDULE, effective_daily_cap, warmup_daily_cap,
)

NOW = datetime(2026, 9, 10, 12, 0, 0)


def _linked(days_ago):
    return NOW - timedelta(days=days_ago)


def test_a_number_linked_today_sends_very_little():
    assert warmup_daily_cap(_linked(0), NOW) == WARMUP_SCHEDULE[0][1]
    assert warmup_daily_cap(_linked(0), NOW) <= 25, (
        "the first day should be a handful of messages, not a campaign"
    )


def test_the_allowance_grows_every_day():
    caps = [warmup_daily_cap(_linked(d), NOW) for d in range(len(WARMUP_SCHEDULE))]
    assert caps == sorted(caps), f"the ramp goes backwards: {caps}"
    assert len(set(caps)) == len(caps), "two days share a ceiling"


def test_an_established_number_is_not_limited_at_all():
    assert warmup_daily_cap(_linked(len(WARMUP_SCHEDULE)), NOW) is None
    assert warmup_daily_cap(_linked(90), NOW) is None


def test_the_warm_up_only_ever_lowers_the_cap():
    """A free plan on day six is still held to its own fifty."""
    for days in range(0, 10):
        assert effective_daily_cap(50, _linked(days), NOW) <= 50
        assert effective_daily_cap(2000, _linked(days), NOW) <= 2000


def test_an_unknown_link_date_is_not_treated_as_brand_new():
    """Accounts predating this field must not be throttled to twenty."""
    assert warmup_daily_cap(None, NOW) is None
    assert effective_daily_cap(500, None, NOW) == 500


def test_a_link_date_stored_as_text_still_works():
    assert warmup_daily_cap("2026-09-10T11:00:00", NOW) == WARMUP_SCHEDULE[0][1]
    assert warmup_daily_cap("not a date", NOW) is None


def test_a_timezone_aware_date_does_not_blow_up():
    aware = (NOW - timedelta(hours=2)).replace(tzinfo=timezone.utc)
    assert warmup_daily_cap(aware, NOW) == WARMUP_SCHEDULE[0][1]


def test_a_clock_skewed_future_date_is_treated_as_brand_new():
    assert warmup_daily_cap(NOW + timedelta(days=3), NOW) == WARMUP_SCHEDULE[0][1]


# ------------------------------------------- what it must never limit

def test_replies_are_not_fan_out():
    """The set decides whose sending is throttled. A reply must not be in it."""
    from whatsapp_service import BULK_SEND_CONTEXTS

    for reply_context in ("auto_reply", "fallback", "manual", "ai_draft",
                          "payment_receipt", "payment_confirmed",
                          "new_contact_alert", "storefront_order"):
        assert reply_context not in BULK_SEND_CONTEXTS, (
            f"{reply_context!r} is counted as fan-out, so a freshly connected "
            "number would stop answering the people messaging it"
        )
    assert "broadcast" in BULK_SEND_CONTEXTS


@pytest.mark.parametrize("path,fn", [("whatsapp_service.py", "send_message"),
                                     ("waha_service.py", "send_message")])
def test_both_senders_enforce_the_fan_out_ceiling(path, fn):
    import ast

    src = (BACKEND / path).read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(src)
    bodies = [ast.get_source_segment(src, n) or ""
              for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn]
    assert bodies, f"{fn} not found in {path}"
    assert any("bulk_remaining" in b for b in bodies), (
        f"{path}:{fn} does not check the warm-up ceiling, so a newly linked "
        "number can still fan out freely through it"
    )

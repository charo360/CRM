"""A newly linked WhatsApp number sends less until it has settled in.

The highest-risk thing this product can do is take a number that was linked an
hour ago and push a few hundred messages through it. That is the shape of a
throwaway number bought for bulk sending, and it is the case least likely to
survive. A number that has been in normal use for a week looks entirely
different to one that appeared this morning.

So the daily allowance ramps over the first week. This is a ceiling on top of
the plan's own daily cap, never a raise: a free plan on day six is still held
to its own fifty.
"""
from datetime import datetime, timedelta
from typing import Optional

# Days since the number was linked -> how many sends that day may carry.
# Deliberately gentle at the start: day one is a handful of messages, not a
# campaign.
WARMUP_SCHEDULE = (
    (1, 20),
    (2, 40),
    (3, 60),
    (4, 90),
    (5, 130),
    (6, 180),
    (7, 250),
)

# After this many days the number is treated as established and only the
# plan's own cap applies.
WARMUP_DAYS = len(WARMUP_SCHEDULE)


def warmup_daily_cap(connected_at, now: Optional[datetime] = None) -> Optional[int]:
    """The ceiling for a number linked at `connected_at`, or None if settled.

    None is also returned when the link date is unknown. An account whose
    connection predates this field is not a new number, and refusing to send
    for a missing timestamp would break every one of them.
    """
    if not connected_at:
        return None
    now = now or datetime.utcnow()

    if isinstance(connected_at, str):
        try:
            connected_at = datetime.fromisoformat(
                connected_at.replace("Z", "+00:00").replace("+00:00", "")
            )
        except ValueError:
            return None

    # Compare naively; both sides come from the same clock in practice, and a
    # tz-aware value here would otherwise raise rather than fall back.
    if getattr(connected_at, "tzinfo", None) is not None:
        connected_at = connected_at.replace(tzinfo=None)
    if getattr(now, "tzinfo", None) is not None:
        now = now.replace(tzinfo=None)

    age_days = (now - connected_at).total_seconds() / 86400.0
    if age_days < 0:
        # Clock skew, or a link recorded in the future. Treat as brand new.
        age_days = 0.0

    for day, cap in WARMUP_SCHEDULE:
        if age_days < day:
            return cap
    return None


def effective_daily_cap(plan_cap: int, connected_at, now: Optional[datetime] = None) -> int:
    """The smaller of the plan's daily cap and the warm-up ceiling."""
    warm = warmup_daily_cap(connected_at, now)
    if warm is None:
        return plan_cap
    return min(plan_cap, warm)


async def warmup_status(db, user: dict, plan_daily_cap: int,
                        now: Optional[datetime] = None) -> Optional[dict]:
    """What to tell the owner about their new number, or None once settled.

    An invisible limit is indistinguishable from a broken feature. Somebody
    whose broadcast stops at twenty needs to see that it is deliberate, that
    replies are unaffected, and that it goes up tomorrow -- otherwise the only
    signal is a send that halts for no stated reason.

    The extra query only runs while the ramp is actually on. Established
    accounts, which is nearly all of them, pay nothing for this.
    """
    now = now or datetime.utcnow()
    linked_at = ((user or {}).get("whatsapp") or {}).get("connected_at")
    cap = warmup_daily_cap(linked_at, now)
    if cap is None:
        return None

    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    business_id = user.get("business_id", user.get("_id"))
    try:
        from whatsapp_service import BULK_SEND_CONTEXTS
        sent_today = await db.messages.count_documents({
            "user_id": business_id,
            "direction": "outgoing",
            "send_context": {"$in": list(BULK_SEND_CONTEXTS)},
            "created_at": {"$gte": today},
        })
    except Exception:
        sent_today = 0

    effective = min(plan_daily_cap, cap)
    tomorrow = warmup_daily_cap(linked_at, now + timedelta(days=1))
    next_cap = plan_daily_cap if tomorrow is None else min(plan_daily_cap, tomorrow)

    # Days remaining before only the plan's own cap applies.
    days_left = 0
    for day, _ in WARMUP_SCHEDULE:
        if warmup_daily_cap(linked_at, now + timedelta(days=day)) is not None:
            days_left = day
    return {
        "active": True,
        "daily_limit": effective,
        "sent_today": sent_today,
        "remaining": max(0, effective - sent_today),
        "next_limit": next_cap,
        "full_limit": plan_daily_cap,
        "days_until_full": days_left + 1,
        # Said plainly, because this is what the owner sees.
        "reason": (
            "Your WhatsApp was connected recently. New numbers send fewer "
            "broadcasts at first so WhatsApp does not flag them. Replies to "
            "customers are not affected, and the limit rises every day."
        ),
    }

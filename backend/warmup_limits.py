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
from datetime import datetime
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

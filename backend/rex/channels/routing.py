"""
Urgency Routing — decides which channels receive an event based on its type.

Per REX.md §4.7:
- SMS is reserved for 'stop what you are doing' moments (URGENT only).
- Morning Briefings land on WhatsApp/Telegram/Email/In-App.
"""

from __future__ import annotations

from rex.channels.primitives import Channel, UrgencyLevel
from rex.ranks.events import EventType, TrustEvent


def route_event_to_channels(event: TrustEvent) -> tuple[Channel, ...]:
    """
    Map an incoming trust event to a list of target delivery channels
    based on its inherent urgency.
    """
    urgency = _urgency_for(event.type)

    if urgency is UrgencyLevel.URGENT:
        # Stop what you are doing — deliver everywhere including SMS immediately
        return (Channel.SMS, Channel.WHATSAPP, Channel.IN_APP)

    if urgency is UrgencyLevel.INTRADAY:
        # Deliver to dashboard + high detail email
        return (Channel.IN_APP, Channel.EMAIL)

    # DAILY (Morning briefings, etc.)
    return (Channel.WHATSAPP, Channel.TELEGRAM, Channel.EMAIL, Channel.IN_APP)


def _urgency_for(event_type: EventType) -> UrgencyLevel:
    # High-risk failures, unilateral demotions, or deal-killer indicators
    if event_type in {
        EventType.USER_DEMOTED_REX,
        EventType.REX_DEMOTED_SUBAGENT,
        EventType.ACTION_FLAGGED_MISTAKE,
        EventType.ACTION_UNDONE,
    }:
        return UrgencyLevel.URGENT

    # Standard approvals, promotions, or notifications
    if event_type in {
        EventType.USER_PROMOTED_REX,
        EventType.REX_RECOMMENDED_SUBAGENT_PROMOTION,
        EventType.USER_APPROVED_RECOMMENDATION,
        EventType.USER_DENIED_RECOMMENDATION,
        EventType.USER_DEFERRED_RECOMMENDATION,
        EventType.REX_LIFTED_PROBATION,
    }:
        return UrgencyLevel.INTRADAY

    return UrgencyLevel.DAILY

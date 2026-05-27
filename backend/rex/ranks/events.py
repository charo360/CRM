"""
TrustEvent — the append-only event types that drive the entire rank system.

REX.md §4 architecture insight: state is a function of events, not vice-versa.
Every event in this module is immutable, hashable, and self-contained. The
RankEngine in engine.py is the pure replay over a sequence of these.

THIRTEEN EVENT TYPES, grouped by purpose:

  Rank-changing — user→Rex (the only user-Rex axis):
    USER_PROMOTED_REX
    USER_DEMOTED_REX

  Rank-changing — Rex→Sub-Agent (asymmetric, see REX.md §4.5):
    REX_RECOMMENDED_SUBAGENT_PROMOTION     (pending — does not change rank)
    USER_APPROVED_RECOMMENDATION           (the gate that completes a promo)
    USER_DENIED_RECOMMENDATION             (closes the recommendation)
    USER_DEFERRED_RECOMMENDATION           (closes it for now)
    REX_DEMOTED_SUBAGENT                   (unilateral safety move)
    REX_LIFTED_PROBATION                   (closes a probation period)

  Operational — feed the trust score, never change rank directly:
    ACTION_APPROVED
    ACTION_REJECTED
    ACTION_UNDONE
    ACTION_CLEAN_SEND
    ACTION_FLAGGED_MISTAKE

Pure module. No I/O.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum


# ---------------------------------------------------------------------------
# Rank enum (IntEnum so we can compare with < and >)
# ---------------------------------------------------------------------------

class Rank(IntEnum):
    OBSERVER = 0
    DRAFTER = 1
    SENDER = 2
    OPERATOR = 3
    CHIEF_OF_STAFF = 4

    @property
    def display(self) -> str:
        return _RANK_DISPLAY[self]

    @classmethod
    def from_display(cls, s: str) -> "Rank":
        """Parse 'Observer', 'Chief of Staff', etc. Raises ValueError."""
        norm = s.strip().lower().replace("-", " ")
        for r in cls:
            if r.display.lower() == norm:
                return r
        raise ValueError(f"Unknown rank display: {s!r}")


_RANK_DISPLAY: dict[Rank, str] = {
    Rank.OBSERVER: "Observer",
    Rank.DRAFTER: "Drafter",
    Rank.SENDER: "Sender",
    Rank.OPERATOR: "Operator",
    Rank.CHIEF_OF_STAFF: "Chief of Staff",
}


# ---------------------------------------------------------------------------
# EventType discriminator
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    # User → Rex
    USER_PROMOTED_REX = "user_promoted_rex"
    USER_DEMOTED_REX = "user_demoted_rex"

    # Rex → Sub-Agent (multi-step promotion, unilateral demotion)
    REX_RECOMMENDED_SUBAGENT_PROMOTION = "rex_recommended_subagent_promotion"
    USER_APPROVED_RECOMMENDATION = "user_approved_recommendation"
    USER_DENIED_RECOMMENDATION = "user_denied_recommendation"
    USER_DEFERRED_RECOMMENDATION = "user_deferred_recommendation"
    REX_DEMOTED_SUBAGENT = "rex_demoted_subagent"
    REX_LIFTED_PROBATION = "rex_lifted_probation"

    # Operational events that feed the trust score
    ACTION_APPROVED = "action_approved"
    ACTION_REJECTED = "action_rejected"
    ACTION_UNDONE = "action_undone"
    ACTION_CLEAN_SEND = "action_clean_send"
    ACTION_FLAGGED_MISTAKE = "action_flagged_mistake"

    # Phase 8: Two-Sided Loyalty Team events
    FOUNDER_INVITED_TEAM_MEMBER = "founder_invited_team_member"
    FOUNDER_REVOKED_TEAM_MEMBER = "founder_revoked_team_member"


# Convenience sets used by the engine + tests.
RANK_CHANGING_EVENTS: frozenset[EventType] = frozenset({
    EventType.USER_PROMOTED_REX,
    EventType.USER_DEMOTED_REX,
    EventType.USER_APPROVED_RECOMMENDATION,
    EventType.REX_DEMOTED_SUBAGENT,
})

OPERATIONAL_EVENTS: frozenset[EventType] = frozenset({
    EventType.ACTION_APPROVED,
    EventType.ACTION_REJECTED,
    EventType.ACTION_UNDONE,
    EventType.ACTION_CLEAN_SEND,
    EventType.ACTION_FLAGGED_MISTAKE,
})

POSITIVE_OPERATIONAL: frozenset[EventType] = frozenset({
    EventType.ACTION_APPROVED,
    EventType.ACTION_CLEAN_SEND,
})

NEGATIVE_OPERATIONAL: frozenset[EventType] = frozenset({
    EventType.ACTION_REJECTED,
    EventType.ACTION_UNDONE,
    EventType.ACTION_FLAGGED_MISTAKE,
})


# ---------------------------------------------------------------------------
# TrustEvent
# ---------------------------------------------------------------------------

def new_event_id() -> str:
    """Globally unique event id. Stable across processes."""
    return uuid.uuid4().hex


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TrustEvent:
    """
    A single immutable entry in the trust event log.

    Fields that are not relevant for a given EventType are left None.
    Validation lives in `transitions.py` — *constructing* an event does not
    enforce semantic legality; *applying* it to the engine does.
    """
    id: str
    timestamp: datetime
    type: EventType

    # Who and where
    actor_name: str      # "Rex" or a Sub-Agent name
    category: str        # canonical Category name (e.g. "outreach")

    # Optional — populated only when meaningful for the event type:
    to_rank: Rank | None = None
    from_rank: Rank | None = None
    recommendation_id: str | None = None
    reason: str | None = None
    confidence: float | None = None

    # ----- constructors for each event type (clearer than naked __init__) ----

    @classmethod
    def user_promoted_rex(cls, *, category: str, to_rank: Rank, from_rank: Rank,
                          reason: str | None = None) -> "TrustEvent":
        return cls(
            id=new_event_id(), timestamp=_utc_now(),
            type=EventType.USER_PROMOTED_REX,
            actor_name="Rex", category=category,
            to_rank=to_rank, from_rank=from_rank, reason=reason,
        )

    @classmethod
    def user_demoted_rex(cls, *, category: str, to_rank: Rank, from_rank: Rank,
                         reason: str | None = None) -> "TrustEvent":
        return cls(
            id=new_event_id(), timestamp=_utc_now(),
            type=EventType.USER_DEMOTED_REX,
            actor_name="Rex", category=category,
            to_rank=to_rank, from_rank=from_rank, reason=reason,
        )

    @classmethod
    def rex_recommended_subagent_promotion(cls, *, subagent: str, category: str,
                                           to_rank: Rank, from_rank: Rank,
                                           reason: str, confidence: float,
                                           ) -> "TrustEvent":
        return cls(
            id=new_event_id(), timestamp=_utc_now(),
            type=EventType.REX_RECOMMENDED_SUBAGENT_PROMOTION,
            actor_name=subagent, category=category,
            to_rank=to_rank, from_rank=from_rank,
            reason=reason, confidence=confidence,
        )

    @classmethod
    def user_approved_recommendation(cls, *, subagent: str, category: str,
                                     to_rank: Rank, from_rank: Rank,
                                     recommendation_id: str) -> "TrustEvent":
        return cls(
            id=new_event_id(), timestamp=_utc_now(),
            type=EventType.USER_APPROVED_RECOMMENDATION,
            actor_name=subagent, category=category,
            to_rank=to_rank, from_rank=from_rank,
            recommendation_id=recommendation_id,
        )

    @classmethod
    def user_denied_recommendation(cls, *, subagent: str, category: str,
                                   recommendation_id: str,
                                   reason: str | None = None) -> "TrustEvent":
        return cls(
            id=new_event_id(), timestamp=_utc_now(),
            type=EventType.USER_DENIED_RECOMMENDATION,
            actor_name=subagent, category=category,
            recommendation_id=recommendation_id, reason=reason,
        )

    @classmethod
    def user_deferred_recommendation(cls, *, subagent: str, category: str,
                                     recommendation_id: str) -> "TrustEvent":
        return cls(
            id=new_event_id(), timestamp=_utc_now(),
            type=EventType.USER_DEFERRED_RECOMMENDATION,
            actor_name=subagent, category=category,
            recommendation_id=recommendation_id,
        )

    @classmethod
    def rex_demoted_subagent(cls, *, subagent: str, category: str,
                             to_rank: Rank, from_rank: Rank,
                             reason: str) -> "TrustEvent":
        return cls(
            id=new_event_id(), timestamp=_utc_now(),
            type=EventType.REX_DEMOTED_SUBAGENT,
            actor_name=subagent, category=category,
            to_rank=to_rank, from_rank=from_rank, reason=reason,
        )

    @classmethod
    def rex_lifted_probation(cls, *, actor_name: str, category: str,
                             reason: str | None = None) -> "TrustEvent":
        return cls(
            id=new_event_id(), timestamp=_utc_now(),
            type=EventType.REX_LIFTED_PROBATION,
            actor_name=actor_name, category=category, reason=reason,
        )

    # Operational --------------------------------------------------------

    @classmethod
    def operational(cls, *, type: EventType, actor_name: str, category: str,
                    confidence: float | None = None,
                    reason: str | None = None) -> "TrustEvent":
        if type not in OPERATIONAL_EVENTS:
            raise ValueError(f"{type} is not an operational event")
        return cls(
            id=new_event_id(), timestamp=_utc_now(), type=type,
            actor_name=actor_name, category=category,
            confidence=confidence, reason=reason,
        )

    # Team Events --------------------------------------------------------

    @classmethod
    def founder_invited_team_member(
        cls,
        *,
        principal_id: str,
        name: str,
        role: str,
        allowed_categories: tuple[str, ...] = (),
    ) -> "TrustEvent":
        """
        An event indicating the founder invited a new team member with specific permissions.
        We package the invited details inside the reason string or other fields.
        """
        cats_str = ",".join(allowed_categories)
        return cls(
            id=new_event_id(),
            timestamp=_utc_now(),
            type=EventType.FOUNDER_INVITED_TEAM_MEMBER,
            actor_name=name,
            category="team",
            reason=f"role:{role.lower()};cats:{cats_str};id:{principal_id}",
        )

    @classmethod
    def founder_revoked_team_member(
        cls,
        *,
        principal_id: str,
        name: str,
    ) -> "TrustEvent":
        """
        An event indicating the founder revoked access for a team member.
        """
        return cls(
            id=new_event_id(),
            timestamp=_utc_now(),
            type=EventType.FOUNDER_REVOKED_TEAM_MEMBER,
            actor_name=name,
            category="team",
            reason=f"id:{principal_id}",
        )

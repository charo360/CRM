"""
Recommendations — how Rex decides when to ask the user for a Sub-Agent promotion.

Per REX.md §4.5, Sub-Agents can only move up via user approval. Rex's job is
to *detect when an agent has earned the next rank* and compile a recommendation.
This module is the pure logic of "has Scout earned Sender on Leads yet?"

The trust score is computed from operational events:

    + ACTION_APPROVED            +1.0
    + ACTION_CLEAN_SEND          +0.8  (Rex sent autonomously, no user undo)
    - ACTION_REJECTED            -2.0
    - ACTION_UNDONE              -2.0
    - ACTION_FLAGGED_MISTAKE     -3.0  (a real screw-up)

Normalized to 0.0–1.0 over the last N events in the (actor, category) window.

Thresholds to recommend the NEXT rank:

    DRAFTER → SENDER         0.70 (with ≥10 events)
    SENDER → OPERATOR        0.85 (with ≥25 events)
    OPERATOR → CHIEF_OF_STAFF 0.95 (with ≥50 events)

OBSERVER → DRAFTER is automatic after first user-approved staged action
(Rex stops being a pure observer the moment he successfully proposes
something the user accepts).

A Sub-Agent on probation cannot be recommended for promotion until
probation lifts.

Pure module. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence
import uuid

from rex.ranks.events import (
    EventType,
    NEGATIVE_OPERATIONAL,
    OPERATIONAL_EVENTS,
    POSITIVE_OPERATIONAL,
    Rank,
    TrustEvent,
)
from rex.ranks.engine import RankEngine, Standing


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

class RecommendationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class Recommendation:
    """
    Rex's pitch to the user. This is the OBJECT shown on the Team page;
    when it's approved/denied/deferred, a TrustEvent of the corresponding
    type is emitted to the engine.
    """
    id: str
    subagent_name: str
    category: str
    from_rank: Rank
    to_rank: Rank
    reason: str                 # one-line Rex-voice reason (Phase 1 generates)
    supporting_stats: tuple[str, ...]  # short stat lines
    confidence: float           # 0.0-1.0, Rex's own confidence
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: RecommendationStatus = RecommendationStatus.PENDING


# ---------------------------------------------------------------------------
# Trust scoring
# ---------------------------------------------------------------------------

# Per-event weight contribution to the trust score.
_EVENT_WEIGHTS: dict[EventType, float] = {
    EventType.ACTION_APPROVED: +1.0,
    EventType.ACTION_CLEAN_SEND: +0.8,
    EventType.ACTION_REJECTED: -2.0,
    EventType.ACTION_UNDONE: -2.0,
    EventType.ACTION_FLAGGED_MISTAKE: -3.0,
}

# Window: only the last N operational events for the (actor, category) pair
# count toward the score. Keeps the score reactive to recent behavior.
_TRUST_WINDOW = 50

# How positive the recent record must be to recommend the next rank,
# and how many events must exist before we'll even consider it.
PROMOTION_THRESHOLDS: dict[Rank, tuple[float, int]] = {
    # target_rank: (min_score_in_0_to_1, min_event_count)
    Rank.DRAFTER: (0.50, 1),           # observer → drafter is light
    Rank.SENDER: (0.70, 10),
    Rank.OPERATOR: (0.85, 25),
    Rank.CHIEF_OF_STAFF: (0.95, 50),
}


def compute_trust_score(
    events: Sequence[TrustEvent],
    *,
    actor_name: str,
    category: str,
) -> tuple[float, int]:
    """
    Compute a (score, event_count) tuple for the (actor, category) window.

    Score is normalized to 0.0–1.0 where 1.0 means "every recent action was
    positive and clean". 0.0 means "every recent action was a failure".
    """
    relevant = [
        e for e in events
        if e.actor_name == actor_name
        and e.category == category
        and e.type in OPERATIONAL_EVENTS
    ]
    window = relevant[-_TRUST_WINDOW:]
    if not window:
        return (0.0, 0)

    # Each event contributes its weight. Score is the average weight
    # normalized so +1.0 maps to 1.0 and the worst -3.0 maps to 0.0.
    total = sum(_EVENT_WEIGHTS[e.type] for e in window)
    avg = total / len(window)

    # Normalize avg from range [-3.0, +1.0] to [0.0, 1.0].
    score = (avg - (-3.0)) / (1.0 - (-3.0))
    score = max(0.0, min(1.0, score))
    return (round(score, 3), len(window))


def _next_rank(current: Rank) -> Rank | None:
    """The next promotable rank, or None if already Chief of Staff."""
    return {
        Rank.OBSERVER: Rank.DRAFTER,
        Rank.DRAFTER: Rank.SENDER,
        Rank.SENDER: Rank.OPERATOR,
        Rank.OPERATOR: Rank.CHIEF_OF_STAFF,
    }.get(current)


# ---------------------------------------------------------------------------
# Recommendation proposal
# ---------------------------------------------------------------------------

def propose_promotion(
    events: Sequence[TrustEvent],
    *,
    engine: RankEngine,
    subagent_name: str,
    category: str,
) -> Recommendation | None:
    """
    If the Sub-Agent has earned the next rank in this Category, return a
    Recommendation. Otherwise return None.

    Caller is responsible for:
      - persisting the Recommendation to the user-facing inbox
      - emitting `REX_RECOMMENDED_SUBAGENT_PROMOTION` to the event store
        so the engine can chain a future USER_APPROVED_RECOMMENDATION.

    This function is pure — it does not mutate state.
    """
    current: Standing = engine.standing(subagent_name, category)

    # Probation blocks promotion until lifted.
    if current.on_probation:
        return None

    target = _next_rank(current.rank)
    if target is None:
        return None  # already Chief of Staff

    min_score, min_events = PROMOTION_THRESHOLDS[target]
    score, count = compute_trust_score(
        events, actor_name=subagent_name, category=category,
    )

    if count < min_events or score < min_score:
        return None

    # Compile supporting stats for the user-facing pitch.
    window = [
        e for e in events
        if e.actor_name == subagent_name
        and e.category == category
        and e.type in OPERATIONAL_EVENTS
    ][-_TRUST_WINDOW:]
    approved = sum(1 for e in window if e.type == EventType.ACTION_APPROVED)
    clean = sum(1 for e in window if e.type == EventType.ACTION_CLEAN_SEND)
    rejected = sum(1 for e in window if e.type == EventType.ACTION_REJECTED)
    undone = sum(1 for e in window if e.type == EventType.ACTION_UNDONE)

    stats = (
        f"{approved} approved, {clean} clean sends in last {count} events",
        f"{rejected} rejected, {undone} undone",
        f"Trust score: {score:.2f} (threshold {min_score:.2f})",
    )

    reason = (
        f"{subagent_name} earned {target.display} on {category}. "
        f"{approved + clean} positive vs {rejected + undone} negative in last "
        f"{count} events."
    )

    return Recommendation(
        id=uuid.uuid4().hex,
        subagent_name=subagent_name,
        category=category,
        from_rank=current.rank,
        to_rank=target,
        reason=reason,
        supporting_stats=stats,
        confidence=score,
    )

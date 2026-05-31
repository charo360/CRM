"""
rex.ranks — The Rank Engine, Trust Event store, and Recommendation generator.

Phase 2 of the Rex build. Like rex.persona, this is a pure module:
no DB writes, no LLM calls, no HTTP. The in-memory event store
implements a Protocol that will be swapped for a real persistence
layer in Phase 4.

PUBLIC API
==========
    Rank                Five-level enum (Observer → Chief of Staff).
    Category            Domain Rex operates in. Tier 1-8 from REX.md §6.
    Actor               Rex or a Sub-Agent.
    REX                 The Rex singleton actor.
    SUB_AGENTS          The registered Sub-Agent catalog.
    Standing            Current (actor, category) → (rank, probation).
    TrustEvent          Frozen append-only event. 13 types.
    EventType           The discriminator enum.
    EventStore          Protocol for storage. InMemoryEventStore is provided.
    RankEngine          Pure replay of events → state.
    Recommendation      Rex's pitch to the user for a Sub-Agent promotion.
    RecommendationStatus
    compute_trust_score Internal scoring from operational events.
    propose_promotion   Threshold detector returning a Recommendation or None.
    ProbationViolation  Raised when an event violates the trust chain.

INVARIANTS (enforced by transitions.py)
=======================================
    1. Only the user can promote Rex.
    2. A Sub-Agent's rank moves up ONLY via USER_APPROVED_RECOMMENDATION
       chained from a prior REX_RECOMMENDED_SUBAGENT_PROMOTION.
    3. Rex may demote a Sub-Agent unilaterally; no user gate.
    4. Demotion triggers automatic probation in that Category.
    5. Probation lifts only via REX_LIFTED_PROBATION, which requires a
       streak of clean operational events (configurable).
    6. State is always a pure function of the event log.
"""

from rex.ranks.categories import Category, Tier, all_categories, category_tier
from rex.ranks.actors import (
    Actor,
    ActorKind,
    REX,
    SUB_AGENTS,
    SubAgentSpec,
    actor_by_name,
)
from rex.ranks.events import (
    EventType,
    TrustEvent,
    Rank,
    new_event_id,
)
from rex.ranks.store import EventStore, InMemoryEventStore
from rex.ranks.engine import (
    Standing,
    RankEngine,
    ProbationViolation,
)
from rex.ranks.recommendations import (
    Recommendation,
    RecommendationStatus,
    compute_trust_score,
    propose_promotion,
    PROMOTION_THRESHOLDS,
)

__all__ = [
    "Category", "Tier", "all_categories", "category_tier",
    "Actor", "ActorKind", "REX", "SUB_AGENTS", "SubAgentSpec", "actor_by_name",
    "EventType", "TrustEvent", "Rank", "new_event_id",
    "EventStore", "InMemoryEventStore",
    "Standing", "RankEngine", "ProbationViolation",
    "Recommendation", "RecommendationStatus",
    "compute_trust_score", "propose_promotion", "PROMOTION_THRESHOLDS",
]

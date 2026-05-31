"""
Rank-aware routing decisions.

When an ActionProducer emits a freshly-proposed Action, the Orchestrator
must decide what happens next:

    - STAGE the action for user review        (PROPOSED → STAGED)
    - SEND the action autonomously             (PROPOSED → SENT, via executor)
    - DROP the action quietly                  (PROPOSED, no further transition;
                                                Observer rank rarely "acts")

The decision is a pure function of:
    - the actor's current Rank in this category
    - the actor's probation flag
    - the action's confidence
    - a policy (thresholds per rank)

Keep this pure. The Orchestrator handles the side-effects of acting on
the decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rex.actions.primitives import Action
from rex.ranks.engine import Standing
from rex.ranks.events import Rank


class Routing(str, Enum):
    """Where an action goes immediately after being proposed."""
    STAGE = "stage"      # → STAGED, await user review
    SEND = "send"        # → SENT (via executor), autonomous
    DROP = "drop"        # remain PROPOSED, not staged, not sent


@dataclass(frozen=True)
class RoutingDecision:
    routing: Routing
    reason: str          # one short sentence Rex could say


# ---------------------------------------------------------------------------
# Policy — minimum confidence to autonomously SEND, keyed by rank.
# ---------------------------------------------------------------------------
#
# Below the threshold (or at a rank that requires staging), the action is
# staged. Probation forces staging regardless of rank.
#
# DRAFTER and OBSERVER NEVER send autonomously — set their threshold to >1.
# CHIEF_OF_STAFF sends almost always — threshold low.

@dataclass(frozen=True)
class RoutingPolicy:
    """Configurable thresholds. The shipped defaults live below."""
    min_confidence_to_send: dict[Rank, float]
    # Drafter stages everything; Observer never even stages (it's a watcher).
    # Mapping required to be complete across all ranks.

    def threshold(self, rank: Rank) -> float:
        return self.min_confidence_to_send[rank]


DEFAULT_ROUTING_POLICY = RoutingPolicy(
    min_confidence_to_send={
        Rank.OBSERVER: 1.01,         # never sends — pure observer
        Rank.DRAFTER: 1.01,          # never sends — always stages for review
        Rank.SENDER: 0.85,           # sends when high-confidence
        Rank.OPERATOR: 0.70,         # sends on most categories
        Rank.CHIEF_OF_STAFF: 0.50,   # sends unless very unsure
    },
)


# ---------------------------------------------------------------------------
# Decision function — pure
# ---------------------------------------------------------------------------

def decide_route(
    *,
    action: Action,
    standing: Standing,
    policy: RoutingPolicy = DEFAULT_ROUTING_POLICY,
) -> RoutingDecision:
    """
    Decide whether to stage, send, or drop this proposed action.

    Rules (in priority order):
        1. Observer rank → DROP. Observers don't even surface to the user.
           (Rex is *watching* the category, not acting in it.)
        2. On probation → STAGE, regardless of rank/confidence. After a
           demotion the actor needs the user back in the loop.
        3. Otherwise → SEND if confidence ≥ policy threshold for the rank,
           else STAGE.
    """
    if standing.rank is Rank.OBSERVER:
        return RoutingDecision(
            routing=Routing.DROP,
            reason=f"Observer on {standing.category}. Watching, not acting.",
        )

    if standing.on_probation:
        return RoutingDecision(
            routing=Routing.STAGE,
            reason=(
                f"On probation in {standing.category}. "
                "Your call until I earn it back."
            ),
        )

    threshold = policy.threshold(standing.rank)
    if action.confidence >= threshold:
        return RoutingDecision(
            routing=Routing.SEND,
            reason=(
                f"{standing.rank.display} on {standing.category}, "
                f"confidence {int(round(action.confidence * 100))}%."
            ),
        )

    return RoutingDecision(
        routing=Routing.STAGE,
        reason=(
            f"Confidence {int(round(action.confidence * 100))}% below "
            f"my send threshold for {standing.rank.display} on "
            f"{standing.category}."
        ),
    )

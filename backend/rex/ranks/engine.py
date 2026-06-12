"""
The Rank Engine — pure replay of TrustEvents into Standings.

REX.md §4: state is a function of the event log, not the other way around.
This module is the function.

It also enforces every invariant from REX.md §4.5:

    1. Only USER_PROMOTED_REX may move Rex up.
    2. Sub-Agents only move up via USER_APPROVED_RECOMMENDATION that
       chains from a matching REX_RECOMMENDED_SUBAGENT_PROMOTION.
    3. Rex may demote a Sub-Agent unilaterally.
    4. Demotion sets probation.
    5. Probation lifts only via REX_LIFTED_PROBATION.
    6. Operational events do NOT change rank — they feed trust score
       (computed in recommendations.py, not here).

Pure module. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from rex.identity import CHIEF_OF_STAFF_NAME
from rex.ranks.events import (
    EventType,
    JOURNAL_ONLY_EVENTS,
    OPERATIONAL_EVENTS,
    Rank,
    TrustEvent,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ProbationViolation(Exception):
    """
    Raised when an event would violate the trust chain.

    Examples:
      - Promoting a Sub-Agent without a prior matching recommendation
      - User demoting Rex with a to_rank above from_rank
      - REX_LIFTED_PROBATION on an actor not currently on probation
    """


# ---------------------------------------------------------------------------
# Standing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Standing:
    """The current rank state for one (actor, category) pair."""
    actor_name: str
    category: str
    rank: Rank
    on_probation: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.actor_name, self.category)


# Default standing for any (actor, category) we haven't seen events for.
def _default_standing(actor_name: str, category: str) -> Standing:
    return Standing(
        actor_name=actor_name, category=category,
        rank=Rank.OBSERVER, on_probation=False,
    )


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

StateMap = dict[tuple[str, str], Standing]


@dataclass
class RankEngine:
    """
    A replay-state cache. The canonical state at any moment is
    `compute(events)`. The engine instance gives you ergonomic access
    + the recommendation-chaining bookkeeping.
    """

    state: StateMap

    # Track which recommendation IDs have been EMITTED but not yet resolved.
    # Required by invariant #2: a USER_APPROVED_RECOMMENDATION must reference
    # a prior REX_RECOMMENDED_SUBAGENT_PROMOTION.
    pending_recommendations: dict[str, TrustEvent]

    @classmethod
    def empty(cls) -> "RankEngine":
        return cls(state={}, pending_recommendations={})

    @classmethod
    def from_events(cls, events: Iterable[TrustEvent]) -> "RankEngine":
        engine = cls.empty()
        for e in events:
            engine.apply(e)
        return engine

    # ------------------------------------------------------------------

    def standing(self, actor_name: str, category: str) -> Standing:
        return self.state.get(
            (actor_name, category),
            _default_standing(actor_name, category),
        )

    def standings_for(self, actor_name: str) -> tuple[Standing, ...]:
        """Every Standing recorded for an actor, sorted by category."""
        out = [s for s in self.state.values() if s.actor_name == actor_name]
        out.sort(key=lambda s: s.category)
        return tuple(out)

    # ------------------------------------------------------------------
    # The single mutator: apply an event to engine state.
    # All invariant enforcement happens here. Operational events are no-ops
    # at the rank level (they're consumed by the trust-score calculator).
    # ------------------------------------------------------------------

    def apply(self, event: TrustEvent) -> None:
        if event.type in OPERATIONAL_EVENTS:
            # No rank state change. Operational events still need to be in
            # the event log so trust scores can read them downstream.
            return

        if event.type in JOURNAL_ONLY_EVENTS:
            # Recorded purely for journal/narrative context (e.g. the daily
            # background-work summary). Never affects rank state or trust score.
            return

        t = event.type
        if t in {EventType.FOUNDER_INVITED_TEAM_MEMBER, EventType.FOUNDER_REVOKED_TEAM_MEMBER}:
            # Handled by Orchestrator / Registry replay, no rank-ladder impact on Rex.
            return

        if t is EventType.USER_PROMOTED_REX:
            self._apply_rex_rank_change(event, direction="up")
        elif t is EventType.USER_DEMOTED_REX:
            self._apply_rex_rank_change(event, direction="down")
        elif t is EventType.REX_RECOMMENDED_SUBAGENT_PROMOTION:
            self._apply_recommend(event)
        elif t is EventType.USER_APPROVED_RECOMMENDATION:
            self._apply_approve_recommendation(event)
        elif t in (
            EventType.USER_DENIED_RECOMMENDATION,
            EventType.USER_DEFERRED_RECOMMENDATION,
        ):
            self._apply_close_recommendation(event)
        elif t is EventType.REX_DEMOTED_SUBAGENT:
            self._apply_rex_demotes_subagent(event)
        elif t is EventType.REX_LIFTED_PROBATION:
            self._apply_lift_probation(event)
        else:
            raise ProbationViolation(f"Unhandled event type: {t}")

    # ------------------------------------------------------------------
    # Specific handlers
    # ------------------------------------------------------------------

    def _apply_rex_rank_change(self, e: TrustEvent, *, direction: str) -> None:
        if e.actor_name != CHIEF_OF_STAFF_NAME:
            raise ProbationViolation(
                f"{e.type} must target {CHIEF_OF_STAFF_NAME}, got actor={e.actor_name!r}"
            )
        if e.to_rank is None or e.from_rank is None:
            raise ProbationViolation(f"{e.type} requires to_rank and from_rank")

        current = self.standing(CHIEF_OF_STAFF_NAME, e.category)
        if current.rank != e.from_rank:
            raise ProbationViolation(
                f"{e.type}: declared from_rank={e.from_rank} does not match "
                f"current rank={current.rank} for Rex/{e.category}"
            )
        if direction == "up" and e.to_rank <= e.from_rank:
            raise ProbationViolation(
                f"{e.type} is a promotion; to_rank must be strictly above from_rank"
            )
        if direction == "down" and e.to_rank >= e.from_rank:
            raise ProbationViolation(
                f"{e.type} is a demotion; to_rank must be strictly below from_rank"
            )

        # Demotion always triggers probation (REX.md §3.7).
        on_probation = (direction == "down") or current.on_probation
        # Promotion does NOT auto-lift probation — Rex has to do that explicitly.

        self.state[(CHIEF_OF_STAFF_NAME, e.category)] = Standing(
            actor_name=CHIEF_OF_STAFF_NAME,
            category=e.category,
            rank=e.to_rank,
            on_probation=on_probation,
        )

    def _apply_recommend(self, e: TrustEvent) -> None:
        if e.actor_name == CHIEF_OF_STAFF_NAME:
            raise ProbationViolation(
                f"Recommendation must target a Sub-Agent, not {CHIEF_OF_STAFF_NAME}"
            )
        if e.to_rank is None or e.from_rank is None:
            raise ProbationViolation("Recommendation requires to_rank and from_rank")
        if e.to_rank <= e.from_rank:
            raise ProbationViolation("Recommendation must move rank up")

        current = self.standing(e.actor_name, e.category)
        if current.rank != e.from_rank:
            raise ProbationViolation(
                f"Recommended from_rank={e.from_rank} does not match current "
                f"rank={current.rank} for {e.actor_name}/{e.category}"
            )
        # No rank change. Park the recommendation for later approval.
        self.pending_recommendations[e.id] = e

    def _apply_approve_recommendation(self, e: TrustEvent) -> None:
        if e.recommendation_id is None:
            raise ProbationViolation(
                "USER_APPROVED_RECOMMENDATION requires recommendation_id"
            )
        rec = self.pending_recommendations.pop(e.recommendation_id, None)
        if rec is None:
            raise ProbationViolation(
                f"No pending recommendation with id={e.recommendation_id!r}. "
                "Sub-Agents cannot be promoted without a prior recommendation."
            )
        # Ensure the approval matches the recommendation exactly.
        if (rec.actor_name != e.actor_name
                or rec.category != e.category
                or rec.to_rank != e.to_rank
                or rec.from_rank != e.from_rank):
            raise ProbationViolation(
                "Approval does not match the original recommendation."
            )
        current = self.standing(e.actor_name, e.category)
        if current.rank != e.from_rank:
            raise ProbationViolation(
                "Sub-Agent rank changed after the recommendation was made."
            )
        self.state[(e.actor_name, e.category)] = replace(
            current, rank=e.to_rank,
        )

    def _apply_close_recommendation(self, e: TrustEvent) -> None:
        if e.recommendation_id is None:
            raise ProbationViolation(f"{e.type} requires recommendation_id")
        # Denials and deferrals just close the pending recommendation.
        # No state change. Missing is OK (idempotent close).
        self.pending_recommendations.pop(e.recommendation_id, None)

    def _apply_rex_demotes_subagent(self, e: TrustEvent) -> None:
        if e.actor_name == CHIEF_OF_STAFF_NAME:
            raise ProbationViolation(
                f"REX_DEMOTED_SUBAGENT cannot target {CHIEF_OF_STAFF_NAME}"
            )
        if e.to_rank is None or e.from_rank is None:
            raise ProbationViolation("Demotion requires to_rank and from_rank")
        if e.to_rank >= e.from_rank:
            raise ProbationViolation("Demotion must move rank strictly down")
        current = self.standing(e.actor_name, e.category)
        if current.rank != e.from_rank:
            raise ProbationViolation(
                f"Declared from_rank={e.from_rank} does not match current "
                f"rank={current.rank} for {e.actor_name}/{e.category}"
            )
        # Demotion triggers automatic probation (REX.md §3.7).
        self.state[(e.actor_name, e.category)] = Standing(
            actor_name=e.actor_name,
            category=e.category,
            rank=e.to_rank,
            on_probation=True,
        )

    def _apply_lift_probation(self, e: TrustEvent) -> None:
        current = self.standing(e.actor_name, e.category)
        if not current.on_probation:
            raise ProbationViolation(
                f"{e.actor_name}/{e.category} is not on probation — nothing to lift"
            )
        self.state[(e.actor_name, e.category)] = replace(
            current, on_probation=False,
        )

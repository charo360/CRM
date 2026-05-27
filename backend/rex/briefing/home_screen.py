"""
HomeScreen — the full snapshot the future UI will render.

`build_home_screen(orchestrator, ...)` reads everything the home screen
needs in one pure pass:

    - the Letter (composed from top-3 staged actions)
    - a count of recent SENT / UNDONE / FAILED actions
    - pending Sub-Agent promotion recommendations awaiting user decision
    - Rex's current standing across Tier-1 categories (the day-1 ones)

Everything is JSON-serializable via `dataclasses.asdict`. The frontend
in Phase 9 will consume this verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from rex.actions.primitives import ActionState
from rex.briefing.letter import Letter, compose_letter
from rex.briefing.opener import opener_for
from rex.briefing.selector import pick_top_actions
from rex.loop.orchestrator import Orchestrator
from rex.ranks.categories import Tier, all_categories
from rex.ranks.engine import Standing
from rex.ranks.events import Rank


# ---------------------------------------------------------------------------
# Snapshot dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PendingPromotion:
    """A Sub-Agent promotion recommendation awaiting user decision."""
    recommendation_id: str
    subagent_name: str
    category: str
    from_rank: str           # display string ("Drafter")
    to_rank: str             # display string ("Sender")
    reason: str
    confidence_pct: int


@dataclass(frozen=True)
class StandingSummary:
    """One actor/category Standing flattened for UI."""
    actor_name: str
    category: str
    rank: str                # display string
    on_probation: bool


@dataclass(frozen=True)
class LedgerCounts:
    staged: int
    sent_today: int
    undone_today: int
    failed_today: int


@dataclass(frozen=True)
class HomeScreen:
    """The full top-of-app payload."""
    letter: Letter
    counts: LedgerCounts
    pending_promotions: tuple[PendingPromotion, ...]
    rex_standings: tuple[StandingSummary, ...]   # Tier-1 only; full list elsewhere
    generated_at: datetime
    relationship_day: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_window(now: datetime) -> datetime:
    """Start-of-day in the same tzinfo as `now`. Used for 'recent' counts."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _count_in_state_today(orch: Orchestrator, state: ActionState, day_start: datetime) -> int:
    n = 0
    for a in orch.ledger.actions_in_state(state):
        # Use the LATEST transition timestamp into this state for "today" check.
        transitions = [c for c in orch.ledger.changes(a.id) if c.to_state is state]
        if transitions and transitions[-1].at >= day_start:
            n += 1
    return n


def _pending_promotions(orch: Orchestrator) -> tuple[PendingPromotion, ...]:
    out: list[PendingPromotion] = []
    for rec_id, evt in orch.engine.pending_recommendations.items():
        out.append(PendingPromotion(
            recommendation_id=rec_id,
            subagent_name=evt.actor_name,
            category=evt.category,
            from_rank=(evt.from_rank.display if evt.from_rank is not None else "—"),
            to_rank=(evt.to_rank.display if evt.to_rank is not None else "—"),
            reason=evt.reason or "",
            confidence_pct=int(round((evt.confidence or 0.0) * 100)),
        ))
    # Stable order: by category then subagent for predictable UI.
    out.sort(key=lambda p: (p.category, p.subagent_name))
    return tuple(out)


def _rex_tier1_standings(orch: Orchestrator) -> tuple[StandingSummary, ...]:
    """Rex's current Standing in every Tier-1 category."""
    out: list[StandingSummary] = []
    for cat in all_categories():
        if cat.tier is not Tier.CORE:
            continue
        s: Standing = orch.engine.standing("Rex", cat.name)
        out.append(StandingSummary(
            actor_name="Rex",
            category=cat.name,
            rank=s.rank.display,
            on_probation=s.on_probation,
        ))
    return tuple(out)


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_home_screen(
    orchestrator: Orchestrator,
    *,
    now: datetime | None = None,
    relationship_day: int = 1,
) -> HomeScreen:
    """
    Build a full home-screen snapshot from the orchestrator's current state.

    Pure: doesn't mutate the orchestrator. Same inputs → same outputs.
    """
    moment = now or datetime.now(timezone.utc)
    if relationship_day < 1:
        raise ValueError("relationship_day must be >= 1")

    # 1) Letter
    staged = list(orchestrator.ledger.staged_actions())
    top = pick_top_actions(staged, limit=3, now=moment)
    opener = opener_for(now=moment, relationship_day=relationship_day)
    letter = compose_letter(
        opener=opener,
        staged_actions=top,
        notebook=orchestrator.notebook,
    )

    # 2) Counts
    day_start = _today_window(moment)
    counts = LedgerCounts(
        staged=len(staged),
        sent_today=_count_in_state_today(orchestrator, ActionState.SENT, day_start),
        undone_today=_count_in_state_today(orchestrator, ActionState.UNDONE, day_start),
        failed_today=_count_in_state_today(orchestrator, ActionState.FAILED, day_start),
    )

    # 3) Pending promotion recommendations
    pending = _pending_promotions(orchestrator)

    # 4) Rex's Tier-1 standings
    standings = _rex_tier1_standings(orchestrator)

    return HomeScreen(
        letter=letter,
        counts=counts,
        pending_promotions=pending,
        rex_standings=standings,
        generated_at=moment,
        relationship_day=relationship_day,
    )

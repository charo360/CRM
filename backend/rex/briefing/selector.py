"""
Pick the top-N STAGED actions for the Letter.

Per REX.md §3.10, the Letter shows AT MOST THREE actions. Everything else
is "in the full ledger below". This module is the pure ranker.

Scoring (no LLM, no I/O):

    score(action) = 0.6 * confidence
                  + 0.3 * freshness    (newer staged = higher)
                  + 0.1 * tier_bias    (Tier-1 categories slightly preferred)

Ties broken by `proposed_at` (newer first).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from rex.actions.primitives import Action
from rex.ranks.categories import Tier, category as _lookup_category, is_category


@dataclass(frozen=True)
class ActionScore:
    """Diagnostic score breakdown — useful for tests + future Inspect mode."""
    action_id: str
    score: float
    confidence_term: float
    freshness_term: float
    tier_term: float


# Soft-decay window: actions older than this contribute zero freshness.
_FRESHNESS_WINDOW_HOURS = 24.0


def _freshness(action: Action, *, now: datetime) -> float:
    age_hours = (now - action.proposed_at).total_seconds() / 3600.0
    if age_hours <= 0:
        return 1.0
    if age_hours >= _FRESHNESS_WINDOW_HOURS:
        return 0.0
    return 1.0 - (age_hours / _FRESHNESS_WINDOW_HOURS)


def _tier_bias(category_name: str) -> float:
    """Tier-1 (Day 1 categories) get a small bump. Unknown categories: 0."""
    if not is_category(category_name):
        return 0.0
    cat = _lookup_category(category_name)
    if cat.tier is Tier.CORE:
        return 1.0
    if cat.tier is Tier.OPERATIONS:
        return 0.6
    return 0.3


def score_action(action: Action, *, now: datetime) -> ActionScore:
    conf = max(0.0, min(1.0, action.confidence))
    fresh = _freshness(action, now=now)
    tier = _tier_bias(action.category)
    s = 0.6 * conf + 0.3 * fresh + 0.1 * tier
    return ActionScore(
        action_id=action.id,
        score=round(s, 4),
        confidence_term=round(0.6 * conf, 4),
        freshness_term=round(0.3 * fresh, 4),
        tier_term=round(0.1 * tier, 4),
    )


def pick_top_actions(
    actions: Iterable[Action],
    *,
    limit: int = 3,
    now: datetime | None = None,
) -> tuple[Action, ...]:
    """
    Return up to `limit` actions ranked highest-relevance first.

    The ranker is deterministic given the same inputs — important for
    snapshot tests and for the Letter to be stable when repeatedly rendered.
    """
    if limit <= 0:
        return ()
    moment = now or datetime.now(timezone.utc)
    pool = list(actions)
    if not pool:
        return ()
    scored = [(score_action(a, now=moment), a) for a in pool]
    # Sort by (score desc, proposed_at desc, id asc for stability).
    scored.sort(
        key=lambda x: (-x[0].score, -x[1].proposed_at.timestamp(), x[1].id),
    )
    return tuple(a for _, a in scored[:limit])

"""
Pick the top-N STAGED actions for the Live Feed.

Per REX.md §3.10, the Letter shows AT MOST THREE actions. Everything else
lives in the full ledger below. This module is the pure ranker, updated to filter
on importance and urgency.

Scoring:
    score = 0.35 * urgency + 0.35 * importance + 0.20 * confidence + 0.10 * freshness

Ties broken by `proposed_at` (newer first).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from rex.actions.primitives import Action, ActionKind
from rex.ranks.categories import Tier, category as _lookup_category, is_category


@dataclass(frozen=True)
class ActionScore:
    """Diagnostic score breakdown — useful for tests + future Inspect mode."""
    action_id: str
    score: float
    confidence_term: float
    freshness_term: float
    tier_term: float
    urgency_term: float
    importance_term: float


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


def calculate_action_urgency(action: Action, now: datetime) -> float:
    """Calculate the urgency level (0.0 to 1.0) of an action."""
    kind = action.kind
    cat = action.category

    # 1. Base urgency by category or kind
    if cat == "replies" or kind in (ActionKind.REPLY, ActionKind.SOCIAL_DM):
        base = 0.9
    elif cat == "invoices" or kind == ActionKind.INVOICE:
        base = 0.8
    elif cat == "follow_ups" or kind == ActionKind.FOLLOW_UP:
        base = 0.7
    elif cat == "quotes" or kind == ActionKind.QUOTE:
        base = 0.6
    elif cat == "leads" or kind in (ActionKind.SOCIAL_POST, ActionKind.OUTREACH):
        base = 0.4
    elif kind == ActionKind.DATA_FLAG:
        base = 0.3
    else:
        base = 0.5

    # 2. Payload override
    payload = action.payload or {}
    urgency_val = payload.get("urgency")
    if urgency_val == "high":
        base = 1.0
    elif urgency_val == "medium":
        base = 0.6
    elif urgency_val == "low":
        base = 0.3

    # 3. Keyword indicators in summary / reasoning
    text = f"{action.summary} {action.reasoning}".lower()
    urgent_keywords = ("urgent", "asap", "dispute", "complaint", "failed", "error")
    if any(kw in text for kw in urgent_keywords):
        base += 0.15

    question_keywords = ("question", "how much", "price", "cost")
    if any(kw in text for kw in question_keywords):
        base += 0.10

    # 4. Aging penalty (anti-starvation)
    age_days = (now - action.proposed_at).total_seconds() / 86400.0
    if age_days >= 1.0:
        penalty = min(0.4, int(age_days) * 0.1)
        base -= penalty

    return max(0.0, min(1.0, base))


def calculate_action_importance(action: Action) -> float:
    """Calculate the importance level (0.0 to 1.0) of an action."""
    cat_name = action.category

    # 1. Base importance by category tier
    if cat_name == "strategy":
        base = 0.92
    elif is_category(cat_name):
        cat = _lookup_category(cat_name)
        if cat.tier is Tier.CORE:
            base = 0.8
        elif cat.tier is Tier.OPERATIONS:
            base = 0.7
        else:
            base = 0.5
    else:
        base = 0.5

    # 2. Modifiers
    payload = action.payload or {}

    # Financial Value
    amount = payload.get("amount")
    if amount is not None:
        try:
            amt_f = float(amount)
            if amt_f > 1000.0:
                base += 0.20
            elif amt_f > 100.0:
                base += 0.10
            elif amt_f > 0.0:
                base += 0.05
        except (ValueError, TypeError):
            pass

    # Customer Status
    tags = payload.get("tags") or []
    if isinstance(tags, (list, tuple)):
        tags_lower = [str(t).lower() for t in tags]
        if "vip" in tags_lower:
            base += 0.20
        elif "returning" in tags_lower:
            base += 0.10

    # Safety & Agency Events
    text = f"{action.summary} {action.reasoning}".lower()
    if "demoted" in text or "probation" in text or "safety" in text:
        base += 0.25
    elif "recommend" in text or "promote" in text:
        base += 0.15

    return max(0.0, min(1.0, base))


def score_action(action: Action, *, now: datetime) -> ActionScore:
    conf = max(0.0, min(1.0, action.confidence))
    fresh = _freshness(action, now=now)
    tier = _tier_bias(action.category)

    urgency = calculate_action_urgency(action, now)
    importance = calculate_action_importance(action)

    s = 0.35 * urgency + 0.35 * importance + 0.20 * conf + 0.10 * fresh

    return ActionScore(
        action_id=action.id,
        score=round(s, 4),
        confidence_term=round(0.20 * conf, 4),
        freshness_term=round(0.10 * fresh, 4),
        tier_term=round(0.10 * tier, 4),  # Kept for backward compatibility in interface
        urgency_term=round(0.35 * urgency, 4),
        importance_term=round(0.35 * importance, 4),
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


"""
Action primitives — frozen dataclasses + lifecycle enum.

Two immutable shapes drive the entire ledger:

    Action              The manifest captured the moment Rex proposes the work.
                        Never changes after creation.
    ActionStateChange   One transition. Append-only. The current state of an
                        Action is computed by replaying its state changes.

This mirrors the event-sourcing pattern already established in rex.ranks
(Phase 2). Same discipline: state is a function of events; replay is a
pure function.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from rex.ranks.events import Rank
from rex.principals.visibility import Visibility, visibility_founder_only


# ---------------------------------------------------------------------------
# IDs + clock
# ---------------------------------------------------------------------------

def new_action_id() -> str:
    return uuid.uuid4().hex


def new_change_id() -> str:
    return uuid.uuid4().hex


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Window during which a SENT Action is reversible. After this, the Ledger
# emits ACTION_CLEAN_SEND on the next sweep (Phase 5 mechanic).
UNDO_WINDOW_SECONDS: int = 30 * 60  # 30 minutes


# ---------------------------------------------------------------------------
# Kind — the SHAPE of work (used for Inspect filtering + journal references)
# ---------------------------------------------------------------------------

class ActionKind(str, Enum):
    OUTREACH = "outreach"               # cold/warm outbound message
    REPLY = "reply"                     # inbound response
    FOLLOW_UP = "follow_up"             # nudge on stalled thread
    INVOICE = "invoice"                 # send or chase an invoice
    QUOTE = "quote"                     # send a quote / proposal
    BOOKING = "booking"                 # confirm / move a booking
    PAYMENT = "payment"                 # process / reconcile a payment
    BROADCAST = "broadcast"             # send to a campaign list
    SOCIAL_POST = "social_post"         # publish to social
    SOCIAL_DM = "social_dm"             # reply to a social DM
    AD_ADJUSTMENT = "ad_adjustment"     # change an ad bid / budget
    DATA_FLAG = "data_flag"             # internal flag, no external send
    INTERNAL_NOTE = "internal_note"     # observation for the user only


# ---------------------------------------------------------------------------
# Lifecycle state
# ---------------------------------------------------------------------------

class ActionState(str, Enum):
    """
    Lifecycle of a single Action. Transitions are validated in transitions.py.

    Flow summary:
        PROPOSED ── Rex's rank allows autonomous send ─→ SENT
        PROPOSED ── Rex's rank requires staging ───────→ STAGED
        STAGED   ── user approves ───────────────────→ APPROVED → SENT
        STAGED   ── user rejects ────────────────────→ REJECTED   (terminal)
        STAGED   ── user "handle manually" ──────────→ DISMISSED  (terminal)
        SENT     ── undo within window ──────────────→ UNDONE     (terminal)
        APPROVED ── executor errors ─────────────────→ FAILED     (terminal)
    """
    PROPOSED = "proposed"
    STAGED = "staged"
    APPROVED = "approved"
    SENT = "sent"
    REJECTED = "rejected"
    DISMISSED = "dismissed"
    UNDONE = "undone"
    FAILED = "failed"


TERMINAL_STATES: frozenset[ActionState] = frozenset({
    ActionState.REJECTED,
    ActionState.DISMISSED,
    ActionState.UNDONE,
    ActionState.FAILED,
})


# ---------------------------------------------------------------------------
# Outcome — optional result data on a state change (e.g. external message id)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Outcome:
    """
    Result data attached to a state change.

    For SENT actions: external_id (e.g. Gmail message id), recipient counts,
    cost-cents, etc. For FAILED: error_class + error_message.
    """
    external_ref: str | None = None      # e.g. "gmail-msg-abc123"
    rows_affected: int | None = None     # e.g. 12 recipients
    cost_cents: int | None = None
    error_class: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Action manifest — frozen at proposal time
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    """
    The immutable manifest captured the moment Rex (or one of his Sub-Agents)
    proposes a piece of work.

    Anything that MIGHT change later (state, outcome) lives in
    ActionStateChange records, not here.
    """

    # Identity + time
    id: str
    proposed_at: datetime

    # Who proposed it
    actor_name: str               # "Rex" or a Sub-Agent name
    rank_at_time: Rank            # rank of actor in this category, at proposal

    # Where it lives
    category: str                 # canonical Category name (e.g. "outreach")
    kind: ActionKind

    # The work itself
    summary: str                  # one-line Rex-voice description (Phase 1)
    payload: Mapping[str, Any]    # mode-specific data (recipient, body, etc.)

    # Why
    reasoning: str                # the "why" string (Phase 1 Mode.REASONING)
    confidence: float             # 0.0-1.0 — Rex's confidence at proposal

    # Provenance
    target_subject: str | None = None    # "Patel", "Acme", etc. (for citations)
    memory_citation_ids: tuple[str, ...] = ()    # NotebookEntry ids
    source_event_ids: tuple[str, ...] = ()       # TrustEvents that triggered

    # Phase 8: Two-Sided Loyalty
    visibility: Visibility = field(default_factory=lambda: visibility_founder_only)

    @classmethod
    def propose(
        cls,
        *,
        actor_name: str,
        rank_at_time: Rank,
        category: str,
        kind: ActionKind,
        summary: str,
        payload: Mapping[str, Any] | None = None,
        reasoning: str = "",
        confidence: float = 0.0,
        target_subject: str | None = None,
        memory_citation_ids: tuple[str, ...] = (),
        source_event_ids: tuple[str, ...] = (),
        visibility: Visibility | None = None,
    ) -> "Action":
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0–1.0, got {confidence}")
        return cls(
            id=new_action_id(),
            proposed_at=_utc_now(),
            actor_name=actor_name,
            rank_at_time=rank_at_time,
            category=category,
            kind=kind,
            summary=summary.strip(),
            payload=dict(payload or {}),     # shallow copy; treat as frozen
            reasoning=reasoning.strip(),
            confidence=confidence,
            target_subject=target_subject,
            memory_citation_ids=tuple(memory_citation_ids),
            source_event_ids=tuple(source_event_ids),
            visibility=visibility if visibility is not None else visibility_founder_only,
        )


# ---------------------------------------------------------------------------
# State change — one transition in the lifecycle
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActionStateChange:
    """
    One append-only entry in the Action's lifecycle log.

    The pair (action_id, sequence_no) is unique within a Ledger; sequence_no
    is assigned by the Ledger at append time.
    """
    id: str
    action_id: str
    at: datetime
    from_state: ActionState | None       # None for the initial state assignment
    to_state: ActionState
    actor_name: str                      # who caused the change ("Rex", "User", a Sub-Agent)
    reason: str | None = None
    outcome: Outcome | None = None

    @classmethod
    def make(
        cls,
        *,
        action_id: str,
        from_state: ActionState | None,
        to_state: ActionState,
        actor_name: str,
        reason: str | None = None,
        outcome: Outcome | None = None,
    ) -> "ActionStateChange":
        return cls(
            id=new_change_id(),
            action_id=action_id,
            at=_utc_now(),
            from_state=from_state,
            to_state=to_state,
            actor_name=actor_name,
            reason=reason,
            outcome=outcome,
        )

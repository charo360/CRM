"""
rex.actions — Action primitive + Ledger (REX.md §3.11 + §4 primitive #5).

Phase 4 of the Rex build. Still pure: no LLM, no DB, no external I/O.
This phase defines the contracts every later phase will satisfy:

    - rex.loop      (Phase 5) emits Actions via ActionProducer
    - rex.briefing  (Phase 6) picks the top 3 STAGED Actions for the Letter
    - rex.journal   (Phase 7) reflects on significant Action outcomes
    - rex.persona   (Phase 1) already knows how to *speak* about Actions
                    (Mode.REASONING, Mode.ACTION_DRAFT, etc.)

THE FIVE PRIMITIVES
===================
    ActionKind          One of ~13 shapes of work (outreach, reply, invoice…)
    ActionState         Lifecycle state — PROPOSED → STAGED → SENT → …
    Action              Immutable manifest captured at proposal time.
    ActionStateChange   Append-only transition event for one Action.
    Outcome             Optional result data attached to terminal states.

THE LEDGER (REX.md §3.11)
=========================
The append-only record of every Action and every state change. Two views
over the SAME data:

    Story mode    — reverse-chronological, Rex's voice, inline expand.
    Inspect mode  — dense table; filterable, sortable, audit-ready.

`rex.actions.rendering` provides both as pure functions.

INTEGRATION POINTS
==================
Phase 4 is wired to Phase 2 (trust events) via `state_change_trust_events`:

    Approving a STAGED action       → ACTION_APPROVED
    Rejecting a STAGED action       → ACTION_REJECTED
    Undoing a SENT action           → ACTION_UNDONE
    A SENT action clearing the undo → ACTION_CLEAN_SEND  (later)
    A FAILED execution flagged      → ACTION_FLAGGED_MISTAKE

The Ledger DOES NOT touch the EventStore directly. State changes return
a list of Phase-2 events the orchestrator routes to the right place.
This keeps every module free of cyclic imports.
"""

from rex.actions.primitives import (
    Action,
    ActionKind,
    ActionState,
    ActionStateChange,
    Outcome,
    new_action_id,
    new_change_id,
    TERMINAL_STATES,
    UNDO_WINDOW_SECONDS,
)
from rex.actions.transitions import (
    InvalidTransition,
    is_valid_transition,
    state_change_trust_events,
    derive_current_state,
)
from rex.actions.ledger import Ledger, LedgerStore, InMemoryLedgerStore
from rex.actions.protocols import ActionProducer, ActionExecutor, ExecutionResult
from rex.actions.rendering import (
    story_render,
    story_render_action,
    inspect_rows,
    InspectRow,
)

__all__ = [
    # Primitives
    "Action", "ActionKind", "ActionState", "ActionStateChange", "Outcome",
    "new_action_id", "new_change_id",
    "TERMINAL_STATES", "UNDO_WINDOW_SECONDS",
    # Transitions
    "InvalidTransition", "is_valid_transition",
    "state_change_trust_events", "derive_current_state",
    # Ledger
    "Ledger", "LedgerStore", "InMemoryLedgerStore",
    # Protocols
    "ActionProducer", "ActionExecutor", "ExecutionResult",
    # Rendering
    "story_render", "story_render_action",
    "inspect_rows", "InspectRow",
]

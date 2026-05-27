"""
Action lifecycle transition rules + Phase 2 trust event mapping.

Two responsibilities:

    1. `is_valid_transition(from_state, to_state)` — pure validator.
    2. `state_change_trust_events(change)` — map an ActionStateChange to the
       Phase 2 TrustEvents the orchestrator should emit alongside it.

By keeping the trust-event mapping in this seam (rather than inside the
Ledger), the Ledger stays purely about Actions. The orchestrator (Phase 5)
will call both: apply the change to the Ledger, then route any returned
TrustEvents to the rex.ranks event store.
"""

from __future__ import annotations

from typing import Iterable

from rex.actions.primitives import Action, ActionState, ActionStateChange
from rex.ranks.events import EventType, TrustEvent


class InvalidTransition(Exception):
    """Raised when a state transition is not permitted by the lifecycle."""


# ---------------------------------------------------------------------------
# Legal transitions — a directed graph
# ---------------------------------------------------------------------------

# (from_state | None) → set of permitted to_states.
# None as the source means "initial assignment" — only PROPOSED is allowed.
_LEGAL: dict[ActionState | None, frozenset[ActionState]] = {
    None: frozenset({ActionState.PROPOSED}),
    ActionState.PROPOSED: frozenset({
        ActionState.STAGED,         # Rex stages for user review
        ActionState.SENT,           # Rex's rank allows autonomous send
    }),
    ActionState.STAGED: frozenset({
        ActionState.APPROVED,       # user clicked approve
        ActionState.REJECTED,       # user clicked reject
        ActionState.DISMISSED,      # user clicked "Handle manually"
    }),
    ActionState.APPROVED: frozenset({
        ActionState.SENT,           # executor ran
        ActionState.FAILED,         # executor errored
    }),
    ActionState.SENT: frozenset({
        ActionState.UNDONE,         # within undo window
        # NOTE: There is no SENT → "CLEAN" state. ACTION_CLEAN_SEND is
        # a Phase-2 TrustEvent emitted by the orchestrator on a sweep
        # once the undo window closes. The Action itself stays in SENT.
    }),
    # Terminal states have no outgoing transitions.
    ActionState.REJECTED: frozenset(),
    ActionState.DISMISSED: frozenset(),
    ActionState.UNDONE: frozenset(),
    ActionState.FAILED: frozenset(),
}


def is_valid_transition(
    from_state: ActionState | None,
    to_state: ActionState,
) -> bool:
    return to_state in _LEGAL.get(from_state, frozenset())


# ---------------------------------------------------------------------------
# State replay — current state of an Action
# ---------------------------------------------------------------------------

def derive_current_state(changes: Iterable[ActionStateChange]) -> ActionState:
    """
    Replay state changes for one Action and return the final state.

    Raises InvalidTransition if any change in the sequence violates the
    lifecycle graph. PROPOSED is the implicit initial state if the first
    change has `from_state=None`.
    """
    current: ActionState | None = None
    for c in changes:
        if c.from_state != current:
            raise InvalidTransition(
                f"Change {c.id} declared from_state={c.from_state} "
                f"but replay state was {current}"
            )
        if not is_valid_transition(current, c.to_state):
            raise InvalidTransition(
                f"Illegal transition {current} → {c.to_state}"
            )
        current = c.to_state
    if current is None:
        raise InvalidTransition("No state changes recorded for this action")
    return current


# ---------------------------------------------------------------------------
# Trust event mapping — Phase 4 → Phase 2 bridge
# ---------------------------------------------------------------------------

# Map (to_state, actor_kind_hint) → Phase 2 EventType.
#
# The actor_name in an ActionStateChange tells us who caused the transition:
#   - "User"     → user-initiated (approve / reject / undo)
#   - "Rex"      → Rex acting (sent autonomously, dismissed, etc.)
#   - <subagent> → a Sub-Agent action (its rank, its category)
#
# What feeds the trust score is the LIFECYCLE OUTCOME on the actor
# whose work this Action represents (action.actor_name), NOT who
# happened to click a button. We pass both in `state_change_trust_events`.

def state_change_trust_events(
    *,
    action: Action,
    change: ActionStateChange,
) -> tuple[TrustEvent, ...]:
    """
    Return the Phase 2 TrustEvents that should be appended when this state
    change happens. Empty tuple is normal — many transitions don't move
    trust (e.g. PROPOSED → STAGED is just queuing).

    Caller (Phase 5 orchestrator) must hand these to the rex.ranks store.
    """
    to = change.to_state
    actor = action.actor_name
    cat = action.category
    conf = action.confidence
    reason = change.reason

    # User approved a staged action — positive for the actor whose work it was.
    if to is ActionState.APPROVED:
        return (TrustEvent.operational(
            type=EventType.ACTION_APPROVED,
            actor_name=actor, category=cat,
            confidence=conf, reason=reason,
        ),)

    # User rejected a staged action — negative.
    if to is ActionState.REJECTED:
        return (TrustEvent.operational(
            type=EventType.ACTION_REJECTED,
            actor_name=actor, category=cat,
            confidence=conf, reason=reason,
        ),)

    # User undid a previously SENT action — negative.
    if to is ActionState.UNDONE:
        return (TrustEvent.operational(
            type=EventType.ACTION_UNDONE,
            actor_name=actor, category=cat,
            confidence=conf, reason=reason,
        ),)

    # Executor failed — mistake.
    if to is ActionState.FAILED:
        return (TrustEvent.operational(
            type=EventType.ACTION_FLAGGED_MISTAKE,
            actor_name=actor, category=cat,
            confidence=conf, reason=reason,
        ),)

    # DISMISSED ("handle manually"), PROPOSED, STAGED, SENT (the SEND itself):
    # no trust event from the transition alone.
    # ACTION_CLEAN_SEND is emitted later by a sweep when the undo window
    # closes on a SENT action — that's Phase 5.
    return ()


# Phase-5 convenience: emit ACTION_CLEAN_SEND once an undo window has closed
# without the action being undone. Pure helper — caller decides when to invoke.
def clean_send_event(*, action: Action) -> TrustEvent:
    return TrustEvent.operational(
        type=EventType.ACTION_CLEAN_SEND,
        actor_name=action.actor_name,
        category=action.category,
        confidence=action.confidence,
    )

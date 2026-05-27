"""
The Ledger — append-only record of every Action and every state change.

REX.md §3.11: "Story + Inspect Mode" — same underlying data, two views.
This module owns the data. rex.actions.rendering owns the two views.

The Ledger is intentionally dumb about Phase 2. It does NOT touch the
rex.ranks event store. When a state transition happens it returns the
Phase-2 TrustEvents to emit, and the orchestrator (Phase 5) routes them.

Pure module. No I/O.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Protocol, runtime_checkable

from rex.actions.primitives import (
    Action,
    ActionState,
    ActionStateChange,
    Outcome,
    TERMINAL_STATES,
)
from rex.actions.transitions import (
    InvalidTransition,
    derive_current_state,
    is_valid_transition,
    state_change_trust_events,
)
from rex.ranks.events import TrustEvent


# ---------------------------------------------------------------------------
# Storage Protocol — swappable in Phase 4 (in-memory) → Phase ? (DB)
# ---------------------------------------------------------------------------

@runtime_checkable
class LedgerStore(Protocol):
    """
    Storage contract. Implementations must preserve:
      - append order for ActionStateChange
      - immutability of stored Actions
      - O(1) lookup by action id
    """

    def put_action(self, action: Action) -> None: ...
    def get_action(self, action_id: str) -> Action | None: ...
    def all_actions(self) -> tuple[Action, ...]: ...

    def append_change(self, change: ActionStateChange) -> None: ...
    def changes_for(self, action_id: str) -> tuple[ActionStateChange, ...]: ...
    def all_changes(self) -> tuple[ActionStateChange, ...]: ...

    def __len__(self) -> int: ...


class InMemoryLedgerStore:
    """Dict + list. Single-process, thread-unsafe; same as other Phase modules."""

    __slots__ = ("_actions", "_changes")

    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}
        self._changes: list[ActionStateChange] = []

    # Actions ----------------------------------------------------------------

    def put_action(self, action: Action) -> None:
        if action.id in self._actions:
            raise ValueError(f"Action already in store: {action.id}")
        self._actions[action.id] = action

    def get_action(self, action_id: str) -> Action | None:
        return self._actions.get(action_id)

    def all_actions(self) -> tuple[Action, ...]:
        # Sort by proposal time then id for deterministic tests.
        return tuple(sorted(
            self._actions.values(),
            key=lambda a: (a.proposed_at, a.id),
        ))

    # Changes ----------------------------------------------------------------

    def append_change(self, change: ActionStateChange) -> None:
        self._changes.append(change)

    def changes_for(self, action_id: str) -> tuple[ActionStateChange, ...]:
        return tuple(c for c in self._changes if c.action_id == action_id)

    def all_changes(self) -> tuple[ActionStateChange, ...]:
        return tuple(self._changes)

    def __len__(self) -> int:
        return len(self._actions)


# ---------------------------------------------------------------------------
# The Ledger — orchestrates Action storage + state-change append
# ---------------------------------------------------------------------------

class Ledger:
    """
    The append-only Action log.

    Typical use:

        ledger = Ledger()
        action = Action.propose(...)
        ledger.record_proposal(action)           # records PROPOSED state

        # User reviews and approves a previously staged action:
        events = ledger.transition(
            action_id=action.id,
            to_state=ActionState.APPROVED,
            actor_name="User",
            reason="Looks good",
        )
        # Phase 5 routes `events` to the rex.ranks store.
    """

    def __init__(self, store: LedgerStore | None = None) -> None:
        self._store: LedgerStore = store if store is not None else InMemoryLedgerStore()

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def record_proposal(self, action: Action) -> ActionStateChange:
        """
        Add a freshly-proposed action and record its initial state change
        (None → PROPOSED).

        Returns the state change. No Phase-2 events emitted at proposal time.
        """
        self._store.put_action(action)
        change = ActionStateChange.make(
            action_id=action.id,
            from_state=None,
            to_state=ActionState.PROPOSED,
            actor_name=action.actor_name,
            reason="Proposed.",
        )
        self._store.append_change(change)
        return change

    def transition(
        self,
        *,
        action_id: str,
        to_state: ActionState,
        actor_name: str,
        reason: str | None = None,
        outcome: Outcome | None = None,
    ) -> tuple[ActionStateChange, tuple[TrustEvent, ...]]:
        """
        Move an Action to a new state. Validates the transition is legal
        against the current replayed state.

        Returns (state_change, trust_events_to_emit).
        """
        action = self._store.get_action(action_id)
        if action is None:
            raise KeyError(f"No action with id={action_id!r}")

        current = self.current_state(action_id)
        if not is_valid_transition(current, to_state):
            raise InvalidTransition(
                f"Illegal transition {current} → {to_state} for action {action_id}"
            )
        if current in TERMINAL_STATES:
            raise InvalidTransition(
                f"Action {action_id} is in terminal state {current}; no transitions allowed"
            )

        change = ActionStateChange.make(
            action_id=action_id,
            from_state=current,
            to_state=to_state,
            actor_name=actor_name,
            reason=reason,
            outcome=outcome,
        )
        self._store.append_change(change)

        events = state_change_trust_events(action=action, change=change)
        return (change, events)

    # ------------------------------------------------------------------
    # Reads / queries
    # ------------------------------------------------------------------

    def get(self, action_id: str) -> Action | None:
        return self._store.get_action(action_id)

    def all_actions(self) -> tuple[Action, ...]:
        return self._store.all_actions()

    def changes(self, action_id: str) -> tuple[ActionStateChange, ...]:
        return self._store.changes_for(action_id)

    def all_changes(self) -> tuple[ActionStateChange, ...]:
        return self._store.all_changes()

    def current_state(self, action_id: str) -> ActionState:
        changes = self._store.changes_for(action_id)
        if not changes:
            raise KeyError(f"No state changes for action {action_id!r}")
        return derive_current_state(changes)

    def staged_actions(self) -> tuple[Action, ...]:
        """Convenience for Phase 6: actions currently waiting for the user."""
        return tuple(
            a for a in self._store.all_actions()
            if self.current_state(a.id) is ActionState.STAGED
        )

    def actions_in_state(self, state: ActionState) -> tuple[Action, ...]:
        return tuple(
            a for a in self._store.all_actions()
            if self.current_state(a.id) is state
        )

    def __len__(self) -> int:
        return len(self._store)

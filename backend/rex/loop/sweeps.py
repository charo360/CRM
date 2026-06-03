"""
Sweeps — periodic background jobs that look at the Ledger and emit
trust events without changing Action states.

Phase 5 ships ONE sweep:

    sweep_undo_window(ledger, already_swept, now=None)
        Find every Action currently in SENT state whose undo window has
        closed, and emit one ACTION_CLEAN_SEND TrustEvent per Action.

The sweep is idempotent: callers pass in a set of action_ids that have
already been swept and we skip those. The Orchestrator owns the swept
set; the sweep itself remains pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from rex.actions.ledger import Ledger
from rex.actions.primitives import ActionState, UNDO_WINDOW_SECONDS
from rex.actions.transitions import clean_send_event
from rex.ranks.events import TrustEvent


@dataclass(frozen=True)
class SweepReport:
    events: tuple[TrustEvent, ...]
    swept_action_ids: tuple[str, ...]


def sweep_undo_window(
    *,
    ledger: Ledger,
    already_swept: set[str],
    now: datetime | None = None,
) -> SweepReport:
    """
    Return ACTION_CLEAN_SEND events for SENT actions past their undo window.

    For each SENT action:
      - Find the most recent transition into SENT (its `at` timestamp).
      - If now - at >= UNDO_WINDOW_SECONDS AND id not in already_swept,
        emit a CLEAN_SEND event.
    """
    moment = now or datetime.now(timezone.utc)
    window = timedelta(seconds=UNDO_WINDOW_SECONDS)
    events: list[TrustEvent] = []
    swept: list[str] = []

    for action in ledger.actions_in_state(ActionState.SENT):
        if action.id in already_swept:
            continue
        sent_at = _latest_transition_at(ledger, action.id, ActionState.SENT)
        if sent_at is None:
            continue  # defensive — shouldn't happen
        if moment - sent_at < window:
            continue
        events.append(clean_send_event(action=action))
        swept.append(action.id)

    return SweepReport(events=tuple(events), swept_action_ids=tuple(swept))


def _latest_transition_at(
    ledger: Ledger,
    action_id: str,
    target_state: ActionState,
) -> datetime | None:
    """Return the timestamp of the most recent transition INTO target_state."""
    candidates = [
        c for c in ledger.changes(action_id)
        if c.to_state is target_state
    ]
    if not candidates:
        return None
    return max(c.at for c in candidates)

"""
Two pure renderings over the same Ledger data:

    story_render(ledger)   — Rex's-voice reverse-chronological feed.
                             This is the default view inside the Ledger
                             tab on the home screen (REX.md §3.11).

    inspect_rows(ledger)   — dense tabular form for power users.
                             Flat rows ready to be table-rendered by the UI.

Both functions are pure — give them a Ledger snapshot, get strings or
InspectRow objects back. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from rex.actions.ledger import Ledger
from rex.actions.primitives import Action, ActionState


# ---------------------------------------------------------------------------
# Story mode
# ---------------------------------------------------------------------------

def _format_hhmm(dt: datetime) -> str:
    """Local 24-hour HH:MM — the Story view leads with time, not date."""
    return f"{dt.hour:02d}:{dt.minute:02d}"


def _state_suffix(state: ActionState) -> str:
    """One-word suffix shown next to an entry in Story view."""
    return {
        ActionState.PROPOSED: "Proposed.",
        ActionState.STAGED: "Staged for you.",
        ActionState.APPROVED: "Approved.",
        ActionState.SENT: "Sent.",
        ActionState.REJECTED: "Rejected.",
        ActionState.DISMISSED: "Dismissed.",
        ActionState.UNDONE: "Undone.",
        ActionState.FAILED: "Failed.",
    }[state]


def story_render_action(ledger: Ledger, action: Action) -> str:
    """
    Render a single Action as a Story entry.

    Format:
        HH:MM — <summary> <state suffix>
            why: <reasoning>           (only if reasoning present)
            confidence: 91%             (rounded)
            [Review → Send / Dismiss]  (only when STAGED)
    """
    state = ledger.current_state(action.id)
    lines: list[str] = [
        f"{_format_hhmm(action.proposed_at)} — {action.summary} {_state_suffix(state)}"
    ]
    if action.reasoning:
        lines.append(f"    why: {action.reasoning}")
    if action.confidence > 0:
        lines.append(f"    confidence: {int(round(action.confidence * 100))}%")

    if state is ActionState.STAGED:
        lines.append("    [Review → Send / Dismiss]")
    elif state is ActionState.SENT:
        # Show undo affordance — Phase 5 will time-bound this.
        lines.append("    [Undo]")
    return "\n".join(lines)


def story_render(ledger: Ledger, *, limit: int | None = None) -> str:
    """
    Render the entire ledger in Rex's-voice Story mode.

    Reverse-chronological. Most recent first. Pass `limit` to cap.
    """
    actions = sorted(
        ledger.all_actions(),
        key=lambda a: a.proposed_at,
        reverse=True,
    )
    if limit is not None:
        actions = actions[:limit]
    if not actions:
        return "Nothing in the ledger yet."
    return "\n\n".join(story_render_action(ledger, a) for a in actions)


# ---------------------------------------------------------------------------
# Inspect mode
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InspectRow:
    """One row in the Inspect table. UI-agnostic; ready to render."""
    time: datetime
    actor: str
    category: str
    kind: str
    state: str
    summary: str
    confidence_pct: int
    target: str | None
    rank_at_time: str
    action_id: str


def inspect_rows(ledger: Ledger) -> tuple[InspectRow, ...]:
    """
    Return a flat tuple of InspectRow ready for table rendering.

    Sorted reverse-chronologically. One row per Action (NOT per state
    change — that's a separate view for forensic deep-dive).
    """
    actions = sorted(
        ledger.all_actions(),
        key=lambda a: a.proposed_at,
        reverse=True,
    )
    return tuple(
        InspectRow(
            time=a.proposed_at,
            actor=a.actor_name,
            category=a.category,
            kind=a.kind.value,
            state=ledger.current_state(a.id).value,
            summary=a.summary,
            confidence_pct=int(round(a.confidence * 100)),
            target=a.target_subject,
            rank_at_time=a.rank_at_time.display,
            action_id=a.id,
        )
        for a in actions
    )

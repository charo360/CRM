"""
Bridge from a NotebookEntry to the Phase 1 Citation type.

Phase 8 will sit on top of this — given an Action, it will:
    1. call `find_relevant(notebook, ...)` to pick up to 2 entries
    2. call `entry_to_citation(entry, confidence_pct)` on each
    3. pass the resulting Citation objects to `render_citations(...)`
       from `rex.persona.templates`

This module is the seam that keeps the persona layer and the memory
layer cleanly decoupled.
"""

from __future__ import annotations

from rex.memory.entries import NotebookEntry
from rex.persona.templates import Citation


# A citation observation is shown on a single line — newlines in the
# notebook entry must be collapsed for the citation form.
def _flatten_to_single_line(text: str, *, max_chars: int = 160) -> str:
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    # Truncate at the nearest sentence boundary inside the budget.
    cutoff = flat[: max_chars - 1]
    last_period = max(cutoff.rfind("."), cutoff.rfind("!"), cutoff.rfind("?"))
    if last_period > max_chars // 2:
        return cutoff[: last_period + 1]
    return cutoff.rstrip() + "…"


def entry_to_citation(
    entry: NotebookEntry,
    *,
    confidence_pct: int,
) -> Citation:
    """
    Build a Phase 1 Citation from a Notebook entry.

    `confidence_pct` is the Action-side confidence the caller computed
    (NOT a property of the entry itself). Per REX.md §3.13 it must be
    in [0, 99].
    """
    if not (0 <= confidence_pct <= 99):
        raise ValueError(
            f"confidence_pct must be 0–99, got {confidence_pct}"
        )
    return Citation(
        observation=_flatten_to_single_line(entry.text),
        confidence_pct=confidence_pct,
    )

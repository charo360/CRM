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

import re
from typing import Sequence

from rex.memory.entries import NotebookEntry
from rex.memory.notebook import Notebook
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


# ---------------------------------------------------------------------------
# Auto-Citation Matcher Logic (Phase 10)
# ---------------------------------------------------------------------------

def scan_and_attach_citations(
    *,
    summary: str,
    category: str,
    target_subject: str | None,
    notebook: Notebook,
) -> tuple[str, ...]:
    """
    Scans the Notebook to find highly relevant context entries to cite.
    Returns up to TWO matching NotebookEntry IDs.

    Matches by:
        1. target_subject match (e.g. "Patel", "Acme") -> High priority
        2. category name match inside tags/buckets -> Medium priority
        3. keyword matches between action summary and entry text -> Relevance density
    """
    scores: list[tuple[float, str]] = []

    # Get all entries from store safely
    all_entries = notebook._store.all()

    for entry in all_entries:
        score = 0.0

        # Match 1: Subject match (Strongest signal)
        if target_subject and entry.subject:
            if target_subject.lower() == entry.subject.lower():
                score += 5.0

        # Match 2: Category match via tags
        if category and entry.tags:
            if category.lower() in [t.lower() for t in entry.tags]:
                score += 2.0

        # Match 3: Keyword density intersection
        # Extract alphanumeric words from summary
        summary_words = set(re.findall(r"\b\w{3,}\b", summary.lower()))
        entry_words = set(re.findall(r"\b\w{3,}\b", entry.text.lower()))

        intersection = summary_words.intersection(entry_words)
        score += len(intersection) * 0.5

        # We need a small floor to prevent completely irrelevant matches
        if score >= 1.0:
            scores.append((score, entry.id))

    # Sort descending by score, stable ID fallback
    scores.sort(key=lambda x: (-x[0], x[1]))

    # Cap at 2 (REX.md §3.13 limits inline citations to at most 2 per action)
    return tuple(entry_id for _, entry_id in scores[:2])


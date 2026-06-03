"""
Notebook — the high-level facade over the NotebookStore.

This is the object the rest of the codebase will hold. It wires up:
    - voice validation on add / update
    - subject normalization
    - per-bucket queries
    - relevance retrieval for Phase 8 citations

Pure module. No I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rex.memory.buckets import Bucket
from rex.memory.entries import NotebookEntry
from rex.memory.store import NotebookStore, InMemoryNotebookStore
from rex.principals.visibility import Visibility
from rex.memory.voice_check import (
    NotebookVoiceReport,
    validate_notebook_entry,
)


class NotebookVoiceError(ValueError):
    """Raised when a write would land an entry that fails HARD voice rules."""

    def __init__(self, report: NotebookVoiceReport):
        self.report = report
        super().__init__(
            "Notebook entry failed voice validation: "
            + "; ".join(f.detail for f in report.flags if f.severity.value == "hard")
        )


class Notebook:
    """
    User-facing operations on the Notebook.

    The store can be swapped (Protocol-typed). Default to in-memory for
    tests and the offline replay path.
    """

    def __init__(self, store: NotebookStore | None = None) -> None:
        self._store: NotebookStore = store if store is not None else InMemoryNotebookStore()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add(
        self,
        *,
        bucket: Bucket,
        text: str,
        subject: str | None = None,
        source_event_ids: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        strict_voice: bool = True,
        visibility: Visibility | None = None,
    ) -> NotebookEntry:
        """
        Add a new entry. Voice-validates first.

        If `strict_voice=True` (default), HARD voice violations raise.
        Set strict_voice=False for user-supplied edits where the user
        is allowed to write anything they want — Rex's voice rules apply
        to Rex's writing, not the user's.
        """
        if strict_voice:
            report = validate_notebook_entry(text, bucket, subject)
            if not report.passed:
                raise NotebookVoiceError(report)

        entry = NotebookEntry.new(
            bucket=bucket,
            text=text,
            subject=_normalize_subject(subject),
            source_event_ids=source_event_ids,
            tags=tags,
            visibility=visibility,
        )
        self._store.put(entry)
        return entry

    def update_text(
        self,
        entry_id: str,
        new_text: str,
        *,
        by_user: bool = True,
    ) -> NotebookEntry:
        """
        Replace the text on an existing entry. By default this is treated
        as a user edit (no voice validation). When Rex himself rewrites
        an entry, pass by_user=False AND validate first via the public
        validator.
        """
        existing = self._store.get(entry_id)
        if existing is None:
            raise KeyError(f"No notebook entry with id={entry_id!r}")
        updated = existing.with_text(new_text, by_user=by_user)
        self._store.put(updated)
        return updated

    def delete(self, entry_id: str) -> bool:
        return self._store.delete(entry_id)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, entry_id: str) -> NotebookEntry | None:
        return self._store.get(entry_id)

    def all(self) -> tuple[NotebookEntry, ...]:
        return self._store.all()

    def by_bucket(self, bucket: Bucket) -> tuple[NotebookEntry, ...]:
        return self._store.by_bucket(bucket)

    def by_subject(self, subject: str) -> tuple[NotebookEntry, ...]:
        return self._store.by_subject(_normalize_subject(subject) or "")

    def count_by_bucket(self) -> dict[Bucket, int]:
        return {
            b: len(self._store.by_bucket(b))
            for b in Bucket
        }

    def __len__(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Subject normalization
# ---------------------------------------------------------------------------

def _normalize_subject(subject: str | None) -> str | None:
    """
    Subjects are presented as Rex would write them: capitalized for People
    ("Patel"), lower-case category names for Lanes ("payments"). For tests
    and lookups we normalize whitespace and strip trailing punctuation.
    """
    if subject is None:
        return None
    s = subject.strip()
    return s if s else None


# ---------------------------------------------------------------------------
# Relevance retrieval (Phase 8 will use this for citations)
# ---------------------------------------------------------------------------

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


def find_relevant(
    notebook: Notebook,
    *,
    subject: str | None = None,
    category: str | None = None,
    query: str | None = None,
    limit: int = 2,
) -> tuple[NotebookEntry, ...]:
    """
    Return up to `limit` entries most relevant to the given hints.

    Ranking is simple in Phase 3 — exact-subject matches first, then tag
    matches, then token-overlap with `query`. Phase 8 may swap to a
    vector retrieval; the contract here is stable.
    """
    pool = list(notebook.all())
    if not pool:
        return ()

    norm_subject = _normalize_subject(subject)
    q_tokens: set[str] = _tokenize(query) if query else set()
    cat_low = (category or "").strip().lower()

    def score(entry: NotebookEntry) -> tuple[int, int, int]:
        # Higher tuples sort earlier. (subject_match, tag_match, token_overlap)
        s_match = 0
        if norm_subject and entry.subject and entry.subject.lower() == norm_subject.lower():
            s_match = 2
        elif norm_subject and entry.subject and norm_subject.lower() in entry.subject.lower():
            s_match = 1

        tag_match = 0
        if cat_low and cat_low in (t.lower() for t in entry.tags):
            tag_match = 1

        tok_overlap = 0
        if q_tokens:
            tok_overlap = len(q_tokens & _tokenize(entry.text))

        return (s_match, tag_match, tok_overlap)

    scored = [(score(e), e) for e in pool]
    # Keep only entries with at least *some* relevance.
    scored = [(s, e) for s, e in scored if s != (0, 0, 0)]
    scored.sort(key=lambda x: x[0], reverse=True)
    return tuple(e for _, e in scored[:limit])

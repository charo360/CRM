"""
NotebookEntry — one observation by Rex.

Frozen + hashable so entries are safe to pass around and compare. The
store is the only thing that mutates collections of entries; entries
themselves are replaced (immutable update) rather than edited in place.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from rex.memory.buckets import Bucket


def new_entry_id() -> str:
    """Globally unique entry id."""
    return uuid.uuid4().hex


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class NotebookEntry:
    """
    One observation in the Notebook.

    Fields
    ------
    id              : stable identifier.
    bucket          : PEOPLE / PATTERNS / LANES.
    subject         : "Patel" for a person; "payments" (Category) for a lane;
                      None for a Pattern (which is generic).
    text            : the prose observation in Rex's voice.
    created_at      : when Rex first wrote this.
    updated_at      : last mutation (== created_at if never edited).
    edited_by_user  : True if the user has touched this entry.
    source_event_ids: TrustEvent ids that informed this observation.
                      Empty tuple is fine — some observations are upstream
                      of the event log (e.g. learned from Day 0 interview).
    tags            : optional indexing aids (e.g. category names).
    """

    id: str
    bucket: Bucket
    subject: str | None
    text: str
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    edited_by_user: bool = False
    source_event_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    # --- factories ------------------------------------------------------

    @classmethod
    def new(
        cls,
        *,
        bucket: Bucket,
        text: str,
        subject: str | None = None,
        source_event_ids: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> "NotebookEntry":
        """Create a fresh entry with auto id and timestamps."""
        now = _utc_now()
        if bucket.subject_required and not subject:
            raise ValueError(
                f"{bucket.display} entries require a subject"
            )
        return cls(
            id=new_entry_id(),
            bucket=bucket,
            subject=subject,
            text=text.strip(),
            created_at=now,
            updated_at=now,
            source_event_ids=tuple(source_event_ids),
            tags=tuple(tags),
        )

    # --- immutable updates ---------------------------------------------

    def with_text(self, text: str, *, by_user: bool = False) -> "NotebookEntry":
        """Return a copy with new text and refreshed updated_at."""
        return replace(
            self,
            text=text.strip(),
            updated_at=_utc_now(),
            edited_by_user=self.edited_by_user or by_user,
        )

    def with_added_source(self, event_id: str) -> "NotebookEntry":
        """Return a copy with one more source event recorded."""
        if event_id in self.source_event_ids:
            return self
        return replace(
            self,
            source_event_ids=self.source_event_ids + (event_id,),
            updated_at=_utc_now(),
        )

    def with_tags(self, tags: tuple[str, ...]) -> "NotebookEntry":
        return replace(self, tags=tuple(tags), updated_at=_utc_now())

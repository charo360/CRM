"""
NotebookStore — Protocol + in-memory implementation.

Same shape as rex.ranks.store: append-only-ish semantics with explicit
update / delete operations. Phase 4 will swap in a DB-backed store.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Protocol, runtime_checkable

from rex.memory.buckets import Bucket
from rex.memory.entries import NotebookEntry


@runtime_checkable
class NotebookStore(Protocol):
    """
    Storage contract for the Notebook.

    Implementations must:
      - Treat NotebookEntry as immutable. `put` replaces by id.
      - Return snapshot tuples from query methods (safe to iterate).
      - Be tolerant of missing ids on `get` (return None) and `delete` (no-op).
    """

    def put(self, entry: NotebookEntry) -> None: ...
    def get(self, entry_id: str) -> NotebookEntry | None: ...
    def delete(self, entry_id: str) -> bool: ...
    def all(self) -> tuple[NotebookEntry, ...]: ...
    def by_bucket(self, bucket: Bucket) -> tuple[NotebookEntry, ...]: ...
    def by_subject(self, subject: str) -> tuple[NotebookEntry, ...]: ...
    def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[NotebookEntry]: ...


class InMemoryNotebookStore:
    """
    Dict-backed implementation. Single-process, thread-unsafe — same
    assumptions as the InMemoryEventStore in Phase 2.
    """

    __slots__ = ("_by_id",)

    def __init__(self, initial: Iterable[NotebookEntry] = ()) -> None:
        self._by_id: dict[str, NotebookEntry] = {e.id: e for e in initial}

    def put(self, entry: NotebookEntry) -> None:
        self._by_id[entry.id] = entry

    def get(self, entry_id: str) -> NotebookEntry | None:
        return self._by_id.get(entry_id)

    def delete(self, entry_id: str) -> bool:
        return self._by_id.pop(entry_id, None) is not None

    def all(self) -> tuple[NotebookEntry, ...]:
        # Stable order: by created_at, then by id for deterministic tests.
        return tuple(sorted(
            self._by_id.values(),
            key=lambda e: (e.created_at, e.id),
        ))

    def by_bucket(self, bucket: Bucket) -> tuple[NotebookEntry, ...]:
        return tuple(
            e for e in self.all() if e.bucket is bucket
        )

    def by_subject(self, subject: str) -> tuple[NotebookEntry, ...]:
        s = subject.lower()
        return tuple(
            e for e in self.all()
            if e.subject is not None and e.subject.lower() == s
        )

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[NotebookEntry]:
        return iter(self.all())

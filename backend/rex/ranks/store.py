"""
Event store — append-only.

Phase 2 ships an in-memory implementation suitable for tests and offline
replay. Phase 4 will add a DB-backed implementation behind the same
Protocol. Nothing outside this module should hold a list of events —
always go through the store.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Protocol, runtime_checkable

from rex.ranks.events import TrustEvent


@runtime_checkable
class EventStore(Protocol):
    """
    Append-only interface. Implementations must guarantee:
      - `append` is total ordering preserving (insert order == iteration order)
      - Stored events are immutable from the caller's perspective
      - `all_events` returns a snapshot tuple (safe to iterate)
    """

    def append(self, event: TrustEvent) -> None: ...
    def all_events(self) -> tuple[TrustEvent, ...]: ...
    def events_for(
        self, *, actor_name: str | None = None,
        category: str | None = None,
    ) -> tuple[TrustEvent, ...]: ...
    def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[TrustEvent]: ...


class InMemoryEventStore:
    """
    Simple list-backed implementation. Thread-unsafe by design — Phase 2
    is offline / single-threaded. Phase 4 will add a real store.
    """

    __slots__ = ("_events",)

    def __init__(self, initial: Iterable[TrustEvent] = ()) -> None:
        self._events: list[TrustEvent] = list(initial)

    def append(self, event: TrustEvent) -> None:
        self._events.append(event)

    def all_events(self) -> tuple[TrustEvent, ...]:
        return tuple(self._events)

    def events_for(
        self, *, actor_name: str | None = None,
        category: str | None = None,
    ) -> tuple[TrustEvent, ...]:
        out: list[TrustEvent] = []
        for e in self._events:
            if actor_name is not None and e.actor_name != actor_name:
                continue
            if category is not None and e.category != category:
                continue
            out.append(e)
        return tuple(out)

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[TrustEvent]:
        return iter(tuple(self._events))

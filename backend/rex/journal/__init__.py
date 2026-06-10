"""
rex.journal — Phase 7: Rex Journal Writer.

Pure backend journal entry generation. No I/O. No LLM calls.
"""

from rex.journal.writer import (
    JournalEntry,
    JournalEventKind,
    JournalWriter,
    write_entry_for_trust_event,
    write_entries_for_events,
)

__all__ = [
    "JournalEntry",
    "JournalEventKind",
    "JournalWriter",
    "write_entry_for_trust_event",
    "write_entries_for_events",
]

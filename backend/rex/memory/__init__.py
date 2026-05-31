"""
rex.memory — The Notebook (REX.md §3.13).

Phase 3 of the Rex build. Like rex.persona and rex.ranks, this is pure:
no DB writes, no LLM calls. In-memory store with a Protocol-shaped
interface so Phase 4 can swap in a real persistence layer.

THE NOTEBOOK
============
Rex's memory of the user's business. NOT a CRM. NOT a settings page.
A diary of observations written in Rex's voice, organized into three
buckets:

    People    — what Rex has noticed about specific humans
    Patterns  — recurring mechanics Rex has observed about how the
                user works (windows, cadences, response rates)
    Lanes     — which categories Rex stays out of, and why

INVIOLABLES (REX.md §3.13)
==========================
    1. Entries are PROSE, never database fields.
       ❌ "Contact: Patel | Preference: Direct"
       ✅ "Patel — responds to directness, not warmth. Tried warm twice."
    2. Entries are written as Rex's witnessed observations, not advice.
       ❌ "You should always send before 9am."
       ✅ "Outreach before 9am replies twice as often as after noon."
    3. The user can read, edit, or delete any entry at any time.
    4. Every entry can cite back to the TrustEvents that informed it
       (source_event_ids) — the audit trail for "why does Rex know this?".

PUBLIC API
==========
    Bucket                Three-bucket enum (PEOPLE / PATTERNS / LANES).
    NotebookEntry         Frozen dataclass — one observation.
    NotebookStore         Protocol for storage.
    InMemoryNotebookStore Default implementation.
    Notebook              High-level facade. The thing the rest of the
                          codebase will hold.
    NotebookVoiceReport   Result of `validate_notebook_entry`.
    validate_notebook_entry(text, bucket)
                          Notebook-specific voice + shape checks on top
                          of the generic Phase 1 validator.
    entry_to_citation(entry, confidence_pct)
                          Bridge to Phase 1's Citation type.
    find_relevant(notebook, subject=None, category=None, query=None, limit=2)
                          Retrieve the most relevant entries for an
                          Action — used by Phase 8 (citations).
"""

from rex.memory.buckets import Bucket
from rex.memory.entries import NotebookEntry, new_entry_id
from rex.memory.store import NotebookStore, InMemoryNotebookStore
from rex.memory.notebook import Notebook, find_relevant
from rex.memory.voice_check import (
    NotebookVoiceReport,
    NotebookVoiceIssue,
    validate_notebook_entry,
)
from rex.memory.citations import entry_to_citation

__all__ = [
    "Bucket",
    "NotebookEntry", "new_entry_id",
    "NotebookStore", "InMemoryNotebookStore",
    "Notebook", "find_relevant",
    "NotebookVoiceReport", "NotebookVoiceIssue",
    "validate_notebook_entry",
    "entry_to_citation",
]

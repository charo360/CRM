"""
Rex — The AI Chief of Staff.

This package is the new product layer described in REX.md at the repo root.
Everything in here serves a single sentence:

    "Rex writes like a special forces operator who is slowly, almost
     reluctantly, becoming someone who gives a damn."

Subpackages are added phase-by-phase per the build sequencing in REX.md:

    rex.persona     — Phase 1: voice engine, prompt specs, templates  (this phase)
    rex.ranks       — Phase 2: rank state machine + trust events
    rex.memory      — Phase 3: notebook (Rex's-voice prose)
    rex.actions     — Phase 4: action layer + ledger
    rex.loop        — Phase 5: overnight loop
    rex.briefing    — Phase 6: daily letter compiler
    rex.journal     — Phase 7: auto-writer with voice evolution
    ...

Phase 1 is intentionally pure — no I/O, no LLM calls, no DB writes.
Just the rules and templates every other phase will obey.
"""

from rex.persona.soul import SOUL_SENTENCE, DECISION_TESTS

__all__ = ["SOUL_SENTENCE", "DECISION_TESTS"]

"""
rex.briefing — The Single-Column Letter (REX.md §3.10) and Home Screen snapshot.

Phase 6 of the Rex build. Pure backend: no I/O, no LLM, no frontend code.
The output is a JSON-serializable snapshot the future Phase 9 UI will render.

THE LETTER, ONE-LINE PROMISE
============================
"Tuesday. 6:47am.
 Quiet night overall — but three things need you.

  06:47 — Drafted Patel follow-up. 9 days cold.
      ↳ Memory: Responds to directness, not warmth. — 91% confidence
      Confidence 91%. [Review → Send / Dismiss]
  ...

 — Rex"

INVIOLABLES (REX.md §3.10)
==========================
    1. Maximum THREE staged-action lines per Letter. Everything else
       lives in the full ledger below the fold.
    2. Voice always Rex's. `validate_voice` clears the prose.
    3. Sign-off is exactly "— Rex" on its own line.
    4. Never fabricated content — only states the system observes.
    5. The Letter is a SNAPSHOT. Not retained. Not editable.

PUBLIC API
==========
    Letter           Frozen dataclass — opener + body + parsed actions.
    LetterAction     One staged-action item rendered into the Letter.
    HomeScreen       Full top-of-app snapshot.
    PendingPromotion Sub-Agent recommendation awaiting user decision.

    pick_top_actions(actions, limit=3)
                     Pure ranker over a list of STAGED Actions.
    opener_for(now, relationship_day)
                     Day-aware opener line (drives subtle voice evolution).
    compose_letter(*, staged_actions, now, relationship_day, ledger)
                     Pure Letter composer.
    build_home_screen(orchestrator, *, now=None, relationship_day=1)
                     Pull-everything-together aggregator.
"""

from rex.briefing.selector import pick_top_actions, ActionScore
from rex.briefing.opener import opener_for, BriefingPhase, briefing_phase_for_day
from rex.briefing.letter import (
    Letter,
    LetterAction,
    compose_letter,
    LetterShapeError,
)
from rex.briefing.home_screen import (
    HomeScreen,
    PendingPromotion,
    StandingSummary,
    build_home_screen,
)

__all__ = [
    "Letter", "LetterAction", "compose_letter", "LetterShapeError",
    "pick_top_actions", "ActionScore",
    "opener_for", "BriefingPhase", "briefing_phase_for_day",
    "HomeScreen", "PendingPromotion", "StandingSummary",
    "build_home_screen",
]

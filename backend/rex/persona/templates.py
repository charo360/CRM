"""
Canonical templates and render helpers.

This module centralizes every Rex-shaped output scaffold so the rest of the
codebase never invents one ad-hoc. If a string format shows up twice in any
other module, it probably belongs here instead.

Pure module: no I/O, no LLM, no state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


# ---------------------------------------------------------------------------
# Ranks (REX.md §3.7)
# ---------------------------------------------------------------------------

RANK_OBSERVER = "Observer"
RANK_DRAFTER = "Drafter"
RANK_SENDER = "Sender"
RANK_OPERATOR = "Operator"
RANK_CHIEF_OF_STAFF = "Chief of Staff"

ALL_RANKS: tuple[str, ...] = (
    RANK_OBSERVER,
    RANK_DRAFTER,
    RANK_SENDER,
    RANK_OPERATOR,
    RANK_CHIEF_OF_STAFF,
)


def rank_index(rank: str) -> int:
    """Return 0..4 for valid ranks. Raises if unknown."""
    return ALL_RANKS.index(rank)


def can_autonomously_execute(rank: str) -> bool:
    """Sender and above may act without staging in their Category."""
    return rank_index(rank) >= rank_index(RANK_SENDER)


# ---------------------------------------------------------------------------
# Notebook buckets (REX.md §3.13)
# ---------------------------------------------------------------------------

NOTEBOOK_BUCKET_PEOPLE = "People"
NOTEBOOK_BUCKET_PATTERNS = "Patterns"
NOTEBOOK_BUCKET_LANES = "Lanes"

NOTEBOOK_BUCKETS: tuple[str, ...] = (
    NOTEBOOK_BUCKET_PEOPLE,
    NOTEBOOK_BUCKET_PATTERNS,
    NOTEBOOK_BUCKET_LANES,
)


# ---------------------------------------------------------------------------
# Briefing letter tokens (REX.md §3.10)
# ---------------------------------------------------------------------------

# Inline action tokens — the exact bracket strings the UI will scan for.
ACTION_TOKEN_REVIEW_SEND = "[Review → Send / Dismiss]"
ACTION_TOKEN_HANDLE_MANUALLY = "[Handle manually]"
ACTION_TOKEN_APPROVE = "[Approve]"
ACTION_TOKEN_UNDO = "[Undo]"

BRIEFING_SIGN_OFF = "— Rex"

# Canonical "nothing happened" letter (used when overnight produced no items).
QUIET_NIGHT_LETTER_TEMPLATE = (
    "{opener}\n"
    "\n"
    "Quiet night. Nothing needs you this morning.\n"
    "\n"
    "I'll keep watching. Full ledger below if you want it.\n"
    "\n"
    f"{BRIEFING_SIGN_OFF}\n"
)


# ---------------------------------------------------------------------------
# Journal (REX.md §3.9)
# ---------------------------------------------------------------------------

def journal_day_anchor(day: int) -> str:
    """The on-its-own-line anchor that opens every journal entry."""
    if day < 1:
        raise ValueError("relationship day must be >= 1")
    return f"Day {day}."


# Verdict closers, by phase. Only the calibrated phase should be used at write time.
JOURNAL_VERDICT_CLOSERS_BLENDED: tuple[str, ...] = (
    "Fair.", "Noted.", "Earned.", "On me.", "Rebuilding.", "Filed.",
)
JOURNAL_VERDICT_CLOSERS_EARNED: tuple[str, ...] = (
    "I won't forget that.", "That's the pattern now.", "Filed.", "Worth knowing.",
)
JOURNAL_VERDICT_CLOSERS_PERSPECTIVE: tuple[str, ...] = (
    "We're past that now.", "Different from where we started.", "Long way from Day 1.",
)


# ---------------------------------------------------------------------------
# Citations (REX.md §3.13)
# ---------------------------------------------------------------------------

# The exact format the UI renders under a Rex action.
CITATION_ARROW = "↳"  # U+21B3


@dataclass(frozen=True)
class Citation:
    observation: str   # Direct quote from the Notebook, one line.
    confidence_pct: int  # 0–99 integer.


def render_citation(cite: Citation) -> str:
    """Render a single citation block in the canonical format."""
    if not (0 <= cite.confidence_pct <= 99):
        raise ValueError("confidence_pct must be 0–99")
    obs = cite.observation.strip().strip('"').strip("'")
    return (
        f'{CITATION_ARROW} Memory: "{obs}"\n'
        f'   Confidence: {cite.confidence_pct}%'
    )


def render_citations(cites: Sequence[Citation]) -> str:
    """
    Render up to TWO citations stacked. More than two is a code smell —
    the system_prompt directive caps memory cites per action at 2.
    """
    if len(cites) > 2:
        raise ValueError("Maximum two citations per action")
    return "\n".join(render_citation(c) for c in cites)


# ---------------------------------------------------------------------------
# Rank-change announcements (used by Journal in PROMOTION / DEMOTION modes)
# ---------------------------------------------------------------------------

def promotion_headline(category: str, new_rank: str) -> str:
    """e.g. 'Earned Sender on outreach.'"""
    return f"Earned {new_rank} on {category.lower()}."


def demotion_headline(category: str, new_rank: str) -> str:
    """e.g. 'Demoted to Drafter on invoices.'"""
    return f"Demoted to {new_rank} on {category.lower()}."


def probation_headline(category: str) -> str:
    return f"On probation in {category.lower()}. Drafting only, asking before each send."


def probation_lifted_headline(category: str, new_rank: str) -> str:
    return f"Restored to {new_rank} on {category.lower()}."


# ---------------------------------------------------------------------------
# Day 0 — the five canonical interview questions (REX.md §3.12)
# ---------------------------------------------------------------------------

INTERVIEW_QUESTIONS: tuple[str, ...] = (
    "Quick. What's keeping you up at night?",
    "Who's the most important customer you have right now?",
    "What's a follow-up you've been putting off?",
    "What can I never do without asking you first?",
    "What time should I file your briefing in the morning?",
)


# ---------------------------------------------------------------------------
# Validation helpers used by tests
# ---------------------------------------------------------------------------

def assert_inviolable_briefing_shape(letter: str) -> None:
    """
    Raises AssertionError if a briefing letter violates structural inviolables.
    (Voice violations are checked by validate_voice; this checks shape only.)
    """
    if not letter.rstrip().endswith(BRIEFING_SIGN_OFF):
        raise AssertionError(
            f"Briefing must end with sign-off line '{BRIEFING_SIGN_OFF}'."
        )
    # Cap action items at 3.
    action_count = (
        letter.count(ACTION_TOKEN_REVIEW_SEND)
        + letter.count(ACTION_TOKEN_HANDLE_MANUALLY)
    )
    if action_count > 3:
        raise AssertionError(
            f"Briefing has {action_count} action items; maximum is 3."
        )

"""
Notebook-specific voice validation.

Builds on Phase 1's `rex.persona.validate_voice` (which catches emoji,
hedging, apologies, sycophancy, etc.) and adds rules unique to Notebook
entries per REX.md §3.13:

    A. No database-field formatting.
       ❌ "Contact: Patel | Preference: Direct"
    B. No first-person reflection ("I noticed", "I observed", "I think").
       The entry is a witnessed observation, not Rex narrating his thoughts.
    C. No advice to the reader ("you should", "you ought to").
       Entries describe what is, not what to do.
    D. Short — at most 3 sentences. Soft signal.
    E. Subject is required for People + Lanes (enforced at NotebookEntry
       level, but reported here so callers can validate without constructing).

Pure module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from rex.memory.buckets import Bucket
from rex.persona.voice_rules import validate_voice, Severity


class NotebookVoiceIssue(str, Enum):
    FIELD_STYLE = "field_style"             # rule A
    FIRST_PERSON_REFLECTION = "first_person_reflection"  # rule B
    ADVICE_TO_READER = "advice_to_reader"   # rule C
    TOO_MANY_SENTENCES = "too_many_sentences"  # rule D
    MISSING_SUBJECT = "missing_subject"     # rule E
    GENERIC_VOICE_VIOLATION = "generic_voice_violation"   # caught by Phase 1


@dataclass(frozen=True)
class NotebookVoiceFlag:
    issue: NotebookVoiceIssue
    severity: Severity
    detail: str


@dataclass(frozen=True)
class NotebookVoiceReport:
    text: str
    bucket: Bucket
    subject: str | None
    flags: tuple[NotebookVoiceFlag, ...]
    score: float  # 0.0–1.0

    @property
    def passed(self) -> bool:
        """True iff there are zero HARD flags."""
        return not any(f.severity is Severity.HARD for f in self.flags)


# ---------------------------------------------------------------------------
# Pattern banks (specific to Notebook entries)
# ---------------------------------------------------------------------------

# Rule A — field-style detection.
# A colon followed by 1-2 words followed by a separator (|, ;, newline) is a
# strong tell of "Contact: X | Preference: Y" style.
_FIELD_STYLE_PATTERN = re.compile(
    r"(?im)^[ \t]*([A-Z][A-Za-z ]{1,30}:[ \t][^|\n;]{1,40})([|;]|\n)"
)
# Also catch labeled-line format: "Name: Patel\nEmail: patel@..."
_LABELED_LINE_PATTERN = re.compile(
    r"(?im)^[ \t]*[A-Z][A-Za-z ]{1,30}:[ \t]\S"
)

# Rule B — first-person reflection.
# "I think / I believe" are already caught by Phase 1 as HEDGING.
# These are the additional reflective verbs the general validator misses.
_REFLECTION_PHRASES: tuple[str, ...] = (
    "i noticed",
    "i observed",
    "i realized",
    "i feel that",
    "i sense",
    "i suspect",
    "it strikes me",
    "in my view",
    "my take",
    "i wonder",
)

# Rule C — advice patterns.
_ADVICE_PHRASES: tuple[str, ...] = (
    "you should",
    "you ought",
    "you must",
    "you need to",
    "you have to",
    "i'd recommend",
    "i would recommend",
    "i recommend",
    "my recommendation",
    "be sure to",
    "make sure to",
    "remember to",
    "don't forget to",
)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def _count_sentences(text: str) -> int:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return len([p for p in parts if p.strip()])


def validate_notebook_entry(
    text: str,
    bucket: Bucket,
    subject: str | None = None,
) -> NotebookVoiceReport:
    """
    Validate a candidate Notebook entry for voice and shape compliance.
    """
    flags: list[NotebookVoiceFlag] = []
    t = text.strip()
    t_low = t.lower()

    # Rule E — missing subject for People / Lanes
    if bucket.subject_required and (subject is None or not subject.strip()):
        flags.append(NotebookVoiceFlag(
            issue=NotebookVoiceIssue.MISSING_SUBJECT,
            severity=Severity.HARD,
            detail=f"{bucket.display} entries require a subject",
        ))

    # Rule A — field-style
    if _FIELD_STYLE_PATTERN.search(t) or _LABELED_LINE_PATTERN.match(t):
        # The labeled-line check matches even a single "Label: value" — we
        # only flag if it looks like multiple lines / pipes are present too.
        if "|" in t or "\n" in t or _LABELED_LINE_PATTERN.search(t):
            flags.append(NotebookVoiceFlag(
                issue=NotebookVoiceIssue.FIELD_STYLE,
                severity=Severity.HARD,
                detail="Looks like database fields. Use prose.",
            ))

    # Rule B — first-person reflection
    for phrase in _REFLECTION_PHRASES:
        if phrase in t_low:
            flags.append(NotebookVoiceFlag(
                issue=NotebookVoiceIssue.FIRST_PERSON_REFLECTION,
                severity=Severity.HARD,
                detail=(
                    f"First-person reflection: {phrase!r}. State the "
                    "observation as witnessed fact."
                ),
            ))

    # Rule C — advice to reader
    for phrase in _ADVICE_PHRASES:
        if phrase in t_low:
            flags.append(NotebookVoiceFlag(
                issue=NotebookVoiceIssue.ADVICE_TO_READER,
                severity=Severity.HARD,
                detail=(
                    f"Advice phrase: {phrase!r}. Notebook describes what "
                    "you saw, not what to do."
                ),
            ))

    # Rule D — sentence count
    if _count_sentences(t) > 3:
        flags.append(NotebookVoiceFlag(
            issue=NotebookVoiceIssue.TOO_MANY_SENTENCES,
            severity=Severity.SOFT,
            detail=(
                f"More than 3 sentences ({_count_sentences(t)}). "
                "Keep Notebook entries tight."
            ),
        ))

    # Compose generic Phase 1 voice violations
    generic = validate_voice(t)
    for v in generic.violations:
        flags.append(NotebookVoiceFlag(
            issue=NotebookVoiceIssue.GENERIC_VOICE_VIOLATION,
            severity=v.severity,
            detail=f"[{v.rule_id}] {v.message}",
        ))

    # Score = (1.0 - 0.2 per HARD - 0.05 per SOFT), floored.
    hard = sum(1 for f in flags if f.severity is Severity.HARD)
    soft = sum(1 for f in flags if f.severity is Severity.SOFT)
    score = max(0.0, 1.0 - 0.2 * hard - 0.05 * soft)

    return NotebookVoiceReport(
        text=t,
        bucket=bucket,
        subject=subject,
        flags=tuple(flags),
        score=round(score, 3),
    )

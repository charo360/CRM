"""
Journal synthesis — engagement entries generated from time, not from TrustEvents.

These are the entries that make the Journal feel alive:
  • MILESTONE — written once when a phase boundary is crossed (Day 15, 31, 61, 91)
  • DAILY_ANCHOR — one ambient entry on quiet days so the streak keeps going
  • RETURNED — a single re-emergence line when the user comes back after silence

All entries here are *synthesized* — they carry no TrustEvent. IDs are stable
per (kind, day) so React can key them and we never duplicate inside a day.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rex.journal.writer import JournalEntry, JournalEventKind
from rex.persona.voice_evolution import JournalPhase, voice_for_day
from rex.principals.visibility import visibility_founder_only


# ---------------------------------------------------------------------------
# Phase-flip boundaries (the day on which a new phase BEGINS).
# Mirror voice_evolution._ALL_CALIBRATIONS.
# ---------------------------------------------------------------------------

PHASE_FLIP_DAYS: dict[JournalPhase, int] = {
    JournalPhase.SHIFTING: 15,
    JournalPhase.BLENDED: 31,
    JournalPhase.EARNED: 61,
    JournalPhase.PERSPECTIVE: 91,
}


# Body text for each milestone. Written in the voice OF the phase being entered.
MILESTONE_BODY: dict[JournalPhase, str] = {
    JournalPhase.SHIFTING: (
        "Two weeks. I have opinions now. "
        "Small ones. Watching the patterns."
    ),
    JournalPhase.BLENDED: (
        "A month. Long enough to commit to verdicts. "
        "Fair. Rebuilding. Earned. I'll say them when they fit."
    ),
    JournalPhase.EARNED: (
        "Two months in. The pattern recognition starts here. "
        "I won't forget what worked."
    ),
    JournalPhase.PERSPECTIVE: (
        "Three months. We have history now. "
        "I'll reach back when it matters."
    ),
}


# Ambient daily anchors. One pool per phase so the tone matches.
# Selected deterministically by (day mod len) so a given day always yields
# the same line — feels intentional, not random.
_DAILY_OBSERVING: tuple[str, ...] = (
    "Quiet. Watching.",
    "Day {day}. Holding.",
    "No movement worth noting. Filed.",
    "Steady. Observing.",
    "Day {day}. Standing post.",
)

_DAILY_SHIFTING: tuple[str, ...] = (
    "Quiet day. Pattern still holding.",
    "Day {day}. No movement. Noted.",
    "Steady. The shape is forming.",
    "Holding the line.",
    "Day {day}. Watching for the next signal.",
)

_DAILY_BLENDED: tuple[str, ...] = (
    "Quiet day. That's fine. Fair.",
    "Day {day}. Nothing broke. Earned.",
    "No fires. The system held.",
    "Steady hand on it. Filed.",
    "Day {day}. Held position.",
)

_DAILY_EARNED: tuple[str, ...] = (
    "Quiet day. We've earned a few of those.",
    "Day {day}. Steady. The trust held.",
    "Nothing urgent. Pattern recognized.",
    "No fires. That's the pattern now.",
    "Day {day}. Held what we built.",
)

_DAILY_PERSPECTIVE: tuple[str, ...] = (
    "Quiet day. There've been a lot of these. We're past noticing.",
    "Day {day}. Months in. The quiet is the win.",
    "Nothing urgent. That's the shape of this now.",
    "Steady, the way it's been.",
    "Day {day}. Held the line. Again.",
)

_DAILY_POOLS: dict[JournalPhase, tuple[str, ...]] = {
    JournalPhase.OBSERVING: _DAILY_OBSERVING,
    JournalPhase.SHIFTING: _DAILY_SHIFTING,
    JournalPhase.BLENDED: _DAILY_BLENDED,
    JournalPhase.EARNED: _DAILY_EARNED,
    JournalPhase.PERSPECTIVE: _DAILY_PERSPECTIVE,
}


# Re-emergence lines (after >= 2 day gap). Days-gone-aware.
def _returned_body(days_gone: int, phase: JournalPhase) -> str:
    if days_gone <= 2:
        base = "Two days quiet. Held the line."
    elif days_gone <= 4:
        base = f"{days_gone} days quiet. Held the line. Back to it."
    elif days_gone <= 10:
        base = f"{days_gone} days. Long enough to notice. Picked it up where you left it."
    else:
        base = f"{days_gone} days gone. The work waited. So did I."

    if phase in (JournalPhase.OBSERVING, JournalPhase.SHIFTING):
        return base
    if phase is JournalPhase.PERSPECTIVE:
        return f"{base} We've been here before."
    return base  # BLENDED / EARNED keep it terse


# ---------------------------------------------------------------------------
# Public synthesis entry-points
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _word_count(text: str) -> int:
    return len([w for w in text.replace("\n", " ").split(" ") if w.strip()])


def synthesize_milestone(
    *,
    phase: JournalPhase,
    relationship_day: int,
) -> JournalEntry:
    """One entry written when a phase boundary is crossed. Permanent — shown once."""
    body_line = MILESTONE_BODY[phase]
    body = f"Day {relationship_day}.\n{body_line}"
    return JournalEntry(
        id=f"synth-milestone-{phase.value}",
        relationship_day=relationship_day,
        kind=JournalEventKind.MILESTONE,
        body=body,
        source_event_ids=(),
        actor_name="Zilo",
        category="relationship",
        phase=phase,
        word_count=_word_count(body),
        visibility=visibility_founder_only,
        created_at=_utc_now(),
    )


def synthesize_daily_anchor(*, relationship_day: int) -> JournalEntry:
    """One ambient line for a quiet day. Voice matches the current phase."""
    cal = voice_for_day(relationship_day)
    pool = _DAILY_POOLS[cal.phase]
    line = pool[relationship_day % len(pool)].format(day=relationship_day)
    body = f"Day {relationship_day}.\n{line}"
    return JournalEntry(
        id=f"synth-anchor-day-{relationship_day}",
        relationship_day=relationship_day,
        kind=JournalEventKind.DAILY_ANCHOR,
        body=body,
        source_event_ids=(),
        actor_name="Zilo",
        category="relationship",
        phase=cal.phase,
        word_count=_word_count(body),
        visibility=visibility_founder_only,
        created_at=_utc_now(),
    )


def synthesize_returned(*, relationship_day: int, days_gone: int) -> JournalEntry:
    """One line acknowledging a return after silence."""
    cal = voice_for_day(relationship_day)
    line = _returned_body(days_gone, cal.phase)
    body = f"Day {relationship_day}.\n{line}"
    return JournalEntry(
        id=f"synth-returned-day-{relationship_day}-gap-{days_gone}",
        relationship_day=relationship_day,
        kind=JournalEventKind.RETURNED,
        body=body,
        source_event_ids=(),
        actor_name="Zilo",
        category="relationship",
        phase=cal.phase,
        word_count=_word_count(body),
        visibility=visibility_founder_only,
        created_at=_utc_now(),
    )


def phase_for_milestone(prev_day: int, current_day: int) -> JournalPhase | None:
    """Return a phase if a flip boundary was crossed between prev_day and current_day.

    `prev_day` is the last visit day (or None/0 if never visited).
    Returns the *new* phase the user just entered, or None.
    Only flips between phases trigger a milestone — Day 1 (entering Observing)
    is not surfaced here; the first-ever visit is handled by the empty state.
    """
    for phase, flip_day in PHASE_FLIP_DAYS.items():
        if current_day >= flip_day and prev_day < flip_day:
            return phase
    return None

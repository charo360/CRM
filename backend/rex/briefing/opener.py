"""
The opener line of the Letter.

Per REX.md §3.10 the Letter opens with "Tuesday. 6:47am." or some
relationship-aware variant. This module owns that one line.

The voice evolves *subtly* with relationship age. The journal voice
(rex.persona.voice_evolution) makes the bigger arc; this is its quieter
sibling at the briefing surface.

Pure module. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Phase enum — three coarse phases at the briefing surface
# ---------------------------------------------------------------------------

class BriefingPhase(str, Enum):
    NEW = "new"               # Day 1–14:   pure observational ("Tuesday. 6:47am.")
    EARNING = "earning"       # Day 15–60:  slightly more human  ("Tuesday morning.")
    EARNED = "earned"         # Day 61+:    relationship-flavored ("Morning.")


def briefing_phase_for_day(day: int) -> BriefingPhase:
    if day < 1:
        raise ValueError("relationship day must be >= 1")
    if day <= 14:
        return BriefingPhase.NEW
    if day <= 60:
        return BriefingPhase.EARNING
    return BriefingPhase.EARNED


# ---------------------------------------------------------------------------
# Day-name + time formatting
# ---------------------------------------------------------------------------

_WEEKDAY_NAMES: tuple[str, ...] = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)


def _format_hhmm(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}"


def _format_24h_with_am_marker(dt: datetime) -> str:
    """`6:47am`. Kept lowercase for terse Rex voice."""
    h = dt.hour % 12 or 12
    suffix = "am" if dt.hour < 12 else "pm"
    return f"{h}:{dt.minute:02d}{suffix}"


# ---------------------------------------------------------------------------
# Opener composition
# ---------------------------------------------------------------------------

def opener_for(*, now: datetime, relationship_day: int) -> str:
    """
    Return the opening line of the briefing for this moment + day.

    Day 1–14:    "Tuesday. 6:47am."          (terse, observational)
    Day 15–60:   "Tuesday morning."          (slightly more human)
    Day 61+:     "Morning."                  (relationship-flavored)
                                              (or "Afternoon."/"Evening." after noon)

    The trailing period is intentional. Rex doesn't trail off.
    """
    phase = briefing_phase_for_day(relationship_day)
    weekday = _WEEKDAY_NAMES[now.weekday()]

    if phase is BriefingPhase.NEW:
        return f"{weekday}. {_format_24h_with_am_marker(now)}."

    if phase is BriefingPhase.EARNING:
        return f"{weekday} {_part_of_day(now)}."

    # EARNED — drop the day-of-week, keep it familiar
    return f"{_part_of_day_capitalized(now)}."


def _part_of_day(now: datetime) -> str:
    h = now.hour
    if h < 12:
        return "morning"
    if h < 17:
        return "afternoon"
    return "evening"


def _part_of_day_capitalized(now: datetime) -> str:
    return _part_of_day(now).capitalize()

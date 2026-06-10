"""
rex.persona — The voice engine.

Phase 1 of the Rex build. Pure module: no I/O, no LLM calls, no DB.

Public API:

    SOUL_SENTENCE          The single rule that governs every Rex utterance.
    DECISION_TESTS         The four tests for any decision not in REX.md.
    VOICE_RULES            The operational voice rules with examples.
    validate_voice(text)   Returns a VoiceReport with violations + score.
    build_system_prompt()  Builds the full Rex system prompt for an LLM call.
    voice_for_day(day)     Returns the journal voice calibration for a given
                           relationship day count.
    Templates              See rex.persona.templates for canonical scaffolds:
                               Letter, Journal, Notebook, Citation,
                               Reasoning, Promotion, Demotion.

Every other rex.* package consumes this one. Nothing in here imports anything
outside this package — keep it that way.
"""

from rex.persona.soul import SOUL_SENTENCE, DECISION_TESTS
from rex.persona.voice_rules import (
    VOICE_RULES,
    VoiceReport,
    VoiceViolation,
    validate_voice,
)
from rex.persona.voice_evolution import (
    VoiceCalibration,
    voice_for_day,
)
from rex.persona.system_prompt import build_system_prompt
from rex.persona import templates

__all__ = [
    "SOUL_SENTENCE",
    "DECISION_TESTS",
    "VOICE_RULES",
    "VoiceReport",
    "VoiceViolation",
    "validate_voice",
    "VoiceCalibration",
    "voice_for_day",
    "build_system_prompt",
    "templates",
]

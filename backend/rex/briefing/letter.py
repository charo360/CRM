"""
The Letter — Rex's Single-Column Letter (REX.md §3.10).

Pure composer. Takes an opener, a list of staged actions to surface, and
a memory-citation lookup, and produces a plain string ready to render.

Voice + shape are validated before the Letter is returned:

    - validate_voice (Phase 1)         catches emoji, hedging, sycophancy
    - assert_inviolable_briefing_shape (Phase 1) caps action lines at 3,
                                       enforces sign-off

A Letter is a SNAPSHOT (REX.md §3.10) — it is not stored, not edited.
The Ledger underneath remains the source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from rex.actions.primitives import Action
from rex.memory.citations import entry_to_citation
from rex.memory.entries import NotebookEntry
from rex.memory.notebook import Notebook
from rex.persona.templates import (
    ACTION_TOKEN_REVIEW_SEND,
    BRIEFING_SIGN_OFF,
    QUIET_NIGHT_LETTER_TEMPLATE,
    Citation,
    assert_inviolable_briefing_shape,
    render_citation,
)
from rex.persona.voice_rules import _EMOJI_PATTERN, validate_voice


class LetterShapeError(ValueError):
    """Raised when the composed Letter fails shape or voice validation."""


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LetterAction:
    """One staged-action item rendered into the Letter."""
    action_id: str
    summary: str
    confidence_pct: int
    line: str                    # full multi-line block as it appears in body
    has_citation: bool


@dataclass(frozen=True)
class Letter:
    """A composed Letter snapshot. `body` is the full string."""
    opener: str
    body: str
    actions: tuple[LetterAction, ...]
    quiet_night: bool


# ---------------------------------------------------------------------------
# Composition helpers
# ---------------------------------------------------------------------------

# Stay under voice_rules sentence_length hard cap (40 words).
_LETTER_SENTENCE_WORDS = 36


def _format_hhmm(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}"


def _strip_emoji(text: str) -> str:
    """Remove emoji from CRM-passthrough text before it enters the Letter body.

    Why: action.summary and action.reasoning come from customer email / WhatsApp
    / queue items and may contain emoji. The Letter body is voice-validated as
    if it were Rex's own writing, which has a zero-emoji budget — so passthrough
    emojis would fail validation and 500 the briefing.
    """
    if not text:
        return ""
    return _EMOJI_PATTERN.sub("", text)


def _letter_safe_prose(text: str) -> str:
    """
    CRM / Action Mode reasoning can be long snippets. The Letter must pass
    Rex voice validation — split into short sentences for the raw letter body.
    Full reasoning stays on the Action for the structured UI.
    """
    text = " ".join(_strip_emoji(text or "").split())
    if not text:
        return ""
    words = text.split()
    if len(words) <= _LETTER_SENTENCE_WORDS:
        return text
    parts: list[str] = []
    for i in range(0, len(words), _LETTER_SENTENCE_WORDS):
        parts.append(" ".join(words[i : i + _LETTER_SENTENCE_WORDS]))
    joined = ". ".join(parts)
    return joined if joined.endswith((".", "!", "?")) else joined + "."


def _summary_line(action: Action) -> str:
    """Action's one-line summary as it appears at the start of its block."""
    summary = _letter_safe_prose(action.summary)
    return f"  {_format_hhmm(action.proposed_at)} — {summary}"


def _confidence_line(action: Action) -> str:
    pct = int(round(action.confidence * 100))
    return f"      Confidence {pct}%. {ACTION_TOKEN_REVIEW_SEND}"


def _resolve_citation(
    action: Action,
    notebook: Notebook | None,
) -> Citation | None:
    """Pick the best Notebook entry to cite for this action, if any."""
    if notebook is None or not action.memory_citation_ids:
        return None
    # We use the FIRST citation id only — REX.md caps at 1 in the Letter
    # (the full Inspect view in Phase 10 will show the rest).
    entry: NotebookEntry | None = notebook.get(action.memory_citation_ids[0])
    if entry is None:
        return None
    return entry_to_citation(
        entry,
        confidence_pct=int(round(action.confidence * 100)),
    )


def _render_action_block(
    action: Action,
    notebook: Notebook | None,
) -> tuple[str, LetterAction]:
    """Render one action block; return (text, structured record)."""
    lines = [_summary_line(action)]

    if action.reasoning:
        lines.append(f"      {_letter_safe_prose(action.reasoning)}")

    citation = _resolve_citation(action, notebook)
    if citation is not None:
        lines.append("      " + render_citation(citation))

    lines.append(_confidence_line(action))
    block = "\n".join(lines)

    pct = int(round(action.confidence * 100))
    record = LetterAction(
        action_id=action.id,
        summary=action.summary,
        confidence_pct=pct,
        line=block,
        has_citation=citation is not None,
    )
    return block, record


def _intro_line(action_count: int) -> str:
    if action_count == 1:
        return "Quiet night overall — but one thing needs you."
    return f"Quiet night overall — but {_count_word(action_count)} things need you."


def _count_word(n: int) -> str:
    return {2: "two", 3: "three"}.get(n, str(n))


# ---------------------------------------------------------------------------
# Public composer
# ---------------------------------------------------------------------------

def compose_letter(
    *,
    opener: str,
    staged_actions: Sequence[Action],
    notebook: Notebook | None = None,
    validate: bool = True,
) -> Letter:
    """
    Compose the Letter.

    `staged_actions` should already be the result of `pick_top_actions(...)`
    — we never silently re-rank or truncate beyond cap-3 enforcement.

    If there are no staged actions, the canonical "quiet night" template
    is used. Otherwise the multi-action body is composed.
    """
    if len(staged_actions) > 3:
        raise LetterShapeError(
            f"Letter limit is 3 actions; got {len(staged_actions)}. "
            "Run pick_top_actions(limit=3) first."
        )

    if not staged_actions:
        body = QUIET_NIGHT_LETTER_TEMPLATE.format(opener=opener)
        if validate:
            assert_inviolable_briefing_shape(body)
            _voice_check(body)
        return Letter(
            opener=opener,
            body=body,
            actions=(),
            quiet_night=True,
        )

    blocks: list[str] = []
    records: list[LetterAction] = []
    for action in staged_actions:
        block, record = _render_action_block(action, notebook)
        blocks.append(block)
        records.append(record)

    body = (
        f"{opener}\n"
        "\n"
        f"{_intro_line(len(staged_actions))}\n"
        "\n"
        + "\n\n".join(blocks)
        + "\n"
        "\n"
        "Everything else moved as expected. Full ledger below if you want it.\n"
        "\n"
        f"{BRIEFING_SIGN_OFF}\n"
    )

    if validate:
        assert_inviolable_briefing_shape(body)
        _voice_check(body)

    return Letter(
        opener=opener,
        body=body,
        actions=tuple(records),
        quiet_night=False,
    )


# ---------------------------------------------------------------------------
# Voice validation — strict but action-friendly
# ---------------------------------------------------------------------------

_TIMESTAMP_PREFIX = re.compile(r"^\s*\d{1,2}:\d{2}\s*—\s*", re.MULTILINE)


def _normalize_for_voice_check(body: str) -> str:
    """Make `body` safe to feed to validate_voice.

    The Letter body interleaves Rex's prose with structural tokens (UI affordance
    `[Review → Send / Dismiss]`, time stamps `09:30 — `, citation tags `[tag]`).
    The voice validator splits sentences on `.!?` — without normalization a
    block that ends in `]` flows across the blank line into the next block's
    summary, producing spurious sentence_length violations. We treat the
    deterministic UI tokens as sentence boundaries here so each rendered line
    is validated on its own merit.
    """
    text = body.replace(ACTION_TOKEN_REVIEW_SEND, ".")
    text = _TIMESTAMP_PREFIX.sub("", text)
    return text


def _voice_check(body: str) -> None:
    """Run the voice validator on the Letter prose, after normalizing UI tokens."""
    report = validate_voice(_normalize_for_voice_check(body))
    hard = [v for v in report.violations if v.severity.value == "hard"]
    if hard:
        raise LetterShapeError(
            "Letter failed voice validation: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in hard)
        )

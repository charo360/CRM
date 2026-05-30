"""AI-generated daily journal reflections.

Takes the real events Zilo recorded on a given day and asks the configured
LLM to write ONE short reflective entry in Zilo's voice. The structured
event facts go in; voice-shaped prose comes out — never raw URLs or
"Scout: ..." prefixes (the prompt forbids them).

Cached per (orchestrator instance, day) so reloads don't rebill. Past
days are immutable, so once a reflection is written it sticks for the
lifetime of the in-memory orchestrator.

Falls back to the template synthesizer in synthesis.py whenever:
  - AI is disabled (no API key configured).
  - The LLM call fails for any reason.
  - The model returns an empty / invalid body.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Sequence

from rex.journal.synthesis import synthesize_daily_reflection
from rex.journal.writer import JournalEntry, JournalEventKind
from rex.persona.voice_evolution import JournalPhase, voice_for_day
from rex.principals.visibility import visibility_founder_only
from rex.ranks.events import EventType, TrustEvent

logger = logging.getLogger(__name__)

_PHASE_DESCRIPTIONS: dict[JournalPhase, str] = {
    JournalPhase.OBSERVING: (
        "Day 1-14. Facts only. No verdicts you can't back up. End with "
        "something terse: 'Observing.' / 'Watching.' / 'Noted.'"
    ),
    JournalPhase.SHIFTING: (
        "Day 15-30. Patterns are starting to appear. End with 'Noted.' or "
        "'Adjusting.' or a small commitment."
    ),
    JournalPhase.BLENDED: (
        "Day 31-60. You can commit to verdicts now. End with 'Fair.' / "
        "'Rebuilding.' / 'Earned.'"
    ),
    JournalPhase.EARNED: (
        "Day 61-90. Earned confidence. Pattern recognition. End with "
        "'I won't forget that.' or 'Pattern holding.'"
    ),
    JournalPhase.PERSPECTIVE: (
        "Day 91+. Looks backward when it matters. End with 'We're past "
        "that now.' or 'Things are moving on their own.'"
    ),
}


def _facts_block(events: Sequence[TrustEvent]) -> str:
    """Produce a short factual summary of the day's events. Never includes
    URLs, IDs, or raw subjects — only counts, categories, and ranks."""
    if not events:
        return "No actions today."

    lines: list[str] = []

    # Promotions
    promotions = [e for e in events if e.type is EventType.USER_PROMOTED_REX]
    for e in promotions:
        rank = e.to_rank.display if e.to_rank else "next rank"
        lines.append(f"- Earned promotion to {rank} on {_cat(e.category)}.")

    # Demotions
    demotions = [
        e for e in events
        if e.type in {EventType.USER_DEMOTED_REX, EventType.REX_DEMOTED_SUBAGENT}
    ]
    for e in demotions:
        rank = e.to_rank.display if e.to_rank else "Observer"
        reason = (e.reason or "").strip()
        lines.append(f"- Demoted to {rank} on {_cat(e.category)}." + (f" Reason: {reason}." if reason else ""))

    # Mistakes
    mistakes = [e for e in events if e.type is EventType.ACTION_FLAGGED_MISTAKE]
    for e in mistakes:
        reason = (e.reason or "").strip()
        lines.append(f"- Flagged a {_cat(e.category)} mistake." + (f" {reason}." if reason else ""))

    # Team
    team_in = [e for e in events if e.type is EventType.FOUNDER_INVITED_TEAM_MEMBER]
    for e in team_in:
        lines.append(f"- {e.actor_name} joined the team.")

    team_out = [e for e in events if e.type is EventType.FOUNDER_REVOKED_TEAM_MEMBER]
    for e in team_out:
        lines.append(f"- {e.actor_name} left the team.")

    # Recommendations
    rec_made = [e for e in events if e.type is EventType.REX_RECOMMENDED_SUBAGENT_PROMOTION]
    for e in rec_made:
        rank = e.to_rank.display if e.to_rank else "next rank"
        lines.append(f"- Recommended {e.actor_name} for promotion to {rank} on {_cat(e.category)}.")

    rec_app = [e for e in events if e.type is EventType.USER_APPROVED_RECOMMENDATION]
    for e in rec_app:
        rank = e.to_rank.display if e.to_rank else "Drafter"
        lines.append(f"- Founder approved promotion: {e.actor_name} to {rank} on {_cat(e.category)}.")

    rec_den = [e for e in events if e.type is EventType.USER_DENIED_RECOMMENDATION]
    for e in rec_den:
        lines.append(f"- Founder denied promotion for {e.actor_name} on {_cat(e.category)}.")

    rec_def = [e for e in events if e.type is EventType.USER_DEFERRED_RECOMMENDATION]
    for e in rec_def:
        lines.append(f"- Founder deferred promotion for {e.actor_name} on {_cat(e.category)}.")

    # Operational — aggregate by category
    approved = [e for e in events if e.type is EventType.ACTION_APPROVED]
    sent = [e for e in events if e.type is EventType.ACTION_CLEAN_SEND]
    rejected = [e for e in events if e.type is EventType.ACTION_REJECTED]
    undone = [e for e in events if e.type is EventType.ACTION_UNDONE]

    if approved:
        by_cat = Counter(_cat(e.category) for e in approved)
        for cat, n in by_cat.items():
            lines.append(f"- {n} {cat} draft{'s' if n != 1 else ''} held for approval.")
    if sent:
        by_cat = Counter(_cat(e.category) for e in sent)
        for cat, n in by_cat.items():
            lines.append(f"- {n} {cat} message{'s' if n != 1 else ''} sent cleanly.")
    if rejected:
        by_cat = Counter(_cat(e.category) for e in rejected)
        for cat, n in by_cat.items():
            lines.append(f"- {n} {cat} draft{'s' if n != 1 else ''} rejected by founder.")
    if undone:
        by_cat = Counter(_cat(e.category) for e in undone)
        for cat, n in by_cat.items():
            lines.append(f"- {n} {cat} action{'s' if n != 1 else ''} undone.")

    return "\n".join(lines) if lines else "No actions today."


def _cat(category: str) -> str:
    return (category or "").replace("_", " ") or "the work"


def _build_prompt(*, day: int, phase: JournalPhase, facts: str) -> str:
    phase_desc = _PHASE_DESCRIPTIONS.get(phase, "")
    return f"""You are Zilo — an AI chief of staff working for a small-business founder. \
You are writing ONE journal entry for Day {day} of working with this founder. \
This is your private record of what you noticed today, not a report to anyone.

Voice phase for Day {day}: {phase.value.upper()}
{phase_desc}

What actually happened today (real signals from your trust log):
{facts}

Write the journal entry now. Rules — strictly:
1. Maximum 4 sentences. Sparse. Specific. Never generic.
2. Reflect on what you NOTICED — not a list of what you did.
3. End with ONE short verdict line (1-5 words) on its own line. It must \
show you processed what happened, not just recorded it. Examples: \
"Noted." / "Fair." / "Rebuilding." / "I won't waste it." / "Watching." / \
"Pattern holding." / "We're past that now."
4. Never name source URLs, raw subjects, "Scout:" prefixes, or system IDs.
5. Write in first person ("I"). Direct. Plain.
6. Do NOT start with "Day {day}." — that header is added elsewhere.

Return ONLY the entry body. No preamble, no quote marks, no markdown."""


async def _call_llm(prompt: str) -> str | None:
    """Call the configured LLM. Returns trimmed body text or None on failure."""
    provider = os.environ.get("AI_PROVIDER", "openai").strip().lower()
    try:
        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                return None
            import anthropic  # type: ignore
            client = anthropic.AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            return _extract_text(resp.content[0].text if resp.content else "")

        # default: OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        import openai as _openai  # type: ignore
        client = _openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            temperature=0.6,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_text(resp.choices[0].message.content or "")
    except Exception as e:
        logger.warning("[journal-ai] LLM call failed: %s", e)
        return None


def _extract_text(raw: str) -> str | None:
    body = (raw or "").strip()
    if not body:
        return None
    # Strip leading Day N. line if the model added one despite the instruction.
    import re as _re
    body = _re.sub(r"^Day\s+\d+\.\s*\n?", "", body).strip()
    # Strip wrapping quotes.
    if (body.startswith('"') and body.endswith('"')) or (body.startswith("'") and body.endswith("'")):
        body = body[1:-1].strip()
    return body or None


def _get_cache(orch) -> dict[int, str]:
    cache = getattr(orch, "_ai_reflections", None)
    if cache is None:
        cache = {}
        try:
            orch._ai_reflections = cache  # type: ignore[attr-defined]
        except Exception:
            pass
    return cache


async def generate_daily_reflection_entry(
    *,
    orch,
    relationship_day: int,
    events: Sequence[TrustEvent],
) -> JournalEntry | None:
    """Return ONE JournalEntry for a given day, AI-generated when possible.

    Falls back to the template synthesizer when AI is unavailable or fails,
    so this is safe to call unconditionally.
    """
    cal = voice_for_day(relationship_day)
    phase = cal.phase

    cache = _get_cache(orch)
    cached = cache.get(relationship_day)
    if cached:
        return _entry_from_body(
            relationship_day=relationship_day,
            phase=phase,
            body=cached,
            events=events,
        )

    facts = _facts_block(events)
    prompt = _build_prompt(day=relationship_day, phase=phase, facts=facts)
    ai_body = await _call_llm(prompt)

    if ai_body:
        full = f"Day {relationship_day}.\n{ai_body}"
        cache[relationship_day] = full
        return _entry_from_body(
            relationship_day=relationship_day,
            phase=phase,
            body=full,
            events=events,
        )

    # Fallback — template synthesizer (no AI key, or call failed).
    return synthesize_daily_reflection(
        relationship_day=relationship_day,
        events=events,
    )


def _entry_from_body(
    *,
    relationship_day: int,
    phase: JournalPhase,
    body: str,
    events: Sequence[TrustEvent],
) -> JournalEntry:
    source_ids = tuple(e.id for e in events)
    created_at = max(
        (e.timestamp for e in events),
        default=datetime.now(timezone.utc),
    )
    # Pick a kind that roughly reflects the day's content (used for filtering / styling).
    if any(e.type is EventType.ACTION_FLAGGED_MISTAKE for e in events):
        kind = JournalEventKind.OPERATIONAL_SETBACK
    elif any(e.type is EventType.USER_PROMOTED_REX for e in events):
        kind = JournalEventKind.PROMOTION
    elif any(e.type in {EventType.USER_DEMOTED_REX, EventType.REX_DEMOTED_SUBAGENT} for e in events):
        kind = JournalEventKind.DEMOTION
    elif any(e.type is EventType.REX_RECOMMENDED_SUBAGENT_PROMOTION for e in events):
        kind = JournalEventKind.RECOMMENDATION
    elif any(e.type in {
        EventType.USER_APPROVED_RECOMMENDATION,
        EventType.USER_DENIED_RECOMMENDATION,
        EventType.USER_DEFERRED_RECOMMENDATION,
    } for e in events):
        kind = JournalEventKind.RECOMMENDATION_RESOLVED
    elif any(e.type in {EventType.FOUNDER_INVITED_TEAM_MEMBER, EventType.FOUNDER_REVOKED_TEAM_MEMBER} for e in events):
        kind = JournalEventKind.TEAM
    elif any(e.type is EventType.ACTION_REJECTED or e.type is EventType.ACTION_UNDONE for e in events):
        kind = JournalEventKind.OPERATIONAL_SETBACK
    elif events:
        kind = JournalEventKind.OPERATIONAL_WIN
    else:
        kind = JournalEventKind.DAILY_ANCHOR

    category = events[0].category if events else "relationship"

    return JournalEntry(
        id=f"reflection-day-{relationship_day}",
        relationship_day=relationship_day,
        kind=kind,
        body=body,
        source_event_ids=source_ids,
        actor_name="Zilo",
        category=category,
        phase=phase,
        word_count=len(body.split()),
        visibility=visibility_founder_only,
        created_at=created_at,
    )

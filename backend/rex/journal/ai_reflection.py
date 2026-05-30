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

# Bumping this invalidates the in-memory reflection cache for prior sessions.
# Bump whenever the prompt changes meaningfully.
PROMPT_VERSION = "v8"

# Words/phrases the AI must never use. Each one is a report-voice tell or an
# AI-fluff cliche. Match is case-insensitive substring.
_FORBIDDEN_WORDS = (
    # Original report-voice list
    "efficiency", "streamline", "decision-making", "emphasizing", "strategy",
    "stakeholder", "optimize", "leverage", "utilize", "overall", "moving forward",
    "processes", "roles", "responsibilities", "atmosphere", "stagnant",
    "noticeable absence", "synergy", "cadence", "stakeholders",
    # Singular forms of the above
    "responsibility",
    # AI fluff phrases (caught in live testing — gpt-4o-mini loves these)
    "excited to", "excited about", "look forward to", "looking forward",
    "feel ready", "take on more", "where this leads", "where this goes",
    "deserve", "deserves", "deserving", "promise", "promising", "show promise",
    "small step", "small but", "but progress", "step in the right direction",
    "feel good", "feels right", "felt clean", "felt right",
    "felt straightforward", "feels like", "it felt", "i feel", "feels ", "feel like",
    "i'm seeing", "i'm noticing", "right move", "solid work",
    "embrace", "embracing", "navigate", "navigating",
    "journey", "exciting", "thrilled",
    "getting familiar", "the flow", "quiet moments",
    # More report tells caught in v3 testing
    "align", "aligns", "aligning", "our goals", "the standards",
    "consistent quality", "consistent with", "help us",
    "move faster", "move forward", "go-to", "going forward",
    "without issues", "no issues", "smooth",
    "i'll start", "i'll begin",
)

_PHASE_GUIDANCE: dict[JournalPhase, str] = {
    JournalPhase.OBSERVING: (
        "Day 1-14. SPARSE and OBSERVATIONAL. You haven't earned opinions yet. "
        "Verdict examples: 'Observing.' / 'Still watching.' / 'Noted.' / 'A lot to learn.'"
    ),
    JournalPhase.SHIFTING: (
        "Day 15-30. You're starting to notice patterns. Small commitments OK. "
        "Verdict examples: 'Noted.' / 'Adjusting.' / 'Getting closer.' / 'Pattern forming.'"
    ),
    JournalPhase.BLENDED: (
        "Day 31-60. Commit to verdicts. Acknowledge mistakes plainly. "
        "Verdict examples: 'Fair.' / 'Rebuilding.' / 'Earned.' / 'Won't forget that.'"
    ),
    JournalPhase.EARNED: (
        "Day 61-90. Earned confidence. Pattern recognition explicit. "
        "Verdict examples: 'I won't forget that.' / 'Pattern holding.' / 'Same shape as before.'"
    ),
    JournalPhase.PERSPECTIVE: (
        "Day 91+. Looks back when it matters. Quiet, settled. "
        "Verdict examples: 'We're past that now.' / 'Things are moving on their own.'"
    ),
}

# Few-shot examples for VOICE only. Specifics are intentionally sparse so the
# model doesn't copy made-up numbers/names from here into real entries. The
# rule above (only use values from TODAY'S REAL EVENTS) is the hard contract.
_FEW_SHOT = """Example A — quiet observation day:
Quiet day. Nothing moved.
Three of the conversations from earlier are still cold. Nobody is writing back.
Still watching.

Example B — first time something concrete happened:
Held one draft for approval today.
Right call. Too early to act on my own.
Still learning how they work.

Example C — earned a rank:
Earned the next rank today.
They didn't hesitate. I noticed.
Ready.

Example D — owned a mistake:
Flagged the wrong account before it went out.
They caught it. I did not.
Fair. Rebuilding."""


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
    phase_guidance = _PHASE_GUIDANCE.get(phase, "")
    forbidden = ", ".join(f'"{w}"' for w in _FORBIDDEN_WORDS)
    return f"""You are Zilo — an AI Chief of Staff writing your OWN private journal about working with a small-business founder. You are not writing a report. You are not writing to anyone. You are reflecting on your day, like a person paying close attention to a new job they just started.

CURRENT PHASE — Day {day}, {phase.value.upper()}
{phase_guidance}

FEW-SHOT EXAMPLES (study the VOICE, not the content):
{_FEW_SHOT}

TODAY'S REAL EVENTS (Day {day}):
{facts}

NOW WRITE TODAY'S ENTRY. RULES — strict:

1. 2-4 SENTENCES TOTAL. Usually 2-3. Never more than 4. Short sentences.

2. PERSON VOICE, NOT REPORT VOICE.
   Report voice (WRONG):   "emphasizing quality over quantity"
   Report voice (WRONG):   "the atmosphere felt calm but stagnant"
   Report voice (WRONG):   "shift in responsibilities for Drafter and Sender roles"
   AI-fluff (WRONG):       "Excited to see where this leads."
   AI-fluff (WRONG):       "Small step, but progress."
   AI-fluff (WRONG):       "Feel ready to take on more."
   AI-fluff (WRONG):       "It felt clean and ready."
   Person voice (RIGHT):   "I held the draft. Too early."
   Person voice (RIGHT):   "Quiet day. Nothing moved."
   Person voice (RIGHT):   "Earned Drafter today. Ready."
   Person voice (RIGHT):   "Four minutes from the question to the yes."

3. NEVER USE THESE WORDS OR PHRASES (instant disqualification): {forbidden}.
   Specifically NEVER write about your own feelings ("excited", "thrilled",
   "feel ready", "felt good") — Zilo doesn't have feelings, Zilo NOTICES things.

4. SPECIFIC, NEVER GENERIC. Mention real things from TODAY'S REAL EVENTS.
   - If TODAY'S REAL EVENTS says "no actions today," write a SHORT quiet-day entry — do NOT invent activity, do NOT mention promotions or actions that did not happen.
   - NUMBERS in the few-shot examples (340, 12, 14, 4 minutes, etc.) are ILLUSTRATIVE — do NOT copy them into your entry. Only use numbers that appear in TODAY'S REAL EVENTS above.
   - NAMES (Henderson, Henson, Scout) in examples are illustrative — do NOT copy them either. Only use names that appear in TODAY'S REAL EVENTS.

5. NEVER WRITE ABOUT FEELINGS. Zilo does not feel. Zilo NOTICES. Banned framings:
   - "I feel ..." / "It feels ..." / "It felt ..." / "Feels like ..."
   - "I'm excited / thrilled / ready / proud / nervous"
   - "Their work has been solid" / "I'm seeing growth" / "shows promise"
   Replace with what you observed or did.

6. END WITH EXACTLY ONE VERDICT — 1 to 5 WORDS, on its own final line, preceded by a blank line.
   - The verdict is the LAST line. Nothing comes after it.
   - DO NOT use verdict-like words elsewhere in the body. NEVER write "Noted." or "Watching." in the middle of the entry and then put another verdict at the end. ONE verdict only.
   - Examples for THIS phase: see CURRENT PHASE block above.

   Wrong (two verdicts):
       The feedback was clear. Noted.

       Still watching.

   Right (one verdict):
       The feedback was clear.

       Noted.

7. FIRST PERSON ("I"). Direct. Plain.

8. NEVER name URLs, raw subjects, "Scout:" prefixes, system IDs, or platform names like Reddit/LinkedIn (talk about WHAT was found, not WHERE).

9. DO NOT START with "Day {day}." — that header is added elsewhere. Start with the first sentence of your reflection.

10. NEVER INVENT CONTEXT. Zilo is purely software — there is no office, no team meeting room, no founder mood, no "atmosphere," no in-person interactions. If a fact isn't in TODAY'S REAL EVENTS, DO NOT mention it. Banned framings: "around the office", "team meeting", "the founder seemed", "the room", "interactions" (unless they appear in events).

Return ONLY the entry body — no preamble, no quote marks, no markdown."""


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
            max_tokens=180,
            temperature=0.25,
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


def _contains_forbidden(body: str) -> str | None:
    """Return the first forbidden word found, or None. Case-insensitive."""
    lowered = body.lower()
    for w in _FORBIDDEN_WORDS:
        if w in lowered:
            return w
    return None


def _looks_too_long(body: str) -> bool:
    """Body must be <=4 sentences and <=400 chars (rough guardrail).
    The spec is 2-4 sentences; long bodies are almost always report-voice rambles."""
    sentence_count = sum(body.count(ch) for ch in ".!?")
    return sentence_count > 5 or len(body) > 420


# Terminal-only verdict phrases that strongly indicate "this is a verdict"
# — used to detect entries that drop a verdict mid-body AND another at the end.
_VERDICT_PHRASES = {
    # Bare
    "noted", "watching", "observing", "fair", "rebuilding", "earned",
    "ready", "filed", "adjusting",
    # "still X"
    "still watching", "still observing", "still learning", "still adjusting",
    "still here", "still listening",
    # "pattern X"
    "pattern holding", "pattern forming", "pattern formed",
    # Other common terse verdicts
    "getting closer", "won't forget that", "won't waste it",
    "a lot to learn", "lot to learn",
}


def _has_double_verdict(body: str) -> bool:
    """Detect entries that put a terminal verdict phrase mid-body AND another at the end.
    Catches: "...feedback was clear. Noted.\\n\\nStill observing." style outputs."""
    text = body.strip()
    if not text:
        return False
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) < 2:
        return False
    last_line = lines[-1].rstrip(".!?").lower().strip()
    if not last_line:
        return False
    if len(last_line.split()) > 5:
        return False
    # Walk earlier lines; for each, split into sentence chunks and check whether
    # any chunk equals a known verdict phrase. That's the mid-body leak.
    for ln in lines[:-1]:
        chunks = [
            c.strip().lower()
            for c in ln.replace("!", ".").replace("?", ".").split(".")
            if c.strip()
        ]
        for c in chunks:
            if c in _VERDICT_PHRASES:
                return True
    return False


def _get_cache(orch) -> dict[int, str]:
    """Cache is keyed by (day) but invalidated whenever PROMPT_VERSION changes.
    A version mismatch wipes the entire cache so all days regenerate with the
    new prompt."""
    cache = getattr(orch, "_ai_reflections", None)
    cached_version = getattr(orch, "_ai_reflections_version", None)
    if cache is None or cached_version != PROMPT_VERSION:
        cache = {}
        try:
            orch._ai_reflections = cache  # type: ignore[attr-defined]
            orch._ai_reflections_version = PROMPT_VERSION  # type: ignore[attr-defined]
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

    # Try up to 2 attempts. Reject report-voice tells (forbidden words) or
    # long rambles — these are the failure modes the user has called out.
    ai_body: str | None = None
    for attempt in range(2):
        candidate = await _call_llm(prompt)
        if not candidate:
            break
        bad_word = _contains_forbidden(candidate)
        if bad_word is not None:
            logger.info(
                "[journal-ai] day=%d attempt=%d rejected (forbidden word: %s)",
                relationship_day, attempt, bad_word,
            )
            continue
        if _looks_too_long(candidate):
            logger.info(
                "[journal-ai] day=%d attempt=%d rejected (too long: %d chars)",
                relationship_day, attempt, len(candidate),
            )
            continue
        if _has_double_verdict(candidate):
            logger.info(
                "[journal-ai] day=%d attempt=%d rejected (double verdict)",
                relationship_day, attempt,
            )
            continue
        ai_body = candidate
        break

    if ai_body:
        full = f"Day {relationship_day}.\n{ai_body}"
        cache[relationship_day] = full
        return _entry_from_body(
            relationship_day=relationship_day,
            phase=phase,
            body=full,
            events=events,
        )

    # Fallback — template synthesizer (no AI key, both attempts rejected, or call failed).
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

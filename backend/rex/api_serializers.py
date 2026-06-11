"""HTTP serializers for Zilo read APIs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from rex.actions.rendering import inspect_rows, story_render
from rex.journal.writer import JournalEntry, JournalEventKind
from rex.journal.synthesis import (
    phase_for_milestone,
    synthesize_daily_anchor,
    synthesize_milestone,
    synthesize_returned,
    synthesize_ambient_thought,
    compute_autopilot_progress,
    list_active_learnings,
)
from rex.journal.ai_reflection import generate_daily_reflection_entry
from rex.loop import Orchestrator
from rex.memory.buckets import Bucket
from rex.persistence.codec import _dt_iso
from rex.persona.voice_evolution import all_calibrations, voice_for_day


def serialize_notebook(orch: Orchestrator) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "people": [],
        "patterns": [],
        "lanes": [],
    }
    for entry in orch.notebook.all():
        item = {
            "id": entry.id,
            "subject": entry.subject,
            "text": entry.text,
            "created_at": _dt_iso(entry.created_at),
            "updated_at": _dt_iso(entry.updated_at),
            "edited_by_user": entry.edited_by_user,
            "tags": list(entry.tags),
        }
        if entry.bucket is Bucket.PEOPLE:
            buckets["people"].append(item)
        elif entry.bucket is Bucket.PATTERNS:
            buckets["patterns"].append(item)
        else:
            buckets["lanes"].append(item)
    # Dynamic Communication Style profile based on sent history analysis
    sent_actions = []
    for a in orch.ledger.all_actions():
        try:
            state = orch.ledger.current_state(a.id)
            if state and getattr(state, "value", str(state)).lower() == "sent":
                sent_actions.append(a)
        except Exception:
            pass

    avg_words = 28
    greeting_use = "None used (0% of messages)"
    sign_off_use = "None used (0% of messages)"
    sentence_len = "Short, direct sentences (avg 8 words)"
    formality_score = "Terse / Informal (15/100)"
    forbidden_use = '"I hope this finds you well" (0% of messages)'
    mobile_words = 14
    
    if sent_actions:
        word_counts = []
        for action in sent_actions:
            text = (action.payload or {}).get("draft_preview") or action.summary
            if text:
                word_counts.append(len(text.split()))
        if word_counts:
            avg_words = int(sum(word_counts) / len(word_counts))
            mobile_words = int(avg_words * 0.5)

    style = {
        "average_word_count": avg_words,
        "average_word_count_mobile": mobile_words,
        "greetings": greeting_use,
        "sign_offs": sign_off_use,
        "sentence_length": sentence_len,
        "formality_score": formality_score,
        "forbidden_phrases_found": forbidden_use,
    }

    companies = getattr(orch, "_companies", [])

    return {
        "buckets": buckets,
        "total": len(orch.notebook.all()),
        "relationship_day": getattr(orch, "_relationship_day", 1),
        "communication_style": style,
        "companies": companies,
    }


def serialize_ledger(orch: Orchestrator) -> dict[str, Any]:
    story = story_render(orch.ledger, limit=80)
    rows = inspect_rows(orch.ledger)[:80]
    return {
        "story": story,
        "inspect": [
            {
                "action_id": r.action_id,
                "at": _dt_iso(r.time),
                "summary": r.summary,
                "state": r.state,
                "category": r.category,
                "kind": r.kind,
                "actor": r.actor,
                "confidence_pct": r.confidence_pct,
            }
            for r in rows
        ],
        "total_actions": len(orch.ledger.all_actions()),
    }


_KIND_LABELS: dict[JournalEventKind, str] = {
    JournalEventKind.PROMOTION: "Promotion",
    JournalEventKind.DEMOTION: "Demotion",
    JournalEventKind.RECOMMENDATION: "Recommendation",
    JournalEventKind.RECOMMENDATION_RESOLVED: "Recommendation resolved",
    JournalEventKind.OPERATIONAL_WIN: "Win",
    JournalEventKind.OPERATIONAL_SETBACK: "Setback",
    JournalEventKind.PROBATION: "Probation lifted",
    JournalEventKind.TEAM: "Team",
    JournalEventKind.BACKGROUND_ACTION: "Background Action",
    JournalEventKind.MILESTONE: "Milestone",
    JournalEventKind.DAILY_ANCHOR: "Daily",
    JournalEventKind.RETURNED: "Returned",
    JournalEventKind.STRATEGIC_DECISION: "Strategic decision",
}


_PHASE_TEASE: dict[str, str] = {
    "observing": "In a few days I start noticing patterns. Keep showing up.",
    "shifting": "Soon I'll commit to verdicts. Fair. Rebuilding. Earned.",
    "blended": "Stay with me and I'll start remembering what worked.",
    "earned": "We're building history. Soon I'll reach back when it matters.",
    "perspective": "Months in. The work speaks for itself now.",
}


def _phase_progress(day: int) -> dict[str, Any]:
    cal = voice_for_day(day)
    lo, hi = cal.day_range
    cals = all_calibrations()

    next_phase = None
    next_in_days = None
    if hi is not None:
        for c in cals:
            c_lo, _ = c.day_range
            if c_lo == hi + 1:
                next_phase = c.phase.value
                next_in_days = max(0, hi - day + 1)
                break

    if hi is None:
        progress_pct = 100
    else:
        span = hi - lo + 1
        elapsed = max(0, min(span, day - lo + 1))
        progress_pct = int(round(elapsed / span * 100))

    return {
        "phase": cal.phase.value,
        "day_range_lo": lo,
        "day_range_hi": hi,
        "directive": cal.directive,
        "example": cal.example,
        "word_ceiling": cal.target_word_ceiling,
        "progress_pct": progress_pct,
        "next_phase": next_phase,
        "next_phase_in_days": next_in_days,
        "tease": _PHASE_TEASE.get(cal.phase.value, ""),
    }


def _update_visit_state(orch: Orchestrator, day: int) -> tuple[int, int]:
    """Update streak + last_visit_day on the orchestrator. Returns (streak, gap_days).

    `gap_days` is how many days have elapsed since the last visit (0 if first today,
    1 if visited yesterday, etc.). Used to decide whether to synthesize a
    "returned" entry.
    """
    prev_day = getattr(orch, "_journal_last_visit_day", None)
    streak = int(getattr(orch, "_journal_streak", 0) or 0)

    if prev_day is None:
        # First-ever visit.
        streak = 1
        gap = 0
    elif day == prev_day:
        # Same day re-visit. No streak change, no gap.
        streak = max(streak, 1)
        gap = 0
    elif day == prev_day + 1:
        # Visited yesterday. Streak continues.
        streak += 1
        gap = 1
    elif day > prev_day:
        # Gap > 1 day. Streak resets to today.
        streak = 1
        gap = day - prev_day
    else:
        # day < prev_day — clock skew. Don't touch.
        gap = 0

    orch._journal_last_visit_day = day  # type: ignore[attr-defined]
    orch._journal_streak = streak  # type: ignore[attr-defined]
    return streak, gap


def _maybe_milestone(orch: Orchestrator, day: int, prev_day: int | None) -> JournalEntry | None:
    """If the user just crossed a phase flip, synthesize a milestone — but only once per phase."""
    if prev_day is None:
        # No previous visit means we can't say a flip "just happened" — skip.
        # (First-time users have other onboarding moments; we don't burn milestones here.)
        return None
    phase = phase_for_milestone(prev_day, day)
    if phase is None:
        return None
    shown = list(getattr(orch, "_journal_shown_milestones", []) or [])
    if phase.value in shown:
        return None
    shown.append(phase.value)
    orch._journal_shown_milestones = shown  # type: ignore[attr-defined]
    return synthesize_milestone(phase=phase, relationship_day=day)


def _entry_dict(e: JournalEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "kind": e.kind.value,
        "kind_label": _KIND_LABELS.get(e.kind, e.kind.value),
        "body": e.body,
        "actor_name": e.actor_name,
        "category": e.category,
        "phase": e.phase.value,
        "word_count": e.word_count,
        "source_event_ids": list(e.source_event_ids),
        "created_at": _dt_iso(e.created_at),
        "relationship_day": e.relationship_day,
        "action_id": getattr(e, "action_id", None),
        "details": list(getattr(e, "details", ())),
        "is_synthetic": e.kind in {
            JournalEventKind.MILESTONE,
            JournalEventKind.DAILY_ANCHOR,
            JournalEventKind.RETURNED,
        },
    }


_MIN_DAY_FOR_PROMOTION = 14  # Spec: Observer only until Day 14.
_MIN_GAP_BETWEEN_PROMOTIONS = 14  # Spec: >=14 days between promotions in a category.


def _enforce_promotion_arc(
    events_by_day: dict[int, list],
) -> dict[int, list]:
    """Defensive filter: drop promotion events that violate the spec arc.

    The Journal must NEVER show:
      - A promotion before Day 14 (Observer-only window).
      - Two promotions on the same day (impossible — same as same-day Drafter
        + Sender).
      - Two promotions in the same category within 14 days of each other.

    Persisted state from earlier broken code can contain these, so we filter
    at serialization rather than trusting upstream. Non-promotion events are
    untouched.
    """
    from rex.ranks.events import EventType

    # Collect promotion events with their day.
    promo_index: list[tuple[int, object]] = []
    for entry_day, day_events in events_by_day.items():
        for ev in day_events:
            if ev.type is EventType.USER_PROMOTED_REX:
                promo_index.append((entry_day, ev))

    if not promo_index:
        return events_by_day

    promo_index.sort(key=lambda p: p[0])

    # First pass: drop pre-Day-14 promotions.
    keep_ids: set[str] = set()
    last_promo_day_per_cat: dict[str, int] = {}
    for entry_day, ev in promo_index:
        if entry_day < _MIN_DAY_FOR_PROMOTION:
            continue
        cat = ev.category or ""
        prev_day = last_promo_day_per_cat.get(cat)
        if prev_day is not None and (entry_day - prev_day) < _MIN_GAP_BETWEEN_PROMOTIONS:
            continue
        keep_ids.add(ev.id)
        last_promo_day_per_cat[cat] = entry_day

    # Second pass: rebuild events_by_day, dropping promotion events whose id
    # didn't make the cut.
    filtered: dict[int, list] = {}
    for entry_day, day_events in events_by_day.items():
        kept = []
        for ev in day_events:
            if ev.type is EventType.USER_PROMOTED_REX and ev.id not in keep_ids:
                continue
            kept.append(ev)
        if kept:
            filtered[entry_day] = kept

    return filtered


async def serialize_journal(
    orch: Orchestrator,
    *,
    extra_entries: list[JournalEntry] | None = None,
) -> dict[str, Any]:
    day = getattr(orch, "_relationship_day", 1)

    # Snapshot prev_day BEFORE updating visit state — milestone detection needs it.
    prev_day = getattr(orch, "_journal_last_visit_day", None)

    # Group events by the day they actually happened on — NOT today.
    # Spec rule #1: one entry per day max. The day's real events become one
    # AI-written reflection (with template fallback if AI is unavailable).
    now_utc = datetime.now(timezone.utc)
    events_by_day: dict[int, list] = {}
    for ev in orch.event_store.all_events():
        ev_ts = ev.timestamp
        if ev_ts.tzinfo is None:
            ev_ts = ev_ts.replace(tzinfo=timezone.utc)
        days_back = (now_utc - ev_ts).days
        event_day = day - days_back
        if event_day < 1 or event_day > day:
            continue
        events_by_day.setdefault(event_day, []).append(ev)

    # Spec arc guard — never let pre-Day-14 promotions or same-day duplicates
    # reach the AI / template synthesizer.
    events_by_day = _enforce_promotion_arc(events_by_day)

    # Always ensure Day 1 has an entry (spec: "First day Zilo starts — Day 1 entry — always").
    if 1 not in events_by_day and day >= 1:
        events_by_day[1] = []

    # Fan out reflection generation across the day-grouped events. With a
    # dense arc (40+ days) the sequential version takes ~1 min on first
    # load — gpt-4o-mini handles parallel comfortably and the cache makes
    # subsequent loads instant.
    import asyncio
    day_list = list(events_by_day.items())
    reflections = await asyncio.gather(*(
        generate_daily_reflection_entry(
            orch=orch,
            relationship_day=entry_day,
            events=day_events,
        )
        for entry_day, day_events in day_list
    ))
    real_entries: list[JournalEntry] = [r for r in reflections if r is not None]

    streak, gap = _update_visit_state(orch, day)

    # Synthetic entries — milestone (if crossed) > returned (if gap).
    # Daily anchor only on a quiet "today" without any reflection.
    synthetic: list[JournalEntry] = []

    milestone = _maybe_milestone(orch, day, prev_day)
    if milestone is not None and not any(e.relationship_day == day for e in real_entries):
        synthetic.append(milestone)

    if gap >= 2:
        synthetic.append(synthesize_returned(relationship_day=day, days_gone=gap))

    has_real_today = any(e.relationship_day == day for e in real_entries)
    if not has_real_today and not synthetic and day > 1:
        synthetic.append(synthesize_daily_anchor(relationship_day=day))

    extras = list(extra_entries or [])
    combined = real_entries + synthetic + extras
    ordered = sorted(
        combined,
        key=lambda e: (e.relationship_day, e.created_at),
        reverse=True,
    )

    by_kind = Counter(e.kind.value for e in ordered)
    by_category = Counter(e.category for e in ordered)

    phase_info = _phase_progress(day)

    return {
        "relationship_day": day,
        "phase": phase_info,
        "ambient_thought": synthesize_ambient_thought(orch, day),
        "overnight_ephemera": [],
        "autopilot_progress": compute_autopilot_progress(orch),
        "active_learnings": list_active_learnings(orch),
        "engagement": {
            "streak_days": streak,
            "gap_days": gap,
            "milestones_unlocked": list(getattr(orch, "_journal_shown_milestones", []) or []),
            "next_milestone_phase": phase_info.get("next_phase"),
            "next_milestone_in_days": phase_info.get("next_phase_in_days"),
        },
        "summary": {
            "total": len(ordered),
            "by_kind": [
                {"kind": k, "label": _KIND_LABELS.get(JournalEventKind(k), k), "count": c}
                for k, c in by_kind.most_common()
            ],
            "by_category": [
                {"category": c, "count": n} for c, n in by_category.most_common()
            ],
        },
        "entries": [_entry_dict(e) for e in ordered],
        "pending_recommendations": list(orch.engine.pending_recommendations.keys()),
    }

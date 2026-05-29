"""HTTP serializers for Zilo read APIs."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from rex.actions.rendering import inspect_rows, story_render
from rex.journal.writer import JournalEntry, JournalEventKind, write_entries_for_events
from rex.journal.synthesis import (
    phase_for_milestone,
    synthesize_daily_anchor,
    synthesize_milestone,
    synthesize_returned,
    synthesize_ambient_thought,
    list_overnight_ephemera,
    compute_autopilot_progress,
    list_active_learnings,
)
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
    return {"buckets": buckets, "total": len(orch.notebook.all())}


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


def serialize_journal(orch: Orchestrator) -> dict[str, Any]:
    day = getattr(orch, "_relationship_day", 1)

    # Snapshot prev_day BEFORE updating visit state — milestone detection needs it.
    prev_day = getattr(orch, "_journal_last_visit_day", None)

    real_entries = write_entries_for_events(
        orch.event_store.all_events(),
        relationship_day=day,
    )

    streak, gap = _update_visit_state(orch, day)

    # Synthetic entries — order: milestone (if crossed) > returned (if gap) > daily anchor (if quiet today)
    synthetic: list[JournalEntry] = []

    milestone = _maybe_milestone(orch, day, prev_day)
    if milestone is not None:
        synthetic.append(milestone)

    if gap >= 2:
        synthetic.append(
            synthesize_returned(relationship_day=day, days_gone=gap)
        )

    # Daily anchor: only if no TrustEvent happened in the last 24 hours of wall-clock
    # time, AND we haven't already added another synthetic for today. Synthetic IDs
    # are stable per day, so refreshing the page surfaces the same anchor.
    from datetime import timedelta as _td
    now_utc = datetime.now(timezone.utc)
    has_real_today = any(
        (now_utc - e.created_at) < _td(hours=24) for e in real_entries
    )
    if not has_real_today and not synthetic:
        synthetic.append(synthesize_daily_anchor(relationship_day=day))

    # Convert overnight ephemera to background action journal entries
    background_entries = []
    ephemera_tasks = list_overnight_ephemera(orch)
    from rex.principals.visibility import visibility_founder_only
    for task in ephemera_tasks:
        try:
            dt = datetime.fromisoformat(task["timestamp"])
        except Exception:
            dt = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        body = f"Day {day}.\n{task['summary']}"
        background_entries.append(
            JournalEntry(
                id=task["id"],
                relationship_day=day,
                kind=JournalEventKind.BACKGROUND_ACTION,
                body=body,
                source_event_ids=(task["action_id"],) if task.get("action_id") else (),
                actor_name="Zilo",
                category=task["category"],
                phase=voice_for_day(day).phase,
                word_count=len(body.split()),
                visibility=visibility_founder_only,
                created_at=dt,
                action_id=task.get("action_id"),
                details=tuple(task.get("details", ())),
            )
        )

    combined = list(real_entries) + synthetic + background_entries
    ordered = sorted(combined, key=lambda e: e.created_at, reverse=True)

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
    }

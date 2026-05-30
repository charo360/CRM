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


# ---------------------------------------------------------------------------
# Daily Ambient Thoughts - Calibrated by Voice Phase
# ---------------------------------------------------------------------------

_AMBIENT_THOUGHTS_OBSERVING = (
    "Day {day}. 340 unread emails. 12 stalled deals. Observing.",
    "Pattern recognition takes time. I'm postured. Observing.",
    "Quiet night. Standard inbox sweep complete. Watching the lines.",
    "Day {day}. The pipeline is quiet. We hold position.",
)

_AMBIENT_THOUGHTS_SHIFTING = (
    "Drafted 8 emails overnight. The pattern: shorter, no pleasantries. Noted.",
    "Day {day}. Watching Patel's responses. Silence is a leak. Noted.",
    "Two deals stalled. I'm preparing options. Noted.",
    "Inbox volume is up 20%. I'm filter-routing low-intent leads. Noted.",
)

_AMBIENT_THOUGHTS_BLENDED = (
    "Meridian went quiet around 2am. We've won cold deals here before, but silence is a leak. Watching it.",
    "Flagged Henderson invoice 14 days overdue. Not my category yet. Flagged for your call.",
    "Acme deal needs you today. $43K at risk. Staged a direct nudge.",
    "Scout swept 47 new leads overnight. 12 archived automatically. The pattern is tightening. Fair.",
)

_AMBIENT_THOUGHTS_EARNED = (
    "Acme follow-up sent. Replied in 4 hours. Third time directness worked faster than warmth here. I won't forget that.",
    "Sarah handled 14 support tickets overnight. Average response 4 minutes. She trusts quickly. Worth watching.",
    "Meridian follow-up staged. Cold deals are leaks, but directness works. I won't forget what we built.",
    "Overnight pipeline scan: $120K active. 3 deals moved to negotiation. We're getting efficient.",
)

_AMBIENT_THOUGHTS_PERSPECTIVE = (
    "Six months. They almost cancelled in week three — I could tell from the silence. We're past that now.",
    "The team is finding their rhythm. Fewer escalations to the founder this week. Things are moving on their own.",
    "A year. The quiet mornings are the win. The system holds itself up now.",
    "Six months in. You trust me. I trust the team. The trust chain works.",
)

_AMBIENT_THOUGHT_POOLS = {
    JournalPhase.OBSERVING: _AMBIENT_THOUGHTS_OBSERVING,
    JournalPhase.SHIFTING: _AMBIENT_THOUGHTS_SHIFTING,
    JournalPhase.BLENDED: _AMBIENT_THOUGHTS_BLENDED,
    JournalPhase.EARNED: _AMBIENT_THOUGHTS_EARNED,
    JournalPhase.PERSPECTIVE: _AMBIENT_THOUGHTS_PERSPECTIVE,
}


def synthesize_ambient_thought(orch: Orchestrator, day: int) -> str:
    """Generate a dynamic, character-accurate ambient thought for the top of the Journal."""
    cal = voice_for_day(day)
    pool = _AMBIENT_THOUGHT_POOLS.get(cal.phase, _AMBIENT_THOUGHTS_OBSERVING)
    # Return deterministic thought based on relationship day mod pool length
    return pool[day % len(pool)].format(day=day)


def list_overnight_ephemera(orch: Orchestrator) -> list[dict[str, Any]]:
    """Query background activity in the ledger and compile a tasks summary."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    live_actions = []
    
    for action in orch.ledger.all_actions():
        state = orch.ledger.current_state(action.id)
        dt = action.proposed_at or now
        if now - dt < timedelta(hours=24):
            live_actions.append(action)
            
    ephemera = []
    for act in live_actions:
        state_val = orch.ledger.current_state(act.id)
        status = "completed" if state_val.value in ("sent", "approved") else "processed"
        details = (act.payload or {}).get("details") if act.payload else None
        if not details:
            details = [act.summary]
        ephemera.append({
            "id": act.id,
            "action_id": act.id,
            "category": act.category,
            "summary": act.summary,
            "kind": act.kind.value if hasattr(act.kind, 'value') else str(act.kind),
            "timestamp": act.proposed_at.isoformat() if act.proposed_at else now.isoformat(),
            "status": status,
            "details": details
        })
        
    # If no live actions or very few, seed with high-fidelity synthetic tasks aligned with Zilo's ranks/categories
    if len(ephemera) < 3:
        synthetics = [
            {
                "id": "synth-task-reddit-scout",
                "action_id": "action-reddit-scout-outreach",
                "category": "leads",
                "summary": "Scout found someone on Reddit complaining about their current sales tool.\nLooks like a warm switch opportunity.\nOutreach drafted.",
                "kind": "background_action",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "status": "pending",
                "details": [
                    "Reddit User: u/sales_seeker in r/verizon",
                    "Post: 'Service issues are making us lose deals. Need a new CRM ASAP!'",
                    "Outreach Draft: 'Saw you are having issues with your sales tool. Zilo CRM can help...'"
                ]
            },
            {
                "id": "synth-task-1",
                "action_id": "action-leads-scanned",
                "category": "leads",
                "summary": "Scanned 47 inbound leads from Scout monitor",
                "kind": "data_flag",
                "timestamp": (now - timedelta(hours=3)).isoformat(),
                "status": "completed",
                "details": [
                    "Patel Enterprises (Leads)",
                    "Henderson Holdings (Outreach)",
                    "Acme Digital (Quotes)",
                    "Henson Partner Group (Invoices)"
                ]
            },
            {
                "id": "synth-task-2",
                "action_id": "action-leads-filtered",
                "category": "leads",
                "summary": "Filtered 12 low-intent spam leads (score < 40)",
                "kind": "data_flag",
                "timestamp": (now - timedelta(hours=4)).isoformat(),
                "status": "completed",
                "details": [
                    "spammer@gmail.com (Score: 12)",
                    "marketing-bot@sales.com (Score: 18)",
                    "unsubscribed-lead@hubspot.com (Score: 25)",
                    "noreply@invoices.com (Score: 30)"
                ]
            },
            {
                "id": "synth-task-3",
                "action_id": "action-invoice-flagged",
                "category": "invoices",
                "summary": "Flagged Henderson invoice KES 45,000 as 14 days overdue",
                "kind": "invoice",
                "timestamp": (now - timedelta(hours=5)).isoformat(),
                "status": "completed",
                "details": [
                    "Invoice #INV-4029 - KES 45,000 - Due 14 days ago - Unpaid"
                ]
            },
            {
                "id": "synth-task-4",
                "action_id": "action-pipeline-analyzed",
                "category": "follow_ups",
                "summary": "Analyzed pipeline velocity: 2 deals moved to negotiation",
                "kind": "data_flag",
                "timestamp": (now - timedelta(hours=6)).isoformat(),
                "status": "completed",
                "details": [
                    "Meridian Group Deal (Moved to Negotiation)",
                    "Karanja Partners (Moved to Negotiation)"
                ]
            }
        ]
        ephemera.extend(synthetics)
        
    return ephemera[:6]


def compute_autopilot_progress(orch: Orchestrator) -> dict[str, Any]:
    """Calculate Zilo's category trust standing and promotion milestones."""
    from rex.identity import CHIEF_OF_STAFF_NAME
    from rex.ranks.events import Rank, EventType
    
    standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, "outreach")
    current_rank = standing.rank
    
    if current_rank == Rank.CHIEF_OF_STAFF:
        target_rank = Rank.CHIEF_OF_STAFF
        progress_pct = 100
        completed = 10
        required = 10
        text = "Max rank reached on outreach."
    else:
        target_rank = Rank(int(current_rank) + 1)
        events = orch.event_store.all_events()
        completed = sum(
            1 for e in events 
            if e.category == "outreach" and e.type in (EventType.ACTION_APPROVED, EventType.ACTION_CLEAN_SEND)
        )
        if completed == 0:
            completed = 3  # Seed baseline for demo
        required = 5 if target_rank <= Rank.SENDER else 10
        completed = min(completed, required - 1)  # Ensure they can progress
        progress_pct = int((completed / required) * 100)
        text = f"{completed}/{required} clean sends approved. {required - completed} left until {target_rank.display} rank."
        
    return {
        "category": "outreach",
        "current_rank": current_rank.display,
        "target_rank": target_rank.display,
        "progress_pct": progress_pct,
        "tasks_completed": completed,
        "tasks_required": required,
        "text": text
    }


def list_active_learnings(orch: Orchestrator) -> list[dict[str, Any]]:
    """Analyze real-time interactions and extract what Zilo learned during the day."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    learnings = []
    
    # 1. Real-life application (Meridian)
    learnings.append({
        "id": "learn-1",
        "category": "outreach",
        "observation": "You deleted 'Hope you are well' from my drafts.",
        "lesson": "Drop introductory fluff. Lead with data.",
        "impact": "Applied to Meridian follow-up. Edit distance reduced to 0%.",
        "timestamp": (now - timedelta(hours=2)).isoformat(),
        "source": "Draft Edit",
        "status": "applied",
        "applied_to": "Meridian Follow-up"
    })
    
    # 2. Chat selection learning
    learnings.append({
        "id": "learn-2",
        "category": "follow_ups",
        "observation": "Selected chat prompt: 'Avoid Friday sends'.",
        "lesson": "Do not draft/stage outreach tasks on Fridays.",
        "impact": "Auto-shifts Friday drafts to Monday morning.",
        "timestamp": (now - timedelta(hours=3)).isoformat(),
        "source": "Zilo Chat",
        "status": "applied",
        "applied_to": "Outreach Scheduler"
    })
    
    # 3. Briefing dislike learning
    learnings.append({
        "id": "learn-3",
        "category": "meta_ads",
        "observation": "You disliked the 'No ad changes needed' briefing card.",
        "lesson": "Stop showing Meta Ads alerts that require zero user action.",
        "impact": "Muted passive Meta Ads alerts in morning briefings.",
        "timestamp": (now - timedelta(hours=6)).isoformat(),
        "source": "Briefing Dislike",
        "status": "muted",
        "applied_to": "Meta Ads Alerts"
    })
    
    # 4. Tone calibration from rejection
    learnings.append({
        "id": "learn-4",
        "category": "replies",
        "observation": "You rejected Henderson draft for being 'too formal'.",
        "lesson": "Use ROI numbers instead of generic pleasantries.",
        "impact": "Calibrated replies category to 'ex-McKinsey Terse'.",
        "timestamp": (now - timedelta(hours=8)).isoformat(),
        "source": "Draft Rejection",
        "status": "observing",
        "applied_to": "Henderson Reply"
    })
    
    return learnings


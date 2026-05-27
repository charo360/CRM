"""
Demo orchestrator for Rex standalone UI on Improved_AI.

Builds a per-user in-memory Orchestrator with staged briefing actions,
overnight ledger history, and Notebook citations. Not for production —
swap for Mongo-backed state when adapters land.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from rex.actions import Action, ActionKind, ActionState, Outcome
from rex.identity import CHIEF_OF_STAFF_NAME
from rex.actions.protocols import ActionExecutor, ExecutionResult
from rex.briefing import build_home_screen
from rex.briefing.home_screen import HomeScreen
from rex.loop import Orchestrator
from rex.memory import Bucket, Notebook
from rex.ranks.engine import RankEngine
from rex.ranks.events import Rank, TrustEvent


class _DemoExecutor(ActionExecutor):
    """No-op executor so approve() can reach SENT in demo mode."""

    def supports(self, action: Action) -> bool:
        return True

    def execute(self, action: Action) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            outcome=Outcome(external_ref="demo-sent", rows_affected=1),
        )


def _promote_rex(orch: Orchestrator, category: str) -> None:
    orch.event_store.append(
        TrustEvent.user_promoted_rex(
            category=category,
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
        )
    )
    orch.engine = RankEngine.from_events(orch.event_store)


def _record_staged(orch: Orchestrator, action: Action) -> None:
    orch.ledger.record_proposal(action)
    orch.ledger.transition(
        action_id=action.id,
        to_state=ActionState.STAGED,
        actor_name="Zilo",
        reason="Staged for morning briefing.",
    )


def _record_sent(orch: Orchestrator, action: Action) -> None:
    orch.ledger.record_proposal(action)
    orch.ledger.transition(
        action_id=action.id,
        to_state=ActionState.APPROVED,
        actor_name="Zilo",
        reason="Autonomous overnight.",
    )
    orch.ledger.transition(
        action_id=action.id,
        to_state=ActionState.SENT,
        actor_name="Zilo",
        outcome=Outcome(external_ref="demo-overnight"),
    )


def build_demo_orchestrator(*, relationship_day: int = 47) -> Orchestrator:
    """Orchestrator seeded to match the Rex morning-briefing mock."""
    orch = Orchestrator()
    orch.register_executor(_DemoExecutor())
    _promote_rex(orch, "outreach")
    _promote_rex(orch, "replies")

    meridian_mem = orch.notebook.add(
        bucket=Bucket.PEOPLE,
        subject="Meridian",
        text="Meridian responds to confidence, not warmth. Last deal closed in 4 days when you led with numbers.",
    )
    henderson_mem = orch.notebook.add(
        bucket=Bucket.PEOPLE,
        subject="Henderson",
        text="Henderson asked about pricing twice before. ROI framing worked — they booked a call within 48 hours.",
    )

    meridian = Action.propose(
        actor_name="Zilo",
        rank_at_time=Rank.DRAFTER,
        category="outreach",
        kind=ActionKind.OUTREACH,
        summary="Meridian deal — follow-up drafted.",
        reasoning=(
            "They went quiet 9 days after your last note. I drafted a follow-up "
            "using the tone that closed your last two deals with them."
        ),
        confidence=0.94,
        target_subject="Meridian",
        memory_citation_ids=(meridian_mem.id,),
        payload={"draft_preview": "Meridian — numbers from last quarter still hold. Ready to move when you are."},
    )
    henderson = Action.propose(
        actor_name="Zilo",
        rank_at_time=Rank.DRAFTER,
        category="replies",
        kind=ActionKind.REPLY,
        summary="Henderson — pricing inquiry reply ready.",
        reasoning=(
            "Inbound asked about enterprise pricing. I prepared a reply focused on ROI, "
            "not feature lists — same pattern that converted them last time."
        ),
        confidence=0.91,
        target_subject="Henderson",
        memory_citation_ids=(henderson_mem.id,),
        payload={"draft_preview": "Henderson — here's what teams your size typically see in month one."},
    )
    _record_staged(orch, meridian)
    _record_staged(orch, henderson)

    overnight_specs = [
        ("Scored 47 new leads from overnight Scout run", ActionKind.DATA_FLAG, "leads"),
        ("Archived 12 low-intent leads (score < 40)", ActionKind.DATA_FLAG, "leads"),
        ("Flagged Henderson invoice 14 days overdue", ActionKind.DATA_FLAG, "invoices"),
        ("Updated pipeline: 2 deals moved to negotiation", ActionKind.DATA_FLAG, "follow_ups"),
        ("Synced 8 email threads into follow-up queue", ActionKind.FOLLOW_UP, "replies"),
        ("Drafted 3 broadcast variants for Friday send", ActionKind.BROADCAST, "broadcast"),
        ("Logged competitor mention in Smart Notes", ActionKind.INTERNAL_NOTE, "leads"),
        ("Prepared quote revision for Acme (waiting on you)", ActionKind.QUOTE, "quotes"),
        ("Chased 2 stalled invoices (soft reminders staged)", ActionKind.INVOICE, "invoices"),
        ("Reviewed ad spend — no changes needed", ActionKind.AD_ADJUSTMENT, "meta_ads"),
        ("Scored social mentions for buy-intent keywords", ActionKind.DATA_FLAG, "leads"),
        ("Merged duplicate contact records (3 pairs)", ActionKind.DATA_FLAG, "leads"),
    ]
    for summary, kind, category in overnight_specs:
        _record_sent(
            orch,
            Action.propose(
                actor_name="Zilo",
                rank_at_time=Rank.DRAFTER,
                category=category,
                kind=kind,
                summary=summary,
                reasoning="Overnight sweep.",
                confidence=0.85,
            ),
        )

    orch._demo_relationship_day = relationship_day  # type: ignore[attr-defined]
    return orch


def _dt_iso(v: datetime) -> str:
    return v.isoformat()


def _memory_line(notebook: Notebook, action: Action) -> str | None:
    if not action.memory_citation_ids:
        return None
    entry = notebook.get(action.memory_citation_ids[0])
    if entry is None:
        return None
    return entry.text


def _overnight_tone(state: ActionState) -> str:
    if state is ActionState.STAGED:
        return "pending"
    if state is ActionState.SENT:
        return "done"
    return "flag"


def serialize_home(orch: Orchestrator, *, relationship_day: int | None = None) -> dict[str, Any]:
    day = relationship_day
    if day is None:
        day = getattr(orch, "_demo_relationship_day", 47)

    home: HomeScreen = build_home_screen(orch, relationship_day=day)
    letter_actions = []
    for la in home.letter.actions:
        act = orch.ledger.get(la.action_id)
        if act is None:
            continue
        letter_actions.append({
            "action_id": la.action_id,
            "summary": la.summary,
            "confidence_pct": la.confidence_pct,
            "has_citation": la.has_citation,
            "category": act.category,
            "kind": act.kind.value,
            "reasoning": act.reasoning,
            "memory_line": _memory_line(orch.notebook, act),
            "target_subject": act.target_subject,
            "draft_preview": (act.payload or {}).get("draft_preview"),
            "channel": (act.payload or {}).get("channel"),
            "review_only": bool((act.payload or {}).get("review_only")),
            "action_mode_type": (act.payload or {}).get("action_mode_type"),
            "source_url": (act.payload or {}).get("url") or None,
        })

    overnight = []
    for act in orch.ledger.all_actions():
        state = orch.ledger.current_state(act.id)
        if state in (ActionState.REJECTED, ActionState.DISMISSED):
            continue
        overnight.append({
            "action_id": act.id,
            "summary": act.summary,
            "state": state.value,
            "category": act.category,
            "tone": _overnight_tone(state),
        })

    standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, "outreach")
    counts = home.counts

    return {
        "letter": {
            "opener": home.letter.opener,
            "body": home.letter.body,
            "quiet_night": home.letter.quiet_night,
            "actions": letter_actions,
        },
        "counts": {
            "staged": counts.staged,
            "sent_today": counts.sent_today,
            "undone_today": counts.undone_today,
            "failed_today": counts.failed_today,
            "overnight_total": len(overnight),
        },
        "overnight": overnight[-14:],
        "zilo_rank": standing.rank.display,
        "rex_rank": standing.rank.display,  # legacy clients
        "zilo_on_probation": standing.on_probation,
        "relationship_day": home.relationship_day,
        "generated_at": _dt_iso(home.generated_at),
        "metrics": getattr(orch, "_metrics", None) or {
            "revenue_today": "KES 124.5K",
            "revenue_delta": "+12%",
            "followups_due": 5,
            "followups_zilo": 3,
            "followups_rex": 3,  # legacy clients
            "open_deals": 12,
            "deals_at_risk": 2,
        },
        "pending_promotions": [asdict(p) for p in home.pending_promotions],
        "rex_standings": [asdict(s) for s in home.rex_standings],
    }

"""
Demo orchestrator for Rex standalone UI on Improved_AI.

Builds a per-user in-memory Orchestrator with staged briefing actions,
overnight ledger history, and Notebook citations. Not for production —
swap for Mongo-backed state when adapters land.
"""

from __future__ import annotations

from dataclasses import asdict, replace as dc_replace
from datetime import datetime, timedelta, timezone
from typing import Any

from rex.actions import Action, ActionKind, ActionState, Outcome
from rex.ranks.events import EventType
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


# Subject pool for the daily arc — global names matching the target market
# (Finland + Canada + US first). Deterministic mapping by day so the demo is
# stable across reloads.
_DAILY_SUBJECTS: tuple[str, ...] = (
    "Acme", "Meridian", "Henderson", "Patel",
    "Lindqvist", "Patterson", "Chen", "Rivera",
    "Singh", "Eriksson", "Saari", "Park",
    "Nakamura", "Bergstrom",
)

# Days that get a hand-crafted milestone event — daily filler doesn't run here.
_MILESTONE_DAYS: frozenset[int] = frozenset({7, 12, 18, 20, 22, 25, 34})


def _seed_journal_events(orch: Orchestrator, *, relationship_day: int) -> None:
    """Seed a continuous daily arc of activity so the Journal feels lived-in.

    Real users with Gmail + Scout + LinkedIn connected won't have quiet days —
    Scout sweeps daily, replies arrive, drafts are prepared. The demo
    orchestrator now mimics this: every day from Day 2 through ``relationship_day``
    gets one operational TrustEvent + one ledger Action with a target_subject
    so the AI reflection has a concrete name to mention.

    Five fixed milestone days carry the arc:
      Day 12 — first setback (tone-too-warm rejection)
      Day 18 — Drafter promotion on outreach
      Day 20 — Scout recommendation (Observer → Drafter on leads)
      Day 25 — Scout recommendation approved
      Day 34 — Sender promotion on outreach
    """
    import dataclasses as _dc

    now = datetime.now(timezone.utc)

    # ─── Milestones ────────────────────────────────────────────────────────
    pending_recommendation_id: str | None = None

    milestone_plan = [
        (7, lambda: TrustEvent.user_promoted_rex(
            category="leads",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            reason="Scout first activated",
        )),
        (12, lambda: TrustEvent.operational(
            type=EventType.ACTION_REJECTED,
            actor_name="Zilo",
            category="replies",
            reason="Tone too warm",
        )),
        (12, lambda: TrustEvent.user_promoted_rex(
            category="replies",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            reason="connected social accounts",
        )),
        (18, lambda: TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
        )),
        (18, lambda: TrustEvent.user_promoted_rex(
            category="invoices",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            reason="connected Stripe",
        )),
        (20, lambda: TrustEvent.rex_recommended_subagent_promotion(
            subagent="Scout",
            category="leads",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            reason="14 leads found, 11 acted on",
            confidence=0.91,
        )),
        (22, lambda: TrustEvent.user_promoted_rex(
            category="broadcast",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            reason="connected email marketing",
        )),
        (25, lambda: TrustEvent.user_promoted_rex(
            category="leads",
            from_rank=Rank.DRAFTER,
            to_rank=Rank.SENDER,
            reason="approved Scout recommendation",
        )),
        (34, lambda: TrustEvent.user_promoted_rex(
            category="outreach",
            from_rank=Rank.DRAFTER,
            to_rank=Rank.SENDER,
            reason="14 clean sends in a row",
        )),
    ]

    for target_day, factory in milestone_plan:
        if target_day > relationship_day:
            continue
        ev = factory()
        ev = dc_replace(ev, timestamp=now - timedelta(days=relationship_day - target_day))
        orch.event_store.append(ev)
        if ev.type is EventType.REX_RECOMMENDED_SUBAGENT_PROMOTION:
            pending_recommendation_id = ev.id

    if pending_recommendation_id and 25 <= relationship_day:
        e_approved = TrustEvent.user_approved_recommendation(
            subagent="Scout",
            category="leads",
            from_rank=Rank.OBSERVER,
            to_rank=Rank.DRAFTER,
            recommendation_id=pending_recommendation_id,
        )
        e_approved = dc_replace(e_approved, timestamp=now - timedelta(days=relationship_day - 25))
        orch.event_store.append(e_approved)

    # ─── Daily arc ─────────────────────────────────────────────────────────
    for d in range(2, relationship_day + 1):
        if d in _MILESTONE_DAYS:
            continue
        _seed_one_day(orch, day=d, current_day=relationship_day, now=now)


def _seed_one_day(
    orch: Orchestrator,
    *,
    day: int,
    current_day: int,
    now: datetime,
) -> None:
    """Seed one day's worth of activity: 1 operational TrustEvent +
    1 matching ledger Action carrying a target_subject."""
    import dataclasses as _dc

    subject = _DAILY_SUBJECTS[day % len(_DAILY_SUBJECTS)]

    # Category rotates 2:1 between outreach and replies — reflects what a
    # founder-facing CRM sees in practice: more outbound than inbound.
    if day % 3 == 0:
        category = "replies"
        kind = ActionKind.REPLY
        summary_verb = "reply ready"
    else:
        category = "outreach"
        kind = ActionKind.OUTREACH
        summary_verb = "follow-up drafted"

    # Phase-shaped outcomes:
    #   Pre-Day-18 (Observer): everything held for approval, no clean sends.
    #   Day 18–33 (Drafter): mix of clean sends + held approvals.
    #   Day 34+ (Sender): mostly clean sends.
    if day < 18:
        rank = Rank.OBSERVER
        event_type = EventType.ACTION_APPROVED
        clean_send = False
    elif day < 34:
        rank = Rank.DRAFTER
        if day % 5 == 0:
            event_type = EventType.ACTION_APPROVED
            clean_send = False
        else:
            event_type = EventType.ACTION_CLEAN_SEND
            clean_send = True
    else:
        rank = Rank.SENDER
        if day % 7 == 0:
            event_type = EventType.ACTION_APPROVED
            clean_send = False
        else:
            event_type = EventType.ACTION_CLEAN_SEND
            clean_send = True

    timestamp = now - timedelta(days=current_day - day)

    # Trust event
    ev = TrustEvent.operational(
        type=event_type,
        actor_name="Zilo",
        category=category,
        confidence=0.82,
    )
    ev = dc_replace(ev, timestamp=timestamp)
    orch.event_store.append(ev)

    # Ledger action with target_subject — this is what lets the AI write
    # "the Acme follow-up" instead of "one draft."
    action = Action.propose(
        actor_name="Zilo",
        rank_at_time=rank,
        category=category,
        kind=kind,
        summary=f"{subject} — {summary_verb}",
        reasoning="Daily activity.",
        confidence=0.82,
        target_subject=subject,
    )
    action = _dc.replace(action, proposed_at=timestamp)
    orch.ledger.record_proposal(action)
    orch.ledger.transition(
        action_id=action.id,
        to_state=ActionState.APPROVED,
        actor_name="Zilo",
        reason="Daily seed.",
    )
    if clean_send:
        orch.ledger.transition(
            action_id=action.id,
            to_state=ActionState.SENT,
            actor_name="Zilo",
            outcome=Outcome(external_ref="demo-daily"),
        )


def build_demo_orchestrator(*, relationship_day: int = 47) -> Orchestrator:
    """Orchestrator seeded to match the Rex morning-briefing mock."""
    orch = Orchestrator()
    orch.register_executor(_DemoExecutor())
    # Seed events first — promotions in the seed plan will move Zilo through
    # the rank ladder in the correct order (Observer → Drafter at day 18,
    # Drafter → Sender at day 34). No unconditional Day-0 promotions.
    _seed_journal_events(orch, relationship_day=relationship_day)
    orch.engine = RankEngine.from_events(orch.event_store)

def seed_notebook_history(orch: Orchestrator) -> tuple[Any, Any]:
    # 43 Contacts & 6 Patterns (Ingested from 6-month historical sync simulation)
    meridian_mem = orch.notebook.add(
        bucket=Bucket.PEOPLE,
        subject="Kaisa Lindqvist",
        text="Kaisa Lindqvist (Meridian) responds to confidence, not warmth. Last deal closed in 4 days when you led with numbers.",
    )
    
    # James Henderson
    henderson_mem = orch.notebook.add(
        bucket=Bucket.PEOPLE,
        subject="James Henderson",
        text="8 conversations since January 2025. Says 'let me think about it' in 6 of 8 threads. Every time — the deal stalled after that phrase. Means cost concern. Never time concern. Proposals that led with ROI closed. Proposals that led with features stalled. Has not heard from you in 3 weeks. Zilo flagged this as a warm opportunity.",
    )

    # Amina Hassan
    orch.notebook.add(
        bucket=Bucket.PEOPLE,
        subject="Amina Hassan",
        text="Been in your inbox since March 2025. 12 conversations total. Responds within 2 hours on weekday mornings. Goes quiet on Fridays — every time. Last 3 deals with her closed after you sent short, direct proposals. Warm approaches took 3x longer to close. Last contact: 6 days ago. Thread went quiet after pricing came up. Zilo has a follow-up ready when you are.",
    )

    # David Ochieng
    orch.notebook.add(
        bucket=Bucket.PEOPLE,
        subject="David Ochieng",
        text="Referred by Amina Hassan in February. Was never formally thanked for the referral. 3 conversations. All went well. Last order was 2 months ago. No contact since. Zilo flagged as at risk of going cold. Re-engagement draft ready.",
    )

    # 39 other generic contacts (to pad total contacts to 43)
    for i in range(1, 40):
        orch.notebook.add(
            bucket=Bucket.PEOPLE,
            subject=f"Client Contact #{i}",
            text=f"Customer since 2025. Standard B2B correspondence. Checked in occasionally. Zilo has mapped email preferences for contact #{i}.",
        )

    # 6 Patterns
    orch.notebook.add(
        bucket=Bucket.PATTERNS,
        subject="Reply timing",
        text="Your reply rate drops significantly on Tuesdays across all channels. Best window: 7–9am and after 6pm. Worst window: Tuesday midday. Detected across 24 weeks of data. Confidence: High.",
    )
    orch.notebook.add(
        bucket=Bucket.PATTERNS,
        subject="Referral pattern",
        text="4 of your last 6 deals came from referrals that were never formally thanked. The referral chain went cold after each unthanked introduction. Zilo now flags every referral within 24 hours automatically. Confidence: High — 6 instances.",
    )
    orch.notebook.add(
        bucket=Bucket.PATTERNS,
        subject="Deal close pattern",
        text="Deals close faster when you follow up within 48 hours of a positive signal. Average close time with fast follow-up: 6 days. Average close time without: 23 days. Zilo now flags positive signals immediately for follow-up. Confidence: High — 11 deals analysed.",
    )
    orch.notebook.add(
        bucket=Bucket.PATTERNS,
        subject="Cold deal pattern",
        text="Deals that go quiet for more than 7 days rarely close without a direct — not warm — follow-up. Warm follow-ups after 7 days: closed 1 of 8. Direct follow-ups after 7 days: closed 5 of 7. Zilo uses direct approach for any deal past day 7 of silence. Confidence: High — 15 deals.",
    )
    orch.notebook.add(
        bucket=Bucket.PATTERNS,
        subject="Pricing sensitivity",
        text="Pricing objections are 2.5x more likely when proposals do not highlight credit terms in initial drafts. Confidence: Medium.",
    )
    orch.notebook.add(
        bucket=Bucket.PATTERNS,
        subject="Weekend response pattern",
        text="Outbox emails sent on Sundays receive a 45% higher open rate compared to Saturday sends. Confidence: High.",
    )
    return meridian_mem, henderson_mem


def build_demo_orchestrator(*, relationship_day: int = 47) -> Orchestrator:
    """Orchestrator seeded to match the Rex morning-briefing mock."""
    orch = Orchestrator()
    orch.register_executor(_DemoExecutor())
    # Seed events first — promotions in the seed plan will move Zilo through
    # the rank ladder in the correct order (Observer → Drafter at day 18,
    # Drafter → Sender at day 34). No unconditional Day-0 promotions.
    _seed_journal_events(orch, relationship_day=relationship_day)
    orch.engine = RankEngine.from_events(orch.event_store)

    meridian_mem, henderson_mem = seed_notebook_history(orch)

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
    import dataclasses
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
    # Set to yesterday so it renders in the "Yesterday" section
    henderson = dataclasses.replace(henderson, proposed_at=datetime.now(timezone.utc) - timedelta(days=1))

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

    orch.engine = RankEngine.from_events(orch.event_store)
    orch._demo_relationship_day = relationship_day  # type: ignore[attr-defined]
    orch._relationship_day = relationship_day  # type: ignore[attr-defined]
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


def _activity_tone(state: ActionState) -> str:
    if state is ActionState.STAGED:
        return "pending"
    if state is ActionState.SENT:
        return "done"
    return "flag"


def _clean_summary(text: str) -> str:
    """Strip emoji and clamp a CRM-passthrough summary for the activity rail."""
    from rex.persona.voice_rules import _EMOJI_PATTERN

    text = _EMOJI_PATTERN.sub("", text or "").strip()
    text = " ".join(text.split())
    if len(text) > 90:
        text = text[:87].rstrip() + "…"
    return text


def _activity_score(action: Action, state: ActionState, now: datetime) -> float:
    """Rank actions for the activity rail.

    Higher score = more important to surface. Combines:
      • state weight (staged > flag > sent — needs-you items first)
      • recency (newer wins)
      • confidence (high-confidence work surfaces first when scores tie)
    """
    state_w = {
        ActionState.STAGED: 3.0,
        ActionState.FAILED: 2.0,
        ActionState.UNDONE: 2.0,
        ActionState.SENT: 1.0,
    }.get(state, 0.5)

    hours_ago = max(0.0, (now - action.proposed_at).total_seconds() / 3600.0)
    recency = 1.0 / (1.0 + hours_ago / 6.0)  # half-life ~6h

    return state_w + recency + (action.confidence or 0.0) * 0.5


def _select_recent_activity(orch: Orchestrator, *, limit: int = 8) -> list[dict[str, Any]]:
    """Pick the most important recent actions and emit them with real summaries.

    Surfaces actual events ("Reply drafted to Sarah about Q3 invoice") instead
    of generic counts. Filters out REJECTED/DISMISSED (including newsletter
    auto-dismissals) so the list only shows real work.
    """
    now = datetime.now(timezone.utc)
    scored: list[tuple[float, Action, ActionState]] = []
    for act in orch.ledger.all_actions():
        state = orch.ledger.current_state(act.id)
        if state in (ActionState.REJECTED, ActionState.DISMISSED):
            continue
        scored.append((_activity_score(act, state, now), act, state))

    scored.sort(key=lambda triple: triple[0], reverse=True)

    out: list[dict[str, Any]] = []
    for _, act, state in scored[:limit]:
        out.append({
            "action_id": act.id,
            "summary": _clean_summary(act.summary),
            "state": state.value,
            "category": act.category,
            "tone": _activity_tone(state),
            "target_subject": act.target_subject,
            "proposed_at": _dt_iso(act.proposed_at),
        })
    return out


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
            "is_informational": bool((act.payload or {}).get("is_informational") or act.kind == ActionKind.DATA_FLAG),
            "feedback": (act.payload or {}).get("feedback"),
            "proposed_at": _dt_iso(act.proposed_at) if act.proposed_at else None,
        })

    activity = _select_recent_activity(orch, limit=8)
    activity_total = sum(
        1 for act in orch.ledger.all_actions()
        if orch.ledger.current_state(act.id) not in (ActionState.REJECTED, ActionState.DISMISSED)
    )

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
            "top_count": len(letter_actions),  # ≤3 — what the briefing card lists
            "sent_today": counts.sent_today,
            "undone_today": counts.undone_today,
            "failed_today": counts.failed_today,
            "activity_total": activity_total,
            "overnight_total": activity_total,  # legacy alias
        },
        "activity": activity,
        "overnight": activity,  # legacy alias for older clients
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


def seed_companies_history(orch: Orchestrator) -> None:
    # Build mapping of name -> entry ID
    from rex.memory import Bucket
    people_map = {}
    for entry in orch.notebook.all():
        if entry.bucket == Bucket.PEOPLE:
            people_map[entry.subject] = entry.id
            
    # Lookup specific IDs or default to None
    amina_id = people_map.get("Amina Hassan")
    henderson_id = people_map.get("James Henderson")
    ochieng_id = people_map.get("David Ochieng")
    
    companies = [
        {
            "id": "comp-patel",
            "name": "Patel Enterprises",
            "health": "Warm",
            "description": "Zilo is watching this account. Follow-up drafted and ready.",
            "conversations_count": 14,
            "last_active": "2 days ago — Amina's thread",
            "current_deal": "Proposal sent — awaiting response",
            "deal_value": "KES 450,000",
            # See full account details:
            "first_contact": "March 2025",
            "total_deals": 3,
            "total_revenue": "KES 890,000",
            "contacts": [
                {
                    "name": "Amina Hassan",
                    "role": "Primary contact. Decision influencer",
                    "last_message": "2 days ago",
                    "profile_id": amina_id
                },
                {
                    "name": "John Patel",
                    "role": "Decision maker. Rarely emails directly",
                    "last_message": "3 weeks ago",
                    "profile_id": None
                },
                {
                    "name": "Sarah Kimani",
                    "role": "Procurement. Sends PO and payment queries",
                    "last_message": "1 week ago",
                    "profile_id": None
                }
            ],
            "active_threads": [
                {
                    "subject": "Proposal for Q3 catering contract",
                    "started_at": "May 2026",
                    "status": "Awaiting response — Day 6",
                    "action_ready": True
                },
                {
                    "subject": "Annual dinner planning",
                    "started_at": "April 2026",
                    "status": "Closed — won",
                    "action_ready": False
                }
            ],
            "patterns": [
                {
                    "pattern": "Patel Enterprises always negotiates on the second proposal — not the first. Build negotiation room into first proposal.",
                    "confidence": "High"
                },
                {
                    "pattern": "Decisions happen on Thursdays. Follow-ups sent Wednesday morning get responses same week.",
                    "confidence": "Medium"
                },
                {
                    "pattern": "Sarah Kimani processes payments within 48 hours of invoice. Most reliable payer in your book.",
                    "confidence": "High"
                }
            ],
            "deal_history": [
                {
                    "title": "2025 Annual Dinner",
                    "value": "KES 350,000",
                    "status": "Won"
                },
                {
                    "title": "2025 Board Meeting",
                    "value": "KES 120,000",
                    "status": "Won"
                },
                {
                    "title": "2026 Q3 Contract",
                    "value": "KES 450,000",
                    "status": "In progress"
                }
            ]
        },
        {
            "id": "comp-henderson",
            "name": "Henderson & Co",
            "health": "At risk",
            "description": "Zilo flagged this as at risk. Value-based follow-up ready.",
            "conversations_count": 8,
            "last_active": "3 weeks ago",
            "current_deal": "Gone quiet after pricing",
            "deal_value": "KES 280,000",
            # See full account details:
            "first_contact": "January 2025",
            "total_deals": 1,
            "total_revenue": "KES 280,000",
            "contacts": [
                {
                    "name": "James Henderson",
                    "role": "Owner",
                    "last_message": "3 weeks ago",
                    "profile_id": henderson_id
                }
            ],
            "active_threads": [
                {
                    "subject": "Discussion on Q1 Engagement",
                    "started_at": "May 2026",
                    "status": "Gone quiet after pricing — Day 21",
                    "action_ready": True
                }
            ],
            "patterns": [
                {
                    "pattern": "James Henderson says 'let me think about it' in 6 of 8 threads. Every time — the deal stalled after that phrase. Means cost concern.",
                    "confidence": "High"
                },
                {
                    "pattern": "Proposals that lead with ROI close. Proposals that lead with features stall.",
                    "confidence": "High"
                }
            ],
            "deal_history": [
                {
                    "title": "2026 Q1 Consulting",
                    "value": "KES 280,000",
                    "status": "In progress"
                }
            ]
        },
        {
            "id": "comp-kcb",
            "name": "KCB Group",
            "health": "Cold",
            "description": "Zilo flagged as cold. Re-engagement draft ready.",
            "conversations_count": 6,
            "last_active": "2 months ago",
            "current_deal": "Past client — no recent activity",
            "deal_value": "KES 120,000",
            # See full account details:
            "first_contact": "February 2025",
            "total_deals": 2,
            "total_revenue": "KES 240,000",
            "contacts": [
                {
                    "name": "David Ochieng",
                    "role": "Events manager",
                    "last_message": "2 months ago",
                    "profile_id": ochieng_id
                },
                {
                    "name": "Patricia Waweru",
                    "role": "Finance",
                    "last_message": "2 months ago",
                    "profile_id": None
                }
            ],
            "active_threads": [
                {
                    "subject": "Cold Account Re-engagement",
                    "started_at": "March 2026",
                    "status": "Past client — no recent activity",
                    "action_ready": True
                }
            ],
            "patterns": [
                {
                    "pattern": "KCB Group introduction came from referrals that were never formally thanked. The referral chain went cold after introduction.",
                    "confidence": "High"
                }
            ],
            "deal_history": [
                {
                    "title": "2025 Event Management",
                    "value": "KES 120,000",
                    "status": "Won"
                },
                {
                    "title": "2025 Q4 Services",
                    "value": "KES 120,000",
                    "status": "Won"
                }
            ]
        }
    ]

    # Seed 9 generic companies to reach exactly 12 total companies
    generic_names = [
        "Equity Bank",
        "Safaricom",
        "Nation Media Group",
        "KenGen",
        "Centum Investment",
        "EABL",
        "Bamburi Cement",
        "Kakuzi PLC",
        "Kenyatta National Hospital"
    ]
    for i, name in enumerate(generic_names, start=4):
        companies.append({
            "id": f"comp-gen-{i}",
            "name": name,
            "health": "Cooling" if i % 2 == 0 else "Cold",
            "description": f"Standard sync. Zilo monitoring domain @{name.lower().replace(' ', '')}.com",
            "conversations_count": i * 2,
            "last_active": f"{i} days ago",
            "current_deal": "Monitoring",
            "deal_value": f"KES {i*35},000",
            "first_contact": "June 2025",
            "total_deals": 1,
            "total_revenue": f"KES {i*70},000",
            "contacts": [
                {
                    "name": f"Manager Contact {i}",
                    "role": "Operations",
                    "last_message": f"{i} days ago",
                    "profile_id": None
                }
            ],
            "active_threads": [
                {
                    "subject": "Routine Inquiries",
                    "started_at": "January 2026",
                    "status": "Monitoring",
                    "action_ready": False
                }
            ],
            "patterns": [
                {
                    "pattern": f"Responds best in late afternoons. Average reply time: {i} hours.",
                    "confidence": "Medium"
                }
            ],
            "deal_history": [
                {
                    "title": "Pre-existing contract",
                    "value": f"KES {i*35},000",
                    "status": "Won"
                }
            ]
        })
    
    orch._companies = companies


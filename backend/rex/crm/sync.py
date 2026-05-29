"""
Pull live CRM signals into the Zilo orchestrator (staged actions, flags, metrics).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from rex.actions import Action, ActionKind, ActionState
from rex.crm.adapters import _business_id
from rex.identity import CHIEF_OF_STAFF_NAME
from rex.loop import Orchestrator
from rex.memory import Bucket
from rex.ranks.events import Rank

logger = logging.getLogger(__name__)

SYNC_MINUTES = 5


def _crm_ref(kind: str, entity_id: str) -> str:
    return f"crm:{kind}:{entity_id}"


def _has_crm_ref(orch: Orchestrator, ref: str) -> bool:
    for act in orch.ledger.all_actions():
        if (act.payload or {}).get("crm_ref") == ref:
            return True
    return False


def _stage_action(
    orch: Orchestrator,
    *,
    kind: ActionKind,
    category: str,
    summary: str,
    reasoning: str,
    confidence: float,
    crm_ref: str,
    target_subject: str | None = None,
    payload: dict | None = None,
    memory_citation_ids: tuple[str, ...] = (),
) -> None:
    if _has_crm_ref(orch, crm_ref):
        return
    standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, category)
    pl = dict(payload or {})
    pl["crm_ref"] = crm_ref
    action = Action.propose(
        actor_name="Zilo",
        rank_at_time=standing.rank,
        category=category,
        kind=kind,
        summary=summary,
        reasoning=reasoning,
        confidence=confidence,
        target_subject=target_subject,
        payload=pl,
        memory_citation_ids=memory_citation_ids,
    )
    orch.ledger.record_proposal(action)
    orch.ledger.transition(
        action_id=action.id,
        to_state=ActionState.STAGED,
        actor_name="Zilo",
        reason="Synced from your CRM.",
    )


def _record_flag(orch: Orchestrator, summary: str, category: str, crm_ref: str) -> None:
    if _has_crm_ref(orch, crm_ref):
        return
    standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, category)
    action = Action.propose(
        actor_name="Zilo",
        rank_at_time=standing.rank,
        category=category,
        kind=ActionKind.DATA_FLAG,
        summary=summary,
        reasoning="Live CRM snapshot.",
        confidence=0.9,
        payload={"crm_ref": crm_ref},
    )
    orch.ledger.record_proposal(action)
    orch.ledger.transition(
        action_id=action.id,
        to_state=ActionState.SENT,
        actor_name="Zilo",
        reason="Logged from CRM sync.",
    )


async def fetch_metrics(db: Any, uid: str) -> dict[str, Any]:
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    tz_window_start = today_start - timedelta(hours=14)
    tz_window_end = today_end + timedelta(hours=14)

    sales_pipeline = [
        {"$match": {"user_id": uid, "created_at": {"$gte": today_start, "$lt": today_end}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    sales_result = await db.sales.aggregate(sales_pipeline).to_list(1)
    sales_today = float(sales_result[0]["total"]) if sales_result else 0.0

    # "Due" = anything that needs you now or sooner — overdue items (reminder_date
    # in the past) plus everything dated through end-of-today (+ tz buffer).
    # Previously this used `$gte: today_start - 14h`, which silently dropped the
    # 7 overdue follow-ups the user actually saw on the follow-ups page.
    followups_due = await db.followups.count_documents({
        "user_id": uid,
        "status": "pending",
        "is_auto_sequence": {"$ne": True},
        "reminder_date": {"$lt": tz_window_end},
    })

    staged_zilo = 0  # filled by caller from orch

    open_deals = await db.customers.count_documents({
        "user_id": uid,
        "pipeline_stage": {"$exists": True, "$nin": ["", "won", "lost", "closed"]},
    })
    deals_at_risk = await db.customers.count_documents({
        "user_id": uid,
        "pipeline_stage": {"$exists": True, "$nin": ["", "won", "lost", "closed"]},
        "pipeline_updated_at": {"$lt": now - timedelta(days=7)},
    })

    currency = "USD"
    sample = await db.sales.find_one({"user_id": uid}, sort=[("created_at", -1)])
    if sample and sample.get("currency"):
        currency = sample["currency"]

    rev_str = f"{currency} {sales_today:,.0f}" if sales_today >= 1000 else f"{currency} {sales_today:,.2f}"

    return {
        "revenue_today": rev_str,
        "revenue_delta": "—",
        "followups_due": followups_due,
        "followups_zilo": staged_zilo,
        "followups_rex": staged_zilo,
        "open_deals": open_deals,
        "deals_at_risk": deals_at_risk,
        "sales_count_today": sales_result[0]["count"] if sales_result else 0,
    }


async def sync_from_crm(
    db: Any,
    user: dict,
    orch: Orchestrator,
    *,
    force: bool = False,
    skip_heavy_staging: bool = False,
) -> None:
    """Refresh metrics and ingest new staged / overnight items from Mongo."""
    if getattr(orch, "_live_mode", True) is False:
        return

    uid = _business_id(user)
    last = getattr(orch, "_last_sync_at", None)
    now = datetime.utcnow()
    if not force and last and (now - last).total_seconds() < SYNC_MINUTES * 60:
        return

    metrics = await fetch_metrics(db, uid)
    metrics["followups_zilo"] = sum(
        1 for a in orch.ledger.all_actions()
        if orch.ledger.current_state(a.id) is ActionState.STAGED
    )
    metrics["followups_rex"] = metrics["followups_zilo"]
    orch._metrics = metrics  # type: ignore[attr-defined]
    orch._last_sync_at = now  # type: ignore[attr-defined]

    if skip_heavy_staging:
        unread = await db.messages.count_documents({
            "user_id": uid,
            "direction": "incoming",
            "read": {"$ne": True},
        })
        if unread:
            _record_flag(
                orch,
                f"{unread} unread WhatsApp messages in inbox",
                "replies",
                _crm_ref("flag", "unread_wa"),
            )
        scout_n = await db.action_mode_opportunities.count_documents({
            "user_id": uid,
            "created_at": {"$gte": now - timedelta(days=7)},
        })
        if scout_n:
            _record_flag(
                orch,
                f"{scout_n} Scout opportunities in the last 7 days",
                "leads",
                _crm_ref("flag", f"scout_{scout_n}_{now.date().isoformat()}"),
            )
        logger.info("[zilo] CRM metrics-only sync uid=%s staged=%s", uid, metrics["followups_zilo"])
        return

    overdue = await db.invoices.find({
        "user_id": uid,
        "status": {"$in": ["unpaid", "Pending", "overdue", "Overdue"]},
        "created_at": {"$lt": now - timedelta(days=7)},
    }).sort("created_at", 1).to_list(20)

    for inv in overdue:
        inv_id = str(inv["_id"])
        ref = _crm_ref("invoice", inv_id)
        cust = await db.customers.find_one({"_id": inv.get("customer_id")}) if inv.get("customer_id") else None
        name = (cust or {}).get("name") or "Customer"
        amount = inv.get("amount", 0)
        currency = inv.get("currency", "USD")
        num = inv.get("invoice_number") or inv_id[-6:]
        _stage_action(
            orch,
            kind=ActionKind.INVOICE,
            category="invoices",
            summary=f"{name} — invoice #{num} overdue ({currency} {amount:,.0f})",
            reasoning="Outstanding invoice passed your reminder threshold. I can draft a chase message when you approve.",
            confidence=0.88,
            crm_ref=ref,
            target_subject=name.split()[0] if name else None,
            payload={"invoice_id": inv_id, "amount": amount, "currency": currency},
        )
        try:
            existing = orch.notebook.by_subject(name)
            if not any("overdue" in e.text.lower() for e in existing):
                orch.notebook.add(
                    bucket=Bucket.PEOPLE,
                    subject=name,
                    text=f"Invoice #{num} overdue — {currency} {amount:,.0f}.",
                    strict_voice=False,
                    tags=("invoices",),
                )
        except Exception:
            pass

    cold = await db.customers.find({
        "user_id": uid,
        "is_customer": True,
        "$or": [
            {"last_contacted": {"$lt": now - timedelta(days=7)}},
            {"last_contacted": {"$exists": False}},
        ],
    }).sort("last_contacted", 1).to_list(15)

    for cust in cold:
        cid = str(cust["_id"])
        name = cust.get("name") or "Contact"
        ref = _crm_ref("cold", cid)
        _stage_action(
            orch,
            kind=ActionKind.FOLLOW_UP,
            category="outreach",
            summary=f"{name} — no contact in 7+ days",
            reasoning="This customer has gone quiet. A short check-in often reopens the thread.",
            confidence=0.82,
            crm_ref=ref,
            target_subject=name,
            payload={"customer_id": cid},
        )

    pending_fu = await db.followups.find({
        "user_id": uid,
        "status": "pending",
        "is_auto_sequence": {"$ne": True},
        "reminder_date": {"$lte": now + timedelta(days=1)},
    }).sort("reminder_date", 1).to_list(15)

    for fu in pending_fu:
        fid = str(fu["_id"])
        ref = _crm_ref("followup", fid)
        cust = await db.customers.find_one({"_id": fu.get("customer_id")}) if fu.get("customer_id") else None
        name = (cust or {}).get("name") or "Follow-up"
        note = (fu.get("notes") or fu.get("description") or "Reminder due today.")[:120]
        _stage_action(
            orch,
            kind=ActionKind.FOLLOW_UP,
            category="follow_ups",
            summary=f"{name} — follow-up due",
            reasoning=note,
            confidence=0.9,
            crm_ref=ref,
            target_subject=name,
            payload={"followup_id": fid},
        )

    unread = await db.messages.count_documents({
        "user_id": uid,
        "direction": "incoming",
        "read": {"$ne": True},
    })
    if unread:
        _record_flag(
            orch,
            f"{unread} unread WhatsApp messages in inbox",
            "replies",
            _crm_ref("flag", "unread_wa"),
        )

    scout_n = await db.action_mode_opportunities.count_documents({
        "user_id": uid,
        "created_at": {"$gte": now - timedelta(days=7)},
    })
    if scout_n:
        _record_flag(
            orch,
            f"{scout_n} Scout opportunities in the last 7 days",
            "leads",
            _crm_ref("flag", f"scout_{scout_n}_{now.date().isoformat()}"),
        )

    logger.info("[zilo] CRM sync uid=%s staged=%s", uid, metrics["followups_zilo"])

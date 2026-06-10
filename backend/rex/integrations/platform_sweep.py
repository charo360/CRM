"""
Full platform sweep — email, scouts, Action Mode agents, queue import.
"""

from __future__ import annotations

import logging
from typing import Any

from rex.crm.adapters import _business_id
from rex.crm.sync import fetch_metrics, sync_from_crm
from rex.integrations.action_mode_bridge import import_pending_queue, import_scout_opportunities
from rex.integrations.email_bridge import sync_and_draft_inbox
from rex.integrations.messages_bridge import draft_whatsapp_inbox
from rex.integrations.social_bridge import collect_social_drafts
from rex.integrations.sources import connected_sources_snapshot
from rex.loop import Orchestrator

logger = logging.getLogger(__name__)


async def _biz_context(db: Any, uid: str) -> dict[str, Any]:
    """Same rich context Action Mode agents use."""
    biz = await db.users.find_one({"_id": uid}) or {}
    bk = biz.get("business_knowledge") or {}
    settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
    country = (
        bk.get("country")
        or biz.get("country")
        or settings.get("country")
        or ""
    )
    return {
        "business_name": biz.get("business_name", "") or "",
        "business_type": bk.get("business_type", "") or biz.get("business_type", "") or "",
        "country": country,
        "goals": settings.get("goals", "") or "",
        "products_services": bk.get("products_services", "") or "",
        "business_description": bk.get("business_description", "") or "",
    }


async def _run_action_mode_agents(db: Any, uid: str, ctx: dict[str, Any]) -> dict[str, str]:
    """Run enabled Action Mode agents (foreground, capped)."""
    from action_mode_routes import (
        _default_agents,
        _run_admin_autopilot,
        _run_funding_hunter,
        _run_lead_gen,
        _run_social_scout,
    )

    settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
    agents_cfg = settings.get("agents", _default_agents())
    ran: dict[str, str] = {}

    async def _safe(name: str, coro):
        try:
            await coro
            ran[name] = "ok"
        except Exception as e:
            logger.warning("[zilo] agent %s failed uid=%s: %s", name, uid, e)
            ran[name] = str(e)[:120]

    tasks = []
    if agents_cfg.get("admin_autopilot", True):
        tasks.append(("admin_autopilot", _run_admin_autopilot(db, uid, ctx)))
    if agents_cfg.get("funding_hunter", False):
        tasks.append(("funding_hunter", _run_funding_hunter(db, uid, ctx)))
    if agents_cfg.get("lead_gen", False):
        tasks.append(("lead_gen", _run_lead_gen(db, uid, ctx)))
    if agents_cfg.get("social_scout", True):
        tasks.append(("social_scout", _run_social_scout(db, uid, ctx)))

    for name, coro in tasks:
        await _safe(name, coro)

    return ran


async def _run_due_scouts(db: Any, uid: str, *, max_scouts: int = 2) -> list[dict[str, Any]]:
    from scout_service import ensure_default_scouts, execute_scout, find_due_scouts, get_biz_context

    ctx = await get_biz_context(db, uid)
    await ensure_default_scouts(db, uid, ctx)
    due_all = await find_due_scouts(db, limit=20)
    scouts = [s for s in due_all if s.get("user_id") == uid][:max_scouts]

    results = []
    for scout in scouts:
        try:
            r = await execute_scout(db, scout, ctx)
            results.append(r)
        except Exception as e:
            logger.warning("[zilo] scout run failed %s: %s", scout.get("_id"), e)
    return results


async def run_platform_sweep(
    db: Any,
    user: dict,
    orch: Orchestrator,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    End-to-end Rex-style sweep:
      email pull → reply drafts → scouts → Action Mode agents → import queue → metrics
    """
    uid = _business_id(user)
    ctx = await _biz_context(db, uid)
    biz_name = ctx.get("business_name", "us")

    report: dict[str, Any] = {"user_id": uid}
    report["sources"] = await connected_sources_snapshot(db, uid)

    # 1) Email sync + draft queue
    try:
        report["email"] = await sync_and_draft_inbox(
            db, uid, biz_name=biz_name,
        )
    except Exception as e:
        logger.warning("[zilo] email bridge: %s", e)
        report["email"] = {"error": str(e)}

    # 1b) WhatsApp message drafts (review → approve to send)
    try:
        report["whatsapp"] = await draft_whatsapp_inbox(db, uid, biz_name=biz_name)
    except Exception as e:
        logger.warning("[zilo] whatsapp bridge: %s", e)
        report["whatsapp"] = {"error": str(e)}

    # 1c) Social inbox / groups (when configured)
    if force:
        try:
            report["social"] = await collect_social_drafts(db, uid, ctx)
        except Exception as e:
            report["social"] = {"error": str(e)}

    # 2) Scouts (find leads → opportunities + queue via scout_service)
    try:
        report["scouts"] = await _run_due_scouts(db, uid, max_scouts=2)
    except Exception as e:
        logger.warning("[zilo] scouts: %s", e)
        report["scouts"] = {"error": str(e)}

    # 3) Legacy Action Mode agents (WhatsApp reminders, funding, social)
    if force:
        try:
            report["agents"] = await _run_action_mode_agents(db, uid, ctx)
        except Exception as e:
            report["agents"] = {"error": str(e)}
    else:
        # Light path: admin only on routine sync
        try:
            from action_mode_routes import _run_admin_autopilot
            await _run_admin_autopilot(db, uid, ctx)
            report["agents"] = {"admin_autopilot": "ok"}
        except Exception as e:
            report["agents"] = {"error": str(e)}

    # 4) Import Action Mode queue + orphan opportunities into Zilo briefing
    report["queue_imported"] = await import_pending_queue(db, uid, orch, limit=30)
    report["opps_imported"] = await import_scout_opportunities(db, uid, orch)

    # 5) CRM metrics + light flags (no duplicate invoice staging)
    await sync_from_crm(db, user, orch, force=force, skip_heavy_staging=True)

    metrics = await fetch_metrics(db, uid)
    metrics["followups_zilo"] = sum(
        1 for a in orch.ledger.all_actions()
        if orch.ledger.current_state(a.id).value == "staged"
    )
    metrics["followups_rex"] = metrics["followups_zilo"]
    orch._metrics = metrics  # type: ignore[attr-defined]

    report["staged"] = metrics["followups_zilo"]

    # 6) Innovation 4 — Relationship Health Scoring (background loop)
    try:
        health_report = await _score_relationship_health(db, uid, orch)
        report["relationship_health"] = health_report
    except Exception as e:
        logger.warning("[zilo] relationship health scoring failed uid=%s: %s", uid, e)
        report["relationship_health"] = {"error": str(e)}

    # 7) Sync all historical trust events into the Notebook (idempotent — skips already-synced)
    try:
        from rex.memory.notebook_sync import sync_events_to_notebook as _sync_nb
        synced_count = _sync_nb(
            events=orch.event_store.all_events(),
            ledger=orch.ledger,
            notebook=orch.notebook,
        )
        if synced_count:
            logger.info("[zilo] notebook synced %d new events", synced_count)
    except Exception as e:
        logger.warning("[zilo] notebook sync failed: %s", e)

    # 8) Emit a BACKGROUND_WORK trust event so the journal has honest daily content.
    # Only emit if real work happened — don't record empty sweeps.
    try:
        from rex.ranks.events import TrustEvent as _TrustEvent
        _drafts_staged = int(report.get("staged") or 0)
        _email_report = report.get("email") or {}
        _emails_swept = int(_email_report.get("fetched") or _email_report.get("total") or 0)
        _leads_found = int((report.get("opps_imported") or 0))
        _actions_sent = sum(
            1 for a in orch.ledger.all_actions()
            if orch.ledger.current_state(a.id).value == "sent"
        )
        if _drafts_staged or _emails_swept or _leads_found or _actions_sent:
            _bg_event = _TrustEvent.background_work(
                drafts_staged=_drafts_staged,
                emails_swept=_emails_swept,
                leads_found=_leads_found,
                actions_sent=_actions_sent,
            )
            orch.event_store.append(_bg_event)
            report["background_work_event"] = "emitted"
    except Exception as e:
        logger.warning("[zilo] background_work event emit failed: %s", e)

    return report


async def _score_relationship_health(
    db: Any,
    uid: str,
    orch: Any,
) -> dict[str, Any]:
    """
    Proactive relationship health scan — runs after every platform sweep.

    Writes observations to the Rex Notebook only when a new at-risk signal
    is detected that isn't already captured (subject-deduped).

    Signals detected:
      1. Customers overdue for contact (no interaction > 30 days, ever purchased)
      2. Customers with open overdue invoices (not yet in a notebook PEOPLE entry)
      3. Broad pattern: if >20% of active customers are cold, log a PATTERNS entry
    """
    from datetime import timedelta
    from rex.memory.buckets import Bucket
    from rex.memory.notebook import NotebookVoiceError

    now_dt = __import__("datetime").datetime.utcnow()
    cutoff_cold = now_dt - timedelta(days=30)
    cutoff_very_cold = now_dt - timedelta(days=60)

    scored: dict[str, Any] = {
        "cold_customers": 0,
        "overdue_invoice_alerts": 0,
        "notebook_writes": 0,
    }

    # Helper: check if notebook already has a PEOPLE entry for this subject
    def _already_noted(subject: str) -> bool:
        existing = orch.notebook.by_subject(subject)
        return len(existing) > 0

    # ── Signal 1: Cold customers (purchased, no recent contact) ─────────────
    try:
        cold_cursor = db.customers.find({
            "user_id": uid,
            "is_customer": True,
            "last_interaction": {"$lt": cutoff_cold, "$exists": True},
        }, {"_id": 1, "name": 1, "last_interaction": 1, "total_orders": 1}).sort(
            "last_interaction", 1
        ).limit(10)
        cold_customers = await cold_cursor.to_list(10)
        scored["cold_customers"] = len(cold_customers)

        for cust in cold_customers:
            name = (cust.get("name") or "").strip()
            if not name or _already_noted(name):
                continue
            last_ts = cust.get("last_interaction")
            days_cold = (now_dt - last_ts).days if last_ts else "unknown"
            orders = cust.get("total_orders") or 0
            obs = (
                f"{name} — no contact in {days_cold} days. "
                f"Previously placed {orders} order{'s' if orders != 1 else ''}. "
                "Re-engagement window narrowing."
            )
            try:
                orch.notebook.add(
                    bucket=Bucket.PEOPLE,
                    subject=name,
                    text=obs,
                    tags=("relationship_health", "cold"),
                    strict_voice=True,
                )
                scored["notebook_writes"] += 1
            except NotebookVoiceError:
                # Fallback: simpler text if voice check fails
                try:
                    orch.notebook.add(
                        bucket=Bucket.PEOPLE,
                        subject=name,
                        text=f"{name} — inactive for {days_cold} days. Relationship at risk.",
                        tags=("relationship_health", "cold"),
                        strict_voice=True,
                    )
                    scored["notebook_writes"] += 1
                except Exception:
                    pass
    except Exception as e:
        logger.warning("[relationship_health] cold scan failed: %s", e)

    # ── Signal 2: Overdue invoice customers ─────────────────────────────────
    try:
        overdue_cursor = db.invoices.find({
            "user_id": uid,
            "status": {"$in": ["overdue", "open"]},
            "due_date": {"$lt": now_dt, "$exists": True},
        }, {"_id": 1, "customer_id": 1, "amount": 1, "due_date": 1}).limit(10)
        overdue_invs = await overdue_cursor.to_list(10)
        scored["overdue_invoice_alerts"] = len(overdue_invs)

        for inv in overdue_invs:
            cid = inv.get("customer_id")
            if not cid:
                continue
            cust_doc = await db.customers.find_one({"_id": cid}, {"name": 1})
            if not cust_doc:
                continue
            name = (cust_doc.get("name") or "").strip()
            if not name:
                continue
            existing = orch.notebook.by_subject(name)
            # Only write if no existing overdue tag
            already_has_overdue = any(
                "overdue" in e.tags for e in existing
            )
            if already_has_overdue:
                continue
            amount = inv.get("amount") or 0
            try:
                orch.notebook.add(
                    bucket=Bucket.PEOPLE,
                    subject=name,
                    text=(
                        f"{name} — outstanding overdue invoice of {amount}. "
                        "Payment conversation not yet resolved."
                    ),
                    tags=("relationship_health", "overdue"),
                    strict_voice=True,
                )
                scored["notebook_writes"] += 1
            except NotebookVoiceError:
                pass
    except Exception as e:
        logger.warning("[relationship_health] overdue invoice scan failed: %s", e)

    # ── Signal 3: Broad pattern — if majority of active customers are cold ───
    try:
        total_customers = await db.customers.count_documents(
            {"user_id": uid, "is_customer": True}
        )
        very_cold_count = await db.customers.count_documents({
            "user_id": uid,
            "is_customer": True,
            "last_interaction": {"$lt": cutoff_very_cold, "$exists": True},
        })
        if total_customers > 0 and very_cold_count / total_customers > 0.2:
            # Log a PATTERNS entry if not already there
            existing_pattern = orch.notebook.by_subject("engagement")
            if not existing_pattern:
                pct = round((very_cold_count / total_customers) * 100)
                try:
                    orch.notebook.add(
                        bucket=Bucket.PATTERNS,
                        text=(
                            f"{pct}% of the customer base has had no contact in over 60 days. "
                            "Broad re-engagement needed — not an isolated case."
                        ),
                        tags=("relationship_health", "engagement"),
                        strict_voice=True,
                    )
                    scored["notebook_writes"] += 1
                except NotebookVoiceError:
                    pass
    except Exception as e:
        logger.warning("[relationship_health] pattern scan failed: %s", e)

    return scored


"""
Zilo Chief-of-Staff HTTP routes (API prefix /api/rex/* — rename to /api/zilo later).

Persists ledger, trust events, and notebook in Mongo when `db` is provided.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from rex.api_serializers import serialize_journal, serialize_ledger, serialize_notebook
from rex.crm.adapters import make_live_scanner
from rex.crm.sync import sync_from_crm
from rex.actions.stub_executor import ensure_stub_executor
from rex.demo_seed import build_demo_orchestrator, serialize_home
from rex.integrations.action_mode_bridge import wire_action_mode_executor
from rex.integrations.briefing_refresh import light_briefing_refresh
from rex.integrations.platform_sweep import run_platform_sweep
from rex.team_api import serialize_team
from rex.loop import Orchestrator
from rex.onboarding import (
    OnboardingEngine,
    OnboardingState,
    CommunicationChannel,
    DirectnessLevel,
    HonestDemoScanner,
)
from rex.persistence.session import OptimisticLockError, ZiloSessionStore
from rex.decisions.models import (
    DecideRequest,
    MessageRequest,
    NoteFeedbackRequest,
    NoteRequest,
    ScheduleRequest,
    SparRequest,
    serialize_session,
)
from rex.decisions.persistence import (
    append_founder_update,
    append_thread_messages,
    archive_session,
    count_open,
    create_session,
    ensure_indexes as ensure_decision_indexes,
    get_session,
    list_sessions,
    patch_founder_update,
    patch_thread_message,
    record_decision,
    seed_thread_if_empty,
    update_outcome_schedule,
    update_spar,
)
from rex.decisions.spar import (
    MAX_UPDATE_REGENERATIONS,
    analyze_rejected_response,
    react_to_update,
    regenerate_thread_assistant,
    run_conversation_turn,
    run_spar,
    spar_opening_message,
)
from rex.decisions.journal import (
    add_decision_notebook_pattern,
    fetch_decision_journal_entries,
    persist_decision_journal,
)
from rex.decisions.bridge import (
    ack_outcome_briefing,
    dismiss_decision_briefing_actions,
    sync_open_decisions_to_briefing,
)
from rex.decisions.context import gather_decision_context
from rex.decisions.outcomes import (
    baseline_from_context,
    init_outcome_tracking,
    normalize_review_days,
    process_due_outcomes,
    rebuild_checkpoints_for_schedule,
)

logger = logging.getLogger(__name__)

_decision_indexes_ready = False


def _uid(user: dict) -> str:
    return str(user.get("_id") or user.get("id") or "anonymous")


def _business_id(user: dict) -> str:
    return str(user.get("business_id") or user.get("_id") or "anonymous")


async def _persist_edited_draft(
    db: Any,
    orch: Orchestrator,
    action_id: str,
    draft_body: str,
    uid: str,
) -> None:
    """Save user-edited draft on the Action Mode queue item before send."""
    action = orch.ledger.get(action_id)
    if not action or not draft_body:
        return
    qid = (action.payload or {}).get("queue_id")
    if not qid:
        return
    await db.action_mode_queue.update_one(
        {"_id": qid, "user_id": uid},
        {"$set": {"draft_content": draft_body, "user_edited": True}},
    )


# ── In-memory fallback (no db) ────────────────────────────────────────────

_ENGINES: dict[str, OnboardingEngine] = {}
_ORCHESTRATORS: dict[str, Orchestrator] = {}
_SESSION: ZiloSessionStore | None = None


def _use_live_db(db: Any | None) -> bool:
    if db is None:
        return False
    if os.environ.get("ZILO_DEMO_ONLY", "").lower() in ("1", "true", "yes"):
        return False
    return True


def _get_engine(user: dict, db: Any | None = None) -> OnboardingEngine:
    user_id = _uid(user)
    engine = _ENGINES.get(user_id)
    if engine is None:
        scanner = make_live_scanner(db, user) if _use_live_db(db) else HonestDemoScanner()
        engine = OnboardingEngine(scanner=scanner)
        _ENGINES[user_id] = engine
    return engine


def _reset_engine(user: dict, db: Any | None = None) -> OnboardingEngine:
    user_id = _uid(user)
    scanner = make_live_scanner(db, user) if _use_live_db(db) else HonestDemoScanner()
    engine = OnboardingEngine(scanner=scanner)
    _ENGINES[user_id] = engine
    return engine


async def _get_orchestrator(
    user: dict,
    db: Any | None,
    *,
    light: bool = True,
    refresh: bool = True,
) -> Orchestrator:
    """Load persisted state.

    refresh=False  → just load persisted orch, no CRM/email ingest. Use for
                     read-only memory surfaces (journal, notebook, ledger).
    light=True    → load + run light briefing refresh (email, queue, metrics).
    light=False   → load + run full platform sweep (scouts, agents).
    """
    uid = _uid(user)
    bid = _business_id(user)

    if not _use_live_db(db):
        orch = _ORCHESTRATORS.get(uid)
        if orch is None:
            orch = build_demo_orchestrator()
            _ORCHESTRATORS[uid] = orch
        return orch

    global _SESSION
    if _SESSION is None:
        _SESSION = ZiloSessionStore(db)
        await _SESSION.ensure_indexes()
    store = _SESSION
    orch = await store.load(uid, business_id=bid)
    wire_action_mode_executor(orch, db, uid)

    if not refresh:
        return orch

    if light:
        await light_briefing_refresh(db, user, orch)
        await store.save(uid, business_id=bid, orch=orch)
        return orch

    # Rate-limit forced sweeps: max 3 per 5 minutes per user (they are expensive)
    from rate_limiter import check_sweep_cooldown
    await check_sweep_cooldown(uid)

    await run_platform_sweep(db, user, orch, force=True)
    await store.save(uid, business_id=bid, orch=orch)
    return orch


async def _persist(user: dict, db: Any | None, orch: Orchestrator) -> None:
    if not _use_live_db(db):
        _ORCHESTRATORS[_uid(user)] = orch
        return
    if _SESSION:
        await _SESSION.save(_uid(user), business_id=_business_id(user), orch=orch)


async def _persist_orch_with_retry(
    user: dict,
    db: Any | None,
    *,
    mutate,
    attempts: int = 4,
) -> bool:
    """Apply ``mutate(orch)`` then persist, retrying on optimistic-lock collisions.

    The background briefing refresh writes the same session doc, so a concurrent
    save can lose the optimistic-lock race. We reload a fresh orchestrator and
    re-apply the mutation each attempt. Best-effort: if every attempt collides we
    log and give up — the caller's primary write (decision/spar) already landed.
    Returns True if persisted, False if it gave up.
    """
    async def _run_mutate(orch: Orchestrator) -> None:
        result = mutate(orch)
        if asyncio.iscoroutine(result):
            await result

    if not _use_live_db(db):
        orch = await _get_orchestrator(user, db, refresh=False)
        await _run_mutate(orch)
        await _persist(user, db, orch)
        return True

    uid = _uid(user)
    for attempt in range(attempts):
        try:
            if _SESSION is not None and attempt > 0:
                _SESSION.invalidate_cache(uid)
            orch = await _get_orchestrator(user, db, refresh=False)
            await _run_mutate(orch)
            await _persist(user, db, orch)
            return True
        except OptimisticLockError:
            if attempt == attempts - 1:
                logger.warning(
                    "[zilo] persist retry exhausted for uid=%s — concurrent writer won", uid
                )
                return False
            await asyncio.sleep(0.15 * (attempt + 1))
        except Exception as e:
            logger.warning("[zilo] persist with retry failed for uid=%s: %s", uid, e)
            return False
    return False


_BG_REFRESH_INFLIGHT: set[str] = set()


async def _background_briefing_refresh(user: dict, db: Any, uid: str, bid: str) -> None:
    """Fire-and-forget light refresh for the SWR /home path.

    Loads a fresh orch (the request's orch is already returned to the client),
    runs the light refresh, persists. Deduped per-user so rapid reloads don't
    stack refreshes on top of each other.
    """
    if uid in _BG_REFRESH_INFLIGHT:
        return
    _BG_REFRESH_INFLIGHT.add(uid)
    try:
        global _SESSION
        if _SESSION is None:
            _SESSION = ZiloSessionStore(db)
            await _SESSION.ensure_indexes()
        store = _SESSION
        orch = await store.load(uid, business_id=bid)
        wire_action_mode_executor(orch, db, uid)
        await light_briefing_refresh(db, user, orch)
        await store.save(uid, business_id=bid, orch=orch)
        logger.info("[zilo] background briefing refresh complete uid=%s", uid)
    except Exception as e:
        logger.warning("[zilo] background briefing refresh failed uid=%s: %s", uid, e)
    finally:
        _BG_REFRESH_INFLIGHT.discard(uid)


# ── Request/response models ───────────────────────────────────────────────

class StartResponse(BaseModel):
    welcome: str
    state: str
    question: Optional[str] = None


class AnswerRequest(BaseModel):
    value: str


class AnswerResponse(BaseModel):
    next_prompt: str
    state: str
    question: Optional[str] = None
    i_see_it: Optional[str] = None
    complete: bool = False


class StateResponse(BaseModel):
    state: str
    question: Optional[str] = None
    complete: bool


class PreferencesResponse(BaseModel):
    preferences: dict


class ActionVerbRequest(BaseModel):
    reason: Optional[str] = None
    draft_body: Optional[str] = None


class HomeResetRequest(BaseModel):
    demo: bool = False


class BriefingPreferencesRequest(BaseModel):
    enabled_categories: list[str]
    lead_scout_interval: Optional[str] = "24h"
    open_scout_interval: Optional[str] = "12h"
    fb_group_interval: Optional[str] = "6h"


class RankChangeRequest(BaseModel):
    category: str
    reason: Optional[str] = None
    to_rank: Optional[str] = None  # display name like "Sender"; defaults to one step up/down


class EditNotebookEntryRequest(BaseModel):
    text: str


class EditCompanyRequest(BaseModel):
    description: str



# ── Router factory ────────────────────────────────────────────────────────

def init_rex_routes(get_current_user, db: Any | None = None) -> APIRouter:
    """Build the Rex router with the host app's auth dependency."""
    router = APIRouter(prefix="/rex", tags=["rex"])

    from rex.workplan.routes import init_workplan_routes
    router.include_router(init_workplan_routes(get_current_user, db))

    async def _session_store() -> ZiloSessionStore:
        global _SESSION
        if _SESSION is None and _use_live_db(db):
            _SESSION = ZiloSessionStore(db)
            await _SESSION.ensure_indexes()
        if _SESSION is None:
            raise HTTPException(status_code=501, detail="Database not configured")
        return _SESSION

    # ── Zilo Briefing (live CRM feed) ────────────────────────────────────

    @router.get("/home")
    async def rex_home(
        user=Depends(get_current_user),
        refresh: bool = Query(False, description="Full platform sweep (slow, blocks)"),
        live: bool = Query(False, description="Block on light refresh before returning"),
        background: bool = Query(True, description="Kicks light refresh in background"),
    ):
        """Stale-while-revalidate by default.

        Returns the persisted briefing instantly and kicks the light refresh in
        the background — the next page load sees fresh data. Set ?live=true to
        block on the refresh (e.g. user-clicked "refresh now"), or ?refresh=true
        for a full platform sweep.
        """
        try:
            if refresh and _use_live_db(db):
                orch = await _get_orchestrator(user, db, light=False)
            elif live and _use_live_db(db):
                orch = await _get_orchestrator(user, db, light=True)
            else:
                orch = await _get_orchestrator(user, db, refresh=False)
                if background and _use_live_db(db):
                    asyncio.create_task(
                        _background_briefing_refresh(user, db, _uid(user), _business_id(user))
                    )
            return serialize_home(orch)
        except Exception as e:
            logger.exception("[zilo] /home failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e)[:500])

    @router.post("/home/reset")
    async def rex_home_reset(body: HomeResetRequest, user=Depends(get_current_user)):
        uid = _uid(user)
        bid = _business_id(user)
        if _use_live_db(db):
            store = await _session_store()
            orch = await store.reset(uid, business_id=bid, demo=body.demo)
            if not body.demo:
                wire_action_mode_executor(orch, db, uid)
                # Rate-limit: max 3 forced sweeps per 5 min; propagate 429 to caller
                try:
                    from rate_limiter import check_sweep_cooldown
                    await check_sweep_cooldown(uid)
                except HTTPException:
                    raise
                except Exception as _rl_exc:
                    logger.warning("[rex] home/reset sweep rate-limit check failed: %s", _rl_exc)
                await run_platform_sweep(db, user, orch, force=True)
                await store.save(uid, business_id=bid, orch=orch)
            return {"ok": True, "demo": body.demo}
        if body.demo:
            _ORCHESTRATORS[uid] = build_demo_orchestrator()
        else:
            o = Orchestrator()
            ensure_stub_executor(o)
            _ORCHESTRATORS[uid] = o
        return {"ok": True, "demo": body.demo}

    @router.post("/actions/{action_id}/approve")
    async def rex_approve(action_id: str, body: ActionVerbRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        if body.draft_body and db is not None:
            await _persist_edited_draft(db, orch, action_id, body.draft_body.strip(), _uid(user))
        try:
            result = orch.approve(action_id, reason=body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)

        # Briefing integration hook: if user approves outreach or replies, auto-create a Zilo monitoring task
        try:
            action = orch.ledger.get(action_id)
            if action and action.category in ("outreach", "replies"):
                import uuid as _uuid
                target_subj = action.target_subject or "contact"
                now = datetime.utcnow()
                due_dt = now + timedelta(days=3)
                task_id = str(_uuid.uuid4())
                task_doc = {
                    "title": f"Watch for {target_subj} reply. Flag if no response in 3 days.",
                    "owner": "zilo",
                    "due_date": due_dt.isoformat(),
                    "source": f"Briefing action {now.strftime('%b %d')}",
                    "status": "pending",
                    "zilo_status": "scheduled",
                    "context": f"Auto-created from approved briefing action: {action.summary}",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat()
                }
                if _use_live_db(db):
                    task_doc["_id"] = task_id
                    task_doc["user_id"] = _uid(user)
                    await db.workplan_tasks.insert_one(task_doc)
                else:
                    uid = _uid(user)
                    if uid not in _IN_MEMORY_TASKS:
                        from rex.workplan.routes import get_demo_tasks
                        _IN_MEMORY_TASKS[uid] = get_demo_tasks()
                    task_doc["id"] = task_id
                    _IN_MEMORY_TASKS[uid].append(task_doc)
        except Exception as _hook_err:
            logger.warning("[workplan-hook] Failed to auto-create tracking task: %s", _hook_err)

        return {
            "ok": True,
            "action_id": result.action_id,
            "final_state": result.final_state.value,
            "home": serialize_home(orch),
        }

    @router.post("/actions/{action_id}/dismiss")
    async def rex_dismiss(action_id: str, body: ActionVerbRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        action = orch.ledger.get(action_id)
        try:
            orch.dismiss(action_id, reason=body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        if action and _use_live_db(db):
            payload = action.payload or {}
            if payload.get("action_mode_type") == "decision_outcome":
                sid = payload.get("decision_session_id")
                day = payload.get("outcome_day")
                if sid and day is not None:
                    await ack_outcome_briefing(db, _uid(user), str(sid), int(day))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.post("/actions/{action_id}/reject")
    async def rex_reject(action_id: str, body: ActionVerbRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            orch.reject(action_id, reason=body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.post("/actions/{action_id}/undo")
    async def rex_undo(action_id: str, body: ActionVerbRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            orch.undo(action_id, reason=body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.post("/actions/{action_id}/like")
    async def rex_like(action_id: str, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            action = orch.ledger.get(action_id)
            if not action:
                raise HTTPException(status_code=404, detail="Action not found")
            from dataclasses import replace
            payload = dict(action.payload or {})
            payload["feedback"] = "like"
            new_action = replace(action, payload=payload)
            orch.ledger._store._actions[action_id] = new_action
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.post("/actions/{action_id}/dislike")
    async def rex_dislike(action_id: str, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            action = orch.ledger.get(action_id)
            if not action:
                raise HTTPException(status_code=404, detail="Action not found")
            from dataclasses import replace
            payload = dict(action.payload or {})
            payload["feedback"] = "dislike"
            new_action = replace(action, payload=payload)
            orch.ledger._store._actions[action_id] = new_action
            orch.dismiss(action_id, reason="User disliked this item.")
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))
        await _persist(user, db, orch)
        return {"ok": True, "home": serialize_home(orch)}

    @router.get("/briefing/preferences")
    async def get_briefing_preferences(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        disabled = getattr(orch, "_disabled_categories", set())
        
        from rex.ranks.categories import all_categories
        categories_data = []
        for cat in all_categories():
            categories_data.append({
                "name": cat.name,
                "display": cat.display,
                "tier": cat.tier.value,
                "enabled": cat.name not in disabled
            })
        return {
            "categories": categories_data,
            "lead_scout_interval": getattr(orch, "_lead_scout_interval", "24h"),
            "open_scout_interval": getattr(orch, "_open_scout_interval", "12h"),
            "fb_group_interval": getattr(orch, "_fb_group_interval", "6h"),
        }

    @router.post("/briefing/preferences")
    async def save_briefing_preferences(body: BriefingPreferencesRequest, user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        uid = _uid(user)
        
        from rex.ranks.categories import all_categories
        all_names = {cat.name for cat in all_categories()}
        enabled_names = set(body.enabled_categories)
        disabled_names = all_names - enabled_names
        
        orch._disabled_categories = disabled_names
        orch._lead_scout_interval = body.lead_scout_interval or "24h"
        orch._open_scout_interval = body.open_scout_interval or "12h"
        orch._fb_group_interval = body.fb_group_interval or "6h"
        
        await _persist(user, db, orch)
        
        # Propagate custom intervals to the user's active database scouts
        try:
            from datetime import datetime, timedelta
            
            # 1. Update Lead Scouts (Lead Finder)
            delta_map = {
                "1h": timedelta(hours=1),
                "2h": timedelta(hours=2),
                "6h": timedelta(hours=6),
                "12h": timedelta(hours=12),
                "24h": timedelta(hours=24),
                "daily": timedelta(hours=24),
                "weekly": timedelta(days=7),
            }
            lead_delta = delta_map.get(body.lead_scout_interval)
            if lead_delta:
                await db["lead_scouts"].update_many(
                    {"user_id": uid, "enabled": True},
                    {"$set": {
                        "frequency": body.lead_scout_interval,
                        "next_run": datetime.utcnow() + lead_delta
                    }}
                )
            else:
                await db["lead_scouts"].update_many(
                    {"user_id": uid, "enabled": True},
                    {"$set": {
                        "frequency": "manual"
                    }, "$unset": {"next_run": ""}}
                )
                
            # 2. Update Open Scouts (Zilo Scouts / Web Finder)
            freq_hours_map = {
                "1h": 1,
                "2h": 2,
                "6h": 6,
                "12h": 12,
                "24h": 24,
                "daily": 24,
                "weekly": 168,
            }
            open_hours = freq_hours_map.get(body.open_scout_interval, 12)
            await db["zilo_scouts"].update_many(
                {"user_id": uid, "is_active": True},
                {"$set": {
                    "frequency": body.open_scout_interval,
                    "frequency_hours": open_hours,
                    "next_run_at": datetime.utcnow() + timedelta(hours=open_hours)
                }}
            )
            
            logger.info("[preferences] propagated scheduling changes to active scouts for user=%s", uid)
        except Exception as e:
            logger.error("[preferences] failed to propagate scheduling changes to scouts: %s", e)
            
        return {"ok": True, "home": serialize_home(orch)}

    # ── Memory surfaces (persisted) ─────────────────────────────────────

    @router.get("/notebook")
    async def rex_notebook(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        return serialize_notebook(orch)

    @router.post("/notebook/{entry_id}")
    async def edit_notebook_entry(
        entry_id: str,
        body: EditNotebookEntryRequest,
        user=Depends(get_current_user),
    ):
        orch = await _get_orchestrator(user, db, refresh=False)
        try:
            orch.notebook.update_text(entry_id, body.text, by_user=True)
        except KeyError:
            raise HTTPException(status_code=404, detail="Notebook entry not found")
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.delete("/notebook/{entry_id}")
    async def delete_notebook_entry(
        entry_id: str,
        user=Depends(get_current_user),
    ):
        orch = await _get_orchestrator(user, db, refresh=False)
        deleted = orch.notebook.delete(entry_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Notebook entry not found")
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.post("/companies/{company_id}")
    async def edit_company(
        company_id: str,
        body: EditCompanyRequest,
        user=Depends(get_current_user),
    ):
        orch = await _get_orchestrator(user, db, refresh=False)
        companies = getattr(orch, "_companies", [])
        found = False
        for c in companies:
            if c.get("id") == company_id:
                c["description"] = body.description
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Company not found")
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.delete("/companies/{company_id}")
    async def delete_company(
        company_id: str,
        user=Depends(get_current_user),
    ):
        orch = await _get_orchestrator(user, db, refresh=False)
        companies = getattr(orch, "_companies", [])
        filtered = [c for c in companies if c.get("id") != company_id]
        if len(filtered) == len(companies):
            raise HTTPException(status_code=404, detail="Company not found")
        orch._companies = filtered
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}


    @router.post("/notebook/clear")
    async def clear_notebook(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        for entry in list(orch.notebook.all()):
            orch.notebook.delete(entry.id)
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.post("/notebook/refresh")
    async def refresh_notebook(user=Depends(get_current_user)):
        uid = _uid(user)
        bid = _business_id(user)
        # Bust the in-memory cache so load() hits MongoDB fresh
        if _SESSION is not None:
            _SESSION._cache.pop(uid, None)
        orch = await _get_orchestrator(user, db, refresh=False)
        # Clear stale auto-generated entries; keep anything the user has edited
        for entry in list(orch.notebook.all()):
            if not entry.edited_by_user:
                orch.notebook.delete(entry.id)
        if hasattr(orch, "_companies"):
            orch._companies = []
        from rex.persistence.extractor import extract_and_populate_notebook
        try:
            await extract_and_populate_notebook(db, uid, orch)
        except Exception as e:
            logger.exception("[zilo-session] failed during manual refresh: %s", e)
        await _persist(user, db, orch)
        return {"ok": True, "notebook": serialize_notebook(orch)}

    @router.post("/bootstrap")
    async def rex_bootstrap(user=Depends(get_current_user)):
        """
        Full account bootstrap: sync emails from Composio then rebuild notebook.
        Call this once after connecting Gmail/Outlook on any account.
        Returns immediately; all heavy work runs in background.
        """
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Requires live database")
        uid = _uid(user)
        from server import _bootstrap_new_account
        import asyncio
        asyncio.create_task(_bootstrap_new_account(uid, db))
        return {"ok": True, "status": "bootstrapping in background — notebook will update within 60s"}

    @router.get("/notebook/export")
    async def export_notebook(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        data = serialize_notebook(orch)
        import json
        from fastapi import Response
        content = json.dumps(data, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=zilo_notebook_export.json"
            }
        )

    @router.get("/ledger")
    async def rex_ledger(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        return serialize_ledger(orch)

    @router.get("/journal")
    async def rex_journal(user=Depends(get_current_user)):
        orch = await _get_orchestrator(user, db, refresh=False)
        day = getattr(orch, "_relationship_day", 1)
        extra_entries = []
        if _use_live_db(db):
            extra_entries = await fetch_decision_journal_entries(
                db, _uid(user), relationship_day=day
            )
        payload = await serialize_journal(orch, extra_entries=extra_entries)
        try:
            await _persist(user, db, orch)
        except OptimisticLockError:
            # Visit-streak save lost the race against a background refresh —
            # the journal read itself is still valid, don't 500 it.
            logger.warning("[zilo] journal visit-state persist lost lock race")
        return payload

    @router.post("/journal/clear-day-override")
    async def rex_journal_clear_day_override(user=Depends(get_current_user)):
        """One-time fix: remove any relationship_day_override so the day is
        computed naturally from created_at. Safe to call repeatedly."""
        uid = _uid(user)
        if _use_live_db(db):
            store = await _session_store()
            await db[store._col.name].update_one(
                {"user_id": uid},
                {"$unset": {"relationship_day_override": ""}},
            )
            store.invalidate_cache(uid)
        return {"ok": True}

    @router.get("/standings")
    async def rex_standings(user=Depends(get_current_user)):
        """Per-category trust ladder for Zilo (Chief of Staff)."""
        from rex.identity import CHIEF_OF_STAFF_NAME
        from rex.ranks.categories import all_categories
        from rex.ranks.events import Rank

        orch = await _get_orchestrator(user, db, refresh=False)
        rows = []
        for cat in all_categories():
            s = orch.engine.standing(CHIEF_OF_STAFF_NAME, cat.name)
            rows.append({
                "category": cat.name,
                "display": cat.display,
                "tier": int(cat.tier),
                "rank": s.rank.display,
                "rank_value": int(s.rank),
                "on_probation": s.on_probation,
            })
        return {
            "standings": rows,
            "ranks": [r.display for r in Rank],
            "max_rank_value": int(Rank.CHIEF_OF_STAFF),
        }

    async def _apply_rank_change(
        user: dict,
        body: RankChangeRequest,
        *,
        direction: str,
    ) -> dict:
        from rex.identity import CHIEF_OF_STAFF_NAME
        from rex.ranks.categories import is_category
        from rex.ranks.engine import RankEngine
        from rex.ranks.events import Rank, TrustEvent

        if not is_category(body.category):
            raise HTTPException(status_code=400, detail=f"Unknown category: {body.category}")

        orch = await _get_orchestrator(user, db, refresh=False)
        standing = orch.engine.standing(CHIEF_OF_STAFF_NAME, body.category)
        from_rank = standing.rank

        if body.to_rank:
            try:
                to_rank = Rank.from_display(body.to_rank)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Unknown rank: {body.to_rank}")
        else:
            step = 1 if direction == "promote" else -1
            new_value = int(from_rank) + step
            if new_value < int(Rank.OBSERVER) or new_value > int(Rank.CHIEF_OF_STAFF):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Already at Chief of Staff." if direction == "promote"
                        else "Already at Observer."
                    ),
                )
            to_rank = Rank(new_value)

        if direction == "promote" and int(to_rank) <= int(from_rank):
            raise HTTPException(status_code=409, detail="Target rank is not a promotion.")
        if direction == "demote" and int(to_rank) >= int(from_rank):
            raise HTTPException(status_code=409, detail="Target rank is not a demotion.")

        # Strategy category never auto-executes — cap at Drafter (Decision Room).
        if body.category == "strategy" and direction == "promote":
            from rex.ranks.events import Rank as _Rank
            if int(to_rank) > int(_Rank.DRAFTER):
                raise HTTPException(
                    status_code=409,
                    detail="Strategy stays at Drafter. Zilo spars — you decide.",
                )

        if direction == "promote":
            event = TrustEvent.user_promoted_rex(
                category=body.category,
                from_rank=from_rank,
                to_rank=to_rank,
                reason=body.reason,
            )
        else:
            event = TrustEvent.user_demoted_rex(
                category=body.category,
                from_rank=from_rank,
                to_rank=to_rank,
                reason=body.reason,
            )

        orch.event_store.append(event)
        orch.engine = RankEngine.from_events(orch.event_store)
        await _persist(user, db, orch)

        return {
            "ok": True,
            "category": body.category,
            "from_rank": from_rank.display,
            "to_rank": to_rank.display,
        }

    @router.post("/promote")
    async def rex_promote(body: RankChangeRequest, user=Depends(get_current_user)):
        return await _apply_rank_change(user, body, direction="promote")

    @router.post("/demote")
    async def rex_demote(body: RankChangeRequest, user=Depends(get_current_user)):
        return await _apply_rank_change(user, body, direction="demote")

    @router.get("/team")
    async def rex_team(user=Depends(get_current_user)):
        """All AI agents — Zilo Chat specialists, deputies, and Action Mode runners.

        Team roster is static; per-agent standings are skipped to keep this endpoint
        snappy. Loading the orchestrator + calling `engine.standing()` for each
        sub-agent triggered per-agent Mongo round-trips that could hang on slow links.
        """
        try:
            return serialize_team(None)
        except Exception as e:
            logger.exception("[zilo] /team failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e)[:500])

    async def _background_sync_task(db: Any, user: dict, uid: str, bid: str):
        try:
            store = ZiloSessionStore(db)
            orch = await store.load(uid, business_id=bid)
            wire_action_mode_executor(orch, db, uid)
            # Rate-limit: max 3 forced sweeps per 5 min (even in background)
            try:
                from rate_limiter import check_sweep_cooldown
                await check_sweep_cooldown(uid)
            except Exception as _rl_exc:
                logger.warning("[rex] sync sweep rate-limit check failed: %s", _rl_exc)
            await run_platform_sweep(db, user, orch, force=True)
            await store.save(uid, business_id=bid, orch=orch)
            logger.info("[zilo] background /sync complete uid=%s", uid)
        except Exception as e:
            logger.warning("[zilo] background /sync failed uid=%s: %s", uid, e)

    @router.post("/sync")
    async def rex_sync(user=Depends(get_current_user)):
        """Email pull, scouts, Action Mode agents, queue import, metrics."""
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="CRM sync requires database")
        uid = _uid(user)
        bid = _business_id(user)
        
        # Enforce rate limit check before launching background task
        from rate_limiter import check_sweep_cooldown
        await check_sweep_cooldown(uid)
        
        store = await _session_store()
        orch = await store.load(uid, business_id=bid)
        
        # Run the heavy sync in the background to prevent 500 proxy timeouts
        asyncio.create_task(_background_sync_task(db, user, uid, bid))
        
        return {"ok": True, "report": {"status": "syncing in background"}, "home": serialize_home(orch)}

    # ── Onboarding ───────────────────────────────────────────────────────

    @router.post("/onboarding/start", response_model=StartResponse)
    async def onboarding_start(user=Depends(get_current_user)):
        engine = _reset_engine(user, db)
        welcome = engine.start()
        return StartResponse(
            welcome=welcome,
            state=engine.state.value,
            question=engine.get_current_question(),
        )

    @router.get("/onboarding/state", response_model=StateResponse)
    async def onboarding_state(user=Depends(get_current_user)):
        engine = _get_engine(user, db)
        return StateResponse(
            state=engine.state.value,
            question=engine.get_current_question(),
            complete=engine.state in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE),
        )

    @router.post("/onboarding/answer/{question_num}", response_model=AnswerResponse)
    async def onboarding_answer(question_num: int, body: AnswerRequest, user=Depends(get_current_user)):
        engine = _get_engine(user, db)
        value = (body.value or "").strip()

        try:
            if question_num == 1:
                prompt = engine.answer_question_1(value)
            elif question_num == 2:
                prompt = engine.answer_question_2(value)
            elif question_num == 3:
                prompt = engine.answer_question_3(value)
            elif question_num == 4:
                try:
                    channel = CommunicationChannel(value.lower())
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Unknown channel: {value}")
                prompt = engine.answer_question_4(channel)
            elif question_num == 5:
                try:
                    directness = DirectnessLevel(value.lower())
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Unknown directness: {value}")
                prompt = engine.answer_question_5(directness)
            elif question_num == 6:
                prompt = engine.answer_question_6(value)
            else:
                raise HTTPException(status_code=400, detail="question_num must be 1-6")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        complete = engine.state in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE)
        i_see_it = None
        if engine.i_see_it is not None:
            i_see_it = engine.i_see_it.rex_response

        return AnswerResponse(
            next_prompt=prompt,
            state=engine.state.value,
            question=engine.get_current_question(),
            i_see_it=i_see_it,
            complete=complete,
        )

    @router.get("/onboarding/preferences", response_model=PreferencesResponse)
    async def onboarding_preferences(user=Depends(get_current_user)):
        engine = _get_engine(user, db)
        if engine.state not in (OnboardingState.I_SEE_IT, OnboardingState.COMPLETE):
            raise HTTPException(status_code=409, detail="Onboarding not complete yet")
        return PreferencesResponse(preferences=engine.get_preferences())

    @router.post("/onboarding/reset")
    async def onboarding_reset(user=Depends(get_current_user)):
        engine = _reset_engine(user, db)
        return {"ok": True, "state": engine.state.value}

    # ── Decision Room (strategic sparring) ─────────────────────────────────

    async def _ensure_decision_indexes() -> None:
        global _decision_indexes_ready
        if _decision_indexes_ready or not _use_live_db(db):
            return
        await ensure_decision_indexes(db)
        _decision_indexes_ready = True

    @router.get("/decisions")
    async def rex_decisions_list(
        user=Depends(get_current_user),
        status: str = Query("open", description="open | decided | archived | all"),
    ):
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            return {"sessions": [], "open_count": 0}
        uid = _uid(user)
        st = None if status == "all" else status
        sessions = await list_sessions(db, uid, status=st, limit=30)
        open_count = await count_open(db, uid)
        return {"sessions": sessions, "open_count": open_count}

    @router.get("/decisions/{session_id}")
    async def rex_decision_get(session_id: str, user=Depends(get_current_user)):
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        doc = await get_session(db, session_id, uid)
        if not doc:
            raise HTTPException(status_code=404, detail="Decision session not found")
        if not doc.get("thread") and doc.get("status") == "open":
            from rex.decisions.models import SparResult
            try:
                opening = spar_opening_message(SparResult.model_validate(doc.get("spar") or {}))
                doc = await seed_thread_if_empty(db, session_id, uid, opening) or doc
            except Exception:
                pass
        return serialize_session(doc)

    @router.post("/decisions/spar")
    async def rex_decision_spar(body: SparRequest, user=Depends(get_current_user)):
        """Start a new spar or push back harder on an existing open session."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        prior = None
        if body.session_id and body.push_back_harder:
            doc = await get_session(db, body.session_id, uid)
            if not doc or doc.get("status") != "open":
                raise HTTPException(status_code=404, detail="Open session not found")
            prior = doc.get("spar")
            question = doc.get("question") or body.question
            founder_lean = doc.get("founder_lean") or body.founder_lean
        else:
            question = body.question
            founder_lean = body.founder_lean

        spar_result, ctx = await run_spar(
            db,
            user,
            question=question,
            founder_lean=founder_lean,
            push_back_harder=body.push_back_harder,
            prior_spar=prior,
        )
        spar_dict = spar_result.model_dump()
        ctx_snapshot = {
            k: ctx.get(k)
            for k in (
                "customer_count", "revenue_30d", "revenue_90d", "stalled_deals",
                "followups_due", "followup_conversion_30d", "currency",
            )
        }

        if body.session_id and body.push_back_harder:
            doc = await update_spar(
                db, body.session_id, uid, spar=spar_dict, push_back=True
            )
            if not doc:
                raise HTTPException(status_code=404, detail="Session not found")
            return {"session": serialize_session(doc)}

        doc = await create_session(
            db,
            user,
            question=question,
            founder_lean=founder_lean,
            spar=spar_dict,
            pricing_simulation=ctx.get("pricing_simulation"),
            context_snapshot=ctx_snapshot,
        )
        opening = spar_opening_message(spar_result)
        doc = await seed_thread_if_empty(db, doc["_id"], uid, opening) or doc

        async def _sync_briefing(o: Orchestrator) -> None:
            await sync_open_decisions_to_briefing(db, user, o)

        try:
            await _persist_orch_with_retry(user, db, mutate=_sync_briefing)
        except Exception as e:
            logger.warning("[zilo] decision spar briefing sync: %s", e)
        return {"session": serialize_session(doc)}

    @router.post("/decisions/{session_id}/message")
    async def rex_decision_message(
        session_id: str,
        body: MessageRequest,
        user=Depends(get_current_user),
    ):
        """Continue the Decision Room conversation — Zilo spars, never decides."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        doc = await get_session(db, session_id, uid)
        if not doc or doc.get("status") != "open":
            raise HTTPException(status_code=404, detail="Open session not found")

        spar_raw = doc.get("spar") or {}
        thread = list(doc.get("thread") or [])
        if not thread:
            from rex.decisions.models import SparResult
            try:
                opening = spar_opening_message(SparResult.model_validate(spar_raw))
            except Exception:
                opening = spar_raw.get("pressure_question") or "What's making this hard to call?"
            seeded = await seed_thread_if_empty(db, session_id, uid, opening)
            if seeded:
                doc = seeded
                thread = list(doc.get("thread") or [])

        from datetime import datetime as _dt
        user_msg = {
            "role": "user",
            "content": body.message.strip(),
            "created_at": _dt.utcnow().isoformat() + "Z",
        }
        reply = await run_conversation_turn(
            db,
            user,
            question=doc.get("question") or "",
            founder_lean=doc.get("founder_lean") or "",
            spar=spar_raw,
            thread=thread + [user_msg],
            user_message=body.message.strip(),
        )
        assistant_msg = {
            "role": "assistant",
            "content": reply,
            "created_at": _dt.utcnow().isoformat() + "Z",
            "regeneration_count": 0,
            "feedback": None,
        }
        updated = await append_thread_messages(db, session_id, uid, [user_msg, assistant_msg])
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session": serialize_session(updated), "reply": reply}

    @router.post("/decisions/{session_id}/thread/{message_index}/feedback")
    async def rex_decision_thread_feedback(
        session_id: str,
        message_index: int,
        body: NoteFeedbackRequest,
        user=Depends(get_current_user),
    ):
        """Thumbs up/down on a spar conversation Zilo message."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        doc = await get_session(db, session_id, uid)
        if not doc or doc.get("status") != "open":
            raise HTTPException(status_code=404, detail="Open session not found")
        thread = doc.get("thread") or []
        if message_index < 0 or message_index >= len(thread):
            raise HTTPException(status_code=404, detail="Message not found")
        if thread[message_index].get("role") != "assistant":
            raise HTTPException(status_code=400, detail="Only Zilo messages can be rated")

        updated = await patch_thread_message(
            db,
            session_id,
            uid,
            message_index,
            fields={"feedback": body.feedback},
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Message not found")
        return {"session": serialize_session(updated)}

    @router.post("/decisions/{session_id}/thread/{message_index}/regenerate")
    async def rex_decision_thread_regenerate(
        session_id: str,
        message_index: int,
        user=Depends(get_current_user),
    ):
        """Regenerate a Zilo spar conversation reply (max 3 per message)."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        doc = await get_session(db, session_id, uid)
        if not doc or doc.get("status") != "open":
            raise HTTPException(status_code=404, detail="Open session not found")
        thread = list(doc.get("thread") or [])
        if message_index < 0 or message_index >= len(thread):
            raise HTTPException(status_code=404, detail="Message not found")
        entry = thread[message_index]
        if entry.get("role") != "assistant":
            raise HTTPException(status_code=400, detail="Only Zilo messages can be regenerated")

        regen_count = int(entry.get("regeneration_count") or 0)
        if regen_count >= MAX_UPDATE_REGENERATIONS:
            raise HTTPException(
                status_code=400,
                detail="Regeneration limit reached. Add more context in the conversation.",
            )

        rejected = (entry.get("content") or "").strip()
        prior_reactions = [
            (m.get("content") or "").strip()
            for m in thread[:message_index]
            if m.get("role") == "assistant" and (m.get("content") or "").strip()
        ]
        if message_index == 0:
            context_text = (doc.get("question") or "").strip()
        else:
            context_text = (thread[message_index - 1].get("content") or "").strip()
        hints = analyze_rejected_response(rejected, prior_reactions, context_text)
        marked_unhelpful = entry.get("feedback") == "down"

        try:
            reply = await regenerate_thread_assistant(
                db,
                user,
                session=doc,
                message_index=message_index,
                rejected_response=rejected,
                marked_unhelpful=marked_unhelpful,
                rejection_hints=hints,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        updated = await patch_thread_message(
            db,
            session_id,
            uid,
            message_index,
            fields={
                "content": reply,
                "regeneration_count": regen_count + 1,
            },
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Message not found")
        return {"session": serialize_session(updated), "reply": reply}

    @router.post("/decisions/{session_id}/note")
    async def rex_decision_note(
        session_id: str,
        body: NoteRequest,
        user=Depends(get_current_user),
    ):
        """Log a founder progress update / outcome on a decision — Zilo reacts as advisor."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        doc = await get_session(db, session_id, uid)
        if not doc:
            raise HTTPException(status_code=404, detail="Decision session not found")

        from datetime import datetime as _dt

        reaction = await react_to_update(db, user, session=doc, update_text=body.text.strip())
        update = {
            "text": body.text.strip(),
            "zilo_reaction": reaction,
            "created_at": _dt.utcnow().isoformat() + "Z",
            "regeneration_count": 0,
            "feedback": None,
        }
        updated = await append_founder_update(db, session_id, uid, update)
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session": serialize_session(updated), "reaction": reaction}

    @router.post("/decisions/{session_id}/note/{update_index}/feedback")
    async def rex_decision_note_feedback(
        session_id: str,
        update_index: int,
        body: NoteFeedbackRequest,
        user=Depends(get_current_user),
    ):
        """Thumbs up/down on a Zilo update reaction — used when regenerating."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        doc = await get_session(db, session_id, uid)
        if not doc:
            raise HTTPException(status_code=404, detail="Decision session not found")
        updates = doc.get("founder_updates") or []
        if update_index < 0 or update_index >= len(updates):
            raise HTTPException(status_code=404, detail="Update not found")

        updated = await patch_founder_update(
            db,
            session_id,
            uid,
            update_index,
            fields={"feedback": body.feedback},
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Update not found")
        return {"session": serialize_session(updated)}

    @router.post("/decisions/{session_id}/note/{update_index}/regenerate")
    async def rex_decision_note_regenerate(
        session_id: str,
        update_index: int,
        user=Depends(get_current_user),
    ):
        """Regenerate Zilo's reaction to a founder update (max 3 per log entry)."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        doc = await get_session(db, session_id, uid)
        if not doc:
            raise HTTPException(status_code=404, detail="Decision session not found")
        updates = doc.get("founder_updates") or []
        if update_index < 0 or update_index >= len(updates):
            raise HTTPException(status_code=404, detail="Update not found")

        entry = updates[update_index]
        regen_count = int(entry.get("regeneration_count") or 0)
        if regen_count >= MAX_UPDATE_REGENERATIONS:
            raise HTTPException(
                status_code=400,
                detail="Regeneration limit reached. Add more context in a new log entry.",
            )

        rejected = (entry.get("zilo_reaction") or "").strip()
        update_text = (entry.get("text") or "").strip()
        prior_reactions = [
            (u.get("zilo_reaction") or "").strip()
            for u in updates[:update_index]
            if (u.get("zilo_reaction") or "").strip()
        ]
        hints = analyze_rejected_response(rejected, prior_reactions, update_text)
        marked_unhelpful = entry.get("feedback") == "down"

        reaction = await react_to_update(
            db,
            user,
            session=doc,
            update_text=update_text,
            thread_updates=updates[:update_index],
            rejected_response=rejected,
            marked_unhelpful=marked_unhelpful,
            rejection_hints=hints,
        )

        updated = await patch_founder_update(
            db,
            session_id,
            uid,
            update_index,
            fields={
                "zilo_reaction": reaction,
                "regeneration_count": regen_count + 1,
            },
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Update not found")
        return {"session": serialize_session(updated), "reaction": reaction}

    @router.post("/decisions/{session_id}/decide")
    async def rex_decision_decide(
        session_id: str,
        body: DecideRequest,
        user=Depends(get_current_user),
    ):
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        ctx = await gather_decision_context(db, user)
        baseline = baseline_from_context(ctx)
        from datetime import datetime as _dt

        decided_now = _dt.utcnow()
        review_days = normalize_review_days(body.review_days)
        tracking = init_outcome_tracking(decided_now, baseline, review_days)
        doc = await record_decision(
            db,
            session_id,
            uid,
            decision=body.decision,
            notes=body.notes,
            metrics_baseline=baseline,
            outcome_checkpoints=tracking["outcome_checkpoints"],
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Open session not found")

        # Decision is recorded. The rest (journal, notebook, briefing cleanup)
        # is best-effort — never fail the request if a background writer collides.
        try:
            orch = await _get_orchestrator(user, db, refresh=False)
            day = getattr(orch, "_relationship_day", 1)
            await persist_decision_journal(
                db,
                doc,
                decision=body.decision,
                notes=body.notes,
                relationship_day=day,
            )
        except Exception as e:
            logger.warning("[zilo] decision journal persist: %s", e)

        def _apply_decision_sideeffects(o: Orchestrator) -> None:
            add_decision_notebook_pattern(
                o,
                question=doc.get("question") or "",
                decision=body.decision,
            )
            dismiss_decision_briefing_actions(o, session_id)

        await _persist_orch_with_retry(user, db, mutate=_apply_decision_sideeffects)

        # Work Plan integration hook: if decision is made, run background task to parse and create tasks
        try:
            async def parse_decision_and_create_tasks_bg():
                try:
                    from rex.workplan.service import parse_notes_and_create_tasks
                    from rex.workplan.routes import _IN_MEMORY_TASKS
                    import uuid as _uuid
                    notes_text = f"Founder decided: {body.decision}\nNotes: {body.notes}"
                    
                    if _use_live_db(db):
                        tasks = await db.workplan_tasks.find({"user_id": uid}).to_list(100)
                        current_tasks = [{**t, "id": str(t["_id"])} for t in tasks]
                    else:
                        current_tasks = _IN_MEMORY_TASKS.get(uid, [])
                        
                    result = await parse_notes_and_create_tasks(notes_text, current_tasks)
                    from rex.workplan.routes import open_duplicate_exists, _norm_title
                    for nt in result.get("new_tasks", []):
                        nt_id = str(_uuid.uuid4())
                        nt_title = nt.get("title") or ""
                        nt_owner = nt.get("owner", "founder")
                        # Re-running the same decision must not duplicate tasks.
                        if _use_live_db(db):
                            if await open_duplicate_exists(db, uid, nt_title, nt_owner):
                                continue
                        else:
                            _norm = _norm_title(nt_title)
                            if any(
                                t.get("owner") == nt_owner
                                and t.get("status") != "done"
                                and _norm_title(t.get("title")) == _norm
                                for t in _IN_MEMORY_TASKS.get(uid, [])
                            ):
                                continue
                        new_task = {
                            "title": nt.get("title"),
                            "owner": nt.get("owner", "founder"),
                            "due_date": nt.get("due_date") or (datetime.utcnow() + timedelta(days=7)).isoformat(),
                            "source": f"Decision Room {datetime.utcnow().strftime('%b %d')}",
                            "status": "pending",
                            "context": nt.get("context"),
                            "created_at": datetime.utcnow().isoformat(),
                            "updated_at": datetime.utcnow().isoformat(),
                        }
                        if _use_live_db(db):
                            new_task["_id"] = nt_id
                            new_task["user_id"] = uid
                            await db.workplan_tasks.insert_one(new_task)
                        else:
                            new_task["id"] = nt_id
                            if uid not in _IN_MEMORY_TASKS:
                                from rex.workplan.routes import get_demo_tasks
                                _IN_MEMORY_TASKS[uid] = get_demo_tasks()
                            _IN_MEMORY_TASKS[uid].append(new_task)
                except Exception as bg_err:
                    logger.warning("[workplan-decision-hook] Background parsing failed: %s", bg_err)
            
            asyncio.create_task(parse_decision_and_create_tasks_bg())
        except Exception as _hook_err:
            logger.warning("[workplan-decision-hook] Failed to spawn task creator: %s", _hook_err)

        refreshed = await get_session(db, session_id, uid)
        return {"session": serialize_session(refreshed or doc)}

    @router.post("/decisions/{session_id}/schedule")
    async def rex_decision_update_schedule(
        session_id: str,
        body: ScheduleRequest,
        user=Depends(get_current_user),
    ):
        """Update review checkpoints on a recorded decision (keeps completed reviews)."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        doc = await get_session(db, session_id, uid)
        if not doc or doc.get("status") != "decided":
            raise HTTPException(status_code=404, detail="Decided session not found")
        decided_at = doc.get("decided_at")
        if not decided_at:
            raise HTTPException(status_code=400, detail="Decision has no decided_at timestamp")

        from datetime import datetime as _dt

        if hasattr(decided_at, "replace"):
            decided_dt = decided_at.replace(tzinfo=None) if getattr(decided_at, "tzinfo", None) else decided_at
        else:
            decided_dt = _dt.fromisoformat(str(decided_at).replace("Z", "+00:00")).replace(tzinfo=None)

        review_days = normalize_review_days(body.review_days)
        checkpoints = rebuild_checkpoints_for_schedule(
            existing_checkpoints=doc.get("outcome_checkpoints") or [],
            outcome_reports=doc.get("outcome_reports") or [],
            decided_at=decided_dt,
            review_days=review_days,
        )
        updated = await update_outcome_schedule(
            db,
            session_id,
            uid,
            outcome_checkpoints=checkpoints,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Decided session not found")
        return {"session": serialize_session(updated)}

    @router.post("/decisions/outcomes/run")
    async def rex_decisions_outcomes_run(
        user=Depends(get_current_user),
        force: bool = Query(False, description="Process all pending checkpoints immediately (demo/testing)"),
    ):
        """Process due 30/60/90-day outcome checkpoints (also runs on briefing refresh)."""
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        created = await process_due_outcomes(db, user, force=force)
        from rex.decisions.bridge import sync_outcome_reports_to_briefing

        async def _sync_outcomes(o: Orchestrator) -> None:
            await sync_outcome_reports_to_briefing(db, user, o)

        try:
            await _persist_orch_with_retry(user, db, mutate=_sync_outcomes)
        except Exception as e:
            logger.warning("[zilo] outcomes briefing sync: %s", e)
        return {"processed": len(created), "reports": created}

    @router.post("/decisions/{session_id}/archive")
    async def rex_decision_archive(session_id: str, user=Depends(get_current_user)):
        await _ensure_decision_indexes()
        if not _use_live_db(db):
            raise HTTPException(status_code=501, detail="Database required")
        uid = _uid(user)
        ok = await archive_session(db, session_id, uid)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")

        def _dismiss(o: Orchestrator) -> None:
            dismiss_decision_briefing_actions(o, session_id)

        await _persist_orch_with_retry(user, db, mutate=_dismiss)
        return {"ok": True}

    return router

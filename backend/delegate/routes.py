"""FastAPI routes for Delegate. Mounted at /api/delegate/*."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from .models import DelegationCreate, DraftRegenerateRequest, DraftUpdateRequest, InterpretRequest, SimulateEventRequest
from .service import (
    COLLECTION,
    MAX_DRAFT_REGENERATIONS,
    approve_all_drafts,
    compute_next_run,
    delegation_mode_label,
    get_automation_diagnostics,
    get_rank_for_category,
    interpret_task,
    map_category,
    pending_draft_count,
    rank_behavior,
    regenerate_draft,
    run_delegation,
    run_due_scheduled_delegations,
    set_draft_approval,
    simulate_client_event,
    update_draft_text,
)

logger = logging.getLogger(__name__)


def _serialize(doc: dict) -> dict:
    from bson import ObjectId

    out: dict[str, Any] = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = _serialize(v)
        elif isinstance(v, list):
            out[k] = [_serialize(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    if "_id" in out and "id" not in out:
        out["id"] = out["_id"]
    out["schedule_label"] = delegation_mode_label(doc)
    return out


def make_delegate_router(db, user_dep):
    router = APIRouter(prefix="/delegate", tags=["delegate"])

    # ── Interpret (live confirmation box) ──────────────────────────────────
    @router.post("/interpret")
    async def interpret(body: InterpretRequest, user=user_dep):
        result = await interpret_task(db, user, body.task)
        behavior = rank_behavior(
            await get_rank_for_category(db, user["_id"], result.get("category", "follow_ups"))
        )
        result["rank_note"] = behavior["note"]
        return result

    # ── List delegations ───────────────────────────────────────────────────
    @router.get("")
    async def list_delegations(user=user_dep):
        docs = await db[COLLECTION].find(
            {"user_id": user["_id"]}, sort=[("created_at", -1)]
        ).to_list(200)
        return [_serialize(d) for d in docs]

    # ── Create delegation ──────────────────────────────────────────────────
    @router.post("")
    async def create_delegation(body: DelegationCreate, user=user_dep):
        user_id = user["_id"]
        category = map_category(body.task)
        rank = await get_rank_for_category(db, user_id, category)
        interp = await interpret_task(db, user, body.task)
        now = datetime.utcnow()
        did = str(uuid.uuid4())

        is_schedule = body.mode == "schedule" and body.schedule is not None
        is_on_opportunity = body.mode == "on_opportunity"
        schedule = body.schedule.model_dump() if (is_schedule and body.schedule) else None
        next_run = compute_next_run(schedule, after=now) if schedule else None
        trigger_filter = (body.trigger_filter or "client_message") if is_on_opportunity else None
        trigger_channel = (body.trigger_channel or "any") if is_on_opportunity else None

        if is_on_opportunity:
            mode = "on_opportunity"
            status = "watching"
        elif is_schedule:
            mode = "schedule"
            status = "scheduled"
        else:
            mode = "once"
            status = "running"

        doc = {
            "_id": did,
            "user_id": user_id,
            "task": body.task.strip(),
            "interpreted": interp,
            "mode": mode,
            "schedule": schedule,
            "trigger_filter": trigger_filter,
            "trigger_channel": trigger_channel,
            "category": category,
            "rank": rank,
            "rank_note": rank_behavior(rank)["note"],
            "status": status,
            "progress": {"total": 0, "done": 0},
            "subtasks": [],
            "staged_count": 0,
            "runs": [],
            "next_run_at": next_run,
            "last_run_at": None,
            "started_at": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await db[COLLECTION].insert_one(doc)

        # Remember the founder's timezone for reuse (briefings, future schedules).
        tz_name = (schedule or {}).get("timezone") if schedule else None
        if tz_name and tz_name != "UTC":
            try:
                await db.users.update_one({"_id": user_id}, {"$set": {"timezone": tz_name}})
            except Exception:  # noqa: BLE001
                pass

        # Once: kick off execution in the background immediately.
        if mode == "once":
            asyncio.create_task(_safe_run(db, did, user))

        saved = await db[COLLECTION].find_one({"_id": did})
        return _serialize(saved)

    @router.get("/automation-status")
    async def automation_status(user=user_dep):
        """Diagnostics for scheduled/event automations (testing & monitoring)."""
        return await get_automation_diagnostics(db, user["_id"])

    @router.post("/run-due-scheduled")
    async def run_due_scheduled(user=user_dep):
        """Force the scheduler tick now (same job that runs every 5 minutes)."""
        before = await get_automation_diagnostics(db, user["_id"])
        count = await run_due_scheduled_delegations(db, user_id=user["_id"])
        after = await get_automation_diagnostics(db, user["_id"])
        return {
            "triggered": count,
            "was_due_before": before.get("due_scheduled_count", 0),
            "still_due": after.get("due_scheduled_count", 0),
            "due_scheduled_ids_before": before.get("due_scheduled_ids", []),
        }

    # ── Get single ─────────────────────────────────────────────────────────
    @router.get("/{delegation_id}")
    async def get_delegation(delegation_id: str, user=user_dep):
        doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Delegation not found")
        return _serialize(doc)

    # ── Pause / Resume ─────────────────────────────────────────────────────
    @router.post("/{delegation_id}/pause")
    async def pause_delegation(delegation_id: str, user=user_dep):
        doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Delegation not found")
        await db[COLLECTION].update_one(
            {"_id": delegation_id},
            {"$set": {"status": "paused", "updated_at": datetime.utcnow()}},
        )
        return _serialize(await db[COLLECTION].find_one({"_id": delegation_id}))

    @router.post("/{delegation_id}/resume")
    async def resume_delegation(delegation_id: str, user=user_dep):
        doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Delegation not found")
        if doc.get("mode") == "schedule":
            new_status = "scheduled"
            next_run = compute_next_run(doc.get("schedule") or {}, after=datetime.utcnow())
            await db[COLLECTION].update_one(
                {"_id": delegation_id},
                {"$set": {"status": new_status, "next_run_at": next_run, "updated_at": datetime.utcnow()}},
            )
        elif doc.get("mode") == "on_opportunity":
            await db[COLLECTION].update_one(
                {"_id": delegation_id},
                {"$set": {"status": "watching", "updated_at": datetime.utcnow()}},
            )
        elif doc.get("subtasks"):
            # A once-task paused after staging drafts: finalize for review rather
            # than re-running, which would wipe (and possibly re-send) those drafts.
            await db[COLLECTION].update_one(
                {"_id": delegation_id},
                {"$set": {"status": "completed", "updated_at": datetime.utcnow()}},
            )
        else:
            await db[COLLECTION].update_one(
                {"_id": delegation_id},
                {"$set": {"status": "running", "updated_at": datetime.utcnow()}},
            )
            asyncio.create_task(_safe_run(db, delegation_id, user))
        return _serialize(await db[COLLECTION].find_one({"_id": delegation_id}))

    @router.post("/{delegation_id}/simulate-event")
    async def simulate_event(delegation_id: str, body: SimulateEventRequest, user=user_dep):
        """Test a client-message automation without sending a real inbound webhook."""
        result = await simulate_client_event(
            db,
            user["_id"],
            delegation_id,
            customer_id=body.customer_id.strip(),
            message=body.message,
            is_first=body.is_first,
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user["_id"]})
        return {"result": result, "session": _serialize(doc) if doc else None}

    # ── Run now (manual trigger for scheduled delegations) ─────────────────
    @router.post("/{delegation_id}/run")
    async def run_now(delegation_id: str, user=user_dep):
        doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Delegation not found")
        asyncio.create_task(_safe_run(db, delegation_id, user, keep_scheduled=doc.get("mode") in ("schedule", "on_opportunity")))
        return {"started": True}

    # ── Update schedule ────────────────────────────────────────────────────
    @router.post("/{delegation_id}/schedule")
    async def edit_schedule(delegation_id: str, body: dict, user=user_dep):
        doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Delegation not found")
        frequency = body.get("frequency")
        time = body.get("time", "07:00")
        if not frequency:
            raise HTTPException(status_code=400, detail="frequency required")
        tz_name = (
            body.get("timezone")
            or (doc.get("schedule") or {}).get("timezone")
            or "UTC"
        )
        schedule = {"frequency": frequency, "time": time, "timezone": tz_name}
        next_run = compute_next_run(schedule, after=datetime.utcnow())
        await db[COLLECTION].update_one(
            {"_id": delegation_id},
            {
                "$set": {
                    "schedule": schedule,
                    "mode": "schedule",
                    "status": "scheduled",
                    "next_run_at": next_run,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return _serialize(await db[COLLECTION].find_one({"_id": delegation_id}))

    # ── Draft review (edit / regenerate / approve / reject) ────────────────
    @router.patch("/{delegation_id}/drafts/{draft_id}")
    async def edit_draft(delegation_id: str, draft_id: str, body: DraftUpdateRequest, user=user_dep):
        updated = await update_draft_text(
            db, delegation_id, user["_id"], draft_id, body.draft
        )
        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Draft not found or already reviewed",
            )
        return {"session": _serialize(updated), "pending": pending_draft_count(updated)}

    @router.post("/{delegation_id}/drafts/{draft_id}/regenerate")
    async def regen_draft(
        delegation_id: str, draft_id: str, body: DraftRegenerateRequest, user=user_dep
    ):
        updated, err = await regenerate_draft(
            db, delegation_id, user["_id"], draft_id, feedback=body.feedback
        )
        if err == "regen_limit":
            raise HTTPException(
                status_code=429,
                detail=f"Maximum {MAX_DRAFT_REGENERATIONS} regenerations per draft",
            )
        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Draft not found or already reviewed",
            )
        return {"session": _serialize(updated), "pending": pending_draft_count(updated)}

    @router.post("/{delegation_id}/drafts/{draft_id}/approve")
    async def approve_draft(delegation_id: str, draft_id: str, user=user_dep):
        updated = await set_draft_approval(
            db, delegation_id, user["_id"], draft_id, "approved"
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Draft not found")
        return {"session": _serialize(updated), "pending": pending_draft_count(updated)}

    @router.post("/{delegation_id}/drafts/{draft_id}/reject")
    async def reject_draft(delegation_id: str, draft_id: str, user=user_dep):
        updated = await set_draft_approval(
            db, delegation_id, user["_id"], draft_id, "rejected"
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Draft not found")
        return {"session": _serialize(updated), "pending": pending_draft_count(updated)}

    @router.post("/{delegation_id}/drafts/approve-all")
    async def approve_all(delegation_id: str, user=user_dep):
        updated = await approve_all_drafts(db, delegation_id, user["_id"])
        if not updated:
            raise HTTPException(status_code=404, detail="Delegation not found")
        return {"session": _serialize(updated), "pending": 0}

    # ── Delete ─────────────────────────────────────────────────────────────
    @router.delete("/{delegation_id}")
    async def delete_delegation(delegation_id: str, user=user_dep):
        doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Delegation not found")
        await db[COLLECTION].delete_one({"_id": delegation_id})
        return {"deleted": True}

    return router


async def _safe_run(db, delegation_id: str, user: dict, *, keep_scheduled: bool = False) -> None:
    doc = await db[COLLECTION].find_one({"_id": delegation_id})
    try:
        await run_delegation(db, delegation_id, user)
        if keep_scheduled and doc:
            mode = doc.get("mode")
            if mode == "on_opportunity":
                await db[COLLECTION].update_one(
                    {"_id": delegation_id},
                    {"$set": {"status": "watching", "updated_at": datetime.utcnow()}},
                )
            elif mode == "schedule":
                await db[COLLECTION].update_one(
                    {"_id": delegation_id},
                    {"$set": {"status": "scheduled", "updated_at": datetime.utcnow()}},
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] run failed for %s: %s", delegation_id, e)
        try:
            # Revert to the mode's resting status so a failed run-now doesn't
            # strand a recurring delegation in "completed" (which never re-runs).
            mode = (doc or {}).get("mode")
            if mode == "on_opportunity":
                fallback = "watching"
            elif mode == "schedule":
                fallback = "scheduled"
            else:
                fallback = "completed"
            await db[COLLECTION].update_one(
                {"_id": delegation_id},
                {"$set": {"status": fallback, "result_summary": "Run failed.", "updated_at": datetime.utcnow()}},
            )
        except Exception:
            pass

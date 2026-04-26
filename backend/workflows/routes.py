"""
routes.py — FastAPI routes for the workflow engine.

Mounted at /api/workflows/* by server.py.

All routes require authentication (same JWT as the rest of the API).
Every DB query is scoped to user_id (tenant isolation enforced here).
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

from .capabilities import CAPABILITIES, TRIGGER_TYPES
from .models import WorkflowCreate, WorkflowUpdate
from .ai_builder import build_workflow_from_description, fallback_workflow_create

logger = logging.getLogger(__name__)


class BuildFromDescriptionBody(BaseModel):
    """POST /build/from-description — tolerate prompt/description aliases and loose client JSON."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    description: str = Field(
        default="",
        validation_alias=AliasChoices("description", "prompt"),
    )

    @field_validator("description", mode="before")
    @classmethod
    def _coerce_description(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (dict, list)):
            return ""
        return str(v).strip()


def make_workflow_router(db, user_dep):
    """Factory that wires the router to the app's db + auth dependency."""
    router = APIRouter(prefix="/workflows", tags=["workflows"])

    # ── List workflows ─────────────────────────────────────────────────────
    @router.get("")
    async def list_workflows(user=user_dep):
        user_id = user["_id"]
        docs = await db.workflows.find(
            {"user_id": user_id},
            sort=[("created_at", -1)],
        ).to_list(200)
        return [_serialize(d) for d in docs]

    # ── Static paths before /{workflow_id} (otherwise "meta" is treated as an id) ──
    @router.get("/meta/capabilities")
    async def get_capabilities(user=user_dep):
        return {
            "capabilities": CAPABILITIES,
            "trigger_types": TRIGGER_TYPES,
        }

    # ── AI builder (body validation is BuildFromDescriptionBody, not bare str) ──
    @router.post("/build/from-description")
    async def build_from_description(payload: BuildFromDescriptionBody, user=user_dep):
        if not payload.description or len(payload.description) < 10:
            raise HTTPException(status_code=400, detail="Description too short")
        desc = payload.description

        wf_dict = None
        try:
            wf_dict = await build_workflow_from_description(description=desc, user=user)
        except Exception as exc:
            logger.warning("[build_from_description] AI builder failed, using fallback: %s", exc)

        validated: WorkflowCreate | None = None
        if wf_dict is not None:
            try:
                validated = WorkflowCreate.model_validate(wf_dict)
            except ValidationError as exc:
                logger.warning(
                    "[build_from_description] AI output failed validation, using fallback: %s",
                    exc.errors(),
                )

        if validated is None:
            try:
                validated = WorkflowCreate.model_validate(fallback_workflow_create(desc))
            except ValidationError as exc:
                logger.exception("[build_from_description] fallback workflow invalid")
                raise HTTPException(status_code=500, detail="Could not create starter workflow") from exc

        user_id = user["_id"]
        for step in validated.steps:
            if step.action not in CAPABILITIES and step.action not in ("wait", "if_no_reply"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown action '{step.action}'. Use GET /api/workflows/meta/capabilities for the list.",
                )

        wf_id = str(uuid.uuid4())
        now = datetime.utcnow()
        doc = {
            "_id": wf_id,
            "user_id": user_id,
            "name": validated.name,
            "description": validated.description,
            "trigger": validated.trigger.model_dump(),
            "steps": [s.model_dump() for s in validated.steps],
            "enabled": validated.enabled,
            "run_count": 0,
            "last_run_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.workflows.insert_one(doc)
        return _serialize(doc)

    # ── Get single workflow ────────────────────────────────────────────────
    @router.get("/{workflow_id}")
    async def get_workflow(workflow_id: str, user=user_dep):
        doc = await db.workflows.find_one({"_id": workflow_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return _serialize(doc)

    # ── Create workflow ────────────────────────────────────────────────────
    @router.post("")
    async def create_workflow(payload: WorkflowCreate, user=user_dep):
        user_id = user["_id"]
        # Validate all step actions are real capabilities
        for step in payload.steps:
            if step.action not in CAPABILITIES and step.action not in ("wait", "if_no_reply"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown action '{step.action}'. Use GET /api/workflows/meta/capabilities for the list.",
                )

        wf_id = str(uuid.uuid4())
        now = datetime.utcnow()
        doc = {
            "_id": wf_id,
            "user_id": user_id,
            "name": payload.name,
            "description": payload.description,
            "trigger": payload.trigger.model_dump(),
            "steps": [s.model_dump() for s in payload.steps],
            "enabled": payload.enabled,
            "run_count": 0,
            "last_run_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.workflows.insert_one(doc)
        return _serialize(doc)

    # ── Update workflow ────────────────────────────────────────────────────
    @router.put("/{workflow_id}")
    async def update_workflow(workflow_id: str, payload: WorkflowUpdate, user=user_dep):
        doc = await db.workflows.find_one({"_id": workflow_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Workflow not found")

        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if payload.name is not None:
            updates["name"] = payload.name
        if payload.description is not None:
            updates["description"] = payload.description
        if payload.trigger is not None:
            updates["trigger"] = payload.trigger.model_dump()
        if payload.steps is not None:
            for step in payload.steps:
                if step.action not in CAPABILITIES and step.action not in ("wait", "if_no_reply"):
                    raise HTTPException(status_code=400, detail=f"Unknown action '{step.action}'")
            updates["steps"] = [s.model_dump() for s in payload.steps]
        if payload.enabled is not None:
            updates["enabled"] = payload.enabled

        await db.workflows.update_one({"_id": workflow_id}, {"$set": updates})
        updated = await db.workflows.find_one({"_id": workflow_id})
        return _serialize(updated)

    # ── Toggle enable/disable ──────────────────────────────────────────────
    @router.post("/{workflow_id}/toggle")
    async def toggle_workflow(workflow_id: str, user=user_dep):
        doc = await db.workflows.find_one({"_id": workflow_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Workflow not found")
        new_state = not doc.get("enabled", True)
        await db.workflows.update_one(
            {"_id": workflow_id},
            {"$set": {"enabled": new_state, "updated_at": datetime.utcnow()}},
        )
        return {"enabled": new_state}

    # ── Delete workflow ────────────────────────────────────────────────────
    @router.delete("/{workflow_id}")
    async def delete_workflow(workflow_id: str, user=user_dep):
        doc = await db.workflows.find_one({"_id": workflow_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Workflow not found")
        await db.workflows.delete_one({"_id": workflow_id})
        # Clean up any pending steps for this workflow
        await db.workflow_pending_steps.delete_many({"workflow_id": workflow_id})
        return {"deleted": True}

    # ── Run history ────────────────────────────────────────────────────────
    @router.get("/{workflow_id}/runs")
    async def get_runs(workflow_id: str, limit: int = 20, user=user_dep):
        doc = await db.workflows.find_one({"_id": workflow_id, "user_id": user["_id"]})
        if not doc:
            raise HTTPException(status_code=404, detail="Workflow not found")
        runs = await db.workflow_runs.find(
            {"workflow_id": workflow_id, "user_id": user["_id"]},
            sort=[("started_at", -1)],
        ).to_list(min(limit, 100))
        return [_serialize(r) for r in runs]

    return router


# ── Serialisation helper ───────────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    from bson import ObjectId
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = _serialize(v)
        elif isinstance(v, list):
            result[k] = [_serialize(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    if "_id" in result and "id" not in result:
        result["id"] = result["_id"]
    return result

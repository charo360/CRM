"""HTTP API: workspaces, channel access, inbound routing settings."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .access import CANONICAL_CHANNELS, list_grants_matrix, replace_grants, tenant_business_id
from .routing import match_routing_rules


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    member_user_ids: List[str] = Field(default_factory=list)
    linked_conversation_id: Optional[str] = None


class WorkspacePatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    member_user_ids: Optional[List[str]] = None
    linked_conversation_id: Optional[str] = None


class ChannelGrantItem(BaseModel):
    user_id: str
    channel: str
    level: str


class ChannelAccessPut(BaseModel):
    grants: List[ChannelGrantItem]


class InboundRule(BaseModel):
    id: Optional[str] = None
    name: str = ""
    enabled: bool = True
    keywords: List[str] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=lambda: ["whatsapp", "social", "email"])
    assignee_user_id: str = ""


class InboundRoutingPut(BaseModel):
    enabled: bool = False
    replace_existing: bool = False
    default_assignee: str = "owner"
    rules: List[InboundRule] = Field(default_factory=list)


class InboundPreviewBody(BaseModel):
    text: str = ""
    subject: Optional[str] = None
    channel: str = "whatsapp"


def _can_manage_collab_settings(check_permission: Callable[..., bool], user: dict) -> bool:
    return check_permission(user, "manager")


def _workspace_visible(row: dict, user: dict, check_permission: Callable[..., bool]) -> bool:
    if _can_manage_collab_settings(check_permission, user):
        return True
    members = row.get("member_user_ids")
    if not members:
        return True
    return str(user["_id"]) in [str(x) for x in members]


def make_collaboration_router(
    db,
    get_current_user,
    check_permission: Callable[..., bool],
):
    router = APIRouter(prefix="/business/collaboration", tags=["business-collaboration"])

    @router.get("/workspaces")
    async def list_workspaces(user=Depends(get_current_user)):
        business_id = tenant_business_id(user)
        out: List[Dict[str, Any]] = []
        async for row in db.business_workspaces.find({"business_id": business_id}).sort(
            "updated_at", -1
        ):
            if not _workspace_visible(row, user, check_permission):
                continue
            out.append(
                {
                    "id": row["_id"],
                    "name": row.get("name"),
                    "description": row.get("description") or "",
                    "member_user_ids": row.get("member_user_ids") or [],
                    "linked_conversation_id": row.get("linked_conversation_id"),
                    "assets": row.get("assets") or [],
                    "created_by": row.get("created_by"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                }
            )
        return {"workspaces": out}

    @router.post("/workspaces")
    async def create_workspace(body: WorkspaceCreate, user=Depends(get_current_user)):
        business_id = tenant_business_id(user)
        now = datetime.utcnow()
        wid = str(uuid.uuid4())
        doc = {
            "_id": wid,
            "business_id": business_id,
            "name": body.name.strip(),
            "description": (body.description or "").strip(),
            "member_user_ids": body.member_user_ids or [],
            "linked_conversation_id": body.linked_conversation_id,
            "assets": [],
            "created_by": str(user["_id"]),
            "created_at": now,
            "updated_at": now,
        }
        await db.business_workspaces.insert_one(doc)
        return {"id": wid, **{k: v for k, v in doc.items() if k not in ("_id", "business_id", "assets")}}

    @router.get("/workspaces/{workspace_id}")
    async def get_workspace(workspace_id: str, user=Depends(get_current_user)):
        business_id = tenant_business_id(user)
        row = await db.business_workspaces.find_one(
            {"_id": workspace_id, "business_id": business_id}
        )
        if not row or not _workspace_visible(row, user, check_permission):
            raise HTTPException(404, "Workspace not found")
        return {
            "id": row["_id"],
            "name": row.get("name"),
            "description": row.get("description") or "",
            "member_user_ids": row.get("member_user_ids") or [],
            "linked_conversation_id": row.get("linked_conversation_id"),
            "assets": row.get("assets") or [],
            "created_by": row.get("created_by"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    @router.patch("/workspaces/{workspace_id}")
    async def patch_workspace(
        workspace_id: str, body: WorkspacePatch, user=Depends(get_current_user)
    ):
        business_id = tenant_business_id(user)
        row = await db.business_workspaces.find_one(
            {"_id": workspace_id, "business_id": business_id}
        )
        if not row:
            raise HTTPException(404, "Workspace not found")
        if not _can_manage_collab_settings(check_permission, user) and row.get("created_by") != str(
            user["_id"]
        ):
            raise HTTPException(403, "Only the creator or a manager can edit this workspace")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if body.name is not None:
            upd["name"] = body.name.strip()
        if body.description is not None:
            upd["description"] = body.description.strip()
        if body.member_user_ids is not None:
            if not _can_manage_collab_settings(check_permission, user):
                raise HTTPException(403, "Only managers can change workspace members")
            upd["member_user_ids"] = body.member_user_ids
        if body.linked_conversation_id is not None:
            upd["linked_conversation_id"] = body.linked_conversation_id
        await db.business_workspaces.update_one({"_id": workspace_id}, {"$set": upd})
        return {"status": "ok"}

    @router.post("/workspaces/{workspace_id}/assets")
    async def add_workspace_asset(
        workspace_id: str,
        payload: Dict[str, Any],
        user=Depends(get_current_user),
    ):
        business_id = tenant_business_id(user)
        row = await db.business_workspaces.find_one(
            {"_id": workspace_id, "business_id": business_id}
        )
        if not row or not _workspace_visible(row, user, check_permission):
            raise HTTPException(404, "Workspace not found")
        asset = {
            "id": str(uuid.uuid4()),
            "type": str(payload.get("type") or "link"),
            "title": str(payload.get("title") or "")[:200],
            "url": str(payload.get("url") or "")[:2000],
            "note": str(payload.get("note") or "")[:5000],
            "created_at": datetime.utcnow().isoformat(),
            "created_by": str(user["_id"]),
        }
        await db.business_workspaces.update_one(
            {"_id": workspace_id},
            {"$push": {"assets": asset}, "$set": {"updated_at": datetime.utcnow()}},
        )
        return {"asset": asset}

    @router.delete("/workspaces/{workspace_id}")
    async def delete_workspace(workspace_id: str, user=Depends(get_current_user)):
        business_id = tenant_business_id(user)
        row = await db.business_workspaces.find_one(
            {"_id": workspace_id, "business_id": business_id}
        )
        if not row:
            raise HTTPException(404, "Workspace not found")
        if not _can_manage_collab_settings(check_permission, user) and row.get("created_by") != str(
            user["_id"]
        ):
            raise HTTPException(403, "Only the creator or a manager can delete this workspace")
        await db.business_workspaces.delete_one({"_id": workspace_id})
        return {"status": "deleted"}

    @router.get("/channel-access")
    async def get_channel_access(user=Depends(get_current_user)):
        if not _can_manage_collab_settings(check_permission, user):
            raise HTTPException(403, "Managers and owners can view channel access")
        business_id = tenant_business_id(user)
        grants = await list_grants_matrix(db, business_id)
        return {
            "channels": list(CANONICAL_CHANNELS),
            "grants": grants,
            "hint": "Leave grants empty to allow full access for everyone (default). "
            "Once you add any grant, the matrix applies to social actions in the CRM.",
        }

    @router.put("/channel-access")
    async def put_channel_access(body: ChannelAccessPut, user=Depends(get_current_user)):
        if not _can_manage_collab_settings(check_permission, user):
            raise HTTPException(403, "Only managers and owners can update channel access")
        business_id = tenant_business_id(user)
        await replace_grants(db, business_id, [g.model_dump() for g in body.grants])
        return {"status": "ok", "count": len(body.grants)}

    @router.get("/inbound-routing")
    async def get_inbound_routing(user=Depends(get_current_user)):
        if not _can_manage_collab_settings(check_permission, user):
            raise HTTPException(403, "Managers and owners can view routing")
        business_id = tenant_business_id(user)
        row = await db.business_inbound_routing.find_one({"business_id": business_id})
        if not row:
            return {
                "enabled": False,
                "replace_existing": False,
                "default_assignee": "owner",
                "rules": [],
            }
        return {
            "enabled": bool(row.get("enabled")),
            "replace_existing": bool(row.get("replace_existing")),
            "default_assignee": row.get("default_assignee") or "owner",
            "rules": row.get("rules") or [],
        }

    @router.put("/inbound-routing")
    async def put_inbound_routing(body: InboundRoutingPut, user=Depends(get_current_user)):
        if not _can_manage_collab_settings(check_permission, user):
            raise HTTPException(403, "Only managers and owners can update routing")
        business_id = tenant_business_id(user)
        rules_out: List[Dict[str, Any]] = []
        for r in body.rules:
            rid = r.id or str(uuid.uuid4())
            rules_out.append(
                {
                    "id": rid,
                    "name": r.name,
                    "enabled": r.enabled,
                    "keywords": [str(k).strip() for k in r.keywords if str(k).strip()],
                    "channels": r.channels or ["whatsapp", "social", "email"],
                    "assignee_user_id": str(r.assignee_user_id).strip(),
                }
            )
        await db.business_inbound_routing.update_one(
            {"business_id": business_id},
            {
                "$set": {
                    "business_id": business_id,
                    "enabled": body.enabled,
                    "replace_existing": body.replace_existing,
                    "default_assignee": body.default_assignee or "owner",
                    "rules": rules_out,
                    "updated_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )
        return {"status": "ok"}

    @router.post("/inbound-routing/preview")
    async def preview_inbound_routing(body: InboundPreviewBody, user=Depends(get_current_user)):
        if not _can_manage_collab_settings(check_permission, user):
            raise HTTPException(403, "Managers and owners can preview routing")
        business_id = tenant_business_id(user)
        row = await db.business_inbound_routing.find_one({"business_id": business_id})
        rules = (row or {}).get("rules") or []
        assignee, rule_name = match_routing_rules(body.text, body.subject, body.channel, rules)
        default_assignee = (row or {}).get("default_assignee") if row else "owner"
        if not assignee:
            assignee = business_id if default_assignee in (None, "", "owner") else str(default_assignee)
        return {
            "assignee_user_id": assignee,
            "matched_rule": rule_name,
            "used_default": rule_name is None,
        }

    return router

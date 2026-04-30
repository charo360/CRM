"""Agent Workspace — shared per-conversation state across agent switches.

Agents are stateless by design, but multi-turn workflows (e.g. Meta Ads →
Creative → Broadcasts) benefit from a shared brief that carries forward
key facts decided in earlier agent sessions.

Schema (assistant_agent_workspace collection):
  {
    "_id": "<conversation_id>",
    "user_id": "<user_id>",
    "product": "<last approved product name>",
    "platform": "<last chosen platform>",
    "campaign_goal": "<e.g. awareness / conversions>",
    "target_audience": "<user-described audience>",
    "approved_copy": "<last approved headline/copy>",
    "brand_color": "<hex color from owner info>",
    "notes": "<free-form agent context, max 400 chars>",
    "last_agent": "<agent_id that last wrote>",
    "updated_at": <timestamp>,
  }

Usage:
  ws = await load_workspace(db, conversation_id)
  await update_workspace(db, conversation_id, user_id, {"product": "Air Max"})
  context_line = workspace_to_context_line(ws)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Fields the workspace tracks.  Only non-empty values are written.
_WORKSPACE_FIELDS = frozenset({
    "product",
    "platform",
    "campaign_goal",
    "target_audience",
    "approved_copy",
    "brand_color",
    "notes",
    "last_agent",
})


async def load_workspace(db, conversation_id: str) -> Dict[str, Any]:
    """Return the workspace for a conversation, or an empty dict if none exists."""
    if not conversation_id:
        return {}
    try:
        doc = await db.assistant_agent_workspace.find_one({"_id": conversation_id})
        return doc or {}
    except Exception as exc:
        logger.debug("[workspace] load failed (non-critical): %s", exc)
        return {}


async def update_workspace(
    db,
    conversation_id: str,
    user_id: str,
    fields: Dict[str, Any],
    agent_id: Optional[str] = None,
) -> None:
    """Upsert workspace fields for a conversation.  Only writes non-None values."""
    if not conversation_id or not fields:
        return
    try:
        updates: Dict[str, Any] = {
            k: v for k, v in fields.items()
            if k in _WORKSPACE_FIELDS and v is not None and v != ""
        }
        if not updates:
            return
        updates["updated_at"] = time.time()
        if agent_id:
            updates["last_agent"] = agent_id
        await db.assistant_agent_workspace.update_one(
            {"_id": conversation_id},
            {"$set": {**updates, "user_id": user_id}},
            upsert=True,
        )
    except Exception as exc:
        logger.debug("[workspace] update failed (non-critical): %s", exc)


def workspace_to_context_line(ws: Dict[str, Any]) -> str:
    """Return a compact system message summarising the shared workspace.

    Injected near the top of the system prompt when switching agents so the
    incoming agent instantly knows what was decided in prior sessions.
    """
    if not ws:
        return ""
    parts = []
    if ws.get("product"):
        parts.append(f"product: {ws['product']}")
    if ws.get("platform"):
        parts.append(f"platform: {ws['platform']}")
    if ws.get("campaign_goal"):
        parts.append(f"goal: {ws['campaign_goal']}")
    if ws.get("target_audience"):
        parts.append(f"audience: {ws['target_audience']}")
    if ws.get("approved_copy"):
        copy_preview = ws["approved_copy"][:120]
        parts.append(f"approved copy: \"{copy_preview}\"")
    if ws.get("brand_color"):
        parts.append(f"brand color: {ws['brand_color']}")
    if ws.get("notes"):
        parts.append(f"notes: {ws['notes'][:200]}")
    if not parts:
        return ""
    last = ws.get("last_agent", "")
    prefix = f"[Shared context from {last} agent] " if last else "[Shared context] "
    return prefix + " | ".join(parts)

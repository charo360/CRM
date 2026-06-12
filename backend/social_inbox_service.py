"""Unified social inbox — Composio (FB/IG) + Unipile (LinkedIn)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import composio_inbox
import unipile_inbox

logger = logging.getLogger(__name__)


async def list_conversations(
    db,
    user: Dict[str, Any],
    *,
    platform: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    business_id = str(user.get("business_id") or user["_id"])
    plat = (platform or "").strip().lower()
    conversations: List[Dict[str, Any]] = []

    async def _composio() -> List[Dict[str, Any]]:
        if plat and plat not in ("facebook", "instagram"):
            return []
        try:
            check = plat or None
            return await composio_inbox.list_conversations(business_id, check)
        except Exception as exc:
            logger.warning("[social-inbox] composio list failed: %s", exc)
            return []

    async def _unipile() -> List[Dict[str, Any]]:
        if plat and plat not in ("linkedin", "linkedin_messaging"):
            return []
        if not unipile_inbox.is_available():
            return []
        try:
            return await unipile_inbox.list_conversations(db, user["_id"], business_id)
        except Exception as exc:
            logger.warning("[social-inbox] unipile list failed: %s", exc)
            return []

    composio_convs, unipile_convs = await asyncio.gather(_composio(), _unipile())
    conversations.extend(composio_convs)
    conversations.extend(unipile_convs)

    conversations.sort(key=lambda c: c.get("last_message_at") or "", reverse=True)
    return conversations[:limit]

"""Snapshot which data sources are active for this business."""

from __future__ import annotations

from typing import Any


async def connected_sources_snapshot(db: Any, uid: str) -> dict[str, Any]:
    user = await db.users.find_one({"_id": uid}) or {}
    sources: list[str] = []

    if user.get("evolution_instance") or user.get("whatsapp_connected"):
        sources.append("whatsapp")
    if await db.email_messages.count_documents({"user_id": uid}, limit=1):
        sources.append("email")
    if await db.messages.count_documents({"user_id": uid}, limit=1):
        sources.append("messages")
    if await db.zilo_scouts.count_documents({"user_id": uid, "is_active": True}):
        sources.append("zilo_scout")
    soc = await db.action_mode_social.find_one({"user_id": uid}) or {}
    if any((soc.get("keywords") or [])):
        sources.append("social")
    if user.get("shopify_shop") or user.get("shopify_access_token"):
        sources.append("shopify")
    if await db.customers.count_documents({"user_id": uid, "is_customer": True}, limit=1):
        sources.append("crm")

    return {"connected": sources, "count": len(sources)}

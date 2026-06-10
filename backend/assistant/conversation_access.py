"""Zilo chat visibility: team-wide vs private + shared collaborators."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def tenant_user_id(user: Dict[str, Any]) -> str:
    """Business tenant key (same as assistant conversation `user_id` field)."""
    return str(user.get("business_id") or user["_id"])


def tenant_user_ids(user: Dict[str, Any]) -> List[str]:
    """All ids that may own a conversation row (legacy chats used account `_id` only)."""
    bid = tenant_user_id(user)
    uid = str(user["_id"])
    if uid == bid:
        return [bid]
    return [bid, uid]


def conversation_list_filter(user: Dict[str, Any]) -> Dict[str, Any]:
    """Mongo filter: conversations this user may see."""
    uid = str(user["_id"])
    return {
        "user_id": {"$in": tenant_user_ids(user)},
        "$or": [
            {"visibility": {"$nin": ["private"]}},
            {"visibility": {"$exists": False}},
            {"created_by": uid},
            {"shared_with": uid},
        ],
    }


def can_access_conversation_row(row: Optional[Dict[str, Any]], user: Dict[str, Any]) -> bool:
    if not row:
        return False
    if str(row.get("user_id")) not in tenant_user_ids(user):
        return False
    vis = row.get("visibility") or "team"
    if vis != "private":
        return True
    uid = str(user["_id"])
    if str(row.get("created_by") or "") == uid:
        return True
    shared = row.get("shared_with") or []
    return uid in [str(x) for x in shared]


def serialize_conversation_meta(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "visibility": row.get("visibility") or "team",
        "shared_with": list(row.get("shared_with") or []),
        "created_by": row.get("created_by"),
    }

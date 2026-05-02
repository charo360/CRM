"""Per-channel access for business social integrations (optional matrix)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException

LEVEL_RANK: Dict[str, int] = {"off": 0, "read": 1, "reply": 2, "admin": 3}

CANONICAL_CHANNELS = (
    "whatsapp",
    "telegram",
    "facebook",
    "instagram",
    "twitter",
    "email_support",
    "social",
)


def tenant_business_id(user: Dict[str, Any]) -> str:
    return str(user.get("business_id") or user["_id"])


def user_bypasses_channel_matrix(user: Dict[str, Any]) -> bool:
    """Owners and managers ignore the matrix when it is enabled."""
    if not user.get("role") and not user.get("business_id"):
        return True
    role = (user.get("role") or "employee").lower()
    return role in ("owner", "manager")


async def channel_matrix_enabled(db, business_id: str) -> bool:
    n = await db.channel_access_grants.count_documents({"business_id": business_id}, limit=1)
    return n > 0


async def effective_channel_level(db, business_id: str, user_id: str, channel: str) -> int:
    ch = (channel or "social").lower().strip()
    doc = await db.channel_access_grants.find_one(
        {"business_id": business_id, "user_id": user_id, "channel": ch}
    )
    if doc:
        return LEVEL_RANK.get(str(doc.get("level") or "off").lower(), 0)
    doc2 = await db.channel_access_grants.find_one(
        {"business_id": business_id, "user_id": user_id, "channel": "social"}
    )
    if doc2:
        return LEVEL_RANK.get(str(doc2.get("level") or "off").lower(), 0)
    return 0


def _normalize_platform(platform: Optional[str]) -> str:
    p = (platform or "").lower().strip()
    mapping = {
        "fb": "facebook",
        "ig": "instagram",
        "x": "twitter",
        "messenger": "facebook",
    }
    return mapping.get(p, p) if p else "social"


async def require_social_channel_level(
    db,
    user: Dict[str, Any],
    platform: Optional[str],
    need: str,
) -> None:
    """Raise 403 if the user cannot perform `need` on this social platform."""
    if user_bypasses_channel_matrix(user):
        return
    bid = tenant_business_id(user)
    if not await channel_matrix_enabled(db, bid):
        return
    need_rank = LEVEL_RANK.get(need, 2)
    ch = _normalize_platform(platform)
    if ch not in CANONICAL_CHANNELS:
        ch = "social"
    uid = str(user["_id"])
    lvl = await effective_channel_level(db, bid, uid, ch)
    lvl = max(lvl, await effective_channel_level(db, bid, uid, "social"))
    if lvl < need_rank:
        raise HTTPException(
            status_code=403,
            detail="Your role does not allow this action on this channel. "
            "Ask an owner or manager to update Collaboration → Channel access.",
        )


async def list_grants_matrix(db, business_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    async for row in db.channel_access_grants.find({"business_id": business_id}):
        out.append(
            {
                "user_id": row.get("user_id"),
                "channel": row.get("channel"),
                "level": row.get("level") or "off",
            }
        )
    return out


async def replace_grants(
    db,
    business_id: str,
    grants: List[Dict[str, Any]],
) -> None:
    await db.channel_access_grants.delete_many({"business_id": business_id})
    now = __import__("datetime").datetime.utcnow()
    for g in grants:
        uid = str(g.get("user_id") or "").strip()
        ch = str(g.get("channel") or "").strip().lower()
        lvl = str(g.get("level") or "off").lower()
        if not uid or ch not in CANONICAL_CHANNELS:
            continue
        if lvl not in LEVEL_RANK:
            lvl = "off"
        await db.channel_access_grants.insert_one(
            {
                "business_id": business_id,
                "user_id": uid,
                "channel": ch,
                "level": lvl,
                "updated_at": now,
            }
        )

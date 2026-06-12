"""Connected social accounts from Composio + Unipile (no Zernio)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from composio_service import (
    TOOLKIT_FACEBOOK,
    TOOLKIT_INSTAGRAM,
    TOOLKIT_LINKEDIN,
    TOOLKIT_TIKTOK,
    TOOLKIT_TWITTER,
    TOOLKIT_YOUTUBE,
    get_connection_status,
)
from unipile_service import get_connection_status as unipile_linkedin_status


_PLATFORM_TOOLKITS = [
    ("facebook", TOOLKIT_FACEBOOK),
    ("instagram", TOOLKIT_INSTAGRAM),
    ("youtube", TOOLKIT_YOUTUBE),
    ("linkedin", TOOLKIT_LINKEDIN),
    ("twitter", TOOLKIT_TWITTER),
    ("x", TOOLKIT_TWITTER),
    ("tiktok", TOOLKIT_TIKTOK),
]


def _account_entry(
    *,
    platform: str,
    connection_id: str,
    name: str = "",
    username: str = "",
) -> Dict[str, Any]:
    return {
        "id": connection_id,
        "_id": connection_id,
        "accountId": connection_id,
        "account_id": connection_id,
        "platform": platform,
        "name": name or platform.title(),
        "username": username,
        "displayName": name or username or platform.title(),
    }


async def list_connected_accounts(db, user: Dict[str, Any]) -> List[Dict[str, Any]]:
    business_id = str(user.get("business_id") or user["_id"])
    accounts: List[Dict[str, Any]] = []
    seen_platforms: set[str] = set()

    for platform, toolkit in _PLATFORM_TOOLKITS:
        if platform in seen_platforms:
            continue
        status = await get_connection_status(business_id, toolkit)
        if not status.get("connected"):
            continue
        conn_id = status.get("connection_id") or f"ca_{platform}"
        accounts.append(
            _account_entry(
                platform=platform if platform != "x" else "twitter",
                connection_id=str(conn_id),
                name=f"{platform.title()} (Composio)",
            )
        )
        seen_platforms.add(platform)
        if platform == "twitter":
            seen_platforms.add("x")

    li_msg = await unipile_linkedin_status(db, user["_id"], business_id)
    if li_msg.get("connected") and li_msg.get("account_id"):
        accounts.append(
            _account_entry(
                platform="linkedin_messaging",
                connection_id=str(li_msg["account_id"]),
                name=str(li_msg.get("name") or "LinkedIn DMs"),
                username="unipile",
            )
        )

    return accounts


async def has_social_connection(db, user: Dict[str, Any]) -> bool:
    accounts = await list_connected_accounts(db, user)
    return len(accounts) > 0

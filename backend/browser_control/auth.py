"""JWT helpers for Zilo Browser Operator WebSocket auth."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
BROWSER_WS_TOKEN_HOURS = int(os.environ.get("BROWSER_WS_TOKEN_HOURS", "168"))


def resolve_browser_user_id(user: dict[str, Any]) -> str:
    """Stable id shared by CRM tools, status API, and the extension session."""
    return str(user.get("business_id") or user.get("_id") or "")


def create_browser_ws_token(user_id: str, *, hours: int | None = None) -> str:
    ttl = hours if hours is not None else BROWSER_WS_TOKEN_HOURS
    payload = {
        "user_id": str(user_id),
        "kind": "browser_ws",
        "exp": datetime.utcnow() + timedelta(hours=ttl),
    }
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_browser_ws_token(token: str, expected_user_id: str) -> bool:
    if not token or not JWT_SECRET:
        return False
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("kind") != "browser_ws":
            return False
        return str(payload.get("user_id")) == str(expected_user_id)
    except jwt.PyJWTError:
        return False

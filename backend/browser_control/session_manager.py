"""In-memory + Mongo session tracking for Browser Operator connections."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MIN = 5
COLLECTION = "browser_sessions"

_ACTIVE: dict[str, "BrowserSession"] = {}


@dataclass
class BrowserSession:
    user_id: str
    session_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_command_at: datetime = field(default_factory=datetime.utcnow)
    allowed_domains: list[str] = field(default_factory=list)

    def touch(self) -> None:
        self.last_command_at = datetime.utcnow()

    def is_stale(self, *, timeout_min: int = SESSION_TIMEOUT_MIN) -> bool:
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_min)
        return self.last_command_at < cutoff

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "connected_at": self.connected_at.isoformat() + "Z",
            "last_command_at": self.last_command_at.isoformat() + "Z",
            "allowed_domains": self.allowed_domains,
        }


def register_session(
    user_id: str,
    websocket: WebSocket,
    *,
    allowed_domains: list[str] | None = None,
) -> BrowserSession:
    session = BrowserSession(
        user_id=str(user_id),
        session_id=str(uuid.uuid4()),
        websocket=websocket,
        allowed_domains=list(allowed_domains or []),
    )
    _ACTIVE[str(user_id)] = session
    return session


def get_session(user_id: str) -> BrowserSession | None:
    return _ACTIVE.get(str(user_id))


def remove_session(user_id: str) -> None:
    _ACTIVE.pop(str(user_id), None)


def touch_session(user_id: str) -> None:
    session = _ACTIVE.get(str(user_id))
    if session:
        session.touch()


def is_connected(user_id: str) -> bool:
    return str(user_id) in _ACTIVE


def get_public_status(user_id: str) -> dict[str, Any]:
    session = _ACTIVE.get(str(user_id))
    if not session:
        return {"connected": False, "user_id": str(user_id)}
    return {"connected": True, **session.to_public_dict()}


async def persist_session(db: Any, session: BrowserSession) -> None:
    if db is None:
        return
    try:
        await db[COLLECTION].update_one(
            {"user_id": session.user_id},
            {
                "$set": {
                    "user_id": session.user_id,
                    "session_id": session.session_id,
                    "connected_at": session.connected_at,
                    "last_command_at": session.last_command_at,
                    "allowed_domains": session.allowed_domains,
                    "status": "connected",
                }
            },
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[browser-control] persist_session failed: %s", exc)


async def mark_disconnected(db: Any, user_id: str) -> None:
    if db is None:
        return
    try:
        await db[COLLECTION].update_one(
            {"user_id": str(user_id)},
            {
                "$set": {
                    "status": "disconnected",
                    "disconnected_at": datetime.utcnow(),
                }
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[browser-control] mark_disconnected failed: %s", exc)


async def cleanup_stale_sessions(db: Any | None = None) -> int:
    """Drop idle in-memory sessions older than SESSION_TIMEOUT_MIN."""
    removed = 0
    stale_ids: list[str] = []
    for uid, session in list(_ACTIVE.items()):
        if session.is_stale():
            stale_ids.append(uid)
    for uid in stale_ids:
        session = _ACTIVE.pop(uid, None)
        if session:
            removed += 1
            try:
                await session.websocket.close(code=4000, reason="Session timed out")
            except Exception:
                pass
            if db is not None:
                await mark_disconnected(db, uid)
    if removed:
        logger.info("[browser-control] cleaned up %d stale session(s)", removed)
    return removed

"""
Zilo AI Browser Control WebSocket Router.
Manages active WebSocket sessions for the Zilo Browser Operator extension.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from browser_control.auth import verify_browser_ws_token
from browser_control.session_manager import (
    cleanup_stale_sessions,
    get_public_status,
    get_session,
    is_connected,
    mark_disconnected,
    persist_session,
    register_session,
    remove_session,
    touch_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browser", tags=["browser-control"])

_OUTSTANDING_COMMANDS: Dict[str, asyncio.Future] = {}
_db: Any | None = None
_cleanup_task: asyncio.Task | None = None


def init_browser_control(db: Any) -> None:
    """Call once at app startup so sessions can be persisted."""
    global _db
    _db = db


def _ensure_cleanup_loop() -> None:
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        return

    async def _loop() -> None:
        while True:
            await asyncio.sleep(60)
            await cleanup_stale_sessions(_db)

    _cleanup_task = asyncio.create_task(_loop())


@router.websocket("/ws/{user_id}")
async def browser_websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(default=""),
):
    """Duplex channel between backend and the user's Browser Operator extension."""
    if not token or not verify_browser_ws_token(token, user_id):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    session = register_session(user_id, websocket)
    await persist_session(_db, session)
    _ensure_cleanup_loop()
    logger.info(
        "🌐 [browser-control] Connected session user=%s session=%s",
        user_id,
        session.session_id,
    )

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
                command_id = data.get("commandId")
                if command_id and command_id in _OUTSTANDING_COMMANDS:
                    future = _OUTSTANDING_COMMANDS[command_id]
                    if not future.done():
                        future.set_result(data.get("result", {}))
                    _OUTSTANDING_COMMANDS.pop(command_id, None)
                    touch_session(user_id)
            except Exception as parse_err:  # noqa: BLE001
                logger.warning("[browser-control] Failed to parse extension message: %s", parse_err)
    except WebSocketDisconnect:
        logger.info("🌐 [browser-control] Disconnected session for user: %s", user_id)
    finally:
        remove_session(user_id)
        await mark_disconnected(_db, user_id)


async def send_browser_command(
    user_id: str,
    action: str,
    *,
    selector: str | None = None,
    text: str | None = None,
    url: str | None = None,
    data_type: str | None = None,
    timeout_sec: float = 20.0,
) -> Dict[str, Any]:
    """Send an automation command to the connected extension and await the result."""
    session = get_session(str(user_id))
    if not session:
        return {"error": "Browser Operator extension is not connected. Install it from Integrations and click Connect."}

    websocket = session.websocket
    command_id = str(uuid.uuid4())
    command_payload = {
        "id": command_id,
        "action": action,
        "selector": selector,
        "text": text,
        "url": url,
        "data_type": data_type,
    }

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    _OUTSTANDING_COMMANDS[command_id] = future

    try:
        await websocket.send_text(json.dumps(command_payload))
        touch_session(str(user_id))
        result = await asyncio.wait_for(future, timeout=timeout_sec)
        touch_session(str(user_id))
        if _db is not None:
            await persist_session(_db, session)
        return result
    except asyncio.TimeoutError:
        logger.warning("[browser-control] Command %s timed out for user %s", action, user_id)
        _OUTSTANDING_COMMANDS.pop(command_id, None)
        return {"error": f"Browser command timed out after {timeout_sec}s."}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[browser-control] Failed to execute browser command: %s", exc)
        _OUTSTANDING_COMMANDS.pop(command_id, None)
        return {"error": f"Browser control failure: {str(exc)}"}


def is_browser_connected(user_id: str) -> bool:
    return is_connected(str(user_id))


def browser_status_payload(user_id: str) -> dict[str, Any]:
    return get_public_status(str(user_id))

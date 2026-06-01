"""
Zilo AI Browser Control WebSocket Router.
Manages active WebSocket sessions for the Zilo Browser Companion extension.
"""
from __future__ import annotations

import json
import uuid
import logging
import asyncio
from typing import Any, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browser", tags=["browser-control"])

# Active session pool mapping user_id -> WebSocket
_ACTIVE_SESSIONS: Dict[str, WebSocket] = {}

# Outstanding command futures mapping command_id -> asyncio.Future
_OUTSTANDING_COMMANDS: Dict[str, asyncio.Future] = {}


@router.websocket("/ws/{user_id}")
async def browser_websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    FastAPI WebSocket endpoint for Zilo Browser extension.
    Establishes real-time duplex channel with the user's browser context.
    """
    await websocket.accept()
    logger.info(f"🌐 [browser-control] Connected session for user: {user_id}")
    
    # Store in connection pool
    _ACTIVE_SESSIONS[user_id] = websocket

    try:
        while True:
            # We await messages from the extension (mostly command execution results)
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
                command_id = data.get("commandId")
                
                # If we have a pending future waiting for this result, complete it!
                if command_id and command_id in _OUTSTANDING_COMMANDS:
                    future = _OUTSTANDING_COMMANDS[command_id]
                    if not future.done():
                        future.set_result(data.get("result", {}))
                    _OUTSTANDING_COMMANDS.pop(command_id, None)
            except Exception as parse_err:
                logger.warning(f"[browser-control] Failed to parse extension message: {parse_err}")

    except WebSocketDisconnect:
        logger.info(f"🌐 [browser-control] Disconnected session for user: {user_id}")
    finally:
        _ACTIVE_SESSIONS.pop(user_id, None)


async def send_browser_command(
    user_id: str,
    action: str,
    *,
    selector: str | None = None,
    text: str | None = None,
    url: str | None = None,
    data_type: str | None = None,
    timeout_sec: float = 20.0
) -> Dict[str, Any]:
    """
    Send an automation command to the user's connected Chrome extension,
    awaits the command's execution result from the content script, and returns it.
    """
    websocket = _ACTIVE_SESSIONS.get(user_id)
    if not websocket:
        return {"error": "Browser companion extension is not currently connected."}

    command_id = str(uuid.uuid4())
    command_payload = {
        "id": command_id,
        "action": action,
        "selector": selector,
        "text": text,
        "url": url,
        "data_type": data_type
    }

    # Create outstanding future to wait on async response
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    _OUTSTANDING_COMMANDS[command_id] = future

    try:
        # Deliver command via socket
        await websocket.send_text(json.dumps(command_payload))
        
        # Await completion or timeout
        result = await asyncio.wait_for(future, timeout=timeout_sec)
        return result
    except asyncio.TimeoutError:
        logger.warning(f"[browser-control] Command {action} timed out for user {user_id}")
        _OUTSTANDING_COMMANDS.pop(command_id, None)
        return {"error": f"Browser command timed out after {timeout_sec}s."}
    except Exception as exc:
        logger.exception(f"[browser-control] Failed to execute browser command: {exc}")
        _OUTSTANDING_COMMANDS.pop(command_id, None)
        return {"error": f"Browser control failure: {str(exc)}"}


def is_browser_connected(user_id: str) -> bool:
    """Check if the user has an active connected browser extension session."""
    return user_id in _ACTIVE_SESSIONS

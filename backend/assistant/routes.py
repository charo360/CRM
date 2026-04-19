"""FastAPI endpoints for the AI assistant."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from .models import DEFAULT_MODEL, list_available_models
from .orchestrator import run_turn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _mk_router(db, get_current_user):
    """Factory — binds db + auth dep into the router. Call this from server.py."""

    @router.get("/models")
    async def models(user=Depends(get_current_user)):
        return {"default": DEFAULT_MODEL, "models": list_available_models()}

    @router.get("/conversations")
    async def list_conversations(user=Depends(get_current_user)):
        user_id = user.get("business_id", user["_id"])
        rows = await db.assistant_conversations.find(
            {"user_id": user_id}
        ).sort("updated_at", -1).to_list(50)
        return [{
            "id": r["_id"],
            "title": r.get("title") or "New chat",
            "updated_at": r.get("updated_at"),
            "message_count": len(r.get("messages") or []),
        } for r in rows]

    @router.get("/conversations/{conv_id}")
    async def get_conversation(conv_id: str, user=Depends(get_current_user)):
        user_id = user.get("business_id", user["_id"])
        row = await db.assistant_conversations.find_one({"_id": conv_id, "user_id": user_id})
        if not row:
            raise HTTPException(404, "Conversation not found")
        return {
            "id": row["_id"],
            "title": row.get("title") or "New chat",
            "model": row.get("model"),
            "messages": row.get("messages") or [],
        }

    @router.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: str, user=Depends(get_current_user)):
        user_id = user.get("business_id", user["_id"])
        await db.assistant_conversations.delete_one({"_id": conv_id, "user_id": user_id})
        return {"status": "deleted"}

    @router.post("/chat")
    async def chat(req: Request, user=Depends(get_current_user)):
        """Send one turn. Body:
        {
            "conversation_id": "..." | null,   // if null a new one is created
            "message": "hi",
            "model": "gpt-4o-mini",            // optional
            "auto_approve": false              // optional — skip confirm gate
        }
        Returns: { conversation_id, reply, steps, model, needs_confirmation }
        """
        body = await req.json()
        msg = (body.get("message") or "").strip()
        if not msg:
            raise HTTPException(400, "message is required")

        user_id = user.get("business_id", user["_id"])
        conv_id = body.get("conversation_id")
        conv: Dict[str, Any]
        if conv_id:
            conv = await db.assistant_conversations.find_one({"_id": conv_id, "user_id": user_id})
            if not conv:
                raise HTTPException(404, "Conversation not found")
        else:
            conv_id = str(uuid.uuid4())
            conv = {
                "_id": conv_id,
                "user_id": user_id,
                "title": msg[:60],
                "model": body.get("model") or DEFAULT_MODEL,
                "messages": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            await db.assistant_conversations.insert_one(conv)

        history: List[Dict[str, Any]] = conv.get("messages") or []
        # Strip non-serializable keys from history before passing to LLM
        clean_history = [_strip_storage_fields(m) for m in history]

        try:
            result = await run_turn(
                db=db,
                user=user,
                history=clean_history,
                user_message=msg,
                model_id=body.get("model") or conv.get("model") or DEFAULT_MODEL,
                auto_approve_destructive=bool(body.get("auto_approve")),
            )
        except Exception as e:
            logger.exception("[assistant.chat] failure")
            raise HTTPException(500, f"Assistant error: {e}")

        # Persist the new messages + step trace
        new_msgs = result["messages_to_append"]
        # Attach tool-trace to the last assistant message for UI display
        if result.get("steps") and new_msgs and new_msgs[-1].get("role") == "assistant":
            new_msgs[-1]["steps"] = result["steps"]
        await db.assistant_conversations.update_one(
            {"_id": conv_id, "user_id": user_id},
            {
                "$push": {"messages": {"$each": new_msgs}},
                "$set": {
                    "updated_at": datetime.utcnow(),
                    "model": result.get("model") or conv.get("model"),
                    "title": conv.get("title") or msg[:60],
                },
            },
        )

        return {
            "conversation_id": conv_id,
            "reply": result["reply"],
            "steps": result.get("steps") or [],
            "model": result.get("model"),
            "needs_confirmation": result.get("needs_confirmation"),
        }

    return router


def _strip_storage_fields(m: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in m.items() if k not in ("steps",)}
    return out

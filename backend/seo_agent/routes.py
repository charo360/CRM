"""FastAPI routes for the LangGraph SEO agent chat."""
from __future__ import annotations
import logging, uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

logger = logging.getLogger(__name__)


# ── Request / Response models ─────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str        # "user" | "assistant"
    content: str

class SEOChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    message: str
    conversation_id: Optional[str] = None
    history: List[ChatMessage] = []   # prior turns sent from the frontend

class SEOChatResponse(BaseModel):
    reply: str
    conversation_id: str
    tool_steps: List[Dict[str, Any]] = []   # what tools ran and their output snippets


def _tid(user): return user.get("business_id", user["_id"])

def _ser_msg(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    ts = doc.get("created_at")
    if ts and hasattr(ts, "isoformat"): doc["created_at"] = ts.isoformat()
    ts2 = doc.get("updated_at")
    if ts2 and hasattr(ts2, "isoformat"): doc["updated_at"] = ts2.isoformat()
    return doc


# ── Router factory ────────────────────────────────────────────────────────────

def make_seo_agent_router(db, user_dep):
    router = APIRouter(prefix="/seo-agent", tags=["seo-agent"])

    # Import lazy getter — graph compiles on first request so env vars are ready
    try:
        from .graph import get_seo_graph
    except Exception as _import_err:
        get_seo_graph = None  # type: ignore
        logger.error(f"[seo_agent] Graph import failed: {_import_err}")

    # ── POST /seo-agent/chat ──────────────────────────────────────────────────

    @router.post("/chat", response_model=SEOChatResponse)
    async def chat(payload: SEOChatRequest, user=user_dep):
        graph = get_seo_graph() if get_seo_graph else None
        if graph is None:
            raise HTTPException(503, "SEO agent is not available — check that OPENAI_API_KEY or ANTHROPIC_API_KEY is set.")

        tid = _tid(user)
        conv_id = payload.conversation_id or str(uuid.uuid4())

        # ── Rebuild message list from history + new user turn ─────────────────
        lc_messages = []
        for m in payload.history:
            if m.role == "user":
                lc_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                lc_messages.append(AIMessage(content=m.content))
        lc_messages.append(HumanMessage(content=payload.message))

        # ── Run the LangGraph (db + user_id injected via config) ─────────────
        try:
            result = await graph.ainvoke(
                {"messages": lc_messages},
                config={
                    "configurable": {"db": db, "user_id": tid},
                    "recursion_limit": 20,
                },
            )
        except Exception as e:
            logger.error(f"[seo_agent] Graph error: {e}", exc_info=True)
            raise HTTPException(500, f"Agent error: {e}")

        # ── Extract final reply and tool steps ────────────────────────────────
        reply = ""
        tool_steps: List[Dict[str, Any]] = []
        new_messages = result.get("messages", [])

        for msg in reversed(new_messages):
            if isinstance(msg, AIMessage) and msg.content:
                reply = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        for msg in new_messages:
            if isinstance(msg, ToolMessage):
                tool_steps.append({
                    "tool": msg.name if hasattr(msg, "name") else "tool",
                    "output": str(msg.content)[:500],
                })
            elif isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_steps.append({
                        "tool": tc.get("name", "unknown"),
                        "args": {k: v for k, v in (tc.get("args") or {}).items()
                                 if k not in ("config",)},
                    })

        # ── Persist conversation to db ────────────────────────────────────────
        try:
            existing = await db.seo_agent_conversations.find_one({"_id": conv_id, "user_id": tid})
            user_turn = {"role": "user", "content": payload.message, "ts": datetime.utcnow()}
            asst_turn = {"role": "assistant", "content": reply, "tool_steps": tool_steps, "ts": datetime.utcnow()}

            if existing:
                await db.seo_agent_conversations.update_one(
                    {"_id": conv_id},
                    {"$push": {"messages": {"$each": [user_turn, asst_turn]}},
                     "$set": {"updated_at": datetime.utcnow()}},
                )
            else:
                # Generate a title from the first user message
                short_title = payload.message[:60] + ("..." if len(payload.message) > 60 else "")
                await db.seo_agent_conversations.insert_one({
                    "_id": conv_id, "user_id": tid,
                    "title": short_title,
                    "messages": [user_turn, asst_turn],
                    "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
                })
        except Exception as db_err:
            logger.warning(f"[seo_agent] DB persist failed: {db_err}")

        return SEOChatResponse(reply=reply, conversation_id=conv_id, tool_steps=tool_steps)

    # ── GET /seo-agent/conversations ──────────────────────────────────────────

    @router.get("/conversations")
    async def list_conversations(user=user_dep):
        tid = _tid(user)
        docs = await db.seo_agent_conversations.find(
            {"user_id": tid},
            {"messages": 0},          # exclude message bodies for speed
        ).sort("updated_at", -1).limit(30).to_list(30)
        return [_ser_msg(d) for d in docs]

    # ── GET /seo-agent/conversations/{conv_id} ────────────────────────────────

    @router.get("/conversations/{conv_id}")
    async def get_conversation(conv_id: str, user=user_dep):
        tid = _tid(user)
        doc = await db.seo_agent_conversations.find_one({"_id": conv_id, "user_id": tid})
        if not doc:
            raise HTTPException(404, "Conversation not found")
        return _ser_msg(doc)

    # ── DELETE /seo-agent/conversations/{conv_id} ─────────────────────────────

    @router.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: str, user=user_dep):
        tid = _tid(user)
        result = await db.seo_agent_conversations.delete_one({"_id": conv_id, "user_id": tid})
        if result.deleted_count == 0:
            raise HTTPException(404, "Conversation not found")
        return {"ok": True}

    # ── GET /seo-agent/status ─────────────────────────────────────────────────

    @router.get("/status")
    async def status(_user=user_dep):
        g = get_seo_graph() if get_seo_graph else None
        from .tools import SEO_TOOLS
        return {
            "available": g is not None,
            "tools": [t.name for t in SEO_TOOLS],
        }

    return router

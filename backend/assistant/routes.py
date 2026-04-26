"""FastAPI endpoints for the AI assistant."""
from __future__ import annotations

import logging
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

import json
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .documents import delete_document, list_for_conversation, store_upload
from .agents import AGENT_REGISTRY, list_agents_public, resolve_agent_id
from .intent_router import route_to_agent
from .models import DEFAULT_MODEL, list_available_models
from .orchestrator import run_turn
from .titler import generate_title

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# ── Rate limit: 30 turns per 60 seconds per user ─────────────────────────────
_RATE_WINDOW_SEC = 60
_RATE_MAX = 30
_rate_hits: Dict[str, Deque[float]] = defaultdict(deque)


def _check_rate_limit(user_id: str) -> None:
    now = time.time()
    dq = _rate_hits[user_id]
    while dq and now - dq[0] > _RATE_WINDOW_SEC:
        dq.popleft()
    if len(dq) >= _RATE_MAX:
        retry = int(_RATE_WINDOW_SEC - (now - dq[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Too many assistant requests. Try again in {retry}s.",
        )
    dq.append(now)


def _mk_router(db, get_current_user):
    """Factory — binds db + auth dep into the router. Call this from server.py."""

    @router.get("/models")
    async def models(user=Depends(get_current_user)):
        payload = {"default": DEFAULT_MODEL, "models": list_available_models()}
        return JSONResponse(
            payload,
            headers={"Cache-Control": "no-store, must-revalidate"},
        )

    @router.get("/agents")
    async def agents_list(user=Depends(get_current_user)):
        """Specialist agents (e.g. Meta Ads) — each uses a dedicated prompt and tool set."""
        return {"agents": list_agents_public()}

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
            "agent": r.get("agent") or "general",
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
            "agent": row.get("agent") or "general",
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
            "auto_approve": false,             // optional — skip confirm gate
            "agent": "general" | "meta_ads" | "google_ads" | "x_ads"   // optional — specialist; locked after first message
        }
        Returns: { conversation_id, reply, steps, model, needs_confirmation }
        """
        body = await req.json()
        msg = (body.get("message") or "").strip()
        if not msg:
            raise HTTPException(400, "message is required")

        user_id = user.get("business_id", user["_id"])
        _check_rate_limit(user_id)
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
                "agent": "general",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            await db.assistant_conversations.insert_one(conv)

        history: List[Dict[str, Any]] = conv.get("messages") or []
        # Route to the best specialist — sticky for continuation messages.
        # If a design flow is in progress (flow_step set and not 'done'), force
        # design agent regardless of keywords — design is multi-turn stateful.
        prev_agent = conv.get("agent") or None
        design_flow_active = False
        if "creative" in AGENT_REGISTRY or "design" in AGENT_REGISTRY:
            try:
                from .design_state import load_design_state
                _ds = await load_design_state(db, conv_id, user_id)
                _step = _ds.get("flow_step")
                design_flow_active = bool(_step and _step != "done")
            except Exception:
                pass
        agent_resolved = await route_to_agent(
            msg, history, AGENT_REGISTRY,
            prev_agent=prev_agent,
            design_flow_active=design_flow_active,
        )

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
                conversation_id=conv_id,
                agent_id=agent_resolved,
            )
        except Exception as e:
            logger.exception("[assistant.chat] failure")
            raise HTTPException(500, f"Assistant error: {e}")

        active_agent = result.get("active_agent") or agent_resolved

        # Persist the new messages + step trace
        new_msgs = result["messages_to_append"]
        # Attach tool-trace + agent badge to the last assistant message for UI display
        if new_msgs and new_msgs[-1].get("role") == "assistant":
            if result.get("steps"):
                new_msgs[-1]["steps"] = result["steps"]
            new_msgs[-1]["agent"] = active_agent

        # Smart title: generated once after the first reply (background, best-effort).
        is_first_turn = not conv.get("messages")
        current_title = conv.get("title") or msg[:60]
        reply_text = result.get("reply") or ""
        if is_first_turn and reply_text:
            import asyncio as _asyncio

            async def _update_title() -> None:
                try:
                    smart = await generate_title(msg, reply_text)
                    if smart:
                        await db.assistant_conversations.update_one(
                            {"_id": conv_id, "user_id": user_id},
                            {"$set": {"title": smart}},
                        )
                except Exception:
                    pass

            _asyncio.create_task(_update_title())

        try:
            await db.assistant_conversations.update_one(
                {"_id": conv_id, "user_id": user_id},
                {
                    "$push": {"messages": {"$each": new_msgs}},
                    "$set": {
                        "updated_at": datetime.utcnow(),
                        "model": result.get("model") or conv.get("model"),
                        "title": current_title,
                        "agent": active_agent,
                    },
                },
            )
        except Exception as db_exc:
            logger.exception("[assistant.chat] failed to save conversation messages")
            raise HTTPException(
                500,
                "Could not save this chat turn (payload may be too large). Try a shorter message or start a new chat.",
            ) from db_exc

        return {
            "conversation_id": conv_id,
            "reply": result["reply"],
            "steps": result.get("steps") or [],
            "model": result.get("model"),
            "needs_confirmation": result.get("needs_confirmation"),
            "active_agent": active_agent,
            "active_agent_label": AGENT_REGISTRY.get(active_agent, {}).get("label", "Zilo"),
            "reply_suggestions": result.get("reply_suggestions") or [],
        }

    @router.post("/chat/stream")
    async def chat_stream(req: Request, user=Depends(get_current_user)):
        """SSE wrapper around /chat for streaming UI. Emits JSON lines:
        {"type":"thinking"}, {"type":"token","text":"..."}, {"type":"done",...}
        """
        body = await req.json()
        msg = (body.get("message") or "").strip()
        if not msg:
            async def _err():
                yield "data: " + json.dumps({"type": "error", "message": "message is required"}) + "\n\n"
            return StreamingResponse(_err(), media_type="text/event-stream")

        user_id = user.get("business_id", user["_id"])

        async def _generate():
            try:
                _check_rate_limit(user_id)
            except HTTPException as e:
                yield "data: " + json.dumps({"type": "error", "message": e.detail}) + "\n\n"
                return

            conv_id = body.get("conversation_id")
            conv: Dict[str, Any]
            if conv_id:
                conv = await db.assistant_conversations.find_one({"_id": conv_id, "user_id": user_id})
                if not conv:
                    yield "data: " + json.dumps({"type": "error", "message": "Conversation not found"}) + "\n\n"
                    return
            else:
                conv_id = str(uuid.uuid4())
                conv = {
                    "_id": conv_id, "user_id": user_id, "title": msg[:60],
                    "model": body.get("model") or DEFAULT_MODEL,
                    "messages": [], "agent": "general",
                    "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
                }
                await db.assistant_conversations.insert_one(conv)

            history = [_strip_storage_fields(m) for m in (conv.get("messages") or [])]

            prev_agent = conv.get("agent") or None
            design_flow_active = False
            if "creative" in AGENT_REGISTRY or "design" in AGENT_REGISTRY:
                try:
                    from .design_state import load_design_state
                    _ds = await load_design_state(db, conv_id, user_id)
                    _step = _ds.get("flow_step")
                    design_flow_active = bool(_step and _step != "done")
                except Exception:
                    pass
            agent_resolved = await route_to_agent(
                msg, history, AGENT_REGISTRY,
                prev_agent=prev_agent, design_flow_active=design_flow_active,
            )
            agent_label = AGENT_REGISTRY.get(agent_resolved, {}).get("label", "Zilo")

            yield "data: " + json.dumps({"type": "thinking", "agent": agent_resolved, "agent_label": agent_label}) + "\n\n"

            try:
                result = await run_turn(
                    db=db, user=user, history=history, user_message=msg,
                    model_id=body.get("model") or conv.get("model") or DEFAULT_MODEL,
                    auto_approve_destructive=bool(body.get("auto_approve")),
                    conversation_id=conv_id, agent_id=agent_resolved,
                )
            except Exception as e:
                logger.exception("[assistant.chat/stream] failure")
                yield "data: " + json.dumps({"type": "error", "message": str(e)}) + "\n\n"
                return

            active_agent = result.get("active_agent") or agent_resolved
            reply_text = result.get("reply") or ""

            # Stream reply token by token (word-level chunks)
            words = reply_text.split(" ")
            chunk = ""
            for i, w in enumerate(words):
                chunk += ("" if i == 0 else " ") + w
                if len(chunk) >= 30 or i == len(words) - 1:
                    yield "data: " + json.dumps({"type": "token", "text": chunk}) + "\n\n"
                    chunk = ""

            # Persist
            new_msgs = result["messages_to_append"]
            if new_msgs and new_msgs[-1].get("role") == "assistant":
                if result.get("steps"):
                    new_msgs[-1]["steps"] = result["steps"]
                new_msgs[-1]["agent"] = active_agent

            is_first_turn = not conv.get("messages")
            current_title = conv.get("title") or msg[:60]
            if is_first_turn and reply_text:
                import asyncio as _asyncio
                async def _update_title():
                    try:
                        smart = await generate_title(msg, reply_text)
                        if smart:
                            await db.assistant_conversations.update_one(
                                {"_id": conv_id, "user_id": user_id}, {"$set": {"title": smart}}
                            )
                    except Exception:
                        pass
                _asyncio.create_task(_update_title())

            try:
                await db.assistant_conversations.update_one(
                    {"_id": conv_id, "user_id": user_id},
                    {"$push": {"messages": {"$each": new_msgs}},
                     "$set": {"updated_at": datetime.utcnow(),
                              "model": result.get("model") or conv.get("model"),
                              "title": current_title, "agent": active_agent}},
                )
            except Exception:
                logger.exception("[assistant.chat/stream] failed to save")

            yield "data: " + json.dumps({
                "type": "done",
                "conversation_id": conv_id,
                "reply": reply_text,
                "steps": result.get("steps") or [],
                "model": result.get("model"),
                "needs_confirmation": result.get("needs_confirmation"),
                "active_agent": active_agent,
                "active_agent_label": AGENT_REGISTRY.get(active_agent, {}).get("label", "Zilo"),
                "reply_suggestions": result.get("reply_suggestions") or [],
            }) + "\n\n"

        return StreamingResponse(_generate(), media_type="text/event-stream")

    @router.patch("/conversations/{conv_id}")
    async def rename_conversation(conv_id: str, req: Request, user=Depends(get_current_user)):
        body = await req.json()
        title = (body.get("title") or "").strip()
        if not title:
            raise HTTPException(400, "title is required")
        if len(title) > 120:
            title = title[:120]
        user_id = user.get("business_id", user["_id"])
        res = await db.assistant_conversations.update_one(
            {"_id": conv_id, "user_id": user_id},
            {"$set": {"title": title, "updated_at": datetime.utcnow()}},
        )
        if res.matched_count == 0:
            raise HTTPException(404, "Conversation not found")
        return {"status": "renamed", "id": conv_id, "title": title}

    # ── Document upload / management ──────────────────────────────────────────
    @router.post("/upload")
    async def upload_document(
        file: UploadFile = File(...),
        conversation_id: Optional[str] = None,
        user=Depends(get_current_user),
    ):
        if not file:
            raise HTTPException(400, "file is required")
        user_id = user.get("business_id", user["_id"])

        # If no conversation_id provided, create a new conversation so the upload
        # has a home and the user can continue the chat from there.
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            await db.assistant_conversations.insert_one({
                "_id": conversation_id,
                "user_id": user_id,
                "title": file.filename or "New chat",
                "model": DEFAULT_MODEL,
                "messages": [],
                "agent": resolve_agent_id("general"),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })
        else:
            conv = await db.assistant_conversations.find_one(
                {"_id": conversation_id, "user_id": user_id}
            )
            if not conv:
                raise HTTPException(404, "Conversation not found")

        content = await file.read()
        try:
            meta = await store_upload(
                db,
                user_id=user_id,
                conversation_id=conversation_id,
                filename=file.filename or "file",
                mime_type=file.content_type or "application/octet-stream",
                content=content,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"conversation_id": conversation_id, "document": meta}

    @router.get("/conversations/{conv_id}/documents")
    async def list_documents(conv_id: str, user=Depends(get_current_user)):
        user_id = user.get("business_id", user["_id"])
        docs = await list_for_conversation(db, user_id, conv_id)
        return {"documents": docs}

    @router.delete("/documents/{doc_id}")
    async def remove_document(doc_id: str, user=Depends(get_current_user)):
        user_id = user.get("business_id", user["_id"])
        ok = await delete_document(db, user_id, doc_id)
        if not ok:
            raise HTTPException(404, "Document not found")
        return {"status": "deleted"}

    @router.post("/export")
    async def export_document(req: Request, user=Depends(get_current_user)):
        """Convert markdown content to PDF or DOCX and stream the file back."""
        from .document_generator import cleanup_file, generate_docx, generate_pdf

        body = await req.json()
        content: str = (body.get("content") or "").strip()
        fmt: str = (body.get("format") or "pdf").lower()
        raw_name: str = (body.get("filename") or "zilo-export").strip()
        business_name: str = (body.get("business_name") or "").strip()

        if not content:
            raise HTTPException(400, "content is required")
        if fmt not in ("pdf", "docx"):
            raise HTTPException(400, "format must be 'pdf' or 'docx'")

        # If no business name supplied, try to look it up from the user record
        if not business_name:
            try:
                user_record = await db.users.find_one({"_id": user.get("business_id", user["_id"])})
                if user_record:
                    business_name = user_record.get("business_name") or user_record.get("owner_name") or ""
            except Exception:
                pass

        # Sanitise filename
        safe = re.sub(r"[^\w\-]", "_", raw_name)[:60] or "zilo-export"
        filename = f"{safe}.{fmt}"

        try:
            if fmt == "pdf":
                filepath = generate_pdf(content, filename, business_name=business_name)
                media = "application/pdf"
            else:
                filepath = generate_docx(content, filename, business_name=business_name)
                media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except Exception as e:
            logger.exception("[assistant.export] generation failed")
            raise HTTPException(500, f"Document generation failed: {e}")

        return FileResponse(
            path=filepath,
            media_type=media,
            filename=filename,
            background=None,
        )

    @router.get("/download/{key}")
    async def download_generated_document(key: str, user=Depends(get_current_user)):
        """Serve a file previously generated by the generate_document tool."""
        from .tools import _doc_store
        import os as _os
        filepath = _doc_store.get(key)
        if not filepath or not _os.path.exists(filepath):
            raise HTTPException(404, "Document not found or expired")
        filename = _os.path.basename(filepath)
        ext = filename.rsplit(".", 1)[-1].lower()
        media = (
            "application/pdf" if ext == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return FileResponse(path=filepath, media_type=media, filename=filename)

    @router.get("/audit")
    async def audit_log(limit: int = 50, user=Depends(get_current_user)):
        """Return the last N destructive tool calls made by the assistant for this account."""
        user_id = user.get("business_id", user["_id"])
        limit = max(1, min(int(limit or 50), 200))
        rows = await db.assistant_audit_log.find(
            {"user_id": user_id}
        ).sort("created_at", -1).to_list(limit)
        return [{
            "id": r.get("_id"),
            "tool": r.get("tool"),
            "arguments": r.get("arguments"),
            "result": r.get("result"),
            "success": r.get("success"),
            "actor_id": r.get("actor_id"),
            "agent": r.get("agent"),
            "created_at": r.get("created_at"),
        } for r in rows]

    return router


def _strip_storage_fields(m: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in m.items() if k not in ("steps",)}
    return out

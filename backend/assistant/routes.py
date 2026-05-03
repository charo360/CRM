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
from .models import DEFAULT_MODEL, list_available_models, stream_reply
from .orchestrator import run_turn, run_turn_stream
from .titler import generate_title
from .agent_workspace import load_workspace, update_workspace, workspace_to_context_line
from .conversation_access import (
    can_access_conversation_row,
    conversation_list_filter,
    serialize_conversation_meta,
    tenant_user_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _explicit_agent_from_body(body: Dict[str, Any]) -> Optional[str]:
    """If the client pinned a specialist, return the raw id string; else None = use intent router only."""
    raw = (body.get("agent") or "").strip()
    if not raw:
        return None
    al = raw.lower()
    if al in ("auto", "router", "automatic"):
        return None
    if resolve_agent_id(raw) == "general":
        return None
    return raw

# ── Rate limit: 30 turns per 60 seconds per user ─────────────────────────────
_RATE_WINDOW_SEC = 60
_RATE_MAX = 30
# In-memory fallback (single-process only)
_rate_hits: Dict[str, Deque[float]] = defaultdict(deque)


async def _check_rate_limit(user_id: str) -> None:
    """Rate-limit check: Redis sliding window with in-memory fallback."""
    now = time.time()
    try:
        from redis_client import get_redis
        r = await get_redis()
        if r:
            key = f"rl:assistant:{user_id}"
            pipe = r.pipeline()
            # Remove hits outside the window, add current timestamp, count, set expiry
            pipe.zremrangebyscore(key, 0, now - _RATE_WINDOW_SEC)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, _RATE_WINDOW_SEC + 1)
            results = await pipe.execute()
            count = results[2]  # zcard result
            if count > _RATE_MAX:
                # Find the oldest hit still in window to compute retry-after
                oldest = await r.zrange(key, 0, 0, withscores=True)
                retry = int(_RATE_WINDOW_SEC - (now - oldest[0][1])) + 1 if oldest else _RATE_WINDOW_SEC
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many assistant requests. Try again in {retry}s.",
                )
            return
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[rate_limit] Redis check failed, falling back to in-memory: %s", exc)

    # In-memory fallback
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


def _extract_workspace_updates(result: Dict[str, Any]) -> Dict[str, Any]:
    """Scan tool step results for facts worth persisting to the agent workspace.

    Looks at tool outputs from a turn for brand_color, product names, etc.
    Returns a (possibly empty) dict of workspace fields to upsert.
    """
    updates: Dict[str, Any] = {}
    for step in result.get("steps") or []:
        tool = step.get("tool", "")
        r = step.get("result") or {}
        if not isinstance(r, dict):
            continue
        # get_owner_info → capture brand color
        if tool == "get_owner_info":
            if r.get("brand_primary_color"):
                updates["brand_color"] = r["brand_primary_color"]
        # generate_social_post / generate_ad_creative → capture platform from args
        if tool in ("generate_social_post", "generate_ad_creative", "generate_carousel_cover"):
            args = step.get("arguments") or {}
            if isinstance(args, dict):
                if args.get("platform"):
                    updates["platform"] = args["platform"]
                if args.get("headline"):
                    updates["approved_copy"] = args["headline"]
    return updates


def _mk_router(db, get_current_user):
    """Factory — binds db + auth dep into the router. Call this from server.py."""

    async def _load_accessible_conv(conv_id: str, user) -> Dict[str, Any]:
        bid = tenant_user_id(user)
        row = await db.assistant_conversations.find_one({"_id": conv_id, "user_id": bid})
        if not row or not can_access_conversation_row(row, user):
            raise HTTPException(404, "Conversation not found")
        return row

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

    @router.get("/suggestions")
    async def get_suggestions(user=Depends(get_current_user)):
        """Return personalized quick-action suggestions for the chat empty state.

        Combines:
          1. Owner preferences (learned from past sessions via Qdrant)
          2. Recent conversation topics (last 5 conversations)
          3. Business context (connected integrations / recent agent usage)
        Falls back to sensible defaults when no history exists.
        """
        import asyncio as _asyncio
        user_id = user.get("business_id", user["_id"])

        # Fetch recent conversations + owner preferences in parallel
        try:
            recent_convs, owner_prefs_raw = await _asyncio.gather(
                db.assistant_conversations.find(
                    conversation_list_filter(user)
                ).sort("updated_at", -1).to_list(5),
                _get_all_owner_prefs_safe(user_id),
            )
        except Exception:
            recent_convs, owner_prefs_raw = [], []

        # Build context string for the suggestion LLM call
        pref_lines = "\n".join(f"- {p['summary']}" for p in owner_prefs_raw[:10]) if owner_prefs_raw else ""
        recent_topics = []
        recent_agents: list = []
        for c in recent_convs:
            if c.get("title") and c["title"] != "New chat":
                recent_topics.append(c["title"])
            if c.get("agent") and c["agent"] not in ("general", None):
                recent_agents.append(c["agent"])

        topics_line = "\n".join(f"- {t}" for t in recent_topics) if recent_topics else ""
        agents_used = list(dict.fromkeys(recent_agents))[:4]  # unique, preserve order

        try:
            from .models import chat_with_tools as _chat
            prompt_parts = [
                "You are generating personalized quick-action suggestion chips for a CRM AI assistant.",
                "The chips appear on the empty chat screen so the owner can tap one to instantly start a task.",
                "",
                "Generate exactly 8 suggestion chips.",
                "Rules:",
                "- Each chip is 4-9 words, action-oriented, starts with a verb",
                "- Mix across: analytics, marketing/campaigns, customers, content creation, operations",
                "- Lean toward what this specific owner actually uses (see context below)",
                "- Be specific — use their business context, not generic CRM phrases",
                "- NO duplicate themes across the 8 chips",
                "- Output ONLY a JSON array of 8 strings, nothing else",
                "",
            ]
            if pref_lines:
                prompt_parts += ["Owner preferences learned from past sessions:", pref_lines, ""]
            if topics_line:
                prompt_parts += ["Recent conversation topics:", topics_line, ""]
            if agents_used:
                prompt_parts.append(f"Specialist agents recently used: {', '.join(agents_used)}")
            prompt_parts += [
                "",
                "Output format (JSON array only, no markdown):",
                '["chip 1", "chip 2", "chip 3", "chip 4", "chip 5", "chip 6", "chip 7", "chip 8"]',
            ]

            resp = await _chat(
                messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
                tools=[],
                temperature=0.7,
                timeout=8.0,
            )
            raw = (resp.get("content") or "").strip()
            # Parse JSON array
            import json as _json, re as _re
            match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
            if match:
                chips = _json.loads(match.group())
                if isinstance(chips, list) and len(chips) >= 4:
                    return {"suggestions": chips[:8], "personalized": bool(pref_lines or topics_line)}
        except Exception as exc:
            logger.debug("[suggestions] LLM generation failed, using fallback: %s", exc)

        # Fallback: static defaults
        return {
            "suggestions": [
                "What's my revenue this week?",
                "Show me overdue follow-ups",
                "Draft a promo broadcast for VIP customers",
                "Which orders are still pending?",
                "Help me set up a Facebook ad campaign",
                "Who are my top customers this month?",
                "Generate a sales report as a PDF",
                "Which customers haven't bought in 60 days?",
            ],
            "personalized": False,
        }

    async def _get_all_owner_prefs_safe(business_id: str) -> list:
        """Wrapper — returns [] on any error."""
        try:
            from memory.owner_prefs import get_all_owner_preferences
            return await get_all_owner_preferences(business_id)
        except Exception:
            return []

    @router.get("/conversations")
    async def list_conversations(user=Depends(get_current_user)):
        rows = await db.assistant_conversations.find(
            conversation_list_filter(user)
        ).sort("updated_at", -1).to_list(50)
        return [{
            "id": r["_id"],
            "title": r.get("title") or "New chat",
            "updated_at": r.get("updated_at"),
            "message_count": len(r.get("messages") or []),
            "agent": r.get("agent") or "general",
            **serialize_conversation_meta(r),
        } for r in rows]

    @router.get("/conversations/{conv_id}")
    async def get_conversation(conv_id: str, user=Depends(get_current_user)):
        row = await _load_accessible_conv(conv_id, user)
        return {
            "id": row["_id"],
            "title": row.get("title") or "New chat",
            "model": row.get("model"),
            "messages": row.get("messages") or [],
            "agent": row.get("agent") or "general",
            **serialize_conversation_meta(row),
        }

    @router.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: str, user=Depends(get_current_user)):
        bid = tenant_user_id(user)
        row = await db.assistant_conversations.find_one({"_id": conv_id, "user_id": bid})
        if not row or not can_access_conversation_row(row, user):
            raise HTTPException(404, "Conversation not found")
        await db.assistant_conversations.delete_one({"_id": conv_id, "user_id": bid})
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
        await _check_rate_limit(user_id)
        conv_id = body.get("conversation_id")
        conv: Dict[str, Any]
        if conv_id:
            conv = await _load_accessible_conv(conv_id, user)
        else:
            conv_id = str(uuid.uuid4())
            vis = (body.get("visibility") or "team").strip().lower()
            if vis not in ("team", "private"):
                vis = "team"
            conv = {
                "_id": conv_id,
                "user_id": user_id,
                "title": msg[:60],
                "model": body.get("model") or DEFAULT_MODEL,
                "messages": [],
                "agent": "general",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": str(user["_id"]),
                "visibility": vis,
                "shared_with": [str(user["_id"])] if vis == "private" else [],
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
            msg,
            history,
            AGENT_REGISTRY,
            prev_agent=prev_agent,
            design_flow_active=design_flow_active,
            explicit_agent=_explicit_agent_from_body(body),
        )

        # Load shared agent workspace — inject as context when agent switches
        workspace = await load_workspace(db, conv_id)
        workspace_ctx = workspace_to_context_line(workspace)
        user_with_ctx = {**user, "_workspace_context": workspace_ctx} if workspace_ctx else user

        # Strip non-serializable keys from history before passing to LLM
        clean_history = [_strip_storage_fields(m) for m in history]

        try:
            result = await run_turn(
                db=db,
                user=user_with_ctx,
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

        # Update shared workspace from tool results (fire-and-forget)
        import asyncio as _asyncio
        _asyncio.create_task(update_workspace(
            db, conv_id, user_id,
            _extract_workspace_updates(result),
            agent_id=active_agent,
        ))

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
                await _check_rate_limit(user_id)
            except HTTPException as e:
                yield "data: " + json.dumps({"type": "error", "message": e.detail}) + "\n\n"
                return

            conv_id = body.get("conversation_id")
            conv: Dict[str, Any]
            if conv_id:
                conv = await db.assistant_conversations.find_one({"_id": conv_id, "user_id": user_id})
                if not conv or not can_access_conversation_row(conv, user):
                    yield "data: " + json.dumps({"type": "error", "message": "Conversation not found"}) + "\n\n"
                    return
            else:
                conv_id = str(uuid.uuid4())
                vis = (body.get("visibility") or "team").strip().lower()
                if vis not in ("team", "private"):
                    vis = "team"
                conv = {
                    "_id": conv_id, "user_id": user_id, "title": msg[:60],
                    "model": body.get("model") or DEFAULT_MODEL,
                    "messages": [], "agent": "general",
                    "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
                    "created_by": str(user["_id"]),
                    "visibility": vis,
                    "shared_with": [str(user["_id"])] if vis == "private" else [],
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
                msg,
                history,
                AGENT_REGISTRY,
                prev_agent=prev_agent,
                design_flow_active=design_flow_active,
                explicit_agent=_explicit_agent_from_body(body),
            )
            agent_label = AGENT_REGISTRY.get(agent_resolved, {}).get("label", "Zilo")

            # Load shared agent workspace and inject context when agent switches
            workspace = await load_workspace(db, conv_id)
            workspace_ctx = workspace_to_context_line(workspace)
            user_with_ctx = {**user, "_workspace_context": workspace_ctx} if workspace_ctx else user

            yield "data: " + json.dumps({"type": "thinking", "agent": agent_resolved, "agent_label": agent_label}) + "\n\n"

            result: Optional[Dict[str, Any]] = None
            reply_text = ""

            # Run the stream in a background task and read events from a queue.
            # This lets us send SSE keepalive comments every 15 s without
            # cancelling the in-progress LLM/tool work (which would happen if we
            # used asyncio.wait_for directly on __anext__()).
            import asyncio as _asyncio
            _KEEPALIVE_SEC = 15
            _queue: _asyncio.Queue[Optional[Dict[str, Any]]] = _asyncio.Queue()

            async def _feed() -> None:
                try:
                    async for _ev in run_turn_stream(
                        db=db, user=user_with_ctx, history=history, user_message=msg,
                        model_id=body.get("model") or conv.get("model") or DEFAULT_MODEL,
                        auto_approve_destructive=bool(body.get("auto_approve")),
                        conversation_id=conv_id, agent_id=agent_resolved,
                    ):
                        await _queue.put(_ev)
                except Exception as _exc:
                    await _queue.put({"type": "error", "message": str(_exc)})
                finally:
                    await _queue.put(None)  # sentinel

            _task = _asyncio.create_task(_feed())
            try:
                while True:
                    try:
                        item = await _asyncio.wait_for(_queue.get(), timeout=_KEEPALIVE_SEC)
                    except _asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if item is None:
                        break
                    etype = item.get("type")
                    if etype == "tool_start":
                        yield "data: " + json.dumps({"type": "tool_start", "tool": item.get("tool", "")}) + "\n\n"
                    elif etype == "token":
                        token = item.get("text", "")
                        reply_text += token
                        yield "data: " + json.dumps({"type": "token", "text": token}) + "\n\n"
                    elif etype == "done":
                        result = item
                    elif etype == "error":
                        yield "data: " + json.dumps({"type": "error", "message": item.get("message", "Unknown error")}) + "\n\n"
                        _task.cancel()
                        return
            except Exception as e:
                _task.cancel()
                logger.exception("[assistant.chat/stream] run_turn_stream failure")
                yield "data: " + json.dumps({"type": "error", "message": str(e)}) + "\n\n"
                return

            if not result:
                yield "data: " + json.dumps({"type": "error", "message": "No result from assistant"}) + "\n\n"
                return

            active_agent = result.get("active_agent") or agent_resolved
            if not reply_text:
                reply_text = result.get("reply") or ""

            # Update shared workspace from tool results (fire-and-forget)
            _asyncio.create_task(update_workspace(
                db, conv_id, user_id,
                _extract_workspace_updates(result),
                agent_id=active_agent,
            ))

            # Persist
            new_msgs = result.get("messages_to_append") or []
            if new_msgs and new_msgs[-1].get("role") == "assistant":
                if reply_text:
                    new_msgs[-1]["content"] = reply_text
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
            }, default=str) + "\n\n"

        return StreamingResponse(_generate(), media_type="text/event-stream")

    @router.patch("/conversations/{conv_id}")
    async def patch_conversation(conv_id: str, req: Request, user=Depends(get_current_user)):
        body = await req.json()
        title_raw = body.get("title")
        title = (title_raw or "").strip() if title_raw is not None else None
        if title is not None and not title:
            raise HTTPException(400, "title cannot be empty")
        if title is not None and len(title) > 120:
            title = title[:120]
        visibility = body.get("visibility")
        if visibility is not None and visibility not in ("team", "private"):
            raise HTTPException(400, "visibility must be 'team' or 'private'")
        if title is None and visibility is None:
            raise HTTPException(400, "Provide title and/or visibility")
        bid = tenant_user_id(user)
        row = await db.assistant_conversations.find_one({"_id": conv_id, "user_id": bid})
        if not row or not can_access_conversation_row(row, user):
            raise HTTPException(404, "Conversation not found")
        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if title is not None:
            updates["title"] = title
        if visibility is not None:
            updates["visibility"] = visibility
            if visibility == "team":
                updates["shared_with"] = []
        res = await db.assistant_conversations.update_one(
            {"_id": conv_id, "user_id": bid},
            {"$set": updates},
        )
        if res.matched_count == 0:
            raise HTTPException(404, "Conversation not found")
        return {"status": "ok", "id": conv_id, **updates}

    @router.post("/conversations/{conv_id}/share")
    async def share_conversation(conv_id: str, req: Request, user=Depends(get_current_user)):
        """Add team login user_ids so they can open this Zilo thread (sets private visibility)."""
        body = await req.json()
        raw_ids = body.get("user_ids") or []
        if not isinstance(raw_ids, list) or not raw_ids:
            raise HTTPException(400, "user_ids array is required")
        bid = tenant_user_id(user)
        row = await db.assistant_conversations.find_one({"_id": conv_id, "user_id": bid})
        if not row or not can_access_conversation_row(row, user):
            raise HTTPException(404, "Conversation not found")
        creator = str(row.get("created_by") or user["_id"])
        shared = {creator, str(user["_id"])}
        for x in raw_ids:
            if x:
                shared.add(str(x))
        await db.assistant_conversations.update_one(
            {"_id": conv_id, "user_id": bid},
            {
                "$set": {
                    "visibility": "private",
                    "shared_with": list(shared),
                    "created_by": creator,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return {"status": "ok", "shared_with": list(shared)}

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
                "created_by": str(user["_id"]),
                "visibility": "team",
                "shared_with": [],
            })
        else:
            conv = await db.assistant_conversations.find_one(
                {"_id": conversation_id, "user_id": user_id}
            )
            if not conv or not can_access_conversation_row(conv, user):
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
        await _load_accessible_conv(conv_id, user)
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

        # Fetch document style profile for branded output
        doc_style: Dict[str, Any] = {}
        try:
            from saved_designs import get_document_style as _get_doc_style
            business_id = user.get("business_id", user["_id"])
            doc_style = await _get_doc_style(db, business_id) or {}
        except Exception:
            pass

        # Sanitise filename
        safe = re.sub(r"[^\w\-]", "_", raw_name)[:60] or "zilo-export"
        filename = f"{safe}.{fmt}"

        try:
            if fmt == "pdf":
                filepath = generate_pdf(content, filename, business_name=business_name, style=doc_style)
                media = "application/pdf"
            else:
                filepath = generate_docx(content, filename, business_name=business_name, style=doc_style)
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
        from .tools import _fallback_doc_store
        import os as _os
        filepath = _fallback_doc_store.get(key)
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

    @router.post("/ai-draft")
    async def ai_draft(req: Request, user=Depends(get_current_user)):
        """Lightweight single-turn LLM call for email drafts, classification, and summaries.

        Body: { "prompt": "<full prompt text>", "model": "<optional model id>" }
        Returns: { "reply": "<generated text>" }
        """
        body = await req.json()
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(400, "prompt is required")

        result = await chat_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            model_id=body.get("model") or DEFAULT_MODEL,
            temperature=0.3,
            timeout=30.0,
        )
        reply = (result.get("content") or "").strip()
        return {"reply": reply}

    @router.get("/context")
    async def business_context(days: int = 7, user=Depends(get_current_user)):
        """Return quick business stats for the command bar (customers, orders, top product, revenue)."""
        from .tools import get_business_context, ToolContext
        
        # Create a mock tool context
        ctx = ToolContext(
            db=db,
            user={
                "user_id": user.get("business_id", user["_id"]),
                "business_id": user.get("business_id"),
            },
        )
        
        result = await get_business_context(ctx, {"days": days})
        stats = result.get("quick_stats", {})
        
        return {
            "new_customers": stats.get("new_customers"),
            "orders": stats.get("orders"),
            "top_product": stats.get("top_product"),
            "total_revenue_window": stats.get("total_revenue_window"),
        }

    return router


def _strip_storage_fields(m: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in m.items() if k not in ("steps",)}
    return out

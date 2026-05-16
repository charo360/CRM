"""FastAPI routes for the LangGraph SEO agent chat."""
from __future__ import annotations
import logging, uuid, json, os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

logger = logging.getLogger(__name__)

# ── Brief generation ──────────────────────────────────────────────────────────

BRIEF_CACHE_HOURS = 12   # regenerate brief every 12 hours

async def _generate_seo_brief(db, user_id: str) -> dict:
    """
    Analyse the user's full SEO state and return a structured brief:
    health score, wins, gaps, and 3-5 prioritised executable actions.
    Runs Claude directly (not the agent) for speed and determinism.
    """
    # ── Collect all state ─────────────────────────────────────────────────────
    now = datetime.utcnow()

    # Published + draft posts
    posts = await db.seo_blog_posts.find({"user_id": user_id}).sort("created_at", -1).limit(50).to_list(50)
    published = [p for p in posts if p.get("status") == "published"]
    drafts    = [p for p in posts if p.get("status") == "draft"]

    # Saved keywords (all months)
    kw_docs = await db.seo_saved_keywords.find({"user_id": user_id}).sort("month", -1).limit(6).to_list(6)
    all_kws: list[dict] = []
    for doc in kw_docs:
        for k in (doc.get("keywords") or []):
            if isinstance(k, dict) and k.get("keyword"):
                all_kws.append(k)

    # Which keywords have a post?
    published_kw_phrases = {kw.lower() for p in published for kw in (p.get("keywords") or [])}
    kws_without_post = [k for k in all_kws if k.get("keyword","").lower() not in published_kw_phrases]

    # Latest audit
    audit = await db.seo_audits.find_one({"user_id": user_id}, sort=[("created_at", -1)])

    # Ranking history (last 30 days)
    cutoff = now - timedelta(days=30)
    rankings = await db.seo_serp_rankings.find(
        {"user_id": user_id, "checked_at": {"$gte": cutoff}}
    ).sort("checked_at", -1).limit(20).to_list(20)

    # User profile
    user = await db.users.find_one({"_id": user_id}, {
        "business_name": 1, "business_type": 1, "country_code": 1,
        "business_knowledge": 1, "settings": 1,
    })
    biz_name = (user or {}).get("business_name") or "Your business"
    bk = (user or {}).get("business_knowledge") or {}
    website = bk.get("website_url") or ""

    # Days since last audit
    days_since_audit = None
    audit_score = None
    if audit:
        delta = now - audit["created_at"]
        days_since_audit = delta.days
        audit_score = audit.get("score")

    # Top keywords by volume (no content yet)
    top_gaps = sorted(kws_without_post, key=lambda k: k.get("search_volume") or 0, reverse=True)[:5]

    # ── Build data summary for Claude ─────────────────────────────────────────
    data_block = f"""
BUSINESS: {biz_name}
WEBSITE: {website or "not set"}

CONTENT STATUS:
- Published posts: {len(published)}
- Draft posts: {len(drafts)}
- Total keywords tracked: {len(all_kws)} across {len(kw_docs)} months
- Keywords with NO content yet: {len(kws_without_post)}
- Top keyword gaps (highest volume, no post):
{chr(10).join(f"  • {k['keyword']} (~{k.get('search_volume') or '?'} searches/mo, {k.get('difficulty','?')} difficulty)" for k in top_gaps) or "  None"}

SEO AUDIT:
- Last audit score: {audit_score}/100 if audit else "No audit run yet"
- Days since last audit: {days_since_audit if days_since_audit is not None else "Never"}
- Critical issues: {len([i for i in (audit or {}).get("issues",[]) if i.get("type")=="critical"]) if audit else "unknown"}

RANKING HISTORY (last 30 days):
{chr(10).join(f"  • '{r.get('keyword')}' — position {r.get('position','?')} on {r.get('domain','?')}" for r in rankings[:5]) or "  No rankings tracked yet"}

RECENT PUBLISHED POSTS:
{chr(10).join(f"  • {p.get('title','Untitled')} ({p.get('status')})" for p in published[:5]) or "  None published yet"}
""".strip()

    # ── Call Claude for analysis ──────────────────────────────────────────────
    import httpx as _httpx
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    prompt = f"""You are a senior SEO strategist reviewing a business's full SEO status. Act like a real expert advisor doing a weekly review — not a chatbot.

{data_block}

Generate a structured SEO brief. Be specific, direct, and use the actual data above. Do NOT give generic advice.

Return ONLY valid JSON (no markdown):
{{
  "health_score": <0-100 integer based on audit score, content volume, and keyword coverage>,
  "health_grade": "<A|B|C|D|F>",
  "status_summary": "<2-3 sentence plain-English summary of the current SEO state. Reference actual numbers.>",
  "wins": ["<specific win 1>", "<specific win 2>"],
  "gaps": ["<specific gap 1>", "<specific gap 2>", "<specific gap 3>"],
  "actions": [
    {{
      "id": "act_1",
      "priority": 1,
      "type": "<write_post|run_audit|research_keywords|check_rankings|fix_issue>",
      "title": "<short action title>",
      "reason": "<1 sentence explaining WHY this is the top priority, using actual data>",
      "effort": "<2 min|5 min|10 min>",
      "keyword": "<keyword phrase if type=write_post, else null>",
      "url": "<site URL if type=run_audit, else null>",
      "agent_prompt": "<exact prompt to send to the SEO agent to execute this action>"
    }}
  ]
}}

Rules:
- actions array: 3-5 items, ordered by impact (highest ROI first)
- write_post: only suggest for keywords that have real search volume and no content yet
- run_audit: suggest if last audit was >14 days ago or score <70
- research_keywords: suggest if fewer than 10 keywords tracked or all keywords have content
- check_rankings: suggest if no rankings tracked in last 30 days
- agent_prompt: must be a complete, standalone instruction the agent can execute immediately
- Be a strategic advisor, not a cheerleader — if the state is bad, say so clearly"""

    raw = ""
    try:
        if claude_key:
            async with _httpx.AsyncClient(timeout=45) as hc:
                resp = await hc.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": claude_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1500,
                          "messages": [{"role": "user", "content": prompt}]},
                )
                raw = resp.json()["content"][0]["text"]
        elif openai_key:
            from openai import AsyncOpenAI
            c = AsyncOpenAI(api_key=openai_key)
            r = await c.chat.completions.create(
                model="gpt-4o-mini", max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = r.choices[0].message.content or ""
        else:
            raise RuntimeError("No AI provider configured")

        raw = raw.strip()
        if raw.startswith("```"): raw = raw[raw.find("{"):]
        if raw.endswith("```"): raw = raw[:raw.rfind("}") + 1]
        brief = json.loads(raw)
    except Exception as e:
        logger.error("[seo_agent] Brief generation failed: %s | raw=%s", e, raw[:300])
        # Fallback: build a basic brief from the raw data
        brief = {
            "health_score": audit_score or 50,
            "health_grade": "C",
            "status_summary": f"{len(published)} posts published. {len(kws_without_post)} keywords have no content yet.",
            "wins": [f"{len(published)} posts published"] if published else ["Getting started with SEO"],
            "gaps": [f"{len(kws_without_post)} tracked keywords have no blog post yet"] if kws_without_post else [],
            "actions": [
                {
                    "id": "act_1", "priority": 1, "type": "research_keywords",
                    "title": "Research keywords for your business",
                    "reason": "Start with keyword research to find your best opportunities.",
                    "effort": "2 min", "keyword": None, "url": None,
                    "agent_prompt": "Research the best keywords for my business and show me search volumes.",
                }
            ],
        }

    brief["generated_at"] = now.isoformat()
    brief["next_check"] = (now + timedelta(hours=BRIEF_CACHE_HOURS)).isoformat()
    brief["data_snapshot"] = {
        "published_posts": len(published),
        "draft_posts": len(drafts),
        "keywords_tracked": len(all_kws),
        "keywords_without_post": len(kws_without_post),
        "audit_score": audit_score,
        "days_since_audit": days_since_audit,
        "rankings_tracked": len(rankings),
    }
    return brief


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

class ExecuteActionRequest(BaseModel):
    agent_prompt: Optional[str] = None
    conversation_id: Optional[str] = None


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
    async def chat(payload: SEOChatRequest, user=Depends(user_dep)):
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

        # ── Run the LangGraph (db + user_id injected via config + contextvars) ─
        from .tools import set_seo_context
        set_seo_context(db, tid)
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
    async def list_conversations(user=Depends(user_dep)):
        tid = _tid(user)
        docs = await db.seo_agent_conversations.find(
            {"user_id": tid},
            {"messages": 0},          # exclude message bodies for speed
        ).sort("updated_at", -1).limit(30).to_list(30)
        return [_ser_msg(d) for d in docs]

    # ── GET /seo-agent/conversations/{conv_id} ────────────────────────────────

    @router.get("/conversations/{conv_id}")
    async def get_conversation(conv_id: str, user=Depends(user_dep)):
        tid = _tid(user)
        doc = await db.seo_agent_conversations.find_one({"_id": conv_id, "user_id": tid})
        if not doc:
            raise HTTPException(404, "Conversation not found")
        return _ser_msg(doc)

    # ── DELETE /seo-agent/conversations/{conv_id} ─────────────────────────────

    @router.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: str, user=Depends(user_dep)):
        tid = _tid(user)
        result = await db.seo_agent_conversations.delete_one({"_id": conv_id, "user_id": tid})
        if result.deleted_count == 0:
            raise HTTPException(404, "Conversation not found")
        return {"ok": True}

    # ── GET /seo-agent/brief ──────────────────────────────────────────────────
    # Returns a cached autonomous SEO brief (regenerated every 12h).
    # Acts like an SEO expert checking in: what's working, what's missing, what to do.

    @router.get("/brief")
    async def get_brief(refresh: bool = False, user=Depends(user_dep)):
        tid = _tid(user)

        # Return cached brief if still fresh
        if not refresh:
            cached = await db.seo_memory.find_one({"_id": f"brief:{tid}"})
            if cached:
                generated_at = cached.get("generated_at")
                if generated_at:
                    age = datetime.utcnow() - generated_at
                    if age.total_seconds() < BRIEF_CACHE_HOURS * 3600:
                        doc = dict(cached)
                        doc.pop("_id", None)
                        if isinstance(doc.get("generated_at"), datetime):
                            doc["generated_at"] = doc["generated_at"].isoformat()
                        return doc

        # Generate fresh brief
        try:
            brief = await _generate_seo_brief(db, tid)
        except Exception as e:
            logger.error("[seo_agent] Brief error: %s", e, exc_info=True)
            raise HTTPException(500, f"Could not generate SEO brief: {e}")

        # Cache it
        try:
            await db.seo_memory.replace_one(
                {"_id": f"brief:{tid}"},
                {"_id": f"brief:{tid}", "user_id": tid, "generated_at": datetime.utcnow(), **brief},
                upsert=True,
            )
        except Exception as e:
            logger.warning("[seo_agent] Brief cache failed: %s", e)

        return brief

    # ── POST /seo-agent/execute-action ────────────────────────────────────────
    # One-click execution of a recommended action from the brief.
    # Runs the action through the full LangGraph agent and returns the result.

    @router.post("/execute-action")
    async def execute_action(payload: ExecuteActionRequest, user=Depends(user_dep)):
        if not payload.agent_prompt or not payload.agent_prompt.strip():
            raise HTTPException(400, "agent_prompt is required and cannot be empty.")

        graph = get_seo_graph() if get_seo_graph else None
        if graph is None:
            raise HTTPException(503, "SEO agent not available.")

        tid = _tid(user)
        conv_id = payload.conversation_id or str(uuid.uuid4())

        from .tools import set_seo_context
        set_seo_context(db, tid)
        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=payload.agent_prompt)]},
                config={
                    "configurable": {"db": db, "user_id": tid},
                    "recursion_limit": 25,
                },
            )
        except Exception as e:
            logger.error("[seo_agent] execute-action error: %s", e, exc_info=True)
            raise HTTPException(500, f"Agent error: {e}")

        reply = ""
        tool_steps: List[Dict[str, Any]] = []
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                reply = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
        for msg in result.get("messages", []):
            if isinstance(msg, ToolMessage):
                tool_steps.append({"tool": getattr(msg, "name", "tool"), "output": str(msg.content)[:400]})

        # Persist to conversation history
        try:
            await db.seo_agent_conversations.replace_one(
                {"_id": conv_id},
                {
                    "_id": conv_id, "user_id": tid,
                    "title": f"Auto: {payload.agent_prompt[:50]}",
                    "messages": [
                        {"role": "user", "content": payload.agent_prompt, "ts": datetime.utcnow()},
                        {"role": "assistant", "content": reply, "tool_steps": tool_steps, "ts": datetime.utcnow()},
                    ],
                    "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
                    "auto_executed": True,
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("[seo_agent] execute-action persist failed: %s", e)

        # Invalidate brief cache so next load reflects the new work
        try:
            await db.seo_memory.delete_one({"_id": f"brief:{tid}"})
        except Exception:
            pass

        return SEOChatResponse(reply=reply, conversation_id=conv_id, tool_steps=tool_steps)

    # ── GET /seo-agent/cache/stats ────────────────────────────────────────────

    @router.get("/cache/stats")
    async def cache_stats(_user=Depends(user_dep)):
        now = datetime.utcnow()
        try:
            total = await db.seo_cache.count_documents({})
            valid = await db.seo_cache.count_documents({"expires_at": {"$gt": now}})

            agg = await db.seo_cache.aggregate([
                {"$group": {
                    "_id": None,
                    "total_hits": {"$sum": "$hit_count"},
                    "oldest": {"$min": "$created_at"},
                    "newest": {"$max": "$created_at"},
                }}
            ]).to_list(1)
            totals = agg[0] if agg else {}

            by_tool = await db.seo_cache.aggregate([
                {"$match": {"expires_at": {"$gt": now}}},
                {"$group": {
                    "_id": "$tool",
                    "count": {"$sum": 1},
                    "hits": {"$sum": "$hit_count"},
                    "ttl_days": {"$first": "$ttl_days"},
                }},
                {"$sort": {"hits": -1}},
            ]).to_list(50)

            return {
                "total_cached": total,
                "valid_cached": valid,
                "expired_cached": total - valid,
                "api_calls_saved": totals.get("total_hits", 0),
                "oldest_entry": totals.get("oldest").isoformat() if totals.get("oldest") else None,
                "newest_entry": totals.get("newest").isoformat() if totals.get("newest") else None,
                "by_tool": [
                    {
                        "tool": r["_id"],
                        "cached": r["count"],
                        "hits": r["hits"],
                        "ttl_days": r.get("ttl_days", 0),
                    }
                    for r in by_tool
                ],
            }
        except Exception as e:
            return {"total_cached": 0, "valid_cached": 0, "expired_cached": 0,
                    "api_calls_saved": 0, "by_tool": [], "error": str(e)}

    # ── DELETE /seo-agent/cache ────────────────────────────────────────────────

    @router.delete("/cache")
    async def clear_cache(tool: str = "", _user=Depends(user_dep)):
        try:
            query = {"tool": tool} if tool else {}
            result = await db.seo_cache.delete_many(query)
            return {"ok": True, "deleted": result.deleted_count}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── GET /seo-agent/status ─────────────────────────────────────────────────

    @router.get("/status")
    async def status(_user=Depends(user_dep)):
        g = get_seo_graph() if get_seo_graph else None
        from .tools import SEO_TOOLS
        return {
            "available": g is not None,
            "tools": [t.name for t in SEO_TOOLS],
        }

    return router

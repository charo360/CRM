"""
Zilo Scouts — scheduled keyword monitors (Open Scouts pattern).

Each scout runs search queries on a schedule, AI-filters for buying intent,
and feeds Field Agents opportunities + approval queue.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCOUTS_COLLECTION = "zilo_scouts"
EXECUTIONS_COLLECTION = "zilo_scout_executions"

FREQUENCY_HOURS = {
    "6h": 6,
    "12h": 12,
    "daily": 24,
    "weekly": 168,
}

URL_DEDUP_DAYS = 14
MAX_RESULTS_PER_SCOUT = 8


def _now() -> datetime:
    return datetime.utcnow()


def _serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    for key in ("created_at", "updated_at", "last_run_at", "next_run_at"):
        val = out.get(key)
        if hasattr(val, "isoformat"):
            out[key] = val.isoformat()
    return out


async def get_biz_context(db, uid: str) -> Dict[str, Any]:
    biz = await db.users.find_one({"_id": uid}) or {}
    settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
    return {
        "business_name": biz.get("business_name", "") or biz.get("name", ""),
        "business_type": biz.get("business_type", "") or biz.get("industry", ""),
        "country": biz.get("country", "") or biz.get("location", ""),
        "goals": settings.get("goals", ""),
        "products": biz.get("products") or biz.get("services") or [],
    }


def _default_scout_templates(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build 3–5 scouts from business profile without LLM."""
    biz_name = (ctx.get("business_name") or "my business").strip()
    biz_type = (ctx.get("business_type") or "services").strip()
    country = (ctx.get("country") or "").strip()
    loc = country or "worldwide"

    scouts: List[Dict[str, Any]] = [
        {
            "title": f"Buy intent — {biz_type}",
            "goal": f"Find people asking for recommendations or looking to hire {biz_type} in {loc}",
            "scout_type": "buy_intent",
            "search_queries": [
                f'"looking for" {biz_type} {country}'.strip(),
                f'"recommend" {biz_type} {country}'.strip(),
                f'"anyone know" {biz_type} {country}'.strip(),
                f'"need a" {biz_type} {country}'.strip(),
            ],
        },
        {
            "title": f"Category discussions — {biz_type}",
            "goal": f"Monitor forum and social threads discussing {biz_type} problems and solutions in {loc}",
            "scout_type": "category",
            "search_queries": [
                f"{biz_type} advice {country}".strip(),
                f"best {biz_type} {country}".strip(),
                f"{biz_type} reddit {country}".strip(),
            ],
        },
    ]

    if biz_name and biz_name.lower() not in ("my business", "business", ""):
        scouts.append({
            "title": f"Brand mentions — {biz_name}",
            "goal": f"Track public mentions and reviews of {biz_name}",
            "scout_type": "brand",
            "search_queries": [
                f'"{biz_name}" review',
                f'"{biz_name}" {country}'.strip(),
            ],
        })

    goals = (ctx.get("goals") or "").lower()
    if any(w in goals for w in ("fund", "grant", "tender", "rfp", "invest")):
        scouts.append({
            "title": "Funding & grants",
            "goal": f"Find grants, tenders, and funding opportunities for {biz_type} in {loc}",
            "scout_type": "funding",
            "search_queries": [
                f"{biz_type} grant {country}".strip(),
                f"{biz_type} tender {country}".strip(),
                f"small business funding {country}".strip(),
            ],
        })

    return scouts[:5]


async def ensure_default_scouts(db, uid: str, ctx: Optional[Dict[str, Any]] = None, force: bool = False) -> List[Dict[str, Any]]:
    """Create profile-based scouts if the user has none (or force=True)."""
    existing = await db[SCOUTS_COLLECTION].count_documents({"user_id": uid})
    if existing > 0 and not force:
        items = await db[SCOUTS_COLLECTION].find({"user_id": uid}).sort("created_at", 1).to_list(20)
        return [_serialize_doc(i) for i in items]

    ctx = ctx or await get_biz_context(db, uid)
    created = []
    now = _now()
    for tpl in _default_scout_templates(ctx):
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "title": tpl["title"],
            "goal": tpl["goal"],
            "scout_type": tpl["scout_type"],
            "search_queries": tpl["search_queries"],
            "location": ctx.get("country", ""),
            "frequency": "12h",
            "frequency_hours": FREQUENCY_HOURS["12h"],
            "is_active": True,
            "auto_generated": True,
            "last_run_at": None,
            "next_run_at": now,
            "created_at": now,
            "updated_at": now,
        }
        await db[SCOUTS_COLLECTION].insert_one(doc)
        created.append(_serialize_doc(doc))

    logger.info("[scouts] auto-created %d scouts for user=%s", len(created), uid)
    return created


async def list_scouts(db, uid: str) -> List[Dict[str, Any]]:
    items = await db[SCOUTS_COLLECTION].find({"user_id": uid}).sort("created_at", -1).to_list(50)
    return [_serialize_doc(i) for i in items]


async def create_scout(db, uid: str, body: Dict[str, Any]) -> Dict[str, Any]:
    freq = body.get("frequency") or "12h"
    freq_hours = FREQUENCY_HOURS.get(freq, FREQUENCY_HOURS["12h"])
    now = _now()
    queries = [q.strip() for q in (body.get("search_queries") or []) if q and q.strip()]
    if not queries and body.get("goal"):
        queries = [body["goal"][:120]]

    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": uid,
        "title": (body.get("title") or body.get("goal") or "Custom scout")[:120],
        "goal": (body.get("goal") or "")[:500],
        "scout_type": body.get("scout_type") or "custom",
        "search_queries": queries[:8],
        "location": body.get("location") or "",
        "frequency": freq,
        "frequency_hours": freq_hours,
        "is_active": True if body.get("is_active") is None else bool(body.get("is_active")),
        "auto_generated": False,
        "last_run_at": None,
        "next_run_at": now,
        "created_at": now,
        "updated_at": now,
    }
    await db[SCOUTS_COLLECTION].insert_one(doc)
    return _serialize_doc(doc)


async def update_scout(db, uid: str, scout_id: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    scout = await db[SCOUTS_COLLECTION].find_one({"_id": scout_id, "user_id": uid})
    if not scout:
        return None

    updates: Dict[str, Any] = {"updated_at": _now()}
    for key in ("title", "goal", "location", "scout_type", "is_active"):
        if key in body and body[key] is not None:
            updates[key] = body[key]
    if "search_queries" in body and body["search_queries"] is not None:
        updates["search_queries"] = [q.strip() for q in body["search_queries"] if q and q.strip()][:8]
    if "frequency" in body and body["frequency"]:
        updates["frequency"] = body["frequency"]
        updates["frequency_hours"] = FREQUENCY_HOURS.get(body["frequency"], FREQUENCY_HOURS["12h"])

    await db[SCOUTS_COLLECTION].update_one({"_id": scout_id, "user_id": uid}, {"$set": updates})
    updated = await db[SCOUTS_COLLECTION].find_one({"_id": scout_id})
    return _serialize_doc(updated) if updated else None


async def delete_scout(db, uid: str, scout_id: str) -> bool:
    result = await db[SCOUTS_COLLECTION].delete_one({"_id": scout_id, "user_id": uid})
    return result.deleted_count > 0


async def get_pulse(db, uid: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Top recent scout-sourced opportunities."""
    cutoff = _now() - timedelta(days=7)
    items = await db.action_mode_opportunities.find({
        "user_id": uid,
        "agent": "zilo_scout",
        "created_at": {"$gte": cutoff},
    }).sort([("score", -1), ("created_at", -1)]).to_list(limit)
    for i in items:
        i["_id"] = str(i["_id"])
        if hasattr(i.get("created_at"), "isoformat"):
            i["created_at"] = i["created_at"].isoformat()
    return items


async def _scout_search(queries: List[str], country: str, goal: str) -> List[Dict[str, Any]]:
    """Run focused web search for a scout's query list."""
    from search_engine import run_search_plan

    plan = {
        "queries": queries[:6],
        "reddit_subreddits": [],
        "news_terms": queries[:2],
        "search_us_gov": country.upper() in ("US", "USA", "UNITED STATES"),
        "brave_country": "us" if country.upper() in ("US", "USA") else "xx",
    }

    # Try LLM subreddit discovery for buy-intent scouts
    if any(w in goal.lower() for w in ("reddit", "recommend", "looking for", "forum")):
        try:
            from search_engine import build_search_plan
            enriched = await build_search_plan(goal, goal, country, n_queries=4)
            if enriched.get("reddit_subreddits"):
                plan["reddit_subreddits"] = enriched["reddit_subreddits"][:5]
            if enriched.get("queries"):
                merged = list(dict.fromkeys(queries + enriched["queries"]))
                plan["queries"] = merged[:8]
        except Exception as e:
            logger.debug("[scouts] subreddit plan skipped: %s", e)

    results = await run_search_plan(plan, max_total=60)
    return results


async def _score_and_save(
    db,
    uid: str,
    scout: Dict[str, Any],
    raw_results: List[Dict[str, Any]],
    ctx: Dict[str, Any],
) -> int:
    from action_mode_routes import (
        _add_to_queue,
        _ai_score_results,
        _draft_contextual_comment,
        _log_activity,
    )

    biz_name = ctx.get("business_name", "")
    biz_type = ctx.get("business_type", "business")
    country = ctx.get("country", "")

    biz_context = (
        f"{biz_name} is a {biz_type} business in {country}. "
        f"Goals: {ctx.get('goals') or 'find customers and opportunities'}."
    )

    enriched = await _ai_score_results(
        raw_results,
        context=biz_context,
        agent_goal=scout.get("goal") or scout.get("title", ""),
    )

    cutoff = _now() - timedelta(days=URL_DEDUP_DAYS)
    saved = 0

    for opp in enriched[:MAX_RESULTS_PER_SCOUT]:
        url = opp.get("url", "")
        if not url or not opp.get("title"):
            continue

        existing = await db.action_mode_opportunities.find_one({
            "user_id": uid,
            "url": url,
            "created_at": {"$gte": cutoff},
        })
        if existing:
            continue

        kind = "social"
        if scout.get("scout_type") == "funding":
            kind = "funding"
        elif scout.get("scout_type") == "buy_intent":
            kind = "group"

        await db.action_mode_opportunities.insert_one({
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "kind": kind,
            "agent": "zilo_scout",
            "agent_name": scout.get("title", "Scout"),
            "title": opp["title"],
            "url": url,
            "snippet": opp.get("snippet", ""),
            "score": opp.get("score", 7),
            "scout_id": scout.get("_id"),
            "created_at": _now(),
        })
        saved += 1

        draft = _draft_contextual_comment(
            biz_name,
            biz_type,
            opp.get("snippet", opp.get("title", "")),
            biz_type,
            country,
        )
        await _add_to_queue(
            db, uid, "zilo_scout", "post_comment",
            f"Scout: {opp['title'][:55]}",
            draft,
            {
                "url": url,
                "snippet": opp.get("snippet", "")[:300],
                "scout_id": scout.get("_id"),
                "scout_title": scout.get("title", ""),
            },
        )

    if saved:
        await _log_activity(
            db, uid, "zilo_scout",
            f"🔭 {scout.get('title', 'Scout')}: {saved} new signals",
            f"AI-filtered from {len(raw_results)} web results",
            kind="opportunity",
        )
        try:
            from deal_alerts import _send_push
            await _send_push(
                db, uid,
                title=f"🔭 Scout found {saved} lead{'s' if saved != 1 else ''}",
                body=f"{scout.get('title', 'Scout')}: open Field Agents to review and reply",
                data={"type": "scout_leads", "scout_id": scout.get("_id")},
            )
        except Exception:
            pass

    return saved


async def execute_scout(db, scout: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one scout execution end-to-end."""
    uid = scout["user_id"]
    scout_id = scout["_id"]
    ctx = ctx or await get_biz_context(db, uid)

    exec_id = str(uuid.uuid4())
    started = _now()
    await db[EXECUTIONS_COLLECTION].insert_one({
        "_id": exec_id,
        "scout_id": scout_id,
        "user_id": uid,
        "status": "running",
        "results_found": 0,
        "summary": "",
        "started_at": started,
        "completed_at": None,
    })

    try:
        queries = scout.get("search_queries") or []
        if not queries:
            raise ValueError("Scout has no search queries")

        country = scout.get("location") or ctx.get("country", "")
        goal = scout.get("goal") or scout.get("title", "")

        raw = await _scout_search(queries, country, goal)
        saved = await _score_and_save(db, uid, scout, raw, ctx)

        freq_hours = scout.get("frequency_hours") or FREQUENCY_HOURS.get(scout.get("frequency", "12h"), 12)
        completed = _now()
        next_run = completed + timedelta(hours=freq_hours)

        await db[SCOUTS_COLLECTION].update_one(
            {"_id": scout_id},
            {"$set": {
                "last_run_at": completed,
                "next_run_at": next_run,
                "updated_at": completed,
            }},
        )

        summary = f"Found {saved} opportunities from {len(raw)} results"
        await db[EXECUTIONS_COLLECTION].update_one(
            {"_id": exec_id},
            {"$set": {
                "status": "completed",
                "results_found": saved,
                "summary": summary,
                "completed_at": completed,
            }},
        )

        logger.info("[scouts] executed scout=%s user=%s saved=%d", scout_id, uid, saved)
        return {"scout_id": scout_id, "results_found": saved, "raw_count": len(raw), "summary": summary}

    except Exception as e:
        logger.error("[scouts] execute failed scout=%s: %s", scout_id, e)
        await db[EXECUTIONS_COLLECTION].update_one(
            {"_id": exec_id},
            {"$set": {
                "status": "failed",
                "summary": str(e)[:300],
                "completed_at": _now(),
            }},
        )
        raise


async def find_due_scouts(db, limit: int = 30) -> List[Dict[str, Any]]:
    """Scouts that are active and due to run."""
    now = _now()
    return await db[SCOUTS_COLLECTION].find({
        "is_active": True,
        "$or": [
            {"next_run_at": {"$lte": now}},
            {"next_run_at": None},
            {"next_run_at": {"$exists": False}},
        ],
    }).sort("next_run_at", 1).limit(limit).to_list(limit)


async def is_user_scouts_enabled(db, uid: str) -> bool:
    settings = await db.action_mode_settings.find_one({"user_id": uid}) or {}
    return bool(settings.get("enabled"))

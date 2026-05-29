"""
API Direct — Facebook group search for Field Agents deal alerts.

Uses one server-side APIDIRECT_API_KEY; meters pages per tenant for billing.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://apidirect.io/v1"
USAGE_COLLECTION = "apidirect_usage"
GROUP_CACHE_COLLECTION = "apidirect_group_cache"

# API Direct list price; billable rate is your customer price (markup).
COST_PER_PAGE_USD = float(os.environ.get("APIDIRECT_COST_PER_PAGE", "0.008"))
BILLABLE_PER_PAGE_USD = float(os.environ.get("APIDIRECT_BILLABLE_PER_PAGE", "0.009"))
DEFAULT_MONTHLY_PAGE_LIMIT = int(os.environ.get("APIDIRECT_DEFAULT_MONTHLY_PAGES", "200"))

FB_GROUP_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?facebook\.com/groups/([^/?#]+)",
    re.I,
)


def is_configured() -> bool:
    return bool(os.environ.get("APIDIRECT_API_KEY", "").strip())


def _api_key() -> str:
    return os.environ.get("APIDIRECT_API_KEY", "").strip()


def _month_key(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.utcnow()
    return dt.strftime("%Y-%m")


def parse_facebook_group_slug(url: str) -> Optional[str]:
    """Extract group id or slug from a Facebook group URL."""
    if not url:
        return None
    m = FB_GROUP_RE.search(url.strip())
    return m.group(1) if m else None


def is_facebook_group_url(url: str) -> bool:
    return bool(parse_facebook_group_slug(url))


async def _apidirect_get(path: str, params: Dict[str, Any]) -> Tuple[Optional[Dict], int]:
    """GET apidirect.io; returns (json_body, pages_billed). pages_billed=0 on failure."""
    key = _api_key()
    if not key:
        return None, 0

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(
                f"{BASE_URL}{path}",
                headers={"X-API-Key": key, "Accept": "application/json"},
                params=params,
            )
            if resp.status_code != 200:
                logger.warning(
                    "[apidirect] %s %s -> %s %s",
                    path, params, resp.status_code, resp.text[:200],
                )
                return None, 0
            data = resp.json()
            pages = int(data.get("pages") or params.get("pages") or 1)
            return data, max(pages, 1)
    except Exception as e:
        logger.warning("[apidirect] request failed %s: %s", path, e)
        return None, 0


async def resolve_group(db, group_url: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a group URL to {id, name, url, privacy}.
    Numeric IDs pass through; slugs resolved via API Direct group details ($0.008/request).
    """
    slug = parse_facebook_group_slug(group_url)
    if not slug:
        return None

    if slug.isdigit():
        return {"id": slug, "name": group_url, "url": group_url, "privacy": "unknown"}

    cached = await db[GROUP_CACHE_COLLECTION].find_one({"slug": slug.lower()})
    if cached and cached.get("group_id"):
        return {
            "id": cached["group_id"],
            "name": cached.get("name") or group_url,
            "url": cached.get("url") or group_url,
            "privacy": cached.get("privacy", "unknown"),
        }

    data, _pages = await _apidirect_get("/facebook/group", {"url": group_url})
    group = (data or {}).get("group") or {}
    gid = str(group.get("id") or "").strip()
    if not gid:
        return None

    doc = {
        "slug": slug.lower(),
        "group_id": gid,
        "name": group.get("name") or slug,
        "url": group.get("url") or group_url,
        "privacy": group.get("privacy") or "unknown",
        "updated_at": datetime.utcnow(),
    }
    await db[GROUP_CACHE_COLLECTION].update_one(
        {"slug": slug.lower()},
        {"$set": doc},
        upsert=True,
    )
    return {"id": gid, "name": doc["name"], "url": doc["url"], "privacy": doc["privacy"]}


async def search_group_posts(
    group_id: str,
    query: str,
    *,
    pages: int = 1,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Search posts in one public Facebook group. Returns (posts, pages_billed)."""
    params: Dict[str, Any] = {
        "group_id": group_id,
        "query": (query or "")[:500],
        "pages": max(1, min(int(pages or 1), 10)),
    }
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    data, billed = await _apidirect_get("/facebook/group/search", params)
    posts = (data or {}).get("posts") or []
    return posts, billed


async def _get_usage_doc(db, user_id: str) -> Dict[str, Any]:
    social = await db.action_mode_social.find_one({"user_id": user_id}) or {}
    month = _month_key()
    stored_month = social.get("fb_pages_month")
    used = int(social.get("fb_pages_used") or 0)
    if stored_month != month:
        used = 0
    limit = int(social.get("fb_pages_limit") or DEFAULT_MONTHLY_PAGE_LIMIT)
    return {"month": month, "used": used, "limit": limit}


async def get_user_fb_usage(db, user_id: str) -> Dict[str, Any]:
    doc = await _get_usage_doc(db, user_id)
    remaining = max(0, doc["limit"] - doc["used"])
    return {
        "month": doc["month"],
        "pages_used": doc["used"],
        "pages_limit": doc["limit"],
        "pages_remaining": remaining,
        "cost_per_page_usd": COST_PER_PAGE_USD,
        "billable_per_page_usd": BILLABLE_PER_PAGE_USD,
        "configured": is_configured(),
    }


async def can_use_pages(db, user_id: str, pages: int = 1) -> bool:
    if not is_configured():
        return False
    doc = await _get_usage_doc(db, user_id)
    return doc["used"] + pages <= doc["limit"]


async def record_usage(
    db,
    user_id: str,
    *,
    endpoint: str,
    pages: int,
    group_id: str = "",
    query: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    pages = max(1, int(pages or 1))
    month = _month_key()
    api_cost = round(pages * COST_PER_PAGE_USD, 6)
    billable = round(pages * BILLABLE_PER_PAGE_USD, 6)

    await db[USAGE_COLLECTION].insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "endpoint": endpoint,
        "pages": pages,
        "api_cost_usd": api_cost,
        "billable_usd": billable,
        "group_id": group_id,
        "query": (query or "")[:200],
        "meta": meta or {},
        "created_at": datetime.utcnow(),
    })

    social = await db.action_mode_social.find_one({"user_id": user_id}) or {}
    if social.get("fb_pages_month") != month:
        await db.action_mode_social.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "fb_pages_used": pages,
                    "fb_pages_month": month,
                    "updated_at": datetime.utcnow(),
                },
            },
            upsert=True,
        )
    else:
        await db.action_mode_social.update_one(
            {"user_id": user_id},
            {
                "$inc": {"fb_pages_used": pages},
                "$set": {"fb_pages_month": month, "updated_at": datetime.utcnow()},
            },
            upsert=True,
        )


def _build_queries(keywords: List[str], business_type: str = "") -> List[str]:
    kws = [k.strip() for k in keywords if k and k.strip()]
    if not kws and business_type:
        kws = [business_type.strip()]

    queries: List[str] = []
    for kw in kws[:5]:
        queries.append(kw)
        queries.append(f"looking for {kw}")
        queries.append(f"need {kw}")
        queries.append(f"recommend {kw}")

    # Generic buy-intent searches (cheap signal in local groups)
    queries.extend(["looking for", "need a", "anyone recommend", "who can"])

    seen: set = set()
    out: List[str] = []
    for q in queries:
        qn = q.strip().lower()
        if qn and qn not in seen:
            seen.add(qn)
            out.append(q.strip())
    return out[:10]


async def scan_user_facebook_groups(
    db,
    user_id: str,
    cfg: Dict[str, Any],
    biz: Dict[str, Any],
    *,
    daily_limit: Optional[int] = None,
    max_pages_per_run: int = 15,
) -> Dict[str, Any]:
    """
    Scan saved public Facebook groups via API Direct and queue deal alerts.
    """
    from action_mode_routes import queue_social_match

    if not is_configured():
        return {"alerts": 0, "api_pages": 0, "skipped": "APIDIRECT_API_KEY not set"}

    groups = [
        g.strip()
        for g in (cfg.get("groups") or [])
        if g and is_facebook_group_url(g)
    ]
    keywords = [k.strip() for k in (cfg.get("keywords") or []) if k and k.strip()]
    biz_type = (biz.get("business_type") or biz.get("industry") or "").strip()

    if not groups:
        return {"alerts": 0, "api_pages": 0, "skipped": "no_facebook_groups"}
    if not keywords and not biz_type:
        return {"alerts": 0, "api_pages": 0, "skipped": "no_keywords"}

    limit = daily_limit if daily_limit is not None else int(cfg.get("daily_limit") or 10)
    queries = _build_queries(keywords, biz_type)
    start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

    alerts = 0
    api_pages = 0
    groups_scanned = 0

    for group_url in groups[:8]:
        if alerts >= limit or api_pages >= max_pages_per_run:
            break

        group = await resolve_group(db, group_url)
        if not group:
            logger.info("[apidirect] could not resolve group url=%s user=%s", group_url, user_id)
            continue

        group_id = group["id"]
        group_name = group.get("name") or group_url
        groups_scanned += 1

        for query in queries:
            if alerts >= limit or api_pages >= max_pages_per_run:
                break
            if not await can_use_pages(db, user_id, 1):
                logger.info("[apidirect] monthly page limit reached user=%s", user_id)
                return {
                    "alerts": alerts,
                    "api_pages": api_pages,
                    "groups_scanned": groups_scanned,
                    "skipped": "monthly_limit",
                }

            posts, billed = await search_group_posts(
                group_id,
                query,
                pages=1,
                start_date=start_date,
            )
            if billed:
                await record_usage(
                    db,
                    user_id,
                    endpoint="facebook/group/search",
                    pages=billed,
                    group_id=group_id,
                    query=query,
                    meta={"group_name": group_name, "posts_returned": len(posts)},
                )
                api_pages += billed

            for post in posts:
                if alerts >= limit:
                    break
                text = (post.get("message") or "").strip()
                url = (post.get("url") or "").strip()
                if not text or not url:
                    continue

                author = post.get("author_name") or "Someone"
                post_id = post.get("post_id") or ""

                ok = await queue_social_match(
                    db,
                    user_id,
                    text=text,
                    author=author,
                    group_name=group_name,
                    platform="facebook",
                    url=url,
                    post_id=post_id,
                )
                if ok:
                    alerts += 1

    await db.action_mode_social.update_one(
        {"user_id": user_id},
        {"$set": {"last_fb_scan_at": datetime.utcnow()}},
        upsert=True,
    )

    logger.info(
        "[apidirect] scan user=%s alerts=%d pages=%d groups=%d",
        user_id, alerts, api_pages, groups_scanned,
    )
    return {
        "alerts": alerts,
        "api_pages": api_pages,
        "groups_scanned": groups_scanned,
        "queries_run": len(queries),
    }

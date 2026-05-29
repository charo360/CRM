"""
ScrapeCreators — Facebook group posts, comments, and Marketplace search for Field Agents.

Replaces apidirect for Facebook (apidirect kept for Twitter).
Credits: $0.00188/credit (Freelance) or $0.00099/credit (Business).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

BASE_URL              = "https://api.scrapecreators.com/v1"
USAGE_COLLECTION      = "sc_usage"
COST_PER_CREDIT_USD   = float(os.environ.get("SC_COST_PER_CREDIT", "0.00188"))
BILLABLE_PER_CREDIT   = float(os.environ.get("SC_BILLABLE_PER_CREDIT", "0.003"))
DEFAULT_MONTHLY_LIMIT = int(os.environ.get("SC_DEFAULT_MONTHLY_CREDITS", "500"))


def is_configured() -> bool:
    return bool(os.environ.get("SCRAPECREATORS_API_KEY", "").strip())


def _api_key() -> str:
    return os.environ.get("SCRAPECREATORS_API_KEY", "").strip()


def _month_key() -> str:
    return datetime.utcnow().strftime("%Y-%m")


async def _sc_get(path: str, params: Dict[str, Any]) -> Optional[Dict]:
    key = _api_key()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(
                f"{BASE_URL}{path}",
                headers={"x-api-key": key, "Accept": "application/json"},
                params=params,
            )
            if resp.status_code != 200:
                logger.warning("[sc] %s %s -> %s %s", path, params, resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            if not data.get("success", True):
                logger.warning("[sc] %s error: %s", path, data.get("message", ""))
                return None
            return data
    except Exception as e:
        logger.warning("[sc] request failed %s: %s", path, e)
        return None


# ── Facebook Group Posts ──────────────────────────────────────────────────────

async def get_group_posts(
    group_url: str,
    cursor: Optional[str] = None,
    limit: int = 20,
) -> Tuple[List[Dict], Optional[str], int]:
    """
    Fetch posts from a public Facebook group.
    Returns (posts, next_cursor, credits_used).
    """
    params: Dict[str, Any] = {"url": group_url, "limit": limit}
    if cursor:
        params["cursor"] = cursor

    data = await _sc_get("/facebook/group/posts", params)
    if not data:
        return [], None, 0

    posts = data.get("posts") or []
    next_cursor = data.get("cursor") or None
    return posts, next_cursor, 1  # 1 credit per call


# ── Facebook Post Detail + Comments ──────────────────────────────────────────

async def get_post_detail(post_url: str) -> Tuple[Optional[Dict], int]:
    """
    Fetch a single post's detail including feedback_id needed for comments.
    Returns (post_data, credits_used).
    """
    data = await _sc_get("/facebook/post", {"url": post_url})
    if not data:
        return None, 0
    return data, 1


async def get_post_comments(
    feedback_id: str,
    cursor: Optional[str] = None,
) -> Tuple[List[Dict], Optional[str], int]:
    """
    Fetch comments for a post using its feedback_id.
    Returns (comments, next_cursor, credits_used).
    """
    params: Dict[str, Any] = {"feedback_id": feedback_id}
    if cursor:
        params["cursor"] = cursor

    data = await _sc_get("/facebook/post/comments", params)
    if not data:
        return [], None, 0

    comments = data.get("comments") or []
    next_cursor = data.get("cursor") if data.get("has_next_page") else None
    return comments, next_cursor, 1


# ── Facebook Marketplace ──────────────────────────────────────────────────────

async def search_marketplace(
    query: str,
    lat: float,
    lng: float,
    radius_km: int = 50,
) -> Tuple[List[Dict], int]:
    """
    Search Facebook Marketplace listings near a location.
    Returns (listings, credits_used).
    """
    data = await _sc_get("/facebook/marketplace/search", {
        "query": query,
        "lat": lat,
        "lng": lng,
        "radius": radius_km,
    })
    if not data:
        return [], 0

    listings = data.get("listings") or []
    return listings, max(1, len(listings) // 10 + 1)


# ── Usage tracking ────────────────────────────────────────────────────────────

async def _get_usage(db, user_id: str) -> Dict:
    doc = await db.action_mode_social.find_one({"user_id": user_id}) or {}
    month = _month_key()
    used = int(doc.get("sc_credits_used") or 0) if doc.get("sc_credits_month") == month else 0
    limit = int(doc.get("sc_credits_limit") or DEFAULT_MONTHLY_LIMIT)
    return {"month": month, "used": used, "limit": limit}


async def can_use_credits(db, user_id: str, credits: int = 1) -> bool:
    if not is_configured():
        return False
    doc = await _get_usage(db, user_id)
    return doc["used"] + credits <= doc["limit"]


async def record_usage(
    db,
    user_id: str,
    *,
    endpoint: str,
    credits: int,
    meta: Optional[Dict] = None,
) -> None:
    credits = max(1, int(credits or 1))
    month = _month_key()

    await db[USAGE_COLLECTION].insert_one({
        "_id":           str(uuid.uuid4()),
        "user_id":       user_id,
        "endpoint":      endpoint,
        "credits":       credits,
        "api_cost_usd":  round(credits * COST_PER_CREDIT_USD, 6),
        "billable_usd":  round(credits * BILLABLE_PER_CREDIT, 6),
        "meta":          meta or {},
        "created_at":    datetime.utcnow(),
    })

    doc = await db.action_mode_social.find_one({"user_id": user_id}) or {}
    if doc.get("sc_credits_month") != month:
        await db.action_mode_social.update_one(
            {"user_id": user_id},
            {"$set": {"sc_credits_used": credits, "sc_credits_month": month, "updated_at": datetime.utcnow()}},
            upsert=True,
        )
    else:
        await db.action_mode_social.update_one(
            {"user_id": user_id},
            {"$inc": {"sc_credits_used": credits}, "$set": {"sc_credits_month": month, "updated_at": datetime.utcnow()}},
            upsert=True,
        )


async def get_user_usage(db, user_id: str) -> Dict:
    doc = await _get_usage(db, user_id)
    return {
        "month":                  doc["month"],
        "credits_used":           doc["used"],
        "credits_limit":          doc["limit"],
        "credits_remaining":      max(0, doc["limit"] - doc["used"]),
        "cost_per_credit_usd":    COST_PER_CREDIT_USD,
        "billable_per_credit_usd":BILLABLE_PER_CREDIT,
        "configured":             is_configured(),
    }


# ── Intent helpers ────────────────────────────────────────────────────────────

INTENT_SIGNALS = [
    "looking for", "need a", "need some", "where can i", "who can",
    "anyone selling", "anyone supply", "recommend", "supplier", "vendor",
    "wtb", "want to buy", "where to buy", "how much", "price?", "dm me",
    "inbox me", "please help", "urgently need", "seeking",
]


def _has_intent(text: str) -> bool:
    t = text.lower()
    return any(sig in t for sig in INTENT_SIGNALS)


def _combine_text(post_text: str, comments: List[Dict]) -> str:
    parts = [post_text]
    for c in comments[:10]:
        ct = (c.get("text") or "").strip()
        if ct:
            parts.append(ct)
    return "\n".join(parts)


# ── Main scanner ──────────────────────────────────────────────────────────────

async def scan_user_facebook_groups(
    db,
    user_id: str,
    cfg: Dict[str, Any],
    biz: Dict[str, Any],
    *,
    max_credits_per_run: int = 30,
) -> Dict[str, Any]:
    """
    Scan configured Facebook groups for buying intent using ScrapeCreators.
    Fetches posts + comments to detect intent signals.
    """
    from action_mode_routes import queue_social_match

    if not is_configured():
        return {"alerts": 0, "credits": 0, "skipped": "SCRAPECREATORS_API_KEY not set"}

    groups = [g.strip() for g in (cfg.get("groups") or []) if g and "facebook.com/groups" in g]
    keywords = [k.strip().lower() for k in (cfg.get("keywords") or []) if k.strip()]
    biz_type = (biz.get("business_type") or biz.get("industry") or "").strip().lower()
    if biz_type and biz_type not in keywords:
        keywords.append(biz_type)

    if not groups:
        return {"alerts": 0, "credits": 0, "skipped": "no_facebook_groups"}

    daily_limit = int(cfg.get("daily_limit") or 10)
    alerts = 0
    credits_used = 0
    groups_scanned = 0

    for group_url in groups[:8]:
        if alerts >= daily_limit or credits_used >= max_credits_per_run:
            break
        if not await can_use_credits(db, user_id, 1):
            return {"alerts": alerts, "credits": credits_used, "groups_scanned": groups_scanned, "skipped": "monthly_limit"}

        posts, _cursor, c = await get_group_posts(group_url, limit=20)
        if c:
            await record_usage(db, user_id, endpoint="facebook/group/posts", credits=c,
                               meta={"group_url": group_url, "posts": len(posts)})
            credits_used += c

        groups_scanned += 1
        group_name = group_url.split("/groups/")[-1].split("/")[0]

        for post in posts:
            if alerts >= daily_limit or credits_used >= max_credits_per_run:
                break

            post_text = (post.get("text") or "").strip()
            post_url  = (post.get("url") or "").strip()
            author    = (post.get("author") or {}).get("name") or "Someone"
            comment_count = int(post.get("commentCount") or 0)
            feedback_id   = post.get("feedback_id") or ""
            post_id       = post.get("id") or ""

            if not post_text or not post_url:
                continue

            # Fetch comments if post has them (key for intent detection)
            comments: List[Dict] = []
            if comment_count > 0 and feedback_id and await can_use_credits(db, user_id, 1):
                cmts, _, cc = await get_post_comments(feedback_id)
                if cc:
                    await record_usage(db, user_id, endpoint="facebook/post/comments", credits=cc,
                                       meta={"post_id": post_id, "comment_count": comment_count})
                    credits_used += cc
                comments = cmts

            # Score intent from post + comments combined
            full_text = _combine_text(post_text, comments)

            # Match against keywords or generic intent signals
            keyword_match = keywords and any(kw in full_text.lower() for kw in keywords)
            intent_match  = _has_intent(full_text)

            if not (keyword_match or intent_match):
                continue

            # Build enriched text with top comments for the alert
            comment_snippets = [c.get("text", "")[:120] for c in comments[:3] if c.get("text")]
            alert_text = post_text
            if comment_snippets:
                alert_text += "\n💬 " + " | ".join(comment_snippets)

            ok = await queue_social_match(
                db, user_id,
                text=alert_text,
                author=author,
                group_name=group_name,
                platform="facebook",
                url=post_url,
                post_id=post_id,
            )
            if ok:
                alerts += 1

    await db.action_mode_social.update_one(
        {"user_id": user_id},
        {"$set": {"last_sc_scan_at": datetime.utcnow()}},
        upsert=True,
    )

    logger.info("[sc] scan user=%s alerts=%d credits=%d groups=%d", user_id, alerts, credits_used, groups_scanned)
    return {"alerts": alerts, "credits": credits_used, "groups_scanned": groups_scanned}


async def scan_marketplace(
    db,
    user_id: str,
    cfg: Dict[str, Any],
    biz: Dict[str, Any],
    *,
    max_credits_per_run: int = 10,
) -> Dict[str, Any]:
    """
    Search Facebook Marketplace for buying/selling signals near the user's location.
    """
    from action_mode_routes import queue_social_match

    if not is_configured():
        return {"alerts": 0, "credits": 0, "skipped": "SCRAPECREATORS_API_KEY not set"}

    raw_lat = cfg.get("marketplace_lat") or biz.get("lat")
    raw_lng = cfg.get("marketplace_lng") or biz.get("lng")
    if not raw_lat or not raw_lng:
        return {"alerts": 0, "credits": 0, "skipped": "no_location_set"}

    lat    = float(raw_lat)
    lng    = float(raw_lng)
    radius = int(cfg.get("marketplace_radius_km") or 50)

    keywords = [k.strip() for k in (cfg.get("keywords") or []) if k.strip()]
    biz_type = (biz.get("business_type") or biz.get("industry") or "").strip()
    queries  = list(dict.fromkeys([biz_type] + keywords))[:5]
    queries  = [q for q in queries if q]

    if not queries:
        return {"alerts": 0, "credits": 0, "skipped": "no_keywords"}

    daily_limit  = int(cfg.get("daily_limit") or 10)
    alerts       = 0
    credits_used = 0

    for query in queries:
        if alerts >= daily_limit or credits_used >= max_credits_per_run:
            break
        if not await can_use_credits(db, user_id, 1):
            break

        listings, c = await search_marketplace(query, lat, lng, radius)
        if c:
            await record_usage(db, user_id, endpoint="facebook/marketplace/search", credits=c,
                               meta={"query": query, "listings": len(listings)})
            credits_used += c

        for listing in listings:
            if alerts >= daily_limit:
                break
            title    = (listing.get("title") or "").strip()
            url      = (listing.get("url") or "").strip()
            price    = (listing.get("price") or {}).get("formatted_amount") or ""
            location = (listing.get("location") or {}).get("display_name") or ""
            if not title or not url:
                continue

            text = f"{title}"
            if price:
                text += f" — {price}"
            if location:
                text += f" ({location})"

            ok = await queue_social_match(
                db, user_id,
                text=text,
                author="Marketplace Seller",
                group_name="Facebook Marketplace",
                platform="facebook_marketplace",
                url=url,
                post_id=listing.get("id") or "",
            )
            if ok:
                alerts += 1

    logger.info("[sc] marketplace user=%s alerts=%d credits=%d", user_id, alerts, credits_used)
    return {"alerts": alerts, "credits": credits_used}

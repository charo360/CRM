"""
Social Engagement Syncer — background worker that pulls engagement metrics for
published posts from Zernio and stores them in MongoDB.

Runs every 30 minutes. Finds all `published` posts that have a `zernio_post_id`
and haven't been synced recently, fetches likes/comments/shares/reach/clicks from
Zernio, and writes them back to `scheduled_posts`.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

ZERNIO_BASE = os.environ.get("ZERNIO_API_BASE", "https://zernio.com/api/v1").rstrip("/")
ZERNIO_API_KEY = os.environ.get("ZERNIO_API_KEY", "").strip()

# Re-sync engagement no more than once every 25 minutes per post
_SYNC_INTERVAL_MINUTES = 25


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {ZERNIO_API_KEY}",
        "Content-Type": "application/json",
    }


async def _fetch_post_analytics(zernio_post_id: str, db, user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch engagement metrics for a single post from Zernio. Includes fallback for LinkedIn."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{ZERNIO_BASE}/posts/{zernio_post_id}/analytics",
                headers=_headers(),
            )
            if resp.status_code != 404:
                resp.raise_for_status()
                data = resp.json()
                # Normalise — Zernio may nest metrics under different keys
                metrics = data.get("analytics") or data.get("metrics") or data.get("data") or data
                if isinstance(metrics, dict):
                    return {
                        "likes":     int(metrics.get("likes")     or metrics.get("like_count")    or 0),
                        "comments":  int(metrics.get("comments")  or metrics.get("comment_count") or 0),
                        "shares":    int(metrics.get("shares")    or metrics.get("share_count")   or 0),
                        "reach":     int(metrics.get("reach")     or metrics.get("impressions")   or 0),
                        "clicks":    int(metrics.get("clicks")    or metrics.get("click_count")   or 0),
                        "saves":     int(metrics.get("saves")     or metrics.get("save_count")    or 0),
                        "raw":       metrics,
                    }
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            logger.warning("[engagement_syncer] Zernio %s for post %s: %s",
                           e.response.status_code, zernio_post_id, e.response.text[:200])
    except Exception as e:
        logger.warning("[engagement_syncer] Failed primary fetch for %s: %s", zernio_post_id, e)

    # Fallback for platforms like LinkedIn where the direct /analytics endpoint 404s
    if not user_id:
        return None

    try:
        user = await db.users.find_one({"_id": user_id})
        profile_id = user.get("zernio_profile_id") if user else None
        if not profile_id:
            return None

        async with httpx.AsyncClient(timeout=20.0) as client:
            acc_resp = await client.get(
                f"{ZERNIO_BASE}/accounts",
                params={"profileId": profile_id},
                headers=_headers(),
            )
            if acc_resp.status_code != 200:
                return None
            
            acc_data = acc_resp.json()
            accounts = acc_data.get("accounts") or acc_data.get("data") or []
            if not isinstance(accounts, list):
                return None
                
            for acc in accounts:
                if not isinstance(acc, dict):
                    continue
                acc_id = acc.get("accountId") or acc.get("account_id") or acc.get("pageId") or acc.get("id")
                if not acc_id:
                    continue
                
                posts_resp = await client.get(
                    f"{ZERNIO_BASE}/accounts/{acc_id}/posts",
                    headers=_headers(),
                )
                if posts_resp.status_code != 200:
                    continue
                    
                posts_data = posts_resp.json()
                posts_list = []
                for k in ("data", "posts", "results"):
                    c = posts_data.get(k)
                    if isinstance(c, list):
                        posts_list = c
                        break
                if not posts_list and isinstance(posts_data, list):
                    posts_list = posts_data

                for p in posts_list:
                    if not isinstance(p, dict):
                        continue
                        
                    p_ids = [str(x) for x in (
                        p.get("id"), p.get("_id"), p.get("postId"), 
                        p.get("post_id"), p.get("platformPostId")
                    ) if x]
                    
                    if zernio_post_id in p_ids:
                        a = p.get("analytics") or p.get("metrics") or p.get("engagement") or p
                        if not isinstance(a, dict):
                            a = {}
                        
                        def _e(keys):
                            for k in keys:
                                v = a.get(k) or p.get(k)
                                if v is not None:
                                    try: return int(v)
                                    except: pass
                            return 0
                            
                        return {
                            "likes": _e(["likes", "likeCount", "like_count"]),
                            "comments": _e(["comments", "commentCount", "comment_count"]),
                            "shares": _e(["shares", "shareCount", "share_count", "reshares"]),
                            "reach": _e(["reach", "impressions", "views", "videoViews"]),
                            "clicks": _e(["clicks", "clickCount", "click_count", "linkClicks"]),
                            "saves": _e(["saves", "saveCount", "save_count"]),
                            "raw": a,
                        }
    except Exception as e:
        logger.warning("[engagement_syncer] Fallback failed for %s: %s", zernio_post_id, e)
        
    return None


async def run_engagement_syncer(db) -> None:
    """Main loop — runs forever, syncs engagement every 30 minutes."""
    logger.info("[engagement_syncer] Started. Syncing every 30 min.")
    while True:
        await asyncio.sleep(1800)  # 30 minutes
        if not ZERNIO_API_KEY:
            continue

        try:
            cutoff = datetime.utcnow() - timedelta(minutes=_SYNC_INTERVAL_MINUTES)

            # Find published posts with a Zernio ID that are due for a sync
            due: List[Dict[str, Any]] = await db.scheduled_posts.find({
                "status": "published",
                "zernio_post_id": {"$exists": True, "$ne": None},
                "$or": [
                    {"engagement_synced_at": None},
                    {"engagement_synced_at": {"$lte": cutoff}},
                    {"engagement_synced_at": {"$exists": False}},
                ],
            }).to_list(100)

            if not due:
                continue

            logger.info("[engagement_syncer] Syncing %d posts", len(due))

            for post in due:
                zid = post.get("zernio_post_id")
                if not zid:
                    continue

                metrics = await _fetch_post_analytics(zid, db, post.get("user_id"))
                now = datetime.utcnow()

                if metrics:
                    await db.scheduled_posts.update_one(
                        {"_id": post["_id"]},
                        {"$set": {
                            "engagement": metrics,
                            "engagement_synced_at": now,
                            "updated_at": now,
                        }},
                    )
                    logger.info(
                        "[engagement_syncer] Post %s synced — likes=%d reach=%d",
                        post["_id"], metrics["likes"], metrics["reach"],
                    )
                else:
                    # Still update sync time so we don't hammer a 404 every cycle
                    await db.scheduled_posts.update_one(
                        {"_id": post["_id"]},
                        {"$set": {"engagement_synced_at": now}},
                    )

        except Exception as e:
            logger.exception("[engagement_syncer] Unexpected error in sync loop: %s", e)

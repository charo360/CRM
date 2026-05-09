"""
Social Post Publisher — background worker that publishes scheduled posts via Zernio.

Runs every 60 seconds. Finds all `scheduled` posts whose `scheduled_at` is in the past,
attempts to publish them via the Zernio API, and updates their status to `published` or `failed`.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

ZERNIO_BASE = os.environ.get("ZERNIO_API_BASE", "https://zernio.com/api/v1").rstrip("/")
ZERNIO_API_KEY = os.environ.get("ZERNIO_API_KEY", "").strip()

# Platform name mapping: our internal name → Zernio platform slug
_PLATFORM_MAP = {
    "facebook": "facebook",
    "instagram": "instagram",
    "linkedin": "linkedin",
    "x": "twitter",
    "twitter": "twitter",
    "tiktok": "tiktok",
}


async def _get_zernio_profile_id(db, user_id: str) -> str | None:
    """Return the Zernio profile ID for a user, creating one if needed."""
    user = await db.users.find_one({"_id": user_id})
    if not user:
        return None
    pid = user.get("zernio_profile_id")
    if pid:
        return pid
    # Try to create one via the Zernio API
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{ZERNIO_BASE}/profiles",
                headers={"Authorization": f"Bearer {ZERNIO_API_KEY}", "Content-Type": "application/json"},
                json={"name": user.get("business_name") or user.get("name") or "CRM User"},
            )
            resp.raise_for_status()
            pid = resp.json().get("id") or resp.json().get("profileId")
            if pid:
                await db.users.update_one({"_id": user_id}, {"$set": {"zernio_profile_id": pid}})
                return pid
    except Exception as e:
        logger.warning("[social_publisher] Could not create Zernio profile for %s: %s", user_id, e)
    return None


async def _publish_post(post: Dict[str, Any], profile_id: str) -> Dict[str, Any]:
    """Push a single post to Zernio. Returns dict with success flag and Zernio post ID."""
    channels = post.get("channels") or ["facebook"]
    platforms = [_PLATFORM_MAP.get(c, c) for c in channels]

    body: Dict[str, Any] = {
        "profileId": profile_id,
        "content": post.get("body") or "",
        "platforms": platforms,
        "scheduledAt": post.get("scheduled_at").isoformat()
            if hasattr(post.get("scheduled_at"), "isoformat")
            else str(post.get("scheduled_at", "")),
    }
    if post.get("image_url"):
        body["mediaUrls"] = [post["image_url"]]
    elif post.get("assets"):
        urls = [a.get("s3_url") or a.get("preview_data_url") for a in post["assets"] if a.get("s3_url") or a.get("preview_data_url")]
        if urls:
            body["mediaUrls"] = urls
    if post.get("link_url"):
        body["linkUrl"] = post["link_url"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{ZERNIO_BASE}/posts",
                headers={"Authorization": f"Bearer {ZERNIO_API_KEY}", "Content-Type": "application/json"},
                json=body,
            )
            if not resp.is_success:
                # Extract the API error message from the response body if possible
                try:
                    err_body = resp.json()
                    api_msg = (
                        err_body.get("message")
                        or err_body.get("error")
                        or err_body.get("detail")
                        or str(err_body)
                    )
                except Exception:
                    api_msg = resp.text[:300] or f"HTTP {resp.status_code}"
                error_reason = f"HTTP {resp.status_code}: {api_msg}"
                logger.error("[social_publisher] Failed to publish post %s: %s", post["_id"], error_reason)
                return {"success": False, "zernio_post_id": None, "error": error_reason}
            data = resp.json()
            # Extract Zernio's post ID from the response (try common key names)
            post_obj = data.get("post") or data.get("data") or data
            zernio_post_id = (
                post_obj.get("_id") or post_obj.get("id") or post_obj.get("postId")
                if isinstance(post_obj, dict) else None
            )
            logger.info("[social_publisher] Published post %s → Zernio id=%s", post["_id"], zernio_post_id)
            return {"success": True, "zernio_post_id": zernio_post_id, "error": None}
    except Exception as e:
        error_reason = str(e)
        logger.error("[social_publisher] Failed to publish post %s: %s", post["_id"], error_reason)
        return {"success": False, "zernio_post_id": None, "error": error_reason}


async def run_publisher(db) -> None:
    """Main loop — runs forever, checks every 60 seconds."""
    logger.info("[social_publisher] Started. Checking every 60 s.")
    while True:
        await asyncio.sleep(60)
        if not ZERNIO_API_KEY:
            continue  # Skip silently if Zernio not configured
        try:
            now = datetime.utcnow()
            # Find all due scheduled posts
            due: List[Dict[str, Any]] = await db.scheduled_posts.find({
                "status": "scheduled",
                "scheduled_at": {"$lte": now},
            }).to_list(50)

            if not due:
                continue

            logger.info("[social_publisher] %d posts due for publishing", len(due))

            # Group by user so we fetch each profile once
            by_user: Dict[str, List[Dict[str, Any]]] = {}
            for post in due:
                uid = str(post.get("user_id", ""))
                by_user.setdefault(uid, []).append(post)

            for user_id, posts in by_user.items():
                profile_id = await _get_zernio_profile_id(db, user_id)
                for post in posts:
                    pid = str(post["_id"])
                    db_update: Dict[str, Any] = {"updated_at": datetime.utcnow()}
                    if profile_id:
                        result = await _publish_post(post, profile_id)
                        db_update["status"] = "published" if result["success"] else "failed"
                        if result.get("zernio_post_id"):
                            db_update["zernio_post_id"] = result["zernio_post_id"]
                            db_update["engagement_synced_at"] = None
                        if result.get("error"):
                            db_update["publish_error"] = result["error"]
                        elif result["success"]:
                            db_update["publish_error"] = None
                    else:
                        # No Zernio profile — mark failed so it doesn't loop forever
                        db_update["status"] = "failed"
                        db_update["publish_error"] = "No publishing profile found. Check that your Zernio account is connected under Integrations."
                        logger.warning("[social_publisher] No Zernio profile for user %s — marking post %s failed", user_id, pid)

                    await db.scheduled_posts.update_one(
                        {"_id": pid},
                        {"$set": db_update},
                    )

        except Exception as e:
            logger.exception("[social_publisher] Unexpected error in publish loop: %s", e)

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


async def _get_zernio_account_ids(profile_id: str) -> Dict[str, str]:
    """
    Fetch the connected social-account IDs for a Zernio profile.

    Zernio requires platforms in the form [{"platform": "facebook", "accountId": "xxx"}].
    Returns a dict mapping platform slug → accountId, e.g.
        {"facebook": "acc_abc123", "instagram": "acc_def456"}
    An empty dict means no connected accounts were found or the request failed.
    """
    if not ZERNIO_API_KEY or not profile_id:
        return {}

    headers = {"Authorization": f"Bearer {ZERNIO_API_KEY}"}

    # Primary endpoint: GET /accounts?profileId=<id>  (same as the web routes use)
    # Use httpx params= so the profile_id is properly URL-encoded.
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ZERNIO_BASE}/accounts",
                headers=headers,
                params={"profileId": profile_id},
            )
        if resp.is_success:
            raw = resp.json()
            items = (
                raw.get("accounts")
                or raw.get("data")
                or (raw if isinstance(raw, list) else [])
            )
            result: Dict[str, str] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                platform = (item.get("platform") or item.get("type") or "").lower()
                acct_id = (
                    item.get("accountId")
                    or item.get("id")
                    or item.get("_id")
                )
                if platform and acct_id:
                    result[platform] = str(acct_id)
            if result:
                logger.info(
                    "[social_publisher] Fetched %d connected account(s) for profile %s",
                    len(result), profile_id,
                )
                return result
            logger.debug(
                "[social_publisher] /accounts returned success but no usable accounts for profile %s: %s",
                profile_id, raw,
            )
        else:
            logger.debug(
                "[social_publisher] /accounts returned HTTP %s for profile %s: %s",
                resp.status_code, profile_id, resp.text[:200],
            )
    except Exception as exc:
        logger.debug("[social_publisher] /accounts fetch failed for profile %s: %s", profile_id, exc)

    logger.warning(
        "[social_publisher] No connected social accounts found for profile %s. "
        "Make sure social accounts are linked under Integrations → Social Inbox.",
        profile_id,
    )
    return {}


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
    platform_slugs = [_PLATFORM_MAP.get(c, c) for c in channels]

    # Zernio requires platforms as objects: [{"platform": "...", "accountId": "..."}]
    account_map = await _get_zernio_account_ids(profile_id)

    platforms_payload: List[Dict[str, str]] = []
    missing_accounts: List[str] = []
    for slug in platform_slugs:
        acct_id = account_map.get(slug)
        if acct_id:
            platforms_payload.append({"platform": slug, "accountId": acct_id})
        else:
            missing_accounts.append(slug)

    if missing_accounts:
        logger.warning(
            "[social_publisher] Post %s: could not find accountIds for platforms: %s",
            post["_id"], missing_accounts,
        )

    if not platforms_payload:
        # No real account IDs — fail with a clear, actionable error instead of
        # sending a bogus accountId (which causes Zernio's "Invalid platforms format" 400).
        error_msg = (
            f"No connected social account found for platform(s): "
            f"{', '.join(platform_slugs)}. "
            "Please connect your social accounts under Integrations → Social Inbox."
        )
        logger.error("[social_publisher] Post %s: %s", post["_id"], error_msg)
        return {"success": False, "zernio_post_id": None, "error": error_msg}

    body: Dict[str, Any] = {
        "profileId": profile_id,
        "content": post.get("body") or "",
        "platforms": platforms_payload,
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

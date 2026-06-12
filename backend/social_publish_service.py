"""
Push CRM scheduled posts to social platforms.

Facebook, Instagram, YouTube, LinkedIn, X, and TikTok use Composio (official OAuth).
LinkedIn Premium (Unipile) handles posting, inbox, InMail, and Sales Navigator in one connect.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

ZERNIO_BASE = os.environ.get("ZERNIO_API_BASE", "https://zernio.com/api/v1").rstrip("/")
ZERNIO_API_KEY = os.environ.get("ZERNIO_API_KEY", "").strip()

_PLATFORM_MAP = {
    "facebook": "facebook",
    "instagram": "instagram",
    "linkedin": "linkedin",
    "x": "twitter",
    "twitter": "twitter",
    "tiktok": "tiktok",
}


def _is_public_url(url: str) -> bool:
    u = (url or "").strip()
    return u.startswith("http://") or u.startswith("https://")


def _as_utc_iso(dt: Any) -> str:
    if hasattr(dt, "isoformat"):
        if getattr(dt, "tzinfo", None) is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        iso = dt.isoformat()
        if "+" not in iso and not iso.endswith("Z"):
            iso += "Z"
        return iso
    return str(dt or "")


def _build_media_items(post: Dict[str, Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen: set[str] = set()

    def _add(url: str, mime: str = "image/jpeg") -> None:
        u = url.strip()
        if not _is_public_url(u) or u in seen:
            return
        seen.add(u)
        media_type = "video" if mime.lower().startswith("video/") else "image"
        items.append({"type": media_type, "url": u})

    if _is_public_url(post.get("image_url") or ""):
        _add(post["image_url"].strip())
    for asset in post.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        url = (asset.get("s3_url") or "").strip()
        if _is_public_url(url):
            _add(url, asset.get("mime_type") or "image/jpeg")
    return items


async def _upload_data_url(data_url: str, filename: str) -> Optional[str]:
    data_url = (data_url or "").strip()
    if not data_url.startswith("data:"):
        return None
    try:
        from image_handler import ImageUploadHandler, S3Handler

        if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
            return await S3Handler.upload_file(data_url, filename)
        result = await ImageUploadHandler.upload_base64_to_cloudinary(data_url, filename)
        return result.get("image_url") or result.get("url")
    except Exception as exc:
        logger.error("[social_publish] Media upload failed for %s: %s", filename, exc)
        return None


def _post_has_unresolved_media(post: Dict[str, Any]) -> bool:
    if (post.get("image_url") or "").strip().startswith("data:"):
        return True
    for asset in post.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        if (asset.get("preview_data_url") or "").strip().startswith("data:"):
            if not _is_public_url(asset.get("s3_url") or ""):
                return True
    return False


async def resolve_post_media(post: Dict[str, Any]) -> tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Upload local preview assets and return Zernio mediaItems + DB patches."""
    media_items: List[Dict[str, str]] = []
    patches: Dict[str, Any] = {}
    seen: set[str] = set()

    async def _add(url: str, mime: str = "image/jpeg") -> None:
        u = url.strip()
        if not _is_public_url(u) or u in seen:
            return
        seen.add(u)
        media_type = "video" if mime.lower().startswith("video/") else "image"
        media_items.append({"type": media_type, "url": u})

    image_url = (post.get("image_url") or "").strip()
    if image_url.startswith("data:"):
        uploaded = await _upload_data_url(image_url, "social-post.jpg")
        if uploaded:
            patches["image_url"] = uploaded
            await _add(uploaded)
    elif _is_public_url(image_url):
        await _add(image_url)

    updated_assets: List[Dict[str, Any]] = []
    for i, raw in enumerate(post.get("assets") or []):
        if not isinstance(raw, dict):
            continue
        asset = dict(raw)
        mime = (asset.get("mime_type") or "image/jpeg").lower()
        url = (asset.get("s3_url") or "").strip()
        preview = (asset.get("preview_data_url") or "").strip()

        if not _is_public_url(url):
            if preview.startswith("data:"):
                fname = asset.get("file_name") or f"social-asset-{i}.jpg"
                uploaded = await _upload_data_url(preview, fname)
                if uploaded:
                    asset["s3_url"] = uploaded
                    url = uploaded
            elif _is_public_url(preview):
                asset["s3_url"] = preview
                url = preview

        if _is_public_url(url):
            await _add(url, mime)
        updated_assets.append(asset)

    if updated_assets:
        patches["assets"] = updated_assets

    return media_items, patches


async def _resolve_user_doc(db, tenant_id: str) -> Optional[Dict[str, Any]]:
    """Resolve the user document that owns the Zernio profile for a tenant."""
    user = await db.users.find_one(
        {"_id": tenant_id},
        {"zernio_profile_id": 1, "business_name": 1, "name": 1},
    )
    if user:
        return user
    return await db.users.find_one(
        {"business_id": tenant_id},
        {"zernio_profile_id": 1, "business_name": 1, "name": 1},
    )


async def get_zernio_profile_id(db, tenant_id: str) -> Optional[str]:
    user = await _resolve_user_doc(db, tenant_id)
    if not user:
        return None
    pid = user.get("zernio_profile_id")
    if pid:
        return str(pid)
    if not ZERNIO_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{ZERNIO_BASE}/profiles",
                headers={"Authorization": f"Bearer {ZERNIO_API_KEY}", "Content-Type": "application/json"},
                json={"name": user.get("business_name") or user.get("name") or "CRM User"},
            )
            resp.raise_for_status()
            data = resp.json()
            profile = data.get("profile") or data
            pid = profile.get("_id") or profile.get("id") or profile.get("profileId")
            if pid:
                await db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"zernio_profile_id": pid}},
                )
                return str(pid)
    except Exception as exc:
        logger.warning("[social_publish] Could not create Zernio profile for %s: %s", tenant_id, exc)
    return None


async def _get_zernio_account_ids(profile_id: str) -> Dict[str, str]:
    if not ZERNIO_API_KEY or not profile_id:
        return {}
    headers = {"Authorization": f"Bearer {ZERNIO_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{ZERNIO_BASE}/accounts",
                headers=headers,
                params={"profileId": profile_id},
            )
        if not resp.is_success:
            return {}
        raw = resp.json()
        items = raw.get("accounts") or raw.get("data") or (raw if isinstance(raw, list) else [])
        result: Dict[str, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            platform = (item.get("platform") or item.get("type") or "").lower()
            acct_id = item.get("accountId") or item.get("id") or item.get("_id")
            if platform and acct_id:
                result[platform] = str(acct_id)
        return result
    except Exception as exc:
        logger.debug("[social_publish] /accounts fetch failed for profile %s: %s", profile_id, exc)
        return {}


def _build_zernio_body(
    post: Dict[str, Any],
    profile_id: str,
    account_map: Dict[str, str],
    media_items: Optional[List[Dict[str, str]]] = None,
) -> tuple[Dict[str, Any], Optional[str]]:
    channels = post.get("channels") or ["facebook"]
    platform_slugs = [_PLATFORM_MAP.get(c, c) for c in channels]

    platforms_payload: List[Dict[str, str]] = []
    missing: List[str] = []
    for slug in platform_slugs:
        acct_id = account_map.get(slug)
        if acct_id:
            platforms_payload.append({"platform": slug, "accountId": acct_id})
        else:
            missing.append(slug)

    if missing:
        logger.warning(
            "[social_publish] Post %s: missing accountIds for: %s",
            post.get("_id"),
            missing,
        )

    if not platforms_payload:
        return {}, (
            f"No connected social account found for platform(s): {', '.join(platform_slugs)}. "
            "Connect accounts under Integrations → Social Inbox."
        )

    title = (post.get("title") or "").strip()
    content = (post.get("body") or "").strip()
    if title and title not in content and not content.startswith(title):
        content = f"{title}\n\n{content}".strip() if content else title

    link_url = (post.get("link_url") or "").strip()
    if link_url and link_url not in content:
        content = f"{content}\n\n{link_url}".strip() if content else link_url

    body: Dict[str, Any] = {
        "profileId": profile_id,
        "title": title or None,
        "content": content,
        "platforms": platforms_payload,
        "timezone": "UTC",
    }
    if body["title"] is None:
        del body["title"]

    resolved_media = media_items if media_items is not None else _build_media_items(post)
    if resolved_media:
        body["mediaItems"] = resolved_media
    elif _post_has_unresolved_media(post):
        return {}, (
            "Post media could not be uploaded. Attach images again or check "
            "that AWS S3 / image upload is configured on the server."
        )

    status = (post.get("status") or "draft").strip().lower()
    sched_at = post.get("scheduled_at")
    now = datetime.utcnow()
    sched_naive = sched_at
    if hasattr(sched_at, "tzinfo") and sched_at.tzinfo is not None:
        sched_naive = sched_at.astimezone(timezone.utc).replace(tzinfo=None)

    publish_immediately = status == "published"
    if status == "scheduled" and sched_naive and sched_naive <= now:
        publish_immediately = True

    if publish_immediately:
        body["publishNow"] = True
    elif status == "scheduled" and sched_naive:
        body["scheduledFor"] = _as_utc_iso(sched_naive)
    else:
        return {}, "Post must be scheduled or set to publish now."

    return body, None


async def push_post_to_zernio(db, post: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create/publish a CRM post on Zernio.
    Returns {success, zernio_post_id, error, crm_status}.
    """
    if not ZERNIO_API_KEY:
        return {
            "success": False,
            "zernio_post_id": None,
            "error": "Zernio is not configured on the server (ZERNIO_API_KEY missing).",
            "crm_status": "failed",
        }

    tenant_id = str(post.get("user_id") or "")
    profile_id = await get_zernio_profile_id(db, tenant_id)
    if not profile_id:
        return {
            "success": False,
            "zernio_post_id": None,
            "error": "No Zernio profile found. Connect a social account under Integrations.",
            "crm_status": "failed",
        }

    account_map = await _get_zernio_account_ids(profile_id)
    media_items, media_patches = await resolve_post_media(post)
    if media_patches:
        await db.scheduled_posts.update_one(
            {"_id": post.get("_id")},
            {"$set": {**media_patches, "updated_at": datetime.utcnow()}},
        )
        post = {**post, **media_patches}

    body, build_error = _build_zernio_body(post, profile_id, account_map, media_items)
    if build_error:
        return {
            "success": False,
            "zernio_post_id": None,
            "error": build_error,
            "crm_status": "failed",
        }

    request_id = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{ZERNIO_BASE}/posts",
                headers={
                    "Authorization": f"Bearer {ZERNIO_API_KEY}",
                    "Content-Type": "application/json",
                    "x-request-id": request_id,
                },
                json=body,
            )
        if not resp.is_success:
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
            logger.error("[social_publish] Failed post %s: %s", post.get("_id"), error_reason)
            return {
                "success": False,
                "zernio_post_id": None,
                "error": error_reason,
                "crm_status": "failed",
            }

        data = resp.json()
        post_obj = data.get("post") or data.get("existingPost") or data.get("data") or data
        zernio_post_id = None
        zernio_status = None
        if isinstance(post_obj, dict):
            zernio_post_id = post_obj.get("_id") or post_obj.get("id") or post_obj.get("postId")
            zernio_status = (post_obj.get("status") or "").lower()

        crm_status = "published" if body.get("publishNow") else "scheduled"
        if zernio_status == "published":
            crm_status = "published"

        logger.info(
            "[social_publish] Post %s → Zernio id=%s status=%s publishNow=%s",
            post.get("_id"),
            zernio_post_id,
            zernio_status or crm_status,
            body.get("publishNow"),
        )
        return {
            "success": True,
            "zernio_post_id": str(zernio_post_id) if zernio_post_id else None,
            "error": None,
            "crm_status": crm_status,
        }
    except Exception as exc:
        error_reason = str(exc)
        logger.error("[social_publish] Failed post %s: %s", post.get("_id"), error_reason)
        return {
            "success": False,
            "zernio_post_id": None,
            "error": error_reason,
            "crm_status": "failed",
        }


def should_push_post(post: Dict[str, Any], *, force: bool = False) -> bool:
    status = (post.get("status") or "draft").strip().lower()
    if status not in ("scheduled", "published"):
        return False
    external_id = post.get("external_post_id") or post.get("zernio_post_id")
    if external_id and not force:
        return False
    return True


def should_push_to_zernio(post: Dict[str, Any], *, force: bool = False) -> bool:
    return should_push_post(post, force=force)


async def push_post(db, post: Dict[str, Any]) -> Dict[str, Any]:
    """Publish via Composio for all supported social channels."""
    from social_composio_publish import post_uses_composio, push_post_to_composio

    if post_uses_composio(post):
        return await push_post_to_composio(db, post)
    return {
        "success": False,
        "external_post_id": None,
        "zernio_post_id": None,
        "error": "No supported channels selected.",
        "crm_status": "failed",
        "publish_provider": None,
    }


async def apply_publish_result(db, post_id: str, result: Dict[str, Any]) -> None:
    update: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    if result.get("success"):
        update["status"] = result.get("crm_status") or "published"
        ext_id = result.get("external_post_id") or result.get("zernio_post_id")
        if ext_id:
            update["external_post_id"] = ext_id
            update["zernio_post_id"] = ext_id
            update["engagement_synced_at"] = None
        if result.get("publish_provider"):
            update["publish_provider"] = result["publish_provider"]
        update["publish_error"] = None
    else:
        update["status"] = "failed"
        if result.get("error"):
            update["publish_error"] = result["error"]
        ext_id = result.get("external_post_id") or result.get("zernio_post_id")
        if ext_id:
            update["external_post_id"] = ext_id
            update["zernio_post_id"] = ext_id
    await db.scheduled_posts.update_one({"_id": post_id}, {"$set": update})

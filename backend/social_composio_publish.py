"""
Publish CRM scheduled posts to Facebook, Instagram, and YouTube via Composio.

Uses the same OAuth connection flow as Gmail/Google Calendar (Composio managed auth).
Facebook requires a selected Page ID; Instagram requires a linked Business account.
YouTube requires a video file upload.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from composio_service import (
    ACTION_FB_CREATE_PHOTO,
    ACTION_FB_CREATE_POST,
    ACTION_FB_CREATE_VIDEO,
    ACTION_FB_LIST_PAGES,
    ACTION_IG_CREATE_MEDIA,
    ACTION_IG_PUBLISH_MEDIA,
    ACTION_YT_MULTIPART_UPLOAD,
    TOOLKIT_FACEBOOK,
    TOOLKIT_INSTAGRAM,
    TOOLKIT_YOUTUBE,
    execute_action,
    get_connection_status,
    is_configured,
    upload_file_for_tool,
)
from social_publish_service import resolve_post_media

logger = logging.getLogger(__name__)

COMPOSIO_CHANNELS = frozenset({"facebook", "instagram", "youtube"})


def _extract_action_data(result: Dict[str, Any]) -> Any:
    if result.get("error"):
        return None
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("data", "response", "response_data", "responseData", "result", "body"):
            inner = data.get(key)
            if inner is not None:
                return inner
    return data


def _extract_pages_list(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    if isinstance(raw, dict):
        for key in ("data", "pages", "items"):
            val = raw.get(key)
            if isinstance(val, list):
                return [p for p in val if isinstance(p, dict)]
    return []


def _page_id(page: Dict[str, Any]) -> Optional[str]:
    pid = page.get("id") or page.get("page_id") or page.get("pageId")
    return str(pid) if pid else None


def _page_name(page: Dict[str, Any]) -> str:
    return str(page.get("name") or page.get("username") or page.get("id") or "Facebook Page")


def _ig_from_page(page: Dict[str, Any]) -> Optional[str]:
    ig = page.get("instagram_business_account")
    if isinstance(ig, dict):
        ig_id = ig.get("id")
        return str(ig_id) if ig_id else None
    if isinstance(ig, str) and ig.strip():
        return ig.strip()
    return None


async def _resolve_user_doc(db, tenant_id: str) -> Optional[Dict[str, Any]]:
    user = await db.users.find_one(
        {"_id": tenant_id},
        {"composio_social": 1, "business_id": 1},
    )
    if user:
        return user
    return await db.users.find_one(
        {"business_id": tenant_id},
        {"composio_social": 1, "business_id": 1},
    )


async def get_social_settings(db, tenant_id: str) -> Dict[str, Any]:
    user = await _resolve_user_doc(db, tenant_id)
    settings = (user or {}).get("composio_social") or {}
    if not isinstance(settings, dict):
        settings = {}
    return dict(settings)


async def save_facebook_page(
    db,
    user_oid: Any,
    *,
    page_id: str,
    page_name: str = "",
    instagram_user_id: Optional[str] = None,
) -> None:
    update: Dict[str, Any] = {
        "composio_social.facebook_page_id": page_id,
        "composio_social.facebook_page_name": page_name or page_id,
    }
    if instagram_user_id:
        update["composio_social.instagram_user_id"] = instagram_user_id
    await db.users.update_one({"_id": user_oid}, {"$set": update})


async def list_facebook_pages(user_id: str) -> Dict[str, Any]:
    if not is_configured():
        return {"error": "COMPOSIO_API_KEY not configured on the server."}
    status = await get_connection_status(user_id, TOOLKIT_FACEBOOK)
    if not status.get("connected"):
        return {"error": "Facebook is not connected. Connect it in Integrations first."}

    result = await execute_action(
        user_id,
        ACTION_FB_LIST_PAGES,
        {
            "limit": 100,
            "fields": "id,name,username,category,instagram_business_account",
        },
    )
    if result.get("error"):
        return {"error": result["error"]}

    pages = _extract_pages_list(_extract_action_data(result))
    normalized: List[Dict[str, Any]] = []
    for page in pages:
        pid = _page_id(page)
        if not pid:
            continue
        normalized.append({
            "id": pid,
            "name": _page_name(page),
            "username": page.get("username") or "",
            "category": page.get("category") or "",
            "instagram_user_id": _ig_from_page(page),
        })
    return {"pages": normalized}


async def resolve_instagram_user_id(
    db,
    user_id: str,
    settings: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    settings = settings or await get_social_settings(db, user_id)
    ig_id = (settings.get("instagram_user_id") or "").strip()
    if ig_id:
        return ig_id

    fb_page_id = (settings.get("facebook_page_id") or "").strip()
    pages_res = await list_facebook_pages(user_id)
    if pages_res.get("error"):
        return None
    for page in pages_res.get("pages") or []:
        if fb_page_id and page.get("id") != fb_page_id:
            continue
        ig = (page.get("instagram_user_id") or "").strip()
        if ig:
            return ig
    return None


def _build_message(post: Dict[str, Any]) -> str:
    title = (post.get("title") or "").strip()
    content = (post.get("body") or "").strip()
    if title and title not in content and not content.startswith(title):
        content = f"{title}\n\n{content}".strip() if content else title
    link_url = (post.get("link_url") or "").strip()
    if link_url and link_url not in content:
        content = f"{content}\n\n{link_url}".strip() if content else link_url
    return content


def _first_media(post: Dict[str, Any], media_items: List[Dict[str, str]]) -> Tuple[Optional[str], str]:
    if media_items:
        item = media_items[0]
        return item.get("url"), item.get("type") or "image"
    image_url = (post.get("image_url") or "").strip()
    if image_url.startswith("http"):
        return image_url, "image"
    for asset in post.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        url = (asset.get("s3_url") or "").strip()
        if url.startswith("http"):
            mime = (asset.get("mime_type") or "image/jpeg").lower()
            media_type = "video" if mime.startswith("video/") else "image"
            return url, media_type
    return None, "image"


def _unix_scheduled(post: Dict[str, Any]) -> Optional[int]:
    sched_at = post.get("scheduled_at")
    if not sched_at:
        return None
    if hasattr(sched_at, "timestamp"):
        dt = sched_at
        if getattr(dt, "tzinfo", None) is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return int(dt.timestamp())
    return None


async def _publish_facebook(
    user_id: str,
    post: Dict[str, Any],
    *,
    page_id: str,
    media_items: List[Dict[str, str]],
) -> Dict[str, Any]:
    message = _build_message(post)
    link_url = (post.get("link_url") or "").strip()
    media_url, media_type = _first_media(post, media_items)

    status = (post.get("status") or "draft").strip().lower()
    sched_unix = _unix_scheduled(post)
    now_unix = int(time.time())
    publish_immediately = status == "published"
    if status == "scheduled" and sched_unix and sched_unix <= now_unix:
        publish_immediately = True

    scheduled_future = (
        status == "scheduled"
        and sched_unix
        and sched_unix > now_unix + 600
    )

    params: Dict[str, Any] = {"page_id": page_id}
    action = ACTION_FB_CREATE_POST

    if media_url:
        if media_type == "video":
            action = ACTION_FB_CREATE_VIDEO
            params["file_url"] = media_url
            if message:
                params["description"] = message
        else:
            action = ACTION_FB_CREATE_PHOTO
            params["url"] = media_url
            if message:
                params["message"] = message
    else:
        if not message and not link_url:
            return {"success": False, "error": "Facebook post requires text or a link."}
        params["message"] = message or link_url
        if link_url:
            params["link"] = link_url

    if scheduled_future:
        params["published"] = False
        params["scheduled_publish_time"] = sched_unix
    else:
        params["published"] = True

    result = await execute_action(user_id, action, params)
    if result.get("error"):
        return {"success": False, "error": result["error"]}

    data = _extract_action_data(result)
    post_id = None
    if isinstance(data, dict):
        post_id = data.get("id") or data.get("post_id") or data.get("postId")
    elif data is not None:
        post_id = str(data)

    crm_status = "scheduled" if scheduled_future else "published"
    return {
        "success": True,
        "post_id": str(post_id) if post_id else None,
        "crm_status": crm_status,
    }


async def _publish_instagram(
    user_id: str,
    post: Dict[str, Any],
    *,
    ig_user_id: str,
    media_items: List[Dict[str, str]],
) -> Dict[str, Any]:
    status = (post.get("status") or "draft").strip().lower()
    sched_unix = _unix_scheduled(post)
    now_unix = int(time.time())
    if status == "scheduled" and sched_unix and sched_unix > now_unix + 60:
        return {
            "success": False,
            "error": (
                "Instagram does not support native scheduling via Composio. "
                "Use status 'Scheduled' with a near-future time, or publish now."
            ),
        }

    caption = _build_message(post)
    media_url, media_type = _first_media(post, media_items)
    if not media_url:
        return {
            "success": False,
            "error": "Instagram posts require an image or video. Add media before publishing.",
        }

    create_params: Dict[str, Any] = {
        "ig_user_id": ig_user_id,
        "caption": caption or None,
    }
    if media_type == "video":
        create_params["video_url"] = media_url
        create_params["media_type"] = "REELS"
    else:
        create_params["image_url"] = media_url

    create_result = await execute_action(user_id, ACTION_IG_CREATE_MEDIA, create_params)
    if create_result.get("error"):
        return {"success": False, "error": create_result["error"]}

    create_data = _extract_action_data(create_result)
    creation_id = None
    if isinstance(create_data, dict):
        creation_id = create_data.get("id") or create_data.get("creation_id")
    elif create_data is not None:
        creation_id = str(create_data)

    if not creation_id:
        return {"success": False, "error": "Instagram media container was not created."}

    publish_params: Dict[str, Any] = {
        "ig_user_id": ig_user_id,
        "creation_id": str(creation_id),
        "max_wait_seconds": 120 if media_type == "video" else 60,
    }
    publish_result = await execute_action(user_id, ACTION_IG_PUBLISH_MEDIA, publish_params)
    if publish_result.get("error"):
        return {"success": False, "error": publish_result["error"]}

    publish_data = _extract_action_data(publish_result)
    media_id = None
    if isinstance(publish_data, dict):
        media_id = publish_data.get("id") or publish_data.get("media_id")
    elif publish_data is not None:
        media_id = str(publish_data)

    return {
        "success": True,
        "post_id": str(media_id) if media_id else str(creation_id),
        "crm_status": "published",
    }


async def _download_public_file(url: str, *, max_bytes: int = 500 * 1024 * 1024) -> Tuple[Optional[bytes], str, str]:
    """Fetch a public media URL. Returns (bytes, filename, mime)."""
    u = (url or "").strip()
    if not u.startswith("http"):
        return None, "media.bin", "application/octet-stream"
    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            resp = await client.get(u)
        if resp.status_code != 200:
            return None, "media.bin", "application/octet-stream"
        data = resp.content
        if len(data) > max_bytes:
            return None, "media.bin", "application/octet-stream"
        ctype = (resp.headers.get("content-type") or "video/mp4").split(";")[0].strip()
        fname = u.rsplit("/", 1)[-1].split("?", 1)[0] or "video.mp4"
        if "." not in fname:
            fname = "video.mp4" if ctype.startswith("video/") else "media.bin"
        return data, fname, ctype or "video/mp4"
    except Exception as exc:
        logger.warning("[social_composio] download failed for %s: %s", u[:80], exc)
        return None, "video.mp4", "video/mp4"


async def _publish_youtube(
    user_id: str,
    post: Dict[str, Any],
    *,
    media_items: List[Dict[str, str]],
) -> Dict[str, Any]:
    title = (post.get("title") or "").strip()
    description = _build_message(post)
    if not title:
        title = (description.split("\n", 1)[0] if description else "CRM Video Post")[:100]
    if not description:
        description = title

    media_url, media_type = _first_media(post, media_items)
    if not media_url or media_type != "video":
        return {
            "success": False,
            "error": "YouTube posts require a video. Attach a video file before publishing.",
        }

    file_bytes, filename, mime = await _download_public_file(media_url)
    if not file_bytes:
        return {
            "success": False,
            "error": "Could not download the video file for YouTube upload. Ensure media is publicly accessible.",
        }

    uploaded = await upload_file_for_tool(
        TOOLKIT_YOUTUBE,
        ACTION_YT_MULTIPART_UPLOAD,
        filename,
        file_bytes,
        mime if mime.startswith("video/") else "video/mp4",
    )
    if uploaded.get("error"):
        return {"success": False, "error": uploaded["error"]}

    video_file = uploaded.get("file")
    if not video_file:
        return {"success": False, "error": "Composio file upload did not return a file reference."}

    privacy = "public"
    params: Dict[str, Any] = {
        "title": title[:100],
        "description": description[:5000],
        "categoryId": "22",
        "privacyStatus": privacy,
        "videoFile": video_file,
    }
    tags_raw = (post.get("title") or "").strip()
    if tags_raw:
        params["tags"] = [t.strip() for t in tags_raw.replace(",", " ").split() if t.strip()][:10]

    result = await execute_action(user_id, ACTION_YT_MULTIPART_UPLOAD, params)
    if result.get("error"):
        return {"success": False, "error": result["error"]}

    data = _extract_action_data(result)
    video_id = None
    if isinstance(data, dict):
        video_id = data.get("id") or data.get("video_id") or data.get("videoId")
    elif data is not None:
        video_id = str(data)

    return {
        "success": True,
        "post_id": str(video_id) if video_id else None,
        "crm_status": "published",
    }


async def push_post_to_composio(db, post: Dict[str, Any]) -> Dict[str, Any]:
    """Publish a post to Facebook, Instagram, and/or YouTube via Composio."""
    if not is_configured():
        return {
            "success": False,
            "external_post_id": None,
            "zernio_post_id": None,
            "error": "Composio is not configured on the server (COMPOSIO_API_KEY missing).",
            "crm_status": "failed",
            "publish_provider": "composio",
        }

    tenant_id = str(post.get("user_id") or "")
    channels = [c.strip().lower() for c in (post.get("channels") or []) if c.strip()]
    composio_channels = [c for c in channels if c in COMPOSIO_CHANNELS]
    if not composio_channels:
        return {
            "success": False,
            "external_post_id": None,
            "zernio_post_id": None,
            "error": "No Facebook, Instagram, or YouTube channels selected.",
            "crm_status": "failed",
            "publish_provider": "composio",
        }

    settings = await get_social_settings(db, tenant_id)
    media_items, media_patches = await resolve_post_media(post)
    if media_patches:
        await db.scheduled_posts.update_one(
            {"_id": post.get("_id")},
            {"$set": {**media_patches, "updated_at": datetime.utcnow()}},
        )
        post = {**post, **media_patches}

    external_ids: List[str] = []
    errors: List[str] = []
    crm_status = "published"

    if "facebook" in composio_channels:
        fb_status = await get_connection_status(tenant_id, TOOLKIT_FACEBOOK)
        if not fb_status.get("connected"):
            errors.append("Facebook is not connected (Integrations → Social Channels).")
        else:
            page_id = (settings.get("facebook_page_id") or "").strip()
            if not page_id:
                pages_res = await list_facebook_pages(tenant_id)
                pages = pages_res.get("pages") or []
                if len(pages) == 1:
                    page_id = pages[0]["id"]
                    user_doc = await _resolve_user_doc(db, tenant_id)
                    if user_doc:
                        await save_facebook_page(
                            db,
                            user_doc["_id"],
                            page_id=page_id,
                            page_name=pages[0].get("name") or "",
                            instagram_user_id=pages[0].get("instagram_user_id"),
                        )
                elif not pages:
                    errors.append(
                        pages_res.get("error")
                        or "No Facebook Pages found. Connect a Page in Integrations."
                    )
                else:
                    errors.append(
                        "Select a Facebook Page in Integrations before publishing."
                    )
            if page_id:
                fb_res = await _publish_facebook(
                    tenant_id, post, page_id=page_id, media_items=media_items
                )
                if fb_res.get("success"):
                    if fb_res.get("post_id"):
                        external_ids.append(f"fb:{fb_res['post_id']}")
                    if fb_res.get("crm_status") == "scheduled":
                        crm_status = "scheduled"
                else:
                    errors.append(f"Facebook: {fb_res.get('error') or 'publish failed'}")

    if "instagram" in composio_channels:
        ig_status = await get_connection_status(tenant_id, TOOLKIT_INSTAGRAM)
        if not ig_status.get("connected"):
            errors.append("Instagram is not connected (Integrations → Social Channels).")
        else:
            ig_user_id = await resolve_instagram_user_id(db, tenant_id, settings)
            if not ig_user_id:
                errors.append(
                    "No Instagram Business account linked. Connect Instagram and link it to your Facebook Page."
                )
            else:
                ig_res = await _publish_instagram(
                    tenant_id, post, ig_user_id=ig_user_id, media_items=media_items
                )
                if ig_res.get("success"):
                    if ig_res.get("post_id"):
                        external_ids.append(f"ig:{ig_res['post_id']}")
                else:
                    errors.append(f"Instagram: {ig_res.get('error') or 'publish failed'}")

    if "youtube" in composio_channels:
        yt_status = await get_connection_status(tenant_id, TOOLKIT_YOUTUBE)
        if not yt_status.get("connected"):
            errors.append("YouTube is not connected (Integrations → Social Channels).")
        else:
            yt_res = await _publish_youtube(tenant_id, post, media_items=media_items)
            if yt_res.get("success"):
                if yt_res.get("post_id"):
                    external_ids.append(f"yt:{yt_res['post_id']}")
            else:
                errors.append(f"YouTube: {yt_res.get('error') or 'publish failed'}")

    if external_ids and not errors:
        ext_id = "|".join(external_ids)
        return {
            "success": True,
            "external_post_id": ext_id,
            "zernio_post_id": ext_id,
            "error": None,
            "crm_status": crm_status,
            "publish_provider": "composio",
        }

    if external_ids and errors:
        ext_id = "|".join(external_ids)
        return {
            "success": False,
            "external_post_id": ext_id,
            "zernio_post_id": ext_id,
            "error": "; ".join(errors),
            "crm_status": "failed",
            "publish_provider": "composio",
        }

    return {
        "success": False,
        "external_post_id": None,
        "zernio_post_id": None,
        "error": "; ".join(errors) if errors else "Publish failed.",
        "crm_status": "failed",
        "publish_provider": "composio",
    }


def post_uses_composio(post: Dict[str, Any]) -> bool:
    channels = [c.strip().lower() for c in (post.get("channels") or []) if c.strip()]
    return any(c in COMPOSIO_CHANNELS for c in channels)


def post_uses_zernio(post: Dict[str, Any]) -> bool:
    zernio_map = {"linkedin", "x", "twitter", "tiktok"}
    channels = [c.strip().lower() for c in (post.get("channels") or []) if c.strip()]
    return any(c in zernio_map for c in channels)

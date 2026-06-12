"""
Publish CRM scheduled posts to Facebook, Instagram, YouTube, LinkedIn, X, and TikTok via Composio.

Uses the same OAuth connection flow as Gmail/Google Calendar (Composio managed auth).
Facebook requires a selected Page ID; Instagram requires a linked Business account.
YouTube requires a video file upload.
LinkedIn posts as the connected member (or a saved organization URN).
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
    ACTION_LI_CREATE_POST,
    ACTION_LI_GET_COMPANY_INFO,
    ACTION_LI_GET_MY_INFO,
    ACTION_TIKTOK_PUBLISH_VIDEO,
    ACTION_TWITTER_CREATE_POST,
    ACTION_YT_MULTIPART_UPLOAD,
    TOOLKIT_FACEBOOK,
    TOOLKIT_INSTAGRAM,
    TOOLKIT_LINKEDIN,
    TOOLKIT_TIKTOK,
    TOOLKIT_TWITTER,
    TOOLKIT_YOUTUBE,
    execute_action,
    get_connection_status,
    is_configured,
    upload_file_for_tool,
)
from social_publish_service import resolve_post_media

logger = logging.getLogger(__name__)

COMPOSIO_CHANNELS = frozenset({
    "facebook", "instagram", "youtube", "linkedin", "twitter", "x", "tiktok",
})


def _extract_action_data(result: Dict[str, Any]) -> Any:
    if result.get("error"):
        return None
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("data", "response", "response_data", "responseData", "result", "body", "response_dict"):
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


async def save_linkedin_author(
    db,
    user_oid: Any,
    *,
    author_urn: str,
    author_name: str = "",
    provider: str = "composio",
    org_id: str = "",
) -> None:
    await db.users.update_one(
        {"_id": user_oid},
        {
            "$set": {
                "composio_social.linkedin_author_urn": author_urn,
                "composio_social.linkedin_author_name": author_name or author_urn,
                "composio_social.linkedin_author_provider": provider or "composio",
                "composio_social.linkedin_author_org_id": org_id or "",
            }
        },
    )


async def save_linkedin_authors_cache(
    db,
    user_oid: Any,
    authors: List[Dict[str, Any]],
) -> None:
    if not authors:
        return
    await db.users.update_one(
        {"_id": user_oid},
        {"$set": {"composio_social.linkedin_authors_cache": authors}},
    )


def linkedin_authors_from_user(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Read cached LinkedIn posting identities from the user document (no Composio call)."""
    social = user.get("composio_social") if isinstance(user, dict) else None
    if not isinstance(social, dict):
        return []
    cached = social.get("linkedin_authors_cache")
    if isinstance(cached, list) and cached:
        return [a for a in cached if isinstance(a, dict) and a.get("urn")]
    urn = social.get("linkedin_author_urn")
    if urn:
        return [{
            "urn": str(urn),
            "name": str(social.get("linkedin_author_name") or urn),
            "type": "person" if ":person:" in str(urn) else "organization",
        }]
    return []


def _linkedin_org_urn(raw: Any) -> Optional[str]:
    if isinstance(raw, str) and raw.strip().startswith("urn:li:organization:"):
        return raw.strip()
    if isinstance(raw, (int, str)) and str(raw).strip().isdigit():
        return f"urn:li:organization:{str(raw).strip()}"
    if isinstance(raw, dict):
        oid = raw.get("id") or raw.get("organization") or raw.get("organizationalTarget")
        if isinstance(oid, str) and oid.startswith("urn:li:organization:"):
            return oid
        if isinstance(oid, dict):
            inner = oid.get("id") or oid.get("organization")
            if inner:
                return _linkedin_org_urn(inner)
        if oid is not None:
            return _linkedin_org_urn(oid)
    return None


async def list_linkedin_authors(
    user_id: str,
    *,
    db=None,
    user_oid: Any = None,
) -> Dict[str, Any]:
    """Personal profile + managed company pages for LinkedIn posting."""
    if not is_configured():
        return {"error": "COMPOSIO_API_KEY not configured on the server.", "authors": []}

    authors: List[Dict[str, Any]] = []
    me_err: Optional[str] = None

    # Personal profile via Composio (member posting, urn:li:person:*).
    li_status = await get_connection_status(user_id, TOOLKIT_LINKEDIN)
    if li_status.get("connected"):
        conn_id = li_status.get("connection_id")
        me = await execute_action(
            user_id,
            ACTION_LI_GET_MY_INFO,
            {},
            connected_account_id=conn_id,
            timeout=20.0,
        )
        me_data = _extract_action_data(me)
        if me.get("error"):
            me_err = str(me["error"])
        else:
            person_urn = _deep_linkedin_person_urn(me_data)
            if person_urn:
                authors.append({
                    "urn": person_urn,
                    "name": _linkedin_profile_name(me_data if isinstance(me_data, dict) else {}),
                    "type": "person",
                    "provider": "composio",
                })

    # Company/organization pages via Unipile. Composio's LinkedIn connection lacks
    # org scopes (and its company action 426s on a retired API version), so Unipile —
    # which works through the member's LinkedIn session — is the source for pages.
    if db is not None and user_oid is not None:
        try:
            from unipile_service import (
                is_configured as unipile_configured,
                list_linkedin_company_pages,
            )
            if unipile_configured():
                business_id = str(user_id)
                udoc = await db.users.find_one({"_id": user_oid}, {"business_id": 1})
                if udoc and udoc.get("business_id"):
                    business_id = str(udoc["business_id"])
                for page in await list_linkedin_company_pages(db, user_oid, business_id):
                    if not any(a.get("urn") == page.get("urn") for a in authors):
                        authors.append(page)
        except Exception as exc:
            logger.debug("[linkedin] unipile company pages skipped: %s", exc)

    if not authors:
        return {
            "error": me_err or "Could not load LinkedIn posting identities. Try disconnecting and reconnecting LinkedIn.",
            "authors": [],
        }

    if db is not None and user_oid is not None:
        await save_linkedin_authors_cache(db, user_oid, authors)
    return {"authors": authors}


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
    if not pages_res.get("error"):
        for page in pages_res.get("pages") or []:
            if fb_page_id and page.get("id") != fb_page_id:
                continue
            ig = (page.get("instagram_user_id") or "").strip()
            if ig:
                return ig

    # Direct fallback using INSTAGRAM_GET_USER_INFO if Facebook page listing fails
    try:
        ig_status = await get_connection_status(user_id, TOOLKIT_INSTAGRAM)
        if ig_status.get("connected"):
            user_info = await execute_action(user_id, "INSTAGRAM_GET_USER_INFO", {})
            if user_info.get("success") and user_info.get("data"):
                ig_id = (user_info["data"].get("id") or "").strip()
                if ig_id:
                    user_doc = await _resolve_user_doc(db, user_id)
                    if user_doc:
                        await db.users.update_one(
                            {"_id": user_doc["_id"]},
                            {"$set": {"composio_social.instagram_user_id": ig_id}}
                        )
                    return ig_id
    except Exception as e:
        logger.warning(f"[social-publish] Failed to resolve Instagram ID directly: {e}")
    return None


async def get_instagram_profile(
    db,
    user_id: str,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fetch the connected Instagram professional account's public profile.

    Returns {username, name, profile_picture_url, followers_count, account_id}.
    Username/name are cached to the user doc (they don't expire); the profile
    picture URL is signed by Instagram and short-lived, so it is fetched live.
    """
    profile: Dict[str, Any] = {
        "username": None,
        "name": None,
        "profile_picture_url": None,
        "followers_count": None,
        "account_id": None,
    }
    settings = settings or await get_social_settings(db, user_id)
    cached = settings.get("instagram_profile") if isinstance(settings, dict) else None
    if isinstance(cached, dict):
        profile["username"] = cached.get("username") or None
        profile["name"] = cached.get("name") or None

    try:
        ig_status = await get_connection_status(user_id, TOOLKIT_INSTAGRAM)
        if not ig_status.get("connected"):
            return profile
        res = await execute_action(user_id, "INSTAGRAM_GET_USER_INFO", {})
        data = _extract_action_data(res)
        if not isinstance(data, dict):
            return profile
        username = (data.get("username") or "").strip() or profile["username"]
        name = (data.get("name") or "").strip() or profile["name"]
        pic = (
            data.get("profile_picture_url")
            or data.get("profile_pic")
            or data.get("profile_picture")
            or ""
        ).strip() or None
        followers = data.get("followers_count")
        account_id = (data.get("id") or "").strip() or None
        profile.update(
            {
                "username": username or None,
                "name": name or None,
                "profile_picture_url": pic,
                "followers_count": followers,
                "account_id": account_id,
            }
        )
        # Persist the non-expiring fields for instant display on next load.
        if username or name:
            user_doc = await _resolve_user_doc(db, user_id)
            if user_doc:
                await db.users.update_one(
                    {"_id": user_doc["_id"]},
                    {
                        "$set": {
                            "composio_social.instagram_profile": {
                                "username": username or None,
                                "name": name or None,
                            }
                        }
                    },
                )
    except Exception as e:
        logger.warning("[social-publish] Instagram profile fetch failed: %s", e)
    return profile


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


def _linkedin_person_urn(raw: Any) -> Optional[str]:
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("urn:li:person:"):
            return s
        return None
    if not isinstance(raw, dict):
        return None
    for key in ("urn", "id", "sub", "person_id", "personId", "member_id", "memberId"):
        val = raw.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if not s:
            continue
        if s.startswith("urn:li:"):
            return s
        return f"urn:li:person:{s}"
    return None


def _deep_linkedin_person_urn(raw: Any, depth: int = 0) -> Optional[str]:
    if depth > 10:
        return None
    direct = _linkedin_person_urn(raw)
    if direct:
        return direct
    if isinstance(raw, dict):
        for val in raw.values():
            found = _deep_linkedin_person_urn(val, depth + 1)
            if found:
                return found
    elif isinstance(raw, list):
        for item in raw:
            found = _deep_linkedin_person_urn(item, depth + 1)
            if found:
                return found
    return None


def _linkedin_profile_name(raw: Any) -> str:
    if not isinstance(raw, dict):
        return "My profile"
    for key in ("data", "response", "profile", "member"):
        inner = raw.get(key)
        if isinstance(inner, dict):
            raw = inner
            break
    first = raw.get("localizedFirstName") or raw.get("firstName") or ""
    last = raw.get("localizedLastName") or raw.get("lastName") or ""
    name = f"{first} {last}".strip()
    return name or str(raw.get("name") or raw.get("vanityName") or "My profile")


async def _resolve_linkedin_author(
    db,
    user_id: str,
    settings: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (author_urn, error). Uses saved org URN or falls back to member profile."""
    settings = settings or await get_social_settings(db, user_id)
    saved = (settings.get("linkedin_author_urn") or "").strip()
    if saved.startswith("urn:li:"):
        return saved, None

    result = await execute_action(user_id, ACTION_LI_GET_MY_INFO, {})
    if result.get("error"):
        return None, result["error"]

    data = _extract_action_data(result)
    if isinstance(data, dict):
        for key in ("data", "response", "profile", "member"):
            inner = data.get(key)
            if isinstance(inner, dict):
                urn = _linkedin_person_urn(inner)
                if urn:
                    user_doc = await _resolve_user_doc(db, user_id)
                    if user_doc:
                        await db.users.update_one(
                            {"_id": user_doc["_id"]},
                            {"$set": {"composio_social.linkedin_author_urn": urn}},
                        )
                    return urn, None
        urn = _linkedin_person_urn(data)
        if urn:
            user_doc = await _resolve_user_doc(db, user_id)
            if user_doc:
                await db.users.update_one(
                    {"_id": user_doc["_id"]},
                    {"$set": {"composio_social.linkedin_author_urn": urn}},
                )
            return urn, None

    return None, "Could not resolve LinkedIn author URN. Reconnect LinkedIn in Integrations."


async def _publish_linkedin(
    user_id: str,
    post: Dict[str, Any],
    *,
    author_urn: str,
    media_items: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    commentary = _build_message(post)
    media_items = media_items or []
    media_url, media_type = _first_media(post, media_items)

    if not commentary and not media_url:
        return {"success": False, "error": "LinkedIn post requires text or an image."}

    # LinkedIn commentary max ~3000 chars
    if commentary and len(commentary) > 3000:
        commentary = commentary[:2997] + "..."

    params: Dict[str, Any] = {
        "author": author_urn,
        "commentary": commentary or " ",
        "visibility": "PUBLIC",
        "lifecycleState": "PUBLISHED",
    }

    if media_url and media_type == "image":
        params["images"] = [media_url]

    result = await execute_action(user_id, ACTION_LI_CREATE_POST, params)
    if result.get("error"):
        return {"success": False, "error": result["error"]}

    data = _extract_action_data(result)
    post_id = None
    if isinstance(data, dict):
        post_id = (
            data.get("id")
            or data.get("post_id")
            or data.get("postId")
            or data.get("x_restli_id")
            or data.get("urn")
        )
    elif data is not None:
        post_id = str(data)

    return {
        "success": True,
        "post_id": str(post_id) if post_id else None,
        "crm_status": "published",
    }


async def _publish_twitter(
    user_id: str,
    post: Dict[str, Any],
) -> Dict[str, Any]:
    text = _build_message(post)
    if not text:
        return {"success": False, "error": "X post requires text content."}
    if len(text) > 280:
        text = text[:277] + "..."

    result = await execute_action(user_id, ACTION_TWITTER_CREATE_POST, {"text": text})
    if result.get("error"):
        return {"success": False, "error": result["error"]}

    data = _extract_action_data(result)
    post_id = None
    if isinstance(data, dict):
        post_id = data.get("id") or data.get("tweet_id") or data.get("data", {}).get("id")
    elif data is not None:
        post_id = str(data)

    return {
        "success": True,
        "post_id": str(post_id) if post_id else None,
        "crm_status": "published",
    }


async def _publish_tiktok(
    user_id: str,
    post: Dict[str, Any],
    *,
    media_items: List[Dict[str, str]],
) -> Dict[str, Any]:
    title = (post.get("title") or "").strip()
    description = _build_message(post)
    if not title:
        title = (description.split("\n", 1)[0] if description else "CRM Video")[:150]
    if not description:
        description = title

    media_url, media_type = _first_media(post, media_items)
    if not media_url or media_type != "video":
        return {
            "success": False,
            "error": "TikTok posts require a video. Attach a video file before publishing.",
        }

    params: Dict[str, Any] = {
        "video_url": media_url,
        "title": title[:150],
        "description": description[:2200],
        "privacy_level": "PUBLIC_TO_EVERYONE",
    }

    result = await execute_action(user_id, ACTION_TIKTOK_PUBLISH_VIDEO, params)
    if result.get("error"):
        return {"success": False, "error": result["error"]}

    data = _extract_action_data(result)
    post_id = None
    if isinstance(data, dict):
        post_id = data.get("id") or data.get("publish_id") or data.get("video_id")
    elif data is not None:
        post_id = str(data)

    return {
        "success": True,
        "post_id": str(post_id) if post_id else None,
        "crm_status": "published",
    }


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
    """Publish a post to supported social channels via Composio."""
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
            "error": "No Composio-supported channels selected.",
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

    if "linkedin" in composio_channels:
        li_res: Optional[Dict[str, Any]] = None
        user_doc = await _resolve_user_doc(db, tenant_id)
        author_provider = str(settings.get("linkedin_author_provider") or "").strip().lower()
        author_org_id = str(settings.get("linkedin_author_org_id") or "").strip()

        async def _unipile_li_post(as_org: Optional[str]) -> Optional[Dict[str, Any]]:
            """Publish via Unipile (member, or a company page when as_org is set).

            Returns None when Unipile isn't usable (not configured / no account),
            so the caller can fall back or surface a connect message.
            """
            if not user_doc:
                return None
            from unipile_service import (
                is_configured as unipile_configured,
                publish_linkedin_post,
                resolve_linkedin_account_id,
            )
            if not unipile_configured():
                return None
            business_id = str(user_doc.get("business_id") or user_doc["_id"])
            account_id = await resolve_linkedin_account_id(db, user_doc["_id"], business_id)
            if not account_id:
                return None
            commentary = _build_message(post)
            media_url, media_type = _first_media(post, media_items)
            if not commentary and not media_url:
                return {"success": False, "error": "LinkedIn post requires text or an image."}
            if commentary and len(commentary) > 3000:
                commentary = commentary[:2997] + "..."
            res = await publish_linkedin_post(
                account_id,
                text=commentary or " ",
                image_url=media_url if media_type == "image" else None,
                as_organization=as_org,
            )
            if res.get("error"):
                return {"success": False, "error": res["error"]}
            return {"success": True, "post_id": res.get("post_id"), "crm_status": "published"}

        if author_provider == "unipile" and author_org_id:
            # Company page → Unipile, posting on the organization's behalf.
            li_res = await _unipile_li_post(author_org_id)
            if li_res is None:
                errors.append(
                    "LinkedIn company-page posting needs LinkedIn Premium (Unipile) connected in Integrations."
                )
        else:
            # Personal profile → Composio (member). Fall back to Unipile member post
            # if Composio LinkedIn isn't connected.
            li_status = await get_connection_status(tenant_id, TOOLKIT_LINKEDIN)
            if li_status.get("connected"):
                author_urn, author_err = await _resolve_linkedin_author(db, tenant_id, settings)
                if author_err or not author_urn:
                    errors.append(f"LinkedIn: {author_err or 'author URN missing'}")
                else:
                    li_res = await _publish_linkedin(
                        tenant_id, post, author_urn=author_urn, media_items=media_items,
                    )
            else:
                li_res = await _unipile_li_post(None)
                if li_res is None:
                    errors.append(
                        "LinkedIn is not connected. Connect LinkedIn (posting) or LinkedIn Premium in Integrations."
                    )

        if li_res:
            if li_res.get("success"):
                if li_res.get("post_id"):
                    external_ids.append(f"li:{li_res['post_id']}")
            else:
                errors.append(f"LinkedIn: {li_res.get('error') or 'publish failed'}")

    twitter_channels = [c for c in composio_channels if c in ("twitter", "x")]
    if twitter_channels:
        tw_status = await get_connection_status(tenant_id, TOOLKIT_TWITTER)
        if not tw_status.get("connected"):
            errors.append("X is not connected (Integrations → Social Channels).")
        else:
            tw_res = await _publish_twitter(tenant_id, post)
            if tw_res.get("success"):
                if tw_res.get("post_id"):
                    external_ids.append(f"x:{tw_res['post_id']}")
            else:
                errors.append(f"X: {tw_res.get('error') or 'publish failed'}")

    if "tiktok" in composio_channels:
        tt_status = await get_connection_status(tenant_id, TOOLKIT_TIKTOK)
        if not tt_status.get("connected"):
            errors.append("TikTok is not connected (Integrations → Social Channels).")
        else:
            tt_res = await _publish_tiktok(tenant_id, post, media_items=media_items)
            if tt_res.get("success"):
                if tt_res.get("post_id"):
                    external_ids.append(f"tt:{tt_res['post_id']}")
            else:
                errors.append(f"TikTok: {tt_res.get('error') or 'publish failed'}")

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
    return False

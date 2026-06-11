"""Posts, comments, and analytics via Composio (Facebook, Instagram, X, …)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from composio_service import (
    TOOLKIT_FACEBOOK,
    TOOLKIT_INSTAGRAM,
    TOOLKIT_LINKEDIN,
    TOOLKIT_TWITTER,
    TOOLKIT_YOUTUBE,
    execute_action,
    get_connection_status,
    is_configured,
)
from social_composio_publish import (
    _resolve_linkedin_author,
    get_social_settings,
    list_facebook_pages,
    resolve_instagram_user_id,
)

logger = logging.getLogger(__name__)

ACTION_FB_PAGE_POSTS = "FACEBOOK_GET_PAGE_POSTS"
ACTION_FB_COMMENTS = "FACEBOOK_GET_COMMENTS"
ACTION_FB_CREATE_COMMENT = "FACEBOOK_CREATE_COMMENT"
ACTION_FB_POST_INSIGHTS = "FACEBOOK_GET_POST_INSIGHTS"
ACTION_FB_POST_REACTIONS = "FACEBOOK_GET_POST_REACTIONS"

ACTION_IG_USER_MEDIA = "INSTAGRAM_GET_IG_USER_MEDIA"
ACTION_IG_MEDIA_COMMENTS = "INSTAGRAM_GET_IG_MEDIA_COMMENTS"
ACTION_IG_COMMENT_REPLY = "INSTAGRAM_POST_IG_COMMENT_REPLIES"
ACTION_IG_MEDIA_INSIGHTS = "INSTAGRAM_GET_IG_MEDIA_INSIGHTS"
ACTION_IG_MEDIA = "INSTAGRAM_GET_IG_MEDIA"

ACTION_TWITTER_ME = "TWITTER_USER_LOOKUP_ME"
ACTION_TWITTER_SEARCH = "TWITTER_RECENT_SEARCH"
ACTION_TWITTER_POST = "TWITTER_POST_LOOKUP_BY_POST_ID"
ACTION_TWITTER_POST_ANALYTICS = "TWITTER_GET_POST_ANALYTICS"

ACTION_LI_POST = "LINKEDIN_GET_POST_CONTENT"
ACTION_LI_SHARE_STATS = "LINKEDIN_GET_SHARE_STATS"
ACTION_LI_COMMENT = "LINKEDIN_CREATE_COMMENT_ON_POST"
ACTION_LI_LIST_REACTIONS = "LINKEDIN_LIST_REACTIONS"
ACTION_LI_GET_MY_INFO = "LINKEDIN_GET_MY_INFO"


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


def _rows(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ("data", "posts", "items", "comments"):
            val = raw.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []


def _int_metric(*values: Any) -> int:
    for v in values:
        if v is None:
            continue
        try:
            return int(float(v))
        except (TypeError, ValueError):
            continue
    return 0


def _normalize_time(value: Any) -> str:
    t = str(value or "").strip()
    if not t:
        return ""
    if "+" in t:
        t = t.split("+", 1)[0]
    if not t.endswith("Z") and "T" in t:
        t += "Z"
    return t


async def _tenant_id(user: Dict[str, Any]) -> str:
    return str(user.get("business_id") or user["_id"])


async def _connection_id(user_id: str, toolkit: str) -> Optional[str]:
    status = await get_connection_status(user_id, toolkit)
    if status.get("connected"):
        return str(status.get("connection_id") or f"ca_{toolkit}")
    return None


async def _facebook_page_id(db, user_id: str) -> Tuple[Optional[str], Optional[str]]:
    settings = await get_social_settings(db, user_id)
    page_id = (settings.get("facebook_page_id") or "").strip()
    if page_id:
        return page_id, str(settings.get("facebook_page_name") or page_id)
    pages_res = await list_facebook_pages(user_id)
    pages = pages_res.get("pages") or []
    if len(pages) == 1:
        return str(pages[0]["id"]), str(pages[0].get("name") or "")
    return None, None


def _normalize_fb_post(
    post: Dict[str, Any],
    *,
    connection_id: str,
    page_id: str,
) -> Dict[str, Any]:
    pid = str(post.get("id") or "")
    if pid and "_" not in pid and page_id:
        pid = f"{page_id}_{pid}"
    message = post.get("message") or post.get("story") or post.get("description") or ""
    attachments = post.get("attachments") or {}
    att_data = attachments.get("data") if isinstance(attachments, dict) else []
    picture = ""
    if isinstance(att_data, list) and att_data:
        media = (att_data[0].get("media") or {}) if isinstance(att_data[0], dict) else {}
        if isinstance(media, dict):
            image = media.get("image") or {}
            if isinstance(image, dict):
                picture = image.get("src") or ""
    return {
        "id": pid,
        "accountId": connection_id,
        "account_id": connection_id,
        "platform": "facebook",
        "message": message,
        "content": message,
        "picture": picture or post.get("full_picture") or "",
        "imageUrl": picture or post.get("full_picture") or "",
        "permalink": post.get("permalink_url") or "",
        "likes": _int_metric(post.get("likes")),
        "shares": _int_metric((post.get("shares") or {}).get("count") if isinstance(post.get("shares"), dict) else post.get("shares")),
        "commentCount": _int_metric(post.get("comments_count"), (post.get("comments") or {}).get("summary", {}).get("total_count")),
        "comments_count": _int_metric(post.get("comments_count")),
        "createdTime": _normalize_time(post.get("created_time")),
        "created_at": _normalize_time(post.get("created_time")),
    }


def _normalize_ig_media(media: Dict[str, Any], *, connection_id: str) -> Dict[str, Any]:
    mid = str(media.get("id") or "")
    caption = media.get("caption") or ""
    return {
        "id": mid,
        "accountId": connection_id,
        "account_id": connection_id,
        "platform": "instagram",
        "message": caption,
        "content": caption,
        "caption": caption,
        "picture": media.get("thumbnail_url") or media.get("media_url") or "",
        "imageUrl": media.get("media_url") or media.get("thumbnail_url") or "",
        "thumbnailUrl": media.get("thumbnail_url") or "",
        "permalink": media.get("permalink") or "",
        "likes": _int_metric(media.get("like_count")),
        "commentCount": _int_metric(media.get("comments_count")),
        "comments_count": _int_metric(media.get("comments_count")),
        "createdTime": _normalize_time(media.get("timestamp")),
        "created_at": _normalize_time(media.get("timestamp")),
    }


def _linkedin_urn(raw: str) -> str:
    pid = str(raw or "").strip()
    if not pid:
        return ""
    if pid.startswith("urn:li:"):
        return pid
    if pid.startswith("li:"):
        return pid[3:]
    if pid.isdigit():
        return f"urn:li:ugcPost:{pid}"
    return pid


def _extract_linkedin_urn_from_external(ext: str) -> str:
    raw = str(ext or "").strip()
    if not raw:
        return ""
    for part in raw.split("|"):
        part = part.strip()
        if part.lower().startswith("li:"):
            return _linkedin_urn(part[3:])
    if "urn:li:" in raw:
        return _linkedin_urn(raw)
    return _linkedin_urn(raw)


def _normalize_linkedin_post(
    row: Dict[str, Any],
    *,
    connection_id: str,
    fallback_id: str = "",
) -> Dict[str, Any]:
    urn = _linkedin_urn(row.get("id") or row.get("post_id") or row.get("urn") or fallback_id)
    text = (
        row.get("commentary")
        or row.get("text")
        or row.get("message")
        or row.get("content")
        or ""
    )
    if isinstance(text, dict):
        text = text.get("text") or ""
    return {
        "id": urn,
        "accountId": connection_id,
        "account_id": connection_id,
        "platform": "linkedin",
        "message": str(text),
        "content": str(text),
        "caption": str(text),
        "picture": row.get("image_url") or row.get("picture") or "",
        "imageUrl": row.get("image_url") or row.get("picture") or "",
        "permalink": row.get("permalink") or row.get("url") or "",
        "likes": _int_metric(row.get("likes"), row.get("like_count")),
        "commentCount": _int_metric(row.get("commentCount"), row.get("comments_count"), row.get("comment_count")),
        "comments_count": _int_metric(row.get("commentCount"), row.get("comments_count"), row.get("comment_count")),
        "shares": _int_metric(row.get("shares"), row.get("share_count")),
        "createdTime": _normalize_time(row.get("createdTime") or row.get("created_at") or row.get("published_at")),
        "created_at": _normalize_time(row.get("createdTime") or row.get("created_at") or row.get("published_at")),
        "source": "composio_linkedin",
    }


async def _enrich_linkedin_post(user_id: str, post: Dict[str, Any]) -> Dict[str, Any]:
    urn = _linkedin_urn(post.get("id") or "")
    if not urn:
        return post
    try:
        result = await execute_action(user_id, ACTION_LI_POST, {"post_id": urn})
        pdata = _extract_action_data(result)
        if isinstance(pdata, dict):
            text = pdata.get("commentary") or pdata.get("text") or pdata.get("content")
            if isinstance(text, dict):
                text = text.get("text") or ""
            if text:
                post["message"] = str(text)
                post["content"] = str(text)
                post["caption"] = str(text)
            social = pdata.get("socialDetail") or pdata.get("social_detail") or {}
            if isinstance(social, dict):
                summary = social.get("totalShareStatistics") or social.get("total_share_statistics") or social
                if isinstance(summary, dict):
                    post["likes"] = _int_metric(summary.get("likeCount"), summary.get("like_count"), post.get("likes"))
                    post["commentCount"] = _int_metric(
                        summary.get("commentCount"), summary.get("comment_count"), post.get("commentCount"),
                    )
                    post["comments_count"] = post["commentCount"]
                    post["shares"] = _int_metric(summary.get("shareCount"), summary.get("share_count"), post.get("shares"))
        reactions = await execute_action(
            user_id,
            ACTION_LI_LIST_REACTIONS,
            {"entity": urn, "count": 50},
        )
        rdata = _extract_action_data(reactions)
        rrows = _rows(rdata)
        if not rrows and isinstance(rdata, dict):
            rrows = _rows(rdata.get("elements"))
        if rrows and not post.get("likes"):
            post["likes"] = len(rrows)
    except Exception as exc:
        logger.debug("[composio-engagement] LI enrich %s: %s", urn, exc)
    return post


async def _fetch_linkedin_posts(
    db,
    user: Dict[str, Any],
    user_id: str,
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    """LinkedIn has no bulk list API — load CRM-published posts and enrich via Composio."""
    conn_id = await _connection_id(user_id, TOOLKIT_LINKEDIN)
    if not conn_id:
        return []

    uid = user.get("_id") or user.get("user_id")
    query = {
        "user_id": uid,
        "status": "published",
        "channels": {"$in": ["linkedin"]},
    }
    rows = await db.scheduled_posts.find(query).sort("published_at", -1).to_list(max(limit, 50))

    posts: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ext = row.get("external_post_id") or row.get("zernio_post_id") or ""
        urn = _extract_linkedin_urn_from_external(str(ext))
        if not urn or urn in seen:
            continue
        seen.add(urn)
        caption = row.get("caption") or row.get("content") or row.get("title") or row.get("body") or ""
        normalized = _normalize_linkedin_post(
            {
                "id": urn,
                "commentary": caption,
                "created_at": row.get("published_at") or row.get("scheduled_at"),
                "likes": (row.get("engagement") or {}).get("likes") if isinstance(row.get("engagement"), dict) else 0,
                "commentCount": (row.get("engagement") or {}).get("comments") if isinstance(row.get("engagement"), dict) else 0,
            },
            connection_id=conn_id,
            fallback_id=urn,
        )
        posts.append(normalized)

    if posts:
        enriched = await asyncio.gather(*[_enrich_linkedin_post(user_id, p) for p in posts[: min(len(posts), 15)]])
        posts = list(enriched)

    return posts[:limit]


def _normalize_twitter_post(tweet: Dict[str, Any], *, connection_id: str) -> Dict[str, Any]:
    tid = str(tweet.get("id") or "")
    metrics = tweet.get("public_metrics") or {}
    text = tweet.get("text") or ""
    return {
        "id": tid,
        "accountId": connection_id,
        "account_id": connection_id,
        "platform": "twitter",
        "message": text,
        "content": text,
        "likes": _int_metric(metrics.get("like_count")),
        "shares": _int_metric(metrics.get("retweet_count")),
        "commentCount": _int_metric(metrics.get("reply_count")),
        "comments_count": _int_metric(metrics.get("reply_count")),
        "createdTime": _normalize_time(tweet.get("created_at")),
        "created_at": _normalize_time(tweet.get("created_at")),
    }


def _parse_fb_insights(raw: Any) -> Dict[str, int]:
    out = {"impressions": 0, "reach": 0, "clicks": 0}
    rows = _rows(raw)
    for row in rows:
        name = str(row.get("name") or "").lower()
        values = row.get("values") or []
        val = 0
        if isinstance(values, list) and values:
            val = _int_metric(values[-1].get("value") if isinstance(values[-1], dict) else values[-1])
        if "view" in name or "impression" in name:
            out["impressions"] = max(out["impressions"], val)
            out["reach"] = max(out["reach"], val)
        if "click" in name:
            out["clicks"] = val
    return out


def _parse_ig_insights(raw: Any) -> Dict[str, int]:
    out = {"impressions": 0, "reach": 0, "likes": 0, "comments": 0, "saves": 0, "shares": 0}
    rows = _rows(raw)
    for row in rows:
        name = str(row.get("name") or "").lower()
        values = row.get("values") or []
        total = row.get("total_value") or {}
        val = 0
        if isinstance(total, dict) and total.get("value") is not None:
            val = _int_metric(total.get("value"))
        elif isinstance(values, list) and values:
            val = _int_metric(values[-1].get("value") if isinstance(values[-1], dict) else values[-1])
        if name in ("reach",):
            out["reach"] = val
        elif name in ("views", "impressions", "plays"):
            out["impressions"] = val
        elif name in ("likes",):
            out["likes"] = val
        elif name in ("comments",):
            out["comments"] = val
        elif name in ("saved", "saves"):
            out["saves"] = val
        elif name in ("shares",):
            out["shares"] = val
    return out


async def _enrich_fb_post(user_id: str, post: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(post.get("id") or "")
    if not pid:
        return post
    try:
        reactions = await execute_action(user_id, ACTION_FB_POST_REACTIONS, {"post_id": pid, "limit": 1})
        rdata = _extract_action_data(reactions)
        summary = (rdata or {}).get("summary") if isinstance(rdata, dict) else {}
        if isinstance(summary, dict) and summary.get("total_count") is not None:
            post["likes"] = _int_metric(summary.get("total_count"))
        insights = await execute_action(
            user_id,
            ACTION_FB_POST_INSIGHTS,
            {"post_id": pid, "metrics": "post_media_view"},
        )
        metrics = _parse_fb_insights(_extract_action_data(insights))
        post["impressions"] = metrics.get("impressions", 0)
        post["reach"] = metrics.get("reach", 0)
        post["clicks"] = metrics.get("clicks", 0)
    except Exception as exc:
        logger.debug("[composio-engagement] FB enrich %s: %s", pid, exc)
    return post


async def _enrich_ig_media(user_id: str, post: Dict[str, Any]) -> Dict[str, Any]:
    mid = str(post.get("id") or "")
    if not mid:
        return post
    try:
        insights = await execute_action(
            user_id,
            ACTION_IG_MEDIA_INSIGHTS,
            {
                "ig_media_id": mid,
                "metric": ["reach", "views", "likes", "comments", "saved", "shares"],
            },
        )
        metrics = _parse_ig_insights(_extract_action_data(insights))
        if metrics.get("likes"):
            post["likes"] = metrics["likes"]
        if metrics.get("comments"):
            post["commentCount"] = metrics["comments"]
            post["comments_count"] = metrics["comments"]
        post["reach"] = metrics.get("reach", 0)
        post["impressions"] = metrics.get("impressions", 0)
        post["saves"] = metrics.get("saves", 0)
        post["shares"] = metrics.get("shares", 0)
    except Exception as exc:
        logger.debug("[composio-engagement] IG enrich %s: %s", mid, exc)
    return post


async def _fetch_facebook_posts(
    db,
    user_id: str,
    *,
    limit: int,
    enrich: bool = True,
) -> List[Dict[str, Any]]:
    conn_id = await _connection_id(user_id, TOOLKIT_FACEBOOK)
    if not conn_id:
        return []
    page_id, _ = await _facebook_page_id(db, user_id)
    if not page_id:
        return []

    result = await execute_action(
        user_id,
        ACTION_FB_PAGE_POSTS,
        {
            "page_id": page_id,
            "limit": min(limit, 50),
            "fields": "id,message,story,created_time,permalink_url,full_picture,shares,comments.summary(true),attachments",
        },
    )
    if result.get("error"):
        logger.warning("[composio-engagement] FB posts: %s", result["error"])
        return []

    posts = [_normalize_fb_post(p, connection_id=conn_id, page_id=page_id) for p in _rows(_extract_action_data(result))]
    if enrich and posts:
        posts = await asyncio.gather(*[_enrich_fb_post(user_id, p) for p in posts[: min(len(posts), 15)]])
    return list(posts)[:limit]


async def _fetch_instagram_posts(
    db,
    user_id: str,
    *,
    limit: int,
    enrich: bool = True,
) -> List[Dict[str, Any]]:
    conn_id = await _connection_id(user_id, TOOLKIT_INSTAGRAM)
    if not conn_id:
        return []
    ig_user_id = await resolve_instagram_user_id(db, user_id)
    if not ig_user_id:
        return []

    result = await execute_action(
        user_id,
        ACTION_IG_USER_MEDIA,
        {
            "ig_user_id": ig_user_id,
            "limit": min(limit, 50),
            "fields": "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,like_count,comments_count",
        },
    )
    if result.get("error"):
        logger.warning("[composio-engagement] IG media: %s", result["error"])
        return []

    posts = [_normalize_ig_media(m, connection_id=conn_id) for m in _rows(_extract_action_data(result))]
    if enrich and posts:
        posts = await asyncio.gather(*[_enrich_ig_media(user_id, p) for p in posts[: min(len(posts), 15)]])
    return list(posts)[:limit]


async def _fetch_twitter_posts(user_id: str, *, limit: int) -> List[Dict[str, Any]]:
    conn_id = await _connection_id(user_id, TOOLKIT_TWITTER)
    if not conn_id:
        return []
    me = await execute_action(user_id, ACTION_TWITTER_ME, {})
    me_data = _extract_action_data(me)
    username = ""
    if isinstance(me_data, dict):
        username = str(me_data.get("username") or me_data.get("data", {}).get("username") or "")
    if not username:
        return []

    result = await execute_action(
        user_id,
        ACTION_TWITTER_SEARCH,
        {
            "query": f"from:{username} -is:retweet",
            "max_results": min(limit, 50),
            "tweet_fields": ["created_at", "public_metrics", "text"],
        },
    )
    if result.get("error"):
        logger.warning("[composio-engagement] X posts: %s", result["error"])
        return []
    raw = _extract_action_data(result)
    tweets = _rows(raw)
    if not tweets and isinstance(raw, dict):
        tweets = _rows(raw.get("data"))
    return [_normalize_twitter_post(t, connection_id=conn_id) for t in tweets[:limit]]


async def list_posts(
    db,
    user: Dict[str, Any],
    *,
    platform: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    if not is_configured():
        return {"posts": [], "error": "COMPOSIO_API_KEY not configured"}

    user_id = await _tenant_id(user)
    plat = (platform or "").strip().lower()
    posts: List[Dict[str, Any]] = []

    if not plat or plat == "facebook":
        posts.extend(await _fetch_facebook_posts(db, user_id, limit=limit))
    if not plat or plat == "instagram":
        posts.extend(await _fetch_instagram_posts(db, user_id, limit=limit))
    if not plat or plat in ("twitter", "x"):
        posts.extend(await _fetch_twitter_posts(user_id, limit=limit))
    if not plat or plat == "linkedin":
        posts.extend(await _fetch_linkedin_posts(db, user, user_id, limit=limit))

    posts.sort(key=lambda p: p.get("createdTime") or p.get("created_at") or "", reverse=True)
    return {"posts": posts[:limit], "pagination": {"total": len(posts[:limit])}}


async def list_commented_posts(
    db,
    user: Dict[str, Any],
    *,
    platform: Optional[str] = None,
    account_id: Optional[str] = None,
    min_comments: Optional[int] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    del account_id
    threshold = max(0, int(min_comments or 1))
    res = await list_posts(db, user, platform=platform, limit=max(limit, 50))
    posts = res.get("posts") or []
    filtered = [
        p for p in posts
        if _int_metric(p.get("commentCount"), p.get("comments_count")) >= threshold
    ]
    return {"posts": filtered[:limit], "data": filtered[:limit], "pagination": {"total": len(filtered[:limit])}}


async def get_post_comments(
    db,
    user: Dict[str, Any],
    post_id: str,
    account_id: str,
    *,
    platform: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    user_id = await _tenant_id(user)
    plat = (platform or "").strip().lower()
    comments: List[Dict[str, Any]] = []

    if plat in ("", "facebook"):
        result = await execute_action(
            user_id,
            ACTION_FB_COMMENTS,
            {
                "object_id": post_id,
                "limit": min(limit, 100),
                "fields": "id,message,created_time,from,like_count,comment_count,parent",
            },
        )
        if result.get("success") or not result.get("error"):
            for row in _rows(_extract_action_data(result)):
                from_obj = row.get("from") or {}
                comments.append({
                    "id": str(row.get("id") or ""),
                    "commentId": str(row.get("id") or ""),
                    "message": row.get("message") or "",
                    "text": row.get("message") or "",
                    "username": from_obj.get("name") or from_obj.get("username") or "",
                    "from": from_obj,
                    "parent": row.get("parent"),
                    "replyCount": _int_metric(row.get("comment_count")),
                    "createdTime": _normalize_time(row.get("created_time")),
                    "created_at": _normalize_time(row.get("created_time")),
                })
            if comments:
                return {"comments": comments, "data": comments}

    if plat in ("", "instagram"):
        result = await execute_action(
            user_id,
            ACTION_IG_MEDIA_COMMENTS,
            {
                "ig_media_id": post_id,
                "limit": min(limit, 100),
                "fields": "id,text,username,timestamp,like_count,replies",
            },
        )
        if result.get("success") or not result.get("error"):
            for row in _rows(_extract_action_data(result)):
                comments.append({
                    "id": str(row.get("id") or ""),
                    "commentId": str(row.get("id") or ""),
                    "message": row.get("text") or "",
                    "text": row.get("text") or "",
                    "username": row.get("username") or "",
                    "replyCount": _int_metric((row.get("replies") or {}).get("count") if isinstance(row.get("replies"), dict) else 0),
                    "createdTime": _normalize_time(row.get("timestamp")),
                    "created_at": _normalize_time(row.get("timestamp")),
                })

    if plat in ("", "linkedin"):
        # LinkedIn Comments API listing is not exposed in Composio; return CRM-cached comments if any.
        cached = await db.social_linkedin_comments.find(
            {"user_id": user.get("_id"), "post_urn": _linkedin_urn(post_id)},
        ).sort("created_at", -1).to_list(min(limit, 100))
        for row in cached:
            if not isinstance(row, dict):
                continue
            comments.append({
                "id": str(row.get("comment_urn") or row.get("id") or ""),
                "commentId": str(row.get("comment_urn") or row.get("id") or ""),
                "message": row.get("text") or row.get("message") or "",
                "text": row.get("text") or row.get("message") or "",
                "username": row.get("author") or row.get("username") or "",
                "replyCount": 0,
                "createdTime": _normalize_time(row.get("created_at")),
                "created_at": _normalize_time(row.get("created_at")),
                "platform": "linkedin",
            })

    return {"comments": comments, "data": comments}


async def reply_to_comment(
    db,
    user: Dict[str, Any],
    post_id: str,
    account_id: str,
    comment_id: str,
    message: str,
    *,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    del account_id
    user_id = await _tenant_id(user)
    plat = (platform or "").strip().lower()
    text = (message or "").strip()
    if not text:
        return {"error": "message is required"}

    if plat == "instagram":
        result = await execute_action(
            user_id,
            ACTION_IG_COMMENT_REPLY,
            {"ig_comment_id": comment_id, "message": text},
        )
    elif plat == "linkedin":
        post_urn = _linkedin_urn(post_id)
        author_urn, author_err = await _resolve_linkedin_author(db, user_id)
        if author_err or not author_urn:
            return {"error": author_err or "LinkedIn author URN missing. Reconnect LinkedIn posting."}
        target_urn = _linkedin_urn(comment_id) if comment_id and "urn:li:comment" in str(comment_id) else post_urn
        params: Dict[str, Any] = {
            "actor": author_urn,
            "object": post_urn,
            "target_urn": target_urn,
            "message": {"text": text},
        }
        if comment_id and "urn:li:comment" in str(comment_id):
            params["parentComment"] = _linkedin_urn(comment_id)
        result = await execute_action(user_id, ACTION_LI_COMMENT, params)
    else:
        target = comment_id or post_id
        result = await execute_action(
            user_id,
            ACTION_FB_CREATE_COMMENT,
            {"object_id": target, "message": text},
        )

    if result.get("error"):
        return {"error": result["error"]}
    return {"success": True, "data": result.get("data")}


async def get_analytics(
    db,
    user: Dict[str, Any],
    *,
    platform: Optional[str] = None,
    account_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    del account_id
    res = await list_posts(db, user, platform=platform, limit=limit)
    posts = res.get("posts") or []
    analytics_rows = []
    for p in posts:
        analytics_rows.append({
            **p,
            "analytics": {
                "likes": p.get("likes", 0),
                "comments": p.get("commentCount", p.get("comments_count", 0)),
                "shares": p.get("shares", 0),
                "reach": p.get("reach", 0),
                "impressions": p.get("impressions", 0),
                "clicks": p.get("clicks", 0),
                "saves": p.get("saves", 0),
            },
        })
    return {"analytics": analytics_rows, "data": analytics_rows, "posts": analytics_rows}


async def get_single_post_analytics(
    db,
    user: Dict[str, Any],
    post_id: str,
    *,
    platform: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    del account_id
    user_id = await _tenant_id(user)
    plat = (platform or "facebook").strip().lower()
    row: Dict[str, Any] = {"id": post_id, "platform": plat}

    if plat == "instagram":
        media = await execute_action(user_id, ACTION_IG_MEDIA, {"ig_media_id": post_id})
        mdata = _extract_action_data(media)
        if isinstance(mdata, dict):
            conn = await _connection_id(user_id, TOOLKIT_INSTAGRAM) or ""
            row = _normalize_ig_media(mdata, connection_id=conn)
        row = await _enrich_ig_media(user_id, row)
    elif plat in ("twitter", "x"):
        conn = await _connection_id(user_id, TOOLKIT_TWITTER) or ""
        result = await execute_action(user_id, ACTION_TWITTER_POST, {"id": post_id})
        tdata = _extract_action_data(result)
        if isinstance(tdata, dict):
            row = _normalize_twitter_post(tdata, connection_id=conn)
        analytics = await execute_action(user_id, ACTION_TWITTER_POST_ANALYTICS, {"ids": [post_id]})
        adata = _extract_action_data(analytics)
        if isinstance(adata, dict):
            metrics = (adata.get("data") or [{}])[0] if isinstance(adata.get("data"), list) else adata
            if isinstance(metrics, dict):
                row["impressions"] = _int_metric(metrics.get("impression_count"), metrics.get("impressions"))
    elif plat == "linkedin":
        urn = _linkedin_urn(post_id)
        conn = await _connection_id(user_id, TOOLKIT_LINKEDIN) or ""
        row = _normalize_linkedin_post({"id": urn}, connection_id=conn, fallback_id=urn)
        row = await _enrich_linkedin_post(user_id, row)
    else:
        conn = await _connection_id(user_id, TOOLKIT_FACEBOOK) or ""
        page_id, _ = await _facebook_page_id(db, user_id)
        fb_res = await execute_action(user_id, "FACEBOOK_GET_POST", {"post_id": post_id})
        pdata = _extract_action_data(fb_res)
        if isinstance(pdata, dict):
            row = _normalize_fb_post(pdata, connection_id=conn, page_id=page_id or "")
        row = await _enrich_fb_post(user_id, row)

    return {
        "analytics": [row],
        "data": [row],
        "posts": [row],
    }

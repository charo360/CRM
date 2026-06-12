"""Social integration snapshot for integrations_status (Composio + Unipile)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import composio_inbox
import unipile_inbox
from social_accounts_service import list_connected_accounts
from social_composio_engagement import list_commented_posts, list_posts
from social_inbox_service import list_conversations

logger = logging.getLogger(__name__)


def _empty_social_activity() -> Dict[str, Any]:
    return {
        "accounts_count": 0,
        "platforms": [],
        "accounts_by_platform": {},
        "window_days": None,
        "recent_inbox_conversations": 0,
        "recent_comments": 0,
        "comments_by_platform_recent": {},
        "recent_posts": 0,
        "recent_unread_conversations": 0,
        "total_inbox_conversations_fetched": 0,
        "total_comments_fetched": 0,
        "total_posts_fetched": 0,
        "inbox_by_platform_recent": {},
        "posts_by_platform_recent": {},
        "latest_messages_sample": [],
        "latest_messages_by_conversation": {},
        "brand_voice_signals": {
            "outgoing_messages_analyzed": 0,
            "avg_outgoing_length": 0,
            "uses_emoji_ratio": 0.0,
            "uses_question_ratio": 0.0,
            "common_openers": [],
        },
        "performance_totals": {
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "reach": 0,
            "clicks": 0,
        },
        "top_post": None,
        "latest_conversations": [],
        "latest_posts": [],
        "last_message_at": None,
        "last_comment_at": None,
        "last_post_at": None,
        "post_data_source": "composio_live",
        "fetch_diagnostics": {
            "accounts": {"status_code": None, "ok": False, "error": None},
            "inbox": {"status_code": None, "ok": False, "error": None},
            "comments": {"status_code": None, "ok": False, "error": None},
            "posts": {"status_code": None, "ok": False, "error": None},
            "analytics": {"status_code": None, "ok": False, "error": None},
        },
        "checked_at": datetime.utcnow().isoformat(),
    }


def _diag_ok(key: str, activity: Dict[str, Any]) -> None:
    activity["fetch_diagnostics"][key]["ok"] = True
    activity["fetch_diagnostics"][key]["status_code"] = 200


def _diag_fail(key: str, activity: Dict[str, Any], error: str) -> None:
    err = (error or "")[:300]
    activity["fetch_diagnostics"][key]["ok"] = False
    activity["fetch_diagnostics"][key]["error"] = err
    low = err.lower()
    if "permission" in low or "403" in low or "401" in low:
        activity["fetch_diagnostics"][key]["status_code"] = 403
    else:
        activity["fetch_diagnostics"][key]["status_code"] = 0


def _int_metric(*values: Any) -> int:
    for v in values:
        if v is None:
            continue
        try:
            return max(0, int(float(v)))
        except (TypeError, ValueError):
            continue
    return 0


def _accounts_from_composio(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": str(a.get("id") or a.get("accountId") or ""),
            "platform": str(a.get("platform") or "").lower(),
            "username": a.get("username"),
            "name": a.get("name") or a.get("displayName"),
            "page_name": a.get("name") or a.get("displayName"),
            "connected": True,
        }
        for a in rows
        if isinstance(a, dict) and a.get("platform")
    ]


async def _sample_brand_voice(
    db,
    user: Dict[str, Any],
    conversations: List[Dict[str, Any]],
    business_id: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    by_conversation: Dict[str, List[Dict[str, Any]]] = {}

    for c in conversations[:10]:
        conv_id = str(c.get("id") or c.get("conversation_id") or "")
        if not conv_id:
            continue
        platform = str(c.get("platform") or "").lower()
        account_id = str(c.get("accountId") or c.get("account_id") or "")
        msgs: List[Dict[str, Any]] = []
        try:
            if platform == "linkedin" and unipile_inbox.is_available():
                msgs = await unipile_inbox.get_conversation_messages(
                    db, user["_id"], business_id, conv_id,
                )
            elif account_id:
                msgs = await composio_inbox.get_conversation_messages(
                    business_id, conv_id, account_id,
                )
        except Exception as exc:
            logger.warning("[integrations_status] message sample failed for %s: %s", conv_id, exc)
            continue

        bucket: List[Dict[str, Any]] = []
        for m in (msgs or [])[-10:]:
            if not isinstance(m, dict):
                continue
            text = (
                (m.get("message") if isinstance(m.get("message"), str) else None)
                or (m.get("text") if isinstance(m.get("text"), str) else None)
                or (m.get("content") if isinstance(m.get("content"), str) else None)
                or ""
            ).strip()
            if not text:
                continue
            direction = str(
                m.get("direction")
                or m.get("type")
                or ("outgoing" if m.get("fromMe") else "incoming")
            ).lower()
            row = {
                "conversation_id": conv_id,
                "platform": platform,
                "username": c.get("username") or c.get("participant_name") or c.get("participant"),
                "direction": direction,
                "text": text[:280],
                "created_at": m.get("createdAt") or m.get("created_at") or m.get("timestamp"),
            }
            bucket.append(row)
            collected.append(row)
        if bucket:
            by_conversation[conv_id] = bucket[-10:]
        if len(collected) >= 50:
            break

    outgoing = [m for m in collected if "out" in str(m.get("direction") or "").lower()]
    signals = {
        "outgoing_messages_analyzed": 0,
        "avg_outgoing_length": 0,
        "uses_emoji_ratio": 0.0,
        "uses_question_ratio": 0.0,
        "common_openers": [],
    }
    if outgoing:
        total_len = sum(len(str(m.get("text") or "")) for m in outgoing)
        emoji_hits = sum(1 for m in outgoing if any(ord(ch) > 10000 for ch in str(m.get("text") or "")))
        question_hits = sum(1 for m in outgoing if "?" in str(m.get("text") or ""))
        openers: Dict[str, int] = {}
        for m in outgoing:
            txt = str(m.get("text") or "").strip().lower()
            first = txt.split(" ")[0] if txt else ""
            if first:
                openers[first] = openers.get(first, 0) + 1
        signals = {
            "outgoing_messages_analyzed": len(outgoing),
            "avg_outgoing_length": int(round(total_len / max(len(outgoing), 1))),
            "uses_emoji_ratio": round(emoji_hits / max(len(outgoing), 1), 3),
            "uses_question_ratio": round(question_hits / max(len(outgoing), 1), 3),
            "common_openers": [k for k, _ in sorted(openers.items(), key=lambda kv: kv[1], reverse=True)[:5]],
        }

    return collected[-50:], by_conversation, signals


async def fetch_social_integrations_snapshot(
    db,
    user: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (social_accounts, social_activity) for integrations_status."""
    activity = _empty_social_activity()
    business_id = str(user.get("business_id") or user["_id"])

    try:
        raw_accounts = await list_connected_accounts(db, user)
    except Exception as exc:
        _diag_fail("accounts", activity, str(exc))
        return [], activity

    social_accounts = _accounts_from_composio(raw_accounts)
    if not social_accounts:
        _diag_ok("accounts", activity)
        return [], activity

    _diag_ok("accounts", activity)
    activity["accounts_count"] = len(social_accounts)
    platforms = sorted({str(a.get("platform") or "").lower() for a in social_accounts if a.get("platform")})
    activity["platforms"] = platforms
    activity["accounts_by_platform"] = {
        p: sum(1 for a in social_accounts if str(a.get("platform") or "").lower() == p)
        for p in platforms
    }

    posts_res, commented_res, conversations = await asyncio.gather(
        list_posts(db, user, limit=50),
        list_commented_posts(db, user, min_comments=1, limit=100),
        list_conversations(db, user, limit=50),
        return_exceptions=True,
    )

    if isinstance(posts_res, Exception):
        _diag_fail("posts", activity, str(posts_res))
        posts: List[Dict[str, Any]] = []
    else:
        posts = posts_res.get("posts") or []
        if posts_res.get("error"):
            _diag_fail("posts", activity, str(posts_res["error"]))
        else:
            _diag_ok("posts", activity)

    if isinstance(commented_res, Exception):
        _diag_fail("comments", activity, str(commented_res))
        commented_posts: List[Dict[str, Any]] = []
    else:
        commented_posts = commented_res.get("posts") or []
        _diag_ok("comments", activity)

    if isinstance(conversations, Exception):
        _diag_fail("inbox", activity, str(conversations))
        conversations = []
    elif conversations:
        _diag_ok("inbox", activity)
    else:
        _diag_ok("inbox", activity)

    if posts:
        activity["total_posts_fetched"] = len(posts)
        activity["recent_posts"] = len(posts)
        posts_by_platform: Dict[str, int] = {}
        top_score = -1
        latest_posts: List[Dict[str, Any]] = []
        for p in posts:
            if not isinstance(p, dict):
                continue
            platform = str(p.get("platform") or "").lower() or "unknown"
            posts_by_platform[platform] = posts_by_platform.get(platform, 0) + 1
            analytics = p.get("analytics") if isinstance(p.get("analytics"), dict) else {}
            likes = _int_metric(p.get("likes"), analytics.get("likes"))
            comments = _int_metric(p.get("commentCount"), p.get("comments_count"), analytics.get("comments"))
            shares = _int_metric(p.get("shares"), analytics.get("shares"))
            reach = _int_metric(p.get("reach"), p.get("impressions"), analytics.get("reach"), analytics.get("impressions"))
            clicks = _int_metric(p.get("clicks"), analytics.get("clicks"))
            activity["performance_totals"]["likes"] += likes
            activity["performance_totals"]["comments"] += comments
            activity["performance_totals"]["shares"] += shares
            activity["performance_totals"]["reach"] += reach
            activity["performance_totals"]["clicks"] += clicks
            score = likes + comments * 2 + shares * 3 + clicks
            if score > top_score:
                top_score = score
                activity["top_post"] = {
                    "post_id": p.get("id"),
                    "platform": platform,
                    "title": p.get("content") or p.get("caption") or p.get("message"),
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "reach": reach,
                    "clicks": clicks,
                    "engagement_score": score,
                }
            latest_posts.append({
                "platform": platform,
                "post_id": p.get("id"),
                "status": "published",
                "title": p.get("content") or p.get("caption") or p.get("message"),
                "scheduled_at": None,
                "published_at": p.get("createdTime") or p.get("created_at") or p.get("createdAt"),
            })
        activity["posts_by_platform_recent"] = posts_by_platform
        activity["latest_posts"] = latest_posts[:20]
        post_times = [
            str(item.get("published_at") or item.get("scheduled_at"))
            for item in activity["latest_posts"]
            if item.get("published_at") or item.get("scheduled_at")
        ]
        if post_times:
            activity["last_post_at"] = post_times[0]
        _diag_ok("analytics", activity)

    if commented_posts:
        activity["total_comments_fetched"] = len(commented_posts)
        activity["recent_comments"] = sum(
            _int_metric(p.get("commentCount"), p.get("comments_count")) for p in commented_posts
        )
        comments_by_platform: Dict[str, int] = {}
        for p in commented_posts:
            plat = str(p.get("platform") or "").lower() or "unknown"
            comments_by_platform[plat] = comments_by_platform.get(plat, 0) + 1
        activity["comments_by_platform_recent"] = comments_by_platform

    if not activity["recent_posts"] and commented_posts:
        activity["total_posts_fetched"] = len(commented_posts)
        activity["recent_posts"] = len(commented_posts)
        activity["latest_posts"] = [
            {
                "platform": str(p.get("platform") or "").lower(),
                "post_id": p.get("id"),
                "status": "active_via_comments",
                "title": p.get("content") or p.get("caption"),
                "scheduled_at": None,
                "published_at": p.get("createdTime") or p.get("created_at"),
            }
            for p in commented_posts[:20]
        ]
        activity["post_data_source"] = "composio_comments_fallback"

    if activity["recent_posts"] == 0:
        internal_rows = await db.scheduled_posts.find(
            {"user_id": user["_id"], "status": {"$in": ["published", "scheduled"]}},
        ).sort("scheduled_at", -1).to_list(100)
        if internal_rows:
            latest_internal = [p for p in internal_rows if isinstance(p, dict)]
            activity["total_posts_fetched"] = len(latest_internal)
            activity["recent_posts"] = len(latest_internal)
            activity["latest_posts"] = [
                {
                    "platform": str((p or {}).get("platform") or "").lower(),
                    "post_id": (p or {}).get("_id") or (p or {}).get("id"),
                    "status": (p or {}).get("status"),
                    "title": (p or {}).get("title") or (p or {}).get("caption") or (p or {}).get("content"),
                    "scheduled_at": (p or {}).get("scheduled_at"),
                    "published_at": (p or {}).get("published_at"),
                }
                for p in latest_internal[:20]
            ]
            activity["post_data_source"] = "internal_scheduled_posts"

    if conversations:
        activity["total_inbox_conversations_fetched"] = len(conversations)
        activity["recent_inbox_conversations"] = len(conversations)
        activity["recent_unread_conversations"] = sum(
            1 for c in conversations
            if isinstance(c, dict) and bool(
                (c.get("unread") is True) or ((c.get("unreadCount") or c.get("unread_count") or 0) > 0)
            )
        )
        inbox_by_platform: Dict[str, int] = {}
        for c in conversations:
            plat = str((c or {}).get("platform") or "").lower() or "unknown"
            inbox_by_platform[plat] = inbox_by_platform.get(plat, 0) + 1
        activity["inbox_by_platform_recent"] = inbox_by_platform
        activity["latest_conversations"] = [
            {
                "platform": str((c or {}).get("platform") or "").lower(),
                "conversation_id": (c or {}).get("id") or (c or {}).get("conversationId"),
                "username": (c or {}).get("username") or (c or {}).get("participant_name") or (c or {}).get("participant"),
                "last_message": (c or {}).get("last_message") or (c or {}).get("lastMessage"),
                "unread_count": (c or {}).get("unreadCount") or (c or {}).get("unread_count") or (1 if c.get("unread") else 0),
                "updated_at": (c or {}).get("last_message_at") or (c or {}).get("updatedAt") or (c or {}).get("updated_at"),
            }
            for c in conversations[:10]
            if isinstance(c, dict)
        ]
        conv_times = [
            str(item.get("updated_at"))
            for item in activity["latest_conversations"]
            if item.get("updated_at")
        ]
        if conv_times:
            activity["last_message_at"] = conv_times[0]

        try:
            msgs, by_conv, signals = await _sample_brand_voice(db, user, conversations, business_id)
            activity["latest_messages_sample"] = msgs
            activity["latest_messages_by_conversation"] = by_conv
            activity["brand_voice_signals"] = signals
        except Exception as exc:
            logger.warning("[integrations_status] brand voice sampling failed: %s", exc)

    return social_accounts, activity


async def fetch_social_conversation_history(
    db,
    user: Dict[str, Any],
    *,
    platform_filter: str = "",
    query: str = "",
    limit: int = 20,
) -> Dict[str, Any]:
    """Conversation history for get_social_conversation_history tool."""
    business_id = str(user.get("business_id") or user["_id"])
    accounts = await list_connected_accounts(db, user)
    if not accounts:
        return {
            "error": "No social accounts connected. Connect platforms in Integrations first.",
            "count": 0,
            "conversations": [],
        }

    plat = platform_filter.strip().lower()
    conversations_raw = await list_conversations(db, user, platform=plat or None, limit=50)
    if not conversations_raw:
        return {
            "count": 0,
            "platform_filter": plat or None,
            "query": query or None,
            "conversations": [],
            "notice": "No social conversations returned from connected channels.",
        }

    q = query.strip().lower()
    results: List[Dict[str, Any]] = []
    for c in conversations_raw:
        if not isinstance(c, dict):
            continue
        conv_id = str(c.get("id") or c.get("conversationId") or "")
        if not conv_id:
            continue
        platform = str(c.get("platform") or "").lower()
        username = c.get("username") or c.get("participant_name") or c.get("participant")
        account_id = str(c.get("accountId") or c.get("account_id") or "")
        parsed_msgs: List[Dict[str, Any]] = []
        try:
            if platform == "linkedin" and unipile_inbox.is_available():
                msgs = await unipile_inbox.get_conversation_messages(
                    db, user["_id"], business_id, conv_id,
                )
            elif account_id:
                msgs = await composio_inbox.get_conversation_messages(
                    business_id, conv_id, account_id,
                )
            else:
                msgs = []
            for m in (msgs or [])[-12:]:
                if not isinstance(m, dict):
                    continue
                text = (
                    (m.get("message") if isinstance(m.get("message"), str) else None)
                    or (m.get("text") if isinstance(m.get("text"), str) else None)
                    or (m.get("content") if isinstance(m.get("content"), str) else None)
                    or ""
                ).strip()
                if not text:
                    continue
                parsed_msgs.append({
                    "direction": str(
                        m.get("direction")
                        or m.get("type")
                        or ("outgoing" if m.get("fromMe") else "incoming")
                    ).lower(),
                    "text": text[:320],
                    "created_at": m.get("createdAt") or m.get("created_at") or m.get("timestamp"),
                })
        except Exception:
            continue

        if q:
            hay = " ".join([
                str(username or "").lower(),
                str((c.get("last_message") or c.get("lastMessage") or "")).lower(),
                " ".join(str(m.get("text") or "").lower() for m in parsed_msgs),
            ])
            if q not in hay:
                continue

        results.append({
            "conversation_id": conv_id,
            "account_id": account_id or None,
            "platform": platform,
            "username": username,
            "unread_count": c.get("unreadCount") or c.get("unread_count") or (1 if c.get("unread") else 0),
            "updated_at": c.get("last_message_at") or c.get("updatedAt") or c.get("updated_at"),
            "last_message": c.get("last_message") or c.get("lastMessage"),
            "messages": parsed_msgs,
        })

    return {
        "count": len(results[:limit]),
        "platform_filter": plat or None,
        "query": q or None,
        "conversations": results[:limit],
    }

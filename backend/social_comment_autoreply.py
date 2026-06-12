"""
Comment auto-reply via Composio (Facebook / Instagram).

Polls for new post comments when auto-reply is enabled — no Zernio webhook required.
When you add Meta app webhooks later, call `handle_comment_event()` from that handler.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from personal_profile import personal_profile_from_user, substitute_social_template
from social_comment_settings import read_comment_autoreply_settings
from social_composio_engagement import get_post_comments, list_commented_posts, reply_to_comment

logger = logging.getLogger(__name__)

MAX_USERS_PER_CYCLE = 40
MAX_POSTS_PER_USER = 12
MAX_COMMENTS_PER_POST = 25
NEW_COMMENT_WINDOW_MINUTES = 15

_POLL_PLATFORMS = ("facebook", "instagram")


def pick_comment_autoreply_message(
    settings: dict,
    comment_text: str,
    author_name: str = "",
    profile: Optional[dict] = None,
    platform: str = "",
) -> str:
    text = (comment_text or "").lower()
    chosen = ""
    for rule in (settings.get("keyword_rules") or []):
        if not isinstance(rule, dict):
            continue
        keyword = str(rule.get("keyword") or "").strip().lower()
        message = str(rule.get("message") or "").strip()
        if keyword and message and keyword in text:
            chosen = message
            break
    if not chosen:
        chosen = str(settings.get("default_message") or "").strip()
    if not chosen:
        return ""
    first = (author_name or "").strip().split(" ")[0]
    prof = profile or {}
    return substitute_social_template(
        chosen, prof, recipient_first_name=first, platform=platform
    )


async def build_native_comment_reply(
    db,
    user: dict,
    comment_text: str,
    author_name: str = "",
    profile: Optional[dict] = None,
    platform: str = "",
    post_caption: str = "",
) -> str:
    from social_draft_service import draft_social_reply

    result = await draft_social_reply(
        db,
        user,
        platform=platform,
        channel="comment",
        recipient_name=author_name,
        their_message=comment_text or "",
        post_caption=post_caption,
    )
    return str(result.get("message") or "")


async def pick_comment_steps(
    db,
    settings: dict,
    comment_event: dict,
    user: Optional[dict] = None,
) -> list:
    profile = personal_profile_from_user(user or {})
    author_first = str(comment_event.get("author_name") or "").strip().split(" ")[0]
    platform = str(comment_event.get("platform") or "")

    mode = str(settings.get("engine_mode") or "hybrid").strip().lower()
    if mode not in {"native_ai_all_posts", "manychat_per_post", "hybrid"}:
        mode = "hybrid"
    post_id = str(comment_event.get("post_id") or "").strip()
    manychat_posts = {str(x).strip() for x in (settings.get("manychat_post_ids") or []) if str(x).strip()}
    manychat_for_post = (not manychat_posts) or (post_id in manychat_posts)
    use_manychat = mode == "manychat_per_post" or (mode == "hybrid" and manychat_for_post)

    if use_manychat:
        chain = settings.get("chain_steps") or []
        valid = []
        for step in chain:
            if not isinstance(step, dict):
                continue
            stype = str(step.get("type") or "text").strip().lower()
            if stype not in {"text", "image", "video", "file"}:
                stype = "text"
            msg = str(step.get("message") or "").strip()
            media_url = str(step.get("media_url") or "").strip()
            delay_seconds = int(step.get("delay_seconds") or 0)
            if stype == "text" and not msg:
                continue
            if stype != "text" and not media_url:
                continue
            if stype == "text" and msg:
                msg = substitute_social_template(
                    msg, profile, recipient_first_name=author_first, platform=platform
                )
            valid.append(
                {
                    "type": stype,
                    "message": msg,
                    "media_url": media_url,
                    "delay_seconds": max(0, min(delay_seconds, 120)),
                }
            )
        if valid:
            return valid
        msg = pick_comment_autoreply_message(
            settings=settings,
            comment_text=str(comment_event.get("comment_text") or ""),
            author_name=str(comment_event.get("author_name") or ""),
            profile=profile,
            platform=platform,
        )
        if msg:
            return [{"type": "text", "message": msg, "delay_seconds": 0}]
        return []

    msg = await build_native_comment_reply(
        db,
        user or {},
        comment_text=str(comment_event.get("comment_text") or ""),
        author_name=str(comment_event.get("author_name") or ""),
        profile=profile,
        platform=platform,
        post_caption=str(comment_event.get("post_caption") or comment_event.get("post_text") or ""),
    )
    return [{"type": "text", "message": msg, "delay_seconds": 0}] if msg else []


async def send_composio_comment_reply(
    db,
    user: dict,
    post_id: str,
    account_id: str,
    comment_id: str,
    message: str,
    *,
    platform: str = "",
    step: Optional[dict] = None,
) -> bool:
    step = step or {"type": "text", "message": message}
    stype = str(step.get("type") or "text").strip().lower()
    text = str(step.get("message") or message or "").strip()
    if stype == "text" and not text:
        return False
    if stype != "text":
        logger.warning("[CommentAutoReply] non-text steps not supported in poll yet")
        return False
    if not (post_id and comment_id and text):
        return False
    try:
        result = await reply_to_comment(
            db,
            user,
            post_id,
            account_id,
            comment_id,
            text[:900],
            platform=platform,
        )
        if result.get("error"):
            logger.warning("[CommentAutoReply] reply failed: %s", result["error"])
            return False
        return bool(result.get("success"))
    except Exception as exc:
        logger.warning("[CommentAutoReply] reply error: %s", exc)
        return False


def _parse_ts(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


async def _owner_ids(db, user: dict) -> Dict[str, str]:
    """Page / IG usernames to skip our own comments."""
    out: Dict[str, str] = {"facebook_page_id": "", "instagram_username": ""}
    business_id = str(user.get("business_id") or user["_id"])
    try:
        from social_composio_publish import get_social_settings

        settings = await get_social_settings(db, business_id)
        out["facebook_page_id"] = str(settings.get("facebook_page_id") or "").strip()
    except Exception:
        pass
    try:
        from composio_service import execute_action

        res = await execute_action(business_id, "INSTAGRAM_GET_USER_INFO", {})
        if res.get("success") and isinstance(res.get("data"), dict):
            out["instagram_username"] = str(res["data"].get("username") or "").strip().lower()
    except Exception:
        pass
    return out


def _is_own_comment(comment: dict, platform: str, owner: Dict[str, str]) -> bool:
    plat = (platform or "").strip().lower()
    if plat == "facebook":
        from_obj = comment.get("from") if isinstance(comment.get("from"), dict) else {}
        author_id = str(from_obj.get("id") or "")
        page_id = owner.get("facebook_page_id") or ""
        return bool(page_id and author_id and author_id == page_id)
    if plat == "instagram":
        username = str(comment.get("username") or "").strip().lower()
        page_user = owner.get("instagram_username") or ""
        return bool(page_user and username and username == page_user)
    return False


def _comment_is_top_level(comment: dict) -> bool:
    parent = comment.get("parent")
    if parent:
        return False
    return True


async def _already_handled(db, user_id: Any, comment_id: str) -> bool:
    doc = await db.social_comment_autoreply_state.find_one(
        {"user_id": user_id, "comment_id": comment_id}
    )
    return bool(doc)


async def _mark_handled(
    db,
    user_id: Any,
    comment_id: str,
    *,
    post_id: str = "",
    platform: str = "",
    baseline_only: bool = False,
) -> None:
    await db.social_comment_autoreply_state.update_one(
        {"user_id": user_id, "comment_id": comment_id},
        {"$set": {
            "user_id": user_id,
            "comment_id": comment_id,
            "post_id": post_id,
            "platform": platform,
            "baseline_only": baseline_only,
            "handled_at": datetime.utcnow(),
        }},
        upsert=True,
    )


def _post_allowed(settings: dict, post_id: str) -> bool:
    if bool(settings.get("apply_all_posts", True)):
        return True
    allowed = {str(x).strip() for x in (settings.get("post_ids") or []) if str(x).strip()}
    return post_id in allowed


async def handle_comment_event(db, user: dict, comment_event: dict) -> bool:
    """Process one comment (webhook or poll). Returns True if a reply was sent."""
    settings = read_comment_autoreply_settings(user.get("settings") if isinstance(user.get("settings"), dict) else {})
    if not settings.get("enabled"):
        return False

    post_id = str(comment_event.get("post_id") or "").strip()
    comment_id = str(comment_event.get("comment_id") or "").strip()
    if not post_id or not comment_id:
        return False
    if not _post_allowed(settings, post_id):
        return False

    reply_count = int(comment_event.get("reply_count") or 0)
    if settings.get("reply_only_unreplied", True) and reply_count > 0:
        await _mark_handled(db, user["_id"], comment_id, post_id=post_id, platform=str(comment_event.get("platform") or ""))
        return False

    if await _already_handled(db, user["_id"], comment_id):
        return False

    steps = await pick_comment_steps(db, settings, comment_event, user=user)
    if not steps:
        await _mark_handled(db, user["_id"], comment_id, post_id=post_id, platform=str(comment_event.get("platform") or ""))
        return False

    sent = False
    for step in steps:
        delay = int(step.get("delay_seconds") or 0)
        if delay > 0:
            await asyncio.sleep(max(0, min(delay, 120)))
        ok = await send_composio_comment_reply(
            db,
            user,
            post_id=post_id,
            account_id=str(comment_event.get("account_id") or ""),
            comment_id=comment_id,
            message=str(step.get("message") or ""),
            platform=str(comment_event.get("platform") or ""),
            step=step,
        )
        sent = sent or ok

    await _mark_handled(db, user["_id"], comment_id, post_id=post_id, platform=str(comment_event.get("platform") or ""))
    return sent


async def _poll_user_comments(db, user: dict) -> int:
    settings = read_comment_autoreply_settings(user.get("settings") if isinstance(user.get("settings"), dict) else {})
    if not settings.get("enabled"):
        return 0

    owner = await _owner_ids(db, user)
    replied = 0

    for platform in _POLL_PLATFORMS:
        try:
            posts_res = await list_commented_posts(
                db, user, platform=platform, min_comments=1, limit=MAX_POSTS_PER_USER
            )
        except Exception as exc:
            logger.warning("[CommentAutoReply] list posts failed user=%s plat=%s: %s", user.get("_id"), platform, exc)
            continue

        for post in (posts_res.get("posts") or [])[:MAX_POSTS_PER_USER]:
            post_id = str(post.get("id") or "").strip()
            account_id = str(post.get("accountId") or post.get("account_id") or "").strip()
            if not post_id or not account_id:
                continue
            if not _post_allowed(settings, post_id):
                continue

            try:
                comments_res = await get_post_comments(
                    db, user, post_id, account_id, platform=platform, limit=MAX_COMMENTS_PER_POST
                )
            except Exception as exc:
                logger.warning("[CommentAutoReply] get comments failed post=%s: %s", post_id, exc)
                continue

            post_caption = str(post.get("caption") or post.get("message") or post.get("content") or "")

            for comment in (comments_res.get("comments") or [])[:MAX_COMMENTS_PER_POST]:
                comment_id = str(comment.get("commentId") or comment.get("id") or "").strip()
                text = str(comment.get("message") or comment.get("text") or "").strip()
                if not comment_id or not text:
                    continue
                if not _comment_is_top_level(comment):
                    continue
                if _is_own_comment(comment, platform, owner):
                    continue

                reply_count = int(comment.get("replyCount") or comment.get("reply_count") or 0)
                author = str(
                    comment.get("username")
                    or comment.get("author")
                    or (comment.get("from") or {}).get("name")
                    or ""
                ).strip()

                created = _parse_ts(
                    str(comment.get("created_at") or comment.get("createdTime") or "")
                )
                is_live = bool(
                    created and (datetime.utcnow() - created) <= timedelta(minutes=NEW_COMMENT_WINDOW_MINUTES)
                )

                if await _already_handled(db, user["_id"], comment_id):
                    continue

                if settings.get("reply_only_unreplied", True) and reply_count > 0:
                    await _mark_handled(db, user["_id"], comment_id, post_id=post_id, platform=platform)
                    continue

                # First sight of an old comment: baseline only (no backlog blast on enable).
                if not is_live:
                    await _mark_handled(
                        db, user["_id"], comment_id,
                        post_id=post_id, platform=platform, baseline_only=True,
                    )
                    continue

                event = {
                    "post_id": post_id,
                    "comment_id": comment_id,
                    "comment_text": text,
                    "account_id": account_id,
                    "author_name": author,
                    "reply_count": reply_count,
                    "platform": platform,
                    "post_caption": post_caption,
                }
                if await handle_comment_event(db, user, event):
                    replied += 1
                    logger.info(
                        "[CommentAutoReply] replied user=%s platform=%s post=%s comment=%s",
                        user.get("_id"), platform, post_id, comment_id,
                    )

    return replied


async def run_comment_autoreply_poll(db) -> None:
    """Scheduler entry — poll Composio for new FB/IG comments and auto-reply."""
    try:
        users = await db.users.find({
            "$or": [
                {"settings.social_comment_autoreply.enabled": True},
                {"settings.zernio_comment_autoreply.enabled": True},
            ]
        }).to_list(MAX_USERS_PER_CYCLE)
    except Exception as exc:
        logger.error("[CommentAutoReply] user query failed: %s", exc)
        return

    if not users:
        return

    total = 0
    for user in users:
        settings = read_comment_autoreply_settings(user.get("settings") if isinstance(user.get("settings"), dict) else {})
        if not settings.get("enabled"):
            continue
        try:
            total += await _poll_user_comments(db, user)
        except Exception as exc:
            logger.error("[CommentAutoReply] user %s failed: %s", user.get("_id"), exc, exc_info=True)

    if total:
        logger.info("[CommentAutoReply] poll complete — %s repl(ies) sent", total)

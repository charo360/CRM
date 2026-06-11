"""Live social posts + engagement for the assistant (Composio-backed)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from composio_service import (
    TOOLKIT_FACEBOOK,
    TOOLKIT_INSTAGRAM,
    TOOLKIT_LINKEDIN,
    TOOLKIT_TWITTER,
    execute_action,
    get_connection_status,
    is_configured,
)
from social_composio_publish import get_social_settings
from social_accounts_service import list_connected_accounts
from social_composio_engagement import list_commented_posts, list_posts
from social_composio_publish import list_facebook_pages, resolve_instagram_user_id

logger = logging.getLogger(__name__)


def _extract_int(*values: Any) -> int:
    for v in values:
        if isinstance(v, dict):
            for key in ("count", "total_count", "totalCount", "value"):
                inner = v.get(key)
                if inner is not None:
                    try:
                        return max(0, int(inner))
                    except (TypeError, ValueError):
                        continue
            continue
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            continue
    return 0


def _post_text(row: Dict[str, Any]) -> str:
    for key in ("content", "caption", "message", "text", "title"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:300]
    return "(no caption)"


def _post_media_type(row: Dict[str, Any]) -> str:
    raw = (row.get("mediaType") or row.get("media_type") or row.get("type") or "").strip().lower()
    if raw in ("image", "photo"):
        return "image"
    if raw in ("video", "reel", "reels"):
        return "video"
    if raw in ("carousel", "carousel_album", "album"):
        return "carousel"
    if row.get("thumbnailUrl") or row.get("picture") or row.get("imageUrl"):
        return "image"
    return "text"


def _engagement_from_post(row: Dict[str, Any]) -> Dict[str, int]:
    analytics = row.get("analytics") if isinstance(row.get("analytics"), dict) else {}
    return {
        "likes": _extract_int(row.get("likes"), analytics.get("likes")),
        "comments": _extract_int(row.get("commentCount"), row.get("comments_count"), analytics.get("comments")),
        "shares": _extract_int(row.get("shares"), analytics.get("shares")),
        "reach": _extract_int(row.get("reach"), row.get("impressions"), analytics.get("reach"), analytics.get("impressions")),
        "clicks": _extract_int(row.get("clicks"), analytics.get("clicks")),
        "saves": _extract_int(row.get("saves"), analytics.get("saves")),
    }


def _build_result_post(row: Dict[str, Any], platform_filter: str) -> Dict[str, Any]:
    eng = _engagement_from_post(row)
    canonical = str(row.get("id") or "")
    created = row.get("createdTime") or row.get("created_at") or row.get("createdAt") or ""
    return {
        "id": canonical,
        "platform": str(row.get("platform") or platform_filter or "unknown").lower(),
        "text": _post_text(row),
        "permalink": row.get("permalink") or row.get("url") or "",
        "created_at": created,
        "media_type": _post_media_type(row),
        "engagement": eng,
        "engagement_score": (
            eng.get("likes", 0)
            + eng.get("comments", 0) * 2
            + eng.get("shares", 0) * 3
            + eng.get("clicks", 0)
        ),
    }


async def _follower_counts(db, user_id: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    fb = await get_connection_status(user_id, TOOLKIT_FACEBOOK)
    if fb.get("connected"):
        pages = await list_facebook_pages(user_id)
        total = 0
        for page in pages.get("pages") or []:
            pid = page.get("id")
            if not pid:
                continue
            res = await execute_action(
                user_id,
                "FACEBOOK_GET_PAGE_DETAILS",
                {"page_id": pid, "fields": "followers_count,fan_count,name"},
            )
            data = res.get("data") if isinstance(res.get("data"), dict) else {}
            total += _extract_int(data.get("followers_count"), data.get("fan_count"))
        if total:
            counts["facebook"] = total

    ig = await get_connection_status(user_id, TOOLKIT_INSTAGRAM)
    if ig.get("connected"):
        ig_uid = await resolve_instagram_user_id(db, user_id)
        if ig_uid:
            res = await execute_action(user_id, "INSTAGRAM_GET_USER_INFO", {})
            data = res.get("data") if isinstance(res.get("data"), dict) else {}
            fc = _extract_int(data.get("followers_count"), data.get("follower_count"))
            if fc:
                counts["instagram"] = fc

    tw = await get_connection_status(user_id, TOOLKIT_TWITTER)
    if tw.get("connected"):
        res = await execute_action(user_id, "TWITTER_USER_LOOKUP_ME", {})
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        fc = _extract_int((inner or {}).get("public_metrics", {}).get("followers_count"))
        if fc:
            counts["twitter"] = fc

    li = await get_connection_status(user_id, TOOLKIT_LINKEDIN)
    if li.get("connected"):
        settings = await get_social_settings(db, user_id)
        author_urn = str(settings.get("linkedin_author_urn") or "")
        if author_urn.startswith("urn:li:organization:"):
            org_id = author_urn.split(":")[-1]
            res = await execute_action(
                user_id,
                "LINKEDIN_GET_NETWORK_SIZE",
                {"organization_id": org_id, "edgeType": "COMPANY_FOLLOWED_BY_MEMBER"},
            )
            data = res.get("data") if isinstance(res.get("data"), dict) else {}
            fc = _extract_int(
                data.get("firstDegreeSize"),
                data.get("follower_count"),
                data.get("followers"),
                (data.get("elements") or [{}])[0].get("firstDegreeSize") if isinstance(data.get("elements"), list) else None,
            )
            if fc:
                counts["linkedin"] = fc

    return counts


async def fetch_live_social_posts(ctx, args: Dict[str, Any]) -> Dict[str, Any]:
    """Build the get_live_social_posts tool payload via Composio."""
    if not is_configured():
        return {"error": "Composio is not configured (COMPOSIO_API_KEY missing).", "posts": []}

    user = await ctx.db.users.find_one(
        {"_id": ctx.business_id},
        {"business_id": 1, "name": 1},
    )
    if not user:
        return {"error": "User not found.", "posts": []}

    platform_filter = (args.get("platform") or "").strip().lower()
    limit = max(1, min(int(args.get("limit") or 50), 100))
    user_id = str(user.get("business_id") or user["_id"])

    accounts = await list_connected_accounts(ctx.db, user)
    if not accounts:
        return {
            "error": "No social accounts connected. Connect platforms in Integrations first.",
            "posts": [],
        }

    posts_res, commented_res = await asyncio.gather(
        list_posts(ctx.db, user, platform=platform_filter or None, limit=100),
        list_commented_posts(
            ctx.db,
            user,
            platform=platform_filter or None,
            min_comments=1,
            limit=100,
        ),
    )

    raw_posts = (posts_res.get("posts") or []) + (commented_res.get("posts") or [])
    seen: set[str] = set()
    merged_rows: List[Dict[str, Any]] = []
    for row in raw_posts:
        pid = str(row.get("id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        merged_rows.append(row)

    result_posts = [_build_result_post(row, platform_filter) for row in merged_rows]
    result_posts.sort(key=lambda x: x["engagement_score"], reverse=True)

    totals = {"likes": 0, "comments": 0, "shares": 0, "reach": 0, "clicks": 0, "saves": 0}
    metric_coverage = {k: 0 for k in totals}
    for p in result_posts:
        for k in totals:
            v = p["engagement"].get(k, 0) or 0
            totals[k] += v
            if v > 0:
                metric_coverage[k] += 1

    total_posts = len(result_posts)
    coverage_pct = {
        k: round((metric_coverage[k] / total_posts) * 100, 1) if total_posts else 0.0
        for k in metric_coverage
    }
    low_coverage_metrics = [k for k, pct in coverage_pct.items() if pct < 30.0 and total_posts > 0]
    metric_notes: List[str] = []
    if "reach" in low_coverage_metrics:
        metric_notes.append(
            f"reach data only available for {metric_coverage['reach']}/{total_posts} posts "
            f"({coverage_pct['reach']}%) — organic Instagram/Facebook posts often omit reach via Graph API."
        )

    posts_per_platform: Dict[str, int] = {}
    for p in result_posts:
        plat = str(p.get("platform") or "").lower()
        if plat:
            posts_per_platform[plat] = posts_per_platform.get(plat, 0) + 1

    followers_by_platform = await _follower_counts(ctx.db, user_id)
    accounts_summary: List[Dict[str, Any]] = []
    for acc in accounts:
        plat = str(acc.get("platform") or "").lower()
        merged_count = posts_per_platform.get(plat, 0)
        sync_status = "synced" if merged_count > 0 else "no_posts_published"
        sync_message = None if merged_count > 0 else (
            f"{plat.title()} is connected but no recent posts were returned from the API."
        )
        accounts_summary.append({
            "account_id": acc.get("id"),
            "platform": plat,
            "username": acc.get("username"),
            "display_name": acc.get("name") or acc.get("displayName"),
            "followers": followers_by_platform.get(plat, 0),
            "merged_post_count": merged_count,
            "sync_status": sync_status,
            "sync_message": sync_message,
        })

    platform_diagnostics: Dict[str, Dict[str, Any]] = {}
    for acc in accounts_summary:
        plat = acc.get("platform")
        if not plat:
            continue
        entry = platform_diagnostics.setdefault(plat, {
            "accounts_connected": 0,
            "total_posts_in_response": 0,
            "sync_statuses": [],
            "messages": [],
        })
        entry["accounts_connected"] += 1
        entry["total_posts_in_response"] += acc.get("merged_post_count") or 0
        entry["sync_statuses"].append(acc.get("sync_status"))
        if acc.get("sync_message"):
            entry["messages"].append(acc["sync_message"])

    from assistant.tools import _compute_derived_insights, _record_and_read_follower_history

    follower_growth = await _record_and_read_follower_history(ctx, accounts_summary)
    derived_insights = _compute_derived_insights(result_posts, followers_by_platform)

    return {
        "source": "composio_live",
        "note": (
            "Live posts and engagement fetched directly from Composio (Facebook, Instagram, X). "
            "LinkedIn posting uses Composio; LinkedIn DMs use Unipile."
        ),
        "total_posts": total_posts,
        "totals": totals,
        "metric_coverage": metric_coverage,
        "metric_coverage_pct": coverage_pct,
        "low_coverage_metrics": low_coverage_metrics,
        "metric_notes": metric_notes,
        "accounts_summary": accounts_summary,
        "platform_diagnostics": platform_diagnostics,
        "sync_health": {"provider": "composio", "real_time": True},
        "total_followers_by_platform": followers_by_platform,
        "follower_growth_by_platform": follower_growth,
        "derived_insights": derived_insights,
        "posts": result_posts[:limit],
        "diagnostics": {
            "connected_accounts": len(accounts),
            "posts_from_composio": len(merged_rows),
            "posts_after_merge": total_posts,
            "provider": "composio",
        },
    }

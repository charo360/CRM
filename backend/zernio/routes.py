"""Social API routes (legacy /zernio/* paths) — Composio posting/inbox + Unipile LinkedIn DMs."""
from __future__ import annotations
import json
import logging, os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from collaboration.access import require_social_channel_level

logger = logging.getLogger(__name__)


ZERNIO_BASE = "https://zernio.com/api/v1"

DEPRECATED_MESSAGE_TAGS = {
    "CONFIRMED_EVENT_UPDATE",
    "ACCOUNT_UPDATE",
    "POST_PURCHASE_UPDATE",
}
# 

def _extract_error_message(body_text: str) -> str:
    try:
        payload = json.loads(body_text) if body_text else {}
    except Exception:
        payload = {}
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()
    return body_text.strip()


def _extract_profile_id(profile: Dict[str, Any]) -> Optional[str]:
    if not isinstance(profile, dict):
        return None
    pid = (
        profile.get("_id")
        or profile.get("id")
        or profile.get("profileId")
        or profile.get("profile_id")
    )
    return str(pid) if pid else None


def _normalize_account(acc: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(acc, dict):
        return {}
    out = dict(acc)
    raw_id = out.get("id") or out.get("_id") or out.get("accountId") or out.get("account_id")
    if raw_id:
        out["id"] = str(raw_id)
    platform = out.get("platform")
    if isinstance(platform, str):
        out["platform"] = platform.lower()
    return out

def _headers():
    key = os.getenv("ZERNIO_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "ZERNIO_API_KEY not configured")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
):
    hdrs = _headers()
    if extra_headers:
        hdrs.update(extra_headers)

    url = f"{ZERNIO_BASE}{path}"
    async with httpx.AsyncClient(timeout=20) as client:
        if method == "GET":
            r = await client.get(url, headers=hdrs, params=params or {})
        elif method == "POST":
            r = await client.post(url, headers=hdrs, json=body or {})
        elif method == "DELETE":
            r = await client.delete(url, headers=hdrs)
        else:
            raise HTTPException(500, f"Unsupported method: {method}")
        r.raise_for_status()
        return r.json()


async def _get(path: str, params: dict = None, extra_headers: Optional[Dict[str, str]] = None):
    return await _request("GET", path, params=params, extra_headers=extra_headers)


async def _post(path: str, body: dict, extra_headers: Optional[Dict[str, str]] = None):
    return await _request("POST", path, body=body, extra_headers=extra_headers)


async def _delete(path: str):
    return await _request("DELETE", path)


class SendMessageBody(BaseModel):
    conversation_id: str
    message: str
    account_id: Optional[str] = None
    messaging_type: Optional[str] = None
    message_tag: Optional[str] = None
    platform: Optional[str] = None

class CreateConversationBody(BaseModel):
    platform: str
    recipient: str
    message: str
    subject: Optional[str] = None
    linkedin_api: Optional[str] = None
    inmail: Optional[bool] = None

class ReplyCommentBody(BaseModel):
    account_id: str
    comment_id: str
    message: str

class CommentAutoReplyRule(BaseModel):
    keyword: str
    message: str

class CommentAutoReplyStep(BaseModel):
    type: str = "text"  # text | image | video | file
    message: Optional[str] = None
    media_url: Optional[str] = None
    delay_seconds: int = 0

class CommentAutoReplySettings(BaseModel):
    enabled: bool = False
    engine_mode: str = "hybrid"  # native_ai_all_posts | manychat_per_post | hybrid
    apply_all_posts: bool = True
    post_ids: List[str] = Field(default_factory=list)
    manychat_post_ids: List[str] = Field(default_factory=list)
    default_message: str = "Thanks for your comment. We have seen it and will follow up shortly."
    keyword_rules: List[CommentAutoReplyRule] = Field(default_factory=list)
    chain_steps: List[CommentAutoReplyStep] = Field(default_factory=list)
    reply_only_unreplied: bool = True


class FacebookHeadlessListBody(BaseModel):
    temp_token: str
    connect_token: str


class FacebookHeadlessCompleteBody(BaseModel):
    temp_token: str
    connect_token: str
    page_id: str
    user_profile: Dict[str, Any]
    redirect_url: Optional[str] = None


META_APP_ID     = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
GRAPH_BASE      = "https://graph.facebook.com/v19.0"

_COMPOSIO_PLATFORM_TOOLKITS = {
    "facebook": "facebook",
    "instagram": "instagram",
    "youtube": "youtube",
    "linkedin": "linkedin",
    "twitter": "twitter",
    "x": "twitter",
    "tiktok": "tiktok",
}


async def _capture_facebook_page_token(db, user_id: str, page_id: str, user_access_token: str) -> None:
    """Exchange the short-lived user token for a long-lived page token and persist it."""
    if not META_APP_ID or not META_APP_SECRET or not user_access_token:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Exchange short-lived → long-lived user token
            ll_resp = await client.get(
                f"{GRAPH_BASE}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": META_APP_ID,
                    "client_secret": META_APP_SECRET,
                    "fb_exchange_token": user_access_token,
                },
            )
            ll_data = ll_resp.json() if ll_resp.status_code == 200 else {}
            ll_token = ll_data.get("access_token") or user_access_token

            # Get page access token using the long-lived user token
            page_resp = await client.get(
                f"{GRAPH_BASE}/{page_id}",
                params={"fields": "access_token,instagram_business_account", "access_token": ll_token},
            )
            if page_resp.status_code != 200:
                logger.warning(f"[zernio] Could not fetch page token for {page_id}: {page_resp.text[:200]}")
                return
            page_data = page_resp.json()
            page_token = page_data.get("access_token")
            ig_id = (page_data.get("instagram_business_account") or {}).get("id", "")
            if not page_token:
                return

        from datetime import datetime
        now = datetime.utcnow()
        await db.meta_connections.update_one(
            {"user_id": user_id, "channel": "messenger"},
            {"$set": {
                "user_id": user_id,
                "page_id": page_id,
                "instagram_id": ig_id or page_id,
                "page_access_token": page_token,
                "channel": "messenger",
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        logger.info(f"[zernio] Captured page token for user {user_id} page {page_id}")
    except Exception as exc:
        logger.warning(f"[zernio] _capture_facebook_page_token failed: {exc}")


def make_composio_social_router(db, user_dep, *, prefix: str = "/composio/social"):
    """Social inbox, posts, comments — Composio + Unipile (legacy path: /zernio)."""
    router = APIRouter(prefix=prefix, tags=["composio-social"])

    async def _need(user, platform: Optional[str], level: str) -> None:
        await require_social_channel_level(db, user, platform, level)

    # ── helpers ────────────────────────────────────────────────────────────────

    async def _list_accounts_for_profile(profile_id: str) -> list[Dict[str, Any]]:
        if not profile_id:
            return []
        try:
            data = await _get("/accounts", {"profileId": profile_id})
            raw_accounts = data.get("accounts") or data.get("data") or []
            if isinstance(raw_accounts, list):
                return [_normalize_account(a) for a in raw_accounts if isinstance(a, dict)]
        except Exception as e:
            logger.warning(f"[zernio] Could not list accounts for profile {profile_id}: {e}")
        return []

    async def _get_or_create_profile(user_id: str) -> str:
        """Return the Zernio profileId for this user, creating one if needed.

        Each user gets their own isolated profile. We never share or reassign
        profiles between users — doing so leaks social accounts across tenants.
        """
        user_doc = await db.users.find_one({"_id": user_id}, {"zernio_profile_id": 1, "business_name": 1})
        profile_id = user_doc.get("zernio_profile_id") if user_doc else None

        # User already has a profile — use it as-is (even if currently empty).
        if profile_id:
            return str(profile_id)

        # Create a fresh, isolated profile for this user.
        name = (user_doc or {}).get("business_name") or f"User {user_id[:8]}"
        try:
            data = await _post("/profiles", {"name": name, "description": "CRM Social Profile"})
            profile = data.get("profile") or data
            profile_id = (
                profile.get("_id") or profile.get("id") or
                profile.get("profileId") or profile.get("profile_id")
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:400]
            logger.error(f"[zernio] Profile create failed HTTP {e.response.status_code}: {body}")
            status_code = e.response.status_code
            message = _extract_error_message(body)
            if status_code == 403 and "profile limit reached" in message.lower():
                message = (
                    "Zernio profile limit reached. "
                    "Please upgrade the Zernio plan to allow more profiles."
                )
            raise HTTPException(status_code, f"Zernio {status_code}: {message}")
        except Exception as e:
            logger.error(f"[zernio] Profile create error: {e}")
            raise HTTPException(503, f"Zernio connection error: {e}")

        if not profile_id:
            logger.error(f"[zernio] Profile created but no ID in response: {data}")
            raise HTTPException(503, "Zernio profile created but ID not found in response")

        await db.users.update_one(
            {"_id": user_id},
            {"$set": {"zernio_profile_id": profile_id}}
        )
        logger.info(f"[zernio] Created profile {profile_id} for user {user_id}")
        return profile_id

    # ── key ping (public debug — no auth required) ────────────────────────────

    @router.get("/ping")
    async def social_ping():
        """Health check — social stack uses Composio + Unipile."""
        from composio_service import is_configured as composio_ok
        from unipile_service import is_configured as unipile_ok
        return {
            "ok": True,
            "provider": "composio+unipile",
            "composio_configured": composio_ok(),
            "unipile_configured": unipile_ok(),
        }

    # ── status & profile ───────────────────────────────────────────────────────

    @router.get("/status")
    async def zernio_status(user=user_dep):
        """Return connected social accounts (Composio + Unipile)."""
        await _need(user, None, "read")
        try:
            from social_accounts_service import has_social_connection, list_connected_accounts

            accounts = await list_connected_accounts(db, user)
            connected = await has_social_connection(db, user)
            return {
                "connected": connected,
                "profile_id": str(user.get("business_id") or user["_id"]),
                "accounts": accounts,
            }
        except Exception as e:
            logger.error("[social] status error: %s", e)
            return {"connected": False, "error": str(e), "accounts": []}

    # ── connect (OAuth flow) ───────────────────────────────────────────────────

    @router.get("/connect/{platform}")
    async def get_connect_url(
        platform: str,
        redirect_url: Optional[str] = None,
        headless: bool = False,
        user=user_dep
    ):
        """Return Composio OAuth URL for supported posting platforms."""
        await _need(user, platform, "admin")
        del headless
        plat = (platform or "").strip().lower()
        toolkit = _COMPOSIO_PLATFORM_TOOLKITS.get(plat)
        if not toolkit:
            raise HTTPException(
                410,
                detail=f"Platform '{platform}' is not available. Connect supported channels in Integrations.",
            )
        try:
            from composio_service import get_connect_url as composio_connect_url

            frontend = os.getenv("FRONTEND_URL", "").rstrip("/")
            target_redirect = (redirect_url or "").strip()
            if not target_redirect and frontend:
                target_redirect = f"{frontend}/dashboard/integrations?connected={plat}"
            business_id = str(user.get("business_id") or user["_id"])
            result = await composio_connect_url(business_id, toolkit, target_redirect)
            if result.get("error"):
                raise HTTPException(502, detail=result["error"])
            auth_url = result.get("redirect_url") or result.get("authUrl") or result.get("url")
            return {"authUrl": auth_url, "platform": plat}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("[social] connect/%s error: %s", platform, e)
            raise HTTPException(502, detail=str(e))

    @router.post("/connect/facebook/headless/pages")
    async def list_facebook_headless_pages(payload: FacebookHeadlessListBody, user=user_dep):
        """Deprecated — connect Facebook via Composio OAuth on Integrations."""
        await _need(user, "facebook", "admin")
        raise HTTPException(
            410,
            detail="Headless Facebook connect via Zernio is removed. Connect Facebook in Integrations (Composio OAuth).",
        )

    @router.post("/connect/facebook/headless/complete")
    async def complete_facebook_headless_connect(payload: FacebookHeadlessCompleteBody, user=user_dep):
        """Deprecated — connect Facebook via Composio OAuth on Integrations."""
        await _need(user, "facebook", "admin")
        raise HTTPException(
            410,
            detail="Headless Facebook connect via Zernio is removed. Connect Facebook in Integrations (Composio OAuth).",
        )

    @router.delete("/accounts/{account_id}")
    async def disconnect_account(account_id: str, user=user_dep):
        """Disconnect a Composio or Unipile social account."""
        await _need(user, None, "admin")
        if not account_id or account_id in ("undefined", "null"):
            raise HTTPException(400, "Invalid account id")

        from composio_service import disconnect as composio_disconnect
        from unipile_service import clear_linkedin_account, is_unipile_account_id

        business_id = str(user.get("business_id") or user["_id"])
        aid = str(account_id)

        if is_unipile_account_id(aid):
            await clear_linkedin_account(db, user["_id"])
            return {"ok": True, "disconnected": aid, "provider": "unipile"}

        from social_accounts_service import list_connected_accounts
        accounts = await list_connected_accounts(db, user)
        match = next((a for a in accounts if str(a.get("id")) == aid), None)
        platform = str((match or {}).get("platform") or "").lower()
        toolkit = _COMPOSIO_PLATFORM_TOOLKITS.get(platform)
        if toolkit:
            result = await composio_disconnect(business_id, toolkit)
            if result.get("error"):
                raise HTTPException(502, result["error"])
            return {"ok": True, "disconnected": aid, "provider": "composio", "toolkit": toolkit}

        raise HTTPException(404, "Account not found or not disconnectable")

    # ── accounts ───────────────────────────────────────────────────────────────

    @router.get("/accounts")
    async def list_accounts(user=user_dep):
        """List connected social accounts (Composio + Unipile)."""
        await _need(user, None, "read")
        from social_accounts_service import list_connected_accounts

        accounts = await list_connected_accounts(db, user)
        return {"accounts": accounts}

    # ── inbox ──────────────────────────────────────────────────────────────────

    @router.get("/inbox")
    async def list_inbox(platform: Optional[str] = None, limit: int = 50, user=user_dep):
        """Unified inbox — Composio (FB/IG) + Unipile (LinkedIn)."""
        await _need(user, platform, "read")
        from social_inbox_service import list_conversations

        business_id = str(user.get("business_id") or user["_id"])
        try:
            convs = await list_conversations(
                db,
                user,
                platform=platform,
                limit=limit,
            )
            return {"conversations": convs, "data": convs, "messages": []}
        except Exception as exc:
            logger.error("[social-inbox] list failed for %s: %s", business_id, exc, exc_info=True)
            return {"conversations": [], "data": [], "messages": []}

    @router.get("/inbox/{conversation_id}")
    async def get_conversation(
        conversation_id: str,
        account_id: Optional[str] = None,
        platform: Optional[str] = None,
        user=user_dep
    ):
        """Get messages for a specific conversation."""
        await _need(user, platform, "read")

        from unipile_service import is_unipile_account_id
        plat = (platform or "").strip().lower()
        if is_unipile_account_id(account_id) or plat == "linkedin":
            import unipile_inbox
            if unipile_inbox.is_available():
                business_id = str(user.get("business_id") or user["_id"])
                try:
                    msgs = await unipile_inbox.get_conversation_messages(
                        db,
                        user["_id"],
                        business_id,
                        conversation_id,
                        account_id or "",
                    )
                    return {"messages": msgs, "data": msgs}
                except Exception as exc:
                    logger.error("[unipile-inbox] conversation failed: %s", exc, exc_info=True)
                    if plat == "linkedin" or is_unipile_account_id(account_id):
                        return {"messages": [], "data": []}

        import composio_inbox
        business_id = str(user.get("business_id") or user["_id"])
        conn_id = account_id or ""
        try:
            msgs = await composio_inbox.get_conversation_messages(
                business_id,
                conversation_id,
                conn_id,
            )
            return {"messages": msgs, "data": msgs}
        except Exception as exc:
            logger.error("[composio-inbox] conversation failed: %s", exc, exc_info=True)
            return {"messages": [], "data": []}

    @router.post("/inbox/send")
    async def send_message(payload: SendMessageBody, user=user_dep):
        """Reply to a conversation."""
        await _need(user, payload.platform, "reply")
        
        business_id = str(user.get("business_id") or user["_id"])
        if payload.account_id and str(payload.account_id).startswith("ca_"):
            import composio_inbox
            logger.info("[composio-inbox] Sending message via Composio for user %s", user["_id"])
            res = await composio_inbox.send_message(
                business_id,
                payload.conversation_id,
                payload.account_id,
                payload.message,
            )
            if res.get("success"):
                return {"status": "sent", "data": res.get("data")}
            raise HTTPException(400, detail=res.get("error") or "Failed to send message via Composio")

        from unipile_service import is_unipile_account_id
        plat = (payload.platform or "").strip().lower()
        if is_unipile_account_id(payload.account_id) or plat == "linkedin":
            import unipile_inbox
            if unipile_inbox.is_available():
                business_id = str(user.get("business_id") or user["_id"])
                logger.info("[unipile-inbox] Sending LinkedIn message for user %s", user["_id"])
                res = await unipile_inbox.send_message(
                    db,
                    user["_id"],
                    business_id,
                    payload.conversation_id,
                    payload.account_id or "",
                    payload.message,
                )
                if res.get("success"):
                    return {"status": "sent", "data": res.get("data")}
                raise HTTPException(400, detail=res.get("error") or "Failed to send message via Unipile")
            
        import composio_inbox
        business_id = str(user.get("business_id") or user["_id"])
        conn_id = payload.account_id or ""
        if not conn_id:
            try:
                convs = await composio_inbox.list_conversations(business_id, payload.platform)
                for conv in convs:
                    if str(conv.get("id") or "") == payload.conversation_id:
                        conn_id = str(conv.get("accountId") or conv.get("account_id") or "")
                        break
            except Exception:
                pass
        if not conn_id:
            raise HTTPException(400, "Missing account_id for inbox send")
        res = await composio_inbox.send_message(
            business_id,
            payload.conversation_id,
            conn_id,
            payload.message,
        )
        if res.get("success"):
            return {"status": "sent", "data": res.get("data")}
        raise HTTPException(400, detail=res.get("error") or "Failed to send message via Composio")

    @router.post("/inbox/new")
    async def new_conversation(payload: CreateConversationBody, user=user_dep):
        """Start a new LinkedIn conversation (InMail / Sales Navigator) via Unipile."""
        plat = (payload.platform or "").strip().lower()
        await _need(user, plat, "reply")
        if plat not in ("linkedin", "linkedin_messaging"):
            raise HTTPException(
                410,
                detail="Starting new conversations is only supported for LinkedIn via this API.",
            )
        import unipile_inbox
        if not unipile_inbox.is_available():
            raise HTTPException(503, "LinkedIn messaging (Unipile) is not configured on the server.")
        business_id = str(user.get("business_id") or user["_id"])
        inmail = payload.inmail if payload.inmail is not None else True
        res = await unipile_inbox.send_inmail(
            db,
            user["_id"],
            business_id,
            recipient_id=payload.recipient.strip(),
            message=payload.message.strip(),
            subject=(payload.subject or "").strip(),
            linkedin_api=payload.linkedin_api,
            inmail=inmail,
        )
        if res.get("error"):
            raise HTTPException(400, detail=res["error"])
        return {
            "status": "sent",
            "conversation_id": res.get("chat_id"),
            "chat_id": res.get("chat_id"),
            "message_id": res.get("message_id"),
        }

    # ── posts ──────────────────────────────────────────────────────────────────

    @router.get("/posts")
    async def list_posts(platform: Optional[str] = None, limit: int = 20, user=user_dep):
        """List live posts from connected accounts via Composio."""
        await _need(user, platform, "read")
        from social_composio_engagement import list_posts as composio_list_posts

        return await composio_list_posts(db, user, platform=platform, limit=limit)

    @router.post("/posts")
    async def create_post(body: Dict[str, Any], user=user_dep):
        """Use CRM Marketing → Social Posts to schedule and publish."""
        await _need(user, (body or {}).get("platform"), "reply")
        raise HTTPException(410, detail="Use CRM scheduled posts (Marketing → Social Posts) to publish.")

    @router.get("/analytics")
    async def get_post_analytics(
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        post_id: Optional[str] = None,
        metrics: Optional[str] = None,
        limit: int = 100,
        page: int = 1,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        user=user_dep,
    ):
        """Post engagement metrics via Composio."""
        await _need(user, platform, "read")
        del metrics, page, from_date, to_date
        from social_composio_engagement import get_analytics, get_single_post_analytics

        if post_id:
            return await get_single_post_analytics(
                db, user, post_id, platform=platform, account_id=account_id,
            )
        return await get_analytics(
            db, user, platform=platform, account_id=account_id, limit=limit,
        )

    @router.get("/analytics/{post_id}")
    async def get_single_post_analytics(
        post_id: str,
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        metrics: Optional[str] = None,
        user=user_dep,
    ):
        """Single-post analytics via Composio."""
        await _need(user, platform, "read")
        del profile_id, metrics
        from social_composio_engagement import get_single_post_analytics as composio_post_analytics

        return await composio_post_analytics(
            db, user, post_id, platform=platform, account_id=account_id,
        )

    # ── comments ───────────────────────────────────────────────────────────────

    @router.get("/comments")
    async def list_commented_posts(
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        min_comments: Optional[int] = None,
        limit: int = 50,
        user=user_dep,
    ):
        """Posts with comments via Composio."""
        await _need(user, platform, "read")
        from social_composio_engagement import list_commented_posts as composio_commented

        return await composio_commented(
            db,
            user,
            platform=platform,
            account_id=account_id,
            min_comments=min_comments,
            limit=limit,
        )

    @router.get("/comments/{post_id}")
    async def get_post_comments(
        post_id: str,
        account_id: str,
        platform: Optional[str] = None,
        limit: int = 100,
        user=user_dep,
    ):
        """Fetch comments on a post via Composio."""
        await _need(user, platform, "read")
        from social_composio_engagement import get_post_comments as composio_comments

        return await composio_comments(
            db, user, post_id, account_id, platform=platform, limit=limit,
        )

    @router.post("/comments/{post_id}/reply")
    async def reply_to_comment(post_id: str, payload: ReplyCommentBody, platform: Optional[str] = None, user=user_dep):
        """Reply to a comment via Composio."""
        await _need(user, platform, "reply")
        from social_composio_engagement import reply_to_comment as composio_reply

        result = await composio_reply(
            db,
            user,
            post_id,
            payload.account_id,
            payload.comment_id,
            payload.message,
            platform=platform,
        )
        if result.get("error"):
            raise HTTPException(400, detail=result["error"])
        return result

    @router.get("/comments/autoreply/settings")
    async def get_comment_autoreply_settings(user=user_dep):
        """Get Social Inbox comment auto-reply settings."""
        from social_comment_settings import read_comment_autoreply_settings

        user_doc = await db.users.find_one(
            {"_id": user["_id"]},
            {"settings.social_comment_autoreply": 1, "settings.zernio_comment_autoreply": 1},
        )
        saved = read_comment_autoreply_settings((user_doc or {}).get("settings"))
        chain_steps = []
        for step in (saved.get("chain_steps") or []):
            if not isinstance(step, dict):
                continue
            stype = str(step.get("type") or "text").strip().lower()
            if stype not in {"text", "image", "video", "file"}:
                stype = "text"
            message = str(step.get("message") or "").strip()
            media_url = str(step.get("media_url") or "").strip()
            delay_seconds = int(step.get("delay_seconds") or 0)
            chain_steps.append(
                {
                    "type": stype,
                    "message": message or None,
                    "media_url": media_url or None,
                    "delay_seconds": max(0, min(delay_seconds, 120)),
                }
            )
        settings = {
            "enabled": bool(saved.get("enabled", False)),
            "engine_mode": str(saved.get("engine_mode") or "hybrid"),
            "apply_all_posts": bool(saved.get("apply_all_posts", True)),
            "post_ids": [str(x) for x in (saved.get("post_ids") or []) if str(x).strip()],
            "manychat_post_ids": [str(x) for x in (saved.get("manychat_post_ids") or []) if str(x).strip()],
            "default_message": str(saved.get("default_message") or "").strip()
            or "Thanks for your comment. We have seen it and will follow up shortly.",
            "keyword_rules": [
                {
                    "keyword": str(r.get("keyword") or "").strip(),
                    "message": str(r.get("message") or "").strip(),
                }
                for r in (saved.get("keyword_rules") or [])
                if isinstance(r, dict) and str(r.get("keyword") or "").strip() and str(r.get("message") or "").strip()
            ],
            "chain_steps": chain_steps,
            "reply_only_unreplied": bool(saved.get("reply_only_unreplied", True)),
        }
        if settings["engine_mode"] not in ("native_ai_all_posts", "manychat_per_post", "hybrid"):
            settings["engine_mode"] = "hybrid"
        return settings

    @router.put("/comments/autoreply/settings")
    async def update_comment_autoreply_settings(payload: CommentAutoReplySettings, user=user_dep):
        """Update Social Inbox comment auto-reply settings."""
        cleaned_rules = []
        for rule in payload.keyword_rules:
            keyword = str(rule.keyword or "").strip()
            message = str(rule.message or "").strip()
            if not keyword or not message:
                continue
            cleaned_rules.append({"keyword": keyword, "message": message})
        cleaned_steps = []
        for step in payload.chain_steps:
            stype = str(step.type or "text").strip().lower()
            if stype not in {"text", "image", "video", "file"}:
                stype = "text"
            message = str(step.message or "").strip()
            media_url = str(step.media_url or "").strip()
            if stype != "text" and not media_url:
                continue
            if stype == "text" and not message:
                continue
            cleaned_steps.append(
                {
                    "type": stype,
                    "message": message or None,
                    "media_url": media_url or None,
                    "delay_seconds": max(0, min(int(step.delay_seconds or 0), 120)),
                }
            )
        mode = str(payload.engine_mode or "hybrid").strip().lower()
        if mode not in ("native_ai_all_posts", "manychat_per_post", "hybrid"):
            mode = "hybrid"
        settings = {
            "enabled": bool(payload.enabled),
            "engine_mode": mode,
            "apply_all_posts": bool(payload.apply_all_posts),
            "post_ids": [str(x).strip() for x in (payload.post_ids or []) if str(x).strip()],
            "manychat_post_ids": [str(x).strip() for x in (payload.manychat_post_ids or []) if str(x).strip()],
            "default_message": str(payload.default_message or "").strip()
            or "Thanks for your comment. We have seen it and will follow up shortly.",
            "keyword_rules": cleaned_rules[:25],
            "chain_steps": cleaned_steps[:12],
            "reply_only_unreplied": bool(payload.reply_only_unreplied),
        }
        from social_comment_settings import comment_autoreply_mongo_set

        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": comment_autoreply_mongo_set(settings)},
            upsert=False,
        )
        return settings

    return router


def make_zernio_router(db, user_dep):
    """Deprecated alias — same handlers at /zernio for backward compatibility."""
    return make_composio_social_router(db, user_dep, prefix="/zernio")

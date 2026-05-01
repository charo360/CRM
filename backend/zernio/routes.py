"""Zernio — unified social inbox: per-user profiles, OAuth connect, posts, DMs."""
from __future__ import annotations
import json
import logging, os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from collaboration.access import require_social_channel_level

logger = logging.getLogger(__name__)

ZERNIO_BASES = (
    "https://zernio.com/v1",
    "https://zernio.com/api/v1",
)

DEPRECATED_MESSAGE_TAGS = {
    "CONFIRMED_EVENT_UPDATE",
    "ACCOUNT_UPDATE",
    "POST_PURCHASE_UPDATE",
}


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

    last_error: Optional[httpx.HTTPStatusError] = None
    async with httpx.AsyncClient(timeout=20) as client:
        for base in ZERNIO_BASES:
            url = f"{base}{path}"
            try:
                if method == "GET":
                    r = await client.get(url, headers=hdrs, params=params or {})
                elif method == "POST":
                    r = await client.post(url, headers=hdrs, json=body or {})
                elif method == "DELETE":
                    r = await client.delete(url, headers=hdrs)
                else:
                    raise HTTPException(500, f"Unsupported method: {method}")
                # Detect HTML response (wrong base path returns the Zernio website)
                content_type = (r.headers.get("content-type") or "").lower()
                is_html = "text/html" in content_type or (r.text or "").lstrip().lower().startswith("<!doctype")
                if is_html:
                    logger.warning(f"[zernio] {method} {url} returned HTML (status {r.status_code}); trying next base")
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                raise

    if last_error is not None:
        raise last_error
    raise HTTPException(503, "Failed to reach Zernio API")


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


def make_zernio_router(db, user_dep):
    router = APIRouter(prefix="/zernio", tags=["zernio"])

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

    async def _pick_profile_with_accounts() -> Optional[str]:
        try:
            profiles_data = await _get("/profiles")
            profiles = profiles_data.get("profiles") or profiles_data.get("data") or []
            if not isinstance(profiles, list):
                return None
            for profile in profiles:
                pid = _extract_profile_id(profile if isinstance(profile, dict) else {})
                if not pid:
                    continue
                accounts = await _list_accounts_for_profile(pid)
                if accounts:
                    return pid
        except Exception as e:
            logger.warning(f"[zernio] Could not scan profiles for connected accounts: {e}")
        return None

    async def _get_or_create_profile(user_id: str) -> str:
        """Return the Zernio profileId for this user, creating one if needed."""
        user_doc = await db.users.find_one({"_id": user_id}, {"zernio_profile_id": 1, "business_name": 1})
        profile_id = user_doc.get("zernio_profile_id") if user_doc else None

        # If user already has a stored profile but it has no social accounts while another
        # profile under the same API key does, auto-heal to that active profile.
        if profile_id:
            current_accounts = await _list_accounts_for_profile(str(profile_id))
            if not current_accounts:
                fallback_profile_id = await _pick_profile_with_accounts()
                if fallback_profile_id and fallback_profile_id != profile_id:
                    await db.users.update_one(
                        {"_id": user_id},
                        {"$set": {"zernio_profile_id": fallback_profile_id}},
                    )
                    logger.info(
                        f"[zernio] Switched user {user_id} profile {profile_id} -> {fallback_profile_id} (found active accounts)"
                    )
                    return fallback_profile_id

        if not profile_id:
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
                    # Free plans can hit profile caps. Reuse an existing profile so the
                    # integration still works instead of hard-failing connect/status.
                    try:
                        existing_profiles_data = await _get("/profiles")
                        existing_profiles = (
                            existing_profiles_data.get("profiles")
                            or existing_profiles_data.get("data")
                            or []
                        )
                        reusable_profile_id = None
                        if isinstance(existing_profiles, list):
                            for profile in existing_profiles:
                                reusable_profile_id = _extract_profile_id(profile)
                                if reusable_profile_id:
                                    break
                        if reusable_profile_id:
                            await db.users.update_one(
                                {"_id": user_id},
                                {"$set": {"zernio_profile_id": reusable_profile_id}},
                            )
                            logger.info(
                                f"[zernio] Reused existing profile {reusable_profile_id} for user {user_id} after limit reached"
                            )
                            return reusable_profile_id
                    except Exception as reuse_error:
                        logger.error(f"[zernio] Could not reuse existing profile after limit reached: {reuse_error}")

                    message = (
                        "Zernio profile limit reached and no reusable profile was found. "
                        "Upgrade the Zernio plan or remove an existing profile, then try again."
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
    async def zernio_ping():
        """Test the API key — no auth needed, safe to call from anywhere."""
        key = os.getenv("ZERNIO_API_KEY", "").strip()
        if not key:
            return {"ok": False, "error": "ZERNIO_API_KEY env var is not set on this server"}
        try:
            body = await _get("/profiles")
            return {"ok": True, "status": 200, "body": body}
        except httpx.HTTPStatusError as e:
            try:
                resp_body = e.response.json()
            except Exception:
                resp_body = e.response.text
            return {"ok": False, "status": e.response.status_code, "body": resp_body}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── status & profile ───────────────────────────────────────────────────────

    @router.get("/status")
    async def zernio_status(user=user_dep):
        """Check API connectivity and return the user's profile + connected accounts."""
        await _need(user, None, "read")
        try:
            user_id = user["_id"]
            profile_id = await _get_or_create_profile(user_id)
            accounts_data = await _get("/accounts", {"profileId": profile_id})
            raw_accounts = accounts_data.get("accounts") or accounts_data.get("data") or []
            accounts = [_normalize_account(a) for a in raw_accounts if isinstance(a, dict)]
            return {
                "connected": True,
                "profile_id": profile_id,
                "accounts": accounts,
            }
        except HTTPException as e:
            return {"connected": False, "error": e.detail}
        except httpx.HTTPStatusError as e:
            logger.error(f"[zernio] status HTTP error {e.response.status_code}: {e.response.text[:200]}")
            return {"connected": False, "error": f"Zernio API error {e.response.status_code}"}
        except Exception as e:
            logger.error(f"[zernio] status error: {e}")
            return {"connected": False, "error": str(e)}

    # ── connect (OAuth flow) ───────────────────────────────────────────────────

    @router.get("/connect/{platform}")
    async def get_connect_url(
        platform: str,
        redirect_url: Optional[str] = None,
        headless: bool = False,
        user=user_dep
    ):
        """Return an OAuth URL so the user can connect a social platform."""
        await _need(user, platform, "admin")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            frontend = os.getenv("FRONTEND_URL", "").rstrip("/")
            params: Dict[str, Any] = {"profileId": profile_id}
            target_redirect = (redirect_url or "").strip()
            if not target_redirect and frontend:
                target_redirect = f"{frontend}/dashboard/integrations?connected={platform}"
            if target_redirect:
                # Zernio docs use redirect_url. Keep redirectUrl too for backward compatibility.
                params["redirect_url"] = target_redirect
                params["redirectUrl"] = target_redirect
            if headless:
                params["headless"] = "true"
            data = await _get(f"/connect/{platform}", params)
            auth_url = (
                data.get("authUrl") or data.get("url") or
                data.get("auth_url") or data.get("redirectUrl")
            )
            return {"authUrl": auth_url, "platform": platform}
        except HTTPException as e:
            raise HTTPException(e.status_code, detail=e.detail)
        except httpx.HTTPStatusError as e:
            body = e.response.text[:400]
            logger.error(f"[zernio] connect/{platform} HTTP {e.response.status_code}: {body}")
            raise HTTPException(502, detail=f"Zernio returned {e.response.status_code}: {body}")
        except Exception as e:
            logger.error(f"[zernio] connect/{platform} error: {e}")
            raise HTTPException(502, detail=str(e))

    @router.post("/connect/facebook/headless/pages")
    async def list_facebook_headless_pages(payload: FacebookHeadlessListBody, user=user_dep):
        """List Facebook pages for headless OAuth flow using connect token."""
        await _need(user, "facebook", "admin")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            data = await _get(
                "/connect/facebook/select-page",
                {"profileId": profile_id, "tempToken": payload.temp_token},
                extra_headers={"X-Connect-Token": payload.connect_token},
            )
            pages = data.get("pages") or data.get("data") or []
            return {"pages": pages}
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            body = e.response.text[:400]
            logger.error(f"[zernio] facebook headless pages HTTP {e.response.status_code}: {body}")
            raise HTTPException(e.response.status_code, detail=body)
        except Exception as e:
            logger.error(f"[zernio] facebook headless pages error: {e}")
            raise HTTPException(502, detail=str(e))

    @router.post("/connect/facebook/headless/complete")
    async def complete_facebook_headless_connect(payload: FacebookHeadlessCompleteBody, user=user_dep):
        """Complete Facebook headless OAuth selection and save selected page."""
        await _need(user, "facebook", "admin")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            frontend = os.getenv("FRONTEND_URL", "").rstrip("/")
            final_redirect = (
                (payload.redirect_url or "").strip()
                or (f"{frontend}/dashboard/integrations?connected=facebook" if frontend else None)
            )
            body: Dict[str, Any] = {
                "profileId": profile_id,
                "pageId": payload.page_id,
                "tempToken": payload.temp_token,
                "userProfile": payload.user_profile,
            }
            if final_redirect:
                body["redirect_url"] = final_redirect
            data = await _post(
                "/connect/facebook/select-page",
                body,
                extra_headers={"X-Connect-Token": payload.connect_token},
            )
            account = data.get("account") or {}
            return {
                "connected": True,
                "account": account,
                "redirect_url": data.get("redirect_url"),
            }
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            logger.error(f"[zernio] facebook headless complete HTTP {e.response.status_code}: {body}")
            raise HTTPException(e.response.status_code, detail=body)
        except Exception as e:
            logger.error(f"[zernio] facebook headless complete error: {e}")
            raise HTTPException(502, detail=str(e))

    @router.delete("/accounts/{account_id}")
    async def disconnect_account(account_id: str, user=user_dep):
        """Disconnect a social account."""
        await _need(user, None, "admin")
        if not account_id or account_id in ("undefined", "null"):
            raise HTTPException(400, "Invalid account id")
        try:
            data = await _delete(f"/accounts/{account_id}")
            return data
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    # ── accounts ───────────────────────────────────────────────────────────────

    @router.get("/accounts")
    async def list_accounts(user=user_dep):
        """List connected social accounts for this user's profile."""
        await _need(user, None, "read")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            data = await _get("/accounts", {"profileId": profile_id})
            raw_accounts = data.get("accounts") or data.get("data") or []
            accounts = [_normalize_account(a) for a in raw_accounts if isinstance(a, dict)]
            return {"accounts": accounts}
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    # ── inbox ──────────────────────────────────────────────────────────────────

    @router.get("/inbox")
    async def list_inbox(platform: Optional[str] = None, limit: int = 50, user=user_dep):
        """Get DM conversations for this user's profile."""
        await _need(user, platform, "read")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            params: Dict[str, Any] = {"profileId": profile_id, "limit": limit}
            if platform:
                params["platform"] = platform
            # Current Zernio inbox endpoint (docs): /v1/inbox/conversations
            data = await _get("/inbox/conversations", params)
            return data
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"conversations": [], "data": [], "messages": []}
            raise HTTPException(e.response.status_code, e.response.text)

    @router.get("/inbox/{conversation_id}")
    async def get_conversation(
        conversation_id: str,
        account_id: Optional[str] = None,
        platform: Optional[str] = None,
        user=user_dep
    ):
        """Get messages for a specific conversation."""
        await _need(user, platform, "read")
        try:
            # New API requires accountId for conversation-scoped reads.
            if account_id:
                data = await _get(
                    f"/inbox/conversations/{conversation_id}/messages",
                    {"accountId": account_id, "limit": 100, "sortOrder": "asc"},
                )
            else:
                # Backward compatibility fallback (older clients without account id).
                data = await _get(f"/inbox/conversations/{conversation_id}", {})
            return data
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"messages": [], "data": []}
            raise HTTPException(e.response.status_code, e.response.text)

    @router.post("/inbox/send")
    async def send_message(payload: SendMessageBody, user=user_dep):
        """Reply to a conversation."""
        await _need(user, payload.platform, "reply")
        try:
            def _with_meta_fields(base: Dict[str, Any]) -> Dict[str, Any]:
                out = dict(base)
                if payload.messaging_type:
                    out["messagingType"] = payload.messaging_type
                if payload.message_tag:
                    # Meta deprecated these tags on 2026-04-27; force safe fallback.
                    if payload.message_tag in DEPRECATED_MESSAGE_TAGS:
                        logger.warning(
                            f"[zernio] deprecated message_tag={payload.message_tag} remapped to HUMAN_AGENT"
                        )
                        out["messageTag"] = "HUMAN_AGENT"
                    else:
                        out["messageTag"] = payload.message_tag
                return out

            async def _send_with_fallbacks(conversation_id: str, account_id: str):
                attempts = [
                    _with_meta_fields({"accountId": account_id, "message": payload.message}),
                    _with_meta_fields({"accountId": account_id, "text": payload.message}),
                    _with_meta_fields({"accountId": account_id, "message": {"text": payload.message}}),
                ]
                last_exc: Optional[httpx.HTTPStatusError] = None
                for body in attempts:
                    try:
                        return await _post(
                            f"/inbox/conversations/{conversation_id}/messages",
                            body,
                        )
                    except httpx.HTTPStatusError as e:
                        last_exc = e
                        if e.response.status_code != 400:
                            raise
                if last_exc:
                    raise last_exc
                raise HTTPException(500, "Failed to send inbox message")

            if payload.account_id:
                return await _send_with_fallbacks(payload.conversation_id, payload.account_id)

            # Backward-compat fallback for older payloads without account id.
            profile_id = await _get_or_create_profile(user["_id"])
            conversations = await _get("/inbox/conversations", {"profileId": profile_id, "limit": 100})
            rows = conversations.get("data") if isinstance(conversations, dict) else []
            if not isinstance(rows, list):
                rows = []
            match = next(
                (
                    r for r in rows
                    if isinstance(r, dict) and str(r.get("id") or "") == payload.conversation_id
                ),
                None,
            )
            account_id = str((match or {}).get("accountId") or "")
            if account_id:
                return await _send_with_fallbacks(payload.conversation_id, account_id)
            raise HTTPException(400, "Missing account_id for inbox send")
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            logger.warning(
                f"[zernio] inbox send HTTP {e.response.status_code} for conv={payload.conversation_id}: {body}"
            )
            msg = _extract_error_message(body)
            raise HTTPException(e.response.status_code, f"Zernio {e.response.status_code}: {msg}")

    @router.post("/inbox/new")
    async def new_conversation(payload: CreateConversationBody, user=user_dep):
        """Start a new DM conversation."""
        await _need(user, payload.platform, "reply")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            return await _post("/messages/create-inbox-conversation", {
                "platform": payload.platform,
                "recipient": payload.recipient,
                "message": payload.message,
                "profileId": profile_id,
            })
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    # ── posts ──────────────────────────────────────────────────────────────────

    @router.get("/posts")
    async def list_posts(platform: Optional[str] = None, limit: int = 20, user=user_dep):
        """List scheduled/published posts for this user's profile."""
        await _need(user, platform, "read")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            params: Dict[str, Any] = {"profileId": profile_id, "limit": limit}
            if platform:
                params["platform"] = platform
            return await _get("/posts", params)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    @router.post("/posts")
    async def create_post(body: Dict[str, Any], user=user_dep):
        """Schedule or publish a post."""
        await _need(user, (body or {}).get("platform"), "reply")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            body["profileId"] = profile_id
            return await _post("/posts", body)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

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
        """Fetch post analytics (likes/comments/shares/etc.) for the user's profile."""
        await _need(user, platform, "read")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            params: Dict[str, Any] = {
                "profileId": profile_id,
                "limit": max(1, min(limit, 100)),
                "page": max(1, int(page)),
            }
            if platform:
                params["platform"] = platform
            if account_id:
                params["accountId"] = account_id
            if post_id:
                params["postId"] = post_id
            if metrics:
                params["metrics"] = metrics
            if from_date:
                params["fromDate"] = from_date
            if to_date:
                params["toDate"] = to_date
            return await _get("/analytics", params)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    @router.get("/analytics/{post_id}")
    async def get_single_post_analytics(
        post_id: str,
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        metrics: Optional[str] = None,
        user=user_dep,
    ):
        """Fetch analytics for one post via bulk analytics query params."""
        await _need(user, platform, "read")
        try:
            resolved_profile_id = profile_id or await _get_or_create_profile(user["_id"])
            params: Dict[str, Any] = {"postId": post_id}
            if platform:
                params["platform"] = platform
            if account_id:
                params["accountId"] = account_id
            if resolved_profile_id:
                params["profileId"] = resolved_profile_id
            if metrics:
                params["metrics"] = metrics
            return await _get("/analytics", params)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    # ── comments ───────────────────────────────────────────────────────────────

    @router.get("/comments")
    async def list_commented_posts(
        platform: Optional[str] = None,
        account_id: Optional[str] = None,
        min_comments: Optional[int] = None,
        limit: int = 50,
        user=user_dep,
    ):
        """List posts that have comments (aggregated across connected accounts)."""
        await _need(user, platform, "read")
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            params: Dict[str, Any] = {"profileId": profile_id, "limit": max(1, min(limit, 100))}
            if platform:
                params["platform"] = platform
            if account_id:
                params["accountId"] = account_id
            if min_comments is not None:
                params["minComments"] = max(0, int(min_comments))
            return await _get("/inbox/comments", params)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    @router.get("/comments/{post_id}")
    async def get_post_comments(
        post_id: str,
        account_id: str,
        platform: Optional[str] = None,
        limit: int = 100,
        user=user_dep,
    ):
        """Fetch comments for a specific post. account_id is required by Zernio."""
        await _need(user, platform, "read")
        try:
            params: Dict[str, Any] = {"accountId": account_id, "limit": max(1, min(limit, 100))}
            return await _get(f"/inbox/comments/{post_id}", params)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    @router.post("/comments/{post_id}/reply")
    async def reply_to_comment(post_id: str, payload: ReplyCommentBody, platform: Optional[str] = None, user=user_dep):
        """Reply to a specific comment on a post."""
        await _need(user, platform, "reply")
        try:
            return await _post(
                f"/inbox/comments/{post_id}",
                {
                    "accountId": payload.account_id,
                    "commentId": payload.comment_id,
                    "message": payload.message,
                },
            )
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    @router.get("/comments/autoreply/settings")
    async def get_comment_autoreply_settings(user=user_dep):
        """Get Social Inbox comment auto-reply settings."""
        user_doc = await db.users.find_one({"_id": user["_id"]}, {"settings.zernio_comment_autoreply": 1})
        saved = ((user_doc or {}).get("settings") or {}).get("zernio_comment_autoreply") or {}
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
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"settings.zernio_comment_autoreply": settings}},
            upsert=False,
        )
        return settings

    return router

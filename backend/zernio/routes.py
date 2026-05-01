"""Zernio — unified social inbox: per-user profiles, OAuth connect, posts, DMs."""
from __future__ import annotations
import json
import logging, os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ZERNIO_BASE = "https://zernio.com/api/v1"


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

def _headers():
    key = os.getenv("ZERNIO_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "ZERNIO_API_KEY not configured")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

async def _get(path: str, params: dict = None):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{ZERNIO_BASE}{path}", headers=_headers(), params=params or {})
        r.raise_for_status()
        return r.json()

async def _post(path: str, body: dict):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{ZERNIO_BASE}{path}", headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()

async def _delete(path: str):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.delete(f"{ZERNIO_BASE}{path}", headers=_headers())
        r.raise_for_status()
        return r.json()


class SendMessageBody(BaseModel):
    conversation_id: str
    message: str
    platform: Optional[str] = None

class CreateConversationBody(BaseModel):
    platform: str
    recipient: str
    message: str


def make_zernio_router(db, user_dep):
    router = APIRouter(prefix="/zernio", tags=["zernio"])

    # ── helpers ────────────────────────────────────────────────────────────────

    async def _get_or_create_profile(user_id: str) -> str:
        """Return the Zernio profileId for this user, creating one if needed."""
        user_doc = await db.users.find_one({"_id": user_id}, {"zernio_profile_id": 1, "business_name": 1})
        profile_id = user_doc.get("zernio_profile_id") if user_doc else None

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
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{ZERNIO_BASE}/profiles",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                )
            return {"ok": r.status_code < 300, "status": r.status_code, "body": r.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── status & profile ───────────────────────────────────────────────────────

    @router.get("/status")
    async def zernio_status(user=user_dep):
        """Check API connectivity and return the user's profile + connected accounts."""
        try:
            user_id = user["_id"]
            profile_id = await _get_or_create_profile(user_id)
            accounts_data = await _get("/accounts", {"profileId": profile_id})
            accounts = accounts_data.get("accounts") or accounts_data.get("data") or []
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
    async def get_connect_url(platform: str, user=user_dep):
        """Return an OAuth URL so the user can connect a social platform."""
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            frontend = os.getenv("FRONTEND_URL", "").rstrip("/")
            params: Dict[str, Any] = {"profileId": profile_id}
            if frontend:
                params["redirectUrl"] = f"{frontend}/dashboard/integrations"
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

    @router.delete("/accounts/{account_id}")
    async def disconnect_account(account_id: str, user=user_dep):
        """Disconnect a social account."""
        try:
            data = await _delete(f"/accounts/{account_id}")
            return data
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    # ── accounts ───────────────────────────────────────────────────────────────

    @router.get("/accounts")
    async def list_accounts(user=user_dep):
        """List connected social accounts for this user's profile."""
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            data = await _get("/accounts", {"profileId": profile_id})
            return data
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    # ── inbox ──────────────────────────────────────────────────────────────────

    @router.get("/inbox")
    async def list_inbox(platform: Optional[str] = None, limit: int = 50, user=user_dep):
        """Get DM conversations for this user's profile."""
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            params: Dict[str, Any] = {"profileId": profile_id, "limit": limit}
            if platform:
                params["platform"] = platform
            data = await _get("/conversations", params)
            return data
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"conversations": [], "data": []}
            raise HTTPException(e.response.status_code, e.response.text)

    @router.get("/inbox/{conversation_id}")
    async def get_conversation(conversation_id: str, user=user_dep):
        """Get messages for a specific conversation."""
        try:
            data = await _get(f"/conversations/{conversation_id}")
            return data
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    @router.post("/inbox/send")
    async def send_message(payload: SendMessageBody, user=user_dep):
        """Reply to a conversation."""
        try:
            body: Dict[str, Any] = {
                "conversation_id": payload.conversation_id,
                "message": payload.message,
            }
            if payload.platform:
                body["platform"] = payload.platform
            return await _post("/messages/send-inbox-message", body)
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    @router.post("/inbox/new")
    async def new_conversation(payload: CreateConversationBody, user=user_dep):
        """Start a new DM conversation."""
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
        try:
            profile_id = await _get_or_create_profile(user["_id"])
            body["profileId"] = profile_id
            return await _post("/posts", body)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, e.response.text)

    return router

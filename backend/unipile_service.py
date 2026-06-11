"""Unipile API client — LinkedIn messaging (hosted auth + inbox)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

UNIPILE_API_KEY = os.environ.get("UNIPILE_API_KEY", "").strip()
UNIPILE_DSN = os.environ.get("UNIPILE_DSN", "").strip()

# Public prefix for account IDs exposed to the CRM inbox UI (distinct from Composio ca_).
UNIPILE_ACCOUNT_PREFIX = "up_"


def is_configured() -> bool:
    return bool(UNIPILE_API_KEY and UNIPILE_DSN)


def _normalize_dsn(dsn: str) -> str:
    raw = (dsn or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return f"https://{raw}"


def api_base() -> str:
    return _normalize_dsn(UNIPILE_DSN)


def _headers() -> Dict[str, str]:
    return {
        "X-API-KEY": UNIPILE_API_KEY,
        "accept": "application/json",
        "Content-Type": "application/json",
    }


def public_account_id(account_id: str) -> str:
    aid = (account_id or "").strip()
    if not aid:
        return ""
    if aid.startswith(UNIPILE_ACCOUNT_PREFIX):
        return aid
    return f"{UNIPILE_ACCOUNT_PREFIX}{aid}"


def strip_public_account_id(account_id: str) -> str:
    aid = (account_id or "").strip()
    if aid.startswith(UNIPILE_ACCOUNT_PREFIX):
        return aid[len(UNIPILE_ACCOUNT_PREFIX):]
    return aid


def is_unipile_account_id(account_id: Optional[str]) -> bool:
    return bool(account_id and str(account_id).startswith(UNIPILE_ACCOUNT_PREFIX))


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    files: Optional[Any] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    if not is_configured():
        return {"error": "UNIPILE_API_KEY or UNIPILE_DSN not configured on the server."}

    base = api_base()
    url = f"{base}{path}" if path.startswith("/") else f"{base}/{path}"
    headers = dict(_headers())
    request_kwargs: Dict[str, Any] = {"params": params}
    if files is not None:
        # multipart/form-data — let httpx set the Content-Type + boundary.
        headers.pop("Content-Type", None)
        request_kwargs["files"] = files
    elif json is not None:
        request_kwargs["json"] = json
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method.upper(),
                url,
                headers=headers,
                **request_kwargs,
            )
    except Exception as exc:
        logger.error("[unipile] request failed %s %s: %s", method, path, exc)
        return {"error": str(exc)}

    if resp.status_code >= 400:
        try:
            body = resp.json()
            msg = body.get("message") or body.get("error") or body.get("detail") or str(body)
        except Exception:
            msg = resp.text[:300] or f"HTTP {resp.status_code}"
        return {"error": f"Unipile HTTP {resp.status_code}: {msg}"}

    try:
        return {"data": resp.json()}
    except Exception:
        return {"data": {"raw": resp.text[:2000]}}


async def list_remote_accounts() -> List[Dict[str, Any]]:
    result = await _request("GET", "/api/v1/accounts")
    if result.get("error"):
        return []
    data = result.get("data") or {}
    items = data.get("items") or data.get("data") or data.get("accounts") or []
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    return [a for a in items if isinstance(a, dict)]


async def get_stored_linkedin_account(db, user_oid: Any) -> Optional[Dict[str, Any]]:
    user = await db.users.find_one({"_id": user_oid}, {"unipile_connections": 1})
    conn = (user or {}).get("unipile_connections") or {}
    li = conn.get("linkedin")
    if isinstance(li, dict) and li.get("account_id"):
        return li
    return None


async def save_linkedin_account(
    db,
    user_oid: Any,
    *,
    account_id: str,
    account_name: str = "",
    contract_id: Optional[str] = None,
    contract_name: Optional[str] = None,
    contract_product: Optional[str] = None,
) -> None:
    existing = await get_stored_linkedin_account(db, user_oid) or {}
    patch: Dict[str, Any] = {
        "account_id": account_id,
        "name": account_name or existing.get("name") or "LinkedIn",
        "connected_at": datetime.utcnow().isoformat(),
        "contract_id": contract_id or existing.get("contract_id"),
        "contract_name": contract_name or existing.get("contract_name"),
        "contract_product": contract_product or existing.get("contract_product"),
    }
    await db.users.update_one(
        {"_id": user_oid},
        {"$set": {"unipile_connections.linkedin": patch}},
    )


async def save_linkedin_contract(
    db,
    user_oid: Any,
    *,
    contract_id: str,
    contract_name: str = "",
    contract_product: str = "",
) -> None:
    await db.users.update_one(
        {"_id": user_oid},
        {
            "$set": {
                "unipile_connections.linkedin.contract_id": contract_id,
                "unipile_connections.linkedin.contract_name": contract_name,
                "unipile_connections.linkedin.contract_product": contract_product,
                "unipile_connections.linkedin.contract_selected_at": datetime.utcnow().isoformat(),
            }
        },
    )


async def delete_remote_account(account_id: str) -> Dict[str, Any]:
    aid = strip_public_account_id(account_id)
    if not aid:
        return {"error": "account_id is required"}
    return await _request("DELETE", f"/api/v1/accounts/{aid}")


async def clear_linkedin_account(db, user_oid: Any, *, delete_remote: bool = True) -> None:
    stored = await get_stored_linkedin_account(db, user_oid)
    if delete_remote and stored and stored.get("account_id"):
        try:
            await delete_remote_account(str(stored["account_id"]))
        except Exception as exc:
            logger.warning("[unipile] remote account delete failed: %s", exc)
    await db.users.update_one(
        {"_id": user_oid},
        {"$unset": {"unipile_connections.linkedin": ""}},
    )


async def resolve_linkedin_account_id(db, user_oid: Any, business_id: str) -> Optional[str]:
    stored = await get_stored_linkedin_account(db, user_oid)
    if stored and stored.get("account_id"):
        return str(stored["account_id"])

    # Fallback: match hosted-auth `name` field to business_id in remote account list.
    for acc in await list_remote_accounts():
        provider = str(acc.get("provider") or acc.get("type") or "").upper()
        if provider and provider != "LINKEDIN":
            continue
        name = str(acc.get("name") or "")
        if name and name != str(business_id):
            continue
        aid = acc.get("id") or acc.get("account_id")
        if aid:
            await save_linkedin_account(
                db,
                user_oid,
                account_id=str(aid),
                account_name=str(acc.get("username") or acc.get("name") or "LinkedIn"),
            )
            return str(aid)
    return None


async def list_linkedin_company_pages(db, user_oid: Any, business_id: str) -> List[Dict[str, Any]]:
    """Company/organization pages the connected member can post as (via Unipile).

    LinkedIn exposes these on the account detail under
    connection_params.im.organizations[]; each has an organization_urn like
    urn:li:fsd_company:108855548. The numeric tail is what Unipile's create-post
    `as_organization` parameter expects.
    """
    account_id = await resolve_linkedin_account_id(db, user_oid, business_id)
    if not account_id:
        return []
    result = await _request("GET", f"/api/v1/accounts/{strip_public_account_id(account_id)}")
    if result.get("error"):
        logger.warning("[unipile] company pages fetch failed: %s", result["error"])
        return []
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    conn = data.get("connection_params") if isinstance(data, dict) else None
    im = conn.get("im") if isinstance(conn, dict) else None
    orgs = im.get("organizations") if isinstance(im, dict) else None
    pages: List[Dict[str, Any]] = []
    if isinstance(orgs, list):
        for org in orgs:
            if not isinstance(org, dict):
                continue
            urn = str(org.get("organization_urn") or "").strip()
            name = str(org.get("name") or "").strip()
            if not urn or not name:
                continue
            pages.append({
                "urn": urn,
                "org_id": urn.split(":")[-1],
                "name": name,
                "type": "organization",
                "provider": "unipile",
            })
    return pages


def _parse_linkedin_connect_response(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"error": "Unexpected Unipile response."}

    if data.get("object") == "Checkpoint":
        checkpoint = data.get("checkpoint") if isinstance(data.get("checkpoint"), dict) else {}
        ctype = str(checkpoint.get("type") or "VERIFICATION")
        hints = {
            "2FA": "Enter the 6-digit code from your authenticator app.",
            "OTP": "Enter the verification code LinkedIn sent you.",
            "IN_APP_VALIDATION": "Approve the login in your LinkedIn mobile app, then click Verify.",
            "PHONE_REGISTER": "Enter your phone number with country code, e.g. (+1)5551234567.",
            "CAPTCHA": "Complete the captcha challenge (contact support if this persists).",
        }
        return {
            "checkpoint": True,
            "account_id": str(data.get("account_id") or ""),
            "checkpoint_type": ctype,
            "message": hints.get(ctype, f"LinkedIn requires {ctype} verification."),
        }

    account_id = data.get("id") or data.get("account_id")
    if account_id:
        return {
            "success": True,
            "account_id": str(account_id),
            "name": data.get("name") or data.get("username") or "LinkedIn",
        }

    if data.get("object") == "Account":
        account_id = data.get("id")
        if account_id:
            return {
                "success": True,
                "account_id": str(account_id),
                "name": data.get("name") or "LinkedIn",
            }

    return {"error": "Unexpected Unipile connect response."}


async def connect_linkedin_with_credentials(
    user_id: str,
    username: str,
    password: str,
    *,
    country: Optional[str] = None,
) -> Dict[str, Any]:
    """LinkedIn native auth — email + password (not OAuth)."""
    user = (username or "").strip()
    pwd = password or ""
    if not user or not pwd:
        return {"error": "LinkedIn email and password are required."}

    body: Dict[str, Any] = {
        "provider": "LINKEDIN",
        "username": user,
        "password": pwd,
        "name": user_id,
    }
    if country:
        body["country"] = country.strip().upper()

    result = await _request("POST", "/api/v1/accounts", json=body, timeout=45.0)
    if result.get("error"):
        return result
    return _parse_linkedin_connect_response(result.get("data"))


async def connect_linkedin_with_cookie(
    user_id: str,
    access_token: str,
    *,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """LinkedIn via li_at browser cookie — works when user signs in with Google on linkedin.com."""
    token = (access_token or "").strip()
    if not token:
        return {"error": "LinkedIn session cookie (li_at) is required."}

    body: Dict[str, Any] = {
        "provider": "LINKEDIN",
        "access_token": token,
        "name": user_id,
    }
    ua = (user_agent or "").strip()
    if ua:
        body["user_agent"] = ua

    result = await _request("POST", "/api/v1/accounts", json=body, timeout=45.0)
    if result.get("error"):
        return result
    return _parse_linkedin_connect_response(result.get("data"))


_OK_ACCOUNT_STATUSES = {"OK", "CONNECTED", "CREATION_SUCCESS", "RECONNECTED"}


async def get_remote_account(account_id: str) -> Dict[str, Any]:
    aid = strip_public_account_id(account_id)
    if not aid:
        return {"error": "account_id is required."}
    return await _request("GET", f"/api/v1/accounts/{aid}")


async def poll_linkedin_account(account_id: str) -> Dict[str, Any]:
    """Poll Unipile until LinkedIn in-app approval completes."""
    result = await get_remote_account(account_id)
    if result.get("error"):
        return result
    data = result.get("data") or {}
    status = str(data.get("status") or data.get("state") or "").upper()
    aid = str(data.get("id") or strip_public_account_id(account_id))
    if status in _OK_ACCOUNT_STATUSES:
        return {
            "success": True,
            "account_id": aid,
            "name": data.get("name") or data.get("username") or "LinkedIn",
            "status": status,
        }
    return {"pending": True, "status": status or "PENDING"}


async def solve_linkedin_checkpoint(account_id: str, code: str) -> Dict[str, Any]:
    aid = strip_public_account_id((account_id or "").strip())
    token = (code or "").strip()
    if not aid:
        return {"error": "account_id is required."}
    if not token:
        return {"error": "Verification code is required."}

    result = await _request(
        "POST",
        "/api/v1/accounts/checkpoint",
        json={"provider": "LINKEDIN", "account_id": aid, "code": token},
        timeout=45.0,
    )
    if result.get("error"):
        return result
    return _parse_linkedin_connect_response(result.get("data"))


async def create_hosted_auth_link(
    user_id: str,
    *,
    notify_url: str,
    success_redirect_url: str,
) -> Dict[str, Any]:
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body: Dict[str, Any] = {
        "type": "create",
        "providers": ["LINKEDIN"],
        "api_url": api_base(),
        "expiresOn": expires,
        "name": user_id,
        "notify_url": notify_url,
        "success_redirect_url": success_redirect_url,
    }
    result = await _request("POST", "/api/v1/hosted/accounts/link", json=body)
    if result.get("error"):
        return result
    data = result.get("data") or {}
    url = data.get("url") or data.get("authUrl") or data.get("auth_url")
    if not url:
        return {"error": "Unipile did not return a hosted auth URL."}
    return {"url": url, "authUrl": url}


async def list_linkedin_contracts(account_id: str) -> Dict[str, Any]:
    aid = strip_public_account_id(account_id)
    if not aid:
        return {"error": "account_id is required"}
    result = await _request(
        "GET",
        "/api/v1/linkedin/contracts",
        params={"account_id": aid},
    )
    if result.get("error"):
        return result
    data = result.get("data") or {}
    items = data.get("items") or []
    contracts = [c for c in items if isinstance(c, dict)]
    return {"contracts": contracts}


async def select_linkedin_contract(account_id: str, contract_id: str) -> Dict[str, Any]:
    aid = strip_public_account_id(account_id)
    cid = (contract_id or "").strip()
    if not aid:
        return {"error": "account_id is required"}
    if not cid:
        return {"error": "contract_id is required"}
    result = await _request(
        "POST",
        f"/api/v1/linkedin/contracts/{cid}/select",
        params={"account_id": aid},
    )
    if result.get("error"):
        return result
    return {"success": True, "data": result.get("data")}


async def get_inmail_balance(account_id: str) -> Dict[str, Any]:
    aid = strip_public_account_id(account_id)
    if not aid:
        return {"error": "account_id is required"}
    result = await _request(
        "GET",
        "/api/v1/linkedin/inmail_balance",
        params={"account_id": aid},
    )
    if result.get("error"):
        return result
    data = result.get("data") or {}
    return {
        "premium": data.get("premium"),
        "recruiter": data.get("recruiter"),
        "sales_navigator": data.get("sales_navigator"),
    }


def _linkedin_api_for_attendee(attendee_id: str, linkedin_api: Optional[str] = None) -> str:
    api = (linkedin_api or "").strip().lower()
    if api in ("classic", "sales_navigator", "recruiter"):
        return api
    aid = (attendee_id or "").strip()
    if aid.startswith("ACw"):
        return "sales_navigator"
    if aid.startswith("AE"):
        return "recruiter"
    return "classic"


async def start_linkedin_chat(
    account_id: str,
    *,
    attendee_ids: List[str],
    text: str,
    subject: Optional[str] = None,
    linkedin_api: Optional[str] = None,
    inmail: bool = False,
) -> Dict[str, Any]:
    aid = strip_public_account_id(account_id)
    attendees = [str(a).strip() for a in (attendee_ids or []) if str(a).strip()]
    body_text = (text or "").strip()
    if not aid:
        return {"error": "account_id is required"}
    if not attendees:
        return {"error": "attendee_id is required"}
    if not body_text:
        return {"error": "Message text is required"}

    primary = attendees[0]
    api_choice = _linkedin_api_for_attendee(primary, linkedin_api)
    linkedin_opts: Dict[str, Any] = {"api": api_choice}
    if inmail and api_choice == "classic":
        linkedin_opts["inmail"] = True

    payload: Dict[str, Any] = {
        "account_id": aid,
        "attendees_ids": attendees,
        "text": body_text,
        "linkedin": linkedin_opts,
    }
    subj = (subject or "").strip()
    if subj:
        payload["subject"] = subj

    result = await _request("POST", "/api/v1/chats", json=payload, timeout=45.0)
    if result.get("error"):
        return result
    data = result.get("data") or {}
    chat_id = data.get("chat_id") or data.get("id")
    if not chat_id:
        return {"error": "Unipile did not return a chat id."}
    return {
        "success": True,
        "chat_id": str(chat_id),
        "message_id": data.get("message_id"),
        "data": data,
    }


_ATTACHMENT_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "video/mp4": "mp4",
}


async def _download_attachment(url: str):
    """Fetch a media URL to (bytes, mime, filename) for multipart upload. Best-effort."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code >= 400 or not resp.content:
            logger.warning("[unipile] attachment fetch %s -> HTTP %s", url, resp.status_code)
            return None, None, None
        mime = (resp.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()
        ext = _ATTACHMENT_EXT.get(mime, "jpg")
        return resp.content, mime, f"attachment.{ext}"
    except Exception as exc:
        logger.warning("[unipile] attachment download failed for %s: %s", url, exc)
        return None, None, None


async def publish_linkedin_post(
    account_id: str,
    *,
    text: str,
    image_url: Optional[str] = None,
    as_organization: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish a LinkedIn post via Unipile (Premium connect).

    Pass ``as_organization`` (the numeric company id) to post on behalf of a
    company page the member administers, instead of as the member.
    """
    aid = strip_public_account_id(account_id)
    body_text = (text or "").strip()
    if not aid:
        return {"error": "account_id is required"}
    if not body_text:
        return {"error": "Post text is required"}

    # Unipile's create-post endpoint is multipart/form-data; text fields are sent
    # as (None, value) parts and attachments as real file parts.
    parts: List[Any] = [
        ("account_id", (None, aid)),
        ("text", (None, body_text)),
    ]
    org = (as_organization or "").strip()
    if org:
        parts.append(("as_organization", (None, org)))
    img = (image_url or "").strip()
    if img.startswith("http"):
        content, mime, fname = await _download_attachment(img)
        if content:
            parts.append(("attachments", (fname, content, mime)))

    result = await _request("POST", "/api/v1/posts", files=parts, timeout=60.0)
    if result.get("error"):
        return result
    data = result.get("data") or {}
    nested_post = data.get("post") if isinstance(data.get("post"), dict) else {}
    post_id = (
        data.get("id")
        or data.get("post_id")
        or data.get("postId")
        or nested_post.get("id")
    )
    if not post_id and isinstance(data, dict):
        post_id = data.get("share_url") or data.get("permalink")
    return {
        "success": True,
        "post_id": str(post_id) if post_id else None,
        "data": data,
    }


async def get_connection_status(db, user_oid: Any, business_id: str) -> Dict[str, Any]:
    if not is_configured():
        return {"connected": False, "configured": False}
    account_id = await resolve_linkedin_account_id(db, user_oid, business_id)
    stored = await get_stored_linkedin_account(db, user_oid)
    inmail_balance: Optional[Dict[str, Any]] = None
    if account_id:
        bal = await get_inmail_balance(account_id)
        if not bal.get("error"):
            inmail_balance = bal
    return {
        "connected": bool(account_id),
        "configured": True,
        "account_id": public_account_id(account_id) if account_id else None,
        "name": (stored or {}).get("name"),
        "contract_id": (stored or {}).get("contract_id"),
        "contract_name": (stored or {}).get("contract_name"),
        "contract_product": (stored or {}).get("contract_product"),
        "inmail_balance": inmail_balance,
    }

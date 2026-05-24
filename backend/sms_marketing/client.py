"""
sms_marketing/client.py
Sent.dm v3 API client for SMS send, receive tracking, and templates.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from country_utils import get_dial_code

logger = logging.getLogger(__name__)

SENT_API_BASE = os.environ.get("SENT_DM_API_BASE", "https://api.sent.dm")
PLATFORM_API_KEY = os.environ.get("SENT_DM_API_KEY", "")


def normalize_phone(phone: str, country_code: str = "") -> str:
    """Best-effort E.164 normalization using ISO country code when the number has no + prefix."""
    if not phone:
        return ""
    raw = re.sub(r"[^\d+]", "", phone.strip())
    if raw.startswith("+"):
        return raw
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    dial = get_dial_code(country_code)
    if dial:
        if digits.startswith("0") and len(digits) >= 7:
            return f"+{dial}{digits[1:]}"
        if digits.startswith(dial):
            return f"+{digits}"
        if len(digits) <= 12 and not digits.startswith(dial):
            return f"+{dial}{digits}"
    if len(digits) >= 10:
        return f"+{digits}"
    return f"+{digits}" if digits else ""


def _headers(api_key: str, idempotency_key: Optional[str] = None, profile_id: Optional[str] = None) -> Dict[str, str]:
    h = {"x-api-key": api_key, "Content-Type": "application/json"}
    if idempotency_key:
        h["Idempotency-Key"] = idempotency_key
    if profile_id:
        h["x-profile-id"] = profile_id
    return h


def resolve_api_key(settings: Dict[str, Any]) -> str:
    provider = (settings.get("provider") or "platform").lower()
    if provider == "own":
        key = (settings.get("api_key") or "").strip()
        if not key:
            raise RuntimeError("SMS is not configured for your account. Contact support.")
        return key
    if not PLATFORM_API_KEY:
        raise RuntimeError("SMS is not available yet. Contact support or complete your application under Setup.")
    return PLATFORM_API_KEY


async def send_message(
    api_key: str,
    to: List[str],
    *,
    template_id: str,
    template_name: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    sandbox: bool = False,
    idempotency_key: Optional[str] = None,
    profile_id: Optional[str] = None,
    country_code: str = "",
) -> Dict[str, Any]:
    phones = [normalize_phone(p, country_code) for p in to if normalize_phone(p, country_code)]
    if not phones:
        raise RuntimeError("No valid phone numbers to send to")
    if not template_id:
        raise RuntimeError("A message template is required")

    payload: Dict[str, Any] = {
        "to": phones,
        "channel": ["sms"],
        "template": {
            "id": template_id,
            "parameters": parameters or {},
        },
        "sandbox": sandbox,
    }
    if template_name:
        payload["template"]["name"] = template_name

    async with httpx.AsyncClient(timeout=45) as hc:
        r = await hc.post(
            f"{SENT_API_BASE}/v3/messages",
            json=payload,
            headers=_headers(api_key, idempotency_key, profile_id),
        )
    data = r.json()
    if not r.is_success or not data.get("success", False):
        err = data.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise RuntimeError(msg or f"SMS send failed ({r.status_code})")
    return data.get("data") or {}


def profile_id_from_settings(settings: Dict[str, Any]) -> Optional[str]:
    pid = (settings.get("sentdm_profile_id") or "").strip()
    return pid or None


async def create_profile(
    api_key: str,
    payload: Dict[str, Any],
    *,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=60) as hc:
        r = await hc.post(
            f"{SENT_API_BASE}/v3/profiles",
            json=payload,
            headers=_headers(api_key, idempotency_key),
        )
    data = r.json()
    if not r.is_success or not data.get("success", False):
        err = data.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise RuntimeError(msg or f"Profile setup failed ({r.status_code})")
    return data.get("data") or {}


async def get_profile(api_key: str, profile_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.get(
            f"{SENT_API_BASE}/v3/profiles/{profile_id}",
            headers=_headers(api_key),
        )
    data = r.json()
    if not r.is_success or not data.get("success", False):
        raise RuntimeError(data.get("error", {}).get("message", r.text[:200]))
    return data.get("data") or {}


async def complete_profile(
    api_key: str,
    profile_id: str,
    *,
    webhook_url: str,
    sandbox: bool = False,
) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=60) as hc:
        r = await hc.post(
            f"{SENT_API_BASE}/v3/profiles/{profile_id}/complete",
            json={"webHookUrl": webhook_url, "sandbox": sandbox},
            headers=_headers(api_key, idempotency_key=f"complete-{profile_id}"),
        )
    data = r.json()
    if not r.is_success or not data.get("success", False):
        err = data.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise RuntimeError(msg or f"Profile completion failed ({r.status_code})")
    return data.get("data") or {}


async def create_brand_campaign(
    api_key: str,
    profile_id: str,
    campaign: Dict[str, Any],
    *,
    sandbox: bool = False,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=60) as hc:
        r = await hc.post(
            f"{SENT_API_BASE}/v3/profiles/{profile_id}/campaigns",
            json={"campaign": campaign, "sandbox": sandbox},
            headers=_headers(api_key, idempotency_key or f"campaign-{profile_id}"),
        )
    data = r.json()
    if not r.is_success or not data.get("success", False):
        err = data.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise RuntimeError(msg or f"Campaign setup failed ({r.status_code})")
    return data.get("data") or {}


async def get_message(api_key: str, message_id: str, profile_id: Optional[str] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.get(
            f"{SENT_API_BASE}/v3/messages/{message_id}",
            headers=_headers(api_key, profile_id=profile_id),
        )
    data = r.json()
    if not r.is_success or not data.get("success", False):
        raise RuntimeError(data.get("error", {}).get("message", r.text[:200]))
    return data.get("data") or {}


async def list_templates(
    api_key: str,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str = "",
    status: str = "APPROVED",
    profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"page": page, "page_size": page_size}
    if search:
        params["search"] = search
    if status:
        params["status"] = status
    async with httpx.AsyncClient(timeout=30) as hc:
        r = await hc.get(
            f"{SENT_API_BASE}/v3/templates",
            params=params,
            headers=_headers(api_key, profile_id=profile_id),
        )
    data = r.json()
    if not r.is_success or not data.get("success", False):
        raise RuntimeError(data.get("error", {}).get("message", r.text[:200]))
    return data.get("data") or {}


def verify_webhook_signature(
    raw_body: bytes,
    signature: str,
    webhook_id: str,
    timestamp: str,
    signing_secret: str,
) -> bool:
    """Verify Sent.dm webhook HMAC-SHA256 signature."""
    if not all([signature, webhook_id, timestamp, signing_secret]):
        return False
    secret = signing_secret
    if secret.startswith("whsec_"):
        secret = secret[6:]
    try:
        key_bytes = base64.b64decode(secret)
    except Exception:
        return False
    signed_content = f"{webhook_id}.{timestamp}.{raw_body.decode('utf-8')}"
    expected = hmac.new(key_bytes, signed_content.encode("utf-8"), hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode("utf-8")
    provided = signature.split(",", 1)[-1] if "," in signature else signature
    return hmac.compare_digest(expected_b64, provided)


async def send_bulk(
    settings: Dict[str, Any],
    recipients: List[str],
    *,
    template_id: str,
    template_name: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    sandbox: bool = False,
    batch_size: int = 50,
) -> Dict[str, int]:
    api_key = resolve_api_key(settings)
    profile_id = profile_id_from_settings(settings)
    country_code = (settings.get("country_code") or "").strip()
    sent = 0
    failed = 0
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i : i + batch_size]
        try:
            await send_message(
                api_key,
                batch,
                template_id=template_id,
                template_name=template_name,
                parameters=parameters,
                sandbox=sandbox,
                idempotency_key=f"sms-{template_id}-{i}",
                profile_id=profile_id,
                country_code=country_code,
            )
            sent += len(batch)
        except Exception as e:
            logger.warning("[sms] batch send failed (%s): %s", i, e)
            failed += len(batch)
    return {"sent": sent, "failed": failed}

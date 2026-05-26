"""
sms_marketing/routes.py
SMS campaigns, inbox, Sent.dm settings, and business application workflow.
"""
from __future__ import annotations

import logging
import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from sms_marketing.client import (
    get_message,
    list_templates,
    normalize_phone,
    profile_id_from_settings,
    resolve_api_key,
    send_bulk,
    send_message,
    verify_webhook_signature,
)
from sms_marketing.provision import normalize_sender_name, submit_to_provider, sync_profile_activation
from sms_marketing.regions import get_application_schema, normalize_country_iso, validate_application

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sms-marketing", tags=["sms_marketing"])
webhook_router = APIRouter(prefix="/sms-marketing", tags=["sms_marketing_webhook"])

STOP_KEYWORDS = {"STOP", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
START_KEYWORDS = {"START", "UNSTOP", "SUBSCRIBE", "YES"}


# ── Pydantic models ───────────────────────────────────────────────────────────

class SmsSettingsBody(BaseModel):
    provider: str = "platform"          # platform | own (own = legacy/operator)
    api_key: str = ""
    sentdm_customer_id: str = ""
    sentdm_profile_id: str = ""
    sender_name: str = ""
    from_number: str = ""
    default_template_id: str = ""
    webhook_secret: str = ""
    notifications_enabled: bool = True   # send SMS to opted-in end-customers via Zilo
    owner_notification_phone: str = ""   # business owner's number — alerts from Zilo


class SmsApplicationCreate(BaseModel):
    business_name: str
    sender_name: str = Field(..., description="Custom sender name shown on SMS (3–11 characters)")
    legal_business_name: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    use_case: str = Field(..., description="How you plan to use SMS marketing")
    expected_volume: str = "under_1k"
    website: str = ""
    contact_email: str = ""
    business_street: str = ""
    business_city: str = ""
    business_state: str = ""
    business_postal: str = ""
    business_country: str = ""
    # Regional (shown based on country)
    tax_id: str = ""
    entity_type: str = ""
    sample_message_1: str = ""
    sample_message_2: str = ""
    message_flow: str = ""
    privacy_policy_url: str = ""
    terms_url: str = ""
    consent_description: str = ""
    gdpr_ack: bool = False
    business_registration_number: str = ""


class CampaignCreate(BaseModel):
    name: str
    template_id: str
    template_name: str = ""
    template_parameters: Dict[str, Any] = {}
    recipient_phones: List[str] = []
    recipient_tags: List[str] = []
    require_opt_in: bool = True


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    template_parameters: Optional[Dict[str, Any]] = None
    recipient_phones: Optional[List[str]] = None
    recipient_tags: Optional[List[str]] = None
    require_opt_in: Optional[bool] = None


class SendRequest(BaseModel):
    test_phone: Optional[str] = None
    sandbox: bool = False


class OptInUpdate(BaseModel):
    customer_id: str
    sms_opt_in: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _id(doc: Dict) -> str:
    return str(doc.get("_id", ""))


def _clean(doc: Dict) -> Dict:
    doc = dict(doc)
    doc["id"] = _id(doc)
    doc.pop("_id", None)
    return doc


def _uid(user: Dict) -> str:
    return str(user.get("business_id") or user["_id"])


def _user_country_iso(user: Dict) -> str:
    for raw in (
        user.get("country_code"),
        (user.get("settings") or {}).get("country_code"),
        (user.get("settings") or {}).get("country"),
        user.get("country"),
    ):
        iso = normalize_country_iso(str(raw or ""))
        if iso:
            return iso
    return ""


def _resolve_country_iso(user: Dict, override: str = "", settings: Optional[Dict] = None) -> str:
    for candidate in (
        normalize_country_iso(override),
        normalize_country_iso((settings or {}).get("country_code") or ""),
        _user_country_iso(user),
        normalize_country_iso(os.environ.get("SENT_DM_DEFAULT_COUNTRY") or ""),
    ):
        if candidate:
            return candidate
    return ""


def _phone_variants(phone: str, country_code: str) -> set[str]:
    norm = normalize_phone(phone, country_code)
    variants = {norm, phone.strip(), norm.lstrip("+")}
    dial = __import__("country_utils").get_dial_code(country_code)
    if dial and norm.startswith(f"+{dial}"):
        local = norm[len(dial) + 1 :]
        if local:
            variants.add(f"0{local}")
            variants.add(local)
    return {v for v in variants if v}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _marketing_active(app: Optional[Dict]) -> bool:
    return bool(app and app.get("status") in ("active", "approved"))


def _capabilities(settings: Dict, app: Optional[Dict]) -> Dict[str, bool]:
    owner_phone = (settings.get("owner_notification_phone") or "").strip()
    return {
        "platform_notifications": settings.get("notifications_enabled", True) is not False,
        "owner_phone_linked": bool(owner_phone),
        "marketing_sms": _marketing_active(app),
    }


async def _get_settings(db, user_id: str) -> Dict:
    doc = await db.sms_settings.find_one({"user_id": user_id})
    if not doc:
        return {
            "provider": "platform",
            "api_key": "",
            "sentdm_customer_id": "",
            "sentdm_profile_id": "",
            "sender_name": "",
            "from_number": "",
            "country_code": "",
            "default_template_id": "",
            "webhook_secret": "",
            "notifications_enabled": True,
            "owner_notification_phone": "",
        }
    return _clean(doc)


def _mask_settings(s: Dict) -> Dict:
    masked = dict(s)
    key = masked.get("api_key") or ""
    if key:
        masked["api_key"] = "••••••••" + key[-4:] if len(key) > 4 else "••••••••"
    secret = masked.get("webhook_secret") or ""
    if secret:
        masked["webhook_secret"] = "••••••••" + secret[-4:] if len(secret) > 4 else "••••••••"
    return masked


async def _get_application(db, user_id: str) -> Optional[Dict]:
    doc = await db.sms_applications.find_one({"user_id": user_id})
    if not doc:
        return None
    cleaned = _clean(doc)
    cleaned.pop("provision_error", None)
    return cleaned


async def _refresh_application(db, user_id: str) -> Optional[Dict]:
    app = await db.sms_applications.find_one({"user_id": user_id})
    if not app:
        return None
    synced = await sync_profile_activation(db, user_id, app)
    if synced:
        return _clean(synced)
    return _clean(app)


async def _collect_recipients(
    db,
    user_id: str,
    phones: List[str],
    tags: List[str],
    *,
    require_opt_in: bool,
    country_code: str = "",
) -> List[str]:
    result: set[str] = set()
    for p in phones:
        norm = normalize_phone(p, country_code)
        if norm:
            result.add(norm)

    query_base: Dict[str, Any] = {"user_id": user_id}
    if require_opt_in:
        query_base["sms_opt_in"] = True

    if tags:
        tag_query = {**query_base, "tags": {"$in": tags}}
        async for c in db.customers.find(tag_query, {"phone_number": 1}):
            norm = normalize_phone(c.get("phone_number", ""), country_code)
            if norm:
                result.add(norm)
        async for c in db.contacts.find(tag_query, {"phone": 1, "phone_number": 1}):
            norm = normalize_phone(c.get("phone_number") or c.get("phone", ""), country_code)
            if norm:
                result.add(norm)

    if phones and require_opt_in:
        opted_out: set[str] = set()
        async for c in db.customers.find(
            {"user_id": user_id, "sms_opt_in": False},
            {"phone_number": 1},
        ):
            norm = normalize_phone(c.get("phone_number", ""), country_code)
            if norm:
                opted_out.add(norm)
        result -= opted_out

    return sorted(result)


async def _find_customer_by_phone(db, user_id: str, phone: str, country_code: str = "") -> Optional[Dict]:
    variants = _phone_variants(phone, country_code)
    if not variants:
        return None
    return await db.customers.find_one({"user_id": user_id, "phone_number": {"$in": list(variants)}})


async def _store_message(
    db,
    user_id: str,
    *,
    direction: str,
    phone: str,
    body: str,
    status: str,
    sentdm_message_id: str = "",
    channel: str = "sms",
    campaign_id: str = "",
    customer_id: str = "",
    country_code: str = "",
) -> str:
    doc = {
        "user_id": user_id,
        "direction": direction,
        "phone": normalize_phone(phone, country_code) or phone,
        "body": body,
        "status": status,
        "channel": channel,
        "sentdm_message_id": sentdm_message_id,
        "campaign_id": campaign_id,
        "customer_id": customer_id,
        "created_at": _now(),
        "updated_at": _now(),
    }
    result = await db.sms_messages.insert_one(doc)
    return str(result.inserted_id)


async def _handle_opt_in_keyword(db, user_id: str, phone: str, text: str, country_code: str = "") -> Optional[str]:
    keyword = (text or "").strip().upper()
    if keyword not in STOP_KEYWORDS and keyword not in START_KEYWORDS:
        return None
    customer = await _find_customer_by_phone(db, user_id, phone, country_code)
    if not customer:
        return None
    if keyword in STOP_KEYWORDS:
        await db.customers.update_one(
            {"_id": customer["_id"]},
            {"$set": {"sms_opt_in": False, "sms_opt_out_at": _now()}},
        )
        return "You've been unsubscribed from SMS messages. Reply START to opt back in."
    await db.customers.update_one(
        {"_id": customer["_id"]},
        {"$set": {"sms_opt_in": True}, "$unset": {"sms_opt_out_at": ""}},
    )
    return "You're subscribed to SMS messages. Reply STOP anytime to unsubscribe."


# ── Authenticated routes ──────────────────────────────────────────────────────

def make_sms_marketing_router(get_current_user, db):

    @router.get("/settings")
    async def get_sms_settings(user=Depends(get_current_user)):
        user_id = _uid(user)
        settings = _mask_settings(await _get_settings(db, user_id))
        if not settings.get("country_code"):
            cc = _user_country_iso(user)
            if cc:
                settings["country_code"] = cc
        application = await _refresh_application(db, user_id)
        caps = _capabilities(settings, application)
        return {"settings": settings, "application": application, "capabilities": caps}

    @router.post("/settings")
    async def save_sms_settings(body: SmsSettingsBody, user=Depends(get_current_user)):
        user_id = _uid(user)
        existing = await db.sms_settings.find_one({"user_id": user_id}) or {}
        creds = dict(existing)
        creds.update(body.dict())
        # Preserve api_key / webhook_secret when masked placeholder sent back
        if body.api_key.startswith("••••"):
            creds["api_key"] = existing.get("api_key", "")
        if body.webhook_secret.startswith("••••"):
            creds["webhook_secret"] = existing.get("webhook_secret", "")
        creds["user_id"] = user_id
        creds["updated_at"] = _now()
        await db.sms_settings.update_one({"user_id": user_id}, {"$set": creds}, upsert=True)

        if body.provider == "own" and body.api_key and not body.api_key.startswith("••••"):
            await db.sms_applications.update_one(
                {"user_id": user_id},
                {"$set": {"status": "active", "approved_at": _now(), "updated_at": _now()}},
                upsert=False,
            )
        return {"ok": True}

    @router.post("/settings/test")
    async def test_sms_settings(body: Dict[str, Any], user=Depends(get_current_user)):
        user_id = _uid(user)
        test_phone = (body.get("test_phone") or "").strip()
        if not test_phone:
            raise HTTPException(400, "test_phone required")
        settings = await _get_settings(db, user_id)
        for k in ("provider", "api_key", "default_template_id"):
            if body.get(k):
                settings[k] = body[k]
        template_id = settings.get("default_template_id") or body.get("template_id")
        if not template_id:
            raise HTTPException(400, "Configure a default message template first")

        app = await _get_application(db, user_id)
        mode = (body.get("mode") or "auto").lower()
        marketing = _marketing_active(app) and settings.get("sentdm_profile_id")
        platform_ok = settings.get("notifications_enabled", True) is not False

        use_marketing = mode == "marketing" or (mode == "auto" and marketing)
        if use_marketing and not marketing:
            raise HTTPException(403, "Complete your SMS marketing application to test your business sender.")
        if not use_marketing and not platform_ok:
            raise HTTPException(403, "Enable customer notifications under Setup first.")

        try:
            api_key = resolve_api_key(settings)
            profile_id = profile_id_from_settings(settings) if use_marketing else None
            cc = _resolve_country_iso(user, (app or {}).get("business_country", ""), settings)
            data = await send_message(
                api_key,
                [test_phone],
                template_id=template_id,
                parameters=body.get("template_parameters") or {"name": "Test"},
                sandbox=bool(body.get("sandbox", True)),
                profile_id=profile_id,
                country_code=cc,
            )
            label = "marketing" if use_marketing else "platform"
            return {"ok": True, "mode": label, "message": f"Test SMS queued to {normalize_phone(test_phone, cc)}", "data": data}
        except Exception as e:
            raise HTTPException(502, str(e))

    @router.get("/application/schema")
    async def get_sms_application_schema(
        country: str = "",
        user=Depends(get_current_user),
    ):
        cc = _resolve_country_iso(user, country)
        return get_application_schema(cc or "")

    @router.get("/application")
    async def get_sms_application(user=Depends(get_current_user)):
        user_id = _uid(user)
        app = await _refresh_application(db, user_id)
        return app or {"status": "none"}

    @router.post("/application")
    async def submit_sms_application(body: SmsApplicationCreate, user=Depends(get_current_user)):
        user_id = _uid(user)
        existing = await db.sms_applications.find_one({"user_id": user_id})
        if existing and existing.get("status") in ("pending", "active"):
            raise HTTPException(400, "An application already exists for this account")

        sender_name = normalize_sender_name(body.sender_name or body.business_name)
        if len(sender_name) < 3:
            raise HTTPException(400, "Sender name must be at least 3 characters (letters and numbers)")

        country_iso = _resolve_country_iso(user, body.business_country)
        if not country_iso:
            raise HTTPException(400, "Select a country or set one under Settings → Regional")

        app_data = body.dict()
        app_data["business_country"] = country_iso
        validation_errors = validate_application(app_data, country_iso)
        if validation_errors:
            raise HTTPException(400, "; ".join(validation_errors[:5]))

        user_doc = await db.users.find_one({"_id": user_id})
        doc = {
            **{k: v for k, v in app_data.items() if k != "business_country"},
            "user_id": user_id,
            "business_name": body.business_name or (user_doc or {}).get("business_name", ""),
            "sender_name": sender_name,
            "legal_business_name": body.legal_business_name or body.business_name,
            "contact_name": body.contact_name or (user_doc or {}).get("name", ""),
            "contact_phone": body.contact_phone or (user_doc or {}).get("phone", ""),
            "contact_email": body.contact_email or (user_doc or {}).get("email", ""),
            "business_country": country_iso,
            "region": get_application_schema(country_iso)["region"],
            "status": "pending",
            "profile_status": "pending",
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.sms_applications.update_one({"user_id": user_id}, {"$set": doc}, upsert=True)
        await db.sms_settings.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "country_code": country_iso, "updated_at": _now()}},
            upsert=True,
        )

        provision = await submit_to_provider(user_id, doc)
        if provision.get("ok"):
            await db.sms_applications.update_one(
                {"user_id": user_id},
                {"$set": {
                    "sentdm_profile_id": provision["profile_id"],
                    "profile_status": provision.get("profile_status", "submitted"),
                    "sender_name": provision.get("sender_name") or sender_name,
                    "updated_at": _now(),
                }},
            )
            await db.sms_settings.update_one(
                {"user_id": user_id},
                {"$set": {
                    "user_id": user_id,
                    "provider": "platform",
                    "sentdm_profile_id": provision["profile_id"],
                    "sender_name": provision.get("sender_name") or sender_name,
                    "country_code": country_iso,
                    "updated_at": _now(),
                }},
                upsert=True,
            )
            logger.info("[sms] provisioned profile user=%s profile=%s", user_id, provision["profile_id"])
        else:
            await db.sms_applications.update_one(
                {"user_id": user_id},
                {"$set": {
                    "provision_error": provision.get("reason", "unknown"),
                    "updated_at": _now(),
                }},
            )
            logger.warning("[sms] provision deferred user=%s reason=%s", user_id, provision.get("reason"))

        logger.info("[sms] application submitted user=%s business=%s sender=%s", user_id, doc["business_name"], sender_name)
        return {
            "ok": True,
            "status": "pending",
            "sender_name": sender_name,
            "message": "Application submitted. We're setting up SMS with your business name — we'll notify you when it's ready.",
        }

    @router.get("/templates")
    async def get_sentdm_templates(
        search: str = "",
        page: int = 1,
        user=Depends(get_current_user),
    ):
        user_id = _uid(user)
        settings = await _get_settings(db, user_id)
        try:
            api_key = resolve_api_key(settings)
            profile_id = profile_id_from_settings(settings)
            data = await list_templates(api_key, page=page, page_size=50, search=search, profile_id=profile_id)
            return data
        except Exception as e:
            raise HTTPException(502, str(e))

    @router.get("/campaigns")
    async def list_campaigns(user=Depends(get_current_user)):
        user_id = _uid(user)
        docs = await db.sms_campaigns.find({"user_id": user_id}).sort("created_at", -1).limit(100).to_list(100)
        return {"campaigns": [_clean(d) for d in docs]}

    @router.post("/campaigns")
    async def create_campaign(body: CampaignCreate, user=Depends(get_current_user)):
        user_id = _uid(user)
        if not body.template_id:
            raise HTTPException(400, "template_id is required")
        doc = {
            "user_id": user_id,
            "name": body.name,
            "template_id": body.template_id,
            "template_name": body.template_name,
            "template_parameters": body.template_parameters,
            "recipient_phones": body.recipient_phones,
            "recipient_tags": body.recipient_tags,
            "require_opt_in": body.require_opt_in,
            "status": "draft",
            "stats": {"sent": 0, "failed": 0, "delivered": 0},
            "created_at": _now(),
            "updated_at": _now(),
        }
        result = await db.sms_campaigns.insert_one(doc)
        return {"ok": True, "id": str(result.inserted_id)}

    @router.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, user=Depends(get_current_user)):
        user_id = _uid(user)
        doc = await db.sms_campaigns.find_one({"_id": ObjectId(campaign_id), "user_id": user_id})
        if not doc:
            raise HTTPException(404, "Campaign not found")
        return _clean(doc)

    @router.patch("/campaigns/{campaign_id}")
    async def update_campaign(campaign_id: str, body: CampaignUpdate, user=Depends(get_current_user)):
        user_id = _uid(user)
        update = {k: v for k, v in body.dict().items() if v is not None}
        if not update:
            raise HTTPException(400, "Nothing to update")
        update["updated_at"] = _now()
        result = await db.sms_campaigns.update_one(
            {"_id": ObjectId(campaign_id), "user_id": user_id},
            {"$set": update},
        )
        if not result.matched_count:
            raise HTTPException(404, "Campaign not found")
        return {"ok": True}

    @router.delete("/campaigns/{campaign_id}")
    async def delete_campaign(campaign_id: str, user=Depends(get_current_user)):
        user_id = _uid(user)
        await db.sms_campaigns.delete_one({"_id": ObjectId(campaign_id), "user_id": user_id})
        return {"ok": True}

    @router.post("/campaigns/{campaign_id}/send")
    async def send_campaign(campaign_id: str, body: SendRequest, user=Depends(get_current_user)):
        user_id = _uid(user)
        doc = await db.sms_campaigns.find_one({"_id": ObjectId(campaign_id), "user_id": user_id})
        if not doc:
            raise HTTPException(404, "Campaign not found")

        settings = await _get_settings(db, user_id)
        app = await _get_application(db, user_id)
        if not _marketing_active(app):
            raise HTTPException(403, "Apply for your own SMS marketing account under Setup to run campaigns.")

        cc = _resolve_country_iso(user, app.get("business_country", ""), settings)

        if body.test_phone:
            try:
                api_key = resolve_api_key(settings)
                profile_id = profile_id_from_settings(settings)
                data = await send_message(
                    api_key,
                    [body.test_phone],
                    template_id=doc["template_id"],
                    template_name=doc.get("template_name", ""),
                    parameters=doc.get("template_parameters") or {},
                    sandbox=body.sandbox,
                    profile_id=profile_id,
                    country_code=cc,
                )
                await _store_message(
                    db, user_id,
                    direction="outbound", phone=body.test_phone,
                    body=str(doc.get("template_parameters", "")),
                    status="queued", sentdm_message_id="",
                    campaign_id=campaign_id,
                    country_code=cc,
                )
                return {"ok": True, "test": True, "data": data}
            except Exception as e:
                raise HTTPException(502, str(e))

        recipients = await _collect_recipients(
            db, user_id,
            doc.get("recipient_phones", []),
            doc.get("recipient_tags", []),
            require_opt_in=doc.get("require_opt_in", True),
            country_code=cc,
        )
        if not recipients:
            raise HTTPException(400, "No eligible recipients. Add phone numbers or tags, and ensure customers have SMS opt-in.")

        await db.sms_campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {"status": "sending", "updated_at": _now()}},
        )

        try:
            result = await send_bulk(
                settings,
                recipients,
                template_id=doc["template_id"],
                template_name=doc.get("template_name", ""),
                parameters=doc.get("template_parameters") or {},
                sandbox=body.sandbox,
            )
        except Exception as e:
            await db.sms_campaigns.update_one(
                {"_id": ObjectId(campaign_id)},
                {"$set": {"status": "draft", "updated_at": _now()}},
            )
            raise HTTPException(502, str(e))

        final_status = "sent" if result["failed"] == 0 else "partial"
        await db.sms_campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {
                "status": final_status,
                "sent_at": _now(),
                "stats": {"sent": result["sent"], "failed": result["failed"], "delivered": 0},
                "updated_at": _now(),
            }},
        )
        return {"ok": True, **result, "status": final_status}

    @router.get("/messages")
    async def list_messages(
        direction: str = "",
        phone: str = "",
        limit: int = 100,
        user=Depends(get_current_user),
    ):
        user_id = _uid(user)
        settings = await _get_settings(db, user_id)
        cc = _resolve_country_iso(user, "", settings)
        query: Dict[str, Any] = {"user_id": user_id}
        if direction in ("inbound", "outbound"):
            query["direction"] = direction
        if phone:
            query["phone"] = normalize_phone(phone, cc)
        docs = await db.sms_messages.find(query).sort("created_at", -1).limit(min(limit, 200)).to_list(min(limit, 200))
        return {"messages": [_clean(d) for d in docs]}

    @router.get("/messages/{message_id}/status")
    async def refresh_message_status(message_id: str, user=Depends(get_current_user)):
        user_id = _uid(user)
        doc = await db.sms_messages.find_one({"_id": ObjectId(message_id), "user_id": user_id})
        if not doc:
            raise HTTPException(404, "Message not found")
        sent_id = doc.get("sentdm_message_id")
        if not sent_id:
            raise HTTPException(400, "No message delivery ID on record")
        settings = await _get_settings(db, user_id)
        try:
            api_key = resolve_api_key(settings)
            profile_id = profile_id_from_settings(settings)
            data = await get_message(api_key, sent_id, profile_id=profile_id)
            status = (data.get("status") or "unknown").lower()
            await db.sms_messages.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": status, "updated_at": _now(), "sentdm_payload": data}},
            )
            return {"ok": True, "status": status, "data": data}
        except Exception as e:
            raise HTTPException(502, str(e))

    @router.post("/opt-in")
    async def update_customer_opt_in(body: OptInUpdate, user=Depends(get_current_user)):
        user_id = _uid(user)
        update: Dict[str, Any] = {"sms_opt_in": body.sms_opt_in}
        if body.sms_opt_in:
            unset = {"sms_opt_out_at": ""}
            await db.customers.update_one(
                {"_id": ObjectId(body.customer_id), "user_id": user_id},
                {"$set": update, "$unset": unset},
            )
        else:
            update["sms_opt_out_at"] = _now()
            await db.customers.update_one(
                {"_id": ObjectId(body.customer_id), "user_id": user_id},
                {"$set": update},
            )
        return {"ok": True}

    @router.get("/stats")
    async def sms_stats(user=Depends(get_current_user)):
        user_id = _uid(user)
        campaigns = await db.sms_campaigns.find({"user_id": user_id}).to_list(500)
        total_sent = sum((c.get("stats") or {}).get("sent", 0) for c in campaigns)
        total_failed = sum((c.get("stats") or {}).get("failed", 0) for c in campaigns)
        opted_in = await db.customers.count_documents({"user_id": user_id, "sms_opt_in": True})
        inbound = await db.sms_messages.count_documents({"user_id": user_id, "direction": "inbound"})
        return {
            "campaigns": {
                "total": len(campaigns),
                "sent": sum(1 for c in campaigns if c.get("status") in ("sent", "partial")),
                "draft": sum(1 for c in campaigns if c.get("status") == "draft"),
            },
            "messages_sent": total_sent,
            "messages_failed": total_failed,
            "customers_opted_in": opted_in,
            "inbound_messages": inbound,
        }

    return router


def make_sms_operator_router(db, require_operator_secret):
    """Operator-only: manually activate SMS after profile is ready on the provider side."""

    op_router = APIRouter(prefix="/sms-marketing/operator", tags=["sms_marketing_operator"])

    @op_router.post("/activate")
    async def operator_activate_sms(request: Request):
        require_operator_secret(request)
        data = await request.json()
        user_id = str(data.get("user_id") or "").strip()
        if not user_id:
            raise HTTPException(400, "user_id required")

        from_number = (data.get("from_number") or "").strip()
        sender_name = (data.get("sender_name") or "").strip()
        profile_id = (data.get("sentdm_profile_id") or data.get("profile_id") or "").strip()
        default_template_id = (data.get("default_template_id") or os.environ.get("SENT_DM_DEFAULT_TEMPLATE_ID", "")).strip()

        patch: Dict[str, Any] = {
            "status": "active",
            "approved_at": _now(),
            "updated_at": _now(),
        }
        if from_number:
            patch["from_number"] = from_number
        if sender_name:
            patch["sender_name"] = sender_name
        if profile_id:
            patch["sentdm_profile_id"] = profile_id

        result = await db.sms_applications.update_one({"user_id": user_id}, {"$set": patch})
        if not result.matched_count:
            raise HTTPException(404, "No SMS application for this user")

        settings_patch: Dict[str, Any] = {
            "user_id": user_id,
            "provider": "platform",
            "updated_at": _now(),
        }
        if profile_id:
            settings_patch["sentdm_profile_id"] = profile_id
            settings_patch["sentdm_customer_id"] = profile_id
        if from_number:
            settings_patch["from_number"] = from_number
        if sender_name:
            settings_patch["sender_name"] = sender_name
        if default_template_id:
            settings_patch["default_template_id"] = default_template_id

        await db.sms_settings.update_one({"user_id": user_id}, {"$set": settings_patch}, upsert=True)
        logger.info("[sms] operator activated user=%s profile=%s", user_id, profile_id)
        return {"ok": True, "user_id": user_id, "status": "active"}

    return op_router


# ── Public webhook (Sent.dm inbound + delivery events) ────────────────────────

def make_sms_webhook_router(db):
    platform_secret = os.environ.get("SENT_DM_WEBHOOK_SECRET", "")

    @webhook_router.post("/webhook/sentdm")
    async def sentdm_webhook(request: Request):
        raw = await request.body()
        sig = request.headers.get("x-webhook-signature", "")
        wh_id = request.headers.get("x-webhook-id", "")
        ts = request.headers.get("x-webhook-timestamp", "")
        event_type = request.headers.get("x-webhook-event-type", "")

        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}

        # Resolve tenant: match sentdm customer/account id in settings
        account_id = ""
        if isinstance(payload, dict):
            account_id = (
                payload.get("payload", {}).get("account_id")
                or payload.get("data", {}).get("customer_id")
                or payload.get("account_id")
                or ""
            )

        settings_doc = None
        if account_id:
            settings_doc = await db.sms_settings.find_one({"sentdm_customer_id": account_id})
        if not settings_doc and account_id:
            settings_doc = await db.sms_settings.find_one({"sentdm_profile_id": account_id})
        if not settings_doc:
            # Fallback: first settings with matching webhook secret
            if platform_secret and verify_webhook_signature(raw, sig, wh_id, ts, platform_secret):
                settings_doc = await db.sms_settings.find_one({"provider": "platform"})
            else:
                async for s in db.sms_settings.find({"webhook_secret": {"$exists": True, "$ne": ""}}):
                    secret = s.get("webhook_secret", "")
                    if secret and verify_webhook_signature(raw, sig, wh_id, ts, secret):
                        settings_doc = s
                        break

        if settings_doc and settings_doc.get("webhook_secret"):
            if not verify_webhook_signature(raw, sig, wh_id, ts, settings_doc["webhook_secret"]):
                logger.warning("[sms-webhook] invalid signature account=%s", account_id)
                raise HTTPException(401, "Invalid webhook signature")
        elif platform_secret and sig:
            if not verify_webhook_signature(raw, sig, wh_id, ts, platform_secret):
                logger.warning("[sms-webhook] invalid platform signature")
                # Allow in dev when no secret configured
                if os.environ.get("SENT_DM_WEBHOOK_SKIP_VERIFY") != "1":
                    raise HTTPException(401, "Invalid webhook signature")

        user_id = (settings_doc or {}).get("user_id", "")
        field = payload.get("field", "")
        sub_type = payload.get("sub_type", event_type or "")
        inner = payload.get("payload") or payload.get("data") or payload

        # Inbound message
        if sub_type == "message.received" or (inner.get("direction") == "INBOUND"):
            from_phone = inner.get("from") or inner.get("phone") or ""
            text = inner.get("text") or inner.get("body") or ""
            if user_id:
                cc = (settings_doc or {}).get("country_code") or ""
                auto_reply = await _handle_opt_in_keyword(db, user_id, from_phone, text, cc)
                customer = await _find_customer_by_phone(db, user_id, from_phone, cc)
                await _store_message(
                    db, user_id,
                    direction="inbound",
                    phone=from_phone,
                    body=text,
                    status="received",
                    sentdm_message_id=inner.get("message_id") or inner.get("id") or "",
                    customer_id=str(customer["_id"]) if customer else "",
                    country_code=cc,
                )
                if auto_reply and settings_doc:
                    try:
                        settings = _clean(settings_doc)
                        template_id = settings.get("default_template_id")
                        if template_id:
                            api_key = resolve_api_key(settings)
                            await send_message(
                                api_key,
                                [from_phone],
                                template_id=template_id,
                                parameters={"message": auto_reply, "body": auto_reply},
                                profile_id=profile_id_from_settings(settings),
                                country_code=cc,
                            )
                    except Exception as e:
                        logger.warning("[sms-webhook] opt-in auto-reply failed: %s", e)
            return {"ok": True}

        # Delivery status updates
        if sub_type in ("message.delivered", "message.sent", "message.failed") or field == "message":
            msg_id = inner.get("message_id") or inner.get("id") or ""
            status = (inner.get("status") or sub_type.split(".")[-1] or "unknown").lower()
            if msg_id and user_id:
                await db.sms_messages.update_one(
                    {"user_id": user_id, "sentdm_message_id": msg_id},
                    {"$set": {"status": status, "updated_at": _now()}},
                )
                # Update campaign delivered count
                msg_doc = await db.sms_messages.find_one({"sentdm_message_id": msg_id})
                if msg_doc and msg_doc.get("campaign_id") and status == "delivered":
                    await db.sms_campaigns.update_one(
                        {"_id": ObjectId(msg_doc["campaign_id"])},
                        {"$inc": {"stats.delivered": 1}},
                    )

        return {"ok": True}

    @webhook_router.post("/webhook/profile-complete")
    async def profile_complete_webhook(request: Request):
        """Called by provider when profile setup finishes (POST /v3/profiles/{id}/complete)."""
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        profile_id = (
            payload.get("profile_id")
            or payload.get("profileId")
            or (payload.get("data") or {}).get("profile_id")
            or (payload.get("data") or {}).get("id")
            or ""
        )
        if not profile_id:
            return {"ok": True, "skipped": "no profile_id"}
        settings_doc = await db.sms_settings.find_one({"sentdm_profile_id": profile_id})
        if not settings_doc:
            return {"ok": True, "skipped": "unknown profile"}
        user_id = settings_doc.get("user_id", "")
        app = await db.sms_applications.find_one({"user_id": user_id})
        if app:
            await sync_profile_activation(db, user_id, app)
            logger.info("[sms-webhook] profile complete user=%s profile=%s", user_id, profile_id)
        return {"ok": True}

    return webhook_router

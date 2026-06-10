"""
White-label SMS provisioning: map CRM applications to Sent.dm sender profiles.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sms_marketing.client import (
    PLATFORM_API_KEY,
    complete_profile,
    create_brand_campaign,
    create_profile,
    get_profile,
)
from sms_marketing.regions import region_compliance_flags, resolve_region

logger = logging.getLogger(__name__)

VOLUME_MAP = {
    "under_1k": "1000",
    "1k_10k": "10000",
    "over_10k": "50000",
}

ACTIVE_PROFILE_STATUSES = {"approved", "completed", "active"}


def normalize_sender_name(raw: str) -> str:
    """Sent.dm short_name: 3–11 chars, letters/numbers/spaces, at least one letter."""
    cleaned = re.sub(r"[^A-Za-z0-9 ]", "", (raw or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 3:
        cleaned = (cleaned + " SMS")[:11].strip()
    if len(cleaned) > 11:
        cleaned = cleaned[:11].strip()
    if cleaned and not re.search(r"[A-Za-z]", cleaned):
        cleaned = f"{cleaned[:8]} Co".strip()[:11]
    return cleaned or "Zilo"


def build_profile_payload(app: Dict[str, Any]) -> Dict[str, Any]:
    country = (app.get("business_country") or app.get("country_code") or os.environ.get("SENT_DM_DEFAULT_COUNTRY") or "").upper()
    if not country:
        raise ValueError("business_country required for SMS provisioning")
    business_name = (app.get("business_name") or "").strip()
    legal_name = (app.get("legal_business_name") or business_name).strip()
    contact_name = (app.get("contact_name") or business_name).strip()
    contact_email = (app.get("contact_email") or "").strip()
    contact_phone = (app.get("contact_phone") or "").strip()
    use_case = (app.get("use_case") or "").strip()
    website = (app.get("website") or "").strip()
    short_name = normalize_sender_name(app.get("sender_name") or business_name)
    flags = region_compliance_flags(country)

    street = (app.get("business_street") or "").strip()
    city = (app.get("business_city") or "").strip()
    state = (app.get("business_state") or "").strip()
    postal = (app.get("business_postal") or "").strip()

    billing_address = ", ".join(p for p in [street, city, state, postal, country] if p)

    payload: Dict[str, Any] = {
        "name": business_name[:120],
        "short_name": short_name,
        "email": contact_email or None,
        "description": use_case[:500] if use_case else f"SMS for {business_name}",
        "inherit_contacts": True,
        "inherit_templates": True,
        "inherit_tcr_brand": False,
        "inherit_tcr_campaign": False,
        "billing_model": "organization",
        "brand": {
            "contact": {
                "name": contact_name,
                "businessName": business_name,
                "email": contact_email or None,
                "phone": contact_phone or None,
            },
            "business": {
                "legalName": legal_name,
                "taxId": (app.get("tax_id") or "").strip() or None,
                "taxIdType": "us_ein" if country == "US" and app.get("tax_id") else None,
                "entityType": (app.get("entity_type") or "").strip() or None,
                "street": street or None,
                "city": city or None,
                "state": state or None,
                "postalCode": postal or None,
                "country": country,
                "url": website or (app.get("privacy_policy_url") or "").strip() or None,
                "countryOfRegistration": country,
            },
            "compliance": {
                "vertical": "PROFESSIONAL",
                "brandRelationship": "SMALL_ACCOUNT",
                "primaryUseCase": use_case[:500] if use_case else None,
                "expectedMessagingVolume": VOLUME_MAP.get(app.get("expected_volume", ""), "1000"),
                "isTcrApplication": flags["is_tcr"],
                "destinationCountries": [{"id": country, "isMain": True}],
                "notes": (app.get("consent_description") or app.get("message_flow") or "")[:500] or None,
            },
        },
    }
    if contact_name and contact_email:
        payload["billing_contact"] = {
            "name": contact_name,
            "email": contact_email,
            "phone": contact_phone or None,
            "address": billing_address or None,
        }
    return payload


def _build_tcr_campaign(app: Dict[str, Any]) -> Dict[str, Any]:
    samples = [
        s for s in [
            (app.get("sample_message_1") or "").strip(),
            (app.get("sample_message_2") or "").strip(),
        ] if s
    ]
    name = (app.get("business_name") or "SMS Campaign")[:80]
    return {
        "name": name,
        "description": (app.get("use_case") or "")[:500],
        "type": "App",
        "useCases": [{
            "messagingUseCaseUs": "MARKETING",
            "sampleMessages": samples or ["Reply STOP to unsubscribe."],
        }],
        "messageFlow": (app.get("message_flow") or app.get("consent_description") or "")[:500],
        "privacyPolicyLink": (app.get("privacy_policy_url") or "").strip() or None,
        "termsAndConditionsLink": (app.get("terms_url") or "").strip() or None,
        "optinMessage": "You are subscribed to SMS updates. Reply STOP to opt out.",
        "optoutMessage": "You have been unsubscribed. Reply START to resubscribe.",
        "helpMessage": "Reply STOP to unsubscribe or contact us for help.",
        "optinKeywords": "START, YES, SUBSCRIBE",
        "optoutKeywords": "STOP, UNSUBSCRIBE, END",
        "helpKeywords": "HELP, INFO",
    }


async def _maybe_create_campaign(api_key: str, profile_id: str, app: Dict[str, Any]) -> None:
    country = (app.get("business_country") or "").upper()
    if not region_compliance_flags(country).get("requires_campaign"):
        return
    try:
        await create_brand_campaign(
            api_key,
            profile_id,
            _build_tcr_campaign(app),
            sandbox=os.environ.get("SENT_DM_PROVISION_SANDBOX", "0") == "1",
            idempotency_key=f"zilo-campaign-{profile_id}",
        )
        logger.info("[sms-provision] TCR campaign created profile=%s", profile_id)
    except Exception as e:
        logger.warning("[sms-provision] campaign create profile=%s: %s", profile_id, e)


async def submit_to_provider(user_id: str, app: Dict[str, Any]) -> Dict[str, Any]:
    """Create a Sent.dm sender profile from a CRM application. Never raises."""
    if not PLATFORM_API_KEY:
        logger.warning("[sms-provision] skipped user=%s — no platform API key", user_id)
        return {"ok": False, "reason": "platform_not_configured"}

    payload = build_profile_payload(app)
    try:
        data = await create_profile(
            PLATFORM_API_KEY,
            payload,
            idempotency_key=f"zilo-sms-{user_id}",
        )
        profile_id = data.get("id") or ""
        if not profile_id:
            return {"ok": False, "reason": "no_profile_id"}

        await _maybe_create_campaign(PLATFORM_API_KEY, profile_id, app)

        webhook_url = (os.environ.get("SENT_DM_PROFILE_WEBHOOK_URL") or "").strip()
        if webhook_url and os.environ.get("SENT_DM_AUTO_COMPLETE_PROFILE", "1") == "1":
            try:
                await complete_profile(
                    PLATFORM_API_KEY,
                    profile_id,
                    webhook_url=webhook_url,
                    sandbox=os.environ.get("SENT_DM_PROVISION_SANDBOX", "0") == "1",
                )
            except Exception as e:
                logger.warning("[sms-provision] complete profile user=%s: %s", user_id, e)

        return {
            "ok": True,
            "profile_id": profile_id,
            "sender_name": data.get("short_name") or payload["short_name"],
            "profile_status": data.get("status") or "incomplete",
            "region": resolve_region(app.get("business_country", "")),
        }
    except Exception as e:
        logger.exception("[sms-provision] create profile failed user=%s", user_id)
        return {"ok": False, "reason": str(e)[:500]}


async def sync_profile_activation(db, user_id: str, app: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Poll Sent.dm profile status; when ready, mark application active and update settings.
    Returns updated application doc or None.
    """
    profile_id = app.get("sentdm_profile_id") or ""
    if not profile_id or not PLATFORM_API_KEY:
        return None
    if app.get("status") == "active":
        return app

    try:
        profile = await get_profile(PLATFORM_API_KEY, profile_id)
    except Exception as e:
        logger.debug("[sms-provision] profile poll user=%s: %s", user_id, e)
        return None

    status = (profile.get("status") or "").lower()
    from_number = profile.get("sending_phone_number") or ""
    sender_name = profile.get("short_name") or app.get("sender_name") or ""

    update: Dict[str, Any] = {
        "profile_status": status,
        "sender_name": sender_name,
        "updated_at": app.get("updated_at"),
    }
    if from_number:
        update["from_number"] = from_number

    ready = status in ACTIVE_PROFILE_STATUSES or (
        status in ("submitted", "incomplete", "completed") and from_number
    )
    auto_activate = os.environ.get("SENT_DM_AUTO_ACTIVATE", "1") == "1"

    if ready and from_number and auto_activate:
        now = datetime.now(timezone.utc)
        update["status"] = "active"
        update["approved_at"] = now
        settings_patch = {
            "user_id": user_id,
            "provider": "platform",
            "sentdm_profile_id": profile_id,
            "sentdm_customer_id": profile.get("organization_id") or profile_id,
            "from_number": from_number,
            "sender_name": sender_name,
        }
        app_country = (app.get("business_country") or "").upper()
        if app_country:
            settings_patch["country_code"] = app_country
        default_tpl = (os.environ.get("SENT_DM_DEFAULT_TEMPLATE_ID") or "").strip()
        if default_tpl:
            settings_patch["default_template_id"] = default_tpl
        await db.sms_settings.update_one(
            {"user_id": user_id},
            {"$set": settings_patch},
            upsert=True,
        )
        logger.info("[sms-provision] activated user=%s profile=%s number=%s", user_id, profile_id, from_number)

    if update.get("profile_status"):
        await db.sms_applications.update_one(
            {"user_id": user_id},
            {"$set": {k: v for k, v in update.items() if v is not None and k != "updated_at"}},
        )
        merged = {**app, **update}
        return merged
    return None

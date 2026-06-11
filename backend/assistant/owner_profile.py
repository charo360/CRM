"""Unified tenant profile for assistant tools — Settings + Business Knowledge + brand."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _clean(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _nonempty_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None or v == "":
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
        elif isinstance(v, str) and v.strip():
            out[k] = v.strip()
        elif isinstance(v, (list, dict)) and v:
            out[k] = v
    return out


def merge_tenant_settings(user: Dict[str, Any]) -> Dict[str, Any]:
    """Mirror GET /api/settings — top-level user fields override nested settings."""
    s = user.get("settings") or {}
    if not isinstance(s, dict):
        s = {}
    return _nonempty_dict({
        "auto_reply_enabled": s.get("auto_reply_enabled"),
        "notification_enabled": s.get("notification_enabled"),
        "notification_time": s.get("notification_time"),
        "daily_alert_count": s.get("daily_alert_count"),
        "message_tone": s.get("message_tone"),
        "daily_pulse_enabled": s.get("daily_pulse_enabled"),
        "daily_pulse_time": s.get("daily_pulse_time"),
        "ai_model": s.get("ai_model"),
        "auto_reply_audience": s.get("auto_reply_audience"),
        "primary_language": s.get("primary_language"),
        "country": s.get("country"),
        "restaurant_has_reservations": s.get("restaurant_has_reservations"),
        "features": s.get("features"),
        "account_mode": s.get("account_mode"),
        "onboarding_v1_completed": s.get("onboarding_v1_completed"),
        "ga4_measurement_id": s.get("ga4_measurement_id"),
        "behavior_discounts_enabled": s.get("behavior_discounts_enabled"),
        "currency": _clean(user.get("currency") or s.get("currency")),
        "country_code": _clean(user.get("country_code") or s.get("country_code")),
        "business_type": _clean(s.get("business_type") or user.get("business_type")),
        "business_name": _clean(user.get("business_name") or s.get("business_name")),
        "owner_name": _clean(user.get("owner_name") or s.get("owner_name") or user.get("name")),
        "owner_title": _clean(user.get("owner_title") or s.get("owner_title")),
    })


def extract_business_knowledge(user: Dict[str, Any], *, max_field_len: int = 600) -> Dict[str, Any]:
    bk = user.get("business_knowledge") or {}
    if not isinstance(bk, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in bk.items():
        if v is None or v == "":
            continue
        if isinstance(v, str):
            text = v.strip()
            if not text:
                continue
            if len(text) > max_field_len:
                text = text[: max_field_len - 1] + "…"
            out[k] = text
        elif isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    return out


def normalize_payment_methods(user: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = user.get("payment_methods") or []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            name = _clean(item.get("name"))
            details = _clean(item.get("details"))
            if name or details:
                out.append({"name": name, "details": details})
        elif isinstance(item, str) and item.strip():
            out.append({"name": item.strip(), "details": ""})
    return out


def build_owner_profile(
    user: Dict[str, Any],
    *,
    default_logo_url: str = "",
    brand_primary_color: str = "",
    brand_font: str = "",
    document_style: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full profile for agents — flat keys for backward compatibility + nested blobs."""
    settings = merge_tenant_settings(user)
    bk = extract_business_knowledge(user)
    doc_style = _nonempty_dict(document_style or {})
    payment_methods = normalize_payment_methods(user)

    currency = _clean(
        user.get("currency") or settings.get("currency") or doc_style.get("currency")
    )
    country = _clean(settings.get("country") or bk.get("business_location"))
    country_code = _clean(user.get("country_code") or settings.get("country_code"))
    business_type = _clean(settings.get("business_type") or bk.get("business_type") or user.get("business_type"))
    business_name = _clean(user.get("business_name") or settings.get("business_name"))
    owner_name = _clean(user.get("owner_name") or settings.get("owner_name") or user.get("name"))
    owner_title = _clean(
        user.get("owner_title") or settings.get("owner_title") or doc_style.get("signature_title")
    )
    phone_number = _clean(
        user.get("phone_number") or settings.get("phone_number") or (user.get("whatsapp") or {}).get("number")
    )
    email = _clean(user.get("email"))
    website_url = _clean(
        bk.get("website_url")
        or user.get("website_url")
        or (user.get("settings") or {}).get("website_url")
        or bk.get("website")
    )
    if website_url:
        _host = (
            website_url.lower()
            .removeprefix("https://")
            .removeprefix("http://")
            .removeprefix("www.")
            .split("/")[0]
            .split("?")[0]
        )
        if _host in {"zilochat.com"}:
            website_url = ""
    tagline = _clean(doc_style.get("header_text") or bk.get("tagline"))
    business_description = _clean(bk.get("business_description"))
    products_services = _clean(bk.get("products_services"))
    pricing_info = _clean(bk.get("pricing_info"))

    return {
        # ── Flat fields (legacy tool consumers) ──
        "owner_name": owner_name,
        "owner_title": owner_title,
        "business_name": business_name,
        "phone_number": phone_number,
        "email": email,
        "country": country,
        "country_code": country_code,
        "currency": currency,
        "whatsapp_number": _clean((user.get("whatsapp") or {}).get("number")),
        "business_type": business_type,
        "website_url": website_url,
        "tagline": tagline,
        "business_location": _clean(bk.get("business_location")),
        "business_description": business_description,
        "products_services": products_services,
        "pricing_info": pricing_info,
        "business_description_hint": business_description[:400],
        "products_services_hint": products_services[:400],
        "primary_language": _clean(settings.get("primary_language")),
        "message_tone": _clean(settings.get("message_tone")),
        "default_logo_url": default_logo_url,
        "brand_primary_color": brand_primary_color,
        "brand_font": brand_font,
        # ── Nested — full Settings / Knowledge / document style ──
        "settings": settings,
        "business_knowledge": bk,
        "document_style": doc_style,
        "payment_methods": payment_methods,
    }

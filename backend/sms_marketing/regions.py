"""
Region-specific SMS application fields and validation.
Single source of truth for which form each country sees.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

EU_EEA_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "IS", "LI", "NO", "CH", "GB",
}

AFRICA_COUNTRIES = {
    "KE", "TZ", "UG", "NG", "GH", "ZA", "RW", "ET", "ZM", "ZW", "SN", "CI", "CM", "EG", "MA",
}

US_ENTITY_TYPES = [
    {"value": "PRIVATE_PROFIT", "label": "Private company"},
    {"value": "PUBLIC_PROFIT", "label": "Public company"},
    {"value": "NON_PROFIT", "label": "Non-profit"},
    {"value": "GOVERNMENT", "label": "Government"},
    {"value": "SOLE_PROPRIETOR", "label": "Sole proprietor"},
]

REGION_NOTICES = {
    "us": "US SMS requires carrier registration (10DLC/TCR). Provide accurate business and sample message details.",
    "ca": "Canadian law (CASL) requires documented consent before marketing SMS. Describe how customers opt in.",
    "eu": "EU rules require a lawful basis for SMS. Customers must be able to opt out (STOP). Privacy policy URL required.",
    "africa": "Provide your registered business details for local sender ID approval.",
    "international": "Provide accurate business details for SMS registration in your country.",
}

REGION_LABELS = {
    "us": "United States",
    "ca": "Canada",
    "eu": "European Union / EEA",
    "africa": "Africa",
    "international": "International",
}

# Settings may store full country name instead of ISO code
COUNTRY_NAME_TO_ISO = {
    "FINLAND": "FI", "CANADA": "CA", "UNITED STATES": "US", "UNITED STATES OF AMERICA": "US",
    "UNITED KINGDOM": "GB", "KENYA": "KE", "GERMANY": "DE", "FRANCE": "FR", "SWEDEN": "SE",
    "NORWAY": "NO", "DENMARK": "DK", "NETHERLANDS": "NL", "AUSTRALIA": "AU", "NEW ZEALAND": "NZ",
}


def normalize_country_iso(code_or_name: str) -> str:
    raw = (code_or_name or "").strip().upper()
    if len(raw) == 2:
        return raw
    return COUNTRY_NAME_TO_ISO.get(raw, "")


def resolve_region(country_code: str) -> str:
    cc = (country_code or "").strip().upper()
    if cc == "US":
        return "us"
    if cc == "CA":
        return "ca"
    if cc in EU_EEA_COUNTRIES:
        return "eu"
    if cc in AFRICA_COUNTRIES:
        return "africa"
    return "international"


def _field(
    key: str,
    label: str,
    *,
    field_type: str = "text",
    required: bool = False,
    placeholder: str = "",
    help_text: str = "",
    options: Optional[List[Dict[str, str]]] = None,
    rows: int = 3,
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "type": field_type,
        "required": required,
        "placeholder": placeholder,
        "helpText": help_text,
        "options": options or [],
        "rows": rows,
    }


CORE_FIELDS: List[Dict[str, Any]] = [
    _field("business_country", "Country", field_type="country", required=True),
    _field("business_name", "Business name", required=True),
    _field("sender_name", "Sender name (shown on SMS)", required=True,
           placeholder="3–11 characters", help_text="Letters and numbers — your brand name on outgoing SMS."),
    _field("legal_business_name", "Legal business name"),
    _field("contact_name", "Contact name", required=True),
    _field("contact_email", "Contact email", field_type="email", required=True),
    _field("contact_phone", "Contact phone", field_type="tel", required=True),
    _field("website", "Website", field_type="url", placeholder="https://"),
    _field("use_case", "How will you use SMS?", field_type="textarea", required=True,
           placeholder="Promotions, order updates, appointment reminders…", rows=3),
    _field("expected_volume", "Expected monthly volume", field_type="select", required=True, options=[
        {"value": "under_1k", "label": "Under 1,000"},
        {"value": "1k_10k", "label": "1,000 – 10,000"},
        {"value": "over_10k", "label": "Over 10,000"},
    ]),
    _field("business_street", "Street address", required=True),
    _field("business_city", "City", required=True),
    _field("business_state", "State / region"),
    _field("business_postal", "Postal code", required=True),
]

REGION_FIELDS: Dict[str, List[Dict[str, Any]]] = {
    "us": [
        _field("tax_id", "EIN / Tax ID", required=True, placeholder="12-3456789"),
        _field("entity_type", "Business type", field_type="select", required=True, options=US_ENTITY_TYPES),
        _field("message_flow", "How do customers opt in?", field_type="textarea", required=True,
               placeholder="e.g. Checkbox at checkout, keyword text-in, paper form…", rows=2),
        _field("sample_message_1", "Sample message 1", field_type="textarea", required=True,
               placeholder="Hi {name}, your order #{order_id} is ready for pickup.", rows=2),
        _field("sample_message_2", "Sample message 2", field_type="textarea", required=True,
               placeholder="Reply STOP to unsubscribe.", rows=2),
        _field("privacy_policy_url", "Privacy policy URL", field_type="url", required=True),
        _field("terms_url", "Terms & conditions URL", field_type="url", required=True),
    ],
    "ca": [
        _field("legal_business_name", "Legal business name", required=True),
        _field("consent_description", "How customers give consent (CASL)", field_type="textarea", required=True,
               placeholder="Describe opt-in: web form, in-store signup, existing customer relationship…", rows=3),
        _field("privacy_policy_url", "Privacy policy URL", field_type="url", required=True),
        _field("message_flow", "Opt-in process summary", field_type="textarea", required=True, rows=2),
    ],
    "eu": [
        _field("legal_business_name", "Legal business name", required=True),
        _field("privacy_policy_url", "Privacy policy URL", field_type="url", required=True,
               help_text="Must explain how you use SMS and how to opt out."),
        _field("gdpr_ack", "I confirm we only SMS customers with consent and honour opt-out requests",
               field_type="checkbox", required=True),
    ],
    "africa": [
        _field("business_registration_number", "Business registration number",
               help_text="If applicable in your country."),
    ],
    "international": [
        _field("privacy_policy_url", "Privacy policy URL", field_type="url"),
    ],
}


def _merge_fields(region: str) -> List[Dict[str, Any]]:
    """Merge core + regional fields; regional overrides win on duplicate keys."""
    by_key: Dict[str, Dict[str, Any]] = {}
    for f in CORE_FIELDS:
        by_key[f["key"]] = dict(f)
    for f in REGION_FIELDS.get(region, REGION_FIELDS["international"]):
        merged = dict(by_key.get(f["key"], {}))
        merged.update(f)
        by_key[f["key"]] = merged
    if region == "ca":
        by_key["legal_business_name"]["required"] = True
    if region == "eu":
        by_key["legal_business_name"]["required"] = True
    return list(by_key.values())


def get_application_schema(country_code: str) -> Dict[str, Any]:
    region = resolve_region(country_code)
    return {
        "country": (country_code or "").upper(),
        "region": region,
        "regionLabel": REGION_LABELS.get(region, "International"),
        "notice": REGION_NOTICES.get(region, REGION_NOTICES["international"]),
        "fields": _merge_fields(region),
    }


def validate_application(data: Dict[str, Any], country_code: str) -> List[str]:
    schema = get_application_schema(country_code)
    errors: List[str] = []
    for f in schema["fields"]:
        if f["key"] == "business_country":
            continue
        key = f["key"]
        val = data.get(key)
        if f["type"] == "checkbox":
            if f.get("required") and not val:
                errors.append(f"{f['label']} is required")
            continue
        if f.get("required") and not str(val or "").strip():
            errors.append(f"{f['label']} is required")
    if not str(data.get("sender_name") or "").strip():
        errors.append("Sender name is required")
    return errors


def region_compliance_flags(country_code: str) -> Dict[str, Any]:
    region = resolve_region(country_code)
    cc = (country_code or "").upper()
    return {
        "region": region,
        "is_tcr": region == "us",
        "requires_campaign": region == "us",
        "requires_privacy_url": region in ("us", "ca", "eu"),
    }

"""
Zilo AI Form Seeder — WPForms.

Generates industry-specific WPForms via Claude and creates them on the client's
WordPress subsite using the WPForms REST API (requires WPForms 1.7.7+ or WPForms
REST API add-on).  Falls back gracefully if WPForms API is unavailable.

Each industry gets purpose-built forms:
  tech/electronics  → Quote Request, Support Ticket
  salon/beauty      → Booking Form, Consultation Request
  restaurant/food   → Table Reservation, Catering Inquiry
  retail/fashion    → Size Guide Request, Custom Order
  consulting        → Discovery Call Request, Project Brief
  (default)         → Contact Us, Service Inquiry
"""
import base64
import json
import logging
import os
from typing import Any, Dict, List

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_claude: Anthropic | None = None


def _get_claude() -> Anthropic:
    global _claude
    if _claude is None:
        _claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _claude


def _wp_auth_header() -> str:
    user = os.getenv("WP_ADMIN_USER", "")
    pwd = os.getenv("WP_ADMIN_APP_PASSWORD", "")
    return base64.b64encode(f"{user}:{pwd}".encode()).decode()


def _wp_configured() -> bool:
    return bool(os.getenv("WP_ADMIN_USER") and os.getenv("WP_ADMIN_APP_PASSWORD"))


# ── Industry form definitions ──────────────────────────────────────────────────

INDUSTRY_FORMS: Dict[str, List[Dict[str, Any]]] = {
    "tech": [
        {
            "name": "Tech Quote Request",
            "fields": [
                {"label": "Your Name", "type": "name", "required": True},
                {"label": "Email Address", "type": "email", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Product / Service Interested In", "type": "text", "required": True},
                {"label": "Budget Range (KES)", "type": "select", "required": False,
                 "choices": ["Under 10,000", "10,000 – 30,000", "30,000 – 60,000", "60,000 – 100,000", "Above 100,000"]},
                {"label": "Additional Requirements", "type": "textarea", "required": False},
            ],
        },
        {
            "name": "Tech Support Ticket",
            "fields": [
                {"label": "Your Name", "type": "name", "required": True},
                {"label": "Email Address", "type": "email", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Device / Product", "type": "text", "required": True},
                {"label": "Issue Type", "type": "select", "required": True,
                 "choices": ["Hardware Problem", "Software Issue", "Network / Connectivity", "Screen / Display", "Battery", "Other"]},
                {"label": "Describe the Problem", "type": "textarea", "required": True},
                {"label": "Urgency", "type": "radio", "required": True,
                 "choices": ["Normal (3-5 days)", "Urgent (same day)", "Emergency (within 2 hours)"]},
            ],
        },
    ],
    "salon": [
        {
            "name": "Salon Appointment Booking",
            "fields": [
                {"label": "Full Name", "type": "name", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Email Address", "type": "email", "required": False},
                {"label": "Service Requested", "type": "select", "required": True,
                 "choices": ["Hair Braiding", "Relaxer / Perming", "Hair Cut & Style", "Weave Installation", "Nails", "Facial / Skincare", "Massage", "Other"]},
                {"label": "Preferred Date", "type": "date", "required": True},
                {"label": "Preferred Time", "type": "select", "required": True,
                 "choices": ["8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM", "12:00 PM", "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM"]},
                {"label": "Special Requests", "type": "textarea", "required": False},
            ],
        },
        {
            "name": "Hair Consultation Form",
            "fields": [
                {"label": "Full Name", "type": "name", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Hair Type", "type": "select", "required": True,
                 "choices": ["Natural / 4C", "Relaxed", "Transitioning", "Locs / Dreadlocks", "Low Cut / Fade", "Other"]},
                {"label": "Current Hair Concerns", "type": "checkbox", "required": False,
                 "choices": ["Hair Loss / Thinning", "Dry / Brittle Hair", "Dandruff", "Scalp Issues", "Colour Damage", "Heat Damage"]},
                {"label": "Desired Style / Look", "type": "textarea", "required": True},
                {"label": "Budget (KES)", "type": "select", "required": False,
                 "choices": ["Under 500", "500 – 1,500", "1,500 – 3,000", "Above 3,000"]},
            ],
        },
    ],
    "restaurant": [
        {
            "name": "Table Reservation",
            "fields": [
                {"label": "Full Name", "type": "name", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Email Address", "type": "email", "required": False},
                {"label": "Number of Guests", "type": "select", "required": True,
                 "choices": ["1 – 2", "3 – 5", "6 – 10", "11 – 20", "Above 20"]},
                {"label": "Date", "type": "date", "required": True},
                {"label": "Time", "type": "select", "required": True,
                 "choices": ["12:00 PM (Lunch)", "1:00 PM", "6:00 PM (Dinner)", "7:00 PM", "8:00 PM"]},
                {"label": "Special Occasion?", "type": "select", "required": False,
                 "choices": ["No", "Birthday", "Anniversary", "Business Lunch", "Other"]},
                {"label": "Dietary Requirements / Notes", "type": "textarea", "required": False},
            ],
        },
        {
            "name": "Catering Inquiry",
            "fields": [
                {"label": "Full Name", "type": "name", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Event Type", "type": "select", "required": True,
                 "choices": ["Wedding", "Corporate Event", "Birthday Party", "Graduation", "Funeral / Memorial", "Other"]},
                {"label": "Event Date", "type": "date", "required": True},
                {"label": "Number of Guests", "type": "text", "required": True},
                {"label": "Location / Venue", "type": "text", "required": True},
                {"label": "Menu Preferences", "type": "textarea", "required": False},
                {"label": "Budget Range (KES)", "type": "select", "required": False,
                 "choices": ["Under 20,000", "20,000 – 50,000", "50,000 – 100,000", "Above 100,000"]},
            ],
        },
    ],
    "retail": [
        {
            "name": "Custom Order Request",
            "fields": [
                {"label": "Full Name", "type": "name", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Email Address", "type": "email", "required": False},
                {"label": "Item / Product", "type": "text", "required": True},
                {"label": "Size", "type": "select", "required": False,
                 "choices": ["XS", "S", "M", "L", "XL", "XXL", "Custom Size"]},
                {"label": "Color Preference", "type": "text", "required": False},
                {"label": "Quantity", "type": "number", "required": True},
                {"label": "Additional Notes", "type": "textarea", "required": False},
            ],
        },
    ],
    "consulting": [
        {
            "name": "Discovery Call Request",
            "fields": [
                {"label": "Full Name", "type": "name", "required": True},
                {"label": "Business Name", "type": "text", "required": True},
                {"label": "Email Address", "type": "email", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Service Interested In", "type": "select", "required": True,
                 "choices": ["Business Strategy", "Marketing & Growth", "Financial Planning", "Operations", "HR / Team Building", "Other"]},
                {"label": "Current Challenge / Goal", "type": "textarea", "required": True},
                {"label": "Preferred Call Time", "type": "select", "required": True,
                 "choices": ["Morning (8 AM – 12 PM)", "Afternoon (12 PM – 5 PM)", "Evening (5 PM – 8 PM)"]},
                {"label": "How Did You Hear About Us?", "type": "select", "required": False,
                 "choices": ["Google", "WhatsApp", "Referral", "Social Media", "Other"]},
            ],
        },
    ],
    "hotel": [
        {
            "name": "Room Booking Inquiry",
            "fields": [
                {"label": "Full Name", "type": "name", "required": True},
                {"label": "Email Address", "type": "email", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "Check-in Date", "type": "date", "required": True},
                {"label": "Check-out Date", "type": "date", "required": True},
                {"label": "Room Type", "type": "select", "required": True,
                 "choices": ["Standard Room", "Deluxe Room", "Suite", "Family Room", "Conference Package"]},
                {"label": "Number of Guests", "type": "select", "required": True,
                 "choices": ["1", "2", "3", "4", "5+"]},
                {"label": "Special Requests", "type": "textarea", "required": False},
            ],
        },
    ],
    "real estate": [
        {
            "name": "Property Inquiry",
            "fields": [
                {"label": "Full Name", "type": "name", "required": True},
                {"label": "Email Address", "type": "email", "required": True},
                {"label": "Phone Number", "type": "phone", "required": True},
                {"label": "I Am Looking To", "type": "radio", "required": True,
                 "choices": ["Buy Property", "Rent / Lease", "Sell My Property", "Get a Valuation", "Property Management"]},
                {"label": "Property Type", "type": "select", "required": True,
                 "choices": ["1 Bedroom", "2 Bedroom", "3 Bedroom", "4+ Bedroom", "Studio", "Commercial", "Land"]},
                {"label": "Budget (KES)", "type": "text", "required": False},
                {"label": "Preferred Location", "type": "text", "required": False},
                {"label": "Additional Notes", "type": "textarea", "required": False},
            ],
        },
    ],
}

# Default forms for any industry not listed above
DEFAULT_FORMS = [
    {
        "name": "Contact Us",
        "fields": [
            {"label": "Full Name", "type": "name", "required": True},
            {"label": "Email Address", "type": "email", "required": True},
            {"label": "Phone Number", "type": "phone", "required": True},
            {"label": "Subject", "type": "text", "required": True},
            {"label": "Message", "type": "textarea", "required": True},
            {"label": "How Can We Help?", "type": "select", "required": False,
             "choices": ["General Inquiry", "Request a Quote", "Support", "Partnership", "Other"]},
        ],
    },
    {
        "name": "Service Inquiry",
        "fields": [
            {"label": "Full Name", "type": "name", "required": True},
            {"label": "Phone Number", "type": "phone", "required": True},
            {"label": "Email Address", "type": "email", "required": False},
            {"label": "Service Needed", "type": "textarea", "required": True},
            {"label": "Preferred Date", "type": "date", "required": False},
            {"label": "Budget (KES)", "type": "text", "required": False},
        ],
    },
]


def _get_forms_for_industry(industry: str) -> List[Dict[str, Any]]:
    industry_key = industry.lower()
    for key, forms in INDUSTRY_FORMS.items():
        if key in industry_key:
            return forms
    return DEFAULT_FORMS


# ── WPForms field type mapper ──────────────────────────────────────────────────

def _wpforms_field(idx: int, field: Dict[str, Any]) -> Dict[str, Any]:
    """Convert our simple field definition to the WPForms internal JSON format.

    WPForms Lite reads post_content as JSON when rendering [wpforms id="X"].
    Critical rules:
    - Field IDs must be strings matching the outer dict key.
    - 'name' type is a compound WPForms type that needs sub-format — use 'text' instead.
    - submit is NOT a field; it lives in settings.submit_text.
    - choices must be a dict keyed by string integers.
    """
    field_type = field["type"]
    # WPForms 'name' type renders as first/last sub-fields which require extra config.
    # A plain 'text' field is simpler and guaranteed to work with WPForms Lite.
    if field_type == "name":
        field_type = "text"

    base: Dict[str, Any] = {
        "id": str(idx),
        "type": field_type,
        "label": field["label"],
        "required": "1" if field.get("required") else "0",
        "size": "medium",
        "label_hide": "0",
        "sublabel_hide": "0",
        "placeholder": "",
    }
    if field_type in ("select", "radio", "checkbox") and "choices" in field:
        base["choices"] = {
            str(i): {"label": c, "value": c, "selected": "0"}
            for i, c in enumerate(field["choices"], 1)
        }
    return base


def _build_wpforms_payload(form_def: Dict[str, Any], business_name: str) -> Dict[str, Any]:
    # Build fields dict — submit button belongs in settings, NOT here
    fields = {str(i): _wpforms_field(i, f) for i, f in enumerate(form_def["fields"], 1)}
    return {
        "fields": fields,
        "settings": {
            "form_title": form_def["name"],
            "form_desc": "",
            "submit_text": "Send Message",
            "submit_text_processing": "Sending…",
            "ajax_submit": "1",
            "notification_enable": "1",
            "notifications": {
                "1": {
                    "notification_name": "Default Notification",
                    "enable": "1",
                    "email": "{admin_email}",
                    "subject": f"New {form_def['name']} from {business_name}",
                    "sender_name": business_name,
                    "sender_address": "{admin_email}",
                    "message": "{all_fields}",
                }
            },
            "confirmation_type": "message",
            "confirmation_message": "<p>Thank you! We've received your message and will get back to you shortly via WhatsApp or email.</p>",
        },
        "meta": {
            "template": "simple-contact-form-template",
        },
    }


# ── Push forms to WPForms REST API ─────────────────────────────────────────────

async def push_forms_to_wpforms(
    site_url: str,
    forms: List[Dict[str, Any]],
    business_name: str,
) -> Dict[str, Any]:
    if not _wp_configured():
        return {"pushed": 0, "reason": "WP credentials not configured"}

    auth = _wp_auth_header()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    pushed = 0
    errors = []

    async with httpx.AsyncClient(timeout=30) as client:
        for form_def in forms:
            payload = _build_wpforms_payload(form_def, business_name)
            try:
                resp = await client.post(
                    f"{site_url.rstrip('/')}/wp-json/wpforms/v1/forms",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code in (200, 201):
                    pushed += 1
                    logger.info(f"[form_seeder] Created form '{form_def['name']}' on {site_url}")
                else:
                    errors.append(f"{form_def['name']}: {resp.status_code}")
                    logger.warning(f"[form_seeder] Form create failed {resp.status_code}: {resp.text[:200]}")
            except Exception as exc:
                errors.append(f"{form_def['name']}: {exc}")
                logger.warning(f"[form_seeder] Form push error: {exc}")

    return {"pushed": pushed, "errors": errors}


# ── Main entry point ───────────────────────────────────────────────────────────

async def seed_forms(
    site_url: str,
    business_name: str,
    industry: str,
) -> Dict[str, Any]:
    """
    Selects industry-appropriate forms and pushes them to WPForms.
    Non-fatal — logs errors but never raises.
    """
    try:
        forms = _get_forms_for_industry(industry)
        result = await push_forms_to_wpforms(site_url, forms, business_name)
        logger.info(f"[form_seeder] Seeded {result.get('pushed', 0)} forms for {business_name}")
        return {"status": "ok", **result}
    except Exception as exc:
        logger.warning(f"[form_seeder] seed_forms failed: {exc}")
        return {"status": "error", "reason": str(exc), "pushed": 0}

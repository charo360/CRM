"""
sidebar_features.py
Sidebar feature catalog + contextual recommendations for the assistant.

Used when the user's goal requires a CRM module that is not enabled yet.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# feature_key → metadata (keep in sync with web/lib/sidebarFeatures.ts)
FEATURE_CATALOG: Dict[str, Dict[str, str]] = {
    "nav_messages": {"label": "Messages", "path": "/dashboard/messages", "group": "Main"},
    "nav_customers": {"label": "Customers / pipeline", "path": "/dashboard/customers", "group": "Main"},
    "nav_contacts": {"label": "Contacts", "path": "/dashboard/contacts", "group": "Main"},
    "nav_followups": {"label": "Follow-ups", "path": "/dashboard/followups", "group": "Main"},
    "nav_sales": {"label": "Sales", "path": "/dashboard/sales", "group": "Sales & revenue"},
    "nav_orders": {"label": "Orders", "path": "/dashboard/orders", "group": "Sales & revenue"},
    "nav_bookings": {"label": "Bookings", "path": "/dashboard/bookings", "group": "Sales & revenue"},
    "nav_invoices": {"label": "Invoices", "path": "/dashboard/invoices", "group": "Sales & revenue"},
    "nav_quotes": {"label": "Quotes", "path": "/dashboard/quotes", "group": "Sales & revenue"},
    "nav_finance": {"label": "Finance / P&L", "path": "/dashboard/finance", "group": "Sales & revenue"},
    "nav_broadcast": {"label": "Broadcast", "path": "/dashboard/broadcast", "group": "Sales & growth"},
    "nav_sms_marketing": {"label": "SMS Marketing", "path": "/dashboard/sms-marketing", "group": "Sales & growth"},
    "nav_ai_scout": {"label": "AI Scout", "path": "/dashboard/action-mode", "group": "Sales & growth"},
    "nav_behavior_tracker": {"label": "Behavior Tracker", "path": "/dashboard/marketing/behavior-discounts", "group": "Sales & growth"},
    "nav_social_scheduler": {"label": "Social scheduler", "path": "/dashboard/social-scheduler", "group": "Sales & growth"},
    "nav_meta_ads": {"label": "Meta Ads", "path": "/dashboard/meta-ads", "group": "Sales & growth"},
    "nav_google_ads": {"label": "Google Ads", "path": "/dashboard/google-ads", "group": "Sales & growth"},
    "nav_x_ads": {"label": "X Ads", "path": "/dashboard/x-ads", "group": "Sales & growth"},
    "nav_social_inbox": {"label": "Social Inbox", "path": "/dashboard/social-inbox", "group": "Sales & growth"},
    "nav_seo": {"label": "SEOhub", "path": "/dashboard/seo", "group": "Sales & growth"},
    "nav_whatsapp": {"label": "WhatsApp", "path": "/dashboard/whatsapp", "group": "Business"},
    "nav_field_agents": {"label": "Field Agents", "path": "/dashboard/field-agents", "group": "Business"},
    "nav_team": {"label": "Team", "path": "/dashboard/team", "group": "Business"},
    "nav_collaboration": {"label": "Collaboration", "path": "/dashboard/collaboration", "group": "Business"},
    "nav_analytics": {"label": "Analytics", "path": "/dashboard/analytics", "group": "Business"},
    "nav_inventory": {"label": "Inventory", "path": "/dashboard/inventory", "group": "Business"},
    "nav_loyalty": {"label": "Loyalty", "path": "/dashboard/loyalty", "group": "Business"},
    "nav_nps": {"label": "Feedback / NPS", "path": "/dashboard/nps", "group": "Business"},
    "nav_email": {"label": "Email Inbox", "path": "/dashboard/email", "group": "Productivity"},
    "nav_email_marketing": {"label": "Email Marketing", "path": "/dashboard/email-marketing", "group": "Productivity"},
    "nav_calendar": {"label": "Calendar", "path": "/dashboard/calendar", "group": "Productivity"},
    "nav_shopify": {"label": "Shopify", "path": "/dashboard/shopify", "group": "Productivity"},
    "nav_kds": {"label": "KDS display", "path": "/dashboard/kds", "group": "Display"},
}

# When user intent maps to a feature (keyword → feature keys to check)
INTENT_TO_FEATURES: Dict[str, List[str]] = {
    "sms": ["nav_sms_marketing"],
    "text message": ["nav_sms_marketing"],
    "broadcast": ["nav_broadcast"],
    "whatsapp promo": ["nav_broadcast", "nav_whatsapp"],
    "field rep": ["nav_field_agents"],
    "field agent": ["nav_field_agents"],
    "check-in": ["nav_field_agents"],
    "discount website": ["nav_behavior_tracker"],
    "cart abandon": ["nav_behavior_tracker"],
    "behavior track": ["nav_behavior_tracker"],
    "scout": ["nav_ai_scout"],
    "find leads": ["nav_ai_scout"],
    "social inbox": ["nav_social_inbox"],
    "dm": ["nav_social_inbox"],
    "schedule post": ["nav_social_scheduler"],
    "facebook ad": ["nav_meta_ads"],
    "instagram ad": ["nav_meta_ads"],
    "google ad": ["nav_google_ads"],
    "invoice": ["nav_invoices"],
    "quote": ["nav_quotes"],
    "loyalty": ["nav_loyalty"],
    "nps": ["nav_nps"],
    "feedback survey": ["nav_nps"],
    "email campaign": ["nav_email_marketing"],
    "seo": ["nav_seo"],
    "blog": ["nav_seo"],
    "inventory": ["nav_inventory"],
    "stock": ["nav_inventory"],
    "kitchen display": ["nav_kds"],
    "kds": ["nav_kds"],
    "booking": ["nav_bookings"],
    "reservation": ["nav_bookings"],
    "team member": ["nav_team"],
    "collaboration": ["nav_collaboration"],
}

# Priority picks by business type (for open-ended "what should I use?" — max 3-4)
RECOMMENDED_BY_TYPE: Dict[str, List[str]] = {
    "retail": ["nav_customers", "nav_whatsapp", "nav_broadcast", "nav_invoices", "nav_inventory"],
    "wholesale": ["nav_customers", "nav_orders", "nav_invoices", "nav_quotes", "nav_field_agents"],
    "restaurant": ["nav_orders", "nav_bookings", "nav_kds", "nav_whatsapp", "nav_broadcast"],
    "food": ["nav_orders", "nav_whatsapp", "nav_broadcast"],
    "bakery": ["nav_orders", "nav_bookings", "nav_whatsapp", "nav_broadcast"],
    "grocery": ["nav_orders", "nav_inventory", "nav_whatsapp", "nav_loyalty"],
    "hotel": ["nav_bookings", "nav_customers", "nav_invoices", "nav_followups"],
    "rental": ["nav_bookings", "nav_customers", "nav_invoices", "nav_quotes"],
    "salon": ["nav_bookings", "nav_customers", "nav_followups", "nav_whatsapp", "nav_broadcast"],
    "spa": ["nav_bookings", "nav_customers", "nav_followups", "nav_whatsapp"],
    "fitness": ["nav_bookings", "nav_customers", "nav_loyalty", "nav_broadcast"],
    "healthcare": ["nav_bookings", "nav_customers", "nav_followups", "nav_calendar"],
    "services": ["nav_quotes", "nav_invoices", "nav_followups", "nav_field_agents"],
    "repair": ["nav_orders", "nav_field_agents", "nav_quotes", "nav_whatsapp"],
    "cleaning": ["nav_field_agents", "nav_bookings", "nav_invoices", "nav_whatsapp"],
    "events": ["nav_quotes", "nav_invoices", "nav_calendar", "nav_social_scheduler"],
    "creator": ["nav_social_inbox", "nav_social_scheduler", "nav_broadcast", "nav_email_marketing"],
    "support": ["nav_messages", "nav_team", "nav_nps", "nav_followups"],
    "general": ["nav_customers", "nav_whatsapp", "nav_followups", "nav_analytics"],
}

FEATURES_PAGE = "/dashboard/features"

# After a tool succeeds, suggest enabling a sidebar module if still off (one nudge per tool).
POST_ACTION_NUDGES: Dict[str, Dict[str, str]] = {
    "create_scheduled_post": {
        "feature_key": "nav_social_scheduler",
        "reason": "You just saved a post — turn on **Social scheduler** to manage your content calendar from the sidebar.",
    },
    "generate_social_post": {
        "feature_key": "nav_social_scheduler",
        "reason": "Your post creative is ready — enable **Social scheduler** in Features to schedule and track posts from the sidebar.",
    },
    "generate_ad_creative": {
        "feature_key": "nav_social_scheduler",
        "reason": "Your creative is ready — **Social scheduler** lets you queue posts and plan your calendar from the sidebar.",
    },
    "create_broadcast": {
        "feature_key": "nav_broadcast",
        "reason": "To run WhatsApp campaigns from the sidebar anytime, turn on **Broadcast** under Features.",
    },
    "create_followup": {
        "feature_key": "nav_followups",
        "reason": "You set a follow-up — enable **Follow-ups** in Features to see and manage reminders in your sidebar.",
    },
    "create_customer": {
        "feature_key": "nav_customers",
        "reason": "You added a contact — turn on **Customers / pipeline** in Features for full CRM access in the sidebar.",
    },
}


def post_action_nudge(
    tool_name: str,
    tool_result: Any,
    features: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Return a single contextual nudge after a successful tool run, or None.
    Only when the related sidebar feature is not enabled yet.
    """
    if not isinstance(tool_result, dict) or tool_result.get("error"):
        return None
    if tool_result.get("success") is False:
        return None

    spec = POST_ACTION_NUDGES.get(tool_name)
    if not spec:
        return None

    key = spec["feature_key"]
    if _is_enabled(features, key):
        return None

    row = _feature_row(
        key,
        reason=spec["reason"],
        enabled=False,
    )
    if not row:
        return None

    row["trigger_tool"] = tool_name
    row["when_to_say"] = (
        "After confirming what you just did for the user, add ONE short sentence: "
        f"for ongoing access they should enable {row['label']} via Features (search → toggle). "
        "Do not pitch other modules."
    )
    return row


def enrich_tool_result_with_nudge(
    tool_name: str,
    tool_result: Any,
    features: Dict[str, Any],
) -> Any:
    """Attach `_feature_hint` to tool JSON the model sees after successful actions."""
    nudge = post_action_nudge(tool_name, tool_result, features)
    if not nudge or not isinstance(tool_result, dict):
        return tool_result
    out = dict(tool_result)
    out["_feature_hint"] = nudge
    return out


def _normalize_type(business_type: str) -> str:
    t = (business_type or "general").strip().lower()
    if t in RECOMMENDED_BY_TYPE:
        return t
    aliases = {
        "beauty": "salon",
        "ecommerce": "retail",
        "shop": "retail",
        "cafe": "restaurant",
        "hospitality": "hotel",
    }
    return aliases.get(t, "general")


def _is_enabled(features: Dict[str, Any], key: str) -> bool:
    return features.get(key) is True


def _feature_row(key: str, *, reason: str, enabled: bool) -> Optional[Dict[str, Any]]:
    meta = FEATURE_CATALOG.get(key)
    if not meta:
        return None
    return {
        "key": key,
        "label": meta["label"],
        "path": meta["path"],
        "group": meta["group"],
        "enabled": enabled,
        "reason": reason,
        "enable_instructions": (
            f"Go to **Features** ({FEATURES_PAGE}), search for \"{meta['label']}\", and turn the toggle on."
        ),
    }


def features_for_intent(user_message: str, features: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return disabled features required for the user's stated intent."""
    msg = (user_message or "").lower()
    matched_keys: List[str] = []
    for phrase, keys in INTENT_TO_FEATURES.items():
        if phrase in msg:
            for k in keys:
                if k not in matched_keys:
                    matched_keys.append(k)

    out: List[Dict[str, Any]] = []
    for key in matched_keys:
        if _is_enabled(features, key):
            continue
        meta = FEATURE_CATALOG.get(key, {})
        reason = f"You need **{meta.get('label', key)}** to do this in Zilo."
        row = _feature_row(key, reason=reason, enabled=False)
        if row:
            out.append(row)
    return out[:3]


def recommendations_for_business(
    business_type: str,
    features: Dict[str, Any],
    *,
    limit: int = 4,
) -> List[Dict[str, Any]]:
    """Suggest features commonly useful for this business type that are not enabled yet."""
    btype = _normalize_type(business_type)
    keys = RECOMMENDED_BY_TYPE.get(btype, RECOMMENDED_BY_TYPE["general"])
    out: List[Dict[str, Any]] = []
    for key in keys:
        if _is_enabled(features, key):
            continue
        meta = FEATURE_CATALOG.get(key, {})
        label = meta.get("label", key)
        reason = f"Common for {btype.replace('_', ' ')} businesses like yours — **{label}** helps with day-to-day work."
        row = _feature_row(key, reason=reason, enabled=False)
        if row:
            out.append(row)
        if len(out) >= limit:
            break
    return out


def build_feature_guidance(
    *,
    business_type: str,
    features: Dict[str, Any],
    user_intent: str = "",
    mode: str = "intent",
    limit: int = 3,
) -> Dict[str, Any]:
    """
    mode:
      - intent: features required for user_intent (task-specific)
      - profile: business-type suggestions (only when user asks what to enable)
    """
    enabled_count = sum(1 for k in FEATURE_CATALOG if _is_enabled(features, k))
    recommendations: List[Dict[str, Any]] = []

    if mode == "profile":
        recommendations = recommendations_for_business(business_type, features, limit=limit)
    elif mode == "intent" and user_intent.strip():
        recommendations = features_for_intent(user_intent, features)

    return {
        "business_type": _normalize_type(business_type),
        "features_page": FEATURES_PAGE,
        "enabled_sidebar_tools": enabled_count,
        "total_optional_tools": len(FEATURE_CATALOG),
        "recommendations": recommendations[:limit],
        "guidance_tone": (
            "Only mention a feature when the user's current goal requires it and it is disabled. "
            "Say what they need it for, then: go to Features, search the tool name, toggle on. "
            "Do not list unrelated tools or repeat after they decline."
        ),
    }

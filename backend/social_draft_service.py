"""Contextual social reply drafts — comments and DMs tailored to the recipient."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from personal_profile import (
    adapt_profile_for_platform,
    build_platform_comment_draft,
    load_personal_profile,
    normalize_social_platform,
    social_tone_hint,
    substitute_social_template,
)

logger = logging.getLogger(__name__)

_PLATFORM_CHAR_LIMITS = {
    "twitter": 280,
    "instagram": 500,
    "facebook": 800,
    "linkedin": 900,
    "tiktok": 300,
    "whatsapp": 1000,
}


def _first_name(name: str, fallback: str = "there") -> str:
    n = (name or "").strip().split()
    return n[0] if n else fallback


def _truncate(text: str, limit: int) -> str:
    t = (text or "").strip()
    if not t or len(t) <= limit:
        return t
    return t[: max(0, limit - 1)].rstrip() + "…"


def _detect_comment_intent(text: str) -> str:
    """Rough intent bucket for fallback templates."""
    low = (text or "").lower()
    if "?" in low or any(w in low for w in ("how", "what", "when", "where", "why", "can you", "do you")):
        return "question"
    if any(w in low for w in ("price", "cost", "how much", "quote", "budget", "rate", "fee")):
        return "pricing"
    if any(w in low for w in ("thank", "thanks", "appreciate", "grateful")):
        return "thanks"
    if any(w in low for w in ("love", "great", "awesome", "amazing", "beautiful", "nice")):
        return "praise"
    if any(w in low for w in ("bad", "worst", "terrible", "scam", "disappointed", "angry", "refund")):
        return "complaint"
    if any(w in low for w in ("dm", "message me", "inbox", "contact", "call", "whatsapp")):
        return "contact_request"
    return "general"


async def find_social_customer(
    db: Any,
    user_id: Any,
    platform: str,
    participant_id: str = "",
) -> Optional[dict]:
    pid = (participant_id or "").strip()
    if not pid:
        return None
    channel = normalize_social_platform(platform)
    phone = f"meta_{channel}_{pid}"
    return await db.customers.find_one({"user_id": user_id, "phone": phone})


async def _load_business_blocks(
    db: Any,
    user_id: Any,
    user: dict,
    customer_id: Any = None,
    their_message: str = "",
) -> tuple[dict, list, list, dict, list]:
    """Return (business_config, products, services, mini_state, messages)."""
    from autoreply.context_loader import load_context

    if customer_id:
        ctx = await load_context(db, user_id, customer_id, user, message=their_message)
        return (
            ctx["business_config"],
            ctx["products"],
            ctx["services"],
            ctx["mini_state"],
            ctx["messages"],
        )

    profile = await load_personal_profile(db, user_id)
    settings = user.get("settings") or {}
    bc = {
        "name": settings.get("business_name") or user.get("business_name") or "this business",
        "type": settings.get("business_type") or user.get("business_type") or "retail",
        "currency": settings.get("currency") or "KES",
        "about": settings.get("about") or "",
        "products_services": settings.get("products_services") or "",
        "business_location": settings.get("business_location") or "",
        "business_hours": settings.get("business_hours") or "",
        "delivery_info": settings.get("delivery_info") or "",
        "special_offers": settings.get("special_offers") or "",
        "payment_methods": settings.get("payment_methods") or [],
        "faqs": settings.get("faqs") or "",
        "owner_name": profile.get("name") or "",
        "owner_title": profile.get("title") or "",
    }
    return bc, [], [], {}, []


def _format_catalog_block(products: list, services: list, currency: str) -> str:
    lines: list[str] = []
    if products:
        lines.append("Products/menu:")
        for p in products[:12]:
            price = f"{currency} {p.get('price', 0):,.0f}"
            desc = f" — {str(p.get('description', ''))[:50]}" if p.get("description") else ""
            lines.append(f"  • {p.get('name')} — {price}{desc}")
    if services:
        lines.append("Services:")
        for s in services[:8]:
            lines.append(f"  • {s.get('name')} — {currency} {s.get('price', 0):,.0f}")
    return "\n".join(lines)


def _format_customer_meta(customer: Optional[dict], currency: str) -> str:
    if not customer:
        return ""
    parts: list[str] = []
    if customer.get("tags"):
        parts.append(f"Tags: {', '.join(customer['tags'][:5])}")
    if customer.get("notes"):
        parts.append(f"Notes: {str(customer['notes'])[:120]}")
    if customer.get("total_spent"):
        parts.append(f"Lifetime value: {currency} {customer['total_spent']:,.0f}")
    return " | ".join(parts)


def _format_history(
    messages: list,
    *,
    inline_history: Optional[List[Dict[str, str]]] = None,
    recipient_name: str = "",
) -> str:
    lines: list[str] = []
    if inline_history:
        for m in inline_history[-10:]:
            role = m.get("role") or ("customer" if m.get("direction") in ("in", "incoming") else "you")
            label = recipient_name if role in ("customer", "them", "in", "incoming") else "You"
            content = (m.get("content") or m.get("text") or "").strip()
            if content:
                lines.append(f"{label}: {content[:400]}")
    elif messages:
        for m in messages[-10:]:
            role = "Customer" if m.get("role") == "customer" else "You"
            content = (m.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content[:400]}")
    return "\n".join(lines) if lines else ""


def _build_prompt(
    *,
    channel: str,
    platform: str,
    recipient_name: str,
    their_message: str,
    post_caption: str,
    profile: dict,
    bc: dict,
    products: list,
    services: list,
    customer: Optional[dict],
    history_text: str,
    custom_instructions: str,
    regenerate_count: int,
) -> str:
    p = normalize_social_platform(platform)
    adapted = adapt_profile_for_platform(profile, p)
    recipient_first = _first_name(recipient_name)
    currency = bc.get("currency") or "KES"
    business_name = bc.get("name") or "this business"
    sender_intro = adapted.get("sender_intro") or adapted.get("name") or business_name
    char_limit = _PLATFORM_CHAR_LIMITS.get(p, 600)

    bc_lines: list[str] = []
    for key, label in (
        ("about", "About"),
        ("products_services", "What we offer"),
        ("business_location", "Location"),
        ("business_hours", "Hours"),
        ("delivery_info", "Delivery"),
        ("special_offers", "Offers"),
        ("faqs", "FAQs"),
    ):
        val = (bc.get(key) or "").strip()
        if val:
            bc_lines.append(f"{label}: {val[:200]}")
    if bc.get("payment_methods"):
        pm = ", ".join(str(x) for x in bc["payment_methods"][:3])
        bc_lines.append(f"Payment: {pm}")

    catalog = _format_catalog_block(products, services, currency)
    customer_meta = _format_customer_meta(customer, currency)
    tone = social_tone_hint(p)

    channel_label = "public comment" if channel == "comment" else "direct message"
    post_block = ""
    if post_caption.strip() and channel == "comment":
        post_block = f'\nYOUR POST they commented on:\n"{post_caption.strip()[:500]}"\n'

    history_block = ""
    if history_text.strip():
        history_block = f"\nCONVERSATION SO FAR:\n{history_text.strip()}\n"

    customer_block = f"Recipient: {recipient_name or recipient_first}"
    if customer_meta:
        customer_block += f" ({customer_meta})"

    intent = _detect_comment_intent(their_message)
    intent_note = ""
    if intent == "question":
        intent_note = "They asked a question — answer it directly with specifics from your business info."
    elif intent == "pricing":
        intent_note = "They asked about price — mention real products/services and prices when available, or invite them to DM for a quote."
    elif intent == "complaint":
        intent_note = "They seem unhappy — acknowledge their concern empathetically and offer to help resolve it."
    elif intent == "thanks":
        intent_note = "They are thanking you — respond warmly and briefly."
    elif intent == "praise":
        intent_note = "They gave positive feedback — thank them genuinely without being over the top."

    variety = [
        "Lead with a direct answer to their exact words.",
        "Reference something specific from their message before your reply.",
        "Keep it ultra-short — one crisp sentence if possible.",
        "Be warm and personal — show you read what they wrote.",
    ]
    variety_note = variety[regenerate_count % len(variety)]

    direction = f"\nEXTRA DIRECTION: {custom_instructions.strip()}\n" if custom_instructions.strip() else ""

    return f"""Write a {channel_label} reply on {p or 'social media'}.

You are {sender_intro}, replying on behalf of {business_name}.
{customer_block}
{tone}
{post_block}
THEIR MESSAGE (respond to THIS — do not give a generic reply):
"{(their_message or '').strip()[:800]}"
{history_block}
{intent_note}

BUSINESS INFO (only use facts listed here — never invent prices or promises):
{chr(10).join(bc_lines) if bc_lines else f"Business: {business_name}"}
{catalog if catalog else ""}
{direction}
RULES:
1. Output ONLY the reply text — no labels, quotes, or explanation.
2. Address {recipient_first} by first name when natural.
3. Directly respond to what they said — reference their topic, question, or concern.
4. Use real product/service names and prices from the catalog when relevant.
5. Match {p} tone — no email sign-offs like "Best regards" or signature blocks.
6. Stay under {char_limit} characters.
7. BANNED: "Thanks for your comment", "We have seen it", "Feel free to reach out", "Don't hesitate", generic templates.
8. VARIETY: {variety_note}

Reply:"""


async def draft_social_reply(
    db: Any,
    user: dict,
    *,
    platform: str = "",
    channel: str = "comment",
    recipient_name: str = "",
    their_message: str = "",
    post_caption: str = "",
    customer_id: Any = None,
    participant_id: str = "",
    conversation_history: Optional[List[Dict[str, str]]] = None,
    custom_instructions: str = "",
    regenerate_count: int = 0,
    use_ai: bool = True,
) -> dict:
    """
    Generate a contextual social reply.

    Returns {"message", "confidence", "reason", "source": "ai"|"template"}.
    """
    user_id = user.get("business_id") or user["_id"]
    profile = await load_personal_profile(db, user_id)

    customer = None
    if customer_id:
        customer = await db.customers.find_one({"_id": customer_id, "user_id": user_id})
    elif participant_id:
        customer = await find_social_customer(db, user_id, platform, participant_id)

    cid = customer["_id"] if customer else customer_id
    bc, products, services, mini_state, ctx_messages = await _load_business_blocks(
        db, user_id, user, cid, their_message=their_message
    )

    history_text = _format_history(
        ctx_messages,
        inline_history=conversation_history,
        recipient_name=recipient_name,
    )

    recipient_first = _first_name(recipient_name)
    p = normalize_social_platform(platform)
    char_limit = _PLATFORM_CHAR_LIMITS.get(p, 600)

    fallback = build_platform_comment_draft(p, recipient_first, their_message or "")
    fallback = substitute_social_template(
        fallback, profile, recipient_first_name=recipient_first, platform=p
    )
    fallback = _truncate(fallback, char_limit)

    if not use_ai:
        return {
            "message": fallback,
            "confidence": 0.6,
            "reason": "Template reply (AI disabled)",
            "source": "template",
        }

    if not (their_message or "").strip() and not history_text.strip():
        return {
            "message": fallback,
            "confidence": 0.5,
            "reason": "No message to respond to",
            "source": "template",
        }

    prompt = _build_prompt(
        channel=channel,
        platform=p,
        recipient_name=recipient_name,
        their_message=their_message,
        post_caption=post_caption,
        profile=profile,
        bc=bc,
        products=products,
        services=services,
        customer=customer,
        history_text=history_text,
        custom_instructions=custom_instructions,
        regenerate_count=regenerate_count,
    )

    model_pref = (user.get("settings") or {}).get("ai_model", "standard") or "standard"
    drafted = ""
    try:
        from ai_service import get_drafter

        drafted = await get_drafter()._call_llm(prompt, model_pref=model_pref)
        drafted = (drafted or "").strip().strip('"').strip("'")
        drafted = re.sub(r"^(reply|message):\s*", "", drafted, flags=re.I).strip()
    except Exception as exc:
        logger.warning("[SocialDraft] LLM failed: %s", exc)

    if not drafted:
        return {
            "message": fallback,
            "confidence": 0.55,
            "reason": "AI unavailable — used smart template",
            "source": "template",
        }

    drafted = substitute_social_template(
        drafted, profile, recipient_first_name=recipient_first, platform=p
    )
    drafted = _truncate(drafted, char_limit)

    reason = f"Replying to {recipient_first}"
    if their_message:
        preview = their_message.strip()[:60]
        reason = f'Re: "{preview}{"..." if len(their_message) > 60 else ""}"'

    return {
        "message": drafted,
        "confidence": 0.88,
        "reason": reason,
        "source": "ai",
    }

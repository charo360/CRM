"""Personal profile helpers for outbound email / draft signatures."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

_PLACEHOLDER_RE = re.compile(
    r"\[(?:Your Name|Your Position|Your Company|Phone/Email)\]",
    re.I,
)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def personal_profile_from_user(
    user: Optional[Dict[str, Any]],
    *,
    document_style: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Build name / title / company from user doc (+ optional document style fallbacks)."""
    user = user or {}
    settings = user.get("settings") if isinstance(user.get("settings"), dict) else {}
    doc_style = document_style if isinstance(document_style, dict) else {}

    name = _clean(
        user.get("owner_name")
        or settings.get("owner_name")
        or user.get("name")
    )
    title = _clean(
        user.get("owner_title")
        or settings.get("owner_title")
        or doc_style.get("signature_title")
    )
    company = _clean(
        user.get("business_name")
        or settings.get("business_name")
    )
    contact = _clean(doc_style.get("signature_contact"))
    if not contact:
        bits = [_clean(user.get("email")), _clean(user.get("phone_number"))]
        contact = " | ".join(b for b in bits if b)

    return {
        "name": name,
        "title": title,
        "company": company,
        "contact": contact,
    }


def append_signature_from_user(user: Optional[Dict[str, Any]]) -> bool:
    """Whether to auto-append sign-off lines after closings like 'Best,'."""
    if not user:
        return True
    settings = user.get("settings") if isinstance(user.get("settings"), dict) else {}
    return settings.get("append_signature_to_drafts", True) is not False


_SOCIAL_VAR_MAP = (
    ("{your_name}", "name"),
    ("{owner_name}", "name"),
    ("{sender_name}", "name"),
    ("{your_first_name}", "first_name"),
    ("{sender_first_name}", "first_name"),
    ("{your_title}", "title"),
    ("{owner_title}", "title"),
    ("{your_position}", "title"),
    ("{your_company}", "company"),
    ("{business_name}", "company"),
    ("{sender_intro}", "sender_intro"),
)


def normalize_social_platform(platform: str) -> str:
    """Normalize platform slug for tone / identity rules."""
    p = (platform or "").strip().lower()
    if p in {"x", "twitter/x"}:
        return "twitter"
    if p in {"fb", "meta"}:
        return "facebook"
    if p in {"ig"}:
        return "instagram"
    if p in {"li"}:
        return "linkedin"
    if p in {"gmail", "outlook", "email"}:
        return "email"
    return p or "default"


def adapt_profile_for_platform(profile: Dict[str, str], platform: str = "") -> Dict[str, str]:
    """Adapt name/title/company presentation to each social channel."""
    p = normalize_social_platform(platform)
    full_name = _clean(profile.get("name"))
    title = _clean(profile.get("title"))
    company = _clean(profile.get("company"))
    first = full_name.split()[0] if full_name else ""

    adapted_name = full_name
    adapted_title = title
    adapted_company = company
    sender_intro = full_name or company

    if p == "linkedin":
        bits = [full_name]
        if title and company:
            bits.append(f"{title} at {company}")
        elif title:
            bits.append(title)
        elif company:
            bits.append(company)
        sender_intro = ", ".join(b for b in bits if b)
    elif p == "twitter":
        adapted_name = first or full_name
        adapted_title = ""
        sender_intro = first or full_name or company
    elif p in {"instagram", "facebook", "messenger", "tiktok", "whatsapp"}:
        adapted_name = first or full_name
        adapted_title = ""
        if first and company:
            sender_intro = f"{first} from {company}"
        else:
            sender_intro = first or full_name or company
    elif p == "email":
        parts_sig = [x for x in (full_name, title, company) if x]
        sender_intro = " · ".join(parts_sig) if parts_sig else full_name or company
    else:
        if full_name and company:
            sender_intro = f"{full_name} ({company})"
        elif full_name:
            sender_intro = full_name

    return {
        **profile,
        "name": adapted_name or full_name,
        "title": adapted_title,
        "company": adapted_company,
        "first_name": first,
        "full_name": full_name,
        "sender_intro": sender_intro,
    }


def substitute_social_template(
    text: str,
    profile: Dict[str, str],
    *,
    recipient_first_name: str = "",
    platform: str = "",
) -> str:
    """Fill social reply templates — recipient {name} plus platform-adapted sender vars."""
    out = (text or "").strip()
    if not out:
        return out

    adapted = adapt_profile_for_platform(profile, platform)
    first = (recipient_first_name or "").strip().split(" ")[0]
    out = out.replace("{name}", first or "there")

    replacements = {
        "[Your Name]": _clean(adapted.get("name")) or _clean(adapted.get("full_name")) or "[Your Name]",
        "[Your Position]": _clean(adapted.get("title")) or "[Your Position]",
        "[Your Company]": _clean(adapted.get("company")) or "[Your Company]",
    }
    for placeholder, value in replacements.items():
        out = out.replace(placeholder, value)

    extra = {
        "{sender_intro}": _clean(adapted.get("sender_intro")),
        "{your_first_name}": _clean(adapted.get("first_name")),
        "{sender_first_name}": _clean(adapted.get("first_name")),
        "{full_name}": _clean(adapted.get("full_name")),
    }
    for token, val in extra.items():
        if val:
            out = out.replace(token, val)

    for token, key in _SOCIAL_VAR_MAP:
        if token in extra:
            continue
        val = _clean(adapted.get(key))
        if val:
            out = out.replace(token, val)

    return out


def sender_display_name(profile: Dict[str, str], platform: str = "") -> str:
    """Label for outbound messages in the social inbox UI."""
    adapted = adapt_profile_for_platform(profile, platform)
    return (
        _clean(adapted.get("name"))
        or _clean(adapted.get("full_name"))
        or _clean(adapted.get("company"))
        or "You"
    )


def social_tone_hint(platform: str) -> str:
    """Short LLM hint for autoreply tone on this channel."""
    p = normalize_social_platform(platform)
    hints = {
        "linkedin": (
            "CHANNEL: LinkedIn — professional B2B tone. You may use full name and title when introducing yourself. "
            "No emoji overload. No email-style sign-offs."
        ),
        "instagram": (
            "CHANNEL: Instagram DM — casual and warm. Refer to yourself by first name only. "
            "Keep replies short. No formal 'Best regards' blocks."
        ),
        "facebook": (
            "CHANNEL: Facebook/Messenger — friendly and conversational. First name is enough for self-reference. "
            "Short replies, no email signatures."
        ),
        "twitter": (
            "CHANNEL: X/Twitter — very brief and direct. First name only if needed. Stay under ~280 characters when possible."
        ),
        "tiktok": (
            "CHANNEL: TikTok — casual, upbeat, short. First name only. Match a younger social tone without slang overload."
        ),
        "whatsapp": (
            "CHANNEL: WhatsApp — text like a real person: warm, concise, first name if needed. No corporate email closings."
        ),
    }
    return hints.get(p, "")


def _comment_intent(text: str) -> str:
    low = (text or "").lower()
    if "?" in low or any(w in low for w in ("how", "what", "when", "where", "why", "can you", "do you")):
        return "question"
    if any(w in low for w in ("price", "cost", "how much", "quote", "budget", "rate")):
        return "pricing"
    if any(w in low for w in ("thank", "thanks", "appreciate")):
        return "thanks"
    if any(w in low for w in ("bad", "worst", "terrible", "disappointed", "refund", "scam")):
        return "complaint"
    if any(w in low for w in ("love", "great", "awesome", "amazing", "beautiful")):
        return "praise"
    return "general"


def build_platform_comment_draft(platform: str, author_first: str, comment_text: str) -> str:
    """Platform-aware default comment reply before template substitution."""
    author = (author_first or "there").strip() or "there"
    raw = (comment_text or "").strip()
    text = raw.lower()
    p = normalize_social_platform(platform)
    intent = _comment_intent(raw)
    snippet = raw[:80].rstrip()
    if len(raw) > 80:
        snippet += "…"

    if p == "linkedin":
        if intent == "complaint":
            return f"Hi {author}, sorry to hear that — I want to make this right. Message me directly and we will sort it out."
        if intent == "question":
            return f"Hi {author}, good question about \"{snippet}\" — message me and I will share the details."
        if intent == "pricing":
            return f"Hi {author}, happy to share pricing for what you need. Send me a DM with specifics and I will reply with options."
        if intent == "thanks":
            return f"You are welcome, {author} — glad I could help."
        if intent == "praise":
            return f"Thank you, {author} — really appreciate you saying that."
        return f"Hi {author}, thanks for your comment on this. I will follow up with you shortly."

    if intent == "complaint":
        return f"Hi {author}, sorry about that — we want to fix this. DM us and we will help you personally."
    if intent == "question":
        return f"Hi {author}, great question! DM us with a bit more detail on \"{snippet}\" and we will help right away."
    if intent == "pricing":
        return f"Hi {author}, thanks for asking! DM us what you are looking for and we will share price and options."
    if intent == "thanks":
        return f"You are welcome {author} — we appreciate you!"
    if intent == "praise":
        return f"Thank you {author} — that means a lot to us!"
    if snippet:
        return f"Hi {author}, thanks for commenting — we saw your note about \"{snippet}\" and will get back to you soon."
    return f"Hi {author}, thanks for your comment! We will get back to you soon."


async def load_personal_profile(db: Any, user_id: Any) -> Dict[str, str]:
    """Load personal profile for a tenant from Mongo."""
    user = await db.users.find_one({"_id": user_id}) or {}
    doc_style: Dict[str, Any] = {}
    try:
        from saved_designs import get_document_style

        doc_style = await get_document_style(db, str(user_id))
    except Exception:
        pass
    return personal_profile_from_user(user, document_style=doc_style)


def build_email_signature_lines(profile: Dict[str, str]) -> list[str]:
    lines: list[str] = []
    for key in ("name", "title", "company"):
        val = _clean(profile.get(key))
        if val:
            lines.append(val)
    return lines


def format_email_closing(profile: Dict[str, str], closing: str = "Best") -> str:
    """Standard multi-line sign-off block."""
    lines = [f"{closing.strip() or 'Best'},"]
    lines.extend(build_email_signature_lines(profile))
    return "\n".join(lines)


_CLOSING_LINE_RE = re.compile(
    r"(?i)^\s*(best|best regards|kind regards|regards|thanks|thank you|sincerely|cheers),?\s*$"
)


def has_existing_signature(text: str, profile: Dict[str, str]) -> bool:
    """True when the body already ends with a name/title/company sign-off block."""
    lines = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return False

    name = _clean(profile.get("name")).lower()
    title = _clean(profile.get("title")).lower()
    company = _clean(profile.get("company")).lower()
    tail = lines[-6:]
    tail_lower = [ln.lower() for ln in tail]

    if name and any(name in ln for ln in tail_lower):
        return True
    if title and company:
        has_title = any(title in ln for ln in tail_lower)
        has_company = any(company in ln for ln in tail_lower)
        if has_title and has_company:
            return True

    # Closing line (Best, etc.) followed by at least one trailing line → treat as signed.
    for i, ln in enumerate(tail):
        if _CLOSING_LINE_RE.match(ln):
            trailing = tail[i + 1 :]
            if trailing and any(len(t) > 2 for t in trailing):
                return True
    return False


def apply_personal_signature(
    body: str,
    profile: Dict[str, str],
    *,
    append_if_missing: bool = True,
) -> str:
    """Replace signature placeholders; optionally append profile sign-off when missing."""
    text = (body or "").strip()
    if not text:
        return text

    replacements = {
        "[Your Name]": _clean(profile.get("name")) or "[Your Name]",
        "[Your Position]": _clean(profile.get("title")) or "[Your Position]",
        "[Your Company]": _clean(profile.get("company")) or "[Your Company]",
        "[Phone/Email]": _clean(profile.get("contact")) or "[Phone/Email]",
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)

    if not append_if_missing or has_existing_signature(text, profile):
        return text

    # LLM left a bare "Best," with no signature lines — append configured lines.
    sig_lines = build_email_signature_lines(profile)
    if sig_lines and not _PLACEHOLDER_RE.search(text):
        tail = text.rstrip()
        if re.search(r"(?i)\b(best|best regards|kind regards|regards|thanks|thank you),?\s*$", tail):
            text = tail + "\n" + "\n".join(sig_lines)

    return text

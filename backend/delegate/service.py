"""Delegate service — interpretation, execution, and scheduling helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from personal_profile import (
    apply_personal_signature,
    append_signature_from_user,
    load_personal_profile,
    personal_profile_from_user,
)

logger = logging.getLogger(__name__)

from .outbound import reply_channel_from_contact, send_delegate_message

COLLECTION = "delegations"
COLD_DAYS_DEFAULT = 14
# Cap how many contacts a single delegation will work through.
MAX_CONTACTS = 50
# Delay between staged drafts so the founder sees live progress.
_STEP_DELAY_SECONDS = float(os.environ.get("DELEGATE_STEP_DELAY", "1.5"))
# Max LLM regenerations per draft before approve (matches Decision Room).
MAX_DRAFT_REGENERATIONS = 3


# ── LLM helper ────────────────────────────────────────────────────────────

async def _call_llm_json(system: str, prompt: str, *, max_tokens: int = 500) -> dict | None:
    provider = os.environ.get("AI_PROVIDER", "openai").strip().lower()
    try:
        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                return None
            import anthropic  # type: ignore

            client = anthropic.AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text if resp.content else ""
        else:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                return None
            import openai as _openai  # type: ignore

            client = _openai.AsyncOpenAI(api_key=api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=max_tokens,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content or ""
        raw = (raw or "").strip()
        if not raw:
            return None
        # Strip code fences if present.
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
        return json.loads(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] LLM interpret failed: %s", e)
        return None


async def _call_llm_text(system: str, prompt: str, *, max_tokens: int = 280) -> str | None:
    provider = os.environ.get("AI_PROVIDER", "openai").strip().lower()
    try:
        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                return None
            import anthropic  # type: ignore

            client = anthropic.AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.content[0].text if resp.content else "") or None

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        import openai as _openai  # type: ignore

        client = _openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=max_tokens,
            temperature=0.35,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or None
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] LLM text failed: %s", e)
        return None


_DRAFT_SYSTEM = (
    "You are Zilo, drafting work for a founder to approve before anything sends. "
    "Write plain text only. Keep follow-ups to 2–4 sentences. "
    "For leads: write about exactly ONE real company or person named in TARGET — "
    "who they are, why they fit, and one suggested opener. "
    "For email replies: write Subject: Re: ... then the email body. Reply to the "
    "specific incoming message in CONTEXT — never meta text like 'I reviewed your emails' "
    "or 'here are drafts for approval'. "
    "NEVER list multiple people. NEVER invent fictional contacts. "
    "NEVER write numbered lists. No preamble like 'here are five leads'. "
    "End emails with a real sign-off using SENDER PROFILE (name, title, company) — "
    "never use placeholders like [Your Name], [Your Position], or [Your Company]."
)


def _parse_target_count(task: str, default: int = 10) -> int:
    m = re.search(r"\b(\d{1,2})\b", task or "")
    if m:
        return max(1, min(50, int(m.group(1))))
    return default


_GENERIC_LEAD_TITLE_RE = re.compile(
    r"zilo|sell on every|web workspace|looking for|american looking|user [a-z0-9]{4,}",
    re.I,
)

# Titles/URLs that represent a source thread or listing — never one CRM contact.
_MULTI_ENTITY_SOURCE_RE = re.compile(
    r"reddit:|google play|apps on|play\.google|store/apps|built a |wondering if|"
    r"on reddit|thread|posted by|@\w+",
    re.I,
)


def _is_generic_lead_title(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    if len(s) > 72:
        return True
    return bool(_GENERIC_LEAD_TITLE_RE.search(s))


def _is_multi_entity_source(label: str, parent: str = "", url: str = "") -> bool:
    blob = f"{label} {parent} {url}"
    return bool(_MULTI_ENTITY_SOURCE_RE.search(blob)) or _is_generic_lead_title(label)


def _name_from_lead_block(block: str, fallback: str) -> str:
    block = (block or "").strip()
    m = re.match(
        r"^\d+[\.\)]\s*(\*{0,2})([A-Za-z][A-Za-z0-9\s&.'-]{1,55}?)(\*{0,2})\s*[:\-—–]",
        block,
    )
    if m:
        return m.group(2).strip()
    m = re.match(r"^(u/[A-Za-z0-9_]+)", block)
    if m:
        return m.group(1)
    return _company_name_from_text(block, fallback)


def _is_intro_only_draft(draft: str) -> bool:
    low = (draft or "").lower()
    if re.search(r"here are \d+ leads", low):
        return True
    if re.search(r"each contact has been chosen", low) and not re.search(r"suggested opener", low, re.I):
        return True
    return len((draft or "").strip()) < 40


def _lead_label_from_opportunity(o: dict[str, Any]) -> str:
    """Pick a human company/person name — not a post title or marketing line."""
    for key in ("company", "author", "name"):
        val = (o.get(key) or "").strip()
        if val and not _is_generic_lead_title(val):
            return val[:120]
    title = (o.get("title") or "").strip()
    if title and not _is_generic_lead_title(title):
        return title[:120]
    snippet = (o.get("snippet") or o.get("description") or "").strip()
    from_snip = _company_name_from_text(snippet, "")
    if from_snip and not _is_generic_lead_title(from_snip):
        return from_snip[:120]
    oid = str(o.get("_id") or "")
    return f"Lead {oid[:8]}" if oid else "Lead"


def _company_name_from_text(text: str, fallback: str) -> str:
    """Extract the primary company/person name from draft or snippet text."""
    raw = (text or "").strip()
    if not raw:
        return fallback if not _is_generic_lead_title(fallback) else "Lead"

    skip = {"why", "suggested", "source", "hi", "hello", "context", "draft", "lead", "notes"}
    for m in re.finditer(r"(?:^|\n)\s*([A-Z][A-Za-z0-9][A-Za-z0-9\s&.'-]{1,45}?)\s*:\s", raw):
        name = m.group(1).strip()
        if name.lower() not in skip and not _is_generic_lead_title(name):
            return name

    first_line = re.sub(r"[*#]+", "", raw.splitlines()[0]).strip()
    first_line = re.sub(r"^(who they are|target|company)\s*:\s*", "", first_line, flags=re.I).strip()
    m = re.match(r"^([A-Z][A-Za-z0-9][A-Za-z0-9\s&.'-]{1,45}?)(?:\s*[—–\-:,]|\s*$)", first_line)
    if m:
        name = m.group(1).strip()
        if name.lower() not in skip and not _is_generic_lead_title(name):
            return name

    if first_line and not _is_generic_lead_title(first_line) and len(first_line) < 50:
        return first_line

    return fallback if not _is_generic_lead_title(fallback) else "Lead"


def _lead_group_from_item(item: dict[str, Any]) -> str:
    if item.get("source") == "email" or item.get("lead_group") == "email":
        return "email"
    if item.get("source") == "crm":
        return "crm"
    url = (item.get("url") or "").lower()
    if "reddit.com" in url:
        return "reddit"
    if "linkedin.com" in url:
        return "linkedin"
    if "twitter.com" in url or "x.com" in url:
        return "social"
    return "scouted"


_LEAD_GROUP_LABELS = {
    "crm": "From your CRM",
    "reddit": "Reddit",
    "linkedin": "LinkedIn",
    "social": "Social",
    "scouted": "Scouted leads",
}


def _is_reddit_url(url: str) -> bool:
    return "reddit.com" in (url or "").lower()


_BLOCKED_SOURCE_HOST_SUFFIXES = (
    "zilo.pro",
    "zilo.app",
    "zilo.vercel.app",
    "onrender.com",
    "localhost",
    "127.0.0.1",
)


def _url_host(url: str) -> str:
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).netloc or "").lower().split("@")[-1]
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _normalize_site_host(site: str) -> str:
    s = (site or "").strip().lower()
    if not s:
        return ""
    if not s.startswith(("http://", "https://")):
        s = f"https://{s}"
    return _url_host(s)


def _is_blocked_source_url(url: str, owner_website: str = "") -> bool:
    host = _url_host(url)
    if not host:
        return True
    for suffix in _BLOCKED_SOURCE_HOST_SUFFIXES:
        if host == suffix or host.endswith(f".{suffix}"):
            return True
    owner_host = _normalize_site_host(owner_website)
    if owner_host and (host == owner_host or host.endswith(f".{owner_host}")):
        return True
    return False


def _parse_contact_info(contact_info: str) -> tuple[str, str]:
    """Parse contact_info into (email, phone)."""
    raw = (contact_info or "").strip()
    if not raw:
        return "", ""
    email = ""
    phone = ""
    m = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", raw)
    if m:
        email = m.group(0).strip().lower()
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 7 and not raw.lower().startswith("http"):
        phone = raw if raw.startswith("+") else digits
    return email, phone


def _contacts_from_opportunity(o: dict[str, Any]) -> tuple[str, str]:
    email = (o.get("email") or "").strip().lower()
    phone = (o.get("phone") or o.get("phone_number") or "").strip()
    info_email, info_phone = _parse_contact_info(str(o.get("contact_info") or ""))
    if not email and info_email:
        email = info_email
    if not phone and info_phone:
        phone = info_phone
    if not email:
        for blob in (o.get("snippet"), o.get("description"), o.get("text")):
            m = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", str(blob or ""))
            if m:
                email = m.group(0).strip().lower()
                break
    if not phone:
        for blob in (o.get("snippet"), o.get("description"), o.get("text")):
            m = re.search(r"\+?\d[\d\s().-]{7,}\d", str(blob or ""))
            if m:
                phone = re.sub(r"[^\d+]", "", m.group(0))
                if len(re.sub(r"\D", "", phone)) >= 7:
                    break
                phone = ""
    return email, phone


def _owner_website_from_user(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    bk = user.get("business_knowledge") or {}
    settings = user.get("settings") or {}
    return str(
        bk.get("website_url")
        or user.get("website_url")
        or settings.get("website_url")
        or bk.get("website")
        or ""
    ).strip()


def _sanitize_lead_source_url(
    url: str | None,
    *,
    email: str = "",
    phone: str = "",
    owner_website: str = "",
) -> str:
    """
    Keep a source URL only when outreach is web/manual (no direct email/phone)
    and the URL is an external lead page — not the owner's site or Zilo.
    """
    if (email or "").strip() or (phone or "").strip():
        return ""
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return ""
    if _is_blocked_source_url(raw, owner_website):
        return ""
    return raw


def _is_web_manual_item(item: dict[str, Any]) -> bool:
    """Leads discovered on the web with no WhatsApp/email — copy-paste outreach."""
    if item.get("phone") or item.get("email"):
        return False
    url = (item.get("url") or item.get("outreach_url") or "").strip()
    if not url or _is_blocked_source_url(url):
        return False
    group = item.get("lead_group") or _lead_group_from_item(item)
    if group == "reddit" or _is_reddit_url(url):
        return True
    return item.get("source") == "scouted"


def _outreach_url_for_item(item: dict[str, Any]) -> str:
    """Best link for the founder to open before pasting a reply."""
    if not _is_web_manual_item(item):
        return ""
    url = (item.get("url") or "").strip()
    if url and not _is_blocked_source_url(url):
        return url
    label = (item.get("label") or "").strip()
    m = re.match(r"^u/([A-Za-z0-9_-]+)$", label, re.I)
    if m:
        return f"https://www.reddit.com/message/compose/?to={m.group(1)}"
    return ""


def _work_item_from_opportunity_dict(
    o: dict[str, Any],
    *,
    owner_website: str = "",
) -> dict[str, Any]:
    """Build a delegate work item from a scouted opportunity with sane contact + URL."""
    email, phone = _contacts_from_opportunity(o)
    url = _sanitize_lead_source_url(
        o.get("url"),
        email=email,
        phone=phone,
        owner_website=owner_website,
    )
    label = _lead_label_from_opportunity(o)
    ctx = o.get("snippet") or o.get("description") or o.get("text") or ""
    if url:
        ctx = f"{ctx}\nSource: {url}".strip()
    elif email:
        ctx = f"{ctx}\nContact email: {email}".strip()
    elif phone:
        ctx = f"{ctx}\nContact phone: {phone}".strip()
    parent_title = (o.get("title") or label)[:120]
    item = {
        "label": label,
        "parent_label": parent_title,
        "context": ctx[:500],
        "contact_id": None,
        "source": "scouted",
        "lead_group": _lead_group_from_item({"url": url, "source": "scouted"}),
        "opportunity_id": str(o.get("_id") or "") or None,
        "url": url or None,
        "phone": phone or None,
        "email": email or None,
    }
    if email or phone:
        item["reply_channel"] = "email" if email and not phone else (
            "whatsapp" if phone and re.sub(r"\D", "", str(phone)) else "email"
        )
    return item


def _web_draft_instructions(item: dict[str, Any]) -> str:
    if not _is_web_manual_item(item):
        if item.get("email"):
            return (
                "\nOUTREACH CHANNEL: Email — write a complete email (Subject: line, then body). "
                "Use the contact's context; do not invent a website source link."
            )
        if item.get("phone"):
            return (
                "\nOUTREACH CHANNEL: WhatsApp/SMS — short chat message, not email format. "
                "No website source link."
            )
        return ""
    url = (item.get("url") or "").strip()
    group = item.get("lead_group") or _lead_group_from_item(item)
    if group == "reddit" or _is_reddit_url(url):
        return (
            "\nOUTREACH CHANNEL: Reddit — the founder will copy-paste your text manually (no auto-send). "
            "Write only the message to paste as a Reddit comment or DM. "
            "Tone: helpful, native to Reddit, not salesy. No email-style sign-offs. "
            "Format with a line 'Suggested opener:' then the paste-ready reply text."
            + (f"\nSource thread: {url}" if url else "")
        )
    if url:
        return (
            "\nOUTREACH CHANNEL: Web — the founder will open the source link and paste your message manually. "
            "Write only the paste-ready reply. Keep it short and relevant to what they posted."
            + f"\nSource: {url}"
        )
    return ""


_EXTRACT_INDIVIDUALS_SYSTEM = (
    "Extract real, distinct outreach targets mentioned in the source content. "
    "Each target = ONE company or person (Twiga Foods, Sarah Thompson, u/username). "
    "NEVER return the post title, app listing title, or platform name as a target. "
    "NEVER invent fictional people not mentioned in the content. "
    'Return ONLY JSON: {"individuals": [{"name": "...", "context": "one sentence"}]}. '
    "If the content has no specific person/company, return {\"individuals\": []}. "
    "Maximum 5."
)


async def _extract_individuals_from_item(doc: dict, item: dict[str, Any]) -> list[dict[str, str]]:
    """Split one opportunity into individual company/person targets."""
    label = (item.get("label") or "").strip()
    ctx = (item.get("context") or "").strip()
    parent = (item.get("parent_label") or label).strip()
    url = item.get("url") or ""

    # Reddit-style usernames in content → one card each
    users = re.findall(r"\bu/[A-Za-z0-9_]+\b", f"{ctx}\n{label}\n{parent}")
    if users:
        uniq = list(dict.fromkeys(users))
        return [{"name": u, "context": ctx[:300]} for u in uniq[:5]]

    # Reddit thread with no named user — still worth a reply on the post
    if _is_reddit_url(url) and _is_multi_entity_source(label, parent, url):
        thread_label = parent if not _is_generic_lead_title(parent) else "Reddit thread"
        return [{"name": thread_label[:120], "context": ctx[:300]}]

    # Only trust a single target when the source is clearly one company/person.
    if (
        not _is_multi_entity_source(label, parent, url)
        and not _is_generic_lead_title(label)
    ):
        return [{"name": label, "context": ctx[:300]}]

    task = (doc.get("task") or "").strip()
    llm = await _call_llm_json(
        _EXTRACT_INDIVIDUALS_SYSTEM,
        f"DELEGATION: {task}\nSOURCE TITLE: {parent}\nURL: {url or 'n/a'}\nCONTENT:\n{ctx[:900]}",
        max_tokens=450,
    )
    if llm and isinstance(llm.get("individuals"), list):
        out: list[dict[str, str]] = []
        for row in llm["individuals"][:5]:
            name = (row.get("name") or row.get("label") or "").strip()
            if name and not _is_generic_lead_title(name):
                out.append({
                    "name": name[:120],
                    "context": (row.get("context") or ctx)[:300],
                })
        if out:
            return out

    # No real individual in this opportunity — skip it (prevents bundled fictional drafts).
    if _is_multi_entity_source(label, parent, url):
        return []

    name = _company_name_from_text(ctx, label)
    if _is_generic_lead_title(name):
        name = label if not _is_generic_lead_title(label) else "Lead"
    return [{"name": name, "context": ctx[:300]}]


async def _expand_to_individual_leads(
    doc: dict, items: list[dict[str, Any]], *, limit: int
) -> list[dict[str, Any]]:
    """One draft card per person/company — never one card for multiple leads."""
    expanded: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in items:
        if item.get("source") == "crm":
            key = (item.get("contact_id") or item.get("label") or "").lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            expanded.append({**item, "lead_group": "crm"})
            continue

        group = _lead_group_from_item(item)
        parent_label = item.get("parent_label") or item.get("label")
        individuals = await _extract_individuals_from_item(doc, item)
        if not individuals:
            continue
        for ind in individuals:
            name = ind["name"]
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            expanded.append({
                **item,
                "label": name,
                "context": ind.get("context") or item.get("context", ""),
                "lead_group": group,
                "parent_label": parent_label,
            })
            if len(expanded) >= limit:
                return expanded[:limit]

    return expanded[:limit]


def _split_multi_lead_draft(draft: str, fallback_label: str) -> list[dict[str, str]]:
    """Split any draft that lists 2+ people/companies into one card each."""
    text = (draft or "").strip()
    if not text:
        return [{"label": fallback_label, "draft": draft}]

    out: list[dict[str, str]] = []

    # 1) Numbered list: "1. Sarah Thompson:" (most common LLM format)
    markers = list(
        re.finditer(
            r"(?:^|\n)\s*(\d+)[\.\)]\s*"
            r"(?:\*{0,2})?"
            r"([A-Za-z][A-Za-z0-9\s&.'-]{1,55}?)"
            r"(?:\*{0,2})?\s*[:\-—–]",
            text,
            re.M,
        )
    )
    if len(markers) >= 2:
        for i, m in enumerate(markers):
            name = m.group(2).strip()
            start = m.start()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
            block = text[start:end].strip()
            block = re.sub(r"^\d+[\.\)]\s+", "", block)
            if _is_intro_only_draft(block):
                continue
            out.append({"label": name, "draft": block})
        if len(out) >= 2:
            return out

    # 2) Lines split by newline + number
    numbered = re.split(r"(?=\n\s*\d+[\.\)]\s+[A-Za-z])", text)
    if len(numbered) > 1:
        out = []
        for block in numbered:
            block = block.strip()
            if _is_intro_only_draft(block):
                continue
            if not re.match(r"^\d+[\.\)]", block):
                continue
            block = re.sub(r"^\d+[\.\)]\s+", "", block)
            label = _name_from_lead_block(f"1. {block}", fallback_label)
            if label.lower() in ("why", "suggested", "here"):
                continue
            out.append({"label": label, "draft": block})
        if len(out) >= 2:
            return out

    # 3) u/username sections
    user_parts = re.split(r"\n(?=u/[A-Za-z0-9_]+)", text)
    if len(user_parts) > 1:
        out = []
        for block in user_parts:
            block = block.strip()
            if len(block) < 25 or _is_intro_only_draft(block):
                continue
            m = re.match(r"^(u/[A-Za-z0-9_]+)", block)
            label = m.group(1) if m else _company_name_from_text(block, fallback_label)
            out.append({"label": label, "draft": block})
        if len(out) >= 2:
            return out

    # 4) Multiple "Suggested opener" blocks — split backward from each opener
    opener_spans = list(re.finditer(r"Suggested opener\s*:", text, re.I))
    if len(opener_spans) >= 2:
        out = []
        # Split text into chunks by finding name before each opener
        chunks = re.split(
            r"(?=\n[A-Z][A-Za-z0-9][A-Za-z0-9\s&.'-]{1,45}\s*[:\-—–])",
            text,
        )
        for block in chunks:
            block = block.strip()
            if _is_intro_only_draft(block) or len(block) < 50:
                continue
            label = _name_from_lead_block(block, fallback_label)
            if label.lower() in ("why", "suggested", "here", "each"):
                continue
            out.append({"label": label, "draft": block})
        if len(out) >= 2:
            return out

    # 5) "Name:" blocks at line starts (Twiga Foods:, Safaricom:)
    blocks = re.split(
        r"\n(?=[A-Z][A-Za-z0-9][A-Za-z0-9\s&.'-]{1,45}:\s)",
        text,
    )
    if len(blocks) >= 2:
        out = []
        for block in blocks:
            block = block.strip()
            if _is_intro_only_draft(block) or len(block) < 40:
                continue
            label = _name_from_lead_block(block, fallback_label)
            if label.lower() in ("why", "suggested", "source", "here", "each"):
                continue
            out.append({"label": label, "draft": block})
        if len(out) >= 2:
            return out

    return [{"label": _company_name_from_text(text, fallback_label), "draft": text}]


def _make_subtask_from_piece(
    item: dict[str, Any], piece: dict[str, str], *, verb: str
) -> dict[str, Any]:
    ctx_limit = 4000 if item.get("source") == "email" else 500
    return {
        "id": str(uuid.uuid4()),
        "label": piece.get("label") or item.get("label") or "Contact",
        "context": (item.get("context") or "")[:ctx_limit],
        "draft": piece.get("draft") or "",
        "detail": verb,
        "status": "done",
        "approval": "pending",
        "at": _now().isoformat() + "Z",
        "contact_id": item.get("contact_id"),
        "source": item.get("source") or "crm",
        "lead_group": item.get("lead_group") or _lead_group_from_item(item),
        "parent_label": item.get("parent_label"),
        "phone": item.get("phone"),
        "email": item.get("email"),
        "url": item.get("url"),
        "opportunity_id": item.get("opportunity_id"),
        "outreach_url": _outreach_url_for_item(item) or None,
        "outreach_mode": "manual_web" if _is_web_manual_item(item) else "auto",
        "reply_channel": item.get("reply_channel"),
        "inbound_message_id": item.get("inbound_message_id"),
        "email_thread_id": item.get("email_thread_id"),
        "email_message_id": item.get("email_message_id"),
        "reply_to_subject": item.get("reply_to_subject"),
        "send_status": None,
        "send_channel": None,
        "regeneration_count": 0,
        "user_edited": False,
    }


async def _gather_email_work_items(
    db: Any,
    user_id: Any,
    doc: dict,
    *,
    since: datetime | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Load recent inbox threads that need replies — not CRM contacts."""
    from rex.integrations.email_bridge import _clean_email, _is_promotional

    task_low = (doc.get("task") or "").lower()
    prefer_unread = any(k in task_low for k in ("unread", "latest", "new", "recent"))

    try:
        from email_sync import sync_emails_for_user

        await sync_emails_for_user(
            user_id,
            db,
            max_results=min(limit * 4, 50),
            trigger_briefing_ingest=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] email sync before gather failed: %s", e)

    whitelist: set[str] = set()
    customers_by_email: dict[str, dict] = {}
    try:
        for c in await db.customers.find({"user_id": user_id}, {"email": 1, "name": 1, "_id": 1}).to_list(2000):
            e = (c.get("email") or "").lower().strip()
            if e:
                whitelist.add(e)
                customers_by_email[e] = c
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] customer email whitelist failed: %s", e)

    async def _fetch_candidates(unread_only: bool) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "user_id": user_id,
            "is_outgoing": {"$ne": True},
        }
        if unread_only:
            query["is_read"] = False
        if since:
            since_val = since.isoformat() if isinstance(since, datetime) else since
            query["date"] = {"$gt": since_val}
        try:
            return await db.email_messages.find(query).sort("date", -1).to_list(limit * 8)
        except Exception:
            return await db.email_messages.find(query, limit=limit * 8).to_list(limit * 8)

    candidates = await _fetch_candidates(prefer_unread)
    if not candidates and prefer_unread:
        candidates = await _fetch_candidates(unread_only=False)

    items: list[dict[str, Any]] = []
    seen_threads: set[str] = set()
    for msg in candidates:
        thread_id = str(msg.get("thread_id") or msg.get("_id") or "")
        if not thread_id or thread_id in seen_threads:
            continue
        skip, reason = _is_promotional(msg, whitelist)
        if skip:
            logger.debug("[delegate] skip email thread=%s reason=%s", thread_id, reason)
            continue
        seen_threads.add(thread_id)

        from_addr = msg.get("from_addr") or ""
        sender_email = _clean_email(from_addr)
        display_name = from_addr.split("<")[0].strip() or sender_email or "Sender"
        subject = (msg.get("subject") or "(no subject)").strip()
        body = (msg.get("body_clean") or msg.get("body_raw") or "").strip()

        customer = customers_by_email.get(sender_email) if sender_email else None
        contact_id = str(customer["_id"]) if customer else None
        if customer and customer.get("name"):
            display_name = str(customer["name"])[:120]

        thread_msgs = await db.email_messages.find(
            {"user_id": user_id, "thread_id": thread_id}
        ).sort("date", 1).to_list(12)
        thread_blob = "\n---\n".join(
            (
                f"From: {m.get('from_addr', '')}\n"
                f"Date: {m.get('date', '')}\n"
                f"{(m.get('body_clean') or m.get('body_raw') or '')[:900]}"
            )
            for m in thread_msgs[-4:]
        )

        items.append(
            {
                "label": display_name[:120],
                "parent_label": subject[:120],
                "context": (
                    f"INCOMING EMAIL TO REPLY TO\n"
                    f"Subject: {subject}\n"
                    f"From: {from_addr}\n"
                    f"Sender email: {sender_email or '(unknown)'}\n\n"
                    f"Latest message:\n{body[:2000]}\n\n"
                    f"Thread context:\n{thread_blob[:2500]}"
                ),
                "contact_id": contact_id,
                "source": "email",
                "lead_group": "email",
                "email": sender_email or None,
                "reply_channel": "email",
                "email_thread_id": thread_id,
                "email_message_id": str(msg.get("_id")),
                "inbound_message_id": str(msg.get("_id")),
                "reply_to_subject": subject,
            }
        )
        if len(items) >= limit:
            break
    return items


async def _gather_work_items(
    db: Any, user_id: Any, doc: dict, *, since: datetime | None = None
) -> list[dict[str, Any]]:
    """Resolve who/what this delegation should work on."""
    task = (doc.get("task") or "").strip()
    category = doc.get("category") or map_category(task)
    interpreted = doc.get("interpreted") or {}
    limit = _parse_target_count(task, default=10 if category == "leads" else MAX_CONTACTS)
    user_doc = await db.users.find_one({"_id": user_id}) or {}
    owner_website = _owner_website_from_user(user_doc)

    if category == "emails":
        items = await _gather_email_work_items(
            db, user_id, doc, since=since, limit=limit
        )
        if items:
            return items
        from delegate.agent_bridge import gather_work_items_via_agent

        return await gather_work_items_via_agent(db, user_doc, doc, limit=limit)

    agent_first = category in (
        "follow_ups",
        "invoices",
        "replies",
        "outreach",
        "broadcast",
        "bookings",
        "social_scheduling",
    )
    if agent_first:
        from delegate.agent_bridge import gather_work_items_via_agent

        agent_items = await gather_work_items_via_agent(db, user_doc, doc, limit=limit)
        if agent_items:
            return agent_items

    if category == "leads":
        items: list[dict[str, Any]] = []
        # Real CRM contacts first — always one person per work item.
        crm_prospects = await db.customers.find(
            {
                "user_id": user_id,
                "$or": [
                    {"tags": {"$in": ["lead", "Lead", "prospect", "Prospect"]}},
                    {"stage": "lead"},
                ],
            }
        ).sort("created_at", -1).to_list(limit)
        for c in crm_prospects:
            name = c.get("name") or c.get("phone") or "Contact"
            items.append({
                "label": str(name)[:120],
                "parent_label": str(name)[:120],
                "context": (c.get("notes") or c.get("email") or "")[:300],
                "contact_id": str(c.get("_id")) if c.get("_id") else None,
                "source": "crm",
                "lead_group": "crm",
                "phone": c.get("phone_number") or c.get("phone"),
                "email": c.get("email"),
                "reply_channel": reply_channel_from_contact(c),
            })
        remaining = max(0, limit - len(items))
        opp_query: dict[str, Any] = {"user_id": user_id}
        if since:
            opp_query["created_at"] = {"$gt": since}
        opps = await db.action_mode_opportunities.find(opp_query).sort(
            [("score", -1), ("created_at", -1)]
        ).to_list(remaining if remaining else limit)
        for o in opps:
            items.append(_work_item_from_opportunity_dict(o, owner_website=owner_website))
        if len(items) < limit:
            extra = await db.customers.find({"user_id": user_id}).sort("created_at", -1).to_list(
                limit - len(items)
            )
            for c in extra:
                name = c.get("name") or c.get("phone") or "Contact"
                if any(x.get("contact_id") == str(c.get("_id")) for x in items):
                    continue
                items.append(
                    {
                        "label": str(name)[:120],
                        "parent_label": str(name)[:120],
                        "context": (c.get("notes") or c.get("email") or "")[:300],
                        "contact_id": str(c.get("_id")) if c.get("_id") else None,
                        "source": "crm",
                        "lead_group": "crm",
                        "phone": c.get("phone_number") or c.get("phone"),
                        "email": c.get("email"),
                        "reply_channel": reply_channel_from_contact(c),
                    }
                )
        if items:
            return items[:limit]
        from delegate.agent_bridge import gather_work_items_via_agent

        agent_items = await gather_work_items_via_agent(db, user_doc, doc, limit=limit)
        return agent_items[:limit]

    contacts = await _cold_contacts(db, user_id, limit=limit)
    return [
        {
            "label": (c.get("name") or c.get("phone") or "Contact"),
            "context": (c.get("notes") or c.get("last_message") or "")[:300],
            "contact_id": str(c.get("_id")) if c.get("_id") else None,
            "source": "crm",
            "phone": c.get("phone_number") or c.get("phone"),
            "email": c.get("email"),
            "reply_channel": reply_channel_from_contact(c),
        }
        for c in contacts
    ]


async def _build_draft_text(
    doc: dict,
    item: dict[str, Any],
    profile: dict[str, str] | None = None,
    *,
    append_if_missing: bool = True,
) -> str:
    task = (doc.get("task") or "").strip()
    category = doc.get("category") or map_category(task)
    interpreted = doc.get("interpreted") or {}
    label = item.get("label") or "Contact"
    context = (item.get("context") or "").strip()
    profile = profile or {}
    profile_block = ""
    if any(profile.get(k) for k in ("name", "title", "company")):
        profile_block = (
            "\nSENDER PROFILE:\n"
            f"Name: {profile.get('name') or '(not set)'}\n"
            f"Title: {profile.get('title') or '(not set)'}\n"
            f"Company: {profile.get('company') or '(not set)'}\n"
        )

    single_target = ""
    if category == "leads":
        single_target = (
            f"\nSTRICT: Write ONLY about this one target: {label}. "
            "One person or company. No numbered lists. No other names. "
            "Do not invent people. Format: name, why they fit (1-2 sentences), "
            "Suggested opener: (the message text)."
        )
        single_target += _web_draft_instructions(item)

    if item.get("source") == "email" or category == "emails":
        subject = item.get("reply_to_subject") or "their message"
        single_target += (
            f"\nSTRICT EMAIL REPLY to: {subject}\n"
            "Write a complete email the founder can send. Format:\n"
            f"Subject: Re: {subject}\n\n(email body)\n"
            "Reply directly to the INCOMING EMAIL in CONTEXT — answer their questions, "
            "acknowledge specifics, propose next steps if appropriate.\n"
            "NEVER write meta commentary like 'I reviewed emails' or 'here are drafts'.\n"
            "NEVER use chat/WhatsApp tone or 'Suggested opener:' for email tasks.\n"
            "One email reply only — for this sender/thread.\n"
        )
    elif item.get("is_first_message") or "first message" in context.lower():
        single_target += (
            "\nOUTREACH CHANNEL: Reply on the same channel they used (WhatsApp, Instagram, "
            "Facebook Messenger, Telegram, LinkedIn, Slack, or email — not a different platform). "
            "Write a short, warm welcome reply to their first message. "
            "Reference what they said if possible. No email-style sign-offs on chat channels. "
            "Format with a line 'Suggested opener:' then the message text only."
        )
    elif (
        item.get("source") == "crm"
        and item.get("reply_channel")
        and category != "emails"
        and item.get("source") != "email"
    ):
        single_target += (
            "\nOUTREACH CHANNEL: Reply on the same channel they used (WhatsApp, Instagram, "
            "Facebook Messenger, Telegram, LinkedIn, Slack, or email — not a different platform). "
            "Draft a reply that fulfills the delegation task above — not a generic welcome unless "
            "the task asks for one. Reference their latest message when helpful. "
            "No email-style sign-offs on chat channels. "
            "Format with a line 'Suggested opener:' then the message text only."
        )

    prompt = f"""DELEGATION TASK: {task}
INTERPRETED AS: {interpreted.get('interpreted_task') or task}
ACTION: {interpreted.get('action') or 'Draft outreach'}
TARGET (single): {label}
CONTEXT: {context or '(no extra context)'}
{profile_block}{single_target}

Write the draft the founder should review."""

    raw = await _call_llm_text(_DRAFT_SYSTEM, prompt, max_tokens=320)
    if raw and raw.strip():
        return apply_personal_signature(raw.strip(), profile, append_if_missing=append_if_missing)

    if category == "leads":
        draft = (
            f"{label}\n\n"
            f"Why they fit: Matches your search — {interpreted.get('criteria_summary') or task}.\n\n"
            f"Suggested opener: Hi — I came across your profile and think there could be a fit. "
            f"Would you be open to a quick chat this week?"
        )
        return apply_personal_signature(draft, profile, append_if_missing=append_if_missing)
    if category == "emails" or item.get("source") == "email":
        subj = item.get("reply_to_subject") or "your message"
        draft = (
            f"Subject: Re: {subj}\n\n"
            f"Hi {label.split()[0] if label else 'there'},\n\n"
            f"Thank you for your email about \"{subj}\". "
            f"I wanted to follow up on the points you raised.\n\n"
            f"[Personalize using the message in context before sending.]"
        )
        return apply_personal_signature(draft, profile, append_if_missing=append_if_missing)
    if item.get("is_first_message"):
        draft = (
            f"Suggested opener: Hi {label}! Thanks for messaging us — we're glad you reached out. "
            f"How can we help you today?"
        )
        return apply_personal_signature(draft, profile, append_if_missing=append_if_missing)
    if category == "invoices":
        draft = (
            f"Hi {label},\n\n"
            f"Just a friendly reminder that your invoice is overdue. "
            f"Please let me know if you need anything from our side to get this sorted."
        )
        return apply_personal_signature(draft, profile, append_if_missing=append_if_missing)
    draft = (
        f"Hi {label},\n\n"
        f"Following up on our last conversation — wanted to check if you're still interested "
        f"or if timing has changed. Happy to chat when convenient."
    )
    return apply_personal_signature(draft, profile, append_if_missing=append_if_missing)


async def _regenerate_draft_text(
    doc: dict,
    item: dict[str, Any],
    *,
    prior_draft: str = "",
    feedback: str = "",
    profile: dict[str, str] | None = None,
    append_if_missing: bool = True,
) -> str:
    task = (doc.get("task") or "").strip()
    category = doc.get("category") or map_category(task)
    interpreted = doc.get("interpreted") or {}
    label = item.get("label") or "Contact"
    context = (item.get("context") or "").strip()
    note = (feedback or "").strip() or "Try a different angle — shorter, warmer, and more direct."
    profile = profile or {}
    profile_block = ""
    if any(profile.get(k) for k in ("name", "title", "company")):
        profile_block = (
            "\nSENDER PROFILE:\n"
            f"Name: {profile.get('name') or '(not set)'}\n"
            f"Title: {profile.get('title') or '(not set)'}\n"
            f"Company: {profile.get('company') or '(not set)'}\n"
        )

    prompt = f"""DELEGATION TASK: {task}
INTERPRETED AS: {interpreted.get('interpreted_task') or task}
ACTION: {interpreted.get('action') or 'Draft outreach'}
TARGET: {label}
CONTEXT: {context or '(no extra context)'}
{profile_block}
PREVIOUS DRAFT (founder did not like this):
{prior_draft or '(none)'}

FOUNDER FEEDBACK:
{note}
{_web_draft_instructions(item) if category == 'leads' else ''}
{"Write a complete email reply (Subject: Re: ...) to the INCOMING EMAIL in CONTEXT. No meta commentary." if category == 'emails' or item.get('source') == 'email' else ''}

Write a completely new draft the founder should review. Do not repeat the previous draft."""

    raw = await _call_llm_text(_DRAFT_SYSTEM, prompt, max_tokens=320)
    if raw and raw.strip():
        return apply_personal_signature(raw.strip(), profile, append_if_missing=append_if_missing)
    return await _build_draft_text(
        doc, item, profile=profile, append_if_missing=append_if_missing
    )


def _subtask_index(subtasks: list, draft_id: str) -> int | None:
    for i, st in enumerate(subtasks):
        sid = st.get("id")
        if str(sid) == str(draft_id) or (not sid and str(i) == str(draft_id)):
            return i
    return None


# ── Category mapping (for the trust ladder) ─────────────────────────────────

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "emails",
            (
                "email",
                "gmail",
                "outlook",
                "inbox",
                "mailbox",
                "mail thread",
                "unread mail",
                "latest mail",
                "review mail",
                "read mail",
            ),
        ),
    ("follow_ups", ("follow up", "follow-up", "cold", "chase", "reconnect", "check in", "nudge")),
    ("invoices", ("invoice", "overdue", "payment", "unpaid", "billing")),
    ("leads", ("lead", "prospect", "scout", "find", "source", "discover")),
    ("outreach", ("outreach", "reach out", "pitch", "cold email", "cold message")),
    ("replies", ("reply", "respond", "answer", "inbox", "welcome", "greet")),
    ("broadcast", ("broadcast", "campaign", "blast", "announce", "newsletter")),
    ("social_scheduling", ("post", "social", "instagram", "facebook", "linkedin")),
    ("bookings", ("book", "appointment", "schedule a call", "reschedule")),
)


def map_category(task: str) -> str:
    low = (task or "").lower()
    for cat, kws in _CATEGORY_KEYWORDS:
        if any(k in low for k in kws):
            return cat
    return "follow_ups"


# ── Rank lookup (best-effort; defaults to Drafter / safe) ───────────────────

async def get_rank_for_category(db: Any, user_id: Any, category: str) -> str:
    """Return the display rank ('Observer'|'Drafter'|'Sender'|'Operator'|'Chief of Staff').

    Best-effort: reads the rex trust-event log if present, else defaults to
    Drafter (drafts staged for approval — the safe default per the spec).
    """
    try:
        from rex.ranks.engine import RankEngine  # type: ignore  # noqa: F401
    except Exception:
        return "Drafter"

    try:
        events_col = db.get_collection("rex_trust_events")
        raw = await events_col.find({"user_id": user_id, "category": category}).to_list(500)
        if not raw:
            return "Drafter"
        # The event log is the source of truth, but replaying it requires the
        # full TrustEvent objects. If a denormalised standing exists, use it.
    except Exception:
        pass

    try:
        standings = db.get_collection("rex_standings")
        doc = await standings.find_one({"user_id": user_id, "category": category})
        if doc and doc.get("rank"):
            return str(doc["rank"])
    except Exception:
        pass
    return "Drafter"


def rank_behavior(rank: str) -> dict[str, str]:
    """Footer note + execution behavior keyed on rank."""
    r = (rank or "Drafter").strip().lower()
    if r in ("sender", "operator", "chief of staff"):
        return {
            "mode": "execute",
            "note": "Sender rank — Zilo will execute directly and report in your briefing",
        }
    if r == "observer":
        return {
            "mode": "observe",
            "note": "Observer rank — Zilo will report findings only. Nothing will be sent.",
        }
    return {
        "mode": "draft",
        "note": "Drafter rank — drafts staged for your approval before anything sends",
    }


# ── Interpretation ──────────────────────────────────────────────────────────

_INTERPRET_SYSTEM = (
    "You are Zilo, interpreting a founder's delegated task for a CRM. "
    "Restate the task as a concrete, executable instruction. "
    "If the task mentions email, gmail, inbox, or reviewing mail, the target is "
    "EMAIL THREADS in the synced inbox — NOT CRM contacts or WhatsApp. "
    "Return ONLY JSON with keys: interpreted_task (what to find/target), "
    "action (what to do for each), output (where results go — usually "
    "'Stage drafts for your review'), criteria_summary (short filter like "
    "'unread inbox' or '14+ days no activity'), needs_detail (true only if the request is too "
    "vague to act on), detail_prompt (a one-line clarifying question if "
    "needs_detail). Be terse. No prose outside JSON."
)


async def _enrich_interpretation_with_agent(
    db: Any, user_id: Any, task: str, interp: dict
) -> dict:
    """Attach specialist agent id so Delegate can call the right agent in the background."""
    from delegate.agent_bridge import resolve_delegate_specialist

    category = interp.get("category") or map_category(task)
    agent_id = await resolve_delegate_specialist(db, user_id, task, category)
    interp["category"] = category
    interp["specialist_agent"] = agent_id
    if agent_id and interp.get("plain_summary"):
        interp["plain_summary"] = (
            f"{interp['plain_summary'].rstrip('.')}. "
            f"Zilo will use the {agent_id} specialist in the background."
        )
    return interp


async def interpret_task(db: Any, user: dict, task: str) -> dict:
    task = (task or "").strip()
    user_id = user.get("_id")
    category = map_category(task)

    if category == "emails":
        contact_count = await _count_emails_needing_reply(db, user_id)
        count_hint = f"Approx. {contact_count} recent inbox email(s) needing a reply."
    else:
        contact_count = await _count_cold_contacts(db, user_id)
        count_hint = f"Approx. matching contacts in CRM right now: {contact_count}."

    llm = await _call_llm_json(
        _INTERPRET_SYSTEM,
        f"Founder's task: {task}\nDetected category: {category}\n{count_hint}",
        max_tokens=400,
    )

    if llm and not llm.get("needs_detail"):
        interpreted_task = str(llm.get("interpreted_task") or "").strip()
        action = str(llm.get("action") or "").strip()
        output = str(llm.get("output") or "Stage drafts for your review").strip()
        criteria = str(llm.get("criteria_summary") or "").strip()
        plain = _plain_summary(interpreted_task, action, output, criteria, contact_count)
        return await _enrich_interpretation_with_agent(
            db,
            user_id,
            task,
            {
                "interpreted_task": interpreted_task,
                "action": action,
                "output": output,
                "criteria_summary": criteria,
                "contact_count": contact_count,
                "plain_summary": plain,
                "needs_detail": False,
                "detail_prompt": "",
                "category": category,
            },
        )

    if llm and llm.get("needs_detail"):
        return await _enrich_interpretation_with_agent(
            db,
            user_id,
            task,
            {
                "interpreted_task": "",
                "action": "",
                "output": "",
                "criteria_summary": "",
                "contact_count": contact_count,
                "plain_summary": "",
                "needs_detail": True,
                "detail_prompt": str(llm.get("detail_prompt") or "")
                or "I need a bit more detail. Who should I contact and what should I say?",
                "category": category,
            },
        )

    # Heuristic fallback (no LLM available).
    return await _enrich_interpretation_with_agent(
        db, user_id, task, _heuristic_interpret(task, category, contact_count)
    )


def _heuristic_interpret(task: str, category: str, contact_count: int) -> dict:
    low = task.lower()
    if len(task) < 6:
        return {
            "interpreted_task": "",
            "action": "",
            "output": "",
            "criteria_summary": "",
            "contact_count": contact_count,
            "plain_summary": "",
            "needs_detail": True,
            "detail_prompt": "I need a bit more detail. Who should I contact and what should I say?",
            "category": category,
        }
    if category == "follow_ups" or "cold" in low or "follow" in low:
        interpreted_task = "Find all contacts with no activity in 14+ days"
        action = "Draft a personalised follow-up for each based on their last conversation"
        criteria = "14+ days no activity"
    elif category == "invoices":
        interpreted_task = "Find all customers with overdue invoices"
        action = "Draft a payment reminder for each"
        criteria = "invoice overdue"
    elif category == "leads":
        interpreted_task = "Search for new leads matching your request"
        action = "Compile a shortlist with contact details"
        criteria = "new prospects"
    elif category == "emails":
        interpreted_task = "Find recent inbox emails that need a reply"
        action = "Draft a personalised email reply for each thread"
        criteria = "recent inbox"
    else:
        interpreted_task = task.strip().capitalize()
        action = "Draft the work for each match"
        criteria = ""
    output = "Stage drafts for your review"
    plain = _plain_summary(interpreted_task, action, output, criteria, contact_count)
    return {
        "interpreted_task": interpreted_task,
        "action": action,
        "output": output,
        "criteria_summary": criteria,
        "contact_count": contact_count,
        "plain_summary": plain,
        "needs_detail": False,
        "detail_prompt": "",
        "category": category,
    }


def _plain_summary(
    interpreted_task: str, action: str, output: str, criteria: str, count: int
) -> str:
    parts: list[str] = []
    if interpreted_task:
        if count and "contact" in interpreted_task.lower():
            parts.append(re.sub(r"\ball contacts\b", f"{count} contacts", interpreted_task, flags=re.I))
        else:
            parts.append(interpreted_task)
    if action:
        parts.append(action)
    if output:
        parts.append(output)
    text = ". ".join(p.rstrip(".") for p in parts if p)
    return text + "." if text else ""


async def _count_cold_contacts(db: Any, user_id: Any, days: int = COLD_DAYS_DEFAULT) -> int:
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return await db.customers.count_documents(
            {
                "user_id": user_id,
                "$or": [{"last_contacted": {"$lt": cutoff}}, {"last_contacted": None}],
            }
        )
    except Exception:
        return 0


async def _cold_contacts(db: Any, user_id: Any, days: int = COLD_DAYS_DEFAULT, limit: int = MAX_CONTACTS):
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return (
            await db.customers.find(
                {
                    "user_id": user_id,
                    "$or": [{"last_contacted": {"$lt": cutoff}}, {"last_contacted": None}],
                }
            )
            .sort("last_contacted", 1)
            .to_list(limit)
        )
    except Exception:
        return []


async def _count_emails_needing_reply(db: Any, user_id: Any, limit: int = 50) -> int:
    """Count recent inbound emails that would be drafted (best-effort)."""
    from rex.integrations.email_bridge import _is_promotional

    try:
        query = {"user_id": user_id, "is_outgoing": {"$ne": True}, "is_read": False}
        msgs = await db.email_messages.find(query, limit=limit * 2).to_list(limit * 2)
        if not msgs:
            query.pop("is_read", None)
            msgs = await db.email_messages.find(query, limit=limit * 2).to_list(limit * 2)
        seen: set[str] = set()
        count = 0
        for msg in msgs:
            thread_id = str(msg.get("thread_id") or msg.get("_id") or "")
            if not thread_id or thread_id in seen:
                continue
            skip, _ = _is_promotional(msg, None)
            if skip:
                continue
            seen.add(thread_id)
            count += 1
        return count
    except Exception:
        return 0


# ── Execution ────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.utcnow()


def _coerce_utc_datetime(value: Any) -> datetime | None:
    """Normalize Mongo/datetime/string timestamps for comparisons."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _utc_iso_z(value: Any) -> str | None:
    """Serialize datetimes (or ISO strings) as UTC with trailing Z."""
    dt = _coerce_utc_datetime(value)
    if dt is None:
        return None
    return dt.isoformat() + "Z"


async def run_delegation(
    db: Any,
    delegation_id: str,
    user: dict,
    *,
    trigger_opportunity: dict[str, Any] | None = None,
    trigger_customer: dict[str, Any] | None = None,
    trigger_message: str = "",
    trigger_message_id: str | None = None,
    trigger_is_first: bool = False,
) -> None:
    """Process a delegation: work through matching contacts, staging a draft each.

    Designed to run as a background task so the UI can poll live progress.
    """
    user_id = user.get("_id")
    doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})
    if not doc:
        return

    mode = doc.get("mode") or "once"
    incremental = mode in ("schedule", "on_opportunity") or trigger_opportunity is not None or trigger_customer is not None
    behavior = rank_behavior(doc.get("rank") or "Drafter")
    category = doc.get("category") or map_category(doc.get("task") or "")
    target_limit = _parse_target_count(doc.get("task") or "", default=10 if category == "leads" else MAX_CONTACTS)

    since: datetime | None = None
    if mode == "schedule":
        since = doc.get("last_run_at")
        if not since:
            since = _now() - timedelta(days=7)

    if trigger_customer:
        work_items = [
            _work_item_from_customer(
                trigger_customer,
                trigger_message,
                is_first=trigger_is_first,
                message_id=trigger_message_id,
            )
        ]
    elif trigger_opportunity:
        user_doc = await db.users.find_one({"_id": user_id}) or {}
        work_items = [
            _work_item_from_opportunity_dict(
                trigger_opportunity,
                owner_website=_owner_website_from_user(user_doc),
            )
        ]
    else:
        work_items = await _gather_work_items(db, user_id, doc, since=since if incremental and category == "leads" else None)

    if category == "leads" and not trigger_customer:
        work_items = await _expand_to_individual_leads(doc, work_items, limit=target_limit)

    existing_opp_ids = _existing_opportunity_ids(doc)
    existing_contact_ids = _existing_contact_ids(doc)
    existing_msg_ids = _existing_inbound_message_ids(doc)
    existing_thread_ids = _existing_email_thread_ids(doc)
    trigger_filter = (doc.get("trigger_filter") or "").strip().lower()

    def _keep_work_item(w: dict[str, Any]) -> bool:
        if w.get("opportunity_id") and str(w["opportunity_id"]) in existing_opp_ids:
            return False
        tid = w.get("email_thread_id")
        if tid and str(tid) in existing_thread_ids:
            return False
        cid = w.get("contact_id")
        mid = w.get("inbound_message_id") or w.get("email_message_id")
        if category == "emails" or w.get("source") == "email":
            if mid and str(mid) in existing_msg_ids:
                return False
            return True
        if trigger_filter == "client_message" and mid:
            return str(mid) not in existing_msg_ids
        if trigger_filter == "first_message" and cid and str(cid) in existing_contact_ids:
            return False
        if trigger_customer is None and cid and str(cid) in existing_contact_ids:
            return False
        return True

    work_items = [w for w in work_items if _keep_work_item(w)]

    personal_profile = personal_profile_from_user(user)
    if not any(personal_profile.get(k) for k in ("name", "title", "company")):
        personal_profile = await load_personal_profile(db, user_id)
    append_if_missing = append_signature_from_user(user)

    # Build one subtask per individual (split multi-lead drafts if LLM still bundles them).
    subtask_plan: list[dict[str, Any]] = []
    verb = "draft ready" if behavior["mode"] == "draft" else (
        "sent" if behavior["mode"] == "execute" else "flagged"
    )
    for item in work_items:
        draft_text = await _build_draft_text(
            doc, item, profile=personal_profile, append_if_missing=append_if_missing
        )
        pieces = _split_multi_lead_draft(draft_text, item.get("label") or "Lead")
        pieces = [p for p in pieces if not _is_intro_only_draft(p.get("draft") or "")]
        if len(pieces) <= 1:
            pieces = [{"label": item.get("label") or "Lead", "draft": draft_text}]
        seen_piece: set[str] = set()
        for piece in pieces:
            dedupe = f"{item.get('opportunity_id') or ''}:{(piece.get('label') or '').lower()}"
            if dedupe in seen_piece:
                continue
            seen_piece.add(dedupe)
            subtask_plan.append(_make_subtask_from_piece(item, piece, verb=verb))

    total = len(subtask_plan)
    existing_subtasks = list(doc.get("subtasks") or [])
    existing_staged = int(doc.get("staged_count") or len(existing_subtasks))

    if total == 0:
        if incremental:
            final_status = "watching" if mode == "on_opportunity" else "scheduled"
            await db[COLLECTION].update_one(
                {"_id": delegation_id},
                {
                    "$set": {
                        "status": final_status,
                        "last_run_at": _now(),
                        "updated_at": _now(),
                    }
                },
            )
            return
        await db[COLLECTION].update_one(
            {"_id": delegation_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": _now(),
                    "last_run_at": _now(),
                    "staged_count": 0,
                    "result_summary": (
                        "No emails needing a reply right now. Connect Gmail or Outlook "
                        "in Integrations and sync your inbox."
                        if category == "emails"
                        else "No matching contacts found right now."
                    ),
                    "updated_at": _now(),
                }
            },
        )
        return

    running_status = "running"
    if incremental:
        await db[COLLECTION].update_one(
            {"_id": delegation_id},
            {
                "$set": {
                    "status": running_status,
                    "started_at": doc.get("started_at") or _now(),
                    "progress": {"total": existing_staged + total, "done": existing_staged},
                    "updated_at": _now(),
                }
            },
        )
    else:
        await db[COLLECTION].update_one(
            {"_id": delegation_id},
            {
                "$set": {
                    "status": "running",
                    "started_at": _now(),
                    "progress": {"total": total, "done": 0},
                    "subtasks": [],
                    "updated_at": _now(),
                }
            },
        )

    staged = existing_staged if incremental else 0
    for i, subtask in enumerate(subtask_plan):
        staged += 1
        await db[COLLECTION].update_one(
            {"_id": delegation_id, "user_id": user_id},
            {
                "$push": {"subtasks": subtask},
                "$set": {
                    "progress": {
                        "total": (existing_staged + total) if incremental else total,
                        "done": (existing_staged + i + 1) if incremental else (i + 1),
                    },
                    "staged_count": staged,
                    "updated_at": _now(),
                },
            },
        )
        latest = await db[COLLECTION].find_one(
            {"_id": delegation_id}, {"status": 1}
        )
        if latest and latest.get("status") == "paused":
            return
        if _STEP_DELAY_SECONDS > 0 and i < total - 1:
            await asyncio.sleep(_STEP_DELAY_SECONDS)

    summary = f"{staged} {'drafts' if behavior['mode'] == 'draft' else 'actions'} ready for your review."
    contact_names = [(item.get("label") or "Contact") for item in work_items[:8]]
    final_status = (
        "watching" if mode == "on_opportunity"
        else ("scheduled" if mode == "schedule" else "completed")
    )
    await db[COLLECTION].update_one(
        {"_id": delegation_id, "user_id": user_id},
        {
            "$set": {
                "status": final_status,
                "completed_at": _now() if final_status == "completed" else doc.get("completed_at"),
                "last_run_at": _now(),
                "staged_count": staged,
                "result_summary": summary,
                "result_contacts": contact_names,
                "updated_at": _now(),
            },
            "$push": {
                "runs": {
                    "ran_at": _now().isoformat() + "Z",
                    "staged_count": len(subtask_plan),
                    "summary": summary,
                    "contacts": contact_names,
                }
            },
        },
    )


def _outbound_message(draft: str, category: str) -> str:
    """Extract the message to actually send from a draft brief."""
    text = (draft or "").strip()
    if category == "leads":
        low = text.lower()
        for marker in ("suggested opener:", "opener:", "message:", "draft:"):
            idx = low.find(marker)
            if idx >= 0:
                return text[idx + len(marker) :].strip()
    return text


def _parse_email_parts(text: str) -> tuple[str, str]:
    lines = text.strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip() or "Following up"
        body = "\n".join(lines[1:]).strip()
        return subject, body or text
    return "Following up", text


async def _save_lead_to_crm(
    db: Any, user_id: Any, subtask: dict[str, Any], draft: str
) -> str:
    """Save one approved scouted lead as its own CRM contact — never merge unrelated leads."""
    label = subtask.get("label") or "Lead"
    crm_name = _company_name_from_text(draft, label)
    if _is_generic_lead_title(crm_name):
        crm_name = label if not _is_generic_lead_title(label) else f"Lead {str(subtask.get('id') or uuid.uuid4())[:8]}"

    subtask_id = subtask.get("id")
    opp_id = subtask.get("opportunity_id")
    existing = None
    if subtask_id:
        existing = await db.customers.find_one(
            {"user_id": user_id, "delegate_subtask_id": str(subtask_id)}
        )
    if not existing and opp_id:
        existing = await db.customers.find_one(
            {"user_id": user_id, "delegate_opportunity_id": str(opp_id)}
        )

    notes = draft
    source_url = (subtask.get("outreach_url") or subtask.get("url") or "").strip()
    if source_url and _is_web_manual_item(subtask):
        notes = f"{draft}\n\nSource: {source_url}"

    if existing:
        cid = str(existing["_id"])
        await db.customers.update_one(
            {"_id": cid},
            {
                "$set": {
                    "name": crm_name[:120],
                    "notes": notes[:4000],
                    "last_contacted": _now(),
                    "stage": existing.get("stage") or "lead",
                    "tags": list(set((existing.get("tags") or []) + ["lead", "delegate"])),
                    "delegate_subtask_id": str(subtask_id) if subtask_id else existing.get("delegate_subtask_id"),
                    "delegate_opportunity_id": str(opp_id) if opp_id else existing.get("delegate_opportunity_id"),
                }
            },
        )
        return cid

    cid = str(uuid.uuid4())
    await db.customers.insert_one({
        "_id": cid,
        "user_id": user_id,
        "name": crm_name[:120],
        "phone_number": subtask.get("phone") or "",
        "email": subtask.get("email"),
        "notes": notes[:4000],
        "tags": ["lead", "delegate"],
        "stage": "lead",
        "created_at": _now(),
        "last_contacted": _now(),
        "source": "delegate",
        "delegate_subtask_id": str(subtask_id) if subtask_id else None,
        "delegate_opportunity_id": str(opp_id) if opp_id else None,
    })
    return cid


async def _execute_approved_draft(
    db: Any, user_id: Any, doc: dict, subtask: dict[str, Any]
) -> dict[str, Any]:
    """Send (or save) a draft after founder approval. Drafter rank: nothing sends before this."""
    if subtask.get("send_status") == "sent":
        return {
            "send_status": "sent",
            "send_channel": subtask.get("send_channel"),
            "sent_at": subtask.get("sent_at"),
        }

    category = doc.get("category") or map_category(doc.get("task") or "")
    draft = (subtask.get("draft") or "").strip()
    if not draft:
        return {"send_status": "skipped", "send_error": "No draft text"}

    message = _outbound_message(draft, category)
    contact_id = subtask.get("contact_id")
    now = _now().isoformat() + "Z"

    contact = None
    if contact_id:
        contact = await db.customers.find_one({"_id": contact_id, "user_id": user_id})

    user_doc = await db.users.find_one({"_id": user_id}) or {}
    profile = personal_profile_from_user(user_doc)
    if not any(profile.get(k) for k in ("name", "title", "company")):
        profile = await load_personal_profile(db, user_id)

    # Scouted web / Reddit — manual copy or CRM save (not auto-sent on wrong channel).
    if category == "leads" or subtask.get("source") == "scouted":
        if _is_web_manual_item(subtask):
            cid = None
            try:
                cid = await _save_lead_to_crm(db, user_id, subtask, draft)
            except Exception as e:  # noqa: BLE001
                return {"send_status": "failed", "send_channel": "crm", "send_error": str(e), "sent_at": now}
            outreach_url = _outreach_url_for_item(subtask) or (subtask.get("url") or "").strip()
            channel = "reddit" if (
                subtask.get("lead_group") == "reddit" or _is_reddit_url(outreach_url)
            ) else "web"
            return {
                "send_status": "manual_copy",
                "send_channel": channel,
                "sent_at": now,
                "contact_id": cid,
                "outreach_url": outreach_url or None,
            }
        if not contact and not subtask.get("phone") and not subtask.get("email"):
            try:
                cid = await _save_lead_to_crm(db, user_id, subtask, draft)
                return {
                    "send_status": "saved",
                    "send_channel": "crm",
                    "sent_at": now,
                    "contact_id": cid,
                }
            except Exception as e:  # noqa: BLE001
                return {"send_status": "failed", "send_channel": "crm", "send_error": str(e), "sent_at": now}

    send_result = await send_delegate_message(
        db,
        user_id,
        contact=contact,
        subtask=subtask,
        message=message,
        profile=profile,
    )
    if send_result.get("send_status") == "sent":
        logger.info(
            "[delegate] sent via %s for %s",
            send_result.get("send_channel"),
            subtask.get("label"),
        )
        return send_result

    # Lead saved to CRM when no send path but we still want the record.
    if (category == "leads" or subtask.get("source") == "scouted") and send_result.get("send_status") != "sent":
        try:
            cid = await _save_lead_to_crm(db, user_id, subtask, draft)
            if send_result.get("send_status") == "no_channel":
                return {
                    **send_result,
                    "contact_id": cid,
                    "send_error": send_result.get("send_error")
                    or "Saved to CRM — open their thread to reply manually.",
                }
        except Exception:
            pass

    return send_result


async def update_draft_text(
    db: Any,
    delegation_id: str,
    user_id: Any,
    draft_id: str,
    draft_text: str,
) -> dict | None:
    """Save founder edits to a pending draft.

    Updates only the matched subtask via a positional array filter so a
    concurrent incremental run (which $pushes new subtasks) can't be clobbered.
    """
    text = (draft_text or "").strip()
    if not text:
        return None
    res = await db[COLLECTION].update_one(
        {
            "_id": delegation_id,
            "user_id": user_id,
            "subtasks": {"$elemMatch": {"id": draft_id, "approval": "pending"}},
        },
        {
            "$set": {
                "subtasks.$[s].draft": text,
                "subtasks.$[s].user_edited": True,
                "subtasks.$[s].edited_at": _now().isoformat() + "Z",
                "updated_at": _now(),
            }
        },
        array_filters=[{"s.id": draft_id}],
    )
    if res.matched_count == 0:
        return None
    return await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})


async def regenerate_draft(
    db: Any,
    delegation_id: str,
    user_id: Any,
    draft_id: str,
    *,
    feedback: str = "",
) -> tuple[dict | None, str | None]:
    """Regenerate one pending draft. Returns (doc, error_code)."""
    doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})
    if not doc:
        return None, "not_found"
    subtasks = list(doc.get("subtasks") or [])
    idx = _subtask_index(subtasks, draft_id)
    if idx is None:
        return None, "not_found"
    st = subtasks[idx]
    if st.get("approval") != "pending":
        return None, "not_pending"
    count = int(st.get("regeneration_count") or 0)
    if count >= MAX_DRAFT_REGENERATIONS:
        return None, "regen_limit"

    item = {
        "label": st.get("label") or "Contact",
        "context": st.get("context") or "",
        "contact_id": st.get("contact_id"),
        "source": st.get("source"),
        "phone": st.get("phone"),
        "email": st.get("email"),
        "url": st.get("url"),
        "lead_group": st.get("lead_group"),
        "reply_channel": st.get("reply_channel"),
        "reply_to_subject": st.get("reply_to_subject"),
        "email_thread_id": st.get("email_thread_id"),
        "email_message_id": st.get("email_message_id"),
    }
    user = await db.users.find_one({"_id": user_id}) or {}
    personal_profile = personal_profile_from_user(user)
    if not any(personal_profile.get(k) for k in ("name", "title", "company")):
        personal_profile = await load_personal_profile(db, user_id)
    append_if_missing = append_signature_from_user(user)
    new_draft = await _regenerate_draft_text(
        doc,
        item,
        prior_draft=st.get("draft") or "",
        feedback=feedback,
        profile=personal_profile,
        append_if_missing=append_if_missing,
    )
    # Write only the matched subtask; re-assert "pending" so we don't overwrite a
    # draft the founder approved while the LLM was generating.
    res = await db[COLLECTION].update_one(
        {
            "_id": delegation_id,
            "user_id": user_id,
            "subtasks": {"$elemMatch": {"id": draft_id, "approval": "pending"}},
        },
        {
            "$set": {
                "subtasks.$[s].draft": new_draft,
                "subtasks.$[s].regeneration_count": count + 1,
                "subtasks.$[s].user_edited": False,
                "subtasks.$[s].regenerated_at": _now().isoformat() + "Z",
                "updated_at": _now(),
            }
        },
        array_filters=[{"s.id": draft_id}],
    )
    if res.matched_count == 0:
        return None, "not_pending"
    updated = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})
    return updated, None


async def set_draft_approval(
    db: Any,
    delegation_id: str,
    user_id: Any,
    draft_id: str,
    approval: str,
) -> dict | None:
    """Approve or reject one staged draft by subtask id.

    Claims the pending subtask atomically (prevents a double-send race), then —
    for approvals — executes the send and writes the result onto just that
    element so concurrent runs/edits aren't clobbered.
    """
    res = await db[COLLECTION].update_one(
        {
            "_id": delegation_id,
            "user_id": user_id,
            "subtasks": {"$elemMatch": {"id": draft_id, "approval": "pending"}},
        },
        {
            "$set": {
                "subtasks.$[s].approval": approval,
                "subtasks.$[s].reviewed_at": _now().isoformat() + "Z",
                "updated_at": _now(),
            }
        },
        array_filters=[{"s.id": draft_id}],
    )
    doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})
    if not doc:
        return None
    if res.matched_count == 0:
        # Subtask absent → real 404; otherwise it was already reviewed (idempotent).
        if _subtask_index(list(doc.get("subtasks") or []), draft_id) is None:
            return None
        return doc

    if approval == "approved":
        subtasks = list(doc.get("subtasks") or [])
        idx = _subtask_index(subtasks, draft_id)
        if idx is not None:
            send_fields = await _execute_approved_draft(db, user_id, doc, subtasks[idx])
            set_ops = {f"subtasks.$[s].{k}": v for k, v in send_fields.items()}
            set_ops["updated_at"] = _now()
            await db[COLLECTION].update_one(
                {"_id": delegation_id, "user_id": user_id},
                {"$set": set_ops},
                array_filters=[{"s.id": draft_id}],
            )
            doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})
    return doc


async def approve_all_drafts(db: Any, delegation_id: str, user_id: Any) -> dict | None:
    """Approve every pending draft, then send them in the background.

    Marking approved is done synchronously so the UI updates immediately; the
    actual sends (one network call each, up to MAX_CONTACTS) run in a background
    task to avoid a long/timeout-prone request. Send status streams in as the
    founder polls.
    """
    doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})
    if not doc:
        return None
    now = _now().isoformat() + "Z"
    pending_ids = [
        st["id"]
        for st in (doc.get("subtasks") or [])
        if st.get("approval") == "pending" and st.get("id")
    ]
    if pending_ids:
        await db[COLLECTION].update_one(
            {"_id": delegation_id, "user_id": user_id},
            {
                "$set": {
                    "subtasks.$[s].approval": "approved",
                    "subtasks.$[s].reviewed_at": now,
                    "updated_at": _now(),
                }
            },
            array_filters=[{"s.approval": "pending"}],
        )
        asyncio.create_task(
            _execute_approved_batch(db, delegation_id, user_id, pending_ids)
        )
    return await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})


async def _execute_approved_batch(
    db: Any, delegation_id: str, user_id: Any, subtask_ids: list[str]
) -> None:
    """Send each approved draft and write its send status onto just that subtask."""
    for sid in subtask_ids:
        try:
            doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})
            if not doc:
                return
            subtasks = list(doc.get("subtasks") or [])
            idx = _subtask_index(subtasks, sid)
            if idx is None:
                continue
            st = subtasks[idx]
            if st.get("send_status") == "sent":
                continue
            send_fields = await _execute_approved_draft(db, user_id, doc, st)
            set_ops = {f"subtasks.$[s].{k}": v for k, v in send_fields.items()}
            set_ops["updated_at"] = _now()
            await db[COLLECTION].update_one(
                {"_id": delegation_id, "user_id": user_id},
                {"$set": set_ops},
                array_filters=[{"s.id": sid}],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[delegate] approve-all send failed for %s: %s", sid, e)


def pending_draft_count(doc: dict) -> int:
    return sum(1 for st in doc.get("subtasks") or [] if st.get("approval") == "pending")


# ── Scheduling ────────────────────────────────────────────────────────────────

_FREQ_LABELS = {
    "every_day": "Every day",
    "every_weekday": "Every weekday",
    "every_monday": "Every Monday",
    "every_friday": "Every Friday",
    "every_sunday": "Every Sunday",
    "first_of_month": "First of month",
}


_TRIGGER_FILTER_LABELS = {
    "client_message": "A client sends a message",
    "first_message": "A client's first message",
    "reddit": "Scouting finds a Reddit lead",
    "scouted": "Scouting finds a web lead",
    "any": "Any scouted lead",
}

_CLIENT_MESSAGE_TRIGGERS = frozenset({"first_message", "client_message"})


def trigger_filter_label(trigger_filter: str | None) -> str:
    key = (trigger_filter or "any").strip().lower()
    return _TRIGGER_FILTER_LABELS.get(key, "New leads")


def trigger_channel_label(trigger_channel: str | None) -> str:
    ch = (trigger_channel or "any").strip().lower()
    if ch in ("", "any", "all"):
        return "any channel"
    labels = {
        "whatsapp": "WhatsApp",
        "slack": "Slack",
        "instagram": "Instagram",
        "facebook": "Facebook Messenger",
        "telegram": "Telegram",
        "linkedin": "LinkedIn",
        "email": "Email",
        "bird": "Bird",
    }
    return labels.get(ch, ch.replace("_", " ").title())


def schedule_label(schedule: dict | None, *, mode: str | None = None, trigger_filter: str | None = None, trigger_channel: str | None = None) -> str:
    if mode == "on_opportunity":
        filt = (trigger_filter or "any").strip().lower()
        if filt in _CLIENT_MESSAGE_TRIGGERS:
            base = trigger_filter_label(trigger_filter)
            ch = (trigger_channel or "any").strip().lower()
            if ch not in ("", "any", "all"):
                return f"When {base.lower()} on {trigger_channel_label(ch)}"
            return f"When {base.lower()}"
        return f"When {trigger_filter_label(trigger_filter).lower()} appear"
    if not schedule:
        return "Once"
    freq = _FREQ_LABELS.get(schedule.get("frequency", ""), schedule.get("frequency", ""))
    t = schedule.get("time", "07:00")
    return f"{freq} · {_pretty_time(t)}"


def delegation_mode_label(doc: dict | None) -> str:
    if not doc:
        return "One-time"
    mode = doc.get("mode") or "once"
    if mode == "on_opportunity":
        filt = (doc.get("trigger_filter") or "any").strip().lower()
        ch = (doc.get("trigger_channel") or "any").strip().lower()
        if filt in _CLIENT_MESSAGE_TRIGGERS:
            when = schedule_label(
                doc.get("schedule"),
                mode=mode,
                trigger_filter=filt,
                trigger_channel=ch,
            )
            return f"Automation · {when.lower()}"
        when = trigger_filter_label(doc.get("trigger_filter")).lower()
        return f"Automation · when {when} appear"
    if mode == "schedule":
        sched = schedule_label(doc.get("schedule"))
        return f"Automation · {sched.lower()}"
    return "One-time"


def _opportunity_matches_filter(opportunity: dict[str, Any], trigger_filter: str | None) -> bool:
    filt = (trigger_filter or "any").strip().lower()
    url = (opportunity.get("url") or "").lower()
    agent = (opportunity.get("agent") or "").lower()
    if filt == "any":
        return True
    if filt == "reddit":
        return "reddit.com" in url
    if filt == "scouted":
        return bool(url) and agent in ("zilo_scout", "deal_alert", "scout")
    if filt == "first_message" or filt == "client_message":
        return False
    return True


def _existing_contact_ids(doc: dict) -> set[str]:
    ids: set[str] = set()
    for st in doc.get("subtasks") or []:
        cid = st.get("contact_id")
        if cid:
            ids.add(str(cid))
    return ids


def _existing_inbound_message_ids(doc: dict) -> set[str]:
    ids: set[str] = set()
    for st in doc.get("subtasks") or []:
        for key in ("inbound_message_id", "email_message_id"):
            mid = st.get(key)
            if mid:
                ids.add(str(mid))
    return ids


def _existing_email_thread_ids(doc: dict) -> set[str]:
    ids: set[str] = set()
    for st in doc.get("subtasks") or []:
        tid = st.get("email_thread_id")
        if tid:
            ids.add(str(tid))
    return ids


def _customer_matches_trigger_channel(customer: dict[str, Any], trigger_channel: str | None) -> bool:
    ch = (trigger_channel or "any").strip().lower()
    if ch in ("", "any", "all"):
        return True
    contact_channel = reply_channel_from_contact(customer)
    from .outbound import normalize_channel

    return normalize_channel(contact_channel) == normalize_channel(ch)


def _work_item_from_customer(
    customer: dict[str, Any],
    message: str,
    *,
    is_first: bool = False,
    message_id: str | None = None,
) -> dict[str, Any]:
    name = customer.get("name") or customer.get("phone_number") or customer.get("phone") or "Contact"
    if is_first:
        context = f"First message from client: {message[:500]}"
    else:
        context = f"Client message: {message[:500]}"
    item = {
        "label": str(name)[:120],
        "parent_label": str(name)[:120],
        "context": context,
        "contact_id": str(customer.get("_id") or "") or None,
        "source": "crm",
        "lead_group": "crm",
        "phone": customer.get("phone_number") or customer.get("phone"),
        "email": customer.get("email"),
        "is_first_message": is_first,
        "reply_channel": reply_channel_from_contact(customer),
    }
    if message_id:
        item["inbound_message_id"] = str(message_id)
    return item


def _existing_opportunity_ids(doc: dict) -> set[str]:
    ids: set[str] = set()
    for st in doc.get("subtasks") or []:
        oid = st.get("opportunity_id")
        if oid:
            ids.add(str(oid))
    return ids


def _work_item_from_opportunity(o: dict[str, Any]) -> dict[str, Any]:
    return _work_item_from_opportunity_dict(o)


def _pretty_time(t: str) -> str:
    try:
        hh, mm = t.split(":")
        h = int(hh)
        suffix = "am" if h < 12 else "pm"
        h12 = h % 12 or 12
        return f"{h12}:{mm}{suffix}"
    except Exception:
        return t


def _matches_frequency(frequency: str, now: datetime) -> bool:
    wd = now.weekday()  # Mon=0
    if frequency == "every_day":
        return True
    if frequency == "every_weekday":
        return wd < 5
    if frequency == "every_monday":
        return wd == 0
    if frequency == "every_friday":
        return wd == 4
    if frequency == "every_sunday":
        return wd == 6
    if frequency == "first_of_month":
        return now.day == 1
    return False


def _resolve_tz(name: str | None):
    """Resolve an IANA tz name to a tzinfo, falling back to UTC.

    Falls back gracefully if the name is unknown or the platform lacks the tz
    database (e.g. Windows without `tzdata` installed).
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo((name or "UTC").strip() or "UTC")
    except Exception:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo("UTC")
        except Exception:
            return timezone.utc


def compute_next_run(schedule: dict, *, after: datetime | None = None) -> datetime:
    """Next datetime (naive UTC) the schedule should fire.

    `schedule["time"]` is a wall-clock HH:MM in `schedule["timezone"]` (default
    UTC). We resolve the next matching local time and return it as naive UTC so
    it compares directly against ``datetime.utcnow()``.
    """
    after = after or datetime.utcnow()
    try:
        hh, mm = schedule.get("time", "07:00").split(":")
        hour, minute = int(hh), int(mm)
    except Exception:
        hour, minute = 7, 0
    freq = schedule.get("frequency", "every_day")
    tz = _resolve_tz(schedule.get("timezone"))

    # Treat `after` as naive UTC, then view it in the schedule's local wall clock
    # so weekday/day-of-month checks happen in the founder's timezone.
    after_local = after.replace(tzinfo=timezone.utc).astimezone(tz)
    candidate = after_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for _ in range(0, 400):
        if candidate > after_local and _matches_frequency(freq, candidate):
            return candidate.astimezone(timezone.utc).replace(tzinfo=None)
        candidate += timedelta(days=1)
        candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return (after_local + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)


async def run_due_scheduled_delegations(db: Any, *, user_id: Any | None = None) -> int:
    """Called by the scheduler. Runs scheduled delegations whose next_run has passed."""
    now = datetime.utcnow()
    triggered = 0
    query: dict[str, Any] = {
        "mode": "schedule",
        "status": {"$in": ["scheduled"]},
        "next_run_at": {"$lte": now},
    }
    if user_id is not None:
        query["user_id"] = user_id
    try:
        cursor = db[COLLECTION].find(query)
        due = await cursor.to_list(200)
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] scheduler query failed: %s", e)
        return 0

    for doc in due:
        try:
            user = await db.users.find_one({"_id": doc["user_id"]})
            if not user:
                continue
            schedule = doc.get("schedule") or {}
            next_run = compute_next_run(schedule, after=now)
            await db[COLLECTION].update_one(
                {"_id": doc["_id"]},
                {"$set": {"next_run_at": next_run, "updated_at": now}},
            )
            await run_delegation(db, doc["_id"], user)
            # Scheduled delegations stay "scheduled" between runs.
            await db[COLLECTION].update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": "scheduled", "updated_at": datetime.utcnow()}},
            )
            triggered += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[delegate] scheduled run failed for %s: %s", doc.get("_id"), e)
    return triggered


async def trigger_opportunity_delegations(
    db: Any,
    user_id: Any,
    user: dict,
    opportunity: dict[str, Any],
) -> None:
    """Run event-driven delegations when scouting finds a matching lead."""
    if not opportunity:
        return
    try:
        docs = await db[COLLECTION].find(
            {
                "user_id": user_id,
                "mode": "on_opportunity",
                "status": {"$in": ["watching", "running", "completed"]},
                "trigger_filter": {"$nin": list(_CLIENT_MESSAGE_TRIGGERS)},
            }
        ).to_list(20)
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] opportunity trigger query failed: %s", e)
        return

    for doc in docs:
        filt = doc.get("trigger_filter") or "any"
        if not _opportunity_matches_filter(opportunity, filt):
            continue
        oid = str(opportunity.get("_id") or "")
        if oid and oid in _existing_opportunity_ids(doc):
            continue
        try:
            await run_delegation(
                db,
                doc["_id"],
                user,
                trigger_opportunity=opportunity,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[delegate] opportunity run failed for %s: %s", doc.get("_id"), e)


async def notify_client_message(
    db: Any,
    user_id: Any,
    customer: dict[str, Any],
    message: str,
    *,
    is_first: bool = False,
    message_id: str | None = None,
) -> None:
    """Fire client-message Delegate automations (first message and/or every message)."""
    try:
        user = await db.users.find_one({"_id": user_id})
        if not user or not customer:
            return

        filters: list[str] = []
        if is_first:
            filters.append("first_message")
        filters.append("client_message")
        filters = list(dict.fromkeys(filters))

        docs = await db[COLLECTION].find(
            {
                "user_id": user_id,
                "mode": "on_opportunity",
                "trigger_filter": {"$in": filters},
                "status": {"$in": ["watching", "running", "completed", "paused"]},
            }
        ).to_list(50)
        docs = [d for d in docs if d.get("status") != "paused"]

        cid = str(customer.get("_id") or "")
        for doc in docs:
            filt = (doc.get("trigger_filter") or "").strip().lower()
            if filt == "first_message" and not is_first:
                continue
            if not _customer_matches_trigger_channel(customer, doc.get("trigger_channel")):
                continue
            if filt == "first_message" and cid and cid in _existing_contact_ids(doc):
                continue
            if filt == "client_message" and message_id:
                if str(message_id) in _existing_inbound_message_ids(doc):
                    continue
            try:
                await run_delegation(
                    db,
                    doc["_id"],
                    user,
                    trigger_customer=customer,
                    trigger_message=message,
                    trigger_message_id=message_id,
                    trigger_is_first=is_first,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[delegate] client_message run failed for %s: %s", doc.get("_id"), e)
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] notify_client_message failed: %s", e)


async def notify_first_message(
    db: Any,
    user_id: Any,
    customer: dict[str, Any],
    message: str,
) -> None:
    """Backward-compatible alias — prefer notify_delegate_inbound from channel webhooks."""
    await notify_client_message(db, user_id, customer, message, is_first=True)


async def notify_opportunity_created(db: Any, user_id: Any, opportunity: dict[str, Any]) -> None:
    """Background-safe hook: auto-draft when a new scouted lead appears."""
    try:
        user = await db.users.find_one({"_id": user_id})
        if not user:
            return
        await trigger_opportunity_delegations(db, user_id, user, opportunity)
    except Exception as e:  # noqa: BLE001
        logger.warning("[delegate] notify_opportunity_created failed: %s", e)


SCHEDULER_INTERVAL_MINUTES = 5


async def get_automation_diagnostics(db: Any, user_id: Any) -> dict[str, Any]:
    """Summarize scheduled/event automations for the Delegate testing panel."""
    now = datetime.utcnow()
    cursor = db[COLLECTION].find(
        {"user_id": user_id, "mode": {"$in": ["schedule", "on_opportunity"]}},
        sort=[("updated_at", -1)],
    )
    docs = await cursor.to_list(100)

    scheduled_rows: list[dict[str, Any]] = []
    due_ids: list[str] = []
    watching_event = 0

    for doc in docs:
        mode = doc.get("mode")
        status = doc.get("status")
        row = {
            "id": str(doc.get("_id")),
            "task": (doc.get("task") or "")[:120],
            "mode": mode,
            "status": status,
            "trigger_filter": doc.get("trigger_filter"),
            "trigger_channel": doc.get("trigger_channel"),
            "next_run_at": _utc_iso_z(doc.get("next_run_at")),
            "last_run_at": _utc_iso_z(doc.get("last_run_at")),
            "staged_count": int(doc.get("staged_count") or 0),
            "schedule_label": delegation_mode_label(doc),
        }
        if mode == "schedule":
            next_run = _coerce_utc_datetime(doc.get("next_run_at"))
            is_due = bool(status == "scheduled" and next_run is not None and next_run <= now)
            row["is_due"] = is_due
            if is_due:
                due_ids.append(str(doc.get("_id")))
            scheduled_rows.append(row)
        elif mode == "on_opportunity" and status == "watching":
            watching_event += 1
            scheduled_rows.append(row)

    return {
        "now_utc": now.isoformat() + "Z",
        "scheduler_interval_minutes": SCHEDULER_INTERVAL_MINUTES,
        "server_hourly_fallback": True,
        "due_scheduled_count": len(due_ids),
        "due_scheduled_ids": due_ids,
        "watching_event_automations": watching_event,
        "automations": scheduled_rows,
    }


async def simulate_client_event(
    db: Any,
    user_id: Any,
    delegation_id: str,
    *,
    customer_id: str,
    message: str,
    is_first: bool | None = None,
) -> dict[str, Any]:
    """Manually fire a client-message automation (for testing without a live webhook)."""
    from bson import ObjectId

    doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": user_id})
    if not doc:
        return {"error": "Delegation not found"}
    if doc.get("mode") != "on_opportunity":
        return {"error": "Only event automations can be simulated"}
    filt = (doc.get("trigger_filter") or "").strip().lower()
    if filt not in _CLIENT_MESSAGE_TRIGGERS:
        return {"error": "This automation is not a client-message trigger"}

    try:
        cust_oid = ObjectId(customer_id)
    except Exception:
        cust_oid = customer_id
    customer = await db.customers.find_one({"_id": cust_oid, "user_id": user_id})
    if not customer:
        return {"error": "Customer not found"}

    if is_first is None:
        incoming_n = await db.messages.count_documents({
            "user_id": user_id,
            "customer_id": customer["_id"],
            "direction": "incoming",
        })
        is_first = incoming_n == 0

    if not _customer_matches_trigger_channel(customer, doc.get("trigger_channel")):
        ch = reply_channel_from_contact(customer)
        want = (doc.get("trigger_channel") or "any").strip().lower()
        return {
            "error": f"Customer is on {ch or 'unknown'}; automation is limited to {want}.",
        }
    if filt == "first_message" and not is_first:
        return {
            "error": "This automation only runs on a contact's first message. "
            "Use a new contact or pass is_first=true in the test request.",
        }

    user = await db.users.find_one({"_id": user_id})
    if not user:
        return {"error": "User not found"}

    before = int(doc.get("staged_count") or len(doc.get("subtasks") or []))
    await run_delegation(
        db,
        delegation_id,
        user,
        trigger_customer=customer,
        trigger_message=message.strip(),
        trigger_message_id=f"simulate_{uuid.uuid4().hex[:12]}",
        trigger_is_first=is_first,
    )
    if doc.get("status") != "paused":
        await db[COLLECTION].update_one(
            {"_id": delegation_id},
            {"$set": {"status": "watching", "updated_at": datetime.utcnow()}},
        )

    updated = await db[COLLECTION].find_one({"_id": delegation_id})
    after = int(updated.get("staged_count") or len(updated.get("subtasks") or [])) if updated else before
    matched = after > before or pending_draft_count(updated or {}) > pending_draft_count(doc)

    return {
        "ok": True,
        "matched": matched,
        "is_first": is_first,
        "customer_name": customer.get("name"),
        "reply_channel": reply_channel_from_contact(customer),
        "pending_drafts": pending_draft_count(updated or {}),
        "message": "Draft staged — open Review drafts."
        if matched
        else "Automation ran but did not stage a new draft (filter mismatch or duplicate).",
    }

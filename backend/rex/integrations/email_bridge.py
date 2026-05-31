"""
Pull inbox via email_sync and queue reply drafts (Action Mode).
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# Subject patterns that strongly indicate a newsletter / promotional / automated
# message. Zilo never drafts replies to these — they get filtered at ingest so
# they don't pollute the briefing.
_PROMO_SUBJECT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"\bnewsletter\b",
        r"\bdigest\b",
        r"\bweekly\b.*\bupdate\b",
        r"\bdaily\b.*\b(brief|update|digest)\b",
        r"\[issue\s*#?\d+",
        r"\bfield\s*notes\b",
        r"\d+%\s*off\b",
        r"\bsale\b.*\bend",
        r"\bblack\s*friday\b",
        r"\bcyber\s*monday\b",
        r"\bflash\s*sale\b",
        r"\bunsubscribe\b",
        r"\bview\s*in\s*browser\b",
        r"\byou.{0,3}re\s*invited\b",
        r"^re:\s*\[",  # auto-reply to a tagged thread
        # Clickbait / financial-spam / marketing hooks the first pass missed.
        # These come in as long teaser headlines, not real conversation subjects.
        r"\d+\s*%\s*(gain|return|profit|up|growth|surge)",
        r"\$\d{2,}",                                # "$10,000", "$500"
        r"\btop\s+\d+\b",                           # "Top 5 New Listings"
        r"\b(secret|hidden|insider)\s+(project|move|pick|trade|trick|method)",
        r"\b(could|will|may|might)\s+(usher|change|transform|disrupt)",
        r"\b(billionaire|millionaire)s?\b",
        r"\b(stock|trade|crypto|coin|portfolio)\s+(pick|alert|tip|signal)",
        r"\bnext\s+big\s+(market|trend|move|stock)",
        r"\b(matching|recommended)\s+your\s+(preferences|interests)",
        r"\bunlock\s+(the|your|exclusive)",
        # "alert" / "warning" anywhere in subject (was anchored to start before
        # — missed "Crisis Alert:" because Crisis is the first word).
        r"\b(urgent|warning|breaking|alert|exclusive|crisis)\b.*[:!]",
        r":\s*your\s+(bank|account|portfolio|money)\s+(balance|is|will)",
        r"\bwiped\s+out\b",
        r"\b(this|that|one)\s+(trade|pick|move|stock)\s+(every|each)\s+time",
        r"\bevery\s+time\s+(the|government|fed)\b",
        r"\b(get\s+out|getting\s+out)\b.*\b(of|before)\b",
        r"\byour\s+(turn|chance|opportunity)\b",
        r"\bsee\s+how\s+your\s+(new|free)\s+account\b",
        r"\b(act\s+now|last\s+chance|limited\s+time)\b",
        r"\b(don.?t\s+miss|don.?t\s+wait)\b",
        # Listicle financial spam: "3 Healthcare Stocks Benefiting From..."
        r"^\d+\s+\w+\s+(stocks?|coins?|cryptos?|funds?|etfs?)\b",
        r"\b\d+\s+(stocks?|coins?|cryptos?|funds?|etfs?)\s+(to|that|benefit)",
        r"\b(aging|retirement|crypto|inflation)\s+(population|wave|crisis|boom)\b",
    )
]

# All-caps shouting in subjects = spam. One word of 5+ chars is enough (WIPED,
# URGENT, FREE, WARNING); the original 2-word rule missed "Crisis Alert: ...
# WIPED OUT!" which has just one such word.
_ALLCAPS_WORD = re.compile(r"\b[A-Z]{5,}\b")

# A direct unsubscribe / manage-subscription link is the most reliable bulk-mail
# tell. Newsletters always include one; real conversations almost never do.
_UNSUB_URL = re.compile(
    r"https?://[^\s<>\"']*"
    r"(?:unsubscribe|list-manage|email-prefs?|email[-_]?settings|mailing-list|optout|opt-out)",
    re.IGNORECASE,
)
_MANAGE_SUBS = re.compile(
    r"\bmanage\s+(subscription|preferences|emails?|mailing)|"
    r"\bemail\s+preferences\b|"
    r"\bupdate\s+(your\s+)?(preferences|subscription)|"
    r"\bunsubscribe\s+(here|from\s+this|link)|"
    r"\bthis\s+email\s+was\s+sent\s+(to|by)",
    re.IGNORECASE,
)

# Free-mail and corporate domains that legitimate humans use — exclude these
# from the "looks automated" heuristic so we don't drop real conversations.
_HUMAN_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "protonmail.com", "live.com", "aol.com", "me.com",
}


_CONVERSATION_BODY_HINTS = re.compile(
    r"\b(thanks?|thank you|please|appreciate|wondering|question|"
    r"could you|would you|can you|let me know|get back to me|"
    r"following up|circling back|quick question|hope you|"
    r"as discussed|as we|per our|regarding our|about our)\b",
    re.IGNORECASE,
)


def _looks_like_conversation(msg: dict[str, Any]) -> bool:
    """Positive signal that this is a real human exchange, not a broadcast.

    Used as an escape hatch: even if no promo pattern fires, we still skip
    drafting unless there's at least one conversation hint. This is the
    "default-deny" half of the filter — newsletters rarely talk like humans.
    """
    subject = (msg.get("subject") or "").strip().lower()
    if subject.startswith(("re:", "fwd:", "fw:")):
        return True

    body = (msg.get("body_clean") or msg.get("body_raw") or "")
    if not body:
        return False
    # Real personal mail is typically short and conversational. Newsletters are long
    # and headline-driven. Short body + a conversation cue is a strong signal.
    if len(body) < 1500 and _CONVERSATION_BODY_HINTS.search(body):
        return True

    return False


def _clean_email(addr: str) -> str:
    if not addr:
        return ""
    addr = addr.lower().strip()
    if "<" in addr and ">" in addr:
        return addr.split("<")[-1].split(">")[0].strip()
    return addr


def _is_promotional(msg: dict[str, Any], whitelist: set[str] | None = None) -> tuple[bool, str]:
    """Return (skip, reason) — should Zilo skip drafting a reply to this message?

    Layered heuristic:
      1. CRM Contact Whitelist (always allow if whitelisted)
      2. Automated/no-reply sender address (noreply@, news@, marketing@, etc.)
      3. List-Unsubscribe / List-ID header present (RFC 2369 — bulk mail marker)
      4. ESP domain (Mailchimp, SendGrid, Substack, etc.)
      5. Subject matches a promo / newsletter / clickbait pattern
      6. Subject screams in ALL CAPS (4+ chars, 2+ words = spam)
      7. Body contains the unsubscribe + newsletter-footer combo
      8. Default-deny for unknown senders if not looking like a conversational email.
    """
    from_addr = (msg.get("from_addr") or "").lower()
    clean_from = _clean_email(from_addr)

    # 1. CRM Contact Whitelist (always allow)
    if whitelist and clean_from in whitelist:
        return False, ""

    # 2. Common Automated/System Senders
    if clean_from:
        prefix = clean_from.split("@")[0]
        if prefix in ("noreply", "no-reply", "newsletter", "news", "marketing", "promotions",
                      "alerts", "info", "hello", "support", "billing", "notifications",
                      "updates", "feedback", "team", "join"):
            return True, f"automated_prefix:{prefix}"

    from email_classifier import _should_skip
    if _should_skip(from_addr):
        return True, "automated_sender"

    headers = msg.get("headers") or {}
    if isinstance(headers, dict):
        lower_keys = {k.lower(): v for k, v in headers.items()}
        if "list-unsubscribe" in lower_keys or "list-id" in lower_keys:
            return True, "list_unsubscribe_header"

    domain = from_addr.split("@")[-1] if "@" in from_addr else ""
    if domain and domain not in _HUMAN_DOMAINS:
        if any(esp in domain for esp in ("mailchimp", "sendgrid", "constantcontact",
                                          "mailgun", "campaign-archive", "list-manage",
                                          "convertkit", "substack")):
            return True, f"esp_domain:{domain}"

    subject = (msg.get("subject") or "")
    for pat in _PROMO_SUBJECT_PATTERNS:
        if pat.search(subject):
            return True, f"subject_pattern:{pat.pattern[:40]}"

    # One or more loud ALL-CAPS words (≥5 chars): WIPED, URGENT, WARNING, FREE.
    if _ALLCAPS_WORD.search(subject):
        return True, "allcaps_subject"

    body_raw = msg.get("body_clean") or msg.get("body_raw") or ""
    if body_raw:
        # An unsubscribe / manage-subscription URL is essentially conclusive.
        if _UNSUB_URL.search(body_raw):
            return True, "unsubscribe_url"
        if _MANAGE_SUBS.search(body_raw):
            return True, "newsletter_footer"

    # Default-deny for unknown senders if it's not a reply thread and doesn't look conversational
    sub_lower = subject.strip().lower()
    if not sub_lower.startswith(("re:", "fwd:", "fw:")):
        if not _looks_like_conversation(msg):
            return True, "not_conversational"

    return False, ""


async def sync_and_draft_inbox(
    db: Any,
    uid: str,
    *,
    max_messages: int = 12,
    biz_name: str = "",
) -> dict[str, Any]:
    """
    1) Sync Gmail/Outlook into email_messages
    2) Queue send_email drafts for unread threads
    """
    from email_sync import sync_emails_for_user
    from action_mode_routes import _add_to_queue

    # Batch-fetch customer email addresses for fast in-memory whitelist lookup
    whitelist: set[str] = set()
    try:
        customers = await db.customers.find({"user_id": uid}, {"email": 1}).to_list(1000)
        for c in customers:
            e = c.get("email")
            if e:
                whitelist.add(e.lower().strip())
    except Exception as e:
        logger.warning("[zilo] failed to build customer email whitelist: %s", e)

    sync_result = await sync_emails_for_user(uid, db, max_results=max_messages)
    drafted = 0

    # Avoid large in-memory sorts (Atlas 32MB limit) — take recent unread without sort.
    unread = await db.email_messages.find(
        {"user_id": uid, "is_read": False},
        limit=max_messages * 3,
    ).to_list(max_messages * 3)
    unread = unread[-max_messages:] if len(unread) > max_messages else unread

    seen_threads: set[str] = set()
    skipped_promo = 0
    for msg in unread:
        thread_id = str(msg.get("thread_id") or msg.get("_id") or "")
        if not thread_id or thread_id in seen_threads:
            continue
        seen_threads.add(thread_id)

        skip, reason = _is_promotional(msg, whitelist)
        if skip:
            skipped_promo += 1
            logger.debug("[zilo] email skip uid=%s thread=%s reason=%s", uid, thread_id, reason)
            continue

        existing = await db.action_mode_queue.find_one({
            "user_id": uid,
            "status": "pending",
            "metadata.thread_id": thread_id,
        })
        if existing:
            continue

        subject = (msg.get("subject") or "(no subject)")[:80]
        from_addr = msg.get("from_addr") or "sender"
        snippet = (msg.get("body_clean") or msg.get("body_raw") or "")[:400]
        name = from_addr.split("<")[0].strip() or "there"
        sign = biz_name or "the team"

        draft = (
            f"Hi {name.split()[0] if name else 'there'},\n\n"
            f"Thank you for your email about \"{subject}\".\n\n"
        )
        if snippet:
            draft += f"I read your note: \"{snippet[:180]}...\"\n\n"
        draft += (
            "[Personalize this reply before sending.]\n\n"
            f"Best regards,\n{sign}"
        )

        await _add_to_queue(
            db,
            uid,
            "zilo_email",
            "send_email",
            f"Email reply: {subject[:50]}",
            draft,
            {
                "thread_id": thread_id,
                "message_id": str(msg.get("_id", "")),
                "from_addr": from_addr,
                "subject": subject,
                "snippet": snippet[:300],
                "channel": "email",
                "review_only": True,
            },
        )
        drafted += 1

    logger.info(
        "[zilo] email sync uid=%s drafted=%d skipped_promo=%d sync=%s",
        uid, drafted, skipped_promo, sync_result,
    )
    return {"sync": sync_result, "drafts_queued": drafted, "skipped_promo": skipped_promo}

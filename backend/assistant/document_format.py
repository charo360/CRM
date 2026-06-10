"""Detect ambiguous PDF vs slide-deck deliverable requests."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

AMBIGUOUS_PHRASES = (
    "company profile",
    "business profile",
    "company overview",
    "business overview",
    "corporate profile",
    "about us document",
    "about our company",
    "introduction to our company",
    "our company profile",
    "write a profile",
    "create a profile",
    "make a profile",
    "build a profile",
)

SLIDES_MARKERS = (
    "pitch deck",
    "slide deck",
    "powerpoint",
    "power point",
    "pptx",
    " ppt",
    "slides",
    "presentation deck",
)

PDF_MARKERS = (
    "pdf",
    "word document",
    "word doc",
    "docx",
    ".docx",
    "written document",
    "written report",
    "download pdf",
)

# Platform domains the model must never invent in business documents
_BLOCKED_DOMAINS = frozenset({"zilochat.com", "www.zilochat.com"})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def combined_request_text(*parts: Iterable[Any]) -> str:
    chunks: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, dict):
            chunks.extend(str(v) for v in part.values() if v)
        elif isinstance(part, (list, tuple, set)):
            chunks.extend(str(v) for v in part if v)
        else:
            text = str(part).strip()
            if text:
                chunks.append(text)
    return " ".join(chunks)


def has_explicit_deliverable_format(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    if any(marker in t for marker in SLIDES_MARKERS):
        return True
    return any(marker in t for marker in PDF_MARKERS)


def is_ambiguous_deliverable_request(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    if has_explicit_deliverable_format(t):
        return False
    return any(phrase in t for phrase in AMBIGUOUS_PHRASES)


def deliverable_format_is_set(user_context: Optional[Dict[str, Any]]) -> bool:
    ctx = user_context or {}
    fmt = _norm(str(ctx.get("deliverable_format") or ctx.get("output_format") or ""))
    if fmt in {"pdf", "slides", "docx", "ppt", "pptx", "word"}:
        return True

    blob = _norm(combined_request_text(ctx))
    if re.search(r"\ba\.?\s*pdf", blob) or "pdf document" in blob:
        return True
    if re.search(r"\bb\.?\s*power", blob) or "slide deck" in blob or "powerpoint" in blob:
        return True
    if re.search(r"\bc\.?\s*word", blob) or ".docx" in blob:
        return True
    return False


def needs_deliverable_format_choice(text: str, user_context: Optional[Dict[str, Any]] = None) -> bool:
    if deliverable_format_is_set(user_context):
        return False
    return is_ambiguous_deliverable_request(text)


def build_deliverable_format_chat_reply() -> str:
    return (
        "How would you like this delivered?\n"
        "A. PDF document — written profile (best for email, printing, formal sharing)\n"
        "B. PowerPoint slide deck — best for meetings and live pitching\n"
        "C. Word document (.docx)"
    )


def format_choice_blocked_response() -> Dict[str, Any]:
    return {
        "success": True,
        "ready": False,
        "blocked": True,
        "block_reason": "deliverable_format",
        "chat_reply": build_deliverable_format_chat_reply(),
        "agent_reply_hint": (
            "Deliverable format is ambiguous — reply using chat_reply verbatim. "
            "Do NOT call check_presentation_requirements, plan_visual_presentation, "
            "check_document_requirements, or create_business_document until the user "
            "chooses PDF, slides, or Word. Store their choice in user_context.deliverable_format."
        ),
    }

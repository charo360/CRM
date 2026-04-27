"""Persist design library rows: assistant outputs, manual template metadata, and brand-kit uploads."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

COLLECTION = "saved_designs"

_KIND_LABEL = {"image": "Image", "pdf": "PDF", "pptx": "Slides", "file": "File"}

BRAND_CONTENT_TYPES = frozenset({"brand_logo", "brand_image", "brand_reference", "brand_other"})

_BRAND_LABEL = {
    "brand_logo": "Logo",
    "brand_image": "Brand image",
    "brand_reference": "Reference file",
    "brand_other": "Other brand asset",
}


def _absolutize_url(url: str) -> str:
    """Make relative upload paths fetchable by remote renderers when possible."""
    if not url or url.startswith("http://") or url.startswith("https://"):
        return url
    base = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("SERVER_URL") or os.environ.get("WEBHOOK_BASE_URL") or "").rstrip("/")
    if not base:
        return url
    return f"{base}{url if url.startswith('/') else '/' + url}"


async def insert_saved_design(
    db,
    business_id: str,
    *,
    name: str,
    asset_kind: str,
    file_url: str,
    thumbnail_url: Optional[str],
    source_tool: str,
    conversation_id: Optional[str] = None,
    platform: str = "general",
    content_type: str = "",
    format: str = "",
) -> None:
    """Best-effort insert; failures are logged and do not break the assistant tool."""
    if not file_url:
        return
    oid = str(uuid.uuid4())
    now = datetime.utcnow()
    thumb = thumbnail_url or (file_url if asset_kind == "image" else "")
    resolved_content_type = content_type or source_tool
    resolved_format = format or asset_kind
    doc: Dict[str, Any] = {
        "_id": oid,
        "user_id": business_id,
        "name": (name or "Untitled")[:200],
        "source": "assistant_generated",
        "asset_kind": asset_kind,
        "file_url": file_url,
        "thumbnail_url": thumb,
        "external_template_id": None,
        "platform": platform,
        "format": resolved_format,
        "format_label": _KIND_LABEL.get(resolved_format, resolved_format.replace("_", " ").title()),
        "content_type": resolved_content_type,
        "use_for": [resolved_content_type, "assistant"],
        "field_schema": {},
        "is_default": False,
        "created_at": now,
        "conversation_id": conversation_id,
    }
    try:
        await db[COLLECTION].insert_one(doc)
    except Exception as exc:
        logger.warning("[saved_designs] insert failed: %s", exc)


async def insert_brand_kit_asset(
    db,
    business_id: str,
    *,
    name: str,
    file_url: str,
    thumbnail_url: str,
    asset_kind: str,
    content_type: str,
    is_default_logo: bool = False,
) -> str:
    """Insert a dashboard-uploaded brand asset. Returns new document _id."""
    if content_type not in BRAND_CONTENT_TYPES:
        content_type = "brand_other"
    oid = str(uuid.uuid4())
    now = datetime.utcnow()
    fmt_labels = {
        "general": "Custom size",
        "square": "Square 1080",
        "story": "Story 9:16",
        "landscape": "Landscape 16:9",
    }
    doc: Dict[str, Any] = {
        "_id": oid,
        "user_id": business_id,
        "name": (name or "Untitled")[:200],
        "source": "brand_kit",
        "asset_kind": asset_kind,
        "file_url": file_url,
        "thumbnail_url": thumbnail_url or (file_url if asset_kind == "image" else ""),
        "external_template_id": None,
        "platform": "general",
        "format": "general",
        "format_label": fmt_labels.get("general", "Custom size"),
        "content_type": content_type,
        "use_for": ["brand", content_type],
        "field_schema": {},
        "is_default": bool(is_default_logo) if content_type == "brand_logo" else False,
        "created_at": now,
    }
    if doc["is_default"]:
        await db[COLLECTION].update_many(
            {"user_id": business_id, "source": "brand_kit", "content_type": "brand_logo", "_id": {"$ne": oid}},
            {"$set": {"is_default": False}},
        )
    await db[COLLECTION].insert_one(doc)
    return oid


async def get_primary_logo_url(db, business_id: str) -> Optional[str]:
    """Public URL for the default or latest brand logo, for compositing into generated HTML."""
    docs = (
        await db[COLLECTION]
        .find({"user_id": business_id, "source": "brand_kit", "content_type": "brand_logo", "file_url": {"$ne": ""}})
        .sort([("is_default", -1), ("created_at", -1)])
        .limit(1)
        .to_list(1)
    )
    doc = docs[0] if docs else None
    if not doc:
        return None
    url = (doc.get("file_url") or "").strip()
    return _absolutize_url(url) if url else None


async def build_design_library_context_message(db, business_id: str) -> str:
    """Short system block so every chat turn is aware of saved brand assets."""
    docs = (
        await db[COLLECTION]
        .find({"user_id": business_id, "source": "brand_kit", "file_url": {"$ne": ""}})
        .sort("created_at", -1)
        .limit(24)
        .to_list(24)
    )
    if not docs:
        return ""
    lines: List[str] = [
        "## Design library — brand assets",
        "The owner saved these under **Dashboard → Design library**. When you write copy, suggest layouts, or call "
        "`render_orshot_template` / `create_business_document`, prefer these URLs for logos and imagery (only where "
        "they apply). Remote renderers need **https** or a public base URL — relative paths may not render off-site.",
        "",
    ]
    for d in docs:
        ct = d.get("content_type") or "brand_other"
        label = _BRAND_LABEL.get(ct, ct.replace("_", " ").title())
        nm = d.get("name") or "Untitled"
        url = (d.get("file_url") or "").strip()
        if not url:
            continue
        absu = _absolutize_url(url)
        default_note = " (default logo)" if d.get("is_default") and ct == "brand_logo" else ""
        lines.append(f"- **{label}**{default_note} — {nm}: {absu}")
    return "\n".join(lines)


async def list_library_for_tool(
    db,
    business_id: str,
    *,
    sources_filter: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Rows for `list_design_library_assets` tool."""
    q: Dict[str, Any] = {"user_id": business_id}
    s = (sources_filter or "all").strip().lower()
    if s and s != "all":
        parts = {p.strip() for p in s.split(",") if p.strip()}
        allowed = {"brand_kit", "assistant_generated", "manual"}
        use = parts & allowed
        if use:
            q["source"] = {"$in": list(use)}
    docs = await db[COLLECTION].find(q).sort("created_at", -1).limit(limit).to_list(limit)
    out: List[Dict[str, Any]] = []
    for d in docs:
        url = (d.get("file_url") or "").strip()
        out.append(
            {
                "id": str(d.get("_id", "")),
                "name": d.get("name", ""),
                "source": d.get("source", ""),
                "content_type": d.get("content_type", ""),
                "asset_kind": d.get("asset_kind", ""),
                "file_url": url,
                "file_url_public": _absolutize_url(url) if url else "",
                "thumbnail_url": (d.get("thumbnail_url") or "").strip(),
                "is_default": bool(d.get("is_default")),
            }
        )
    return out


# ── Brand settings (font + primary color) ────────────────────────────────────

BRAND_SETTINGS_COLLECTION = "brand_settings"

# Popular Google Fonts — surfaces as a pick-list in the UI
GOOGLE_FONT_OPTIONS = [
    "Inter", "Poppins", "Montserrat", "Raleway", "Nunito",
    "DM Sans", "Lato", "Outfit", "Sora",
    "Playfair Display", "Cormorant Garamond", "Libre Baskerville",
    "Space Grotesk", "Plus Jakarta Sans",
    "Oswald", "Barlow", "Bebas Neue",
]


async def get_brand_settings(db, business_id: str) -> Dict[str, Any]:
    """Return the brand settings doc for this business (empty dict if not set)."""
    doc = await db[BRAND_SETTINGS_COLLECTION].find_one({"user_id": business_id})
    return {
        "brand_font": doc.get("brand_font", "") if doc else "",
        "brand_primary_color": doc.get("brand_primary_color", "") if doc else "",
    }


async def upsert_brand_settings(
    db,
    business_id: str,
    *,
    brand_font: Optional[str] = None,
    brand_primary_color: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update brand font/color settings for a business."""
    update: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    if brand_font is not None:
        update["brand_font"] = brand_font.strip()[:120]
    if brand_primary_color is not None:
        update["brand_primary_color"] = brand_primary_color.strip()[:20]
    await db[BRAND_SETTINGS_COLLECTION].update_one(
        {"user_id": business_id},
        {"$set": update, "$setOnInsert": {"user_id": business_id}},
        upsert=True,
    )
    return await get_brand_settings(db, business_id)


# ── Document Style Profile ────────────────────────────────────────────────────

_DOC_STYLE_FIELDS = (
    "tone",               # e.g. "formal", "conversational", "bold", "friendly"
    "font_style",         # e.g. "serif", "sans-serif", "modern", "classic"
    "primary_color",      # hex, e.g. "#1E3A5F"
    "secondary_color",    # hex, e.g. "#F5A623"
    "logo_placement",     # "top-left" | "top-center" | "top-right" | "none"
    "header_text",        # company tagline or standing header line
    "footer_text",        # disclaimer, copyright, or standing footer line
    "signature_name",     # sign-off name, e.g. "James Kariuki"
    "signature_title",    # e.g. "Chief Executive Officer"
    "signature_contact",  # e.g. "james@company.co.ke | +254 712 345 678"
    "date_format",        # e.g. "DD Month YYYY", "MM/DD/YYYY"
    "currency",           # e.g. "KES", "USD"
    "standing_instructions",  # freeform: "always include payment terms", etc.
)

_DOC_STYLE_KEY = "document_style"


async def get_document_style(db, business_id: str) -> Dict[str, Any]:
    """Return the document style profile for this business (empty dict if not set)."""
    doc = await db[BRAND_SETTINGS_COLLECTION].find_one({"user_id": business_id})
    raw = (doc or {}).get(_DOC_STYLE_KEY) or {}
    return {f: raw.get(f, "") for f in _DOC_STYLE_FIELDS}


async def upsert_document_style(
    db,
    business_id: str,
    fields: Dict[str, Any],
) -> Dict[str, Any]:
    """Create or update the document style profile for a business."""
    allowed = {k: str(v).strip()[:500] for k, v in fields.items() if k in _DOC_STYLE_FIELDS and v is not None}
    if not allowed:
        return await get_document_style(db, business_id)
    await db[BRAND_SETTINGS_COLLECTION].update_one(
        {"user_id": business_id},
        {
            "$set": {f"{_DOC_STYLE_KEY}.{k}": v for k, v in allowed.items()} | {"updated_at": datetime.utcnow()},
            "$setOnInsert": {"user_id": business_id},
        },
        upsert=True,
    )
    return await get_document_style(db, business_id)

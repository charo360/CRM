"""Design library: saved graphics/PDFs/decks from the assistant + optional manual metadata."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from image_handler import ImageUploadHandler
from saved_designs import (
    BRAND_CONTENT_TYPES, COLLECTION,
    GOOGLE_FONT_OPTIONS,
    insert_brand_kit_asset,
    get_brand_settings,
    upsert_brand_settings,
    get_document_style,
    upsert_document_style,
)

logger = logging.getLogger(__name__)

MAX_REF_BYTES = 15 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_PPT_BYTES = 50 * 1024 * 1024     # 50 MB
MAX_BRAND_IMAGE_BATCH = 10
IMG_EXT = frozenset({"jpg", "jpeg", "png", "webp", "gif"})
VIDEO_EXT = frozenset({"mp4", "mov", "webm", "avi", "mkv"})
PPT_EXT = frozenset({"ppt", "pptx"})


def _tid(user: dict) -> str:
    return user.get("business_id", user["_id"])


def _ser(doc: dict) -> dict:
    out = dict(doc)
    oid = out.pop("_id", None)
    out["id"] = str(oid) if oid is not None else ""
    for f in ("created_at", "updated_at"):
        v = out.get(f)
        if v and hasattr(v, "isoformat"):
            out[f] = v.isoformat()
    ext = out.get("external_template_id")
    out["external_template_id"] = int(ext) if ext is not None and ext != "" else 0
    out.setdefault("source", "manual")
    out.setdefault("file_url", "")
    out.setdefault("asset_kind", "")
    out.setdefault("thumbnail_url", out.get("thumbnail_url") or "")
    out.setdefault("use_for", out.get("use_for") or [])
    out.setdefault("field_schema", out.get("field_schema") or {})
    return out


class DesignTemplateCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str
    external_template_id: int = Field(0, ge=0)
    platform: str = "general"
    format: str = "general"
    content_type: str = "general"
    use_for: List[str] = []
    thumbnail_url: str = ""
    field_schema: Dict[str, str] = {}
    is_default: bool = False


async def _persist_brand_upload(file: UploadFile) -> tuple[str, str, str]:
    """Store upload; returns ``(file_url, asset_kind, thumbnail_url)``."""
    raw_name = file.filename or "upload"
    ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
    if ext in IMG_EXT:
        up = await ImageUploadHandler.save_image(file)
        u = (up.get("image_url") or "").strip()
        if not u:
            raise HTTPException(status_code=502, detail="Upload succeeded but no URL was returned")
        return u, "image", u
    if ext == "pdf":
        content = await file.read()
        if len(content) > MAX_REF_BYTES:
            raise HTTPException(status_code=413, detail="PDF too large (max 15MB)")
        unique = f"{uuid.uuid4()}.pdf"
        backend_dir = Path(__file__).resolve().parent
        upload_dir = backend_dir / "uploads" / "media"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / unique
        async with aiofiles.open(dest, "wb") as out:
            await out.write(content)
        rel = f"/uploads/media/{unique}"
        return rel, "pdf", ""
    if ext in VIDEO_EXT:
        content = await file.read()
        if len(content) > MAX_VIDEO_BYTES:
            raise HTTPException(status_code=413, detail="Video too large (max 200MB)")
        unique = f"{uuid.uuid4()}.{ext}"
        backend_dir = Path(__file__).resolve().parent
        upload_dir = backend_dir / "uploads" / "media"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / unique
        async with aiofiles.open(dest, "wb") as out:
            await out.write(content)
        rel = f"/uploads/media/{unique}"
        return rel, "video", ""
    if ext in PPT_EXT:
        content = await file.read()
        if len(content) > MAX_PPT_BYTES:
            raise HTTPException(status_code=413, detail="Presentation too large (max 50MB)")
        unique = f"{uuid.uuid4()}.{ext}"
        backend_dir = Path(__file__).resolve().parent
        upload_dir = backend_dir / "uploads" / "media"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / unique
        async with aiofiles.open(dest, "wb") as out:
            await out.write(content)
        rel = f"/uploads/media/{unique}"
        return rel, "ppt", ""
    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Use jpg, jpeg, png, webp, gif, pdf, mp4, mov, webm, ppt, or pptx.",
    )


class BrandSettingsUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    brand_font: Optional[str] = None
    brand_primary_color: Optional[str] = None


class DesignTemplateUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: Optional[str] = None
    external_template_id: Optional[int] = None
    platform: Optional[str] = None
    format: Optional[str] = None
    content_type: Optional[str] = None
    use_for: Optional[List[str]] = None
    thumbnail_url: Optional[str] = None
    field_schema: Optional[Dict[str, str]] = None
    is_default: Optional[bool] = None


def make_design_templates_router(db, user_dep):
    router = APIRouter(prefix="/design-templates", tags=["design-templates"])

    @router.get("/meta")
    async def design_meta(user=user_dep):
        return {
            "platforms": ["general", "instagram", "facebook", "linkedin", "tiktok", "youtube", "x"],
            "formats": [
                # ── Social media (images & videos) ──
                {"value": "general",    "label": "Custom size",                  "kind": "social"},
                {"value": "square",     "label": "Square 1:1 · 1080×1080",       "kind": "social"},
                {"value": "story",      "label": "Story / Reels 9:16 · 1080×1920", "kind": "social"},
                {"value": "landscape",  "label": "Landscape 16:9 · 1920×1080",   "kind": "social"},
                {"value": "portrait",   "label": "Portrait 4:5 · 1080×1350",     "kind": "social"},
                # ── Document (PDFs & PPTs) ──
                {"value": "a4",         "label": "A4 · 210×297 mm",              "kind": "document"},
                {"value": "letter",     "label": "Letter · 8.5×11 in",           "kind": "document"},
                {"value": "slide_169",  "label": "Slide 16:9 · 1920×1080 px",    "kind": "document"},
                {"value": "slide_43",   "label": "Slide 4:3 · 1024×768 px",      "kind": "document"},
                {"value": "slide_a4",   "label": "Slide A4 · 297×210 mm",        "kind": "document"},
            ],
            "content_types": [
                "general",
                "ad",
                "post",
                "story",
                "carousel",
                "email_header",
                "presentation",
                "create_business_document",
                "create_presentation",
                "brand_logo",
                "brand_image",
                "brand_reference",
                "brand_other",
            ],
            "material_types": [
                {"value": "brand_logo", "label": "Logo"},
                {"value": "brand_image", "label": "Brand image"},
                {"value": "brand_reference", "label": "Reference (PDF)"},
                {"value": "brand_other", "label": "Other"},
            ],
            "sources": ["brand_kit", "assistant_generated", "manual"],
            "max_brand_image_batch": MAX_BRAND_IMAGE_BATCH,
        }

    @router.get("")
    async def list_templates(
        platform: str = "any",
        content_type: str = "any",
        source: str = "any",
        user=user_dep,
    ):
        tid = _tid(user)
        q: Dict[str, Any] = {"user_id": tid}
        if platform and platform != "any":
            q["platform"] = platform
        if content_type and content_type != "any":
            q["content_type"] = content_type
        if source and source != "any":
            q["source"] = source
        docs = await db[COLLECTION].find(q, sort=[("created_at", -1)]).to_list(200)
        return [_ser(d) for d in docs]

    @router.post("")
    async def create_template(payload: DesignTemplateCreate, user=user_dep):
        tid = _tid(user)
        oid = str(uuid.uuid4())
        now = datetime.utcnow()
        fmt_labels = {
            "general": "Custom size",
            "square": "Square 1080",
            "story": "Story 9:16",
            "landscape": "Landscape 16:9",
        }
        doc = {
            "_id": oid,
            "user_id": tid,
            "name": payload.name,
            "source": "manual",
            "asset_kind": "",
            "file_url": "",
            "external_template_id": payload.external_template_id or None,
            "platform": payload.platform,
            "format": payload.format,
            "format_label": fmt_labels.get(payload.format, payload.format.replace("_", " ").title()),
            "content_type": payload.content_type,
            "use_for": payload.use_for,
            "thumbnail_url": payload.thumbnail_url,
            "field_schema": payload.field_schema,
            "is_default": payload.is_default,
            "created_at": now,
        }
        if payload.is_default:
            await db[COLLECTION].update_many(
                {"user_id": tid, "platform": payload.platform, "content_type": payload.content_type},
                {"$set": {"is_default": False}},
            )
        await db[COLLECTION].insert_one(doc)
        return _ser(await db[COLLECTION].find_one({"_id": oid}))

    @router.post("/brand-assets")
    async def upload_brand_assets_batch(
        files: List[UploadFile] = File(...),
        material_type: str = Form("brand_image"),
        name_base: str = Form(""),
        is_default_logo: str = Form("false"),
        user=user_dep,
    ):
        """Batch image upload using the same ``files`` multipart pattern as ``POST /products/{id}/images``."""
        tid = _tid(user)
        mt = material_type if material_type in BRAND_CONTENT_TYPES else "brand_image"
        if mt == "brand_reference":
            raise HTTPException(
                status_code=400,
                detail="Reference PDFs use POST /design-templates/brand-asset with a single file.",
            )
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        if len(files) > MAX_BRAND_IMAGE_BATCH:
            raise HTTPException(
                status_code=400,
                detail=f"At most {MAX_BRAND_IMAGE_BATCH} images per request (same limit style as shop photos).",
            )

        default_flag = is_default_logo.strip().lower() in ("1", "true", "yes", "on")
        base = name_base.strip()[:200]
        default_applied = False
        created: List[dict] = []

        for idx, file in enumerate(files):
            raw_name = file.filename or f"image-{idx + 1}"
            ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
            if ext not in IMG_EXT:
                logger.warning("[design-templates] brand-assets skip non-image: %s", raw_name)
                continue
            try:
                file_url, asset_kind, thumb = await _persist_brand_upload(file)
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("[design-templates] brand-assets file failed: %s", exc)
                continue

            stem = Path(raw_name).stem.strip() or f"image-{idx + 1}"
            stem = stem[:120]
            if base:
                disp = f"{base} — {stem}" if len(files) > 1 else base
            else:
                disp = stem[:200]

            is_def = bool(default_flag and mt == "brand_logo" and not default_applied)
            if is_def:
                default_applied = True

            oid = await insert_brand_kit_asset(
                db,
                tid,
                name=disp[:200] or "Brand image",
                file_url=file_url,
                thumbnail_url=thumb,
                asset_kind=asset_kind,
                content_type=mt,
                is_default_logo=is_def,
            )
            row = await db[COLLECTION].find_one({"_id": oid})
            if row:
                created.append(_ser(row))

        if not created:
            raise HTTPException(
                status_code=400,
                detail="No valid images were saved. Use jpg, png, webp, or gif (same as product photos).",
            )
        return {"status": "success", "created": len(created), "items": created}

    @router.post("/brand-asset")
    async def upload_brand_asset(
        file: UploadFile = File(...),
        name: str = Form(...),
        material_type: str = Form("brand_other"),
        is_default_logo: str = Form("false"),
        user=user_dep,
    ):
        """Upload logo / image / reference PDF into the same design library collection."""
        tid = _tid(user)
        mt = material_type if material_type in BRAND_CONTENT_TYPES else "brand_other"
        default_flag = is_default_logo.strip().lower() in ("1", "true", "yes", "on")
        try:
            file_url, asset_kind, thumb = await _persist_brand_upload(file)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("[design-templates] brand-asset upload failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        oid = await insert_brand_kit_asset(
            db,
            tid,
            name=name.strip()[:200] or "Brand asset",
            file_url=file_url,
            thumbnail_url=thumb,
            asset_kind=asset_kind,
            content_type=mt,
            is_default_logo=default_flag and mt == "brand_logo",
        )
        row = await db[COLLECTION].find_one({"_id": oid})
        if not row:
            raise HTTPException(status_code=500, detail="Save failed")
        return _ser(row)

    @router.get("/settings/brand")
    async def get_brand_settings_route(user=user_dep):
        """Return the brand font + primary color for this business."""
        tid = _tid(user)
        settings = await get_brand_settings(db, tid)
        return {**settings, "font_options": GOOGLE_FONT_OPTIONS}

    @router.post("/settings/brand")
    async def save_brand_settings_route(payload: BrandSettingsUpdate, user=user_dep):
        """Save brand font and/or primary color."""
        tid = _tid(user)
        settings = await upsert_brand_settings(
            db,
            tid,
            brand_font=payload.brand_font,
            brand_primary_color=payload.brand_primary_color,
        )
        return settings

    @router.put("/{design_id}")
    async def update_template(
        design_id: str,
        payload: DesignTemplateUpdate,
        user=user_dep,
    ):
        uid = _tid(user)
        doc = await db[COLLECTION].find_one({"_id": design_id, "user_id": uid})
        if not doc:
            raise HTTPException(404, "Design not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            if v is not None:
                upd[k] = v
        if payload.is_default is True:
            plat = upd.get("platform", doc.get("platform", "general"))
            ct = upd.get("content_type", doc.get("content_type", "general"))
            await db[COLLECTION].update_many(
                {"user_id": uid, "platform": plat, "content_type": ct, "_id": {"$ne": design_id}},
                {"$set": {"is_default": False}},
            )
        await db[COLLECTION].update_one({"_id": design_id}, {"$set": upd})
        return _ser(await db[COLLECTION].find_one({"_id": design_id}))

    @router.post("/{design_id}/clone")
    async def clone_template(design_id: str, user=user_dep):
        """Duplicate a document as a reusable template clone."""
        uid = _tid(user)
        original = await db[COLLECTION].find_one({"_id": design_id, "user_id": uid})
        if not original:
            raise HTTPException(404, "Design not found")
        oid = str(uuid.uuid4())
        now = datetime.utcnow()
        clone = {
            k: v for k, v in original.items()
            if k not in ("_id", "created_at", "updated_at", "conversation_id", "source_tool")
        }
        clone["_id"] = oid
        clone["user_id"] = uid
        clone["name"] = f"Clone of {original.get('name', 'Document')}"
        clone["source"] = "clone"
        clone["created_at"] = now
        clone["updated_at"] = now
        await db[COLLECTION].insert_one(clone)
        return _ser(await db[COLLECTION].find_one({"_id": oid}))

    @router.post("/{design_id}/ingest-to-conversation")
    async def ingest_design_to_conversation(design_id: str, user=user_dep):
        """Load a design document's text into a new assistant conversation so
        the AI can read its full structure and use it as a cloning reference."""
        uid = _tid(user)
        doc = await db[COLLECTION].find_one({"_id": design_id, "user_id": uid})
        if not doc:
            raise HTTPException(404, "Design not found")

        asset_kind = doc.get("asset_kind", "")
        if asset_kind not in ("pdf", "docx"):
            raise HTTPException(
                400,
                f"Only PDF and Word documents can be used as AI reference templates (got '{asset_kind}').",
            )

        doc_name = doc.get("name", "template")
        conv_id = str(uuid.uuid4())

        # Create the conversation record so the assistant page can load it
        from assistant.models import DEFAULT_MODEL
        from assistant.agents import resolve_agent_id, DOCUMENT_AGENT_ID
        await db.assistant_conversations.insert_one({
            "_id": conv_id,
            "user_id": uid,
            "title": f"Template: {doc_name}",
            "model": DEFAULT_MODEL,
            "messages": [],
            "agent": resolve_agent_id(DOCUMENT_AGENT_ID),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

        # ── Path 1: source_markdown stored at generation time (most reliable) ─
        source_markdown = (doc.get("source_markdown") or "").strip()
        if source_markdown:
            doc_record = {
                "_id": str(uuid.uuid4()),
                "user_id": uid,
                "conversation_id": conv_id,
                "filename": f"{doc_name}.md",
                "mime_type": "text/markdown",
                "kind": "md",
                "size": len(source_markdown.encode()),
                "text": source_markdown,
                "text_len": len(source_markdown),
                "b64": None,
                "created_at": datetime.utcnow(),
            }
            await db.assistant_documents.insert_one(doc_record)
            return {
                "conversation_id": conv_id,
                "document": {
                    "filename": doc_record["filename"],
                    "kind": "md",
                    "text_len": doc_record["text_len"],
                    "has_text": True,
                },
            }

        # ── Path 2: fetch raw bytes and extract text ──────────────────────────
        file_url = doc.get("file_url", "")
        if not file_url:
            raise HTTPException(400, "Document has no file and no stored markdown")

        mime_map = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        mime_type = mime_map[asset_kind]

        try:
            if file_url.startswith("http://") or file_url.startswith("https://"):
                # Use boto3 S3 direct download (bypasses presigned-URL expiry)
                import os as _os
                from urllib.parse import urlparse as _urlparse
                parsed = _urlparse(file_url)
                # hostname is like "bucket.s3.amazonaws.com" or "bucket.s3.region.amazonaws.com"
                bucket = parsed.hostname.split(".")[0]
                key = parsed.path.lstrip("/")
                aws_key = _os.environ.get("AWS_ACCESS_KEY_ID", "")
                aws_secret = _os.environ.get("AWS_SECRET_ACCESS_KEY", "")
                aws_region = _os.environ.get("AWS_DEFAULT_REGION") or _os.environ.get("AWS_REGION") or "us-east-2"
                if aws_key and aws_secret and bucket and key:
                    import asyncio
                    import boto3 as _boto3
                    def _s3_get():
                        s3 = _boto3.client(
                            "s3",
                            aws_access_key_id=aws_key,
                            aws_secret_access_key=aws_secret,
                            region_name=aws_region,
                        )
                        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                    content = await asyncio.get_event_loop().run_in_executor(None, _s3_get)
                else:
                    # No AWS creds — try plain HTTPS fetch (works for public buckets)
                    import httpx
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.get(file_url)
                        resp.raise_for_status()
                        content = resp.content
            else:
                backend_dir = Path(__file__).resolve().parent
                local_path = backend_dir / file_url.lstrip("/")
                async with aiofiles.open(local_path, "rb") as fh:
                    content = await fh.read()
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("[design-templates] ingest-to-conversation file fetch failed")
            raise HTTPException(502, f"Could not retrieve document file: {exc}") from exc

        from assistant.documents import store_upload
        try:
            meta = await store_upload(
                db,
                user_id=uid,
                conversation_id=conv_id,
                filename=f"{doc_name}.{asset_kind}",
                mime_type=mime_type,
                content=content,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        return {"conversation_id": conv_id, "document": meta}

    @router.delete("/{design_id}")
    async def delete_template(design_id: str, user=user_dep):
        uid = _tid(user)
        res = await db[COLLECTION].delete_one({"_id": design_id, "user_id": uid})
        if res.deleted_count == 0:
            raise HTTPException(404, "Design not found")
        return {"status": "ok"}

    # ── Document Style Profile ──────────────────────────────────────────────

    @router.get("/document-style")
    async def get_doc_style(user=user_dep):
        """Return the saved Document Style Profile for this business."""
        profile = await get_document_style(db, _tid(user))
        return {"profile": profile}

    @router.put("/document-style")
    async def update_doc_style(payload: Dict[str, Any], user=user_dep):
        """Create or update the Document Style Profile."""
        updated = await upsert_document_style(db, _tid(user), payload)
        return {"status": "saved", "profile": updated}

    return router

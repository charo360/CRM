"""Document ingestion for Zilo Chat.

- Accepts uploads (PDF, DOCX, TXT/MD, images).
- Extracts plain text where possible (pypdf / python-docx / raw decode).
- For images + PDFs, keeps the original base64 so Claude can receive them
  natively via its Messages API.
- Stores each document under `assistant_documents` keyed by conversation_id.
"""
from __future__ import annotations

import base64
import io
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_BYTES = 15 * 1024 * 1024          # 15 MB per file
MAX_EXTRACT_CHARS = 200_000           # cap stored text per file

SUPPORTED_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/csv": "csv",
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "image/gif": "image",
}


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        out: List[str] = []
        for page in reader.pages:
            try:
                out.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n\n".join(out).strip()
    except Exception as e:
        logger.warning(f"[documents] PDF extract failed: {e}")
        return ""


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        parts: List[str] = [p.text for p in doc.paragraphs if p.text]
        for t in doc.tables:
            for row in t.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        return "\n".join(parts).strip()
    except Exception as e:
        logger.warning(f"[documents] DOCX extract failed: {e}")
        return ""


def _extract_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return ""


def extract(content: bytes, mime_type: str) -> Tuple[str, str]:
    """Return (kind, extracted_text). Kind is one of: pdf, docx, txt, md, csv, image."""
    kind = SUPPORTED_MIME.get(mime_type, "")
    if not kind:
        return "", ""
    if kind == "pdf":
        text = _extract_pdf(content)
    elif kind == "docx":
        text = _extract_docx(content)
    elif kind in ("txt", "md", "csv"):
        text = _extract_text(content)
    else:
        text = ""  # images: no text extraction, Claude handles them natively
    return kind, text[:MAX_EXTRACT_CHARS]


async def store_upload(
    db,
    *,
    user_id: str,
    conversation_id: str,
    filename: str,
    mime_type: str,
    content: bytes,
) -> Dict[str, Any]:
    if len(content) > MAX_BYTES:
        raise ValueError(f"File too large. Max is {MAX_BYTES // (1024*1024)} MB.")
    if mime_type not in SUPPORTED_MIME:
        raise ValueError(
            f"Unsupported file type '{mime_type}'. "
            "Supported: PDF, DOCX, TXT, MD, CSV, PNG, JPEG, WEBP, GIF."
        )
    kind, text = extract(content, mime_type)
    doc_id = str(uuid.uuid4())
    doc = {
        "_id": doc_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "filename": filename,
        "mime_type": mime_type,
        "kind": kind,
        "size": len(content),
        "text": text,
        "text_len": len(text),
        # base64 is only kept for images + PDFs so Claude can ingest them natively
        "b64": base64.b64encode(content).decode("ascii") if kind in ("image", "pdf") else None,
        "created_at": datetime.utcnow(),
    }
    await db.assistant_documents.insert_one(doc)
    return {
        "id": doc_id,
        "filename": filename,
        "kind": kind,
        "mime_type": mime_type,
        "size": len(content),
        "text_len": len(text),
        "has_text": bool(text),
    }


async def list_for_conversation(db, user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
    rows = await db.assistant_documents.find(
        {"user_id": user_id, "conversation_id": conversation_id}
    ).sort("created_at", 1).to_list(50)
    return [{
        "id": r["_id"],
        "filename": r.get("filename"),
        "kind": r.get("kind"),
        "mime_type": r.get("mime_type"),
        "size": r.get("size"),
        "text_len": r.get("text_len", 0),
        "has_text": bool(r.get("text")),
        "created_at": r.get("created_at"),
    } for r in rows]


async def load_full(db, user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
    """Load docs with their text + base64 payloads for passing into the model."""
    return await db.assistant_documents.find(
        {"user_id": user_id, "conversation_id": conversation_id}
    ).sort("created_at", 1).to_list(50)


async def delete_document(db, user_id: str, doc_id: str) -> bool:
    res = await db.assistant_documents.delete_one({"_id": doc_id, "user_id": user_id})
    return res.deleted_count > 0


def build_context_preamble(docs: List[Dict[str, Any]], per_doc_chars: int = 12_000) -> Optional[str]:
    """Return a single string to prepend as a system message so any provider
    (OpenAI / DeepSeek / Grok) can reference the documents. For Claude we ALSO
    pass native image/PDF blocks on top."""
    if not docs:
        return None
    blocks: List[str] = ["The user has attached the following reference documents:"]
    for i, d in enumerate(docs, 1):
        fn = d.get("filename") or f"document {i}"
        kind = d.get("kind") or "file"
        text = (d.get("text") or "").strip()
        header = f"\n--- Document {i}: {fn} ({kind}) ---"
        if not text:
            blocks.append(header + "\n[No extractable text — image or scanned PDF]")
            continue
        snippet = text[:per_doc_chars]
        truncated = " …[truncated]" if len(text) > per_doc_chars else ""
        blocks.append(f"{header}\n{snippet}{truncated}")
    blocks.append(
        "\nWhen the user asks about these documents, quote short excerpts "
        "and cite them by filename. Do not fabricate content not present in the documents."
    )
    return "\n".join(blocks)

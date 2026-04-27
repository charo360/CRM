"""Chunk, embed, and upsert business knowledge documents into Qdrant.

Call index_business_document() whenever business_knowledge fields are saved
(e.g. from the settings PATCH endpoint in server.py).
"""
from __future__ import annotations

import logging
import os
from uuid import uuid4

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 400    # tokens
_CHUNK_OVERLAP = 80  # tokens


def _chunk_text(text: str) -> list:
    """Split text into overlapping token-based chunks. Returns list[str]."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        chunks = []
        i = 0
        while i < len(tokens):
            chunk_tokens = tokens[i: i + _CHUNK_SIZE]
            decoded = enc.decode(chunk_tokens)
            if decoded.strip():
                chunks.append(decoded)
            i += _CHUNK_SIZE - _CHUNK_OVERLAP
        return chunks
    except Exception:
        # Fallback: character-based chunking (no tiktoken)
        size, overlap = 1600, 320
        text = text.strip()
        if not text:
            return []
        if len(text) <= size:
            return [text]
        chunks = []
        i = 0
        while i < len(text):
            chunks.append(text[i: i + size])
            i += size - overlap
        return chunks


async def index_business_document(
    business_id: str,
    doc_text: str,
    doc_type: str = "knowledge",
) -> int:
    """Chunk doc_text, embed all chunks, and upsert into business_knowledge collection.

    Returns the number of chunks indexed. Returns 0 if doc_text is empty or
    OPENAI_API_KEY is not configured.
    """
    if not doc_text or not doc_text.strip():
        return 0
    if not os.getenv("OPENAI_API_KEY", "").strip():
        logger.warning("[rag.indexer] OPENAI_API_KEY not set — skipping indexing")
        return 0

    chunks = _chunk_text(doc_text)
    if not chunks:
        return 0

    try:
        from openai import AsyncOpenAI
        from qdrant_client.models import PointStruct
        from vector_store import get_qdrant

        resp = await AsyncOpenAI().embeddings.create(
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            input=chunks,
        )
        points = [
            PointStruct(
                id=str(uuid4()),
                vector=e.embedding,
                payload={
                    "business_id": business_id,
                    "doc_type": doc_type,
                    "chunk": chunks[i],
                    "chunk_index": i,
                },
            )
            for i, e in enumerate(resp.data)
        ]
        await get_qdrant().upsert(collection_name="business_knowledge", points=points)
        logger.info("[rag.indexer] indexed %d chunks for business %s", len(points), business_id)
        return len(points)
    except Exception as exc:
        logger.error("[rag.indexer] failed to index for business %s: %s", business_id, exc)
        return 0


async def reindex_all_businesses(db) -> None:
    """One-time batch: index all existing users' business_knowledge fields.

    Safe to run multiple times — each run overwrites previous vectors for the
    same business since we always delete-before-insert by business_id filter.
    """
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
    from vector_store import get_qdrant

    count = 0
    async for user in db.users.find({"business_knowledge": {"$exists": True}}, {"_id": 1, "business_knowledge": 1}):
        bk = user.get("business_knowledge") or {}
        if not isinstance(bk, dict):
            continue
        business_id = str(user["_id"])

        # Delete existing vectors for this business first
        try:
            await get_qdrant().delete(
                collection_name="business_knowledge",
                points_selector=FilterSelector(
                    filter=Filter(must=[FieldCondition(key="business_id", match=MatchValue(value=business_id))])
                ),
            )
        except Exception:
            pass

        # Combine all knowledge fields into one document
        parts = []
        for field in ("business_description", "products_services", "pricing_info",
                      "business_hours", "delivery_info", "special_offers", "faqs"):
            val = bk.get(field, "")
            if val:
                parts.append(f"{field.replace('_', ' ').title()}: {val}")
        if parts:
            await index_business_document(business_id, "\n\n".join(parts))
            count += 1

    logger.info("[rag.indexer] reindex_all_businesses complete: %d businesses indexed", count)

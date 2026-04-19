"""Embeddings + semantic search for uploaded documents.

- Chunks long text into ~800-character overlapping windows.
- Embeds chunks with OpenAI `text-embedding-3-small` (1536 dims, cheap/fast).
- Stores chunks + vectors under `assistant_document_chunks`.
- Cosine search returns the top-K chunks for a given query.

Gracefully no-ops if OPENAI_API_KEY is missing — caller falls back to the
text preamble shipped in `documents.build_context_preamble`.
"""
from __future__ import annotations

import logging
import math
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
LONG_DOC_THRESHOLD = 6_000   # characters; above this we chunk + embed
MAX_CHUNKS_PER_DOC = 80


def _embeddings_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Try to end on a paragraph / sentence break for cleaner chunks
        if end < len(text):
            snap = text.rfind("\n\n", start, end)
            if snap == -1 or snap - start < size * 0.4:
                snap = text.rfind(". ", start, end)
            if snap != -1 and snap - start >= size * 0.4:
                end = snap + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
        if len(chunks) >= MAX_CHUNKS_PER_DOC:
            break
    return [c for c in chunks if c]


async def _embed_batch(texts: List[str], timeout: float = 30.0) -> List[List[float]]:
    if not _embeddings_available():
        return []
    key = os.environ["OPENAI_API_KEY"]
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": EMBED_MODEL, "input": texts},
        )
        r.raise_for_status()
        data = r.json()
    return [row["embedding"] for row in data.get("data", [])]


async def embed_query(text: str) -> Optional[List[float]]:
    if not text.strip() or not _embeddings_available():
        return None
    vecs = await _embed_batch([text.strip()])
    return vecs[0] if vecs else None


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


async def ingest_document_chunks(
    db,
    *,
    user_id: str,
    conversation_id: str,
    document_id: str,
    filename: str,
    text: str,
) -> int:
    """Chunk + embed text and persist. Returns # of chunks stored."""
    if not text or len(text) < LONG_DOC_THRESHOLD:
        return 0
    chunks = chunk_text(text)
    if not chunks:
        return 0
    try:
        vectors = await _embed_batch(chunks)
    except Exception as e:
        logger.warning(f"[embeddings] ingest failed for {filename}: {e}")
        return 0
    if not vectors or len(vectors) != len(chunks):
        return 0
    docs = [
        {
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "document_id": document_id,
            "filename": filename,
            "chunk_index": i,
            "text": chunk,
            "vector": vec,
            "created_at": datetime.utcnow(),
        }
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]
    await db.assistant_document_chunks.insert_many(docs)
    return len(docs)


async def search_chunks(
    db,
    *,
    user_id: str,
    conversation_id: str,
    query: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Return top-K chunks for the query, scored by cosine similarity."""
    qvec = await embed_query(query)
    if not qvec:
        return []
    rows = await db.assistant_document_chunks.find(
        {"user_id": user_id, "conversation_id": conversation_id}
    ).to_list(5000)
    if not rows:
        return []
    scored: List[Dict[str, Any]] = []
    for r in rows:
        score = _cosine(qvec, r.get("vector") or [])
        scored.append({
            "filename": r.get("filename"),
            "chunk_index": r.get("chunk_index"),
            "text": r.get("text") or "",
            "score": score,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


async def delete_document_chunks(db, user_id: str, document_id: str) -> int:
    res = await db.assistant_document_chunks.delete_many(
        {"user_id": user_id, "document_id": document_id}
    )
    return res.deleted_count

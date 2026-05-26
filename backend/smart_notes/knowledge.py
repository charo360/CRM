"""
Meeting Knowledge Base — persistent semantic memory built from Smart Notes.

Every time a note is saved, its content is embedded and stored in
`meeting_knowledge_base`. The assistant can then search this store
across all past meetings to answer questions like:
  - "What did we decide about pricing last week?"
  - "What are the open action items from client meetings?"
  - "What was discussed in the Zilo demo on Tuesday?"

Embeddings: OpenAI text-embedding-3-small (1536 dims, ~$0.0001 / 1k tokens).
Storage: MongoDB — no extra infrastructure needed.
"""
from __future__ import annotations

import logging
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

EMBED_MODEL  = "text-embedding-3-small"
COLLECTION   = "meeting_knowledge_base"
CHUNK_SIZE   = 800
CHUNK_OVERLAP= 120


# ── Embedding helpers ──────────────────────────────────────────────────────────

def _available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


async def _embed(texts: List[str]) -> List[List[float]]:
    if not texts or not _available():
        return []
    key = os.environ["OPENAI_API_KEY"]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": EMBED_MODEL, "input": texts},
        )
        r.raise_for_status()
    return [row["embedding"] for row in r.json().get("data", [])]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y; na += x * x; nb += y * y
    return dot / (math.sqrt(na) * math.sqrt(nb)) if na and nb else 0.0


def _chunk(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text) and len(chunks) < 60:
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            snap = text.rfind("\n\n", start, end)
            if snap == -1 or snap - start < CHUNK_SIZE * 0.4:
                snap = text.rfind(". ", start, end)
            if snap != -1 and snap - start >= CHUNK_SIZE * 0.4:
                end = snap + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return [c for c in chunks if c]


# ── Build rich text from a note doc ───────────────────────────────────────────

def _note_to_text(note: Dict[str, Any]) -> str:
    """Flatten a note document into a dense, searchable text block."""
    parts: List[str] = []
    parts.append(f"Meeting: {note.get('title', 'Untitled')}")

    date = note.get("meeting_start") or note.get("created_at")
    if date:
        try:
            d = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
            parts.append(f"Date: {d.strftime('%A %d %B %Y, %H:%M')}")
        except Exception:
            parts.append(f"Date: {date}")

    attendees = note.get("attendees") or []
    if attendees:
        parts.append(f"Attendees: {', '.join(attendees)}")

    summary = (note.get("summary") or "").strip()
    if summary:
        parts.append(f"\nSUMMARY:\n{summary}")

    key_points = note.get("key_points") or []
    if key_points:
        parts.append("\nKEY POINTS:\n" + "\n".join(f"- {p}" for p in key_points))

    action_items = note.get("action_items") or []
    if action_items:
        parts.append("\nACTION ITEMS:\n" + "\n".join(f"- {a}" for a in action_items))

    decisions = note.get("decisions") or []
    if decisions:
        parts.append("\nDECISIONS:\n" + "\n".join(f"- {d}" for d in decisions))

    next_steps = (note.get("next_steps") or "").strip()
    if next_steps:
        parts.append(f"\nNEXT STEPS:\n{next_steps}")

    transcript = (note.get("transcript") or "").strip()
    if transcript:
        # Cap transcript at 4000 chars — enough for semantic context
        parts.append(f"\nTRANSCRIPT (excerpt):\n{transcript[:4000]}")

    return "\n".join(parts)


# ── Public API ─────────────────────────────────────────────────────────────────

async def ingest_note(db, note: Dict[str, Any]) -> int:
    """
    Embed a saved note and store chunks in the knowledge base.
    Replaces any existing chunks for the same note_id.
    Returns number of chunks stored.
    """
    if not _available():
        logger.debug("[meeting-kb] OpenAI key missing — skipping embed")
        return 0

    tid     = note.get("user_id", "")
    note_id = str(note.get("_id", note.get("id", "")))
    if not tid or not note_id:
        return 0

    # Remove old chunks for this note (in case it was re-saved)
    await db[COLLECTION].delete_many({"user_id": tid, "note_id": note_id})

    full_text = _note_to_text(note)
    chunks    = _chunk(full_text)
    if not chunks:
        return 0

    try:
        vectors = await _embed(chunks)
    except Exception as e:
        logger.warning("[meeting-kb] embed failed: %s", e)
        return 0

    if not vectors or len(vectors) != len(chunks):
        return 0

    now  = datetime.now(timezone.utc)
    docs = [
        {
            "_id":          str(uuid.uuid4()),
            "user_id":      tid,
            "note_id":      note_id,
            "note_title":   note.get("title", ""),
            "meeting_date": note.get("meeting_start") or str(now.date()),
            "attendees":    note.get("attendees") or [],
            "chunk_index":  i,
            "text":         chunk,
            "vector":       vec,
            "created_at":   now,
        }
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]

    await db[COLLECTION].insert_many(docs)
    logger.info("[meeting-kb] indexed %d chunks for note %s", len(docs), note_id)
    return len(docs)


async def search_knowledge(
    db,
    user_id: str,
    query: str,
    top_k: int = 6,
) -> List[Dict[str, Any]]:
    """
    Semantic search across all indexed meeting notes for a user.
    Returns top_k most relevant chunks with source metadata.
    """
    if not query.strip():
        return []

    try:
        vecs = await _embed([query.strip()])
    except Exception as e:
        logger.warning("[meeting-kb] embed query failed: %s", e)
        return []

    if not vecs:
        return []
    qvec = vecs[0]

    rows = await db[COLLECTION].find(
        {"user_id": user_id},
        {"vector": 1, "text": 1, "note_title": 1, "meeting_date": 1, "attendees": 1, "note_id": 1},
    ).to_list(3000)

    if not rows:
        return []

    scored = sorted(
        [
            {
                "note_id":      r.get("note_id", ""),
                "note_title":   r.get("note_title", ""),
                "meeting_date": r.get("meeting_date", ""),
                "attendees":    r.get("attendees") or [],
                "text":         r.get("text", ""),
                "score":        _cosine(qvec, r.get("vector") or []),
            }
            for r in rows
        ],
        key=lambda x: x["score"],
        reverse=True,
    )

    # Deduplicate by note — keep only the best chunk per note
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for item in scored:
        nid = item["note_id"]
        if nid not in seen:
            seen.add(nid)
            unique.append(item)
        if len(unique) >= top_k:
            break

    return unique


async def list_recent_notes_summary(
    db,
    user_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return the most recent meeting notes (title, date, summary) — no embeddings needed."""
    docs = await db.smart_notes.find(
        {"user_id": user_id},
        {"title": 1, "meeting_start": 1, "summary": 1, "action_items": 1, "attendees": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)

    return [
        {
            "id":           str(d.get("_id", "")),
            "title":        d.get("title", ""),
            "meeting_date": d.get("meeting_start", ""),
            "summary":      d.get("summary", ""),
            "action_items": d.get("action_items") or [],
            "attendees":    d.get("attendees") or [],
        }
        for d in docs
    ]

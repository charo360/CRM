"""Shared Qdrant async client and embedding helper.

Usage:
    from vector_store import get_qdrant, embed, bootstrap_collections

Call bootstrap_collections() once at FastAPI startup.
Named vector_store (not qdrant_client) to avoid shadowing the installed package.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536  # text-embedding-3-small output dimensions

_client: Any = None  # AsyncQdrantClient


def get_qdrant():
    """Return the shared AsyncQdrantClient, creating it on first call."""
    global _client
    if _client is None:
        from qdrant_client import AsyncQdrantClient
        _client = AsyncQdrantClient(url=QDRANT_URL)
    return _client


async def bootstrap_collections() -> None:
    """Create the two Qdrant collections if they don't exist yet.

    Collections:
        customer_memories   — per-customer long-term memory summaries
        business_knowledge  — chunked, embedded business knowledge docs
    """
    from qdrant_client.models import Distance, VectorParams
    q = get_qdrant()
    existing = {c.name for c in (await q.get_collections()).collections}
    for name in ("customer_memories", "business_knowledge"):
        if name not in existing:
            await q.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            logger.info("[vector_store] created collection: %s", name)


async def embed(text: str) -> list:
    """Embed text using OpenAI text-embedding-3-small. Returns list[float]."""
    from openai import AsyncOpenAI
    resp = await AsyncOpenAI().embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding

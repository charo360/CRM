"""Semantic retrieval of business knowledge chunks from Qdrant.

Returns the top-K chunks whose cosine similarity exceeds RAG_SCORE_THRESHOLD.
Falls back to an empty list if Qdrant is unavailable or OPENAI_API_KEY is missing.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 3
_DEFAULT_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.72"))


async def get_knowledge_chunks(
    business_id: str,
    query: str,
    top_k: int = _DEFAULT_TOP_K,
) -> list:
    """Search business_knowledge for chunks relevant to query.

    Returns list[str] — the raw chunk text. Empty list on error or no match.
    """
    if not query or not query.strip():
        return []
    if not os.getenv("QDRANT_URL") or not os.getenv("OPENAI_API_KEY", "").strip():
        return []

    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        from vector_store import embed, get_qdrant

        threshold = float(os.getenv("RAG_SCORE_THRESHOLD", str(_DEFAULT_THRESHOLD)))
        q_vec = await embed(query)
        client = get_qdrant()
        filt = Filter(must=[FieldCondition(key="business_id", match=MatchValue(value=business_id))])
        hits = await client.search(
            collection_name="business_knowledge",
            query_vector=q_vec,
            query_filter=filt,
            limit=top_k,
            with_payload=True,
        )
        chunks = [r.payload["chunk"] for r in hits if r.score > threshold]
        return chunks
    except Exception as exc:
        logger.warning("[rag.retriever] knowledge retrieval failed: %r", exc)
        return []

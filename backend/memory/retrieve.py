"""Semantic retrieval of long-term customer memories from Qdrant.

Returns the top-K memory summaries most semantically similar to the current query.
Falls back to an empty list if Qdrant/OpenAI is unavailable.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 3


async def get_customer_memories(
    customer_id: str,
    query: str,
    top_k: int = _DEFAULT_TOP_K,
) -> list:
    """Return list[str] of past memory summaries for this customer, most relevant first."""
    if not query or not query.strip():
        return []
    if not os.getenv("QDRANT_URL") or not os.getenv("OPENAI_API_KEY", "").strip():
        return []

    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        from vector_store import embed, get_qdrant

        q_vec = await embed(query)
        results = await get_qdrant().search(
            collection_name="customer_memories",
            query_vector=q_vec,
            query_filter=Filter(
                must=[FieldCondition(key="customer_id", match=MatchValue(value=customer_id))]
            ),
            limit=top_k,
        )
        return [r.payload["summary"] for r in results if r.payload.get("summary")]
    except Exception as exc:
        logger.warning("[memory.retrieve] failed for customer %s: %s", customer_id, exc)
        return []

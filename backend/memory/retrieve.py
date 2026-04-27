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
        client = get_qdrant()
        filt = Filter(must=[FieldCondition(key="customer_id", match=MatchValue(value=customer_id))])
        response = await client.query_points(
            collection_name="customer_memories",
            query=q_vec,
            query_filter=filt,
            limit=top_k,
            with_payload=True,
        )
        return [r.payload["summary"] for r in response.points if r.payload.get("summary")]
    except Exception as exc:
        logger.warning("[memory.retrieve] failed for customer %s: %r", customer_id, exc)
        return []

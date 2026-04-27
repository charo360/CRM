"""Context builder: assembles long-term memory + RAG knowledge in parallel.

Used by run_turn() in orchestrator.py to enrich every Zilo Chat request
with semantic context before the ReAct loop runs.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def build_context(
    user_id: str,
    business_id: str,
    user_message: str,
) -> dict:
    """Run memory + RAG retrieval in parallel and return a context dict.

    Returns:
        {
            "long_term_memories": list[str],   # from customer_memories collection
            "knowledge_chunks":   list[str],   # from business_knowledge collection
        }
    Both lists are empty when Qdrant/OpenAI is unavailable (graceful fallback).
    """
    try:
        from memory.retrieve import get_customer_memories
        from rag.retriever import get_knowledge_chunks

        memories, knowledge = await asyncio.gather(
            get_customer_memories(user_id, user_message),
            get_knowledge_chunks(business_id, user_message),
        )
        return {"long_term_memories": memories, "knowledge_chunks": knowledge}
    except Exception as exc:
        logger.warning("[context_builder] retrieval failed: %s", exc)
        return {"long_term_memories": [], "knowledge_chunks": []}


def format_context_block(ctx: dict) -> str:
    """Format the context dict into a system message string for injection."""
    parts = []
    memories = ctx.get("long_term_memories") or []
    knowledge = ctx.get("knowledge_chunks") or []

    if memories:
        bullet_list = "\n".join(f"- {m}" for m in memories)
        parts.append(f"**What you know about this user (from past sessions):**\n{bullet_list}")

    if knowledge:
        bullet_list = "\n".join(f"- {c}" for c in knowledge)
        parts.append(f"**Relevant business knowledge:**\n{bullet_list}")

    return "\n\n".join(parts)

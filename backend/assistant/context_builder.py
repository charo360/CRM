"""Context builder: assembles long-term memory + RAG knowledge in parallel.

Used by run_turn() in orchestrator.py to enrich every Zilo Chat request
with semantic context before the ReAct loop runs.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def build_context(
    db,
    user_id: str,
    business_id: str,
    user_message: str,
) -> dict:
    """Run memory + RAG retrieval in parallel and return a context dict.

    Returns:
        {
            "long_term_memories": list[str],      # from customer_memories collection
            "knowledge_chunks":   list[str],      # from business_knowledge collection
            "owner_preferences":  list[str],      # from owner_preferences collection
            "conversation_memory": dict,          # from conversation_memory collection
        }
    All lists are empty when Qdrant/OpenAI is unavailable (graceful fallback).
    """
    try:
        from memory.retrieve import get_customer_memories
        from rag.retriever import get_knowledge_chunks
        from memory.owner_prefs import get_owner_preferences
        from memory.conversation_memory import load_conversation_memory

        memories, knowledge, owner_prefs, conv_memory = await asyncio.gather(
            get_customer_memories(user_id, user_message),
            get_knowledge_chunks(business_id, user_message),
            get_owner_preferences(business_id, user_message),
            load_conversation_memory(db, business_id),
        )
        return {
            "long_term_memories": memories,
            "knowledge_chunks": knowledge,
            "owner_preferences": owner_prefs,
            "conversation_memory": conv_memory,
        }
    except Exception as exc:
        logger.warning("[context_builder] retrieval failed: %s", exc)
        return {
            "long_term_memories": [],
            "knowledge_chunks": [],
            "owner_preferences": [],
            "conversation_memory": {},
        }


def format_context_block(ctx: dict) -> str:
    """Format the context dict into a system message string for injection."""
    parts = []
    memories = ctx.get("long_term_memories") or []
    knowledge = ctx.get("knowledge_chunks") or []
    owner_prefs = ctx.get("owner_preferences") or []
    conv_memory = ctx.get("conversation_memory") or {}

    # Conversation memory comes FIRST — this is what makes the agent remember across sessions
    if conv_memory:
        from memory.conversation_memory import format_memory_context
        memory_text = format_memory_context(conv_memory)
        if memory_text:
            parts.append(
                "**Context from previous sessions (you already know this — never ask again):**\n"
                + memory_text
            )

    # Owner preferences come second — use to personalise suggestions, not to override decisions
    if owner_prefs:
        bullet_list = "\n".join(f"- {p}" for p in owner_prefs)
        parts.append(
            "**What you know about this owner's working style (use to make smarter suggestions "
            "and pre-fill defaults — but always show options and let the owner decide):**\n"
            + bullet_list
        )

    if memories:
        bullet_list = "\n".join(f"- {m}" for m in memories)
        parts.append(f"**What you know about this user (from past sessions):**\n{bullet_list}")

    if knowledge:
        bullet_list = "\n".join(f"- {c}" for c in knowledge)
        parts.append(f"**Relevant business knowledge:**\n{bullet_list}")

    return "\n\n".join(parts)

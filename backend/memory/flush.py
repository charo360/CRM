"""Async memory flush: summarize the last N turns and upsert to Qdrant.

Called as a background task (asyncio.create_task) — never blocks the response.
Fires every MEMORY_FLUSH_EVERY turns (default: 10).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)


async def flush_to_long_term(
    customer_id: str,
    business_id: str,
    turns: list,
) -> None:
    """Summarize `turns` and upsert the summary as a vector into customer_memories.

    `turns` should be a list of OpenAI-format message dicts:
        [{"role": "user"|"assistant", "content": "..."}]
    No-ops if OPENAI_API_KEY or QDRANT_URL is not configured.
    """
    if not os.getenv("OPENAI_API_KEY", "").strip() or not os.getenv("QDRANT_URL"):
        return
    if not turns:
        return

    try:
        # Build a compact text of the turns for the summarizer
        text_parts = []
        for t in turns:
            role = t.get("role", "")
            content = (t.get("content") or "")
            if isinstance(content, str) and content.strip():
                label = "Customer" if role == "user" else "Agent"
                text_parts.append(f"{label}: {content[:300]}")
        if not text_parts:
            return
        turns_text = "\n".join(text_parts)

        # Summarize with a lightweight LLM call (no tools needed)
        from assistant.models import chat_with_tools
        resp = await chat_with_tools(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract key facts from this conversation segment. "
                        "Output 3-5 concise bullet points covering: "
                        "customer name/identity, preferences, complaints, orders placed, "
                        "decisions made, and any important context. Be brief."
                    ),
                },
                {"role": "user", "content": turns_text},
            ],
            tools=[],
            temperature=0.2,
        )
        summary = (resp.get("content") or "").strip()
        if not summary:
            return

        # Embed the summary
        from vector_store import embed, get_qdrant
        from qdrant_client.models import PointStruct

        vector = await embed(summary)
        await get_qdrant().upsert(
            collection_name="customer_memories",
            points=[
                PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "customer_id": customer_id,
                        "business_id": business_id,
                        "summary": summary,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
            ],
        )
        logger.info(
            "[memory.flush] flushed %d turns for customer %s", len(turns), customer_id
        )
    except Exception as exc:
        logger.warning("[memory.flush] failed for customer %s: %s", customer_id, exc)

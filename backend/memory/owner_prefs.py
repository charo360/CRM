"""Owner preference memory — learns the business owner's working style across sessions.

Separate from customer_memories (which tracks end-customer facts).
This tracks the OWNER's own preferences, habits, and patterns as they use Zilo Chat.

Examples of what gets stored:
  - "Owner always prefers Instagram Feed format over Stories"
  - "Owner uses dark background on all ad creatives"
  - "Owner's tone: casual and punchy, never corporate"
  - "Owner typically targets 18-25 streetwear audience"
  - "Owner prefers broadcast messages under 3 sentences"
  - "Owner usually runs Meta Ads campaigns, not Google"

Qdrant collection: owner_preferences
  payload fields: business_id, summary, category, timestamp

Categories:
  design      — visual style, colors, format preferences
  content     — tone, length, hashtag style
  campaigns   — preferred channels, budget patterns
  workflow    — which agents they use, task patterns
  audience    — target customer profile
  general     — anything else
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

_COLLECTION = "owner_preferences"

# How many preference memories to retrieve per query
_DEFAULT_TOP_K = 4


async def flush_owner_preferences(
    business_id: str,
    turns: list,
    agent_id: str = "general",
) -> None:
    """Summarize turns into owner preference facts and store in Qdrant.

    Called as a background task from the orchestrator.
    Only stores substantive preference signals — skips short/generic exchanges.
    No-ops if QDRANT_URL or OPENAI_API_KEY is not set.
    """
    if not os.getenv("QDRANT_URL") or not os.getenv("OPENAI_API_KEY", "").strip():
        return
    if not turns:
        return

    try:
        text_parts = []
        for t in turns:
            role = t.get("role", "")
            content = t.get("content") or ""
            if isinstance(content, str) and content.strip() and role in ("user", "assistant"):
                label = "Owner" if role == "user" else "Zilo"
                text_parts.append(f"{label}: {content[:400]}")
        if not text_parts or len(text_parts) < 2:
            return
        turns_text = "\n".join(text_parts)

        from assistant.models import chat_with_tools
        resp = await chat_with_tools(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are analyzing a conversation between a business owner and their AI assistant.\n"
                        "Extract working-style observations that will help the AI make smarter, more relevant "
                        "SUGGESTIONS in future sessions — not rules to blindly enforce.\n\n"
                        "The goal: when the owner asks for help next time, the AI should already know their "
                        "tendencies and offer tailored options — but still present choices, not decide for them.\n\n"
                        "Focus on:\n"
                        "- Design tendencies (colors, format, style they gravitate toward)\n"
                        "- Content tendencies (tone, length, emoji/hashtag style they like)\n"
                        "- Channel tendencies (which platforms they use most — Meta, WhatsApp, email, etc.)\n"
                        "- Audience tendencies (who their typical customers are)\n"
                        "- Workflow tendencies (tasks they return to often, agents they use)\n\n"
                        "Rules:\n"
                        "- Only note tendencies that are clearly stated or strongly implied\n"
                        "- Skip one-off tasks like 'show me revenue' — those are not tendencies\n"
                        "- Write each as a short observation starting with 'Owner tends to' or 'Owner usually' or 'Owner prefers'\n"
                        "- Output 0-4 bullet points. If there are no clear tendencies, output: NONE\n"
                        "- Each bullet must be under 20 words.\n\n"
                        "Examples of GOOD output:\n"
                        "- Owner tends to use Instagram Feed format rather than Stories\n"
                        "- Owner usually prefers dark backgrounds with white text in ad creatives\n"
                        "- Owner typically targets 18-25 streetwear audience for campaigns\n"
                        "- Owner prefers short broadcast messages, usually under 3 sentences\n\n"
                        "Examples of BAD output (skip these):\n"
                        "- Owner asked about revenue (this is a one-off task)\n"
                        "- Owner wants to see customers (this is a task, not a tendency)"
                    ),
                },
                {"role": "user", "content": f"Agent used: {agent_id}\n\n{turns_text}"},
            ],
            tools=[],
            temperature=0.1,
        )
        raw = (resp.get("content") or "").strip()
        if not raw or raw.upper() == "NONE" or raw.startswith("NONE"):
            return

        # Parse bullet lines
        lines = [
            line.lstrip("-•* ").strip()
            for line in raw.splitlines()
            if line.strip() and not line.strip().upper().startswith("NONE")
        ]
        prefs = [l for l in lines if len(l) > 10 and l.lower().startswith("owner")]
        if not prefs:
            return

        from vector_store import embed, get_qdrant
        from qdrant_client.models import PointStruct

        client = get_qdrant()
        points = []
        for pref in prefs:
            category = _classify_preference(pref)
            vec = await embed(pref)
            points.append(PointStruct(
                id=str(uuid4()),
                vector=vec,
                payload={
                    "business_id": business_id,
                    "summary": pref,
                    "category": category,
                    "agent": agent_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            ))

        if points:
            await client.upsert(collection_name=_COLLECTION, points=points)
            logger.info(
                "[owner_prefs.flush] stored %d preferences for business %s",
                len(points), business_id,
            )
    except Exception as exc:
        logger.debug("[owner_prefs.flush] failed (non-critical): %s", exc)


async def get_owner_preferences(
    business_id: str,
    query: str,
    top_k: int = _DEFAULT_TOP_K,
) -> list[str]:
    """Retrieve the most relevant owner preferences for the current query.

    Returns list[str] of preference summaries, most relevant first.
    Empty list if Qdrant/OpenAI is unavailable.
    """
    if not query or not query.strip():
        return []
    if not os.getenv("QDRANT_URL") or not os.getenv("OPENAI_API_KEY", "").strip():
        return []
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        from vector_store import embed, get_qdrant

        q_vec = await embed(query)
        client = get_qdrant()
        filt = Filter(must=[FieldCondition(key="business_id", match=MatchValue(value=business_id))])
        hits = await client.search(
            collection_name=_COLLECTION,
            query_vector=q_vec,
            query_filter=filt,
            limit=top_k,
            with_payload=True,
        )
        return [r.payload["summary"] for r in hits if r.payload.get("summary") and r.score > 0.70]
    except Exception as exc:
        logger.debug("[owner_prefs.retrieve] failed (non-critical): %r", exc)
        return []


async def get_all_owner_preferences(
    business_id: str,
    limit: int = 30,
) -> list[dict]:
    """Return all stored preferences for a business (used by suggestions API).

    Returns list of {summary, category, timestamp} dicts sorted by timestamp desc.
    """
    if not os.getenv("QDRANT_URL"):
        return []
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        from vector_store import get_qdrant

        client = get_qdrant()
        filt = Filter(must=[FieldCondition(key="business_id", match=MatchValue(value=business_id))])
        results, _ = await client.scroll(
            collection_name=_COLLECTION,
            scroll_filter=filt,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        rows = [
            {
                "summary": r.payload.get("summary", ""),
                "category": r.payload.get("category", "general"),
                "agent": r.payload.get("agent", "general"),
                "timestamp": r.payload.get("timestamp", ""),
            }
            for r in results
            if r.payload.get("summary")
        ]
        rows.sort(key=lambda x: x["timestamp"], reverse=True)
        return rows
    except Exception as exc:
        logger.debug("[owner_prefs.get_all] failed (non-critical): %r", exc)
        return []


def _classify_preference(text: str) -> str:
    """Bucket a preference string into a category."""
    t = text.lower()
    if any(w in t for w in ("color", "background", "dark", "light", "font", "design", "visual",
                             "layout", "format", "instagram feed", "stories", "carousel", "template")):
        return "design"
    if any(w in t for w in ("tone", "casual", "formal", "emoji", "hashtag", "caption", "copy",
                             "sentence", "short", "long", "punchy", "corporate", "professional")):
        return "content"
    if any(w in t for w in ("meta", "google", "facebook", "ads", "campaign", "budget", "roas",
                             "ad creative", "audience", "target", "retarget", "shopify")):
        return "campaigns"
    if any(w in t for w in ("broadcast", "whatsapp", "message", "customer", "follow", "loyalty")):
        return "workflow"
    if any(w in t for w in ("18", "25", "age", "demographic", "streetwear", "women", "men",
                             "young", "audience", "segment")):
        return "audience"
    return "general"

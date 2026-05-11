"""
Zilo Autoblogging — Topic Generator.
Analyses a client's WhatsApp message history to derive high-intent blog topics.
"""
import os
import logging
from typing import Optional
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_client: Optional[Anthropic] = None


def _get_claude() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


async def generate_topic_from_chats(db, client_id: str) -> str:
    """
    Analyses a client's recent WhatsApp customer messages to surface the best
    blog topic — what customers are actually asking about = high-intent keywords.
    Falls back to an industry/location-based topic if no chat history exists.
    """
    recent_chats = await db.messages.find(
        {"client_id": client_id, "role": "customer"},
        {"content": 1},
    ).sort("created_at", -1).limit(50).to_list(None)

    blog = await db.blogs.find_one({"client_id": client_id})
    business_name = blog.get("business_name", "this business") if blog else "this business"
    location = blog.get("location", "Nairobi") if blog else "Nairobi"
    industry = blog.get("industry", "services") if blog else "services"

    if not recent_chats:
        fallback = (
            f"Top {industry} services offered by {business_name} in {location}"
        )
        logger.info(f"[topic_gen] No chat history for {client_id}, using fallback topic")
        return fallback

    chat_text = "\n".join(m["content"] for m in recent_chats if m.get("content"))

    response = _get_claude().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    "Based on these customer questions from a WhatsApp business chat, "
                    "suggest ONE specific blog post topic that would answer common questions "
                    "AND rank on Google.\n\n"
                    f"Customer questions:\n{chat_text}\n\n"
                    "Return ONLY the blog post title. Make it specific, local, and SEO-friendly.\n"
                    'Example: "Best Hair Braiding Styles in Westlands Nairobi 2025"'
                ),
            }
        ],
    )

    topic = response.content[0].text.strip()
    logger.info(f"[topic_gen] Generated topic for {client_id}: {topic}")
    return topic

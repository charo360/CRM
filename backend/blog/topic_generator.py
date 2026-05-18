"""
Zilo Autoblogging — Topic Generator.
Picks the best blog topic using real DataForSEO search data.
Falls back to WhatsApp chat history analysis if DataForSEO is unavailable.
"""
import logging
from typing import Optional
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_client: Optional[Anthropic] = None


def _get_claude() -> Anthropic:
    import os
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


async def research_seo_topic(db, client_id: str) -> dict:
    """
    Picks the best blog topic for a client using DataForSEO keyword research.
    Returns:
        {
            "topic": str,            # human-readable topic/angle for the post
            "focus_keyword": str,    # primary SEO keyword (highest value)
            "keywords": list[str],   # top related keywords with real search volume
        }
    Falls back to chat-based topic if DataForSEO credentials are missing or API fails.
    """
    blog = await db.blogs.find_one({"client_id": client_id})
    industry = blog.get("industry", "services") if blog else "services"
    location = blog.get("location", "") if blog else ""
    business_name = blog.get("business_name", "") if blog else ""

    # Always get a chat-based seed topic as fallback
    fallback_topic = await generate_topic_from_chats(db, client_id)

    try:
        from dataforseo_service import get_keyword_suggestions, get_location_code

        location_code = get_location_code(location)
        seed = f"{industry} {location}"

        result = await get_keyword_suggestions(
            seed_keyword=seed,
            location_code=location_code,
            limit=80,
        )

        suggestions = result.get("suggestions", [])
        if not suggestions:
            logger.info("[topic_gen] DataForSEO returned no suggestions for '%s'", seed)
            return {"topic": fallback_topic, "focus_keyword": fallback_topic, "keywords": []}

        # Score = search_volume / (competition + 0.1)
        # Prefer: meaningful volume (>50), not too competitive (<0.75)
        scored = [
            {**s, "_score": s.get("search_volume", 0) / (s.get("competition", 0.5) + 0.1)}
            for s in suggestions
            if s.get("search_volume", 0) > 50
        ]

        if not scored:
            scored = [
                {**s, "_score": s.get("search_volume", 0) / (s.get("competition", 0.5) + 0.1)}
                for s in suggestions
            ]

        scored.sort(key=lambda s: s["_score"], reverse=True)

        focus = scored[0]["keyword"]
        top_keywords = [s["keyword"] for s in scored[:6]]

        # Turn the winning keyword into a blog topic angle using the chat-derived context
        topic = _build_topic_from_keyword(focus, business_name, location, fallback_topic)

        logger.info(
            "[topic_gen] DataForSEO → focus='%s' vol=%d comp=%.2f | topic='%s'",
            focus,
            scored[0].get("search_volume", 0),
            scored[0].get("competition", 0),
            topic,
        )

        return {
            "topic": topic,
            "focus_keyword": focus,
            "keywords": top_keywords,
        }

    except Exception as e:
        logger.warning("[topic_gen] DataForSEO unavailable (%s), using chat-derived topic", e)
        return {"topic": fallback_topic, "focus_keyword": fallback_topic, "keywords": []}


def _build_topic_from_keyword(focus_keyword: str, business_name: str, location: str, fallback: str) -> str:
    """
    Converts a raw keyword like 'restaurants nairobi' into a
    blog-worthy topic angle. Uses a small Claude call.
    """
    try:
        resp = _get_claude().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{
                "role": "user",
                "content": (
                    f"Turn this SEO keyword into a specific, engaging blog post topic.\n"
                    f"Keyword: {focus_keyword}\n"
                    f"Business: {business_name} in {location}\n"
                    f"Return ONLY the blog post title. Be specific, local, practical.\n"
                    f"Example output: '7 Things to Know Before Hiring a Plumber in Westlands Nairobi'"
                ),
            }],
        )
        topic = resp.content[0].text.strip().strip('"').strip("'")
        return topic if topic else fallback
    except Exception:
        return fallback


async def generate_topic_from_chats(db, client_id: str) -> str:
    """
    Analyses a client's recent WhatsApp customer messages to surface the best
    blog topic. Falls back to an industry/location-based topic if no chat history.
    """
    recent_chats = await db.messages.find(
        {"client_id": client_id, "role": "customer"},
        {"content": 1},
    ).sort("created_at", -1).limit(50).to_list(None)

    blog = await db.blogs.find_one({"client_id": client_id})
    business_name = blog.get("business_name", "this business") if blog else "this business"
    location = blog.get("location", "") if blog else ""
    industry = blog.get("industry", "services") if blog else "services"

    if not recent_chats:
        fallback = f"Top {industry} services offered by {business_name} in {location}"
        logger.info("[topic_gen] No chat history for %s, using fallback topic", client_id)
        return fallback

    chat_text = "\n".join(m["content"] for m in recent_chats if m.get("content"))

    response = _get_claude().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                "Based on these customer questions from a WhatsApp business chat, "
                "suggest ONE specific blog post topic that would answer common questions "
                "AND rank on Google.\n\n"
                f"Customer questions:\n{chat_text}\n\n"
                "Return ONLY the blog post title. Make it specific, local, and SEO-friendly.\n"
                'Example: "Best Hair Braiding Styles in Westlands Nairobi 2025"'
            ),
        }],
    )

    topic = response.content[0].text.strip()
    logger.info("[topic_gen] Generated topic for %s: %s", client_id, topic)
    return topic

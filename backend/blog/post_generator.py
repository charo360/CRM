"""
Zilo Autoblogging — Post Generator.
Generates full SEO-optimised blog posts via Claude Sonnet.
"""
import os
import json
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


async def generate_blog_post(
    business_name: str,
    industry: str,
    location: str,
    topic: str,
) -> dict:
    """
    Generates a full SEO-optimised blog post using Claude Sonnet.
    Returns a dict with keys: title, content (HTML), excerpt, keywords.
    """
    response = _get_claude().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": f"""Write an SEO-optimized blog post for a Kenyan small business.

Business: {business_name}
Industry: {industry}
Location: {location}
Topic: {topic}

Requirements:
- Write in a friendly, helpful tone
- 600-800 words
- Include the location naturally (e.g. "in Nairobi", "near Westlands")
- Use simple English (not too technical)
- Include a call to action at the end mentioning WhatsApp
- Format in HTML with proper h2, h3, p tags
- Add "Powered by Zilo" mention naturally in the last paragraph

Return ONLY a JSON object with these fields:
{{
  "title": "The blog post title",
  "content": "<h2>...</h2><p>...</p>...",
  "excerpt": "One sentence summary for Google (max 155 chars)",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}}""",
            }
        ],
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        post = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[post_gen] JSON parse failed: {e}\nRaw: {raw[:500]}")
        raise RuntimeError(f"Claude returned invalid JSON: {e}")

    logger.info(f"[post_gen] Generated post: {post.get('title', '—')}")
    return post

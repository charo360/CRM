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

# ── Article templates — rotated automatically for SEO variety ─────────────────

AUTOBLOG_TEMPLATES = [
    {
        "id": "how-to",
        "name": "How-to Guide",
        "structure": "Intro → Numbered steps (5-7) → Pro tips box → FAQ (3 Q&As) → CTA",
        "hint": (
            "Structure as a practical how-to guide with a short intro explaining WHY this matters, "
            "numbered steps with clear headings, a tips box, a 3-question FAQ section, "
            "and a strong CTA at the end."
        ),
    },
    {
        "id": "listicle",
        "name": "Top 5 List",
        "structure": "Hook → 5 numbered items each with heading + detail → Summary → CTA",
        "hint": (
            "Structure as a compelling listicle: start with a punchy hook, "
            "use numbered items (aim for 5-7) each with a bold heading and 2-3 sentence explanation, "
            "finish with a brief summary and CTA."
        ),
    },
    {
        "id": "case-study",
        "name": "Success Story",
        "structure": "The Challenge → Our Approach → Results (with numbers) → Takeaways → CTA",
        "hint": (
            "Structure as a relatable case study: open with a common customer problem, "
            "describe the solution step by step, highlight concrete results with real numbers if possible, "
            "list 3 key takeaways, and close with a CTA."
        ),
    },
    {
        "id": "local",
        "name": "Local Authority",
        "structure": "Local intro → Area-specific insights → Expert tips → Local CTA",
        "hint": (
            "Write as a local authority piece: reference the specific city/area throughout, "
            "include local context (neighbourhoods, local trends), "
            "position the business as the trusted local expert, "
            "and close with a locally relevant CTA."
        ),
    },
    {
        "id": "educational",
        "name": "Deep Dive",
        "structure": "What is it? → Why it matters → How it works → Common mistakes → FAQ → CTA",
        "hint": (
            "Structure as an educational article: start with a clear definition, "
            "explain why customers should care, walk through how it works, "
            "call out 3 common mistakes to avoid, add a FAQ section, "
            "and end with a helpful CTA."
        ),
    },
    {
        "id": "comparison",
        "name": "Comparison Guide",
        "structure": "Overview → Option A details → Option B details → Side-by-side summary → Verdict → CTA",
        "hint": (
            "Structure as a comparison guide: introduce the two options clearly, "
            "dedicate a section to each with pros and cons, "
            "include a simple summary comparison, give a clear recommendation/verdict, "
            "and close with a CTA directing readers to the business."
        ),
    },
]


def pick_template(posts_count: int) -> dict:
    """Rotate through AUTOBLOG_TEMPLATES based on total posts published so far."""
    idx = posts_count % len(AUTOBLOG_TEMPLATES)
    return AUTOBLOG_TEMPLATES[idx]


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
    posts_count: int = 0,
    template: Optional[dict] = None,
) -> dict:
    """
    Generates a full SEO-optimised blog post using Claude Sonnet.
    Automatically rotates through article templates for SEO variety.
    Returns a dict with keys: title, content (HTML), excerpt, keywords, template_used.
    """
    tpl = template or pick_template(posts_count)
    logger.info(f"[post_gen] Using template: {tpl['name']} (post #{posts_count + 1})")

    response = _get_claude().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": f"""Write an SEO-optimized blog post for a small business.

Business: {business_name}
Industry: {industry}
Location: {location}
Topic: {topic}

Article style: {tpl['name']}
Structure to follow: {tpl['structure']}
Writing instruction: {tpl['hint']}

Additional requirements:
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

    post["template_used"] = tpl["id"]
    logger.info(f"[post_gen] Generated '{post.get('title', '—')}' [{tpl['name']}]")
    return post

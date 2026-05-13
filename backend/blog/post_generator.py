"""
Zilo Autoblogging — Post Generator.
Generates full SEO-optimised blog posts via Claude using WordPress Gutenberg block format.
Every post includes callout boxes, pull quotes, two-column layouts, WooCommerce product
embeds, and a WhatsApp CTA — making each post look premium and visually rich.
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
        "structure": "Punchy hook → Why it matters callout → Numbered steps (5-7, each an H2) → Pro tips column layout → FAQ pull quote → CTA",
        "hint": (
            "Open with a bold hook sentence. Use a callout box for a key stat or insight. "
            "Number your steps clearly with H2 headings. Add a two-column 'Do this / Not that' "
            "or 'Fast tip / Pro tip' section. Pull the single best sentence as a pull quote. "
            "End with the WooCommerce products and WhatsApp CTA."
        ),
    },
    {
        "id": "listicle",
        "name": "Top 5 List",
        "structure": "Hook → Callout stat → 5 numbered items (H2 each) → Two-column summary → Pull quote → Products → CTA",
        "hint": (
            "Start with a scroll-stopping hook. Use a callout box with the most surprising stat. "
            "Each list item gets its own H2 and 2-3 sentences. Use a two-column layout near the "
            "end to compare two angles or summarise top picks. Pull the most shareable line as a "
            "pull quote. End with products and CTA."
        ),
    },
    {
        "id": "case-study",
        "name": "Success Story",
        "structure": "The problem hook → Callout with key numbers → Challenge H2 → Solution H2 → Results column layout → Takeaways → Pull quote → CTA",
        "hint": (
            "Open by naming a real, relatable customer problem. Callout box: highlight the before/after "
            "numbers. Walk through challenge, approach, and results. Use a two-column layout for "
            "'Before vs After' or '3 key results'. Pull the most impactful result as a pull quote. "
            "End with products and CTA."
        ),
    },
    {
        "id": "local",
        "name": "Local Authority",
        "structure": "Local hook → Local stat callout → Area insights H2s → Expert tips column → Local pull quote → Products → CTA",
        "hint": (
            "Reference the specific city/area in the first sentence and throughout. Callout box: "
            "a local market stat or trend. Use neighbourhood names and local context. Two-column "
            "layout for 'What locals love / What visitors discover'. Pull a strongly local insight "
            "as the pull quote. Position the business as THE trusted local expert."
        ),
    },
    {
        "id": "educational",
        "name": "Deep Dive",
        "structure": "Definition hook → Callout with key fact → What/Why/How H2s → Common mistakes column → FAQ pull quote → Products → CTA",
        "hint": (
            "Open by answering 'what is this and why should I care' in one punchy sentence. "
            "Callout box: the most important fact readers don't know. Walk through what, why, how. "
            "Two-column layout for 'Common mistakes vs Smart approach'. Pull the single most "
            "educational sentence as a pull quote. End with products and CTA."
        ),
    },
    {
        "id": "comparison",
        "name": "Comparison Guide",
        "structure": "Stakes hook → Callout insight → Option A H2 → Option B H2 → Side-by-side column → Verdict pull quote → Products → CTA",
        "hint": (
            "Open by raising the stakes of choosing wrong. Callout box: a surprising comparison stat. "
            "Give each option its own H2 section with pros and cons. Use a two-column layout as the "
            "side-by-side summary. Pull the verdict as the pull quote — make it decisive. "
            "End with products and CTA."
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
    Generates a premium SEO-optimised blog post using Claude.
    Output uses WordPress Gutenberg block format with callout boxes, pull quotes,
    two-column layouts, WooCommerce product embeds, and a WhatsApp CTA.
    """
    tpl = template or pick_template(posts_count)
    logger.info(f"[post_gen] Using template: {tpl['name']} (post #{posts_count + 1})")

    response = _get_claude().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[
            {
                "role": "user",
                "content": f"""You are a world-class blog writer for small businesses. Write a premium blog post in WordPress Gutenberg block format.

Business: {business_name}
Industry: {industry}
Location: {location}
Topic: {topic}

Article style: {tpl['name']}
Structure: {tpl['structure']}
Writing guidance: {tpl['hint']}

GUTENBERG BLOCK FORMAT — use exactly these patterns:

Standard paragraph:
<!-- wp:paragraph -->
<p>Your text here.</p>
<!-- /wp:paragraph -->

H2 heading (main sections):
<!-- wp:heading {{"level":2}} -->
<h2>Section Heading</h2>
<!-- /wp:heading -->

H3 heading (subsections):
<!-- wp:heading {{"level":3}} -->
<h3>Subsection</h3>
<!-- /wp:heading -->

CALLOUT BOX (use 1-2 times — for key stats or insights that stop the reader):
<!-- wp:group {{"backgroundColor":"pale-cyan-blue","style":{{"spacing":{{"padding":{{"top":"24px","bottom":"24px","left":"24px","right":"24px"}}}}}},"layout":{{"type":"constrained"}}}} -->
<div class="wp-block-group has-pale-cyan-blue-background-color has-background" style="padding-top:24px;padding-right:24px;padding-bottom:24px;padding-left:24px"><!-- wp:paragraph -->
<p>💡 <strong>Your key insight or stat</strong> — supporting detail that makes this feel authoritative and useful.</p>
<!-- /wp:paragraph --></div>
<!-- /wp:group -->

PULL QUOTE (use exactly once — the single most powerful sentence in the article):
<!-- wp:pullquote -->
<figure class="wp-block-pullquote"><blockquote><p>Your most shareable, impactful sentence that makes readers stop scrolling.</p></blockquote></figure>
<!-- /wp:pullquote -->

SECTION SEPARATOR (use between major sections):
<!-- wp:separator {{"className":"is-style-wide"}} -->
<hr class="wp-block-separator has-alpha-channel-opacity is-style-wide"/>
<!-- /wp:separator -->

TWO-COLUMN LAYOUT (use exactly once — to break visual rhythm and compare two angles):
<!-- wp:columns -->
<div class="wp-block-columns"><!-- wp:column -->
<div class="wp-block-column"><!-- wp:heading {{"level":3}} -->
<h3>Left Column Heading</h3><!-- /wp:heading --><!-- wp:paragraph -->
<p>Left column content — 2-3 sentences.</p><!-- /wp:paragraph --></div><!-- /wp:column --><!-- wp:column -->
<div class="wp-block-column"><!-- wp:heading {{"level":3}} -->
<h3>Right Column Heading</h3><!-- /wp:heading --><!-- wp:paragraph -->
<p>Right column content — 2-3 sentences.</p><!-- /wp:paragraph --></div><!-- /wp:column --></div>
<!-- /wp:columns -->

WOOCOMMERCE PRODUCTS (use near end — embeds the business's own shop products):
<!-- wp:heading {{"level":3}} -->
<h3>Browse Our Products</h3>
<!-- /wp:heading -->
<!-- wp:shortcode -->
[products limit="3" columns="3" orderby="popularity"]
<!-- /wp:shortcode -->

WHATSAPP CTA BUTTON (use as the final element — green WhatsApp button):
<!-- wp:buttons {{"layout":{{"type":"flex","justifyContent":"center"}}}} -->
<div class="wp-block-buttons"><!-- wp:button {{"style":{{"border":{{"radius":"8px"}},"color":{{"background":"#25D366","text":"#ffffff"}}}}}} -->
<div class="wp-block-button"><a class="wp-block-button__link has-text-color has-background" style="border-radius:8px;background-color:#25D366;color:#ffffff" href="https://wa.me/" target="_blank" rel="noreferrer noopener">💬 Chat with us on WhatsApp</a></div>
<!-- /wp:button --></div>
<!-- /wp:buttons -->

CONTENT RULES:
- Total 750-950 words of readable content
- Include the location naturally throughout (e.g. "in {location}", "across {location}")
- Friendly, expert tone — helpful, not salesy
- Real specific advice, not generic filler
- Mention "Powered by Zilo" naturally in the second-to-last paragraph
- The article must feel written by a real local expert

Return ONLY valid JSON — no markdown fences, no explanation:
{{
  "title": "SEO title with location keyword — max 65 chars",
  "content": "<!-- wp:paragraph -->...[complete Gutenberg block content]...",
  "excerpt": "Meta description for Google — max 155 chars, includes {location}",
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

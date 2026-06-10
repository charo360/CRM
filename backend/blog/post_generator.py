"""
Zilo Autoblogging — Post Generator.
Generates full SEO-optimised blog posts via Claude using WordPress Gutenberg block format.
Every post includes callout boxes, pull quotes, two-column layouts, WooCommerce product
embeds, and a WhatsApp CTA — making each post look premium and visually rich.
Keywords are sourced from DataForSEO real search data, not guessed.
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


def _format_keyword_brief(focus_keyword: str, seo_keywords: list) -> str:
    """Build the keyword section of the prompt from real DataForSEO data."""
    if not focus_keyword and not seo_keywords:
        return ""
    lines = []
    if focus_keyword:
        lines.append(f"PRIMARY KEYWORD (use in title, first paragraph, at least 2 H2s, meta): {focus_keyword}")
    secondary = [k for k in (seo_keywords or []) if k != focus_keyword][:5]
    if secondary:
        lines.append(f"SECONDARY KEYWORDS (weave in naturally, don't force): {', '.join(secondary)}")
    lines.append("These are real keywords people search on Google — use them where they fit naturally.")
    return "\n".join(lines)


async def generate_blog_post(
    business_name: str,
    industry: str,
    location: str,
    topic: str,
    posts_count: int = 0,
    template: Optional[dict] = None,
    focus_keyword: str = "",
    seo_keywords: Optional[list] = None,
) -> dict:
    """
    Generates a premium SEO-optimised blog post using Claude.
    Output uses WordPress Gutenberg block format with callout boxes, pull quotes,
    two-column layouts, WooCommerce product embeds, and a WhatsApp CTA.

    focus_keyword and seo_keywords should come from DataForSEO research — not guessed.
    """
    tpl = template or pick_template(posts_count)
    logger.info("[post_gen] Using template: %s (post #%d)", tpl["name"], posts_count + 1)

    kw_brief = _format_keyword_brief(focus_keyword, seo_keywords or [])

    response = _get_claude().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3500,
        messages=[
            {
                "role": "user",
                "content": f"""You are a senior local content writer with 10+ years of real-world experience in {industry}. You write articles that people actually read to the end — not AI summaries. Before writing, ask: what does someone searching this topic REALLY want to know? What's the angle that makes this worth reading?

Business: {business_name}
Industry: {industry}
Location: {location}
Topic: {topic}
{kw_brief}

Article style: {tpl['name']}
Structure: {tpl['structure']}
Writing guidance: {tpl['hint']}

━━━ MANDATORY — COMMIT TO YOUR OPENING BEFORE WRITING ━━━

Your first sentence is the most important sentence in the article. Choose ONE of these six opening types and use it. Your opening must be the very first thing — no preamble, no "introduction", no context-setting paragraph before it.

TYPE A — SCENE (a moment the reader has lived through):
"You asked three [industry] businesses for a quote. You got three different prices. Nobody explained why."
"The delivery arrived late. Again. The customer messaged at midnight. That's where most businesses lose it."

TYPE B — COUNTER-INTUITIVE FACT (true but goes against what people assume):
"The most expensive option in {location}'s {industry} market is rarely the best one."
"Most businesses in {location} are losing customers at the exact moment they think they've won them."

TYPE C — DIRECT QUESTION (the one already in the reader's head):
"How do you know if the price you're paying for [service] is actually fair?"
"What's the difference between a [service] that works and one that costs you twice as much to fix?"

TYPE D — OBSERVATION FROM EXPERIENCE (someone who's been in the room):
"I've worked with [industry] businesses across {location} for years. The ones that fail all make the same first mistake."
"After seeing this play out dozens of times, the pattern is always the same."

TYPE E — SPECIFIC NUMBER OR STAT:
"In {location}, the average business spends 30% more on [aspect] than it needs to in year one."
"Three out of four customers in {location} check online reviews before they ever make contact."

TYPE F — BOLD POSITION (take a clear side):
"Everyone says [common advice]. It's wrong for most {location} businesses, and here's the proof."
"Stop [common but ineffective approach]. It's not saving you anything."

━━━ HEADLINE ━━━
Your H1 title must match the energy of your chosen opening.
✓ "The [Topic] Mistake That's Costing {location} Businesses More Than They Realise"
✓ "5 Things Nobody Tells You About [Topic] in {location}"
✓ "Why [Common Belief] Is Wrong — And What Actually Works in {location}"
✗ "A Guide to [Topic]" / "Understanding [Topic]" / "The Ultimate Guide to [Topic]"

━━━ WRITING RULES ━━━
- Write to ONE person, not a crowd. "You'll want to..." not "Businesses should..."
- Short sentences. Punchy. Then a longer one when you need to explain something. Vary the rhythm constantly.
- Contractions throughout: don't, it's, you'll, we've, I've. Formal tone = AI tone.
- Specific over vague: name real areas in {location}, real price ranges, real scenarios your reader recognises.
- Every paragraph must earn its place — if it doesn't teach something or move the story forward, cut it.
- One concrete example always beats three abstract claims.

INSTANT FAIL — if any of these appear, rewrite:
✗ "In today's..." / "In this [fast-paced / digital / competitive] world..."
✗ "In this article, we will explore..." / "Are you looking for..."
✗ "[Topic] is an important/essential/crucial aspect of..."
✗ "In conclusion" / "To summarize" / "As we have seen" / "To wrap up"
✗ dive into · delve into · game-changer · leverage · seamlessly · unlock · revolutionize · transformative · landscape · cutting-edge · state-of-the-art · harness the power · it goes without saying · look no further · without further ado

STRUCTURE & SEO:
- 850-1050 words of readable content
- Use the location naturally (e.g. "in {location}", "across {location}")
- The primary keyword must appear in: the title, the first paragraph, at least one H2, and the excerpt
- Mention "{business_name}" once naturally — as the local expert, not an advertisement
- No keyword stuffing — if a keyword doesn't fit naturally, skip it
- Call-to-action must be specific: say what happens when they contact, not just "contact us today"

━━━ GUTENBERG BLOCK FORMAT ━━━

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

━━━ OUTPUT FORMAT ━━━

The "content" field must start with your chosen opening sentence — not "In today's world", not "In this article", not a definition. The opening type you chose is the FIRST thing in the article.

Return ONLY valid JSON — no markdown fences, no explanation:
{{
  "title": "SEO title that includes the primary keyword — max 65 chars, headline energy not a label",
  "content": "<!-- wp:paragraph -->...[complete Gutenberg block content starting with your opening sentence]...",
  "excerpt": "Meta description for Google — max 155 chars, specific benefit + {location}, no fluff",
  "keywords": ["focus_keyword", "keyword2", "keyword3", "keyword4", "keyword5"]
}}

The keywords array must use the provided SEO keywords (not made-up ones). If no keywords were provided, suggest real phrases people would actually search.""",
            }
        ],
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        post = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("[post_gen] JSON parse failed: %s\nRaw: %s", e, raw[:500])
        raise RuntimeError(f"Claude returned invalid JSON: {e}")

    # Strip any markdown bold/italic markers the model accidentally left in the title
    if "title" in post:
        import re as _re
        post["title"] = _re.sub(r"[*_`#]+", "", post["title"]).strip()

    # Always use real DataForSEO keywords — override anything Claude guessed
    if seo_keywords:
        post["keywords"] = seo_keywords[:5]
    if focus_keyword:
        existing = [k for k in (post.get("keywords") or []) if k != focus_keyword]
        post["keywords"] = [focus_keyword] + existing[:4]

    post["template_used"] = tpl["id"]
    post["focus_keyword"] = focus_keyword or (post.get("keywords") or [""])[0]
    logger.info(
        "[post_gen] Generated '%s' [%s] focus='%s'",
        post.get("title", "—"), tpl["name"], post.get("focus_keyword"),
    )
    return post

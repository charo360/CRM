"""
SEO-optimized blog post generator using Claude AI.
Generates high-quality, keyword-optimized content for WordPress autoblogging.
"""
import os
import logging
from typing import List, Dict, Any
import anthropic

logger = logging.getLogger(__name__)


async def generate_seo_blog_post(
    topic: str,
    keywords: List[str],
    business_name: str,
    industry: str,
    location: str,
    word_count: int = 1000,
) -> Dict[str, Any]:
    """
    Generate an SEO-optimized blog post using Claude.
    
    Returns:
        {
            "title": str,
            "content": str (markdown),
            "excerpt": str (150-160 chars),
            "keywords": List[str],
            "word_count": int,
        }
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    
    # Build keyword context
    kw_context = ""
    if keywords:
        kw_context = f"\n\n**Target Keywords (use naturally throughout):**\n" + "\n".join(f"- {kw}" for kw in keywords)
    
    # Build location context
    location_context = f" in {location}" if location else ""
    
    # Build business context
    business_context = ""
    if business_name:
        business_context = f"\n\n**Business Context:** This is for {business_name}"
        if industry:
            business_context += f", a {industry} business"
        business_context += "."
    
    prompt = f"""You are an expert SEO content writer. Write a comprehensive, engaging blog post on the following topic:

**Topic:** {topic}
{kw_context}
{business_context}

**Requirements:**
1. **Word count:** Approximately {word_count} words
2. **SEO optimization:**
   - Include primary keyword in title, first paragraph, and naturally throughout
   - Use H2 and H3 headings with secondary keywords
   - Write compelling meta description (150-160 chars)
   - Include internal linking opportunities (mention related topics)
3. **Content structure:**
   - Engaging introduction with a hook
   - Clear H2/H3 section headings
   - Actionable tips and examples
   - Conclusion with call-to-action
4. **Writing style:**
   - Professional but conversational
   - Use short paragraphs (2-3 sentences)
   - Include bullet points and numbered lists
   - Write for humans first, search engines second
5. **Local SEO{location_context}:**
   - Include location-specific references where relevant
   - Use local terminology and examples

**Output format (strict JSON):**
{{
  "title": "SEO-optimized title (50-60 chars, include primary keyword)",
  "content": "Full blog post in markdown format with ## H2 and ### H3 headings",
  "excerpt": "Compelling meta description (150-160 chars, include primary keyword + CTA)",
  "keywords": ["primary keyword", "secondary keyword 1", "secondary keyword 2"]
}}

Write the blog post now. Return ONLY the JSON object, no other text."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            temperature=0.7,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        
        # Extract JSON from response
        content = response.content[0].text.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        import json
        result = json.loads(content)
        
        # Add word count
        result["word_count"] = len(result["content"].split())
        
        logger.info(
            "[content_generator] Generated blog post: '%s' (%d words)",
            result["title"],
            result["word_count"],
        )
        
        return result
        
    except Exception as e:
        logger.error("[content_generator] Failed to generate blog post: %s", str(e))
        raise RuntimeError(f"Blog post generation failed: {str(e)}")

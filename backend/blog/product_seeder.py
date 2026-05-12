"""
Zilo AI Product Seeder — WooCommerce.

Generates industry-specific products via Claude and pushes them to a client's
WooCommerce store via REST API.  Called once during site creation so the client
launches with real, relevant products (not WC generic demo data).

Industries handled with tailored templates:
  tech / electronics  → laptops, phones, accessories with specs
  salon / beauty      → hair services, treatments, packages
  restaurant / food   → menu items, combos, specials
  retail / fashion    → clothing, shoes, accessories
  health / fitness    → supplements, equipment, memberships
  consulting / services → service packages / retainers
  (default)           → generic product catalogue
"""
import base64
import json
import logging
import os
from typing import Any, Dict, List

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_claude: Anthropic | None = None


def _get_claude() -> Anthropic:
    global _claude
    if _claude is None:
        _claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _claude


def _wc_auth() -> tuple[str, str]:
    return os.getenv("WC_CONSUMER_KEY", ""), os.getenv("WC_CONSUMER_SECRET", "")


def _wc_configured() -> bool:
    k, s = _wc_auth()
    return bool(k and s)


# ── AI generation ──────────────────────────────────────────────────────────────

INDUSTRY_PROMPT: Dict[str, str] = {
    "tech": """Generate 8 realistic tech/electronics products for a Kenyan tech shop.
Mix: 2 laptops, 2 smartphones, 2 accessories (earbuds/charger), 1 tablet, 1 smart TV.
For each product include realistic KES pricing (laptops: 45,000–120,000, phones: 15,000–80,000).
Each product MUST have a "attributes" list with technical specs:
  laptops: RAM, Storage, Processor, Display, Battery
  phones: RAM, Storage, Camera, Battery, Display
  accessories: Compatibility, Color, Warranty""",

    "electronics": """Generate 8 electronics products for a Kenyan electronics store.
Mix of: TVs, home appliances, audio equipment, gaming accessories.
Include realistic KES pricing. Add technical attributes/specs for each.""",

    "salon": """Generate 8 salon/beauty services as WooCommerce products (type: service).
Mix: 3 hair services (braiding, relaxer, cut), 2 nail services, 2 skincare treatments, 1 package deal.
Pricing in KES (200–5000). Include Duration and Who It's For as attributes.""",

    "beauty": """Generate 8 beauty products/services for a Kenyan beauty business.
Mix of physical products (skincare, makeup) and services. Realistic KES pricing.""",

    "restaurant": """Generate 8 food menu items as WooCommerce products.
Mix: 3 main dishes, 2 sides, 1 combo meal, 1 drink/juice, 1 dessert.
Kenyan cuisine (nyama choma, pilau, ugali, chapati, etc.) plus some continental.
KES pricing (200–1500). Add Portion Size and Allergens as attributes.""",

    "food": """Generate 8 food/beverage products for a Kenyan food business.
Realistic KES pricing. Include relevant product attributes.""",

    "retail": """Generate 8 retail/fashion products for a Kenyan fashion shop.
Mix: 3 tops/shirts, 2 trousers/skirts, 1 dress/suit, 1 shoes, 1 accessories.
KES pricing (500–8000). Include Size, Color, Material as attributes.""",

    "fashion": """Generate 8 fashion items for a Kenyan clothing store.
Include Size options, Color options, and Material attributes.""",

    "health": """Generate 8 health & wellness products for a Kenyan health store.
Mix of supplements, equipment, and service packages. KES pricing.""",

    "fitness": """Generate 8 fitness products/memberships.
Mix: equipment, supplements, training packages, memberships. KES pricing.""",

    "consulting": """Generate 6 consulting/professional service packages.
Examples: Business Strategy Session, Marketing Audit, Website Setup Package, etc.
KES pricing (5,000–50,000). Include Duration and Deliverables as attributes.""",

    "real estate": """Generate 6 real estate service packages/listings.
Examples: Property Valuation, Tenant Search, Property Management (monthly), etc.
KES pricing. Include Location, Type, Duration as attributes.""",

    "education": """Generate 8 educational courses/programs as products.
Examples: digital skills courses, tutoring packages, certification programs.
KES pricing (2,000–30,000). Include Duration, Level, Certificate as attributes.""",

    "hotel": """Generate 8 hotel room types and packages.
Mix: room types (standard/deluxe/suite), meal packages, day conference packages.
KES pricing per night (3,000–25,000). Include Capacity, Amenities, Meals as attributes.""",
}

DEFAULT_PROMPT = """Generate 8 general business products/services for a small Kenyan business.
Mix of physical products and services relevant to the industry.
Realistic KES pricing. Include relevant product attributes."""


def _build_prompt(business_name: str, industry: str, location: str) -> str:
    industry_key = industry.lower()
    # Find best matching industry key
    specific = None
    for key in INDUSTRY_PROMPT:
        if key in industry_key:
            specific = INDUSTRY_PROMPT[key]
            break
    template = specific or DEFAULT_PROMPT

    return f"""You are seeding a WooCommerce store for: {business_name} ({industry}) in {location}.

{template}

Return ONLY a valid JSON array of product objects. Each object must follow this EXACT structure:
{{
  "name": "Product Name",
  "type": "simple",
  "regular_price": "1500",
  "description": "<p>Full product description (2-3 sentences, mention the business location).</p>",
  "short_description": "<p>One-line summary.</p>",
  "categories": [{{"name": "Category Name"}}],
  "attributes": [
    {{"name": "Color", "options": ["Black", "White"], "visible": true, "variation": false}},
    {{"name": "Warranty", "options": ["1 Year"], "visible": true, "variation": false}}
  ],
  "manage_stock": false,
  "stock_status": "instock",
  "featured": false
}}

Rules:
- All prices as strings (no KES symbol, just numbers e.g. "4500")
- type must be "simple" for all
- Return array of exactly 8 products (6 for consulting/real estate)
- No markdown, no explanation — ONLY the JSON array"""


async def generate_products(
    business_name: str,
    industry: str,
    location: str,
) -> List[Dict[str, Any]]:
    prompt = _build_prompt(business_name, industry, location)
    response = _get_claude().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    # Extract JSON array
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON array found in Claude response: {raw[:300]}")
    products = json.loads(raw[start:end])
    logger.info(f"[product_seeder] AI generated {len(products)} products for {business_name}")
    return products


# ── WooCommerce push ───────────────────────────────────────────────────────────

async def push_products_to_wc(
    site_url: str,
    products: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Creates products in WooCommerce via REST API.
    Uses batch endpoint for efficiency (up to 100 at once).
    """
    if not _wc_configured():
        logger.warning("[product_seeder] WC keys not configured — skipping product push")
        return {"pushed": 0, "reason": "WC keys not configured"}

    key, secret = _wc_auth()
    batch_url = f"{site_url.rstrip('/')}/wp-json/wc/v3/products/batch"

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                batch_url,
                auth=(key, secret),
                json={"create": products},
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                created = len(data.get("create", []))
                logger.info(f"[product_seeder] Pushed {created} products to {site_url}")
                return {"pushed": created, "errors": data.get("create_errors", [])}
            else:
                logger.warning(f"[product_seeder] WC batch failed {resp.status_code}: {resp.text[:300]}")
                return {"pushed": 0, "reason": f"WC API {resp.status_code}"}
    except Exception as exc:
        logger.warning(f"[product_seeder] Push failed: {exc}")
        return {"pushed": 0, "reason": str(exc)}


# ── Main entry point ───────────────────────────────────────────────────────────

async def seed_products(
    site_url: str,
    business_name: str,
    industry: str,
    location: str,
) -> Dict[str, Any]:
    """
    Full pipeline: AI generate → push to WooCommerce.
    Called during site creation. Failures are non-fatal (logged only).
    """
    try:
        products = await generate_products(business_name, industry, location)
        result = await push_products_to_wc(site_url, products)
        return {"status": "ok", **result}
    except Exception as exc:
        logger.warning(f"[product_seeder] seed_products failed: {exc}")
        return {"status": "error", "reason": str(exc), "pushed": 0}

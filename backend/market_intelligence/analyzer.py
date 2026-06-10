"""
Winning product analyzer — combines Google Trends + CJ Hot Products + Facebook Ads
into a single opportunity score per product, adding strategic product classification,
profitability optimization, and AI audience/hook generation.

Opportunity Score (0-100):
  - Trend score     × 0.30  (Google Trends recent avg, 0-100)
  - Sales score     × 0.45  (CJ order volume, normalized to 0-100)
  - Ad spend score  × 0.25  (FB ad count, capped at 200 → 100)
"""
from __future__ import annotations

import asyncio
import logging
import re
import json
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def _normalize(value: float, max_val: float) -> float:
    if max_val <= 0:
        return 0.0
    return min(100.0, (value / max_val) * 100)


def _opportunity_score(trend: float, sales: float, ads: float) -> int:
    return round(trend * 0.30 + sales * 0.45 + ads * 0.25)


def _classify_opportunity(trend_score: float, trend_direction: str, sales_score: float, ads_score: float) -> Dict[str, Any]:
    """
    Classify the product into a strategic market opportunity tier to prevent 
    new dropshippers from selling saturated items and highlight true winners.
    """
    if trend_direction == "rising" and ads_score < 30 and sales_score > 15:
        return {
            "tier": "🏆 WINNING (Golden Ticket)",
            "badge": "Golden Ticket",
            "color": "green",
            "description": "High search trends and strong supplier sales, with very low competitor ad spend. A high-probability winner."
        }
    elif trend_direction == "rising" and ads_score >= 50:
        return {
            "tier": "🔥 VIRAL TREND (Competitive)",
            "badge": "Viral Trend",
            "color": "indigo",
            "description": "Explosive consumer interest and heavy sales, but competition is fierce. Requires highly unique creatives and custom angles."
        }
    elif sales_score < 40 and ads_score < 15 and trend_direction in ("rising", "stable"):
        return {
            "tier": "🌱 EMERGING (Hidden Gem)",
            "badge": "Hidden Gem",
            "color": "emerald",
            "description": "Early interest starting to grow with zero ad saturation. Highly recommended for testing with fresh audiences before it scales."
        }
    elif trend_direction == "falling" and ads_score > 40:
        return {
            "tier": "⚠️ SATURATED (High Risk)",
            "badge": "Saturated",
            "color": "rose",
            "description": "Declining search interest with highly saturated competitor ad channels. Extremely difficult to scale for beginners."
        }
    else:
        return {
            "tier": "⚡ STABLE DEMAND (Evergreen)",
            "badge": "Stable",
            "color": "gray",
            "description": "Consistent baseline search and supplier demand. Safe, evergreen product that maintains steady sales."
        }


def _calculate_profit_card(cost: float) -> Dict[str, Any]:
    """
    Calculate an optimized, realistic dropshipping profitability card.
    Standard shipping is estimated flat at $4.99 (average weight/epacket).
    """
    shipping_cost = 4.99
    cogs = cost
    total_cost = cogs + shipping_cost
    
    # Standard dropshipping markup is 2.5x to 3x of delivered cost
    suggested_retail = round((total_cost * 2.5) - 0.01, 2)
    if suggested_retail < 9.99:
        suggested_retail = 9.99
        
    # Transaction Fees (Stripe/PayPal standard 2.9% + $0.30)
    gateway_fee = round((suggested_retail * 0.029) + 0.30, 2)
    
    net_profit = round(suggested_retail - total_cost - gateway_fee, 2)
    net_margin_pct = round((net_profit / suggested_retail) * 100, 1) if suggested_retail > 0 else 0
    
    return {
        "cogs": round(cogs, 2),
        "est_shipping": shipping_cost,
        "total_cost_to_deliver": round(total_cost, 2),
        "suggested_retail_price": suggested_retail,
        "gateway_fees": gateway_fee,
        "net_profit_dollar": net_profit,
        "net_profit_margin_pct": net_margin_pct,
        "roi_multiplier": round(suggested_retail / max(total_cost, 0.1), 2)
    }


async def _generate_ai_marketing_guide(title: str, category: str) -> Dict[str, str]:
    """
    Queries Gemini/LLM to generate on-the-fly target persona and ad hooks for high scorers.
    """
    try:
        from ai_service import get_drafter
        ai = get_drafter()
        
        prompt = f"""
You are an expert Dropshipping Marketing Coach. Analyse the following product and provide a high-converting audience target and a viral ad hook.

Product Title: {title}
Category: {category}

Format your response EXACTLY as a JSON object with three fields (do not write any markdown blocks, conversational preamble or backticks):
{{
    "target_persona": "Who exactly to target (e.g. demographic, interests, behavior) in 1 clear sentence.",
    "viral_hook_text": "An attention-grabbing visual/text hook for Facebook/TikTok ads in 1 sentence.",
    "marketing_angle": "The primary emotional or functional angle to pitch in 1 sentence."
}}
"""
        response = await ai._call_llm(prompt, model_pref="standard")
        
        # Clean up markdown code block if present
        cleaned = re.sub(r"```json\s*", "", response)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()
        
        data = json.loads(cleaned)
        return {
            "target_persona": data.get("target_persona", f"Audiences interested in {category}."),
            "viral_hook_text": data.get("viral_hook_text", f"Struggling with {title}? This changes everything!"),
            "marketing_angle": data.get("marketing_angle", "Ultimate daily problem solver.")
        }
    except Exception as e:
        log.warning(f"[AliExpressClient] AI marketing guide failed for {title}: {e}")
        return {
            "target_persona": f"Engaged shoppers interested in {category} and novelty tools.",
            "viral_hook_text": f"Why is everyone obsessed with this {title}? Here is why.",
            "marketing_angle": "Convenience and practical value for your daily routine."
        }


async def find_winning_products(
    niche: str,
    country: str = "US",
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Full market analysis for a niche.
    Returns ranked winning products with scores from all three sources,
    plus strategic classifications, profit margins, and AI advertising guides.
    """
    from market_intelligence.trends import get_interest_over_time, get_related_rising
    from market_intelligence.fb_ads import search_ads

    # Run trends + FB ads in parallel (CJ hot products separate)
    trends_task  = asyncio.create_task(get_interest_over_time(niche, geo=country))
    rising_task  = asyncio.create_task(get_related_rising(niche, geo=country))
    fb_task      = asyncio.create_task(search_ads(niche, countries=[country], limit=20))

    # CJ hot products
    cj_products: List[Dict[str, Any]] = []
    try:
        from cj_dropship.client import cj_get
        data = await cj_get("/product/list", {
            "pageNum": 1, "pageSize": min(limit * 2, 50),
            "productNameEn": niche,
        })
        raw = data.get("list", []) if isinstance(data, dict) else []
        raw.sort(key=lambda p: int(p.get("listedNum", 0) or 0), reverse=True)
        for p in raw[:limit]:
            cost = float(str(p.get("sellPrice", 0)).split()[0].replace(",", "") or 0)
            cj_products.append({
                "cj_pid":       p.get("pid", ""),
                "title":        p.get("productNameEn") or p.get("productName", ""),
                "category":     p.get("categoryName", ""),
                "cost":         cost,
                "orders":       int(p.get("listedNum", 0) or 0),
                "free_ship":    bool(p.get("isFreeShipping", False)),
                "image":        p.get("productImage", ""),
            })
    except Exception as e:
        log.warning("[analyzer] CJ fetch failed: %s", e)

    trend_data, rising, fb_data = await asyncio.gather(trends_task, rising_task, fb_task)

    # Normalize sales volume
    max_orders = max((p["orders"] for p in cj_products), default=1)
    fb_total   = fb_data.get("total", 0) if fb_data.get("available") else 0
    trend_score = trend_data.get("score", 0)
    ads_score   = _normalize(fb_total, 200)   # 200 active ads = max score
    trend_direction = trend_data.get("direction", "stable")

    # Build product cards with opportunity scores and profitability metrics
    raw_products = []
    for p in cj_products:
        s_score = _normalize(p["orders"], max_orders)
        opp     = _opportunity_score(trend_score, s_score, ads_score)
        
        # 1. Product Classification Tier
        opp_class = _classify_opportunity(trend_score, trend_direction, s_score, ads_score)
        
        # 2. Profitability Analysis
        profit_card = _calculate_profit_card(p["cost"])
        
        raw_products.append({
            **p,
            "opportunity_score": opp,
            "opportunity_analysis": opp_class,
            "profitability_card": profit_card
        })

    # Sort by opportunity score descending
    raw_products.sort(key=lambda x: x["opportunity_score"], reverse=True)
    top_products = raw_products[:limit]

    # 3. Generate AI Target Audience Personas and Ad Hooks for the top 3 winning products in parallel
    ai_tasks = []
    for p in top_products[:3]:
        ai_tasks.append(asyncio.create_task(_generate_ai_marketing_guide(p["title"], p["category"])))
        
    if ai_tasks:
        ai_results = await asyncio.gather(*ai_tasks)
        for i, guide in enumerate(ai_results):
            top_products[i]["marketing_guide"] = guide

    return {
        "niche":        niche,
        "country":      country,
        "trend":        trend_data,
        "rising":       rising[:8],
        "fb_ads": {
            "available":  fb_data.get("available", False),
            "total":      fb_total,
            "sample_ads": fb_data.get("ads", [])[:5],
        },
        "products":     top_products,
        "summary": {
            "trend_direction":  trend_direction,
            "trend_change_pct": trend_data.get("change_pct", 0),
            "active_fb_ads":    fb_total,
            "top_cj_orders":    cj_products[0]["orders"] if cj_products else 0,
        },
    }

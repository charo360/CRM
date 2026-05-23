"""Embedding-based semantic router for Zilo Chat.

Pre-embeds ~250 representative phrases at startup (cached to disk so we
never pay the embedding cost again unless phrases change).  At query-time
one tiny embedding call (~50-80 ms) replaces the 500 ms LLM routing call
for the vast majority of messages.

Initialization
--------------
Call ``await initialize()`` once at server startup (non-blocking; runs the
embedding API call in background if the disk cache is cold).

Usage
-----
Call ``await route(message, agent_registry)`` from the intent router.
Returns ``(agent_id, confidence)`` when confidence >= threshold, else
``None`` (fall back to LLM).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "text-embedding-3-small"
_CONFIDENCE_THRESHOLD = 0.72  # cosine similarity cutoff; below this → defer to LLM
_CACHE_FILE = Path(__file__).parent / "_semantic_cache.json"

# ── Phrase library ─────────────────────────────────────────────────────────────
# Each agent gets 6-10 phrases written the way users *actually type them*.
# Diversity matters more than length — mix formal and casual phrasings.
AGENT_PHRASES: Dict[str, List[str]] = {
    "meta_ads": [
        "create a Facebook ad campaign",
        "Instagram ad performance ROAS",
        "Meta ads budget optimization",
        "retargeting ads lookalike audience",
        "my Facebook campaign is in learning phase",
        "ad spend CTR not converting",
        "run Instagram ads for my product",
        "boost a post on Facebook",
    ],
    "google_ads": [
        "Google search ad campaign",
        "Google ads keyword strategy",
        "PPC performance max campaign",
        "display ads quality score",
        "Google adwords optimize bids",
        "search campaign low impressions",
        "Google shopping ads setup",
    ],
    "x_ads": [
        "X ads promoted tweet",
        "Twitter ad campaign setup",
        "advertise on X",
        "promoted post on Twitter",
        "X advertising budget",
    ],
    "creative": [
        "design an Instagram post for my business",
        "create an ad graphic",
        "make a social media visual",
        "design a flyer for my product",
        "generate a Facebook post image",
        "make a banner",
        "create visual content for social media",
        "design a social post",
        "generate an image for my ad",
        "make a post graphic",
    ],
    "document": [
        "write a business proposal",
        "create a pitch deck presentation",
        "draft a business plan",
        "write a press release",
        "create a company profile document",
        "draft a contract",
        "write an investment memo",
        "make a PowerPoint presentation",
        "create slides for my business",
        "write a report",
        "create a presentation",
        "write a letter of intent",
        "write a formal business document",
    ],
    "sales": [
        "show my revenue this month",
        "top selling products",
        "sales report for last week",
        "how much did I earn today",
        "total sales and earnings",
        "best selling items",
        "sales analytics and trends",
        "revenue by product",
    ],
    "customers": [
        "show my customer list",
        "find a customer record",
        "add a new customer",
        "VIP customer segment",
        "customer health score",
        "at-risk customers",
        "dormant customers who haven't bought",
        "customer profile details",
    ],
    "orders": [
        "show my orders",
        "pending order status",
        "track an order delivery",
        "mark order as delivered",
        "fulfillment pipeline stages",
        "orders today",
        "stuck delayed orders",
        "update order status",
    ],
    "broadcasts": [
        "send a bulk WhatsApp message",
        "broadcast to all my customers",
        "mass message promo",
        "send promotional message to customers",
        "WhatsApp blast campaign",
        "message all my customers at once",
        "bulk message customers about promotion",
    ],
    "follow_ups": [
        "follow up with a customer",
        "overdue follow-ups list",
        "set a follow-up reminder",
        "who should I reconnect with",
        "pending follow-ups today",
        "schedule a reminder to call customer",
        "follow-up overdue",
    ],
    "bookings": [
        "my appointments today",
        "schedule a booking",
        "upcoming appointments list",
        "book a service for customer",
        "reservation management",
        "appointment list",
        "available booking slots",
    ],
    "finance": [
        "profit and loss report",
        "cash flow summary",
        "business expenses breakdown",
        "financial overview",
        "gross profit net profit",
        "operating costs",
        "monthly P&L statement",
        "money in money out",
    ],
    "automations": [
        "create a workflow automation",
        "whenever a customer messages auto reply",
        "set up an automation rule",
        "trigger action when customer is created",
        "list my automations",
        "build an automated sequence",
        "auto-reply workflow setup",
    ],
    "invoices": [
        "create an invoice",
        "send invoice to customer",
        "unpaid invoices list",
        "overdue invoice",
        "invoice tracking",
        "generate invoice for customer",
        "invoice status",
        "outstanding invoices",
    ],
    "quotes": [
        "create a quote for customer",
        "send a quotation",
        "pricing estimate document",
        "scope of work",
        "service proposal with price",
        "create a price quote",
        "estimate for client",
    ],
    "payments": [
        "record a payment received",
        "payment history",
        "who paid me",
        "outstanding payments",
        "payment tracking",
        "payment summary",
        "collect payment from customer",
    ],
    "analytics": [
        "business dashboard overview",
        "KPI performance report",
        "business metrics this month",
        "overall business performance",
        "business statistics",
        "monthly report",
        "how is my business doing",
        "revenue and growth report",
        "business overview",
    ],
    "inventory": [
        "add a new product to my store",
        "update product price",
        "stock level is low",
        "restock product",
        "create product in catalog",
        "edit product description",
        "product inventory management",
        "delete product",
        "add products to catalog",
    ],
    "shopify": [
        "Shopify store management",
        "connect my Shopify store",
        "Shopify abandoned cart recovery",
        "Shopify discount code",
        "manage my Shopify store",
        "Shopify sync",
        "Shopify autopilot",
    ],
    "shopify_orders": [
        "Shopify order fulfillment",
        "fulfill Shopify order",
        "Shopify order status",
        "Shopify shipping tracking",
        "cancel Shopify order",
        "Shopify refund",
        "unfulfilled Shopify orders",
    ],
    "shopify_products": [
        "add product to Shopify",
        "Shopify inventory management",
        "Shopify product catalog",
        "Shopify stock levels",
        "Shopify variant SKU",
        "update Shopify product price",
        "Shopify collection",
    ],
    "shopify_analytics": [
        "Shopify revenue report",
        "Shopify sales analytics",
        "Shopify performance metrics",
        "Shopify conversion rate",
        "Shopify growth metrics",
        "Shopify AOV average order value",
        "Shopify customer lifetime value",
    ],
    "shopify_customers": [
        "Shopify customer segments",
        "tag Shopify customer",
        "Shopify VIP customer",
        "win-back lapsed Shopify customer",
        "Shopify abandoned cart customer",
        "Shopify loyalty",
        "Shopify customer tags management",
    ],
    "stripe": [
        "Stripe payment",
        "Stripe subscription",
        "Stripe invoice",
        "Stripe balance",
        "Stripe refund",
        "create Stripe payment link",
        "Stripe customer management",
        "Stripe dashboard",
    ],
    "messages": [
        "my WhatsApp inbox",
        "WhatsApp messages from customers",
        "message history",
        "unread WhatsApp messages",
        "conversation thread WhatsApp",
        "reply to customer WhatsApp message",
    ],
    "social_inbox": [
        "social media DMs",
        "Instagram direct messages",
        "Facebook DM inbox",
        "reply to social media message",
        "social media conversations",
        "social inbox",
        "unified social DM inbox",
    ],
    "social_scheduler": [
        "schedule a social media post",
        "content calendar plan",
        "when to post on Instagram",
        "social media posting schedule",
        "schedule post for tomorrow",
        "plan my social content",
        "posting schedule calendar",
    ],
    "social_monitor": [
        "how are my posts performing",
        "Instagram post engagement rate",
        "social media analytics",
        "likes comments shares on posts",
        "which post got most reach",
        "post performance metrics",
        "social media ROI",
        "top performing posts",
        "how many likes on my posts",
    ],
    "contacts": [
        "add a contact",
        "leads database",
        "import contacts",
        "contact record",
        "contact list management",
        "new lead contact",
        "contact database",
    ],
    "loyalty": [
        "loyalty program",
        "customer rewards",
        "loyalty points",
        "reward VIP customers",
        "win back customer loyalty",
        "repeat customer rewards",
        "loyalty tier program",
    ],
    "nps": [
        "customer satisfaction survey",
        "NPS score",
        "collect customer feedback",
        "CSAT rating",
        "customer feedback campaign",
        "satisfaction survey message",
    ],
    "seo": [
        "SEO keyword research",
        "rank on Google",
        "search engine optimization",
        "meta description and tags",
        "website SEO audit",
        "organic traffic strategy",
        "Google ranking improvement",
        "backlinks",
        "blog post SEO optimization",
        "content strategy SEO",
    ],
    "team": [
        "my team members",
        "add staff member",
        "team roles and permissions",
        "manage team access",
        "staff list",
        "invite team member",
        "employee management",
    ],
    "team_analytics": [
        "team performance report",
        "who is selling the most",
        "staff performance analytics",
        "top performing staff member",
        "sales by team member",
        "team productivity",
    ],
    "klaviyo": [
        "Klaviyo email flow",
        "Klaviyo campaign",
        "Klaviyo automation",
        "Klaviyo segment",
        "Klaviyo email marketing metrics",
    ],
    "mailchimp": [
        "Mailchimp campaign",
        "Mailchimp email",
        "Mailchimp audience",
        "Mailchimp automation",
    ],
    "brevo": [
        "Brevo email campaign",
        "Brevo SMS",
        "Brevo automation",
        "Sendinblue campaign",
    ],
    "gmail": [
        "Gmail inbox",
        "Google mail",
        "send email via Gmail",
        "Gmail draft",
        "email inbox Google",
    ],
    "google_calendar": [
        "Google Calendar event",
        "schedule meeting Google Calendar",
        "create calendar event",
        "Google Calendar invite",
        "upcoming meetings calendar",
    ],
    "slack": [
        "Slack notification",
        "Slack message",
        "send to Slack channel",
        "Slack workspace",
        "Slack alert notification",
    ],
    "google_sheets": [
        "Google Sheets sync",
        "export to spreadsheet",
        "Google Sheets report",
        "sync data to Google Sheets",
        "spreadsheet integration",
    ],
    "notion": [
        "Notion page",
        "sync to Notion",
        "Notion database",
        "write to Notion workspace",
    ],
    "telegram": [
        "Telegram bot",
        "connect Telegram",
        "Telegram notification",
        "Telegram channel setup",
    ],
    "whatsapp": [
        "WhatsApp setup",
        "connect WhatsApp",
        "WhatsApp QR code scan",
        "WhatsApp disconnected reconnect",
        "WhatsApp business connection",
    ],
    "suppliers": [
        "supplier list",
        "vendor management",
        "add supplier",
        "purchase order",
        "vendor payment",
        "supplier contact details",
    ],
    "shop": [
        "my shop page",
        "storefront catalog",
        "shop link",
        "shop menu",
        "store page setup",
        "shop catalog",
    ],
    "email_marketing": [
        "email marketing campaign",
        "send email campaign",
        "email list",
        "email campaign stats",
        "configure email provider",
    ],
}


# ── Module state ──────────────────────────────────────────────────────────────
# _normalized_embeddings[agent_id] = L2-normalized matrix (N_phrases × D)
# normalised at init time so query-time is just a dot product.
_normalized_embeddings: Dict[str, np.ndarray] = {}
_initialized = False
_init_lock = asyncio.Lock()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _phrases_hash() -> str:
    content = json.dumps(AGENT_PHRASES, sort_keys=True)
    return hashlib.md5(content.encode()).hexdigest()


def _load_cache() -> Optional[Dict[str, List[List[float]]]]:
    if not _CACHE_FILE.exists():
        return None
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        if data.get("hash") != _phrases_hash():
            logger.info("[SemanticRouter] Cache stale — will re-embed")
            return None
        return data.get("embeddings")
    except Exception as exc:
        logger.warning("[SemanticRouter] Cache load error: %s", exc)
        return None


def _save_cache(raw: Dict[str, np.ndarray]) -> None:
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump(
                {"hash": _phrases_hash(), "embeddings": {k: v.tolist() for k, v in raw.items()}},
                f,
            )
        logger.info("[SemanticRouter] Cache saved to %s", _CACHE_FILE)
    except Exception as exc:
        logger.warning("[SemanticRouter] Cache save failed: %s", exc)


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    return matrix / norms


async def _embed(texts: List[str]) -> np.ndarray:
    import openai
    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    resp = await client.embeddings.create(model=_EMBEDDING_MODEL, input=texts)
    return np.array([e.embedding for e in resp.data], dtype=np.float32)


# ── Public API ────────────────────────────────────────────────────────────────

async def initialize() -> None:
    """Pre-embed all agent phrases.  Safe to call multiple times — idempotent."""
    global _normalized_embeddings, _initialized
    async with _init_lock:
        if _initialized:
            return

        cached = _load_cache()
        if cached:
            _normalized_embeddings = {
                k: _normalize(np.array(v, dtype=np.float32)) for k, v in cached.items()
            }
            _initialized = True
            logger.info(
                "[SemanticRouter] Loaded from cache — %d agents, ready",
                len(_normalized_embeddings),
            )
            return

        # Cold start: embed all phrases in one batched API call
        all_phrases: List[str] = []
        slices: Dict[str, Tuple[int, int]] = {}
        offset = 0
        for agent_id, phrases in AGENT_PHRASES.items():
            slices[agent_id] = (offset, offset + len(phrases))
            all_phrases.extend(phrases)
            offset += len(phrases)

        try:
            logger.info(
                "[SemanticRouter] Embedding %d phrases for %d agents…",
                len(all_phrases), len(AGENT_PHRASES),
            )
            raw = await _embed(all_phrases)
            raw_by_agent: Dict[str, np.ndarray] = {}
            for agent_id, (start, end) in slices.items():
                raw_by_agent[agent_id] = raw[start:end]

            _save_cache(raw_by_agent)
            _normalized_embeddings = {k: _normalize(v) for k, v in raw_by_agent.items()}
            _initialized = True
            logger.info("[SemanticRouter] Ready — %d agents indexed", len(_normalized_embeddings))
        except Exception as exc:
            logger.error("[SemanticRouter] Initialization failed: %s", exc)
            # Leave _initialized=False so the intent router falls back to LLM every time


async def route(
    message: str,
    agent_registry: Dict,
) -> Optional[Tuple[str, float]]:
    """Return *(agent_id, confidence)* if confidence ≥ threshold, else *None*.

    Each embedding call takes ~50-80 ms via OpenAI's API — much faster than
    the ~500 ms LLM routing call it replaces.
    """
    if not _initialized or not _normalized_embeddings:
        return None

    try:
        msg_emb = (await _embed([message]))[0]
    except Exception as exc:
        logger.warning("[SemanticRouter] Embed failed: %s", exc)
        return None

    msg_norm = msg_emb / (np.linalg.norm(msg_emb) + 1e-8)

    best_agent: Optional[str] = None
    best_score = 0.0
    second_score = 0.0

    for agent_id, norm_matrix in _normalized_embeddings.items():
        if agent_id not in agent_registry:
            continue
        # max cosine similarity across all phrases for this agent
        score = float(np.max(norm_matrix @ msg_norm))
        if score > best_score:
            second_score = best_score
            best_score = score
            best_agent = agent_id
        elif score > second_score:
            second_score = score

    # Require both an absolute threshold AND a margin over the runner-up
    # so we don't route to the wrong agent when two are equally plausible.
    margin = best_score - second_score
    if best_agent and best_score >= _CONFIDENCE_THRESHOLD and margin >= 0.03:
        logger.info(
            "[SemanticRouter] → %s (score=%.3f, margin=%.3f)",
            best_agent, best_score, margin,
        )
        return best_agent, best_score

    logger.debug(
        "[SemanticRouter] Low confidence (best=%.3f, margin=%.3f) — deferring to LLM",
        best_score, margin,
    )
    return None

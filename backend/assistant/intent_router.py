"""Lightweight intent router for Zilo Chat.

Pipeline (v3):
  1. Hard safety/sticky overrides (session continuity, explicit exits).
  2. LLM intent routing first (AutoReply-v2 style).
  3. Deterministic keyword fallback for low-confidence / failures.

Scoring uses word-count of matched phrases so that sub-agent keywords
(e.g. "shopify order" = 2 words) always beat parent keywords
(e.g. "shopify" = 1 word) when both match.

Adding a new agent: add entries to _KEYWORD_MAP + register in agents.py.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LLM_ROUTE_CONFIDENCE_MIN = 0.68

# Routed here only when the user clearly means the Shopify *store*, not generic catalog work.
_SHOPIFY_AGENT_IDS = frozenset(
    {"shopify", "shopify_orders", "shopify_products", "shopify_analytics"}
)


def _explicit_shopify_intent(msg_lower: str) -> bool:
    """True if the user is asking about Shopify specifically (not just 'a shop')."""
    if "shopify" in msg_lower:
        return True
    needles = (
        "my shopify",
        "shopify store",
        "shopify admin",
        "shopify catalog",
        "add to shopify",
        "shopify listing",
        "shopify order",
        "shopify sku",
        "shopify variant",
        "shopify collection",
    )
    return any(n in msg_lower for n in needles)


def _design_or_creative_document_intent(msg_lower: str) -> bool:
    """True when the user wants graphics, PDFs, decks, or ad visuals — not CRM catalog rows alone."""
    deck_markers = (
        "powerpoint",
        "power point",
        "pptx",
        "ppt ",
        " ppt",
        "slide deck",
        "slides for",
        "presentation for",
        "deck for",
        "slideshow",
    )
    if any(m in msg_lower for m in deck_markers):
        return True
    visual_markers = (
        "ad design",
        "design the ad",
        "design an ad",
        "design my ad",
        "ad graphic",
        "ad image",
        "ad creative",
        "social graphic",
        "create a graphic",
        "make a flyer",
        "make a poster",
        "banner for",
        "visual for my",
        "creative for",
        "image for my ad",
        "designing ad",
    )
    if any(m in msg_lower for m in visual_markers):
        return True
    if "pdf" in msg_lower and any(
        w in msg_lower for w in ("design", "flyer", "poster", "graphic", "layout", "brand", "brochure")
    ):
        return True
    # "create/make/build + post" with a social platform = visual creation, not scheduling.
    creation_verbs = ("create", "make", "build", "design", "generate")
    post_targets = (
        "instagram post", "instagram story", "instagram reel",
        "facebook post", "facebook story",
        "tiktok post", "linkedin post", "twitter post", "x post",
        "social post", "a post", "the post",
    )
    if any(v in msg_lower for v in creation_verbs) and any(t in msg_lower for t in post_targets):
        return True
    return False


def _is_text_document_intent(msg_lower: str) -> bool:
    """True when the user clearly wants a written document — never route this to creative."""
    markers = (
        "proposal", "business plan", "pitch deck", "executive summary",
        "partnership", "investment memo", "press release", "meeting minutes",
        "contract", "letter of intent", "sales letter", "company profile",
        "onboarding letter", "welcome letter", "write a report",
        "business document", "formal document", "write a", "draft a",
        "create a document", "brochure", "presentation", "powerpoint", "pptx",
        "slide deck",
    )
    return any(m in msg_lower for m in markers)


def _prefer_creative_agent(msg_lower: str, agent_registry: Dict[str, Any]) -> str:
    """Pick a specialist for graphics / PDF / decks — prefer the creative agent when registered."""
    if "creative" in agent_registry:
        return "creative"
    if "meta_ads" in agent_registry:
        return "meta_ads"
    return "general"


_CATALOG_STOCK_WITHOUT_DESIGN_TOOLS = frozenset(
    {
        "inventory",
        "shop",
        "shopify",
        "shopify_products",
        "shopify_orders",
        "shopify_analytics",
    }
)


def _crm_catalog_intent(msg_lower: str) -> bool:
    """Generic product / catalog work in Zilo (CRM), not necessarily Shopify."""
    needles = (
        "add product",
        "add products",
        "add a product",
        "new product",
        "new products",
        "create product",
        "create products",
        "my catalog",
        "product catalog",
        "product list",
        "my products",
        "list products",
        "edit product",
        "update product",
        "delete product",
        "remove product",
        "change price",
        "update price",
        "product price",
        "sku",
        "adjust inventory",
        "stock level",
        "restock",
        "low stock",
    )
    return any(n in msg_lower for n in needles)


# ── Keyword map ────────────────────────────────────────────────────────────────
# agent_id → phrases that strongly signal that domain.
# All matches are case-insensitive substring on the full user message.
# Score = sum of WORD COUNTS of matched phrases — longer phrases win over shorter
# ones, so sub-agents beat their parent agent automatically.
_KEYWORD_MAP: Dict[str, List[str]] = {

    # ── Advertising ───────────────────────────────────────────────────────────
    "meta_ads": [
        "facebook ad", "instagram ad", "meta ad", "meta campaign",
        "fb ad", "ads manager", "learning phase", "roas ", "cpm ",
        "ad creative", "retargeting", "prospecting", "lookalike",
        "facebook campaign", "instagram campaign", "meta ads",
        "ad budget", "ad spend", "ad account",
        "ad design", "ad graphic", "ad image", "design the ad", "design an ad", "design my ad",
        "visual ad", "social ad", "banner ad", "ad banner", "creative asset",
    ],
    "google_ads": [
        "google ad", "google campaign", "google search ad",
        "display ad", "ppc ", "quality score", "adwords",
        "google keyword", "google ads", "search campaign",
        "performance max", "smart campaign",
    ],
    "x_ads": [
        "x ads", "x ad ", "twitter ads", "twitter ad",
        "promoted tweet", "promoted post on x", "promoted post on twitter",
        "x campaign", "twitter campaign", "x advertising",
        "advertise on x", "advertise on twitter", "x.com ad",
    ],

    # ── Creative (social + design merged) ────────────────────────────────────
    "creative": [
        # social content
        "social media", "instagram post", "facebook post", "tiktok",
        "twitter post", "linkedin post", "schedule post", "social inbox",
        "social account", "social channel", "post to social",
        "publish post", "connect social",
        "post graphic", "social graphic", "instagram graphic", "facebook graphic",
        "caption", "hashtag", "content idea", "content strategy",
        "what to post", "when to post", "best time to post",
        # design / visual — pure graphics only, NOT text documents
        "graphic", "create a graphic", "make a graphic",
        "ad design", "design the ad", "design an ad", "design my ad",
        "ad graphic", "ad image", "ad creative", "social graphic",
        "create a flyer", "make a flyer", "make a poster", "banner for",
        "visual for my", "creative for", "image for my ad", "designing ad",
        "facebook ad design", "instagram ad design", "social media design",
        "graphic design", "visual design", "creative design", "marketing design",
        "promotional graphic", "ad visual", "social visual", "post graphic",
        "create visual", "make visual", "design visual", "visual content",
        "create post", "make a post", "build a post", "generate a post",
    ],

    # ── CRM core ──────────────────────────────────────────────────────────────
    "sales": [
        "revenue", "sales report", "top selling", "best seller",
        "how much did i make", "earnings", "sales today",
        "sales this week", "sales this month", "total sales",
        "sales analysis", "profit margin", "sales trend",
        "what did i earn", "income report",
    ],
    "customers": [
        "my customers", "add customer", "new customer", "find customer",
        "customer segment", "vip customers", "top customers",
        "customer health", "customer list", "contact list",
        "customer profile", "at risk customer", "dormant customer",
        "who bought", "customer tags",
    ],
    "orders": [
        "my orders", "pending orders", "order status", "track order",
        "order delivery", "fulfillment", "order update", "mark order",
        "delivery status", "orders today", "new orders",
        "orders this week", "order pipeline",
    ],
    "broadcasts": [
        "broadcast", "bulk message", "mass message", "send to all",
        "send to my customers", "whatsapp blast", "campaign message",
        "send broadcast", "message all", "bulk send",
        "broadcast to", "send a message to all",
    ],
    "follow_ups": [
        "follow up", "follow-up", "followup", "overdue follow",
        "set reminder", "schedule reminder", "reconnect with",
        "who should i follow", "follow ups today", "pending follow",
        "missed follow", "follow up list",
    ],
    "bookings": [
        "booking", "appointment", "reservation", "book a session",
        "schedule appointment", "upcoming appointments",
        "booking list", "my appointments", "available slots",
        "book a service", "booking today",
    ],
    "finance": [
        "invoice", "expenses", "cash flow", "financial report",
        "profit and loss", "money in", "money out",
        "outstanding invoice", "unpaid invoice", "record expense",
        "finance summary", "financial overview",
    ],
    "automations": [
        "automate", "automation", "workflow", "whenever a customer",
        "every time", "set up a rule", "auto reply rule",
        "trigger action", "create a sequence", "list automations",
        "what automations", "build a workflow",
    ],

    # ── Shopify sub-agents (listed BEFORE parent so longer phrases score higher)
    "shopify_orders": [
        "shopify order", "shopify fulfillment", "shopify delivery",
        "my shopify orders", "shopify order status", "shopify shipping",
        "shopify refund", "shopify return", "shopify cancelled order",
        "unfulfilled shopify", "shopify pending order",
        "fulfill order", "fulfill shopify", "auto fulfill", "auto-fulfill",
        "cancel shopify order", "shopify cancel",
    ],
    "shopify_products": [
        "shopify product", "shopify catalog", "shopify inventory",
        "shopify listing", "shopify variant", "shopify collection",
        "shopify stock", "shopify sku", "shopify item",
        "add to shopify", "shopify price", "out of stock shopify",
        "shopify restock", "add product to shopify", "add products to my store",
        "product ideas for my store", "find products to sell", "source products",
        "product research shopify", "what products to sell", "suggest products",
        "ai product finder", "product sourcing", "shopify add product",
        # Note: do not use generic phrases like "adjust inventory" / "low stock" here —
        # those belong to CRM `inventory`; Shopify wins only when Shopify-specific terms match.
    ],
    "shopify_analytics": [
        "shopify revenue", "shopify sales", "shopify analytics",
        "shopify report", "shopify performance", "shopify conversion",
        "shopify traffic", "shopify aov", "shopify average order",
        "shopify growth", "shopify stats", "shopify cac", "shopify ltv",
        "repeat purchase", "at-risk customers", "abandoned cart value",
        "growth metrics", "shopify channel attribution",
    ],
    "shopify": [
        "shopify", "my shopify", "shopify store",
        "connect shopify", "shopify sync", "shopify autopilot",
        "run shopify", "shopify discount", "create discount shopify",
        "abandoned cart", "cart recovery", "shopify win-back",
    ],

    # ── Payments ──────────────────────────────────────────────────────────────
    "stripe": [
        "stripe", "stripe payment", "stripe subscription", "stripe invoice",
        "stripe dashboard", "stripe charge", "stripe refund",
        "stripe dispute", "stripe webhook", "stripe customer",
        "stripe balance", "stripe customers", "stripe subscriptions",
        "payment link", "stripe checkout", "create payment link",
        "stripe revenue", "stripe payout", "stripe account",
        "overdue invoice", "paid invoice", "unpaid invoice",
    ],

    # ── Email marketing ───────────────────────────────────────────────────────
    "klaviyo": [
        "klaviyo", "klaviyo flow", "klaviyo campaign", "klaviyo email",
        "klaviyo segment", "klaviyo automation", "klaviyo list",
        "klaviyo metric", "klaviyo template",
    ],
    "mailchimp": [
        "mailchimp", "mailchimp campaign", "mailchimp audience",
        "mailchimp automation", "mailchimp email", "mailchimp list",
        "mailchimp template", "mailchimp report",
    ],
    "brevo": [
        "brevo", "brevo campaign", "brevo email", "brevo sms",
        "brevo automation", "brevo contact", "brevo transactional",
        "sendinblue",
    ],

    # ── Productivity ──────────────────────────────────────────────────────────
    "slack": [
        "slack", "slack notification", "slack alert", "slack message",
        "slack channel", "slack workspace", "slack bot",
        "notify slack", "send to slack",
    ],
    "gmail": [
        "gmail", "google mail", "my email", "email inbox",
        "send email", "email campaign", "email thread",
        "gmail draft", "gmail label",
    ],
    "microsoft": [
        "microsoft", "outlook", "office 365", "microsoft teams",
        "onedrive", "sharepoint", "microsoft calendar",
        "outlook email", "outlook calendar", "ms teams",
    ],
    "google_calendar": [
        "google calendar", "calendar event", "my calendar",
        "schedule meeting", "create event", "calendar invite",
        "google meet", "upcoming meeting", "calendar sync",
        "meeting schedule",
    ],

    # ── Messaging management ──────────────────────────────────────────────────
    "telegram": [
        "telegram", "telegram bot", "telegram channel",
        "telegram group", "connect telegram", "telegram message",
        "botfather", "telegram notification",
    ],

    # ── Platform features ─────────────────────────────────────────────────────
    "messages": [
        "inbox", "my messages", "message inbox", "unread messages",
        "whatsapp message", "send a message", "message history",
        "conversation history", "chat history", "who messaged me",
        "reply to customer", "message thread",
    ],
    "contacts": [
        "my contacts", "add contact", "new contact", "find contact",
        "contact record", "contact details", "contact database",
        "import contacts", "contact notes", "update contact",
        "delete contact", "contact management", "leads",
    ],
    "suppliers": [
        "supplier", "vendor", "purchase order", "my vendors",
        "supplier list", "vendor list", "supplier details",
        "supplier contact", "vendor management", "procurement",
        "supplier payment", "add supplier",
    ],
    "payments": [
        "payment record", "record payment", "payment history",
        "received payment", "payment tracking", "payment summary",
        "who paid", "outstanding payment", "payment status",
        "collect payment", "payment method",
    ],
    "invoices": [
        "invoice", "create invoice", "send invoice", "unpaid invoice",
        "invoice list", "overdue invoice", "invoice status",
        "invoice for customer", "generate invoice", "invoice number",
        "outstanding invoice", "invoice tracking",
    ],
    "quotes": [
        "quote", "proposal", "quotation", "create a quote",
        "send a proposal", "quote for customer", "pricing proposal",
        "estimate", "quote document", "scope of work",
        "service proposal", "quote breakdown",
    ],
    "document": [
        "write a document", "create a document", "draft a document",
        "business proposal", "write a proposal", "draft a proposal",
        "proposal for", "proposal to", "a proposal",
        "pitch deck", "investor pitch", "write a pitch", "pitch presentation",
        "business plan", "write a business plan", "draft a plan",
        "executive summary", "write an executive summary",
        "partnership proposal", "write a partnership",
        "investment memo", "investor memo", "fundraising document",
        "press release", "write a press release",
        "meeting minutes", "write minutes", "draft minutes",
        "contract", "draft a contract", "service agreement", "write an agreement",
        "letter of intent", "loi", "write a letter of intent",
        "client onboarding", "onboarding letter", "welcome letter",
        "sales letter", "write a sales letter",
        "write a report", "market report", "competitor report",
        "business document", "formal document", "professional document",
        "write a letter", "draft a letter", "business letter",
        "company profile", "write a company profile",
        "presentation", "powerpoint", "power point", "pptx", "ppt",
        "slide deck", "slideshow", "slides for", "create presentation",
        "make a presentation", "build a presentation", "brochure",
        "proposal document", "proposal pdf", "proposal word",
    ],
    "analytics": [
        "analytics", "dashboard", "performance report", "kpi",
        "business metrics", "revenue report", "monthly report",
        "weekly report", "stats", "numbers", "how is my business",
        "business overview", "trend report", "growth rate",
    ],
    "team_analytics": [
        "team performance", "staff performance", "team report",
        "team analytics", "who is selling most", "top performer",
        "team stats", "staff stats", "sales by staff",
        "team productivity", "individual performance",
    ],
    "team": [
        "my team", "team members", "staff list", "add staff",
        "team roles", "staff roles", "manage team", "team access",
        "staff permissions", "remove staff", "invite team member",
        "team management", "employee list",
    ],
    "inventory": [
        "inventory", "stock", "stock level", "stock count",
        "low stock", "out of stock", "restock", "stock alert",
        "stock management", "add product", "add products", "add a product",
        "new product", "new products", "create product", "create products",
        "edit product", "update product", "delete product",
        "product price", "update price", "catalog management",
        "product list", "my products", "adjust inventory",
    ],
    "loyalty": [
        "loyalty", "rewards", "loyalty program", "loyalty points",
        "reward customer", "vip reward", "customer retention",
        "win back customer", "loyalty tier", "repeat customer",
        "loyalty campaign", "reward message",
    ],
    "nps": [
        "nps", "feedback", "customer feedback", "satisfaction",
        "customer satisfaction", "survey", "nps survey", "csat",
        "customer rating", "how do customers feel", "collect feedback",
        "feedback message", "satisfaction score",
    ],
    "social_inbox": [
        "social inbox", "social dm", "instagram dm", "facebook dm",
        "social message", "dm from instagram", "dm from facebook",
        "social media message", "reply to dm", "social comment",
        "unified inbox", "social reply",
    ],
    "social_scheduler": [
        "schedule post", "content calendar", "plan post",
        "social scheduler", "schedule instagram", "schedule facebook",
        "post schedule", "when to post", "content plan",
        "social media plan", "weekly post", "content strategy",
    ],
    "social_monitor": [
        "social media performance", "social performance", "post performance",
        "engagement rate", "engagement analytics", "social analytics",
        "how are my posts doing", "post analytics", "social media analytics",
        "which platform is performing", "best performing post",
        "reach and engagement", "social media reach", "social media metrics",
        "social media strategy", "social strategy", "what's working on",
        "platform performance", "content performance", "post reach",
        "monitor social", "social media monitor", "social media report",
        "social report", "instagram performance", "facebook performance",
        "linkedin performance", "tiktok performance", "x performance",
        "how many likes", "how many views", "social media roi",
        "which posts work", "top posts", "best posts",
        "social media insights", "content insights", "posting strategy",
        "advise on social", "social media advice",
    ],
    "whatsapp": [
        "whatsapp setup", "whatsapp connection", "connect whatsapp",
        "whatsapp qr", "whatsapp scan", "whatsapp disconnected",
        "whatsapp status", "reconnect whatsapp", "whatsapp instance",
        "whatsapp pairing", "whatsapp business",
    ],
    "shop": [
        "my shop", "shop catalog", "storefront", "shop products",
        "add to shop", "shop menu", "catalog", "product catalog",
        "shop setup", "shop link", "shop page", "my menu",
    ],
}


def _looks_like_agent_switch_request(msg_lower: str) -> bool:
    """True when the user is asking to change specialist — never treat as a bland continuation."""
    needles = (
        "switch to ",
        "transfer to ",
        "hand off",
        "handoff",
        "talk to creative",
        "use creative",
        "use document",
        "document writer",
        "creative specialist",
        "creative agent",
        "wrong agent",
        "different agent",
        "route me to",
        "open ",
    )
    return any(n in msg_lower for n in needles)


def _is_continuation_message(msg_lower: str) -> bool:
    """True for short, ambiguous follow-ups that are clearly continuing the same flow."""
    if _looks_like_agent_switch_request(msg_lower):
        return False
    words = msg_lower.split()
    if len(words) > 6:
        return False
    # Any 1–2 word message is almost certainly a tap-chip pick (product name, option, etc.)
    # Never re-route on a single word — it's always a continuation.
    if len(words) <= 2:
        return True
    # Pure affirmatives / negatives
    if msg_lower.strip() in {
        "yes", "y", "yep", "yeah", "yup", "sure", "ok", "okay", "go", "do it",
        "no", "nope", "skip", "cancel", "stop", "next", "continue", "proceed",
        "perfect", "great", "good", "nice", "love it", "looks good", "done",
        "that one", "this one", "pick this", "pick that", "choose this",
    }:
        return True
    # Platform / format choice — user picking from chips (e.g. "Instagram Feed sounds good")
    platform_format_words = {
        "feed", "story", "stories", "reel", "reels", "square", "portrait",
        "landscape", "carousel", "vertical", "horizontal",
        "facebook", "instagram", "tiktok", "linkedin", "twitter", "pinterest",
        "static", "video", "image",
        "one", "two", "first", "second", "both", "left", "right",
        "option a", "option b", "template",
    }
    if any(w in msg_lower for w in platform_format_words):
        # Short chip reply that picks a platform/format/option — definitely a continuation
        return True
    # "Let's go with X", "I like X", "X sounds good", "X please", "X works" — option-picking phrases
    picking_patterns = (
        "let's go with", "lets go with", "i like the", "i'll go with",
        "sounds good", "works for me", "that works", "i prefer",
        "i want the", "i choose", "go with", "use the", "pick the",
    )
    if any(msg_lower.startswith(p) or p in msg_lower for p in picking_patterns):
        return True
    return False


_DESIGN_EXIT_MARKERS = (
    "back to ads", "back to meta ads", "back to analytics", "back to customers",
    "back to orders", "back to finance", "back to the dashboard", "switch to",
    "stop designing", "stop design", "forget the design", "cancel the design",
    "never mind the design", "leave design", "exit design", "quit design",
    "show my orders", "show my customers", "show my sales", "show my followups",
    "show my analytics", "show my invoices", "list my customers", "list my orders",
    "my revenue", "my pipeline", "create a customer", "create an order",
    "send a broadcast", "schedule a followup",
    # Document requests always exit creative
    "write a proposal", "create a proposal", "draft a proposal",
    "write a document", "create a document", "draft a document",
    "write a report", "business plan", "business proposal",
    "partnership proposal", "pitch deck", "presentation",
)


def _is_explicit_design_exit(msg_lower: str) -> bool:
    """True if the user clearly wants to leave a design session and go elsewhere."""
    return any(m in msg_lower for m in _DESIGN_EXIT_MARKERS)


def _is_social_connection_status_intent(msg_lower: str) -> bool:
    """True for account-count/status questions that should not start creative flows."""
    needles = (
        "how many social",
        "how many connected",
        "social connected",
        "social accounts connected",
        "connected accounts",
        "which social account",
        "what social account",
        "social integration",
        "integrations connected",
    )
    return any(n in msg_lower for n in needles)


def _is_social_inbox_intent(msg_lower: str) -> bool:
    needles = (
        "social inbox", "inbox", "dm", "direct message", "conversation history",
        "reply to message", "social conversation", "message thread", "unread social",
    )
    return any(n in msg_lower for n in needles)


def _is_social_scheduler_intent(msg_lower: str) -> bool:
    needles = (
        "schedule post", "content calendar", "publish time", "when to post",
        "scheduled post", "plan post", "posting schedule",
    )
    return any(n in msg_lower for n in needles)


def _is_social_monitor_intent(msg_lower: str) -> bool:
    needles = (
        "social analytics", "engagement rate", "post performance", "social roi",
        "likes and shares", "which post performed", "social metrics", "reach and impressions",
        "my likes", "my comments", "my shares", "my reach", "my engagement",
        "how many likes", "how many comments", "how many shares",
        "see my post", "see the post", "can't see", "cannot see",
        "post engagement", "engagement on my", "engagement on the",
        "post stats", "post data", "post results", "post insights",
        "live post", "latest post", "recent post", "my post",
        "top post", "best post", "performing post",
        "social inbox engagement", "comment count", "like count", "share count",
    )
    return any(n in msg_lower for n in needles)


async def _llm_route_choice(
    message: str,
    history: List[Dict[str, Any]],
    agent_registry: Dict[str, Any],
    msg_lower: str,
) -> Optional[tuple[str, float]]:
    """Ask the model to choose an agent. Returns (agent, confidence) or None."""
    try:
        from .models import chat_with_tools as _chat_with_tools

        agent_menu = "\n".join(
            f"  {aid}: {cfg.get('description', '')}"
            for aid, cfg in agent_registry.items()
        )

        context_lines: List[str] = []
        for m in history[-4:]:
            role = m.get("role", "user")
            content = str(m.get("content", ""))[:120]
            context_lines.append(f"{role}: {content}")
        recent = "\n".join(context_lines) if context_lines else "(new conversation)"

        prompt = (
            "You are the routing layer of a CRM assistant. "
            "Pick the single best specialist agent for this message.\n\n"
            "Agent boundaries (strict):\n"
            "- social_inbox: DMs, inbox conversations, replies, message history\n"
            "- social_scheduler: scheduling, calendar, publishing plans\n"
            "- social_monitor: post metrics, engagement analytics, social ROI\n"
            "- creative: generating/refining visuals and creative assets\n"
            "- general: integrations/account status, cross-domain and fallback\n\n"
            "Rules: If the user is adding or editing products in general (catalog, prices, SKUs) but does NOT mention "
            "Shopify or a Shopify store, prefer **inventory** or **shop** — NOT shopify / shopify_products / shopify_orders. "
            "Shopify agents are only for explicit Shopify store/admin/sync questions.\n\n"
            "**Critical:** If the user wants **ad graphics, social posts, social media content, captions, hashtags, "
            "flyers/posters, PDF layouts, PowerPoint/slide decks, template-based renders, or any visual creative**, "
            "route to **creative** when it appears in the list — never **inventory** or **shop**.\n\n"
            "**Critical:** Questions about connected integrations/accounts (e.g. \"how many social accounts connected\") "
            "should route to **general** unless a dedicated integration status agent is clearly better.\n\n"
            f"Available agents:\n{agent_menu}\n\n"
            f"Recent context:\n{recent}\n\n"
            f"User message: \"{message}\"\n\n"
            "Reply ONLY with valid JSON on one line: "
            "{\"agent\": \"<agent_id>\", \"confidence\": <0.0-1.0>, \"reason\": \"<one sentence>\"}\n"
            "confidence: 1.0 = unambiguously clear, 0.5 = could go either way. "
            "Choose the most specific agent. Use 'general' only if nothing else fits."
        )

        resp = await _chat_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            model_id=None,
            temperature=0.0,
            timeout=8.0,
        )
        raw = resp.get("content", "")
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group())
        chosen = data.get("agent", "general")
        confidence = float(data.get("confidence", 0.0))

        # Override: visual/social intent must never land on catalog/stock agents
        if _design_or_creative_document_intent(msg_lower):
            if chosen in _CATALOG_STOCK_WITHOUT_DESIGN_TOOLS:
                chosen = _prefer_creative_agent(msg_lower, agent_registry)
                logger.info(f"[IntentRouter] LLM → {chosen} (override: creative intent; was catalog agent)")
            elif chosen in {"social_media", "design"} and "creative" in agent_registry:
                chosen = "creative"

        if chosen in agent_registry:
            logger.info(
                f"[IntentRouter] LLM candidate → {chosen} (confidence={confidence:.2f}): {data.get('reason', '')}"
            )
            return chosen, confidence
    except Exception as exc:
        logger.warning(f"[IntentRouter] LLM routing failed: {exc}")
    return None


async def route_to_agent(
    message: str,
    history: List[Dict[str, Any]],
    agent_registry: Dict[str, Any],
    prev_agent: Optional[str] = None,
    design_flow_active: bool = False,
    explicit_agent: Optional[str] = None,
) -> str:
    """Return the best agent_id for this message.

    Strategy:
      0. Optional explicit agent from UI/API (user locked or picked a specialist).
      0a/0a-2. Sticky creative / document sessions (multi-turn).
      0b. Sticky continuation — short replies stay with prev_agent **only after**
          there is prior conversation (never on the first user message of a thread).
      1. Hard intent overrides (document, integration-status, explicit creative).
      2. LLM route (confidence-gated).
      3. Keyword fallback.
    Always returns a valid agent_id that exists in agent_registry.
    """
    msg_lower = message.lower()

    # ── Explicit specialist from client (agent picker / lock) ─────────────────
    if explicit_agent:
        from .agents import resolve_agent_id

        rid = resolve_agent_id(explicit_agent.strip())
        if rid in agent_registry:
            logger.info("[IntentRouter] explicit client agent → %s", rid)
            return rid

    has_prior_turns = bool(history)

    # ── 0a. Extra-sticky routing for active creative sessions ────────────────
    # Creative is multi-turn and heavily stateful (product / platform / template /
    # copy / staged image / render). Bouncing out mid-flow loses all context.
    # Two signals trigger stickiness:
    #   a) prev_agent resolves to "creative" (handles legacy "design" alias)
    #   b) design_flow_active == True (DB confirms flow_step is set and not done)
    # Only leave when the user EXPLICITLY asks.
    _AGENT_ALIASES_LOCAL = {"design": "creative"}
    prev_agent_resolved = _AGENT_ALIASES_LOCAL.get(prev_agent or "", prev_agent or "")
    is_active_creative = (
        "creative" in agent_registry
        and (prev_agent_resolved == "creative" or design_flow_active)
    )
    if is_active_creative:
        # Never trap document/proposal requests inside a sticky creative flow.
        if "document" in agent_registry and _is_text_document_intent(msg_lower):
            logger.info(
                "[IntentRouter] leaving creative → document (text document intent during active creative session)"
            )
            return "document"
        if not _is_explicit_design_exit(msg_lower):
            logger.info(
                "[IntentRouter] sticky → creative (active creative session; "
                "prev=%r flow_active=%s; message: %r)",
                prev_agent, design_flow_active, message[:60],
            )
            return "creative"
        logger.info(f"[IntentRouter] leaving creative (explicit exit: {message!r})")

    # ── 0a-2. Sticky routing for document agent ──────────────────────────────
    # Document sessions (e.g. template cloning) are multi-turn — don't bounce
    # the user to creative/general just because keywords like "template" match.
    if prev_agent_resolved == "document" and "document" in agent_registry:
        if not _is_explicit_design_exit(msg_lower):
            logger.info(
                "[IntentRouter] sticky → document (active document session; message: %r)",
                message[:60],
            )
            return "document"
        logger.info(f"[IntentRouter] leaving document (explicit exit: {message!r})")

    # ── 0b. Sticky routing — don't break mid-flow on ambiguous replies ────────
    # New threads default conv.agent to "general"; without this guard, the *first*
    # short user message (e.g. "create an instagram post") was treated as a
    # "continuation" of general and never reached creative routing.
    if (
        has_prior_turns
        and prev_agent_resolved
        and prev_agent_resolved in agent_registry
        and _is_continuation_message(msg_lower)
    ):
        logger.info(f"[IntentRouter] sticky → {prev_agent_resolved} (continuation: {message!r})")
        return prev_agent_resolved

    # Text document intent → document agent (must check BEFORE creative override)
    if "document" in agent_registry and _is_text_document_intent(msg_lower):
        logger.info("[IntentRouter] forced → document (text document/proposal intent)")
        return "document"

    # Integration/account status questions should not trigger creative session routing.
    if _is_social_connection_status_intent(msg_lower):
        logger.info("[IntentRouter] forced → general (social/integration status intent)")
        return "general" if "general" in agent_registry else next(iter(agent_registry.keys()))

    if _is_social_inbox_intent(msg_lower) and "social_inbox" in agent_registry:
        logger.info("[IntentRouter] forced → social_inbox")
        return "social_inbox"

    if _is_social_scheduler_intent(msg_lower) and "social_scheduler" in agent_registry:
        logger.info("[IntentRouter] forced → social_scheduler")
        return "social_scheduler"

    if _is_social_monitor_intent(msg_lower) and "social_monitor" in agent_registry:
        logger.info("[IntentRouter] forced → social_monitor")
        return "social_monitor"

    # Visual / creative intent → creative agent (only for pure graphics/social posts)
    if "creative" in agent_registry and _design_or_creative_document_intent(msg_lower) and not _is_text_document_intent(msg_lower):
        logger.info("[IntentRouter] forced → creative (visual/layout/deck intent)")
        return "creative"

    # ── 1. LLM route first (AutoReply-v2 style), confidence gated ────────────
    llm_choice = await _llm_route_choice(message, history, agent_registry, msg_lower)
    if llm_choice is not None:
        chosen, confidence = llm_choice
        if confidence >= _LLM_ROUTE_CONFIDENCE_MIN:
            logger.info(
                f"[IntentRouter] LLM → {chosen} (accepted; confidence={confidence:.2f} >= {_LLM_ROUTE_CONFIDENCE_MIN:.2f})"
            )
            return chosen
        logger.info(
            f"[IntentRouter] LLM low-confidence ({confidence:.2f} < {_LLM_ROUTE_CONFIDENCE_MIN:.2f}); falling back to keywords"
        )

    # ── 2. Keyword scoring fallback (word-count weighted) ─────────────────────
    # Score = total word count of all matched phrases.
    # "shopify order" (2 words) beats "shopify" (1 word) automatically.
    scores: Dict[str, int] = {}
    for agent_id, keywords in _KEYWORD_MAP.items():
        if agent_id not in agent_registry:
            continue
        score = sum(len(kw.split()) for kw in keywords if kw.strip() in msg_lower)
        if score:
            scores[agent_id] = score

    if scores:
        best = max(scores, key=lambda k: scores[k])
        # Prefer CRM catalog agents when the user did not mention Shopify but is clearly
        # doing catalog / stock work — avoids mis-routing to Shopify specialists.
        if (
            best in _SHOPIFY_AGENT_IDS
            and not _explicit_shopify_intent(msg_lower)
            and _crm_catalog_intent(msg_lower)
        ):
            for preferred in ("inventory", "shop", "sales"):
                if preferred in scores:
                    best = preferred
                    logger.info(
                        f"[IntentRouter] keyword → {best} (override: CRM catalog, not Shopify; was shopify-tied; scores={scores})"
                    )
                    return best
            best = "inventory"
            logger.info(
                f"[IntentRouter] keyword → {best} (override: CRM catalog default; scores={scores})"
            )
            return best
        # Catalog/stock agents have no graphic/PDF/deck tools — do not answer design/PDF/PPT there.
        if _design_or_creative_document_intent(msg_lower) and best in _CATALOG_STOCK_WITHOUT_DESIGN_TOOLS:
            alt = _prefer_creative_agent(msg_lower, agent_registry)
            logger.info(
                f"[IntentRouter] keyword → {alt} (override: creative/doc intent; was {best}; scores={scores})"
            )
            return alt
        logger.info(f"[IntentRouter] keyword → {best} (fallback; scores={scores})")
        return best

    return "general"

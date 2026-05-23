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

_LLM_ROUTE_CONFIDENCE_MIN = 0.75

# Routed here only when the user clearly means the Shopify *store*, not generic catalog work.
_SHOPIFY_AGENT_IDS = frozenset(
    {"shopify", "shopify_orders", "shopify_products", "shopify_analytics", "shopify_customers"}
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
        # Presentation follow-up phrases — keep these in document, never route to creative
        "the slide", "the slides", "the deck", "my slides", "my deck",
        "make the slide", "make them look", "make it look",
        "slide design", "deck design", "slide layout", "deck layout",
        "slide style", "deck style", "visually appealing", "look appealing",
        "make it appealing", "make them appealing", "look good for",
        "slides look", "deck look", "slide look",
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
        "shopify_customers",
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
        "retargeting", "prospecting", "lookalike",
        "facebook campaign", "instagram campaign", "meta ads",
        "ad budget", "ad spend", "ad account",
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
        # visual content creation (graphics, images, designs)
        "instagram post", "facebook post", "tiktok",
        "twitter post", "linkedin post",
        "post graphic", "social graphic", "instagram graphic", "facebook graphic",
        "caption", "hashtag", "content idea",
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
        "creative asset",
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
        "expenses", "cash flow", "financial report",
        "profit and loss", "money in", "money out",
        "record expense", "finance summary", "financial overview",
        "p&l", "gross profit", "net profit", "operating cost",
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
    "shopify_customers": [
        "shopify customer", "shopify buyer", "shopify client",
        "tag customer", "tag shopify customer", "shopify vip",
        "win-back", "win back customer", "lapsed customer",
        "at-risk customer", "shopify segment", "customer segment shopify",
        "shopify loyalty", "shopify ltv customer", "top shopify customer",
        "abandoned cart customer", "message shopify customer",
        "shopify customer tag", "customer lifetime value shopify",
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
        "brochure", "presentation", "powerpoint", "power point", "pptx", "ppt",
        "slide deck", "slideshow", "slides for", "create presentation",
        "make a presentation", "build a presentation", "make slides",
        "create slides", "generate slides", "slide show",
        "proposal document", "proposal pdf", "proposal word",
    ],
    "analytics": [
        # Use qualified phrases so bare "analytics" doesn't tie with team_analytics/social_monitor
        "business analytics", "business dashboard", "performance report", "kpi",
        "business metrics", "revenue report", "monthly report",
        "weekly report", "how is my business", "business overview",
        "trend report", "growth rate", "overall performance",
        "business performance", "business stats", "business numbers",
        "show my stats", "show me stats", "my kpis",
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
    "seo": [
        "seo", "search engine optimization", "keyword research", "keywords for",
        "rank on google", "google ranking", "search ranking", "organic traffic",
        "meta description", "meta tags", "title tag", "h1 tag",
        "on-page seo", "technical seo", "local seo", "seo audit",
        "content strategy", "blog strategy", "content calendar", "topic ideas",
        "google business profile", "google my business", "local search",
        "backlinks", "link building", "guest posting", "domain authority",
        "page speed", "core web vitals", "schema markup", "structured data",
        "sitemap", "robots.txt", "canonical tags", "404 errors",
        "search console", "google search console", "search traffic",
        "optimize for search", "seo optimization", "improve seo",
        "product seo", "e-commerce seo", "category seo",
        "blog post seo", "content optimization", "seo content",
    ],

    # ── Spreadsheet / Workspace integrations ──────────────────────────────────
    "google_sheets": [
        "google sheets", "google sheet", "sync to sheets", "export to sheets",
        "spreadsheet", "my spreadsheet", "update sheet", "read sheet",
        "sheets integration", "google spreadsheet", "sync customers to sheets",
        "sync orders to sheets", "export to google", "google sheet report",
    ],
    "notion": [
        "notion", "notion page", "notion database", "sync to notion",
        "notion workspace", "update notion", "notion doc", "notion board",
        "notion integration", "write to notion", "notion table",
        "sync crm to notion", "notion notes",
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
    # Use whole-word matching to avoid "feed" matching "feedback", "story" matching
    # "story on this order", "video" matching "video call", etc.
    platform_format_words = {
        "feed", "story", "stories", "reel", "reels", "square", "portrait",
        "landscape", "carousel", "vertical", "horizontal",
        "facebook", "instagram", "tiktok", "linkedin", "twitter", "pinterest",
        "static", "video", "image",
        "one", "two", "first", "second", "both", "left", "right",
        "option a", "option b", "template",
    }
    msg_words = set(msg_lower.split())
    if any(w in msg_words for w in platform_format_words):
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
    "partnership proposal", "presentation", "pitch deck", "slide deck",
    # Creative/visual requests always exit document sticky
    "use creative", "creative agent", "creative specialist",
    "i want the design", "i want the visual", "i want the graphic",
    "want a design", "want the design", "need the design",
    "want a visual", "want a graphic", "want an image",
    "make the visual", "create the visual", "generate the visual",
    "make the graphic", "create the graphic", "generate the graphic",
    "make the image", "create the image", "generate the image",
    "the actual design", "actual visual", "real design",
    "creative design", "visual design",
    # Natural language variants users actually say
    "need design", "need a design", "need the design", "need a visual",
    "need the visual", "need a graphic", "need the graphic",
    "design to post", "design for the post", "design for my post",
    "design the post", "design this post", "design for instagram",
    "design for facebook", "design for tiktok",
    "i need design", "i need a design", "i need the design",
    "i need the visual", "i need a visual",
    "just the design", "just the visual", "just the graphic",
    "show me the design", "show the design", "get the design",
    "do the design", "do the visual", "do the graphic",
)


def _is_explicit_design_exit(msg_lower: str) -> bool:
    """True if the user clearly wants to leave a design session and go elsewhere.

    Uses startswith / exact phrase checks for short ambiguous markers like
    "switch to" to avoid false positives (e.g. "switch to creative" should NOT
    exit creative, but "switch to meta ads" should).
    """
    # Markers that are only safe to match at the START of the message
    _START_ONLY = ("switch to ", "back to ")
    for m in _DESIGN_EXIT_MARKERS:
        if any(m.startswith(s) for s in _START_ONLY):
            if msg_lower.startswith(m):
                return True
        else:
            if m in msg_lower:
                return True
    return False


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
        for m in history[-8:]:
            role = m.get("role", "user")
            content = str(m.get("content", ""))[:200]
            context_lines.append(f"{role}: {content}")
        recent = "\n".join(context_lines) if context_lines else "(new conversation)"

        prompt = (
            "You are the routing layer of a CRM assistant. "
            "Pick the single best specialist agent for this message.\n\n"
            "AGENT OWNERSHIP (strict — pick the most specific match):\n"
            "- invoices: creating, viewing, sending, or tracking invoices and their status\n"
            "- payments: recording/viewing payment receipts, who paid, outstanding payments (not invoices)\n"
            "- finance: P&L, cash flow, expenses, financial overview — NOT individual invoices or payments\n"
            "- stripe: ONLY when user explicitly mentions Stripe, payment links, Stripe subscriptions\n"
            "- analytics: business-wide KPIs, dashboards, monthly/weekly performance reports\n"
            "- sales: revenue by product, top sellers, sales trends — NOT financial P&L\n"
            "- inventory: add/edit/delete products, stock levels, SKUs, pricing — only when Shopify NOT mentioned\n"
            "- shop: storefront/shop page/catalog link/shop menu — NOT product editing\n"
            "- shopify / shopify_*: ONLY when user explicitly mentions Shopify or Shopify store\n"
            "- customers: customer records, segments, VIPs, health scores, at-risk customers\n"
            "- contacts: leads, contact database, import contacts, contact records (not customers)\n"
            "- quotes: short pricing docs — quotes, estimates, scope-of-work for a specific customer\n"
            "- document: long-form written docs — business plans, pitch decks, contracts, reports, press releases, proposals\n"
            "- meta_ads: Facebook/Instagram ad campaigns, budgets, ROAS, ad performance strategy\n"
            "- google_ads: Google Search/Display/Performance Max campaigns, quality score, adwords\n"
            "- creative: generating/refining VISUALS — graphics, flyers, ad images, social post images, carousels\n"
            "- social_inbox: social DMs, inbox conversations, replies, message history from social platforms\n"
            "- social_scheduler: scheduling posts, content calendar, publishing plans, when to post\n"
            "- social_monitor: post performance metrics, engagement analytics, reach, social ROI, likes/shares\n"
            "- messages: WhatsApp inbox, composing/reading WhatsApp messages to customers\n"
            "- broadcasts: bulk/mass WhatsApp message sends — promos, announcements, send to all\n"
            "- follow_ups: follow-up reminders, overdue contacts, reconnect scheduling\n"
            "- bookings: appointments, reservations, scheduling services, availability\n"
            "- automations: workflow triggers, auto-reply rules, sequences, automation setup\n"
            "- general: integrations/account status questions, cross-domain fallback\n\n"
            "DISAMBIGUATION RULES (apply in order):\n"
            "1. 'invoice' / 'create invoice' / 'unpaid invoice' / 'overdue invoice' → invoices (not finance, not stripe)\n"
            "2. 'expense' / 'cash flow' / 'P&L' / 'profit and loss' → finance (not invoices)\n"
            "3. 'stripe [anything]' → stripe; otherwise payment records → payments\n"
            "4. 'business plan' / 'pitch deck' / 'contract' / 'press release' / 'write a report' → document\n"
            "5. 'quote' / 'estimate' / 'scope of work' for a specific customer → quotes (not document)\n"
            "6. 'design an ad' / 'ad graphic' / 'ad image' / 'make a flyer' → creative (not meta_ads)\n"
            "7. 'facebook ad campaign' / 'ad budget' / 'ROAS' / 'ad spend' / 'retargeting' → meta_ads (not creative)\n"
            "8. 'add product' / 'edit product' / 'stock level' without Shopify → inventory (not shop, not shopify)\n"
            "9. 'my customers' / 'customer segment' / 'VIP customers' → customers (not contacts)\n"
            "10. 'leads' / 'contact database' / 'import contacts' → contacts (not customers)\n"
            "11. 'post performance' / 'engagement rate' / 'how are my posts doing' → social_monitor (not creative)\n"
            "12. 'schedule post' / 'content calendar' / 'when to post' → social_scheduler (not creative)\n"
            "13. 'social DM' / 'social inbox' / 'reply to social message' → social_inbox (not messages — messages=WhatsApp)\n"
            "14. 'send to all customers' / 'bulk message' / 'mass message' → broadcasts (not messages)\n"
            "15. 'how many social accounts' / 'connected integrations' → general\n\n"
            f"Available agents:\n{agent_menu}\n\n"
            f"Recent context:\n{recent}\n\n"
            f"User message: \"{message}\"\n\n"
            "Reply ONLY with valid JSON on one line: "
            "{\"agent\": \"<agent_id>\", \"confidence\": <0.0-1.0>, \"reason\": \"<one sentence>\"}\n"
            "confidence: 1.0 = unambiguously clear, 0.5 = could go either way. "
            "Choose the most specific agent. Use 'general' only if truly nothing else fits."
        )

        resp = await _chat_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            model_id="deepseek-v4-flash",
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

    Strategy (semantic-first):
      0.  Explicit agent from UI/API — user locked or picked a specialist.
      0a. Sticky creative — active multi-turn design flow (stateful, never interrupt).
      1.  Semantic router — cosine similarity on pre-embedded phrases (~70 ms, no LLM).
          Skips steps 2-3 when confidence ≥ 0.72 with margin ≥ 0.03.
      2.  LLM routing — fallback when semantic confidence is low.
      3.  Keyword scoring — last-resort if both LLM fails and returns low confidence.
    Always returns a valid agent_id that exists in agent_registry.
    """
    msg_lower = message.lower()

    # ── 0. Explicit specialist from client (agent picker / lock) ──────────────
    if explicit_agent:
        from .agents import resolve_agent_id
        rid = resolve_agent_id(explicit_agent.strip())
        if rid in agent_registry:
            logger.info("[IntentRouter] explicit client agent → %s", rid)
            return rid

    _AGENT_ALIASES_LOCAL = {"design": "creative"}
    prev_agent_resolved = _AGENT_ALIASES_LOCAL.get(prev_agent or "", prev_agent or "")

    # ── 0a. Sticky creative — only for active stateful design flows ───────────
    # Creative is heavily stateful (template / platform / staged image / render).
    # Keep it sticky ONLY when the design flow is genuinely in progress.
    # Always exit if user explicitly asks to leave OR wants a text document.
    is_active_creative = (
        "creative" in agent_registry
        and (prev_agent_resolved == "creative" or design_flow_active)
    )
    if is_active_creative:
        if "document" in agent_registry and _is_text_document_intent(msg_lower):
            logger.info("[IntentRouter] leaving creative → document (text document intent)")
            return "document"
        if not _is_explicit_design_exit(msg_lower):
            logger.info(
                "[IntentRouter] sticky → creative (active design flow; prev=%r flow_active=%s)",
                prev_agent, design_flow_active,
            )
            return "creative"
        logger.info("[IntentRouter] leaving creative (explicit exit: %r)", message[:60])

    # ── 0b. Sticky social_scheduler — keep Samuel mid-flow ───────────────────
    # Scheduling is multi-turn (design → approve → time → confirm).
    # Short replies like "Instagram", "tomorrow", "10am", "yes" must not re-route.
    _SCHEDULER_EXIT_PHRASES = (
        "whatsapp", "broadcast", "analytics", "how are my posts doing",
        "facebook ad", "google ad", "invoice", "payment",
    )
    if prev_agent_resolved == "social_scheduler" and "social_scheduler" in agent_registry:
        if not any(p in msg_lower for p in _SCHEDULER_EXIT_PHRASES):
            logger.info("[IntentRouter] sticky → social_scheduler (mid-scheduling flow)")
            return "social_scheduler"

    # ── 1. Semantic route — embedding cosine-similarity (no LLM call) ────────
    # ~50-80 ms vs ~500 ms for LLM. Falls back to LLM when confidence is low.
    try:
        from .semantic_router import route as _sem_route
        sem = await _sem_route(message, agent_registry)
        if sem is not None:
            sem_agent, sem_score = sem
            # Apply the same creative/catalog safety overrides as the LLM path
            if _design_or_creative_document_intent(msg_lower) and sem_agent in _CATALOG_STOCK_WITHOUT_DESIGN_TOOLS:
                sem_agent = _prefer_creative_agent(msg_lower, agent_registry)
                logger.info("[IntentRouter] Semantic override: creative intent; was catalog agent")
            if sem_agent in agent_registry:
                logger.info("[IntentRouter] Semantic → %s (score=%.3f)", sem_agent, sem_score)
                return sem_agent
    except Exception as _sem_exc:
        logger.warning("[IntentRouter] Semantic router error: %s", _sem_exc)

    # ── 2. LLM route — fallback when semantic confidence is low ──────────────
    # Runs before any keyword checks. LLM understands meaning, not just words.
    llm_choice = await _llm_route_choice(message, history, agent_registry, msg_lower)
    if llm_choice is not None:
        chosen, confidence = llm_choice
        if confidence >= _LLM_ROUTE_CONFIDENCE_MIN:
            if chosen == "general" and _is_text_document_intent(msg_lower) and "document" in agent_registry:
                logger.info("[IntentRouter] LLM → document (override: text-doc intent mis-routed to general)")
                return "document"
            logger.info("[IntentRouter] LLM → %s (confidence=%.2f)", chosen, confidence)
            return chosen
        logger.info("[IntentRouter] LLM low-confidence (%.2f); falling back to keywords", confidence)

    # ── 3. Keyword scoring fallback ───────────────────────────────────────────
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

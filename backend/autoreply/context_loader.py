"""
context_loader.py — loads everything Claude needs for one turn.

What gets loaded:
  - Last 10 messages (conversation history = state)
  - Mini-state (5 fields: active_flow, flow_product_id, flow_step, last_menu+TTL, escalated)
  - Product catalog (id, name, price, category — sanitized)
  - Services (id, name, price, duration — sanitized)
  - Business config (name, type, currency, payment methods, hours, etc.)

Cost control: 10 messages max, catalog fields only (no long descriptions).
Security: all catalog text sanitized against prompt injection.
"""
from __future__ import annotations

import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Last menu expires after this many hours — prevents "1" resolving to yesterday's catalog
MENU_TTL_HOURS = 2

# Business types that support product orders
_ORDER_TYPES = {"retail", "restaurant", "wholesale", "food", "bakery", "grocery",
                "creator",   # digital products (courses, presets, content packages)
                "general"}   # flexible — may have products OR services OR both

# Business types that support service bookings
_BOOKING_TYPES = {"salon", "beauty", "spa", "services", "rental", "clinic", "healthcare",
                  "gym", "fitness", "photography", "events", "cleaning", "repair",
                  "general"}  # flexible — may have services in addition to products

# Business types that support both orders AND bookings
_BOTH_TYPES: set = set()  # restaurant handles dine-in/delivery/takeout entirely via create_order


def _sanitize(text: Any) -> str:
    """Strip prompt-injection patterns from catalog / config fields."""
    if not text:
        return ""
    cleaned = re.sub(
        r'\b(ignore|forget|disregard|override|system\s*prompt|instruction|jailbreak)\b',
        "***",
        str(text),
        flags=re.I,
    )
    return cleaned.strip()


def _supports_orders(business_type: str) -> bool:
    bt = (business_type or "").lower()
    return bt in _ORDER_TYPES or bt in _BOTH_TYPES


def _supports_bookings(business_type: str) -> bool:
    bt = (business_type or "").lower()
    return bt in _BOOKING_TYPES or bt in _BOTH_TYPES


async def load_context(db, user_id, customer_id, user: dict) -> dict:
    """
    Returns:
        {
            "messages": [...],          # last 10, oldest first
            "mini_state": {...},        # 5-field state
            "products": [...],          # sanitized catalog
            "services": [...],          # sanitized services
            "business_config": {...},   # all business settings
        }
    """
    messages = await _load_messages(db, user_id, customer_id)
    mini_state = await _load_mini_state(db, user_id, customer_id)
    settings = user.get("settings", {}) or {}
    business_type = (settings.get("business_type") or user.get("business_type", "retail")).lower()

    # Always load products — all businesses add their catalog via ProductCatalogModal → db.products
    products = await _load_products(db, user_id)

    # Additionally load from services collection for booking businesses
    # (secondary catalog; most items will be in db.products)
    services = []
    if _supports_bookings(business_type):
        services = await _load_services(db, user_id)

    business_config = _build_business_config(user, settings, business_type)

    return {
        "messages": messages,
        "mini_state": mini_state,
        "products": products,
        "services": services,
        "business_config": business_config,
    }


async def _load_messages(db, user_id, customer_id) -> List[Dict]:
    if not customer_id:
        return []
    raw = await db.messages.find(
        {
            "user_id": user_id,
            "customer_id": customer_id,
            "send_context": {"$ne": "fallback"},  # exclude fallback error msgs from AI history
        }
    ).sort("created_at", -1).limit(10).to_list(10)

    return [
        {
            "role": "customer" if m.get("direction") == "incoming" else "assistant",
            "content": m.get("content", ""),
        }
        for m in reversed(raw)
        if m.get("content")
    ]


async def _load_mini_state(db, user_id, customer_id) -> Dict:
    if not customer_id:
        return {}
    doc = await db.conversation_states.find_one(
        {"user_id": user_id, "customer_id": customer_id}
    )
    if not doc:
        return {}

    state: Dict = {
        "active_flow":      doc.get("active_flow"),
        "flow_product_id":  doc.get("flow_product_id"),
        "flow_step":        doc.get("flow_step"),
        "escalated":        doc.get("escalated", False),
    }

    # last_menu with TTL check
    last_menu = doc.get("last_menu") or {}
    last_menu_at = doc.get("last_menu_at")
    if last_menu and last_menu_at:
        # Normalise to naive UTC
        if hasattr(last_menu_at, "tzinfo") and last_menu_at.tzinfo is not None:
            last_menu_at = last_menu_at.replace(tzinfo=None)
        age_hours = (datetime.utcnow() - last_menu_at).total_seconds() / 3600
        if age_hours <= MENU_TTL_HOURS:
            state["last_menu"] = last_menu
        else:
            logger.info(f"[ContextLoader] last_menu expired ({age_hours:.1f}h old) — discarded")

    return state


async def _load_products(db, user_id) -> List[Dict]:
    raw = await db.products.find(
        {"user_id": user_id, "is_active": {"$ne": False}}
    ).limit(40).to_list(40)

    products = []
    for p in raw:
        name = _sanitize(p.get("name", ""))
        if not name:
            continue
        # Collect all image URLs for this product
        imgs = []
        if p.get("image_url"):
            imgs.append(p["image_url"])
        for extra in p.get("images", []):
            if extra and extra not in imgs:
                imgs.append(extra)

        raw_variants = p.get("variants") or []
        variants = [
            {"name": _sanitize(v.get("name", "")), "price": float(v.get("price", p.get("price", 0)))}
            for v in raw_variants if v.get("name", "").strip()
        ]

        raw_groups = p.get("modifier_groups") or []
        modifier_groups = []
        for g in raw_groups:
            options = [
                {"name": _sanitize(o.get("name", "")), "price_delta": float(o.get("price_delta", 0))}
                for o in (g.get("options") or []) if o.get("name", "").strip()
            ]
            if options:
                modifier_groups.append({
                    "name":         _sanitize(g.get("name", "")),
                    "required":     bool(g.get("required", False)),
                    "multi_select": bool(g.get("multi_select", False)),
                    "options":      options,
                })

        products.append({
            "id":              str(p["_id"]),
            "name":            name,
            "price":           float(p.get("price", 0)),
            "category":        _sanitize(p.get("category", "")),
            "sub_category":    _sanitize(p.get("sub_category", "")),
            "description":     _sanitize(p.get("description", "")),
            "in_stock":        p.get("in_stock", True),
            "image_url":       imgs[0] if imgs else "",
            "images":          imgs[:3],
            "variants":        variants,
            "modifier_groups": modifier_groups,
        })
    return products


async def _load_services(db, user_id) -> List[Dict]:
    # Try 'services' collection; some older installs may not have it
    try:
        raw = await db.services.find(
            {"user_id": user_id, "is_active": {"$ne": False}}
        ).limit(30).to_list(30)
    except Exception:
        return []

    services = []
    for s in raw:
        name = _sanitize(s.get("name", ""))
        if not name:
            continue
        services.append({
            "id":        str(s["_id"]),
            "name":      name,
            "price":     float(s.get("price", 0)),
            "duration":  s.get("duration_minutes", 0),
            "category":  _sanitize(s.get("category", "")),
            "is_rental": s.get("service_category") == "rental",
        })
    return services


def _build_business_config(user: dict, settings: dict, business_type: str) -> Dict:
    # Currency: settings → user doc → fallback
    currency = settings.get("currency") or user.get("currency", "KES")

    # Payment methods → list of human-readable strings
    raw_pm = user.get("payment_methods") or []
    payment_methods: List[str] = []
    for pm in raw_pm:
        if isinstance(pm, dict):
            line = pm.get("name", "")
            if pm.get("details"):
                line += f": {pm['details']}"
        else:
            line = str(pm)
        line = line.strip()
        if line:
            payment_methods.append(line)

    bk = user.get("business_knowledge") or {}

    # If structured payment_methods is empty, try to pull details from business_knowledge
    if not payment_methods and bk.get("pricing_info"):
        payment_methods = [_sanitize(bk["pricing_info"])]

    return {
        "type":               business_type,
        "name":               _sanitize(user.get("business_name", "")),
        "currency":           currency,
        "payment_methods":    payment_methods,
        "business_hours":     _sanitize(bk.get("business_hours", "")),
        "delivery_info":      _sanitize(bk.get("delivery_info", "")),
        "about":              _sanitize(bk.get("business_description", "")),
        "products_services":  _sanitize(bk.get("products_services", "")),
        "special_offers":     _sanitize(bk.get("special_offers", "")),
        "faqs":               _sanitize(bk.get("faqs", "")),
        "supports_orders":    _supports_orders(business_type),
        "supports_bookings":  _supports_bookings(business_type),
        "supports_delivery":  business_type in ("retail", "restaurant", "wholesale", "food", "grocery", "bakery"),
        "supports_pickup":    True,
        # Restaurant-specific config
        "restaurant_has_dine_in":    bk.get("restaurant_has_dine_in", True),
        "restaurant_has_delivery":   bk.get("restaurant_has_delivery", True),
        "restaurant_has_takeout":    bk.get("restaurant_has_takeout", True),
        "restaurant_table_range":    _sanitize(bk.get("restaurant_table_range", "")),
        "restaurant_avg_wait":       _sanitize(bk.get("restaurant_avg_wait", "")),
        "restaurant_min_delivery":   _sanitize(bk.get("restaurant_min_delivery", "")),
        "restaurant_has_reservations": bool(settings.get("restaurant_has_reservations", False)),
    }

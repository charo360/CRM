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
                  "hotel",     # a room is booked for dates, like a rental
                  "tech",      # callouts and repairs are booked like any service
                  "general"}   # flexible — may have services in addition to products

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


async def load_context(db, user_id, customer_id, user: dict, message: str = "") -> dict:
    """
    Returns:
        {
            "messages": [...],          # last 10, oldest first
            "mini_state": {...},        # 5-field state
            "products": [...],          # sanitized catalog (priority on relevance to current message)
            "services": [...],          # sanitized services
            "business_config": {...},   # all business settings
        }
    """
    messages = await _load_messages(db, user_id, customer_id)
    mini_state = await _load_mini_state(db, user_id, customer_id)
    settings = user.get("settings", {}) or {}
    bk_type = (user.get("business_knowledge") or {}).get("business_type", "")
    # Business Knowledge holds the type the merchant chose; the settings copy is
    # the sign-up default. Read the chosen one first, as the shop and the app do.
    business_type = (bk_type or settings.get("business_type") or user.get("business_type") or "retail").lower()

    # Load local products
    products = await _load_products(db, user_id)

    # Additionally load live products from WooCommerce if connected
    # We pass the user message to prioritize relevant products
    wc_products = await _load_wc_products(db, user_id, message)
    if wc_products:
        # Merge, preferring WC products if IDs or names clash, but keeping total count reasonable
        seen_names = {p["name"].lower() for p in wc_products}
        for p in products:
            if p["name"].lower() not in seen_names:
                wc_products.append(p)
        products = wc_products[:50]  # Cap at 50 for context window

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


async def _load_wc_products(db, user_id, search_query: str = "") -> List[Dict]:
    """Fetch live products from connected WooCommerce store if keys are present."""
    import httpx, os, base64
    from blog.routes import _blog_url_for_response

    blog = await db.blogs.find_one({"client_id": user_id})
    if not blog:
        return []

    site_base = await _blog_url_for_response(db, blog)
    if not site_base:
        return []

    wc_key = os.getenv("WC_CONSUMER_KEY", "")
    wc_secret = os.getenv("WC_CONSUMER_SECRET", "")
    if not wc_key or not wc_secret:
        return []

    try:
        # Detect if we should search specifically
        url = f"{site_base}/wp-json/wc/v3/products?per_page=30&status=publish"
        
        # Simple extraction of possible product keywords from message
        if search_query:
            # Clean message: remove common stopwords/short words
            words = [w for w in search_query.lower().split() if len(w) > 3]
            if words:
                search_term = " ".join(words[:3]) # Use first few significant words
                url += f"&search={search_term}"

        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, auth=(wc_key, wc_secret))
            if r.status_code != 200:
                # If search failed or returned nothing, fallback to general products
                if "search=" in url:
                    r = await client.get(f"{site_base}/wp-json/wc/v3/products?per_page=30&status=publish", auth=(wc_key, wc_secret))
                
                if r.status_code != 200:
                    return []
            
            raw = r.json()
            products = []
            for p in raw:
                # Handle images
                imgs = [img.get("src") for img in p.get("images", []) if img.get("src")]
                
                products.append({
                    "id":              f"wc_{p['id']}", # Prefix to distinguish from local DB
                    "name":            _sanitize(p.get("name", "")),
                    "price":           float(p.get("price") or 0),
                    "category":        _sanitize(p.get("categories", [{}])[0].get("name", "") if p.get("categories") else ""),
                    "description":     _sanitize(p.get("short_description") or p.get("description", "")),
                    "in_stock":        p.get("stock_status") == "instock",
                    "image_url":       imgs[0] if imgs else "",
                    "images":          imgs[:3],
                    "is_live_wc":      True,
                    "permalink":       p.get("permalink", ""),
                })
            return products
    except Exception as e:
        logger.warning(f"[ContextLoader] WC fetch failed for {user_id}: {e}")
        return []


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
        "owner_name":         _sanitize(user.get("owner_name") or (user.get("settings") or {}).get("owner_name") or user.get("name", "")),
        "owner_title":        _sanitize(user.get("owner_title") or (user.get("settings") or {}).get("owner_title", "")),
        "currency":           currency,
        "payment_methods":    payment_methods,
        "business_hours":     _sanitize(bk.get("business_hours", "")),
        "business_location":  _sanitize(bk.get("business_location", "")),
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
        # Retail-specific config
        "retail_has_delivery":       bk.get("retail_has_delivery", True),
        "retail_has_pickup":         bk.get("retail_has_pickup", True),
        "retail_delivery_fee":       _sanitize(bk.get("retail_delivery_fee", "")),
        "retail_free_delivery_above": _sanitize(bk.get("retail_free_delivery_above", "")),
        "retail_has_custom_orders":  bk.get("retail_has_custom_orders", False),
        "retail_custom_lead_time":   _sanitize(bk.get("retail_custom_lead_time", "")),
        "retail_return_policy":      _sanitize(bk.get("retail_return_policy", "")),
        # Bakery-specific config
        "bakery_advance_days":       bk.get("bakery_advance_days", 3),
        "bakery_deposit_required":   bk.get("bakery_deposit_required", False),
        "bakery_deposit_pct":        bk.get("bakery_deposit_pct", 50),
        # Grocery-specific config
        "grocery_delivery_slots":    _sanitize(bk.get("grocery_delivery_slots", "")),
        "grocery_min_order":         _sanitize(bk.get("grocery_min_order", "")),
        "grocery_allow_substitutions": bk.get("grocery_allow_substitutions", True),
        # Wholesale-specific config
        "wholesale_lead_time":       _sanitize(bk.get("wholesale_lead_time", "")),
        "wholesale_min_order_value": _sanitize(bk.get("wholesale_min_order_value", "")),
        "wholesale_payment_terms":   _sanitize(bk.get("wholesale_payment_terms", "")),
        "wholesale_has_credit_account": bk.get("wholesale_has_credit_account", False),
        # Salon-specific config
        "salon_multiple_stylists":   bk.get("salon_multiple_stylists", False),
        "salon_stylist_names":       _sanitize(bk.get("salon_stylist_names", "")),
        "salon_deposit_required":    bk.get("salon_deposit_required", False),
        "salon_deposit_pct":         bk.get("salon_deposit_pct", 50),
        "salon_cancellation_policy": _sanitize(bk.get("salon_cancellation_policy", "")),
        # Spa-specific config
        "spa_has_couples":           bk.get("spa_has_couples", True),
        "spa_deposit_required":      bk.get("spa_deposit_required", True),
        "spa_deposit_pct":           bk.get("spa_deposit_pct", 50),
        "spa_cancellation_hours":    bk.get("spa_cancellation_hours", 24),
        # Repair-specific config
        "repair_has_onsite":         bk.get("repair_has_onsite", True),
        "repair_has_dropoff":        bk.get("repair_has_dropoff", True),
        "repair_diagnosis_free":     bk.get("repair_diagnosis_free", True),
        "repair_turnaround":         _sanitize(bk.get("repair_turnaround", "")),
        "repair_warranty":           _sanitize(bk.get("repair_warranty", "")),
        # Services-specific config
        "services_has_onsite":       bk.get("services_has_onsite", True),
        "services_has_remote":       bk.get("services_has_remote", True),
        "services_quote_first":      bk.get("services_quote_first", False),
        "services_deposit_required": bk.get("services_deposit_required", False),
        "services_turnaround":       _sanitize(bk.get("services_turnaround", "")),
        "services_cancellation_policy": _sanitize(bk.get("services_cancellation_policy", "")),
        # Cleaning-specific config
        "cleaning_has_recurring":    bk.get("cleaning_has_recurring", True),
        "cleaning_has_commercial":   bk.get("cleaning_has_commercial", False),
        "cleaning_supplies_included": bk.get("cleaning_supplies_included", True),
        # Fitness-specific config
        "fitness_has_classes":       bk.get("fitness_has_classes", True),
        "fitness_has_memberships":   bk.get("fitness_has_memberships", True),
        "fitness_has_personal_training": bk.get("fitness_has_personal_training", False),
        "fitness_has_trial":         bk.get("fitness_has_trial", True),
        "fitness_class_schedule":    _sanitize(bk.get("fitness_class_schedule", "")),
        # Events-specific config
        "events_deposit_pct":        bk.get("events_deposit_pct", 50),
        "events_lead_time":          _sanitize(bk.get("events_lead_time", "")),
        "events_delivery_days":      _sanitize(bk.get("events_delivery_days", "")),
        # Healthcare-specific config
        "hc_consultation_fee":       _sanitize(bk.get("hc_consultation_fee", "")),
        "hc_has_lab_tests":          bk.get("hc_has_lab_tests", False),
        "hc_has_home_visit":         bk.get("hc_has_home_visit", False),
        "hc_prep_instructions":      _sanitize(bk.get("hc_prep_instructions", "")),
        "hc_insurance_accepted":     _sanitize(bk.get("hc_insurance_accepted", "")),
        # Support-specific config
        "support_ticket_prefix":     _sanitize(bk.get("support_ticket_prefix", "TKT")),
        "support_response_sla":      _sanitize(bk.get("support_response_sla", "")),
        "support_has_billing_support":   bk.get("support_has_billing_support", True),
        "support_has_technical_support": bk.get("support_has_technical_support", True),
        "support_has_complaints":    bk.get("support_has_complaints", True),
        "support_has_live_handoff":  bk.get("support_has_live_handoff", False),
        "support_escalation_policy": _sanitize(bk.get("support_escalation_policy", "")),
        "support_refund_policy":     _sanitize(bk.get("support_refund_policy", "")),
        # Hotel-specific config
        "hotel_checkin_time":        _sanitize(bk.get("hotel_checkin_time", "2:00 PM")),
        "hotel_checkout_time":       _sanitize(bk.get("hotel_checkout_time", "11:00 AM")),
        "hotel_min_nights":          bk.get("hotel_min_nights", 0),
        "hotel_deposit_required":    bk.get("hotel_deposit_required", True),
        "hotel_deposit_pct":         bk.get("hotel_deposit_pct", 30),
        "hotel_has_meal_plans":      bk.get("hotel_has_meal_plans", False),
        "hotel_meal_plan_options":   _sanitize(bk.get("hotel_meal_plan_options", "")),
        "hotel_has_airport_transfer": bk.get("hotel_has_airport_transfer", False),
        "hotel_has_spa":             bk.get("hotel_has_spa", False),
        "hotel_has_pool":            bk.get("hotel_has_pool", False),
        "hotel_cancellation_policy": _sanitize(bk.get("hotel_cancellation_policy", "")),
        # Rental-specific config
        "rental_type":               _sanitize(bk.get("rental_type", "property")),
        "rental_deposit_required":   bk.get("rental_deposit_required", True),
        "rental_deposit_pct":        bk.get("rental_deposit_pct", 30),
        "rental_min_nights":         bk.get("rental_min_nights", 0),
        "rental_checkin_time":       _sanitize(bk.get("rental_checkin_time", "")),
        "rental_checkout_time":      _sanitize(bk.get("rental_checkout_time", "")),
        "rental_pet_policy":         _sanitize(bk.get("rental_pet_policy", "")),
        "rental_cancellation_policy": _sanitize(bk.get("rental_cancellation_policy", "")),
        "rental_has_extras":         bk.get("rental_has_extras", False),
    }

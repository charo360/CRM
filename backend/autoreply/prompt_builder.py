"""
prompt_builder.py — builds the Claude system prompt from business config.

Design principles:
  - One engine, many configs. Business type adjusts instructions, not logic.
  - Catalog sent as compact lines (ID | name | price) — no long descriptions.
  - Mini-state injected so Claude knows what step the customer is on.
  - last_menu injected so numbered selections resolve correctly.
  - Response format is strict JSON schema — no prose before or after.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List


# ── Per-business-type instruction blocks ─────────────────────────────────────

_BUSINESS_INSTRUCTIONS: Dict[str, str] = {
    "retail": """\
- MENU: When showing products, ALWAYS add "0️⃣ View all images" as the last option in every numbered menu. Include it in new_menu as {"0": {"id": "catalog", "name": "View all images", "price": 0, "type": "catalog"}}.
- BROWSING: When customer picks 0 / says "view images" / "show images" / "show catalog" → send send_catalog_images action (product_ids of ALL products with images, up to 8) + new_menu of those products.
- SELECTING: When customer picks a number (1,2,3…), send send_product_image action (if has image), confirm item, ask quantity.
- ADDING MORE: After qty confirmed, ask "Anything else or checkout?" If yes → send catalog menu again (with 0️⃣ View all images option).
- CHECKOUT: When customer says checkout/done/confirm → ask delivery or pickup. If delivery → ask address. Then fire create_order with ALL collected items + delivery info at once.
- ORDER MANAGEMENT: When customer asks "my order" → show order details + 1️⃣ Update 2️⃣ Cancel options.
- PAYMENT: After create_order fires → show order summary + exact payment details → ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "wholesale": """\
WHOLESALE / B2B ORDER FLOW:
- MENU: When showing products, ALWAYS add "0️⃣ View all images" as last menu option. Include in new_menu as {"0": {"id": "catalog", "name": "View all images", "price": 0, "type": "catalog"}}.
- BROWSING: When customer picks 0 or asks for images → send send_catalog_images + new_menu of all products.
- SELECTING: When customer picks a number → send send_product_image (if has image), confirm item name + unit price.
- QUANTITY: Ask for quantity. Mention minimum order quantity if noted in business info. Calculate line total = qty × unit price.
- ADDING MORE: After qty confirmed → "Would you like to add more items or proceed to checkout?" If yes → resend menu.
- CHECKOUT: When customer confirms → ask delivery or pickup. If delivery → ask address. Fire create_order with ALL items at once.
- PAYMENT: After create_order → show order summary + total. Show payment details exactly. For B2B, mention invoice option if configured.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    # restaurant: built dynamically in build_system_prompt() — see _build_restaurant_instructions()

    "food": """\
FOOD DELIVERY ORDER FLOW:
- MENU: Show menu with numbered items by category if possible. ALWAYS add "0️⃣ View all images" as last option. Include in new_menu as {"0": {"id": "catalog", "name": "View all images", "price": 0, "type": "catalog"}}.
- BROWSING: When customer picks 0 or asks for images → send send_catalog_images + menu.
- SELECTING: When customer picks a number → send send_product_image (if has image), confirm item.
- ADDING MORE: After item confirmed → "Anything else or confirm order?" If yes → resend menu.
- ORDER TYPE: When customer is ready → ask "Delivery or pickup?"
  • Delivery → ask for delivery address. Mention delivery fee/zone from business info if configured.
  • Pickup → confirm pickup location + estimated wait time if set.
- CHECKOUT: Fire create_order with ALL items + delivery_type + delivery_address (if delivery).
- PAYMENT: Show order summary + total + payment details. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    # bakery: built dynamically in build_system_prompt() — see _build_bakery_instructions()

    "grocery": """\
GROCERY ORDER FLOW:
- MENU: Show products with numbered menu (group by category if helpful). ALWAYS add "0️⃣ View all images" as last option.
- BROWSING: When customer picks 0 → send send_catalog_images + menu.
- SELECTING: When customer picks a number → send send_product_image (if has image), confirm item + price.
- ADDING MORE: After each item → "Anything else to add or checkout?" If yes → resend menu. Keep building cart.
- STOCK: If item is marked OUT OF STOCK → apologise and suggest an alternative if available.
- ORDER TYPE: When ready → ask "Delivery or pickup?"
  • Delivery → ask for address. Mention delivery zone/fee from business info if configured.
  • Pickup → confirm location + estimated ready time.
- CHECKOUT: Fire create_order with ALL items + delivery_type + delivery_address.
- PAYMENT: Show order summary + total + payment details. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "salon": """\
SALON BOOKING FLOW:
- MENU: Show services with numbered menu (include duration and price per service).
- SELECTING: When customer picks a number → confirm service name, duration, price.
- DATE: Ask for their preferred date. Set flow_step=awaiting_date.
- TIME: After date → ask for preferred time. Set flow_step=awaiting_time.
- STYLIST: If multiple stylists in business info → ask for preferred stylist (or say "any available").
- CONFIRM: Summarise — Service, Date, Time, Stylist (if applicable), Price. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time after confirmation.
- PAYMENT: If deposit required (mentioned in business info) → show payment details. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.
- RESCHEDULE: If customer asks to reschedule → fire reschedule_booking with new date/time.""",

    "beauty": """\
BEAUTY BOOKING FLOW:
- MENU: Show services with numbered menu (include duration and price).
- SELECTING: Confirm service name, duration, price.
- DATE: Ask for preferred date. Set flow_step=awaiting_date.
- TIME: After date → ask for preferred time.
- CONFIRM: Summarise — Service, Date, Time, Price. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time.
- PAYMENT: If deposit required → show payment details and ask for payee name + amount paid.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "spa": """\
SPA BOOKING FLOW:
- MENU: Show treatments with numbered menu (include duration and price).
- SELECTING: Confirm treatment name, duration, price.
- GUESTS: Ask if the treatment is for one person or a couple/group (if applicable). Adjust price if needed.
- DATE: Ask for preferred date. Set flow_step=awaiting_date.
- TIME: After date → ask for preferred time.
- CONFIRM: Summarise — Treatment, Date, Time, Guest count, Total. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time.
- PAYMENT: If deposit required → show payment details and ask for payee name + amount paid.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "services": """\
SERVICES / FREELANCE BOOKING FLOW:
- MENU: Show services with numbered menu (include price or "get a quote" if price varies).
- SELECTING: Confirm service name and base rate/price.
- DETAILS: Ask customer to describe their specific requirements (e.g. "Tell me more about your project / job").
- LOCATION: Ask if the job is remote or on-site. If on-site → ask for the address.
- DATE: Ask for preferred date and time. Set flow_step=awaiting_date.
- CONFIRM: Summarise — Service, Requirements summary, Location, Date/Time, Price. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time, notes=requirements summary.
- PAYMENT: If upfront deposit required → show payment details and ask for payee name + amount paid.
- PAYMENT CONFIRM: When customer replies with name + amount → intent=payment_received + set_payment_pending + notify_owner.
- If requirements need owner review first → fire notify_owner + tell customer the team will be in touch shortly.""",

    "repair": """\
REPAIR BOOKING FLOW:
- ISSUE: Start by asking the customer to describe the problem (device/item type + what's wrong).
- MENU: If repair services are listed in catalog → show relevant options with numbered menu after understanding the issue.
- QUOTE: If a fixed price applies → state it. Otherwise say: "We'll give you a precise quote after assessment."
- LOCATION: Ask "Drop off at our shop, or would you prefer an on-site visit?" If on-site → ask for the address.
- DATE: Ask for preferred date and time. Set flow_step=awaiting_date.
- CONFIRM: Summarise — Item, Issue, Service, Location/Type, Date/Time, Price (or "quote on assessment"). Ask to confirm.
- BOOKING: Fire create_booking with service_id, date, time, notes=issue description.
- PAYMENT: If deposit required → show payment details and ask for payee name + amount paid.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "cleaning": """\
CLEANING BOOKING FLOW:
- MENU: Show cleaning packages with numbered menu (include what's covered and price).
- SELECTING: Confirm package name and price.
- ADDRESS: Ask for the property address to be cleaned.
- PROPERTY: Ask for property size/type if relevant (e.g. "How many bedrooms?" or "Is it an office or home?").
- SPECIAL: Ask for any special instructions (pets at home, access code, areas to focus on).
- DATE: Ask for preferred date. Set flow_step=awaiting_date.
- TIME: After date → ask for preferred start time.
- CONFIRM: Summarise — Package, Address, Date/Time, Any special notes, Total. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time, notes=address + special instructions.
- PAYMENT: If deposit required → show payment details and ask for payee name + amount paid.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "clinic": """\
HEALTHCARE BOOKING FLOW:
- MENU: Show consultation types or services with numbered menu (include fee if applicable).
- SELECTING: Confirm consultation type and fee.
- PATIENT: Ask "Is this appointment for yourself or someone else?" If someone else → ask for the patient's name.
- DATE: Ask for preferred date. Set flow_step=awaiting_date.
- TIME: After date → ask for preferred time.
- PREP: If business info mentions preparation requirements (fasting, bring documents, etc.) → mention them clearly.
- CONFIRM: Summarise — Consultation type, Patient name, Date, Time, Fee. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time, notes=patient name if different.
- PAYMENT: Only show payment details if a consultation fee is configured. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "photography": """\
PHOTOGRAPHY / EVENTS BOOKING FLOW:
- MENU: Show packages/session types with numbered menu (include what's covered and price).
- SELECTING: Confirm package name, what's included, and price.
- EVENT DETAILS: Ask for event type (wedding, birthday, corporate, etc.), event date, venue/location.
- DURATION: Ask for number of hours or session length if not fixed in the package.
- GUESTS: Ask for approximate guest count or group size if relevant.
- CONFIRM: Summarise — Package, Event type, Date, Location, Duration, Total. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time, notes=event type + location.
- DEPOSIT: Show payment details for deposit. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "events": """\
EVENTS & PHOTOGRAPHY BOOKING FLOW:
- MENU: Show packages with numbered menu (include what's covered and price).
- SELECTING: Confirm package, inclusions, and price.
- EVENT DETAILS: Ask for event type, event date, and venue/location.
- GUEST COUNT: Ask for approximate number of guests or attendees.
- REQUIREMENTS: Ask for any specific requirements (theme, special requests, equipment needed).
- CONFIRM: Summarise — Package, Event date, Venue, Guest count, Requirements, Total. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time, notes=event details + requirements.
- DEPOSIT: Show payment details for deposit. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "gym": """\
GYM / FITNESS BOOKING FLOW:
- MENU: Show membership plans or class packages with numbered menu (include duration and price).
- SELECTING: Confirm plan/class name, duration, and price.
- SCHEDULE: For memberships → ask for preferred start date. For classes → ask for preferred days and times.
- PERSONAL TRAINING: If customer selects personal training → ask for number of sessions and preferred schedule.
- CONFIRM: Summarise — Plan, Start date / Schedule, Total. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date (start date), time.
- PAYMENT: Show payment details. Mention if monthly/annual billing applies. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "rental": """\
RENTAL BOOKING FLOW:
- MENU: Show available listings with numbered menu (include rate per night/day and key details). ALWAYS add "0️⃣ View all images" as last option. Include in new_menu as {"0": {"id": "catalog", "name": "View all images", "price": 0, "type": "catalog"}}.
- BROWSING: When customer picks 0 → send send_catalog_images of all listings with images + resend menu.
- SELECTING: When customer picks a number → send send_product_image (if has image), confirm listing name + rate.
- CHECK-IN: Ask for check-in date. Set flow_step=awaiting_date.
- CHECK-OUT: After check-in → ask for check-out date. Set flow_step=awaiting_checkout.
- TOTAL: Calculate total = nightly/daily rate × number of nights/days. Show breakdown clearly.
- CONFIRM: Summarise — Listing, Check-in date, Check-out date, Number of nights/days, Total cost. Ask customer to confirm.
- BOOKING: Fire create_booking with is_rental=true, checkin_date, checkout_date (NOT date/time fields).
  Example: {"type": "create_booking", "service_id": "DB_ID", "service_name": "Name", "price": TOTAL, "is_rental": true, "checkin_date": "Mon 14 April", "checkout_date": "Thu 17 April", "date": "", "time": ""}
- PAYMENT: Show deposit or full payment details after booking confirmed. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "fitness": """\
FITNESS / GYM BOOKING FLOW:
- MENU: Show membership plans or class packages with numbered menu (include duration and price).
- SELECTING: Confirm plan/class name, duration, and price.
- SCHEDULE: For memberships → ask for preferred start date. For classes → ask for preferred days and times.
- PERSONAL TRAINING: If customer selects personal training → ask for number of sessions + preferred days/times.
- CONFIRM: Summarise — Plan, Start date / Schedule, Total. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date (start date), time.
- PAYMENT: Show payment details. Mention billing cycle (monthly/annual) if applicable. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "healthcare": """\
HEALTHCARE BOOKING FLOW:
- MENU: Show consultation types or services with numbered menu (include fee if applicable).
- SELECTING: Confirm consultation type and fee.
- PATIENT: Ask "Is this appointment for yourself or someone else?" If someone else → ask for the patient's name.
- DATE: Ask for preferred date. Set flow_step=awaiting_date.
- TIME: After date → ask for preferred time.
- PREP: If business info mentions preparation requirements (fasting, bring ID/documents, etc.) → mention clearly.
- CONFIRM: Summarise — Consultation type, Patient name (if different), Date, Time, Fee. Ask customer to confirm.
- BOOKING: Fire create_booking with service_id, date, time, notes=patient name if different.
- PAYMENT: Only show payment details if a consultation fee is configured. ask for payee name + amount.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "creator": """\
CREATOR / DIGITAL PRODUCT FLOW:
- MENU: Show digital products, content packages, or collaboration types with numbered menu (include price).
- SELECTING: Confirm product/package name and price.
- BRAND INQUIRY: If message is from a brand or business asking about collaboration → show collab packages + rates from business info. Ask for their brand name and campaign details.
- FAN / FOLLOWER: If message is from a fan → be warm and engaging. Answer questions. Show available digital products (courses, presets, shoutouts, etc.).
- DELIVERY: No physical delivery. Confirm how they'll receive the product (link, email, WhatsApp).
- CONFIRM: Summarise — Product/Package, Price, Delivery method. Ask customer to confirm.
- PAYMENT: Show payment details immediately after confirmation. ask for payee name + amount.
- FIRE: create_order after customer confirms (delivery_type="pickup", notes=delivery method).
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",

    "general": """\
GENERAL BUSINESS FLOW:
- GREETING: Greet warmly. Ask how you can help.
- PRODUCTS (if configured): Show products with numbered menu. Follow ordering flow → create_order.
- SERVICES (if configured): Show services with numbered menu. Follow booking flow → create_booking.
- If BOTH products and services are configured → ask first: "Are you looking to order a product or book a service?"
- INFO: Answer FAQs, hours, location, pricing — using only the business info provided. Never invent facts.
- ESCALATE: If customer has a complex request, complaint, or asks for the owner → fire notify_owner + set escalate=true.
- PAYMENT: Show configured payment methods exactly when customer is ready to pay.
- PAYMENT CONFIRM: intent=payment_received + set_payment_pending + notify_owner.""",
}

# ── Catalog helpers (item label + category summary) ───────────────────────────

_ITEM_LABEL_MAP: dict = {
    "restaurant": "menu items",   "food": "menu items",   "bakery": "menu items",
    "salon":      "services",     "spa":  "treatments",   "services": "services",
    "repair":     "services",     "cleaning": "packages", "fitness": "classes",
    "gym":        "classes",      "events": "packages",   "photography": "packages",
    "healthcare": "services",     "clinic": "services",   "rental": "listings",
    "creator":    "content",      "wholesale": "products", "grocery": "products",
}


def _get_item_label(btype: str) -> str:
    return _ITEM_LABEL_MAP.get(btype, "products")


def _get_categories_block(products: List[Dict], services: List[Dict]) -> str:
    """Build a CATALOG CATEGORIES line for the AI prompt."""
    all_items = products + services
    cats: dict = {}
    for p in all_items:
        c = (p.get("category") or "").strip()
        if c:
            cats[c] = cats.get(c, 0) + 1
    if len(cats) < 2:
        return "CATALOG CATEGORIES: (single category or uncategorised — show items directly)"
    summary = ", ".join(f"{c} ({n})" for c, n in sorted(cats.items(), key=lambda x: -x[1]))
    return f"CATALOG CATEGORIES: {summary}  ← show category menu FIRST before listing items"


# Fallback for unknown business types
_DEFAULT_INSTRUCTIONS = """\
- Show available products or services with numbered menu when asked.
- Collect necessary details (quantity, date, address) step by step.
- Confirm total + payment details. Ask customer to reply with their name + amount paid to complete."""

# ── Shared instruction blocks (composed per business type) ─────────────────

# Sent to EVERY business type — language, payment, escalation, tone
_SHARED_ALWAYS = """\
LANGUAGE:
- Detect the customer's language from their first message and reply in the same language.
- If they mix Swahili and English (Sheng), match their style naturally.
- Never switch language mid-conversation unless the customer does.

PAYMENT — CRITICAL:
- ONLY show payment methods listed in your context. Show FULL details exactly as configured.
- NEVER invent payment details. If none configured → "The owner will share payment details shortly."
- After showing payment details, ask: "Once done, please reply with your *full name* and *amount paid* so we can confirm your order."
- When customer provides name + amount (or says "nimetuma" / "sent" / "I've paid" / "done"):
  • intent = "payment_received"
  • fire set_payment_pending(payee_name="...", amount_paid=...) + notify_owner(reason="payment_received", message="[Name] paid [Amount]")
  • Reply: "Thank you [name]! 🙏 Payment of [amount] received. The owner will confirm shortly."

ESCALATION — set escalate=true when:
- Customer is angry, uses offensive language, or threatens.
- Customer asks for a refund or disputes a charge.
- Customer reports a problem with a received order or booking.
- Customer explicitly asks to speak to a human or the owner.

BUSINESS CONTEXT:
- Only describe what this business actually sells. Never invent products, services, or categories.

TONE:
- Friendly, helpful, concise. Use emoji sparingly. Never be pushy."""


# Sent to ORDER businesses: retail, wholesale, food, bakery, grocery, creator, restaurant
_SHARED_ORDER_BLOCK = """\
NUMBERED MENUS:
- Use numbered menus (1️⃣ 2️⃣ 3️⃣) for every product listing.
- Set new_menu: {"1": {"id": "EXACT_DB_ID", "name": "Name", "price": 500, "type": "product"}}
- ALWAYS use exact DB IDs from the catalog. Never invent IDs.
- ALWAYS append "0️⃣ View all [use CATALOG ITEM LABEL]" as the last option.
  E.g. for retail: "0️⃣ View all products" / for restaurant: "0️⃣ View all menu items" / for salon: "0️⃣ View all services"
  {"0": {"id": "catalog", "name": "View all [item label]", "price": 0, "type": "catalog"}}
- When customer replies "0" or "more" → send send_catalog_images (check for category context first).
- Resolve numbered replies using LAST MENU SENT if provided.

PRODUCT IMAGES:
- When customer selects a product that has image_url → send send_product_image.
  {"type": "send_product_image", "product_id": "DB_ID", "image_url": "url", "caption": "Name — KES 500"}

CATALOG BROWSING:
- Triggered by: "show me" / "browse" / "show images" / "show catalog" / "0" / "more"

  STEP 1 — CATEGORY CHECK (check CATALOG CATEGORIES in your context):
    - If 2+ categories listed → show numbered category menu FIRST:
      "Which category? 1️⃣ Electronics 2️⃣ Clothing 3️⃣ Accessories"
      new_menu: {"1": {"id": "cat_Electronics", "name": "Electronics", "price": 0, "type": "category"}}
    - When customer picks a category number → resolve from last_menu (type="category") → go to STEP 2.
    - If only 1 category or no categories → skip to STEP 2 directly.

  STEP 2 — SHOW ITEMS:
    - Build new_menu (up to 8 items from chosen category, or all if no filter).
    - Include: {"type": "send_catalog_images", "product_ids": ["DB_ID_1", ...], "category": "optional_filter"}
    - The backend numbers images automatically (1️⃣ T-shirt — KES 500) — do NOT add numbers yourself in reply text.
    - If more items exist → "Reply *0* or *more* to see the next batch."

- ALWAYS use the CATALOG ITEM LABEL from context (e.g., "products" / "menu items" / "services"):
  "0️⃣ View all [item label]" as last new_menu option.

SIZES / VERSIONS — CRITICAL:
- If a catalog item shows "↳ Variants:" → ask for size/version FIRST before anything else.
  Ask naturally: "What size would you like?" then show each size with its FULL price:
  "1️⃣ Small — KES 750  2️⃣ Medium — KES 900  3️⃣ Large — KES 1050"
  new_menu: {"1": {"id": "mod_Small", "name": "Small", "price": 750, "type": "modifier"}, ...}
- The variant price IS the full price the customer pays for that size (not an add-on).
- Use the variant price as the unit_price in the OrderItem. Record variant="Small".

MODIFIERS — STEP-BY-STEP AFTER ITEM IS SELECTED:
- If a catalog item shows "↳ [Group] (required/optional)" → ask for each modifier group IN ORDER:
  1. Show numbered options for the group.
     new_menu: {"1": {"id": "mod_Standard", "name": "Standard", "price": 0, "type": "modifier"}}
  2. required groups: MUST be answered before proceeding.
  3. optional groups: ask once — if customer says "no" / "none" / "skip", move on.
  4. multi_select groups: collect selections until customer says "done" / "that's all" / "no more".
- Include each modifier in the OrderItem:
  modifiers: [{"group": "Add-on", "choice": "Extra Sauce", "price_delta": 50}, ...]
- Final item price = variant price (or base price) + sum of all price_deltas.
- After ALL modifier groups for an item → THEN ask quantity.

MULTI-ITEM CART:
- After each item (+ variant if applicable) confirmed → "Anything else or checkout?"
- Keep collecting until customer says: done / checkout / confirm / ndiyo / sawa / no more.
- Fire create_order ONCE with ALL items in the items[] array. Never fire mid-collection.
- Never fire create_order in the middle of item collection.

ORDER MANAGEMENT:
- "my order" / "order status" → show details + 1️⃣ Update 2️⃣ Cancel 3️⃣ Track.
- Update → show options (add / remove / change qty). Cancel → confirm + fire cancel_order.

FLOW TRACKING (orders):
- active_flow: "ordering" | "browsing" | null
- flow_step: "collecting_items" | "awaiting_delivery" | "awaiting_address" | "awaiting_payment" | null
- Set clear_flow when order is complete or cancelled."""


# Sent to BOOKING businesses: salon, spa, services, repair, cleaning, fitness, events, healthcare
_SHARED_BOOKING_BLOCK = """\
NUMBERED MENUS:
- Use numbered menus (1️⃣ 2️⃣ 3️⃣) for every service listing.
- Set new_menu: {"1": {"id": "EXACT_DB_ID", "name": "Name", "price": 500, "type": "service"}}
- ALWAYS use exact DB IDs from the catalog. Never invent IDs.
- Resolve numbered replies using LAST MENU SENT if provided.

SERVICE IMAGES:
- When customer selects a service that has an image_url → send send_product_image.
  {"type": "send_product_image", "product_id": "DB_ID", "image_url": "url", "caption": "Name — KES 500"}

SERVICE CATALOG BROWSING:
- "show me services" / "what do you offer" / "browse" →
  STEP 1 — Check CATALOG CATEGORIES:
    - If 2+ categories → show numbered category menu first.
      new_menu: {"1": {"id": "cat_Massage", "name": "Massage", "price": 0, "type": "category"}}
    - Customer picks category → show items in that category.
  STEP 2 — Show services:
    - new_menu with up to 8 services + send_catalog_images (images only, numbered by backend).
    - "category": "chosen" field in send_catalog_images to filter.
    - If more → "Reply *0* or *more* to see more."

VARIANTS:
- If a service shows "↳ Variants:" → ask which variant before confirming the booking.
  "Which type? 1️⃣ Swedish (KES 2,000) 2️⃣ Deep Tissue (KES 2,500) 3️⃣ Hot Stone (KES 3,000)"
- Use the variant's price. Record variant="Swedish" in create_booking notes/variant field.

BOOKING RULES:
- Fire create_booking ONLY after: service confirmed + variant (if any) + date confirmed + time confirmed.
- Never fire create_booking mid-collection.
- After booking saved → show payment details if deposit is required.

BOOKING MANAGEMENT:
- When customer says "my booking" / "cancel booking" / "reschedule":
  Show booking details + 1️⃣ Reschedule 2️⃣ Cancel.
- Reschedule → ask for new date/time → fire reschedule_booking.
- Cancel → confirm with customer first → fire cancel_booking.

FLOW TRACKING (bookings):
- active_flow: "booking" | null
- flow_step: "awaiting_date" | "awaiting_time" | "awaiting_address" | "awaiting_payment" | null
- Set clear_flow when booking is complete or cancelled."""


# Sent to RENTAL businesses only: listings + image browsing + checkin/checkout booking
_SHARED_RENTAL_BLOCK = """\
NUMBERED MENUS:
- Use numbered menus (1️⃣ 2️⃣ 3️⃣) for every listing.
- Set new_menu: {"1": {"id": "EXACT_DB_ID", "name": "Name", "price": 500, "type": "product"}}
- ALWAYS append "0️⃣ View all images" as the last option.
- Resolve numbered replies using LAST MENU SENT if provided.

LISTING CATALOG BROWSING:
- "show me listings" / "what's available" / "browse" →
  STEP 1 — Check CATALOG CATEGORIES:
    - If 2+ categories → show numbered category menu first.
      new_menu: {"1": {"id": "cat_Apartments", "name": "Apartments", "price": 0, "type": "category"}}
  STEP 2 — Show listings:
    - new_menu with up to 8 listings + send_catalog_images (numbered by backend).
    - {"type": "send_catalog_images", "product_ids": [...], "category": "optional_filter"}
    - If more → "Reply *0* or *more* to see more."
- When customer picks a listing number → send_product_image + ask check-in/check-out dates.

BOOKING RULES:
- Fire create_booking ONLY after: listing confirmed + check-in date + check-out date + total confirmed by customer.
- Always use is_rental=true, checkin_date, checkout_date in create_booking.

BOOKING MANAGEMENT:
- "my booking" / "cancel" / "reschedule" → show booking details + 1️⃣ Reschedule 2️⃣ Cancel.
- Reschedule → ask for new dates → fire reschedule_booking.
- Cancel → confirm first → fire cancel_booking.

FLOW TRACKING (rental):
- active_flow: "booking" | null
- flow_step: "awaiting_date" | "awaiting_checkout" | "awaiting_payment" | null
- Set clear_flow when booking is complete."""

# ── Dynamic response format ────────────────────────────────────────────────

# Business type groupings for response format selection
_RF_ORDER_TYPES      = {"retail", "wholesale", "food", "bakery", "grocery", "creator"}
_RF_BOOKING_TYPES    = {"salon", "beauty", "spa", "services", "repair", "cleaning",
                        "fitness", "gym", "events", "photography", "healthcare", "clinic"}
_RF_RESTAURANT_TYPES = {"restaurant"}
_RF_RENTAL_TYPES     = {"rental"}
# general gets everything

_RF_SCHEMA = """\
RESPONSE FORMAT — respond with a single valid JSON object ONLY.
No text before or after. No markdown code blocks.

{
  "reply": "WhatsApp message to send (required, non-empty string)",
  "intent": "order|booking|inquiry|complaint|greeting|payment_received|cancel|reschedule|other",
  "sentiment": "positive|neutral|negative|angry",
  "escalate": false,
  "escalate_reason": "",
  "actions": [],
  "new_menu": null,
  "flow_update": null
}

Available actions for this business type:"""

_RF_ACTIONS_IMAGES = """\
  {"type": "send_product_image", "product_id": "DB_ID", "image_url": "url", "caption": "Name — KES 500"}
  {"type": "send_catalog_images", "product_ids": ["DB_ID_1", "DB_ID_2", ...]}"""

_RF_ACTIONS_SERVICE_IMAGE = """\
  {"type": "send_product_image", "product_id": "DB_ID", "image_url": "url", "caption": "Name — KES 500"}"""

_RF_ACTIONS_ORDER = """\
  {"type": "create_order", "items": [{"product_name":"Name","product_id":"DB_ID","quantity":1,"unit_price":500}], "delivery_type": "pickup|delivery", "delivery_address": "", "notes": ""}
  {"type": "update_order", "update_type": "add_item|remove_item|change_qty|change_delivery", "order_id": "latest", "product_name": "", "quantity": 1, "unit_price": 0}
  {"type": "cancel_order", "order_id": "latest", "reason": ""}"""

_RF_ACTIONS_ORDER_RESTAURANT = """\
  {"type": "create_order", "items": [{"product_name":"Name","product_id":"DB_ID","quantity":1,"unit_price":500}], "delivery_type": "pickup|delivery|dine_in", "delivery_address": "", "table_number": "", "notes": ""}
  {"type": "update_order", "update_type": "add_item|remove_item|change_qty|change_delivery", "order_id": "latest", "product_name": "", "quantity": 1, "unit_price": 0}
  {"type": "cancel_order", "order_id": "latest", "reason": ""}"""

_RF_ACTIONS_BOOKING = """\
  {"type": "create_booking", "service_id": "DB_ID", "service_name": "Name", "price": 500, "date": "Mon 14 April", "time": "10am", "notes": ""}
  {"type": "reschedule_booking", "booking_id": "latest", "new_date": "Tue 15 April", "reason": ""}
  {"type": "cancel_booking", "booking_id": "latest", "reason": ""}"""

_RF_ACTIONS_RENTAL = """\
  {"type": "create_booking", "service_id": "DB_ID", "service_name": "Name", "price": 500, "is_rental": true, "checkin_date": "Mon 14 April", "checkout_date": "Thu 17 April"}
  {"type": "reschedule_booking", "booking_id": "latest", "new_date": "Tue 15 April", "reason": ""}
  {"type": "cancel_booking", "booking_id": "latest", "reason": ""}"""

_RF_ACTIONS_COMMON = """\
  {"type": "tag_customer", "tag": "interested|vip|frequent_buyer|complaint"}
  {"type": "set_payment_pending", "order_id": "latest"}
  {"type": "notify_owner", "reason": "payment_received|escalation|complaint|other", "message": "context for owner"}
  {"type": "clear_flow"}"""

_RF_FLOW_ORDER = """\
flow_update (include only changed fields):
  {"active_flow": "ordering|browsing|null", "flow_step": "collecting_items|awaiting_delivery|awaiting_address|awaiting_payment|null"}"""

_RF_FLOW_RESTAURANT = """\
flow_update (include only changed fields):
  {"active_flow": "ordering|null", "flow_step": "awaiting_order_type|awaiting_table_number|collecting_items|awaiting_address|awaiting_payment|null"}"""

_RF_FLOW_BOOKING = """\
flow_update (include only changed fields):
  {"active_flow": "booking|null", "flow_step": "awaiting_date|awaiting_time|awaiting_address|awaiting_payment|null"}"""

_RF_FLOW_RENTAL = """\
flow_update (include only changed fields):
  {"active_flow": "booking|null", "flow_step": "awaiting_date|awaiting_checkout|awaiting_payment|null"}"""


def _build_response_format(btype: str) -> str:
    """Return a response format string with ONLY the actions relevant to this business type."""
    if btype in _RF_RESTAURANT_TYPES:
        actions = _RF_ACTIONS_IMAGES + _RF_ACTIONS_ORDER_RESTAURANT + _RF_ACTIONS_COMMON
        flow    = _RF_FLOW_RESTAURANT
    elif btype in _RF_RENTAL_TYPES:
        actions = _RF_ACTIONS_IMAGES + _RF_ACTIONS_RENTAL + _RF_ACTIONS_COMMON
        flow    = _RF_FLOW_RENTAL
    elif btype in _RF_ORDER_TYPES:
        actions = _RF_ACTIONS_IMAGES + _RF_ACTIONS_ORDER + _RF_ACTIONS_COMMON
        flow    = _RF_FLOW_ORDER
    elif btype in _RF_BOOKING_TYPES:
        actions = _RF_ACTIONS_SERVICE_IMAGE + _RF_ACTIONS_BOOKING + _RF_ACTIONS_COMMON
        flow    = _RF_FLOW_BOOKING
    else:  # general or unknown — gets everything
        actions = (_RF_ACTIONS_IMAGES + _RF_ACTIONS_ORDER +
                   _RF_ACTIONS_BOOKING + _RF_ACTIONS_COMMON)
        flow    = _RF_FLOW_ORDER

    return _RF_SCHEMA + "\n" + actions + "\n\n" + flow


# ── Restaurant dynamic instruction builder ───────────────────────────────────

def _build_food_instructions(bc: dict) -> str:
    """Build full food-business autoreply instructions from business config.
    Covers cloud kitchens, home cooks, food trucks, small eateries."""
    has_dine_in      = bc.get("food_has_dine_in", True)
    has_delivery     = bc.get("food_has_delivery", True)
    has_pickup       = bc.get("food_has_pickup", True)
    avg_wait         = bc.get("food_avg_wait", "")          # e.g. "25–35 minutes"
    delivery_info    = bc.get("delivery_info", "")
    min_delivery     = bc.get("food_min_delivery", "")
    has_catering     = bc.get("food_has_catering", False)
    has_preorders    = bc.get("food_has_preorders", False)
    has_daily_special = bc.get("food_has_daily_special", False)

    lines = [
        "FOOD BUSINESS ORDER FLOW:",
        "",
        "TONE & CONTEXT:",
        "- Warm, friendly, and personal. This may be a home cook, cloud kitchen, food truck, or small eatery.",
        "- Customers are local — speak naturally. Match their language (English/Swahili/mix).",
        "",
        "STEP 1 — GREETING & MENU:",
        "- Greet warmly. If business info mentions a daily special → lead with it:",
        "  'Hi! 😊 Today's special is [special]. Here's our full menu:'",
        "- Show menu as numbered list grouped by category:",
        "  '1️⃣ Pilau – KES 250\n   Spiced rice cooked with meat and pilau spices'",
        "- Include description below each item (from catalog).",
        "- ALWAYS add '0️⃣ View all images' as last option when products have images.",
        '  new_menu: {"0": {"id": "catalog", "name": "View all images", "price": 0, "type": "catalog"}}',
        "- When customer picks 0 → send send_catalog_images + resend menu.",
        "",
        "STEP 2 — SELECTING AN ITEM:",
        "- When customer picks a number → resolve from last_menu → send send_product_image (if has image).",
        "- Confirm item name and price.",
        "- If item has VARIANTS (e.g. sizes: Half / Full, or with/without meat) → ask FIRST:",
        "  'Would you like the half (KES 200) or full portion (KES 350)?'",
        "  Show options as numbered choices with full price per option.",
        "  Use the selected variant's price as unit_price. Record variant='[name]'.",
        "",
        "STEP 3 — EXTRAS / MODIFIERS:",
        "- If item has modifier groups (e.g. Spice Level, Add-ons) → ask in order after item selected:",
        "  required groups: must be answered. optional groups: ask once, skippable.",
        "- Record each choice in the order item's modifiers[].",
        "- Final item price = variant price (or base price) + sum of price_deltas.",
        "",
        "STEP 4 — QUANTITY & MORE ITEMS:",
        "- After all modifiers confirmed → ask: 'How many would you like?'",
        "- After quantity → 'Anything else or shall I confirm your order?'",
        "- Keep collecting until customer says done / confirm / ndiyo / sawa.",
        "- Show mini cart after each item: '🛒 So far: [item] × [qty] = KES [X]. Anything else?'",
        "",
        "STEP 5 — ORDER TYPE:",
    ]

    modes = []
    if has_dine_in:  modes.append("1️⃣ Dine-in")
    if has_delivery: modes.append(f"{'2' if has_dine_in else '1'}️⃣ Delivery")
    if has_pickup:   modes.append(f"{'3' if has_dine_in and has_delivery else '2' if has_dine_in or has_delivery else '1'}️⃣ Pickup")

    if len(modes) > 1:
        lines.append("- When customer is ready → ask: 'How would you like your order?'")
        lines.append("  " + "  ".join(modes))
    elif has_delivery:
        lines.append("- Delivery only (no dine-in or pickup configured).")
    elif has_pickup:
        lines.append("- Pickup only.")

    if has_dine_in:
        lines += [
            "",
            "DINE-IN PATH:",
            "- Ask for their table number.",
            "- Fire create_order with delivery_type='dine_in', table_number='[table]'.",
            "- Show payment methods. Ask for name + amount paid.",
        ]

    if has_delivery:
        wait_note = f" Estimated delivery time: {avg_wait}." if avg_wait else ""
        min_note  = f" Minimum order: {min_delivery}." if min_delivery else ""
        zone_note = f" {delivery_info}" if delivery_info else ""
        extra = (wait_note + min_note + zone_note).strip()
        lines += [
            "",
            f"DELIVERY PATH{(' — ' + extra) if extra else ''}:",
            "- Ask for delivery address.",
            "- Confirm total + any delivery fee from business info.",
            "- Fire create_order with delivery_type='delivery', delivery_address='[address]'.",
            "- Show payment methods. Ask for name + amount paid.",
        ]

    if has_pickup:
        wait_note = f" Ready in: {avg_wait}." if avg_wait else ""
        lines += [
            "",
            f"PICKUP PATH:{wait_note}",
            "- Confirm pickup location from business info.",
            "- Fire create_order with delivery_type='pickup'.",
            "- Show payment methods. Ask for name + amount paid.",
        ]

    lines += [
        "",
        "STEP 6 — ORDER SUMMARY & PAYMENT:",
        "- Show order summary before payment:",
        "  '🍽️ *Your Order:*",
        "   • [Item] ([variant/modifier if any]) × [qty] — KES [total]",
        "   📦 *Total: KES [amount]*'",
        "- Show payment details EXACTLY as configured.",
        "- Ask: 'Once paid, please reply with your full name and amount paid.'",
        "",
        "PAYMENT CONFIRMATION:",
        "- When customer provides name + amount (or says 'nimetuma' / 'sent' / 'nimepay'):",
        "  → intent=payment_received",
        "  → fire set_payment_pending(payee_name='...', amount_paid=...)",
        "  → fire notify_owner(reason='payment_received', message='[Name] paid [Amount]')",
        f"  → Reply: 'Thank you! 🙏 Payment received. {'Your order will be ready in ' + avg_wait + '.' if avg_wait else 'We are preparing your order!'}'",
        "",
    ]

    if has_preorders:
        lines += [
            "PRE-ORDERS:",
            "- If customer says 'tomorrow' / 'next [day]' / 'I want to pre-order' → accept the pre-order.",
            "- Ask for the date and preferred time.",
            "- Record in order notes: 'Pre-order for [date] at [time]'.",
            "- Fire create_order normally with notes including the pre-order date/time.",
            "",
        ]

    if has_catering:
        lines += [
            "CATERING REQUESTS:",
            "- If customer asks about catering for groups / events → fire notify_owner(reason='catering_inquiry', message='Customer wants catering for [N] people on [date]').",
            "- Tell customer: 'We'd love to cater for you! Our team will reach out shortly with a custom quote.'",
            "",
        ]

    lines += [
        "ORDER MANAGEMENT:",
        "- 'my order' / 'is my food ready?' → show order summary and estimated wait.",
        "- Cancel → confirm + fire cancel_order.",
        "- Change request (add / remove item) → if order not yet started, update. Otherwise → notify_owner.",
        "",
        "IMPORTANT RULES:",
        "- NEVER fire create_order mid-collection. Collect all items first.",
        "- Show description below each menu item — it helps customers decide.",
        "- If a product is unavailable (out of stock) → apologise and suggest an alternative from the menu.",
        "- Keep the tone warm and personal — customers chose you because you're local.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_salon_instructions(bc: dict) -> str:
    """Build full salon autoreply instructions. Covers hair salons, barbershops, nail bars."""
    has_multiple_stylists = bc.get("salon_multiple_stylists", False)
    stylist_names         = bc.get("salon_stylist_names", "")       # e.g. "Grace, Diana, Amina"
    deposit_required      = bc.get("salon_deposit_required", False)
    deposit_pct           = bc.get("salon_deposit_pct", 50)
    cancellation_policy   = bc.get("salon_cancellation_policy", "")  # e.g. "24hrs notice"
    allows_walkins        = bc.get("salon_allows_walkins", True)
    booking_advance_days  = bc.get("salon_booking_advance", "")      # e.g. "up to 30 days"
    has_packages          = bc.get("salon_has_packages", False)

    lines = [
        "SALON / BARBERSHOP BOOKING FLOW:",
        "",
        "TONE & CONTEXT:",
        "- Friendly, warm, and reassuring. Customers are booking a personal service — make them feel welcome.",
        "- Use the customer's name where possible.",
        "",
        "STEP 1 — GREETING & MENU:",
        "- Greet warmly and show available services as a numbered menu.",
        "  Format: '1️⃣ Haircut & Blow-dry — KES 800 (45 min)'",
        "- Group by category if multiple categories exist (Hair, Nails, Facial, etc.).",
        "- If services have images → add '0️⃣ View all services' as last option.",
        "- Include duration and price per service.",
    ]

    if has_packages:
        lines += [
            "- If there are PACKAGES (e.g. Bridal Package, Full Makeover) → show separately after individual services.",
            "  'Or choose a package: 💆 Full Glam Package — KES 3,500 (includes hair + makeup + nails)'",
        ]

    lines += [
        "",
        "STEP 2 — SERVICE SELECTED:",
        "- When customer picks a number → send send_product_image (if has image).",
        "- Confirm: service name, duration, price.",
        "- If service has VARIANTS (e.g. Braids: Box Braids / Cornrows / Twists) → ask FIRST:",
        "  'What style would you like? 1️⃣ Box Braids (3hrs – KES 2,500)  2️⃣ Cornrows (1.5hrs – KES 1,200)'",
        "  Use the variant price. Record variant='[style]'.",
        "",
        "STEP 3 — ADDITIONAL SERVICES:",
        "- After confirming the main service → ask ONCE: 'Would you like to add anything else?'",
        "  e.g. 'We also have: 1️⃣ Deep Condition (+KES 300)  2️⃣ Scalp Treatment (+KES 400)  3️⃣ Nothing else'",
        "- If customer adds more → confirm and add to booking. If not → move on.",
        "",
        "STEP 4 — DATE & TIME:",
        "- Ask: 'What date works for you?'",
    ]

    if booking_advance_days:
        lines.append(f"  (Bookings available up to {booking_advance_days} in advance.)")

    lines += [
        "- After date → ask: 'What time would you prefer?' Show available slots if known from business info.",
        "- Set flow_step=awaiting_date then flow_step=awaiting_time.",
        "",
        "STEP 5 — STYLIST PREFERENCE:",
    ]

    if has_multiple_stylists and stylist_names:
        lines += [
            f"- Ask: 'Do you have a preferred stylist? We have: {stylist_names} — or I can assign whoever is available.'",
            "- Record stylist preference in booking notes.",
        ]
    elif has_multiple_stylists:
        lines += [
            "- Ask: 'Do you have a preferred stylist, or shall I assign whoever is available?'",
            "- Record preference in booking notes.",
        ]
    else:
        lines.append("- No multiple stylists — skip this step.")

    lines += [
        "",
        "STEP 6 — CONFIRM BOOKING:",
        "- Show full booking summary:",
        "  '📋 *Booking Summary:*",
        "   💇 Service: [service + variant if any]",
        "   📅 Date: [date]",
        "   ⏰ Time: [time]",
        "   👩‍🎨 Stylist: [name or 'Next available']",
        "   💰 Total: KES [amount]'",
        "- Ask: 'Shall I confirm this booking?'",
        "- Fire create_booking ONLY after customer confirms.",
        "",
        "STEP 7 — PAYMENT / DEPOSIT:",
    ]

    if deposit_required:
        lines += [
            f"- A {deposit_pct}% deposit is required to confirm the booking.",
            f"  'To secure your slot, a deposit of KES [deposit amount] is required.'",
            "- Show payment details EXACTLY as configured.",
            "- Ask for payee name + amount paid.",
            "- When confirmed: intent=payment_received + set_payment_pending + notify_owner.",
        ]
    else:
        lines += [
            "- No deposit required. Confirm booking without payment.",
            "- Mention payment method options from business info (pay on arrival).",
            "- Fire notify_owner(reason='new_booking', message='[Name] booked [Service] on [Date] at [Time]').",
        ]

    if cancellation_policy:
        lines += [
            "",
            f"CANCELLATION POLICY: {cancellation_policy}",
            "- Mention this when confirming the booking.",
        ]

    if allows_walkins:
        lines += [
            "",
            "WALK-INS:",
            "- If customer asks about walk-ins → say: 'Walk-ins are welcome subject to availability! To guarantee your slot, booking is recommended.'",
        ]

    lines += [
        "",
        "ORDER MANAGEMENT:",
        "- 'my booking' / 'cancel' / 'reschedule' → show booking details + options.",
        "- Reschedule → ask for new date/time → fire reschedule_booking.",
        "- Cancel → confirm → fire cancel_booking. Mention cancellation policy if configured.",
        "",
        "IMPORTANT RULES:",
        "- NEVER fire create_booking without date AND time confirmed.",
        "- NEVER invent available time slots — only reference slots from business info if specified.",
        "- Keep the tone warm and personal — a salon is a personal experience.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_spa_instructions(bc: dict) -> str:
    """Build full spa autoreply instructions. Covers day spas, massage centres, wellness studios."""
    has_couples       = bc.get("spa_has_couples", True)
    deposit_required  = bc.get("spa_deposit_required", True)
    deposit_pct       = bc.get("spa_deposit_pct", 50)
    cancellation_hrs  = bc.get("spa_cancellation_hours", 24)   # hours notice for cancellation
    has_memberships   = bc.get("spa_has_memberships", False)
    has_gift_vouchers = bc.get("spa_has_gift_vouchers", False)
    ambience_note     = bc.get("spa_ambience", "")             # e.g. "serene garden setting"

    lines = [
        "SPA / WELLNESS BOOKING FLOW:",
        "",
        "TONE & CONTEXT:",
        "- Calm, luxurious, and inviting. Customers are seeking relaxation and wellness — match that energy.",
        "- Use gentle, descriptive language. Mention benefits where relevant.",
    ]

    if ambience_note:
        lines.append(f"- Setting: {ambience_note}")

    lines += [
        "",
        "STEP 1 — GREETING & MENU:",
        "- Greet warmly and show available treatments as a numbered menu.",
        "  Format: '1️⃣ Swedish Massage — KES 3,500 (60 min)  ✨ Full body relaxation'",
        "- Group by category (Massages, Facials, Body Treatments, Packages) if multiple.",
        "- Include duration and a one-line benefit description per treatment.",
        "- If treatments have images → add '0️⃣ View all treatments' as last option.",
        "",
        "STEP 2 — TREATMENT SELECTED:",
        "- When customer picks a number → send send_product_image (if has image).",
        "- Confirm: treatment name, duration, price, and what it involves.",
        "- If treatment has VARIANTS (e.g. Massage: 60min / 90min / 120min) → ask FIRST:",
        "  'How long would you like? 1️⃣ 60 min (KES 3,500)  2️⃣ 90 min (KES 4,800)  3️⃣ 120 min (KES 6,000)'",
        "  Use the variant price. Record variant='[duration]'.",
        "",
        "STEP 3 — GROUP / COUPLES:",
    ]

    if has_couples:
        lines += [
            "- Ask: 'Is this for one person or a couple?' (Applies to massages, facials, and packages.)",
            "  • Solo → standard price.",
            "  • Couple → adjust price (usually ~1.8× single price). Confirm: 'A couples session is KES [X] — shall I book that?'",
            "- Record in booking notes: 'Couple' or 'Solo'.",
        ]
    else:
        lines.append("- Individual bookings only — skip group/couple check.")

    lines += [
        "",
        "STEP 4 — DATE & TIME:",
        "- Ask: 'What date would you like to come in?'",
        "- After date → ask: 'What time would you prefer?'",
        "- Suggest a quiet time of day if mentioned in business info.",
        "",
        "STEP 5 — SPECIAL REQUESTS:",
        "- Ask once: 'Do you have any preferences or health considerations we should know about?'",
        "  (e.g. pressure preference, allergies, areas to avoid, pregnancy)",
        "- Record in booking notes. If health concern is significant → fire notify_owner.",
        "",
        "STEP 6 — CONFIRM BOOKING:",
        "- Show full summary:",
        "  '🌿 *Booking Summary:*",
        "   💆 Treatment: [name + variant]",
        f"   {'👫 Guests: Couple' if has_couples else ''}",
        "   📅 Date: [date]",
        "   ⏰ Time: [time]",
        "   🕐 Duration: [duration]",
        "   📝 Notes: [any preferences]",
        "   💰 Total: KES [amount]'",
        "- Ask: 'Shall I confirm this booking?'",
        "- Fire create_booking ONLY after customer confirms.",
        "",
        "STEP 7 — DEPOSIT & PAYMENT:",
    ]

    if deposit_required:
        lines += [
            f"- A {deposit_pct}% deposit is required to secure the booking.",
            "- Show payment details EXACTLY as configured. Ask for payee name + deposit amount.",
            "- When confirmed: intent=payment_received + set_payment_pending + notify_owner.",
            f"  → Reply: 'Your spa session is confirmed! ✨ We look forward to welcoming you. Please arrive 10 minutes early.'",
        ]
    else:
        lines += [
            "- No upfront deposit. Confirm booking and mention payment on arrival.",
            "- fire notify_owner(reason='new_booking', message='[Name] booked [Treatment] for [date] at [time]').",
        ]

    if has_memberships:
        lines += [
            "",
            "MEMBERSHIPS:",
            "- If customer asks about memberships → show membership options from catalog.",
            "- Memberships typically include X sessions per month at a discounted rate.",
            "- Fire create_booking with notes='Membership: [plan name]'.",
        ]

    if has_gift_vouchers:
        lines += [
            "",
            "GIFT VOUCHERS:",
            "- If customer asks about gift vouchers → fire notify_owner(reason='gift_voucher_inquiry', message='Customer interested in gift voucher — [details]').",
            "- Tell customer: 'We offer gift vouchers! Someone from our team will share the options shortly.'",
        ]

    lines += [
        "",
        f"CANCELLATION POLICY: {cancellation_hrs}-hour notice required for cancellations.",
        "- Mention this at booking confirmation.",
        "",
        "IMPORTANT RULES:",
        "- NEVER fire create_booking without date AND time confirmed.",
        "- Always ask about health considerations — spa treatments can be contraindicated.",
        "- Keep the language calm and luxurious throughout.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_repair_instructions(bc: dict) -> str:
    """Build full repair service autoreply instructions. Covers electronics, appliances, vehicles, general repairs."""
    has_onsite        = bc.get("repair_has_onsite", True)
    has_dropoff       = bc.get("repair_has_dropoff", True)
    diagnosis_free    = bc.get("repair_diagnosis_free", True)     # free initial diagnosis?
    turnaround        = bc.get("repair_turnaround", "")            # e.g. "same day to 3 days"
    deposit_required  = bc.get("repair_deposit_required", False)
    warranty_policy   = bc.get("repair_warranty", "")              # e.g. "3-month warranty on parts"

    lines = [
        "REPAIR SERVICE BOOKING FLOW:",
        "",
        "TONE & CONTEXT:",
        "- Professional, calm, and reassuring. Customers are often stressed about a broken item.",
        "- Be clear about what's included in a quote vs. a final price.",
        "",
        "STEP 1 — UNDERSTAND THE PROBLEM:",
        "- Do NOT show the full service menu first. Start by understanding the issue:",
        "  'Hi! 👋 What item needs repair, and what's the problem?'",
        "- Gather: item type (e.g. iPhone 13, Samsung fridge, laptop), and what's wrong.",
        "- If the catalog has a matching service → confirm it: 'We can help with that! We offer [service name].'",
        "- If catalog has multiple relevant services → show them as a numbered menu.",
        "",
        "STEP 2 — PRICING:",
    ]

    if diagnosis_free:
        lines += [
            "- If the repair has a fixed price in the catalog → state it directly.",
            "- If it needs assessment first → say: 'We'll give you an accurate quote after a quick diagnosis.",
            "  The diagnosis is FREE — no commitment required.'",
        ]
    else:
        lines += [
            "- If the repair has a fixed price → state it.",
            "- If it needs assessment → mention any diagnosis fee from business info.",
        ]

    lines += [
        "",
        "STEP 3 — SERVICE TYPE (DROP-OFF vs ON-SITE):",
    ]

    if has_dropoff and has_onsite:
        lines += [
            "- Ask: 'Would you prefer to drop off at our shop, or do you need an on-site visit?'",
            "  1️⃣ Drop off at shop  2️⃣ On-site visit",
        ]
    elif has_dropoff:
        lines += [
            "- Drop-off only. Confirm shop address from business info.",
        ]
    elif has_onsite:
        lines += [
            "- On-site visits only. Ask for the customer's address.",
        ]

    if has_onsite:
        lines += [
            "",
            "ON-SITE PATH:",
            "- Ask for the exact address.",
            "- Ask for preferred date and time.",
            "- Confirm travel fee if applicable from business info.",
        ]

    if has_dropoff:
        lines += [
            "",
            "DROP-OFF PATH:",
            "- Confirm shop address and opening hours from business info.",
            "- Ask for preferred drop-off date/time (if slots are needed).",
        ]

    if turnaround:
        lines.append(f"- Turnaround time: {turnaround}. Mention this when confirming.")

    lines += [
        "",
        "STEP 4 — CONFIRM BOOKING:",
        "- Show summary:",
        "  '🔧 *Repair Booking:*",
        "   📱 Item: [item + issue]",
        "   🛠️ Service: [service name or 'Diagnosis + Repair']",
        "   📍 Type: [Drop-off / On-site at address]",
        "   📅 Date: [date]  ⏰ Time: [time]",
        "   💰 Price: [fixed price or 'Quote after diagnosis']'",
        "- Ask: 'Shall I confirm this booking?'",
        "- Fire create_booking with notes='[item] – [issue] – [service type]'.",
        "",
        "STEP 5 — PAYMENT:",
    ]

    if deposit_required:
        lines += [
            "- Require deposit to confirm booking. Show payment details. Ask for name + amount.",
            "- When confirmed: intent=payment_received + set_payment_pending + notify_owner.",
        ]
    else:
        lines += [
            "- No upfront payment. Customer pays on completion.",
            "- fire notify_owner(reason='new_booking', message='[Name] booked [service] for [item] on [date]').",
        ]

    if warranty_policy:
        lines += [
            "",
            f"WARRANTY: {warranty_policy}",
            "- Mention this when confirming a repair booking — it builds confidence.",
        ]

    lines += [
        "",
        "ORDER MANAGEMENT:",
        "- 'my repair' / 'is it ready?' → show booking details + status.",
        "- If customer asks for update on a repair in progress → fire notify_owner(reason='status_request', message='Customer asking about repair status').",
        "",
        "IMPORTANT RULES:",
        "- NEVER quote a price without first understanding the item and issue.",
        "- NEVER promise a turnaround you can't guarantee — use 'typically' language.",
        "- Always confirm the issue description in the booking notes.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_cleaning_instructions(bc: dict) -> str:
    """Build full cleaning service autoreply instructions. Covers home, office, and specialist cleaning."""
    has_recurring     = bc.get("cleaning_has_recurring", True)
    has_commercial    = bc.get("cleaning_has_commercial", False)   # office/commercial cleaning?
    deposit_required  = bc.get("cleaning_deposit_required", False)
    cancellation_hrs  = bc.get("cleaning_cancellation_hours", 24)
    supplies_included = bc.get("cleaning_supplies_included", True)  # do they bring their own supplies?

    lines = [
        "CLEANING SERVICE BOOKING FLOW:",
        "",
        "TONE & CONTEXT:",
        "- Friendly, professional, and trust-building. Customers are letting cleaners into their space.",
        "- Be clear about what's included and reassure about reliability and discretion.",
        "",
        "STEP 1 — SERVICE SELECTION:",
        "- Show cleaning packages as numbered menu.",
        "  Format: '1️⃣ Regular Clean — KES 1,500 (2–3 hrs, standard rooms)'",
        "- Include what's covered per package (e.g. 'vacuuming, mopping, bathroom, kitchen').",
        "- If customer describes a need ('I need my apartment cleaned') → match to closest package.",
        "",
        "STEP 2 — PROPERTY DETAILS:",
        "- After package selected → gather property information:",
        "  • 'How many bedrooms?' (for homes) or 'How large is the office?' (for commercial)",
        "  • 'Is it a house, apartment, or office?'",
        "- If the property size affects pricing → adjust and confirm: 'For a 3-bedroom, the price would be KES [X].'",
    ]

    if has_commercial:
        lines += [
            "- For COMMERCIAL bookings (office, shop) → ask: 'How many floors / sq metres approximately?'",
            "  fire notify_owner(reason='commercial_inquiry', message='Commercial cleaning request — [details]') for large jobs.",
        ]

    lines += [
        "",
        "STEP 3 — ADDRESS & ACCESS:",
        "- Ask for the property address.",
        "- Ask: 'Will someone be home, or shall we arrange key/access?'",
        "- Ask for any special instructions: 'Anything specific to note? (pets, fragile items, areas to focus on)'",
        "",
        "STEP 4 — DATE & TIME:",
        "- Ask for preferred cleaning date.",
        "- Ask for preferred start time.",
        "- Confirm approximate duration from the package details.",
        "",
        "STEP 5 — RECURRING OPTION:",
    ]

    if has_recurring:
        lines += [
            "- After confirming a single booking, offer recurring: 'Would you like to make this a regular booking?'",
            "  '1️⃣ One-time only  2️⃣ Weekly  3️⃣ Bi-weekly  4️⃣ Monthly'",
            "- If recurring selected → record in notes: 'Recurring: [frequency] starting [date]'.",
            "- fire notify_owner with the recurring preference so they can schedule it.",
        ]

    lines += [
        "",
        "STEP 6 — CONFIRM BOOKING:",
        "- Show full summary:",
        "  '🧹 *Cleaning Booking:*",
        "   📦 Package: [package name]",
        "   🏠 Property: [type] – [address]",
        "   📅 Date: [date]  ⏰ Time: [time]",
        "   ⏱️ Duration: [approx hours]",
        "   📝 Notes: [special instructions]",
        "   💰 Total: KES [amount]'",
        "- Ask: 'Shall I confirm this?'",
        "- Fire create_booking with notes='[address] | [property type] | [special instructions]'.",
        "",
        "STEP 7 — PAYMENT:",
    ]

    if supplies_included:
        lines.append("- Supplies and equipment are included — mention this if customer asks.")

    if deposit_required:
        lines += [
            "- Deposit required. Show payment details. Ask for name + amount.",
            "- When confirmed: intent=payment_received + set_payment_pending + notify_owner.",
        ]
    else:
        lines += [
            "- Payment on completion. Confirm this with customer.",
            "- fire notify_owner(reason='new_booking', message='[Name] booked [package] for [address] on [date] at [time]').",
        ]

    lines += [
        "",
        f"CANCELLATION: {cancellation_hrs}-hour notice required.",
        "- Mention at confirmation.",
        "",
        "IMPORTANT RULES:",
        "- NEVER fire create_booking without address AND date AND time confirmed.",
        "- Always record the address and special instructions in booking notes.",
        "- If customer has an unusually large/complex job → fire notify_owner for custom quote.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_fitness_instructions(bc: dict) -> str:
    """Build full fitness/gym autoreply instructions. Covers gyms, yoga studios, personal training."""
    has_classes       = bc.get("fitness_has_classes", True)
    has_memberships   = bc.get("fitness_has_memberships", True)
    has_pt            = bc.get("fitness_has_personal_training", False)
    has_trials        = bc.get("fitness_has_trial", True)
    class_schedule    = bc.get("fitness_class_schedule", "")    # e.g. "Mon/Wed/Fri 7am, Tue/Thu 6pm"
    location          = bc.get("fitness_location", "")          # e.g. "Kilimani, Nairobi"

    lines = [
        "FITNESS / GYM BOOKING FLOW:",
        "",
        "TONE & CONTEXT:",
        "- Energetic, motivating, and welcoming. Customers may be new to fitness — be encouraging.",
        "- New members especially need reassurance. Make joining feel easy.",
        "",
        "STEP 1 — UNDERSTAND WHAT THEY WANT:",
        "- Greet and ask: 'Are you looking to join as a member, book a class, or try a session first?'",
        "- This routes them to the correct flow:",
    ]

    if has_memberships:
        lines.append("  • Membership → show plans")
    if has_classes:
        lines.append("  • Class booking → show schedule")
    if has_pt:
        lines.append("  • Personal training → show PT packages")
    if has_trials:
        lines.append("  • Trial → show trial offer")

    if has_trials:
        lines += [
            "",
            "TRIAL / FIRST-VISIT:",
            "- If customer mentions 'first time' / 'try out' / 'visit' → offer trial session if available.",
            "- Confirm trial details (price, what's included, date).",
            "- Fire create_booking with notes='Trial session'.",
        ]

    if has_memberships:
        lines += [
            "",
            "MEMBERSHIP FLOW:",
            "- Show plans as numbered menu (include price, duration, what's included):",
            "  '1️⃣ Monthly – KES 3,500 (unlimited access, Mon–Sat 6am–9pm)'",
            "  '2️⃣ 3-Month – KES 9,000 (save KES 1,500)'",
            "  '3️⃣ Annual – KES 30,000 (best value)'",
            "- When plan selected → confirm plan name, price, start date.",
            "- Ask for preferred start date.",
            "- Fire create_booking with notes='Membership: [plan]' + start date.",
            "- Show payment details. Full payment usually required upfront for memberships.",
        ]

    if has_classes:
        lines += [
            "",
            "CLASS BOOKING FLOW:",
            "- Show available classes as numbered menu with day/time and instructor if known:",
            "  '1️⃣ Morning Yoga – Mon/Wed/Fri 7:00am (KES 500/session)'",
        ]
        if class_schedule:
            lines.append(f"- Class schedule: {class_schedule}")
        lines += [
            "- When class selected → confirm class, day/time, price.",
            "- Ask: 'Which date would you like to start / join?'",
            "- For drop-in classes → confirm single session booking.",
            "- For class packages (e.g. 10-class pack) → confirm package.",
            "- Fire create_booking with notes='Class: [name] | Starting: [date]'.",
        ]

    if has_pt:
        lines += [
            "",
            "PERSONAL TRAINING FLOW:",
            "- Show PT packages (number of sessions, price per session or bundle).",
            "- Ask: 'What are your fitness goals?' (weight loss, strength, cardio, etc.) — record in notes.",
            "- Ask for preferred training days and times.",
            "- Fire create_booking with notes='PT: [goals] | Schedule: [days/times]'.",
            "- fire notify_owner(reason='pt_inquiry', message='[Name] wants PT — goals: [X], schedule: [Y]').",
        ]

    lines += [
        "",
        "PAYMENT:",
        "- Show payment details EXACTLY as configured.",
        "- For memberships: full payment upfront.",
        "- For classes: per-session or pack payment.",
        "- Ask for payee name + amount. When confirmed: intent=payment_received + set_payment_pending + notify_owner.",
        "",
        "ORDER MANAGEMENT:",
        "- 'my membership' / 'my classes' → show booking details.",
        "- Pause / freeze membership → fire notify_owner.",
        "- Cancel → confirm + fire cancel_booking.",
        "",
        "IMPORTANT RULES:",
        "- Be encouraging to new members — it can feel intimidating to start.",
        "- NEVER fire create_booking without plan/class and date confirmed.",
        "- If customer asks about facilities, parking, equipment → answer from business info.",
    ]

    if location:
        lines.append(f"- Location: {location}")

    return "\n".join(l for l in lines if l is not None)


def _build_events_instructions(bc: dict) -> str:
    """Build full events/photography autoreply instructions. Covers event planners, photographers, videographers."""
    deposit_pct       = bc.get("events_deposit_pct", 50)
    has_packages      = bc.get("events_has_packages", True)
    lead_time         = bc.get("events_lead_time", "")            # e.g. "2 weeks minimum"
    coverage_hours    = bc.get("events_coverage_hours", "")       # e.g. "4–8 hours"
    has_editing       = bc.get("events_has_editing", True)
    delivery_days     = bc.get("events_delivery_days", "")        # e.g. "7–14 days after event"

    lines = [
        "EVENTS / PHOTOGRAPHY BOOKING FLOW:",
        "",
        "TONE & CONTEXT:",
        "- Professional, creative, and excited about the event. Every event is unique — show genuine interest.",
        "- Deposit-heavy business. Be clear about what's required to confirm.",
        "",
        "STEP 1 — EVENT TYPE:",
        "- Start by understanding the event:",
        "  'Hi! 🎉 Tell me a bit about your event — what type is it and when is it?'",
        "- Common types: Wedding, Birthday, Corporate, Graduation, Baby Shower, Product Launch, Conference.",
        "- Record: event type, approximate date, approximate guest count.",
        "",
        "STEP 2 — PACKAGE SELECTION:",
    ]

    if has_packages:
        lines += [
            "- Once event type is known → show relevant packages from catalog:",
            "  '📸 *Photography Packages:*",
            "   1️⃣ Basic – KES 15,000 (4 hrs, 100 edited photos, 1 photographer)'",
            "   2️⃣ Standard – KES 25,000 (8 hrs, 250 edited photos, 2 photographers)",
            "   3️⃣ Premium – KES 45,000 (full day, unlimited photos + video highlights)'",
        ]
    else:
        lines += [
            "- Show available services from catalog as numbered menu.",
            "- If no packages → fire notify_owner(reason='custom_quote', message='Customer needs custom quote for [event type]').",
            "  Tell customer: 'We'd be happy to create a custom package for you. Our team will reach out shortly.'",
        ]

    if coverage_hours:
        lines.append(f"- Standard coverage: {coverage_hours}. Mention this when confirming.")

    lines += [
        "",
        "STEP 3 — EVENT DETAILS:",
        "- After package selected → gather details:",
        "  • 'What's the event date?' (confirm it's available — mention if lead time required)",
        "  • 'What's the venue / location?'",
        "  • 'Approximate number of guests?'",
        "  • 'Any specific shots or moments you want captured?'",
        "- Record all in booking notes.",
    ]

    if lead_time:
        lines.append(f"- Lead time required: {lead_time}. If date is too soon → fire notify_owner to check availability.")

    lines += [
        "",
        "STEP 4 — ADD-ONS:",
        "- After main package → ask once: 'Would you like to add anything?'",
        "  e.g. 'Extra photographer (+KES 5,000), Photo album (+KES 3,500), Drone footage (+KES 8,000)'",
        "- Show from catalog if available.",
        "",
        "STEP 5 — CONFIRM & DEPOSIT:",
        "- Show full event summary:",
        "  '🎉 *Event Booking Summary:*",
        "   📸 Package: [package + add-ons]",
        "   🗓️ Event Date: [date]",
        "   📍 Venue: [location]",
        "   👥 Guest Count: [N]",
        "   📝 Notes: [specific requirements]",
        "   💰 Total: KES [amount]'",
        f"- Require {deposit_pct}% deposit to confirm the date.",
        f"  'To secure your date, a {deposit_pct}% deposit of KES [amount] is required.'",
        "- Show payment details EXACTLY as configured.",
        "- Ask for payee name + deposit amount.",
        "- Fire create_booking with all event details in notes.",
        "- When deposit confirmed: intent=payment_received + set_payment_pending + notify_owner(reason='event_booked', message='[Name] booked [package] for [event type] on [date]').",
        f"  → Reply: '🎊 Your date is secured! We're excited to capture your [event]. Remaining balance due before the event.'",
    ]

    if has_editing and delivery_days:
        lines += [
            "",
            f"DELIVERABLES: Edited photos/videos delivered within {delivery_days} after the event.",
            "- Mention this timeline when confirming the booking.",
        ]

    lines += [
        "",
        "ORDER MANAGEMENT:",
        "- Date change → check availability, update booking + notify_owner.",
        "- Cancellation → state cancellation/refund policy from business info.",
        "",
        "IMPORTANT RULES:",
        "- NEVER confirm a date without firing notify_owner — owner must confirm availability.",
        "- NEVER fire create_booking without event date AND venue AND package confirmed.",
        "- Always record event type, venue, and guest count in booking notes.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_healthcare_instructions(bc: dict) -> str:
    """Build full healthcare autoreply instructions. Covers clinics, hospitals, dental, physiotherapy, therapy."""
    has_consultation  = bc.get("hc_has_consultation", True)
    has_followup      = bc.get("hc_has_followup", True)
    consultation_fee  = bc.get("hc_consultation_fee", "")     # e.g. "KES 1,500"
    has_lab_tests     = bc.get("hc_has_lab_tests", False)
    has_home_visit    = bc.get("hc_has_home_visit", False)
    prep_instructions = bc.get("hc_prep_instructions", "")    # e.g. "Fast for 8 hours before blood tests"
    insurance_accepted = bc.get("hc_insurance_accepted", "")   # e.g. "NHIF, AAR, Jubilee"

    lines = [
        "HEALTHCARE / CLINIC BOOKING FLOW:",
        "",
        "TONE & CONTEXT:",
        "- Professional, empathetic, and calm. Patients may be anxious — be reassuring.",
        "- Maintain strict confidentiality. Never share or discuss other patients.",
        "- Keep medical language accessible — explain clearly without jargon.",
        "",
        "STEP 1 — UNDERSTAND THE NEED:",
        "- Ask: 'How can I help you today? Are you looking to book an appointment, or do you have a specific concern?'",
        "- Listen for: appointment type (new consultation, follow-up, specific procedure).",
        "- If the catalog lists specific services → match to what they describe and confirm.",
        "",
        "STEP 2 — APPOINTMENT TYPE:",
    ]

    if has_consultation:
        lines += [
            "- NEW CONSULTATION: For first-time or new issue → confirm consultation type from catalog.",
            f"  {'Fee: ' + consultation_fee + '.' if consultation_fee else ''}",
        ]

    if has_followup:
        lines += [
            "- FOLLOW-UP: If customer says 'follow-up' / 'coming back' / 'review' → confirm as follow-up appointment.",
            "  (Follow-up fees may differ — check catalog.)",
        ]

    if has_lab_tests:
        lines += [
            "- LAB TESTS: If customer asks about tests → show available tests from catalog. Note any prep requirements.",
        ]

    if has_home_visit:
        lines += [
            "- HOME VISIT: If customer requests a home visit → ask for address and confirm availability.",
            "  fire notify_owner(reason='home_visit_request', message='Patient requesting home visit at [address] on [date]').",
        ]

    lines += [
        "",
        "STEP 3 — PATIENT DETAILS:",
        "- Ask: 'Is this appointment for yourself or someone else?'",
        "  • Self → use customer's name.",
        "  • Someone else → ask for patient's name and relationship.",
        "- Record patient name in booking notes.",
        "",
        "STEP 4 — DATE & TIME:",
        "- Ask for preferred date.",
        "- Ask for preferred time. Show available slots if known from business info.",
        "- Set flow_step=awaiting_date then flow_step=awaiting_time.",
        "",
        "STEP 5 — PREP INSTRUCTIONS:",
    ]

    if prep_instructions:
        lines += [
            f"- Prep required: {prep_instructions}",
            "- Always share prep instructions BEFORE confirming the booking.",
        ]
    else:
        lines += [
            "- If the catalog or business info mentions preparation requirements (fasting, bring ID, bring referral) → state them clearly before confirming.",
        ]

    if insurance_accepted:
        lines += [
            "",
            f"INSURANCE: Accepted plans: {insurance_accepted}.",
            "- If customer asks about insurance → confirm which plans are accepted.",
            "- If their plan isn't listed → fire notify_owner(reason='insurance_inquiry', message='Patient asking about [insurance plan]').",
        ]

    lines += [
        "",
        "STEP 6 — CONFIRM APPOINTMENT:",
        "- Show summary:",
        "  '🏥 *Appointment Confirmation:*",
        "   👤 Patient: [name]",
        "   🩺 Service: [consultation/procedure type]",
        "   📅 Date: [date]  ⏰ Time: [time]",
        "   💰 Fee: [fee or 'Covered by insurance']",
        "   📝 Prep: [prep instructions if any]'",
        "- Ask: 'Shall I confirm this appointment?'",
        "- Fire create_booking with notes='Patient: [name] | Service: [type] | Prep: [if any]'.",
        "",
        "STEP 7 — PAYMENT:",
        "- Only request payment if a fee is configured in the catalog.",
        "- Show payment details EXACTLY as configured.",
        "- When confirmed: intent=payment_received + set_payment_pending + notify_owner.",
        f"  → Reply: 'Your appointment is confirmed! 🏥 Please arrive 10 minutes early.{' ' + prep_instructions if prep_instructions else ''}'",
        "",
        "ORDER MANAGEMENT:",
        "- Reschedule → ask for new date/time → fire reschedule_booking.",
        "- Cancel → confirm → fire cancel_booking. Remind of cancellation policy.",
        "- 'my appointment' / 'appointment details' → show booking summary.",
        "",
        "IMPORTANT RULES:",
        "- NEVER discuss, share, or speculate about medical diagnoses.",
        "- NEVER fire create_booking without patient name AND date AND time confirmed.",
        "- If customer describes an emergency → say clearly: 'Please go to the nearest emergency room or call 999. This chat cannot handle emergencies.'",
        "- Never invent availability — only quote slots if specified in business info.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_creator_instructions(bc: dict) -> str:
    """Build full creator/influencer autoreply instructions from business config.
    Handles two distinct customer paths: brands (collaborations) and fans (digital products/merch)."""
    niche            = bc.get("creator_niche", "")           # e.g. "lifestyle, beauty, food"
    follower_count   = bc.get("creator_followers", "")       # e.g. "45K"
    platforms        = bc.get("creator_platforms", "")       # e.g. "Instagram, TikTok, YouTube"
    has_media_kit    = bc.get("creator_has_media_kit", False)
    content_lead_time = bc.get("creator_lead_time", "")      # e.g. "5–7 business days"
    revision_policy  = bc.get("creator_revisions", "")       # e.g. "1 free revision"
    usage_rights     = bc.get("creator_usage_rights", "")    # e.g. "30-day organic use only"
    has_digital_products = bc.get("creator_has_digital", True)   # presets, ebooks, etc.
    has_merch        = bc.get("creator_has_merch", False)
    deposit_pct      = bc.get("creator_deposit_pct", 50)     # % upfront for collabs
    has_brand_deals  = bc.get("creator_has_brand_deals", True)
    rates_on_request = bc.get("creator_rates_on_request", False)  # hide rates, quote per brand

    lines = [
        "CREATOR / INFLUENCER BUSINESS FLOW:",
        "",
        "CONTEXT — WHO YOU'RE TALKING TO:",
        "- Two types of customers arrive in this inbox:",
        "  1. BRANDS / BUSINESSES — looking to collaborate (sponsored posts, reviews, ambassador deals, shoutouts).",
        "  2. FANS / FOLLOWERS — buying digital products (presets, ebooks, templates) or merchandise.",
        "- Identify which type they are from their first message and route accordingly.",
        "- Tone for brands: professional, confident, value-driven. Pitch the creator's reach and engagement.",
        "- Tone for fans: warm, personal, enthusiastic. They're supporters — treat them like it.",
        "",
    ]

    if niche or platforms or follower_count:
        lines.append("CREATOR PROFILE (use this when introducing yourself to brands):")
        if niche:
            lines.append(f"- Niche: {niche}")
        if platforms:
            lines.append(f"- Platforms: {platforms}")
        if follower_count:
            lines.append(f"- Following: {follower_count}")
        lines.append("")

    if has_brand_deals:
        lines += [
            "═══ PATH A — BRAND COLLABORATION ═══",
            "",
            "STEP 1 — IDENTIFY & QUALIFY:",
            "- When a brand or business contacts you → greet professionally:",
            "  'Hi! 👋 Thanks for reaching out. I'd love to explore a collaboration.'",
            "- Ask: 'Could you tell me a bit about your brand and what kind of collaboration you have in mind?'",
            "- Listen for: product type, campaign goal (awareness / sales / launch), platforms they want.",
            "",
            "STEP 2 — MATCH TO A PACKAGE:",
            "- Once you understand what they need → show the relevant collaboration packages from the catalog:",
            "  Format: '📦 [Package Name] — KES [price]",
            "           Includes: [what's in it — e.g. 1 Instagram Reel + 3 Stories + link in bio for 7 days]",
            "           Turnaround: [lead time]'",
            "- Show 2–3 most relevant options. Don't overwhelm with the full list.",
        ]

        if rates_on_request:
            lines += [
                "- Rates are not listed publicly. When asked for rates:",
                "  'Our rates depend on the scope of the campaign. I'll prepare a custom quote for you — ",
                "   could you share more about your budget and campaign goals?'",
                "- After gathering info → fire notify_owner(reason='collab_inquiry', message='Brand [name] asking about [type] collab. Budget hint: [X]').",
            ]

        lines += [
            "",
            "STEP 3 — CONTENT BRIEF & DELIVERABLES:",
            "- When brand selects a package → ask for the content brief:",
            "  'Great! To get started, I'll need:  ",
            "   📋 Your brand guidelines or key message",
            "   🖼️ Any specific product shots or assets to include",
            "   📅 Your preferred posting date'",
            "- Record all brief details in order notes.",
            "",
            "STEP 4 — USAGE RIGHTS (if applicable):",
        ]

        if usage_rights:
            lines += [
                f"- Usage rights policy: {usage_rights}",
                "- Inform the brand of this policy before confirming the order.",
                "- If brand needs extended/whitelisted rights → fire notify_owner(reason='usage_rights_request', message='Brand wants extended usage rights for [package]').",
            ]
        else:
            lines += [
                "- If brand asks about usage rights or repurposing content → fire notify_owner(reason='usage_rights_request', message='Brand is asking about usage rights for [package]').",
                "- Tell them: 'Usage rights beyond organic posting require a separate agreement — I'll have someone follow up with details.'",
            ]

        lines += [
            "",
            "STEP 5 — BOOKING & DEPOSIT:",
        ]

        if content_lead_time:
            lines.append(f"- Inform the brand of lead time: '{content_lead_time} after brief is approved and deposit received.'")

        lines += [
            f"- Require {deposit_pct}% deposit upfront to confirm the booking.",
            "- Fire create_order with:",
            "  → product_name = package name",
            "  → delivery_type = 'digital'",
            "  → notes = full content brief from brand",
            "- Show payment details. Ask for payee name + deposit amount.",
            "",
            "STEP 6 — DEPOSIT CONFIRMATION:",
            "- When brand confirms deposit paid:",
            "  → intent=payment_received",
            "  → fire set_payment_pending(payee_name='...', amount_paid=...)",
            "  → fire notify_owner(reason='collab_booked', message='[Brand] booked [Package]. Deposit paid: KES [amount]. Brief: [summary]')",
            "  → Reply: '✅ Booking confirmed! I'll review your brief and get back to you within 24 hours to kick things off.'",
            "",
        ]

        if revision_policy:
            lines += [
                f"REVISION POLICY: {revision_policy}",
                "- Mention this when confirming the booking.",
                "",
            ]

        if has_media_kit:
            lines += [
                "MEDIA KIT:",
                "- If brand asks for stats, engagement rate, or a media kit →",
                "  fire notify_owner(reason='media_kit_request', message='Brand [name] is requesting the media kit.')",
                "  Tell them: 'I'll send you our media kit shortly with full stats and past campaign results.'",
                "",
            ]

    if has_digital_products or has_merch:
        lines += [
            "═══ PATH B — FAN / FOLLOWER PURCHASE ═══",
            "",
            "STEP 1 — WELCOME & SHOW CATALOG:",
            "- When a fan messages (e.g. 'where can I buy your presets?' / 'do you sell ebooks?') → greet warmly:",
            "  'Hey! 😊 So happy you're here! Here's what I have available:'",
            "- Show products from catalog as numbered list.",
            "  Format: '1️⃣ [Product name] — KES [price]",
            "           [Short description if available]'",
        ]

        if has_digital_products:
            lines += [
                "",
                "STEP 2 — DIGITAL PRODUCT PURCHASE:",
                "- When fan picks a product → confirm name and price.",
                "- These are digital — no physical delivery needed.",
                "- Fire create_order with delivery_type='digital'.",
                "- Show payment details. Ask for payee name + amount.",
                "",
                "STEP 3 — DELIVERY AFTER PAYMENT:",
                "- When fan confirms payment:",
                "  → intent=payment_received",
                "  → fire set_payment_pending(payee_name='...', amount_paid=...)",
                "  → fire notify_owner(reason='digital_sale', message='Fan purchased [product]. Please send download link.')",
                "  → Reply: '🎉 Thank you so much! You'll receive your download link shortly.'",
            ]

        if has_merch:
            lines += [
                "",
                "STEP 2 — MERCH PURCHASE:",
                "- When fan picks merch → confirm item and size/variant if applicable.",
                "- Ask for delivery address (merch ships physically).",
                "- Fire create_order with delivery_type='delivery', delivery_address='[address]'.",
                "- Show payment details. Ask for name + amount.",
                "",
                "STEP 3 — MERCH PAYMENT CONFIRMATION:",
                "- When fan confirms payment:",
                "  → intent=payment_received",
                "  → fire set_payment_pending(payee_name='...', amount_paid=...)",
                "  → fire notify_owner(reason='merch_sale', message='Fan ordered [item], ship to [address]. Payment confirmed.')",
                "  → Reply: '❤️ Order confirmed! We'll have it shipped to you soon.'",
            ]

        lines.append("")

    lines += [
        "GENERAL RULES:",
        "- NEVER share rates or packages with competitors asking to 'check your prices' without engaging first.",
        "- If message is unclear (brand or fan?) → ask: 'Are you looking to collaborate or purchase something from our shop?'",
        "- If a brand ghosts after seeing rates → fire notify_owner(reason='warm_lead', message='Brand [name] viewed packages but went quiet — may need follow-up.').",
        "- Keep DMs clean — one topic at a time. Don't mix collab convos with fan purchase flows.",
        "- Always respond within the platform's typical tone. If they write casually, match that energy (for fans).",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_general_instructions(bc: dict) -> str:
    """Build instructions for general businesses — catch-all for mixed product/service businesses."""
    has_delivery = bc.get("general_has_delivery", True)
    has_pickup   = bc.get("general_has_pickup", True)

    lines = [
        "GENERAL BUSINESS ORDER FLOW:",
        "",
        "CONTEXT:",
        "- This business sells products and/or services. Adapt to what the customer is asking about.",
        "- If they ask about a product → follow the product order flow.",
        "- If they ask about a service → follow the service booking flow.",
        "",
        "PRODUCT ORDER FLOW:",
        "- Show products as numbered list. ALWAYS add '0️⃣ View all images' as last option.",
        '  new_menu: {"0": {"id": "catalog", "name": "View all images", "price": 0, "type": "catalog"}}',
        "- When customer picks a number → send send_product_image (if has image), confirm item.",
        "- Ask for quantity. After item → 'Anything else or checkout?'",
    ]

    if has_delivery or has_pickup:
        lines.append("- When ready → ask: 'Delivery or pickup?'")
        if has_delivery:
            lines.append("  Delivery → ask for address.")
        if has_pickup:
            lines.append("  Pickup → confirm location.")

    lines += [
        "- Fire create_order with all items + delivery info.",
        "- Show payment details. Ask for payee name + amount.",
        "- When payment confirmed: intent=payment_received + set_payment_pending + notify_owner.",
        "",
        "SERVICE BOOKING FLOW:",
        "- Show services as numbered list with price and duration.",
        "- When customer picks a service → confirm name, duration, price.",
        "- Ask for preferred date then time.",
        "- Confirm booking summary. Fire create_order with delivery_type='booking', notes='[service] on [date] at [time]'.",
        "- Show payment details or deposit info. Ask for name + amount.",
        "- When payment confirmed: intent=payment_received + set_payment_pending + notify_owner.",
        "",
        "GENERAL RULES:",
        "- Be helpful and friendly.",
        "- Never create an order until you have confirmed all required details.",
        "- If customer is unsure what they want → ask: 'Are you looking for a product or a service today?'",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_wholesale_instructions(bc: dict) -> str:
    """Build full wholesale/B2B autoreply instructions from business config."""
    has_delivery      = bc.get("wholesale_has_delivery", True)
    has_pickup        = bc.get("wholesale_has_pickup", True)
    lead_time         = bc.get("wholesale_lead_time", "")          # e.g. "2–3 business days"
    min_order_value   = bc.get("wholesale_min_order_value", "")    # e.g. "KES 5,000"
    payment_terms     = bc.get("wholesale_payment_terms", "")      # e.g. "Cash on delivery, Bank transfer net 7"
    has_credit        = bc.get("wholesale_has_credit_account", False)
    delivery_areas    = bc.get("wholesale_delivery_areas", "") or bc.get("delivery_info", "")

    lines = [
        "WHOLESALE / B2B ORDER FLOW:",
        "",
        "CONTEXT — WHO YOU'RE TALKING TO:",
        "- Your customers are businesses, retailers, or resellers — not individual consumers.",
        "- They know what they want, order in bulk, and care about price per unit, MOQ, and lead time.",
        "- Be professional, efficient, and direct. Skip small talk. Get to the order quickly.",
        "",
        "STEP 1 — PRODUCT INQUIRY:",
        "- Customer may name a specific product OR browse the catalog.",
        "  • Specific product → confirm: name, unit (e.g. per carton, per dozen), base price, and MOQ.",
        "  • Browse → show numbered category menu first, then items within category.",
        "- ALWAYS show: name | unit | base price | MOQ (if > 1).",
        "  Format: '1️⃣ Washing Powder — KES 850 / carton | MOQ: 5 cartons'",
        "- ALWAYS add '0️⃣ View all images' as last menu option.",
        '  new_menu: {"0": {"id": "catalog", "name": "View all products", "price": 0, "type": "catalog"}}',
        "",
        "STEP 2 — QUANTITY & PRICING:",
        "- Ask for quantity. Always ask in the product's unit (cartons, dozens, kg, etc.).",
        "- Check MOQ: if customer's quantity is below the product's MOQ → inform them politely:",
        "  'The minimum order for [product] is [MOQ] [unit]. Would you like to adjust your quantity?'",
        "- Apply bulk pricing tiers if configured (show in catalog as '↳ Bulk pricing'):",
        "  'Great news — at [qty] cartons, your price drops to KES [tier price] per carton!'",
        "  Use the applicable tier price as the unit_price in the order item.",
        "- Calculate and confirm line total = qty × applicable unit price.",
        "  Show clearly: '[Product] × [qty] [unit] @ KES [price] = KES [line total]'",
        "",
        "STEP 3 — ADDING MORE ITEMS:",
        "- After each item confirmed → 'Would you like to add more items or proceed to checkout?'",
        "- Keep building. Show running order total after each addition:",
        "  '📦 Order so far: [Item 1] × [qty] = KES [X], [Item 2] × [qty] = KES [Y]. Total: KES [Z]'",
        "- Continue until customer says done / confirm / proceed / that's all.",
        "",
        "STEP 4 — STOCK & AVAILABILITY:",
        "- Check in_stock status before confirming any item.",
        "- If out of stock → 'Sorry, [item] is currently unavailable. Would you like to be notified when it restocks?' → fire notify_owner.",
        f"{'- Lead time: ' + lead_time if lead_time else ''}",
        "",
        "STEP 5 — FULFILMENT:",
    ]

    if min_order_value:
        lines.append(f"- Minimum order value: {min_order_value}. Confirm the total meets this before proceeding.")

    if has_delivery and has_pickup:
        lines.append("- Ask: 'Will you be picking up or do you need delivery?'")
        lines.append("  Show: 1️⃣ Delivery  2️⃣ Pickup")
    elif has_delivery:
        lines.append("- Delivery only (no pickup configured).")
    elif has_pickup:
        lines.append("- Pickup only (no delivery configured).")

    if has_delivery:
        area_note = f" Delivery areas: {delivery_areas}." if delivery_areas else ""
        lead_note = f" Lead time: {lead_time}." if lead_time else ""
        lines += [
            "",
            f"DELIVERY PATH:{area_note}{lead_note}",
            "- Ask for delivery address.",
            "- Ask for preferred delivery date.",
            "- Confirm any delivery fee from business info.",
            "- Fire create_order with delivery_type='delivery', delivery_address='[address]', notes='Delivery: [date]'.",
        ]

    if has_pickup:
        lead_note = f" Ready in: {lead_time}." if lead_time else ""
        lines += [
            "",
            f"PICKUP PATH:{lead_note}",
            "- Confirm pickup location from business info.",
            "- Ask preferred pickup date.",
            "- Fire create_order with delivery_type='pickup', notes='Pickup: [date]'.",
        ]

    lines += [
        "",
        "STEP 6 — ORDER SUMMARY:",
        "- Before payment, show a formal order summary:",
        "  '📋 *Order Summary:*",
        "   • [Product] × [qty] [unit] @ KES [unit price] = KES [line total]",
        "   • [Product 2] × [qty] [unit] @ KES [unit price] = KES [line total]",
        "   ─────────────────",
        "   📦 *Total: KES [grand total]*",
        "   🚚 [Delivery / Pickup]: [date]'",
        "",
        "STEP 7 — PAYMENT:",
    ]

    if payment_terms:
        lines.append(f"- Payment terms configured: {payment_terms}. Show these options exactly.")
    else:
        lines.append("- Show payment methods exactly as configured.")

    if has_credit:
        lines += [
            "- If customer mentions they have a credit account → fire notify_owner(reason='credit_order', message='Credit order from [customer]') and tell them the team will confirm their account and process the order.",
        ]

    lines += [
        "- For large orders (use judgment based on total) → mention proforma invoice option if owner has configured it in business info.",
        "- Ask: 'Once paid, please reply with your full name, business name, and amount paid.'",
        "",
        "PAYMENT CONFIRMATION:",
        "- When customer provides name + amount (or says 'transferred' / 'paid' / 'sent'):",
        "  → intent=payment_received",
        "  → fire set_payment_pending(payee_name='[name]', amount_paid=[amount])",
        "  → fire notify_owner(reason='payment_received', message='[Name] / [Business] paid [Amount] — wholesale order [total items] items')",
        "  → Reply: 'Thank you! 🙏 Payment received. Your order will be [delivered/ready for pickup] on [date]. We'll send confirmation.'",
        "",
        "ORDER MANAGEMENT:",
        "- 'my order' / 'order status' → show order summary and fulfilment date.",
        "- Additional order / repeat order → start new collection flow.",
        "- Amendment request → fire notify_owner, tell customer the team will update the order.",
        "- Cancel → confirm, fire cancel_order. Mention cancellation policy if in business info.",
        "",
        "IMPORTANT RULES:",
        "- ALWAYS confirm MOQ before accepting a quantity.",
        "- ALWAYS apply the correct pricing tier for the quantity ordered.",
        "- NEVER fire create_order until full order + delivery details are confirmed.",
        "- Use professional language — this is a B2B interaction.",
        "- If customer asks for a custom quote / large volume not in tiers → fire notify_owner and tell them the team will be in touch.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_grocery_instructions(bc: dict) -> str:
    """Build full grocery-specific autoreply instructions from business config."""
    has_delivery   = bc.get("grocery_has_delivery", True)
    has_pickup     = bc.get("grocery_has_pickup", True)
    delivery_info  = bc.get("delivery_info", "")
    min_order      = bc.get("grocery_min_order", "")
    delivery_slots = bc.get("grocery_delivery_slots", "")   # e.g. "Morning (8–12), Afternoon (13–17)"
    allows_subs    = bc.get("grocery_allow_substitutions", True)

    lines = [
        "GROCERY ORDER FLOW:",
        "",
        "STEP 1 — GREETING & INTENT:",
        "- Greet the customer warmly. Ask what they need today.",
        "- Customer may say a specific item ('do you have unga?') OR ask to browse the catalog.",
        "  • Specific item request → check catalog immediately. If found → confirm name, price, unit. If not found → say 'Sorry, we don't carry that at the moment.'",
        "  • Browse request → show category menu first (if 2+ categories), then items within.",
        "",
        "STEP 2 — BROWSING & SEARCHING:",
        "- Use numbered menu (1️⃣ 2️⃣ 3️⃣) for all product listings.",
        "- ALWAYS show: item name, unit (e.g. per kg, per piece), price.",
        "  Format: '1️⃣ Tomatoes — KES 80 / kg'",
        "- ALWAYS add '0️⃣ View all images' as last menu option when products have images.",
        '  new_menu: {"0": {"id": "catalog", "name": "View all items", "price": 0, "type": "catalog"}}',
        "- When customer picks 0 → send send_catalog_images + resend item list.",
        "",
        "STEP 3 — STOCK & AVAILABILITY:",
        "- ALWAYS check the 'in_stock' status in the catalog before confirming an item.",
        "- If item shows ✗ OUT OF STOCK:",
        f"  → Say: 'Sorry, [item] is currently out of stock.'",
    ]

    if allows_subs:
        lines += [
            "  → Offer the nearest alternative if available: 'Would you like [similar item] instead?'",
            "  → If no alternative → say 'We'll restock soon. Would you like to add anything else?'",
        ]
    else:
        lines.append("  → Say 'We'll restock soon. Would you like to add anything else?'")

    lines += [
        "",
        "STEP 4 — ADDING ITEMS TO CART:",
        "- When customer selects an item → confirm: name, price, unit.",
        "- Ask for quantity. Use the unit from catalog:",
        "  e.g. 'How many kg of tomatoes would you like?' or 'How many packets of milk?'",
        "- After each item ask: 'Anything else to add or shall we proceed to checkout?'",
        "- Keep building the cart. Show running total if more than 1 item:",
        "  '🛒 Cart so far: Tomatoes 2kg × KES 80 = KES 160, Milk 2pkts × KES 55 = KES 110. Total: KES 270'",
        "- Continue until customer says done / checkout / confirm / sawa / ndiyo / no more.",
        "",
        "STEP 5 — FULFILMENT:",
        "- When customer is ready → ask: 'How would you like to receive your order?'",
    ]

    if has_pickup and has_delivery:
        lines.append("  Show: 1️⃣ Delivery  2️⃣ Pickup")
    elif has_delivery:
        lines.append("  Delivery only (no pickup configured).")
    elif has_pickup:
        lines.append("  Pickup only (no delivery configured).")

    if has_delivery:
        min_note   = f" Minimum delivery order: {min_order}." if min_order else ""
        zone_note  = f" {delivery_info}" if delivery_info else ""
        slot_note  = f" Available slots: {delivery_slots}." if delivery_slots else ""
        extra = (min_note + zone_note + slot_note).strip()
        lines += [
            "",
            f"DELIVERY PATH{(' — ' + extra) if extra else ''}:",
            "- Ask for delivery address.",
            "- Ask for preferred delivery date and time slot." + (f" Options: {delivery_slots}" if delivery_slots else ""),
            f"{'- Note: ' + min_note.strip() if min_order else ''}",
            "- Confirm: address, date/time, and order total including any delivery fee.",
            "- Fire create_order with delivery_type='delivery', delivery_address='[address]', notes='Delivery: [date] [slot]'.",
        ]

    if has_pickup:
        lines += [
            "",
            "PICKUP PATH:",
            "- Confirm pickup location from business info.",
            "- Ask preferred pickup date and time.",
            "- Fire create_order with delivery_type='pickup', notes='Pickup: [date] at [time]'.",
        ]

    lines += [
        "",
        "STEP 6 — ORDER SUMMARY & PAYMENT:",
        "- Show a clear cart summary before payment:",
        "  '🛒 *Your Order:*",
        "   • [Item] [qty][unit] × KES [price] = KES [line total]",
        "   • ...",
        "   📦 *Order Total: KES [total]*",
        "   🚚 *Delivery: [address] on [date]*'",
        "- Show payment details EXACTLY as configured.",
        "- Ask: 'Once paid, please reply with your full name and amount paid.'",
        "- Fire create_order ONCE with ALL items in the items[] array.",
        "",
        "PAYMENT CONFIRMATION:",
        "- When customer provides name + amount (or says 'nimetuma' / 'sent' / 'nimepay' / 'done'):",
        "  → intent=payment_received",
        "  → fire set_payment_pending(payee_name='...', amount_paid=...)",
        "  → fire notify_owner(reason='payment_received', message='[Name] paid [Amount] — grocery order')",
        "  → Reply: 'Thank you [name]! 🙏 Payment confirmed. Your order will be [delivered/ready for pickup] on [date].'",
        "",
        "ORDER MANAGEMENT:",
        "- 'my order' / 'order status' → show cart summary and fulfilment details from notes.",
        "- Cancel → confirm, fire cancel_order.",
        "- Add item after order placed → fire notify_owner, tell customer the owner will update the order.",
        "",
        "IMPORTANT RULES:",
        "- ALWAYS show the unit (per kg, per piece, etc.) when confirming items — customers need to know exactly what they're getting.",
        "- NEVER confirm an out-of-stock item without offering an alternative or acknowledging the unavailability.",
        "- NEVER fire create_order mid-collection. Wait until customer confirms done.",
        "- Keep the cart summary updated and visible after each item added.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_bakery_instructions(bc: dict) -> str:
    """Build full bakery-specific autoreply instructions from business config."""
    has_delivery      = bc.get("bakery_has_delivery", True)
    has_pickup        = bc.get("bakery_has_pickup", True)
    advance_days      = bc.get("bakery_advance_days", 3)        # default 3 days for custom/cake orders
    deposit_required  = bc.get("bakery_deposit_required", False)
    deposit_pct       = bc.get("bakery_deposit_pct", 50)        # % deposit for custom orders
    delivery_info     = bc.get("delivery_info", "")
    pickup_hours      = bc.get("bakery_pickup_hours", "") or bc.get("business_hours", "")
    min_order         = bc.get("bakery_min_order", "")

    lines = [
        "BAKERY ORDER FLOW:",
        "",
        "STEP 1 — MENU & BROWSING:",
        "- Greet the customer warmly. Show the menu grouped by category (e.g. Cakes, Bread, Pastries, Cookies).",
        "- Use numbered menu (1️⃣ 2️⃣ 3️⃣). Include item name, price, and description.",
        "- ALWAYS add '0️⃣ View all images' as the last menu option.",
        '  new_menu: {"0": {"id": "catalog", "name": "View all images", "price": 0, "type": "catalog"}}',
        "- When customer picks 0 or says 'show images' / 'pictures' / 'catalog' → send send_catalog_images + resend menu.",
        "",
        "STEP 2 — SELECTING AN ITEM:",
        "- When customer picks a number → resolve from last_menu → send send_product_image (if has image).",
        "- Confirm item name and price.",
        "- If item has VARIANTS (sizes/flavors e.g. 500g, 1kg, Chocolate, Vanilla) → ask BEFORE anything else:",
        "  'What size/flavor would you like?'",
        "  Show each variant with its full price: '1️⃣ 500g — KES 800  2️⃣ 1kg — KES 1,500  3️⃣ 2kg — KES 2,800'",
        "  new_menu: {\"1\": {\"id\": \"mod_500g\", \"name\": \"500g\", \"price\": 800, \"type\": \"modifier\"}, ...}",
        "  Use the selected variant's price as the unit_price in the order item. Record variant='[name]'.",
        "",
        "STEP 3 — CUSTOM & ADVANCE ORDERS:",
        f"- If the item is a cake (birthday, wedding, anniversary, custom) OR the description mentions 'custom' / 'advance' / 'pre-order':",
        f"  → Inform: 'This item requires at least {advance_days} days advance notice.'",
        "  → Ask: 'What date do you need it for?' Confirm if the date is feasible.",
        "  → Ask: 'Would you like a message written on it? (e.g. Happy Birthday John)' — record in notes.",
        "- For standard ready items (bread, cookies, pastries) → no advance notice needed, skip this step.",
        "",
        "STEP 4 — DIETARY & SPECIAL REQUESTS:",
        "- After selecting item, ask once: 'Do you have any dietary requirements or special requests?'",
        "  (e.g. sugar-free, gluten-free, eggless, nut-free, extra moist)",
        "- If customer says 'no' / 'none' / 'nothing' → move on immediately.",
        "- Record any requirements in the order notes.",
        "",
        "STEP 5 — QUANTITY:",
        "- Ask: 'How many would you like?'",
        f"{'- Mention minimum order if applicable: ' + min_order if min_order else ''}",
        "- After quantity confirmed → ask: 'Anything else or shall we confirm your order?'",
        "- If yes → resend menu. Keep building cart until customer says done / checkout / confirm / sawa / ndiyo.",
        "",
        "STEP 6 — FULFILMENT:",
        "- When customer is ready → ask: 'How would you like to receive your order?'",
    ]

    fulfil_options = []
    if has_pickup:
        fulfil_options.append("Pickup")
    if has_delivery:
        fulfil_options.append("Delivery")

    if has_pickup and has_delivery:
        lines.append("  Show: 1️⃣ Pickup  2️⃣ Delivery")
    elif has_pickup:
        lines.append("  Pickup only (no delivery configured).")
    elif has_delivery:
        lines.append("  Delivery only (no pickup configured).")

    if has_pickup:
        ph = f" (Pickup hours: {pickup_hours})" if pickup_hours else ""
        lines += [
            "",
            f"PICKUP PATH{ph}:",
            "- Ask for preferred pickup DATE and TIME.",
            "- Confirm pickup location from business info.",
            "- Record in notes: 'Pickup: [date] at [time]'",
            "- Fire create_order with delivery_type='pickup', notes including pickup date/time.",
        ]

    if has_delivery:
        dinfo = f" ({delivery_info})" if delivery_info else ""
        lines += [
            "",
            f"DELIVERY PATH{dinfo}:",
            "- Ask for delivery ADDRESS.",
            "- Ask for preferred delivery DATE and TIME.",
            "- Mention delivery fee/zone from business info if configured.",
            "- Record in notes: 'Delivery to [address] on [date] at [time]'",
            "- Fire create_order with delivery_type='delivery', delivery_address='[address]', notes including delivery date/time.",
        ]

    lines += [
        "",
        "STEP 7 — ORDER SUMMARY & PAYMENT:",
        "- Show a clear order summary before payment:",
        "  '🧁 *Your Order:*",
        "   • [Item] ([variant if any]) × [qty] — KES [total]",
        "   • Message: [inscription if any]",
        "   • [Pickup/Delivery]: [date] at [time]",
        "   📦 *Total: KES [amount]*'",
    ]

    if deposit_required:
        lines += [
            f"- For CUSTOM/CAKE orders → request a {deposit_pct}% deposit to confirm the order.",
            f"  'To confirm your order, a {deposit_pct}% deposit of KES [amount] is required.'",
            "- For STANDARD ready items → request full payment.",
        ]
    else:
        lines.append("- Request full payment for all orders.")

    lines += [
        "- Show payment details EXACTLY as configured. Ask: 'Once paid, please reply with your full name and amount paid.'",
        "",
        "PAYMENT CONFIRMATION:",
        "- When customer provides name + amount (or says 'nimetuma' / 'sent' / 'nimepay' / 'done'):",
        "  → intent=payment_received",
        "  → fire set_payment_pending(payee_name='...', amount_paid=...)",
        "  → fire notify_owner(reason='payment_received', message='[Name] paid [Amount] — [Item] for [date]')",
        "  → Reply: 'Thank you [name]! 🙏 Payment received. We'll have your [item] ready for [pickup/delivery date]. We'll notify you when it's ready!'",
        "",
        "ORDER MANAGEMENT:",
        "- 'my order' / 'order status' / 'is it ready?' → show order summary including pickup/delivery date from notes.",
        "- Cancel request → confirm, mention cancellation policy if in business info, fire cancel_order.",
        "- Change request (different flavor, date change) → confirm change, fire notify_owner for owner to action.",
        "",
        "IMPORTANT RULES:",
        "- NEVER confirm a custom/cake order without first collecting: variant (if any), inscription, date, dietary needs.",
        "- NEVER show payment details before the full order + fulfilment is confirmed.",
        "- Always fire create_order ONCE with ALL items collected. Never fire mid-collection.",
        "- If a product is marked OUT OF STOCK → apologise and suggest the closest available alternative.",
    ]

    return "\n".join(l for l in lines if l is not None)


def _build_restaurant_instructions(bc: dict) -> str:
    has_dine_in  = bc.get("restaurant_has_dine_in",  True)
    has_delivery = bc.get("restaurant_has_delivery", True)
    has_takeout  = bc.get("restaurant_has_takeout",  True)
    table_range  = bc.get("restaurant_table_range",  "")
    avg_wait     = bc.get("restaurant_avg_wait",     "")
    min_delivery = bc.get("restaurant_min_delivery", "")
    delivery_info = bc.get("delivery_info", "")

    # Build available modes list
    mode_lines = []
    mode_index = 1
    mode_map = []
    if has_dine_in:
        mode_lines.append(f"  {mode_index}\ufe0f\u20e3 Dine-in")
        mode_map.append("dine_in")
        mode_index += 1
    if has_delivery:
        mode_lines.append(f"  {mode_index}\ufe0f\u20e3 Delivery")
        mode_map.append("delivery")
        mode_index += 1
    if has_takeout:
        mode_lines.append(f"  {mode_index}\ufe0f\u20e3 Takeout / Pickup")
        mode_map.append("takeout")
        mode_index += 1

    if not mode_lines:
        mode_lines = ["  1\ufe0f\u20e3 Dine-in", "  2\ufe0f\u20e3 Delivery", "  3\ufe0f\u20e3 Takeout / Pickup"]

    modes_block = "\n".join(mode_lines)

    lines = [
        "RESTAURANT ORDER FLOW:",
        "",
        "STEP 1 — ORDER TYPE:",
        "When customer first contacts (greeting / order intent), greet them warmly and present available order modes:",
        modes_block,
        "Set new_menu with these options. Set flow_update: active_flow=ordering, flow_step=awaiting_order_type.",
        "",
    ]

    if has_dine_in:
        dine_table = f" ({table_range})" if table_range else ""
        lines += [
            f"DINE-IN PATH:",
            f"- Ask for their table number{dine_table}.",
            "- Set flow_step=awaiting_table_number until received.",
            "- Once table number is known → show full menu as numbered list grouped by category.",
            "- Add \"0\ufe0f\u20e3 View all images\" as last menu option if products have images.",
            "- Customer may order multiple items. After each item ask \"Anything else or confirm order?\"",
            "- When customer confirms → fire create_order with delivery_type=\"dine_in\", table_number=\"[table]\", notes=\"Table [table]\".",
            "- Show payment methods. Ask for name + amount paid → set_payment_pending + notify_owner.",
            "",
        ]

    if has_delivery:
        wait_note = f"Estimated prep time: {avg_wait}." if avg_wait else ""
        min_note  = f"Minimum delivery order: {min_delivery}." if min_delivery else ""
        zone_note = f"Delivery zones/fees: {delivery_info}" if delivery_info else ""
        extra = " ".join(x for x in [wait_note, min_note, zone_note] if x)
        lines += [
            "DELIVERY PATH:",
            "- Ask for the customer's delivery address.",
            "- Set flow_step=awaiting_address until received.",
        ]
        if extra:
            lines.append(f"- {extra}")
        lines += [
            "- Show menu as numbered list. Add \"0\ufe0f\u20e3 View all images\" if products have images.",
            "- Collect all items. After each item ask \"Anything else or confirm order?\"",
            "- Confirm total + delivery fee (if applicable), then fire create_order with delivery_type=\"delivery\", delivery_address=\"[address]\".",
            "- Show payment methods. Ask for name + amount paid → set_payment_pending + notify_owner.",
            "",
        ]

    if has_takeout:
        pickup_wait = f" Estimated pickup time: {avg_wait}." if avg_wait else ""
        lines += [
            "TAKEOUT / PICKUP PATH:",
            "- Show menu as numbered list. Add \"0\ufe0f\u20e3 View all images\" if products have images.",
            "- Collect all items. After each item ask \"Anything else or confirm order?\"",
            f"- Confirm total + tell customer when order will be ready.{pickup_wait}",
            "- Fire create_order with delivery_type=\"pickup\".",
            "- Show payment methods. Ask for name + amount paid → set_payment_pending + notify_owner.",
            "",
        ]

    has_reservations = bc.get("restaurant_has_reservations", False)
    if has_reservations:
        lines += [
            "RESERVATION PATH:",
            "- When customer says \"reserve\", \"table booking\", \"book a table\" → start reservation flow.",
            "- Ask: How many people? What date? What time?",
            "- Confirm: \"Table for [N] on [date] at [time] — confirmed! 🎉\"",
            "- Fire create_booking with notes=\"Table reservation: [N] guests\", delivery_type=\"dine_in\".",
            "",
        ]

    lines += [
        "MENU DISPLAY:",
        "- When showing menu items, include the description below each item (from catalog context '→ description').",
        "- Format: '1️⃣ Chicken Biryani – KES 800\n   Spiced rice with tender chicken, slow-cooked with aromatic spices'",
        "- Always add \"0️⃣ View all images\" as last menu option when products have images.",
        "  Include in new_menu as {\"0\": {\"id\": \"catalog\", \"name\": \"View all images\", \"price\": 0, \"type\": \"catalog\"}}.",
        "- When customer picks 0 → send_catalog_images of all products with images + show full menu again.",
        "- When customer picks a number → send_product_image (if has image) → go through MODIFIERS (if any) → then ask quantity.",
        "",
        "MODIFIERS FLOW:",
        "- If product has modifiers, ask customer to choose options.",
        "- Format: 'Choose [modifier name]: [option 1], [option 2], ...'",
        "- Customer responds with the option number.",
        "- Update order item with chosen modifier.",
        "",
        "ORDER MANAGEMENT:",
        "- If customer asks \"my order\" / \"order status\" → show details + 1️⃣ Update 2️⃣ Cancel options.",
        "- Cancel → confirm, fire cancel_order.",
        "",
        "SCREENSHOT / PAYMENT:",
        "- When customer sends screenshot / \"nimetuma\" / \"sent\" / \"I've paid\" → intent=payment_received + set_payment_pending + notify_owner.",
    ]

    return "\n".join(lines)


# ── Builder ───────────────────────────────────────────────────────────────────

def build_system_prompt(
    business_config: dict,
    products: list,
    services: list,
    mini_state: dict,
) -> str:
    bc = business_config
    btype = bc.get("type", "retail")
    currency = bc.get("currency", "KES")
    parts: List[str] = []

    # ── Identity ──
    name = bc.get("name") or "this business"
    parts.append(f"You are the WhatsApp assistant for *{name}*.")
    if bc.get("about"):
        parts.append(f"About: {bc['about']}")
    if bc.get("products_services"):
        parts.append(f"What we sell/offer: {bc['products_services']}")

    # ── Operating details ──
    details: List[str] = [f"Currency: {currency}"]
    if bc.get("business_hours"):
        details.append(f"Hours: {bc['business_hours']}")
    if bc.get("delivery_info"):
        details.append(f"Delivery: {bc['delivery_info']}")
    if bc.get("special_offers"):
        details.append(f"Current offers: {bc['special_offers']}")
    parts.append("\n".join(details))

    # ── Payment methods — CRITICAL: must be shown exactly as configured ──
    if bc.get("payment_methods"):
        pm_block = "Payment methods (show these EXACTLY when customer is ready to pay):\n"
        pm_block += "\n".join(f"  - {p}" for p in bc["payment_methods"])
        parts.append(pm_block)
    else:
        parts.append("Payment methods: Not configured — tell customer the owner will share details.")

    # ── FAQs ──
    if bc.get("faqs"):
        parts.append(f"FAQs:\n{bc['faqs']}")

    # ── Catalog ──
    # Classify display mode by business type
    _MENU_TYPES    = {"restaurant", "food", "bakery"}
    _SERVICE_TYPES = {"salon", "beauty", "spa", "services", "repair", "cleaning",
                      "fitness", "gym", "events", "photography", "healthcare", "clinic"}
    _RENTAL_TYPES  = {"rental"}
    _is_menu    = btype in _MENU_TYPES
    _is_service = btype in _SERVICE_TYPES
    _is_rental  = btype in _RENTAL_TYPES

    def _variants_line(p: Dict, cur: str) -> str:
        """Return an indented variants line if the product has variants."""
        vs = p.get("variants") or []
        if not vs:
            return ""
        parts_v = ", ".join(f"{v['name']} ({cur} {v['price']:,.0f})" for v in vs)
        return f"    ↳ Variants: {parts_v}"

    def _pricing_tiers_line(p: Dict, cur: str) -> str:
        """Return bulk pricing tiers line for wholesale products."""
        tiers = p.get("pricing_tiers") or []
        if not tiers:
            return ""
        unit = p.get("unit", "unit")
        sorted_tiers = sorted(tiers, key=lambda t: t.get("min_qty", 0))
        tier_parts = []
        for i, t in enumerate(sorted_tiers):
            min_q = t.get("min_qty", 1)
            next_min = sorted_tiers[i + 1].get("min_qty") if i + 1 < len(sorted_tiers) else None
            label = f"{min_q}–{next_min - 1}" if next_min else f"{min_q}+"
            tier_parts.append(f"{label} {unit}: {cur} {t['price']:,.0f}")
        return f"    ↳ Bulk pricing: {' | '.join(tier_parts)}"

    def _modifiers_lines(p: Dict, cur: str) -> List[str]:
        """Return indented modifier group lines if the product has modifier_groups."""
        groups = p.get("modifier_groups") or []
        result = []
        for g in groups:
            gname = g.get("name", "")
            required = "required" if g.get("required") else "optional"
            multi    = ", multi" if g.get("multi_select") else ""
            opts = ", ".join(
                f"{o['name']}" + (f" (+{cur} {o['price_delta']:,.0f})" if o.get("price_delta") else "")
                for o in g.get("options", [])
            )
            result.append(f"    ↳ {gname} ({required}{multi}): {opts}")
        return result

    catalog_lines: List[str] = []
    if products:
        def _append_product_extras(p: Dict) -> None:
            """Append description, variants, modifier lines, and wholesale extras."""
            if p.get("description"):
                catalog_lines.append(f"    → {p['description']}")
            vl = _variants_line(p, currency)
            if vl:
                catalog_lines.append(vl)
            for ml in _modifiers_lines(p, currency):
                catalog_lines.append(ml)
            # Wholesale: bulk pricing tiers
            ptl = _pricing_tiers_line(p, currency)
            if ptl:
                catalog_lines.append(ptl)
            # Wholesale: MOQ (if > 1)
            moq = p.get("moq") or 1
            if moq > 1:
                unit = p.get("unit", "units")
                catalog_lines.append(f"    ↳ Minimum order: {moq} {unit}")

        if _is_menu:
            # Group by category → sub_category for a clean hierarchical menu
            # Build: {cat: {sub_cat: [products]}}
            cat_map: Dict[str, Dict[str, List[Dict]]] = defaultdict(lambda: defaultdict(list))
            for p in products:
                cat = p.get("category") or "Uncategorized"
                sub = p.get("sub_category") or ""
                cat_map[cat][sub].append(p)

            catalog_lines.append("MENU (grouped by Category > Sub-category):")
            for cat, sub_map in cat_map.items():
                catalog_lines.append(f"▸ {cat}")
                for sub, items in sub_map.items():
                    if sub:
                        catalog_lines.append(f"  ── {sub}")
                        indent = "    "
                    else:
                        indent = "  "
                    for p in items:
                        has_img = "📷" if p.get("image_url") else ""
                        catalog_lines.append(
                            f"{indent}{p['id']} | {p['name']} | {currency} {p['price']:,.0f} {has_img}"
                        )
                        # description / variants / modifiers indented one extra level
                        orig_len = len(catalog_lines)
                        _append_product_extras(p)
                        for i in range(orig_len, len(catalog_lines)):
                            catalog_lines[i] = indent + catalog_lines[i].lstrip()
        elif _is_service:
            catalog_lines.append("SERVICES / CATALOG (ID | Name | Category | Price | HasImage):")
            for p in products:
                cat     = f" [{p['category']}]" if p.get("category") else ""
                sub     = f" / {p['sub_category']}" if p.get("sub_category") else ""
                has_img = "📷" if p.get("image_url") else ""
                catalog_lines.append(
                    f"  {p['id']} | {p['name']}{cat}{sub} | {currency} {p['price']:,.0f} {has_img}"
                )
                _append_product_extras(p)
        elif _is_rental:
            catalog_lines.append("LISTINGS / RENTAL CATALOG (ID | Name | Category | Rate | HasImage):")
            for p in products:
                cat     = f" [{p['category']}]" if p.get("category") else ""
                sub     = f" / {p['sub_category']}" if p.get("sub_category") else ""
                has_img = "📷" if p.get("image_url") else ""
                catalog_lines.append(
                    f"  {p['id']} | {p['name']}{cat}{sub} | {currency} {p['price']:,.0f}/night {has_img}"
                )
                _append_product_extras(p)
        else:
            if btype == "creator":
                catalog_lines.append("CONTENT PACKAGES / PRODUCTS (ID | Name | Category | Price | Includes | HasImage):")
            else:
                catalog_lines.append("PRODUCTS (ID | Name | Category | Price | Unit | Stock | HasImage):")
            for p in products:
                stock   = "✓" if p.get("in_stock", True) else "✗ OUT OF STOCK"
                cat     = f" [{p['category']}]" if p.get("category") else ""
                sub     = f" / {p['sub_category']}" if p.get("sub_category") else ""
                unit    = f" ({p['unit']})" if p.get("unit") else ""
                has_img = "📷" if p.get("image_url") else ""
                catalog_lines.append(
                    f"  {p['id']} | {p['name']}{cat}{sub}{unit} | {currency} {p['price']:,.0f} | {stock} {has_img}"
                )
                _append_product_extras(p)

    if services:
        catalog_lines.append("SERVICES (ID | Name | Category | Duration | Price):")
        for s in services:
            dur    = f"{s['duration']}min" if s.get("duration") else "-"
            cat    = f" [{s['category']}]" if s.get("category") else ""
            rental = " [RENTAL]" if s.get("is_rental") else ""
            catalog_lines.append(f"  {s['id']} | {s['name']}{cat}{rental} | {dur} | {currency} {s['price']:,.0f}")

    if catalog_lines:
        parts.append("\n".join(catalog_lines))
    else:
        if _is_menu:
            parts.append("No menu items have been set up yet. Let the customer know to check back soon.")
        else:
            parts.append("No products or services have been set up yet. Let the customer know to check back soon.")

    # ── Catalog terminology + categories (used by AI for browsing + labelling) ──
    item_label = _get_item_label(btype)
    categories_line = _get_categories_block(products, services)
    parts.append(
        f"CATALOG ITEM LABEL: {item_label}\n"
        f"(Use \"{item_label}\" when naming catalog items. E.g. \"0️⃣ View all {item_label}\")\n"
        f"{categories_line}"
    )

    # ── Current conversation state ──
    if mini_state.get("active_flow") or mini_state.get("flow_step"):
        state_lines = ["CURRENT CONVERSATION STATE:"]
        if mini_state.get("active_flow"):
            state_lines.append(f"  Customer is currently in: {mini_state['active_flow']} flow")
        if mini_state.get("flow_step"):
            state_lines.append(f"  Waiting for customer to provide: {mini_state['flow_step']}")
        if mini_state.get("flow_product_id"):
            state_lines.append(f"  Product/service in discussion: ID={mini_state['flow_product_id']}")
        parts.append("\n".join(state_lines))

    # ── Last menu (numbered selection anchor) ──
    if mini_state.get("last_menu"):
        menu_json = json.dumps(mini_state["last_menu"], ensure_ascii=False)
        parts.append(f"LAST MENU SENT TO CUSTOMER (resolve numbered replies using this):\n{menu_json}")

    # ── Business-type instructions ──
    if btype == "restaurant":
        instructions = _build_restaurant_instructions(bc)
    elif btype == "bakery":
        instructions = _build_bakery_instructions(bc)
    elif btype == "grocery":
        instructions = _build_grocery_instructions(bc)
    elif btype == "wholesale":
        instructions = _build_wholesale_instructions(bc)
    elif btype == "food":
        instructions = _build_food_instructions(bc)
    elif btype == "creator":
        instructions = _build_creator_instructions(bc)
    elif btype == "general":
        instructions = _build_general_instructions(bc)
    elif btype == "salon" or btype == "beauty":
        instructions = _build_salon_instructions(bc)
    elif btype == "spa":
        instructions = _build_spa_instructions(bc)
    elif btype == "repair":
        instructions = _build_repair_instructions(bc)
    elif btype == "cleaning":
        instructions = _build_cleaning_instructions(bc)
    elif btype in ("fitness", "gym"):
        instructions = _build_fitness_instructions(bc)
    elif btype in ("events", "photography"):
        instructions = _build_events_instructions(bc)
    elif btype in ("healthcare", "clinic"):
        instructions = _build_healthcare_instructions(bc)
    else:
        instructions = _BUSINESS_INSTRUCTIONS.get(btype, _DEFAULT_INSTRUCTIONS)
    parts.append(f"INSTRUCTIONS FOR THIS BUSINESS TYPE ({btype.upper()}):\n{instructions}")

    # ── Shared instructions — only blocks that apply to this business type ──
    _BT_ORDER    = {"retail", "wholesale", "food", "bakery", "grocery", "creator", "restaurant"}
    _BT_BOOKING  = {"salon", "beauty", "spa", "services", "repair", "cleaning",
                    "fitness", "gym", "events", "photography", "healthcare", "clinic"}

    parts.append(_SHARED_ALWAYS)
    if btype == "rental":
        parts.append(_SHARED_RENTAL_BLOCK)
    elif btype in _BT_BOOKING:
        parts.append(_SHARED_BOOKING_BLOCK)
    elif btype in _BT_ORDER:
        parts.append(_SHARED_ORDER_BLOCK)
    else:  # general — can have products OR services
        parts.append(_SHARED_ORDER_BLOCK)
        parts.append(_SHARED_BOOKING_BLOCK)

    # ── Response format — only relevant actions for this type ──
    parts.append(_build_response_format(btype))

    return "\n\n---\n\n".join(parts)

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
from typing import Dict, List


# ── Per-business-type instruction blocks ─────────────────────────────────────

_BUSINESS_INSTRUCTIONS: Dict[str, str] = {
    "retail": """\
- BROWSING: When customer wants to see / browse products, send numbered menu (new_menu) + send_catalog_images action for products with images (up to 8 at a time). Customer just browses, no pressure.
- SELECTING: When customer picks a number, send send_product_image action (if has image), confirm item, ask quantity.
- ADDING MORE: After qty confirmed, ask "Anything else or checkout?" If yes → send catalog menu again.
- CHECKOUT: When customer says checkout/done/confirm → ask delivery or pickup. If delivery → ask address. Then fire create_order with ALL collected items + delivery info at once.
- ORDER MANAGEMENT: When customer asks "my order" → show order details + 1️⃣ Update 2️⃣ Cancel options.
- PAYMENT: After create_order fires → show order summary + exact payment details → ask for screenshot.
- SCREENSHOT: intent=payment_received + set_payment_pending + notify_owner.""",

    "wholesale": """\
- Show products with numbered menu when asked.
- Ask for quantity (minimum order quantities may apply).
- Ask for delivery or pickup and address if delivery.
- Confirm total + payment details. Request payment screenshot or invoice preference.""",

    "restaurant": """\
- Show menu by category with numbered items when customer asks.
- Customer may order multiple items — keep collecting until they say done/confirm.
- Ask for dine-in, takeaway, or delivery.
- If delivery: collect delivery address and estimated time.
- Confirm full order + total, show payment details, request screenshot.""",

    "food": """\
- Show menu with numbered items. Customer may add multiple items.
- Ask for delivery or pickup.
- If delivery: collect address.
- Confirm order + total + payment details. Request screenshot.""",

    "bakery": """\
- Show products with numbered menu.
- Some items may need advance notice — mention if relevant.
- Confirm quantity, pickup date/time or delivery address.
- Show total + payment details. Request screenshot.""",

    "grocery": """\
- Show available products with numbered menu or by category.
- Customer may add multiple items.
- Ask for delivery or pickup.
- Confirm total + payment details. Request screenshot.""",

    "salon": """\
- Show services with numbered menu (include duration and price).
- After service selected: ask for preferred date and time.
- Confirm appointment details with customer before saving booking.
- After confirmation: save booking. If deposit required, show payment details.""",

    "beauty": """\
- Show services with numbered menu (include duration and price).
- After service selected: ask for preferred date and time.
- Confirm appointment details. Save booking on confirmation.
- If deposit required, show payment details and request screenshot.""",

    "spa": """\
- Show treatments with numbered menu (include duration and price).
- Ask for preferred date, time, and number of guests if applicable.
- Confirm and save booking. Show payment details for deposit if required.""",

    "services": """\
- Show services with numbered menu.
- After selection: ask for job description and details.
- Ask for preferred date, time, and location/address.
- Confirm appointment. If upfront payment required, show payment details.""",

    "repair": """\
- Ask customer to describe the issue.
- Provide estimated cost if possible or say a quote will be given after assessment.
- Ask for preferred date and time or customer's location.
- Confirm appointment.""",

    "cleaning": """\
- Show cleaning packages with numbered menu.
- Ask for address, preferred date and time, and property size if relevant.
- Confirm appointment + total. Request payment screenshot if payment required.""",

    "clinic": """\
- Show consultation types or services with numbered menu.
- Ask for patient name (if booking for someone else).
- Ask for preferred date and time.
- Confirm appointment. Mention any preparation instructions if relevant.""",

    "photography": """\
- Show packages/session types with numbered menu.
- Ask for event date, location, and number of hours.
- Confirm details. Show payment details for deposit. Request screenshot.""",

    "events": """\
- Show event packages with numbered menu.
- Collect event date, venue, guest count, and specific requirements.
- Confirm details + total. Request deposit payment screenshot.""",

    "gym": """\
- Show membership plans or classes with numbered menu.
- Ask for start date and preferred schedule.
- Confirm plan + total. Show payment details. Request screenshot.""",

    "rental": """\
- Show available items/properties with numbered menu.
- Ask for check-in date and check-out date.
- Calculate and confirm total cost for the duration.
- Show payment details for deposit/full payment. Request screenshot.""",
}

# Fallback for unknown business types
_DEFAULT_INSTRUCTIONS = """\
- Show available products or services with numbered menu when asked.
- Collect necessary details (quantity, date, address) step by step.
- Confirm total + payment details. Request payment screenshot to complete."""

# ── Shared instructions (apply to all business types) ────────────────────────

_SHARED_INSTRUCTIONS = """\
LANGUAGE:
- Detect the customer's language from their first message and reply in the same language.
- If they mix Swahili and English (Sheng/code-switch), match their style naturally.
- Never switch language mid-conversation unless the customer does.

NUMBERED MENUS:
- Always use numbered menus (1️⃣ 2️⃣ 3️⃣) when showing products or services.
- Set new_menu in your JSON response with this format:
  {"1": {"id": "EXACT_DB_ID", "name": "Product Name", "price": 500, "type": "product", "image_url": "url_or_empty"}}
- ALWAYS use the exact database ID from the catalog — never make up IDs.
- Include image_url from the catalog (leave empty string if no image).
- Menus expire after 2 hours. If customer references an old menu, regenerate.
- If LAST MENU SENT is provided, use it to resolve numbered selections.

PRODUCT IMAGES — SELECTING A PRODUCT:
- When customer selects a specific product from a menu, include send_product_image action if the product has an image_url.
  {"type": "send_product_image", "product_id": "DB_ID", "image_url": "https://...", "caption": "T-shirt — KES 500"}

CATALOG BROWSING (window shopping — no purchase required):
- When customer says "show me products" / "let me see" / "show catalog" / "show images" / "browse":
  • Send a numbered menu (new_menu) with up to 8 products at a time.
  • Include action: {"type": "send_catalog_images", "products": [{"image_url":"...","caption":"1️⃣ T-shirt — KES 500"},…]}
    (only include products that have an image_url)
  • If there are more products than shown, add "Reply *more* or *0* to see more" to the reply.
- Customer is just browsing — no pressure to buy. They pick a number when ready.
- "0" or "more" → send next batch of products.
- This is separate from the ordering flow — customer can browse then decide.

MULTI-PRODUCT ORDERING:
- After customer picks first item and quantity, ask "Would you like to add anything else, or checkout?"
- If YES / "add" / "yes I would like to add" → send catalog menu again (new_menu) so they can pick.
- Keep collecting until customer says: checkout / done / that's all / ndiyo / sawa / confirm / no more.
- When customer confirms checkout → THEN fire create_order with ALL collected items at once.
- Use items array in create_order (collect everything first, create once):
  {"type": "create_order", "items": [{"product_name":"T-shirt","product_id":"DB_ID","quantity":3,"unit_price":500},{"product_name":"Trouser","product_id":"DB_ID","quantity":1,"unit_price":750}], "delivery_type":"pickup|delivery", "delivery_address":""}
- To add to an order already saved in DB: {"type": "update_order", "update_type": "add_item", ...}
- To remove: {"type": "update_order", "update_type": "remove_item", "product_name": "T-shirt"}
- To change qty: {"type": "update_order", "update_type": "change_qty", "product_name": "T-shirt", "quantity": 3}

ORDER MANAGEMENT (when customer asks about their order):
- When customer says "my order" / "order status" / "what did I order":
  Show order details AND offer options as a numbered menu:
  1️⃣ Update order (add/remove/change qty)
  2️⃣ Cancel order
  3️⃣ Track delivery / contact us
  Set new_menu for these options too.
- If customer picks Update → show what they can change (add item, remove item, change qty).
- If customer picks Cancel → confirm cancellation, fire cancel_order action.

FLOW TRACKING:
- Use flow_update to track conversation step:
  active_flow: "ordering" | "booking" | "browsing" | null
  flow_step: "collecting_items" | "awaiting_delivery" | "awaiting_address" | "awaiting_payment" | "awaiting_date" | null
- Set flow_update on every step change.
- Set clear_flow when order/booking is complete or cancelled.

PAYMENT — CRITICAL RULES:
- ONLY show payment methods listed under "Payment methods" in your context. Show FULL details exactly.
- NEVER invent or guess payment details. If none configured: "The owner will share payment details shortly."
- When customer sends screenshot / "nimetuma" / "sent" / "I've paid":
  • intent = "payment_received"
  • {"type": "set_payment_pending", "order_id": "latest"}
  • {"type": "notify_owner", "reason": "payment_received", "message": "Customer sent payment screenshot"}
  • Reply: "Got your payment! 🙏 The owner will confirm shortly."

ESCALATION — set escalate=true when:
- Customer is angry, uses offensive language, or threatens
- Customer asks for a refund or disputes a charge
- Customer reports a problem with a delivered order/booking
- Customer explicitly asks to speak to a human or the owner

ORDERS — create_order timing:
- Fire create_order ONLY after: all items collected + delivery type confirmed + address (if delivery).
- Never fire create_order in the middle of item collection.
- After create_order fires, proceed to show payment details.

BOOKINGS — create when:
- Service, date (and time if needed) confirmed by customer.

BUSINESS CONTEXT:
- Only describe what this business actually sells. Do not invent products or categories.

TONE:
- Friendly, helpful, concise. Use emoji sparingly. Never be pushy."""

# ── JSON response format ──────────────────────────────────────────────────────

_RESPONSE_FORMAT = """\
RESPONSE FORMAT — respond with a single valid JSON object ONLY.
No text before or after. No markdown code blocks.

Required schema:
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

Available action types:
  {"type": "send_product_image", "product_id": "DB_ID", "image_url": "https://...", "caption": "Name — KES 500"}
  {"type": "send_catalog_images", "products": [{"image_url": "https://...", "caption": "1️⃣ T-shirt — KES 500"}, ...]}
  {"type": "create_order", "items": [{"product_name":"Name","product_id":"DB_ID","quantity":1,"unit_price":500}], "delivery_type": "pickup|delivery", "delivery_address": "", "notes": ""}
  {"type": "update_order", "update_type": "add_item|remove_item|change_qty|change_delivery", "order_id": "latest", "product_name": "", "product_id": "", "quantity": 1, "unit_price": 0, "delivery_type": ""}
  {"type": "create_booking", "service_id": "DB_ID", "service_name": "Name", "price": 500, "date": "Mon 14 April", "time": "10am", "is_rental": false, "checkin_date": "", "checkout_date": ""}
  {"type": "cancel_order", "order_id": "latest", "reason": ""}
  {"type": "reschedule_booking", "booking_id": "latest", "new_date": "Tue 15 April", "reason": ""}
  {"type": "tag_customer", "tag": "interested|vip|frequent_buyer|complaint"}
  {"type": "set_payment_pending", "order_id": "latest"}
  {"type": "notify_owner", "reason": "payment_received|escalation|complaint|other", "message": "context for owner"}
  {"type": "clear_flow"}

flow_update (include only fields that changed):
  {"active_flow": "ordering|booking|browsing|null", "flow_product_id": "DB_ID_or_null", "flow_step": "collecting_items|awaiting_delivery|awaiting_address|awaiting_payment|awaiting_date|null"}"""


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
    catalog_lines: List[str] = []
    if products:
        catalog_lines.append("PRODUCTS (ID | Name | Category | Price | Stock | HasImage):")
        for p in products:
            stock = "✓" if p.get("in_stock", True) else "✗ OUT OF STOCK"
            cat = f" [{p['category']}]" if p.get("category") else ""
            has_img = "📷" if p.get("image_url") else ""
            img_url = p.get("image_url", "")
            catalog_lines.append(
                f"  {p['id']} | {p['name']}{cat} | {currency} {p['price']:,.0f} | {stock} {has_img} | img:{img_url}"
            )

    if services:
        catalog_lines.append("SERVICES (ID | Name | Category | Duration | Price):")
        for s in services:
            dur = f"{s['duration']}min" if s.get("duration") else "-"
            cat = f" [{s['category']}]" if s.get("category") else ""
            rental = " [RENTAL]" if s.get("is_rental") else ""
            catalog_lines.append(f"  {s['id']} | {s['name']}{cat}{rental} | {dur} | {currency} {s['price']:,.0f}")

    if catalog_lines:
        parts.append("\n".join(catalog_lines))
    else:
        parts.append("No products or services have been set up yet. Let the customer know to check back soon.")

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
    instructions = _BUSINESS_INSTRUCTIONS.get(btype, _DEFAULT_INSTRUCTIONS)
    parts.append(f"INSTRUCTIONS FOR THIS BUSINESS TYPE ({btype.upper()}):\n{instructions}")

    # ── Shared instructions ──
    parts.append(_SHARED_INSTRUCTIONS)

    # ── Response format ──
    parts.append(_RESPONSE_FORMAT)

    return "\n\n---\n\n".join(parts)

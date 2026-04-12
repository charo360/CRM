# AutoReply V2 — Architecture & Implementation Guide

Branch: `feat/autoreply-v2`
Entry point: `CRM/backend/autoreply/engine.py`

---

## Overview

AutoReply V2 is a stateless AI-driven WhatsApp assistant engine for the CRM SaaS.
It replaces a broken 30-field state machine with a clean architecture:

> **Conversation history (last 10 messages) = state. Mini-state = 5 fields only.**

The engine is multi-tenant and multi-provider. Every business owner can pick their own AI model (OpenAI, DeepSeek, Grok, Claude, GPT-5) and the engine routes through AIMessageDrafter automatically.

---

## File Structure

```
CRM/backend/autoreply/
├── __init__.py             # empty package init
├── engine.py               # main entry point — called from server.py
├── context_loader.py       # loads all DB context for one AI turn
├── prompt_builder.py       # builds the system prompt from business config
└── action_handler.py       # executes CRM write actions from AI response
```

---

## How It Works (One Turn)

```
WhatsApp message arrives
        ↓
server.py (gates: owner pause, opt-out, not own number)
        ↓
autoreply/engine.py → process_message()
    1. load_context()         — last 10 msgs + mini-state + catalog + business config
    2. build_system_prompt()  — config-driven prompt for this business type
    3. call AI with retry     — routes through AIMessageDrafter provider
    4. parse + validate JSON  — retry once on failure, fallback on second fail
    5. execute_actions()      — CRM writes (orders, bookings, tags, etc.)
    6. push notifications     — payment received, escalation, alerts
    7. update mini-state      — save flow/menu state to conversation_states
    8. send images            — extra angles (no caption), last image with caption
    9. send text reply        — append order number if new order was created
```

---

## AI Response Schema

The AI must respond with a single JSON object — no markdown, no prose:

```json
{
  "reply": "WhatsApp message to send (required)",
  "intent": "order|booking|inquiry|complaint|greeting|payment_received|cancel|reschedule|other",
  "sentiment": "positive|neutral|negative|angry",
  "escalate": false,
  "escalate_reason": "",
  "actions": [],
  "new_menu": null,
  "flow_update": null
}
```

On JSON failure: retries once with a correction prompt. On second failure: sends FALLBACK_REPLY ("Sorry, I didn't quite catch that. Could you please repeat?") and logs the full raw AI response at ERROR level (visible in Railway logs).

---

## Actions the AI Can Fire

| Action | What it does |
|--------|-------------|
| `create_order` | Inserts into `db.orders` with items[], total, delivery info. Returns order_number. |
| `update_order` | add_item / remove_item / change_qty / change_delivery on latest active order |
| `create_booking` | Inserts into `db.bookings` with service, date, time |
| `cancel_order` | Sets order status=cancelled |
| `reschedule_booking` | Sets booking status=reschedule_requested with new_date |
| `tag_customer` | $addToSet tag on customer (interested/vip/frequent_buyer/complaint) |
| `set_payment_pending` | Sets order payment_status=pending_verification |
| `notify_owner` | Sets needs_human=True on customer + sends push notification |
| `send_product_image` | Engine sends all product images (extra angles no caption, last with caption) |
| `send_catalog_images` | Engine sends 8 products per batch, each with all their angles |
| `clear_flow` | Wipes active_flow/flow_step/flow_product_id/last_menu from mini-state |

---

## Mini-State (5 fields in `db.conversation_states`)

| Field | Values | Purpose |
|-------|--------|---------|
| `active_flow` | `"ordering"` / `"booking"` / `"browsing"` / `null` | What the customer is doing |
| `flow_product_id` | DB ID or `null` | Product/service being discussed |
| `flow_step` | `"collecting_items"` / `"awaiting_delivery"` / `"awaiting_address"` / `"awaiting_payment"` / `"awaiting_date"` / `null` | Where in the flow |
| `last_menu` | `{"1": {id, name, price, type}, ...}` or `{}` | Last numbered menu sent (2hr TTL) |
| `escalated` | `bool` | Whether this customer has been escalated |

`last_menu` expires after 2 hours — prevents "1" resolving to yesterday's menu.

---

## Product Image Sending

**Scenario 1 — Customer selects a specific product (`send_product_image` action):**
1. Engine looks up product by DB ID in `products_by_id` dict (built from loaded catalog)
2. Sends `images[0..n-2]` with no caption (extra angles) — 0.7s delay between each
3. Sends `images[-1]` with caption: `"T-shirt — KES 500"` — 0.5s after
4. Fallback: if product not in catalog, uses `image_url` from AI response directly

**Scenario 2 — Customer browses catalog (`send_catalog_images` action):**
1. AI returns `product_ids: ["DB_ID_1", "DB_ID_2", ...]` (max 8)
2. Engine resolves each ID from loaded catalog
3. Applies Scenario 1 per product
4. 1.5s gap between products (WhatsApp rate limiting)

---

## Numbered Menus

Every product menu always includes `0️⃣ View all images` as the last option:

```
1️⃣ T-shirt — KES 500
2️⃣ Trouser — KES 750
0️⃣ View all images
```

`new_menu` in the JSON response:
```json
{
  "1": {"id": "DB_ID", "name": "T-shirt", "price": 500, "type": "product"},
  "2": {"id": "DB_ID", "name": "Trouser", "price": 750, "type": "product"},
  "0": {"id": "catalog", "name": "View all images", "price": 0, "type": "catalog"}
}
```

When customer replies `0` → triggers `send_catalog_images` with all products that have images.

---

## Multi-Product Ordering Flow

1. Customer browses → picks a number → bot asks quantity
2. Bot asks: "Anything else or checkout?"
3. Customer says yes → menu sent again (keeps collecting)
4. Customer says checkout/done → bot asks delivery or pickup
5. If delivery → asks address
6. THEN fires `create_order` with ALL items at once in `items[]` array
7. Bot shows order summary + payment details
8. Customer sends screenshot → `payment_received` intent + `set_payment_pending` + `notify_owner`

---

## Payment Methods — Important

Payment methods are stored at `user.payment_methods` (top-level on the user doc).
**NOT** under `user.settings.payment_methods`.

- `GET /business-knowledge` → reads from `user.payment_methods`
- `PUT /settings` with `{payment_methods: [...]}` → saves to `user.payment_methods` (top-level)
- `context_loader._build_business_config()` → reads from `user.payment_methods`

The AI is instructed: **NEVER invent payment details. Show only what is configured. If none configured, tell customer the owner will share details.**

---

## Push Notifications

`engine.py` has a standalone `_send_push_notification(db, user_id, title, body, data)` function (avoids circular import with server.py). Uses Expo push API.

Triggers:
- `notify_owner` with `reason=payment_received` → 💰 "Payment Received — CustomerName"
- `notify_owner` with `reason=escalation/complaint` → ⚠️ "Customer Needs Attention"
- `escalate=true` in AI response → 🚨 "Escalation — CustomerName"
- Any other `notify_owner` → 🔔 "Alert — CustomerName"

---

## Multi-Provider AI Support

The engine uses `AIMessageDrafter` from `ai_service.py` via `_get_drafter()` singleton.
Business owners set `user.settings.ai_model` to one of:

| Setting | Provider | Model |
|---------|----------|-------|
| `standard` | OpenAI | gpt-4o-mini |
| `premium` | OpenAI | gpt-4o |
| `claude` | Anthropic (HTTP) | claude-3-5-sonnet |
| `grok` | xAI | grok-3 |
| `deepseek` | DeepSeek | deepseek-chat |
| `gpt-5` | OpenAI | gpt-5 |

Claude is called via direct HTTP (httpx) — not the Anthropic SDK — because only `openai` SDK is in requirements.txt.

Temperature is set to `0.4` for all OpenAI-compatible providers to keep JSON responses consistent. Grok-4 and GPT-5 use `max_completion_tokens` instead of `max_tokens`.

---

## Business Types Supported

Prompt instructions are config-driven per business type. Each type in `_BUSINESS_INSTRUCTIONS` dict:

**Order types** (use products + create_order): retail, wholesale, restaurant, food, bakery, grocery
**Booking types** (use services + create_booking): salon, beauty, spa, services, repair, cleaning, clinic, photography, events, gym, rental
**Both**: restaurant

Unknown types fall back to `_DEFAULT_INSTRUCTIONS`.

---

## Order Schema (autoreply-created)

Orders created by the bot differ from manually-created orders:

| Field | Autoreply | Manual |
|-------|-----------|--------|
| Product | `product_name` + `items[]` | `product` (string) |
| Price | `total_amount` / `total` | `price` + `total_amount` |
| Status | `status` ("pending") | `delivery_status` ("Processing") |
| Extra | `order_number`, `delivery_type`, `delivery_address`, `created_by: "customer"` | — |

`GET /orders` handles both schemas with `.get()` fallbacks. `OrderResponse` includes optional fields for all autoreply fields (`order_number`, `items`, `delivery_type`, etc.).

---

## How server.py Calls the Engine

In `server.py`, after all gates (owner pause, opt-out, not own number), the v2 engine is called:

```python
from autoreply.engine import process_message as _v2_process

return await _v2_process(
    db=db,
    user=user,
    customer=customer,
    customer_id=customer_id,
    message=body,
    from_number=from_number,
    whatsapp_service=_ws_v2,
)
```

Returns `{"status": "ok", "handled_by": "autoreply_v2"}` on success or `{"status": "error", ...}` on fatal failure (fallback reply still sent to customer).

---

## Prompt Injection Protection

`context_loader._sanitize()` strips injection patterns from all catalog and config fields before they reach the system prompt:

```python
re.sub(r'\b(ignore|forget|disregard|override|system\s*prompt|instruction|jailbreak)\b', "***", text)
```

Applied to: product names, categories, descriptions, business name, hours, delivery info, FAQs, offers.

---

## Known Limitations / Future Work

- Order summary in AI reply doesn't include order number (order is created after AI responds). Workaround: engine appends `🧾 Order #: ORD-XXXXXX` to the reply after action execution.
- `send_catalog_images` is capped at 8 products per batch. Customer can reply "0" or "more" for the next batch — but the engine doesn't yet auto-track which batch was last sent (AI tracks this via conversation history).
- Escalation push and `notify_owner` push can double-fire if both `escalate=true` AND `notify_owner` action are in the same response. Acceptable for now.

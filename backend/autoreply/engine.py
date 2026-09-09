"""
engine.py — autoreply v2 main entry point.

Uses the existing AIMessageDrafter infrastructure so it works with
whatever AI provider + model the business owner has chosen:
  standard  → default provider (OpenAI gpt-4o-mini, DeepSeek, etc.)
  premium   → gpt-4o
  claude    → Anthropic Claude (via HTTP)
  grok      → xAI Grok
  deepseek  → DeepSeek
  gpt-5     → GPT-5

Mini-state (durable fields in conversation_states):
  active_flow:      "ordering" | "booking" | "browsing" | None
  flow_product_id:  str | None
  flow_step:        "awaiting_qty" | "awaiting_address" | "awaiting_date" | "awaiting_payment" | None
  last_menu:        {"1": {id, name, price, type}, ...} | None
  last_menu_at:     datetime  (2hr TTL)
  flow_data:        the confirmed cart / fulfilment / booking snapshot
  escalated:        bool
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .context_loader import load_context
from .prompt_builder import build_system_prompt
from .action_handler import execute_actions

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I'm having a little trouble right now. Please send your message again! 🙏"
MAX_RETRIES = 2


def _infer_reply_channel(customer: Optional[dict], from_number: str) -> str:
    """Detect social channel for tone (Instagram vs LinkedIn vs WhatsApp)."""
    ch = ((customer or {}).get("channel") or (customer or {}).get("source") or "").strip().lower()
    if ch:
        return ch
    fn = (from_number or "").strip().lower()
    if "instagram" in fn:
        return "instagram"
    if "linkedin" in fn:
        return "linkedin"
    if "facebook" in fn or "messenger" in fn:
        return "facebook"
    if fn.startswith("meta_"):
        parts = fn.split("_")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return "whatsapp"


async def _send_push_notification(db, user_id, title: str, body: str, data: dict = None) -> None:
    """Send Expo push notification to all devices registered for this user."""
    import httpx
    try:
        user = await db.users.find_one({"_id": user_id})
        if not user:
            return
        tokens = user.get("push_tokens", [])
        if not tokens:
            return
        messages = [
            {"to": t, "title": title, "body": body, "data": data or {}, "sound": "default", "priority": "high"}
            for t in tokens
            if t.startswith("ExponentPushToken") or t.startswith("ExpoPushToken")
        ]
        if not messages:
            return
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                "https://exp.host/--/api/v2/push/send",
                json=messages,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
        logger.info(f"[AutoReplyV2] Push sent to {len(messages)} device(s): {resp.status_code}")
    except Exception as exc:
        logger.warning(f"[AutoReplyV2] Push notification failed: {exc}")

# Singleton drafter — created once, reused across requests
_drafter = None


def _get_drafter():
    global _drafter
    if _drafter is None:
        from ai_service import AIMessageDrafter
        _drafter = AIMessageDrafter()
    return _drafter


# ── Public entry point ────────────────────────────────────────────────────────

async def process_message(
    db,
    user: dict,
    customer: dict,
    customer_id,
    message: str,
    from_number: str,
    whatsapp_service,
) -> dict:
    """
    Main autoreply v2 engine.
    Called from server.py after all gates pass (owner pause, opt-out, etc.)
    """
    user_id = user["_id"]
    customer_name = (customer or {}).get("name", "") if customer else ""
    # Respect the business owner's AI model choice
    model_pref = (user.get("settings") or {}).get("ai_model", "standard") or "standard"

    try:
        # 1. Load context (with message-aware WC search)
        ctx = await load_context(db, user_id, customer_id, user, message=message)

        # 2. Build system prompt
        reply_channel = _infer_reply_channel(customer, from_number)
        system_prompt = build_system_prompt(
            business_config=ctx["business_config"],
            products=ctx["products"],
            services=ctx["services"],
            mini_state=ctx["mini_state"],
            reply_channel=reply_channel,
        )

        # 3. Build conversation messages.  Numbered replies are resolved from
        # the stored menu before they reach the model, so "1" stays attached
        # to the exact item the customer saw even after an interruption.
        trusted_event = _trusted_flow_event(ctx, message)
        conv_messages = _build_conv_messages(ctx["messages"], message, trusted_event)

        # 4. Call AI with validation + retry
        response_data = await _call_ai_with_retry(system_prompt, conv_messages, model_pref)
        _apply_durable_action_facts(response_data, ctx.get("mini_state") or {}, trusted_event)
        _apply_trusted_actions(response_data, trusted_event)

        # 5. Execute CRM actions
        actions = response_data.get("actions", [])
        action_results = await execute_actions(
            db=db,
            actions=actions,
            user_id=user_id,
            customer_id=customer_id,
            user=user,
        )

        # 6. Handle escalation + push notifications to owner
        if response_data.get("escalate"):
            await _mark_needs_human(
                db, customer_id,
                response_data.get("escalate_reason", "Escalated by bot"),
            )

        # Push notification for payment received or escalation
        for action in actions:
            atype = action.get("type")
            reason = action.get("reason", "")
            if atype == "notify_owner":
                if reason == "payment_received":
                    await _send_push_notification(
                        db, user_id,
                        title=f"💰 Payment Received — {customer_name or from_number}",
                        body=action.get("message", "Customer confirmed payment — check order to verify"),
                        data={"type": "payment_received", "customer_id": str(customer_id)},
                    )
                elif reason in ("escalation", "complaint"):
                    await _send_push_notification(
                        db, user_id,
                        title=f"⚠️ Customer Needs Attention — {customer_name or from_number}",
                        body=action.get("message", "Customer requested human support"),
                        data={"type": "escalation", "customer_id": str(customer_id)},
                    )
                else:
                    await _send_push_notification(
                        db, user_id,
                        title=f"🔔 Alert — {customer_name or from_number}",
                        body=action.get("message", reason or "Customer needs attention"),
                        data={"type": "notify_owner", "customer_id": str(customer_id)},
                    )

        if response_data.get("escalate"):
            await _send_push_notification(
                db, user_id,
                title=f"🚨 Escalation — {customer_name or from_number}",
                body=response_data.get("escalate_reason", "Customer requested human support"),
                data={"type": "escalation", "customer_id": str(customer_id)},
            )

        # 7. Update mini-state — skip on fallback so flow is preserved
        if not response_data.get("_is_fallback"):
            await _update_mini_state(
                db, user_id, customer_id, response_data,
                existing_state=ctx.get("mini_state") or {},
                trusted_event=trusted_event,
            )

        # 8. Send images BEFORE the text reply
        # Build product lookup from loaded catalog
        products_by_id = {p["id"]: p for p in ctx.get("products", [])}

        async def _send_product_images(product: dict, caption: str) -> None:
            """
            Send all images for a product:
              - Extra angles (all but last) → no caption
              - Last image → with caption (name + price)
            """
            images = product.get("images") or []
            if not images and product.get("image_url"):
                images = [product["image_url"]]
            if not images:
                return
            # Extra angles — no caption
            for img_url in images[:-1]:
                try:
                    await whatsapp_service.send_message(
                        user_id=user_id,
                        to_number=from_number,
                        message="",
                        customer_name=customer_name,
                        send_context="auto_reply",
                        media_url=img_url,
                    )
                    await asyncio.sleep(0.7)
                except Exception as img_err:
                    logger.warning(f"[AutoReplyV2] Failed to send extra angle: {img_err}")
            # Last image WITH caption
            try:
                await whatsapp_service.send_message(
                    user_id=user_id,
                    to_number=from_number,
                    message=caption,
                    customer_name=customer_name,
                    send_context="auto_reply",
                    media_url=images[-1],
                )
                await asyncio.sleep(0.5)
            except Exception as img_err:
                logger.warning(f"[AutoReplyV2] Failed to send captioned image: {img_err}")

        for action in actions:
            atype = action.get("type")

            if atype == "send_product_image":
                # Scenario 1: customer selected a specific product
                product = products_by_id.get(action.get("product_id", ""))
                if product:
                    caption = action.get("caption") or f"{product['name']} — {(user.get('settings') or {}).get('currency', 'KES')} {product['price']:,.0f}"
                    await _send_product_images(product, caption)
                elif action.get("image_url"):
                    # Fallback: AI provided URL directly (no extra angles)
                    try:
                        await whatsapp_service.send_message(
                            user_id=user_id,
                            to_number=from_number,
                            message=action.get("caption", ""),
                            customer_name=customer_name,
                            send_context="auto_reply",
                            media_url=action["image_url"],
                        )
                        await asyncio.sleep(0.8)
                    except Exception as img_err:
                        logger.warning(f"[AutoReplyV2] Failed to send product image: {img_err}")

            elif atype == "send_catalog_images":
                # Scenario 2: customer browsing catalog — 8 products per batch, numbered captions
                currency = (user.get("settings") or {}).get("currency", "KES")
                _EMOJI_NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
                product_ids     = action.get("product_ids") or []
                category_filter = (action.get("category") or "").strip().lower()

                # Build ordered batch of products that have images
                batch: List[dict] = []
                if product_ids:
                    for pid in product_ids:
                        product = products_by_id.get(str(pid))
                        if not product:
                            continue
                        if category_filter and product.get("category", "").lower() != category_filter:
                            continue
                        if product.get("images") or product.get("image_url"):
                            batch.append(product)
                        if len(batch) >= 8:
                            break
                else:
                    # No IDs given — scan all loaded products (filtered by category if set)
                    for product in products_by_id.values():
                        if not (product.get("images") or product.get("image_url")):
                            continue
                        if category_filter and product.get("category", "").lower() != category_filter:
                            continue
                        batch.append(product)
                        if len(batch) >= 8:
                            break

                if batch:
                    for i, product in enumerate(batch):
                        num     = _EMOJI_NUMS[i] if i < len(_EMOJI_NUMS) else f"{i + 1}."
                        caption = f"{num} {product['name']} — {currency} {product['price']:,.0f}"
                        await _send_product_images(product, caption)
                        await asyncio.sleep(1.5)
                else:
                    # Legacy fallback: AI provided products list with image_url
                    img_items = [p for p in (action.get("products") or []) if p.get("image_url")]
                    for i, img in enumerate(img_items[:8]):
                        num = _EMOJI_NUMS[i] if i < len(_EMOJI_NUMS) else f"{i + 1}."
                        try:
                            await whatsapp_service.send_message(
                                user_id=user_id,
                                to_number=from_number,
                                message=f"{num} {img.get('caption', '')}".strip(),
                                customer_name=customer_name,
                                send_context="auto_reply",
                                media_url=img["image_url"],
                            )
                            await asyncio.sleep(1.0)
                        except Exception as img_err:
                            logger.warning(f"[AutoReplyV2] Failed to send catalog image: {img_err}")

        # 9. Send text reply.  A shop link is opt-in: catalog browsing should
        # stay inside WhatsApp unless the customer asks for the full web shop.
        storefront_url = None
        storefront_was_requested = any(
            action.get("type") == "share_storefront"
            for action in actions
            if isinstance(action, dict)
        )
        if storefront_was_requested:
            try:
                from storefront_routes import public_storefront_url_for_user
                storefront_url = await public_storefront_url_for_user(db, user)
            except Exception as exc:
                logger.warning("[AutoReplyV2] Could not add storefront link: %s", exc)

        reply_text = (response_data.get("reply") or "").strip() or FALLBACK_REPLY
        if action_results.get("order_number"):
            reply_text += f"\n\n🧾 *Order #:* {action_results['order_number']}"
            # Businesses that set up online payment can be paid here and now.
            # Those that have not are left exactly as they were: a total, and
            # the owner collecting it their own way.
            try:
                from chat_checkout import checkout_link_for_order
                _order = await db.orders.find_one(
                    {"user_id": user_id, "order_number": action_results["order_number"]}
                )
                if _order:
                    _pay = await checkout_link_for_order(
                        db, user, _order, customer=customer, phone=from_number
                    )
                    if _pay:
                        reply_text += "\n\n\U0001f4b3 Pay now:\n" + _pay
            except Exception as exc:
                logger.warning("[AutoReplyV2] no checkout link: %s", exc)
        if storefront_url:
            reply_text += f"\n\n🛍️ Browse the full catalog & pay online:\n{storefront_url}"
        is_fallback = response_data.get("_is_fallback", False)
        await whatsapp_service.send_message(
            user_id=user_id,
            to_number=from_number,
            message=reply_text,
            customer_name=customer_name,
            send_context="fallback" if is_fallback else "auto_reply",
        )

        logger.info(
            f"[AutoReplyV2] ✓ {from_number} | model={model_pref} "
            f"intent={response_data.get('intent')} sentiment={response_data.get('sentiment')} "
            f"escalate={response_data.get('escalate')} "
            f"actions={[a.get('type') for a in response_data.get('actions', [])]}"
        )
        return {"status": "ok", "handled_by": "autoreply_v2"}

    except Exception as exc:
        logger.error(f"[AutoReplyV2] Fatal error for {from_number}: {exc}", exc_info=True)
        try:
            await whatsapp_service.send_message(
                user_id=user_id,
                to_number=from_number,
                message=FALLBACK_REPLY,
                customer_name=customer_name,
                send_context="fallback",  # tagged so context_loader excludes it from history
            )
        except Exception:
            pass
        return {"status": "error", "handled_by": "autoreply_v2"}


# ── Durable commerce state ───────────────────────────────────────────────────

_NUMBERED_REPLY = re.compile(r"^\s*(?:#\s*)?([0-8])(?:[.)])?\s*$")
_FLOW_TEXT_FIELDS = (
    "selected_category", "delivery_type", "delivery_address", "table_number",
    "date", "time", "address", "checkin_date", "checkout_date", "notes",
    "last_choice",
)


def _short_text(value: Any, limit: int = 240) -> str:
    """Return bounded plain text before it is stored as durable flow state."""
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _safe_flow_data(value: Any) -> Dict[str, Any]:
    """Keep only bounded, non-sensitive checkout facts in conversation state."""
    if not isinstance(value, dict):
        return {}

    safe: Dict[str, Any] = {}
    selected = value.get("selected_item")
    if isinstance(selected, dict):
        selected_id = _short_text(selected.get("id"), 120)
        selected_name = _short_text(selected.get("name"), 160)
        selected_type = _short_text(selected.get("type"), 24).lower()
        if selected_id and selected_name and selected_type in {"product", "service"}:
            safe["selected_item"] = {
                "id": selected_id,
                "name": selected_name,
                "type": selected_type,
            }

    if "cart" in value and isinstance(value.get("cart"), list):
        cart = []
        for raw_item in value["cart"][:25]:
            if not isinstance(raw_item, dict):
                continue
            product_id = _short_text(raw_item.get("product_id"), 120)
            product_name = _short_text(raw_item.get("product_name"), 160)
            if not product_id or not product_name:
                continue
            try:
                quantity = max(1, min(int(raw_item.get("quantity") or 1), 999))
            except (TypeError, ValueError):
                quantity = 1
            item: Dict[str, Any] = {
                "product_id": product_id,
                "product_name": product_name,
                "quantity": quantity,
            }
            variant = _short_text(raw_item.get("variant"), 100)
            if variant:
                item["variant"] = variant
            modifiers = []
            for raw_modifier in (raw_item.get("modifiers") or [])[:12]:
                if not isinstance(raw_modifier, dict):
                    continue
                group = _short_text(raw_modifier.get("group"), 100)
                choice = _short_text(raw_modifier.get("choice"), 100)
                if group and choice:
                    modifiers.append({"group": group, "choice": choice})
            if modifiers:
                item["modifiers"] = modifiers
            cart.append(item)
        safe["cart"] = cart

    for field in _FLOW_TEXT_FIELDS:
        if field in value:
            text = _short_text(value.get(field), 500 if field in {"delivery_address", "address", "notes"} else 160)
            if text:
                safe[field] = text
    return safe


def _merge_flow_data(current: Any, incoming: Any) -> Dict[str, Any]:
    """Merge a partial AI update without losing confirmed earlier details."""
    merged = _safe_flow_data(current)
    update = _safe_flow_data(incoming)
    for key, value in update.items():
        # A model that answers an unrelated question may return an empty cart
        # object.  Empty output is never evidence that the customer discarded
        # a real cart, so retain the confirmed cart until it is explicitly
        # changed in a later commerce step.
        if key == "cart" and not value and merged.get("cart"):
            continue
        if key == "selected_item" and isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _find_catalog_item(ctx: Dict[str, Any], item_id: str, item_type: str) -> Optional[Dict[str, Any]]:
    source = ctx.get("services", []) if item_type == "service" else ctx.get("products", [])
    return next((item for item in source if str(item.get("id")) == str(item_id)), None)


def _trusted_flow_event(ctx: Dict[str, Any], message: str) -> Optional[Dict[str, Any]]:
    """Resolve a bare numbered reply against the menu the backend previously sent.

    The event is generated from server-side state, not guessed by the model.
    Natural-language messages continue to go straight to V2 unchanged.
    """
    state = ctx.get("mini_state") or {}
    words = (message or "").strip().lower()
    if any(phrase in words for phrase in ("website", "web shop", "webshop", "catalog link", "shop link", "online checkout", "send me the link")):
        return {
            "kind": "storefront_request",
            "note": "The customer explicitly requested the website/full catalog link. Use share_storefront.",
            "state": {},
        }
    match = _NUMBERED_REPLY.match(message or "")
    if not match:
        return None
    number = match.group(1)
    flow_step = (state.get("flow_step") or "").lower()
    flow_data = _safe_flow_data(state.get("flow_data"))

    # At this point a number is a quantity, not a second menu selection.
    if flow_step in {"awaiting_qty", "awaiting_quantity"} and number != "0":
        selected = flow_data.get("selected_item") or {}
        if selected.get("type") == "product":
            quantity = int(number)
            cart = list(flow_data.get("cart") or [])
            matching = next((item for item in cart if item.get("product_id") == selected.get("id")), None)
            if matching:
                matching["quantity"] = quantity
            else:
                cart.append({
                    "product_id": selected["id"],
                    "product_name": selected["name"],
                    "quantity": quantity,
                })
            return {
                "kind": "quantity",
                "note": (
                    f"The customer gave the quantity {quantity} for the selected product "
                    f"{selected['name']} (ID {selected['id']}). This is a confirmed quantity, not a menu choice."
                ),
                "state": {
                    "active_flow": "ordering",
                    "flow_step": "awaiting_delivery",
                    "flow_data": {"cart": cart},
                },
            }

    menu = state.get("last_menu") or {}
    item = menu.get(number)
    if not isinstance(item, dict):
        return None

    item_id = _short_text(item.get("id"), 120)
    item_name = _short_text(item.get("name"), 160)
    item_type = _short_text(item.get("type"), 24).lower()
    if not item_id or not item_name:
        return None

    if item_type in {"product", "service"}:
        catalog_item = _find_catalog_item(ctx, item_id, item_type) or {}
        if item_type == "service":
            next_step = "awaiting_date"
            active_flow = "booking"
        else:
            has_options = bool(catalog_item.get("variants") or catalog_item.get("modifier_groups"))
            next_step = "awaiting_options" if has_options else "awaiting_qty"
            active_flow = "ordering"
        return {
            "kind": "menu_item",
            "note": (
                f"The customer selected menu item {number}: {item_type} {item_name} (ID {item_id}). "
                "Treat this as an exact confirmed selection, not an ambiguous number."
            ),
            "state": {
                "active_flow": active_flow,
                "flow_product_id": item_id,
                "flow_step": next_step,
                "flow_data": {
                    "selected_item": {"id": item_id, "name": item_name, "type": item_type},
                },
                "clear_menu": True,
            },
            "force_actions": (
                [{"type": "send_product_image", "product_id": item_id}]
                if catalog_item.get("images") or catalog_item.get("image_url")
                else []
            ),
        }

    if item_type == "category":
        return {
            "kind": "category",
            "note": f"The customer selected the exact category {item_name}. Show only its matching items next.",
            "state": {
                "active_flow": "browsing",
                "flow_step": "choosing_item",
                "flow_data": {"selected_category": item_name},
                "clear_menu": True,
            },
        }

    if item_type == "catalog":
        return {
            "kind": "storefront_request",
            "note": "The customer selected View all products. Share the full catalog link and let them keep their current WhatsApp conversation state.",
            "force_actions": ["share_storefront"],
            "state": {},
        }

    return {
        "kind": "option",
        "note": f"The customer selected the exact option {item_name} (ID {item_id}). Keep the current flow and apply it.",
        "state": {"flow_data": {"last_choice": item_name}, "clear_menu": True},
    }


def _apply_trusted_actions(response_data: Dict[str, Any], trusted_event: Optional[Dict[str, Any]]) -> None:
    """Ensure backend-confirmed customer choices cause their required action.

    V2 still writes the friendly reply, but it cannot accidentally omit a
    catalog link the customer explicitly selected or an image for the exact
    product they chose from a stored menu.
    """
    if not trusted_event:
        return
    actions = response_data.get("actions")
    if not isinstance(actions, list):
        actions = []
        response_data["actions"] = actions

    for forced in trusted_event.get("force_actions") or []:
        forced_action = {"type": forced} if isinstance(forced, str) else forced
        if not isinstance(forced_action, dict) or not forced_action.get("type"):
            continue
        exists = any(
            isinstance(action, dict)
            and action.get("type") == forced_action["type"]
            and (
                forced_action["type"] != "send_product_image"
                or action.get("product_id") == forced_action.get("product_id")
            )
            for action in actions
        )
        if not exists:
            actions.append(forced_action)

    if trusted_event.get("kind") == "storefront_request" and response_data.get("_is_fallback"):
        response_data["reply"] = "Here is the full catalog. You can browse everything there, or continue chatting with me here anytime."


def _apply_durable_action_facts(
    response_data: Dict[str, Any],
    existing_state: Dict[str, Any],
    trusted_event: Optional[Dict[str, Any]],
) -> None:
    """Carry confirmed commerce facts into an order or booking action.

    The model still chooses the natural wording and decides when the customer
    has confirmed.  Once it creates a real CRM record, however, previously
    confirmed items and details must not disappear merely because an earlier
    message fell outside the conversation-history window.
    """
    snapshot = _safe_flow_data(existing_state.get("flow_data"))
    event_state = (trusted_event or {}).get("state") or {}
    if isinstance(event_state, dict) and "flow_data" in event_state:
        snapshot = _merge_flow_data(snapshot, event_state.get("flow_data"))
    ai_flow_update = response_data.get("flow_update") or {}
    if isinstance(ai_flow_update, dict) and "flow_data" in ai_flow_update:
        snapshot = _merge_flow_data(snapshot, ai_flow_update.get("flow_data"))
    if not snapshot:
        return

    actions = response_data.get("actions")
    if not isinstance(actions, list):
        return

    saved_cart = snapshot.get("cart") or []
    selected = snapshot.get("selected_item") or {}
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type == "create_order":
            action_items = action.get("items")
            if not isinstance(action_items, list):
                action_items = []
                action["items"] = action_items
            indexed = {
                str(item.get("product_id") or ""): item
                for item in action_items
                if isinstance(item, dict) and item.get("product_id")
            }
            for saved_item in saved_cart:
                product_id = str(saved_item.get("product_id") or "")
                if not product_id:
                    continue
                target = indexed.get(product_id)
                if target is None:
                    target = {
                        "product_id": product_id,
                        "product_name": saved_item.get("product_name", ""),
                        "quantity": saved_item.get("quantity", 1),
                    }
                    action_items.append(target)
                    indexed[product_id] = target
                # The state is created from a confirmed choice/quantity, so
                # it outranks a model omission.  Catalog pricing is still
                # recalculated by action_handler.py.
                target["quantity"] = saved_item.get("quantity", target.get("quantity", 1))
                if saved_item.get("variant") and not target.get("variant"):
                    target["variant"] = saved_item["variant"]
                if saved_item.get("modifiers") and not target.get("modifiers"):
                    target["modifiers"] = saved_item["modifiers"]

            if snapshot.get("delivery_type"):
                action["delivery_type"] = snapshot["delivery_type"]
            if snapshot.get("delivery_address") and not action.get("delivery_address"):
                action["delivery_address"] = snapshot["delivery_address"]
            if snapshot.get("table_number") and not action.get("table_number"):
                action["table_number"] = snapshot["table_number"]

        elif action_type == "create_booking":
            if selected.get("type") == "service":
                if not action.get("service_id"):
                    action["service_id"] = selected.get("id", "")
                if not action.get("service_name"):
                    action["service_name"] = selected.get("name", "")
            for field in ("date", "time", "checkin_date", "checkout_date", "notes"):
                if snapshot.get(field) and not action.get(field):
                    action[field] = snapshot[field]


# ── AI call ───────────────────────────────────────────────────────────────────

def _build_conv_messages(
    history: List[Dict],
    current_message: str,
    trusted_event: Optional[Dict[str, Any]] = None,
) -> List[Dict]:
    """Convert stored messages to API format and add an internal trusted flow event."""
    messages = []
    for m in history:
        role = "user" if m["role"] == "customer" else "assistant"
        content = (m.get("content") or "").strip()
        if content:
            messages.append({"role": role, "content": content})
    content = current_message
    if trusted_event and trusted_event.get("note"):
        content += f"\n\n[TRUSTED FLOW EVENT — backend-confirmed: {trusted_event['note']}]"
    messages.append({"role": "user", "content": content})
    return messages


async def _call_ai_with_retry(
    system_prompt: str,
    messages: List[Dict],
    model_pref: str,
) -> Dict[str, Any]:
    """
    Call the AI using AIMessageDrafter's provider routing.
    Retries once with an explicit correction prompt on JSON failure.
    Falls back to a safe default on second failure.
    """
    drafter = _get_drafter()
    client_type, model_name, client = drafter._get_client_and_model(model_pref)

    # If no client available, try default provider
    if not client:
        logger.warning(f"[AutoReplyV2] Provider '{model_pref}' not available, using default")
        client_type, model_name, client = drafter._get_default_client_and_model()

    if not client:
        raise RuntimeError("No AI provider configured — add API key to environment")

    attempt_messages = messages.copy()
    raw = ""
    # A configured provider that starts failing — no credit, a dead key, a
    # response shape we cannot read — must not end the conversation. Once,
    # and only once, move to the default model before apologising to the
    # customer. Switching only happens if we are not already on it.
    switched_to_default = False

    def _switch_to_default():
        """Return the default provider, or None if it is what we are using."""
        fb_type, fb_model, fb_client = drafter._get_default_client_and_model()
        if not fb_client or (fb_type, fb_model) == (client_type, model_name):
            return None
        return fb_type, fb_model, fb_client

    for attempt in range(MAX_RETRIES):
        try:
            raw = await _call_provider(client_type, client, model_name, system_prompt, attempt_messages)
            data = _parse_and_validate(raw)
            return data

        except _ValidationError as exc:
            # Log the FULL raw response so it's visible in Render logs
            logger.error(
                f"[AutoReplyV2] ❌ VALIDATION FAILED attempt {attempt + 1}/{MAX_RETRIES}\n"
                f"Error: {exc}\n"
                f"RAW RESPONSE FROM AI:\n{'='*60}\n{raw}\n{'='*60}"
            )
            if attempt < MAX_RETRIES - 1:
                attempt_messages = attempt_messages + [
                    {"role": "assistant", "content": raw or ""},
                    {"role": "user", "content": (
                        "Your previous response was not valid JSON or was missing required fields. "
                        "Reply with ONLY a valid JSON object containing: reply, intent, sentiment, actions, escalate, escalate_reason, new_menu, flow_update. "
                        "Include send_product_image or send_catalog_images in actions if a product was selected or catalog was requested. "
                        "No text before or after. No markdown code blocks."
                    )},
                ]
                continue
            if not switched_to_default and (fb := _switch_to_default()):
                client_type, model_name, client = fb
                switched_to_default = True
                logger.warning(
                    f"[AutoReplyV2] {model_pref} kept returning unusable JSON — "
                    f"retrying on {model_name}"
                )
                # The retries are spent, so make the one attempt on the
                # default model here rather than looping again.
                try:
                    return _parse_and_validate(
                        await _call_provider(client_type, client, model_name,
                                             system_prompt, messages.copy())
                    )
                except Exception:
                    logger.error("[AutoReplyV2] default model also failed")
            logger.error("[AutoReplyV2] All retries exhausted — using fallback response")
            return _fallback_response()

        except Exception as exc:
            logger.error(
                f"[AutoReplyV2] ❌ AI CALL ERROR attempt {attempt + 1}/{MAX_RETRIES}: {exc}",
                exc_info=True,
            )
            if attempt < MAX_RETRIES - 1:
                continue
            if not switched_to_default and (fb := _switch_to_default()):
                client_type, model_name, client = fb
                switched_to_default = True
                logger.warning(
                    f"[AutoReplyV2] {model_pref} failed ({exc}) — retrying on {model_name}"
                )
                attempt_messages = messages.copy()
                raw = await _call_provider(client_type, client, model_name,
                                           system_prompt, attempt_messages)
                try:
                    return _parse_and_validate(raw)
                except Exception:
                    logger.error("[AutoReplyV2] default model also failed")
            return _fallback_response()

    return _fallback_response()


async def _call_provider(
    client_type: str,
    client,
    model_name: str,
    system_prompt: str,
    messages: List[Dict],
) -> str:
    """Call the correct provider with proper message format."""

    if client_type == "claude":
        # Anthropic via HTTP (client is a dict with key + endpoint)
        return await _call_claude_http(client, model_name, system_prompt, messages)
    else:
        # OpenAI-compatible: OpenAI, DeepSeek, Grok
        return await _call_openai_compat(client, model_name, system_prompt, messages)


async def _call_openai_compat(client, model_name: str, system_prompt: str, messages: List[Dict]) -> str:
    """Call OpenAI-compatible API (OpenAI, DeepSeek, Grok) with full message history."""
    api_messages = [{"role": "system", "content": system_prompt}] + messages

    is_grok_reasoning = model_name.startswith("grok-4")
    is_gpt5 = model_name.startswith("gpt-5")

    kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": api_messages,
    }
    if is_grok_reasoning:
        kwargs["max_completion_tokens"] = 1500
    elif is_gpt5:
        pass  # GPT-5 manages its own output length
    else:
        kwargs["max_tokens"] = 1500
        kwargs["temperature"] = 0.4   # lower temp → more consistent JSON
        # Force JSON output — prevents None/empty content from the API
        # Supported by gpt-4o, gpt-4o-mini, deepseek-chat, grok (non-reasoning)
        _JSON_OBJECT_MODELS = ("gpt-", "deepseek", "grok-3", "grok-2")
        if any(model_name.startswith(p) for p in _JSON_OBJECT_MODELS):
            kwargs["response_format"] = {"type": "json_object"}

    response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
    choice = response.choices[0]
    content = choice.message.content
    # Log refusals so they're visible in Render logs
    if content is None:
        refusal = getattr(choice.message, "refusal", None)
        finish = choice.finish_reason
        logger.error(
            f"[AutoReplyV2] OpenAI returned None content — finish_reason={finish} refusal={refusal}"
        )
        return ""
    return content


async def _call_claude_http(client_config: Dict, model_name: str, system_prompt: str, messages: List[Dict]) -> str:
    """Call Anthropic API via HTTP with full message history."""
    import httpx

    headers = {
        "x-api-key": client_config["key"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model_name,
        "max_tokens": 1500,
        "system": system_prompt,
        "messages": messages,
    }
    async with httpx.AsyncClient() as http:
        resp = await http.post(client_config["endpoint"], json=payload, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Claude API {resp.status_code}: {resp.text[:300]}")
        # Claude 4.7 and later can return a thinking block ahead of the
        # answer, so take the text blocks rather than the first one. Reading
        # content[0] raised KeyError on every reply, which the caller turned
        # into the "having a little trouble" fallback.
        data = resp.json()
        return "".join(
            c.get("text", "") for c in data.get("content", []) if c.get("type") == "text"
        )


# ── JSON validation ───────────────────────────────────────────────────────────

class _ValidationError(Exception):
    pass


def _parse_and_validate(raw: str) -> Dict[str, Any]:
    """Extract and validate JSON from the AI response."""
    text = raw.strip()

    # Strip markdown code block if the model wrapped it
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _ValidationError(f"JSON parse error: {exc}") from exc

    if not isinstance(data, dict):
        raise _ValidationError("Response is not a JSON object")

    reply = data.get("reply", "")
    if not isinstance(reply, str) or not reply.strip():
        raise _ValidationError("'reply' field is missing or empty")

    # Coerce intent / sentiment — don't raise, just default
    valid_intents = {"order", "booking", "inquiry", "complaint", "greeting",
                     "payment_received", "cancel", "reschedule", "other"}
    valid_sentiments = {"positive", "neutral", "negative", "angry"}
    if data.get("intent") not in valid_intents:
        data["intent"] = "other"
    if data.get("sentiment") not in valid_sentiments:
        data["sentiment"] = "neutral"
    if not isinstance(data.get("actions"), list):
        data["actions"] = []

    return data


def _fallback_response() -> Dict[str, Any]:
    return {
        "reply": FALLBACK_REPLY,
        "intent": "other",
        "sentiment": "neutral",
        "actions": [],
        "escalate": False,
        "escalate_reason": "",
        "new_menu": None,
        "flow_update": None,
        "_is_fallback": True,  # sentinel — engine skips state update on fallback
    }


# ── Mini-state update ─────────────────────────────────────────────────────────

async def _update_mini_state(
    db,
    user_id,
    customer_id,
    response_data: Dict,
    *,
    existing_state: Optional[Dict[str, Any]] = None,
    trusted_event: Optional[Dict[str, Any]] = None,
) -> None:
    if not customer_id:
        return

    update: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    flow_data = _safe_flow_data((existing_state or {}).get("flow_data"))

    # Save new menu if Claude/AI sent one this turn
    new_menu = response_data.get("new_menu")
    if new_menu and isinstance(new_menu, dict):
        update["last_menu"] = new_menu
        update["last_menu_at"] = datetime.utcnow()

    # Apply flow_update fields
    actions = response_data.get("actions") or []
    terminal_action = any(
        isinstance(action, dict)
        and action.get("type") in {"clear_flow", "create_order", "create_booking", "cancel_order", "cancel_booking"}
        for action in actions
    )

    flow_update = response_data.get("flow_update")
    if flow_update and isinstance(flow_update, dict):
        for field in ("active_flow", "flow_product_id", "flow_step"):
            # A blank AI field is not a customer cancellation.  Preserve an
            # unfinished state until a terminal action explicitly closes it.
            if field in flow_update and (flow_update[field] is not None or terminal_action):
                update[field] = flow_update[field]
        if "flow_data" in flow_update:
            flow_data = _merge_flow_data(flow_data, flow_update.get("flow_data"))

    # A bare numeric reply has already been matched to a server-stored menu.
    # Let that fact win over an AI interpretation of the same digit.
    event_state = (trusted_event or {}).get("state") or {}
    if isinstance(event_state, dict):
        for field in ("active_flow", "flow_product_id", "flow_step"):
            if field in event_state:
                update[field] = event_state[field]
        if "flow_data" in event_state:
            flow_data = _merge_flow_data(flow_data, event_state.get("flow_data"))
        # Keep a replacement menu the AI supplied (for example size options)
        # instead of clearing it after resolving the previous menu choice.
        if event_state.get("clear_menu") and not (new_menu and isinstance(new_menu, dict)):
            update["last_menu"] = {}
            update["last_menu_at"] = None

    if flow_data:
        update["flow_data"] = flow_data

    # clear_flow action wipes everything
    if terminal_action:
        update.update({
            "active_flow":     None,
            "flow_product_id": None,
            "flow_step":       None,
            "flow_data":       {},
            "last_menu":       {},
            "last_menu_at":    None,
        })

    if response_data.get("escalate"):
        update["escalated"] = True

    await db.conversation_states.update_one(
        {"user_id": user_id, "customer_id": customer_id},
        {"$set": update},
        upsert=True,
    )


async def _mark_needs_human(db, customer_id, reason: str) -> None:
    if not customer_id:
        return
    await db.customers.update_one(
        {"_id": customer_id},
        {"$set": {
            "needs_human":        True,
            "needs_human_reason": reason,
            "needs_human_at":     datetime.utcnow(),
        }},
    )
    logger.info(f"[AutoReplyV2] Escalated customer {customer_id}: {reason}")

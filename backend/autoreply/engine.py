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

Mini-state (5 fields in conversation_states):
  active_flow:      "ordering" | "booking" | "browsing" | None
  flow_product_id:  str | None
  flow_step:        "awaiting_qty" | "awaiting_address" | "awaiting_date" | "awaiting_payment" | None
  last_menu:        {"1": {id, name, price, type}, ...} | None
  last_menu_at:     datetime  (2hr TTL)
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
        # 1. Load context
        ctx = await load_context(db, user_id, customer_id, user)

        # 2. Build system prompt
        system_prompt = build_system_prompt(
            business_config=ctx["business_config"],
            products=ctx["products"],
            services=ctx["services"],
            mini_state=ctx["mini_state"],
        )

        # 3. Build conversation messages
        conv_messages = _build_conv_messages(ctx["messages"], message)

        # 4. Call AI with validation + retry
        response_data = await _call_ai_with_retry(system_prompt, conv_messages, model_pref)

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
            await _update_mini_state(db, user_id, customer_id, response_data)

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

        # 9. Send text reply — append order number if a new order was created
        reply_text = (response_data.get("reply") or "").strip() or FALLBACK_REPLY
        if action_results.get("order_number"):
            reply_text += f"\n\n🧾 *Order #:* {action_results['order_number']}"
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


# ── AI call ───────────────────────────────────────────────────────────────────

def _build_conv_messages(history: List[Dict], current_message: str) -> List[Dict]:
    """Convert stored messages to API message format, append current message."""
    messages = []
    for m in history:
        role = "user" if m["role"] == "customer" else "assistant"
        content = (m.get("content") or "").strip()
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": current_message})
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

    for attempt in range(MAX_RETRIES):
        try:
            raw = await _call_provider(client_type, client, model_name, system_prompt, attempt_messages)
            data = _parse_and_validate(raw)
            return data

        except _ValidationError as exc:
            # Log the FULL raw response so it's visible in Railway logs
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
            logger.error("[AutoReplyV2] All retries exhausted — using fallback response")
            return _fallback_response()

        except Exception as exc:
            logger.error(
                f"[AutoReplyV2] ❌ AI CALL ERROR attempt {attempt + 1}/{MAX_RETRIES}: {exc}",
                exc_info=True,
            )
            if attempt < MAX_RETRIES - 1:
                continue
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

    response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
    return response.choices[0].message.content or ""


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
        return resp.json()["content"][0]["text"]


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

async def _update_mini_state(db, user_id, customer_id, response_data: Dict) -> None:
    if not customer_id:
        return

    update: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    # Save new menu if Claude/AI sent one this turn
    new_menu = response_data.get("new_menu")
    if new_menu and isinstance(new_menu, dict):
        update["last_menu"] = new_menu
        update["last_menu_at"] = datetime.utcnow()

    # Apply flow_update fields
    flow_update = response_data.get("flow_update")
    if flow_update and isinstance(flow_update, dict):
        for field in ("active_flow", "flow_product_id", "flow_step"):
            if field in flow_update:
                update[field] = flow_update[field]

    # clear_flow action wipes everything
    actions = response_data.get("actions") or []
    if any(a.get("type") == "clear_flow" for a in actions):
        update.update({
            "active_flow":     None,
            "flow_product_id": None,
            "flow_step":       None,
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

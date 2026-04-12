"""
engine.py — autoreply v2 main entry point.

Replaces: router.py, conversation_state.py, sales_agent.py, order_agent.py,
          booking_agent.py, intent_analyzer.py, flow_judge.py

Flow per message:
  1. Load context (messages + mini-state + catalog + business config)
  2. Build system prompt (config-driven, business-type aware)
  3. Call Claude (claude-haiku for cost efficiency)
  4. Validate JSON response (Pydantic) — retry once on failure — fallback on second failure
  5. Execute CRM actions (orders, bookings, tags, escalations)
  6. Update mini-state (5 fields only)
  7. Send WhatsApp reply
  8. Log everything for debugging

Mini-state schema (stored in conversation_states collection):
  active_flow:      str | None   — "ordering" | "booking" | "browsing"
  flow_product_id:  str | None   — DB product/service ID
  flow_step:        str | None   — "awaiting_qty" | "awaiting_address" | "awaiting_date" | "awaiting_payment"
  last_menu:        dict | None  — {"1": {id, name, price, type}, ...}
  last_menu_at:     datetime     — for TTL check (2h expiry)
  escalated:        bool
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

from .context_loader import load_context
from .prompt_builder import build_system_prompt
from .action_handler import execute_actions

logger = logging.getLogger(__name__)

# Model: Haiku for cost efficiency (~$0.0001/message at 1000 tokens)
_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024
_MAX_RETRIES = 2

FALLBACK_REPLY = "Sorry, I didn't quite catch that. Could you please repeat?"

# Anthropic client — lazy init
_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic()
    return _client


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
    Main autoreply engine.
    Called from server.py after all gates pass (owner pause, opt-out, AI enabled, etc.)

    Returns {"status": "ok"|"error", "handled_by": "autoreply_v2"}
    """
    user_id = user["_id"]
    customer_name = (customer or {}).get("name", "") if customer else ""

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

        # 3. Build Claude message list (conversation history + current message)
        claude_messages = _build_claude_messages(ctx["messages"], message)

        # 4. Call Claude with validation + retry
        response_data = await _call_claude_with_retry(system_prompt, claude_messages)

        # 5. Execute CRM actions
        await execute_actions(
            db=db,
            actions=response_data.get("actions", []),
            user_id=user_id,
            customer_id=customer_id,
            user=user,
        )

        # 6. Handle escalation flag
        if response_data.get("escalate"):
            await _mark_needs_human(db, customer_id, response_data.get("escalate_reason", "Escalated by bot"))

        # 7. Update mini-state
        await _update_mini_state(db, user_id, customer_id, response_data)

        # 8. Send reply
        reply_text = (response_data.get("reply") or "").strip() or FALLBACK_REPLY
        await whatsapp_service.send_message(
            user_id=user_id,
            to_number=from_number,
            message=reply_text,
            customer_name=customer_name,
            send_context="auto_reply",
        )

        logger.info(
            f"[AutoReplyV2] ✓ {from_number} | intent={response_data.get('intent')} "
            f"sentiment={response_data.get('sentiment')} escalate={response_data.get('escalate')} "
            f"actions={[a.get('type') for a in response_data.get('actions', [])]}"
        )
        return {"status": "ok", "handled_by": "autoreply_v2"}

    except Exception as exc:
        logger.error(f"[AutoReplyV2] Fatal error for {from_number}: {exc}", exc_info=True)
        # Best-effort fallback reply so customer isn't left in silence
        try:
            await whatsapp_service.send_message(
                user_id=user_id,
                to_number=from_number,
                message=FALLBACK_REPLY,
                customer_name=customer_name,
                send_context="auto_reply",
            )
        except Exception:
            pass
        return {"status": "error", "handled_by": "autoreply_v2"}


# ── Claude call + validation ──────────────────────────────────────────────────

def _build_claude_messages(history: list, current_message: str) -> list:
    """Convert stored messages to Claude API format, append current message."""
    messages = []
    for m in history:
        role = "user" if m["role"] == "customer" else "assistant"
        content = (m.get("content") or "").strip()
        if content:
            messages.append({"role": role, "content": content})

    # Ensure messages alternate correctly (Claude requires user/assistant/user...)
    # If last message is also "user", merge or just append (Claude handles adjacent user turns in newer API)
    messages.append({"role": "user", "content": current_message})
    return messages


async def _call_claude_with_retry(system_prompt: str, messages: list) -> Dict[str, Any]:
    """
    Call Claude and validate the JSON response.
    Retries once with an explicit correction prompt.
    Falls back to a safe default on second failure.
    """
    client = _get_client()
    attempt_messages = messages.copy()

    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=_MAX_TOKENS,
                system=system_prompt,
                messages=attempt_messages,
            )

            raw = response.content[0].text.strip()
            data = _parse_and_validate(raw)
            return data

        except _ValidationError as exc:
            logger.warning(f"[AutoReplyV2] Validation failed attempt {attempt + 1}: {exc}")
            if attempt < _MAX_RETRIES - 1:
                # Inject correction turn so Claude knows what went wrong
                attempt_messages = attempt_messages + [
                    {"role": "assistant", "content": raw if "raw" in dir() else ""},
                    {"role": "user", "content": (
                        "Your response was not valid JSON or was missing required fields. "
                        "Reply with ONLY a valid JSON object matching the required schema. "
                        "No text before or after the JSON."
                    )},
                ]
                continue

            logger.error("[AutoReplyV2] All retries exhausted — using fallback response")
            return _fallback_response()

        except Exception as exc:
            logger.error(f"[AutoReplyV2] Claude API error attempt {attempt + 1}: {exc}", exc_info=True)
            if attempt < _MAX_RETRIES - 1:
                continue
            return _fallback_response()

    return _fallback_response()


class _ValidationError(Exception):
    pass


def _parse_and_validate(raw: str) -> Dict[str, Any]:
    """Extract JSON from Claude's response and validate required fields."""
    # Strip markdown code block if Claude wrapped the JSON
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    text = match.group(1) if match else raw

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _ValidationError(f"JSON parse error: {exc}") from exc

    if not isinstance(data, dict):
        raise _ValidationError("Response is not a JSON object")

    reply = data.get("reply", "")
    if not isinstance(reply, str) or not reply.strip():
        raise _ValidationError("'reply' field is missing or empty")

    # Coerce intent / sentiment to valid values (don't raise — just default)
    valid_intents = {"order", "booking", "inquiry", "complaint", "greeting", "payment_received", "cancel", "reschedule", "other"}
    valid_sentiments = {"positive", "neutral", "negative", "angry"}
    if data.get("intent") not in valid_intents:
        data["intent"] = "other"
    if data.get("sentiment") not in valid_sentiments:
        data["sentiment"] = "neutral"

    # Ensure actions is a list
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
    }


# ── Mini-state update ─────────────────────────────────────────────────────────

async def _update_mini_state(db, user_id, customer_id, response_data: Dict) -> None:
    """Persist the 5-field mini-state from Claude's response."""
    update: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    # Save new menu if Claude sent one this turn
    new_menu = response_data.get("new_menu")
    if new_menu and isinstance(new_menu, dict) and new_menu:
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

    # Escalation flag
    if response_data.get("escalate"):
        update["escalated"] = True

    if customer_id:
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

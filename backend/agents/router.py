import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from collections import defaultdict

from .intent_analyzer import analyze_intent, route_intent_to_agent, build_threaded_context, format_threaded_history
from .conversation_state import load_state, save_state, mark_escalated
from .reply_validator import validate_reply, RESULT_APPROVE, RESULT_REJECT, RESULT_ESCALATE
from .sales_agent import SalesAgent
from .order_agent import OrderAgent
from .payment_agent import PaymentAgent
from .complaint_agent import ComplaintAgent
from .chat_agent import ChatAgent
from .booking_agent import BookingAgent
from .session_summarizer import maybe_summarize, format_summary_for_prompt

logger = logging.getLogger(__name__)

MAX_VALIDATOR_RETRIES = 1

# 12.1: Intents that benefit from a more capable model
_HIGH_COMPLEXITY_INTENTS = {
    "COMPLAINT", "LEGAL_THREAT", "FRAUD_CLAIM",
    "NEGOTIATION", "DAMAGED_ITEM", "WRONG_ITEM",
    "REFUND_REQUEST", "ESCALATION",
}

# 12.5: Simple in-memory rate limiter (per user+customer pair)
_rate_store: Dict[str, List[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60   # seconds
_RATE_LIMIT_MAX = 5       # max messages per window


def _is_rate_limited(user_id: str, customer_id: str) -> bool:
    """Return True if this customer has sent too many messages recently."""
    key = f"{user_id}:{customer_id}"
    now = datetime.now(timezone.utc).timestamp()
    _rate_store[key] = [t for t in _rate_store[key] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_store[key]) >= _RATE_LIMIT_MAX:
        return True
    _rate_store[key].append(now)
    return False


def _get_model_for_intent(intent: str, sentiment: str) -> str:
    """12.1: Select model tier based on intent complexity and sentiment."""
    if sentiment in ("angry", "frustrated") or intent in _HIGH_COMPLEXITY_INTENTS:
        return "advanced"
    return "standard"


# 17: Multilingual word-to-number map for menu selection normalization
_SELECTION_MAP = {
    # Digits
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    # English words
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "the first": 1, "the second": 2, "the third": 3,
    "first one": 1, "second one": 2, "third one": 3,
    "option 1": 1, "option 2": 2, "option 3": 3, "option 4": 4, "option 5": 5,
    "number 1": 1, "number 2": 2, "number 3": 3,
    "no 1": 1, "no 2": 2, "no 3": 3, "no. 1": 1, "no. 2": 2, "no. 3": 3,
    "#1": 1, "#2": 2, "#3": 3, "#4": 4, "#5": 5,
    # Swahili
    "moja": 1, "mbili": 2, "tatu": 3, "nne": 4, "tano": 5,
    "ya kwanza": 1, "ya pili": 2, "ya tatu": 3,
    "chaguo 1": 1, "chaguo 2": 2, "chaguo 3": 3,
    # French
    "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    # Arabic-Indic digits
    "\u0661": 1, "\u0662": 2, "\u0663": 3, "\u0664": 4, "\u0665": 5,
}


def _normalize_selection(message: str):
    """17: Normalize a customer reply to a menu item number. Returns int or None."""
    cleaned = message.strip().lower()
    return _SELECTION_MAP.get(cleaned)


# 16.3: Business-critical intents that warrant owner notification
_BUSINESS_CRITICAL_INTENTS = {
    "COMPLAINT", "LEGAL_THREAT", "FRAUD_CLAIM",
    "PAYMENT_ISSUE", "REFUND_REQUEST", "ESCALATION",
    "DAMAGED_ITEM", "WRONG_ITEM",
}


def should_notify_owner(contact_signal: dict, intent: str) -> bool:
    """16.3: Only notify for business-critical situations. Never for personal contacts."""
    if contact_signal.get("type") == "personal":
        return False
    if intent in _BUSINESS_CRITICAL_INTENTS:
        return True
    return False


class Router:
    def __init__(self, db: Any):
        self.db = db

    async def _get_contact_state(self, customer_id: str, user_id: str) -> dict:
        """16.4: Load contact classification state from customer document."""
        if not customer_id or self.db is None:
            return {"contact_type": "UNKNOWN", "message_count": 0, "ai_enabled": True}
        try:
            doc = await self.db.customers.find_one(
                {"_id": customer_id, "user_id": user_id},
                {"contact_type": 1, "contact_type_source": 1, "message_count": 1, "ai_enabled": 1, "is_personal": 1}
            )
            if doc:
                return {
                    "contact_type": doc.get("contact_type", "UNKNOWN"),
                    "contact_type_source": doc.get("contact_type_source", "unknown"),
                    "message_count": doc.get("message_count", 0),
                    "ai_enabled": doc.get("ai_enabled", not doc.get("is_personal", False)),
                }
        except Exception as e:
            logger.error(f"[Router] _get_contact_state error: {e}")
        return {"contact_type": "UNKNOWN", "message_count": 0, "ai_enabled": True}

    async def _update_contact_state(self, customer_id: str, user_id: str, updates: dict) -> None:
        """16.4: Persist contact classification state on customer document."""
        if not customer_id or self.db is None:
            return
        try:
            updates["contact_state_updated_at"] = datetime.now(timezone.utc)
            await self.db.customers.update_one(
                {"_id": customer_id, "user_id": user_id},
                {"$set": updates}
            )
        except Exception as e:
            logger.error(f"[Router] _update_contact_state error: {e}")

    async def route_and_process(
        self, user_id: str, message: str, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Full pipeline:
          1. Build threaded context (relationship detection)
          2. Load conversation state (auto-resets if stale)
          3. Analyze intent (1 AI call, threaded context)
          4. Contact classification gate (16.2)
          5. Dispatch to correct agent
          6. Validate reply (fast rules, no LLM)
          7. Save state + flag for human if needed
        """
        customer_id = context.get("customer_id")
        is_personal = context.get("is_personal", False)
        history = context.get("history", [])
        business_knowledge = context.get("business_knowledge", "")
        customer_name = context.get("customer_name", "Customer")

        # ── 1. Build threaded context ─────────────────────────────────────
        threaded = build_threaded_context(history)
        context["_threaded"] = threaded
        context["_relationship"] = threaded.get("relationship", "new_conversation")
        context["_threaded_history_text"] = format_threaded_history(threaded)

        # ── 2. Load conversation state ────────────────────────────────────
        conv_state = await load_state(self.db, user_id, str(customer_id) if customer_id else "")
        context["conversation_state_data"] = conv_state

        # ── 2.5: Menu selection gate (17) ─────────────────────────────────
        # Check BEFORE intent analyzer — intercepts "One", "moja", "first", "ya kwanza" etc.
        if conv_state.get("waiting_for_selection") and conv_state.get("menu_items"):
            _sel = _normalize_selection(message)
            _menu_items = conv_state.get("menu_items", {})
            if _sel is not None and str(_sel) in _menu_items:
                _selected = _menu_items[str(_sel)]
                _menu_type = conv_state.get("menu_type", "product_selection")
                _lang = conv_state.get("preferred_language", "English") or "English"
                logger.info(f"[Router] Menu selection intercepted: '{message}' → {_sel} = {_selected.get('name')} (type={_menu_type})")
                # Clear menu state immediately
                if customer_id:
                    await save_state(self.db, user_id, str(customer_id), {
                        "active_menu": False, "waiting_for_selection": False,
                        "menu_items": {}, "menu_type": None,
                        "last_discussed_product": _selected.get("name"),
                    })
                # Build confirmation response based on menu type
                _name = _selected.get("name", "")
                _price = _selected.get("price", 0)
                _currency = context.get("currency", "")
                if _menu_type == "service_selection":
                    _dur = _selected.get("duration")
                    _dur_str = f" ({_dur} min)" if _dur else ""
                    _reply = (
                        f"Great choice! *{_name}*{_dur_str} — {_currency} {_price:,.0f}\n\n"
                        f"When would you like to book? Reply with your preferred date and time."
                    )
                else:
                    _reply = (
                        f"Great choice! *{_name}* — {_currency} {_price:,.0f}\n\n"
                        f"Would you like to:\n1️⃣  Order Now\n2️⃣  Add to Cart\n\n_Reply with 1 or 2_"
                    )
                return {
                    "handled": True, "escalated": False,
                    "messages": [{"text": _reply}],
                }
            elif _sel is None:
                # Unrelated reply — clear menu state, continue to intent analyzer
                if customer_id:
                    await save_state(self.db, user_id, str(customer_id), {
                        "active_menu": False, "waiting_for_selection": False,
                        "menu_items": {}, "menu_type": None,
                    })

        # ── 2.6: Rate limiting ─────────────────────────────────────────────
        if customer_id and _is_rate_limited(user_id, str(customer_id)):
            logger.warning(f"[Router] Rate limited: user={user_id} customer={customer_id}")
            return {
                "handled": True,
                "escalated": False,
                "messages": [{"text": "You're sending messages very quickly. Please wait a moment before trying again."}],
            }

        # ── 3. Analyze intent ─────────────────────────────────────────────
        classification = await analyze_intent(
            message=message,
            history=history,
            business_knowledge=business_knowledge,
            conversation_state=conv_state,
            customer_name=customer_name,
            is_personal=is_personal,
            business_type=context.get("business_type", ""),
        )

        intent = classification.get("intent", "UNKNOWN")
        sentiment = classification.get("sentiment", "neutral")
        language = classification.get("language", "English")
        confidence = float(classification.get("confidence", 0.5))
        needs_escalation = classification.get("needs_escalation", False)
        escalation_reason = classification.get("escalation_reason", "")
        relationship = classification.get("_relationship", "new_conversation")
        entities = classification.get("entities", {})
        alternative_intents = classification.get("alternative_intents", [])
        contact_signal = classification.get("contact_signal", {"type": "unclear", "confidence": 0.0, "reason": ""})

        # ── 3.5: Contact classification gate (16.2) ────────────────────────
        contact_state = await self._get_contact_state(str(customer_id) if customer_id else "", user_id)
        msg_count = contact_state.get("message_count", 0) + 1
        current_contact_type = contact_state.get("contact_type", "UNKNOWN")
        ai_enabled = contact_state.get("ai_enabled", True)

        # 16.5: If ai_enabled is False (personal contact, owner toggled off) → complete silence
        if not ai_enabled:
            logger.info(f"[Router] AI disabled for customer={customer_id} (personal contact)")
            await self._update_contact_state(str(customer_id) if customer_id else "", user_id, {"message_count": msg_count})
            return None

        sig_type = contact_signal.get("type", "unclear")
        sig_conf = float(contact_signal.get("confidence", 0.0))

        if current_contact_type == "UNKNOWN":
            if sig_type == "customer" and sig_conf >= 0.65:
                # Auto-tag as customer, continue pipeline normally
                logger.info(f"[Router] Auto-tagged customer={customer_id} as KNOWN_CUSTOMER")
                await self._update_contact_state(
                    str(customer_id) if customer_id else "", user_id,
                    {"contact_type": "KNOWN_CUSTOMER", "contact_type_source": "auto_detected",
                     "auto_detected_at_message": msg_count, "message_count": msg_count, "ai_enabled": True}
                )
                is_personal = False
                context["is_personal"] = False
            elif sig_type == "personal" and sig_conf >= 0.65:
                # Auto-tag as personal, go silent
                logger.info(f"[Router] Auto-tagged customer={customer_id} as KNOWN_PERSONAL — going silent")
                await self._update_contact_state(
                    str(customer_id) if customer_id else "", user_id,
                    {"contact_type": "KNOWN_PERSONAL", "contact_type_source": "auto_detected",
                     "auto_detected_at_message": msg_count, "message_count": msg_count,
                     "ai_enabled": False, "is_personal": True}
                )
                return None
            else:
                # Still unclear or low confidence
                if msg_count > 3:
                    # After 3 messages, if they STILL haven't proven to be a business contact, go silent
                    logger.info(f"[Router] Unknown contact reached message 4 — defaulting to KNOWN_PERSONAL and going silent")
                    await self._update_contact_state(
                        str(customer_id) if customer_id else "", user_id,
                        {"contact_type": "KNOWN_PERSONAL", "contact_type_source": "auto_detected_timeout",
                         "auto_detected_at_message": msg_count, "message_count": msg_count,
                         "ai_enabled": False, "is_personal": True}
                    )
                    return None

                await self._update_contact_state(
                    str(customer_id) if customer_id else "", user_id,
                    {"message_count": msg_count}
                )
                
                # At exactly 3 messages, send one natural clarifying question if unclear
                if msg_count == 3 and sig_type == "unclear":
                    logger.info(f"[Router] Unknown contact at 3 msgs — sending clarifying question")
                    return {
                        "handled": True,
                        "escalated": False,
                        "messages": [{"text": "What are you looking for today? 😊"}],
                    }
                # Within first 2 messages or if sig_type is personal with low confidence — respond naturally, continue pipeline
        else:
            # Known contact type — just update message count
            await self._update_contact_state(
                str(customer_id) if customer_id else "", user_id,
                {"message_count": msg_count}
            )
            # KNOWN_PERSONAL with ai_enabled=False already caught above
            if current_contact_type == "KNOWN_PERSONAL":
                is_personal = True
                context["is_personal"] = True

        # Expose contact_signal to downstream agents
        context["contact_signal"] = contact_signal

        # 1.6: Careful mode for low-confidence classifications
        careful_instruction = ""
        if confidence < 0.65 and not needs_escalation:
            context["careful_mode"] = True
            careful_instruction = (
                "Intent confidence is low. Read the customer message "
                "very carefully. If unsure, ask ONE clarifying question "
                "instead of assuming."
            )
            context["careful_instruction"] = careful_instruction

        # 12.1: Select AI model based on complexity
        selected_model = _get_model_for_intent(intent, sentiment)
        context["ai_model"] = selected_model

        # 14: Build business_config and inject into context
        business_config = {
            "business_id": user_id,
            "name": context.get("business_name", ""),
            "type": context.get("business_type", ""),
            "country": context.get("country", ""),
            "currency": context.get("currency", "USD"),
            "currency_symbol": context.get("currency_symbol", "$"),
            "primary_language": language,
            "payment_methods": context.get("payment_methods", []),
            "discount_policy": context.get("discount_policy", ""),
            "timezone": context.get("timezone", "UTC"),
            "escalation_contact": context.get("escalation_contact", ""),
            "booking_or_catalog": "booking" if context.get("business_type", "") in {
                "salon", "spa", "clinic", "gym", "hotel", "rental", "service"
            } else "catalog",
        }
        context["business_config"] = business_config

        # 15: Session summary every 5 messages
        session_summary = await maybe_summarize(
            history=history,
            business_knowledge=business_knowledge,
            customer_name=customer_name,
            conv_state=conv_state,
            user_id=user_id,
        )
        session_summary_text = format_summary_for_prompt(session_summary)

        # Enrich context with classification results
        context.update({
            "intent": intent,
            "sentiment": sentiment,
            "language": language,
            "confidence": confidence,
            "keywords": classification.get("keywords", []),
            "entities": entities,
            "alternative_intents": alternative_intents,
            "careful_instruction": careful_instruction,
            "session_summary": session_summary,
            "session_summary_text": session_summary_text,
        })

        logger.info(
            f"[Router] user={user_id} customer={customer_id} "
            f"intent={intent} alt={alternative_intents} sentiment={sentiment} "
            f"lang={language} conf={confidence:.2f} model={selected_model} "
            f"escalate={needs_escalation} relationship={relationship}"
        )

        # ── 4. Immediate escalation if analyzer says so ────────────────────
        if needs_escalation:
            await self._do_escalate(user_id, customer_id, escalation_reason or f"Intent {intent} flagged for escalation")
            return {
                "handled": True,
                "escalated": True,
                "messages": [],
                "escalation_reason": escalation_reason,
            }

        # ── 5. Dispatch to agent ───────────────────────────────────────────
        agent_name = route_intent_to_agent(intent, context.get("business_type", ""))
        
        # Override agent routing based on active multi-step flows
        if conv_state.get("pending_order_action") or conv_state.get("pending_order_list"):
            logger.info("[Router] Overriding agent to 'order' due to pending order state")
            agent_name = "order"
        elif conv_state.get("pending_booking_action") or conv_state.get("pending_booking_list"):
            logger.info("[Router] Overriding agent to 'booking' due to pending booking state")
            agent_name = "booking"
            
        if is_personal:
            agent_name = "chat"

        # 12.3: BookingAgent handling a complaint → ComplaintAgent
        if agent_name == "booking" and sentiment in ("angry", "frustrated") and conv_state.get("complaint_count", 0) > 0:
            logger.info(f"[Router] Booking+complaint sentiment → routing to complaint agent")
            agent_name = "complaint"

        logger.info(f"[Router] dispatching to agent={agent_name} for intent={intent} btype={context.get('business_type','')}")
        agent_result = await self._dispatch(agent_name, user_id, message, context)
        logger.info(f"[Router] agent={agent_name} returned handled={agent_result.get('handled') if agent_result else None}")

        if not agent_result:
            agent_result = {"handled": False}

        # If agent itself requested escalation
        if agent_result.get("escalate"):
            reason = agent_result.get("escalate_reason", f"Agent {agent_name} escalated")
            await self._do_escalate(user_id, customer_id, reason)
            # Preserve any messages the agent already prepared (e.g. cancel/update confirmations)
            escalate_messages = agent_result.get("messages", [])
            return {
                "handled": True,
                "escalated": True,
                "messages": escalate_messages,
                "escalation_reason": reason,
            }

        if not agent_result.get("handled"):
            # For service/retail businesses, try the business-specific agent before chat fallback
            # This ensures booking/catalog requests that slip through intent classification
            # still reach the correct agent instead of ChatAgent generating fake confirmations
            _btype_fb = context.get("business_type", "").lower()
            _is_svc_fb = any(k in _btype_fb for k in (
                "salon", "saloon", "barbershop", "spa", "clinic", "healthcare",
                "fitness", "gym", "services", "restaurant", "hotel", "beauty",
                "rental", "airbnb", "creator", "service",
            ))
            if _is_svc_fb and agent_name != "booking":
                logger.info(f"[Router] Service biz: trying booking agent as fallback for intent={intent}")
                agent_result = await self._dispatch("booking", user_id, message, context)
            elif not _is_svc_fb and agent_name != "sales":
                logger.info(f"[Router] Retail biz: trying sales agent as fallback for intent={intent}")
                agent_result = await self._dispatch("sales", user_id, message, context)

            if not agent_result or not agent_result.get("handled"):
                # Final fallback: chat agent
                logger.warning(f"[Router] No agent handled intent={intent}, trying chat fallback")
                agent_result = await self._dispatch("chat", user_id, message, context)
            if not agent_result or not agent_result.get("handled"):
                await self._do_escalate(user_id, customer_id, f"No agent handled intent={intent}")
                return {"handled": True, "escalated": True, "messages": [], "escalation_reason": f"Unhandled intent: {intent}"}

        # ── 6. Reply validation (fast rules, no LLM) ─────────────────────
        messages_out = agent_result.get("messages", [])
        if messages_out:
            reply_text = " ".join(m.get("text", "") for m in messages_out if m.get("text"))
            validation = await validate_reply(
                reply_text=reply_text,
                original_message=message,
                intent=intent,
                sentiment=sentiment,
                language=language,
                agent_name=agent_name,
                business_knowledge=business_knowledge,
                history=history,
            )

            if validation["result"] == RESULT_ESCALATE:
                reason = validation.get("reason", "Validator escalated reply")
                logger.warning(f"[Router] Validator ESCALATE: {reason}")
                await self._do_escalate(user_id, customer_id, reason)
                return {"handled": True, "escalated": True, "messages": [], "escalation_reason": reason}

            if validation["result"] == RESULT_REJECT:
                # One retry with the suggestion fed back
                suggestion = validation.get("suggestion", "")
                logger.info(f"[Router] Validator REJECT — retrying. Reason: {validation.get('reason')} | Suggestion: {suggestion}")
                context["validator_suggestion"] = suggestion
                context["custom_instructions"] = suggestion

                retry_result = await self._dispatch(agent_name, user_id, message, context)
                if retry_result and retry_result.get("handled") and not retry_result.get("escalate"):
                    messages_out = retry_result.get("messages", [])
                    agent_result = retry_result
                else:
                    await self._do_escalate(user_id, customer_id, "Retry agent failed")
                    return {"handled": True, "escalated": True, "messages": [], "escalation_reason": "Retry agent failed"}

        # ── 7. Save conversation state ────────────────────────────────────
        state_updates = agent_result.get("context_update", {})
        state_updates["last_intent"] = intent
        if customer_id:
            await save_state(self.db, user_id, str(customer_id), state_updates)

        # ── 8. Flag for human if agent requested soft flag ────────────────
        if agent_result.get("flag_for_human") and customer_id:
            try:
                await self.db.customers.update_one(
                    {"_id": customer_id},
                    {"$set": {
                        "needs_human": True,
                        "needs_human_reason": agent_result.get("flag_reason", "Agent flagged for review"),
                        "needs_human_at": datetime.now(timezone.utc),
                    }}
                )
            except Exception as e:
                logger.error(f"[Router] flag_for_human update error: {e}")

        return {
            "handled": True,
            "escalated": False,
            "messages": messages_out,
            "context_update": state_updates,
        }

    async def _dispatch(
        self, agent_name: str, user_id: str, message: str, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Instantiate and run the correct agent."""
        try:
            if agent_name == "sales":
                return await SalesAgent("sales", self.db).process(user_id, message, context)
            elif agent_name == "order":
                return await OrderAgent(self.db).process(user_id, message, context)
            elif agent_name == "payment":
                return await PaymentAgent(self.db).process(user_id, message, context)
            elif agent_name == "complaint":
                return await ComplaintAgent(self.db).process(user_id, message, context)
            elif agent_name == "booking":
                return await BookingAgent("booking", self.db).process(user_id, message, context)
            else:
                return await ChatAgent("chat", self.db).process(user_id, message, context)
        except Exception as e:
            logger.error(f"[Router] _dispatch error agent={agent_name}: {e}")
            return {"handled": False}

    async def _do_escalate(self, user_id: str, customer_id, reason: str) -> None:
        """Mark conversation as escalated in DB."""
        if customer_id:
            await mark_escalated(self.db, user_id, str(customer_id), reason)
        logger.info(f"[Router] ESCALATED customer={customer_id} reason={reason}")

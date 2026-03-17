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


class Router:
    def __init__(self, db: Any):
        self.db = db

    async def route_and_process(
        self, user_id: str, message: str, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Full pipeline:
          1. Build threaded context (relationship detection)
          2. Load conversation state (auto-resets if stale)
          3. Analyze intent (1 AI call, threaded context)
          4. Dispatch to correct agent
          5. Validate reply (fast rules, no LLM)
          6. Save state + flag for human if needed
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

        # ── 2.5: Rate limiting ─────────────────────────────────────────────
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
        agent_name = route_intent_to_agent(intent)
        if is_personal:
            agent_name = "chat"

        # 12.3: BookingAgent handling a complaint → ComplaintAgent
        if agent_name == "booking" and sentiment in ("angry", "frustrated") and conv_state.get("complaint_count", 0) > 0:
            logger.info(f"[Router] Booking+complaint sentiment → routing to complaint agent")
            agent_name = "complaint"

        agent_result = await self._dispatch(agent_name, user_id, message, context)

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
            # No agent could handle it — fallback to chat, then escalate
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

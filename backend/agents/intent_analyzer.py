"""
IntentAnalyzer — One fast AI call that understands the message in full business context.

Uses threaded-context architecture:
  Layer 1: THE current message (what to reply to)
  Layer 2: Immediate thread (last 2-3 messages within 30 min)
  Layer 3: Relationship signal (follow-up / new conversation / continuation)
  Layer 4: Older context summarized in 1-2 lines
"""
import json
import re
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Intents that map to specific agents
SALES_INTENTS = {"PRODUCT_INQUIRY", "PRICE_INQUIRY", "CATALOG_REQUEST", "STOCK_CHECK", "NEGOTIATION", "BULK_ORDER"}
ORDER_INTENTS = {"ORDER_STATUS", "DELIVERY_INQUIRY", "TRACKING", "ORDER_CANCEL", "ORDER_MODIFY"}
PAYMENT_INTENTS = {"PAYMENT_CONFIRM", "PAYMENT_METHOD", "PAYMENT_ISSUE", "REFUND_REQUEST"}
COMPLAINT_INTENTS = {"COMPLAINT", "NEGATIVE_FEEDBACK", "DAMAGED_ITEM", "WRONG_ITEM", "ESCALATION"}
CHAT_INTENTS = {"GENERAL_CHAT", "PERSONAL_CHAT", "GREETING", "SMALL_TALK", "OFF_TOPIC"}
BOOKING_INTENTS = {"BOOKING_REQUEST", "AVAILABILITY_CHECK", "BOOKING_STATUS", "BOOKING_CANCEL", "RESCHEDULE"}

# Intents that must always escalate — AI should never handle alone
ALWAYS_ESCALATE_INTENTS = {"LEGAL_THREAT", "FRAUD_CLAIM", "ESCALATION"}

ESCALATE_THRESHOLD = 0.40

# Time thresholds for conversation threading
THREAD_GAP_MINUTES = 30       # messages within 30 min = same thread
NEW_CONVERSATION_HOURS = 24   # gap > 24h = brand new conversation


def build_threaded_context(history: list) -> Dict[str, Any]:
    """
    Split flat history into threaded layers with a relationship signal.
    
    Returns:
        {
            "immediate_thread": [last 2-3 msgs within 30 min of latest],
            "older_context": [remaining older messages],
            "relationship": "follow_up" | "new_conversation" | "continuation",
            "gap_description": "Customer is replying 2 minutes after last message" | etc,
            "hours_since_last": float or None,
        }
    """
    if not history:
        return {
            "immediate_thread": [],
            "older_context": [],
            "relationship": "new_conversation",
            "gap_description": "First message — no prior conversation.",
            "hours_since_last": None,
        }

    now = datetime.now(timezone.utc)
    
    # Parse timestamps from history (most recent is last)
    last_msg = history[-1]
    last_ts = _parse_ts(last_msg.get("created_at"))
    
    if not last_ts:
        # No timestamp — treat all recent as immediate thread
        immediate = history[-3:] if len(history) >= 3 else history
        older = history[:-len(immediate)] if len(history) > len(immediate) else []
        return {
            "immediate_thread": immediate,
            "older_context": older,
            "relationship": "continuation",
            "gap_description": "Ongoing conversation (timestamps unavailable).",
            "hours_since_last": None,
        }

    # Calculate gap between now and last message
    gap = now - last_ts
    hours_since = gap.total_seconds() / 3600.0

    # Build immediate thread: walk backwards, include messages within THREAD_GAP_MINUTES
    immediate = []
    older = []
    thread_cutoff = last_ts - timedelta(minutes=THREAD_GAP_MINUTES)
    
    for m in reversed(history):
        m_ts = _parse_ts(m.get("created_at"))
        if m_ts and m_ts >= thread_cutoff and len(immediate) < 4:
            immediate.insert(0, m)
        else:
            older.insert(0, m)

    # If no timestamps parsed, just take last 3
    if not immediate:
        immediate = history[-3:]
        older = history[:-3] if len(history) > 3 else []

    # Determine relationship
    if hours_since >= NEW_CONVERSATION_HOURS:
        relationship = "new_conversation"
        if hours_since >= 48:
            gap_desc = f"Customer is messaging again after {int(hours_since / 24)} days of silence. Treat as a FRESH conversation."
        else:
            gap_desc = f"Customer is messaging again after {int(hours_since)} hours. Likely a new topic."
    elif hours_since <= 0.5:  # within 30 min
        relationship = "follow_up"
        minutes = max(1, int(hours_since * 60))
        gap_desc = f"Customer replied {minutes} minute(s) after the last message. This is a DIRECT FOLLOW-UP to the conversation above."
    else:
        relationship = "continuation"
        gap_desc = f"Customer is continuing a conversation from {int(hours_since)} hours ago."

    return {
        "immediate_thread": immediate,
        "older_context": older,
        "relationship": relationship,
        "gap_description": gap_desc,
        "hours_since_last": round(hours_since, 2),
    }


def _parse_ts(ts_val) -> datetime | None:
    """Parse a timestamp value into a timezone-aware datetime."""
    if ts_val is None:
        return None
    if isinstance(ts_val, datetime):
        if ts_val.tzinfo is None:
            return ts_val.replace(tzinfo=timezone.utc)
        return ts_val
    if isinstance(ts_val, str):
        try:
            dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
    return None


def format_threaded_history(threaded: Dict[str, Any]) -> str:
    """Format threaded context into a structured prompt section."""
    parts = []
    
    # Older context — summarized
    older = threaded.get("older_context", [])
    if older:
        older_lines = []
        for m in older[-6:]:  # max 6 older messages
            role = "Customer" if m.get("direction") == "incoming" else "Business"
            content = (m.get("content", "") or "")[:120]
            older_lines.append(f"  {role}: {content}")
        parts.append("Earlier in the conversation:\n" + "\n".join(older_lines))
    
    # Immediate thread — full detail
    immediate = threaded.get("immediate_thread", [])
    if immediate:
        thread_lines = []
        for m in immediate:
            role = "Customer" if m.get("direction") == "incoming" else "Business"
            content = m.get("content", "") or ""
            thread_lines.append(f"  {role}: {content}")
        parts.append("Recent thread (most relevant):\n" + "\n".join(thread_lines))
    
    # Relationship signal
    gap_desc = threaded.get("gap_description", "")
    if gap_desc:
        parts.append(f"⚡ CONTEXT: {gap_desc}")
    
    return "\n\n".join(parts) if parts else "(no prior history)"


async def analyze_intent(
    message: str,
    history: list,
    business_knowledge: str,
    conversation_state: dict,
    customer_name: str,
    is_personal: bool,
    business_type: str = "",
) -> Dict[str, Any]:
    """
    Single AI call that returns full intent classification.
    Uses threaded-context: focuses on the immediate thread + relationship signal
    so the AI knows whether this is a follow-up or a new conversation.
    """
    try:
        from ai_service import get_drafter
        ai = get_drafter()

        # Build threaded context
        threaded = build_threaded_context(history)
        history_text = format_threaded_history(threaded)
        relationship = threaded.get("relationship", "new_conversation")

        # Build conversation state hint — but RESET if new conversation
        state_hint = ""
        if conversation_state and relationship != "new_conversation":
            cs = conversation_state.get("state", "new")
            lp = conversation_state.get("last_discussed_product")
            lpo = conversation_state.get("last_price_offered")
            if cs != "new":
                state_hint = f"\nConversation is currently in state: {cs}."
                if lp:
                    state_hint += f" Last discussed product: {lp}."
                if lpo:
                    state_hint += f" Last price offered: {lpo}."

        bk_snippet = ""
        if business_knowledge:
            bk_snippet = f"\nBusiness context:\n{business_knowledge[:1200]}"

        personal_note = "\nThis is a personal contact (friend/family), not a business customer." if is_personal else ""

        # Business-type bias: service/rental businesses must use booking intents, never CATALOG_REQUEST
        SERVICE_BUSINESS_TYPES = {"salon", "saloon", "barbershop", "spa", "clinic", "healthcare", "fitness", "gym", "services", "restaurant", "hotel", "beauty", "rental"}
        _btype = (business_type or "").lower().strip()
        booking_bias = ""
        if _btype in SERVICE_BUSINESS_TYPES or any(k in _btype for k in ("salon", "spa", "clinic", "barber", "beauty", "fitness", "gym", "service", "rental", "airbnb")):
            booking_bias = (
                f"\n🚫 CRITICAL RULE — This is a '{business_type}' business that sells SERVICES/RENTALS, NOT physical products."
                f"\n   • NEVER classify as CATALOG_REQUEST or PRODUCT_INQUIRY."
                f"\n   • Any message asking 'what do you offer', 'what services', 'what do you have', prices, availability = BOOKING_REQUEST."
                f"\n   • Any message asking when open, free slots, availability = AVAILABILITY_CHECK."
                f"\n   • CATALOG_REQUEST is FORBIDDEN for this business type. Use BOOKING_REQUEST instead."
            )

        prompt = f"""You are an AI intent classifier for a WhatsApp business assistant.

Analyze the customer's LATEST message below and classify it accurately.
Focus on what the customer wants RIGHT NOW — not what was discussed before unless it's a direct follow-up.{bk_snippet}{personal_note}{booking_bias}{state_hint}

{history_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CUSTOMER'S CURRENT MESSAGE (reply to THIS): "{message}"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return ONLY valid JSON with these exact keys:
{{
  "intent": "<INTENT>",
  "sentiment": "<happy|neutral|frustrated|angry|urgent>",
  "language": "<language name or code, e.g. English, Swahili, Sheng, Arabic>",
  "entities": {{
    "products": [],
    "amounts": [],
    "dates": [],
    "other": []
  }},
  "conversation_state": "<new|ongoing|negotiating|closing|resolved>",
  "confidence": <0.0-1.0>,
  "needs_escalation": <true|false>,
  "escalation_reason": "<reason or null>",
  "keywords": []
}}

Intent categories with examples:

CATALOG_REQUEST - Customer wants to browse/see available products to choose from:
  • "I want to order something", "Can I buy something?", "Show me what you have"
  • "Let me see your products", "What are you selling?", "Send catalog"
  • "I'd like to purchase", "I want to order something else", "Show me items"

PRODUCT_INQUIRY - Asking about a SPECIFIC product/category:
  • "Do you have red dresses?", "Tell me about the iPhone", "What sizes for shoes?"
  • "How much is the laptop?", "Is the blue dress available?"

PRICE_INQUIRY - Asking about pricing without mentioning specific product:
  • "How much?", "What's the price?", "Cost?"

ORDER_STATUS - Checking existing order:
  • "Where is my order?", "Has it shipped?", "Order status?"

PAYMENT_METHOD - Asking HOW to pay / requesting payment details (NOT confirming payment):
  • "Send payment method", "How do I pay?", "What are your payment details?"
  • "Send me your account number", "Which Mpesa number?", "Where do I send money?"
  • "Payment details please", "How can I pay?", "Send payment info"

PAYMENT_CONFIRM - Confirming payment ALREADY MADE (money already sent):
  • "I've paid", "I have paid", "Sent the money", "Payment done", "Mpesa sent"
  • "I already transferred", "Done paying", "Check your Mpesa", "I've made the payment"

COMPLAINT - Expressing dissatisfaction:
  • "This is wrong", "Not what I ordered", "Poor quality", "I'm not happy"

GENERAL_CHAT - Casual conversation, greetings, thanks:
  • "Thank you", "Ok", "Sure", "Hello", "How are you?"

GREETING - Initial contact greeting:
  • "Hi", "Hello", "Good morning", "Hey"

BOOKING_REQUEST - Customer wants to book/schedule an appointment or service:
  • "I want to book", "Can I make an appointment?", "Book me in", "I need a haircut"
  • "Schedule me for Saturday", "I'd like to reserve a slot", "Can I get an appointment?"
  • "I want to come in", "Can you fit me in?", "Book an appointment for me"

AVAILABILITY_CHECK - Customer asking when business is open or what slots are free:
  • "When are you available?", "What times do you have?", "Are you open Saturday?"
  • "What's your schedule?", "Do you have slots this week?", "When can I come?"
  • "What services do you offer?", "What do you do?", "Show me your services" (for service businesses)

BOOKING_STATUS - Checking an existing appointment:
  • "What time is my appointment?", "Is my booking confirmed?", "When is my session?"

BOOKING_CANCEL - Cancelling or rescheduling:
  • "I need to cancel", "Can I reschedule?", "I can't make it", "Change my appointment"

Classification rules:
1. Understand INTENT not exact words - "I want to order something else" = CATALOG_REQUEST even though it doesn't say "catalog"
2. Short follow-ups ("ok", "yes", "sure") inherit intent from RECENT THREAD context
3. When unsure between two intents, pick the one that requires ACTION (e.g., CATALOG_REQUEST over GENERAL_CHAT)
4. For personal contacts, prefer PERSONAL_CHAT unless clearly business
5. Low confidence (<0.4) on business messages → needs_escalation=true
6. LEGAL_THREAT, FRAUD_CLAIM always → needs_escalation=true

JSON only, no markdown:"""

        raw = await ai._call_llm(prompt, model_pref="standard")

        # Strip markdown if present
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON in response: {raw[:200]}")

        result = json.loads(json_match.group())

        # Store relationship signal for downstream agents
        result["_relationship"] = relationship
        result["_hours_since_last"] = threaded.get("hours_since_last")

        # Enforce escalation on always-escalate intents
        intent = result.get("intent", "UNKNOWN")
        if intent in ALWAYS_ESCALATE_INTENTS:
            result["needs_escalation"] = True
            if not result.get("escalation_reason"):
                result["escalation_reason"] = f"Intent '{intent}' always requires human review"

        # Enforce escalation on low confidence
        confidence = float(result.get("confidence", 0.5))
        if confidence < ESCALATE_THRESHOLD and intent not in CHAT_INTENTS:
            result["needs_escalation"] = True
            if not result.get("escalation_reason"):
                result["escalation_reason"] = f"Low confidence ({confidence:.2f}) — human review needed"

        # UNKNOWN intent on short messages = conversational follow-up, not escalation
        if intent == "UNKNOWN" and len(message.split()) <= 8:
            result["intent"] = "GENERAL_CHAT"
            result["needs_escalation"] = False
            result["escalation_reason"] = None
            result["confidence"] = 0.7
            logger.info(f"[IntentAnalyzer] Short UNKNOWN message reclassified as GENERAL_CHAT: '{message}'")

        logger.info(
            f"[IntentAnalyzer] intent={result.get('intent')} sentiment={result.get('sentiment')} "
            f"confidence={result.get('confidence')} escalate={result.get('needs_escalation')} "
            f"relationship={relationship}"
        )
        return result

    except Exception as e:
        logger.error(f"[IntentAnalyzer] error: {e}")
        return {
            "intent": "UNKNOWN",
            "sentiment": "neutral",
            "language": "English",
            "entities": {"products": [], "amounts": [], "dates": [], "other": []},
            "conversation_state": "new",
            "confidence": 0.0,
            "needs_escalation": True,
            "escalation_reason": f"Intent analysis failed: {e}",
            "keywords": [],
            "_relationship": "new_conversation",
            "_hours_since_last": None,
        }


def route_intent_to_agent(intent: str) -> str:
    """Map an intent string to the agent name that should handle it."""
    if intent in SALES_INTENTS:
        return "sales"
    if intent in ORDER_INTENTS:
        return "order"
    if intent in PAYMENT_INTENTS:
        return "payment"
    if intent in COMPLAINT_INTENTS:
        return "complaint"
    if intent in BOOKING_INTENTS:
        return "booking"
    return "chat"

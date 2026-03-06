"""
IntentAnalyzer — One fast AI call that understands the message in full business context.

Returns a rich classification object that every downstream agent uses.
No hardcoded intent list — the AI infers intent from the business knowledge.
"""
import json
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Intents that map to specific agents
SALES_INTENTS = {"PRODUCT_INQUIRY", "PRICE_INQUIRY", "CATALOG_REQUEST", "STOCK_CHECK", "NEGOTIATION", "BULK_ORDER"}
ORDER_INTENTS = {"ORDER_STATUS", "DELIVERY_INQUIRY", "TRACKING", "ORDER_CANCEL", "ORDER_MODIFY"}
PAYMENT_INTENTS = {"PAYMENT_CONFIRM", "PAYMENT_METHOD", "PAYMENT_ISSUE", "REFUND_REQUEST"}
COMPLAINT_INTENTS = {"COMPLAINT", "NEGATIVE_FEEDBACK", "DAMAGED_ITEM", "WRONG_ITEM", "ESCALATION"}
CHAT_INTENTS = {"GENERAL_CHAT", "PERSONAL_CHAT", "GREETING", "SMALL_TALK", "OFF_TOPIC"}

# Intents that must always escalate — AI should never handle alone
ALWAYS_ESCALATE_INTENTS = {"LEGAL_THREAT", "FRAUD_CLAIM", "ESCALATION"}

ESCALATE_THRESHOLD = 0.40  # confidence below this → escalate (raised from 0.55 to avoid escalating short follow-ups)


async def analyze_intent(
    message: str,
    history: list,
    business_knowledge: str,
    conversation_state: dict,
    customer_name: str,
    is_personal: bool,
) -> Dict[str, Any]:
    """
    Single AI call that returns full intent classification.

    Returns:
        {
            intent: str,
            sentiment: str,        # happy | neutral | frustrated | angry | urgent
            language: str,         # detected language code or name
            entities: dict,        # products, amounts, dates, etc.
            conversation_state: str, # new | ongoing | negotiating | closing | resolved
            confidence: float,
            needs_escalation: bool,
            escalation_reason: str | None,
            keywords: list[str],
        }
    """
    try:
        from ai_service import get_drafter
        ai = get_drafter()

        # Build recent history snippet (last 6 messages max for speed)
        history_text = ""
        if history:
            recent = history[-6:]
            lines = []
            for m in recent:
                role = "Customer" if m.get("direction") == "incoming" else "Business"
                lines.append(f"{role}: {m.get('content', '')}")
            history_text = "\n".join(lines)

        # Build conversation state hint
        state_hint = ""
        if conversation_state:
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
            bk_snippet = f"\nBusiness context:\n{business_knowledge[:800]}"

        personal_note = "\nThis is a personal contact (friend/family), not a business customer." if is_personal else ""

        prompt = f"""You are an AI intent classifier for a WhatsApp business assistant.

Analyze the customer's latest message and classify it accurately.{bk_snippet}{personal_note}{state_hint}

Recent conversation:
{history_text if history_text else "(no prior history)"}

Customer's latest message: "{message}"

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

Intent MUST be one of:
PRODUCT_INQUIRY, PRICE_INQUIRY, CATALOG_REQUEST, STOCK_CHECK, NEGOTIATION, BULK_ORDER,
ORDER_STATUS, DELIVERY_INQUIRY, TRACKING, ORDER_CANCEL, ORDER_MODIFY,
PAYMENT_CONFIRM, PAYMENT_METHOD, PAYMENT_ISSUE, REFUND_REQUEST,
COMPLAINT, NEGATIVE_FEEDBACK, DAMAGED_ITEM, WRONG_ITEM,
GENERAL_CHAT, PERSONAL_CHAT, GREETING, SMALL_TALK, OFF_TOPIC,
LEGAL_THREAT, FRAUD_CLAIM, ESCALATION, UNKNOWN

Rules:
- If the message is a short follow-up or agreement ("ok", "sure", "yes please", "can i see") — look at conversation history to determine intent, prefer CATALOG_REQUEST or PRODUCT_INQUIRY over UNKNOWN
- If you are not sure what the customer wants even after checking history, use GENERAL_CHAT (not UNKNOWN) for messages under 10 words
- If sentiment is angry AND confidence < 0.7, set needs_escalation=true
- LEGAL_THREAT always needs_escalation=true
- For personal contacts, prefer PERSONAL_CHAT or GENERAL_CHAT unless clearly business
- keywords: 1-4 English keywords useful for product search (only for sales intents)

JSON only, no markdown:"""

        raw = await ai._call_llm(prompt, model_pref="standard")

        # Strip markdown if present
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON in response: {raw[:200]}")

        result = json.loads(json_match.group())

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
        # e.g. "sure can i see", "ok", "yes please", "go ahead" — treat as GENERAL_CHAT
        if intent == "UNKNOWN" and len(message.split()) <= 8:
            result["intent"] = "GENERAL_CHAT"
            result["needs_escalation"] = False
            result["escalation_reason"] = None
            result["confidence"] = 0.7
            logger.info(f"[IntentAnalyzer] Short UNKNOWN message reclassified as GENERAL_CHAT: '{message}'")

        logger.info(
            f"[IntentAnalyzer] intent={result.get('intent')} sentiment={result.get('sentiment')} "
            f"confidence={result.get('confidence')} escalate={result.get('needs_escalation')}"
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
    return "chat"

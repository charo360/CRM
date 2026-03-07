from .base_agent import BaseAgent
from typing import List, Dict, Any
import logging
import re

logger = logging.getLogger(__name__)

# Only escalate when the customer is CLEARLY asking the business about money/orders
# These are multi-word patterns to avoid false positives on casual language
# "I paid my rent" won't trigger, but "how much is the dress" will
BUSINESS_MONEY_PATTERNS = [
    r'\bhow\s+much\s+(is|are|does|do|for|the)\b',  # "how much is the dress"
    r'\bwhat\s+(is|are)\s+the\s+price\b',            # "what is the price"
    r'\bwhat\s+do\s+you\s+charge\b',                 # "what do you charge"
    r'\bi\s+want\s+to\s+(pay|order|buy|purchase)\b',  # "i want to pay/order"
    r'\bcan\s+i\s+(pay|order|buy|purchase)\b',        # "can i pay/order"
    r'\bplace\s+(an?\s+)?order\b',                    # "place an order"
    r'\bmy\s+order\b',                                # "my order"
    r'\bmy\s+refund\b',                               # "my refund"
    r'\bmy\s+delivery\b',                             # "my delivery"
    r'\binvoice\b',                                   # invoice is always business
    r'\breceipt\b',                                   # receipt is always business
]


class ChatAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles general conversation, personal chat, and off-topic messages.
        Acts as a smart personal assistant — can help with drafts, general questions, life topics.

        Only escalates on CLEAR business/money requests (multi-word patterns).
        Casual mentions of money words in everyday language are NOT escalated.
        """
        is_personal = context.get("is_personal", False)
        intent = context.get("intent", "GENERAL_CHAT")
        language = context.get("language", "English")

        # Silent escalate ONLY if message clearly asks the business about money/orders
        if not is_personal and self._is_business_money_request(message):
            logger.info(f"[ChatAgent] Business money request detected, escalating: '{message[:60]}'")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "ChatAgent detected clear business/money request — escalating to human",
                "messages": [],
            }

        try:
            from ai_service import get_drafter
            ai_service = get_drafter()

            customer_name = context.get("customer_name", "there")
            business_name = context.get("business_name", "")
            business_knowledge = context.get("business_knowledge", "")
            history = context.get("history", [])
            if not history:
                history = [{"direction": "incoming", "content": message}]

            # Detect simple greeting — greet back naturally, no old context injected
            _GREETING_WORDS = {"hi", "hello", "hey", "hii", "habari", "mambo", "niaje", "sasa",
                               "good morning", "good afternoon", "good evening", "morning", "evening",
                               "howdy", "sup", "wassup", "salamu", "hola"}
            _msg_clean = message.lower().strip().rstrip("!?.,")
            _msg_words = _msg_clean.split()
            _is_greeting = (
                len(_msg_words) <= 5 and
                (any(_msg_clean.startswith(g) for g in _GREETING_WORDS) or _msg_clean in _GREETING_WORDS)
            )

            if _is_greeting:
                # Just greet back — no history, no memory, no products, clean slate
                instructions = (
                    f"The customer just said: \"{message}\"\n"
                    f"Reply with a natural, warm greeting back to {customer_name}. "
                    "MATCH THEIR LANGUAGE AND ENERGY exactly. "
                    "Just greet them back — 1 short sentence. "
                    "Do NOT mention any past conversations, products, orders, or topics. "
                    "Do NOT ask multiple questions. Just say hello back naturally. "
                    "Sound like a real person, not a bot."
                )
                result = await ai_service.draft_followup_message(
                    customer_name=customer_name,
                    customer_data={},
                    messages=[{"direction": "incoming", "content": message}],
                    business_name=business_name or "Personal",
                    tone="casual",
                    business_knowledge=None,
                    custom_instructions=instructions,
                    user_id=user_id,
                    model_pref=context.get("ai_model", "standard")
                )
            else:
                # Build persona instructions
                if is_personal:
                    instructions = (
                        f"You're texting {customer_name} who is a friend or family of the business owner — NOT a customer. "
                        "Write exactly how a real person texts a close friend: casual, warm, sometimes informal. "
                        "MATCH THEIR LANGUAGE AND ENERGY — if they write in Sheng, Pidgin, Swahili, mixed, you match it exactly. "
                        "No corporate tone, no formality, no 'I hope this message finds you well'. "
                        "Help with whatever they ask — drafting something, answering a question, just chatting. "
                        "Keep it real, keep it short. Sound like a person, not a product. "
                        "CRITICAL: ONLY use information from the conversation. NEVER invent facts or personal details."
                    )
                else:
                    instructions = (
                        "The customer is making small talk or asking something off-topic. "
                        "Reply like a real business owner would — friendly, natural, briefly. "
                        "MATCH THEIR LANGUAGE EXACTLY: English stays English, Swahili stays Swahili, mixed stays mixed. "
                        "Do NOT drag in products or pricing unless they bring it up first. "
                        "If they ask for help drafting something, do it well and directly. "
                        "If they ask a general question you can answer, answer it straight. "
                        "Never promise anything financial or make business commitments. "
                        "1-2 sentences max. No filler. No corporate phrases. Sound human. "
                        "CRITICAL: ONLY use information from the conversation. NEVER invent facts or personal details."
                    )

                custom_req = context.get("custom_instructions")
                if custom_req:
                    instructions += f"\n\nExtra direction for this reply: {custom_req}"

                result = await ai_service.draft_followup_message(
                    customer_name=customer_name,
                    customer_data=context.get("customer_data", {}),
                    messages=history,
                    business_name=business_name or "Personal",
                    tone="casual",
                    business_knowledge=business_knowledge if business_knowledge else None,
                    custom_instructions=instructions,
                    user_id=user_id,
                    model_pref=context.get("ai_model", "standard")
                )

            reply_text = result.get("drafted_message", "")

            if reply_text:
                return {
                    "messages": [{"text": reply_text}],
                    "handled": True,
                    "escalate": False,
                    "context_update": {"state": "ongoing", "last_intent": intent},
                }

        except Exception as e:
            logger.error(f"[ChatAgent] error: {e}")

        return {"handled": False}

    def _is_business_money_request(self, message: str) -> bool:
        """Only returns True for CLEAR business money/order requests, not casual mentions."""
        msg_lower = message.lower()
        for pattern in BUSINESS_MONEY_PATTERNS:
            if re.search(pattern, msg_lower):
                return True
        return False

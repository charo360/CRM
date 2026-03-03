from .base_agent import BaseAgent
from typing import List, Dict, Any
import logging
import re

logger = logging.getLogger(__name__)

# Topics that should silently escalate — ChatAgent never handles these
MONEY_BUSINESS_PATTERNS = [
    r'\bprice\b', r'\bcost\b', r'\bhow\s+much\b', r'\bpay\b', r'\bpaid\b',
    r'\bpayment\b', r'\border\b', r'\bdeliver\b', r'\brefund\b', r'\bdiscount\b',
    r'\boffer\b', r'\bdeal\b', r'\bpromot\b', r'\bfree\b', r'\bcharg\b',
    r'\binvoice\b', r'\breceipt\b', r'\bstock\b', r'\bavailab\b',
]

class ChatAgent(BaseAgent):
    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles general conversation, personal chat, and off-topic messages.
        Acts as a smart personal assistant — can help with drafts, general questions, life topics.

        NEVER handles money, pricing, payments, or business commitments.
        Silently escalates if those topics appear.
        """
        is_personal = context.get("is_personal", False)
        intent = context.get("intent", "GENERAL_CHAT")
        language = context.get("language", "English")

        # Silent escalate if message contains money/business topics and this is a business chat
        if not is_personal and self._contains_money_topic(message):
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "ChatAgent detected business/money topic — escalating to human",
                "messages": [],
            }

        try:
            from ai_service import get_drafter
            ai_service = get_drafter()

            customer_name = context.get("customer_name", "there")
            business_name = context.get("business_name", "")
            history = context.get("history", [])
            if not history:
                history = [{"direction": "incoming", "content": message}]

            # Build persona instructions
            if is_personal:
                instructions = (
                    f"You're texting {customer_name} who is a friend or family of the business owner — NOT a customer. "
                    "Write exactly how a real person texts a close friend: casual, warm, sometimes informal. "
                    "MATCH THEIR LANGUAGE AND ENERGY — if they write in Sheng, Pidgin, Swahili, mixed, you match it exactly. "
                    "No corporate tone, no formality, no 'I hope this message finds you well'. "
                    "Help with whatever they ask — drafting something, answering a question, just chatting. "
                    "Keep it real, keep it short. Sound like a person, not a product."
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
                    "1-2 sentences max. No filler. No corporate phrases. Sound human."
                )

            custom_req = context.get("custom_instructions")
            if custom_req:
                instructions += f"\n\nExtra direction for this reply: {custom_req}"

            result = await ai_service.draft_followup_message(
                customer_name=customer_name,
                customer_data={},
                messages=history,
                business_name=business_name or "Personal",
                tone="casual",
                business_knowledge=context.get("business_knowledge") if is_personal else None,
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

    def _contains_money_topic(self, message: str) -> bool:
        msg_lower = message.lower()
        for pattern in MONEY_BUSINESS_PATTERNS:
            if re.search(pattern, msg_lower):
                return True
        return False

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

# 6.2: Sensitive info patterns that should never be shared
SENSITIVE_INFO_PATTERNS = [
    r'\b(password|pin|passcode)\b',
    r'\b(account\s*number|bank\s*details|routing\s*number)\b',
    r'\b(national\s*id|id\s*number|passport\s*number)\b',
    r'\b(send\s*(me|us|your)\s*(money|cash|funds|payment))\b',
    r'\b(wire\s*transfer|send\s*to\s*my)\b',
]

# 6.1: Personal contact asking about complaints/refunds/orders → escalate
PERSONAL_COMPLAINT_PATTERNS = [
    r'\b(complaint|complain|unhappy|angry|upset|frustrated)\b',
    r'\b(refund|return|broken|damaged|wrong|missing)\b',
    r'\b(my\s+order|delivery|invoice|receipt|payment)\b',
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
        confidence = context.get("confidence", 1.0)
        careful_instruction = context.get("careful_instruction", "")

        # 7.2: UNKNOWN intent fallback — ask ONE clarifying question instead of guessing
        if intent == "UNKNOWN":
            return {
                "handled": True,
                "escalate": False,
                "messages": [{"text": "Just to make sure I help you properly — could you tell me a bit more about what you need? 😊"}],
                "context_update": {"state": "ongoing", "last_intent": "UNKNOWN"},
            }

        # 6.1: Personal contact asking about business complaints/orders → escalate
        if is_personal and self._matches_patterns(message, PERSONAL_COMPLAINT_PATTERNS):
            logger.info(f"[ChatAgent] Personal contact with business complaint, escalating")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "Personal contact raised business complaint — needs human review",
                "messages": [],
            }

        # 6.2: Sensitive info guard — never let AI share or request sensitive information
        if self._matches_patterns(message, SENSITIVE_INFO_PATTERNS):
            logger.info(f"[ChatAgent] Sensitive info request detected, escalating")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "Possible sensitive info request or social engineering — needs human review",
                "messages": [],
            }

        # Silent escalate ONLY if message clearly asks the business about money/orders
        if not is_personal and self._is_business_money_request(message):
            logger.info(f"[ChatAgent] Business money request detected, escalating: '{message[:60]}'")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "ChatAgent detected clear business/money request — escalating to human",
                "messages": [],
            }

        # Booking/order guardrail: ChatAgent must NEVER fake-confirm bookings or orders.
        # If a customer sends a clear booking/order confirmation request and ChatAgent is
        # the fallback, return unhandled so the proper agent can take over.
        _BOOKING_CONFIRM_PATTERNS = [
            r'\b(confirm|book|schedule|reserve|set\s+up|make)\b.*\b(appointment|booking|session|haircut|massage|service|slot)\b',
            r'\b(i\s+want|i\'d\s+like|can\s+i\s+get|please\s+book|book\s+me)\b.*\b(haircut|massage|service|appointment|session)\b',
            r'\bcan\s+you\s+confirm\b',
            r'\bconfirm\s+that\s+for\s+me\b',
            r'\b(reschedule|rebook|move\s+my\s+booking|change\s+my\s+booking|cancel\s+my\s+booking|cancel\s+my\s+appointment)\b',
            r'\b(wanna|want\s+to|need\s+to|i\'d\s+like\s+to)\s+(reschedule|cancel|rebook)\b',
        ]
        
        # Scheduling guardrail: ChatAgent should NEVER handle scheduling back-and-forths.
        # If the customer mentions a day of the week or a time, let the BookingAgent handle it.
        _SCHEDULING_PATTERNS = [
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b',
            r'\b(tomorrow|today|next\s+week|this\s+week)\b',
            r'\b\d{1,2}(:\d{2})?\s*(am|pm)\b',  # "4pm", "11:30 am"
            r'\b(what\s+time|which\s+day|what\s+day|available\s+slot|open\s+slot|free\s+slot)\b',
        ]
        
        if not is_personal and (
            self._matches_patterns(message, _BOOKING_CONFIRM_PATTERNS) or
            self._matches_patterns(message, _SCHEDULING_PATTERNS)
        ):
            logger.info(f"[ChatAgent] Booking or scheduling request detected — returning unhandled to trigger BookingAgent")
            return {"handled": False}

        try:
            from ai_service import get_drafter
            ai_service = get_drafter()

            customer_name = context.get("customer_name", "there")
            business_name = context.get("business_name", "")
            business_knowledge = context.get("business_knowledge", "")
            history = context.get("history", [])
            if not history:
                history = [{"direction": "incoming", "content": message}]

            # Intent hint injection
            intent_hint = (
                f"Intent classified as: {intent} ({confidence:.0%} confidence)\n"
                f"Customer message: \"{message}\"\n\n"
                f"Read the message yourself. If the classification seems off, address what the customer actually needs instead.\n"
            )
            if careful_instruction:
                intent_hint += f"\n{careful_instruction}\n"

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
                    f"IMPORTANT: Reply in {language} only — that is the language the customer used. "
                    "Do NOT switch to another language even if the business name sounds local. "
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
                    # Build a short thread so the AI has real conversation context
                    _p_thread = []
                    for _hm in history[-10:]:
                        _role = "Them" if _hm.get("direction") == "incoming" else "You"
                        _p_thread.append(f"{_role}: {_hm.get('content', '')}")
                    _p_thread_text = "\n".join(_p_thread) if _p_thread else "(No prior messages)"

                    instructions = (
                        f"You are replying on WhatsApp to {customer_name} — a personal contact (friend or family), NOT a customer.\n\n"
                        f"Their latest message: \"{message}\"\n\n"
                        f"Recent thread:\n{_p_thread_text}\n\n"
                        "Reply the way a real person texts someone they actually know:\n"
                        "- Match their exact language and energy — Sheng, Swahili, English, mixed — whatever they used\n"
                        "- If they said something funny, be funny. If they're venting, be warm. If they asked something, answer it.\n"
                        "- Do NOT mention the business, products, or anything sales-related\n"
                        "- Do NOT use corporate phrases: 'I hope this helps', 'I understand your concern', 'I'd be happy to'\n"
                        "- 1-2 sentences unless they asked something that needs more\n"
                        "- NEVER invent facts or personal details about them\n"
                        "- NEVER share sensitive info (passwords, bank details, IDs)\n"
                        "Output ONLY the reply text."
                    )
                    # Suppress business knowledge entirely for personal chats
                    business_knowledge = None
                else:
                    instructions = (
                        f"{intent_hint}"
                        "The customer is making small talk or asking something off-topic. "
                        # 7.1: If mixed small talk + business intent, answer the business part
                        "If the message contains BOTH small talk AND a business question, answer the business question directly. "
                        "Reply like a real business owner would — friendly, natural, briefly. "
                        "MATCH THEIR LANGUAGE EXACTLY: English stays English, Swahili stays Swahili, mixed stays mixed. "
                        "Do NOT drag in products or pricing unless they bring it up first. "
                        "If they ask for help drafting something, do it well and directly. "
                        "If they ask a general question you can answer, answer it straight. "
                        "Never promise anything financial or make business commitments. "
                        "CRITICAL: NEVER engage in scheduling, booking, or confirming appointments. "
                        "If they try to book or pick a time, NEVER confirm it. "
                        "Do NOT invent or share opening hours or available days. "
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

    def _matches_patterns(self, message: str, patterns: list) -> bool:
        """Return True if message matches any pattern in the list."""
        msg_lower = message.lower()
        for pattern in patterns:
            if re.search(pattern, msg_lower):
                return True
        return False

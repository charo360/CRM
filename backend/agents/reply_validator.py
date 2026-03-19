"""
ReplyValidator — Fast rules-only quality gate on every outgoing AI reply.

No LLM call — uses deterministic checks only for speed and consistency:
  1. Empty reply check
  2. ChatAgent money promise patterns
  3. Too-short reply for non-chat intents
  4. Too-long reply (WhatsApp readability)
  5. Dangerous commitment patterns (any agent)

Returns: APPROVE | REJECT(reason) | ESCALATE(reason)
"""
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

RESULT_APPROVE = "APPROVE"
RESULT_REJECT = "REJECT"
RESULT_ESCALATE = "ESCALATE"

# Hard rules that auto-escalate — dangerous commitments
MONEY_PROMISE_PATTERNS = [
    r'\b(i will|we will|i\'ll|we\'ll)\s+(give|offer|send|pay|refund|deliver)\b',
    r'\bfree\s+of\s+charge\b',
    r'\bno\s+charge\b',
    r'\bpromise\b',
    r'\bguarantee\s+(you|delivery|arrival)\b',
    r'\bby\s+(tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
]

# Patterns that indicate the AI is hallucinating an identity
IDENTITY_HALLUCINATION_PATTERNS = [
    r'\b(i am|i\'m|my name is)\s+(an?\s+)?(ai|bot|assistant|language model|chatbot|virtual)\b',
    r'\bas an ai\b',
]

# Chat intents where short replies are fine
SHORT_OK_INTENTS = {"GREETING", "SMALL_TALK", "GENERAL_CHAT", "PERSONAL_CHAT"}

# 12.4: Revised length thresholds
MIN_REPLY_CHARS = 20          # minimum characters for non-chat intents
MAX_REPLY_CHARS = 600         # ~150 words — WhatsApp readability limit
MAX_REPLY_CHARS_COMPLAINT = 800  # complaint/booking can be a bit longer

# 12.6: Booking hallucination patterns — inventing availability or prices
BOOKING_HALLUCINATION_PATTERNS = [
    r'\bavailable\s+(on|at|for)\s+\w+\s+(at\s+)?\d+',   # "available on Monday at 3"
    r'\b(slot|appointment|booking)\s+(is\s+)?available\b',
    r'\bwe have\s+(a\s+)?(slot|opening|appointment|space)\b',
    r'\b(come in|come\s+at|be here)\s+(on\s+)?\w+\s+at\s+\d+',
    r'\bprice\s+(is|for)\s+[\$\£\€\₦\₹\¥]?\s*\d+',     # inventing service prices
    r'\bcosts?\s+[\$\£\€\₦\₹\¥]?\s*\d+',
]


async def validate_reply(
    reply_text: str,
    original_message: str,
    intent: str,
    sentiment: str,
    language: str,
    agent_name: str,
    business_knowledge: str,
    history: list,
) -> Dict[str, Any]:
    """
    Fast rules-only validation — no LLM call.
    Checks for empty, too short, too long, money promises, and identity hallucinations.
    """
    # Rule 1: Empty reply
    if not reply_text or not reply_text.strip():
        return {
            "result": RESULT_ESCALATE,
            "reason": "Empty reply generated",
            "suggestion": None,
        }

    reply_lower = reply_text.lower()
    word_count = len(reply_text.split())
    char_count = len(reply_text.strip())

    # Rule 2: ChatAgent must never make money promises
    if agent_name == "chat":
        for pattern in MONEY_PROMISE_PATTERNS:
            if re.search(pattern, reply_lower):
                return {
                    "result": RESULT_ESCALATE,
                    "reason": f"ChatAgent reply contains money/delivery promise",
                    "suggestion": None,
                }

    # Rule 3: Any agent — dangerous commitment patterns
    if agent_name != "chat":
        # Only escalate on very specific dangerous patterns
        dangerous = [
            r'\b(we guarantee|i guarantee)\b',
            r'\b(legal|lawyer|sue|court)\b.*\b(will|promise)\b',
        ]
        for pattern in dangerous:
            if re.search(pattern, reply_lower):
                return {
                    "result": RESULT_ESCALATE,
                    "reason": "Reply contains dangerous commitment language",
                    "suggestion": None,
                }

    # Rule 4: Identity hallucination — AI revealing itself as a bot
    for pattern in IDENTITY_HALLUCINATION_PATTERNS:
        if re.search(pattern, reply_lower):
            return {
                "result": RESULT_REJECT,
                "reason": "Reply reveals AI identity — should sound like the business owner",
                "suggestion": "Reply as the business owner, not as an AI assistant.",
            }

    # Rule 5: Too short for non-chat intents
    if char_count < MIN_REPLY_CHARS and intent not in SHORT_OK_INTENTS:
        return {
            "result": RESULT_REJECT,
            "reason": f"Reply too short ({char_count} chars) for intent {intent}",
            "suggestion": "Provide a complete answer to the customer's question.",
        }

    # Rule 6: Too long — WhatsApp messages should be concise
    max_chars = MAX_REPLY_CHARS_COMPLAINT if agent_name in ("complaint", "booking") else MAX_REPLY_CHARS
    if char_count > max_chars:
        return {
            "result": RESULT_REJECT,
            "reason": f"Reply too long ({char_count} chars) — will bore the customer on WhatsApp",
            "suggestion": "Keep the reply under 600 characters. Be direct and WhatsApp-natural.",
        }

    # Rule 7: Booking agent must not invent availability slots or prices
    if agent_name == "booking":
        for pattern in BOOKING_HALLUCINATION_PATTERNS:
            if re.search(pattern, reply_lower):
                return {
                    "result": RESULT_REJECT,
                    "reason": "Booking reply appears to invent availability or prices not from business data",
                    "suggestion": "Do NOT invent specific time slots or prices. Ask the customer what date works and let the owner confirm.",
                }

    # All rules passed
    logger.info(f"[ReplyValidator] APPROVE agent={agent_name} intent={intent} words={word_count}")
    return {
        "result": RESULT_APPROVE,
        "reason": "Passed all quality checks",
        "suggestion": None,
    }

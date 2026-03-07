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

MAX_REPLY_WORDS = 200  # WhatsApp readability limit


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
    if word_count < 3 and intent not in SHORT_OK_INTENTS:
        return {
            "result": RESULT_REJECT,
            "reason": f"Reply too short ({word_count} words) for intent {intent}",
            "suggestion": "Provide a complete answer to the customer's question.",
        }

    # Rule 6: Too long — WhatsApp messages should be concise
    if word_count > MAX_REPLY_WORDS:
        return {
            "result": RESULT_REJECT,
            "reason": f"Reply too long ({word_count} words) — will bore the customer on WhatsApp",
            "suggestion": "Keep the reply under 150 words. Be direct and WhatsApp-natural.",
        }

    # All rules passed
    logger.info(f"[ReplyValidator] APPROVE agent={agent_name} intent={intent} words={word_count}")
    return {
        "result": RESULT_APPROVE,
        "reason": "Passed all quality checks",
        "suggestion": None,
    }

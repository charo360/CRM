"""
ReplyValidator — Quality gate on every outgoing AI reply.

Checks:
  1. Does the reply actually answer the customer's question?
  2. No invented prices, dates, names, or promises?
  3. Tone matches customer sentiment?
  4. Language matches what the customer used?
  5. Not too long / not too short?
  6. ChatAgent replies never contain money promises or commitments?

Returns: APPROVE | REJECT(reason) | ESCALATE(reason)
"""
import json
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

RESULT_APPROVE = "APPROVE"
RESULT_REJECT = "REJECT"
RESULT_ESCALATE = "ESCALATE"

# Hard rules that auto-escalate without even calling AI
MONEY_PROMISE_PATTERNS = [
    r'\b(i will|we will|i\'ll|we\'ll)\s+(give|offer|send|pay|refund|deliver)\b',
    r'\bfree\s+of\s+charge\b',
    r'\bno\s+charge\b',
    r'\bpromise\b',
    r'\bguarantee\s+(you|delivery|arrival)\b',
    r'\bby\s+(tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
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
    Validate a proposed reply before sending.

    Returns:
        {
            "result": "APPROVE" | "REJECT" | "ESCALATE",
            "reason": str,
            "suggestion": str | None   (if REJECT, hint for retry)
        }
    """
    if not reply_text or not reply_text.strip():
        return {
            "result": RESULT_ESCALATE,
            "reason": "Empty reply generated",
            "suggestion": None,
        }

    # --- Hard rule: ChatAgent must never make money promises ---
    if agent_name == "chat":
        reply_lower = reply_text.lower()
        for pattern in MONEY_PROMISE_PATTERNS:
            if re.search(pattern, reply_lower):
                return {
                    "result": RESULT_ESCALATE,
                    "reason": f"ChatAgent reply contains a money/delivery promise (pattern: {pattern})",
                    "suggestion": None,
                }

    # --- Hard rule: very short replies for non-chat intents are suspicious ---
    word_count = len(reply_text.split())
    if word_count < 3 and intent not in ("GREETING", "SMALL_TALK", "GENERAL_CHAT", "PERSONAL_CHAT"):
        return {
            "result": RESULT_REJECT,
            "reason": f"Reply too short ({word_count} words) for intent {intent}",
            "suggestion": "Provide a complete answer to the customer's question.",
        }

    # --- AI validation for quality ---
    try:
        from ai_service import get_drafter
        ai = get_drafter()

        history_snippet = ""
        if history:
            recent = history[-4:]
            lines = [
                f"{'Customer' if m.get('direction')=='incoming' else 'Business'}: {m.get('content','')}"
                for m in recent
            ]
            history_snippet = "\n".join(lines)

        bk = (business_knowledge or "")[:400]

        prompt = f"""You are a reply quality checker for a WhatsApp business assistant.

Business context: {bk}

Recent conversation:
{history_snippet if history_snippet else "(no history)"}

Customer's message: "{original_message}"
Detected intent: {intent}
Customer sentiment: {sentiment}
Customer language: {language}
Agent that generated reply: {agent_name}

Proposed reply to send:
\"\"\"
{reply_text}
\"\"\"

Check the proposed reply against ALL these rules:
1. Does it actually answer or address the customer's question/intent?
2. Does it match the customer's language (or at least partially)?
3. Is the tone appropriate for the customer's sentiment? (e.g. angry customer needs empathy first)
4. Does it invent facts not present in the business context or conversation?
5. For non-chat agents: does it avoid vague promises like "we'll handle it soon"?
6. Is the length appropriate? (not a novel, not a one-word answer for a real question)

Return ONLY valid JSON:
{{
  "result": "APPROVE" or "REJECT" or "ESCALATE",
  "reason": "<brief reason>",
  "suggestion": "<improvement hint if REJECT, else null>"
}}

Use ESCALATE only if the reply could cause real harm or makes false commitments.
Use REJECT if the reply is wrong/irrelevant but fixable.
Use APPROVE if the reply is good enough to send.

JSON only:"""

        raw = await ai._call_llm(prompt, model_pref="standard")
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON in validator response: {raw[:200]}")

        result = json.loads(json_match.group())
        vresult = result.get("result", RESULT_APPROVE).upper()
        if vresult not in (RESULT_APPROVE, RESULT_REJECT, RESULT_ESCALATE):
            vresult = RESULT_APPROVE

        logger.info(f"[ReplyValidator] agent={agent_name} intent={intent} result={vresult} reason={result.get('reason','')}")
        return {
            "result": vresult,
            "reason": result.get("reason", ""),
            "suggestion": result.get("suggestion"),
        }

    except Exception as e:
        logger.error(f"[ReplyValidator] error: {e} — defaulting to APPROVE")
        # Validator failure should not block reply — log and approve
        return {
            "result": RESULT_APPROVE,
            "reason": f"Validator error (passthrough): {e}",
            "suggestion": None,
        }

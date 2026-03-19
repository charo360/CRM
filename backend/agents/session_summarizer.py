"""
SessionSummarizer — Generates a structured JSON summary of the conversation state
every 5 messages. Injected into agent context to help agents understand where
the conversation is and what the customer actually needs.

Summary keys:
  what_customer_wants     - concise description of the primary goal
  conversation_stage      - new | exploring | negotiating | ready_to_buy | post_purchase | escalating
  key_products_discussed  - list of product/service names mentioned
  unresolved_issues       - any complaints, confusion, or unanswered questions
  next_logical_step       - what should happen next to move this forward
  watch_out_for           - risks: social engineering, frustration, conflicting info
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

SUMMARIZE_EVERY_N = 5  # Run summarizer after every 5 messages


async def maybe_summarize(
    history: List[Dict],
    business_knowledge: str,
    customer_name: str,
    conv_state: Dict,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Run the summarizer if the message count is a multiple of SUMMARIZE_EVERY_N.
    Returns the summary dict, or None if not triggered yet.
    """
    message_count = len(history)
    if message_count < SUMMARIZE_EVERY_N or message_count % SUMMARIZE_EVERY_N != 0:
        return None

    try:
        return await _build_summary(history, business_knowledge, customer_name, conv_state, user_id)
    except Exception as e:
        logger.error(f"[SessionSummarizer] error: {e}")
        return None


async def _build_summary(
    history: List[Dict],
    business_knowledge: str,
    customer_name: str,
    conv_state: Dict,
    user_id: str,
) -> Dict[str, Any]:
    from ai_service import get_drafter
    ai = get_drafter()

    # Use last 15 messages for summary
    recent = history[-15:]
    history_text = "\n".join(
        f"{'Customer' if m.get('direction') == 'incoming' else 'Business'}: {m.get('content', '')}"
        for m in recent
    )

    bk = (business_knowledge or "")[:400]
    complaint_count = conv_state.get("complaint_count", 0)
    last_product = conv_state.get("last_discussed_product", "")
    state = conv_state.get("state", "new")

    prompt = f"""You are analyzing a WhatsApp business conversation to generate a structured summary.

Business info: {bk}
Customer name: {customer_name}
Conversation state: {state}
Complaint count: {complaint_count}
Last discussed product: {last_product or "none"}

Recent conversation:
{history_text}

Generate a JSON summary with EXACTLY these keys:
{{
  "what_customer_wants": "<1-2 sentences describing the customer's primary goal right now>",
  "conversation_stage": "<one of: new | exploring | negotiating | ready_to_buy | post_purchase | escalating | resolved>",
  "key_products_discussed": ["<product name>", ...],
  "unresolved_issues": "<any complaints, confusion, or unanswered questions — or 'none'>",
  "next_logical_step": "<what should the business do next to move this forward>",
  "watch_out_for": "<risks or red flags: frustration, social engineering, conflicting info — or 'none'>"
}}

Rules:
- Be concise and factual — only use information from the conversation above
- NEVER invent products, prices, or events not mentioned
- "conversation_stage" must be exactly one of the listed values
- Return ONLY valid JSON, no markdown or extra text

JSON only:"""

    raw = await ai._call_llm(prompt, model_pref="standard")

    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not json_match:
        raise ValueError(f"No JSON in summarizer response: {raw[:200]}")

    summary = json.loads(json_match.group())

    # Validate required keys
    required_keys = {
        "what_customer_wants", "conversation_stage", "key_products_discussed",
        "unresolved_issues", "next_logical_step", "watch_out_for",
    }
    missing = required_keys - set(summary.keys())
    if missing:
        logger.warning(f"[SessionSummarizer] Missing keys in summary: {missing}")
        for k in missing:
            summary[k] = "unknown"

    logger.info(
        f"[SessionSummarizer] stage={summary.get('conversation_stage')} "
        f"wants={summary.get('what_customer_wants', '')[:60]}"
    )
    return summary


def format_summary_for_prompt(summary: Optional[Dict[str, Any]]) -> str:
    """
    Format the session summary into a short text block for injection into agent prompts.
    Returns empty string if no summary available.
    """
    if not summary:
        return ""

    products = summary.get("key_products_discussed", [])
    products_str = ", ".join(products) if products else "none"

    return (
        f"\n══ SESSION SUMMARY ══\n"
        f"What customer wants: {summary.get('what_customer_wants', 'unknown')}\n"
        f"Stage: {summary.get('conversation_stage', 'unknown')}\n"
        f"Products discussed: {products_str}\n"
        f"Unresolved: {summary.get('unresolved_issues', 'none')}\n"
        f"Next step: {summary.get('next_logical_step', 'unknown')}\n"
        f"Watch out for: {summary.get('watch_out_for', 'none')}\n"
        f"══════════════════════\n"
    )

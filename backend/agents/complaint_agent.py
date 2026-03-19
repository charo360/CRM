"""
ComplaintAgent — Handles angry/frustrated customers, complaints, negative feedback.

Strategy:
  1. Always lead with empathy — acknowledge before anything else
  2. Attempt resolution if the issue is clear and within business power
  3. Escalate to human if: repeated complaint, high anger, legal threat, can't resolve
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

HIGH_ANGER_SENTIMENTS = {"angry", "urgent"}
ESCALATE_INTENTS = {"LEGAL_THREAT", "FRAUD_CLAIM", "ESCALATION"}


class ComplaintAgent:
    def __init__(self, db: Any):
        self.db = db

    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        intent = context.get("intent", "COMPLAINT")
        sentiment = context.get("sentiment", "frustrated")
        language = context.get("language", "English")
        customer_name = context.get("customer_name", "there")
        business_knowledge = context.get("business_knowledge", "")
        history = context.get("history", [])
        conv_state = context.get("conversation_state_data", {})
        complaint_count = conv_state.get("complaint_count", 0)
        confidence = context.get("confidence", 1.0)
        careful_instruction = context.get("careful_instruction", "")

        # Always escalate on legal threats or fraud claims
        if intent in ESCALATE_INTENTS:
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"Intent '{intent}' requires immediate human response",
                "messages": [],
            }

        # Escalate on repeated complaints (3+)
        if complaint_count >= 3:
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"Customer has complained {complaint_count} times — needs personal attention",
                "messages": [],
            }

        # Escalate on extreme anger — human touch is better
        if sentiment == "angry" and complaint_count >= 1:
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "Angry customer with prior complaint — human should respond",
                "messages": [],
            }

        # Attempt AI de-escalation
        try:
            reply = await self._build_empathy_reply(
                message, intent, sentiment, customer_name, language,
                business_knowledge, history, complaint_count=complaint_count,
                confidence=confidence, careful_instruction=careful_instruction,
            )
            if not reply:
                raise ValueError("Empty reply from AI")

            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": False,
                "context_update": {
                    "state": "ongoing",
                    "last_intent": intent,
                    "complaint_count": complaint_count + 1,
                },
                "flag_for_human": sentiment in HIGH_ANGER_SENTIMENTS,
                "flag_reason": f"Frustrated customer — AI responded but human may want to follow up" if sentiment in HIGH_ANGER_SENTIMENTS else None,
            }
        except Exception as e:
            logger.error(f"[ComplaintAgent] error: {e}")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"ComplaintAgent failed to build reply: {e}",
                "messages": [],
            }

    async def _build_empathy_reply(
        self, message, intent, sentiment, customer_name, language,
        business_knowledge, history, complaint_count=0, confidence=1.0, careful_instruction="",
    ) -> str:
        from ai_service import get_drafter
        ai = get_drafter()

        history_snippet = self._format_history(history)
        bk = (business_knowledge or "")[:500]

        tone_guidance = {
            "angry": "The customer is very angry. Lead with a sincere, warm apology. Do not be defensive.",
            "frustrated": "The customer is frustrated. Be understanding and solution-focused.",
            "urgent": "The customer feels something is urgent. Acknowledge urgency and respond quickly.",
        }.get(sentiment, "Be empathetic and professional.")

        # 10.1: complaint_count context for the AI
        complaint_history_note = ""
        if complaint_count > 0:
            complaint_history_note = f"\n⚠️ This customer has complained {complaint_count} time(s) before. Show extra care and urgency."

        # Intent hint injection
        intent_hint = (
            f"Intent classified as: {intent} ({confidence:.0%} confidence)\n"
            f"Customer message: \"{message}\"\n\n"
            f"Read the message yourself. If the classification seems off, address what the customer actually needs instead.\n"
        )
        if careful_instruction:
            intent_hint += f"\n{careful_instruction}\n"

        prompt = f"""You are a customer care assistant handling a complaint for a WhatsApp business.

{intent_hint}
Business info: {bk}

Customer name: {customer_name}
Customer sentiment: {sentiment}
Tone guidance: {tone_guidance}{complaint_history_note}

Recent conversation:
{history_snippet}

Think one sentence about what this customer actually needs, then reply. Output only the customer-facing message.

Rules:
1. Open with genuine empathy/apology first — never skip this
2. Acknowledge the specific issue they raised by name
3. Offer a concrete next step if possible (based on business info) — or say the team will follow up
4. Do NOT make promises you cannot keep (no specific timelines unless stated in business info)
5. Do NOT be defensive or dismissive
6. 10.2 COMPENSATION BOUNDARY: Do NOT offer refunds, discounts, or free products unless explicitly stated in business info
7. If unsure about a resolution, say \"I'll personally look into this for you\"
8. Warm, human, brief (3-5 sentences max), natural WhatsApp tone
9. CRITICAL: ONLY use facts from business info and conversation. NEVER invent details or timelines."""

        return await ai._call_llm(prompt, model_pref="standard")

    def _format_history(self, history: list, context: dict = None) -> str:
        if context and context.get("_threaded_history_text"):
            return context["_threaded_history_text"]
        if not history:
            return "(no prior history)"
        recent = history[-15:]
        lines = [
            f"{'Customer' if m.get('direction')=='incoming' else 'Business'}: {m.get('content','')}"
            for m in recent
        ]
        return "\n".join(lines)

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
                business_knowledge, history
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
        business_knowledge, history
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

        prompt = f"""You are a customer care assistant handling a complaint for a WhatsApp business.

Business info: {bk}

Customer name: {customer_name}
Customer message: "{message}"
Complaint type: {intent}
Customer sentiment: {sentiment}
Tone guidance: {tone_guidance}

Recent conversation:
{history_snippet}

Write a reply in {language} that:
1. Opens with genuine empathy/apology (don't skip this)
2. Acknowledges the specific issue they raised
3. Offers a concrete next step if possible (based on business info) — or says the team will follow up
4. Does NOT make promises you can't keep (no specific timelines unless in business info)
5. Does NOT be defensive or dismissive
6. Is warm, human, and brief (3-5 sentences max)
7. Matches a natural WhatsApp tone

Reply only:"""

        return await ai._call_llm(prompt, model_pref="standard")

    def _format_history(self, history: list) -> str:
        if not history:
            return "(no prior history)"
        recent = history[-4:]
        lines = [
            f"{'Customer' if m.get('direction')=='incoming' else 'Business'}: {m.get('content','')}"
            for m in recent
        ]
        return "\n".join(lines)

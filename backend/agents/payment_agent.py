"""
PaymentAgent — Handles payment confirmations, payment method questions, refunds.

Reads payment methods from business_knowledge (set by the business owner).
Never invents payment details. Escalates when payment can't be verified.
"""
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PaymentAgent:
    def __init__(self, db: Any):
        self.db = db

    async def process(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        intent = context.get("intent", "PAYMENT_METHOD")
        customer_name = context.get("customer_name", "there")
        language = context.get("language", "English")
        business_knowledge = context.get("business_knowledge", "")
        history = context.get("history", [])
        entities = context.get("entities", {})
        customer_id = context.get("customer_id")

        # Use structured payment_methods from context (preferred — accurate, no regex guessing)
        structured_pm = context.get("payment_methods", [])
        if structured_pm:
            payment_methods = [pm.get("name", "") for pm in structured_pm if isinstance(pm, dict) and pm.get("name")]
        else:
            # Fallback: regex extraction from business_knowledge text
            payment_methods = self._extract_payment_methods(business_knowledge)
            structured_pm = []

        if intent == "PAYMENT_CONFIRM":
            return await self._handle_payment_confirm(
                user_id, customer_id, message, customer_name, language,
                business_knowledge, payment_methods, history, entities
            )

        if intent in ("PAYMENT_METHOD", "PAYMENT_ISSUE"):
            return await self._handle_payment_method_question(
                message, customer_name, language, business_knowledge, payment_methods, structured_pm, history
            )

        if intent == "REFUND_REQUEST":
            # Refunds always need human — can't auto-approve
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "Customer requested a refund — needs human review",
                "messages": [],
            }

        # Fallback: explain payment methods if we have them
        if payment_methods:
            return await self._handle_payment_method_question(
                message, customer_name, language, business_knowledge, payment_methods, structured_pm, history
            )

        # No payment info in business knowledge
        return {
            "handled": True,
            "escalate": True,
            "escalate_reason": "Payment question but no payment methods configured in business knowledge",
            "messages": [],
        }

    async def _handle_payment_confirm(
        self, user_id, customer_id, message, customer_name, language,
        business_knowledge, payment_methods, history, entities
    ) -> Dict[str, Any]:
        """Customer says they've paid. Acknowledge and note — don't confirm what we can't verify."""
        try:
            from ai_service import get_drafter
            ai = get_drafter()

            amounts = entities.get("amounts", [])
            amount_text = f" of {amounts[0]}" if amounts else ""

            bk = (business_knowledge or "")[:400]
            methods_text = ", ".join(payment_methods) if payment_methods else "our accepted methods"

            history_snippet = self._format_history(history)

            prompt = f"""You are a payment acknowledgement assistant for a WhatsApp business.

Business info: {bk}
Accepted payment methods: {methods_text}

Customer name: {customer_name}
Customer message: "{message}"
Payment amount mentioned: {amount_text if amount_text else "not specified"}

Recent conversation:
{history_snippet}

Write a short, warm reply in {language} that:
1. Acknowledges that you've received their payment notification
2. Tells them the business will verify and confirm shortly
3. Does NOT confirm the payment as received (you cannot verify it here)
4. Does NOT promise delivery timelines
5. Is 1-2 sentences, WhatsApp-natural

Reply only:"""

            reply = await ai._call_llm(prompt, model_pref="standard")

            # Flag for human to verify payment
            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": False,
                "context_update": {
                    "state": "ongoing",
                    "last_intent": "PAYMENT_CONFIRM",
                    "pending_question": f"Verify payment{amount_text} from {customer_name}",
                },
                "flag_for_human": True,
                "flag_reason": f"Customer reported payment{amount_text} — needs verification",
            }
        except Exception as e:
            logger.error(f"[PaymentAgent] payment confirm error: {e}")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"PaymentAgent failed to build confirmation reply: {e}",
                "messages": [],
            }

    async def _handle_payment_method_question(
        self, message, customer_name, language, business_knowledge, payment_methods, structured_pm, history
    ) -> Dict[str, Any]:
        """Customer asks how to pay."""
        if not payment_methods:
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": "Customer asked about payment methods but none configured in business knowledge",
                "messages": [],
            }

        try:
            from ai_service import get_drafter
            ai = get_drafter()

            history_snippet = self._format_history(history)
            # Build a structured payment methods block for the AI prompt
            pm_formatted = self._format_payment_methods_for_prompt(structured_pm)

            prompt = f"""You are a business owner replying on WhatsApp. A customer asked how to pay.

Customer: {customer_name}
Their message: "{message}"

Your payment methods (ONLY share these — NEVER invent details):
{pm_formatted}

Recent conversation:
{history_snippet}

Write a clear, natural reply in {language} that:
1. Gives them exactly what they need to pay — name, number/account/details for each method
2. For Paybill: say the Business No. and Account No. on separate lines clearly
3. For Till/Buy Goods: give the Till No.
4. For phone-based payments (M-Pesa, Airtel Money, etc.): give the number
5. For bank: give bank name and account number
6. Format as a WhatsApp message — use line breaks between methods, bold the method name with *asterisks*
7. 1 short sentence intro, then the payment details, then offer to help if they have questions
8. CRITICAL: ONLY use the payment details listed above. NEVER invent numbers.

Reply only:"""

            reply = await ai._call_llm(prompt, model_pref="standard")
            return {
                "handled": True,
                "messages": [{"text": reply}],
                "escalate": False,
                "context_update": {"state": "ongoing", "last_intent": "PAYMENT_METHOD"},
            }
        except Exception as e:
            logger.error(f"[PaymentAgent] method question error: {e}")
            return {
                "handled": True,
                "escalate": True,
                "escalate_reason": f"PaymentAgent failed: {e}",
                "messages": [],
            }

    def _format_payment_methods_for_prompt(self, structured_pm: list) -> str:
        """Format structured payment methods clearly for the AI prompt."""
        if not structured_pm:
            return "(No payment methods configured)"
        lines = []
        for pm in structured_pm:
            if not isinstance(pm, dict):
                lines.append(f"- {pm}")
                continue
            name = pm.get("name", "")
            if not name:
                continue
            # Multi-field format (e.g. Paybill, Bank Transfer)
            if pm.get("fields"):
                field_lines = [
                    f"  {f['label']}: {f['value']}"
                    for f in pm["fields"]
                    if f.get("value") and str(f["value"]).strip()
                ]
                if field_lines:
                    lines.append(f"- {name}:\n" + "\n".join(field_lines))
                else:
                    lines.append(f"- {name}")
            elif pm.get("details") and str(pm["details"]).strip():
                lines.append(f"- {name}: {pm['details']}")
            else:
                lines.append(f"- {name}")
        return "\n".join(lines) if lines else "(No payment methods configured)"

    def _extract_payment_methods(self, business_knowledge: str) -> list:
        """Extract payment method mentions from business knowledge text."""
        if not business_knowledge:
            return []
        methods = []
        patterns = [
            r'm-?pesa', r'mpesa', r'airtel\s*money', r'mtn\s*money', r'orange\s*money',
            r'paypal', r'bank\s*transfer', r'bank\s*deposit', r'cash', r'card',
            r'visa', r'mastercard', r'stripe', r'flutterwave', r'paystack',
            r'venmo', r'zelle', r'western\s*union', r'moneygram',
            r'bitcoin', r'crypto', r'usdt', r'mobile\s*money',
        ]
        bk_lower = business_knowledge.lower()
        for p in patterns:
            if re.search(p, bk_lower):
                # Return display name
                display = re.search(p, business_knowledge, re.IGNORECASE)
                if display:
                    methods.append(display.group(0).strip())
        return list(dict.fromkeys(methods))  # deduplicate preserving order

    def _format_history(self, history: list, context: dict = None) -> str:
        if context and context.get("_threaded_history_text"):
            return context["_threaded_history_text"]
        if not history:
            return "(no prior history)"
        recent = history[-6:]
        lines = [
            f"{'Customer' if m.get('direction')=='incoming' else 'Business'}: {m.get('content','')}"
            for m in recent
        ]
        return "\n".join(lines)

"""FlowJudge — AI-first mid-flow message understanding.

Every message during a multi-step flow (booking, order-update, etc.) passes
through here BEFORE any rigid rule-based parser.  The AI decides:

  continue  — they answered what was asked; extract the value
  go_back   — they want to change a previous choice
  tangent   — unrelated message; reply warmly then re-ask
  cancel    — they want to stop entirely
  unclear   — genuinely ambiguous; ask one clarifying question

The caller uses the returned action to route accordingly. The rigid parser
only runs for action == "continue", optionally using extracted_value as
cleaner input.
"""
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


FLOW_JUDGE_PROMPT = """\
You are managing a WhatsApp {flow_type} conversation.

Booking progress so far:
{booking_summary}

Current step  : {current_step}
Waiting for   : {waiting_for}
Last bot msg  : {last_bot_message}
Detected lang : {language}

Customer just said: "{message}"

═══ LANGUAGE RULE (CRITICAL) ═══
You MUST reply in the EXACT same language the customer used.
Detected customer language: {language}
• If they wrote in English → reply ONLY in English
• If they wrote in Swahili → reply ONLY in Swahili  
• If they wrote in French → reply ONLY in French
• NEVER switch languages. NEVER mix languages unless the customer did.

═══ MULTILINGUAL INPUT ═══
Customers write in ANY language. Understand meaning in ANY language:
• "kesho asubuhi" → tomorrow morning (Swahili)
• "lunes" → Monday (Spanish) | "demain" → tomorrow (French)
• "غداً" → tomorrow (Arabic) | "kal subah" → tomorrow morning (Hindi)
• "próxima semana" → next week | "mbili" → 2 (Swahili)

═══ CONTEXT-AWARE NUMBER RULE ═══
If the last bot message mentioned a specific date being CLOSED/UNAVAILABLE,
and the customer replies with JUST A NUMBER (e.g. "26", "27"),
that number is the DAY of the SAME MONTH they were discussing.
Extract it as "[number] [month]" — action MUST be "continue".

Example:
  Last bot: "Sorry, we're closed on 25 March"
  Customer: "26" → extracted_value: "26 March", action: "continue"
  Customer: "27" → extracted_value: "27 March", action: "continue"

Return ONLY a valid JSON object — no explanation, no code fences:
{{
  "action": "continue | go_back | tangent | cancel | unclear | paginate_next | jump_period",
  "extracted_value": "the value they provided — or null",
  "target_step": "service_selection | date | time | addon | confirm | null",
  "period": "morning | afternoon | evening | null",
  "reply": "your reply (ONLY for tangent/cancel/unclear — 1-2 lines, match their language)",
  "reasoning": "brief explanation"
}}

═══ ACTION RULES ═══

- continue  : they provided what was asked. BE EXTREMELY FLEXIBLE — any format, any language.
              • Dates: "March 23", "23 March", "23/3", "Monday", "tomorrow", "kesho",
                "lunes", "demain", "الاثنين", "26" (in date context), "next week"
              • Times: "3pm", "15:00", "afternoon", "morning", "asubuhi", "soir", "3"
              • Numbers/slots: "1", "2", "5" (selecting from a menu)
              • Names: any text that could be a name
              Extract value AS-IS. If they gave a date, extract the date.
              ⚠ RULE: If you are waiting for a date and the customer provides ANY date-like
              value (number, day name, month name, relative word) → action MUST be "continue".
              ⚠ RULE: If you are waiting for a time slot number and the customer provides a
              number → action MUST be "continue".

- go_back   : ONLY when they EXPLICITLY say they want to change a PAST choice.
              Required trigger words: "change", "different", "another", "wrong", "not that",
              "actually no", "wait no", "start over", "badilisha", "tena", "ya nyingine",
              "cambiar", "changer", "تغيير"
              Set target_step to what they want to change.
              ⚠ NEVER use go_back just because they sent a date/time/number.
              ⚠ NEVER use go_back when you are WAITING for that type of input.

- tangent   : unrelated question mid-flow (price, hours, location, casual chat).
              Set reply = brief answer + gentle re-ask. Match their language.

- cancel    : explicit stop intent ("cancel", "never mind", "hapana", "acha", "stop").
              Set reply = friendly goodbye in their language.

- unclear   : ONLY if genuinely cannot tell. Set reply = one clarifying question.
              ⚠ Do NOT use unclear when they sent a date/time/number that makes sense in context.

- paginate_next : they want to see more time slots ("next", "more", "zaidi", "show more").

- jump_period   : they want a specific time of day.
                  "morning"/"asubuhi"/"mañana" → period: "morning"
                  "afternoon"/"mchana"/"après-midi" → period: "afternoon"
                  "evening"/"jioni"/"soir" → period: "evening"

Tone: natural WhatsApp — friendly, concise, never robotic.
Never say "I'm an AI" or "I cannot".
"""


class FlowJudge:
    """Lightweight singleton — one instance per server process."""

    def __init__(self):
        self._drafter = None

    def _get_drafter(self):
        if self._drafter is None:
            from ai_service import get_drafter  # lazy import
            self._drafter = get_drafter()
        return self._drafter

    async def understand(
        self,
        message: str,
        current_step: str,
        waiting_for: str,
        pending_state: Dict[str, Any],
        language: str = "English",
        flow_type: str = "booking",
        currency: str = "",
        last_bot_message: str = "",
    ) -> Dict[str, Any]:
        """
        Ask the AI what to do with this mid-flow message.

        Returns a dict:
          { "action": str, "extracted_value": str|None,
            "target_step": str|None, "reply": str|None, "reasoning": str }

        Never raises — falls back to {"action": "continue"} on any error.
        """
        # Build a human-readable booking summary for context
        lines = []
        if pending_state.get("booking_service_name"):
            svc = pending_state["booking_service_name"]
            price = pending_state.get("booking_service_price", 0)
            price_str = f" ({currency} {price:,.0f})" if price and currency else ""
            lines.append(f"- Service: {svc}{price_str}")
        if pending_state.get("booking_date"):
            lines.append(f"- Date: {pending_state['booking_date']}")
        if pending_state.get("booking_time"):
            lines.append(f"- Time: {pending_state['booking_time']}")
        if pending_state.get("booking_checkin_date"):
            lines.append(f"- Check-in: {pending_state['booking_checkin_date']}")
        if pending_state.get("booking_checkout_date"):
            lines.append(f"- Check-out: {pending_state['booking_checkout_date']}")
        if pending_state.get("booking_selected_addons"):
            lines.append(f"- Extras: {', '.join(pending_state['booking_selected_addons'])}")
        booking_summary = "\n".join(lines) if lines else "(just started)"

        prompt = FLOW_JUDGE_PROMPT.format(
            flow_type=flow_type,
            booking_summary=booking_summary,
            current_step=current_step,
            waiting_for=waiting_for,
            message=message,
            language=language,
            last_bot_message=(last_bot_message[:120] if last_bot_message else "(none)"),
        )

        try:
            drafter = self._get_drafter()
            raw = await drafter._call_llm(prompt, model_pref="standard")
            if not raw:
                return _default_continue()
            raw = raw.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start != -1 and end > start:
                    raw = raw[start:end]
            result = json.loads(raw)
            action = result.get("action", "continue")
            if action not in ("continue", "go_back", "tangent", "cancel", "unclear", "paginate_next", "jump_period"):
                result["action"] = "continue"
            logger.info(
                f"[FlowJudge] step='{current_step}' msg='{message[:50]}' "
                f"→ action={result.get('action')} reason={result.get('reasoning')}"
            )
            return result
        except Exception as e:
            logger.warning(f"[FlowJudge] AI call failed — defaulting to continue: {e}")
            return _default_continue()


def _default_continue() -> Dict[str, Any]:
    return {"action": "continue", "extracted_value": None, "target_step": None, "reply": None, "reasoning": "error"}


# ── Module-level singleton ────────────────────────────────────────────────────

_flow_judge: Optional[FlowJudge] = None


def get_flow_judge() -> FlowJudge:
    """Return (or lazily create) the module-level FlowJudge singleton."""
    global _flow_judge
    if _flow_judge is None:
        _flow_judge = FlowJudge()
    return _flow_judge

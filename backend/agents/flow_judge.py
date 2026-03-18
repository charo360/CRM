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

Customer just said: "{message}"

Return ONLY a valid JSON object — no explanation, no code fences:
{{
  "action": "continue | go_back | tangent | cancel | unclear",
  "extracted_value": "the value they provided (date/time/number/name) — or null",
  "target_step": "service_selection | date | time | addon | confirm | null",
  "reply": "your reply to the customer (ONLY for tangent/cancel/unclear — 1-2 short lines, warm WhatsApp tone)",
  "reasoning": "one word"
}}

Action rules (choose exactly one):
- continue  : they answered what you asked — extract the raw value into extracted_value.
              Be VERY FLEXIBLE with formats:
              • Dates: "March 23", "23 March", "23/3", "Monday", "tomorrow", "next week", "kesho"
              • Times: "3pm", "15:00", "3 o'clock", "afternoon", "morning", "evening", "asubuhi"
              • Numbers: "2", "two", "couple", "a few", "mbili"
              • Names: any text that looks like a name
              Extract the value AS-IS — don't try to normalize it, just pass it through.
- go_back   : they EXPLICITLY want to change something already chosen.
              Trigger words: "another", "change", "different", "actually no", "wait no",
              "wrong", "not that one", "other one", "choose again", "start over",
              "ya nyingine", "badilisha", "tena", "la kwanza tena".
              CRITICAL: DO NOT classify dates/times/numbers as go_back just because they're in
              a different format than the example. "March 23" is NOT go_back when waiting for a date.
- tangent   : unrelated / casual message ("hello", "thanks", "haha", "okay cool",
              "ngoja", "sawa").  Set reply = warm response + gentle re-ask.
- cancel    : they explicitly want to stop ("never mind", "forget it", "cancel",
              "stop", "hapana", "acha", "no thanks", "skip").
              Set reply = friendly goodbye.
- unclear   : genuinely cannot tell.  Set reply = ONE clarifying question only.

Language: {language}
Tone: natural WhatsApp — friendly, concise, never robotic. Never say "I'm an AI."
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
            if action not in ("continue", "go_back", "tangent", "cancel", "unclear"):
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

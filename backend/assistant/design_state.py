"""Design-flow mini-state persistence for the assistant.

Mirrors AutoReply v2's `conversation_states` pattern: the LLM remains the brain,
this module just persists a compact snapshot of decisions the AI has already made
(locked product, chosen platform, generated image URL, …) so that:

  - long conversations don't lose the lock when chat history gets truncated
  - a server restart mid-flow doesn't reset what the user picked
  - each turn's system prompt can show the AI exactly what's already locked

State is updated as a side-effect of successful design-tool calls
(`generate_social_post`, `generate_ad_creative`, `generate_carousel_cover`, `refine_design`).
The orchestrator loads it at the start of each design-agent turn and injects a
short markdown preamble into the system prompt.

Collection: ``assistant_design_states``  (keyed by conversation_id).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLLECTION = "assistant_design_states"

# Cap how many template ids we remember per conversation so the doc doesn't grow
# unbounded across long browsing sessions.
_MAX_TEMPLATES_SHOWN = 60

# ── Flow step definitions ─────────────────────────────────────────────────────
# Each step maps to a one-line "NEXT ACTION" the LLM must execute this turn.
# The AI advances the step by calling the listed tool — the tool call sets the
# next flow_step as a side-effect. The LLM reads these from the injected prompt
# block and must NOT deviate from the prescribed next action.
FLOW_STEPS = (
    "awaiting_product",
    "awaiting_platform",
    "awaiting_copy_approval",
    "awaiting_greenlight",
    "refining",
    "done",
)

_STEP_NEXT_ACTION: Dict[str, str] = {
    "awaiting_product": (
        "MANDATORY FIRST STEP — run this before anything else this turn. "
        "Silently call `list_products` right now. Then present ALL of these options to the user:\n"
        "1. Every real product from the catalog — show each as a chip (name + short tag).\n"
        "2. '📎 I have my own image — I'll attach it via the paperclip' — for custom/non-catalog images.\n"
        "3. '🎉 It's a promotion or offer — no specific product'\n"
        "4. '📣 Announcement or news'\n"
        "FORBIDDEN THIS TURN: `generate_social_post`, `generate_ad_creative`, "
        "`generate_carousel_cover`, `refine_design`. Platform noted — it will be used later."
    ),
    "awaiting_platform": (
        "Product is locked. Now handle platform. "
        "Check the conversation history — did the user already state a platform "
        "(e.g. 'Facebook post', 'Instagram story', 'TikTok', 'LinkedIn')? "
        "If YES: confirm it aloud (e.g. 'Facebook it is!') then move to copy approval. "
        "If NO: ask ONE question — show platform options as tap chips and wait. "
        "FORBIDDEN: `generate_social_post`, `generate_ad_creative`, `generate_carousel_cover`."
    ),
    "awaiting_copy_approval": (
        "Platform is locked. Propose copy (headline, tagline, CTA) and ask the user "
        "to approve or tweak. Do NOT generate yet — wait for their approval."
    ),
    "awaiting_greenlight": (
        "Copy is approved. "
        "If the user just said 'yes', 'go ahead', 'generate it', or any approval phrase, "
        "call the appropriate Gemini design tool immediately — do NOT ask again. "
        "Use `generate_social_post` for organic posts, `generate_ad_creative` for ads, "
        "`generate_carousel_cover` for carousels. "
        "If no approval yet, show a brief plan and ask: 'Shall I generate it?'"
    ),
    "refining": (
        "Design is generated. Present the image to the user and ask if they want "
        "any tweaks. If they want changes, use `refine_design` with their feedback."
    ),
    "done": (
        "Design is finalised. Ask the user what they want to do next — "
        "e.g. create an ad from this image, post it, or start a new design."
    ),
}


async def load_design_state(db, conversation_id: str, user_id: str) -> Dict[str, Any]:
    """Return the saved state doc, or an empty dict if none exists / on error."""
    if not conversation_id or not user_id:
        return {}
    try:
        doc = await db[COLLECTION].find_one({"_id": conversation_id, "user_id": user_id})
    except Exception:
        logger.exception("[design_state] load failed (conv=%s)", conversation_id)
        return {}
    if not doc:
        return {}
    doc.pop("_id", None)
    return doc


async def update_design_state(
    db,
    conversation_id: Optional[str],
    user_id: Optional[str],
    *,
    add_templates_shown: Optional[List[Any]] = None,
    add_pending_requirements: Optional[List[str]] = None,
    **fields: Any,
) -> None:
    """Best-effort upsert. Silently no-ops when conversation_id/user_id are missing
    so non-design agents (or pre-conversation tool calls) don't crash.

    Pass simple scalar updates as keyword args (e.g. locked_template_id="8923").
    Use ``add_templates_shown=[...]`` to append to the de-duplicated list.
    Use ``add_pending_requirements=[...]`` to add user-stated design requirements
    (e.g. "include_logo", "use_brand_color", "stage_product") that the render-time
    and pre-presentation guards will verify against the latest modifications dict.
    """
    if not conversation_id or not user_id:
        return

    set_fields: Dict[str, Any] = {"user_id": user_id, "updated_at": datetime.utcnow()}
    for k, v in fields.items():
        if v is None:
            continue
        set_fields[k] = v

    update: Dict[str, Any] = {"$set": set_fields}
    add_to_set: Dict[str, Any] = {}
    if add_templates_shown:
        # Keep as strings + de-dup at write time via $addToSet
        ids = [str(t) for t in add_templates_shown if t is not None]
        if ids:
            add_to_set["templates_shown"] = {"$each": ids}
    if add_pending_requirements:
        reqs = [str(r) for r in add_pending_requirements if r]
        if reqs:
            add_to_set["pending_requirements"] = {"$each": reqs}
    if add_to_set:
        update["$addToSet"] = add_to_set

    try:
        await db[COLLECTION].update_one(
            {"_id": conversation_id},
            update,
            upsert=True,
        )
        # Trim templates_shown if it grows past the cap (cheapest: only when we wrote new ids)
        if add_templates_shown:
            doc = await db[COLLECTION].find_one(
                {"_id": conversation_id},
                {"templates_shown": 1},
            )
            shown = (doc or {}).get("templates_shown") or []
            if isinstance(shown, list) and len(shown) > _MAX_TEMPLATES_SHOWN:
                trimmed = shown[-_MAX_TEMPLATES_SHOWN:]
                await db[COLLECTION].update_one(
                    {"_id": conversation_id},
                    {"$set": {"templates_shown": trimmed}},
                )
    except Exception:
        logger.exception("[design_state] update failed (conv=%s)", conversation_id)


def format_design_state_for_prompt(state: Dict[str, Any]) -> str:
    """Render the state as a short markdown preamble for the system prompt.
    Returns an empty string when there's nothing locked yet."""
    if not state:
        return ""

    lines: List[str] = []

    # ── Flow step — shown first so the AI knows exactly what to do this turn ──
    flow_step = state.get("flow_step")
    if flow_step:
        next_action = _STEP_NEXT_ACTION.get(flow_step, "Continue the design flow.")
        lines.append(f"▶ **CURRENT STEP: `{flow_step}`**")
        lines.append(f"**NEXT ACTION (mandatory this turn):** {next_action}")
        lines.append("")  # blank line separator before locked values

    if state.get("product_name") or state.get("product_id"):
        pid = state.get("product_id")
        nm = state.get("product_name") or ""
        suffix = f" (id `{pid}`)" if pid else ""
        lines.append(f"- 📦 **Product:** {nm}{suffix}".rstrip())

    plat = state.get("chosen_platform")
    asp = state.get("chosen_aspect")
    if plat or asp:
        bits = [b for b in (plat, asp) if b]
        lines.append(f"- 📱 **Platform:** {' · '.join(bits)}")

    last_render = state.get("last_render_url")
    if last_render:
        lines.append(f"- 🎨 **Generated design:** {last_render}")

    pending = state.get("pending_requirements") or []
    if isinstance(pending, list) and pending:
        lines.append(
            f"- ✅ **User requirements (must satisfy before final):** {', '.join(sorted(set(pending)))}"
        )

    if not lines:
        return ""

    return (
        "## 📋 CURRENT DESIGN STATE (server-tracked — do not contradict)\n\n"
        + "\n".join(lines)
        + "\n\nUse the locked values above for every subsequent tool call. "
        + "If the user explicitly asks to change one (e.g. 'different template', "
        + "'switch platform'), update the choice and re-stage as needed; otherwise "
        + "treat these as immutable for this turn."
    )

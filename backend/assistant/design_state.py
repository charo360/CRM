"""Design-flow mini-state persistence for the assistant.

Mirrors AutoReply v2's `conversation_states` pattern: the LLM remains the brain,
this module just persists a compact snapshot of decisions the AI has already made
(locked template, chosen platform, staged image URL, …) so that:

  - long conversations don't lose the lock when chat history gets truncated
  - a server restart mid-flow doesn't reset what the user picked
  - each turn's system prompt can show the AI exactly what's already locked,
    making the "no silent template swap" rule self-enforcing

State is updated as a side-effect of successful design-tool calls
(`render_orshot_template`, `generate_design_background`, `list_orshot_templates`).
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
    "awaiting_template",
    "awaiting_copy_approval",
    "awaiting_greenlight",
    "refining",
    "done",
)

_STEP_NEXT_ACTION: Dict[str, str] = {
    "awaiting_product": (
        "Ask the user which product they want to feature. "
        "If catalog has items, silently call `list_products` first and offer them by name."
    ),
    "awaiting_platform": (
        "Product is locked. Ask ONE question: which platform and format? "
        "(e.g. Instagram Feed — square, Instagram Story — 9:16, Facebook Post). "
        "Do NOT jump to templates yet."
    ),
    "awaiting_template": (
        "Platform is locked. If you haven't shown templates yet this turn, call `list_orshot_templates` "
        "and show 3 templates with the exact thumbnail_url values copied verbatim from the tool result — "
        "never invent or retype a URL. Include 'See more options' and 'You pick the best one' chips. "
        "If templates have already been shown and you are waiting for the user to pick, do NOT call "
        "`list_orshot_templates` again — just wait. Do NOT ask any other questions this turn."
    ),
    "awaiting_copy_approval": (
        "Template is locked and its fields have been studied. Propose copy for each text field "
        "within the character limits you already noted. Ask the user to approve or tweak. "
        "Do NOT call `get_orshot_template_fields` again (already done). Do NOT render yet."
    ),
    "awaiting_greenlight": (
        "Product is staged (staged_image_url is set). Copy is approved. "
        "If the user just said 'yes', 'go ahead', 'render it', or any approval phrase, "
        "call `render_orshot_template` immediately — do NOT ask again. "
        "If no approval yet, show a brief plan (template + copy + staged image) and ask: "
        "'Shall I render it?'"
    ),
    "refining": (
        "Design is rendered. Present the image to the user and ask if they want "
        "any tweaks (headline, template, colours). If they approve, call `verify_design_ready`."
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

    tid = state.get("locked_template_id")
    tname = state.get("locked_template_name")
    if tid:
        nm = tname or "(unnamed)"
        lines.append(f"- 🔒 **Locked template:** {nm} (id `{tid}`)")

    staged = state.get("staged_image_url")
    if staged:
        lines.append(f"- 🖼️ **Approved staged shot:** {staged}")

    last_render = state.get("last_render_url")
    if last_render and last_render != staged:
        lines.append(f"- 🎨 **Last render:** {last_render}")

    pending = state.get("pending_requirements") or []
    if isinstance(pending, list) and pending:
        # User-stated requirements the render-time guard will enforce.
        # Show them so the AI knows what `verify_design_ready` will check.
        lines.append(
            f"- ✅ **User requirements (must satisfy before final):** {', '.join(sorted(set(pending)))}"
        )

    shown = state.get("templates_shown") or []
    if isinstance(shown, list) and shown:
        # Only show the count to keep the prompt compact; the full list is in DB.
        lines.append(f"- 🗂️ **Templates already shown this thread:** {len(shown)} (skip these on 'See more options')")

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

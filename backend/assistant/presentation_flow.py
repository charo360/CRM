"""Direct presentation flows that bypass unreliable LLM steps where possible."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from .agents import AGENT_REGISTRY
from .presentation_plan import (
    build_generation_reply,
    build_regenerate_slide_reply,
    build_requirements_chat_reply,
    collect_presentation_user_context,
    finalize_slides_for_generation,
    infer_presentation_session,
    normalize_slide_plan,
    resolve_slides_for_generation,
)
from .tools import ToolContext, run_tool

logger = logging.getLogger(__name__)

APPROVE_LABEL = "✓ Approved slide plan — generate the presentation now."
APPROVE_EDITED_LABEL = "✓ Approved edited slide plan — generate the presentation now."


async def persist_presentation_plan_update(
    *,
    db,
    user_id: str,
    conversation_id: str,
    message_index: int,
    slides: List[Dict[str, Any]],
    topic: str = "",
) -> Dict[str, Any]:
    """Save user-edited slides back onto the plan_visual_presentation step in the conversation."""
    if db is None or not conversation_id:
        return {"error": "Conversation not found."}

    conv = await db.assistant_conversations.find_one({"_id": conversation_id, "user_id": user_id})
    if not conv:
        return {"error": "Conversation not found."}

    messages = list(conv.get("messages") or [])
    if message_index < 0 or message_index >= len(messages):
        return {"error": "Message not found."}

    msg = dict(messages[message_index])
    if msg.get("role") != "assistant":
        return {"error": "Plan can only be saved on an assistant message."}

    steps = list(msg.get("steps") or [])
    normalized = normalize_slide_plan(slides)
    if not normalized:
        return {"error": "slides are required."}

    saved_at = datetime.utcnow().isoformat() + "Z"
    updated = False
    saved_topic = (topic or "").strip()

    for step in steps:
        if step.get("tool") != "plan_visual_presentation":
            continue
        result = dict(step.get("result") or {})
        if not result.get("plan_ready") or not result.get("slides"):
            continue
        result["slides"] = normalized
        result["user_edited"] = True
        result["saved_at"] = saved_at
        if saved_topic:
            result["topic"] = saved_topic
            saved_topic = str(result.get("topic") or saved_topic)
        step["result"] = result
        updated = True
        break

    # Legacy turns persisted assistant messages without steps — attach plan from UI edits.
    if not updated:
        for step in steps:
            if step.get("tool") != "plan_visual_presentation":
                continue
            result = dict(step.get("result") or {})
            result["success"] = True
            result["plan_ready"] = True
            result["slides"] = normalized
            result["user_edited"] = True
            result["saved_at"] = saved_at
            if saved_topic:
                result["topic"] = saved_topic
            step["result"] = result
            updated = True
            saved_topic = str(result.get("topic") or saved_topic or "Presentation")
            break

    if not updated:
        steps.append({
            "tool": "plan_visual_presentation",
            "result": {
                "success": True,
                "plan_ready": True,
                "topic": saved_topic or "Presentation",
                "slides": normalized,
                "user_edited": True,
                "saved_at": saved_at,
            },
        })
        saved_topic = saved_topic or "Presentation"

    msg["steps"] = steps
    messages[message_index] = msg

    try:
        await db.assistant_conversations.update_one(
            {"_id": conversation_id, "user_id": user_id},
            {"$set": {"messages": messages, "updated_at": datetime.utcnow()}},
        )
    except Exception as exc:
        logger.warning("[presentation_flow] plan persist failed: %s", exc)
        return {"error": "Could not save plan to the conversation."}

    return {
        "success": True,
        "slides": normalized,
        "topic": saved_topic or topic or "Presentation",
        "user_edited": True,
        "saved_at": saved_at,
    }


def _format_requirements_submission(answers: Dict[str, str]) -> str:
    lines = [f"- **{k}**: {v.strip()}" for k, v in answers.items() if v and str(v).strip()]
    if not lines:
        return ""
    return "Here are my presentation details:\n\n" + "\n".join(lines)


async def _persist_turn(
    *,
    db,
    user_id: str,
    conversation_id: Optional[str],
    user_content: str,
    assistant_content: str,
    steps: List[Dict[str, Any]],
) -> None:
    if db is None or not conversation_id:
        return
    try:
        await db.assistant_conversations.update_one(
            {"_id": conversation_id, "user_id": user_id},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            {"role": "user", "content": user_content},
                            {
                                "role": "assistant",
                                "content": assistant_content,
                                "agent": "document",
                                "steps": steps,
                            },
                        ],
                        "$slice": -2000,
                    }
                },
                "$set": {"updated_at": datetime.utcnow(), "agent": "document"},
            },
        )
    except Exception as exc:
        logger.warning("[presentation_flow] message persist failed: %s", exc)


async def run_presentation_requirements_submit_stream(
    *,
    db,
    user: Dict[str, Any],
    conversation_id: Optional[str],
    deck_purpose: str = "",
    topic: str = "",
    audience: str = "",
    slide_count: int = 0,
    answers: Optional[Dict[str, str]] = None,
    prior_user_context: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Checklist submit → deterministic requirements re-check → plan when ready.
    Bypasses the chat agent for the re-check so it cannot ask for market size.
    """
    user_id = user.get("business_id") or user["_id"]
    answers = dict(answers or {})
    session = infer_presentation_session(
        deck_purpose=deck_purpose,
        topic=topic,
        audience=audience,
        slide_count=slide_count,
        messages=history,
        prior_user_context=prior_user_context,
    )
    user_label = _format_requirements_submission(answers) or "Here are my presentation details."
    merged_context = collect_presentation_user_context(
        args_user_context={**(prior_user_context or {}), **answers},
        user_message=user_label,
        full_history=history,
    )

    yield {
        "type": "thinking",
        "agent": "document",
        "agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
    }
    yield {"type": "tool_start", "tool": "check_presentation_requirements"}

    ctx = ToolContext(db, user)
    check_args = {
        "deck_purpose": session["deck_purpose"],
        "topic": session["topic"],
        "audience": session["audience"],
        "user_context": merged_context,
    }
    check_result = await run_tool("check_presentation_requirements", ctx, check_args)
    check_step = {
        "tool": "check_presentation_requirements",
        "arguments": check_args,
        "result": check_result,
    }
    steps: List[Dict[str, Any]] = [check_step]

    if not isinstance(check_result, dict) or check_result.get("error"):
        err = (check_result or {}).get("error", "Requirements check failed.")
        reply = f"Sorry — I couldn't verify the deck requirements: {err}"
        yield {"type": "token", "text": reply}
        await _persist_turn(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            user_content=user_label,
            assistant_content=reply,
            steps=steps,
        )
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "reply": reply,
            "steps": steps,
            "model": None,
            "needs_confirmation": None,
            "active_agent": "document",
            "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
            "reply_suggestions": [],
        }
        return

    checklist = check_result.get("checklist") or []
    reply = check_result.get("chat_reply") or build_requirements_chat_reply(
        check_result, checklist, check_result.get("auto_researched") or {}
    )

    if not check_result.get("ready"):
        for i in range(0, len(reply), 12):
            yield {"type": "token", "text": reply[i : i + 12]}
        await _persist_turn(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            user_content=user_label,
            assistant_content=reply,
            steps=steps,
        )
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "reply": reply,
            "steps": steps,
            "model": None,
            "needs_confirmation": None,
            "active_agent": "document",
            "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
            "reply_suggestions": [],
        }
        return

    # Requirements complete — plan with a narrow agent task (plan tool only).
    yield {"type": "tool_start", "tool": "plan_visual_presentation"}
    user_context = check_result.get("user_context") or merged_context
    plan_topic = (
        (check_result.get("business_profile") or {}).get("topic")
        or check_result.get("topic")
        or session["topic"]
    )
    slide_n = int(session.get("slide_count") or 5)
    readiness = check_result.get("readiness_summary") or []
    readiness_note = (
        "Gathered: " + "; ".join(readiness[:8]) if readiness else "CRM + web research complete."
    )
    plan_task = (
        "PRESENTATION_REQUIREMENTS_READY — call plan_visual_presentation exactly ONCE.\n\n"
        f"deck_purpose: {session['deck_purpose']}\n"
        f"topic: {plan_topic}\n"
        f"audience: {session['audience']}\n"
        f"slide_count: {slide_n}\n"
        f"{readiness_note}\n"
        f"user_context: {json.dumps(user_context, default=str)}\n\n"
        f"Build exactly {slide_n} slides using ONLY facts from user_context and CRM. "
        "Do NOT call check_presentation_requirements. Do NOT ask the user questions. "
        "After the tool succeeds, reply in one sentence pointing to the plan card below."
    )

    from .agent_runner import run_agent_stream

    plan_steps: List[Dict[str, Any]] = []
    plan_reply = ""
    try:
        async for ev in run_agent_stream(
            agent_id="document",
            task=plan_task,
            db=db,
            user=user,
            history=history,
            stream_final=True,
        ):
            if ev.get("type") == "tool_start":
                yield ev
            elif ev.get("type") == "token":
                plan_reply += ev.get("text") or ""
                yield ev
            elif ev.get("type") == "agent_result":
                plan_steps = ev.get("result", {}).get("steps") or []
                agent_text = (ev.get("result") or {}).get("text") or ""
                if agent_text.strip():
                    plan_reply = agent_text.strip()
    except Exception as exc:
        logger.exception("[presentation_flow] plan agent failed")
        plan_reply = f"{reply} Plan generation hit an error: {exc}"

    steps.extend(plan_steps)
    if not any(s.get("tool") == "plan_visual_presentation" for s in plan_steps):
        plan_reply = (
            f"{reply} I couldn't build the slide plan automatically — please tap "
            "**Proceed with the deck** to retry."
        )

    await _persist_turn(
        db=db,
        user_id=user_id,
        conversation_id=conversation_id,
        user_content=user_label,
        assistant_content=plan_reply,
        steps=steps,
    )

    yield {
        "type": "done",
        "conversation_id": conversation_id,
        "reply": plan_reply,
        "steps": steps,
        "model": None,
        "needs_confirmation": None,
        "active_agent": "document",
        "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
        "reply_suggestions": [],
    }


async def run_presentation_generate_stream(
    *,
    db,
    user: Dict[str, Any],
    conversation_id: Optional[str],
    topic: str,
    slides: List[Dict[str, Any]],
    edited: bool = False,
    message_index: Optional[int] = None,
    conversation_messages: Optional[List[Dict[str, Any]]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Step 3 of the presentation loop: UI approval → Gemini deck generation."""
    user_id = user.get("business_id") or user["_id"]

    if conversation_messages is None and db is not None and conversation_id:
        try:
            conv = await db.assistant_conversations.find_one(
                {"_id": conversation_id, "user_id": user_id}
            )
            if conv:
                conversation_messages = conv.get("messages") or []
        except Exception as exc:
            logger.warning("[presentation_flow] conv load for generate failed: %s", exc)

    resolved_slides, db_topic, db_edited = resolve_slides_for_generation(
        client_slides=slides,
        messages=conversation_messages,
        message_index=message_index,
        client_edited=edited,
    )
    edited = bool(db_edited or edited)
    topic = (db_topic or topic or "Presentation").strip()
    user_label = APPROVE_EDITED_LABEL if edited else APPROVE_LABEL
    normalized = finalize_slides_for_generation(
        resolved_slides,
        topic=topic,
        user_edited=edited,
    )
    if not normalized:
        reply = "Sorry — no slide plan found to generate. Update your plan and try again."
        yield {"type": "token", "text": reply}
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "reply": reply,
            "steps": [],
            "model": None,
            "needs_confirmation": None,
            "active_agent": "document",
            "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
            "reply_suggestions": [],
        }
        return

    yield {
        "type": "thinking",
        "agent": "document",
        "agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
    }
    yield {"type": "tool_start", "tool": "create_visual_presentation"}

    ctx = ToolContext(db, user)
    tool_args = {"topic": topic, "slides": normalized, "user_edited": edited}
    result = await run_tool("create_visual_presentation", ctx, tool_args)
    step = {"tool": "create_visual_presentation", "arguments": tool_args, "result": result}
    steps = [step]
    reply = build_generation_reply(result, len(normalized))

    chunk_size = 12
    for i in range(0, len(reply), chunk_size):
        yield {"type": "token", "text": reply[i : i + chunk_size]}

    await _persist_turn(
        db=db,
        user_id=user_id,
        conversation_id=conversation_id,
        user_content=user_label,
        assistant_content=reply,
        steps=steps,
    )

    yield {
        "type": "done",
        "conversation_id": conversation_id,
        "reply": reply,
        "steps": steps,
        "model": None,
        "needs_confirmation": None,
        "active_agent": "document",
        "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
        "reply_suggestions": [],
    }


async def persist_regenerate_slide_on_message(
    *,
    db,
    user_id: str,
    conversation_id: str,
    message_index: int,
    regenerate_step: Dict[str, Any],
) -> Dict[str, Any]:
    """Append a regenerate_slide step onto the assistant message that holds the deck preview."""
    if db is None or not conversation_id:
        return {"error": "Conversation not found."}

    conv = await db.assistant_conversations.find_one({"_id": conversation_id, "user_id": user_id})
    if not conv:
        return {"error": "Conversation not found."}

    messages = list(conv.get("messages") or [])
    if message_index < 0 or message_index >= len(messages):
        return {"error": "Message not found."}

    msg = dict(messages[message_index])
    if msg.get("role") != "assistant":
        return {"error": "Regenerate can only update an assistant message with the deck preview."}

    steps = list(msg.get("steps") or [])
    steps.append(regenerate_step)
    msg["steps"] = steps
    messages[message_index] = msg

    try:
        await db.assistant_conversations.update_one(
            {"_id": conversation_id, "user_id": user_id},
            {"$set": {"messages": messages, "updated_at": datetime.utcnow()}},
        )
    except Exception as exc:
        logger.warning("[presentation_flow] regenerate persist failed: %s", exc)
        return {"error": "Could not save the updated slide to the conversation."}

    return {"success": True, "steps": steps}


async def run_presentation_regenerate_slide_stream(
    *,
    db,
    user: Dict[str, Any],
    conversation_id: Optional[str],
    message_index: int,
    slide_index: int,
    instruction: str,
    slides: List[Dict[str, Any]],
    image_urls: List[str],
    topic: str = "",
) -> AsyncGenerator[Dict[str, Any], None]:
    """Regenerate ONE slide image and merge it back into the existing deck (no LLM round-trip)."""
    user_id = user.get("business_id") or user["_id"]
    instruction = (instruction or "").strip()
    topic = (topic or "Presentation").strip()

    if slide_index < 0:
        reply = "Invalid slide index."
        yield {"type": "token", "text": reply}
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "reply": reply,
            "steps": [],
            "message_index": message_index,
            "model": None,
            "needs_confirmation": None,
            "active_agent": "document",
            "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
            "reply_suggestions": [],
        }
        return

    if not slides:
        reply = "Sorry — no slide data found. Generate the deck again first."
        yield {"type": "token", "text": reply}
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "reply": reply,
            "steps": [],
            "message_index": message_index,
            "model": None,
            "needs_confirmation": None,
            "active_agent": "document",
            "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
            "reply_suggestions": [],
        }
        return

    if not instruction:
        reply = "Describe what to change on this slide first."
        yield {"type": "token", "text": reply}
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "reply": reply,
            "steps": [],
            "message_index": message_index,
            "model": None,
            "needs_confirmation": None,
            "active_agent": "document",
            "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
            "reply_suggestions": [],
        }
        return

    if not image_urls:
        image_urls = [""] * len(slides)

    yield {
        "type": "thinking",
        "agent": "document",
        "agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
    }
    yield {"type": "tool_start", "tool": "regenerate_slide"}

    ctx = ToolContext(db, user)
    tool_args = {
        "slide_index": slide_index,
        "instruction": instruction,
        "slides": slides,
        "image_urls": image_urls,
        "topic": topic,
    }
    result = await run_tool("regenerate_slide", ctx, tool_args)
    step = {"tool": "regenerate_slide", "arguments": tool_args, "result": result}
    reply = build_regenerate_slide_reply(result, slide_index)

    updated_steps: List[Dict[str, Any]] = []
    if conversation_id is not None and message_index is not None:
        persist = await persist_regenerate_slide_on_message(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            message_index=message_index,
            regenerate_step=step,
        )
        if persist.get("success"):
            updated_steps = persist.get("steps") or []

    chunk_size = 12
    for i in range(0, len(reply), chunk_size):
        yield {"type": "token", "text": reply[i : i + chunk_size]}

    yield {
        "type": "done",
        "conversation_id": conversation_id,
        "reply": reply,
        "steps": updated_steps,
        "message_index": message_index,
        "regenerate_step": step,
        "model": None,
        "needs_confirmation": None,
        "active_agent": "document",
        "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
        "reply_suggestions": [],
    }

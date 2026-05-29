"""Written-document flows — plan/review card then export PDF (mirrors presentation_flow)."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from .agents import AGENT_REGISTRY
from .tools import ToolContext, run_tool

logger = logging.getLogger(__name__)

APPROVE_LABEL = "✓ Approved document draft — export PDF now."
APPROVE_EDITED_LABEL = "✓ Approved edited document — export PDF now."


async def prepare_business_document(
    ctx: ToolContext,
    *,
    title: str,
    content: str,
    doc_type: str = "",
    template: str = "",
    image_prompt: str = "",
    export_pdf: bool = False,
) -> Dict[str, Any]:
    """Build HTML preview; optionally upload PDF."""
    import base64
    import uuid as _uuid

    from .document_plan import (
        build_export_config,
        enrich_doc_style,
        get_document_type_spec,
        infer_document_type_from_title,
        resolve_document_type,
        sanitize_document_text,
    )
    from .tools import get_owner_info

    title = (title or "Document").strip()
    content = (content or "").strip()
    if not content:
        return {"error": "content is required"}

    raw_doc_type = (doc_type or "").strip() or infer_document_type_from_title(title)
    resolved = resolve_document_type(raw_doc_type)
    type_spec = get_document_type_spec(resolved)
    export_cfg = build_export_config(resolved, type_spec)
    tpl = (template or export_cfg.get("template") or "professional").lower()

    owner = await ctx.db.users.find_one({"_id": ctx.business_id})
    business_name = (
        (owner.get("business_name") or owner.get("owner_name") or "My Business") if owner else "My Business"
    )

    owner_profile: Dict[str, Any] = {}
    try:
        owner_profile = await get_owner_info(ctx, {}) or {}
        if owner_profile.get("error"):
            owner_profile = {}
    except Exception:
        owner_profile = {}
    if owner:
        owner_profile.setdefault("email", owner.get("email") or "")
        owner_profile.setdefault("phone_number", owner.get("phone_number") or "")

    doc_style: Dict[str, Any] = {}
    try:
        from saved_designs import get_document_style as _get_doc_style
        doc_style = await _get_doc_style(ctx.db, ctx.business_id) or {}
    except Exception:
        pass
    doc_style, _spec = await enrich_doc_style(
        ctx.db, ctx.business_id, doc_style, resolved, owner=owner_profile,
    )

    website = (owner_profile.get("website_url") or "").strip()
    email = (owner_profile.get("email") or "").strip()
    content = sanitize_document_text(content, website_url=website, email=email)

    md = f"# {title}\n\n{content}"
    hero_image_url: Optional[str] = None
    _image_prompt = (image_prompt or "").strip()
    if not export_cfg.get("hero_image"):
        _image_prompt = ""
    elif not _image_prompt:
        _image_prompt = (export_cfg.get("hero_hint") or "").strip()
    if _image_prompt:
        try:
            from nano_banana_service import generate_creative_image
            _hero_result = await generate_creative_image(
                prompt=_image_prompt
                + ", shot on full-frame camera, natural lighting, no text, no watermarks, no logos, clean composition",
                format="landscape",
                quality="pro",
            )
            if _hero_result.get("success"):
                hero_image_url = _hero_result["image_url"]
        except Exception as exc:
            logger.warning("[document_flow] Hero image skipped: %s", exc)

    from .document_generator import generate_html_document, generate_pdf_from_html_async, store_html_preview

    html_preview = generate_html_document(
        md,
        title=title,
        business_name=business_name,
        style=doc_style,
        template=tpl,
        hero_image_url=hero_image_url,
    )
    preview_key = store_html_preview(html_preview)

    out: Dict[str, Any] = {
        "success": True,
        "plan_ready": True,
        "title": title,
        "doc_type": resolved,
        "doc_type_label": type_spec.get("label", "Document"),
        "template": tpl,
        "content_md": md,
        "body_markdown": content,
        "html_preview": html_preview,
        "preview_key": preview_key,
        "preview_url": f"/api/document-preview/{preview_key}" if preview_key else "",
        "logo_included": bool(export_cfg.get("use_logo") and doc_style.get("logo_url")),
        "website_url": website,
    }

    if not export_pdf:
        out["agent_reply_hint"] = (
            "Document plan is ready — reply in 1–2 sentences telling the user to review "
            "the draft below and tap Approve & Export PDF when ready. Do NOT call create_business_document yet."
        )
        return out

    filepath = None
    try:
        filepath = await generate_pdf_from_html_async(html_preview, None)
    except Exception as exc:
        logger.exception("[document_flow] PDF generation failed")
        return {"error": f"PDF generation failed: {exc}"}

    try:
        from pathlib import Path as _Path
        from image_handler import S3Handler

        _filepath = _Path(filepath) if isinstance(filepath, str) else filepath
        pdf_bytes = _filepath.read_bytes()
        b64 = base64.b64encode(pdf_bytes).decode()
        filename = f"doc-{_uuid.uuid4().hex[:8]}.pdf"
        pdf_url = await S3Handler.upload_file(b64, filename, content_type="application/pdf")
    except Exception as exc:
        logger.exception("[document_flow] S3 upload failed")
        return {"error": f"PDF upload failed: {exc}"}
    finally:
        try:
            from pathlib import Path as _Path
            _filepath = _Path(filepath) if isinstance(filepath, str) else filepath
            _filepath.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        from saved_designs import insert_saved_design
        await insert_saved_design(
            ctx.db,
            ctx.business_id,
            name=title[:200],
            asset_kind="pdf",
            file_url=pdf_url,
            thumbnail_url=None,
            source_tool="create_business_document",
            conversation_id=ctx.user.get("_active_conversation_id"),
        )
    except Exception:
        logger.exception("[document_flow] saved_designs insert skipped")

    out.update({
        "pdf_url": pdf_url,
        "download_url": pdf_url,
        "filename": f"{title}.pdf",
        "markdown": f"📄 **[Download {title}]({pdf_url})**" if pdf_url else "",
    })
    return out


def looks_like_document_dump(text: str) -> bool:
    """True when the model pasted a full document in chat instead of using plan_business_document."""
    body = (text or "").strip()
    if len(body) < 400:
        return False
    lowered = body.lower()
    markers = (
        "## ",
        "| ",
        "who we are",
        "company profile",
        "business profile",
        "the problem we solve",
        "what we do",
    )
    return sum(1 for m in markers if m in lowered) >= 2


def extract_markdown_body_from_dump(text: str) -> str:
    """Pull document markdown out of a chat reply that may include a short intro."""
    body = (text or "").strip()
    if not body:
        return ""
    for i, line in enumerate(body.splitlines()):
        stripped = line.strip()
        if stripped.startswith("#"):
            return "\n".join(body.splitlines()[i:]).strip()
    return body


async def recover_document_plan_from_dump(
    ctx: ToolContext,
    steps: List[Dict[str, Any]],
    task: str,
    dumped_text: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """When the agent pasted the full doc in chat, build the plan card from that text."""
    meta = _collect_requirements_from_steps(steps)
    content = extract_markdown_body_from_dump(dumped_text)
    if not content or len(content) < 200:
        return "", steps

    title = meta["title"]
    first_line = content.splitlines()[0].strip() if content else ""
    if first_line.startswith("#"):
        title = first_line.lstrip("#").strip() or title
        content = "\n".join(content.splitlines()[1:]).strip() or content

    plan_args = {
        "title": title,
        "content": content,
        "doc_type": meta["doc_type"],
    }
    plan_result = await prepare_business_document(ctx, **plan_args, export_pdf=False)
    plan_step = {"tool": "plan_business_document", "arguments": plan_args, "result": plan_result}
    new_steps = steps + [plan_step]

    if plan_result.get("error"):
        return f"Sorry — I couldn't build the document preview: {plan_result['error']}", new_steps

    reply = (
        f"Here's your **{title}** draft — review it below. "
        "Edit anything inline, then tap **Approve & Export PDF** when you're ready."
    )
    return reply, new_steps


def _collect_requirements_from_steps(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    doc_type = "company_profile"
    topic = ""
    title = ""
    user_context: Dict[str, Any] = {}
    sections: List[str] = []
    for step in steps:
        tool = step.get("tool") or ""
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        if tool == "check_document_requirements":
            doc_type = result.get("doc_type") or doc_type
            topic = result.get("topic") or topic
            user_context.update(result.get("user_context") or {})
            sections = list(result.get("recommended_sections") or sections)
        if tool == "plan_business_document" and result.get("plan_ready"):
            title = result.get("title") or title
    if not title:
        label = doc_type.replace("_", " ").title()
        title = f"{topic} — {label}" if topic else label
    return {
        "doc_type": doc_type,
        "topic": topic,
        "title": title,
        "user_context": user_context,
        "sections": sections,
    }


async def auto_plan_document_from_steps(
    ctx: ToolContext,
    steps: List[Dict[str, Any]],
    task: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Last-resort: draft markdown + plan card when the agent exhausted tool steps."""
    from .models import chat_with_tools
    from .tools import get_owner_info

    meta = _collect_requirements_from_steps(steps)
    owner = await get_owner_info(ctx, {}) or {}
    website = (owner.get("website_url") or "").strip()
    sections = meta["sections"] or [
        "Company Overview", "Products & Services", "Team", "Traction & Metrics", "Contact",
    ]
    section_list = ", ".join(sections)

    prompt = (
        f"Write a complete business document in Markdown.\n"
        f"Title: {meta['title']}\n"
        f"Document type: {meta['doc_type']}\n"
        f"Task: {task}\n"
        f"Business: {owner.get('business_name', '')}\n"
        f"Owner: {owner.get('owner_name', '')}\n"
        f"Country: {owner.get('country', '')}\n"
        f"Currency: {owner.get('currency', '')}\n"
        f"Website (Settings only — omit if blank): {website or 'none — do not invent any URL'}\n"
        f"Tagline: {owner.get('tagline', '')}\n"
        f"Description: {(owner.get('business_description') or '')[:500]}\n"
        f"Products: {(owner.get('products_services') or '')[:400]}\n"
        f"Required sections: {section_list}\n\n"
        "Return ONLY the markdown body (no # title line). Use real CRM facts. "
        "No placeholders. If website is empty, do not invent a domain."
    )

    resp = await chat_with_tools(messages=[
        {"role": "system", "content": "You are a senior business writer. Output markdown only."},
        {"role": "user", "content": prompt},
    ], tools=[], model_id=None)
    body = (resp.get("content") or "").strip()
    if not body:
        return "", steps

    plan_args = {
        "title": meta["title"],
        "content": body,
        "doc_type": meta["doc_type"],
    }
    plan_result = await prepare_business_document(ctx, **plan_args, export_pdf=False)
    plan_step = {"tool": "plan_business_document", "arguments": plan_args, "result": plan_result}
    new_steps = steps + [plan_step]

    if plan_result.get("error"):
        return f"Sorry — I couldn't build the document preview: {plan_result['error']}", new_steps

    reply = (
        f"Here's your **{meta['title']}** draft — review it below. "
        "Edit anything inline, then tap **Approve & Export PDF** when you're ready."
    )
    return reply, new_steps


async def persist_document_plan_update(
    *,
    db,
    user_id: str,
    conversation_id: str,
    message_index: int,
    title: str,
    content_md: str,
    body_markdown: str = "",
) -> Dict[str, Any]:
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
    saved_at = datetime.utcnow().isoformat() + "Z"
    updated = False
    for step in steps:
        if step.get("tool") != "plan_business_document":
            continue
        result = dict(step.get("result") or {})
        if not result.get("plan_ready"):
            continue
        result["title"] = title.strip() or result.get("title")
        result["content_md"] = content_md
        result["body_markdown"] = body_markdown or content_md
        result["user_edited"] = True
        result["saved_at"] = saved_at
        step["result"] = result
        updated = True
        break

    if not updated:
        steps.append({
            "tool": "plan_business_document",
            "result": {
                "success": True,
                "plan_ready": True,
                "title": title,
                "content_md": content_md,
                "body_markdown": body_markdown or content_md,
                "user_edited": True,
                "saved_at": saved_at,
            },
        })

    msg["steps"] = steps
    messages[message_index] = msg
    await db.assistant_conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {"$set": {"messages": messages, "updated_at": datetime.utcnow()}},
    )
    return {"success": True, "title": title, "content_md": content_md, "saved_at": saved_at}


def _resolve_plan_from_message(
    *,
    conversation_messages: List[Dict[str, Any]],
    message_index: Optional[int],
    title: str,
    content_md: str,
    body_markdown: str,
    doc_type: str,
) -> Tuple[str, str, str, str]:
    if message_index is not None and 0 <= message_index < len(conversation_messages):
        msg = conversation_messages[message_index]
        if msg.get("role") == "assistant":
            for step in reversed(msg.get("steps") or []):
                if step.get("tool") != "plan_business_document":
                    continue
                result = step.get("result") or {}
                if not result.get("plan_ready"):
                    continue
                return (
                    str(result.get("title") or title or "Document"),
                    str(result.get("content_md") or content_md or ""),
                    str(result.get("body_markdown") or body_markdown or ""),
                    str(result.get("doc_type") or doc_type or "other"),
                )
    return title or "Document", content_md, body_markdown, doc_type or "other"


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
        logger.warning("[document_flow] message persist failed: %s", exc)


async def run_document_generate_stream(
    *,
    db,
    user: Dict[str, Any],
    conversation_id: Optional[str],
    title: str,
    content_md: str,
    body_markdown: str = "",
    doc_type: str = "",
    edited: bool = False,
    message_index: Optional[int] = None,
    conversation_messages: Optional[List[Dict[str, Any]]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Export PDF directly from an approved document plan (no LLM round-trip)."""
    user_id = user.get("business_id") or user["_id"]
    title, content_md, body_markdown, doc_type = _resolve_plan_from_message(
        conversation_messages=conversation_messages or [],
        message_index=message_index,
        title=title,
        content_md=content_md,
        body_markdown=body_markdown,
        doc_type=doc_type,
    )

    body = (body_markdown or "").strip()
    if not body and content_md.strip().startswith("#"):
        body = "\n".join(content_md.strip().splitlines()[1:]).strip()

    user_label = APPROVE_EDITED_LABEL if edited else APPROVE_LABEL

    if not body:
        reply = "Sorry — no document content found to export. Edit the draft and try again."
        yield {"type": "token", "text": reply}
        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "reply": reply,
            "steps": [],
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
    yield {"type": "tool_start", "tool": "create_business_document"}

    ctx = ToolContext(db, user)
    tool_args = {"title": title, "content": body, "doc_type": doc_type}
    result = await prepare_business_document(ctx, **tool_args, export_pdf=True)
    step = {"tool": "create_business_document", "arguments": tool_args, "result": result}
    steps = [step]

    if result.get("error"):
        reply = f"Sorry — PDF export failed: {result['error']}"
    else:
        reply = result.get("markdown") or f"📄 Your **{title}** PDF is ready."

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
        "active_agent": "document",
        "active_agent_label": AGENT_REGISTRY.get("document", {}).get("label", "Document Writer"),
        "reply_suggestions": [],
    }

"""V2 multi-agent orchestrator for Zilo Chat.

Architecture
------------
User → Orchestrator (Claude) ──delegate_to_specialist──► AgentRunner
                              ◄── {text, artifacts} ──────────────
       Orchestrator chains specialists and streams the final reply.

Persistent flow state
---------------------
Every artifact produced in a conversation (image_url, caption, post_id, …)
is saved to MongoDB on the conversation document under `flow_state`.
On every new turn it is loaded and injected directly into the orchestrator
system prompt — so the orchestrator ALWAYS knows what has already been done,
even if the message history was compressed or the user comes back hours later.

Adding a new agent
------------------
    1. Add one entry to assistant/agents.py AGENT_REGISTRY:
           {"label": ..., "description": ..., "system_prompt": ..., "allowed_tools": ...}
    2. Restart the backend.
    Done. The orchestrator and runner pick it up automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Orchestrator base system prompt ──────────────────────────────────────────
_ORCHESTRATOR_BASE = """You are the master orchestrator of Zilo CRM Chat.

Your job: understand the user's intent and either answer directly (simple questions) or delegate to the right specialist(s).

## SPECIALISTS
You have access to all registered specialists via delegate_to_specialist.
Read the tool description for the full list and their capabilities.

## WHEN TO ANSWER DIRECTLY (no delegation)
- Pure small talk ("hi", "thanks", "ok", "got it") — one sentence max, then offer to help
- Explaining what a Zilo feature does in general (no business data needed)
- NOTHING ELSE — do not ask clarifying questions yourself. Delegate immediately and let the specialist ask.

## DELEGATE IMMEDIATELY — do not pre-qualify
If the user wants to create, design, schedule, analyse, or manage anything → delegate to the specialist RIGHT NOW without asking preliminary questions first. The specialist has `get_owner_info` and will fetch the business context itself. You asking "what platform?" or "what's the post about?" before delegating wastes turns and makes the experience feel slow.

Examples of what to delegate immediately (do not ask first):
- "create a post" → delegate to creative or social_scheduler
- "schedule something" → delegate to social_scheduler
- "show me analytics" → delegate to analytics
- "send a broadcast" → delegate to broadcasts
- "add a customer" → delegate to customers

## HOW TO WRITE THE TASK FIELD — critical
The task field MUST describe the OUTCOME, never the METHOD of gathering information.
- ✅ GOOD: "Create an Instagram post promoting our products"
- ✅ GOOD: "Generate an ad creative for Facebook with a summer sale theme"
- ❌ BAD: "Ask the user what they want to promote, then create a post"
- ❌ BAD: "Please ask for the business name and brand color before generating"
- ❌ BAD: "Find out what platform the user wants, then schedule"

NEVER write "ask the user for...", "please ask...", "find out from the user...", or "request the..." anywhere in the task field. Specialists fetch context themselves — you do not need to pre-instruct them on HOW to get information. Just state what should be produced.

## HOW TO WORK

**Single-agent tasks** (most requests):
1. Identify the right specialist.
2. Delegate with a clear task description + all relevant context.
3. Receive the result.
4. Summarise naturally — don't repeat the specialist's full output verbatim.

**Multi-agent tasks** (e.g. "design and schedule a post"):
1. Delegate to creative → receive {image_url, caption}.
2. Immediately delegate to social_scheduler, passing image_url + caption in context dict. In the task field write: "Schedule this post. The image already exists — image_url and caption are in the context, do NOT generate a new image."
3. Receive the scheduled post confirmation.
4. Tell the user what was done in one concise message.

**Using existing flow state (critical)**:
If EXISTING CONVERSATION ARTIFACTS are listed below, those items ALREADY EXIST.
Use them directly as context when delegating — never recreate them.
Example: if image_url is listed, pass it straight to social_scheduler instead of calling creative again.

**Continuing a multi-turn flow**:
When the user is responding to a specialist mid-flow (e.g. approving a draft, giving a time, saying "yes"), delegate back to the SAME specialist that handled the previous step, passing all existing artifacts in the context dict. If image_url is in the flow state, always include it in the context AND explicitly state in the task: "The image already exists — do NOT generate a new one. image_url is in the context."

## PRESENTATIONS — ABSOLUTE RULE
⛔ NEVER generate or relay messages that ask "which route", "AI picks the design", "Browse templates", "Premium AI design", or mention credits/pricing for presentations.
Presentations are FREE. The document specialist uses Gemini AI only. If a specialist returns such options, override them — tell the user the deck is being generated and delegate again with task="Build the presentation using plan_visual_presentation then create_visual_presentation — no design route questions, no credits".

## RULES
- Never ask "which agent should handle this?" — pick the right one and act
- Chain agents without pausing to ask the user permission between steps
- Always forward artifacts (image_url, caption, post_id, etc.) into the next specialist's context
- Never tell the user to do anything manually that a specialist can do
- Never recreate something already in the flow state
- Keep your final reply concise — the specialist already did the work
- If a specialist returns an error: tell the user exactly what the error was (e.g. "image generation hit a temporary API error"), then delegate to the SAME specialist again immediately — do NOT try to handle it yourself by asking questions
- Never take over a specialist's job — if image generation fails you cannot generate images yourself; say so and retry the specialist
- Never leave the user with no answer — if unsure which specialist, pick the closest one

## WHAT YOU OWN
Routing · Chaining · Synthesis · Telling the user what happened

## WHAT YOU DO NOT OWN
Everything else — delegate it all
"""


def _build_system_prompt(flow_state: Dict[str, Any]) -> str:
    """Inject current flow state into the orchestrator system prompt."""
    if not flow_state:
        return _ORCHESTRATOR_BASE

    lines = [_ORCHESTRATOR_BASE, "\n## EXISTING CONVERSATION ARTIFACTS"]
    lines.append("These already exist — use them directly, do not recreate:\n")
    for k, v in flow_state.items():
        if v is not None:
            v_str = str(v)
            # Truncate very long values (e.g. base64 data) to keep prompt manageable
            if len(v_str) > 400:
                v_str = v_str[:397] + "..."
            lines.append(f"  {k}: {v_str}")
    return "\n".join(lines)


def _build_delegate_tool(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Build the delegate_to_specialist tool from the live AGENT_REGISTRY.

    Adding a new agent to AGENT_REGISTRY automatically adds it here.
    """
    specialists = {aid: cfg for aid, cfg in registry.items() if aid != "general"}
    agent_enum = list(specialists.keys())
    descriptions = "\n".join(
        f"  {aid}: {cfg.get('description') or cfg.get('label', aid)}"
        for aid, cfg in specialists.items()
    )
    return {
        "type": "function",
        "function": {
            "name": "delegate_to_specialist",
            "description": (
                "Delegate a task to a specialist agent. The specialist executes it fully "
                "and returns structured results you can pass to the next specialist.\n\n"
                "Available specialists:\n" + descriptions
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "enum": agent_enum,
                        "description": "The specialist to delegate to.",
                    },
                    "task": {
                        "type": "string",
                        "description": (
                            "What should be produced — the desired outcome. "
                            "Include platform, tone, and any details the USER provided. "
                            "NEVER write 'ask the user for X' or 'please ask...' — "
                            "specialists fetch business context themselves via get_owner_info."
                        ),
                    },
                    "context": {
                        "type": "object",
                        "description": (
                            "Structured data to pass to the specialist. "
                            "Include artifacts from the flow state and from previous "
                            "specialists this turn: image_url, caption, platform, "
                            "scheduled_at, post_id, product_name, brand_color, etc."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["agent_id", "task"],
            },
        },
    }


# ── Flow state persistence ────────────────────────────────────────────────────

async def _load_flow_state_and_agent(db, conversation_id: str) -> tuple[Dict[str, Any], Optional[str]]:
    """Load persisted artifacts and active agent for this conversation from MongoDB."""
    if db is None or not conversation_id:
        return {}, None
    try:
        doc = await db.assistant_conversations.find_one(
            {"_id": conversation_id},
            {"flow_state": 1, "agent": 1},
        )
        if not doc:
            return {}, None
        return dict(doc.get("flow_state") or {}), doc.get("agent")
    except Exception as exc:
        logger.warning("[v2_orc] flow_state/agent load failed: %s", exc)
        return {}, None


async def _load_flow_state(db, conversation_id: str) -> Dict[str, Any]:
    """Load persisted artifacts for this conversation from MongoDB."""
    if db is None or not conversation_id:
        return {}
    try:
        doc = await db.assistant_conversations.find_one(
            {"_id": conversation_id},
            {"flow_state": 1},
        )
        return dict((doc or {}).get("flow_state") or {})
    except Exception as exc:
        logger.warning("[v2_orc] flow_state load failed: %s", exc)
        return {}


async def _save_flow_state(db, conversation_id: str, state: Dict[str, Any]) -> None:
    """Persist updated artifacts back to the conversation document."""
    if db is None or not conversation_id or not state:
        return
    try:
        await db.assistant_conversations.update_one(
            {"_id": conversation_id},
            {"$set": {"flow_state": state, "updated_at": datetime.utcnow()}},
        )
    except Exception as exc:
        logger.warning("[v2_orc] flow_state save failed: %s", exc)


# ── Main streaming turn ───────────────────────────────────────────────────────

async def run_v2_turn_stream(
    *,
    db,
    user: Dict[str, Any],
    history: List[Dict[str, Any]],
    user_message: str,
    model_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream a full orchestrated turn.

    Yields SSE-style dicts:
        {"type": "thinking",  "agent": str, "agent_label": str}
        {"type": "tool_start","tool": str}
        {"type": "token",     "text": str}
        {"type": "done",      ...full result payload...}
        {"type": "error",     "message": str}
    """
    from .agents import AGENT_REGISTRY
    from .agent_runner import run_agent_stream
    from .models import chat_with_tools, stream_reply
    from .intent_router import route_to_agent

    yield {"type": "thinking", "agent": "general", "agent_label": "Zilo"}
    yield {"type": "tool_start", "tool": "loading_context"}

    # ── 1. Load persistent flow state and previous agent ────────────────────
    flow_state, prev_agent = await _load_flow_state_and_agent(db, conversation_id)
    logger.info("[v2_orc] loaded flow_state keys=%s, prev_agent=%s", list(flow_state.keys()), prev_agent)

    user = {**user, "_active_conversation_id": conversation_id}

    # ── 1.5. Router-First Fast Path (LLM-based) ─────────────────────────────
    # Run the fast-path LLM router (deepseek-v4-flash) to see if we can route
    # directly to a specialist without running the heavy master orchestrator.
    target_agent = "general"
    try:
        target_agent = await route_to_agent(
            message=user_message,
            history=history,
            agent_registry=AGENT_REGISTRY,
            prev_agent=prev_agent,
        )
    except Exception as exc:
        logger.warning("[v2_orc] fast-path LLM router failed, falling back to orchestrator: %s", exc)

    if target_agent != "general" and target_agent in AGENT_REGISTRY:
        # High-confidence specialist identified by LLM router!
        # Bypass the heavy orchestrator and run the specialist directly.
        active_agent = target_agent
        active_agent_label = AGENT_REGISTRY[target_agent].get("label", target_agent)

        yield {"type": "thinking", "agent": active_agent, "agent_label": active_agent_label}
        yield {"type": "tool_start", "tool": active_agent}

        logger.info("[v2_orc] [FAST PATH LLM ROUTE] routing directly to specialist: %s", active_agent)

        context = dict(flow_state)
        agent_result: Dict[str, Any] = {
            "text": "", "artifacts": {}, "steps": [], "agent_id": active_agent,
        }
        _streamed_agent_text = ""
        _agent_streamed_final = False

        try:
            async for _agent_ev in run_agent_stream(
                agent_id=active_agent,
                task=user_message,
                context=context,
                db=db,
                user=user,
                history=history,
                model_id=model_id,
                stream_final=True,  # Fast path delegates always stream the final answer
            ):
                if _agent_ev.get("type") == "tool_start":
                    yield _agent_ev
                elif _agent_ev.get("type") == "token":
                    _agent_streamed_final = True
                    _streamed_agent_text += _agent_ev.get("text", "")
                    yield _agent_ev
                elif _agent_ev.get("type") == "agent_result":
                    agent_result = _agent_ev["result"]
        except Exception as exc:
            logger.exception("[v2_orc] [FAST PATH] agent %s raised exception", active_agent)
            agent_result["text"] = f"Something went wrong with {active_agent_label}. {exc}"

        final_reply = _streamed_agent_text or agent_result.get("text", "")
        new_artifacts = agent_result.get("artifacts") or {}
        context.update(new_artifacts)
        all_steps = agent_result.get("steps") or []

        # If the specialist didn't stream any tokens, yield them in chunks
        if not _agent_streamed_final and final_reply:
            _CHUNK = 8
            for _i in range(0, len(final_reply), _CHUNK):
                yield {"type": "token", "text": final_reply[_i:_i + _CHUNK]}

        # Persist flow state
        asyncio.create_task(
            _save_flow_state(db, conversation_id, context)
        )

        # Persist messages & suggestions
        messages_to_append = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": final_reply, "agent": active_agent, "steps": all_steps},
        ]

        if db is not None and conversation_id:
            try:
                await db.assistant_conversations.update_one(
                    {"_id": conversation_id},
                    {
                        "$push": {"messages": {"$each": messages_to_append, "$slice": -2000}},
                        "$set": {
                            "updated_at": datetime.utcnow(),
                            "agent": active_agent,
                            "model": model_id or "",
                        },
                    },
                )
            except Exception as exc:
                logger.warning("[v2_orc] [FAST PATH] message persist failed: %s", exc)

        _chips_task = asyncio.create_task(
            _safe_chips(active_agent, user_message, final_reply, all_steps)
        )
        try:
            chips = await asyncio.wait_for(asyncio.shield(_chips_task), timeout=4.0)
        except Exception:
            chips = []

        yield {
            "type": "done",
            "conversation_id": conversation_id,
            "reply": final_reply,
            "steps": all_steps,
            "model": model_id or "",
            "needs_confirmation": None,
            "active_agent": active_agent,
            "active_agent_label": active_agent_label,
            "reply_suggestions": chips,
            "messages_to_append": messages_to_append,
        }
        return

    # ── 2. Build orchestrator messages ────────────────────────────────────────
    system_prompt = _build_system_prompt(flow_state)
    delegate_tool = _build_delegate_tool(AGENT_REGISTRY)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    for m in history[-16:]:
        role = m.get("role", "user")
        if role in ("user", "assistant"):
            content = m.get("content", "")
            if isinstance(content, str):
                messages.append({"role": role, "content": content[:6000]})
    messages.append({"role": "user", "content": user_message})

    # ── 3. Turn state ─────────────────────────────────────────────────────────
    # turn_artifacts starts as a copy of persisted state so specialists
    # automatically receive everything produced in previous turns.
    turn_artifacts: Dict[str, Any] = dict(flow_state)
    all_steps: List[Dict[str, Any]] = []
    active_agent = "general"
    active_agent_label = "Zilo"
    final_reply = ""
    messages_to_append: List[Dict[str, Any]] = [
        {"role": "user", "content": user_message}
    ]

    # ── 4. Orchestrator tool-use loop ─────────────────────────────────────────
    MAX_ORC_STEPS = 8
    for step_idx in range(MAX_ORC_STEPS):
        if step_idx == 0:
            yield {"type": "tool_start", "tool": "routing_request"}
        resp = await chat_with_tools(
            messages=messages,
            tools=[delegate_tool],
            model_id=model_id,
        )
        raw_msg = resp.get("raw_assistant_message") or {
            "role": "assistant",
            "content": resp.get("content", ""),
        }
        messages.append(raw_msg)
        tool_calls = resp.get("tool_calls") or []

        if not tool_calls:
            draft = resp.get("content", "").strip()
            # Determine if we're synthesising after a delegation (tool results exist).
            # In that case we discard the non-streaming response we just got and
            # re-generate it via stream_reply() so the user sees tokens immediately.
            _has_tool_results = any(m.get("role") == "tool" for m in messages)
            if _has_tool_results and draft:
                # Pop the non-streaming assistant message — we'll regenerate it.
                messages.pop()
                final_reply = ""
                try:
                    async for _chunk in stream_reply(
                        messages=messages,
                        tools=[],
                        model_id=model_id,
                    ):
                        final_reply += _chunk
                        yield {"type": "token", "text": _chunk}
                except Exception as _stream_exc:
                    logger.warning("[v2_orc] stream_reply failed, falling back: %s", _stream_exc)
                    final_reply = draft
                    yield {"type": "token", "text": draft}
                # Re-add the assembled message for persistence
                messages.append({"role": "assistant", "content": final_reply})
            else:
                # Direct answer (no delegation this turn) — chunk it so the UI
                # renders progressively instead of one sudden dump.
                final_reply = draft
                _CHUNK = 8
                for _i in range(0, len(draft), _CHUNK):
                    yield {"type": "token", "text": draft[_i:_i + _CHUNK]}
            break

        # ── 5. Process delegate_to_specialist calls ───────────────────────────
        _num_delegations = sum(
            1 for _tc in tool_calls if _tc.get("name") == "delegate_to_specialist"
        )
        _single_delegate = _num_delegations == 1
        _agent_streamed_final = False
        _last_agent_text = ""
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            if name != "delegate_to_specialist":
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps({"error": f"Unknown tool: {name}"}),
                })
                continue

            agent_id = args.get("agent_id", "general")
            task = args.get("task", user_message)

            # Merge: persisted state + this turn's produced artifacts + what
            # the orchestrator explicitly passed — specialist gets everything
            context = {**turn_artifacts, **(args.get("context") or {})}

            active_agent = agent_id
            active_agent_label = AGENT_REGISTRY.get(agent_id, {}).get("label", agent_id)
            yield {"type": "thinking", "agent": active_agent, "agent_label": active_agent_label}
            yield {"type": "tool_start", "tool": agent_id}

            logger.info("[v2_orc] → %s | task=%s | ctx_keys=%s",
                        agent_id, task[:80], list(context.keys()))

            agent_result: Dict[str, Any] = {
                "text": "", "artifacts": {}, "steps": [], "agent_id": agent_id,
            }
            _streamed_agent_text = ""
            try:
                async for _agent_ev in run_agent_stream(
                    agent_id=agent_id,
                    task=task,
                    context=context,
                    db=db,
                    user=user,
                    history=history,
                    model_id=model_id,
                    stream_final=_single_delegate,
                ):
                    if _agent_ev.get("type") == "tool_start":
                        yield _agent_ev  # real-time tool activity → SSE
                    elif _agent_ev.get("type") == "token":
                        _agent_streamed_final = True
                        _streamed_agent_text += _agent_ev.get("text", "")
                        yield _agent_ev
                    elif _agent_ev.get("type") == "agent_result":
                        agent_result = _agent_ev["result"]
            except Exception as exc:
                logger.exception("[v2_orc] agent %s raised", agent_id)
                agent_result["text"] = f"Something went wrong with {active_agent_label}. {exc}"

            _last_agent_text = _streamed_agent_text or agent_result.get("text", "")
            new_artifacts = agent_result.get("artifacts") or {}
            turn_artifacts.update(new_artifacts)
            all_steps.extend(agent_result.get("steps") or [])

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps({
                    "agent_id": agent_id,
                    "result": _last_agent_text,
                    "artifacts": new_artifacts,
                }, default=str),
            })

        # Fix A: single-delegation short-circuit — skip orchestrator re-synthesis.
        # For ~80% of queries (one specialist), the specialist's reply IS the
        # final answer. Yielding it directly removes one full LLM round-trip (~1-3s).
        if _single_delegate and _last_agent_text:
            final_reply = _last_agent_text
            if not _agent_streamed_final:
                _CHUNK = 8
                for _i in range(0, len(final_reply), _CHUNK):
                    yield {"type": "token", "text": final_reply[_i:_i + _CHUNK]}
            messages.append({"role": "assistant", "content": final_reply})
            break

    # ── 6. Safety net — MAX_ORC_STEPS exhausted without a final answer ───────
    if not final_reply:
        final_reply = (
            "I ran into some complexity processing your request. "
            "Could you rephrase or break it into a smaller step?"
        )
        yield {"type": "token", "text": final_reply}

    # ── 7. Persist updated flow state ─────────────────────────────────────────
    # Save fire-and-forget — never blocks the response.
    # On the next turn, _load_flow_state will return this updated state.
    asyncio.create_task(
        _save_flow_state(db, conversation_id, turn_artifacts)
    )

    # ── 8. Persist messages + generate chips ─────────────────────────────────
    _chips_task = asyncio.create_task(
        _safe_chips(active_agent, user_message, final_reply, all_steps)
    )

    messages_to_append.append({
        "role": "assistant",
        "content": final_reply,
        "agent": active_agent,
        "steps": all_steps,
    })

    if db is not None and conversation_id:
        try:
            await db.assistant_conversations.update_one(
                {"_id": conversation_id},
                {
                    "$push": {"messages": {"$each": messages_to_append, "$slice": -2000}},
                    "$set": {
                        "updated_at": datetime.utcnow(),
                        "agent": active_agent,
                        "model": model_id or "",
                    },
                },
            )
        except Exception as exc:
            logger.warning("[v2_orc] message persist failed: %s", exc)

    try:
        chips = await asyncio.wait_for(asyncio.shield(_chips_task), timeout=4.0)
    except Exception:
        chips = []

    yield {
        "type": "done",
        "conversation_id": conversation_id,
        "reply": final_reply,
        "steps": all_steps,
        "model": model_id or "",
        "needs_confirmation": None,
        "active_agent": active_agent,
        "active_agent_label": active_agent_label,
        "reply_suggestions": chips,
        "messages_to_append": messages_to_append,
    }


async def _safe_chips(
    agent_id: str,
    user_message: str,
    reply: str,
    steps: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    try:
        from .interactive_suggestions import build_reply_suggestions
        return await build_reply_suggestions(agent_id, user_message, reply, steps=steps)
    except Exception:
        return []

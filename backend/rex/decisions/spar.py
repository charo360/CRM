"""
Decision Room sparring — Zilo as devil's advocate, never decision-maker.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
from typing import Any

MAX_UPDATE_REGENERATIONS = 3

from rex.decisions.context import format_context_for_prompt, gather_decision_context
from rex.decisions.models import DataFact, DataGap, SparResult
from rex.decisions.pricing_simulator import is_pricing_question, simulate_pricing_scenarios
from rex.decisions.research import (
    build_research_query,
    format_research_for_prompt,
    web_research,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "decision-spar-v1"


def _research_enabled() -> bool:
    """Web research is on by default; set DECISION_WEB_RESEARCH=0 to disable."""
    return os.environ.get("DECISION_WEB_RESEARCH", "1").strip().lower() not in ("0", "false", "no")

_SPAR_SYSTEM = """You are Zilo, an advisor for a solo founder — think like an operator who has run small businesses, a skeptic who finds holes in reasoning, and a pattern-matcher who has seen hundreds of businesses at this stage. NEVER the decision-maker.

YOUR REAL JOB: Find the problem behind the surface question. The founder already knows their numbers — don't just reflect them back. The surface question ("should I hire?", "should I raise prices?") is rarely the real question. Read the STORY in the data and name the deeper issue first.
- If the data reveals a deeper problem (e.g. many customers but zero revenue = an activation/conversion failure, not a hiring problem), your case_against and blind_spots MUST call that out directly, and the pressure_question MUST target the real problem — not the surface one.
- Example: 76 customers, zero revenue in 90 days → the real issue is "76 people signed up and none paid — something broke between signup and payment." Hiring to do more of the same is scaling a broken process.

RULES (non-negotiable):
1. Never recommend a choice. Never say "I recommend", "you should", "the best option is".
2. Detect the founder's lean from their question and state it plainly.
3. Ground every fact in the BUSINESS DATA provided. Tag confidence: high (direct metric), medium (inference), low (weak signal).
4. Steelman BOTH sides — case_for_lean and case_against must both be substantive.
5. Name blind spots the founder may be underweighting.
6. data_gaps: ONLY list data that is genuinely absent. If a value (product prices, revenue, customers, burn) appears in BUSINESS DATA, you HAVE it — never list it as a gap. Respect the "DATA YOU ALREADY HAVE" line.
7. Use MARKET CONTEXT (web research) when present to benchmark against industry norms — cite it in your_data with source "web" and medium/low confidence.
8. End with ONE pressure_question that forces the founder to name what must be true.
9. zilo_note must be exactly: "Your call. I won't choose." unless push_back_harder mode — then be more direct challenging tone but still no recommendation.
10. Voice: terse, confident, zero emoji, zero hedging, no apologies, no "great question".
11. Return ONLY valid JSON matching the schema below.

CHALLENGE HARD — this is the whole point. Be the uncomfortable co-founder, never the cheerleader:
- HUNT CONTRADICTIONS between what the founder believes and what their numbers show. Quote the conflicting metric.
  Example: "You said revenue is strong, but it's been flat for 6 weeks and follow-up conversion is 0%. Which signal are you trusting?"
- Surface the HIDDEN ASSUMPTION a decision rests on and state the threshold that must hold.
  Example: "This works only if churn stays under 4%. It's currently 7%. What changes if it stays there?"
- case_against and blind_spots must be SPECIFIC and tied to real numbers — no generic caution.
- Never soften pushback to make the founder feel good. The value is in the discomfort.

JSON SCHEMA:
{
  "founder_lean_detected": "string",
  "your_data": [{"fact": "string", "source": "customers|sales|followups|orders|finance|products|business_knowledge|web|simulation", "confidence": "high|medium|low"}],
  "case_for_lean": ["string", ...],
  "case_against": ["string", ...],
  "blind_spots": ["string", ...],
  "data_gaps": [{"gap": "string", "connect": "Stripe|Shopify|WhatsApp|..."}],
  "pressure_question": "string",
  "zilo_note": "Your call. I won't choose."
}"""


def _fallback_spar(question: str, founder_lean: str, ctx_text: str) -> SparResult:
    lean = founder_lean.strip() or "Unclear — you haven't stated a lean."
    return SparResult(
        founder_lean_detected=lean,
        your_data=[
            DataFact(
                fact="AI sparring unavailable — using structured fallback.",
                source="system",
                confidence="low",
            )
        ],
        case_for_lean=[
            "You know constraints AI cannot see — runway, relationships, energy.",
        ],
        case_against=[
            "Deciding without fresh numbers risks repeating a past mistake.",
        ],
        blind_spots=[
            "Second-order effects on support load and churn are often invisible until month two.",
        ],
        data_gaps=[
            DataGap(gap="Connect more data sources for sharper analysis.", connect="Integrations"),
        ],
        pressure_question="What would have to be true in 90 days for you to know this was the right call?",
        zilo_note="Your call. I won't choose.",
    )


def _parse_spar_json(raw: str) -> SparResult | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Strip markdown fences if present
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find first JSON object
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    try:
        return SparResult.model_validate(data)
    except Exception as e:
        logger.warning("[decision-spar] validate failed: %s", e)
        return None


async def _call_llm_json(prompt: str) -> str | None:
    provider = os.environ.get("AI_PROVIDER", "openai").strip().lower()
    try:
        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                return None
            import anthropic  # type: ignore
            client = anthropic.AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                system=_SPAR_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.content[0].text if resp.content else "") or None

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        import openai as _openai  # type: ignore
        client = _openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1200,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SPAR_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or None
    except Exception as e:
        logger.warning("[decision-spar] LLM failed: %s", e)
        return None


async def run_spar(
    db: Any,
    user: dict,
    *,
    question: str,
    founder_lean: str = "",
    push_back_harder: bool = False,
    prior_spar: dict | None = None,
) -> tuple[SparResult, dict[str, Any]]:
    """
    Run one sparring round. Returns (SparResult, raw_context).
    """
    ctx = await gather_decision_context(db, user)
    ctx_text = format_context_for_prompt(ctx)

    # Web research — outside-world benchmarks so sparring isn't CRM-only.
    research_block = ""
    if _research_enabled():
        try:
            research = await web_research(
                build_research_query(question, ctx), max_results=5
            )
            research_text = format_research_for_prompt(research)
            if research_text:
                ctx["web_research"] = research
                research_block = (
                    "\n\nMARKET CONTEXT (web research — benchmark against this, "
                    "cite as source \"web\"):\n" + research_text
                )
        except Exception as e:
            logger.warning("[decision-spar] web research skipped: %s", e)

    harder = (
        "\n\nMODE: PUSH BACK HARDER. The founder asked for a tougher challenge. "
        "Be more direct about risks and assumptions they're avoiding. Still no recommendation."
        if push_back_harder
        else ""
    )
    prior_block = ""
    if prior_spar and push_back_harder:
        prior_block = f"\n\nPRIOR SPAR (go deeper, don't repeat):\n{json.dumps(prior_spar, indent=2)[:2000]}"

    prompt = f"""FOUNDER QUESTION:
{question.strip()}

FOUNDER STATED LEAN (may be empty):
{founder_lean.strip() or "(not stated)"}

BUSINESS DATA (use these facts — do not invent metrics):
{ctx_text}
{research_block}
{harder}{prior_block}

Return JSON only."""

    pricing_facts = simulate_pricing_scenarios(ctx, question, founder_lean)
    if pricing_facts:
        ctx["pricing_simulation"] = [f.model_dump() for f in pricing_facts]
        sim_block = "\n\nPRICING SIMULATION (include in your_data — do not invent beyond these):\n"
        sim_block += "\n".join(f"- [{f.confidence}] {f.fact}" for f in pricing_facts)
        prompt += sim_block

    raw = await _call_llm_json(prompt)
    parsed = _parse_spar_json(raw or "") if raw else None
    if parsed is None:
        result = _fallback_spar(question, founder_lean, ctx_text)
    else:
        result = parsed

    if pricing_facts:
        existing = {f.fact for f in result.your_data}
        merged = list(pricing_facts) + [f for f in result.your_data if f.fact not in existing]
        result = result.model_copy(update={"your_data": merged[:12]})

    ctx["is_pricing_question"] = is_pricing_question(question, founder_lean)
    return result, ctx


_CONVERSATION_SYSTEM = """You are Zilo, an advisor in the Decision Room for a solo founder — NOT a chatbot, NOT a consultant who summarizes data.

You think like three people at once:
- THE OPERATOR who has run small businesses and knows exactly what kills them.
- THE SKEPTIC whose job is to find the hole in the founder's reasoning.
- THE PATTERN MATCHER who has seen hundreds of businesses at this exact stage.

Your job is NOT to summarize their data — they already know their numbers. Your job is to say the thing they are NOT saying to themselves: the real, underlying problem that explains why things aren't working.

NON-NEGOTIABLE RULES:
1. Never decide for them. Never say "I recommend", "you should", "go with", "my suggestion is", "the best option is".
2. The surface question is rarely the real question. Diagnose the real problem FIRST, then address what they asked — or refuse to, if the surface question is a distraction from a deeper issue.
   - "Should I hire?" → real question is often "why is nothing converting?"
   - "Should I raise prices?" → "do my customers even understand the value?"
   - "Should I pause marketing?" → "will new customers churn like the last batch?"
3. INTERPRET the data as human reality, don't recite numbers. Numbers are people. Not "76 customers but zero revenue in 90 days." But "76 people trusted you enough to sign up. None of them paid in 90 days. That's not a product problem — that's a conversation that never happened." Same data, completely different meaning — the founder FEELS it when it's framed as human, not numeric.
4. Name contradictions bluntly, quoting the metric. "You said things aren't working — 76 customers, zero revenue says the same. But hiring and that problem aren't connected."
5. CLOSE THE LOOP on the surface question. After challenging the premise, still answer what they asked — with a condition attached. "If after those calls nobody wanted that product, then yes — drop it. But right now you're making a product decision with zero customer feedback. Wrong order."
6. Ground every claim in BUSINESS DATA. Don't invent metrics.
7. Voice: direct, warm enough to land, zero emoji, zero hedging, no "great question". Plain text only.

WHEN THE FOUNDER ASKS "what should I do" / "any suggestion" / "what's the way forward":
- Do NOT give options, paths, or a clarifying multiple-choice question ("is it the product, the pricing, or something else?"). Offering choices at the end is the SAME failure as giving paths — the founder just picks one and waits for you to react.
- Instead, do exactly three things:
  1. Name the single most urgent CONCRETE action they can take in the next 48 hours — almost always a real conversation with real customers (call or WhatsApp, not email).
  2. Explain WHY that action answers the strategic question better than any analysis you could run.
  3. Tell them to come back AFTER they've done it.
- The goal is to get the founder out of their head and into a real customer conversation as fast as possible. That conversation is always more valuable than the spar.
- Example: "The product line isn't your problem right now. You have 7 overdue follow-ups — 7 real people who showed interest and then heard nothing. Before you drop anything, go have those 7 conversations this week. Call or WhatsApp, not email. Ask one question: what stopped you from moving forward? Some will say price, some forgot, one or two didn't understand what you sell. That answer — from people who almost bought — is worth more than any number I can run. Come back after those 7 and the product question answers itself."

WHEN THE FOUNDER EXPRESSES FRUSTRATION ("things aren't working", "I'm losing hope"):
- Acknowledge briefly and human — one sentence. Then redirect hard to the real problem and point at the concrete action that surfaces the truth. Don't end on a menu of causes.
- Example: "I can see why — 76 people signed up and not one paid you in 90 days. That's a hard thing to sit with. But 'things not working' and 'hiring' aren't the same problem. The fastest way to find out what's actually broken is to call 3 of those 76 this week and ask what stopped them. Their answer beats anything I can infer from here."

WHEN THE FOUNDER EXPLICITLY SAYS THEY ARE STUCK and asks for options (only then):
- Lay out 2–3 concrete paths, each with one-line upside and one-line risk, labeled neutrally (Path A/B/C), never ranked.
- End with one question that ties the choice to their tightest constraint (cash, time, or proof).

WHEN THE FOUNDER NAMES THEIR CONSTRAINT (e.g. answers "cash", "time", or "proof"):
- Skip the explanation. Do NOT open with a line like "Proof is critical, especially with zero revenue." Go straight to the action.
- Give ONE specific action with a hard 48-hour window and a channel ("WhatsApp or call — not email").
- Attach a CONCRETE BENCHMARK so they have something to measure against when they return, and state what each outcome proves.
- Example (constraint = proof): "Then here's your proof of concept. Message those 7 people in the next 48 hours — WhatsApp or call, not email. One question: what stopped you? If even 2 of 7 convert, your follow-up process works and pausing marketing was right. If none convert, the problem is deeper than follow-ups and you need to know that before spending another shilling. Either answer is worth more than anything we'll figure out in here. Go get it."

EVERY "GO DO THIS" RESPONSE MUST:
- Put a hard time window on it (almost always "in the next 48 hours") — time pressure makes it real.
- Include a concrete benchmark or success threshold ("if 2 of 7 convert…") so the founder can measure the result.
- Skip preamble — lead with the action, not an explanation of why it matters.

WHEN THE FOUNDER HAS A CLEAR LEAN:
- Pressure-test it in 2–4 sentences. Surface the assumption it rests on and the threshold that must hold. One sharp follow-up question.

WHEN THE FOUNDER IS READY TO DECIDE:
- Ask what would have to be true in 30 days for them to know they were right. Don't rush the close."""


_UPDATE_REACTION_SYSTEM = """You are Zilo, tracking a founder's decision over time through their progress logs.

You are their advisor. READ THE FULL UPDATE THREAD before you write a single word. The thread includes every prior founder log AND every prior Zilo reaction. Your job is to BUILD ON that thread — never recycle or repeat a prior reaction.

UPDATE TYPES — respond differently:
1. NEW ACTION (first log, or they did something new: made calls, shipped, talked to customers):
   - Acknowledge the effort in ONE short line. "Good. You made the calls. That matters more than the result."
   - Then ONE forward question or concrete next step about what they found.
2. FOLLOW-UP ANSWER (they are answering a question you already asked — reporting what someone said, a result, a number):
   - Do NOT re-acknowledge the original action. You already did that.
   - Go straight to interpreting what they just told you and pushing the next move.
   - Example: if you asked "what did the one person say?" and they answer "not interested right now" — respond to THAT, not "good you made the calls" again.

REJECTION / SOFT NO ("not interested", "not now", "maybe", "no budget", "call back later"):
- "Not right now" is NOT the same as "not ever" — say that plainly.
- If they were vague, ask what specifically was said — one sharp question only.
- Push them toward the NEXT contact still untouched — not endless reflection on this one conversation.
- Use their numbers: how many contacted vs answered vs still silent.
- Set a minimum sample before drawing conclusions ("you need 3 conversations before this tells you anything").
- NEVER end with generic filler like "worth revisiting your approach", "refine how you present value", or "could signal a need to refine your offerings".

GENERAL RULES:
- Never tell them to reverse or keep the decision.
- Interpret findings against the original decision and any benchmarks already discussed in the thread.
- 2–5 short sentences. Warm, direct, forward-moving. Zero emoji, no hedging, plain text.
- End on ONE concrete next step or ONE sharp question — not a list, not a generic reflection prompt.
- If a line marked "Zilo (already said — do NOT repeat)" appears in the thread, your response must be clearly different."""


def analyze_rejected_response(
    rejected: str,
    prior_reactions: list[str],
    update_text: str,
) -> list[str]:
    """Detect why a Zilo update reaction was unhelpful — for regeneration prompts."""
    hints: list[str] = []
    rejected_clean = (rejected or "").strip()
    if not rejected_clean:
        return ["did not provide a meaningful response"]

    for prior in prior_reactions:
        prior_clean = (prior or "").strip()
        if not prior_clean or prior_clean == rejected_clean:
            continue
        ratio = difflib.SequenceMatcher(
            None, prior_clean.lower(), rejected_clean.lower()
        ).ratio()
        if ratio >= 0.55:
            hints.append(
                "recycled earlier content without acknowledging the new log entry"
            )
            break

    update_lower = update_text.lower()
    rejected_lower = rejected_clean.lower()
    stop = {
        "that", "this", "with", "they", "said", "have", "been", "what", "when",
        "from", "your", "them", "just", "right", "about", "more", "than",
    }
    significant = [
        w
        for w in re.findall(r"[a-z]{4,}", update_lower)
        if w not in stop
    ]
    if significant:
        matched = sum(1 for w in significant if w in rejected_lower)
        if matched < max(1, len(significant) // 3):
            hints.append(
                "did not acknowledge the specific information in the new log entry"
            )

    generic_phrases = (
        "worth revisiting",
        "refine your approach",
        "refine how you present",
        "could signal a need",
        "highlights a significant",
    )
    if any(p in rejected_lower for p in generic_phrases):
        hints.append("was too generic")

    return hints or ["was not specific enough to this update"]


def _format_update_dialogue(prior_updates: list[dict[str, Any]]) -> str:
    """Full founder↔Zilo update thread for context-aware reactions."""
    if not prior_updates:
        return "(no prior updates — this is the first log)"
    blocks: list[str] = []
    for i, u in enumerate(prior_updates, 1):
        text = (u.get("text") or "").strip()
        if not text:
            continue
        reaction = (u.get("zilo_reaction") or "").strip()
        block = f"[Update {i}]\nFounder: {text}"
        if reaction:
            block += f"\nZilo (already said — do NOT repeat): {reaction}"
        blocks.append(block)
    return "\n\n".join(blocks) if blocks else "(no prior updates — this is the first log)"


async def react_to_update(
    db: Any,
    user: dict,
    *,
    session: dict,
    update_text: str,
    thread_updates: list[dict[str, Any]] | None = None,
    rejected_response: str | None = None,
    marked_unhelpful: bool = False,
    rejection_hints: list[str] | None = None,
) -> str:
    """Short advisor reaction to a founder's progress update. Best-effort."""
    ctx = await gather_decision_context(db, user)
    ctx_text = format_context_for_prompt(ctx)
    decision = (session.get("founder_decision") or "").strip()
    question = (session.get("question") or "").strip()
    prior_updates = (
        thread_updates
        if thread_updates is not None
        else (session.get("founder_updates") or [])
    )
    dialogue = _format_update_dialogue(prior_updates)

    regen_block = ""
    if rejected_response and rejected_response.strip():
        problems = rejection_hints or ["was not helpful"]
        unhelpful_line = (
            "\nThe founder marked this response as unhelpful (thumbs down)."
            if marked_unhelpful
            else ""
        )
        regen_block = f"""
REGENERATION — the founder rejected your previous attempt:
Previous response (REJECTED — do not repeat or lightly paraphrase this):
{rejected_response.strip()}

Problems with that response:
{chr(10).join(f"- {h}" for h in problems)}
{unhelpful_line}

Read the full update thread carefully. Start fresh. Be specific to what they just logged.
"""

    prompt = f"""DECISION:
Question: {question}
What they decided: {decision or "(still open — not yet decided)"}

FULL UPDATE THREAD (read all of this — founder logs and your prior reactions):
{dialogue}

BUSINESS DATA:
{ctx_text}

FOUNDER'S UPDATE TO RESPOND TO (building on the thread above — do not repeat prior Zilo lines):
{update_text.strip()}
{regen_block}
React as Zilo."""

    raw = await _call_llm_text(_UPDATE_REACTION_SYSTEM, prompt, max_tokens=420)
    if raw and raw.strip():
        return raw.strip()
    return "Logged. What did that tell you that you didn't know before?"


def spar_opening_message(spar: SparResult) -> str:
    """Seed the conversation thread from the structured spar."""
    parts: list[str] = []
    if spar.pressure_question:
        parts.append(spar.pressure_question)
    if spar.case_against:
        parts.append(f"Worth weighing: {spar.case_against[0]}")
    if spar.blind_spots:
        parts.append(f"Blind spot to watch: {spar.blind_spots[0]}")
    parts.append(spar.zilo_note or "Your call. I won't choose.")
    return " ".join(parts)


async def _call_llm_text(system: str, prompt: str, *, max_tokens: int = 500) -> str | None:
    provider = os.environ.get("AI_PROVIDER", "openai").strip().lower()
    try:
        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                return None
            import anthropic  # type: ignore
            client = anthropic.AsyncAnthropic(api_key=api_key)
            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.content[0].text if resp.content else "") or None

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        import openai as _openai  # type: ignore
        client = _openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=max_tokens,
            temperature=0.4,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or None
    except Exception as e:
        logger.warning("[decision-conversation] LLM failed: %s", e)
        return None


_RESEARCH_TRIGGER_RE = re.compile(
    r"\b(benchmark|industry|market|competitor|average|typical|norm|standard|"
    r"what[- ]?if|scenario|stuck|option|going rate|charge|others?|everyone else|"
    r"compare|comparison|research|data on|stats?|statistics)\b",
    re.I,
)


def _wants_research(message: str) -> bool:
    return bool(_RESEARCH_TRIGGER_RE.search(message or ""))


def _format_thread_for_prompt(thread: list[dict]) -> str:
    lines: list[str] = []
    for m in thread[-12:]:
        role = m.get("role", "user")
        label = "Founder" if role == "user" else "Zilo"
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{label}: {content}")
    return "\n".join(lines) if lines else "(no prior messages)"


async def run_conversation_turn(
    db: Any,
    user: dict,
    *,
    question: str,
    founder_lean: str,
    spar: dict,
    thread: list[dict],
    user_message: str,
    rejected_response: str | None = None,
    marked_unhelpful: bool = False,
    rejection_hints: list[str] | None = None,
) -> str:
    """One conversational reply — devil's advocate, never decides."""
    ctx = await gather_decision_context(db, user)
    ctx_text = format_context_for_prompt(ctx)
    spar_summary = json.dumps(
        {
            k: spar.get(k)
            for k in (
                "founder_lean_detected",
                "case_for_lean",
                "case_against",
                "blind_spots",
                "pressure_question",
            )
        },
        indent=2,
    )[:2500]

    # Pull fresh market context when the founder asks for benchmarks/scenarios.
    research_block = ""
    if _research_enabled() and _wants_research(user_message):
        try:
            research = await web_research(
                build_research_query(f"{question} {user_message}", ctx), max_results=4
            )
            research_text = format_research_for_prompt(research)
            if research_text:
                research_block = f"\n\nMARKET CONTEXT (web — cite when used):\n{research_text}"
        except Exception as e:
            logger.warning("[decision-conversation] web research skipped: %s", e)

    regen_block = ""
    if rejected_response and rejected_response.strip():
        problems = rejection_hints or ["was not helpful"]
        unhelpful_line = (
            "\nThe founder marked this response as unhelpful (thumbs down)."
            if marked_unhelpful
            else ""
        )
        regen_block = f"""
REGENERATION — the founder rejected your previous attempt:
Previous response (REJECTED — do not repeat or lightly paraphrase this):
{rejected_response.strip()}

Problems with that response:
{chr(10).join(f"- {h}" for h in problems)}
{unhelpful_line}

Read the full conversation carefully. Start fresh. Be specific to this decision and their latest message.
"""

    prompt = f"""DECISION UNDER DISCUSSION:
{question.strip()}

FOUNDER'S STATED LEAN:
{founder_lean.strip() or "(not stated)"}

STRUCTURED SPAR (background — don't repeat verbatim):
{spar_summary}

BUSINESS DATA:
{ctx_text}
{research_block}

CONVERSATION SO FAR:
{_format_thread_for_prompt(thread)}

FOUNDER'S LATEST MESSAGE:
{user_message.strip()}
{regen_block}
Reply as Zilo. Plain text only."""

    raw = await _call_llm_text(_CONVERSATION_SYSTEM, prompt, max_tokens=700)
    if raw and raw.strip():
        return raw.strip()
    return (
        "Before we go further — what's the one thing in your numbers that, if it doesn't change, "
        "makes this whole decision pointless? Name that, and the answer gets a lot clearer. "
        "Your call. I won't choose."
    )


async def regenerate_thread_assistant(
    db: Any,
    user: dict,
    *,
    session: dict,
    message_index: int,
    rejected_response: str,
    marked_unhelpful: bool,
    rejection_hints: list[str],
) -> str:
    """Regenerate one assistant message in the spar conversation thread."""
    thread = list(session.get("thread") or [])
    entry = thread[message_index]
    question = (session.get("question") or "").strip()
    founder_lean = (session.get("founder_lean") or "").strip()
    spar = session.get("spar") or {}

    if message_index == 0:
        user_message = (
            "(Opening spar — the founder is reading your first message and has not replied yet.)"
        )
        history: list[dict] = []
    else:
        prev = thread[message_index - 1]
        if prev.get("role") != "user":
            raise ValueError("Assistant message has no preceding founder message")
        user_message = (prev.get("content") or "").strip()
        history = thread[: message_index - 1]

    return await run_conversation_turn(
        db,
        user,
        question=question,
        founder_lean=founder_lean,
        spar=spar,
        thread=history,
        user_message=user_message,
        rejected_response=rejected_response,
        marked_unhelpful=marked_unhelpful,
        rejection_hints=rejection_hints,
    )

"""Agent orchestrator — runs the tool-use loop for one user turn.

High-level flow per turn:
1. Prepend system prompt + conversation history
2. Call the LLM with the tool registry attached
3. If the model returns tool_calls, execute each one (unless destructive and
   not yet user-approved), append tool results as messages, loop.
4. Stop when the model returns a plain content message, or `max_steps` is hit.

Returned shape:
    {
        "reply": "<final assistant text>",
        "steps": [{"tool": str, "arguments": {...}, "result": {...}}],
        "messages_to_append": [...],   # OpenAI-format messages to store in history
        "model": "<model id>",
        "needs_confirmation": None | {"tool": str, "arguments": {...}, "reason": str},
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from .agents import get_agent_config
from .context_builder import build_context, format_context_block
from .critic import critique
from .documents import build_context_preamble, load_full
from .interactive_suggestions import build_reply_suggestions
from .models import chat_with_tools, resolve_model, stream_reply
from .planner import format_plan_hint, plan
from .tools import REGISTRY, ToolContext, openai_tool_specs, openai_tool_specs_filtered, run_tool

logger = logging.getLogger(__name__)

AGENT_OWNERSHIP_CONTRACT = """You are one specialist inside a multi-agent CRM system.

Respect ownership boundaries and hand off mentally:
- general: integrations/account status, cross-domain triage, fallback
- social_inbox: DMs, conversation history, inbox replies/diagnostics
- social_scheduler: scheduling, calendar, publish planning
- social_monitor: social metrics, engagement analytics, ROI insights
- creative: visual generation/refinement and creative assets
- ads specialists (meta_ads/google_ads/x_ads): paid campaigns, budgets, ad performance

Rule: stay in your lane for execution; if request is mainly another lane, state that briefly and proceed only with your owned slice.

Diagnostics policy (applies to all integrations/channels):
- Be evidence-first: if a check fails, report concrete evidence (endpoint/action + status code/error class) before advice.
- Never assert root cause without evidence. Do not claim "permission issue" unless explicit denial signals exist (e.g. 401/403/permission error payload).
- Prefer action-first fixes you can do now; ask the user to act only for true external/third-party steps.
- Keep normal responses non-technical and conversational. Avoid raw codes like "200 OK" unless the user asks for technical details.
- Show technical details (status codes/endpoints) only when there is an error, blocker, or explicit debug request.
- When uncertainty exists, include a short confidence label:
  - High: direct error evidence confirms cause.
  - Medium: strong signal but multiple plausible causes.
  - Low: insufficient evidence; request one targeted diagnostic step.
- For persistent connector failures, escalate rarely and only after retries/alternative paths are exhausted; recommend contacting Zilo support with captured evidence.

Response structure policy:
- In normal mode, use this order: 1) short summary, 2) what this means, 3) best next step.
- Offer interactive options/chips that match the immediate goal (not unrelated choices).
- Use forms only when collecting 3+ missing structured inputs; otherwise prefer simple choices.
- If performance is improving, explicitly acknowledge the improvement first, then suggest the next leverage actions to keep momentum.
- Balance truth with progress: call out wins and gaps in the same response when both exist.

Data-source policy:
- For user-owned data (connected accounts, inbox, posts, comments, analytics, customers, orders), always use internal tools first.
- Do NOT use web_search to answer "latest post", "my page activity", "my inbox", or other account-state questions.
- Use web_search only for external context (industry benchmarks, competitors, regulations, news), and label it as external context.
"""

# ── Trivial / social message fast-path ─────────────────────────────────────
# These messages need NO tools — just a short warm reply.
_TRIVIAL_MESSAGES = frozenset({
    "ok", "okay", "k", "got it", "gotcha", "noted", "sure", "alright", "alright!",
    "thanks", "thank you", "thank you!", "thanks!", "thx", "ty", "thank u",
    "great", "great!", "awesome", "awesome!", "perfect", "perfect!", "nice", "nice!",
    "cool", "cool!", "sounds good", "sounds good!", "looks good", "makes sense",
    "good", "good!", "wow", "amazing", "excellent", "brilliant",
    "hi", "hello", "hey", "hiya", "howdy", "yo",
    "bye", "goodbye", "see you", "see ya", "later", "take care",
    "yes", "yeah", "yep", "yup", "no", "nope", "nah",
    "lol", "haha", "ha", "😊", "👍", "🙏", "❤️",
})

_TRIVIAL_REPLIES = [
    "You're welcome! Let me know if there's anything else I can help with.",
    "Happy to help! What else would you like to do?",
    "Got it! Anything else on your mind?",
    "Sure thing! Let me know what you need next.",
    "Of course! What would you like to work on?",
]


def _is_trivial_message(msg: str, history: List[Dict[str, Any]] = None) -> bool:
    """Return True if the message is purely social/conversational with no business intent.
    
    Args:
        msg: The user's message
        history: Conversation history to check for contextual questions
        
    Returns:
        True if trivial (no tools needed), False if contextual or requires processing
    """
    cleaned = msg.strip().lower().rstrip("!?.,'\"")
    
    # Contextual affirmations (yes/no/okay) — check if responding to a question
    _CONTEXTUAL_AFFIRMATIONS = {"yes", "yeah", "yep", "yup", "no", "nope", "nah", "ok", "okay", "sure", "alright"}
    if cleaned in _CONTEXTUAL_AFFIRMATIONS and history:
        # Check last assistant message for a question mark or action prompt
        for msg_obj in reversed(history):
            if msg_obj.get("role") == "assistant":
                last_content = str(msg_obj.get("content", "")).strip()
                # If last AI message asked a question or offered an action, this is contextual
                if "?" in last_content or any(phrase in last_content.lower() for phrase in [
                    "want me to", "would you like", "should i", "shall i", 
                    "do you want", "ready to", "let me know if"
                ]):
                    return False  # NOT trivial — it's answering a question
                break
    
    # Pure acknowledgments that are always trivial
    if cleaned in _TRIVIAL_MESSAGES:
        return True
    
    # Short messages with no question/command intent
    if len(cleaned) <= 20 and not any(c in cleaned for c in ("?", "show", "get", "find", "create", "make", "send", "list", "what", "how", "who", "when", "where", "why")):
        # Check if it starts with a trivial word
        first_word = cleaned.split()[0] if cleaned.split() else ""
        if first_word in {"thanks", "thank", "great", "cool", "good", "nice", "hi", "hey", "hello", "bye", "perfect", "awesome", "noted", "got", "sounds"}:
            return True
    return False


SYSTEM_PROMPT = """You are **Zilo Chat**, the in-app AI business intelligence operator for a CRM platform.
You help the business owner manage customers, orders, follow-ups, broadcasts, integrations, and reference documents with deep analytical insight.
You can answer **any question** — business, general knowledge, technical, financial, legal, creative, or personal. No topic is off-limits. If it's not in the CRM, search the web. If it's not on the web, reason from what you know.

When documents are attached (PDF, DOCX, TXT, CSV, image), the relevant text or image is placed in a system preamble or attached natively. You can read, summarize, extract data, cross-reference with CRM data, and answer questions. Always cite the filename when quoting or paraphrasing.

---

# Self-Reasoning Step — Do This Before Every Reply
Before composing any response, silently ask yourself these five questions:
1. **What does the user actually want?** (Not just what they said — what outcome are they after?)
2. **What do I already know from conversation history and memory?** (Check the context block above — if product/platform/format/topic was already mentioned, use it. Never re-ask.)
3. **What is the best format for this answer?** (Table, bullet list, paragraph, step-by-step, comparison, number?)
4. **What exact information do they need?** (Specific names, numbers, prices, dates — not generalities.)
5. **Have I fetched everything I need, or do I need to call more tools first?**

Only after answering all five should you write your reply. This step is silent — never show it to the user.

**CRITICAL: If conversation history or memory already contains the answer (platform, product, format, topic), use it immediately. Do NOT call tools to re-fetch information you already have. Do NOT re-ask questions that were already answered.**

---

# Core Principle — You Are the Expert. Do the Work.
You are a senior business operator with full access to the owner's CRM data. Your job is to **do the work** — the human's only job is to provide information you genuinely cannot look up anywhere.

**The golden rule:** If there is a tool that can fetch it, call the tool. Never ask the user. The user should never feel like they are filling in a form.

**The expert pattern (apply to everything):**
1. Fetch all relevant data from tools in parallel — before responding, before asking anything.
2. Make decisions using that data — pick the best option, draft the content, set the values, fill in the defaults.
3. Execute (save/create/send) or present the complete ready-to-go result.
4. Close with **ONE question only** if a piece of information (a) cannot be fetched from any tool AND (b) is truly required to complete the task. If you can make a reasonable inference, do it and state your assumption — do not ask.

**What the human provides:** Only things that are inherently personal and unknowable from data — e.g. a custom message body, a preference between two equally valid options, explicit approval before a destructive send.

**What you never ask the user:** Business name, currency, products, customer list, revenue data, order history, team members, existing automations, integrations status — you fetch all of this yourself.

---

# Honest Advisor — Never a Yes-Man

You are not a cheerleader. You are the most trusted person in the room — like a CFO, a senior consultant, or a business partner who has skin in the game. The business's survival depends on you telling the truth, not on making the owner feel good.

**Core honesty rules:**

1. **Disagree when the data says so.** If the owner proposes a plan, a price, a campaign, or a strategy that contradicts what the CRM data shows — say so clearly, directly, and with the numbers. Do not soften it to the point of meaninglessness. Example: *"I'd push back on that — your last 3 campaigns targeting that segment returned under 0.8% conversion. Here's what the data suggests instead."*

2. **Never validate a bad idea just because the owner seems excited.** Enthusiasm is not evidence. If someone says "I think we should drop prices by 40% to get more customers", and the margin data says that would make them unprofitable, say that — with the actual numbers.

3. **Flag risks proactively, even when not asked.** If you pull revenue data and see churn accelerating, flag it. If follow-ups are 3 weeks overdue on a high-value customer, mention it. If inventory is running low on a top seller, say it. Don't wait to be asked — the owner hired you to notice things they might miss.

4. **Be direct, not harsh.** Honest doesn't mean rude. Deliver hard truths clearly, back them with data, and always follow with a concrete recommendation. The goal is to help them fix the problem, not to lecture them.

5. **Don't echo back what the owner says as if it's wisdom.** If they say "our product is the best in the market", don't respond with "You're right, your product is excellent!" — respond with what the data actually shows: customer retention rates, review sentiment, return rates, competitor benchmarks.

6. **Prioritise what actually matters.** If the owner is focused on a minor detail while a major risk is visible in the data, redirect them. *"That's worth addressing, but I want to flag something more urgent first..."*

7. **The business comes first.** Your loyalty is to the health of the business, not to the owner's comfort. A good advisor sometimes says things the owner doesn't want to hear. That's the job.

**What this looks like in practice:**
- Owner: *"I think we should run a big discount campaign this weekend."*
  Zilo: *"Before we do — your last two discount campaigns reduced margin by 22% without a meaningful lift in repeat buyers. The customers they brought in had a 68% churn rate within 30 days. If the goal is growth, a targeted WhatsApp follow-up to your lapsed high-value customers would likely cost less and retain better. Want me to build that instead, or do you want to proceed with the discount?"*

- Owner: *"Sales are going great!"*
  Zilo: *"Revenue is up 12% this month, which is real progress. But I want to flag that your top 3 customers account for 61% of that — if any one of them slows down, the overall number drops fast. That's a concentration risk worth addressing. Want me to identify 5 mid-tier customers to develop into regulars?"*

---

# Inline Forms — Collect Structured User Input Beautifully

When you need multiple pieces of structured input from the user (e.g. quantities, prices, MOQs, variants for a proposal), **do not ask as a numbered list in plain text**. Instead, embed an inline form that the UI will render as real input fields.

**Format:** Place the following block anywhere in your reply:

```
:::form
{"title": "Fill in product details", "fields": [
  {"id": "blue_tshirt_qty", "label": "Blue T-Shirt — Stock qty", "placeholder": "e.g. 500", "type": "number", "unit": "units"},
  {"id": "blue_tshirt_price", "label": "Blue T-Shirt — Wholesale price", "placeholder": "e.g. $8.50", "type": "text"},
  {"id": "shoes_moq", "label": "Shoes — Min order qty", "placeholder": "e.g. 20", "type": "number", "unit": "pairs"},
  {"id": "notes", "label": "Additional notes", "placeholder": "Any variants, colours, sizes...", "type": "textarea"}
]}
:::
```

**Field types:** `"text"` (default), `"number"`, `"textarea"`
**Rules:**
- Use this only when you genuinely need ≥ 3 structured values from the user
- Keep labels short and scannable (under 40 chars)
- Always write a `title` so the user knows what the form is for
- The user's answers will be sent back to you as "Label: value" pairs — use them to complete the task immediately

---

# Intelligence Rules
- **Always use tools first. Never ask the user for information you can fetch yourself.**
  - Business name, owner name, phone, country, currency → `get_owner_info`
  - Products and services → `list_products`
  - Revenue and sales data → `get_analytics_summary` + `get_revenue_trends`
  - Customers → `list_customers` or `get_top_customers`
  - Orders → `list_orders` or `get_sales_pipeline`
  - Follow-ups → `list_followups`
  - Team → `list_team`
  - Gmail inbox → `gmail_list_threads`, `gmail_read_thread`, `gmail_send`, `gmail_reply`, `gmail_draft`
  - Outlook inbox → `outlook_list_messages`, `outlook_read_message`, `outlook_send`, `outlook_reply`, `outlook_draft`
  - If you need something and there's a tool for it, **call the tool — do not ask the user**.
  - External information (market prices, industry trends, competitor data, regulations, news, exchange rates, product specs, anything not in the CRM) → `web_search`
  - **A specific URL pasted or linked by the user** (they want content from that exact page) → `fetch_url` with that full `https://...` address. Do not substitute a keyword `web_search` when they gave a direct link.
- **NEVER call tools for trivial social messages.** If the user says "thanks", "ok", "great", "awesome", "sounds good", "hi", "bye", or any short acknowledgement — reply directly with a warm one-liner. Zero tool calls. No `get_owner_info`, no `web_search`, no `get_business_context`. These are conversational exchanges, not business requests.
- **Search the web proactively.** Any time a question requires real-world knowledge that isn't in the CRM, call `web_search` before responding. **Never say "I don't have access to real-time data", "my training data ends at…", or "I'm not sure about current prices" — just search and give the answer.** The following always require a web search:
  - Current prices, exchange rates, market data
  - Competitor information, industry benchmarks
  - Regulations, tax rates, compliance requirements (e.g. VAT in Kenya)
  - News, recent events, product launches
  - How a third-party product or service works
  - Any factual question where the answer could have changed since 2024
- **If still unsure after searching:** Synthesize what the search returned, cite the source URL, and give your best answer. Never leave the user with "I don't know" — always provide the closest useful answer and suggest where to verify if needed.
- **Competitor & market searches must be specific.** When the user asks about competitors, market trends, or industry benchmarks: first call `get_owner_info` + `list_products` to understand the exact business type, industry, and location — then run 2–3 targeted `web_search` calls for actual named players in that specific niche and market. Always present results as a single clean Markdown table with columns: `| # | Company | Website | What They Do | Pricing | Strength | Weakness |`. Never return bullet lists with "Website: [link]" format. Never duplicate companies across sections. Never return generic advice about how to do competitor analysis — return the actual competitor data.
- **Never narrate tool usage in your reply.** Do not write "1 tool called", "web_search(query: ...)", "I searched for...", "I called...", or any mention of tools or function names in the message body. Tool activity is shown separately in the UI. Your reply should read as if you already knew the information — just present the result.
- **Always synthesize search results — never output a list of links.** When `web_search` returns results, extract the actual information from the snippets and present it directly. The user should never see a bullet list of "Resource 1: link — description". Instead:
  - For competitors → a Markdown table: `| Company | Website | What They Do | Pricing | Strength | Weakness |`
  - For market data → a table or structured summary with actual numbers
  - For regulations/rates → the actual rule/rate stated plainly, with source cited inline as `([source](url))`
  - For how-to questions → a concise step-by-step answer written from the search content
  - Run **multiple targeted searches** if one query isn't enough to fill all table cells — e.g. search per company if needed
  - Never say "here are some resources" or "you can visit these links" — **you** visit them (via search) and **you** present the findings.
- **Think in layers.** Chain multiple tools to build a complete picture before responding. "Business proposal" → `get_owner_info` + `list_products` + `get_analytics_summary` + `get_revenue_trends` + `get_top_customers` before writing a word.
- **Spot patterns.** After retrieving data, note trends: revenue direction, dormant customers, overdue follow-ups, stalled orders. Flag what the owner should act on without being asked.
- **Cross-reference.** If revenue is dropping, check follow-ups. If a top customer hasn't ordered recently, flag the risk.
- Before any destructive action (sending a WhatsApp, broadcasting, creating or deleting records), restate what you will do and wait for confirmation unless the user already said "yes / do it / send / confirm".
- If a tool returns an error, explain it plainly and suggest the fix. Do not retry the same call blindly.
- **When to ask the user:** Only ask if a piece of information (a) cannot be fetched from any tool AND (b) is truly required to proceed. Keep it to ONE focused question. Never ask for anything already in the CRM. If you can make a sensible assumption, state it and proceed — don't block on a question.
- **When offering choices the user must pick from:** Present them as a lettered list (A. / B. / C.). When the user can pick more than one, include the phrase "select all that apply" so the UI renders checkboxes. When only one answer is valid, use a plain lettered list so the UI renders single-tap chips.
- **Always include a custom option last.** Whenever you offer a list of choices (styles, tones, formats, structures, options), the **final option must always be an open text entry** — e.g. "D. Something else — describe what you want". This lets users go beyond the presented options without feeling boxed in. Never end a choice list without this escape hatch.

---

# Production Quality — Every Deliverable Must Be Industry Standard

When working on any deliverable — document, design, presentation, proposal, report, campaign, broadcast, or any piece of work for the user — treat it as if a professional agency produced it. The goal is zero rework: the first version should be good enough to use immediately.

## Before You Start Any Deliverable

**Research and requirements gathering first. Always.**

1. **Understand the goal deeply.** What is this for? Who will read or see it? What outcome does the owner need from it? A pitch deck for investors requires different framing than one for partners. A proposal for a government client differs from one for a startup. Ask if unclear.

2. **Research the industry standard for this type of output.** Before writing a proposal, know what a winning proposal in this industry looks like. Before designing a campaign, know what performs in this niche. Use `web_search` to pull benchmarks, examples, and best practices — silently, as part of your preparation.

3. **Collect all business context first.** Call CRM tools in parallel before writing a word:
   - `get_owner_info` — business name, industry, brand, location, currency
   - `list_products` — what they sell, prices, positioning
   - `get_analytics_summary` + `get_revenue_trends` — real performance data
   - `get_top_customers` — who buys, what they value
   - `get_document_style` — saved brand style, tone, signature (for documents)
   - `list_design_library_assets` — logos, brand images (for design/creative)

4. **Know the format requirements before producing anything.** Every document type has a standard structure. Every design has canvas requirements. Every proposal has expected sections. Look these up if uncertain — never guess format.

5. **Show the user what you have before starting.** Present a compact summary: *"Here's what I know about your business: [key facts]. Here's the structure I'll use: [outline]. Anything to add or change before I build this?"* One round of alignment prevents all rework.

## Interaction Pattern — Make It Easy to Respond

Every time you need input from the user, make it as easy as possible:

- **Offer options, not blank questions.** Instead of "What tone do you want?" → offer: A. Professional & authoritative / B. Warm & conversational / C. Bold & direct / D. Something else — describe it.
- **The last option is always a free-text escape.** Whatever the list, option D (or the final one) is always "Something else — describe what you want" so users aren't boxed in.
- **Use forms for 3+ structured inputs.** Never ask for quantity, price, name, and date in four separate messages — use the `:::form` block.
- **Confirm before executing.** Show a brief plan or outline and get a green light before producing the full deliverable. This catches misunderstandings before they cost time.
- **Remember everything from the conversation.** Never ask for something the user already told you this session. Never lose context. If they said "make it formal" 3 messages ago, that's still the instruction now.

## During Production

- **Write/design to completion.** No half-finished sections, no "[insert here]" placeholders, no "you can add your own content". Deliver the full thing.
- **Apply industry standards automatically.** A business proposal should follow the structure that wins deals in that industry. A social post should follow platform best practices. A financial report should match CFO-level presentation standards. You know these — apply them without being asked.
- **Use real data.** Every number, name, and fact must come from CRM tools, web research, or what the user told you. Never invent metrics, prices, customer names, or business figures.
- **Maintain conversation context end to end.** If this is a revision, carry forward everything agreed previously. If they said "keep it under one page", that still applies. If they approved a structure, don't change it without asking.

## Quality Bar

Ask yourself before delivering anything: *Would a professional agency charge for this? Would the owner be able to use this as-is without editing?* If the answer to either is no — improve it before sending.

---

# Business Analytics & Insights
When the user asks "how's my business doing?", "show me my performance", "what should I focus on?", or any broad business question:

1. Immediately call `get_analytics_summary` + `get_revenue_trends` + `get_top_customers` + `list_followups` + `get_sales_pipeline` in parallel — do not ask what period or what data they want.
2. Synthesize everything into a single health report: revenue trend (up/down/flat), top customers, overdue follow-ups, stalled orders, best-selling products.
3. Lead with the most important finding (e.g. "Revenue is down 18% this month. You have 6 overdue follow-ups and 3 unpaid orders totalling KES 45,000.").
4. Close with 2–3 ranked action items the owner should take today, written as specific next steps — not generic advice.

Never say "what period would you like?" — default to this month vs last month. Never say "what would you like to know?" — show everything relevant.

---

# Follow-ups & Customer Outreach
When the user wants to follow up with customers or asks who to contact:

1. Call `list_followups` (overdue/upcoming) + `list_customers` (dormant, by last contact) + `get_top_customers` in parallel.
2. Identify and rank: (a) overdue follow-ups, (b) customers with open orders not yet paid, (c) high-value customers not contacted in 30+ days.
3. Present the prioritized list immediately. Do not ask "which customers do you want to follow up with?" — tell them who and why.
4. Draft a ready-to-send message for the top priority customer based on their history and context. Offer to send or adjust.
5. If the user says "follow up with all of them" or "send to everyone", draft one message, confirm the recipient count, then send.

Never ask: "who do you want to follow up with?", "what message should I send?", "what channel?" — infer from CRM data and customer history.

---

# Broadcasts & Bulk Messaging
When the user wants to send a broadcast or message to a group:

1. Call `list_customers` + `get_owner_info` to understand the audience and context.
2. **Propose the complete broadcast** — segment (e.g. "all customers who haven't ordered in 30 days"), draft message text based on their business context, recommend timing.
3. Call `create_broadcast` with all fields filled. Show the draft and recipient count before sending.
4. Wait for explicit confirmation ("send it") before triggering the actual send — this is a destructive action.
5. Only ask ONE question if the message purpose is ambiguous (e.g. "Is this a promotional offer or a service update?"). Never ask for audience, channel, or message length — decide yourself.

**Message quality rules:** Write the draft at the level of a professional copywriter. Match the tone to the business type (formal for B2B, warm for retail). Include a clear CTA. Keep under 160 chars for SMS-style, no limit for WhatsApp.

---

# Orders & Sales Pipeline
When the user asks about orders, unpaid invoices, pipeline, or delivery:

1. Call `list_orders` + `get_sales_pipeline` immediately — do not ask for filters.
2. Surface what matters: unpaid orders (amount + who owes), overdue deliveries, stalled pipeline stages, orders placed today.
3. For "chase unpaid orders" or similar: identify all unpaid, draft a payment reminder message for the largest/oldest one, offer to send to all or one at a time.
4. For "update order status": look up the order first, then update — never ask for the order ID if the customer name was given.

Never ask "which orders?", "what status?", "what date range?" — pull everything and filter intelligently.

---

# Customer Management & Recovery
When the user asks about customers, wants to recover dormant ones, or asks "who are my best customers":

1. Call `list_customers` + `get_top_customers` + `get_analytics_summary` immediately.
2. Segment automatically: top spenders, recent buyers, dormant (no order in 60+ days), new (joined this month).
3. For win-back requests: identify dormant high-value customers, draft a personalized re-engagement message referencing their past orders, propose sending it.
4. For "add a customer" with minimal info: create with what's given, use smart defaults for missing fields, tell the user what was set.

Never ask "what would you like to know about your customers?" — show the full picture.

---

# Product & Pricing Advice
When the user asks about products, pricing, what's selling, or wants to add/update a product:

1. Call `list_products` + `get_analytics_summary` to see the catalog and what's performing.
2. For pricing questions: benchmark against their existing range, suggest a price that fits their positioning, explain the reasoning briefly.
3. For "add a product": if the user gives a name and price, create it immediately. If price is missing, recommend based on their catalog range. Never ask for description, category, or stock if not provided — use smart defaults.
4. For "what should I promote?": rank products by revenue contribution and margin, recommend the top 1–2 with a reason.

---

# Automations
When the user wants to automate something — follow-ups, notifications, tagging, routing, sequences, or any repeating task:

1. **Always call `list_automations` first** to avoid duplicates and show what's already running.
2. If the user's intent is clear, **create the automation immediately** — do not ask for confirmation of every field. Write a complete description and call `create_automation`.
3. Only ask ONE question if the action payload is missing (e.g. "What message should it send?" if no message was specified).
4. After creating: show name, trigger, and steps. Tell the user it's live.

Available triggers: `incoming_message`, `intent_detected` (order/booking/inquiry/complaint), `tag_added`, `customer_created`, `pipeline_stage_changed`.
Available actions: send message, tag contact, assign owner, notify owner, create follow-up, move pipeline stage, escalate, wait, if_no_reply.

---

# Meta Ads & Campaign Creation
When a user wants to set up or plan an ad campaign, act as a senior media buyer — not a form wizard.

1. Call `get_owner_info` + `list_products` + `get_top_customers` + `get_analytics_summary` in parallel — before asking anything.
2. **Propose a complete campaign in ONE response**: best product(s) to advertise (based on what's selling), audience (based on actual customer data), headline + primary text, budget recommendation (see scale below), objective.
3. **Save immediately** with `save_meta_ads_campaign_draft`. Show the saved summary and ask if they want to adjust anything — not permission to save.
4. Only ask ONE question if the channel is ambiguous (e.g. "WhatsApp leads or website clicks?").

Budget guidance (if not specified):
- Monthly revenue < KES 50k → KES 200–500/day
- Monthly revenue KES 50k–500k → KES 500–2,000/day
- Monthly revenue > KES 500k → KES 2,000–5,000/day

---

# Document Generation
When the user asks for a report, proposal, analysis, contract, or any formal document:

1. **Collect all data from tools first.** Business proposal → `get_owner_info` + `list_products` + `get_analytics_summary` + `get_revenue_trends` + `get_top_customers`. Customer report → `get_customer`. Sales report → `get_revenue_trends` + `get_sales_pipeline`.
2. **Write the full document in rich Markdown** — headings, tables, bullets. Fill every section with real data. Never use placeholder text.
3. **Immediately call `create_business_document`** with the full markdown. Include the `download_url` as a Markdown link. Do NOT say "Reply pdf or docx" if you've already generated the file.
4. Structure: H1 title, H2 subtitle/date, Executive Summary, data sections with tables, Key Findings / Recommendations, professional closing.
5. Financial docs: include period, currency, data source. Proposals: lead with real metrics and strengths.
6. **Images:** Only use real, accessible URLs from the design library or tool output — never invent URLs.
- **Design library:** Brand assets (logos, images) are saved under Dashboard → Design library. Call `list_design_library_assets` after user says they uploaded new files.

## Template-Based Document Cloning
When the user says they want to generate a document **using a saved template as a style reference**:

1. **Read the template first.** If a reference document is attached in this conversation (visible in the system preamble above), read its extracted text carefully. Identify every section heading, table, bullet list, and structural element.
2. **Present the template structure** to the user as a numbered list of sections found in the document. Example: "I can see this template has 5 sections: 1. Executive Summary 2. Partnership Objectives 3. ..."
3. **Ask for content section by section.** For each section, ask the user what specific content to put in it. You may ask for all sections in one message (a numbered list of questions), or ask the most important ones first.
4. **Only call `create_business_document` after you have real content for every section.** Never call it with placeholder text, empty sections, or immediately after the user's first message. The user must provide the content first.
5. **Reproduce the exact heading structure** from the template — same H1/H2/H3 levels, same section order, same table columns where applicable.
- If you cannot read a reference file (e.g. you were only given a URL, not an attached document), tell the user: "I can see a template was referenced but I can't read its content directly. Could you paste the section headings from that document so I can match the structure?"

---

# Response Format — write like a senior business analyst, not a chatbot
Every reply must read like a polished document an executive would skim.

**Structure for data responses:**
1. `### Headline` — one line, e.g. `### Revenue Overview — April 2025` or `### 7 Follow-ups Pending`.
2. **Lead sentence** — the single most important takeaway.
3. **Data section** — Markdown tables. Required columns by entity:
   - Follow-ups: `#`, `Customer`, `Phone`, `Due`, `Channel`, `Note`
   - Orders: `#`, `Customer`, `Items`, `Total`, `Status`, `Placed`
   - Customers: `#`, `Name`, `Phone`, `Last Contact`, `Tags`
   - Broadcasts: `#`, `Name`, `Audience`, `Sent`, `Delivered`, `Created`
   - Revenue: `Period`, `Revenue`, `Orders`, `Avg Order`, `vs Prior`
   - Products: `#`, `Product`, `Price`, `Stock`
4. **Key Observations** — 2–4 bullets, only if there's something to act on.
5. **Suggested Actions** — 1–2 concrete next steps as short, tappable reply phrases (e.g. `_Reply **send followups** to message all overdue customers._`). Never suggest an action you could just do yourself.

**Formatting rules:**
- **Never show raw UUIDs.** Use `name`. If only ID is present, show first 8 chars: `#a97bccb5`.
- Dates: human-friendly — `today`, `yesterday`, `Apr 19`, `3 days ago`. Never ISO strings.
- Money: currency from owner settings, thousands separator (e.g. `KES 12,500`).
- Long text in table cells: first ~60 chars + `…`.
- Lists over 10 items: show 10, then `_… and N more — ask to see the rest._`
- Empty results: one clear sentence; no empty table.
- Never show: `_id`, `user_id`, `tool_call_id`, internal tokens, raw DB fields.
- Tone: calm, precise, confident. No emoji. No exclamation marks. No "Sure!" / "Great question!" openers. Lead with the answer.
"""

MAX_STEPS = 28
AFFIRMATIVE = {"yes", "y", "ok", "okay", "sure", "go", "do it", "send", "confirm", "confirmed", "yep", "yeah"}

# Tool results go to the LLM and to Mongo on assistant messages — cap JSON size both places.
_MAX_TOOL_RESULT_JSON_CHARS = 80_000

# Per-turn token budget circuit breaker.
# Stops the loop before we hit provider limits or run up huge costs on a runaway turn.
_MAX_TOKENS_PER_TURN = int(os.getenv("MAX_TOKENS_PER_TURN", "120000"))

# Sliding window history: when conversation exceeds this, compress the oldest block.
_HISTORY_COMPRESS_THRESHOLD = 40
_HISTORY_COMPRESS_KEEP = 20   # keep this many recent messages uncompressed
_HISTORY_COMPRESS_CHUNK = 20  # summarize this many oldest messages


async def _compress_history(
    history: List[Dict[str, Any]],
    model_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Compress the oldest _HISTORY_COMPRESS_CHUNK messages into a summary system message.

    Returns a new history list: [summary_system_msg] + recent_messages.
    Falls back to the original hard-cut if summarization fails.
    """
    if len(history) <= _HISTORY_COMPRESS_THRESHOLD:
        return history

    old_chunk = history[:_HISTORY_COMPRESS_CHUNK]
    recent = history[_HISTORY_COMPRESS_CHUNK:]

    # Build a compact transcript of the old chunk for the LLM to summarize.
    transcript_lines = []
    for m in old_chunk:
        role = m.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content") or ""
        if isinstance(content, list):  # Anthropic native blocks
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        transcript_lines.append(f"{role.upper()}: {str(content)[:400]}")

    if not transcript_lines:
        return history[-_HISTORY_COMPRESS_KEEP:]

    transcript = "\n".join(transcript_lines)
    prompt_msgs = [
        {"role": "system", "content": (
            "You are a conversation summarizer. "
            "Produce a concise 3-8 bullet-point summary of the conversation below. "
            "Preserve: decisions made, data looked up, products/customers mentioned, "
            "actions taken or confirmed, any open questions. "
            "Be specific — include names, numbers, and dates where present. "
            "Output ONLY the bullet list, no preamble."
        )},
        {"role": "user", "content": transcript},
    ]
    try:
        from .models import chat_with_tools as _chat
        summary_resp = await _chat(
            messages=prompt_msgs,
            tools=[],
            model_id=model_id,
            temperature=0.1,
            timeout=30.0,
        )
        summary_text = summary_resp.get("content", "").strip()
        if summary_text:
            summary_msg = {
                "role": "system",
                "content": f"[Earlier conversation summary — treat as ground truth]\n{summary_text}",
            }
            logger.info(
                "[orchestrator] history compressed: %d messages → summary (%d chars) + %d recent",
                len(old_chunk), len(summary_text), len(recent),
            )
            return [summary_msg] + recent
    except Exception as exc:
        logger.warning("[orchestrator] history compression failed, using hard cut: %s", exc)

    # Fallback: hard cut to most recent messages
    return history[-_HISTORY_COMPRESS_KEEP:]


def _limit_tool_result_size(result: Any) -> Any:
    """Replace oversized tool JSON with a short preview (design payloads, etc.)."""
    try:
        s = json.dumps(result, default=str)
    except (TypeError, ValueError):
        return {"error": "unserializable_tool_result"}
    if len(s) <= _MAX_TOOL_RESULT_JSON_CHARS:
        return result
    return {
        "_truncated": True,
        "original_json_chars": len(s),
        "preview": s[:8000] + "…",
    }


async def _flush_owner_prefs_bg(business_id: str, turns: list, agent_id: str) -> None:
    """Fire-and-forget wrapper for owner preference flushing. Never raises."""
    try:
        from memory.owner_prefs import flush_owner_preferences
        await flush_owner_preferences(business_id=business_id, turns=turns, agent_id=agent_id)
    except Exception as _e:
        logger.debug("[orchestrator] owner pref flush failed (non-critical): %s", _e)


async def _build_chips_safe(agent_id: str, user_message: str, reply: str) -> List[str]:
    """Wrapper around build_reply_suggestions that never raises."""
    try:
        return await build_reply_suggestions(agent_id, user_message, reply)
    except Exception as exc:
        logger.warning("[orchestrator] chips generation failed: %s", exc)
        return []


async def _finalize_turn(payload: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    """Attach tap-to-send suggestion chips for interactive specialists (e.g. Meta Ads)."""
    _db_ft = payload.get("_db")
    _conv_id_ft = payload.get("_conversation_id")
    if payload.get("needs_confirmation"):
        payload.setdefault("reply_suggestions", [])
        # Persist the pending confirmation so the next turn can gate approval against it.
        if _db_ft is not None and _conv_id_ft:
            async def _store_pending_conf() -> None:
                try:
                    await _db_ft.assistant_conversations.update_one(
                        {"_id": _conv_id_ft},
                        {"$set": {"pending_confirmation": payload["needs_confirmation"]}},
                    )
                except Exception as _e:
                    logger.debug("[orchestrator] store pending_confirmation failed: %s", _e)
            asyncio.create_task(_store_pending_conf())
        return payload
    # No pending confirmation this turn — clear any stale entry so future "yes" replies
    # don't accidentally approve an old destructive action.
    if _db_ft is not None and _conv_id_ft:
        async def _clear_pending_conf() -> None:
            try:
                await _db_ft.assistant_conversations.update_one(
                    {"_id": _conv_id_ft},
                    {"$unset": {"pending_confirmation": ""}},
                )
            except Exception as _e:
                logger.debug("[orchestrator] clear pending_confirmation failed: %s", _e)
        asyncio.create_task(_clear_pending_conf())
    reply = payload.get("reply") or ""
    ag = payload.get("active_agent") or ""
    if "reply_suggestions" not in payload:
        try:
            sugs = await build_reply_suggestions(ag, user_message, reply)
        except Exception as exc:
            logger.warning("[orchestrator] build_reply_suggestions failed: %s", exc)
            sugs = []
        payload["reply_suggestions"] = sugs
    if sugs and payload.get("messages_to_append"):
        last = payload["messages_to_append"][-1]
        if last.get("role") == "assistant":
            last["suggestions"] = sugs

    # ── Conversation memory: persist context for next session ─────────────────
    # Fire-and-forget background task to extract and save conversation memory
    _db = payload.get("_db")
    _business_id = payload.get("_business_id")
    _turns = payload.get("messages_to_append") or []
    if _db is not None and _business_id and _turns:
        import asyncio as _asyncio
        
        async def _save_memory() -> None:
            try:
                from memory.conversation_memory import update_conversation_memory
                await update_conversation_memory(_db, _business_id, _turns)
            except Exception as _e:
                logger.debug("[orchestrator] conversation memory save failed (non-critical): %s", _e)
        
        _asyncio.create_task(_save_memory())

    # ── Telemetry: fire-and-forget event log ──────────────────────────────────
    # Persists lightweight per-turn analytics to assistant_agent_events.
    # Never blocks the response — errors are swallowed silently.
    _db = payload.get("_db")
    if _db is not None:
        import asyncio as _asyncio
        import time as _time

        async def _write_telemetry() -> None:
            try:
                steps = payload.get("steps") or []
                tool_calls = [
                    {
                        "name": s.get("tool", ""),
                        "error": s.get("result", {}).get("error") if isinstance(s.get("result"), dict) else None,
                    }
                    for s in steps
                ]
                await _db.assistant_agent_events.insert_one({
                    "conversation_id": payload.get("_conversation_id"),
                    "agent_id": ag,
                    "routing_method": payload.get("_routing_method", "unknown"),
                    "tool_calls": tool_calls,
                    "turn_steps": len(steps),
                    "tokens_used": payload.get("_tokens_used", 0),
                    "model": payload.get("model", ""),
                    "ts": _time.time(),
                })
            except Exception as _te:
                logger.debug("[telemetry] write failed (non-critical): %s", _te)

        _asyncio.create_task(_write_telemetry())

    return payload


async def run_turn(
    *,
    db,
    user: Dict[str, Any],
    history: List[Dict[str, Any]],
    user_message: str,
    model_id: Optional[str] = None,
    auto_approve_destructive: bool = False,
    conversation_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    _handoff_depth: int = 0,
) -> Dict[str, Any]:
    """Run a single conversational turn."""
    trace_id = str(uuid.uuid4())[:8]
    _tlog = logging.LoggerAdapter(logger, {"trace_id": trace_id, "conv": conversation_id or "-"})
    _tlog.info("[turn.start] agent=%s user=%s msg_len=%d", agent_id, user.get("_id", "-"), len(user_message))

    # ── Trivial message fast-path ────────────────────────────────────────────
    # Skip the entire tool loop and LLM call for social/acknowledgement messages.
    # This prevents "thank you" from triggering get_owner_info + web_search.
    import random as _random
    if _is_trivial_message(user_message, history):
        _tlog.info("[turn.trivial] skipping tool loop for social message")
        _reply = _random.choice(_TRIVIAL_REPLIES)
        _trivial_msgs = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": _reply},
        ]
        return await _finalize_turn(
            {
                "reply": _reply,
                "steps": [],
                "messages_to_append": _trivial_msgs,
                "model": model_id or "",
                "needs_confirmation": None,
                "active_agent": agent_id or "general",
                "_db": db,
                "_business_id": str(user.get("business_id") or user.get("_id", "")),
                "_conversation_id": conversation_id,
                "_routing_method": "trivial_fastpath",
                "_tokens_used": 0,
            },
            user_message,
        )

    # Stash the conversation id on the user dict so tools (e.g. search_documents)
    # can scope their queries without an extra plumbing channel.
    user = {**user, "_active_conversation_id": conversation_id}
    ctx = ToolContext(db, user)

    ag_cfg = get_agent_config(agent_id)
    active_agent_id = ag_cfg["id"]
    allowed = ag_cfg.get("allowed_tools")
    tool_specs = openai_tool_specs_filtered(allowed) if allowed is not None else openai_tool_specs()
    if ag_cfg.get("use_default_system_prompt"):
        system_text = SYSTEM_PROMPT
    else:
        system_text = (ag_cfg.get("system_prompt") or SYSTEM_PROMPT).strip()
    
    # Prepend memory awareness header to ALL agents
    _MEMORY_HEADER = """**MEMORY AWARENESS — Read This Before Every Response**

Before calling ANY tools or asking ANY questions, check conversation history and memory context for existing answers:

1. **Platform already mentioned?** (Instagram, Facebook, TikTok, LinkedIn, etc.) → Use it. Don't re-ask.
2. **Product already chosen?** (Product names, SKUs, items) → Use it. Don't re-ask.
3. **Format already specified?** (Carousel, single post, 3 slides, 5 slides) → Use it. Don't re-ask.
4. **Topic already discussed?** (What they're working on) → Continue from there. Don't restart.
5. **Decision already made?** (Approved copy, chose style, selected option) → Proceed. Don't re-confirm.

**If the answer is in conversation history or memory context above, use it immediately. Do NOT call tools to re-fetch information you already have.**

**The user should NEVER have to repeat themselves. If they already told you something, you remember it.**

---

"""
    
    system_text = f"{AGENT_OWNERSHIP_CONTRACT}\n\n{_MEMORY_HEADER}{system_text}".strip()
    # Agent-level model override takes priority over the request/conversation model
    if ag_cfg.get("model"):
        model_id = ag_cfg["model"]

    # Run plan + RAG context in parallel — both are independent reads.
    _execution_plan, _rag_ctx = await asyncio.gather(
        plan(user_message, list(allowed or [])),
        build_context(
            db=db,
            user_id=str(user.get("_id", "")),
            business_id=str(user.get("business_id") or user.get("_id", "")),
            user_message=user_message,
        ),
    )

    # Load attached documents for this conversation
    attached_docs: List[Dict[str, Any]] = []
    native_attachments: List[Dict[str, Any]] = []
    if conversation_id:
        attached_docs = await load_full(db, ctx.business_id, conversation_id)
        provider = resolve_model(model_id)["provider"]
        if provider == "anthropic":
            for d in attached_docs:
                if d.get("b64") and d.get("kind") in ("image", "pdf"):
                    native_attachments.append({
                        "kind": d["kind"],
                        "mime_type": d.get("mime_type"),
                        "filename": d.get("filename"),
                        "b64": d["b64"],
                    })

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_text}]

    # Inject shared agent workspace context (set by routes.py when agents switch).
    # This lets the incoming agent know what was decided in prior sessions
    # (product chosen, campaign goal, approved copy, brand color, etc.)
    _workspace_ctx = user.get("_workspace_context", "")
    if _workspace_ctx:
        messages.append({"role": "system", "content": _workspace_ctx})

    # Mirror AutoReply v2's mini-state pattern: when running the design agent,
    # inject a compact snapshot of locked template / platform / staged image so
    # the model can't silently drift onto a different template across turns.
    # Note: social_media is excluded — it uses its own STEP 0-8 session flow.
    if active_agent_id in ("design", "creative") and conversation_id:
        try:
            from .design_state import (
                load_design_state,
                format_design_state_for_prompt,
                update_design_state,
                _STEP_NEXT_ACTION,
            )

            ds = await load_design_state(db, conversation_id, ctx.business_id)
            # Bootstrap flow_step on the very first design-agent turn
            if not ds.get("flow_step"):
                await update_design_state(
                    db, conversation_id, ctx.business_id,
                    flow_step="awaiting_product",
                )
                ds["flow_step"] = "awaiting_product"
            ds_block = format_design_state_for_prompt(ds)
            if ds_block:
                messages.append({"role": "system", "content": ds_block})
        except Exception:
            logger.exception("[orchestrator] design state injection skipped")

    try:
        from saved_designs import build_design_library_context_message

        lib_ctx = await build_design_library_context_message(db, ctx.business_id)
        if lib_ctx:
            messages.append({"role": "system", "content": lib_ctx})
    except Exception:
        logger.exception("[orchestrator] design library context skipped")
    # Append document context (text) as a second system message.
    # For LONG docs we also note that the `search_documents` tool is available so
    # the model can pull additional excerpts instead of relying on the truncated preamble.
    if attached_docs:
        preamble = build_context_preamble(attached_docs)
        if preamble:
            has_long_doc = any(
                (d.get("text_len") or len(d.get("text") or "")) >= 6000 for d in attached_docs
            )
            if has_long_doc:
                preamble += (
                    "\n\nNote: at least one document is long and has been chunked. "
                    "Call the `search_documents` tool with a natural-language query whenever "
                    "you need passages that aren't in the excerpt above."
                )
            messages.append({"role": "system", "content": preamble})
    _ctx_block = format_context_block(_rag_ctx)
    if _ctx_block:
        messages.append({"role": "system", "content": _ctx_block})

    # Inject Planner hint for complex multi-step requests
    _plan_hint = format_plan_hint(_execution_plan)
    if _plan_hint:
        messages.append({"role": "system", "content": _plan_hint})

    # Sliding window: compress old history into a summary when conversation is long.
    history = await _compress_history(history, model_id)

    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    steps: List[Dict[str, Any]] = []
    messages_to_append: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]

    # Load stored pending confirmation to gate approval correctly.
    # Without this, any "yes" reply to an unrelated question (e.g. "Yes, use blue")
    # would auto-approve a destructive broadcast that was pending from a different context.
    _stored_pending: Optional[Dict[str, Any]] = None
    if conversation_id:
        try:
            _conv_snap = await db.assistant_conversations.find_one(
                {"_id": conversation_id}, {"pending_confirmation": 1}
            )
            if _conv_snap:
                _stored_pending = _conv_snap.get("pending_confirmation")
        except Exception:
            pass

    is_confirmation_reply = user_message.strip().lower() in AFFIRMATIVE
    approved_destructive = auto_approve_destructive or (is_confirmation_reply and _stored_pending is not None)

    pending_confirmation: Optional[Dict[str, Any]] = None
    model_used = model_id or ""
    _tokens_used = 0  # running total for circuit breaker
    _handoff_agent: Optional[str] = None

    for step_idx in range(MAX_STEPS):
        # Circuit breaker: abort before the next LLM call if we've already spent
        # too many tokens this turn (prevents runaway loops from being expensive).
        if _tokens_used >= _MAX_TOKENS_PER_TURN:
            _tlog.warning(
                "[turn.circuit_breaker] token budget exceeded: %d >= %d — stopping loop",
                _tokens_used, _MAX_TOKENS_PER_TURN,
            )
            break

        resp = await chat_with_tools(
            messages=messages,
            tools=tool_specs,
            model_id=model_id,
            # Attach on the first LLM call only — subsequent tool-loop rounds
            # already have the system context and should not re-upload the files.
            attachments=native_attachments if step_idx == 0 else None,
        )
        model_used = resp.get("model", model_used)
        # Accumulate token usage from the provider response.
        _usage = resp.get("raw", {}).get("usage", {}) if isinstance(resp.get("raw"), dict) else {}
        _tokens_used += (_usage.get("total_tokens") or _usage.get("input_tokens", 0) + _usage.get("output_tokens", 0))

        tool_calls = resp.get("tool_calls") or []
        # Echo the assistant message (with any tool_calls) back into the running
        # messages list so the subsequent tool role messages reference the right ids.
        asst_msg = resp.get("raw_assistant_message") or {
            "role": "assistant",
            "content": resp.get("content", ""),
        }
        messages.append(asst_msg)

        if not tool_calls:
            _tlog.info("[turn.done] steps=%d tokens_used=%d", step_idx, _tokens_used)
            final = resp.get("content", "")
            # Critic: review the draft before returning. No-ops unless CRITIC_ENABLED=true.
            final = await critique(
                draft=final,
                user_message=user_message,
                knowledge_chunks=_rag_ctx.get("knowledge_chunks", []),
                tool_steps=steps,
                system_prompt=system_text,
            )
            messages_to_append.append({"role": "assistant", "content": final})
            # Memory flush: every MEMORY_FLUSH_EVERY turns, summarize + embed async.
            _flush_every = int(os.getenv("MEMORY_FLUSH_EVERY", "10"))
            _business_id = str(user.get("business_id") or user.get("_id", ""))
            def _log_bg_task_error(task: asyncio.Task) -> None:
                """Callback to surface unhandled exceptions from fire-and-forget tasks."""
                if not task.cancelled():
                    exc = task.exception()
                    if exc:
                        logger.warning("[orchestrator] background task %s failed: %s", task.get_name(), exc)

            if len(history) > 0 and (len(history) + 1) % _flush_every == 0:
                from memory.flush import flush_to_long_term
                _t1 = asyncio.create_task(flush_to_long_term(
                    customer_id=str(user.get("_id", "")),
                    business_id=_business_id,
                    turns=history[-_flush_every:],
                ))
                _t1.add_done_callback(_log_bg_task_error)
            # Owner preference flush: fires every turn on the last N messages
            _t2 = asyncio.create_task(_flush_owner_prefs_bg(
                business_id=_business_id,
                turns=messages_to_append,
                agent_id=active_agent_id,
            ))
            _t2.add_done_callback(_log_bg_task_error)
            return await _finalize_turn(
                {
                    "reply": final,
                    "steps": steps,
                    "messages_to_append": messages_to_append,
                    "model": model_used,
                    "needs_confirmation": pending_confirmation,
                    "active_agent": active_agent_id,
                    "_db": db,
                    "_business_id": _business_id,
                    "_conversation_id": conversation_id,
                    "_routing_method": "orchestrator",
                    "_tokens_used": _tokens_used,
                },
                user_message,
            )

        # ── Parallel tool execution ───────────────────────────────────────────
        # Separate destructive tools (need sequential confirmation gate) from
        # safe tools (can run concurrently). If ANY destructive tool is present
        # and not yet approved, stop and ask for confirmation immediately.
        _safe_tcs: List[Dict[str, Any]] = []
        for tc in tool_calls:
            name = tc.get("name")
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except Exception:
                    args = {}
            tc["arguments"] = args  # normalize in-place

            if not name:
                logger.error("[orchestrator] tool_call missing name: %s", tc)
                steps.append({"tool": "(invalid)", "arguments": tc, "result": {"error": "Model returned a tool call without a name — retry the message."}})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or str(uuid.uuid4()),
                    "content": json.dumps({"error": "Malformed tool call (missing name)."}, default=str),
                })
                continue

            spec = REGISTRY.get(name)
            if spec and spec.get("destructive") and not approved_destructive:
                pending_confirmation = {
                    "tool": name,
                    "arguments": args,
                    "reason": f"Destructive action `{name}` requires confirmation.",
                }
                preview_text = _describe_destructive(name, args)
                messages_to_append.append({"role": "assistant", "content": preview_text})
                return await _finalize_turn(
                    {
                        "reply": preview_text,
                        "steps": steps,
                        "messages_to_append": messages_to_append,
                        "model": model_used,
                        "needs_confirmation": pending_confirmation,
                        "active_agent": active_agent_id,
                        "_db": db,
                        "_business_id": _business_id,
                        "_conversation_id": conversation_id,
                        "_routing_method": "orchestrator",
                        "_tokens_used": _tokens_used,
                    },
                    user_message,
                )
            _safe_tcs.append(tc)

        if not _safe_tcs:
            continue

        # Run all safe tool calls concurrently
        async def _exec_one(tc: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
            name = tc["name"]
            args = tc["arguments"]
            result = await run_tool(name, ctx, args)
            return tc, result

        _tlog.info("[turn.tools] step=%d parallel=%d tools=%s", step_idx, len(_safe_tcs), [t["name"] for t in _safe_tcs])
        results_pairs = await asyncio.gather(*[_exec_one(tc) for tc in _safe_tcs], return_exceptions=True)

        _LLM_STRIP_FIELDS = {"html_preview", "content_md"}
        for pair in results_pairs:
            if isinstance(pair, BaseException):
                logger.error("[orchestrator] tool coroutine raised: %s", pair)
                continue
            tc, result = pair
            tc_id = tc.get("id") or str(uuid.uuid4())
            name = tc["name"]
            args = tc["arguments"]
            spec = REGISTRY.get(name)
            capped = _limit_tool_result_size(result)
            steps.append({"tool": name, "arguments": args, "result": capped})

            # ── Handoff signal detection ──────────────────────────────────────
            if isinstance(capped, dict) and "__handoff__" in capped:
                _handoff_agent = str(capped["__handoff__"])
                logger.info(
                    "[orchestrator.handoff] agent=%s → %s (reason: %s)",
                    active_agent_id, _handoff_agent, capped.get("reason", ""),
                )
                break  # break inner loop

            if isinstance(result, dict) and result.get("error"):
                try:
                    logger.error(
                        "[assistant.tool_error] tool=%s agent=%s conv=%s user=%s args=%s error=%r",
                        name, active_agent_id, conversation_id, ctx.user_id,
                        json.dumps(args, default=str)[:1500], result.get("error"),
                    )
                except Exception:
                    logger.exception("[assistant.tool_error] log emission failed (tool=%s)", name)

            if spec and spec.get("destructive"):
                try:
                    await ctx.db.assistant_audit_log.insert_one({
                        "_id": str(uuid.uuid4()),
                        "user_id": ctx.business_id,
                        "actor_id": ctx.user_id,
                        "tool": name,
                        "arguments": args,
                        "result": capped,
                        "success": not (isinstance(result, dict) and "error" in result),
                        "agent": active_agent_id,
                        "created_at": datetime.utcnow(),
                    })
                except Exception as e:
                    logger.warning("[assistant.audit] failed to write log: %s", e)

            llm_result = (
                {k: v for k, v in capped.items() if k not in _LLM_STRIP_FIELDS}
                if isinstance(capped, dict) else capped
            )
            try:
                tool_payload = json.dumps(llm_result, default=str)
            except (TypeError, ValueError) as ser_err:
                logger.exception("[orchestrator] tool result not JSON-serializable (tool=%s)", name)
                tool_payload = json.dumps(
                    {"error": "Tool output could not be serialized", "tool": name, "detail": str(ser_err)},
                    default=str,
                )
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": tool_payload,
            })

        if _handoff_agent:
            break  # break outer step_idx loop

    # ── Handoff re-run (max 1 hop to prevent loops) ─────────────────────────
    if _handoff_agent and _handoff_depth < 1:
        logger.info("[orchestrator.handoff] re-running turn with agent=%s", _handoff_agent)
        return await run_turn(
            db=db, user=user, history=history, user_message=user_message,
            model_id=model_id, auto_approve_destructive=auto_approve_destructive,
            conversation_id=conversation_id, agent_id=_handoff_agent,
            _handoff_depth=_handoff_depth + 1,
        )

    # Hit step limit without a final answer
    _tlog.warning("[turn.step_limit] hit MAX_STEPS=%d without final answer", MAX_STEPS)
    fallback = "I've gathered a lot of info but couldn't finish the task in one go. Ask me to narrow it down or try again."
    messages_to_append.append({"role": "assistant", "content": fallback})
    return await _finalize_turn(
        {
            "reply": fallback,
            "steps": steps,
            "messages_to_append": messages_to_append,
            "model": model_used,
            "needs_confirmation": pending_confirmation,
            "active_agent": active_agent_id,
            "_db": db,
            "_business_id": _business_id,
            "_conversation_id": conversation_id,
            "_routing_method": "orchestrator",
            "_tokens_used": _tokens_used,
        },
        user_message,
    )


async def run_turn_stream(
    *,
    db,
    user: Dict[str, Any],
    history: List[Dict[str, Any]],
    user_message: str,
    model_id: Optional[str] = None,
    auto_approve_destructive: bool = False,
    conversation_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    _handoff_depth: int = 0,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Like run_turn but yields SSE-style dicts during execution.

    Yields:
        {"type": "tool_start", "tool": name}       — each tool call as it fires
        {"type": "token", "text": chunk}            — streamed reply tokens
        {"type": "done", ...full result payload...} — final summary (same shape as run_turn)
        {"type": "error", "message": str}           — on failure
    """
    # ── Trivial message fast-path ────────────────────────────────────────────
    # Emit done immediately — no tool calls, no spinner delay.
    import random as _random_s
    if _is_trivial_message(user_message, history):
        _reply_s = _random_s.choice(_TRIVIAL_REPLIES)
        _trivial_msgs_s = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": _reply_s},
        ]
        yield {"type": "token", "text": _reply_s}
        yield {
            "type": "done",
            "reply": _reply_s,
            "steps": [],
            "model": model_id or "",
            "needs_confirmation": None,
            "active_agent": agent_id or "general",
            "active_agent_label": "Zilo",
            "messages_to_append": _trivial_msgs_s,
            "conversation_id": conversation_id,
        }
        return

    user = {**user, "_active_conversation_id": conversation_id}
    ctx = ToolContext(db, user)

    ag_cfg = get_agent_config(agent_id)
    active_agent_id = ag_cfg["id"]
    allowed = ag_cfg.get("allowed_tools")
    tool_specs = openai_tool_specs_filtered(allowed) if allowed is not None else openai_tool_specs()
    if ag_cfg.get("use_default_system_prompt"):
        system_text = SYSTEM_PROMPT
    else:
        system_text = (ag_cfg.get("system_prompt") or SYSTEM_PROMPT).strip()
    
    # Prepend memory awareness header to ALL agents (streaming path)
    _MEMORY_HEADER = """**MEMORY AWARENESS — Read This Before Every Response**

Before calling ANY tools or asking ANY questions, check conversation history and memory context for existing answers:

1. **Platform already mentioned?** (Instagram, Facebook, TikTok, LinkedIn, etc.) → Use it. Don't re-ask.
2. **Product already chosen?** (Product names, SKUs, items) → Use it. Don't re-ask.
3. **Format already specified?** (Carousel, single post, 3 slides, 5 slides) → Use it. Don't re-ask.
4. **Topic already discussed?** (What they're working on) → Continue from there. Don't restart.
5. **Decision already made?** (Approved copy, chose style, selected option) → Proceed. Don't re-confirm.

**If the answer is in conversation history or memory context above, use it immediately. Do NOT call tools to re-fetch information you already have.**

**The user should NEVER have to repeat themselves. If they already told you something, you remember it.**

---

"""
    
    system_text = f"{AGENT_OWNERSHIP_CONTRACT}\n\n{_MEMORY_HEADER}{system_text}".strip()
    if ag_cfg.get("model"):
        model_id = ag_cfg["model"]

    # Run plan + RAG context in parallel — both are independent reads.
    # Previously sequential; now firing together saves the full planner latency.
    _execution_plan, _rag_ctx = await asyncio.gather(
        plan(user_message, list(allowed or [])),
        build_context(
            db=db,
            user_id=str(user.get("_id", "")),
            business_id=str(user.get("business_id") or user.get("_id", "")),
            user_message=user_message,
        ),
    )

    attached_docs: List[Dict[str, Any]] = []
    native_attachments: List[Dict[str, Any]] = []
    if conversation_id:
        attached_docs = await load_full(db, ctx.business_id, conversation_id)
        provider = resolve_model(model_id)["provider"]
        if provider == "anthropic":
            for d in attached_docs:
                if d.get("b64") and d.get("kind") in ("image", "pdf"):
                    native_attachments.append({
                        "kind": d["kind"], "mime_type": d.get("mime_type"),
                        "filename": d.get("filename"), "b64": d["b64"],
                    })

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_text}]

    # Inject shared agent workspace context when agent switches
    _workspace_ctx_s = user.get("_workspace_context", "")
    if _workspace_ctx_s:
        messages.append({"role": "system", "content": _workspace_ctx_s})

    # Note: social_media is excluded — it uses its own STEP 0-8 session flow.
    if active_agent_id in ("design", "creative") and conversation_id:
        try:
            from .design_state import load_design_state, format_design_state_for_prompt, update_design_state
            ds = await load_design_state(db, conversation_id, ctx.business_id)
            if not ds.get("flow_step"):
                await update_design_state(db, conversation_id, ctx.business_id, flow_step="awaiting_product")
                ds["flow_step"] = "awaiting_product"
            ds_block = format_design_state_for_prompt(ds)
            if ds_block:
                messages.append({"role": "system", "content": ds_block})
        except Exception:
            pass

    try:
        from saved_designs import build_design_library_context_message
        lib_ctx = await build_design_library_context_message(db, ctx.business_id)
        if lib_ctx:
            messages.append({"role": "system", "content": lib_ctx})
    except Exception:
        pass

    if attached_docs:
        preamble = build_context_preamble(attached_docs)
        if preamble:
            has_long_doc = any((d.get("text_len") or len(d.get("text") or "")) >= 6000 for d in attached_docs)
            if has_long_doc:
                preamble += "\n\nNote: at least one document is long. Call `search_documents` for additional excerpts."
            messages.append({"role": "system", "content": preamble})
    _ctx_block = format_context_block(_rag_ctx)
    if _ctx_block:
        messages.append({"role": "system", "content": _ctx_block})

    _plan_hint = format_plan_hint(_execution_plan)
    if _plan_hint:
        messages.append({"role": "system", "content": _plan_hint})

    # Sliding window: compress old history into a summary when conversation is long.
    history = await _compress_history(history, model_id)

    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    steps: List[Dict[str, Any]] = []
    messages_to_append: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]

    _stored_pending_s: Optional[Dict[str, Any]] = None
    if conversation_id:
        try:
            _conv_snap_s = await db.assistant_conversations.find_one(
                {"_id": conversation_id}, {"pending_confirmation": 1}
            )
            if _conv_snap_s:
                _stored_pending_s = _conv_snap_s.get("pending_confirmation")
        except Exception:
            pass

    is_confirmation_reply = user_message.strip().lower() in AFFIRMATIVE
    approved_destructive = auto_approve_destructive or (is_confirmation_reply and _stored_pending_s is not None)
    pending_confirmation: Optional[Dict[str, Any]] = None
    model_used = model_id or ""
    _tokens_used = 0  # running total for circuit breaker
    _stream_handoff_agent: Optional[str] = None

    for step_idx in range(MAX_STEPS):
        if _tokens_used >= _MAX_TOKENS_PER_TURN:
            logger.warning("[run_turn_stream.circuit_breaker] token budget %d exceeded", _MAX_TOKENS_PER_TURN)
            break

        resp = await chat_with_tools(
            messages=messages,
            tools=tool_specs,
            model_id=model_id,
            attachments=native_attachments if step_idx == 0 else None,
        )
        model_used = resp.get("model", model_used)
        _usage = resp.get("raw", {}).get("usage", {}) if isinstance(resp.get("raw"), dict) else {}
        _tokens_used += (_usage.get("total_tokens") or _usage.get("input_tokens", 0) + _usage.get("output_tokens", 0))
        tool_calls = resp.get("tool_calls") or []
        asst_msg = resp.get("raw_assistant_message") or {"role": "assistant", "content": resp.get("content", "")}
        messages.append(asst_msg)

        if not tool_calls:
            # ── Final reply ───────────────────────────────────────────────────
            # If this is the first step (no tool calls ran), we already have the
            # full content from chat_with_tools — stream it directly without a
            # second LLM round-trip. Only fall back to stream_reply after tool
            # calls, where the model needs to see the tool results and generate
            # a fresh response.
            pre_fetched = (resp.get("content") or "").strip()
            reply_text = ""
            if step_idx == 0 and pre_fetched:
                # Emit the already-fetched content token-by-token (small chunks
                # so the frontend renders progressively, just like real streaming).
                _CHUNK = 24
                for _i in range(0, len(pre_fetched), _CHUNK):
                    _tok = pre_fetched[_i: _i + _CHUNK]
                    reply_text += _tok
                    yield {"type": "token", "text": _tok}
            else:
                # After tool calls: model must see tool results → real stream call.
                stream_context = messages[:-1]  # drop the empty final assistant msg
                try:
                    async for token in stream_reply(messages=stream_context, tools=[], model_id=model_id):
                        reply_text += token
                        yield {"type": "token", "text": token}
                except Exception as stream_err:
                    logger.warning("[run_turn_stream] stream_reply failed, using pre-computed reply: %s", stream_err)
                    reply_text = resp.get("content", "")
                    yield {"type": "token", "text": reply_text}

            if not reply_text:
                reply_text = resp.get("content", "")

            # Fire chip generation immediately — runs in parallel with critique
            # so the latency is hidden and chips are ready when the response is assembled.
            _chips_task = asyncio.create_task(
                _build_chips_safe(active_agent_id, user_message, reply_text)
            )

            final = await critique(
                draft=reply_text,
                user_message=user_message,
                knowledge_chunks=_rag_ctx.get("knowledge_chunks", []),
                tool_steps=steps,
                system_prompt=system_text,
            )
            messages_to_append.append({"role": "assistant", "content": final})

            # Owner preference flush (stream path)
            asyncio.create_task(_flush_owner_prefs_bg(
                business_id=str(user.get("business_id") or user.get("_id", "")),
                turns=messages_to_append,
                agent_id=active_agent_id,
            ))

            # Collect chips — almost certainly done by now since critique ran in parallel
            try:
                _precomputed_sugs = await asyncio.wait_for(asyncio.shield(_chips_task), timeout=4.0)
            except Exception:
                _precomputed_sugs = []

            result = await _finalize_turn(
                {
                    "reply": final,
                    "steps": steps,
                    "messages_to_append": messages_to_append,
                    "model": model_used,
                    "needs_confirmation": pending_confirmation,
                    "active_agent": active_agent_id,
                    "_db": db,
                    "_conversation_id": conversation_id,
                    "_routing_method": "orchestrator",
                    "_tokens_used": _tokens_used,
                    "reply_suggestions": _precomputed_sugs,
                },
                user_message,
            )
            yield {"type": "done", **result}
            return

        # ── Parallel tool execution (stream) ─────────────────────────────────
        # Normalize args and check for destructive tools first (sequential gate).
        _safe_stream_tcs: List[Dict[str, Any]] = []
        for tc in tool_calls:
            name = tc.get("name")
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except Exception:
                    args = {}
            tc["arguments"] = args

            if not name:
                messages.append({"role": "tool", "tool_call_id": tc.get("id") or str(uuid.uuid4()), "content": json.dumps({"error": "Malformed tool call."}, default=str)})
                continue

            spec = REGISTRY.get(name)
            if spec and spec.get("destructive") and not approved_destructive:
                pending_confirmation = {"tool": name, "arguments": args, "reason": f"Destructive action `{name}` requires confirmation."}
                preview_text = _describe_destructive(name, args)
                messages_to_append.append({"role": "assistant", "content": preview_text})
                result = await _finalize_turn(
                    {"reply": preview_text, "steps": steps, "messages_to_append": messages_to_append,
                     "model": model_used, "needs_confirmation": pending_confirmation, "active_agent": active_agent_id,
                     "_db": db, "_conversation_id": conversation_id, "_routing_method": "orchestrator",
                     "_tokens_used": _tokens_used},
                    user_message,
                )
                yield {"type": "token", "text": preview_text}
                yield {"type": "done", **result}
                return
            _safe_stream_tcs.append(tc)

        if not _safe_stream_tcs:
            continue

        # Emit tool_start events before launching (so UI shows spinners immediately)
        for tc in _safe_stream_tcs:
            yield {"type": "tool_start", "tool": tc["name"]}

        # Run all safe tools concurrently
        async def _exec_stream_one(tc: Dict[str, Any]) -> Tuple[Dict[str, Any], Any]:
            return tc, await run_tool(tc["name"], ctx, tc["arguments"])

        stream_results = await asyncio.gather(*[_exec_stream_one(tc) for tc in _safe_stream_tcs], return_exceptions=True)

        _LLM_STRIP_FIELDS = {"html_preview", "content_md"}
        for pair in stream_results:
            if isinstance(pair, BaseException):
                logger.error("[run_turn_stream] tool coroutine raised: %s", pair)
                continue
            tc, result_data = pair
            tc_id = tc.get("id") or str(uuid.uuid4())
            name = tc["name"]
            args = tc["arguments"]
            spec = REGISTRY.get(name)
            capped = _limit_tool_result_size(result_data)
            steps.append({"tool": name, "arguments": args, "result": capped})

            # ── Handoff signal detection (stream) ─────────────────────────────
            if isinstance(capped, dict) and "__handoff__" in capped:
                _stream_handoff_agent = str(capped["__handoff__"])
                logger.info(
                    "[run_turn_stream.handoff] agent=%s → %s (reason: %s)",
                    active_agent_id, _stream_handoff_agent, capped.get("reason", ""),
                )
                break  # break inner loop

            if isinstance(result_data, dict) and result_data.get("error"):
                logger.error("[run_turn_stream.tool_error] tool=%s error=%r", name, result_data.get("error"))

            if spec and spec.get("destructive"):
                try:
                    await ctx.db.assistant_audit_log.insert_one({
                        "_id": str(uuid.uuid4()), "user_id": ctx.business_id, "actor_id": ctx.user_id,
                        "tool": name, "arguments": args, "result": capped,
                        "success": not (isinstance(result_data, dict) and "error" in result_data),
                        "agent": active_agent_id, "created_at": datetime.utcnow(),
                    })
                except Exception:
                    pass

            llm_result = (
                {k: v for k, v in capped.items() if k not in _LLM_STRIP_FIELDS}
                if isinstance(capped, dict) else capped
            )
            try:
                tool_payload = json.dumps(llm_result, default=str)
            except Exception:
                tool_payload = json.dumps({"error": "Tool output could not be serialized."}, default=str)
            messages.append({"role": "tool", "tool_call_id": tc_id, "content": tool_payload})

        if _stream_handoff_agent:
            break  # break outer step_idx loop

    # ── Handoff re-run for streaming (max 1 hop to prevent loops) ─────────────
    if _stream_handoff_agent and _handoff_depth < 1:
        logger.info("[run_turn_stream.handoff] re-streaming turn with agent=%s", _stream_handoff_agent)
        async for event in run_turn_stream(
            db=db, user=user, history=history, user_message=user_message,
            model_id=model_id, auto_approve_destructive=auto_approve_destructive,
            conversation_id=conversation_id, agent_id=_stream_handoff_agent,
            _handoff_depth=_handoff_depth + 1,
        ):
            yield event
        return

    # Step limit fallback
    fallback = "I've gathered a lot of info but couldn't finish the task in one go. Ask me to narrow it down or try again."
    messages_to_append.append({"role": "assistant", "content": fallback})
    result = await _finalize_turn(
        {"reply": fallback, "steps": steps, "messages_to_append": messages_to_append,
         "model": model_used, "needs_confirmation": pending_confirmation, "active_agent": active_agent_id,
         "_db": db, "_conversation_id": conversation_id, "_routing_method": "orchestrator",
         "_tokens_used": _tokens_used},
        user_message,
    )
    yield {"type": "token", "text": fallback}
    yield {"type": "done", **result}


def _describe_destructive(name: str, args: Dict[str, Any]) -> str:
    blurbs = {
        "create_customer":        lambda a: f"Add new customer **{a.get('name')}** ({a.get('phone_number')})?",
        "create_followup":        lambda a: f"Set a follow-up on customer `{a.get('customer_id')}` for `{a.get('when')}`?",
        "send_whatsapp_message":  lambda a: f"Send this WhatsApp message to customer `{a.get('customer_id')}`?\n\n> {a.get('message')}",
        "create_broadcast":       lambda a: f"Broadcast this message to audience `{a.get('filter_type','all')}`?\n\n> {a.get('message')}",
        "disconnect_telegram":    lambda a: "Disconnect the Telegram bot? Incoming Telegram messages will stop.",
    }
    blurb = blurbs.get(name, lambda a: f"Run `{name}` with {a}?")(args)
    return f"{blurb}\n\nReply **yes** to confirm, or tell me what to change."

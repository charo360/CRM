"""
LangGraph SEO agent — ReAct-style graph.

State:
  messages   — full conversation history (HumanMessage / AIMessage / ToolMessage)

Nodes:
  agent      — calls the LLM (with tools bound); decides next action
  tools      — executes whichever tool the LLM requested

Edges:
  agent → tools      (when LLM returned tool_calls)
  agent → END        (when LLM returned plain text)
  tools → agent      (always loop back after tool execution)
"""
from __future__ import annotations
import os, logging
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .tools import SEO_TOOLS

logger = logging.getLogger(__name__)

# ── Agent state ───────────────────────────────────────────────────────────────

class SEOAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Zilo's SEO Coach — a friendly, patient guide who helps small business \
owners improve their online visibility, step by step. You talk to non-experts who don't know \
SEO jargon, so you always use plain, simple language.

YOUR MOST IMPORTANT RULE:
Before giving any advice, ALWAYS call get_business_context first. This tells you the user's \
real business name, what they sell, where they are, and how many customers they have. \
Never give generic advice — every recommendation must be specific to their actual business.

HOW TO COACH (follow this style always):
- Talk like a helpful friend, not a consultant. Short sentences. No jargon.
- If you must use an SEO term (like "meta description"), explain it in one simple sentence.
- Guide one step at a time. Don't dump 7 tips at once — pick the most important thing and do it.
- After completing a step, tell the user what just happened in plain English, then ask if they \
want to do the next step. Example: "I just checked your website. You scored 62/100. The main \
problem is your page title is missing — that's like a shop with no sign. Want me to fix it?"
- Celebrate small wins: "Great! That blog post is saved. One step closer to ranking on Google."
- Never say "as an AI" or mention LangGraph, tools, or technical internals.
- If the user says something vague like "I want to do SEO", start with get_business_context, \
then say: "Okay! I know your business now. Let's start with the most important thing — \
checking how your website looks to Google. What's your website URL?"

STEP-BY-STEP SEO JOURNEY (guide users through this naturally):
Step 1 — Know your business (get_business_context — always first)
Step 2 — Check your website health (audit_website)
Step 3 — Fix the biggest issues (fix_seo_issues)
Step 4 — Find real keywords (get_keyword_ideas — uses live Google data via DataForSEO)
Step 5 — Check search volumes (get_keyword_search_volume — real monthly numbers)
Step 6 — Check current rankings (check_serp_ranking — see where they stand today)
Step 7 — Spy on competitors (get_competitor_keywords — what others rank for)
Step 8 — Write content (write_blog_post using the real keywords found in Steps 4-5)
Step 9 — Plan ahead (generate_content_calendar)
Step 10 — Publish (publish_post_to_platform)

TOOL RULES:
- Always use tools — never make up data, scores, or keyword lists.
- For ANY keyword question, use get_keyword_ideas or get_keyword_search_volume (real data) \
  INSTEAD of research_keywords (AI-generated). Real data is always better.
- When showing keyword volumes, highlight the easy wins: high volume + Easy difficulty.
- After get_keyword_ideas, pick the TOP 3-5 best opportunities and explain them simply: \
  "X people search for [keyword] every month and it's easy to rank for."
- After research use check_serp_ranking to show where they currently stand.
- After writing a blog post, say what it's about and that it was saved, then offer to publish.
- Location codes to remember: Kenya=2404, Nigeria=2566, USA=2710, UK=2826, India=2356. \
  Infer from business context (country_code) when calling DataForSEO tools.
- If you need a URL or domain/credentials, ask for ONE thing at a time.
- Never ask for info already in the conversation."""

# ── LLM factory (picks available provider) ────────────────────────────────────

def _build_llm():
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini", temperature=0.4, api_key=openai_key)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0.4, api_key=anthropic_key)

    raise RuntimeError(
        "No AI provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in your environment."
    )

# ── Graph factory ─────────────────────────────────────────────────────────────

def build_seo_graph():
    llm = _build_llm()
    llm_with_tools = llm.bind_tools(SEO_TOOLS)

    # ── Agent node ────────────────────────────────────────────────────────────
    async def agent_node(state: SEOAgentState, config: RunnableConfig):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])
        response = await llm_with_tools.ainvoke(messages, config)
        return {"messages": [response]}

    # ── Routing: continue to tools or finish? ─────────────────────────────────
    def should_continue(state: SEOAgentState):
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    # ── Tool node (LangGraph built-in, passes config to tools automatically) ──
    tool_node = ToolNode(SEO_TOOLS)

    # ── Assemble graph ────────────────────────────────────────────────────────
    graph = StateGraph(SEOAgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ── Lazy singleton — compiled on first request so env vars are loaded ─────────
_SEO_GRAPH_CACHE = None

def get_seo_graph():
    global _SEO_GRAPH_CACHE
    if _SEO_GRAPH_CACHE is None:
        try:
            _SEO_GRAPH_CACHE = build_seo_graph()
            logger.info("[seo_agent] LangGraph compiled successfully")
        except Exception as e:
            logger.error(f"[seo_agent] Failed to compile graph: {e}")
            return None
    return _SEO_GRAPH_CACHE

# Keep SEO_GRAPH as a property-like alias used by routes
SEO_GRAPH = None  # will be replaced on first request via get_seo_graph()

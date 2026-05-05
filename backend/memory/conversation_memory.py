"""Conversation memory — persistent context across chat sessions.

Stores factual information about what the user is working on, recent topics,
and key decisions. Separate from owner_prefs (which stores style preferences).

MongoDB collection: conversation_memory
  document per business_id:
  {
    "business_id": str,
    "current_project": str,           # "Building Instagram carousel for Zilo Starter"
    "recent_topics": list[str],       # Last 5 topics discussed
    "key_facts": dict,                # {"product": "Zilo Starter", "platform": "Instagram"}
    "decisions_made": list[str],      # ["Approved 3-slide carousel", "Chose benefit-first copy"]
    "last_conversation_summary": str, # Summary of last session
    "updated_at": datetime,
  }
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_COLLECTION = "conversation_memory"


async def load_conversation_memory(
    db,
    business_id: str,
) -> Dict[str, Any]:
    """Load persistent conversation memory for a business.
    
    Returns:
        {
            "current_project": str,
            "recent_topics": list[str],
            "key_facts": dict,
            "decisions_made": list[str],
            "last_conversation_summary": str,
        }
    """
    try:
        doc = await db[_COLLECTION].find_one({"business_id": business_id})
        if not doc:
            return {
                "current_project": "",
                "recent_topics": [],
                "key_facts": {},
                "decisions_made": [],
                "last_conversation_summary": "",
            }
        
        return {
            "current_project": doc.get("current_project", ""),
            "recent_topics": doc.get("recent_topics", [])[:5],  # Last 5 topics
            "key_facts": doc.get("key_facts", {}),
            "decisions_made": doc.get("decisions_made", [])[-10:],  # Last 10 decisions
            "last_conversation_summary": doc.get("last_conversation_summary", ""),
        }
    except Exception as exc:
        logger.warning("[conversation_memory.load] failed: %s", exc)
        return {
            "current_project": "",
            "recent_topics": [],
            "key_facts": {},
            "decisions_made": [],
            "last_conversation_summary": "",
        }


async def update_conversation_memory(
    db,
    business_id: str,
    turns: List[Dict[str, Any]],
) -> None:
    """Extract key information from conversation and update memory.
    
    Called after each conversation to persist context for next session.
    Uses LLM to extract:
    - Current project/topic
    - Key facts mentioned
    - Decisions made
    - Summary for next time
    """
    if not turns or len(turns) < 2:
        return
    
    try:
        # Build conversation text
        text_parts = []
        for t in turns[-10:]:  # Last 10 turns only
            role = t.get("role", "")
            content = t.get("content") or ""
            if isinstance(content, str) and content.strip() and role in ("user", "assistant"):
                label = "User" if role == "user" else "Assistant"
                text_parts.append(f"{label}: {content[:500]}")
        
        if len(text_parts) < 2:
            return
        
        conversation_text = "\n".join(text_parts)
        
        # Extract memory using LLM
        from assistant.models import chat_with_tools
        
        resp = await chat_with_tools(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are analyzing a conversation to extract persistent memory.\n\n"
                        "Extract the following in JSON format:\n"
                        "{\n"
                        '  "current_project": "What is the user currently working on? (one sentence)",\n'
                        '  "key_facts": {"key": "value", ...},  // Important facts mentioned (product names, platforms, formats, etc.)\n'
                        '  "decisions_made": ["decision 1", "decision 2"],  // Explicit approvals or choices\n'
                        '  "topic": "Main topic of this conversation (3-5 words)"\n'
                        "}\n\n"
                        "Rules:\n"
                        "- current_project: What they're building/working on right now\n"
                        "- key_facts: Concrete details (product='Zilo Starter', platform='Instagram', format='3-slide carousel')\n"
                        "- decisions_made: Only explicit approvals ('approved carousel', 'chose benefit-first copy')\n"
                        "- topic: Brief label for this conversation\n"
                        "- If nothing substantive, return empty strings/arrays\n"
                        "- Output ONLY valid JSON, no markdown, no explanation"
                    ),
                },
                {"role": "user", "content": conversation_text},
            ],
            tools=[],
            temperature=0.1,
            timeout=10.0,
        )
        
        import json
        import re
        
        raw = (resp.get("content") or "").strip()
        # Extract JSON from potential markdown code block
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if not match:
            logger.debug("[conversation_memory] no JSON found in LLM response")
            return
        
        extracted = json.loads(match.group())
        
        current_project = extracted.get("current_project", "").strip()
        key_facts = extracted.get("key_facts", {})
        decisions = extracted.get("decisions_made", [])
        topic = extracted.get("topic", "").strip()
        
        # Load existing memory
        existing = await db[_COLLECTION].find_one({"business_id": business_id}) or {}
        
        # Merge key facts (new facts override old)
        merged_facts = existing.get("key_facts", {})
        merged_facts.update(key_facts)
        
        # Append new decisions (keep last 20)
        existing_decisions = existing.get("decisions_made", [])
        all_decisions = existing_decisions + decisions
        all_decisions = all_decisions[-20:]  # Keep last 20
        
        # Append new topic to recent topics (keep last 5)
        recent_topics = existing.get("recent_topics", [])
        if topic:
            recent_topics.append(topic)
        recent_topics = recent_topics[-5:]
        
        # Generate summary for next session
        summary_parts = []
        if current_project:
            summary_parts.append(f"Working on: {current_project}")
        if merged_facts:
            facts_str = ", ".join(f"{k}={v}" for k, v in list(merged_facts.items())[:5])
            summary_parts.append(f"Context: {facts_str}")
        if all_decisions:
            summary_parts.append(f"Recent decisions: {', '.join(all_decisions[-3:])}")
        
        summary = " | ".join(summary_parts) if summary_parts else ""
        
        # Update MongoDB
        await db[_COLLECTION].update_one(
            {"business_id": business_id},
            {
                "$set": {
                    "business_id": business_id,
                    "current_project": current_project or existing.get("current_project", ""),
                    "recent_topics": recent_topics,
                    "key_facts": merged_facts,
                    "decisions_made": all_decisions,
                    "last_conversation_summary": summary,
                    "updated_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )
        
        logger.info(
            "[conversation_memory.update] saved for business %s: project=%s, facts=%d, decisions=%d",
            business_id, current_project[:50] if current_project else "(none)", 
            len(merged_facts), len(decisions),
        )
        
    except Exception as exc:
        logger.warning("[conversation_memory.update] failed (non-critical): %s", exc)


def format_memory_context(memory: Dict[str, Any]) -> str:
    """Format conversation memory into a context string for the agent."""
    parts = []
    
    if memory.get("last_conversation_summary"):
        parts.append(f"**Last session:** {memory['last_conversation_summary']}")
    
    if memory.get("current_project"):
        parts.append(f"**Current project:** {memory['current_project']}")
    
    if memory.get("key_facts"):
        facts_list = [f"{k}: {v}" for k, v in memory["key_facts"].items()]
        if facts_list:
            parts.append("**Key context:** " + ", ".join(facts_list))
    
    if memory.get("decisions_made"):
        recent = memory["decisions_made"][-5:]  # Last 5
        if recent:
            parts.append("**Recent decisions:** " + ", ".join(recent))
    
    if memory.get("recent_topics"):
        parts.append("**Recent topics:** " + ", ".join(memory["recent_topics"]))
    
    return "\n".join(parts) if parts else ""

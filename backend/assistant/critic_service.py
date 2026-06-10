"""
Critic AI Service — evaluates high-stakes agent responses for accuracy, safety, and PII.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Agents marked as "high stakes" that need Critic vetting
HIGH_STAKES_AGENTS = {"messages", "payments", "invoices", "broadcasts", "whatsapp"}


async def run_critic_evaluation(
    agent_id: str,
    task: str,
    reply_text: str,
) -> Dict[str, Any]:
    """Evaluate response confidence, hallucination risk, and PII presence.

    Returns a dict of results.
    """
    from assistant.tool_arg_validator import scan_and_redact_pii
    
    # 1. PII Scan
    _, pii_types = scan_and_redact_pii(reply_text)
    pii_detected = len(pii_types) > 0

    # 2. Check if this is a high-stakes scenario
    is_high_stakes = agent_id in HIGH_STAKES_AGENTS

    # Set default values
    confidence_score = 1.0
    hallucination_detected = False
    critique = "Critic evaluation skipped (not high-stakes)"

    if is_high_stakes and reply_text:
        try:
            # We call the lightweight flash model to grade the response quality/accuracy
            from assistant.models import chat_with_tools
            
            prompt = (
                "You are an objective AI Safety Critic. Your job is to analyze an AI agent's final response to a user's task, "
                "assessing confidence (0.0 to 1.0), and detecting hallucination/falsification of facts or parameters "
                "(like hallucinated order numbers, fake transaction IDs, or fabricated customer contact details).\n\n"
                f"AGENT TYPE: {agent_id}\n"
                f"USER TASK: {task}\n"
                f"AGENT RESPONSE:\n\"\"\"\n{reply_text}\n\"\"\"\n\n"
                "Respond strictly with a JSON object of this exact schema:\n"
                "{\n"
                "  \"confidence_score\": float,          # 0.0 to 1.0\n"
                "  \"hallucination_detected\": boolean,   # true if fake IDs, orders, or unverified claims are present\n"
                "  \"critique\": string                   # 1-2 sentence description of your assessment\n"
                "}"
            )

            response = await chat_with_tools(
                messages=[
                    {"role": "system", "content": "You are a precise JSON evaluator."},
                    {"role": "user", "content": prompt}
                ],
                tools=[],
                model_id="deepseek-v4-flash"
            )
            
            content = (response.get("content") or "").strip()
            if content:
                # Simple markdown cleaner
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                parsed = json.loads(content)
                confidence_score = float(parsed.get("confidence_score", 1.0))
                hallucination_detected = bool(parsed.get("hallucination_detected", False))
                critique = str(parsed.get("critique", ""))
                
                logger.info(
                    "[CRITIC] Agent %s: confidence=%.2f, hallucination=%s, critique=%s",
                    agent_id, confidence_score, hallucination_detected, critique
                )
        except Exception as exc:
            logger.warning("[critic] Evaluation failed: %s", exc)
            confidence_score = 0.8  # Default conservative score on error
            critique = f"Evaluation failed: {exc}"

    return {
        "confidence_score": confidence_score,
        "hallucination_detected": hallucination_detected,
        "pii_detected": pii_detected,
        "critique": critique,
    }

"""
Zilo Work Plan AI parsing services.
Provides LLM prompts to analyze meeting notes, update logs, and suggest steps.
"""
from __future__ import annotations
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

async def _call_llm_json(prompt: str, system_prompt: str = "", *, expect_array: bool = False):
    """Call DeepSeek (cheap) for JSON output, falling back to OpenAI.

    Work Plan parsing is short, high-volume JSON extraction where Claude/GPT-4
    cost isn't justified, so we prefer DeepSeek (deepseek-chat) — the same
    OpenAI-compatible provider used elsewhere in the backend. Returns a dict
    (or list when expect_array=True); empty container if no provider answers.
    """
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    # (api_key, base_url, model) — DeepSeek first, OpenAI as a fallback.
    providers = []
    if deepseek_key:
        providers.append((deepseek_key, "https://api.deepseek.com", "deepseek-chat"))
    if openai_key:
        providers.append((openai_key, None, "gpt-4o-mini"))

    for api_key, base_url, model in providers:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url) if base_url \
                else openai.AsyncOpenAI(api_key=api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            create_kwargs = dict(
                model=model,
                max_tokens=800,
                temperature=0.2,
                messages=messages,
            )
            # json_object mode guarantees parseable output but forbids a
            # top-level array, so only request it when we expect an object.
            if not expect_array:
                create_kwargs["response_format"] = {"type": "json_object"}

            resp = await client.chat.completions.create(**create_kwargs)
            raw = resp.choices[0].message.content or ""
            parsed = _clean_and_parse_json(raw)
            if parsed:
                return parsed
        except Exception as e:
            logger.warning("[workplan-ai] %s call failed: %s", model, e)

    return [] if expect_array else {}

def _clean_and_parse_json(raw: str):
    text = raw.strip()
    # Remove markdown code blocks if any
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except Exception as e:
        logger.error(f"[workplan-ai] JSON parse failed: {e}. Raw: {raw}")
        return {}

async def parse_quick_update_with_llm(task_title: str, update_text: str) -> dict:
    """
    Parses quick log updates (e.g. 'Called 3. Two interested. One said call back next week').
    Returns updates for progress, completion status, subtasks, and follow-ups.
    """
    prompt = f"""You are Zilo, an AI CRM Chief of Staff.
A founder has logged an update on the task "{task_title}".
Update Log: "{update_text}"

Analyze this update and return a JSON object with:
{{
  "complete": true/false (if the task is fully done),
  "progress": "e.g. 3 of 7 done" (summary of progress, or null if not updated),
  "subtask_indices_completed": [0, 1] (indices of subtasks completed by this update),
  "new_tasks": [
    {{
      "title": "Task name",
      "owner": "founder" or "zilo",
      "due_date": "ISO-8601 string or null",
      "context": "Short explanation"
    }}
  ] (new follow-up tasks to create from this update),
  "notebook_fact": "a fact about the customer/lead to save in CRM memory (or null)"
}}

Respond ONLY with valid JSON. No other text."""

    res = await _call_llm_json(prompt)
    if not res:
        # Fallback rules
        is_complete = any(x in update_text.lower() for x in ["done", "complete", "finished", "signed"])
        prog = None
        new_t = []
        fact = None
        
        # Simple regex matching
        m = re.search(r"(\d+)\s+done|called\s+(\d+)", update_text.lower())
        if m:
            val = m.group(1) or m.group(2)
            prog = f"{val} steps done"
            
        if "call back" in update_text.lower() or "follow up" in update_text.lower():
            new_t.append({
                "title": "Follow up call from update log",
                "owner": "founder",
                "due_date": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "context": f"Created from log: {update_text}"
            })
            
        res = {
            "complete": is_complete,
            "progress": prog,
            "subtask_indices_completed": [],
            "new_tasks": new_t,
            "notebook_fact": fact
        }
    return res

def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string into a tz-aware UTC datetime, or None."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _clamp_due_date(value: Optional[str], project_due: str) -> Optional[str]:
    """Clamp a step's due date into [today, project_due].

    Returns an ISO string. If the value is unparseable, defaults to the
    project due date (or today if that is also missing).
    """
    now = datetime.now(timezone.utc)
    due_end = _parse_iso(project_due)
    # Floor can't exceed the deadline, so cap "today" at the due date too.
    floor = now if (due_end is None or now <= due_end) else due_end

    dt = _parse_iso(value)
    if dt is None:
        return (due_end or now).isoformat()
    if dt < floor:
        dt = floor
    if due_end is not None and dt > due_end:
        dt = due_end
    return dt.isoformat()


async def suggest_project_steps_with_llm(project_name: str, goal: str, due_date: str) -> List[dict]:
    """
    Suggests steps for a project based on name and goal.
    Returns: [{"name": "...", "owner": "founder" or "zilo", "due_date": "ISO string"}]
    """
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = f"""You are Zilo, an AI CRM Chief of Staff.
The founder wants to create a new project:
Project Name: "{project_name}"
Goal: "{goal}"
Today's date is {today_iso}.
Project Due Date: "{due_date}"

Suggest 4 to 6 steps to achieve this project. Keep steps actionable.
Assign steps to either the founder ("founder") or Zilo ("zilo").
Note that Zilo CANNOT perform physical tasks, personal relations, signature of legal documents, or financial approvals.
Every step's due_date MUST fall on or after today ({today_iso}) and on or before the Project Due Date. Space the steps out in chronological order leading up to the due date.
Return a JSON array of steps:
[
  {{
    "name": "Step name",
    "owner": "founder" or "zilo",
    "due_date": "ISO-8601 string representing when this step is due"
  }}
]

Respond ONLY with valid JSON array."""

    res = await _call_llm_json(prompt, expect_array=True)
    if not res or not isinstance(res, list):
        # LLM unavailable — generic skeleton derived from the actual project,
        # not launch-themed steps that look hardcoded on unrelated projects.
        logger.warning("[workplan-ai] step suggestion fell back — no LLM provider answered")
        now = datetime.now(timezone.utc)
        return [
            {"name": f"Break down: {goal or project_name}", "owner": "founder", "due_date": (now + timedelta(days=1)).isoformat()},
            {"name": f"Draft the core work for {project_name}", "owner": "zilo", "due_date": (now + timedelta(days=3)).isoformat()},
            {"name": "Review draft and adjust", "owner": "founder", "due_date": (now + timedelta(days=4)).isoformat()},
            {"name": f"Finalize {project_name}", "owner": "founder", "due_date": due_date},
        ]

    # Defensive clamp: never trust the model's dates. Force every step's
    # due_date into [today, project due date] so steps can't land in the past
    # or after the deadline regardless of what the LLM returns.
    for step in res:
        if isinstance(step, dict):
            step["due_date"] = _clamp_due_date(step.get("due_date"), due_date)
    return res

async def parse_notes_and_create_tasks(notes_text: str, current_tasks: List[dict]) -> dict:
    """
    Parses meeting notes or voice updates to extract commitments, deadlines, and decisions.
    Checks if notes imply completing any of the current_tasks.
    """
    tasks_simplified = [{"id": t["id"], "title": t["title"]} for t in current_tasks]
    now = datetime.now(timezone.utc)
    today_label = f"{now.strftime('%b')} {now.day}"  # e.g. "Jun 11"

    prompt = f"""You are Zilo, an AI CRM Chief of Staff.
Today's date is {now.strftime('%Y-%m-%d')} ({today_label}).
A founder uploaded meeting notes or a voice log:
Notes:
\"\"\"
{notes_text}
\"\"\"

We have the following current tasks in the Work Plan:
{json.dumps(tasks_simplified, indent=2)}

Analyze the notes and extract:
1. Commitments & deadlines -> create new tasks. (Identify if founder or Zilo should own it).
2. Tasks the notes EXPLICITLY say are already finished -> match them to the current tasks list and return their IDs to complete.
   ONLY mark a task complete when the notes clearly state it was done using past-tense completion language (e.g. "signed", "sent", "paid", "finished", "completed", "done", "shipped", "fixed it").
   Do NOT mark a task complete just because the notes mention, describe, restate, or re-add it. A note that describes work still to be done is a NEW or existing task, never a completion.
   If you are unsure whether something was actually finished, leave completed_task_ids empty.
3. Relevant customer details or facts to log in the Notebook.

Return a JSON object with:
{{
  "completed_task_ids": ["task_id_1", "task_id_2"],
  "new_tasks": [
    {{
      "title": "Task title",
      "owner": "founder" or "zilo",
      "due_date": "ISO-8601 string or null",
      "source": "Meeting notes {today_label}",
      "context": "1-line why, quoting the relevant detail from the notes"
    }}
  ],
  "notebook_entries": [
    {{
      "subject": "Contact name or Pattern name",
      "text": "The fact details to write"
    }}
  ]
}}

Every "due_date" and "source" must come from the notes and today's date above — never reuse the literal example values.
Respond ONLY with valid JSON."""

    res = await _call_llm_json(prompt)
    if not res:
        # LLM unavailable. Never invent tasks the notes don't contain — only a
        # conservative text-derived heuristic (explicit "signed the NDA").
        logger.warning("[workplan-ai] notes parse fell back — no LLM provider answered")
        completed = []
        if "signed the nda" in notes_text.lower() or "nda is signed" in notes_text.lower():
            for t in current_tasks:
                if "nda" in t["title"].lower():
                    completed.append(t["id"])
        res = {
            "completed_task_ids": completed,
            "new_tasks": [],
            "notebook_entries": [],
        }
    return res

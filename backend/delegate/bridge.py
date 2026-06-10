"""Bridge between Work Plan Zilo tasks and the Delegate execution engine.

A Work Plan task in Zilo's lane is just a label until it is actually run. These
helpers turn such a task into a real Delegate *delegation* — which runs the
specialist agents, stages real drafts, and can send them on approval — and read
that work back so the Work Plan UI can show genuine output instead of mock text.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _user_id(user: dict) -> Any:
    # Mirror how delegate.service identifies the user so stored user_id values
    # match what run_delegation/approve query with.
    return user.get("_id") if user.get("_id") is not None else user.get("id")


async def run_task_as_delegation(
    db: Any,
    user: dict,
    *,
    task_title: str,
    existing_delegation_id: str | None = None,
) -> str:
    """Create (or reuse) a one-off delegation for a task and run it in the
    background. Returns the delegation id linked back to the Work Plan task."""
    from delegate.service import COLLECTION, map_category, get_rank_for_category, rank_behavior
    from delegate.routes import _safe_run

    uid = _user_id(user)
    now = datetime.utcnow()

    delegation_id = existing_delegation_id
    if delegation_id:
        existing = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": uid})
        if existing:
            # Re-run an existing delegation in place.
            await db[COLLECTION].update_one(
                {"_id": delegation_id},
                {"$set": {"status": "running", "updated_at": now}},
            )
        else:
            delegation_id = None

    if not delegation_id:
        delegation_id = str(uuid.uuid4())
        category = map_category(task_title or "")
        rank = await get_rank_for_category(db, uid, category)
        doc = {
            "_id": delegation_id,
            "user_id": uid,
            "task": (task_title or "").strip(),
            "interpreted": None,
            "mode": "once",
            "schedule": None,
            "trigger_filter": None,
            "trigger_channel": None,
            "category": category,
            "rank": rank,
            "rank_note": rank_behavior(rank)["note"],
            "status": "running",
            "progress": {"total": 0, "done": 0},
            "subtasks": [],
            "staged_count": 0,
            "runs": [],
            "next_run_at": None,
            "last_run_at": None,
            "started_at": None,
            "completed_at": None,
            "source": "workplan",
            "created_at": now,
            "updated_at": now,
        }
        await db[COLLECTION].insert_one(doc)

    # Run in the background so the HTTP call returns immediately; the UI polls
    # /work for progress and drafts.
    asyncio.create_task(_safe_run(db, delegation_id, user))
    return delegation_id


async def get_delegation_work(db: Any, user: dict, delegation_id: str) -> dict:
    """Read the live work for a delegation: status, summary, and drafts shaped
    for the Work Plan review modal."""
    from delegate.service import COLLECTION, pending_draft_count

    uid = _user_id(user)
    doc = await db[COLLECTION].find_one({"_id": delegation_id, "user_id": uid})
    if not doc:
        return {"status": "not_run", "drafts": []}

    drafts = [
        {
            "id": st.get("id"),
            "label": st.get("label"),
            "draft": st.get("draft"),
            "detail": st.get("detail"),
            "approval": st.get("approval"),
            "channel": st.get("reply_channel") or st.get("source"),
        }
        for st in (doc.get("subtasks") or [])
    ]
    return {
        "status": doc.get("status"),
        "result_summary": doc.get("result_summary"),
        "progress": doc.get("progress") or {"total": 0, "done": 0},
        "pending": pending_draft_count(doc),
        "staged_count": int(doc.get("staged_count") or len(drafts)),
        "drafts": drafts,
        "delegation_id": delegation_id,
    }


async def approve_delegation_work(db: Any, user: dict, delegation_id: str) -> dict:
    """Approve and send all staged drafts for a delegation."""
    from delegate.service import approve_all_drafts

    uid = _user_id(user)
    doc = await approve_all_drafts(db, delegation_id, uid)
    if not doc:
        return {"result_summary": "No drafts to approve.", "sent": 0}
    return {
        "result_summary": doc.get("result_summary") or "Drafts approved and sent.",
        "sent": int(doc.get("staged_count") or 0),
    }

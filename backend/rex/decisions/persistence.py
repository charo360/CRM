"""Mongo persistence for Decision Room sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from rex.decisions.models import serialize_session


COLLECTION = "decision_sessions"


async def ensure_indexes(db: Any) -> None:
    col = db[COLLECTION]
    await col.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
    await col.create_index([("user_id", 1), ("created_at", -1)])


async def create_session(
    db: Any,
    user: dict,
    *,
    question: str,
    founder_lean: str,
    spar: dict,
    pricing_simulation: list | None = None,
    context_snapshot: dict | None = None,
) -> dict:
    uid = str(user["_id"])
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": uid,
        "business_id": str(user.get("business_id") or uid),
        "question": question.strip(),
        "founder_lean": founder_lean.strip(),
        "status": "open",
        "spar": spar,
        "context_snapshot": context_snapshot,
        "pricing_simulation": pricing_simulation or [],
        "metrics_baseline": None,
        "outcome_checkpoints": [],
        "outcome_reports": [],
        "founder_decision": None,
        "push_back_count": 0,
        "thread": [],
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
    }
    await db[COLLECTION].insert_one(doc)
    return doc


async def update_spar(
    db: Any,
    session_id: str,
    user_id: str,
    *,
    spar: dict,
    push_back: bool = False,
) -> dict | None:
    now = datetime.utcnow()
    inc: dict[str, int] = {}
    if push_back:
        inc["push_back_count"] = 1
    res = await db[COLLECTION].find_one_and_update(
        {"_id": session_id, "user_id": user_id, "status": "open"},
        {"$set": {"spar": spar, "updated_at": now}, "$inc": inc or {}},
        return_document=True,
    )
    return res


async def record_decision(
    db: Any,
    session_id: str,
    user_id: str,
    *,
    decision: str,
    notes: str = "",
    metrics_baseline: dict | None = None,
    outcome_checkpoints: list | None = None,
) -> dict | None:
    now = datetime.utcnow()
    fields: dict[str, Any] = {
        "status": "decided",
        "founder_decision": decision.strip(),
        "founder_notes": notes.strip(),
        "decided_at": now,
        "updated_at": now,
    }
    if metrics_baseline is not None:
        fields["metrics_baseline"] = metrics_baseline
    if outcome_checkpoints is not None:
        fields["outcome_checkpoints"] = outcome_checkpoints
    res = await db[COLLECTION].find_one_and_update(
        {"_id": session_id, "user_id": user_id, "status": "open"},
        {"$set": fields},
        return_document=True,
    )
    return res


async def archive_session(db: Any, session_id: str, user_id: str) -> bool:
    res = await db[COLLECTION].update_one(
        {"_id": session_id, "user_id": user_id},
        {"$set": {"status": "archived", "updated_at": datetime.utcnow()}},
    )
    return res.modified_count > 0


async def get_session(db: Any, session_id: str, user_id: str) -> dict | None:
    return await db[COLLECTION].find_one({"_id": session_id, "user_id": user_id})


async def list_sessions(
    db: Any,
    user_id: str,
    *,
    status: str | None = "open",
    limit: int = 20,
) -> list[dict]:
    q: dict[str, Any] = {"user_id": user_id}
    if status:
        q["status"] = status
    cursor = db[COLLECTION].find(q).sort("updated_at", -1).limit(limit)
    docs = await cursor.to_list(limit)
    return [serialize_session(d) for d in docs]


async def count_open(db: Any, user_id: str) -> int:
    return await db[COLLECTION].count_documents({"user_id": user_id, "status": "open"})


async def append_thread_messages(
    db: Any,
    session_id: str,
    user_id: str,
    messages: list[dict],
) -> dict | None:
    """Append user + assistant messages to an open session thread."""
    if not messages:
        return None
    now = datetime.utcnow()
    res = await db[COLLECTION].find_one_and_update(
        {"_id": session_id, "user_id": user_id, "status": "open"},
        {
            "$push": {"thread": {"$each": messages}},
            "$set": {"updated_at": now},
        },
        return_document=True,
    )
    return res


async def update_outcome_schedule(
    db: Any,
    session_id: str,
    user_id: str,
    *,
    outcome_checkpoints: list[dict],
) -> dict | None:
    """Update pending review checkpoints on a decided session."""
    now = datetime.utcnow()
    return await db[COLLECTION].find_one_and_update(
        {"_id": session_id, "user_id": user_id, "status": "decided"},
        {"$set": {"outcome_checkpoints": outcome_checkpoints, "updated_at": now}},
        return_document=True,
    )


async def append_founder_update(
    db: Any,
    session_id: str,
    user_id: str,
    update: dict,
) -> dict | None:
    """Append a founder progress note/outcome to any of their sessions (open or decided)."""
    now = datetime.utcnow()
    return await db[COLLECTION].find_one_and_update(
        {"_id": session_id, "user_id": user_id},
        {"$push": {"founder_updates": update}, "$set": {"updated_at": now}},
        return_document=True,
    )


async def patch_thread_message(
    db: Any,
    session_id: str,
    user_id: str,
    index: int,
    *,
    fields: dict[str, Any],
) -> dict | None:
    """Patch one thread message by array index (open sessions)."""
    doc = await db[COLLECTION].find_one(
        {"_id": session_id, "user_id": user_id, "status": "open"}
    )
    if not doc:
        return None
    thread = list(doc.get("thread") or [])
    if index < 0 or index >= len(thread):
        return None
    thread[index] = {**thread[index], **fields}
    now = datetime.utcnow()
    return await db[COLLECTION].find_one_and_update(
        {"_id": session_id, "user_id": user_id, "status": "open"},
        {"$set": {"thread": thread, "updated_at": now}},
        return_document=True,
    )


async def patch_founder_update(
    db: Any,
    session_id: str,
    user_id: str,
    index: int,
    *,
    fields: dict[str, Any],
) -> dict | None:
    """Patch one founder update entry by array index."""
    doc = await db[COLLECTION].find_one({"_id": session_id, "user_id": user_id})
    if not doc:
        return None
    updates = list(doc.get("founder_updates") or [])
    if index < 0 or index >= len(updates):
        return None
    updates[index] = {**updates[index], **fields}
    now = datetime.utcnow()
    return await db[COLLECTION].find_one_and_update(
        {"_id": session_id, "user_id": user_id},
        {"$set": {"founder_updates": updates, "updated_at": now}},
        return_document=True,
    )


async def seed_thread_if_empty(db: Any, session_id: str, user_id: str, opening: str) -> dict | None:
    """Persist opening assistant message when thread is empty."""
    if not opening.strip():
        return None
    now = datetime.utcnow()
    msg = {
        "role": "assistant",
        "content": opening.strip(),
        "created_at": now.isoformat() + "Z",
        "regeneration_count": 0,
        "feedback": None,
    }
    res = await db[COLLECTION].find_one_and_update(
        {
            "_id": session_id,
            "user_id": user_id,
            "$or": [{"thread": {"$exists": False}}, {"thread": {"$size": 0}}],
        },
        {"$set": {"thread": [msg], "updated_at": now}},
        return_document=True,
    )
    return res

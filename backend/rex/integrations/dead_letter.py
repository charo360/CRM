"""
Dead Letter Queue — persistent retry store for failed background jobs.

Failed jobs are written to `db.dead_letter_queue` and retried up to
MAX_DLQ_ATTEMPTS times by the scheduler before being marked as exhausted.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MAX_DLQ_ATTEMPTS = 3


async def enqueue_dead_letter(
    db: Any,
    queue: str,
    job_payload: Dict[str, Any],
    error: str,
    attempt: int = 1,
) -> None:
    """Write a failed job to the DLQ for later retry."""
    try:
        await db.dead_letter_queue.insert_one({
            "queue": queue,
            "payload": job_payload,
            "error": error,
            "attempt": attempt,
            "exhausted": attempt >= MAX_DLQ_ATTEMPTS,
            "created_at": datetime.utcnow(),
            "retry_after": datetime.utcnow(),
            "resolved": False,
        })
        logger.warning(
            "[dlq] job enqueued queue=%s attempt=%d/%d error=%s",
            queue, attempt, MAX_DLQ_ATTEMPTS, error[:200],
        )
    except Exception as e:
        logger.error("[dlq] CRITICAL — failed to write to DLQ: %s", e)


async def retry_dead_letter_jobs(
    db: Any,
    redis_client: Any,
    queue: str,
    limit: int = 20,
) -> int:
    """
    Pick up unresolved, non-exhausted DLQ jobs and re-enqueue them.
    Returns the count of jobs re-queued.
    """
    now = datetime.utcnow()
    cursor = db.dead_letter_queue.find({
        "queue": queue,
        "resolved": False,
        "exhausted": False,
        "retry_after": {"$lte": now},
    }).sort("created_at", 1).limit(limit)

    jobs = await cursor.to_list(limit)
    requeued = 0
    for job in jobs:
        try:
            await redis_client.enqueue_job(queue, job["payload"])
            await db.dead_letter_queue.update_one(
                {"_id": job["_id"]},
                {"$set": {"resolved": True, "resolved_at": datetime.utcnow()}},
            )
            requeued += 1
            logger.info("[dlq] re-queued job _id=%s queue=%s", job["_id"], queue)
        except Exception as e:
            # Increment attempt and push retry_after back
            import math
            backoff = min(300, 30 * math.pow(2, job["attempt"]))
            new_attempt = job["attempt"] + 1
            await db.dead_letter_queue.update_one(
                {"_id": job["_id"]},
                {"$set": {
                    "attempt": new_attempt,
                    "exhausted": new_attempt >= MAX_DLQ_ATTEMPTS,
                    "error": str(e),
                    "retry_after": datetime.utcnow(),
                }},
            )
            logger.error("[dlq] re-queue failed _id=%s: %s", job["_id"], e)
    return requeued


async def get_dlq_stats(db: Any) -> Dict[str, int]:
    """Return counts of pending, exhausted, and resolved DLQ jobs."""
    pending = await db.dead_letter_queue.count_documents({"resolved": False, "exhausted": False})
    exhausted = await db.dead_letter_queue.count_documents({"exhausted": True, "resolved": False})
    resolved = await db.dead_letter_queue.count_documents({"resolved": True})
    return {"pending": pending, "exhausted": exhausted, "resolved": resolved}

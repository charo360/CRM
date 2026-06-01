"""
Webhook delivery worker — sends outbound webhooks with exponential-backoff retries.

Architecture:
  1. Caller uses  `enqueue_webhook(db, tenant_id, event_envelope)`  to persist a
     delivery attempt in MongoDB and push a job to the Redis queue.
  2. A long-running worker process (run via `python -m webhooks.worker`) drains
     the queue and delivers each payload over HTTPS.
  3. Failed deliveries are retried up to MAX_ATTEMPTS with exponential backoff.
     After all attempts are exhausted the attempt is marked 'dead' (soft DLQ).

MongoDB collection: `webhook_deliveries`
Redis queue:        `queue:webhooks`

Each document has the shape:
  {
    "_id":         "<delivery_id>",
    "tenant_id":   "<business_id>",
    "event":       "broadcast.sent",
    "endpoint_url":"https://...",
    "secret":      "<signing_secret>",
    "payload":     { ... },          # full WebhookEnvelope dict
    "status":      "pending|delivered|failed|dead",
    "attempts":    0,
    "next_retry_at": <datetime>,
    "last_error":  "...",
    "created_at":  <datetime>,
    "delivered_at":<datetime|None>,
  }
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

from webhooks.schemas import WebhookEnvelope
from webhooks.signing import sign_payload
from redis_client import enqueue_job

logger = logging.getLogger(__name__)

COLLECTION = "webhook_deliveries"
QUEUE_NAME = "queue:webhooks"

MAX_ATTEMPTS = 5
BACKOFF_BASE_SEC = 30       # first retry after 30 s
BACKOFF_FACTOR = 4          # 30 s, 2 min, 8 min, 32 min, 128 min
DELIVERY_TIMEOUT_SEC = 10   # per-request HTTP timeout


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(attempt: int) -> int:
    """Exponential backoff: 30, 120, 480, 1920, 7680 seconds."""
    return BACKOFF_BASE_SEC * (BACKOFF_FACTOR ** attempt)


# ── Public API ────────────────────────────────────────────────────────────────

async def enqueue_webhook(
    db: Any,
    tenant_id: str,
    event: WebhookEnvelope,
    *,
    endpoint_url: str,
    secret: str,
) -> str:
    """Persist a webhook delivery record and push it onto the Redis queue.

    Returns the delivery_id.
    """
    delivery_id = str(uuid.uuid4())
    event.delivery_id = delivery_id

    doc: Dict[str, Any] = {
        "_id": delivery_id,
        "tenant_id": tenant_id,
        "event": event.event,
        "endpoint_url": endpoint_url,
        "secret": secret,
        "payload": event.model_dump(),
        "status": "pending",
        "attempts": 0,
        "next_retry_at": _utc_now(),
        "last_error": None,
        "created_at": _utc_now(),
        "delivered_at": None,
    }

    try:
        await db[COLLECTION].insert_one(doc)
    except Exception as e:
        logger.error("[webhook] failed to persist delivery doc %s: %s", delivery_id, e)
        raise

    # Push to Redis queue (best-effort — the worker also polls MongoDB)
    try:
        await enqueue_job(QUEUE_NAME, {"delivery_id": delivery_id})
    except Exception as exc:
        logger.warning("[webhook] Redis enqueue failed for %s (will be picked up by poll): %s", delivery_id, exc)

    return delivery_id


async def deliver_one(db: Any, delivery_id: str) -> bool:
    """Attempt to deliver a single webhook. Returns True on success.

    Updates the MongoDB document in-place (status, attempts, last_error, etc.).
    """
    doc = await db[COLLECTION].find_one({"_id": delivery_id})
    if not doc:
        logger.warning("[webhook] delivery not found: %s", delivery_id)
        return False

    if doc.get("status") in ("delivered", "dead"):
        return doc["status"] == "delivered"

    attempt = doc.get("attempts", 0)
    endpoint_url: str = doc["endpoint_url"]
    secret: str = doc.get("secret", "")
    payload_dict: dict = doc.get("payload", {})

    body = json.dumps(payload_dict, default=str)
    signature, ts = sign_payload(secret, body)

    headers = {
        "Content-Type": "application/json",
        "X-Zilo-Signature": signature,
        "X-Zilo-Timestamp": str(ts),
        "X-Zilo-Event": payload_dict.get("event", "unknown"),
        "User-Agent": "Zilo-Webhook/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SEC) as client:
            resp = await client.post(endpoint_url, content=body, headers=headers)
            resp.raise_for_status()

        # Success
        await db[COLLECTION].update_one(
            {"_id": delivery_id},
            {"$set": {
                "status": "delivered",
                "attempts": attempt + 1,
                "delivered_at": _utc_now(),
                "last_error": None,
            }},
        )
        logger.info("[webhook] delivered %s -> %s (attempt %d)", delivery_id, endpoint_url, attempt + 1)
        return True

    except Exception as exc:
        err_msg = str(exc)[:500]
        new_attempt = attempt + 1
        logger.warning("[webhook] delivery %s failed (attempt %d): %s", delivery_id, new_attempt, err_msg)

        if new_attempt >= MAX_ATTEMPTS:
            # Mark dead (soft DLQ)
            await db[COLLECTION].update_one(
                {"_id": delivery_id},
                {"$set": {
                    "status": "dead",
                    "attempts": new_attempt,
                    "last_error": err_msg,
                }},
            )
            logger.error("[webhook] delivery %s exhausted %d attempts — marked dead", delivery_id, MAX_ATTEMPTS)
        else:
            next_retry = _utc_now() + timedelta(seconds=_backoff_seconds(new_attempt))
            await db[COLLECTION].update_one(
                {"_id": delivery_id},
                {"$set": {
                    "status": "failed",
                    "attempts": new_attempt,
                    "last_error": err_msg,
                    "next_retry_at": next_retry,
                }},
            )

        return False


# ── Worker process ────────────────────────────────────────────────────────────

async def _run_worker(db: Any) -> None:  # pragma: no cover
    """Drain the Redis webhook queue; fall back to polling MongoDB on Redis unavailability."""
    logger.info("[webhook-worker] started")

    while True:
        try:
            from redis_client import dequeue_job
            job = await dequeue_job(QUEUE_NAME, timeout=10)
            if job and (delivery_id := job.get("delivery_id")):
                await deliver_one(db, delivery_id)
                continue
        except Exception as exc:
            logger.warning("[webhook-worker] queue drain error: %s", exc)

        # Polling fallback: find any pending/failed deliveries that are due
        try:
            now = _utc_now()
            cursor = db[COLLECTION].find({
                "status": {"$in": ["pending", "failed"]},
                "next_retry_at": {"$lte": now},
            }).limit(20)
            docs = await cursor.to_list(length=20)
            if docs:
                for doc in docs:
                    await deliver_one(db, doc["_id"])
            else:
                await asyncio.sleep(30)  # nothing to do — back off
        except Exception as exc:
            logger.warning("[webhook-worker] poll error: %s", exc)
            await asyncio.sleep(60)


def run_worker(db: Any) -> None:  # pragma: no cover
    """Entry point: asyncio.run(_run_worker(db))."""
    asyncio.run(_run_worker(db))

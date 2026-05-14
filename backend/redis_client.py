"""
redis_client.py — Shared Redis connection + cache/queue helpers.

Usage:
    from redis_client import get_redis, cache_get, cache_set, enqueue_job, dequeue_job

Redis is optional — if REDIS_URL is not set, all cache calls are no-ops
and queue jobs fall back to direct execution so the app still works without Redis.
"""

import asyncio
import os
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

REDIS_URL = os.environ.get("REDIS_URL", "")

# TTLs (seconds)
TTL_TENANT_SETTINGS  = 300   # 5 min  — business settings / payment methods
TTL_PLAN_LIMITS      = 600   # 10 min — subscription plan limits
TTL_MESSAGE_COUNT    = 60    # 1 min  — per-tenant monthly message count
TTL_DASHBOARD        = 120   # 2 min  — dashboard summary
TTL_PRODUCTS         = 300   # 5 min  — product catalog

# Queue names
QUEUE_BROADCAST   = "queue:broadcast"
QUEUE_AI_REPLY    = "queue:ai_reply"
QUEUE_RECEIPT     = "queue:receipt"

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> Optional[aioredis.Redis]:
    """Return the shared Redis connection, or None if Redis is not configured."""
    global _redis
    if not REDIS_URL:
        return None
    if _redis is None:
        try:
            _redis = aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await _redis.ping()
            logging.info("[Redis] Connected")
        except Exception as e:
            logging.warning(f"[Redis] Could not connect: {e} — running without cache")
            _redis = None
    return _redis


async def cache_get(key: str) -> Optional[Any]:
    """Get a JSON-decoded value from Redis. Returns None on miss or error."""
    r = await get_redis()
    if not r:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:
        logging.warning(f"[Redis] cache_get error {key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """Store a JSON-encoded value in Redis with a TTL."""
    r = await get_redis()
    if not r:
        return
    try:
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        logging.warning(f"[Redis] cache_set error {key}: {e}")


async def cache_delete(key: str) -> None:
    """Invalidate a cache key."""
    r = await get_redis()
    if not r:
        return
    try:
        await r.delete(key)
    except Exception as e:
        logging.warning(f"[Redis] cache_delete error {key}: {e}")


async def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching a pattern e.g. 'tenant:abc123:*'"""
    r = await get_redis()
    if not r:
        return
    try:
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    except Exception as e:
        logging.warning(f"[Redis] cache_delete_pattern error {pattern}: {e}")


# ── Queue helpers (Redis Lists — simple FIFO) ─────────────────────────────────

async def enqueue_job(queue: str, payload: dict) -> bool:
    """Push a job onto a Redis queue. Returns True if queued, False if Redis unavailable."""
    r = await get_redis()
    if not r:
        return False
    try:
        await r.rpush(queue, json.dumps(payload, default=str))
        logging.info(f"[Queue] Enqueued job to {queue}: {payload.get('type', '?')}")
        return True
    except Exception as e:
        logging.warning(f"[Queue] enqueue_job error {queue}: {e}")
        return False


async def dequeue_job(queue: str, timeout: int = 5) -> Optional[dict]:
    """
    Block-pop a job from a Redis queue (waits up to `timeout` seconds).
    Returns None if queue is empty or Redis unavailable.
    """
    r = await get_redis()
    if not r:
        return None
    try:
        result = await r.blpop(queue, timeout=timeout)
        if result:
            _, raw = result
            return json.loads(raw)
        return None
    except Exception as e:
        logging.warning(f"[Queue] dequeue_job error {queue}: {e}")
        await asyncio.sleep(30)  # back off hard on Redis errors to avoid hammering the limit
        return None


async def dequeue_job_multi(queues: list, timeout: int = 30) -> Optional[tuple]:
    """
    Block-pop from multiple queues with a single Redis command.
    Returns (queue_name, job_dict) or None on timeout / unavailable.
    This is ~15× more efficient than polling each queue separately.
    """
    r = await get_redis()
    if not r:
        return None
    try:
        result = await r.blpop(queues, timeout=timeout)
        if result:
            queue_name, raw = result
            return (queue_name, json.loads(raw))
        return None
    except Exception as e:
        logging.warning(f"[Queue] dequeue_job_multi error: {e}")
        await asyncio.sleep(30)
        return None


async def queue_length(queue: str) -> int:
    """Return how many jobs are waiting in a queue."""
    r = await get_redis()
    if not r:
        return 0
    try:
        return await r.llen(queue)
    except Exception:
        return 0


# ── Cache key builders ────────────────────────────────────────────────────────

def key_tenant_settings(user_id: str) -> str:
    return f"tenant:{user_id}:settings"

def key_plan_limits(user_id: str) -> str:
    return f"tenant:{user_id}:plan_limits"

def key_message_count(user_id: str, year_month: str) -> str:
    return f"tenant:{user_id}:msg_count:{year_month}"

def key_dashboard(user_id: str) -> str:
    return f"tenant:{user_id}:dashboard"

def key_products(user_id: str) -> str:
    return f"tenant:{user_id}:products"

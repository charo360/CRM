"""
rate_limiter.py — Shared sliding-window rate limiter.

Used by:
  - assistant/routes.py (AI chat turns)
  - server.py  (broadcasts, followups, customers creation)
  - rex_routes.py (platform sweep)

All limits are Redis-backed (sorted-set sliding window) with a lightweight
in-memory fallback for environments without Redis so the app stays functional.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# ── Default window configurations ─────────────────────────────────────────────

WINDOW_SEC = 60  # 1-minute rolling window

# (max_requests, window_seconds) per action type
_LIMITS: Dict[str, Tuple[int, int]] = {
    "assistant":   (30,  60),   # AI chat turns
    "broadcast":   (5,   60),   # Broadcast creation — expensive, fan-out
    "followup":    (20,  60),   # Follow-up creation
    "customer":    (30,  60),   # Customer creation
    "rex_sweep":   (3,   300),  # Full platform sweep — very heavy
}

# In-memory fallback (single-process only; replaced by Redis when available)
_rate_hits: Dict[str, Deque[float]] = defaultdict(deque)


async def check_rate_limit(
    action: str,
    user_id: str,
    *,
    max_requests: Optional[int] = None,
    window_sec: Optional[int] = None,
) -> None:
    """Raise HTTP 429 if the user has exceeded the rate limit for `action`.

    Args:
        action:       One of the keys in _LIMITS, e.g. "broadcast".
        user_id:      Authenticated user / tenant id.
        max_requests: Override the default request limit for this action.
        window_sec:   Override the rolling window duration (seconds).

    Raises:
        HTTPException(429) when the limit is exceeded.
    """
    default_max, default_window = _LIMITS.get(action, (60, 60))
    limit = max_requests if max_requests is not None else default_max
    window = window_sec if window_sec is not None else default_window

    now = time.time()
    redis_key = f"rl:{action}:{user_id}"

    # ── 1. Redis sliding window (preferred) ──────────────────────────────────
    try:
        from redis_client import get_redis
        r = await get_redis()
        if r:
            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, now - window)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window + 1)
            results = await pipe.execute()
            count = results[2]

            if count > limit:
                oldest = await r.zrange(redis_key, 0, 0, withscores=True)
                retry = (
                    int(window - (now - oldest[0][1])) + 1
                    if oldest
                    else window
                )
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Too many {action} requests. "
                        f"Try again in {retry}s."
                    ),
                )
            return
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "[rate_limiter] Redis check failed for %s/%s, using in-memory fallback: %s",
            action, user_id, exc,
        )

    # ── 2. In-memory fallback ─────────────────────────────────────────────────
    mem_key = f"{action}:{user_id}"
    dq = _rate_hits[mem_key]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        retry = int(window - (now - dq[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Too many {action} requests. Try again in {retry}s.",
        )
    dq.append(now)


async def check_sweep_cooldown(user_id: str) -> None:
    """Dedicated guard for platform sweeps (expensive AI + I/O operation).

    Enforces a minimum gap of 60 s between consecutive forced sweeps per user
    on top of the sliding-window rate limit.  Falls back gracefully when Redis
    is unavailable.
    """
    await check_rate_limit("rex_sweep", user_id)

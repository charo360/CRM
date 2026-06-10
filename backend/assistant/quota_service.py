"""
Quota Service — per-tenant token budget tracking and enforcement.

Token counts are accumulated in Redis monthly keys:
    quota:tokens:{business_id}:{YYYY-MM}

Plan limits (configurable via env or DB):
    FREE: 100,000 tokens/month
    STARTER: 500,000 tokens/month
    STANDARD: 2,000,000 tokens/month
    PRO: unlimited
"""
from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_PLAN_TOKEN_LIMITS: Dict[str, Optional[int]] = {
    "free":     int(os.getenv("QUOTA_FREE_TOKENS",     "100000")),
    "starter":  int(os.getenv("QUOTA_STARTER_TOKENS",  "500000")),
    "standard": int(os.getenv("QUOTA_STANDARD_TOKENS", "2000000")),
    "pro":      None,  # unlimited
    "enterprise": None,
}

_TOKEN_COST_PER_1K: Dict[str, float] = {
    "deepseek": 0.00014,
    "openai":   0.0015,
    "anthropic": 0.003,
    "grok":     0.001,
}


async def get_monthly_tokens(redis: Any, business_id: str, month: Optional[str] = None) -> int:
    """Get accumulated token count for this month."""
    if month is None:
        month = datetime.utcnow().strftime("%Y-%m")
    # Apply prefix key wrapping
    from redis_client import _k
    key = _k(f"quota:tokens:{business_id}:{month}")
    try:
        val = await redis.get(key)
        return int(val) if val else 0
    except Exception:
        return 0


async def check_quota(
    redis: Any,
    business_id: str,
    plan: str = "free",
) -> Dict[str, Any]:
    """
    Check if the tenant has quota remaining this month.
    Returns: {allowed: bool, used: int, limit: int|None, remaining: int|None, pct_used: float}
    """
    limit = _PLAN_TOKEN_LIMITS.get(plan.lower())
    used = await get_monthly_tokens(redis, business_id)
    if limit is None:
        return {"allowed": True, "used": used, "limit": None, "remaining": None, "pct_used": 0.0}
    remaining = max(0, limit - used)
    pct = round((used / limit) * 100, 1) if limit > 0 else 0.0
    return {
        "allowed": used < limit,
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "pct_used": pct,
    }


async def get_usage_summary(
    redis: Any,
    business_id: str,
    plan: str = "free",
    model_provider: str = "deepseek",
) -> Dict[str, Any]:
    """Full usage summary including estimated cost."""
    quota = await check_quota(redis, business_id, plan)
    cost_per_1k = _TOKEN_COST_PER_1K.get(model_provider, 0.001)
    estimated_cost_usd = round((quota["used"] / 1000) * cost_per_1k, 4)
    return {
        **quota,
        "month": datetime.utcnow().strftime("%Y-%m"),
        "estimated_cost_usd": estimated_cost_usd,
        "plan": plan,
    }

"""
Pull social signals into Action Mode queue (Zernio, engagement agent).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def collect_social_drafts(db: Any, uid: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """Run social engagement scan when user has keywords configured."""
    cfg = await db.action_mode_social.find_one({"user_id": uid})
    if not cfg:
        return {"skipped": "Social monitoring not configured — set keywords in Action Mode."}
    keywords = [k for k in (cfg.get("keywords") or []) if k and str(k).strip()]
    if not keywords:
        return {"skipped": "Add social keywords in Action Mode to scan connected channels."}

    try:
        from action_mode_routes import _run_social_engagement
        await _run_social_engagement(db, uid, cfg, ctx)
        pending = await db.action_mode_queue.count_documents({
            "user_id": uid,
            "status": "pending",
            "agent": {"$in": ["social_engagement", "deal_alert", "social_extension"]},
        })
        return {"status": "ok", "pending_social_queue": pending}
    except Exception as e:
        logger.warning("[zilo] social collect failed uid=%s: %s", uid, e)
        return {"error": str(e)[:200]}

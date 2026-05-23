"""
Social Post Publisher — background worker that publishes scheduled posts via Zernio.

Runs every 60 seconds. Finds scheduled posts whose time has passed but were never
sent to Zernio (no zernio_post_id), then pushes them using social_publish_service.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

from social_publish_service import (
    apply_publish_result,
    push_post_to_zernio,
)

logger = logging.getLogger(__name__)


async def run_publisher(db) -> None:
    """Main loop — runs forever, checks every 60 seconds."""
    logger.info("[social_publisher] Started. Checking every 60 s.")
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.utcnow()
            due: List[Dict[str, Any]] = await db.scheduled_posts.find({
                "status": "scheduled",
                "scheduled_at": {"$lte": now},
                "$or": [
                    {"zernio_post_id": {"$exists": False}},
                    {"zernio_post_id": None},
                    {"zernio_post_id": ""},
                ],
            }).to_list(50)

            if not due:
                continue

            logger.info("[social_publisher] %d posts due for publishing", len(due))

            for post in due:
                pid = str(post["_id"])
                result = await push_post_to_zernio(db, post)
                await apply_publish_result(db, pid, result)

        except Exception as e:
            logger.exception("[social_publisher] Unexpected error in publish loop: %s", e)

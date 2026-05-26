"""
Zilo Scout Worker — runs due scouts on a schedule (Open Scouts dispatcher pattern).

Checks every 5 minutes for scouts whose next_run_at has passed.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from scout_service import (
    EXECUTIONS_COLLECTION,
    execute_scout,
    find_due_scouts,
)

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 300  # 5 minutes


async def _scout_already_running(db, scout_id: str) -> bool:
    running = await db[EXECUTIONS_COLLECTION].find_one({
        "scout_id": scout_id,
        "status": "running",
    })
    return running is not None


async def run_scout_worker(db) -> None:
    """Main loop — runs forever."""
    logger.info("[scout_worker] Started. Checking every %ds.", CHECK_INTERVAL_SEC)
    while True:
        try:
            due = await find_due_scouts(db, limit=20)
            if due:
                logger.info("[scout_worker] %d scouts due", len(due))

                for scout in due:
                    uid = scout.get("user_id", "")
                    scout_id = scout.get("_id", "")

                    if not uid or not scout_id:
                        continue

                    if await _scout_already_running(db, scout_id):
                        logger.debug("[scout_worker] skip scout=%s already running", scout_id)
                        continue

                    try:
                        result = await execute_scout(db, scout)
                        logger.info("[scout_worker] scout=%s done: found=%s raw=%s", scout_id, result.get("results_found"), result.get("raw_count"))
                    except Exception as e:
                        logger.error("[scout_worker] scout=%s failed: %s", scout_id, e)

        except Exception as e:
            logger.exception("[scout_worker] loop error: %s", e)
            
        await asyncio.sleep(CHECK_INTERVAL_SEC)

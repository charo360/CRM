"""
worker.py — Background job worker.

Runs as a separate process alongside the main API server.
Consumes jobs from Redis queues and executes them asynchronously.

Start with:
    python worker.py

Jobs processed:
  - queue:broadcast  — send WhatsApp broadcast messages
  - queue:receipt    — send sale receipts via WhatsApp
  - queue:ai_reply   — (future) AI reply generation
"""

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv
load_dotenv()

from redis_client import (
    dequeue_job,
    QUEUE_BROADCAST,
    QUEUE_RECEIPT,
    QUEUE_AI_REPLY,
    get_redis,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)

_running = True


def _shutdown(sig, frame):
    global _running
    logging.info("[Worker] Shutdown signal received — finishing current job then stopping")
    _running = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


# ── Database setup (reuse server's DB connection) ─────────────────────────────

async def _get_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    tunnel_mode = os.environ.get("TUNNEL_MODE", "").lower() == "true"
    if tunnel_mode:
        from mongo_http_client import AsyncMongoHTTPClient
        api_url = os.environ.get("MONGO_DATA_API_URL")
        api_key = os.environ.get("MONGO_DATA_API_KEY")
        cluster = os.environ.get("MONGO_CLUSTER_NAME", "Cluster0")
        db_name = os.environ.get("DB_NAME", "whatsapp_crm")
        if not api_url or not api_key:
            logging.critical("MONGO_DATA_API_URL or MONGO_DATA_API_KEY not set (TUNNEL_MODE=true)")
            sys.exit(1)
        client = AsyncMongoHTTPClient(api_url, api_key, cluster, db_name)
        return client[db_name]
    else:
        mongo_url = os.environ.get("MONGO_URL")
        if not mongo_url:
            logging.critical("MONGO_URL not set in environment. Set MONGO_URL to your MongoDB connection string.")
            sys.exit(1)
        client = AsyncIOMotorClient(mongo_url)
        return client[os.environ.get("DB_NAME", "whatsapp_crm")]


# ── Job handlers ──────────────────────────────────────────────────────────────

async def handle_broadcast(job: dict, db) -> None:
    """Send a broadcast that was queued from the API."""
    from whatsapp_service import get_whatsapp_service, BROADCAST_DELAY
    import random as _rnd

    broadcast_id = job["broadcast_id"]
    user_id      = job["user_id"]
    message      = job["message"]
    customers    = job["customers"]
    image_urls   = job.get("image_urls", [])

    ws = get_whatsapp_service(db)
    server_url = os.environ.get("SERVER_URL", "").rstrip("/")

    def _full_url(url: str) -> str:
        if not url:
            return url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{server_url}{url}" if server_url else url

    resolved_images = [_full_url(u) for u in image_urls if u]
    sent_count = 0

    for customer in customers:
        try:
            personalized = message.replace("{{name}}", customer.get("name", "there"))
            if resolved_images:
                await ws.send_message(
                    user_id=user_id,
                    to_number=customer["phone_number"],
                    message=personalized,
                    customer_name=customer.get("name"),
                    media_url=resolved_images[0],
                    send_context="broadcast",
                )
                for img_url in resolved_images[1:]:
                    await ws.send_message(
                        user_id=user_id,
                        to_number=customer["phone_number"],
                        message="",
                        customer_name=customer.get("name"),
                        media_url=img_url,
                        send_context="broadcast",
                    )
            else:
                await ws.send_message(
                    user_id=user_id,
                    to_number=customer["phone_number"],
                    message=personalized,
                    customer_name=customer.get("name"),
                    send_context="broadcast",
                )
            sent_count += 1
        except Exception as e:
            logging.error(f"[Worker][Broadcast] Failed to send to {customer.get('phone_number')}: {e}")

        await asyncio.sleep(_rnd.uniform(*BROADCAST_DELAY))

    await db.broadcasts.update_one(
        {"_id": broadcast_id},
        {"$set": {"sent_count": sent_count, "status": "completed"}},
    )
    logging.info(f"[Worker][Broadcast] {broadcast_id} complete — {sent_count}/{len(customers)} sent")


async def handle_receipt(job: dict, db) -> None:
    """Send a sale receipt via WhatsApp."""
    from whatsapp_service import get_whatsapp_service
    ws = get_whatsapp_service(db)
    try:
        await ws.send_message(
            user_id=job["user_id"],
            to_number=job["phone"],
            message=job["message"],
            customer_name=job.get("customer_name"),
            send_context="receipt",
        )
        await db.sales.update_one(
            {"_id": job["sale_id"]},
            {"$set": {"receipt_sent": True}},
        )
        logging.info(f"[Worker][Receipt] Receipt sent for sale {job['sale_id']}")
    except Exception as e:
        logging.error(f"[Worker][Receipt] Failed for sale {job.get('sale_id')}: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────

QUEUES = [QUEUE_BROADCAST, QUEUE_RECEIPT, QUEUE_AI_REPLY]


async def main():
    logging.info("[Worker] Starting — connecting to DB and Redis...")
    db = await _get_db()

    # Verify Redis connection
    r = await get_redis()
    if r:
        logging.info("[Worker] Redis connected — ready to process jobs")
    else:
        logging.warning("[Worker] Redis not available — worker has nothing to do. Set REDIS_URL to enable.")
        return

    logging.info(f"[Worker] Listening on queues: {QUEUES}")

    while _running:
        try:
            # Poll each queue in round-robin (short timeout so we check _running often)
            for queue in QUEUES:
                if not _running:
                    break
                job = await dequeue_job(queue, timeout=2)
                if not job:
                    continue

                job_type = job.get("type", queue)
                logging.info(f"[Worker] Processing job type={job_type} queue={queue}")

                try:
                    if queue == QUEUE_BROADCAST:
                        await handle_broadcast(job, db)
                    elif queue == QUEUE_RECEIPT:
                        await handle_receipt(job, db)
                    else:
                        logging.warning(f"[Worker] No handler for queue {queue}")
                except Exception as e:
                    logging.error(f"[Worker] Job failed (type={job_type}): {e}", exc_info=True)

        except Exception as e:
            logging.error(f"[Worker] Unexpected error in main loop: {e}", exc_info=True)
            await asyncio.sleep(2)

    logging.info("[Worker] Stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())

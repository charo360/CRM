"""
Lead Scout Worker — runs saved lead searches on schedule and stores results
in the discovered_leads collection, deduplicating against CRM customers.

Called by:
  - POST /lead-scouts/:id/run  (manual trigger)
  - Background loop started at app startup (checks every 30 min)
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SCOUTS_COL  = "lead_scouts"
INBOX_COL   = "discovered_leads"
CREDITS_COL = "lead_credits"

# Cost DataForSEO charges Zilo per search
_DFS_COST_USD   = 0.002
# What Zilo charges users per run (set in .env — default 5× markup)
_CREDIT_PRICE   = float(os.environ.get("LEAD_CREDIT_PRICE_USD", "0.01"))
# Free credits given to every new user
_FREE_CREDITS   = int(os.environ.get("LEAD_FREE_CREDITS", "10"))
# Zilo's margin per run
_MARGIN_USD     = round(_CREDIT_PRICE - _DFS_COST_USD, 4)


async def get_credit_balance(db, user_id: str) -> float:
    doc = await db[CREDITS_COL].find_one({"user_id": user_id})
    if not doc:
        # First time — initialise with free credits
        await db[CREDITS_COL].insert_one({
            "_id": user_id,
            "user_id": user_id,
            "balance_credits": float(_FREE_CREDITS),
            "total_spent_usd": 0.0,
            "total_runs": 0,
            "created_at": datetime.utcnow(),
        })
        return float(_FREE_CREDITS)
    return float(doc.get("balance_credits", 0))


async def deduct_credit(db, user_id: str, credits: float = 1.0) -> float:
    """Atomically deduct credits and record spend. Returns new balance."""
    result = await db[CREDITS_COL].find_one_and_update(
        {"user_id": user_id, "balance_credits": {"$gte": credits}},
        {"$inc": {
            "balance_credits": -credits,
            "total_spent_usd": _CREDIT_PRICE * credits,
            "total_runs": 1,
        }},
        return_document=True,
        upsert=False,
    )
    if not result:
        raise ValueError("Insufficient credits")
    return float(result["balance_credits"])


async def add_credits(db, user_id: str, credits: float, note: str = "manual") -> float:
    """Add credits to a user's balance (admin top-up or purchase)."""
    result = await db[CREDITS_COL].find_one_and_update(
        {"user_id": user_id},
        {"$inc": {"balance_credits": credits},
         "$push": {"top_ups": {"credits": credits, "note": note, "at": datetime.utcnow()}}},
        return_document=True,
        upsert=True,
    )
    return float(result["balance_credits"])

_FREQ_DELTA = {
    "daily":  timedelta(hours=24),
    "weekly": timedelta(days=7),
    "manual": None,
}


async def _already_in_crm(db, user_id: str, domain: Optional[str], email: Optional[str], name: str) -> bool:
    q = {"user_id": user_id}
    if email:
        if await db.customers.find_one({**q, "email": email.lower().strip()}):
            return True
    if domain:
        import re as _re
        if await db.customers.find_one({**q, "notes": {"$regex": _re.escape(domain), "$options": "i"}}):
            return True
    return False


async def _already_in_inbox(db, user_id: str, scout_id: str, domain: Optional[str], name: str) -> bool:
    if domain:
        if await db[INBOX_COL].find_one({"user_id": user_id, "domain": domain}):
            return True
    # Fallback: same name from same scout
    if await db[INBOX_COL].find_one({"user_id": user_id, "scout_id": scout_id,
                                      "name": name, "status": {"$ne": "dismissed"}}):
        return True
    return False


async def run_scout(db, scout: dict) -> int:
    """Run one scout, deduct 1 credit, store new leads in inbox. Returns new lead count."""
    uid                = scout["user_id"]
    scout_id           = scout["_id"]
    keyword            = scout.get("keyword", "")
    location           = scout.get("location", "")
    expanded_keywords  = scout.get("expanded_keywords")  # pre-computed by AI on creation

    # ── Skip if inbox still has plenty of leads ──────────────────────────────
    inbox_count = await db[INBOX_COL].count_documents(
        {"user_id": uid, "scout_id": scout_id, "status": "new"}
    )
    if inbox_count >= 15:
        logger.info("[lead_scout] scout %s skipped — %d leads still waiting in inbox", scout_id, inbox_count)
        return 0

    logger.info("[lead_scout] running scout %s: %r in %r", scout_id, keyword, location)

    # ── Credit check & deduction ─────────────────────────────────────────────
    try:
        new_balance = await deduct_credit(db, uid, credits=1.0)
        logger.info("[lead_scout] deducted 1 credit from %s — balance now %.1f", uid, new_balance)
    except ValueError:
        logger.warning("[lead_scout] scout %s blocked — user %s has insufficient credits", scout_id, uid)
        await db[SCOUTS_COL].update_one({"_id": scout_id}, {"$set": {
            "last_error": "Insufficient credits — please top up to continue running scouts.",
            "last_run": datetime.utcnow(),
        }})
        return 0

    try:
        from business_leads import search_all_keywords, expand_keywords
        # Cache expanded keywords on first run so subsequent runs skip the AI call
        if not expanded_keywords:
            expanded_keywords = await expand_keywords(keyword)
            await db[SCOUTS_COL].update_one(
                {"_id": scout_id},
                {"$set": {"expanded_keywords": expanded_keywords}},
            )
        leads = await search_all_keywords(keyword, location=location, expanded_keywords=expanded_keywords)
    except Exception as e:
        logger.error("[lead_scout] search failed for scout %s: %s", scout_id, e)
        await db[SCOUTS_COL].update_one({"_id": scout_id}, {"$set": {
            "last_run": datetime.utcnow(),
            "last_error": str(e),
        }})
        return 0

    new_count = 0
    for lead in leads:
        domain = lead.get("domain")
        email  = lead.get("email")
        name   = lead.get("name", "")

        # Skip if already in CRM
        if await _already_in_crm(db, uid, domain, email, name):
            continue
        # Skip if already in inbox (not yet dismissed)
        if await _already_in_inbox(db, uid, scout_id, domain, name):
            continue

        doc = {
            "_id":         str(uuid.uuid4()),
            "user_id":     uid,
            "scout_id":    scout_id,
            "scout_name":  scout.get("name", keyword),
            "status":      "new",        # new | saved | dismissed
            "discovered_at": datetime.utcnow(),
            **lead,
        }
        await db[INBOX_COL].insert_one(doc)
        new_count += 1

    # Update last_run and schedule next_run
    freq   = scout.get("frequency", "manual")
    delta  = _FREQ_DELTA.get(freq)
    update = {
        "last_run":   datetime.utcnow(),
        "last_error": None,
        "new_leads":  new_count,
    }
    if delta:
        update["next_run"] = datetime.utcnow() + delta

    await db[SCOUTS_COL].update_one({"_id": scout_id}, {"$set": update})
    logger.info("[lead_scout] scout %s found %d new leads", scout_id, new_count)
    return new_count


async def run_all_due(db) -> None:
    """Run all scouts whose next_run time has passed."""
    now = datetime.utcnow()
    due = await db[SCOUTS_COL].find({
        "enabled": True,
        "frequency": {"$in": ["daily", "weekly"]},
        "$or": [
            {"next_run": {"$lte": now}},
            {"next_run": {"$exists": False}},
            {"last_run": {"$exists": False}},
        ],
    }).to_list(200)

    if not due:
        return

    logger.info("[lead_scout] %d scouts due to run", len(due))
    for scout in due:
        try:
            await run_scout(db, scout)
        except Exception as e:
            logger.error("[lead_scout] scout %s crashed: %s", scout["_id"], e)
        await asyncio.sleep(2)   # polite gap between scouts


async def background_loop(db) -> None:
    """Infinite loop — checks for due scouts every 30 minutes."""
    while True:
        try:
            await run_all_due(db)
        except Exception as e:
            logger.error("[lead_scout] background loop error: %s", e)
        await asyncio.sleep(30 * 60)   # 30 minutes

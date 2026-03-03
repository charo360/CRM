"""
ConversationState — Reads and writes per-customer conversation state to MongoDB.

State is stored in db.conversation_states collection.
Agents read it before replying and update it after.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLLECTION = "conversation_states"


async def load_state(db, user_id: str, customer_id: str) -> Dict[str, Any]:
    """
    Load the current conversation state for a customer.
    Returns a default state dict if none found.
    """
    if db is None or not customer_id:
        return _default_state()
    try:
        doc = await db[COLLECTION].find_one({
            "user_id": user_id,
            "customer_id": str(customer_id)
        })
        if doc:
            return {
                "state": doc.get("state", "new"),
                "last_discussed_product": doc.get("last_discussed_product"),
                "last_discussed_product_id": doc.get("last_discussed_product_id"),
                "last_price_offered": doc.get("last_price_offered"),
                "pending_question": doc.get("pending_question"),
                "complaint_count": doc.get("complaint_count", 0),
                "last_intent": doc.get("last_intent"),
                "updated_at": doc.get("updated_at"),
            }
    except Exception as e:
        logger.error(f"[ConversationState] load error: {e}")
    return _default_state()


async def save_state(db, user_id: str, customer_id: str, updates: Dict[str, Any]) -> None:
    """
    Upsert conversation state for a customer.
    Only updates provided keys — does not wipe existing state.
    """
    if db is None or not customer_id:
        return
    try:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db[COLLECTION].update_one(
            {"user_id": user_id, "customer_id": str(customer_id)},
            {"$set": updates},
            upsert=True
        )
    except Exception as e:
        logger.error(f"[ConversationState] save error: {e}")


async def mark_escalated(db, user_id: str, customer_id: str, reason: str) -> None:
    """Mark this conversation as needing human attention."""
    if db is None or not customer_id:
        return
    try:
        await db[COLLECTION].update_one(
            {"user_id": user_id, "customer_id": str(customer_id)},
            {"$set": {
                "state": "escalated",
                "escalation_reason": reason,
                "updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        # Also flag the customer record
        await db.customers.update_one(
            {"_id": customer_id},
            {"$set": {
                "needs_human": True,
                "needs_human_reason": reason,
                "needs_human_at": datetime.now(timezone.utc)
            }}
        )
        logger.info(f"[ConversationState] escalated customer {customer_id}: {reason}")
    except Exception as e:
        logger.error(f"[ConversationState] mark_escalated error: {e}")


async def clear_escalation(db, user_id: str, customer_id: str) -> None:
    """Clear escalation flag when human has responded."""
    if db is None or not customer_id:
        return
    try:
        await db[COLLECTION].update_one(
            {"user_id": user_id, "customer_id": str(customer_id)},
            {"$set": {"state": "ongoing"}, "$unset": {"escalation_reason": ""}},
        )
        await db.customers.update_one(
            {"_id": customer_id},
            {"$unset": {"needs_human": "", "needs_human_reason": "", "needs_human_at": ""}}
        )
    except Exception as e:
        logger.error(f"[ConversationState] clear_escalation error: {e}")


def _default_state() -> Dict[str, Any]:
    return {
        "state": "new",
        "last_discussed_product": None,
        "last_discussed_product_id": None,
        "last_price_offered": None,
        "pending_question": None,
        "complaint_count": 0,
        "last_intent": None,
        "updated_at": None,
    }

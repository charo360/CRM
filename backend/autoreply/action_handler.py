"""
action_handler.py — validates and executes Claude's CRM actions.

Every action is executed independently — one failure doesn't block the others.
All DB writes are logged so failures are traceable.

Actions supported:
  create_order          → db.orders.insert_one
  create_booking        → db.bookings.insert_one
  cancel_order          → db.orders.update_one (status=cancelled)
  reschedule_booking    → db.bookings.update_one (status=reschedule_requested)
  tag_customer          → db.customers.update_one ($addToSet tags)
  set_payment_pending   → db.orders.update_one (payment_status=pending_verification)
  notify_owner          → db.customers.update_one (needs_human=True)
  clear_flow            → handled in engine.py (state update)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def execute_actions(
    db,
    actions: List[Dict[str, Any]],
    user_id,
    customer_id,
    user: dict,
) -> None:
    """Execute all CRM write actions returned by Claude. Failures are logged, not raised."""
    if not actions:
        return

    currency = (user.get("settings") or {}).get("currency") or user.get("currency", "KES")

    for action in actions:
        atype = action.get("type", "")
        try:
            if atype == "create_order":
                await _create_order(db, action, user_id, customer_id, currency)
            elif atype == "create_booking":
                await _create_booking(db, action, user_id, customer_id)
            elif atype == "cancel_order":
                await _cancel_order(db, action, user_id, customer_id)
            elif atype == "reschedule_booking":
                await _reschedule_booking(db, action, user_id, customer_id)
            elif atype == "tag_customer":
                await _tag_customer(db, action, customer_id)
            elif atype == "set_payment_pending":
                await _set_payment_pending(db, action, user_id, customer_id)
            elif atype == "notify_owner":
                await _notify_owner(db, action, customer_id)
            elif atype == "clear_flow":
                pass  # handled by engine after all actions
            else:
                logger.warning(f"[ActionHandler] Unknown action type: '{atype}' — skipped")
        except Exception as exc:
            logger.error(f"[ActionHandler] Action '{atype}' failed: {exc}", exc_info=True)


# ── Individual action handlers ────────────────────────────────────────────────

async def _create_order(db, action: dict, user_id, customer_id, currency: str) -> None:
    qty = max(1, int(action.get("quantity") or 1))
    unit_price = float(action.get("unit_price") or 0)
    total = round(qty * unit_price, 2)
    order_number = f"ORD-{uuid.uuid4().hex[:6].upper()}"
    product_name = (action.get("product_name") or "").strip()

    if not product_name:
        logger.warning("[ActionHandler] create_order skipped — product_name missing")
        return

    order_doc = {
        "user_id":        user_id,
        "customer_id":    customer_id,
        "order_number":   order_number,
        "product_name":   product_name,
        "items": [{
            "product_name": product_name,
            "product_id":   action.get("product_id", ""),
            "quantity":     qty,
            "unit_price":   unit_price,
            "price":        total,
        }],
        "total_amount":       total,
        "total":              total,
        "status":             "pending",
        "payment_status":     "unpaid",
        "delivery_type":      action.get("delivery_type", "pickup"),
        "delivery_address":   action.get("delivery_address", ""),
        "notes":              action.get("notes", ""),
        "created_at":         datetime.utcnow(),
        "created_by":         "customer",
    }
    result = await db.orders.insert_one(order_doc)
    logger.info(f"[ActionHandler] Order created: {order_number} id={result.inserted_id} product='{product_name}' qty={qty} total={currency}{total}")


async def _create_booking(db, action: dict, user_id, customer_id) -> None:
    service_name = (action.get("service_name") or "").strip()
    if not service_name:
        logger.warning("[ActionHandler] create_booking skipped — service_name missing")
        return

    booking_number = f"BK-{uuid.uuid4().hex[:6].upper()}"
    is_rental = bool(action.get("is_rental"))

    booking_doc = {
        "user_id":        user_id,
        "customer_id":    customer_id,
        "booking_number": booking_number,
        "service_name":   service_name,
        "service_id":     action.get("service_id", ""),
        "price":          float(action.get("price") or 0),
        "status":         "pending",
        "created_at":     datetime.utcnow(),
        "created_by":     "customer",
    }

    if is_rental:
        booking_doc["checkin_date"]  = action.get("checkin_date", "")
        booking_doc["checkout_date"] = action.get("checkout_date", "")
    else:
        booking_doc["date"] = action.get("date", "")
        booking_doc["time"] = action.get("time", "")

    if action.get("notes"):
        booking_doc["notes"] = action["notes"]

    result = await db.bookings.insert_one(booking_doc)
    logger.info(f"[ActionHandler] Booking created: {booking_number} id={result.inserted_id} service='{service_name}'")


async def _cancel_order(db, action: dict, user_id, customer_id) -> None:
    order_id = action.get("order_id", "latest")
    query: dict = {"user_id": user_id, "customer_id": customer_id, "status": {"$ne": "cancelled"}}

    if order_id and order_id != "latest":
        # Try to use provided ID directly (could be string or ObjectId-compatible)
        query["order_number"] = order_id

    order = await db.orders.find_one(query, sort=[("created_at", -1)])
    if not order:
        logger.warning(f"[ActionHandler] cancel_order — no active order found for customer {customer_id}")
        return

    await db.orders.update_one(
        {"_id": order["_id"]},
        {"$set": {
            "status":        "cancelled",
            "cancelled_at":  datetime.utcnow(),
            "cancelled_by":  "customer",
            "cancel_reason": action.get("reason", ""),
        }},
    )
    logger.info(f"[ActionHandler] Order cancelled: {order.get('order_number')} id={order['_id']}")


async def _reschedule_booking(db, action: dict, user_id, customer_id) -> None:
    booking_id = action.get("booking_id", "latest")
    query: dict = {"user_id": user_id, "customer_id": customer_id, "status": {"$ne": "cancelled"}}

    if booking_id and booking_id != "latest":
        query["booking_number"] = booking_id

    booking = await db.bookings.find_one(query, sort=[("created_at", -1)])
    if not booking:
        logger.warning(f"[ActionHandler] reschedule_booking — no active booking found for customer {customer_id}")
        return

    await db.bookings.update_one(
        {"_id": booking["_id"]},
        {"$set": {
            "status":                   "reschedule_requested",
            "new_date":                 action.get("new_date", ""),
            "reschedule_reason":        action.get("reason", ""),
            "reschedule_requested_at":  datetime.utcnow(),
        }},
    )
    logger.info(f"[ActionHandler] Booking reschedule requested: {booking.get('booking_number')} → {action.get('new_date')}")


async def _tag_customer(db, action: dict, customer_id) -> None:
    tag = (action.get("tag") or "").strip()
    if not tag or not customer_id:
        return
    await db.customers.update_one(
        {"_id": customer_id},
        {"$addToSet": {"tags": tag}},
    )
    logger.info(f"[ActionHandler] Customer {customer_id} tagged: '{tag}'")


async def _set_payment_pending(db, action: dict, user_id, customer_id) -> None:
    """Mark the most recent active order as payment pending verification."""
    order = await db.orders.find_one(
        {"user_id": user_id, "customer_id": customer_id, "status": {"$ne": "cancelled"}},
        sort=[("created_at", -1)],
    )
    if not order:
        logger.warning(f"[ActionHandler] set_payment_pending — no order found for customer {customer_id}")
        return

    await db.orders.update_one(
        {"_id": order["_id"]},
        {"$set": {
            "payment_status":                  "pending_verification",
            "payment_screenshot_received_at":  datetime.utcnow(),
        }},
    )
    logger.info(f"[ActionHandler] Payment pending set for order {order.get('order_number')} customer={customer_id}")


async def _notify_owner(db, action: dict, customer_id) -> None:
    """Flag customer as needing human attention."""
    reason = action.get("reason", "other")
    message = action.get("message", "")
    human_reason = message or reason

    await db.customers.update_one(
        {"_id": customer_id},
        {"$set": {
            "needs_human":        True,
            "needs_human_reason": human_reason,
            "needs_human_at":     datetime.utcnow(),
        }},
    )
    logger.info(f"[ActionHandler] Owner notified for customer {customer_id} — reason: {reason}")

"""Find the order a customer is talking about, so the AI can act on it.

A buyer arriving from the storefront lands in WhatsApp with the order
number already typed:

    "Hi Lex, I just placed order ZILO-260909-F20D94 on your shop."

The AI had no idea what that was, so it escalated — "let me flag this to
the team" — for an order sitting in the database with its items, total and
payment status. The customer has done everything right and been handed to
a queue.

This looks the order up so the reply can name what they bought, say
whether it is paid, and take payment if it is not.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ZILO-260909-F20D94 from the storefront; ORD-A1B2C3 from a chat order.
_ORDER_PATTERNS = (
    re.compile(r"\bZILO-\d{6}-[0-9A-Z]{4,10}\b", re.I),
    re.compile(r"\bORD-[0-9A-Z]{4,12}\b", re.I),
)

# "my order", "the order", "order status" — a reference without a number.
_VAGUE_ORDER = re.compile(
    r"\b(my|the|our)\s+(order|purchase|delivery)\b|\border\s+(status|update)\b",
    re.I,
)


def referenced_order_numbers(message: str) -> List[str]:
    """Order numbers named in the message, uppercased, in the order seen."""
    found: List[str] = []
    for pattern in _ORDER_PATTERNS:
        for match in pattern.findall(message or ""):
            upper = match.upper()
            if upper not in found:
                found.append(upper)
    return found


async def find_referenced_order(
    db, user_id: str, customer_id: Optional[str], message: str
) -> Optional[Dict[str, Any]]:
    """The order this message is about, or None.

    A number in the message wins. Failing that, a customer asking vaguely
    about "my order" gets their most recent one. Never raises: not finding
    an order must leave the conversation exactly as it was.
    """
    try:
        for number in referenced_order_numbers(message):
            order = await db.orders.find_one({"user_id": user_id, "order_number": number})
            if order:
                return order
            # A number we cannot find is worth knowing about: it is either a
            # typo or another business's order read out to us.
            logger.info("[order_lookup] %s not found for user %s", number, user_id)

        if customer_id and _VAGUE_ORDER.search(message or ""):
            return await db.orders.find_one(
                {"user_id": user_id, "customer_id": customer_id,
                 "status": {"$ne": "cancelled"}},
                sort=[("created_at", -1)],
            )
    except Exception as exc:
        logger.warning("[order_lookup] %s", exc)
    return None


def is_unpaid(order: Dict[str, Any]) -> bool:
    status = str(order.get("payment_status") or "").strip().lower()
    return status not in ("paid", "refunded")


def describe_order(order: Dict[str, Any], pay_url: Optional[str] = None) -> str:
    """The order as prompt context, so the AI answers instead of escalating."""
    currency = order.get("currency") or ""
    total = order.get("total_amount") or 0
    lines = [
        "THE CUSTOMER'S ORDER — you already have this, do not ask the team:",
        f"  Number: {order.get('order_number')}",
        f"  Total: {currency} {total}",
        f"  Payment: {'PAID' if not is_unpaid(order) else 'NOT PAID YET'}",
    ]
    items = order.get("items") or []
    if items:
        listed = ", ".join(
            f"{i.get('quantity', 1)}x {i.get('product_name') or i.get('name') or 'item'}"
            for i in items[:8]
        )
        lines.append(f"  Items: {listed}")
    if order.get("delivery_address"):
        lines.append(f"  Deliver to: {order['delivery_address']}")

    if is_unpaid(order):
        if pay_url:
            lines.append(f"  Payment link to give them: {pay_url}")
            lines.append(
                "  Confirm what they ordered and the total, then give them that link. "
                "Do not say you will check with anyone — you have everything."
            )
        else:
            lines.append(
                "  This business takes payment manually. Confirm what they ordered and the "
                "total, then tell them how to pay using the payment details above. "
                "Do not escalate to a team."
            )
    else:
        lines.append(
            "  Already paid. Thank them, confirm what is coming, and say when. "
            "Do not ask them to pay again."
        )
    return "\n".join(lines)

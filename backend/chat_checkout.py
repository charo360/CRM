"""A pay-now link for an order taken in a WhatsApp conversation.

Online payment existed only on the storefront: a customer who ordered by
chat was told a total and left to pay by hand, even when the business had
Paystack connected. This offers the same checkout inside the conversation
for businesses that set it up, and stays silent for those that have not,
so the manual flow is untouched.

Paystack requires an email and a chat customer usually has none, so one is
derived from their phone number. It is a routing address for the receipt,
not a claim that we know their email.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Paystack rejects a request with no email. A customer who ordered over
# WhatsApp gave us a phone number instead.
_RECEIPT_DOMAIN = "wa.zilo.pro"


def _receipt_email(customer: Optional[Dict[str, Any]], phone: str) -> str:
    existing = ((customer or {}).get("email") or "").strip()
    if existing and "@" in existing:
        return existing
    digits = re.sub(r"\D", "", phone or "") or "customer"
    return f"{digits}@{_RECEIPT_DOMAIN}"


def _public_origin() -> str:
    return (os.environ.get("FRONTEND_URL") or "https://zilo.pro").rstrip("/")


async def checkout_link_for_order(
    db,
    user: Dict[str, Any],
    order: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
    phone: str = "",
) -> Optional[str]:
    """Return a pay-now URL, or None when the business takes payment manually.

    Never raises: a checkout that cannot be started must not cost the
    customer their reply, so the conversation simply carries on without a
    link and the owner collects payment as before.
    """
    try:
        from paystack_credentials import paystack_connected
    except Exception:  # pragma: no cover - import guard
        return None

    if not paystack_connected(user):
        return None

    try:
        total = float(order.get("total_amount") or order.get("total") or 0)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None

    try:
        from paystack_service import initialize_checkout_for_user

        result = await initialize_checkout_for_user(
            db,
            user,
            user_id=str(user["_id"]),
            email=_receipt_email(customer, phone),
            amount_major=total,
            currency=order.get("currency") or "KES",
            external_reference=order.get("order_number") or "",
            order_id=order.get("_id"),
            customer_id=order.get("customer_id"),
            customer_name=order.get("customer_name") or "",
            callback_url=f"{_public_origin()}/paid",
        )
        return (result or {}).get("authorization_url") or None
    except Exception as exc:
        logger.warning("[chat_checkout] could not start checkout: %s", exc)
        return None

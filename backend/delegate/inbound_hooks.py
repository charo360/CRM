"""Universal inbound hook: fire Delegate automations for CRM client messages."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def notify_delegate_inbound(
    db: Any,
    user_id: Any,
    customer: dict[str, Any],
    message: str,
    *,
    message_id: str | None = None,
) -> None:
    """
    Call after storing an inbound client message.

    Computes first-vs-repeat and dispatches matching Delegate automations
    (client_message, first_message) across all channels.
    """
    if not customer or not (message or "").strip():
        return
    try:
        incoming_n = await db.messages.count_documents({
            "user_id": user_id,
            "customer_id": customer["_id"],
            "direction": "incoming",
        })
        is_first = incoming_n <= 1
    except Exception as exc:  # noqa: BLE001
        logger.debug("[delegate] inbound count failed: %s", exc)
        is_first = False

    from .service import notify_client_message

    await notify_client_message(
        db,
        user_id,
        customer,
        message.strip(),
        is_first=is_first,
        message_id=message_id,
    )

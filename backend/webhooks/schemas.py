"""
Webhook schemas — Pydantic models for outbound event payloads.

All events include a standard envelope with:
  - event:      dot-namespaced type string (e.g. "broadcast.sent")
  - tenant_id:  business_id of the account that triggered the event
  - timestamp:  UTC ISO-8601 string
  - data:       event-specific payload dict
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WebhookEnvelope(BaseModel):
    """Standard wrapper for every outbound webhook payload."""

    event: str
    tenant_id: str
    timestamp: str
    data: Dict[str, Any]
    delivery_id: Optional[str] = None   # set by the delivery worker


# ── Typed event factory helpers ───────────────────────────────────────────────

class BroadcastSentEvent(WebhookEnvelope):
    event: str = "broadcast.sent"

    @classmethod
    def create(cls, tenant_id: str, broadcast_id: str, recipient_count: int, message: str) -> "BroadcastSentEvent":
        return cls(
            event="broadcast.sent",
            tenant_id=tenant_id,
            timestamp=_utc_now(),
            data={
                "broadcast_id": broadcast_id,
                "recipient_count": recipient_count,
                "message_preview": message[:120],
            },
        )


class CustomerCreatedEvent(WebhookEnvelope):
    event: str = "customer.created"

    @classmethod
    def create(cls, tenant_id: str, customer_id: str, name: str, phone: str) -> "CustomerCreatedEvent":
        return cls(
            event="customer.created",
            tenant_id=tenant_id,
            timestamp=_utc_now(),
            data={
                "customer_id": customer_id,
                "name": name,
                "phone": phone,
            },
        )


class OrderCreatedEvent(WebhookEnvelope):
    event: str = "order.created"

    @classmethod
    def create(cls, tenant_id: str, order_id: str, total: float, items: list) -> "OrderCreatedEvent":
        return cls(
            event="order.created",
            tenant_id=tenant_id,
            timestamp=_utc_now(),
            data={
                "order_id": order_id,
                "total": total,
                "item_count": len(items),
            },
        )


class SaleRecordedEvent(WebhookEnvelope):
    event: str = "sale.recorded"

    @classmethod
    def create(cls, tenant_id: str, sale_id: str, amount: float, customer_id: Optional[str] = None) -> "SaleRecordedEvent":
        return cls(
            event="sale.recorded",
            tenant_id=tenant_id,
            timestamp=_utc_now(),
            data={
                "sale_id": sale_id,
                "amount": amount,
                "customer_id": customer_id,
            },
        )


class FollowUpDueEvent(WebhookEnvelope):
    event: str = "followup.due"

    @classmethod
    def create(cls, tenant_id: str, followup_id: str, customer_name: str, message: str) -> "FollowUpDueEvent":
        return cls(
            event="followup.due",
            tenant_id=tenant_id,
            timestamp=_utc_now(),
            data={
                "followup_id": followup_id,
                "customer_name": customer_name,
                "message_preview": message[:120],
            },
        )

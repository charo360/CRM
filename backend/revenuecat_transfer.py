"""Resolve RevenueCat TRANSFER events from the subscription ledger.

RevenueCat deliberately keeps TRANSFER payloads small: they name the old and
new App User IDs, but do not repeat product, transaction, or expiration data.
Those fields must come from the last subscription event (or the old user row)
instead of from the TRANSFER itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Optional


def _milliseconds(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _datetime_milliseconds(value: object) -> int:
    if not isinstance(value, datetime):
        return 0
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return int(aware.timestamp() * 1000)


def _plan_from_product(product_id: object, plan_ids: set[str]) -> Optional[str]:
    base_product_id = str(product_id or "").split(":", 1)[0]
    return next(
        (plan_id for plan_id in plan_ids if base_product_id == f"crm_{plan_id}_monthly"),
        None,
    )


def resolve_transfer_subscription(
    transfer_event: Mapping[str, object],
    source_event: Optional[Mapping[str, object]],
    source_user: Optional[Mapping[str, object]],
    plan_ids: set[str],
) -> Optional[dict]:
    """Return the active subscription state carried by a TRANSFER.

    A historical subscription event is preferred because it preserves the
    store product and transaction identifiers even after the original Zilo
    account has been deleted. The old user row is a fallback for installations
    whose webhook ledger predates those fields.
    """
    source_event = source_event or {}
    source_user = source_user or {}

    product_id = source_event.get("product_id")
    plan_id = _plan_from_product(product_id, plan_ids)
    if not plan_id:
        candidate = str(source_user.get("subscription_plan") or "")
        plan_id = candidate if candidate in plan_ids else None
    if not plan_id:
        return None

    expiration_at_ms = _milliseconds(source_event.get("expiration_at_ms"))
    if not expiration_at_ms:
        expiration_at_ms = _datetime_milliseconds(
            source_user.get("subscription_current_period_end")
        )

    transfer_at_ms = _milliseconds(transfer_event.get("event_timestamp_ms"))
    active_in_user_row = source_user.get("subscription_active") is True
    active_in_ledger = bool(
        expiration_at_ms and transfer_at_ms and expiration_at_ms > transfer_at_ms
    )
    if not active_in_user_row and not active_in_ledger:
        return None

    period_type = str(source_event.get("period_type") or "").upper()
    is_trial = period_type == "TRIAL" or source_user.get("subscription_is_trial") is True
    return {
        "plan_id": plan_id,
        "expiration_at_ms": expiration_at_ms or None,
        "purchased_at_ms": _milliseconds(source_event.get("purchased_at_ms")) or None,
        "is_trial": is_trial,
        "transaction_id": source_event.get("transaction_id")
        or source_user.get("revenuecat_transaction_id"),
        "original_transaction_id": source_event.get("original_transaction_id")
        or source_user.get("revenuecat_original_transaction_id"),
        "source_event_id": source_event.get("_id"),
    }

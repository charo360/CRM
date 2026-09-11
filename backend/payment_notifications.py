"""Tell people when money moves.

Two payment paths both ended in silence. A buyer who paid online got a web
page saying "Payment confirmed" and nothing on WhatsApp, while the buyer
who *didn't* pay got a friendly confirmation message — the paying customer
was treated worse than the browsing one. And a customer who paid by M-Pesa
had their order marked pending_verification with nothing telling the owner
to go and check.

In both cases the money had arrived or been claimed and the only way to
find out was to open the app and look.

Nothing here is worth failing a payment over, so every send is best effort:
the webhook must still record the money if WhatsApp is down.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Templated alerts, not written by a model, so they cost one plan message
# whatever model the business has selected.
RECEIPT_CONTEXT = "payment_receipt"
OWNER_ALERT_CONTEXT = "payment_alert"


def _same_line(a: str, b: str) -> bool:
    """Whether two numbers are the same phone, however each was written.

    The owner's number is stored as +254700000001 in one place and
    254700000001 in another; a plain != would send them their own receipt.
    """
    da = "".join(ch for ch in str(a or "") if ch.isdigit())
    db_ = "".join(ch for ch in str(b or "") if ch.isdigit())
    return bool(da) and bool(db_) and (da == db_ or da[-9:] == db_[-9:])


def _money(currency: str, amount: Any) -> str:
    try:
        return f"{currency} {float(amount):,.2f}".replace(".00", "")
    except (TypeError, ValueError):
        return f"{currency} {amount}"


def _items_line(order: Optional[Dict[str, Any]]) -> str:
    items = (order or {}).get("items") or []
    if not items:
        return ""
    return ", ".join(
        f"{i.get('quantity', 1)}x {i.get('product_name') or i.get('name') or 'item'}"
        for i in items[:6]
    )


async def notify_payment_received(
    db,
    user: Dict[str, Any],
    *,
    order: Optional[Dict[str, Any]],
    customer_name: str,
    customer_phone: str,
    amount: Any,
    currency: str,
    reference: str = "",
) -> None:
    """Receipt to the buyer, and tell the owner the money landed."""
    order_number = (order or {}).get("order_number") or reference or ""
    items = _items_line(order)
    total = _money(currency, amount)

    try:
        from whatsapp_service import get_whatsapp_service, owner_whatsapp_number

        wa = get_whatsapp_service(db)
        user_id = str(user["_id"])

        if customer_phone:
            lines = [f"✅ *Payment received — {total}*"]
            if order_number:
                lines.append(f"Order: *{order_number}*")
            if items:
                lines.append(f"For: {items}")
            lines += ["", "Thank you! We're getting your order ready."]
            try:
                await wa.send_message(
                    user_id=user_id,
                    to_number=customer_phone,
                    message="\n".join(lines),
                    customer_name=customer_name,
                    send_context=RECEIPT_CONTEXT,
                )
            except Exception as exc:
                logger.warning("[payment_notify] receipt to buyer failed: %s", exc)

        owner_no = owner_whatsapp_number(user)
        if owner_no and not _same_line(owner_no, customer_phone):
            lines = [f"💰 *{total} received* from {customer_name}"]
            if order_number:
                lines.append(f"Order: *{order_number}*")
            if items:
                lines.append(f"For: {items}")
            lines += ["", "Paid online. Nothing to collect."]
            try:
                await wa.send_message(
                    user_id=user_id,
                    to_number=owner_no,
                    message="\n".join(lines),
                    send_context=OWNER_ALERT_CONTEXT,
                )
            except Exception as exc:
                logger.warning("[payment_notify] owner alert failed: %s", exc)
    except Exception as exc:
        logger.warning("[payment_notify] could not notify: %s", exc)


async def notify_payment_claimed(
    db,
    user: Dict[str, Any],
    *,
    order: Optional[Dict[str, Any]],
    customer_name: str,
    amount_claimed: Any = None,
    currency: str = "",
) -> None:
    """A customer says they have paid by hand — someone has to check.

    The alert used to read "WhatsApp contact says they have paid —  3,000":
    no name, because the customer record had none and the name they gave was
    never passed on, and no currency, because orders do not carry one. The
    owner could not tell who was claiming what.
    """
    order_number = (order or {}).get("order_number") or ""
    cur = currency or (order or {}).get("currency") or ""
    order_total = (order or {}).get("total_amount") or (order or {}).get("total") or 0
    claimed = amount_claimed if amount_claimed not in (None, "") else order_total
    total = _money(cur, claimed).strip()
    try:
        from whatsapp_service import get_whatsapp_service, owner_whatsapp_number

        owner_no = owner_whatsapp_number(user)
        if not owner_no:
            return
        lines = [f"🧾 *{customer_name} says they have paid* — {total}"]
        if order_number:
            lines.append(f"Order: *{order_number}*")
        try:
            if amount_claimed not in (None, "") and order_total and \
                    abs(float(str(amount_claimed).replace(",", "")) - float(order_total)) > 0.5:
                lines.append(f"The order total is {_money(cur, order_total).strip()} -- check the difference.")
        except (TypeError, ValueError):
            pass
        lines += ["", "Not confirmed yet. Check the payment, then mark it paid in Zilo."]
        await get_whatsapp_service(db).send_message(
            user_id=str(user["_id"]),
            to_number=owner_no,
            message="\n".join(lines),
            send_context=OWNER_ALERT_CONTEXT,
        )
    except Exception as exc:
        logger.warning("[payment_notify] claim alert failed: %s", exc)

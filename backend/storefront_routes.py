"""Public Zilo catalog and checkout routes.

The mobile product catalog remains the source of truth.  A business gets a
stable public link (``/<slug>``) that shows only products it has not
explicitly hidden, creates normal Zilo orders, and starts the merchant's
configured checkout.  Prices and stock are always recalculated on the server;
the browser never supplies a price that is trusted.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from paystack_credentials import paystack_connected
from paystack_service import initialize_checkout_for_user as initialize_paystack_checkout


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_PHONE_RE = re.compile(r"^[+0-9][0-9 .()\-]{6,31}$")
_ONLINE_PROVIDERS = ("paystack",)

logger = logging.getLogger(__name__)

# Shops sit at the site root (``/<slug>``), so a slug matching a page of the
# web app would be shadowed by it and the shop would be unreachable. Every
# current top-level route is listed, plus names likely to become one.
_RESERVED_SLUGS = frozenset({
    "about", "account", "admin", "api", "app", "auth", "blog", "cart",
    "change-password", "checkout", "contact", "dashboard", "data-deletion",
    "deal", "delete-account", "docs", "faq", "feedback", "help", "home",
    "images", "invoice", "kds", "legal", "login", "logout", "media", "new",
    "order", "orders", "plans", "portal", "pricing", "privacy",
    "privacy-policy", "public", "quote", "register", "reset-password", "rex",
    "robots", "search", "security", "settings", "shop", "shopify-install-complete",
    "signup", "sitemap", "static", "status", "store", "support", "terms",
    "terms-of-service", "uploads", "user", "users", "www",
})


def _text(value: Any, maximum: int = 200) -> str:
    return str(value or "").strip()[:maximum]


def _currency(user: dict) -> str:
    return _text(
        user.get("currency") or (user.get("settings") or {}).get("currency") or "USD",
        8,
    ).upper()


def _slug_base(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (normalized or "store")[:60].strip("-") or "store"


async def _slug_is_free(db, candidate: str, user_id: Any) -> bool:
    if candidate in _RESERVED_SLUGS:
        return False
    owner = await db.users.find_one(
        {"$or": [{"public_store_slug": candidate}, {"public_store_slug_aliases": candidate}]},
        {"_id": 1},
    )
    return owner is None or owner["_id"] == user_id


async def _claim_slug(db, user_doc: dict, slug: str, keep_as_alias: str = "") -> str:
    """Point a business at ``slug``, still answering on any link already shared."""
    update: Dict[str, Any] = {"$set": {"public_store_slug": slug}}
    if keep_as_alias and keep_as_alias != slug:
        update["$addToSet"] = {"public_store_slug_aliases": keep_as_alias}
    await db.users.update_one({"_id": user_doc["_id"]}, update)
    user_doc["public_store_slug"] = slug
    return slug


async def _ensure_store_slug(db, user_doc: dict) -> str:
    existing = _text(user_doc.get("public_store_slug"), 80).lower()
    base = _slug_base(_text(user_doc.get("business_name"), 100))

    # Shops used to always get a random suffix, even when nothing else wanted
    # the name. Take the plain business name once it is free, and answer on the
    # old link too so anything already shared keeps working.
    if _SLUG_RE.fullmatch(existing):
        if existing != base and _SLUG_RE.fullmatch(base) and await _slug_is_free(db, base, user_doc["_id"]):
            return await _claim_slug(db, user_doc, base, keep_as_alias=existing)
        return existing

    if _SLUG_RE.fullmatch(base) and await _slug_is_free(db, base, user_doc["_id"]):
        return await _claim_slug(db, user_doc, base)

    for _ in range(8):
        candidate = f"{base}-{secrets.token_hex(3)}"
        if await _slug_is_free(db, candidate, user_doc["_id"]):
            return await _claim_slug(db, user_doc, candidate)
    raise HTTPException(503, "Could not create a public catalog link. Please try again.")


async def _name_taken_notice(db, user_doc: dict, slug: str) -> Dict[str, Any]:
    """Explain a link that is not simply the business name.

    Two businesses can genuinely share a name, so the first to claim the link
    keeps it and the others fall back to a suffix. Say so rather than leaving
    the merchant to wonder where the extra characters came from.
    """
    base = _slug_base(_text(user_doc.get("business_name"), 100))
    if slug == base:
        return {"preferred_slug": base, "name_taken": False, "name_reserved": False}
    return {
        "preferred_slug": base,
        "name_taken": base not in _RESERVED_SLUGS,
        "name_reserved": base in _RESERVED_SLUGS,
    }


async def public_storefront_url_for_user(db, user_doc: dict) -> Optional[str]:
    """Return a business's public shop URL, creating its stable slug when needed.

    Catalog messages must never point to a personal staff account. Resolve the
    actual business record first, and only return a link while the storefront is
    enabled.
    """
    business_id = user_doc.get("business_id", user_doc.get("_id"))
    if not business_id:
        return None
    business = await db.users.find_one({"_id": business_id})
    if not business or business.get("storefront_enabled", True) is False:
        return None
    slug = await _ensure_store_slug(db, business)
    return f"{_public_origin()}/{slug}"


def _catalog_limit(business: dict) -> Optional[int]:
    """How many products this business may list publicly, or None for no cap."""
    from entitlements import (
        normalize_plan_id,
        paid_subscription_active,
        product_catalog_limit,
        trial_window,
    )

    trial_active, _, _ = trial_window(business)
    paid = paid_subscription_active(business)
    if trial_active:
        effective = "trial"
    elif paid:
        effective = normalize_plan_id(business.get("subscription_plan"))
    else:
        effective = "free"
    return product_catalog_limit(effective, paid, trial_active)


async def _listable_products(db, business: dict) -> List[dict]:
    """The products a shop may show, newest first, capped to its plan.

    A lapsed trial keeps its shop and its products, but lists only as many as
    the free tier allows. The link a merchant shared over WhatsApp still
    works — it just shows less until they subscribe.
    """
    products = await db.products.find(
        {"user_id": business["_id"], "public_visible": {"$ne": False}}
    ).sort("created_at", -1).to_list(250)
    limit = _catalog_limit(business)
    return products if limit is None else products[:limit]


async def _business_doc(db, slug: str) -> dict:
    normalized = _text(slug, 80).lower()
    if not _SLUG_RE.fullmatch(normalized):
        raise HTTPException(404, "Store not found")
    business = await db.users.find_one(
        {"$or": [{"public_store_slug": normalized}, {"public_store_slug_aliases": normalized}]}
    )
    if not business:
        raise HTTPException(404, "Store not found")
    return business


def _public_product(product: dict) -> Dict[str, Any]:
    images = list(product.get("images") or [])
    image_url = _text(product.get("image_url"), 2000)
    if image_url and image_url not in images:
        images.insert(0, image_url)
    return {
        "id": str(product["_id"]),
        "name": _text(product.get("name"), 200),
        "description": _text(product.get("description"), 2000),
        "price": float(product.get("price") or 0),
        "discount_price": product.get("discount_price"),
        "category": _text(product.get("category") or "Other", 100),
        "image_url": image_url or (images[0] if images else ""),
        "images": images[:5],
        "in_stock": bool(product.get("in_stock", True)),
        "stock_quantity": product.get("stock_quantity"),
        "unit": _text(product.get("unit"), 80),
        "moq": max(1, int(product.get("moq") or 1)),
        "pricing_tiers": product.get("pricing_tiers") or [],
        "variants": product.get("variants") or [],
        "modifier_groups": product.get("modifier_groups") or [],
    }


def _connected_providers(user_doc: dict) -> List[str]:
    return ["paystack"] if paystack_connected(user_doc) else []


def _selected_provider(user_doc: dict) -> Optional[str]:
    connected = _connected_providers(user_doc)
    preferred = _text(user_doc.get("storefront_payment_provider"), 32).lower()
    if preferred in connected:
        return preferred
    return connected[0] if connected else None


def _ensure_paystack_currency_matches_catalog(user_doc: dict, catalog_currency: str) -> None:
    """Never send a catalog price to Paystack in a different currency."""
    paystack_currency = _text(user_doc.get("paystack_default_currency"), 8).upper()
    if paystack_currency and paystack_currency != catalog_currency.upper():
        raise HTTPException(
            409,
            (
                f"This catalog is priced in {catalog_currency}, but the business's Paystack account is "
                f"configured for {paystack_currency}. The business must use matching Zilo and Paystack "
                "currencies before accepting online payments."
            ),
        )


def _store_payload(user_doc: dict, products: Iterable[dict]) -> Dict[str, Any]:
    provider = _selected_provider(user_doc)
    return {
        "slug": user_doc.get("public_store_slug"),
        "business_name": _text(user_doc.get("business_name") or "Zilo Store", 120),
        "currency": _currency(user_doc),
        "products": [_public_product(product) for product in products],
        "checkout": {
            "online_payment_available": bool(provider),
            "provider": provider,
            "payment_label": "Pay securely" if provider else "Place order",
        },
    }


def _requested_option_names(raw: Any) -> List[Tuple[str, str]]:
    if not isinstance(raw, list):
        return []
    selected: List[Tuple[str, str]] = []
    for value in raw[:20]:
        if not isinstance(value, dict):
            continue
        group = _text(value.get("group") or value.get("group_name"), 100)
        option = _text(value.get("option") or value.get("option_name"), 100)
        if group and option:
            selected.append((group, option))
    return selected


def _tier_price(product: dict, quantity: int, base_price: float) -> float:
    applicable: List[Tuple[int, float]] = []
    for tier in product.get("pricing_tiers") or []:
        if not isinstance(tier, dict):
            continue
        try:
            minimum = int(tier.get("min_qty") or 0)
            price = float(tier.get("price"))
        except (TypeError, ValueError):
            continue
        if minimum > 0 and minimum <= quantity and price >= 0:
            applicable.append((minimum, price))
    return max(applicable, default=(0, base_price), key=lambda row: row[0])[1]


def _price_item(product: dict, requested: dict) -> Dict[str, Any]:
    try:
        quantity = int(requested.get("quantity") or 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Each quantity must be a whole number") from exc
    if quantity < 1 or quantity > 100:
        raise HTTPException(400, "Each quantity must be between 1 and 100")

    minimum = max(1, int(product.get("moq") or 1))
    if quantity < minimum:
        raise HTTPException(400, f"{product.get('name', 'This product')} has a minimum order of {minimum}")

    base_price = float(product.get("discount_price") or product.get("price") or 0)
    variant_name = _text(requested.get("variant_name") or requested.get("variant"), 120)
    if variant_name:
        variant = next(
            (v for v in product.get("variants") or [] if _text(v.get("name"), 120) == variant_name),
            None,
        )
        if not variant:
            raise HTTPException(400, f"That variant is no longer available for {product.get('name', 'this product')}")
        try:
            base_price = float(variant.get("price"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "This variant has an invalid price") from exc

    unit_price = _tier_price(product, quantity, base_price)
    selected_modifiers = _requested_option_names(requested.get("modifiers"))
    modifier_labels: List[str] = []
    selected_by_group: Dict[str, List[str]] = {}
    for group_name, option_name in selected_modifiers:
        selected_by_group.setdefault(group_name, []).append(option_name)

    for group in product.get("modifier_groups") or []:
        group_name = _text(group.get("name"), 100)
        selections = selected_by_group.pop(group_name, [])
        if group.get("required") and not selections:
            raise HTTPException(400, f"Choose an option for {group_name}")
        if not group.get("multi_select") and len(selections) > 1:
            raise HTTPException(400, f"Choose only one option for {group_name}")
        options = { _text(option.get("name"), 100): option for option in group.get("options") or [] }
        for option_name in selections:
            option = options.get(option_name)
            if not option:
                raise HTTPException(400, f"{option_name} is no longer available")
            try:
                unit_price += float(option.get("price_delta") or 0)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "A modifier has an invalid price") from exc
            modifier_labels.append(f"{group_name}: {option_name}")

    if selected_by_group:
        raise HTTPException(400, "One or more selected options are no longer available")
    if unit_price < 0:
        raise HTTPException(400, "Product price is invalid")

    return {
        "product_id": str(product["_id"]),
        "product_name": _text(product.get("name"), 200),
        "quantity": quantity,
        "unit_price": round(unit_price, 2),
        "price": round(unit_price * quantity, 2),
        "variant": variant_name or None,
        "modifiers": modifier_labels,
    }


async def _create_or_update_customer(db, user_id: str, body: dict) -> dict:
    name = _text(body.get("customer_name") or body.get("name"), 120)
    phone = _text(body.get("phone") or body.get("phone_number"), 32)
    email = _text(body.get("email"), 254).lower()
    if len(name) < 2:
        raise HTTPException(400, "Please enter your name")
    if not _PHONE_RE.fullmatch(phone):
        raise HTTPException(400, "Please enter a valid phone number")
    if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
        raise HTTPException(400, "Please enter a valid email address")

    existing = await db.customers.find_one({"user_id": user_id, "phone_number": phone})
    if existing:
        updates: Dict[str, Any] = {"name": name, "updated_at": datetime.utcnow()}
        if email:
            updates["email"] = email
        await db.customers.update_one({"_id": existing["_id"]}, {"$set": updates})
        return {**existing, **updates}

    customer = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": name,
        "phone_number": phone,
        "email": email,
        "source": "storefront",
        "status": "active",
        "total_spent": 0.0,
        "purchase_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    await db.customers.insert_one(customer)
    return customer


async def _reserve_stock(db, user_id: str, line_items: List[dict]) -> None:
    reserved: List[Tuple[str, int]] = []
    try:
        for item in line_items:
            product = await db.products.find_one({"_id": item["product_id"], "user_id": user_id})
            stock = product.get("stock_quantity") if product else None
            if stock is None:
                continue
            result = await db.products.update_one(
                {
                    "_id": item["product_id"],
                    "user_id": user_id,
                    "in_stock": {"$ne": False},
                    "stock_quantity": {"$gte": item["quantity"]},
                },
                {"$inc": {"stock_quantity": -item["quantity"]}},
            )
            if result.modified_count != 1:
                raise HTTPException(409, f"{item['product_name']} is no longer available in that quantity")
            reserved.append((item["product_id"], item["quantity"]))
    except Exception:
        for product_id, quantity in reserved:
            await db.products.update_one({"_id": product_id, "user_id": user_id}, {"$inc": {"stock_quantity": quantity}})
        raise


async def _announce_new_order(db, business: dict, order: dict) -> None:
    """Tell both sides that an order arrived.

    An order that skips online payment used to land silently: the buyer was
    told the business would confirm shortly, and the business heard nothing
    until it next opened the app. Neither message is worth failing an order
    over, so both are best effort. Paid orders are announced by the payment
    webhook instead, which can say the money actually arrived.
    """
    currency = _text(order.get("currency"), 8)
    total = float(order.get("total_amount") or 0)
    amount = f"{currency} {total:,.2f}".replace(".00", "")
    order_number = _text(order.get("order_number"), 40)
    customer_name = _text(order.get("customer_name"), 120) or "Customer"
    phone = _text(order.get("customer_phone"), 40)

    if phone:
        try:
            from whatsapp_service import get_whatsapp_service

            await get_whatsapp_service(db).send_message(
                user_id=str(business["_id"]),
                to_number=phone,
                message="\n".join([
                    f"🛒 *Order received — {amount}*",
                    f"Order: *{order_number}*",
                    "",
                    "Thank you! We'll confirm your order shortly.",
                ]),
                customer_name=customer_name,
                send_context="storefront_order",
            )
        except Exception as exc:
            logger.error("[storefront] order confirmation to buyer failed: %s", exc)

    push_token = business.get("push_token")
    if push_token:
        try:
            from notification_service import get_notification_service

            await get_notification_service().send_notification(
                push_token=push_token,
                title=f"🛒 New order — {amount}",
                body=f"{customer_name} — {order_number}",
                data={"type": "storefront_order", "order_id": str(order["_id"])},
            )
        except Exception as exc:
            logger.error("[storefront] new order push to merchant failed: %s", exc)


async def _release_stock(db, user_id: str, line_items: List[dict]) -> None:
    for item in line_items:
        product = await db.products.find_one({"_id": item["product_id"], "user_id": user_id})
        if not product or product.get("stock_quantity") is None:
            continue
        await db.products.update_one(
            {"_id": item["product_id"], "user_id": user_id},
            {"$inc": {"stock_quantity": int(item["quantity"])}},
        )


async def release_expired_storefront_reservations(db, older_than_minutes: int = 30) -> int:
    """Give back stock held by online payments that were never completed.

    Stock is taken when the order is placed so two buyers cannot claim the last
    item while one of them is on the payment page. A buyer who closes that page
    never comes back, though, so without this the count stays down for good and
    the product eventually reads as out of stock.

    Orders without an online provider are left alone: those are a real
    commitment the merchant intends to fulfil, not a pending payment.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
    stale = await db.orders.find({
        "created_by": "storefront",
        "stock_reserved": True,
        "payment_provider": {"$in": list(_ONLINE_PROVIDERS)},
        "payment_status": {"$ne": "Paid"},
        "created_at": {"$lt": cutoff},
    }).to_list(200)

    released = 0
    for order in stale:
        try:
            await _release_stock(db, str(order["user_id"]), order.get("items") or [])
            await db.orders.update_one(
                {"_id": order["_id"], "stock_reserved": True},
                {"$set": {"stock_reserved": False, "payment_status": "Expired"}},
            )
            released += 1
        except Exception as exc:
            logger.error("[storefront] could not release stock for %s: %s", order.get("_id"), exc)
    if released:
        logger.info("[storefront] released stock held by %s unpaid order(s)", released)
    return released


async def remind_unconfirmed_storefront_orders(db, older_than_minutes: int = 120) -> int:
    """Nudge merchants about shop orders they have not acted on yet.

    The buyer is told the business will confirm shortly, so an order left
    sitting is a promise going unkept. Reminds once per order and groups them
    per business, so a busy shop gets one push rather than one per order.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
    waiting = await db.orders.find({
        "created_by": "storefront",
        "status": "pending",
        "payment_status": {"$ne": "Expired"},
        "pending_reminder_sent": {"$ne": True},
        "created_at": {"$lt": cutoff},
    }).to_list(200)
    if not waiting:
        return 0

    by_business: Dict[str, List[dict]] = {}
    for order in waiting:
        by_business.setdefault(str(order.get("user_id")), []).append(order)

    reminded = 0
    for business_id, orders in by_business.items():
        business = await db.users.find_one({"_id": business_id})
        push_token = (business or {}).get("push_token")
        if push_token:
            oldest = min(orders, key=lambda o: o.get("created_at") or datetime.utcnow())
            waited = datetime.utcnow() - (oldest.get("created_at") or datetime.utcnow())
            hours = max(1, int(waited.total_seconds() // 3600))
            body = (
                f"{_text(oldest.get('customer_name'), 120) or 'A customer'} has been waiting {hours}h"
                if len(orders) == 1
                else f"{len(orders)} orders waiting — the oldest for {hours}h"
            )
            try:
                from notification_service import get_notification_service

                await get_notification_service().send_notification(
                    push_token=push_token,
                    title="⏳ Shop orders need confirming",
                    body=body,
                    data={"type": "storefront_orders_waiting", "count": len(orders)},
                )
            except Exception as exc:
                logger.error("[storefront] pending order reminder failed: %s", exc)
                continue

        # Mark them either way: without a push token there is nothing to send,
        # and re-checking these same orders every cycle helps nobody.
        for order in orders:
            await db.orders.update_one(
                {"_id": order["_id"]}, {"$set": {"pending_reminder_sent": True}}
            )
            reminded += 1

    if reminded:
        logger.info("[storefront] reminded on %s unconfirmed order(s)", reminded)
    return reminded


def _public_origin() -> str:
    return (os.environ.get("FRONTEND_URL") or "https://zilo.pro").rstrip("/")


async def _start_online_payment(db, business: dict, order: dict) -> Dict[str, Any]:
    provider = _selected_provider(business)
    if not provider:
        return {"provider": None, "payment_action": "manual"}

    _ensure_paystack_currency_matches_catalog(business, _text(order.get("currency") or "USD", 8))
    user_id = str(business["_id"])
    callback = f"{_public_origin()}/{business['public_store_slug']}/checkout?order={order['public_token']}"
    email = _text(order.get("customer_email"), 254)
    if not email:
        raise HTTPException(400, "An email address is required for secure online payment")

    try:
        result = await initialize_paystack_checkout(
            db, business, user_id=user_id, email=email, amount_major=float(order["total_amount"]),
            currency=order["currency"], external_reference=order["order_number"],
            order_id=order["_id"], customer_id=order["customer_id"],
            customer_name=order["customer_name"], callback_url=callback,
        )
        return {
            "provider": "paystack",
            "payment_action": "redirect",
            "checkout_url": result.get("authorization_url"),
            "reference": result.get("reference"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Could not start {provider.title()} checkout. Please try again.") from exc

    return {"provider": None, "payment_action": "manual"}


def _order_payload(order: dict) -> Dict[str, Any]:
    return {
        "order_token": order["public_token"],
        "order_number": order["order_number"],
        "payment_status": order.get("payment_status", "Pending"),
        "payment_provider": order.get("payment_provider"),
        "total_amount": float(order.get("total_amount") or 0),
        "currency": order.get("currency") or "USD",
        "items": order.get("items") or [],
        "created_at": order.get("created_at").isoformat() if order.get("created_at") else None,
    }


def register_storefront_routes(api_router: APIRouter, db, get_current_user: Callable) -> None:
    """Attach public catalog routes and authenticated store settings to the API."""

    @api_router.get("/storefront/me")
    async def storefront_me(user=Depends(get_current_user)):
        business_id = user.get("business_id", user["_id"])
        business = await db.users.find_one({"_id": business_id})
        if not business:
            raise HTTPException(404, "Business account not found")
        slug = await _ensure_store_slug(db, business)
        return {
            "slug": slug,
            "public_url": f"{_public_origin()}/{slug}",
            "payment_provider": _selected_provider(business) or "manual",
            "available_payment_providers": _connected_providers(business),
            **await _name_taken_notice(db, business, slug),
        }

    @api_router.put("/storefront/settings")
    async def update_storefront_settings(body: dict, user=Depends(get_current_user)):
        business_id = user.get("business_id", user["_id"])
        business = await db.users.find_one({"_id": business_id})
        if not business:
            raise HTTPException(404, "Business account not found")
        preferred = _text(body.get("payment_provider"), 32).lower()
        if preferred and preferred not in (*_ONLINE_PROVIDERS, "auto", "manual"):
            raise HTTPException(
                400,
                "Storefront checkout currently supports Paystack only. Other providers are not enabled yet.",
            )
        connected = _connected_providers(business)
        if preferred in _ONLINE_PROVIDERS and preferred not in connected:
            raise HTTPException(400, "Connect that payment provider before selecting it")
        update: Dict[str, Any] = {}
        if preferred:
            update["storefront_payment_provider"] = "" if preferred == "auto" else preferred
        if "enabled" in body:
            update["storefront_enabled"] = bool(body.get("enabled"))
        if update:
            await db.users.update_one({"_id": business_id}, {"$set": update})
            business.update(update)
        slug = await _ensure_store_slug(db, business)
        return {
            "slug": slug,
            "public_url": f"{_public_origin()}/{slug}",
            "payment_provider": _selected_provider(business) or "manual",
            "enabled": business.get("storefront_enabled", True),
            **await _name_taken_notice(db, business, slug),
        }

    @api_router.get("/storefront/name-available")
    async def storefront_name_available(name: str = ""):
        """Whether a business name is still free as a shop link.

        Unauthenticated because it is used while signing up, before there is an
        account. It reveals nothing private: every shop link is public already.
        """
        base = _slug_base(_text(name, 100))
        if not _text(name, 100) or not _SLUG_RE.fullmatch(base):
            return {"slug": base, "available": False, "reason": "invalid"}
        if base in _RESERVED_SLUGS:
            return {"slug": base, "available": False, "reason": "reserved"}
        taken = await db.users.find_one(
            {"$or": [{"public_store_slug": base}, {"public_store_slug_aliases": base}]},
            {"_id": 1},
        )
        if taken:
            return {"slug": base, "available": False, "reason": "taken"}
        return {"slug": base, "available": True, "reason": ""}

    @api_router.get("/storefront/public/{slug}")
    async def public_storefront(slug: str):
        business = await _business_doc(db, slug)
        if business.get("storefront_enabled", True) is False:
            raise HTTPException(404, "Store not found")
        return _store_payload(business, await _listable_products(db, business))

    @api_router.post("/storefront/public/{slug}/orders")
    async def create_public_order(slug: str, body: dict, request: Request, background_tasks: BackgroundTasks):
        business = await _business_doc(db, slug)
        if business.get("storefront_enabled", True) is False:
            raise HTTPException(404, "Store not found")
        provider = _selected_provider(business)
        email = _text(body.get("email"), 254)
        if provider == "paystack" and not email:
            raise HTTPException(400, "An email address is required for secure online payment")
        if provider == "paystack":
            _ensure_paystack_currency_matches_catalog(business, _currency(business))
        raw_items = body.get("items")
        if not isinstance(raw_items, list) or not raw_items or len(raw_items) > 20:
            raise HTTPException(400, "Add between 1 and 20 products to your order")

        requested_items: List[Tuple[str, dict]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise HTTPException(400, "Each order item must be valid")
            product_id = _text(item.get("product_id") or item.get("id"), 80)
            if not product_id:
                raise HTTPException(400, "Each order item must include a product")
            requested_items.append((product_id, item))

        # A buyer can purchase more than one configuration of the same product
        # (for example, one small and one large).  Preserve those separate cart
        # lines while using the de-duplicated IDs only for the database lookup.
        product_ids = list(dict.fromkeys(product_id for product_id, _ in requested_items))
        listable = {str(p["_id"]): p for p in await _listable_products(db, business)}
        products_by_id = {
            product_id: listable[product_id]
            for product_id in product_ids
            if product_id in listable and listable[product_id].get("in_stock") is not False
        }
        if len(products_by_id) != len(product_ids):
            raise HTTPException(409, "One or more products are out of stock or no longer available")
        lines = [
            _price_item(products_by_id[product_id], item)
            for product_id, item in requested_items
        ]

        customer = await _create_or_update_customer(db, str(business["_id"]), body)
        total = round(sum(float(line["price"]) for line in lines), 2)
        if total <= 0:
            raise HTTPException(400, "This order does not have a valid total")
        now = datetime.utcnow()
        order = {
            "_id": str(uuid.uuid4()),
            "user_id": str(business["_id"]),
            "customer_id": customer["_id"],
            "customer_name": customer["name"],
            "customer_phone": customer["phone_number"],
            "customer_email": customer.get("email") or "",
            "product": ", ".join(line["product_name"] for line in lines)[:500],
            "product_name": ", ".join(line["product_name"] for line in lines)[:500],
            "quantity": sum(int(line["quantity"]) for line in lines),
            "price": float(lines[0]["unit_price"]),
            "items": lines,
            "total_amount": total,
            "total": total,
            "currency": _currency(business),
            "payment_status": "Pending",
            "payment_provider": _selected_provider(business) or "manual",
            "delivery_status": "Pending",
            "delivery_type": _text(body.get("delivery_type"), 32) or "pickup",
            "delivery_address": _text(body.get("delivery_address"), 500),
            "notes": _text(body.get("notes"), 1000),
            "status": "pending",
            "created_by": "storefront",
            "recorded_by": "storefront",
            "order_number": f"ZILO-{now.strftime('%y%m%d')}-{secrets.token_hex(3).upper()}",
            "public_token": secrets.token_urlsafe(24),
            "stock_reserved": True,
            "created_at": now,
            "storefront_ip": _text(request.client.host if request.client else "", 64),
        }
        await _reserve_stock(db, str(business["_id"]), lines)
        await db.orders.insert_one(order)
        try:
            payment = await _start_online_payment(db, business, order)
        except HTTPException as exc:
            # The order is still useful to the merchant if a provider has a
            # short outage.  Return its safe public token so the customer can
            # retry payment instead of losing the basket or duplicating stock.
            payment = {
                "provider": provider,
                "payment_action": "payment_unavailable",
                "payment_error": str(exc.detail),
            }
        await db.orders.update_one(
            {"_id": order["_id"]},
            {"$set": {"payment_provider": payment.get("provider") or "manual", "payment_reference": payment.get("reference") or ""}},
        )
        order["payment_provider"] = payment.get("provider") or "manual"
        # An order heading to a payment page is announced by the webhook once
        # the money lands. Anything else is announced now, or nobody is told.
        if payment.get("payment_action") != "redirect":
            background_tasks.add_task(_announce_new_order, db, business, order)
        return {**_order_payload(order), **payment}

    @api_router.get("/storefront/public/orders/{order_token}")
    async def public_order_status(order_token: str):
        order = await db.orders.find_one({"public_token": _text(order_token, 128)})
        if not order:
            raise HTTPException(404, "Order not found")
        return _order_payload(order)

    @api_router.post("/storefront/public/orders/{order_token}/payment")
    async def retry_public_order_payment(order_token: str):
        order = await db.orders.find_one({"public_token": _text(order_token, 128)})
        if not order:
            raise HTTPException(404, "Order not found")
        if _text(order.get("payment_status"), 32).lower() == "paid":
            return {**_order_payload(order), "payment_action": "paid"}
        business = await db.users.find_one({"_id": order["user_id"]})
        if not business or business.get("storefront_enabled", True) is False:
            raise HTTPException(404, "Store not found")
        # The reservation may have been released while the buyer was away, so
        # claim the stock again before sending them back to pay for it.
        if not order.get("stock_reserved", True):
            await _reserve_stock(db, str(order["user_id"]), order.get("items") or [])
            await db.orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"stock_reserved": True, "payment_status": "Pending"}},
            )
            order["stock_reserved"] = True
        payment = await _start_online_payment(db, business, order)
        await db.orders.update_one(
            {"_id": order["_id"]},
            {"$set": {"payment_provider": payment.get("provider") or "manual", "payment_reference": payment.get("reference") or ""}},
        )
        return {**_order_payload(order), **payment}

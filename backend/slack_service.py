"""

slack_service.py — Slack inbound/outbound helpers for Zilo CRM.



Slack is connected via Composio (Integrations). Inbound messages arrive through

Composio trigger webhooks (SLACK_DIRECT_MESSAGE_RECEIVED, SLACK_CHANNEL_MESSAGE_RECEIVED).

Outbound replies use Composio chat.postMessage (see delegate/outbound.py).

"""



from __future__ import annotations



import logging

from datetime import datetime

from typing import Any, Optional



logger = logging.getLogger(__name__)





async def register_slack_workspace(db, user_oid: Any, composio_user_id: str) -> None:

    """After Composio Slack OAuth, cache workspace metadata for inbound filtering."""

    from composio_service import slack_auth_test_via_composio_or_proxy



    try:

        data = await slack_auth_test_via_composio_or_proxy(composio_user_id)

    except Exception as exc:  # noqa: BLE001

        logger.warning("[Slack] auth.test failed for %s: %s", composio_user_id, exc)

        return



    if not data or data.get("ok") is False:

        logger.warning("[Slack] auth.test returned error for %s: %s", composio_user_id, data)

        return



    team_id = str(data.get("team_id") or data.get("team") or "").strip()

    if not team_id:

        logger.warning("[Slack] auth.test missing team_id for %s", composio_user_id)

        return



    team_name = str(data.get("team") or data.get("team_name") or team_id)

    bot_user_id = str(data.get("user_id") or data.get("bot_id") or "").strip()

    now = datetime.utcnow()



    await db.slack_connections.update_one(

        {"user_id": user_oid},

        {

            "$set": {

                "user_id": user_oid,

                "composio_entity_id": composio_user_id,

                "team_id": team_id,

                "team_name": team_name,

                "bot_user_id": bot_user_id,

                "updated_at": now,

            },

            "$setOnInsert": {"created_at": now},

        },

        upsert=True,

    )

    logger.info("[Slack] registered workspace %s (%s) for user %s", team_name, team_id, user_oid)





async def unregister_slack_workspace(db, user_oid: Any) -> None:

    await db.slack_connections.delete_one({"user_id": user_oid})





async def get_or_create_slack_customer(

    db,

    user_id: Any,

    *,

    slack_user_id: str,

    channel_id: str,

    thread_ts: str | None,

    sender_name: str,

    team_id: str,

) -> dict:

    """One CRM contact per Slack user in the workspace."""

    phone = f"slack_{slack_user_id}"

    customer = await db.customers.find_one({"user_id": user_id, "phone": phone})

    now = datetime.utcnow()

    patch = {

        "slack_channel_id": channel_id,

        "slack_user_id": slack_user_id,

        "slack_team_id": team_id,

        "channel": "slack",

        "source": "slack",

        "updated_at": now,

    }

    if thread_ts:

        patch["slack_thread_ts"] = thread_ts



    if customer:

        await db.customers.update_one({"_id": customer["_id"]}, {"$set": patch})

        customer.update(patch)

        return customer



    doc = {

        "user_id": user_id,

        "phone": phone,

        "name": sender_name or f"Slack User {slack_user_id[-6:]}",

        "channel": "slack",

        "source": "slack",

        "slack_user_id": slack_user_id,

        "slack_channel_id": channel_id,

        "slack_team_id": team_id,

        "meta_id": slack_user_id,

        "created_at": now,

        "updated_at": now,

        "tags": ["New"],

        "notes": "",

        "vip": False,

        "customer_initiated": True,

        "auto_created": True,

    }

    if thread_ts:

        doc["slack_thread_ts"] = thread_ts

    result = await db.customers.insert_one(doc)

    doc["_id"] = result.inserted_id

    logger.info("[Slack] created customer %s for user %s", slack_user_id, user_id)

    return doc





async def save_slack_message(

    db,

    user_id: Any,

    customer_id: Any,

    *,

    text: str,

    direction: str,

    slack_ts: str,

    channel_id: str,

    slack_user_id: str = "",

) -> None:

    if direction == "incoming" and slack_ts:

        existing = await db.messages.find_one(

            {"user_id": user_id, "slack_ts": slack_ts, "channel": "slack"}

        )

        if existing:

            return



    await db.messages.insert_one({

        "user_id": user_id,

        "customer_id": customer_id,

        "direction": direction,

        "content": text,

        "channel": "slack",

        "slack_ts": slack_ts,

        "slack_channel_id": channel_id,

        "from_number": f"slack_{slack_user_id or channel_id}",

        "message_type": "text",

        "send_context": "incoming" if direction == "incoming" else "delegate",

        "created_at": datetime.utcnow(),

    })





async def send_slack_reply(

    db,

    user_id: Any,

    composio_entity_id: str,

    customer: dict,

    text: str,

    *,

    send_context: str = "auto_reply",

) -> bool:

    from composio_service import slack_post_message_via_composio_or_proxy



    channel_id = (customer.get("slack_channel_id") or "").strip()

    if not channel_id:

        return False

    thread_ts = customer.get("slack_thread_ts")

    data = await slack_post_message_via_composio_or_proxy(

        composio_entity_id,

        channel=channel_id,

        text=text,

        thread_ts=str(thread_ts) if thread_ts else None,

    )

    ok = bool(data.get("ok") is True or data.get("ts"))

    if ok:

        await save_slack_message(

            db,

            user_id,

            customer["_id"],

            text=text,

            direction="outgoing",

            slack_ts=str(data.get("ts") or ""),

            channel_id=channel_id,

            slack_user_id=customer.get("slack_user_id") or "",

        )

        await db.customers.update_one(

            {"_id": customer["_id"]},

            {"$set": {"last_message": text[:200], "last_contacted": datetime.utcnow()}},

        )

    return ok





def should_ignore_slack_payload(payload: dict, bot_user_id: str = "") -> bool:

    """Filter bot echoes, edits, and non-user messages from Composio Slack triggers."""

    if not payload:

        return True

    subtype = payload.get("subtype") or ""

    if subtype in (

        "bot_message",

        "message_changed",

        "message_deleted",

        "channel_join",

        "channel_leave",

    ):

        return True

    if payload.get("bot_id"):

        return True

    slack_user_id = str(payload.get("user") or "").strip()

    if bot_user_id and slack_user_id == bot_user_id:

        return True

    text = (payload.get("text") or "").strip()

    if not text:

        return True

    return False





async def process_inbound_slack_message(

    db,

    user: dict,

    payload: dict,

    *,

    composio_entity_id: str,

) -> dict[str, Any]:

    """Handle a Composio Slack trigger payload: CRM contact, Delegate, optional auto-reply."""

    import asyncio

    import logging



    user_id = user["_id"]

    conn = await db.slack_connections.find_one({"user_id": user_id})

    bot_user_id = (conn or {}).get("bot_user_id") or ""



    if should_ignore_slack_payload(payload, bot_user_id):

        return {"status": "ignored"}



    slack_user_id = str(payload.get("user") or "").strip()

    channel_id = str(payload.get("channel") or "").strip()

    text = (payload.get("text") or "").strip()

    slack_ts = str(payload.get("ts") or "")

    channel_type = payload.get("channel_type") or ""

    team_id = str(payload.get("team_id") or (conn or {}).get("team_id") or "").strip()

    thread_ts = payload.get("thread_ts")

    if not thread_ts and channel_type in ("channel", "group", "mpim"):

        thread_ts = slack_ts



    if not slack_user_id or not channel_id or not text:

        return {"status": "ignored"}



    customer = await get_or_create_slack_customer(

        db,

        user_id,

        slack_user_id=slack_user_id,

        channel_id=channel_id,

        thread_ts=str(thread_ts) if thread_ts else None,

        sender_name=f"Slack User {slack_user_id[-6:]}",

        team_id=team_id,

    )

    await save_slack_message(

        db,

        user_id,

        customer["_id"],

        text=text,

        direction="incoming",

        slack_ts=slack_ts,

        channel_id=channel_id,

        slack_user_id=slack_user_id,

    )

    await db.customers.update_one(

        {"_id": customer["_id"]},

        {"$set": {"last_message": text[:200], "last_contacted": datetime.utcnow()}},

    )



    async def _after_inbound():
        try:
            from delegate.inbound_hooks import notify_delegate_inbound

            fresh = await db.customers.find_one({"_id": customer["_id"], "user_id": user_id})
            if fresh:
                await notify_delegate_inbound(
                    db,
                    user_id,
                    fresh,
                    text,
                    message_id=slack_ts or None,
                )
        except Exception as exc:
            logging.debug("[Slack] delegate inbound hook failed: %s", exc)

        if customer.get("auto_reply") is False or not composio_entity_id:
            return



        try:

            from autoreply.engine import process_message as ar_process



            fresh_customer = await db.customers.find_one({"_id": customer["_id"], "user_id": user_id})

            if not fresh_customer:

                return



            class _SlackSender:

                async def send_message(

                    self, _uid, _to_number, message, customer_name="", send_context="auto_reply", **kwargs

                ):

                    await send_slack_reply(

                        db,

                        user_id,

                        composio_entity_id,

                        fresh_customer,

                        message,

                        send_context=send_context,

                    )



            await ar_process(

                db=db,

                user=user,

                customer=fresh_customer,

                customer_id=fresh_customer["_id"],

                message=text,

                from_number=f"slack_{slack_user_id}",

                whatsapp_service=_SlackSender(),

            )

        except Exception as exc:

            logging.error("[Slack] AutoReply error: %s", exc, exc_info=True)



    asyncio.create_task(_after_inbound())

    return {"status": "ok", "customer_id": str(customer["_id"])}



"""Unipile routes — LinkedIn messaging connect + webhooks."""

from __future__ import annotations



import logging

import os

from datetime import datetime

from typing import Any, Dict, Optional



from fastapi import APIRouter, Depends, HTTPException, Request



from unipile_service import (
    clear_linkedin_account,
    connect_linkedin_with_cookie,
    connect_linkedin_with_credentials,
    create_hosted_auth_link,
    get_connection_status,
    get_inmail_balance,
    get_stored_linkedin_account,
    is_configured,
    list_linkedin_contracts,
    poll_linkedin_account,
    resolve_linkedin_account_id,
    save_linkedin_account,
    save_linkedin_contract,
    select_linkedin_contract,
    solve_linkedin_checkpoint,
    start_linkedin_chat,
)



logger = logging.getLogger(__name__)



_AUTH_STATUSES = {"OK", "CONNECTED", "CREATION_SUCCESS", "RECONNECTED"}

_MESSAGE_EVENTS = {

    "message_received",

    "message_sent",

    "message_read",

    "message_reaction",

    "message_edited",

    "message_deleted",

    "message_delivered",

}





def _api_public_base(request: Request) -> str:

    env = (os.environ.get("API_PUBLIC_BASE") or os.environ.get("BACKEND_PUBLIC_URL") or "").strip().rstrip("/")

    if env:

        return env

    return str(request.base_url).rstrip("/")





def _frontend_base(client_origin: Optional[str] = None) -> str:

    if client_origin and client_origin.startswith("http"):

        return client_origin.rstrip("/")

    env = (os.environ.get("FRONTEND_URL") or os.environ.get("NEXT_PUBLIC_APP_URL") or "").strip().rstrip("/")

    return env or "http://localhost:3000"





async def _resolve_user_by_account_or_name(db, *, account_id: str, user_key: str):

    if user_key:

        user = await db.users.find_one(

            {"$or": [{"business_id": user_key}, {"_id": user_key}]},

            {"_id": 1},

        )

        if user:

            return user

    if account_id:

        return await db.users.find_one(

            {"unipile_connections.linkedin.account_id": str(account_id)},

            {"_id": 1},

        )

    return None


async def _get_or_create_linkedin_customer(
    db, user_id, participant_id: str, participant_name: str, conv_id: str
) -> dict:
    """Find or create a CRM customer record for a LinkedIn participant."""
    phone = f"linkedin_{participant_id}"
    customer = await db.customers.find_one({"user_id": user_id, "phone": phone})
    if customer:
        if customer.get("social_conversation_id") != conv_id:
            await db.customers.update_one(
                {"_id": customer["_id"]},
                {"$set": {"social_conversation_id": conv_id, "updated_at": datetime.utcnow()}},
            )
            customer["social_conversation_id"] = conv_id
        return customer

    now = datetime.utcnow()
    doc = {
        "user_id": user_id,
        "phone": phone,
        "name": participant_name or (f"LinkedIn User {str(participant_id)[-6:]}" if participant_id else "LinkedIn User"),
        "channel": "linkedin",
        "source": "linkedin",
        "linkedin_id": participant_id,
        "social_conversation_id": conv_id,
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "notes": "",
        "vip": False,
    }
    result = await db.customers.insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(f"[unipile] created linkedin customer {participant_id} for user {user_id}")
    return doc


async def save_incoming_unipile_message(db, user_id, customer_id, sender_provider_id: str, text: str, mid: str) -> None:
    """Save an inbound LinkedIn/Unipile message to the messages collection."""
    if not mid:
        return
    existing = await db.messages.find_one({"$or": [{"social_mid": mid}, {"unipile_mid": mid}]})
    if existing:
        return

    await db.messages.insert_one({
        "user_id": user_id,
        "customer_id": customer_id,
        "direction": "incoming",
        "content": text,
        "channel": "linkedin",
        "social_mid": mid,
        "unipile_mid": mid,
        "from_number": f"linkedin_{sender_provider_id}",
        "message_type": "text",
        "send_context": "incoming",
        "created_at": datetime.utcnow(),
    })


async def save_outgoing_unipile_message(db, user_id, customer_id, text: str) -> None:
    """Save an outbound LinkedIn/Unipile message reply to the messages collection."""
    await db.messages.insert_one({
        "user_id": user_id,
        "customer_id": customer_id,
        "direction": "outgoing",
        "content": text,
        "channel": "linkedin",
        "message_type": "text",
        "send_context": "auto_reply",
        "created_at": datetime.utcnow(),
    })


async def _process_unipile_linkedin_message(db, user: dict, payload: dict) -> None:
    """Asynchronously process an incoming LinkedIn/Unipile message and generate an AI auto-reply."""
    from autoreply.engine import process_message as ar_process

    sender_provider_id = payload.get("sender", {}).get("attendee_provider_id")
    account_user_id = payload.get("account_info", {}).get("user_id")

    if not sender_provider_id or not account_user_id:
        return
    if sender_provider_id == account_user_id:
        # Outbound message loop safety: ignore messages sent by us
        return

    text = (payload.get("message") or payload.get("text") or "").strip()
    if not text:
        return

    chat_id = payload.get("chat_id") or payload.get("chatId") or ""
    if not chat_id:
        return

    sender_name = payload.get("sender", {}).get("attendee_name") or f"LinkedIn User {str(sender_provider_id)[-6:]}"
    user_id = user["_id"]

    customer = await _get_or_create_linkedin_customer(db, user_id, sender_provider_id, sender_name, chat_id)
    if customer.get("auto_reply") is False:
        return

    mid = payload.get("message_id") or payload.get("messageId") or ""

    # Share dedup + daily cap with the 45s poller (social_autoreply) so the two paths never
    # double-reply, and the ban-risk cap is enforced no matter which path handles the message.
    from social_autoreply import (
        _bump_linkedin_daily_count,
        _linkedin_daily_count,
        MAX_LINKEDIN_AUTOREPLIES_PER_DAY,
    )
    if mid:
        st = await db.social_autoreply_state.find_one(
            {"user_id": user_id, "conversation_id": chat_id}
        )
        if st and st.get("last_handled_mid") == str(mid):
            return  # already answered (by the poller or a prior webhook delivery/retry)

    await save_incoming_unipile_message(db, user_id, customer["_id"], sender_provider_id, text, mid)

    try:
        from delegate.inbound_hooks import notify_delegate_inbound

        fresh = await db.customers.find_one({"_id": customer["_id"], "user_id": user_id})
        if fresh:
            await notify_delegate_inbound(
                db,
                user_id,
                fresh,
                text,
                message_id=str(mid) if mid else None,
            )
    except Exception as exc:
        logger.debug("[unipile] delegate inbound hook failed: %s", exc)

    business_id = str(user.get("business_id") or user_id)
    account_id = await resolve_linkedin_account_id(db, user_id, business_id)
    if not account_id:
        logger.warning("[unipile-autoreply] no account_id resolved for user=%s", user_id)
        return

    if await _linkedin_daily_count(db, user_id, account_id) >= MAX_LINKEDIN_AUTOREPLIES_PER_DAY:
        logger.info("[unipile-autoreply] LinkedIn daily cap reached for user=%s; skipping", user_id)
        return

    class _UnipileSender:
        async def send_message(self, user_id, to_number, message, customer_name="", send_context="auto_reply", **kwargs):
            import unipile_inbox
            res = await unipile_inbox.send_message(db, user_id, business_id, chat_id, account_id, message)
            if isinstance(res, dict) and (res.get("success") or res.get("data")) and not res.get("error"):
                await save_outgoing_unipile_message(db, user_id, customer["_id"], message)
                return True
            else:
                logger.error("[unipile-autoreply] send failed: %s", res.get("error") if isinstance(res, dict) else res)
                return False

    try:
        await ar_process(
            db=db,
            user=user,
            customer=customer,
            customer_id=customer["_id"],
            message=text,
            from_number=f"linkedin_{sender_provider_id}",
            whatsapp_service=_UnipileSender(),
        )
    except Exception as exc:
        logger.error("[unipile-autoreply] AutoReply error: %s", exc, exc_info=True)
        import unipile_inbox
        fallback = "Sorry, I'm having trouble right now. Please try again! 🙏"
        await unipile_inbox.send_message(db, user_id, business_id, chat_id, account_id, fallback)

    # Record handled in the shared state so the poller skips it, and count toward the cap.
    if mid:
        await db.social_autoreply_state.update_one(
            {"user_id": user_id, "conversation_id": chat_id},
            {"$set": {
                "user_id": user_id,
                "conversation_id": chat_id,
                "last_handled_mid": str(mid),
                "baseline_only": False,
                "updated_at": datetime.utcnow(),
            }},
            upsert=True,
        )
    await _bump_linkedin_daily_count(db, user_id, account_id)

    # Latency telemetry — end-to-end from when the contact's message was sent to our reply.
    try:
        from datetime import timezone as _tz
        raw_ts = payload.get("timestamp")
        if raw_ts:
            sent = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            secs = (datetime.now(_tz.utc) - sent).total_seconds()
            logger.info("[unipile-webhook] reply sent for chat=%s; end-to-end latency=%.1fs", chat_id, secs)
    except Exception:
        pass


async def _handle_message_event(db, payload: Dict[str, Any]) -> None:
    account_id = str(payload.get("account_id") or payload.get("accountId") or "")
    event = str(payload.get("event") or "").lower()
    user_key = str(payload.get("name") or payload.get("user_id") or "").strip()
    user = await _resolve_user_by_account_or_name(db, account_id=account_id, user_key=user_key)
    if not user:
        logger.info("[unipile] message webhook ignored — user not found for account=%s", account_id)
        return

    ts = payload.get("timestamp") or datetime.utcnow().isoformat()
    chat_id = str(payload.get("chat_id") or payload.get("chatId") or "")
    message_id = str(payload.get("message_id") or payload.get("messageId") or "")
    await db.unipile_message_events.insert_one({
        "user_id": user["_id"],
        "account_id": account_id,
        "event": event,
        "chat_id": chat_id,
        "message_id": message_id,
        "message": payload.get("message") or payload.get("text") or "",
        "sender": payload.get("sender") or {},
        "payload": payload,
        "created_at": datetime.utcnow(),
    })
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "unipile_connections.linkedin.last_message_at": ts,
                "unipile_connections.linkedin.last_webhook_event": event,
                "unipile_connections.linkedin.last_chat_id": chat_id,
            }
        },
    )

    if event == "message_received":
        full_user = await db.users.find_one({"_id": user["_id"]})
        if full_user:
            settings = full_user.get("settings") or {}
            # LinkedIn auto-reply has its own opt-in flag (distinct from Instagram's
            # social_dm_autoreply_enabled) because LinkedIn automation carries account risk.
            if settings.get("linkedin_dm_autoreply_enabled"):
                import asyncio
                asyncio.create_task(_process_unipile_linkedin_message(db, full_user, payload))





def make_unipile_router(db, user_dep):

    router = APIRouter(prefix="/unipile", tags=["unipile"])



    @router.get("/status")

    async def unipile_status(user=user_dep):

        business_id = str(user.get("business_id") or user["_id"])

        status = await get_connection_status(db, user["_id"], business_id)

        return status



    @router.post("/connect/linkedin/cookie")

    async def connect_linkedin_cookie(body: Dict[str, Any], user=user_dep):

        if not is_configured():

            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")



        business_id = str(user.get("business_id") or user["_id"])

        li_at = str(body.get("li_at") or body.get("access_token") or body.get("cookie") or "").strip()

        user_agent = str(body.get("user_agent") or "").strip() or None



        result = await connect_linkedin_with_cookie(

            business_id, li_at, user_agent=user_agent,

        )

        if result.get("error"):

            raise HTTPException(400, detail=result["error"])

        if result.get("checkpoint"):

            return result

        account_id = result.get("account_id")

        if account_id:

            await save_linkedin_account(

                db, user["_id"],

                account_id=str(account_id),

                account_name=str(result.get("name") or "LinkedIn"),

            )

            return {"success": True, "connected": True, "account_id": account_id}

        raise HTTPException(502, detail="Unipile did not return an account.")



    @router.post("/connect/linkedin/credentials")

    async def connect_linkedin_credentials(body: Dict[str, Any], user=user_dep):

        if not is_configured():

            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")



        business_id = str(user.get("business_id") or user["_id"])

        username = str(body.get("username") or body.get("email") or "").strip()

        password = str(body.get("password") or "")

        country = str(body.get("country") or "").strip() or None



        result = await connect_linkedin_with_credentials(

            business_id, username, password, country=country,

        )

        if result.get("error"):

            raise HTTPException(400, detail=result["error"])

        if result.get("checkpoint"):

            return result

        account_id = result.get("account_id")

        if account_id:

            await save_linkedin_account(

                db, user["_id"],

                account_id=str(account_id),

                account_name=str(result.get("name") or username),

            )

            return {"success": True, "connected": True, "account_id": account_id}

        raise HTTPException(502, detail="Unipile did not return an account.")



    @router.post("/connect/linkedin/checkpoint")

    async def connect_linkedin_checkpoint(body: Dict[str, Any], user=user_dep):

        if not is_configured():

            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")



        account_id = str(body.get("account_id") or "").strip()

        code = str(body.get("code") or body.get("verification_code") or "").strip()

        result = await solve_linkedin_checkpoint(account_id, code)

        if result.get("error"):

            raise HTTPException(400, detail=result["error"])

        if result.get("checkpoint"):

            return result

        if result.get("success") and result.get("account_id"):

            await save_linkedin_account(

                db, user["_id"],

                account_id=str(result["account_id"]),

                account_name=str(result.get("name") or "LinkedIn"),

            )

            return {"success": True, "connected": True, "account_id": result["account_id"]}

        raise HTTPException(502, detail="Checkpoint not resolved.")



    @router.post("/connect/linkedin/poll")

    async def connect_linkedin_poll(body: Dict[str, Any], user=user_dep):

        if not is_configured():

            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")



        account_id = str(body.get("account_id") or "").strip()

        result = await poll_linkedin_account(account_id)

        if result.get("error"):

            raise HTTPException(400, detail=result["error"])

        if result.get("pending"):

            return result

        if result.get("success") and result.get("account_id"):

            await save_linkedin_account(

                db, user["_id"],

                account_id=str(result["account_id"]),

                account_name=str(result.get("name") or "LinkedIn"),

            )

            return {"success": True, "connected": True, "account_id": result["account_id"]}

        raise HTTPException(502, detail="Account not ready yet.")



    @router.post("/connect/linkedin")

    async def connect_linkedin(request: Request, user=user_dep):

        if not is_configured():

            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")



        business_id = str(user.get("business_id") or user["_id"])

        client_origin: Optional[str] = None

        try:

            body = await request.json()

            if isinstance(body, dict):

                raw = body.get("redirect_base") or body.get("redirectBase")

                if isinstance(raw, str):

                    client_origin = raw

        except Exception:

            pass



        frontend = _frontend_base(client_origin)

        api_base = _api_public_base(request)

        # The unipile router is mounted under the /api prefix, so the webhook lives at
        # /api/unipile/webhook. Without /api, Unipile POSTs to a 404 and no event is delivered.
        notify_url = f"{api_base}/api/unipile/webhook"

        success_redirect = f"{frontend}/dashboard/integrations?connected=unipile-linkedin"



        result = await create_hosted_auth_link(

            business_id,

            notify_url=notify_url,

            success_redirect_url=success_redirect,

        )

        if result.get("error"):

            raise HTTPException(502, detail=result["error"])

        return {"authUrl": result.get("url"), "platform": "linkedin"}



    @router.delete("/connections/linkedin")

    async def disconnect_linkedin(user=user_dep):

        await clear_linkedin_account(db, user["_id"], delete_remote=True)

        return {"ok": True}



    @router.post("/webhook")

    async def unipile_webhook(payload: Dict[str, Any]):

        """Hosted-auth callback + real-time LinkedIn message events."""

        if not isinstance(payload, dict):

            return {"ok": True}



        event = str(payload.get("event") or "").lower()

        if event in _MESSAGE_EVENTS:

            logger.info(
                "[unipile-webhook] HIT event=%s chat=%s msg_id=%s msg_ts=%s recv=%s",
                event,
                payload.get("chat_id") or payload.get("chatId"),
                payload.get("message_id") or payload.get("messageId"),
                payload.get("timestamp"),
                datetime.utcnow().isoformat(),
            )

            try:

                await _handle_message_event(db, payload)

            except Exception as exc:

                logger.warning("[unipile] message webhook handler failed: %s", exc)

            return {"ok": True}



        status = str(payload.get("status") or payload.get("account_status") or "").upper()

        account_id = payload.get("account_id") or payload.get("accountId") or payload.get("id")

        user_key = str(payload.get("name") or payload.get("user_id") or payload.get("userId") or "").strip()



        if not account_id:

            return {"ok": True, "ignored": True}



        if status and status not in _AUTH_STATUSES:

            if status == "CREDENTIALS":

                user = await _resolve_user_by_account_or_name(

                    db, account_id=str(account_id), user_key=user_key,

                )

                if user:

                    await db.users.update_one(

                        {"_id": user["_id"]},

                        {"$set": {"unipile_connections.linkedin.needs_reconnect": True}},

                    )

            logger.info("[unipile] webhook ignored status=%s account=%s", status, account_id)

            return {"ok": True, "ignored": True}



        if not user_key and not account_id:

            return {"ok": True, "ignored": True}



        user = await _resolve_user_by_account_or_name(

            db, account_id=str(account_id), user_key=user_key,

        )

        if not user:

            logger.warning("[unipile] webhook user not found for name=%s account=%s", user_key, account_id)

            return {"ok": True, "user_missing": True}



        await save_linkedin_account(

            db,

            user["_id"],

            account_id=str(account_id),

            account_name=str(payload.get("username") or payload.get("provider_username") or "LinkedIn"),

        )

        await db.users.update_one(

            {"_id": user["_id"]},

            {"$unset": {"unipile_connections.linkedin.needs_reconnect": ""}},

        )

        logger.info("[unipile] linked LinkedIn account %s to user %s", account_id, user["_id"])

        return {"ok": True}

    @router.get("/linkedin/contracts")
    async def linkedin_contracts(user=user_dep):
        if not is_configured():
            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")
        business_id = str(user.get("business_id") or user["_id"])
        account_id = await resolve_linkedin_account_id(db, user["_id"], business_id)
        if not account_id:
            raise HTTPException(400, "LinkedIn is not connected.")
        result = await list_linkedin_contracts(account_id)
        if result.get("error"):
            raise HTTPException(502, detail=result["error"])
        stored = await get_stored_linkedin_account(db, user["_id"]) or {}
        return {
            "contracts": result.get("contracts") or [],
            "selected_contract_id": stored.get("contract_id"),
        }

    @router.post("/linkedin/contracts/select")
    async def linkedin_select_contract(body: Dict[str, Any], user=user_dep):
        if not is_configured():
            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")
        business_id = str(user.get("business_id") or user["_id"])
        account_id = await resolve_linkedin_account_id(db, user["_id"], business_id)
        if not account_id:
            raise HTTPException(400, "LinkedIn is not connected.")
        contract_id = str(body.get("contract_id") or body.get("id") or "").strip()
        if not contract_id:
            raise HTTPException(400, "contract_id is required.")
        result = await select_linkedin_contract(account_id, contract_id)
        if result.get("error"):
            raise HTTPException(400, detail=result["error"])
        contract_name = str(body.get("name") or body.get("contract_name") or "").strip()
        contract_product = str(body.get("product") or body.get("contract_product") or "").strip()
        if not contract_name or not contract_product:
            contracts_res = await list_linkedin_contracts(account_id)
            for c in contracts_res.get("contracts") or []:
                if isinstance(c, dict) and str(c.get("id")) == contract_id:
                    contract_name = contract_name or str(c.get("name") or "")
                    contract_product = contract_product or str(c.get("product") or "")
                    break
        await save_linkedin_contract(
            db,
            user["_id"],
            contract_id=contract_id,
            contract_name=contract_name,
            contract_product=contract_product,
        )
        return {"ok": True, "contract_id": contract_id, "contract_name": contract_name, "contract_product": contract_product}

    @router.get("/linkedin/inmail-balance")
    async def linkedin_inmail_balance(user=user_dep):
        if not is_configured():
            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")
        business_id = str(user.get("business_id") or user["_id"])
        account_id = await resolve_linkedin_account_id(db, user["_id"], business_id)
        if not account_id:
            raise HTTPException(400, "LinkedIn is not connected.")
        result = await get_inmail_balance(account_id)
        if result.get("error"):
            raise HTTPException(502, detail=result["error"])
        return result

    @router.post("/linkedin/inmail")
    async def linkedin_send_inmail(body: Dict[str, Any], user=user_dep):
        if not is_configured():
            raise HTTPException(503, "UNIPILE_API_KEY and UNIPILE_DSN must be configured on the server.")
        business_id = str(user.get("business_id") or user["_id"])
        account_id = await resolve_linkedin_account_id(db, user["_id"], business_id)
        if not account_id:
            raise HTTPException(400, "LinkedIn is not connected.")
        recipient = str(body.get("recipient") or body.get("recipient_id") or body.get("attendee_id") or "").strip()
        message = str(body.get("message") or body.get("text") or "").strip()
        subject = str(body.get("subject") or "").strip()
        linkedin_api = str(body.get("linkedin_api") or body.get("api") or "").strip() or None
        inmail = body.get("inmail")
        if inmail is None:
            inmail = True
        if not recipient:
            raise HTTPException(400, "recipient (LinkedIn provider id) is required.")
        if not message:
            raise HTTPException(400, "message is required.")
        result = await start_linkedin_chat(
            account_id,
            attendee_ids=[recipient],
            text=message,
            subject=subject or None,
            linkedin_api=linkedin_api,
            inmail=bool(inmail),
        )
        if result.get("error"):
            raise HTTPException(400, detail=result["error"])
        return {
            "status": "sent",
            "conversation_id": result.get("chat_id"),
            "chat_id": result.get("chat_id"),
            "message_id": result.get("message_id"),
        }

    return router


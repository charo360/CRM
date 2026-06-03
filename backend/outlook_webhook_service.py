"""
Outlook Webhook Integration Service.

Manages Microsoft Graph API webhook subscriptions for Outlook mailboxes,
renewals, and incoming push notifications using the Composio proxy.
"""

import logging
import uuid
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from composio_service import composio_proxy, get_connection_status, TOOLKIT_OUTLOOK
from email_sync import _shape_outlook_message, _store_messages

logger = logging.getLogger(__name__)


def _get_backend_public_url() -> str:
    """Resolve backend public URL for Outlook webhooks."""
    url = (
        os.environ.get("COMPOSIO_WEBHOOK_URL")
        or os.environ.get("BACKEND_PUBLIC_URL")
        or os.environ.get("NEXT_PUBLIC_API_URL", "").replace("/api", "")
        or "https://crm-1-pnfo.onrender.com"
    )
    # Ensure it ends up as f"{backend_url}/api/webhooks/outlook"
    # If the URL contains /api/webhooks/composio, map it correctly
    if "/api/webhooks" in url:
        base = url.split("/api/webhooks")[0]
        return f"{base.rstrip('/')}/api/webhooks/outlook"
    return f"{url.rstrip('/')}/api/webhooks/outlook"


async def create_outlook_subscription(user_id: str, db: Any) -> Dict[str, Any]:
    """
    Create a new Microsoft Graph subscription for Outlook Inbox changes.
    Max expiration for message resource is 4230 minutes (2.9 days). We use 2 days.
    """
    logger.info(f"[outlook_webhook] Attempting to create subscription for user_id: {user_id}")
    
    # 1. Check connection status
    status = await get_connection_status(user_id, TOOLKIT_OUTLOOK)
    if not status.get("connected"):
        logger.warning(f"[outlook_webhook] User {user_id} is not connected to Outlook")
        return {"error": "Outlook not connected"}

    # 2. Setup subscription params
    client_state = uuid.uuid4().hex
    expiration_dt = datetime.now(timezone.utc) + timedelta(days=2)
    # Graph API requires ISO format: YYYY-MM-DDTHH:mm:ss.sssZ
    expiration_iso = expiration_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    notification_url = _get_backend_public_url()

    payload = {
        "changeType": "created",
        "notificationUrl": notification_url,
        "resource": "me/mailFolders('Inbox')/messages",
        "expirationDateTime": expiration_iso,
        "clientState": client_state
    }

    try:
        # 3. Request subscription creation via Composio Graph Proxy
        response = await composio_proxy(
            user_id=user_id,
            toolkit=TOOLKIT_OUTLOOK,
            method="POST",
            path="/v1.0/subscriptions",
            json=payload
        )

        if "error" in response:
            logger.error(f"[outlook_webhook] Graph API error creating subscription for {user_id}: {response['error']}")
            return {"error": response["error"]}

        sub_id = response.get("id")
        if not sub_id:
            logger.error(f"[outlook_webhook] Subscription creation returned no ID for {user_id}. Response: {response}")
            return {"error": "No subscription ID returned"}

        # 4. Save metadata to DB (email_sync_status collection)
        await db.email_sync_status.update_one(
            {"user_id": user_id},
            {"$set": {
                "outlook_subscription_id": sub_id,
                "outlook_subscription_expiration": expiration_dt,
                "outlook_client_state": client_state,
                "outlook_sync_enabled": True,
                "updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )

        logger.info(f"✅ [outlook_webhook] Created subscription {sub_id} for user {user_id} expiring {expiration_iso}")
        return {"success": True, "subscription_id": sub_id}

    except Exception as e:
        logger.exception(f"[outlook_webhook] Failed to create subscription for user {user_id}: {e}")
        return {"error": str(e)}


async def renew_outlook_subscriptions(db: Any) -> Dict[str, Any]:
    """
    Periodic job that renews Outlook subscriptions nearing expiration (expires in < 12 hours).
    If renewal fails or subscription expired, it will re-create a new one from scratch.
    """
    logger.info("[outlook_webhook] Starting periodic subscription renewal job...")
    now = datetime.now(timezone.utc)
    threshold = now + timedelta(hours=12)

    # Find active subscriptions expiring soon
    cursor = db.email_sync_status.find({
        "outlook_subscription_id": {"$exists": True, "$ne": None},
        "outlook_subscription_expiration": {"$lt": threshold},
        "outlook_sync_enabled": {"$ne": False}
    })
    soon_expiring = await cursor.to_list(1000)

    renewed = 0
    recreated = 0
    failed = 0

    for status_doc in soon_expiring:
        user_id = status_doc["user_id"]
        sub_id = status_doc["outlook_subscription_id"]
        expiration_dt = status_doc.get("outlook_subscription_expiration")
        
        # Check connection status first
        conn = await get_connection_status(user_id, TOOLKIT_OUTLOOK)
        if not conn.get("connected"):
            logger.warning(f"[outlook_webhook] Skipping renewal for {user_id} - Outlook is no longer connected")
            continue

        # If completely expired, just recreate it directly
        if expiration_dt and expiration_dt < now:
            logger.info(f"[outlook_webhook] Subscription {sub_id} completely expired for user {user_id}. Recreating...")
            res = await create_outlook_subscription(user_id, db)
            if "success" in res:
                recreated += 1
            else:
                failed += 1
            continue

        # Attempt renewal PATCH
        new_expiration_dt = now + timedelta(days=2)
        new_expiration_iso = new_expiration_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        try:
            response = await composio_proxy(
                user_id=user_id,
                toolkit=TOOLKIT_OUTLOOK,
                method="PATCH",
                path=f"/v1.0/subscriptions/{sub_id}",
                json={"expirationDateTime": new_expiration_iso}
            )

            if "error" not in response:
                await db.email_sync_status.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "outlook_subscription_expiration": new_expiration_dt,
                        "updated_at": now
                    }}
                )
                logger.info(f"✅ [outlook_webhook] Renewed subscription {sub_id} for user {user_id} until {new_expiration_iso}")
                renewed += 1
            else:
                # If PATCH failed because subscription is missing/invalid, recreate it
                logger.warning(f"[outlook_webhook] Renewal PATCH failed for {sub_id} ({user_id}): {response['error']}. Recreating...")
                res = await create_outlook_subscription(user_id, db)
                if "success" in res:
                    recreated += 1
                else:
                    failed += 1

        except Exception as e:
            logger.exception(f"[outlook_webhook] Error renewing subscription {sub_id} for user {user_id}: {e}")
            failed += 1

    result = {"renewed": renewed, "recreated": recreated, "failed": failed}
    logger.info(f"[outlook_webhook] Subscription renewal job finished: {result}")
    return result


async def handle_outlook_notification(payload: Dict[str, Any], db: Any) -> Dict[str, Any]:
    """
    Handle incoming notifications from Microsoft Graph.
    Checks clientState, retrieves message, parses, and pushes to db + Zilo.
    """
    notifications = payload.get("value", [])
    if not notifications:
        return {"status": "ignored", "reason": "empty payload"}

    processed_count = 0
    errors = []

    for item in notifications:
        sub_id = item.get("subscriptionId")
        client_state = item.get("clientState")
        resource = item.get("resource", "")

        if not sub_id or not client_state:
            continue

        # 1. Match subscription in MongoDB to find user_id
        status_doc = await db.email_sync_status.find_one({
            "outlook_subscription_id": sub_id,
            "outlook_client_state": client_state
        })

        if not status_doc:
            logger.warning(f"[outlook_webhook] Received notification with unrecognized subscriptionId: {sub_id} or clientState: {client_state}")
            continue

        user_id = status_doc["user_id"]
        
        # 2. Extract Message ID
        msg_id = (item.get("resourceData") or {}).get("id")
        if not msg_id and "Messages/" in resource:
            # Fallback: extract message ID from resource string (e.g. "Users/guid/Messages/msg-guid")
            parts = resource.split("Messages/")
            if len(parts) > 1:
                msg_id = parts[1].split("/")[0]

        if not msg_id:
            logger.warning(f"[outlook_webhook] Unrecognized resource path format: {resource}")
            continue

        logger.info(f"📧 [outlook_webhook] Processing notification for user {user_id}, Message ID: {msg_id}")

        try:
            # 3. Retrieve full message details from Graph API via Composio Proxy
            message = await composio_proxy(
                user_id=user_id,
                toolkit=TOOLKIT_OUTLOOK,
                method="GET",
                path=f"/v1.0/me/messages/{msg_id}"
            )

            if "error" in message:
                logger.error(f"[outlook_webhook] Failed to retrieve message details for {msg_id}: {message['error']}")
                errors.append(message["error"])
                continue

            # 4. Shape & store the message in MongoDB
            shaped_msg = _shape_outlook_message(message, user_id)
            result = await _store_messages(user_id, db, [shaped_msg], pre_shaped=True)
            synced_count = result.get("synced_messages", 0)

            logger.info(f"✅ [outlook_webhook] Stored {synced_count} Outlook message for user {user_id}")
            processed_count += synced_count

            # 5. Trigger classification
            try:
                from email_classifier import get_email_classifier
                await get_email_classifier(db).classify_new_emails(user_id)
            except Exception as class_err:
                logger.warning(f"[outlook_webhook] Contact classification error: {class_err}")

            # 6. Trigger Zilo briefing ingest refresh
            try:
                user_doc = await db.users.find_one({"_id": user_id})
                if not user_doc:
                    user_doc = await db.users.find_one({"business_id": user_id})
                
                if user_doc:
                    from rex.integrations.briefing_refresh import ingest_crm_signals_into_briefing
                    await ingest_crm_signals_into_briefing(db, user_doc)
            except Exception as zilo_err:
                logger.warning(f"[outlook_webhook] Zilo briefing ingest error: {zilo_err}")

        except Exception as e:
            logger.exception(f"[outlook_webhook] Failed to process message {msg_id} for user {user_id}: {e}")
            errors.append(str(e))

    return {
        "status": "processed",
        "processed_messages": processed_count,
        "errors": errors
    }

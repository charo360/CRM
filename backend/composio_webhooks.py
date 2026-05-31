"""
Composio Webhook Handler for Gmail Real-Time Notifications.

Handles:
1. Receiving webhook events from Composio
2. Processing GMAIL_NEW_GMAIL_MESSAGE triggers
3. Syncing new emails to MongoDB
"""
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def verify_composio_webhook(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify Composio webhook signature.
    
    Args:
        payload: Raw request body bytes
        signature: X-Composio-Signature header value
        secret: Webhook secret from Composio
    
    Returns:
        True if signature is valid
    """
    if not secret or not signature:
        return False
    
    # Composio uses HMAC-SHA256. Some providers prefix with "sha256=".
    normalized_sig = (signature or "").strip()
    if normalized_sig.lower().startswith("sha256="):
        normalized_sig = normalized_sig.split("=", 1)[1].strip()

    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(normalized_sig, expected_signature)


def _extract_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize Composio webhook payloads to a single event shape.
    Handles:
      - direct event payloads
      - {"data": {...}}
      - {"event": {...}}
      - {"events": [{...}]}
    """
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("trigger_name"), str):
        return payload
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload.get("event"), dict):
        return payload["event"]
    events = payload.get("events")
    if isinstance(events, list) and events and isinstance(events[0], dict):
        return events[0]
    return payload


def _extract_trigger_name(event: Dict[str, Any]) -> str:
    return str(
        event.get("trigger_name")
        or event.get("triggerName")
        or event.get("name")
        or event.get("event")
        or ""
    ).strip()


def _extract_connected_account_id(event: Dict[str, Any], body: Dict[str, Any]) -> str:
    return str(
        event.get("connected_account_id")
        or event.get("connectedAccountId")
        or body.get("connected_account_id")
        or body.get("connectedAccountId")
        or ""
    ).strip()


def _extract_user_hint(event: Dict[str, Any], body: Dict[str, Any]) -> str:
    return str(
        event.get("user_id")
        or event.get("userId")
        or event.get("composio_user_id")
        or event.get("composioUserId")
        or body.get("user_id")
        or body.get("userId")
        or ""
    ).strip()


async def _resolve_user_for_event(
    db: Any,
    connected_account_id: str,
    user_hint: str,
) -> Optional[Dict[str, Any]]:
    """
    Find the user document for a Composio webhook using best-effort lookups.
    """
    if connected_account_id:
        user = await db.users.find_one({
            "$or": [
                {"composio_connections.gmail.connected_account_id": connected_account_id},
                {"composio_connections.gmail.connectedAccountId": connected_account_id},
                {"composio_connections.google_mail.connected_account_id": connected_account_id},
                {"composio_connections.google_mail.connectedAccountId": connected_account_id},
            ]
        })
        if user:
            return user
    if user_hint:
        # Composio user IDs in this app often align with business_id (string UUID)
        user = await db.users.find_one({
            "$or": [
                {"business_id": user_hint},
                {"_id": user_hint},
            ]
        })
        if user:
            return user
    return None


async def process_gmail_trigger(event: Dict[str, Any], db: Any) -> Dict[str, Any]:
    """
    Process GMAIL_NEW_GMAIL_MESSAGE trigger event.
    
    Event payload structure:
    {
        "trigger_id": "...",
        "trigger_name": "GMAIL_NEW_GMAIL_MESSAGE",
        "connected_account_id": "...",
        "payload": {
            "threadId": "...",
            "messageText": "...",
            "sender": "...",
            "subject": "...",
            "messageId": "...",
            ...
        }
    }
    """
    try:
        trigger_name = _extract_trigger_name(event).upper()
        if trigger_name != "GMAIL_NEW_GMAIL_MESSAGE":
            logger.warning(f"Unexpected trigger type: {trigger_name}")
            return {"error": "Unsupported trigger type"}

        payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
        connected_account_id = _extract_connected_account_id(event, payload)
        user_hint = _extract_user_hint(event, payload)
        
        thread_id = payload.get("threadId")
        message_text = payload.get("messageText")
        sender = payload.get("sender")
        subject = payload.get("subject")
        message_id = payload.get("messageId")
        
        logger.info(f"📧 Gmail trigger: {sender} - {subject}")
        
        # Resolve target user from connected account id (preferred) or user hints.
        user = await _resolve_user_for_event(db, connected_account_id, user_hint)
        
        if not user:
            # Fallback: try to find by any Gmail connection
            logger.warning(
                "User not found for webhook event (connected_account_id=%s, user_hint=%s)",
                connected_account_id,
                user_hint,
            )
            # We'll still process it by fetching the full message via Composio
            return {"error": "User not found"}
        
        user_id = str(user.get("business_id") or user["_id"])
        
        # Webhook payload shape can vary; safest path is to run the existing quick
        # sync pipeline that normalizes + stores Gmail/Outlook into email_db.
        try:
            from email_sync import sync_emails_for_user
            result = await sync_emails_for_user(user_id, db, max_results=10, trigger_briefing_ingest=True)
            logger.info(
                "✅ Gmail webhook sync for %s → threads=%s messages=%s",
                user.get("email", user_id),
                result.get("synced_threads", 0),
                result.get("synced_messages", 0),
            )
            return {
                "success": True,
                "synced_threads": result.get("synced_threads", 0),
                "synced_messages": result.get("synced_messages", 0),
                "message_id": message_id,
                "thread_id": thread_id,
            }
        except Exception as e:
            logger.error(f"Error syncing after Gmail webhook: {e}", exc_info=True)
            return {"error": str(e)}
        
    except Exception as e:
        logger.error(f"Error processing Gmail trigger: {e}")
        return {"error": str(e)}


async def handle_composio_webhook(payload: Dict[str, Any], db: Any) -> Dict[str, Any]:
    """
    Main webhook handler for all Composio events.
    
    Routes different trigger types to appropriate handlers.
    """
    event = _extract_event(payload)
    trigger_name = _extract_trigger_name(event).upper()

    if trigger_name == "GMAIL_NEW_GMAIL_MESSAGE":
        return await process_gmail_trigger(event, db)
    else:
        logger.warning(f"Unhandled trigger type: {trigger_name}")
        return {"error": f"Unhandled trigger: {trigger_name}"}

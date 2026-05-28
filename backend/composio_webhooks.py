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
from typing import Any, Dict
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
    
    # Composio uses HMAC-SHA256
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


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
        trigger_name = event.get("trigger_name")
        if trigger_name != "GMAIL_NEW_GMAIL_MESSAGE":
            logger.warning(f"Unexpected trigger type: {trigger_name}")
            return {"error": "Unsupported trigger type"}
        
        connected_account_id = event.get("connected_account_id")
        payload = event.get("payload", {})
        
        thread_id = payload.get("threadId")
        message_text = payload.get("messageText")
        sender = payload.get("sender")
        subject = payload.get("subject")
        message_id = payload.get("messageId")
        
        logger.info(f"📧 Gmail trigger: {sender} - {subject}")
        
        # Find user by connected_account_id
        # Composio stores this in user's composio_connections
        user = await db.users.find_one({
            "composio_connections.gmail.connected_account_id": connected_account_id
        })
        
        if not user:
            # Fallback: try to find by any Gmail connection
            logger.warning(f"User not found for connected_account_id: {connected_account_id}")
            # We'll still process it by fetching the full message via Composio
            return {"error": "User not found"}
        
        user_id = str(user.get("business_id") or user["_id"])
        
        # Webhook payload shape can vary; safest path is to run the existing quick
        # sync pipeline that normalizes + stores Gmail/Outlook into email_db.
        try:
            from email_sync import sync_emails_for_user
            result = await sync_emails_for_user(user_id, db, max_results=10)
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
    trigger_name = payload.get("trigger_name", "")
    
    if trigger_name == "GMAIL_NEW_GMAIL_MESSAGE":
        return await process_gmail_trigger(payload, db)
    else:
        logger.warning(f"Unhandled trigger type: {trigger_name}")
        return {"error": f"Unhandled trigger: {trigger_name}"}

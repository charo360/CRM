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
        
        # Fetch full message details via Composio
        from composio_service import composio_proxy
        
        try:
            # Get full message from Gmail API
            message_response = await composio_proxy(
                user_id,
                "gmail",
                "GET",
                f"gmail/v1/users/me/messages/{message_id}?format=full"
            )
            
            if "error" not in message_response:
                # Store in MongoDB using existing email_sync logic
                from email_sync import _store_messages
                
                result = await _store_messages(user_id, db, [message_response])
                
                logger.info(f"✅ Stored {result.get('synced_messages', 0)} message(s) for {user.get('email', user_id)}")
                
                # Trigger email classification
                from email_classifier import get_email_classifier
                await get_email_classifier(db).classify_new_emails(user_id)
                
                return {
                    "success": True,
                    "synced_messages": result.get("synced_messages", 0)
                }
            else:
                logger.error(f"Failed to fetch message {message_id}: {message_response['error']}")
                return {"error": message_response["error"]}
                
        except Exception as e:
            logger.error(f"Error fetching message via Composio: {e}")
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

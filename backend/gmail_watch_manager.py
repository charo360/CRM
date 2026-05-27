"""
Gmail Watch Manager - Registers and renews Gmail push notifications.

Handles:
1. Registering Gmail watch for newly connected accounts
2. Renewing watches before they expire (7 day max lifetime)
3. Storing watch state in MongoDB
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

PROJECT_ID = "zilocrm"
TOPIC_NAME = f"projects/{PROJECT_ID}/topics/gmail-notifications"

async def register_gmail_watch(user_id: str, db: Any) -> Dict[str, Any]:
    """
    Register Gmail push notifications for a user.
    Must be called after user connects Gmail via Composio.
    """
    from composio_service import composio_proxy
    
    try:
        # Call Gmail API users.watch()
        response = await composio_proxy(
            user_id,
            "gmail",
            "POST",
            "gmail/v1/users/me/watch",
            json={
                "topicName": TOPIC_NAME,
                "labelIds": ["INBOX"],
                "labelFilterBehavior": "INCLUDE"
            }
        )
        
        if "error" in response:
            logger.error(f"Failed to register Gmail watch for user {user_id}: {response['error']}")
            return {"error": response["error"]}
        
        history_id = response.get("historyId")
        expiration = response.get("expiration")  # Unix timestamp in milliseconds
        
        if not history_id or not expiration:
            logger.error(f"Invalid watch response for user {user_id}: {response}")
            return {"error": "Invalid watch response"}
        
        # Convert expiration to datetime
        expiration_dt = datetime.fromtimestamp(int(expiration) / 1000, tz=timezone.utc)
        
        # Store watch state in DB
        await db.email_sync_status.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "gmail_watch_expiration": expiration_dt,
                    "gmail_history_id": history_id,
                    "gmail_watch_registered_at": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        logger.info(f"✅ Registered Gmail watch for user {user_id}, expires at {expiration_dt}")
        
        return {
            "success": True,
            "historyId": history_id,
            "expiration": expiration_dt.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Exception registering Gmail watch for user {user_id}: {e}")
        return {"error": str(e)}


async def renew_gmail_watch(user_id: str, db: Any) -> Dict[str, Any]:
    """
    Renew Gmail watch for a user (same as registering, but updates existing).
    """
    logger.info(f"Renewing Gmail watch for user {user_id}")
    return await register_gmail_watch(user_id, db)


async def renew_expiring_watches(db: Any):
    """
    Find all Gmail watches expiring in the next 24 hours and renew them.
    Should be run daily as a scheduled job.
    """
    now = datetime.now(timezone.utc)
    threshold = now + timedelta(hours=24)
    
    # Find users with watches expiring soon
    expiring_watches = await db.email_sync_status.find({
        "gmail_watch_expiration": {"$lt": threshold, "$gt": now}
    }).to_list(length=1000)
    
    logger.info(f"Found {len(expiring_watches)} Gmail watches expiring in next 24h")
    
    renewed = 0
    failed = 0
    
    for watch in expiring_watches:
        user_id = watch["user_id"]
        try:
            result = await renew_gmail_watch(user_id, db)
            if "error" not in result:
                renewed += 1
            else:
                failed += 1
                logger.error(f"Failed to renew watch for user {user_id}: {result['error']}")
        except Exception as e:
            failed += 1
            logger.error(f"Exception renewing watch for user {user_id}: {e}")
    
    logger.info(f"Watch renewal complete: {renewed} renewed, {failed} failed")
    
    return {"renewed": renewed, "failed": failed}


async def stop_gmail_watch(user_id: str) -> Dict[str, Any]:
    """
    Stop Gmail push notifications for a user (called when disconnecting Gmail).
    """
    from composio_service import composio_proxy
    
    try:
        response = await composio_proxy(
            user_id,
            "gmail",
            "POST",
            "gmail/v1/users/me/stop"
        )
        
        if "error" in response:
            logger.error(f"Failed to stop Gmail watch for user {user_id}: {response['error']}")
            return {"error": response["error"]}
        
        logger.info(f"✅ Stopped Gmail watch for user {user_id}")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Exception stopping Gmail watch for user {user_id}: {e}")
        return {"error": str(e)}

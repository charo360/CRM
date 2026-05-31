"""
Gmail Webhook Listener - Pulls notifications from Google Cloud Pub/Sub.

This background worker:
1. Pulls messages from Pub/Sub subscription
2. Decodes Gmail notification data
3. Triggers incremental email sync for affected users
4. Acknowledges processed messages
"""
import asyncio
import base64
import json
import logging
import os
from concurrent.futures import TimeoutError
from google.cloud import pubsub_v1
from typing import Any, Dict

logger = logging.getLogger(__name__)

PROJECT_ID = "zilocrm"
SUBSCRIPTION_ID = "gmail-notifications-pull"
PULL_TIMEOUT = 10.0  # seconds

class GmailWebhookListener:
    """Listens to Gmail push notifications via Pub/Sub."""
    
    def __init__(self, db):
        self.db = db
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)
        self.running = False
    
    def decode_notification(self, message: pubsub_v1.types.PubsubMessage) -> Dict[str, Any]:
        """Decode Pub/Sub message to extract Gmail notification data."""
        try:
            # Pub/Sub message data is base64 encoded JSON
            data = base64.b64decode(message.data).decode('utf-8')
            notification = json.loads(data)
            
            # Gmail notification format:
            # {
            #   "emailAddress": "user@example.com",
            #   "historyId": "1234567890"
            # }
            return notification
        except Exception as e:
            logger.error(f"Failed to decode notification: {e}")
            return {}
    
    async def process_notification(self, notification: Dict[str, Any]):
        """Process a Gmail notification by triggering incremental sync."""
        email_address = notification.get("emailAddress")
        history_id = notification.get("historyId")
        
        if not email_address or not history_id:
            logger.warning(f"Invalid notification: {notification}")
            return
        
        logger.info(f"📧 Gmail notification: {email_address} @ historyId {history_id}")
        
        # Find user by email
        user = await self.db.users.find_one({"email": email_address})
        if not user:
            logger.warning(f"User not found for email: {email_address}")
            return
        
        user_id = str(user["_id"])
        
        # Trigger incremental sync
        from email_sync import sync_gmail_history
        try:
            result = await sync_gmail_history(user_id, history_id, self.db)
            logger.info(f"✅ Synced {result.get('new_messages', 0)} new messages for {email_address}")
            if result.get("new_messages", 0) > 0:
                try:
                    from rex.integrations.briefing_refresh import ingest_crm_signals_into_briefing
                    await ingest_crm_signals_into_briefing(self.db, user)
                except Exception as zilo_err:
                    logger.warning("[zilo] post-gmail briefing ingest: %s", zilo_err)
        except Exception as e:
            logger.error(f"Failed to sync Gmail history for {email_address}: {e}")
    
    def callback(self, message: pubsub_v1.types.PubsubMessage):
        """Callback for each Pub/Sub message (runs in thread pool)."""
        try:
            notification = self.decode_notification(message)
            if notification:
                # Run async processing in event loop
                asyncio.run(self.process_notification(notification))
            
            # Acknowledge the message
            message.ack()
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Don't ack - message will be redelivered
            message.nack()
    
    def start(self):
        """Start listening for Pub/Sub messages."""
        logger.info(f"🚀 Starting Gmail webhook listener on {self.subscription_path}")
        self.running = True
        
        # Subscribe with callback
        streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path,
            callback=self.callback
        )
        
        logger.info("✅ Listening for Gmail notifications...")
        
        try:
            # Block until stopped
            streaming_pull_future.result()
        except TimeoutError:
            streaming_pull_future.cancel()
            streaming_pull_future.result()
        except KeyboardInterrupt:
            logger.info("Stopping listener...")
            streaming_pull_future.cancel()
    
    def stop(self):
        """Stop the listener."""
        self.running = False
        logger.info("Listener stopped")


async def start_gmail_listener(db):
    """Start the Gmail webhook listener in background."""
    listener = GmailWebhookListener(db)
    
    # Run in background thread to not block FastAPI
    import threading
    thread = threading.Thread(target=listener.start, daemon=True)
    thread.start()
    
    logger.info("Gmail webhook listener started in background")
    return listener

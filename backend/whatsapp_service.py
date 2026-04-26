"""
WhatsApp Service
Handles sending messages and auto-creating contacts
"""
import os
import logging
from datetime import datetime
from twilio.rest import Client
from typing import Dict, Optional
import uuid

logger = logging.getLogger(__name__)

class WhatsAppService:
    """Service for WhatsApp messaging with auto-contact creation"""
    
    def __init__(self, db):
        self.db = db
        self.account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        self.auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        self.from_number = os.environ.get('TWILIO_PHONE_NUMBER', '')
        
        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None
            logger.warning("Twilio credentials not configured")
    
    async def send_message(
        self,
        user_id: str,
        to_number: str,
        message: str,
        customer_name: Optional[str] = None
    ) -> Dict:
        """
        Send WhatsApp message and auto-create contact if needed
        
        Args:
            user_id: Business owner's user ID
            to_number: Customer's phone number
            message: Message to send
            customer_name: Optional customer name (if known)
        
        Returns:
            Dict with status, customer_id, and message_id
        """
        try:
            # Step 1: Check if customer exists, create if not
            customer = await self.db.customers.find_one({
                "user_id": user_id,
                "phone_number": to_number
            })
            
            customer_id = None
            created_new = False
            
            if customer:
                customer_id = customer["_id"]
                logger.info(f"Found existing customer: {customer['name']}")
            else:
                # Auto-create customer when business initiates contact
                customer_id = str(uuid.uuid4())
                new_customer_name = customer_name if customer_name else f"Customer {to_number[-4:]}"
                
                await self.db.customers.insert_one({
                    "_id": customer_id,
                    "user_id": user_id,
                    "name": new_customer_name,
                    "phone_number": to_number,
                    "notes": "Auto-created when business sent message",
                    "tags": ["New"],
                    "last_contacted": datetime.utcnow(),
                    "created_at": datetime.utcnow(),
                    "auto_created": False,  # Business initiated, not customer
                    "business_initiated": True  # Business reached out first
                })
                created_new = True
                logger.info(f"Auto-created customer: {new_customer_name} ({to_number})")
            
            # Step 2: Store message in database
            message_id = str(uuid.uuid4())
            await self.db.messages.insert_one({
                "_id": message_id,
                "customer_id": customer_id,
                "user_id": user_id,
                "direction": "outgoing",
                "content": message,
                "message_type": "text",
                "from_number": self.from_number,
                "to_number": to_number,
                "created_at": datetime.utcnow()
            })
            
            # Step 3: Update customer's last_contacted
            await self.db.customers.update_one(
                {"_id": customer_id},
                {"$set": {"last_contacted": datetime.utcnow()}}
            )
            
            # Step 4: Send via Twilio (if configured)
            twilio_sid = None
            if self.client and self.from_number:
                try:
                    # Format numbers for WhatsApp
                    from_whatsapp = f"whatsapp:{self.from_number}"
                    to_whatsapp = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
                    
                    twilio_message = self.client.messages.create(
                        from_=from_whatsapp,
                        body=message,
                        to=to_whatsapp
                    )
                    twilio_sid = twilio_message.sid
                    logger.info(f"Sent WhatsApp message: {twilio_sid}")
                except Exception as e:
                    logger.error(f"Failed to send via Twilio: {e}")
                    # Continue anyway - message is stored in DB
            
            return {
                "status": "success",
                "customer_id": customer_id,
                "message_id": message_id,
                "twilio_sid": twilio_sid,
                "created_new_contact": created_new,
                "customer_name": new_customer_name if created_new else customer["name"]
            }
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise

# Singleton instance
_whatsapp_service = None

def get_whatsapp_service(db):
    """Get singleton instance"""
    global _whatsapp_service
    if _whatsapp_service is None:
        _whatsapp_service = WhatsAppService(db)
    return _whatsapp_service

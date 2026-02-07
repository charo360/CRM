"""
WhatsApp Service — Evolution API Integration
Multi-tenant WhatsApp gateway using Evolution API with pairing code auth.
Each user gets their own Evolution API instance linked to their WhatsApp number.
"""
import os
import logging
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import uuid

logger = logging.getLogger(__name__)

# Evolution API config
EVOLUTION_API_URL = os.environ.get('EVOLUTION_API_URL', 'http://localhost:8080')
EVOLUTION_API_KEY = os.environ.get('EVOLUTION_API_KEY', '')

# Message limits per subscription plan (monthly)
PLAN_MESSAGE_LIMITS = {
    "free": 50,
    "starter": 500,
    "standard": 2000,
    "pro": 10000,
}

# Rate limiting
DAILY_MESSAGE_LIMIT = 500  # Max messages per user per day (WhatsApp safety)
BROADCAST_COOLDOWN_HOURS = 24  # Min hours between broadcasts


class WhatsAppService:
    """Multi-tenant WhatsApp service via Evolution API"""

    def __init__(self, db):
        self.db = db
        self.base_url = EVOLUTION_API_URL.rstrip('/')
        self.api_key = EVOLUTION_API_KEY
        self._broadcast_queues: Dict[str, asyncio.Queue] = {}
        self._broadcast_tasks: Dict[str, asyncio.Task] = {}

    def _headers(self) -> Dict:
        return {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

    def _instance_name(self, user_id: str) -> str:
        """Generate a unique instance name for a user"""
        return f"user_{user_id.replace('-', '_')}"

    # ============ INSTANCE MANAGEMENT ============

    async def create_instance(self, user_id: str, phone_number: str) -> Dict:
        """
        Create an Evolution API instance for a user and request a pairing code.
        Returns the 8-digit pairing code for the user to enter in WhatsApp.
        """
        instance_name = self._instance_name(user_id)
        # Strip + and any non-digit chars for Evolution API
        clean_number = phone_number.lstrip('+').replace(' ', '').replace('-', '')

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Step 1: Create instance
                create_payload = {
                    "instanceName": instance_name,
                    "token": str(uuid.uuid4()),
                    "number": clean_number,
                    "integration": "WHATSAPP-BAILEYS",
                    "reject_call": False,
                    "groupsIgnore": True,
                }

                create_resp = await client.post(
                    f"{self.base_url}/instance/create",
                    json=create_payload,
                    headers=self._headers(),
                )

                if create_resp.status_code not in (200, 201):
                    error_detail = create_resp.text
                    # Instance might already exist — try to connect anyway
                    if "already" in error_detail.lower() or "exists" in error_detail.lower():
                        logger.info(f"Instance {instance_name} already exists, requesting new pairing code")
                    else:
                        logger.error(f"Failed to create instance: {error_detail}")
                        return {"status": "error", "message": f"Failed to create WhatsApp instance: {error_detail}"}

                # Step 2: Request pairing code
                code_resp = await client.get(
                    f"{self.base_url}/instance/connect/{instance_name}",
                    params={"number": clean_number},
                    headers=self._headers(),
                )

                if code_resp.status_code != 200:
                    logger.error(f"Failed to get pairing code: {code_resp.text}")
                    return {"status": "error", "message": "Failed to generate pairing code"}

                code_data = code_resp.json()
                pairing_code = code_data.get("code") or code_data.get("pairingCode", "")

                # Step 3: Store instance info in user record
                await self.db.users.update_one(
                    {"_id": user_id},
                    {"$set": {
                        "whatsapp.number": phone_number,
                        "whatsapp.instance_name": instance_name,
                        "whatsapp.status": "pairing",
                        "whatsapp.pairing_code": pairing_code,
                        "whatsapp.created_at": datetime.utcnow(),
                    }}
                )

                logger.info(f"Created instance {instance_name} for user {user_id}, pairing code: {pairing_code}")
                return {
                    "status": "pairing",
                    "pairing_code": pairing_code,
                    "instance_name": instance_name,
                    "message": "Enter this code in WhatsApp > Linked Devices > Link with phone number",
                }

        except httpx.ConnectError:
            logger.error("Cannot connect to Evolution API — is it running?")
            return {"status": "error", "message": "WhatsApp service is not available. Please try again later."}
        except Exception as e:
            logger.error(f"Error creating instance: {e}")
            return {"status": "error", "message": str(e)}

    async def get_instance_status(self, user_id: str) -> Dict:
        """Check the connection status of a user's WhatsApp instance"""
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        wa = user.get("whatsapp") if user else None

        if not wa or not wa.get("instance_name"):
            return {"connected": False, "status": "not_connected"}

        instance_name = wa["instance_name"]

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/instance/connectionState/{instance_name}",
                    headers=self._headers(),
                )

                if resp.status_code == 200:
                    data = resp.json()
                    state = data.get("instance", {}).get("state", "close")
                    is_open = state == "open"

                    # Update DB if status changed
                    new_status = "connected" if is_open else "disconnected"
                    if wa.get("status") != new_status:
                        await self.db.users.update_one(
                            {"_id": user_id},
                            {"$set": {"whatsapp.status": new_status}}
                        )

                    return {
                        "connected": is_open,
                        "status": new_status,
                        "number": wa.get("number"),
                        "instance_name": instance_name,
                    }
                else:
                    return {"connected": False, "status": "unknown", "number": wa.get("number")}

        except httpx.ConnectError:
            return {"connected": False, "status": "service_unavailable"}
        except Exception as e:
            logger.error(f"Error checking instance status: {e}")
            return {"connected": False, "status": "error"}

    async def disconnect_instance(self, user_id: str) -> Dict:
        """Disconnect and delete a user's WhatsApp instance"""
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        wa = user.get("whatsapp") if user else None

        if not wa or not wa.get("instance_name"):
            return {"status": "not_connected"}

        instance_name = wa["instance_name"]

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Logout first (unlinks WhatsApp)
                await client.delete(
                    f"{self.base_url}/instance/logout/{instance_name}",
                    headers=self._headers(),
                )
                # Delete the instance
                await client.delete(
                    f"{self.base_url}/instance/delete/{instance_name}",
                    headers=self._headers(),
                )
        except Exception as e:
            logger.error(f"Error deleting instance: {e}")

        # Clear WhatsApp config from user
        await self.db.users.update_one(
            {"_id": user_id},
            {"$unset": {"whatsapp": ""}}
        )

        # Cancel any broadcast task
        task = self._broadcast_tasks.pop(user_id, None)
        if task:
            task.cancel()

        return {"status": "disconnected"}

    # ============ RATE LIMITING (MongoDB) ============

    async def check_message_limit(self, user_id: str) -> Dict:
        """Check monthly plan limit and daily safety limit"""
        user = await self.db.users.find_one({"_id": user_id})
        if not user:
            return {"allowed": False, "reason": "User not found"}

        plan = user.get("subscription_plan", "free")
        monthly_limit = PLAN_MESSAGE_LIMITS.get(plan, PLAN_MESSAGE_LIMITS["free"])

        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        monthly_count = await self.db.messages.count_documents({
            "user_id": user_id,
            "direction": "outgoing",
            "created_at": {"$gte": month_start},
        })

        daily_count = await self.db.messages.count_documents({
            "user_id": user_id,
            "direction": "outgoing",
            "created_at": {"$gte": day_start},
        })

        if daily_count >= DAILY_MESSAGE_LIMIT:
            return {
                "allowed": False,
                "reason": f"Daily safety limit reached ({DAILY_MESSAGE_LIMIT}). Try again tomorrow.",
                "sent": monthly_count,
                "limit": monthly_limit,
                "daily_sent": daily_count,
                "daily_limit": DAILY_MESSAGE_LIMIT,
            }

        if monthly_count >= monthly_limit:
            return {
                "allowed": False,
                "reason": f"Monthly limit reached ({monthly_limit}). Upgrade your plan for more messages.",
                "sent": monthly_count,
                "limit": monthly_limit,
            }

        return {
            "allowed": True,
            "sent": monthly_count,
            "limit": monthly_limit,
            "remaining": monthly_limit - monthly_count,
            "daily_sent": daily_count,
            "daily_limit": DAILY_MESSAGE_LIMIT,
            "plan": plan,
        }

    # ============ MESSAGING ============

    async def send_message(
        self,
        user_id: str,
        to_number: str,
        message: str,
        customer_name: Optional[str] = None,
        media_url: Optional[str] = None,
    ) -> Dict:
        """
        Send a WhatsApp message via Evolution API.
        Auto-creates customer contact if needed.
        Enforces rate limits.
        """
        try:
            # Check rate limits
            limit_check = await self.check_message_limit(user_id)
            if not limit_check["allowed"]:
                return {"status": "limit_reached", "message": limit_check["reason"]}

            # Get user's WhatsApp config
            user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
            wa = user.get("whatsapp") if user else None

            if not wa or wa.get("status") != "connected":
                return {"status": "error", "message": "WhatsApp not connected. Please link your number first."}

            instance_name = wa["instance_name"]
            from_number = wa.get("number", "")

            # Format recipient number for Evolution API (digits only, no +)
            clean_to = to_number.lstrip('+').replace(' ', '').replace('-', '')

            # Step 1: Find or create customer
            customer = await self.db.customers.find_one({
                "user_id": user_id,
                "phone_number": to_number,
            })

            customer_id = None
            created_new = False
            new_customer_name = ""

            if customer:
                customer_id = customer["_id"]
            else:
                customer_id = str(uuid.uuid4())
                new_customer_name = customer_name or f"Customer {to_number[-4:]}"
                await self.db.customers.insert_one({
                    "_id": customer_id,
                    "user_id": user_id,
                    "name": new_customer_name,
                    "phone_number": to_number,
                    "notes": "Auto-created when business sent message",
                    "tags": ["New"],
                    "last_contacted": datetime.utcnow(),
                    "created_at": datetime.utcnow(),
                    "auto_created": False,
                    "business_initiated": True,
                })
                created_new = True

            # Step 2: Store message in DB
            message_id = str(uuid.uuid4())
            message_doc = {
                "_id": message_id,
                "customer_id": customer_id,
                "user_id": user_id,
                "direction": "outgoing",
                "content": message,
                "message_type": "image" if media_url else "text",
                "from_number": from_number,
                "to_number": to_number,
                "status": "pending",
                "created_at": datetime.utcnow(),
            }
            if media_url:
                message_doc["image_url"] = media_url
            await self.db.messages.insert_one(message_doc)

            # Step 3: Update customer last_contacted
            await self.db.customers.update_one(
                {"_id": customer_id},
                {"$set": {"last_contacted": datetime.utcnow()}}
            )

            # Step 4: Send via Evolution API
            evo_msg_id = None
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    if media_url:
                        # Send media message
                        payload = {
                            "number": clean_to,
                            "mediaMessage": {
                                "mediatype": "image",
                                "caption": message,
                                "media": media_url,
                            }
                        }
                        resp = await client.post(
                            f"{self.base_url}/message/sendMedia/{instance_name}",
                            json=payload,
                            headers=self._headers(),
                        )
                    else:
                        # Send text message
                        payload = {
                            "number": clean_to,
                            "textMessage": {"text": message},
                        }
                        resp = await client.post(
                            f"{self.base_url}/message/sendText/{instance_name}",
                            json=payload,
                            headers=self._headers(),
                        )

                    if resp.status_code in (200, 201):
                        resp_data = resp.json()
                        evo_msg_id = resp_data.get("key", {}).get("id")
                        await self.db.messages.update_one(
                            {"_id": message_id},
                            {"$set": {"status": "sent", "evo_message_id": evo_msg_id}}
                        )
                        logger.info(f"Sent message via Evolution API: {evo_msg_id}")
                    else:
                        logger.error(f"Evolution API send error: {resp.text}")
                        await self.db.messages.update_one(
                            {"_id": message_id},
                            {"$set": {"status": "failed", "error": resp.text}}
                        )

            except Exception as e:
                logger.error(f"Failed to send via Evolution API: {e}")
                await self.db.messages.update_one(
                    {"_id": message_id},
                    {"$set": {"status": "failed", "error": str(e)}}
                )

            return {
                "status": "success",
                "customer_id": customer_id,
                "message_id": message_id,
                "evo_message_id": evo_msg_id,
                "created_new_contact": created_new,
                "customer_name": new_customer_name if created_new else (customer or {}).get("name", ""),
            }

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise

    # ============ BROADCAST (asyncio queue) ============

    async def send_broadcast(
        self,
        user_id: str,
        phone_numbers: List[str],
        message: str,
        media_url: Optional[str] = None,
    ) -> Dict:
        """
        Queue a broadcast to multiple numbers with 10s delay between each.
        Enforces 24h cooldown between broadcasts.
        """
        # Check broadcast cooldown
        last_broadcast = await self.db.broadcasts.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)],
        )
        if last_broadcast:
            cooldown_end = last_broadcast["created_at"] + timedelta(hours=BROADCAST_COOLDOWN_HOURS)
            if datetime.utcnow() < cooldown_end:
                remaining = (cooldown_end - datetime.utcnow()).total_seconds() / 3600
                return {
                    "status": "cooldown",
                    "message": f"Please wait {remaining:.1f} hours before sending another broadcast.",
                }

        # Check message limit for total messages
        limit_check = await self.check_message_limit(user_id)
        if not limit_check["allowed"]:
            return {"status": "limit_reached", "message": limit_check["reason"]}

        remaining = limit_check.get("remaining", 0)
        if len(phone_numbers) > remaining:
            return {
                "status": "limit_reached",
                "message": f"Not enough messages remaining. Need {len(phone_numbers)}, have {remaining}.",
            }

        # Record broadcast
        broadcast_id = str(uuid.uuid4())
        await self.db.broadcasts.insert_one({
            "_id": broadcast_id,
            "user_id": user_id,
            "total": len(phone_numbers),
            "sent": 0,
            "failed": 0,
            "status": "in_progress",
            "created_at": datetime.utcnow(),
        })

        # Start async broadcast task
        task = asyncio.create_task(
            self._process_broadcast(user_id, broadcast_id, phone_numbers, message, media_url)
        )
        self._broadcast_tasks[user_id] = task

        return {
            "status": "queued",
            "broadcast_id": broadcast_id,
            "total": len(phone_numbers),
            "message": f"Sending to {len(phone_numbers)} contacts with delays to protect your number.",
        }

    async def _process_broadcast(
        self,
        user_id: str,
        broadcast_id: str,
        phone_numbers: List[str],
        message: str,
        media_url: Optional[str] = None,
    ):
        """Process broadcast queue with 10s delay between messages"""
        sent = 0
        failed = 0

        for phone in phone_numbers:
            try:
                result = await self.send_message(
                    user_id=user_id,
                    to_number=phone,
                    message=message,
                    media_url=media_url,
                )
                if result.get("status") == "success":
                    sent += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Broadcast message failed for {phone}: {e}")
                failed += 1

            # Update progress
            await self.db.broadcasts.update_one(
                {"_id": broadcast_id},
                {"$set": {"sent": sent, "failed": failed}}
            )

            # 10-second delay between messages
            await asyncio.sleep(10)

        # Mark broadcast complete
        await self.db.broadcasts.update_one(
            {"_id": broadcast_id},
            {"$set": {"status": "completed", "sent": sent, "failed": failed, "completed_at": datetime.utcnow()}}
        )
        logger.info(f"Broadcast {broadcast_id} completed: {sent} sent, {failed} failed")

    # ============ WEBHOOK PROCESSING ============

    async def handle_connection_update(self, instance_name: str, data: Dict):
        """Handle connection.update webhook from Evolution API"""
        state = data.get("state") or data.get("instance", {}).get("state", "")

        user = await self.db.users.find_one({"whatsapp.instance_name": instance_name})
        if not user:
            logger.warning(f"No user found for instance {instance_name}")
            return

        if state == "open":
            await self.db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {
                    "whatsapp.status": "connected",
                    "whatsapp.connected_at": datetime.utcnow(),
                }}
            )
            logger.info(f"Instance {instance_name} connected for user {user['_id']}")
        elif state in ("close", "refused"):
            await self.db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"whatsapp.status": "disconnected"}}
            )
            logger.info(f"Instance {instance_name} disconnected for user {user['_id']}")

    async def handle_incoming_message(self, instance_name: str, data: Dict):
        """Handle messages.upsert webhook from Evolution API"""
        # Find the business user who owns this instance
        user = await self.db.users.find_one({"whatsapp.instance_name": instance_name})
        if not user:
            logger.warning(f"No user found for instance {instance_name}")
            return

        # Extract message data from Evolution API webhook payload
        msg = data.get("data", data)
        key = msg.get("key", {})
        from_me = key.get("fromMe", False)

        if from_me:
            return  # Ignore our own outgoing messages

        # Extract sender info
        remote_jid = key.get("remoteJid", "")
        # Convert JID to phone number (remove @s.whatsapp.net)
        from_number = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
        if from_number and not from_number.startswith("+"):
            from_number = f"+{from_number}"

        # Get message content
        message_data = msg.get("message", {})
        body = (
            message_data.get("conversation")
            or message_data.get("extendedTextMessage", {}).get("text")
            or message_data.get("imageMessage", {}).get("caption")
            or ""
        )

        push_name = msg.get("pushName", "")

        if not from_number or not body:
            return

        return {
            "user": user,
            "from_number": from_number,
            "body": body,
            "push_name": push_name,
            "remote_jid": remote_jid,
        }

    async def find_user_by_instance(self, instance_name: str) -> Optional[Dict]:
        """Find user by their Evolution API instance name"""
        return await self.db.users.find_one({"whatsapp.instance_name": instance_name})


# Singleton instance
_whatsapp_service = None


def get_whatsapp_service(db):
    """Get singleton instance"""
    global _whatsapp_service
    if _whatsapp_service is None:
        _whatsapp_service = WhatsAppService(db)
    return _whatsapp_service

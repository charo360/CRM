"""
WhatsApp Service — Evolution API Integration
Multi-tenant WhatsApp gateway using Evolution API with pairing code auth.
Each user gets their own Evolution API instance linked to their WhatsApp number.
"""
import os
import logging
import asyncio
import httpx
import random
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import uuid

logger = logging.getLogger(__name__)

# Evolution API config
EVOLUTION_API_URL = os.environ.get('EVOLUTION_API_URL', 'http://localhost:8080')
EVOLUTION_API_KEY = os.environ.get('EVOLUTION_API_KEY', '')

# Message limits per subscription plan (monthly)
PLAN_MESSAGE_LIMITS = {
    "free": 250,
    "starter": 2500,
    "standard": 5000,
    "pro": 10000,
}

# Credit cost per AI model (deducted from monthly quota per message sent)
# DeepSeek=1x, GPT-4o mini=1.6x, Grok=1.7x, GPT-4o=15x, GPT-5=12x
MODEL_MESSAGE_CREDITS = {
    "standard":   1.6,   # GPT-4o mini (default)
    "gpt4o-mini": 1.6,   # GPT-4o mini
    "deepseek":   1.0,   # DeepSeek V3
    "grok":       1.7,   # Grok 4.1
    "premium":    15.0,  # GPT-4o
    "gpt4o":      15.0,  # GPT-4o
    "gpt5":       12.0,  # GPT-5
    "claude":     12.0,  # Claude
    "claude-3.5": 12.0,  # Claude 3.5
}

def get_model_credits(ai_model: str) -> float:
    """Return credit cost for a given AI model slug."""
    return MODEL_MESSAGE_CREDITS.get(ai_model or "standard", 1.6)

# Rate limiting
DAILY_MESSAGE_LIMIT = 500  # Max messages per user per day (WhatsApp safety)
BROADCAST_COOLDOWN_HOURS = 24  # Min hours between broadcasts

# ============ HUMAN BEHAVIOR SETTINGS (anti-ban) ============
# These make automated messages look human to WhatsApp's detection systems.
# All delays are in seconds. Ranges are (min, max) for random selection.

# Typing speed: fast typer with predictive text, ~25-40 chars/sec
TYPING_CHARS_PER_SECOND = (25, 40)

# Read delay: time between receiving a message and starting to type
AUTO_REPLY_READ_DELAY = (1, 3)      # For auto-replies (AI responses)
ORDER_CONFIRM_READ_DELAY = (0.5, 2) # For order confirmations
MANUAL_SEND_READ_DELAY = (0.3, 1.0) # For manual sends from app (user is waiting)

# Typing pause: humans pause mid-typing (thinking, correcting)
TYPING_PAUSE_CHANCE = 0.2           # 20% chance of a pause per slot
TYPING_PAUSE_DURATION = (0.3, 0.8)  # How long each pause lasts

# Broadcast delays: time between each broadcast message
BROADCAST_DELAY = (2, 5)            # Random delay between broadcast sends

# Max typing indicator duration (WhatsApp resets typing after ~25s)
MAX_TYPING_DURATION = 22


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
            async with httpx.AsyncClient(timeout=60) as client:
                # Step 1: Create instance
                create_payload = {
                    "instanceName": instance_name,
                    "token": str(uuid.uuid4()),
                    "number": clean_number,
                    "qrcode": True,
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
                    # Instance already exists — force-delete it and recreate for a fresh pairing code
                    if "already" in error_detail.lower() or "exists" in error_detail.lower():
                        logger.info(f"Instance {instance_name} already exists — force-deleting for fresh pairing")
                        try:
                            await client.delete(
                                f"{self.base_url}/instance/logout/{instance_name}",
                                headers=self._headers(),
                            )
                            await asyncio.sleep(1)
                            await client.delete(
                                f"{self.base_url}/instance/delete/{instance_name}",
                                headers=self._headers(),
                            )
                            await asyncio.sleep(2)
                        except Exception as del_err:
                            logger.warning(f"Force-delete of stale instance failed: {del_err}")
                        # Re-create the instance fresh
                        create_resp = await client.post(
                            f"{self.base_url}/instance/create",
                            json=create_payload,
                            headers=self._headers(),
                        )
                        if create_resp.status_code not in (200, 201):
                            logger.error(f"Failed to recreate instance after force-delete: {create_resp.text}")
                            return {"status": "error", "message": "Failed to create WhatsApp instance after cleanup"}
                    else:
                        logger.error(f"Failed to create instance: {error_detail}")
                        return {"status": "error", "message": f"Failed to create WhatsApp instance: {error_detail}"}

                # Step 1b: Configure webhook so we receive messages in real-time
                # Evolution API runs in Docker, so use host.docker.internal
                webhook_base = os.environ.get(
                    'WEBHOOK_BASE_URL',
                    'http://host.docker.internal:8000'
                )
                webhook_payload = {
                    "webhook": {
                        "enabled": True,
                        "url": f"{webhook_base}/api/webhooks/evolution",
                        "webhookByEvents": False,
                        "webhookBase64": False,
                        "events": [
                            "MESSAGES_UPSERT",
                            "MESSAGES_UPDATE",
                            "CHATS_UPDATE",
                            "CONNECTION_UPDATE",
                        ]
                    }
                }
                try:
                    wh_resp = await client.post(
                        f"{self.base_url}/webhook/set/{instance_name}",
                        json=webhook_payload,
                        headers=self._headers(),
                    )
                    if wh_resp.status_code in (200, 201):
                        logger.info(f"Webhook configured for {instance_name}")
                    else:
                        logger.warning(f"Failed to set webhook for {instance_name}: {wh_resp.status_code} {wh_resp.text}")
                except Exception as wh_err:
                    logger.warning(f"Webhook setup error for {instance_name}: {wh_err}")

                # Step 2: Wait for Baileys WebSocket — poll until "connecting" state or timeout
                # WA Business needs a bit more time than regular WA to establish the socket
                await asyncio.sleep(5)
                for _wait in range(5):
                    try:
                        state_resp = await client.get(
                            f"{self.base_url}/instance/connectionState/{instance_name}",
                            headers=self._headers(),
                        )
                        if state_resp.status_code == 200:
                            _state = state_resp.json().get("instance", {}).get("state", "")
                            if _state in ("connecting", "open", "close"):
                                break
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                # Step 3: Request pairing code — retry up to 3× with 5s back-off
                # Works for both WhatsApp and WhatsApp Business (same Baileys protocol)
                pairing_code = ""
                last_code_error = ""
                for attempt in range(3):
                    try:
                        code_resp = await client.get(
                            f"{self.base_url}/instance/connect/{instance_name}",
                            params={"number": clean_number},
                            headers=self._headers(),
                            timeout=30,
                        )
                        if code_resp.status_code == 200:
                            code_data = code_resp.json()
                            pairing_code = code_data.get("pairingCode") or code_data.get("code", "")
                            if pairing_code:
                                logger.info(f"Pairing code obtained on attempt {attempt + 1} for {instance_name}")
                                break
                            else:
                                last_code_error = f"Empty code in response: {code_resp.text[:200]}"
                        else:
                            last_code_error = f"HTTP {code_resp.status_code}: {code_resp.text[:200]}"
                    except Exception as ce:
                        last_code_error = str(ce)
                    if attempt < 2:
                        logger.warning(f"Pairing code attempt {attempt + 1} failed for {instance_name}: {last_code_error} — retrying in 5s")
                        await asyncio.sleep(5)

                if not pairing_code:
                    logger.error(f"Failed to get pairing code after 3 attempts: {last_code_error}")
                    return {"status": "error", "message": "Failed to generate pairing code. Please try again."}

                # Step 4: Store instance info in user record
                # Detect WA Business vs regular WA from the profile info if available
                is_business_account = False
                try:
                    profile_resp = await client.get(
                        f"{self.base_url}/instance/fetchInstances",
                        headers=self._headers(),
                    )
                    if profile_resp.status_code == 200:
                        instances = profile_resp.json()
                        for inst in (instances if isinstance(instances, list) else []):
                            if inst.get("name") == instance_name:
                                is_business_account = inst.get("isBusiness", False) or inst.get("businessId") is not None
                                break
                except Exception:
                    pass

                await self.db.users.update_one(
                    {"_id": user_id},
                    {"$set": {
                        "whatsapp.number": phone_number,
                        "whatsapp.instance_name": instance_name,
                        "whatsapp.status": "pairing",
                        "whatsapp.pairing_code": pairing_code,
                        "whatsapp.is_business": is_business_account,
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
        """Check monthly plan limit (credit-weighted) and daily safety limit"""
        user = await self.db.users.find_one({"_id": user_id})
        if not user:
            return {"allowed": False, "reason": "User not found"}

        plan = user.get("subscription_plan", "free")
        monthly_limit = PLAN_MESSAGE_LIMITS.get(plan, PLAN_MESSAGE_LIMITS["free"]) + user.get("extra_credits", 0)

        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Sum credits spent this month (falls back to 1.6 per message if no credits field)
        monthly_agg = await self.db.messages.aggregate([
            {"$match": {
                "user_id": user_id,
                "direction": "outgoing",
                "created_at": {"$gte": month_start},
                "synced_from_history": {"$ne": True},
            }},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$message_credits", 1.6]}}}}
        ]).to_list(1)
        monthly_credits = monthly_agg[0]["total"] if monthly_agg else 0.0

        # Daily count (raw, for anti-ban safety limit)
        daily_count = await self.db.messages.count_documents({
            "user_id": user_id,
            "direction": "outgoing",
            "created_at": {"$gte": day_start},
            "synced_from_history": {"$ne": True},
        })

        if daily_count >= DAILY_MESSAGE_LIMIT:
            return {
                "allowed": False,
                "reason": f"Daily safety limit reached ({DAILY_MESSAGE_LIMIT}). Try again tomorrow.",
                "sent": round(monthly_credits),
                "limit": monthly_limit,
                "daily_sent": daily_count,
                "daily_limit": DAILY_MESSAGE_LIMIT,
            }

        if monthly_credits >= monthly_limit:
            return {
                "allowed": False,
                "reason": f"Monthly credit limit reached ({monthly_limit}). Upgrade your plan for more messages.",
                "sent": round(monthly_credits),
                "limit": monthly_limit,
            }

        return {
            "allowed": True,
            "sent": round(monthly_credits),
            "limit": monthly_limit,
            "remaining": max(0, monthly_limit - monthly_credits),
            "daily_sent": daily_count,
            "daily_limit": DAILY_MESSAGE_LIMIT,
            "plan": plan,
        }

    # ============ HUMAN BEHAVIOR (anti-ban) ============

    async def _send_presence(self, instance_name: str, to_number: str, presence: str = "composing"):
        """Send typing/presence indicator via Evolution API.
        presence: 'composing' (typing...) or 'paused' (stopped typing)
        """
        clean_to = to_number.lstrip('+').replace(' ', '').replace('-', '')
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self.base_url}/chat/sendPresence/{instance_name}",
                    headers=self._headers(),
                    json={
                        "number": clean_to,
                        "presence": presence,
                        "delay": 1000,
                    },
                )
        except Exception as e:
            logger.debug(f"Presence send failed (non-critical): {e}")

    async def _simulate_typing(self, instance_name: str, to_number: str, message: str):
        """Simulate realistic human typing with pauses before sending a message."""
        msg_len = len(message)
        if msg_len == 0:
            return

        # Calculate typing time based on message length
        chars_per_sec = random.uniform(*TYPING_CHARS_PER_SECOND)
        base_typing_time = msg_len / chars_per_sec
        base_typing_time = min(base_typing_time, 8)   # Cap at 8s — no one waits longer than this
        base_typing_time = max(base_typing_time, 1.0)  # Min so it's not instant

        # Determine pause slots for longer messages
        num_pauses = 0
        if msg_len > 80:
            num_pauses = 1
        if msg_len > 200:
            num_pauses = 2

        # Build typing schedule: list of (action, duration)
        schedule = []
        if num_pauses == 0:
            schedule.append(("composing", base_typing_time))
        else:
            chunk_time = base_typing_time / (num_pauses + 1)
            for i in range(num_pauses + 1):
                schedule.append(("composing", chunk_time))
                if i < num_pauses and random.random() < TYPING_PAUSE_CHANCE:
                    pause_dur = random.uniform(*TYPING_PAUSE_DURATION)
                    schedule.append(("paused", pause_dur))

        # Execute the typing schedule
        _PRESENCE_REFRESH = 5  # WhatsApp drops typing indicator after ~10s; refresh every 5s to keep it alive
        for action, duration in schedule:
            await self._send_presence(instance_name, to_number, action)
            if action == "composing":
                remaining = duration
                while remaining > 0:
                    wait = min(remaining, _PRESENCE_REFRESH)
                    await asyncio.sleep(wait)
                    remaining -= wait
                    if remaining > 0:
                        await self._send_presence(instance_name, to_number, "composing")
            else:
                await asyncio.sleep(duration)

    async def _human_delay(self, delay_range: tuple):
        """Wait a random duration within the given range (simulates reading/thinking)."""
        delay = random.uniform(*delay_range)
        logger.info(f"Human behavior: waiting {delay:.1f}s before typing")
        await asyncio.sleep(delay)

    async def mark_as_read(self, instance_name: str, remote_jid: str, message_id: str):
        """Send read receipt to Evolution API — gives customer blue ticks immediately."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Evolution API v2: POST /chat/markMessageAsRead/{instance} (v1 used /message/markAsRead)
                await client.post(
                    f"{self.base_url}/chat/markMessageAsRead/{instance_name}",
                    headers=self._headers(),
                    json={
                        "readMessages": [
                            {
                                "id": message_id,
                                "fromMe": False,
                                "remoteJid": remote_jid,
                            }
                        ]
                    },
                )
        except Exception as e:
            logger.debug(f"markAsRead failed (non-critical): {e}")

    # ============ MESSAGING ============

    async def send_message(
        self,
        user_id: str,
        to_number: str,
        message: str,
        customer_name: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: str = "image",
        media_filename: Optional[str] = None,
        send_context: str = "manual",
        ai_model: Optional[str] = None,
    ) -> Dict:
        """
        Send a WhatsApp message via Evolution API.
        Auto-creates customer contact if needed.
        Enforces rate limits.
        Simulates human behavior (typing + delays) to prevent bans.
        
        send_context: 'manual' | 'auto_reply' | 'order_confirm' | 'broadcast'
        """
        try:
            # Check rate limits
            limit_check = await self.check_message_limit(user_id)
            if not limit_check["allowed"]:
                return {"status": "limit_reached", "message": limit_check["reason"]}

            # Get user's WhatsApp config and AI model
            user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1, "settings": 1})
            wa = user.get("whatsapp") if user else None
            # Manual sends always cost 1 credit flat (no AI used)
            # AI-assisted sends (auto_reply, broadcast, order_confirm) use the model multiplier
            if send_context == "manual":
                _ai_model = "manual"
                _credits = 1.0
            else:
                _ai_model = ai_model or (user.get("settings", {}).get("ai_model", "standard") if user else "standard")
                _credits = get_model_credits(_ai_model)

            if not wa or wa.get("status") != "connected":
                return {"status": "error", "message": "WhatsApp not connected. Please link your number first."}

            instance_name = wa["instance_name"]
            from_number = wa.get("number", "")

            # Format recipient number for Evolution API (digits only, no +, max 15 digits E.164)
            clean_to = to_number.lstrip('+').replace(' ', '').replace('-', '')
            if len(clean_to) > 15:
                clean_to = clean_to[:15]

            # --- Human behavior: delays only for auto-replies (anti-ban) ---
            # Manual sends skip all delays — user is actively waiting
            try:
                if send_context == "auto_reply":
                    await self._human_delay(AUTO_REPLY_READ_DELAY)
                    await self._simulate_typing(instance_name, to_number, message)
                elif send_context == "order_confirm":
                    await self._human_delay(ORDER_CONFIRM_READ_DELAY)
                    await self._simulate_typing(instance_name, to_number, message)
                # manual, product_send, broadcast — no delays
            except Exception as e:
                logger.debug(f"Human behavior simulation error (non-critical): {e}")

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
                # Fetch profile picture in background for new contact
                async def _fetch_pic_bg(uid, cid, phone):
                    try:
                        pic_url = await self.fetch_profile_picture(uid, phone)
                        if pic_url:
                            await self.db.customers.update_one(
                                {"_id": cid},
                                {"$set": {"profile_picture": pic_url}}
                            )
                            logger.info(f"Profile picture set for new contact {phone}")
                    except Exception as e:
                        logger.debug(f"Could not fetch profile pic for {phone}: {e}")
                asyncio.create_task(_fetch_pic_bg(user_id, customer_id, to_number))

            # Step 2: Store message in DB
            message_id = str(uuid.uuid4())
            message_doc = {
                "_id": message_id,
                "customer_id": customer_id,
                "user_id": user_id,
                "direction": "outgoing",
                "content": message,
                "message_type": (media_type or "image") if media_url else "text",
                "from_number": from_number,
                "ai_model": _ai_model,
                "message_credits": _credits,
                "to_number": to_number,
                "status": "pending",
                "send_context": send_context,
                "created_at": datetime.utcnow(),
            }
            if media_url:
                message_doc["image_url"] = media_url
            if media_filename:
                import urllib.parse as _up
                message_doc["file_name"] = _up.unquote(media_filename)
            await self.db.messages.insert_one(message_doc)

            # Step 3: Update customer last_contacted and last_message
            await self.db.customers.update_one(
                {"_id": customer_id},
                {"$set": {
                    "last_contacted": datetime.utcnow(),
                    "last_message": message[:200],
                }}
            )

            # Step 4: Send via Evolution API
            evo_msg_id = None
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    if media_url:
                        # Decode URL-encoded filename (e.g. "my%20file.pdf" → "my file.pdf")
                        import urllib.parse
                        clean_filename = urllib.parse.unquote(media_filename or "")
                        if not clean_filename:
                            clean_filename = "image.jpg" if (media_type or "image") == "image" else "document.pdf"
                        # Send media message (FLAT structure fix)
                        payload = {
                            "number": clean_to,
                            "mediatype": media_type or "image",
                            "media": media_url,
                            "caption": message,
                            "fileName": clean_filename,
                        }
                        logger.info(f"Sending media payload: {payload}")  # DEBUG LOG
                        resp = await client.post(
                            f"{self.base_url}/message/sendMedia/{instance_name}",
                            json=payload,
                            headers=self._headers(),
                        )
                    else:
                        # Send text message
                        payload = {
                            "number": clean_to,
                            "text": message,
                        }
                        resp = await client.post(
                            f"{self.base_url}/message/sendText/{instance_name}",
                            json=payload,
                            headers=self._headers(),
                        )

                    logger.info(f"Evolution API response status: {resp.status_code}")
                    logger.info(f"Evolution API response body: {resp.text[:500]}")
                    
                    if resp.status_code in (200, 201):
                        resp_data = resp.json()
                        evo_msg_id = resp_data.get("key", {}).get("id")
                        remote_jid_out = resp_data.get("key", {}).get("remoteJid") or f"{clean_to}@s.whatsapp.net"
                        await self.db.messages.update_one(
                            {"_id": message_id},
                            {"$set": {"status": "sent", "evo_message_id": evo_msg_id, "remote_jid": remote_jid_out}}
                        )
                        logger.info(f"[OK] Sent message via Evolution API: {evo_msg_id}")
                    else:
                        logger.error(f"[FAIL] Evolution API send error [{resp.status_code}]: {resp.text}")
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

    async def send_list(
        self,
        user_id: str,
        to_number: str,
        title: str,
        description: str,
        button_text: str,
        sections: List[Dict],
        footer_text: Optional[str] = None
    ) -> Dict:
        """
        Send an interactive list message (Catalog-like experience).
        """
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        if not user or not user.get("whatsapp", {}).get("instance_name"):
            return {"status": "error", "message": "WhatsApp not connected"}

        instance_name = user["whatsapp"]["instance_name"]
        clean_to = to_number.lstrip('+').replace(' ', '').replace('-', '')

        payload = {
            "number": clean_to,
            "title": title,
            "description": description,
            "buttonText": button_text,
            "footerText": footer_text or "Powered by CRM",
            "sections": sections
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/message/sendList/{instance_name}",
                    json=payload,
                    headers=self._headers(),
                )

                if resp.status_code in (200, 201):
                    return {"status": "success", "data": resp.json()}
                else:
                    return {"status": "error", "message": resp.text}
        except Exception as e:
            logger.error(f"Error sending list message: {e}")
            return {"status": "error", "message": str(e)}

    async def send_buttons(
        self,
        user_id: str,
        to_number: str,
        title: str,
        description: str,
        buttons: List[Dict],
        footer_text: Optional[str] = None,
        media_url: Optional[str] = None,
    ) -> Dict:
        """
        Send an interactive button message via Evolution API.
        buttons: list of {"buttonId": "...", "buttonText": {"displayText": "..."}}
        Max 3 buttons per WhatsApp rules.
        """
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        if not user or not user.get("whatsapp", {}).get("instance_name"):
            return {"status": "error", "message": "WhatsApp not connected"}

        instance_name = user["whatsapp"]["instance_name"]
        clean_to = to_number.lstrip('+').replace(' ', '').replace('-', '')

        formatted_buttons = []
        for btn in buttons[:3]:
            formatted_buttons.append({
                "type": "replyButton",
                "buttonId": btn.get("buttonId", "btn"),
                "buttonText": btn.get("buttonText", {"displayText": "Button"}),
            })

        payload = {
            "number": clean_to,
            "title": title,
            "description": description,
            "buttons": formatted_buttons,
            "footerText": footer_text or "",
        }

        if media_url:
            payload["mediaMessage"] = {
                "mediatype": "image",
                "media": media_url,
            }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/message/sendButtons/{instance_name}",
                    json=payload,
                    headers=self._headers(),
                )

                if resp.status_code in (200, 201):
                    logger.info(f"Sent button message to {clean_to}")
                    return {"status": "success", "data": resp.json()}
                else:
                    logger.error(f"Button message error: {resp.text}")
                    return {"status": "error", "message": resp.text}
        except Exception as e:
            logger.error(f"Error sending button message: {e}")
            return {"status": "error", "message": str(e)}

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
                    send_context="broadcast",
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

            # Randomized delay between broadcast messages (human-like spacing)
            delay = random.uniform(*BROADCAST_DELAY)
            logger.info(f"Broadcast delay: {delay:.1f}s before next recipient")
            await asyncio.sleep(delay)

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
        """Handle messages.upsert webhook from Evolution API.
        Captures BOTH incoming and outgoing messages so AI has full conversation context.
        """
        # Find the business user who owns this instance
        user = await self.db.users.find_one({"whatsapp.instance_name": instance_name})
        if not user:
            logger.warning(f"No user found for instance {instance_name}")
            return

        # Extract message data from Evolution API webhook payload
        msg = data.get("data", data)
        key = msg.get("key", {})
        from_me = key.get("fromMe", False)

        # Extract sender/recipient info
        remote_jid = key.get("remoteJid", "")

        # Skip group messages (only handle 1:1 chats)
        if "@g.us" in remote_jid:
            return

        # Convert JID to phone number (remove @s.whatsapp.net)
        contact_number = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
        if contact_number and not contact_number.startswith("+"):
            contact_number = f"+{contact_number}"

        # Get message content
        message_data = msg.get("message", {})
        body = (
            message_data.get("conversation")
            or message_data.get("extendedTextMessage", {}).get("text")
            or message_data.get("imageMessage", {}).get("caption")
            or message_data.get("buttonsResponseMessage", {}).get("selectedButtonId")
            or message_data.get("listResponseMessage", {}).get("singleSelectReply", {}).get("selectedRowId")
            or ""
        )

        # Extract image URL if present
        image_message = message_data.get("imageMessage", {})
        image_url = image_message.get("url") or image_message.get("directPath")

        # Extract document if present
        # Evolution API sends documents in two variants:
        # 1. documentMessage — plain document
        # 2. documentWithCaption — document with a text caption
        doc_message = (
            message_data.get("documentMessage")
            or (message_data.get("documentWithCaption") or {}).get("message", {}).get("documentMessage")
            or {}
        )
        doc_url = doc_message.get("url") or doc_message.get("directPath")
        doc_filename = doc_message.get("fileName") or doc_message.get("title") or ""

        if doc_url:
            message_type = "document"
            media_url = doc_url
            # Use doc filename as body if body is empty
            # Avoid the generic fallback string so frontend can detect it properly
            if not body:
                body = doc_filename or "📎 Received document"
        elif image_url:
            message_type = "image"
            media_url = image_url
        else:
            message_type = "text"
            media_url = None

        push_name = msg.get("pushName", "")

        # Allow image-only messages through even when body (caption) is empty —
        # payment screenshots often have no caption text.
        if not contact_number:
            return
        if not body:
            if image_url:
                body = "📷"  # Sentinel so downstream code has a non-empty body
            else:
                return

        evo_msg_id = key.get("id", "")

        result = {
            "user": user,
            "from_number": contact_number,
            "body": body,
            "push_name": push_name,
            "remote_jid": remote_jid,
            "from_me": from_me,
            "evo_message_id": evo_msg_id,
            "message_type": message_type,
        }

        # Store the media URL (works for both images and documents)
        if media_url:
            result["image_url"] = media_url
        # Store original filename for documents
        if doc_filename:
            result["file_name"] = doc_filename

        return result

    async def handle_message_update(self, instance_name: str, data: Dict):
        """Handle messages.update webhook — updates message status (sent/delivered/read).
        Evolution API sends status updates with ack levels:
          1 = sent (server), 2 = delivered, 3 = read, 4 = played (audio)
        """
        logger.info(f"handle_message_update called, data type={type(data).__name__}")
        
        user = await self.db.users.find_one({"whatsapp.instance_name": instance_name})
        if not user:
            logger.warning(f"No user for instance {instance_name}")
            return

        # data can be a list of updates or a single update
        updates = data if isinstance(data, list) else [data]
        logger.info(f"Processing {len(updates)} status updates")
        for update in updates:
            logger.info(f"Update keys: {list(update.keys()) if isinstance(update, dict) else type(update)}")
            
            # Evolution API sends flat format: keyId, remoteJid, fromMe, status at top level
            # OR nested format with key: {remoteJid, id, fromMe}
            key = update.get("key")
            if isinstance(key, dict):
                remote_jid = key.get("remoteJid", "")
                msg_id_field = key.get("id", "")
                from_me = key.get("fromMe", False)
            else:
                # Flat format
                remote_jid = update.get("remoteJid", "")
                msg_id_field = update.get("keyId", "")
                from_me = update.get("fromMe", False)

            logger.info(f"remoteJid={remote_jid}, fromMe={from_me}, msgId={msg_id_field}")

            ack = update.get("status")

            # When the user opens a chat on native WhatsApp, Evolution API fires messages.update
            # with status=READ.  The fromMe flag on these READ receipts is TRUE (it's your device
            # acknowledging you read the incoming message) — so we check both fromMe values.
            if ack == "READ":
                customer_id_found = None

                # Method 1: find a message with this remote_jid and get its customer_id
                if remote_jid:
                    sample_msg = await self.db.messages.find_one({
                        "user_id": user["_id"],
                        "remote_jid": remote_jid,
                        "direction": "incoming",
                    })
                    if sample_msg:
                        customer_id_found = sample_msg.get("customer_id")

                # Method 2: match by lid_jid stored on customer (handles @lid READ events)
                if not customer_id_found and "@lid" in remote_jid:
                    customer = await self.db.customers.find_one({
                        "user_id": user["_id"],
                        "lid_jid": remote_jid,
                    })
                    if customer:
                        customer_id_found = customer["_id"]

                # Method 3: fallback — try phone number match (only works for @s.whatsapp.net)
                if not customer_id_found and "@s.whatsapp.net" in remote_jid:
                    phone = remote_jid.replace("@s.whatsapp.net", "")
                    if not phone.startswith("+"):
                        phone = f"+{phone}"
                    customer = await self.db.customers.find_one({
                        "user_id": user["_id"],
                        "phone_number": phone,
                    })
                    if customer:
                        customer_id_found = customer["_id"]

                if customer_id_found:
                    result = await self.db.messages.update_many(
                        {
                            "user_id": user["_id"],
                            "customer_id": customer_id_found,
                            "direction": "incoming",
                            "read": {"$ne": True},
                        },
                        {"$set": {"read": True}}
                    )
                    if result.modified_count:
                        logger.info(f"Marked {result.modified_count} incoming messages as read (jid={remote_jid}, fromMe={from_me}, opened on WhatsApp)")
                continue

            # Skip non-READ updates for incoming messages — only track delivery status on outgoing
            if not from_me:
                continue

            # Map ack level to status (outgoing delivery tracking)
            ack = update.get("status")
            if ack is None:
                ack = update.get("update", {}).get("status")
            logger.info(f"ack={ack!r}, type={type(ack).__name__ if ack is not None else 'NoneType'}")
            
            # Evolution API uses different formats
            if isinstance(ack, str):
                status_map = {
                    "SERVER_ACK": "sent",
                    "DELIVERY_ACK": "delivered",
                    "READ": "read",
                    "PLAYED": "read",
                }
                new_status = status_map.get(ack, ack.lower())
            elif isinstance(ack, int):
                ack_map = {0: "pending", 1: "sent", 2: "delivered", 3: "read", 4: "read"}
                new_status = ack_map.get(ack, "sent")
            else:
                continue

            # Match by evo_message_id (the WhatsApp message ID stored when we sent the message)
            if msg_id_field:
                result = await self.db.messages.update_one(
                    {
                        "user_id": user["_id"],
                        "evo_message_id": msg_id_field,
                        "direction": "outgoing",
                    },
                    {"$set": {"status": new_status}}
                )
                logger.info(f"Updated message evo_message_id={msg_id_field} to status={new_status}, matched={result.matched_count}")
            else:
                logger.warning(f"No message ID in update payload, skipping")

    async def fetch_profile_picture(self, user_id: str, phone_number: str) -> Optional[str]:
        """Fetch a contact's WhatsApp profile picture URL via Evolution API.
        Returns URL string on success, None on failure/not-found.
        Raises ConnectionError if the instance doesn't exist (caller should stop retrying).
        """
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        wa = user.get("whatsapp") if user else None
        if not wa or not wa.get("instance_name"):
            return None

        instance_name = wa["instance_name"]
        clean_number = phone_number.lstrip("+").replace(" ", "").replace("-", "")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/fetchProfilePictureUrl/{instance_name}",
                    headers=self._headers(),
                    json={"number": clean_number},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    pic_url = data.get("profilePictureUrl") or data.get("profilePicUrl") or data.get("url")
                    return pic_url
                if resp.status_code == 404:
                    # Instance doesn't exist in Evolution API — no point retrying
                    body = resp.text
                    if "instance does not exist" in body.lower():
                        raise ConnectionError(f"Instance {instance_name} does not exist in Evolution API")
                    # 404 for the contact's picture is normal (no profile pic set)
                    return None
        except ConnectionError:
            raise  # Re-raise so callers can handle instance-not-found
        except Exception as e:
            logger.debug(f"Could not fetch profile pic for {phone_number}: {e}")
        return None

    async def fetch_profile_pictures_bulk(self, user_id: str) -> Dict:
        """Fetch profile pictures for all customers missing them.
        
        Strategy:
        1. Use findContacts (single API call) to get all cached profile pics from Evolution API
        2. Match by phone number and update customers in our DB
        3. For remaining customers still missing pics, try fetchProfilePictureUrl individually
        """
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        wa = user.get("whatsapp") if user else None
        if not wa or not wa.get("instance_name"):
            return {"updated": 0}

        instance_name = wa["instance_name"]
        updated = 0

        # --- Phase 1: Bulk update from findContacts cache ---
        # Must send {"where": {}} — empty body returns 0 contacts
        evo_pics = {}    # digits-only phone -> pic_url
        evo_names = {}   # digits-only phone -> pushName
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/findContacts/{instance_name}",
                    headers=self._headers(),
                    json={"where": {}},
                )
                if resp.status_code == 200:
                    contacts = resp.json()
                    if not isinstance(contacts, list):
                        contacts = contacts.get("contacts", contacts.get("data", []))
                    for c in contacts:
                        remote_jid = c.get("remoteJid") or ""
                        # Only match standard JIDs — @lid format can't be mapped to phone
                        if "@s.whatsapp.net" not in remote_jid:
                            continue
                        digits = remote_jid.replace("@s.whatsapp.net", "").strip()
                        pic_url = c.get("profilePicUrl")
                        push_name = c.get("pushName") or c.get("name") or ""
                        if pic_url:
                            evo_pics[digits] = pic_url
                        if push_name:
                            evo_names[digits] = push_name
                    logger.info(f"findContacts: {len(contacts)} contacts, {len(evo_pics)} with pics, {len(evo_names)} with names")
                elif resp.status_code == 404 and "instance does not exist" in resp.text.lower():
                    logger.warning(f"Instance {instance_name} not found, skipping bulk profile fetch")
                    return {"updated": 0}
                else:
                    logger.warning(f"findContacts returned {resp.status_code}, skipping cache phase")
        except Exception as e:
            logger.warning(f"findContacts failed: {e}")

        # Get customers missing profile pictures
        customers = await self.db.customers.find(
            {"user_id": user_id, "phone_number": {"$exists": True},
             "$or": [{"profile_picture": None}, {"profile_picture": {"$exists": False}}, {"profile_picture": ""}]},
            {"_id": 1, "phone_number": 1}
        ).to_list(None)

        if not customers:
            logger.info(f"All customers already have profile pictures (user {user_id})")
            return {"updated": 0}

        logger.info(f"{len(customers)} customers missing profile pictures")

        # Match customers to cached pics (and backfill names while we're at it)
        still_missing = []
        names_updated = 0
        for cust in customers:
            phone = cust.get("phone_number", "").lstrip("+").replace(" ", "").replace("-", "")
            if not phone:
                continue
            pic_url = evo_pics.get(phone)
            push_name = evo_names.get(phone, "")
            updates = {}
            if pic_url:
                updates["profile_picture"] = pic_url
                updated += 1
            else:
                still_missing.append(cust)
            # Also fix fallback names while we have the data
            current_name = cust.get("name", "")
            is_fallback = not current_name or current_name.startswith("Contact ") or current_name.startswith("+")
            if push_name and is_fallback:
                updates["name"] = push_name
                names_updated += 1
            if updates:
                await self.db.customers.update_one({"_id": cust["_id"]}, {"$set": updates})

        logger.info(f"Phase 1 (findContacts cache): {updated} pics, {names_updated} names updated")

        # --- Phase 2: Parallel batch fetch for all remaining ---
        BATCH_SIZE = 20  # fetch 20 at a time in parallel
        errors = 0
        phase2_updated = 0
        abort = False

        valid_missing = [
            c for c in still_missing
            if c.get("phone_number") and 5 <= len(c["phone_number"].lstrip("+").replace(" ", "").replace("-", "")) <= 15
        ]

        async def _fetch_one(client: httpx.AsyncClient, cust: Dict):
            phone = cust.get("phone_number", "").lstrip("+").replace(" ", "").replace("-", "")
            try:
                resp = await client.post(
                    f"{self.base_url}/chat/fetchProfilePictureUrl/{instance_name}",
                    headers=self._headers(),
                    json={"number": phone},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    pic_url = data.get("profilePictureUrl") or data.get("profilePicUrl") or data.get("url")
                    return (cust["_id"], pic_url, None)
                if resp.status_code == 404 and "instance does not exist" in resp.text.lower():
                    return (cust["_id"], None, "instance_gone")
                return (cust["_id"], None, "no_pic")
            except Exception as e:
                return (cust["_id"], None, str(e))

        async with httpx.AsyncClient(timeout=10) as client:
            for i in range(0, len(valid_missing), BATCH_SIZE):
                if abort:
                    break
                batch = valid_missing[i:i + BATCH_SIZE]
                results = await asyncio.gather(*[_fetch_one(client, c) for c in batch])
                for cust_id, pic_url, err in results:
                    if err == "instance_gone":
                        logger.warning(f"Instance {instance_name} gone, aborting")
                        abort = True
                        break
                    if pic_url:
                        await self.db.customers.update_one(
                            {"_id": cust_id},
                            {"$set": {"profile_picture": pic_url}}
                        )
                        phase2_updated += 1
                    elif err and err not in ("no_pic", "instance_gone"):
                        errors += 1
                # Small pause between batches to avoid hammering Evolution API
                await asyncio.sleep(0.5)

        updated += phase2_updated
        logger.info(f"Phase 2 (parallel batch fetch): updated {phase2_updated}, errors: {errors}")
        logger.info(f"Total profile pictures updated: {updated} (user {user_id})")
        return {"updated": updated, "errors": errors}

    async def find_user_by_instance(self, instance_name: str) -> Optional[Dict]:
        """Find user by their Evolution API instance name"""
        return await self.db.users.find_one({"whatsapp.instance_name": instance_name})

    # ============ CONTACT & HISTORY SYNC ============

    async def fetch_contacts(self, user_id: str) -> Dict:
        """
        Fetch all WhatsApp contacts from Evolution API and create them in the CRM.
        Called once after initial WhatsApp connection to seed the contact list.
        Uses POST /chat/findContacts/{instance} endpoint.
        """
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1, "phone_number": 1})
        wa = user.get("whatsapp") if user else None
        if not wa or not wa.get("instance_name"):
            return {"status": "error", "message": "WhatsApp not connected"}

        instance_name = wa["instance_name"]
        own_number = (user.get("phone_number") or "").lstrip("+")
        created = 0
        updated = 0
        skipped = 0

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/findContacts/{instance_name}",
                    headers=self._headers(),
                    json={"where": {}},
                )

                if resp.status_code != 200:
                    logger.error(f"Failed to fetch contacts: {resp.status_code} {resp.text}")
                    return {"status": "error", "message": "Failed to fetch contacts from WhatsApp"}

                contacts = resp.json()
                if not isinstance(contacts, list):
                    contacts = contacts.get("data", contacts.get("contacts", []))

                for contact in contacts:
                    # Extract phone from remoteJid
                    jid = contact.get("remoteJid", "")
                    if not jid or "@g.us" in jid or "status@" in jid or "0@s.whatsapp.net" == jid:
                        continue  # Skip groups, status broadcasts, system contacts
                    phone = jid.split("@")[0] if "@" in jid else jid
                    if not phone or not phone.isdigit():
                        continue
                    # Skip own number
                    if phone == own_number:
                        continue
                    phone = f"+{phone}"

                    raw_name = (
                        contact.get("pushName")
                        or contact.get("name")
                        or contact.get("notify")
                        or ""
                    )

                    # Check if contact already exists
                    existing = await self.db.customers.find_one({
                        "user_id": user_id,
                        "phone_number": phone
                    })
                    if existing:
                        updates = {}
                        if not existing.get("synced_from_whatsapp"):
                            updates["synced_from_whatsapp"] = True

                        current_name = existing.get("name", "")
                        is_fallback = not current_name or current_name.startswith("Contact ") or current_name.startswith("+")
                        if raw_name and not raw_name.startswith("Contact ") and is_fallback:
                            updates["name"] = raw_name
                        elif is_fallback and not raw_name:
                            # Try to get name from most recent message pushName
                            recent_msg = await self.db.messages.find_one(
                                {"customer_id": existing["_id"], "user_id": user_id, "push_name": {"$exists": True, "$ne": ""}},
                                sort=[("created_at", -1)]
                            )
                            if recent_msg and recent_msg.get("push_name"):
                                updates["name"] = recent_msg["push_name"]

                        if updates:
                            await self.db.customers.update_one(
                                {"_id": existing["_id"]},
                                {"$set": updates}
                            )
                            updated += 1
                        else:
                            skipped += 1
                        continue

                    # For new contacts with no name, use phone last 4 as temp fallback
                    name = raw_name or f"Contact {phone[-4:]}"

                    await self.db.customers.insert_one({
                        "_id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "name": name,
                        "phone_number": phone,
                        "notes": "",
                        "tags": ["New"],
                        "purchase_count": 0,
                        "total_spent": 0.0,
                        "last_message": None,
                        "last_contacted": None,
                        "created_at": datetime.utcnow(),
                        "auto_created": True,
                        "synced_from_whatsapp": True,
                        "is_customer": False,
                    })
                    created += 1

            logger.info(f"Contact sync for user {user_id}: {created} created, {updated} updated, {skipped} already synced")
            return {"status": "success", "created": created, "updated": updated, "skipped": skipped}

        except httpx.ConnectError:
            return {"status": "error", "message": "Evolution API not reachable"}
        except Exception as e:
            logger.error(f"Error fetching contacts: {e}")
            return {"status": "error", "message": str(e)}

    async def fetch_chat_history(self, user_id: str, max_messages_per_chat: int = 50) -> Dict:
        """
        Fetch recent chat history from Evolution API for all contacts.
        Called once after initial WhatsApp connection to populate past conversations.
        Uses POST /chat/findChats and POST /chat/findMessages endpoints.
        Evolution API returns messages as: {"messages": {"total": N, "records": [...]}}
        """
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1, "phone_number": 1})
        wa = user.get("whatsapp") if user else None
        if not wa or not wa.get("instance_name"):
            return {"status": "error", "message": "WhatsApp not connected"}

        instance_name = wa["instance_name"]
        own_number = (user.get("phone_number") or "").lstrip("+")
        total_messages = 0
        chats_synced = 0

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                # Step 1: Get list of chats via POST
                chats_resp = await client.post(
                    f"{self.base_url}/chat/findChats/{instance_name}",
                    headers=self._headers(),
                    json={},
                )

                if chats_resp.status_code != 200:
                    logger.error(f"Failed to fetch chats: {chats_resp.status_code} {chats_resp.text}")
                    return {"status": "error", "message": "Failed to fetch chat list"}

                chats = chats_resp.json()
                if not isinstance(chats, list):
                    chats = chats.get("data", chats.get("chats", []))

                for chat in chats:
                    chat_jid = chat.get("remoteJid", "")
                    if not chat_jid or "@g.us" in chat_jid or "status@" in chat_jid:
                        continue  # Skip groups and status broadcasts

                    phone = chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
                    if not phone or not phone.isdigit():
                        continue
                    # Skip own number
                    if phone == own_number:
                        continue
                    phone = f"+{phone}"

                    # Find or create customer record
                    customer = await self.db.customers.find_one({
                        "user_id": user_id,
                        "phone_number": phone
                    })
                    if not customer:
                        # Auto-create from chat
                        push_name = chat.get("pushName") or f"Contact {phone[-4:]}"
                        customer_id = str(uuid.uuid4())
                        customer = {
                            "_id": customer_id,
                            "user_id": user_id,
                            "name": push_name,
                            "phone_number": phone,
                            "notes": "",
                            "tags": ["New"],
                            "purchase_count": 0,
                            "total_spent": 0.0,
                            "last_message": None,
                            "last_contacted": None,
                            "created_at": datetime.utcnow(),
                            "auto_created": True,
                            "synced_from_whatsapp": True,
                            "is_customer": False,
                        }
                        await self.db.customers.insert_one(customer)

                    # Skip only if we already synced history for this customer
                    already_synced = await self.db.messages.count_documents({
                        "customer_id": customer["_id"],
                        "user_id": user_id,
                        "synced_from_history": True
                    })
                    if already_synced > 0:
                        continue  # History already pulled for this contact

                    # Step 2: Fetch messages for this chat
                    try:
                        msgs_resp = await client.post(
                            f"{self.base_url}/chat/findMessages/{instance_name}",
                            headers=self._headers(),
                            json={
                                "where": {"key": {"remoteJid": chat_jid}},
                                "limit": max_messages_per_chat,
                            },
                        )

                        if msgs_resp.status_code != 200:
                            continue

                        raw = msgs_resp.json()
                        # Evolution API returns: {"messages": {"total": N, "pages": N, "records": [...]}}
                        if isinstance(raw, dict):
                            msg_container = raw.get("messages", raw)
                            if isinstance(msg_container, dict):
                                records = msg_container.get("records", [])
                            elif isinstance(msg_container, list):
                                records = msg_container
                            else:
                                records = []
                        elif isinstance(raw, list):
                            records = raw
                        else:
                            records = []

                        last_body = None
                        best_push_name = chat.get("pushName") or chat.get("name") or ""
                        for msg in records:
                            key = msg.get("key", {})
                            from_me = key.get("fromMe", False)
                            msg_data = msg.get("message", {})
                            body = (
                                msg_data.get("conversation")
                                or msg_data.get("extendedTextMessage", {}).get("text")
                                or msg_data.get("imageMessage", {}).get("caption")
                                or ""
                            )
                            if not body:
                                continue

                            # Capture pushName from incoming messages
                            msg_push_name = msg.get("pushName", "")
                            if msg_push_name and not from_me:
                                best_push_name = best_push_name or msg_push_name

                            # Parse timestamp
                            ts = msg.get("messageTimestamp")
                            if isinstance(ts, (int, float)):
                                msg_time = datetime.utcfromtimestamp(ts)
                            else:
                                msg_time = datetime.utcnow()

                            direction = "outgoing" if from_me else "incoming"

                            msg_doc = {
                                "_id": str(uuid.uuid4()),
                                "customer_id": customer["_id"],
                                "user_id": user_id,
                                "direction": direction,
                                "content": body,
                                "message_type": "text",
                                "from_number": phone if not from_me else user.get("phone_number", ""),
                                "created_at": msg_time,
                                "synced_from_history": True,
                            }
                            if msg_push_name and not from_me:
                                msg_doc["push_name"] = msg_push_name
                            await self.db.messages.insert_one(msg_doc)
                            total_messages += 1
                            last_body = body

                        # Update customer's last message + resolve name
                        updates = {
                            "last_contacted": datetime.utcnow(),
                        }
                        if last_body:
                            updates["last_message"] = last_body[:200]

                        # Update name if current is a fallback and we found a real pushName
                        current_name = customer.get("name", "")
                        is_fallback = not current_name or current_name.startswith("Contact ") or current_name.startswith("+")
                        if best_push_name and is_fallback:
                            updates["name"] = best_push_name
                        
                        await self.db.customers.update_one(
                            {"_id": customer["_id"]},
                            {"$set": updates}
                        )
                        chats_synced += 1

                    except Exception as chat_err:
                        logger.error(f"Error fetching messages for {phone}: {chat_err}")
                        continue

            logger.info(f"Chat history sync for user {user_id}: {chats_synced} chats, {total_messages} messages")
            return {"status": "success", "chats_synced": chats_synced, "messages_synced": total_messages}

        except httpx.ConnectError:
            return {"status": "error", "message": "Evolution API not reachable"}
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return {"status": "error", "message": str(e)}

    async def fetch_history_for_contact(
        self,
        user_id: str,
        phone: str,
        customer_id: str,
        max_messages: int = 50,
    ) -> Dict:
        """
        Fetch WhatsApp message history for a single contact and store it in DB.
        Called immediately after a customer is manually created or imported so their
        prior conversations appear right away.

        Returns {"status": "success"|"error", "messages_synced": N}.
        """
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1, "phone_number": 1})
        wa = user.get("whatsapp") if user else None
        if not wa or not wa.get("instance_name"):
            return {"status": "error", "message": "WhatsApp not connected"}

        instance_name = wa["instance_name"]
        own_number = (user.get("phone_number") or "").lstrip("+")

        # Normalise phone → digits only (no +)
        digits = phone.lstrip("+").replace(" ", "").replace("-", "")
        if not digits or digits == own_number:
            return {"status": "skip", "message": "Own number or invalid phone"}

        chat_jid = f"{digits}@s.whatsapp.net"

        # Skip if we already synced history for this customer
        already_synced = await self.db.messages.count_documents({
            "customer_id": customer_id,
            "user_id": user_id,
            "synced_from_history": True,
        })
        if already_synced > 0:
            return {"status": "skip", "message": "History already synced"}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                msgs_resp = await client.post(
                    f"{self.base_url}/chat/findMessages/{instance_name}",
                    headers=self._headers(),
                    json={
                        "where": {"key": {"remoteJid": chat_jid}},
                        "limit": max_messages,
                    },
                )
                if msgs_resp.status_code != 200:
                    return {"status": "error", "message": f"Evolution API returned {msgs_resp.status_code}"}

                raw = msgs_resp.json()
                if isinstance(raw, dict):
                    msg_container = raw.get("messages", raw)
                    records = msg_container.get("records", []) if isinstance(msg_container, dict) else (msg_container if isinstance(msg_container, list) else [])
                elif isinstance(raw, list):
                    records = raw
                else:
                    records = []

                total = 0
                last_body = None
                best_push_name = ""
                for msg in records:
                    key = msg.get("key", {})
                    from_me = key.get("fromMe", False)
                    msg_data = msg.get("message", {})
                    body = (
                        msg_data.get("conversation")
                        or msg_data.get("extendedTextMessage", {}).get("text")
                        or msg_data.get("imageMessage", {}).get("caption")
                        or ""
                    )
                    if not body:
                        continue

                    msg_push_name = msg.get("pushName", "")
                    if msg_push_name and not from_me:
                        best_push_name = best_push_name or msg_push_name

                    ts = msg.get("messageTimestamp")
                    msg_time = datetime.utcfromtimestamp(ts) if isinstance(ts, (int, float)) else datetime.utcnow()

                    msg_doc = {
                        "_id": str(uuid.uuid4()),
                        "customer_id": customer_id,
                        "user_id": user_id,
                        "direction": "outgoing" if from_me else "incoming",
                        "content": body,
                        "message_type": "text",
                        "from_number": f"+{digits}" if not from_me else user.get("phone_number", ""),
                        "created_at": msg_time,
                        "synced_from_history": True,
                    }
                    if msg_push_name and not from_me:
                        msg_doc["push_name"] = msg_push_name

                    try:
                        await self.db.messages.insert_one(msg_doc)
                        total += 1
                        last_body = body
                    except Exception:
                        pass  # Duplicate key — already stored

                # Update customer's last_message / last_contacted and name if it was a fallback
                if total > 0:
                    updates: Dict = {"last_contacted": datetime.utcnow()}
                    if last_body:
                        updates["last_message"] = last_body[:200]

                    customer = await self.db.customers.find_one({"_id": customer_id})
                    if customer:
                        current_name = customer.get("name", "")
                        is_fallback = (
                            not current_name
                            or current_name.startswith("Contact ")
                            or current_name.startswith("+")
                        )
                        if best_push_name and is_fallback:
                            updates["name"] = best_push_name

                    await self.db.customers.update_one({"_id": customer_id}, {"$set": updates})

                logger.info(f"[HistorySync] {total} messages pulled for customer {customer_id} ({phone})")
                return {"status": "success", "messages_synced": total}

        except httpx.ConnectError:
            return {"status": "error", "message": "Evolution API not reachable"}
        except Exception as e:
            logger.error(f"[HistorySync] Failed for {phone}: {e}")
            return {"status": "error", "message": str(e)}


# Singleton instance
_whatsapp_service = None


def get_whatsapp_service(db):
    """Get singleton instance"""
    global _whatsapp_service
    if _whatsapp_service is None:
        _whatsapp_service = WhatsAppService(db)
    return _whatsapp_service


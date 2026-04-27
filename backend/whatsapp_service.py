"""
WhatsApp Service — Evolution API
Handles instance lifecycle, message sending, contact sync, and webhook parsing.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Module-level constants (imported by server.py)
EVOLUTION_API_URL: str = os.environ.get("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY: str = os.environ.get("EVOLUTION_API_KEY", "")

# Daily/monthly message limits per plan
_PLAN_LIMITS: Dict[str, Dict] = {
    "free":       {"daily": 50,   "monthly": 500},
    "starter":    {"daily": 500,  "monthly": 5000},
    "growth":     {"daily": 2000, "monthly": 20000},
    "enterprise": {"daily": 10000, "monthly": 100000},
}


def _jid_to_phone(jid: str) -> str:
    """Extract bare phone number from WhatsApp JID (e.g. '254712345678@s.whatsapp.net')."""
    return jid.split("@")[0].split(":")[0]


def _extract_message_body(msg: dict) -> tuple[str, str, Optional[str], Optional[str]]:
    """
    Extract (body, message_type, image_url, file_name) from Evolution message object.
    Returns empty strings / None on unknown types.
    """
    if not msg:
        return "", "text", None, None

    # Text
    if "conversation" in msg:
        return msg["conversation"], "text", None, None

    ext = msg.get("extendedTextMessage", {})
    if ext and ext.get("text"):
        return ext["text"], "text", None, None

    # Image
    img = msg.get("imageMessage", {})
    if img:
        return img.get("caption", ""), "image", img.get("url") or img.get("jpegThumbnail"), None

    # Video
    vid = msg.get("videoMessage", {})
    if vid:
        return vid.get("caption", ""), "video", vid.get("url"), None

    # Document
    doc = msg.get("documentMessage", {})
    if doc:
        return doc.get("caption", ""), "document", doc.get("url"), doc.get("fileName")

    # Audio / PTT
    audio = msg.get("audioMessage", {})
    if audio:
        return "[Voice message]", "audio", audio.get("url"), None

    # Sticker
    if "stickerMessage" in msg:
        return "[Sticker]", "sticker", None, None

    # Location
    loc = msg.get("locationMessage", {})
    if loc:
        lat = loc.get("degreesLatitude", "")
        lng = loc.get("degreesLongitude", "")
        return f"[Location: {lat},{lng}]", "location", None, None

    # Buttons / lists (just capture title)
    for key in ("buttonsResponseMessage", "listResponseMessage", "templateMessage"):
        if key in msg:
            inner = msg[key]
            text = (
                inner.get("selectedDisplayText")
                or inner.get("singleSelectReply", {}).get("selectedRowId")
                or inner.get("hydratedTemplate", {}).get("hydratedContentText")
                or ""
            )
            return text, "interactive", None, None

    # Reaction
    reaction = msg.get("reactionMessage", {})
    if reaction:
        return reaction.get("text", "👍"), "reaction", None, None

    return "", "unknown", None, None


class WhatsAppService:
    """Evolution API wrapper for WhatsApp messaging."""

    def __init__(self, db):
        self.db = db
        self.base_url = EVOLUTION_API_URL.rstrip("/")
        self._api_key = EVOLUTION_API_KEY

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {"apikey": self._api_key, "Content-Type": "application/json"}

    def _instance_name(self, user_id: str) -> str:
        """Deterministic instance name from user_id."""
        return f"user_{str(user_id).replace('-', '_')}"

    # ── Instance lifecycle ───────────────────────────────────────────────────

    async def create_instance(self, user_id: str, phone: str) -> dict:
        """Create Evolution API instance and request a pairing code."""
        instance_name = self._instance_name(user_id)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Create instance
                create_resp = await client.post(
                    f"{self.base_url}/instance/create",
                    headers=self._headers(),
                    json={
                        "instanceName": instance_name,
                        "number": phone,
                        "token": "",
                        "qrcode": False,
                        "integration": "WHATSAPP-BAILEYS",
                    },
                )
                logger.info(f"[create_instance] status={create_resp.status_code} body={create_resp.text[:300]}")

                # 409 = already exists — that is fine, continue to get pairing code
                if create_resp.status_code not in (200, 201, 409):
                    return {"status": "error", "message": create_resp.text[:200]}

                # Persist instance name in DB
                await self.db.users.update_one(
                    {"_id": user_id},
                    {"$set": {"whatsapp.instance_name": instance_name}},
                )

                # Request pairing code
                pair_resp = await client.post(
                    f"{self.base_url}/instance/pairingCode/{instance_name}",
                    headers=self._headers(),
                    json={"number": phone},
                )
                logger.info(f"[pairing_code] status={pair_resp.status_code} body={pair_resp.text[:300]}")

                if pair_resp.status_code in (200, 201):
                    pair_data = pair_resp.json()
                    code = pair_data.get("code") or pair_data.get("pairingCode", "")
                    return {
                        "status": "pairing",
                        "pairing_code": code,
                        "pairing_data": pair_data,
                    }

                return {"status": "error", "message": pair_resp.text[:200]}

        except Exception as e:
            logger.error(f"[create_instance] error: {e}")
            return {"status": "error", "message": str(e)}

    async def refresh_pairing_code(self, user_id: str, phone: str) -> dict:
        """Re-request a pairing code for an existing instance."""
        instance_name = self._instance_name(user_id)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{self.base_url}/instance/pairingCode/{instance_name}",
                    headers=self._headers(),
                    json={"number": phone},
                )
                data = resp.json() if resp.status_code in (200, 201) else {}
                return {
                    "status": "pairing",
                    "pairing_code": data.get("code") or data.get("pairingCode", ""),
                    "pairing_data": data,
                }
        except Exception as e:
            logger.error(f"[refresh_pairing_code] error: {e}")
            return {"status": "error", "message": str(e)}

    async def get_instance_status(self, user_id: str) -> dict:
        """Return connection status for the user's WhatsApp instance."""
        instance_name = self._instance_name(user_id)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/instance/connectionState/{instance_name}",
                    headers=self._headers(),
                )
                if resp.status_code == 404:
                    return {"connected": False, "status": "not_found"}

                data = resp.json()
                # Evolution API returns {"instance": {"state": "open"}} or {"state": "open"}
                state = (
                    data.get("state")
                    or (data.get("instance") or {}).get("state")
                    or ""
                )
                connected = state == "open"
                number = (
                    data.get("number")
                    or (data.get("instance") or {}).get("wuid", "").split(":")[0].split("@")[0]
                    or None
                )
                return {"connected": connected, "status": state, "number": number}
        except Exception as e:
            logger.warning(f"[get_instance_status] {user_id}: {e}")
            return {"connected": False, "status": "error"}

    async def disconnect_instance(self, user_id: str) -> dict:
        """Logout and delete the Evolution API instance."""
        instance_name = self._instance_name(user_id)
        results: dict = {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                logout = await client.delete(
                    f"{self.base_url}/instance/logout/{instance_name}",
                    headers=self._headers(),
                )
                results["logout"] = logout.status_code

                delete = await client.delete(
                    f"{self.base_url}/instance/delete/{instance_name}",
                    headers=self._headers(),
                )
                results["delete"] = delete.status_code
        except Exception as e:
            results["error"] = str(e)

        await self.db.users.update_one(
            {"_id": user_id},
            {"$unset": {"whatsapp.instance_name": ""}},
        )
        return results

    # ── Message sending ──────────────────────────────────────────────────────

    async def check_message_limit(self, user_id: str) -> dict:
        """Return daily and monthly message usage for the user."""
        try:
            user = await self.db.users.find_one({"_id": user_id}, {"subscription": 1, "plan": 1})
            plan = (user or {}).get("plan", "free") if user else "free"
            limits = _PLAN_LIMITS.get(plan, _PLAN_LIMITS["free"])

            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            daily_sent = await self.db.messages.count_documents({
                "user_id": user_id,
                "direction": "outgoing",
                "created_at": {"$gte": today},
            })
            return {
                "sent": daily_sent,
                "limit": limits["daily"],
                "remaining": max(0, limits["daily"] - daily_sent),
                "daily_sent": daily_sent,
                "daily_limit": limits["daily"],
                "plan": plan,
            }
        except Exception as e:
            logger.warning(f"[check_message_limit] {user_id}: {e}")
            return {"sent": 0, "limit": 50, "remaining": 50, "daily_sent": 0, "daily_limit": 50, "plan": "free"}

    async def send_message(
        self,
        user_id: str,
        to_number: str,
        message: str,
        customer_name: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        media_filename: Optional[str] = None,
        send_context: str = "manual",
    ) -> dict:
        """
        Send a WhatsApp message via Evolution API.
        Auto-creates customer record if not found.
        Returns {"status": "success"|"limit_reached", ...}.
        """
        try:
            # Rate limit check
            limits = await self.check_message_limit(user_id)
            if limits["remaining"] <= 0:
                return {
                    "status": "limit_reached",
                    "message": f"Daily limit of {limits['daily_limit']} messages reached.",
                }

            # Find or create customer
            customer = await self.db.customers.find_one({
                "user_id": user_id,
                "phone_number": to_number,
            })
            customer_id: str
            if customer:
                customer_id = customer["_id"]
            else:
                customer_id = str(uuid.uuid4())
                display_name = customer_name or f"Contact {to_number[-4:]}"
                await self.db.customers.insert_one({
                    "_id": customer_id,
                    "user_id": user_id,
                    "name": display_name,
                    "phone_number": to_number,
                    "notes": "",
                    "tags": ["New"],
                    "last_contacted": datetime.utcnow(),
                    "created_at": datetime.utcnow(),
                    "auto_created": False,
                    "business_initiated": True,
                })
                logger.info(f"[send_message] auto-created customer {display_name} ({to_number})")

            # Store message in DB first (so we can back-fill evo_message_id from webhook)
            message_id = str(uuid.uuid4())
            msg_doc = {
                "_id": message_id,
                "customer_id": customer_id,
                "user_id": user_id,
                "direction": "outgoing",
                "content": message,
                "message_type": "image" if media_url and media_type == "image" else ("document" if media_url else "text"),
                "from_number": to_number,
                "created_at": datetime.utcnow(),
                "send_context": send_context,
            }
            if media_url:
                msg_doc["image_url"] = media_url
            if media_filename:
                msg_doc["file_name"] = media_filename
            await self.db.messages.insert_one(msg_doc)

            # Update customer last_contacted
            await self.db.customers.update_one(
                {"_id": customer_id},
                {"$set": {"last_contacted": datetime.utcnow(), "last_message": message[:200]}},
            )

            # Fetch user's WhatsApp instance name
            user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
            instance_name = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)

            # Send via Evolution API
            evo_msg_id: Optional[str] = None
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    if media_url:
                        mtype = (media_type or "document").lower()
                        payload = {
                            "number": to_number,
                            "mediatype": mtype,
                            "media": media_url,
                            "caption": message,
                        }
                        if media_filename:
                            payload["fileName"] = media_filename
                        evo_resp = await client.post(
                            f"{self.base_url}/message/sendMedia/{instance_name}",
                            headers=self._headers(),
                            json=payload,
                        )
                    else:
                        evo_resp = await client.post(
                            f"{self.base_url}/message/sendText/{instance_name}",
                            headers=self._headers(),
                            json={"number": to_number, "text": message},
                        )

                    if evo_resp.status_code in (200, 201):
                        evo_data = evo_resp.json()
                        evo_msg_id = (
                            evo_data.get("key", {}).get("id")
                            or evo_data.get("id")
                        )
                        if evo_msg_id:
                            await self.db.messages.update_one(
                                {"_id": message_id},
                                {"$set": {"evo_message_id": evo_msg_id}},
                            )
                    else:
                        logger.warning(f"[send_message] Evolution API {evo_resp.status_code}: {evo_resp.text[:200]}")
            except Exception as evo_err:
                logger.error(f"[send_message] Evolution API error: {evo_err}")
                # Message already stored in DB — don't fail the whole request

            return {
                "status": "success",
                "customer_id": customer_id,
                "message_id": message_id,
                "evo_message_id": evo_msg_id,
                "customer_name": customer_name or (customer.get("name") if customer else f"Contact {to_number[-4:]}"),
                "created_new_contact": customer is None,
            }

        except Exception as e:
            logger.error(f"[send_message] error: {e}")
            raise

    # ── Contact and history sync ─────────────────────────────────────────────

    async def fetch_contacts(self, user_id: str) -> dict:
        """Pull all WhatsApp contacts into the customers collection."""
        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        instance_name = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.base_url}/contacts/findContacts/{instance_name}",
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return {"status": "error", "message": resp.text[:200]}

                contacts = resp.json()
                if isinstance(contacts, dict):
                    contacts = contacts.get("contacts", contacts.get("data", []))

            created = 0
            updated = 0
            for contact in contacts:
                jid = contact.get("id") or contact.get("jid") or ""
                if "@g.us" in jid or "@broadcast" in jid:
                    continue  # skip groups
                phone = _jid_to_phone(jid)
                if not phone or len(phone) < 6:
                    continue

                name = (
                    contact.get("pushName")
                    or contact.get("name")
                    or contact.get("notify")
                    or f"Contact {phone[-4:]}"
                )

                existing = await self.db.customers.find_one({
                    "user_id": user_id,
                    "phone_number": phone,
                })
                if existing:
                    # Update name only if it's a fallback placeholder
                    current_name = existing.get("name", "")
                    is_fallback = (
                        current_name == phone
                        or re.match(r"^(Customer|Contact)\s+\d+$", current_name) is not None
                    )
                    if name and is_fallback and not re.match(r"^(Customer|Contact)\s+\d+$", name):
                        await self.db.customers.update_one(
                            {"_id": existing["_id"]},
                            {"$set": {"name": name, "synced_from_whatsapp": True}},
                        )
                        updated += 1
                else:
                    await self.db.customers.insert_one({
                        "_id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "name": name,
                        "phone_number": phone,
                        "notes": "",
                        "tags": ["New"],
                        "created_at": datetime.utcnow(),
                        "auto_created": True,
                        "synced_from_whatsapp": True,
                        "is_customer": False,
                    })
                    created += 1

            return {"status": "success", "created": created, "updated": updated, "total": len(contacts)}

        except Exception as e:
            logger.error(f"[fetch_contacts] {user_id}: {e}")
            return {"status": "error", "message": str(e)}

    async def fetch_chat_history(self, user_id: str, limit: int = 50) -> dict:
        """Pull recent chat messages from WhatsApp into the messages collection."""
        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        instance_name = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                # Get list of chats
                chats_resp = await client.post(
                    f"{self.base_url}/chat/findChats/{instance_name}",
                    headers=self._headers(),
                    json={},
                )
                if chats_resp.status_code not in (200, 201):
                    return {"status": "error", "message": chats_resp.text[:200]}

                chats_data = chats_resp.json()
                if isinstance(chats_data, dict):
                    chats = chats_data.get("chats", chats_data.get("data", []))
                else:
                    chats = chats_data if isinstance(chats_data, list) else []

            imported = 0
            for chat in chats[:100]:  # cap at 100 chats
                jid = chat.get("id") or chat.get("remoteJid") or ""
                if "@g.us" in jid or "@broadcast" in jid:
                    continue
                phone = _jid_to_phone(jid)
                if not phone:
                    continue

                try:
                    msgs_imported = await self._import_chat_messages(user_id, instance_name, phone, jid, limit=20)
                    imported += msgs_imported
                except Exception as chat_err:
                    logger.warning(f"[fetch_chat_history] chat {jid} error: {chat_err}")

            return {"status": "success", "messages_imported": imported}

        except Exception as e:
            logger.error(f"[fetch_chat_history] {user_id}: {e}")
            return {"status": "error", "message": str(e)}

    async def fetch_history_for_contact(self, user_id: str, phone: str, customer_id: str) -> dict:
        """Pull chat history for a specific contact."""
        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        instance_name = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)
        jid = f"{phone}@s.whatsapp.net"
        try:
            imported = await self._import_chat_messages(user_id, instance_name, phone, jid, limit=50)
            return {"status": "success", "messages_imported": imported}
        except Exception as e:
            logger.error(f"[fetch_history_for_contact] {phone}: {e}")
            return {"status": "error", "message": str(e)}

    async def _import_chat_messages(
        self, user_id: str, instance_name: str, phone: str, jid: str, limit: int = 20
    ) -> int:
        """Fetch messages for one JID and upsert into DB. Returns count imported."""
        customer = await self.db.customers.find_one({"user_id": user_id, "phone_number": phone})
        if not customer:
            return 0

        customer_id = customer["_id"]
        imported = 0

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/findMessages/{instance_name}",
                    headers=self._headers(),
                    json={"where": {"key.remoteJid": jid}, "limit": limit},
                )
                if resp.status_code not in (200, 201):
                    return 0

                data = resp.json()
                msgs = data if isinstance(data, list) else data.get("messages", data.get("data", []))

            for m in msgs:
                evo_id = (m.get("key") or {}).get("id") or m.get("id")
                if not evo_id:
                    continue
                # Skip if already stored
                if await self.db.messages.find_one({"evo_message_id": evo_id, "user_id": user_id}):
                    continue

                key = m.get("key", {})
                msg_obj = m.get("message") or {}
                body, mtype, img_url, fname = _extract_message_body(msg_obj)
                from_me = key.get("fromMe", False)
                ts = m.get("messageTimestamp")
                created = datetime.utcfromtimestamp(ts) if ts else datetime.utcnow()

                msg_doc = {
                    "_id": str(uuid.uuid4()),
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "direction": "outgoing" if from_me else "incoming",
                    "content": body,
                    "message_type": mtype,
                    "from_number": phone,
                    "remote_jid": jid,
                    "evo_message_id": evo_id,
                    "created_at": created,
                    "synced_from_history": True,
                }
                if img_url:
                    msg_doc["image_url"] = img_url
                if fname:
                    msg_doc["file_name"] = fname

                try:
                    await self.db.messages.insert_one(msg_doc)
                    imported += 1
                except Exception:
                    pass  # duplicate key — already there

        except Exception as e:
            logger.warning(f"[_import_chat_messages] {jid}: {e}")

        return imported

    # ── Profile pictures ─────────────────────────────────────────────────────

    async def fetch_profile_picture(self, user_id: str, phone: str) -> Optional[str]:
        """Return the WhatsApp profile picture URL for a phone number, or None."""
        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        instance_name = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/chat/fetchProfilePictureUrl/{instance_name}",
                    headers=self._headers(),
                    params={"number": phone},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return data.get("profilePictureUrl") or data.get("url") or None
        except Exception as e:
            logger.debug(f"[fetch_profile_picture] {phone}: {e}")
        return None

    async def fetch_profile_pictures_bulk(self, user_id: str) -> dict:
        """Fetch and store profile pictures for all contacts of a user."""
        customers = await self.db.customers.find(
            {"user_id": user_id, "profile_picture": {"$exists": False}},
            {"_id": 1, "phone_number": 1},
        ).to_list(200)

        updated = 0
        for c in customers:
            pic = await self.fetch_profile_picture(user_id, c["phone_number"])
            if pic:
                await self.db.customers.update_one(
                    {"_id": c["_id"]},
                    {"$set": {"profile_picture": pic}},
                )
                updated += 1

        return {"status": "success", "updated": updated, "checked": len(customers)}

    # ── Read receipts ────────────────────────────────────────────────────────

    async def mark_as_read(self, instance_name: str, remote_jid: str, evo_msg_id: str) -> None:
        """Send a blue-tick read receipt for a message."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self.base_url}/chat/markChatAsRead/{instance_name}",
                    headers=self._headers(),
                    json={
                        "readMessages": [
                            {"remoteJid": remote_jid, "id": evo_msg_id, "fromMe": False}
                        ]
                    },
                )
        except Exception as e:
            logger.debug(f"[mark_as_read] {evo_msg_id}: {e}")

    # ── Webhook handlers ─────────────────────────────────────────────────────

    async def find_user_by_instance(self, instance_name: str) -> Optional[dict]:
        """Return the user document whose WhatsApp instance_name matches."""
        try:
            user = await self.db.users.find_one(
                {"whatsapp.instance_name": instance_name}
            )
            if user:
                return user
            # Fallback: derive user_id from instance name (user_abc123 → abc123)
            if instance_name.startswith("user_"):
                derived_id = instance_name[len("user_"):].replace("_", "-")
                return await self.db.users.find_one({"_id": derived_id})
        except Exception as e:
            logger.warning(f"[find_user_by_instance] {instance_name}: {e}")
        return None

    async def handle_connection_update(self, instance_name: str, data: dict) -> None:
        """Persist connection state changes from Evolution API webhook."""
        try:
            state = data.get("state") or (data.get("instance") or {}).get("state", "")
            user = await self.find_user_by_instance(instance_name)
            if not user:
                logger.warning(f"[handle_connection_update] no user for instance {instance_name}")
                return

            update: dict = {"whatsapp.connection_state": state}

            if state == "open":
                update["whatsapp.connected"] = True
                # Extract phone number if provided
                wuid = (data.get("instance") or {}).get("wuid", "")
                if wuid:
                    update["whatsapp.phone_number"] = _jid_to_phone(wuid)
            elif state in ("close", "connecting"):
                update["whatsapp.connected"] = False

            await self.db.users.update_one(
                {"_id": user["_id"]},
                {"$set": update},
            )
            logger.info(f"[handle_connection_update] user={user['_id']} state={state}")
        except Exception as e:
            logger.error(f"[handle_connection_update] {instance_name}: {e}")

    async def handle_message_update(self, instance_name: str, data: dict) -> None:
        """Update message delivery/read status from Evolution API webhook."""
        try:
            user = await self.find_user_by_instance(instance_name)
            if not user:
                return

            # Evolution sends either a list or a single update dict
            updates = data if isinstance(data, list) else [data]
            for upd in updates:
                key = upd.get("key", {})
                evo_id = key.get("id")
                status_raw = (upd.get("update") or {}).get("status") or upd.get("status", "")
                if not evo_id:
                    continue

                status_map = {
                    "PENDING":   "pending",
                    "SERVER_ACK": "sent",
                    "DELIVERY_ACK": "delivered",
                    "READ":      "read",
                    "PLAYED":    "read",
                    "ERROR":     "failed",
                }
                status = status_map.get(status_raw.upper() if status_raw else "", status_raw.lower())

                result = await self.db.messages.update_many(
                    {"evo_message_id": evo_id, "user_id": user["_id"]},
                    {"$set": {"delivery_status": status}},
                )
                if result.modified_count:
                    logger.debug(f"[handle_message_update] {evo_id} → {status}")

        except Exception as e:
            logger.error(f"[handle_message_update] {instance_name}: {e}")

    async def handle_incoming_message(self, instance_name: str, data: dict) -> Optional[dict]:
        """
        Parse an Evolution API messages.upsert webhook payload.

        Returns a dict with: user, from_number, body, push_name, from_me,
        evo_message_id, remote_jid, message_type, image_url, file_name.
        Returns None if the message should be ignored (no user, group, status update, etc.).
        """
        try:
            user = await self.find_user_by_instance(instance_name)
            if not user:
                logger.warning(f"[handle_incoming_message] no user for instance {instance_name}")
                return None

            # Evolution API sends either a single message dict or a list
            messages = data if isinstance(data, list) else [data]
            if not messages:
                return None

            # Process only the first message in the batch
            msg_data = messages[0]

            key = msg_data.get("key", {})
            remote_jid = key.get("remoteJid", "")
            from_me = bool(key.get("fromMe", False))
            evo_msg_id = key.get("id", "")

            # Skip group messages
            if "@g.us" in remote_jid or "@broadcast" in remote_jid:
                return None

            # Skip status broadcasts
            if "status@broadcast" in remote_jid:
                return None

            from_number = _jid_to_phone(remote_jid)
            if not from_number:
                return None

            push_name = msg_data.get("pushName") or msg_data.get("notifyName") or ""

            msg_obj = msg_data.get("message") or {}

            # Skip protocol/ephemeral messages
            if "protocolMessage" in msg_obj or "senderKeyDistributionMessage" in msg_obj:
                return None

            body, message_type, image_url, file_name = _extract_message_body(msg_obj)

            return {
                "user": user,
                "from_number": from_number,
                "body": body,
                "push_name": push_name,
                "from_me": from_me,
                "evo_message_id": evo_msg_id,
                "remote_jid": remote_jid,
                "message_type": message_type,
                "image_url": image_url,
                "file_name": file_name,
            }

        except Exception as e:
            logger.error(f"[handle_incoming_message] {instance_name}: {e}")
            return None


# ── Singleton ────────────────────────────────────────────────────────────────

_whatsapp_service: Optional[WhatsAppService] = None


def get_whatsapp_service(db) -> WhatsAppService:
    """Return singleton WhatsAppService, recreating if db changes."""
    global _whatsapp_service
    if _whatsapp_service is None or _whatsapp_service.db is not db:
        _whatsapp_service = WhatsAppService(db)
    return _whatsapp_service

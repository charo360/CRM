"""WAHA provider for Zilo's WhatsApp integration.

This adapter keeps the public service contract used by the rest of the backend,
but uses WAHA's persistent named sessions instead of recreating a gateway
instance whenever a customer asks for a fresh pairing code.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import re
import uuid
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import quote

import httpx

from whatsapp_service import WhatsAppService as EvolutionWhatsAppService, _jid_to_phone

logger = logging.getLogger(__name__)

WAHA_API_URL = os.environ.get("WAHA_API_URL", "").rstrip("/")
WAHA_NODE_URLS = tuple(
    url.strip().rstrip("/")
    for url in os.environ.get("WAHA_API_URLS", WAHA_API_URL).split(",")
    if url.strip()
)
WAHA_API_KEY = os.environ.get("WAHA_API_KEY", "")
WAHA_WEBHOOK_SECRET = os.environ.get("WAHA_WEBHOOK_SECRET", "")
WAHA_VERIFY_SSL = os.environ.get("WAHA_VERIFY_SSL", "true").lower() in ("true", "1", "yes")


def waha_config_error() -> Optional[str]:
    """Return a safe configuration error instead of leaking WAHA credentials."""
    if not WAHA_NODE_URLS:
        return "WhatsApp linking is not configured on this server. Please contact support."
    if not WAHA_API_KEY:
        return "WhatsApp linking is not configured on this server. Please contact support."
    if not WAHA_WEBHOOK_SECRET:
        return "WhatsApp linking is not configured on this server. Please contact support."
    if not os.environ.get("WEBHOOK_BASE_URL", "").strip():
        return "WhatsApp linking is not configured on this server. Please contact support."
    return None


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _chat_id(phone: str) -> str:
    """Return WAHA's canonical personal-chat identifier."""
    number = _digits(phone)
    return f"{number}@c.us"


def _message_type(media: Optional[dict]) -> str:
    if not media:
        return "text"
    mimetype = str(media.get("mimetype") or "").lower()
    if mimetype.startswith("image/"):
        return "image"
    if mimetype.startswith("video/"):
        return "video"
    if mimetype.startswith("audio/"):
        return "audio"
    return "document"


def _looks_like_image(url: Optional[str], media_type: Optional[str]) -> bool:
    """Classify product-image URLs correctly when callers omit a MIME type."""
    if (media_type or "").lower() == "image":
        return True
    return bool(re.search(r"\.(?:jpe?g|png|gif|webp)(?:\?|$)", url or "", re.IGNORECASE))


def _image_mimetype(url: Optional[str]) -> str:
    """Keep a supplied image's content type accurate for WAHA sendImage."""
    suffix = (url or "").split("?", 1)[0].rsplit(".", 1)[-1].lower()
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "webp": "image/webp",
    }.get(suffix, "image/jpeg")


class WahaWhatsAppService(EvolutionWhatsAppService):
    """WAHA implementation of the WhatsApp service used throughout Zilo."""

    provider = "waha"

    def __init__(self, db):
        # Reuse billing, customer lookup and watchdog helpers from the original
        # service. All provider network calls are overridden below.
        super().__init__(db)
        self.node_urls = WAHA_NODE_URLS
        self.base_url = self.node_urls[0] if self.node_urls else ""
        self._api_key = WAHA_API_KEY
        self.verify_ssl = WAHA_VERIFY_SSL

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _webhook_config(self) -> dict:
        webhook_base = os.environ["WEBHOOK_BASE_URL"].rstrip("/")
        return {
            "metadata": {"provider": "zilo"},
            "webhooks": [{
                "url": f"{webhook_base}/api/webhooks/waha",
                "events": ["session.status", "message", "message.ack"],
                "hmac": {"key": WAHA_WEBHOOK_SECRET},
            }],
        }

    async def _node_for_user(self, user_id: str) -> tuple[int, str]:
        """Keep every business on one node across calls and deployments."""
        if not self.node_urls:
            raise RuntimeError("WAHA_API_URL is not configured")
        user = await self.db.users.find_one({"_id": user_id}, {"whatsapp.waha_node": 1})
        stored = (user or {}).get("whatsapp", {}).get("waha_node")
        if isinstance(stored, int) and 0 <= stored < len(self.node_urls):
            return stored, self.node_urls[stored]
        # A stable, even distribution means an existing account never switches
        # nodes merely because the process restarts.
        index = int(hashlib.sha256(str(user_id).encode("utf-8")).hexdigest(), 16) % len(self.node_urls)
        return index, self.node_urls[index]

    async def _start_session(self, base_url: str, instance_name: str) -> dict:
        """Create/update/start a session without deleting an existing auth state."""
        payload = {"name": instance_name, "config": self._webhook_config()}
        async with httpx.AsyncClient(timeout=30, verify=self.verify_ssl) as client:
            response = await client.post(
                f"{base_url}/api/sessions/start", headers=self._headers(), json=payload
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"WAHA session start failed ({response.status_code})")
        return response.json()

    async def _request_pairing_code(self, base_url: str, instance_name: str, phone: str) -> dict:
        async with httpx.AsyncClient(timeout=25, verify=self.verify_ssl) as client:
            response = await client.post(
                f"{base_url}/api/{quote(instance_name, safe='')}/auth/request-code",
                headers=self._headers(),
                json={"phoneNumber": _digits(phone)},
            )
        if response.status_code not in (200, 201):
            return {"status": "error", "message": "Pairing code is not available. Use the QR link instead."}
        data = response.json()
        code = data.get("code", "")
        return {"status": "pairing", "pairing_code": code, "pairing_data": data}

    async def create_instance(self, user_id: str, phone: str) -> dict:
        """Start a persistent WAHA session, then obtain a phone pairing code."""
        if error := waha_config_error():
            return {"status": "error", "message": error}
        instance_name = self._instance_name(user_id)
        try:
            node, base_url = await self._node_for_user(user_id)
            session = await self._start_session(base_url, instance_name)
            await self.db.users.update_one(
                {"_id": user_id},
                {"$set": {
                    "whatsapp.provider": self.provider,
                    "whatsapp.waha_node": node,
                    "whatsapp.instance_name": instance_name,
                    "whatsapp.status": "pairing_pending",
                    "whatsapp.connected": False,
                    "whatsapp.created_at": datetime.utcnow(),
                }},
            )
            result = await self._request_pairing_code(base_url, instance_name, phone)
            if result.get("pairing_code"):
                return result

            # WAHA documents QR as the necessary fallback when phone pairing is
            # unavailable. Keep the session; never recreate it for a refresh.
            qr = await self.get_qr_code(user_id)
            if qr.get("qr_base64"):
                return {"status": "qr_ready", **qr}
            return {
                "status": "error",
                "message": result.get("message") or f"Session is {session.get('status', 'starting')}. Try QR linking.",
            }
        except Exception as exc:
            logger.exception("[waha.create_instance] %s", user_id)
            return {"status": "error", "message": str(exc)}

    async def refresh_pairing_code(self, user_id: str, phone: str) -> dict:
        """Refresh only the code; session credentials are intentionally retained."""
        if error := waha_config_error():
            return {"status": "error", "message": error}
        try:
            _, base_url = await self._node_for_user(user_id)
            return await self._request_pairing_code(base_url, self._instance_name(user_id), phone)
        except Exception as exc:
            logger.warning("[waha.refresh_pairing_code] %s", exc)
            return {"status": "error", "message": str(exc)}

    async def create_qr_instance(self, user_id: str) -> dict:
        if error := waha_config_error():
            return {"status": "error", "message": error}
        instance_name = self._instance_name(user_id)
        try:
            node, base_url = await self._node_for_user(user_id)
            await self._start_session(base_url, instance_name)
            await self.db.users.update_one(
                {"_id": user_id},
                {"$set": {
                    "whatsapp.provider": self.provider,
                    "whatsapp.waha_node": node,
                    "whatsapp.instance_name": instance_name,
                    "whatsapp.status": "qr_pending",
                    "whatsapp.connected": False,
                    "whatsapp.created_at": datetime.utcnow(),
                }},
            )
            return await self.get_qr_code(user_id)
        except Exception as exc:
            logger.exception("[waha.create_qr_instance] %s", user_id)
            return {"status": "error", "message": str(exc)}

    async def get_qr_code(self, user_id: str) -> dict:
        instance_name = self._instance_name(user_id)
        status = await self.get_instance_status(user_id)
        if status.get("connected"):
            return {"status": "connected", "qr_base64": "", "connection_state": "open"}
        try:
            _, base_url = await self._node_for_user(user_id)
            headers = self._headers()
            headers["Accept"] = "application/json"
            async with httpx.AsyncClient(timeout=20, verify=self.verify_ssl) as client:
                response = await client.get(
                    f"{base_url}/api/{quote(instance_name, safe='')}/auth/qr?format=image",
                    headers=headers,
                )
            if response.status_code != 200:
                return {"status": "qr_pending", "qr_base64": "", "connection_state": status.get("status", "")}
            data = response.json()
            encoded = data.get("data") or data.get("base64") or ""
            if encoded and not encoded.startswith("data:"):
                encoded = f"data:{data.get('mimetype', 'image/png')};base64,{encoded}"
            return {"status": "qr_ready", "qr_base64": encoded, "connection_state": status.get("status", "")}
        except Exception as exc:
            logger.warning("[waha.get_qr_code] %s", exc)
            return {"status": "qr_pending", "qr_base64": "", "connection_state": status.get("status", "")}

    async def get_instance_status(self, user_id: str) -> dict:
        instance_name = self._instance_name(user_id)
        try:
            _, base_url = await self._node_for_user(user_id)
            async with httpx.AsyncClient(timeout=12, verify=self.verify_ssl) as client:
                response = await client.get(
                    f"{base_url}/api/sessions/{quote(instance_name, safe='')}", headers=self._headers()
                )
            if response.status_code == 404:
                return {"connected": False, "status": "not_found"}
            if response.status_code != 200:
                return {"connected": False, "status": "error"}
            data = response.json()
            state = str(data.get("status") or "").upper()
            me = data.get("me") or {}
            number = _jid_to_phone(str(me.get("id") or "")) or None
            return {"connected": state == "WORKING", "status": state.lower() or "unknown", "number": number}
        except Exception as exc:
            logger.warning("[waha.get_instance_status] %s: %s", user_id, exc)
            return {"connected": False, "status": "error"}

    async def disconnect_instance(self, user_id: str) -> dict:
        instance_name = self._instance_name(user_id)
        results: dict = {}
        try:
            _, base_url = await self._node_for_user(user_id)
            async with httpx.AsyncClient(timeout=20, verify=self.verify_ssl) as client:
                logout = await client.post(
                    f"{base_url}/api/sessions/{quote(instance_name, safe='')}/logout", headers=self._headers()
                )
                results["logout"] = logout.status_code
                delete = await client.delete(
                    f"{base_url}/api/sessions/{quote(instance_name, safe='')}", headers=self._headers()
                )
                results["delete"] = delete.status_code
            await self.db.users.update_one(
                {"_id": user_id},
                {"$set": {"whatsapp.connected": False, "whatsapp.status": "disconnected", "whatsapp.disconnected_at": datetime.utcnow()}},
            )
            return {"status": "success", "results": results}
        except Exception as exc:
            logger.warning("[waha.disconnect_instance] %s", exc)
            return {"status": "error", "message": str(exc), "results": results}

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
        """Send via WAHA and persist only an honestly accepted/failed result."""
        limits = await self.check_message_limit(user_id)
        if not limits.get("dashboard_access"):
            return {"status": "limit_reached", "message": "Subscribe or start a free trial to send WhatsApp messages."}
        if limits.get("monthly_remaining", 0) <= 0 and limits.get("monthly_limit", 0) > 0:
            return {"status": "limit_reached", "message": f"Monthly limit of {limits['monthly_limit']:,} messages reached. Upgrade your plan."}
        if limits.get("remaining", 0) <= 0:
            return {"status": "limit_reached", "message": f"Daily limit of {limits['daily_limit']} messages reached."}

        customer = await self.db.customers.find_one({"user_id": user_id, "phone_number": to_number})
        if customer:
            customer_id = customer["_id"]
        else:
            customer_id = str(uuid.uuid4())
            await self.db.customers.insert_one({
                "_id": customer_id, "user_id": user_id,
                "name": customer_name or f"Contact {to_number[-4:]}", "phone_number": to_number,
                "notes": "", "tags": ["New"], "last_contacted": datetime.utcnow(),
                "created_at": datetime.utcnow(), "auto_created": False, "business_initiated": True,
            })

        message_id = str(uuid.uuid4())
        is_image = _looks_like_image(media_url, media_type)
        doc = {
            "_id": message_id, "customer_id": customer_id, "user_id": user_id,
            "direction": "outgoing", "content": message,
            "message_type": "image" if media_url and is_image else ("document" if media_url else "text"),
            "from_number": to_number, "remote_jid": _chat_id(to_number),
            "created_at": datetime.utcnow(), "send_context": send_context,
            "delivery_status": "pending",
        }
        if media_url:
            doc["image_url"] = media_url
        if media_filename:
            doc["file_name"] = media_filename
        await self.db.messages.insert_one(doc)
        await self.db.customers.update_one(
            {"_id": customer_id}, {"$set": {"last_contacted": datetime.utcnow(), "last_message": message[:200]}}
        )

        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        session = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)
        _, base_url = await self._node_for_user(user_id)
        if media_url:
            path = "/api/sendImage" if is_image else "/api/sendFile"
            mimetype = _image_mimetype(media_url) if is_image else "application/octet-stream"
            payload = {
                "session": session, "chatId": _chat_id(to_number), "caption": message,
                "file": {"url": media_url, "mimetype": mimetype, "filename": media_filename},
            }
        else:
            path = "/api/sendText"
            payload = {"session": session, "chatId": _chat_id(to_number), "text": message}

        accepted = False
        provider_message_id = None
        delivery_error = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=25, verify=self.verify_ssl) as client:
                    response = await client.post(f"{base_url}{path}", headers=self._headers(), json=payload)
                if response.status_code in (200, 201):
                    accepted = True
                    data = response.json()
                    provider_message_id = data.get("id") or (data.get("key") or {}).get("id")
                    break
                delivery_error = f"WAHA API {response.status_code}: {response.text[:200]}"
                if response.status_code < 500 and response.status_code != 429:
                    break
            except Exception as exc:
                delivery_error = str(exc)
            if attempt < 2:
                await asyncio.sleep((2 ** attempt) * (1 + random.random() * 0.5))

        if accepted:
            updates = {"delivery_status": "sent"}
            if provider_message_id:
                updates["evo_message_id"] = provider_message_id  # legacy field name retained for existing DB queries
            await self.db.messages.update_one({"_id": message_id}, {"$set": updates})
            return {
                "status": "success", "delivered": True, "customer_id": customer_id,
                "message_id": message_id, "evo_message_id": provider_message_id,
                "customer_name": customer_name or (customer or {}).get("name", f"Contact {to_number[-4:]}"),
                "created_new_contact": customer is None,
            }

        delivery_error = delivery_error or "WAHA did not accept the message"
        await self.db.messages.update_one(
            {"_id": message_id}, {"$set": {"delivery_status": "failed", "delivery_error": delivery_error[:500]}}
        )
        await self.db.failed_sends.insert_one({
            "message_id": message_id, "user_id": user_id, "to_number": to_number,
            "error": delivery_error[:500], "send_context": send_context, "created_at": datetime.utcnow(),
        })
        return {"status": "error", "message": "Message was not sent. Please try again.", "delivery_error": delivery_error, "message_id": message_id}

    async def fetch_contacts(self, user_id: str) -> dict:
        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        session = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)
        _, base_url = await self._node_for_user(user_id)
        try:
            async with httpx.AsyncClient(timeout=45, verify=self.verify_ssl) as client:
                response = await client.get(
                    f"{base_url}/api/contacts/all", headers=self._headers(),
                    params={"session": session, "limit": 500, "offset": 0},
                )
            if response.status_code != 200:
                return {"status": "error", "message": response.text[:200]}
            contacts = response.json()
            created = updated = 0
            for contact in contacts if isinstance(contacts, list) else []:
                if contact.get("isGroup"):
                    continue
                phone = _digits(str(contact.get("number") or _jid_to_phone(str(contact.get("id") or ""))))
                if len(phone) < 6:
                    continue
                name = contact.get("name") or contact.get("pushname") or contact.get("shortName") or f"Contact {phone[-4:]}"
                existing = await self.db.customers.find_one({"user_id": user_id, "phone_number": phone})
                if existing:
                    if re.match(r"^(Customer|Contact)\s+\d+$", existing.get("name", "")) and not re.match(r"^(Customer|Contact)\s+\d+$", name):
                        await self.db.customers.update_one({"_id": existing["_id"]}, {"$set": {"name": name, "synced_from_whatsapp": True}})
                        updated += 1
                else:
                    await self.db.customers.insert_one({
                        "_id": str(uuid.uuid4()), "user_id": user_id, "name": name, "phone_number": phone,
                        "notes": "", "tags": ["New"], "created_at": datetime.utcnow(), "auto_created": True,
                        "synced_from_whatsapp": True, "is_customer": False,
                    })
                    created += 1
            return {"status": "success", "created": created, "updated": updated, "total": len(contacts) if isinstance(contacts, list) else 0}
        except Exception as exc:
            logger.error("[waha.fetch_contacts] %s", exc)
            return {"status": "error", "message": str(exc)}

    async def _import_messages(self, user_id: str, session: str, chat_id: str, limit: int = 50) -> int:
        phone = _digits(_jid_to_phone(chat_id))
        customer = await self.db.customers.find_one({"user_id": user_id, "phone_number": phone})
        if not customer:
            return 0
        try:
            _, base_url = await self._node_for_user(user_id)
            async with httpx.AsyncClient(timeout=35, verify=self.verify_ssl) as client:
                response = await client.get(
                    f"{base_url}/api/{quote(session, safe='')}/chats/{quote(chat_id, safe='')}/messages",
                    headers=self._headers(), params={"limit": limit, "downloadMedia": "false"},
                )
            if response.status_code != 200:
                return 0
            messages = response.json()
            imported = 0
            for item in messages if isinstance(messages, list) else []:
                provider_id = item.get("id")
                if not provider_id or await self.db.messages.find_one({"evo_message_id": provider_id, "user_id": user_id}):
                    continue
                media = item.get("media") or {}
                timestamp = item.get("timestamp")
                created_at = datetime.utcfromtimestamp(timestamp) if isinstance(timestamp, (int, float)) else datetime.utcnow()
                doc = {
                    "_id": str(uuid.uuid4()), "customer_id": customer["_id"], "user_id": user_id,
                    "direction": "outgoing" if item.get("fromMe") else "incoming", "content": item.get("body") or "",
                    "message_type": _message_type(media), "from_number": phone, "remote_jid": chat_id,
                    "evo_message_id": provider_id, "created_at": created_at, "synced_from_history": True,
                }
                if media.get("url"):
                    doc["image_url"] = media["url"]
                if media.get("filename"):
                    doc["file_name"] = media["filename"]
                try:
                    await self.db.messages.insert_one(doc)
                    imported += 1
                except Exception:
                    pass
            return imported
        except Exception as exc:
            logger.warning("[waha._import_messages] %s", exc)
            return 0

    async def fetch_chat_history(self, user_id: str, limit: int = 50) -> dict:
        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        session = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)
        try:
            _, base_url = await self._node_for_user(user_id)
            async with httpx.AsyncClient(timeout=45, verify=self.verify_ssl) as client:
                response = await client.get(
                    f"{base_url}/api/{quote(session, safe='')}/chats", headers=self._headers(),
                    params={"limit": 100, "offset": 0, "sortBy": "messageTimestamp", "sortOrder": "desc"},
                )
            if response.status_code != 200:
                return {"status": "error", "message": response.text[:200]}
            chats = response.json()
            imported = 0
            for chat in chats if isinstance(chats, list) else []:
                chat_id = str(chat.get("id") or "")
                if not chat_id or "@g.us" in chat_id or "@broadcast" in chat_id:
                    continue
                imported += await self._import_messages(user_id, session, chat_id, min(limit, 50))
            return {"status": "success", "messages_imported": imported}
        except Exception as exc:
            logger.error("[waha.fetch_chat_history] %s", exc)
            return {"status": "error", "message": str(exc)}

    async def fetch_history_for_contact(self, user_id: str, phone: str, customer_id: str) -> dict:
        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        session = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)
        imported = await self._import_messages(user_id, session, _chat_id(phone), 50)
        return {"status": "success", "messages_imported": imported}

    async def fetch_profile_picture(self, user_id: str, phone: str) -> Optional[str]:
        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp": 1})
        session = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)
        try:
            _, base_url = await self._node_for_user(user_id)
            async with httpx.AsyncClient(timeout=15, verify=self.verify_ssl) as client:
                response = await client.get(
                    f"{base_url}/api/contacts/profile-picture", headers=self._headers(),
                    params={"contactId": _chat_id(phone), "session": session},
                )
            if response.status_code == 200:
                return response.json().get("profilePictureURL")
        except Exception as exc:
            logger.debug("[waha.fetch_profile_picture] %s", exc)
        return None

    async def mark_as_read(self, instance_name: str, remote_jid: str, evo_msg_id: str) -> None:
        try:
            user = await self.find_user_by_instance(instance_name)
            if not user:
                return
            _, base_url = await self._node_for_user(user["_id"])
            async with httpx.AsyncClient(timeout=15, verify=self.verify_ssl) as client:
                await client.post(
                    f"{base_url}/api/{quote(instance_name, safe='')}/chats/{quote(remote_jid, safe='')}/messages/read",
                    headers=self._headers(), json={"messages": 1, "days": 1},
                )
        except Exception as exc:
            logger.debug("[waha.mark_as_read] %s", exc)

    async def delete_message_for_everyone(
        self, user_id: str, instance_name: str, remote_jid: str, message_id: str
    ) -> dict:
        """Revoke an outgoing message through WAHA's GOWS-supported endpoint."""
        try:
            _, base_url = await self._node_for_user(user_id)
            async with httpx.AsyncClient(timeout=15, verify=self.verify_ssl) as client:
                response = await client.delete(
                    f"{base_url}/api/{quote(instance_name, safe='')}/chats/"
                    f"{quote(remote_jid, safe='')}/messages/{quote(message_id, safe='')}",
                    headers=self._headers(),
                )
            if response.status_code not in (200, 201, 204):
                return {"status": "error", "message": response.text[:200]}
            return {"status": "success"}
        except Exception as exc:
            logger.warning("[waha.delete_message_for_everyone] %s", exc)
            return {"status": "error", "message": str(exc)}

    async def handle_connection_update(self, instance_name: str, data: dict) -> None:
        state = str(data.get("status") or data.get("state") or "").upper()
        connected = state in ("WORKING", "OPEN", "CONNECTED")
        user = await self.find_user_by_instance(instance_name)
        if not user:
            return
        update = {
            "whatsapp.connection_state": state.lower(),
            "whatsapp.status": "connected" if connected else state.lower(),
            "whatsapp.connected": connected,
        }
        me = data.get("me") or (data.get("instance") or {}).get("wuid") or ""
        if isinstance(me, dict):
            me = me.get("id") or ""
        if me:
            update["whatsapp.phone_number"] = _jid_to_phone(str(me))
        if state == "FAILED":
            update["whatsapp.disconnected_at"] = datetime.utcnow()
        await self.db.users.update_one({"_id": user["_id"]}, {"$set": update})

    async def handle_message_update(self, instance_name: str, data: dict) -> None:
        user = await self.find_user_by_instance(instance_name)
        if not user:
            return
        message_id = data.get("id") or data.get("messageId") or (data.get("key") or {}).get("id")
        ack = data.get("ackName") or data.get("ack") or data.get("status") or ""
        ack_map = {"0": "pending", "1": "sent", "2": "delivered", "3": "read", "4": "read", "ERROR": "failed", "PENDING": "pending", "SERVER": "sent", "DEVICE": "delivered", "READ": "read", "PLAYED": "read"}
        if message_id:
            await self.db.messages.update_many(
                {"evo_message_id": message_id, "user_id": user["_id"]},
                {"$set": {"delivery_status": ack_map.get(str(ack).upper(), str(ack).lower())}},
            )

    async def handle_incoming_message(self, instance_name: str, data: dict) -> Optional[dict]:
        user = await self.find_user_by_instance(instance_name)
        if not user:
            return None
        from_me = bool(data.get("fromMe", False))
        remote_jid = str(data.get("chatId") or (data.get("to") if from_me else data.get("from")) or "")
        if not remote_jid or "@g.us" in remote_jid or "@broadcast" in remote_jid:
            return None
        phone = _digits(_jid_to_phone(remote_jid))
        if not phone:
            return None
        media = data.get("media") or {}
        return {
            "user": user, "from_number": phone, "body": data.get("body") or "",
            "push_name": data.get("pushName") or data.get("notifyName") or "", "from_me": from_me,
            "evo_message_id": data.get("id") or "", "remote_jid": remote_jid,
            "message_type": _message_type(media), "image_url": media.get("url"), "file_name": media.get("filename"),
        }

    async def handle_group_message(self, instance_name: str, data: dict) -> Optional[dict]:
        user = await self.find_user_by_instance(instance_name)
        if not user or data.get("fromMe"):
            return None
        group_jid = str(data.get("chatId") or data.get("from") or "")
        body = str(data.get("body") or "").strip()
        if "@g.us" not in group_jid or len(body) < 5:
            return None
        return {
            "user": user, "body": body, "push_name": data.get("pushName") or "Member",
            "group_jid": group_jid, "group_name": data.get("groupName") or group_jid.split("@", 1)[0],
        }

"""
WhatsApp Service — Evolution API
Handles instance lifecycle, message sending, contact sync, and webhook parsing.
"""
from __future__ import annotations

import asyncio
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
EVOLUTION_API_VERIFY_SSL: bool = os.environ.get("EVOLUTION_API_VERIFY_SSL", "true").lower() in ("true", "1", "yes")
WHATSAPP_PROVIDER: str = os.environ.get("WHATSAPP_PROVIDER", "waha").strip().lower()

# Randomized pause between consecutive broadcast/bulk sends (min, max) seconds.
# Human-like pacing is the single most important anti-ban measure for bulk
# sending through an unofficial gateway. Tunable via env without a deploy.
BROADCAST_DELAY: tuple = (
    float(os.environ.get("BROADCAST_DELAY_MIN", "3.0")),
    float(os.environ.get("BROADCAST_DELAY_MAX", "8.0")),
)

# Daily send throttle (monthly caps enforced via entitlements)
_DAILY_SEND_LIMITS: Dict[str, int] = {
    "free": 50,
    "trial": 500,
    "starter": 500,
    "standard": 2000,
    "pro": 5000,
}


def whatsapp_owner_id(user: dict) -> str:
    """Business (tenant) id used for Evolution instance naming and WhatsApp state."""
    raw = user.get("business_id") or user.get("_id") or user.get("id") or ""
    return str(raw) if raw is not None else ""


def evolution_config_error() -> Optional[str]:
    """Provider configuration check used by existing routes. Always WAHA now."""
    from waha_service import waha_config_error

    return waha_config_error()


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
        self.verify_ssl = EVOLUTION_API_VERIFY_SSL
        self._conn_throttle: Dict[str, float] = {}  # instance -> last processed timestamp

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
            async with httpx.AsyncClient(timeout=30, verify=self.verify_ssl) as client:
                # 1. Clean up existing stale instances first (like in QR flow)
                await self._delete_all_user_instances(client, user_id)
                await asyncio.sleep(1)

                # 2. Try creating instance with retries (for eventual consistency)
                last_body = ""
                created_ok = False
                for attempt in range(3):
                    if attempt > 0:
                        await asyncio.sleep(min(2 + attempt * 2, 8))

                    create_resp = await client.post(
                        f"{self.base_url}/instance/create",
                        headers=self._headers(),
                        json={
                            "instanceName": instance_name,
                            "number": phone,
                            "token": str(uuid.uuid4()),
                            "qrcode": False,
                            "integration": "WHATSAPP-BAILEYS",
                            "reject_call": False,
                            "groupsIgnore": True,
                        },
                    )
                    last_body = create_resp.text[:500]
                    logger.info(
                        "[create_instance] attempt=%s status=%s body=%s",
                        attempt + 1,
                        create_resp.status_code,
                        last_body[:300],
                    )

                    if create_resp.status_code in (200, 201):
                        created_ok = True
                        break

                    if self._create_conflict_response(last_body):
                        if await self._instance_exists(client, instance_name):
                            created_ok = True
                            break
                        await self._force_delete_instance(client, instance_name)
                        await asyncio.sleep(3)
                        continue

                if not created_ok:
                    return {"status": "error", "message": f"Instance creation failed: {last_body[:200]}"}

                # 3. Configure webhook on the new instance
                webhook_base = os.environ.get("WEBHOOK_BASE_URL", "http://host.docker.internal:8000")
                webhook_secret = os.environ.get("WEBHOOK_SECRET", os.environ.get("EVOLUTION_API_KEY", ""))
                
                webhook_cfg = {
                    "webhook": {
                        "enabled": True,
                        "url": f"{webhook_base}/api/webhooks/evolution",
                        "webhookByEvents": False,
                        "webhookBase64": False,
                        "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "CHATS_UPDATE", "CONNECTION_UPDATE"],
                    }
                }
                if webhook_secret:
                    webhook_cfg["webhook"]["headers"] = {"apikey": webhook_secret}

                try:
                    await client.post(
                        f"{self.base_url}/webhook/set/{instance_name}",
                        headers=self._headers(),
                        json=webhook_cfg,
                    )
                except Exception as web_err:
                    logger.warning(f"[create_instance] failed to set webhook: {web_err}")

                # 4. Update MongoDB user record to track pending connection
                await self.db.users.update_one(
                    {"_id": user_id},
                    {"$set": {
                        "whatsapp.instance_name": instance_name,
                        "whatsapp.status": "pairing_pending",
                        "whatsapp.connected": False,
                        "whatsapp.created_at": datetime.utcnow()
                    }},
                )

                # 5. Request pairing code
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
            async with httpx.AsyncClient(timeout=20, verify=self.verify_ssl) as client:
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
            async with httpx.AsyncClient(timeout=10, verify=self.verify_ssl) as client:
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
                    or (data.get("instance") or {}).get("status")
                    or ""
                ).lower()
                connected = state in ("open", "connected")
                number = (
                    data.get("number")
                    or (data.get("instance") or {}).get("wuid", "").split(":")[0].split("@")[0]
                    or None
                )
                return {"connected": connected, "status": state, "number": number}
        except Exception as e:
            logger.warning(f"[get_instance_status] {user_id}: {e}")
            return {"connected": False, "status": "error"}

    async def _force_delete_instance(self, client: httpx.AsyncClient, instance_name: str) -> None:
        """Best-effort logout + delete for one Evolution instance name."""
        for path in ("logout", "delete"):
            try:
                await client.delete(
                    f"{self.base_url}/instance/{path}/{instance_name}",
                    headers=self._headers(),
                )
            except Exception as e:
                logger.debug(f"[force_delete] {path}/{instance_name}: {e}")

    async def _delete_all_user_instances(self, client: httpx.AsyncClient, user_id: str) -> None:
        """
        Remove Evolution instances for this tenant (canonical name + any duplicates).
        Used before QR / pairing flows so stale instances do not block create.
        """
        canonical = self._instance_name(user_id)
        names: set[str] = {canonical}

        try:
            list_resp = await client.get(
                f"{self.base_url}/instance/fetchInstances",
                headers=self._headers(),
            )
            if list_resp.status_code == 200:
                payload = list_resp.json()
                raw = payload if isinstance(payload, list) else (
                    payload.get("instances")
                    or payload.get("response")
                    or payload.get("data")
                    or []
                )
                for item in raw:
                    if isinstance(item, str):
                        n = item
                    elif isinstance(item, dict):
                        n = (
                            item.get("instanceName")
                            or item.get("name")
                            or (item.get("instance") or {}).get("instanceName")
                        )
                    else:
                        n = None
                    if n and (n == canonical or n.startswith(canonical)):
                        names.add(n)
        except Exception as e:
            logger.warning(f"[_delete_all_user_instances] fetchInstances: {e}")

        for name in names:
            await self._force_delete_instance(client, name)

    @staticmethod
    def _create_conflict_response(text: str) -> bool:
        err = (text or "").lower()
        return any(
            token in err
            for token in ("already", "in use", "exists", "forbidden", "duplicate")
        )

    async def _instance_exists(self, client: httpx.AsyncClient, instance_name: str) -> bool:
        try:
            resp = await client.get(
                f"{self.base_url}/instance/fetchInstances",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return False
            payload = resp.json()
            raw = payload if isinstance(payload, list) else (
                payload.get("instances")
                or payload.get("response")
                or payload.get("data")
                or []
            )
            for item in raw:
                if isinstance(item, str):
                    n = item
                elif isinstance(item, dict):
                    n = item.get("instanceName") or item.get("name")
                else:
                    n = None
                if n == instance_name:
                    return True
        except Exception as e:
            logger.warning(f"[_instance_exists] {instance_name}: {e}")
        return False

    async def recreate_instance_for_qr(
        self,
        client: httpx.AsyncClient,
        user_id: str,
        *,
        extra_instance_names: Optional[List[str]] = None,
    ) -> str:
        """
        Delete stale Evolution instances for this tenant and create a fresh one for QR linking.
        Retries create when Evolution reports the name is still in use (eventual consistency).
        """
        instance_name = self._instance_name(user_id)
        extra = {n for n in (extra_instance_names or []) if n}
        extra.add(instance_name)

        await self._delete_all_user_instances(client, user_id)
        for name in extra:
            await self._force_delete_instance(client, name)
        await asyncio.sleep(1)

        last_body = ""
        for attempt in range(3):
            if attempt > 0:
                await asyncio.sleep(min(2 + attempt * 2, 8))

            create_resp = await client.post(
                f"{self.base_url}/instance/create",
                headers=self._headers(),
                json={
                    "instanceName": instance_name,
                    "token": str(uuid.uuid4()),
                    "qrcode": True,
                    "integration": "WHATSAPP-BAILEYS",
                    "reject_call": False,
                    "groupsIgnore": True,
                },
            )
            last_body = create_resp.text[:500]
            logger.info(
                "[recreate_instance_for_qr] attempt=%s status=%s body=%s",
                attempt + 1,
                create_resp.status_code,
                last_body[:300],
            )

            if create_resp.status_code in (200, 201):
                return instance_name

            if self._create_conflict_response(last_body):
                if await self._instance_exists(client, instance_name):
                    return instance_name
                await self._force_delete_instance(client, instance_name)
                await asyncio.sleep(3)
                continue

        raise RuntimeError(last_body or "Evolution instance create failed")

    async def disconnect_instance(self, user_id: str) -> dict:
        """Logout and delete the Evolution API instance."""
        instance_name = self._instance_name(user_id)
        results: dict = {}
        try:
            async with httpx.AsyncClient(timeout=15, verify=self.verify_ssl) as client:
                await self._force_delete_instance(client, instance_name)
                results["delete"] = "attempted"
        except Exception as e:
            results["error"] = str(e)

        await self.db.users.update_one(
            {"_id": user_id},
            {"$unset": {"whatsapp.instance_name": "", "whatsapp.status": ""}},
        )
        return results

    # ── Message sending ──────────────────────────────────────────────────────

    async def check_message_limit(self, user_id: str) -> dict:
        """Return daily and monthly message usage for the business (owner billing)."""
        try:
            from entitlements import build_entitlements, load_billing_record

            user = await self.db.users.find_one({"_id": user_id})
            record = await load_billing_record(self.db, user or {"_id": user_id})
            ent = await build_entitlements(self.db, record)
            business_id = ent["owner_id"]
            plan = ent.get("effective_plan", "free")
            daily_cap = _DAILY_SEND_LIMITS.get(plan, _DAILY_SEND_LIMITS["free"])

            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            daily_sent = await self.db.messages.count_documents({
                "user_id": business_id,
                "direction": "outgoing",
                "created_at": {"$gte": today},
            })
            usage = ent.get("usage") or {}
            monthly_sent = usage.get("outbound_messages_month", 0)
            monthly_cap = usage.get("outbound_messages_cap", 0)
            monthly_remaining = usage.get("outbound_messages_remaining", 0)
            return {
                "sent": daily_sent,
                "limit": daily_cap,
                "remaining": max(0, daily_cap - daily_sent),
                "daily_sent": daily_sent,
                "daily_limit": daily_cap,
                "monthly_sent": monthly_sent,
                "monthly_limit": monthly_cap,
                "monthly_remaining": monthly_remaining,
                "plan": plan,
                "dashboard_access": ent.get("dashboard_access"),
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
            if not limits.get("dashboard_access"):
                return {
                    "status": "limit_reached",
                    "message": "Subscribe or start a free trial to send WhatsApp messages.",
                }
            if limits.get("monthly_remaining", 0) <= 0 and limits.get("monthly_limit", 0) > 0:
                return {
                    "status": "limit_reached",
                    "message": f"Monthly limit of {limits['monthly_limit']:,} messages reached. Upgrade your plan.",
                }
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

            # Send via Evolution API with retries (transient failures only).
            # 3 attempts, exponential backoff with jitter: ~1s, ~2-3s.
            evo_msg_id: Optional[str] = None
            delivery_error: Optional[str] = None
            if media_url:
                mtype = (media_type or "document").lower()
                send_path = f"/message/sendMedia/{instance_name}"
                send_payload: dict = {
                    "number": to_number,
                    "mediatype": mtype,
                    "media": media_url,
                    "caption": message,
                }
                if media_filename:
                    send_payload["fileName"] = media_filename
            else:
                send_path = f"/message/sendText/{instance_name}"
                send_payload = {"number": to_number, "text": message}

            import random as _random
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=20, verify=self.verify_ssl) as client:
                        evo_resp = await client.post(
                            f"{self.base_url}{send_path}",
                            headers=self._headers(),
                            json=send_payload,
                        )
                    if evo_resp.status_code in (200, 201):
                        evo_data = evo_resp.json()
                        evo_msg_id = (
                            evo_data.get("key", {}).get("id")
                            or evo_data.get("id")
                        )
                        delivery_error = None
                        if evo_msg_id:
                            await self.db.messages.update_one(
                                {"_id": message_id},
                                {"$set": {"evo_message_id": evo_msg_id}},
                            )
                        break
                    # 5xx and 429 are transient — retry; other 4xx are permanent
                    delivery_error = f"Evolution API {evo_resp.status_code}: {evo_resp.text[:200]}"
                    logger.warning(f"[send_message] attempt {attempt + 1}: {delivery_error}")
                    if evo_resp.status_code < 500 and evo_resp.status_code != 429:
                        break
                except Exception as evo_err:
                    delivery_error = str(evo_err)
                    logger.error(f"[send_message] attempt {attempt + 1} error: {evo_err}")
                if attempt < 2:
                    await asyncio.sleep((2 ** attempt) * (1 + _random.random() * 0.5))

            # Honest delivery state on the stored message. Webhooks will upgrade
            # it (sent → delivered → read); "failed" surfaces in the chat UI and
            # in the failed_sends collection for recovery/inspection.
            if delivery_error and not evo_msg_id:
                await self.db.messages.update_one(
                    {"_id": message_id},
                    {"$set": {"delivery_status": "failed", "delivery_error": delivery_error[:500]}},
                )
                try:
                    await self.db.failed_sends.insert_one({
                        "message_id": message_id,
                        "user_id": user_id,
                        "to_number": to_number,
                        "error": delivery_error[:500],
                        "send_context": send_context,
                        "created_at": datetime.utcnow(),
                    })
                except Exception:
                    pass
            elif evo_msg_id:
                # Keep one-time purchased messages from being charged before a
                # provider has accepted the send. The WAHA implementation uses
                # the same helper after its successful response.
                try:
                    from entitlements import consume_extra_message_if_needed
                    await consume_extra_message_if_needed(self.db, user_id, message_id)
                except Exception:
                    logger.exception("[send_message] could not record extra-message usage for %s", message_id)

            return {
                # Do not report a failed provider call as a successful send.
                # Mobile optimistic UI relies on this status to offer a retry.
                "status": "error" if delivery_error and not evo_msg_id else "success",
                "message": "Message was not sent. Please try again." if delivery_error and not evo_msg_id else None,
                "delivered": evo_msg_id is not None,
                "delivery_error": delivery_error if not evo_msg_id else None,
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
            async with httpx.AsyncClient(timeout=30, verify=self.verify_ssl) as client:
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
            async with httpx.AsyncClient(timeout=60, verify=self.verify_ssl) as client:
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
            async with httpx.AsyncClient(timeout=30, verify=self.verify_ssl) as client:
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
            async with httpx.AsyncClient(timeout=10, verify=self.verify_ssl) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/fetchProfilePictureUrl/{instance_name}",
                    headers=self._headers(),
                    json={"number": phone},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return (
                        data.get("profilePictureUrl")
                        or data.get("profilePictureURL")
                        or data.get("url")
                        or None
                    )
        except Exception as e:
            logger.debug(f"[fetch_profile_picture] {phone}: {e}")
        return None

    async def fetch_profile_pictures_bulk(self, user_id: str) -> dict:
        """Fetch and store profile pictures for all contacts of a user."""
        customers = await self.db.customers.find(
            {
                "user_id": user_id,
                "$or": [
                    {"profile_picture": {"$exists": False}},
                    {"profile_picture": None},
                    {"profile_picture": ""},
                ],
            },
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
            async with httpx.AsyncClient(timeout=10, verify=self.verify_ssl) as client:
                await client.post(
                    f"{self.base_url}/message/markMessageAsRead/{instance_name}",
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
            import time
            state = data.get("state") or (data.get("instance") or {}).get("state", "")

            # Throttle transitional states (connecting/close) to once per 10 s per instance
            # to prevent Evolution API flood from hammering the DB and logs.
            if state in ("connecting", "close"):
                now = time.monotonic()
                last = self._conn_throttle.get(instance_name, 0.0)
                if now - last < 10.0:
                    return
                self._conn_throttle[instance_name] = now

            user = await self.find_user_by_instance(instance_name)
            if not user:
                logger.warning(f"[handle_connection_update] no user for instance {instance_name}")
                return

            update: dict = {"whatsapp.connection_state": state}

            state_norm = (state or "").lower()
            if state_norm in ("open", "connected"):
                update["whatsapp.connected"] = True
                self._conn_throttle.pop(instance_name, None)  # reset throttle on successful connect
                # Extract phone number if provided
                wuid = (data.get("instance") or {}).get("wuid", "")
                if wuid:
                    update["whatsapp.phone_number"] = _jid_to_phone(wuid)
            elif state_norm in ("close", "connecting"):
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


    async def handle_group_message(self, instance_name: str, data: dict) -> Optional[dict]:
        """
        Extract a WhatsApp group message for keyword monitoring.
        Called from the webhook handler before handle_incoming_message (which skips groups).
        Returns None if not a group message, outgoing, or unparseable.
        """
        try:
            user = await self.find_user_by_instance(instance_name)
            if not user:
                return None

            messages = data if isinstance(data, list) else [data]
            if not messages:
                return None

            msg_data  = messages[0]
            key       = msg_data.get("key", {})
            remote_jid = key.get("remoteJid", "")
            from_me   = bool(key.get("fromMe", False))

            if "@g.us" not in remote_jid:
                return None
            if from_me:
                return None

            msg_obj = msg_data.get("message") or {}
            if "protocolMessage" in msg_obj or "senderKeyDistributionMessage" in msg_obj:
                return None

            body, _, _, _ = _extract_message_body(msg_obj)
            if not body or len(body.strip()) < 5:
                return None

            push_name  = msg_data.get("pushName") or msg_data.get("notifyName") or "Member"
            group_name = msg_data.get("groupName") or remote_jid.split("@")[0]

            return {
                "user":       user,
                "body":       body.strip(),
                "push_name":  push_name,
                "group_jid":  remote_jid,
                "group_name": group_name,
            }
        except Exception as e:
            logger.error("[handle_group_message] %s: %s", instance_name, e)
            return None

# ── Connection watchdog ──────────────────────────────────────────────────────

WATCHDOG_INTERVAL = int(os.environ.get("WA_WATCHDOG_INTERVAL_SECONDS", "300"))
# Consecutive failed checks before declaring an instance dead (2 × 5min ≈ 10min)
WATCHDOG_FAIL_THRESHOLD = int(os.environ.get("WA_WATCHDOG_FAIL_THRESHOLD", "2"))


async def connection_watchdog_loop(db, notify_user=None) -> None:
    """Periodically verify every 'connected' WhatsApp instance is actually alive.

    Webhook-driven state goes stale silently (phone offline, unlinked, Evolution
    restart). This loop heals state in both directions and notifies the owner
    when their connection dies, instead of them discovering it via failed sends.

    notify_user: optional async callable (user_id, title, body) for push alerts.
    """
    service = get_whatsapp_service(db)
    while True:
        try:
            cursor = db.users.find(
                {"whatsapp.connected": True},
                {"_id": 1, "whatsapp": 1},
            )
            async for user in cursor:
                user_id = user["_id"]
                status = await service.get_instance_status(user_id)
                state = status.get("status")

                if status.get("connected"):
                    if (user.get("whatsapp") or {}).get("watchdog_fails"):
                        await db.users.update_one(
                            {"_id": user_id}, {"$set": {"whatsapp.watchdog_fails": 0}}
                        )
                elif state == "error":
                    # Couldn't reach Evolution — that's our problem, not the
                    # user's connection. Never mark users offline for this.
                    logger.warning("[watchdog] Evolution unreachable while checking %s", user_id)
                else:
                    fails = ((user.get("whatsapp") or {}).get("watchdog_fails") or 0) + 1
                    if fails >= WATCHDOG_FAIL_THRESHOLD:
                        await db.users.update_one(
                            {"_id": user_id},
                            {"$set": {
                                "whatsapp.connected": False,
                                "whatsapp.disconnected_at": datetime.utcnow(),
                                "whatsapp.watchdog_fails": 0,
                            }},
                        )
                        logger.warning("[watchdog] marked %s disconnected (state=%s)", user_id, state)
                        if notify_user:
                            try:
                                await notify_user(
                                    user_id,
                                    "WhatsApp disconnected",
                                    "Your WhatsApp connection was lost. Open Account → WhatsApp Business to reconnect.",
                                )
                            except Exception as ne:
                                logger.warning("[watchdog] notify failed for %s: %s", user_id, ne)
                    else:
                        await db.users.update_one(
                            {"_id": user_id}, {"$set": {"whatsapp.watchdog_fails": fails}}
                        )
                # Gentle pacing so a large tenant list doesn't hammer Evolution
                await asyncio.sleep(1)
        except Exception as e:
            logger.error("[watchdog] loop error: %s", e)
        await asyncio.sleep(WATCHDOG_INTERVAL)


# ── Singleton ────────────────────────────────────────────────────────────────

_whatsapp_service: Optional[WhatsAppService] = None


def get_whatsapp_service(db) -> WhatsAppService:
    """Return the WAHA adapter. Evolution has been removed from the server."""
    global _whatsapp_service
    from waha_service import WahaWhatsAppService

    if (
        _whatsapp_service is None
        or _whatsapp_service.db is not db
        or not isinstance(_whatsapp_service, WahaWhatsAppService)
    ):
        _whatsapp_service = WahaWhatsAppService(db)
    return _whatsapp_service

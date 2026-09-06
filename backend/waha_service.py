"""WAHA provider for Zilo's WhatsApp integration.

This adapter keeps the public service contract used by the rest of the backend,
but uses WAHA's persistent named sessions instead of recreating a gateway
instance whenever a customer asks for a fresh pairing code.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
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


def _region_proxies(raw: str) -> dict[str, dict[str, str]]:
    """Parse the optional, per-country WAHA egress configuration safely.

    ``WAHA_REGION_PROXIES_JSON`` deliberately lives only in the deployment
    environment because it can contain proxy credentials. Each entry has a
    stable proxy ``server`` and optional ``username`` and ``password``. Bad
    entries are ignored rather than allowing a malformed environment variable
    to interrupt WhatsApp linking globally.
    """
    try:
        configured = json.loads(raw or "{}")
    except json.JSONDecodeError:
        logger.warning("[waha] WAHA_REGION_PROXIES_JSON is not valid JSON")
        return {}
    if not isinstance(configured, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for country, value in configured.items():
        if not isinstance(country, str) or not isinstance(value, dict):
            continue
        server = str(value.get("server") or "").strip()
        if not server:
            continue
        proxy = {"server": server}
        for field in ("username", "password"):
            item = value.get(field)
            if isinstance(item, str) and item:
                proxy[field] = item
        result[country.strip().upper()] = proxy
    return result


WAHA_REGION_PROXIES = _region_proxies(os.environ.get("WAHA_REGION_PROXIES_JSON", ""))


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


def _is_lid_jid(value: object) -> bool:
    """Return whether a value is WhatsApp's opaque linked-identity JID.

    WAHA/NOWEB can receive a chat as ``<lid>@lid``.  A LID is not a phone
    number, so converting it to ``@c.us`` makes WAHA accept a send request
    without necessarily being able to deliver it.  Only accept the exact
    suffix we receive from WhatsApp; all other values use the normal phone
    fallback.
    """
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9]+@lid", value))


def _is_phone_like(value: str) -> bool:
    """Return True once non-digits are stripped the value is a plausible phone number."""
    digits = _digits(value)
    return 6 <= len(digits) <= 15


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
        # Cache LID -> phone lookups for 10 minutes to avoid hitting WAHA on
        # every incoming webhook for the same contact.
        self._lid_phone_cache: dict[str, tuple[str, float]] = {}

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

    async def _session_config_for_user(self, user_id: str) -> tuple[dict, Optional[str]]:
        """Return the webhook config plus a sticky country-specific egress.

        WhatsApp evaluates a newly linked device from the network it sees. A
        business must therefore retain the same country egress for the life of
        its WAHA session; silently changing it later would be less trustworthy
        than leaving its working connection alone.
        """
        user = await self.db.users.find_one(
            {"_id": user_id},
            {"country_code": 1, "settings.country_code": 1, "whatsapp.waha_egress_region": 1},
        ) or {}
        whatsapp = user.get("whatsapp") or {}
        settings = user.get("settings") or {}
        region = str(
            whatsapp.get("waha_egress_region")
            or user.get("country_code")
            or settings.get("country_code")
            or ""
        ).strip().upper()
        proxy = WAHA_REGION_PROXIES.get(region)
        config = self._webhook_config()
        if proxy:
            config["proxy"] = proxy
            config["metadata"]["egress_region"] = region
            return config, region
        return config, None

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

    async def _resolve_lid_phone(self, user_id: str, remote_jid: str) -> Optional[str]:
        """Resolve a WhatsApp LID JID to the underlying phone number via WAHA.

        When a modern WhatsApp account uses a linked-identity (LID) chat,
        the JID contains an opaque ID rather than the real phone number. Do
        not use the generic contacts endpoint here: for a LID it can return
        the LID itself in ``number``. WAHA's dedicated lids endpoint returns
        ``pn`` only when WhatsApp has actually exposed a phone number.
        """
        now = datetime.utcnow().timestamp()
        cache_entry = self._lid_phone_cache.get(remote_jid)
        if cache_entry:
            phone, expires = cache_entry
            if now < expires:
                return phone

        user_doc = await self.db.users.find_one({"_id": user_id}, {"whatsapp.instance_name": 1})
        session = (user_doc or {}).get("whatsapp", {}).get("instance_name") or self._instance_name(user_id)
        _, base_url = await self._node_for_user(user_id)
        try:
            async with httpx.AsyncClient(timeout=10, verify=self.verify_ssl) as client:
                response = await client.get(
                    # WAHA accepts either the bare numeric LID or an escaped
                    # ``123@lid`` here. The bare identifier avoids a proxy
                    # accidentally treating @ as a path token.
                    f"{base_url}/api/{quote(session, safe='')}/lids/{quote(remote_jid.split('@', 1)[0], safe='')}",
                    headers=self._headers(),
                )
                if response.status_code == 200:
                    data = response.json()
                    phone = _digits(str(data.get("pn") or ""))
                    if _is_phone_like(phone):
                        self._lid_phone_cache[remote_jid] = (phone, now + 600)
                        return phone
        except Exception as exc:
            logger.debug("[waha._resolve_lid_phone] %s", exc)
        self._lid_phone_cache[remote_jid] = (None, now + 60)
        return None

    async def repair_lid_contacts(self, user_id: str) -> dict:
        """Repair contacts previously saved with a LID as their phone number.

        Older webhook handling could save the digits from ``123@lid`` into
        ``phone_number``. Repair only records that are tied to a LID message;
        WhatsApp intentionally withholds some mappings, so guessing a number
        would be worse than showing no number.
        """
        mappings: dict[str, str] = {}
        pipeline = [
            {"$match": {"user_id": user_id, "remote_jid": {"$regex": r"^[0-9]+@lid$"}}},
            {"$group": {"_id": {"customer_id": "$customer_id", "lid": "$remote_jid"}}},
        ]
        async for row in self.db.messages.aggregate(pipeline):
            entry = row.get("_id") or {}
            customer_id = entry.get("customer_id")
            lid = entry.get("lid")
            if customer_id and lid:
                mappings[str(customer_id)] = str(lid)

        repaired = unavailable = merged = 0
        for customer_id, lid in mappings.items():
            customer = await self.db.customers.find_one({"_id": customer_id, "user_id": user_id})
            if not customer:
                continue
            phone = await self._resolve_lid_phone(user_id, lid)
            if not phone:
                if _digits(str(customer.get("phone_number") or "")) == _digits(lid):
                    await self.db.customers.update_one(
                        {"_id": customer_id},
                        {"$set": {"phone_number": "", "lid_jid": lid, "phone_number_unavailable": True}},
                    )
                    unavailable += 1
                continue

            duplicate = await self.db.customers.find_one({
                "user_id": user_id,
                "_id": {"$ne": customer_id},
                "$or": [{"phone_number": phone}, {"phone_number": f"+{phone}"}],
            })
            if duplicate:
                # Keep one contact and move its complete message history there.
                await self.db.messages.update_many(
                    {"user_id": user_id, "customer_id": customer_id},
                    {"$set": {"customer_id": duplicate["_id"]}},
                )
                merged_tags = list(dict.fromkeys((duplicate.get("tags") or []) + (customer.get("tags") or [])))
                update = {"tags": merged_tags, "lid_jid": lid}
                if not duplicate.get("profile_picture") and customer.get("profile_picture"):
                    update["profile_picture"] = customer["profile_picture"]
                await self.db.customers.update_one({"_id": duplicate["_id"]}, {"$set": update})
                await self.db.customers.delete_one({"_id": customer_id})
                merged += 1
            else:
                await self.db.customers.update_one(
                    {"_id": customer_id},
                    {"$set": {"phone_number": phone, "lid_jid": lid}, "$unset": {"phone_number_unavailable": ""}},
                )
                repaired += 1

        return {
            "status": "success",
            "contacts_checked": len(mappings),
            "repaired": repaired,
            "merged": merged,
            "number_unavailable": unavailable,
        }

    async def _start_session(self, base_url: str, instance_name: str, config: dict) -> dict:
        """Create/update/start a session without deleting an existing auth state."""
        payload = {"name": instance_name, "config": config}
        async with httpx.AsyncClient(timeout=30, verify=self.verify_ssl) as client:
            response = await client.post(
                f"{base_url}/api/sessions/start", headers=self._headers(), json=payload
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"WAHA session start failed ({response.status_code})")
        return response.json()

    async def _clear_failed_session(self, base_url: str, instance_name: str) -> bool:
        """Remove a session only when WAHA has already marked it as failed.

        A failed, unlinked WAHA session cannot be paired again and can make the
        next start request return 422.  Never delete a working, pending, or
        otherwise unknown session: those may still contain a customer's valid
        linked-device state.
        """
        try:
            async with httpx.AsyncClient(timeout=20, verify=self.verify_ssl) as client:
                status = await client.get(
                    f"{base_url}/api/sessions/{quote(instance_name, safe='')}",
                    headers=self._headers(),
                )
                if status.status_code != 200:
                    return False
                data = status.json()
                if str(data.get("status") or "").upper() != "FAILED":
                    return False
                deleted = await client.delete(
                    f"{base_url}/api/sessions/{quote(instance_name, safe='')}",
                    headers=self._headers(),
                )
            if deleted.status_code in (200, 204, 404):
                logger.info("[waha] removed failed pairing session %s", instance_name)
                return True
            logger.warning(
                "[waha] could not remove failed pairing session %s (HTTP %s)",
                instance_name,
                deleted.status_code,
            )
        except Exception as exc:
            logger.warning("[waha] failed-session cleanup %s: %s", instance_name, exc)
        return False

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
            session_config, egress_region = await self._session_config_for_user(user_id)
            # A previous aborted attempt leaves WAHA in FAILED.  Remove only
            # that failed session before creating a new pairing attempt.
            recovered_failed_session = await self._clear_failed_session(base_url, instance_name)
            try:
                session = await self._start_session(base_url, instance_name, session_config)
            except RuntimeError:
                # WAHA can transition to FAILED between the pre-check and the
                # start call.  Recover once, then surface any real failure.
                if not recovered_failed_session and await self._clear_failed_session(base_url, instance_name):
                    session = await self._start_session(base_url, instance_name, session_config)
                else:
                    raise
            update = {
                "whatsapp.provider": self.provider,
                "whatsapp.waha_node": node,
                "whatsapp.instance_name": instance_name,
                "whatsapp.status": "pairing_pending",
                "whatsapp.connected": False,
                "whatsapp.created_at": datetime.utcnow(),
            }
            if egress_region:
                update["whatsapp.waha_egress_region"] = egress_region
            await self.db.users.update_one(
                {"_id": user_id},
                {"$set": update},
            )
            result = await self._request_pairing_code(base_url, instance_name, phone)
            if result.get("pairing_code"):
                return result

            # WAHA documents QR as the necessary fallback when phone pairing is
            # unavailable. Keep the session; never recreate it for a refresh.
            qr = await self.get_qr_code(user_id)
            if qr.get("qr_base64"):
                return {"status": "qr_ready", **qr}
            # If WAHA has already given up, remove the unusable session so the
            # customer can immediately start a clean attempt instead of being
            # trapped behind a 422 on their next tap.
            await self._clear_failed_session(base_url, instance_name)
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
            session_config, egress_region = await self._session_config_for_user(user_id)
            await self._start_session(base_url, instance_name, session_config)
            update = {
                "whatsapp.provider": self.provider,
                "whatsapp.waha_node": node,
                "whatsapp.instance_name": instance_name,
                "whatsapp.status": "qr_pending",
                "whatsapp.connected": False,
                "whatsapp.created_at": datetime.utcnow(),
            }
            if egress_region:
                update["whatsapp.waha_egress_region"] = egress_region
            await self.db.users.update_one(
                {"_id": user_id},
                {"$set": update},
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
            # Only the connection webhook used to record this, so a business
            # that linked WhatsApp before then never had it stored — and its
            # shop sent buyers to the sign-up number instead. WAHA tells us
            # here too, so keep it whenever we ask.
            if number:
                try:
                    await self.db.users.update_one(
                        {"_id": user_id, "whatsapp.phone_number": {"$ne": number}},
                        {"$set": {"whatsapp.phone_number": number}},
                    )
                except Exception as exc:
                    logger.warning("[waha.get_instance_status] could not store number: %s", exc)
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

        destination = str(to_number or "").strip()
        destination_is_lid = _is_lid_jid(destination)
        to_number = _digits(destination)
        if not destination_is_lid and (not to_number or len(to_number) < 6 or len(to_number) > 15):
            return {"status": "error", "message": "Invalid phone number"}

        customer_query = {"user_id": user_id, "lid_jid": destination} if destination_is_lid else {
            "user_id": user_id,
            "$or": [{"phone_number": to_number}, {"phone_number": f"+{to_number}"}],
        }
        customer = await self.db.customers.find_one(customer_query)
        if customer:
            customer_id = customer["_id"]
        else:
            customer_id = str(uuid.uuid4())
            await self.db.customers.insert_one({
                "_id": customer_id, "user_id": user_id,
                "name": customer_name or ("WhatsApp contact" if destination_is_lid else f"Contact {to_number[-4:]}"),
                "phone_number": "" if destination_is_lid else to_number,
                "notes": "", "tags": ["New"], "last_contacted": datetime.utcnow(),
                "created_at": datetime.utcnow(), "auto_created": False, "business_initiated": True,
                **({"lid_jid": destination, "phone_number_unavailable": True} if destination_is_lid else {}),
            })

        # Prefer WhatsApp's current LID for a known inbound contact.  NOWEB
        # reports LID chats on modern WhatsApp accounts; translating them to a
        # phone JID is accepted by the API but can silently fail delivery.
        chat_id = destination if destination_is_lid else (customer.get("lid_jid") if customer else None)
        if not _is_lid_jid(chat_id):
            latest_inbound = await self.db.messages.find_one(
                {
                    "user_id": user_id,
                    "customer_id": customer_id,
                    "direction": "incoming",
                    "remote_jid": {"$regex": r"@lid$"},
                },
                sort=[("created_at", -1)],
            )
            chat_id = (latest_inbound or {}).get("remote_jid")
        if not _is_lid_jid(chat_id):
            chat_id = _chat_id(to_number)

        message_id = str(uuid.uuid4())
        is_image = _looks_like_image(media_url, media_type)
        doc = {
            "_id": message_id, "customer_id": customer_id, "user_id": user_id,
            "direction": "outgoing", "content": message,
            "message_type": "image" if media_url and is_image else ("document" if media_url else "text"),
            "from_number": "" if destination_is_lid else to_number, "remote_jid": chat_id,
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
                "session": session, "chatId": chat_id, "caption": message,
                "file": {"url": media_url, "mimetype": mimetype, "filename": media_filename},
            }
        else:
            path = "/api/sendText"
            payload = {"session": session, "chatId": chat_id, "text": message}

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
            # Purchased messages are used only once the provider accepts this
            # overage message. Failed sends do not reduce the balance.
            try:
                from entitlements import consume_extra_message_if_needed
                await consume_extra_message_if_needed(self.db, user_id, message_id)
            except Exception:
                logger.exception("[waha] could not record extra-message usage for %s", message_id)
            return {
                "status": "success", "delivered": True, "customer_id": customer_id,
                "message_id": message_id, "evo_message_id": provider_message_id,
                "customer_name": customer_name or (customer or {}).get("name", "WhatsApp contact" if destination_is_lid else f"Contact {to_number[-4:]}"),
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
                contact_id = str(contact.get("id") or "")
                is_lid_contact = _is_lid_jid(contact_id)
                if is_lid_contact:
                    phone = await self._resolve_lid_phone(user_id, contact_id)
                else:
                    phone = _digits(str(contact.get("number") or _jid_to_phone(contact_id)))
                if not phone or not _is_phone_like(phone):
                    # Do not bulk-create a contact with the opaque LID digits.
                    # A later inbound message can still create a LID-backed
                    # contact, preserving the chat without fabricating a phone.
                    continue
                name = contact.get("name") or contact.get("pushname") or contact.get("shortName") or f"Contact {phone[-4:]}"
                existing = await self.db.customers.find_one({"user_id": user_id, "phone_number": phone})
                if existing:
                    if re.match(r"^(Customer|Contact)\s+\d+$", existing.get("name", "")) and not re.match(r"^(Customer|Contact)\s+\d+$", name):
                        update = {"name": name, "synced_from_whatsapp": True}
                        if is_lid_contact:
                            update["lid_jid"] = contact_id
                        await self.db.customers.update_one({"_id": existing["_id"]}, {"$set": update})
                        updated += 1
                else:
                    await self.db.customers.insert_one({
                        "_id": str(uuid.uuid4()), "user_id": user_id, "name": name, "phone_number": phone,
                        "notes": "", "tags": ["New"], "created_at": datetime.utcnow(), "auto_created": True,
                        "synced_from_whatsapp": True, "is_customer": False,
                        **({"lid_jid": contact_id} if is_lid_contact else {}),
                    })
                    created += 1
            return {"status": "success", "created": created, "updated": updated, "total": len(contacts) if isinstance(contacts, list) else 0}
        except Exception as exc:
            logger.error("[waha.fetch_contacts] %s", exc)
            return {"status": "error", "message": str(exc)}

    async def _import_messages(self, user_id: str, session: str, chat_id: str, limit: int = 50) -> int:
        if _is_lid_jid(chat_id):
            phone = await self._resolve_lid_phone(user_id, chat_id)
        else:
            phone = _digits(_jid_to_phone(chat_id))
            if not _is_phone_like(phone):
                phone = None
        if not phone:
            return 0
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
            candidates = [_chat_id(phone), _digits(phone)]
            async with httpx.AsyncClient(timeout=15, verify=self.verify_ssl) as client:
                for contact_id in candidates:
                    response = await client.get(
                        f"{base_url}/api/contacts/profile-picture",
                        headers=self._headers(),
                        params={"contactId": contact_id, "session": session, "refresh": "true"},
                    )
                    if response.status_code == 200:
                        data = response.json()
                        pic = (
                            data.get("profilePictureURL")
                            or data.get("profilePictureUrl")
                            or data.get("url")
                            or None
                        )
                        if pic:
                            return pic
                    else:
                        logger.debug(
                            "[waha.fetch_profile_picture] non-200 %s for %s: %s",
                            response.status_code,
                            contact_id,
                            response.text[:200],
                        )
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
        if connected:
            update["whatsapp.connected_at"] = datetime.utcnow()
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

        # LID JIDs carry an opaque identity, not a real phone number. Ask WAHA to
        # resolve it so the CRM never stores a fabricated number again.
        is_lid = _is_lid_jid(remote_jid)
        if is_lid:
            phone = await self._resolve_lid_phone(user["_id"], remote_jid)
        else:
            phone = _digits(_jid_to_phone(remote_jid))
            if not _is_phone_like(phone):
                phone = None

        if not phone and not is_lid:
            logger.warning(
                "[waha.handle_incoming_message] dropping message from %s; no real phone number",
                remote_jid,
            )
            return None

        media = data.get("media") or {}
        return {
            # Keep an unresolved LID as the delivery target, but never present
            # its digits as a phone number in the CRM.
            "user": user, "from_number": phone or remote_jid, "body": data.get("body") or "",
            "push_name": data.get("pushName") or data.get("notifyName") or "", "from_me": from_me,
            "evo_message_id": data.get("id") or "", "remote_jid": remote_jid,
            "phone_number_unavailable": is_lid and not bool(phone),
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

"""Outbound SMS via Vonage.

WhatsApp is the intended channel for everything a buyer sees. This exists for
the moments it is not available — a shop whose connection has dropped, or one
that has not connected WhatsApp yet — so a buyer is never left with no
confirmation at all. SMS costs money per message, so send only what matters.

The sign-up OTP path in ``server.py`` still talks to Vonage directly. It can
move here, but it is the sign-up critical path and was left alone.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def sms_configured() -> bool:
    return bool(os.environ.get("VONAGE_API_KEY") and os.environ.get("VONAGE_API_SECRET"))


async def send_sms(to_number: str, text: str) -> bool:
    """Send one SMS. Returns whether Vonage accepted it."""
    api_key = os.environ.get("VONAGE_API_KEY")
    api_secret = os.environ.get("VONAGE_API_SECRET")
    to_number = (to_number or "").strip()
    if not (api_key and api_secret and to_number and text):
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://rest.nexmo.com/sms/json",
                json={
                    "api_key": api_key,
                    "api_secret": api_secret,
                    "to": to_number.lstrip("+"),
                    "from": os.environ.get("VONAGE_FROM", "Zilo"),
                    "text": text,
                },
                timeout=10.0,
            )
        if response.status_code != 200:
            logger.error("[sms] Vonage returned HTTP %s", response.status_code)
            return False
        messages = (response.json() or {}).get("messages") or []
        if messages and str(messages[0].get("status")) == "0":
            return True
        reason = messages[0].get("error-text") if messages else "no message in response"
        logger.error("[sms] Vonage rejected the message: %s", reason)
        return False
    except Exception as exc:
        logger.error("[sms] send failed: %s", exc)
        return False

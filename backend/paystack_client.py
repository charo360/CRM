"""
Thin async client for Paystack REST API (https://paystack.com/docs/api/).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from paystack_auth import PAYSTACK_BASE


class PaystackApiError(Exception):
    def __init__(self, message: str, *, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class PaystackClient:
    def __init__(self, secret_key: str, *, timeout: float = 20.0):
        self._secret_key = secret_key.strip()
        self._timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Dict[str, Any]:
        url = f"{PAYSTACK_BASE}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
            )
        text = (r.text or "")[:500]
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code >= 400 or not data.get("status", True):
            msg = data.get("message") if isinstance(data, dict) else None
            raise PaystackApiError(
                msg or f"Paystack HTTP {r.status_code}",
                status_code=r.status_code,
                body=text,
            )
        return data

    async def fetch_business(self) -> Dict[str, Any]:
        """
        Validate the secret key and return display fields for the CRM UI.

        Paystack has no public `/business` route (404). Use `/balance` to verify the
        key, then best-effort `/integration` for merchant name.
        """
        await self._request("GET", "/balance")
        out: Dict[str, Any] = {}
        try:
            data = await self._request("GET", "/integration")
            row = data.get("data") or {}
            if isinstance(row, dict):
                out = row
        except PaystackApiError:
            pass
        name = (
            (out.get("business_name") or out.get("name") or out.get("email") or "")
            .strip()
        )
        if name:
            out["name"] = name
            out["business_name"] = name
        return out

    async def initialize_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = await self._request("POST", "/transaction/initialize", json=payload)
        return data.get("data") or {}

    async def verify_transaction(self, reference: str) -> Dict[str, Any]:
        data = await self._request("GET", f"/transaction/verify/{reference}")
        return data.get("data") or {}

"""
Async client for Flutterwave v3 API (https://developer.flutterwave.com).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from flutterwave_auth import FLUTTERWAVE_BASE


def normalize_bank_option(row: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not isinstance(row, dict):
        return None
    name = (row.get("name") or "").strip()
    code = str(row.get("code") or row.get("id") or "").strip()
    if not name or not code:
        return None
    return {"code": code, "name": name}


class FlutterwaveApiError(Exception):
    def __init__(self, message: str, *, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class FlutterwaveClient:
    def __init__(self, secret_key: str, *, timeout: float = 25.0):
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
        url = f"{FLUTTERWAVE_BASE}{path}"
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
        if r.status_code >= 400:
            msg = None
            if isinstance(data, dict):
                msg = data.get("message")
            raise FlutterwaveApiError(
                msg or f"Flutterwave HTTP {r.status_code}",
                status_code=r.status_code,
                body=text,
            )
        if isinstance(data, dict) and data.get("status") == "error":
            raise FlutterwaveApiError(
                (data.get("message") or "Flutterwave error"),
                status_code=r.status_code,
                body=text,
            )
        return data if isinstance(data, dict) else {}

    async def list_banks(self, *, country: str) -> List[Dict[str, Any]]:
        cc = (country or "NG").strip().upper()
        data = await self._request("GET", f"/banks/{cc}")
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    async def create_subaccount(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = await self._request("POST", "/subaccounts", json=payload)
        row = data.get("data") or {}
        return row if isinstance(row, dict) else {}

    async def create_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = await self._request("POST", "/payments", json=payload)
        row = data.get("data") or {}
        return row if isinstance(row, dict) else {}

    async def verify_by_reference(self, tx_ref: str) -> Dict[str, Any]:
        data = await self._request(
            "GET",
            "/transactions/verify_by_reference",
            params={"tx_ref": tx_ref},
        )
        row = data.get("data") or {}
        return row if isinstance(row, dict) else {}

    async def create_refund(self, *, transaction_id: int, amount: Optional[float] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"id": int(transaction_id)}
        if amount is not None:
            payload["amount"] = float(amount)
        data = await self._request("POST", "/refunds", json=payload)
        row = data.get("data") or {}
        return row if isinstance(row, dict) else {}

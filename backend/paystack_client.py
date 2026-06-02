"""
Thin async client for Paystack REST API (https://paystack.com/docs/api/).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from paystack_auth import PAYSTACK_BASE

# Paystack List Banks — https://paystack.com/docs/api/miscellaneous/#bank
CURRENCY_COUNTRY = {
    "NGN": "nigeria",
    "KES": "kenya",
    "GHS": "ghana",
    "ZAR": "south africa",
}


def normalize_bank_option(row: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not isinstance(row, dict):
        return None
    if row.get("is_deleted"):
        return None
    name = (row.get("name") or "").strip()
    code_raw = row.get("code")
    code = ""
    if code_raw is not None and str(code_raw).strip():
        code = str(code_raw).strip()
    if not code:
        longcode = (row.get("longcode") or "").strip()
        if longcode:
            code = longcode
    if not code:
        code = (row.get("slug") or "").strip()
    if not name or not code:
        return None
    return {"code": code, "name": name}


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

    async def create_refund(self, *, transaction: str, amount_subunit: Optional[int] = None) -> Dict[str, Any]:
        """Full or partial refund. `transaction` is Paystack reference or transaction id."""
        payload: Dict[str, Any] = {"transaction": transaction}
        if amount_subunit is not None:
            payload["amount"] = int(amount_subunit)
        data = await self._request("POST", "/refund", json=payload)
        return data.get("data") or {}

    async def _list_banks_once(self, params: Dict[str, Any]) -> list[Dict[str, Any]]:
        """Single GET /bank (no cursor — cursor mode can return wrong/partial sets)."""
        data = await self._request("GET", "/bank", params={**params, "perPage": 100})
        rows = data.get("data") or []
        return rows if isinstance(rows, list) else []

    async def list_banks(self, *, currency: str, payout_type: str = "bank") -> list[Dict[str, Any]]:
        cur = (currency or "NGN").upper()
        kind = (payout_type or "bank").strip().lower()
        country = CURRENCY_COUNTRY.get(cur)

        param_sets: list[Dict[str, Any]] = []
        if kind == "mobile_money":
            if country:
                param_sets.append({"country": country, "type": "mobile_money"})
            param_sets.append({"currency": cur, "type": "mobile_money"})
        else:
            # Bank / settlement accounts (match Paystack dashboard subaccount types)
            if cur == "KES" and country:
                param_sets.append({"country": country, "type": "kepss"})
            elif cur == "GHS" and country:
                param_sets.append({"country": country, "type": "ghipss"})
            elif country:
                param_sets.append({"country": country})
            param_sets.append({"currency": cur})
            if cur == "NGN":
                param_sets.append({})

        collected: list[Dict[str, Any]] = []
        for params in param_sets:
            try:
                rows = await self._list_banks_once(params)
            except PaystackApiError:
                continue
            if rows:
                collected = rows
                break

        if not collected:
            return []

        if kind == "bank":
            mobile_types = {"mobile_money", "mobile_money_business"}
            filtered = [
                r
                for r in collected
                if isinstance(r, dict)
                and (r.get("type") or "").lower() not in mobile_types
            ]
            if filtered:
                collected = filtered

        return collected

    async def create_subaccount(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = await self._request("POST", "/subaccount", json=payload)
        return data.get("data") or {}

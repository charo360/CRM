"""
PaymentScreenshotVerifier — AI-powered payment screenshot verification.

When a customer sends a payment screenshot:
1. Calls GPT-4o vision to extract payment details (amount, reference, method)
2. Matches against the customer's pending orders in DB
3. Returns a verification result for the webhook to act on

Works for any payment method or region: M-Pesa, bank transfer, PayPal, etc.
"""
import os
import re
import json
import logging
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

ORDER_NUMBER_RE = re.compile(r'\bORD[-]?([A-Z0-9]{4,10})\b', re.IGNORECASE)


class PaymentScreenshotVerifier:

    def __init__(self, db):
        self.db = db

    async def verify(
        self,
        image_url: str,
        business_user_id: str,
        customer_id: str,
        expected_order_id: Optional[str] = None,
        expected_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Verify a payment screenshot.

        Returns dict with:
          verified: bool
          order_id: str | None
          order_number: str | None
          amount: float | None
          currency: str
          reference: str | None
          payment_method: str | None
          reason: str
          extracted: dict (raw vision output)
        """
        # Step 1 — call GPT-4o vision
        extracted = await self._call_vision(image_url)
        if extracted.get("error"):
            return self._fail(f"Vision API error: {extracted['error']}", extracted)

        # Not a payment screenshot at all
        if extracted.get("is_payment_confirmation") is False:
            return self._fail("Image does not appear to be a payment screenshot", extracted)

        # Step 2 — match to an order
        order = await self._match_order(
            business_user_id, customer_id, expected_order_id, expected_amount, extracted
        )
        if not order:
            return self._fail("Could not match screenshot to any pending order", extracted)

        # Step 3 — amount sanity check (±10% tolerance)
        ext_amount = extracted.get("amount")
        order_amount = float(order.get("total_amount") or order.get("amount") or 0)
        if ext_amount and order_amount:
            ratio = abs(ext_amount - order_amount) / max(order_amount, 0.01)
            if ratio > 0.10:
                return self._fail(
                    f"Amount mismatch: screenshot shows {ext_amount}, order total is {order_amount}",
                    extracted,
                    order=order,
                )

        order_number = order.get("order_number") or ("ORD-" + str(order["_id"])[:6].upper())

        return {
            "verified": True,
            "order_id": str(order["_id"]),
            "order_number": order_number,
            "amount": ext_amount or order_amount,
            "currency": extracted.get("currency", ""),
            "reference": extracted.get("reference"),
            "payment_method": extracted.get("payment_method"),
            "reason": "Screenshot verified successfully",
            "extracted": extracted,
        }

    async def _call_vision(self, image_url: str) -> Dict[str, Any]:
        """Send image to GPT-4o vision and extract structured payment data."""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return {"error": "OPENAI_API_KEY not configured"}

        prompt = (
            "You are a payment verification assistant. Analyze this payment screenshot carefully.\n"
            "Extract the following fields and return them as a JSON object. Use null for any field not visible.\n\n"
            "Fields:\n"
            "- amount: numeric amount paid as a float (no currency symbol or commas), e.g. 1500.0\n"
            "- currency: currency code or name (e.g. KES, USD, NGN, KSh, GHS)\n"
            "- reference: transaction reference or confirmation code string\n"
            "- date: payment date as a string\n"
            "- payment_method: e.g. M-Pesa, Airtel Money, MTN Money, Bank Transfer, PayPal, Flutterwave\n"
            "- order_ref: any order number visible in format ORD-XXXXXX, or null\n"
            "- sender: name of the sender if visible, or null\n"
            "- recipient: name or number of recipient if visible, or null\n"
            "- is_payment_confirmation: true if this is a genuine payment receipt/confirmation, false otherwise\n\n"
            "Return ONLY valid JSON. No explanation, no markdown."
        )

        payload = {
            "model": "gpt-4o",
            "max_tokens": 400,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url, "detail": "low"},
                        },
                    ],
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                raw_text = resp.json()["choices"][0]["message"]["content"].strip()

                # Strip markdown code fences if present
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
                    raw_text = re.sub(r"\n?```$", "", raw_text)

                data = json.loads(raw_text)

                # Normalize amount to float
                raw_amt = data.get("amount")
                if raw_amt is not None:
                    try:
                        data["amount"] = float(str(raw_amt).replace(",", "").strip())
                    except (ValueError, TypeError):
                        data["amount"] = None

                return data

        except json.JSONDecodeError as e:
            logger.error(f"[PaymentVerifier] JSON parse error: {e}")
            return {"error": f"JSON parse error: {e}"}
        except Exception as e:
            logger.error(f"[PaymentVerifier] Vision call failed: {e}")
            return {"error": str(e)}

    async def _match_order(
        self,
        user_id: str,
        customer_id: str,
        expected_order_id: Optional[str],
        expected_amount: Optional[float],
        extracted: Dict[str, Any],
    ) -> Optional[dict]:
        """
        Find the best matching pending order. Priority order:
        1. expected_order_id from conversation state
        2. Order number extracted from screenshot (ORD-XXXXXX)
        3. Amount match ±10% among unpaid orders
        4. Most recent unpaid order (fallback)
        """
        # 1. Exact order ID from conversation state (most reliable)
        if expected_order_id:
            order = await self.db.orders.find_one({
                "_id": expected_order_id,
                "user_id": user_id,
            })
            if order:
                return order

        # 2. Order number visible in screenshot
        order_ref = extracted.get("order_ref") or ""
        if order_ref:
            m = ORDER_NUMBER_RE.search(order_ref)
            if m:
                suffix = re.escape(m.group(1))
                order = await self.db.orders.find_one({
                    "user_id": user_id,
                    "customer_id": customer_id,
                    "order_number": {"$regex": f"ORD-?{suffix}", "$options": "i"},
                })
                if order:
                    return order

        # Fetch unpaid orders for steps 3 and 4
        unpaid = await self.db.orders.find({
            "user_id": user_id,
            "customer_id": customer_id,
            "payment_status": {
                "$in": ["Pending", "pending", "partial", "Partial", "unpaid", "Unpaid", ""]
            },
        }).sort("created_at", -1).to_list(10)

        if not unpaid:
            return None

        # 3. Amount match ±10%
        ext_amount = extracted.get("amount")
        if ext_amount:
            for o in unpaid:
                order_amt = float(o.get("total_amount") or o.get("amount") or o.get("price") or 0)
                if order_amt > 0:
                    ratio = abs(ext_amount - order_amt) / order_amt
                    if ratio <= 0.10:
                        return o

        # 4. Fallback: most recent unpaid order
        return unpaid[0]

    @staticmethod
    def _fail(reason: str, extracted: Dict, order: Optional[dict] = None) -> Dict[str, Any]:
        return {
            "verified": False,
            "order_id": str(order["_id"]) if order else None,
            "order_number": order.get("order_number", "") if order else None,
            "amount": extracted.get("amount"),
            "currency": extracted.get("currency", ""),
            "reference": extracted.get("reference"),
            "payment_method": extracted.get("payment_method"),
            "reason": reason,
            "extracted": extracted,
        }

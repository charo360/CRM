"""
Contact Classifier
AI-powered classification of WhatsApp contacts as Customer or Supplier
based on chat message analysis. Runs automatically on incoming messages
and periodically on all unclassified contacts.
"""
import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


# Keyword-based fast classifier (no AI needed, instant)
SUPPLIER_KEYWORDS = [
    "invoice", "delivery note", "shipment", "tracking number", "dispatch",
    "wholesale", "bulk price", "minimum order", "moq", "lead time",
    "payment terms", "net 30", "net 60", "proforma", "quotation",
    "supply", "restock", "stock available", "in stock", "out of stock",
    "per unit", "per piece", "per carton", "per dozen",
    "catalogue", "price list", "updated prices",
]

CUSTOMER_KEYWORDS = [
    "i want to buy", "i want to order", "how much", "what's the price",
    "do you have", "is it available", "can i get", "i need",
    "place an order", "order for", "send me", "deliver to",
    "my address", "delivery address", "when will it arrive",
    "receipt", "warranty", "return", "refund", "exchange",
]

# Patterns where the BUSINESS is asking (outgoing) — indicates supplier
OUTGOING_SUPPLIER_PATTERNS = [
    "what's your price", "do you have stock", "can you supply",
    "send me quote", "send quotation", "what's the moq",
    "delivery time", "lead time", "when can you deliver",
    "i need to order", "restock", "bulk order",
    "price for", "how much for bulk", "wholesale price",
]


class ContactClassifier:
    """Classifies contacts as Customer or Supplier based on chat analysis"""

    def __init__(self, db):
        self.db = db
        raw_key = (os.environ.get('OPENAI_API_KEY') or '').strip()
        self.api_key = raw_key.replace('\r', '').replace('\n', '').replace(' ', '')
        if self.api_key and self.api_key != 'your_openai_api_key_here':
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.has_ai = True
            except Exception:
                self.client = None
                self.has_ai = False
        else:
            self.client = None
            self.has_ai = False

    async def classify_contact(self, user_id: str, customer_id: str, keyword_only: bool = False) -> Optional[Dict]:
        """
        Classify a single contact based on their chat history.
        keyword_only=True: free keyword scan only (used on every message)
        keyword_only=False: keywords + AI fallback (used on manual scan or threshold)
        """
        # Get recent messages for this contact
        messages = await self.db.messages.find({
            "customer_id": customer_id,
            "user_id": user_id
        }).sort("created_at", -1).limit(30).to_list(30)

        if len(messages) < 2:
            return None  # Not enough data to classify

        messages.reverse()  # Chronological order

        # Get contact info
        contact = await self.db.customers.find_one({"_id": customer_id, "user_id": user_id})
        if not contact:
            return None

        # Skip if already confirmed (user already approved a classification)
        if contact.get("classification_confirmed"):
            return None

        # Step 1: Fast keyword-based classification (always free)
        keyword_result = self._keyword_classify(messages)

        # Step 2: If keywords are strong enough, use them
        if keyword_result["confidence"] >= 0.6:
            result = keyword_result
        elif not keyword_only and self.has_ai and len(messages) >= 5:
            # AI fallback — only when explicitly allowed (manual scan or threshold)
            ai_result = await self._ai_classify(messages, contact)
            if ai_result:
                result = ai_result
            else:
                result = keyword_result
        else:
            result = keyword_result

        # Only return if we have reasonable confidence
        if result["confidence"] < 0.4:
            return None

        return {
            "customer_id": customer_id,
            "contact_name": contact.get("name", "Unknown"),
            "phone_number": contact.get("phone_number", ""),
            "suggested_type": result["type"],  # "customer" or "supplier"
            "confidence": result["confidence"],
            "reason": result["reason"],
            "detected_details": result.get("details", {}),
        }

    def _keyword_classify(self, messages: List[Dict]) -> Dict:
        """Fast keyword-based classification"""
        incoming_text = " ".join([
            m.get("content", "").lower() for m in messages
            if m.get("direction") == "incoming"
        ])
        outgoing_text = " ".join([
            m.get("content", "").lower() for m in messages
            if m.get("direction") == "outgoing"
        ])

        supplier_score = 0
        customer_score = 0
        reasons = []

        # Check incoming messages for supplier signals
        for kw in SUPPLIER_KEYWORDS:
            if kw in incoming_text:
                supplier_score += 2
                reasons.append(f"They mentioned '{kw}'")

        # Check incoming messages for customer signals
        for kw in CUSTOMER_KEYWORDS:
            if kw in incoming_text:
                customer_score += 2
                reasons.append(f"They asked '{kw}'")

        # Check outgoing messages — if YOU are asking supplier-type questions
        for kw in OUTGOING_SUPPLIER_PATTERNS:
            if kw in outgoing_text:
                supplier_score += 3  # Strong signal — you're treating them as supplier
                reasons.append(f"You asked them '{kw}'")

        total = supplier_score + customer_score
        if total == 0:
            return {"type": "customer", "confidence": 0.2, "reason": "No clear signals", "details": {}}

        if supplier_score > customer_score:
            confidence = min(0.9, supplier_score / (total + 2))
            return {
                "type": "supplier",
                "confidence": confidence,
                "reason": "; ".join(reasons[:3]),
                "details": {},
            }
        else:
            confidence = min(0.9, customer_score / (total + 2))
            return {
                "type": "customer",
                "confidence": confidence,
                "reason": "; ".join(reasons[:3]),
                "details": {},
            }

    async def _ai_classify(self, messages: List[Dict], contact: Dict) -> Optional[Dict]:
        """Use OpenAI to classify contact with high accuracy"""
        try:
            conversation = ""
            for m in messages[-20:]:
                role = "THEM" if m.get("direction") == "incoming" else "YOU"
                conversation += f"{role}: {m.get('content', '')}\n"

            prompt = f"""Analyze this WhatsApp business conversation and classify the contact.

CONTACT: {contact.get('name', 'Unknown')} ({contact.get('phone_number', '')})

CONVERSATION:
{conversation}

Based on the conversation, classify this contact as either:
- CUSTOMER: Someone who buys from you (asks prices, places orders, inquires about products)
- SUPPLIER: Someone who sells/supplies to you (sends invoices, quotes prices for bulk, discusses stock/delivery)

Respond in EXACTLY this format (no other text):
TYPE: customer OR supplier
CONFIDENCE: 0.0 to 1.0
REASON: Brief explanation (max 20 words)
CATEGORY: If supplier, suggest category (Electronics/Clothing/Food & Beverage/Beauty & Health/Home & Garden/Automotive/Raw Materials/Packaging/Stationery/Services/Other). If customer, write "N/A"
PRODUCTS: Comma-separated list of products discussed (max 5), or "N/A" if unclear"""

            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150,
            )

            text = response.choices[0].message.content.strip()
            return self._parse_ai_response(text)

        except Exception as e:
            logger.error(f"AI classification failed: {e}")
            return None

    def _parse_ai_response(self, text: str) -> Optional[Dict]:
        """Parse the structured AI response"""
        try:
            lines = text.strip().split("\n")
            result = {}
            for line in lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    result[key.strip().upper()] = val.strip()

            contact_type = result.get("TYPE", "customer").lower()
            if contact_type not in ("customer", "supplier"):
                contact_type = "customer"

            confidence = float(result.get("CONFIDENCE", "0.5"))
            confidence = max(0.0, min(1.0, confidence))

            reason = result.get("REASON", "AI analysis")
            category = result.get("CATEGORY", "Other")
            products = result.get("PRODUCTS", "N/A")

            details = {}
            if contact_type == "supplier" and category != "N/A":
                details["suggested_category"] = category
            if products and products != "N/A":
                details["products"] = [p.strip() for p in products.split(",") if p.strip()]

            return {
                "type": contact_type,
                "confidence": confidence,
                "reason": reason,
                "details": details,
            }
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}, text: {text}")
            return None

    async def classify_all_contacts(self, user_id: str) -> List[Dict]:
        """
        Classify all unclassified contacts for a user.
        Returns list of pending classifications for user approval.
        """
        # Get contacts that haven't been classified yet
        contacts = await self.db.customers.find({
            "user_id": user_id,
            "classification_confirmed": {"$ne": True},
        }).sort("last_contacted", -1).limit(50).to_list(50)

        results = []
        for contact in contacts:
            # Skip contacts that already have a pending classification
            existing = await self.db.pending_classifications.find_one({
                "customer_id": contact["_id"],
                "user_id": user_id,
                "status": "pending",
            })
            if existing:
                continue

            classification = await self.classify_contact(user_id, contact["_id"])
            if classification:
                # Store as pending classification
                await self.db.pending_classifications.update_one(
                    {"customer_id": contact["_id"], "user_id": user_id},
                    {"$set": {
                        "customer_id": contact["_id"],
                        "user_id": user_id,
                        "contact_name": classification["contact_name"],
                        "phone_number": classification["phone_number"],
                        "suggested_type": classification["suggested_type"],
                        "confidence": classification["confidence"],
                        "reason": classification["reason"],
                        "detected_details": classification.get("detected_details", {}),
                        "status": "pending",
                        "created_at": datetime.utcnow(),
                    }},
                    upsert=True,
                )
                results.append(classification)

        return results

    async def classify_single_on_message(self, user_id: str, customer_id: str):
        """
        Called after a new message arrives. Uses KEYWORD-ONLY classification
        (zero cost). AI is never called here — it only runs on manual scan
        or at the 5-message threshold (one-time).
        """
        contact = await self.db.customers.find_one({"_id": customer_id, "user_id": user_id})
        if not contact:
            return

        # Skip if user already confirmed this contact's type
        if contact.get("classification_confirmed"):
            return

        # Skip if already has a pending classification
        existing = await self.db.pending_classifications.find_one({
            "customer_id": customer_id,
            "user_id": user_id,
            "status": "pending",
        })
        if existing:
            return

        # Count messages
        msg_count = await self.db.messages.count_documents({
            "customer_id": customer_id,
            "user_id": user_id,
        })
        if msg_count < 3:
            return

        # Decide: keyword-only (free) or allow AI (one-time at threshold)
        # AI runs ONCE when contact hits exactly 5 messages — after that, keyword-only
        use_ai = (msg_count == 5 and self.has_ai)
        classification = await self.classify_contact(
            user_id, customer_id, keyword_only=not use_ai
        )

        if classification and classification["confidence"] >= 0.5:
            await self.db.pending_classifications.update_one(
                {"customer_id": customer_id, "user_id": user_id},
                {"$set": {
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "contact_name": classification["contact_name"],
                    "phone_number": classification["phone_number"],
                    "suggested_type": classification["suggested_type"],
                    "confidence": classification["confidence"],
                    "reason": classification["reason"],
                    "detected_details": classification.get("detected_details", {}),
                    "status": "pending",
                    "updated_at": datetime.utcnow(),
                }},
                upsert=True,
            )


# Singleton
_classifier_instance = None

def get_classifier(db) -> ContactClassifier:
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = ContactClassifier(db)
    return _classifier_instance

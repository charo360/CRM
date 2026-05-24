"""
email_classifier.py — AI-powered classification of email contacts.

After emails are synced, this service analyses each unique sender's
email threads and classifies them as:
  • investor  — funding, term sheets, due diligence, equity, cap table
  • customer  — purchases, orders, inquiries, support, pricing questions
  • partner   — reseller, affiliate, co-marketing, integration, referral
  • supplier  — wholesale, invoices, shipments, stock, raw materials
  • personal  — friends, family, non-commercial
  • unknown   — not enough signal

Classified contacts are upserted into `db.customers` with the right tag
(Investor / Partner / Supplier / Customer) and their email threads are linked.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Keyword banks ─────────────────────────────────────────────────────────────

INVESTOR_KEYWORDS = [
    "term sheet", "due diligence", "cap table", "equity", "valuation",
    "series a", "series b", "seed round", "pre-seed", "angel",
    "investment thesis", "portfolio", "fund", "fundraise", "fundraising",
    "convertible note", "safe note", "dilution", "runway", "burn rate",
    "pitch deck", "investor update", "board seat", "board meeting",
    "venture capital", "vc fund", "limited partner", "lp", "gp",
    "deal flow", "capital call", "follow-on", "pro rata",
    "exit strategy", "ipo", "acquisition", "m&a",
    "interested in investing", "investment opportunity",
    "returns", "roi", "irr", "multiple",
]

CUSTOMER_KEYWORDS = [
    "i want to buy", "i want to order", "how much", "what's the price",
    "pricing", "price list", "quote me", "send me a quote",
    "do you have", "is it available", "can i get", "i need",
    "place an order", "order for", "send me", "deliver to",
    "my address", "delivery address", "when will it arrive",
    "receipt", "warranty", "return", "refund", "exchange",
    "subscription", "plan", "upgrade", "downgrade",
    "support ticket", "help with", "issue with", "bug report",
    "customer support", "account", "billing", "invoice",
    "demo", "trial", "onboarding", "getting started",
    "interested in your product", "interested in your service",
]

PARTNER_KEYWORDS = [
    "partnership", "partner program", "co-marketing", "co-sell",
    "reseller", "affiliate", "referral program", "referral fee",
    "integration", "api integration", "white label", "whitelabel",
    "distribution", "channel partner", "strategic alliance",
    "revenue share", "rev share", "commission",
    "joint venture", "collaboration", "cross-promotion",
    "technology partner", "solution partner",
    "reseller agreement", "partner agreement", "mou",
    "go-to-market", "gtm", "co-branded",
]

SUPPLIER_KEYWORDS = [
    "invoice", "delivery note", "shipment", "tracking number", "dispatch",
    "wholesale", "bulk price", "minimum order", "moq", "lead time",
    "payment terms", "net 30", "net 60", "proforma", "quotation",
    "supply", "restock", "stock available", "in stock", "out of stock",
    "per unit", "per piece", "per carton", "per dozen",
    "catalogue", "price list", "updated prices",
    "raw materials", "manufacturing", "production run",
    "shipping manifest", "bill of lading", "customs",
    "purchase order", "po number", "fulfillment",
    "warehouse", "inventory", "consignment",
]

PERSONAL_KEYWORDS = [
    "happy birthday", "happy anniversary", "miss you",
    "thinking of you", "get well soon", "congratulations",
    "catch up", "let's hang", "dinner tonight",
    "family", "vacation", "holiday photos",
]

# Senders to always skip (automated / no-reply)
SKIP_SENDERS = [
    "noreply@", "no-reply@", "notifications@", "mailer-daemon@",
    "postmaster@", "support@google", "calendar-notification",
    "news@", "newsletter@", "marketing@", "updates@",
    "donotreply@", "do-not-reply@", "automated@",
]


def _extract_email(addr: str) -> str:
    """Pull bare email from 'Name <email@x.com>' format."""
    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", addr or "")
    return m.group(0).lower() if m else (addr or "").strip().lower()


def _extract_name(addr: str) -> str:
    """Pull display name from 'Name <email@x.com>', fall back to local part."""
    addr = (addr or "").strip()
    m = re.match(r'^"?([^"<]+)"?\s*<', addr)
    if m:
        return m.group(1).strip()
    email = _extract_email(addr)
    return email.split("@")[0].replace(".", " ").title() if email else "Unknown"


def _should_skip(email: str) -> bool:
    """Return True for automated/no-reply senders."""
    lower = email.lower()
    return any(skip in lower for skip in SKIP_SENDERS)


class EmailContactClassifier:
    """Classify email contacts and upsert them into the CRM."""

    def __init__(self, db: Any):
        self.db = db
        raw_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        self.api_key = raw_key.replace("\r", "").replace("\n", "").replace(" ", "")
        if self.api_key and self.api_key != "your_openai_api_key_here":
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.has_ai = True
            except Exception:
                self.client = None
                self.has_ai = False
        else:
            self.client = None
            self.has_ai = False

    # ── Public API ────────────────────────────────────────────────────────────

    async def classify_new_emails(self, user_id: str) -> Dict[str, Any]:
        """
        Scan all email messages for this user that haven't been classified yet.
        Group by sender, classify each unique sender, upsert contacts.
        Returns summary stats.
        """
        # Find messages not yet classified
        unclassified = await self.db.email_messages.find({
            "user_id": user_id,
            "contact_classified": {"$ne": True},
        }).sort("date", -1).to_list(500)

        if not unclassified:
            return {"classified": 0, "created": 0, "updated": 0}

        # Group by sender email
        sender_map: Dict[str, List[Dict]] = {}
        for msg in unclassified:
            # Skip outgoing messages — classify the OTHER person
            if msg.get("is_outgoing"):
                continue
            email = _extract_email(msg.get("from_addr", ""))
            if not email or _should_skip(email):
                continue
            sender_map.setdefault(email, []).append(msg)

        classified = 0
        created = 0
        updated = 0

        for sender_email, messages in sender_map.items():
            try:
                result = await self._classify_sender(
                    user_id, sender_email, messages
                )
                if result:
                    contact_result = await self._upsert_contact(
                        user_id, sender_email, messages, result
                    )
                    classified += 1
                    if contact_result == "created":
                        created += 1
                    elif contact_result == "updated":
                        updated += 1

                # Mark all messages from this sender as classified
                msg_ids = [m["_id"] for m in messages]
                await self.db.email_messages.update_many(
                    {"_id": {"$in": msg_ids}},
                    {"$set": {"contact_classified": True}},
                )
            except Exception as e:
                logger.warning(
                    "[email_classifier] Failed for %s: %s", sender_email, e
                )

        logger.info(
            "[email_classifier] user=%s classified=%d created=%d updated=%d",
            user_id, classified, created, updated,
        )
        return {"classified": classified, "created": created, "updated": updated}

    async def classify_thread(
        self, user_id: str, thread_id: str
    ) -> Optional[Dict[str, Any]]:
        """Classify a single email thread and return the result."""
        messages = await self.db.email_messages.find({
            "user_id": user_id,
            "thread_id": thread_id,
        }).sort("date", 1).to_list(100)

        if not messages:
            return None

        # Find the primary external sender
        for msg in messages:
            if not msg.get("is_outgoing"):
                email = _extract_email(msg.get("from_addr", ""))
                if email and not _should_skip(email):
                    return await self._classify_sender(user_id, email, messages)
        return None

    # ── Core classification ───────────────────────────────────────────────────

    async def _classify_sender(
        self, user_id: str, sender_email: str, messages: List[Dict]
    ) -> Optional[Dict[str, Any]]:
        """Classify a sender based on their email messages."""
        # Aggregate text from all messages for this sender
        all_bodies = []
        subjects = []
        for msg in messages:
            body = msg.get("body_clean") or msg.get("body_raw") or ""
            if body:
                all_bodies.append(body[:500])  # cap per message
            subj = msg.get("subject") or ""
            if subj:
                subjects.append(subj)

        combined_text = " ".join(all_bodies + subjects).lower()

        if not combined_text.strip():
            return None

        # Step 1: keyword classification (free, instant)
        kw_result = self._keyword_classify(combined_text)

        # Step 2: if keywords are confident enough, use them
        if kw_result["confidence"] >= 0.6:
            return kw_result

        # Step 3: AI fallback if available and enough content
        if self.has_ai and len(combined_text) > 100:
            biz_context = await self._get_business_context(user_id)
            ai_result = await self._ai_classify(
                sender_email, messages, subjects, biz_context
            )
            if ai_result and ai_result["confidence"] > kw_result["confidence"]:
                return ai_result

        # Return keyword result if it has any signal
        if kw_result["confidence"] >= 0.35:
            return kw_result

        return None

    def _keyword_classify(self, text: str) -> Dict[str, Any]:
        """Fast keyword scoring."""
        investor_score = sum(2 for kw in INVESTOR_KEYWORDS if kw in text)
        customer_score = sum(2 for kw in CUSTOMER_KEYWORDS if kw in text)
        partner_score = sum(2 for kw in PARTNER_KEYWORDS if kw in text)
        supplier_score = sum(2 for kw in SUPPLIER_KEYWORDS if kw in text)
        personal_score = sum(1 for kw in PERSONAL_KEYWORDS if kw in text)

        scores = {
            "investor": investor_score,
            "customer": customer_score,
            "partner": partner_score,
            "supplier": supplier_score,
            "personal": personal_score,
        }

        total = sum(scores.values())
        if total == 0:
            return {
                "type": "unknown",
                "confidence": 0.1,
                "reason": "No clear signals in email content",
            }

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        if best_type == "personal":
            return {"type": "personal", "confidence": 0.0, "reason": "Personal email"}

        confidence = min(0.9, best_score / (total + 2))

        reasons = []
        kw_banks = {
            "investor": INVESTOR_KEYWORDS,
            "customer": CUSTOMER_KEYWORDS,
            "partner": PARTNER_KEYWORDS,
            "supplier": SUPPLIER_KEYWORDS,
        }
        if best_type in kw_banks:
            hits = [kw for kw in kw_banks[best_type] if kw in text][:3]
            reasons = [f"Mentions: {', '.join(hits)}"]

        return {
            "type": best_type,
            "confidence": confidence,
            "reason": "; ".join(reasons) if reasons else f"Keyword match: {best_type}",
        }

    async def _get_business_context(self, user_id: str) -> str:
        """Fetch business info for AI context."""
        try:
            user = await self.db.users.find_one({"_id": user_id})
            if not user:
                return ""
            parts = []
            name = user.get("business_name") or user.get("name") or ""
            btype = user.get("business_type") or ""
            if name:
                parts.append(f"Business: {name}")
            if btype:
                parts.append(f"Type: {btype}")
            bk = user.get("business_knowledge")
            if isinstance(bk, dict):
                for k, v in bk.items():
                    if v:
                        parts.append(f"{k}: {v}")
            elif isinstance(bk, str) and bk:
                parts.append(bk)
            return "\n".join(parts)
        except Exception:
            return ""

    async def _ai_classify(
        self,
        sender_email: str,
        messages: List[Dict],
        subjects: List[str],
        biz_context: str,
    ) -> Optional[Dict[str, Any]]:
        """Use OpenAI to classify the email contact."""
        try:
            # Build conversation summary
            email_summary = ""
            for msg in messages[-15:]:
                direction = "FROM THEM" if not msg.get("is_outgoing") else "FROM US"
                subj = msg.get("subject", "")
                body = (msg.get("body_clean") or msg.get("body_raw") or "")[:400]
                email_summary += f"[{direction}] Subject: {subj}\n{body}\n---\n"

            biz_section = f"\nABOUT THIS BUSINESS:\n{biz_context}\n" if biz_context else ""

            prompt = f"""You are an expert CRM system that classifies email contacts for businesses.

Read the email conversation below between a business and an external contact.{biz_section}
SENDER EMAIL: {sender_email}
SUBJECTS: {', '.join(subjects[:5])}

EMAILS:
{email_summary}

Classify this contact as ONE of:
- INVESTOR — they are or could be an investor (discusses funding, equity, term sheets, due diligence, cap tables, board meetings, investment returns)
- CUSTOMER — they are a customer or prospect (asks about products/services, pricing, orders, support, billing, demos)
- PARTNER — they are a business partner (discusses partnerships, integrations, reselling, affiliates, co-marketing, revenue sharing, channel sales)
- SUPPLIER — they supply goods/materials TO this business (sends invoices, quotations, shipment tracking, wholesale pricing, stock updates, purchase orders, delivery notes)
- PERSONAL — friend, family, or non-commercial contact
- UNKNOWN — genuinely unclear from the emails

Rules:
- Read the full email conversation holistically, not just individual words
- Consider the INTENT and RELATIONSHIP, not just keywords
- SUPPLIER vs CUSTOMER: if THEY are selling/supplying TO this business → SUPPLIER. If THEY are buying FROM this business → CUSTOMER.
- If there's significant doubt, choose UNKNOWN
- Newsletter/automated senders should be UNKNOWN

Respond in EXACTLY this format:
TYPE: investor OR customer OR partner OR supplier OR personal OR unknown
CONFIDENCE: 0.0 to 1.0
REASON: One clear sentence explaining your classification
SUBTYPE: For investor (Angel/VC/PE/Family Office/Other), for partner (Strategic/Channel/Technology/Affiliate/Other), for supplier (Electronics/Clothing/Food/Beauty/Raw Materials/Packaging/Services/Other), for customer (Lead/Active/Support). Otherwise N/A"""

            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=150,
            )

            text = response.choices[0].message.content.strip()
            return self._parse_ai_response(text)

        except Exception as e:
            logger.error("[email_classifier] AI classification failed: %s", e)
            return None

    def _parse_ai_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse structured AI response."""
        try:
            lines = text.strip().split("\n")
            result = {}
            for line in lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    result[key.strip().upper()] = val.strip()

            contact_type = result.get("TYPE", "unknown").lower().strip()
            valid_types = ("investor", "customer", "partner", "supplier", "personal", "unknown")
            if contact_type not in valid_types:
                contact_type = "unknown"

            confidence = float(result.get("CONFIDENCE", "0.5"))
            confidence = max(0.0, min(1.0, confidence))

            reason = result.get("REASON", "AI analysis")
            subtype = result.get("SUBTYPE", "Other")

            return {
                "type": contact_type,
                "confidence": confidence,
                "reason": reason,
                "subtype": subtype if subtype != "N/A" else None,
            }
        except Exception as e:
            logger.error("[email_classifier] Parse failed: %s, text: %s", e, text)
            return None

    # ── Contact upsert ────────────────────────────────────────────────────────

    async def _upsert_contact(
        self,
        user_id: str,
        sender_email: str,
        messages: List[Dict],
        classification: Dict[str, Any],
    ) -> str:
        """
        Create or update a contact in db.customers based on classification.
        Links email threads to the contact.
        Returns 'created', 'updated', or 'skipped'.
        """
        contact_type = classification["type"]
        if contact_type in ("personal", "unknown"):
            return "skipped"

        # Extract name from the most recent message
        name = "Unknown"
        for msg in reversed(messages):
            if not msg.get("is_outgoing"):
                name = _extract_name(msg.get("from_addr", ""))
                break

        # Determine tag
        tag_map = {
            "investor": "Investor",
            "customer": "Customer",
            "partner": "Partner",
            "supplier": "Supplier",
        }
        tag = tag_map.get(contact_type, "Customer")

        # Collect thread IDs for linking
        thread_ids = list({m.get("thread_id") for m in messages if m.get("thread_id")})

        # Check if contact already exists by email
        existing = await self.db.customers.find_one({
            "user_id": user_id,
            "email": sender_email,
        })

        now = datetime.now(timezone.utc)

        if existing:
            # Update: add tag if not present, link threads
            update_ops: Dict[str, Any] = {
                "$addToSet": {"tags": tag},
                "$set": {
                    "last_contacted": now,
                    "email_classification": classification,
                    "email_classified_at": now,
                },
            }
            if thread_ids:
                update_ops.setdefault("$addToSet", {})
                update_ops["$addToSet"]["email_thread_ids"] = {"$each": thread_ids}

            # Add type-specific fields
            subtype = classification.get("subtype")
            if contact_type == "investor" and subtype:
                update_ops["$set"]["investor_type"] = subtype
                update_ops["$set"]["investment_stage"] = "Prospect"
            elif contact_type == "partner" and subtype:
                update_ops["$set"]["partner_type"] = subtype
            elif contact_type == "supplier" and subtype:
                update_ops["$set"]["supplier_category"] = subtype

            await self.db.customers.update_one(
                {"_id": existing["_id"]},
                update_ops,
            )

            # Also store in pending_email_classifications for review
            await self._store_pending(
                user_id, existing["_id"], name, sender_email, classification, thread_ids
            )
            return "updated"
        else:
            # Create new contact
            customer_id = str(uuid.uuid4())
            tags = [tag]
            if tag != "Customer":
                tags.append(tag)  # Will be de-duped by $addToSet later if needed

            doc: Dict[str, Any] = {
                "_id": customer_id,
                "user_id": user_id,
                "name": name,
                "email": sender_email,
                "phone_number": "",
                "notes": f"Auto-created from email. {classification.get('reason', '')}",
                "tags": list(set(tags)),
                "is_customer": contact_type == "customer",
                "auto_created": True,
                "source": "email",
                "email_thread_ids": thread_ids,
                "email_classification": classification,
                "email_classified_at": now,
                "purchase_count": 0,
                "total_spent": 0.0,
                "last_message": (messages[-1].get("body_clean") or "")[:200] if messages else None,
                "last_contacted": now,
                "created_at": now,
            }

            # Add type-specific fields
            subtype = classification.get("subtype")
            if contact_type == "investor":
                doc["investor_type"] = subtype or "Other"
                doc["investment_stage"] = "Prospect"
                doc["investor_notes"] = classification.get("reason", "")
            elif contact_type == "partner":
                doc["partner_type"] = subtype or "Other"
            elif contact_type == "supplier":
                doc["supplier_category"] = subtype or "Other"

            await self.db.customers.insert_one(doc)

            # Store pending classification for owner review
            await self._store_pending(
                user_id, customer_id, name, sender_email, classification, thread_ids
            )
            return "created"

    async def _store_pending(
        self,
        user_id: str,
        customer_id: str,
        name: str,
        email: str,
        classification: Dict[str, Any],
        thread_ids: List[str],
    ) -> None:
        """Store a pending email classification for owner review."""
        await self.db.pending_email_classifications.update_one(
            {"customer_id": customer_id, "user_id": user_id},
            {"$set": {
                "customer_id": customer_id,
                "user_id": user_id,
                "contact_name": name,
                "email": email,
                "suggested_type": classification["type"],
                "subtype": classification.get("subtype"),
                "confidence": classification["confidence"],
                "reason": classification["reason"],
                "email_thread_ids": thread_ids,
                "status": "pending",
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )

    # ── Bulk operations ───────────────────────────────────────────────────────

    async def reclassify_all(self, user_id: str) -> Dict[str, Any]:
        """
        Force reclassify ALL email contacts for a user.
        Resets the contact_classified flag and re-runs classification.
        """
        # Reset classification flags
        await self.db.email_messages.update_many(
            {"user_id": user_id},
            {"$unset": {"contact_classified": ""}},
        )
        return await self.classify_new_emails(user_id)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[EmailContactClassifier] = None


def get_email_classifier(db: Any) -> EmailContactClassifier:
    global _instance
    if _instance is None:
        _instance = EmailContactClassifier(db)
    return _instance

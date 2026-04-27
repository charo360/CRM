"""Quotes / Proposals — create, brand, share, convert to invoice.

Full feature set mirrors the invoices module:
- CRUD with QTE-XXXX numbering
- Branding (logo, colors, company info) reused from user settings
- Public share link via share_token (no auth required)
- AI-assisted drafting using the same LLM adapter as invoices
- Convert-to-invoice with full data carry-over
- Status machine: draft → sent → viewed → accepted / declined / expired
"""
from __future__ import annotations
import os, json, logging, uuid, secrets
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

ALLOWED_STATUS = frozenset({"draft", "sent", "viewed", "accepted", "declined", "expired"})


# ── helpers ───────────────────────────────────────────────────────────────────

def _tid(user): return user.get("business_id", user["_id"])


def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at", "expires_date", "issue_date",
              "sent_at", "viewed_at", "accepted_at"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"):
            doc[f] = v.isoformat()
    return doc


def _calc(items: List["QuoteItem"], tax_rate: float, discount: float = 0):
    subtotal = sum(i.qty * i.unit_price for i in items)
    disc = round(subtotal * (discount / 100), 2) if discount else 0
    taxed_base = max(subtotal - disc, 0)
    tax = round(taxed_base * (tax_rate / 100), 2)
    return round(subtotal, 2), round(disc, 2), tax, round(taxed_base + tax, 2)


# ── models ────────────────────────────────────────────────────────────────────

class QuoteItem(BaseModel):
    name: str = ""
    description: str = ""
    qty: float = 1
    unit_price: float = 0
    amount: float = 0


class Branding(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    from_phone: Optional[str] = None
    from_address: Optional[str] = None
    logo_url: Optional[str] = None
    accent_color: Optional[str] = None
    text_color: Optional[str] = None
    template: Optional[str] = None
    footer: Optional[str] = None
    payment_instructions: Optional[str] = None


class QuoteCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    customer_id: Optional[str] = None
    customer_name: str = ""
    customer_phone: str = ""
    customer_email: str = ""
    customer_address: str = ""
    items: List[QuoteItem] = []
    tax_rate: float = 0
    discount: float = 0
    currency: str = "KES"
    issue_date: Optional[str] = None
    expires_date: Optional[str] = None
    notes: str = ""
    terms: str = ""
    subject: str = ""
    status: str = "draft"
    branding: Optional[Branding] = None
    po_number: Optional[str] = None


class QuoteUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    items: Optional[List[QuoteItem]] = None
    tax_rate: Optional[float] = None
    discount: Optional[float] = None
    currency: Optional[str] = None
    issue_date: Optional[str] = None
    expires_date: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    subject: Optional[str] = None
    status: Optional[str] = None
    branding: Optional[Branding] = None
    po_number: Optional[str] = None


class AIDraftRequest(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=2000)
    currency: Optional[str] = None
    customer_name: Optional[str] = None


# ── AI helper (shared with invoices module) ───────────────────────────────────

async def _ai_draft(prompt: str, currency: str, customer_name: str) -> Dict[str, Any]:
    system = (
        "You extract quote line items from a short business description. "
        "Return ONLY valid JSON with keys: customer_name (string), items (array of "
        "{name, description, qty, unit_price}), notes (string), terms (string). "
        "Use the currency hint to interpret amounts. If prices are unknown, leave 0."
    )
    user_msg = (
        f"Currency: {currency or 'KES'}\n"
        f"Known customer name: {customer_name or '(unknown)'}\n"
        f"Description:\n{prompt}"
    )
    try:
        from assistant.models import resolve_model, _OAI_COMPATIBLE_BASE, _OAI_KEY_ENV
        import httpx as _httpx
        cfg = resolve_model(None)
        provider = cfg["provider"]
        model_name = cfg["model"]
        logger.info(f"[quotes.ai] using provider={provider} model={model_name}")

        if provider in ("openai", "deepseek", "grok"):
            base = _OAI_COMPATIBLE_BASE[provider]
            key = os.environ[_OAI_KEY_ENV[provider]]
            payload: Dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.2,
                "max_tokens": 600,
                "response_format": {"type": "json_object"},
            }
            async with _httpx.AsyncClient(timeout=30) as hc:
                r = await hc.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json=payload,
                )
                r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"] or "{}"
        elif provider == "anthropic":
            import anthropic as _ant
            key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            ac = _ant.AsyncAnthropic(api_key=key)
            msg = await ac.messages.create(
                model=model_name, max_tokens=600, system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = msg.content[0].text if msg.content else "{}"
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"[quotes.ai] fallback due to: {e}")
        return {
            "customer_name": customer_name or "",
            "items": [{"name": prompt[:80], "qty": 1, "unit_price": 0, "amount": 0}],
            "notes": "", "terms": "",
        }

    items = []
    for it in (data.get("items") or []):
        q = float(it.get("qty") or 1)
        p = float(it.get("unit_price") or 0)
        items.append({"name": it.get("name", ""), "description": it.get("description", ""),
                      "qty": q, "unit_price": p, "amount": round(q * p, 2)})
    return {
        "customer_name": data.get("customer_name") or customer_name or "",
        "items": items,
        "notes": data.get("notes") or "",
        "terms": data.get("terms") or "",
    }


# ── branding helper (mirrors invoices) ────────────────────────────────────────

async def _default_branding(db, user_id: str) -> Dict[str, Any]:
    user = await db.users.find_one({"_id": user_id}) or {}
    settings = user.get("settings") or {}
    brand_kit_logo, brand_kit_color = "", ""
    try:
        logo_doc = await db.saved_designs.find_one(
            {"user_id": user_id, "content_type": "brand_logo", "is_default": True}
        ) or await db.saved_designs.find_one(
            {"user_id": user_id, "content_type": "brand_logo"},
            sort=[("created_at", -1)],
        )
        if logo_doc:
            brand_kit_logo = logo_doc.get("file_url") or logo_doc.get("thumbnail_url") or ""
    except Exception:
        pass
    try:
        bs = await db.brand_settings.find_one({"user_id": user_id}) or {}
        brand_kit_color = (bs.get("brand_primary_color") or "").strip()
    except Exception:
        pass

    currency = (
        settings.get("currency") or user.get("currency") or "KES"
    )
    return {
        "from_name": user.get("business_name") or settings.get("business_name") or "",
        "from_email": user.get("email") or settings.get("business_email") or "",
        "from_phone": user.get("phone_number") or settings.get("business_phone") or "",
        "from_address": settings.get("business_location") or "",
        "logo_url": settings.get("logo_url") or brand_kit_logo or "",
        "accent_color": settings.get("brand_color") or brand_kit_color or "#7c3aed",
        "text_color": settings.get("invoice_text_color") or "#0f172a",
        "template": settings.get("invoice_template") or "modern",
        "footer": settings.get("invoice_footer") or "Thank you for considering us!",
        "payment_instructions": "",
        "currency": currency,
    }


# ── router ────────────────────────────────────────────────────────────────────

def make_quotes_router(db, user_dep):
    router = APIRouter(prefix="/quotes", tags=["quotes"])

    # Public: view a shared quote by token (no auth). Declared FIRST to avoid
    # collision with /{quote_id}.
    @router.get("/public/{token}")
    async def public_view(token: str, request: Request):
        doc = await db.quotes.find_one({"share_token": token})
        if not doc:
            raise HTTPException(404, "Quote not found")
        upd: Dict[str, Any] = {"last_viewed_at": datetime.utcnow()}
        if not doc.get("viewed_at"):
            upd["viewed_at"] = datetime.utcnow()
            if doc.get("status") == "sent":
                upd["status"] = "viewed"
        await db.quotes.update_one({"_id": doc["_id"]},
                                   {"$set": upd, "$inc": {"view_count": 1}})
        out = _ser(doc)
        out.pop("user_id", None)
        return out

    @router.get("")
    async def list_quotes(status: Optional[str] = None, q: Optional[str] = None,
                          user=user_dep):
        query: Dict[str, Any] = {"user_id": _tid(user)}
        if status:
            query["status"] = status
        if q:
            query["$or"] = [
                {"number": {"$regex": q, "$options": "i"}},
                {"customer_name": {"$regex": q, "$options": "i"}},
            ]
        # Auto-expire: quotes past their expires_date that are still open
        docs = await db.quotes.find(query, sort=[("created_at", -1)]).to_list(500)
        today = date.today().isoformat()
        expire_ids = []
        for d in docs:
            if d.get("status") in ("sent", "viewed") and d.get("expires_date"):
                if str(d["expires_date"])[:10] < today:
                    d["status"] = "expired"
                    expire_ids.append(d["_id"])
        if expire_ids:
            await db.quotes.update_many(
                {"_id": {"$in": expire_ids}},
                {"$set": {"status": "expired", "updated_at": datetime.utcnow()}},
            )
        return [_ser(d) for d in docs]

    @router.get("/meta/summary")
    async def quote_summary(user=user_dep):
        tid = _tid(user)
        pipeline = [
            {"$match": {"user_id": tid}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}, "total": {"$sum": "$total"}}},
        ]
        rows = await db.quotes.aggregate(pipeline).to_list(20)
        summary = {r["_id"]: {"count": r["count"], "total": r["total"]} for r in rows}
        return {
            "by_status": summary,
            "total_quoted": sum(r["total"] for r in rows),
            "accepted": summary.get("accepted", {}).get("total", 0),
        }

    @router.get("/meta/branding")
    async def get_branding(user=user_dep):
        return await _default_branding(db, _tid(user))

    @router.post("/ai/draft")
    async def ai_draft(req: AIDraftRequest, user=user_dep):
        result = await _ai_draft(req.prompt, req.currency or "KES",
                                  req.customer_name or "")
        return result

    @router.post("")
    async def create_quote(payload: QuoteCreate, user=user_dep):
        tid = _tid(user)
        defaults = await _default_branding(db, tid)
        count = await db.quotes.count_documents({"user_id": tid})
        sub, disc_amt, tax, total = _calc(payload.items, payload.tax_rate,
                                          payload.discount)
        merged_branding = {**defaults}
        if payload.branding:
            merged_branding.update(
                {k: v for k, v in payload.branding.model_dump().items()
                 if v is not None}
            )
        now = datetime.utcnow()
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "number": f"QTE-{count + 1:04d}",
            "share_token": secrets.token_urlsafe(16),
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name,
            "customer_phone": payload.customer_phone,
            "customer_email": payload.customer_email,
            "customer_address": payload.customer_address,
            "subject": payload.subject,
            "items": [i.model_dump() for i in payload.items],
            "subtotal": sub,
            "discount": payload.discount,
            "discount_amount": disc_amt,
            "tax_rate": payload.tax_rate,
            "tax_amount": tax,
            "total": total,
            "currency": (payload.currency or defaults.get("currency") or "KES").upper()[:6],
            "issue_date": payload.issue_date,
            "expires_date": payload.expires_date,
            "notes": payload.notes,
            "terms": payload.terms,
            "po_number": payload.po_number,
            "status": payload.status if payload.status in ALLOWED_STATUS else "draft",
            "branding": merged_branding,
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.quotes.insert_one(doc)
        return _ser(doc)

    @router.get("/{quote_id}")
    async def get_quote(quote_id: str, user=user_dep):
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Quote not found")
        return _ser(doc)

    @router.put("/{quote_id}")
    async def update_quote(quote_id: str, payload: QuoteUpdate, user=user_dep):
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Quote not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        if not doc.get("share_token"):
            upd["share_token"] = secrets.token_urlsafe(16)
        for f in ("customer_name", "customer_phone", "customer_email",
                   "customer_address", "currency", "issue_date", "expires_date",
                   "notes", "terms", "subject", "po_number"):
            v = getattr(payload, f, None)
            if v is not None:
                upd[f] = v
        if payload.status and payload.status in ALLOWED_STATUS:
            upd["status"] = payload.status
            if payload.status == "sent" and not doc.get("sent_at"):
                upd["sent_at"] = datetime.utcnow()
            if payload.status == "accepted" and not doc.get("accepted_at"):
                upd["accepted_at"] = datetime.utcnow()
        if payload.branding is not None:
            merged = {**(doc.get("branding") or {}),
                      **payload.branding.model_dump(exclude_none=True)}
            upd["branding"] = merged
        items = payload.items if payload.items is not None else \
            [QuoteItem(**i) for i in doc.get("items", [])]
        tr = payload.tax_rate if payload.tax_rate is not None else doc.get("tax_rate", 0)
        disc = payload.discount if payload.discount is not None else doc.get("discount", 0)
        if payload.items is not None or payload.tax_rate is not None \
                or payload.discount is not None:
            sub, disc_amt, tax, total = _calc(items, tr, disc)
            upd.update({
                "items": [i.model_dump() for i in items],
                "subtotal": sub,
                "discount": disc,
                "discount_amount": disc_amt,
                "tax_rate": tr,
                "tax_amount": tax,
                "total": total,
            })
        await db.quotes.update_one({"_id": quote_id}, {"$set": upd})
        updated = await db.quotes.find_one({"_id": quote_id})
        return _ser(updated)

    @router.patch("/{quote_id}/status")
    async def set_status(quote_id: str, body: Dict[str, Any], user=user_dep):
        st = body.get("status")
        if st not in ALLOWED_STATUS:
            raise HTTPException(400, f"Invalid status: {st}")
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Quote not found")
        upd: Dict[str, Any] = {"status": st, "updated_at": datetime.utcnow()}
        if st == "sent" and not doc.get("sent_at"):
            upd["sent_at"] = datetime.utcnow()
        if st == "accepted" and not doc.get("accepted_at"):
            upd["accepted_at"] = datetime.utcnow()
        await db.quotes.update_one({"_id": quote_id}, {"$set": upd})
        return {"status": st}

    @router.post("/{quote_id}/duplicate")
    async def duplicate_quote(quote_id: str, user=user_dep):
        tid = _tid(user)
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": tid})
        if not doc:
            raise HTTPException(404, "Quote not found")
        count = await db.quotes.count_documents({"user_id": tid})
        now = datetime.utcnow()
        new_doc = {
            **{k: v for k, v in doc.items() if k not in ("_id", "share_token",
               "created_at", "updated_at", "sent_at", "viewed_at",
               "accepted_at", "view_count")},
            "_id": str(uuid.uuid4()),
            "number": f"QTE-{count + 1:04d}",
            "share_token": secrets.token_urlsafe(16),
            "status": "draft",
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.quotes.insert_one(new_doc)
        return _ser(new_doc)

    @router.post("/{quote_id}/share")
    async def rotate_share(quote_id: str, user=user_dep):
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Quote not found")
        token = secrets.token_urlsafe(16)
        await db.quotes.update_one({"_id": quote_id},
                                   {"$set": {"share_token": token,
                                             "updated_at": datetime.utcnow()}})
        return {"share_token": token}

    @router.post("/{quote_id}/convert-to-invoice")
    async def convert_to_invoice(quote_id: str, user=user_dep):
        """Convert an accepted (or any) quote into a draft invoice."""
        tid = _tid(user)
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": tid})
        if not doc:
            raise HTTPException(404, "Quote not found")
        count = await db.invoices.count_documents({"user_id": tid})
        now = datetime.utcnow()
        invoice = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "number": f"INV-{count + 1:04d}",
            "share_token": secrets.token_urlsafe(16),
            "quote_id": quote_id,
            "customer_id": doc.get("customer_id"),
            "customer_name": doc.get("customer_name", ""),
            "customer_phone": doc.get("customer_phone", ""),
            "customer_email": doc.get("customer_email", ""),
            "customer_address": doc.get("customer_address", ""),
            "items": doc.get("items", []),
            "subtotal": doc.get("subtotal", 0),
            "discount": doc.get("discount", 0),
            "discount_amount": doc.get("discount_amount", 0),
            "tax_rate": doc.get("tax_rate", 0),
            "tax_amount": doc.get("tax_amount", 0),
            "total": doc.get("total", 0),
            "amount_paid": 0,
            "currency": doc.get("currency", "KES"),
            "issue_date": doc.get("issue_date"),
            "due_date": None,
            "notes": doc.get("notes", ""),
            "terms": doc.get("terms", ""),
            "po_number": doc.get("po_number"),
            "branding": doc.get("branding", {}),
            "status": "draft",
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.invoices.insert_one(invoice)
        await db.quotes.update_one(
            {"_id": quote_id},
            {"$set": {"status": "accepted", "accepted_at": now,
                      "invoice_id": invoice["_id"], "updated_at": now}},
        )
        return {"invoice": _ser(invoice), "invoice_id": invoice["_id"]}

    @router.delete("/{quote_id}")
    async def delete_quote(quote_id: str, user=user_dep):
        doc = await db.quotes.find_one({"_id": quote_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Quote not found")
        await db.quotes.delete_one({"_id": quote_id})
        return {"deleted": True}

    return router

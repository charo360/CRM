"""Invoice management — create, send, share, and track payment.

Features:
 - Full CRUD on /invoices
 - Per-invoice branding (logo, colors, company info, footer, payment instructions)
   with auto-fill from user settings / business knowledge on create.
 - AI-assisted drafting: turn a freeform description into items, notes, terms.
 - Public share link (`share_token`) and public read endpoint — no auth required,
   suitable for WhatsApp / Email forwarding.
 - Timeline events (sent_at, viewed_at, paid_at) for payment tracking.
 - Summary metrics for dashboard cards.
"""
from __future__ import annotations
import os, json, logging, uuid, secrets
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


async def _auto_record_paid(db, doc: dict) -> None:
    """When an invoice is fully paid, write a sale + a finance income entry
    so the transaction appears in Sales and P&L automatically."""
    tid = doc.get("user_id", "")
    inv_id = doc.get("_id", "")
    already = await db.sales.find_one({"invoice_id": inv_id, "user_id": tid})
    if already:
        return
    total = float(doc.get("total") or 0)
    currency = doc.get("currency", "KES")
    customer_id = doc.get("customer_id") or "walk-in"
    customer_name = doc.get("customer_name") or "Customer"
    item_names = ", ".join(
        (i.get("name") or "").strip() for i in (doc.get("items") or []) if i.get("name")
    ) or f"Invoice {doc.get('number', '')}"
    now = datetime.utcnow()
    sale_id = str(uuid.uuid4())
    try:
        await db.sales.insert_one({
            "_id": sale_id,
            "user_id": tid,
            "customer_id": customer_id,
            "item": item_names,
            "amount": total,
            "currency": currency,
            "payment_method": "Invoice",
            "receipt_sent": False,
            "is_credit": False,
            "invoice_id": inv_id,
            "invoice_number": doc.get("number", ""),
            "created_at": now,
        })
        # Update customer stats
        if customer_id and customer_id != "walk-in":
            await db.customers.update_one(
                {"_id": customer_id, "user_id": tid},
                {"$inc": {"purchase_count": 1, "total_spent": total},
                 "$set": {"last_contacted": now}},
            )
    except Exception as e:
        logger.warning(f"[invoices] sale record failed: {e}")
    try:
        await db.finance_entries.insert_one({
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "type": "income",
            "category": "Sales",
            "amount": total,
            "currency": currency,
            "description": f"Invoice {doc.get('number', '')} — {customer_name}",
            "invoice_id": inv_id,
            "created_at": now,
            "updated_at": now,
        })
    except Exception as e:
        logger.warning(f"[invoices] finance entry failed: {e}")

    # Fire workflow trigger
    try:
        from workflows.engine import fire_trigger
        from workflows.models import WorkflowEvent
        from whatsapp_service import get_whatsapp_service
        ws = get_whatsapp_service(db)
        event = WorkflowEvent(
            trigger_type="invoice_paid",
            user_id=tid,
            customer_id=customer_id if customer_id != "walk-in" else None,
            from_number=doc.get("customer_phone") or "",
            data={
                "invoice_id": inv_id,
                "invoice_number": doc.get("number", ""),
                "amount": total,
                "currency": currency,
                "customer_name": customer_name,
            }
        )
        import asyncio
        asyncio.create_task(fire_trigger(db, event, ws))
    except Exception as e:
        logger.warning(f"[invoices] fire_trigger paid failed: {e}")


ALLOWED_STATUS = frozenset({"draft", "sent", "viewed", "paid", "partial", "overdue", "cancelled"})


# ── helpers ──────────────────────────────────────────────────────────────────

def _tid(user): return user.get("business_id", user["_id"])


def _ser(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id", doc.get("id", "")))
    for f in ("created_at", "updated_at", "due_date", "issue_date",
              "sent_at", "viewed_at", "paid_at"):
        v = doc.get(f)
        if v and hasattr(v, "isoformat"):
            doc[f] = v.isoformat()
    return doc


def _next_number(existing: int, prefix: str = "INV") -> str:
    return f"{prefix}-{existing + 1:04d}"


def _calc(items: List["InvoiceItem"], tax_rate: float, discount: float = 0):
    subtotal = sum(i.qty * i.unit_price for i in items)
    disc = round(subtotal * (discount / 100), 2) if discount else 0
    taxed_base = max(subtotal - disc, 0)
    tax = round(taxed_base * (tax_rate / 100), 2)
    return round(subtotal, 2), round(disc, 2), tax, round(taxed_base + tax, 2)


_COUNTRY_NAME_TO_CODE = {
    "kenya": "KE", "tanzania": "TZ", "uganda": "UG", "rwanda": "RW",
    "ethiopia": "ET", "nigeria": "NG", "ghana": "GH", "senegal": "SN",
    "ivory coast": "CI", "côte d'ivoire": "CI", "cameroon": "CM",
    "south africa": "ZA", "zimbabwe": "ZW", "zambia": "ZM",
    "egypt": "EG", "saudi arabia": "SA", "united arab emirates": "AE",
    "uae": "AE", "morocco": "MA",
    "india": "IN", "pakistan": "PK", "bangladesh": "BD",
    "indonesia": "ID", "philippines": "PH", "malaysia": "MY",
    "thailand": "TH", "vietnam": "VN",
    "brazil": "BR", "mexico": "MX", "argentina": "AR", "colombia": "CO",
    "chile": "CL", "peru": "PE",
    "united states": "US", "usa": "US", "us": "US",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB",
    "canada": "CA",
}


def _currency_from_country(settings: Dict[str, Any]) -> str:
    """Derive currency from a country_code or country name on settings.
    Uses the same lookup table the rest of the app uses for payment methods."""
    code = (settings.get("country_code") or "").strip().upper()
    if not code:
        name = (settings.get("country") or "").strip().lower()
        code = _COUNTRY_NAME_TO_CODE.get(name, "")
    if not code:
        return ""
    try:
        from country_utils import COUNTRY_PAYMENT_METHODS
        entry = COUNTRY_PAYMENT_METHODS.get(code) or COUNTRY_PAYMENT_METHODS.get("DEFAULT") or {}
        return entry.get("currency") or ""
    except Exception:
        return ""


async def _default_branding(db, user_id: str) -> Dict[str, Any]:
    """Pull sensible branding defaults from user / settings / business knowledge /
    brand kit. Priority order for each field is: invoice-specific override
    (`settings.invoice_*`) → brand kit (default logo + primary color from
    `brand_settings`) → general business profile fields → safe fallback.
    This means once the user uploads a logo & color in their Brand Kit, every
    new invoice picks them up automatically — no need to re-upload.
    """
    user = await db.users.find_one({"_id": user_id}) or {}
    settings = (user.get("settings") or {})
    try:
        bk = await db.business_knowledge.find_one({"user_id": user_id}) or {}
    except Exception:
        bk = {}

    # Brand Kit logo: a saved_design with content_type=brand_logo & is_default=true
    brand_kit_logo = ""
    try:
        logo_doc = await db.saved_designs.find_one(
            {"user_id": user_id, "content_type": "brand_logo", "is_default": True}
        )
        if not logo_doc:
            logo_doc = await db.saved_designs.find_one(
                {"user_id": user_id, "content_type": "brand_logo"},
                sort=[("created_at", -1)],
            )
        if logo_doc:
            brand_kit_logo = logo_doc.get("file_url") or logo_doc.get("thumbnail_url") or ""
    except Exception:
        pass

    # Brand Kit color (font is captured but not surfaced in invoice yet).
    brand_kit_color = ""
    try:
        bs = await db.brand_settings.find_one({"user_id": user_id}) or {}
        brand_kit_color = (bs.get("brand_primary_color") or "").strip()
    except Exception:
        pass

    return {
        "from_name": user.get("business_name") or settings.get("business_name") or "",
        "from_email": user.get("email") or settings.get("business_email") or "",
        "from_phone": user.get("phone_number") or settings.get("business_phone") or "",
        "from_address": settings.get("business_location") or bk.get("business_location") or "",
        "logo_url": settings.get("invoice_logo_url") or settings.get("logo_url") or brand_kit_logo or "",
        "accent_color": settings.get("invoice_accent_color") or settings.get("brand_color") or brand_kit_color or "#0f766e",
        "text_color": settings.get("invoice_text_color") or "#0f172a",
        "template": settings.get("invoice_template") or "modern",
        "footer": settings.get("invoice_footer") or "Thank you for your business!",
        "payment_instructions": settings.get("payment_instructions") or _default_pay_instructions(settings),
        # NB: PUT /settings stores `currency` and `country_code` at the top
        # level of the user doc (see server.update_settings), not inside
        # `user.settings`. Check both, then fall back to country lookup.
        "currency": (
            settings.get("currency")
            or user.get("currency")
            or _currency_from_country(settings)
            or _currency_from_country(user)
            or "USD"
        ),
        "tax_rate": float(settings.get("default_tax_rate") or 0),
    }


def _default_pay_instructions(settings: Dict[str, Any]) -> str:
    methods = settings.get("payment_methods") or []
    if not methods:
        return ""
    lines = []
    for m in methods:
        if isinstance(m, dict):
            name = (m.get("name") or "").strip()
            details = (m.get("details") or "").strip()
            if name and details:
                lines.append(f"{name}: {details}")
            elif name:
                lines.append(name)
    return "\n".join(lines)


# ── models ───────────────────────────────────────────────────────────────────

class InvoiceItem(BaseModel):
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
    logo_url: Optional[str] = None      # data URL or https URL
    accent_color: Optional[str] = None  # hex
    text_color: Optional[str] = None
    template: Optional[str] = None      # modern | classic | minimal | bold
    footer: Optional[str] = None
    payment_instructions: Optional[str] = None


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    customer_id: Optional[str] = None
    customer_name: str = ""
    customer_phone: str = ""
    customer_email: str = ""
    customer_address: str = ""
    items: List[InvoiceItem] = []
    tax_rate: float = 0
    discount: float = 0
    currency: str = "KES"
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    notes: str = ""
    terms: str = ""
    status: str = "draft"
    branding: Optional[Branding] = None
    po_number: Optional[str] = None


class InvoiceUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    items: Optional[List[InvoiceItem]] = None
    tax_rate: Optional[float] = None
    discount: Optional[float] = None
    currency: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    status: Optional[str] = None
    branding: Optional[Branding] = None
    po_number: Optional[str] = None


class AIDraftRequest(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=2000)
    currency: Optional[str] = None
    customer_name: Optional[str] = None


# ── AI helper ────────────────────────────────────────────────────────────────


async def _ai_draft(prompt: str, currency: str, customer_name: str) -> Dict[str, Any]:
    """Call the configured LLM (DeepSeek / OpenAI / Grok / Anthropic) to convert
    freeform text → structured invoice JSON. Uses the same model registry as the
    rest of the app so it respects whatever AI_PROVIDER / key is configured."""
    system = (
        "You extract invoice line items from a short business description. "
        "Return ONLY valid JSON with keys: customer_name (string), items (array of "
        "{name, description, qty, unit_price}), notes (string), terms (string). "
        "Use the currency hint to interpret amounts. Never invent totals — compute "
        "amount from qty*unit_price on the client. If prices are unknown, leave 0."
    )
    user_msg = (
        f"Currency: {currency or 'KES'}\n"
        f"Known customer name: {customer_name or '(unknown)'}\n"
        f"Description:\n{prompt}"
    )
    try:
        from assistant.models import resolve_model, _OAI_COMPATIBLE_BASE, _OAI_KEY_ENV
        import asyncio, httpx as _httpx
        cfg = resolve_model(None)   # picks first available provider
        provider = cfg["provider"]
        model_name = cfg["model"]
        logger.info(f"[invoices.ai] using provider={provider} model={model_name}")

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
                model=model_name,
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = msg.content[0].text if msg.content else "{}"
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"[invoices.ai] fallback due to: {e}")
        return {
            "customer_name": customer_name or "",
            "items": [{"name": prompt[:80], "qty": 1, "unit_price": 0, "amount": 0}],
            "notes": "",
            "terms": "",
        }

    items = data.get("items") or []
    clean_items = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or it.get("description") or "").strip()
        if not name:
            continue
        qty = float(it.get("qty") or it.get("quantity") or 1)
        price = float(it.get("unit_price") or it.get("price") or 0)
        clean_items.append({
            "name": name,
            "description": str(it.get("description") or "").strip(),
            "qty": qty,
            "unit_price": price,
            "amount": round(qty * price, 2),
        })
    return {
        "customer_name": str(data.get("customer_name") or customer_name or "").strip(),
        "items": clean_items or [{"name": prompt[:80], "qty": 1, "unit_price": 0, "amount": 0}],
        "notes": str(data.get("notes") or "").strip(),
        "terms": str(data.get("terms") or "").strip(),
    }


# ── router ───────────────────────────────────────────────────────────────────

def make_invoices_router(db, user_dep):
    router = APIRouter(prefix="/invoices", tags=["invoices"])

    # Public: view a shared invoice by token (no auth). Declared FIRST so the
    # token path doesn't collide with /{invoice_id}.
    @router.get("/public/{token}")
    async def public_view(token: str, request: Request):
        doc = await db.invoices.find_one({"share_token": token})
        if not doc:
            raise HTTPException(404, "Invoice not found")
        # Mark viewed (idempotent-ish: only first view sets timestamp).
        upd: Dict[str, Any] = {"last_viewed_at": datetime.utcnow()}
        if not doc.get("viewed_at"):
            upd["viewed_at"] = datetime.utcnow()
            if doc.get("status") == "sent":
                upd["status"] = "viewed"
        await db.invoices.update_one({"_id": doc["_id"]}, {"$set": upd,
                                                              "$inc": {"view_count": 1}})
        out = _ser(doc)
        # Never leak the owner's internal ids / token in the public payload.
        out.pop("user_id", None)
        return out

    @router.get("")
    async def list_invoices(status: Optional[str] = None, q: Optional[str] = None,
                              user=user_dep):
        query: Dict[str, Any] = {"user_id": _tid(user)}
        if status:
            query["status"] = status
        if q:
            query["$or"] = [
                {"number": {"$regex": q, "$options": "i"}},
                {"customer_name": {"$regex": q, "$options": "i"}},
                {"customer_email": {"$regex": q, "$options": "i"}},
            ]
        docs = await db.invoices.find(query, sort=[("created_at", -1)]).to_list(500)
        # Auto-mark overdue: any non-terminal invoice past its due date.
        today = date.today().isoformat()
        overdue_ids = []
        for d in docs:
            if d.get("status") in ("sent", "viewed", "partial") and d.get("due_date"):
                due = str(d["due_date"])[:10]
                if due < today:
                    d["status"] = "overdue"
                    overdue_ids.append(d["_id"])
        if overdue_ids:
            await db.invoices.update_many(
                {"_id": {"$in": overdue_ids}},
                {"$set": {"status": "overdue", "updated_at": datetime.utcnow()}},
            )
        return [_ser(d) for d in docs]

    @router.get("/meta/summary")
    async def invoice_summary(user=user_dep):
        tid = _tid(user)
        pipeline = [
            {"$match": {"user_id": tid}},
            {"$group": {"_id": "$status", "count": {"$sum": 1},
                         "total": {"$sum": "$total"}}},
        ]
        rows = await db.invoices.aggregate(pipeline).to_list(20)
        summary = {r["_id"]: {"count": r["count"], "total": r["total"]} for r in rows}
        all_total = sum(r["total"] for r in rows)
        paid = summary.get("paid", {}).get("total", 0)
        outstanding = all_total - paid
        return {
            "by_status": summary,
            "total_invoiced": all_total,
            "total_paid": paid,
            "outstanding": round(outstanding, 2),
        }

    @router.get("/meta/branding")
    async def get_branding(user=user_dep):
        """Default branding derived from this user's settings; used as form defaults."""
        return await _default_branding(db, _tid(user))

    @router.put("/meta/branding")
    async def save_branding(payload: Branding, user=user_dep):
        """Persist invoice branding as defaults. Mirrors the accent color into the
        Brand Kit (`brand_settings.brand_primary_color`) so logo, color and
        company info stay consistent across invoices, designs, and other
        materials. The user only sets these once."""
        tid = _tid(user)
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        upd: Dict[str, Any] = {}
        mapping = {
            "logo_url": "settings.logo_url",
            "accent_color": "settings.brand_color",
            "text_color": "settings.invoice_text_color",
            "from_name": "business_name",
            "from_email": "settings.business_email",
            "from_phone": "settings.business_phone",
            "from_address": "settings.business_location",
            "footer": "settings.invoice_footer",
            "payment_instructions": "settings.payment_instructions",
            "template": "settings.invoice_template",
        }
        for k, v in data.items():
            target = mapping.get(k)
            if target:
                upd[target] = v
        if upd:
            await db.users.update_one({"_id": tid}, {"$set": upd})

        # Mirror into Brand Kit so designs share the same primary color.
        if data.get("accent_color"):
            try:
                await db.brand_settings.update_one(
                    {"user_id": tid},
                    {"$set": {"brand_primary_color": data["accent_color"],
                                "updated_at": datetime.utcnow()},
                     "$setOnInsert": {"user_id": tid}},
                    upsert=True,
                )
            except Exception as e:
                logger.warning(f"[invoices] could not mirror color to brand_settings: {e}")

        return await _default_branding(db, tid)

    @router.post("/ai/draft")
    async def ai_draft(payload: AIDraftRequest, user=user_dep):
        data = await _ai_draft(
            payload.prompt,
            payload.currency or "KES",
            payload.customer_name or "",
        )
        return data

    @router.post("")
    async def create_invoice(payload: InvoiceCreate, user=user_dep):
        tid = _tid(user)
        count = await db.invoices.count_documents({"user_id": tid})
        sub, disc, tax, total = _calc(payload.items, payload.tax_rate, payload.discount)
        now = datetime.utcnow()
        # Fill branding defaults from settings where user didn't override.
        defaults = await _default_branding(db, tid)
        branding_data = (payload.branding.model_dump(exclude_none=True)
                          if payload.branding else {})
        merged_branding = {**defaults, **branding_data}
        # keep only branding-ish keys (not currency/tax_rate — those are invoice-level)
        for k in ("currency", "tax_rate"):
            merged_branding.pop(k, None)

        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": tid,
            "number": _next_number(count),
            "share_token": secrets.token_urlsafe(16),
            "customer_id": payload.customer_id,
            "customer_name": payload.customer_name,
            "customer_phone": payload.customer_phone,
            "customer_email": payload.customer_email,
            "customer_address": payload.customer_address,
            "items": [i.model_dump() for i in payload.items],
            "subtotal": sub,
            "discount": payload.discount,
            "discount_amount": disc,
            "tax_rate": payload.tax_rate,
            "tax_amount": tax,
            "total": total,
            "amount_paid": 0,
            "currency": (payload.currency or defaults.get("currency") or "KES").upper()[:6],
            "issue_date": payload.issue_date,
            "due_date": payload.due_date,
            "notes": payload.notes,
            "terms": payload.terms,
            "po_number": payload.po_number,
            "status": payload.status if payload.status in ALLOWED_STATUS else "draft",
            "branding": merged_branding,
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.invoices.insert_one(doc)
        return _ser(doc)

    @router.get("/{invoice_id}")
    async def get_invoice(invoice_id: str, user=user_dep):
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Invoice not found")
        return _ser(doc)

    @router.put("/{invoice_id}")
    async def update_invoice(invoice_id: str, payload: InvoiceUpdate, user=user_dep):
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Invoice not found")
        upd: Dict[str, Any] = {"updated_at": datetime.utcnow()}
        # Back-fill share_token for invoices created before this field existed.
        if not doc.get("share_token"):
            upd["share_token"] = secrets.token_urlsafe(16)
        for f in ("customer_name", "customer_phone", "customer_email",
                   "customer_address", "currency", "issue_date", "due_date",
                   "notes", "terms", "po_number"):
            v = getattr(payload, f, None)
            if v is not None:
                upd[f] = v
        if payload.status and payload.status in ALLOWED_STATUS:
            upd["status"] = payload.status
            if payload.status == "sent" and not doc.get("sent_at"):
                upd["sent_at"] = datetime.utcnow()
            if payload.status == "paid" and not doc.get("paid_at"):
                upd["paid_at"] = datetime.utcnow()
                upd["amount_paid"] = doc.get("total", 0)
        if payload.branding is not None:
            merged = {**(doc.get("branding") or {}),
                      **payload.branding.model_dump(exclude_none=True)}
            upd["branding"] = merged

        items = payload.items if payload.items is not None else [InvoiceItem(**i) for i in doc.get("items", [])]
        tr = payload.tax_rate if payload.tax_rate is not None else doc.get("tax_rate", 0)
        disc = payload.discount if payload.discount is not None else doc.get("discount", 0)
        if payload.items is not None or payload.tax_rate is not None or payload.discount is not None:
            sub, d_amt, tax, total = _calc(items, tr, disc)
            upd.update({
                "items": [i.model_dump() for i in items],
                "subtotal": sub,
                "discount": disc,
                "discount_amount": d_amt,
                "tax_rate": tr,
                "tax_amount": tax,
                "total": total,
            })

        await db.invoices.update_one({"_id": invoice_id}, {"$set": upd})
        updated = await db.invoices.find_one({"_id": invoice_id})
        return _ser(updated)

    @router.patch("/{invoice_id}/status")
    async def set_status(invoice_id: str, body: Dict[str, Any], user=user_dep):
        st = body.get("status")
        if st not in ALLOWED_STATUS:
            raise HTTPException(400, f"Invalid status: {st}")
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Invoice not found")
        upd: Dict[str, Any] = {"status": st, "updated_at": datetime.utcnow()}
        if st == "sent" and not doc.get("sent_at"):
            upd["sent_at"] = datetime.utcnow()
        if st == "paid" and not doc.get("paid_at"):
            upd["paid_at"] = datetime.utcnow()
            upd["amount_paid"] = doc.get("total", 0)
        await db.invoices.update_one({"_id": invoice_id}, {"$set": upd})
        if st == "paid" and not doc.get("paid_at"):
            paid_doc = {**doc, **upd}
            await _auto_record_paid(db, paid_doc)
        return {"status": st}

    @router.post("/{invoice_id}/payment")
    async def record_payment(invoice_id: str, body: Dict[str, Any], user=user_dep):
        """Record a (partial) payment toward an invoice."""
        amount = float(body.get("amount") or 0)
        if amount <= 0:
            raise HTTPException(400, "amount must be > 0")
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Invoice not found")
        paid = float(doc.get("amount_paid") or 0) + amount
        total = float(doc.get("total") or 0)
        new_status = "paid" if paid >= total - 0.01 else "partial"
        upd: Dict[str, Any] = {
            "amount_paid": round(paid, 2),
            "status": new_status,
            "updated_at": datetime.utcnow(),
        }
        is_newly_paid = new_status == "paid" and not doc.get("paid_at")
        if is_newly_paid:
            upd["paid_at"] = datetime.utcnow()
        await db.invoices.update_one(
            {"_id": invoice_id},
            {"$set": upd,
             "$push": {"payments": {
                 "amount": amount,
                 "method": body.get("method") or "",
                 "note": body.get("note") or "",
                 "at": datetime.utcnow(),
             }}},
        )
        updated = await db.invoices.find_one({"_id": invoice_id})
        if is_newly_paid:
            await _auto_record_paid(db, updated)
        return _ser(updated)

    @router.post("/{invoice_id}/share")
    async def rotate_share_token(invoice_id: str, user=user_dep):
        """Rotate the public share token (invalidates previous link)."""
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Invoice not found")
        token = secrets.token_urlsafe(16)
        await db.invoices.update_one({"_id": invoice_id},
                                        {"$set": {"share_token": token,
                                                   "updated_at": datetime.utcnow()}})
        return {"share_token": token}

    @router.delete("/{invoice_id}")
    async def delete_invoice(invoice_id: str, user=user_dep):
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": _tid(user)})
        if not doc:
            raise HTTPException(404, "Invoice not found")
        await db.invoices.delete_one({"_id": invoice_id})
        return {"deleted": True}

    @router.post("/{invoice_id}/duplicate")
    async def duplicate_invoice(invoice_id: str, user=user_dep):
        tid = _tid(user)
        doc = await db.invoices.find_one({"_id": invoice_id, "user_id": tid})
        if not doc:
            raise HTTPException(404, "Invoice not found")
        count = await db.invoices.count_documents({"user_id": tid})
        now = datetime.utcnow()
        new_doc = dict(doc)
        new_doc["_id"] = str(uuid.uuid4())
        new_doc["number"] = _next_number(count)
        new_doc["share_token"] = secrets.token_urlsafe(16)
        new_doc["status"] = "draft"
        new_doc["amount_paid"] = 0
        new_doc["view_count"] = 0
        for k in ("sent_at", "viewed_at", "paid_at", "last_viewed_at", "payments"):
            new_doc.pop(k, None)
        new_doc["created_at"] = now
        new_doc["updated_at"] = now
        await db.invoices.insert_one(new_doc)
        return _ser(new_doc)

    return router

"""
Zilo Forms — embeddable form system.
Replaces WPForms entirely. Forms are defined in MongoDB, rendered by a JS widget,
and submissions flow into the Zilo CRM (visible alongside WhatsApp conversations).

Public endpoints (no auth):
  GET  /api/forms/{form_id}           — form definition for the widget
  POST /api/forms/{form_id}/submit    — submit an entry

Authenticated endpoints:
  POST /api/forms                     — create a form
  GET  /api/forms                     — list forms for the current user
  GET  /api/forms/{form_id}/entries   — view submissions
  DELETE /api/forms/{form_id}         — delete a form
"""
import logging
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Field & form definitions ───────────────────────────────────────────────────

INDUSTRY_FORMS: dict[str, list[dict]] = {
    "restaurant": [
        {
            "name": "Table Reservation",
            "type": "order",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Full Name",           "required": True},
                {"id": "phone",   "type": "tel",      "label": "Phone Number",        "required": True},
                {"id": "email",   "type": "email",    "label": "Email Address",       "required": False},
                {"id": "guests",  "type": "select",   "label": "Number of Guests",    "required": True,
                 "options": ["1–2", "3–5", "6–10", "11–20", "Above 20"]},
                {"id": "date",    "type": "date",     "label": "Date",                "required": True},
                {"id": "time",    "type": "select",   "label": "Time",                "required": True,
                 "options": ["12:00 PM (Lunch)", "1:00 PM", "6:00 PM (Dinner)", "7:00 PM", "8:00 PM"]},
                {"id": "notes",   "type": "textarea", "label": "Special Requests",    "required": False},
            ],
        },
        {
            "name": "Catering Inquiry",
            "type": "contact",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Full Name",           "required": True},
                {"id": "phone",   "type": "tel",      "label": "Phone Number",        "required": True},
                {"id": "event",   "type": "select",   "label": "Event Type",          "required": True,
                 "options": ["Wedding", "Corporate Event", "Birthday Party", "Graduation", "Other"]},
                {"id": "date",    "type": "date",     "label": "Event Date",          "required": True},
                {"id": "guests",  "type": "text",     "label": "Number of Guests",    "required": True},
                {"id": "venue",   "type": "text",     "label": "Location / Venue",    "required": True},
                {"id": "budget",  "type": "select",   "label": "Budget Range (KES)",  "required": False,
                 "options": ["Under 20,000", "20,000–50,000", "50,000–100,000", "Above 100,000"]},
                {"id": "notes",   "type": "textarea", "label": "Menu Preferences",    "required": False},
            ],
        },
        {
            "name": "Customer Feedback",
            "type": "survey",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Your Name",           "required": False},
                {"id": "rating",  "type": "select",   "label": "Overall Experience",  "required": True,
                 "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor", "⭐ Very Poor"]},
                {"id": "food",    "type": "select",   "label": "Food Quality",        "required": True,
                 "options": ["Excellent", "Good", "Average", "Needs Improvement"]},
                {"id": "service", "type": "select",   "label": "Service Speed",       "required": True,
                 "options": ["Very Fast", "Fast", "Average", "Slow"]},
                {"id": "revisit", "type": "radio",    "label": "Would You Visit Again?", "required": True,
                 "options": ["Definitely Yes", "Probably", "Not Sure", "No"]},
                {"id": "comment", "type": "textarea", "label": "Additional Comments", "required": False},
            ],
        },
    ],
    "salon": [
        {
            "name": "Appointment Booking",
            "type": "order",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Full Name",           "required": True},
                {"id": "phone",   "type": "tel",      "label": "Phone Number",        "required": True},
                {"id": "service", "type": "select",   "label": "Service",             "required": True,
                 "options": ["Hair Braiding", "Relaxer / Perming", "Hair Cut & Style", "Weave Installation", "Nails", "Facial / Skincare", "Massage", "Other"]},
                {"id": "date",    "type": "date",     "label": "Preferred Date",      "required": True},
                {"id": "time",    "type": "select",   "label": "Preferred Time",      "required": True,
                 "options": ["8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM", "12:00 PM", "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM"]},
                {"id": "notes",   "type": "textarea", "label": "Special Requests",    "required": False},
            ],
        },
        {
            "name": "Customer Feedback",
            "type": "survey",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Your Name",           "required": False},
                {"id": "rating",  "type": "select",   "label": "Overall Experience",  "required": True,
                 "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"]},
                {"id": "revisit", "type": "radio",    "label": "Would You Book Again?", "required": True,
                 "options": ["Definitely Yes", "Probably", "Not Sure", "No"]},
                {"id": "comment", "type": "textarea", "label": "Comments",            "required": False},
            ],
        },
    ],
    "tech": [
        {
            "name": "Quote Request",
            "type": "order",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Your Name",               "required": True},
                {"id": "email",   "type": "email",    "label": "Email Address",           "required": True},
                {"id": "phone",   "type": "tel",      "label": "Phone Number",            "required": True},
                {"id": "product", "type": "text",     "label": "Product / Service",       "required": True},
                {"id": "budget",  "type": "select",   "label": "Budget (KES)",            "required": False,
                 "options": ["Under 10,000", "10,000–30,000", "30,000–60,000", "60,000–100,000", "Above 100,000"]},
                {"id": "notes",   "type": "textarea", "label": "Additional Requirements", "required": False},
            ],
        },
        {
            "name": "Support Ticket",
            "type": "contact",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Your Name",       "required": True},
                {"id": "email",   "type": "email",    "label": "Email",           "required": True},
                {"id": "phone",   "type": "tel",      "label": "Phone",           "required": True},
                {"id": "device",  "type": "text",     "label": "Device / Product","required": True},
                {"id": "issue",   "type": "select",   "label": "Issue Type",      "required": True,
                 "options": ["Hardware Problem", "Software Issue", "Network / Connectivity", "Screen / Display", "Battery", "Other"]},
                {"id": "desc",    "type": "textarea", "label": "Describe the Problem", "required": True},
                {"id": "urgency", "type": "radio",    "label": "Urgency",         "required": True,
                 "options": ["Normal (3-5 days)", "Urgent (same day)", "Emergency (within 2 hours)"]},
            ],
        },
        {
            "name": "Customer Feedback",
            "type": "survey",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Your Name",       "required": False},
                {"id": "rating",  "type": "select",   "label": "Service Rating",  "required": True,
                 "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"]},
                {"id": "comment", "type": "textarea", "label": "Comments",        "required": False},
            ],
        },
    ],
    "retail": [
        {
            "name": "Custom Order",
            "type": "order",
            "fields": [
                {"id": "name",     "type": "text",     "label": "Full Name",       "required": True},
                {"id": "phone",    "type": "tel",      "label": "Phone Number",    "required": True},
                {"id": "email",    "type": "email",    "label": "Email",           "required": False},
                {"id": "item",     "type": "text",     "label": "Item / Product",  "required": True},
                {"id": "size",     "type": "select",   "label": "Size",            "required": False,
                 "options": ["XS", "S", "M", "L", "XL", "XXL", "Custom Size"]},
                {"id": "color",    "type": "text",     "label": "Color Preference","required": False},
                {"id": "qty",      "type": "number",   "label": "Quantity",        "required": True},
                {"id": "notes",    "type": "textarea", "label": "Additional Notes","required": False},
            ],
        },
        {
            "name": "Customer Feedback",
            "type": "survey",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Your Name",       "required": False},
                {"id": "rating",  "type": "select",   "label": "Shopping Experience", "required": True,
                 "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"]},
                {"id": "comment", "type": "textarea", "label": "Comments",        "required": False},
            ],
        },
    ],
    "hotel": [
        {
            "name": "Room Booking",
            "type": "order",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Full Name",       "required": True},
                {"id": "email",   "type": "email",    "label": "Email",           "required": True},
                {"id": "phone",   "type": "tel",      "label": "Phone Number",    "required": True},
                {"id": "checkin", "type": "date",     "label": "Check-in Date",   "required": True},
                {"id": "checkout","type": "date",     "label": "Check-out Date",  "required": True},
                {"id": "room",    "type": "select",   "label": "Room Type",       "required": True,
                 "options": ["Standard Room", "Deluxe Room", "Suite", "Family Room"]},
                {"id": "guests",  "type": "select",   "label": "Guests",          "required": True,
                 "options": ["1", "2", "3", "4", "5+"]},
                {"id": "notes",   "type": "textarea", "label": "Special Requests","required": False},
            ],
        },
        {
            "name": "Customer Feedback",
            "type": "survey",
            "fields": [
                {"id": "name",    "type": "text",     "label": "Your Name",       "required": False},
                {"id": "rating",  "type": "select",   "label": "Stay Experience", "required": True,
                 "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"]},
                {"id": "comment", "type": "textarea", "label": "Comments",        "required": False},
            ],
        },
    ],
}

DEFAULT_FORMS = [
    {
        "name": "Contact Us",
        "type": "contact",
        "fields": [
            {"id": "name",    "type": "text",     "label": "Full Name",       "required": True},
            {"id": "email",   "type": "email",    "label": "Email Address",   "required": True},
            {"id": "phone",   "type": "tel",      "label": "Phone Number",    "required": True},
            {"id": "subject", "type": "text",     "label": "Subject",         "required": True},
            {"id": "message", "type": "textarea", "label": "Message",         "required": True},
        ],
    },
    {
        "name": "Service Inquiry",
        "type": "order",
        "fields": [
            {"id": "name",    "type": "text",     "label": "Full Name",       "required": True},
            {"id": "phone",   "type": "tel",      "label": "Phone Number",    "required": True},
            {"id": "email",   "type": "email",    "label": "Email",           "required": False},
            {"id": "service", "type": "textarea", "label": "Service Needed",  "required": True},
            {"id": "date",    "type": "date",     "label": "Preferred Date",  "required": False},
        ],
    },
    {
        "name": "Customer Feedback",
        "type": "survey",
        "fields": [
            {"id": "name",    "type": "text",     "label": "Your Name",       "required": False},
            {"id": "rating",  "type": "select",   "label": "Overall Rating",  "required": True,
             "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"]},
            {"id": "comment", "type": "textarea", "label": "Comments",        "required": False},
        ],
    },
]


def get_forms_for_industry(industry: str) -> list[dict]:
    key = (industry or "").lower()
    for k, forms in INDUSTRY_FORMS.items():
        if k in key:
            return forms
    return DEFAULT_FORMS


# ── Pydantic models ────────────────────────────────────────────────────────────

class FormCreateRequest(BaseModel):
    name: str
    form_type: str = "contact"   # contact | order | survey
    fields: list[dict]
    business_name: str = ""
    notify_email: str = ""
    notify_whatsapp: str = ""


class FormSubmitRequest(BaseModel):
    data: dict[str, Any]
    source_url: str = ""


# ── Router factory ─────────────────────────────────────────────────────────────

def make_forms_router(db, get_current_user):
    router = APIRouter()

    # ── JS widget (served as JavaScript) ──────────────────────────────────────

    @router.get("/widget.js", include_in_schema=False)
    async def form_widget_js(request: Request):
        """Serve the Zilo Forms embeddable JavaScript widget."""
        base_url = str(request.base_url).rstrip("/")
        js = _build_widget_js(base_url)
        return Response(content=js, media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=3600"})

    # ── Create a form (auth) ───────────────────────────────────────────────────

    @router.post("")
    async def create_form(req: FormCreateRequest, user=Depends(get_current_user)):
        client_id = str(user.get("_id") or user.get("id", ""))
        doc = {
            "client_id": client_id,
            "name": req.name,
            "form_type": req.form_type,
            "fields": req.fields,
            "business_name": req.business_name,
            "notify_email": req.notify_email,
            "notify_whatsapp": req.notify_whatsapp,
            "entry_count": 0,
            "created_at": datetime.utcnow(),
        }
        result = await db.zilo_forms.insert_one(doc)
        form_id = str(result.inserted_id)
        logger.info("[forms] Created form '%s' id=%s for client=%s", req.name, form_id, client_id)
        return {"form_id": form_id, "name": req.name}

    # ── List forms for current user (auth) ────────────────────────────────────

    @router.get("")
    async def list_forms(user=Depends(get_current_user)):
        client_id = str(user.get("_id") or user.get("id", ""))
        forms = await db.zilo_forms.find(
            {"client_id": client_id}, {"_id": 1, "name": 1, "form_type": 1, "entry_count": 1, "created_at": 1}
        ).sort("created_at", -1).to_list(100)
        for f in forms:
            f["form_id"] = str(f.pop("_id"))
            if isinstance(f.get("created_at"), datetime):
                f["created_at"] = f["created_at"].isoformat()
        return {"forms": forms}

    # ── Get form definition (PUBLIC — used by the JS widget) ──────────────────

    @router.get("/{form_id}")
    async def get_form(form_id: str):
        try:
            oid = ObjectId(form_id)
        except Exception:
            raise HTTPException(400, "Invalid form ID")
        form = await db.zilo_forms.find_one({"_id": oid})
        if not form:
            raise HTTPException(404, "Form not found")
        return {
            "form_id": form_id,
            "name": form["name"],
            "form_type": form.get("form_type", "contact"),
            "fields": form["fields"],
            "business_name": form.get("business_name", ""),
        }

    # ── Submit a form entry (PUBLIC) ──────────────────────────────────────────

    @router.post("/{form_id}/submit")
    async def submit_form(form_id: str, req: FormSubmitRequest, request: Request):
        try:
            oid = ObjectId(form_id)
        except Exception:
            raise HTTPException(400, "Invalid form ID")

        form = await db.zilo_forms.find_one({"_id": oid})
        if not form:
            raise HTTPException(404, "Form not found")

        # Validate required fields
        for field in form.get("fields", []):
            if field.get("required") and not req.data.get(field["id"]):
                raise HTTPException(422, f"'{field['label']}' is required")

        entry = {
            "form_id": form_id,
            "client_id": form["client_id"],
            "form_name": form["name"],
            "form_type": form.get("form_type", "contact"),
            "data": req.data,
            "source_url": req.source_url,
            "ip": request.client.host if request.client else "",
            "submitted_at": datetime.utcnow(),
            "read": False,
        }
        await db.form_entries.insert_one(entry)
        await db.zilo_forms.update_one({"_id": oid}, {"$inc": {"entry_count": 1}})

        # Notify business owner via WhatsApp if configured
        wa = form.get("notify_whatsapp", "")
        if wa:
            try:
                summary = "\n".join(f"*{k}*: {v}" for k, v in req.data.items() if v)
                msg = f"📋 *New {form['name']} submission*\n\n{summary}\n\n_via Zilo Forms_"
                await db.outgoing_notifications.insert_one({
                    "to": wa, "message": msg, "type": "form_submission",
                    "form_id": form_id, "created_at": datetime.utcnow(), "sent": False,
                })
            except Exception as e:
                logger.warning("[forms] WhatsApp notify failed: %s", e)

        logger.info("[forms] New entry for form '%s' (client=%s)", form["name"], form["client_id"])
        return {"status": "ok", "message": "Thank you! We'll be in touch shortly."}

    # ── Get entries for a form (auth) ─────────────────────────────────────────

    @router.get("/{form_id}/entries")
    async def get_entries(form_id: str, limit: int = 50, user=Depends(get_current_user)):
        client_id = str(user.get("_id") or user.get("id", ""))
        try:
            oid = ObjectId(form_id)
        except Exception:
            raise HTTPException(400, "Invalid form ID")
        form = await db.zilo_forms.find_one({"_id": oid, "client_id": client_id})
        if not form:
            raise HTTPException(404, "Form not found")

        entries = await db.form_entries.find(
            {"form_id": form_id}, {"_id": 0}
        ).sort("submitted_at", -1).limit(limit).to_list(None)

        for e in entries:
            if isinstance(e.get("submitted_at"), datetime):
                e["submitted_at"] = e["submitted_at"].isoformat()

        return {"form_id": form_id, "name": form["name"], "entries": entries}

    # ── Delete a form (auth) ──────────────────────────────────────────────────

    @router.delete("/{form_id}")
    async def delete_form(form_id: str, user=Depends(get_current_user)):
        client_id = str(user.get("_id") or user.get("id", ""))
        try:
            oid = ObjectId(form_id)
        except Exception:
            raise HTTPException(400, "Invalid form ID")
        result = await db.zilo_forms.delete_one({"_id": oid, "client_id": client_id})
        if result.deleted_count == 0:
            raise HTTPException(404, "Form not found")
        await db.form_entries.delete_many({"form_id": form_id})
        return {"status": "deleted"}

    return router


# ── JavaScript widget ──────────────────────────────────────────────────────────

def _build_widget_js(api_base: str) -> str:
    return r"""
(function(){
'use strict';
var API = '""" + api_base + r"""/api/forms';

var STYLES = `
  .zf-wrap{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;margin:0 auto;padding:0}
  .zf-title{font-size:20px;font-weight:700;color:#0f172a;margin-bottom:20px}
  .zf-field{margin-bottom:18px}
  .zf-label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px}
  .zf-req{color:#ef4444;margin-left:2px}
  .zf-input{width:100%;padding:10px 14px;border:1.5px solid #e2e8f0;border-radius:8px;font-size:15px;
    color:#1e293b;background:#fff;box-sizing:border-box;transition:border-color .2s,box-shadow .2s;outline:none}
  .zf-input:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}
  .zf-input.zf-error{border-color:#ef4444}
  .zf-select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%2364748b' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat:no-repeat;background-position:right 14px center;padding-right:36px;cursor:pointer}
  .zf-radio-group,.zf-check-group{display:flex;flex-direction:column;gap:8px}
  .zf-radio-item,.zf-check-item{display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px 12px;
    border:1.5px solid #e2e8f0;border-radius:8px;transition:border-color .15s,background .15s}
  .zf-radio-item:hover,.zf-check-item:hover{border-color:#93c5fd;background:#f0f9ff}
  .zf-radio-item input,.zf-check-item input{accent-color:#2563eb;width:16px;height:16px;flex-shrink:0}
  .zf-radio-item span,.zf-check-item span{font-size:14px;color:#374151}
  .zf-btn{width:100%;padding:13px;background:linear-gradient(135deg,#2563eb,#1e40af);color:#fff;border:none;
    border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px;
    transition:opacity .2s,transform .1s}
  .zf-btn:hover{opacity:.93}
  .zf-btn:active{transform:scale(.99)}
  .zf-btn:disabled{opacity:.6;cursor:not-allowed}
  .zf-success{text-align:center;padding:36px 24px;background:linear-gradient(135deg,#f0fdf4,#dcfce7);
    border-radius:14px;border:1.5px solid #86efac}
  .zf-success-icon{font-size:48px;margin-bottom:12px}
  .zf-success-title{font-size:20px;font-weight:700;color:#15803d;margin-bottom:8px}
  .zf-success-msg{font-size:15px;color:#166534}
  .zf-err-banner{background:#fef2f2;border:1.5px solid #fca5a5;border-radius:8px;
    padding:10px 14px;color:#dc2626;font-size:14px;margin-bottom:16px}
  .zf-loading{text-align:center;padding:40px;color:#64748b;font-size:15px}
  .zf-footer{margin-top:16px;text-align:center;font-size:11px;color:#94a3b8}
  .zf-footer a{color:#94a3b8;text-decoration:none}
  .zf-footer a:hover{color:#64748b}
`;

function injectStyles(){
  if(document.getElementById('zilo-form-styles')) return;
  var s=document.createElement('style');
  s.id='zilo-form-styles';
  s.textContent=STYLES;
  document.head.appendChild(s);
}

function el(tag,cls,html){
  var e=document.createElement(tag);
  if(cls) e.className=cls;
  if(html!==undefined) e.innerHTML=html;
  return e;
}

function renderField(field){
  var wrap=el('div','zf-field');
  var labelEl=el('label','zf-label');
  labelEl.setAttribute('for','zf-'+field.id);
  labelEl.innerHTML=field.label+(field.required?'<span class="zf-req">*</span>':'');
  wrap.appendChild(labelEl);

  var t=field.type;
  if(t==='textarea'){
    var ta=el('textarea','zf-input');
    ta.id='zf-'+field.id; ta.name=field.id; ta.rows=3;
    ta.placeholder=field.placeholder||'';
    wrap.appendChild(ta);
  } else if(t==='select'){
    var sel=el('select','zf-input zf-select');
    sel.id='zf-'+field.id; sel.name=field.id;
    var opt=document.createElement('option');
    opt.value=''; opt.textContent='Select an option…';
    sel.appendChild(opt);
    (field.options||[]).forEach(function(o){
      var op=document.createElement('option');
      op.value=o; op.textContent=o;
      sel.appendChild(op);
    });
    wrap.appendChild(sel);
  } else if(t==='radio'){
    var rg=el('div','zf-radio-group');
    (field.options||[]).forEach(function(o){
      var item=el('div','zf-radio-item');
      var inp=document.createElement('input');
      inp.type='radio'; inp.name=field.id; inp.value=o; inp.id='zf-'+field.id+'-'+o.replace(/\s/g,'_');
      var sp=el('span','',o);
      item.appendChild(inp); item.appendChild(sp);
      item.addEventListener('click',function(){inp.checked=true;});
      rg.appendChild(item);
    });
    wrap.appendChild(rg);
  } else if(t==='checkbox'){
    var cg=el('div','zf-check-group');
    (field.options||[]).forEach(function(o){
      var item=el('div','zf-check-item');
      var inp=document.createElement('input');
      inp.type='checkbox'; inp.name=field.id; inp.value=o; inp.id='zf-'+field.id+'-'+o.replace(/\s/g,'_');
      var sp=el('span','',o);
      item.appendChild(inp); item.appendChild(sp);
      cg.appendChild(item);
    });
    wrap.appendChild(cg);
  } else {
    var inp=el('input','zf-input');
    inp.id='zf-'+field.id; inp.name=field.id; inp.type=t||'text';
    inp.placeholder=field.placeholder||'';
    wrap.appendChild(inp);
  }
  return wrap;
}

function collectData(form_def,container){
  var data={};
  (form_def.fields||[]).forEach(function(field){
    var t=field.type;
    if(t==='radio'){
      var checked=container.querySelector('input[name="'+field.id+'"]:checked');
      data[field.id]=checked?checked.value:'';
    } else if(t==='checkbox'){
      var vals=[];
      container.querySelectorAll('input[name="'+field.id+'"]:checked').forEach(function(cb){vals.push(cb.value);});
      data[field.id]=vals.join(', ');
    } else {
      var el=container.querySelector('[name="'+field.id+'"]');
      data[field.id]=el?el.value.trim():'';
    }
  });
  return data;
}

function validate(form_def,data){
  var errors=[];
  (form_def.fields||[]).forEach(function(field){
    if(field.required && !data[field.id]){
      errors.push(field.label+' is required');
      var inp=document.querySelector('#zf-'+field.id);
      if(inp) inp.classList.add('zf-error');
    }
  });
  return errors;
}

window.ZiloForm={
  render:function(containerId,formId){
    injectStyles();
    var container=document.getElementById(containerId);
    if(!container){console.warn('[ZiloForm] container #'+containerId+' not found');return;}
    container.innerHTML='<div class="zf-loading">Loading form…</div>';

    fetch(API+'/'+formId)
      .then(function(r){return r.json();})
      .then(function(form_def){
        container.innerHTML='';
        var wrap=el('div','zf-wrap');
        var title=el('div','zf-title',form_def.name);
        wrap.appendChild(title);

        (form_def.fields||[]).forEach(function(field){
          wrap.appendChild(renderField(field));
        });

        var btn=el('button','zf-btn','Send Message');
        wrap.appendChild(btn);

        var footer=el('div','zf-footer','<a href="https://zilo.pro" target="_blank" rel="noopener">Powered by Zilo</a>');
        wrap.appendChild(footer);

        container.appendChild(wrap);

        btn.addEventListener('click',function(){
          // Clear previous errors
          container.querySelectorAll('.zf-error').forEach(function(e){e.classList.remove('zf-error');});
          container.querySelectorAll('.zf-err-banner').forEach(function(e){e.remove();});

          var data=collectData(form_def,container);
          var errors=validate(form_def,data);
          if(errors.length){
            var banner=el('div','zf-err-banner',errors[0]);
            wrap.insertBefore(banner,btn);
            return;
          }

          btn.disabled=true; btn.textContent='Sending…';
          fetch(API+'/'+formId+'/submit',{
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({data:data,source_url:window.location.href})
          })
          .then(function(r){return r.json();})
          .then(function(res){
            if(res.status==='ok'){
              container.innerHTML='<div class="zf-success"><div class="zf-success-icon">✅</div>'
                +'<div class="zf-success-title">Message Sent!</div>'
                +'<div class="zf-success-msg">'+(res.message||"Thank you! We'll be in touch shortly.")+'</div>'
                +'<div style="margin-top:16px;font-size:11px;color:#86efac"><a href="https://zilo.pro" target="_blank" rel="noopener" style="color:#86efac">Powered by Zilo</a></div></div>';
            } else {
              btn.disabled=false; btn.textContent='Send Message';
              var banner=el('div','zf-err-banner',res.detail||'Submission failed. Please try again.');
              wrap.insertBefore(banner,btn);
            }
          })
          .catch(function(){
            btn.disabled=false; btn.textContent='Send Message';
            var banner=el('div','zf-err-banner','Network error. Please try again.');
            wrap.insertBefore(banner,btn);
          });
        });
      })
      .catch(function(){
        container.innerHTML='<div class="zf-err-banner">Could not load form. Please refresh the page.</div>';
      });
  }
};
})();
"""


async def seed_zilo_forms(db, client_id: str, business_name: str, industry: str, notify_whatsapp: str = "") -> dict:
    """
    Creates the standard set of Zilo forms for a new client subsite.
    Returns {contact_id, order_id, survey_id}.
    """
    forms = get_forms_for_industry(industry)
    ids: dict[str, str] = {"contact": "", "order": "", "survey": ""}

    for form_def in forms:
        doc = {
            "client_id": client_id,
            "name": form_def["name"],
            "form_type": form_def["type"],
            "fields": form_def["fields"],
            "business_name": business_name,
            "notify_whatsapp": notify_whatsapp,
            "notify_email": "",
            "entry_count": 0,
            "created_at": datetime.utcnow(),
        }
        result = await db.zilo_forms.insert_one(doc)
        fid = str(result.inserted_id)
        ftype = form_def["type"]
        if ftype in ids:
            ids[ftype] = fid
        logger.info("[forms] Seeded '%s' (type=%s) id=%s for client=%s", form_def["name"], ftype, fid, client_id)

    return ids

"""
Form Builder — create shareable lead-capture forms.
Submissions auto-create contacts in the CRM.
"""
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _uid(user) -> str:
    return str(user["_id"])


def _make_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"


class CreateForm(BaseModel):
    title: str
    description: Optional[str] = None
    fields: Optional[List[Dict[str, Any]]] = None
    settings: Optional[Dict[str, Any]] = None
    branding: Optional[Dict[str, Any]] = None
    active: bool = True


class SubmitForm(BaseModel):
    data: Dict[str, Any]


def make_forms_router(db, user_dep):
    router = APIRouter(prefix="/forms", tags=["forms"])

    # ── JS widget (served as JavaScript — used by blog pages) ─────────────────

    @router.get("/widget.js", include_in_schema=False)
    async def form_widget_js(request: Request):
        import os
        base_url = os.getenv("BACKEND_PUBLIC_URL", "").rstrip("/")
        if not base_url:
            base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
        js = _build_widget_js(base_url)
        return Response(content=js, media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})

    # ─────────────────────────────────────────────────────────────────────────
    # Public — serve & submit (NO auth — must be defined before /{form_id})
    # ─────────────────────────────────────────────────────────────────────────

    @router.get("/public/{slug}")
    async def get_public_form(slug: str):
        doc = await db.forms.find_one({"slug": slug, "active": True})
        if not doc:
            raise HTTPException(404, "Form not found or inactive")
        return {
            "id": str(doc["_id"]),
            "title": doc.get("title", ""),
            "description": doc.get("description", ""),
            "fields": doc.get("fields", []),
            "settings": {
                "success_message": doc.get("settings", {}).get(
                    "success_message", "Thank you! We'll be in touch soon."
                ),
            },
            "branding": doc.get("branding", {}),
        }

    @router.post("/public/{slug}/submit")
    async def submit_form(slug: str, body: SubmitForm):
        form = await db.forms.find_one({"slug": slug, "active": True})
        if not form:
            raise HTTPException(404, "Form not found")

        form_id = str(form["_id"])
        uid = form["user_id"]
        settings = form.get("settings", {})

        submission: Dict[str, Any] = {
            "_id": str(uuid.uuid4()),
            "form_id": form_id,
            "user_id": uid,
            "data": body.data,
            "created_at": datetime.utcnow(),
        }

        # Auto-create contact from submission data
        if settings.get("create_contact", True):
            name = (
                body.data.get("name")
                or body.data.get("full_name")
                or body.data.get("Name")
                or body.data.get("Full Name")
                or ""
            )
            phone = (
                body.data.get("phone")
                or body.data.get("Phone")
                or body.data.get("Phone Number")
                or body.data.get("mobile")
                or ""
            )
            email = (
                body.data.get("email")
                or body.data.get("Email")
                or body.data.get("Email Address")
                or ""
            )

            if name or phone or email:
                existing = None
                if phone:
                    existing = await db.contacts.find_one({"user_id": uid, "phone": phone})
                if not existing and email:
                    existing = await db.contacts.find_one({"user_id": uid, "email": email})

                if not existing:
                    contact_id = str(uuid.uuid4())
                    # Build a notes string from all submitted data
                    notes_lines = [f"{k}: {v}" for k, v in body.data.items() if v]
                    await db.contacts.insert_one({
                        "_id": contact_id,
                        "user_id": uid,
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "source": f"form:{form.get('title', '')}",
                        "notes": "Form: " + form.get("title", "") + "\n" + "\n".join(notes_lines),
                        "created_at": datetime.utcnow(),
                    })
                    submission["contact_id"] = contact_id
                else:
                    submission["contact_id"] = str(existing["_id"])

        await db.form_submissions.insert_one(submission)
        await db.forms.update_one({"_id": form_id}, {"$inc": {"response_count": 1}})

        return {
            "status": "ok",
            "message": settings.get("success_message", "Thank you! We'll be in touch soon."),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Authenticated CRUD
    # ─────────────────────────────────────────────────────────────────────────

    @router.post("")
    async def create_form(body: CreateForm, user=Depends(user_dep)):
        uid = _uid(user)
        slug = _make_slug(body.title)
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": uid,
            "title": body.title,
            "description": body.description or "",
            "slug": slug,
            "fields": body.fields if body.fields is not None else _default_fields(),
            "settings": body.settings or {
                "success_message": "Thank you! We'll be in touch soon.",
                "create_contact": True,
                "auto_whatsapp": False,
            },
            "branding": body.branding or {},
            "active": body.active,
            "response_count": 0,
            "created_at": datetime.utcnow(),
        }
        await db.forms.insert_one(doc)
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @router.get("")
    async def list_forms(user=Depends(user_dep)):
        uid = _uid(user)
        items = await db.forms.find({"user_id": uid}).sort("created_at", -1).to_list(100)
        for i in items:
            if hasattr(i.get("created_at"), "isoformat"):
                i["created_at"] = i["created_at"].isoformat()
        return {"forms": items}

    @router.get("/{form_id}")
    async def get_form(form_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        doc = await db.forms.find_one({"_id": form_id, "user_id": uid})
        if not doc:
            raise HTTPException(404, "Form not found")
        if hasattr(doc.get("created_at"), "isoformat"):
            doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @router.put("/{form_id}")
    async def update_form(form_id: str, body: CreateForm, user=Depends(user_dep)):
        uid = _uid(user)
        result = await db.forms.update_one(
            {"_id": form_id, "user_id": uid},
            {"$set": {
                "title": body.title,
                "description": body.description or "",
                "fields": body.fields if body.fields is not None else [],
                "settings": body.settings or {},
                "branding": body.branding or {},
                "active": body.active,
                "updated_at": datetime.utcnow(),
            }},
        )
        if result.matched_count == 0:
            raise HTTPException(404, "Form not found")
        return {"status": "updated"}

    @router.delete("/{form_id}")
    async def delete_form(form_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        result = await db.forms.delete_one({"_id": form_id, "user_id": uid})
        if result.deleted_count == 0:
            raise HTTPException(404, "Form not found")
        await db.form_submissions.delete_many({"form_id": form_id})
        return {"status": "deleted"}

    @router.get("/{form_id}/responses")
    async def get_responses(form_id: str, user=Depends(user_dep)):
        uid = _uid(user)
        form = await db.forms.find_one({"_id": form_id, "user_id": uid})
        if not form:
            raise HTTPException(404, "Form not found")
        items = await db.form_submissions.find(
            {"form_id": form_id}
        ).sort("created_at", -1).to_list(500)
        for i in items:
            if hasattr(i.get("created_at"), "isoformat"):
                i["created_at"] = i["created_at"].isoformat()
        return {"responses": items, "total": len(items)}

    return router


def _default_fields() -> list:
    return [
        {
            "id": str(uuid.uuid4())[:8],
            "type": "text",
            "label": "Full Name",
            "placeholder": "Your name",
            "required": True,
        },
        {
            "id": str(uuid.uuid4())[:8],
            "type": "phone",
            "label": "Phone Number",
            "placeholder": "+1...",
            "required": True,
        },
        {
            "id": str(uuid.uuid4())[:8],
            "type": "email",
            "label": "Email Address",
            "placeholder": "you@example.com",
            "required": False,
        },
        {
            "id": str(uuid.uuid4())[:8],
            "type": "textarea",
            "label": "Message",
            "placeholder": "What can we help you with?",
            "required": False,
        },
    ]


# ── Blog form seeder — creates industry-specific forms in the existing system ──

_BLOG_FORM_DEFS: dict[str, list[dict]] = {
    "restaurant": [
        {"type": "contact", "title": "Contact Us", "fields": [
            {"id": "name",    "type": "text",     "label": "Full Name",        "placeholder": "Your name",         "required": True},
            {"id": "phone",   "type": "phone",    "label": "Phone Number",     "placeholder": "+1…",             "required": True},
            {"id": "email",   "type": "email",    "label": "Email Address",    "placeholder": "you@example.com",   "required": False},
            {"id": "message", "type": "textarea", "label": "Message",          "placeholder": "How can we help?",  "required": False},
        ]},
        {"type": "order", "title": "Table Reservation", "fields": [
            {"id": "name",    "type": "text",     "label": "Full Name",        "placeholder": "Your name",         "required": True},
            {"id": "phone",   "type": "phone",    "label": "Phone Number",     "placeholder": "+1…",             "required": True},
            {"id": "guests",  "type": "dropdown", "label": "Number of Guests", "placeholder": "",                  "required": True,
             "options": ["1–2", "3–5", "6–10", "11–20", "Above 20"]},
            {"id": "date",    "type": "text",     "label": "Date",             "placeholder": "e.g. 15 Jan 2026",  "required": True},
            {"id": "time",    "type": "dropdown", "label": "Time",             "placeholder": "",                  "required": True,
             "options": ["12:00 PM (Lunch)", "1:00 PM", "6:00 PM (Dinner)", "7:00 PM", "8:00 PM"]},
            {"id": "notes",   "type": "textarea", "label": "Special Requests", "placeholder": "Anything we should know?", "required": False},
        ]},
        {"type": "survey", "title": "Customer Feedback", "fields": [
            {"id": "name",    "type": "text",     "label": "Your Name",        "placeholder": "Optional",          "required": False},
            {"id": "rating",  "type": "dropdown", "label": "Overall Experience","placeholder": "Select rating",   "required": True,
             "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"]},
            {"id": "revisit", "type": "dropdown", "label": "Would You Visit Again?", "placeholder": "",           "required": True,
             "options": ["Definitely Yes", "Probably", "Not Sure", "No"]},
            {"id": "comment", "type": "textarea", "label": "Comments",         "placeholder": "Tell us more…",    "required": False},
        ]},
    ],
    "salon": [
        {"type": "order", "title": "Appointment Booking", "fields": [
            {"id": "name",    "type": "text",     "label": "Full Name",        "placeholder": "Your name",         "required": True},
            {"id": "phone",   "type": "phone",    "label": "Phone Number",     "placeholder": "+1…",             "required": True},
            {"id": "service", "type": "dropdown", "label": "Service",          "placeholder": "Select service",    "required": True,
             "options": ["Hair Braiding", "Relaxer / Perming", "Hair Cut & Style", "Weave Installation", "Nails", "Facial", "Massage", "Other"]},
            {"id": "date",    "type": "text",     "label": "Preferred Date",   "placeholder": "e.g. 15 Jan 2026",  "required": True},
            {"id": "time",    "type": "dropdown", "label": "Preferred Time",   "placeholder": "Select time",       "required": True,
             "options": ["8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM", "12:00 PM", "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM"]},
            {"id": "notes",   "type": "textarea", "label": "Special Requests", "placeholder": "Anything we should know?", "required": False},
        ]},
        {"type": "contact", "title": "Contact Us", "fields": [
            {"id": "name",    "type": "text",     "label": "Full Name",        "placeholder": "Your name",         "required": True},
            {"id": "phone",   "type": "phone",    "label": "Phone Number",     "placeholder": "+1…",             "required": True},
            {"id": "message", "type": "textarea", "label": "Message",          "placeholder": "How can we help?",  "required": False},
        ]},
        {"type": "survey", "title": "Customer Feedback", "fields": [
            {"id": "name",    "type": "text",     "label": "Your Name",        "placeholder": "Optional",          "required": False},
            {"id": "rating",  "type": "dropdown", "label": "Overall Experience","placeholder": "Select rating",   "required": True,
             "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"]},
            {"id": "comment", "type": "textarea", "label": "Comments",         "placeholder": "Tell us more…",    "required": False},
        ]},
    ],
}

_DEFAULT_BLOG_FORMS = [
    {"type": "contact", "title": "Contact Us", "fields": [
        {"id": "name",    "type": "text",     "label": "Full Name",    "placeholder": "Your name",        "required": True},
        {"id": "phone",   "type": "phone",    "label": "Phone Number", "placeholder": "+1…",            "required": True},
        {"id": "email",   "type": "email",    "label": "Email",        "placeholder": "you@example.com",  "required": False},
        {"id": "message", "type": "textarea", "label": "Message",      "placeholder": "How can we help?", "required": False},
    ]},
    {"type": "order", "title": "Service Inquiry", "fields": [
        {"id": "name",    "type": "text",     "label": "Full Name",    "placeholder": "Your name",        "required": True},
        {"id": "phone",   "type": "phone",    "label": "Phone Number", "placeholder": "+1…",            "required": True},
        {"id": "service", "type": "textarea", "label": "Service Needed","placeholder": "What do you need?","required": True},
        {"id": "date",    "type": "text",     "label": "Preferred Date","placeholder": "e.g. 15 Jan 2026", "required": False},
    ]},
    {"type": "survey", "title": "Customer Feedback", "fields": [
        {"id": "name",    "type": "text",     "label": "Your Name",    "placeholder": "Optional",         "required": False},
        {"id": "rating",  "type": "dropdown", "label": "Overall Rating","placeholder": "Select rating",   "required": True,
         "options": ["⭐⭐⭐⭐⭐ Excellent", "⭐⭐⭐⭐ Good", "⭐⭐⭐ Average", "⭐⭐ Poor"]},
        {"id": "comment", "type": "textarea", "label": "Comments",     "placeholder": "Tell us more…",    "required": False},
    ]},
]


def _get_blog_forms_for_industry(industry: str) -> list[dict]:
    key = (industry or "").lower()
    for k, forms in _BLOG_FORM_DEFS.items():
        if k in key:
            return forms
    return _DEFAULT_BLOG_FORMS


async def seed_blog_forms(db, user_id: str, business_name: str, industry: str) -> dict[str, str]:
    """
    Creates the standard set of forms (contact, order, survey) for a new blog site.
    Forms are created in the main `forms` collection so they appear in the user's
    forms dashboard automatically. Returns {contact: slug, order: slug, survey: slug}.
    """
    form_defs = _get_blog_forms_for_industry(industry)
    slugs: dict[str, str] = {"contact": "", "order": "", "survey": ""}

    for form_def in form_defs:
        ftype = form_def["type"]
        slug = _make_slug(form_def["title"])
        doc = {
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": form_def["title"],
            "description": f"Auto-created for {business_name}",
            "slug": slug,
            "fields": form_def["fields"],
            "settings": {
                "success_message": "Thank you! We'll be in touch shortly via WhatsApp.",
                "create_contact": True,
                "auto_whatsapp": False,
            },
            "branding": {},
            "active": True,
            "response_count": 0,
            "created_at": datetime.utcnow(),
            "source": "blog_autoseed",
        }
        await db.forms.insert_one(doc)
        if ftype in slugs:
            slugs[ftype] = slug
        logger.info("[forms] Blog seeded '%s' slug=%s for user=%s", form_def["title"], slug, user_id)

    return slugs


def _build_widget_js(api_base: str) -> str:
    """Returns the self-contained Zilo Forms JS widget (~5KB)."""
    return r"""
(function(){
'use strict';
var API='""" + api_base + r"""/api/forms';
var S=`
.zf-wrap{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;margin:0 auto}
.zf-title{font-size:20px;font-weight:700;color:#0f172a;margin-bottom:20px}
.zf-field{margin-bottom:18px}
.zf-label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px}
.zf-req{color:#ef4444;margin-left:2px}
.zf-input{width:100%;padding:10px 14px;border:1.5px solid #e2e8f0;border-radius:8px;font-size:15px;color:#1e293b;background:#fff;box-sizing:border-box;transition:border-color .2s;outline:none}
.zf-input:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}
.zf-input.zf-err{border-color:#ef4444}
.zf-select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%2364748b' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 14px center;padding-right:36px;cursor:pointer}
.zf-btn{width:100%;padding:13px;background:linear-gradient(135deg,#2563eb,#1e40af);color:#fff;border:none;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px;transition:opacity .2s}
.zf-btn:hover{opacity:.92}
.zf-btn:disabled{opacity:.55;cursor:not-allowed}
.zf-ok{text-align:center;padding:36px 24px;background:#f0fdf4;border-radius:14px;border:1.5px solid #86efac}
.zf-ok-icon{font-size:48px;margin-bottom:12px}
.zf-ok-title{font-size:20px;font-weight:700;color:#15803d;margin-bottom:8px}
.zf-ok-msg{font-size:15px;color:#166534}
.zf-banner{background:#fef2f2;border:1.5px solid #fca5a5;border-radius:8px;padding:10px 14px;color:#dc2626;font-size:14px;margin-bottom:16px}
.zf-loading{text-align:center;padding:40px;color:#64748b;font-size:15px}
.zf-foot{margin-top:16px;text-align:center;font-size:11px;color:#94a3b8}
.zf-foot a{color:#94a3b8;text-decoration:none}
`;
function injectCss(){if(!document.getElementById('_zf_css')){var s=document.createElement('style');s.id='_zf_css';s.textContent=S;document.head.appendChild(s);}}
function el(t,c,h){var e=document.createElement(t);if(c)e.className=c;if(h!==undefined)e.innerHTML=h;return e;}
function renderField(f){
  var w=el('div','zf-field');
  var lb=el('label','zf-label');
  lb.setAttribute('for','_zf_'+f.id);
  lb.innerHTML=f.label+(f.required?'<span class="zf-req">*</span>':'');
  w.appendChild(lb);
  var t=f.type;
  if(t==='textarea'){var ta=el('textarea','zf-input');ta.id='_zf_'+f.id;ta.name=f.id;ta.rows=3;ta.placeholder=f.placeholder||'';w.appendChild(ta);}
  else if(t==='dropdown'){var sl=el('select','zf-input zf-select');sl.id='_zf_'+f.id;sl.name=f.id;var op=document.createElement('option');op.value='';op.textContent='Select…';sl.appendChild(op);(f.options||[]).forEach(function(o){var p=document.createElement('option');p.value=o;p.textContent=o;sl.appendChild(p);});w.appendChild(sl);}
  else{var inp=el('input','zf-input');inp.id='_zf_'+f.id;inp.name=f.id;inp.type=(t==='phone'?'tel':t==='email'?'email':'text');inp.placeholder=f.placeholder||'';w.appendChild(inp);}
  return w;
}
function collect(fields,ctr){var d={};fields.forEach(function(f){var e=ctr.querySelector('[name="'+f.id+'"]');d[f.id]=e?e.value.trim():'';});return d;}
function validate(fields,data){var errs=[];fields.forEach(function(f){if(f.required&&!data[f.id]){errs.push(f.label+' is required');var e=document.querySelector('#_zf_'+f.id);if(e)e.classList.add('zf-err');}});return errs;}
window.ZiloForm={
  render:function(cid,slug){
    injectCss();
    var ctr=document.getElementById(cid);
    if(!ctr){console.warn('[ZiloForm] #'+cid+' not found');return;}
    ctr.innerHTML='<div class="zf-loading">Loading…</div>';
    fetch(API+'/public/'+slug)
      .then(function(r){return r.json();})
      .then(function(fd){
        ctr.innerHTML='';
        var w=el('div','zf-wrap');
        w.appendChild(el('div','zf-title',fd.title));
        (fd.fields||[]).forEach(function(f){w.appendChild(renderField(f));});
        var btn=el('button','zf-btn','Send Message');
        w.appendChild(btn);
        w.appendChild(el('div','zf-foot','<a href="https://zilo.pro" target="_blank" rel="noopener">Powered by Zilo</a>'));
        ctr.appendChild(w);
        btn.addEventListener('click',function(){
          ctr.querySelectorAll('.zf-err').forEach(function(e){e.classList.remove('zf-err');});
          ctr.querySelectorAll('.zf-banner').forEach(function(e){e.remove();});
          var data=collect(fd.fields,ctr);
          var errs=validate(fd.fields,data);
          if(errs.length){var b=el('div','zf-banner',errs[0]);w.insertBefore(b,btn);return;}
          btn.disabled=true;btn.textContent='Sending…';
          fetch(API+'/public/'+slug+'/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data:data})})
            .then(function(r){return r.json();})
            .then(function(res){
              if(res.status==='ok'){ctr.innerHTML='<div class="zf-ok"><div class="zf-ok-icon">✅</div><div class="zf-ok-title">Sent!</div><div class="zf-ok-msg">'+(res.message||"We'll be in touch shortly.")+'</div><div style="margin-top:14px;font-size:11px"><a href="https://zilo.pro" target="_blank" style="color:#86efac">Powered by Zilo</a></div></div>';}
              else{btn.disabled=false;btn.textContent='Send Message';w.insertBefore(el('div','zf-banner',res.detail||'Something went wrong.'),btn);}
            })
            .catch(function(){btn.disabled=false;btn.textContent='Send Message';w.insertBefore(el('div','zf-banner','Network error. Please try again.'),btn);});
        });
      })
      .catch(function(){ctr.innerHTML='<div class="zf-banner">Could not load form. Please refresh.</div>';});
  }
};
})();
"""

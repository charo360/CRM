import os
import sys
from pathlib import Path
import re
from dotenv import load_dotenv

# Load env before ANY other imports
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

import os
# Check AWS immediately
if os.environ.get("AWS_ACCESS_KEY_ID"):
    print("STARTUP_CHECK: AWS Credentials DETECTED")
else:
    print("STARTUP_CHECK: AWS Credentials NOT DETECTED")

# Validate environment on startup
def validate_startup_env():
    """Quick validation to catch common issues"""
    print("DEBUG: MODIFIED STARTUP CHECK RUNNING")
    ai_provider = os.environ.get('AI_PROVIDER', 'openai').strip().lower()
    if ai_provider == 'deepseek':
        api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        key_name = 'DEEPSEEK_API_KEY'
        label = 'DeepSeek'
    else:
        api_key = os.environ.get('OPENAI_API_KEY', '')
        key_name = 'OPENAI_API_KEY'
        label = 'OpenAI'
    
    if not api_key or api_key in ('your_openai_api_key_here', 'your_deepseek_api_key_here'):
        print("\n" + "="*60)
        print(f"[CRITICAL] ERROR: {key_name} not configured in .env file")
        print("="*60 + "\n")
        sys.exit(1)
    else:
        print(f"[OK] {label} API Key loaded (ends with: ...{api_key[-10:]})")

    # Check optional keys
    if os.environ.get('ANTHROPIC_API_KEY'):
        print("[OK] Anthropic API Key DETECTED")
    else:
        print("[INFO] Anthropic API Key NOT DETECTED (Claude will not work)")
        
    if os.environ.get('GROK_API_KEY') or os.environ.get('XS_API_KEY'):
        print("[OK] Grok/xAI API Key DETECTED")
    else:
        print("[INFO] Grok/xAI API Key NOT DETECTED (Grok will not work)")

validate_startup_env()

from fastapi import FastAPI, APIRouter, HTTPException, Depends, BackgroundTasks, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import io
import difflib
# Force UTF-8 for Windows console output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import logging
import asyncio

# Configure logging with rotation (10 MB per file, keep 3 backups) + stdout
from logging.handlers import RotatingFileHandler as _RotatingFileHandler
log_file = Path("/tmp/server.log") if os.environ.get("RENDER") else ROOT_DIR.parent / "server.log"
_log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_file_handler = _RotatingFileHandler(str(log_file), maxBytes=10*1024*1024, backupCount=3, encoding='utf-8')
_file_handler.setFormatter(_log_formatter)
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_log_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _stream_handler])
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
import uuid
from datetime import datetime, timedelta
import jwt
import httpx
import hmac
import hashlib
import json
import re as _re
# Evolution API replaces Twilio — config in whatsapp_service.py
# from emergentintegrations.llm.chat import LlmChat, UserMessage
from ai_service import get_drafter, AIMessageDrafter
from daily_analyzer import DailyCustomerAnalyzer
from notification_service import get_notification_service
from image_handler import ImageUploadHandler, S3Handler
from product_organizer import get_organizer
from whatsapp_service import get_whatsapp_service
from followup_analytics import get_analytics
from smart_notifications import get_smart_notifications
from supplier_analyzer import SupplierAnalyzer
from contact_classifier import get_classifier
from fastapi import UploadFile, File, Body, Form
from fastapi.staticfiles import StaticFiles
from daily_scheduler import start_daily_scheduler
from mongo_http_client import AsyncMongoHTTPClient
from google_play_billing import check_feature_access, check_limit, SUBSCRIPTION_LIMITS



from bson import ObjectId as _ObjectId

# Anti-duplicate auto-reply guard: tracks evo_message_id to prevent double replies
# Evolution API often fires messages.upsert webhook multiple times for the same message
import asyncio as _aio
_auto_reply_dedup = {}  # key: evo_message_id -> timestamp
_auto_reply_lock = _aio.Lock()
_AUTO_REPLY_DEDUP_TTL = 120  # seconds

# Ping-pong loop guard: tracks last auto-reply sent time per (user_id, phone)
# key: "user_id:phone" -> timestamp of last auto-reply sent
_last_auto_reply_sent: dict = {}
_PING_PONG_TTL = 5  # seconds — only block instant AI echoes (real humans take >5s to type follow-ups)

# Keywords that indicate a genuine business information request — these bypass the loop guard
_BUSINESS_INFO_KEYWORDS = [
    "price", "cost", "how much", "pric", "bei", "bei gani", "ngapi", "charges", "fee",
    "product", "item", "stock", "available", "catalog", "catalogue", "menu",
    "dress", "shoe", "bag", "cloth", "fabric", "trouser", "shirt", "skirt", "jean",
    "food", "drink", "meal", "juice", "water", "coffee", "tea",
    "phone", "laptop", "computer", "tv", "appliance", "electronic",
    "order", "buy", "purchase", "delivery", "deliver", "shipping", "ship",
    "location", "address", "where are you", "directions", "open", "hours", "working hours",
    "payment", "pay", "mpesa", "m-pesa", "bank", "transfer", "cash",
    "contact", "email", "whatsapp", "reach",
    "offer", "discount", "sale", "promo", "promotion", "deal",
    "service", "repair", "fix", "install", "maintain",
    "hello", "hi ", "hii", "habari", "mambo", "sema", "niaje", "hey",
    "do you have", "do you sell", "can i", "is it", "are you", "what is", "what are",
    "i want", "i need", "looking for", "nataka", "nahitaji",
]

def _is_business_info_request(message: str) -> bool:
    """Returns True if the message looks like a genuine business inquiry, not an AI echo."""
    msg_lower = message.lower().strip()
    # A message ending with ? is almost always a genuine question
    if msg_lower.endswith("?"):
        return True
    # Short messages (under 15 words) that aren't clearly automated
    word_count = len(msg_lower.split())
    if word_count <= 8:
        return True
    return any(kw in msg_lower for kw in _BUSINESS_INFO_KEYWORDS)

def serialize_doc(doc):
    """Recursively convert MongoDB ObjectId fields to strings for JSON serialization."""
    if isinstance(doc, dict):
        return {k: serialize_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    elif isinstance(doc, _ObjectId):
        return str(doc)
    return doc

def sanitize_string(value: str, max_length: int = 500) -> str:
    """Strip dangerous characters and limit length for user input."""
    if not value:
        return value
    # Remove null bytes and control characters (keep newlines/tabs)
    value = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', value)
    # Strip leading/trailing whitespace
    value = value.strip()
    # Enforce max length
    return value[:max_length]

def sanitize_phone(phone: str) -> str:
    """Normalize phone number: keep only digits and leading +."""
    if not phone:
        return phone
    phone = phone.strip()
    if phone.startswith('+'):
        return '+' + _re.sub(r'[^\d]', '', phone[1:])
    return _re.sub(r'[^\d]', '', phone)

# === AGENT SYSTEM ===
from agents.router import Router
# ====================

def normalize_url(u):
    """Normalize media URLs so Evolution API (external) can fetch them."""
    import re as _re
    if not u:
        return u
    # Always prefer PUBLIC_BASE_URL (set on Render) for relative paths
    _public_base = os.environ.get('PUBLIC_BASE_URL') or os.environ.get('WEBHOOK_BASE_URL') or ''
    if u.startswith('/'):
        if _public_base:
            return f"{_public_base.rstrip('/')}{u}"
        return f"http://host.docker.internal:8000{u}"
    # If running on Render (PUBLIC_BASE_URL set), replace any localhost/docker URLs
    if _public_base:
        if u.startswith('http://localhost:') or u.startswith('http://127.0.0.1:'):
            # Strip port, replace with public base + path
            path = '/' + u.split('/', 3)[-1] if u.count('/') >= 3 else ''
            return f"{_public_base.rstrip('/')}{path}"
        if u.startswith('http://host.docker.internal:'):
            path = '/' + u.split('/', 3)[-1] if u.count('/') >= 3 else ''
            return f"{_public_base.rstrip('/')}{path}"
    # Local Docker fallback
    if u.startswith('http://localhost:'):
        return u.replace('http://localhost:', 'http://host.docker.internal:')
    if u.startswith('http://127.0.0.1:'):
        return u.replace('http://127.0.0.1:', 'http://host.docker.internal:')
    # Replace any LAN/private IP with host.docker.internal
    u = _re.sub(r'http://(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.\d+\.\d+\.\d+):(\d+)',
                lambda m: f'http://host.docker.internal:{m.group(2)}', u)
    return u

# OpenAI API Key
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# MongoDB connection
if os.environ.get('TUNNEL_MODE') == 'true':
    print("STARTUP_CHECK: TUNNEL_MODE ENABLED - Using MongoDB Data API")
    api_url = os.environ.get('MONGO_DATA_API_URL')
    api_key = os.environ.get('MONGO_DATA_API_KEY')
    cluster = os.environ.get('MONGO_CLUSTER_NAME', 'Cluster0')
    db_name = os.environ.get('DB_NAME', 'whatsapp_crm')
    
    if not api_url or not api_key:
        print("[CRITICAL] TUNNEL_MODE=true but MONGO_DATA_API_URL or MONGO_DATA_API_KEY is missing")
        sys.exit(1)
        
    client = AsyncMongoHTTPClient(api_url, api_key, cluster, db_name)
    db = client[db_name]
else:
    mongo_url = os.environ['MONGO_URL']
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', 'whatsapp_crm')]

router = Router(db) # specific router for agents


async def _handle_flow_go_back(
    target_step: Optional[str],
    pending_state: Dict[str, Any],
    customer_id: str,
    user_id: str,
    from_number: str,
    customer_name: str,
    default_step: str = "booking_service_select"
) -> Dict[str, Any]:
    """
    Handle go_back action with dynamic target_step routing.
    FlowJudge tells us what the customer wants to change, we route accordingly.
    """
    ws = get_whatsapp_service(db)
    
    # Map FlowJudge target_step to action_context
    step_map = {
        "service_selection": "booking_service_select",
        "date": "booking_date_input",
        "time": "booking_time_select",
        "addon": "booking_addon_select",
        "confirm": "booking_confirm",
    }
    
    action_context = step_map.get(target_step, default_step) if target_step else default_step
    
    # Resend appropriate prompt based on target step
    if action_context == "booking_service_select":
        # Fetch and resend service list
        _svcs = await db.products.find({
            "user_id": user_id, "in_stock": True,
            "offering_type": {"$in": ["service","class","appointment","consultation","rental","equipment","package"]}
        }).to_list(20)
        if not _svcs:
            _svcs = await db.products.find({"user_id": user_id, "in_stock": True}).to_list(20)
        
        if _svcs:
            user_doc = await db.users.find_one({"_id": user_id})
            _cur = (user_doc or {}).get("currency", "")
            _lines = ["📋 *Our Services*\n"]
            for _i, _s in enumerate(_svcs[:8], 1):
                _price = _s.get("price", 0)
                _dur = _s.get("duration")
                _ps = f"{_cur} {_price:,.0f}" if _price else "Contact for price"
                _ds = f" · {_dur} min" if _dur else ""
                _lines.append(f"{_i}️⃣  *{_s['name']}* — {_ps}{_ds}")
            _lines.append("\n_Reply with the number of the service you'd like to book_")
            
            await db.pending_catalogs.update_one(
                {"customer_id": customer_id, "user_id": user_id},
                {"$set": {
                    "action_context": action_context,
                    "products": [{"id": str(_s["_id"]), "name": _s["name"], "price": _s.get("price", 0),
                                  "duration": _s.get("duration"), "index": _i,
                                  "service_category": _s.get("service_category", "appointment")}
                                 for _i, _s in enumerate(_svcs[:8], 1)],
                    "updated_at": datetime.utcnow(),
                }},
                upsert=True
            )
            await ws.send_message(
                user_id=user_id, to_number=from_number,
                message="No problem! Here are the services again 😊\n\n" + "\n".join(_lines),
                customer_name=customer_name, send_context="booking_flow"
            )
        else:
            await ws.send_message(
                user_id=user_id, to_number=from_number,
                message="No problem! What service would you like to book? 😊",
                customer_name=customer_name, send_context="booking_flow"
            )
    
    elif action_context == "booking_date_input":
        svc_name = pending_state.get("booking_service_name", "your service")
        await db.pending_catalogs.update_one(
            {"customer_id": customer_id, "user_id": user_id},
            {"$set": {"action_context": action_context, "booking_date": None, "updated_at": datetime.utcnow()}}
        )
        await ws.send_message(
            user_id=user_id, to_number=from_number,
            message=f"No problem! What date would you like for *{svc_name}*? 📅\n_e.g. tomorrow, Monday, 15 March_",
            customer_name=customer_name, send_context="booking_flow"
        )
    
    elif action_context == "booking_time_select":
        svc_name = pending_state.get("booking_service_name", "your service")
        bk_date = pending_state.get("booking_date", "")
        await db.pending_catalogs.update_one(
            {"customer_id": customer_id, "user_id": user_id},
            {"$set": {"action_context": action_context, "booking_time": None, "updated_at": datetime.utcnow()}}
        )
        await ws.send_message(
            user_id=user_id, to_number=from_number,
            message=f"No problem! What time would you like for *{svc_name}* on {bk_date}? ⏰",
            customer_name=customer_name, send_context="booking_flow"
        )
    
    else:
        # Generic fallback
        await db.pending_catalogs.update_one(
            {"customer_id": customer_id, "user_id": user_id},
            {"$set": {"action_context": action_context, "updated_at": datetime.utcnow()}}
        )
        await ws.send_message(
            user_id=user_id, to_number=from_number,
            message="No problem! Let's adjust that 😊",
            customer_name=customer_name, send_context="booking_flow"
        )
    
    return {"status": "ok", "handled_by": f"go_back_to_{action_context}"}


# WhatsApp via Evolution API (config in .env: EVOLUTION_API_URL, EVOLUTION_API_KEY)

# JWT Config — enforce strong secret
_jwt_secret_raw = os.environ.get('JWT_SECRET', '')
if not _jwt_secret_raw or _jwt_secret_raw == 'default-secret-key':
    import secrets as _secrets
    _jwt_secret_raw = _secrets.token_urlsafe(64)
    print("\n" + "="*60)
    print("[WARNING] JWT_SECRET not set in .env -- auto-generated for this session.")
    print("   Add a strong JWT_SECRET to .env for persistence across restarts.")
    print("="*60 + "\n")
JWT_SECRET = _jwt_secret_raw
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

# Google Play / App Store IAP Config
GOOGLE_PLAY_PACKAGE_NAME = os.environ.get('GOOGLE_PLAY_PACKAGE_NAME', '')

app = FastAPI(title="WhatsApp CRM")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

# Configure CORS — use ALLOWED_ORIGINS env var in production (comma-separated)
_allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*')
_origins_list = [o.strip() for o in _allowed_origins.split(',')] if _allowed_origins != '*' else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_credentials=_allowed_origins != '*',
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def fix_team_members_index():
    try:
        await db.team_members.drop_index("business_id_1_email_1")
        logging.info("Dropped bad team_members index: business_id_1_email_1")
    except Exception:
        pass
    try:
        await db.team_members.create_index(
            [("business_id", 1), ("phone_number", 1)], unique=True, name="business_id_1_phone_1"
        )
        logging.info("Ensured team_members index: business_id_1_phone_1")
    except Exception:
        pass
    # Migrate existing records: auto_created=True → is_customer=False (contacts pool)
    # Records without auto_created (manually added) → is_customer=True
    try:
        r1 = await db.customers.update_many(
            {"auto_created": True, "is_customer": {"$exists": False}},
            {"$set": {"is_customer": False}}
        )
        r2 = await db.customers.update_many(
            {"auto_created": {"$ne": True}, "is_customer": {"$exists": False}},
            {"$set": {"is_customer": True}}
        )
        logging.info(f"[Migration] is_customer backfill: {r1.modified_count} contacts, {r2.modified_count} customers")
    except Exception as e:
        logging.warning(f"[Migration] is_customer backfill failed: {e}")

    # Migration: remove auto_reply=False from all records so they respect global settings
    # (was incorrectly set to False in a previous migration - unset it so global toggle works)
    try:
        r3 = await db.customers.update_many(
            {"auto_reply": False},
            {"$unset": {"auto_reply": ""}}
        )
        logging.info(f"[Migration] Cleared auto_reply override from {r3.modified_count} records")
    except Exception as e:
        logging.warning(f"[Migration] auto_reply clear failed: {e}")

    # Phase 1d migration: set business_type=retail on existing users that don't have it
    try:
        r4 = await db.users.update_many(
            {"settings.business_type": {"$exists": False}},
            {"$set": {"settings.business_type": "retail"}}
        )
        logging.info(f"[Migration] Set business_type=retail on {r4.modified_count} users")
    except Exception as e:
        logging.warning(f"[Migration] business_type backfill failed: {e}")

    # Phase 1d migration: set offering_type=product on existing products that don't have it
    try:
        r5 = await db.products.update_many(
            {"offering_type": {"$exists": False}},
            {"$set": {"offering_type": "product"}}
        )
        logging.info(f"[Migration] Set offering_type=product on {r5.modified_count} products")
    except Exception as e:
        logging.warning(f"[Migration] offering_type backfill failed: {e}")

    # Phase 1e migration: fix services wrongly tagged as offering_type=product by the previous migration.
    # Products with duration set are bookable services, not physical retail products.
    try:
        r5b = await db.products.update_many(
            {"offering_type": "product", "duration": {"$exists": True, "$ne": None}},
            {"$set": {"offering_type": "service"}}
        )
        logging.info(f"[Migration] Fixed {r5b.modified_count} services wrongly tagged as offering_type=product → service")
    except Exception as e:
        logging.warning(f"[Migration] offering_type service fix failed: {e}")

    # Phase 1f migration: fix products with service_category set — they are bookable services
    try:
        r5c = await db.products.update_many(
            {"offering_type": "product", "service_category": {"$exists": True, "$not": {"$in": [None, ""]}}},
            {"$set": {"offering_type": "service"}}
        )
        logging.info(f"[Migration] Fixed {r5c.modified_count} products with service_category → offering_type=service")
    except Exception as e:
        logging.warning(f"[Migration] service_category fix failed: {e}")

    # Startup: purge invalid contacts for all existing users (one-time cleanup + permanent gate)
    try:
        asyncio.create_task(_startup_purge_invalid_contacts())
    except Exception as e:
        logging.warning(f"[StartupPurge] Failed to start purge task: {e}")

    # Start keep-alive pinger to prevent Render free-tier sleep
    asyncio.create_task(run_keep_alive_scheduler())

    # Start automation scheduler in background
    asyncio.create_task(run_automation_scheduler())

async def _purge_invalid_contacts_for_user(user_id: str) -> int:
    """
    Remove auto-created contacts whose phone numbers are invalid:
    - More than 15 digits (garbage from @lid JIDs)
    - Fewer than 7 digits (not a real phone number)
    - Matches the user's own phone number (self-contact)
    Returns number of records deleted.
    """
    user = await db.users.find_one({"_id": user_id}, {"phone_number": 1})
    own_digits = (user.get("phone_number") or "").lstrip("+").replace(" ", "").replace("-", "") if user else ""
    deleted = 0
    candidates = await db.customers.find(
        {"user_id": user_id, "auto_created": True, "is_customer": {"$ne": True}},
        {"_id": 1, "phone_number": 1}
    ).to_list(None)
    for c in candidates:
        phone = c.get("phone_number", "")
        digits = phone.lstrip("+").replace(" ", "").replace("-", "")
        is_too_long = len(digits) > 15
        is_too_short = len(digits) < 7
        is_own = own_digits and digits == own_digits
        if is_too_long or is_too_short or is_own:
            await db.customers.delete_one({"_id": c["_id"]})
            await db.messages.delete_many({"customer_id": c["_id"]})
            deleted += 1
    if deleted:
        logging.info(f"[ContactPurge] Removed {deleted} invalid contacts for user {user_id}")
    return deleted


async def _startup_purge_invalid_contacts():
    """Run once at startup: purge invalid contacts for every user in the DB."""
    await asyncio.sleep(5)  # let server fully start
    try:
        users = await db.users.find({}, {"_id": 1}).to_list(None)
        total = 0
        for u in users:
            try:
                total += await _purge_invalid_contacts_for_user(u["_id"])
            except Exception as e:
                logging.warning(f"[StartupPurge] Failed for user {u['_id']}: {e}")
        logging.info(f"[StartupPurge] Total invalid contacts removed across all users: {total}")
    except Exception as e:
        logging.error(f"[StartupPurge] Failed: {e}")


async def run_keep_alive_scheduler():
    """Ping Evolution API and self every 14 min to prevent Render free-tier sleep."""
    await asyncio.sleep(30)  # wait for server to fully start
    evolution_url = os.environ.get('EVOLUTION_API_URL', '').rstrip('/')
    self_url = os.environ.get('RENDER_EXTERNAL_URL', '').rstrip('/')
    while True:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                if evolution_url:
                    try:
                        r = await client.get(f"{evolution_url}/")
                        logging.info(f"[KeepAlive] Evolution API ping: {r.status_code}")
                    except Exception as e:
                        logging.warning(f"[KeepAlive] Evolution API ping failed: {e}")
                if self_url:
                    try:
                        r = await client.get(f"{self_url}/api/health")
                        logging.info(f"[KeepAlive] Self ping: {r.status_code}")
                    except Exception as e:
                        logging.warning(f"[KeepAlive] Self ping failed: {e}")
        except Exception as e:
            logging.warning(f"[KeepAlive] Scheduler error: {e}")
        await asyncio.sleep(840)  # 14 minutes

async def run_automation_scheduler():
    """Runs every hour — executes due broadcast automations (auto follow-up & recurring)"""
    import asyncio
    await asyncio.sleep(10)  # brief delay to let server finish starting
    while True:
        try:
            await execute_broadcast_automations()
        except Exception as e:
            logging.error(f"Automation scheduler error: {e}")
        await asyncio.sleep(3600)  # check every hour

async def run_booking_reminder_scheduler():
    """Runs every 30 minutes — sends WhatsApp reminders for upcoming bookings (24h and 1h before)"""
    import asyncio
    await asyncio.sleep(60)  # brief delay on startup
    while True:
        try:
            await send_booking_reminders()
        except Exception as e:
            logging.error(f"Booking reminder scheduler error: {e}")
        await asyncio.sleep(1800)  # every 30 minutes

async def send_booking_reminders():
    """Find upcoming bookings and send WhatsApp reminders at 24h and 1h windows."""
    from whatsapp_service import get_whatsapp_service
    now = datetime.utcnow()

    upcoming = await db.bookings.find({
        "status": {"$in": ["pending", "confirmed"]},
        "$or": [
            {"reminder_sent_24h": {"$ne": True}},
            {"reminder_sent_1h": {"$ne": True}},
        ]
    }).to_list(None)

    ws = get_whatsapp_service(db)

    for booking in upcoming:
        try:
            date_str = booking.get("date", "")
            time_str = booking.get("time", "")
            if not date_str or not time_str:
                continue
            
            # Skip rental bookings - they use "check-in" instead of time format
            service_category = booking.get("service_category", "")
            if service_category == "rental" or time_str in ("check-in", "check-out"):
                continue

            booking_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            diff_hours = (booking_dt - now).total_seconds() / 3600

            user_id         = booking.get("user_id")
            customer_phone  = booking.get("customer_phone")
            customer_name   = booking.get("customer_name", "there")
            service_name    = booking.get("service_name", "appointment")
            booking_number  = booking.get("booking_number", "")

            if not user_id or not customer_phone:
                continue

            # 24h reminder window: 23–25 hours before
            if not booking.get("reminder_sent_24h") and 23 <= diff_hours <= 25:
                msg = (
                    f"Hi {customer_name}! \U0001f44b Just a reminder that your *{service_name}* "
                    f"is scheduled for *tomorrow at {time_str}* \U0001f4c5\n\n"
                    f"Ref: *{booking_number}*\n"
                    f"_Reply to reschedule or cancel_"
                )
                await ws.send_message(
                    user_id=user_id, to_number=customer_phone,
                    message=msg, customer_name=customer_name, send_context="booking_reminder"
                )
                await db.bookings.update_one(
                    {"_id": booking["_id"]},
                    {"$set": {"reminder_sent_24h": True, "reminder_sent_24h_at": now}}
                )
                logging.info(f"[BookingReminder] 24h reminder sent for booking {booking['_id']}")

            # 1h reminder window: 45–90 minutes before
            if not booking.get("reminder_sent_1h") and 0.75 <= diff_hours <= 1.5:
                msg = (
                    f"Hi {customer_name}! \u23f0 Your *{service_name}* starts in *1 hour* "
                    f"at *{time_str}* today \U0001f4c5\n\n"
                    f"Ref: *{booking_number}*\n"
                    f"See you soon! \U0001f60a"
                )
                await ws.send_message(
                    user_id=user_id, to_number=customer_phone,
                    message=msg, customer_name=customer_name, send_context="booking_reminder"
                )
                await db.bookings.update_one(
                    {"_id": booking["_id"]},
                    {"$set": {"reminder_sent_1h": True, "reminder_sent_1h_at": now}}
                )
                logging.info(f"[BookingReminder] 1h reminder sent for booking {booking['_id']}")

        except Exception as e:
            logging.error(f"[BookingReminder] Error on booking {booking.get('_id')}: {e}")

async def execute_broadcast_automations():
    """Find and execute all due broadcast automations"""
    from whatsapp_service import get_whatsapp_service
    now = datetime.utcnow()
    whatsapp_service = get_whatsapp_service(db)

    automations = await db.broadcast_automations.find({"status": "active"}).to_list(None)

    for automation in automations:
        try:
            user_id = automation["user_id"]
            a_type = automation.get("type")

            if a_type == "auto_followup":
                broadcast_id = automation.get("broadcast_id")
                delay_days = automation.get("delay_days", 3)
                followup_msg = automation.get("followup_message", "")
                if not broadcast_id or not followup_msg:
                    continue

                broadcast = await db.broadcasts.find_one({"_id": broadcast_id})
                if not broadcast:
                    continue

                # Only run once, after the delay has passed since broadcast
                sent_at = broadcast.get("created_at")
                if not sent_at or (now - sent_at).days < delay_days:
                    continue

                # Skip if already executed
                if automation.get("last_run"):
                    continue

                # Find customers who received broadcast but haven't replied since
                customer_ids = broadcast.get("customer_ids")
                query = {"user_id": user_id}
                if customer_ids:
                    query["_id"] = {"$in": customer_ids}
                elif broadcast.get("filter_type") == "returning":
                    query["tags"] = "Returning"
                elif broadcast.get("filter_type") == "vip":
                    query["tags"] = "VIP"
                elif broadcast.get("filter_type") == "new":
                    query["tags"] = "New"

                customers = await db.customers.find(query).to_list(None)

                # Filter to only customers who have NOT replied since broadcast
                no_reply_customers = []
                for c in customers:
                    replied = await db.messages.find_one({
                        "customer_id": c["_id"],
                        "user_id": user_id,
                        "direction": "incoming",
                        "created_at": {"$gte": sent_at}
                    })
                    if not replied:
                        no_reply_customers.append(c)

                # Send follow-up to non-responders
                sent = 0
                for c in no_reply_customers:
                    try:
                        msg = followup_msg.replace("{{name}}", c.get("name", "there"))
                        await whatsapp_service.send_message(
                            user_id=user_id,
                            to_number=c["phone_number"],
                            message=msg,
                            customer_name=c.get("name"),
                            send_context="broadcast",
                        )
                        sent += 1
                    except Exception as e:
                        logging.error(f"Auto follow-up send error: {e}")

                # Mark automation as run
                await db.broadcast_automations.update_one(
                    {"_id": automation["_id"]},
                    {"$set": {"last_run": now, "last_run_sent": sent, "status": "completed"}}
                )
                logging.info(f"Auto follow-up executed: {sent} messages sent for broadcast {broadcast_id}")

            elif a_type == "recurring":
                recurrence = automation.get("recurrence", "weekly")
                last_run = automation.get("last_run")
                send_hour = automation.get("send_hour", 9)

                # Check if it's time to run
                if now.hour != send_hour:
                    continue

                if last_run:
                    days_since = (now - last_run).days
                    if recurrence == "weekly" and days_since < 7:
                        continue
                    if recurrence == "monthly" and days_since < 28:
                        continue

                message = automation.get("message", "")
                image_urls = automation.get("image_urls", [])
                filter_type = automation.get("filter_type", "all")
                if not message:
                    continue

                query = {"user_id": user_id}
                if filter_type == "returning":
                    query["tags"] = "Returning"
                elif filter_type == "vip":
                    query["tags"] = "VIP"
                elif filter_type == "new":
                    query["tags"] = "New"

                customers = await db.customers.find(query).to_list(None)
                if not customers:
                    continue

                # Create broadcast record
                new_id = str(uuid.uuid4())
                await db.broadcasts.insert_one({
                    "_id": new_id,
                    "user_id": user_id,
                    "message": message,
                    "name": f"Recurring ({recurrence})",
                    "filter_type": filter_type,
                    "recipients_count": len(customers),
                    "sent_count": 0,
                    "status": "pending",
                    "image_urls": image_urls,
                    "image_url": image_urls[0] if image_urls else None,
                    "scheduled_at": None,
                    "created_at": now,
                })
                await send_broadcast_messages(new_id, user_id, message, customers, image_urls)

                await db.broadcast_automations.update_one(
                    {"_id": automation["_id"]},
                    {"$set": {"last_run": now}, "$inc": {"runs": 1}}
                )
                logging.info(f"Recurring broadcast executed: {len(customers)} recipients")

        except Exception as e:
            logging.error(f"Error executing automation {automation.get('_id')}: {e}")

@app.get("/health")
async def health_check():
    try:
        with open("trace.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.utcnow().isoformat()} - Health check called\n")
    except:
        pass
    # Include AI status so you can always verify AI is working
    try:
        drafter = get_drafter()
        ai_status = drafter.get_status()
    except:
        ai_status = {"ready": False, "error": "drafter not initialized"}
    return {"status": "ok", "service": "crm-backend", "trace": "active", "ai": ai_status}

# ============ HELPER FUNCTIONS ============

def create_token(user_id: str, phone_number: str) -> str:
    payload = {
        "user_id": user_id,
        "phone_number": phone_number,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    payload = verify_token(credentials.credentials)
    user = await db.users.find_one({"_id": payload["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def generate_simple_reason(customer: dict, days_since_contact: int) -> str:
    """Generate a simple follow-up reason without AI calls for performance"""
    tags = customer.get("tags", [])
    last_message = customer.get("last_message", "")
    created_at = customer.get("created_at")
    
    # Calculate days since customer was added
    days_since_added = None
    if created_at:
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        days_since_added = (datetime.utcnow() - created_at).days
    
    # Quick rule-based reasons
    if not customer.get("last_contacted"):
        # Recently added contact (within 7 days) - reminder to reach out
        if days_since_added is not None and days_since_added <= 7:
            if days_since_added == 0:
                return "Added today - reach out and introduce yourself"
            elif days_since_added == 1:
                return "Added yesterday - time to make first contact"
            else:
                return f"Added {days_since_added} days ago - haven't contacted yet"
        
        # Older contacts
        if "New" in tags:
            return "New customer - send welcome message"
        return "Never contacted - introduce your services"
    
    if days_since_contact and days_since_contact > 30:
        return f"Inactive for {days_since_contact} days - re-engage with offer"
    
    if "VIP" in tags and days_since_contact and days_since_contact > 7:
        return f"VIP customer not contacted in {days_since_contact} days"
    
    # Check last message for context
    if last_message:
        lower_msg = last_message.lower()
        if any(word in lower_msg for word in ["price", "cost", "how much", "pric", "bei"]):
            return "Asked about pricing - follow up on quote"
        if any(word in lower_msg for word in ["think", "consider", "later", "tomorrow"]):
            return "Was considering purchase - check decision"
        if any(word in lower_msg for word in ["thank", "thanks", "asante"]):
            return "Previous transaction - check satisfaction"
    
    # Default with days
    if days_since_contact:
        return f"No contact in {days_since_contact} days - check in"
    
    return "Due for follow-up"

async def generate_quick_reason(customer: dict, messages: list) -> str:
    """Generate a quick follow-up reason without full AI call for performance"""
    last_message = customer.get("last_message", "")
    tags = customer.get("tags", [])
    days_since = None
    
    if customer.get("last_contacted"):
        days_since = (datetime.utcnow() - customer["last_contacted"]).days
    
    # Quick rule-based reasons first
    if not customer.get("last_contacted"):
        if "New" in tags:
            return "New customer - send welcome message"
        return "Never contacted - introduce your services"
    
    if days_since and days_since > 30:
        return f"Inactive for {days_since} days - re-engage with offer"
    
    if "VIP" in tags and days_since and days_since > 7:
        return f"VIP customer not contacted in {days_since} days"
    
    # Check last message for context
    if last_message:
        lower_msg = last_message.lower()
        if any(word in lower_msg for word in ["price", "cost", "how much", "pric", "bei"]):
            return "Asked about pricing - follow up on quote"
        if any(word in lower_msg for word in ["think", "consider", "later", "tomorrow"]):
            return "Was considering purchase - check decision"
        if any(word in lower_msg for word in ["thank", "thanks", "asante"]):
            return "Previous transaction - check satisfaction"
    
    # Default with days
    if days_since:
        return f"No contact in {days_since} days - check in"
    
    return "Due for follow-up"

# ============ PYDANTIC MODELS ============

# Auth Models
class OTPRequest(BaseModel):
    phone_number: str  # E.164 format: +<country_code><number>

class OTPVerify(BaseModel):
    phone_number: str
    code: str

class WhatsAppAuthStart(BaseModel):
    phone_number: str  # E.164 format: +<country_code><number>
    country_code: Optional[str] = None  # ISO 3166-1 alpha-2 e.g. 'KE'

class WhatsAppAuthCheck(BaseModel):
    session_token: str

class UserCreate(BaseModel):
    phone_number: str
    business_name: str
    owner_name: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    phone_number: str
    business_name: str
    owner_name: Optional[str] = None
    subscription_plan: Optional[str] = None
    subscription_active: bool = False
    country_code: Optional[str] = None
    currency: Optional[str] = None
    payment_methods: List[str] = []
    created_at: datetime

# Team/Business Models
class TeamMemberRole:
    OWNER = "owner"
    MANAGER = "manager"
    EMPLOYEE = "employee"

class TeamMemberInvite(BaseModel):
    phone_number: str  # Primary identifier — employee logs in with this
    name: str
    role: str = "employee"  # owner, manager, employee
    email: Optional[str] = None  # Optional, for reference only

class TeamMemberResponse(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    role: str
    business_id: str
    status: str  # active, invited, suspended
    invited_by: str
    created_at: datetime
    last_active: Optional[datetime] = None

class TeamMemberUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None

class ConversationAssignment(BaseModel):
    customer_id: str
    assigned_to: Optional[str] = None  # team member user_id
    assigned_by: str
    notes: Optional[str] = None

class ActivityLog(BaseModel):
    user_id: str
    user_name: str
    action: str  # "message_sent", "customer_created", "order_created", "conversation_assigned"
    entity_type: str  # "customer", "message", "order", "conversation"
    entity_id: str
    details: Optional[dict] = None
    timestamp: datetime

# Customer Models
class CustomerCreate(BaseModel):
    name: str
    phone_number: str
    notes: Optional[str] = None
    tags: List[str] = []
    is_personal: bool = False

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    auto_reply: Optional[bool] = None
    is_personal: Optional[bool] = None
    ai_enabled: Optional[bool] = None
    stage: Optional[str] = None

class CustomerResponse(BaseModel):
    id: str
    user_id: str
    name: str
    phone_number: str
    notes: Optional[str] = None
    tags: List[str] = []
    auto_reply: Optional[bool] = None
    is_personal: bool = False
    ai_enabled: bool = True
    contact_type: str = "UNKNOWN"
    is_customer: bool = False
    stage: str = "lead"
    purchase_count: int = 0
    total_spent: float = 0.0
    last_message: Optional[str] = None
    last_contacted: Optional[datetime] = None
    profile_picture: Optional[str] = None
    unread_count: int = 0
    created_at: datetime
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None

# Follow-up Models
class FollowUpCreate(BaseModel):
    customer_id: str
    reminder_date: datetime
    message: Optional[str] = None
    type: str = "call"  # call, whatsapp, meeting, email

class FollowUpUpdate(BaseModel):
    reminder_date: Optional[datetime] = None
    message: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    outcome: Optional[str] = None  # called, replied, no_answer, converted, rescheduled
    outcome_note: Optional[str] = None

class FollowUpResponse(BaseModel):
    id: str
    user_id: str
    customer_id: str
    customer_name: str
    customer_phone: Optional[str] = None
    reminder_date: datetime
    message: Optional[str] = None
    status: str
    type: str
    outcome: Optional[str] = None
    outcome_note: Optional[str] = None
    created_at: datetime

# Sales/Receipt Models
class SaleCreate(BaseModel):
    customer_id: str
    item: str
    amount: float
    payment_method: Optional[str] = None  # Optional for credit sales
    send_receipt: bool = True
    receipt_message: Optional[str] = None
    is_credit: bool = False  # Whether this is a credit sale
    due_date: Optional[str] = None  # When payment is due (ISO format)
    paid_date: Optional[str] = None  # When credit was paid (ISO format)

class SaleResponse(BaseModel):
    id: str
    user_id: str
    customer_id: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    item: str
    amount: float
    payment_method: Optional[str] = None
    receipt_sent: bool = False
    is_credit: bool = False
    due_date: Optional[str] = None
    paid_date: Optional[str] = None
    created_at: datetime
    source: str = "sale"  # "sale" | "booking"

# Order Models
class OrderCreate(BaseModel):
    customer_id: str
    product: str
    quantity: int = 1
    price: float
    total_amount: float
    payment_status: str = "Pending"  # Pending, Partial, Paid
    delivery_status: str = "Processing"  # Processing, Shipped, Delivered
    notes: Optional[str] = None
    due_date: Optional[str] = None

class OrderResponse(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    customer_phone: str
    product: str
    quantity: int
    price: float
    total_amount: float
    payment_status: str
    delivery_status: str
    status: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[str] = None
    created_at: str

# Expense Models
class ExpenseCreate(BaseModel):
    category: str  # Inventory, Rent, Transport, Utilities, Salaries, Other
    amount: float
    description: Optional[str] = None
    date: Optional[datetime] = None

class ExpenseResponse(BaseModel):
    id: str
    user_id: str
    category: str
    amount: float
    description: Optional[str] = None
    created_at: datetime

# Broadcast Template Models
class BroadcastTemplateCreate(BaseModel):
    name: str
    message: str
    image_url: Optional[str] = None

class BroadcastTemplateResponse(BaseModel):
    id: str
    user_id: str
    name: str
    message: str
    image_url: Optional[str] = None
    created_at: datetime

# Broadcast Models
class BroadcastCreate(BaseModel):
    message: str
    name: Optional[str] = None
    filter_type: str = "all"  # all, returning, vip, new
    customer_ids: Optional[List[str]] = None
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None
    scheduled_at: Optional[datetime] = None
    template_id: Optional[str] = None

class BroadcastResponse(BaseModel):
    id: str
    user_id: str
    message: str
    name: Optional[str] = None
    filter_type: str
    recipients_count: int
    sent_count: int = 0
    status: str = "pending"
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None
    scheduled_at: Optional[datetime] = None
    created_at: datetime

# ============ AI MESSAGE GENERATION ============

# ... (skipping AI lines)

# ============ BROADCAST ENDPOINTS ============

@api_router.post("/broadcasts", response_model=BroadcastResponse)
async def create_broadcast(broadcast: BroadcastCreate, background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    """Create and send a broadcast message"""
    business_id = user.get("business_id", user["_id"])
    # Get recipients based on filter
    query = {"user_id": business_id}

    if broadcast.filter_type == "returning":
        query["tags"] = "Returning"
    elif broadcast.filter_type == "vip":
        query["tags"] = "VIP"
    elif broadcast.filter_type == "new":
        query["tags"] = "New"
    elif broadcast.filter_type in ("custom", "group") or broadcast.customer_ids:
        # Custom group / specific IDs — must have IDs, otherwise refuse
        if not broadcast.customer_ids:
            raise HTTPException(status_code=400, detail="customer_ids required for custom/group broadcast")
        query["_id"] = {"$in": broadcast.customer_ids}
    # else filter_type == "all" — no extra filter, send to everyone

    customers = await db.customers.find(query).to_list(200)   # Hard cap: 200 max per broadcast for WhatsApp safety
    
    # Handle images: Normalize to image_urls list
    image_urls = broadcast.image_urls or []
    if not image_urls and broadcast.image_url:
        image_urls = [broadcast.image_url]
    
    # Sync single image_url for storage/backwards compat
    primary_image_url = image_urls[0] if image_urls else None

    broadcast_id = str(uuid.uuid4())
    broadcast_doc = {
        "_id": broadcast_id,
        "user_id": business_id,
        "message": broadcast.message,
        "name": broadcast.name or None,
        "filter_type": broadcast.filter_type,
        "customer_ids": broadcast.customer_ids or None,
        "recipients_count": len(customers),
        "sent_count": 0,
        "status": "scheduled" if broadcast.scheduled_at else "pending",
        "image_url": primary_image_url,
        "image_urls": image_urls,
        "scheduled_at": broadcast.scheduled_at,
        "created_at": datetime.utcnow()
    }
    
    await db.broadcasts.insert_one(broadcast_doc)
    
    # Send messages in background (only if not scheduled)
    if not broadcast.scheduled_at:
        background_tasks.add_task(
            send_broadcast_messages,
            broadcast_id,
            business_id,
            broadcast.message,
            customers,
            image_urls
        )
    
    return BroadcastResponse(
        id=broadcast_id,
        user_id=business_id,
        message=broadcast.message,
        name=broadcast.name or None,
        filter_type=broadcast.filter_type,
        recipients_count=len(customers),
        sent_count=0,
        status="scheduled" if broadcast.scheduled_at else "sending",
        image_url=primary_image_url,
        image_urls=image_urls,
        scheduled_at=broadcast.scheduled_at,
        created_at=broadcast_doc["created_at"]
    )

def _humanize_message(message: str, name: str) -> str:
    """
    Slightly vary the message text so each send is unique.
    WhatsApp detects identical bulk messages — variation avoids spam flags.
    """
    import random
    text = message.replace("{{name}}", name or "there")

    # Randomly swap common phrases for equivalents
    swaps = [
        ("Hi ", ["Hey ", "Hello ", "Hi there, ", "Hii "]),
        ("Hello ", ["Hey ", "Hi ", "Heya ", "Hello there, "]),
        ("Check out", ["Have a look at", "Take a look at", "See our"]),
        ("Available now", ["In stock now", "Available today", "Ready to order"]),
        ("Let me know", ["Feel free to ask", "Reach out", "Message us"]),
        ("Don't miss", ["Don't miss out on", "You don't want to miss", "Check out"]),
        ("!", ["!", "!", " 😊", " 🙌", ""]),  # Occasionally soften exclamations
    ]
    for original, alternatives in swaps:
        if original.lower() in text.lower():
            if random.random() < 0.4:  # 40% chance to swap
                replacement = random.choice(alternatives)
                # Case-preserving replace
                idx = text.lower().find(original.lower())
                if idx != -1:
                    text = text[:idx] + replacement + text[idx + len(original):]
                break

    return text


async def send_broadcast_messages(broadcast_id: str, user_id: str, message: str, customers: list, image_urls: List[str] = []):
    """
    Send broadcast to all recipients with human-like pacing.
    - 45s–3min delay between each message
    - 5–15 min break every 10 messages (batch pause)
    - Shuffled send order so it doesn't look sequential
    - Slight message variation per recipient to avoid spam detection
    """
    import random as _rnd
    from whatsapp_service import get_whatsapp_service, BROADCAST_DELAY, BROADCAST_BATCH_SIZE, BROADCAST_BATCH_BREAK
    whatsapp_service = get_whatsapp_service(db)

    # Normalize relative image URLs to absolute
    server_url = os.environ.get("SERVER_URL", "").rstrip("/")
    def _full_url(url: str) -> str:
        if not url:
            return url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{server_url}{url}" if server_url else url

    resolved_images = [_full_url(u) for u in image_urls if u]

    # Mark as sending immediately so cancel button appears in frontend
    await db.broadcasts.update_one(
        {"_id": broadcast_id},
        {"$set": {"status": "sending"}}
    )

    # Shuffle recipients so sends don't follow a predictable pattern
    shuffled = list(customers)
    _rnd.shuffle(shuffled)

    sent_count = 0
    for i, customer in enumerate(shuffled):
        # Check if broadcast was cancelled before each send
        bc_doc = await db.broadcasts.find_one({"_id": broadcast_id})
        if not bc_doc or bc_doc.get("status") in ("cancelled", "stopped"):
            logging.info(f"[Broadcast] {broadcast_id} cancelled — stopped at {sent_count} sent")
            return

        # --- BATCH BREAK: pause after every N messages ---
        if i > 0 and i % BROADCAST_BATCH_SIZE == 0:
            batch_break = _rnd.uniform(*BROADCAST_BATCH_BREAK)
            logging.info(f"[Broadcast] {broadcast_id} — batch break {batch_break/60:.1f} min after {sent_count} sent")
            await db.broadcasts.update_one(
                {"_id": broadcast_id},
                {"$set": {"sent_count": sent_count, "status": "sending", "paused_until": (datetime.utcnow()).isoformat()}}
            )
            await asyncio.sleep(batch_break)

            # Re-check cancellation after the long break
            bc_doc = await db.broadcasts.find_one({"_id": broadcast_id})
            if not bc_doc or bc_doc.get("status") in ("cancelled", "stopped"):
                logging.info(f"[Broadcast] {broadcast_id} cancelled during batch break")
                return

        try:
            # Humanize the message slightly per recipient
            personalized_message = _humanize_message(message, customer.get("name", "there"))

            if resolved_images:
                await whatsapp_service.send_message(
                    user_id=user_id,
                    to_number=customer["phone_number"],
                    message=personalized_message,
                    customer_name=customer.get("name"),
                    media_url=resolved_images[0],
                    send_context="broadcast",
                )
                for img_url in resolved_images[1:]:
                    await asyncio.sleep(_rnd.uniform(2, 5))  # Short gap between multi-images
                    await whatsapp_service.send_message(
                        user_id=user_id,
                        to_number=customer["phone_number"],
                        message="",
                        customer_name=customer.get("name"),
                        media_url=img_url,
                        send_context="broadcast",
                    )
            else:
                await whatsapp_service.send_message(
                    user_id=user_id,
                    to_number=customer["phone_number"],
                    message=personalized_message,
                    customer_name=customer.get("name"),
                    send_context="broadcast",
                )

            sent_count += 1
            logging.info(f"[Broadcast] {broadcast_id} — sent {sent_count}/{len(shuffled)} to {customer['phone_number']}")
            
            # Update sent_count in real-time so frontend shows progress
            await db.broadcasts.update_one(
                {"_id": broadcast_id},
                {"$set": {"sent_count": sent_count}}
            )

        except Exception as e:
            logging.error(f"[Broadcast] Failed to send to {customer['phone_number']}: {e}")

        # Human-like delay between messages (45s–3min)
        delay = _rnd.uniform(*BROADCAST_DELAY)
        logging.info(f"[Broadcast] Waiting {delay:.0f}s before next recipient")
        await asyncio.sleep(delay)

    # Mark complete
    await db.broadcasts.update_one(
        {"_id": broadcast_id},
        {"$set": {"sent_count": sent_count, "status": "completed"}}
    )

@api_router.get("/broadcasts", response_model=List[BroadcastResponse])
async def get_broadcasts(user = Depends(get_current_user)):
    """Get all broadcasts for current user"""
    business_id = user.get("business_id", user["_id"])
    broadcasts = await db.broadcasts.find({"user_id": business_id}).sort("created_at", -1).to_list(100)
    
    return [
        BroadcastResponse(
            id=b["_id"],
            user_id=b["user_id"],
            message=b["message"],
            name=b.get("name"),
            filter_type=b["filter_type"],
            recipients_count=b["recipients_count"],
            sent_count=b.get("sent_count", 0),
            status=b["status"],
            image_url=b.get("image_url"),
            image_urls=b.get("image_urls", [b.get("image_url")] if b.get("image_url") else []),
            scheduled_at=b.get("scheduled_at"),
            created_at=b["created_at"]
        )
        for b in broadcasts
    ]

@api_router.get("/broadcasts/automations")
async def get_broadcast_automations(user = Depends(get_current_user)):
    """Get all broadcast automations for user"""
    business_id = user.get("business_id", user["_id"])
    automations = await db.broadcast_automations.find({"user_id": business_id}).sort("created_at", -1).to_list(50)
    return [serialize_doc(a) for a in automations]

@api_router.delete("/broadcasts/automations/{automation_id}")
async def delete_broadcast_automation(automation_id: str, user = Depends(get_current_user)):
    """Delete a broadcast automation"""
    business_id = user.get("business_id", user["_id"])
    result = await db.broadcast_automations.delete_one({"_id": automation_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"status": "deleted"}

@api_router.post("/broadcasts/{broadcast_id}/cancel")
async def cancel_broadcast(broadcast_id: str, user = Depends(get_current_user)):
    """Cancel an in-progress broadcast immediately"""
    business_id = user.get("business_id", user["_id"])
    result = await db.broadcasts.update_one(
        {"_id": broadcast_id, "user_id": business_id},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    return {"status": "cancelled", "message": "Broadcast is being stopped"}

@api_router.delete("/broadcasts/{broadcast_id}")
async def delete_broadcast(broadcast_id: str, user = Depends(get_current_user)):
    """Delete a broadcast"""
    business_id = user.get("business_id", user["_id"])
    # Also mark as cancelled first to stop any in-progress sending
    await db.broadcasts.update_one(
        {"_id": broadcast_id, "user_id": business_id},
        {"$set": {"status": "cancelled"}}
    )
    result = await db.broadcasts.delete_one({"_id": broadcast_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    return {"status": "deleted"}

@api_router.post("/broadcasts/{broadcast_id}/resend")
async def resend_broadcast(broadcast_id: str, background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    """Resend an existing broadcast to the same audience"""
    business_id = user.get("business_id", user["_id"])
    original = await db.broadcasts.find_one({"_id": broadcast_id, "user_id": business_id})
    if not original:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    # Build recipients same way as original
    query = {"user_id": business_id}
    filter_type = original.get("filter_type", "all")
    if filter_type == "returning":
        query["tags"] = "Returning"
    elif filter_type == "vip":
        query["tags"] = "VIP"
    elif filter_type == "new":
        query["tags"] = "New"
    elif filter_type in ("custom", "group") or original.get("customer_ids"):
        stored_ids = original.get("customer_ids")
        if stored_ids:
            query["_id"] = {"$in": stored_ids}
        # else old broadcast with no saved ids — fall back to "all" for this business
    # else "all" — no extra filter
    customers = await db.customers.find(query).to_list(None)

    image_urls = original.get("image_urls") or ([original["image_url"]] if original.get("image_url") else [])
    new_id = str(uuid.uuid4())
    original_name = original.get("name")
    new_doc = {
        "_id": new_id,
        "user_id": business_id,
        "message": original["message"],
        "name": f"{original_name} (Resend)" if original_name else None,
        "filter_type": filter_type,
        "customer_ids": original.get("customer_ids") or None,
        "recipients_count": len(customers),
        "sent_count": 0,
        "status": "pending",
        "image_url": original.get("image_url"),
        "image_urls": image_urls,
        "scheduled_at": None,
        "created_at": datetime.utcnow()
    }
    await db.broadcasts.insert_one(new_doc)
    background_tasks.add_task(send_broadcast_messages, new_id, business_id, original["message"], customers, image_urls)
    return {"status": "resending", "broadcast_id": new_id, "recipients_count": len(customers)}

@api_router.get("/broadcasts/{broadcast_id}/performance")
async def get_broadcast_performance(broadcast_id: str, user = Depends(get_current_user)):
    """Get reply rate and performance stats for a broadcast"""
    business_id = user.get("business_id", user["_id"])
    broadcast = await db.broadcasts.find_one({"_id": broadcast_id, "user_id": business_id})
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    sent_at = broadcast.get("created_at", datetime.utcnow())
    window_end = sent_at + timedelta(days=3)

    # Count how many customers replied after the broadcast
    replies = await db.messages.count_documents({
        "user_id": business_id,
        "direction": "incoming",
        "created_at": {"$gte": sent_at, "$lte": window_end}
    })

    sent_count = broadcast.get("sent_count", 0)
    reply_rate = round((replies / sent_count * 100), 1) if sent_count > 0 else 0

    return {
        "broadcast_id": broadcast_id,
        "sent_count": sent_count,
        "recipients_count": broadcast.get("recipients_count", 0),
        "replies": replies,
        "reply_rate": reply_rate,
    }

class AutoFollowUpCreate(BaseModel):
    broadcast_id: str
    follow_up_message: str
    delay_days: int = 2

class RecurringBroadcastCreate(BaseModel):
    message: str
    filter_type: str = "all"
    image_urls: List[str] = []
    recurrence: str = "weekly"  # "weekly" or "monthly"
    send_hour: int = 9  # hour of day (0-23)

@api_router.post("/broadcasts/auto-followup")
async def create_auto_followup(data: AutoFollowUpCreate, user = Depends(get_current_user)):
    """Set up auto follow-up for customers who didn't reply to a broadcast"""
    business_id = user.get("business_id", user["_id"])
    broadcast = await db.broadcasts.find_one({"_id": data.broadcast_id, "user_id": business_id})
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    followup_id = str(uuid.uuid4())
    await db.broadcast_automations.insert_one({
        "_id": followup_id,
        "user_id": business_id,
        "type": "auto_followup",
        "broadcast_id": data.broadcast_id,
        "follow_up_message": data.follow_up_message,
        "delay_days": data.delay_days,
        "status": "active",
        "created_at": datetime.utcnow(),
        "runs": 0,
    })
    return {"status": "created", "automation_id": followup_id, "delay_days": data.delay_days}

@api_router.post("/broadcasts/recurring")
async def create_recurring_broadcast(data: RecurringBroadcastCreate, user = Depends(get_current_user)):
    """Set up a recurring broadcast (weekly or monthly)"""
    business_id = user.get("business_id", user["_id"])
    rec_id = str(uuid.uuid4())
    await db.broadcast_automations.insert_one({
        "_id": rec_id,
        "user_id": business_id,
        "type": "recurring",
        "message": data.message,
        "filter_type": data.filter_type,
        "image_urls": data.image_urls,
        "recurrence": data.recurrence,
        "send_hour": data.send_hour,
        "status": "active",
        "last_run": None,
        "created_at": datetime.utcnow(),
        "runs": 0,
    })
    return {"status": "created", "automation_id": rec_id, "recurrence": data.recurrence}

# AI Message Generation
class AIMessageRequest(BaseModel):
    prompt: str
    business_type: Optional[str] = None

# Subscription Models
class SubscriptionPlan(BaseModel):
    id: str
    name: str
    amount: int  # in cents
    amount_display: str
    interval: str
    features: List[str]

class IAPVerifyRequest(BaseModel):
    plan_id: str
    purchase_token: str  # Google Play purchase token or Apple receipt
    platform: str  # 'android' or 'ios'

# Message Models (for storing WhatsApp messages)
class MessageCreate(BaseModel):
    customer_id: str
    direction: str  # incoming, outgoing
    content: str
    message_type: str = "text"  # text, image, document

class MessageResponse(BaseModel):
    id: str
    customer_id: str
    direction: str
    content: str
    message_type: str
    created_at: datetime

# AI Analysis Models
class AIAnalysisRequest(BaseModel):
    customer_id: str

class AIAnalysisResponse(BaseModel):
    customer_id: str
    summary: str
    follow_up_reason: str
    suggested_message: str
    interests: List[str]
    sentiment: str

# AI Draft Message Models
class DraftMessageRequest(BaseModel):
    customer_id: str
    tone: Optional[str] = "friendly"  # professional, friendly, casual
    custom_instructions: Optional[str] = None
    regenerate_count: Optional[int] = 0  # increments each regenerate to force variety
    mode: Optional[str] = "auto"  # auto, business, personal

class DraftMessageResponse(BaseModel):
    message: str
    confidence: float
    reason: str

class SendAutoMessageRequest(BaseModel):
    customer_id: str
    message: str

# Payment method object
class PaymentMethodEntry(BaseModel):
    name: str  # e.g. 'M-Pesa', 'PayPal', 'Bank Transfer'
    details: Optional[str] = None  # e.g. phone number, email, account number

# User Settings Models
class UserSettingsUpdate(BaseModel):
    auto_reply_enabled: Optional[bool] = None
    notification_enabled: Optional[bool] = None
    notification_time: Optional[str] = None
    payment_methods: Optional[List[Any]] = None  # supports both legacy List[str] and List[{name,details}]
    currency: Optional[str] = None
    country_code: Optional[str] = None  # ISO 3166-1 alpha-2 e.g. 'US', 'KE', 'NG'
    daily_alert_count: Optional[int] = None
    message_tone: Optional[str] = None
    push_token: Optional[str] = None
    daily_pulse_enabled: Optional[bool] = None
    daily_pulse_time: Optional[str] = None  # e.g. '20:00'
    ai_model: Optional[str] = None  # standard, premium, claude-3.5, grok, etc.
    auto_reply_audience: Optional[str] = None  # 'everyone', 'customers_only', 'new_contacts_only'
    business_type: Optional[str] = None  # retail, salon, restaurant, services, fitness, healthcare, creator
    business_hours: Optional[Dict[str, Any]] = None  # {"mon": {"open": "09:00", "close": "18:00", "closed": false}, ...}
    booking_settings: Optional[Dict[str, Any]] = None  # duration_default, buffer_minutes, advance_days, etc.
    timezone: Optional[str] = None  # e.g. 'Africa/Nairobi', 'America/New_York'
    rental_availability: Optional[List[str]] = None  # list of blocked date strings YYYY-MM-DD

# Business Knowledge Model
class BusinessKnowledge(BaseModel):
    products_services: Optional[str] = None
    pricing_info: Optional[str] = None
    business_hours: Optional[str] = None
    delivery_info: Optional[str] = None
    faqs: Optional[str] = None
    special_offers: Optional[str] = None
    business_description: Optional[str] = None
    # Business type
    business_type: Optional[str] = None  # 'general', 'retail', 'creator', 'restaurant', 'service'
    # Creator-specific fields
    creator_niche: Optional[str] = None
    creator_platforms: Optional[str] = None
    creator_audience_size: Optional[str] = None
    creator_collab_types: Optional[str] = None
    creator_rate_card: Optional[str] = None
    creator_whats_included: Optional[str] = None
    creator_turnaround: Optional[str] = None
    creator_booking_process: Optional[str] = None
    creator_min_budget: Optional[str] = None
    creator_blacklisted_niches: Optional[str] = None
    creator_fan_dm_response: Optional[str] = None
    creator_media_kit_link: Optional[str] = None
    payment_methods: Optional[List[Any]] = None

# Product Catalog Models
class Product(BaseModel):
    id: str
    user_id: str
    name: str
    price: float
    image_url: str
    category: Optional[str] = "Other"
    description: Optional[str] = None
    in_stock: bool = True
    ai_suggested_name: Optional[str] = None
    ai_confidence: Optional[float] = None
    created_at: datetime
    updated_at: datetime

# ============ AUTH ENDPOINTS (WhatsApp-Only) ============

# WhatsApp auth sessions stored in MongoDB (survives restarts)
# Rate limiter: phone -> list of attempt timestamps
_wa_start_rate: dict = {}

@api_router.post("/auth/whatsapp-start")
async def whatsapp_auth_start(request: WhatsAppAuthStart):
    """
    Start WhatsApp-based authentication.
    1. Creates or finds user by phone number
    2. Starts WhatsApp pairing via Evolution API
    3. Returns session_token + pairing_code for the frontend
    """
    from country_utils import detect_country_from_phone, get_payment_methods_for_country

    phone = request.phone_number.strip()
    if not phone or len(phone) < 8:
        raise HTTPException(status_code=400, detail="Valid phone number is required")

    # Rate limit: max 5 attempts per phone per 10 minutes
    import time as _time
    _now = _time.time()
    _window = 600  # 10 minutes
    _attempts = _wa_start_rate.get(phone, [])
    _attempts = [t for t in _attempts if _now - t < _window]
    if len(_attempts) >= 5:
        raise HTTPException(status_code=429, detail="Too many login attempts. Please wait 10 minutes before trying again.")
    _attempts.append(_now)
    _wa_start_rate[phone] = _attempts

    # ── TEAM MEMBER FAST LOGIN ──────────────────────────────────────────────
    # If this phone number was pre-added as a team member, log them in directly.
    # No WhatsApp pairing needed — they use the business owner's WhatsApp instance.
    team_member = await db.team_members.find_one({
        "phone_number": phone,
        "status": {"$in": ["invited", "active"]}
    })
    if team_member:
        business_id = team_member["business_id"]
        # Find or create a user account for this employee
        emp_user = await db.users.find_one({"phone_number": phone})
        if not emp_user:
            emp_user_id = str(uuid.uuid4())
            emp_user = {
                "_id": emp_user_id,
                "phone_number": phone,
                "business_name": "",
                "owner_name": team_member["name"],
                "role": team_member["role"],
                "business_id": business_id,
                "subscription_active": True,  # Inherits from business
                "setup_complete": True,
                "created_at": datetime.utcnow(),
            }
            await db.users.insert_one(emp_user)
        else:
            emp_user_id = emp_user["_id"]
            # Ensure role and business_id are set
            await db.users.update_one(
                {"_id": emp_user_id},
                {"$set": {
                    "role": team_member["role"],
                    "business_id": business_id,
                    "setup_complete": True,
                }}
            )

        # Activate team member and link user_id
        await db.team_members.update_one(
            {"_id": team_member["_id"]},
            {"$set": {
                "status": "active",
                "user_id": emp_user_id,
                "last_active": datetime.utcnow(),
            }}
        )

        token = create_token(emp_user_id, phone)
        logging.info(f"Team member {phone} logged in directly (no pairing needed)")
        return {
            "status": "success",
            "connected": True,
            "token": token,
            "is_new_user": False,
            "is_team_member": True,
            "user": {
                "id": emp_user_id,
                "phone_number": phone,
                "business_name": "",
                "owner_name": team_member["name"],
                "role": team_member["role"],
                "business_id": business_id,
            },
            "message": "Logged in as team member.",
        }
    # ── END TEAM MEMBER FAST LOGIN ───────────────────────────────────────────

    # Check if user already exists
    user = await db.users.find_one({"phone_number": phone})
    is_new_user = user is None

    if is_new_user:
        # Create new user (business_name will be set in /auth/register after connect)
        country_code = request.country_code or detect_country_from_phone(phone)
        country_config = get_payment_methods_for_country(country_code)

        user_id = str(uuid.uuid4())
        user_doc = {
            "_id": user_id,
            "phone_number": phone,
            "business_name": "",
            "owner_name": "",
            "subscription_plan": None,
            "subscription_active": False,
            "country_code": country_code,
            "currency": country_config["currency"],
            "payment_methods": [{"name": m, "details": ""} for m in country_config["methods"][:3]],
            "created_at": datetime.utcnow(),
            "setup_complete": False,
        }
        await db.users.insert_one(user_doc)
        user = user_doc
    else:
        user_id = user["_id"]

        # If existing user already has WhatsApp connected, skip pairing — issue JWT directly
        whatsapp_service = get_whatsapp_service(db)
        try:
            status = await whatsapp_service.get_instance_status(user_id)
            if status.get("connected"):
                token = create_token(user_id, phone)
                setup_done = user.get("setup_complete", True)
                return serialize_doc({
                    "status": "success",
                    "connected": True,
                    "token": token,
                    "is_new_user": not setup_done,
                    "user": {
                        "id": user_id,
                        "phone_number": phone,
                        "business_name": user.get("business_name", ""),
                        "owner_name": user.get("owner_name", ""),
                    },
                    "message": "WhatsApp already connected. Logged in.",
                })
        except Exception as e:
            logging.warning(f"Error checking existing connection for {user_id}: {e}")

    # Start WhatsApp pairing (new user or existing user not connected)
    whatsapp_service = get_whatsapp_service(db)
    # Force a fresh instance if: explicitly flagged (401 logout) OR if WhatsApp status was
    # anything other than "connected" (handles Evolution API restart/sleep causing stuck instances)
    wa_status = (user.get("whatsapp") or {}).get("status", "") if user else ""
    explicit_force_new = (user.get("whatsapp") or {}).get("force_new", False) if user else False
    force_new = explicit_force_new or (not is_new_user and wa_status not in ("connected", "pairing", ""))
    logging.info(f"whatsapp-start: user={user_id}, wa_status={wa_status!r}, force_new={force_new}")
    result = await whatsapp_service.create_instance(user_id, phone, force_new=force_new)

    # Clear force_new flag after use
    if explicit_force_new:
        await db.users.update_one({"_id": user_id}, {"$unset": {"whatsapp.force_new": ""}})

    if result.get("status") == "error":
        err_msg = result.get("message", "Failed to start WhatsApp pairing")
        logging.error(f"whatsapp-start create_instance error for {phone}: {err_msg}")
        # If new user was just created and pairing failed, clean up
        if is_new_user:
            await db.users.delete_one({"_id": user_id})
        raise HTTPException(status_code=500, detail=err_msg)

    # Create a session token to track this auth attempt
    import secrets
    session_token = secrets.token_urlsafe(32)
    await db.wa_auth_sessions.insert_one({
        "_id": session_token,
        "user_id": user_id,
        "phone": phone,
        "is_new_user": is_new_user,
        "created_at": datetime.utcnow(),
        "expires": datetime.utcnow() + timedelta(minutes=5),
    })

    return {
        "status": "pairing",
        "session_token": session_token,
        "pairing_code": result.get("pairing_code", ""),
        "pairing_data": result.get("pairing_data", {}),
        "is_new_user": is_new_user,
        "message": "Enter this code in WhatsApp > Linked Devices > Link with phone number",
    }

@api_router.post("/auth/whatsapp-check")
async def whatsapp_auth_check(request: WhatsAppAuthCheck):
    """
    Poll WhatsApp connection status during auth.
    Once connected, issues a JWT token and returns user data.
    """
    session = await db.wa_auth_sessions.find_one({"_id": request.session_token})
    if not session:
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    if datetime.utcnow() > session["expires"]:
        await db.wa_auth_sessions.delete_one({"_id": request.session_token})
        raise HTTPException(status_code=400, detail="Session expired. Please start again.")

    user_id = session["user_id"]
    phone = session["phone"]

    # Check WhatsApp connection status
    whatsapp_service = get_whatsapp_service(db)
    status = await whatsapp_service.get_instance_status(user_id)

    if not status.get("connected"):
        return {"status": "waiting", "connected": False}

    # WhatsApp connected! Issue JWT
    token = create_token(user_id, phone)

    # Clean up session
    await db.wa_auth_sessions.delete_one({"_id": request.session_token})

    user = await db.users.find_one({"_id": user_id})
    is_new_user = session["is_new_user"] or not user.get("setup_complete", True)

    # Auto-trigger contact sync + profile pictures + classification in background
    async def _auto_sync(uid):
        try:
            ws = get_whatsapp_service(db)
            await ws.fetch_contacts(uid)
            await ws.fetch_chat_history(uid)
            await ws.fetch_profile_pictures_bulk(uid)
            logging.info(f"Auto-sync complete for user {uid}")
        except Exception as e:
            logging.error(f"Auto-sync error for user {uid}: {e}")
        try:
            classifier = get_classifier(db)
            await classifier.classify_all_contacts(uid)
            logging.info(f"Auto-classification complete for user {uid}")
        except Exception as e:
            logging.error(f"Auto-classification error for user {uid}: {e}")
    asyncio.create_task(_auto_sync(user_id))

    return serialize_doc({
        "status": "success",
        "connected": True,
        "token": token,
        "is_new_user": is_new_user,
        "user": {
            "id": user_id,
            "phone_number": phone,
            "business_name": user.get("business_name", ""),
            "owner_name": user.get("owner_name", ""),
            "subscription_active": user.get("subscription_active", False),
        }
    })

@api_router.post("/auth/whatsapp-refresh")
async def whatsapp_auth_refresh(request: WhatsAppAuthCheck):
    """
    Refresh the pairing code during auth (called before 60s expiry).
    """
    session = await db.wa_auth_sessions.find_one({"_id": request.session_token})
    if not session:
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    if datetime.utcnow() > session["expires"]:
        await db.wa_auth_sessions.delete_one({"_id": request.session_token})
        raise HTTPException(status_code=400, detail="Session expired. Please start again.")

    user_id = session["user_id"]
    phone = session["phone"]

    # Request new pairing code
    whatsapp_service = get_whatsapp_service(db)
    result = await whatsapp_service.create_instance(user_id, phone)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to refresh pairing code"))

    # Extend session expiry
    await db.wa_auth_sessions.update_one(
        {"_id": request.session_token},
        {"$set": {"expires": datetime.utcnow() + timedelta(minutes=5)}}
    )

    return {
        "status": "pairing",
        "pairing_code": result.get("pairing_code", ""),
        "pairing_data": result.get("pairing_data", {}),
    }

@api_router.post("/auth/register")
async def register_user(user_data: UserCreate, user = Depends(get_current_user)):
    """
    Complete registration after WhatsApp auth.
    Sets business name and owner name for a newly created user.
    Creates the user as the business owner in the team_members collection.
    Requires JWT (issued after WhatsApp connects).
    """
    # Update the user's business info
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "business_name": user_data.business_name,
            "owner_name": user_data.owner_name or "",
            "setup_complete": True,
            "role": TeamMemberRole.OWNER,
            "business_id": user["_id"],  # Owner's user_id is the business_id
        }}
    )

    # Create team member entry for the owner
    team_member = {
        "_id": str(uuid.uuid4()),
        "user_id": user["_id"],
        "name": user_data.owner_name or user_data.business_name,
        "email": "",  # Optional for owner
        "phone_number": user["phone_number"],
        "role": TeamMemberRole.OWNER,
        "business_id": user["_id"],
        "status": "active",
        "invited_by": user["_id"],
        "created_at": datetime.utcnow(),
        "last_active": datetime.utcnow()
    }
    await db.team_members.insert_one(team_member)

    return serialize_doc({
        "status": "success",
        "user": {
            "id": user["_id"],
            "phone_number": user["phone_number"],
            "business_name": user_data.business_name,
            "owner_name": user_data.owner_name or "",
            "role": TeamMemberRole.OWNER,
            "business_id": user["_id"],
            "subscription_active": user.get("subscription_active", False),
            "country_code": user.get("country_code"),
            "currency": user.get("currency", "USD"),
            "payment_methods": user.get("payment_methods", ["Cash", "Mobile Money", "Bank Transfer"]),
        }
    })

@api_router.get("/auth/me")
async def get_me(user = Depends(get_current_user)):
    """Get current user info"""
    business_id = user.get("business_id", user["_id"])
    
    # Count active team members for adaptive UI (with timeout to prevent hanging)
    try:
        team_members_count = await asyncio.wait_for(
            db.team_members.count_documents({"business_id": business_id, "status": "active"}),
            timeout=2.0
        )
    except (asyncio.TimeoutError, Exception):
        team_members_count = 0
    
    return serialize_doc({
        "id": user["_id"],
        "phone_number": user["phone_number"],
        "business_name": user.get("business_name", ""),
        "owner_name": user.get("owner_name", ""),
        "role": user.get("role", TeamMemberRole.OWNER),
        "business_id": business_id,
        "team_members_count": team_members_count,
        "subscription_plan": user.get("subscription_plan"),
        "subscription_active": user.get("subscription_active", False),
        "country_code": user.get("country_code"),
        "currency": user.get("currency", "USD"),
        "payment_methods": user.get("payment_methods", ["Cash", "Mobile Money", "Bank Transfer"])
    })

# ============ USER SETTINGS ============

_DEFAULT_BUSINESS_HOURS = {
    "mon": {"open": "08:00", "close": "17:00", "closed": False},
    "tue": {"open": "08:00", "close": "17:00", "closed": False},
    "wed": {"open": "08:00", "close": "17:00", "closed": False},
    "thu": {"open": "08:00", "close": "17:00", "closed": False},
    "fri": {"open": "08:00", "close": "17:00", "closed": False},
    "sat": {"open": "09:00", "close": "14:00", "closed": True},
    "sun": {"open": "09:00", "close": "14:00", "closed": True},
}

@api_router.get("/settings")
async def get_settings(user = Depends(get_current_user)):
    """Get current user settings"""
    s = user.get("settings", {})
    # Auto-initialize business hours with defaults if not yet configured
    business_hours = s.get("business_hours")
    if not business_hours:
        business_hours = _DEFAULT_BUSINESS_HOURS
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"settings.business_hours": business_hours}}
        )
        logging.info(f"[Settings] Auto-initialized business hours for user {user['_id']}")
    return {
        "auto_reply_enabled": s.get("auto_reply_enabled", False),
        "notification_enabled": s.get("notification_enabled", True),
        "notification_time": s.get("notification_time", "09:00"),
        "daily_alert_count": s.get("daily_alert_count", 5),
        "message_tone": s.get("message_tone", "friendly"),
        "push_token": s.get("push_token"),
        "daily_pulse_enabled": s.get("daily_pulse_enabled", False),
        "daily_pulse_time": s.get("daily_pulse_time", "08:00"),
        "currency": user.get("currency", s.get("currency", "USD")),
        "country_code": user.get("country_code", s.get("country_code", "")),
        "ai_model": s.get("ai_model", "standard"),
        "auto_reply_audience": s.get("auto_reply_audience", "everyone"),
        "business_type": s.get("business_type", "retail"),
        "business_hours": business_hours,
        "booking_settings": s.get("booking_settings", {}),
        "timezone": s.get("timezone", "UTC"),
        "rental_availability": s.get("rental_availability", []),
        "payment_methods": user.get("payment_methods", s.get("payment_methods", [])),
    }

@api_router.put("/settings")
async def update_settings(request: Request, user = Depends(get_current_user)):
    """Update user settings"""
    body = await request.json()
    # Top-level fields (currency, country_code) live directly on the user doc
    top_level_fields = {}
    settings_fields = {}
    for k, v in body.items():
        if k in ("currency", "country_code", "payment_methods"):
            top_level_fields[k] = v
        else:
            settings_fields[f"settings.{k}"] = v
    update_doc = {}
    if top_level_fields:
        update_doc.update(top_level_fields)
    if settings_fields:
        update_doc.update(settings_fields)
    if update_doc:
        await db.users.update_one({"_id": user["_id"]}, {"$set": update_doc})
    return {"status": "ok"}

# ============ PRODUCT ACTIONS ============

DEFAULT_PRODUCT_ACTIONS = [
    {"label": "Order Now",       "action_type": "order",       "index": 1, "ai_prompt": ""},
    {"label": "Add to Cart",     "action_type": "add_to_cart", "index": 2, "ai_prompt": ""},
]

# All action types supported + what they do
PRODUCT_ACTION_TYPES = {
    "order":       "Create order immediately",
    "add_to_cart": "Add to cart for multi-item checkout",
    "ask":         "Let customer ask the AI a question",
    "book":        "Book an appointment / service",
    "subscribe":   "Subscribe to a plan / service",
    "quote":       "Request a price quote",
    "test_drive":  "Schedule a test drive",
    "info":        "Get more product details via AI",
    "custom":      "Custom AI response (define your prompt)",
}

@api_router.get("/settings/product-actions")
async def get_product_actions(user = Depends(get_current_user)):
    """Get business's customized WhatsApp product action buttons"""
    actions = user.get("settings", {}).get("product_actions") or DEFAULT_PRODUCT_ACTIONS
    return {"actions": actions, "available_types": PRODUCT_ACTION_TYPES}

@api_router.put("/settings/product-actions")
async def update_product_actions(request: Request, user = Depends(get_current_user)):
    """Update business's WhatsApp product action buttons (max 3)"""
    body = await request.json()
    raw = body.get("actions", [])
    validated = []
    for i, a in enumerate(raw[:3], 1):
        lbl = str(a.get("label", "")).strip()[:30]
        atype = str(a.get("action_type", "order")).strip()
        if not lbl:
            continue
        if atype not in PRODUCT_ACTION_TYPES:
            atype = "order"
        validated.append({
            "label":       lbl,
            "action_type": atype,
            "index":       i,
            "ai_prompt":   str(a.get("ai_prompt", "")).strip()[:200],
        })
    if not validated:
        validated = DEFAULT_PRODUCT_ACTIONS
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"settings.product_actions": validated}}
    )
    return {"status": "ok", "actions": validated}

# ============ CONTACT CLASSIFICATION ============

@api_router.post("/contacts/classify")
async def classify_contacts(user = Depends(get_current_user)):
    """Run AI classification on unclassified contacts"""
    business_id = user.get("business_id", user["_id"])
    classifier = get_classifier(db)
    # Find customers without a confirmed classification
    unclassified = await db.customers.find({
        "user_id": business_id,
        "classification_confirmed": {"$ne": True},
    }).to_list(100)
    results = []
    for c in unclassified:
        try:
            result = await classifier.classify_contact(business_id, c["_id"])
            if result and result.get("suggested_type"):
                await db.customers.update_one(
                    {"_id": c["_id"]},
                    {"$set": {
                        "pending_classification": result["suggested_type"],
                        "classification_confidence": result.get("confidence", 0),
                        "classification_reason": result.get("reason", ""),
                        "classification_pending": True,
                    }}
                )
                results.append({"id": c["_id"], "name": c["name"], "classification": result["suggested_type"]})
        except Exception as e:
            logging.error(f"Classification error for {c['_id']}: {e}")
    return {"classified": len(results), "results": results}

@api_router.get("/contacts/pending")
async def get_pending_classifications(user = Depends(get_current_user)):
    """Get contacts with pending (unconfirmed) AI classifications"""
    business_id = user.get("business_id", user["_id"])
    pending = await db.customers.find({
        "user_id": business_id,
        "classification_pending": True,
    }).to_list(50)
    result = []
    for c in pending:
        result.append({
            "id": c["_id"],
            "name": c["name"],
            "phone_number": c["phone_number"],
            "pending_classification": c.get("pending_classification"),
            "classification_confidence": c.get("classification_confidence", 0),
            "classification_reason": c.get("classification_reason", ""),
        })
    return result

@api_router.post("/contacts/{customer_id}/confirm")
async def confirm_classification(customer_id: str, request: Request, user = Depends(get_current_user)):
    """Confirm or override a pending contact classification"""
    business_id = user.get("business_id", user["_id"])
    body = await request.json()
    action = body.get("action")  # "approve" or "reject"
    contact_type = body.get("type")  # "customer" or "supplier"
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Contact not found")
    if action == "approve":
        classification = contact_type or customer.get("pending_classification", "customer")
        tags = list(customer.get("tags", []))
        if classification == "supplier" and "Supplier" not in tags:
            tags.append("Supplier")
        elif classification == "customer" and "Supplier" in tags:
            tags.remove("Supplier")
        await db.customers.update_one(
            {"_id": customer_id},
            {"$set": {
                "classification_type": classification,
                "classification_confirmed": True,
                "classification_pending": False,
                "is_customer": True,
                "tags": tags,
                "classified_at": datetime.utcnow(),
            }}
        )
        # Clear pending classification entry
        await db.pending_classifications.update_one(
            {"customer_id": customer_id, "user_id": business_id},
            {"$set": {"status": "approved", "resolved_at": datetime.utcnow()}}
        )
    else:
        # Reject — clear pending flag and dismiss classification
        await db.customers.update_one(
            {"_id": customer_id},
            {"$set": {"classification_pending": False}}
        )
        await db.pending_classifications.update_one(
            {"customer_id": customer_id, "user_id": business_id},
            {"$set": {"status": "rejected", "resolved_at": datetime.utcnow()}}
        )
    return {"status": "ok", "action": action}

@api_router.post("/contacts/{customer_id}/dismiss")
async def dismiss_classification(customer_id: str, user = Depends(get_current_user)):
    """Dismiss a pending classification without confirming"""
    business_id = user.get("business_id", user["_id"])
    await db.customers.update_one(
        {"_id": customer_id, "user_id": business_id},
        {"$set": {"classification_pending": False}}
    )
    return {"status": "ok"}

@api_router.post("/auth/push-token")
async def save_push_token(request: Request, user = Depends(get_current_user)):
    """Save Expo push token for this user device"""
    body = await request.json()
    token = body.get("token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token required")
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"push_tokens": token}}
    )
    return {"status": "ok"}

@api_router.delete("/auth/push-token")
async def remove_push_token(request: Request, user = Depends(get_current_user)):
    """Remove Expo push token (on logout)"""
    body = await request.json()
    token = body.get("token", "").strip()
    if token:
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$pull": {"push_tokens": token}}
        )
    return {"status": "ok"}

async def send_push_notification(user_id: str, title: str, body: str, data: dict = None):
    """Send Expo push notification to all devices of a user"""
    import httpx
    user = await db.users.find_one({"_id": user_id})
    if not user:
        return
    tokens = user.get("push_tokens", [])
    if not tokens:
        return
    messages = [
        {
            "to": token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
            "priority": "high",
        }
        for token in tokens
        if token.startswith("ExponentPushToken") or token.startswith("ExpoPushToken")
    ]
    if not messages:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=messages,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            logging.info(f"Push notification sent to {len(messages)} device(s): {resp.status_code}")
    except Exception as e:
        logging.error(f"Push notification failed: {e}")

# ============ TEAM MANAGEMENT ENDPOINTS ============

def check_permission(user: dict, required_role: str) -> bool:
    """Check if user has required permission level.
    Users with no role field and no business_id are business owners (created before team feature).
    """
    role_hierarchy = {TeamMemberRole.OWNER: 3, TeamMemberRole.MANAGER: 2, TeamMemberRole.EMPLOYEE: 1}
    # If no role set and no business_id, this is a standalone owner account
    if not user.get("role") and not user.get("business_id"):
        effective_role = TeamMemberRole.OWNER
    else:
        effective_role = user.get("role", TeamMemberRole.EMPLOYEE)
    user_level = role_hierarchy.get(effective_role, 1)
    required_level = role_hierarchy.get(required_role, 1)
    return user_level >= required_level

@api_router.post("/team/invite", response_model=TeamMemberResponse)
async def invite_team_member(invite: TeamMemberInvite, user = Depends(get_current_user)):
    """Invite a new team member (Owner/Manager only)"""
    if not check_permission(user, TeamMemberRole.MANAGER):
        raise HTTPException(status_code=403, detail="Only owners and managers can invite team members")
    
    business_id = user.get("business_id", user["_id"])

    # Normalize phone number
    phone = invite.phone_number.strip()
    if not phone or len(phone) < 8:
        raise HTTPException(status_code=400, detail="Valid phone number is required")

    # Check if phone already added to this business
    existing = await db.team_members.find_one({"business_id": business_id, "phone_number": phone})
    if existing:
        raise HTTPException(status_code=400, detail="This phone number is already on your team")

    # Validate role
    if invite.role not in [TeamMemberRole.EMPLOYEE, TeamMemberRole.MANAGER]:
        raise HTTPException(status_code=400, detail="Can only invite employees or managers")

    # Create team member — status is "invited" until they log in for the first time
    member_id = str(uuid.uuid4())
    team_member = {
        "_id": member_id,
        "user_id": None,  # Linked automatically when they log in with this phone
        "name": invite.name,
        "email": invite.email,  # Optional reference
        "phone_number": phone,
        "role": invite.role,
        "business_id": business_id,
        "status": "invited",
        "invited_by": user["_id"],
        "created_at": datetime.utcnow(),
        "last_active": None
    }
    await db.team_members.insert_one(team_member)

    # Notify the employee via WhatsApp on the business instance
    try:
        business_owner = await db.users.find_one({"_id": business_id})
        business_name = business_owner.get("business_name", "Your employer") if business_owner else "Your employer"
        ws = get_whatsapp_service(db)
        await ws.send_message(
            user_id=business_id,
            to_number=phone,
            message=(
                f"👋 Hi {invite.name}! You've been added to *{business_name}*'s team as {invite.role}.\n\n"
                f"Download the CRM app and enter your phone number (*{phone}*) to log in — no extra steps needed!"
            ),
            send_context="auto_reply"
        )
    except Exception as e:
        logging.warning(f"Could not send WhatsApp invite notification: {e}")

    return TeamMemberResponse(**{**team_member, "id": member_id})

@api_router.get("/team/members")
async def get_team_members(user = Depends(get_current_user)):
    """Get all team members for the business"""
    business_id = user.get("business_id", user["_id"])
    
    members = []
    async for member in db.team_members.find({"business_id": business_id}).sort("created_at", -1):
        members.append({
            "id": member["_id"],
            "name": member["name"],
            "email": member.get("email", ""),
            "phone_number": member.get("phone_number"),
            "role": member["role"],
            "business_id": member["business_id"],
            "status": member["status"],
            "invited_by": member["invited_by"],
            "created_at": member["created_at"],
            "last_active": member.get("last_active")
        })
    
    return members

@api_router.put("/team/members/{member_id}")
async def update_team_member(member_id: str, updates: TeamMemberUpdate, user = Depends(get_current_user)):
    """Update team member (Owner/Manager only)"""
    if not check_permission(user, TeamMemberRole.MANAGER):
        raise HTTPException(status_code=403, detail="Only owners and managers can update team members")
    
    business_id = user.get("business_id", user["_id"])
    
    # Get member
    member = await db.team_members.find_one({"_id": member_id, "business_id": business_id})
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    # Can't change owner role
    if member["role"] == TeamMemberRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot modify the business owner")
    
    # Build update
    update_data = {}
    if updates.name:
        update_data["name"] = updates.name
    if updates.role and updates.role in [TeamMemberRole.EMPLOYEE, TeamMemberRole.MANAGER]:
        update_data["role"] = updates.role
    if updates.status and updates.status in ["active", "suspended"]:
        update_data["status"] = updates.status
    
    if update_data:
        await db.team_members.update_one({"_id": member_id}, {"$set": update_data})
    
    return {"status": "success", "message": "Team member updated"}

@api_router.delete("/team/members/{member_id}")
async def remove_team_member(member_id: str, user = Depends(get_current_user)):
    """Remove team member (Owner only)"""
    if not check_permission(user, TeamMemberRole.OWNER):
        raise HTTPException(status_code=403, detail="Only the business owner can remove team members")
    
    business_id = user.get("business_id", user["_id"])
    
    # Get member
    member = await db.team_members.find_one({"_id": member_id, "business_id": business_id})
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    # Can't remove owner
    if member["role"] == TeamMemberRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot remove the business owner")
    
    # Remove member
    await db.team_members.delete_one({"_id": member_id})
    
    # Unassign all conversations
    await db.conversation_assignments.update_many(
        {"business_id": business_id, "assigned_to": member.get("user_id")},
        {"$set": {"assigned_to": None}}
    )
    
    return {"status": "success", "message": "Team member removed"}

# ============ CONVERSATION ASSIGNMENT ENDPOINTS ============

@api_router.post("/conversations/assign")
async def assign_conversation(assignment: ConversationAssignment, user = Depends(get_current_user)):
    """Assign a conversation to a team member"""
    business_id = user.get("business_id", user["_id"])
    
    # Verify customer exists
    customer = await db.customers.find_one({"_id": assignment.customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Verify assignee is a team member (if assigned)
    if assignment.assigned_to:
        assignee = await db.team_members.find_one({
            "business_id": business_id,
            "user_id": assignment.assigned_to,
            "status": "active"
        })
        if not assignee:
            raise HTTPException(status_code=404, detail="Team member not found")
    
    # Create or update assignment
    assignment_doc = {
        "customer_id": assignment.customer_id,
        "business_id": business_id,
        "assigned_to": assignment.assigned_to,
        "assigned_by": assignment.assigned_by,
        "assigned_at": datetime.utcnow(),
        "notes": assignment.notes
    }
    
    await db.conversation_assignments.update_one(
        {"business_id": business_id, "customer_id": assignment.customer_id},
        {"$set": assignment_doc},
        upsert=True
    )
    
    # Log activity
    await log_activity(
        business_id=business_id,
        user_id=user["_id"],
        user_name=user.get("owner_name", user.get("business_name", "User")),
        action="conversation_assigned",
        entity_type="conversation",
        entity_id=assignment.customer_id,
        details={"assigned_to": assignment.assigned_to, "notes": assignment.notes}
    )
    
    return {"status": "success", "message": "Conversation assigned"}

@api_router.get("/conversations/assignments")
async def get_conversation_assignments(user = Depends(get_current_user)):
    """Get all conversation assignments for the business"""
    business_id = user.get("business_id", user["_id"])
    
    assignments = []
    async for assignment in db.conversation_assignments.find({"business_id": business_id}):
        assignments.append({
            "customer_id": assignment["customer_id"],
            "assigned_to": assignment.get("assigned_to"),
            "assigned_by": assignment["assigned_by"],
            "assigned_at": assignment["assigned_at"],
            "notes": assignment.get("notes")
        })
    
    return assignments

@api_router.get("/conversations/my-assignments")
async def get_my_assignments(user = Depends(get_current_user)):
    """Get conversations assigned to current user"""
    business_id = user.get("business_id", user["_id"])
    
    assignments = []
    async for assignment in db.conversation_assignments.find({
        "business_id": business_id,
        "assigned_to": user["_id"]
    }):
        # Get customer details
        customer = await db.customers.find_one({"_id": assignment["customer_id"]})
        if customer:
            assignments.append({
                "customer_id": assignment["customer_id"],
                "customer_name": customer.get("name", "Unknown"),
                "customer_phone": customer.get("phone_number", ""),
                "assigned_at": assignment["assigned_at"],
                "notes": assignment.get("notes")
            })
    
    return assignments

# ============ ACTIVITY LOG ENDPOINTS ============

async def log_activity(business_id: str, user_id: str, user_name: str, action: str, entity_type: str, entity_id: str, details: dict = None):
    """Helper function to log user activity"""
    activity = {
        "_id": str(uuid.uuid4()),
        "business_id": business_id,
        "user_id": user_id,
        "user_name": user_name,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details or {},
        "timestamp": datetime.utcnow()
    }
    await db.activity_logs.insert_one(activity)

@api_router.get("/activity/logs")
async def get_activity_logs(
    limit: int = Query(50, le=200),
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Get activity logs for the business"""
    if not check_permission(user, TeamMemberRole.MANAGER):
        raise HTTPException(status_code=403, detail="Only owners and managers can view activity logs")
    
    business_id = user.get("business_id", user["_id"])
    
    query = {"business_id": business_id}
    if user_id:
        query["user_id"] = user_id
    if entity_type:
        query["entity_type"] = entity_type
    
    logs = []
    async for log in db.activity_logs.find(query).sort("timestamp", -1).limit(limit):
        logs.append({
            "id": log["_id"],
            "user_id": log["user_id"],
            "user_name": log["user_name"],
            "action": log["action"],
            "entity_type": log["entity_type"],
            "entity_id": log["entity_id"],
            "details": log.get("details", {}),
            "timestamp": log["timestamp"]
        })
    
    return logs

# ============ SUPPLIER ENDPOINTS ============

SUPPLIER_CATEGORIES = [
    "Electronics", "Clothing", "Food & Beverage", "Beauty & Health",
    "Home & Garden", "Automotive", "Raw Materials", "Packaging",
    "Stationery", "Services", "Other"
]

@api_router.get("/suppliers/categories")
async def get_supplier_categories():
    """Get available supplier categories"""
    return SUPPLIER_CATEGORIES

@api_router.get("/suppliers/insights")
async def get_supplier_insights(user = Depends(get_current_user)):
    """Get supplier insights and potential suppliers"""
    business_id = user.get("business_id", user["_id"])
    analyzer = SupplierAnalyzer(db)
    potential = await analyzer.identify_potential_suppliers(business_id)
    restock = await analyzer.get_restock_suggestions(business_id)
    return serialize_doc({
        "potential_suppliers": potential,
        "restock_suggestions": restock
    })

@api_router.get("/suppliers")
async def get_suppliers(user = Depends(get_current_user)):
    """Get all suppliers with their details"""
    business_id = user.get("business_id", user["_id"])
    suppliers = await db.customers.find({
        "user_id": business_id,
        "tags": "Supplier"
    }).to_list(100)
    
    # Enrich with product links
    for s in suppliers:
        s["id"] = s["_id"]
        s["supplier_category"] = s.get("supplier_category", "Other")
        s["products_supplied"] = s.get("products_supplied", [])
        s["payment_terms"] = s.get("payment_terms", "")
        s["lead_time"] = s.get("lead_time", "")
        s["rating"] = s.get("rating", 0)
    
    return serialize_doc(suppliers)

@api_router.post("/suppliers/{customer_id}/tag")
async def tag_supplier(customer_id: str, user = Depends(get_current_user)):
    """Tag a customer as a supplier"""
    business_id = user.get("business_id", user["_id"])
    await db.customers.update_one(
        {"_id": customer_id, "user_id": business_id},
        {"$addToSet": {"tags": "Supplier"}}
    )
    return {"status": "success"}

@api_router.put("/suppliers/{customer_id}")
async def update_supplier_details(customer_id: str, body: dict = Body(...), user = Depends(get_current_user)):
    """Update supplier-specific details like category, products, payment terms"""
    update_fields = {}
    if "supplier_category" in body:
        update_fields["supplier_category"] = body["supplier_category"]
    if "products_supplied" in body:
        update_fields["products_supplied"] = body["products_supplied"]
    if "payment_terms" in body:
        update_fields["payment_terms"] = body["payment_terms"]
    if "lead_time" in body:
        update_fields["lead_time"] = body["lead_time"]
    if "rating" in body:
        update_fields["rating"] = int(body["rating"])
    
    business_id = user.get("business_id", user["_id"])
    if update_fields:
        await db.customers.update_one(
            {"_id": customer_id, "user_id": business_id},
            {"$set": update_fields}
        )
    
    return {"status": "success"}

@api_router.delete("/suppliers/{customer_id}")
async def remove_supplier_tag(customer_id: str, user = Depends(get_current_user)):
    """Remove supplier tag from a customer"""
    business_id = user.get("business_id", user["_id"])
    await db.customers.update_one(
        {"_id": customer_id, "user_id": business_id},
        {"$pull": {"tags": "Supplier"}, "$unset": {"supplier_category": "", "products_supplied": "", "payment_terms": "", "lead_time": "", "rating": ""}}
    )
    return {"status": "success"}

# ============ CONTACT CLASSIFICATION ============

@api_router.post("/contacts/classify")
async def classify_contacts(background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    """Scan all contacts and classify them as customer/supplier using AI"""
    classifier = get_classifier(db)
    results = await classifier.classify_all_contacts(user["_id"])
    return {
        "classified": len(results),
        "results": results
    }

@api_router.get("/contacts/pending")
async def get_pending_classifications(user = Depends(get_current_user)):
    """Get all pending AI classifications awaiting user approval"""
    business_id = user.get("business_id", user["_id"])
    pending = await db.pending_classifications.find({
        "user_id": business_id,
        "status": "pending",
        "confidence": {"$gte": 0.4},
    }).sort("confidence", -1).to_list(50)
    
    for p in pending:
        p["id"] = str(p["_id"])
        p["customer_id"] = str(p["customer_id"]) if p.get("customer_id") else None
    
    # Drop entries where customer_id resolved to None (orphaned records)
    pending = [p for p in pending if p.get("customer_id")]
    
    return serialize_doc(pending)

@api_router.post("/contacts/{customer_id}/confirm")
async def confirm_classification(customer_id: str, body: dict = Body(...), user = Depends(get_current_user)):
    """
    Confirm or reject an AI classification.
    body: { "action": "approve" | "reject", "type": "customer" | "supplier" }
    If approved, tags the contact accordingly. If rejected, dismisses the suggestion.
    """
    action = body.get("action", "approve")
    contact_type = body.get("type", "customer")
    business_id = user.get("business_id", user["_id"])
    
    if action == "approve":
        update_tags = {}
        if contact_type == "supplier":
            # Add Supplier tag
            update_tags = {
                "$addToSet": {"tags": "Supplier"},
                "$set": {
                    "classification_confirmed": True,
                    "classification_type": "supplier",
                    "classified_at": datetime.utcnow(),
                    "is_customer": True,
                }
            }
            # If AI detected a category, apply it
            pending = await db.pending_classifications.find_one({
                "customer_id": customer_id, "user_id": business_id
            })
            if pending and pending.get("detected_details", {}).get("suggested_category"):
                update_tags["$set"]["supplier_category"] = pending["detected_details"]["suggested_category"]
            if pending and pending.get("detected_details", {}).get("products"):
                update_tags["$set"]["products_supplied"] = pending["detected_details"]["products"]
        else:
            # Confirm as customer (remove Supplier tag if present)
            update_tags = {
                "$pull": {"tags": "Supplier"},
                "$set": {
                    "classification_confirmed": True,
                    "classification_type": "customer",
                    "classified_at": datetime.utcnow(),
                    "is_customer": True,
                }
            }
        
        await db.customers.update_one(
            {"_id": customer_id, "user_id": business_id},
            update_tags
        )
    
    # Mark classification as handled
    await db.pending_classifications.update_one(
        {"customer_id": customer_id, "user_id": business_id},
        {"$set": {
            "status": "approved" if action == "approve" else "rejected",
            "resolved_at": datetime.utcnow(),
        }}
    )
    
    return {"status": "success", "action": action, "type": contact_type}

@api_router.post("/contacts/{customer_id}/dismiss")
async def dismiss_classification(customer_id: str, user = Depends(get_current_user)):
    """Dismiss a pending classification without confirming"""
    business_id = user.get("business_id", user["_id"])
    await db.pending_classifications.update_one(
        {"customer_id": customer_id, "user_id": business_id},
        {"$set": {"status": "dismissed", "resolved_at": datetime.utcnow()}}
    )
    return {"status": "success"}

# ============ CUSTOMER ENDPOINTS ============

@api_router.post("/customers", response_model=CustomerResponse)
async def create_customer(customer: CustomerCreate, user = Depends(get_current_user)):
    """Create a new customer"""
    # Sanitize inputs
    clean_name = sanitize_string(customer.name, 200)
    clean_phone = sanitize_phone(customer.phone_number)
    clean_notes = sanitize_string(customer.notes, 2000) if customer.notes else None
    clean_tags = [sanitize_string(t, 50) for t in (customer.tags or []) if t.strip()][:20]

    if not clean_name:
        raise HTTPException(status_code=400, detail="Customer name is required")
    if not clean_phone or len(clean_phone) < 6:
        raise HTTPException(status_code=400, detail="Valid phone number is required")

    customer_id = str(uuid.uuid4())
    business_id = user.get("business_id", user["_id"])

    # Check for duplicate phone number
    existing = await db.customers.find_one({"user_id": business_id, "phone_number": clean_phone})
    if existing:
        if existing.get("is_customer"):
            raise HTTPException(status_code=409, detail="A customer with this phone number already exists")
        # Contact exists but not yet a customer — promote it
        await db.customers.update_one(
            {"_id": existing["_id"]},
            {"$set": {"is_customer": True, "name": clean_name, "notes": clean_notes, "tags": clean_tags if clean_tags else ["New"]}}
        )
        return CustomerResponse(
            id=existing["_id"],
            user_id=business_id,
            name=clean_name,
            phone_number=clean_phone,
            notes=clean_notes,
            tags=clean_tags if clean_tags else ["New"],
            purchase_count=existing.get("purchase_count", 0),
            total_spent=existing.get("total_spent", 0.0),
            last_message=existing.get("last_message"),
            last_contacted=existing.get("last_contacted"),
            created_at=existing.get("created_at", datetime.utcnow()),
            is_customer=True,
        )

    customer_doc = {
        "_id": customer_id,
        "user_id": business_id,
        "name": clean_name,
        "phone_number": clean_phone,
        "notes": clean_notes,
        "tags": clean_tags if clean_tags else ["New"],
        "purchase_count": 0,
        "total_spent": 0.0,
        "last_message": None,
        "last_contacted": None,
        "created_at": datetime.utcnow(),
        "is_customer": True,
    }

    try:
        await db.customers.insert_one(customer_doc)
    except Exception as e:
        logging.error(f"create_customer insert failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create customer — please try again")

    return CustomerResponse(
        id=customer_id,
        user_id=business_id,
        name=clean_name,
        phone_number=clean_phone,
        notes=clean_notes,
        tags=customer_doc["tags"],
        purchase_count=0,
        total_spent=0.0,
        last_message=None,
        last_contacted=None,
        created_at=customer_doc["created_at"],
        is_customer=True,
    )

def _normalize_phone(phone: str) -> str:
    """Normalize a phone number — strip +, spaces, dashes, and truncate to max 15 digits (E.164 max)"""
    if not phone:
        return phone
    digits = phone.lstrip('+').replace(' ', '').replace('-', '')
    # E.164 max is 15 digits. If longer, it's a malformed JID — truncate to 15
    if len(digits) > 15:
        digits = digits[:15]
    return digits

@api_router.get("/customers/all-contacts")
async def get_all_contacts(user = Depends(get_current_user)):
    """Return all contacts synced from WhatsApp regardless of customer/supplier status"""
    business_id = user.get("business_id", user["_id"])
    contacts = await db.customers.find({"user_id": business_id}).sort("created_at", -1).to_list(2000)
    result = []
    for c in contacts:
        raw_phone = c.get("phone_number", "")
        result.append({
            "id": c["_id"],
            "name": c.get("name", ""),
            "phone_number": raw_phone,
            "tags": c.get("tags", []),
            "classification_type": c.get("classification_type", ""),
            "classification_confirmed": c.get("classification_confirmed", False),
            "last_contacted": c.get("last_contacted"),
            "last_message": c.get("last_message", ""),
            "created_at": c.get("created_at"),
            "is_customer": bool(c.get("classification_confirmed") and c.get("classification_type") == "customer")
                          or (not c.get("classification_type") and "Supplier" not in c.get("tags", [])),
        })
    return result

@api_router.get("/contacts")
async def get_contacts(search: str = "", user = Depends(get_current_user)):
    """Return all WhatsApp-synced contacts that are NOT yet customers."""
    business_id = user.get("business_id", user["_id"])
    query = {
        "user_id": business_id,
        "is_customer": False,
        "auto_created": True,
    }
    contacts = await db.customers.find(query).to_list(2000)
    if search:
        s = search.lower()
        contacts = [c for c in contacts if s in c.get("name", "").lower() or s in c.get("phone_number", "").lower()]

    # Merge pending classification data onto contacts
    contact_ids = [c["_id"] for c in contacts]
    pending_list = await db.pending_classifications.find({
        "user_id": business_id,
        "customer_id": {"$in": contact_ids},
        "status": "pending",
    }).to_list(2000)
    pending_map = {p["customer_id"]: p for p in pending_list}

    # Sort: suggested contacts first, then A-Z, symbols/numbers last
    def _sort_key(c):
        has_suggestion = c["_id"] in pending_map
        name = (c.get("name") or "").strip()
        first = name[0].upper() if name else ""
        is_letter = first.isalpha()
        return (0 if has_suggestion else 1, 0 if is_letter else 1, name.lower())
    contacts.sort(key=_sort_key)

    result = []
    for c in contacts:
        pending = pending_map.get(c["_id"])
        raw_confidence = pending["confidence"] if pending else c.get("suggestion_confidence", 0)
        raw_suggested_type = pending["suggested_type"] if pending else c.get("suggested_type")
        # Only surface suggestions with meaningful confidence (>= 40%) so empty/0% entries never show confirm buttons
        suggested_type = raw_suggested_type if (raw_suggested_type and raw_confidence >= 0.4) else None
        result.append({
            "id": str(c["_id"]),
            "name": c.get("name", ""),
            "phone_number": c.get("phone_number", ""),
            "profile_picture": c.get("profile_picture"),
            "last_message": c.get("last_message", ""),
            "last_contacted": c.get("last_contacted"),
            "suggested_type": suggested_type,
            "suggestion_reason": (pending["reason"] if pending else c.get("suggestion_reason")) if suggested_type else None,
            "suggestion_confidence": raw_confidence,
            "tags": c.get("tags", []),
            "created_at": c.get("created_at"),
        })
    return result

@api_router.get("/contacts/suggestions")
async def get_contact_suggestions(user = Depends(get_current_user)):
    """Return contacts that AI has flagged as likely customers."""
    business_id = user.get("business_id", user["_id"])
    contacts = await db.customers.find({
        "user_id": business_id,
        "is_customer": False,
        "suggested_type": "customer",
    }).sort("suggestion_confidence", -1).to_list(100)
    return [
        {
            "id": c["_id"],
            "name": c.get("name", ""),
            "phone_number": c.get("phone_number", ""),
            "profile_picture": c.get("profile_picture"),
            "last_message": c.get("last_message", ""),
            "last_contacted": c.get("last_contacted"),
            "suggested_type": c.get("suggested_type"),
            "suggestion_reason": c.get("suggestion_reason"),
            "suggestion_confidence": c.get("suggestion_confidence", 0),
        }
        for c in contacts
    ]

@api_router.post("/contacts/{contact_id}/add-as-customer")
async def add_contact_as_customer(contact_id: str, user = Depends(get_current_user)):
    """Promote a WhatsApp contact to a CRM customer."""
    business_id = user.get("business_id", user["_id"])
    contact = await db.customers.find_one({"_id": contact_id, "user_id": business_id})
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if contact.get("is_customer"):
        return {"status": "already_customer", "customer_id": contact_id}
    await db.customers.update_one(
        {"_id": contact_id},
        {"$set": {"is_customer": True, "promoted_at": datetime.utcnow()}}
    )
    return {"status": "success", "customer_id": contact_id}

@api_router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, user = Depends(get_current_user)):
    """Remove a WhatsApp contact (not a customer) from the contacts pool."""
    business_id = user.get("business_id", user["_id"])
    contact = await db.customers.find_one({"_id": contact_id, "user_id": business_id})
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if contact.get("is_customer"):
        raise HTTPException(status_code=400, detail="Cannot delete a customer from contacts — remove them from Customers instead")
    await db.customers.delete_one({"_id": contact_id})
    await db.messages.delete_many({"customer_id": contact_id})
    return {"status": "deleted"}

@api_router.post("/contacts/purge-lid-numbers")
async def purge_lid_numbers(user = Depends(get_current_user)):
    """
    Delete auto-created contacts with invalid phone numbers:
    - Garbage @lid JID numbers (>15 digits)
    - User's own number stored as a contact
    - Too-short numbers (<7 digits)
    Safe to call multiple times — never deletes confirmed customers.
    """
    business_id = user.get("business_id", user["_id"])
    deleted = await _purge_invalid_contacts_for_user(business_id)
    return {"status": "done", "deleted": deleted}

@api_router.post("/contacts/scan-suggestions")
async def scan_contact_suggestions(background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    """Run AI classification on all unclassified contacts to generate customer suggestions."""
    business_id = user.get("business_id", user["_id"])

    async def _scan():
        classifier = get_classifier(db)
        contacts = await db.customers.find({
            "user_id": business_id,
            "is_customer": False,
            "suggested_type": {"$exists": False},
        }).to_list(500)
        updated = 0
        for contact in contacts:
            try:
                result = await classifier.classify_contact(business_id, contact["_id"], keyword_only=True)
                if result and result.get("confidence", 0) >= 0.4:
                    await db.customers.update_one(
                        {"_id": contact["_id"]},
                        {"$set": {
                            "suggested_type": result["suggested_type"],
                            "suggestion_reason": result["reason"],
                            "suggestion_confidence": result["confidence"],
                        }}
                    )
                    updated += 1
            except Exception:
                continue
        logging.info(f"Contact suggestion scan: {updated}/{len(contacts)} contacts classified")

    background_tasks.add_task(_scan)
    return {"status": "scanning", "message": "Suggestion scan started in background"}

@api_router.get("/customers", response_model=List[CustomerResponse])
async def get_customers(
    tag: Optional[str] = None, 
    sort_by: Optional[str] = None, 
    filter_by: Optional[str] = None,  # "all", "assigned_to_me", "unassigned"
    user = Depends(get_current_user)
):
    """
    Get customers for current user with role-based filtering.
    - Owner/Manager: Can see all customers
    - Employee: Can see assigned + unassigned customers
    - filter_by: "all" (owner/manager only), "assigned_to_me", "unassigned"
    """
    business_id = user.get("business_id", user["_id"])
    user_role = user.get("role", "owner")
    
    # Base query uses business_id for multi-user support
    # Only return explicit customers — WhatsApp-synced contacts live in /contacts
    query = {"user_id": business_id, "$or": [{"is_customer": True}, {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}]}
    if tag:
        query["tags"] = tag
    
    # Fetch customers
    if sort_by == "purchases":
        sort_field = "purchase_count"
        sort_order = -1
    elif sort_by == "recently_contacted":
        sort_field = "last_contacted"
        sort_order = -1
    elif sort_by == "oldest":
        sort_field = "created_at"
        sort_order = 1
    else:
        sort_field = "created_at"
        sort_order = -1
    
    customers = await db.customers.find(query).sort(sort_field, sort_order).to_list(1000)
    customer_ids = [c["_id"] for c in customers]
    
    # Fetch assignments for filtering
    assignments = await db.conversation_assignments.find({
        "business_id": business_id,
        "customer_id": {"$in": customer_ids}
    }).to_list(1000)
    assignment_map = {a["customer_id"]: a.get("assigned_to") for a in assignments}
    
    # Apply role-based filtering
    if filter_by == "assigned_to_me":
        # Show only customers assigned to current user
        customers = [c for c in customers if assignment_map.get(c["_id"]) == user["_id"]]
    elif filter_by == "unassigned":
        # Show only unassigned customers
        customers = [c for c in customers if c["_id"] not in assignment_map or assignment_map.get(c["_id"]) is None]
    elif user_role == "employee":
        # Employees see their assigned + unassigned (not other employees' assignments)
        customers = [c for c in customers if c["_id"] not in assignment_map or assignment_map.get(c["_id"]) in [None, user["_id"]]]
    # Owner/Manager with filter_by="all" or no filter sees everything
    
    # Batch fetch unread counts
    customer_ids = [c["_id"] for c in customers]
    unread_pipeline = [
        {"$match": {"customer_id": {"$in": customer_ids}, "user_id": business_id, "direction": "incoming", "read": {"$ne": True}}},
        {"$group": {"_id": "$customer_id", "count": {"$sum": 1}}}
    ]
    unread_results = await db.messages.aggregate(unread_pipeline).to_list(1000)
    unread_map = {r["_id"]: r["count"] for r in unread_results}

    # Fetch team member names for assigned_to display
    team_members = await db.team_members.find({"business_id": business_id}).to_list(100)
    member_map = {m.get("user_id"): m["name"] for m in team_members if m.get("user_id")}

    return [
        CustomerResponse(
            id=c["_id"],
            user_id=c["user_id"],
            name=c["name"],
            phone_number=c["phone_number"],
            notes=c.get("notes"),
            tags=c.get("tags", []),
            stage=c.get("stage", "lead"),
            purchase_count=c.get("purchase_count", 0),
            total_spent=c.get("total_spent", 0.0),
            last_message=c.get("last_message"),
            last_contacted=c.get("last_contacted"),
            profile_picture=c.get("profile_picture"),
            unread_count=unread_map.get(c["_id"], 0),
            created_at=c.get("created_at", datetime.utcnow()),
            assigned_to=assignment_map.get(c["_id"]),
            assigned_to_name=member_map.get(assignment_map.get(c["_id"])) if assignment_map.get(c["_id"]) else None
        )
        for c in customers
    ]

@api_router.get("/customers/cold")
async def get_cold_customers(days: int = 14, user = Depends(get_current_user)):
    """Get customers who haven't been contacted in X days"""
    business_id = user.get("business_id", user["_id"])
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    customers = await db.customers.find({
        "user_id": business_id,
        "$or": [{"is_customer": True}, {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}],
    }).sort("last_contacted", 1).to_list(100)
    
    # Get today's analysis date
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Try to get Smart Insights first (AI Daily Analysis)
    # This respects the "Smart Tiers" (limit 10/20/30) and "Smart Cadence" (24h/3d)
    smart_insights = await db.customer_analysis.find({
        "user_id": business_id,
        "analysis_date": {"$gte": today}
    }).sort("urgency_score", -1).to_list(100)
    
    result = []
    analyzed_customer_ids = set()
    
    # First, add customers with smart insights (if available)
    if smart_insights:
        for analysis in smart_insights:
            c = await db.customers.find_one({"_id": analysis["customer_id"]})
            if not c: continue
            # Skip raw contacts — only real customers
            if not c.get("is_customer", True) and c.get("auto_created"):
                continue
            
            # CRITICAL: Only include if they actually need attention (>7 days or never contacted)
            last_contacted = c.get("last_contacted")
            if last_contacted and last_contacted >= cutoff_date:
                continue  # Skip - contacted recently
            
            analyzed_customer_ids.add(c["_id"])
            result.append({
                "id": c["_id"], "name": c["name"], "phone_number": c["phone_number"],
                "notes": c.get("notes"), "tags": c.get("tags", []),
                "last_message": c.get("last_message"), "last_contacted": c.get("last_contacted"),
                "days_since_contact": analysis.get("days_since_contact"), 
                "has_pending_followup": analysis.get("has_pending_followup", False),
                "ai_reason": analysis.get("ai_reason") if analysis.get("ai_reason") else "Smart Follow-up",
                "urgency_score": analysis.get("urgency_score", 0),
                "created_at": c["created_at"]
            })
    
    # Then, add customers that need attention but don't have analysis yet
    customers_without_analysis = await db.customers.find({
        "user_id": business_id,
        "$and": [
            {"$or": [{"is_customer": True}, {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}]},
            {"$or": [{"last_contacted": {"$lt": cutoff_date}}, {"last_contacted": None}, {"last_contacted": {"$exists": False}}]},
        ],
    }).sort("last_contacted", 1).to_list(100)
    
    for c in customers_without_analysis:
        # Skip if already added from analysis
        if c["_id"] in analyzed_customer_ids:
            continue
            
        pending_followup = await db.followups.find_one({"customer_id": c["_id"], "status": "pending"})
        days_since_contact = (datetime.utcnow() - c["last_contacted"]).days if c.get("last_contacted") else None
        
        # Use simple rule-based reason to avoid timeout
        ai_reason = generate_simple_reason(c, days_since_contact)
            
        result.append({
            "id": c["_id"], "name": c["name"], "phone_number": c["phone_number"],
            "notes": c.get("notes"), "tags": c.get("tags", []),
            "last_message": c.get("last_message"), "last_contacted": c.get("last_contacted"),
            "days_since_contact": days_since_contact, "has_pending_followup": pending_followup is not None,
            "ai_reason": ai_reason, "created_at": c["created_at"]
        })
            
    # Sort by urgency/days and limit to top 30 most urgent
    result.sort(key=lambda x: x.get("urgency_score", 0) if "urgency_score" in x else (x["days_since_contact"] if x["days_since_contact"] else 999), reverse=True)
    return serialize_doc(result[:30])  # Only return top 30 most urgent customers

@api_router.get("/customers/cold-with-reasons")
async def get_cold_customers_with_ai_reasons(days: int = 14, user = Depends(get_current_user)):
    """Alias for get_cold_customers to support frontend with reasons included"""
    return await get_cold_customers(days, user)

@api_router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str, user = Depends(get_current_user)):
    """Get a specific customer"""
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    return CustomerResponse(
        id=customer["_id"],
        user_id=customer["user_id"],
        name=customer["name"],
        phone_number=customer["phone_number"],
        notes=customer.get("notes"),
        tags=customer.get("tags", []),
        last_message=customer.get("last_message"),
        last_contacted=customer.get("last_contacted"),
        profile_picture=customer.get("profile_picture"),
        auto_reply=customer.get("auto_reply"),
        is_personal=customer.get("is_personal", False),
        ai_enabled=customer.get("ai_enabled", not customer.get("is_personal", False)),
        contact_type=customer.get("contact_type", "UNKNOWN"),
        is_customer=customer.get("is_customer", False),
        created_at=customer["created_at"]
    )

@api_router.post("/customers/{customer_id}/promote")
async def promote_to_customer(customer_id: str, user = Depends(get_current_user)):
    """Promote a contact to a confirmed customer"""
    business_id = user.get("business_id", user["_id"])
    await db.customers.update_one(
        {"_id": customer_id, "user_id": business_id},
        {"$set": {
            "classification_type": "customer",
            "classification_confirmed": True,
            "classified_at": datetime.utcnow(),
        }, "$pull": {"tags": "Supplier"}}
    )
    return {"status": "success"}

@api_router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(customer_id: str, update: CustomerUpdate, user = Depends(get_current_user)):
    """Update a customer"""
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    update_data = {}
    if update.name is not None:
        update_data["name"] = sanitize_string(update.name, 200)
    if update.notes is not None:
        update_data["notes"] = sanitize_string(update.notes, 2000)
    if update.tags is not None:
        update_data["tags"] = [sanitize_string(t, 50) for t in update.tags if t.strip()][:20]
    if update.auto_reply is not None:
        update_data["auto_reply"] = update.auto_reply
    if update.is_personal is not None:
        update_data["is_personal"] = update.is_personal
        # User requested AI to continue chatting when personal button is clicked
        if update.is_personal is True:
            if update.ai_enabled is None:
                update_data["ai_enabled"] = True
            update_data["contact_type"] = "KNOWN_PERSONAL"
            update_data["contact_type_source"] = "owner_tagged"
        elif update.is_personal is False:
            if update.ai_enabled is None:
                update_data["ai_enabled"] = True
            update_data["contact_type"] = "KNOWN_CUSTOMER"
            update_data["contact_type_source"] = "owner_tagged"
    if update.ai_enabled is not None:
        update_data["ai_enabled"] = update.ai_enabled
    if update.stage is not None:
        valid_stages = ["lead", "contacted", "negotiating", "won", "lost"]
        if update.stage in valid_stages:
            update_data["stage"] = update.stage
        
    if update_data:
        await db.customers.update_one({"_id": customer_id}, {"$set": update_data})
    
    updated = await db.customers.find_one({"_id": customer_id})
    
    return CustomerResponse(
        id=updated["_id"],
        user_id=updated["user_id"],
        name=updated["name"],
        phone_number=updated["phone_number"],
        notes=updated.get("notes"),
        tags=updated.get("tags", []),
        auto_reply=updated.get("auto_reply"),
        is_personal=updated.get("is_personal", False),
        ai_enabled=updated.get("ai_enabled", not updated.get("is_personal", False)),
        contact_type=updated.get("contact_type", "UNKNOWN"),
        is_customer=updated.get("is_customer", False),
        stage=updated.get("stage", "lead"),
        last_message=updated.get("last_message"),
        last_contacted=updated.get("last_contacted"),
        profile_picture=updated.get("profile_picture"),
        created_at=updated["created_at"]
    )


@api_router.post("/customers/{customer_id}/toggle-ai")
async def toggle_ai_for_contact(customer_id: str, user = Depends(get_current_user)):
    """16.5: Toggle AI on/off for a contact. Personal contacts are silent by default.
    This is the personal/business switch button endpoint."""
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    current_ai_enabled = customer.get("ai_enabled", not customer.get("is_personal", False))
    new_ai_enabled = not current_ai_enabled

    await db.customers.update_one(
        {"_id": customer_id, "user_id": business_id},
        {"$set": {
            "ai_enabled": new_ai_enabled,
            "contact_type_source": "owner_tagged",
        }}
    )
    return {
        "status": "success",
        "ai_enabled": new_ai_enabled,
        "message": "AI enabled for this contact" if new_ai_enabled else "AI silenced for this contact",
    }


@api_router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, user = Depends(get_current_user)):
    """Delete a customer"""
    business_id = user.get("business_id", user["_id"])
    result = await db.customers.delete_one({"_id": customer_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"status": "success", "message": "Customer deleted"}

# ============ FOLLOW-UP ENDPOINTS ============

@api_router.post("/followups", response_model=FollowUpResponse)
async def create_followup(followup: FollowUpCreate, user = Depends(get_current_user)):
    """Create a follow-up reminder"""
    business_id = user.get("business_id", user["_id"])
    # Verify customer exists
    customer = await db.customers.find_one({"_id": followup.customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    followup_id = str(uuid.uuid4())
    followup_doc = {
        "_id": followup_id,
        "user_id": business_id,
        "customer_id": followup.customer_id,
        "reminder_date": followup.reminder_date,
        "message": followup.message,
        "status": "pending",
        "type": followup.type,
        "created_at": datetime.utcnow()
    }
    
    await db.followups.insert_one(followup_doc)
    
    return FollowUpResponse(
        id=followup_id,
        user_id=business_id,
        customer_id=followup.customer_id,
        customer_name=customer["name"],
        customer_phone=customer["phone_number"],
        reminder_date=followup.reminder_date,
        message=followup.message,
        status="pending",
        type=followup.type,
        created_at=followup_doc["created_at"]
    )

@api_router.get("/followups", response_model=List[FollowUpResponse])
async def get_followups(status: Optional[str] = None, user = Depends(get_current_user)):
    """Get all follow-ups for current user"""
    business_id = user.get("business_id", user["_id"])
    query = {"user_id": business_id}
    if status:
        query["status"] = status
    
    followups = await db.followups.find(query).sort("reminder_date", 1).to_list(1000)
    if not followups:
        return []

    # Batch fetch all customers in one query (fixes N+1)
    customer_ids = list({f["customer_id"] for f in followups})
    customers_list = await db.customers.find({"_id": {"$in": customer_ids}}).to_list(None)
    customers_map = {c["_id"]: c for c in customers_list}

    result = []
    for f in followups:
        customer = customers_map.get(f["customer_id"])
        result.append(FollowUpResponse(
            id=f["_id"],
            user_id=f["user_id"],
            customer_id=f["customer_id"],
            customer_name=customer["name"] if customer else "Unknown",
            customer_phone=customer["phone_number"] if customer else None,
            reminder_date=f["reminder_date"],
            message=f.get("message"),
            status=f["status"],
            type=f.get("type", "call"),
            outcome=f.get("outcome"),
            outcome_note=f.get("outcome_note"),
            created_at=f["created_at"]
        ))
    
    return result

@api_router.put("/followups/{followup_id}", response_model=FollowUpResponse)
async def update_followup(followup_id: str, update: FollowUpUpdate, user = Depends(get_current_user)):
    """Update a follow-up"""
    business_id = user.get("business_id", user["_id"])
    followup = await db.followups.find_one({"_id": followup_id, "user_id": business_id})
    if not followup:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    
    update_data = {k: v for k, v in update.dict().items() if v is not None}
    if update_data:
        await db.followups.update_one({"_id": followup_id}, {"$set": update_data})
    
    updated = await db.followups.find_one({"_id": followup_id})
    customer = await db.customers.find_one({"_id": updated["customer_id"]})
    
    return FollowUpResponse(
        id=updated["_id"],
        user_id=updated["user_id"],
        customer_id=updated["customer_id"],
        customer_name=customer["name"] if customer else "Unknown",
        customer_phone=customer["phone_number"] if customer else None,
        reminder_date=updated["reminder_date"],
        message=updated.get("message"),
        status=updated["status"],
        type=updated.get("type", "call"),
        outcome=updated.get("outcome"),
        outcome_note=updated.get("outcome_note"),
        created_at=updated["created_at"]
    )

@api_router.delete("/followups/{followup_id}")
async def delete_followup(followup_id: str, user = Depends(get_current_user)):
    """Delete a follow-up"""
    business_id = user.get("business_id", user["_id"])
    result = await db.followups.delete_one({"_id": followup_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return {"status": "success", "message": "Follow-up deleted"}

@api_router.post("/followups/{followup_id}/snooze")
async def snooze_followup(followup_id: str, days: int = 1, user = Depends(get_current_user)):
    """
    Snooze a follow-up by X days
    Common options: 1 day, 3 days, 7 days
    """
    business_id = user.get("business_id", user["_id"])
    followup = await db.followups.find_one({"_id": followup_id, "user_id": business_id})
    if not followup:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    
    # Calculate new date
    current_date = followup.get("reminder_date", datetime.utcnow())
    new_date = current_date + timedelta(days=days)
    
    # Update follow-up
    await db.followups.update_one(
        {"_id": followup_id},
        {"$set": {"reminder_date": new_date}}
    )
    
    return {
        "status": "success",
        "message": f"Follow-up snoozed for {days} day(s)",
        "new_date": new_date
    }

@api_router.post("/followup-events")
async def record_followup_event(
    customer_id: str = Body(...),
    outcome: str = Body(...),  # called, replied, converted, no_answer, rescheduled, not_interested
    note: Optional[str] = Body(None),
    user = Depends(get_current_user)
):
    """Record a manual follow-up outcome for a cold/needs-attention customer"""
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    event = {
        "_id": str(uuid.uuid4()),
        "user_id": business_id,
        "customer_id": customer_id,
        "customer_name": customer.get("name", "Unknown"),
        "outcome": outcome,
        "note": note,
        "source": "needs_attention",
        "created_at": datetime.utcnow(),
    }
    await db.followup_events.insert_one(event)

    # Update last_contacted so they drop off Needs Attention
    await db.customers.update_one(
        {"_id": customer_id},
        {"$set": {"last_contacted": datetime.utcnow()}}
    )
    return {"status": "ok", "id": event["_id"]}


@api_router.get("/followups/analytics")
async def get_followup_analytics(days: int = 30, user = Depends(get_current_user)):
    """
    Get follow-up success metrics for analytics dashboard
    Automatically tracks: conversions, responses, timing
    Also includes needs-attention contact events
    """
    business_id = user.get("business_id", user["_id"])
    analytics = get_analytics(db)
    stats = await analytics.get_followup_stats(user["_id"], days)
    best_times = await analytics.get_best_followup_times(user["_id"])

    # Pull manual followup_events (from Needs Attention "Done" button)
    cutoff = datetime.utcnow() - timedelta(days=days)
    events = await db.followup_events.find({
        "user_id": business_id,
        "created_at": {"$gte": cutoff}
    }).to_list(1000)

    # Aggregate outcome counts across both reminders (followups) and needs-attention events
    # Start from completed followups outcome field
    completed_followups = await db.followups.find({
        "user_id": business_id,
        "status": "completed",
        "reminder_date": {"$gte": cutoff}
    }).to_list(1000)

    outcome_counts: dict = {}
    for f in completed_followups:
        o = f.get("outcome")
        if o:
            outcome_counts[o] = outcome_counts.get(o, 0) + 1

    for e in events:
        o = e.get("outcome")
        if o:
            outcome_counts[o] = outcome_counts.get(o, 0) + 1

    # Merge event totals into stats
    events_total = len(events)
    stats["needs_attention_contacted"] = events_total
    stats["total_all"] = stats.get("total_followups", 0) + events_total

    return {
        "stats": stats,
        "best_times": best_times,
        "outcome_counts": outcome_counts,
    }

@api_router.get("/stats/followup-suggestions")
async def get_followup_suggestions(user = Depends(get_current_user)):
    """Get follow-up suggestion counts for the follow-ups tab header stats"""
    business_id = user.get("business_id", user["_id"])
    now = datetime.utcnow()
    cutoff_week = now - timedelta(days=7)
    cutoff_month = now - timedelta(days=30)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Real customers only — use $and to safely combine two $or conditions
    _is_customer = {"$or": [{"is_customer": True}, {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}]}
    _no_contact_week = {"$or": [{"last_contacted": {"$lt": cutoff_week}}, {"last_contacted": None}, {"last_contacted": {"$exists": False}}]}
    _no_contact_month = {"$or": [{"last_contacted": {"$lt": cutoff_month}}, {"last_contacted": None}, {"last_contacted": {"$exists": False}}]}
    
    # Count today's analyzed customers that need attention (respects random daily quota)
    analyzed_count = 0
    smart_insights = await db.customer_analysis.find({
        "user_id": business_id,
        "analysis_date": {"$gte": today}
    }).to_list(100)
    
    for analysis in smart_insights:
        c = await db.customers.find_one({"_id": analysis["customer_id"]})
        if c:
            last_contacted = c.get("last_contacted")
            # Only count if they actually need attention (>7 days or never)
            if not last_contacted or last_contacted < cutoff_week:
                analyzed_count += 1
    
    # Count non-analyzed customers that still need attention
    non_analyzed_customers = await db.customers.find({
        "user_id": business_id,
        "$and": [_is_customer, _no_contact_week]
    }).to_list(100)
    
    analyzed_ids = {a["customer_id"] for a in smart_insights}
    non_analyzed_count = sum(1 for c in non_analyzed_customers if c["_id"] not in analyzed_ids)
    
    # Total shown in Needs Attention list = analyzed + non-analyzed (up to 30 max per endpoint)
    neglected_week = min(analyzed_count + non_analyzed_count, 30)
    
    # Customers not contacted in 30+ days (or never) - keep original logic
    neglected_month = await db.customers.count_documents({
        "user_id": business_id,
        "$and": [_is_customer, _no_contact_month]
    })
    # New customers (created in last 7 days) with no follow-up
    new_cutoff = now - timedelta(days=7)
    new_customers = await db.customers.find({
        "user_id": business_id,
        "$and": [_is_customer, {"created_at": {"$gte": new_cutoff}}]
    }).to_list(None)
    new_no_followup = 0
    for c in new_customers:
        has_fu = await db.followups.find_one({"customer_id": c["_id"], "status": "pending"})
        if not has_fu:
            new_no_followup += 1
    # VIP customers not contacted in 7+ days
    vip_neglected = await db.customers.count_documents({
        "user_id": business_id,
        "tags": "VIP",
        "$and": [
            _is_customer,
            {"$or": [{"last_contacted": {"$lt": cutoff_week}}, {"last_contacted": None}]}
        ]
    })
    return {
        "neglected_week": neglected_week,
        "neglected_month": neglected_month,
        "new_no_followup": new_no_followup,
        "vip_neglected": vip_neglected,
        "total_needing_attention": neglected_week
    }

@api_router.get("/analytics/summary")
async def get_analytics_summary(user = Depends(get_current_user)):
    """
    Get quick analytics summary for menu/dashboard
    Shows key metrics at a glance
    """
    business_id = user.get("business_id", user["_id"])
    analytics = get_analytics(db)

    # Follow-up stats
    try:
        stats_30d = await analytics.get_followup_stats(user["_id"], days=30)
        stats_7d = await analytics.get_followup_stats(user["_id"], days=7)
    except Exception as e:
        logging.error(f"followup stats error: {e}")
        stats_30d = {"conversion_rate": 0, "response_rate": 0, "total_revenue": 0, "total_followups": 0}
        stats_7d = {"conversion_rate": 0, "total_followups": 0, "total_revenue": 0}

    # Smart insight
    try:
        smart_notif = get_smart_notifications(db)
        insight = await smart_notif.get_meaningful_insights(user["_id"])
    except Exception as e:
        logging.error(f"insight error: {e}")
        insight = None

    # Top products from orders
    try:
        top_products = await analytics.get_product_insights(user["_id"], days=30)
    except Exception as e:
        logging.error(f"top products error: {e}")
        top_products = []

    # Best followup times
    try:
        best_times = await analytics.get_best_followup_times(user["_id"])
    except Exception as e:
        logging.error(f"best times error: {e}")
        best_times = {"best_day": "Monday", "best_hour": 10, "sample_size": 0}

    # Top selling items from sales (last 30 days)
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        sales_pipeline = [
            {"$match": {"user_id": business_id, "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$item", "total_revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
            {"$sort": {"total_revenue": -1}},
            {"$limit": 5}
        ]
        top_items_raw = await db.sales.aggregate(sales_pipeline).to_list(5)
        top_items = [{"name": r["_id"], "count": r["count"], "revenue": r["total_revenue"]} for r in top_items_raw]
    except Exception as e:
        logging.error(f"top items error: {e}")
        top_items = []

    # Best days of week from sales
    try:
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        all_sales = await db.sales.find({"user_id": business_id, "created_at": {"$gte": cutoff}}).to_list(1000)
        day_revenue = {}
        for s in all_sales:
            dow = s["created_at"].weekday()
            day_revenue[dow] = day_revenue.get(dow, 0) + s.get("amount", 0)
        best_days = sorted(
            [{"day": day_names[k], "revenue": v} for k, v in day_revenue.items()],
            key=lambda x: x["revenue"], reverse=True
        )
    except Exception as e:
        logging.error(f"best days error: {e}")
        best_days = []

    # Customers
    try:
        total_customers = await db.customers.count_documents({"user_id": business_id, "is_customer": True})
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        new_customers = await db.customers.count_documents({"user_id": business_id, "is_customer": True, "created_at": {"$gte": month_start}})
    except Exception as e:
        logging.error(f"customers error: {e}")
        total_customers = 0
        new_customers = 0

    # Currency from owner settings
    try:
        owner = await db.users.find_one({"_id": business_id})
        currency = (owner or user).get("currency", "USD")
    except Exception:
        currency = user.get("currency", "USD")

    return {
        "currency": currency,
        "last_30_days": {
            "conversion_rate": round(stats_30d["conversion_rate"], 1),
            "response_rate": round(stats_30d["response_rate"], 1),
            "total_revenue": stats_30d["total_revenue"],
            "followups": stats_30d["total_followups"]
        },
        "last_7_days": {
            "conversion_rate": round(stats_7d["conversion_rate"], 1),
            "followups": stats_7d["total_followups"],
            "revenue": stats_7d.get("total_revenue", 0)
        },
        "top_products": top_products,
        "top_items": top_items,
        "best_days": best_days,
        "best_times": best_times,
        "customers": {"total": total_customers, "new_this_month": new_customers},
        "insight": insight
    }

@api_router.get("/analytics/stock")
async def get_stock_analytics(user = Depends(get_current_user)):
    """Get stock analytics: low stock, out of stock, total inventory value"""
    business_id = user.get("business_id", user["_id"])
    products = await db.products.find({"user_id": business_id}).to_list(1000)

    total_products = len(products)
    out_of_stock = []
    low_stock = []
    total_value = 0.0
    in_stock_count = 0

    for p in products:
        sq = p.get("stock_quantity")
        price = p.get("price") or 0
        name = p.get("name", "Unknown")
        category = p.get("category", "Other")

        if not p.get("in_stock", True):
            out_of_stock.append({"name": name, "category": category})
        elif sq is not None:
            if sq == 0:
                out_of_stock.append({"name": name, "category": category, "stock_quantity": 0})
            elif sq <= 5:
                low_stock.append({"name": name, "category": category, "stock_quantity": sq})
            else:
                in_stock_count += 1
            total_value += sq * price
        else:
            in_stock_count += 1

    return {
        "total_products": total_products,
        "in_stock_count": in_stock_count,
        "out_of_stock_count": len(out_of_stock),
        "low_stock_count": len(low_stock),
        "total_inventory_value": round(total_value, 2),
        "out_of_stock": out_of_stock[:10],
        "low_stock": low_stock[:10],
    }

@api_router.post("/notifications/test-smart")
async def test_smart_notification(user = Depends(get_current_user)):
    """
    Test smart notification system
    Sends notification only if there's something meaningful
    """
    smart_notif = get_smart_notifications(db)
    sent = await smart_notif.send_smart_notification(user["_id"])
    
    if sent:
        return {"status": "sent", "message": "Smart notification sent"}
    else:
        return {"status": "skipped", "message": "No meaningful insight or too frequent"}

# ============ SALES/RECEIPT ENDPOINTS ============

@api_router.post("/sales", response_model=SaleResponse)
async def create_sale(sale: SaleCreate, background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    """Record a sale and optionally send receipt"""
    business_id = user.get("business_id", user["_id"])
    # Handle walk-in customers
    is_walk_in = sale.customer_id == 'walk-in'
    
    if not is_walk_in:
        # Verify customer exists for regular sales
        customer = await db.customers.find_one({"_id": sale.customer_id, "user_id": business_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
    else:
        # Create placeholder for walk-in customer
        customer = {
            "name": "Walk-in Customer",
            "phone_number": "N/A"
        }
    
    sale_id = str(uuid.uuid4())
    
    # Set payment method to "Credit" if this is a credit sale
    payment_method = sale.payment_method
    if sale.is_credit and not payment_method:
        payment_method = "Credit"
    
    sale_doc = {
        "_id": sale_id,
        "user_id": business_id,
        "recorded_by": user["_id"],
        "customer_id": sale.customer_id,
        "item": sale.item,
        "amount": sale.amount,
        "payment_method": payment_method,
        "receipt_sent": False,
        "is_credit": sale.is_credit,
        "due_date": sale.due_date,
        "paid_date": sale.paid_date,
        "created_at": datetime.utcnow()
    }
    
    await db.sales.insert_one(sale_doc)
    
    # Update customer tag to "Returning" if was "New"
    update_ops = {
        "$inc": {"purchase_count": 1, "total_spent": sale.amount},
        "$set": {"last_contacted": datetime.utcnow()}
    }
    
    if "New" in customer.get("tags", []):
        new_tags = [t for t in customer.get("tags", []) if t != "New"]
        new_tags.append("Returning")
        update_ops["$set"]["tags"] = new_tags
        
    await db.customers.update_one(
        {"_id": sale.customer_id},
        update_ops
    )
    
    # Send receipt via WhatsApp (background task)
    # Use business_id (owner) for WhatsApp instance, since team members don't have their own instance
    if sale.send_receipt:
        owner = await db.users.find_one({"_id": business_id}) if business_id != user["_id"] else user
        currency = (owner or user).get("currency", "USD")
        business_name = (owner or user).get("business_name", user.get("business_name", "Your Shop"))
        background_tasks.add_task(
            send_receipt_message,
            customer["phone_number"],
            customer["name"],
            sale.item,
            sale.amount,
            business_name,
            sale_id,
            sale.receipt_message,
            currency,
            business_id
        )
    
    return SaleResponse(
        id=sale_id,
        user_id=business_id,
        customer_id=sale.customer_id,
        customer_name=customer["name"],
        customer_phone=customer["phone_number"],
        item=sale.item,
        amount=sale.amount,
        payment_method=payment_method,
        receipt_sent=sale.send_receipt,
        is_credit=sale.is_credit,
        due_date=sale.due_date,
        paid_date=sale.paid_date,
        created_at=sale_doc["created_at"]
    )

@api_router.put("/sales/{sale_id}/mark-paid")
async def mark_sale_as_paid(sale_id: str, payment_method: str, user = Depends(get_current_user)):
    """Mark a credit sale as paid"""
    business_id = user.get("business_id", user["_id"])
    # Verify sale exists and belongs to user
    sale = await db.sales.find_one({"_id": sale_id, "user_id": business_id})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    
    if not sale.get("is_credit"):
        raise HTTPException(status_code=400, detail="This is not a credit sale")
    
    if sale.get("paid_date"):
        raise HTTPException(status_code=400, detail="Sale already marked as paid")
    
    # Update sale to mark as paid
    await db.sales.update_one(
        {"_id": sale_id},
        {
            "$set": {
                "paid_date": datetime.utcnow().isoformat(),
                "payment_method": payment_method
            }
        }
    )
    
    return {"message": "Sale marked as paid", "paid_date": datetime.utcnow().isoformat()}

async def send_receipt_message(phone: str, name: str, item: str, amount: float, business: str, sale_id: str, custom_message: Optional[str] = None, currency: str = "USD", user_id: Optional[str] = None):
    """Send receipt via WhatsApp (Evolution API)"""
    try:
        if custom_message:
            message = custom_message
        else:
            message = f"""✅ Payment received
Item: {item}
Amount: {currency} {amount:,.0f}
Thank you for shopping with {business} 🙏"""
        
        if user_id:
            whatsapp_service = get_whatsapp_service(db)
            await whatsapp_service.send_message(
                user_id=user_id,
                to_number=phone,
                message=message,
                customer_name=name,
                send_context="auto_reply",
            )
        
        # Update receipt status
        await db.sales.update_one({"_id": sale_id}, {"$set": {"receipt_sent": True}})
    except Exception as e:
        logging.error(f"Failed to send receipt: {e}")

@api_router.get("/sales", response_model=List[SaleResponse])
async def get_sales(user = Depends(get_current_user)):
    """Get all sales for current user. Employees see only their own; owner/manager see all."""
    try:
        business_id = user.get("business_id", user["_id"])
        user_role = user.get("role", "owner")
        query = {"user_id": business_id}
        if user_role == "employee":
            query["recorded_by"] = user["_id"]
        sales = await db.sales.find(query).sort("created_at", -1).to_list(1000)
        
        result = []
        for s in sales:
            try:
                customer = await db.customers.find_one({"_id": s.get("customer_id")})
                result.append(SaleResponse(
                    id=s["_id"],
                    user_id=s["user_id"],
                    customer_id=s.get("customer_id", ""),
                    customer_name=customer.get("name") if customer else "Unknown",
                    customer_phone=customer.get("phone_number") if customer else None,
                    item=s.get("item", ""),
                    amount=s.get("amount", 0),
                    payment_method=s.get("payment_method", ""),
                    receipt_sent=s.get("receipt_sent", False),
                    is_credit=s.get("is_credit", False),
                    due_date=s.get("due_date"),
                    paid_date=s.get("paid_date"),
                    created_at=s.get("created_at")
                ))
            except Exception as sale_err:
                logging.error(f"Error processing sale {s.get('_id')}: {sale_err}")
                continue
        
        return result
    except Exception as e:
        logging.error(f"Error in get_sales endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch sales: {str(e)}")

@api_router.get("/revenue", response_model=List[SaleResponse])
async def get_revenue(user = Depends(get_current_user)):
    """Unified revenue: sales + paid bookings combined and sorted by date."""
    business_id = user.get("business_id", user["_id"])
    result = []

    # 1. Regular sales
    sales = await db.sales.find({"user_id": business_id}).sort("created_at", -1).to_list(1000)
    for s in sales:
        try:
            customer = await db.customers.find_one({"_id": s.get("customer_id")})
            result.append(SaleResponse(
                id=s["_id"], user_id=s["user_id"],
                customer_id=s.get("customer_id", ""),
                customer_name=customer.get("name") if customer else s.get("customer_name", "Unknown"),
                customer_phone=customer.get("phone_number") if customer else None,
                item=s.get("item", ""), amount=s.get("amount", 0),
                payment_method=s.get("payment_method", ""),
                receipt_sent=s.get("receipt_sent", False),
                is_credit=s.get("is_credit", False),
                due_date=s.get("due_date"), paid_date=s.get("paid_date"),
                created_at=s.get("created_at"), source="sale"
            ))
        except Exception:
            continue

    # 2. Paid bookings
    paid_bookings = await db.bookings.find(
        {"user_id": business_id, "payment_status": "paid"}
    ).sort("date", -1).to_list(1000)
    for b in paid_bookings:
        try:
            # Use the booking date as created_at for sorting
            booking_dt = datetime.strptime(f"{b['date']} {b.get('time', '00:00')}", "%Y-%m-%d %H:%M")
            result.append(SaleResponse(
                id=b["_id"], user_id=b["user_id"],
                customer_id=b.get("customer_id", ""),
                customer_name=b.get("customer_name", "Customer"),
                customer_phone=b.get("customer_phone"),
                item=b.get("service_name", "Appointment"),
                amount=b.get("price", 0),
                payment_method=b.get("payment_method", "Cash"),
                receipt_sent=False, is_credit=False,
                created_at=booking_dt, source="booking"
            ))
        except Exception:
            continue

    # Sort combined list by date descending
    result.sort(key=lambda x: x.created_at, reverse=True)
    return result


@api_router.get("/sales/by-employee")
async def get_sales_by_employee(user = Depends(get_current_user)):
    """Get sales totals grouped by employee (owner/manager only)"""
    business_id = user.get("business_id", user["_id"])

    pipeline = [
        {"$match": {"user_id": business_id}},
        {"$group": {
            "_id": "$recorded_by",
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"total": -1}}
    ]
    rows = await db.sales.aggregate(pipeline).to_list(100)

    result = []
    for row in rows:
        uid = row["_id"]
        member = await db.team_members.find_one({"user_id": uid, "business_id": business_id})
        name = member["name"] if member else "Owner"
        result.append({
            "user_id": uid,
            "name": name,
            "total": row["total"],
            "count": row["count"]
        })
    return result

@api_router.post("/sales/{sale_id}/resend-receipt")
async def resend_receipt(sale_id: str, background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    """Resend receipt for a sale"""
    business_id = user.get("business_id", user["_id"])
    sale = await db.sales.find_one({"_id": sale_id, "user_id": business_id})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    
    customer = await db.customers.find_one({"_id": sale["customer_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Send receipt via WhatsApp (background task)
    background_tasks.add_task(
        send_receipt_message,
        customer["phone_number"],
        customer["name"],
        sale["item"],
        sale["amount"],
        user.get("business_name", "Your Shop"),
        sale_id
    )
    
    return {"status": "success", "message": "Receipt sent"}

# ============ ORDER ENDPOINTS ============

@api_router.post("/orders", response_model=OrderResponse)
async def create_order(order: OrderCreate, user = Depends(get_current_user)):
    """Create a new order"""
    business_id = user.get("business_id", user["_id"])
    # Handle walk-in customers
    is_walk_in = order.customer_id == 'walk-in'
    
    if not is_walk_in:
        # Verify customer exists
        customer = await db.customers.find_one({"_id": order.customer_id, "user_id": business_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
    else:
        # Create placeholder for walk-in customer
        customer = {
            "name": "Walk-in Customer",
            "phone_number": "N/A"
        }
    
    order_id = str(uuid.uuid4())
    
    order_doc = {
        "_id": order_id,
        "user_id": business_id,
        "recorded_by": user["_id"],
        "customer_id": order.customer_id,
        "product": order.product,
        "quantity": order.quantity,
        "price": order.price,
        "total_amount": order.total_amount,
        "payment_status": order.payment_status,
        "delivery_status": order.delivery_status,
        "notes": order.notes,
        "due_date": order.due_date,
        "created_at": datetime.utcnow()
    }
    
    # Reduce stock if matching product is found and quantity is tracked
    await db.products.update_one(
        {
            "user_id": business_id, 
            "name": order.product, 
            "stock_quantity": {"$exists": True, "$ne": None},
            "stock_quantity": {"$gte": order.quantity}
        },
        {"$inc": {"stock_quantity": -order.quantity}}
    )

    await db.orders.insert_one(order_doc)
    
    # Handle created_at safely
    created_at_val = order_doc["created_at"]
    if isinstance(created_at_val, datetime):
        created_at_str = created_at_val.isoformat()
    else:
        created_at_str = created_at_val
    
    return OrderResponse(
        id=order_id,
        customer_id=order.customer_id,
        customer_name=customer["name"],
        customer_phone=customer["phone_number"],
        product=order.product,
        quantity=order.quantity,
        price=order.price,
        total_amount=order.total_amount,
        payment_status=order.payment_status,
        delivery_status=order.delivery_status,
        notes=order.notes,
        due_date=order.due_date,
        created_at=created_at_str
    )

@api_router.get("/orders", response_model=List[OrderResponse])
async def get_orders(user = Depends(get_current_user)):
    """Get all orders for the current user. Employees see only their own; owner/manager see all."""
    business_id = user.get("business_id", user["_id"])
    user_role = user.get("role", "owner")
    query = {"user_id": business_id}
    if user_role == "employee":
        query["recorded_by"] = user["_id"]
    orders = await db.orders.find(query).sort("created_at", -1).to_list(None)
    
    result = []
    for order in orders:
        try:
            # Get customer info
            if order.get("customer_id") == "walk-in":
                customer_name = "Walk-in Customer"
                customer_phone = "N/A"
            else:
                customer = await db.customers.find_one({"_id": order.get("customer_id")})
                customer_name = customer["name"] if customer else "Unknown"
                customer_phone = customer.get("phone_number", "N/A") if customer else "N/A"
            
            # Handle created_at field safely
            created_at_value = order.get("created_at")
            if isinstance(created_at_value, datetime):
                created_at_str = created_at_value.isoformat()
            elif isinstance(created_at_value, str):
                created_at_str = created_at_value
            else:
                created_at_str = datetime.utcnow().isoformat()
            
            result.append(OrderResponse(
                id=order["_id"],
                customer_id=order.get("customer_id", ""),
                customer_name=customer_name,
                customer_phone=customer_phone,
                product=order.get("product", ""),
                quantity=order.get("quantity", 1),
                price=order.get("price", 0),
                total_amount=order.get("total_amount", 0),
                payment_status=order.get("payment_status", "unpaid"),
                delivery_status=order.get("delivery_status", "pending"),
                status=order.get("status", "pending"),
                notes=order.get("notes"),
                due_date=order.get("due_date"),
                created_at=created_at_str
            ))
        except Exception as e:
            # Log error but continue processing other orders
            print(f"[ERROR] Failed to process order {order.get('_id', 'unknown')}: {str(e)}")
            continue
    
    return result

@api_router.put("/orders/{order_id}", response_model=OrderResponse)
async def update_order(order_id: str, payment_status: Optional[str] = None, delivery_status: Optional[str] = None, notes: Optional[str] = None, user = Depends(get_current_user)):
    """Update order payment status, delivery status, or notes"""
    try:
        business_id = user.get("business_id", user["_id"])
        # Verify order exists
        order = await db.orders.find_one({"_id": order_id, "user_id": business_id})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Build update operations
        update_ops = {}
        if payment_status:
            update_ops["payment_status"] = payment_status
        if delivery_status:
            update_ops["delivery_status"] = delivery_status
        if notes is not None:
            update_ops["notes"] = notes
        
        if update_ops:
            await db.orders.update_one(
                {"_id": order_id},
                {"$set": update_ops}
            )
            # Refresh order data
            order = await db.orders.find_one({"_id": order_id})
        
        # Get customer info
        if order["customer_id"] == "walk-in":
            customer_name = "Walk-in Customer"
            customer_phone = "N/A"
        else:
            customer = await db.customers.find_one({"_id": order["customer_id"]})
            customer_name = customer["name"] if customer else "Unknown"
            customer_phone = customer["phone_number"] if customer else "N/A"
        
        # Handle created_at - could be string or datetime
        created_at_str = order["created_at"]
        if isinstance(created_at_str, datetime):
            created_at_str = created_at_str.isoformat()
        
        return OrderResponse(
            id=order["_id"],
            customer_id=order.get("customer_id", ""),
            customer_name=customer_name,
            customer_phone=customer_phone,
            product=order.get("product") or order.get("item") or order.get("product_name") or "Unknown",
            quantity=order.get("quantity", 1),
            price=order.get("price", 0),
            total_amount=order.get("total_amount") or order.get("amount", 0),
            payment_status=order.get("payment_status", "Pending"),
            delivery_status=order.get("delivery_status", "Processing"),
            notes=order.get("notes"),
            due_date=order.get("due_date"),
            created_at=created_at_str
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[UPDATE_ORDER] Error updating order {order_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update order: {str(e)}")

@api_router.delete("/orders/{order_id}")
async def delete_order(order_id: str, user = Depends(get_current_user)):
    """Delete an order"""
    business_id = user.get("business_id", user["_id"])
    result = await db.orders.delete_one({"_id": order_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": "Order deleted successfully"}

@api_router.post("/orders/{order_id}/convert-to-sale", response_model=SaleResponse)
async def convert_order_to_sale(order_id: str, payment_method: str, user = Depends(get_current_user)):
    """Convert a paid order to a sale"""
    business_id = user.get("business_id", user["_id"])
    # Verify order exists
    order = await db.orders.find_one({"_id": order_id, "user_id": business_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order["payment_status"] != "Paid":
        raise HTTPException(status_code=400, detail="Only paid orders can be converted to sales")
    
    # Get customer info
    if order["customer_id"] == "walk-in":
        customer_name = "Walk-in Customer"
        customer_phone = "N/A"
    else:
        customer = await db.customers.find_one({"_id": order["customer_id"]})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer_name = customer["name"]
        customer_phone = customer["phone_number"]
    
    # Create sale
    sale_id = str(uuid.uuid4())
    sale_doc = {
        "_id": sale_id,
        "user_id": business_id,
        "recorded_by": user["_id"],
        "customer_id": order["customer_id"],
        "item": order["product"],
        "amount": order["total_amount"],
        "payment_method": payment_method,
        "receipt_sent": False,
        "is_credit": False,
        "due_date": None,
        "paid_date": None,
        "created_at": datetime.utcnow()
    }
    
    await db.sales.insert_one(sale_doc)
    
    # Update customer stats (skip for walk-in)
    if order["customer_id"] != "walk-in":
        update_ops = {
            "$inc": {"purchase_count": 1, "total_spent": order["total_amount"]},
            "$set": {"last_contacted": datetime.utcnow()}
        }
        
        if customer.get("tag") == "New":
            update_ops["$set"]["tag"] = "Returning"
        
        await db.customers.update_one(
            {"_id": order["customer_id"]},
            update_ops
        )
    
    # Delete the order
    await db.orders.delete_one({"_id": order_id})
    
    return SaleResponse(
        id=sale_id,
        user_id=business_id,
        customer_id=order["customer_id"],
        customer_name=customer_name,
        customer_phone=customer_phone,
        item=order["product"],
        amount=order["total_amount"],
        payment_method=payment_method,
        receipt_sent=False,
        is_credit=False,
        due_date=None,
        paid_date=None,
        created_at=sale_doc["created_at"]
    )

async def send_order_payment_reminders():
    """Background task to send payment reminders for unpaid orders after 24 hours"""
    try:
        # Get orders created 24 hours ago that are still unpaid/partial
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        one_hour_buffer = datetime.utcnow() - timedelta(hours=23)  # 1-hour window
        
        # Find orders created ~24 hours ago with pending/partial payment
        unpaid_orders = await db.orders.find({
            "created_at": {
                "$gte": twenty_four_hours_ago,
                "$lte": one_hour_buffer
            },
            "payment_status": {"$in": ["Pending", "Partial"]},
            "customer_id": {"$ne": "walk-in"}  # Skip walk-in customers
        }).to_list(None)
        
        if not unpaid_orders:
            logging.info("No unpaid orders requiring reminders")
            return
        
        logging.info(f"Found {len(unpaid_orders)} unpaid orders for reminders")
        
        # Get notification service
        notif_service = get_notification_service()
        sent_count = 0
        
        for order in unpaid_orders:
            try:
                # Get user info for WhatsApp credentials
                user = await db.users.find_one({"_id": order["user_id"]})
                if not user:
                    continue
                
                # Get customer info
                customer = await db.customers.find_one({"_id": order["customer_id"]})
                if not customer:
                    continue
                
                # Prepare reminder message
                amount_paid = 0
                if order["payment_status"] == "Partial":
                    # You could track partial payments if needed
                    balance = order["total_amount"]
                else:
                    balance = order["total_amount"]
                
                message = f"""🔔 *Payment Reminder*

Hello {customer['name']}! 👋

This is a friendly reminder about your order:

📦 *Product:* {order['product']}
💰 *Amount:* {user_settings.get('currency', 'USD')} {order['total_amount']:,}
📊 *Status:* {order['payment_status']}

"""
                
                if order.get("due_date"):
                    due_date_str = datetime.fromisoformat(order["due_date"]).strftime("%B %d, %Y")
                    message += f"📅 *Due Date:* {due_date_str}\n"
                
                message += f"\nPlease complete your payment at your earliest convenience. Thank you! 🙏"
                
                # Send WhatsApp message
                success = await notif_service.send_whatsapp(
                    to_number=customer["phone_number"],
                    message=message,
                    user_id=user["_id"]
                )
                
                if success:
                    sent_count += 1
                    logging.info(f"Sent payment reminder for order {order['_id']} to {customer['name']}")
                    
                    # Mark that reminder was sent (optional: add a field to track this)
                    await db.orders.update_one(
                        {"_id": order["_id"]},
                        {"$set": {"reminder_sent": True, "reminder_sent_at": datetime.utcnow()}}
                    )
                else:
                    logging.warning(f"Failed to send reminder for order {order['_id']}")
                    
            except Exception as e:
                logging.error(f"Error sending reminder for order {order.get('_id')}: {e}")
                continue
        
        logging.info(f"Sent {sent_count} order payment reminders")
        
    except Exception as e:
        logging.error(f"Error in send_order_payment_reminders: {e}")

# ============ EXPENSE ENDPOINTS ============

@api_router.post("/expenses", response_model=ExpenseResponse)
async def create_expense(expense: ExpenseCreate, user = Depends(get_current_user)):
    """Record an expense"""
    business_id = user.get("business_id", user["_id"])
    expense_id = str(uuid.uuid4())
    expense_doc = {
        "_id": expense_id,
        "user_id": business_id,
        "recorded_by": user["_id"],
        "category": expense.category,
        "amount": expense.amount,
        "description": expense.description,
        "created_at": expense.date if expense.date else datetime.utcnow()
    }
    
    await db.expenses.insert_one(expense_doc)
    
    return ExpenseResponse(
        id=expense_id,
        user_id=business_id,
        category=expense.category,
        amount=expense.amount,
        description=expense.description,
        created_at=expense_doc["created_at"]
    )

@api_router.get("/expenses", response_model=List[ExpenseResponse])
async def get_expenses(user = Depends(get_current_user)):
    """Get all expenses for current user. Employees see only their own; owner/manager see all."""
    business_id = user.get("business_id", user["_id"])
    user_role = user.get("role", "owner")
    query = {"user_id": business_id}
    if user_role == "employee":
        query["recorded_by"] = user["_id"]
    expenses = await db.expenses.find(query).sort("created_at", -1).to_list(1000)
    
    return [
        ExpenseResponse(
            id=e["_id"],
            user_id=e["user_id"],
            category=e["category"],
            amount=e["amount"],
            description=e.get("description"),
            created_at=e["created_at"]
        )
        for e in expenses
    ]

@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, user = Depends(get_current_user)):
    """Delete an expense"""
    business_id = user.get("business_id", user["_id"])
    result = await db.expenses.delete_one({"_id": expense_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"status": "success", "message": "Expense deleted"}

# ============ BROADCAST ENDPOINTS ============


# ============ BROADCAST TEMPLATE ENDPOINTS ============

@api_router.post("/broadcast-templates", response_model=BroadcastTemplateResponse)
async def create_broadcast_template(template: BroadcastTemplateCreate, user = Depends(get_current_user)):
    """Create a reusable broadcast template"""
    business_id = user.get("business_id", user["_id"])
    template_id = str(uuid.uuid4())
    template_doc = {
        "_id": template_id,
        "user_id": business_id,
        "name": template.name,
        "message": template.message,
        "image_url": template.image_url,
        "created_at": datetime.utcnow()
    }
    
    await db.broadcast_templates.insert_one(template_doc)
    
    return BroadcastTemplateResponse(
        id=template_id,
        user_id=business_id,
        name=template.name,
        message=template.message,
        image_url=template.image_url,
        created_at=template_doc["created_at"]
    )

@api_router.get("/broadcast-templates", response_model=List[BroadcastTemplateResponse])
async def get_broadcast_templates(user = Depends(get_current_user)):
    """Get all broadcast templates for current user"""
    business_id = user.get("business_id", user["_id"])
    templates = await db.broadcast_templates.find({"user_id": business_id}).sort("created_at", -1).to_list(100)
    
    return [
        BroadcastTemplateResponse(
            id=t["_id"],
            user_id=t["user_id"],
            name=t["name"],
            message=t["message"],
            image_url=t.get("image_url"),
            created_at=t["created_at"]
        )
        for t in templates
    ]

@api_router.delete("/broadcast-templates/{template_id}")
async def delete_broadcast_template(template_id: str, user = Depends(get_current_user)):
    """Delete a broadcast template"""
    business_id = user.get("business_id", user["_id"])
    result = await db.broadcast_templates.delete_one({"_id": template_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "success", "message": "Template deleted"}

# ============ CUSTOMER GROUP ENDPOINTS ============

class CustomerGroupCreate(BaseModel):
    name: str
    customer_ids: List[str]

class CustomerGroupResponse(BaseModel):
    id: str
    user_id: str
    name: str
    customer_ids: List[str]
    count: int
    created_at: datetime

@api_router.post("/customer-groups", response_model=CustomerGroupResponse)
async def create_customer_group(group: CustomerGroupCreate, user = Depends(get_current_user)):
    """Create a custom group of customers"""
    business_id = user.get("business_id", user["_id"])
    group_id = str(uuid.uuid4())
    
    # deduplicate ids
    customer_ids = list(set(group.customer_ids))
    
    group_doc = {
        "_id": group_id,
        "user_id": business_id,
        "name": group.name,
        "customer_ids": customer_ids,
        "created_at": datetime.utcnow()
    }
    
    await db.customer_groups.insert_one(group_doc)
    
    return CustomerGroupResponse(
        id=group_id,
        user_id=business_id,
        name=group.name,
        customer_ids=customer_ids,
        count=len(customer_ids),
        created_at=group_doc["created_at"]
    )

@api_router.get("/customer-groups", response_model=List[CustomerGroupResponse])
async def get_customer_groups(user = Depends(get_current_user)):
    """Get all customer groups for user"""
    business_id = user.get("business_id", user["_id"])
    groups = await db.customer_groups.find({"user_id": business_id}).sort("created_at", -1).to_list(100)
    
    return [
        CustomerGroupResponse(
            id=g["_id"],
            user_id=g["user_id"],
            name=g["name"],
            customer_ids=g.get("customer_ids", []),
            count=len(g.get("customer_ids", [])),
            created_at=g["created_at"]
        )
        for g in groups
    ]

@api_router.delete("/customer-groups/{group_id}")
async def delete_customer_group(group_id: str, user = Depends(get_current_user)):
    """Delete a customer group"""
    business_id = user.get("business_id", user["_id"])
    result = await db.customer_groups.delete_one({"_id": group_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"status": "success", "message": "Group deleted"}


# ============ BOOKING ENDPOINTS ============

class BookingCreate(BaseModel):
    service_id: str
    customer_id: Optional[str] = None  # None for walk-in customers
    customer_name: Optional[str] = None  # used when no customer_id (walk-in)
    customer_phone: Optional[str] = None
    date: str                          # "YYYY-MM-DD"
    time: str                          # "HH:MM" 24h
    notes: Optional[str] = None
    staff_id: Optional[str] = None

class BookingUpdate(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    notes: Optional[str] = None
    staff_id: Optional[str] = None
    status: Optional[str] = None       # pending|confirmed|completed|cancelled|no_show
    payment_status: Optional[str] = None  # unpaid|partial|paid

class BookingResponse(BaseModel):
    id: str
    booking_number: str
    customer_id: str
    customer_name: str
    customer_phone: Optional[str] = None
    service_id: Optional[str] = None
    service_name: str
    staff_id: Optional[str] = None
    staff_name: Optional[str] = None
    date: str
    time: str
    end_time: Optional[str] = None
    duration: Optional[int] = None
    status: str
    payment_status: str
    price: float
    notes: Optional[str] = None
    source: Optional[str] = None
    reminder_sent: bool = False
    last_reminder_at: Optional[datetime] = None
    created_at: datetime

def _generate_booking_number() -> str:
    """Generate short booking reference like BK-X7K2M9"""
    import random, string
    chars = string.ascii_uppercase + string.digits
    return "BK-" + "".join(random.choices(chars, k=6))

def _calc_end_time(start_time: str, duration_minutes: int) -> str:
    """Calculate end time string from start time + duration in minutes"""
    try:
        h, m = map(int, start_time.split(":"))
        total = h * 60 + m + duration_minutes
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return start_time

@api_router.post("/bookings", response_model=BookingResponse)
async def create_booking(booking: BookingCreate, user = Depends(get_current_user)):
    """Create a new booking/appointment"""
    business_id = user.get("business_id", user["_id"])

    # Fetch service
    service = await db.products.find_one({"_id": booking.service_id, "user_id": business_id})
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Fetch customer (or allow walk-in with no customer record)
    customer = None
    if booking.customer_id:
        customer = await db.customers.find_one({"_id": booking.customer_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

    duration = service.get("duration") or 60
    end_time = _calc_end_time(booking.time, duration)

    # Conflict check: no overlapping confirmed/pending bookings for same date/service
    existing = await db.bookings.find_one({
        "user_id": business_id,
        "service_id": booking.service_id,
        "date": booking.date,
        "status": {"$in": ["pending", "confirmed"]},
        "time": booking.time,
    })
    max_concurrent = service.get("max_concurrent", 1)
    if existing:
        slot_count = await db.bookings.count_documents({
            "user_id": business_id,
            "service_id": booking.service_id,
            "date": booking.date,
            "time": booking.time,
            "status": {"$in": ["pending", "confirmed"]},
        })
        if slot_count >= max_concurrent:
            raise HTTPException(status_code=409, detail="That time slot is already fully booked")

    booking_id = str(uuid.uuid4())
    booking_number = _generate_booking_number()
    now = datetime.utcnow()

    booking_settings = user.get("settings", {}).get("booking_settings", {})
    auto_confirm = booking_settings.get("auto_confirm", False)
    initial_status = "confirmed" if auto_confirm else "pending"

    booking_doc = {
        "_id": booking_id,
        "user_id": business_id,
        "booking_number": booking_number,
        "customer_id": booking.customer_id or "walkin",
        "customer_name": customer.get("name", "Customer") if customer else (booking.customer_name or "Walk-in Customer"),
        "customer_phone": customer.get("phone_number") if customer else booking.customer_phone,
        "service_id": booking.service_id,
        "service_name": service.get("name", "Service"),
        "staff_id": booking.staff_id,
        "staff_name": None,
        "date": booking.date,
        "time": booking.time,
        "end_time": end_time,
        "duration": duration,
        "status": initial_status,
        "payment_status": "unpaid",
        "price": service.get("price", 0),
        "notes": booking.notes,
        "reminder_sent": False,
        "created_at": now,
        "updated_at": now,
    }
    await db.bookings.insert_one(booking_doc)

    return BookingResponse(
        id=booking_id,
        booking_number=booking_number,
        customer_id=booking.customer_id,
        customer_name=booking_doc["customer_name"],
        customer_phone=booking_doc["customer_phone"],
        service_id=booking.service_id,
        service_name=booking_doc["service_name"],
        staff_id=booking.staff_id,
        staff_name=None,
        date=booking.date,
        time=booking.time,
        end_time=end_time,
        duration=duration,
        status=initial_status,
        payment_status="unpaid",
        price=booking_doc["price"],
        notes=booking.notes,
        source=None,
        reminder_sent=False,
        last_reminder_at=None,
        created_at=now,
    )

@api_router.get("/bookings", response_model=List[BookingResponse])
async def get_bookings(
    status: Optional[str] = None,
    date: Optional[str] = None,
    customer_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """List bookings with optional filters"""
    business_id = user.get("business_id", user["_id"])
    query: Dict[str, Any] = {"user_id": business_id}
    if status:
        query["status"] = status
    if date:
        query["date"] = date
    if customer_id:
        query["customer_id"] = customer_id

    docs = await db.bookings.find(query).sort([("date", -1), ("time", 1)]).to_list(500)
    return [
        BookingResponse(
            id=d["_id"],
            booking_number=d.get("booking_number", ""),
            customer_id=d["customer_id"],
            customer_name=d.get("customer_name", ""),
            customer_phone=d.get("customer_phone"),
            service_id=d.get("service_id"),
            service_name=d.get("service_name", ""),
            staff_id=d.get("staff_id"),
            staff_name=d.get("staff_name"),
            date=d["date"],
            time=d["time"],
            end_time=d.get("end_time"),
            duration=d.get("duration"),
            status=d.get("status", "pending"),
            payment_status=d.get("payment_status", "unpaid"),
            price=d.get("price", 0),
            notes=d.get("notes"),
            source=d.get("source"),
            reminder_sent=d.get("reminder_sent", False),
            last_reminder_at=d.get("last_reminder_at"),
            created_at=d.get("created_at", datetime.utcnow()),
        )
        for d in docs
    ]

@api_router.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: str, user = Depends(get_current_user)):
    """Get a single booking"""
    business_id = user.get("business_id", user["_id"])
    d = await db.bookings.find_one({"_id": booking_id, "user_id": business_id})
    if not d:
        raise HTTPException(status_code=404, detail="Booking not found")
    return BookingResponse(
        id=d["_id"],
        booking_number=d.get("booking_number", ""),
        customer_id=d["customer_id"],
        customer_name=d.get("customer_name", ""),
        customer_phone=d.get("customer_phone"),
        service_id=d["service_id"],
        service_name=d.get("service_name", ""),
        staff_id=d.get("staff_id"),
        staff_name=d.get("staff_name"),
        date=d["date"],
        time=d["time"],
        end_time=d.get("end_time"),
        duration=d.get("duration"),
        status=d.get("status", "pending"),
        payment_status=d.get("payment_status", "unpaid"),
        price=d.get("price", 0),
        notes=d.get("notes"),
        source=d.get("source"),
        reminder_sent=d.get("reminder_sent", False),
        last_reminder_at=d.get("last_reminder_at"),
        created_at=d.get("created_at", datetime.utcnow()),
    )

@api_router.put("/bookings/{booking_id}", response_model=BookingResponse)
async def update_booking(booking_id: str, updates: BookingUpdate, user = Depends(get_current_user)):
    """Update booking details or status"""
    business_id = user.get("business_id", user["_id"])
    d = await db.bookings.find_one({"_id": booking_id, "user_id": business_id})
    if not d:
        raise HTTPException(status_code=404, detail="Booking not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    if updates.date is not None:
        update_data["date"] = updates.date
    if updates.time is not None:
        update_data["time"] = updates.time
        # Recalculate end_time
        duration = d.get("duration", 60)
        update_data["end_time"] = _calc_end_time(updates.time, duration)
    if updates.notes is not None:
        update_data["notes"] = updates.notes
    if updates.staff_id is not None:
        update_data["staff_id"] = updates.staff_id
    if updates.status is not None:
        update_data["status"] = updates.status
        if updates.status == "cancelled":
            update_data["cancelled_at"] = datetime.utcnow()
    if updates.payment_status is not None:
        update_data["payment_status"] = updates.payment_status

    await db.bookings.update_one({"_id": booking_id}, {"$set": update_data})
    d.update(update_data)

    return BookingResponse(
        id=d["_id"],
        booking_number=d.get("booking_number", ""),
        customer_id=d["customer_id"],
        customer_name=d.get("customer_name", ""),
        customer_phone=d.get("customer_phone"),
        service_id=d["service_id"],
        service_name=d.get("service_name", ""),
        staff_id=d.get("staff_id"),
        staff_name=d.get("staff_name"),
        date=d["date"],
        time=d["time"],
        end_time=d.get("end_time"),
        duration=d.get("duration"),
        status=d.get("status", "pending"),
        payment_status=d.get("payment_status", "unpaid"),
        price=d.get("price", 0),
        notes=d.get("notes"),
        source=d.get("source"),
        reminder_sent=d.get("reminder_sent", False),
        last_reminder_at=d.get("last_reminder_at"),
        created_at=d.get("created_at", datetime.utcnow()),
    )

@api_router.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str, user = Depends(get_current_user)):
    """Cancel/delete a booking"""
    business_id = user.get("business_id", user["_id"])
    result = await db.bookings.delete_one({"_id": booking_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"status": "success", "message": "Booking deleted"}

@api_router.post("/bookings/{booking_id}/send-reminder")
async def send_booking_reminder_manual(booking_id: str, user = Depends(get_current_user)):
    """Manually send a WhatsApp reminder for a specific booking"""
    from whatsapp_service import get_whatsapp_service
    business_id = user.get("business_id", user["_id"])
    booking = await db.bookings.find_one({"_id": booking_id, "user_id": business_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    customer_phone = booking.get("customer_phone")
    if not customer_phone:
        raise HTTPException(status_code=400, detail="No phone number on this booking")

    customer_name  = booking.get("customer_name", "there")
    service_name   = booking.get("service_name", "appointment")
    date_str       = booking.get("date", "")
    time_str       = booking.get("time", "")
    booking_number = booking.get("booking_number", "")

    msg = (
        f"Hi {customer_name}! \U0001f4c5 Just a reminder about your upcoming "
        f"*{service_name}* on *{date_str} at {time_str}*.\n\n"
        f"Ref: *{booking_number}*\n"
        f"_Reply to reschedule or cancel_"
    )
    ws = get_whatsapp_service(db)
    await ws.send_message(
        user_id=business_id, to_number=customer_phone,
        message=msg, customer_name=customer_name, send_context="booking_reminder"
    )
    await db.bookings.update_one(
        {"_id": booking_id},
        {"$set": {"last_reminder_at": datetime.utcnow()}}
    )
    return {"status": "sent"}

@api_router.get("/availability/day")
async def get_availability(
    date: str,
    service_id: str,
    user = Depends(get_current_user)
):
    """Get available time slots for a service on a given date (YYYY-MM-DD)"""
    business_id = user.get("business_id", user["_id"])

    # Fetch service for duration
    service = await db.products.find_one({"_id": service_id, "user_id": business_id})
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    duration = service.get("duration", 60)
    max_concurrent = service.get("max_concurrent", 1)

    # Get business hours for the weekday
    try:
        from datetime import date as _date
        parsed_date = _date.fromisoformat(date)
        weekday_map = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        day_key = weekday_map[parsed_date.weekday()]
        day_name = parsed_date.strftime("%A")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    business_hours = user.get("settings", {}).get("business_hours", {})
    day_hours = business_hours.get(day_key, {})
    if day_hours.get("closed", False) or not day_hours:
        return {
            "date": date,
            "day": day_name,
            "closed": True,
            "available_slots": [],
            "booked_slots": [],
        }

    open_time = day_hours.get("open", "09:00")
    close_time = day_hours.get("close", "17:00")

    booking_settings = user.get("settings", {}).get("booking_settings", {})
    buffer = booking_settings.get("buffer_minutes", 15)

    # Build all possible slots
    def time_to_min(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def min_to_time(m: int) -> str:
        return f"{m // 60:02d}:{m % 60:02d}"

    open_min = time_to_min(open_time)
    close_min = time_to_min(close_time)
    slot_step = duration + buffer

    all_slots = []
    cursor = open_min
    while cursor + duration <= close_min:
        all_slots.append(min_to_time(cursor))
        cursor += slot_step

    # Fetch existing bookings for that date and service
    existing_bookings = await db.bookings.find({
        "user_id": business_id,
        "service_id": service_id,
        "date": date,
        "status": {"$in": ["pending", "confirmed"]},
    }).to_list(200)

    booked_slot_counts: Dict[str, int] = {}
    for b in existing_bookings:
        t = b.get("time", "")
        booked_slot_counts[t] = booked_slot_counts.get(t, 0) + 1

    booked_slots = [
        {"time": b.get("time"), "end_time": b.get("end_time"), "service": b.get("service_name")}
        for b in existing_bookings
    ]

    available_slots = [
        {"time": s, "end_time": _calc_end_time(s, duration)}
        for s in all_slots
        if booked_slot_counts.get(s, 0) < max_concurrent
    ]

    return {
        "date": date,
        "day": day_name,
        "closed": False,
        "business_hours": {"open": open_time, "close": close_time},
        "available_slots": available_slots,
        "booked_slots": booked_slots,
    }

@api_router.get("/availability/week")
async def get_availability_week(
    start: str,
    service_id: str,
    user = Depends(get_current_user)
):
    """Get availability summary for 7 days starting from start date"""
    from datetime import date as _date, timedelta
    try:
        start_date = _date.fromisoformat(start)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    result = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_str = day.isoformat()
        day_avail = await get_availability(day_str, service_id, user)
        result.append({
            "date": day_str,
            "day": day.strftime("%A"),
            "closed": day_avail.get("closed", False),
            "available_count": len(day_avail.get("available_slots", [])),
        })
    return result


# ============ PRODUCT ENDPOINTS ============

class ProductResponse(BaseModel):
    id: str
    name: str
    price: float = 0.0
    discount_price: Optional[float] = None
    category: str = "Other"
    image_url: Optional[str] = None
    images: List[str] = []
    description: Optional[str] = None
    in_stock: bool = True
    stock_quantity: Optional[int] = None
    created_at: datetime
    # Multi-business-type fields
    offering_type: Optional[str] = "product"  # product, service, menu_item, class, digital
    duration: Optional[int] = None            # minutes (for services/classes)
    requires_staff: Optional[bool] = False
    max_concurrent: Optional[int] = 1
    digital: Optional[bool] = False
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    service_category: Optional[str] = "appointment"  # appointment | rental
    addons: Optional[List[dict]] = []               # [{name, price}] max 4
    listing_blocked_dates: Optional[List[str]] = []  # per-listing blocked YYYY-MM-DD dates
    deposit_percent: Optional[int] = 0               # 0=none, 1-100 = required deposit %
    price_unit: Optional[str] = "night"               # night | day | week | month | year | person
    capacity: Optional[int] = 1                      # max appointments per time slot (default 1)

@api_router.get("/products", response_model=List[ProductResponse])
async def get_products(user = Depends(get_current_user)):
    """Get all products for the user"""
    business_id = user.get("business_id", user["_id"])
    products = await db.products.find({"user_id": business_id}).to_list(100)
    
    result = []
    for p in products:
        imgs = list(p.get("images", []))
        orig = p.get("image_url")
        if orig and orig not in imgs:
            imgs.insert(0, orig)
        result.append(ProductResponse(
            id=p["_id"],
            name=p.get("name", "Unnamed Product"),
            price=p.get("price") or 0.0,
            discount_price=p.get("discount_price"),
            category=p.get("category") or "Other",
            image_url=orig,
            images=imgs,
            description=p.get("description"),
            in_stock=p.get("in_stock", True),
            stock_quantity=p.get("stock_quantity"),
            created_at=p.get("created_at", datetime.utcnow()),
            offering_type=p.get("offering_type", "product"),
            duration=p.get("duration"),
            requires_staff=p.get("requires_staff", False),
            max_concurrent=p.get("max_concurrent", 1),
            digital=p.get("digital", False),
            download_url=p.get("download_url"),
            preview_url=p.get("preview_url"),
            service_category=p.get("service_category", "appointment"),
            addons=p.get("addons", []),
            listing_blocked_dates=p.get("listing_blocked_dates", []),
            deposit_percent=p.get("deposit_percent", 0),
            price_unit=p.get("price_unit", "night"),
            capacity=p.get("capacity", 1),
        ))
    return result

class ProductCreate(BaseModel):
    name: str = "New Product"
    price: float = 0.0
    discount_price: Optional[float] = None
    category: str = "Other"
    image_url: Optional[str] = None
    images: List[str] = []
    description: Optional[str] = None
    in_stock: bool = True
    stock_quantity: Optional[int] = None
    # Multi-business-type fields
    offering_type: Optional[str] = "product"
    duration: Optional[int] = None
    requires_staff: Optional[bool] = False
    max_concurrent: Optional[int] = 1
    digital: Optional[bool] = False
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    service_category: Optional[str] = "appointment"
    addons: Optional[List[dict]] = []
    listing_blocked_dates: Optional[List[str]] = []
    deposit_percent: Optional[int] = 0
    price_unit: Optional[str] = "night"
    capacity: Optional[int] = 1

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    discount_price: Optional[float] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    description: Optional[str] = None
    in_stock: Optional[bool] = None
    stock_quantity: Optional[int] = None
    # Multi-business-type fields
    offering_type: Optional[str] = None
    duration: Optional[int] = None
    requires_staff: Optional[bool] = None
    max_concurrent: Optional[int] = None
    digital: Optional[bool] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    service_category: Optional[str] = None
    addons: Optional[List[dict]] = None
    listing_blocked_dates: Optional[List[str]] = None
    deposit_percent: Optional[int] = None
    price_unit: Optional[str] = None
    capacity: Optional[int] = None

# Plan-based product and image limits
PLAN_PRODUCT_LIMITS = {
    "free":     {"products": 5,   "images": 25},
    "starter":  {"products": 20,  "images": 100},
    "standard": {"products": 50,  "images": 250},
    "pro":      {"products": None, "images": None},  # None = unlimited
}

def get_plan_limits(user: dict) -> dict:
    plan = user.get("subscription_plan", "free")
    return PLAN_PRODUCT_LIMITS.get(plan, PLAN_PRODUCT_LIMITS["free"])

async def count_total_images(db, business_id: str) -> int:
    pipeline = [
        {"$match": {"user_id": business_id}},
        {"$project": {"img_count": {"$size": {"$ifNull": ["$images", []]}}}},
        {"$group": {"_id": None, "total": {"$sum": "$img_count"}}}
    ]
    result = await db.products.aggregate(pipeline).to_list(1)
    return result[0]["total"] if result else 0

@api_router.post("/products", response_model=ProductResponse)
async def create_product(product: ProductCreate, user = Depends(get_current_user)):
    """Create a new product"""
    business_id = user.get("business_id", user["_id"])
    limits = get_plan_limits(user)
    # Check product limit
    count = await db.products.count_documents({"user_id": business_id})
    if limits["products"] is not None and count >= limits["products"]:
        raise HTTPException(status_code=400, detail=f"Product limit reached ({limits['products']} on your plan). Upgrade for more.")
    # Check total image limit
    new_images = product.images or ([product.image_url] if product.image_url else [])
    if limits["images"] is not None and new_images:
        current_images = await count_total_images(db, business_id)
        if current_images + len(new_images) > limits["images"]:
            raise HTTPException(status_code=400, detail=f"Image limit reached ({limits['images']} total on your plan). Upgrade for more.")
    
    # Sanitize inputs
    clean_name = sanitize_string(product.name, 200)
    clean_category = sanitize_string(product.category or "Other", 100)
    clean_description = sanitize_string(product.description, 1000) if product.description else None

    if not clean_name:
        raise HTTPException(status_code=400, detail="Product name is required")
    if product.price is not None and product.price < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative")
    if product.discount_price is not None and product.discount_price < 0:
        raise HTTPException(status_code=400, detail="Discount price cannot be negative")
    if product.discount_price is not None and product.discount_price >= product.price:
        raise HTTPException(status_code=400, detail="Discount price must be less than regular price")

    # Ensure images list is populated if image_url is provided
    images = product.images
    if not images and product.image_url:
        images = [product.image_url]
    
    product_doc = {
        "_id": str(uuid.uuid4()),
        "user_id": business_id,
        "name": clean_name,
        "price": product.price,
        "discount_price": product.discount_price,
        "category": clean_category,
        "image_url": product.image_url,
        "images": images,
        "description": clean_description,
        "in_stock": product.in_stock,
        "stock_quantity": product.stock_quantity,
        "offering_type": product.offering_type or "product",
        "duration": product.duration,
        "requires_staff": product.requires_staff or False,
        "max_concurrent": product.max_concurrent or 1,
        "digital": product.digital or False,
        "download_url": product.download_url,
        "preview_url": product.preview_url,
        "service_category": product.service_category or "appointment",
        "addons": (product.addons or [])[:4],
        "listing_blocked_dates": product.listing_blocked_dates or [],
        "deposit_percent": product.deposit_percent or 0,
        "price_unit": product.price_unit or "night",
        "capacity": product.capacity or 1,
        "created_at": datetime.utcnow()
    }
    
    await db.products.insert_one(product_doc)
    
    return ProductResponse(
        id=product_doc["_id"],
        name=product_doc["name"],
        price=product_doc["price"],
        discount_price=product_doc["discount_price"],
        category=product_doc["category"],
        image_url=product_doc["image_url"],
        images=product_doc["images"],
        description=product_doc["description"],
        in_stock=product_doc["in_stock"],
        stock_quantity=product_doc["stock_quantity"],
        created_at=product_doc["created_at"],
        offering_type=product_doc["offering_type"],
        duration=product_doc["duration"],
        requires_staff=product_doc["requires_staff"],
        max_concurrent=product_doc["max_concurrent"],
        digital=product_doc["digital"],
        download_url=product_doc["download_url"],
        preview_url=product_doc["preview_url"],
        service_category=product_doc["service_category"],
        addons=product_doc["addons"],
        listing_blocked_dates=product_doc.get("listing_blocked_dates", []),
        deposit_percent=product_doc.get("deposit_percent", 0),
        price_unit=product_doc.get("price_unit", "night"),
        capacity=product_doc.get("capacity", 1),
    )

@api_router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: str, updates: ProductUpdate, user = Depends(get_current_user)):
    """Update a product"""
    # Create update dict excluding None values (allow empty list for listing_blocked_dates)
    update_data = {k: v for k, v in updates.dict().items() if v is not None or k == "listing_blocked_dates"}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    # Validate discount price if provided
    if "discount_price" in update_data and update_data["discount_price"] is not None:
        if update_data["discount_price"] < 0:
            raise HTTPException(status_code=400, detail="Discount price cannot be negative")
        business_id = user.get("business_id", user["_id"])
        # Get current product to validate discount vs regular price
        current = await db.products.find_one({"_id": product_id, "user_id": business_id})
        if not current:
            raise HTTPException(status_code=404, detail="Product not found")
        # Use the new price if being updated, otherwise use current price
        comparison_price = update_data.get("price", current.get("price", 0))
        if update_data["discount_price"] >= comparison_price:
            raise HTTPException(status_code=400, detail="Discount price must be less than regular price")
        
    business_id = user.get("business_id", user["_id"])
    # If updating images, ensure image_url is consistent (take first image)
    if "images" in update_data and update_data["images"]:
        update_data["image_url"] = update_data["images"][0]
    elif "images" in update_data and not update_data["images"]:
        update_data["image_url"] = None

    result = await db.products.find_one_and_update(
        {"_id": product_id, "user_id": business_id},
        {"$set": update_data},
        return_document=True
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Product not found")
        
    imgs = list(result.get("images", []))
    orig = result.get("image_url")
    if orig and orig not in imgs:
        imgs.insert(0, orig)
    
    return ProductResponse(
        id=result["_id"],
        name=result["name"],
        price=result.get("price") or 0.0,
        discount_price=result.get("discount_price"),
        category=result.get("category") or "Other",
        image_url=orig,
        images=imgs,
        description=result.get("description"),
        in_stock=result.get("in_stock", True),
        stock_quantity=result.get("stock_quantity"),
        created_at=result["created_at"],
        offering_type=result.get("offering_type", "product"),
        duration=result.get("duration"),
        requires_staff=result.get("requires_staff", False),
        max_concurrent=result.get("max_concurrent", 1),
        digital=result.get("digital", False),
        download_url=result.get("download_url"),
        preview_url=result.get("preview_url"),
        service_category=result.get("service_category", "appointment"),
        addons=result.get("addons", []),
        listing_blocked_dates=result.get("listing_blocked_dates", []),
        deposit_percent=result.get("deposit_percent", 0),
        price_unit=result.get("price_unit", "night"),
    )

@api_router.post("/products/{product_id}/images")
async def add_product_images(
    product_id: str,
    files: List[UploadFile] = File(...),
    user = Depends(get_current_user)
):
    """Add images to an existing product (max 5 images per product)"""
    business_id = user.get("business_id", user["_id"])
    product = await db.products.find_one({"_id": product_id, "user_id": business_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    existing_images = list(product.get("images", []))
    # Ensure the original image_url is in the images array
    original_url = product.get("image_url")
    if original_url and original_url not in existing_images:
        existing_images.insert(0, original_url)
    
    if len(existing_images) + len(files) > 5:
        raise HTTPException(status_code=400, detail=f"Maximum 5 images per product. Currently has {len(existing_images)}.")
    
    new_image_urls = []
    for file in files:
        try:
            result = await ImageUploadHandler.save_image(file)
            if result:
                new_image_urls.append(result["image_url"])
        except Exception as e:
            logging.error(f"Failed to save image: {e}")
    
    if new_image_urls:
        all_images = existing_images + new_image_urls
        update_data = {"images": all_images, "image_url": all_images[0]}
        
        await db.products.update_one(
            {"_id": product_id},
            {"$set": update_data}
        )
    
    return {"status": "success", "images_added": len(new_image_urls), "total_images": len(existing_images) + len(new_image_urls)}

@api_router.delete("/products/{product_id}/images/{image_index}")
async def delete_product_image(
    product_id: str,
    image_index: int,
    user = Depends(get_current_user)
):
    """Delete a specific image from a product"""
    business_id = user.get("business_id", user["_id"])
    product = await db.products.find_one({"_id": product_id, "user_id": business_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    images = product.get("images", [])
    if image_index < 0 or image_index >= len(images):
        raise HTTPException(status_code=400, detail="Invalid image index")
    
    images.pop(image_index)
    update_data = {"images": images, "image_url": images[0] if images else None}
    await db.products.update_one({"_id": product_id}, {"$set": update_data})
    
    return {"status": "success", "remaining_images": len(images)}

# ============ AI MESSAGE GENERATION ============

@api_router.post("/ai/generate-broadcast-message")
async def generate_broadcast_message(request: AIMessageRequest, user = Depends(get_current_user)):
    """Generate a broadcast message using AI"""
    try:
        drafter = get_drafter()
        generated_message = await drafter.draft_broadcast_message(
            prompt=request.prompt,
            business_type=request.business_type
        )
        
        return {"message": generated_message}
    except Exception as e:
        logging.error(f"AI generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate message")

# ============ IMAGE UPLOAD ENDPOINTS ============

class ImageUploadRequest(BaseModel):
    base64_data: str
    filename: Optional[str] = "image.jpg"

@api_router.post("/upload-image")
async def upload_broadcast_image(request: ImageUploadRequest, user = Depends(get_current_user)):
    """Upload an image for broadcast messages - returns public URL"""
    try:
        # Try S3 first if configured
        if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
            try:
                url = await S3Handler.upload_file(request.base64_data, request.filename)
                result = {"image_url": url, "filename": request.filename}
                logging.info(f"Image uploaded to S3: {url}")
                return result
            except Exception as e:
                logging.error(f"S3 Upload Failed, falling back: {e}")

        result = await ImageUploadHandler.upload_base64_to_cloudinary(
            request.base64_data,
            request.filename
        )
        logging.info(f"Image uploaded successfully (ImgBB): {result}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Image upload error: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload image")

# ============ SUBSCRIPTION ENDPOINTS ============

# Base plan features (prices are set per region)
PLAN_FEATURES = {
    "starter": {
        "name": "Starter",
        "interval": "monthly",
        "features": ["1,500 messages/month", "Unlimited customers", "Follow-ups & broadcasts", "AI replies"]
    },
    "standard": {
        "name": "Growth",
        "interval": "monthly",
        "features": ["5,000 messages/month", "Unlimited customers", "Follow-ups & broadcasts", "AI replies", "Priority support"]
    },
    "pro": {
        "name": "Pro",
        "interval": "monthly",
        "features": ["10,000 messages/month", "Unlimited customers", "Advanced analytics", "Custom templates", "Dedicated support"]
    }
}

# Regional pricing: currency -> (starter, standard, pro)
# Anchor: KES 700 / 1500 / 2500  ≈  USD 5.40 / 11.60 / 19.30
REGIONAL_PRICING = {
    # East Africa
    "KES": (700, 1500, 2500),       # Kenya
    "TZS": (14000, 30000, 50000),   # Tanzania
    "UGX": (20000, 43000, 72000),   # Uganda
    "RWF": (6000, 13000, 22000),    # Rwanda
    "ETB": (300, 650, 1100),        # Ethiopia
    "BIF": (16000, 34000, 57000),   # Burundi
    "SOS": (3000, 6500, 11000),     # Somalia
    # West Africa
    "NGN": (4500, 9500, 16000),     # Nigeria
    "GHS": (45, 95, 160),           # Ghana
    "XOF": (3500, 7500, 12500),     # CFA (Senegal, Ivory Coast, etc.)
    "XAF": (3500, 7500, 12500),     # CFA (Cameroon, etc.)
    # Southern Africa
    "ZAR": (100, 210, 350),         # South Africa
    "CDF": (15000, 32000, 53000),   # DR Congo
    # North Africa / Middle East
    "EGP": (170, 360, 600),         # Egypt
    "MAD": (55, 115, 195),          # Morocco
    "TND": (17, 36, 60),            # Tunisia
    "AED": (20, 43, 71),            # UAE
    "SAR": (20, 43, 71),            # Saudi Arabia
    # South Asia
    "INR": (450, 960, 1600),        # India
    "PKR": (1500, 3200, 5400),      # Pakistan
    "BDT": (600, 1300, 2100),       # Bangladesh
    # Southeast Asia
    "PHP": (300, 650, 1100),        # Philippines
    "IDR": (85000, 180000, 300000), # Indonesia
    "MYR": (25, 54, 90),            # Malaysia
    "THB": (190, 410, 680),         # Thailand
    "VND": (135000, 290000, 480000),# Vietnam
    # East Asia
    "CNY": (39, 84, 140),           # China
    "JPY": (800, 1700, 2900),       # Japan
    "KRW": (7200, 15500, 26000),    # South Korea
    # Americas
    "USD": (10, 18, 28),            # USA/Canada (Tier 1)
    "BRL": (30, 65, 108),           # Brazil
    "MXN": (100, 215, 360),         # Mexico
    "COP": (22000, 47000, 78000),   # Colombia
    "CLP": (4800, 10200, 17000),    # Chile
    "ARS": (4500, 9600, 16000),     # Argentina
    # Europe
    "GBP": (8, 14, 22),             # UK (Tier 1)
    "EUR": (9, 16, 25),             # Eurozone (Tier 1)
    "AUD": (15, 27, 42),            # Australia (Tier 1)
    "NZD": (16, 28, 44),            # New Zealand (Tier 1)
    "CAD": (13, 23, 36),            # Canada (Tier 1)
    "CHF": (9, 16, 25),             # Switzerland (Tier 1)
    "SGD": (13, 23, 36),            # Singapore (Tier 1)
}

def get_regional_plans(currency: str) -> list:
    """Get subscription plans with regional pricing"""
    prices = REGIONAL_PRICING.get(currency, REGIONAL_PRICING["USD"])
    plan_ids = ["starter", "standard", "pro"]
    plans = []
    for i, plan_id in enumerate(plan_ids):
        plan = PLAN_FEATURES[plan_id].copy()
        amount = prices[i]
        # Format display amount with commas
        if amount >= 1000:
            display = f"{amount:,.0f}/month"
        else:
            display = f"{amount}/month"
        plans.append({
            "id": plan_id,
            "name": plan["name"],
            "amount": amount,
            "currency": currency,
            "amount_display": display,
            "interval": plan["interval"],
            "features": plan["features"]
        })
    return plans

@api_router.get("/subscription/plans")
async def get_subscription_plans(user = Depends(get_current_user)):
    """Get available subscription plans with regional pricing"""
    # Check user.currency first (top-level), then user.settings.currency, then USD
    currency = user.get('currency') or user.get('settings', {}).get('currency', 'USD') or 'USD'
    return get_regional_plans(currency)

async def _verify_google_play_purchase(purchase_token: str, plan_id: str) -> dict:
    """Verify a Google Play purchase token with the Android Publisher API."""
    # Google Play product IDs follow the pattern: crm_{plan}_monthly
    product_id = f"crm_{plan_id}_monthly"
    package_name = GOOGLE_PLAY_PACKAGE_NAME or 'com.zilo.reply'
    # Default to the service account file saved in the backend directory
    sa_key_path = os.environ.get('GOOGLE_SA_KEY_PATH', 'google-service-account.json')

    if not os.path.exists(sa_key_path):
        logging.warning(f"Service account key not found at '{sa_key_path}' — skipping server verification")
        return {"valid": True, "reason": "no_server_config"}

    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GRequest
        import httpx

        creds = service_account.Credentials.from_service_account_file(
            sa_key_path,
            scopes=["https://www.googleapis.com/auth/androidpublisher"],
        )
        creds.refresh(GRequest())

        url = (
            f"https://androidpublisher.googleapis.com/androidpublisher/v3"
            f"/applications/{package_name}/purchases/products/{product_id}"
            f"/tokens/{purchase_token}"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {creds.token}"})

        if resp.status_code != 200:
            return {"valid": False, "reason": f"Google API error: {resp.status_code}"}

        data = resp.json()
        # purchaseState 0 = purchased, 1 = canceled
        if data.get("purchaseState", -1) != 0:
            return {"valid": False, "reason": "Purchase not completed"}

        return {"valid": True, "order_id": data.get("orderId")}
    except ImportError:
        logging.warning("google-auth not installed — skipping Google Play verification")
        return {"valid": True, "reason": "no_google_auth_lib"}
    except Exception as e:
        logging.error(f"Google Play verification error: {e}")
        return {"valid": False, "reason": str(e)}


async def _verify_apple_receipt(purchase_token: str) -> dict:
    """Verify an Apple App Store receipt."""
    apple_shared_secret = os.environ.get('APPLE_SHARED_SECRET', '')
    if not apple_shared_secret:
        logging.warning("APPLE_SHARED_SECRET not set — skipping Apple verification")
        return {"valid": True, "reason": "no_server_config"}

    try:
        import httpx
        payload = {"receipt-data": purchase_token, "password": apple_shared_secret}

        # Try production first, then sandbox
        for url in [
            "https://buy.itunes.apple.com/verifyReceipt",
            "https://sandbox.itunes.apple.com/verifyReceipt",
        ]:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
            data = resp.json()
            status = data.get("status", -1)
            if status == 21007:
                continue  # sandbox receipt sent to production — retry sandbox
            if status == 0:
                return {"valid": True, "receipt": data.get("receipt", {})}
            return {"valid": False, "reason": f"Apple status {status}"}

        return {"valid": False, "reason": "Verification failed on both endpoints"}
    except Exception as e:
        logging.error(f"Apple receipt verification error: {e}")
        return {"valid": False, "reason": str(e)}


@api_router.post("/subscription/verify-purchase")
async def verify_iap_purchase(request: IAPVerifyRequest, user = Depends(get_current_user)):
    """Verify in-app purchase from Google Play or App Store"""
    if request.plan_id not in PLAN_FEATURES:
        raise HTTPException(status_code=400, detail="Invalid plan")

    # Prevent duplicate token usage
    existing_txn = await db.transactions.find_one({"purchase_token": request.purchase_token, "status": "success"})
    if existing_txn:
        raise HTTPException(status_code=400, detail="This purchase has already been redeemed")

    # Server-side receipt verification
    if request.platform == "android":
        verification = await _verify_google_play_purchase(request.purchase_token, request.plan_id)
    elif request.platform == "ios":
        verification = await _verify_apple_receipt(request.purchase_token)
    else:
        raise HTTPException(status_code=400, detail="Invalid platform")

    if not verification.get("valid"):
        logging.warning(f"IAP verification failed for user {user['_id']}: {verification.get('reason')}")
        raise HTTPException(status_code=403, detail=f"Purchase verification failed: {verification.get('reason', 'unknown')}")

    # Update user subscription
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "subscription_plan": request.plan_id,
                "subscription_active": True,
                "subscription_date": datetime.utcnow()
            }
        }
    )
    
    # Store transaction
    await db.transactions.insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": user["_id"],
        "purchase_token": request.purchase_token,
        "plan_id": request.plan_id,
        "platform": request.platform,
        "verification": verification,
        "status": "success",
        "created_at": datetime.utcnow()
    })
    
    return {
        "status": "success",
        "message": "Subscription activated",
        "plan": request.plan_id
    }

@api_router.get("/subscription/status")
async def get_subscription_status(user = Depends(get_current_user)):
    """Get current user subscription status"""
    plan = user.get("subscription_plan")
    active = user.get("subscription_active", False)
    # Build limits from SUBSCRIPTION_LIMITS for the current plan
    limits = SUBSCRIPTION_LIMITS.get(plan, SUBSCRIPTION_LIMITS['free']) if plan else SUBSCRIPTION_LIMITS['free']
    return {
        "subscription_plan": plan,
        "subscription_active": active,
        "subscription_date": user.get("subscription_date"),
        "subscription_expiry": user.get("subscription_expiry"),
        "auto_renewing": user.get("auto_renewing", False),
        "extra_credits": user.get("extra_credits", 0),
        "limits": limits,
    }


class RestorePurchasesRequest(BaseModel):
    purchases: list  # [{purchase_token, plan_id, platform}]

@api_router.post("/subscription/restore-purchases")
async def restore_purchases(request: RestorePurchasesRequest, user = Depends(get_current_user)):
    """Restore previous purchases after app reinstall"""
    if not request.purchases:
        return {"restored": 0, "message": "No purchases to restore"}

    restored_count = 0
    best_plan = None

    plan_rank = {"pro": 3, "standard": 2, "starter": 1, "free": 0}

    for purchase in request.purchases:
        purchase_token = purchase.get("purchase_token") or purchase.get("purchaseToken")
        plan_id = purchase.get("plan_id") or purchase.get("productId", "").replace("crm_", "").replace("_monthly", "").replace("_yearly", "")
        platform = purchase.get("platform", "android")

        if not purchase_token or not plan_id:
            continue

        if platform == "android":
            verification = await _verify_google_play_purchase(purchase_token, plan_id)
        elif platform == "ios":
            verification = await _verify_apple_receipt(purchase_token)
        else:
            continue

        if verification.get("valid"):
            restored_count += 1
            if not best_plan or plan_rank.get(plan_id, 0) > plan_rank.get(best_plan, 0):
                best_plan = plan_id

    if best_plan:
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {
                "subscription_plan": best_plan,
                "subscription_active": True,
                "subscription_date": user.get("subscription_date") or datetime.utcnow(),
            }}
        )
        logging.info(f"Restored subscription '{best_plan}' for user {user['_id']}")
        return {"restored": restored_count, "plan": best_plan, "message": "Subscription restored successfully"}

    return {"restored": 0, "message": "No valid active subscriptions found"}


@api_router.post("/subscription/rtdn-webhook")
async def google_play_rtdn_webhook(request: Request):
    """
    Google Play Real-Time Developer Notifications (RTDN) webhook.
    Google sends Pub/Sub messages here when subscription state changes.
    Set this URL in Play Console -> Monetize -> Subscriptions -> Real-time notifications.
    """
    try:
        body = await request.json()
        # Pub/Sub message format: {"message": {"data": "<base64>", "messageId": "..."}, "subscription": "..."}
        import base64
        message_data = body.get("message", {}).get("data", "")
        if not message_data:
            return {"status": "ok"}

        decoded = base64.b64decode(message_data).decode("utf-8")
        notification = json.loads(decoded)

        notification_type = notification.get("notificationType")
        purchase_token = notification.get("purchaseToken")
        subscription_id = notification.get("subscriptionId", "")  # e.g. crm_pro_monthly

        logging.info(f"RTDN received: type={notification_type}, sub={subscription_id}")

        if not purchase_token:
            return {"status": "ok"}

        # Find user by purchase token
        user_doc = await db.users.find_one({"purchase_token": purchase_token})
        if not user_doc:
            return {"status": "ok"}

        # notificationType: 1=RECOVERED, 2=RENEWED, 3=CANCELED, 4=PURCHASED,
        #                    5=ON_HOLD, 6=IN_GRACE_PERIOD, 7=RESTARTED, 13=EXPIRED
        ACTIVE_TYPES = {1, 2, 4, 7}    # subscription is active
        INACTIVE_TYPES = {3, 5, 13}     # subscription ended or on hold

        if notification_type in ACTIVE_TYPES:
            plan_id = subscription_id.replace("crm_", "").replace("_monthly", "").replace("_yearly", "")
            await db.users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"subscription_active": True, "subscription_plan": plan_id}}
            )
        elif notification_type in INACTIVE_TYPES:
            await db.users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"subscription_active": False}}
            )

        return {"status": "ok"}

    except Exception as e:
        logging.error(f"RTDN webhook error: {e}")
        return {"status": "ok"}  # Always return 200 to prevent Pub/Sub retries


# Credit top-up bundles: bundle_id -> {credits, price_usd}
CREDIT_BUNDLES = {
    "credits_500":  {"credits": 500,  "price_usd": 2.99,  "label": "500 Credits"},
    "credits_1000": {"credits": 1000, "price_usd": 4.99,  "label": "1,000 Credits"},
    "credits_2500": {"credits": 2500, "price_usd": 9.99,  "label": "2,500 Credits"},
    "credits_5000": {"credits": 5000, "price_usd": 17.99, "label": "5,000 Credits"},
}

class CreditTopUpRequest(BaseModel):
    bundle_id: str
    purchase_token: str
    platform: str  # "android" | "ios"

@api_router.get("/subscription/credit-bundles")
async def get_credit_bundles_list(user = Depends(get_current_user)):
    """Return available credit top-up bundles"""
    return [{"bundle_id": k, **v} for k, v in CREDIT_BUNDLES.items()]

@api_router.post("/subscription/add-credits")
async def add_credits(request: CreditTopUpRequest, user = Depends(get_current_user)):
    """Purchase a credit top-up bundle via IAP"""
    bundle = CREDIT_BUNDLES.get(request.bundle_id)
    if not bundle:
        raise HTTPException(status_code=400, detail="Invalid bundle")

    # Prevent duplicate token usage
    existing = await db.transactions.find_one({"purchase_token": request.purchase_token, "status": "success"})
    if existing:
        raise HTTPException(status_code=400, detail="This purchase has already been redeemed")

    # Server-side receipt verification (reuse same IAP flow)
    if request.platform == "android":
        verification = await _verify_google_play_purchase(request.purchase_token, request.bundle_id)
    elif request.platform == "ios":
        verification = await _verify_apple_receipt(request.purchase_token)
    else:
        raise HTTPException(status_code=400, detail="Invalid platform")

    if not verification.get("valid"):
        raise HTTPException(status_code=403, detail=f"Purchase verification failed: {verification.get('reason', 'unknown')}")

    credits_to_add = bundle["credits"]

    # Add credits to user (never expires, accumulates)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$inc": {"extra_credits": credits_to_add}}
    )

    # Store transaction
    await db.transactions.insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": user["_id"],
        "purchase_token": request.purchase_token,
        "bundle_id": request.bundle_id,
        "credits": credits_to_add,
        "platform": request.platform,
        "type": "credit_topup",
        "verification": verification,
        "status": "success",
        "created_at": datetime.utcnow()
    })

    # Return updated balance
    updated_user = await db.users.find_one({"_id": user["_id"]}, {"extra_credits": 1})
    return {
        "status": "success",
        "credits_added": credits_to_add,
        "total_extra_credits": updated_user.get("extra_credits", 0),
        "message": f"{bundle['label']} added to your account"
    }

# ============ ACCOUNT MANAGEMENT ============

@api_router.delete("/account")
async def delete_account(user = Depends(get_current_user)):
    """
    Permanently delete user account and all associated data.
    Required for GDPR/CCPA compliance and app store policies.
    """
    user_id = user["_id"]

    # Disconnect WhatsApp instance first
    try:
        whatsapp_service = get_whatsapp_service(db)
        await whatsapp_service.disconnect_instance(user_id)
    except Exception as e:
        logging.error(f"Error disconnecting WhatsApp during account deletion: {e}")

    # Delete all user data from every collection
    await db.customers.delete_many({"user_id": user_id})
    await db.messages.delete_many({"user_id": user_id})
    await db.sales.delete_many({"user_id": user_id})
    await db.expenses.delete_many({"user_id": user_id})
    await db.followups.delete_many({"user_id": user_id})
    await db.orders.delete_many({"user_id": user_id})
    await db.products.delete_many({"user_id": user_id})
    await db.broadcasts.delete_many({"user_id": user_id})
    await db.broadcast_templates.delete_many({"user_id": user_id})
    await db.transactions.delete_many({"user_id": user_id})
    await db.customer_analysis.delete_many({"user_id": user_id})
    await db.pending_classifications.delete_many({"user_id": user_id})
    await db.pending_catalogs.delete_many({"user_id": user_id})

    # Delete the user record itself
    await db.users.delete_one({"_id": user_id})

    logging.info(f"Account deleted for user {user_id}")
    return {"status": "success", "message": "Account and all data permanently deleted"}

@api_router.get("/account/export")
async def export_account_data(user = Depends(get_current_user)):
    """
    Export all user data as JSON. Required for GDPR data portability.
    Returns customers, messages, sales, expenses, follow-ups, orders, products.
    """
    user_id = user["_id"]

    customers = await db.customers.find({"user_id": user_id}).to_list(None)
    messages = await db.messages.find({"user_id": user_id}).to_list(None)
    sales = await db.sales.find({"user_id": user_id}).to_list(None)
    expenses = await db.expenses.find({"user_id": user_id}).to_list(None)
    followups = await db.followups.find({"user_id": user_id}).to_list(None)
    orders = await db.orders.find({"user_id": user_id}).to_list(None)
    products = await db.products.find({"user_id": user_id}).to_list(None)

    export = {
        "exported_at": datetime.utcnow().isoformat(),
        "user": {
            "id": user_id,
            "phone_number": user.get("phone_number"),
            "business_name": user.get("business_name"),
            "owner_name": user.get("owner_name"),
            "country_code": user.get("country_code"),
            "created_at": str(user.get("created_at", "")),
        },
        "customers": serialize_doc(customers),
        "messages": serialize_doc(messages),
        "sales": serialize_doc(sales),
        "expenses": serialize_doc(expenses),
        "followups": serialize_doc(followups),
        "orders": serialize_doc(orders),
        "products": serialize_doc(products),
    }

    return export

# ============ WHATSAPP (EVOLUTION API) ENDPOINTS ============

@api_router.post("/whatsapp/connect")
async def whatsapp_connect(request: Request, user = Depends(get_current_user)):
    """
    Start WhatsApp pairing: creates Evolution API instance and returns pairing code.
    User enters the code in WhatsApp > Linked Devices > Link with phone number.
    """
    body = await request.json()
    phone_number = body.get("phone_number", "").strip()
    if not phone_number:
        raise HTTPException(status_code=400, detail="Phone number is required")
    
    whatsapp_service = get_whatsapp_service(db)
    result = await whatsapp_service.create_instance(user["_id"], phone_number)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    
    return result

@api_router.get("/whatsapp/status")
async def whatsapp_status(user = Depends(get_current_user)):
    """Get WhatsApp connection status and message usage"""
    whatsapp_service = get_whatsapp_service(db)
    status = await whatsapp_service.get_instance_status(user["_id"])
    limits = await whatsapp_service.check_message_limit(user["_id"])
    
    return {
        "connected": status.get("connected", False),
        "status": status.get("status", "not_connected"),
        "number": status.get("number"),
        "messages_sent": limits.get("sent", 0),
        "messages_limit": limits.get("limit", 50),
        "messages_remaining": limits.get("remaining", 50),
        "daily_sent": limits.get("daily_sent", 0),
        "daily_limit": limits.get("daily_limit", 500),
        "plan": limits.get("plan", "free"),
    }

@api_router.post("/whatsapp/sync")
async def whatsapp_sync(user = Depends(get_current_user)):
    """
    Manually trigger WhatsApp contact + chat history sync.
    Pulls all contacts and recent conversations from WhatsApp into the CRM.
    Runs in background to avoid Render's 30s idle timeout.
    """
    logging.info(f"WhatsApp sync requested by user {user['_id']}")
    whatsapp_service = get_whatsapp_service(db)
    status = await whatsapp_service.get_instance_status(user["_id"])
    if not status.get("connected"):
        raise HTTPException(status_code=400, detail="WhatsApp not connected. Please make sure WhatsApp is linked first.")

    uid = user["_id"]

    async def _do_full_sync(uid):
        try:
            ws = get_whatsapp_service(db)
            contacts_result = await ws.fetch_contacts(uid)
            logging.info(f"Contact sync result for {uid}: {contacts_result}")
            history_result = await ws.fetch_chat_history(uid)
            logging.info(f"History sync result for {uid}: {history_result}")

            # AI classification
            try:
                classifier = get_classifier(db)
                customers = await db.customers.find({"user_id": uid}).to_list(None)
                for c in customers:
                    msg_count = await db.messages.count_documents({"customer_id": c["_id"], "user_id": uid})
                    if msg_count >= 2:
                        await classifier.classify_contact(uid, c["_id"])
            except Exception as e:
                logging.error(f"Post-sync classification error: {e}")

            # Profile pictures
            try:
                pic_result = await ws.fetch_profile_pictures_bulk(uid)
                logging.info(f"Profile pictures after sync: {pic_result}")
            except Exception as e:
                logging.error(f"Profile picture fetch error after sync: {e}")

            logging.info(f"Full sync complete for user {uid}")
        except Exception as e:
            logging.error(f"Background sync error for {uid}: {e}")

    asyncio.create_task(_do_full_sync(uid))

    # Get current DB totals as a quick snapshot
    total_customers = await db.customers.count_documents({"user_id": uid})
    total_messages = await db.messages.count_documents({"user_id": uid})
    synced_messages = await db.messages.count_documents({"user_id": uid, "synced_from_history": True})

    return {
        "status": "started",
        "message": "Sync started in background. Contacts and chat history will appear in 1-3 minutes.",
        "contacts": {"created": 0, "updated": 0},
        "history": {"chats_synced": 0, "messages_synced": 0},
        "totals": {
            "customers": total_customers,
            "messages": total_messages,
            "synced_messages": synced_messages,
        }
    }


@api_router.get("/customers/{customer_id}/profile-picture")
async def get_customer_profile_picture(customer_id: str, token: str = Query(default=None), request: Request = None):
    """Fetch a fresh profile picture for a customer directly from Evolution API.
    Accepts token as Bearer header OR ?token= query param (needed for React Native Image src).
    """
    from fastapi.responses import Response as FastAPIResponse

    # Resolve token from header or query param
    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[7:]
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = verify_token(raw_token)
    except HTTPException:
        raise

    user = await db.users.find_one({"_id": payload["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    business_id = user.get("business_id", user["_id"])
    customer_full = await db.customers.find_one({"_id": customer_id, "user_id": business_id}, {"phone_number": 1, "profile_picture": 1})
    if not customer_full:
        raise HTTPException(status_code=404, detail="Customer not found")

    async def _bg_upload_to_imgbb(content_bytes: bytes, cust_id: str):
        try:
            import base64
            from image_handler import CloudinaryHandler
            b64 = base64.b64encode(content_bytes).decode('utf-8')
            res = await CloudinaryHandler.upload_base64_to_cloudinary(b64, "profile.jpg")
            perm_url = res.get("image_url")
            if perm_url:
                await db.customers.update_one({"_id": cust_id}, {"$set": {"profile_picture": perm_url}})
                logging.info(f"Permanently stored profile pic for {cust_id} at {perm_url}")
        except Exception as e:
            logging.error(f"Failed to upload profile pic to ImgBB for {cust_id}: {e}")

    async def _proxy_and_upload(url: str, save_to_db: bool = False):
        """Try to fetch an image URL, return Response, and optionally upload to ImgBB."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                img_resp = await client.get(url)
                if img_resp.status_code == 200 and img_resp.headers.get("content-type", "").startswith("image/"):
                    content_bytes = img_resp.content
                    media_type = img_resp.headers.get("content-type", "image/jpeg")
                    
                    if save_to_db and os.environ.get('IMGBB_API_KEY'):
                        import asyncio
                        asyncio.create_task(_bg_upload_to_imgbb(content_bytes, customer_id))

                    return FastAPIResponse(
                        content=content_bytes,
                        media_type=media_type,
                        headers={"Cache-Control": "public, max-age=3600"},
                    )
        except Exception:
            pass
        return None

    # Step 1: Try the stored URL (it may still be valid if fetched recently)
    stored_url = customer_full.get("profile_picture") if customer_full else None
    
    if stored_url:
        if "imgbb.com" in stored_url or "cloudinary.com" in stored_url:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(stored_url)
            
        result = await _proxy_and_upload(stored_url, save_to_db=True)
        if result:
            return result

    # Step 2: Stored URL expired or missing — re-fetch from Evolution API
    whatsapp_service = get_whatsapp_service(db)
    try:
        pic_url = await whatsapp_service.fetch_profile_picture(business_id, customer_full["phone_number"])
    except Exception:
        pic_url = None

    if pic_url:
        await db.customers.update_one({"_id": customer_id}, {"$set": {"profile_picture": pic_url}})
        result = await _proxy_and_upload(pic_url, save_to_db=True)
        if result:
            return result

    raise HTTPException(status_code=404, detail="No profile picture")

@api_router.post("/customers/refresh-profile-pictures")
async def refresh_profile_pictures(user = Depends(get_current_user)):
    """Fetch profile pictures for customers that are missing them"""
    whatsapp_service = get_whatsapp_service(db)
    
    async def _refresh(uid):
        try:
            result = await whatsapp_service.fetch_profile_pictures_bulk(uid)
            logging.info(f"Profile pictures refreshed: {result}")
        except Exception as e:
            logging.error(f"Profile picture refresh error: {e}")
    asyncio.create_task(_refresh(user["_id"]))
    
    return {"status": "started", "message": "Profile pictures are being refreshed in the background."}

@api_router.post("/customers/backfill-names")
async def backfill_contact_names(user = Depends(get_current_user)):
    """
    Fix contacts with fallback names like 'Contact 1234' or raw phone numbers.
    Strategy:
    1. Pull all contacts from Evolution API findContacts (has pushName/name)
    2. Match by phone and update name in DB
    3. For remaining fallbacks, check their stored messages for push_name field
    """
    uid = user.get("business_id", user["_id"])
    wa_user = await db.users.find_one({"_id": uid}, {"whatsapp": 1})
    wa = wa_user.get("whatsapp") if wa_user else None
    if not wa or not wa.get("instance_name"):
        raise HTTPException(status_code=400, detail="WhatsApp not connected")

    instance_name = wa["instance_name"]

    async def _backfill(uid, instance_name):
        updated = 0
        try:
            import httpx as _httpx
            from whatsapp_service import EVOLUTION_API_URL, EVOLUTION_API_KEY
            base_url = EVOLUTION_API_URL.rstrip("/")
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

            # Step 1: Get all contacts from Evolution API with their pushName
            evo_names = {}
            async with _httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{base_url}/chat/findContacts/{instance_name}",
                    headers=headers,
                    json={"where": {}},
                )
                if resp.status_code == 200:
                    contacts = resp.json()
                    if not isinstance(contacts, list):
                        contacts = contacts.get("contacts", contacts.get("data", []))
                    for c in contacts:
                        jid = c.get("remoteJid", "")
                        name = c.get("pushName") or c.get("name") or c.get("notify") or ""
                        if "@s.whatsapp.net" in jid and name:
                            # Store by raw digits (no + prefix) for reliable matching
                            digits = jid.replace("@s.whatsapp.net", "").strip()
                            evo_names[digits] = name

            logging.info(f"Backfill: Evolution API returned {len(evo_names)} named contacts")

            # Step 2: Find all customers with fallback names
            fallback_customers = await db.customers.find({
                "user_id": uid,
                "$or": [
                    {"name": {"$regex": "^Contact [0-9]"}},
                    {"name": {"$regex": "^[+][0-9]"}},
                    {"name": ""},
                    {"name": None},
                ]
            }, {"_id": 1, "phone_number": 1, "name": 1}).to_list(None)

            logging.info(f"Backfill: {len(fallback_customers)} customers with fallback names")

            for cust in fallback_customers:
                raw_phone = cust.get("phone_number", "")
                # Normalize to raw digits for matching
                digits = raw_phone.lstrip("+").replace(" ", "").replace("-", "")
                new_name = evo_names.get(digits, "")

                if not new_name:
                    # Try finding pushName from stored messages
                    msg = await db.messages.find_one(
                        {"customer_id": cust["_id"], "user_id": uid,
                         "push_name": {"$exists": True, "$ne": ""}},
                        sort=[("created_at", -1)]
                    )
                    if msg:
                        new_name = msg.get("push_name", "")

                if new_name and not new_name.startswith("Contact "):
                    await db.customers.update_one(
                        {"_id": cust["_id"]},
                        {"$set": {"name": new_name}}
                    )
                    updated += 1

            logging.info(f"Backfill names complete: updated {updated} contacts for user {uid}")
        except Exception as e:
            logging.error(f"Backfill names error: {e}")

    asyncio.create_task(_backfill(uid, instance_name))
    return {"status": "started", "message": "Contact name backfill running in background."}

@api_router.post("/whatsapp/disconnect")
async def whatsapp_disconnect(user = Depends(get_current_user)):
    """Disconnect and remove WhatsApp instance"""
    whatsapp_service = get_whatsapp_service(db)
    result = await whatsapp_service.disconnect_instance(user["_id"])
    return result

# ============ MARK MESSAGES AS READ ============

@api_router.post("/customers/{customer_id}/messages/read")
async def mark_messages_read(customer_id: str, user = Depends(get_current_user)):
    """Mark all incoming messages for a customer as read"""
    business_id = user.get("business_id", user["_id"])
    result = await db.messages.update_many(
        {"customer_id": customer_id, "user_id": business_id, "direction": "incoming", "read": {"$ne": True}},
        {"$set": {"read": True}}
    )
    return {"marked_read": result.modified_count}

# ============ DASHBOARD SUMMARY ============

@api_router.get("/dashboard/summary")
async def get_dashboard_summary(user = Depends(get_current_user)):
    """Get a quick dashboard summary: unread messages, today's follow-ups, today's sales"""
    uid = user.get("business_id", user["_id"])
    
    # Get user's timezone offset (default to UTC+3 for Kenya if not set)
    user_doc = await db.users.find_one({"_id": uid})
    tz_offset_hours = 3  # Default to EAT (East Africa Time)
    if user_doc and user_doc.get("timezone_offset"):
        tz_offset_hours = user_doc["timezone_offset"]
    
    # Calculate "today" in user's local timezone
    utc_now = datetime.utcnow()
    local_now = utc_now + timedelta(hours=tz_offset_hours)
    local_today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_today_end = local_today_start + timedelta(days=1)
    
    # Convert back to UTC for database queries
    today_start_utc = local_today_start - timedelta(hours=tz_offset_hours)
    today_end_utc = local_today_end - timedelta(hours=tz_offset_hours)

    # Total unread messages — only from confirmed customers (is_customer: True)
    customer_ids_for_unread = await db.customers.distinct(
        "_id",
        {"user_id": uid, "is_customer": True}
    )
    unread_count = await db.messages.count_documents({
        "user_id": uid, "direction": "incoming", "read": {"$ne": True},
        "customer_id": {"$in": customer_ids_for_unread}
    })

    # All pending follow-up reminders (overdue + today + future)
    pending_reminders = await db.followups.count_documents({
        "user_id": uid, "status": "pending"
    })

    # Cold customers needing attention (7+ days no contact)
    cutoff_7days = utc_now - timedelta(days=7)
    cold_count = await db.customers.count_documents({
        "user_id": uid,
        "$and": [
            {"$or": [{"is_customer": True}, {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}]},
            {"$or": [{"last_contacted": {"$lt": cutoff_7days}}, {"last_contacted": None}, {"last_contacted": {"$exists": False}}]}
        ]
    })
    followups_today = pending_reminders + min(cold_count, 30)  # needs-attention shows max 30

    # Today's sales total (using user's local "today")
    sales_pipeline = [
        {"$match": {"user_id": uid, "created_at": {"$gte": today_start_utc, "$lt": today_end_utc}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    sales_result = await db.sales.aggregate(sales_pipeline).to_list(1)
    sales_today = sales_result[0]["total"] if sales_result else 0
    sales_count = sales_result[0]["count"] if sales_result else 0

    # Today's bookings count (appointments scheduled for today)
    today_date_str = local_now.strftime("%Y-%m-%d")
    bookings_today = await db.bookings.count_documents({
        "user_id": uid,
        "date": today_date_str,
        "status": {"$in": ["pending", "confirmed"]}
    })

    # Total customers (confirmed only, not raw contacts)
    total_customers = await db.customers.count_documents({
        "user_id": uid,
        "$or": [{"is_customer": True}, {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}]
    })

    return {
        "unread_messages": unread_count,
        "followups_today": followups_today,
        "sales_today": sales_today,
        "sales_count_today": sales_count,
        "bookings_today": bookings_today,
        "total_customers": total_customers,
    }

# ============ MESSAGE SEARCH ============

@api_router.get("/customers/{customer_id}/messages/search")
async def search_messages(customer_id: str, q: str = "", user = Depends(get_current_user)):
    """Search messages within a customer conversation"""
    business_id = user.get("business_id", user["_id"])
    if not q.strip():
        return []
    messages = await db.messages.find({
        "customer_id": customer_id,
        "user_id": business_id,
        "content": {"$regex": q, "$options": "i"}
    }).sort("created_at", -1).limit(50).to_list(50)
    return serialize_doc(messages)

# ============ CUSTOMER ACTIVITY TIMELINE ============

@api_router.get("/customers/{customer_id}/timeline")
async def get_customer_timeline(customer_id: str, user = Depends(get_current_user)):
    """Get a unified timeline of all activities for a customer"""
    uid = user.get("business_id", user["_id"])

    # Fetch messages (last 20)
    messages = await db.messages.find({
        "customer_id": customer_id, "user_id": uid
    }).sort("created_at", -1).limit(20).to_list(20)

    # Fetch sales
    sales = await db.sales.find({
        "customer_id": customer_id, "user_id": uid
    }).sort("created_at", -1).limit(10).to_list(10)

    # Fetch follow-ups
    followups = await db.followups.find({
        "customer_id": customer_id, "user_id": uid
    }).sort("created_at", -1).limit(10).to_list(10)

    timeline = []
    for m in messages:
        timeline.append({
            "type": "message",
            "direction": m.get("direction"),
            "content": m.get("content", "")[:200],
            "created_at": m.get("created_at"),
        })
    for s in sales:
        timeline.append({
            "type": "sale",
            "content": f"{s.get('item', 'Sale')} - {s.get('amount', 0)}",
            "created_at": s.get("created_at"),
        })
    for f in followups:
        timeline.append({
            "type": "followup",
            "content": f.get("message", "Follow-up"),
            "status": f.get("status", "pending"),
            "created_at": f.get("reminder_date") or f.get("created_at"),
        })

    # Sort by date descending
    timeline.sort(key=lambda x: x.get("created_at") or datetime.min, reverse=True)
    return serialize_doc(timeline[:50])

@api_router.post("/messages/send-media")
async def send_whatsapp_media(
    file: UploadFile = File(...),
    to_number: str = Form(...),
    caption: str = Form(""),
    customer_name: Optional[str] = Form(None),
    user = Depends(get_current_user)
):
    """
    Upload and send a media file (image or document) to a customer via WhatsApp.
    """
    try:
        from image_handler import ImageUploadHandler
        
        # Determine media type from file extension/content type
        filename = file.filename or "file"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        image_exts = {"jpg", "jpeg", "png", "webp", "gif"}
        is_image = ext in image_exts
        media_type = "image" if is_image else "document"
        
        # Upload to get a public URL
        try:
            result = await ImageUploadHandler.upload_to_cloudinary(file)
            media_url = result["image_url"]
        except Exception:
            # Fallback: save locally
            await file.seek(0)
            content = await file.read()
            import aiofiles
            from pathlib import Path
            upload_dir = Path(__file__).parent / "uploads" / "media"
            upload_dir.mkdir(parents=True, exist_ok=True)
            unique_name = f"{uuid.uuid4()}.{ext}" if ext else f"{uuid.uuid4()}"
            file_path = upload_dir / unique_name
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            server_url = os.environ.get("SERVER_URL", "").rstrip("/")
            media_url = f"{server_url}/uploads/media/{unique_name}" if server_url else f"/uploads/media/{unique_name}"
        
        # Normalize URL so Docker (Evolution API) can reach it
        media_url = normalize_url(media_url)

        business_id = user.get("business_id", user["_id"])
        whatsapp_service = get_whatsapp_service(db)
        send_result = await whatsapp_service.send_message(
            user_id=business_id,
            to_number=to_number,
            message=caption,
            customer_name=customer_name,
            media_url=media_url,
            media_type=media_type,
            media_filename=filename,
            send_context="product_send",
        )
        if send_result.get("status") == "limit_reached":
            raise HTTPException(status_code=429, detail=send_result.get("message"))
        return send_result
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error sending media: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/messages/send")
async def send_whatsapp_message(to_number: str, message: str, customer_name: Optional[str] = None, user = Depends(get_current_user)):
    """
    Send WhatsApp message to a customer via Evolution API.
    Auto-creates contact if number doesn't exist. Enforces rate limits.
    Auto-assigns conversation to employee on first reply if unassigned.
    """
    try:
        business_id = user.get("business_id", user["_id"])
        
        # Find customer to check assignment
        customer = await db.customers.find_one({
            "user_id": business_id,
            "phone_number": to_number
        })
        
        # Auto-assign on first reply if unassigned
        if customer:
            assignment = await db.conversation_assignments.find_one({
                "business_id": business_id,
                "customer_id": customer["_id"]
            })
            
            # If no assignment exists and user is employee/manager, auto-assign
            if not assignment and user.get("role") in ["employee", "manager"]:
                await db.conversation_assignments.insert_one({
                    "customer_id": customer["_id"],
                    "business_id": business_id,
                    "assigned_to": user["_id"],
                    "assigned_by": user["_id"],
                    "assigned_at": datetime.utcnow(),
                    "notes": "Auto-assigned on first reply"
                })
                
                # Log activity
                await log_activity(
                    business_id=business_id,
                    user_id=user["_id"],
                    user_name=user.get("owner_name", user.get("business_name", "User")),
                    action="conversation_auto_assigned",
                    entity_type="conversation",
                    entity_id=customer["_id"],
                    details={"customer_name": customer.get("name", "Unknown")}
                )
                
                logging.info(f"Auto-assigned customer {customer['_id']} to user {user['_id']}")
        
        whatsapp_service = get_whatsapp_service(db)
        result = await whatsapp_service.send_message(
            user_id=business_id,  # Use business_id for WhatsApp instance
            to_number=to_number,
            message=message,
            customer_name=customer_name
        )
        if result.get("status") == "limit_reached":
            raise HTTPException(status_code=429, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ EVOLUTION API WEBHOOK ============

# Webhook secret for verifying Evolution API callbacks
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', os.environ.get('EVOLUTION_API_KEY', ''))

@api_router.post("/webhooks/evolution")
async def evolution_webhook(request: Request):
    """
    Receive webhooks from Evolution API.
    Handles: connection.update, messages.upsert
    Configure in Evolution API: webhook URL = https://your-domain/api/webhooks/evolution
    """
    def log_trace(msg):
        try:
            with open("trace.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.utcnow().isoformat()} - {msg}\n")
        except:
            pass

    log_trace("Webhook received")

    # Verify webhook authenticity via API key header or query param
    incoming_key = (
        request.headers.get("apikey")
        or request.headers.get("x-webhook-secret")
        or request.query_params.get("key")
    )
    if WEBHOOK_SECRET and incoming_key and incoming_key != WEBHOOK_SECRET:
        logging.warning(f"Webhook auth failed: got key={incoming_key!r}")
        raise HTTPException(status_code=401, detail="Unauthorized webhook")

    try:
        payload = await request.json()
        raw_event = payload.get("event", "")
        instance_name = payload.get("instance", "")
        data = payload.get("data", payload)
        
        # Normalize event name: Evolution API may send "messages.update" or "MESSAGES_UPDATE"
        event = raw_event.lower().replace("_", ".")
        
        logging.info(f"Evolution webhook: raw_event={raw_event!r}, normalized={event!r}, instance={instance_name}")
        
        
        whatsapp_service = get_whatsapp_service(db)
        
        # Handle connection status changes
        if event == "connection.update":
            await whatsapp_service.handle_connection_update(instance_name, data)

            # When WhatsApp first connects, sync contacts and chat history in background
            state = data.get("state") or data.get("instance", {}).get("state", "")
            if state == "open":
                user = await whatsapp_service.find_user_by_instance(instance_name)
                if user:
                    user_id = user["_id"]
                    # Check if this is first sync (no synced_contacts flag)
                    if not user.get("whatsapp", {}).get("initial_sync_done"):
                        async def _run_initial_sync(uid):
                            try:
                                logging.info(f"Starting initial WhatsApp sync for user {uid}")
                                contacts_result = await whatsapp_service.fetch_contacts(uid)
                                logging.info(f"Contact sync: {contacts_result}")
                                history_result = await whatsapp_service.fetch_chat_history(uid)
                                logging.info(f"History sync: {history_result}")
                                # Mark sync as done so we don't re-run
                                await db.users.update_one(
                                    {"_id": uid},
                                    {"$set": {"whatsapp.initial_sync_done": True}}
                                )
                                # Run AI classification on all synced contacts — auto-promotes high-confidence ones
                                try:
                                    classifier = get_classifier(db)
                                    contacts = await db.customers.find({"user_id": uid, "synced_from_whatsapp": True}).to_list(None)
                                    promoted = 0
                                    pending = 0
                                    for c in contacts:
                                        try:
                                            msg_count = await db.messages.count_documents({"customer_id": c["_id"], "user_id": uid})
                                            if msg_count >= 2:
                                                await classifier.classify_single_on_message(uid, c["_id"])
                                                # Check if it got auto-promoted
                                                updated = await db.customers.find_one({"_id": c["_id"]})
                                                if updated and updated.get("classification_confirmed"):
                                                    promoted += 1
                                                else:
                                                    pending += 1
                                        except Exception as _ce:
                                            logging.warning(f"classify_single_on_message failed for {c['_id']}: {_ce}")
                                    logging.info(f"Initial sync classification: {promoted} auto-promoted, {pending} pending review")
                                except Exception as cls_err:
                                    logging.error(f"Post-sync classification error: {cls_err}")
                                
                                # Fetch profile pictures
                                try:
                                    logging.info("Starting profile picture sync...")
                                    pic_result = await whatsapp_service.fetch_profile_pictures_bulk(uid)
                                    logging.info(f"Profile pic sync: {pic_result}")
                                except Exception as pic_err:
                                    logging.error(f"Profile pic sync error: {pic_err}")

                                # Auto-purge any invalid contacts that slipped through
                                try:
                                    await _purge_invalid_contacts_for_user(uid)
                                except Exception as purge_err:
                                    logging.error(f"Post-sync purge error: {purge_err}")

                            except Exception as sync_err:
                                logging.error(f"Initial sync failed for user {uid}: {sync_err}")

                        asyncio.create_task(_run_initial_sync(user_id))

            return {"status": "ok"}
        
        # Handle message status updates (sent/delivered/read receipts)
        if event == "messages.update":
            import json as _json
            logging.info(f"messages.update payload: {_json.dumps(data, default=str)[:800]}")
            await whatsapp_service.handle_message_update(instance_name, data)
            return {"status": "ok"}

        # Handle chats.update — fired when a chat is read on native WhatsApp
        if event == "chats.update":
            import json as _json2
            logging.info(f"chats.update payload: {_json2.dumps(data, default=str)[:800]}")
            user = await whatsapp_service.find_user_by_instance(instance_name)
            if user:
                updates = data if isinstance(data, list) else [data]
                for upd in updates:
                    inner = upd.get("data", upd)
                    unread = inner.get("unreadCount", inner.get("unreadMessages", None))
                    remote_jid = inner.get("id") or inner.get("remoteJid") or inner.get("jid") or ""
                    if unread in (0, None) and remote_jid and "@g.us" not in remote_jid:
                        # Look up customer by remote_jid on messages or by lid_jid
                        sample = await db.messages.find_one({
                            "user_id": user["_id"],
                            "remote_jid": remote_jid,
                            "direction": "incoming",
                        })
                        cid = sample.get("customer_id") if sample else None
                        if not cid:
                            cust = await db.customers.find_one({
                                "user_id": user["_id"],
                                "lid_jid": remote_jid,
                            })
                            if cust:
                                cid = cust["_id"]
                        if cid:
                            res = await db.messages.update_many(
                                {"user_id": user["_id"], "customer_id": cid, "direction": "incoming", "read": {"$ne": True}},
                                {"$set": {"read": True}}
                            )
                            if res.modified_count:
                                logging.info(f"chats.update: marked {res.modified_count} messages read for jid={remote_jid}")
            return {"status": "ok"}

        # Handle incoming AND outgoing messages
        if event == "messages.upsert":
            parsed = await whatsapp_service.handle_incoming_message(instance_name, data)
            
            if not parsed:
                log_trace("Parsed is empty/None")
                return {"status": "ok"}
            
            # === DEDUPLICATION GUARD ===
            # We must check this BEFORE any processing (including dynamic matching)
            import time as _time
            import hashlib as _hl
            
            _evo_id = parsed.get("evo_message_id", "")
            _body_content = parsed.get("body", "") or ""
            _u_id = parsed.get("user", {}).get("_id", "unknown")
            _cust_id_dedup = parsed.get("from_number", "unknown")
            
            # Dedup guard: Evolution API fires messages.upsert multiple times per message
            _dedup_key = _evo_id if _evo_id else f"{_u_id}:{_cust_id_dedup}:{_hl.md5(_body_content.encode()).hexdigest()[:16]}"
            
            async with _auto_reply_lock:
                _now = _time.time()
                # Clean old entries
                _expired = [k for k, v in _auto_reply_dedup.items() if _now - v > _AUTO_REPLY_DEDUP_TTL]
                for k in _expired:
                    del _auto_reply_dedup[k]
                
                if _dedup_key in _auto_reply_dedup:
                    logging.info(f"Webhook dedup: skipping duplicate key={_dedup_key[:30]}")
                    return {"status": "ok"}
                
                # Mark as seen
                _auto_reply_dedup[_dedup_key] = _now
            # === END DEDUPLICATION GUARD ===

            log_trace(f"Parsed body: {parsed.get('body')}")
            
            user = parsed["user"]
            from_number = parsed["from_number"]
            body = parsed["body"]
            push_name = parsed["push_name"]
            from_me = parsed.get("from_me", False)
            evo_msg_id_log = parsed.get("evo_message_id", "?")
            direction = "outgoing" if from_me else "incoming"
            parsed_message_type = parsed.get("message_type", "text")
            parsed_image_url = parsed.get("image_url")
            print(f"DEBUG: Webhook received. Direction={direction}, Body='{body}'")
            logging.info(f"messages.upsert: direction={direction}, from={from_number}, evo_id={evo_msg_id_log}, body={body[:60]}")

            # For incoming messages: fire blue-tick read receipt back to Evolution API immediately
            if not from_me:
                _remote_jid = parsed.get("remote_jid", "")
                _evo_msg_id = parsed.get("evo_message_id", "")
                _wa = (await db.users.find_one({"_id": user["_id"]}, {"whatsapp": 1}) or {}).get("whatsapp", {})
                _inst = _wa.get("instance_name", "")
                if _inst and _remote_jid and _evo_msg_id:
                    asyncio.create_task(
                        whatsapp_service.mark_as_read(_inst, _remote_jid, _evo_msg_id)
                    )
            
            # Find or create customer (the contact on the other end)
            customer = await db.customers.find_one({
                "user_id": user["_id"],
                "phone_number": from_number
            })
            
            customer_id = None
            customer_name = push_name or f"Contact {from_number[-4:]}"
            
            if customer:
                print(f"DEBUG: Customer found: {customer['name']}")
                customer_id = customer["_id"]
                customer_name = customer.get("name", customer_name)
                remote_jid_val = parsed.get("remote_jid", "")
                lid_update = {}
                if remote_jid_val and "@lid" in remote_jid_val and not customer.get("lid_jid"):
                    lid_update["lid_jid"] = remote_jid_val
                await db.customers.update_one(
                    {"_id": customer["_id"]},
                    {"$set": {
                        "last_message": body[:200] if body else None,
                        "last_contacted": datetime.utcnow(),
                        **lid_update,
                    }}
                )
            else:
                print(f"DEBUG: New customer auto-created")
                customer_id = str(uuid.uuid4())
                await db.customers.insert_one({
                    "_id": customer_id,
                    "user_id": user["_id"],
                    "name": customer_name,
                    "phone_number": from_number,
                    "notes": "",
                    "tags": ["New"],
                    "last_message": body[:200] if body else None,
                    "last_contacted": datetime.utcnow(),
                    "created_at": datetime.utcnow(),
                    "auto_created": True,
                    "is_customer": False,
                    "customer_initiated": not from_me,
                })
                logging.info(f"Auto-created contact from WhatsApp: {customer_name} ({from_number})")
                
                # Fetch profile picture in background for new contact
                async def _fetch_pic(uid, cid, phone):
                    try:
                        ws = get_whatsapp_service(db)
                        pic_url = await ws.fetch_profile_picture(uid, phone)
                        if pic_url:
                            await db.customers.update_one(
                                {"_id": cid},
                                {"$set": {"profile_picture": pic_url}}
                            )
                            logging.info(f"Profile picture set for new contact {phone}")
                    except Exception as e:
                        logging.debug(f"Could not fetch profile pic for new contact {phone}: {e}")
                asyncio.create_task(_fetch_pic(user["_id"], customer_id, from_number))

                # Notify owner of new contact messaging for the first time
                async def _notify_owner_new_contact(owner_user, cust_name, cust_phone, msg_body):
                    try:
                        owner_phone = owner_user.get("phone_number") or owner_user.get("whatsapp", {}).get("phone_number")
                        if not owner_phone:
                            return
                        # Don't notify if owner IS the new contact (self-message edge case)
                        if owner_phone == cust_phone:
                            return
                        ws = get_whatsapp_service(db)
                        preview = msg_body[:100] + ("..." if len(msg_body) > 100 else "")
                        notification = (
                            f"🆕 *New contact just messaged you!*\n\n"
                            f"👤 *{cust_name}*\n"
                            f"📱 {cust_phone}\n\n"
                            f"💬 _{preview}_\n\n"
                            f"Open your CRM app to view and reply."
                        )
                        await ws.send_message(
                            user_id=owner_user["_id"],
                            to_number=owner_phone,
                            message=notification,
                            send_context="auto_reply"
                        )
                        logging.info(f"Owner notified of new contact: {cust_name} ({cust_phone})")
                    except Exception as e:
                        logging.error(f"Failed to notify owner of new contact: {e}")

                asyncio.create_task(_notify_owner_new_contact(user, customer_name, from_number, body))

                # Also send Expo push notification to owner's device(s)
                async def _push_new_contact(owner_id, cust_name, msg_body):
                    try:
                        preview = msg_body[:80] + ("..." if len(msg_body) > 80 else "")
                        await send_push_notification(
                            user_id=owner_id,
                            title=f"🆕 New contact: {cust_name}",
                            body=preview,
                            data={"type": "new_contact", "contact_name": cust_name}
                        )
                    except Exception as e:
                        logging.error(f"Push for new contact failed: {e}")

                asyncio.create_task(_push_new_contact(user["_id"], customer_name, body))

            # Store message (both incoming and outgoing)
            if customer_id and body:
                evo_msg_id = parsed.get("evo_message_id", "")
                
                # For outgoing messages, check if already stored by send_message()
                # (auto-replies and manual sends store the message before the webhook arrives)
                if from_me and evo_msg_id:
                    existing = await db.messages.find_one({
                        "evo_message_id": evo_msg_id,
                        "user_id": user["_id"],
                    })
                    if existing:
                        print(f"DEBUG: Outgoing message already exists, skipping AI")
                        return {"status": "ok"}
                
                message_id = str(uuid.uuid4())
                msg_doc = {
                    "_id": message_id,
                    "customer_id": customer_id,
                    "user_id": user["_id"],
                    "direction": direction,
                    "content": body,
                    "message_type": parsed.get("message_type", "text"),
                    "from_number": from_number,
                    "created_at": datetime.utcnow(),
                }
                
                # Add image URL if present
                if parsed.get("image_url"):
                    msg_doc["image_url"] = parsed["image_url"]
                # Store original filename for documents
                if parsed.get("file_name"):
                    msg_doc["file_name"] = parsed["file_name"]
                if evo_msg_id:
                    msg_doc["evo_message_id"] = evo_msg_id
                remote_jid = parsed.get("remote_jid", "")
                if remote_jid:
                    msg_doc["remote_jid"] = remote_jid
                await db.messages.insert_one(msg_doc)

                # Always update last_contacted + last_message regardless of direction
                # This ensures native WhatsApp conversations keep the customer active
                await db.customers.update_one(
                    {"_id": customer_id},
                    {"$set": {
                        "last_contacted": datetime.utcnow(),
                        "last_message": body[:200] if body else "",
                    }}
                )

                # For outgoing messages (typed in WhatsApp), just store — no auto-reply needed
                if from_me:
                    # Mark all unread incoming messages from this customer as read,
                    # since replying means you've already read them on native WhatsApp
                    await db.messages.update_many(
                        {"user_id": user["_id"], "customer_id": customer_id, "direction": "incoming", "read": {"$ne": True}},
                        {"$set": {"read": True}}
                    )
                    # Clear needs_human flag — business owner just replied manually,
                    # so AI can resume auto-replying on the next incoming message
                    if customer and customer.get("needs_human"):
                        await db.customers.update_one(
                            {"_id": customer_id},
                            {"$set": {"needs_human": False, "needs_human_reason": "", "needs_human_cleared_at": datetime.utcnow()}}
                        )
                        logging.info(f"needs_human cleared for {customer_name} ({from_number}) — owner replied manually")
                    return {"status": "ok"}
                
                # Auto-classify contact in background (customer vs supplier)
                try:
                    classifier = get_classifier(db)
                    asyncio.create_task(
                        classifier.classify_single_on_message(user["_id"], customer_id)
                    )
                except Exception as classify_err:
                    logging.error(f"Classification error: {classify_err}")

                # Notify assigned employee of incoming message (background)
                async def _notify_assigned_employee(business_id, cust_id, cust_name, msg_body):
                    try:
                        assignment = await db.conversation_assignments.find_one({
                            "business_id": business_id,
                            "customer_id": cust_id
                        })
                        if not assignment:
                            return  # Unassigned — no specific notification needed

                        assigned_user_id = assignment.get("assigned_to")
                        if not assigned_user_id:
                            return

                        # Find the team member record to get their phone number
                        member = await db.team_members.find_one({
                            "business_id": business_id,
                            "user_id": assigned_user_id,
                            "status": "active"
                        })
                        if not member or not member.get("phone_number"):
                            return

                        # Send WhatsApp notification to the assigned employee
                        ws = get_whatsapp_service(db)
                        preview = msg_body[:80] + ("..." if len(msg_body) > 80 else "")
                        notification = (
                            f"💬 *New message from {cust_name}*\n\n"
                            f"_{preview}_\n\n"
                            f"Open your CRM app to reply."
                        )
                        await ws.send_message(
                            user_id=business_id,
                            to_number=member["phone_number"],
                            message=notification,
                            send_context="auto_reply"
                        )
                        logging.info(f"Notified employee {assigned_user_id} of message from {cust_name}")
                    except Exception as e:
                        logging.error(f"Failed to notify assigned employee: {e}")

                asyncio.create_task(
                    _notify_assigned_employee(user["_id"], customer_id, customer_name, body)
                )

                # AI↔AI loop guard: our auto-replies carry an invisible \u200B marker.
                # If an incoming message contains it, it was sent by another AI — skip.
                if "\u200B" in (body or ""):
                    logging.info(f"Auto-reply BLOCKED: AI signature detected from {from_number}")
                    return {"status": "ok", "message": "loop guard: AI signature"}

                # ============================================================
                # PAYMENT PROOF IMAGE HANDLER — customer sent photo while awaiting payment
                # ============================================================
                if not from_me and parsed_message_type == "image" and parsed_image_url:
                    _pending_del = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "delivery_pending"
                    })
                    if _pending_del:
                        _proof_order_id = _pending_del.get("order_id")
                        if _proof_order_id:
                            await db.orders.update_one(
                                {"_id": _proof_order_id},
                                {"$set": {"payment_proof": parsed_image_url, "payment_proof_at": datetime.utcnow()}}
                            )
                            _proof_order = await db.orders.find_one({"_id": _proof_order_id}, {"order_number": 1})
                            _proof_order_num = (_proof_order or {}).get("order_number", _proof_order_id[:8].upper())
                            ws = get_whatsapp_service(db)
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message=(
                                    f"📸 *Payment screenshot received!* Thank you.\n\n"
                                    f"Order *#{_proof_order_num}* is awaiting verification by our team. "
                                    f"We will notify you once your payment is confirmed and your order is being processed. 🙏"
                                ),
                                customer_name=customer_name, send_context="payment_proof"
                            )
                            _biz_id_proof = user.get("business_id", user["_id"])
                            try:
                                await send_push_notification(
                                    user_id=_biz_id_proof,
                                    title="💳 Payment Proof Received!",
                                    body=f"{customer_name} sent payment proof for order #{_proof_order_num}",
                                    data={"type": "payment_proof", "order_id": _proof_order_id}
                                )
                            except Exception as _proof_push_err:
                                logging.warning(f"Payment proof push failed: {_proof_push_err}")
                            logging.info(f"Payment proof saved for order {_proof_order_id}")
                            return {"status": "ok", "handled_by": "payment_proof"}

                # ============================================================
                # BUTTON RESPONSE HANDLER — detect and process button clicks
                # ============================================================
                # Check if this is a button response (button IDs follow pattern: action_productid)
                button_patterns = {
                    "order_": "order",
                    "buy_": "order",
                    "cart_": "add_to_cart",
                    "checkout_cart": "checkout",
                    "continue_shopping": "continue",
                    "details_": "details",
                    "select_": "select",
                    "ask_": "ask",
                    "question_": "ask",
                    "share_": "share",
                }
                
                button_action = None
                button_product_id = None
                
                for prefix, action in button_patterns.items():
                    if body and body.startswith(prefix):
                        button_action = action
                        button_product_id = body.replace(prefix, "")
                        logging.info(f"Button click detected: action={action}, product_id={button_product_id}")
                        break
                
                # NUMBERED REPLY HANDLER — customer replies "1", "2", "3" / "One" / "moja" to action text
                if not button_action and not from_me and body:
                    _body_stripped = body.strip()
                    _body_lower = _body_stripped.lower()
                    # Accept plain digits, emoji keycap digits, written numbers (multilingual)
                    _num_map = {
                        # Digits 1-16 (extended for time slot menus)
                        "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
                        "6": 6, "7": 7, "8": 8, "9": 9,
                        "10": 10, "11": 11, "12": 12, "13": 13,
                        "14": 14, "15": 15, "16": 16,
                        # Emoji keycap digits
                        "0\ufe0f\u20e3": 0, "1\ufe0f\u20e3": 1, "2\ufe0f\u20e3": 2, "3\ufe0f\u20e3": 3,
                        "4\ufe0f\u20e3": 4, "5\ufe0f\u20e3": 5, "6\ufe0f\u20e3": 6,
                        "7\ufe0f\u20e3": 7, "8\ufe0f\u20e3": 8, "9\ufe0f\u20e3": 9,
                        # English words
                        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                        "six": 6, "seven": 7, "eight": 8, "nine": 9,
                        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
                        "the first": 1, "the second": 2, "the third": 3,
                        "first one": 1, "second one": 2, "third one": 3,
                        "option 1": 1, "option 2": 2, "option 3": 3, "option 4": 4, "option 5": 5,
                        "number 1": 1, "number 2": 2, "number 3": 3, "number 4": 4, "number 5": 5,
                        "no 1": 1, "no 2": 2, "no 3": 3, "no. 1": 1, "no. 2": 2, "no. 3": 3,
                        "#1": 1, "#2": 2, "#3": 3, "#4": 4, "#5": 5,
                        # Swahili
                        "sifuri": 0, "moja": 1, "mbili": 2, "tatu": 3, "nne": 4, "tano": 5,
                        "ya kwanza": 1, "ya pili": 2, "ya tatu": 3,
                        "chaguo 1": 1, "chaguo 2": 2, "chaguo 3": 3,
                        # French
                        "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
                        "premier": 1, "deuxième": 2, "troisième": 3,
                        # Arabic numerals (common in mixed contexts)
                        "١": 1, "٢": 2, "٣": 3, "٤": 4, "٥": 5,
                    }
                    _reply_num = _num_map.get(_body_lower) or _num_map.get(_body_stripped)
                    if _reply_num is not None:
                        # Check if customer has pending order list — if so, skip catalog handler and let OrderAgent handle it
                        _conv_state_check = await db.conversation_states.find_one({
                            "customer_id": str(customer_id), "user_id": user["_id"]
                        })
                        if _conv_state_check and (
                            _conv_state_check.get("pending_order_list") or
                            _conv_state_check.get("pending_order_action") or
                            _conv_state_check.get("pending_update_step") or
                            _conv_state_check.get("pending_booking_list") or
                            _conv_state_check.get("pending_booking_action")
                        ):
                            # Customer is interacting with an order or booking — don't intercept, let agent handle it
                            logging.info(f"Numbered reply {_reply_num} with pending order/booking state — passing to agent")
                        else:
                            _pending_cat = await db.pending_catalogs.find_one({
                                "customer_id": customer_id, "user_id": user["_id"]
                            })
                            if _pending_cat:
                                _ctx = _pending_cat.get("action_context", "product")

                                if _ctx == "catalog_select":
                                    _cat_products = _pending_cat.get("products", [])
                                    _biz_id_cs = user.get("business_id", user["_id"])
                                    # Check if customer wants next page (reply=9 and has_more=True)
                                    if _reply_num == 9 and _pending_cat.get("has_more"):
                                        _all_ids = _pending_cat.get("all_product_ids", [])
                                        _cur_offset = _pending_cat.get("page_offset", 0)
                                        _new_offset = _cur_offset + 8
                                        _next_ids = _all_ids[_new_offset:_new_offset + 8]
                                        _new_has_more = len(_all_ids) > _new_offset + 8
                                        _page_num = (_new_offset // 8) + 1
                                        # Fetch next page products from DB
                                        _next_products = []
                                        for _pid in _next_ids:
                                            _np = await db.products.find_one({"_id": _pid, "user_id": _biz_id_cs})
                                            if _np:
                                                _next_products.append(_np)
                                        if _next_products:
                                            _currency_pg = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                            _next_with_curr = [{"currency": _currency_pg, **_np} for _np in _next_products]
                                            ws = get_whatsapp_service(db)
                                            await ws.send_product_list(
                                                user_id=user["_id"],
                                                to_number=from_number,
                                                title="Our Products",
                                                products=_next_with_curr,
                                                has_more=_new_has_more,
                                                page_num=_page_num
                                            )
                                            await db.pending_catalogs.update_one(
                                                {"customer_id": customer_id, "user_id": user["_id"]},
                                                {"$set": {
                                                    "products": [{"id": _np["_id"], "name": _np["name"],
                                                                  "price": _np.get("price", 0), "index": i}
                                                                 for i, _np in enumerate(_next_products, 1)],
                                                    "page_offset": _new_offset,
                                                    "has_more": _new_has_more,
                                                    "updated_at": datetime.utcnow()
                                                }}
                                            )
                                            logging.info(f"Catalog page {_page_num}: sent {len(_next_products)} products (offset={_new_offset})")
                                            return {"status": "ok", "handled_by": "catalog_next_page"}
                                    elif _reply_num == 0:
                                        # Send all images for the current page
                                        _currency_pg = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                        ws = get_whatsapp_service(db)
                                        _sent_count = 0
                                        await ws.send_message(
                                            user_id=user["_id"], to_number=from_number,
                                            message="🖼️ Sending product images...",
                                        )
                                        for _sp in _cat_products:
                                            _full_p = await db.products.find_one({"_id": _sp["id"], "user_id": _biz_id_cs})
                                            if _full_p:
                                                _price = _full_p.get('price') or 0
                                                _all_img_urls = []
                                                if _full_p.get("image_url"):
                                                    _all_img_urls.append(_full_p["image_url"])
                                                for _img in _full_p.get("images", []):
                                                    if _img and _img not in _all_img_urls:
                                                        _all_img_urls.append(_img)
                                                        
                                                if len(_all_img_urls) > 1:
                                                    for _img_u in _all_img_urls[:-1]:
                                                        await ws.send_message(
                                                            user_id=user["_id"], to_number=from_number,
                                                            message="", media_url=_img_u, send_context="catalog_visual_all"
                                                        )
                                                if _all_img_urls:
                                                    _msg_txt = f"*{_full_p['name']}*\n💰 {_currency_pg} {_price:,.0f}"
                                                    await ws.send_message(
                                                        user_id=user["_id"], to_number=from_number,
                                                        message=_msg_txt, media_url=_all_img_urls[-1], send_context="catalog_visual_all"
                                                    )
                                                    _sent_count += 1
                                        if _sent_count > 0:
                                            logging.info(f"Catalog visual blast: sent {_sent_count} product image sets.")
                                            return {"status": "ok", "handled_by": "catalog_visual_all"}
                                        else:
                                            await ws.send_message(
                                                user_id=user["_id"], to_number=from_number,
                                                message="Sorry, there are no images available for these products."
                                            )
                                            return {"status": "ok", "handled_by": "catalog_visual_all"}
                                    else:
                                        # Customer picked a product from the numbered list — show full details
                                        _selected_p = next((p for p in _cat_products if p.get("index") == _reply_num), None)
                                        if _selected_p:
                                            _full_p = await db.products.find_one({"_id": _selected_p["id"], "user_id": _biz_id_cs})
                                            if _full_p:
                                                ws = get_whatsapp_service(db)
                                                await ws.send_product_showcase(
                                                    user_id=user["_id"],
                                                    to_number=from_number,
                                                    product=_full_p,
                                                    send_buttons=True,
                                                )
                                                # Switch context to product actions so next 1/2/3 = order/cart/ask
                                                await db.pending_catalogs.update_one(
                                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                                    {"$set": {
                                                        "products": [{"id": _full_p["_id"], "name": _full_p["name"],
                                                                      "price": _full_p.get("price", 0), "index": 1}],
                                                        "action_context": "product",
                                                        "updated_at": datetime.utcnow()
                                                    }}
                                                )
                                                logging.info(f"Catalog select #{_reply_num}: showed product {_full_p['_id']}")
                                                return {"status": "ok", "handled_by": "catalog_select"}
                                    # If product not found, fall through to AI
                                    logging.warning(f"Catalog select #{_reply_num}: no product at that index")

                                elif _ctx == "cart":
                                    # 1 = checkout, 2 = continue shopping, 3 = cancel order
                                    _num_to_action = {1: "checkout", 2: "continue", 3: "cancel_cart"}
                                    _matched = _num_to_action.get(_reply_num)
                                    if _matched:
                                        button_action = _matched
                                        button_product_id = None
                                        logging.info(f"Numbered cart reply: {_reply_num} → {_matched}")

                                elif _ctx == "duplicate_order_choice":
                                    # 1 = create new (double), 2 = keep existing, 3 = cancel existing & create new
                                    _dup_order_id = _pending_cat.get("duplicate_order_id")
                                    _dup_items = _pending_cat.get("pending_cart_items", [])
                                    _dup_total = _pending_cat.get("pending_cart_total", 0)
                                    _biz_id_dup = user.get("business_id", user["_id"])
                                    _currency_dup = user.get("currency") or user.get("settings", {}).get("currency", "USD")

                                    if _reply_num == 1:
                                        # Create new order (double order)
                                        _new_order_id = str(uuid.uuid4())
                                        _new_order_num = "ORD-" + _new_order_id.replace("-", "").upper()[:6]
                                        _item_names_dup = ", ".join(i["product_name"] for i in _dup_items[:3])
                                        if len(_dup_items) > 3:
                                            _item_names_dup += f" +{len(_dup_items)-3} more"
                                        await db.orders.insert_one({
                                            "_id": _new_order_id,
                                            "order_number": _new_order_num,
                                            "user_id": _biz_id_dup,
                                            "customer_id": customer_id,
                                            "customer_name": customer_name,
                                            "customer_phone": from_number,
                                            "product": _item_names_dup,
                                            "items": _dup_items,
                                            "quantity": len(_dup_items),
                                            "total_amount": _dup_total,
                                            "total": _dup_total,
                                            "payment_status": "Unpaid",
                                            "delivery_status": "Processing",
                                            "status": "pending",
                                            "created_at": datetime.utcnow(),
                                            "source": "cart_checkout_duplicate"
                                        })
                                        # Clear cart
                                        _cart_dup = await db.carts.find_one({"customer_id": customer_id, "user_id": _biz_id_dup, "status": "active"})
                                        if _cart_dup:
                                            await db.carts.update_one({"_id": _cart_dup["_id"]}, {"$set": {"status": "completed"}})
                                        ws = get_whatsapp_service(db)
                                        _user_dup1 = await db.users.find_one({"_id": _biz_id_dup})
                                        _raw_pm_dup1 = (_user_dup1 or {}).get("payment_methods", [])
                                        _pm_dup1_lines = []
                                        for _pm in _raw_pm_dup1:
                                            if isinstance(_pm, dict):
                                                _ln = _pm.get("name", "")
                                                _hd = False
                                                if _pm.get("fields"):
                                                    _fp = [f"{f['label']}: {f['value']}" for f in _pm["fields"] if f.get("value") and str(f["value"]).strip()]
                                                    if _fp:
                                                        _ln += " — " + ", ".join(_fp)
                                                        _hd = True
                                                elif _pm.get("details") and str(_pm["details"]).strip():
                                                    _ln += f": {_pm['details']}"
                                                    _hd = True
                                                if _ln.strip() and _hd:
                                                    _pm_dup1_lines.append(f"  • {_ln}")
                                            else:
                                                if str(_pm).strip():
                                                    _pm_dup1_lines.append(f"  • {_pm}")
                                        _pay_text_dup1 = "\n".join(_pm_dup1_lines)
                                        _dup1_msg_lines = [
                                            f"✅ New order *#{_new_order_num}* created!\n",
                                            f"💰 *Total: {_currency_dup} {_dup_total:,.0f}*",
                                            f"Status: 🔴 *Unpaid*\n",
                                            "To complete your order, please make payment using the details below.\n",
                                        ]
                                        if _pay_text_dup1:
                                            _dup1_msg_lines.append(f"*💳 Payment Details:*\n{_pay_text_dup1}\n")
                                        else:
                                            _dup1_msg_lines.append("We will send you our payment details shortly.\n")
                                        _dup1_msg_lines.append(
                                            f"📸 Once you have paid, *send us a screenshot* of your payment confirmation.\n\n"
                                            f"Also send your *delivery details:*\n"
                                            f"• Full name\n• Delivery address\n• Phone number\n\n"
                                            f"Your order *#{_new_order_num}* will be processed once payment is confirmed. 🙏"
                                        )
                                        await ws.send_message(
                                            user_id=user["_id"],
                                            to_number=from_number,
                                            message="\n".join(_dup1_msg_lines),
                                            customer_name=customer_name,
                                            send_context="order_confirm"
                                        )
                                        await db.pending_catalogs.update_one(
                                            {"customer_id": customer_id, "user_id": user["_id"]},
                                            {"$set": {"action_context": "delivery_pending", "order_id": _new_order_id, "updated_at": datetime.utcnow()}}
                                        )
                                        logging.info(f"Duplicate order created: {_new_order_num}")
                                        return {"status": "ok", "handled_by": "duplicate_order_create_new"}

                                    elif _reply_num == 2:
                                        # Keep existing order, clear cart
                                        _cart_dup2 = await db.carts.find_one({"customer_id": customer_id, "user_id": _biz_id_dup, "status": "active"})
                                        if _cart_dup2:
                                            await db.carts.update_one({"_id": _cart_dup2["_id"]}, {"$set": {"status": "cancelled"}})
                                        _existing = await db.orders.find_one({"_id": _dup_order_id})
                                        _existing_num = (_existing or {}).get("order_number", "")
                                        ws = get_whatsapp_service(db)
                                        await ws.send_message(
                                            user_id=user["_id"],
                                            to_number=from_number,
                                            message=f"👍 Got it! Your existing order *#{_existing_num}* is still active.\n\nCart has been cleared. Payment details were sent earlier. 😊",
                                            customer_name=customer_name,
                                            send_context="order_confirm"
                                        )
                                        await db.pending_catalogs.update_one(
                                            {"customer_id": customer_id, "user_id": user["_id"]},
                                            {"$set": {"action_context": None, "updated_at": datetime.utcnow()}}
                                        )
                                        logging.info(f"Duplicate order: kept existing {_existing_num}")
                                        return {"status": "ok", "handled_by": "duplicate_order_keep_existing"}

                                    elif _reply_num == 3:
                                        # Cancel existing, create new
                                        await db.orders.update_one(
                                            {"_id": _dup_order_id},
                                            {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow(), "cancelled_by": "customer"}}
                                        )
                                        _new_order_id3 = str(uuid.uuid4())
                                        _new_order_num3 = "ORD-" + _new_order_id3.replace("-", "").upper()[:6]
                                        _item_names_dup3 = ", ".join(i["product_name"] for i in _dup_items[:3])
                                        if len(_dup_items) > 3:
                                            _item_names_dup3 += f" +{len(_dup_items)-3} more"
                                        await db.orders.insert_one({
                                            "_id": _new_order_id3,
                                            "order_number": _new_order_num3,
                                            "user_id": _biz_id_dup,
                                            "customer_id": customer_id,
                                            "customer_name": customer_name,
                                            "customer_phone": from_number,
                                            "product": _item_names_dup3,
                                            "items": _dup_items,
                                            "quantity": len(_dup_items),
                                            "total_amount": _dup_total,
                                            "total": _dup_total,
                                            "payment_status": "Unpaid",
                                            "delivery_status": "Processing",
                                            "status": "pending",
                                            "created_at": datetime.utcnow(),
                                            "source": "cart_checkout_replaced"
                                        })
                                        # Clear cart
                                        _cart_dup3 = await db.carts.find_one({"customer_id": customer_id, "user_id": _biz_id_dup, "status": "active"})
                                        if _cart_dup3:
                                            await db.carts.update_one({"_id": _cart_dup3["_id"]}, {"$set": {"status": "completed"}})
                                        _old_order = await db.orders.find_one({"_id": _dup_order_id})
                                        _old_num = (_old_order or {}).get("order_number", "")
                                        ws = get_whatsapp_service(db)
                                        _user_dup3 = await db.users.find_one({"_id": _biz_id_dup})
                                        _raw_pm_dup3 = (_user_dup3 or {}).get("payment_methods", [])
                                        _pm_dup3_lines = []
                                        for _pm in _raw_pm_dup3:
                                            if isinstance(_pm, dict):
                                                _ln = _pm.get("name", "")
                                                _hd = False
                                                if _pm.get("fields"):
                                                    _fp = [f"{f['label']}: {f['value']}" for f in _pm["fields"] if f.get("value") and str(f["value"]).strip()]
                                                    if _fp:
                                                        _ln += " — " + ", ".join(_fp)
                                                        _hd = True
                                                elif _pm.get("details") and str(_pm["details"]).strip():
                                                    _ln += f": {_pm['details']}"
                                                    _hd = True
                                                if _ln.strip() and _hd:
                                                    _pm_dup3_lines.append(f"  • {_ln}")
                                            else:
                                                if str(_pm).strip():
                                                    _pm_dup3_lines.append(f"  • {_pm}")
                                        _pay_text_dup3 = "\n".join(_pm_dup3_lines)
                                        _dup3_msg_lines = [
                                            f"✅ Order *#{_old_num}* cancelled.\n",
                                            f"🆕 New order *#{_new_order_num3}* created!\n",
                                            f"💰 *Total: {_currency_dup} {_dup_total:,.0f}*",
                                            f"Status: 🔴 *Unpaid*\n",
                                            "To complete your order, please make payment using the details below.\n",
                                        ]
                                        if _pay_text_dup3:
                                            _dup3_msg_lines.append(f"*💳 Payment Details:*\n{_pay_text_dup3}\n")
                                        else:
                                            _dup3_msg_lines.append("We will send you our payment details shortly.\n")
                                        _dup3_msg_lines.append(
                                            f"📸 Once you have paid, *send us a screenshot* of your payment confirmation.\n\n"
                                            f"Also send your *delivery details:*\n"
                                            f"• Full name\n• Delivery address\n• Phone number\n\n"
                                            f"Your order *#{_new_order_num3}* will be processed once payment is confirmed. 🙏"
                                        )
                                        await ws.send_message(
                                            user_id=user["_id"],
                                            to_number=from_number,
                                            message="\n".join(_dup3_msg_lines),
                                            customer_name=customer_name,
                                            send_context="order_confirm"
                                        )
                                        await db.pending_catalogs.update_one(
                                            {"customer_id": customer_id, "user_id": user["_id"]},
                                            {"$set": {"action_context": "delivery_pending", "order_id": _new_order_id3, "updated_at": datetime.utcnow()}}
                                        )
                                        logging.info(f"Duplicate order: cancelled {_old_num}, created {_new_order_num3}")
                                        return {"status": "ok", "handled_by": "duplicate_order_replace"}

                                elif _ctx == "booking_service_select":
                                    # Customer picked a service number from booking menu
                                    _bk_services = _pending_cat.get("products", [])
                                    _bk_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                    _bk_biz_type = (user.get("settings", {}).get("business_type") or "").lower().strip()
                                    _bk_is_rental_biz = _bk_biz_type == "rental"
                                    _bk_is_restaurant = _bk_biz_type == "restaurant"
                                    _bk_is_creator = _bk_biz_type == "creator"

                                    # Reply 9 = see more services (pagination)
                                    if _reply_num == 9 and _pending_cat.get("catalog_has_more"):
                                        _all_svc_ids = _pending_cat.get("catalog_all_ids", [])
                                        _cur_svc_off = _pending_cat.get("catalog_page_offset", 0)
                                        _new_svc_off = _cur_svc_off + 8
                                        _next_svc_ids = _all_svc_ids[_new_svc_off:_new_svc_off + 8]
                                        _more_svc_has_more = len(_all_svc_ids) > _new_svc_off + 8
                                        if _next_svc_ids:
                                            _biz_id_bk_pg = user.get("business_id", user["_id"])
                                            _next_svcs = []
                                            for _sid in _next_svc_ids:
                                                _sd = await db.products.find_one({"_id": _sid, "user_id": _biz_id_bk_pg})
                                                if _sd:
                                                    _next_svcs.append(_sd)
                                            if _next_svcs:
                                                if _bk_is_rental_biz:
                                                    _pg_lines = ["🏠 *More Listings*\n"]
                                                    for _pi, _ps in enumerate(_next_svcs, 1):
                                                        _pp = _ps.get("price", 0)
                                                        _pu = _ps.get("price_unit", "night")
                                                        _pu_lbl = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(_pu, "night")
                                                        _pp_str = f"{_bk_currency} {_pp:,.0f}/{_pu_lbl}" if _pp else "Contact for price"
                                                        _pg_lines.append(f"{_pi}️⃣  *{_ps['name']}* — {_pp_str}")
                                                    if _more_svc_has_more:
                                                        _pg_lines.append("9️⃣  ➡️ *See more listings*")
                                                else:
                                                    _pg_lines = ["📋 *More Services*\n"]
                                                    for _pi, _ps in enumerate(_next_svcs, 1):
                                                        _pp = _ps.get("price", 0)
                                                        _pd = _ps.get("duration")
                                                        _pp_str = f"{_bk_currency} {_pp:,.0f}" if _pp else "Contact for price"
                                                        _pd_str = f" · {_pd} min" if _pd else ""
                                                        _pg_lines.append(f"{_pi}️⃣  *{_ps['name']}* — {_pp_str}{_pd_str}")
                                                    if _more_svc_has_more:
                                                        _pg_lines.append("9️⃣  ➡️ *See more services*")
                                                _pg_lines.append("\n_Reply with the number to book_")
                                                await db.pending_catalogs.update_one(
                                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                                    {"$set": {
                                                        "products": [
                                                            {"id": str(_ps["_id"]), "name": _ps["name"],
                                                             "price": _ps.get("price", 0), "duration": _ps.get("duration"),
                                                             "index": _pi}
                                                            for _pi, _ps in enumerate(_next_svcs, 1)
                                                        ],
                                                        "catalog_page_offset": _new_svc_off,
                                                        "catalog_has_more": _more_svc_has_more,
                                                        "updated_at": datetime.utcnow()
                                                    }}
                                                )
                                                ws = get_whatsapp_service(db)
                                                await ws.send_message(
                                                    user_id=user["_id"], to_number=from_number,
                                                    message="\n".join(_pg_lines),
                                                    customer_name=customer_name, send_context="booking_flow"
                                                )
                                                return {"status": "ok", "handled_by": "booking_service_page"}

                                    _bk_sel = next((s for s in _bk_services if s.get("index") == _reply_num), None)
                                    if _bk_sel:
                                        _bk_price_str = f"{_bk_currency} {_bk_sel.get('price', 0):,.0f}" if _bk_sel.get("price") else "Contact for price"
                                        _bk_svc_id = _bk_sel["id"]
                                        _bk_svc_name = _bk_sel["name"]
                                        # Fetch full service doc for image, addons, service_category, AND fresh duration
                                        _bk_full_svc = await db.products.find_one({"_id": _bk_svc_id, "user_id": user.get("business_id", user["_id"])})
                                        _bk_duration = (_bk_full_svc or {}).get("duration")  # Get fresh duration from DB, not cache
                                        _bk_image_url = (_bk_full_svc or {}).get("image_url") or ""
                                        # Build ordered image list: primary image always first, then extras
                                        _bk_all_images = []
                                        if _bk_image_url:
                                            _bk_all_images.append(_bk_image_url)
                                        for _extra_img in ((_bk_full_svc or {}).get("images") or []):
                                            if _extra_img and _extra_img != _bk_image_url:
                                                _bk_all_images.append(_extra_img)
                                        _bk_addons = (_bk_full_svc or {}).get("addons", []) or []
                                        # If whole business is rental, treat all listings as rental regardless of stored service_category
                                        _bk_svc_cat = "rental" if _bk_is_rental_biz else (_bk_full_svc or {}).get("service_category", "appointment")
                                        _bk_description = (_bk_full_svc or {}).get("description", "")
                                        ws = get_whatsapp_service(db)
                                        # Send listing images (up to 5) — captioned image always first
                                        if _bk_all_images:
                                            try:
                                                import httpx as _httpx_bk
                                                _inst_doc = await db.users.find_one({"_id": user["_id"]}, {"whatsapp": 1})
                                                _inst_name = (_inst_doc or {}).get("whatsapp", {}).get("instance_name", "")
                                                if _inst_name:
                                                    async with _httpx_bk.AsyncClient(timeout=15) as _hc:
                                                        for _img_idx, _img_u in enumerate(_bk_all_images[:5]):
                                                            _caption = ""
                                                            if _img_idx == 0:
                                                                _caption = f"*{_bk_svc_name}* — {_bk_price_str}"
                                                                if _bk_description:
                                                                    _caption += f"\n_{_bk_description[:120]}_"
                                                            await _hc.post(
                                                                f"{ws.base_url}/message/sendMedia/{_inst_name}",
                                                                json={"number": from_number.lstrip("+"), "mediatype": "image",
                                                                      "media": _img_u, "caption": _caption},
                                                                headers=ws._headers(),
                                                            )
                                            except Exception as _img_err:
                                                logging.warning(f"[Booking] Listing image send failed: {_img_err}")

                                        _bk_price_unit = (_bk_full_svc or {}).get("price_unit", "night")
                                        _bk_unit_label = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}.get(_bk_price_unit, "night")
                                        # Store core booking fields in pending_catalogs
                                        _base_ctx = {
                                            "booking_service_id": _bk_svc_id,
                                            "booking_service_name": _bk_svc_name,
                                            "booking_service_price": _bk_sel.get("price", 0),
                                            "booking_service_duration": _bk_duration,
                                            "booking_service_category": _bk_svc_cat,
                                            "booking_price_unit": _bk_price_unit,
                                            "booking_addons_available": _bk_addons,
                                            "booking_selected_addons": [],
                                            "updated_at": datetime.utcnow(),
                                        }

                                        if _bk_addons:
                                            # Step: show add-ons menu before date
                                            _addon_lines = [f"✅ *{_bk_svc_name}* selected ({_bk_price_str})\n"]
                                            _addon_lines.append("🔧 *Optional Add-ons:*\n")
                                            for _ai, _ad in enumerate(_bk_addons[:4], 1):
                                                _ad_price = _ad.get("price", 0)
                                                _ad_str = f"+{_bk_currency} {_ad_price:,.0f}" if _ad_price else "Free"
                                                _addon_lines.append(f"{_ai}️⃣  {_ad.get('name', '')} — {_ad_str}")
                                            _addon_lines.append(f"0️⃣  No extras")
                                            _addon_lines.append("\n_Reply with numbers separated by spaces (e.g. *1 3*) or *0* to skip_")
                                            _base_ctx["action_context"] = "booking_addon_select"
                                            await db.pending_catalogs.update_one(
                                                {"customer_id": customer_id, "user_id": user["_id"]},
                                                {"$set": _base_ctx}
                                            )
                                            await ws.send_message(
                                                user_id=user["_id"], to_number=from_number,
                                                message="\n".join(_addon_lines),
                                                customer_name=customer_name, send_context="booking_flow"
                                            )
                                        elif _bk_svc_cat == "rental":
                                            _base_ctx["action_context"] = "booking_checkin_input"
                                            await db.pending_catalogs.update_one(
                                                {"customer_id": customer_id, "user_id": user["_id"]},
                                                {"$set": _base_ctx}
                                            )
                                            await ws.send_message(
                                                user_id=user["_id"], to_number=from_number,
                                                message=(
                                                    f"Great choice! *{_bk_svc_name}* ({_bk_price_str}/{_bk_unit_label}).\n\n"
                                                    f"📅 *Check-in date?*\n"
                                                    f"_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*_"
                                                ),
                                                customer_name=customer_name, send_context="booking_flow"
                                            )
                                        elif _bk_is_restaurant:
                                            _base_ctx["action_context"] = "booking_date_input"
                                            await db.pending_catalogs.update_one(
                                                {"customer_id": customer_id, "user_id": user["_id"]},
                                                {"$set": _base_ctx}
                                            )
                                            await ws.send_message(
                                                user_id=user["_id"], to_number=from_number,
                                                message=(
                                                    f"Great choice! *{_bk_svc_name}* ({_bk_price_str}).\n\n"
                                                    f"🍽️ *Table Reservation*\n"
                                                    f"📅 *What date would you like?*\n"
                                                    f"_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*_"
                                                ),
                                                customer_name=customer_name, send_context="booking_flow"
                                            )
                                        elif _bk_is_creator:
                                            _base_ctx["action_context"] = "creator_timeline_input"
                                            await db.pending_catalogs.update_one(
                                                {"customer_id": customer_id, "user_id": user["_id"]},
                                                {"$set": _base_ctx}
                                            )
                                            await ws.send_message(
                                                user_id=user["_id"], to_number=from_number,
                                                message=(
                                                    f"Great choice! *{_bk_svc_name}* ({_bk_price_str}).\n\n"
                                                    f"📅 *When do you need this delivered?*\n"
                                                    f"_Reply with a deadline, e.g. *in 3 days*, *next Friday*, *March 20*_"
                                                ),
                                                customer_name=customer_name, send_context="booking_flow"
                                            )
                                        else:
                                            _base_ctx["action_context"] = "booking_date_input"
                                            await db.pending_catalogs.update_one(
                                                {"customer_id": customer_id, "user_id": user["_id"]},
                                                {"$set": _base_ctx}
                                            )
                                            await ws.send_message(
                                                user_id=user["_id"], to_number=from_number,
                                                message=(
                                                    f"Great choice! *{_bk_svc_name}* ({_bk_price_str}).\n\n"
                                                    f"📅 *What date would you like?*\n"
                                                    f"_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*, or *2026-03-15*_"
                                                ),
                                                customer_name=customer_name, send_context="booking_flow"
                                            )
                                        logging.info(f"[Booking] Service selected: {_bk_svc_name} (cat={_bk_svc_cat}, addons={len(_bk_addons)}) for customer {customer_id}")
                                        return {"status": "ok", "handled_by": "booking_service_select"}

                                elif _ctx == "booking_time_select":
                                    # Customer picked a time slot number
                                    _bk_slots = _pending_cat.get("time_slots", [])
                                    _bk_slot = next((s for s in _bk_slots if s.get("index") == _reply_num), None)
                                    if _bk_slot:
                                        _bk_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                        _bk_price = _pending_cat.get("booking_service_price", 0)
                                        _bk_price_str = f"{_bk_currency} {_bk_price:,.0f}" if _bk_price else ""
                                        _bk_biz_type_ts = (user.get("settings", {}).get("business_type") or "").lower().strip()
                                        
                                        # Restaurant: ask for party size
                                        if _bk_biz_type_ts == "restaurant":
                                            await db.pending_catalogs.update_one(
                                                {"customer_id": customer_id, "user_id": user["_id"]},
                                                {"$set": {
                                                    "action_context": "restaurant_party_size_input",
                                                    "booking_time": _bk_slot["time"],
                                                    "updated_at": datetime.utcnow()
                                                }}
                                            )
                                            ws = get_whatsapp_service(db)
                                            await ws.send_message(
                                                user_id=user["_id"], to_number=from_number,
                                                message=(
                                                    f"✅ Time: *{_bk_slot['time']}*\n\n"
                                                    f"👥 *How many people?*\n"
                                                    f"_Reply with the party size (1-50)_"
                                                ),
                                                customer_name=customer_name, send_context="booking_flow"
                                            )
                                            return {"status": "ok", "handled_by": "booking_time_select_restaurant"}
                                        
                                        # Other services: show summary
                                        _bk_summary = (
                                            f"✅ *Booking Summary*\n\n"
                                            f"📋 Service: *{_pending_cat.get('booking_service_name', '')}*\n"
                                            f"📅 Date: *{_pending_cat.get('booking_date', '')}*\n"
                                            f"🕐 Time: *{_bk_slot['time']}*\n"
                                            + (f"💰 Price: *{_bk_price_str}*\n" if _bk_price_str else "")
                                            + f"\nReply *YES* to confirm or *NO* to cancel"
                                        )
                                        await db.pending_catalogs.update_one(
                                            {"customer_id": customer_id, "user_id": user["_id"]},
                                            {"$set": {
                                                "action_context": "booking_confirm",
                                                "booking_time": _bk_slot["time"],
                                                "updated_at": datetime.utcnow()
                                            }}
                                        )
                                        ws = get_whatsapp_service(db)
                                        await ws.send_message(
                                            user_id=user["_id"], to_number=from_number,
                                            message=_bk_summary, customer_name=customer_name, send_context="booking_flow"
                                        )
                                        logging.info(f"[Booking] Time selected: {_bk_slot['time']} for customer {customer_id}")
                                        return {"status": "ok", "handled_by": "booking_time_select"}

                                else:
                                    # product context — look up user's custom action buttons
                                    _default_actions = [
                                        {"label": "Order Now",             "action_type": "order",       "index": 1},
                                        {"label": "Add to Cart",           "action_type": "add_to_cart", "index": 2},
                                        {"label": "See Similar Products",  "action_type": "similar",     "index": 3},
                                    ]
                                    _user_actions_doc = await db.users.find_one(
                                        {"_id": user["_id"]}, {"settings.product_actions": 1}
                                    )
                                    _user_actions = (
                                        (_user_actions_doc or {}).get("settings", {}).get("product_actions")
                                        or _default_actions
                                    )
                                    # Add "Back to Catalog" as last option (matches whatsapp_service.py)
                                    _back_index = len(_user_actions) + 1
                                    _user_actions_with_back = _user_actions + [{"label": "🔙 Back to Catalog", "action_type": "back", "index": _back_index}]

                                    _chosen = next(
                                        (a for a in _user_actions_with_back if a.get("index") == _reply_num), None
                                    )
                                    if _chosen and _pending_cat.get("products"):
                                        button_action = _chosen["action_type"]
                                        button_product_id = _pending_cat["products"][0].get("id")
                                        # Store the full action for prompt lookup in the handler
                                        _chosen_action_meta = _chosen
                                        logging.info(f"Numbered product reply: {_reply_num} → {button_action}, product={button_product_id}")

                # TEXT OPTION HANDLER — match full option text (legacy poll / typed responses)
                if not button_action and not from_me and body:
                    _body_lower = body.strip().lower()
                    _poll_option_map = {
                        "🛒 order now": "order",
                        "order now": "order",
                        "✅ order now": "order",
                        "➕ add to cart": "add_to_cart",
                        "🛒 add to cart": "add_to_cart",
                        "add to cart": "add_to_cart",
                        "💬 ask a question": "similar",
                        "💬 ask question": "similar",
                        "ask a question": "similar",
                        "ask question": "similar",
                        "see similar": "similar",
                        "similar products": "similar",
                        "📋 more info": "details",
                        "more info": "details",
                        "🛍️ continue shopping": "continue",
                        "continue shopping": "continue",
                        "✅ checkout now": "checkout",
                        "checkout now": "checkout",
                        "📱 share": "share",
                    }
                    _poll_matched = _poll_option_map.get(_body_lower)
                    if _poll_matched:
                        _pending_cat = await db.pending_catalogs.find_one({
                            "customer_id": customer_id, "user_id": user["_id"]
                        })
                        if _pending_cat and _pending_cat.get("products"):
                            button_action = _poll_matched
                            button_product_id = _pending_cat["products"][0].get("id")
                            logging.info(f"Text option matched: action={_poll_matched}, product={button_product_id}")
                
                # ORDER CONFIRMATION — FlowJudge for ambiguous messages (not clear YES/NO)
                if not button_action and not from_me and body:
                    _oc_pre_body = body.strip().lower()
                    _oc_pre_yes = {"yes","yeah","yep","sure","ok","okay","confirm","ndio","sawa","yes please","yep!","yes!",
                                   "sounds good","order it","go ahead","let's do it","great","perfect","proceed"}
                    _oc_pre_no  = {"no","nope","cancel","hapana","nah","no thanks","no thank you","cancel order",
                                   "never mind","forget it","don't","dont","stop","acha"}
                    if _oc_pre_body not in _oc_pre_yes and _oc_pre_body not in _oc_pre_no:
                        _oc_fj_state = await db.pending_catalogs.find_one({
                            "customer_id": customer_id, "user_id": user["_id"],
                            "action_context": "order_confirm"
                        })
                        if _oc_fj_state:
                            try:
                                from agents.flow_judge import get_flow_judge as _get_fj_oc
                                _fj_oc = _get_fj_oc()
                                _fj_oc_cur = user.get("currency") or user.get("settings", {}).get("currency", "")
                                # Build a quick order summary for context
                                _oc_product_id = _oc_fj_state.get("confirm_product_id")
                                _oc_product = await db.products.find_one({"_id": _oc_product_id}) if _oc_product_id else None
                                _oc_ctx = {
                                    "booking_service_name": _oc_product["name"] if _oc_product else _oc_fj_state.get("product_name", ""),
                                    "booking_service_price": _oc_product.get("price", 0) if _oc_product else _oc_fj_state.get("price", 0),
                                }
                                _fj_oc_result = await _fj_oc.understand(
                                    message=body,
                                    current_step="waiting for order confirmation",
                                    waiting_for="YES to confirm order or NO to cancel",
                                    pending_state=_oc_ctx,
                                    language="English",
                                    currency=_fj_oc_cur,
                                )
                                _fj_oc_action = _fj_oc_result.get("action", "unclear")
                                _oc_ws = get_whatsapp_service(db)
                                _oc_prod_name = _oc_ctx.get("booking_service_name", "this item")
                                _oc_price = _oc_ctx.get("booking_service_price", 0)
                                _oc_price_str = f"{_fj_oc_cur} {_oc_price:,.0f}" if _oc_price else ""
                                if _fj_oc_action == "continue":
                                    _ext_oc = (_fj_oc_result.get("extracted_value") or "").lower()
                                    _oc_pre_body = "yes" if _ext_oc in ("yes","confirm","y","sure","ok","ndio","sawa","agree","order","proceed") else "no"
                                    body = _oc_pre_body
                                elif _fj_oc_action == "go_back":
                                    await db.pending_catalogs.update_one(
                                        {"customer_id": customer_id, "user_id": user["_id"]},
                                        {"$set": {"action_context": None, "updated_at": datetime.utcnow()}}
                                    )
                                    await _oc_ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message="No problem! What else can I help you with? 😊",
                                        customer_name=customer_name, send_context="order_flow"
                                    )
                                    return {"status": "ok", "handled_by": "order_confirm_go_back"}
                                elif _fj_oc_action == "cancel":
                                    await db.pending_catalogs.update_one(
                                        {"customer_id": customer_id, "user_id": user["_id"]},
                                        {"$set": {"action_context": None, "updated_at": datetime.utcnow()}}
                                    )
                                    await _oc_ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message=_fj_oc_result.get("reply") or "No worries! Let me know if you'd like to order anything else 😊",
                                        customer_name=customer_name, send_context="order_flow"
                                    )
                                    return {"status": "ok", "handled_by": "order_confirm_cancelled"}
                                elif _fj_oc_action == "tangent":
                                    _oc_summary_hint = f" for *{_oc_prod_name}*" + (f" ({_oc_price_str})" if _oc_price_str else "")
                                    _oc_tangent_msg = _fj_oc_result.get("reply") or (
                                        f"Hey! 😊 We were just confirming your order{_oc_summary_hint}. Reply *YES* to confirm or *NO* to cancel."
                                    )
                                    await _oc_ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message=_oc_tangent_msg, customer_name=customer_name, send_context="order_flow"
                                    )
                                    return {"status": "ok", "handled_by": "order_confirm_tangent"}
                                else:  # unclear
                                    _oc_re_summary = (
                                        f"Just to confirm your order:\n"
                                        f"🛍️ *{_oc_prod_name}*"
                                        + (f" — {_oc_price_str}" if _oc_price_str else "")
                                        + f"\n\nReply *YES* to confirm or *NO* to cancel 😊"
                                    )
                                    await _oc_ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message=_oc_re_summary, customer_name=customer_name, send_context="order_flow"
                                    )
                                    return {"status": "ok", "handled_by": "order_confirm_unclear"}
                            except Exception as _fj_oc_err:
                                logging.warning(f"[FlowJudge/order_confirm] {_fj_oc_err}")

                # ORDER CONFIRMATION HANDLER — customer replied YES or NO to an order confirmation request
                if not button_action and not from_me and body:
                    _body_confirm = body.strip().lower()
                    _yes_words = {"yes", "yeah", "yep", "sure", "ok", "okay", "confirm", "ndio", "sawa", "yes please", "yep!", "yes!",
                                  "sounds good", "order it", "go ahead", "let's do it", "great", "perfect", "proceed"}
                    _no_words = {"no", "nope", "cancel", "hapana", "nah", "no thanks", "no thank you", "cancel order",
                                 "never mind", "forget it", "don't", "dont", "stop", "acha"}
                    if _body_confirm in _yes_words or _body_confirm in _no_words:
                        _pending_confirm = await db.pending_catalogs.find_one({
                            "customer_id": customer_id, "user_id": user["_id"],
                            "action_context": "order_confirm"
                        })
                        if _pending_confirm:
                            _biz_id_conf = user.get("business_id", user["_id"])
                            _conf_product_id = _pending_confirm.get("confirm_product_id")
                            if _body_confirm in _yes_words:
                                # Customer confirmed — create order and send payment details
                                _conf_product = await db.products.find_one({"_id": _conf_product_id, "user_id": _biz_id_conf}) if _conf_product_id else None
                                if _conf_product:
                                    _currency_conf = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                    _price_conf = _conf_product.get("price", 0)
                                    _now_conf = datetime.utcnow()
                                    _order_id_conf = str(uuid.uuid4())
                                    _order_number = "ORD-" + _order_id_conf.replace("-", "").upper()[:6]
                                    # Create ORDER with Unpaid status — sale only created when payment confirmed by owner
                                    await db.orders.insert_one({
                                        "_id": _order_id_conf,
                                        "order_number": _order_number,
                                        "user_id": _biz_id_conf,
                                        "customer_id": customer_id,
                                        "customer_name": customer_name,
                                        "customer_phone": from_number,
                                        "product": _conf_product["name"],
                                        "product_id": _conf_product["_id"],
                                        "items": [{"product_id": _conf_product["_id"], "product_name": _conf_product["name"], "quantity": 1, "price": _price_conf}],
                                        "quantity": 1,
                                        "price": _price_conf,
                                        "total_amount": _price_conf,
                                        "total": _price_conf,
                                        "payment_status": "Unpaid",
                                        "delivery_status": "Processing",
                                        "status": "pending",
                                        "created_at": _now_conf,
                                        "source": "whatsapp_confirmed"
                                    })
                                    # Create sales record so order appears in CRM sales tab
                                    await db.sales.insert_one({
                                        "_id": str(uuid.uuid4()),
                                        "user_id": _biz_id_conf,
                                        "customer_id": customer_id,
                                        "customer_name": customer_name,
                                        "product": _conf_product["name"],
                                        "product_id": _conf_product["_id"],
                                        "amount": _price_conf,
                                        "quantity": 1,
                                        "status": "pending_payment",
                                        "payment_status": "unpaid",
                                        "order_id": _order_id_conf,
                                        "order_number": _order_number,
                                        "source": "whatsapp_order",
                                        "created_at": _now_conf,
                                    })
                                    await db.customers.update_one(
                                        {"_id": customer_id},
                                        {
                                            "$inc": {"purchase_count": 1, "total_spent": _price_conf},
                                            "$set": {"last_contacted": _now_conf}
                                        }
                                    )
                                    # Extract payment details from user.payment_methods (top-level)
                                    _user_conf_doc = await db.users.find_one({"_id": _biz_id_conf})
                                    _raw_pm_conf = (_user_conf_doc or {}).get("payment_methods", [])
                                    _pm_conf_lines = []
                                    for _pm in _raw_pm_conf:
                                        if isinstance(_pm, dict):
                                            _line = _pm.get("name", "")
                                            _has_details = False
                                            if _pm.get("fields"):
                                                _fp = [f"{f['label']}: {f['value']}" for f in _pm["fields"] if f.get("value") and str(f["value"]).strip()]
                                                if _fp:
                                                    _line += " — " + ", ".join(_fp)
                                                    _has_details = True
                                            elif _pm.get("details") and str(_pm["details"]).strip():
                                                _line += f": {_pm['details']}"
                                                _has_details = True
                                            if _line.strip() and _has_details:
                                                _pm_conf_lines.append(f"  • {_line}")
                                        else:
                                            if str(_pm).strip():
                                                _pm_conf_lines.append(f"  • {_pm}")
                                    _payment_text = "\n".join(_pm_conf_lines)
                                    # Build order confirmation + payment request message
                                    _conf_msg = (
                                        f"✅ *Order Received!*\n\n"
                                        f"🔖 Order No: *#{_order_number}*\n"
                                        f"📦 *{_conf_product['name']}*\n"
                                        f"💰 {_currency_conf} {_price_conf:,.0f}\n"
                                        f"Status: 🔴 *Unpaid*\n\n"
                                        f"To complete your order, please make payment using the details below.\n\n"
                                    )
                                    if _payment_text:
                                        _conf_msg += f"*💳 Payment Details:*\n{_payment_text}\n\n"
                                    else:
                                        _conf_msg += "We will send you our payment details shortly.\n\n"
                                    _conf_msg += (
                                        f"📸 Once you have paid, *send us a screenshot* of your payment confirmation.\n\n"
                                        f"Also send your *delivery details:*\n"
                                        f"• Full name\n"
                                        f"• Delivery address\n"
                                        f"• Phone number\n\n"
                                        f"Your order *#{_order_number}* will be processed once payment is confirmed. 🙏"
                                    )
                                    ws = get_whatsapp_service(db)
                                    await ws.send_message(
                                        user_id=_biz_id_conf, to_number=from_number,
                                        message=_conf_msg, customer_name=customer_name, send_context="order_confirm"
                                    )
                                    # Update context to awaiting delivery details
                                    await db.pending_catalogs.update_one(
                                        {"customer_id": customer_id, "user_id": user["_id"]},
                                        {"$set": {"action_context": "delivery_pending", "order_id": _order_id_conf, "updated_at": _now_conf}}
                                    )
                                    # Notify business owner
                                    _owner_conf = await db.users.find_one({"_id": _biz_id_conf}, {"expo_push_token": 1})
                                    _push_conf = (_owner_conf or {}).get("expo_push_token", "")
                                    if _push_conf:
                                        try:
                                            from notification_service import get_notification_service
                                            _ns_conf = get_notification_service()
                                            await _ns_conf.send_notification(
                                                push_token=_push_conf,
                                                title="🛒 New Order Received!",
                                                body=f"{customer_name} ordered {_conf_product['name']} — {_currency_conf} {_price_conf:,.0f}",
                                                data={"type": "new_order", "order_id": _order_id_conf, "customer_id": customer_id}
                                            )
                                        except Exception as _ne_conf:
                                            logging.warning(f"Order confirm push failed: {_ne_conf}")
                                    logging.info(f"[Order] Confirmed via YES reply: {_order_id_conf}")
                                    return {"status": "ok", "handled_by": "order_confirm_yes"}
                            else:
                                # Customer cancelled
                                ws = get_whatsapp_service(db)
                                await ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message="No problem! If you'd like to browse our products again, just say *catalog* or let me know how I can help. 😊",
                                    customer_name=customer_name, send_context="order_cancel"
                                )
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "product", "updated_at": datetime.utcnow()}}
                                )
                                logging.info(f"[Order] Cancelled via NO reply for customer={customer_id}")
                                return {"status": "ok", "handled_by": "order_confirm_no"}

                # BOOKING ADDON SELECT HANDLER — customer picks add-ons (or 0 to skip)
                if not button_action and not from_me and body:
                    _addon_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "booking_addon_select"
                    })
                    if _addon_state:
                        import re as _re_addon
                        _addon_available = _addon_state.get("booking_addons_available", [])
                        _addon_body = body.strip().lower()
                        _selected_addons = []
                        if _addon_body != "0" and _addon_body not in ("no", "skip", "none"):
                            _nums = [int(x) for x in _re_addon.findall(r'\d+', body) if int(x) > 0 and int(x) <= len(_addon_available)]
                            for _n in _nums:
                                _selected_addons.append(_addon_available[_n - 1])
                        _bk_svc_cat = _addon_state.get("booking_service_category", "appointment")
                        _bk_currency_ad = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                        _bk_svc_name_ad = _addon_state.get("booking_service_name", "Service")
                        _bk_price_ad = _addon_state.get("booking_service_price", 0)
                        _addon_total = _bk_price_ad + sum(a.get("price", 0) for a in _selected_addons)
                        _addon_total_str = f"{_bk_currency_ad} {_addon_total:,.0f}" if _addon_total else ""
                        ws = get_whatsapp_service(db)
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "booking_selected_addons": _selected_addons,
                                "action_context": "booking_checkin_input" if _bk_svc_cat == "rental" else "booking_date_input",
                                "updated_at": datetime.utcnow(),
                            }}
                        )
                        if _bk_svc_cat == "rental":
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message=(
                                    (f"Got it — added: {', '.join(a['name'] for a in _selected_addons)}\n\n" if _selected_addons else "No extras added.\n\n")
                                    + f"📅 *Check-in date?*\n_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*_"
                                ),
                                customer_name=customer_name, send_context="booking_flow"
                            )
                        else:
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message=(
                                    (f"Got it — added: {', '.join(a['name'] for a in _selected_addons)}\n\n" if _selected_addons else "No extras added.\n\n")
                                    + (f"💰 Total: *{_addon_total_str}*\n\n" if _addon_total_str else "")
                                    + f"📅 *What date would you like?*\n_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*_"
                                ),
                                customer_name=customer_name, send_context="booking_flow"
                            )
                        logging.info(f"[Booking] Addons selected: {_selected_addons} for customer {customer_id}")
                        return {"status": "ok", "handled_by": "booking_addon_select"}

                # BOOKING CHECK-IN DATE HANDLER — for rental services
                if not button_action and not from_me and body:
                    _ci_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "booking_checkin_input"
                    })
                    if _ci_state:
                        # ── FlowJudge: AI reads message before rigid date parser ──
                        _ci_fj_skip = False
                        try:
                            from agents.flow_judge import get_flow_judge as _get_fj_ci
                            _fj_ci = _get_fj_ci()
                            _fj_ci_cur = user.get("currency") or user.get("settings", {}).get("currency", "")
                            _fj_ci_result = await _fj_ci.understand(
                                message=body,
                                current_step="waiting for rental check-in date",
                                waiting_for="a check-in date (today, tomorrow, Monday, 15 March, 2026-03-15)",
                                pending_state=_ci_state,
                                language="English",
                                currency=_fj_ci_cur,
                            )
                            _fj_ci_action = _fj_ci_result.get("action", "continue")
                            _fj_ci_ws = get_whatsapp_service(db)
                            _ci_svc = _ci_state.get("booking_service_name", "your rental")
                            if _fj_ci_action == "go_back":
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "booking_service_select", "updated_at": datetime.utcnow()}}
                                )
                                await _fj_ci_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message="No problem! Which listing would you like? Reply with the number 😊",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "checkin_go_back"}
                            elif _fj_ci_action == "cancel":
                                await db.pending_catalogs.delete_one({"_id": _ci_state["_id"]})
                                await _fj_ci_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_ci_result.get("reply") or "No worries! Feel free to come back anytime 😊",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "checkin_cancelled"}
                            elif _fj_ci_action == "tangent":
                                await _fj_ci_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_ci_result.get("reply") or f"Hey! 😊 We were picking your check-in date for *{_ci_svc}* — what date works for you? 📅",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "checkin_tangent"}
                            elif _fj_ci_action == "unclear":
                                await _fj_ci_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_ci_result.get("reply") or "What date would you like to check in? 📅\n_e.g. tomorrow, Monday, 15 March_",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "checkin_unclear"}
                            if _fj_ci_result.get("extracted_value"):
                                body = _fj_ci_result["extracted_value"]
                        except Exception as _fj_ci_err:
                            logging.warning(f"[FlowJudge/checkin] {_fj_ci_err}")

                        import re as _re_ci
                        _ci_body = body.strip()
                        _ci_lower = _ci_body.lower()
                        _ci_is_cancel = False
                        _ci_is_avail = any(_ci_lower.startswith(kw) for kw in ("availability", "check availability", "available dates", "show dates", "what dates", "when is it available"))

                        if _ci_is_cancel:
                            await db.pending_catalogs.delete_one({"_id": _ci_state["_id"]})
                            # Fall through — let agent pipeline handle
                        elif _ci_is_avail:
                            # Show the listing's availability calendar and KEEP booking state
                            import calendar as _cal_ci
                            _avail_ws = get_whatsapp_service(db)
                            _avail_today = datetime.utcnow().date()
                            _avail_yr, _avail_mo = _avail_today.year, _avail_today.month
                            _avail_days_in_month = _cal_ci.monthrange(_avail_yr, _avail_mo)[1]
                            _avail_month_label = _avail_today.strftime("%B %Y")
                            _avail_svc_id = _ci_state.get("booking_service_id", "")
                            _avail_svc_name = _ci_state.get("booking_service_name", "this listing")
                            _avail_user_doc = await db.users.find_one({"_id": user["_id"]})
                            _avail_global_blocked = set((_avail_user_doc or {}).get("settings", {}).get("rental_availability") or [])
                            _avail_listing_doc = await db.products.find_one({"_id": _avail_svc_id}) if _avail_svc_id else None
                            _avail_listing_blocked = set((_avail_listing_doc or {}).get("listing_blocked_dates") or [])
                            _avail_all_blocked = _avail_global_blocked | _avail_listing_blocked
                            _avail_blocked_days = [d for d in range(1, _avail_days_in_month + 1)
                                                   if f"{_avail_yr:04d}-{_avail_mo:02d}-{d:02d}" in _avail_all_blocked]
                            _avail_free_days = [d for d in range(1, _avail_days_in_month + 1)
                                                if d not in _avail_blocked_days and _avail_today.replace(day=d) >= _avail_today]

                            def _compress_ranges(days):
                                if not days: return ""
                                ranges, s, e = [], days[0], days[0]
                                for d in days[1:]:
                                    if d == e + 1: e = d
                                    else:
                                        ranges.append(str(s) if s == e else f"{s}–{e}")
                                        s = e = d
                                ranges.append(str(s) if s == e else f"{s}–{e}")
                                return ", ".join(ranges)

                            _avail_lines = [f"📅 *{_avail_svc_name} — {_avail_month_label}*\n"]
                            if not _avail_blocked_days:
                                _avail_lines.append("✅ Fully available this month!")
                            else:
                                if _avail_free_days:
                                    _avail_lines.append(f"✅ *Available:* {_compress_ranges(_avail_free_days)}")
                                _avail_lines.append(f"❌ *Blocked:* {_compress_ranges(_avail_blocked_days)}")
                            _avail_lines.append(f"\n_Reply with your preferred check-in date to continue booking_ 📅")
                            await _avail_ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message="\n".join(_avail_lines),
                                customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "booking_checkin_avail_view"}
                        else:
                            _today_ci = datetime.utcnow().date()
                            _parsed_ci = None
                            _parsed_co_inline = None  # checkout parsed from same message (range)

                            _mm_ci = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                                      "january":1,"february":2,"march":3,"april":4,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}

                            def _parse_single_date_ci(txt, ref_today):
                                """Parse a single date token into a date object, or return None."""
                                txt = txt.strip().lower().rstrip("stndrh")  # strip ordinal suffixes (1st→1)
                                if txt == "today": return ref_today
                                if txt == "tomorrow": return ref_today + timedelta(days=1)
                                if txt in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday"):
                                    _wd = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}[txt]
                                    return ref_today + timedelta(days=(_wd - ref_today.weekday()) % 7 or 7)
                                # plain day number like "27"
                                if _re_ci.fullmatch(r"\d{1,2}", txt):
                                    d = int(txt)
                                    mo, yr = ref_today.month, ref_today.year
                                    try:
                                        candidate = datetime(yr, mo, d).date()
                                        if candidate < ref_today:
                                            mo += 1
                                            if mo > 12: mo, yr = 1, yr + 1
                                        return datetime(yr, mo, d).date()
                                    except Exception: return None
                                # YYYY-MM-DD
                                _m = _re_ci.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", txt)
                                if _m:
                                    try: return datetime(int(_m.group(1)), int(_m.group(2)), int(_m.group(3))).date()
                                    except Exception: return None
                                # DD/MM/YYYY or DD-MM-YYYY
                                _m4 = _re_ci.fullmatch(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", txt)
                                if _m4:
                                    try: return datetime(int(_m4.group(3)), int(_m4.group(2)), int(_m4.group(1))).date()
                                    except Exception: return None
                                # "15 march" or "march 15"
                                _m2 = _re_ci.fullmatch(r"(\d{1,2})\s+([a-z]+)", txt)
                                _m3 = _re_ci.fullmatch(r"([a-z]+)\s+(\d{1,2})", txt)
                                if _m2 and _m2.group(2) in _mm_ci:
                                    d, mo = int(_m2.group(1)), _mm_ci[_m2.group(2)]
                                    yr = ref_today.year if (mo, d) >= (ref_today.month, ref_today.day) else ref_today.year + 1
                                    try: return datetime(yr, mo, d).date()
                                    except Exception: return None
                                if _m3 and _m3.group(1) in _mm_ci:
                                    d, mo = int(_m3.group(2)), _mm_ci[_m3.group(1)]
                                    yr = ref_today.year if (mo, d) >= (ref_today.month, ref_today.day) else ref_today.year + 1
                                    try: return datetime(yr, mo, d).date()
                                    except Exception: return None
                                return None

                            try:
                                # ── Range detection: "27-31", "27 to 31", "27 – 31",
                                #    "march 27-31", "27 march to 31 march", "27th to 31st" ──
                                _range_m = _re_ci.search(
                                    r"(\d{1,2}(?:st|nd|rd|th)?\s*(?:[a-z]*)?)\s*(?:to|-|–|till|until|thru|through)\s*(\d{1,2}(?:st|nd|rd|th)?\s*(?:[a-z]*)?)",
                                    _ci_lower
                                )
                                if _range_m:
                                    _tok_a = _range_m.group(1).strip()
                                    _tok_b = _range_m.group(2).strip()
                                    _d_a = _parse_single_date_ci(_tok_a, _today_ci)
                                    _d_b = _parse_single_date_ci(_tok_b, _today_ci)
                                    # If only day numbers, they share the same month
                                    if _d_a and _d_b and _d_b <= _d_a:
                                        # e.g. "27-31" both in same month: recalculate _d_b with _d_a's month
                                        try: _d_b = _d_a.replace(day=int(_re_ci.sub(r"[^0-9]", "", _tok_b)))
                                        except Exception: pass
                                    if _d_a and _d_b and _d_b > _d_a:
                                        _parsed_ci = _d_a
                                        _parsed_co_inline = _d_b
                                if not _parsed_ci:
                                    _parsed_ci = _parse_single_date_ci(_ci_lower, _today_ci)
                            except Exception: _parsed_ci = None

                            ws = get_whatsapp_service(db)
                            if not _parsed_ci or _parsed_ci < _today_ci:
                                await ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message="I didn't catch that. Please reply with a check-in date like *tomorrow*, *Monday*, or *15 March* 📅",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_checkin_invalid"}
                            _ci_user_doc = await db.users.find_one({"_id": user["_id"]})
                            _ci_blocked_global = (_ci_user_doc or {}).get("settings", {}).get("rental_availability") or []
                            _ci_svc_id = _ci_state.get("booking_service_id", "")
                            _ci_listing_doc = await db.products.find_one({"_id": _ci_svc_id}) if _ci_svc_id else None
                            _ci_blocked_listing = (_ci_listing_doc or {}).get("listing_blocked_dates") or []
                            _ci_all_blocked = set(_ci_blocked_global) | set(_ci_blocked_listing)
                            if str(_parsed_ci) in _ci_all_blocked:
                                await ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=(
                                        f"Sorry, *{_parsed_ci.strftime('%A %d %B %Y')}* is not available for check-in. \n\n"
                                        f"📅 Please reply with a different check-in date."
                                    ),
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_checkin_blocked"}

                            if _parsed_co_inline and _parsed_co_inline > _parsed_ci:
                                # Range given in one message (e.g. "27-31") — check checkout date too
                                _co_also_blocked = any(
                                    f"{_parsed_ci + timedelta(days=i)}" in _ci_all_blocked
                                    for i in range((_parsed_co_inline - _parsed_ci).days)
                                )
                                if _co_also_blocked:
                                    await ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message=(
                                            f"Some dates in *{_parsed_ci.strftime('%d %b')} – {_parsed_co_inline.strftime('%d %b %Y')}* "
                                            f"are not available. Please choose a different range. 📅"
                                        ),
                                        customer_name=customer_name, send_context="booking_flow"
                                    )
                                    return {"status": "ok", "handled_by": "booking_checkin_range_blocked"}
                                # Both dates good — store both and jump to checkout handler
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {
                                        "booking_checkin_date": str(_parsed_ci),
                                        "booking_checkout_date": str(_parsed_co_inline),
                                        "action_context": "booking_checkout_input",
                                        "updated_at": datetime.utcnow()
                                    }}
                                )
                                # Re-use the checkout confirmation message by falling through to checkout handler
                                # Inject a synthetic body so the checkout handler processes the stored date
                                body = str(_parsed_co_inline)
                                # Fall through — checkout handler will pick up the stored checkout date
                            else:
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"booking_checkin_date": str(_parsed_ci), "action_context": "booking_checkout_input", "updated_at": datetime.utcnow()}}
                                )
                                await ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=(
                                        f"✅ Check-in: *{_parsed_ci.strftime('%A %d %B %Y')}*\n\n"
                                        f"📅 *Check-out date?*\n_Reply with a date after your check-in_"
                                    ),
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_checkin_input"}

                # BOOKING CHECK-OUT DATE HANDLER — completes rental date range
                if not button_action and not from_me and body:
                    _co_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "booking_checkout_input"
                    })
                    if _co_state:
                        # ── FlowJudge: AI reads message before rigid date parser ──
                        try:
                            from agents.flow_judge import get_flow_judge as _get_fj_co
                            _fj_co = _get_fj_co()
                            _fj_co_cur = user.get("currency") or user.get("settings", {}).get("currency", "")
                            _fj_co_result = await _fj_co.understand(
                                message=body,
                                current_step="waiting for rental check-out date",
                                waiting_for="a check-out date (must be after check-in)",
                                pending_state=_co_state,
                                language="English",
                                currency=_fj_co_cur,
                            )
                            _fj_co_action = _fj_co_result.get("action", "continue")
                            _fj_co_ws = get_whatsapp_service(db)
                            _co_svc = _co_state.get("booking_service_name", "your rental")
                            _co_ci = _co_state.get("booking_checkin_date", "")
                            if _fj_co_action == "go_back":
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "booking_checkin_input", "booking_checkin_date": None, "updated_at": datetime.utcnow()}}
                                )
                                await _fj_co_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=f"No problem! What check-in date would you like for *{_co_svc}*? 📅",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "checkout_go_back"}
                            elif _fj_co_action == "cancel":
                                await db.pending_catalogs.delete_one({"_id": _co_state["_id"]})
                                await _fj_co_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_co_result.get("reply") or "No worries! Feel free to come back anytime 😊",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "checkout_cancelled"}
                            elif _fj_co_action == "tangent":
                                await _fj_co_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_co_result.get("reply") or f"Hey! 😊 Check-in: *{_co_ci}* is set. What date would you like to check out? 📅",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "checkout_tangent"}
                            elif _fj_co_action == "unclear":
                                await _fj_co_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_co_result.get("reply") or f"What date would you like to check out? 📅\n_Check-in is {_co_ci}_",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "checkout_unclear"}
                            if _fj_co_result.get("extracted_value"):
                                body = _fj_co_result["extracted_value"]
                        except Exception as _fj_co_err:
                            logging.warning(f"[FlowJudge/checkout] {_fj_co_err}")

                        import re as _re_co
                        _co_body = body.strip()
                        _co_lower = _co_body.lower()
                        if False:
                            pass
                        else:
                            _today_co = datetime.utcnow().date()
                            _ci_date_str = _co_state.get("booking_checkin_date", "")
                            try: _ci_date = datetime.strptime(_ci_date_str, "%Y-%m-%d").date()
                            except Exception: _ci_date = _today_co
                            _parsed_co = None
                            try:
                                if _co_lower == "tomorrow": _parsed_co = _today_co + timedelta(days=1)
                                elif _co_lower in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday"):
                                    _wd = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}[_co_lower]
                                    _parsed_co = _today_co + timedelta(days=(_wd - _today_co.weekday()) % 7 or 7)
                                else:
                                    _m = _re_co.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", _co_body)
                                    if _m: _parsed_co = datetime(int(_m.group(1)), int(_m.group(2)), int(_m.group(3))).date()
                                    else:
                                        _mm = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                                               "january":1,"february":2,"march":3,"april":4,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
                                        _m2 = _re_co.match(r"(\d{1,2})\s+([a-z]+)", _co_lower)
                                        _m3 = _re_co.match(r"([a-z]+)\s+(\d{1,2})", _co_lower)
                                        if _m2 and _m2.group(2) in _mm:
                                            _d, _mo = int(_m2.group(1)), _mm[_m2.group(2)]
                                            _parsed_co = datetime(_today_co.year if (_mo,_d)>=(_today_co.month,_today_co.day) else _today_co.year+1, _mo, _d).date()
                                        elif _m3 and _m3.group(1) in _mm:
                                            _d, _mo = int(_m3.group(2)), _mm[_m3.group(1)]
                                            _parsed_co = datetime(_today_co.year if (_mo,_d)>=(_today_co.month,_today_co.day) else _today_co.year+1, _mo, _d).date()
                                        else:
                                            _m4 = _re_co.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", _co_body)
                                            if _m4: _parsed_co = datetime(int(_m4.group(3)), int(_m4.group(2)), int(_m4.group(1))).date()
                            except Exception: _parsed_co = None
                            ws = get_whatsapp_service(db)
                            if not _parsed_co or _parsed_co <= _ci_date:
                                await ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=f"Check-out must be after check-in (*{_ci_date_str}*). Please reply with a valid check-out date 📅",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_checkout_invalid"}
                            _co_user_doc = await db.users.find_one({"_id": user["_id"]})
                            _co_blocked_global = (_co_user_doc or {}).get("settings", {}).get("rental_availability") or []
                            _co_svc_id = _co_state.get("booking_service_id", "")
                            _co_listing_doc = await db.products.find_one({"_id": _co_svc_id}) if _co_svc_id else None
                            _co_blocked_listing = (_co_listing_doc or {}).get("listing_blocked_dates") or []
                            _co_all_blocked = set(_co_blocked_global) | set(_co_blocked_listing)
                            _nights_check = (_parsed_co - _ci_date).days
                            _blocked_in_range = [str(_ci_date + timedelta(days=i)) for i in range(_nights_check) if str(_ci_date + timedelta(days=i)) in _co_all_blocked]
                            if _blocked_in_range:
                                await ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=(
                                        f"Sorry, some dates in that range are not available (❌ {', '.join(_blocked_in_range[:3])}{'...' if len(_blocked_in_range) > 3 else ''}). \n"
                                        f"📅 Please reply with a different check-out date."
                                    ),
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_checkout_blocked"}
                            _nights = _nights_check
                            _co_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                            _co_base_price = _co_state.get("booking_service_price", 0)
                            _co_addons = _co_state.get("booking_selected_addons", [])
                            _co_addon_total = sum(a.get("price", 0) for a in _co_addons)
                            _co_price_unit = _co_state.get("booking_price_unit", "night")
                            _co_unit_labels = {"night": "night", "day": "day", "week": "week", "month": "month", "year": "year", "person": "person"}
                            _co_unit_label = _co_unit_labels.get(_co_price_unit, "night")
                            if _co_price_unit == "week":
                                _co_periods = max(1, round(_nights / 7))
                            elif _co_price_unit == "month":
                                _co_periods = max(1, round(_nights / 30))
                            elif _co_price_unit == "year":
                                _co_periods = max(1, round(_nights / 365))
                            elif _co_price_unit == "person":
                                _co_periods = 1
                            else:
                                _co_periods = _nights
                            _co_total = (_co_base_price * _co_periods) + _co_addon_total
                            _co_svc_name = _co_state.get("booking_service_name", "Service")
                            _co_price_str = f"{_co_currency} {_co_total:,.0f}" if _co_total else ""
                            _co_dur_label = f"{_co_periods} {_co_unit_label}{'s' if _co_periods != 1 else ''}"
                            _co_summary = (
                                f"📋 *Booking Summary*\n\n"
                                f"🏠 *{_co_svc_name}*\n"
                                f"📅 Check-in: *{_ci_date_str}*\n"
                                f"📅 Check-out: *{str(_parsed_co)}*\n"
                                f"⏱ Duration: *{_co_dur_label}*\n"
                            )
                            if _co_addons:
                                _co_summary += "🔧 Add-ons: " + ", ".join(f"{a['name']} (+{_co_currency} {a.get('price',0):,.0f})" for a in _co_addons) + "\n"
                            if _co_price_str:
                                _co_summary += f"💰 Total: *{_co_price_str}*\n"
                            _co_summary += "\nReply *YES* to confirm or *NO* to cancel"
                            await db.pending_catalogs.update_one(
                                {"customer_id": customer_id, "user_id": user["_id"]},
                                {"$set": {
                                    "action_context": "booking_confirm",
                                    "booking_checkout_date": str(_parsed_co),
                                    "booking_nights": _nights,
                                    "booking_total_price": _co_total,
                                    "booking_time": "check-in",
                                    "booking_date": _ci_date_str,
                                    "updated_at": datetime.utcnow(),
                                }}
                            )
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message=_co_summary, customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "booking_checkout_input"}

                # BOOKING DATE INPUT HANDLER — customer types a date for a pending booking
                if not button_action and not from_me and body:
                    _bk_date_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "booking_date_input"
                    })
                    if _bk_date_state:
                        # ── FlowJudge: AI reads message before rigid date parser ──
                        try:
                            from agents.flow_judge import get_flow_judge as _get_fj_bkd
                            _fj_bkd = _get_fj_bkd()
                            _fj_bkd_lang = _bk_date_state.get("preferred_language") or "English"
                            _fj_bkd_cur = user.get("currency") or user.get("settings", {}).get("currency", "")
                            _fj_bkd_result = await _fj_bkd.understand(
                                message=body,
                                current_step="waiting for booking date",
                                waiting_for="a date (today, tomorrow, Monday, 15 March, 2026-03-15)",
                                pending_state=_bk_date_state,
                                language=_fj_bkd_lang,
                                currency=_fj_bkd_cur,
                                last_bot_message=_bk_date_state.get("last_bot_message", ""),
                            )
                            _fj_bkd_action = _fj_bkd_result.get("action", "continue")
                            _fj_bkd_ws = get_whatsapp_service(db)
                            _bkd_svc = _bk_date_state.get("booking_service_name", "your service")
                            if _fj_bkd_action == "go_back":
                                # Use dynamic routing based on what customer wants to change
                                _target = _fj_bkd_result.get("target_step")
                                return await _handle_flow_go_back(
                                    target_step=_target,
                                    pending_state=_bk_date_state,
                                    customer_id=customer_id,
                                    user_id=user["_id"],
                                    from_number=from_number,
                                    customer_name=customer_name,
                                    default_step="booking_service_select"
                                )
                            elif _fj_bkd_action == "cancel":
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": None, "updated_at": datetime.utcnow()}}
                                )
                                await _fj_bkd_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_bkd_result.get("reply") or "No worries! Feel free to come back anytime 😊",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_date_cancelled"}
                            elif _fj_bkd_action == "tangent":
                                await _fj_bkd_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_bkd_result.get("reply") or f"Hey! 😊 We were just picking a date for *{_bkd_svc}* — what day works for you? 📅",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_date_tangent"}
                            elif _fj_bkd_action == "unclear":
                                await _fj_bkd_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_bkd_result.get("reply") or f"What date would you like for *{_bkd_svc}*? 📅\n_e.g. tomorrow, Monday, 15 March_",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_date_unclear"}
                            # continue — use extracted_value as cleaner date input for parser
                            if _fj_bkd_result.get("extracted_value"):
                                body = _fj_bkd_result["extracted_value"]
                        except Exception as _fj_bkd_err:
                            logging.warning(f"[FlowJudge/booking_date] {_fj_bkd_err}")

                        import re as _re_bk
                        _body_bk = body.strip()
                        _body_lower_bk = _body_bk.lower()
                        _today_bk = datetime.utcnow().date()
                        _parsed_bk_date = None
                        try:
                            # Check for common words first (exact match)
                            if "today" in _body_lower_bk:
                                _parsed_bk_date = _today_bk
                            elif "tomorrow" in _body_lower_bk or "kesho" in _body_lower_bk:
                                _parsed_bk_date = _today_bk + timedelta(days=1)
                            else:
                                # Check for weekday names
                                _wd_map = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6,
                                          "mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}
                                for _wd_name, _wd_num in _wd_map.items():
                                    if _wd_name in _body_lower_bk:
                                        _days_ahead = (_wd_num - _today_bk.weekday()) % 7 or 7
                                        _parsed_bk_date = _today_bk + timedelta(days=_days_ahead)
                                        break
                                
                                if not _parsed_bk_date:
                                    # Try YYYY-MM-DD (search anywhere in message)
                                    _m = _re_bk.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", _body_bk)
                                    if _m:
                                        _parsed_bk_date = datetime(int(_m.group(1)), int(_m.group(2)), int(_m.group(3))).date()
                                    else:
                                        # Try "15 March", "March 15", "May10" (no space), "May 10"
                                        _month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                                                      "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                                                      "january":1,"february":2,"march":3,"april":4,"june":6,
                                                      "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
                                        # Search anywhere in message, not just start
                                        _m2 = _re_bk.search(r"(\d{1,2})\s+([a-z]+)", _body_lower_bk)
                                        _m3 = _re_bk.search(r"([a-z]+)\s*(\d{1,2})", _body_lower_bk)
                                        if _m2 and _m2.group(2) in _month_map:
                                            _d, _mo = int(_m2.group(1)), _month_map[_m2.group(2)]
                                            _yr = _today_bk.year if (_mo, _d) >= (_today_bk.month, _today_bk.day) else _today_bk.year + 1
                                            _parsed_bk_date = datetime(_yr, _mo, _d).date()
                                        elif _m3 and _m3.group(1) in _month_map:
                                            _d, _mo = int(_m3.group(2)), _month_map[_m3.group(1)]
                                            _yr = _today_bk.year if (_mo, _d) >= (_today_bk.month, _today_bk.day) else _today_bk.year + 1
                                            _parsed_bk_date = datetime(_yr, _mo, _d).date()
                                        else:
                                            # Try DD/MM/YYYY or MM/DD/YYYY
                                            _m4 = _re_bk.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", _body_bk)
                                            if _m4:
                                                _parsed_bk_date = datetime(int(_m4.group(3)), int(_m4.group(2)), int(_m4.group(1))).date()
                        except Exception:
                            _parsed_bk_date = None

                        if not _parsed_bk_date or _parsed_bk_date < _today_bk:
                            ws = get_whatsapp_service(db)
                            if _parsed_bk_date and _parsed_bk_date < _today_bk:
                                _bk_err_msg = f"That date has already passed. Please reply with a future date 📅"
                            else:
                                _bk_err_msg = "I didn't catch that date. Please reply with a date like *tomorrow*, *Monday*, *15 March*, or *2026-03-15* 📅"
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message=_bk_err_msg, customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "booking_date_invalid"}

                        # Fetch business hours to validate day + build slots
                        _bk_biz_id = user.get("business_id", user["_id"])
                        _bk_user_doc = await db.users.find_one({"_id": _bk_biz_id})
                        _bk_settings = (_bk_user_doc or {}).get("settings", {})
                        _bk_biz_hours = _bk_settings.get("business_hours", {})
                        _bk_wd_keys = ["mon","tue","wed","thu","fri","sat","sun"]
                        _bk_day_key = _bk_wd_keys[_parsed_bk_date.weekday()]
                        _bk_day_hours = _bk_biz_hours.get(_bk_day_key, {})
                        
                        # Debug logging for business hours validation
                        logging.info(f"[Booking] Date={_parsed_bk_date.strftime('%A %Y-%m-%d')}, day_key={_bk_day_key}, day_hours={_bk_day_hours}, closed={_bk_day_hours.get('closed')}")

                        if _bk_day_hours.get("closed"):
                            ws = get_whatsapp_service(db)
                            _closed_msg = f"Sorry, we're closed on {_parsed_bk_date.strftime('%A %d %B')}. Please choose another date 📅"
                            await db.pending_catalogs.update_one(
                                {"customer_id": customer_id, "user_id": user["_id"]},
                                {"$set": {"last_bot_message": _closed_msg, "updated_at": datetime.utcnow()}}
                            )
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message=_closed_msg, customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "booking_date_closed"}

                        _bk_open = _bk_day_hours.get("open", "08:00")
                        _bk_close = _bk_day_hours.get("close", "17:00")

                        # Get existing bookings for that date and count per time slot
                        _bk_existing = await db.bookings.find({
                            "user_id": user["_id"],
                            "date": str(_parsed_bk_date),
                            "status": {"$nin": ["cancelled"]}
                        }).to_list(100)
                        _bk_slot_counts = {}
                        for _b in _bk_existing:
                            _bt = _b.get("time")
                            if _bt:
                                _bk_slot_counts[_bt] = _bk_slot_counts.get(_bt, 0) + 1

                        # Get service capacity (default 1 for backward compatibility)
                        _bk_capacity = 1
                        _bk_service_id = _bk_date_state.get("booking_service_id")
                        if _bk_service_id:
                            _bk_svc_doc = await db.products.find_one({"_id": _bk_service_id})
                            if _bk_svc_doc:
                                _bk_capacity = _bk_svc_doc.get("capacity", 1)

                        # Build slots using service duration (or default 60 min)
                        _bk_slot_mins = 60
                        try:
                            _raw_dur = _bk_date_state.get("booking_service_duration")
                            if _raw_dur and int(_raw_dur) >= 15:
                                _bk_slot_mins = int(_raw_dur)
                        except Exception:
                            pass
                        try:
                            _bk_oh, _bk_om = map(int, _bk_open.split(":"))
                            _bk_ch, _bk_cm = map(int, _bk_close.split(":"))
                            _bk_cur = _bk_oh * 60 + _bk_om
                            _bk_end = _bk_ch * 60 + _bk_cm
                            _bk_avail = []
                            while _bk_cur + _bk_slot_mins <= _bk_end:
                                _t = f"{_bk_cur // 60:02d}:{_bk_cur % 60:02d}"
                                _booked_count = _bk_slot_counts.get(_t, 0)
                                if _booked_count < _bk_capacity:
                                    _remaining = _bk_capacity - _booked_count
                                    _bk_avail.append({"time": _t, "remaining": _remaining})
                                _bk_cur += _bk_slot_mins
                        except Exception:
                            _bk_avail = [{"time": t, "remaining": 1} for t in ["09:00","10:00","11:00","14:00","15:00","16:00"]]
                        
                        if not _bk_avail:
                            ws = get_whatsapp_service(db)
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message=f"No available slots on {_parsed_bk_date.strftime('%A %d %B')}. Please try another date 📅",
                                customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "booking_date_no_slots"}

                        # ── Paginated time slots: show 5 per page ──
                        _BK_PAGE_SIZE = 5
                        _bk_all_slots = [{"time": s["time"], "remaining": s["remaining"]} for s in _bk_avail]
                        _bk_page_slots = _bk_all_slots[:_BK_PAGE_SIZE]
                        _bk_has_more = len(_bk_all_slots) > _BK_PAGE_SIZE

                        # Detect time-of-day period of first slot for header
                        def _bk_slot_period(t):
                            h = int(t.split(":")[0])
                            if h < 12: return "Morning"
                            if h < 17: return "Afternoon"
                            return "Evening"

                        _bk_date_label = _parsed_bk_date.strftime("%A %d %B")
                        _bk_period_label = _bk_slot_period(_bk_page_slots[0]["time"])
                        _bk_slot_lines = [f"🕐 *{_bk_period_label} — {_bk_date_label}:*\n"]
                        _bk_page_objs = []
                        for _bk_i, _bk_slot in enumerate(_bk_page_slots, 1):
                            _bk_time = _bk_slot["time"]
                            _bk_rem = _bk_slot["remaining"]
                            if _bk_capacity > 1 and _bk_rem > 1:
                                _bk_slot_lines.append(f"{_bk_i}. {_bk_time} ({_bk_rem} spots left)")
                            elif _bk_capacity > 1 and _bk_rem == 1:
                                _bk_slot_lines.append(f"{_bk_i}. {_bk_time} (1 spot left)")
                            else:
                                _bk_slot_lines.append(f"{_bk_i}. {_bk_time}")
                            _bk_page_objs.append({"index": _bk_i, "time": _bk_time, "remaining": _bk_rem})

                        _bk_nav_hints = ["_Reply with a number to select_"]
                        if _bk_has_more:
                            _bk_nav_hints.append('_"next" for more slots_')
                        # Check if afternoon/evening slots exist
                        _bk_has_afternoon = any(int(s["time"].split(":")[0]) >= 12 for s in _bk_all_slots)
                        _bk_has_evening = any(int(s["time"].split(":")[0]) >= 17 for s in _bk_all_slots)
                        if _bk_has_afternoon and _bk_period_label == "Morning":
                            _bk_nav_hints.append('_"afternoon" for afternoon slots_')
                        if _bk_has_evening and _bk_period_label != "Evening":
                            _bk_nav_hints.append('_"evening" for evening slots_')
                        _bk_slot_lines.append("\n" + " · ".join(_bk_nav_hints))

                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "action_context": "booking_time_select",
                                "booking_date": str(_parsed_bk_date),
                                "all_slots": _bk_all_slots,
                                "time_slots": _bk_page_objs,
                                "time_slots_page": 0,
                                "time_slots_period": None,
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message="\n".join(_bk_slot_lines), customer_name=customer_name, send_context="booking_flow"
                        )
                        logging.info(f"[Booking] Date={_parsed_bk_date}, total_slots={len(_bk_all_slots)}, page=0, shown={len(_bk_page_slots)} for customer={customer_id}")
                        return {"status": "ok", "handled_by": "booking_date_input"}

                # TIME SLOT NAVIGATION HANDLER — handles "next", "morning", "afternoon", "evening"
                # when customer is in booking_time_select state (navigating paginated slots)
                if not button_action and not from_me and body:
                    _bk_ts_nav_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "booking_time_select"
                    })
                    if _bk_ts_nav_state:
                        _bk_ts_body = body.strip().lower()
                        _bk_ts_all = _bk_ts_nav_state.get("all_slots", [])
                        _bk_ts_cur_page = _bk_ts_nav_state.get("time_slots_page", 0)
                        _bk_ts_capacity = 1
                        _BK_TS_PAGE_SIZE = 5

                        def _bk_ts_period_of(t):
                            h = int(t.split(":")[0])
                            if h < 12: return "Morning"
                            if h < 17: return "Afternoon"
                            return "Evening"

                        def _bk_ts_build_and_send(slots_subset, period_label, page_idx, total_all):
                            """Build slot message lines and page objs for a given subset."""
                            page_slots = slots_subset[:_BK_TS_PAGE_SIZE]
                            has_more = len(slots_subset) > _BK_TS_PAGE_SIZE
                            bk_date = _bk_ts_nav_state.get("booking_date", "")
                            try:
                                from datetime import date as _dt_date
                                _d = datetime.strptime(bk_date, "%Y-%m-%d")
                                date_label = _d.strftime("%A %d %B")
                            except Exception:
                                date_label = bk_date
                            lines = [f"🕐 *{period_label} — {date_label}:*\n"]
                            objs = []
                            for idx, s in enumerate(page_slots, 1):
                                t = s["time"]
                                rem = s.get("remaining", 1)
                                cap = _bk_ts_nav_state.get("booking_service_capacity", 1)
                                if cap > 1 and rem > 1:
                                    lines.append(f"{idx}. {t} ({rem} spots left)")
                                elif cap > 1 and rem == 1:
                                    lines.append(f"{idx}. {t} (1 spot left)")
                                else:
                                    lines.append(f"{idx}. {t}")
                                objs.append({"index": idx, "time": t, "remaining": rem})
                            nav_hints = ["_Reply with a number to select_"]
                            if has_more:
                                nav_hints.append('_"next" for more_')
                            has_aft = any(int(s["time"].split(":")[0]) >= 12 for s in total_all)
                            has_eve = any(int(s["time"].split(":")[0]) >= 17 for s in total_all)
                            if has_aft and period_label == "Morning":
                                nav_hints.append('_"afternoon" for afternoon_')
                            if has_eve and period_label != "Evening":
                                nav_hints.append('_"evening" for evening_')
                            if period_label != "Morning":
                                nav_hints.append('_"morning" for morning_')
                            lines.append("\n" + " · ".join(nav_hints))
                            return "\n".join(lines), objs, has_more

                        # Navigation word detection
                        _bk_ts_nav_action = None
                        _bk_ts_jump_period = None
                        _next_words = {"next", "more", "zaidi", "show more", "more slots", "siguiente", "suivant"}
                        _morning_words = {"morning", "asubuhi", "mañana", "matin", "subah", "صباح"}
                        _afternoon_words = {"afternoon", "mchana", "après-midi", "tarde", "dopogiorno", "بعد الظهر"}
                        _evening_words = {"evening", "jioni", "soir", "noche", "sera", "مساء"}

                        if _bk_ts_body in _next_words:
                            _bk_ts_nav_action = "next"
                        elif _bk_ts_body in _morning_words:
                            _bk_ts_nav_action = "jump"
                            _bk_ts_jump_period = "morning"
                        elif _bk_ts_body in _afternoon_words:
                            _bk_ts_nav_action = "jump"
                            _bk_ts_jump_period = "afternoon"
                        elif _bk_ts_body in _evening_words:
                            _bk_ts_nav_action = "jump"
                            _bk_ts_jump_period = "evening"

                        if _bk_ts_nav_action == "next" and _bk_ts_all:
                            # If a period is active, paginate within that period's slots only
                            _bk_ts_cur_period = _bk_ts_nav_state.get("time_slots_period")
                            if _bk_ts_cur_period:
                                _pf = {"morning": (0, 12), "afternoon": (12, 17), "evening": (17, 24)}
                                _ps, _pe = _pf.get(_bk_ts_cur_period, (0, 24))
                                _bk_ts_pool = [s for s in _bk_ts_all if _ps <= int(s["time"].split(":")[0]) < _pe]
                            else:
                                _bk_ts_pool = _bk_ts_all
                            _bk_ts_next_page = _bk_ts_cur_page + 1
                            _bk_ts_offset = _bk_ts_next_page * _BK_TS_PAGE_SIZE
                            _bk_ts_remaining_slots = _bk_ts_pool[_bk_ts_offset:]
                            if not _bk_ts_remaining_slots:
                                # Wrap around to page 0 of same pool
                                _bk_ts_next_page = 0
                                _bk_ts_remaining_slots = _bk_ts_pool
                            _bk_ts_plabel = _bk_ts_period_of(_bk_ts_remaining_slots[0]["time"])
                            _bk_ts_msg, _bk_ts_objs, _ = _bk_ts_build_and_send(_bk_ts_remaining_slots, _bk_ts_plabel, _bk_ts_next_page, _bk_ts_all)
                            await db.pending_catalogs.update_one(
                                {"customer_id": customer_id, "user_id": user["_id"]},
                                {"$set": {"time_slots": _bk_ts_objs, "time_slots_page": _bk_ts_next_page, "updated_at": datetime.utcnow()}}
                            )
                            ws = get_whatsapp_service(db)
                            await ws.send_message(user_id=user["_id"], to_number=from_number, message=_bk_ts_msg, customer_name=customer_name, send_context="booking_flow")
                            return {"status": "ok", "handled_by": "booking_time_next_page"}

                        elif _bk_ts_nav_action == "jump" and _bk_ts_all:
                            _period_filter = {"morning": (0, 12), "afternoon": (12, 17), "evening": (17, 24)}
                            _ph_start, _ph_end = _period_filter[_bk_ts_jump_period]
                            _bk_ts_period_slots = [s for s in _bk_ts_all if _ph_start <= int(s["time"].split(":")[0]) < _ph_end]
                            if not _bk_ts_period_slots:
                                ws = get_whatsapp_service(db)
                                _period_names = {"morning": "morning", "afternoon": "afternoon", "evening": "evening"}
                                await ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=f"No {_period_names[_bk_ts_jump_period]} slots available on that date. Reply with a number from the list above, or try another period.",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "booking_time_period_empty"}
                            _bk_ts_plabel = _bk_ts_jump_period.capitalize()
                            _bk_ts_msg, _bk_ts_objs, _ = _bk_ts_build_and_send(_bk_ts_period_slots, _bk_ts_plabel, 0, _bk_ts_all)
                            await db.pending_catalogs.update_one(
                                {"customer_id": customer_id, "user_id": user["_id"]},
                                {"$set": {"time_slots": _bk_ts_objs, "time_slots_page": 0, "time_slots_period": _bk_ts_jump_period, "updated_at": datetime.utcnow()}}
                            )
                            ws = get_whatsapp_service(db)
                            await ws.send_message(user_id=user["_id"], to_number=from_number, message=_bk_ts_msg, customer_name=customer_name, send_context="booking_flow")
                            return {"status": "ok", "handled_by": "booking_time_jump_period"}

                # RESTAURANT PARTY SIZE HANDLER — after time slot selection
                if not button_action and not from_me and body:
                    _rest_party_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "restaurant_party_size_input"
                    })
                    if _rest_party_state:
                        # ── FlowJudge: AI reads message before rigid number parser ──
                        try:
                            from agents.flow_judge import get_flow_judge as _get_fj_rp
                            _fj_rp = _get_fj_rp()
                            _fj_rp_result = await _fj_rp.understand(
                                message=body,
                                current_step="waiting for restaurant party size",
                                waiting_for="a number of people (1-50)",
                                pending_state=_rest_party_state,
                                language="English",
                                currency=user.get("currency", ""),
                            )
                            _fj_rp_action = _fj_rp_result.get("action", "continue")
                            _fj_rp_ws = get_whatsapp_service(db)
                            if _fj_rp_action == "cancel":
                                await db.pending_catalogs.delete_one({"_id": _rest_party_state["_id"]})
                                await _fj_rp_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_rp_result.get("reply") or "No worries! Feel free to come back anytime 😊",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "party_size_cancelled"}
                            elif _fj_rp_action == "go_back":
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "booking_time_select", "updated_at": datetime.utcnow()}}
                                )
                                await _fj_rp_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message="No problem! Reply with the time slot number to pick a different time 😊",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "party_size_go_back"}
                            elif _fj_rp_action == "tangent":
                                await _fj_rp_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_rp_result.get("reply") or "Hey! 😊 How many people will be dining? 👥",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "party_size_tangent"}
                            elif _fj_rp_action == "unclear":
                                await _fj_rp_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_rp_result.get("reply") or "How many people will be joining? (e.g. reply *2* for 2 people) 👥",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "party_size_unclear"}
                            if _fj_rp_result.get("extracted_value"):
                                body = _fj_rp_result["extracted_value"]
                        except Exception as _fj_rp_err:
                            logging.warning(f"[FlowJudge/party_size] {_fj_rp_err}")

                        _party_body = body.strip()
                        _party_size = None
                        try:
                            _party_size = int(_party_body)
                            if _party_size < 1 or _party_size > 50:
                                _party_size = None
                        except Exception:
                            pass
                        
                        ws = get_whatsapp_service(db)
                        if not _party_size:
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message="Please reply with a valid party size (1-50 people) 👥",
                                customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "restaurant_party_invalid"}
                        
                        # Ask for special requests
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "restaurant_party_size": _party_size,
                                "action_context": "restaurant_requests_input",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=(
                                f"✅ Party size: *{_party_size} {'person' if _party_size == 1 else 'people'}*\n\n"
                                f"📝 *Any special requests?*\n"
                                f"_e.g. window seat, high chair, dietary restrictions_\n\n"
                                f"Reply *NONE* if no special requests"
                            ),
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "restaurant_party_size_input"}

                # RESTAURANT SPECIAL REQUESTS HANDLER
                if not button_action and not from_me and body:
                    _rest_req_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "restaurant_requests_input"
                    })
                    if _rest_req_state:
                        _req_body = body.strip()
                        _special_requests = "" if _req_body.lower() in ("none", "no", "nope", "nothing") else _req_body
                        
                        # Show booking summary
                        _rest_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                        _rest_svc_name = _rest_req_state.get("booking_service_name", "")
                        _rest_price = _rest_req_state.get("booking_service_price", 0)
                        _rest_date = _rest_req_state.get("booking_date", "")
                        _rest_time = _rest_req_state.get("booking_time", "")
                        _rest_party = _rest_req_state.get("restaurant_party_size", 1)
                        _rest_price_str = f"{_rest_currency} {_rest_price:,.0f}" if _rest_price else ""
                        
                        _rest_summary = (
                            f"✅ *Reservation Summary*\n\n"
                            f"🍽️ Restaurant: *{_rest_svc_name}*\n"
                            f"📅 Date: *{_rest_date}*\n"
                            f"🕐 Time: *{_rest_time}*\n"
                            f"👥 Party size: *{_rest_party} {'person' if _rest_party == 1 else 'people'}*\n"
                            + (f"📝 Special requests: {_special_requests}\n" if _special_requests else "")
                            + (f"💰 Price: *{_rest_price_str}*\n" if _rest_price_str else "")
                            + f"\nReply *YES* to confirm or *NO* to cancel"
                        )
                        
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "restaurant_special_requests": _special_requests,
                                "action_context": "booking_confirm",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=_rest_summary,
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "restaurant_requests_input"}

                # CREATOR TIMELINE/DEADLINE HANDLER
                if not button_action and not from_me and body:
                    _cr_timeline_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "creator_timeline_input"
                    })
                    if _cr_timeline_state:
                        # ── FlowJudge: AI reads message before rigid timeline parser ──
                        try:
                            from agents.flow_judge import get_flow_judge as _get_fj_cr
                            _fj_cr = _get_fj_cr()
                            _fj_cr_result = await _fj_cr.understand(
                                message=body,
                                current_step="waiting for project deadline/timeline",
                                waiting_for="a deadline or timeframe (e.g. in 2 weeks, next Friday, 15 March)",
                                pending_state=_cr_timeline_state,
                                language="English",
                                currency=user.get("currency", ""),
                            )
                            _fj_cr_action = _fj_cr_result.get("action", "continue")
                            _fj_cr_ws = get_whatsapp_service(db)
                            _cr_svc = _cr_timeline_state.get("booking_service_name", "your project")
                            if _fj_cr_action == "go_back":
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "booking_service_select", "updated_at": datetime.utcnow()}}
                                )
                                await _fj_cr_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message="No problem! Which service would you like instead? Reply with the number 😊",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "creator_timeline_go_back"}
                            elif _fj_cr_action == "cancel":
                                await db.pending_catalogs.delete_one({"_id": _cr_timeline_state["_id"]})
                                await _fj_cr_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_cr_result.get("reply") or "No worries! Feel free to come back anytime 😊",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "creator_timeline_cancelled"}
                            elif _fj_cr_action == "tangent":
                                await _fj_cr_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_cr_result.get("reply") or f"Hey! 😊 We were setting a timeline for *{_cr_svc}* — when would you need it by? 📅",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "creator_timeline_tangent"}
                            elif _fj_cr_action == "unclear":
                                await _fj_cr_ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message=_fj_cr_result.get("reply") or "When do you need *{_cr_svc}* completed? 📅\n_e.g. in 2 weeks, next Friday, 15 March_",
                                    customer_name=customer_name, send_context="booking_flow"
                                )
                                return {"status": "ok", "handled_by": "creator_timeline_unclear"}
                            if _fj_cr_result.get("extracted_value"):
                                body = _fj_cr_result["extracted_value"]
                        except Exception as _fj_cr_err:
                            logging.warning(f"[FlowJudge/creator_timeline] {_fj_cr_err}")

                        import re as _re_cr
                        _timeline_body = body.strip()
                        _timeline_lower = _timeline_body.lower()
                        _today_cr = datetime.utcnow().date()
                        _parsed_deadline = None
                        
                        try:
                            # Parse relative dates like "in 3 days", "in 1 week"
                            _m_days = _re_cr.search(r"in\s+(\d+)\s+days?", _timeline_lower)
                            _m_weeks = _re_cr.search(r"in\s+(\d+)\s+weeks?", _timeline_lower)
                            if _m_days:
                                _parsed_deadline = _today_cr + timedelta(days=int(_m_days.group(1)))
                            elif _m_weeks:
                                _parsed_deadline = _today_cr + timedelta(weeks=int(_m_weeks.group(1)))
                            elif _timeline_lower == "today":
                                _parsed_deadline = _today_cr
                            elif _timeline_lower == "tomorrow":
                                _parsed_deadline = _today_cr + timedelta(days=1)
                            elif _timeline_lower.startswith("next "):
                                _day_name = _timeline_lower.replace("next ", "").strip()
                                if _day_name in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday"):
                                    _wd_map = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
                                    _tgt_wd = _wd_map[_day_name]
                                    _days_ahead = (_tgt_wd - _today_cr.weekday()) % 7 or 7
                                    _parsed_deadline = _today_cr + timedelta(days=_days_ahead)
                            else:
                                # Try standard date formats
                                _month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                                              "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                                              "january":1,"february":2,"march":3,"april":4,"june":6,
                                              "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
                                _m2 = _re_cr.match(r"(\d{1,2})\s+([a-z]+)", _timeline_lower)
                                _m3 = _re_cr.match(r"([a-z]+)\s*(\d{1,2})", _timeline_lower)
                                if _m2 and _m2.group(2) in _month_map:
                                    _d, _mo = int(_m2.group(1)), _month_map[_m2.group(2)]
                                    _yr = _today_cr.year if (_mo, _d) >= (_today_cr.month, _today_cr.day) else _today_cr.year + 1
                                    _parsed_deadline = datetime(_yr, _mo, _d).date()
                                elif _m3 and _m3.group(1) in _month_map:
                                    _d, _mo = int(_m3.group(2)), _month_map[_m3.group(1)]
                                    _yr = _today_cr.year if (_mo, _d) >= (_today_cr.month, _today_cr.day) else _today_cr.year + 1
                                    _parsed_deadline = datetime(_yr, _mo, _d).date()
                        except Exception:
                            _parsed_deadline = None
                        
                        ws = get_whatsapp_service(db)
                        if not _parsed_deadline or _parsed_deadline < _today_cr:
                            await ws.send_message(
                                user_id=user["_id"], to_number=from_number,
                                message="I didn't catch that deadline. Please reply with a date like *in 3 days*, *next Friday*, or *March 20* 📅",
                                customer_name=customer_name, send_context="booking_flow"
                            )
                            return {"status": "ok", "handled_by": "creator_timeline_invalid"}
                        
                        # Ask for budget
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "creator_deadline": str(_parsed_deadline),
                                "action_context": "creator_budget_input",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=(
                                f"✅ Deadline: *{_parsed_deadline.strftime('%A %d %B %Y')}*\n\n"
                                f"💰 *What's your budget?*\n"
                                f"_Reply with an amount or *FLEXIBLE* if negotiable_"
                            ),
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "creator_timeline_input"}

                # CREATOR BUDGET HANDLER
                if not button_action and not from_me and body:
                    _cr_budget_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "creator_budget_input"
                    })
                    if _cr_budget_state:
                        _budget_body = body.strip()
                        _budget_lower = _budget_body.lower()
                        _budget_amount = None
                        _budget_text = _budget_body
                        
                        if _budget_lower in ("flexible", "negotiable", "open", "tbd"):
                            _budget_text = "Flexible/Negotiable"
                        else:
                            try:
                                import re as _re_budget
                                _num_match = _re_budget.search(r"[\d,]+", _budget_body)
                                if _num_match:
                                    _budget_amount = int(_num_match.group().replace(",", ""))
                            except Exception:
                                pass
                        
                        # Ask for project details
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "creator_budget": _budget_text,
                                "creator_budget_amount": _budget_amount,
                                "action_context": "creator_details_input",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=(
                                f"✅ Budget: *{_budget_text}*\n\n"
                                f"📝 *Tell me about your project*\n"
                                f"_What do you need? Include any specific requirements, deliverables, or details_"
                            ),
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "creator_budget_input"}

                # CREATOR PROJECT DETAILS HANDLER
                if not button_action and not from_me and body:
                    _cr_details_state = await db.pending_catalogs.find_one({
                        "customer_id": customer_id, "user_id": user["_id"],
                        "action_context": "creator_details_input"
                    })
                    if _cr_details_state:
                        _details_body = body.strip()
                        
                        # Show booking summary
                        _cr_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                        _cr_svc_name = _cr_details_state.get("booking_service_name", "")
                        _cr_price = _cr_details_state.get("booking_service_price", 0)
                        _cr_deadline = _cr_details_state.get("creator_deadline", "")
                        _cr_budget = _cr_details_state.get("creator_budget", "")
                        _cr_price_str = f"{_cr_currency} {_cr_price:,.0f}" if _cr_price else ""
                        
                        _cr_summary = (
                            f"✅ *Collaboration Summary*\n\n"
                            f"🎨 Service: *{_cr_svc_name}*\n"
                            f"📅 Deadline: *{_cr_deadline}*\n"
                            f"💰 Budget: *{_cr_budget}*\n"
                            + (f"💵 Base price: *{_cr_price_str}*\n" if _cr_price_str else "")
                            + f"📝 Details: {_details_body[:200]}{'...' if len(_details_body) > 200 else ''}\n"
                            + f"\nReply *YES* to confirm or *NO* to cancel"
                        )
                        
                        await db.pending_catalogs.update_one(
                            {"customer_id": customer_id, "user_id": user["_id"]},
                            {"$set": {
                                "creator_project_details": _details_body,
                                "action_context": "booking_confirm",
                                "updated_at": datetime.utcnow()
                            }}
                        )
                        
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=user["_id"], to_number=from_number,
                            message=_cr_summary,
                            customer_name=customer_name, send_context="booking_flow"
                        )
                        return {"status": "ok", "handled_by": "creator_details_input"}

                # BOOKING CONFIRMATION — FlowJudge for ambiguous messages (not clear YES/NO)
                if not button_action and not from_me and body:
                    _bkc_pre_body = body.strip().lower()
                    _bkc_pre_yes = {"yes","yeah","yep","sure","ok","okay","confirm","ndio","sawa","yes please",
                                    "sounds good","let's do it","go ahead","book it","great","perfect","done"}
                    _bkc_pre_no  = {"no","nope","cancel","hapana","nah","no thanks","no thank you",
                                    "never mind","forget it","don't","dont","stop","acha"}
                    if _bkc_pre_body not in _bkc_pre_yes and _bkc_pre_body not in _bkc_pre_no:
                        _bkc_fj_state = await db.pending_catalogs.find_one({
                            "customer_id": customer_id, "user_id": user["_id"],
                            "action_context": "booking_confirm"
                        })
                        if _bkc_fj_state:
                            try:
                                from agents.flow_judge import get_flow_judge as _get_fj_bc
                                _fj_bc = _get_fj_bc()
                                _fj_bc_cur = user.get("currency") or user.get("settings", {}).get("currency", "")
                                _fj_bc_result = await _fj_bc.understand(
                                    message=body,
                                    current_step="waiting for booking confirmation",
                                    waiting_for="YES to confirm or NO to cancel",
                                    pending_state=_bkc_fj_state,
                                    language="English",
                                    currency=_fj_bc_cur,
                                )
                                _fj_bc_action = _fj_bc_result.get("action", "unclear")
                                _bc_ws = get_whatsapp_service(db)
                                _bc_svc = _bkc_fj_state.get("booking_service_name", "your service")
                                _bc_date = _bkc_fj_state.get("booking_date", "")
                                _bc_time = _bkc_fj_state.get("booking_time", "")
                                if _fj_bc_action == "continue":
                                    # AI extracted a yes/no intent — map to body for existing handler
                                    _ext_bc = (_fj_bc_result.get("extracted_value") or "").lower()
                                    _bkc_pre_body = "yes" if _ext_bc in ("yes","confirm","y","sure","ok","ndio","sawa","agree","book","proceed") else "no"
                                    # Fall through to YES/NO handler below with updated _bkc_pre_body
                                    # We need to re-route to the handler — set body to the extracted value
                                    body = _bkc_pre_body
                                elif _fj_bc_action == "go_back":
                                    await db.pending_catalogs.update_one(
                                        {"customer_id": customer_id, "user_id": user["_id"]},
                                        {"$set": {"action_context": "booking_date_input",
                                                  "booking_time": None, "updated_at": datetime.utcnow()}}
                                    )
                                    await _bc_ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message=f"No problem! Let's pick a new date for *{_bc_svc}* 📅\n_Reply with a date, e.g. tomorrow, Monday, 15 March_",
                                        customer_name=customer_name, send_context="booking_flow"
                                    )
                                    return {"status": "ok", "handled_by": "booking_confirm_go_back"}
                                elif _fj_bc_action == "cancel":
                                    await db.pending_catalogs.update_one(
                                        {"customer_id": customer_id, "user_id": user["_id"]},
                                        {"$set": {"action_context": None, "updated_at": datetime.utcnow()}}
                                    )
                                    await _bc_ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message=_fj_bc_result.get("reply") or "No worries! Feel free to come back anytime 😊",
                                        customer_name=customer_name, send_context="booking_flow"
                                    )
                                    return {"status": "ok", "handled_by": "booking_confirm_cancelled"}
                                elif _fj_bc_action == "tangent":
                                    _summary_hint = (f" for *{_bc_svc}*" + (f" on {_bc_date} at {_bc_time}" if _bc_date and _bc_time else ""))
                                    _tangent_msg = _fj_bc_result.get("reply") or (
                                        f"Hey! 😊 We were just confirming your booking{_summary_hint}. Reply *YES* to confirm or *NO* to cancel."
                                    )
                                    await _bc_ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message=_tangent_msg, customer_name=customer_name, send_context="booking_flow"
                                    )
                                    return {"status": "ok", "handled_by": "booking_confirm_tangent"}
                                else:  # unclear
                                    _bkc_re_summary = (
                                        f"Just to confirm your booking:\n"
                                        f"📋 *{_bc_svc}*\n"
                                        + (f"📅 {_bc_date}" if _bc_date else "")
                                        + (f" at {_bc_time}" if _bc_time else "")
                                        + f"\n\nReply *YES* to confirm or *NO* to cancel 😊"
                                    )
                                    await _bc_ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message=_bkc_re_summary, customer_name=customer_name, send_context="booking_flow"
                                    )
                                    return {"status": "ok", "handled_by": "booking_confirm_unclear"}
                            except Exception as _fj_bc_err:
                                logging.warning(f"[FlowJudge/booking_confirm] {_fj_bc_err}")

                # BOOKING CONFIRMATION HANDLER — customer said YES or NO to booking summary
                if not button_action and not from_me and body:
                    _bkc_body = body.strip().lower()
                    _bkc_yes = {"yes","yeah","yep","sure","ok","okay","confirm","ndio","sawa","yes please",
                                "sounds good","let's do it","go ahead","book it","great","perfect","done"}
                    _bkc_no  = {"no","nope","cancel","hapana","nah","no thanks","no thank you",
                                "never mind","forget it","don't","dont","stop","acha"}
                    if _bkc_body in _bkc_yes or _bkc_body in _bkc_no:
                        _bkc_state = await db.pending_catalogs.find_one({
                            "customer_id": customer_id, "user_id": user["_id"],
                            "action_context": "booking_confirm"
                        })
                        if _bkc_state:
                            _bkc_biz_id = user.get("business_id", user["_id"])
                            _bkc_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                            if _bkc_body in _bkc_yes:
                                _bkc_now = datetime.utcnow()
                                _bkc_svc_name = _bkc_state.get("booking_service_name", "Service")
                                _bkc_svc_id   = _bkc_state.get("booking_service_id", "")
                                _bkc_price    = _bkc_state.get("booking_service_price", 0)
                                _bkc_date_str = _bkc_state.get("booking_date", "")
                                _bkc_time_str = _bkc_state.get("booking_time", "")
                                _bkc_price_str = f"{_bkc_currency} {_bkc_price:,.0f}" if _bkc_price else ""
                                _reschedule_id = _bkc_state.get("reschedule_booking_id")
                                _reschedule_num = _bkc_state.get("reschedule_booking_number", "")

                                if _reschedule_id:
                                    # RESCHEDULE — update existing booking
                                    await db.bookings.update_one(
                                        {"_id": _reschedule_id},
                                        {"$set": {
                                            "date": _bkc_date_str,
                                            "time": _bkc_time_str,
                                            "status": "pending",
                                            "rescheduled_at": _bkc_now,
                                            "rescheduled_by": "customer",
                                            "updated_at": _bkc_now,
                                        }}
                                    )
                                    _bkc_number = _reschedule_num
                                    _bkc_conf_msg = (
                                        f"✅ *Booking Rescheduled!*\n\n"
                                        f"🔖 Ref: *{_bkc_number}*\n"
                                        f"📋 Service: *{_bkc_svc_name}*\n"
                                        f"📅 New Date: *{_bkc_date_str}*\n"
                                        f"🕐 New Time: *{_bkc_time_str}*\n"
                                        + (f"💰 Price: *{_bkc_price_str}*\n" if _bkc_price_str else "")
                                        + f"\nSee you then! 😊"
                                    )
                                    _bkc_push_title = "🔄 Booking Rescheduled"
                                    _bkc_push_body = f"{customer_name} rescheduled {_bkc_svc_name} to {_bkc_date_str} at {_bkc_time_str}"
                                    _bkc_push_type = "booking_rescheduled"
                                    _bkc_id = _reschedule_id
                                    logging.info(f"[Booking] Rescheduled via WhatsApp: {_reschedule_id}")
                                else:
                                    # NEW BOOKING — insert
                                    # VALIDATE BUSINESS HOURS before creating booking
                                    try:
                                        from datetime import datetime as _dt_bkc
                                        _bkc_date_obj = _dt_bkc.strptime(_bkc_date_str, "%Y-%m-%d").date()
                                        _bkc_biz_id_check = user.get("business_id", user["_id"])
                                        _bkc_user_doc = await db.users.find_one({"_id": _bkc_biz_id_check})
                                        _bkc_settings = (_bkc_user_doc or {}).get("settings", {})
                                        _bkc_biz_hours = _bkc_settings.get("business_hours", {})
                                        _bkc_wd_keys = ["mon","tue","wed","thu","fri","sat","sun"]
                                        _bkc_day_key = _bkc_wd_keys[_bkc_date_obj.weekday()]
                                        _bkc_day_hours = _bkc_biz_hours.get(_bkc_day_key, {})
                                        
                                        if _bkc_day_hours.get("closed"):
                                            logging.warning(f"[Booking] Blocked booking on closed day: {_bkc_date_str} ({_bkc_day_key})")
                                            ws = get_whatsapp_service(db)
                                            await ws.send_message(
                                                user_id=user["_id"], to_number=from_number,
                                                message=f"Sorry, we're closed on {_bkc_date_obj.strftime('%A %d %B')}. Your booking was not created. Please choose another date 📅",
                                                customer_name=customer_name, send_context="booking_flow"
                                            )
                                            await db.pending_catalogs.delete_one({"customer_id": customer_id, "user_id": user["_id"]})
                                            return {"status": "ok", "handled_by": "booking_confirm_closed_day_blocked"}
                                    except Exception as _bkc_val_err:
                                        logging.error(f"[Booking] Business hours validation error: {_bkc_val_err}")
                                    
                                    _bkc_id = str(uuid.uuid4())
                                    _bkc_number = _generate_booking_number()
                                    _bkc_selected_addons = _bkc_state.get("booking_selected_addons", [])
                                    _bkc_checkout = _bkc_state.get("booking_checkout_date", "")
                                    _bkc_nights = _bkc_state.get("booking_nights", 0)
                                    _bkc_total = _bkc_state.get("booking_total_price") or _bkc_price
                                    _bkc_svc_cat = _bkc_state.get("booking_service_category", "appointment")
                                    # Fetch deposit_percent from product doc
                                    _bkc_listing_doc = await db.products.find_one({"_id": _bkc_svc_id}) if _bkc_svc_id else None
                                    _bkc_deposit_pct = (_bkc_listing_doc or {}).get("deposit_percent", 0) or 0
                                    _bkc_deposit_amt = round((_bkc_total or _bkc_price) * _bkc_deposit_pct / 100, 2) if _bkc_deposit_pct > 0 else 0
                                    _bkc_payment_status = "deposit_pending" if _bkc_deposit_pct > 0 else "unpaid"
                                    # Restaurant and creator-specific fields
                                    _bkc_party_size = _bkc_state.get("restaurant_party_size")
                                    _bkc_special_req = _bkc_state.get("restaurant_special_requests")
                                    _bkc_deadline = _bkc_state.get("creator_deadline")
                                    _bkc_budget = _bkc_state.get("creator_budget")
                                    _bkc_project_details = _bkc_state.get("creator_project_details")
                                    
                                    await db.bookings.insert_one({
                                        "_id": _bkc_id,
                                        "booking_number": _bkc_number,
                                        "user_id": _bkc_biz_id,
                                        "customer_id": customer_id,
                                        "customer_name": customer_name,
                                        "customer_phone": from_number,
                                        "service_id": _bkc_svc_id,
                                        "service_name": _bkc_svc_name,
                                        "service_category": _bkc_svc_cat,
                                        "date": _bkc_date_str,
                                        "time": _bkc_time_str,
                                        "checkin_date": _bkc_date_str if _bkc_svc_cat == "rental" else None,
                                        "checkout_date": _bkc_checkout or None,
                                        "nights": _bkc_nights or None,
                                        "addons": _bkc_selected_addons,
                                        "party_size": _bkc_party_size,
                                        "special_requests": _bkc_special_req,
                                        "deadline": _bkc_deadline,
                                        "budget": _bkc_budget,
                                        "project_details": _bkc_project_details,
                                        "status": "pending",
                                        "payment_status": _bkc_payment_status,
                                        "deposit_percent": _bkc_deposit_pct,
                                        "deposit_amount": _bkc_deposit_amt,
                                        "price": _bkc_price,
                                        "total_price": _bkc_total,
                                        "source": "whatsapp",
                                        "created_at": _bkc_now,
                                        "updated_at": _bkc_now,
                                    })
                                    # Create sales record so booking appears in CRM sales/revenue tab
                                    _bkc_sale_amount = _bkc_total or _bkc_price or 0
                                    await db.sales.insert_one({
                                        "_id": str(uuid.uuid4()),
                                        "user_id": _bkc_biz_id,
                                        "customer_id": customer_id,
                                        "customer_name": customer_name,
                                        "product": _bkc_svc_name,
                                        "product_id": _bkc_svc_id,
                                        "amount": _bkc_sale_amount,
                                        "quantity": 1,
                                        "type": "booking",
                                        "status": "pending_payment",
                                        "payment_status": _bkc_payment_status,
                                        "booking_id": _bkc_id,
                                        "booking_number": _bkc_number,
                                        "source": "whatsapp_booking",
                                        "created_at": _bkc_now,
                                    })
                                    # Update customer stats
                                    await db.customers.update_one(
                                        {"_id": customer_id},
                                        {
                                            "$inc": {"purchase_count": 1, "total_spent": _bkc_sale_amount},
                                            "$set": {"last_contacted": _bkc_now}
                                        }
                                    )
                                    _bkc_total_str = f"{_bkc_currency} {_bkc_total:,.0f}" if _bkc_total else _bkc_price_str
                                    _bkc_deposit_str = f"{_bkc_currency} {_bkc_deposit_amt:,.0f}" if _bkc_deposit_amt else ""
                                    # Build payment methods snippet (full details incl. multi-field format)
                                    _bkc_pm_doc = await db.users.find_one({"_id": _bkc_biz_id})
                                    _bkc_raw_pm = (_bkc_pm_doc or {}).get("payment_methods", []) or []
                                    _bkc_pm_lines = []
                                    for _pm in _bkc_raw_pm:
                                        if isinstance(_pm, dict) and _pm.get("name"):
                                            _line = f"  • *{_pm['name']}*"
                                            if _pm.get("fields"):
                                                _fparts = [f"{f['label']}: {f['value']}" for f in _pm["fields"] if f.get("value") and str(f["value"]).strip()]
                                                if _fparts: _line += " — " + ", ".join(_fparts)
                                            elif _pm.get("details"):
                                                _line += f": {_pm['details']}"
                                            _bkc_pm_lines.append(_line)
                                        elif isinstance(_pm, str) and _pm.strip():
                                            _bkc_pm_lines.append(f"  • *{_pm}*")
                                    _bkc_pm_block = ("\n".join(_bkc_pm_lines) + "\n") if _bkc_pm_lines else ""
                                    if _bkc_deposit_pct > 0:
                                        _bkc_deposit_block = (
                                            f"\n💳 *Deposit Required ({_bkc_deposit_pct}%)*\n"
                                            f"Please send *{_bkc_deposit_str}* to secure your booking:\n"
                                            + _bkc_pm_block
                                            + f"\nSend proof of payment once done. Remaining balance due on arrival."
                                        )
                                    elif _bkc_pm_block:
                                        _bkc_deposit_block = (
                                            f"\n💳 *Payment Details:*\n"
                                            + _bkc_pm_block
                                            + f"\nFull amount of *{_bkc_total_str}* is due on arrival. "
                                            f"You may also send payment in advance via the above details and share proof of payment."
                                        )
                                    else:
                                        _bkc_deposit_block = (
                                            f"\n💰 Full amount of *{_bkc_total_str}* is due on arrival." if _bkc_total_str else ""
                                        )
                                    _bkc_closing = "\n\nWe look forward to having you! 😊 If you need to change anything, just say *reschedule*."
                                    if _bkc_svc_cat == "rental":
                                        _bkc_conf_msg = (
                                            f"✅ *Booking Confirmed!*\n\n"
                                            f"🔖 Ref: *{_bkc_number}*\n"
                                            f"🏠 *{_bkc_svc_name}*\n"
                                            f"📅 Check-in: *{_bkc_date_str}*\n"
                                            f"📅 Check-out: *{_bkc_checkout}*\n"
                                            f"🌙 {_bkc_nights} night(s)\n"
                                            + ("🔧 Add-ons: " + ", ".join(a["name"] for a in _bkc_selected_addons) + "\n" if _bkc_selected_addons else "")
                                            + (f"💰 Total: *{_bkc_total_str}*\n" if _bkc_total_str else "")
                                            + _bkc_deposit_block
                                            + _bkc_closing
                                        )
                                    else:
                                        _bkc_conf_msg = (
                                            f"✅ *Booking Confirmed!*\n\n"
                                            f"🔖 Ref: *{_bkc_number}*\n"
                                            f"📋 Service: *{_bkc_svc_name}*\n"
                                            + ("🔧 Add-ons: " + ", ".join(a["name"] for a in _bkc_selected_addons) + "\n" if _bkc_selected_addons else "")
                                            + f"📅 Date: *{_bkc_date_str}*\n"
                                            f"🕐 Time: *{_bkc_time_str}*\n"
                                            + (f"💰 Total: *{_bkc_total_str}*\n" if _bkc_total_str else "")
                                            + _bkc_deposit_block
                                            + _bkc_closing
                                        )
                                    # Append other available services to the confirmation message
                                    try:
                                        _bkc_other_svcs = await db.products.find(
                                            {"user_id": _bkc_biz_id, "in_stock": {"$ne": False}},
                                        ).to_list(20)
                                        # Exclude the service they just booked
                                        _bkc_other_svcs = [s for s in _bkc_other_svcs if str(s["_id"]) != str(_bkc_svc_id)]
                                        if _bkc_other_svcs:
                                            _bkc_currency_str = _bkc_currency
                                            _bkc_other_lines = ["\n\n✨ *Our other services:*"]
                                            for _os in _bkc_other_svcs[:5]:
                                                _os_price = _os.get("price", 0)
                                                _os_price_str = f"{_bkc_currency_str} {_os_price:,.0f}" if _os_price else "Contact for price"
                                                _os_dur = f" · {_os['duration']} min" if _os.get("duration") else ""
                                                _bkc_other_lines.append(f"  • *{_os['name']}* — {_os_price_str}{_os_dur}")
                                            _bkc_other_lines.append("\n_Reply *book* anytime to make another appointment._")
                                            _bkc_conf_msg += "\n".join(_bkc_other_lines)
                                    except Exception as _bkc_other_err:
                                        logging.warning(f"[Booking] Other services fetch failed: {_bkc_other_err}")

                                    # Auto-block confirmed rental booking dates on the listing
                                    if _bkc_svc_cat == "rental" and _bkc_svc_id and _bkc_checkout and _bkc_date_str:
                                        try:
                                            from datetime import date as _date_cls
                                            _bl_ci = datetime.strptime(_bkc_date_str, "%Y-%m-%d").date()
                                            _bl_co = datetime.strptime(_bkc_checkout, "%Y-%m-%d").date()
                                            _bl_range = [str(_bl_ci + timedelta(days=i)) for i in range((_bl_co - _bl_ci).days)]
                                            if _bl_range:
                                                await db.products.update_one(
                                                    {"_id": _bkc_svc_id},
                                                    {"$addToSet": {"listing_blocked_dates": {"$each": _bl_range}}}
                                                )
                                                logging.info(f"[Booking] Auto-blocked dates {_bl_range[0]}→{_bl_range[-1]} on listing {_bkc_svc_id}")
                                        except Exception as _bl_err:
                                            logging.warning(f"[Booking] Auto-block dates failed: {_bl_err}")
                                    _bkc_push_title = "📅 New Booking!"
                                    _bkc_push_body = f"{customer_name} booked {_bkc_svc_name} on {_bkc_date_str} at {_bkc_time_str}"
                                    _bkc_push_type = "new_booking"
                                    logging.info(f"[Booking] Created via WhatsApp confirm: {_bkc_id}")

                                ws = get_whatsapp_service(db)
                                await ws.send_message(
                                    user_id=_bkc_biz_id, to_number=from_number,
                                    message=_bkc_conf_msg, customer_name=customer_name, send_context="booking_confirm"
                                )
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "product", "updated_at": _bkc_now}}
                                )
                                await db.customers.update_one(
                                    {"_id": customer_id}, {"$set": {"last_contacted": _bkc_now}}
                                )
                                # Push notification to owner
                                _bkc_owner = await db.users.find_one({"_id": _bkc_biz_id}, {"expo_push_token": 1})
                                _bkc_push = (_bkc_owner or {}).get("expo_push_token", "")
                                if _bkc_push:
                                    try:
                                        from notification_service import get_notification_service
                                        _bkc_ns = get_notification_service()
                                        await _bkc_ns.send_notification(
                                            push_token=_bkc_push,
                                            title=_bkc_push_title,
                                            body=_bkc_push_body,
                                            data={"type": _bkc_push_type, "booking_id": _bkc_id, "customer_id": customer_id}
                                        )
                                    except Exception as _bkc_ne:
                                        logging.warning(f"Booking push failed: {_bkc_ne}")
                                return {"status": "ok", "handled_by": "booking_confirm_yes"}
                            else:
                                ws = get_whatsapp_service(db)
                                await ws.send_message(
                                    user_id=user["_id"], to_number=from_number,
                                    message="No problem! If you'd like to book again, just say *book* or ask about our services. 😊",
                                    customer_name=customer_name, send_context="booking_cancel"
                                )
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "product", "updated_at": datetime.utcnow()}}
                                )
                                logging.info(f"[Booking] Cancelled via NO reply for customer={customer_id}")
                                return {"status": "ok", "handled_by": "booking_confirm_no"}

                # Handle button actions
                if button_action and (button_product_id or button_action in ("checkout", "continue", "cancel_cart")):
                    try:
                        if button_action == "order":
                            # Customer clicked "Order Now" — ask for confirmation first, don't create order yet
                            _biz_id = user.get("business_id", user["_id"])
                            product = await db.products.find_one({"_id": button_product_id, "user_id": _biz_id})
                            if product:
                                currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                _price = product.get("price", 0)
                                confirm_req = (
                                    f"📦 *Please confirm your order:*\n\n"
                                    f"🛍️ *{product['name']}*\n"
                                    f"💰 {currency} {_price:,.0f}\n"
                                    f"Qty: 1\n\n"
                                    f"Reply *YES* to confirm or *NO* to cancel"
                                )
                                ws = get_whatsapp_service(db)
                                await ws.send_message(
                                    user_id=_biz_id,
                                    to_number=from_number,
                                    message=confirm_req,
                                    customer_name=customer_name,
                                    send_context="order_request"
                                )
                                # Store context so YES/NO reply is understood
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {
                                        "action_context": "order_confirm",
                                        "confirm_product_id": button_product_id,
                                        "updated_at": datetime.utcnow()
                                    }},
                                    upsert=True
                                )
                                logging.info(f"Order confirmation requested: product={button_product_id}, customer={customer_id}")
                                return {"status": "ok", "handled_by": "order_request"}
                        
                        elif button_action == "details":
                            # Customer clicked "More Info" button
                            product = await db.products.find_one({"_id": button_product_id, "user_id": user["_id"]})
                            if product:
                                ws = get_whatsapp_service(db)
                                _details_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                detailed_msg = ws.format_product_message(product, currency=_details_currency)
                                await ws.send_message(
                                    user_id=user["_id"],
                                    to_number=from_number,
                                    message=detailed_msg,
                                    customer_name=customer_name,
                                    send_context="product_send"
                                )
                                logging.info(f"Product details sent for button click: {button_product_id}")
                                return {"status": "ok", "handled_by": "button_details"}
                        
                        elif button_action == "select":
                            # Customer selected product from list
                            product = await db.products.find_one({"_id": button_product_id, "user_id": user["_id"]})
                            if product:
                                # Send full product showcase with buttons
                                currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                product_data = {"currency": currency, **product}
                                
                                ws = get_whatsapp_service(db)
                                await ws.send_product_showcase(
                                    user_id=user["_id"],
                                    to_number=from_number,
                                    product=product_data,
                                    send_buttons=True
                                )
                                logging.info(f"Product showcase sent for list selection: {button_product_id}")
                                return {"status": "ok", "handled_by": "button_select"}
                        
                        elif button_action == "share":
                            # Customer clicked "Share" button
                            share_msg = (
                                "📱 To share this product with a friend, simply forward this message to them!\n\n"
                                "They can also visit our store to see our full catalog. 🛍️"
                            )
                            
                            ws = get_whatsapp_service(db)
                            await ws.send_message(
                                user_id=user["_id"],
                                to_number=from_number,
                                message=share_msg,
                                customer_name=customer_name,
                                send_context="auto_reply"
                            )
                            logging.info(f"Share instructions sent for button click: {button_product_id}")
                            return {"status": "ok", "handled_by": "button_share"}
                        
                        elif button_action == "add_to_cart":
                            # Customer selected "Add to Cart" from button
                            _biz_id = user.get("business_id", user["_id"])
                            product = await db.products.find_one({"_id": button_product_id, "user_id": _biz_id})
                            if product:
                                currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                await db.carts.update_one(
                                    {"customer_id": customer_id, "user_id": _biz_id, "status": "active"},
                                    {
                                        "$push": {"items": {
                                            "product_id": product["_id"],
                                            "product_name": product["name"],
                                            "price": product.get("price", 0),
                                            "quantity": 1,
                                        }},
                                        "$set": {"updated_at": datetime.utcnow()},
                                        "$setOnInsert": {
                                            "_id": str(uuid.uuid4()),
                                            "created_at": datetime.utcnow(),
                                        },
                                    },
                                    upsert=True,
                                )
                                cart = await db.carts.find_one({"customer_id": customer_id, "user_id": user["_id"], "status": "active"})
                                cart_items = cart.get("items", []) if cart else []
                                cart_total = sum(i.get("price", 0) * i.get("quantity", 1) for i in cart_items)
                                added_msg = (
                                    f"✅ *{product['name']}* added to cart!\n\n"
                                    f"🛒 *Cart: {len(cart_items)} item(s)* — {currency} {cart_total:,.0f}"
                                )
                                ws = get_whatsapp_service(db)
                                # Send confirmation message
                                await ws.send_message(
                                    user_id=user["_id"],
                                    to_number=from_number,
                                    message=added_msg,
                                    customer_name=customer_name,
                                    send_context="order_confirm",
                                )
                                # Send "What's next?" as list (compact single button → opens clean menu)
                                import httpx
                                _instance = await db.users.find_one({"_id": user["_id"]}, {"whatsapp": 1})
                                _inst_name = (_instance or {}).get("whatsapp", {}).get("instance_name", "")
                                if _inst_name:
                                    async with httpx.AsyncClient(timeout=30) as client:
                                        await asyncio.sleep(0.5)
                                        cart_text = (
                                            f"*What would you like to do?*\n\n"
                                            f"1️⃣  Checkout Now\n"
                                            f"2️⃣  Continue Shopping\n"
                                            f"3️⃣  Cancel Order\n\n"
                                            f"_Reply with 1, 2 or 3_"
                                        )
                                        await client.post(
                                            f"{ws.base_url}/message/sendText/{_inst_name}",
                                            json={"number": from_number.lstrip("+"), "text": cart_text},
                                            headers=ws._headers(),
                                        )
                                # Store cart action context so "1"/"2" replies are understood
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "cart", "updated_at": datetime.utcnow()}},
                                )
                                logging.info(f"Added to cart: product={button_product_id}, cart_size={len(cart_items)}")
                                return {"status": "ok", "handled_by": "add_to_cart"}

                        elif button_action == "checkout":
                            # Customer clicked "Checkout Now" button
                            _biz_id = user.get("business_id", user["_id"])
                            _cart = await db.carts.find_one({"customer_id": customer_id, "user_id": _biz_id, "status": "active"})
                            if _cart and _cart.get("items"):
                                _items = _cart["items"]
                                _total = sum(i.get("price", 0) * i.get("quantity", 1) for i in _items)
                                _now = datetime.utcnow()
                                _currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                
                                # ── Check for duplicate unpaid orders with same items ──────────────
                                _existing_orders = await db.orders.find({
                                    "user_id": _biz_id,
                                    "customer_id": customer_id,
                                    "payment_status": "Unpaid",
                                    "status": {"$in": ["pending", "confirmed"]}
                                }).sort("created_at", -1).to_list(10)
                                
                                _duplicate_order = None
                                for _eo in _existing_orders:
                                    _eo_items = _eo.get("items", [])
                                    # Check if items match (same products, same quantities)
                                    if len(_eo_items) == len(_items):
                                        _match = True
                                        for _ci in _items:
                                            _found = False
                                            for _ei in _eo_items:
                                                if (_ei.get("product_id") == _ci.get("product_id") and
                                                    _ei.get("quantity") == _ci.get("quantity")):
                                                    _found = True
                                                    break
                                            if not _found:
                                                _match = False
                                                break
                                        if _match:
                                            _duplicate_order = _eo
                                            break
                                
                                if _duplicate_order:
                                    # Found duplicate unpaid order — ask customer what to do
                                    _dup_order_num = _duplicate_order.get("order_number") or ("ORD-" + str(_duplicate_order.get("_id", ""))[:6].upper())
                                    _dup_items_text = ", ".join(i.get("product_name", "Item") for i in _duplicate_order.get("items", [])[:3])
                                    if len(_duplicate_order.get("items", [])) > 3:
                                        _dup_items_text += f" +{len(_duplicate_order.get('items', []))-3} more"
                                    
                                    ws = get_whatsapp_service(db)
                                    _dup_msg = (
                                        f"⚠️ You already have an unpaid order with the same items:\n\n"
                                        f"🔖 Order *#{_dup_order_num}*\n"
                                        f"📦 {_dup_items_text}\n"
                                        f"💰 {_currency} {_duplicate_order.get('total_amount', 0):,.0f}\n\n"
                                        f"*What would you like to do?*\n\n"
                                        f"1️⃣  Create New Order (double order)\n"
                                        f"2️⃣  Keep Existing Order\n"
                                        f"3️⃣  Cancel Existing & Create New\n\n"
                                        f"_Reply with 1, 2 or 3_"
                                    )
                                    await ws.send_message(
                                        user_id=user["_id"],
                                        to_number=from_number,
                                        message=_dup_msg,
                                        customer_name=customer_name,
                                        send_context="order_confirm"
                                    )
                                    # Store duplicate context so next reply resolves the choice
                                    await db.pending_catalogs.update_one(
                                        {"customer_id": customer_id, "user_id": user["_id"]},
                                        {"$set": {
                                            "action_context": "duplicate_order_choice",
                                            "duplicate_order_id": str(_duplicate_order["_id"]),
                                            "pending_cart_items": _items,
                                            "pending_cart_total": _total,
                                            "updated_at": _now
                                        }},
                                        upsert=True
                                    )
                                    logging.info(f"Duplicate order detected: existing={_dup_order_num}, asking customer")
                                    return {"status": "ok", "handled_by": "duplicate_order_prompt"}
                                
                                # No duplicate — proceed with normal checkout
                                _order_id = str(uuid.uuid4())
                                _order_number = "ORD-" + _order_id.replace("-", "").upper()[:6]
                                # Build item summary for order name
                                _item_names = ", ".join(i["product_name"] for i in _items[:3])
                                if len(_items) > 3:
                                    _item_names += f" +{len(_items)-3} more"
                                # Create ORDER as Unpaid — sale record only after payment confirmed
                                await db.orders.insert_one({
                                    "_id": _order_id,
                                    "order_number": _order_number,
                                    "user_id": _biz_id,
                                    "customer_id": customer_id,
                                    "customer_name": customer_name,
                                    "customer_phone": from_number,
                                    "product": _item_names,
                                    "items": _items,
                                    "quantity": len(_items),
                                    "total_amount": _total,
                                    "total": _total,
                                    "payment_status": "Unpaid",
                                    "delivery_status": "Processing",
                                    "status": "pending",
                                    "created_at": _now,
                                    "source": "cart_checkout"
                                })
                                await db.customers.update_one(
                                    {"_id": customer_id},
                                    {"$set": {"last_contacted": _now}}
                                )
                                await db.carts.update_one({"_id": _cart["_id"]}, {"$set": {"status": "completed"}})
                                # Extract payment details from user.payment_methods (top-level)
                                _user_co_doc = await db.users.find_one({"_id": _biz_id})
                                _raw_pm_co = (_user_co_doc or {}).get("payment_methods", [])
                                _pm_co_lines = []
                                for _pm in _raw_pm_co:
                                    if isinstance(_pm, dict):
                                        _line = _pm.get("name", "")
                                        _has_details_co = False
                                        if _pm.get("fields"):
                                            _fp = [f"{f['label']}: {f['value']}" for f in _pm["fields"] if f.get("value") and str(f["value"]).strip()]
                                            if _fp:
                                                _line += " — " + ", ".join(_fp)
                                                _has_details_co = True
                                        elif _pm.get("details") and str(_pm["details"]).strip():
                                            _line += f": {_pm['details']}"
                                            _has_details_co = True
                                        if _line.strip() and _has_details_co:
                                            _pm_co_lines.append(f"  • {_line}")
                                    else:
                                        if str(_pm).strip():
                                            _pm_co_lines.append(f"  • {_pm}")
                                _payment_text_co = "\n".join(_pm_co_lines)
                                # Build order summary + payment request
                                _co_lines = [f"✅ *Order Received!*\n", f"🔖 Order No: *#{_order_number}*\n"]
                                for _it in _items:
                                    _co_lines.append(f"• {_it['product_name']} × {_it.get('quantity',1)} — {_currency} {_it.get('price',0):,.0f}")
                                _co_lines.append(f"\n💰 *Total: {_currency} {_total:,.0f}*")
                                _co_lines.append(f"Status: 🔴 *Unpaid*\n")
                                _co_lines.append("To complete your order, please make payment using the details below.\n")
                                if _payment_text_co:
                                    _co_lines.append(f"*💳 Payment Details:*\n{_payment_text_co}\n")
                                else:
                                    _co_lines.append("We will send you our payment details shortly.\n")
                                _co_lines.append(
                                    f"📸 Once you have paid, *send us a screenshot* of your payment confirmation.\n\n"
                                    f"Also send your *delivery details:*\n"
                                    f"• Full name\n"
                                    f"• Delivery address\n"
                                    f"• Phone number\n\n"
                                    f"Your order *#{_order_number}* will be processed once payment is confirmed. 🙏"
                                )
                                ws = get_whatsapp_service(db)
                                await ws.send_message(
                                    user_id=_biz_id, to_number=from_number,
                                    message="\n".join(_co_lines),
                                    customer_name=customer_name, send_context="order_confirm"
                                )
                                # Set state to delivery_pending so payment screenshot is captured
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": "delivery_pending", "order_id": _order_id, "updated_at": _now}},
                                    upsert=True
                                )
                                logging.info(f"Cart checkout initiated: order_id={_order_id}, items={len(_items)}, total={_total}")
                                # Notify business owner via push notification
                                _owner2 = await db.users.find_one({"_id": _biz_id}, {"expo_push_token": 1})
                                _push_token2 = (_owner2 or {}).get("expo_push_token", "")
                                if _push_token2:
                                    try:
                                        from notification_service import get_notification_service
                                        _ns2 = get_notification_service()
                                        await _ns2.send_notification(
                                            push_token=_push_token2,
                                            title="🛒 New Order Received!",
                                            body=f"{customer_name} checked out {len(_items)} item(s) — {_currency} {_total:,.0f}",
                                            data={"type": "new_order", "order_id": _order_id, "customer_id": customer_id}
                                        )
                                    except Exception as _ne2:
                                        logging.warning(f"Checkout push notification failed: {_ne2}")
                                return {"status": "ok", "handled_by": "checkout"}

                        elif button_action == "cancel_cart":
                            # Customer chose "Cancel Order" from cart menu
                            _biz_id_cancel = user.get("business_id", user["_id"])
                            _cart_cancel = await db.carts.find_one({"customer_id": customer_id, "user_id": _biz_id_cancel, "status": "active"})
                            if _cart_cancel:
                                await db.carts.update_one({"_id": _cart_cancel["_id"]}, {"$set": {"status": "cancelled"}})
                                ws = get_whatsapp_service(db)
                                await ws.send_message(
                                    user_id=user["_id"],
                                    to_number=from_number,
                                    message="🗑️ Your cart has been cleared.\n\nFeel free to browse our catalog anytime! 😊",
                                    customer_name=customer_name,
                                    send_context="order_confirm"
                                )
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {"action_context": None, "updated_at": datetime.utcnow()}}
                                )
                                logging.info(f"Cart cancelled by customer: customer_id={customer_id}")
                                return {"status": "ok", "handled_by": "cancel_cart"}

                        elif button_action == "continue" or button_action == "back":
                            # Customer chose "Continue Shopping" or "Back to Catalog" — re-send product catalog with pagination
                            _biz_id_cont = user.get("business_id", user["_id"])
                            _all_products = await db.products.find(
                                {"user_id": _biz_id_cont, "in_stock": True}
                            ).sort("name", 1).to_list(100)
                            ws = get_whatsapp_service(db)
                            if _all_products:
                                _currency_cont = user.get("settings", {}).get("currency", "KES")
                                PAGE_SIZE = 8
                                _first_page = _all_products[:PAGE_SIZE]
                                _has_more = len(_all_products) > PAGE_SIZE
                                for p in _first_page:
                                    if "currency" not in p:
                                        p["currency"] = _currency_cont
                                await ws.send_product_list(
                                    user_id=user["_id"],
                                    to_number=from_number,
                                    title="Our Products",
                                    products=_first_page,
                                    has_more=_has_more
                                )
                                # Set catalog_select so next numbered reply picks a product
                                await db.pending_catalogs.update_one(
                                    {"customer_id": customer_id, "user_id": user["_id"]},
                                    {"$set": {
                                        "products": [{"id": p["_id"], "name": p["name"],
                                                      "price": p.get("price", 0), "index": i}
                                                     for i, p in enumerate(_first_page, 1)],
                                        "all_product_ids": [p["_id"] for p in _all_products],
                                        "page_offset": 0,
                                        "has_more": _has_more,
                                        "action_context": "catalog_select",
                                        "updated_at": datetime.utcnow()
                                    }},
                                    upsert=True
                                )
                            else:
                                await ws.send_message(
                                    user_id=user["_id"],
                                    to_number=from_number,
                                    message="😔 No other products in stock right now. Reply *CHECKOUT* whenever you're ready to place your order!",
                                    customer_name=customer_name,
                                    send_context="auto_reply"
                                )
                            logging.info("Continue shopping: re-sent product catalog")
                            return {"status": "ok", "handled_by": "continue_shopping"}

                        elif button_action == "similar":
                            # Customer wants to see similar/related products
                            _biz_id_sim = user.get("business_id", user["_id"])
                            _sim_product = await db.products.find_one({"_id": button_product_id, "user_id": _biz_id_sim})
                            _sim_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                            if _sim_product:
                                _sim_category = _sim_product.get("category", "")
                                _sim_name = _sim_product["name"]
                                # Find products in same category, excluding the current one
                                _sim_query = {"user_id": _biz_id_sim, "_id": {"$ne": button_product_id}}
                                if _sim_category:
                                    _sim_query["category"] = _sim_category
                                _sim_matches = await db.products.find(_sim_query).to_list(5)
                                # If same-category has < 3 results, pad with other products
                                if len(_sim_matches) < 3:
                                    _other_query = {"user_id": _biz_id_sim, "_id": {"$nin": [button_product_id] + [p["_id"] for p in _sim_matches]}}
                                    _others = await db.products.find(_other_query).to_list(5 - len(_sim_matches))
                                    _sim_matches += _others
                                ws = get_whatsapp_service(db)
                                if _sim_matches:
                                    _sim_lines = [f"Here are some products you might also like:\n"]
                                    for _si, _sp in enumerate(_sim_matches[:5], 1):
                                        _sp_price = f"{_sim_currency} {_sp.get('price',0):,.0f}" if _sp.get('price') else "POA"
                                        _sp_stock = "✅" if _sp.get('in_stock', True) else "❌"
                                        _sim_lines.append(f"{_si}️⃣  *{_sp['name']}* — {_sp_price} {_sp_stock}")
                                    _sim_lines.append("\n_Reply with a number to select_")
                                    await ws.send_message(
                                        user_id=_biz_id_sim, to_number=from_number,
                                        message="\n".join(_sim_lines),
                                        customer_name=customer_name, send_context="similar_products"
                                    )
                                    # Save to pending_catalogs so numbered replies work
                                    await db.pending_catalogs.update_one(
                                        {"customer_id": customer_id, "user_id": user["_id"]},
                                        {"$set": {
                                            "products": [{"id": str(p["_id"]), "name": p["name"], "price": p.get("price",0), "index": idx}
                                                         for idx, p in enumerate(_sim_matches[:5], 1)],
                                            "action_context": "catalog_select",
                                            "updated_at": datetime.utcnow()
                                        }}
                                    )
                                else:
                                    await ws.send_message(
                                        user_id=_biz_id_sim, to_number=from_number,
                                        message=f"Sorry, we don't have other products similar to *{_sim_name}* right now. Feel free to browse our full catalog by typing *catalog*! 😊",
                                        customer_name=customer_name, send_context="similar_products"
                                    )
                            logging.info(f"Similar products shown for product {button_product_id}")
                            return {"status": "ok", "handled_by": "similar_products"}

                        elif button_action in ("book", "subscribe", "quote", "test_drive", "info", "custom"):
                            # Custom action types — craft intent message and let AI handle naturally
                            _biz_id_ca = user.get("business_id", user["_id"])
                            _ca_product = await db.products.find_one({"_id": button_product_id, "user_id": _biz_id_ca})
                            _pname = _ca_product["name"] if _ca_product else "this product"
                            _intent_map = {
                                "book":       f"I want to book an appointment for {_pname}",
                                "subscribe":  f"I want to subscribe to {_pname}",
                                "quote":      f"I want to get a quote for {_pname}",
                                "test_drive": f"I want to schedule a test drive for {_pname}",
                                "info":       f"Tell me more about {_pname}",
                                "custom":     f"I'm interested in {_pname}",
                            }
                            # Check if user has a custom ai_prompt for this action
                            _ca_user_doc = await db.users.find_one({"_id": user["_id"]}, {"settings.product_actions": 1})
                            _ca_actions = (_ca_user_doc or {}).get("settings", {}).get("product_actions", [])
                            _ca_action_def = next((a for a in _ca_actions if a.get("action_type") == button_action), None)
                            if _ca_action_def and _ca_action_def.get("ai_prompt"):
                                body = _ca_action_def["ai_prompt"].replace("{product}", _pname).replace("{name}", customer_name)
                            else:
                                body = _intent_map.get(button_action, f"I'm interested in {_pname}")
                            await db.messages.update_one({"_id": message_id}, {"$set": {"content": body}})
                            logging.info(f"Custom action '{button_action}' for {_pname}: body={body!r}, passing to AI")
                    
                    except Exception as btn_err:
                        logging.error(f"Button handler error: {btn_err}")
                        # Fall through to normal AI handling on error

                # ============================================================
                # CART KEYWORD HANDLER — "checkout" / "cart" text commands
                # ============================================================
                if not button_action and not from_me and body:
                    _ck = body.strip().lower()
                    _is_checkout = _ck in ("checkout", "check out", "✅ checkout")
                    # Expanded cart detection for natural language variations
                    _is_view_cart = (
                        _ck in ("cart", "view cart", "my cart", "show cart", "see cart")
                        or "my cart" in _ck
                        or "show" in _ck and "cart" in _ck
                        or "back to" in _ck and "cart" in _ck
                        or "go to" in _ck and "cart" in _ck
                        or "what" in _ck and "cart" in _ck
                    )
                    if _is_checkout or _is_view_cart:
                        _biz_id_cart = user.get("business_id", user["_id"])
                        _cart = await db.carts.find_one(
                            {"customer_id": customer_id, "user_id": _biz_id_cart, "status": "active"}
                        )
                        ws = get_whatsapp_service(db)
                        _currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                        if not _cart or not _cart.get("items"):
                            await ws.send_message(
                                user_id=user["_id"],
                                to_number=from_number,
                                message="🛒 Your cart is empty. Browse our products and tap *Add to Cart* to get started!",
                                customer_name=customer_name,
                                send_context="auto_reply",
                            )
                            return {"status": "ok", "handled_by": "cart_empty"}
                        _items = _cart["items"]
                        _total = sum(i.get("price", 0) * i.get("quantity", 1) for i in _items)
                        if _is_view_cart:
                            _lines = [f"🛒 *Your Cart ({len(_items)} item(s))*\n"]
                            for _idx, _it in enumerate(_items, 1):
                                _lines.append(f"{_idx}. {_it['product_name']} — {_currency} {_it.get('price', 0):,.0f}")
                            _lines.append(f"\n💰 *Total: {_currency} {_total:,.0f}*\n")
                            _lines.append("1️⃣  ✅ *Checkout Now*")
                            _lines.append("2️⃣  🛍️ *Continue Shopping*")
                            _lines.append("\n_Reply with a number_")
                            await ws.send_message(
                                user_id=user["_id"],
                                to_number=from_number,
                                message="\n".join(_lines),
                                customer_name=customer_name,
                                send_context="auto_reply",
                            )
                            # Set context so "1"/"2" replies are understood
                            await db.pending_catalogs.update_one(
                                {"customer_id": customer_id, "user_id": user["_id"]},
                                {"$set": {"action_context": "cart", "updated_at": datetime.utcnow()}},
                                upsert=True
                            )
                            return {"status": "ok", "handled_by": "view_cart"}
                        if _is_checkout:
                            _biz_id_ck = user.get("business_id", user["_id"])
                            _order_id = str(uuid.uuid4())
                            _now_ck = datetime.utcnow()
                            _item_names_ck = ", ".join(_it["product_name"] for _it in _items[:3])
                            if len(_items) > 3:
                                _item_names_ck += f" +{len(_items)-3} more"
                            await db.orders.insert_one({
                                "_id": _order_id,
                                "user_id": _biz_id_ck,
                                "customer_id": customer_id,
                                "customer_name": customer_name,
                                "customer_phone": from_number,
                                "product": _item_names_ck,
                                "items": [
                                    {
                                        "product_id": _it["product_id"],
                                        "product_name": _it["product_name"],
                                        "quantity": _it.get("quantity", 1),
                                        "price": _it.get("price", 0),
                                    }
                                    for _it in _items
                                ],
                                "quantity": len(_items),
                                "total": _total,
                                "total_amount": _total,
                                "status": "pending",
                                "created_at": _now_ck,
                                "source": "whatsapp_cart",
                            })
                            await db.sales.insert_one({
                                "_id": str(uuid.uuid4()),
                                "user_id": _biz_id_ck,
                                "customer_id": customer_id,
                                "customer_name": customer_name,
                                "product": _item_names_ck,
                                "amount": _total,
                                "quantity": len(_items),
                                "status": "completed",
                                "created_at": _now_ck,
                                "source": "whatsapp_cart",
                            })
                            await db.customers.update_one(
                                {"_id": customer_id},
                                {"$inc": {"total_spent": _total, "purchase_count": 1},
                                 "$set": {"last_contacted": _now_ck}}
                            )
                            await db.carts.update_one(
                                {"_id": _cart["_id"]},
                                {"$set": {"status": "checked_out", "order_id": _order_id, "checked_out_at": _now_ck}},
                            )
                            _conf_lines = ["✅ *Order Confirmed!*\n"]
                            for _it in _items:
                                _conf_lines.append(f"• {_it['product_name']} x{_it.get('quantity', 1)} — {_currency} {_it.get('price', 0):,.0f}")
                            _conf_lines.append(f"\n💰 *Total: {_currency} {_total:,.0f}*")
                            _conf_lines.append("\nWe'll contact you shortly to confirm delivery details. Thank you! 🙏")
                            await ws.send_message(
                                user_id=_biz_id_ck,
                                to_number=from_number,
                                message="\n".join(_conf_lines),
                                customer_name=customer_name,
                                send_context="order_confirm",
                            )
                            # Push notification to business owner
                            try:
                                await send_push_notification(
                                    user_id=_biz_id_ck,
                                    title="🛒 New Order Received!",
                                    body=f"{customer_name} checked out {len(_items)} item(s) — {_currency} {_total:,.0f}",
                                    data={"type": "new_order", "order_id": _order_id, "customer_id": customer_id}
                                )
                            except Exception as _pne:
                                logging.warning(f"Checkout push notification failed: {_pne}")
                            logging.info(f"Multi-item order {_order_id} created from cart ({len(_items)} items, total={_total})")
                            return {"status": "ok", "handled_by": "cart_checkout"}

                # ============================================================
                # AUTO-REPLY GATE — check before agent/catalog/keyword handlers
                # Rules:
                #   1. Global OFF + customer individual ON  → SEND (individual overrides)
                #   2. Global ON  + customer individual OFF → SKIP (individual overrides)
                #   3. Global ON  + customer individual unset → apply audience filter
                #   4. Global OFF + customer individual unset → SKIP
                # ============================================================
                _user_settings = user.get('settings', {})
                _global_auto_reply = _user_settings.get('auto_reply_enabled', False)
                # customer.auto_reply: True=force ON, False=force OFF, None/missing=respect global
                _customer_auto_reply = customer.get('auto_reply') if customer else None
                logging.info(f"[AutoReply-Debug] customer={customer_name}, db_auto_reply={repr(customer.get('auto_reply') if customer else 'NO_CUSTOMER')}, type={type(customer.get('auto_reply') if customer else None).__name__}")

                if _customer_auto_reply is True:
                    _should_auto_reply = True
                elif _customer_auto_reply is False:
                    _should_auto_reply = False
                elif _global_auto_reply:
                    _audience = _user_settings.get('auto_reply_audience', 'everyone')
                    if _audience == 'customers_only':
                        _should_auto_reply = bool(customer and customer.get('is_customer', False))
                    elif _audience == 'new_contacts_only':
                        _should_auto_reply = bool(not customer or not customer.get('last_contacted'))
                    else:
                        _should_auto_reply = True
                else:
                    _should_auto_reply = False

                logging.info(f"Auto-reply gate: customer_override={_customer_auto_reply}, global={_global_auto_reply}, audience={_user_settings.get('auto_reply_audience','everyone')}, result={_should_auto_reply}")

                if not _should_auto_reply:
                    logging.info(f"Auto-reply BLOCKED for {from_number} (customer_override={_customer_auto_reply}, global={_global_auto_reply})")
                    return {"status": "ok", "message": "auto-reply disabled for this contact"}

                # needs_human gate: if the customer was escalated to a human, apply smart logic:
                # 1. Auto-expire after 15 minutes (in case owner never manually responds)
                # 2. If message is on a clearly different topic, clear escalation and reply normally
                # 3. If still escalated, send a brief acknowledgement (don't go completely silent)
                if customer and customer.get("needs_human"):
                    _needs_human_at = customer.get("needs_human_at")
                    _escalation_expired = False
                    if _needs_human_at:
                        from datetime import timezone as _tz
                        _now_utc = datetime.now(_tz.utc)
                        if hasattr(_needs_human_at, "tzinfo") and _needs_human_at.tzinfo is None:
                            _needs_human_at = _needs_human_at.replace(tzinfo=_tz.utc)
                        _mins_since = (_now_utc - _needs_human_at).total_seconds() / 60
                        if _mins_since >= 15:
                            _escalation_expired = True
                            logging.info(f"[Escalation] Auto-expiring needs_human for {customer_name} — {_mins_since:.0f} min elapsed")
                            await db.customers.update_one(
                                {"_id": customer_id},
                                {"$unset": {"needs_human": "", "needs_human_reason": "", "needs_human_at": ""}}
                            )

                    if not _escalation_expired:
                        # Still within 15-min window — acknowledge politely, don't go silent
                        logging.info(
                            f"Auto-reply SOFT-BLOCK for {customer_name} ({from_number}): "
                            f"needs_human=True reason={customer.get('needs_human_reason','')[:80]}"
                        )
                        try:
                            import random as _rnd
                            _ack_msgs = [
                                "Our team has been notified and will get back to you shortly.",
                                "I've flagged this for our team — they'll reach out to you soon.",
                                "A team member has been notified and will follow up with you shortly.",
                            ]
                            _ws_ack = get_whatsapp_service(db)
                            await _ws_ack.send_message(
                                user_id=user["_id"],
                                to_number=from_number,
                                message=_rnd.choice(_ack_msgs),
                                customer_name=customer_name,
                                send_context="auto_reply"
                            )
                        except Exception as _ack_err:
                            logging.error(f"[Escalation] Ack message failed: {_ack_err}")
                        return {"status": "ok", "message": "escalated — ack sent to customer"}

                # ============================================================
                # AGENT-BASED PIPELINE
                # ============================================================

                # Check if this is a personal contact
                is_personal = customer.get("is_personal", False) if customer else False

                # Fetch recent message history (last 20) for full conversation context
                # EXCLUDE the current message (already stored above) so the AI
                # doesn't see the same message twice (once in history, once as input)
                history = []
                if customer_id:
                    recent_msgs = await db.messages.find({
                        "user_id": user["_id"],
                        "customer_id": customer_id,
                        "_id": {"$ne": message_id},  # exclude current msg
                    }).sort("created_at", -1).limit(20).to_list(20)
                    history = [
                        {
                            "direction": m["direction"],
                            "content": m["content"],
                            "created_at": m.get("created_at"),  # timestamp for gap detection
                        }
                        for m in reversed(recent_msgs)
                    ]

                # Build business knowledge string for agents
                _bk_data = user.get("business_knowledge", {})
                _bk_parts = []
                if _bk_data:
                    if _bk_data.get("business_description"):
                        _bk_parts.append(f"About: {_bk_data['business_description']}")
                    if _bk_data.get("products_services"):
                        _bk_parts.append(f"Products/Services: {_bk_data['products_services']}")
                    if _bk_data.get("pricing_info"):
                        _bk_parts.append(f"Pricing/Payment notes: {_bk_data['pricing_info']}")
                    if _bk_data.get("business_hours"):
                        _bk_parts.append(f"Hours: {_bk_data['business_hours']}")
                    if _bk_data.get("delivery_info"):
                        _bk_parts.append(f"Delivery: {_bk_data['delivery_info']}")
                    if _bk_data.get("special_offers"):
                        _bk_parts.append(f"Offers: {_bk_data['special_offers']}")
                    if _bk_data.get("faqs"):
                        _bk_parts.append(f"FAQs: {_bk_data['faqs']}")
                # Inject structured payment methods from user doc
                _raw_pm = user.get("payment_methods", [])
                if _raw_pm:
                    _pm_lines = []
                    for _pm in _raw_pm:
                        if isinstance(_pm, dict):
                            _line = _pm.get("name", "")
                            # New multi-field format: fields=[{label, value}, ...]
                            if _pm.get("fields"):
                                field_parts = [
                                    f"{f['label']}: {f['value']}"
                                    for f in _pm["fields"]
                                    if f.get("value") and str(f["value"]).strip()
                                ]
                                if field_parts:
                                    _line += " — " + ", ".join(field_parts)
                            elif _pm.get("details"):
                                _line += f": {_pm['details']}"
                        else:
                            _line = str(_pm)
                        if _line.strip():
                            _pm_lines.append(f"  - {_line}")
                    if _pm_lines:
                        _bk_parts.append("Payment methods accepted:\n" + "\n".join(_pm_lines))
                # Inject actual product catalog from DB so all agents see real products/services
                _biz_id_for_ctx = user.get("business_id", user["_id"])
                _ctx_currency = user.get("currency") or _user_settings.get("currency", "USD")
                try:
                    _ctx_products = await db.products.find({"user_id": _biz_id_for_ctx}).to_list(50)
                    if _ctx_products:
                        _cat_lines = ["\nPRODUCTS/SERVICES CATALOG (use exact names and prices — do NOT invent):"]
                        for _cp in _ctx_products:
                            _cp_stock = "" if _cp.get("in_stock", True) else " [OUT OF STOCK]"
                            _cp_price = f"{_ctx_currency} {_cp['price']:,.0f}" if _cp.get("price") is not None else "Price on request"
                            _cp_dur = f" · {_cp['duration']} min" if _cp.get("duration") else ""
                            _cp_desc = f" — {_cp['description'][:80]}" if _cp.get("description") else ""
                            _cat_lines.append(f"  • {_cp['name']}: {_cp_price}{_cp_dur}{_cp_desc}{_cp_stock}")
                        _cat_lines.append("IMPORTANT: Only mention products listed above. Never invent product names or prices.")
                        _bk_parts.append("\n".join(_cat_lines))
                    else:
                        _bk_parts.append("No products/services in catalog yet. Do NOT make up product names or prices.")
                except Exception as _ctx_cat_err:
                    logging.warning(f"[Webhook] Failed to fetch products for agent context: {_ctx_cat_err}")

                # Inject structured business hours from settings (not the text field)
                _struct_bh = _user_settings.get("business_hours", {})
                if _struct_bh:
                    _bh_lines = ["Business Hours:"]
                    _bh_day_names = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
                                     "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
                    for _bh_key, _bh_label in _bh_day_names.items():
                        _bh = _struct_bh.get(_bh_key, {})
                        if _bh.get("closed"):
                            _bh_lines.append(f"  {_bh_label}: CLOSED")
                        elif _bh.get("open") and _bh.get("close"):
                            _bh_lines.append(f"  {_bh_label}: {_bh['open']} – {_bh['close']}")
                    if len(_bh_lines) > 1:
                        _bk_parts.append("\n".join(_bh_lines))

                _business_knowledge = "\n".join(_bk_parts) if _bk_parts else ""

                currency = user.get("currency") or _user_settings.get("currency", "USD")
                # Build customer data dict for agents that need it
                _customer_data = {}
                if customer:
                    _customer_data = {
                        "_id": customer.get("_id"),
                        "name": customer.get("name", ""),
                        "phone": customer.get("phone_number", ""),
                        "tags": customer.get("tags", []),
                        "notes": customer.get("notes", ""),
                        "purchase_count": customer.get("purchase_count", 0),
                        "total_spent": customer.get("total_spent", 0),
                        "last_contacted": customer.get("last_contacted"),
                    }
                agent_context = {
                    "currency": currency,
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "customer_data": _customer_data,
                    "is_personal": is_personal,
                    "history": history,
                    "business_knowledge": _business_knowledge,
                    "business_name": user.get("business_name", ""),
                    "ai_model": _user_settings.get("ai_model", "standard"),
                    "payment_methods": _raw_pm,  # structured array for PaymentAgent
                    "business_type": _user_settings.get("business_type", ""),
                    # business_id is the authoritative ID for product/service queries
                    # (may differ from user["_id"] for sub-users)
                    "business_id": _biz_id_for_ctx,
                }

                # ESCAPE HATCH — detect when customer wants to break out of pending flows
                # (cart, catalog, product selection) to switch context (e.g., check orders, cancel, etc.)
                if not button_action and not from_me and body:
                    _escape_body = body.strip().lower()
                    _escape_keywords = {
                        "order", "my order", "orders", "my orders", "order status", "check order",
                        "cancel", "nevermind", "never mind", "forget it", "stop", "exit", "quit",
                        "back", "go back", "start over", "reset", "help", "menu", "main menu",
                        "booking", "book", "appointment", "my booking", "bookings",
                        "payment", "pay", "mpesa", "receipt", "invoice",
                    }
                    _should_escape = any(kw in _escape_body for kw in _escape_keywords)
                    # Also escape if message is a question (starts with what/which/where/when/how/why)
                    _is_question = any(_escape_body.startswith(q) for q in ["what", "which", "where", "when", "how", "why", "who"])
                    if _should_escape or _is_question:
                        # Check if there's a pending catalog/cart state
                        _pending_escape = await db.pending_catalogs.find_one({
                            "customer_id": customer_id, "user_id": user["_id"]
                        })
                        if _pending_escape and _pending_escape.get("action_context") in ("cart", "catalog_select", "product"):
                            # Clear the pending catalog state to allow context switch
                            await db.pending_catalogs.delete_one({
                                "customer_id": customer_id, "user_id": user["_id"]
                            })
                            logging.info(f"[Escape Hatch] Cleared pending_catalogs for customer {customer_id} - context switch: {_escape_body[:50]}")
                        # Also clear conversation_states pending_update_step / pending_order_action
                        # so the numbered reply handler stops intercepting future messages
                        _conv_escape = await db.conversation_states.find_one({
                            "customer_id": str(customer_id), "user_id": user["_id"]
                        })
                        if _conv_escape and (_conv_escape.get("pending_update_step") or _conv_escape.get("pending_order_action")):
                            await db.conversation_states.update_one(
                                {"customer_id": str(customer_id), "user_id": user["_id"]},
                                {"$set": {
                                    "pending_update_step": None,
                                    "pending_order_action": None,
                                    "pending_update_products": None,
                                    "pending_update_selected_product": None,
                                }}
                            )
                            logging.info(f"[Escape Hatch] Cleared pending_update_step for customer {customer_id} - context switch: {_escape_body[:50]}")

                # ── BOOKING FLOW GUARD ────────────────────────────────────────────────────
                # Intercept non-number messages when customer is in an active booking state.
                # Prevents AI from hallucinating time slots, dates, and fake confirmations.
                if not button_action and not from_me and body:
                    import re as _re_bkg
                    _bkg_body = body.strip()
                    _bkg_lower = _bkg_body.lower()
                    _bkg_is_number = bool(_re_bkg.match(r'^\d+$', _bkg_body))

                    if not _bkg_is_number:
                        # Guard 1: pending_booking_list + non-number → resend booking list
                        _bkg_conv = await db.conversation_states.find_one({
                            "customer_id": str(customer_id), "user_id": user["_id"]
                        })
                        if _bkg_conv and _bkg_conv.get("pending_booking_list"):
                            try:
                                _bkg_bks = []
                                for _bid in _bkg_conv["pending_booking_list"]:
                                    _bk_g = await db.bookings.find_one({"_id": _bid})
                                    if _bk_g:
                                        _bkg_bks.append(_bk_g)
                                if _bkg_bks:
                                    _bkg_lines = ["📅 *Your Upcoming Bookings*\n"]
                                    for _bi, _bb in enumerate(_bkg_bks, 1):
                                        _bst = "✅" if _bb.get("status") == "confirmed" else "⏳"
                                        _bdt = f"{_bb.get('date', '')} at {_bb.get('time', '')}"
                                        _bkg_lines.append(
                                            f"*{_bi}.* {_bst} *{_bb.get('service_name', 'Service')}*\n"
                                            f"   📆 {_bdt}\n"
                                            f"   Ref: *{_bb.get('booking_number', '')}*"
                                        )
                                    _bkg_lines.append("\n_Reply with a number to manage that booking (e.g. *1*)_")
                                    ws = get_whatsapp_service(db)
                                    await ws.send_message(
                                        user_id=user["_id"], to_number=from_number,
                                        message="\n".join(_bkg_lines),
                                        customer_name=customer_name, send_context="booking_flow"
                                    )
                                    return {"status": "ok", "handled_by": "booking_list_guard"}
                            except Exception as _bkg_e:
                                logging.warning(f"[BookingGuard] pending_booking_list guard: {_bkg_e}")

                        # Guard 2: booking_service_select + non-number → fuzzy service name match
                        _bkg_pending = await db.pending_catalogs.find_one({
                            "customer_id": customer_id, "user_id": user["_id"],
                            "action_context": "booking_service_select"
                        })
                        if _bkg_pending:
                            _bkg_svcs = _bkg_pending.get("products", [])
                            _bkg_currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                            _bkg_biz_type = (user.get("settings", {}).get("business_type") or "").lower().strip()
                            _bkg_is_rental = _bkg_biz_type == "rental"
                            _bkg_is_creator = _bkg_biz_type == "creator"
                            # Fuzzy match: body contained in service name or service name in body
                            _bkg_match = None
                            for _sv in _bkg_svcs:
                                _sv_nl = _sv.get("name", "").lower()
                                if _sv_nl in _bkg_lower or _bkg_lower in _sv_nl or any(w in _sv_nl for w in _bkg_lower.split() if len(w) > 3):
                                    _bkg_match = _sv
                                    break
                            if _bkg_match:
                                _bkg_svc_id = _bkg_match["id"]
                                _bkg_svc_name = _bkg_match["name"]
                                _bkg_price = _bkg_match.get("price", 0)
                                _bkg_price_str = f"{_bkg_currency} {_bkg_price:,.0f}" if _bkg_price else "Contact for price"
                                _bkg_full_svc = await db.products.find_one({"_id": _bkg_svc_id, "user_id": user.get("business_id", user["_id"])})
                                _bkg_duration = (_bkg_full_svc or {}).get("duration")
                                _bkg_addons = (_bkg_full_svc or {}).get("addons", []) or []
                                _bkg_svc_cat = "rental" if _bkg_is_rental else (_bkg_full_svc or {}).get("service_category", "appointment")
                                _bkg_price_unit = (_bkg_full_svc or {}).get("price_unit", "night")
                                _bkg_unit_lbl = {"night": "night", "day": "day", "week": "week", "month": "month"}.get(_bkg_price_unit, "night")
                                _bkg_base = {
                                    "booking_service_id": _bkg_svc_id,
                                    "booking_service_name": _bkg_svc_name,
                                    "booking_service_price": _bkg_price,
                                    "booking_service_duration": _bkg_duration,
                                    "booking_service_category": _bkg_svc_cat,
                                    "booking_price_unit": _bkg_price_unit,
                                    "booking_addons_available": _bkg_addons,
                                    "booking_selected_addons": [],
                                    "updated_at": datetime.utcnow(),
                                }
                                ws = get_whatsapp_service(db)
                                if _bkg_addons:
                                    _bkg_base["action_context"] = "booking_addon_select"
                                    _al = [f"✅ *{_bkg_svc_name}* selected ({_bkg_price_str})\n", "🔧 *Optional Add-ons:*\n"]
                                    for _ai2, _ad2 in enumerate(_bkg_addons[:4], 1):
                                        _adp = _ad2.get("price", 0)
                                        _al.append(f"{_ai2}️⃣  {_ad2.get('name','')} — {'+' + _bkg_currency + ' ' + f'{_adp:,.0f}' if _adp else 'Free'}")
                                    _al += ["0️⃣  No extras", "\n_Reply with numbers or *0* to skip_"]
                                    await db.pending_catalogs.update_one({"customer_id": customer_id, "user_id": user["_id"]}, {"$set": _bkg_base})
                                    await ws.send_message(user_id=user["_id"], to_number=from_number, message="\n".join(_al), customer_name=customer_name, send_context="booking_flow")
                                elif _bkg_svc_cat == "rental":
                                    _bkg_base["action_context"] = "booking_checkin_input"
                                    await db.pending_catalogs.update_one({"customer_id": customer_id, "user_id": user["_id"]}, {"$set": _bkg_base})
                                    await ws.send_message(user_id=user["_id"], to_number=from_number, message=f"Great choice! *{_bkg_svc_name}* ({_bkg_price_str}/{_bkg_unit_lbl}).\n\n📅 *Check-in date?*\n_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*_", customer_name=customer_name, send_context="booking_flow")
                                elif _bkg_is_creator:
                                    _bkg_base["action_context"] = "creator_timeline_input"
                                    await db.pending_catalogs.update_one({"customer_id": customer_id, "user_id": user["_id"]}, {"$set": _bkg_base})
                                    await ws.send_message(user_id=user["_id"], to_number=from_number, message=f"Great choice! *{_bkg_svc_name}* ({_bkg_price_str}).\n\n📅 *When do you need this delivered?*\n_Reply with a deadline, e.g. *in 3 days*, *next Friday*, *March 20*_", customer_name=customer_name, send_context="booking_flow")
                                else:
                                    _bkg_base["action_context"] = "booking_date_input"
                                    await db.pending_catalogs.update_one({"customer_id": customer_id, "user_id": user["_id"]}, {"$set": _bkg_base})
                                    await ws.send_message(user_id=user["_id"], to_number=from_number, message=f"Great choice! *{_bkg_svc_name}* ({_bkg_price_str}).\n\n📅 *What date would you like?*\n_Reply with a date, e.g. *tomorrow*, *Monday*, *15 March*, or *2026-03-15*_", customer_name=customer_name, send_context="booking_flow")
                                logging.info(f"[BookingGuard] Name match: '{_bkg_body}' → '{_bkg_svc_name}' for customer {customer_id}")
                                return {"status": "ok", "handled_by": "booking_service_name_match"}
                            else:
                                # No match — resend numbered service list
                                _bkg_sl = ["📋 *Our Services*\n"]
                                for _sv in _bkg_svcs:
                                    _sv_p = _sv.get("price", 0)
                                    _sv_d = _sv.get("duration")
                                    _sv_ps = f"{_bkg_currency} {_sv_p:,.0f}" if _sv_p else "Contact for price"
                                    _sv_ds = f" · {_sv_d} min" if _sv_d else ""
                                    _bkg_sl.append(f"{_sv.get('index','?')}️⃣  *{_sv.get('name','Service')}* — {_sv_ps}{_sv_ds}")
                                _bkg_sl.append("\n_Reply with the number to select (e.g. *1*, *2*)_")
                                ws = get_whatsapp_service(db)
                                await ws.send_message(user_id=user["_id"], to_number=from_number, message="\n".join(_bkg_sl), customer_name=customer_name, send_context="booking_flow")
                                logging.info(f"[BookingGuard] No service match for '{_bkg_body}', resent list for customer {customer_id}")
                                return {"status": "ok", "handled_by": "booking_service_no_match_guard"}

                # Skip agent pipeline if button_action already set by numbered response handler
                if not button_action:
                    logging.info(
                        f"[Webhook] ▶ agent pipeline: user_id={user['_id']} "
                        f"biz_id={_biz_id_for_ctx} btype={_user_settings.get('business_type','')} "
                        f"msg={repr(body[:80])}"
                    )
                    agent_result = await router.route_and_process(
                        user_id=user["_id"],
                        message=body,
                        context=agent_context
                    )
                    logging.info(
                        f"[Webhook] ◀ agent result: handled={agent_result.get('handled') if agent_result else None} "
                        f"escalated={agent_result.get('escalated') if agent_result else None} "
                        f"msgs={len(agent_result.get('messages',[])) if agent_result else 0}"
                    )
                else:
                    agent_result = None
                    logging.info(f"[Webhook] Skipping agent pipeline - button_action already set: {button_action}")

                # Router returned None = AI explicitly disabled (personal contact / silenced)
                # Do NOT fall through to raw AI generation in this case
                if not button_action and agent_result is None:
                    logging.info(f"[Webhook] Router returned None for {from_number} — silencing reply")
                    return {"status": "ok"}

                if agent_result and agent_result.get("handled"):
                    # If escalated — notify owner/employee, then stop (human will handle)
                    if agent_result.get("escalated"):
                        escalation_reason = agent_result.get('escalation_reason', '')
                        logging.info(
                            f"[Webhook] Escalated for {from_number}: {escalation_reason}"
                        )

                        async def _notify_escalation(owner_user, cust_name, cust_phone, msg_body, reason, cust_id):
                            try:
                                ws_notif = get_whatsapp_service(db)
                                owner_phone = owner_user.get("phone_number") or owner_user.get("whatsapp", {}).get("phone_number")

                                # Check if there's an assigned employee for this customer
                                notify_phone = None
                                notify_name = "Business Owner"
                                assignment = await db.conversation_assignments.find_one({
                                    "business_id": owner_user["_id"],
                                    "customer_id": cust_id
                                })
                                if assignment:
                                    member = await db.team_members.find_one({
                                        "business_id": owner_user["_id"],
                                        "user_id": assignment.get("assigned_to"),
                                        "status": "active"
                                    })
                                    if member and member.get("phone_number"):
                                        notify_phone = member["phone_number"]
                                        notify_name = member.get("name", "Team Member")

                                # Fall back to owner if no assigned employee
                                if not notify_phone:
                                    notify_phone = owner_phone

                                if notify_phone and notify_phone != cust_phone:
                                    preview = msg_body[:120] + ("..." if len(msg_body) > 120 else "")
                                    reason_line = f"📋 *Reason:* {reason}\n\n" if reason else ""
                                    notification_msg = (
                                        f"🔔 *Customer needs your help!*\n\n"
                                        f"👤 *{cust_name}* ({cust_phone})\n"
                                        f"💬 *Last message:* _{preview}_\n\n"
                                        f"{reason_line}"
                                        f"Please reply to them directly on WhatsApp."
                                    )
                                    await ws_notif.send_message(
                                        user_id=owner_user["_id"],
                                        to_number=notify_phone,
                                        message=notification_msg,
                                        send_context="auto_reply"
                                    )
                                    logging.info(f"[Escalation] Notified {notify_name} ({notify_phone}) about {cust_name}")

                                # Also send Expo push notification to owner's device
                                try:
                                    _push_body = reason if reason else msg_body[:100]
                                    await send_push_notification(
                                        user_id=owner_user["_id"],
                                        title=f"🔔 {cust_name} needs your help",
                                        body=_push_body,
                                        data={"type": "escalation", "customer_id": cust_id, "customer_name": cust_name}
                                    )
                                except Exception:
                                    pass
                            except Exception as notif_err:
                                logging.error(f"[Escalation] Notification failed: {notif_err}")

                        # Send agent-prepared message (e.g. cancel confirmation) OR a hold message
                        _escalation_messages = agent_result.get("messages", [])
                        try:
                            _ws_hold = get_whatsapp_service(db)
                            if _escalation_messages:
                                # Agent gave a specific reply (e.g. "order cancelled", "flagged for team")
                                for _em in _escalation_messages:
                                    if _em.get("text"):
                                        await _ws_hold.send_message(
                                            user_id=user["_id"],
                                            to_number=from_number,
                                            message=_em["text"],
                                            customer_name=customer_name,
                                            send_context="auto_reply"
                                        )
                            else:
                                import random as _random
                                _hold_messages = [
                                    "Hang on, let me check on that for you.",
                                    "One sec, let me look into that.",
                                    "Sure, give me a moment on that.",
                                    "Let me check and get back to you shortly.",
                                    "On it — give me a moment.",
                                ]
                                _hold_msg = _random.choice(_hold_messages)
                                await _ws_hold.send_message(
                                    user_id=user["_id"],
                                    to_number=from_number,
                                    message=_hold_msg,
                                    customer_name=customer_name,
                                    send_context="auto_reply"
                                )
                        except Exception as _hold_err:
                            logging.error(f"[Escalation] Hold message failed: {_hold_err}")

                        asyncio.create_task(
                            _notify_escalation(user, customer_name, from_number, body, escalation_reason, customer_id)
                        )
                        return {"status": "ok", "handled_by": "escalation"}

                    ws = get_whatsapp_service(db)

                    # If agent returned catalog data, store in pending_catalogs for numbered replies
                    _ctx_update = agent_result.get("context_update", {})
                    if _ctx_update.get("catalog_all_ids"):
                        _all_ids = _ctx_update["catalog_all_ids"]
                        _page_offset = _ctx_update.get("catalog_page_offset", 0)
                        _has_more = _ctx_update.get("catalog_has_more", False)
                        _first_page_ids = _all_ids[_page_offset:_page_offset + 8]
                        _biz_id_cat = user.get("business_id", user["_id"])
                        _page_products = []
                        for _pid in _first_page_ids:
                            _p = await db.products.find_one({"_id": _pid, "user_id": _biz_id_cat})
                            if _p:
                                _page_products.append(_p)
                        if _page_products:
                            await db.pending_catalogs.update_one(
                                {"customer_id": customer_id, "user_id": user["_id"]},
                                {"$set": {
                                    "products": [{"id": _p["_id"], "name": _p["name"], "price": _p.get("price", 0), "index": i}
                                                 for i, _p in enumerate(_page_products, 1)],
                                    "all_product_ids": _all_ids,
                                    "page_offset": _page_offset,
                                    "has_more": _has_more,
                                    "action_context": "catalog_select",
                                    "created_at": datetime.utcnow()
                                }},
                                upsert=True
                            )
                            logging.info(f"[Agent] Stored catalog in pending_catalogs: {len(_page_products)} products, has_more={_has_more}")

                    # Send all messages returned by agent
                    for msg in agent_result.get("messages", []):
                        _msg_text = msg.get("text", "")
                        _msg_media = msg.get("media_url")
                        # Skip if neither text nor media
                        if not _msg_text and not _msg_media:
                            continue
                        # Strip any [NEEDS_HUMAN] tag that leaked into message text
                        _msg_text = _msg_text.replace("[NEEDS_HUMAN]", "").strip()
                        await ws.send_message(
                            user_id=user["_id"],
                            to_number=from_number,
                            message=_msg_text,
                            customer_name=customer_name,
                            media_url=_msg_media,
                            send_context="auto_reply"
                        )

                    # Send push notification to owner if agent requested it (e.g. order cancellation)
                    _owner_notif = agent_result.get("owner_notification")
                    if _owner_notif:
                        try:
                            await send_push_notification(
                                user_id=user.get("business_id", user["_id"]),
                                title=_owner_notif.get("title", "Order Update"),
                                body=_owner_notif.get("body", ""),
                            )
                            logging.info(f"[Agent] Owner notified: {_owner_notif.get('title')}")
                        except Exception as _notif_err:
                            logging.error(f"[Agent] Owner notification failed: {_notif_err}")

                    import time as _t_stamp
                    _last_auto_reply_sent[f"{user['_id']}:{from_number}"] = _t_stamp.time()
                    return {"status": "ok", "handled_by": "agent"}

                # Agent pipeline ran but returned unhandled — stop here, do NOT fall through to legacy AI handler
                if agent_result is not None:
                    logging.info(f"[Webhook] Agent returned unhandled for {from_number} — stopping (no legacy fallback)")
                    return {"status": "ok", "handled_by": "agent_unhandled"}

                # Check if customer is ordering from a catalog
                body_lower = body.lower().strip()
                pending = await db.pending_catalogs.find_one({
                    "customer_id": customer_id,
                    "user_id": user["_id"]
                })
                if pending and pending.get("products"):
                    matched_product = None
                    is_single = pending.get("single_product", False)
                    
                    if is_single and body_lower in ("yes", "yeah", "yep", "ok", "sure", "order", "buy", "i want", "1"):
                        matched_product = pending["products"][0]
                    
                    if not matched_product:
                        try:
                            idx = int(body_lower)
                            for p in pending["products"]:
                                if p["index"] == idx:
                                    matched_product = p
                                    break
                        except ValueError:
                            pass
                    
                    if not matched_product:
                        for prefix in ("order", "buy", "i want", "i'll take"):
                            if body_lower.startswith(prefix):
                                query = body_lower[len(prefix):].strip().strip("*").strip()
                                try:
                                    idx = int(query)
                                    for p in pending["products"]:
                                        if p["index"] == idx:
                                            matched_product = p
                                            break
                                except ValueError:
                                    pass
                                if not matched_product and query:
                                    for p in pending["products"]:
                                        if query in p["name"].lower():
                                            matched_product = p
                                            break
                                if matched_product:
                                    break
                    
                    if matched_product:
                        _biz_id_cat = user.get("business_id", user["_id"])
                        currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                        _price_cat = matched_product.get("price", 0)
                        _now_cat = datetime.utcnow()
                        order_id = str(uuid.uuid4())
                        await db.orders.insert_one({
                            "_id": order_id,
                            "user_id": _biz_id_cat,
                            "customer_id": customer_id,
                            "customer_name": customer_name,
                            "customer_phone": from_number,
                            "product": matched_product["name"],
                            "product_id": matched_product.get("id"),
                            "items": [{"product_id": matched_product.get("id"), "product_name": matched_product["name"], "quantity": 1, "price": _price_cat}],
                            "quantity": 1,
                            "price": _price_cat,
                            "total_amount": _price_cat,
                            "total": _price_cat,
                            "status": "pending",
                            "created_at": _now_cat,
                            "source": "catalog_reply",
                        })
                        await db.sales.insert_one({
                            "_id": str(uuid.uuid4()),
                            "user_id": _biz_id_cat,
                            "customer_id": customer_id,
                            "customer_name": customer_name,
                            "product": matched_product["name"],
                            "amount": _price_cat,
                            "quantity": 1,
                            "status": "completed",
                            "created_at": _now_cat,
                            "source": "catalog_reply",
                        })
                        await db.customers.update_one(
                            {"_id": customer_id},
                            {"$inc": {"total_spent": _price_cat, "purchase_count": 1},
                             "$set": {"last_contacted": _now_cat}}
                        )

                        # Reduce stock if tracked
                        if matched_product.get("id"):
                            await db.products.update_one(
                                {"_id": matched_product["id"], "stock_quantity": {"$exists": True, "$ne": None, "$gte": 1}},
                                {"$inc": {"stock_quantity": -1}}
                            )
                        
                        try:
                            ws = get_whatsapp_service(db)
                            confirm_msg = (
                                f"✅ *Order Confirmed!*\n\n"
                                f"*{matched_product['name']}*\n"
                                f"Qty: 1\n"
                                f"💰 Total: {currency} {_price_cat:,.0f}\n\n"
                                f"Thank you! We'll process your order right away. 🚀"
                            )
                            await ws.send_message(
                                user_id=_biz_id_cat,
                                to_number=from_number,
                                message=confirm_msg,
                                customer_name=customer_name,
                                send_context="order_confirm",
                            )
                        except Exception as e:
                            logging.error(f"Failed to send order confirmation: {e}")
                        # Push notification to business owner
                        try:
                            await send_push_notification(
                                user_id=_biz_id_cat,
                                title="🛒 New Order Received!",
                                body=f"{customer_name} ordered {matched_product['name']} — {currency} {_price_cat:,.0f}",
                                data={"type": "new_order", "order_id": order_id, "customer_id": customer_id}
                            )
                        except Exception:
                            pass
                        
                        await db.pending_catalogs.delete_one({"_id": pending["_id"]})
                        return {"status": "ok"}
                
                user_settings = _user_settings
                
                if True:  # auto-reply already gated above
                    # Dedup check already done at top of handler

                    
                    print(f"DEBUG: Proceeding to AI generation... model_pref={user_settings.get('ai_model', 'standard')}", flush=True)
                    try:
                        recent_messages = await db.messages.find({
                            "customer_id": customer_id,
                            "user_id": user["_id"]
                        }).sort("created_at", -1).limit(20).to_list(20)
                        recent_messages.reverse()
                        
                        customer_data = customer if customer else await db.customers.find_one({"_id": customer_id})
                        c_name = customer_data.get("name", "Customer") if customer_data else "Customer"
                        
                        bk = user.get("business_knowledge", {})
                        business_knowledge = "\n".join([f"{k}: {v}" for k, v in bk.items() if v]) if bk else ""
                        
                        log_trace(f"Starting AI generation for {from_number}")
                        
                        _ai_biz_id = user.get("business_id", user["_id"])
                        user_products = await db.products.find({"user_id": _ai_biz_id}).to_list(50)
                        product_catalog_map = {}  # product_id -> image_url
                        product_name_map = {}     # lowercase product name -> {id, image_url, name}
                        if user_products:
                            currency = user_settings.get("currency", "USD")
                            catalog_lines = ["\nPRODUCT CATALOG (real products with actual prices):"]
                            for p in user_products:
                                stock = "IN STOCK" if p.get("in_stock", True) else "OUT OF STOCK"
                                desc = f' - {p["description"]}' if p.get("description") else ""
                                price_str = f"{currency} {p['price']:,.0f}" if p.get('price') is not None else "Price not set"
                                
                                # Get product image (first from images array, fallback to image_url)
                                product_id = str(p['_id'])
                                all_images = []
                                if p.get("image_url"):
                                    all_images.append(p["image_url"])
                                for img in p.get("images", []):
                                    if img and img not in all_images:
                                        all_images.append(img)
                                
                                image_url = all_images[0] if all_images else None
                                if image_url:
                                    product_catalog_map[product_id] = image_url
                                    image_marker = " [HAS IMAGE]"
                                else:
                                    image_marker = ""
                                
                                # Build name lookup for auto-matching
                                product_name_map[p['name'].lower()] = {
                                    "id": product_id,
                                    "image_url": image_url,
                                    "name": p['name'],
                                    "all_images": all_images,
                                }
                                # Also index individual words for partial matching (skip short words)
                                for word in p['name'].lower().split():
                                    if len(word) >= 4 and word not in ("with", "from", "that", "this", "have", "each", "pack", "size"):
                                        if word not in product_name_map:
                                            product_name_map[word] = {
                                                "id": product_id,
                                                "image_url": image_url,
                                                "name": p['name'],
                                                "all_images": all_images,
                                            }
                                
                                catalog_lines.append(f"  • {p['name']} (ID: {product_id}): {price_str} [{stock}] ({p.get('category', 'Other')}){desc}{image_marker}")
                            
                            catalog_lines.append("\nWhen customers ask about products, use this catalog for accurate answers. Do NOT make up prices.")
                            catalog_lines.append(
                                "IMPORTANT: If the customer asks to see products or lists them (e.g. 'send all dresses'), you MUST include [SEND_IMAGE:product_id] for EACH matching product. "
                                "NEVER list products in text only. "
                                "If multiple match, use [SEND_IMAGE:id] tags for the top 3-5 matches. "
                                "Example reply: 'Here are the dresses: [SEND_IMAGE:123] [SEND_IMAGE:456]'"
                            )
                            business_knowledge = (business_knowledge or "") + "\n".join(catalog_lines)
                        else:
                            # No products in catalog - tell AI to avoid hallucinating
                            no_products_msg = "\nIMPORTANT: You do not have access to any product information. DO NOT make up product names, prices, descriptions, or inventory. DO NOT pretend specific products exist. If customers ask about specific products or prices, respond naturally based on the conversation context without inventing details. You can discuss general topics, answer questions, and help customers, but never fabricate product information."
                            business_knowledge = (business_knowledge or "") + no_products_msg
                        
                        if not business_knowledge:
                            business_knowledge = ""
                        
                        # Append business hours context + build closed_days hard override list
                        business_hours = user_settings.get("business_hours", {})
                        closed_days_list = []
                        if business_hours:
                            hours_lines = ["\nBUSINESS HOURS:"]
                            for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
                                h = business_hours.get(day, {})
                                if h.get("closed"):
                                    hours_lines.append(f"- {day.capitalize()}: CLOSED (Do NOT offer bookings or availability for this day)")
                                    closed_days_list.append(day.capitalize())
                                elif h.get("open") and h.get("close"):
                                    hours_lines.append(f"- {day.capitalize()}: {h.get('open')} to {h.get('close')}")
                            business_knowledge += "\n".join(hours_lines)
                        
                        if not business_knowledge.strip():
                            business_knowledge = None
                        
                        from ai_service import get_drafter
                        ai_service = get_drafter()
                        print(f"DEBUG: AI drafter obtained, clients={list(ai_service.clients.keys())}", flush=True)
                        user_country_code = user_settings.get("country_code", "")
                        customer_phone = customer_data.get("phone", from_number) if customer_data else from_number
                        result = await ai_service.draft_followup_message(
                            customer_name=c_name,
                            customer_data=customer_data or {},
                            messages=[{"direction": m.get("direction", "incoming"), "content": m.get("content", "")} for m in recent_messages],
                            business_name=user.get("business_name", "Our Business"),
                            tone=user_settings.get("message_tone", "friendly"),
                            business_knowledge=business_knowledge,
                            custom_instructions=f"Their latest message: '{body}'. Reply naturally to what they actually said right now. Don't repeat yourself.",
                            user_id=user["_id"],
                            db=db,
                            customer_id=customer_id,
                            user_country=user_country_code,
                            customer_phone=customer_phone,
                            model_pref=user_settings.get("ai_model", "standard"),
                            closed_days=closed_days_list if closed_days_list else None
                        )
                        
                        reply_text = result.get("drafted_message", "")
                        
                        # If AI service failed (returns None), skip auto-reply
                        if reply_text is None:
                            logging.warning(f"AI service failed for {from_number} - skipping auto-reply. Reason: {result.get('ai_reason', 'Unknown')}")
                            print(f"WARNING: AI failed, no auto-reply sent to {from_number}", flush=True)
                            return {"status": "ok", "message": "AI service unavailable, auto-reply skipped"}
                        
                        print(f"DEBUG: AI reply received ({len(reply_text)} chars): {reply_text[:100]}", flush=True)
                        logging.info(f"AI raw reply for {from_number}: {reply_text[:300]}")
                        
                        # Check if AI flagged this as needing human attention
                        needs_human = False
                        if reply_text and "[NEEDS_HUMAN]" in reply_text:
                            needs_human = True
                            reply_text = reply_text.replace("[NEEDS_HUMAN]", "").strip()
                            logging.info(f"⚠️ NEEDS_HUMAN flagged for {from_number} — alerting business owner")
                            # Send push notification to business owner
                            try:
                                push_token = user.get("push_token")
                                if push_token:
                                    from notification_service import get_notification_service
                                    notif_service = get_notification_service()
                                    await notif_service.send_notification(
                                        push_token=push_token,
                                        title="🔔 Customer Needs Your Help",
                                        body=f"{c_name}: {body[:100]}",
                                        data={
                                            "type": "needs_human",
                                            "customer_id": customer_id,
                                            "customer_name": c_name,
                                            "message": body[:200],
                                        },
                                        sound="default",
                                    )
                            except Exception as notif_err:
                                logging.error(f"Failed to send NEEDS_HUMAN notification: {notif_err}")
                            # Flag customer as needing human attention
                            try:
                                await db.customers.update_one(
                                    {"_id": customer_id},
                                    {"$set": {"needs_human": True, "needs_human_reason": body[:200], "needs_human_at": datetime.utcnow()}}
                                )
                            except Exception:
                                pass
                        
                        if reply_text:
                            logging.info(f"RAW AI RESPONSE: {reply_text}")
                            import re
                            # Strip any [SEND_IMAGE:...] tags the AI might have included
                            image_pattern = r'\[SEND_IMAGE:([^\]]+)\]'
                            ai_tag_matches = re.findall(image_pattern, reply_text)
                            clean_reply_text = re.sub(image_pattern, '', reply_text).strip()
                            
                            ws = get_whatsapp_service(db)
                            
                            # Send the text message first
                            if clean_reply_text:
                                await ws.send_message(
                                    user_id=user["_id"],
                                    to_number=from_number,
                                    message=clean_reply_text,
                                    customer_name=c_name,
                                    send_context="auto_reply",
                                )
                            
                            # === PRODUCT IMAGE & BUTTON SENDING (only via explicit AI tags) ===
                            # Note: Auto-detect product matching is handled earlier in the 
                            # "DYNAMIC PRODUCT KEYWORD MATCHING" section. The AI reply
                            # only sends additional images if the AI explicitly tags them.
                            images_sent = set()
                            
                            # Honor any AI [SEND_IMAGE:id] tags
                            for pid in ai_tag_matches:
                                pid = pid.strip()
                                if pid in product_catalog_map and pid not in images_sent:
                                    try:
                                        # Get product details for button
                                        product_info = product_name_map.get(pid) # this map is keyed by name, not ID. Let's find by ID from user_products list we fetched earlier
                                        
                                        # Fallback search since map above is by name
                                        target_product = None
                                        for p in user_products:
                                            if str(p['_id']) == pid:
                                                target_product = p
                                                break
                                        
                                        if target_product:
                                            # Collect ALL images for this product
                                            all_imgs = []
                                            if target_product.get("image_url"):
                                                all_imgs.append(target_product["image_url"])
                                            for img in target_product.get("images", []):
                                                if img and img not in all_imgs:
                                                    all_imgs.append(img)
                                            all_imgs = [normalize_url(u) for u in all_imgs]
                                            
                                            currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
                                            price_display = f"{currency} {target_product.get('price', 0):,.0f}"
                                            product_name = target_product.get('name', 'Product')
                                            caption = f"{product_name}\n💰 {price_display}"
                                            if target_product.get('description'):
                                                caption += f"\n{target_product['description']}"
                                            
                                            logging.info(f"AI tag: sending {len(all_imgs)} images for product {pid}")
                                            
                                            # Send extra images first (no caption)
                                            for extra_img in all_imgs[1:]:
                                                await ws.send_message(
                                                    user_id=user["_id"],
                                                    to_number=from_number,
                                                    message="",
                                                    customer_name=c_name,
                                                    send_context="auto_reply",
                                                    media_url=extra_img
                                                )
                                            
                                            # Send main image LAST with caption (name, price)
                                            first_img = all_imgs[0] if all_imgs else None
                                            await ws.send_message(
                                                user_id=user["_id"],
                                                to_number=from_number,
                                                message=caption,
                                                customer_name=c_name,
                                                send_context="auto_reply",
                                                media_url=first_img
                                            )
                                            
                                            images_sent.add(pid)
                                            logging.info(f"Sent {len(all_imgs)} product image(s) for {pid} to {c_name}")
                                        else:
                                            # Fallback: product not in user_products list
                                            img_url = normalize_url(product_catalog_map[pid])
                                            await ws.send_message(
                                                user_id=user["_id"],
                                                to_number=from_number,
                                                message="",
                                                customer_name=c_name,
                                                send_context="auto_reply",
                                                media_url=img_url
                                            )
                                            images_sent.add(pid)
                                            logging.info(f"Sent product image (fallback) for {pid} to {c_name}")
                                            
                                    except Exception as img_err:
                                        logging.error(f"Failed to send product button/image {pid}: {img_err}")
                            
                            import time as _t_stamp2
                            _last_auto_reply_sent[f"{user['_id']}:{from_number}"] = _t_stamp2.time()
                            logging.info(f"Auto-replied to {c_name} ({from_number}), images_sent={len(images_sent)}")
                        
                    except Exception as e:
                        print(f"ERROR: Auto-reply failed: {e}", flush=True)
                        logging.error(f"Auto-reply failed for {from_number}: {e}")
                        import traceback
                        traceback.print_exc()
            
            return {"status": "ok"}
        
        return {"status": "ok", "event": event}
        
    except Exception as e:
        logging.error(f"Evolution webhook error: {e}")
        return {"status": "error", "message": str(e)}

# ============ SMART FOLLOW-UP ENDPOINTS ============

@api_router.get("/stats/followup-suggestions")
async def get_followup_suggestions(user = Depends(get_current_user)):
    """
    Get smart follow-up suggestions based on customer activity
    Only counts customers who don't already have pending follow-ups
    """
    now = datetime.utcnow()
    
    # Get all customers with pending follow-ups
    pending_followups = await db.followups.find({
        "user_id": user["_id"],
        "status": "pending"
    }).to_list(None)
    
    customer_ids_with_followups = {f["customer_id"] for f in pending_followups}
    
    # Customers not contacted in 14+ days (without pending follow-ups)
    # This is more realistic - 14 days is when attention is truly needed
    two_weeks_ago = now - timedelta(days=14)
    neglected_week = await db.customers.count_documents({
        "user_id": user["_id"],
        "_id": {"$nin": list(customer_ids_with_followups)},
        "$or": [
            {"last_contacted": {"$lt": two_weeks_ago}},
            {"last_contacted": None}
        ]
    })
    
    # Customers not contacted in 30+ days (without pending follow-ups)
    month_ago = now - timedelta(days=30)
    neglected_month = await db.customers.count_documents({
        "user_id": user["_id"],
        "_id": {"$nin": list(customer_ids_with_followups)},
        "last_contacted": {"$lt": month_ago}
    })
    
    # New customers (never followed up and no pending follow-ups)
    new_no_followup = await db.customers.count_documents({
        "user_id": user["_id"],
        "_id": {"$nin": list(customer_ids_with_followups)},
        "tags": "New",
        "last_contacted": None
    })
    
    # VIP customers not contacted in 7+ days (VIPs need more frequent attention)
    week_ago = now - timedelta(days=7)
    vip_neglected = await db.customers.count_documents({
        "user_id": user["_id"],
        "_id": {"$nin": list(customer_ids_with_followups)},
        "tags": "VIP",
        "$or": [
            {"last_contacted": {"$lt": week_ago}},
            {"last_contacted": None}
        ]
    })
    
    return {
        "neglected_week": neglected_week,
        "neglected_month": neglected_month,
        "new_no_followup": new_no_followup,
        "vip_neglected": vip_neglected,
        "total_needing_attention": neglected_week + new_no_followup + vip_neglected
    }

# ============ STATS ENDPOINTS ============

@api_router.get("/stats")
async def get_stats(user = Depends(get_current_user)):
    """Get dashboard stats"""
    customers_count = await db.customers.count_documents({"user_id": user["_id"], "is_customer": True})
    pending_followups = await db.followups.count_documents({"user_id": user["_id"], "status": "pending"})
    
    # Sales this month
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sales_this_month = await db.sales.find({
        "user_id": user["_id"],
        "created_at": {"$gte": start_of_month}
    }).to_list(1000)
    
    total_sales = sum(s["amount"] for s in sales_this_month)
    
    return {
        "customers_count": customers_count,
        "pending_followups": pending_followups,
        "sales_this_month": len(sales_this_month),
        "revenue_this_month": total_sales
    }

@api_router.get("/stats/wow-moments")
async def get_wow_moments(user = Depends(get_current_user)):
    """
    Get daily 'wow moment' insights that show intelligent features at work
    Returns personalized insights, predictions, and delightful statistics
    """
    try:
        wow_gen = get_wow_generator(db)
        insights = await wow_gen.get_daily_wow_insights(user["_id"])
        return insights
    except Exception as e:
        logging.error(f"Error generating wow moments: {e}")
        return {
            "greeting": "Welcome back!",
            "quick_wins": [],
            "revenue_opportunity": {"message": "Loading insights..."},
            "streak": {"message": "Keep up the great work!"},
            "ai_saved_time": {"message": "AI is working for you"},
            "success_prediction": {"message": "Good luck today!"},
            "best_time_to_contact": {"message": "Contact customers when they're active"}
        }

# ============ AI-POWERED ENDPOINTS ============

async def analyze_customer_with_ai(customer: dict, messages: list, user: dict) -> dict:
    """Use OpenAI to analyze customer conversation and generate insights"""
    try:
        analyzer = DailyCustomerAnalyzer(db)
        # Use existing method
        return await analyzer.analyze_single_customer(customer["_id"], user["_id"])
    except Exception as e:
        logging.error(f"AI analysis error: {e}")
        # Return fallback
        return {
            "summary": "AI Analysis Unavailable",
            "follow_up_reason": "Analysis failed",
            "suggested_message": "Hi! Checking in.",
            "interests": [],
            "sentiment": "neutral"
        }

async def generate_notes_from_messages(customer: dict, messages: list) -> str:
    """Use AI to generate notes from conversation history"""
    try:
        drafter = get_drafter()
        return await drafter.analyze_conversation_for_notes(messages)
    except Exception as e:
        logging.error(f"Notes generation error: {e}")
        return customer.get("notes", "") or "Could not generate notes"

@api_router.get("/customers/{customer_id}/ai-analysis")
async def get_customer_ai_analysis(customer_id: str, user = Depends(get_current_user)):
    """Get AI-powered analysis for a customer"""
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get customer's messages
    messages = await db.messages.find({"customer_id": customer_id, "user_id": business_id}).sort("created_at", 1).to_list(50)
    
    analysis = await analyze_customer_with_ai(customer, messages, user)
    
    return {
        "customer_id": customer_id,
        **analysis
    }

@api_router.post("/customers/{customer_id}/clear-needs-human")
async def clear_needs_human(customer_id: str, user = Depends(get_current_user)):
    """Clear the needs_human flag so AI resumes auto-replying for this customer"""
    business_id = user.get("business_id", user["_id"])
    result = await db.customers.update_one(
        {"_id": customer_id, "user_id": business_id},
        {"$set": {"needs_human": False, "needs_human_reason": "", "needs_human_cleared_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"status": "success", "message": "AI auto-reply resumed for this customer"}

@api_router.post("/customers/{customer_id}/generate-notes")
async def generate_customer_notes(customer_id: str, user = Depends(get_current_user)):
    """Generate AI notes from customer conversations"""
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    messages = await db.messages.find({"customer_id": customer_id, "user_id": business_id}).sort("created_at", 1).to_list(50)
    
    notes = await generate_notes_from_messages(customer, messages)
    
    # Update customer notes
    await db.customers.update_one(
        {"_id": customer_id},
        {"$set": {"notes": notes, "notes_generated_at": datetime.utcnow()}}
    )
    
    return {"customer_id": customer_id, "notes": notes}

@api_router.get("/ai/draft-message")
async def draft_message(customer_id: str, custom_instructions: Optional[str] = None, user = Depends(get_current_user)):
    """
    Draft a personalized message for a customer using AI with optional custom instructions
    """
    try:
        # Re-use the POST implementation logic by constructing a request object
        # or just calling the shared logic. To keep it simple, I'll redirect it.
        from fastapi.responses import RedirectResponse
        # But we want to return the same data. Let's just call a shared helper.
        return await draft_ai_message(DraftMessageRequest(
            customer_id=customer_id,
            custom_instructions=custom_instructions
        ), user)
    except Exception as e:
        import traceback
        logging.error(f"Error in draft_message: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# Duplicate function removed - using the first definition

# ============ MESSAGE STORAGE ENDPOINTS ============

@api_router.get("/customers/{customer_id}/messages")
async def get_customer_messages(customer_id: str, limit: int = 50, user = Depends(get_current_user)):
    """Get messages for a customer"""
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    messages = await db.messages.find({"customer_id": customer_id, "user_id": business_id}).sort("created_at", -1).to_list(limit)
    
    return serialize_doc([
        {
            "id": m["_id"],
            "customer_id": m["customer_id"],
            "direction": m["direction"],
            "content": m["content"],
            "message_type": m.get("message_type", "text"),
            "image_url": m.get("image_url"),
            "file_name": m.get("file_name"),
            "status": m.get("status"),
            "created_at": m.get("created_at", m.get("timestamp")),
            "evo_message_id": m.get("evo_message_id"),
            "remote_jid": m.get("remote_jid"),
        }
        for m in messages
    ])

@api_router.get("/admin/fix-all-images")
async def fix_all_broken_images():
    """
    ADMIN: Fix ALL broken WhatsApp images across all users.
    Call this once after deploying the image download fix.
    """
    total_fixed = 0
    total_failed = 0
    users_processed = []
    
    # Get all users with WhatsApp connected
    users = await db.users.find({"whatsapp.status": "connected"}).to_list(None)
    
    for user in users:
        try:
            business_id = user.get("business_id", user["_id"])
            instance_name = user.get("whatsapp", {}).get("instance_name")
            
            if not instance_name:
                continue
            
            # Find broken images for this user
            broken_images = await db.messages.find({
                "user_id": business_id,
                "message_type": "image",
                "image_url": {"$exists": True},
                "$or": [
                    {"image_url": {"$regex": "^/v/"}},
                    {"image_url": {"$regex": "directPath"}},
                ]
            }).to_list(None)
            
            user_fixed = 0
            user_failed = 0
            
            for msg in broken_images:
                try:
                    if not msg.get("evo_message_id") or not msg.get("remote_jid"):
                        user_failed += 1
                        continue
                    
                    # Build a minimal message object — old msgs won't have encrypted keys
                    # so this will only work if Evolution API still has the media cached
                    message_obj = {
                        "key": {
                            "id": msg["evo_message_id"],
                            "remoteJid": msg["remote_jid"],
                            "fromMe": msg.get("direction") == "outgoing"
                        }
                    }
                    
                    from whatsapp_service import download_whatsapp_media
                    new_url = await download_whatsapp_media(instance_name, message_obj, "image")
                    
                    if new_url:
                        await db.messages.update_one(
                            {"_id": msg["_id"]},
                            {"$set": {"image_url": new_url}}
                        )
                        user_fixed += 1
                    else:
                        user_failed += 1
                        
                except Exception as e:
                    user_failed += 1
                    logging.error(f"Error fixing image: {e}")
            
            total_fixed += user_fixed
            total_failed += user_failed
            
            if user_fixed > 0 or user_failed > 0:
                users_processed.append({
                    "user_id": business_id,
                    "phone": user.get("phone_number", "unknown"),
                    "fixed": user_fixed,
                    "failed": user_failed
                })
                
        except Exception as e:
            logging.error(f"Error processing user {user.get('_id')}: {e}")
    
    return {
        "status": "complete",
        "total_fixed": total_fixed,
        "total_failed": total_failed,
        "users_processed": len(users_processed),
        "details": users_processed
    }

@api_router.post("/messages/fix-images")
async def fix_broken_images(user = Depends(get_current_user)):
    """
    Migration endpoint: Fix existing messages with broken WhatsApp image URLs.
    Re-downloads images from Evolution API and updates database.
    """
    business_id = user.get("business_id", user["_id"])
    whatsapp_service = get_whatsapp_service(db)
    
    # Find all image messages with URLs that look like WhatsApp internal paths
    broken_images = await db.messages.find({
        "user_id": business_id,
        "message_type": "image",
        "image_url": {"$exists": True},
        "$or": [
            {"image_url": {"$regex": "^/v/"}},  # directPath format
            {"image_url": {"$regex": "directPath"}},
        ]
    }).to_list(None)
    
    if not broken_images:
        return {
            "status": "success",
            "message": "No broken images found",
            "fixed": 0,
            "failed": 0
        }
    
    fixed_count = 0
    failed_count = 0
    
    # Get user's WhatsApp instance
    wa = user.get("whatsapp", {})
    instance_name = wa.get("instance_name")
    
    if not instance_name:
        raise HTTPException(status_code=400, detail="WhatsApp not connected")
    
    for msg in broken_images:
        try:
            # We need the message key to download from Evolution API
            # Try to reconstruct it from stored metadata
            if not msg.get("evo_message_id") or not msg.get("remote_jid"):
                failed_count += 1
                continue
            
            # Build a minimal message object — old msgs won't have encrypted keys
            message_obj = {
                "key": {
                    "id": msg["evo_message_id"],
                    "remoteJid": msg["remote_jid"],
                    "fromMe": msg.get("direction") == "outgoing"
                }
            }
            
            # Download the image
            from whatsapp_service import download_whatsapp_media
            new_url = await download_whatsapp_media(instance_name, message_obj, "image")
            
            if new_url:
                # Update the message with the new URL
                await db.messages.update_one(
                    {"_id": msg["_id"]},
                    {"$set": {"image_url": new_url}}
                )
                fixed_count += 1
                logging.info(f"Fixed image for message {msg['_id']}")
            else:
                failed_count += 1
                logging.warning(f"Failed to download image for message {msg['_id']}")
                
        except Exception as e:
            failed_count += 1
            logging.error(f"Error fixing image for message {msg.get('_id')}: {e}")
    
    return {
        "status": "success",
        "message": f"Fixed {fixed_count} images, {failed_count} failed",
        "total_found": len(broken_images),
        "fixed": fixed_count,
        "failed": failed_count
    }

@api_router.delete("/messages/{message_id}")
async def delete_message(message_id: str, user = Depends(get_current_user)):
    """Delete a single message from the CRM (local only, does not unsend on WhatsApp)"""
    business_id = user.get("business_id", user["_id"])
    result = await db.messages.delete_one({"_id": message_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "success", "message": "Message deleted"}

@api_router.delete("/messages/{message_id}/for-everyone")
async def delete_message_for_everyone(message_id: str, user = Depends(get_current_user)):
    """Delete a message for everyone on WhatsApp (revoke) then remove from CRM.
    Only works for outgoing messages within WhatsApp's ~60 hour window."""
    business_id = user.get("business_id", user["_id"])
    msg = await db.messages.find_one({"_id": message_id, "user_id": business_id})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    evo_msg_id = msg.get("evo_message_id")
    remote_jid = msg.get("remote_jid")

    if not evo_msg_id or not remote_jid:
        raise HTTPException(status_code=400, detail="Cannot delete for everyone: message has no WhatsApp ID (may be too old or not sent via this CRM)")

    wa_user = await db.users.find_one({"_id": business_id})
    wa = wa_user.get("whatsapp", {}) if wa_user else {}
    instance_name = wa.get("instance_name")
    if not instance_name:
        raise HTTPException(status_code=400, detail="WhatsApp not connected")

    import os as _os, httpx as _httpx
    base_url = _os.environ.get("EVOLUTION_API_URL", "http://localhost:8080")
    api_key = _os.environ.get("EVOLUTION_API_KEY", "")

    try:
        async with _httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(
                method="DELETE",
                url=f"{base_url}/chat/deleteMessageForEveryone/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"id": evo_msg_id, "remoteJid": remote_jid, "fromMe": True},
            )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"WhatsApp delete failed: {resp.text}")
    except _httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach WhatsApp: {str(e)}")

    await db.messages.delete_one({"_id": message_id})
    return {"status": "success", "message": "Message deleted for everyone"}

@api_router.post("/customers/{customer_id}/messages")
async def add_customer_message(customer_id: str, message: MessageCreate, user = Depends(get_current_user)):
    """Manually add a message to customer history"""
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    message_id = str(uuid.uuid4())
    message_doc = {
        "_id": message_id,
        "customer_id": customer_id,
        "user_id": business_id,
        "direction": message.direction,
        "content": message.content,
        "message_type": message.message_type,
        "created_at": datetime.utcnow()
    }
    
    await db.messages.insert_one(message_doc)
    
    # Update customer's last message and contacted time
    update_data = {"last_contacted": datetime.utcnow()}
    update_data["last_message"] = message.content[:200]
    
    await db.customers.update_one({"_id": customer_id}, {"$set": update_data})
    
    return {"id": message_id, "status": "success"}

# ============ AI ENDPOINTS ============

@api_router.get("/business-knowledge")
async def get_business_knowledge(user = Depends(get_current_user)):
    """Get business knowledge for AI context"""
    knowledge = user.get('business_knowledge', {})
    # Normalize payment_methods — legacy may be plain strings
    raw_pm = user.get('payment_methods', [])
    payment_methods = [
        m if isinstance(m, dict) else {"name": m, "details": ""}
        for m in raw_pm
    ]
    return {
        "products_services": knowledge.get('products_services', ''),
        "pricing_info": knowledge.get('pricing_info', ''),
        "business_hours": knowledge.get('business_hours', ''),
        "delivery_info": knowledge.get('delivery_info', ''),
        "faqs": knowledge.get('faqs', ''),
        "special_offers": knowledge.get('special_offers', ''),
        "business_description": knowledge.get('business_description', ''),
        "business_type": knowledge.get('business_type', 'general'),
        "creator_niche": knowledge.get('creator_niche', ''),
        "creator_platforms": knowledge.get('creator_platforms', ''),
        "creator_audience_size": knowledge.get('creator_audience_size', ''),
        "creator_collab_types": knowledge.get('creator_collab_types', ''),
        "creator_rate_card": knowledge.get('creator_rate_card', ''),
        "creator_whats_included": knowledge.get('creator_whats_included', ''),
        "creator_turnaround": knowledge.get('creator_turnaround', ''),
        "creator_booking_process": knowledge.get('creator_booking_process', ''),
        "creator_min_budget": knowledge.get('creator_min_budget', ''),
        "creator_blacklisted_niches": knowledge.get('creator_blacklisted_niches', ''),
        "creator_fan_dm_response": knowledge.get('creator_fan_dm_response', ''),
        "creator_media_kit_link": knowledge.get('creator_media_kit_link', ''),
        "payment_methods": payment_methods,
    }

@api_router.put("/business-knowledge")
async def update_business_knowledge(knowledge: BusinessKnowledge, user = Depends(get_current_user)):
    """Update business knowledge for AI to use in conversations"""
    update_data = {}
    fields = [
        'products_services', 'pricing_info', 'business_hours', 'delivery_info',
        'faqs', 'special_offers', 'business_description', 'business_type',
        'creator_niche', 'creator_platforms', 'creator_audience_size',
        'creator_collab_types', 'creator_rate_card', 'creator_whats_included',
        'creator_turnaround', 'creator_booking_process', 'creator_min_budget',
        'creator_blacklisted_niches', 'creator_fan_dm_response', 'creator_media_kit_link',
    ]
    for field in fields:
        val = getattr(knowledge, field, None)
        if val is not None:
            update_data[f'business_knowledge.{field}'] = val
    if knowledge.payment_methods is not None:
        update_data['payment_methods'] = knowledge.payment_methods
    if update_data:
        await db.users.update_one({"_id": user["_id"]}, {"$set": update_data})
    return {"status": "success", "message": "Business knowledge updated"}

@api_router.post("/ai/draft-message")
async def draft_ai_message(request: DraftMessageRequest, user = Depends(get_current_user)):
    """Generate AI-drafted follow-up message for a customer"""
    logging.info(f"DEBUG: draft_ai_message called for customer_id={request.customer_id}")
    try:
        business_id = user.get("business_id", user["_id"])
        customer = await db.customers.find_one({"_id": request.customer_id, "user_id": business_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Get last 20 messages — sort DESC to get most recent, then reverse for chronological order
        raw_messages = await db.messages.find({
            "customer_id": request.customer_id,
            "user_id": business_id
        }).sort("created_at", -1).limit(20).to_list(20)
        raw_messages = list(reversed(raw_messages))

        user_settings = user.get('settings', {})
        business_name = user.get('business_name', 'Your Business')
        currency = user_settings.get('currency', 'USD')
        model_pref = user_settings.get('ai_model', 'standard')
        customer_name = customer.get('name', 'Customer')
        custom_direction = request.custom_instructions or ""
        regenerate_count = request.regenerate_count or 0
        requested_mode = (request.mode or "auto").strip().lower()
        if requested_mode not in ("auto", "business", "personal"):
            requested_mode = "auto"

        # Build business knowledge string
        bk_data = user.get('business_knowledge', {})
        business_type = bk_data.get('business_type', 'general')
        bk_parts = []
        if bk_data.get('business_description'):
            bk_parts.append(f"About: {bk_data['business_description']}")

        if business_type == 'creator':
            # Creator-specific fields injected with clear labels for the AI
            if bk_data.get('creator_niche'):
                bk_parts.append(f"Content niche: {bk_data['creator_niche']}")
            if bk_data.get('creator_platforms'):
                bk_parts.append(f"Platforms: {bk_data['creator_platforms']}")
            if bk_data.get('creator_audience_size'):
                bk_parts.append(f"Audience size: {bk_data['creator_audience_size']}")
            if bk_data.get('creator_collab_types'):
                bk_parts.append(f"Collaboration types offered: {bk_data['creator_collab_types']}")
            if bk_data.get('creator_rate_card'):
                bk_parts.append(f"Rate card: {bk_data['creator_rate_card']}")
            if bk_data.get('creator_whats_included'):
                bk_parts.append(f"What's included: {bk_data['creator_whats_included']}")
            if bk_data.get('creator_turnaround'):
                bk_parts.append(f"Turnaround time: {bk_data['creator_turnaround']}")
            if bk_data.get('creator_booking_process'):
                bk_parts.append(f"Booking process: {bk_data['creator_booking_process']}")
            if bk_data.get('creator_min_budget'):
                bk_parts.append(f"Minimum budget: {bk_data['creator_min_budget']}")
            if bk_data.get('creator_blacklisted_niches'):
                bk_parts.append(f"Brands I don't work with: {bk_data['creator_blacklisted_niches']}")
            if bk_data.get('creator_media_kit_link'):
                bk_parts.append(f"Media kit: {bk_data['creator_media_kit_link']}")
            if bk_data.get('creator_fan_dm_response'):
                bk_parts.append(f"Fan DM response template: {bk_data['creator_fan_dm_response']}")
        else:
            if bk_data.get('products_services'):
                bk_parts.append(f"Products/Services: {bk_data['products_services']}")
            if bk_data.get('delivery_info'):
                bk_parts.append(f"Delivery: {bk_data['delivery_info']}")

        if bk_data.get('pricing_info'):
            bk_parts.append(f"Payment notes: {bk_data['pricing_info']}")
        if bk_data.get('business_hours'):
            bk_parts.append(f"Hours: {bk_data['business_hours']}")
        if bk_data.get('special_offers'):
            bk_parts.append(f"Current offers: {bk_data['special_offers']}")
        if bk_data.get('faqs'):
            bk_parts.append(f"FAQs: {bk_data['faqs']}")
        # Inject structured payment methods
        raw_pm = user.get('payment_methods', [])
        if raw_pm:
            pm_lines = []
            for pm in raw_pm:
                if isinstance(pm, dict):
                    line = pm.get('name', '')
                    if pm.get('details'):
                        line += f": {pm['details']}"
                else:
                    line = str(pm)
                if line.strip():
                    pm_lines.append(f"  - {line}")
            if pm_lines:
                bk_parts.append("Payment methods accepted:\n" + "\n".join(pm_lines))

        # Inject product catalog
        user_products = await db.products.find({"user_id": business_id}).to_list(50)
        if user_products:
            catalog_lines = ["\nProducts available:"]
            idx = 1
            for p in user_products:
                if not p.get("in_stock", True):
                    continue
                price_str = f"{currency} {p['price']:,.0f}" if p.get('price') is not None else "price on request"
                desc = f" — {p['description'][:80]}" if p.get("description") else ""
                catalog_lines.append(f"  {idx}. {p['name']}: {price_str}{desc}")
                idx += 1
            bk_parts.append("\n".join(catalog_lines))

        business_knowledge = "\n".join(bk_parts) if bk_parts else ""

        # Build conversation log with timestamps for threaded context
        history = [
            {"direction": m["direction"], "content": m["content"], "created_at": m.get("created_at")}
            for m in raw_messages
        ]

        # Use threaded context — same logic as the agent pipeline
        from agents.intent_analyzer import build_threaded_context, format_threaded_history, _parse_ts
        threaded = build_threaded_context(history)
        relationship = threaded.get("relationship", "new_conversation")
        hours_since = threaded.get("hours_since_last")
        threaded_history_text = format_threaded_history(threaded)

        conv_lines = []
        for m in history:
            role = "Customer" if m["direction"] == "incoming" else "You"
            conv_lines.append(f"{role}: {m['content']}")
        conversation_log = "\n".join(conv_lines) if conv_lines else ""

        # Determine scenario — use threaded relationship signal
        last_message = history[-1] if history else None
        days_since = customer.get("days_since_contact")
        last_contacted = customer.get("last_contacted")
        if not days_since and last_contacted:
            try:
                lc = last_contacted if isinstance(last_contacted, datetime) else datetime.fromisoformat(str(last_contacted).replace("Z", "+00:00"))
                days_since = (datetime.utcnow() - lc.replace(tzinfo=None)).days
            except Exception:
                days_since = None

        is_first_contact = not last_message and not last_contacted
        # Find the most recent INCOMING message regardless of position
        last_incoming = next((m for m in reversed(history) if m["direction"] == "incoming"), None)
        last_incoming_text = (last_incoming["content"] if last_incoming else "").strip()
        last_incoming_lower = last_incoming_text.lower()
        customer_is_personal = bool(customer.get("is_personal", False))
        effective_personal_mode = requested_mode == "personal" or (requested_mode == "auto" and customer_is_personal)
        greeting_starts = ("hi", "hello", "hey", "good morning", "good afternoon", "good evening", "morning", "evening", "habari", "mambo", "niaje", "sasa", "how are you", "how r u", "umeamkaje", "za asubuhi")
        business_keywords = ("price", "cost", "how much", "buy", "order", "pay", "catalog", "product", "stock", "available", "delivery", "cars", "car", "parts", "accessories")
        incoming_words = [w for w in re.findall(r"\b\w+\b", last_incoming_lower) if w]
        starts_like_greeting = any(last_incoming_lower.startswith(g) for g in greeting_starts)
        has_business_signal = any(k in last_incoming_lower for k in business_keywords)
        is_simple_greeting = bool(last_incoming_text) and starts_like_greeting and not has_business_signal and len(incoming_words) <= 8
        social_markers = ("😂", "🤣", "🥰", "😘", "😍", "❤️", "♥", "haha", "lol", "lmao")
        is_casual_social = bool(last_incoming_text) and not has_business_signal and (is_simple_greeting or any(marker in last_incoming_text or marker in last_incoming_lower for marker in social_markers))
        suppress_business_context = effective_personal_mode or is_casual_social
        if suppress_business_context:
            business_knowledge = ""
        # Replying to customer if: they sent something recently (within 24h) OR last message is theirs
        is_replying_to_incoming = (
            last_incoming is not None and (
                relationship in ("follow_up", "continuation") or
                (last_message and last_message["direction"] == "incoming")
            )
        )

        # Anti-repetition: block same opener as last outgoing message
        last_outgoing = next((m["content"] for m in reversed(history) if m["direction"] == "outgoing"), None)
        repetition_block = ""
        if last_outgoing:
            first_words = " ".join(last_outgoing.split()[:4])
            repetition_block = f'\nCRITICAL: Your last message to them started with "{first_words}" — do NOT open with those words or any variation. Completely different opener.'

        # Build scenario-specific writing goal
        has_bk = bool(business_knowledge.strip()) if business_knowledge else False

        if effective_personal_mode and last_incoming_text:
            scenario_block = f"""SCENARIO: This is a PERSONAL chat with {customer_name}, not a business customer.

LATEST MESSAGE: "{last_incoming_text}"

GOAL: Reply like a real person texting normally.
- Keep it casual, warm, and natural
- No sales language, no product mentions, no business pitch
- If it's just a greeting or playful message, reply to that energy only
- Short WhatsApp style — not polished, not formal"""

        elif is_casual_social and last_incoming_text:
            scenario_block = f"""SCENARIO: {customer_name} sent a casual message: "{last_incoming_text}"

GOAL: Reply naturally to their latest message only.
- Treat this like normal WhatsApp conversation, not a sales opportunity
- Do NOT force products, offers, catalog, or business info into the reply
- Match their vibe and keep it short
- If they just greeted you, greet back naturally and stop there"""

        elif is_first_contact:
            bk_instruction = (
                "USE the business info below — name at least one specific product or service by its actual name and price. "
                "Don't say 'we have great products' — say what they actually are."
            ) if has_bk else "Introduce yourself and your business briefly."

            scenario_block = f"""SCENARIO: First-ever message to {customer_name}. They don't know you yet.

GOAL: Write an opener that feels like it came from a real person — not a sales pitch, not a template.
- {bk_instruction}
- Introduce in ONE casual sentence — like telling a friend what you do
- End with a light question or open door — make it easy for them to reply
- DO NOT start with: "Hi, I'm reaching out", "I wanted to introduce", "Hope this finds you well", "I'm excited to share" — dead giveaways of a mass message"""

        elif is_replying_to_incoming:
            last_in = last_incoming["content"]
            # Add time context for the AI
            if relationship == "follow_up":
                time_note = f"They replied just now (within the last 30 minutes)."
            elif hours_since and hours_since < 24:
                time_note = f"They replied {int(hours_since)} hours ago."
            else:
                time_note = ""
            bk_instruction = (
                "The business info below has real product names and prices — USE them directly in your answer. "
                "Never say 'let me check' or 'I'll get back to you' when the answer is right there."
            ) if has_bk else ""

            scenario_block = f"""SCENARIO: {customer_name} messaged you: "{last_in}" {time_note}

GOAL: Reply directly and naturally to THEIR LATEST MESSAGE ONLY.
- CRITICAL: Ignore any old topics from days/weeks ago — reply to what they JUST said: "{last_in}"
- Answer their actual question — don't dance around it
- {bk_instruction}
- Skip the greeting if the conversation is already going
- Match their energy: casual stays casual, direct stays direct
- If this is a short follow-up like "ok" or "yes" — look at the recent thread below to understand what they're agreeing to
- DO NOT reference old conversation topics unless the customer explicitly brought them up in their latest message"""

        else:
            days_label = f"{days_since} days" if days_since else "a while"
            # Show last incoming if exists — more relevant than last outgoing
            last_preview = last_incoming["content"][:120] if last_incoming else (last_message["content"][:120] if last_message else "(no prior message on record)")
            bk_instruction = (
                "Use the business info below as your hook — reference a specific product, price, offer, or update by name. "
                "That's a real reason to reply. Vague 'just checking in' gives them nothing to respond to."
            ) if has_bk else "Give them a real reason to reply — a question, an update, something useful."

            scenario_block = f"""SCENARIO: Following up with {customer_name} after {days_label}. Last thing from them: "{last_preview}"

GOAL: Re-engage them with one short, genuine message.
- {bk_instruction}
- Reference the last topic only if it's still naturally relevant
- Sound like you're texting someone you actually know, not sending a follow-up email
- BANNED openers: "Just checking in", "I wanted to follow up", "Hope you're doing well", "It's been a while" — customers tune these out immediately"""

        # Custom direction — clean injection for regenerate
        direction_block = ""
        if custom_direction.strip():
            direction_block = f"\n\nDIRECTION FOR THIS VERSION: {custom_direction.strip()}\nApply this while keeping the message natural and WhatsApp-appropriate."

        # Variety directive — only for outbound/re-engage drafts, NOT when replying to a specific incoming message
        # When replying, variety would derail the AI away from the customer's actual question
        variety_block = ""
        if not is_replying_to_incoming:
            variety_angles = [
                "Try a direct question opener — ask them something specific about a product or their needs.",
                "Lead with a specific product name and price from the business info as the hook.",
                "Open with a reference to the last conversation topic, then connect it to something in your catalog.",
                "Try a very short punchy opener — under 8 words, name a specific product or offer.",
                "Open with a benefit — what does your best product do for them? Name it specifically.",
                "Be warm and personal — reference something from the conversation history, then offer to help.",
                "Be ultra-direct — one sentence naming a specific product/price, straight to the point.",
            ]
            angle = variety_angles[regenerate_count % len(variety_angles)]
            variety_block = f"\n\nVARIETY NOTE (draft attempt #{regenerate_count + 1}): {angle} Make this version feel distinctly different from any previous draft."

        # Business context — label it clearly as the source of truth
        bk_block = (
            f"\n\nYOUR BUSINESS INFO — use specific names and prices from this, do not speak generically:\n{business_knowledge}"
            if has_bk else f"\n\nBusiness name: {business_name}"
        )
        if suppress_business_context:
            bk_block = ""

        # Use threaded history if available — shows immediate thread + older context separately
        if relationship == "new_conversation" and last_incoming_text:
            history_block = f"\n\nLatest message from {customer_name}:\nCustomer: {last_incoming_text}"
        elif is_replying_to_incoming and last_incoming_text:
            # When replying, show last 8 messages for multi-turn context
            recent_only = []
            for m in history[-8:]:
                role = "Customer" if m["direction"] == "incoming" else "You"
                recent_only.append(f"{role}: {m['content']}")
            history_block = f"\n\nRecent thread (context only — reply to the LATEST message above):\n" + "\n".join(recent_only)
        elif threaded_history_text and threaded_history_text != "(no prior history)":
            history_block = f"\n\nConversation context:\n{threaded_history_text}"
        elif conversation_log:
            history_block = f"\n\nConversation history (most recent at bottom):\n{conversation_log}"
        else:
            history_block = "\n\n(No prior conversation with this customer)"

        # Relationship context note for prompt
        relationship_note = ""
        if relationship == "new_conversation":
            relationship_note = "\n\n⚡ NOTE: This customer hasn't messaged in over 24 hours — treat this as a FRESH conversation. Do NOT reference old topics unless directly relevant."
        elif relationship == "follow_up":
            relationship_note = "\n\n⚡ NOTE: This is an ACTIVE conversation — the customer just replied recently. Keep the flow natural, no re-introductions."
        elif is_replying_to_incoming:
            relationship_note = f"\n\n⚡ CRITICAL: Reply to their LATEST message: \"{last_incoming_text[:100]}\" — ignore any old topics from earlier in the conversation history."

        # Anchor block — moved to TOP of prompt so AI sees the most recent exchange FIRST
        recent_lines = []
        for m in history[-8:]:
            role = "Customer" if m["direction"] == "incoming" else "You"
            recent_lines.append(f"{role}: {m['content']}")
        recent_exchange = "\n".join(recent_lines) if recent_lines else ""
        anchor_block = (
            f"MOST RECENT EXCHANGE — your reply MUST address this directly:\n{recent_exchange}\n"
            if recent_exchange else ""
        )

        # Latest incoming message focus block — prominently signals what to reply to
        if last_incoming_text:
            latest_msg_block = (
                f"CUSTOMER'S LATEST MESSAGE: \"{last_incoming_text}\"\n"
                f"→ Reply to THIS. Not to old topics. Not to the full history. THIS message.\n"
            )
        else:
            latest_msg_block = ""

        # Session summary — structured understanding of what conversation is about
        session_summary_block = ""
        try:
            from agents.session_summarizer import maybe_summarize, format_summary_for_prompt
            from agents.conversation_state import load_state
            _conv_state = await load_state(db, business_id, request.customer_id)
            _session_summary = await maybe_summarize(
                history=history,
                user_id=business_id,
                customer_id=request.customer_id,
                db=db,
                conv_state=_conv_state,
            )
            if _session_summary:
                _summary_text = format_summary_for_prompt(_session_summary)
                if _summary_text:
                    session_summary_block = f"\nCONVERSATION SUMMARY (use this to understand context, but still reply to the LATEST message above):\n{_summary_text}\n"
        except Exception:
            pass
        # Relax length limit if the user explicitly asks for a list or catalog
        length_rule = "2. 1-3 sentences. Short is better. WhatsApp messages are not emails."
        if custom_direction and any(word in custom_direction.lower() for word in ["list", "catalog", "menu", "products", "options"]):
            length_rule = "2. You MAY use a numbered list if it fits the user's direction, keeping items brief."

        # Full prompt — anchor and latest message are at the TOP so the AI sees them first
        prompt = f"""You are the owner of {business_name}. You're writing a WhatsApp message to {customer_name}.
You are a real person — not a bot, not a marketing tool. Direct, warm, brief.

{latest_msg_block}
{anchor_block}
{session_summary_block}
{scenario_block}{bk_block}{history_block}{relationship_note}{repetition_block}{direction_block}{variety_block}

WRITING RULES (non-negotiable):
1. Output ONLY the message text. No labels, no quotes around it, no explanation.
{length_rule}
3. YOUR REPLY MUST DIRECTLY ADDRESS the customer's latest message shown at the top — do NOT ignore it and talk about something unrelated.
4. USE REAL SPECIFICS: If business info is provided, name actual products, actual prices, actual offers — never say "we have great options".
5. BANNED PHRASES — never use: "Sure thing", "Absolutely", "Certainly", "Of course", "I'd be happy to", "Feel free to", "Don't hesitate", "I hope this helps", "Thank you for your interest", "I understand your concern", "Kindly", "Please be advised", "I apologize for any inconvenience", "I'm reaching out", "I wanted to touch base".
6. LANGUAGE: Write in the same language the customer used in their last message. Mix naturally if they mix.
7. EMOJIS: Only if it genuinely fits. Never: 😊😇🙏✨💯 — bot emojis.
8. HONESTY: Only use facts from the business info above. Never invent prices, stock, or promises not listed.

Think one sentence about what this customer actually needs, then reply. Output only the customer-facing message."""

        # Call LLM directly
        from ai_service import get_drafter
        ai_service = get_drafter()
        drafted = await ai_service._call_llm(prompt, model_pref=model_pref)
        drafted = drafted.strip().strip('"').strip("'")

        # Build reason string
        if is_first_contact:
            reason = "First message — introduce your business"
        elif effective_personal_mode:
            reason = f"Personal reply to: {last_incoming_text[:60]}..." if last_incoming_text else "Personal conversation reply"
        elif is_casual_social:
            reason = f"Replying naturally to: {last_incoming_text[:60]}..." if last_incoming_text else "Casual conversation reply"
        elif is_replying_to_incoming:
            reason = f"Replying to: {last_message['content'][:60]}..."
        else:
            reason = f"No contact in {days_label}" if days_since else "Follow-up opportunity"

        return DraftMessageResponse(
            message=drafted or f"Hi {customer_name}, just checking in — anything I can help you with?",
            confidence=0.9,
            reason=reason
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        err_msg = f"Error in draft_ai_message: {e}\n{traceback.format_exc()}"
        logging.error(err_msg)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/ai/send-auto-message")
async def send_auto_message(request: SendAutoMessageRequest, user = Depends(get_current_user)):
    """Send an auto-drafted message via WhatsApp"""
    
    # Check if auto-reply is enabled
    user_settings = user.get('settings', {})
    if not user_settings.get('auto_reply_enabled', False):
        raise HTTPException(status_code=403, detail="Auto-reply is not enabled")
    
    business_id = user.get("business_id", user["_id"])
    # Get customer
    customer = await db.customers.find_one({"_id": request.customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Store message in database
    message_id = str(uuid.uuid4())
    message_doc = {
        "_id": message_id,
        "customer_id": request.customer_id,
        "user_id": business_id,
        "direction": "outgoing",
        "content": request.message,
        "message_type": "text",
        "created_at": datetime.utcnow(),
        "auto_sent": True
    }
    await db.messages.insert_one(message_doc)
    
    # Update customer's last contacted time
    await db.customers.update_one(
        {"_id": request.customer_id},
        {"$set": {"last_contacted": datetime.utcnow()}}
    )
    
    # Send via WhatsApp
    phone = customer.get("phone_number")
    if not phone:
        return {
            "status": "partial",
            "message_id": message_id,
            "note": "Message logged but customer has no phone number."
        }
    
    try:
        from whatsapp_service import get_whatsapp_service
        whatsapp_service = get_whatsapp_service(db)
        await whatsapp_service.send_message(
            user_id=business_id,
            to_number=phone,
            message=request.message,
            customer_name=customer.get("name"),
            send_context="auto_reply",
        )
    except Exception as e:
        logging.error(f"Auto-reply WhatsApp send failed: {e}")
        return {
            "status": "partial",
            "message_id": message_id,
            "note": f"Message logged but WhatsApp send failed: {str(e)[:100]}"
        }
    
    return {
        "status": "success",
        "message_id": message_id,
        "note": "Message sent via WhatsApp"
    }

@api_router.get("/analysis/daily-insights")
async def get_daily_insights(background_tasks: BackgroundTasks, limit: int = 10, user = Depends(get_current_user)):
    """Get today's customer insights from AI analysis"""
    try:
        analyzer = DailyCustomerAnalyzer(db)
        business_id = user.get("business_id", user["_id"])
        
        # Check if we have today's analysis
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        existing_analysis_count = await db.customer_analysis.count_documents({
            "user_id": business_id,
            "analysis_date": {"$gte": today}
        })
        
        # Only trigger background analysis if none exists today for this business
        if existing_analysis_count == 0:
            logging.info(f"Triggering background analysis for business {business_id}")
            background_tasks.add_task(analyzer.analyze_all_customers, business_id)
        
        # Get whatever insights we have so far (poll correctly handles partial results)
        insights = await analyzer.get_todays_insights(business_id, limit)
        
        from bson import json_util
        import json
        return json.loads(json_util.dumps(insights))
        
    except Exception as e:
        import traceback
        logging.error(f"Error in daily-insights: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/analysis/run-now")
async def run_analysis_now(user = Depends(get_current_user)):
    """Manually trigger customer analysis"""
    
    analyzer = DailyCustomerAnalyzer(db)
    analyses = await analyzer.analyze_all_customers(user["_id"])
    
    return {
        "status": "success",
        "analyzed_count": len(analyses),
        "high_priority": len([a for a in analyses if a['urgency_level'] == 'high'])
    }

# ============ DIGEST ENDPOINTS ============

@api_router.get("/digest/preview")
async def preview_digest(digest_type: str = "morning", user = Depends(get_current_user)):
    """Preview digest without sending it"""
    from digest_service import get_digest_service
    
    business_id = user.get("business_id", user["_id"])
    digest_service = get_digest_service(db)
    
    digest = await digest_service.generate_digest(business_id, digest_type)
    whatsapp_message = digest_service.format_whatsapp_message(digest)
    push_notification = digest_service.format_push_notification(digest)
    
    return {
        "digest": digest,
        "whatsapp_message": whatsapp_message,
        "push_notification": push_notification
    }

@api_router.post("/digest/send-now")
async def send_digest_now(digest_type: str = "morning", user = Depends(get_current_user)):
    """Manually send digest to current user"""
    from digest_service import get_digest_service
    from notification_service import get_notification_service
    from whatsapp_service import WhatsAppService
    
    business_id = user.get("business_id", user["_id"])
    digest_service = get_digest_service(db)
    
    # Generate digest
    digest = await digest_service.generate_digest(business_id, digest_type)
    
    results = {"whatsapp": False, "push": False}
    
    # Send via WhatsApp
    if user.get("phone_number"):
        try:
            wa_service = WhatsAppService()
            message = digest_service.format_whatsapp_message(digest)
            result = await wa_service.send_message(
                user_id=user["_id"],
                to_number=user["phone_number"],
                message=message
            )
            results["whatsapp"] = result.get("success", False)
        except Exception as e:
            logging.error(f"WhatsApp delivery failed: {e}")
    
    # Send via Push
    if user.get("push_token"):
        try:
            notification_service = get_notification_service()
            notification = digest_service.format_push_notification(digest)
            results["push"] = await notification_service.send_notification(
                push_token=user["push_token"],
                title=notification["title"],
                body=notification["body"],
                data=notification["data"]
            )
        except Exception as e:
            logging.error(f"Push delivery failed: {e}")
    
    return {
        "status": "sent",
        "digest": digest,
        "delivery": results
    }

@api_router.post("/users/push-token")
async def register_push_token(token: str = Body(..., embed=True), user = Depends(get_current_user)):
    """Register user's push notification token"""
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"push_token": token}}
    )
    return {"status": "ok"}

@api_router.post("/users/notifications/settings")
async def update_notification_settings(
    enabled: bool = Body(...),
    user = Depends(get_current_user)
):
    """Update notification preferences"""
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"notifications_enabled": enabled}}
    )
    return {"status": "ok", "notifications_enabled": enabled}

@api_router.get("/motivation/preview")
async def preview_motivation(is_monday: bool = False, user = Depends(get_current_user)):
    """Preview motivation message without sending"""
    from motivation_service import get_motivation_service
    
    motivation_service = get_motivation_service(db)
    
    if is_monday:
        motivation = await motivation_service.get_monday_motivation(user["_id"])
    else:
        motivation = await motivation_service.get_midweek_motivation(user["_id"])
    
    return motivation

@api_router.post("/motivation/send-now")
async def send_motivation_now(is_monday: bool = False, user = Depends(get_current_user)):
    """Manually send motivation message to current user"""
    from motivation_service import get_motivation_service
    from whatsapp_service import WhatsAppService
    
    motivation_service = get_motivation_service(db)
    
    if is_monday:
        motivation = await motivation_service.get_monday_motivation(user["_id"])
    else:
        motivation = await motivation_service.get_midweek_motivation(user["_id"])
    
    result = {"sent": False}
    
    # Send via WhatsApp
    if user.get("phone_number"):
        try:
            wa_service = WhatsAppService()
            response = await wa_service.send_message(
                user_id=user["_id"],
                to_number=user["phone_number"],
                message=motivation["message"]
            )
            result["sent"] = response.get("success", False)
        except Exception as e:
            logging.error(f"WhatsApp delivery failed: {e}")
    
    return {
        "status": "sent" if result["sent"] else "failed",
        "motivation": motivation,
        "delivery": result
    }

# ============ DAILY PULSE ENDPOINTS ============

async def generate_daily_pulse_message(user_id: str) -> str:
    """Generate the daily business pulse summary message"""
    from datetime import timedelta
    
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    # Get user info
    user = await db.users.find_one({"_id": user_id})
    business_name = user.get("business_name", "Your Business") if user else "Your Business"
    currency = user.get("currency") or user.get("settings", {}).get("currency", "USD") if user else "USD"
    
    # Today's sales
    today_sales = await db.sales.find({
        "user_id": user_id,
        "created_at": {"$gte": today, "$lt": tomorrow}
    }).to_list(1000)
    
    total_sales_amount = sum(s.get("amount", 0) for s in today_sales)
    sales_count = len(today_sales)
    
    # Today's expenses
    today_expenses = await db.expenses.find({
        "user_id": user_id,
        "created_at": {"$gte": today, "$lt": tomorrow}
    }).to_list(1000)
    
    total_expenses = sum(e.get("amount", 0) for e in today_expenses)
    expenses_count = len(today_expenses)
    
    # Net profit
    net_profit = total_sales_amount - total_expenses
    
    # Top customer today
    customer_totals = {}
    for sale in today_sales:
        cid = sale.get("customer_id", "unknown")
        customer_totals[cid] = customer_totals.get(cid, 0) + sale.get("amount", 0)
    
    top_customer_name = None
    top_customer_amount = 0
    if customer_totals:
        top_cid = max(customer_totals, key=customer_totals.get)
        top_customer_amount = customer_totals[top_cid]
        top_customer = await db.customers.find_one({"_id": top_cid})
        top_customer_name = top_customer["name"] if top_customer else "Walk-in"
    
    # Credit sales unpaid
    unpaid_credits = await db.sales.find({
        "user_id": user_id,
        "is_credit": True,
        "paid_date": None
    }).to_list(1000)
    unpaid_count = len(unpaid_credits)
    unpaid_total = sum(s.get("amount", 0) for s in unpaid_credits)
    
    # Pending orders
    pending_orders = await db.orders.find({
        "user_id": user_id,
        "delivery_status": {"$ne": "Delivered"}
    }).to_list(1000)
    pending_orders_count = len(pending_orders)
    
    # Pending follow-ups
    pending_followups = await db.followups.find({
        "user_id": user_id,
        "status": "pending",
        "reminder_date": {"$lte": tomorrow}
    }).to_list(1000)
    overdue_followups = [f for f in pending_followups if f.get("reminder_date", tomorrow) < today]
    
    # Build message
    date_str = today.strftime("%a, %b %d")
    
    lines = [f"📊 *Daily Pulse — {date_str}*"]
    lines.append(f"_{business_name}_\n")
    
    # Sales & Profit
    lines.append(f"💰 Sales: {currency} {total_sales_amount:,.0f} ({sales_count} sale{'s' if sales_count != 1 else ''})")
    if expenses_count > 0:
        lines.append(f"💸 Expenses: {currency} {total_expenses:,.0f}")
    
    profit_emoji = "📈" if net_profit >= 0 else "📉"
    lines.append(f"{profit_emoji} Net Profit: {currency} {net_profit:,.0f}\n")
    
    # Top customer
    if top_customer_name:
        lines.append(f"🔥 Top Customer: {top_customer_name} ({currency} {top_customer_amount:,.0f})")
    
    # Alerts
    alerts = []
    if unpaid_count > 0:
        alerts.append(f"⚠️ {unpaid_count} credit sale{'s' if unpaid_count != 1 else ''} unpaid ({currency} {unpaid_total:,.0f} due)")
    if pending_orders_count > 0:
        alerts.append(f"📦 {pending_orders_count} order{'s' if pending_orders_count != 1 else ''} pending delivery")
    if len(overdue_followups) > 0:
        alerts.append(f"🔔 {len(overdue_followups)} overdue follow-up{'s' if len(overdue_followups) != 1 else ''}")
    
    if alerts:
        lines.append("")
        lines.extend(alerts)
    
    # AI Tip - simple rule-based insights
    tip = None
    if sales_count == 0:
        tip = "No sales today. Consider sending a broadcast to re-engage your customers!"
    elif top_customer_name and top_customer_amount > total_sales_amount * 0.5:
        tip = f"{top_customer_name} made up over half your revenue today — consider a loyalty reward to keep them coming back!"
    elif unpaid_count >= 3:
        tip = f"You have {unpaid_count} unpaid credits. Send gentle reminders to recover {currency} {unpaid_total:,.0f}."
    elif net_profit > 0 and sales_count >= 3:
        tip = "Great day! You're on a roll. Keep the momentum going tomorrow!"
    elif len(overdue_followups) > 0:
        tip = f"You have {len(overdue_followups)} overdue follow-ups. Reaching out could turn them into sales!"
    
    if tip:
        lines.append(f"\n🤖 *AI Tip:* _{tip}_")
    
    lines.append("\n_Sent by Zilo_")
    
    return "\n".join(lines)


@api_router.get("/daily-pulse/preview")
async def preview_daily_pulse(user = Depends(get_current_user)):
    """Preview today's daily pulse message without sending"""
    message = await generate_daily_pulse_message(user["_id"])
    return {"message": message}


@api_router.post("/daily-pulse/send")
async def send_daily_pulse(user = Depends(get_current_user)):
    """Manually send today's daily pulse via WhatsApp"""
    from whatsapp_service import get_whatsapp_service
    
    message = await generate_daily_pulse_message(user["_id"])
    phone = user.get("phone_number")
    
    if not phone:
        raise HTTPException(status_code=400, detail="No phone number on account")
    
    whatsapp_service = get_whatsapp_service(db)
    try:
        result = await whatsapp_service.send_message(
            user_id=user["_id"],
            to_number=phone,
            message=message,
            customer_name=user.get("owner_name", "Business Owner"),
            send_context="auto_reply",
        )
        return {"status": "success", "message": "Daily pulse sent!", "preview": message}
    except Exception as e:
        logging.error(f"Failed to send daily pulse: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send: {str(e)}")


async def run_daily_pulse_scheduler():
    """Background task that checks every minute and sends daily pulse to users at their scheduled time"""
    import asyncio
    
    while True:
        try:
            now = datetime.utcnow()
            current_time = now.strftime("%H:%M")
            
            # Find users who have daily pulse enabled and it's their scheduled time
            users_cursor = db.users.find({
                "settings.daily_pulse_enabled": True,
                "settings.daily_pulse_time": current_time
            })
            
            async for user in users_cursor:
                try:
                    phone = user.get("phone_number")
                    if not phone:
                        continue
                    
                    # Check if we already sent today (prevent duplicates)
                    today_key = now.strftime("%Y-%m-%d")
                    last_sent = user.get("settings", {}).get("daily_pulse_last_sent")
                    if last_sent == today_key:
                        continue
                    
                    message = await generate_daily_pulse_message(user["_id"])
                    
                    from whatsapp_service import get_whatsapp_service
                    whatsapp_service = get_whatsapp_service(db)
                    
                    await whatsapp_service.send_message(
                        user_id=user["_id"],
                        to_number=phone,
                        message=message,
                        customer_name=user.get("owner_name", "Business Owner"),
                        send_context="auto_reply",
                    )
                    
                    # Mark as sent today
                    await db.users.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"settings.daily_pulse_last_sent": today_key}}
                    )
                    
                    logging.info(f"Daily pulse sent to {user.get('business_name', user['_id'])}")
                    
                except Exception as e:
                    logging.error(f"Failed to send daily pulse to user {user.get('_id')}: {e}")
            
        except Exception as e:
            logging.error(f"Daily pulse scheduler error: {e}")
        
        # Check every 60 seconds
        await asyncio.sleep(60)


# ============ USER SETTINGS ENDPOINTS ============

@api_router.get("/settings")
async def get_user_settings(user = Depends(get_current_user)):
    """Get user settings"""
    settings = user.get('settings', {})
    
    # Auto-detect currency from phone number if not explicitly set
    currency = settings.get('currency', '')
    country_code = settings.get('country_code', '')
    if not currency or currency == 'USD':
        phone = user.get('phone_number', '')
        if phone:
            from ai_service import detect_language_from_phone, PHONE_PREFIX_LANGUAGES
            lang_info = detect_language_from_phone(phone)
            if lang_info.get('country'):
                # Map country to currency
                country_currency_map = {
                    'Kenya': ('KE', 'KES'), 'Tanzania': ('TZ', 'TZS'), 'Uganda': ('UG', 'UGX'),
                    'Ethiopia': ('ET', 'ETB'), 'Nigeria': ('NG', 'NGN'), 'Ghana': ('GH', 'GHS'),
                    'South Africa': ('ZA', 'ZAR'), 'Cameroon': ('CM', 'XAF'), 'Ivory Coast': ('CI', 'XOF'),
                    'Senegal': ('SN', 'XOF'), 'DR Congo': ('CD', 'CDF'), 'Rwanda': ('RW', 'RWF'),
                    'Burundi': ('BI', 'BIF'), 'Somalia': ('SO', 'SOS'),
                    'India': ('IN', 'INR'), 'Pakistan': ('PK', 'PKR'), 'Bangladesh': ('BD', 'BDT'),
                    'Philippines': ('PH', 'PHP'), 'Indonesia': ('ID', 'IDR'), 'Malaysia': ('MY', 'MYR'),
                    'Thailand': ('TH', 'THB'), 'Vietnam': ('VN', 'VND'),
                    'China': ('CN', 'CNY'), 'Japan': ('JP', 'JPY'), 'South Korea': ('KR', 'KRW'),
                    'UAE': ('AE', 'AED'), 'Saudi Arabia': ('SA', 'SAR'), 'Egypt': ('EG', 'EGP'),
                    'Morocco': ('MA', 'MAD'), 'Tunisia': ('TN', 'TND'),
                    'USA/Canada': ('US', 'USD'), 'UK': ('GB', 'GBP'),
                    'France': ('FR', 'EUR'), 'Germany': ('DE', 'EUR'), 'Spain': ('ES', 'EUR'),
                    'Italy': ('IT', 'EUR'), 'Portugal': ('PT', 'EUR'),
                    'Brazil': ('BR', 'BRL'), 'Mexico': ('MX', 'MXN'), 'Colombia': ('CO', 'COP'),
                    'Chile': ('CL', 'CLP'), 'Argentina': ('AR', 'ARS'),
                }
                detected = country_currency_map.get(lang_info['country'])
                if detected:
                    currency = detected[1]
                    if not country_code:
                        country_code = detected[0]
                    # Persist so we don't detect every time
                    await db.users.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"settings.currency": currency, "settings.country_code": country_code}}
                    )
    
    if not currency:
        currency = 'USD'
    
    # Return with defaults
    return {
        "auto_reply_enabled": settings.get('auto_reply_enabled', False),
        "notification_enabled": settings.get('notification_enabled', True),
        "notification_time": settings.get('notification_time', '08:00'),
        "daily_alert_count": settings.get('daily_alert_count', 5),
        "message_tone": settings.get('message_tone', 'friendly'),
        "push_token": user.get('push_token'),
        "daily_pulse_enabled": settings.get('daily_pulse_enabled', False),
        "daily_pulse_time": settings.get('daily_pulse_time', '20:00'),
        "ai_model": settings.get('ai_model', 'standard'),
        "currency": currency,
        "country_code": country_code,
        "plan_limits": get_plan_limits(user),
        "subscription_plan": user.get("subscription_plan", "free"),
        "business_type": settings.get("business_type", "retail"),
        "business_hours": settings.get("business_hours", {}),
        "booking_settings": settings.get("booking_settings", {}),
        "timezone": settings.get("timezone", "UTC"),
        "rental_availability": settings.get("rental_availability", []),
        "payment_methods": user.get("payment_methods", settings.get("payment_methods", [])),
    }

@api_router.put("/settings")
async def update_user_settings(settings: UserSettingsUpdate, user = Depends(get_current_user)):
    """Update user settings"""
    
    update_data = {}
    
    if settings.auto_reply_enabled is not None:
        update_data['settings.auto_reply_enabled'] = settings.auto_reply_enabled
    
    if settings.notification_enabled is not None:
        update_data['settings.notification_enabled'] = settings.notification_enabled
    
    if settings.notification_time is not None:
        update_data['settings.notification_time'] = settings.notification_time
    
    if settings.daily_alert_count is not None:
        update_data['settings.daily_alert_count'] = settings.daily_alert_count
    
    if settings.message_tone is not None:
        update_data['settings.message_tone'] = settings.message_tone
    
    if settings.daily_pulse_enabled is not None:
        update_data['settings.daily_pulse_enabled'] = settings.daily_pulse_enabled
    
    if settings.daily_pulse_time is not None:
        update_data['settings.daily_pulse_time'] = settings.daily_pulse_time
    
    if settings.push_token is not None:
        update_data['push_token'] = settings.push_token
    
    if settings.payment_methods is not None:
        update_data['payment_methods'] = settings.payment_methods
    
    if settings.currency is not None:
        update_data['settings.currency'] = settings.currency
    
    if settings.country_code is not None:
        update_data['settings.country_code'] = settings.country_code
    
    if settings.ai_model is not None:
        update_data['settings.ai_model'] = settings.ai_model
    
    if settings.auto_reply_audience is not None:
        update_data['settings.auto_reply_audience'] = settings.auto_reply_audience

    if settings.business_type is not None:
        update_data['settings.business_type'] = settings.business_type

    if settings.business_hours is not None:
        update_data['settings.business_hours'] = settings.business_hours

    if settings.booking_settings is not None:
        update_data['settings.booking_settings'] = settings.booking_settings

    if settings.timezone is not None:
        update_data['settings.timezone'] = settings.timezone

    if settings.rental_availability is not None:
        update_data['settings.rental_availability'] = settings.rental_availability

    if update_data:
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": update_data}
        )
    
    return {"status": "success", "message": "Settings updated"}

@api_router.post("/notifications/register-token")
async def register_push_token(token: dict, user = Depends(get_current_user)):
    """Register Expo push token for notifications"""
    
    push_token = token.get('push_token')
    if not push_token:
        raise HTTPException(status_code=400, detail="push_token required")
    
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"push_token": push_token}}
    )
    
    return {"status": "success", "message": "Push token registered"}

@api_router.post("/notifications/send-test")
async def send_test_notification(user = Depends(get_current_user)):
    """Send a test notification to verify setup"""
    
    push_token = user.get('push_token')
    if not push_token:
        raise HTTPException(status_code=400, detail="No push token registered")
    
    notification_service = get_notification_service()
    success = await notification_service.send_notification(
        push_token=push_token,
        title="🎉 CRM Notifications Active!",
        body="You'll receive daily follow-up reminders here",
        data={"type": "test"}
    )
    
    if success:
        return {"status": "success", "message": "Test notification sent"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send notification")

@api_router.post("/notifications/send-daily-now")
async def send_daily_notifications_now(user = Depends(get_current_user)):
    """Manually trigger daily notifications (for testing)"""
    
    from daily_scheduler import get_scheduler
    
    try:
        scheduler = await get_scheduler(db)
        sent_count = await scheduler.send_daily_notifications()
        
        return {
            "status": "success",
            "message": f"Daily notifications sent to {sent_count} users",
            "sent_count": sent_count
        }
    except Exception as e:
        logging.error(f"Failed to send daily notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ PRODUCT CATALOG ENDPOINTS ============

@api_router.post("/products/reanalyze")
async def reanalyze_products(user = Depends(get_current_user)):
    """Re-analyze all product images with AI Vision to fix names/descriptions/categories"""
    from product_organizer import get_organizer
    organizer = get_organizer()
    
    if not organizer.vision_available:
        raise HTTPException(status_code=400, detail="OpenAI Vision not available. Add OPENAI_API_KEY to .env file.")
    
    products = await db.products.find({"user_id": user["_id"]}).to_list(100)
    if not products:
        return {"status": "success", "updated": 0, "message": "No products to analyze"}
    
    updated = 0
    results = []
    for p in products:
        image_url = p.get("image_url", "")
        if not image_url:
            continue
        
        # Use the full URL for remote images
        if not image_url.startswith("http"):
            server_url = os.environ.get("SERVER_URL", "").rstrip("/")
            if server_url:
                image_url = f"{server_url}{image_url}"
            else:
                continue
        
        try:
            analysis = await organizer.analyze_product_image(image_url)
            if "error" not in analysis and analysis.get("name", "Product") != "Product":
                update_data = {"name": analysis["name"], "category": analysis.get("category", "Other")}
                if analysis.get("description"):
                    update_data["description"] = analysis["description"]
                if analysis.get("suggested_price") and p.get("price", 0) == 0:
                    update_data["price"] = analysis["suggested_price"]
                
                await db.products.update_one({"_id": p["_id"]}, {"$set": update_data})
                updated += 1
                results.append({"id": p["_id"], "old_name": p["name"], "new_name": analysis["name"], "category": analysis.get("category")})
                logging.info(f"Re-analyzed product {p['_id']}: {p['name']} -> {analysis['name']}")
        except Exception as e:
            logging.error(f"Failed to re-analyze product {p['_id']}: {e}")
            results.append({"id": p["_id"], "old_name": p["name"], "error": str(e)})
    
    return {"status": "success", "updated": updated, "total": len(products), "results": results}

@api_router.post("/products/upload")
async def upload_products(
    files: List[UploadFile] = File(...),
    user = Depends(get_current_user)
):
    """Bulk upload product images with AI analysis"""
    
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Check product limit
    business_id = user.get("business_id", user["_id"])
    limits = get_plan_limits(user)
    count = await db.products.count_documents({"user_id": business_id})
    if limits["products"] is not None and count >= limits["products"]:
        raise HTTPException(status_code=400, detail=f"Product limit reached ({limits['products']} on your plan). Upgrade for more.")
    if limits["products"] is not None and count + len(files) > limits["products"]:
        raise HTTPException(status_code=400, detail=f"Can only add {limits['products'] - count} more product(s). You have {count}/{limits['products']}. Upgrade for more.")
    # Check total image limit (each bulk upload file = 1 image per product)
    if limits["images"] is not None:
        current_images = await count_total_images(db, business_id)
        if current_images + len(files) > limits["images"]:
            raise HTTPException(status_code=400, detail=f"Image limit reached ({limits['images']} total on your plan). Upgrade for more.")
    
    # Save images
    upload_handler = ImageUploadHandler()
    saved_images = await upload_handler.save_multiple_images(files)
    
    # Filter successful uploads
    successful_uploads = [img for img in saved_images if 'error' not in img]
    
    if not successful_uploads:
        raise HTTPException(status_code=400, detail="No images could be saved")
    
    # Analyze images with AI
    organizer = get_organizer()
    image_paths = [
        upload_handler.get_image_path(img['filename']) 
        for img in successful_uploads
    ]
    
    # Get business context for AI
    business_knowledge_data = user.get('business_knowledge', {})
    business_context = ""
    if business_knowledge_data:
        parts = []
        if business_knowledge_data.get('business_description'):
            parts.append(f"Description: {business_knowledge_data['business_description']}")
        if business_knowledge_data.get('products_services'):
            parts.append(f"Products/Services: {business_knowledge_data['products_services']}")
        business_context = " | ".join(parts)
    
    ai_analyses = await organizer.analyze_multiple_images([str(p) for p in image_paths], business_context=business_context)
    
    # Create product documents
    products = []
    now = datetime.utcnow()
    
    for i, (img_data, ai_data) in enumerate(zip(successful_uploads, ai_analyses)):
        ai_failed = 'error' in ai_data

        product_id = str(uuid.uuid4())
        product_doc = {
            "_id": product_id,
            "user_id": business_id,
            "name": ai_data.get('name', f'Product {i+1}') if not ai_failed else f'Product {i+1}',
            "price": float(ai_data.get('suggested_price') or 0.0) if not ai_failed else 0.0,
            "image_url": img_data['image_url'],
            "images": [img_data['image_url']],
            "category": ai_data.get('category', 'Other') if not ai_failed else 'Other',
            "description": ai_data.get('description', '') if not ai_failed else '',
            "in_stock": True,
            "ai_suggested_name": ai_data.get('name') if not ai_failed else None,
            "ai_confidence": ai_data.get('confidence', 0.5) if not ai_failed else 0.0,
            "ai_failed": ai_failed,
            "needs_review": True,
            "created_at": now,
            "updated_at": now
        }

        await db.products.insert_one(product_doc)
        products.append(product_doc)
    
    return {
        "status": "success",
        "uploaded_count": len(successful_uploads),
        "products_created": len(products),
        "products": [
            {
                "id": p["_id"],
                "name": p["name"],
                "price": p["price"],
                "discount_price": p.get("discount_price"),
                "category": p["category"],
                "description": p.get("description", ""),
                "image_url": p["image_url"],
                "images": p.get("images", []),
                "in_stock": p.get("in_stock", True),
                "ai_confidence": p.get("ai_confidence", 0),
                "ai_failed": p.get("ai_failed", False),
            }
            for p in products
        ]
    }

@api_router.get("/products")
async def get_products(
    category: Optional[str] = None,
    in_stock: Optional[bool] = None,
    user = Depends(get_current_user)
):
    """Get all products for the user"""
    
    query = {"user_id": user["_id"]}
    
    if category:
        query["category"] = category
    
    if in_stock is not None:
        query["in_stock"] = in_stock
    
    products = await db.products.find(query).sort("created_at", -1).to_list(100)
    
    return serialize_doc([
        {
            "id": p["_id"],
            "name": p["name"],
            "price": p["price"],
            "image_url": p["image_url"],
            "category": p.get("category", "Other"),
            "description": p.get("description", ""),
            "in_stock": p.get("in_stock", True),
            "created_at": p["created_at"].isoformat()
        }
        for p in products
    ])

@api_router.get("/products/{product_id}")
async def get_product(product_id: str, user = Depends(get_current_user)):
    """Get a single product"""
    business_id = user.get("business_id", user["_id"])
    product = await db.products.find_one({"_id": product_id, "user_id": business_id})
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    imgs = list(product.get("images", []))
    orig = product.get("image_url")
    if orig and orig not in imgs:
        imgs.insert(0, orig)
    
    return serialize_doc({
        "id": product["_id"],
        "name": product.get("name", "Unnamed Product"),
        "price": product.get("price") or 0.0,
        "image_url": orig,
        "images": imgs,
        "category": product.get("category", "Other"),
        "description": product.get("description", ""),
        "in_stock": product.get("in_stock", True),
        "ai_suggested_name": product.get("ai_suggested_name"),
        "ai_confidence": product.get("ai_confidence"),
        "created_at": product.get("created_at", datetime.utcnow()).isoformat() if hasattr(product.get("created_at", datetime.utcnow()), 'isoformat') else str(product.get("created_at", ""))
    })

@api_router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    product_update: ProductUpdate,
    user = Depends(get_current_user)
):
    """Update product details"""
    business_id = user.get("business_id", user["_id"])
    product = await db.products.find_one({"_id": product_id, "user_id": business_id})
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = {"updated_at": datetime.utcnow()}
    
    if product_update.name is not None:
        update_data["name"] = product_update.name
    
    if product_update.price is not None:
        update_data["price"] = product_update.price
    
    if product_update.category is not None:
        update_data["category"] = product_update.category
    
    if product_update.description is not None:
        update_data["description"] = product_update.description
    
    if product_update.in_stock is not None:
        update_data["in_stock"] = product_update.in_stock
    
    if product_update.stock_quantity is not None:
        update_data["stock_quantity"] = product_update.stock_quantity
    
    if product_update.offering_type is not None:
        update_data["offering_type"] = product_update.offering_type
    
    if product_update.duration is not None:
        update_data["duration"] = product_update.duration
    
    if product_update.service_category is not None:
        update_data["service_category"] = product_update.service_category
    
    if product_update.addons is not None:
        update_data["addons"] = product_update.addons
    
    if product_update.capacity is not None:
        update_data["capacity"] = product_update.capacity
    
    await db.products.update_one(
        {"_id": product_id},
        {"$set": update_data}
    )
    
    return {"status": "success", "message": "Product updated"}

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, user = Depends(get_current_user)):
    """Delete a product"""
    business_id = user.get("business_id", user["_id"])
    product = await db.products.find_one({"_id": product_id, "user_id": business_id})
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Delete image file
    if product.get("image_url"):
        filename = product["image_url"].split("/")[-1]
        ImageUploadHandler.delete_image(filename)
    
    # Delete from database
    await db.products.delete_one({"_id": product_id})
    
    return {"status": "success", "message": "Product deleted"}

@api_router.post("/products/{product_id}/send")
async def send_product_to_customer(
    product_id: str,
    customer_id: str = Query(...),
    use_buttons: bool = Query(True, description="Use interactive buttons (default: true)"),
    user = Depends(get_current_user)
):
    """Send a single product with image to customer via WhatsApp with interactive buttons"""
    
    business_id = user.get("business_id", user["_id"])
    product = await db.products.find_one({"_id": product_id, "user_id": business_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
    
    # Prepare product data with currency
    product_data = {
        **product,
        "currency": currency
    }
    
    # Send via WhatsApp API
    from whatsapp_service import get_whatsapp_service
    whatsapp_service = get_whatsapp_service(db)
    
    # Manual send from CRM: always send product card only (no action menu)
    # Action menus are for AI conversations where the customer can reply with numbers
    if use_buttons:
        try:
            result = await whatsapp_service.send_product_showcase(
                user_id=business_id,
                to_number=customer["phone_number"],
                product=product_data,
                send_buttons=False
            )
            # Save to db.messages so it appears in CRM chat history
            try:
                _images = product.get("images", [])
                _img_url = product.get("image_url")
                _media = _images[0] if _images else _img_url
                _price = product.get('price') or 0
                _caption = f"🌟 *{product['name']}*\n💰 {currency} {_price:,.0f}"
                _msg_id = str(uuid.uuid4())
                await db.messages.insert_one({
                    "_id": _msg_id,
                    "customer_id": customer_id,
                    "user_id": business_id,
                    "direction": "outgoing",
                    "content": _caption,
                    "message_type": "image" if _media else "text",
                    "image_url": _media,
                    "status": "sent",
                    "created_at": datetime.utcnow(),
                    "send_context": "product_send",
                })
                await db.customers.update_one(
                    {"_id": customer_id},
                    {"$set": {"last_message": _caption[:200], "last_contacted": datetime.utcnow()}}
                )
            except Exception as _save_err:
                logger.error(f"Failed to save product message to DB: {_save_err}")
        except Exception as e:
            logger.error(f"Error sending product with buttons: {e}")
            # Fallback to legacy method
            use_buttons = False
    
    # Legacy method (plain message with image)
    if not use_buttons:
        server_url = os.environ.get("SERVER_URL", "").rstrip("/")
        all_images = []
        seen = set()
        for img in list(product.get("images", [])):
            if img and img not in seen:
                seen.add(img)
                full = img if img.startswith("http") else (f"{server_url}{img}" if server_url else None)
                if full:
                    all_images.append(full)
        if not all_images:
            img = product.get("image_url")
            if img:
                full = img if img.startswith("http") else (f"{server_url}{img}" if server_url else None)
                if full:
                    all_images.append(full)
        
        stock_label = "✅ In Stock" if product.get("in_stock", True) else "❌ Out of Stock"
        desc = f"\n_{product.get('description', '')}_" if product.get("description") else ""
        price = product.get('price') or 0
        message_text = (
            f"*{product['name']}*\n"
            f"💰 {currency} {price:,.0f}\n"
            f"{stock_label}{desc}\n\n"
            f"👉 Reply *Yes* or *Order* to buy!"
        )
        
        result = None
        if len(all_images) > 1:
            for extra_img in all_images[:-1]:
                await whatsapp_service.send_message(
                    user_id=business_id,
                    to_number=customer["phone_number"],
                    message="",
                    customer_name=customer.get("name"),
                    media_url=extra_img,
                    send_context="product_send",
                )
        
        result = await whatsapp_service.send_message(
            user_id=business_id,
            to_number=customer["phone_number"],
            message=message_text,
            customer_name=customer.get("name"),
            media_url=all_images[-1] if all_images else None,
            send_context="product_send",
        )
    
    # Store as pending catalog so button clicks or "Yes"/"Order" auto-creates the order
    await db.pending_catalogs.update_one(
        {"customer_id": customer_id, "user_id": business_id},
        {"$set": {
            "products": [{"id": product["_id"], "name": product["name"], "price": product.get("price", 0), "index": 1}],
            "single_product": True,
            "action_context": "product",
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )
    
    return {
        "status": "success",
        "message_id": result.get("message_id") if isinstance(result, dict) else None,
        "customer_name": customer.get("name"),
        "method": "interactive_buttons" if use_buttons else "legacy"
    }

class SendCatalogRequest(BaseModel):
    customer_id: str
    product_ids: List[str]

class BroadcastCatalogRequest(BaseModel):
    product_ids: List[str]
    filter_type: str = "all"  # all, new, returning, vip, custom
    customer_ids: Optional[List[str]] = None  # for custom filter

@api_router.post("/products/send-catalog")
async def send_catalog_to_customer(
    request: SendCatalogRequest,
    use_list: bool = Query(True, description="Use interactive list (default: true)"),
    user = Depends(get_current_user)
):
    """Send multiple products as a catalog message to customer via WhatsApp"""
    
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": request.customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    products = []
    for pid in request.product_ids:  # No hard limit — pagination handles display
        p = await db.products.find_one({"_id": pid, "user_id": business_id})
        if p:
            products.append(p)
    
    if not products:
        raise HTTPException(status_code=400, detail="No valid products found")
    
    currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
    
    from whatsapp_service import get_whatsapp_service
    whatsapp_service = get_whatsapp_service(db)

    PAGE_SIZE = 8 if use_list else 5
    page_products = products[:PAGE_SIZE]
    has_more = len(products) > PAGE_SIZE

    # Add currency to products for this page
    products_with_currency = [{"currency": currency, **p} for p in page_products]
    
    # Try interactive list first
    result = None
    if use_list and len(page_products) > 1:
        try:
            result = await whatsapp_service.send_product_list(
                user_id=business_id,
                to_number=customer["phone_number"],
                title="Our Products",
                products=products_with_currency,
                category="Catalog",
                has_more=has_more,
                page_num=1
            )
            use_list = True
        except Exception as e:
            logger.error(f"Error sending product list: {e}")
            use_list = False
    else:
        use_list = False
    
    # Fallback to visual mode (send primary image for each product sequentially)
    if not use_list:
        server_url = os.environ.get("SERVER_URL", "").rstrip("/")
        for i, p in enumerate(page_products):
            stock_label = "✅ In Stock" if p.get("in_stock", True) else "❌ Out of Stock"
            desc = f"\n_{p.get('description', '')}_" if p.get("description") else ""
            price = p.get('price') or 0
            message_text = (
                f"*{i+1}. {p['name']}*\n"
                f"💰 {currency} {price:,.0f}\n"
                f"{stock_label}{desc}\n\n"
                f"👉 Reply *{i+1}* to select!"
            )
            
            # Select primary image
            primary_image = None
            if p.get("image_url"):
                primary_image = p.get("image_url")
            elif p.get("images") and len(p.get("images")) > 0:
                primary_image = p.get("images")[0]
                
            if primary_image and not primary_image.startswith("http") and server_url:
                primary_image = f"{server_url}{primary_image}"
                
            result = await whatsapp_service.send_message(
                user_id=business_id, to_number=customer["phone_number"],
                message=message_text, customer_name=customer.get("name"),
                media_url=primary_image, send_context="product_send",
            )
            
        if has_more:
            await whatsapp_service.send_message(
                user_id=business_id, to_number=customer["phone_number"],
                message=f"Reply *9* to see more products ➡️", customer_name=customer.get("name"),
                send_context="product_send",
            )
    
    # Store ALL product IDs for pagination, show first page indexed 1-8
    all_product_ids = [p["_id"] for p in products]
    await db.pending_catalogs.update_one(
        {"customer_id": request.customer_id, "user_id": business_id},
        {"$set": {
            "products": [{"id": p["_id"], "name": p["name"], "price": p.get("price", 0), "index": i}
                         for i, p in enumerate(page_products, 1)],
            "all_product_ids": all_product_ids,
            "page_offset": 0,
            "has_more": has_more,
            "action_context": "catalog_select",
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )
    
    return {
        "status": "success",
        "products_sent": len(page_products),
        "total_products": len(products),
        "has_more": has_more,
        "message_id": result.get("message_id") if isinstance(result, dict) else None,
        "method": "interactive_list" if use_list else "legacy"
    }

@api_router.post("/products/broadcast-catalog")
async def broadcast_catalog(
    request: BroadcastCatalogRequest,
    background_tasks: BackgroundTasks,
    user = Depends(get_current_user)
):
    """Broadcast a product catalog to multiple customers via WhatsApp"""

    business_id = user.get("business_id", user["_id"])
    logging.info(f"broadcast_catalog: user_id={user['_id']} business_id={business_id} product_ids={request.product_ids}")

    # Get products
    catalog_products = []
    for pid in request.product_ids[:10]:
        p = await db.products.find_one({"_id": pid})
        if p and p.get("user_id") == business_id:
            catalog_products.append(p)

    if not catalog_products:
        raise HTTPException(status_code=400, detail="No valid products found")

    # Get target customers based on filter
    query = {"user_id": business_id}
    if request.filter_type == "custom" and request.customer_ids:
        query["_id"] = {"$in": request.customer_ids}
    elif request.filter_type == "new":
        query["tags"] = "New"
    elif request.filter_type == "returning":
        query["tags"] = "Returning"
    elif request.filter_type == "vip":
        query["tags"] = "VIP"

    target_customers = await db.customers.find(query).to_list(None)
    if not target_customers:
        raise HTTPException(status_code=400, detail="No customers match this filter")

    currency = user.get("currency") or user.get("settings", {}).get("currency", "USD")
    business_name = user.get("business_name", "Our Store")
    server_url = os.environ.get("SERVER_URL", "").rstrip("/")

    def _resolve_img(img: str) -> Optional[str]:
        if not img:
            return None
        if img.startswith("http://") or img.startswith("https://"):
            return img
        return f"{server_url}{img}" if server_url else None

    # Build per-product messages
    product_messages = []
    for i, p in enumerate(catalog_products, 1):
        desc = f"\n_{p['description']}_" if p.get("description") else ""
        caption = (
            f"🛍️ *{business_name}*\n\n"
            f"*{i}. {p['name']}*{desc}\n"
            f"💰 {currency} {p.get('price', 0):,.0f}\n\n"
            f"👉 Reply *{i}* to order!"
        )
        imgs = p.get("images") or ([p["image_url"]] if p.get("image_url") else [])
        resolved_imgs = [u for u in (_resolve_img(u) for u in imgs) if u]
        product_messages.append({"caption": caption, "images": resolved_imgs})

    # Summary text for broadcast log
    summary_lines = [f"🛍️ *{business_name}* Catalog\n"]
    for i, p in enumerate(catalog_products, 1):
        summary_lines.append(f"*{i}.* {p['name']} — {currency} {p.get('price', 0):,.0f}")
    message_text = "\n".join(summary_lines)
    first_image = product_messages[0]["images"][0] if product_messages and product_messages[0]["images"] else None
    product_index_list = [{"id": p["_id"], "name": p["name"], "price": p.get("price", 0), "index": i} for i, p in enumerate(catalog_products, 1)]

    # Insert broadcast record immediately as "sending"
    broadcast_id = str(uuid.uuid4())
    await db.broadcasts.insert_one({
        "_id": broadcast_id,
        "user_id": business_id,
        "message": message_text,
        "filter_type": request.filter_type,
        "recipients_count": len(target_customers),
        "sent_count": 0,
        "status": "sending",
        "is_catalog": True,
        "product_ids": request.product_ids,
        "image_url": first_image,
        "created_at": datetime.utcnow()
    })

    async def _send_catalog_bg():
        from whatsapp_service import get_whatsapp_service
        whatsapp_service = get_whatsapp_service(db)
        sent_count = 0
        for customer in target_customers:
            try:
                for pm in product_messages:
                    if pm["images"]:
                        # Extra images first — no caption
                        for extra_img in pm["images"][:-1]:
                            await whatsapp_service.send_message(
                                user_id=business_id,
                                to_number=customer["phone_number"],
                                message="",
                                customer_name=customer.get("name"),
                                media_url=extra_img,
                                send_context="broadcast",
                            )
                        # Last image carries the caption
                        await whatsapp_service.send_message(
                            user_id=business_id,
                            to_number=customer["phone_number"],
                            message=pm["caption"],
                            customer_name=customer.get("name"),
                            media_url=pm["images"][-1],
                            send_context="broadcast",
                        )
                    else:
                        await whatsapp_service.send_message(
                            user_id=business_id,
                            to_number=customer["phone_number"],
                            message=pm["caption"],
                            customer_name=customer.get("name"),
                            send_context="broadcast",
                        )
                await db.pending_catalogs.update_one(
                    {"customer_id": customer["_id"], "user_id": business_id},
                    {"$set": {"products": product_index_list, "action_context": "catalog_select", "created_at": datetime.utcnow()}},
                    upsert=True
                )
                sent_count += 1
            except Exception as e:
                logging.error(f"Failed to send catalog to {customer.get('name')}: {e}")
            from whatsapp_service import BROADCAST_DELAY
            import random as _rnd
            await asyncio.sleep(_rnd.uniform(*BROADCAST_DELAY))

        await db.broadcasts.update_one(
            {"_id": broadcast_id},
            {"$set": {"sent_count": sent_count, "status": "completed"}}
        )

    background_tasks.add_task(_send_catalog_bg)

    return {
        "status": "sending",
        "broadcast_id": broadcast_id,
        "recipients_count": len(target_customers),
        "sent_count": 0,
        "products_in_catalog": len(catalog_products)
    }

# ============ MAIN APP SETUP ============

@api_router.get("/health")
async def health_check():
    return {"status": "ok"}

@api_router.post("/push-token")
async def register_push_token(
    payload: dict,
    user = Depends(get_current_user)
):
    """Save Expo push token for the business owner so they receive order notifications"""
    token = payload.get("token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    # Save to expo_push_token (single) AND push_tokens (array) for compatibility
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"expo_push_token": token, "push_token_updated": datetime.utcnow()},
            "$addToSet": {"push_tokens": token},
        }
    )
    return {"status": "ok"}

@api_router.get("/debug/evolution")
async def debug_evolution():
    import os, httpx
    evo_url = os.environ.get("EVOLUTION_API_URL", "NOT_SET")
    evo_key = os.environ.get("EVOLUTION_API_KEY", "NOT_SET")
    result = {"evolution_url": evo_url, "evolution_key_set": evo_key != "NOT_SET" and evo_key != ""}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{evo_url.rstrip('/')}/", headers={"apikey": evo_key})
            result["ping_status"] = resp.status_code
            result["ping_body"] = resp.text[:200]
    except Exception as e:
        result["ping_error"] = str(e)
    return result

@api_router.get("/debug/test-buttons")
@api_router.post("/debug/test-buttons")
async def debug_test_buttons(
    phone: str = Query(..., description="Phone number to send test buttons to"),
    user_phone: str = Query(..., description="Your registered phone number (for lookup)")
):
    """
    Diagnostic: fire sendButtons with 3 different payload formats + sendPoll + sendList.
    Returns raw Evolution API status code + response body for each attempt.
    """
    import httpx as _httpx
    
    # Find user by their registered phone number
    user_doc = await db.users.find_one({"phone_number": user_phone.strip()})
    if not user_doc:
        return {"error": f"No user found with phone number {user_phone}. Use your registered business phone."}
    
    ws = get_whatsapp_service(db)
    instance = user_doc.get("whatsapp", {}).get("instance_name", "")
    base = ws.base_url.rstrip("/")
    hdrs = ws._headers()
    num = phone.strip().lstrip("+")
    if not num.startswith("+"):
        num = f"+{num}"

    results = {}
    async with _httpx.AsyncClient(timeout=15) as c:

        # Format A — nested buttonMessage wrapper (user-suggested format)
        r = await c.post(f"{base}/message/sendButtons/{instance}", headers=hdrs, json={
            "number": num,
            "buttonMessage": {
                "title": "Test A",
                "description": "Format A: nested buttonMessage",
                "footerText": "tap a button",
                "buttons": [
                    {"type": "reply", "displayText": "Button 1", "id": "btn_1"},
                    {"type": "reply", "displayText": "Button 2", "id": "btn_2"},
                ],
            },
        })
        results["A_nested_buttonMessage"] = {"status": r.status_code, "body": r.text[:400]}

        await asyncio.sleep(0.5)

        # Format B — flat (Evolution API v1 style)
        r = await c.post(f"{base}/message/sendButtons/{instance}", headers=hdrs, json={
            "number": num,
            "title": "Test B",
            "description": "Format B: flat v1 style",
            "footerText": "tap a button",
            "buttons": [
                {"buttonId": "btn_1", "buttonText": {"displayText": "Button 1"}, "type": 1},
                {"buttonId": "btn_2", "buttonText": {"displayText": "Button 2"}, "type": 1},
            ],
        })
        results["B_flat_v1"] = {"status": r.status_code, "body": r.text[:400]}

        await asyncio.sleep(0.5)

        # Format C — flat v2 style (id/displayText/title)
        r = await c.post(f"{base}/message/sendButtons/{instance}", headers=hdrs, json={
            "number": num,
            "title": "Test C",
            "description": "Format C: flat v2 style",
            "footer": "tap a button",
            "buttons": [
                {"id": "btn_1", "displayText": "Button 1", "title": "Button 1"},
                {"id": "btn_2", "displayText": "Button 2", "title": "Button 2"},
            ],
        })
        results["C_flat_v2"] = {"status": r.status_code, "body": r.text[:400]}

        await asyncio.sleep(0.5)

        # sendPoll — for comparison
        r = await c.post(f"{base}/message/sendPoll/{instance}", headers=hdrs, json={
            "number": num,
            "name": "Test Poll",
            "selectableCount": 1,
            "values": ["Option 1", "Option 2", "Option 3"],
        })
        results["D_sendPoll"] = {"status": r.status_code, "body": r.text[:400]}

        await asyncio.sleep(0.5)

        # sendList E1 — flat with sections (correct v2 format)
        r = await c.post(f"{base}/message/sendList/{instance}", headers=hdrs, json={
            "number": num,
            "title": "Test E1",
            "description": "Pick an action",
            "buttonText": "View Options",
            "footer": "tap to pick",
            "sections": [{"title": "Actions", "rows": [
                {"title": "Add to Cart", "description": "Save for later", "rowId": "cart_test"},
                {"title": "Order Now", "description": "Buy immediately", "rowId": "order_test"},
                {"title": "Ask Question", "description": "Chat with us", "rowId": "ask_test"},
            ]}],
        })
        results["E1_sendList_flat_sections"] = {"status": r.status_code, "body": r.text[:400]}
        await asyncio.sleep(0.5)
        # sendList E2 — nested listMessage wrapper
        r = await c.post(f"{base}/message/sendList/{instance}", headers=hdrs, json={
            "number": num,
            "listMessage": {
                "title": "Test E2",
                "description": "Pick an action",
                "buttonText": "View Options",
                "footerText": "tap to pick",
                "sections": [{"title": "Actions", "rows": [
                    {"title": "Add to Cart", "description": "Save for later", "rowId": "cart_test"},
                    {"title": "Order Now", "description": "Buy immediately", "rowId": "order_test"},
                ]}],
            },
        })
        results["E2_sendList_nested"] = {"status": r.status_code, "body": r.text[:400]}

    return {"instance": instance, "base_url": base, "results": results}


app.include_router(api_router)

# ── No-auth diagnostic endpoint (registered directly on app, bypasses HTTPBearer) ──
@app.get("/diag/test-buttons")
async def diag_test_buttons(
    phone: str = Query(...),
    user_phone: str = Query(...)
):
    import httpx as _httpx
    _up = user_phone.strip().lstrip("+")
    user_doc = (
        await db.users.find_one({"phone_number": user_phone.strip()}) or
        await db.users.find_one({"phone_number": f"+{_up}"}) or
        await db.users.find_one({"phone_number": _up})
    )
    if not user_doc:
        # Return all stored phone numbers to help diagnose the mismatch
        all_phones = await db.users.distinct("phone_number")
        return {"error": f"No user found with phone_number={user_phone}", "stored_phone_numbers": all_phones}
    ws = get_whatsapp_service(db)
    instance = user_doc.get("whatsapp", {}).get("instance_name", "")
    base = ws.base_url.rstrip("/")
    hdrs = ws._headers()
    num = phone.strip()
    if not num.startswith("+"):
        num = f"+{num}"
    results = {}
    async with _httpx.AsyncClient(timeout=15) as c:
        # sendButtons: type=reply + displayText + id
        r = await c.post(f"{base}/message/sendButtons/{instance}", headers=hdrs, json={
            "number": num,
            "title": "What would you like to do?",
            "description": "Test product",
            "footer": "Tap a button to continue",
            "buttons": [
                {"type": "reply", "displayText": "🛒 Add to Cart", "id": "cart_test"},
                {"type": "reply", "displayText": "✅ Order Now",   "id": "order_test"},
                {"type": "reply", "displayText": "💬 Ask Question","id": "ask_test"},
            ],
        })
        results["sendButtons_reply"] = {"status": r.status_code, "body": r.text[:500]}
        await asyncio.sleep(0.8)
        # sendList: footerText (not footer) + buttonText + sections
        r = await c.post(f"{base}/message/sendList/{instance}", headers=hdrs, json={
            "number": num,
            "title": "What would you like to do?",
            "description": "Choose an option",
            "buttonText": "View Options",
            "footerText": "Tap to select",
            "sections": [{"title": "Actions", "rows": [
                {"title": "🛒 Add to Cart", "description": "Save for later", "rowId": "cart_test"},
                {"title": "✅ Order Now",   "description": "Buy immediately", "rowId": "order_test"},
                {"title": "💬 Ask Question","description": "Chat with us",    "rowId": "ask_test"},
            ]}],
        })
        results["sendList_footerText"] = {"status": r.status_code, "body": r.text[:500]}
    return {"instance": instance, "base_url": base, "results": results}

@app.get("/diag/test-flow")
async def diag_test_flow(user_phone: str = Query(...)):
    """Comprehensive end-to-end test of the entire order/cart/button flow.
    Tests DB writes, button pattern matching, order+sale creation, cart ops, push tokens.
    All test data is cleaned up after the test."""
    import traceback
    results = {}
    _test_ids = []  # track IDs for cleanup

    try:
        # 1. Find user
        _up = user_phone.strip().lstrip("+")
        user_doc = (
            await db.users.find_one({"phone_number": user_phone.strip()}) or
            await db.users.find_one({"phone_number": f"+{_up}"}) or
            await db.users.find_one({"phone_number": _up})
        )
        if not user_doc:
            all_phones = await db.users.distinct("phone_number")
            return {"error": f"No user found", "stored_phones": all_phones}
        _biz_id = user_doc.get("business_id", user_doc["_id"])
        results["1_user_found"] = {"status": "✅", "user_id": user_doc["_id"], "business_id": _biz_id}

        # 2. Test button pattern matching
        button_patterns = {
            "order_": "order", "buy_": "order", "cart_": "add_to_cart",
            "checkout_cart": "checkout", "continue_shopping": "continue",
            "details_": "details", "select_": "select",
            "ask_": "ask", "question_": "ask", "share_": "share",
        }
        test_cases = {
            "order_abc123": ("order", "abc123"),
            "cart_xyz789": ("add_to_cart", "xyz789"),
            "checkout_cart": ("checkout", ""),
            "continue_shopping": ("continue", ""),
            "question_prod1": ("ask", "prod1"),
        }
        pattern_results = {}
        for body, (expected_action, expected_pid) in test_cases.items():
            action = None
            pid = None
            for prefix, act in button_patterns.items():
                if body.startswith(prefix):
                    action = act
                    pid = body.replace(prefix, "")
                    break
            ok = action == expected_action and pid == expected_pid
            can_handle = bool(action and (pid or action in ("checkout", "continue")))
            pattern_results[body] = {"action": action, "product_id": pid, "will_handle": can_handle, "correct": ok}
        all_patterns_ok = all(r["correct"] and r["will_handle"] for r in pattern_results.values())
        results["2_button_patterns"] = {"status": "✅" if all_patterns_ok else "❌", "tests": pattern_results}

        # 3. Test order creation
        _test_order_id = f"_test_{uuid.uuid4()}"
        _test_ids.append(("orders", _test_order_id))
        _now = datetime.utcnow()
        await db.orders.insert_one({
            "_id": _test_order_id,
            "user_id": _biz_id,
            "customer_id": "test_customer",
            "customer_name": "Test Customer",
            "customer_phone": "+0000000000",
            "product": "Test Product",
            "product_id": "test_prod",
            "items": [{"product_id": "test_prod", "product_name": "Test Product", "quantity": 1, "price": 100}],
            "quantity": 1, "price": 100, "total_amount": 100, "total": 100,
            "status": "pending", "created_at": _now, "source": "diag_test",
        })
        order_check = await db.orders.find_one({"_id": _test_order_id})
        order_fields = ["product", "total_amount", "customer_name", "customer_phone", "items", "source"]
        missing_fields = [f for f in order_fields if f not in (order_check or {})]
        results["3_order_creation"] = {
            "status": "✅" if order_check and not missing_fields else "❌",
            "found": bool(order_check),
            "missing_fields": missing_fields or "none",
        }

        # 4. Test sale creation
        _test_sale_id = f"_test_{uuid.uuid4()}"
        _test_ids.append(("sales", _test_sale_id))
        await db.sales.insert_one({
            "_id": _test_sale_id,
            "user_id": _biz_id, "customer_id": "test_customer",
            "customer_name": "Test Customer", "product": "Test Product",
            "amount": 100, "quantity": 1, "status": "completed",
            "created_at": _now, "source": "diag_test",
        })
        sale_check = await db.sales.find_one({"_id": _test_sale_id})
        results["4_sale_creation"] = {"status": "✅" if sale_check else "❌", "found": bool(sale_check)}

        # 5. Test cart operations
        _test_cart_id = f"_test_{uuid.uuid4()}"
        _test_ids.append(("carts", _test_cart_id))
        await db.carts.update_one(
            {"_id": _test_cart_id},
            {
                "$push": {"items": {"product_id": "test_prod", "product_name": "Test Product", "price": 100, "quantity": 1}},
                "$set": {"customer_id": "test_customer", "user_id": _biz_id, "status": "active", "updated_at": _now},
            },
            upsert=True,
        )
        cart_check = await db.carts.find_one({"_id": _test_cart_id})
        cart_items = (cart_check or {}).get("items", [])
        results["5_cart_operations"] = {
            "status": "✅" if cart_check and len(cart_items) == 1 else "❌",
            "items_count": len(cart_items),
        }

        # 6. Test push token storage
        _old_tokens = user_doc.get("push_tokens", [])
        _old_expo = user_doc.get("expo_push_token", "")
        results["6_push_token"] = {
            "status": "✅" if _old_tokens or _old_expo else "⚠️ No token registered yet (open the app first)",
            "expo_push_token": bool(_old_expo),
            "push_tokens_count": len(_old_tokens),
        }

        # 7. Test Evolution API connectivity
        ws = get_whatsapp_service(db)
        instance = user_doc.get("whatsapp", {}).get("instance_name", "")
        evo_ok = False
        if instance:
            try:
                import httpx as _httpx
                async with _httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(f"{ws.base_url.rstrip('/')}/instance/connectionState/{instance}", headers=ws._headers())
                    evo_ok = r.status_code in (200, 201)
                    results["7_evolution_api"] = {"status": "✅" if evo_ok else "❌", "http": r.status_code, "body": r.text[:200]}
            except Exception as e:
                results["7_evolution_api"] = {"status": "❌", "error": str(e)}
        else:
            results["7_evolution_api"] = {"status": "❌", "error": "No WhatsApp instance found"}

        # 8. Test WhatsApp sendButtons (dry check — use diag/test-buttons to actually send)
        results["8_sendButtons_format"] = {
            "status": "✅",
            "format": "type=reply, displayText, id",
            "confirmed_201": "Use /diag/test-buttons?phone=X&user_phone=Y to live-test",
        }

        # 9. Check products exist
        product_count = await db.products.count_documents({"user_id": _biz_id})
        results["9_products"] = {
            "status": "✅" if product_count > 0 else "⚠️ No products — upload some first",
            "count": product_count,
        }

        # 10. Check customers exist
        customer_count = await db.customers.count_documents({"user_id": user_doc["_id"]})
        results["10_customers"] = {
            "status": "✅" if customer_count > 0 else "⚠️ No customers yet",
            "count": customer_count,
        }

        # Summary
        statuses = [v.get("status", "") for v in results.values() if isinstance(v, dict)]
        fails = sum(1 for s in statuses if "❌" in s)
        warns = sum(1 for s in statuses if "⚠️" in s)
        passes = sum(1 for s in statuses if "✅" in s)
        results["_summary"] = {
            "passed": passes, "warnings": warns, "failed": fails,
            "verdict": "ALL GOOD ✅" if fails == 0 else f"{fails} ISSUE(S) FOUND ❌",
        }

    except Exception as e:
        results["_error"] = {"message": str(e), "traceback": traceback.format_exc()[-500:]}

    # Cleanup test data
    for collection, test_id in _test_ids:
        try:
            await getattr(db, collection).delete_one({"_id": test_id})
        except Exception:
            pass

    return results

# Serve static files (product images)
app.mount("/uploads", StaticFiles(directory=str(ROOT_DIR / "uploads")), name="uploads")
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "static")), name="static")

# Startup event
@app.on_event("startup")
async def startup_tasks():
    """Run startup tasks"""

    # ---- P0: Ensure required folders exist ----
    try:
        static_dir = ROOT_DIR / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        
        # Create whatsapp_media folder for downloaded images
        whatsapp_media_dir = ROOT_DIR / "uploads" / "whatsapp_media"
        whatsapp_media_dir.mkdir(parents=True, exist_ok=True)
        logging.info("Created uploads/whatsapp_media directory")
        logging.info(f"Static folder ensured at: {static_dir}")
        
        uploads_dir = ROOT_DIR / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Uploads folder ensured at: {uploads_dir}")
    except Exception as e:
        logging.error(f"Failed to create folders: {e}")

    # ---- P1: Ensure database indexes ----
    try:
        logging.info("Ensuring database indexes...")

        # Users
        await db.users.create_index("phone_number", unique=True)

        # Customers — most queried collection
        await db.customers.create_index("user_id")
        await db.customers.create_index([("user_id", 1), ("phone_number", 1)], unique=True)
        await db.customers.create_index([("user_id", 1), ("last_contacted", 1)])
        await db.customers.create_index([("user_id", 1), ("tags", 1)])
        await db.customers.create_index([("user_id", 1), ("created_at", -1)])

        # Messages
        await db.messages.create_index("user_id")
        await db.messages.create_index("customer_id")
        await db.messages.create_index([("customer_id", 1), ("created_at", -1)])
        await db.messages.create_index([("user_id", 1), ("created_at", -1)])

        # Sales
        await db.sales.create_index("user_id")
        await db.sales.create_index("customer_id")
        await db.sales.create_index([("user_id", 1), ("created_at", -1)])

        # Follow-ups
        await db.followups.create_index("user_id")
        await db.followups.create_index([("user_id", 1), ("status", 1)])
        await db.followups.create_index([("user_id", 1), ("reminder_date", 1)])
        await db.followups.create_index("customer_id")

        # Orders
        await db.orders.create_index("user_id")
        await db.orders.create_index("customer_id")

        # Expenses
        await db.expenses.create_index([("user_id", 1), ("created_at", -1)])

        # Products
        await db.products.create_index("user_id")

        # Broadcasts
        await db.broadcasts.create_index([("user_id", 1), ("created_at", -1)])

        # Customer analysis (AI insights)
        await db.customer_analysis.create_index([("user_id", 1), ("analysis_date", -1)])
        await db.customer_analysis.create_index("customer_id")

        # Pending classifications
        await db.pending_classifications.create_index("user_id")

        # Transactions (IAP)
        await db.transactions.create_index("user_id")
        await db.transactions.create_index("purchase_token", unique=True, sparse=True)

        # WhatsApp auth sessions (TTL: auto-delete after 10 minutes)
        await db.wa_auth_sessions.create_index("expires", expireAfterSeconds=600)

        # Pending catalogs
        await db.pending_catalogs.create_index([("customer_id", 1), ("user_id", 1)])

        # Team members
        await db.team_members.create_index([("business_id", 1), ("status", 1)])
        await db.team_members.create_index("phone_number")
        await db.team_members.create_index([("business_id", 1), ("phone_number", 1)])

        # Conversation memory (AI context per customer per user)
        await db.conversation_memory.create_index([("customer_id", 1), ("user_id", 1)])


        # Conversation assignments
        await db.conversation_assignments.create_index([("business_id", 1), ("customer_id", 1)], unique=True)
        await db.conversation_assignments.create_index([("business_id", 1), ("assigned_to", 1)])

        # Activity logs
        await db.activity_logs.create_index([("business_id", 1), ("timestamp", -1)])
        await db.activity_logs.create_index([("business_id", 1), ("user_id", 1), ("timestamp", -1)])
        await db.activity_logs.create_index([("business_id", 1), ("entity_type", 1), ("entity_id", 1)])

        logging.info("Database indexes ensured successfully")
    except Exception as e:
        logging.error(f"Failed to create indexes: {e}")

    # Purge contaminated conversation memory (one-time cleanup)
    try:
        purged = await db.conversation_memory.delete_many({})
        if purged.deleted_count > 0:
            logging.info(f"Purged {purged.deleted_count} old conversation memory entries")
    except Exception as e:
        logging.error(f"Failed to purge conversation memory: {e}")

    # Recalculate customer totals from sales (Self-Healing)
    try:
        logging.info("Starting customer totals recalculation...")
        
        # 1. Reset all totals to 0 first (safety)
        await db.customers.update_many(
            {}, 
            {"$set": {"total_spent": 0.0, "purchase_count": 0}}
        )
        
        # 2. Aggregate sales data directly from database
        pipeline = [
            {
                "$group": {
                    "_id": "$customer_id",
                    "total_spent": {"$sum": "$amount"},
                    "count": {"$sum": 1},
                    "last_sale_date": {"$max": "$created_at"}
                }
            }
        ]
        
        sales_stats = await db.sales.aggregate(pipeline).to_list(None)
        
        # 3. Update each customer with their real totals
        updates = 0
        for stat in sales_stats:
            if stat["_id"]:
                await db.customers.update_one(
                    {"_id": stat["_id"]},
                    {
                        "$set": {
                            "total_spent": stat["total_spent"], 
                            "purchase_count": stat["count"],
                            "last_contacted": stat["last_sale_date"]
                        }
                    }
                )
                updates += 1
                
        logging.info(f"Recalculated totals for {updates} customers")
        
    except Exception as e:
        logging.error(f"Failed to recalculate totals: {e}")
    
    # Start daily notification scheduler
    try:
        logging.info("Starting timezone-aware notification scheduler...")
        # Scheduler runs every hour and checks each user's local timezone
        await start_daily_scheduler(db)
        logging.info("Scheduler started - notifications sent based on user timezone")
    except Exception as e:
        logging.error(f"Failed to start scheduler: {e}")
    
    # Start daily pulse scheduler
    try:
        import asyncio
        logging.info("Starting daily pulse scheduler...")
        asyncio.create_task(run_daily_pulse_scheduler())
        logging.info("Daily pulse scheduler started")
    except Exception as e:
        logging.error(f"Failed to start daily pulse scheduler: {e}")
    
    # Start digest notification scheduler (8 AM and 3 PM)
    try:
        from scheduler import start_scheduler
        logging.info("Starting digest notification scheduler...")
        start_scheduler(db)
        logging.info("Digest scheduler started - notifications at 8 AM and 3 PM EAT")
    except Exception as e:
        logging.error(f"Failed to start digest scheduler: {e}")

    # Keep Evolution API alive (Render free-tier sleeps after 15 min inactivity)
    async def _evolution_keepalive():
        import httpx, os
        evo_url = os.environ.get("EVOLUTION_API_URL", "").rstrip("/")
        evo_key = os.environ.get("EVOLUTION_API_KEY", "")
        if not evo_url:
            return
        while True:
            await asyncio.sleep(4 * 60)  # every 4 minutes
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    await c.get(f"{evo_url}/", headers={"apikey": evo_key})
                    logging.debug("Evolution API keep-alive ping sent")
            except Exception as e:
                logging.debug(f"Evolution API keep-alive ping failed: {e}")

    try:
        asyncio.create_task(_evolution_keepalive())
        logging.info("Evolution API keep-alive task started")
    except Exception as e:
        logging.error(f"Failed to start Evolution API keep-alive: {e}")

    # Start booking reminder scheduler
    try:
        asyncio.create_task(run_booking_reminder_scheduler())
        logging.info("Booking reminder scheduler started (24h + 1h reminders)")
    except Exception as e:
        logging.error(f"Failed to start booking reminder scheduler: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

import os
import sys
from pathlib import Path
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

from fastapi import FastAPI, APIRouter, HTTPException, Depends, BackgroundTasks, Request, Query, Response
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
log_file = ROOT_DIR.parent / "server.log"
_log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_file_handler = _RotatingFileHandler(str(log_file), maxBytes=10*1024*1024, backupCount=3, encoding='utf-8')
_file_handler.setFormatter(_log_formatter)
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_log_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _stream_handler])
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Any
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



from bson import ObjectId as _ObjectId
from redis_client import (
    cache_get, cache_set, cache_delete, cache_delete_pattern,
    enqueue_job,
    key_tenant_settings, key_plan_limits, key_dashboard, key_products,
    QUEUE_BROADCAST, QUEUE_RECEIPT,
    TTL_TENANT_SETTINGS, TTL_PLAN_LIMITS, TTL_DASHBOARD, TTL_PRODUCTS,
)

# Anti-duplicate auto-reply guard: tracks evo_message_id to prevent double replies
# Evolution API often fires messages.upsert webhook multiple times for the same message
import asyncio as _aio
_AUTO_REPLY_DEDUP_TTL = 120  # seconds — prevents duplicate processing of same Evolution API message ID
_OWNER_ATTENTION_TTL = 900   # 15 minutes

# WhatsApp safe send delays (seconds) — avoids spam detection + rate limits
_WA_DELAY_BETWEEN_MSGS  = 1.2   # between text messages in same reply
_WA_DELAY_BETWEEN_IMGS  = 1.5   # between images (heavier, more suspicious)
_WA_GALLERY_MAX         = 8     # max products in gallery before capping

# In-memory fallbacks (used when Redis is unavailable / single-instance mode)
_auto_reply_dedup: dict = {}
_auto_reply_lock = _aio.Lock()
_last_auto_reply_sent: dict = {}
_owner_last_manual_reply: dict = {}

# ── Redis-backed helpers (cross-instance safe) ────────────────────────────────

async def _dedup_check_and_set(key: str, ttl: int = _AUTO_REPLY_DEDUP_TTL) -> bool:
    """Return True if this is a NEW key (not a duplicate). False = already seen."""
    from redis_client import get_redis
    r = await get_redis()
    if r:
        try:
            # SET NX EX is atomic — returns True if key was newly set
            return bool(await r.set(f"dedup:{key}", "1", nx=True, ex=ttl))
        except Exception as e:
            logging.warning(f"[Redis] dedup_check_and_set error: {e}")
    # Fallback: in-memory (single-instance only)
    global _auto_reply_dedup
    import time as _t
    now = _t.time()
    async with _auto_reply_lock:
        _auto_reply_dedup = {k: v for k, v in _auto_reply_dedup.items() if now - v <= ttl}
        if key in _auto_reply_dedup:
            return False
        _auto_reply_dedup[key] = now
    return True

_ts_fallback: dict = {}  # in-memory fallback for _redis_set_ts / _redis_get_ts

async def _redis_set_ts(key: str, ttl: int) -> None:
    """Store current timestamp under key with TTL. Used for cooldown tracking."""
    from redis_client import get_redis
    import time as _t
    r = await get_redis()
    if r:
        try:
            await r.setex(f"ts:{key}", ttl, str(_t.time()))
            return
        except Exception as e:
            logging.warning(f"[Redis] _redis_set_ts error: {e}")
    # Fallback: in-memory (single-instance only)
    import time as _t2
    _ts_fallback[key] = _t2.time()

async def _redis_get_ts(key: str) -> float:
    """Return stored timestamp for key, or 0.0 if not found."""
    from redis_client import get_redis
    r = await get_redis()
    if r:
        try:
            val = await r.get(f"ts:{key}")
            return float(val) if val else 0.0
        except Exception as e:
            logging.warning(f"[Redis] _redis_get_ts error: {e}")
    return _ts_fallback.get(key, 0.0)

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
from agents.payment_verifier import PaymentScreenshotVerifier
# ====================

def normalize_url(u):
    """Normalize media URLs for Docker/local access."""
    import re as _re
    if not u:
        return u
    if u.startswith('/'):
        base = os.environ.get('PUBLIC_BASE_URL') or os.environ.get('WEBHOOK_BASE_URL') or 'http://host.docker.internal:8000'
        return f"{base.rstrip('/')}{u}"
    if u.startswith('http://localhost:'):
        return u.replace('http://localhost:', 'http://host.docker.internal:')
    if u.startswith('http://127.0.0.1:'):
        return u.replace('http://127.0.0.1:', 'http://host.docker.internal:')
    # Replace any LAN/private IP (10.x, 192.168.x, 172.x) with host.docker.internal
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
    # Promote contacts that already have reminders to is_customer=True
    try:
        contacts_with_reminders = await db.followups.distinct("customer_id")
        if contacts_with_reminders:
            r3 = await db.customers.update_many(
                {"_id": {"$in": contacts_with_reminders}, "is_customer": {"$ne": True}},
                {"$set": {"is_customer": True}}
            )
            logging.info(f"[Migration] Promoted {r3.modified_count} contacts with reminders to customers")
    except Exception as e:
        logging.warning(f"[Migration] Reminder-based promotion failed: {e}")
    # Start automation scheduler in background
    import asyncio
    asyncio.create_task(run_automation_scheduler())
    # Fix fallback names + backfill last_owner_reply on startup
    async def _startup_tasks():
        await asyncio.sleep(30)
        await _backfill_all_users_names()
        await _backfill_last_owner_reply()
    asyncio.create_task(_startup_tasks())

async def _backfill_last_owner_reply():
    """Populate last_owner_reply from outgoing messages for all customers that don't have it yet."""
    try:
        customers = await db.customers.find(
            {"last_owner_reply": {"$exists": False}}
        ).to_list(None)
        updated = 0
        for c in customers:
            last_out = await db.messages.find_one(
                {"customer_id": c["_id"], "direction": "outgoing"},
                sort=[("created_at", -1)]
            )
            await db.customers.update_one(
                {"_id": c["_id"]},
                {"$set": {"last_owner_reply": last_out["created_at"] if last_out else None}}
            )
            updated += 1
        logging.info(f"[Migration] last_owner_reply backfilled for {updated} customers")
    except Exception as e:
        logging.warning(f"[Migration] last_owner_reply backfill failed: {e}")

async def run_automation_scheduler():
    """Runs every hour — executes due broadcast automations (auto follow-up & recurring)"""
    import asyncio
    await asyncio.sleep(10)  # brief delay to let server finish starting
    run_count = 0
    while True:
        try:
            await execute_broadcast_automations()
        except Exception as e:
            logging.error(f"Automation scheduler error: {e}")
        # Run name backfill every 6 hours to fix Customer/Contact XXXX names
        if run_count % 6 == 0:
            try:
                await _backfill_all_users_names()
            except Exception as e:
                logging.error(f"Name backfill scheduler error: {e}")
        run_count += 1
        await asyncio.sleep(3600)  # check every hour

async def _backfill_all_users_names():
    """Fix fallback names (Customer XXXX / Contact XXXX / raw phone) for all users"""
    from whatsapp_service import get_whatsapp_service, EVOLUTION_API_URL, EVOLUTION_API_KEY
    import httpx as _httpx, re as _re
    users = await db.users.find(
        {"whatsapp.instance_name": {"$exists": True, "$ne": ""}},
        {"_id": 1, "whatsapp": 1}
    ).to_list(None)
    for u in users:
        try:
            uid = u["_id"]
            instance_name = u.get("whatsapp", {}).get("instance_name")
            if not instance_name:
                continue
            base_url = EVOLUTION_API_URL.rstrip("/")
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            evo_names = {}
            async with _httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{base_url}/chat/findContacts/{instance_name}",
                    headers=headers, json={"where": {}},
                )
                if resp.status_code == 200:
                    contacts = resp.json()
                    if not isinstance(contacts, list):
                        contacts = contacts.get("contacts", contacts.get("data", []))
                    for c in contacts:
                        jid = c.get("remoteJid", "")
                        name = c.get("pushName") or c.get("name") or c.get("notify") or ""
                        if "@s.whatsapp.net" in jid and name:
                            digits = jid.replace("@s.whatsapp.net", "").strip()
                            evo_names[digits] = name
            if not evo_names:
                continue
            fallback_customers = await db.customers.find({
                "user_id": uid,
                "$or": [
                    {"name": {"$regex": "^(Contact|Customer)\\s+[0-9]"}},
                    {"name": {"$regex": "^[+]?[0-9]"}},
                    {"name": ""},
                    {"name": None},
                ]
            }, {"_id": 1, "phone_number": 1, "name": 1}).to_list(None)
            updated = 0
            for cust in fallback_customers:
                raw_phone = cust.get("phone_number", "")
                digits = raw_phone.lstrip("+").replace(" ", "").replace("-", "")
                new_name = evo_names.get(digits, "")
                if not new_name:
                    msg = await db.messages.find_one(
                        {"customer_id": cust["_id"], "user_id": uid,
                         "push_name": {"$exists": True, "$ne": ""}},
                        sort=[("created_at", -1)]
                    )
                    if msg:
                        new_name = msg.get("push_name", "")
                if new_name and not _re.match(r'^(Contact|Customer)\s+\d+$', new_name):
                    await db.customers.update_one(
                        {"_id": cust["_id"]}, {"$set": {"name": new_name}}
                    )
                    updated += 1
            if updated:
                logging.info(f"[NameBackfill] Updated {updated} names for user {uid}")
        except Exception as e:
            logging.warning(f"[NameBackfill] Error for user {u.get('_id')}: {e}")

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
        raise HTTPException(status_code=401, detail="User not found", headers={"X-Account-Deleted": "true"})
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
        if any(word in lower_msg for word in ["price", "cost", "how much", "bei"]):
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
        if any(word in lower_msg for word in ["price", "cost", "how much", "bei"]):
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
    # Optional user_id of owner or team member; omit or null → assign to creator
    assigned_to: Optional[str] = None

class FollowUpUpdate(BaseModel):
    reminder_date: Optional[datetime] = None
    message: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    outcome: Optional[str] = None  # called, replied, no_answer, converted, rescheduled
    outcome_note: Optional[str] = None
    assigned_to: Optional[str] = None  # set "" to clear assignee

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
    is_auto_sequence: Optional[bool] = None
    sequence_day: Optional[int] = None
    created_at: datetime
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None

class BulkFollowUpIds(BaseModel):
    ids: List[str]

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

# Order Models
class OrderCreate(BaseModel):
    customer_id: str
    product: Optional[str] = None
    product_name: Optional[str] = None
    quantity: int = 1
    price: float = 0
    total_amount: float = 0
    payment_status: str = "Pending"  # Pending, Partial, Paid
    delivery_status: str = "Processing"  # Processing, Shipped, Delivered
    notes: Optional[str] = None
    due_date: Optional[str] = None
    delivery_type: Optional[str] = "pickup"
    delivery_address: Optional[str] = None
    table_number: Optional[str] = None
    items: Optional[list] = None

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
    notes: Optional[str] = None
    due_date: Optional[str] = None
    created_at: str
    order_number: Optional[str] = None
    delivery_type: Optional[str] = None
    delivery_address: Optional[str] = None
    table_number: Optional[str] = None
    items: Optional[list] = None
    status: Optional[str] = None
    created_by: Optional[str] = None
    fulfillment_status: Optional[str] = None
    assigned_to: Optional[str] = None

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

# Booking Models
class BookingAddon(BaseModel):
    name: str
    price: float = 0

class BookingCreate(BaseModel):
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None  # for walk-in
    service_id: str = ""  # catalog product id; empty or "manual" with service_name
    service_name: Optional[str] = None  # when not linked to a catalog item
    date: str = ""  # YYYY-MM-DD
    time: str = "09:00"  # HH:MM
    checkin_date: Optional[str] = None
    checkout_date: Optional[str] = None
    staff_name: Optional[str] = None
    capacity: Optional[int] = None
    notes: Optional[str] = None
    price: float = 0
    addons: Optional[List[BookingAddon]] = None

class BookingUpdate(BaseModel):
    status: Optional[str] = None
    payment_status: Optional[str] = None
    staff_name: Optional[str] = None
    notes: Optional[str] = None

class BookingResponse(BaseModel):
    id: str
    booking_number: str
    user_id: str
    customer_id: Optional[str] = None
    customer_name: str
    customer_phone: Optional[str] = None
    service_id: str
    service_name: str
    service_category: Optional[str] = None
    staff_name: Optional[str] = None
    date: str
    time: str
    end_time: Optional[str] = None
    duration: Optional[int] = None
    checkin_date: Optional[str] = None
    checkout_date: Optional[str] = None
    nights: Optional[int] = None
    capacity: Optional[int] = None
    enrolled_count: Optional[int] = None
    addons: Optional[List[BookingAddon]] = None
    total_price: Optional[float] = None
    status: str
    payment_status: str
    price: float
    notes: Optional[str] = None
    source: Optional[str] = None
    last_reminder_at: Optional[str] = None
    created_at: str

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

    customers = await db.customers.find(query).to_list(None)  # no hard cap
    
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
        # Try Redis queue first (worker process handles it); fall back to in-process task
        queued = await enqueue_job(QUEUE_BROADCAST, {
            "type": "broadcast",
            "broadcast_id": broadcast_id,
            "user_id": business_id,
            "message": broadcast.message,
            "customers": customers,
            "image_urls": image_urls,
        })
        if not queued:
            background_tasks.add_task(
                send_broadcast_messages,
                broadcast_id,
                business_id,
                broadcast.message,
                customers,
                image_urls,
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

async def send_broadcast_messages(broadcast_id: str, user_id: str, message: str, customers: list, image_urls: List[str] = []):
    """Send broadcast to all recipients"""
    from whatsapp_service import get_whatsapp_service
    whatsapp_service = get_whatsapp_service(db)

    # Normalize relative image URLs to absolute so Evolution API can fetch them
    server_url = os.environ.get("SERVER_URL", "").rstrip("/")
    def _full_url(url: str) -> str:
        if not url:
            return url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{server_url}{url}" if server_url else url

    resolved_images = [_full_url(u) for u in image_urls if u]

    sent_count = 0
    for customer in customers:
        bcheck = await db.broadcasts.find_one({"_id": broadcast_id})
        if bcheck and bcheck.get("status") == "cancelled":
            await db.broadcasts.update_one(
                {"_id": broadcast_id},
                {"$set": {"sent_count": sent_count}},
            )
            return

        try:
            personalized_message = message.replace("{{name}}", customer.get("name", "there"))

            if resolved_images:
                # First image carries the caption
                await whatsapp_service.send_message(
                    user_id=user_id,
                    to_number=customer["phone_number"],
                    message=personalized_message,
                    customer_name=customer.get("name"),
                    media_url=resolved_images[0],
                    send_context="broadcast",
                )
                # Remaining images — no caption (gallery style)
                for img_url in resolved_images[1:]:
                    await whatsapp_service.send_message(
                        user_id=user_id,
                        to_number=customer["phone_number"],
                        message="",
                        customer_name=customer.get("name"),
                        media_url=img_url,
                        send_context="broadcast",
                    )
            else:
                # Text-only broadcast
                await whatsapp_service.send_message(
                    user_id=user_id,
                    to_number=customer["phone_number"],
                    message=personalized_message,
                    customer_name=customer.get("name"),
                    send_context="broadcast",
                )

            sent_count += 1
        except Exception as e:
            logging.error(f"Failed to send to {customer['phone_number']}: {e}")
        
        # Randomized delay between broadcast recipients
        from whatsapp_service import BROADCAST_DELAY
        import random as _rnd
        await asyncio.sleep(_rnd.uniform(*BROADCAST_DELAY))
    
    # Update broadcast status (do not overwrite cancelled)
    fin = await db.broadcasts.find_one({"_id": broadcast_id})
    if fin and fin.get("status") == "cancelled":
        await db.broadcasts.update_one(
            {"_id": broadcast_id},
            {"$set": {"sent_count": sent_count}},
        )
    else:
        await db.broadcasts.update_one(
            {"_id": broadcast_id},
            {"$set": {"sent_count": sent_count, "status": "completed"}},
        )

@api_router.post("/broadcasts/{broadcast_id}/cancel")
async def cancel_broadcast_in_progress(broadcast_id: str, user = Depends(get_current_user)):
    """Stop an in-progress broadcast (no further recipients will be sent)."""
    business_id = user.get("business_id", user["_id"])
    result = await db.broadcasts.update_one(
        {
            "_id": broadcast_id,
            "user_id": business_id,
            "status": {"$in": ["pending", "sending", "scheduled"]},
        },
        {"$set": {"status": "cancelled"}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Broadcast not found or cannot be stopped")
    return {"status": "cancelled"}

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

@api_router.delete("/broadcasts/{broadcast_id}")
async def delete_broadcast(broadcast_id: str, user = Depends(get_current_user)):
    """Delete a broadcast"""
    business_id = user.get("business_id", user["_id"])
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
    queued = await enqueue_job(QUEUE_BROADCAST, {
        "type": "broadcast",
        "broadcast_id": new_id,
        "user_id": business_id,
        "message": original["message"],
        "customers": customers,
        "image_urls": image_urls,
    })
    if not queued:
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
    mode: Optional[str] = "auto"  # "auto" = business mode, "personal" = personal conversation mode

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

# Business Knowledge Model
class BusinessKnowledge(BaseModel):
    products_services: Optional[str] = None
    pricing_info: Optional[str] = None
    business_hours: Optional[str] = None
    delivery_info: Optional[str] = None
    faqs: Optional[str] = None
    special_offers: Optional[str] = None
    business_description: Optional[str] = None
    # General
    business_location: Optional[str] = None  # physical address / area
    # Business type
    business_type: Optional[str] = None  # 'general', 'retail', 'creator', 'restaurant', 'service'
    # Restaurant-specific fields
    restaurant_has_dine_in: Optional[bool] = None
    restaurant_has_delivery: Optional[bool] = None
    restaurant_has_takeout: Optional[bool] = None
    restaurant_table_range: Optional[str] = None   # e.g. "Tables 1–20"
    restaurant_avg_wait: Optional[str] = None       # e.g. "15–20 minutes"
    restaurant_min_delivery: Optional[str] = None   # e.g. "$10 minimum order"
    # Retail-specific fields
    retail_has_delivery: Optional[bool] = None
    retail_has_pickup: Optional[bool] = None
    retail_delivery_fee: Optional[str] = None
    retail_free_delivery_above: Optional[str] = None
    retail_has_custom_orders: Optional[bool] = None
    retail_custom_lead_time: Optional[str] = None
    retail_return_policy: Optional[str] = None
    # Bakery-specific fields
    bakery_advance_days: Optional[int] = None
    bakery_deposit_required: Optional[bool] = None
    bakery_deposit_pct: Optional[int] = None
    # Grocery-specific fields
    grocery_delivery_slots: Optional[str] = None
    grocery_min_order: Optional[str] = None
    grocery_allow_substitutions: Optional[bool] = None
    # Wholesale-specific fields
    wholesale_lead_time: Optional[str] = None
    wholesale_min_order_value: Optional[str] = None
    wholesale_payment_terms: Optional[str] = None
    wholesale_has_credit_account: Optional[bool] = None
    # Salon-specific fields
    salon_multiple_stylists: Optional[bool] = None
    salon_stylist_names: Optional[str] = None
    salon_deposit_required: Optional[bool] = None
    salon_deposit_pct: Optional[int] = None
    salon_cancellation_policy: Optional[str] = None
    # Spa-specific fields
    spa_has_couples: Optional[bool] = None
    spa_deposit_required: Optional[bool] = None
    spa_deposit_pct: Optional[int] = None
    spa_cancellation_hours: Optional[int] = None
    # Repair-specific fields
    repair_has_onsite: Optional[bool] = None
    repair_has_dropoff: Optional[bool] = None
    repair_diagnosis_free: Optional[bool] = None
    repair_turnaround: Optional[str] = None
    repair_warranty: Optional[str] = None
    # Services-specific fields
    services_has_onsite: Optional[bool] = None
    services_has_remote: Optional[bool] = None
    services_quote_first: Optional[bool] = None
    services_deposit_required: Optional[bool] = None
    services_turnaround: Optional[str] = None
    services_cancellation_policy: Optional[str] = None
    # Support-specific fields
    support_ticket_prefix: Optional[str] = None
    support_response_sla: Optional[str] = None
    support_has_billing_support: Optional[bool] = None
    support_has_technical_support: Optional[bool] = None
    support_has_complaints: Optional[bool] = None
    support_has_live_handoff: Optional[bool] = None
    support_escalation_policy: Optional[str] = None
    support_refund_policy: Optional[str] = None
    # Hotel-specific fields
    hotel_checkin_time: Optional[str] = None
    hotel_checkout_time: Optional[str] = None
    hotel_min_nights: Optional[int] = None
    hotel_deposit_required: Optional[bool] = None
    hotel_deposit_pct: Optional[int] = None
    hotel_has_meal_plans: Optional[bool] = None
    hotel_meal_plan_options: Optional[str] = None
    hotel_has_airport_transfer: Optional[bool] = None
    hotel_has_spa: Optional[bool] = None
    hotel_has_pool: Optional[bool] = None
    hotel_cancellation_policy: Optional[str] = None
    # Rental-specific fields
    rental_type: Optional[str] = None
    rental_deposit_required: Optional[bool] = None
    rental_deposit_pct: Optional[int] = None
    rental_min_nights: Optional[int] = None
    rental_checkin_time: Optional[str] = None
    rental_checkout_time: Optional[str] = None
    rental_pet_policy: Optional[str] = None
    rental_cancellation_policy: Optional[str] = None
    rental_has_extras: Optional[bool] = None
    # Cleaning-specific fields
    cleaning_has_recurring: Optional[bool] = None
    cleaning_has_commercial: Optional[bool] = None
    cleaning_supplies_included: Optional[bool] = None
    # Fitness-specific fields
    fitness_has_memberships: Optional[bool] = None
    fitness_has_classes: Optional[bool] = None
    fitness_has_personal_training: Optional[bool] = None
    fitness_has_trial: Optional[bool] = None
    fitness_class_schedule: Optional[str] = None
    # Events-specific fields
    events_deposit_pct: Optional[int] = None
    events_lead_time: Optional[str] = None
    events_delivery_days: Optional[str] = None
    # Healthcare-specific fields
    hc_consultation_fee: Optional[str] = None
    hc_has_lab_tests: Optional[bool] = None
    hc_has_home_visit: Optional[bool] = None
    hc_prep_instructions: Optional[str] = None
    hc_insurance_accepted: Optional[str] = None
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
    creator_followers: Optional[str] = None
    creator_lead_time: Optional[str] = None
    creator_revisions: Optional[str] = None
    creator_usage_rights: Optional[str] = None
    creator_deposit_pct: Optional[int] = None
    creator_rates_on_request: Optional[bool] = None

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

    # Rate limit: max 20 attempts per phone per 10 minutes
    import time as _time
    _now = _time.time()
    _window = 600  # 10 minutes
    _attempts = _wa_start_rate.get(phone, [])
    _attempts = [t for t in _attempts if _now - t < _window]
    if len(_attempts) >= 20:
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
        # Verify the business owner still exists — stale team_member records from deleted accounts must be ignored
        owner_exists = await db.users.find_one({"_id": business_id}, {"_id": 1})
        if not owner_exists:
            # Clean up the stale record and fall through to normal registration
            await db.team_members.delete_many({"business_id": business_id})
            team_member = None

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
    result = await whatsapp_service.create_instance(user_id, phone)

    if result.get("status") == "error":
        # If new user was just created and pairing failed, clean up
        if is_new_user:
            await db.users.delete_one({"_id": user_id})
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to start WhatsApp pairing"))

    # Guard: if pairing code is empty, instance is stuck — abort rather than create a dangling session
    if not result.get("pairing_code"):
        logging.error(f"create_instance returned empty pairing code for user {user_id} — aborting auth")
        if is_new_user:
            await db.users.delete_one({"_id": user_id})
        raise HTTPException(status_code=500, detail="Could not generate a pairing code. Please wait a moment and try again.")

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

    # Auto-trigger contact sync + profile pictures in background
    async def _auto_sync(uid):
        try:
            ws = get_whatsapp_service(db)
            await ws.fetch_contacts(uid)
            await ws.fetch_chat_history(uid)
            await ws.fetch_profile_pictures_bulk(uid)
            logging.info(f"Auto-sync complete for user {uid}")
        except Exception as e:
            logging.error(f"Auto-sync error for user {uid}: {e}")
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

    # New pairing code only — do NOT call create_instance() here (it could delete/recreate
    # the Evolution instance and invalidate the code the user is typing).
    whatsapp_service = get_whatsapp_service(db)
    result = await whatsapp_service.refresh_pairing_code(user_id, phone)

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

@api_router.get("/settings")
async def get_settings(user = Depends(get_current_user)):
    """Get current user settings — served from Redis cache when available."""
    user_id = user["_id"]
    cache_key = key_tenant_settings(user_id)

    cached = await cache_get(cache_key)
    if cached:
        return cached

    s = user.get("settings", {})
    result = {
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
        "business_type": s.get("business_type") or user.get("business_type", ""),
        "primary_language": s.get("primary_language", "English"),
        "country": s.get("country", "Kenya"),
        "business_name": user.get("business_name", ""),
        "owner_name": user.get("owner_name", ""),
        "restaurant_has_reservations": s.get("restaurant_has_reservations", False),
    }
    await cache_set(cache_key, result, TTL_TENANT_SETTINGS)
    return result

@api_router.put("/settings")
async def update_settings(request: Request, user = Depends(get_current_user)):
    """Update user settings and invalidate cache."""
    body = await request.json()
    # Top-level fields (currency, country_code) live directly on the user doc
    top_level_fields = {}
    settings_fields = {}
    for k, v in body.items():
        if k in ("currency", "country_code", "payment_methods", "business_name", "owner_name"):
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
    await cache_delete(key_tenant_settings(user["_id"]))
    return {"status": "ok"}

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

async def _verify_payment_and_respond(
    db,
    image_url: str,
    user: dict,
    customer_id: str,
    customer_name: str,
    from_number: str,
    conv_state: dict,
):
    """
    Background task: AI-verifies a payment screenshot, updates the order,
    notifies the customer and owner, and clears pending verification state.
    """
    from agents.payment_verifier import PaymentScreenshotVerifier
    from agents.conversation_state import save_state as _save_state

    user_id = user["_id"]
    expected_order_id = conv_state.get("pending_payment_order_id")
    expected_amount = conv_state.get("pending_payment_amount")
    currency = (user.get("settings") or {}).get("currency", "")

    try:
        verifier = PaymentScreenshotVerifier(db)
        result = await verifier.verify(
            image_url=image_url,
            business_user_id=user_id,
            customer_id=customer_id,
            expected_order_id=expected_order_id,
            expected_amount=expected_amount,
        )
    except Exception as e:
        logging.error(f"[PaymentVerify] Verifier raised: {e}")
        result = {"verified": False, "reason": f"Internal error: {e}", "extracted": {}}

    ws = get_whatsapp_service(db)

    if result.get("verified"):
        order_id = result.get("order_id")
        order_number = result.get("order_number", "")
        amount = result.get("amount")
        reference = result.get("reference") or ""
        payment_method = result.get("payment_method") or ""

        # Mark order as paid
        try:
            update_fields = {
                "payment_status": "Paid",
                "payment_verified_at": datetime.utcnow(),
            }
            if reference:
                update_fields["payment_reference"] = reference
            if payment_method:
                update_fields["payment_method_used"] = payment_method
            if amount:
                update_fields["paid_amount"] = amount
            await db.orders.update_one({"_id": order_id}, {"$set": update_fields})
            logging.info(f"[PaymentVerify] Order {order_id} marked Paid for customer {customer_id}")
        except Exception as e:
            logging.error(f"[PaymentVerify] Failed to update order: {e}")

        # Send receipt to customer
        amount_str = f"{currency} {amount:,.0f}".strip() if amount else "your payment"
        ref_line = f"\n📋 Ref: *{reference}*" if reference else ""
        method_line = f"\n💳 Via: {payment_method}" if payment_method else ""
        receipt_msg = (
            f"✅ *Payment Confirmed!*\n\n"
            f"Thank you {customer_name}! Your payment of *{amount_str}* has been verified "
            f"and confirmed for order *{order_number}*.{ref_line}{method_line}\n\n"
            f"We'll process your order right away. 🚀"
        )
        try:
            await ws.send_message(
                user_id=user_id,
                to_number=from_number,
                message=receipt_msg,
                customer_name=customer_name,
                send_context="auto_reply",
            )
        except Exception as e:
            logging.error(f"[PaymentVerify] Failed to send receipt: {e}")

        # Push notification to owner
        try:
            await send_push_notification(
                user_id=user_id,
                title=f"💰 Payment Verified — {customer_name}",
                body=f"{order_number}: {amount_str} confirmed automatically",
                data={"type": "payment_verified", "order_id": order_id, "customer_id": customer_id},
            )
        except Exception as e:
            logging.error(f"[PaymentVerify] Push notification failed: {e}")

        # Clear pending state
        try:
            await _save_state(db, user_id, customer_id, {
                "pending_payment_verification": False,
                "pending_payment_order_id": None,
                "pending_payment_amount": None,
                "pending_question": None,
            })
        except Exception as e:
            logging.error(f"[PaymentVerify] Failed to clear state: {e}")

    else:
        # Verification failed — flag customer for human review
        reason = result.get("reason", "Could not verify screenshot")
        extracted = result.get("extracted", {})

        try:
            await db.customers.update_one(
                {"_id": customer_id},
                {"$set": {
                    "needs_human": True,
                    "needs_human_reason": f"Payment screenshot auto-verification failed: {reason}",
                    "needs_human_at": datetime.utcnow(),
                }}
            )
        except Exception as e:
            logging.error(f"[PaymentVerify] Failed to flag customer: {e}")

        # Message to customer
        apology_msg = (
            f"Hi {customer_name}, we received your screenshot but couldn't verify it automatically. "
            f"Our team has been notified and will manually confirm your payment shortly. "
            f"Sorry for the inconvenience! 🙏"
        )
        try:
            await ws.send_message(
                user_id=user_id,
                to_number=from_number,
                message=apology_msg,
                customer_name=customer_name,
                send_context="auto_reply",
            )
        except Exception as e:
            logging.error(f"[PaymentVerify] Failed to send failure msg: {e}")

        # Push notification to owner with details
        detail_parts = []
        if extracted.get("amount"):
            detail_parts.append(f"{extracted.get('currency','')} {extracted['amount']}")
        if extracted.get("reference"):
            detail_parts.append(f"Ref: {extracted['reference']}")
        if extracted.get("payment_method"):
            detail_parts.append(extracted["payment_method"])
        details_str = " | ".join(detail_parts) if detail_parts else "No details extracted"

        try:
            await send_push_notification(
                user_id=user_id,
                title=f"⚠️ Payment Needs Review — {customer_name}",
                body=details_str,
                data={"type": "payment_review_needed", "customer_id": customer_id},
            )
        except Exception as e:
            logging.error(f"[PaymentVerify] Owner push failed: {e}")


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
            "user_id": member.get("user_id"),
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
        "status": "pending"
    }).sort("confidence", -1).to_list(50)
    
    for p in pending:
        p["id"] = p["_id"] if isinstance(p["_id"], str) else str(p["_id"])
    
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
        if "duplicate" in str(e).lower() or "E11000" in str(e):
            existing = await db.customers.find_one({"user_id": business_id, "phone_number": clean_phone})
            if existing:
                # Promote to customer if not already
                if not existing.get("is_customer"):
                    await db.customers.update_one({"_id": existing["_id"]}, {"$set": {"is_customer": True}})
                    existing["is_customer"] = True
                return CustomerResponse(
                    id=existing["_id"], user_id=business_id, name=existing.get("name", clean_name),
                    phone_number=existing.get("phone_number", clean_phone), notes=existing.get("notes"),
                    tags=existing.get("tags", ["New"]), purchase_count=existing.get("purchase_count", 0),
                    total_spent=existing.get("total_spent", 0.0), last_message=existing.get("last_message"),
                    last_contacted=existing.get("last_contacted"), created_at=existing.get("created_at", datetime.utcnow())
                )
        raise

    # Fetch WhatsApp profile picture in background (same as webhook auto-create)
    async def _fetch_pic(uid, cid, phone):
        try:
            ws = get_whatsapp_service(db)
            pic_url = await ws.fetch_profile_picture(uid, phone)
            if pic_url:
                await db.customers.update_one(
                    {"_id": cid},
                    {"$set": {"profile_picture": pic_url}}
                )
        except Exception:
            pass
    asyncio.create_task(_fetch_pic(business_id, customer_id, clean_phone))

    # Pull any existing WhatsApp chat history for this number in the background
    async def _pull_history(uid, cid, phone):
        try:
            ws = get_whatsapp_service(db)
            result = await ws.fetch_history_for_contact(uid, phone, cid)
            logging.info(f"[HistorySync] create_customer result for {phone}: {result}")
        except Exception as e:
            logging.warning(f"[HistorySync] create_customer failed for {phone}: {e}")
    asyncio.create_task(_pull_history(business_id, customer_id, clean_phone))

    # Trigger immediate analysis so new customer appears in Needs Attention right away
    async def _analyze_new_customer(uid, cid):
        try:
            from daily_analyzer import DailyCustomerAnalyzer
            analyzer = DailyCustomerAnalyzer(db)
            analysis = await analyzer.analyze_single_customer(cid, uid)
            if analysis:
                today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                analysis["show_date"] = today
                analysis["analysis_date"] = datetime.utcnow()
                await db.customer_analysis.insert_one(analysis)
        except Exception as e:
            logging.debug(f"New customer analysis failed: {e}")
    asyncio.create_task(_analyze_new_customer(business_id, customer_id))

    return CustomerResponse(
        id=customer_id,
        user_id=business_id,
        name=customer.name,
        phone_number=customer.phone_number,
        notes=customer.notes,
        tags=customer_doc["tags"],
        purchase_count=0,
        total_spent=0.0,
        last_message=None,
        last_contacted=None,
        created_at=customer_doc["created_at"]
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
        result.append({
            "id": c["_id"],
            "name": c.get("name", ""),
            "phone_number": c.get("phone_number", ""),
            "profile_picture": c.get("profile_picture"),
            "last_message": c.get("last_message", ""),
            "last_contacted": c.get("last_contacted"),
            "suggested_type": pending["suggested_type"] if pending else c.get("suggested_type"),
            "suggestion_reason": pending["reason"] if pending else c.get("suggestion_reason"),
            "suggestion_confidence": pending["confidence"] if pending else c.get("suggestion_confidence", 0),
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
            phone_number=c.get("phone_number") or c.get("phone", ""),
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
    
    # Get today's scheduled insights (respects daily cap + queuing)
    tomorrow = today + timedelta(days=1)
    smart_insights = await db.customer_analysis.find({
        "user_id": business_id,
        "show_date": {"$gte": today, "$lt": tomorrow},
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
            
            # Only include if owner has NOT replied recently (use last_owner_reply, not last_contacted)
            last_owner_reply = c.get("last_owner_reply")
            if last_owner_reply and last_owner_reply >= cutoff_date:
                continue  # Skip - owner replied recently
            
            analyzed_customer_ids.add(c["_id"])
            auto_seq = await db.followups.find_one({"customer_id": c["_id"], "status": "pending", "is_auto_sequence": True})
            result.append({
                "id": c["_id"], "name": c["name"], "phone_number": c["phone_number"],
                "notes": c.get("notes"), "tags": c.get("tags", []),
                "last_message": c.get("last_message"), "last_contacted": c.get("last_contacted"),
                "days_since_contact": analysis.get("days_since_contact"),
                "has_pending_followup": analysis.get("has_pending_followup", False),
                "ai_reason": analysis.get("ai_reason") if analysis.get("ai_reason") else "Smart Follow-up",
                "urgency_score": analysis.get("urgency_score", 0),
                "created_at": c["created_at"],
                "ai_draft_message": auto_seq.get("message") if auto_seq else None,
                "ai_draft_followup_id": auto_seq["_id"] if auto_seq else None,
                "ai_draft_day": auto_seq.get("sequence_day") if auto_seq else None,
            })
    
    # Then, add customers that need attention but don't have analysis yet
    # Use last_owner_reply — only counts when the owner actually sent a message
    customers_without_analysis = await db.customers.find({
        "user_id": business_id,
        "$and": [
            {"$or": [{"is_customer": True}, {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}]},
            {"$or": [{"last_owner_reply": {"$lt": cutoff_date}}, {"last_owner_reply": None}, {"last_owner_reply": {"$exists": False}}]},
        ],
    }).sort("last_owner_reply", 1).to_list(100)

    for c in customers_without_analysis:
        if c["_id"] in analyzed_customer_ids:
            continue

        pending_followup = await db.followups.find_one({"customer_id": c["_id"], "status": "pending", "is_auto_sequence": {"$ne": True}})
        auto_seq = await db.followups.find_one({"customer_id": c["_id"], "status": "pending", "is_auto_sequence": True})
        last_owner_reply = c.get("last_owner_reply")
        days_since_contact = (datetime.utcnow() - last_owner_reply).days if last_owner_reply else None

        # Use simple rule-based reason to avoid timeout
        ai_reason = generate_simple_reason(c, days_since_contact)

        result.append({
            "id": c["_id"], "name": c["name"], "phone_number": c["phone_number"],
            "notes": c.get("notes"), "tags": c.get("tags", []),
            "last_message": c.get("last_message"), "last_contacted": c.get("last_contacted"),
            "days_since_contact": days_since_contact, "has_pending_followup": pending_followup is not None,
            "ai_reason": ai_reason, "created_at": c["created_at"],
            "ai_draft_message": auto_seq.get("message") if auto_seq else None,
            "ai_draft_followup_id": auto_seq["_id"] if auto_seq else None,
            "ai_draft_day": auto_seq.get("sequence_day") if auto_seq else None,
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
        # None means "inherit global auto-reply settings"
        auto_reply=customer.get("auto_reply"),
        is_personal=customer.get("is_personal", False),
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
        # None means "inherit global auto-reply settings"
        auto_reply=updated.get("auto_reply"),
        is_personal=updated.get("is_personal", False),
        stage=updated.get("stage", "lead"),
        last_message=updated.get("last_message"),
        last_contacted=updated.get("last_contacted"),
        profile_picture=updated.get("profile_picture"),
        created_at=updated["created_at"]
    )

@api_router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, user = Depends(get_current_user)):
    """Delete a customer"""
    business_id = user.get("business_id", user["_id"])
    result = await db.customers.delete_one({"_id": customer_id, "user_id": business_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"status": "success", "message": "Customer deleted"}

# ============ FOLLOW-UP ENDPOINTS ============

async def _validate_followup_assignee(assignee_id: str, business_id: str) -> None:
    if assignee_id == business_id:
        return
    m = await db.team_members.find_one({"business_id": business_id, "user_id": assignee_id})
    if not m:
        raise HTTPException(status_code=400, detail="Invalid assignee for this business")


async def _followup_assignee_labels(business_id: str, assignee_ids: set) -> dict:
    """Map user_id -> display name for follow-up assignees."""
    if not assignee_ids:
        return {}
    out: dict = {}
    if business_id in assignee_ids:
        u = await db.users.find_one({"_id": business_id})
        out[business_id] = (u or {}).get("business_name") or (u or {}).get("name") or "Owner"
    remaining = assignee_ids - {business_id}
    if remaining:
        cur = db.team_members.find({"business_id": business_id, "user_id": {"$in": list(remaining)}})
        async for m in cur:
            uid = m.get("user_id")
            if uid:
                out[uid] = m.get("name") or "Team"
    return out


@api_router.post("/followups", response_model=FollowUpResponse)
async def create_followup(followup: FollowUpCreate, user = Depends(get_current_user)):
    """Create a follow-up reminder"""
    business_id = user.get("business_id", user["_id"])
    # Verify customer exists
    customer = await db.customers.find_one({"_id": followup.customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Promote to customer if they were auto-created (contact pool) — creating a reminder signals intent
    if not customer.get("is_customer"):
        await db.customers.update_one(
            {"_id": followup.customer_id},
            {"$set": {"is_customer": True}}
        )

    followup_id = str(uuid.uuid4())
    assignee_raw = followup.assigned_to
    if assignee_raw == "":
        resolved_assignee = None
    elif assignee_raw is not None:
        await _validate_followup_assignee(assignee_raw, business_id)
        resolved_assignee = assignee_raw
    else:
        resolved_assignee = user["_id"]
        await _validate_followup_assignee(resolved_assignee, business_id)

    followup_doc = {
        "_id": followup_id,
        "user_id": business_id,
        "customer_id": followup.customer_id,
        "reminder_date": followup.reminder_date,
        "message": followup.message,
        "status": "pending",
        "type": followup.type,
        "created_at": datetime.utcnow(),
        "assigned_to": resolved_assignee,
    }

    await db.followups.insert_one(followup_doc)
    labels = await _followup_assignee_labels(business_id, {resolved_assignee} if resolved_assignee else set())
    aname = labels.get(resolved_assignee) if resolved_assignee else None
    
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
        is_auto_sequence=followup_doc.get("is_auto_sequence"),
        sequence_day=followup_doc.get("sequence_day"),
        created_at=followup_doc["created_at"],
        assigned_to=resolved_assignee,
        assigned_to_name=aname,
    )

@api_router.get("/followups", response_model=List[FollowUpResponse])
async def get_followups(
    status: Optional[str] = None,
    assigned_to: Optional[str] = Query(
        None,
        description="Filter by assignee user_id, or 'mine', or 'unassigned'",
    ),
    user = Depends(get_current_user),
):
    """Get all follow-ups for current user — excludes auto-sequence (AI Draft) items"""
    business_id = user.get("business_id", user["_id"])
    query: dict = {"user_id": business_id, "is_auto_sequence": {"$ne": True}}
    if status:
        query["status"] = status
    if assigned_to == "mine":
        query["assigned_to"] = user["_id"]
    elif assigned_to == "unassigned":
        query["$or"] = [{"assigned_to": None}, {"assigned_to": {"$exists": False}}]
    elif assigned_to:
        query["assigned_to"] = assigned_to

    followups = await db.followups.find(query).sort("reminder_date", 1).to_list(1000)
    if not followups:
        return []

    # Batch fetch all customers in one query (fixes N+1)
    customer_ids = list({f["customer_id"] for f in followups})
    customers_list = await db.customers.find({"_id": {"$in": customer_ids}}).to_list(None)
    customers_map = {c["_id"]: c for c in customers_list}

    aid_set = {f.get("assigned_to") for f in followups if f.get("assigned_to")}
    labels = await _followup_assignee_labels(business_id, aid_set)

    result = []
    for f in followups:
        customer = customers_map.get(f["customer_id"])
        aid = f.get("assigned_to")
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
            is_auto_sequence=f.get("is_auto_sequence"),
            sequence_day=f.get("sequence_day"),
            created_at=f["created_at"],
            assigned_to=aid,
            assigned_to_name=labels.get(aid) if aid else None,
        ))
    
    return result

@api_router.put("/followups/{followup_id}", response_model=FollowUpResponse)
async def update_followup(followup_id: str, update: FollowUpUpdate, user = Depends(get_current_user)):
    """Update a follow-up"""
    business_id = user.get("business_id", user["_id"])
    followup = await db.followups.find_one({"_id": followup_id, "user_id": business_id})
    if not followup:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    
    raw = update.model_dump(exclude_unset=True)
    update_data = {}
    for k, v in raw.items():
        if k == "assigned_to":
            if v == "":
                update_data["assigned_to"] = None
            elif v is not None:
                await _validate_followup_assignee(v, business_id)
                update_data["assigned_to"] = v
        elif v is not None:
            update_data[k] = v
    if update_data:
        await db.followups.update_one({"_id": followup_id}, {"$set": update_data})
    
    updated = await db.followups.find_one({"_id": followup_id})
    customer = await db.customers.find_one({"_id": updated["customer_id"]})
    aid = updated.get("assigned_to")
    labels = await _followup_assignee_labels(business_id, {aid} if aid else set())
    
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
        is_auto_sequence=updated.get("is_auto_sequence"),
        sequence_day=updated.get("sequence_day"),
        created_at=updated["created_at"],
        assigned_to=aid,
        assigned_to_name=labels.get(aid) if aid else None,
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


class BulkSnoozeBody(BaseModel):
    ids: List[str]
    days: int = 1


@api_router.post("/followups/bulk-snooze")
async def bulk_snooze_followups(body: BulkSnoozeBody, user = Depends(get_current_user)):
    """Snooze multiple pending follow-ups by the same number of days."""
    business_id = user.get("business_id", user["_id"])
    days = max(1, min(body.days, 365))
    modified = 0
    for fid in body.ids:
        doc = await db.followups.find_one({"_id": fid, "user_id": business_id, "status": "pending"})
        if not doc:
            continue
        current_date = doc.get("reminder_date", datetime.utcnow())
        new_date = current_date + timedelta(days=days)
        await db.followups.update_one({"_id": fid}, {"$set": {"reminder_date": new_date}})
        modified += 1
    return {"status": "success", "updated": modified, "days": days}


@api_router.post("/followups/bulk-delete")
async def bulk_delete_followups(body: BulkFollowUpIds, user = Depends(get_current_user)):
    business_id = user.get("business_id", user["_id"])
    result = await db.followups.delete_many({"_id": {"$in": body.ids}, "user_id": business_id})
    return {"status": "success", "deleted": result.deleted_count}


@api_router.post("/followups/{followup_id}/redraft")
async def redraft_followup_message(
    followup_id: str,
    direction: str = Body(..., embed=True),
    user = Depends(get_current_user)
):
    """
    Redraft the AI message for an auto-sequence follow-up using owner-provided direction.
    Calls the same rich-context AI logic as the auto-sequence generator but injects the
    owner's direction as an extra instruction.
    """
    business_id = user.get("business_id", user["_id"])
    followup = await db.followups.find_one({"_id": followup_id, "user_id": business_id})
    if not followup:
        raise HTTPException(status_code=404, detail="Follow-up not found")

    customer_id = followup.get("customer_id")
    customer = await db.customers.find_one({"_id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    sequence_day = followup.get("sequence_day", 3)
    customer_name = customer.get("name", "there")
    customer_phone = customer.get("phone_number", "")
    business_name = user.get("business_name") or user.get("name") or ""

    # ── Business knowledge ──────────────────────────────────────────────────
    bk = user.get("business_knowledge", {}) if isinstance(user.get("business_knowledge"), dict) else {}
    business_desc  = (bk.get("business_description", "") or "").strip()
    products       = (bk.get("products_services", "") or "").strip()
    pricing_info   = (bk.get("pricing_info", "") or "").strip()
    special_offers = (bk.get("special_offers", "") or "").strip()
    delivery_info  = (bk.get("delivery_info", "") or "").strip()
    faqs           = (bk.get("faqs", "") or "").strip()

    has_business_context = bool(business_desc or products)

    # ── Customer signals ────────────────────────────────────────────────────
    tags           = customer.get("tags", [])
    purchase_count = int(customer.get("purchase_count", 0) or 0)
    total_spent    = float(customer.get("total_spent", 0) or 0)
    is_vip         = "VIP" in tags
    is_returning   = purchase_count > 0 or "Returning" in tags
    currency       = (user.get("settings") or {}).get("currency", "")

    # ── Conversation state ──────────────────────────────────────────────────
    preferred_language = ""
    personality = ""
    price_sensitivity = ""
    products_viewed: list = []
    try:
        from agents.conversation_state import load_state
        conv_state = await load_state(db, user["_id"], str(customer.get("_id", "")))
        preferred_language = conv_state.get("preferred_language") or ""
        personality        = conv_state.get("personality") or ""
        price_sensitivity  = conv_state.get("price_sensitivity") or ""
        products_viewed    = conv_state.get("products_viewed", [])
    except Exception:
        pass

    if not preferred_language and customer_phone:
        try:
            from ai_service import detect_language_from_phone
            lang_info = detect_language_from_phone(customer_phone)
            langs = lang_info.get("languages", [])
            preferred_language = langs[0] if langs else ""
        except Exception:
            pass

    # ── Recent conversation history ─────────────────────────────────────────
    recent_history = ""
    try:
        msgs = await db.messages.find({
            "user_id": user["_id"],
            "customer_id": str(customer.get("_id", "")),
        }).sort("created_at", -1).limit(6).to_list(6)
        if msgs:
            lines = [
                f"{'Customer' if m.get('direction') == 'incoming' else 'Business'}: {m.get('content', '')[:120]}"
                for m in reversed(msgs)
                if m.get("content", "").strip()
            ]
            recent_history = "\n".join(lines)
    except Exception:
        pass

    # ── Build context blocks ────────────────────────────────────────────────
    ctx = []
    if business_name: ctx.append(f"Business: {business_name}")
    if business_desc:  ctx.append(f"What we do: {business_desc}")
    if products:       ctx.append(f"Products/Services: {products}")
    if pricing_info:   ctx.append(f"Pricing: {pricing_info}")
    if special_offers: ctx.append(f"Current offers: {special_offers}")
    if delivery_info:  ctx.append(f"Delivery info: {delivery_info}")
    if faqs:           ctx.append(f"FAQs: {faqs[:300]}")
    business_context = "\n".join(ctx) if ctx else "(no business knowledge configured)"

    profile = [f"Customer name: {customer_name}"]
    if is_vip:
        profile.append("Customer status: VIP — high-value, treat with extra warmth")
    elif is_returning:
        spend_str = f"{currency} {total_spent:,.0f}".strip() if total_spent else ""
        profile.append(
            f"Customer status: Returning customer "
            f"({purchase_count} order{'s' if purchase_count != 1 else ''}"
            f"{', total spent ' + spend_str if spend_str else ''})"
        )
    else:
        profile.append("Customer status: New — first interaction")
    if products_viewed:
        profile.append(f"Products they showed interest in: {', '.join(products_viewed[:4])}")
    if price_sensitivity == "high":
        profile.append("Price sensitivity: high — they care about value/deals")
    if personality == "direct":
        profile.append("Communication style: direct and brief — skip pleasantries")
    elif personality == "chatty":
        profile.append("Communication style: chatty — enjoys friendly conversation")
    elif personality == "formal":
        profile.append("Communication style: formal — keep professional tone")
    customer_profile = "\n".join(profile)

    if sequence_day == 3:
        base_goal = (
            "This customer contacted us 3 days ago but hasn't purchased yet. "
            "Write a warm, natural check-in message."
        )
    else:
        base_goal = (
            "This customer contacted us 7 days ago but hasn't purchased yet. "
            "Write a gentle re-engagement message."
        )

    lang_instruction = f"Write in {preferred_language}." if preferred_language else "Write in English."

    direction_block = f"\n## Owner Direction\n{direction.strip()}\nApply this direction to the message." if direction.strip() else ""

    prompt = f"""You are writing a WhatsApp follow-up message on behalf of a business owner.

## Business Context
{business_context}

## Customer Profile
{customer_profile}

## Recent Conversation
{recent_history if recent_history else "(no prior messages on record)"}

## Task
{base_goal}
{direction_block}

## Language
{lang_instruction}

## STRICT RULES
- ONLY reference products, prices, offers, or details explicitly listed in Business Context above.
- NEVER invent products, prices, discounts, or promotions not listed above.
- Max 2-3 sentences. WhatsApp-friendly tone — no formal letter style.
- Use the customer's name naturally (once).
- No markdown, no asterisks, no bullet points.

Output only the message text. Nothing else."""

    new_message = None
    try:
        from ai_service import get_drafter
        ai = get_drafter()
        new_message = (await ai._call_llm(prompt, model_pref="standard")).strip()
    except Exception as e:
        logger.error(f"[Redraft] AI call failed: {e}")

    if not new_message:
        # Safe fallback
        new_message = (
            f"Hi {customer_name}! Just checking in — we're here whenever you're ready. "
            f"Feel free to reach out anytime!"
        )

    # Persist the new draft back to the follow-up
    await db.followups.update_one(
        {"_id": followup_id},
        {"$set": {"message": new_message}}
    )

    return {"message": new_message}


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

    await db.customers.update_one(
        {"_id": customer_id},
        {"$set": {"last_contacted": datetime.utcnow(), "last_owner_reply": datetime.utcnow()}}
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

    # Use last_owner_reply — only counts when owner actually sent a message
    _is_customer = {"$or": [{"is_customer": True}, {"is_customer": {"$exists": False}, "auto_created": {"$ne": True}}]}
    _no_reply_week = {"$or": [{"last_owner_reply": {"$lt": cutoff_week}}, {"last_owner_reply": None}, {"last_owner_reply": {"$exists": False}}]}
    _no_reply_month = {"$or": [{"last_owner_reply": {"$lt": cutoff_month}}, {"last_owner_reply": None}, {"last_owner_reply": {"$exists": False}}]}

    # Count today's scheduled insights
    analyzed_count = 0
    tomorrow = today + timedelta(days=1)
    smart_insights = await db.customer_analysis.find({
        "user_id": business_id,
        "show_date": {"$gte": today, "$lt": tomorrow},
    }).to_list(100)
    analyzed_count = len(smart_insights)

    # Count non-analyzed customers that still need attention
    non_analyzed_customers = await db.customers.find({
        "user_id": business_id,
        "$and": [_is_customer, _no_reply_week]
    }).to_list(100)
    
    analyzed_ids = {a["customer_id"] for a in smart_insights}
    non_analyzed_count = sum(1 for c in non_analyzed_customers if c["_id"] not in analyzed_ids)
    
    # Total shown in Needs Attention list = analyzed + non-analyzed (up to 30 max per endpoint)
    neglected_week = min(analyzed_count + non_analyzed_count, 30)
    
    neglected_month = await db.customers.count_documents({
        "user_id": business_id,
        "$and": [_is_customer, _no_reply_month]
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
    
    # Update CRM customer stats (skip walk-in — not a real customer document)
    if not is_walk_in:
        update_ops = {
            "$inc": {"purchase_count": 1, "total_spent": sale.amount},
            "$set": {"last_contacted": datetime.utcnow()}
        }
        if "New" in customer.get("tags", []):
            new_tags = [t for t in customer.get("tags", []) if t != "New"]
            new_tags.append("Returning")
            update_ops["$set"]["tags"] = new_tags
        await db.customers.update_one(
            {"_id": sale.customer_id, "user_id": business_id},
            update_ops
        )
    
    # Send receipt via WhatsApp — try Redis queue first, fall back to background_tasks
    # Use business_id (owner) for WhatsApp instance, since team members don't have their own instance
    if sale.send_receipt and not is_walk_in:
        owner = await db.users.find_one({"_id": business_id}) if business_id != user["_id"] else user
        currency = (owner or user).get("currency", "USD")
        business_name = (owner or user).get("business_name", user.get("business_name", "Your Shop"))
        receipt_job = {
            "type": "receipt",
            "user_id": business_id,
            "sale_id": sale_id,
            "phone": customer["phone_number"],
            "customer_name": customer["name"],
            "message": sale.receipt_message or (
                f"✅ Payment received\nItem: {sale.item}\nAmount: {currency} {sale.amount:,.0f}\nThank you for shopping with us 🙏"
            ),
        }
        queued = await enqueue_job(QUEUE_RECEIPT, receipt_job)
        if not queued:
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
                business_id,
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
    business_id = user.get("business_id", user["_id"])
    user_role = user.get("role", "owner")
    query = {"user_id": business_id}
    if user_role == "employee":
        query["recorded_by"] = user["_id"]
    sales = await db.sales.find(query).sort("created_at", -1).to_list(1000)
    
    result = []
    for s in sales:
        customer = await db.customers.find_one({"_id": s["customer_id"]})
        result.append(SaleResponse(
            id=s["_id"],
            user_id=s["user_id"],
            customer_id=s["customer_id"],
            customer_name=customer["name"] if customer else "Unknown",
            customer_phone=customer["phone_number"] if customer else None,
            item=s["item"],
            amount=s["amount"],
            payment_method=s["payment_method"],
            receipt_sent=s.get("receipt_sent", False),
            is_credit=s.get("is_credit", False),
            due_date=s.get("due_date"),
            paid_date=s.get("paid_date"),
            created_at=s["created_at"]
        ))
    
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
    
    # Send receipt via WhatsApp — queue first, fall back to background_tasks
    currency = user.get("currency", "USD")
    queued = await enqueue_job(QUEUE_RECEIPT, {
        "type": "receipt",
        "user_id": business_id,
        "sale_id": sale_id,
        "phone": customer["phone_number"],
        "customer_name": customer["name"],
        "message": f"✅ Payment received\nItem: {sale['item']}\nAmount: {currency} {sale['amount']:,.0f}\nThank you for shopping with us 🙏",
    })
    if not queued:
        background_tasks.add_task(
            send_receipt_message,
            customer["phone_number"],
            customer["name"],
            sale["item"],
            sale["amount"],
            user.get("business_name", "Your Shop"),
            sale_id,
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

    # Resolve product label from items array or fallback to product/product_name field
    items = order.items or []
    product_label = (
        order.product
        or order.product_name
        or (", ".join(it.get("product_name", "") for it in items) if items else "Order")
    )
    quantity = order.quantity or (items[0].get("quantity", 1) if items else 1)
    price = order.price or (items[0].get("unit_price", 0) if items else 0)
    total_amount = order.total_amount or sum(it.get("price", 0) for it in items) or round(quantity * price, 2)

    order_doc = {
        "_id": order_id,
        "user_id": business_id,
        "recorded_by": user["_id"],
        "customer_id": order.customer_id,
        "product": product_label,
        "product_name": product_label,
        "quantity": quantity,
        "price": price,
        "total_amount": total_amount,
        "total": total_amount,
        "payment_status": order.payment_status,
        "delivery_status": order.delivery_status,
        "status": "pending",
        "notes": order.notes,
        "due_date": order.due_date,
        "delivery_type": order.delivery_type or "pickup",
        "delivery_address": order.delivery_address or "",
        "table_number": order.table_number or "",
        "items": items,
        "created_at": datetime.utcnow(),
        "created_by": "staff",
    }

    # Reduce stock for each item if stock is tracked
    for it in items:
        if it.get("product_id"):
            await db.products.update_one(
                {"_id": it["product_id"], "user_id": business_id, "stock_quantity": {"$gte": it.get("quantity", 1)}},
                {"$inc": {"stock_quantity": -it.get("quantity", 1)}}
            )
        elif it.get("product_name"):
            await db.products.update_one(
                {"user_id": business_id, "name": it["product_name"], "stock_quantity": {"$gte": it.get("quantity", 1)}},
                {"$inc": {"stock_quantity": -it.get("quantity", 1)}}
            )

    if not items and product_label:
        # Single-item legacy path: deduct stock by product name
        await db.products.update_one(
            {"user_id": business_id, "name": product_label, "stock_quantity": {"$gte": quantity}},
            {"$inc": {"stock_quantity": -quantity}}
        )

    await db.orders.insert_one(order_doc)

    return OrderResponse(
        id=order_id,
        customer_id=order.customer_id,
        customer_name=customer.get("name", "Unknown"),
        customer_phone=customer.get("phone_number", "N/A"),
        product=product_label,
        quantity=int(quantity),
        price=float(price),
        total_amount=float(total_amount),
        payment_status=order.payment_status,
        delivery_status=order.delivery_status,
        notes=order.notes,
        due_date=order.due_date,
        delivery_type=order.delivery_type,
        delivery_address=order.delivery_address,
        table_number=order.table_number,
        items=items if items else None,
        status="pending",
        created_by="staff",
        created_at=order_doc["created_at"].isoformat()
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
        # Get customer info
        if order["customer_id"] == "walk-in":
            customer_name = "Walk-in Customer"
            customer_phone = "N/A"
        else:
            customer = await db.customers.find_one({"_id": order["customer_id"]})
            customer_name = customer["name"] if customer else "Unknown"
            customer_phone = customer["phone_number"] if customer else "N/A"
        
        # Support both manual orders (product/quantity/price) and autoreply orders (product_name/items/total_amount)
        items = order.get("items") or []
        product_label = (
            order.get("product")
            or order.get("product_name")
            or (", ".join(it.get("product_name", "") for it in items) if items else "Order")
        )
        quantity = order.get("quantity") or (items[0].get("quantity", 1) if items else 1)
        unit_price = order.get("price") or (items[0].get("unit_price", 0) if items else 0)
        total = order.get("total_amount") or order.get("total") or 0

        result.append(OrderResponse(
            id=str(order["_id"]),
            customer_id=str(order.get("customer_id", "")),
            customer_name=customer_name,
            customer_phone=customer_phone,
            product=product_label,
            quantity=quantity,
            price=unit_price,
            total_amount=total,
            payment_status=order.get("payment_status", "unpaid"),
            delivery_status=order.get("delivery_status", order.get("status", "pending")),
            notes=order.get("notes"),
            due_date=order.get("due_date"),
            created_at=order["created_at"].isoformat(),
            order_number=order.get("order_number"),
            delivery_type=order.get("delivery_type"),
            delivery_address=order.get("delivery_address"),
            table_number=order.get("table_number"),
            items=items if items else None,
            status=order.get("status"),
            created_by=order.get("created_by"),
            fulfillment_status=order.get("fulfillment_status", "New"),
            assigned_to=order.get("assigned_to"),
        ))
    
    return result

@api_router.put("/orders/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: str,
    payment_status: Optional[str] = None,
    delivery_status: Optional[str] = None,
    notes: Optional[str] = None,
    payment_method: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Update order payment status, delivery status, or notes"""
    from bson import ObjectId
    business_id = user.get("business_id", user["_id"])
    # Try string _id first (autoreply orders use uuid strings), then ObjectId (manual orders)
    order = await db.orders.find_one({"_id": order_id, "user_id": business_id})
    if not order:
        try:
            order = await db.orders.find_one({"_id": ObjectId(order_id), "user_id": business_id})
        except Exception:
            pass
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
        await db.orders.update_one({"_id": order["_id"]}, {"$set": update_ops})
        order = await db.orders.find_one({"_id": order["_id"]})

    # When marking paid, record revenue in sales (same logic as convert-to-sale); skip if already linked
    if (
        payment_status is not None
        and (payment_status or "").strip().lower() == "paid"
        and order
        and not order.get("sale_id")
    ):
        pm = (payment_method or "Cash").strip() or "Cash"
        sale_id = await _insert_sale_from_order_document(order, user, business_id, pm)
        await db.orders.update_one({"_id": order["_id"]}, {"$set": {"sale_id": sale_id}})
        order = await db.orders.find_one({"_id": order["_id"]})

    # Get customer info
    if order.get("customer_id") == "walk-in":
        customer_name = "Walk-in Customer"
        customer_phone = "N/A"
    else:
        customer = await db.customers.find_one({"_id": order.get("customer_id")})
        customer_name = customer.get("name", "Unknown") if customer else "Unknown"
        customer_phone = customer.get("phone_number", "N/A") if customer else "N/A"

    # Send WhatsApp confirmation when owner marks order as Paid
    if payment_status is not None and (payment_status or "").strip().lower() == "paid" and customer_phone and customer_phone != "N/A":
        try:
            ws = get_whatsapp_service(db)
            order_number = order.get("order_number", "")
            total = float(order.get("total_amount") or order.get("total") or 0)
            user_settings = user.get("settings") or {}
            currency_code = user_settings.get("currency", "")
            total_str = f"{currency_code} {total:,.0f}".strip() if total else ""
            order_ref = f" for order *{order_number}*" if order_number else ""
            amount_line = f"\n💰 Amount: *{total_str}*" if total_str else ""
            msg = (
                f"✅ *Payment Confirmed!*\n\n"
                f"Hi {customer_name}! Your payment{order_ref} has been confirmed.{amount_line}\n\n"
                f"We're processing your order now. Thank you! 🙏"
            )
            business_id = user.get("business_id", user["_id"])
            await ws.send_message(
                user_id=business_id,
                to_number=customer_phone,
                message=msg,
                send_context="payment_confirmed",
            )
        except Exception as e:
            logging.warning(f"[update_order] Failed to send payment confirmation WhatsApp: {e}")

    # Handle both autoreply orders (product_name/items) and manual orders (product)
    items = order.get("items") or []
    product_label = (
        order.get("product")
        or order.get("product_name")
        or (", ".join(it.get("product_name", "") for it in items) if items else "Order")
    )
    quantity = int(order.get("quantity") or (items[0].get("quantity", 1) if items else 1))
    unit_price = float(order.get("price") or (items[0].get("unit_price", 0) if items else 0))
    total = float(order.get("total_amount") or order.get("total") or 0)

    created_at_raw = order.get("created_at")
    created_at_str = created_at_raw.isoformat() if hasattr(created_at_raw, "isoformat") else str(created_at_raw or "")

    return OrderResponse(
        id=str(order["_id"]),
        customer_id=str(order.get("customer_id", "")),
        customer_name=customer_name,
        customer_phone=customer_phone,
        product=product_label,
        quantity=quantity,
        price=unit_price,
        total_amount=total,
        payment_status=order.get("payment_status", "unpaid"),
        delivery_status=order.get("delivery_status", order.get("status", "pending")),
        notes=order.get("notes"),
        due_date=order.get("due_date"),
        created_at=created_at_str,
        order_number=order.get("order_number"),
        delivery_type=order.get("delivery_type"),
        delivery_address=order.get("delivery_address"),
        items=items if items else None,
        status=order.get("status"),
        created_by=order.get("created_by"),
    )

@api_router.patch("/orders/{order_id}/progress")
async def update_order_progress(
    order_id: str,
    body: dict,
    user = Depends(get_current_user),
):
    """Update fulfillment_status and/or assigned_to for an order."""
    business_id = user.get("business_id", user["_id"])
    # Support both string UUIDs and legacy ObjectId _ids
    try:
        oid = _ObjectId(order_id)
        order = await db.orders.find_one({"_id": oid, "user_id": business_id})
        raw_id: Any = oid
    except Exception:
        order = None
        raw_id = order_id
    if not order:
        order = await db.orders.find_one({"_id": order_id, "user_id": business_id})
        raw_id = order_id
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    update: dict = {}
    if "fulfillment_status" in body:
        update["fulfillment_status"] = body["fulfillment_status"]
    if "assigned_to" in body:
        update["assigned_to"] = body["assigned_to"]
    if update:
        await db.orders.update_one({"_id": raw_id}, {"$set": update})
    order = await db.orders.find_one({"_id": raw_id})

    # Send WhatsApp notification on fulfillment_status change
    new_status = update.get("fulfillment_status")
    if new_status:
        try:
            customer_id = order.get("customer_id")
            if customer_id and customer_id != "walk-in":
                customer = await db.customers.find_one({"_id": customer_id})
                customer_phone = customer.get("phone_number") if customer else None
                if customer_phone:
                    order_number = order.get("order_number", "")
                    order_ref = f" *#{order_number}*" if order_number else ""
                    delivery_type = (order.get("delivery_type") or "").strip()
                    delivery_address = order.get("delivery_address", "")
                    is_delivery = delivery_type.lower() == "delivery"
                    is_dine_in = delivery_type.lower() in ("dine in", "dine-in", "dine_in")

                    # Resolve business type
                    biz_settings = await db.settings.find_one({"user_id": business_id}) or {}
                    bk = await db.users.find_one({"_id": business_id}) or {}
                    biz_type = (
                        biz_settings.get("business_type")
                        or (bk.get("business_knowledge") or {}).get("business_type")
                        or bk.get("business_type")
                        or "general"
                    ).lower()

                    def _msgs(confirmed, preparing, ready_dine, ready_delivery, ready_pickup, done):
                        if is_delivery and delivery_address:
                            ready = f"{ready_delivery}\n\n🚗 Delivering to: *{delivery_address}*"
                        elif is_dine_in:
                            ready = ready_dine
                        else:
                            ready = ready_pickup
                        return {"Confirmed": confirmed, "Preparing": preparing, "Ready": ready, "Done": done}

                    templates = {
                        "restaurant": _msgs(
                            f"✅ Your order{order_ref} is *confirmed*! We're preparing it fresh for you.",
                            f"👨‍🍳 Your food{order_ref} is being prepared in the kitchen. Won't be long!",
                            f"🍽️ Your food{order_ref} is *ready*! Enjoy your meal 😊",
                            f"🎉 Your food{order_ref} is *on its way*!",
                            f"🔥 Your food{order_ref} is *ready* for pickup! Come grab it while it's hot.",
                            f"Thank you so much for dining with us! 🙏\nWe hope you enjoyed every bite and look forward to having you back soon. 😊",
                        ),
                        "bakery": _msgs(
                            f"✅ Your order{order_ref} is *confirmed*! We'll bake it fresh for you.",
                            f"🔥 Your order{order_ref} is in the oven! Almost ready.",
                            f"🥐 Your order{order_ref} is *ready*! Enjoy 😊",
                            f"🎉 Your fresh bakes{order_ref} are *on their way*!",
                            f"🥐 Fresh out of the oven! Your order{order_ref} is *ready* for pickup.",
                            f"Thank you for choosing us! 🙏\nWe hope you enjoyed every bite. See you next time! 🥐",
                        ),
                        "grocery": _msgs(
                            f"✅ Your order{order_ref} is *confirmed*! We're picking and packing it now.",
                            f"🛒 Your order{order_ref} is being packed and checked.",
                            f"✅ Your order{order_ref} is *ready*!",
                            f"🚗 Your groceries{order_ref} are *on their way*!",
                            f"🛍️ Your order{order_ref} is *packed and ready* for pickup!",
                            f"Thank you for your order! 🙏\nWe appreciate your support. See you next time! 🛒",
                        ),
                        "wholesale": _msgs(
                            f"✅ Your order{order_ref} is *confirmed*! We're processing it now.",
                            f"📦 Your order{order_ref} is being packed and quality-checked.",
                            f"✅ Your order{order_ref} is *ready*!",
                            f"🚚 Your order{order_ref} is *dispatched* and on its way!",
                            f"📦 Your order{order_ref} is *ready* for collection!",
                            f"Thank you for your business! 🙏\nWe appreciate the partnership and look forward to your next order.",
                        ),
                        "salon": _msgs(
                            f"✅ Your appointment{order_ref} is *confirmed*! We're looking forward to seeing you.",
                            f"💇 We're getting your station ready{order_ref}. Almost time!",
                            f"💇 We're *ready* for you{order_ref}! Come on in 😊",
                            f"💇 We're *ready* for you{order_ref}! Come on in 😊",
                            f"💇 We're *ready* for you{order_ref}! Come on in 😊",
                            f"Thank you for visiting us! 🙏\nWe hope you loved your look. See you next time! 💇",
                        ),
                        "spa": _msgs(
                            f"✅ Your appointment{order_ref} is *confirmed*! We're looking forward to welcoming you.",
                            f"🕯️ We're preparing your treatment room{order_ref}. Almost ready!",
                            f"🌿 We're *ready* for you{order_ref}. Come relax and unwind 😊",
                            f"🌿 We're *ready* for you{order_ref}. Come relax and unwind 😊",
                            f"🌿 We're *ready* for you{order_ref}. Come relax and unwind 😊",
                            f"Thank you for visiting us! 🙏\nWe hope you left feeling refreshed and rejuvenated. See you next time! 🌿",
                        ),
                        "repair": _msgs(
                            f"✅ Your repair job{order_ref} is *confirmed*! Our technician will get right on it.",
                            f"🔧 Your item{order_ref} is being worked on by our technician.",
                            f"🔧 Your item{order_ref} is *repaired*! Come pick it up 😊",
                            f"🚗 Your repaired item{order_ref} is *on its way* back to you!",
                            f"✅ Great news! Your item{order_ref} is *repaired and ready* for pickup 🔧",
                            f"Thank you for trusting us with your repair! 🙏\nWe hope everything works perfectly. Don't hesitate to reach out if you need anything.",
                        ),
                        "cleaning": _msgs(
                            f"✅ Your cleaning appointment{order_ref} is *confirmed*! Our team is on it.",
                            f"🧹 Our team is on their way / getting set up{order_ref}.",
                            f"✨ Cleaning *complete*{order_ref}! Everything is fresh and spotless.",
                            f"✨ Cleaning *complete*{order_ref}! Everything is fresh and spotless.",
                            f"✨ Cleaning *complete*{order_ref}! Everything is fresh and spotless.",
                            f"Thank you for choosing us! 🙏\nWe hope you love the results. See you next time! ✨",
                        ),
                        "fitness": _msgs(
                            f"✅ Your session{order_ref} is *confirmed*! Get ready to work hard 💪",
                            f"💪 Your trainer is getting set up{order_ref}. Almost time!",
                            f"💪 Your session{order_ref} is *ready to begin*! Let's go!",
                            f"💪 Your session{order_ref} is *ready to begin*! Let's go!",
                            f"💪 Your session{order_ref} is *ready to begin*! Let's go!",
                            f"Great session! 💪\nThank you for training with us. Keep up the great work and see you next time!",
                        ),
                        "hotel": _msgs(
                            f"✅ Your booking{order_ref} is *confirmed*! We're preparing for your arrival.",
                            f"🏨 Your room{order_ref} is being prepared. Almost ready!",
                            f"🏨 Your room{order_ref} is *ready*! Welcome — we hope you enjoy your stay 😊",
                            f"🏨 Your room{order_ref} is *ready*! Welcome — we hope you enjoy your stay 😊",
                            f"🏨 Your room{order_ref} is *ready*! Welcome — we hope you enjoy your stay 😊",
                            f"Thank you for staying with us! 🙏\nWe hope you had a wonderful experience and look forward to welcoming you back. 🏨",
                        ),
                        "events": _msgs(
                            f"✅ Your event booking{order_ref} is *confirmed*! We're excited to make it special.",
                            f"🎉 We're setting everything up{order_ref}. Almost ready!",
                            f"🎉 Everything is *set up and ready*{order_ref}! Let's celebrate!",
                            f"🎉 Everything is *set up and ready*{order_ref}! Let's celebrate!",
                            f"🎉 Everything is *set up and ready*{order_ref}! Let's celebrate!",
                            f"Thank you for celebrating with us! 🎉\nWe hope it was everything you dreamed of. See you at the next one!",
                        ),
                        "healthcare": _msgs(
                            f"✅ Your appointment{order_ref} is *confirmed*.",
                            f"🩺 The practitioner will be with you shortly{order_ref}.",
                            f"🩺 We're *ready* for you{order_ref}. Please come in.",
                            f"🩺 We're *ready* for you{order_ref}. Please come in.",
                            f"🩺 We're *ready* for you{order_ref}. Please come in.",
                            f"Thank you for visiting us. 🙏\nWe hope you feel better soon. Take care!",
                        ),
                        "rental": _msgs(
                            f"✅ Your rental{order_ref} is *confirmed*! We're getting it ready for you.",
                            f"🔑 Your rental{order_ref} is being prepared and inspected.",
                            f"🔑 Your rental{order_ref} is *ready*! Come pick it up 😊",
                            f"🚗 Your rental{order_ref} is *on its way* to you!",
                            f"🔑 Your rental{order_ref} is *ready* for pickup!",
                            f"Thank you for renting with us! 🙏\nWe hope you had a great experience. See you next time!",
                        ),
                        "creator": _msgs(
                            f"✅ Your project{order_ref} is *confirmed*! We'll get started right away.",
                            f"🎨 We're working on your project{order_ref}. Progress is looking great!",
                            f"🎨 Your project{order_ref} is *complete* and ready for delivery!",
                            f"🎨 Your project{order_ref} is *complete* and on its way!",
                            f"🎨 Your project{order_ref} is *complete* and ready!",
                            f"Thank you for working with us! 🙏\nWe hope you love the final result. Looking forward to the next project together! 🎨",
                        ),
                        "retail": _msgs(
                            f"✅ Your order{order_ref} is *confirmed*! We're packing it up for you.",
                            f"📦 Your order{order_ref} is being packed and quality-checked.",
                            f"✅ Your order{order_ref} is *ready*!",
                            f"🚗 Your order{order_ref} is *on its way*!",
                            f"🛍️ Your order{order_ref} is *packed and ready* for pickup!",
                            f"Thank you for shopping with us! 🙏\nWe hope you love your purchase. See you next time! 🛍️",
                        ),
                    }

                    # Fall back to general for unknown business types
                    msgs = templates.get(biz_type) or _msgs(
                        f"✅ Your order{order_ref} has been *confirmed*! We're getting it ready for you.",
                        f"⏳ Your order{order_ref} is now being *processed*. Won't be long!",
                        f"🎉 Your order{order_ref} is *ready*! Enjoy 😊",
                        f"🎉 Your order{order_ref} is *ready* and on its way!",
                        f"✅ Your order{order_ref} is *ready* for pickup!",
                        f"Thank you so much for your support! 🙏\nWe really appreciate your business and hope to serve you again soon. Have a wonderful day! 😊",
                    )

                    msg = msgs.get(new_status)
                    if msg:
                        ws = get_whatsapp_service(db)
                        await ws.send_message(
                            user_id=business_id,
                            to_number=customer_phone,
                            message=msg,
                            send_context="order_progress",
                        )
        except Exception as e:
            logging.warning(f"[update_order_progress] Failed to send progress WhatsApp: {e}")

    return {"fulfillment_status": order.get("fulfillment_status", "New"), "assigned_to": order.get("assigned_to")}


@api_router.get("/settings/staff")
async def get_staff(user = Depends(get_current_user)):
    """Get the staff list for the current business."""
    business_id = user.get("business_id", user["_id"])
    doc = await db.settings.find_one({"user_id": business_id})
    staff = (doc or {}).get("staff_list", [])
    return {"staff": staff}


@api_router.post("/settings/staff")
async def add_staff(body: dict, user = Depends(get_current_user)):
    """Add a staff member (name only) to the staff list."""
    business_id = user.get("business_id", user["_id"])
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    staff_id = str(uuid.uuid4())
    await db.settings.update_one(
        {"user_id": business_id},
        {"$push": {"staff_list": {"id": staff_id, "name": name}}},
        upsert=True,
    )
    return {"id": staff_id, "name": name}


@api_router.delete("/settings/staff/{staff_id}")
async def remove_staff(staff_id: str, user = Depends(get_current_user)):
    """Remove a staff member from the staff list."""
    business_id = user.get("business_id", user["_id"])
    await db.settings.update_one(
        {"user_id": business_id},
        {"$pull": {"staff_list": {"id": staff_id}}},
    )
    return {"message": "removed"}


@api_router.delete("/orders/{order_id}")
async def delete_order(order_id: str, user = Depends(get_current_user)):
    """Delete an order"""
    from bson import ObjectId
    business_id = user.get("business_id", user["_id"])
    result = await db.orders.delete_one({"_id": order_id, "user_id": business_id})
    if result.deleted_count == 0:
        try:
            result = await db.orders.delete_one({"_id": ObjectId(order_id), "user_id": business_id})
        except Exception:
            pass
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": "Order deleted successfully"}


async def _insert_sale_from_order_document(order: dict, user: dict, business_id: str, payment_method: str) -> str:
    """
    Insert a sales row for a paid order and update customer CRM stats.
    Used when marking an order Paid (web/mobile) and when converting an order to a sale.
    """
    items = order.get("items") or []
    order_item = (
        order.get("product")
        or order.get("product_name")
        or (", ".join(it.get("product_name", "") for it in items if it.get("product_name")) if items else None)
        or "Order"
    )
    order_amount = float(order.get("total_amount") or order.get("total") or 0)
    sale_id = str(uuid.uuid4())
    sale_doc = {
        "_id": sale_id,
        "user_id": business_id,
        "recorded_by": user["_id"],
        "customer_id": order["customer_id"],
        "item": order_item,
        "amount": order_amount,
        "payment_method": payment_method,
        "receipt_sent": False,
        "is_credit": False,
        "due_date": None,
        "paid_date": None,
        "created_at": datetime.utcnow(),
        "source_order_id": str(order["_id"]),
    }
    await db.sales.insert_one(sale_doc)

    if order.get("customer_id") != "walk-in":
        customer = await db.customers.find_one({"_id": order["customer_id"]})
        if customer:
            update_ops = {
                "$inc": {"purchase_count": 1, "total_spent": order_amount},
                "$set": {"last_contacted": datetime.utcnow()},
            }
            if customer.get("tag") == "New":
                update_ops["$set"]["tag"] = "Returning"
            await db.customers.update_one(
                {"_id": order["customer_id"]},
                update_ops,
            )
    return sale_id


@api_router.post("/orders/{order_id}/convert-to-sale", response_model=SaleResponse)
async def convert_order_to_sale(order_id: str, payment_method: str, user = Depends(get_current_user)):
    """Convert a paid order to a sale (or clear the order if a sale was already created when marking Paid)."""
    from bson import ObjectId
    business_id = user.get("business_id", user["_id"])
    order = await db.orders.find_one({"_id": order_id, "user_id": business_id})
    if not order:
        try:
            order = await db.orders.find_one({"_id": ObjectId(order_id), "user_id": business_id})
        except Exception:
            pass
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    paid = (order.get("payment_status") or "").strip().lower() == "paid"
    if not paid:
        raise HTTPException(status_code=400, detail="Only paid orders can be converted to sales")

    # Sale already created when the order was marked Paid — only remove the order from the queue
    if order.get("sale_id"):
        existing = await db.sales.find_one({"_id": order["sale_id"], "user_id": business_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Linked sale not found")
        if order["customer_id"] == "walk-in":
            customer_name = "Walk-in Customer"
            customer_phone = "N/A"
        else:
            customer = await db.customers.find_one({"_id": order["customer_id"]})
            if not customer:
                raise HTTPException(status_code=404, detail="Customer not found")
            customer_name = customer["name"]
            customer_phone = customer["phone_number"]
        await db.orders.delete_one({"_id": order["_id"]})
        return SaleResponse(
            id=existing["_id"],
            user_id=existing["user_id"],
            customer_id=existing["customer_id"],
            customer_name=customer_name,
            customer_phone=customer_phone,
            item=existing["item"],
            amount=float(existing["amount"]),
            payment_method=existing.get("payment_method"),
            receipt_sent=existing.get("receipt_sent", False),
            is_credit=existing.get("is_credit", False),
            due_date=existing.get("due_date"),
            paid_date=existing.get("paid_date"),
            created_at=existing["created_at"],
        )

    # Get customer info for response
    if order["customer_id"] == "walk-in":
        customer_name = "Walk-in Customer"
        customer_phone = "N/A"
    else:
        customer = await db.customers.find_one({"_id": order["customer_id"]})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer_name = customer["name"]
        customer_phone = customer["phone_number"]

    items = order.get("items") or []
    order_item = (
        order.get("product")
        or order.get("product_name")
        or (", ".join(it.get("product_name", "") for it in items if it.get("product_name")) if items else None)
        or "Order"
    )
    order_amount = float(order.get("total_amount") or order.get("total") or 0)

    sale_id = await _insert_sale_from_order_document(order, user, business_id, payment_method)
    sale_doc = await db.sales.find_one({"_id": sale_id})

    await db.orders.delete_one({"_id": order["_id"]})

    return SaleResponse(
        id=sale_id,
        user_id=business_id,
        customer_id=order["customer_id"],
        customer_name=customer_name,
        customer_phone=customer_phone,
        item=order_item,
        amount=order_amount,
        payment_method=payment_method,
        receipt_sent=False,
        is_credit=False,
        due_date=None,
        paid_date=None,
        created_at=sale_doc["created_at"],
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


# ============ PRODUCT ENDPOINTS ============

class ProductResponse(BaseModel):
    id: str
    name: str
    price: float = 0.0
    discount_price: Optional[float] = None
    category: str = "Other"
    sub_category: Optional[str] = None
    image_url: Optional[str] = None
    images: List[str] = []
    description: Optional[str] = None
    in_stock: bool = True
    stock_quantity: Optional[int] = None
    unit: Optional[str] = None
    moq: Optional[int] = None
    pricing_tiers: Optional[List[dict]] = None
    created_at: datetime

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
            sub_category=p.get("sub_category"),
            image_url=orig,
            images=imgs,
            description=p.get("description"),
            in_stock=p.get("in_stock", True),
            stock_quantity=p.get("stock_quantity"),
            unit=p.get("unit") or None,
            moq=p.get("moq"),
            pricing_tiers=p.get("pricing_tiers") or None,
            created_at=p.get("created_at", datetime.utcnow())
        ))
    return result

class ProductCreate(BaseModel):
    name: str = "New Product"
    price: float = 0.0
    discount_price: Optional[float] = None
    category: str = "Other"
    sub_category: Optional[str] = None
    image_url: Optional[str] = None
    images: List[str] = []
    description: Optional[str] = None
    in_stock: bool = True
    stock_quantity: Optional[int] = None
    variants: Optional[List[dict]] = None          # [{name, price}]
    modifier_groups: Optional[List[dict]] = None   # [{name, required, multi_select, options:[{name, price_delta}]}]
    unit: Optional[str] = None                     # e.g. "per kg", "per carton" — grocery/wholesale
    moq: Optional[int] = None                      # minimum order quantity — wholesale
    pricing_tiers: Optional[List[dict]] = None     # [{min_qty, price}] bulk pricing — wholesale

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    discount_price: Optional[float] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    description: Optional[str] = None
    in_stock: Optional[bool] = None
    stock_quantity: Optional[int] = None
    variants: Optional[List[dict]] = None          # [{name, price}]
    modifier_groups: Optional[List[dict]] = None   # [{name, required, multi_select, options:[{name, price_delta}]}]
    unit: Optional[str] = None                     # e.g. "per kg", "per carton" — grocery/wholesale
    moq: Optional[int] = None                      # minimum order quantity — wholesale
    pricing_tiers: Optional[List[dict]] = None     # [{min_qty, price}] bulk pricing — wholesale

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
        "sub_category": product.sub_category,
        "image_url": product.image_url,
        "images": images,
        "description": clean_description,
        "in_stock": product.in_stock,
        "stock_quantity": product.stock_quantity,
        "variants": product.variants or [],
        "modifier_groups": product.modifier_groups or [],
        "unit": product.unit or "",
        "moq": product.moq or 1,
        "pricing_tiers": product.pricing_tiers or [],
        "created_at": datetime.utcnow()
    }

    await db.products.insert_one(product_doc)
    
    return ProductResponse(
        id=product_doc["_id"],
        name=product_doc["name"],
        price=product_doc["price"],
        discount_price=product_doc["discount_price"],
        category=product_doc["category"],
        sub_category=product_doc.get("sub_category"),
        image_url=product_doc["image_url"],
        images=product_doc["images"],
        description=product_doc["description"],
        in_stock=product_doc["in_stock"],
        stock_quantity=product_doc["stock_quantity"],
        unit=product_doc.get("unit") or None,
        moq=product_doc.get("moq"),
        pricing_tiers=product_doc.get("pricing_tiers") or None,
        created_at=product_doc["created_at"]
    )

@api_router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: str, updates: ProductUpdate, user = Depends(get_current_user)):
    """Update a product"""
    # Create update dict excluding None values
    update_data = {k: v for k, v in updates.dict().items() if v is not None}
    
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
        sub_category=result.get("sub_category"),
        image_url=orig,
        images=imgs,
        description=result.get("description"),
        in_stock=result.get("in_stock", True),
        stock_quantity=result.get("stock_quantity"),
        unit=result.get("unit") or None,
        moq=result.get("moq"),
        pricing_tiers=result.get("pricing_tiers") or None,
        created_at=result["created_at"]
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
        "features": ["2,500 messages/month", "Unlimited customers", "Follow-ups & broadcasts", "AI replies"]
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
# Anchor: KES 1400 / 3000 / 5000  ≈  USD 10.80 / 23.20 / 38.60
REGIONAL_PRICING = {
    # East Africa
    "KES": (1400, 3000, 5000),       # Kenya
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
    package_name = GOOGLE_PLAY_PACKAGE_NAME
    sa_key_path = os.environ.get('GOOGLE_SA_KEY_PATH', '')

    if not package_name:
        logging.warning("GOOGLE_PLAY_PACKAGE_NAME not set — skipping server verification")
        return {"valid": True, "reason": "no_server_config"}

    if not sa_key_path or not os.path.exists(sa_key_path):
        logging.warning("GOOGLE_SA_KEY_PATH not set or file missing — skipping server verification")
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
    return {
        "subscription_plan": user.get("subscription_plan"),
        "subscription_active": user.get("subscription_active", False),
        "subscription_date": user.get("subscription_date"),
        "extra_credits": user.get("extra_credits", 0),
    }

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
async def delete_account(request: Request):
    """
    Permanently delete user account and all associated data.
    Required for GDPR/CCPA compliance and app store policies.
    """
    # Manually extract user so we can handle already-deleted accounts gracefully
    from fastapi.security import HTTPBearer as _HTTPBearer
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header.split(" ", 1)[1]
    try:
        payload = verify_token(token)
    except HTTPException:
        raise

    user_id = payload["user_id"]
    user = await db.users.find_one({"_id": user_id})

    # If account is already gone (e.g. prior attempt crashed after delete), still clean up
    # any leftover team_members/settings records keyed by phone or user_id, then return success
    if not user:
        phone_number = payload.get("phone_number", "")
        if phone_number:
            await db.team_members.delete_many({"phone_number": phone_number})
        await db.team_members.delete_many({"business_id": user_id})
        await db.settings.delete_many({"user_id": user_id})
        return {"status": "success", "message": "Account already deleted"}
    whatsapp_service = get_whatsapp_service(db)
    instance_name = (
        (user.get("whatsapp") or {}).get("instance_name")
        or whatsapp_service._instance_name(user_id)
    )

    # Fire-and-forget Evolution cleanup — do NOT await so the response returns fast.
    # Awaiting Evolution API (15s timeout + retries) caused Render to time out the request,
    # which triggered the mobile app's offline queue to fake a success without actually deleting.
    async def _cleanup_evolution():
        try:
            await whatsapp_service.disconnect_instance(user_id)
            logging.info(f"Account deletion: Evolution instances removed for user {user_id}")
        except Exception as e:
            logging.warning(f"Account deletion: Evolution cleanup failed for {user_id}: {e}")
    asyncio.create_task(_cleanup_evolution())

    # Delete all user data from every collection (user_id and business_id are the same for owners)
    await db.customers.delete_many({"user_id": user_id})
    await db.messages.delete_many({"user_id": user_id})
    await db.sales.delete_many({"user_id": user_id})
    await db.expenses.delete_many({"user_id": user_id})
    await db.followups.delete_many({"user_id": user_id})
    await db.orders.delete_many({"user_id": user_id})
    await db.products.delete_many({"user_id": user_id})
    await db.broadcasts.delete_many({"user_id": user_id})
    await db.broadcast_templates.delete_many({"user_id": user_id})
    await db.broadcast_automations.delete_many({"user_id": user_id})
    await db.transactions.delete_many({"user_id": user_id})
    await db.customer_analysis.delete_many({"user_id": user_id})
    await db.pending_classifications.delete_many({"user_id": user_id})
    await db.pending_catalogs.delete_many({"user_id": user_id})
    await db.settings.delete_many({"user_id": user_id})
    await db.bookings.delete_many({"user_id": user_id})
    await db.customer_groups.delete_many({"user_id": user_id})
    await db.followup_events.delete_many({"user_id": user_id})
    await db.conversation_memory.delete_many({"user_id": user_id})
    await db.activity_logs.delete_many({"business_id": user_id})
    await db.conversation_assignments.delete_many({"business_id": user_id})
    await db.team_members.delete_many({"business_id": user_id})
    await db.wa_auth_sessions.delete_many({"user_id": user_id})

    # Delete the user record itself
    await db.users.delete_one({"_id": user_id})

    logging.info(f"Account deleted for user {user_id}")
    return {"status": "success", "message": "Account and all data permanently deleted"}


@api_router.post("/admin/cleanup-instance")
async def force_cleanup_evolution_instance(request: Request, user = Depends(get_current_user)):
    """
    Force-delete a stuck Evolution API instance by name or by user_id.
    Use this when an account was deleted but its WhatsApp instance remains in Evolution API.
    Body: { "instance_name": "user_abc123" }  OR  { "user_id": "abc-123" }
    """
    body = await request.json()
    instance_name = body.get("instance_name")
    target_user_id = body.get("user_id")

    if not instance_name and not target_user_id:
        raise HTTPException(status_code=400, detail="Provide either instance_name or user_id")

    if not instance_name:
        # Derive from user_id using the same formula as whatsapp_service
        instance_name = f"user_{target_user_id.replace('-', '_')}"

    results = {}
    try:
        import httpx as _httpx
        evo_base = os.environ.get('EVOLUTION_API_URL', 'http://localhost:8080').rstrip('/')
        evo_headers = {"apikey": os.environ.get('EVOLUTION_API_KEY', '')}
        async with _httpx.AsyncClient(timeout=15) as client:
            # Step 1: logout (unlinks WhatsApp session)
            logout_resp = await client.delete(f"{evo_base}/instance/logout/{instance_name}", headers=evo_headers)
            results["logout"] = logout_resp.status_code
            await asyncio.sleep(1)
            # Step 2: delete the instance record
            delete_resp = await client.delete(f"{evo_base}/instance/delete/{instance_name}", headers=evo_headers)
            results["delete"] = delete_resp.status_code
            results["delete_body"] = delete_resp.text[:300]
    except Exception as e:
        results["error"] = str(e)

    success = results.get("delete") in (200, 201, 404)
    logging.info(f"Force cleanup instance {instance_name}: {results}")
    return {
        "instance_name": instance_name,
        "success": success,
        "results": results,
        "note": "404 on delete means it was already gone — that is fine." if results.get("delete") == 404 else None,
    }

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
    """
    logging.info(f"WhatsApp sync requested by user {user['_id']}")
    whatsapp_service = get_whatsapp_service(db)
    status = await whatsapp_service.get_instance_status(user["_id"])
    if not status.get("connected"):
        raise HTTPException(status_code=400, detail="WhatsApp not connected")

    contacts_result = await whatsapp_service.fetch_contacts(user["_id"])
    logging.info(f"Contact sync result: {contacts_result}")
    history_result = await whatsapp_service.fetch_chat_history(user["_id"])
    logging.info(f"History sync result: {history_result}")

    # Get current DB totals so user sees actual state
    total_customers = await db.customers.count_documents({"user_id": user["_id"]})
    total_messages = await db.messages.count_documents({"user_id": user["_id"]})
    synced_messages = await db.messages.count_documents({"user_id": user["_id"], "synced_from_history": True})

    # Run AI classification in background to avoid blocking the sync response
    async def _classify_after_sync(uid):
        classified = 0
        try:
            classifier = get_classifier(db)
            customers = await db.customers.find({"user_id": uid}).to_list(None)
            for c in customers:
                msg_count = await db.messages.count_documents({"customer_id": c["_id"], "user_id": uid})
                if msg_count >= 2:
                    await classifier.classify_contact(uid, c["_id"])
                    classified += 1
        except Exception as e:
            logging.error(f"Post-sync classification error: {e}")
        logging.info(f"Post-sync classification done: {classified} contacts classified for user {uid}")

    asyncio.create_task(_classify_after_sync(user["_id"]))

    # Fetch profile pictures in background
    async def _fetch_pics(uid):
        try:
            ws = get_whatsapp_service(db)
            result = await ws.fetch_profile_pictures_bulk(uid)
            logging.info(f"Profile pictures: {result}")
        except Exception as e:
            logging.error(f"Profile picture fetch error: {e}")
    asyncio.create_task(_fetch_pics(user["_id"]))

    return {
        "status": "success",
        "contacts": contacts_result,
        "history": history_result,
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

    async def _proxy_url(url: str):
        """Try to fetch an image URL and return Response, or None if it fails."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                img_resp = await client.get(url)
                if img_resp.status_code == 200 and img_resp.headers.get("content-type", "").startswith("image/"):
                    return FastAPIResponse(
                        content=img_resp.content,
                        media_type=img_resp.headers.get("content-type", "image/jpeg"),
                        headers={"Cache-Control": "public, max-age=3600"},
                    )
        except Exception:
            pass
        return None

    # Step 1: Try the stored URL (it may still be valid if fetched recently)
    stored_url = customer_full.get("profile_picture") if customer_full else None
    if stored_url:
        result = await _proxy_url(stored_url)
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
        result = await _proxy_url(pic_url)
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
                    {"name": {"$regex": "^Customer [0-9]"}},
                    {"name": {"$regex": "^[+][0-9]"}},
                    {"name": {"$regex": "^[0-9]"}},
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

                import re as _re2
                is_still_fallback = bool(_re2.match(r'^(Contact|Customer)\s+\d+$', new_name))
                if new_name and not is_still_fallback:
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
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Total unread messages — only from confirmed customers (is_customer: True)
    customer_ids_for_unread = await db.customers.distinct(
        "_id",
        {"user_id": uid, "is_customer": True}
    )
    unread_count = await db.messages.count_documents({
        "user_id": uid, "direction": "incoming", "read": {"$ne": True},
        "customer_id": {"$in": customer_ids_for_unread}
    })

    # Today's follow-ups — widen window by ±1 day to cover all timezones (UTC-12 to UTC+14)
    tz_window_start = today_start - timedelta(hours=14)
    tz_window_end = today_end + timedelta(hours=14)
    followups_today = await db.followups.count_documents({
        "user_id": uid, "status": "pending",
        "reminder_date": {"$gte": tz_window_start, "$lt": tz_window_end}
    })

    # Today's sales total
    sales_pipeline = [
        {"$match": {"user_id": uid, "created_at": {"$gte": today_start, "$lt": today_end}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    sales_result = await db.sales.aggregate(sales_pipeline).to_list(1)
    sales_today = sales_result[0]["total"] if sales_result else 0
    sales_count = sales_result[0]["count"] if sales_result else 0

    # Today's bookings count
    bookings_today = await db.bookings.count_documents({
        "user_id": uid,
        "created_at": {"$gte": today_start, "$lt": today_end},
        "status": {"$nin": ["cancelled"]}
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
            # Redis SET NX is atomic — safe across multiple server instances.
            # Falls back to asyncio lock + in-memory dict when Redis is unavailable.
            import hashlib as _hl

            _evo_id = parsed.get("evo_message_id", "")
            _body_content = parsed.get("body", "") or ""
            _u_id = parsed.get("user", {}).get("_id", "unknown")
            _cust_id_dedup = parsed.get("from_number", "unknown")

            # ALWAYS check content-hash first (10s TTL).
            # Evolution API fires the same message twice: once without evo_message_id
            # (uses content hash key) and once with it (uses evo_id key).
            # Without this, both calls use different keys and both pass dedup.
            _content_key = f"{_u_id}:{_cust_id_dedup}:{_hl.md5(_body_content.encode()).hexdigest()[:16]}"
            if not await _dedup_check_and_set(_content_key, 10):
                logging.info(f"Webhook dedup (content): skipping duplicate key={_content_key[:40]}")
                return {"status": "ok"}
            # Also check evo_id key if present (longer TTL for cross-instance safety)
            if _evo_id:
                if not await _dedup_check_and_set(_evo_id, _AUTO_REPLY_DEDUP_TTL):
                    logging.info(f"Webhook dedup (evo_id): skipping duplicate key={_evo_id[:40]}")
                    return {"status": "ok"}
            # === END DEDUPLICATION GUARD ===

            log_trace(f"Parsed body: {parsed.get('body')}")
            
            user = parsed["user"]
            from_number = parsed["from_number"]
            body = parsed["body"]
            push_name = parsed["push_name"]
            from_me = parsed.get("from_me", False)
            evo_msg_id_log = parsed.get("evo_message_id", "?")
            direction = "outgoing" if from_me else "incoming"
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
                # Auto-update fallback names when WhatsApp push_name is available
                existing_name = customer.get("name", "")
                import re as _re
                is_fallback = (
                    existing_name == from_number or
                    _re.match(r'^(Customer|Contact)\s+\d+$', existing_name) is not None
                )
                name_update = {}
                if push_name and is_fallback:
                    name_update["name"] = push_name
                    customer_name = push_name
                contact_update = {
                    "last_message": body[:200] if body else None,
                    **lid_update,
                    **name_update,
                }
                if from_me:
                    contact_update["last_contacted"] = datetime.utcnow()
                    contact_update["last_owner_reply"] = datetime.utcnow()
                await db.customers.update_one(
                    {"_id": customer["_id"]},
                    {"$set": contact_update}
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
                if from_me:
                    existing = None
                    # Primary lookup: by evo_message_id
                    if evo_msg_id:
                        existing = await db.messages.find_one({
                            "evo_message_id": evo_msg_id,
                            "user_id": user["_id"],
                        })
                    # Fallback: send_message() stores BEFORE calling Evolution API,
                    # so evo_message_id may not be set yet when this webhook fires.
                    # Match by content + direction + recency (last 30s) instead.
                    if not existing and body:
                        _dedup_cutoff = datetime.utcnow() - __import__("datetime").timedelta(seconds=30)
                        existing = await db.messages.find_one({
                            "user_id": user["_id"],
                            "customer_id": customer_id,
                            "direction": "outgoing",
                            "content": body,
                            "created_at": {"$gte": _dedup_cutoff},
                        })
                    if existing:
                        print(f"DEBUG: Outgoing message already exists (send_context={existing.get('send_context','?')}), skipping AI")
                        # Back-fill evo_message_id if missing (fixes the race window)
                        if evo_msg_id and not existing.get("evo_message_id"):
                            await db.messages.update_one(
                                {"_id": existing["_id"]},
                                {"$set": {"evo_message_id": evo_msg_id}}
                            )
                        # Only pause auto-reply when the OWNER manually typed this message.
                        # Bot-sent messages (auto_reply, broadcast, etc.) must NOT set owner_reply
                        # or they will lock out the bot for 15 minutes after every auto-reply.
                        if existing.get("send_context", "manual") == "manual":
                            await _redis_set_ts(f"{user['_id']}:{from_number}:owner_reply", _OWNER_ATTENTION_TTL)
                            logging.info(f"Owner manually replied to {from_number} — auto-reply paused 15 min")
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

                # Store push_name on incoming messages so name backfill can use it
                if not from_me and push_name:
                    msg_doc["push_name"] = push_name

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

                native_update = {"last_message": body[:200] if body else ""}
                if from_me:
                    native_update["last_contacted"] = datetime.utcnow()
                    native_update["last_owner_reply"] = datetime.utcnow()
                await db.customers.update_one(
                    {"_id": customer_id},
                    {"$set": native_update}
                )

                # Real-time: re-analyse this customer immediately on incoming message
                if not from_me and customer_id:
                    async def _realtime_analyze(uid, cid):
                        try:
                            from daily_analyzer import DailyCustomerAnalyzer
                            analyzer = DailyCustomerAnalyzer(db)
                            analysis = await analyzer.analyze_single_customer(cid, uid)
                            if analysis:
                                today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                                analysis["show_date"] = today
                                analysis["analysis_date"] = datetime.utcnow()
                                # Upsert — replace today's analysis for this customer
                                await db.customer_analysis.delete_one({
                                    "user_id": uid,
                                    "customer_id": cid,
                                    "show_date": {"$gte": today},
                                })
                                await db.customer_analysis.insert_one(analysis)
                        except Exception as e:
                            logging.debug(f"Real-time analysis failed for {cid}: {e}")
                    asyncio.create_task(_realtime_analyze(user["_id"], customer_id))

                # For outgoing messages (typed in WhatsApp), just store — no auto-reply needed
                if from_me:
                    # Mark all unread incoming messages from this customer as read
                    await db.messages.update_many(
                        {"user_id": user["_id"], "customer_id": customer_id, "direction": "incoming", "read": {"$ne": True}},
                        {"$set": {"read": True}}
                    )
                    # Only clear menu state when the OWNER manually replies from their phone.
                    # Do NOT clear it for bot-sent messages — the bot saves menu state AFTER
                    # sending and Evolution API fires this from_me webhook almost immediately,
                    # which would wipe the menu before the customer can select anything.
                    # We detect owner vs bot by checking the owner-attention Redis key:
                    # if the owner was NOT already handling this chat, this is a bot message.
                    import time as _fm_t
                    _owner_ts = await _redis_get_ts(f"{user['_id']}:{from_number}:owner_reply")
                    _owner_active = (_fm_t.time() - _owner_ts) < _OWNER_ATTENTION_TTL
                    if customer_id and _owner_active:
                        try:
                            from agents.conversation_state import save_state as _save_state
                            await _save_state(db, user["_id"], customer_id, {
                                "active_menu": False,
                                "waiting_for_selection": False,
                                "menu_items": {},
                                "menu_type": None,
                            })
                        except Exception:
                            pass
                    return {"status": "ok"}

                # ── PAYMENT SCREENSHOT AUTO-VERIFICATION ──────────────────
                # If this incoming image has a pending payment verification,
                # spawn AI verification instead of routing through agent.
                if parsed.get("image_url") and customer_id:
                    from agents.conversation_state import load_state as _load_cs
                    _cs = await _load_cs(db, user["_id"], str(customer_id))
                    if _cs.get("pending_payment_verification"):
                        logging.info(f"[PaymentVerify] Spawning verification for {customer_id}")
                        asyncio.create_task(
                            _verify_payment_and_respond(
                                db=db,
                                image_url=parsed["image_url"],
                                user=user,
                                customer_id=str(customer_id),
                                customer_name=customer_name,
                                from_number=from_number,
                                conv_state=_cs,
                            )
                        )
                        return {"status": "ok", "handled_by": "payment_verification"}
                # ── END PAYMENT VERIFICATION ───────────────────────────────

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
                
                # ============================================================
                # OWNER ATTENTION COOLDOWN
                # If owner manually replied to this contact within last 15 min,
                # block AI — owner is handling it.
                # After 15 min with no new owner reply, AI resumes automatically.
                # ============================================================
                import time as _t_owner
                _loop_key = f"{user['_id']}:{from_number}"
                _now_loop = _t_owner.time()
                _owner_reply_ts = await _redis_get_ts(f"{_loop_key}:owner_reply")
                _time_since_owner = _now_loop - _owner_reply_ts
                _owner_handling = _owner_reply_ts > 0 and _time_since_owner < _OWNER_ATTENTION_TTL
                if _owner_handling:
                    _mins_left = int((_OWNER_ATTENTION_TTL - _time_since_owner) / 60) + 1
                    logging.info(f"Auto-reply PAUSED for {from_number} — owner replied {int(_time_since_owner/60)}m ago, {_mins_left}m left")
                    return {"status": "ok", "message": "owner attention: auto-reply paused"}
                # If owner replied but 15 min passed — flag it so AI knows to handle carefully
                _owner_was_handling = _owner_reply_ts > 0 and _time_since_owner >= _OWNER_ATTENTION_TTL

                # ============================================================
                # STOP / START opt-out (must be checked before auto-reply gate)
                # ============================================================
                _body_opt = body.strip().lower()
                if _body_opt == "stop":
                    if customer_id:
                        await db.customers.update_one(
                            {"_id": customer_id},
                            {"$set": {"auto_reply": False, "unsubscribed_at": datetime.utcnow()}}
                        )
                    ws_opt = get_whatsapp_service(db)
                    await ws_opt.send_message(
                        user_id=user["_id"], to_number=from_number,
                        message="You've been unsubscribed from automated replies. Reply *START* to re-enable anytime.",
                        send_context="opt_out"
                    )
                    return {"status": "ok", "handled_by": "stop"}
                if _body_opt == "start":
                    if customer_id:
                        await db.customers.update_one(
                            {"_id": customer_id},
                            {"$set": {"auto_reply": True}, "$unset": {"unsubscribed_at": ""}}
                        )
                    ws_opt = get_whatsapp_service(db)
                    await ws_opt.send_message(
                        user_id=user["_id"], to_number=from_number,
                        message="You're back! Automated replies are now enabled. 👋",
                        send_context="opt_in"
                    )
                    return {"status": "ok", "handled_by": "start"}

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

                # ============================================================
                # AGENT-BASED PIPELINE
                # ============================================================

                # Check if this is a personal contact
                is_personal = customer.get("is_personal", False) if customer else False

                # Fetch recent message history (last 20) for full conversation context
                history = []
                if customer_id:
                    recent_msgs = await db.messages.find({
                        "user_id": user["_id"],
                        "customer_id": customer_id
                    }).sort("created_at", -1).limit(20).to_list(20)
                    history = [
                        {"direction": m["direction"], "content": m["content"]}
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
                            if _pm.get("details"):
                                _line += f": {_pm['details']}"
                        else:
                            _line = str(_pm)
                        if _line.strip():
                            _pm_lines.append(f"  - {_line}")
                    if _pm_lines:
                        _bk_parts.append("Payment methods accepted:\n" + "\n".join(_pm_lines))
                _business_knowledge = "\n".join(_bk_parts) if _bk_parts else ""

                # Currency: settings sub-doc → top-level user doc → phone-number detection → USD
                currency = (
                    _user_settings.get("currency")
                    or user.get("currency")
                    or __import__("country_utils").get_payment_methods_for_country(
                        __import__("country_utils").detect_country_from_phone(user.get("phone_number", ""))
                    )["currency"]
                )
                _business_type = _user_settings.get("business_type") or user.get("business_type", "")
                _raw_pm_ctx = user.get("payment_methods") or []
                _payment_methods_ctx = [
                    m if isinstance(m, dict) else {"name": str(m), "details": ""}
                    for m in _raw_pm_ctx
                ]
                agent_context = {
                    "currency": currency,
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "is_personal": is_personal,
                    "history": history,
                    "business_knowledge": _business_knowledge,
                    "business_name": user.get("business_name", ""),
                    "ai_model": _user_settings.get("ai_model", "standard"),
                    "business_type": _business_type,
                    "owner_was_handling": _owner_was_handling,  # owner replied but stepped away >15min ago
                    "payment_methods": _payment_methods_ctx,
                }

                # ── AUTOREPLY V2 ENGINE ────────────────────────────────────
                # Stateless AI + 5-field mini-state. Replaces the old
                # pre-router + router + agents pipeline.
                # ──────────────────────────────────────────────────────────
                from autoreply.engine import process_message as _v2_process
                _ws_v2 = get_whatsapp_service(db)
                return await _v2_process(
                    db=db,
                    user=user,
                    customer=customer,
                    customer_id=customer_id,
                    message=body,
                    from_number=from_number,
                    whatsapp_service=_ws_v2,
                )

                # Handle order button taps: "order_<product_id>"
                body_lower = body.lower().strip()
                import re as _re
                _order_btn_match = _re.match(r'^order_([a-f0-9-]+)$', body_lower)
                if _order_btn_match:
                    _ordered_pid = _order_btn_match.group(1)
                    _ordered_product = await db.products.find_one({"_id": _ordered_pid, "user_id": user["_id"]})
                    if _ordered_product:
                        currency = user.get("settings", {}).get("currency", "USD")
                        order_id = str(uuid.uuid4())
                        await db.orders.insert_one({
                            "_id": order_id,
                            "user_id": user["_id"],
                            "customer_id": customer_id,
                            "product": _ordered_product["name"],
                            "quantity": 1,
                            "price": _ordered_product.get("price", 0),
                            "total_amount": _ordered_product.get("price", 0),
                            "status": "pending",
                            "created_at": datetime.utcnow()
                        })
                        
                        # Reduce stock if tracked
                        if _ordered_product.get("stock_quantity") is not None:
                            await db.products.update_one(
                                {"_id": _ordered_pid, "stock_quantity": {"$gte": 1}},
                                {"$inc": {"stock_quantity": -1}}
                            )
                        try:
                            ws = get_whatsapp_service(db)
                            price_display = f"{currency} {_ordered_product.get('price', 0):,.0f}"
                            confirm_msg = (
                                f"✅ *Order Confirmed!*\n\n"
                                f"*{_ordered_product['name']}*\n"
                                f"Qty: 1\n"
                                f"💰 Total: {price_display}\n\n"
                                f"Thank you! We'll process your order right away. 🚀"
                            )
                            await ws.send_message(
                                user_id=user["_id"],
                                to_number=from_number,
                                message=confirm_msg,
                                customer_name=customer_name,
                                send_context="order_confirm",
                            )
                        except Exception as e:
                            logging.error(f"Failed to send button order confirmation: {e}")
                        return {"status": "ok", "handled_by": "button_order"}

                # Check if customer is ordering from a catalog
                # body_lower is already defined above
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
                        currency = user.get("settings", {}).get("currency", "USD")
                        order_id = str(uuid.uuid4())
                        await db.orders.insert_one({
                            "_id": order_id,
                            "user_id": user["_id"],
                            "customer_id": customer_id,
                            "product": matched_product["name"],
                            "quantity": 1,
                            "price": matched_product["price"],
                            "total_amount": matched_product["price"],
                            "status": "pending",
                            "created_at": datetime.utcnow()
                        })

                        # Reduce stock if tracked
                        if matched_product.get("id"):
                            await db.products.update_one(
                                {"_id": matched_product["id"], "stock_quantity": {"$exists": True, "$ne": None}, "stock_quantity": {"$gte": 1}},
                                {"$inc": {"stock_quantity": -1}}
                            )
                        
                        try:
                            ws = get_whatsapp_service(db)
                            confirm_msg = (
                                f"✅ *Order Confirmed!*\n\n"
                                f"*{matched_product['name']}*\n"
                                f"Qty: 1\n"
                                f"💰 Total: {currency} {matched_product['price']:,.0f}\n\n"
                                f"Thank you! We'll process your order right away. 🚀"
                            )
                            await ws.send_message(
                                user_id=user["_id"],
                                to_number=from_number,
                                message=confirm_msg,
                                customer_name=customer_name,
                                send_context="order_confirm",
                            )
                        except Exception as e:
                            logging.error(f"Failed to send order confirmation: {e}")
                        
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
                        
                        user_products = await db.products.find({"user_id": user["_id"]}).to_list(50)
                        product_catalog_map = {}  # product_id -> image_url
                        product_name_map = {}     # lowercase product name -> {id, image_url, name}
                        if user_products:
                            currency = (
                                user_settings.get("currency")
                                or user.get("currency")
                                or __import__("country_utils").get_payment_methods_for_country(
                                    __import__("country_utils").detect_country_from_phone(user.get("phone_number", ""))
                                )["currency"]
                            )
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
                            model_pref=user_settings.get("ai_model", "standard")
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
                                            
                                            currency = user.get("settings", {}).get("currency", "USD")
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
    
    update_data = {"last_contacted": datetime.utcnow(), "last_owner_reply": datetime.utcnow()}
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
    # Return all stored fields plus normalized payment_methods and a safe default for business_type
    return {
        **knowledge,
        "business_type": knowledge.get('business_type', 'general'),
        "payment_methods": payment_methods,
    }

@api_router.put("/business-knowledge")
async def update_business_knowledge(knowledge: BusinessKnowledge, user = Depends(get_current_user)):
    """Update business knowledge for AI to use in conversations"""
    update_data = {}
    fields = [
        # Core fields
        'products_services', 'pricing_info', 'business_hours', 'delivery_info',
        'faqs', 'special_offers', 'business_description', 'business_location', 'business_type',
        # Restaurant
        'restaurant_has_dine_in', 'restaurant_has_delivery', 'restaurant_has_takeout',
        'restaurant_table_range', 'restaurant_avg_wait', 'restaurant_min_delivery',
        # Retail
        'retail_has_delivery', 'retail_has_pickup',
        'retail_delivery_fee', 'retail_free_delivery_above',
        'retail_has_custom_orders', 'retail_custom_lead_time', 'retail_return_policy',
        # Bakery
        'bakery_advance_days', 'bakery_deposit_required', 'bakery_deposit_pct',
        # Grocery
        'grocery_delivery_slots', 'grocery_min_order', 'grocery_allow_substitutions',
        # Wholesale
        'wholesale_lead_time', 'wholesale_min_order_value', 'wholesale_payment_terms', 'wholesale_has_credit_account',
        # Salon
        'salon_multiple_stylists', 'salon_stylist_names', 'salon_deposit_required', 'salon_deposit_pct', 'salon_cancellation_policy',
        # Spa
        'spa_has_couples', 'spa_deposit_required', 'spa_deposit_pct', 'spa_cancellation_hours',
        # Repair
        'repair_has_onsite', 'repair_has_dropoff', 'repair_diagnosis_free', 'repair_turnaround', 'repair_warranty',
        # Services
        'services_has_onsite', 'services_has_remote', 'services_quote_first', 'services_deposit_required',
        'services_turnaround', 'services_cancellation_policy',
        # Support
        'support_ticket_prefix', 'support_response_sla', 'support_has_billing_support',
        'support_has_technical_support', 'support_has_complaints', 'support_has_live_handoff',
        'support_escalation_policy', 'support_refund_policy',
        # Hotel
        'hotel_checkin_time', 'hotel_checkout_time', 'hotel_min_nights', 'hotel_deposit_required',
        'hotel_deposit_pct', 'hotel_has_meal_plans', 'hotel_meal_plan_options',
        'hotel_has_airport_transfer', 'hotel_has_spa', 'hotel_has_pool', 'hotel_cancellation_policy',
        # Rental
        'rental_type', 'rental_deposit_required', 'rental_deposit_pct', 'rental_min_nights',
        'rental_checkin_time', 'rental_checkout_time', 'rental_pet_policy',
        'rental_cancellation_policy', 'rental_has_extras',
        # Cleaning
        'cleaning_has_recurring', 'cleaning_has_commercial', 'cleaning_supplies_included',
        # Fitness
        'fitness_has_memberships', 'fitness_has_classes', 'fitness_has_personal_training',
        'fitness_has_trial', 'fitness_class_schedule',
        # Events
        'events_deposit_pct', 'events_lead_time', 'events_delivery_days',
        # Healthcare
        'hc_consultation_fee', 'hc_has_lab_tests', 'hc_has_home_visit',
        'hc_prep_instructions', 'hc_insurance_accepted',
        # Creator
        'creator_niche', 'creator_platforms', 'creator_audience_size',
        'creator_collab_types', 'creator_rate_card', 'creator_whats_included',
        'creator_turnaround', 'creator_booking_process', 'creator_min_budget',
        'creator_blacklisted_niches', 'creator_fan_dm_response', 'creator_media_kit_link',
        'creator_followers', 'creator_lead_time', 'creator_revisions',
        'creator_usage_rights', 'creator_deposit_pct', 'creator_rates_on_request',
    ]
    for field in fields:
        val = getattr(knowledge, field, None)
        if val is not None:
            update_data[f'business_knowledge.{field}'] = val
    if update_data:
        await db.users.update_one({"_id": user["_id"]}, {"$set": update_data})
    return {"status": "success", "message": "Business knowledge updated"}

@api_router.post("/ai/draft-message")
async def draft_ai_message(request: DraftMessageRequest, user = Depends(get_current_user)):
    """Generate AI-drafted follow-up message for a customer"""
    try:
        business_id = user.get("business_id", user["_id"])
        customer = await db.customers.find_one({"_id": request.customer_id, "user_id": business_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        customer_name = customer.get("name", "them")

        # ── Personal mode: skip all business context, just draft a natural reply ──
        if request.mode == "personal":
            raw_msgs = await db.messages.find({
                "customer_id": request.customer_id,
                "user_id": business_id
            }).sort("created_at", 1).limit(20).to_list(20)

            conv_lines = []
            for m in raw_msgs:
                role = customer_name if m["direction"] == "incoming" else "You"
                conv_lines.append(f"{role}: {m['content']}")
            conversation_log = "\n".join(conv_lines) if conv_lines else ""

            last_msg = raw_msgs[-1] if raw_msgs else None
            is_replying = last_msg and last_msg["direction"] == "incoming"
            custom_direction = request.custom_instructions or ""
            model_pref = user.get("settings", {}).get("ai_model", "standard")

            direction_note = f"\nDIRECTION: {custom_direction.strip()}" if custom_direction.strip() else ""

            if is_replying:
                scenario = f'They just said: "{last_msg["content"]}"'
                goal = "Reply naturally to what they said."
            elif conv_lines:
                scenario = "Continue the conversation naturally."
                goal = "Send a follow-up that fits the tone and topic."
            else:
                scenario = "First message to this person."
                goal = "Say something genuine and easy to reply to."

            prompt = f"""You are writing a personal WhatsApp message to {customer_name}.
This is a personal conversation — not business, not sales.

{scenario}
{goal}{direction_note}

Conversation so far:
{conversation_log or "(no prior messages)"}

RULES:
1. Output ONLY the message text. No labels, no explanation.
2. 1-3 sentences max. Casual and warm.
3. Match their language and tone from the conversation.
4. No business talk, no product mentions, no sales pitch.
5. Sound like a real person texting a friend.

Message:"""

            from ai_service import get_drafter
            drafted = await (get_drafter())._call_llm(prompt, model_pref=model_pref)
            drafted = drafted.strip().strip('"').strip("'")
            return DraftMessageResponse(
                message=drafted or f"Hey {customer_name}, how are you?",
                confidence=0.9,
                reason="Personal conversation draft"
            )

        # ── v2 context loader: full catalog + structured business config ──
        from autoreply.context_loader import load_context as _load_ctx
        ctx         = await _load_ctx(db, business_id, request.customer_id, user)
        bc          = ctx["business_config"]
        products    = ctx["products"]
        services    = ctx["services"]
        mini_state  = ctx["mini_state"]
        v2_messages = ctx["messages"]   # last 10, oldest-first (role: customer/assistant)

        user_settings    = user.get("settings", {})
        model_pref       = user_settings.get("ai_model", "standard")
        business_name    = bc.get("name") or user.get("business_name", "this business")
        btype            = bc.get("type", "retail")
        currency         = bc.get("currency", "KES")
        custom_direction = request.custom_instructions or ""
        regenerate_count = request.regenerate_count or 0

        # ── Business context block ──
        bc_lines = []
        if bc.get("about"):
            bc_lines.append(f"About: {bc['about']}")
        if bc.get("products_services"):
            bc_lines.append(f"What we sell: {bc['products_services']}")
        if bc.get("business_location"):
            bc_lines.append(f"Location: {bc['business_location']}")
        if bc.get("business_hours"):
            bc_lines.append(f"Hours: {bc['business_hours']}")
        if bc.get("delivery_info"):
            bc_lines.append(f"Delivery: {bc['delivery_info']}")
        if bc.get("special_offers"):
            bc_lines.append(f"Current offers: {bc['special_offers']}")
        if bc.get("payment_methods"):
            pm_str = ", ".join(bc["payment_methods"][:3])
            bc_lines.append(f"Payment: {pm_str}")
        if bc.get("faqs"):
            bc_lines.append(f"FAQs: {bc['faqs']}")

        # ── Catalog block (structured, with variants & descriptions) ──
        catalog_lines = []
        if products:
            catalog_lines.append("Products/Menu:")
            for p in products[:20]:
                stock = "" if p.get("in_stock", True) else " [OUT OF STOCK]"
                cat   = f" [{p['category']}]" if p.get("category") else ""
                desc  = f" — {p['description'][:60]}" if p.get("description") else ""
                price = f"{currency} {p['price']:,.0f}"
                variants_str = ""
                if p.get("variants"):
                    variants_str = " (sizes: " + ", ".join(
                        f"{v['name']} {currency} {v['price']:,.0f}" for v in p["variants"]
                    ) + ")"
                catalog_lines.append(f"  • {p['name']}{cat}{stock} — {price}{variants_str}{desc}")
        if services:
            catalog_lines.append("Services:")
            for s in services[:15]:
                dur = f" ({s['duration']}min)" if s.get("duration") else ""
                catalog_lines.append(f"  • {s['name']}{dur} — {currency} {s['price']:,.0f}")

        has_catalog = bool(catalog_lines)

        # ── Raw messages for scenario detection ──
        raw_messages = await db.messages.find({
            "customer_id": request.customer_id,
            "user_id": business_id
        }).sort("created_at", 1).limit(20).to_list(20)
        history = [{"direction": m["direction"], "content": m["content"]} for m in raw_messages]

        # Human-readable conversation log from v2 context (last 10, oldest first)
        conv_lines = []
        for m in v2_messages:
            role = "Customer" if m["role"] == "customer" else "You"
            conv_lines.append(f"{role}: {m['content']}")

        last_message    = history[-1] if history else None
        last_contacted  = customer.get("last_contacted")
        days_since      = None
        if last_contacted:
            try:
                lc = last_contacted if isinstance(last_contacted, datetime) else datetime.fromisoformat(str(last_contacted).replace("Z", "+00:00"))
                days_since = (datetime.utcnow() - lc.replace(tzinfo=None)).days
            except Exception:
                pass

        is_first_contact        = not last_message and not last_contacted
        is_replying_to_incoming = bool(last_message and last_message["direction"] == "incoming")

        # ── Anti-repetition ──
        last_outgoing = next((m["content"] for m in reversed(history) if m["direction"] == "outgoing"), None)
        repetition_block = ""
        if last_outgoing:
            first_words = " ".join(last_outgoing.split()[:4])
            repetition_block = f'\nCRITICAL: Your last message started with "{first_words}" — use a completely different opener.'

        # ── Active conversation flow context ──
        flow_block = ""
        if mini_state.get("active_flow"):
            flow_block = f"\nNOTE: This customer is currently mid-flow ({mini_state['active_flow']}, step: {mini_state.get('flow_step', 'unknown')}) — keep that in mind."

        # ── Customer profile context ──
        customer_meta_parts = []
        if customer.get("tags"):
            customer_meta_parts.append(f"Tags: {', '.join(customer['tags'])}")
        if customer.get("notes"):
            customer_meta_parts.append(f"Notes: {customer['notes'][:100]}")
        if customer.get("total_spent"):
            customer_meta_parts.append(f"Total spent: {currency} {customer['total_spent']:,.0f}")
        customer_meta = "  |  ".join(customer_meta_parts) if customer_meta_parts else ""

        # ── Scenario-specific goal block ──
        catalog_hook = (
            "Reference a specific product/service name and price from the catalog below."
            if has_catalog else "Briefly introduce what you offer."
        )

        if is_first_contact:
            scenario_block = f"""SCENARIO: First-ever message to {customer_name}. They don't know you yet.
GOAL: Write a personal opener — not a sales pitch, not a template.
- {catalog_hook}
- ONE casual sentence introducing what you do — like telling a friend
- End with a light question that's easy to reply to
- BANNED openers: "Hi, I'm reaching out", "I wanted to introduce", "Hope this finds you well", "I'm excited to share" """

        elif is_replying_to_incoming:
            last_in = last_message["content"]
            scenario_block = f"""SCENARIO: {customer_name} just messaged you: "{last_in}"
GOAL: Reply directly and naturally to what they said.
- Answer their actual question — don't dance around it
- {f"Use real product names and prices from the catalog below." if has_catalog else ""}
- Skip the greeting if conversation is ongoing. Match their energy."""

        else:
            days_label = f"{days_since} days" if days_since else "a while"
            last_preview = last_message["content"][:120] if last_message else "(no prior message)"
            scenario_block = f"""SCENARIO: You haven't spoken to {customer_name} in {days_label}. Last said: "{last_preview}"
GOAL: Re-engage with one short, genuine message.
- {catalog_hook if has_catalog else "Give them a real reason to reply."}
- Sound like texting someone you know — not sending a follow-up email
- BANNED openers: "Just checking in", "I wanted to follow up", "Hope you're doing well", "It's been a while" """

        # ── Direction for regenerate ──
        direction_block = ""
        if custom_direction.strip():
            direction_block = f"\nDIRECTION: {custom_direction.strip()}\nApply while keeping the message natural and WhatsApp-appropriate."

        # ── Variety angles (rotate per regenerate attempt) ──
        variety_angles = [
            "Ask them something specific about a product or their need.",
            "Lead with a specific product name and price as the hook.",
            "Reference the last conversation topic, then connect it to something in the catalog.",
            "Ultra-short punchy opener — under 8 words, name a specific product or offer.",
            "Lead with a benefit — what does your best product DO for them? Name it.",
            "Be warm and personal — reference something from conversation history, then offer help.",
            "Be ultra-direct — one sentence with a specific product/price, straight to the point.",
        ]
        angle = variety_angles[regenerate_count % len(variety_angles)]
        variety_block = f"\nVARIETY (attempt #{regenerate_count + 1}): {angle}"

        # ── Assemble prompt ──
        business_block = (
            "\n\nBUSINESS INFO (use specific names/prices — never be generic):\n" + "\n".join(bc_lines)
        ) if bc_lines else f"\n\nBusiness: {business_name}"
        catalog_block = (
            "\n\nCATALOG (reference specific items when relevant):\n" + "\n".join(catalog_lines)
        ) if catalog_lines else ""
        history_block = (
            "\n\nConversation history:\n" + "\n".join(conv_lines)
        ) if conv_lines else "\n\n(No prior conversation)"
        customer_block = f"\nCustomer: {customer_name}" + (f"  |  {customer_meta}" if customer_meta else "")

        prompt = f"""You are the owner of {business_name} — a real person, not a bot.
Business type: {btype}{customer_block}

{scenario_block}{business_block}{catalog_block}{history_block}{flow_block}{repetition_block}{direction_block}{variety_block}

RULES (non-negotiable):
1. Output ONLY the message text — no labels, no quotes, no explanation.
2. 1-3 sentences max. Short is better. WhatsApp is not email.
3. USE REAL SPECIFICS: name actual products and prices from catalog above. Never say "we have great options".
4. BANNED PHRASES: "Sure thing", "Absolutely", "Certainly", "Of course", "I'd be happy to", "Feel free to", "Don't hesitate", "I hope this helps", "Thank you for your interest", "Kindly", "Please be advised", "I apologize for any inconvenience", "I'm reaching out", "I wanted to touch base".
5. LANGUAGE: Match the customer's language. Mix naturally if they mix.
6. EMOJIS: Only if it genuinely fits. Never: 😊😇🙏✨💯
7. HONESTY: Only use facts from business info above. Never invent prices or promises.

Message:"""

        from ai_service import get_drafter
        ai = get_drafter()
        drafted = await ai._call_llm(prompt, model_pref=model_pref)
        drafted = drafted.strip().strip('"').strip("'")

        if is_first_contact:
            reason = "First message — introduce your business"
        elif is_replying_to_incoming:
            reason = f"Replying to: {last_message['content'][:60]}..."
        else:
            days_label = f"{days_since} days" if days_since else "a while"
            reason = f"No contact in {days_label}"

        return DraftMessageResponse(
            message=drafted or f"Hi {customer_name}, anything I can help you with?",
            confidence=0.9,
            reason=reason
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logging.error(f"Error in draft_ai_message: {e}\n{traceback.format_exc()}")
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
    
    await db.customers.update_one(
        {"_id": request.customer_id},
        {"$set": {"last_contacted": datetime.utcnow(), "last_owner_reply": datetime.utcnow()}}
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
    currency = (user.get("currency") or user.get("settings", {}).get("currency") or "USD") if user else "USD"
    
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
    
    lines.append("\n_Sent by Zilo CRM_")
    
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
        "auto_reply_audience": settings.get('auto_reply_audience', 'everyone'),
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
    }

@api_router.put("/settings")
async def update_user_settings(settings: UserSettingsUpdate, user = Depends(get_current_user)):
    """Update user settings"""
    
    update_data = {}
    
    if settings.auto_reply_enabled is not None:
        update_data['settings.auto_reply_enabled'] = settings.auto_reply_enabled

    if settings.auto_reply_audience is not None:
        _aud = settings.auto_reply_audience
        if _aud not in ("everyone", "customers_only", "new_contacts_only"):
            raise HTTPException(status_code=400, detail="Invalid auto_reply_audience")
        update_data['settings.auto_reply_audience'] = _aud
    
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

    if product_update.sub_category is not None:
        update_data["sub_category"] = product_update.sub_category

    if product_update.variants is not None:
        update_data["variants"] = product_update.variants

    if product_update.modifier_groups is not None:
        update_data["modifier_groups"] = product_update.modifier_groups

    if product_update.unit is not None:
        update_data["unit"] = product_update.unit

    if product_update.moq is not None:
        update_data["moq"] = product_update.moq

    if product_update.pricing_tiers is not None:
        update_data["pricing_tiers"] = product_update.pricing_tiers

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
    user = Depends(get_current_user)
):
    """Send a single product with image to customer via WhatsApp"""
    
    business_id = user.get("business_id", user["_id"])
    product = await db.products.find_one({"_id": product_id, "user_id": business_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    customer = await db.customers.find_one({"_id": customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    currency = user.get("settings", {}).get("currency", "USD")
    stock_label = "✅ In Stock" if product.get("in_stock", True) else "❌ Out of Stock"
    desc = f"\n_{product.get('description', '')}_" if product.get("description") else ""
    price = product.get('price') or 0
    message_text = (
        f"*{product['name']}*\n"
        f"💰 {currency} {price:,.0f}\n"
        f"{stock_label}{desc}\n\n"
        f"👉 Reply *Yes* or *Order* to buy!"
    )
    
    # Collect all product images (deduplicated, preserving order)
    server_url = os.environ.get("SERVER_URL", "").rstrip("/")
    all_images = []
    seen = set()
    for img in list(product.get("images", [])):
        if img and img not in seen:
            seen.add(img)
            full = img if img.startswith("http") else (f"{server_url}{img}" if server_url else None)
            if full:
                all_images.append(full)
    # Fallback: if images array was empty, try image_url
    if not all_images:
        img = product.get("image_url")
        if img:
            full = img if img.startswith("http") else (f"{server_url}{img}" if server_url else None)
            if full:
                all_images.append(full)
    
    # Send via WhatsApp API
    from whatsapp_service import get_whatsapp_service
    whatsapp_service = get_whatsapp_service(db)
    
    # Send extra images first (no caption), then last image with product details
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
    
    # Send last image (or only image) with the product details caption
    result = await whatsapp_service.send_message(
        user_id=business_id,
        to_number=customer["phone_number"],
        message=message_text,
        customer_name=customer.get("name"),
        media_url=all_images[-1] if all_images else None,
        send_context="product_send",
    )
    
    # Store as pending catalog so "Yes"/"Order" auto-creates the order
    await db.pending_catalogs.update_one(
        {"customer_id": customer_id, "user_id": business_id},
        {"$set": {
            "products": [{"id": product["_id"], "name": product["name"], "price": product.get("price", 0), "index": 1}],
            "single_product": True,
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )
    
    return {
        "status": "success",
        "message_id": result.get("message_id"),
        "customer_name": result.get("customer_name")
    }

class AIDescriptionRequest(BaseModel):
    product_name: str
    category: Optional[str] = None
    business_type: Optional[str] = None
    current_description: Optional[str] = None
    mode: str = "generate"  # "generate" or "improve"

@api_router.post("/products/ai-description")
async def generate_ai_description(
    request: AIDescriptionRequest,
    user = Depends(get_current_user)
):
    """Generate or improve product description using AI based on business type"""
    from ai_service import get_drafter
    
    drafter = get_drafter()
    business_type = request.business_type or "retail"
    
    # Business-specific prompts
    prompts = {
        "creator": "As a content creator, write a compelling description for brands looking to sponsor content. Focus on: target audience, engagement rates, content style, deliverables, and brand benefits. Make it professional and appealing to marketing managers.",
        "restaurant": "As a restaurant, write an appetizing description for this menu item. Focus on: ingredients, preparation method, taste profile, presentation, and why customers will love it. Include allergen warnings if relevant.",
        "rental": "As a rental business, write a detailed description for this listing. Focus on: key features, amenities, location benefits, ideal use cases, rental terms, and what makes it special. Be informative and trustworthy.",
        "healthcare": "As a healthcare provider, write a professional description for this service. Focus on: procedure details, benefits, duration, what patients should expect, qualifications, and reassurance. Be clear and professional.",
        "fitness": "As a fitness business, write a motivating description for this class. Focus on: workout intensity, equipment needed, skill level, benefits, instructor expertise, and what participants will achieve. Be inspiring and informative.",
        "services": "As a service business, write a clear description for this service. Focus on: scope of work, process, timeline, qualifications, customer benefits, and what sets it apart. Be professional and trustworthy.",
        "salon": "As a salon, write an appealing description for this beauty service. Focus on: treatment details, benefits, duration, products used, expertise, and results clients can expect. Be luxurious and reassuring.",
        "retail": "As a retail business, write an engaging product description. Focus on: key features, benefits, quality, use cases, and why customers should choose this product. Be persuasive and informative."
    }
    
    prompt_template = prompts.get(business_type.lower(), prompts["retail"])
    
    if request.mode == "improve" and request.current_description:
        user_prompt = f"Product Name: {request.product_name}\nCategory: {request.category or 'General'}\nCurrent Description: {request.current_description}\n\n{prompt_template}\n\nImprove this description. Return ONLY the description text, no labels or quotes."
        system_prompt = "You are a professional copywriter. Improve the description to be more appealing. Keep it to 1-2 short sentences, max 30 words. Return ONLY the description text."
    else:
        user_prompt = f"Product Name: {request.product_name}\nCategory: {request.category or 'General'}\n\n{prompt_template}\n\nReturn ONLY the description text, no labels, no quotes, no extra explanation."
        system_prompt = "You are a professional copywriter. Write a short, punchy product description. Max 2 sentences, max 30 words. Focus on taste/benefit. Return ONLY the description text."
    
    try:
        # Build the prompt as a string for the AI service
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Use the existing AI service with standard model
        response = await drafter._call_llm(
            prompt=full_prompt,
            model_pref="standard"
        )
        
        description = response.strip()
        
        return {
            "status": "success",
            "description": description
        }
    except Exception as e:
        print(f"AI description generation error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate description: {str(e)}")

class BusinessAboutRequest(BaseModel):
    business_type: str
    current_description: Optional[str] = None
    mode: str = "generate"  # "generate" or "improve"

@api_router.post("/settings/ai-about")
async def generate_business_about(
    request: BusinessAboutRequest,
    user = Depends(get_current_user)
):
    """Generate or improve business About description using AI based on business type"""
    from ai_service import get_drafter
    
    drafter = get_drafter()
    business_type = request.business_type or "general"
    
    # Business-specific prompts for About section
    prompts = {
        "creator": "As a content creator, write a compelling 'About' section that introduces you to potential brand partners. Focus on: your unique style, niche expertise, audience demographics, content quality, past collaborations, and what makes you stand out. Make it professional yet authentic.",
        "restaurant": "As a restaurant, write an engaging 'About' section that tells your story. Focus on: cuisine type, signature dishes, chef background, atmosphere, what makes your restaurant special, years in business, and commitment to quality. Make it appetizing and inviting.",
        "rental": "As a rental business, write a trustworthy 'About' section. Focus on: types of properties/items you offer, service area, years of experience, customer satisfaction, maintenance standards, booking process, and what sets you apart. Be professional and reassuring.",
        "healthcare": "As a healthcare provider, write a professional 'About' section. Focus on: medical specialties, qualifications, years of practice, treatment philosophy, patient care approach, facility features, and commitment to health. Be clear, professional, and reassuring.",
        "fitness": "As a fitness business, write a motivating 'About' section. Focus on: training philosophy, instructor qualifications, class variety, equipment/facilities, success stories, community atmosphere, and fitness goals you help achieve. Be inspiring and energetic.",
        "services": "As a service business, write a professional 'About' section. Focus on: services offered, expertise, years in business, team qualifications, work quality, customer satisfaction, and what differentiates you. Be trustworthy and competent.",
        "salon": "As a salon/beauty business, write an appealing 'About' section. Focus on: services offered, stylist expertise, product brands used, salon atmosphere, years of experience, beauty philosophy, and client satisfaction. Be luxurious and welcoming.",
        "retail": "As a retail business, write an engaging 'About' section. Focus on: products you sell, quality standards, sourcing, customer service, years in business, unique offerings, and shopping experience. Be inviting and trustworthy.",
        "general": "Write a professional 'About' section for this business. Focus on: what the business does, expertise, years of experience, commitment to customers, unique value proposition, and what sets it apart. Be clear and professional."
    }
    
    prompt_template = prompts.get(business_type.lower(), prompts["general"])
    
    if request.mode == "improve" and request.current_description:
        user_prompt = f"Business Type: {business_type}\nCurrent About: {request.current_description}\n\n{prompt_template}\n\nPlease improve this About section to be more professional, engaging, and effective."
        system_prompt = "You are a professional business copywriter. Improve the given About section to be more compelling and clear. Keep the same core message but enhance the language and structure. Keep it under 150 words."
    else:
        user_prompt = f"Business Type: {business_type}\n\n{prompt_template}"
        system_prompt = "You are a professional business copywriter. Write compelling About sections that help businesses connect with their customers. Keep descriptions under 150 words and focus on building trust and interest."
    
    try:
        # Build the prompt as a string for the AI service
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Use the existing AI service with standard model
        response = await drafter._call_llm(
            prompt=full_prompt,
            model_pref="standard"
        )
        
        description = response.strip()
        
        return {
            "status": "success",
            "description": description
        }
    except Exception as e:
        print(f"AI business about generation error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate About description: {str(e)}")

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
    user = Depends(get_current_user)
):
    """Send multiple products as a catalog message to customer via WhatsApp"""
    
    business_id = user.get("business_id", user["_id"])
    customer = await db.customers.find_one({"_id": request.customer_id, "user_id": business_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    products = []
    for pid in request.product_ids[:10]:  # Max 10 products per catalog
        p = await db.products.find_one({"_id": pid, "user_id": business_id})
        if p:
            products.append(p)
    
    if not products:
        raise HTTPException(status_code=400, detail="No valid products found")
    
    currency = user.get("settings", {}).get("currency", "USD")
    
    from whatsapp_service import get_whatsapp_service
    whatsapp_service = get_whatsapp_service(db)
    
    # Send each product: extra images first, then last image with details
    server_url = os.environ.get("SERVER_URL", "").rstrip("/")
    result = None
    for i, p in enumerate(products):
        stock_label = "✅ In Stock" if p.get("in_stock", True) else "❌ Out of Stock"
        desc = f"\n_{p.get('description', '')}_" if p.get("description") else ""
        price = p.get('price') or 0
        message_text = (
            f"*{p['name']}*\n"
            f"💰 {currency} {price:,.0f}\n"
            f"{stock_label}{desc}\n\n"
            f"👉 Reply *{i+1}* to order!"
        )
        
        # Collect all product images (deduplicated, preserving order)
        all_images = []
        seen = set()
        for img in list(p.get("images", [])):
            if img and img not in seen:
                seen.add(img)
                full = img if img.startswith("http") else (f"{server_url}{img}" if server_url else None)
                if full:
                    all_images.append(full)
        if not all_images:
            img = p.get("image_url")
            if img:
                full = img if img.startswith("http") else (f"{server_url}{img}" if server_url else None)
                if full:
                    all_images.append(full)
        
        # Send extra images first (no caption)
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
        
        # Send last image with product details caption
        result = await whatsapp_service.send_message(
            user_id=business_id,
            to_number=customer["phone_number"],
            message=message_text,
            customer_name=customer.get("name"),
            media_url=all_images[-1] if all_images else None,
            send_context="product_send",
        )
    
    # Store product IDs in a pending catalog for this customer (for order matching)
    await db.pending_catalogs.update_one(
        {"customer_id": request.customer_id, "user_id": business_id},
        {"$set": {
            "products": [{"id": p["_id"], "name": p["name"], "price": p.get("price", 0), "index": i} for i, p in enumerate(products, 1)],
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )
    
    return {
        "status": "success",
        "products_sent": len(products),
        "message_id": result.get("message_id")
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

    currency = user.get("settings", {}).get("currency", "USD")
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
                    {"$set": {"products": product_index_list, "created_at": datetime.utcnow()}},
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


@api_router.head("/health")
async def health_check_head():
    """Render and some probes use HEAD; GET-only routes return 405."""
    return Response(status_code=200)


# Serve static files (product images)
app.mount("/uploads", StaticFiles(directory=str(ROOT_DIR / "uploads")), name="uploads")

# Serve static pages (privacy policy, account deletion, etc.)
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "static")), name="static")

# Startup event
@app.on_event("startup")
async def startup_tasks():
    """Run startup tasks"""

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

logger = logging.getLogger(__name__)

# ============ BOOKINGS ENDPOINTS ============

def _generate_booking_number() -> str:
    import random, string
    return "BK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _booking_query_by_id(business_id: str, booking_id: str) -> dict:
    """
    Match a booking document whether _id was stored as a string UUID (manual /api/bookings)
    or as a BSON ObjectId (WhatsApp / AI insert_one paths).
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    or_ids = [{"_id": booking_id}]
    try:
        or_ids.append({"_id": ObjectId(booking_id)})
    except (InvalidId, TypeError):
        pass
    return {"user_id": business_id, "$or": or_ids}


def _booking_to_response(doc: dict) -> dict:
    created = doc.get("created_at", datetime.utcnow())
    if isinstance(created, datetime):
        created_str = created.isoformat()
    else:
        created_str = str(created)

    # Rentals / AI inserts may only set checkin_date — surface a single calendar date for lists
    date_val = (doc.get("date") or "").strip()
    if not date_val and doc.get("checkin_date"):
        date_val = str(doc.get("checkin_date", "")).strip()

    has_checkin = bool(doc.get("checkin_date"))
    is_stay = bool(doc.get("checkin_date") and doc.get("checkout_date"))
    time_val = doc.get("time")
    if time_val is None or str(time_val).strip() == "":
        time_val = "—" if (is_stay or has_checkin) else "09:00"

    return {
        "id": str(doc.get("_id", "")),
        "booking_number": doc.get("booking_number", ""),
        "user_id": str(doc.get("user_id", "")),
        "customer_id": doc.get("customer_id"),
        "customer_name": doc.get("customer_name", ""),
        "customer_phone": doc.get("customer_phone"),
        "service_id": doc.get("service_id", ""),
        "service_name": doc.get("service_name", ""),
        "service_category": doc.get("service_category"),
        "staff_name": doc.get("staff_name"),
        "date": date_val,
        "time": time_val,
        "end_time": doc.get("end_time"),
        "duration": doc.get("duration"),
        "checkin_date": doc.get("checkin_date"),
        "checkout_date": doc.get("checkout_date"),
        "nights": doc.get("nights"),
        "capacity": doc.get("capacity"),
        "enrolled_count": doc.get("enrolled_count", 0),
        "addons": doc.get("addons", []),
        "total_price": doc.get("total_price"),
        "status": doc.get("status", "pending"),
        "payment_status": doc.get("payment_status", "unpaid"),
        "price": doc.get("price", 0),
        "notes": doc.get("notes"),
        "source": doc.get("source"),
        "last_reminder_at": doc.get("last_reminder_at"),
        "created_at": created_str,
    }

@api_router.post("/bookings", response_model=BookingResponse)
async def create_booking(booking: BookingCreate, user=Depends(get_current_user)):
    """Create a new booking/appointment"""
    business_id = user.get("business_id", user["_id"])

    # Resolve customer info
    customer_name = "Walk-in Customer"
    customer_phone = None
    if booking.customer_id and booking.customer_id != "walk-in":
        cust = await db.customers.find_one({"_id": booking.customer_id, "user_id": business_id})
        if cust:
            customer_name = cust.get("name", "Unknown")
            customer_phone = cust.get("phone_number")
    elif booking.customer_name:
        customer_name = booking.customer_name

    # Resolve service: catalog id, or custom name (same as mobile app)
    sid = (booking.service_id or "").strip()
    if sid.lower() == "manual":
        sid = ""
    svc = None
    if sid:
        svc = await db.products.find_one({"_id": sid, "user_id": business_id})
    service_name = ""
    service_category = None
    duration = None
    if svc:
        service_name = (svc.get("name") or "").strip()
        service_category = svc.get("offering_type") or svc.get("category")
        duration = svc.get("duration")
    elif booking.service_name and str(booking.service_name).strip():
        service_name = str(booking.service_name).strip()
    else:
        raise HTTPException(
            status_code=400,
            detail="Select a service from your catalog or enter a custom service name.",
        )

    has_stay = bool(booking.checkin_date and booking.checkout_date)
    if (booking.checkin_date or booking.checkout_date) and not has_stay:
        raise HTTPException(
            status_code=400,
            detail="Both check-in and check-out dates are required for a stay.",
        )

    if has_stay:
        date_val = ((booking.date or "").strip() or (booking.checkin_date or "").strip())
        time_val = (booking.time or "").strip() or "00:00"
    else:
        date_val = (booking.date or "").strip()
        if not date_val:
            raise HTTPException(status_code=400, detail="Date is required.")
        time_val = (booking.time or "").strip() or "09:00"

    price_val = float(booking.price or 0)
    if price_val == 0 and svc:
        price_val = float(svc.get("price") or 0)

    # Calculate end time from duration
    end_time = None
    if duration and time_val and time_val != "—":
        try:
            h, m = map(int, time_val.split(":"))
            total_m = h * 60 + m + int(duration)
            end_time = f"{total_m // 60:02d}:{total_m % 60:02d}"
        except Exception:
            pass

    # Calculate nights for rentals
    nights = None
    if booking.checkin_date and booking.checkout_date:
        try:
            from datetime import date as _date
            ci = _date.fromisoformat(booking.checkin_date)
            co = _date.fromisoformat(booking.checkout_date)
            nights = max((co - ci).days, 0)
        except Exception:
            pass

    booking_id = str(uuid.uuid4())
    now = datetime.utcnow()
    stored_service_id = sid or "manual"
    doc = {
        "_id": booking_id,
        "booking_number": _generate_booking_number(),
        "user_id": business_id,
        "customer_id": booking.customer_id if booking.customer_id and booking.customer_id != "walk-in" else None,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service_id": stored_service_id,
        "service_name": service_name,
        "service_category": service_category,
        "staff_name": booking.staff_name,
        "date": date_val,
        "time": time_val,
        "end_time": end_time,
        "duration": duration,
        "checkin_date": booking.checkin_date,
        "checkout_date": booking.checkout_date,
        "nights": nights,
        "capacity": booking.capacity,
        "enrolled_count": 1 if booking.customer_id and booking.customer_id != "walk-in" else 0,
        "addons": [a.dict() for a in booking.addons] if booking.addons else [],
        "total_price": price_val,
        "status": "pending",
        "payment_status": "unpaid",
        "price": price_val,
        "notes": booking.notes,
        "source": "manual",
        "created_at": now,
    }
    await db.bookings.insert_one(doc)
    return _booking_to_response(doc)

@api_router.get("/bookings", response_model=List[BookingResponse])
async def get_bookings(
    status: Optional[str] = None,
    limit: int = Query(200, le=500),
    user=Depends(get_current_user)
):
    """Get all bookings for the authenticated business"""
    business_id = user.get("business_id", user["_id"])
    query: dict = {"user_id": business_id}
    if status:
        query["status"] = status
    docs = await db.bookings.find(query).sort("created_at", -1).limit(limit).to_list(limit)
    return [_booking_to_response(d) for d in docs]

@api_router.put("/bookings/{booking_id}", response_model=BookingResponse)
async def update_booking(booking_id: str, update: BookingUpdate, user=Depends(get_current_user)):
    """Update booking status, payment status, or staff"""
    business_id = user.get("business_id", user["_id"])
    doc = await db.bookings.find_one(_booking_query_by_id(business_id, booking_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Booking not found")
    updates = {k: v for k, v in update.dict().items() if v is not None}
    if updates:
        q = _booking_query_by_id(business_id, booking_id)
        await db.bookings.update_one(q, {"$set": updates})
        doc.update(updates)
    return _booking_to_response(doc)

@api_router.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str, user=Depends(get_current_user)):
    """Delete a booking"""
    business_id = user.get("business_id", user["_id"])
    result = await db.bookings.delete_one(_booking_query_by_id(business_id, booking_id))
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"success": True}

@api_router.post("/bookings/{booking_id}/reminder")
async def send_booking_reminder(booking_id: str, user=Depends(get_current_user)):
    """Send WhatsApp reminder for a booking"""
    business_id = user.get("business_id", user["_id"])
    doc = await db.bookings.find_one(_booking_query_by_id(business_id, booking_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Booking not found")
    phone = doc.get("customer_phone")
    if not phone:
        raise HTTPException(status_code=400, detail="No phone number for customer")
    # Format reminder message
    date_str = doc.get("checkin_date") or doc.get("date", "")
    time_str = doc.get("time", "")
    checkout_str = doc.get("checkout_date", "")
    if checkout_str:
        when_str = f"Check-in: {date_str}, Check-out: {checkout_str}"
    elif time_str:
        when_str = f"{date_str} at {time_str}"
    else:
        when_str = date_str
    message = (
        f"Hi {doc.get('customer_name', 'there')}! "
        f"Reminder for your {doc.get('service_name', 'appointment')}: {when_str}. "
        f"Booking ref: {doc.get('booking_number', '')}. See you soon!"
    )
    try:
        whatsapp_service = get_whatsapp_service(db)
        await whatsapp_service.send_message(business_id, phone, message)
        now = datetime.utcnow().isoformat()
        await db.bookings.update_one(_booking_query_by_id(business_id, booking_id), {"$set": {"last_reminder_at": now}})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send reminder: {str(e)}")
    return {"success": True, "sent_at": datetime.utcnow().isoformat()}


# ── API: Connect a Facebook Page / Instagram account ──────────────────────────
# NOTE: these must be registered on api_router BEFORE app.include_router(api_router)

@api_router.post("/meta/connect")
async def connect_meta_page(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    page_id = data.get("page_id", "").strip()
    token   = data.get("page_access_token", "").strip()
    channel = data.get("channel", "messenger")
    ig_id   = data.get("instagram_id", "").strip()
    if not page_id or not token:
        raise HTTPException(status_code=400, detail="page_id and page_access_token required")
    user_id = user.get("business_id", user["_id"])
    now = datetime.utcnow()
    await db.meta_connections.update_one(
        {"user_id": user_id, "channel": channel},
        {"$set": {
            "user_id": user_id, "page_id": page_id,
            "instagram_id": ig_id or page_id,
            "page_access_token": token, "channel": channel, "updated_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    logging.info(f"[Meta] {channel} connected for user {user_id} page {page_id}")
    return {"status": "connected", "channel": channel, "page_id": page_id}


@api_router.get("/meta/connections")
async def get_meta_connections(user=Depends(get_current_user)):
    user_id = user.get("business_id", user["_id"])
    conns = await db.meta_connections.find({"user_id": user_id}).to_list(10)
    return [{"channel": c["channel"], "page_id": c.get("page_id", ""), "connected": True} for c in conns]


@api_router.delete("/meta/disconnect/{channel}")
async def disconnect_meta(channel: str, user=Depends(get_current_user)):
    user_id = user.get("business_id", user["_id"])
    await db.meta_connections.delete_one({"user_id": user_id, "channel": channel})
    return {"status": "disconnected", "channel": channel}


def _operator_provision_secret() -> str:
    """Single secret for operator-only provisioning (Bird, Telegram bot, etc.)."""
    return (os.environ.get("OPERATOR_PROVISION_SECRET") or os.environ.get("BIRD_PROVISION_SECRET") or "").strip()


def _require_operator_secret(request: Request) -> None:
    expected = _operator_provision_secret()
    got = (
        request.headers.get("X-Operator-Provision-Secret")
        or request.headers.get("X-Bird-Provision-Secret")
        or ""
    ).strip()
    if not expected or got != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-Operator-Provision-Secret",
        )


# ── Bird.com — operator-only: map Bird channel → CRM user (clients never configure Bird) ──


@api_router.post("/bird/provision-channel")
async def bird_provision_channel(request: Request):
    """Map a Bird channel UUID to a CRM user. Header: X-Operator-Provision-Secret (or legacy X-Bird-Provision-Secret)."""
    _require_operator_secret(request)
    data = await request.json()
    channel_id = (data.get("channel_id") or data.get("channelId") or "").strip()
    user_id_raw = data.get("user_id") or data.get("crm_user_id")
    workspace_id = (data.get("workspace_id") or data.get("workspaceId") or os.environ.get("BIRD_WORKSPACE_ID", "") or "").strip()
    if not channel_id or user_id_raw is None or user_id_raw == "":
        raise HTTPException(status_code=400, detail="channel_id and user_id required")
    from bird_service import normalize_crm_user_id

    user_id = normalize_crm_user_id(user_id_raw)
    now = datetime.utcnow()
    await db.bird_connections.update_one(
        {"channel_id": channel_id},
        {
            "$set": {
                "user_id": user_id,
                "channel_id": channel_id,
                "workspace_id": workspace_id,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    logging.info(f"[Bird] provisioned channel {channel_id} -> user {user_id}")
    return {"status": "ok", "channel_id": channel_id, "user_id": str(user_id)}


@api_router.delete("/bird/provision-channel/{channel_id}")
async def bird_unprovision_channel(channel_id: str, request: Request):
    """Remove channel mapping (same secret as POST)."""
    _require_operator_secret(request)
    await db.bird_connections.delete_one({"channel_id": channel_id})
    logging.info(f"[Bird] removed channel mapping {channel_id}")
    return {"status": "removed", "channel_id": channel_id}


import base64 as _b64
import json as _json2

_FACEBOOK_APP_ID     = os.environ.get("FACEBOOK_APP_ID") or os.environ.get("META_APP_ID", "")
_FACEBOOK_APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET") or os.environ.get("META_APP_SECRET", "")

def _meta_state_encode(user_id: str, channel: str) -> str:
    raw = _b64.urlsafe_b64encode(_json2.dumps({"uid": user_id, "ch": channel}).encode()).decode().rstrip("=")
    sig = hmac.new(JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{raw}.{sig}"

def _meta_state_decode(state: str):
    try:
        raw, sig = state.rsplit(".", 1)
        expected = hmac.new(JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
        if sig != expected:
            raise ValueError("bad sig")
        padded = raw + "=" * (-len(raw) % 4)
        data = _json2.loads(_b64.urlsafe_b64decode(padded))
        return data["uid"], data["ch"]
    except Exception:
        return None, None


@api_router.get("/meta/oauth/start")
async def meta_oauth_start(channel: str = "messenger", user=Depends(get_current_user)):
    """Return the Facebook OAuth URL so the frontend can redirect the user."""
    if not _FACEBOOK_APP_ID:
        raise HTTPException(status_code=500, detail="FACEBOOK_APP_ID not configured on server")
    user_id = str(user.get("business_id", user["_id"]))
    state = _meta_state_encode(user_id, channel)
    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "https://crm-1-pnfo.onrender.com").rstrip("/")
    redirect_uri = f"{backend_url}/api/meta/oauth/callback"
    # Basic permissions only — easy Meta review; Bird handles actual messaging
    scopes = "pages_show_list,pages_read_engagement,business_management"
    if channel == "instagram":
        scopes += ",instagram_basic"
    fb_url = (
        f"https://www.facebook.com/v18.0/dialog/oauth"
        f"?client_id={_FACEBOOK_APP_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scopes}"
        f"&state={state}"
        f"&response_type=code"
    )
    return {"url": fb_url, "redirect_uri": redirect_uri}


# ── Telegram — operator provisions bot; clients only see status (read-only GET) ───────────


@api_router.post("/telegram/provision-bot")
async def telegram_provision_bot(request: Request):
    """Attach a bot token to a CRM user. Same header as Bird: X-Operator-Provision-Secret."""
    _require_operator_secret(request)
    from telegram_service import get_bot_info, set_telegram_webhook
    from bird_service import normalize_crm_user_id

    data = await request.json()
    bot_token = data.get("bot_token", "").strip()
    user_id_raw = data.get("user_id") or data.get("crm_user_id")
    if not bot_token or user_id_raw is None or user_id_raw == "":
        raise HTTPException(status_code=400, detail="bot_token and user_id required")

    bot_info = await get_bot_info(bot_token)
    if not bot_info:
        raise HTTPException(status_code=400, detail="Invalid bot token")

    user_id = normalize_crm_user_id(user_id_raw)
    now = datetime.utcnow()
    bot_username = bot_info.get("username", "")

    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "https://crm-1-pnfo.onrender.com").rstrip("/")
    webhook_url = f"{backend_url}/webhook/telegram/{bot_token}"
    await set_telegram_webhook(bot_token, webhook_url)

    await db.telegram_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "bot_token": bot_token,
                "bot_username": bot_username,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    logging.info(f"[Telegram] provisioned @{bot_username} for user {user_id}")
    return {"status": "connected", "bot_username": bot_username, "user_id": str(user_id)}


@api_router.delete("/telegram/provision-bot/{user_id}")
async def telegram_unprovision_bot(user_id: str, request: Request):
    """Remove Telegram bot for a CRM user (operator only). user_id = Mongo ObjectId hex."""
    _require_operator_secret(request)
    from bird_service import normalize_crm_user_id
    from telegram_service import delete_telegram_webhook

    uid = normalize_crm_user_id(user_id)
    conn = await db.telegram_connections.find_one({"user_id": uid})
    if conn:
        await delete_telegram_webhook(conn["bot_token"])
        await db.telegram_connections.delete_one({"user_id": uid})
    logging.info(f"[Telegram] removed bot for user {uid}")
    return {"status": "disconnected", "user_id": user_id}


@api_router.get("/telegram/connection")
async def get_telegram_connection(user=Depends(get_current_user)):
    user_id = user.get("business_id", user["_id"])
    conn = await db.telegram_connections.find_one({"user_id": user_id})
    if not conn:
        return {"connected": False}
    return {"connected": True, "bot_username": conn.get("bot_username", "")}


app.include_router(api_router)


# ── Facebook OAuth callback (public — called by Facebook, no JWT) ─────────────

@app.get("/api/meta/oauth/callback")
async def meta_oauth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
):
    """Facebook redirects here after user grants/denies Messenger/Instagram access."""
    frontend_url = os.environ.get("FRONTEND_URL", "https://zilo.vercel.app").rstrip("/")
    back_url = f"{frontend_url}/dashboard/integrations"

    if error or not code:
        logging.warning(f"[Meta OAuth] Denied or error: {error} — {error_description}")
        return Response(status_code=302, headers={"Location": f"{back_url}?error=oauth_denied"})

    user_id, channel = _meta_state_decode(state)
    if not user_id:
        return Response(status_code=302, headers={"Location": f"{back_url}?error=invalid_state"})

    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "https://crm-1-pnfo.onrender.com").rstrip("/")
    redirect_uri = f"{backend_url}/api/meta/oauth/callback"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # 1. Exchange code → short-lived user access token
            tok_resp = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={
                    "client_id":     _FACEBOOK_APP_ID,
                    "client_secret": _FACEBOOK_APP_SECRET,
                    "redirect_uri":  redirect_uri,
                    "code":          code,
                },
            )
            tok_data = tok_resp.json()
            if "error" in tok_data:
                logging.error(f"[Meta OAuth] Token exchange failed: {tok_data}")
                return Response(status_code=302, headers={"Location": f"{back_url}?error=token_exchange"})
            short_token = tok_data["access_token"]

            # 2. Exchange → long-lived user token (60 days)
            ll_resp = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={
                    "grant_type":      "fb_exchange_token",
                    "client_id":       _FACEBOOK_APP_ID,
                    "client_secret":   _FACEBOOK_APP_SECRET,
                    "fb_exchange_token": short_token,
                },
            )
            ll_data = ll_resp.json()
            long_user_token = ll_data.get("access_token", short_token)

            # 3. Get pages the user administers
            pages_resp = await client.get(
                "https://graph.facebook.com/v18.0/me/accounts",
                params={
                    "access_token": long_user_token,
                    "fields": "id,name,access_token,instagram_business_account",
                },
            )
            pages_data = pages_resp.json()
            pages = pages_data.get("data", [])

        if not pages:
            logging.warning(f"[Meta OAuth] No pages found for user {user_id}")
            return Response(status_code=302, headers={"Location": f"{back_url}?error=no_pages"})

        # 4. Use first page — store all pages so client can switch later
        page      = pages[0]
        page_id   = page["id"]
        page_name = page.get("name", page_id)
        now       = datetime.utcnow()

        ig_id = page_id
        if channel == "instagram":
            ig_account = page.get("instagram_business_account") or {}
            ig_id = ig_account.get("id", page_id)

        # 5. Create Bird connector for this page
        from bird_service import BIRD_API_KEY, BIRD_API_BASE, BIRD_WORKSPACE_ID, _auth_headers
        ws = BIRD_WORKSPACE_ID
        bird_channel_id = None
        if BIRD_API_KEY and ws:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    if channel == "instagram":
                        connector_payload = {
                            "name": f"Instagram: {page_name}",
                            "connectorTemplateId": "fa65761f-9141-4d84-95f3-bd96f7e0e475",
                            "arguments": {
                                "instagramAccountId": ig_id,
                                "pageId": page_id,
                            },
                        }
                    else:
                        connector_payload = {
                            "name": f"Messenger: {page_name}",
                            "connectorTemplateId": "f3851b68-02f0-4574-8ccb-295caf3a14a9",
                            "arguments": {"pageId": page_id},
                        }
                    conn_resp = await client.post(
                        f"{BIRD_API_BASE}/workspaces/{ws}/connectors",
                        json=connector_payload,
                        headers=_auth_headers(),
                    )
                    if conn_resp.status_code in (200, 201):
                        conn_data = conn_resp.json()
                        bird_channel_id = (conn_data.get("channel") or {}).get("channelId")
                        logging.info(f"[Meta OAuth] Bird connector created for {channel} page {page_id} → channel {bird_channel_id}")
                    else:
                        logging.warning(f"[Meta OAuth] Bird connector creation failed {conn_resp.status_code}: {conn_resp.text[:300]}")
            except Exception as bird_exc:
                logging.error(f"[Meta OAuth] Bird connector error: {bird_exc}")

        # 6. Auto-provision Bird channel → CRM user
        if bird_channel_id:
            await db.bird_connections.update_one(
                {"channel_id": bird_channel_id},
                {"$set": {
                    "user_id": user_id,
                    "channel_id": bird_channel_id,
                    "workspace_id": ws,
                    "page_id": page_id,
                    "channel": channel,
                    "updated_at": now,
                }, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            logging.info(f"[Meta OAuth] Auto-provisioned Bird channel {bird_channel_id} → user {user_id}")

        # 7. Also save meta_connection for reference
        await db.meta_connections.update_one(
            {"user_id": user_id, "channel": channel},
            {"$set": {
                "user_id": user_id, "page_id": page_id,
                "instagram_id": ig_id,
                "channel": channel,
                "bird_channel_id": bird_channel_id,
                "page_name": page_name,
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

        logging.info(f"[Meta OAuth] {channel} connected via OAuth for user {user_id} page {page_id}")
        return Response(status_code=302, headers={"Location": f"{back_url}?connected={channel}"})

    except Exception as exc:
        logging.exception(f"[Meta OAuth] Unexpected error: {exc}")
        return Response(status_code=302, headers={"Location": f"{back_url}?error=server_error"})


# ============ TELEGRAM WEBHOOK ============

from telegram_service import (
    send_telegram_message,
    get_user_by_bot_token,
    get_or_create_telegram_customer,
    save_telegram_message,
)


@app.post("/webhook/telegram/{bot_token}")
async def telegram_webhook(bot_token: str, request: Request):
    """Receive messages from Telegram for the given bot token."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"status": "ignored"}

    text = (message.get("text") or "").strip()
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    message_id = message.get("message_id", 0)
    sender = message.get("from", {})
    sender_name = f"{sender.get('first_name', '')} {sender.get('last_name', '')}".strip() or f"User {chat_id}"

    if not text or not chat_id:
        return {"status": "ignored"}

    # Find CRM user who owns this bot
    user = await get_user_by_bot_token(db, bot_token)
    if not user:
        logging.warning(f"[Telegram] No CRM user found for bot token ending ...{bot_token[-6:]}")
        return {"status": "ignored"}

    user_id = user["_id"]
    token   = user["_tg_token"]

    customer = await get_or_create_telegram_customer(db, user_id, chat_id, sender_name)
    await save_telegram_message(db, user_id, customer["_id"], chat_id, text, "incoming", message_id)

    async def _process():
        from autoreply.engine import process_message as ar_process

        class _TelegramSender:
            async def send_message(self, user_id, to_number, message, customer_name="", send_context="auto_reply", **kwargs):
                ok = await send_telegram_message(token, chat_id, message)
                if ok:
                    await save_telegram_message(db, user_id, customer["_id"], chat_id, message, "outgoing")

        try:
            await ar_process(
                db=db,
                user=user,
                customer=customer,
                customer_id=customer["_id"],
                message=text,
                from_number=f"telegram_{chat_id}",
                whatsapp_service=_TelegramSender(),
            )
        except Exception as exc:
            logging.error(f"[Telegram] AutoReply error: {exc}", exc_info=True)
            await send_telegram_message(token, chat_id, "Sorry, I'm having trouble right now. Please try again! 🙏")

    asyncio.create_task(_process())
    return {"status": "ok"}


# ============ META WEBHOOKS (Messenger + Instagram) ============
# These live directly on the app (not under /api) so Meta can reach them.
# Webhook URLs:
#   Messenger : https://crm-1-pnfo.onrender.com/webhook/messenger
#   Instagram : https://crm-1-pnfo.onrender.com/webhook/instagram

from meta_service import (
    META_VERIFY_TOKEN,
    get_user_by_page_id,
    get_user_by_instagram_id,
    get_or_create_meta_customer,
    save_incoming_message,
    save_outgoing_message,
    send_messenger_message,
    send_instagram_message,
)


async def _process_meta_message(
    user: dict,
    customer: dict,
    text: str,
    sender_id: str,
    channel: str,
    token: str,
):
    """Run AutoReplyV2 for a Meta message and reply via the right channel."""
    from autoreply.engine import process_message as ar_process

    user_id = user["_id"]

    class _MetaSender:
        """Thin wrapper so AutoReplyV2 can call send_message() without knowing the channel."""
        async def send_message(self, user_id, to_number, message, customer_name="", send_context="auto_reply", **kwargs):
            if channel == "messenger":
                ok = await send_messenger_message(token, sender_id, message)
            else:
                ok = await send_instagram_message(token, sender_id, message)
            if ok:
                await save_outgoing_message(db, user_id, customer["_id"], message, channel)

    try:
        await ar_process(
            db=db,
            user=user,
            customer=customer,
            customer_id=customer["_id"],
            message=text,
            from_number=f"meta_{channel}_{sender_id}",
            whatsapp_service=_MetaSender(),
        )
    except Exception as exc:
        logging.error(f"[Meta] AutoReply error for {channel}/{sender_id}: {exc}", exc_info=True)
        # Send fallback
        fallback = "Sorry, I'm having trouble right now. Please try again! 🙏"
        if channel == "messenger":
            await send_messenger_message(token, sender_id, fallback)
        else:
            await send_instagram_message(token, sender_id, fallback)


@app.get("/webhook/messenger")
async def messenger_webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification handshake."""
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        logging.info("[Meta] Messenger webhook verified ✓")
        return Response(content=hub_challenge, media_type="text/plain")
    logging.warning(f"[Meta] Messenger verification failed — token mismatch")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/messenger")
async def messenger_webhook(request: Request):
    """Receive Messenger messages from Meta."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if body.get("object") != "page":
        return {"status": "ignored"}

    for entry in body.get("entry", []):
        page_id = entry.get("id", "")
        for event in entry.get("messaging", []):
            # Only handle incoming messages (not echoes/reads)
            if "message" not in event:
                continue
            msg = event["message"]
            if msg.get("is_echo"):
                continue
            sender_id = event.get("sender", {}).get("id", "")
            text = msg.get("text", "").strip()
            mid = msg.get("mid", "")
            if not sender_id or not text:
                continue

            # Find the CRM user who owns this page
            user = await get_user_by_page_id(db, page_id)
            if not user:
                logging.warning(f"[Meta] No CRM user found for page {page_id}")
                continue

            user_id = user["_id"]
            token   = user["_meta_token"]

            # Get/create customer
            customer = await get_or_create_meta_customer(db, user_id, sender_id, "messenger")
            await save_incoming_message(db, user_id, customer["_id"], sender_id, text, "messenger", mid)

            # Process async so webhook returns fast
            asyncio.create_task(_process_meta_message(user, customer, text, sender_id, "messenger", token))

    return {"status": "ok"}


@app.get("/webhook/instagram")
async def instagram_webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification handshake for Instagram."""
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        logging.info("[Meta] Instagram webhook verified ✓")
        return Response(content=hub_challenge, media_type="text/plain")
    logging.warning(f"[Meta] Instagram verification failed — token mismatch")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/instagram")
async def instagram_webhook(request: Request):
    """Receive Instagram DMs from Meta."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if body.get("object") != "instagram":
        return {"status": "ignored"}

    for entry in body.get("entry", []):
        instagram_id = entry.get("id", "")
        for event in entry.get("messaging", []):
            if "message" not in event:
                continue
            msg = event["message"]
            if msg.get("is_echo"):
                continue
            sender_id = event.get("sender", {}).get("id", "")
            text = msg.get("text", "").strip()
            mid = msg.get("mid", "")
            if not sender_id or not text:
                continue

            user = await get_user_by_instagram_id(db, instagram_id)
            if not user:
                logging.warning(f"[Meta] No CRM user found for instagram {instagram_id}")
                continue

            user_id = user["_id"]
            token   = user["_meta_token"]

            customer = await get_or_create_meta_customer(db, user_id, sender_id, "instagram")
            await save_incoming_message(db, user_id, customer["_id"], sender_id, text, "instagram", mid)

            asyncio.create_task(_process_meta_message(user, customer, text, sender_id, "instagram", token))

    return {"status": "ok"}


# ============ BIRD.COM (Conversations) =========================================
# Webhook URL (configure in Bird dashboard → Notifications → Webhook subscription):
#   POST https://<BACKEND_PUBLIC_URL>/webhook/bird
# Service: conversations — events: conversation.created, conversation.updated
# Optional: set signingKey in Bird and BIRD_WEBHOOK_SIGNING_KEY + BIRD_WEBHOOK_PUBLIC_URL here.

from bird_service import (
    BIRD_WEBHOOK_SIGNING_KEY as _BIRD_SIGNING_KEY,
    verify_webhook_signature,
    extract_text_from_last_message,
    find_user_participant_id,
    get_connection_for_inbound,
    get_user_for_bird,
    get_or_create_bird_customer,
    save_incoming_bird_message,
    save_outgoing_bird_message,
    send_channel_message,
    send_conversation_message,
    fetch_conversation,
    fetch_conversation_participants,
)


async def _process_bird_message(
    user: dict,
    customer: dict,
    text: str,
    workspace_id: str,
    conversation_id: str,
    user_participant_id: str,
):
    from autoreply.engine import process_message as ar_process

    user_id = user["_id"]
    bird_contact = customer.get("bird_contact") or {}
    identifier_key = bird_contact.get("identifierKey", "")
    identifier_value = bird_contact.get("identifierValue") or bird_contact.get("platformAddress", "")
    channel_id = customer.get("bird_channel_id", "")

    class _BirdSender:
        async def send_message(self, user_id, to_number, message, customer_name="", send_context="auto_reply", media_url=None, media_type="image", **kwargs):
            ok = False
            if channel_id and identifier_key and identifier_value:
                ok = await send_channel_message(workspace_id, channel_id, identifier_key, identifier_value, message, media_url=media_url, media_type=media_type)
            if not ok:
                ok = await send_conversation_message(workspace_id, conversation_id, user_participant_id, message)
            if ok:
                await save_outgoing_bird_message(db, user_id, customer["_id"], message)

    try:
        await ar_process(
            db=db,
            user=user,
            customer=customer,
            customer_id=customer["_id"],
            message=text,
            from_number=f"bird_{conversation_id}",
            whatsapp_service=_BirdSender(),
        )
    except Exception as exc:
        logging.error(f"[Bird] AutoReply error: {exc}", exc_info=True)
        await send_conversation_message(
            workspace_id,
            conversation_id,
            user_participant_id,
            "Sorry, I'm having trouble right now. Please try again! 🙏",
        )


@app.post("/webhook/bird")
async def bird_webhook(request: Request):
    raw = await request.body()
    verify_url = (os.environ.get("BIRD_WEBHOOK_PUBLIC_URL") or str(request.url)).strip()
    sig = request.headers.get("messagebird-signature") or request.headers.get("Messagebird-Signature")
    ts = request.headers.get("messagebird-request-timestamp") or request.headers.get("Messagebird-Request-Timestamp")
    if _BIRD_SIGNING_KEY and not verify_webhook_signature(raw, sig, ts, verify_url):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        await db.bird_connections.create_index(
            "channel_id",
            unique=True,
            partialFilterExpression={"channel_id": {"$type": "string", "$ne": ""}},
        )
    except Exception:
        pass

    if body.get("service") != "conversations":
        return {"status": "ignored"}
    if body.get("event") not in ("conversation.created", "conversation.updated"):
        return {"status": "ignored"}

    payload = body.get("payload") or {}
    last = payload.get("lastMessage")
    if not last:
        return {"status": "ok"}
    sender = last.get("sender") or {}
    if sender.get("type") != "contact":
        return {"status": "ok"}

    text = extract_text_from_last_message(last)
    if not text:
        return {"status": "ok"}

    mid = (last.get("id") or "").strip()
    channel_id = (payload.get("channelId") or "").strip()
    workspace_id = (
        (body.get("workspaceId") or body.get("workspace_id") or "").strip()
        or (payload.get("workspaceId") or "").strip()
        or os.environ.get("BIRD_WORKSPACE_ID", "").strip()
    )
    if not workspace_id:
        logging.warning("[Bird] webhook missing workspaceId; set BIRD_WORKSPACE_ID on the server")
        return {"status": "ok"}

    conn = await get_connection_for_inbound(db, workspace_id, channel_id)
    if not conn:
        logging.warning(
            f"[Bird] No CRM mapping for channel_id={channel_id or '(none)'} workspace={workspace_id}; "
            "provision with POST /api/bird/provision-channel"
        )
        return {"status": "ok"}

    user = await get_user_for_bird(db, conn)
    if not user:
        logging.warning("[Bird] Linked user record not found")
        return {"status": "ok"}

    conversation_id = payload.get("id")
    user_pid = find_user_participant_id(payload)
    if (not user_pid) and conversation_id:
        full = await fetch_conversation(workspace_id, conversation_id)
        if full:
            user_pid = find_user_participant_id(full)

    if not conversation_id:
        logging.warning("[Bird] Missing conversation id")
        return {"status": "ok"}

    customer = await get_or_create_bird_customer(db, user["_id"], sender, channel_id)
    await save_incoming_bird_message(db, user["_id"], customer["_id"], text, mid, channel_id)

    if not user_pid:
        user_pid = await fetch_conversation_participants(workspace_id, conversation_id)
        if not user_pid:
            logging.warning("[Bird] No sender participant found even from participants endpoint — auto-reply skipped")
            return {"status": "ok"}

    asyncio.create_task(
        _process_bird_message(user, customer, text, workspace_id, conversation_id, user_pid)
    )
    return {"status": "ok"}


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

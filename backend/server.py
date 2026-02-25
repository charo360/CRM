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

# Configure logging to file (outside watched directory) and stdout
# Using parent directory to avoid uvicorn reload loops
log_file = ROOT_DIR.parent / "server.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(log_file)),
        logging.StreamHandler(sys.stdout)
    ]
)
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
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
from wow_enhancements import get_wow_generator
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

# Anti-duplicate auto-reply guard: tracks evo_message_id to prevent double replies
# Evolution API often fires messages.upsert webhook multiple times for the same message
import asyncio as _aio
_auto_reply_dedup = {}  # key: evo_message_id -> timestamp
_auto_reply_lock = _aio.Lock()
_AUTO_REPLY_DEDUP_TTL = 120  # seconds

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
    # Start automation scheduler in background
    import asyncio
    asyncio.create_task(run_automation_scheduler())

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
    
    # Update broadcast status
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

class DraftMessageResponse(BaseModel):
    message: str
    confidence: float
    reason: str

class SendAutoMessageRequest(BaseModel):
    customer_id: str
    message: str

# User Settings Models
class UserSettingsUpdate(BaseModel):
    auto_reply_enabled: Optional[bool] = None
    notification_enabled: Optional[bool] = None
    notification_time: Optional[str] = None
    payment_methods: Optional[List[str]] = None
    currency: Optional[str] = None
    country_code: Optional[str] = None  # ISO 3166-1 alpha-2 e.g. 'US', 'KE', 'NG'
    daily_alert_count: Optional[int] = None
    message_tone: Optional[str] = None
    push_token: Optional[str] = None
    daily_pulse_enabled: Optional[bool] = None
    daily_pulse_time: Optional[str] = None  # e.g. '20:00'
    ai_model: Optional[str] = None  # standard, premium, claude-3.5, grok, etc.

# Business Knowledge Model
class BusinessKnowledge(BaseModel):
    products_services: Optional[str] = None  # What you sell/offer
    pricing_info: Optional[str] = None  # Price ranges, payment methods
    business_hours: Optional[str] = None  # When you're available
    delivery_info: Optional[str] = None  # Delivery areas, costs, timing
    faqs: Optional[str] = None  # Common questions and answers
    special_offers: Optional[str] = None  # Current promotions
    business_description: Optional[str] = None  # What makes you unique

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

# Temporary session store for WhatsApp pairing (in production, use Redis)
wa_auth_sessions = {}

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
            "payment_methods": country_config["methods"],
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

    # Create a session token to track this auth attempt
    import secrets
    session_token = secrets.token_urlsafe(32)
    wa_auth_sessions[session_token] = {
        "user_id": user_id,
        "phone": phone,
        "is_new_user": is_new_user,
        "created_at": datetime.utcnow(),
        "expires": datetime.utcnow() + timedelta(minutes=5),
    }

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
    session = wa_auth_sessions.get(request.session_token)
    if not session:
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    if datetime.utcnow() > session["expires"]:
        wa_auth_sessions.pop(request.session_token, None)
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
    wa_auth_sessions.pop(request.session_token, None)

    user = await db.users.find_one({"_id": user_id})
    is_new_user = session["is_new_user"] or not user.get("setup_complete", True)

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
    session = wa_auth_sessions.get(request.session_token)
    if not session:
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    if datetime.utcnow() > session["expires"]:
        wa_auth_sessions.pop(request.session_token, None)
        raise HTTPException(status_code=400, detail="Session expired. Please start again.")

    user_id = session["user_id"]
    phone = session["phone"]

    # Request new pairing code
    whatsapp_service = get_whatsapp_service(db)
    result = await whatsapp_service.create_instance(user_id, phone)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to refresh pairing code"))

    # Extend session expiry
    session["expires"] = datetime.utcnow() + timedelta(minutes=5)

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
    """Get current user settings"""
    s = user.get("settings", {})
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
    }

@api_router.put("/settings")
async def update_settings(request: Request, user = Depends(get_current_user)):
    """Update user settings"""
    body = await request.json()
    # Top-level fields (currency, country_code) live directly on the user doc
    top_level_fields = {}
    settings_fields = {}
    for k, v in body.items():
        if k in ("currency", "country_code"):
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
                "tags": tags,
                "classified_at": datetime.utcnow(),
            }}
        )
    else:
        # Reject — just clear the pending flag
        await db.customers.update_one(
            {"_id": customer_id},
            {"$set": {"classification_pending": False}}
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
        "created_at": datetime.utcnow()
    }
    
    await db.customers.insert_one(customer_doc)
    
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
    query = {"user_id": business_id}
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
        "$or": [
            {"last_contacted": {"$lt": cutoff_date}},
            {"last_contacted": None}
        ]
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
    
    # If we have smart insights, use them as the primary source for "Needs Attention"
    if smart_insights:
        for analysis in smart_insights:
            c = await db.customers.find_one({"_id": analysis["customer_id"]})
            if not c: continue
            
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
    else:
        # Fallback to legacy "Cold" logic if AI hasn't run yet
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        customers = await db.customers.find({
            "user_id": business_id,
            "$or": [
                {"last_contacted": {"$lt": cutoff_date}},
                {"last_contacted": None}
            ]
        }).sort("last_contacted", 1).to_list(100)
        
        for c in customers:
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
        auto_reply=customer.get("auto_reply", True),
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
        auto_reply=updated.get("auto_reply", True),
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

@api_router.get("/followups/analytics")
async def get_followup_analytics(days: int = 30, user = Depends(get_current_user)):
    """
    Get follow-up success metrics for analytics dashboard
    Automatically tracks: conversions, responses, timing
    """
    analytics = get_analytics(db)
    stats = await analytics.get_followup_stats(user["_id"], days)
    best_times = await analytics.get_best_followup_times(user["_id"])
    
    return {
        "stats": stats,
        "best_times": best_times
    }

@api_router.get("/stats/followup-suggestions")
async def get_followup_suggestions(user = Depends(get_current_user)):
    """Get follow-up suggestion counts for the follow-ups tab header stats"""
    business_id = user.get("business_id", user["_id"])
    now = datetime.utcnow()
    cutoff_week = now - timedelta(days=7)
    cutoff_month = now - timedelta(days=30)

    # Customers not contacted in 7+ days
    neglected_week = await db.customers.count_documents({
        "user_id": business_id,
        "$or": [{"last_contacted": {"$lt": cutoff_week}}, {"last_contacted": None}]
    })
    # Customers not contacted in 30+ days
    neglected_month = await db.customers.count_documents({
        "user_id": business_id,
        "$or": [{"last_contacted": {"$lt": cutoff_month}}, {"last_contacted": None}]
    })
    # New customers (created in last 7 days) with no follow-up
    new_cutoff = now - timedelta(days=7)
    new_customers = await db.customers.find({
        "user_id": business_id,
        "created_at": {"$gte": new_cutoff}
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
        "$or": [{"last_contacted": {"$lt": cutoff_week}}, {"last_contacted": None}]
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
        total_customers = await db.customers.count_documents({"user_id": business_id})
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        new_customers = await db.customers.count_documents({"user_id": business_id, "created_at": {"$gte": month_start}})
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
        
        result.append(OrderResponse(
            id=order["_id"],
            customer_id=order["customer_id"],
            customer_name=customer_name,
            customer_phone=customer_phone,
            product=order["product"],
            quantity=order["quantity"],
            price=order["price"],
            total_amount=order["total_amount"],
            payment_status=order["payment_status"],
            delivery_status=order["delivery_status"],
            notes=order.get("notes"),
            due_date=order.get("due_date"),
            created_at=order["created_at"].isoformat()
        ))
    
    return result

@api_router.put("/orders/{order_id}", response_model=OrderResponse)
async def update_order(order_id: str, payment_status: Optional[str] = None, delivery_status: Optional[str] = None, notes: Optional[str] = None, user = Depends(get_current_user)):
    """Update order payment status, delivery status, or notes"""
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
    
    return OrderResponse(
        id=order["_id"],
        customer_id=order["customer_id"],
        customer_name=customer_name,
        customer_phone=customer_phone,
        product=order["product"],
        quantity=order["quantity"],
        price=order["price"],
        total_amount=order["total_amount"],
        payment_status=order["payment_status"],
        delivery_status=order["delivery_status"],
        notes=order.get("notes"),
        due_date=order.get("due_date"),
        created_at=order["created_at"].isoformat()
    )

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
            created_at=p.get("created_at", datetime.utcnow())
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

MAX_PRODUCTS = 20

@api_router.post("/products", response_model=ProductResponse)
async def create_product(product: ProductCreate, user = Depends(get_current_user)):
    """Create a new product"""
    business_id = user.get("business_id", user["_id"])
    # Check product limit
    count = await db.products.count_documents({"user_id": business_id})
    if count >= MAX_PRODUCTS:
        raise HTTPException(status_code=400, detail=f"Product limit reached. Maximum {MAX_PRODUCTS} products allowed.")
    
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
        image_url=orig,
        images=imgs,
        description=result.get("description"),
        in_stock=result.get("in_stock", True),
        stock_quantity=result.get("stock_quantity"),
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
        "features": ["Up to 100 customers", "Basic follow-ups", "Receipt sending"]
    },
    "standard": {
        "name": "Standard",
        "interval": "monthly",
        "features": ["Up to 500 customers", "Unlimited follow-ups", "Broadcast messages", "Priority support"]
    },
    "pro": {
        "name": "Pro",
        "interval": "monthly",
        "features": ["Unlimited customers", "Advanced analytics", "Custom templates", "WhatsApp Business API", "Dedicated support"]
    }
}

# Regional pricing: currency -> (starter, standard, pro)
REGIONAL_PRICING = {
    # East Africa
    "KES": (700, 1000, 1500),       # Kenya
    "TZS": (15000, 22000, 33000),   # Tanzania
    "UGX": (25000, 37000, 55000),   # Uganda
    "RWF": (7000, 10000, 15000),    # Rwanda
    "ETB": (400, 600, 900),         # Ethiopia
    "BIF": (20000, 30000, 45000),   # Burundi
    "SOS": (4000, 6000, 9000),      # Somalia
    # West Africa
    "NGN": (5000, 7500, 11000),     # Nigeria
    "GHS": (50, 75, 110),           # Ghana
    "XOF": (4000, 6000, 9000),      # CFA (Senegal, Ivory Coast, etc.)
    "XAF": (4000, 6000, 9000),      # CFA (Cameroon, etc.)
    # Southern Africa
    "ZAR": (100, 150, 220),         # South Africa
    "CDF": (18000, 27000, 40000),   # DR Congo
    # North Africa / Middle East
    "EGP": (200, 300, 450),         # Egypt
    "MAD": (60, 90, 135),           # Morocco
    "TND": (20, 30, 45),            # Tunisia
    "AED": (25, 37, 55),            # UAE
    "SAR": (25, 37, 55),            # Saudi Arabia
    # South Asia
    "INR": (500, 750, 1100),        # India
    "PKR": (2000, 3000, 4500),      # Pakistan
    "BDT": (700, 1000, 1500),       # Bangladesh
    # Southeast Asia
    "PHP": (400, 600, 900),         # Philippines
    "IDR": (100000, 150000, 220000),# Indonesia
    "MYR": (30, 45, 65),            # Malaysia
    "THB": (250, 375, 550),         # Thailand
    "VND": (170000, 250000, 370000),# Vietnam
    # East Asia
    "CNY": (45, 65, 100),           # China
    "JPY": (1000, 1500, 2200),      # Japan
    "KRW": (9000, 13000, 20000),    # South Korea
    # Americas
    "USD": (7, 10, 15),             # USA/Canada
    "BRL": (35, 50, 75),            # Brazil
    "MXN": (120, 180, 270),         # Mexico
    "COP": (28000, 42000, 63000),   # Colombia
    "CLP": (5500, 8000, 12000),     # Chile
    "ARS": (5000, 7500, 11000),     # Argentina
    # Europe
    "GBP": (5, 8, 12),             # UK
    "EUR": (6, 9, 14),             # Eurozone
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
    user_settings = user.get('settings', {})
    currency = user_settings.get('currency', 'USD')
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
        "subscription_date": user.get("subscription_date")
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

@api_router.post("/customers/refresh-profile-pictures")
async def refresh_profile_pictures(user = Depends(get_current_user)):
    """Fetch profile pictures for customers that are missing them"""
    whatsapp_service = get_whatsapp_service(db)
    
    # Run bulk fetch in background (only fetches for customers missing pictures)
    async def _refresh(uid):
        try:
            result = await whatsapp_service.fetch_profile_pictures_bulk(uid)
            logging.info(f"Profile pictures refreshed: {result}")
        except Exception as e:
            logging.error(f"Profile picture refresh error: {e}")
    asyncio.create_task(_refresh(user["_id"]))
    
    return {"status": "started", "message": "Profile pictures are being refreshed in the background."}

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

    # Total unread messages
    unread_count = await db.messages.count_documents({
        "user_id": uid, "direction": "incoming", "read": {"$ne": True}
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

    # Total customers
    total_customers = await db.customers.count_documents({"user_id": uid})

    return {
        "unread_messages": unread_count,
        "followups_today": followups_today,
        "sales_today": sales_today,
        "sales_count_today": sales_count,
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
                                # Run AI classification on all synced contacts
                                try:
                                    classifier = get_classifier(db)
                                    customers = await db.customers.find({"user_id": uid, "synced_from_whatsapp": True}).to_list(None)
                                    for c in customers:
                                        msg_count = await db.messages.count_documents({"customer_id": c["_id"], "user_id": uid})
                                        if msg_count >= 2:
                                            await classifier.classify_contact(uid, c["_id"])
                                    logging.info(f"AI classification done for {len(customers)} synced contacts")
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
            print(f"DEBUG: Webhook received. Direction={direction}, Body='{body}'")
            logging.info(f"messages.upsert: direction={direction}, from={from_number}, evo_id={evo_msg_id_log}, body={body[:60]}")
            
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
                await db.customers.update_one(
                    {"_id": customer["_id"]},
                    {"$set": {
                        "last_message": body[:200] if body else None,
                        "last_contacted": datetime.utcnow(),
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
                await db.messages.insert_one(msg_doc)
                
                # For outgoing messages (typed in WhatsApp), just store — no auto-reply needed
                if from_me:
                    print(f"DEBUG: Ignoring outgoing message from me")
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
                
                # ============================================================
                # AGENT-BASED PRODUCT MATCHING & HANDLING (REPLACES OLD MONOLITH)
                # ============================================================
                
                # Placeholder for last_context, if needed by agents
                last_context = {} # You might fetch this from customer.get("agent_context", {})
                
                # Check if this is a personal contact
                is_personal = customer.get("is_personal", False) if customer else False
                
                # 2. Fetch recent message history (last 5) for context
                history = []
                if customer_id:
                    recent_msgs = await db.messages.find({
                        "user_id": user["_id"],
                        "customer_id": customer_id
                    }).sort("created_at", -1).limit(5).to_list(5)
                    
                    # Store as [{"direction": "incoming/outgoing", "content": "..."}]
                    # Reverse because we fetched -1 but usually need chronological for LLM
                    history = [{"direction": m["direction"], "content": m["content"]} for m in reversed(recent_msgs)]

                currency = user.get('settings', {}).get('currency', 'USD')
                agent_context = {
                    "currency": currency,
                    "previous_context": last_context,
                    "customer_id": customer_id,
                    "is_personal": is_personal,
                    "history": history
                }
                
                agent_result = await router.route_and_process(
                    user_id=user["_id"],
                    message=body,
                    context=agent_context
                )
                
                if agent_result and agent_result.get("handled"):
                    ws = get_whatsapp_service(db)
                    
                    # 1. Send messages returned by agent
                    for msg in agent_result.get("messages", []):
                        await ws.send_message(
                            user_id=user["_id"],
                            to_number=from_number,
                            message=msg.get("text", ""),
                            customer_name=customer_name,
                            media_url=msg.get("media_url"),
                            send_context="auto_reply"
                        )
                    
                    # 2. Update Context
                    updates = agent_result.get("context_update", {})
                    if updates:
                        db_updates = {}
                        if "last_discussed_product_id" in updates:
                            db_updates["last_discussed_product_id"] = updates["last_discussed_product_id"]
                        
                        if db_updates:
                            await db.customers.update_one(
                                {"_id": customer_id},
                                {"$set": db_updates}
                            )
                        
                    return {"status": "ok", "handled_by": "agent"}

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
                
                # Auto-reply logic (Per-Customer overrides Global)
                user_settings = user.get('settings', {})
                print(f"DEBUG: User settings: {user_settings}", flush=True)
                
                # Ensure we have the customer data
                if not customer and customer_id:
                    customer = await db.customers.find_one({"_id": customer_id})
                
                customer_auto_reply = customer.get('auto_reply') if customer else None
                global_auto_reply = user_settings.get('auto_reply_enabled', False)
                
                should_auto_reply = customer_auto_reply if customer_auto_reply is not None else global_auto_reply
                
                print(f"DEBUG: Auto-reply check. Customer={customer_auto_reply}, Global={global_auto_reply} -> RESULT={should_auto_reply}", flush=True)
                logging.info(f"Auto-reply check: Customer={customer_auto_reply}, Global={global_auto_reply}, Result={should_auto_reply}")
                
                if should_auto_reply:
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
    customers_count = await db.customers.count_documents({"user_id": user["_id"]})
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
            "created_at": m.get("created_at", m.get("timestamp"))
        }
        for m in messages
    ])

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
    
    return {
        "products_services": knowledge.get('products_services', ''),
        "pricing_info": knowledge.get('pricing_info', ''),
        "business_hours": knowledge.get('business_hours', ''),
        "delivery_info": knowledge.get('delivery_info', ''),
        "faqs": knowledge.get('faqs', ''),
        "special_offers": knowledge.get('special_offers', ''),
        "business_description": knowledge.get('business_description', ''),
    }

@api_router.put("/business-knowledge")
async def update_business_knowledge(knowledge: BusinessKnowledge, user = Depends(get_current_user)):
    """Update business knowledge for AI to use in conversations"""
    
    update_data = {}
    
    if knowledge.products_services is not None:
        update_data['business_knowledge.products_services'] = knowledge.products_services
    
    if knowledge.pricing_info is not None:
        update_data['business_knowledge.pricing_info'] = knowledge.pricing_info
    
    if knowledge.business_hours is not None:
        update_data['business_knowledge.business_hours'] = knowledge.business_hours
    
    if knowledge.delivery_info is not None:
        update_data['business_knowledge.delivery_info'] = knowledge.delivery_info
    
    if knowledge.faqs is not None:
        update_data['business_knowledge.faqs'] = knowledge.faqs
    
    if knowledge.special_offers is not None:
        update_data['business_knowledge.special_offers'] = knowledge.special_offers
    
    if knowledge.business_description is not None:
        update_data['business_knowledge.business_description'] = knowledge.business_description
    
    if update_data:
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": update_data}
        )
    
    return {"status": "success", "message": "Business knowledge updated"}

@api_router.post("/ai/draft-message")
async def draft_ai_message(request: DraftMessageRequest, user = Depends(get_current_user)):
    """Generate AI-drafted follow-up message for a customer"""
    logging.info(f"DEBUG: draft_ai_message called for customer_id={request.customer_id}")
    try:
        business_id = user.get("business_id", user["_id"])
        # Get customer
        customer = await db.customers.find_one({"_id": request.customer_id, "user_id": business_id})
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Get message history
        messages = await db.messages.find({
            "customer_id": request.customer_id,
            "user_id": business_id
        }).sort("created_at", 1).limit(10).to_list(10)
        
        # Get business name
        business_name = user.get('business_name', 'Your Business')
        
        # Get user's preferred tone or use request tone
        user_settings = user.get('settings', {})
        tone = user_settings.get('message_tone', request.tone)
        
        # Build business knowledge context
        business_knowledge_data = user.get('business_knowledge', {})
        business_knowledge = None
        
        if business_knowledge_data:
            # Format business knowledge for AI
            knowledge_parts = []
            
            if business_knowledge_data.get('business_description'):
                knowledge_parts.append(f"About us: {business_knowledge_data['business_description']}")
            
            if business_knowledge_data.get('products_services'):
                knowledge_parts.append(f"Products/Services: {business_knowledge_data['products_services']}")
            
            if business_knowledge_data.get('pricing_info'):
                knowledge_parts.append(f"Pricing: {business_knowledge_data['pricing_info']}")
            
            if business_knowledge_data.get('business_hours'):
                knowledge_parts.append(f"Hours: {business_knowledge_data['business_hours']}")
            
            if business_knowledge_data.get('delivery_info'):
                knowledge_parts.append(f"Delivery: {business_knowledge_data['delivery_info']}")
            
            if business_knowledge_data.get('special_offers'):
                knowledge_parts.append(f"Current Offers: {business_knowledge_data['special_offers']}")
            
            if business_knowledge_data.get('faqs'):
                knowledge_parts.append(f"FAQs: {business_knowledge_data['faqs']}")
            
            if knowledge_parts:
                business_knowledge = "\n".join(knowledge_parts)
        
        # Inject product catalog
        user_products = await db.products.find({"user_id": business_id}).to_list(50)
        if user_products:
            currency = user_settings.get("currency", "USD")
            catalog_lines = ["\nPRODUCT CATALOG (real products with actual prices):"]
            for p in user_products:
                stock = "IN STOCK" if p.get("in_stock", True) else "OUT OF STOCK"
                desc = f' - {p["description"]}' if p.get("description") else ""
                price_str = f"{currency} {p['price']:,.0f}" if p.get('price') is not None else "Price not set"
                
                # Get product image
                product_id = str(p['_id'])
                image_url = p.get("image_url") or (p.get("images", [])[0] if p.get("images") else None)
                image_marker = " [HAS IMAGE]" if image_url else ""
                
                catalog_lines.append(f"  • {p['name']} (ID: {product_id}): {price_str} [{stock}] ({p.get('category', 'Other')}){desc}{image_marker}")
            
            catalog_lines.append("\nWhen customers ask about products, use this catalog for accurate answers. Do NOT make up prices.")
            catalog_lines.append("When customers ask to see products, suggest them by name. The user will manually select and send product images from their catalog.")
            business_knowledge = (business_knowledge or "") + "\n".join(catalog_lines)
        
        # Get user country for language awareness
        user_country_code = user_settings.get("country_code", "")
        
        # Prepare history for agent context
        history = [{"direction": m["direction"], "content": m["content"]} for m in messages]
        
        # Determine current message (trigger) for routing
        # If last message is incoming, we are replying to it. 
        # Otherwise, we are just drafting a general follow-up.
        trigger_message = ""
        if history:
            last_msg = history[-1]
            if last_msg["direction"] == "incoming":
                trigger_message = last_msg["content"]
            else:
                trigger_message = "draft follow-up" # Generic intent

        # Check if is personal
        is_personal = customer.get("is_personal", False)
        
        # Build agent context
        currency = user_settings.get('currency', 'USD')
        agent_context = {
            "currency": currency,
            "customer_id": request.customer_id,
            "customer_name": customer['name'],
            "is_personal": is_personal,
            "history": history,
            "business_name": business_name,
            "tone": tone,
            "business_knowledge": business_knowledge,
            "custom_instructions": request.custom_instructions,
            "ai_model": user_settings.get('ai_model', 'standard')
        }
        
        # Process via Router
        agent_result = await router.route_and_process(
            user_id=user["_id"],
            message=trigger_message,
            context=agent_context
        )
        
        # Extract response from agent result
        msg_text = ""
        if agent_result and agent_result.get("handled"):
            # Combine all messages from agent into one draft
            msg_text = "\n\n".join([m.get("text", "") for m in agent_result.get("messages", [])])
            
        if not msg_text:
            msg_text = "Hi! Just checking in—can I help with anything?"
            
        result = {"message": msg_text, "reason": "Drafted by agent", "confidence": 0.9}
        
        # Support both legacy and new AI service response keys
        msg_text = result.get('message') or result.get('drafted_message') or "Hi! Just checking in—can I help with anything?"
        reason_text = result.get('reason') or result.get('ai_reason') or "Due for follow-up"
        confidence_val = result.get('confidence', 0.5)

        return DraftMessageResponse(
            message=msg_text,
            confidence=confidence_val,
            reason=reason_text
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
        
        # Check if we have today's analysis
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        existing_analysis_count = await db.customer_analysis.count_documents({
            "user_id": user["_id"],
            "analysis_date": {"$gte": today}
        })
        
        # If no analysis for today OR we're just starting up, queue a background run
        # We check count > 0 to see if results are already flowing in
        if existing_analysis_count == 0:
            logging.info(f"Triggering background analysis for user {user['_id']}")
            background_tasks.add_task(analyzer.analyze_all_customers, user["_id"])
        
        # Get whatever insights we have so far (poll correctly handles partial results)
        insights = await analyzer.get_todays_insights(user["_id"], limit)
        
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

# ============ DAILY PULSE ENDPOINTS ============

async def generate_daily_pulse_message(user_id: str) -> str:
    """Generate the daily business pulse summary message"""
    from datetime import timedelta
    
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    # Get user info
    user = await db.users.find_one({"_id": user_id})
    business_name = user.get("business_name", "Your Business") if user else "Your Business"
    currency = user.get("settings", {}).get("currency", "USD") if user else "USD"
    
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
    
    lines.append("\n_Sent by Charo360 CRM_")
    
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
        "country_code": country_code
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
    count = await db.products.count_documents({"user_id": business_id})
    if count >= MAX_PRODUCTS:
        raise HTTPException(status_code=400, detail=f"Product limit reached. Maximum {MAX_PRODUCTS} products allowed.")
    if count + len(files) > MAX_PRODUCTS:
        raise HTTPException(status_code=400, detail=f"Can only add {MAX_PRODUCTS - count} more product(s). You have {count}/{MAX_PRODUCTS}.")
    
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

app.include_router(api_router)

# Serve static files (product images)
app.mount("/uploads", StaticFiles(directory=str(ROOT_DIR / "uploads")), name="uploads")

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

logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

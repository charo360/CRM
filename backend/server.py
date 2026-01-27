from fastapi import FastAPI, APIRouter, HTTPException, Depends, BackgroundTasks, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
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
from twilio.rest import Client as TwilioClient
# from emergentintegrations.llm.chat import LlmChat, UserMessage
from ai_message_drafter import get_drafter
from daily_analyzer import DailyCustomerAnalyzer
from notification_service import get_notification_service
from image_handler import ImageUploadHandler
from product_organizer import get_organizer
from fastapi import UploadFile, File
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Gemini API Key
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'whatsapp_crm')]

# Twilio setup
twilio_client = TwilioClient(
    os.environ.get('TWILIO_ACCOUNT_SID'),
    os.environ.get('TWILIO_AUTH_TOKEN')
)

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'default-secret-key')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

# Paystack Config
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')
PAYSTACK_BASE_URL = "https://api.paystack.co"

app = FastAPI(title="WhatsApp CRM Kenya")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

# Configure CORS to allow mobile app connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ PYDANTIC MODELS ============

# Auth Models
class OTPRequest(BaseModel):
    phone_number: str  # E.164 format: +254...

class OTPVerify(BaseModel):
    phone_number: str
    code: str

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
    created_at: datetime

# Customer Models
class CustomerCreate(BaseModel):
    name: str
    phone_number: str
    notes: Optional[str] = None
    tags: List[str] = []

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None

class CustomerResponse(BaseModel):
    id: str
    user_id: str
    name: str
    phone_number: str
    notes: Optional[str] = None
    tags: List[str] = []
    purchase_count: int = 0
    total_spent: float = 0.0
    last_message: Optional[str] = None
    last_contacted: Optional[datetime] = None
    created_at: datetime

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

class FollowUpResponse(BaseModel):
    id: str
    user_id: str
    customer_id: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    reminder_date: datetime
    message: Optional[str] = None
    status: str = "pending"  # pending, completed, cancelled
    type: str = "call"
    created_at: datetime

# Sales/Receipt Models
class SaleCreate(BaseModel):
    customer_id: str
    item: str
    amount: float
    payment_method: str  # Cash, M-Pesa
    send_receipt: bool = True

class SaleResponse(BaseModel):
    id: str
    user_id: str
    customer_id: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    item: str
    amount: float
    payment_method: str
    receipt_sent: bool = False
    created_at: datetime

# Broadcast Models
class BroadcastCreate(BaseModel):
    message: str
    filter_type: str = "all"  # all, returning, vip
    customer_ids: Optional[List[str]] = None

class BroadcastResponse(BaseModel):
    id: str
    user_id: str
    message: str
    filter_type: str
    recipients_count: int
    sent_count: int = 0
    status: str = "pending"
    created_at: datetime

# Subscription Models
class SubscriptionPlan(BaseModel):
    id: str
    name: str
    amount: int  # in cents
    amount_display: str
    interval: str
    features: List[str]

class PaymentInitRequest(BaseModel):
    email: str
    plan_id: str

class PaymentVerifyRequest(BaseModel):
    reference: str

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
    daily_alert_count: Optional[int] = None
    message_tone: Optional[str] = None
    push_token: Optional[str] = None

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

class ProductCreate(BaseModel):
    name: str
    price: float
    image_url: str
    category: Optional[str] = "Other"
    description: Optional[str] = None
    in_stock: bool = True

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    in_stock: Optional[bool] = None

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

# Store OTPs temporarily (in production, use Redis)
otp_store = {}

def generate_otp() -> str:
    import random
    return str(random.randint(100000, 999999))

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

# ============ AUTH ENDPOINTS ============

@api_router.post("/auth/send-otp")
async def send_otp(request: OTPRequest):
    """Send OTP to phone number via SMS"""
    phone = request.phone_number
    
    # Generate OTP
    otp = generate_otp()
    otp_store[phone] = {
        "code": otp,
        "expires": datetime.utcnow() + timedelta(minutes=10)
    }
    
    # Check if we have a real Twilio phone number configured
    twilio_phone = os.environ.get('TWILIO_PHONE_NUMBER')
    
    if twilio_phone and not twilio_phone.startswith('+1500'):  # Not a test number
        try:
            # Send SMS via Twilio (LIVE MODE)
            message = twilio_client.messages.create(
                body=f"Your WhatsApp CRM verification code is: {otp}",
                from_=twilio_phone,
                to=phone
            )
            return {"status": "success", "message": "OTP sent successfully"}
        except Exception as e:
            logging.error(f"Twilio error: {e}")
            # Fall back to sandbox mode
            return {"status": "success", "message": "OTP sent (sandbox)", "dev_otp": otp}
    else:
        # SANDBOX MODE - Show OTP in response for testing
        logging.info(f"SANDBOX MODE: OTP for {phone} is {otp}")
        return {"status": "success", "message": "OTP sent (sandbox)", "dev_otp": otp}

@api_router.post("/auth/verify-otp")
async def verify_otp(request: OTPVerify):
    """Verify OTP and return JWT token"""
    phone = request.phone_number
    code = request.code
    
    stored = otp_store.get(phone)
    if not stored:
        raise HTTPException(status_code=400, detail="OTP not found. Please request a new one.")
    
    if datetime.utcnow() > stored["expires"]:
        del otp_store[phone]
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")
    
    if stored["code"] != code:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    # Clear OTP
    del otp_store[phone]
    
    # Check if user exists
    user = await db.users.find_one({"phone_number": phone})
    
    if user:
        token = create_token(user["_id"], phone)
        return {
            "status": "success",
            "token": token,
            "is_new_user": False,
            "user": {
                "id": user["_id"],
                "phone_number": user["phone_number"],
                "business_name": user.get("business_name", ""),
                "owner_name": user.get("owner_name", ""),
                "subscription_active": user.get("subscription_active", False)
            }
        }
    else:
        # Return temporary token for registration
        temp_token = create_token("temp_" + phone, phone)
        return {
            "status": "success",
            "token": temp_token,
            "is_new_user": True
        }

@api_router.post("/auth/register")
async def register_user(user_data: UserCreate):
    """Register new user after OTP verification"""
    # Check if user already exists
    existing = await db.users.find_one({"phone_number": user_data.phone_number})
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    
    user_id = str(uuid.uuid4())
    user_doc = {
        "_id": user_id,
        "phone_number": user_data.phone_number,
        "business_name": user_data.business_name,
        "owner_name": user_data.owner_name,
        "subscription_plan": None,
        "subscription_active": False,
        "created_at": datetime.utcnow()
    }
    
    await db.users.insert_one(user_doc)
    token = create_token(user_id, user_data.phone_number)
    
    return {
        "status": "success",
        "token": token,
        "user": {
            "id": user_id,
            "phone_number": user_data.phone_number,
            "business_name": user_data.business_name,
            "owner_name": user_data.owner_name,
            "subscription_active": False
        }
    }

@api_router.get("/auth/me")
async def get_me(user = Depends(get_current_user)):
    """Get current user info"""
    return {
        "id": user["_id"],
        "phone_number": user["phone_number"],
        "business_name": user.get("business_name", ""),
        "owner_name": user.get("owner_name", ""),
        "subscription_plan": user.get("subscription_plan"),
        "subscription_active": user.get("subscription_active", False)
    }

# ============ CUSTOMER ENDPOINTS ============

@api_router.post("/customers", response_model=CustomerResponse)
async def create_customer(customer: CustomerCreate, user = Depends(get_current_user)):
    """Create a new customer"""
    customer_id = str(uuid.uuid4())
    customer_doc = {
        "_id": customer_id,
        "user_id": user["_id"],
        "name": customer.name,
        "phone_number": customer.phone_number,
        "notes": customer.notes,
        "tags": customer.tags if customer.tags else ["New"],
        "purchase_count": 0,
        "total_spent": 0.0,
        "last_message": None,
        "last_contacted": None,
        "created_at": datetime.utcnow()
    }
    
    await db.customers.insert_one(customer_doc)
    
    return CustomerResponse(
        id=customer_id,
        user_id=user["_id"],
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

@api_router.get("/customers", response_model=List[CustomerResponse])
async def get_customers(tag: Optional[str] = None, sort_by: Optional[str] = None, user = Depends(get_current_user)):
    """Get all customers for current user"""
    query = {"user_id": user["_id"]}
    if tag:
        query["tags"] = tag
    
    # Defaults
    sort_field = "created_at"
    sort_order = -1
    
    if sort_by == "purchases":
        sort_field = "purchase_count"
        sort_order = -1
    
    customers = await db.customers.find(query).sort(sort_field, sort_order).to_list(1000)
    
    return [
        CustomerResponse(
            id=c["_id"],
            user_id=c["user_id"],
            name=c["name"],
            phone_number=c["phone_number"],
            notes=c.get("notes"),
            tags=c.get("tags", []),
            purchase_count=c.get("purchase_count", 0),
            total_spent=c.get("total_spent", 0.0),
            last_message=c.get("last_message"),
            last_contacted=c.get("last_contacted"),
            created_at=c["created_at"]
        )
        for c in customers
    ]

@api_router.get("/customers/cold")
async def get_cold_customers(days: int = 14, user = Depends(get_current_user)):
    """Get customers who haven't been contacted in X days"""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    customers = await db.customers.find({
        "user_id": user["_id"],
        "$or": [
            {"last_contacted": {"$lt": cutoff_date}},
            {"last_contacted": None}
        ]
    }).sort("last_contacted", 1).to_list(100)
    
    result = []
    for c in customers:
        pending_followup = await db.followups.find_one({"customer_id": c["_id"], "status": "pending"})
        days_since_contact = (datetime.utcnow() - c["last_contacted"]).days if c.get("last_contacted") else None
        ai_reason = await generate_quick_reason(c, [])
        result.append({
            "id": c["_id"], "name": c["name"], "phone_number": c["phone_number"],
            "notes": c.get("notes"), "tags": c.get("tags", []),
            "last_message": c.get("last_message"), "last_contacted": c.get("last_contacted"),
            "days_since_contact": days_since_contact, "has_pending_followup": pending_followup is not None,
            "ai_reason": ai_reason, "created_at": c["created_at"]
        })
    result.sort(key=lambda x: x["days_since_contact"] if x["days_since_contact"] else 999, reverse=True)
    return result

@api_router.get("/customers/cold-with-reasons")
async def get_cold_customers_with_ai_reasons(days: int = 14, user = Depends(get_current_user)):
    """Alias for get_cold_customers to support frontend with reasons included"""
    return await get_cold_customers(days, user)

@api_router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str, user = Depends(get_current_user)):
    """Get a specific customer"""
    customer = await db.customers.find_one({"_id": customer_id, "user_id": user["_id"]})
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
        created_at=customer["created_at"]
    )

@api_router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(customer_id: str, update: CustomerUpdate, user = Depends(get_current_user)):
    """Update a customer"""
    customer = await db.customers.find_one({"_id": customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    update_data = {k: v for k, v in update.dict().items() if v is not None}
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
        last_message=updated.get("last_message"),
        last_contacted=updated.get("last_contacted"),
        created_at=updated["created_at"]
    )

@api_router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, user = Depends(get_current_user)):
    """Delete a customer"""
    result = await db.customers.delete_one({"_id": customer_id, "user_id": user["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"status": "success", "message": "Customer deleted"}

# ============ FOLLOW-UP ENDPOINTS ============

@api_router.post("/followups", response_model=FollowUpResponse)
async def create_followup(followup: FollowUpCreate, user = Depends(get_current_user)):
    """Create a follow-up reminder"""
    # Verify customer exists
    customer = await db.customers.find_one({"_id": followup.customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    followup_id = str(uuid.uuid4())
    followup_doc = {
        "_id": followup_id,
        "user_id": user["_id"],
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
        user_id=user["_id"],
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
    query = {"user_id": user["_id"]}
    if status:
        query["status"] = status
    
    followups = await db.followups.find(query).sort("reminder_date", 1).to_list(1000)
    
    result = []
    for f in followups:
        customer = await db.customers.find_one({"_id": f["customer_id"]})
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
            created_at=f["created_at"]
        ))
    
    return result

@api_router.put("/followups/{followup_id}", response_model=FollowUpResponse)
async def update_followup(followup_id: str, update: FollowUpUpdate, user = Depends(get_current_user)):
    """Update a follow-up"""
    followup = await db.followups.find_one({"_id": followup_id, "user_id": user["_id"]})
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
    result = await db.followups.delete_one({"_id": followup_id, "user_id": user["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return {"status": "success", "message": "Follow-up deleted"}

# ============ SALES/RECEIPT ENDPOINTS ============

@api_router.post("/sales", response_model=SaleResponse)
async def create_sale(sale: SaleCreate, background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    """Record a sale and optionally send receipt"""
    # Verify customer exists
    customer = await db.customers.find_one({"_id": sale.customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    sale_id = str(uuid.uuid4())
    sale_doc = {
        "_id": sale_id,
        "user_id": user["_id"],
        "customer_id": sale.customer_id,
        "item": sale.item,
        "amount": sale.amount,
        "payment_method": sale.payment_method,
        "receipt_sent": False,
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
    if sale.send_receipt:
        background_tasks.add_task(
            send_receipt_message,
            customer["phone_number"],
            customer["name"],
            sale.item,
            sale.amount,
            user.get("business_name", "Your Shop"),
            sale_id
        )
    
    return SaleResponse(
        id=sale_id,
        user_id=user["_id"],
        customer_id=sale.customer_id,
        customer_name=customer["name"],
        customer_phone=customer["phone_number"],
        item=sale.item,
        amount=sale.amount,
        payment_method=sale.payment_method,
        receipt_sent=sale.send_receipt,
        created_at=sale_doc["created_at"]
    )

async def send_receipt_message(phone: str, name: str, item: str, amount: float, business: str, sale_id: str):
    """Send receipt via SMS (WhatsApp requires approved templates)"""
    try:
        message = f"""✅ Payment received
Item: {item}
Amount: KES {amount:,.0f}
Thank you for shopping with {business} 🙏"""
        
        twilio_client.messages.create(
            body=message,
            from_=os.environ.get('TWILIO_PHONE_NUMBER', '+15005550006'),
            to=phone
        )
        
        # Update receipt status
        await db.sales.update_one({"_id": sale_id}, {"$set": {"receipt_sent": True}})
    except Exception as e:
        logging.error(f"Failed to send receipt: {e}")

@api_router.get("/sales", response_model=List[SaleResponse])
async def get_sales(user = Depends(get_current_user)):
    """Get all sales for current user"""
    sales = await db.sales.find({"user_id": user["_id"]}).sort("created_at", -1).to_list(1000)
    
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

# ============ BROADCAST ENDPOINTS ============

@api_router.post("/broadcasts", response_model=BroadcastResponse)
async def create_broadcast(broadcast: BroadcastCreate, background_tasks: BackgroundTasks, user = Depends(get_current_user)):
    """Create and send a broadcast message"""
    # Get recipients based on filter
    query = {"user_id": user["_id"]}
    
    if broadcast.filter_type == "returning":
        query["tags"] = "Returning"
    elif broadcast.filter_type == "vip":
        query["tags"] = "VIP"
    elif broadcast.customer_ids:
        query["_id"] = {"$in": broadcast.customer_ids}
    
    customers = await db.customers.find(query).to_list(1000)
    
    broadcast_id = str(uuid.uuid4())
    broadcast_doc = {
        "_id": broadcast_id,
        "user_id": user["_id"],
        "message": broadcast.message,
        "filter_type": broadcast.filter_type,
        "recipients_count": len(customers),
        "sent_count": 0,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    
    await db.broadcasts.insert_one(broadcast_doc)
    
    # Send messages in background
    background_tasks.add_task(
        send_broadcast_messages,
        broadcast_id,
        broadcast.message,
        customers
    )
    
    return BroadcastResponse(
        id=broadcast_id,
        user_id=user["_id"],
        message=broadcast.message,
        filter_type=broadcast.filter_type,
        recipients_count=len(customers),
        sent_count=0,
        status="sending",
        created_at=broadcast_doc["created_at"]
    )

async def send_broadcast_messages(broadcast_id: str, message: str, customers: list):
    """Send broadcast to all recipients"""
    sent_count = 0
    for customer in customers:
        try:
            twilio_client.messages.create(
                body=message,
                from_=os.environ.get('TWILIO_PHONE_NUMBER', '+15005550006'),
                to=customer["phone_number"]
            )
            sent_count += 1
        except Exception as e:
            logging.error(f"Failed to send to {customer['phone_number']}: {e}")
    
    # Update broadcast status
    await db.broadcasts.update_one(
        {"_id": broadcast_id},
        {"$set": {"sent_count": sent_count, "status": "completed"}}
    )

@api_router.get("/broadcasts", response_model=List[BroadcastResponse])
async def get_broadcasts(user = Depends(get_current_user)):
    """Get all broadcasts for current user"""
    broadcasts = await db.broadcasts.find({"user_id": user["_id"]}).sort("created_at", -1).to_list(100)
    
    return [
        BroadcastResponse(
            id=b["_id"],
            user_id=b["user_id"],
            message=b["message"],
            filter_type=b["filter_type"],
            recipients_count=b["recipients_count"],
            sent_count=b.get("sent_count", 0),
            status=b["status"],
            created_at=b["created_at"]
        )
        for b in broadcasts
    ]

# ============ SUBSCRIPTION ENDPOINTS ============

SUBSCRIPTION_PLANS = [
    {
        "id": "starter",
        "name": "Starter",
        "amount": 70000,  # KES 700 in cents
        "amount_display": "KES 700/month",
        "interval": "monthly",
        "features": ["Up to 100 customers", "Basic follow-ups", "Receipt sending"]
    },
    {
        "id": "standard",
        "name": "Standard",
        "amount": 100000,  # KES 1000 in cents
        "amount_display": "KES 1,000/month",
        "interval": "monthly",
        "features": ["Up to 500 customers", "Unlimited follow-ups", "Broadcast messages", "Priority support"]
    },
    {
        "id": "pro",
        "name": "Pro",
        "amount": 150000,  # KES 1500 in cents
        "amount_display": "KES 1,500/month",
        "interval": "monthly",
        "features": ["Unlimited customers", "Advanced analytics", "Custom templates", "WhatsApp Business API", "Dedicated support"]
    }
]

@api_router.get("/subscription/plans")
async def get_subscription_plans():
    """Get available subscription plans"""
    return SUBSCRIPTION_PLANS

@api_router.post("/subscription/initialize")
async def initialize_payment(request: PaymentInitRequest, user = Depends(get_current_user)):
    """Initialize Paystack payment"""
    plan = next((p for p in SUBSCRIPTION_PLANS if p["id"] == request.plan_id), None)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "email": request.email,
        "amount": plan["amount"],
        "currency": "KES",
        "channels": ["card", "mobile_money"],
        "metadata": {
            "user_id": user["_id"],
            "plan_id": plan["id"],
            "plan_name": plan["name"]
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYSTACK_BASE_URL}/transaction/initialize",
            json=payload,
            headers=headers
        )
        data = response.json()
        
        if data.get("status"):
            return {
                "status": "success",
                "authorization_url": data["data"]["authorization_url"],
                "reference": data["data"]["reference"]
            }
        else:
            raise HTTPException(status_code=400, detail=data.get("message", "Payment initialization failed"))

@api_router.post("/subscription/verify")
async def verify_payment(request: PaymentVerifyRequest, user = Depends(get_current_user)):
    """Verify Paystack payment"""
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{request.reference}",
            headers=headers
        )
        data = response.json()
        
        if data.get("status") and data["data"].get("status") == "success":
            # Update user subscription
            plan_id = data["data"]["metadata"].get("plan_id")
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "subscription_plan": plan_id,
                        "subscription_active": True,
                        "subscription_date": datetime.utcnow()
                    }
                }
            )
            
            # Store transaction
            await db.transactions.insert_one({
                "_id": str(uuid.uuid4()),
                "user_id": user["_id"],
                "reference": request.reference,
                "amount": data["data"]["amount"],
                "plan_id": plan_id,
                "status": "success",
                "created_at": datetime.utcnow()
            })
            
            return {
                "status": "success",
                "message": "Subscription activated",
                "plan": plan_id
            }
        else:
            raise HTTPException(status_code=400, detail="Payment verification failed")

@api_router.post("/webhooks/paystack")
async def paystack_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle Paystack webhooks"""
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    
    # Verify signature
    if PAYSTACK_SECRET_KEY:
        hash_obj = hmac.new(
            PAYSTACK_SECRET_KEY.encode('utf-8'),
            body,
            hashlib.sha512
        )
        if hash_obj.hexdigest() != signature:
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    payload = json.loads(body)
    event = payload.get("event")
    data = payload.get("data", {})
    
    if event == "charge.success":
        user_id = data.get("metadata", {}).get("user_id")
        plan_id = data.get("metadata", {}).get("plan_id")
        
        if user_id and plan_id:
            await db.users.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "subscription_plan": plan_id,
                        "subscription_active": True,
                        "subscription_date": datetime.utcnow()
                    }
                }
            )
    
    return {"status": "ok"}

# ============ WHATSAPP WEBHOOK ENDPOINTS ============

@api_router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Receive incoming WhatsApp messages from Twilio
    Auto-creates customers when new numbers message us
    Stores all messages for AI analysis
    """
    try:
        form_data = await request.form()
        
        from_number = form_data.get("From", "").replace("whatsapp:", "")
        to_number = form_data.get("To", "").replace("whatsapp:", "")
        body = form_data.get("Body", "")
        profile_name = form_data.get("ProfileName", "")
        
        if not from_number:
            return {"status": "ok"}
        
        # Find the business owner by their WhatsApp number
        user = await db.users.find_one({"phone_number": to_number})
        if not user:
            # Try without country code variations
            user = await db.users.find_one({})  # For testing, get first user
        
        if not user:
            logging.warning(f"No user found for number {to_number}")
            return {"status": "ok"}
        
        # Check if customer already exists
        customer = await db.customers.find_one({
            "user_id": user["_id"],
            "phone_number": from_number
        })
        
        customer_id = None
        
        if customer:
            customer_id = customer["_id"]
            # Update existing customer with last message
            await db.customers.update_one(
                {"_id": customer["_id"]},
                {
                    "$set": {
                        "last_message": body[:200] if body else None,
                        "last_contacted": datetime.utcnow()
                    }
                }
            )
            logging.info(f"Updated customer {customer['name']} with new message")
        else:
            # Auto-create new customer
            customer_id = str(uuid.uuid4())
            customer_name = profile_name if profile_name else f"Customer {from_number[-4:]}"
            
            await db.customers.insert_one({
                "_id": customer_id,
                "user_id": user["_id"],
                "name": customer_name,
                "phone_number": from_number,
                "notes": f"Auto-added from WhatsApp chat",
                "tags": ["New"],
                "last_message": body[:200] if body else None,
                "last_contacted": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "auto_created": True
            })
            logging.info(f"Auto-created customer: {customer_name} ({from_number})")
        
        # Store the message for AI analysis
        if customer_id and body:
            message_id = str(uuid.uuid4())
            await db.messages.insert_one({
                "_id": message_id,
                "customer_id": customer_id,
                "user_id": user["_id"],
                "direction": "incoming",
                "content": body,
                "message_type": "text",
                "from_number": from_number,
                "to_number": to_number,
                "created_at": datetime.utcnow()
            })
            logging.info(f"Stored incoming message from {from_number}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logging.error(f"WhatsApp webhook error: {e}")
        return {"status": "error", "message": str(e)}

# ============ SMART FOLLOW-UP ENDPOINTS ============

@api_router.get("/stats/followup-suggestions")
async def get_followup_suggestions(user = Depends(get_current_user)):
    """
    Get smart follow-up suggestions based on customer activity
    """
    now = datetime.utcnow()
    
    # Customers not contacted in 7+ days
    week_ago = now - timedelta(days=7)
    neglected_week = await db.customers.count_documents({
        "user_id": user["_id"],
        "last_contacted": {"$lt": week_ago}
    })
    
    # Customers not contacted in 30+ days
    month_ago = now - timedelta(days=30)
    neglected_month = await db.customers.count_documents({
        "user_id": user["_id"],
        "last_contacted": {"$lt": month_ago}
    })
    
    # New customers (never followed up)
    new_no_followup = await db.customers.count_documents({
        "user_id": user["_id"],
        "tags": "New",
        "last_contacted": None
    })
    
    # VIP customers not contacted in 14+ days
    two_weeks_ago = now - timedelta(days=14)
    vip_neglected = await db.customers.count_documents({
        "user_id": user["_id"],
        "tags": "VIP",
        "last_contacted": {"$lt": two_weeks_ago}
    })
    
    return {
        "neglected_week": neglected_week,
        "neglected_month": neglected_month,
        "new_no_followup": new_no_followup,
        "vip_neglected": vip_neglected,
        "total_needing_attention": neglected_week + new_no_followup
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

# ============ AI-POWERED ENDPOINTS ============

async def analyze_customer_with_ai(customer: dict, messages: list, user: dict) -> dict:
    """Use Gemini AI to analyze customer conversation and generate insights"""
    if not GEMINI_API_KEY:
        # Fallback if no API key
        return {
            "summary": "Unable to analyze - AI not configured",
            "follow_up_reason": "Customer hasn't been contacted recently",
            "suggested_message": f"Hi {customer.get('name', 'there')}! Just checking in. How can I help you today?",
            "interests": [],
            "sentiment": "neutral"
        }
    
    try:
        # Build conversation context
        conversation_text = ""
        if messages:
            for msg in messages[-20:]:  # Last 20 messages
                direction = "Customer" if msg.get("direction") == "incoming" else "You"
                conversation_text += f"{direction}: {msg.get('content', '')}\n"
        
        notes = customer.get("notes", "") or ""
        tags = ", ".join(customer.get("tags", []))
        last_message = customer.get("last_message", "") or ""
        days_since = ""
        if customer.get("last_contacted"):
            days = (datetime.utcnow() - customer["last_contacted"]).days
            days_since = f"{days} days ago"
        else:
            days_since = "Never contacted"
        
        business_name = user.get("business_name", "the business")
        
        prompt = f"""You are an AI assistant for a small business CRM in Kenya. Analyze this customer data and provide actionable insights.

CUSTOMER INFO:
- Name: {customer.get('name', 'Unknown')}
- Phone: {customer.get('phone_number', 'Unknown')}
- Tags: {tags}
- Notes: {notes}
- Last message from customer: {last_message}
- Last contacted: {days_since}

RECENT CONVERSATION:
{conversation_text if conversation_text else "No conversation history available"}

Based on this information, provide:
1. A brief summary of this customer (1-2 sentences)
2. A specific reason why they need follow-up now (be specific, e.g., "Asked about iPhone 15 pricing but didn't purchase" or "New customer, hasn't received welcome message")
3. A suggested WhatsApp message to send (casual, friendly Kenyan business style, keep it short)
4. List any products/services they showed interest in
5. Their sentiment (positive, neutral, negative, or unknown)

Respond in this exact JSON format:
{{"summary": "...", "follow_up_reason": "...", "suggested_message": "...", "interests": ["item1", "item2"], "sentiment": "..."}}
"""

        # chat = LlmChat(
        #     api_key=GEMINI_API_KEY,
        #     session_id=f"analyze_{customer['_id']}",
        #     system_message="You are a helpful CRM assistant. Always respond with valid JSON only."
        # ).with_model("gemini", "gemini-2.5-flash")
        
        # response = await chat.send_message(UserMessage(text=prompt))
        
        # # Parse JSON response
        # import re
        # json_match = re.search(r'\{.*\}', response, re.DOTALL)
        # if json_match:
        #     result = json.loads(json_match.group())
        #     return result
        # else:
        #     raise ValueError("No JSON found in response")
        raise Exception("LLM Disabled")
            
    except Exception as e:
        logging.error(f"AI analysis error: {e}")
        # Return fallback
        days_text = ""
        if customer.get("last_contacted"):
            days = (datetime.utcnow() - customer["last_contacted"]).days
            days_text = f"Last contacted {days} days ago"
        else:
            days_text = "Never contacted"
            
        return {
            "summary": f"Customer since {customer.get('created_at', datetime.utcnow()).strftime('%b %Y')}",
            "follow_up_reason": days_text,
            "suggested_message": f"Hi {customer.get('name', 'there')}! Hope you're doing well. Is there anything I can help you with today?",
            "interests": [],
            "sentiment": "neutral"
        }

async def generate_notes_from_messages(customer: dict, messages: list) -> str:
    """Use AI to generate notes from conversation history"""
    if not GEMINI_API_KEY or not messages:
        return customer.get("notes", "") or "No conversation to analyze"
    
    try:
        conversation_text = ""
        for msg in messages[-30:]:
            direction = "Customer" if msg.get("direction") == "incoming" else "Business"
            conversation_text += f"{direction}: {msg.get('content', '')}\n"
        
        prompt = f"""Analyze this WhatsApp business conversation and extract key information as CRM notes.

CONVERSATION:
{conversation_text}

Create brief, useful CRM notes that include:
- What products/services the customer is interested in
- Any specific requirements or preferences mentioned
- Price points discussed
- Any commitments or next steps agreed
- Customer's tone/attitude

Keep it concise (max 3-4 bullet points). Use simple language."""

        # chat = LlmChat(
        #     api_key=GEMINI_API_KEY,
        #     session_id=f"notes_{customer['_id']}",
        #     system_message="You are a CRM assistant. Generate concise, actionable notes."
        # ).with_model("gemini", "gemini-2.5-flash")
        
        # response = await chat.send_message(UserMessage(text=prompt))
        # return response.strip()
        return "Notes generation disabled."
        
    except Exception as e:
        logging.error(f"Notes generation error: {e}")
        return customer.get("notes", "") or "Could not generate notes"

@api_router.get("/customers/{customer_id}/ai-analysis")
async def get_customer_ai_analysis(customer_id: str, user = Depends(get_current_user)):
    """Get AI-powered analysis for a customer"""
    customer = await db.customers.find_one({"_id": customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get customer's messages
    messages = await db.messages.find({"customer_id": customer_id}).sort("created_at", 1).to_list(50)
    
    analysis = await analyze_customer_with_ai(customer, messages, user)
    
    return {
        "customer_id": customer_id,
        **analysis
    }

@api_router.post("/customers/{customer_id}/generate-notes")
async def generate_customer_notes(customer_id: str, user = Depends(get_current_user)):
    """Generate AI notes from customer conversations"""
    customer = await db.customers.find_one({"_id": customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    messages = await db.messages.find({"customer_id": customer_id}).sort("created_at", 1).to_list(50)
    
    notes = await generate_notes_from_messages(customer, messages)
    
    # Update customer notes
    await db.customers.update_one(
        {"_id": customer_id},
        {"$set": {"notes": notes, "notes_generated_at": datetime.utcnow()}}
    )
    
    return {"customer_id": customer_id, "notes": notes}

async def generate_quick_reason(customer: dict, messages: list) -> str:
    """Generate a quick follow-up reason without full AI call for performance"""
    last_message = customer.get("last_message", "")
    notes = customer.get("notes", "")
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

# ============ MESSAGE STORAGE ENDPOINTS ============

@api_router.get("/customers/{customer_id}/messages")
async def get_customer_messages(customer_id: str, limit: int = 50, user = Depends(get_current_user)):
    """Get messages for a customer"""
    customer = await db.customers.find_one({"_id": customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    messages = await db.messages.find({"customer_id": customer_id}).sort("created_at", -1).to_list(limit)
    
    return [
        {
            "id": m["_id"],
            "customer_id": m["customer_id"],
            "direction": m["direction"],
            "content": m["content"],
            "message_type": m.get("message_type", "text"),
            "created_at": m["created_at"]
        }
        for m in messages
    ]

@api_router.post("/customers/{customer_id}/messages")
async def add_customer_message(customer_id: str, message: MessageCreate, user = Depends(get_current_user)):
    """Manually add a message to customer history"""
    customer = await db.customers.find_one({"_id": customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    message_id = str(uuid.uuid4())
    message_doc = {
        "_id": message_id,
        "customer_id": customer_id,
        "user_id": user["_id"],
        "direction": message.direction,
        "content": message.content,
        "message_type": message.message_type,
        "created_at": datetime.utcnow()
    }
    
    await db.messages.insert_one(message_doc)
    
    # Update customer's last message and contacted time
    update_data = {"last_contacted": datetime.utcnow()}
    if message.direction == "incoming":
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

@api_router.post("/ai/draft-message", response_model=DraftMessageResponse)
async def draft_ai_message(request: DraftMessageRequest, user = Depends(get_current_user)):
    """Generate AI-drafted follow-up message for a customer"""
    
    # Get customer
    customer = await db.customers.find_one({"_id": request.customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get message history
    messages = await db.messages.find({
        "customer_id": request.customer_id
    }).sort("timestamp", 1).limit(10).to_list(10)
    
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
    
    # Draft message using AI
    drafter = get_drafter()
    result = await drafter.draft_followup_message(
        customer_name=customer['name'],
        customer_data=customer,
        messages=messages,
        business_name=business_name,
        tone=tone,
        business_knowledge=business_knowledge
    )
    
    return DraftMessageResponse(
        message=result['message'],
        confidence=result['confidence'],
        reason=result['reason']
    )

@api_router.post("/ai/send-auto-message")
async def send_auto_message(request: SendAutoMessageRequest, user = Depends(get_current_user)):
    """Send an auto-drafted message via WhatsApp"""
    
    # Check if auto-reply is enabled
    user_settings = user.get('settings', {})
    if not user_settings.get('auto_reply_enabled', False):
        raise HTTPException(status_code=403, detail="Auto-reply is not enabled")
    
    # Get customer
    customer = await db.customers.find_one({"_id": request.customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Store message in database
    message_id = str(uuid.uuid4())
    message_doc = {
        "_id": message_id,
        "customer_id": request.customer_id,
        "user_id": user["_id"],
        "direction": "outgoing",
        "content": request.message,
        "message_type": "text",
        "timestamp": datetime.utcnow(),
        "auto_sent": True
    }
    await db.messages.insert_one(message_doc)
    
    # Update customer's last contacted time
    await db.customers.update_one(
        {"_id": request.customer_id},
        {"$set": {"last_contacted": datetime.utcnow()}}
    )
    
    # TODO: Actually send via WhatsApp API when integrated
    # For now, we'll just return success and the user can manually send
    
    return {
        "status": "success",
        "message_id": message_id,
        "note": "Message logged. WhatsApp integration pending."
    }

@api_router.get("/analysis/daily-insights")
async def get_daily_insights(limit: int = 10, user = Depends(get_current_user)):
    """Get today's customer insights from AI analysis"""
    
    analyzer = DailyCustomerAnalyzer(db)
    
    # Check if we have today's analysis
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    existing_analysis = await db.customer_analysis.find_one({
        "user_id": user["_id"],
        "analysis_date": {"$gte": today}
    })
    
    # If no analysis for today, run it now
    if not existing_analysis:
        logging.info(f"No analysis found for today, running now for user {user['_id']}")
        await analyzer.analyze_all_customers(user["_id"])
    
    # Get insights
    insights = await analyzer.get_todays_insights(user["_id"], limit)
    
    return insights

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

# ============ USER SETTINGS ENDPOINTS ============

@api_router.get("/settings")
async def get_user_settings(user = Depends(get_current_user)):
    """Get user settings"""
    settings = user.get('settings', {})
    
    # Return with defaults
    return {
        "auto_reply_enabled": settings.get('auto_reply_enabled', False),
        "notification_enabled": settings.get('notification_enabled', True),
        "notification_time": settings.get('notification_time', '08:00'),
        "daily_alert_count": settings.get('daily_alert_count', 5),
        "message_tone": settings.get('message_tone', 'friendly'),
        "push_token": user.get('push_token')
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
    
    if settings.push_token is not None:
        update_data['push_token'] = settings.push_token
    
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

# ============ PRODUCT CATALOG ENDPOINTS ============

@api_router.post("/products/upload")
async def upload_products(
    files: List[UploadFile] = File(...),
    user = Depends(get_current_user)
):
    """Bulk upload product images with AI analysis"""
    
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
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
    
    ai_analyses = await organizer.analyze_multiple_images([str(p) for p in image_paths])
    
    # Create product documents
    products = []
    now = datetime.utcnow()
    
    for i, (img_data, ai_data) in enumerate(zip(successful_uploads, ai_analyses)):
        if 'error' in ai_data:
            continue
        
        product_id = str(uuid.uuid4())
        product_doc = {
            "_id": product_id,
            "user_id": user["_id"],
            "name": ai_data.get('name', f'Product {i+1}'),
            "price": ai_data.get('suggested_price', 0.0),
            "image_url": img_data['image_url'],
            "category": ai_data.get('category', 'Other'),
            "description": ai_data.get('description', ''),
            "in_stock": True,
            "ai_suggested_name": ai_data.get('name'),
            "ai_confidence": ai_data.get('confidence', 0.5),
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
                "category": p["category"],
                "image_url": p["image_url"],
                "ai_confidence": p["ai_confidence"]
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
    
    return [
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
    ]

@api_router.get("/products/{product_id}")
async def get_product(product_id: str, user = Depends(get_current_user)):
    """Get a single product"""
    
    product = await db.products.find_one({"_id": product_id, "user_id": user["_id"]})
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {
        "id": product["_id"],
        "name": product["name"],
        "price": product["price"],
        "image_url": product["image_url"],
        "category": product.get("category", "Other"),
        "description": product.get("description", ""),
        "in_stock": product.get("in_stock", True),
        "ai_suggested_name": product.get("ai_suggested_name"),
        "ai_confidence": product.get("ai_confidence"),
        "created_at": product["created_at"].isoformat()
    }

@api_router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    product_update: ProductUpdate,
    user = Depends(get_current_user)
):
    """Update product details"""
    
    product = await db.products.find_one({"_id": product_id, "user_id": user["_id"]})
    
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
    
    product = await db.products.find_one({"_id": product_id, "user_id": user["_id"]})
    
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
    customer_id: str,
    user = Depends(get_current_user)
):
    """Send product image to customer via WhatsApp"""
    
    # Get product
    product = await db.products.find_one({"_id": product_id, "user_id": user["_id"]})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get customer
    customer = await db.customers.find_one({"_id": customer_id, "user_id": user["_id"]})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # TODO: Send via WhatsApp API when integrated
    # For now, just log the message
    message_id = str(uuid.uuid4())
    message_doc = {
        "_id": message_id,
        "customer_id": customer_id,
        "user_id": user["_id"],
        "direction": "outgoing",
        "content": f"{product['name']} - KES {product['price']:,.0f}",
        "message_type": "image",
        "image_url": product["image_url"],
        "timestamp": datetime.utcnow()
    }
    
    await db.messages.insert_one(message_doc)
    
    return {
        "status": "success",
        "message_id": message_id,
        "note": "Product logged. WhatsApp integration pending."
    }

# ============ MAIN APP SETUP ============

app.include_router(api_router)

# Serve static files (product images)
app.mount("/uploads", StaticFiles(directory=str(ROOT_DIR / "uploads")), name="uploads")

@app.on_event("startup")
async def startup_event():
    """Run startup tasks"""
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

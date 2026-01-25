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
from emergentintegrations.llm.chat import LlmChat, UserMessage

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
    last_message: Optional[str] = None
    last_contacted: Optional[datetime] = None
    created_at: datetime

# Follow-up Models
class FollowUpCreate(BaseModel):
    customer_id: str
    reminder_date: datetime
    message: Optional[str] = None

class FollowUpUpdate(BaseModel):
    reminder_date: Optional[datetime] = None
    message: Optional[str] = None
    status: Optional[str] = None

class FollowUpResponse(BaseModel):
    id: str
    user_id: str
    customer_id: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    reminder_date: datetime
    message: Optional[str] = None
    status: str = "pending"  # pending, completed, cancelled
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
        last_message=None,
        last_contacted=None,
        created_at=customer_doc["created_at"]
    )

@api_router.get("/customers", response_model=List[CustomerResponse])
async def get_customers(tag: Optional[str] = None, user = Depends(get_current_user)):
    """Get all customers for current user"""
    query = {"user_id": user["_id"]}
    if tag:
        query["tags"] = tag
    
    customers = await db.customers.find(query).sort("created_at", -1).to_list(1000)
    
    return [
        CustomerResponse(
            id=c["_id"],
            user_id=c["user_id"],
            name=c["name"],
            phone_number=c["phone_number"],
            notes=c.get("notes"),
            tags=c.get("tags", []),
            last_message=c.get("last_message"),
            last_contacted=c.get("last_contacted"),
            created_at=c["created_at"]
        )
        for c in customers
    ]

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
    if "New" in customer.get("tags", []):
        new_tags = [t for t in customer.get("tags", []) if t != "New"]
        new_tags.append("Returning")
        await db.customers.update_one(
            {"_id": sale.customer_id},
            {"$set": {"tags": new_tags, "last_contacted": datetime.utcnow()}}
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
        
        if customer:
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
        
        return {"status": "ok"}
        
    except Exception as e:
        logging.error(f"WhatsApp webhook error: {e}")
        return {"status": "error", "message": str(e)}

# ============ SMART FOLLOW-UP ENDPOINTS ============

@api_router.get("/customers/cold")
async def get_cold_customers(days: int = 14, user = Depends(get_current_user)):
    """
    Get customers who haven't been contacted in X days
    These are potential follow-up opportunities
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Find customers not contacted recently
    customers = await db.customers.find({
        "user_id": user["_id"],
        "$or": [
            {"last_contacted": {"$lt": cutoff_date}},
            {"last_contacted": None}
        ]
    }).sort("last_contacted", 1).to_list(100)
    
    # Check which ones don't have pending follow-ups
    result = []
    for c in customers:
        pending_followup = await db.followups.find_one({
            "customer_id": c["_id"],
            "status": "pending"
        })
        
        days_since_contact = None
        if c.get("last_contacted"):
            days_since_contact = (datetime.utcnow() - c["last_contacted"]).days
        
        result.append({
            "id": c["_id"],
            "name": c["name"],
            "phone_number": c["phone_number"],
            "notes": c.get("notes"),
            "tags": c.get("tags", []),
            "last_message": c.get("last_message"),
            "last_contacted": c.get("last_contacted"),
            "days_since_contact": days_since_contact,
            "has_pending_followup": pending_followup is not None,
            "created_at": c["created_at"]
        })
    
    # Sort by days since contact (most neglected first)
    result.sort(key=lambda x: x["days_since_contact"] if x["days_since_contact"] else 999, reverse=True)
    
    return result

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

        chat = LlmChat(
            api_key=GEMINI_API_KEY,
            session_id=f"analyze_{customer['_id']}",
            system_message="You are a helpful CRM assistant. Always respond with valid JSON only."
        ).with_model("gemini", "gemini-2.5-flash")
        
        response = await chat.send_message(UserMessage(text=prompt))
        
        # Parse JSON response
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            raise ValueError("No JSON found in response")
            
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

        chat = LlmChat(
            api_key=GEMINI_API_KEY,
            session_id=f"notes_{customer['_id']}",
            system_message="You are a CRM assistant. Generate concise, actionable notes."
        ).with_model("gemini", "gemini-2.5-flash")
        
        response = await chat.send_message(UserMessage(text=prompt))
        return response.strip()
        
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

@api_router.get("/customers/cold-with-reasons")
async def get_cold_customers_with_ai_reasons(days: int = 14, user = Depends(get_current_user)):
    """
    Get cold customers with AI-generated follow-up reasons
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    customers = await db.customers.find({
        "user_id": user["_id"],
        "$or": [
            {"last_contacted": {"$lt": cutoff_date}},
            {"last_contacted": None}
        ]
    }).sort("last_contacted", 1).to_list(50)
    
    result = []
    for c in customers:
        pending_followup = await db.followups.find_one({
            "customer_id": c["_id"],
            "status": "pending"
        })
        
        days_since_contact = None
        if c.get("last_contacted"):
            days_since_contact = (datetime.utcnow() - c["last_contacted"]).days
        
        # Get messages for AI analysis
        messages = await db.messages.find({"customer_id": c["_id"]}).sort("created_at", -1).to_list(20)
        
        # Generate AI reason (simplified for performance)
        ai_reason = await generate_quick_reason(c, messages)
        
        result.append({
            "id": c["_id"],
            "name": c["name"],
            "phone_number": c["phone_number"],
            "notes": c.get("notes"),
            "tags": c.get("tags", []),
            "last_message": c.get("last_message"),
            "last_contacted": c.get("last_contacted"),
            "days_since_contact": days_since_contact,
            "has_pending_followup": pending_followup is not None,
            "ai_reason": ai_reason,
            "created_at": c["created_at"]
        })
    
    result.sort(key=lambda x: x["days_since_contact"] if x["days_since_contact"] else 999, reverse=True)
    
    return result

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

# ============ MAIN APP SETUP ============

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

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
    
    try:
        # Send SMS via Twilio
        message = twilio_client.messages.create(
            body=f"Your WhatsApp CRM verification code is: {otp}",
            from_=os.environ.get('TWILIO_PHONE_NUMBER', '+15005550006'),  # Use test number if not set
            to=phone
        )
        return {"status": "success", "message": "OTP sent successfully"}
    except Exception as e:
        # For development, still store OTP but log error
        logging.error(f"Twilio error: {e}")
        # Return success for testing (OTP is stored)
        return {"status": "success", "message": "OTP sent (dev mode)", "dev_otp": otp}

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

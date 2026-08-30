"""Seed the Android/iOS phone-auth test account for Zilo CRM.

The mobile app signs in with Firebase Phone Auth (see AuthContext.sendOTP ->
/auth/firebase). Repeated real sign-ups get the tester's number SMS-blocked, so
testing runs on a Firebase *test phone number* instead: Firebase Console ->
Authentication -> Sign-in method -> Phone -> "Phone numbers for testing".
Those numbers never send an SMS and never touch the SMS quota, but they still
mint a real ID token, so /auth/firebase accepts them unchanged.

This script prepares the matching Zilo account for that number.

Usage:
    cd CRM/backend
    python scripts/seed_mobile_test_account.py

Set RESET=1 to wipe the account and re-seed a ready-to-use dashboard:
    RESET=1 python scripts/seed_mobile_test_account.py

Set FRESH=1 to delete the account and leave it deleted, so the next sign-in in
the app runs the full new-user onboarding flow again:
    FRESH=1 python scripts/seed_mobile_test_account.py

Override the number (must match the one registered in Firebase Console):
    TEST_PHONE=+16505553434 python scripts/seed_mobile_test_account.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

from motor.motor_asyncio import AsyncIOMotorClient

# Must match the number registered in Firebase Console. +1 650-555-xxxx is the
# fictional range Firebase's own docs use, so it can never reach a real handset.
TEST_PHONE    = os.environ.get("TEST_PHONE", "+16505553434").strip()
TEST_BUSINESS = "Zilo Test Shop"
TEST_OWNER    = "Test Tester"
RESET         = os.environ.get("RESET", "").lower() in ("1", "true", "yes")
FRESH         = os.environ.get("FRESH", "").lower() in ("1", "true", "yes")

# Every collection the app writes against a user_id.
USER_COLLECTIONS = [
    "activity_logs", "bookings", "broadcast_automations", "broadcast_templates",
    "broadcasts", "contact_documents", "conversation_assignments",
    "customer_analysis", "customer_groups", "customers", "expenses",
    "followup_events", "followups", "messages", "order_payments", "orders",
    "products", "sales", "transactions",
]


def uid() -> str:
    return str(uuid.uuid4())


def now(offset_days: int = 0) -> datetime:
    return datetime.utcnow() + timedelta(days=offset_days)


PRODUCTS = [
    {"name": "Cold Brew Coffee 500ml", "price": 6.50,  "category": "Drinks", "stock_quantity": 40, "description": "Slow-steeped 18 hours, no added sugar."},
    {"name": "Almond Croissant",       "price": 4.25,  "category": "Bakery", "stock_quantity": 24, "description": "Butter laminated, filled with almond cream."},
    {"name": "House Blend Beans 1kg",  "price": 22.00, "category": "Beans",  "stock_quantity": 15, "description": "Medium roast, chocolate and citrus notes."},
    {"name": "Ceramic Pour-Over Set",  "price": 38.00, "category": "Gear",   "stock_quantity": 8,  "description": "Dripper, carafe and 50 filters."},
    {"name": "Reusable Cup 350ml",     "price": 14.00, "category": "Gear",   "stock_quantity": 30, "description": "Double-walled, dishwasher safe."},
]

CUSTOMERS = [
    ("Ada Nwosu",     "+12025550101", ["VIP", "Returning"], 11, 320.50, True),
    ("Ben Carter",    "+12025550102", ["Returning"],         6, 148.00, False),
    ("Chloe Martin",  "+12025550103", ["Returning"],         4,  92.25, False),
    ("Diego Alvarez", "+12025550104", ["New"],               1,  22.00, False),
    ("Ella Virtanen", "+12025550105", ["At Risk"],           5, 110.75, False),
]

FOLLOWUP_NOTES = [
    ("Ada Nwosu",     "Asked about a wholesale rate for the house blend - send pricing."),
    ("Ella Virtanen", "No order in 6 weeks - send a win-back offer."),
    ("Diego Alvarez", "First order last week - check they were happy with it."),
]


async def purge(db, user_id: str) -> None:
    """Remove the account and everything hanging off it."""
    for col in USER_COLLECTIONS:
        result = await db[col].delete_many({"user_id": user_id})
        if result.deleted_count:
            print(f"[seed]   Deleted {result.deleted_count:>3} {col}")

    # A stale team_members row for this phone would send the next sign-in down
    # the team-member branch of _complete_verified_phone_login instead of
    # creating an owner account, so it has to go too.
    tm = await db.team_members.delete_many(
        {"$or": [{"business_id": user_id}, {"phone_number": TEST_PHONE}]}
    )
    if tm.deleted_count:
        print(f"[seed]   Deleted {tm.deleted_count:>3} team_members")

    await db.otp_codes.delete_one({"_id": TEST_PHONE})
    await db.users.delete_many({"$or": [{"_id": user_id}, {"phone_number": TEST_PHONE}]})
    print(f"[seed]   Deleted user {user_id}")


async def seed():
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        sys.exit("[seed] MONGO_URL is not set - check backend/.env")
    if not TEST_PHONE.startswith("+") or len(TEST_PHONE) < 8:
        sys.exit(f"[seed] TEST_PHONE must be E.164, e.g. +16505553434 (got {TEST_PHONE!r})")

    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get("DB_NAME", "whatsapp_crm")]

    existing = await db.users.find_one({"phone_number": TEST_PHONE})

    if FRESH:
        if existing:
            user_id = str(existing.get("business_id") or existing["_id"])
            print(f"[seed] Deleting test account for a clean onboarding run (user_id={user_id})...")
            await purge(db, user_id)
        else:
            print("[seed] No existing test account - already clean.")
        print(f"""
+----------------------------------------------------------+
|            TEST ACCOUNT CLEARED                          |
+----------------------------------------------------------+
|  Phone: {TEST_PHONE:<48} |
|                                                          |
|  Sign in on the app with this number and the fixed code  |
|  from Firebase Console. It runs the full new-user        |
|  onboarding flow, with no SMS sent.                      |
+----------------------------------------------------------+
""")
        client.close()
        return

    if existing and RESET:
        user_id = str(existing.get("business_id") or existing["_id"])
        print(f"[seed] Resetting existing account (user_id={user_id})...")
        await purge(db, user_id)
        existing = None

    if existing and not RESET:
        print(f"""
Test account already exists - skipping seed.
   Phone: {TEST_PHONE}
   Run with RESET=1 to wipe and re-seed, or FRESH=1 to test onboarding.
""")
        client.close()
        return

    user_id = uid()
    await db.users.insert_one({
        "_id":                 user_id,
        "phone_number":        TEST_PHONE,
        "business_name":       TEST_BUSINESS,
        "owner_name":          TEST_OWNER,
        "business_id":         user_id,
        "role":                "owner",
        # Matches what /auth/firebase records for a real phone sign-in, so the
        # account behaves identically to one created through the app.
        "auth_provider":       "firebase_phone",
        "subscription_plan":   None,
        "subscription_active": False,
        "country_code":        "US",
        "currency":            "USD",
        "setup_complete":      True,
        "settings": {
            "business_type":           "retail",
            "onboarding_v1_completed": True,
        },
        "payment_methods": [
            {"name": "Credit Card", "details": ""},
            {"name": "Cash",        "details": ""},
        ],
        "created_at": now(-30),
    })
    print(f"[seed] OK User created  (id={user_id})")

    for p in PRODUCTS:
        await db.products.insert_one({
            "_id":            uid(),
            "user_id":        user_id,
            "name":           p["name"],
            "price":          p["price"],
            "discount_price": None,
            "description":    p["description"],
            "category":       p["category"],
            "in_stock":       True,
            "stock_quantity": p["stock_quantity"],
            "images":         [],
            "variants":       [],
            "moq":            1,
            "created_at":     now(-25),
        })
    print(f"[seed] OK {len(PRODUCTS)} products created")

    customer_map: dict[str, str] = {}
    for (name, phone, tags, purchase_count, total_spent, vip) in CUSTOMERS:
        cid = uid()
        customer_map[name] = cid
        days_ago = max(1, 30 - purchase_count * 2)
        await db.customers.insert_one({
            "_id":            cid,
            "user_id":        user_id,
            "name":           name,
            "phone_number":   phone,
            "email":          "",
            "tags":           tags,
            "purchase_count": purchase_count,
            "total_spent":    total_spent,
            "vip":            vip,
            "notes":          "",
            "is_customer":    True,
            "last_contacted": now(-days_ago),
            "last_message":   None,
            "created_at":     now(-30),
            "updated_at":     now(-days_ago),
        })
    print(f"[seed] OK {len(CUSTOMERS)} customers created")

    statuses = ["Done", "Done", "Confirmed", "Preparing", "New"]
    orders_created = 0
    for i, (name, cid) in enumerate(customer_map.items()):
        for j in range(2):
            prod  = PRODUCTS[(i + j) % len(PRODUCTS)]
            qty   = (j % 3) + 1
            total = round(prod["price"] * qty, 2)
            status = statuses[(i + j) % len(statuses)]
            await db.orders.insert_one({
                "_id":            uid(),
                "user_id":        user_id,
                "customer_id":    cid,
                "order_number":   f"MT-{1000 + orders_created + 1}",
                "product_name":   prod["name"],
                "items": [{
                    "product_name": prod["name"],
                    "quantity":     qty,
                    "price":        prod["price"],
                    "subtotal":     total,
                }],
                "total_amount":   total,
                "total":          total,
                "quantity":       qty,
                "status":         status,
                "payment_status": "paid" if status == "Done" else "unpaid",
                "delivery_type":  "delivery",
                "notes":          "",
                "created_at":     now(-(28 - orders_created)),
            })
            orders_created += 1
    print(f"[seed] OK {orders_created} orders created")

    for i, (cname, note) in enumerate(FOLLOWUP_NOTES):
        cid = customer_map.get(cname, uid())
        overdue = i == 0
        await db.followups.insert_one({
            "_id":           uid(),
            "user_id":       user_id,
            "customer_id":   cid,
            "customer_name": cname,
            "note":          note,
            "message":       note,
            "status":        "pending",
            "type":          "whatsapp",
            "reminder_date": now(-2 if overdue else (i * 2 + 1)),
            "due_date":      now(-2 if overdue else (i * 2 + 1)),
            "assigned_to":   user_id,
            "created_at":    now(-7),
        })
    print(f"[seed] OK {len(FOLLOWUP_NOTES)} follow-ups created (1 overdue)")

    print(f"""
+----------------------------------------------------------+
|            MOBILE TEST ACCOUNT READY                     |
+----------------------------------------------------------+
|  Phone:    {TEST_PHONE:<45} |
|  Code:     the fixed code set in Firebase Console        |
|  Business: {TEST_BUSINESS:<45} |
+----------------------------------------------------------+
|  Seeded data:                                            |
|   - {len(PRODUCTS)} products                                         |
|   - {len(CUSTOMERS)} customers (VIP, New, At-Risk, Returning)         |
|   - {orders_created} orders across several statuses                 |
|   - {len(FOLLOWUP_NOTES)} follow-ups (1 overdue)                         |
+----------------------------------------------------------+
|  RESET=1  wipe and re-seed this ready-to-use account     |
|  FRESH=1  delete it, so the next sign-in runs onboarding |
+----------------------------------------------------------+
""")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())

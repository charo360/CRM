"""Seed a Shopify test account for Zilo CRM development and QA.

Creates a ready-to-use merchant account with realistic data for testing
Shopify integration flows (OAuth, billing, webhooks, product sync, etc.)

Usage:
    cd CRM/backend
    python scripts/seed_shopify_test_account.py

Set RESET=1 to wipe the account and re-seed from scratch:
    RESET=1 python scripts/seed_shopify_test_account.py
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
from passlib.context import CryptContext

TEST_EMAIL    = "shopifytest@zilo.pro"
TEST_PASSWORD = "ZiloTest2025!"
TEST_BUSINESS = "The Test Store — Electronics"
TEST_OWNER    = "Alex Test"
RESET         = os.environ.get("RESET", "").lower() in ("1", "true", "yes")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def uid() -> str:
    return str(uuid.uuid4())

def now(offset_days: int = 0) -> datetime:
    return datetime.utcnow() + timedelta(days=offset_days)


PRODUCTS = [
    {"name": "Wireless Noise-Cancelling Headphones", "price": 199.99, "category": "Audio",       "stock_quantity": 30, "description": "Over-ear BT 5.3, 40h battery, active noise cancellation."},
    {"name": "Smart Watch Pro",                      "price": 249.99, "category": "Wearables",   "stock_quantity": 20, "description": "AMOLED display, health tracking, 7-day battery."},
    {"name": "USB-C Hub 7-in-1",                     "price":  49.99, "category": "Accessories", "stock_quantity": 80, "description": "HDMI 4K, 3× USB-A, SD/MicroSD, 100W PD."},
    {"name": "Mechanical Keyboard TKL",              "price": 129.99, "category": "Peripherals", "stock_quantity": 25, "description": "Tenkeyless, hot-swap switches, per-key RGB."},
    {"name": "27-inch 4K Monitor",                   "price": 399.99, "category": "Displays",    "stock_quantity": 12, "description": "IPS panel, 144Hz, USB-C, factory-calibrated."},
    {"name": "Portable SSD 1TB",                     "price":  89.99, "category": "Storage",     "stock_quantity": 50, "description": "USB 3.2 Gen 2, 1050MB/s read, shock-resistant."},
    {"name": "Webcam 4K Auto-Focus",                 "price":  79.99, "category": "Peripherals", "stock_quantity": 35, "description": "4K 30fps, built-in stereo mic, privacy cover."},
    {"name": "RGB Gaming Mouse",                     "price":  59.99, "category": "Peripherals", "stock_quantity": 60, "description": "25K DPI sensor, 11 programmable buttons."},
    {"name": "Laptop Stand Adjustable",              "price":  34.99, "category": "Accessories", "stock_quantity": 70, "description": "Aluminium, 6 height settings, foldable."},
    {"name": "Fast Wireless Charger 15W",            "price":  29.99, "category": "Accessories", "stock_quantity": 90, "description": "Qi2, compatible with iPhone & Android, LED indicator."},
]

CUSTOMERS = [
    ("Jordan Lee",      "+12025550001", "jordan@testmail.com",  ["VIP", "Returning"],  12, 2340.00, True),
    ("Morgan Smith",    "+12025550002", "morgan@testmail.com",  ["VIP", "Returning"],  9,  1870.50, True),
    ("Riley Johnson",   "+12025550003", "riley@testmail.com",   ["VIP"],               7,  1025.00, True),
    ("Casey Brown",     "+12025550004", "casey@testmail.com",   ["Returning"],         6,   720.00, False),
    ("Taylor Davis",    "+12025550005", "taylor@testmail.com",  ["Returning"],         5,   540.00, False),
    ("Jamie Wilson",    "+12025550006", "jamie@testmail.com",   ["Returning"],         4,   430.00, False),
    ("Avery Miller",    "+12025550007", "avery@testmail.com",   ["New"],               2,   199.99, False),
    ("Cameron Moore",   "+12025550008", "cameron@testmail.com", ["New"],               2,   179.98, False),
    ("Dakota Taylor",   "+12025550009", "dakota@testmail.com",  ["New"],               1,    89.99, False),
    ("Reese Anderson",  "+12025550010", "reese@testmail.com",   ["New"],               1,    49.99, False),
    ("Skyler Thomas",   "+12025550011", "skyler@testmail.com",  ["New"],               1,    59.99, False),
    ("Quinn Jackson",   "+12025550012", "quinn@testmail.com",   ["New"],               1,    34.99, False),
    ("Blake Martinez",  "+12025550013", "blake@testmail.com",   ["At Risk"],           5,   650.00, False),
    ("Drew Garcia",     "+12025550014", "drew@testmail.com",    ["At Risk"],           3,   310.00, False),
    ("Finley White",    "+12025550015", "finley@testmail.com",  ["At Risk"],           3,   280.00, False),
]

ORDER_STATUSES = ["Done", "Done", "Done", "Confirmed", "Preparing", "New", "Cancelled"]

BROADCAST_MESSAGES = [
    {
        "name":    "Black Friday Deals",
        "message": "🖤 Black Friday is HERE! Up to 50% off headphones, monitors & more. Limited stock — shop now: https://teststore.zilo.pro/bf",
        "status":  "sent", "recipients_count": 15, "sent_count": 15,
    },
    {
        "name":    "New Arrivals — Smart Watch Pro",
        "message": "The Smart Watch Pro just landed! 🕐 Health tracking, 7-day battery, AMOLED display. Get yours: https://teststore.zilo.pro/new",
        "status":  "sent", "recipients_count": 12, "sent_count": 12,
    },
    {
        "name":    "VIP Early Access — 4K Monitor",
        "message": "VIP perk: 24-hour early access to our new 4K Monitor before it goes public. 🎉 Shop: https://teststore.zilo.pro/vip",
        "status":  "sent", "recipients_count": 3, "sent_count": 3,
    },
    {
        "name":    "Win-Back — At Risk Customers",
        "message": "Hi {name}, we noticed you haven't visited lately 👋 Here's 10% off your next order. Use COMEBACK10 at checkout.",
        "status":  "sent", "recipients_count": 3, "sent_count": 3,
    },
    {
        "name":    "Cyber Monday Flash Sale",
        "message": "⚡ CYBER MONDAY — 30% off sitewide today only! No code needed. Ends midnight: https://teststore.zilo.pro",
        "status":  "scheduled", "recipients_count": 15, "sent_count": 0,
    },
]

FOLLOWUP_NOTES = [
    ("Jordan Lee",    "Asked about bulk order pricing for the USB-C Hub — follow up with quote."),
    ("Blake Martinez","No order in 2 months — send win-back message with 10% discount."),
    ("Drew Garcia",   "Reported package delay — check shipping status and update."),
    ("Finley White",  "Interested in Smart Watch Pro but unsure about compatibility — clarify."),
    ("Casey Brown",   "Returning customer — recommend new accessories based on past purchases."),
    ("Avery Miller",  "First-time buyer — check they're happy with the Webcam order."),
]


async def seed():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "whatsapp_crm")]

    existing = await db.users.find_one({"email": TEST_EMAIL})
    if existing and RESET:
        user_id = str(existing.get("business_id") or existing["_id"])
        print(f"[seed] Resetting existing account (user_id={user_id})…")
        for col in ["customers", "products", "orders", "broadcasts", "followups"]:
            result = await db[col].delete_many({"user_id": user_id})
            print(f"[seed]   Deleted {result.deleted_count} {col}")
        await db.users.delete_one({"_id": existing["_id"]})
        existing = None

    if existing and not RESET:
        print(f"\n✅ Test account already exists — skipping seed.")
        print(f"   Email:    {TEST_EMAIL}")
        print(f"   Password: {TEST_PASSWORD}")
        print(f"   Run with RESET=1 to wipe and re-seed.")
        return

    user_id = uid()
    await db.users.insert_one({
        "_id":                    user_id,
        "email":                  TEST_EMAIL,
        "password_hash":          pwd_ctx.hash(TEST_PASSWORD),
        "phone_number":           "+12025550000",
        "business_name":          TEST_BUSINESS,
        "owner_name":             TEST_OWNER,
        "business_id":            user_id,
        "role":                   "owner",
        "auth_provider":          "email_web",
        "subscription_plan":      "growth",
        "subscription_active":    True,
        "shopify_plan":           "growth",
        "shopify_billing_status": "active",
        "country_code":           "US",
        "currency":               "USD",
        "setup_complete":         True,
        "settings": {
            "business_type":           "electronics",
            "onboarding_v1_completed": True,
        },
        "payment_methods": [
            {"name": "Credit Card", "details": ""},
            {"name": "PayPal",      "details": ""},
        ],
        "created_at": now(-60),
    })
    print(f"[seed] ✓ User created  (id={user_id})")

    product_ids = []
    for p in PRODUCTS:
        pid = uid()
        product_ids.append(pid)
        await db.products.insert_one({
            "_id":            pid,
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
            "created_at":     now(-45),
        })
    print(f"[seed] ✓ {len(PRODUCTS)} products created")

    customer_map: dict[str, str] = {}
    for (name, phone, email, tags, purchase_count, total_spent, vip) in CUSTOMERS:
        cid = uid()
        customer_map[name] = cid
        days_ago = 60 if purchase_count == 0 else max(1, 60 - purchase_count * 4)
        await db.customers.insert_one({
            "_id":            cid,
            "user_id":        user_id,
            "name":           name,
            "phone_number":   phone,
            "email":          email,
            "tags":           tags,
            "purchase_count": purchase_count,
            "total_spent":    total_spent,
            "vip":            vip,
            "notes":          "",
            "is_customer":    True,
            "last_contacted": now(-days_ago) if purchase_count > 0 else None,
            "last_message":   None,
            "created_at":     now(-60),
            "updated_at":     now(-days_ago),
        })
    print(f"[seed] ✓ {len(CUSTOMERS)} customers created")

    orders_created = 0
    customer_list = list(customer_map.items())
    for i, (name, cid) in enumerate(customer_list[:12]):
        cdata = next(c for c in CUSTOMERS if c[0] == name)
        n_orders = min(cdata[4], 3) if cdata[4] > 0 else 0
        for j in range(n_orders):
            prod  = PRODUCTS[(i + j) % len(PRODUCTS)]
            qty   = (j % 3) + 1
            total = round(prod["price"] * qty, 2)
            status = ORDER_STATUSES[(i + j) % len(ORDER_STATUSES)]
            await db.orders.insert_one({
                "_id":            uid(),
                "user_id":        user_id,
                "customer_id":    cid,
                "order_number":   f"TS-{2000 + orders_created + 1}",
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
                "created_at":     now(-(60 - orders_created * 2)),
            })
            orders_created += 1
    print(f"[seed] ✓ {orders_created} orders created")

    for i, b in enumerate(BROADCAST_MESSAGES):
        await db.broadcasts.insert_one({
            "_id":              uid(),
            "user_id":          user_id,
            "name":             b["name"],
            "message":          b["message"],
            "filter_type":      "tags" if "VIP" in b["name"] else "all",
            "status":           b["status"],
            "recipients_count": b["recipients_count"],
            "sent_count":       b["sent_count"],
            "image_url":        None,
            "image_urls":       [],
            "scheduled_at":     now(2) if b["status"] == "scheduled" else None,
            "created_at":       now(-(len(BROADCAST_MESSAGES) - i) * 5),
        })
    print(f"[seed] ✓ {len(BROADCAST_MESSAGES)} broadcasts created")

    for i, (cname, note) in enumerate(FOLLOWUP_NOTES):
        cid = customer_map.get(cname, uid())
        overdue = i < 2
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
            "created_at":    now(-10),
        })
    print(f"[seed] ✓ {len(FOLLOWUP_NOTES)} follow-ups created ({sum(1 for i in range(2))} overdue)")

    print(f"""
╔══════════════════════════════════════════════════════════╗
║            SHOPIFY TEST ACCOUNT READY                   ║
╠══════════════════════════════════════════════════════════╣
║  URL:      https://zilo.pro                             ║
║  Email:    {TEST_EMAIL:<44} ║
║  Password: {TEST_PASSWORD:<44} ║
╠══════════════════════════════════════════════════════════╣
║  Business: The Test Store — Electronics                 ║
║  Plan:     Growth ($79/mo) — billing test mode ON       ║
╠══════════════════════════════════════════════════════════╣
║  Seeded data:                                           ║
║   • {len(PRODUCTS)} products (headphones, monitors, accessories…)     ║
║   • {len(CUSTOMERS)} customers (VIP, New, At-Risk, Returning)         ║
║   • {orders_created} orders in various statuses                    ║
║   • {len(BROADCAST_MESSAGES)} broadcasts (4 sent, 1 scheduled)              ║
║   • {len(FOLLOWUP_NOTES)} follow-ups (2 overdue)                       ║
╚══════════════════════════════════════════════════════════╝
""")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())

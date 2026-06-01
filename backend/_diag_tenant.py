"""Diagnostic: per-user data counts across tenant-scoped collections.

Read-only. Helps locate cross-account data bleed.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

COLLECTIONS = [
    "customers",
    "email_messages",
    "messages",
    "orders",
    "invoices",
    "zilo_sessions",
]


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "whatsapp_crm")]

    users = await db.users.find(
        {}, {"_id": 1, "email": 1, "business_id": 1, "created_at": 1}
    ).to_list(100)

    print(f"[diag] total users: {len(users)}\n")
    for u in users:
        uid = u["_id"]
        bid = u.get("business_id") or uid
        print(f"user={u.get('email','<no-email>')} _id={uid} business_id={bid}")
        for col in COLLECTIONS:
            key = "user_id" if col != "zilo_sessions" else "user_id"
            try:
                n_uid = await db[col].count_documents({key: uid})
                n_bid = await db[col].count_documents({key: bid})
                print(f"    {col:16} user_id={n_uid:<5} business_id={n_bid}")
            except Exception as e:
                print(f"    {col:16} error: {e}")
        print()


if __name__ == "__main__":
    asyncio.run(main())

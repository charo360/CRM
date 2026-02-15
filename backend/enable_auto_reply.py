import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.environ.get('MONGO_URL')
if not MONGO_URL:
    print("Error: MONGO_URL not found")
    exit(1)

DB_NAME = os.environ.get('DB_NAME', 'whatsapp_crm')

async def enable_ai():
    print(f"Connecting to DB...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    user_id = "366e141a-115c-4b28-8bed-362db48b2031"
    
    print(f"Enabling auto-reply for user {user_id}...")
    result = await db.users.update_one(
        {"_id": user_id},
        {"$set": {"settings.auto_reply_enabled": True}}
    )
    
    if result.modified_count > 0:
        print("✅ Auto-reply ENABLED successfully.")
    else:
        print("ℹ️ Auto-reply was already enabled (or user not found).")

    # Double check
    user = await db.users.find_one({"_id": user_id})
    print(f"Current Setting: {user.get('settings', {}).get('auto_reply_enabled')}")

if __name__ == "__main__":
    asyncio.run(enable_ai())

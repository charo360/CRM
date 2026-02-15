
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

# Load env
load_dotenv(Path(__file__).parent / '.env', override=True)

async def force_resync():
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017/crm_db")
    db_name = os.getenv("DB_NAME", "whatsapp_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Find user with whatsapp connected
    user = await db.users.find_one({"whatsapp.status": "connected"})
    if not user:
        print("No connected user found.")
        return

    print(f"Found user: {user.get('phone_number')}")
    
    # Unset initial_sync_done
    result = await db.users.update_one(
        {"_id": user["_id"]},
        {"$unset": {"whatsapp.initial_sync_done": ""}}
    )
    print(f"Unset initial_sync_done: {result.modified_count}")
    
    # Also unset synced_from_whatsapp for all customers to force update?
    # No, my code checks if synced_from_whatsapp is True.
    # But now I modified code to update name even if synced.
    # So just triggering fetch_contacts is enough.

if __name__ == "__main__":
    asyncio.run(force_resync())

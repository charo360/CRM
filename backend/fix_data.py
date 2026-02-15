
import asyncio
import os
import uuid
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

# Load env
load_dotenv(Path(__file__).parent / '.env', override=True)

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_data():
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017/crm_db")
    db_name = os.getenv("DB_NAME", "whatsapp_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Find user with whatsapp connected
    user = await db.users.find_one({"whatsapp.status": "connected"})
    if not user:
        print("No connected user found.")
        return

    user_id = user["_id"]
    print(f"Found user: {user.get('phone_number')}")
    
    # 1. Trigger Profile Picture Sync
    print("--- 1. Syncing Profile Pictures ---")
    # Need to instantiate WhatsAppService properly or just call the method if we can import
    # But whatsapp_service needs 'db' which is compatible.
    try:
        from whatsapp_service import WhatsAppService
        ws = WhatsAppService(db)
        
        # We can call fetch_profile_pictures_bulk directly
        result = await ws.fetch_profile_pictures_bulk(user_id)
        print(f"Profile Pics Updated: {result}")
    except Exception as e:
        print(f"Error syncing pics: {e}")

    # 2. Fix "Contact ..." names from Chat History
    print("--- 2. Fixing Contact Names from Chat History ---")
    # We'll re-run fetch_chat_history but we must make sure it updates the names
    # The code I just patched in whatsapp_service.py handle this.
    # So calling fetch_chat_history should update names for existing contacts!
    
    # However, fetch_chat_history skips if "synced_from_history" is True for messages?
    # No, it checks:
    # already_synced = count_documents({"customer_id": ..., "synced_from_history": True})
    # If > 0, it skips!
    
    # So I need to bypass this check or just manually update names here.
    
    # Let's manually update names by fetching chats directly from Evolution API.
    
    instance_name = user["whatsapp"]["instance_name"]
    print(f"Using instance: {instance_name}")
    
    base_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip('/')
    api_key = os.getenv("EVOLUTION_API_KEY", "")
    
    import httpx
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{base_url}/chat/findChats/{instance_name}",
                headers=headers,
                json={}
            )
            
            if resp.status_code == 200:
                chats = resp.json()
                updated_names = 0
                for chat in chats:
                    jid = chat.get("remoteJid", "")
                    if "@s.whatsapp.net" not in jid:
                        continue
                    
                    phone = jid.split("@")[0]
                    push_name = chat.get("pushName") or chat.get("name")
                    
                    if not push_name:
                        continue
                        
                    # Find customer
                    customer = await db.customers.find_one({
                        "user_id": user_id,
                        "phone_number": f"+{phone}"
                    })
                    
                    if customer and customer.get("name", "").startswith("Contact "):
                        await db.customers.update_one(
                            {"_id": customer["_id"]},
                            {"$set": {"name": push_name}}
                        )
                        updated_names += 1
                        print(f"Updated {phone} -> {push_name}")
                
                print(f"Total Names Updated: {updated_names}")
            else:
                print(f"Failed to fetch chats: {resp.text}")
    except Exception as e:
        print(f"Error fetching chats: {e}")

if __name__ == "__main__":
    asyncio.run(fix_data())

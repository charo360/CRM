
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

# Load env
load_dotenv(Path(__file__).parent / '.env', override=True)

async def force_names():
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017/crm_db")
    db_name = os.getenv("DB_NAME", "whatsapp_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Find customers with "Contact " name
    cursor = db.customers.find({"name": {"$regex": "^Contact "}})
    customers = await cursor.to_list(None)
    
    print(f"Found {len(customers)} customers with fallback names.")
    
    updated = 0
    for c in customers:
        # Check if they have a 'last_message' or if we can find a message from them
        # Sometimes messages have pushName stored in them?
        # My messages schema doesn't store pushName, but the incoming webhook parser returns it.
        # But we don't store it in the message doc.
        
        # However, we can check if there are other customers with same phone number? No, unique.
        
        pass

    print("--- Strategy 2: Use Evolution API 'findContacts' instead of 'findChats' ---")
    # findChats returns chat list. findContacts returns address book.
    # Maybe address book has names?
    
    user = await db.users.find_one({"whatsapp.status": "connected"})
    instance_name = user["whatsapp"]["instance_name"]
    base_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip('/')
    api_key = os.getenv("EVOLUTION_API_KEY", "")
    
    import httpx
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base_url}/chat/findContacts/{instance_name}",
            headers=headers,
            json={}
        )
        
        if resp.status_code == 200:
            contacts = resp.json()
            if isinstance(contacts, dict):
                contacts = contacts.get("data", [])
            
            print(f"Fetched {len(contacts)} contacts from address book.")
            
            for contact in contacts:
                jid = contact.get("id") or contact.get("remoteJid", "")
                if "@s.whatsapp.net" not in jid:
                    continue
                
                phone = jid.split("@")[0]
                name = contact.get("pushName") or contact.get("name") or contact.get("notify")
                
                if name:
                    # Update DB
                    res = await db.customers.update_one(
                        {"user_id": user["_id"], "phone_number": f"+{phone}", "name": {"$regex": "^Contact "}},
                        {"$set": {"name": name}}
                    )
                    if res.modified_count > 0:
                        print(f"Updated {phone} -> {name}")
                        updated += 1
    
    print(f"Total Names Updated via Address Book: {updated}")

if __name__ == "__main__":
    asyncio.run(force_names())

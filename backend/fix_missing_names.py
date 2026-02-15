
import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path
import httpx

# Load env
load_dotenv(Path(__file__).parent / '.env', override=True)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_names_advanced():
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017/crm_db")
    db_name = os.getenv("DB_NAME", "whatsapp_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Get connected user
    user = await db.users.find_one({"whatsapp.status": "connected"})
    if not user:
        print("No connected user found.")
        return

    instance_name = user["whatsapp"]["instance_name"]
    base_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip('/')
    api_key = os.getenv("EVOLUTION_API_KEY", "")
    
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    print(f"Fetching chats for instance: {instance_name}")
    
    async with httpx.AsyncClient(timeout=120) as http:
        resp = await http.post(
            f"{base_url}/chat/findChats/{instance_name}",
            headers=headers,
            json={}
        )
        
        if resp.status_code != 200:
            print(f"Error fetching chats: {resp.status_code}")
            return

        chats = resp.json()
        if isinstance(chats, dict):
            chats = chats.get("data", [])
            
        print(f"Processing {len(chats)} chats...")
        
        updated_count = 0
        
        for chat in chats:
            # 1. Extract Name
            name = chat.get("pushName") or chat.get("name")
            
            # If no name, check lastMessage
            last_msg = chat.get("lastMessage", {})
            if not name and last_msg:
                name = last_msg.get("pushName")
            
            if not name:
                continue

            # 2. Extract Phone Number
            remote_jid = chat.get("remoteJid", "")
            
            # Helper to extract phone from JID
            def extract_phone(jid):
                if "@s.whatsapp.net" in jid:
                    return jid.split("@")[0]
                return None

            phone = extract_phone(remote_jid)
            
            # If LID, try to find alternate JID in lastMessage
            if not phone and "@lid" in remote_jid:
                key = last_msg.get("key", {})
                alt_jid = key.get("remoteJidAlt")
                if alt_jid:
                    phone = extract_phone(alt_jid)
                
                # If still no phone, check if remoteJid in key is different (sometimes key has the phone jid)
                if not phone:
                    key_jid = key.get("remoteJid")
                    if key_jid and key_jid != remote_jid:
                        phone = extract_phone(key_jid)

            if not phone:
                continue
                
            # Normalize phone
            formatted_phone = f"+{phone}"
            
            # 3. Update DB
            # Try to find customer by this phone
            customer = await db.customers.find_one({
                "user_id": user["_id"],
                "phone_number": formatted_phone
            })
            
            if customer:
                # Update if current name is fallback OR empty
                curr_name = customer.get("name", "")
                if not curr_name or curr_name.startswith("Contact "):
                    await db.customers.update_one(
                        {"_id": customer["_id"]},
                        {"$set": {"name": name}}
                    )
                    print(f"Updated {formatted_phone}: {curr_name} -> {name}")
                    updated_count += 1
            else:
                # Verify if we have a customer with the LID-based number (the bad import)
                # If my previous sync imported "229050...@lid" as "+229050...", I should fix it!
                bad_phone = f"+{remote_jid.split('@')[0]}"
                bad_customer = await db.customers.find_one({
                    "user_id": user["_id"],
                    "phone_number": bad_phone
                })
                
                if bad_customer:
                    print(f"Fixing BAD LID customer: {bad_phone} -> {formatted_phone} ({name})")
                    await db.customers.update_one(
                        {"_id": bad_customer["_id"]},
                        {"$set": {
                            "phone_number": formatted_phone, 
                            "name": name,
                            # Also fix profile pic if needed?
                        }}
                    )
                    updated_count += 1

        print(f"Total Customers Updated: {updated_count}")

if __name__ == "__main__":
    asyncio.run(fix_names_advanced())

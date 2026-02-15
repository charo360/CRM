
import asyncio
import os
import logging
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

# Load env
load_dotenv(Path(__file__).parent / '.env', override=True)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONCURRENCY = 15

async def fetch_pic(http, db, instance_name, base_url, headers, cust, stats):
    phone = cust.get("phone_number", "").lstrip("+").replace(" ", "").replace("-", "")
    if not phone:
        return
        
    try:
        resp = await http.post(
            f"{base_url}/chat/fetchProfilePictureUrl/{instance_name}",
            headers=headers,
            json={"number": phone},
            timeout=15
        )
        
        stats["processed"] += 1
        
        if resp.status_code == 200:
            data = resp.json()
            pic_url = data.get("profilePictureUrl") or data.get("profilePicUrl") or data.get("url")
            if pic_url:
                await db.customers.update_one(
                    {"_id": cust["_id"]},
                    {"$set": {"profile_picture": pic_url}}
                )
                stats["updated"] += 1
            else:
                # Mark as attempted but empty
                await db.customers.update_one(
                    {"_id": cust["_id"]},
                    {"$set": {"profile_picture": ""}}
                )
        else:
             # Mark as attempted (404/others)
            await db.customers.update_one(
                {"_id": cust["_id"]},
                {"$set": {"profile_picture": ""}}
            )
            
    except Exception:
        stats["errors"] += 1
    
    if stats["processed"] % 50 == 0:
        print(f"Progress: {stats['processed']} processed. Updated: {stats['updated']}, Errors: {stats['errors']}")

async def super_sync():
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017/crm_db")
    db_name = os.getenv("DB_NAME", "whatsapp_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    user = await db.users.find_one({"whatsapp.status": "connected"})
    if not user:
        print("No connected user found.")
        return

    instance_name = user["whatsapp"]["instance_name"]
    base_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip('/')
    api_key = os.getenv("EVOLUTION_API_KEY", "")
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    print("--- Phase 1: Bulk findContacts ---")
    async with httpx.AsyncClient(timeout=60) as http:
        try:
            resp = await http.post(
                f"{base_url}/chat/findContacts/{instance_name}",
                headers=headers,
                json={}
            )
            if resp.status_code == 200:
                contacts = resp.json()
                if isinstance(contacts, dict): contacts = contacts.get("data", [])
                
                print(f"Resolving {len(contacts)} contacts from cache...")
                for c in contacts:
                    pic = c.get("profilePicUrl")
                    jid = c.get("id") or c.get("remoteJid", "")
                    if pic and "@s.whatsapp.net" in jid:
                        phone = f"+{jid.split('@')[0]}"
                        await db.customers.update_one(
                            {"user_id": user["_id"], "phone_number": phone},
                            {"$set": {"profile_picture": pic}}
                        )
        except Exception as e:
            print(f"findContacts failed: {e}")

    print("--- Phase 2: Individual fetch for remaining ---")
    cursor = db.customers.find(
        {
            "user_id": user["_id"], 
            "profile_picture": None
        },
        {"_id": 1, "phone_number": 1}
    )
    customers = await cursor.to_list(None)
    print(f"Processing {len(customers)} remaining customers...")
    
    stats = {"processed": 0, "updated": 0, "errors": 0}
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async with httpx.AsyncClient(timeout=30) as http:
        tasks = []
        async def sem_task(c):
            async with semaphore:
                await fetch_pic(http, db, instance_name, base_url, headers, c, stats)
                await asyncio.sleep(0.1)
        
        for cust in customers:
            tasks.append(sem_task(cust))
            
        await asyncio.gather(*tasks)

    print(f"Final Result - Processed: {stats['processed']}, Updated: {stats['updated']}, Errors: {stats['errors']}")

if __name__ == "__main__":
    asyncio.run(super_sync())

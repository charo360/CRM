import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

async def check_db():
    mongo_url = os.environ.get('MONGO_URL')
    client = AsyncIOMotorClient(mongo_url)
    db = client['whatsapp_crm']
    
    # Check customers for ai_reason field
    customers = await db.customers.find({}).to_list(100)
    print(f"Total customers: {len(customers)}")
    
    for c in customers:
        ai_reason = c.get('ai_reason', '')
        if ai_reason and ('gemini' in ai_reason.lower() or '404' in ai_reason or 'Fallback' in ai_reason):
            print(f"Customer {c.get('name')}: {ai_reason[:80]}")
    
    # Check all collections
    collections = await db.list_collection_names()
    print(f"\nCollections: {collections}")
    
    # Check followups
    followups = await db.followups.find({}).to_list(100)
    print(f"\nTotal followups: {len(followups)}")
    for f in followups:
        ai_reason = f.get('ai_reason', '')
        if ai_reason and ('gemini' in ai_reason.lower() or '404' in ai_reason or 'Fallback' in ai_reason):
            print(f"Followup: {ai_reason[:80]}")
    
    client.close()

asyncio.run(check_db())

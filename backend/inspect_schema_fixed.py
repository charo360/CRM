import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def inspect():
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME", "whatsapp_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    collections = ["orders", "customers", "products"]
    for coll_name in collections:
        doc = await db[coll_name].find_one({})
        if doc:
            print(f"--- {coll_name} ---")
            for k in doc.keys():
                print(f"  {k}")
        else:
            print(f"--- {coll_name} (Empty) ---")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(inspect())

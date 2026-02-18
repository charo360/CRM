import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def inspect_schema():
    mongo_uri = os.getenv("MONGO_URL", "mongodb://localhost:27017/crm_db")
    client = AsyncIOMotorClient(mongo_uri)
    db = client[os.environ.get('DB_NAME', 'whatsapp_crm')]
    
    print("--- Orders Sample ---")
    order = await db.orders.find_one({})
    print(order)
    
    print("\n--- Customers Sample ---")
    customer = await db.customers.find_one({})
    print(customer)
    
    client.close()

if __name__ == "__main__":
    asyncio.run(inspect_schema())

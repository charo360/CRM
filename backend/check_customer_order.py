import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def check_customers():
    """Check customer creation times and sorting"""
    mongo_url = os.environ.get('MONGO_URL')
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', 'whatsapp_crm')]
    
    # Get all customers sorted by created_at descending (newest first)
    customers = await db.customers.find({}).sort("created_at", -1).to_list(10)
    
    print("\n=== CUSTOMERS (Sorted by created_at DESC - Newest First) ===\n")
    for i, customer in enumerate(customers, 1):
        created_at = customer.get('created_at')
        auto_created = customer.get('auto_created', False)
        customer_initiated = customer.get('customer_initiated', False)
        
        print(f"{i}. {customer['name']}")
        print(f"   Phone: {customer['phone_number']}")
        print(f"   Created: {created_at}")
        print(f"   Auto-created: {auto_created}")
        print(f"   Customer initiated: {customer_initiated}")
        print(f"   Last contacted: {customer.get('last_contacted')}")
        print()
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_customers())

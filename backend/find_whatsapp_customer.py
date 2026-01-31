import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def find_whatsapp_customer():
    """Find the WhatsApp auto-created customer"""
    mongo_url = os.environ.get('MONGO_URL')
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', 'whatsapp_crm')]
    
    # Search for customer with your phone number
    customer = await db.customers.find_one({"phone_number": "+254796148903"})
    
    if customer:
        print("\n=== WHATSAPP CUSTOMER FOUND ===\n")
        print(f"Name: {customer['name']}")
        print(f"Phone: {customer['phone_number']}")
        print(f"Created: {customer.get('created_at')}")
        print(f"Auto-created: {customer.get('auto_created', False)}")
        print(f"Customer initiated: {customer.get('customer_initiated', False)}")
        print(f"Last contacted: {customer.get('last_contacted')}")
        print(f"Last message: {customer.get('last_message')}")
        
        # Count how many customers are newer
        newer_count = await db.customers.count_documents({
            "created_at": {"$gt": customer.get('created_at')}
        })
        print(f"\nCustomers created after this one: {newer_count}")
    else:
        print("\n❌ WhatsApp customer NOT FOUND with phone +254796148903")
        
        # Search by name
        mysafaricom = await db.customers.find_one({"name": {"$regex": "Mysafaricom", "$options": "i"}})
        if mysafaricom:
            print("\nFound by name 'Mysafaricom':")
            print(f"Phone: {mysafaricom['phone_number']}")
            print(f"Created: {mysafaricom.get('created_at')}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(find_whatsapp_customer())

"""
Fix Imported Customers
Sets last_contacted = created_at for imported customers so they don't all show as "never contacted"
This makes the system focus on customers with actual conversations
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_imported_customers():
    """Update imported customers to have realistic last_contacted dates"""
    
    print("\n" + "="*60)
    print("FIXING IMPORTED CUSTOMERS")
    print("="*60 + "\n")
    
    mongo_url = os.environ.get('MONGO_URL')
    client = AsyncIOMotorClient(mongo_url)
    db = client['whatsapp_crm']
    
    # Get all users
    users = await db.users.find({}).to_list(100)
    
    for user in users:
        user_id = user["_id"]
        print(f"\nProcessing user: {user.get('name', 'Unknown')}")
        
        # Find customers with no messages (imported, never engaged)
        customers = await db.customers.find({
            "user_id": user_id,
            "last_contacted": None
        }).to_list(10000)
        
        print(f"Found {len(customers)} customers with no contact history")
        
        updated_count = 0
        skipped_count = 0
        
        for customer in customers:
            customer_id = customer["_id"]
            
            # Check if customer has any messages
            message_count = await db.messages.count_documents({
                "customer_id": customer_id
            })
            
            if message_count > 0:
                # Has messages, skip (will be handled by conversation tracking)
                skipped_count += 1
                continue
            
            # No messages = imported contact
            # Set last_contacted to created_at so they don't appear as urgent
            created_at = customer.get("created_at", datetime.utcnow())
            
            await db.customers.update_one(
                {"_id": customer_id},
                {
                    "$set": {
                        "last_contacted": created_at,
                        "auto_created": False  # Mark as manually imported
                    }
                }
            )
            updated_count += 1
        
        print(f"✓ Updated {updated_count} imported customers")
        print(f"✓ Skipped {skipped_count} customers with messages")
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("\nWhat changed:")
    print("- Imported customers now have last_contacted = created_at")
    print("- They won't show as 'never contacted' anymore")
    print("- System will focus on customers with actual conversations")
    print("\nWhat this means:")
    print("- Customers who MESSAGE YOU will be prioritized")
    print("- Active conversations get highest urgency")
    print("- Old imports get lowest priority")
    print("\n" + "="*60 + "\n")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_imported_customers())

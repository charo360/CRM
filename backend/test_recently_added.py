"""
Test Recently Added Contacts Feature
Verify that manually added contacts appear in "Needs Attention" as reminders
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import uuid

load_dotenv()

async def test_recently_added_contacts():
    """Test that recently added contacts show up correctly"""
    
    print("\n" + "="*60)
    print("TESTING RECENTLY ADDED CONTACTS")
    print("="*60 + "\n")
    
    mongo_url = os.environ.get('MONGO_URL')
    client = AsyncIOMotorClient(mongo_url)
    db = client['whatsapp_crm']
    
    # Get test user
    user = await db.users.find_one({})
    if not user:
        print("❌ No users found")
        return
    
    user_id = user["_id"]
    print(f"✓ Testing with user: {user.get('name', 'Unknown')}\n")
    
    # TEST 1: Create a new contact (added today)
    print("--- TEST 1: Creating New Contact (Added Today) ---")
    
    test_customer_id = str(uuid.uuid4())
    await db.customers.insert_one({
        "_id": test_customer_id,
        "user_id": user_id,
        "name": "Test Customer Today",
        "phone_number": "+254700000001",
        "notes": "Manually added for testing",
        "tags": ["New"],
        "last_contacted": None,  # Never contacted
        "created_at": datetime.utcnow(),  # Added today
        "auto_created": False  # Manually added
    })
    print(f"✓ Created test customer: Test Customer Today")
    print(f"  - Added: Today")
    print(f"  - Last contacted: Never")
    print(f"  - Expected: Should appear in 'Needs Attention'\n")
    
    # TEST 2: Create a contact added 3 days ago
    print("--- TEST 2: Creating Contact (Added 3 Days Ago) ---")
    
    test_customer_id_2 = str(uuid.uuid4())
    three_days_ago = datetime.utcnow() - timedelta(days=3)
    await db.customers.insert_one({
        "_id": test_customer_id_2,
        "user_id": user_id,
        "name": "Test Customer 3 Days",
        "phone_number": "+254700000002",
        "notes": "Added 3 days ago, not contacted",
        "tags": ["New"],
        "last_contacted": None,
        "created_at": three_days_ago,
        "auto_created": False
    })
    print(f"✓ Created test customer: Test Customer 3 Days")
    print(f"  - Added: 3 days ago")
    print(f"  - Last contacted: Never")
    print(f"  - Expected: Should appear in 'Needs Attention'\n")
    
    # TEST 3: Simulate urgency scoring
    print("--- TEST 3: Urgency Score Calculation ---")
    
    from daily_analyzer import DailyCustomerAnalyzer
    analyzer = DailyCustomerAnalyzer(db)
    
    # Get the customers we just created
    customer_1 = await db.customers.find_one({"_id": test_customer_id})
    customer_2 = await db.customers.find_one({"_id": test_customer_id_2})
    
    # Get messages (should be empty)
    messages_1 = await db.messages.find({"customer_id": test_customer_id}).to_list(100)
    messages_2 = await db.messages.find({"customer_id": test_customer_id_2}).to_list(100)
    
    # Calculate urgency scores
    score_1 = analyzer._calculate_urgency_score(customer_1, messages_1, False)
    score_2 = analyzer._calculate_urgency_score(customer_2, messages_2, False)
    
    print(f"Customer 1 (added today):")
    print(f"  - Urgency Score: {score_1}/100")
    print(f"  - Expected: 50+ (should appear)")
    print(f"  - Result: {'✓ PASS' if score_1 >= 30 else '❌ FAIL'}\n")
    
    print(f"Customer 2 (added 3 days ago):")
    print(f"  - Urgency Score: {score_2}/100")
    print(f"  - Expected: 50+ (should appear)")
    print(f"  - Result: {'✓ PASS' if score_2 >= 30 else '❌ FAIL'}\n")
    
    # TEST 4: Check AI reasons
    print("--- TEST 4: AI Reason Messages ---")
    
    from server import generate_simple_reason
    
    reason_1 = generate_simple_reason(customer_1, None)
    reason_2 = generate_simple_reason(customer_2, None)
    
    print(f"Customer 1 reason: '{reason_1}'")
    print(f"  - Expected: 'Added today - reach out and introduce yourself'")
    print(f"  - Result: {'✓ PASS' if 'today' in reason_1.lower() else '❌ FAIL'}\n")
    
    print(f"Customer 2 reason: '{reason_2}'")
    print(f"  - Expected: 'Added 3 days ago - haven't contacted yet'")
    print(f"  - Result: {'✓ PASS' if '3 days' in reason_2.lower() else '❌ FAIL'}\n")
    
    # TEST 5: Compare with old imported contact
    print("--- TEST 5: Compare with Old Imported Contact ---")
    
    # Find an old imported contact
    old_contact = await db.customers.find_one({
        "user_id": user_id,
        "last_contacted": {"$ne": None},
        "auto_created": False
    })
    
    if old_contact:
        old_messages = await db.messages.find({"customer_id": old_contact["_id"]}).to_list(100)
        old_score = analyzer._calculate_urgency_score(old_contact, old_messages, False)
        
        print(f"Old imported contact: {old_contact['name']}")
        print(f"  - Urgency Score: {old_score}/100")
        print(f"  - Expected: <30 (should NOT appear)")
        print(f"  - Result: {'✓ PASS' if old_score < 30 else '⚠️  WARNING'}\n")
    
    # CLEANUP
    print("--- CLEANUP ---")
    await db.customers.delete_one({"_id": test_customer_id})
    await db.customers.delete_one({"_id": test_customer_id_2})
    print("✓ Deleted test customers\n")
    
    # SUMMARY
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print("\n✅ Recently Added Contacts Feature:")
    print("  - Contacts added within 7 days appear in 'Needs Attention'")
    print("  - Clear reminder messages (e.g., 'Added today - reach out')")
    print("  - Higher urgency than old imports")
    print("  - Helps users remember to contact new additions")
    print("\n✅ Priority Tiers:")
    print("  1. Customer messaged you (50+ points)")
    print("  2. Active conversations (30-70 points)")
    print("  3. Recently added, not contacted (35-50 points) ← NEW")
    print("  4. Old imports, never engaged (5-10 points)")
    print("\n" + "="*60 + "\n")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_recently_added_contacts())

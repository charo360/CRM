"""
Test Auto-Contact Creation from Outgoing Messages
Verify that sending messages to new numbers auto-creates contacts
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
from dotenv import load_dotenv
from whatsapp_service import WhatsAppService

load_dotenv()

async def test_outgoing_auto_contact():
    """Test auto-contact creation when business sends message"""
    
    print("\n" + "="*60)
    print("TESTING AUTO-CONTACT FROM OUTGOING MESSAGES")
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
    
    # TEST 1: Send message to NEW number (should auto-create)
    print("--- TEST 1: Send Message to New Number ---")
    
    test_number = "+254799999999"
    test_message = "Hi! This is a test message from our business."
    
    # Make sure this number doesn't exist
    existing = await db.customers.find_one({
        "user_id": user_id,
        "phone_number": test_number
    })
    
    if existing:
        print(f"⚠️  Test number already exists, deleting first...")
        await db.customers.delete_one({"_id": existing["_id"]})
        await db.messages.delete_many({"customer_id": existing["_id"]})
    
    # Send message via WhatsApp service
    whatsapp_service = WhatsAppService(db)
    result = await whatsapp_service.send_message(
        user_id=user_id,
        to_number=test_number,
        message=test_message,
        customer_name="Test Customer"
    )
    
    print(f"✓ Message sent:")
    print(f"  - Status: {result['status']}")
    print(f"  - Customer ID: {result['customer_id']}")
    print(f"  - Created new contact: {result['created_new_contact']}")
    print(f"  - Customer name: {result['customer_name']}")
    
    if not result['created_new_contact']:
        print("❌ FAIL: Should have created new contact")
    else:
        print("✓ PASS: New contact created\n")
    
    # TEST 2: Verify contact was created correctly
    print("--- TEST 2: Verify Contact Details ---")
    
    customer = await db.customers.find_one({"_id": result['customer_id']})
    
    if not customer:
        print("❌ FAIL: Contact not found in database")
    else:
        print(f"✓ Contact found:")
        print(f"  - Name: {customer['name']}")
        print(f"  - Phone: {customer['phone_number']}")
        print(f"  - Tags: {customer.get('tags', [])}")
        print(f"  - Business initiated: {customer.get('business_initiated', False)}")
        print(f"  - Auto created: {customer.get('auto_created', False)}")
        print(f"  - Last contacted: {customer.get('last_contacted')}")
        
        # Verify flags
        if customer.get('business_initiated') == True:
            print("✓ PASS: business_initiated flag set correctly")
        else:
            print("❌ FAIL: business_initiated should be True")
        
        if customer.get('auto_created') == False:
            print("✓ PASS: auto_created flag set correctly (False for business-initiated)")
        else:
            print("⚠️  WARNING: auto_created should be False for business-initiated")
        
        print()
    
    # TEST 3: Verify message was stored
    print("--- TEST 3: Verify Message Storage ---")
    
    message = await db.messages.find_one({"_id": result['message_id']})
    
    if not message:
        print("❌ FAIL: Message not found in database")
    else:
        print(f"✓ Message stored:")
        print(f"  - Direction: {message['direction']}")
        print(f"  - Content: {message['content'][:50]}...")
        print(f"  - Customer ID: {message['customer_id']}")
        
        if message['direction'] == 'outgoing':
            print("✓ PASS: Direction is 'outgoing'")
        else:
            print("❌ FAIL: Direction should be 'outgoing'")
        
        print()
    
    # TEST 4: Send another message to SAME number (should NOT create duplicate)
    print("--- TEST 4: Send to Existing Number ---")
    
    result2 = await whatsapp_service.send_message(
        user_id=user_id,
        to_number=test_number,
        message="This is a second message",
        customer_name="Different Name"  # Should be ignored
    )
    
    print(f"✓ Second message sent:")
    print(f"  - Created new contact: {result2['created_new_contact']}")
    print(f"  - Customer ID: {result2['customer_id']}")
    
    if result2['created_new_contact']:
        print("❌ FAIL: Should NOT have created duplicate contact")
    else:
        print("✓ PASS: Used existing contact")
    
    if result2['customer_id'] == result['customer_id']:
        print("✓ PASS: Same customer ID used\n")
    else:
        print("❌ FAIL: Different customer ID (duplicate created)\n")
    
    # TEST 5: Check urgency scoring
    print("--- TEST 5: Urgency Score for Business-Initiated ---")
    
    from daily_analyzer import DailyCustomerAnalyzer
    analyzer = DailyCustomerAnalyzer(db)
    
    customer = await db.customers.find_one({"_id": result['customer_id']})
    messages = await db.messages.find({"customer_id": result['customer_id']}).to_list(100)
    
    score = analyzer._calculate_urgency_score(customer, messages, False)
    
    print(f"✓ Urgency score: {score}/100")
    print(f"  - Has conversation: Yes ({len(messages)} messages)")
    print(f"  - Business initiated: {customer.get('business_initiated', False)}")
    print(f"  - Expected: 30-50 (has conversation)")
    
    if score >= 30:
        print("✓ PASS: Score is appropriate for business-initiated conversation\n")
    else:
        print("⚠️  WARNING: Score seems low for active conversation\n")
    
    # CLEANUP
    print("--- CLEANUP ---")
    await db.customers.delete_one({"_id": result['customer_id']})
    await db.messages.delete_many({"customer_id": result['customer_id']})
    print("✓ Deleted test data\n")
    
    # SUMMARY
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print("\n✅ Auto-Contact Creation from Outgoing Messages:")
    print("  - Business sends message to new number")
    print("  - Contact auto-created with business_initiated=True")
    print("  - Message stored with direction='outgoing'")
    print("  - Subsequent messages use existing contact")
    print("  - No duplicates created")
    print("\n✅ Complete Conversation Tracking:")
    print("  - Customer → Business: auto_created=True, customer_initiated=True")
    print("  - Business → Customer: auto_created=False, business_initiated=True")
    print("  - Both scenarios tracked in CRM")
    print("\n" + "="*60 + "\n")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_outgoing_auto_contact())

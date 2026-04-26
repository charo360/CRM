
import asyncio
import os
import sys

# Ensure backend dir is in path
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from ai_message_drafter import get_drafter

async def test_drafter():
    print("Initializing drafter...")
    drafter = get_drafter()
    
    # Dummy data
    customer_name = "Test User"
    customer_data = {
        "tags": ["VIP"], 
        "purchase_count": 5, 
        "total_spent": 5000,
        "last_contacted": None
    }
    messages = [
        {"direction": "outgoing", "content": "Hi, how can we help?"},
        {"direction": "incoming", "content": "How much does the premium service cost?"}
    ]
    business_name = "Test Biz"
    
    print("Calling draft_followup_message...")
    try:
        result = await drafter.draft_followup_message(
            customer_name, 
            customer_data, 
            messages, 
            business_name
        )
        print("\nSUCCESS! Result:")
        print(f"Message: {result.get('drafted_message')}")
        print(f"Reason: {result.get('ai_reason')}")
        print(f"Confidence: {result.get('confidence')}")
    except Exception as e:
        print(f"\nFAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_drafter())

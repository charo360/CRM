"""
Quick verification that AI is working correctly
"""
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env
load_dotenv(Path('.env'), override=True)

from ai_service import get_drafter

async def verify():
    print("=== AI Service Verification ===\n")
    
    drafter = get_drafter()
    
    print(f"✓ API Key loaded (ends with: {drafter.api_key[-10:]})")
    print(f"✓ Mock mode: {drafter.mock_mode}")
    print(f"✓ Client initialized: {drafter.client is not None}\n")
    
    if drafter.mock_mode:
        print("✗ ERROR: AI is in mock mode - API key not configured properly")
        sys.exit(1)
    
    # Test actual message generation
    print("Testing message generation...")
    result = await drafter.draft_followup_message(
        customer_name='Test Customer',
        customer_data={
            'last_contacted': None,
            'tags': ['New'],
            'purchase_count': 0,
            'total_spent': 0,
            'notes': 'Interested in products'
        },
        messages=[
            {'content': 'Hi, what are your prices?', 'direction': 'incoming'}
        ],
        business_name='Your Business'
    )
    
    if result['confidence'] > 0.5 and 'just checking in' not in result['drafted_message'].lower():
        print(f"✓ AI Generated Message: {result['drafted_message'][:100]}...")
        print(f"✓ Confidence: {result['confidence']}")
        print(f"✓ Reason: {result['ai_reason']}\n")
        print("=== ✓ AI SERVICE IS WORKING CORRECTLY ===")
    else:
        print(f"✗ ERROR: Still getting fallback message")
        print(f"Message: {result['drafted_message']}")
        print(f"Reason: {result['ai_reason']}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify())

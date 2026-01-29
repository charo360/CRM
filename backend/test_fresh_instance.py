import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Force reload env
load_dotenv(Path('.env'), override=True)

# Import AFTER loading env
from ai_service import AIMessageDrafter

async def test():
    # Create fresh instance (not singleton)
    drafter = AIMessageDrafter()
    
    print(f"Mock mode: {drafter.mock_mode}")
    print(f"Has client: {drafter.client is not None}")
    print(f"API key ends with: {drafter.api_key[-10:] if drafter.api_key else 'None'}")
    
    result = await drafter.draft_followup_message(
        customer_name='John Doe',
        customer_data={
            'last_contacted': None,
            'tags': ['New'],
            'purchase_count': 0,
            'total_spent': 0,
            'notes': 'Interested in our products'
        },
        messages=[
            {'content': 'Hi, how much is the product?', 'direction': 'incoming'}
        ],
        business_name='Test Shop'
    )
    
    print("\n=== RESULT ===")
    print(f"Message: {result['drafted_message']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Reason: {result['ai_reason']}")

asyncio.run(test())

import os
import sys

# Clear any cached environment
if 'OPENAI_API_KEY' in os.environ:
    del os.environ['OPENAI_API_KEY']

# Now load from .env with override
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env'), override=True)

print(f"Loaded key ends with: {os.environ.get('OPENAI_API_KEY', 'NOT SET')[-10:]}")

# Now test
import asyncio
from ai_service import AIMessageDrafter

async def test():
    # Create fresh instance
    drafter = AIMessageDrafter()
    
    print(f"Drafter key ends with: {drafter.api_key[-10:]}")
    print(f"Mock mode: {drafter.mock_mode}")
    
    result = await drafter.draft_followup_message(
        customer_name='Philo Ngerenya',
        customer_data={
            'last_contacted': None,
            'tags': [],
            'purchase_count': 0,
            'total_spent': 0,
            'notes': ''
        },
        messages=[],
        business_name='Test Business'
    )
    
    print(f"\nDrafted Message: {result['drafted_message']}")
    print(f"Confidence: {result['confidence']}")

asyncio.run(test())

import asyncio
from ai_service import get_drafter

async def test():
    drafter = get_drafter()
    print(f"API key ends with: {drafter.api_key[-10:]}")
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
    print(f"Reason: {result['ai_reason']}")

asyncio.run(test())

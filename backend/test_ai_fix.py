import asyncio
from ai_service import get_drafter

async def test():
    drafter = get_drafter()
    print(f"Mock mode: {drafter.mock_mode}")
    print(f"Has client: {drafter.client is not None}")
    print(f"API key set: {bool(drafter.api_key)}")
    
    result = await drafter.draft_followup_message(
        customer_name='Test Customer',
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
    
    print("\nResult:")
    print(result)

asyncio.run(test())

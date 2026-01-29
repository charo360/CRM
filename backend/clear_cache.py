import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

async def clear_old_analysis():
    mongo_url = os.environ.get('MONGO_URL')
    client = AsyncIOMotorClient(mongo_url)
    db = client['whatsapp_crm']
    
    # Delete ALL customer_analysis to force fresh generation
    result = await db.customer_analysis.delete_many({})
    print(f'Deleted {result.deleted_count} analysis records')
    
    client.close()

asyncio.run(clear_old_analysis())

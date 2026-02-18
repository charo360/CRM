import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

async def check_product_urls():
    """Check what URLs are stored for products"""
    mongodb_uri = os.getenv('MONGODB_URI')
    if not mongodb_uri:
        print("ERROR: MONGODB_URI not found in .env")
        return
    
    client = AsyncIOMotorClient(mongodb_uri)
    db = client.crm
    
    products = await db.products.find({}).to_list(10)
    print(f"Found {len(products)} products")
    for p in products:
        pid = str(p.get('_id', ''))
        name = p.get('name', 'NO NAME')
        image_url = p.get('image_url', 'NO image_url')
        images = p.get('images', [])
        print(f"\nProduct: {name}")
        print(f"  ID: {pid}")
        print(f"  image_url: {image_url}")
        print(f"  images: {images}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_product_urls())

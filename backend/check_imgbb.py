import os
import base64
import requests
import asyncio
from dotenv import load_dotenv
from pathlib import Path

# Load env variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

async def test_imgbb():
    print("Testing ImgBB Upload...")
    
    api_key = os.environ.get('IMGBB_API_KEY')
    print(f"API Key present: {bool(api_key)}")
    
    if not api_key:
        print("❌ Error: IMGBB_API_KEY not found in .env")
        return

    # Create a tiny test image (base64)
    # This is a 1x1 black pixel
    base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    
    try:
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": api_key,
            "image": base64_data,
            "name": "test_upload_verify"
        }
        
        print("Sending request to ImgBB...")
        response = requests.post(url, data=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Upload Successful!")
            print(f"URL: {data['data']['url']}")
            print(f"Viewer URL: {data['data']['url_viewer']}")
            print(f"Delete URL: {data['data']['delete_url']}")
        else:
            print(f"\n❌ Upload Failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"\n❌ Validaton Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_imgbb())

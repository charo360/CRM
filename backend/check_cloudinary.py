import os
import sys
from dotenv import load_dotenv
from pathlib import Path

# Load env
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

print(f"Cloudinary Configuration Check:")
cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', '').strip()
api_key = os.environ.get('CLOUDINARY_API_KEY', '').strip()
api_secret = os.environ.get('CLOUDINARY_API_SECRET', '').strip()

print(f"Cloud Name: {cloud_name}")
print(f"API Key: {api_key[:4]}...{api_key[-4:] if api_key else 'None'}")
print(f"API Secret: {'*' * 10 if api_secret else 'None'}")

if not all([cloud_name, api_key, api_secret]):
    print("❌ Error: Missing Cloudinary configuration.")
    sys.exit(1)

try:
    import cloudinary
    import cloudinary.uploader
    import uuid
    
    print("\nCloudinary library imported successfully.")
    
    # Configure 
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )
    
    print("\nTest: SDK Upload with Data URI formatting...")
    
    # Simulate the input from valid app usage (Data URI string)
    # The fix ensures that even if raw base64 comes in, it gets prefixed. 
    # But here we will test the final string that gets passed to the SDK.
    
    raw_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    
    # Mimic the fix logic from image_handler.py:
    if not raw_base64.startswith('data:'):
        raw_base64 = f"data:image/png;base64,{raw_base64}"
        print("✅ Correctly applied Data URI prefix logic.")

    public_id = f"test_verify_{uuid.uuid4().hex}"
    
    response = cloudinary.uploader.upload(
        raw_base64
    )
    
    print(f"\n✅ Upload Successful!")
    print(f"Public ID: {response.get('public_id')}")
    print(f"URL: {response.get('secure_url')}")
    
except ImportError:
    print("\n❌ Error: 'cloudinary' library not installed.")
except Exception as e:
    import traceback
    error_msg = f"\n❌ Upload Failed: {str(e)}\nFull error details:\n{traceback.format_exc()}"
    print(error_msg)
    with open("error_log.txt", "w", encoding="utf-8") as f:
        f.write(error_msg)

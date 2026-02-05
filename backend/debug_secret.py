import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

secret = os.environ.get('CLOUDINARY_API_SECRET', '')
print(f"Secret length: {len(secret)}")
print(f"Secret repr: {repr(secret)}")

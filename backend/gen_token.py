
import sys
import os
import datetime
import jwt
# Add current directory to path
sys.path.append(os.getcwd())

# Mock environment
os.environ['JWT_SECRET'] = 'dev_secret_key'
os.environ['JWT_ALGORITHM'] = 'HS256'

from datetime import datetime, timedelta

def create_token(user_id: str, phone_number: str) -> str:
    payload = {
        "user_id": user_id,
        "phone_number": phone_number,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, 'dev_secret_key', algorithm='HS256')

# Generate token for a dummy user needed
# I need a valid user_id if the code checks DB.
# get_current_user checks DB.
# So I need to insert a user or use an existing one.
# Connecting to DB in script might be hard if using async motor.

# Alternative: Login via API?
# /auth/send-otp -> /auth/verify-otp
# But verify-otp needs DB too.

print("Token generation requires DB access logic or bypassing.")

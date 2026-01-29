"""
Environment validation script - Run this on startup to catch API key issues early
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def validate_environment():
    """Validate that environment is configured correctly"""
    
    # Load .env file with override
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path, override=True)
    
    errors = []
    warnings = []
    
    # Check OpenAI API Key
    api_key = os.environ.get('OPENAI_API_KEY', '')
    
    if not api_key:
        errors.append("OPENAI_API_KEY is not set in .env file")
    elif api_key == 'your_openai_api_key_here':
        errors.append("OPENAI_API_KEY is still set to placeholder value")
    elif not api_key.startswith('sk-'):
        errors.append(f"OPENAI_API_KEY has invalid format (should start with 'sk-')")
    elif len(api_key) < 40:
        errors.append(f"OPENAI_API_KEY seems too short (length: {len(api_key)})")
    else:
        # Validate with OpenAI
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            # Quick test call
            client.models.list()
            print(f"✓ OpenAI API Key valid (ends with: ...{api_key[-10:]})")
        except Exception as e:
            error_msg = str(e)
            if '401' in error_msg or 'invalid' in error_msg.lower():
                errors.append(f"OPENAI_API_KEY is invalid or expired: {error_msg[:100]}")
            else:
                warnings.append(f"Could not verify OpenAI API Key: {error_msg[:100]}")
    
    # Check other required env vars
    required_vars = ['MONGO_URL', 'JWT_SECRET', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN']
    for var in required_vars:
        if not os.environ.get(var):
            warnings.append(f"{var} is not set")
    
    # Print results
    print("\n=== Environment Validation ===")
    
    if errors:
        print("\n❌ ERRORS:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease fix these errors before starting the server.")
        return False
    
    if warnings:
        print("\n⚠️  WARNINGS:")
        for warning in warnings:
            print(f"  - {warning}")
    
    if not errors and not warnings:
        print("\n✓ All environment variables configured correctly")
    
    print("\n" + "="*40 + "\n")
    return True

if __name__ == "__main__":
    if not validate_environment():
        sys.exit(1)

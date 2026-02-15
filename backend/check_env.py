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
    
    # Check AI Provider and API Key
    ai_provider = os.environ.get('AI_PROVIDER', 'openai').strip().lower()
    
    if ai_provider == 'deepseek':
        api_key = os.environ.get('DEEPSEEK_API_KEY', '')
        key_name = 'DEEPSEEK_API_KEY'
        provider_label = 'DeepSeek'
        base_url = 'https://api.deepseek.com'
    else:
        api_key = os.environ.get('OPENAI_API_KEY', '')
        key_name = 'OPENAI_API_KEY'
        provider_label = 'OpenAI'
        base_url = None
    
    if not api_key:
        errors.append(f"{key_name} is not set in .env file")
    elif api_key in ('your_openai_api_key_here', 'your_deepseek_api_key_here'):
        errors.append(f"{key_name} is still set to placeholder value")
    elif ai_provider != 'deepseek' and not api_key.startswith('sk-'):
        errors.append(f"{key_name} has invalid format (should start with 'sk-')")
    elif len(api_key) < 20:
        errors.append(f"{key_name} seems too short (length: {len(api_key)})")
    else:
        # Validate with a quick API call
        try:
            from openai import OpenAI
            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
            client.chat.completions.create(
                model='deepseek-chat' if ai_provider == 'deepseek' else 'gpt-4o-mini',
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5
            )
            print(f"✓ {provider_label} API Key valid (ends with: ...{api_key[-10:]})")
        except Exception as e:
            error_msg = str(e)
            if '401' in error_msg or 'invalid' in error_msg.lower() or 'auth' in error_msg.lower():
                errors.append(f"{key_name} is invalid or expired: {error_msg[:100]}")
            else:
                warnings.append(f"Could not verify {provider_label} API Key: {error_msg[:100]}")
    
    # Check other required env vars
    required_vars = ['MONGO_URL', 'JWT_SECRET', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN']
    for var in required_vars:
        if not os.environ.get(var):
            warnings.append(f"{var} is not set")

    # Check AWS Credentials
    if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
        warnings.append("AWS Credentials not set - Image uploads will fallback to ImgBB (unreliable)")
    elif not os.environ.get('AWS_BUCKET_NAME'):
        warnings.append("AWS_BUCKET_NAME not set - S3 uploads will fail")
    
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

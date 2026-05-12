# Environment Setup Guide

## API Key Configuration

### Important: Avoiding API Key Issues

The application uses OpenAI API for AI-powered message drafting. To prevent configuration issues:

1. **Always use the `.env` file** - Never set `OPENAI_API_KEY` as a system environment variable
2. **The `.env` file takes precedence** - The server is configured with `override=True` to use `.env` values
3. **Validation on startup** - The server validates the API key on startup and will fail fast if misconfigured

### Setup Steps

1. Copy `.env.example` to `.env` (if not already done)
2. Edit `.env` and set your OpenAI API key:
   ```
   OPENAI_API_KEY=sk-proj-your_actual_key_here
   ```
3. Ensure the key:
   - Starts with `sk-` or `sk-proj-`
   - Is at least 40 characters long
   - Is valid (not expired or revoked)

### Validation

Before starting the server, you can validate your environment:

```bash
python check_env.py
```

This will check:
- ✓ OpenAI API key is set and valid
- ✓ All required environment variables are present
- ✓ API key can successfully connect to OpenAI

### Troubleshooting

**Issue: Getting fallback messages like "Hi {name}, just checking in!"**

This means the AI service is not working. Check:

1. Run `python check_env.py` to validate your API key
2. Check server logs for errors starting with `❌`
3. Ensure no system environment variable is overriding `.env`:
   ```powershell
   # Check if system env var exists
   $env:OPENAI_API_KEY
   
   # If it exists and is wrong, remove it:
   Remove-Item Env:\OPENAI_API_KEY
   [System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $null, 'User')
   ```
4. Restart the server completely (kill all Python processes)

**Issue: Server won't start**

If you see:
```
❌ ERROR: OPENAI_API_KEY not configured in .env file
```

The server will not start until you fix the API key in `.env`.

### Server Startup Logs

When the server starts correctly, you should see:
```
✓ OpenAI API Key loaded (ends with: ...yourkey)
✓ OpenAI client initialized successfully (key ends: ...yourkey)
```

If you see warnings or errors, fix them before proceeding.

## Other Environment Variables

Required:
- `MONGO_URL` - MongoDB connection string
- `JWT_SECRET` - Secret for JWT token generation
- `TWILIO_ACCOUNT_SID` - Twilio account SID
- `TWILIO_AUTH_TOKEN` - Twilio auth token
- `TWILIO_PHONE_NUMBER` - Your Twilio WhatsApp number

Optional:
- `DB_NAME` - Database name (default: whatsapp_crm)
- `PORT` - Server port (default: 8000)

## Autoblogging (WordPress Multisite) Variables

Add these to your `.env` when the Hostinger VPS + WordPress Multisite is set up:

```dotenv
# WordPress Multisite (Hostinger VPS)
WP_BASE_URL=https://zilo.pro
WP_ADMIN_USER=ziloadmin
WP_ADMIN_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
WP_JWT_SECRET=your-very-long-random-secret-key-here-change-this
```

- `WP_BASE_URL` — Root URL of your WordPress Multisite install (no trailing slash)
- `WP_ADMIN_USER` — WordPress network admin username
- `WP_ADMIN_APP_PASSWORD` — Application password created under Users → Profile → Application Passwords
- `WP_JWT_SECRET` — Must match `JWT_AUTH_SECRET_KEY` defined in `wp-config.php`

The autoblogging scheduler publishes one post per active client daily at **9 AM EAT**.
Weekly post limits per plan: `free=2`, `starter=5`, `growth=7`, `premium=7`.

## Quick Start

```bash
# 1. Validate environment
python check_env.py

# 2. Start server
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

## Changes Made to Prevent Issues

1. **`server.py`** - Added `override=True` to `load_dotenv()` so `.env` always takes precedence
2. **`server.py`** - Added startup validation that fails fast if API key is missing
3. **`ai_service.py`** - Enhanced logging to show which API key is being used
4. **`ai_service.py`** - Singleton recreates when API key changes
5. **`ai_service.py`** - Fixed async/sync issues with OpenAI API calls using `asyncio.to_thread()`

# Composio Webhooks Setup Guide

## Overview

This guide explains how to set up **real-time Gmail notifications** using Composio's webhook system. Unlike the Google Cloud Pub/Sub approach, this works directly with Composio-managed Gmail connections.

## How It Works

1. **Webhook Subscription**: Register your webhook URL with Composio (one-time per project)
2. **Trigger Registration**: Create `GMAIL_NEW_GMAIL_MESSAGE` triggers for each user with Gmail connected
3. **Real-Time Events**: When a new email arrives, Composio sends a webhook to your backend
4. **Auto-Sync**: Your backend fetches and stores the email in MongoDB within seconds

## Prerequisites

- ✅ Gmail connected via Composio (already done)
- ✅ Backend running with public HTTPS URL
- ⚠️ For local testing: Install [ngrok](https://ngrok.com) to expose localhost

## Setup Steps

### Step 1: Get Your Webhook URL

**For Production:**
```
https://your-domain.com/api/webhooks/composio
```

**For Local Testing with ngrok:**
```bash
# Install ngrok: https://ngrok.com/download
# Start ngrok tunnel
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# Your webhook URL will be: https://abc123.ngrok.io/api/webhooks/composio
```

### Step 2: Add Webhook URL to Environment

Edit `backend/.env`:
```bash
# Add this line with your actual webhook URL
COMPOSIO_WEBHOOK_URL=https://your-domain.com/api/webhooks/composio

# Or for ngrok:
COMPOSIO_WEBHOOK_URL=https://abc123.ngrok.io/api/webhooks/composio
```

### Step 3: Run Setup Script

```bash
cd backend
python setup_composio_webhooks.py
```

This script will:
1. Create a webhook subscription in Composio
2. Register Gmail triggers for all connected users
3. Output a webhook secret

**Expected Output:**
```
📡 Setting up Composio webhook subscription...

✅ Webhook subscription created!
   URL: https://your-domain.com/api/webhooks/composio
   Secret: wh_sec_abc123xyz...

   ⚠️  IMPORTANT: Add this to your .env file:
   COMPOSIO_WEBHOOK_SECRET=wh_sec_abc123xyz...

📧 Registering Gmail triggers for connected users...

✅ newlife101au@gmail.com - Connected (ID: conn_abc123)
✅ evans@paya.co.ke - Connected (ID: conn_xyz789)

📧 Found 2 user(s) with Gmail connected
============================================================

📧 Registering trigger for newlife101au@gmail.com...
   ✅ Trigger registered successfully

📧 Registering trigger for evans@paya.co.ke...
   ✅ Trigger registered successfully

✅ Done!
```

### Step 4: Add Webhook Secret to .env

Copy the secret from the output and add to `backend/.env`:
```bash
COMPOSIO_WEBHOOK_SECRET=wh_sec_abc123xyz...
```

### Step 5: Restart Backend

```bash
# Stop current backend (Ctrl+C)
# Restart:
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

## Testing

### 1. Send Test Email

Send an email to one of your connected Gmail accounts.

### 2. Check Backend Logs

You should see:
```
[composio-webhook] Received: GMAIL_NEW_GMAIL_MESSAGE
📧 Gmail trigger: sender@example.com - Test Subject
✅ Stored 1 message(s) for newlife101au@gmail.com
```

### 3. Verify in CRM

- Go to your CRM email inbox
- The new email should appear within 5-10 seconds
- No need to click "Sync"!

## Troubleshooting

### Webhook Not Receiving Events

**Check webhook URL is accessible:**
```bash
curl -X POST https://your-domain.com/api/webhooks/composio \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

Should return: `{"status": "ok"}` or similar

**For ngrok users:**
- Make sure ngrok is still running
- ngrok URLs expire when you restart ngrok
- Update `COMPOSIO_WEBHOOK_URL` if URL changes

### Invalid Signature Error

- Make sure `COMPOSIO_WEBHOOK_SECRET` is set correctly in `.env`
- Restart backend after adding the secret

### User Not Found Error

- Run the setup script again to update user documents with `connected_account_id`
- Check that Gmail is still connected in Composio

### Trigger Not Firing

**Check trigger status in Composio dashboard:**
1. Go to https://app.composio.dev
2. Navigate to Triggers section
3. Verify `GMAIL_NEW_GMAIL_MESSAGE` triggers are active

**Re-register triggers:**
```bash
python setup_composio_webhooks.py
```

## Managing Triggers

### Register Trigger for New User

When a new user connects Gmail, automatically register their trigger:

```python
# In your Gmail connection success handler
from setup_composio_webhooks import register_gmail_trigger_for_user

await register_gmail_trigger_for_user(user_id, connected_account_id, db)
```

### Delete Webhook Subscription

```bash
curl -X DELETE "https://backend.composio.dev/api/v3.1/webhook_subscriptions" \
  -H "X-API-Key: YOUR_COMPOSIO_API_KEY"
```

Then run setup script again to recreate.

## Architecture

```
Gmail → Composio → Your Webhook → MongoDB
  ↓         ↓           ↓            ↓
New      Detects    Receives    Stores
Email    Event      Webhook     Email
```

**Flow:**
1. User receives email in Gmail
2. Composio detects new email via Gmail API
3. Composio sends webhook to your backend
4. Backend fetches full email via Composio API
5. Email stored in MongoDB
6. Email classified by AI
7. Appears in CRM instantly

## Benefits Over Polling

| Feature | Polling (10 min) | Webhooks (Real-time) |
|---------|------------------|----------------------|
| Latency | 0-10 minutes | 5-10 seconds |
| API Calls | Every 10 min per user | Only when email arrives |
| Server Load | Constant | Event-driven |
| Scalability | Limited | Excellent |

## Next Steps

- ✅ Gmail webhooks working
- 🔄 Add Outlook webhooks (similar process)
- 🔄 Add Slack message webhooks
- 🔄 Add Calendar event webhooks

## Support

- Composio Docs: https://docs.composio.dev/docs/using-triggers
- Composio Dashboard: https://app.composio.dev
- ngrok Docs: https://ngrok.com/docs

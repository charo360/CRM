# Twilio WhatsApp Integration Setup Guide

## Step 1: Create a Twilio Account

1. Go to [https://www.twilio.com/try-twilio](https://www.twilio.com/try-twilio)
2. Sign up for a free account
3. Verify your email and phone number
4. You'll get **$15 in free trial credits**

## Step 2: Get Your Twilio Credentials

After signing up, you'll be on the Twilio Console dashboard:

1. **Account SID**: Found on the main dashboard (looks like: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
2. **Auth Token**: Click "Show" next to Auth Token on the dashboard
3. Copy both of these - you'll need them for your `.env` file

## Step 3: Set Up WhatsApp Sandbox (For Testing)

Twilio provides a WhatsApp Sandbox for testing before you get approved for a production number.

1. In Twilio Console, go to **Messaging** → **Try it out** → **Send a WhatsApp message**
2. You'll see a sandbox number (like `+1 415 523 8886`)
3. **Join the sandbox**:
   - Send a WhatsApp message to the sandbox number
   - Use the join code shown (e.g., "join <your-code>")
   - You'll receive a confirmation message

4. **Get your Sandbox WhatsApp number**:
   - This is the number you'll use as `TWILIO_PHONE_NUMBER`
   - Format: `+14155238886` (without spaces)

## Step 4: Configure Webhook for Incoming Messages

Your backend needs to receive incoming WhatsApp messages. We'll set this up after your server is accessible.

### Option A: Local Development (Using ngrok)

1. **Install ngrok**: [https://ngrok.com/download](https://ngrok.com/download)
2. **Start your backend server** (on port 8000)
3. **Run ngrok**:
   ```bash
   ngrok http 8000
   ```
4. **Copy the HTTPS URL** (e.g., `https://abc123.ngrok.io`)
5. **Configure in Twilio**:
   - Go to **Messaging** → **Settings** → **WhatsApp sandbox settings**
   - Set "WHEN A MESSAGE COMES IN" to: `https://abc123.ngrok.io/api/webhooks/whatsapp`
   - Method: `POST`
   - Click **Save**

### Option B: Production (Using deployed server)

1. Deploy your backend to a server (e.g., Railway, Heroku, DigitalOcean)
2. Use your production URL: `https://yourdomain.com/api/webhooks/whatsapp`
3. Configure in Twilio WhatsApp sandbox settings

## Step 5: Update Your .env File

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+14155238886
```

Replace with your actual values from Steps 2 and 3.

## Step 6: Test the Integration

### Test Sending Messages (From Your App)

1. Open your CRM app
2. Go to a customer's detail page
3. Click "Send Message" or use the AI draft feature
4. The message should be sent via WhatsApp to the customer

### Test Receiving Messages (To Your App)

1. Send a WhatsApp message to your Twilio sandbox number
2. The message should:
   - Appear in your CRM
   - Auto-create a customer if it's a new number
   - Be stored for AI analysis

## Step 7: Production WhatsApp Number (Optional)

For production use, you need an approved WhatsApp Business number:

1. Go to **Messaging** → **Senders** → **WhatsApp senders**
2. Click **Request to enable my Twilio numbers for WhatsApp**
3. Fill out the form with your business details
4. Wait for approval (usually 1-3 business days)
5. Once approved, update `TWILIO_PHONE_NUMBER` with your approved number

## Troubleshooting

### Messages not sending?
- Check your Twilio credentials in `.env`
- Verify you have trial credits remaining
- Check backend logs for errors

### Not receiving messages?
- Verify webhook URL is correct in Twilio Console
- Check that your server is accessible (ngrok running if local)
- Look at Twilio's webhook logs in the Console

### "Unverified number" error?
- In trial mode, you can only send to verified numbers
- Verify numbers in Twilio Console: **Phone Numbers** → **Verified Caller IDs**
- Or upgrade to a paid account to send to any number

## Cost Information

- **Trial**: $15 free credit
- **WhatsApp messages**: ~$0.005 per message (very cheap!)
- **Monthly phone number**: ~$1/month
- **No monthly fees** for pay-as-you-go accounts

## Next Steps

1. Create your Twilio account
2. Get your credentials
3. Join the WhatsApp sandbox
4. Update your `.env` file
5. Test sending and receiving messages

Let me know when you have your Twilio credentials ready!

# Twilio WhatsApp Webhook Configuration

## Your ngrok URL
```
https://grisel-pyloric-semiprovincially.ngrok-free.dev
```

## Configure Twilio Webhook - Step by Step

### 1. Go to Twilio Console
Open: [https://console.twilio.com/](https://console.twilio.com/)

### 2. Navigate to WhatsApp Sandbox Settings
- Click **Messaging** in the left sidebar
- Click **Try it out**
- Click **Send a WhatsApp message**
- Scroll down to **Sandbox Configuration**

### 3. Configure the Webhook URL

In the "WHEN A MESSAGE COMES IN" field, enter:
```
https://grisel-pyloric-semiprovincially.ngrok-free.dev/api/webhooks/whatsapp
```

**Important Settings:**
- **HTTP Method**: `POST`
- **Content Type**: `application/x-www-form-urlencoded` (default)

### 4. Save Configuration
Click the **Save** button at the bottom

## Test Your Integration

### Test 1: Send a WhatsApp Message to Your CRM

1. Open WhatsApp on your phone
2. Send a message to: `+1 866 834 4424`
3. Type any message (e.g., "Hello, I'm interested in your products")

**What should happen:**
- The message appears in your CRM
- A new customer is auto-created with the sender's phone number
- The message is stored for AI analysis

### Test 2: Send a WhatsApp Message from Your CRM

1. Open your CRM app
2. Go to a customer's detail page
3. Use the AI draft feature or type a message
4. Click "Send"

**What should happen:**
- The customer receives the message on WhatsApp
- The message is logged in your CRM
- Customer's `last_contacted` is updated

## Troubleshooting

### Messages not being received in CRM?
1. Check ngrok is still running: `http://127.0.0.1:4040` (ngrok dashboard)
2. Verify webhook URL in Twilio is correct
3. Check backend server logs for errors
4. Verify you joined the sandbox (send join code to sandbox number)

### Can't send messages?
1. Check `.env` file has correct credentials
2. Restart backend server after updating `.env`
3. Check Twilio account has credits
4. Verify recipient joined the sandbox (for testing)

### "Unverified number" error?
- In sandbox mode, recipients must join the sandbox first
- Send them the join code: `join <your-code>`
- Or verify their number in Twilio Console

## Next Steps After Testing

Once everything works:
1. Apply for a WhatsApp Business number (production)
2. Update `TWILIO_PHONE_NUMBER` in `.env` with approved number
3. Update webhook URL to use your production domain (not ngrok)
4. Remove sandbox join requirement

## Important Notes

- **ngrok URL changes** every time you restart ngrok (free plan)
- For production, use a permanent domain or ngrok paid plan
- Keep ngrok running while testing
- Backend server must be running on port 8000

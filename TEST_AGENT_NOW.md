# Test Gmail Filter Agent NOW

## ✅ Setup Complete!

The Gmail filter agent is now integrated into your assistant. You can test it immediately!

## 🚀 How to Test

### Option 1: Through Your CRM Assistant (Recommended)

1. **Start your backend** (if not already running):
   ```bash
   cd backend
   python server.py
   ```

2. **Open your CRM assistant** (wherever you chat with it)

3. **Try these commands**:

   ```
   "Set up newsletter filters"
   ```
   ✅ Should create 9 filters for common newsletters

   ```
   "Archive all emails from test@example.com"
   ```
   ✅ Should create a single archive filter

   ```
   "Show me filter suggestions"
   ```
   ✅ Should analyze your inbox and suggest filters

   ```
   "List all my filters"
   ```
   ✅ Should show all active filters

   ```
   "Mark emails from boss@company.com as important"
   ```
   ✅ Should create an important filter

### Option 2: Direct API Test

Test the tool directly via API:

```bash
# Replace YOUR_USER_ID with your actual user ID
curl -X POST http://localhost:8000/api/assistant/tool \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID",
    "tool_name": "manage_gmail_filters",
    "args": {
      "command": "Set up newsletter filters"
    }
  }'
```

### Option 3: Python Test Script

Create a file `test_filter_agent.py`:

```python
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test_agent():
    # Connect to MongoDB
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.crm_db
    
    # Import the agent
    from agents.gmail_filter_agent import gmail_filter_agent_tool
    
    # Test commands
    commands = [
        "Set up newsletter filters",
        "Show me filter suggestions",
        "List all my filters",
    ]
    
    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"Testing: {cmd}")
        print('='*60)
        
        result = await gmail_filter_agent_tool(
            user_id="YOUR_USER_ID",  # Replace with your user ID
            db=db,
            command=cmd
        )
        
        print(f"Result: {result}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_agent())
```

Then run:
```bash
cd backend
python test_filter_agent.py
```

## 📋 Expected Results

### "Set up newsletter filters"
```json
{
  "success": true,
  "message": "✓ Newsletter filter setup complete!\n  • Created 9 filters\n  • Failed: 0\n\nThese senders will now be auto-archived:\n  • customerservice@exct.stansberryresearch.com\n  • info@exct.chaikinanalytics.com\n  ...",
  "created": 9,
  "failed": 0
}
```

### "Archive all emails from test@example.com"
```json
{
  "success": true,
  "message": "✓ Created filter to archive emails from test@example.com",
  "filter_id": "ANe1BmhK..."
}
```

### "Show me filter suggestions"
```json
{
  "success": true,
  "message": "📊 Found 3 filter suggestions:\n\n1. **promo@store.com**\n   • 15 emails (13% read rate)\n   • High volume sender\n   • Suggested: Archive automatically\n...",
  "suggestions": [...]
}
```

### "List all my filters"
```json
{
  "success": true,
  "message": "📋 Your active filters (9):\n\n1. Archive emails from: customerservice@exct.stansberryresearch.com\n2. Archive emails from: info@exct.chaikinanalytics.com\n...",
  "filters": [...],
  "count": 9
}
```

## ⚠️ Prerequisites

Before testing, ensure:

1. **Composio API Key is valid**
   - Check `backend/.env` has `COMPOSIO_API_KEY=...`
   - If expired, renew at https://app.composio.dev

2. **Gmail is connected**
   - Visit `/dashboard/integrations`
   - Click "Connect Gmail"
   - Complete OAuth flow

3. **Backend is running**
   - `cd backend && python server.py`
   - Should see: `[gmail-filters] routes mounted at /api/gmail/filters/*`

## 🔍 Verify in Gmail

After creating filters:

1. Go to Gmail → Settings (gear icon) → See all settings
2. Click "Filters and Blocked Addresses"
3. You should see all your new filters listed!
4. Send a test email from a filtered address
5. It should skip your inbox (archived)

## 🐛 Troubleshooting

### "COMPOSIO_API_KEY not configured"
```bash
cd backend
echo "COMPOSIO_API_KEY=your_key_here" >> .env
```

### "Gmail is not connected"
- Visit `/dashboard/integrations`
- Click "Connect Gmail"
- Authorize Composio

### "No suggestions available"
- Run email sync first: `curl "http://localhost:8000/api/email/sync?user_id=YOUR_USER_ID"`
- Wait for sync to complete
- Try again

### Agent doesn't respond
- Check backend logs for errors
- Verify `agents/gmail_filter_agent.py` exists
- Ensure `gmail_filter_service.py` is in backend folder

## 🎯 What to Test

1. ✅ **Basic Archive** - "Archive emails from test@example.com"
2. ✅ **Batch Setup** - "Set up newsletter filters"
3. ✅ **Suggestions** - "Show me filter suggestions"
4. ✅ **List Filters** - "List all my filters"
5. ✅ **Mark Important** - "Mark emails from boss@company.com as important"
6. ✅ **Delete Filter** - "Delete the filter for test@example.com"

## 📊 Success Criteria

- ✅ Agent responds to all commands
- ✅ Filters appear in Gmail settings
- ✅ Test emails get archived correctly
- ✅ Suggestions load (if you have email data)
- ✅ No errors in backend logs

## 🎉 You're Ready!

The agent is **live and ready to use**. Just talk to your assistant naturally:

- "I'm getting too many newsletters, can you help?"
- "Archive all emails from spam@example.com"
- "What senders should I filter?"
- "Set up my inbox automation"

The agent will understand and execute the appropriate filter operations!

---

**Need help?** Check:
- `GMAIL_FILTERS_GUIDE.md` - Full documentation
- `TESTING_GMAIL_FILTERS.md` - Detailed testing guide
- Backend logs: `tail -f backend/logs/app.log | grep gmail_filter`

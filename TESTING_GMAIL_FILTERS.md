# Testing Gmail Filter System

## Prerequisites

1. **Composio API Key** must be valid
   - Go to https://app.composio.dev
   - Generate/renew your API key
   - Update `COMPOSIO_API_KEY` in `backend/.env`

2. **Gmail Connected**
   - Visit your CRM at `/dashboard/integrations`
   - Click "Connect Gmail"
   - Authorize Composio

3. **Backend Running**
   ```bash
   cd backend
   python server.py
   ```

## Test 1: Quick Setup (Recommended First Test)

### Via Web UI
1. Navigate to `http://localhost:3000/dashboard/gmail-filters`
2. Click the **"Quick Setup"** tab
3. Click **"Create All Filters"**
4. Verify success message shows "Created 9 filters"

### Via API
```bash
curl -X POST http://localhost:8000/api/gmail/filters/batch/newsletters \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID"
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "created": 9,
  "failed": 0,
  "filters": [
    {
      "sender": "customerservice@exct.stansberryresearch.com",
      "filter_id": "ANe1BmhK...",
      "status": "created"
    },
    ...
  ]
}
```

## Test 2: Archive Single Sender

### Via Web UI
1. Go to "My Filters" tab
2. Enter `test@example.com` in the input
3. Click "Archive Sender"
4. Verify filter appears in the list

### Via API
```bash
curl -X POST http://localhost:8000/api/gmail/filters/archive-sender \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID",
    "sender": "test@example.com",
    "also_mark_read": false
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "filter_id": "ANe1BmhK..."
}
```

## Test 3: Get Filter Suggestions

### Via Web UI
1. Click the **"Suggestions"** tab
2. Wait for analysis to complete
3. Review suggested filters
4. Click "Create Filter" on any suggestion

### Via API
```bash
curl "http://localhost:8000/api/gmail/filters/suggestions?user_id=YOUR_USER_ID&min_count=3"
```

**Expected Response:**
```json
{
  "success": true,
  "suggestions": [
    {
      "sender": "promo@store.com",
      "count": 15,
      "sample_subjects": ["Sale!", "New arrivals", "Weekly deals"],
      "suggested_action": "archive",
      "reason": "High volume sender",
      "read_rate": 0.13
    }
  ],
  "count": 1
}
```

## Test 4: List Filters

### Via API
```bash
curl "http://localhost:8000/api/gmail/filters/my-filters?user_id=YOUR_USER_ID"
```

**Expected Response:**
```json
{
  "success": true,
  "filters": [
    {
      "id": "ANe1BmhK...",
      "criteria": {"from": "test@example.com"},
      "action": {"removeLabelIds": ["INBOX"]},
      "type": "archive_sender",
      "created_at": "2026-05-25T15:00:00Z"
    }
  ],
  "count": 1
}
```

## Test 5: Delete Filter

### Via Web UI
1. Go to "My Filters" tab
2. Find the filter you want to delete
3. Click "Delete" button
4. Confirm deletion
5. Verify filter is removed from list

### Via API
```bash
curl -X DELETE "http://localhost:8000/api/gmail/filters/delete/FILTER_ID?user_id=YOUR_USER_ID"
```

**Expected Response:**
```json
{
  "success": true
}
```

## Test 6: AI Agent Commands

### Via Assistant Chat
Open your CRM assistant and try these commands:

1. **"Set up newsletter filters"**
   - Should create 9 filters
   - Returns success message with count

2. **"Archive all emails from spam@example.com"**
   - Creates single archive filter
   - Returns filter ID

3. **"Show me filter suggestions"**
   - Analyzes inbox
   - Returns list of recommended filters

4. **"List all my filters"**
   - Shows all active filters
   - Formatted in readable text

5. **"Delete the filter for test@example.com"**
   - Finds and deletes filter
   - Confirms deletion

## Test 7: Smart Filter Types

### Archive by Domain
```bash
curl -X POST http://localhost:8000/api/gmail/filters/smart-create \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID",
    "filter_type": "archive_domain",
    "params": {"domain": "marketing.com"}
  }'
```

### Mark as Important
```bash
curl -X POST http://localhost:8000/api/gmail/filters/smart-create \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID",
    "filter_type": "important_sender",
    "params": {"sender": "boss@company.com"}
  }'
```

### Archive Large Attachments
```bash
curl -X POST http://localhost:8000/api/gmail/filters/smart-create \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID",
    "filter_type": "archive_large",
    "params": {"size_mb": 10}
  }'
```

## Verification in Gmail

After creating filters, verify they work:

1. Go to Gmail settings → Filters and Blocked Addresses
2. You should see all created filters listed
3. Send a test email from a filtered address
4. Verify it gets archived (skips inbox)

## Common Issues & Solutions

### Issue: "COMPOSIO_API_KEY not configured"
**Solution:** 
```bash
cd backend
echo "COMPOSIO_API_KEY=your_key_here" >> .env
```

### Issue: "Gmail is not connected"
**Solution:**
1. Visit `/dashboard/integrations`
2. Click "Connect Gmail"
3. Complete OAuth flow

### Issue: "401 Unauthorized"
**Solution:**
- Composio API key expired
- Go to https://app.composio.dev
- Generate new key
- Update `.env`

### Issue: "No suggestions available"
**Solution:**
- Email sync hasn't run yet
- Run: `curl "http://localhost:8000/api/email/sync?user_id=YOUR_USER_ID"`
- Wait for sync to complete
- Try suggestions again

### Issue: "Filter creation failed"
**Solution:**
- Check Gmail API scopes include `gmail.settings.basic`
- Verify Composio connection is active
- Check you haven't hit Gmail's 1,000 filter limit

## Performance Testing

### Batch Create 100 Filters
```python
import asyncio
import httpx

async def test_batch():
    async with httpx.AsyncClient() as client:
        for i in range(100):
            await client.post(
                "http://localhost:8000/api/gmail/filters/archive-sender",
                json={
                    "user_id": "YOUR_USER_ID",
                    "sender": f"test{i}@example.com"
                }
            )
            print(f"Created filter {i+1}/100")

asyncio.run(test_batch())
```

**Expected:** All 100 filters created successfully (takes ~2-3 minutes due to API rate limits)

## Integration Testing

### Test with Real Newsletter
1. Find a real newsletter in your inbox
2. Copy sender email
3. Create filter via UI or API
4. Ask sender to send you another email
5. Verify it gets archived

### Test Catch-All Filter
1. Create the "unsubscribe" catch-all filter
2. Find any newsletter with unsubscribe link
3. Forward it to yourself
4. Verify it gets archived

## Monitoring

### Check Filter Count
```bash
curl "http://localhost:8000/api/gmail/filters/my-filters?user_id=YOUR_USER_ID" | jq '.count'
```

### Check Database
```javascript
// In MongoDB shell
use crm_db
db.gmail_filters.countDocuments({user_id: "YOUR_USER_ID"})
db.gmail_filters.find({user_id: "YOUR_USER_ID"}).pretty()
```

### Check Logs
```bash
# Backend logs
tail -f backend/logs/app.log | grep gmail_filter

# Look for:
# [gmail_filter] Created filter ANe1BmhK... for user user123
# [gmail_filter] Batch setup complete: 9 created, 0 failed
```

## Success Criteria

✅ All 9 newsletter filters created successfully
✅ Single sender archive filter works
✅ Filter suggestions load and display
✅ Filters appear in Gmail settings
✅ Test email gets archived correctly
✅ AI agent commands work
✅ Web UI loads without errors
✅ API returns proper JSON responses

## Next Steps After Testing

1. **Monitor Performance**
   - Check filter effectiveness after 1 week
   - Review inbox reduction metrics

2. **Tune Suggestions**
   - Adjust `min_sender_count` threshold
   - Add custom heuristics for your inbox patterns

3. **Expand Templates**
   - Add more newsletter senders to predefined list
   - Create industry-specific filter templates

4. **User Feedback**
   - Collect which filters users create most
   - Add popular patterns to Quick Setup

---

**Need Help?**
- Check `GMAIL_FILTERS_GUIDE.md` for full documentation
- Review Composio docs: https://docs.composio.dev/toolkits/gmail
- Check Gmail API docs: https://developers.google.com/gmail/api/guides/filter_settings

# Gmail Filter Management System

## Overview

Your CRM now has **full programmatic control** over Gmail filters! This means you can create, manage, and automate email filters through:
- 🤖 **AI Agent** - Natural language commands
- 🌐 **Web UI** - Visual filter management dashboard
- 🔌 **API** - Direct programmatic access
- 📦 **Batch Operations** - Set up multiple filters at once

## Quick Start (2 minutes)

### Option 1: Use the Web UI

1. Navigate to `/dashboard/gmail-filters` in your CRM
2. Click **"Quick Setup"** tab
3. Click **"Create All Filters"**
4. Done! 8+ newsletter filters created instantly

### Option 2: Use the AI Agent

Talk to your AI assistant:
```
"Set up newsletter filters"
"Archive all emails from newsletter@example.com"
"Show me filter suggestions based on my inbox"
```

### Option 3: Use the API

```bash
# Batch create newsletter filters
curl -X POST http://localhost:8000/api/gmail/filters/batch/newsletters \
  -H "Content-Type: application/json" \
  -d '{"user_id": "YOUR_USER_ID"}'

# Archive a specific sender
curl -X POST http://localhost:8000/api/gmail/filters/archive-sender \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "YOUR_USER_ID",
    "sender": "newsletter@example.com",
    "also_mark_read": false
  }'
```

## Features

### 1. Predefined Newsletter Filters

Automatically archives emails from these common senders:
- `customerservice@exct.stansberryresearch.com`
- `info@exct.chaikinanalytics.com`
- `stocknewsletter@mail.beehiiv.com`
- `info@analyticsindiamag.com`
- `newsletters@analystratings.net`
- `partners@analystratings.net`
- `newsmax@latest.newsmax.com`
- `team@cmail.bark.com`

Plus a **catch-all filter** that archives any email containing "unsubscribe" in the body.

### 2. Smart Filter Suggestions

The system analyzes your inbox and suggests filters for:
- High-volume senders (10+ emails)
- Low-engagement senders (rarely read)
- Newsletter/automated senders
- Promotional content

### 3. Custom Filter Types

Create filters for various scenarios:

| Filter Type | Description | Example |
|------------|-------------|---------|
| `archive_sender` | Archive emails from sender | Archive all from `spam@example.com` |
| `archive_domain` | Archive entire domain | Archive all from `@marketing.com` |
| `archive_subject` | Archive by subject keyword | Archive all with "Newsletter" |
| `important_sender` | Mark sender as important | Important: `boss@company.com` |
| `label_sender` | Apply custom label | Label `invoices@vendor.com` as "Invoices" |
| `forward_sender` | Forward to another email | Forward `alerts@system.com` to `team@company.com` |
| `archive_large` | Archive large attachments | Archive emails > 10MB |
| `archive_unsubscribe` | Archive emails with unsubscribe | Catch-all for newsletters |

## API Reference

### Base URL
```
http://localhost:8000/api/gmail/filters
```

### Endpoints

#### 1. List Filters
```http
GET /list?user_id=USER_ID
```

**Response:**
```json
{
  "success": true,
  "filters": [
    {
      "id": "filter_123",
      "criteria": {"from": "newsletter@example.com"},
      "action": {"removeLabelIds": ["INBOX"]}
    }
  ],
  "count": 1
}
```

#### 2. Create Filter
```http
POST /create
Content-Type: application/json

{
  "user_id": "USER_ID",
  "criteria": {
    "from": "sender@example.com",
    "subject": "Newsletter",
    "query": "has:attachment",
    "hasAttachment": true,
    "size": 10485760,
    "sizeComparison": "larger"
  },
  "action": {
    "addLabelIds": ["IMPORTANT"],
    "removeLabelIds": ["INBOX", "UNREAD"]
  }
}
```

**Response:**
```json
{
  "success": true,
  "filter_id": "filter_123",
  "filter": {...}
}
```

#### 3. Delete Filter
```http
DELETE /delete/{filter_id}?user_id=USER_ID
```

#### 4. Smart Create
```http
POST /smart-create
Content-Type: application/json

{
  "user_id": "USER_ID",
  "filter_type": "archive_sender",
  "params": {
    "sender": "newsletter@example.com"
  }
}
```

#### 5. Batch Newsletter Setup
```http
POST /batch/newsletters
Content-Type: application/json

{
  "user_id": "USER_ID",
  "custom_senders": ["extra@newsletter.com"]
}
```

**Response:**
```json
{
  "success": true,
  "created": 9,
  "failed": 0,
  "filters": [
    {
      "sender": "customerservice@exct.stansberryresearch.com",
      "filter_id": "filter_123",
      "status": "created"
    }
  ]
}
```

#### 6. Get Suggestions
```http
GET /suggestions?user_id=USER_ID&min_count=3
```

**Response:**
```json
{
  "success": true,
  "suggestions": [
    {
      "sender": "promo@store.com",
      "count": 15,
      "sample_subjects": ["Sale!", "New arrivals"],
      "suggested_action": "archive",
      "reason": "High volume sender",
      "read_rate": 0.13
    }
  ]
}
```

#### 7. Archive Sender (Quick)
```http
POST /archive-sender
Content-Type: application/json

{
  "user_id": "USER_ID",
  "sender": "newsletter@example.com",
  "also_mark_read": false
}
```

#### 8. My Filters (from DB)
```http
GET /my-filters?user_id=USER_ID
```

## AI Agent Usage

The Gmail Filter Agent understands natural language commands:

### Archive Commands
```
"Archive all emails from newsletter@example.com"
"Archive emails from @marketing.com domain"
"Archive large emails over 10MB"
```

### Important Commands
```
"Mark emails from boss@company.com as important"
"Make sender@client.com important"
```

### Batch Operations
```
"Set up newsletter filters"
"Set up filters for all my newsletters"
```

### Analysis
```
"Show me filter suggestions"
"Analyze my inbox for filter recommendations"
"What senders should I filter?"
```

### Management
```
"List all my filters"
"Show my active filters"
"Delete the filter for sender@example.com"
```

## Integration with Composio

The system uses **Composio's Gmail API integration** via OAuth:

1. User connects Gmail through Composio (already set up in your CRM)
2. Filters are created using Gmail API's `users.settings.filters` endpoint
3. All operations go through Composio's proxy for automatic token refresh

### Required Scopes
- `https://www.googleapis.com/auth/gmail.settings.basic` - Create/manage filters
- `https://www.googleapis.com/auth/gmail.readonly` - Read emails for suggestions

## Database Schema

Filters are tracked in MongoDB for fast access:

```javascript
{
  _id: ObjectId,
  user_id: "user123",
  filter_id: "gmail_filter_abc123",
  criteria: {
    from: "sender@example.com"
  },
  action: {
    removeLabelIds: ["INBOX"]
  },
  filter_type: "archive_sender",
  created_at: ISODate("2026-05-25T15:00:00Z"),
  updated_at: ISODate("2026-05-25T15:00:00Z")
}
```

## Advanced Usage

### Create Complex Filters

```python
from gmail_filter_service import create_gmail_filter

# Archive large promotional emails
result = await create_gmail_filter(
    user_id="user123",
    criteria={
        "query": "category:promotions",
        "size": 5242880,  # 5MB
        "sizeComparison": "larger"
    },
    action={
        "removeLabelIds": ["INBOX"],
        "addLabelIds": ["TRASH"]
    }
)
```

### Analyze Inbox Patterns

```python
from gmail_filter_service import analyze_inbox_for_filter_suggestions

suggestions = await analyze_inbox_for_filter_suggestions(
    user_id="user123",
    db=db,
    min_sender_count=5  # Only suggest senders with 5+ emails
)

for sugg in suggestions["suggestions"]:
    print(f"{sugg['sender']}: {sugg['count']} emails ({sugg['reason']})")
```

### Custom Filter Logic

```python
from gmail_filter_service import create_smart_filter

# Forward urgent emails to team
result = await create_smart_filter(
    user_id="user123",
    filter_type="forward_sender",
    params={
        "sender": "alerts@monitoring.com",
        "forward_to": "team@company.com"
    }
)
```

## Troubleshooting

### "Composio API key expired"
- Go to https://app.composio.dev
- Generate a new API key
- Update `COMPOSIO_API_KEY` in `.env`

### "Gmail not connected"
- Visit `/dashboard/integrations` in your CRM
- Click "Connect Gmail"
- Authorize Composio to access your Gmail

### "Filter creation failed"
- Check that Gmail API scopes include `gmail.settings.basic`
- Verify Composio connection is active
- Gmail has a limit of 1,000 filters per account

### "Suggestions not loading"
- Ensure email sync has run at least once
- Check that `email_messages` collection has data
- Try lowering `min_count` parameter

## Best Practices

1. **Start with Quick Setup** - Use the predefined newsletter filters first
2. **Review Suggestions** - Check AI suggestions before creating filters
3. **Test One at a Time** - Create one filter, verify it works, then batch create
4. **Use Catch-All Last** - The "unsubscribe" catch-all should be your last resort
5. **Monitor Regularly** - Check filter suggestions monthly to catch new patterns

## Limitations

- **Gmail Limit**: Maximum 1,000 filters per account
- **Not Retroactive**: Filters only apply to new emails (not existing ones)
- **API Rate Limits**: Composio/Gmail may rate limit bulk operations
- **Scope Required**: User must grant `gmail.settings.basic` scope

## Future Enhancements

- [ ] Bulk edit existing filters
- [ ] Filter templates library
- [ ] Scheduled filter analysis reports
- [ ] Filter performance analytics (how many emails filtered)
- [ ] Import/export filters as JSON
- [ ] Filter testing (preview matches before creating)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Composio docs: https://docs.composio.dev/toolkits/gmail
3. Check Gmail API docs: https://developers.google.com/gmail/api/guides/filter_settings

---

**Built with:**
- Gmail API (via Composio)
- FastAPI (backend)
- Next.js (frontend)
- MongoDB (filter tracking)
- AI Agent (natural language interface)

# Gmail Filters — Quick Start (2 min)

## 🚀 Fastest Way: Web UI

1. Go to: `http://localhost:3000/dashboard/gmail-filters`
2. Click **"Quick Setup"** tab
3. Click **"Create All Filters"**
4. ✅ Done! 9 filters created

## 📋 What Gets Filtered

These senders will now auto-archive:
- ✉️ Stansberry Research newsletters
- ✉️ Chaikin Analytics
- ✉️ Stock newsletters (Beehiiv)
- ✉️ Analytics India Magazine
- ✉️ Analyst Ratings
- ✉️ Newsmax
- ✉️ Bark.com
- ✉️ **Plus:** Any email with "unsubscribe" (catch-all)

## 🤖 AI Agent Commands

Just talk to your assistant:

```
"Set up newsletter filters"
"Archive emails from spam@example.com"
"Show me filter suggestions"
"List my filters"
```

## 🔌 API One-Liner

```bash
curl -X POST http://localhost:8000/api/gmail/filters/batch/newsletters \
  -H "Content-Type: application/json" \
  -d '{"user_id": "YOUR_USER_ID"}'
```

## ⚡ Quick Actions

### Archive a Sender
**UI:** Enter email → Click "Archive Sender"
**API:**
```bash
curl -X POST http://localhost:8000/api/gmail/filters/archive-sender \
  -d '{"user_id": "YOUR_USER_ID", "sender": "spam@example.com"}'
```

### Get AI Suggestions
**UI:** Click "Suggestions" tab
**API:**
```bash
curl "http://localhost:8000/api/gmail/filters/suggestions?user_id=YOUR_USER_ID"
```

### List All Filters
**UI:** Click "My Filters" tab
**API:**
```bash
curl "http://localhost:8000/api/gmail/filters/my-filters?user_id=YOUR_USER_ID"
```

## 🎯 Common Use Cases

| Want to... | Do this... |
|-----------|-----------|
| Archive newsletters | Quick Setup → Create All Filters |
| Archive one sender | My Filters → Enter email → Archive Sender |
| Find noisy senders | Suggestions tab → Review AI recommendations |
| Mark boss as important | AI: "Mark emails from boss@company.com as important" |
| Archive large files | API: `filter_type: "archive_large"` |

## ⚠️ Before You Start

1. **Composio API Key** must be set in `backend/.env`
2. **Gmail must be connected** at `/dashboard/integrations`
3. **Backend must be running** on port 8000

## 🔍 Verify It Works

1. Go to Gmail → Settings → Filters and Blocked Addresses
2. You should see your new filters listed
3. Send a test email from a filtered address
4. It should skip your inbox (archived)

## 💡 Pro Tips

- Filters apply to **future emails only** (not retroactive)
- "Archive" = skip inbox but keep in All Mail
- Gmail limit: 1,000 filters per account
- Check Suggestions weekly for new patterns

## 🆘 Troubleshooting

**"API key not configured"** → Update `COMPOSIO_API_KEY` in `.env`
**"Gmail not connected"** → Visit `/dashboard/integrations` → Connect Gmail
**"No suggestions"** → Run email sync first, then try again

## 📚 Full Documentation

- **Complete Guide:** `GMAIL_FILTERS_GUIDE.md`
- **Testing Guide:** `TESTING_GMAIL_FILTERS.md`
- **API Reference:** See guide for all endpoints

---

**That's it!** Your inbox is now automated. 🎉

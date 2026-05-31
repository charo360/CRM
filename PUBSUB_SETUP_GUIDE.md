# Gmail Pub/Sub Setup Guide

## Prerequisites Completed ✅
- Google Cloud Project: **zilocrm**
- Project Number: **1027344689629**

---

## Step 1: Create Service Account & Download Credentials

### 1.1 Create Service Account
1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts?project=zilocrm
2. Click **"+ CREATE SERVICE ACCOUNT"**
3. Fill in:
   - **Service account name:** `crm-pubsub-service`
   - **Service account ID:** `crm-pubsub-service` (auto-filled)
   - **Description:** "Service account for CRM Gmail Pub/Sub notifications"
4. Click **"CREATE AND CONTINUE"**

### 1.2 Grant Permissions
5. Add these roles:
   - **Pub/Sub Admin** (to create topics/subscriptions)
   - **Pub/Sub Subscriber** (to pull messages)
6. Click **"CONTINUE"** → **"DONE"**

### 1.3 Download JSON Key
7. Click on the newly created service account
8. Go to **"KEYS"** tab
9. Click **"ADD KEY"** → **"Create new key"**
10. Choose **JSON** format
11. Click **"CREATE"**
12. Save the downloaded JSON file as: `c:\Users\sarch\Desktop\crm\backend\google-credentials.json`

---

## Step 2: Install Google Cloud Pub/Sub Library

```bash
cd c:\Users\sarch\Desktop\crm\backend
pip install google-cloud-pubsub
```

---

## Step 3: Set Environment Variable

### Option A: Add to `.env` file
Add this line to `backend/.env`:
```
GOOGLE_APPLICATION_CREDENTIALS=c:\Users\sarch\Desktop\crm\backend\google-credentials.json
```

### Option B: Set in PowerShell (temporary)
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="c:\Users\sarch\Desktop\crm\backend\google-credentials.json"
```

---

## Step 4: Run Setup Script

```bash
cd c:\Users\sarch\Desktop\crm\backend
python pubsub_setup.py
```

**Expected output:**
```
🚀 Setting up Google Cloud Pub/Sub for Gmail notifications...

Project ID: zilocrm
Topic ID: gmail-notifications
Subscription ID: gmail-notifications-pull

Step 1: Creating topic...
✅ Created topic: projects/zilocrm/topics/gmail-notifications

Step 2: Granting Gmail publish permission...
✅ Granted publish permission to gmail-api-push@system.gserviceaccount.com

Step 3: Creating pull subscription...
✅ Created subscription: projects/zilocrm/subscriptions/gmail-notifications-pull

✅ Setup complete!
```

---

## Step 5: Verify in Google Cloud Console

1. Go to: https://console.cloud.google.com/cloudpubsub/topic/list?project=zilocrm
2. You should see: **gmail-notifications** topic
3. Click on it → **SUBSCRIPTIONS** tab
4. You should see: **gmail-notifications-pull** subscription

---

## Next Steps (After Setup)

- [ ] Implement webhook endpoint to pull Pub/Sub messages
- [ ] Register Gmail watch for each connected user
- [ ] Create background worker to process notifications
- [ ] Add watch renewal scheduler

---

## Troubleshooting

### Error: "Could not automatically determine credentials"
**Solution:** Make sure `GOOGLE_APPLICATION_CREDENTIALS` is set correctly

### Error: "Permission denied"
**Solution:** Ensure service account has "Pub/Sub Admin" role

### Error: "Topic already exists"
**Solution:** This is fine! The script will skip creation and continue

---

## Security Notes

⚠️ **IMPORTANT:** Add to `.gitignore`:
```
backend/google-credentials.json
```

Never commit the credentials JSON file to Git!

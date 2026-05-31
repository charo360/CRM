# Feature Roadmap: Real-Time Email Sync & Browser Automation

**Last Updated:** May 24, 2026  
**Status:** Planning Phase

---

## 🎯 Strategic Goals

- **Real-time email notifications** → Eliminate 10-minute polling delay
- **Browser automation** → Compete with Manus Browser Operator
- **Market positioning** → "AI Business OS with instant sync and universal web control"

---

## 📧 Feature 1: Webhook-Based Email Sync

### Gmail Push Notifications (via Composio Webhooks) ✅

#### Phase 1: Composio Webhook Setup ✅
- [x] **1.1** Create webhook subscription in Composio
  - Script: `backend/setup_composio_webhooks.py`
  - Webhook URL: `https://your-domain.com/api/webhooks/composio`
  - Subscribe to trigger events

- [x] **1.2** Create webhook endpoint
  - File: `backend/composio_webhooks.py`
  - Route: `POST /api/webhooks/composio`
  - Verify webhook signature
  - Process `GMAIL_NEW_GMAIL_MESSAGE` events

- [x] **1.3** Register Gmail triggers per user
  - Trigger: `GMAIL_NEW_GMAIL_MESSAGE`
  - Auto-register when user connects Gmail
  - Store `connected_account_id` in user document

#### Phase 2: Backend Implementation ✅
- [x] **2.1** Webhook handler
  - File: `backend/composio_webhooks.py`
  - Function: `handle_composio_webhook()`
  - Parse event payload
  - Route to appropriate handler

- [x] **2.2** Gmail event processor
  - Function: `process_gmail_trigger()`
  - Extract email metadata from webhook
  - Fetch full message via Composio API
  - Store in MongoDB

- [x] **2.3** Database integration
  - Reuse existing `_store_messages()` function
  - Trigger email classification
  - Update user's email threads

- [x] **2.4** Setup automation
  - Script: `setup_composio_webhooks.py`
  - Creates webhook subscription
  - Registers triggers for all Gmail users
  - Outputs webhook secret for .env

#### Phase 3: Testing & Monitoring
- [ ] **3.1** Test with single user account
  - Connect Gmail via Composio
  - Register watch
  - Send test email → verify notification received
  - Check MongoDB updated within 5 seconds

- [ ] **3.2** Load testing
  - Test with 10+ concurrent users
  - Verify no duplicate notifications
  - Monitor Pub/Sub quota usage

- [ ] **3.3** Error handling
  - Handle expired watches gracefully
  - Fallback to polling if webhook fails
  - Alert admin if watch registration fails

- [ ] **3.4** Monitoring dashboard
  - Track active watches count
  - Monitor notification latency
  - Alert on Pub/Sub errors

#### Estimated Effort: **2-3 days**
#### Infrastructure Cost: **$5-20/month** (Pub/Sub)

---

### Outlook Webhooks (via Microsoft Graph)

#### Phase 1: Infrastructure Setup
- [ ] **1.1** Verify Microsoft Graph permissions
  - App registration in Azure AD
  - Required scopes: `Mail.Read`, `Mail.ReadWrite`
  - Webhook permission: `Mail.Read` (delegated)

- [ ] **1.2** Set up webhook endpoint
  - Route: `POST /api/webhooks/outlook`
  - Must respond to validation request with `validationToken`
  - Endpoint must be publicly accessible HTTPS

#### Phase 2: Backend Implementation
- [ ] **2.1** Create webhook endpoint
  - File: `backend/webhooks/outlook_webhook.py`
  - Route: `POST /api/webhooks/outlook`
  - Validate `clientState` secret
  - Handle validation handshake

- [ ] **2.2** Subscription manager
  - File: `backend/composio_service.py`
  - Function: `create_outlook_subscription(user_id)`
  - API: `POST /subscriptions` to Microsoft Graph
  - Store subscription ID and expiration

- [ ] **2.3** Notification handler
  - Parse notification payload
  - Extract changed message IDs
  - Fetch full messages via Graph API
  - Update MongoDB

- [ ] **2.4** Database schema updates
  - Collection: `email_sync_status`
  - Add fields:
    - `outlook_subscription_id`: String
    - `outlook_subscription_expiration`: DateTime
    - `outlook_client_state`: String (secret)

- [ ] **2.5** Subscription renewal scheduler
  - Job: `renew_outlook_subscriptions()` runs every 6 hours
  - Renew subscriptions expiring in <12 hours
  - Max subscription lifetime: 3 days for messages

#### Phase 3: Testing & Monitoring
- [ ] **3.1** Test validation handshake
  - Create subscription
  - Verify Microsoft sends validation request
  - Confirm subscription created successfully

- [ ] **3.2** Test notifications
  - Send email to connected Outlook account
  - Verify webhook receives notification
  - Check MongoDB updated

- [ ] **3.3** Test subscription renewal
  - Wait for expiration
  - Verify auto-renewal works
  - Test manual renewal endpoint

- [ ] **3.4** Error handling
  - Handle expired subscriptions
  - Retry failed renewals
  - Fallback to polling if webhooks fail

#### Estimated Effort: **2-3 days**
#### Infrastructure Cost: **Free** (included with Graph API)

---

## 🌐 Feature 2: Browser Automation

### Chrome Extension Approach (Recommended)

#### Phase 1: Extension Foundation
- [ ] **1.1** Project setup
  - Create folder: `extension/browser-operator/`
  - Manifest V3 configuration
  - Icons and branding assets

- [ ] **1.2** Manifest.json
  - Permissions: `activeTab`, `scripting`, `storage`
  - Host permissions: `<all_urls>` (user approves per-site)
  - Background service worker
  - Content scripts injection

- [ ] **1.3** Background service worker
  - File: `extension/browser-operator/background.js`
  - WebSocket connection to backend
  - Command queue management
  - Session state tracking

- [ ] **1.4** Content script
  - File: `extension/browser-operator/content.js`
  - DOM manipulation API
  - Element selector (CSS, XPath)
  - Event listeners for AI commands

#### Phase 2: Backend WebSocket Server
- [ ] **2.1** WebSocket endpoint
  - File: `backend/browser_control/websocket.py`
  - Route: `WS /ws/browser/{user_id}`
  - Authentication via JWT token
  - Connection pool management

- [ ] **2.2** Command protocol
  - Define JSON command schema:
    - `click`: Click element by selector
    - `type`: Fill input field
    - `extract`: Get text/data from page
    - `navigate`: Go to URL
    - `screenshot`: Capture page image
    - `scroll`: Scroll to element

- [ ] **2.3** Session manager
  - File: `backend/browser_control/session_manager.py`
  - Track active browser sessions
  - Queue commands per session
  - Timeout inactive sessions (5 min)

- [ ] **2.4** Database schema
  - Collection: `browser_sessions`
  - Fields:
    - `user_id`: String
    - `session_id`: String
    - `connected_at`: DateTime
    - `last_command_at`: DateTime
    - `allowed_domains`: Array[String]

#### Phase 3: AI Integration
- [ ] **3.1** Browser control tools
  - File: `backend/assistant/tools.py`
  - Tool: `browser_click(selector, description)`
  - Tool: `browser_type(selector, text)`
  - Tool: `browser_extract(selector, data_type)`
  - Tool: `browser_navigate(url)`
  - Tool: `browser_screenshot()`

- [ ] **3.2** Element selector AI
  - Use GPT-4 Vision to identify elements
  - Natural language → CSS selector conversion
  - Fallback to XPath if CSS fails

- [ ] **3.3** Workflow recorder (Future)
  - User demonstrates task in browser
  - Extension records actions
  - AI converts to reusable workflow

#### Phase 4: Extension Features
- [ ] **4.1** Element highlighter
  - Visual feedback when AI selects element
  - Highlight in yellow before action
  - Confirm/cancel prompt for destructive actions

- [ ] **4.2** Permission manager
  - User approves domains before automation
  - Whitelist/blacklist management
  - Per-domain permission levels

- [ ] **4.3** Action logger
  - Log all browser actions
  - Display in extension popup
  - Export audit trail

- [ ] **4.4** Screenshot capture
  - Full page screenshot
  - Visible viewport only
  - Element-specific capture

#### Phase 5: Security & Safety
- [ ] **5.1** Command whitelist
  - Block dangerous actions: `eval()`, file access
  - Sanitize user input
  - Rate limiting (max 10 commands/min)

- [ ] **5.2** Domain approval flow
  - User must approve each domain
  - Show permission request popup
  - Store approved domains in extension storage

- [ ] **5.3** Audit logging
  - Log all commands to backend
  - User can review action history
  - Admin dashboard for monitoring

- [ ] **5.4** Session encryption
  - Encrypt WebSocket messages
  - Use TLS for all connections
  - Rotate session tokens every 24h

#### Phase 6: Testing & Deployment
- [ ] **6.1** Local testing
  - Test on localhost sites
  - Verify all command types work
  - Test WebSocket reconnection

- [ ] **6.2** Chrome Web Store submission
  - Prepare store listing
  - Screenshots and demo video
  - Privacy policy and terms

- [ ] **6.3** User onboarding
  - Installation guide
  - Video tutorial
  - Sample automation workflows

- [ ] **6.4** Beta testing
  - Invite 10-20 users
  - Collect feedback
  - Fix critical bugs

#### Estimated Effort: **2-3 weeks**
#### Infrastructure Cost: **$10-30/month** (WebSocket server)

---

## 📊 Success Metrics

### Email Webhooks
- [ ] **Notification latency** < 10 seconds (vs. 10 minutes polling)
- [ ] **Watch uptime** > 99.5%
- [ ] **Sync accuracy** 100% (no missed emails)
- [ ] **Cost per user** < $0.10/month

### Browser Automation
- [ ] **Command success rate** > 95%
- [ ] **Average command latency** < 2 seconds
- [ ] **User adoption** 30%+ of active users install extension
- [ ] **Workflows created** 100+ unique automation workflows

---

## 🚀 Launch Plan

### Week 1-2: Email Webhooks
- [ ] Gmail Pub/Sub setup
- [ ] Outlook Graph webhooks
- [ ] Testing with 10 beta users
- [ ] **Ship to production**

### Week 3-5: Browser Extension
- [ ] Extension MVP (click, type, extract)
- [ ] WebSocket backend
- [ ] AI tool integration
- [ ] Chrome Web Store submission

### Week 6: Polish & Marketing
- [ ] Documentation and tutorials
- [ ] Blog post: "Real-time email sync"
- [ ] Blog post: "AI browser automation"
- [ ] Comparison page vs. Manus

---

## 📝 Notes & Decisions

### Email Webhooks
- **Decision:** Use Composio for Gmail API calls (not direct Gmail API)
- **Reason:** Existing integration, handles OAuth refresh
- **Trade-off:** Pub/Sub still requires direct Google Cloud setup

### Browser Automation
- **Decision:** Chrome extension (not headless browser)
- **Reason:** More secure, uses user's authenticated sessions
- **Trade-off:** Requires user to install extension

### Infrastructure
- **Decision:** Self-hosted WebSocket server (not third-party)
- **Reason:** Full control, lower cost at scale
- **Trade-off:** More DevOps complexity

---

## 🔗 Resources

### Gmail Webhooks
- [Gmail Push Notifications Guide](https://developers.google.com/workspace/gmail/api/guides/push)
- [Google Cloud Pub/Sub Docs](https://cloud.google.com/pubsub/docs)
- [Composio Gmail Integration](https://docs.composio.dev)

### Outlook Webhooks
- [Microsoft Graph Webhooks](https://learn.microsoft.com/en-us/graph/outlook-change-notifications-overview)
- [Subscription API Reference](https://learn.microsoft.com/en-us/graph/api/subscription-post-subscriptions)

### Browser Automation
- [Chrome Extension Manifest V3](https://developer.chrome.com/docs/extensions/mv3/)
- [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [Puppeteer Documentation](https://pptr.dev/) (reference for API design)

---

## ✅ Completion Tracking

**Overall Progress:** 0/94 tasks (0%)

### By Feature
- **Gmail Webhooks:** 0/23 tasks
- **Outlook Webhooks:** 0/19 tasks
- **Browser Extension:** 0/52 tasks

**Next Action:** Choose which feature to start with and begin Phase 1 setup.

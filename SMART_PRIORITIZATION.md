# 🎯 Smart Customer Prioritization

## The Problem (Fixed)

**Before**: System treated all "never contacted" customers equally
- 1872 imported contacts showed as "needs attention"
- No distinction between real customers and imports
- Overwhelmed users with irrelevant suggestions

**After**: System prioritizes based on conversation quality
- Customers who MESSAGE YOU get highest priority
- Active conversations ranked above imports
- Imported contacts without engagement get lowest priority

---

## New Priority Logic

### Priority Tier 1: Customer Initiated (Score: 50+)
**Customers who reached out to YOU**
- They messaged you on WhatsApp
- Auto-created from incoming messages
- Highest urgency - they're interested!

**Example**: Customer asks "Bei ngapi?" on WhatsApp
- ✅ Auto-creates contact
- ✅ Stores conversation
- ✅ High urgency score (70-90)
- ✅ Appears in top suggestions

### Priority Tier 2: Active Conversations (Score: 30-70)
**Customers with message history**
- You've chatted back and forth
- 24-hour window: +40 urgency
- 3-day window: +30 urgency
- Unanswered questions: +20 urgency

**Example**: Customer asked about price 2 days ago
- ✅ 3-day follow-up window
- ✅ Unanswered question detected
- ✅ High urgency (80+)

### Priority Tier 3: VIP/Returning (Score: 20-50)
**Valuable customers going cold**
- VIP tag: +25 urgency
- Returning customer: +15 urgency
- Purchase history: +5-10 urgency

**Example**: VIP customer, 15 days no contact
- ✅ VIP bonus
- ✅ Re-engagement needed
- ✅ Medium urgency (45-60)

### Priority Tier 4: Imported Contacts (Score: 5-15)
**Manually added, never engaged**
- No conversation history
- No messages exchanged
- Lowest priority

**Example**: Imported from phone contacts
- ❌ No messages
- ❌ Never engaged
- ❌ Low urgency (5-10)

---

## WhatsApp Auto-Creation

### How It Works

**When customer messages you:**
```
Customer: "Hi, do you have laptops?"
```

**System automatically:**
1. ✅ Creates customer record
2. ✅ Stores message in database
3. ✅ Sets `auto_created = True`
4. ✅ Sets `customer_initiated = True`
5. ✅ Updates `last_contacted = now`
6. ✅ Adds to AI analysis queue

**Result**: Customer appears in "Needs Attention" with HIGH urgency

### Webhook Endpoint
```
POST /api/webhooks/whatsapp
```

Receives from Twilio:
- `From`: Customer's WhatsApp number
- `Body`: Message content
- `ProfileName`: Customer's WhatsApp name

---

## Urgency Score Breakdown

### Maximum Possible Score: 100

| Factor | Points | Condition |
|--------|--------|-----------|
| **Customer initiated** | +50 | They messaged you first |
| **24-hour window** | +40 | Last contact was yesterday |
| **3-day window** | +30 | Last contact was 3 days ago |
| **VIP customer** | +25 | Tagged as VIP |
| **Unanswered question** | +20 | Last message has "?", "price", etc. |
| **They messaged last** | +20 | Direction = incoming |
| **New with conversation** | +15 | New tag + has messages |
| **Returning customer** | +15 | Tagged as Returning |
| **High purchase history** | +10 | 10+ purchases |
| **Has conversation** | +30 | Any message history |
| **Auto-created** | +25 | From WhatsApp |
| **Imported, no messages** | +5 | Manual import, never engaged |
| **Has pending follow-up** | -50 | Already scheduled |

### Example Calculations

**Scenario 1: Customer messaged you yesterday**
- Customer initiated: +50
- 24-hour window: +40
- They messaged last: +20
- **Total: 110 → Capped at 100 (URGENT)**

**Scenario 2: VIP customer, 15 days no contact**
- Has conversation: +30
- VIP tag: +25
- 14+ days: +15
- **Total: 70 (HIGH)**

**Scenario 3: Imported contact, never messaged**
- No conversation: +5
- Old import: +5
- **Total: 10 (LOW)**

---

## Smart Filtering

### What Gets Shown (Top 30)
1. Customers who messaged YOU
2. Unanswered questions
3. 24h and 3-day follow-up windows
4. VIP customers going cold
5. Active conversations needing follow-up

### What Gets Hidden
- ❌ Customers with pending follow-ups
- ❌ Recently contacted (<14 days, no conversation)
- ❌ Imported contacts with no engagement
- ❌ Low urgency scores (<30)

---

## Fixing Imported Customers

### The Issue
If you imported 1000+ contacts:
- All show as "never contacted"
- All appear as "needs attention"
- System overwhelmed with irrelevant suggestions

### The Solution
Run the fix script:
```bash
python fix_imported_customers.py
```

**What it does:**
1. Finds customers with `last_contacted = null`
2. Checks if they have any messages
3. If NO messages → Sets `last_contacted = created_at`
4. Marks as `auto_created = False` (imported)

**Result:**
- Imported contacts no longer show as "never contacted"
- They get low urgency scores (5-10)
- System focuses on real conversations

---

## Real-World Examples

### Example 1: New Customer via WhatsApp ✅
```
Customer: "Hi, bei ya laptop ni ngapi?"
```
**System Response:**
- Auto-creates contact "Customer 1234"
- Stores message (direction: incoming)
- Urgency score: 90 (customer initiated + question)
- Appears at TOP of "Needs Attention"
- AI drafts: "Hi! Laptop prices start from KES 25,000..."

### Example 2: Follow-up Window ✅
```
You messaged customer 3 days ago about a product
No response yet
```
**System Response:**
- Detects 3-day window
- Urgency score: 60 (3-day window + has conversation)
- Appears in "Needs Attention"
- AI drafts: "Hi [name], following up on the [product]..."

### Example 3: Imported Contact ❌
```
Contact imported from phone
Never messaged
No conversation history
```
**System Response:**
- Urgency score: 10 (imported, no engagement)
- Does NOT appear in "Needs Attention" (below threshold)
- Will only show if you manually search

---

## Configuration

### Urgency Threshold
```python
# In daily_analyzer.py line 127
if urgency_score < 30:
    return None  # Skip low-priority customers
```

**Adjust this to:**
- `< 20`: More suggestions (includes some imports)
- `< 30`: Balanced (current setting)
- `< 40`: Fewer suggestions (only active conversations)

### Daily Limits
```python
# In daily_analyzer.py lines 83-90
if total_customers < 100:
    return 10  # Small business
elif total_customers < 500:
    return 20  # Medium business
else:
    return 30  # Power user
```

---

## Summary

**The system now understands:**
- ✅ Customers who message YOU are most important
- ✅ Active conversations need timely follow-up
- ✅ Imported contacts without engagement are low priority
- ✅ Real-world usage: customers reach out to businesses
- ✅ Auto-create contacts from WhatsApp automatically

**Result**: Smart, actionable suggestions focused on real opportunities, not imported contact lists.

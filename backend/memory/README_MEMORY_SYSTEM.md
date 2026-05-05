# Persistent Memory System — How Your Agent Remembers Everything

## What This Does

Your Zilo agent now has **ChatGPT-style memory** — it remembers:
- What you're working on
- Decisions you've made
- Key facts you've mentioned
- Recent conversation topics

**Example:**
- Morning: "Create an Instagram carousel for Zilo Starter"
- Evening: "Make it 5 slides instead" → Agent remembers you're working on the carousel

## How It Works

### 1. **MongoDB Storage** (`conversation_memory` collection)

Every business gets one document that stores:

```json
{
  "business_id": "user_123",
  "current_project": "Building Instagram carousel for Zilo Starter",
  "recent_topics": ["Instagram post", "carousel design", "copy approval"],
  "key_facts": {
    "product": "Zilo Starter",
    "platform": "Instagram",
    "format": "3-slide carousel"
  },
  "decisions_made": [
    "Approved 3-slide carousel",
    "Chose benefit-first copy",
    "Selected dark background"
  ],
  "last_conversation_summary": "Working on: Instagram carousel | Context: product=Zilo Starter, platform=Instagram",
  "updated_at": "2026-05-05T04:36:00Z"
}
```

### 2. **The Flow**

```
User opens chat
      ↓
Load conversation_memory from MongoDB
      ↓
Inject into agent's system prompt
      ↓
Agent responds (already knows context)
      ↓
Chat ends
      ↓
LLM extracts key info from conversation
      ↓
Update MongoDB with new facts/decisions
      ↓
Next session → Agent remembers everything
```

### 3. **What Gets Remembered**

✅ **Current project:** "Building Instagram carousel for Zilo Starter"  
✅ **Key facts:** product names, platforms, formats, colors, preferences  
✅ **Decisions:** "Approved 3-slide carousel", "Chose benefit-first copy"  
✅ **Recent topics:** Last 5 conversation topics  

❌ **NOT remembered:** Temporary tasks like "show me revenue" (one-off queries)

### 4. **Files Created**

- **`conversation_memory.py`** — Core memory service
  - `load_conversation_memory()` — Loads memory before each turn
  - `update_conversation_memory()` — Saves context after each turn
  - `format_memory_context()` — Formats memory for agent prompt

- **Updated `context_builder.py`** — Now loads conversation memory alongside preferences
- **Updated `orchestrator.py`** — Loads memory before turn, saves after turn

## How to Test

1. **Start a conversation:**
   ```
   User: "Create an Instagram carousel for Zilo Starter"
   Agent: [asks questions, gathers context]
   ```

2. **Close the chat and come back later:**
   ```
   User: "Make it 5 slides instead"
   Agent: "Got it — updating your Zilo Starter Instagram carousel to 5 slides..."
   ```

The agent **remembers** you're working on a carousel without you re-explaining.

## MongoDB Collection

**Collection name:** `conversation_memory`

**Indexes needed:**
```javascript
db.conversation_memory.createIndex({ "business_id": 1 }, { unique: true })
db.conversation_memory.createIndex({ "updated_at": -1 })
```

## Memory Extraction (Automatic)

After each conversation, an LLM call extracts:
- **Current project** from the conversation
- **Key facts** (product names, platforms, etc.)
- **Decisions made** (approvals, choices)
- **Topic** (brief label for this session)

This runs in the background — never blocks the response.

## What the Agent Sees

Before every turn, the agent's system prompt includes:

```
**Context from previous sessions (you already know this — never ask again):**
**Last session:** Working on: Instagram carousel | Context: product=Zilo Starter, platform=Instagram
**Current project:** Building Instagram carousel for Zilo Starter
**Key context:** product: Zilo Starter, platform: Instagram, format: 3-slide carousel
**Recent decisions:** Approved 3-slide carousel, Chose benefit-first copy
**Recent topics:** Instagram post, carousel design, copy approval
```

## Graceful Degradation

If MongoDB is unavailable:
- Memory loading returns empty dict
- Memory saving fails silently
- Agent still works (just without memory)

No crashes, no errors shown to user.

## Difference from `owner_prefs`

- **`owner_prefs`** (Qdrant) → Style preferences ("Owner prefers dark backgrounds")
- **`conversation_memory`** (MongoDB) → Factual context ("Working on Zilo Starter carousel")

Both are loaded and injected into the agent's prompt.

---

**Result:** Your agent now remembers context across sessions, just like ChatGPT.

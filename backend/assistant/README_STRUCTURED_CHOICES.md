# Structured Choice UI — How It Works

## Overview

Your Zilo agent now provides **tap-to-send suggestion buttons** after every response. Users can click a button to send that message instantly, or type freely to say something else.

This creates a **guided conversation flow** while never trapping the user.

---

## The Complete System

### 1. **Backend: AI Generates Suggestions** (`interactive_suggestions.py`)

After every agent response, an LLM call generates 3-6 contextual follow-up options:

```python
async def build_reply_suggestions(agent_id, user_message, assistant_reply):
    # AI reads the conversation
    # Generates chips that match the current phase
    # Returns: ["Option 1", "Option 2", "Something else — I'll describe it"]
```

**Key features:**
- Fully AI-driven (no hardcoded fallback arrays)
- Matches conversation phase (choosing platform, approving design, etc.)
- Always includes "Something else — I'll describe it" as escape hatch
- Works for **ALL agents** (general, creative, sales, orders, etc.)

### 2. **Orchestrator: Attaches Suggestions to Response** (`orchestrator.py`)

```python
async def _finalize_turn(payload, user_message):
    sugs = await build_reply_suggestions(agent_id, user_message, reply)
    payload["reply_suggestions"] = sugs
    # Also attaches to messages_to_append for history
```

### 3. **API: Returns Suggestions in Response** (`routes.py`)

```json
{
  "reply": "Perfect — Zilo Starter it is. What vibe are we going for?",
  "reply_suggestions": [
    "Clean and professional",
    "Raw founder energy",
    "Bold and aggressive",
    "Something else — I'll describe it"
  ]
}
```

### 4. **Frontend: Renders as Buttons** (`AssistantChat.tsx`)

```tsx
{msg.suggestions?.map((chip) => (
  <button
    onClick={() => onSuggestionSend(chip)}
    className="rounded-xl border-2 border-brand/30 bg-white px-3.5 py-2.5..."
  >
    {chip}
  </button>
))}
```

**User clicks button** → Sends that text as their next message → Agent responds with new suggestions

---

## How Suggestions Are Generated

### The AI Prompt Logic

The suggestion generator matches the **exact phase** of the conversation:

| **Conversation Phase** | **Chips Generated** |
|------------------------|---------------------|
| Agent asks user to choose platform | `["Instagram", "Facebook", "TikTok", "Something else"]` |
| Agent shows 3 copy options (A/B/C) | `["Go with A — ...", "Go with B — ...", "Go with C — ...", "Try a different angle"]` |
| Agent shows a design image | `["Looks perfect, use it", "Change the headline", "Try different colors", "Different layout"]` |
| Agent asks a question | `[Likely answer 1, Likely answer 2, "Something else"]` |
| Agent gives pure data/analytics | `[]` (no chips — informational only) |

### The Golden Rule

**Always include a free-text escape option:**
- "Something else — I'll describe it"
- "Try a different angle"
- "None of these — I'll explain"

This prevents users from feeling trapped.

---

## Which Agents Get Suggestions

**ALL agents** now generate suggestions:

✅ General  
✅ Creative / Design  
✅ Meta Ads / Google Ads / X Ads  
✅ Social Media / Social Inbox / Social Scheduler  
✅ Sales / Customers / Orders  
✅ Broadcasts / Follow-ups / Bookings  
✅ Finance / Automations  
✅ Shopify (all sub-agents)  

Previously only 6 agents had this. Now it's universal.

---

## The Flow

```
User sends message
      ↓
Agent processes and responds
      ↓
Orchestrator calls build_reply_suggestions()
      ↓
AI generates 3-6 contextual chips
      ↓
Response includes reply + suggestions array
      ↓
Frontend renders buttons below message
      ↓
User clicks button OR types freely
      ↓
Either way — sends as normal message
      ↓
Loop continues
```

---

## Example Conversation

**User:** "Create an Instagram post"

**Agent:** "Perfect — what are we featuring?"

**Buttons:**
- 🛍️ Zilo Starter — AI CRM for small biz
- 📎 I have my own image
- 🎉 It's a promotion or offer
- ✏️ Something else — I'll describe it

**User clicks:** "Zilo Starter — AI CRM for small biz"

**Agent:** "Great choice. What vibe are we going for?"

**Buttons:**
- Clean and professional
- Raw founder energy
- Bold and aggressive
- Something else — I'll describe it

**User clicks:** "Raw founder energy"

**Agent:** "Love it. Here's the copy I'm thinking..."

---

## Configuration

### Enable/Disable for Specific Agents

Edit `interactive_suggestions.py`:

```python
AGENTS_WITH_SUGGESTION_CHIPS = frozenset({
    "general", "creative", "sales", ...
})
```

Remove an agent from this set to disable suggestions for it.

### Adjust Chip Generation

The AI prompt is in `build_reply_suggestions()` function. You can modify:
- Number of chips (currently 3-6)
- Max length (currently 90 chars)
- Tone/style
- Which phases get chips

### Frontend Styling

Buttons are styled in `AssistantChat.tsx`:

```tsx
className="rounded-xl border-2 border-brand/30 bg-white px-3.5 py-2.5 text-left text-[13px] font-medium leading-snug text-brand-ink shadow-sm transition hover:border-brand hover:bg-brand/10"
```

---

## Performance

- **LLM call:** Fast model (DeepSeek/GPT-4o-mini/Gemini Flash)
- **Timeout:** 10 seconds
- **Fallback:** If chip generation fails, conversation continues normally (no chips shown)
- **Cost:** ~$0.0001 per chip generation (negligible)

---

## Key Files

1. **`backend/assistant/interactive_suggestions.py`** — AI chip generator
2. **`backend/assistant/orchestrator.py`** — Calls chip generator in `_finalize_turn()`
3. **`backend/assistant/routes.py`** — Returns `reply_suggestions` in API response
4. **`web/components/AssistantChat.tsx`** — Renders buttons in UI
5. **`web/lib/api.ts`** — TypeScript types for `reply_suggestions`

---

## Result

Every agent response now includes contextual tap-to-send buttons that:
- Match the exact conversation phase
- Advance the conversation naturally
- Always include a free-text escape
- Never trap the user in a decision tree

The user can **always** type freely, but the buttons make common paths instant.

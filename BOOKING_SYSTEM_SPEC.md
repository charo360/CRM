# Multi-Business Type Support — Full Specification

> **Branch:** `booking-system`
> **Status:** Planning
> **Created:** March 10, 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [Business Types](#2-business-types)
3. [What Currently Exists (Retail/Shop)](#3-what-currently-exists)
4. [Database Schema Changes](#4-database-schema-changes)
5. [Backend API Endpoints](#5-backend-api-endpoints)
6. [AI Agent Changes](#6-ai-agent-changes)
7. [WhatsApp Customer Flows](#7-whatsapp-customer-flows)
8. [Frontend UI Changes](#8-frontend-ui-changes)
9. [Edge Cases & Business Rules](#9-edge-cases--business-rules)
10. [Implementation Phases](#10-implementation-phases)
11. [Testing Checklist](#11-testing-checklist)

---

## 1. Overview

### Goal
Transform the CRM from a retail-only system into a universal business platform. The business type determines what screens show, what AI says, and what WhatsApp flows customers experience.

### Core Principle
Same app, same codebase, different configuration per business type.

---

## 2. Business Types

### 2.1 Supported Types

| Code | Label | Catalog Label | Item Label | Primary Action | Secondary Action |
|------|-------|--------------|------------|----------------|------------------|
| `retail` | Shop / E-commerce | Products | Order | Order Now | Add to Cart |
| `salon` | Salon / Spa | Services | Appointment | Book Now | Check Availability |
| `restaurant` | Restaurant / Cafe | Menu | Order | Order Now | Reserve Table |
| `services` | Professional Services | Services | Booking | Book Consultation | Request Quote |
| `fitness` | Gym / Fitness | Classes | Booking | Book Class | View Schedule |
| `healthcare` | Healthcare | Services | Appointment | Book Appointment | Check Availability |
| `creator` | Creator / Digital | Content / Products | Order | Buy Now | Preview |

### 2.2 Business Type Details

#### RETAIL (Current — Already Built)
- **Use case:** Clothing shops, electronics stores, general e-commerce
- **Catalog:** Products with images, prices, stock status
- **Flow:** Browse → Select → Order/Add to Cart → Checkout → Payment
- **Features:** Cart, orders, payment tracking, inventory
- **WhatsApp actions:** 1) Order Now, 2) Add to Cart, 3) Ask Question, 4) Back to Catalog

#### SALON / SPA
- **Use case:** Hair salons, nail bars, spas, barbershops, beauty studios
- **Catalog:** Services with duration and price (e.g., "Haircut — 45min — $25")
- **Flow:** Browse services → Select → Pick date/time → Confirm booking
- **Features:** Appointment calendar, availability, staff assignment, reminders
- **WhatsApp actions:** 1) Book Now, 2) Check Availability, 3) Ask Question, 4) Back to Services

#### RESTAURANT / CAFE
- **Use case:** Restaurants, cafes, bakeries, catering, food trucks
- **Catalog:** Menu items grouped by category (Breakfast, Lunch, Drinks, etc.)
- **Flow:** Browse menu → Select items → Order for delivery/pickup OR Reserve table
- **Features:** Menu management, delivery orders, table reservations, order tracking
- **WhatsApp actions:** 1) Order Now, 2) Add to Cart, 3) Ask Question, 4) Back to Menu

#### PROFESSIONAL SERVICES
- **Use case:** Consultants, lawyers, accountants, tutors, coaches
- **Catalog:** Service packages with descriptions and pricing
- **Flow:** Browse → Select → Book consultation slot → Confirm
- **Features:** Consultation scheduling, quote requests, meeting reminders
- **WhatsApp actions:** 1) Book Session, 2) Request Quote, 3) Ask Question, 4) Back to Services

#### FITNESS
- **Use case:** Gyms, yoga studios, personal trainers, dance schools
- **Catalog:** Classes/sessions with schedule and capacity
- **Flow:** View schedule → Select class → Book spot → Confirm
- **Features:** Class schedule, capacity management, recurring bookings, reminders
- **WhatsApp actions:** 1) Book Class, 2) View Schedule, 3) Ask Question, 4) Back to Classes

#### HEALTHCARE
- **Use case:** Clinics, dentists, therapists, veterinarians
- **Catalog:** Services/specialties with duration and price
- **Flow:** Select service → Pick doctor/provider → Pick date/time → Confirm
- **Features:** Provider assignment, appointment management, patient notes, reminders
- **WhatsApp actions:** 1) Book Appointment, 2) Check Availability, 3) Ask Question, 4) Back to Services

#### CREATOR
- **Use case:** Content creators, digital product sellers, course creators, artists, musicians
- **Catalog:** Digital products, courses, subscriptions, commissions, merch
- **Flow:** Browse → Select → Buy/Download → Receive link or file
- **Features:** Digital delivery (links/files), subscriptions, commission requests
- **WhatsApp actions:** 1) Buy Now, 2) Preview, 3) Ask Question, 4) Back to Catalog
- **Special:** No physical shipping needed. Delivery = send download link or file via WhatsApp

---

## 3. What Currently Exists (Retail/Shop)

### 3.1 Already Built — No Changes Needed
These features work for ALL business types as-is:

- **Customer management** — contacts, customer list, profiles
- **Chat/messaging** — WhatsApp integration, conversation view
- **Broadcast system** — mass messaging with human-like delays
- **Follow-ups** — automated follow-up scheduling and reminders
- **AI auto-reply** — intent detection, conversation state, escalation
- **Business knowledge** — AI reads business info for context
- **Push notifications** — Expo push to business owner
- **Analytics** — daily analyzer, sales tracking
- **Account/Settings** — profile, subscription, WhatsApp connection

### 3.2 Retail-Specific Features (Already Built)
These are currently hardcoded for retail and need to be made conditional:

- **Products collection** — catalog of items with images, prices, stock
- **Product catalog modal** — frontend grid UI for managing products
- **Product actions** — Order Now, Add to Cart, Ask Question (customizable)
- **Cart system** — add to cart, view cart, checkout
- **Orders collection** — order creation, tracking, payment status
- **Order confirmation flow** — YES/NO confirmation with order number
- **Payment tracking** — Unpaid/Partial/Paid status, payment screenshots
- **Sales agent** — handles catalog requests, product questions, negotiations
- **WhatsApp product showcase** — sends product image + action buttons
- **Catalog pagination** — 8 items per page with "See more" option

### 3.3 What Needs to Change
- Products screen → **Offerings screen** (shows Products OR Services depending on type)
- Orders screen → **Orders/Bookings screen** (shows orders OR appointments)
- Sales tab stats → **Adapt labels** per business type
- AI agent → **Route to correct handler** based on business type
- WhatsApp actions → **Dynamic per business type**

---

## 4. Database Schema Changes

### 4.1 Users Collection — New Settings Fields

```
user.settings.business_type       : string   — "retail" | "salon" | "restaurant" | "services" | "fitness" | "healthcare" | "creator"
user.settings.business_hours      : object   — { "mon": {"open": "09:00", "close": "18:00", "closed": false}, ... }
user.settings.booking_settings    : object   — (see below)
```

**booking_settings sub-document:**
```
{
  "duration_default": 60,           // default appointment duration in minutes
  "buffer_minutes": 15,             // gap between appointments
  "advance_days": 30,               // how far ahead customers can book
  "cancellation_hours": 24,         // min hours before appt to allow cancel
  "auto_confirm": false,            // true = instant confirm, false = owner approves
  "reminder_hours": 24,             // send reminder X hours before appointment
  "allow_walk_ins": true,           // accept unscheduled visits
  "max_daily_bookings": null,       // null = unlimited
  "working_days": ["mon","tue","wed","thu","fri","sat"]
}
```

### 4.2 Services Collection (New)

For salon, restaurant, services, fitness, healthcare, creator:

```
{
  "_id": "uuid",
  "user_id": "business_owner_id",
  "name": "Haircut & Styling",
  "description": "Professional haircut with wash and blow-dry",
  "price": 2500,
  "duration": 45,                    // minutes (null for retail/creator)
  "category": "Hair",               // grouping
  "image_url": "https://...",
  "images": [],
  "available": true,                 // equivalent to in_stock
  "requires_staff": true,           // needs specific staff member
  "max_concurrent": 1,              // how many can happen at same time
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

**For CREATOR type specifically:**
```
{
  ... (same as above) ...
  "digital": true,                   // flag for digital product
  "download_url": "https://...",     // link sent after purchase
  "file_type": "pdf",               // pdf, video, audio, image, link
  "preview_url": "https://...",     // free preview link
}
```

**Decision: Reuse `products` collection or create separate `services`?**
→ **REUSE `products` collection.** Add a `type` field:
- `type: "product"` — physical product (retail)
- `type: "service"` — service/appointment (salon, healthcare, etc.)
- `type: "menu_item"` — restaurant menu item
- `type: "class"` — fitness class
- `type: "digital"` — digital product (creator)

This means:
- Same CRUD endpoints work
- Same catalog modal works (with conditional fields)
- Same AI product injection works
- Just add `duration`, `digital`, `download_url`, `preview_url`, `max_concurrent`, `requires_staff` fields

### 4.3 Bookings Collection (New)

```
{
  "_id": "uuid",
  "user_id": "business_owner_id",
  "customer_id": "customer_uuid",
  "customer_name": "Jane Doe",
  "customer_phone": "+254...",
  "booking_number": "BK-A1B2C3",    // short reference like ORD-XXXXXX
  "service_id": "product/service uuid",
  "service_name": "Haircut & Styling",
  "staff_id": null,                  // optional: assigned staff member
  "staff_name": null,
  "date": "2026-03-15",             // appointment date
  "time": "10:00",                  // appointment start time
  "end_time": "10:45",              // calculated from duration
  "duration": 45,                   // minutes
  "status": "pending",              // pending | confirmed | completed | cancelled | no_show
  "price": 2500,
  "payment_status": "unpaid",       // unpaid | partial | paid
  "notes": "",                      // customer notes or special requests
  "reminder_sent": false,
  "created_at": "datetime",
  "updated_at": "datetime",
  "cancelled_at": null,
  "cancellation_reason": null
}
```

**Booking statuses:**
- `pending` — customer booked, waiting for owner confirmation (if auto_confirm=false)
- `confirmed` — appointment confirmed
- `completed` — appointment done
- `cancelled` — cancelled by customer or owner
- `no_show` — customer didn't show up

### 4.4 Staff Collection (New — Phase 2, Optional)

```
{
  "_id": "uuid",
  "user_id": "business_owner_id",
  "name": "Sarah",
  "role": "Stylist",
  "services": ["service_id_1", "service_id_2"],  // what they can do
  "working_hours": { "mon": {"start": "09:00", "end": "17:00"}, ... },
  "active": true,
  "created_at": "datetime"
}
```

**Note:** Staff is OPTIONAL for Phase 1. Many small salons are owner-only. We can add staff management later.

### 4.5 Availability Slots (Computed, Not Stored)

We do NOT store available slots. We compute them on-the-fly:
1. Get business hours for the requested day
2. Get all confirmed bookings for that day
3. Subtract booked times from business hours
4. Apply buffer_minutes between slots
5. Return available time windows

This avoids stale data and complex slot management.

---

## 5. Backend API Endpoints

### 5.1 Existing Endpoints — Changes Needed

#### `GET /products` & `POST /products`
- Add `type` field support ("product", "service", "menu_item", "class", "digital")
- Add `duration`, `requires_staff`, `max_concurrent`, `digital`, `download_url`, `preview_url` fields
- Filter by type based on business_type if needed
- **No breaking changes** — existing retail products keep working (default type="product")

#### `PUT /settings`
- Accept new fields: `business_type`, `business_hours`, `booking_settings`

#### `GET /settings`
- Return new fields so frontend can configure UI

### 5.2 New Endpoints

#### Bookings CRUD:
```
POST   /bookings                    — Create a new booking
GET    /bookings                    — List bookings (with filters: date, status, staff)
GET    /bookings/{id}               — Get single booking
PUT    /bookings/{id}/status        — Update status (confirm, complete, cancel, no_show)
PUT    /bookings/{id}               — Update booking details (reschedule)
DELETE /bookings/{id}               — Cancel/delete booking
```

#### Availability:
```
GET    /availability?date=2026-03-15&service_id=xxx  — Get available time slots for a date
GET    /availability/week?start=2026-03-15           — Get availability for a whole week
```

#### Business Hours:
```
GET    /business-hours              — Get current business hours
PUT    /business-hours              — Update business hours
```

#### Staff (Phase 2):
```
POST   /staff                       — Add staff member
GET    /staff                       — List staff
PUT    /staff/{id}                  — Update staff
DELETE /staff/{id}                  — Remove staff
```

### 5.3 Endpoint Details

#### `POST /bookings`
**Request:**
```json
{
  "service_id": "uuid",
  "customer_id": "uuid",
  "date": "2026-03-15",
  "time": "10:00",
  "notes": "Prefer short style",
  "staff_id": null
}
```
**Logic:**
1. Validate service exists and is available
2. Check time slot is not already booked (overlap check)
3. Check within business hours
4. Check within advance_days limit
5. Generate booking_number (BK-XXXXXX)
6. Create booking with status = "confirmed" (if auto_confirm) or "pending"
7. Send WhatsApp confirmation to customer
8. Send push notification to owner
9. Return booking doc

#### `GET /availability?date=2026-03-15&service_id=xxx`
**Logic:**
1. Get service duration
2. Get business hours for that weekday
3. Get all bookings for that date (status = pending or confirmed)
4. Generate available slots from open to close, skipping occupied + buffer
5. Return array of `{"time": "10:00", "end_time": "10:45"}`

**Response:**
```json
{
  "date": "2026-03-15",
  "day": "Saturday",
  "business_hours": {"open": "09:00", "close": "18:00"},
  "available_slots": [
    {"time": "09:00", "end_time": "09:45"},
    {"time": "10:00", "end_time": "10:45"},
    {"time": "11:00", "end_time": "11:45"},
    {"time": "14:00", "end_time": "14:45"}
  ],
  "booked_slots": [
    {"time": "12:00", "end_time": "13:30", "service": "Full Treatment"}
  ]
}
```

---

## 6. AI Agent Changes

### 6.1 Intent Analyzer Updates

**File: `agents/intent_analyzer.py`**

Add booking-related intents to the analyzer:
- `BOOKING_REQUEST` — customer wants to book an appointment
- `AVAILABILITY_CHECK` — customer asks about available times
- `BOOKING_STATUS` — customer asks about existing booking
- `BOOKING_CANCEL` — customer wants to cancel
- `BOOKING_RESCHEDULE` — customer wants to change date/time
- `SCHEDULE_VIEW` — customer wants to see class schedule (fitness)

### 6.2 New Agent: BookingAgent

**File: `agents/booking_agent.py`**

Handles all booking-related intents for non-retail business types.

**Methods:**
- `_handle_booking_request()` — start booking flow, ask for preferred date/time
- `_handle_availability_check()` — show available slots for requested date
- `_handle_booking_status()` — look up customer's bookings
- `_handle_booking_cancel()` — process cancellation request
- `_handle_booking_reschedule()` — process reschedule request

**Booking conversation flow:**
```
Customer: "I want to book a haircut"
AI: "Great! Here are our hair services:
     1. Haircut — 45min — $25
     2. Haircut & Styling — 60min — $40
     3. Hair Coloring — 90min — $80
     Reply with a number to select"

Customer: "1"
AI: "Haircut — 45min — $25
     When would you like to come in?
     
     Available this week:
     Mon 15 Mar: 9:00, 10:00, 11:00, 14:00, 15:00
     Tue 16 Mar: 9:00, 10:00, 14:00
     Wed 17 Mar: 9:00, 11:00, 13:00, 15:00
     
     Reply with your preferred date and time (e.g., 'Mon 10:00')"

Customer: "Mon 10"
AI: "Please confirm your booking:
     
     Service: Haircut
     Date: Monday, March 15
     Time: 10:00 AM - 10:45 AM
     Price: $25
     
     1️⃣ Confirm Booking
     2️⃣ Change Time
     3️⃣ Cancel
     
     Reply with a number"

Customer: "1"
AI: "Your booking is confirmed!
     
     Booking #BK-X7K2M9
     Service: Haircut
     Date: Monday, March 15 at 10:00 AM
     
     You'll receive a reminder 24 hours before.
     To cancel or reschedule, just message us!"
```

### 6.3 Router Updates

**File: `agents/router.py`**

Add business type awareness:
```python
business_type = context.get("business_type", "retail")

if intent in ("BOOKING_REQUEST", "AVAILABILITY_CHECK", "BOOKING_STATUS", 
              "BOOKING_CANCEL", "BOOKING_RESCHEDULE"):
    if business_type != "retail":
        return await booking_agent.process(intent, context)
    else:
        # Retail doesn't have bookings — treat as general inquiry
        return await chat_agent.process(intent, context)
```

### 6.4 Sales Agent Updates

**File: `agents/sales_agent.py`**

- `_handle_catalog_request()` — already paginated. Just change labels:
  - Retail: "Here are our products"
  - Salon: "Here are our services"
  - Restaurant: "Here's our menu"
  - Creator: "Here's what we offer"
- Product showcase actions — already dynamic via `product_actions` setting

### 6.5 Creator-Specific Handling

For `creator` business type:
- After purchase confirmation, immediately send download link via WhatsApp
- No shipping/delivery tracking needed
- Preview action sends `preview_url` to customer
- Support file attachments (PDF, images, audio) via Evolution API media send

---

## 7. WhatsApp Customer Flows

### 7.1 Retail Flow (Existing)
```
Customer says "products" / "catalog" / "what do you sell"
→ AI sends paginated product list (8 per page)
→ Customer picks number
→ Product detail + 4 options (Order, Cart, Ask, Back)
→ "1" Order Now → quantity → confirm YES/NO → order created → payment request
→ "2" Add to Cart → added → keep shopping or checkout
→ "4" Back to Catalog → catalog list again
```

### 7.2 Salon Flow (New)
```
Customer says "services" / "book" / "appointment" / "what services do you offer"
→ AI sends paginated service list (8 per page)
→ Customer picks number
→ Service detail + 4 options (Book Now, Check Availability, Ask, Back)
→ "1" Book Now → show available dates/times → customer picks → confirm → booking created → reminder scheduled
→ "2" Check Availability → show available slots for next 3 days
→ "4" Back to Services → service list again
```

### 7.3 Restaurant Flow (New)
```
Customer says "menu" / "what food" / "order food"
→ AI sends paginated menu (8 per page, grouped by category)
→ Customer picks number
→ Item detail + 4 options (Order, Add to Cart, Ask, Back)
→ Same as retail but with "Delivery or Pickup?" question after order
```

### 7.4 Creator Flow (New)
```
Customer says "products" / "what do you have" / "courses"
→ AI sends paginated catalog (8 per page)
→ Customer picks number
→ Product detail + 4 options (Buy Now, Preview, Ask, Back)
→ "1" Buy Now → confirm → order created → payment request → after payment: send download link
→ "2" Preview → send preview_url or sample file
→ "4" Back to Catalog
```

### 7.5 Booking Date/Time Selection (WhatsApp UX)

Since WhatsApp doesn't have a date picker, use text-based selection:

**Step 1 — Show available dates:**
```
📅 Available dates for Haircut:

1️⃣  Mon, Mar 15 — 5 slots available
2️⃣  Tue, Mar 16 — 3 slots available
3️⃣  Wed, Mar 17 — 4 slots available
4️⃣  Thu, Mar 18 — 6 slots available
5️⃣  Fri, Mar 19 — 2 slots available
6️⃣  ➡️  See next week

Reply with a number
```

**Step 2 — Show available times for selected date:**
```
⏰ Available times for Mon, Mar 15:

1️⃣  9:00 AM
2️⃣  10:00 AM
3️⃣  11:00 AM
4️⃣  2:00 PM
5️⃣  3:00 PM
6️⃣  🔙 Pick different date

Reply with a number
```

**Step 3 — Confirm:**
```
✅ Please confirm your booking:

📋 Service: Haircut
📅 Date: Monday, March 15
⏰ Time: 10:00 AM - 10:45 AM
💰 Price: $25

1️⃣  ✅ Confirm Booking
2️⃣  🔄 Change Time
3️⃣  ❌ Cancel

Reply with a number
```

### 7.6 Booking Reminders (Automated)

24 hours before appointment, send:
```
⏰ Reminder: You have an appointment tomorrow!

📋 Service: Haircut
📅 Date: Tuesday, March 16
⏰ Time: 10:00 AM
📍 Location: [business address from business_knowledge]

Booking #BK-X7K2M9

To cancel, reply "cancel booking" or "cancel BK-X7K2M9"
```

---

## 8. Frontend UI Changes

### 8.1 Account Settings — Business Type Selector

**Location:** Account tab → Settings section (at the top)

```
Business Type
┌──────────────────────────┐
│ 🛍️  Shop / E-commerce    │  ← current default
│ 💇  Salon / Spa          │
│ 🍽️  Restaurant / Cafe    │
│ 💼  Professional Services │
│ 🏋️  Gym / Fitness        │
│ 🏥  Healthcare           │
│ 🎨  Creator / Digital    │
└──────────────────────────┘
```

When changed:
- Update `user.settings.business_type` via API
- Refresh all screens to show correct labels
- Show/hide booking-specific settings (business hours, booking settings)

### 8.2 Conditional Tab Labels

| Tab | Retail | Salon | Restaurant | Creator |
|-----|--------|-------|------------|---------|
| Tab 1 | Customers | Customers | Customers | Customers |
| Tab 2 | Products | Services | Menu | Products |
| Tab 3 | Sales | Appointments | Orders | Sales |
| Tab 4 | Broadcast | Broadcast | Broadcast | Broadcast |
| Tab 5 | Follow-ups | Follow-ups | Follow-ups | Follow-ups |

### 8.3 Products/Services Screen Changes

**For Retail (no change):**
- Product grid with images, prices, stock badges
- Add/Edit product modal with image upload

**For Salon/Spa/Healthcare/Services/Fitness:**
- Service list showing: name, duration, price, availability
- Add/Edit service modal with: name, description, price, duration, category, images
- Duration picker (15min increments: 15, 30, 45, 60, 90, 120)

**For Restaurant:**
- Menu items grouped by category tabs
- Add/Edit item modal: name, description, price, category, images

**For Creator:**
- Product grid (similar to retail)
- Add/Edit modal adds: download URL, preview URL, file type
- "Digital" badge instead of "In Stock"

### 8.4 Orders/Bookings Screen Changes

**For Retail (no change):**
- Order list with order number, customer, total, payment status
- Order detail: items, payment status, payment proof images

**For Booking-Based Types (salon, healthcare, services, fitness):**
- Appointment list with: booking number, customer, service, date, time, status
- Status badges: Pending (yellow), Confirmed (blue), Completed (green), Cancelled (red), No Show (gray)
- Quick actions: Confirm, Complete, Cancel, No Show
- Optional: Calendar view toggle (list view ↔ calendar view)
- Filter by: date range, status, service, staff

**For Restaurant:**
- Hybrid: Orders list (delivery) + Reservations list (dine-in)
- Tab toggle: "Delivery Orders" | "Reservations"

### 8.5 Business Hours Settings (New — Booking Types Only)

Show only when business_type is NOT "retail" or "creator":

```
Business Hours
┌─────────────────────────────────────┐
│ Monday      09:00 — 18:00    [✓]   │
│ Tuesday     09:00 — 18:00    [✓]   │
│ Wednesday   09:00 — 18:00    [✓]   │
│ Thursday    09:00 — 18:00    [✓]   │
│ Friday      09:00 — 18:00    [✓]   │
│ Saturday    09:00 — 14:00    [✓]   │
│ Sunday      Closed           [ ]   │
└─────────────────────────────────────┘

Booking Settings
┌─────────────────────────────────────┐
│ Default duration:  60 min          │
│ Buffer between:    15 min          │
│ Book up to:        30 days ahead   │
│ Cancel before:     24 hours        │
│ Auto-confirm:      [ ] Yes         │
│ Send reminder:     24 hours before │
└─────────────────────────────────────┘
```

### 8.6 Stats/Analytics Adaptation

**Sales tab header stats:**

| Stat | Retail | Salon | Restaurant | Creator |
|------|--------|-------|------------|---------|
| Stat 1 | Revenue | Revenue | Revenue | Revenue |
| Stat 2 | Orders | Appointments | Orders | Sales |
| Stat 3 | Products Sold | Services Done | Items Sold | Downloads |
| Stat 4 | Avg Order | Avg Booking | Avg Order | Avg Sale |

---

## 9. Edge Cases & Business Rules

### 9.1 Booking Conflicts
- **Double booking prevention:** Before confirming, check no overlap with existing bookings + buffer
- **Concurrent services:** Some services allow multiple concurrent bookings (e.g., gym class with 20 spots)
- **Use `max_concurrent` field:** If > 1, allow that many bookings in same slot

### 9.2 Cancellation Rules
- Customer can cancel if `current_time < booking_time - cancellation_hours`
- Late cancellations: notify owner, mark as "cancelled_late"
- Owner can always cancel (send apology message to customer)
- Cancelled bookings free up the time slot immediately

### 9.3 Business Type Switching
- User changes from "retail" to "salon":
  - Existing products remain in DB (just hidden from new service view)
  - Orders remain accessible
  - New "services" and "bookings" features appear
- User changes back from "salon" to "retail":
  - Services remain but hidden
  - Bookings remain accessible
  - Product view returns
- **No data loss on type switch**

### 9.4 Timezone Handling
- Store all times in UTC in database
- Display in user's timezone (from browser/device)
- WhatsApp messages show times in business timezone
- Use `user.settings.timezone` (default to UTC if not set)

### 9.5 Creator Digital Delivery
- After payment confirmed (screenshot received or status changed to "Paid"):
  - Automatically send download link via WhatsApp
  - Message: "Thank you for your purchase! Here's your download: [link]"
  - If file (PDF, image), send as media attachment
- Preview: send preview_url without requiring payment

### 9.6 Reminders
- Run a background task every 15 minutes checking for upcoming bookings
- Send reminder at configured `reminder_hours` before appointment
- Mark `reminder_sent = true` to avoid duplicates
- Only send for `status = confirmed` bookings

### 9.7 Walk-ins (Salon/Healthcare)
- Owner can create booking from app with "now" as time
- Status goes directly to "confirmed"
- Useful for tracking walk-in revenue and service history

---

## 10. Implementation Phases

### Phase 1: Backend Foundation (3-4 days)
- [ ] Add `business_type` to user settings model + PUT/GET endpoints
- [ ] Add `type`, `duration`, `requires_staff`, `max_concurrent`, `digital`, `download_url`, `preview_url` fields to products collection
- [ ] Create `bookings` collection with indexes
- [ ] Build booking CRUD endpoints (POST, GET, PUT status, DELETE)
- [ ] Build availability computation endpoint (GET /availability)
- [ ] Add `business_hours` and `booking_settings` to user settings
- [ ] Add booking number generation (BK-XXXXXX)
- [ ] Startup migration: set existing users to `business_type: "retail"`, set existing products to `type: "product"`

### Phase 2: AI Agent — BookingAgent (3-4 days)
- [ ] Create `agents/booking_agent.py` with all booking intents
- [ ] Update `agents/intent_analyzer.py` with booking-related intents
- [ ] Update `agents/router.py` to dispatch booking intents based on business_type
- [ ] Update `agents/sales_agent.py` catalog labels based on business_type
- [ ] Build WhatsApp booking flow: date selection → time selection → confirmation
- [ ] Store booking conversation state in `pending_catalogs` or `conversation_states`
- [ ] Handle booking cancellation and rescheduling via WhatsApp

### Phase 3: Frontend — Business Type + Services UI (4-5 days)
- [ ] Add business type selector to Account settings
- [ ] Make tab labels dynamic based on business_type
- [ ] Add duration field to product/service creation modal (conditional)
- [ ] Add digital product fields to creation modal (for creator type)
- [ ] Build bookings/appointments list screen
- [ ] Add booking detail view with status management (confirm/complete/cancel)
- [ ] Add business hours settings UI (for booking-based types)
- [ ] Add booking settings UI (duration, buffer, advance days, etc.)
- [ ] Adapt stats labels per business type

### Phase 4: WhatsApp Booking Flow (3-4 days)
- [ ] Implement date selection via numbered list in WhatsApp
- [ ] Implement time slot selection via numbered list
- [ ] Implement booking confirmation with YES/NO
- [ ] Send booking confirmation message with booking number
- [ ] Handle "cancel booking" keywords in webhook
- [ ] Handle "reschedule" keywords in webhook
- [ ] Digital delivery: auto-send download link after payment (creator)

### Phase 5: Reminders + Polish (2-3 days)
- [ ] Build booking reminder background task (runs every 15 min)
- [ ] Send WhatsApp reminder 24h before appointment
- [ ] Handle no-show marking (manual by owner)
- [ ] Calendar view toggle on bookings screen (optional, time permitting)
- [ ] Test all 7 business types end-to-end
- [ ] Fix edge cases from testing
- [ ] Update AI prompts for each business type personality

### Total Estimated: 15-20 days

---

## 11. Testing Checklist

### Backend Tests
- [ ] Create user with each business type → verify settings saved
- [ ] Create service with duration → verify stored correctly
- [ ] Create booking → verify booking_number generated
- [ ] Create booking at occupied slot → verify rejected
- [ ] Create booking outside business hours → verify rejected
- [ ] Create booking beyond advance_days → verify rejected
- [ ] Get availability → verify correct slots returned
- [ ] Get availability with existing bookings → verify occupied slots excluded
- [ ] Cancel booking → verify slot freed
- [ ] Cancel booking too late → verify cancellation_hours enforced
- [ ] Confirm booking → verify status updated + customer notified
- [ ] Complete booking → verify status updated
- [ ] Business type switch → verify no data loss

### WhatsApp Flow Tests
- [ ] Customer asks for services → receives service list (salon)
- [ ] Customer asks for menu → receives menu (restaurant)
- [ ] Customer selects service → sees date options
- [ ] Customer selects date → sees time slots
- [ ] Customer selects time → sees confirmation
- [ ] Customer confirms → booking created + confirmation sent
- [ ] Customer cancels booking → booking cancelled + confirmation
- [ ] Customer asks about booking status → receives status
- [ ] Creator: customer buys → payment → receives download link
- [ ] Reminder sent 24h before → verify message received

### Frontend Tests
- [ ] Business type selector shows in settings
- [ ] Changing type updates tab labels
- [ ] Services screen shows duration for salon type
- [ ] Menu screen shows categories for restaurant type
- [ ] Creator screen shows download URL field
- [ ] Bookings list shows correct status badges
- [ ] Quick actions work (confirm, complete, cancel)
- [ ] Business hours UI saves correctly
- [ ] Booking settings UI saves correctly
- [ ] Stats labels match business type

---

## Appendix: Business Type → Action Button Mapping

```
RETAIL:
  1) Order Now        → action_type: "order"
  2) Add to Cart      → action_type: "add_to_cart"
  3) Ask a Question   → action_type: "ask"
  4) Back to Catalog  → action_type: "back"

SALON / HEALTHCARE / SERVICES / FITNESS:
  1) Book Now         → action_type: "book"
  2) Check Availability → action_type: "availability"
  3) Ask a Question   → action_type: "ask"
  4) Back to Services → action_type: "back"

RESTAURANT:
  1) Order Now        → action_type: "order"
  2) Add to Cart      → action_type: "add_to_cart"
  3) Ask a Question   → action_type: "ask"
  4) Back to Menu     → action_type: "back"

CREATOR:
  1) Buy Now          → action_type: "order"
  2) Preview          → action_type: "preview"
  3) Ask a Question   → action_type: "ask"
  4) Back to Catalog  → action_type: "back"
```

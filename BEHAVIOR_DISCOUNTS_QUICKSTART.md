# Behavior-Triggered Discounts - Quick Start Guide

## 🚀 What You Just Got

A complete system that automatically sends personalized discounts to website visitors based on their behavior. This is one of the most powerful conversion tools you can have!

---

## 📊 How It Works

```
Visitor browses website → GA4 tracks behavior → Trigger detected → Discount sent → Conversion! 💰
```

---

## ✅ What's Included

### 1. **Backend System** (`backend/marketing/`)
- ✅ `behavior_triggers.py` - Core trigger engine
- ✅ `discount_routes.py` - API endpoints
- ✅ Routes mounted at `/api/marketing/behavior-discounts/*`

### 2. **Admin Dashboard** (`web/app/dashboard/marketing/behavior-discounts/`)
- ✅ Create/edit campaigns
- ✅ Real-time analytics
- ✅ Performance tracking
- ✅ Campaign management

### 3. **Tracking System**
- ✅ `GA4BehaviorTracker.tsx` - React component
- ✅ `zilo-behavior-tracker.js` - Standalone JavaScript
- ✅ Tracks 8 different trigger events

### 4. **Discount Widget**
- ✅ `BehaviorDiscountWidget.tsx` - Beautiful popup
- ✅ Auto-displays offers
- ✅ Copy-paste discount codes

---

## 🎯 8 Trigger Events Available

1. **🛒 Cart Abandoned** - 25-30% recovery rate
2. **👀 Product Browsing** - Views product multiple times
3. **🔄 Returning Visitor** - Rewards loyalty
4. **⏱️ Time on Site** - Engaged visitors (2+ minutes)
5. **📄 Page Views** - Multiple pages viewed
6. **🚪 Exit Intent** - About to leave
7. **🆕 First-Time Visitor** - Welcome offer
8. **💎 High-Value Visitor** - Viewing expensive products

---

## 🎨 5 Delivery Methods

- **📧 Email** - Professional, detailed (needs email)
- **📱 SMS** - Instant, 98% open rate (needs phone)
- **💬 WhatsApp** - Personal, conversational (needs phone)
- **🎯 Popup** - Immediate on-site (no contact needed)
- **🎨 Banner** - Subtle top banner (no contact needed)

---

## 🚀 Quick Setup (5 Minutes)

### Step 1: Access the Dashboard
```
Go to: Dashboard → Marketing → Behavior Discounts
```

### Step 2: Create Your First Campaign
Click **"Create Campaign"** and fill in:

**Example: Cart Abandonment Recovery**
- **Name:** Cart Recovery 15% Off
- **Trigger:** Cart Abandoned
- **Discount:** 15% off
- **Delivery:** Popup
- **Message:** "Come back! Use code {discount_code} for {discount_value}% off your order!"

### Step 3: Add Tracking to Your Website

**For Shopify/Wix/WordPress/Custom Sites:**

Add this code to your website (after GA4 tracking code):

```html
<script src="https://yourdomain.com/tracking/zilo-behavior-tracker.js"></script>
<script>
  ZiloBehaviorTracker.init({
    businessId: 'YOUR_BUSINESS_ID', // Get from Zilo dashboard
    apiUrl: 'https://crm.zilo.pro/api'
  });
</script>
```

**For Zilo-Hosted Blogs:**
Already integrated! No code needed.

### Step 4: Test It!
1. Visit your website
2. Add item to cart
3. Wait 5 minutes
4. See the discount popup! 🎉

---

## 📈 Expected Results

Based on industry benchmarks:

| Trigger | Conversion Rate | Use Case |
|---------|----------------|----------|
| Cart Abandoned | 25-30% | E-commerce |
| Exit Intent | 10-15% | All sites |
| First-Time Visitor | 15-20% | New customers |
| Product Browsing | 5-10% | High-consideration |
| Time on Site | 8-12% | Engaged visitors |

**Average ROI:** 300-500% return on discount investment

---

## 🎯 Campaign Templates

### Template 1: Cart Recovery
```
Trigger: Cart Abandoned
Condition: Cart value > $30
Discount: 15% off
Delivery: Email
Message: "Don't forget your items! Complete your order and save 15% with code {discount_code}"
```

### Template 2: Exit Intent Saver
```
Trigger: Exit Intent
Condition: None
Discount: Free Shipping
Delivery: Popup
Message: "Wait! Don't leave yet! Get FREE SHIPPING with code {discount_code}"
```

### Template 3: First-Time Welcome
```
Trigger: First-Time Visitor
Condition: 3+ pages viewed
Discount: 10% off
Delivery: Popup
Message: "Welcome! Get 10% off your first order with code {discount_code}"
```

### Template 4: High-Value Incentive
```
Trigger: High-Value Visitor
Condition: Product price > $100
Discount: $20 off
Delivery: Email
Message: "Still thinking? Here's $20 off to help you decide! Use code {discount_code}"
```

---

## 🔧 API Endpoints

All endpoints are at `/api/marketing/behavior-discounts/`

### Campaign Management
- `POST /campaigns` - Create campaign
- `GET /campaigns` - List all campaigns
- `GET /campaigns/{id}` - Get campaign details
- `PUT /campaigns/{id}` - Update campaign
- `DELETE /campaigns/{id}` - Delete campaign

### Tracking
- `POST /track/{business_id}` - Track visitor event
- `GET /check` - Check for pending offers
- `POST /mark-shown` - Mark offer as shown

### Analytics
- `GET /analytics` - Get all campaign analytics
- `GET /campaigns/{id}/performance` - Get campaign performance

### Validation
- `POST /validate` - Validate discount code
- `POST /apply` - Apply discount code (track conversion)

---

## 💡 Pro Tips

### 1. **Start Small**
Begin with 1-2 campaigns (cart abandonment + exit intent)

### 2. **Test Different Offers**
Try 10%, 15%, 20% to find the sweet spot

### 3. **Use Conditions**
Add minimum cart value to protect margins

### 4. **Monitor Performance**
Check analytics weekly, pause low performers

### 5. **Don't Over-Discount**
Start at 10-15%, not 50%

### 6. **Create Urgency**
"Limited time" or "Expires in 7 days"

### 7. **A/B Test**
Run multiple campaigns with different offers

### 8. **Segment by Behavior**
Different offers for different visitor types

---

## 🎨 Customization

### Change Popup Design
Edit `web/components/marketing/BehaviorDiscountWidget.tsx`

### Add New Trigger Events
Edit `backend/marketing/behavior_triggers.py` → `TriggerEvent` enum

### Customize Tracking
Edit `web/public/tracking/zilo-behavior-tracker.js`

---

## 📊 Viewing Analytics

Go to: **Dashboard → Marketing → Behavior Discounts**

You'll see:
- **Discounts Sent** - Total offers sent
- **Conversions** - How many were used
- **Conversion Rate** - % of offers that converted
- **Revenue Generated** - Total sales from discounts

For each campaign:
- Sent count
- Conversion count
- Conversion rate
- Revenue impact

---

## 🔐 Privacy & Compliance

### GDPR (Europe)
- Add cookie consent banner
- Allow users to opt-out
- Update privacy policy

### CAN-SPAM (Email)
- Include unsubscribe link
- Use real business address
- Honor opt-outs within 10 days

### TCPA (SMS/WhatsApp)
- Get explicit consent
- Provide opt-out instructions
- Keep consent records

---

## 🐛 Troubleshooting

### Discounts Not Triggering?
1. Check campaign is active
2. Verify GA4 is tracking events
3. Check visitor hasn't received offer recently (30-day cooldown)
4. Verify conditions are met (cart value, page views, etc.)

### Popup Not Showing?
1. Check browser console for errors
2. Verify tracking script is loaded
3. Check visitor ID is being generated
4. Test with different browser/incognito mode

### Low Conversion Rate?
1. Try different discount amounts
2. Test different delivery methods
3. Adjust trigger conditions
4. Improve message copy

---

## 📚 Documentation

- **Full Guide:** `/docs/behavior-discount-guide.md`
- **GA4 Setup:** `/docs/ga4-universal-setup.md`
- **API Docs:** Check backend routes

---

## 🎉 Success Metrics

Track these KPIs:

1. **Discount Send Rate** - How many visitors trigger offers
2. **Conversion Rate** - % who use the code
3. **Revenue per Discount** - Average order value
4. **ROI** - Revenue vs. discount cost
5. **Time to Conversion** - How fast they buy

---

## 🚀 Next Steps

1. ✅ Create your first campaign
2. ✅ Add tracking code to your website
3. ✅ Test the flow end-to-end
4. ✅ Monitor performance for 7 days
5. ✅ Optimize based on data
6. ✅ Scale successful campaigns

---

## 💰 Expected Impact

**Conservative Estimate:**
- 1000 monthly visitors
- 5% trigger rate = 50 offers sent
- 20% conversion rate = 10 sales
- $50 average order value = $500 revenue
- 15% discount cost = $75
- **Net profit: $425/month**

**Scale this up with more traffic!**

---

## 🎯 Your First Campaign Checklist

- [ ] Access Dashboard → Marketing → Behavior Discounts
- [ ] Click "Create Campaign"
- [ ] Choose trigger event (start with Cart Abandoned)
- [ ] Set discount (15% off)
- [ ] Choose delivery method (Popup)
- [ ] Write message
- [ ] Activate campaign
- [ ] Add tracking code to website
- [ ] Test by triggering the event
- [ ] Monitor analytics

---

## 🔥 This Feature Will...

✅ **Recover abandoned carts** (25-30% recovery rate)  
✅ **Reduce bounce rate** (exit intent popups)  
✅ **Increase conversions** (15-20% boost)  
✅ **Build email/SMS list** (collect contacts)  
✅ **Reward loyal customers** (returning visitor offers)  
✅ **Boost average order value** (strategic discounting)  
✅ **Generate revenue automatically** (set and forget)  

---

**Ready to start converting browsers into buyers? Create your first campaign now!** 🚀

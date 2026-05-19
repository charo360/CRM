# Behavior-Triggered Discount Campaigns

## Overview

Automatically send personalized discounts to website visitors based on their behavior. Turn browsers into buyers with smart, timely offers!

---

## How It Works

```
Visitor browses your website
        ↓
GA4 tracks their behavior
        ↓
Zilo detects trigger event
        ↓
Automatic discount sent
        ↓
Visitor converts! 🎉
```

---

## Trigger Events

### 🛒 **Cart Abandoned**
Send a discount when someone adds items to cart but doesn't checkout.

**Example:** "Come back! Here's 15% off to complete your order"

**Best for:** E-commerce stores, high-value products

---

### 👀 **Product Browsing**
Trigger when someone views a product multiple times without buying.

**Example:** "Still thinking? Here's 10% off that item you love!"

**Best for:** Fashion, electronics, furniture

---

### 🔄 **Returning Visitor**
Reward customers who come back to your site.

**Example:** "Welcome back! Enjoy 20% off as a thank you"

**Best for:** Building loyalty, repeat purchases

---

### ⏱️ **Time on Site**
Send offers to engaged visitors who spend significant time browsing.

**Example:** "You've been browsing for 5 minutes - here's a special offer!"

**Best for:** High-consideration purchases

---

### 📄 **Page Views Threshold**
Trigger after someone views multiple pages.

**Example:** "Viewed 5+ pages? Here's 15% off your first order!"

**Best for:** New visitors, content-heavy sites

---

### 🚪 **Exit Intent**
Catch visitors as they're about to leave.

**Example:** "Wait! Don't leave without 10% off!"

**Best for:** Reducing bounce rate, impulse purchases

---

### 🆕 **First-Time Visitor**
Welcome new visitors with a special offer.

**Example:** "Welcome! Get 15% off your first purchase"

**Best for:** Customer acquisition, building email list

---

### 💎 **High-Value Visitor**
Target visitors viewing expensive products.

**Example:** "Premium products deserve premium discounts - 20% off!"

**Best for:** Luxury items, high-ticket products

---

## Delivery Methods

### 📧 **Email**
- Requires visitor email (from form submission or account)
- Professional, detailed offers
- Good for longer messages

### 📱 **SMS**
- Requires phone number
- Instant delivery
- High open rates (98%)
- Best for urgent offers

### 💬 **WhatsApp**
- Requires phone number
- Personal, conversational
- Great for customer relationships

### 🎯 **Popup**
- Shows on next page load
- No contact info needed
- Immediate impact
- Best for exit intent

### 🎨 **Banner**
- Displays at top of website
- Subtle, non-intrusive
- Stays visible while browsing

---

## Setting Up a Campaign

### Step 1: Choose Your Trigger
Pick the behavior that should trigger the discount:
- Cart abandoned
- Product browsing
- Exit intent
- etc.

### Step 2: Set Conditions (Optional)
Add rules to make it more targeted:
- **Minimum cart value:** Only trigger for carts over $50
- **Minimum page views:** At least 3 pages viewed
- **Time on site:** At least 2 minutes
- **Product category:** Only for specific categories
- **Visitor type:** New vs. returning

### Step 3: Create Your Discount
- **Type:** Percentage off, fixed amount, or free shipping
- **Value:** 10%, $5, etc.
- **Duration:** How long the code is valid (default: 7 days)

### Step 4: Write Your Message
Personalize the message with variables:
- `{discount_code}` - The unique code
- `{discount_value}` - The discount amount
- `{discount_type}` - percentage or fixed

**Example:**
```
🎉 Special offer just for you!

Use code {discount_code} for {discount_value}% off your order.

Valid for 7 days. Don't miss out!
```

### Step 5: Choose Delivery Method
Select how to send the discount:
- Email (needs email address)
- SMS (needs phone number)
- WhatsApp (needs phone number)
- Popup (no contact needed)
- Banner (no contact needed)

### Step 6: Activate!
Turn on the campaign and watch conversions roll in.

---

## Campaign Examples

### Example 1: Cart Abandonment Recovery
**Trigger:** Cart Abandoned  
**Condition:** Cart value > $30  
**Discount:** 15% off  
**Delivery:** Email  
**Message:**
```
Don't forget your items! 🛒

Complete your order now and save 15% with code {discount_code}

Your cart is waiting: [View Cart]
```

---

### Example 2: First-Time Visitor Welcome
**Trigger:** First-Time Visitor  
**Condition:** Viewed 3+ pages  
**Discount:** 10% off  
**Delivery:** Popup  
**Message:**
```
Welcome to our store! 👋

Get 10% off your first order with code {discount_code}

Start shopping and save!
```

---

### Example 3: Exit Intent Saver
**Trigger:** Exit Intent  
**Condition:** None  
**Discount:** Free Shipping  
**Delivery:** Popup  
**Message:**
```
Wait! Don't leave yet! 🚀

Get FREE SHIPPING on your order with code {discount_code}

Limited time offer!
```

---

### Example 4: High-Value Product Incentive
**Trigger:** Product View (No Purchase)  
**Condition:** Product price > $100, viewed 2+ times  
**Discount:** $20 off  
**Delivery:** Email  
**Message:**
```
Still thinking about that purchase? 💭

Here's $20 off to help you decide!

Use code {discount_code} at checkout.
```

---

## Best Practices

### ✅ Do's
- **Test different triggers** - See what works for your audience
- **Keep messages short** - Get to the point quickly
- **Create urgency** - "Limited time" or "Expires in 7 days"
- **Make codes easy** - Short, memorable discount codes
- **Track performance** - Monitor conversion rates
- **Segment audiences** - Different offers for different behaviors

### ❌ Don'ts
- **Don't spam** - Max 1 offer per visitor per 30 days
- **Don't over-discount** - Start with 10-15%, not 50%
- **Don't ignore mobile** - Most traffic is mobile
- **Don't forget expiry** - Always set expiration dates
- **Don't send without testing** - Test your campaigns first

---

## Tracking Performance

Monitor your campaigns in the Analytics dashboard:

- **Sent Count:** How many discounts were sent
- **Conversion Rate:** % of recipients who used the code
- **Revenue Impact:** Total sales from discount codes
- **Best Performers:** Which triggers convert best
- **ROI:** Return on investment for each campaign

---

## Privacy & Compliance

### Email Collection
- Only send emails to visitors who provided their email
- Include unsubscribe links
- Follow CAN-SPAM regulations

### SMS/WhatsApp
- Get explicit consent before sending
- Follow TCPA regulations (US)
- Provide opt-out instructions

### Cookies
- Inform visitors about tracking cookies
- Provide cookie consent banner (GDPR)
- Allow opt-out of behavioral tracking

---

## Integration with GA4

The system uses GA4 events to track visitor behavior:

- `add_to_cart` - Cart additions
- `view_item` - Product views
- `page_view` - Page navigation
- `session_start` - New sessions
- `user_engagement` - Time on site

Make sure GA4 is properly configured for accurate tracking.

---

## Frequently Asked Questions

**Q: How quickly are discounts sent?**  
A: Instantly! Popups show immediately, emails/SMS within seconds.

**Q: Can I send multiple offers to the same visitor?**  
A: No, each visitor gets max 1 offer per campaign per 30 days to avoid spam.

**Q: What if someone doesn't have an email/phone?**  
A: Use popup or banner delivery methods - they don't require contact info.

**Q: Can I customize the popup design?**  
A: Yes, customize colors, text, and styling in the campaign settings.

**Q: How do I know if it's working?**  
A: Check the Analytics dashboard for real-time campaign performance.

**Q: Can I A/B test different offers?**  
A: Yes! Create multiple campaigns with different discounts and compare results.

---

## Getting Started

1. **Set up GA4** (if not already done)
2. **Create your first campaign** in Marketing → Behavior Discounts
3. **Test it** by triggering the behavior yourself
4. **Monitor performance** in Analytics
5. **Optimize** based on results

---

**Ready to boost conversions?** Create your first behavior-triggered discount campaign now!

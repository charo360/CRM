# Google Analytics 4 Setup Guide - All Platforms

## What is Google Analytics 4?

Google Analytics 4 (GA4) is a free analytics tool that tracks visitor behavior on **any website** - whether you use Shopify, Wix, WordPress, Squarespace, or a custom-built site.

### What You Can Track:
- 📊 **Visitor numbers** - Daily, weekly, monthly traffic
- 🌍 **Traffic sources** - Google, social media, direct visits
- 📱 **Device types** - Mobile, desktop, tablet usage
- ⏱️ **User behavior** - Time on site, pages viewed, bounce rate
- 🎯 **Conversions** - Form submissions, purchases, sign-ups

---

## Quick Setup (3 Steps)

### Step 1: Create Your GA4 Property

1. Go to [Google Analytics](https://analytics.google.com)
2. Sign in with your Google account
3. Click **Admin** (gear icon) → **Create Property**
4. Enter your business name and website URL
5. Click **Create** → Select **Web** platform
6. **Copy your Measurement ID** (looks like `G-XXXXXXXXXX`)

### Step 2: Save Your Measurement ID in Zilo

1. Go to your **Zilo Dashboard** → **Settings** → **Analytics & Tracking**
2. Paste your Measurement ID (e.g., `G-XXXXXXXXXX`)
3. Click **Save**

### Step 3: Add Tracking to Your Website

Choose your platform below and follow the instructions:

---

## Platform-Specific Instructions

### 🛍️ Shopify

**Method 1: Using Shopify's Built-in Integration (Recommended)**
1. Go to **Shopify Admin** → **Settings** → **Apps and sales channels**
2. Search for "Google" and install **Google & YouTube**
3. Connect your Google account
4. Enter your GA4 Measurement ID
5. Click **Save**

**Method 2: Manual Code Injection**
1. Go to **Online Store** → **Themes**
2. Click **Actions** → **Edit code**
3. Find `theme.liquid` in the **Layout** folder
4. Paste the tracking code (from Zilo) just before `</head>`
5. Click **Save**

---

### 🎨 Wix

1. Go to **Wix Dashboard** → **Settings** → **Custom Code**
2. Click **+ Add Custom Code**
3. Paste the tracking code (copy from Zilo)
4. Set **Place Code in:** → **Head**
5. Set **Add Code to Pages:** → **All Pages**
6. Click **Apply**

---

### 📝 WordPress (Self-Hosted)

**Method 1: Using a Plugin (Easiest)**
1. Install **Insert Headers and Footers** or **WPCode** plugin
2. Go to **Settings** → **Insert Headers and Footers**
3. Paste the tracking code in the **Header** section
4. Click **Save**

**Method 2: Manual (Advanced)**
1. Go to **Appearance** → **Theme File Editor**
2. Find `header.php`
3. Paste the tracking code before `</head>`
4. Click **Update File**

---

### 🎯 Squarespace

1. Go to **Settings** → **Advanced** → **Code Injection**
2. Paste the tracking code in the **Header** section
3. Click **Save**

---

### 💻 Custom Website / HTML

1. Open your website's HTML files
2. Find the `<head>` section in your main template
3. Paste the tracking code before `</head>`
4. Save and upload to your server

---

### ⚡ Zilo Blog (Auto-Install)

If you have a **Zilo-hosted blog**, we can install GA4 automatically:

1. Save your Measurement ID in Zilo Settings
2. Select **Zilo Blog (Auto)** as your platform
3. Click **Auto-Activate on Zilo Blog**
4. Done! ✅

**Note:** This only works for your Zilo blog, not external websites like Shopify.

---

## Your Tracking Code

After saving your Measurement ID in Zilo, you can copy your tracking code:

```html
<!-- Google Analytics 4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
<!-- End Google Analytics 4 -->
```

Replace `G-XXXXXXXXXX` with your actual Measurement ID.

---

## Verifying It Works

1. Add the tracking code to your website
2. Visit your website in a new browser tab
3. Go to **Google Analytics** → **Reports** → **Realtime**
4. You should see yourself as an active user (appears within 1-2 minutes)

---

## Understanding Your Data

### Realtime Report
- See current visitors on your site
- View which pages they're on
- See where they came from

### Acquisition Report
- Understand how people find your site
- Track Google, social media, email traffic
- Identify best marketing channels

### Engagement Report
- Most viewed pages
- Average time on site
- Bounce rate

### Demographics
- Visitor location (country, city)
- Age and gender (if available)
- Device type (mobile, desktop)

---

## Common Questions

**Q: Will this work with my Shopify/Wix/WordPress site?**  
A: Yes! GA4 works with ANY website platform.

**Q: Do I need different Measurement IDs for different websites?**  
A: Yes, create a separate GA4 property for each website.

**Q: Can I use the same Measurement ID for my Shopify store AND Zilo blog?**  
A: No, each website should have its own Measurement ID for accurate tracking.

**Q: Is Google Analytics free?**  
A: Yes, GA4 is completely free for most businesses.

**Q: Will it slow down my website?**  
A: No, the tracking code is very lightweight and loads asynchronously.

**Q: How do I track my Shopify store AND my Zilo blog?**  
A: Create 2 separate GA4 properties:
- Property 1: For your Shopify store (add code to Shopify)
- Property 2: For your Zilo blog (auto-activate in Zilo)

---

## Privacy & GDPR

If you have visitors from Europe:
- Add a cookie consent banner
- Update your privacy policy
- Allow users to opt-out of tracking

**Tools for Cookie Consent:**
- Shopify: Cookie Consent apps
- Wix: Built-in cookie banner
- WordPress: Cookie Notice plugin

---

## Need Help?

- **Google Analytics Help**: [support.google.com/analytics](https://support.google.com/analytics)
- **GA4 Setup Guide**: [support.google.com/analytics/answer/9304153](https://support.google.com/analytics/answer/9304153)
- **Zilo Support**: Contact us through your dashboard

---

## Platform Comparison

| Platform | Difficulty | Method |
|----------|-----------|--------|
| Shopify | ⭐ Easy | Built-in integration or code injection |
| Wix | ⭐ Easy | Custom code section |
| Squarespace | ⭐ Easy | Code injection |
| WordPress | ⭐⭐ Medium | Plugin or theme editor |
| Custom Site | ⭐⭐⭐ Advanced | Manual HTML editing |
| Zilo Blog | ⚡ Instant | Auto-activation |

---

**Ready to track your website traffic?** Get your GA4 Measurement ID and add it to Zilo Settings now!

# Google Analytics 4 Setup Guide for Zilo

## What is Google Analytics 4?

Google Analytics 4 (GA4) is a free analytics tool from Google that helps you understand how people use your website. With GA4, you can:

- **Track visitor numbers** - See how many people visit your site daily, weekly, or monthly
- **Understand user behavior** - Know which pages are most popular and how long people stay
- **Identify traffic sources** - Discover where your visitors come from (Google search, social media, direct visits, etc.)
- **Measure conversions** - Track important actions like form submissions, purchases, or sign-ups
- **Make informed decisions** - Use real data to improve your website and marketing

---

## Step-by-Step Setup Guide

### Step 1: Create a Google Analytics 4 Property

1. **Go to Google Analytics**
   - Visit [https://analytics.google.com](https://analytics.google.com)
   - Sign in with your Google account (or create one if you don't have it)

2. **Create a new property** (if you don't have one already)
   - Click **Admin** (gear icon) in the bottom left
   - Under "Property" column, click **Create Property**
   - Enter your website name (e.g., "My Business Website")
   - Select your timezone and currency
   - Click **Next**

3. **Set up a data stream**
   - Select **Web** as your platform
   - Enter your website URL (e.g., `https://yourbusiness.zilo.pro`)
   - Enter a stream name (e.g., "Main Website")
   - Click **Create stream**

4. **Copy your Measurement ID**
   - After creating the stream, you'll see your **Measurement ID**
   - It looks like: `G-XXXXXXXXXX` (starts with "G-")
   - **Copy this ID** - you'll need it in the next step

---

### Step 2: Add GA4 to Your Zilo Website

1. **Go to your Zilo Dashboard**
   - Log in to your Zilo account
   - Navigate to **Settings** → **Analytics & Tracking**

2. **Enter your Measurement ID**
   - Paste the Measurement ID you copied (e.g., `G-XXXXXXXXXX`)
   - Click **Save**

3. **Activate GA4 Tracking**
   - After saving, click **Activate GA4 Tracking**
   - Wait a few seconds for the system to add the tracking code to your website
   - You'll see a success message when it's done

4. **Verify it's working**
   - Visit your website in a new browser tab
   - Go back to Google Analytics → **Reports** → **Realtime**
   - You should see yourself as an active user (may take 1-2 minutes to appear)

---

## Understanding Your GA4 Dashboard

Once GA4 is set up, here's what you can track:

### 1. **Realtime Report**
- See who's on your website right now
- View which pages they're visiting
- See where they came from

### 2. **Acquisition Report**
- Understand how people find your website
- Track traffic from Google, social media, email, etc.
- Identify your best marketing channels

### 3. **Engagement Report**
- See which pages get the most views
- Track how long people stay on your site
- Identify popular content

### 4. **User Demographics**
- Learn about your audience (age, gender, location)
- Understand their interests
- See what devices they use (mobile, desktop, tablet)

---

## Common Questions

### How long does it take for data to appear?
- **Realtime data**: 1-2 minutes
- **Standard reports**: 24-48 hours for full data processing

### Do I need to pay for Google Analytics?
No! Google Analytics 4 is completely free for most businesses. There's a paid version (GA360) for very large enterprises, but the free version is more than enough for small to medium businesses.

### Will GA4 slow down my website?
No. The GA4 tracking code is very lightweight and loads asynchronously, meaning it won't affect your website's speed.

### Can I track multiple websites?
Yes! You can create multiple data streams in GA4. Each website gets its own Measurement ID, which you can add to different Zilo sites.

### What if I change my Measurement ID?
Simply update the ID in your Zilo settings and click "Update Tracking". The system will automatically update the tracking code on your website.

### How do I remove GA4 tracking?
Go to Settings → Analytics & Tracking and click "Remove Tracking". This will remove all GA4 code from your website.

---

## Privacy & Compliance

### GDPR & Cookie Consent
If you have visitors from Europe, you may need to:
- Add a cookie consent banner to your website
- Allow users to opt-out of tracking
- Update your privacy policy

### Data Retention
By default, GA4 keeps user data for 2 months. You can adjust this in:
- Google Analytics → Admin → Data Settings → Data Retention

---

## Need Help?

- **Google Analytics Help Center**: [https://support.google.com/analytics](https://support.google.com/analytics)
- **GA4 Setup Guide**: [https://support.google.com/analytics/answer/9304153](https://support.google.com/analytics/answer/9304153)
- **Zilo Support**: Contact us through your dashboard

---

## Tips for Success

1. **Set up goals** - Track important actions like form submissions or purchases
2. **Check weekly** - Review your analytics at least once a week
3. **Look for trends** - Identify what's working and what's not
4. **Take action** - Use insights to improve your website and marketing
5. **Be patient** - It takes time to collect meaningful data (aim for at least 30 days)

---

**Ready to get started?** Head to your Zilo Dashboard → Settings → Analytics & Tracking to set up GA4 now!

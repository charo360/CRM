import {
  mjmlNewsletter, mjmlFlashSale, mjmlWelcome, mjmlWinback,
  mjmlAnnouncement, mjmlAbandonedCart, mjmlOrderConfirmation,
  mjmlEventInvitation, mjmlReferral, mjmlFeedback,
  mjmlHolidaySale, mjmlProductShowcase,
  mjmlShippingNotification, mjmlPasswordReset,
  mjmlReceiptInvoice, mjmlPaymentFailed,
} from "./mjml-templates";

export type TemplateVar = {
  key: string;
  label: string;
  placeholder: string;
  defaultValue: string;
  multiline?: boolean;
};

export type EmailTemplate = {
  id: string;
  name: string;
  category: string;
  description: string;
  thumbnail: string; // emoji preview
  defaultSubject: string;
  html: string;
  variables: TemplateVar[];
  /** If set, template is compiled server-side via /api/email-marketing/render-mjml */
  type?: "html" | "mjml";
  mjmlSource?: string;
};

/** Replace all {{KEY}} tokens in html with the given vars map */
export function applyVars(html: string, vars: Record<string, string>): string {
  return Object.entries(vars).reduce(
    (acc, [k, v]) => acc.replaceAll(`{{${k}}}`, v || `[${k}]`),
    html,
  );
}

const base = (accentColor: string, body: string) => `
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta http-equiv="X-UA-Compatible" content="IE=edge"/>
<title>Email</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="100%" style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
${body}
<!-- footer -->
<tr><td style="background:#f9fafb;padding:24px 32px;text-align:center;border-top:1px solid #e5e7eb;">
  <p style="margin:0 0 4px;font-size:12px;color:#9ca3af;">You received this email because you're on our list.</p>
  <p style="margin:0;font-size:12px;color:#9ca3af;"><a href="#" style="color:${accentColor};text-decoration:none;">Unsubscribe</a> · <a href="#" style="color:${accentColor};text-decoration:none;">View in browser</a></p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>`.trim();

// ── 1. Newsletter ─────────────────────────────────────────────────────────────
const newsletter = base("#6366f1", `
<tr><td style="background:linear-gradient(135deg,#6366f1 0%,#8b5cf6 100%);padding:40px 32px;text-align:center;">
  <h1 style="margin:0;font-size:28px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">📰 {{HEADLINE}}</h1>
  <p style="margin:8px 0 0;font-size:15px;color:rgba(255,255,255,0.85);">{{SUBHEADLINE}}</p>
</td></tr>
<tr><td style="padding:32px;">
  <h2 style="margin:0 0 8px;font-size:20px;font-weight:700;color:#111827;">👋 Hello, valued subscriber!</h2>
  <p style="margin:0 0 24px;font-size:15px;color:#4b5563;line-height:1.7;">We've put together this month's best content just for you. From industry insights to practical tips, there's something for everyone.</p>
  
  <!-- Article 1 -->
  <table role="presentation" width="100%" style="background:#f8f7ff;border-radius:10px;overflow:hidden;margin-bottom:16px;">
  <tr>
    <td style="padding:20px 24px;">
      <span style="display:inline-block;background:#6366f1;color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;text-transform:uppercase;letter-spacing:0.5px;">Feature</span>
      <h3 style="margin:10px 0 6px;font-size:17px;font-weight:700;color:#111827;">{{ARTICLE_1_TITLE}}</h3>
      <p style="margin:0 0 12px;font-size:14px;color:#6b7280;line-height:1.6;">{{ARTICLE_1_SUMMARY}}</p>
      <a href="#" style="display:inline-block;color:#6366f1;font-size:14px;font-weight:600;text-decoration:none;">Read more →</a>
    </td>
  </tr>
  </table>

  <!-- Article 2 -->
  <table role="presentation" width="100%" style="background:#f0fdf4;border-radius:10px;overflow:hidden;margin-bottom:24px;">
  <tr>
    <td style="padding:20px 24px;">
      <span style="display:inline-block;background:#10b981;color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;text-transform:uppercase;letter-spacing:0.5px;">Tips</span>
      <h3 style="margin:10px 0 6px;font-size:17px;font-weight:700;color:#111827;">{{ARTICLE_2_TITLE}}</h3>
      <p style="margin:0 0 12px;font-size:14px;color:#6b7280;line-height:1.6;">{{ARTICLE_2_SUMMARY}}</p>
      <a href="#" style="display:inline-block;color:#10b981;font-size:14px;font-weight:600;text-decoration:none;">Read more →</a>
    </td>
  </tr>
  </table>

  <!-- CTA -->
  <div style="text-align:center;padding:8px 0 16px;">
    <a href="{{CTA_URL}}" style="display:inline-block;background:#6366f1;color:#ffffff;font-size:15px;font-weight:700;padding:14px 36px;border-radius:8px;text-decoration:none;letter-spacing:0.2px;">Visit Our Blog →</a>
  </div>
</td></tr>
`);

// ── 2. Flash Sale ─────────────────────────────────────────────────────────────
const flashSale = base("#ef4444", `
<tr><td style="background:linear-gradient(135deg,#dc2626 0%,#f97316 100%);padding:48px 32px;text-align:center;">
  <p style="margin:0 0 6px;font-size:13px;font-weight:700;color:rgba(255,255,255,0.8);text-transform:uppercase;letter-spacing:2px;">Limited Time Only</p>
  <h1 style="margin:0 0 8px;font-size:52px;font-weight:900;color:#ffffff;line-height:1;">🔥 {{DISCOUNT}}</h1>
  <p style="margin:0 0 24px;font-size:18px;color:rgba(255,255,255,0.9);">{{SALE_DESCRIPTION}}</p>
  <a href="{{CTA_URL}}" style="display:inline-block;background:#ffffff;color:#dc2626;font-size:16px;font-weight:800;padding:16px 48px;border-radius:8px;text-decoration:none;letter-spacing:0.3px;">SHOP NOW</a>
</td></tr>
<tr><td style="padding:32px;">
  <p style="margin:0 0 20px;font-size:15px;color:#4b5563;line-height:1.7;text-align:center;">Don't miss out — our biggest sale of the year is here. Use code <strong style="color:#dc2626;">{{PROMO_CODE}}</strong> at checkout.</p>
  
  <!-- Products row -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
  <tr>
    <td width="48%" style="background:#fff5f5;border-radius:10px;padding:20px;text-align:center;vertical-align:top;">
      <div style="font-size:40px;margin-bottom:10px;">👗</div>
      <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#111827;">Clothing</p>
      <p style="margin:0 0 10px;font-size:13px;color:#9ca3af;">From $9.99</p>
      <a href="#" style="display:inline-block;background:#ef4444;color:#fff;font-size:13px;font-weight:600;padding:8px 20px;border-radius:6px;text-decoration:none;">Shop</a>
    </td>
    <td width="4%"></td>
    <td width="48%" style="background:#fff5f5;border-radius:10px;padding:20px;text-align:center;vertical-align:top;">
      <div style="font-size:40px;margin-bottom:10px;">📱</div>
      <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#111827;">Electronics</p>
      <p style="margin:0 0 10px;font-size:13px;color:#9ca3af;">From $19.99</p>
      <a href="#" style="display:inline-block;background:#ef4444;color:#fff;font-size:13px;font-weight:600;padding:8px 20px;border-radius:6px;text-decoration:none;">Shop</a>
    </td>
  </tr>
  </table>

  <!-- Urgency -->
  <table role="presentation" width="100%" style="background:#fef2f2;border:2px solid #fca5a5;border-radius:10px;">
  <tr><td style="padding:16px 20px;text-align:center;">
    <p style="margin:0;font-size:14px;color:#b91c1c;font-weight:700;">⏰ Sale ends {{SALE_DEADLINE}} — don't wait!</p>
  </td></tr>
  </table>
</td></tr>
`);

// ── 3. Welcome Email ──────────────────────────────────────────────────────────
const welcome = base("#10b981", `
<tr><td style="background:linear-gradient(135deg,#065f46 0%,#10b981 100%);padding:48px 32px;text-align:center;">
  <div style="font-size:56px;margin-bottom:12px;">🎉</div>
  <h1 style="margin:0 0 8px;font-size:30px;font-weight:800;color:#ffffff;">Welcome to {{COMPANY_NAME}}!</h1>
  <p style="margin:0;font-size:16px;color:rgba(255,255,255,0.85);">We're so glad you're here</p>
</td></tr>
<tr><td style="padding:32px;">
  <p style="margin:0 0 24px;font-size:15px;color:#4b5563;line-height:1.7;">Hi there! 👋 Thanks for joining us. We're excited to have you and can't wait to show you everything we have to offer. Here's how to get started:</p>

  <!-- Steps -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="12" style="margin-bottom:28px;">
  <tr><td style="background:#f0fdf4;border-left:4px solid #10b981;border-radius:0 8px 8px 0;padding:16px 20px;">
    <table role="presentation"><tr>
      <td style="font-size:22px;padding-right:14px;vertical-align:top;">1️⃣</td>
      <td><strong style="color:#111827;font-size:14px;">Complete your profile</strong><br/><span style="font-size:13px;color:#6b7280;">Add your details so we can personalise your experience.</span></td>
    </tr></table>
  </td></tr>
  <tr><td style="background:#f0fdf4;border-left:4px solid #10b981;border-radius:0 8px 8px 0;padding:16px 20px;">
    <table role="presentation"><tr>
      <td style="font-size:22px;padding-right:14px;vertical-align:top;">2️⃣</td>
      <td><strong style="color:#111827;font-size:14px;">Explore our features</strong><br/><span style="font-size:13px;color:#6b7280;">Discover everything available to help your business grow.</span></td>
    </tr></table>
  </td></tr>
  <tr><td style="background:#f0fdf4;border-left:4px solid #10b981;border-radius:0 8px 8px 0;padding:16px 20px;">
    <table role="presentation"><tr>
      <td style="font-size:22px;padding-right:14px;vertical-align:top;">3️⃣</td>
      <td><strong style="color:#111827;font-size:14px;">Reach out anytime</strong><br/><span style="font-size:13px;color:#6b7280;">Our support team is here 24/7 — just reply to this email.</span></td>
    </tr></table>
  </td></tr>
  </table>

  <div style="text-align:center;">
    <a href="{{CTA_URL}}" style="display:inline-block;background:#10b981;color:#ffffff;font-size:15px;font-weight:700;padding:14px 40px;border-radius:8px;text-decoration:none;">Get Started →</a>
  </div>
</td></tr>
`);

// ── 4. Win-back ───────────────────────────────────────────────────────────────
const winback = base("#f59e0b", `
<tr><td style="background:linear-gradient(135deg,#92400e 0%,#f59e0b 100%);padding:48px 32px;text-align:center;">
  <div style="font-size:56px;margin-bottom:12px;">💔</div>
  <h1 style="margin:0 0 8px;font-size:30px;font-weight:800;color:#ffffff;">We miss you!</h1>
  <p style="margin:0;font-size:16px;color:rgba(255,255,255,0.85);">It's been a while — here's something special to bring you back</p>
</td></tr>
<tr><td style="padding:32px;">
  <p style="margin:0 0 24px;font-size:15px;color:#4b5563;line-height:1.7;">Hey! We noticed you haven't been around for a while. We hate to see you go, so we've put together an exclusive offer just for you.</p>

  <!-- Offer box -->
  <table role="presentation" width="100%" style="background:linear-gradient(135deg,#fffbeb,#fef3c7);border:2px solid #fcd34d;border-radius:12px;margin-bottom:24px;">
  <tr><td style="padding:28px;text-align:center;">
    <p style="margin:0 0 4px;font-size:13px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:1.5px;">Your exclusive offer</p>
    <p style="margin:0 0 8px;font-size:44px;font-weight:900;color:#d97706;">{{DISCOUNT}}</p>
    <p style="margin:0 0 16px;font-size:14px;color:#78716c;">Use code: <strong style="color:#d97706;font-size:18px;letter-spacing:2px;">{{PROMO_CODE}}</strong></p>
    <a href="{{CTA_URL}}" style="display:inline-block;background:#f59e0b;color:#ffffff;font-size:15px;font-weight:700;padding:14px 40px;border-radius:8px;text-decoration:none;">Claim My Offer</a>
    <p style="margin:12px 0 0;font-size:12px;color:#a78bfa;">Expires in {{EXPIRE_DAYS}} days</p>
  </td></tr>
  </table>

  <p style="margin:0;font-size:14px;color:#9ca3af;text-align:center;">Questions? Just reply to this email — we'd love to hear from you. 💛</p>
</td></tr>
`);

// ── 5. Product Announcement ───────────────────────────────────────────────────
const announcement = base("#3b82f6", `
<tr><td style="background:linear-gradient(135deg,#1e3a8a 0%,#3b82f6 100%);padding:48px 32px;text-align:center;">
  <p style="margin:0 0 8px;font-size:12px;font-weight:700;color:rgba(255,255,255,0.7);text-transform:uppercase;letter-spacing:2px;">New Release</p>
  <h1 style="margin:0 0 10px;font-size:32px;font-weight:800;color:#ffffff;line-height:1.2;">{{PRODUCT_NAME}}</h1>
  <p style="margin:0;font-size:16px;color:rgba(255,255,255,0.85);">We've been working hard on this for months</p>
</td></tr>
<tr><td style="padding:32px;">
  <p style="margin:0 0 24px;font-size:15px;color:#4b5563;line-height:1.7;">We're thrilled to announce the launch of our newest product/feature. This has been a long time coming and we can't wait for you to try it.</p>

  <!-- Feature highlights -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
  <tr>
    <td width="30%" style="padding:16px;text-align:center;vertical-align:top;">
      <div style="font-size:32px;margin-bottom:8px;">⚡</div>
      <strong style="font-size:14px;color:#111827;">Blazing Fast</strong>
      <p style="margin:4px 0 0;font-size:12px;color:#9ca3af;">3x faster than before</p>
    </td>
    <td width="30%" style="padding:16px;text-align:center;vertical-align:top;">
      <div style="font-size:32px;margin-bottom:8px;">🔒</div>
      <strong style="font-size:14px;color:#111827;">Secure</strong>
      <p style="margin:4px 0 0;font-size:12px;color:#9ca3af;">Enterprise-grade security</p>
    </td>
    <td width="30%" style="padding:16px;text-align:center;vertical-align:top;">
      <div style="font-size:32px;margin-bottom:8px;">🎯</div>
      <strong style="font-size:14px;color:#111827;">Precise</strong>
      <p style="margin:4px 0 0;font-size:12px;color:#9ca3af;">Accuracy you can trust</p>
    </td>
  </tr>
  </table>

  <table role="presentation" width="100%" style="background:#eff6ff;border-radius:10px;margin-bottom:24px;">
  <tr><td style="padding:20px 24px;">
    <p style="margin:0;font-size:14px;color:#1e40af;line-height:1.7;">{{TESTIMONIAL}}</p>
  </td></tr>
  </table>

  <div style="text-align:center;">
    <a href="{{CTA_URL}}" style="display:inline-block;background:#3b82f6;color:#ffffff;font-size:15px;font-weight:700;padding:14px 40px;border-radius:8px;text-decoration:none;">Explore Now →</a>
  </div>
</td></tr>
`);

// ── 6. Abandoned Cart ─────────────────────────────────────────────────────────
const abandonedCart = base("#8b5cf6", `
<tr><td style="background:linear-gradient(135deg,#4c1d95 0%,#8b5cf6 100%);padding:48px 32px;text-align:center;">
  <div style="font-size:56px;margin-bottom:12px;">🛒</div>
  <h1 style="margin:0 0 8px;font-size:28px;font-weight:800;color:#ffffff;">You left something behind!</h1>
  <p style="margin:0;font-size:16px;color:rgba(255,255,255,0.85);">Your cart is waiting — complete your order today</p>
</td></tr>
<tr><td style="padding:32px;">
  <p style="margin:0 0 24px;font-size:15px;color:#4b5563;line-height:1.7;">Hey! You had some great items in your cart. We saved them for you, but they're selling fast — don't miss out!</p>

  <!-- Cart item placeholder -->
  <table role="presentation" width="100%" style="border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;margin-bottom:24px;">
  <tr style="background:#f9fafb;"><td colspan="2" style="padding:12px 16px;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">Items in your cart</td></tr>
  <tr>
    <td style="padding:16px;border-top:1px solid #e5e7eb;">
      <table role="presentation"><tr>
        <td style="width:56px;height:56px;background:#ede9fe;border-radius:8px;font-size:28px;text-align:center;vertical-align:middle;padding-right:14px;">🎁</td>
        <td>
          <strong style="font-size:14px;color:#111827;">{{PRODUCT_NAME}}</strong><br/>
          <span style="font-size:13px;color:#9ca3af;">{{PRODUCT_VARIANT}}</span>
        </td>
        <td style="text-align:right;padding-left:16px;">
          <strong style="font-size:15px;color:#8b5cf6;">{{PRODUCT_PRICE}}</strong>
        </td>
      </tr></table>
    </td>
  </tr>
  </table>

  <!-- Incentive -->
  <table role="presentation" width="100%" style="background:#faf5ff;border:2px dashed #c4b5fd;border-radius:10px;margin-bottom:24px;">
  <tr><td style="padding:16px 20px;text-align:center;">
    <p style="margin:0;font-size:14px;color:#6d28d9;">🎁 Complete your order now and get <strong>free shipping</strong> on us!</p>
  </td></tr>
  </table>

  <div style="text-align:center;">
    <a href="{{CTA_URL}}" style="display:inline-block;background:#8b5cf6;color:#ffffff;font-size:16px;font-weight:700;padding:16px 48px;border-radius:8px;text-decoration:none;">Complete My Order →</a>
    <p style="margin:12px 0 0;font-size:12px;color:#9ca3af;">Items reserved for 24 hours</p>
  </div>
</td></tr>
`);

// ── Export ────────────────────────────────────────────────────────────────────
export const EMAIL_TEMPLATES: EmailTemplate[] = [
  {
    id: "newsletter",
    name: "Newsletter",
    category: "Content",
    description: "Monthly or weekly newsletter with articles and updates",
    thumbnail: "📰",
    defaultSubject: "📰 Your Monthly Newsletter — [Month] Edition",
    html: newsletter,
    variables: [
      { key: "HEADLINE",        label: "Newsletter title",    placeholder: "June Monthly Newsletter",               defaultValue: "Your Monthly Newsletter" },
      { key: "SUBHEADLINE",     label: "Subtitle",           placeholder: "The latest tips and updates",            defaultValue: "The latest news, tips, and updates from us" },
      { key: "ARTICLE_1_TITLE",label: "Article 1 title",    placeholder: "Top 5 Tips for This Month",              defaultValue: "Article Title Goes Here" },
      { key: "ARTICLE_1_SUMMARY",label:"Article 1 summary", placeholder: "A short description...",                 defaultValue: "A brief summary of the article that explains what the reader will learn.", multiline: true },
      { key: "ARTICLE_2_TITLE",label: "Article 2 title",    placeholder: "Another Great Read",                     defaultValue: "Second Article Title" },
      { key: "ARTICLE_2_SUMMARY",label:"Article 2 summary", placeholder: "Another short description...",            defaultValue: "Another brief summary here that entices the reader to click.", multiline: true },
      { key: "CTA_URL",         label: "Blog / CTA link",   placeholder: "https://yourdomain.com/blog",            defaultValue: "#" },
    ],
  },
  {
    id: "flash-sale",
    name: "Flash Sale",
    category: "Promotional",
    description: "Bold sale announcement with urgency and promo code",
    thumbnail: "🔥",
    defaultSubject: "🔥 50% OFF — Today Only!",
    html: flashSale,
    variables: [
      { key: "DISCOUNT",         label: "Discount amount",     placeholder: "50% OFF",                    defaultValue: "50% OFF" },
      { key: "SALE_DESCRIPTION", label: "Sale description",    placeholder: "Everything — this weekend only", defaultValue: "Everything in the store — this weekend only" },
      { key: "PROMO_CODE",       label: "Promo code",          placeholder: "SAVE50",                     defaultValue: "SAVE50" },
      { key: "SALE_DEADLINE",    label: "Sale deadline",       placeholder: "Sunday at midnight",         defaultValue: "Sunday at midnight" },
      { key: "CTA_URL",          label: "Shop link",           placeholder: "https://yourstore.com",      defaultValue: "#" },
    ],
  },
  {
    id: "welcome",
    name: "Welcome Email",
    category: "Onboarding",
    description: "Warm welcome for new subscribers with getting-started steps",
    thumbnail: "🎉",
    defaultSubject: "🎉 Welcome to [Company] — Let's get started!",
    html: welcome,
    variables: [
      { key: "COMPANY_NAME", label: "Company / brand name", placeholder: "Acme Inc.",                      defaultValue: "Your Company" },
      { key: "CTA_URL",     label: "Get started link",    placeholder: "https://app.yourcompany.com",    defaultValue: "#" },
    ],
  },
  {
    id: "winback",
    name: "Win-back",
    category: "Retention",
    description: "Re-engage inactive customers with an exclusive offer",
    thumbnail: "💔",
    defaultSubject: "We miss you 💛 Here's 30% off to come back",
    html: winback,
    variables: [
      { key: "DISCOUNT",    label: "Discount amount",    placeholder: "30% OFF",                    defaultValue: "30% OFF" },
      { key: "PROMO_CODE", label: "Promo code",         placeholder: "COMEBACK30",                  defaultValue: "COMEBACK30" },
      { key: "EXPIRE_DAYS",label: "Offer expires (days)",placeholder: "7",                          defaultValue: "7" },
      { key: "CTA_URL",    label: "Claim offer link",   placeholder: "https://yourstore.com",      defaultValue: "#" },
    ],
  },
  {
    id: "announcement",
    name: "Announcement",
    category: "News",
    description: "Product launch or feature announcement with highlights",
    thumbnail: "🚀",
    defaultSubject: "🚀 Big news — Introducing [Product Name]",
    html: announcement,
    variables: [
      { key: "PRODUCT_NAME", label: "Product / feature name", placeholder: "Introducing Something Amazing 🚀",                                            defaultValue: "Introducing Something Amazing 🚀" },
      { key: "TESTIMONIAL",  label: "Testimonial quote",      placeholder: "\"This changed how we work.\" — Happy Customer",                               defaultValue: "\"This is exactly what we've been waiting for. The new release completely changes how we work.\" — Early Access User", multiline: true },
      { key: "CTA_URL",      label: "Explore link",          placeholder: "https://yoursite.com/product",                                                defaultValue: "#" },
    ],
  },
  {
    id: "abandoned-cart",
    name: "Abandoned Cart",
    category: "E-commerce",
    description: "Recover abandoned carts with urgency and free shipping offer",
    thumbnail: "🛒",
    defaultSubject: "🛒 You left something behind — complete your order",
    html: abandonedCart,
    variables: [
      { key: "PRODUCT_NAME",    label: "Product name",      placeholder: "Awesome Sneakers",             defaultValue: "Your Product" },
      { key: "PRODUCT_VARIANT", label: "Variant / size",    placeholder: "Medium / Blue",                defaultValue: "Size / Variant" },
      { key: "PRODUCT_PRICE",   label: "Product price",     placeholder: "$29.99",                       defaultValue: "$29.99" },
      { key: "CTA_URL",         label: "Cart / checkout link",placeholder: "https://yourstore.com/cart",  defaultValue: "#" },
    ],
  },

  // ── MJML-powered templates (responsive, mobile-first) ─────────────────────

  {
    id: "mjml-newsletter",
    name: "Newsletter (MJML)",
    category: "Newsletter",
    description: "Responsive newsletter with two featured articles and CTA",
    thumbnail: "📰",
    defaultSubject: "📰 {{HEADLINE}} — This Month's Highlights",
    html: "",
    type: "mjml",
    mjmlSource: mjmlNewsletter,
    variables: [
      { key: "HEADLINE",         label: "Headline",            placeholder: "Monthly Highlights",          defaultValue: "Monthly Highlights" },
      { key: "SUBHEADLINE",      label: "Sub-headline",        placeholder: "Your curated digest",         defaultValue: "Your curated digest — hand-picked just for you" },
      { key: "ARTICLE_1_TITLE",  label: "Article 1 title",     placeholder: "Industry Insight",            defaultValue: "5 Trends Reshaping E-commerce in 2025" },
      { key: "ARTICLE_1_SUMMARY",label: "Article 1 summary",   placeholder: "Short summary...",            defaultValue: "Discover how AI, social commerce, and sustainability are changing the game for online retailers.", multiline: true },
      { key: "ARTICLE_2_TITLE",  label: "Article 2 title",     placeholder: "Practical Tips",              defaultValue: "10 Quick Wins to Boost Your Conversion Rate" },
      { key: "ARTICLE_2_SUMMARY",label: "Article 2 summary",   placeholder: "Short summary...",            defaultValue: "Simple tweaks your team can implement today to see measurable improvements by next week.", multiline: true },
      { key: "CTA_URL",          label: "Read more link",      placeholder: "https://yoursite.com/blog",   defaultValue: "#" },
    ],
  },

  {
    id: "mjml-flash-sale",
    name: "Flash Sale (MJML)",
    category: "Promotional",
    description: "Bold responsive sale email with promo code and urgency",
    thumbnail: "🔥",
    defaultSubject: "🔥 {{DISCOUNT}} OFF — Today Only!",
    html: "",
    type: "mjml",
    mjmlSource: mjmlFlashSale,
    variables: [
      { key: "DISCOUNT",         label: "Discount amount",     placeholder: "50% OFF",                     defaultValue: "50% OFF" },
      { key: "SALE_DESCRIPTION", label: "Sale description",    placeholder: "Everything in our store",     defaultValue: "Everything in our store — this weekend only" },
      { key: "PROMO_CODE",       label: "Promo code",          placeholder: "SAVE50",                      defaultValue: "SAVE50" },
      { key: "SALE_DEADLINE",    label: "Deadline",            placeholder: "Sunday at midnight",          defaultValue: "Sunday at midnight" },
      { key: "CTA_URL",          label: "Shop link",           placeholder: "https://yourstore.com",       defaultValue: "#" },
    ],
  },

  {
    id: "mjml-welcome",
    name: "Welcome Email (MJML)",
    category: "Onboarding",
    description: "Warm mobile-first welcome with 3 onboarding steps",
    thumbnail: "🎉",
    defaultSubject: "Welcome to {{COMPANY_NAME}} — Let's get started!",
    html: "",
    type: "mjml",
    mjmlSource: mjmlWelcome,
    variables: [
      { key: "COMPANY_NAME", label: "Company / brand name", placeholder: "Acme Inc.",                   defaultValue: "Your Company" },
      { key: "CTA_URL",      label: "Get started link",     placeholder: "https://app.yourcompany.com", defaultValue: "#" },
    ],
  },

  {
    id: "mjml-winback",
    name: "Win-back (MJML)",
    category: "Retention",
    description: "Re-engage inactive customers with a prominent discount code",
    thumbnail: "💛",
    defaultSubject: "We miss you 💛 — Here's {{DISCOUNT}} to come back",
    html: "",
    type: "mjml",
    mjmlSource: mjmlWinback,
    variables: [
      { key: "DISCOUNT",    label: "Discount amount",     placeholder: "30% OFF",      defaultValue: "30% OFF" },
      { key: "PROMO_CODE",  label: "Promo code",          placeholder: "COMEBACK30",   defaultValue: "COMEBACK30" },
      { key: "EXPIRE_DAYS", label: "Expires in (days)",   placeholder: "7",            defaultValue: "7" },
      { key: "CTA_URL",     label: "Claim offer link",    placeholder: "https://yourstore.com", defaultValue: "#" },
    ],
  },

  {
    id: "mjml-announcement",
    name: "Announcement (MJML)",
    category: "News",
    description: "Product launch or feature announcement with highlights and testimonial",
    thumbnail: "🚀",
    defaultSubject: "🚀 Introducing {{PRODUCT_NAME}}",
    html: "",
    type: "mjml",
    mjmlSource: mjmlAnnouncement,
    variables: [
      { key: "PRODUCT_NAME", label: "Product / feature name", placeholder: "Something Amazing",               defaultValue: "Something Amazing" },
      { key: "TESTIMONIAL",  label: "Testimonial quote",      placeholder: "\"This changed everything.\"",    defaultValue: "\"This is exactly what we've been waiting for. It completely changes how we work.\" — Early Access User", multiline: true },
      { key: "CTA_URL",      label: "Explore link",           placeholder: "https://yoursite.com/product",    defaultValue: "#" },
    ],
  },

  {
    id: "mjml-abandoned-cart",
    name: "Abandoned Cart (MJML)",
    category: "E-commerce",
    description: "Recover carts with product card, free shipping badge, and urgency",
    thumbnail: "🛒",
    defaultSubject: "🛒 You left something behind — your cart is waiting",
    html: "",
    type: "mjml",
    mjmlSource: mjmlAbandonedCart,
    variables: [
      { key: "PRODUCT_NAME",    label: "Product name",         placeholder: "Awesome Sneakers",             defaultValue: "Your Product" },
      { key: "PRODUCT_VARIANT", label: "Variant / size",       placeholder: "Medium / Blue",                defaultValue: "Size M / Navy Blue" },
      { key: "PRODUCT_PRICE",   label: "Price",                placeholder: "$29.99",                       defaultValue: "$29.99" },
      { key: "CTA_URL",         label: "Cart / checkout link", placeholder: "https://yourstore.com/cart",   defaultValue: "#" },
    ],
  },

  {
    id: "mjml-order-confirmation",
    name: "Order Confirmation (MJML)",
    category: "Transactional",
    description: "Clean order summary with line items, shipping address, and tracking link",
    thumbnail: "✅",
    defaultSubject: "Your order #{{ORDER_NUMBER}} is confirmed!",
    html: "",
    type: "mjml",
    mjmlSource: mjmlOrderConfirmation,
    variables: [
      { key: "ORDER_NUMBER",     label: "Order number",        placeholder: "10042",                    defaultValue: "10042" },
      { key: "PRODUCT_NAME",     label: "Product name",        placeholder: "Blue Running Shoes",       defaultValue: "Blue Running Shoes" },
      { key: "PRODUCT_PRICE",    label: "Order total",         placeholder: "$89.99",                   defaultValue: "$89.99" },
      { key: "SHIPPING_ADDRESS", label: "Shipping address",    placeholder: "123 Main St, City, State", defaultValue: "123 Main Street, San Francisco, CA 94101", multiline: true },
      { key: "CTA_URL",          label: "Track order link",    placeholder: "https://yourstore.com/orders/10042", defaultValue: "#" },
    ],
  },

  {
    id: "mjml-event-invitation",
    name: "Event Invitation (MJML)",
    category: "Events",
    description: "Elegant event invite with date, time, and location details",
    thumbnail: "📅",
    defaultSubject: "You're invited — {{EVENT_NAME}}",
    html: "",
    type: "mjml",
    mjmlSource: mjmlEventInvitation,
    variables: [
      { key: "EVENT_NAME",     label: "Event name",      placeholder: "Annual Product Summit 2025",  defaultValue: "Annual Product Summit 2025" },
      { key: "EVENT_DATE",     label: "Date",            placeholder: "Thursday, June 12, 2025",     defaultValue: "Thursday, June 12, 2025" },
      { key: "EVENT_TIME",     label: "Time",            placeholder: "2:00 PM — 5:00 PM EST",       defaultValue: "2:00 PM — 5:00 PM EST" },
      { key: "EVENT_LOCATION", label: "Location",        placeholder: "Zoom Webinar (link TBA)",     defaultValue: "Zoom Webinar — link sent upon registration" },
      { key: "CTA_URL",        label: "RSVP / register", placeholder: "https://yoursite.com/event",  defaultValue: "#" },
    ],
  },

  {
    id: "mjml-referral",
    name: "Referral Program (MJML)",
    category: "Growth",
    description: "Referral invite with 3-step explainer and unique code",
    thumbnail: "🎁",
    defaultSubject: "Share {{COMPANY_NAME}} and earn {{REWARD_AMOUNT}}!",
    html: "",
    type: "mjml",
    mjmlSource: mjmlReferral,
    variables: [
      { key: "COMPANY_NAME",   label: "Company / app name", placeholder: "Zilo",                  defaultValue: "Zilo" },
      { key: "REWARD_AMOUNT",  label: "Reward amount",      placeholder: "$10 credit",             defaultValue: "$10 credit" },
      { key: "REFERRAL_CODE",  label: "Referral code",      placeholder: "REF-ABC123",             defaultValue: "REF-ABC123" },
      { key: "CTA_URL",        label: "Share / referral link", placeholder: "https://yoursite.com/refer", defaultValue: "#" },
    ],
  },

  {
    id: "mjml-feedback",
    name: "Feedback Request (MJML)",
    category: "Feedback",
    description: "Emoji-rating survey with full survey CTA",
    thumbnail: "⭐",
    defaultSubject: "How was your experience with {{PRODUCT_NAME}}?",
    html: "",
    type: "mjml",
    mjmlSource: mjmlFeedback,
    variables: [
      { key: "PRODUCT_NAME",  label: "Product / service name", placeholder: "Zilo CRM",                  defaultValue: "Zilo CRM" },
      { key: "SURVEY_TOPIC",  label: "Survey topic / question", placeholder: "How was your overall experience?", defaultValue: "How would you rate your overall experience with Zilo CRM?" },
      { key: "CTA_URL",       label: "Full survey link",        placeholder: "https://yoursite.com/survey", defaultValue: "#" },
    ],
  },

  {
    id: "mjml-holiday-sale",
    name: "Holiday Sale (MJML)",
    category: "Seasonal",
    description: "Festive holiday sale with promo code, free shipping, and gift wrap perks",
    thumbnail: "🎄",
    defaultSubject: "🎄 {{SALE_TITLE}} — {{DISCOUNT}} OFF Everything!",
    html: "",
    type: "mjml",
    mjmlSource: mjmlHolidaySale,
    variables: [
      { key: "SALE_TITLE",    label: "Sale title",      placeholder: "Holiday Sale",            defaultValue: "Our Biggest Holiday Sale Ever" },
      { key: "SALE_SUBTITLE", label: "Sale subtitle",   placeholder: "Shop gifts for everyone", defaultValue: "Shop the best gifts for everyone on your list" },
      { key: "DISCOUNT",      label: "Discount amount", placeholder: "40%",                     defaultValue: "40%" },
      { key: "PROMO_CODE",    label: "Promo code",      placeholder: "HOLIDAY40",               defaultValue: "HOLIDAY40" },
      { key: "SALE_DEADLINE", label: "Sale ends",       placeholder: "December 24th",           defaultValue: "December 24th at midnight" },
      { key: "CTA_URL",       label: "Shop link",       placeholder: "https://yourstore.com",   defaultValue: "#" },
    ],
  },

  {
    id: "mjml-product-showcase",
    name: "Product Showcase (MJML)",
    category: "E-commerce",
    description: "Dark hero product reveal with emoji display, price, and 3 key features",
    thumbnail: "✨",
    defaultSubject: "✨ Meet {{PRODUCT_NAME}} — just launched",
    html: "",
    type: "mjml",
    mjmlSource: mjmlProductShowcase,
    variables: [
      { key: "PRODUCT_NAME",    label: "Product name",      placeholder: "AirPods Pro",             defaultValue: "Your New Product" },
      { key: "PRODUCT_TAGLINE", label: "Tagline",           placeholder: "Sound like never before",  defaultValue: "The next generation of awesome" },
      { key: "PRODUCT_EMOJI",   label: "Product emoji",     placeholder: "🎧",                      defaultValue: "✨" },
      { key: "PRODUCT_DESCRIPTION", label: "Short description", placeholder: "1-2 sentences...",   defaultValue: "Crafted with precision and built to impress. Your customers will love it.", multiline: true },
      { key: "PRODUCT_PRICE",   label: "Price",             placeholder: "$199",                    defaultValue: "$199" },
      { key: "FEATURE_1",       label: "Feature 1",         placeholder: "Premium quality materials", defaultValue: "Premium quality, built to last" },
      { key: "FEATURE_2",       label: "Feature 2",         placeholder: "Free express shipping",   defaultValue: "Free express shipping on all orders" },
      { key: "FEATURE_3",       label: "Feature 3",         placeholder: "30-day money back",       defaultValue: "30-day money-back guarantee" },
      { key: "CTA_URL",         label: "Shop link",         placeholder: "https://yourstore.com",   defaultValue: "#" },
    ],
  },

  // ── Transactional ────────────────────────────────────────────────────────────

  {
    id: "mjml-shipping-notification",
    name: "Shipping Notification (MJML)",
    category: "Transactional",
    description: "Shipped order alert with tracking number, carrier, estimated delivery, and shipment summary",
    thumbnail: "📦",
    defaultSubject: "📦 Your order #{{ORDER_NUMBER}} has shipped!",
    html: "",
    type: "mjml",
    mjmlSource: mjmlShippingNotification,
    variables: [
      { key: "ORDER_NUMBER",         label: "Order number",         placeholder: "12345",                           defaultValue: "12345" },
      { key: "CARRIER",              label: "Carrier",              placeholder: "FedEx",                           defaultValue: "FedEx" },
      { key: "TRACKING_NUMBER",      label: "Tracking number",      placeholder: "794644792798",                    defaultValue: "794644792798" },
      { key: "TRACKING_URL",         label: "Tracking link",        placeholder: "https://tracking.fedex.com/...",  defaultValue: "#" },
      { key: "DELIVERY_DATE",        label: "Est. delivery date",   placeholder: "Friday, May 24",                  defaultValue: "Friday, May 24" },
      { key: "SHIPPING_ADDRESS",     label: "Shipping address",     placeholder: "123 Main St, City, ST 12345",     defaultValue: "123 Main St, City, ST 12345", multiline: true },
      { key: "ORDER_ITEMS_SUMMARY",  label: "Items summary",        placeholder: "1× Blue T-Shirt (M), 2× Socks",  defaultValue: "1× Product Name", multiline: true },
    ],
  },

  {
    id: "mjml-password-reset",
    name: "Password Reset (MJML)",
    category: "Transactional",
    description: "Secure password reset with expiry warning, IP details, and didn't-request disclaimer",
    thumbnail: "🔐",
    defaultSubject: "Reset your {{COMPANY_NAME}} password",
    html: "",
    type: "mjml",
    mjmlSource: mjmlPasswordReset,
    variables: [
      { key: "COMPANY_NAME",  label: "Company name",     placeholder: "Zilo",                              defaultValue: "Your Company" },
      { key: "RESET_URL",     label: "Reset link",       placeholder: "https://yourapp.com/reset/token",   defaultValue: "#" },
      { key: "EXPIRY_HOURS",  label: "Link expires in",  placeholder: "24",                                defaultValue: "24" },
      { key: "REQUEST_IP",    label: "Request IP",       placeholder: "192.168.1.1",                       defaultValue: "Unknown" },
      { key: "REQUEST_TIME",  label: "Request time",     placeholder: "May 21, 2026 at 3:42 PM",           defaultValue: "Just now" },
    ],
  },

  {
    id: "mjml-receipt-invoice",
    name: "Receipt / Invoice (MJML)",
    category: "Transactional",
    description: "Full purchase receipt with line-item table, subtotal/tax/total breakdown, and shipping address",
    thumbnail: "🧾",
    defaultSubject: "Your receipt from {{COMPANY_NAME}} — Order #{{INVOICE_NUMBER}}",
    html: "",
    type: "mjml",
    mjmlSource: mjmlReceiptInvoice,
    variables: [
      { key: "COMPANY_NAME",    label: "Company name",    placeholder: "Zilo Store",           defaultValue: "Your Company" },
      { key: "INVOICE_NUMBER",  label: "Invoice/Order #", placeholder: "INV-2026-0042",        defaultValue: "INV-0001" },
      { key: "INVOICE_DATE",    label: "Invoice date",    placeholder: "May 21, 2026",          defaultValue: "Today" },
      { key: "CUSTOMER_NAME",   label: "Customer name",   placeholder: "John",                 defaultValue: "Valued Customer" },
      { key: "ORDER_ITEMS",     label: "Line items (HTML <tr> rows)", placeholder: "<tr><td style=\"padding:12px 16px;\">Product</td><td style=\"padding:12px 16px;text-align:center;\">1</td><td style=\"padding:12px 16px;text-align:right;\">$29.00</td></tr>", defaultValue: "<tr><td style=\"padding:12px 16px;border-bottom:1px solid #f3f4f6;\">Sample Product</td><td style=\"padding:12px 16px;text-align:center;border-bottom:1px solid #f3f4f6;\">1</td><td style=\"padding:12px 16px;text-align:right;border-bottom:1px solid #f3f4f6;\">$29.00</td></tr>", multiline: true },
      { key: "SUBTOTAL",        label: "Subtotal",        placeholder: "$29.00",               defaultValue: "$29.00" },
      { key: "SHIPPING_COST",   label: "Shipping",        placeholder: "$0.00",                defaultValue: "FREE" },
      { key: "TAX",             label: "Tax",             placeholder: "$2.32",                defaultValue: "$0.00" },
      { key: "TOTAL",           label: "Total",           placeholder: "$31.32",               defaultValue: "$29.00" },
      { key: "SHIPPING_ADDRESS",label: "Shipping address",placeholder: "123 Main St...",       defaultValue: "123 Main St, City, ST 12345", multiline: true },
      { key: "CTA_URL",         label: "View invoice link",placeholder: "https://...",         defaultValue: "#" },
    ],
  },

  {
    id: "mjml-payment-failed",
    name: "Payment Failed (MJML)",
    category: "Transactional",
    description: "Payment failure alert with failure reason, order hold notice, and update payment CTA",
    thumbnail: "⚠️",
    defaultSubject: "⚠️ Payment failed for order #{{ORDER_NUMBER}} — action required",
    html: "",
    type: "mjml",
    mjmlSource: mjmlPaymentFailed,
    variables: [
      { key: "CUSTOMER_NAME",   label: "Customer name",    placeholder: "John",                    defaultValue: "Valued Customer" },
      { key: "ORDER_NUMBER",    label: "Order number",     placeholder: "12345",                   defaultValue: "12345" },
      { key: "ORDER_TOTAL",     label: "Amount due",       placeholder: "$49.99",                  defaultValue: "$49.99" },
      { key: "FAILURE_REASON",  label: "Failure reason",   placeholder: "Card was declined",       defaultValue: "Your card was declined. Please check your card details or try a different payment method." },
      { key: "HOLD_HOURS",      label: "Hold duration (hrs)", placeholder: "48",                  defaultValue: "48" },
      { key: "CTA_URL",         label: "Update payment link", placeholder: "https://...",          defaultValue: "#" },
    ],
  },
];

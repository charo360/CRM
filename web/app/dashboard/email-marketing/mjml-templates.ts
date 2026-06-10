/**
 * MJML source templates — compiled server-side via /api/email-marketing/render-mjml
 * Each template uses {{VARIABLE}} tokens which survive MJML compilation.
 */

const footer = (accent: string) => `
    <mj-section background-color="#f9fafb" padding="24px 32px" border-top="1px solid #e5e7eb">
      <mj-column>
        <mj-text color="#9ca3af" font-size="12px" align="center" padding="0">
          You received this email because you're subscribed to our list.<br/>
          <a href="#" style="color:${accent};text-decoration:none;">Unsubscribe</a> &nbsp;·&nbsp; <a href="#" style="color:${accent};text-decoration:none;">View in browser</a>
        </mj-text>
      </mj-column>
    </mj-section>`;

// ── 1. Newsletter ─────────────────────────────────────────────────────────────

export const mjmlNewsletter = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#6366f1" border-radius="8px" font-size="14px" font-weight="700" padding="14px 28px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f4f4f5">
    <mj-section background-color="#6366f1" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="28px" font-weight="800" align="center" padding="0">📰 {{HEADLINE}}</mj-text>
        <mj-text color="#e0e7ff" font-size="15px" align="center" padding-top="8px" padding-bottom="0">{{SUBHEADLINE}}</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="32px">
      <mj-column>
        <mj-text font-size="19px" font-weight="700" color="#111827" padding-bottom="12px">👋 Hello, valued subscriber!</mj-text>
        <mj-text color="#4b5563" padding-bottom="24px">We've curated this month's best content just for you — industry insights, practical tips, and more.</mj-text>

        <mj-text background-color="#f8f7ff" border-radius="10px" padding="20px 24px">
          <span style="display:inline-block;background:#6366f1;color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;text-transform:uppercase;letter-spacing:0.5px;">Feature</span>
          <h3 style="margin:10px 0 6px;font-size:17px;font-weight:700;color:#111827;">{{ARTICLE_1_TITLE}}</h3>
          <p style="margin:0 0 12px;font-size:14px;color:#6b7280;line-height:1.6;">{{ARTICLE_1_SUMMARY}}</p>
          <a href="{{CTA_URL}}" style="color:#6366f1;font-size:14px;font-weight:600;text-decoration:none;">Read more →</a>
        </mj-text>

        <mj-spacer height="12px" />

        <mj-text background-color="#f0fdf4" border-radius="10px" padding="20px 24px">
          <span style="display:inline-block;background:#10b981;color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;text-transform:uppercase;letter-spacing:0.5px;">Tips</span>
          <h3 style="margin:10px 0 6px;font-size:17px;font-weight:700;color:#111827;">{{ARTICLE_2_TITLE}}</h3>
          <p style="margin:0 0 12px;font-size:14px;color:#6b7280;line-height:1.6;">{{ARTICLE_2_SUMMARY}}</p>
          <a href="{{CTA_URL}}" style="color:#10b981;font-size:14px;font-weight:600;text-decoration:none;">Read more →</a>
        </mj-text>

        <mj-spacer height="24px" />
        <mj-button href="{{CTA_URL}}" align="center">View all articles →</mj-button>
      </mj-column>
    </mj-section>
    ${footer("#6366f1")}
  </mj-body>
</mjml>`.trim();

// ── 2. Flash Sale ─────────────────────────────────────────────────────────────

export const mjmlFlashSale = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#ef4444" border-radius="8px" font-size="15px" font-weight="700" padding="16px 36px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#fff5f5">
    <mj-section background-color="#ef4444" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="42px" font-weight="800" align="center" padding="0">🔥 {{DISCOUNT}}</mj-text>
        <mj-text color="#fecaca" font-size="16px" align="center" padding-top="6px" padding-bottom="0">{{SALE_DESCRIPTION}}</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="32px">
      <mj-column>
        <mj-text color="#111827" font-size="18px" font-weight="700" padding-bottom="8px" align="center">This offer ends {{SALE_DEADLINE}}</mj-text>
        <mj-text color="#6b7280" align="center" padding-bottom="28px">Don't miss out — use your exclusive code at checkout and save big today.</mj-text>

        <mj-text background-color="#fef2f2" border-radius="12px" padding="20px 24px" align="center">
          <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:1px;">Your Promo Code</p>
          <p style="margin:0;font-size:28px;font-weight:800;color:#ef4444;letter-spacing:4px;font-family:monospace;">{{PROMO_CODE}}</p>
        </mj-text>

        <mj-spacer height="28px" />
        <mj-button href="{{CTA_URL}}" align="center">Shop Now — Save {{DISCOUNT}}</mj-button>
        <mj-spacer height="16px" />
        <mj-text color="#9ca3af" font-size="12px" align="center" padding="0">
          ⏰ Hurry! Sale ends {{SALE_DEADLINE}}. No rain checks.
        </mj-text>
      </mj-column>
    </mj-section>
    ${footer("#ef4444")}
  </mj-body>
</mjml>`.trim();

// ── 3. Welcome Email ──────────────────────────────────────────────────────────

export const mjmlWelcome = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#10b981" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f0fdf4">
    <mj-section background-color="#10b981" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="36px" font-weight="800" align="center" padding="0">🎉</mj-text>
        <mj-text color="#ffffff" font-size="24px" font-weight="700" align="center" padding-top="8px" padding-bottom="0">Welcome to {{COMPANY_NAME}}!</mj-text>
        <mj-text color="#d1fae5" font-size="15px" align="center" padding-top="6px" padding-bottom="0">We're so glad you're here.</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#111827" font-size="17px" font-weight="700" padding-bottom="8px">Here's how to get started:</mj-text>

        <mj-text padding="16px 0" border-bottom="1px solid #f3f4f6">
          <table cellpadding="0" cellspacing="0" style="width:100%"><tr>
            <td style="width:40px;vertical-align:top;padding-top:2px;">
              <div style="width:32px;height:32px;border-radius:50%;background:#d1fae5;display:flex;align-items:center;justify-content:center;font-size:16px;text-align:center;line-height:32px;">1</div>
            </td>
            <td style="vertical-align:top;padding-left:12px;">
              <p style="margin:0 0 2px;font-weight:700;color:#111827;font-size:15px;">Complete your profile</p>
              <p style="margin:0;color:#6b7280;font-size:14px;">Add your details so we can personalise your experience.</p>
            </td>
          </tr></table>
        </mj-text>

        <mj-text padding="16px 0" border-bottom="1px solid #f3f4f6">
          <table cellpadding="0" cellspacing="0" style="width:100%"><tr>
            <td style="width:40px;vertical-align:top;padding-top:2px;">
              <div style="width:32px;height:32px;border-radius:50%;background:#d1fae5;display:flex;align-items:center;justify-content:center;font-size:16px;text-align:center;line-height:32px;">2</div>
            </td>
            <td style="vertical-align:top;padding-left:12px;">
              <p style="margin:0 0 2px;font-weight:700;color:#111827;font-size:15px;">Explore the dashboard</p>
              <p style="margin:0;color:#6b7280;font-size:14px;">Discover all the tools available to grow your business.</p>
            </td>
          </tr></table>
        </mj-text>

        <mj-text padding="16px 0">
          <table cellpadding="0" cellspacing="0" style="width:100%"><tr>
            <td style="width:40px;vertical-align:top;padding-top:2px;">
              <div style="width:32px;height:32px;border-radius:50%;background:#d1fae5;display:flex;align-items:center;justify-content:center;font-size:16px;text-align:center;line-height:32px;">3</div>
            </td>
            <td style="vertical-align:top;padding-left:12px;">
              <p style="margin:0 0 2px;font-weight:700;color:#111827;font-size:15px;">Make your first move</p>
              <p style="margin:0;color:#6b7280;font-size:14px;">Start a campaign, import contacts, or connect your store.</p>
            </td>
          </tr></table>
        </mj-text>

        <mj-spacer height="24px" />
        <mj-button href="{{CTA_URL}}" align="center">Get started now →</mj-button>
      </mj-column>
    </mj-section>
    ${footer("#10b981")}
  </mj-body>
</mjml>`.trim();

// ── 4. Win-back ───────────────────────────────────────────────────────────────

export const mjmlWinback = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#f59e0b" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#fffbeb">
    <mj-section background-color="#f59e0b" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="36px" align="center" padding="0">💛</mj-text>
        <mj-text color="#ffffff" font-size="24px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">We miss you!</mj-text>
        <mj-text color="#fef3c7" font-size="15px" align="center" padding-top="6px" padding-bottom="0">It's been a while — here's something special to bring you back.</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="24px">
          As one of our valued customers, you deserve a special treat. We've been busy adding new products, improving our service, and we'd love to share it all with you.
        </mj-text>

        <mj-text background-color="#fffbeb" border="2px dashed #f59e0b" border-radius="12px" padding="24px" align="center">
          <p style="margin:0 0 4px;font-size:13px;font-weight:600;color:#92400e;text-transform:uppercase;letter-spacing:1px;">Exclusive offer — just for you</p>
          <p style="margin:0 0 8px;font-size:40px;font-weight:800;color:#f59e0b;">{{DISCOUNT}} OFF</p>
          <p style="margin:0 0 12px;font-size:13px;color:#6b7280;">Use code at checkout:</p>
          <p style="margin:0;font-size:24px;font-weight:800;color:#92400e;letter-spacing:3px;font-family:monospace;">{{PROMO_CODE}}</p>
        </mj-text>

        <mj-text color="#9ca3af" font-size="12px" align="center" padding="16px 0 24px">⏰ Expires in {{EXPIRE_DAYS}} days. One use per customer.</mj-text>
        <mj-button href="{{CTA_URL}}" align="center">Claim my {{DISCOUNT}} discount →</mj-button>
      </mj-column>
    </mj-section>
    ${footer("#f59e0b")}
  </mj-body>
</mjml>`.trim();

// ── 5. Announcement / Product Launch ─────────────────────────────────────────

export const mjmlAnnouncement = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#3b82f6" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#eff6ff">
    <mj-section background-color="#3b82f6" padding="40px 32px">
      <mj-column>
        <mj-text color="#bfdbfe" font-size="12px" font-weight="700" align="center" padding="0" letter-spacing="2px">INTRODUCING</mj-text>
        <mj-text color="#ffffff" font-size="26px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">{{PRODUCT_NAME}}</mj-text>
        <mj-text color="#bfdbfe" font-size="15px" align="center" padding-top="8px" padding-bottom="0">The future is here. And it's beautiful.</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#111827" font-size="18px" font-weight="700" padding-bottom="8px">What makes it special?</mj-text>
        <mj-text color="#4b5563" padding-bottom="24px">We've been working hard behind the scenes to bring you something truly remarkable. Here's what you can look forward to:</mj-text>

        <mj-text padding="0 0 12px">
          <table cellpadding="0" cellspacing="0" style="width:100%"><tr>
            <td style="width:40px;vertical-align:top;padding-top:2px;"><div style="width:32px;height:32px;border-radius:8px;background:#dbeafe;text-align:center;line-height:32px;font-size:16px;">⚡</div></td>
            <td style="padding-left:12px;vertical-align:top;">
              <p style="margin:0 0 2px;font-weight:700;color:#111827;font-size:15px;">Lightning fast</p>
              <p style="margin:0;color:#6b7280;font-size:14px;">Built for speed and performance from the ground up.</p>
            </td>
          </tr></table>
        </mj-text>

        <mj-text padding="0 0 12px">
          <table cellpadding="0" cellspacing="0" style="width:100%"><tr>
            <td style="width:40px;vertical-align:top;padding-top:2px;"><div style="width:32px;height:32px;border-radius:8px;background:#dbeafe;text-align:center;line-height:32px;font-size:16px;">🎯</div></td>
            <td style="padding-left:12px;vertical-align:top;">
              <p style="margin:0 0 2px;font-weight:700;color:#111827;font-size:15px;">Precision tools</p>
              <p style="margin:0;color:#6b7280;font-size:14px;">Everything you need, exactly where you need it.</p>
            </td>
          </tr></table>
        </mj-text>

        <mj-text padding="0 0 28px">
          <table cellpadding="0" cellspacing="0" style="width:100%"><tr>
            <td style="width:40px;vertical-align:top;padding-top:2px;"><div style="width:32px;height:32px;border-radius:8px;background:#dbeafe;text-align:center;line-height:32px;font-size:16px;">🔒</div></td>
            <td style="padding-left:12px;vertical-align:top;">
              <p style="margin:0 0 2px;font-weight:700;color:#111827;font-size:15px;">Secure by design</p>
              <p style="margin:0;color:#6b7280;font-size:14px;">Enterprise-grade security built in from day one.</p>
            </td>
          </tr></table>
        </mj-text>

        <mj-text background-color="#eff6ff" border-left="4px solid #3b82f6" border-radius="0 8px 8px 0" padding="16px 20px">
          <p style="margin:0;font-size:14px;color:#1e40af;font-style:italic;">{{TESTIMONIAL}}</p>
        </mj-text>

        <mj-spacer height="28px" />
        <mj-button href="{{CTA_URL}}" align="center">Explore {{PRODUCT_NAME}} →</mj-button>
      </mj-column>
    </mj-section>
    ${footer("#3b82f6")}
  </mj-body>
</mjml>`.trim();

// ── 6. Abandoned Cart ─────────────────────────────────────────────────────────

export const mjmlAbandonedCart = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#7c3aed" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f5f3ff">
    <mj-section background-color="#7c3aed" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="32px" align="center" padding="0">🛒</mj-text>
        <mj-text color="#ffffff" font-size="22px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">You left something behind!</mj-text>
        <mj-text color="#ddd6fe" font-size="15px" align="center" padding-top="6px" padding-bottom="0">Your cart is waiting — complete your order before it's gone.</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="20px">Hi there! We noticed you didn't complete your purchase. No worries — we saved your cart so you can pick up right where you left off.</mj-text>

        <mj-text background-color="#faf5ff" border-radius="12px" padding="20px 24px" border="1px solid #ede9fe">
          <table cellpadding="0" cellspacing="0" style="width:100%"><tr>
            <td style="width:70px;vertical-align:middle;">
              <div style="width:60px;height:60px;border-radius:10px;background:#7c3aed;text-align:center;line-height:60px;font-size:28px;">📦</div>
            </td>
            <td style="padding-left:16px;vertical-align:middle;">
              <p style="margin:0 0 2px;font-weight:700;color:#111827;font-size:16px;">{{PRODUCT_NAME}}</p>
              <p style="margin:0 0 2px;font-size:13px;color:#9ca3af;">{{PRODUCT_VARIANT}}</p>
              <p style="margin:0;font-size:18px;font-weight:800;color:#7c3aed;">{{PRODUCT_PRICE}}</p>
            </td>
          </tr></table>
        </mj-text>

        <mj-text background-color="#f0fdf4" border-radius="8px" padding="12px 16px" padding-top="16px">
          <p style="margin:0;font-size:14px;color:#166534;font-weight:600;">🚚 Free shipping on orders over $50 — automatically applied!</p>
        </mj-text>

        <mj-spacer height="24px" />
        <mj-button href="{{CTA_URL}}" align="center">Complete my order →</mj-button>
        <mj-spacer height="12px" />
        <mj-text color="#9ca3af" font-size="12px" align="center" padding="0">Items in your cart are not reserved — order now to secure yours.</mj-text>
      </mj-column>
    </mj-section>
    ${footer("#7c3aed")}
  </mj-body>
</mjml>`.trim();

// ── 7. Order Confirmation ─────────────────────────────────────────────────────

export const mjmlOrderConfirmation = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#10b981" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f0fdf4">
    <mj-section background-color="#10b981" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="36px" align="center" padding="0">✅</mj-text>
        <mj-text color="#ffffff" font-size="22px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">Order Confirmed!</mj-text>
        <mj-text color="#d1fae5" font-size="14px" align="center" padding-top="6px" padding-bottom="0">Order #{{ORDER_NUMBER}} · Thank you for your purchase!</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="20px">
          Great news — your order has been received and is being processed. You'll receive a shipping confirmation once your package is on its way.
        </mj-text>

        <mj-text background-color="#f9fafb" border-radius="12px" padding="20px 24px" border="1px solid #e5e7eb">
          <p style="margin:0 0 12px;font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">Order Summary</p>
          <table cellpadding="0" cellspacing="0" style="width:100%">
            <tr>
              <td style="padding-bottom:8px;color:#111827;font-weight:600;">{{PRODUCT_NAME}}</td>
              <td style="padding-bottom:8px;text-align:right;font-weight:700;color:#111827;">{{PRODUCT_PRICE}}</td>
            </tr>
            <tr>
              <td style="padding-bottom:8px;color:#6b7280;font-size:14px;">Shipping</td>
              <td style="padding-bottom:8px;text-align:right;color:#10b981;font-weight:600;font-size:14px;">FREE</td>
            </tr>
            <tr style="border-top:1px solid #e5e7eb;">
              <td style="padding-top:8px;font-weight:700;color:#111827;">Total</td>
              <td style="padding-top:8px;text-align:right;font-weight:800;color:#111827;font-size:18px;">{{PRODUCT_PRICE}}</td>
            </tr>
          </table>
        </mj-text>

        <mj-text background-color="#f9fafb" border-radius="12px" padding="20px 24px" border="1px solid #e5e7eb">
          <p style="margin:0 0 6px;font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">Shipping To</p>
          <p style="margin:0;color:#374151;font-size:14px;line-height:1.6;">{{SHIPPING_ADDRESS}}</p>
        </mj-text>

        <mj-spacer height="24px" />
        <mj-button href="{{CTA_URL}}" align="center">Track my order →</mj-button>
      </mj-column>
    </mj-section>
    ${footer("#10b981")}
  </mj-body>
</mjml>`.trim();

// ── 8. Event Invitation ───────────────────────────────────────────────────────

export const mjmlEventInvitation = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#f97316" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#fff7ed">
    <mj-section background-color="#f97316" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffedd5" font-size="12px" font-weight="700" align="center" padding="0" letter-spacing="2px">YOU'RE INVITED</mj-text>
        <mj-text color="#ffffff" font-size="26px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">{{EVENT_NAME}}</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="24px">
          You're cordially invited to join us for an exciting event. Reserve your spot today — spaces are limited!
        </mj-text>

        <mj-text background-color="#fff7ed" border-radius="12px" padding="24px" border="1px solid #fed7aa">
          <table cellpadding="0" cellspacing="0" style="width:100%">
            <tr>
              <td style="padding-bottom:14px;vertical-align:top;width:30px;font-size:20px;">📅</td>
              <td style="padding-bottom:14px;padding-left:12px;vertical-align:top;">
                <p style="margin:0 0 2px;font-size:12px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Date</p>
                <p style="margin:0;font-weight:700;color:#111827;font-size:15px;">{{EVENT_DATE}}</p>
              </td>
            </tr>
            <tr>
              <td style="padding-bottom:14px;vertical-align:top;width:30px;font-size:20px;">🕐</td>
              <td style="padding-bottom:14px;padding-left:12px;vertical-align:top;">
                <p style="margin:0 0 2px;font-size:12px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Time</p>
                <p style="margin:0;font-weight:700;color:#111827;font-size:15px;">{{EVENT_TIME}}</p>
              </td>
            </tr>
            <tr>
              <td style="vertical-align:top;width:30px;font-size:20px;">📍</td>
              <td style="padding-left:12px;vertical-align:top;">
                <p style="margin:0 0 2px;font-size:12px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Location</p>
                <p style="margin:0;font-weight:700;color:#111827;font-size:15px;">{{EVENT_LOCATION}}</p>
              </td>
            </tr>
          </table>
        </mj-text>

        <mj-spacer height="28px" />
        <mj-button href="{{CTA_URL}}" align="center">Reserve my spot →</mj-button>
        <mj-spacer height="12px" />
        <mj-text color="#9ca3af" font-size="12px" align="center" padding="0">Seats are limited. RSVP early to secure your place.</mj-text>
      </mj-column>
    </mj-section>
    ${footer("#f97316")}
  </mj-body>
</mjml>`.trim();

// ── 9. Referral Program ───────────────────────────────────────────────────────

export const mjmlReferral = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#6366f1" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#eef2ff">
    <mj-section background-color="#6366f1" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="32px" align="center" padding="0">🎁</mj-text>
        <mj-text color="#ffffff" font-size="24px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">Share {{COMPANY_NAME}}, earn rewards!</mj-text>
        <mj-text color="#c7d2fe" font-size="15px" align="center" padding-top="6px" padding-bottom="0">Invite friends and both of you get {{REWARD_AMOUNT}}.</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="24px">
          Love using {{COMPANY_NAME}}? Share it with friends and colleagues! Every time someone signs up using your link, you both earn {{REWARD_AMOUNT}} — it's that simple.
        </mj-text>

        <mj-text background-color="#eef2ff" border-radius="12px" padding="24px" align="center" border="1px solid #c7d2fe">
          <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#6366f1;text-transform:uppercase;letter-spacing:1px;">Your unique referral code</p>
          <p style="margin:0 0 16px;font-size:28px;font-weight:800;color:#4f46e5;letter-spacing:4px;font-family:monospace;">{{REFERRAL_CODE}}</p>
          <p style="margin:0;font-size:13px;color:#6b7280;">Share this code or your referral link</p>
        </mj-text>

        <mj-text padding="20px 0 0">
          <table cellpadding="0" cellspacing="0" style="width:100%;text-align:center">
            <tr>
              <td style="padding:0 8px;">
                <div style="background:#f9fafb;border-radius:12px;padding:16px 8px;">
                  <p style="margin:0 0 4px;font-size:22px;">📤</p>
                  <p style="margin:0 0 4px;font-weight:700;color:#111827;font-size:14px;">You share</p>
                  <p style="margin:0;color:#6b7280;font-size:13px;">Send your code to friends</p>
                </div>
              </td>
              <td style="padding:0 8px;">
                <div style="background:#f9fafb;border-radius:12px;padding:16px 8px;">
                  <p style="margin:0 0 4px;font-size:22px;">✅</p>
                  <p style="margin:0 0 4px;font-weight:700;color:#111827;font-size:14px;">They sign up</p>
                  <p style="margin:0;color:#6b7280;font-size:13px;">Using your referral code</p>
                </div>
              </td>
              <td style="padding:0 8px;">
                <div style="background:#f9fafb;border-radius:12px;padding:16px 8px;">
                  <p style="margin:0 0 4px;font-size:22px;">🎉</p>
                  <p style="margin:0 0 4px;font-weight:700;color:#111827;font-size:14px;">Both get rewarded</p>
                  <p style="margin:0;color:#6b7280;font-size:13px;">{{REWARD_AMOUNT}} each!</p>
                </div>
              </td>
            </tr>
          </table>
        </mj-text>

        <mj-spacer height="28px" />
        <mj-button href="{{CTA_URL}}" align="center">Share my referral link →</mj-button>
      </mj-column>
    </mj-section>
    ${footer("#6366f1")}
  </mj-body>
</mjml>`.trim();

// ── 10. Feedback / Survey Request ─────────────────────────────────────────────

export const mjmlFeedback = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#8b5cf6" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#faf5ff">
    <mj-section background-color="#8b5cf6" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="32px" align="center" padding="0">⭐</mj-text>
        <mj-text color="#ffffff" font-size="22px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">How was your experience?</mj-text>
        <mj-text color="#ede9fe" font-size="15px" align="center" padding-top="6px" padding-bottom="0">We'd love to hear your thoughts on {{PRODUCT_NAME}}.</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="16px">
          Hi there! Your opinion matters more than you know. We're constantly working to improve {{PRODUCT_NAME}} and your feedback helps us get better every day.
        </mj-text>

        <mj-text background-color="#faf5ff" border-radius="12px" padding="24px" align="center" border="1px solid #ddd6fe">
          <p style="margin:0 0 8px;font-weight:700;color:#111827;font-size:15px;">{{SURVEY_TOPIC}}</p>
          <p style="margin:0 0 16px;font-size:14px;color:#6b7280;">Takes less than 2 minutes. Your response is anonymous.</p>
          <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
            <tr>
              <td style="padding:0 6px;text-align:center;">
                <a href="{{CTA_URL}}" style="font-size:28px;text-decoration:none;">😞</a>
                <p style="margin:4px 0 0;font-size:11px;color:#9ca3af;">Poor</p>
              </td>
              <td style="padding:0 6px;text-align:center;">
                <a href="{{CTA_URL}}" style="font-size:28px;text-decoration:none;">😐</a>
                <p style="margin:4px 0 0;font-size:11px;color:#9ca3af;">Okay</p>
              </td>
              <td style="padding:0 6px;text-align:center;">
                <a href="{{CTA_URL}}" style="font-size:28px;text-decoration:none;">😊</a>
                <p style="margin:4px 0 0;font-size:11px;color:#9ca3af;">Good</p>
              </td>
              <td style="padding:0 6px;text-align:center;">
                <a href="{{CTA_URL}}" style="font-size:28px;text-decoration:none;">🤩</a>
                <p style="margin:4px 0 0;font-size:11px;color:#9ca3af;">Amazing</p>
              </td>
            </tr>
          </table>
        </mj-text>

        <mj-text color="#6b7280" font-size="14px" align="center" padding="16px 0">
          Or share detailed feedback below:
        </mj-text>

        <mj-button href="{{CTA_URL}}" align="center">Take the full survey →</mj-button>
        <mj-spacer height="12px" />
        <mj-text color="#9ca3af" font-size="12px" align="center" padding="0">
          This survey is completely anonymous. We appreciate your time! ❤️
        </mj-text>
      </mj-column>
    </mj-section>
    ${footer("#8b5cf6")}
  </mj-body>
</mjml>`.trim();

// ── 11. Holiday Sale ──────────────────────────────────────────────────────────

export const mjmlHolidaySale = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#dc2626" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#fef2f2">
    <mj-section background-color="#dc2626" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="36px" align="center" padding="0">🎄 🎁 ⛄</mj-text>
        <mj-text color="#ffffff" font-size="26px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">{{SALE_TITLE}}</mj-text>
        <mj-text color="#fca5a5" font-size="15px" align="center" padding-top="6px" padding-bottom="0">{{SALE_SUBTITLE}}</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#111827" font-size="17px" font-weight="700" padding-bottom="8px" align="center">🎁 Holiday Deals — Up to {{DISCOUNT}} OFF</mj-text>
        <mj-text color="#4b5563" padding-bottom="24px" align="center">
          Give the gift of great products this season. Shop our biggest sale of the year with savings across everything.
        </mj-text>

        <mj-text background-color="#fef2f2" border="2px solid #dc2626" border-radius="12px" padding="20px 24px" align="center">
          <p style="margin:0 0 4px;font-size:13px;font-weight:700;color:#991b1b;text-transform:uppercase;letter-spacing:1px;">Holiday Promo Code</p>
          <p style="margin:0 0 4px;font-size:32px;font-weight:800;color:#dc2626;letter-spacing:3px;font-family:monospace;">{{PROMO_CODE}}</p>
          <p style="margin:0;font-size:13px;color:#9ca3af;">Valid through {{SALE_DEADLINE}}</p>
        </mj-text>

        <mj-text background-color="#f0fdf4" border-radius="8px" padding="14px 16px" padding-top="20px">
          <table cellpadding="0" cellspacing="0" style="width:100%;text-align:center">
            <tr>
              <td style="padding:0 4px;"><p style="margin:0;font-size:13px;color:#166534;font-weight:600;">🚚 Free Shipping</p></td>
              <td style="padding:0 4px;"><p style="margin:0;font-size:13px;color:#166534;font-weight:600;">🎁 Gift Wrapping</p></td>
              <td style="padding:0 4px;"><p style="margin:0;font-size:13px;color:#166534;font-weight:600;">🔄 Easy Returns</p></td>
            </tr>
          </table>
        </mj-text>

        <mj-spacer height="28px" />
        <mj-button href="{{CTA_URL}}" align="center">Shop Holiday Deals →</mj-button>
      </mj-column>
    </mj-section>
    ${footer("#dc2626")}
  </mj-body>
</mjml>`.trim();

// ── 13. Shipping Notification ─────────────────────────────────────────────────

export const mjmlShippingNotification = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#0ea5e9" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f0f9ff">
    <mj-section background-color="#0ea5e9" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="36px" align="center" padding="0">📦</mj-text>
        <mj-text color="#ffffff" font-size="22px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">Your order is on its way!</mj-text>
        <mj-text color="#bae6fd" font-size="14px" align="center" padding-top="6px" padding-bottom="0">Order #{{ORDER_NUMBER}} has shipped via {{CARRIER}}</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="20px">
          Great news! Your package is on its way. Here are your shipping details:
        </mj-text>

        <mj-text background-color="#f0f9ff" border-radius="12px" padding="20px 24px" border="1px solid #bae6fd">
          <table cellpadding="0" cellspacing="0" style="width:100%">
            <tr>
              <td style="padding-bottom:12px;width:50%;vertical-align:top;">
                <p style="margin:0 0 2px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Tracking Number</p>
                <p style="margin:0;font-weight:700;color:#0ea5e9;font-size:15px;font-family:monospace;">{{TRACKING_NUMBER}}</p>
              </td>
              <td style="padding-bottom:12px;vertical-align:top;">
                <p style="margin:0 0 2px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Carrier</p>
                <p style="margin:0;font-weight:700;color:#111827;font-size:15px;">{{CARRIER}}</p>
              </td>
            </tr>
            <tr>
              <td style="vertical-align:top;">
                <p style="margin:0 0 2px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Estimated Delivery</p>
                <p style="margin:0;font-weight:700;color:#111827;font-size:15px;">{{DELIVERY_DATE}}</p>
              </td>
              <td style="vertical-align:top;">
                <p style="margin:0 0 2px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Shipping To</p>
                <p style="margin:0;color:#374151;font-size:14px;line-height:1.5;">{{SHIPPING_ADDRESS}}</p>
              </td>
            </tr>
          </table>
        </mj-text>

        <mj-text background-color="#f9fafb" border-radius="12px" padding="16px 24px" border="1px solid #e5e7eb">
          <p style="margin:0 0 10px;font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">Items in this shipment</p>
          <p style="margin:0;font-size:14px;color:#374151;line-height:1.6;">{{ORDER_ITEMS_SUMMARY}}</p>
        </mj-text>

        <mj-spacer height="24px" />
        <mj-button href="{{TRACKING_URL}}" align="center">Track My Package →</mj-button>
        <mj-spacer height="12px" />
        <mj-text color="#9ca3af" font-size="12px" align="center" padding="0">
          Tracking may take up to 24 hours to update after shipment.
        </mj-text>
      </mj-column>
    </mj-section>
    ${footer("#0ea5e9")}
  </mj-body>
</mjml>`.trim();

// ── 14. Password Reset ────────────────────────────────────────────────────────

export const mjmlPasswordReset = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#374151" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f9fafb">
    <mj-section background-color="#111827" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="32px" align="center" padding="0">🔐</mj-text>
        <mj-text color="#ffffff" font-size="22px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">Password Reset Request</mj-text>
        <mj-text color="#9ca3af" font-size="14px" align="center" padding-top="6px" padding-bottom="0">{{COMPANY_NAME}} · Account Security</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="20px">
          We received a request to reset the password for your {{COMPANY_NAME}} account. Click the button below to choose a new password:
        </mj-text>

        <mj-button href="{{RESET_URL}}" align="center">Reset My Password</mj-button>

        <mj-text color="#6b7280" font-size="13px" align="center" padding="16px 0">
          This link expires in <strong>{{EXPIRY_HOURS}} hours</strong>.
        </mj-text>

        <mj-text background-color="#fef3c7" border-radius="10px" padding="16px 20px" border="1px solid #fde68a">
          <p style="margin:0;font-size:14px;color:#92400e;line-height:1.6;">
            ⚠️ <strong>Didn't request this?</strong> You can safely ignore this email. Your password will not change until you click the link above. If you're concerned, please contact our support team immediately.
          </p>
        </mj-text>

        <mj-text background-color="#f9fafb" border-radius="10px" padding="16px 20px" border="1px solid #e5e7eb">
          <table cellpadding="0" cellspacing="0" style="width:100%">
            <tr>
              <td style="padding-bottom:6px;">
                <p style="margin:0;font-size:12px;color:#9ca3af;">Request made from IP address</p>
                <p style="margin:0;font-size:13px;font-weight:600;color:#374151;font-family:monospace;">{{REQUEST_IP}}</p>
              </td>
              <td style="text-align:right;padding-bottom:6px;vertical-align:top;">
                <p style="margin:0;font-size:12px;color:#9ca3af;">Request time</p>
                <p style="margin:0;font-size:13px;font-weight:600;color:#374151;">{{REQUEST_TIME}}</p>
              </td>
            </tr>
          </table>
        </mj-text>

        <mj-text color="#9ca3af" font-size="12px" align="center" padding="16px 0 0">
          If the button above doesn't work, copy and paste this URL into your browser:<br/>
          <a href="{{RESET_URL}}" style="color:#374151;word-break:break-all;">{{RESET_URL}}</a>
        </mj-text>
      </mj-column>
    </mj-section>
    ${footer("#374151")}
  </mj-body>
</mjml>`.trim();

// ── 15. Receipt / Invoice ─────────────────────────────────────────────────────

export const mjmlReceiptInvoice = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#10b981" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f9fafb">
    <mj-section background-color="#111827" padding="32px">
      <mj-column width="60%">
        <mj-text color="#ffffff" font-size="22px" font-weight="800" padding="0">{{COMPANY_NAME}}</mj-text>
        <mj-text color="#9ca3af" font-size="13px" padding-top="4px" padding-bottom="0">Receipt / Invoice</mj-text>
      </mj-column>
      <mj-column width="40%">
        <mj-text color="#9ca3af" font-size="12px" align="right" padding="0">
          <strong style="color:#ffffff;font-size:15px;">#{{INVOICE_NUMBER}}</strong><br/>
          {{INVOICE_DATE}}
        </mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="28px 32px 0">
      <mj-column>
        <mj-text color="#111827" font-size="15px" padding-bottom="20px">
          Hi <strong>{{CUSTOMER_NAME}}</strong>, here's your receipt for your recent purchase. Thank you for your business!
        </mj-text>

        <mj-text background-color="#f9fafb" border-radius="10px" padding="0" border="1px solid #e5e7eb">
          <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
            <thead>
              <tr style="background:#f3f4f6;">
                <th style="padding:12px 16px;text-align:left;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #e5e7eb;">Item</th>
                <th style="padding:12px 16px;text-align:center;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #e5e7eb;">Qty</th>
                <th style="padding:12px 16px;text-align:right;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #e5e7eb;">Price</th>
              </tr>
            </thead>
            <tbody>
              {{ORDER_ITEMS}}
            </tbody>
          </table>
        </mj-text>

        <mj-spacer height="1px" />

        <mj-text background-color="#f9fafb" border-radius="10px" padding="16px 20px" border="1px solid #e5e7eb">
          <table cellpadding="0" cellspacing="0" style="width:100%">
            <tr>
              <td style="padding-bottom:8px;color:#6b7280;font-size:14px;">Subtotal</td>
              <td style="padding-bottom:8px;text-align:right;color:#374151;font-size:14px;">{{SUBTOTAL}}</td>
            </tr>
            <tr>
              <td style="padding-bottom:8px;color:#6b7280;font-size:14px;">Shipping</td>
              <td style="padding-bottom:8px;text-align:right;color:#374151;font-size:14px;">{{SHIPPING_COST}}</td>
            </tr>
            <tr>
              <td style="padding-bottom:8px;color:#6b7280;font-size:14px;">Tax</td>
              <td style="padding-bottom:8px;text-align:right;color:#374151;font-size:14px;">{{TAX}}</td>
            </tr>
            <tr style="border-top:2px solid #e5e7eb;">
              <td style="padding-top:10px;font-weight:800;color:#111827;font-size:16px;">Total</td>
              <td style="padding-top:10px;text-align:right;font-weight:800;color:#111827;font-size:18px;">{{TOTAL}}</td>
            </tr>
          </table>
        </mj-text>

        <mj-text background-color="#f9fafb" border-radius="10px" padding="16px 20px" border="1px solid #e5e7eb">
          <p style="margin:0 0 4px;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;">Shipped To</p>
          <p style="margin:0;font-size:14px;color:#374151;line-height:1.6;">{{SHIPPING_ADDRESS}}</p>
        </mj-text>

        <mj-spacer height="24px" />
        <mj-button href="{{CTA_URL}}" align="center">View Full Invoice →</mj-button>
        <mj-spacer height="16px" />
      </mj-column>
    </mj-section>
    ${footer("#10b981")}
  </mj-body>
</mjml>`.trim();

// ── 16. Payment Failed ────────────────────────────────────────────────────────

export const mjmlPaymentFailed = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#ef4444" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#fff5f5">
    <mj-section background-color="#dc2626" padding="40px 32px">
      <mj-column>
        <mj-text color="#ffffff" font-size="32px" align="center" padding="0">⚠️</mj-text>
        <mj-text color="#ffffff" font-size="22px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">Payment Failed</mj-text>
        <mj-text color="#fca5a5" font-size="14px" align="center" padding-top="6px" padding-bottom="0">Order #{{ORDER_NUMBER}} · Action required</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text color="#4b5563" padding-bottom="16px">
          Hi <strong>{{CUSTOMER_NAME}}</strong>, we were unable to process the payment for your recent order. Please update your payment method to complete your purchase.
        </mj-text>

        <mj-text background-color="#fef2f2" border-radius="10px" padding="16px 20px" border="1px solid #fecaca">
          <table cellpadding="0" cellspacing="0" style="width:100%">
            <tr>
              <td style="padding-bottom:8px;width:50%;vertical-align:top;">
                <p style="margin:0 0 2px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Order</p>
                <p style="margin:0;font-weight:700;color:#111827;font-size:15px;">#{{ORDER_NUMBER}}</p>
              </td>
              <td style="padding-bottom:8px;vertical-align:top;">
                <p style="margin:0 0 2px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Amount Due</p>
                <p style="margin:0;font-weight:800;color:#dc2626;font-size:17px;">{{ORDER_TOTAL}}</p>
              </td>
            </tr>
            <tr>
              <td colspan="2">
                <p style="margin:0 0 2px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.5px;">Reason</p>
                <p style="margin:0;font-size:14px;color:#374151;">{{FAILURE_REASON}}</p>
              </td>
            </tr>
          </table>
        </mj-text>

        <mj-text background-color="#fffbeb" border-radius="10px" padding="14px 18px" border="1px solid #fde68a">
          <p style="margin:0;font-size:14px;color:#92400e;">
            🕐 <strong>Your order is on hold.</strong> We'll keep it reserved for {{HOLD_HOURS}} hours. After that, items may go back to stock.
          </p>
        </mj-text>

        <mj-spacer height="24px" />
        <mj-button href="{{CTA_URL}}" align="center">Update Payment Method →</mj-button>
        <mj-spacer height="12px" />
        <mj-text color="#9ca3af" font-size="12px" align="center" padding="0">
          Need help? Reply to this email or contact our support team.
        </mj-text>
      </mj-column>
    </mj-section>
    ${footer("#dc2626")}
  </mj-body>
</mjml>`.trim();

// ── 12. Product Showcase ──────────────────────────────────────────────────────

export const mjmlProductShowcase = `
<mjml>
  <mj-head>
    <mj-attributes>
      <mj-all font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" />
      <mj-text color="#374151" font-size="15px" line-height="1.7" />
      <mj-button background-color="#0f172a" border-radius="8px" font-size="14px" font-weight="700" padding="14px 32px" color="#ffffff" />
    </mj-attributes>
  </mj-head>
  <mj-body background-color="#f8fafc">
    <mj-section background-color="#0f172a" padding="40px 32px">
      <mj-column>
        <mj-text color="#94a3b8" font-size="12px" font-weight="700" align="center" padding="0" letter-spacing="3px">NEW ARRIVAL</mj-text>
        <mj-text color="#ffffff" font-size="28px" font-weight="800" align="center" padding-top="8px" padding-bottom="0">{{PRODUCT_NAME}}</mj-text>
        <mj-text color="#64748b" font-size="15px" align="center" padding-top="6px" padding-bottom="0">{{PRODUCT_TAGLINE}}</mj-text>
      </mj-column>
    </mj-section>

    <mj-section background-color="#ffffff" padding="36px 32px">
      <mj-column>
        <mj-text background-color="#0f172a" border-radius="16px" padding="40px" align="center">
          <p style="margin:0;font-size:72px;line-height:1;">{{PRODUCT_EMOJI}}</p>
        </mj-text>

        <mj-spacer height="24px" />

        <mj-text font-size="19px" font-weight="700" color="#111827" padding-bottom="8px" align="center">{{PRODUCT_NAME}}</mj-text>
        <mj-text color="#4b5563" align="center" padding-bottom="8px">{{PRODUCT_DESCRIPTION}}</mj-text>
        <mj-text color="#0f172a" font-size="28px" font-weight="800" align="center" padding-bottom="24px">{{PRODUCT_PRICE}}</mj-text>

        <mj-text padding="0 0 16px">
          <table cellpadding="0" cellspacing="0" style="width:100%">
            <tr>
              <td style="padding:8px 0;border-top:1px solid #f1f5f9;color:#374151;font-size:14px;">✅ {{FEATURE_1}}</td>
            </tr>
            <tr>
              <td style="padding:8px 0;border-top:1px solid #f1f5f9;color:#374151;font-size:14px;">✅ {{FEATURE_2}}</td>
            </tr>
            <tr>
              <td style="padding:8px 0;border-top:1px solid #f1f5f9;border-bottom:1px solid #f1f5f9;color:#374151;font-size:14px;">✅ {{FEATURE_3}}</td>
            </tr>
          </table>
        </mj-text>

        <mj-spacer height="24px" />
        <mj-button href="{{CTA_URL}}" align="center">Shop Now →</mj-button>
      </mj-column>
    </mj-section>
    ${footer("#0f172a")}
  </mj-body>
</mjml>`.trim();

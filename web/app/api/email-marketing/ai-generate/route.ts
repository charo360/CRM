import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";

type Product = { name: string; price: string; description: string; image_url?: string };

// ── ESP merge-tag registry ────────────────────────────────────────────────────

type EspTokens = {
  firstName:   string;
  lastName:    string;
  email:       string;
  unsubscribe: string;
  viewBrowser: string;
  name:        string;   // display label for prompts
  notes:       string;   // provider-specific design advice
};

const ESP_TOKENS: Record<string, EspTokens> = {
  platform: {
    name: "Zilo Platform",
    firstName:   "{{FIRST_NAME}}",
    lastName:    "{{LAST_NAME}}",
    email:       "{{EMAIL}}",
    unsubscribe: "{{UNSUBSCRIBE_URL}}",
    viewBrowser: "{{VIEW_BROWSER_URL}}",
    notes: "Standard HTML email. MJML renders well.",
  },
  mailchimp: {
    name: "Mailchimp (Mandrill)",
    firstName:   "*|FNAME|*",
    lastName:    "*|LNAME|*",
    email:       "*|EMAIL|*",
    unsubscribe: "*|UNSUB|*",
    viewBrowser: "*|ARCHIVE|*",
    notes: "Mailchimp blocks external CSS. Avoid background-image on <div> (use mj-section bg instead). Keep image-to-text ratio ~60:40 to avoid spam filters. All merge tags use *|TAG|* syntax.",
  },
  klaviyo: {
    name: "Klaviyo",
    firstName:   "{{ first_name }}",
    lastName:    "{{ last_name }}",
    email:       "{{ email }}",
    unsubscribe: "{% unsubscribe_link %}",
    viewBrowser: "{{ view_in_browser_url }}",
    notes: "Klaviyo renders complex HTML well. Supports Jinja2-style conditionals: {% if first_name %}Hi {{ first_name }}{% else %}Hi there{% endif %}. Use {{ organization.name }} for brand name if needed.",
  },
  sendgrid: {
    name: "SendGrid",
    firstName:   "{{{first_name}}}",
    lastName:    "{{{last_name}}}",
    email:       "{{{email}}}",
    unsubscribe: "{{{unsubscribe}}}",
    viewBrowser: "{{{weblink}}}",
    notes: "SendGrid uses triple-brace {{{var}}} for HTML-safe substitution. Avoid inline event handlers. Test through SendGrid's Email Validation API.",
  },
  brevo: {
    name: "Brevo (Sendinblue)",
    firstName:   "{{contact.FIRSTNAME}}",
    lastName:    "{{contact.LASTNAME}}",
    email:       "{{contact.EMAIL}}",
    unsubscribe: "{unsubscribe}",
    viewBrowser: "{mirror}",
    notes: "Brevo renders HTML reliably. Use {{contact.ATTRIBUTE_NAME}} for custom attributes. Brevo automatically appends the unsubscribe footer if {unsubscribe} is present.",
  },
  mailgun: {
    name: "Mailgun",
    firstName:   "%recipient.first_name%",
    lastName:    "%recipient.last_name%",
    email:       "%recipient.email%",
    unsubscribe: "%unsubscribe_url%",
    viewBrowser: "",
    notes: "Mailgun uses %recipient.variable% syntax for batch personalization. Keep HTML under 100KB. Avoid JavaScript.",
  },
  smtp: {
    name: "Custom SMTP",
    firstName:   "{{FIRST_NAME}}",
    lastName:    "{{LAST_NAME}}",
    email:       "{{EMAIL}}",
    unsubscribe: "{{UNSUBSCRIBE_URL}}",
    viewBrowser: "{{VIEW_BROWSER_URL}}",
    notes: "Custom SMTP — placeholders will be replaced server-side. Use simple {{VAR}} syntax that your templating layer can parse.",
  },
};

// ── Colour maps ───────────────────────────────────────────────────────────────

const THEME_COLORS: Record<string, string> = {
  zilo: "#009b3a", indigo: "#6366f1", red: "#ef4444", green: "#10b981",
  blue: "#3b82f6", amber: "#f59e0b", dark: "#0f172a", purple: "#8b5cf6", orange: "#f97316",
};
const THEME_DARK: Record<string, string> = {
  zilo: "#007a2e", indigo: "#4f46e5", red: "#dc2626", green: "#059669",
  blue: "#2563eb", amber: "#d97706", dark: "#020617", purple: "#7c3aed", orange: "#ea580c",
};

// ── Email type intelligence ───────────────────────────────────────────────────

export type DesignLevel = "rich" | "moderate" | "plain";
export type CopyFramework = "AIDA" | "PAS" | "BAB" | "storytelling" | "direct";

export type EmailAnalysis = {
  email_type: string;
  design_level: DesignLevel;
  framework: CopyFramework;
  tip: string;
  images_recommendation: string;
};

function analyzeEmailType(description: string, products: Product[], heroImageUrl: string): EmailAnalysis {
  const d = description.toLowerCase();

  // ── Plain text triggers ───────────────────────────────────────────────────
  const isWinBack    = /win.back|miss you|haven.t heard|come back|we.ve missed|re.engage|lapsed/i.test(d);
  const isPersonal   = /personal|from the (ceo|founder|team)|just wanted|checking in|hey |hi ,/i.test(d);
  const isTransact   = /receipt|order confirm|password|reset|shipping|delivered|invoice|account/i.test(d);
  const isColdOutr   = /cold|outreach|first email|introduction|reach out/i.test(d);

  // ── Moderate triggers (clean design, no heavy visuals) ────────────────────
  const isNewsletter = /newsletter|digest|weekly|monthly|roundup|curated|reading|links/i.test(d);
  const isWelcome    = /welcome|onboard|getting started|new member|new subscriber|thank you for joining/i.test(d);
  const isAnnounce   = /announce|feature update|changelog|new release|launch|product update|we.re excited/i.test(d);
  const isEducation  = /tips|guide|how to|learn|tutorial|course|webinar|educational/i.test(d);

  // ── Rich triggers (full visual design) ───────────────────────────────────
  const isSale       = /sale|discount|off|promo|deal|coupon|flash|limited time|only.*hours|save/i.test(d);
  const isProduct    = products.length > 0 || /product|collection|shop|store|catalog|new arrival/i.test(d);
  const isSeasonal   = /black friday|cyber monday|christmas|holiday|halloween|mother.s day|valentine|summer|winter/i.test(d);
  const isEvent      = /event|conference|webinar|live|concert|festival|invitation|rsvp/i.test(d);

  // ── Decide design level ───────────────────────────────────────────────────
  let design_level: DesignLevel = "moderate";
  if (isTransact || isWinBack || isPersonal || isColdOutr) design_level = "plain";
  else if (isSale || isSeasonal || isEvent || (isProduct && products.length > 0)) design_level = "rich";
  else if (isNewsletter || isWelcome || isAnnounce || isEducation) design_level = "moderate";

  // ── Override: if user provided hero/product images, bump to rich ──────────
  const hasImages = heroImageUrl || products.some(p => p.image_url);
  if (hasImages && design_level !== "plain") design_level = "rich";

  // ── Pick copywriting framework ────────────────────────────────────────────
  let framework: CopyFramework = "AIDA";
  if (isWinBack || isPersonal || isColdOutr) framework = "storytelling";
  else if (isSale || isProduct || isSeasonal) framework = "AIDA";
  else if (isNewsletter || isEducation) framework = "direct";
  else if (isAnnounce) framework = "BAB";
  else if (/problem|struggle|challenge|pain|frustrat/i.test(d)) framework = "PAS";

  // ── Build email_type label ────────────────────────────────────────────────
  let email_type = "Promotional";
  if (isTransact)   email_type = "Transactional";
  else if (isWinBack)  email_type = "Win-back";
  else if (isPersonal) email_type = "Personal / Founder";
  else if (isColdOutr) email_type = "Cold outreach";
  else if (isWelcome)  email_type = "Welcome";
  else if (isNewsletter) email_type = "Newsletter";
  else if (isAnnounce)  email_type = "Product announcement";
  else if (isEducation) email_type = "Educational";
  else if (isSeasonal)  email_type = "Seasonal campaign";
  else if (isEvent)     email_type = "Event invitation";
  else if (isSale)      email_type = "Flash sale";

  // ── Marketing tip ─────────────────────────────────────────────────────────
  const tips: Record<string, string> = {
    "Transactional":        "Transactional emails get 8× higher open rates than promos. Keep them clean and functional — no heavy design needed.",
    "Win-back":             "Plain-text win-back emails from a 'real person' convert up to 40% better than designed ones. Authenticity wins.",
    "Personal / Founder":   "Looks like a personal email — plain text with a direct voice will feel more genuine and drive more replies.",
    "Cold outreach":        "Cold emails should look like they came from a person, not a brand. Plain text, short, one clear ask.",
    "Welcome":              "Welcome emails have 4× the open rate of regular campaigns. A clean design with a clear next step outperforms flashy.",
    "Newsletter":           "Newsletters work best with a clean reading layout — focus on content hierarchy over heavy visuals.",
    "Product announcement": "Announcements do well with a Before-After-Bridge (BAB) structure — where you were, where you are now, what that means for the reader.",
    "Educational":          "Educational emails convert best when they lead with value immediately. Use direct, benefit-first copy.",
    "Seasonal campaign":    "Seasonal emails are the place to go bold — rich color, urgency, and product visuals drive click-through.",
    "Event invitation":     "Event emails should create FOMO fast. Date, benefit, and CTA above the fold.",
    "Flash sale":           "Flash sale emails live and die by urgency. Big price, big button, short copy — AIDA in 5 seconds.",
    "Promotional":          "Great promo emails lead with the offer, not the brand. Show the value first, then who it's from.",
  };

  const imagesNotes: Record<DesignLevel, string> = {
    rich:     "Images will make this email pop — use your hero and product photos for maximum impact.",
    moderate: "A few brand visuals help, but great copy is more important than heavy imagery for this type.",
    plain:    "Images would actually hurt this email. The plain, personal look is what makes it work.",
  };

  return {
    email_type,
    design_level,
    framework,
    tip: tips[email_type] ?? tips["Promotional"],
    images_recommendation: imagesNotes[design_level],
  };
}

// ── Prompt builder ────────────────────────────────────────────────────────────

type EmailLink = { label: string; url: string };

function extractYouTubeThumbnail(url: string): string {
  const m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  return m ? `https://img.youtube.com/vi/${m[1]}/hqdefault.jpg` : "";
}

function buildPrompt(
  description: string,
  brand: string,
  products: Product[],
  theme: string,
  logoUrl: string,
  heroImageUrl: string,
  analysis: EmailAnalysis,
  links: EmailLink[],
  videoUrl: string,
  provider: string,
): string {
  const accent    = THEME_COLORS[theme] ?? "#009b3a";
  const dark      = THEME_DARK[theme]   ?? "#007a2e";
  const brandName = brand || "the brand";
  const { design_level, framework, email_type } = analysis;

  // ── ESP token lookup ──────────────────────────────────────────────────────
  const esp = ESP_TOKENS[provider] ?? ESP_TOKENS.platform;
  const espHeader = `EMAIL PROVIDER: ${esp.name}
MERGE TAG SYNTAX — use these EXACT tokens for personalization (wrong syntax breaks the ESP):
  • First name: ${esp.firstName}
  • Last name:  ${esp.lastName}
  • Email:      ${esp.email}
  • Unsubscribe link: ${esp.unsubscribe}
  ${esp.viewBrowser ? `• View in browser: ${esp.viewBrowser}` : ""}
ESP NOTES: ${esp.notes}`;

  // ── Link library ──────────────────────────────────────────────────────────
  const filledLinks = links.filter(l => l.url.trim());
  const primaryCtaUrl = filledLinks.find(l =>
    /primary|cta|main|shop|buy|get started|start/i.test(l.label)
  )?.url ?? filledLinks[0]?.url ?? "";

  const linksGuide = filledLinks.length > 0
    ? `LINKS — use these real URLs for ALL buttons and CTAs (never write {{CTA_URL}} when real URLs are given):\n${filledLinks.map(l => `  • ${l.label}: ${l.url}`).join("\n")}\nThe most important CTA should use: ${primaryCtaUrl}`
    : `CTA URL: use the placeholder {{CTA_URL}} for all main CTA buttons.`;

  // ── Video block ───────────────────────────────────────────────────────────
  const videoThumb = videoUrl.trim() ? extractYouTubeThumbnail(videoUrl.trim()) : "";
  const videoBlockSpec = videoUrl.trim() && design_level !== "plain"
    ? `
VIDEO BLOCK — include this section directly after the hero banner:
  <mj-section background-url="${videoThumb || ""}" background-size="cover" background-color="#0f172a" padding="64px 0">
    <mj-column>
      <mj-text align="center" padding="0">
        <a href="${videoUrl.trim()}" style="display:inline-flex;align-items:center;justify-content:center;width:72px;height:72px;background:rgba(255,255,255,0.95);border-radius:50%;text-decoration:none;box-shadow:0 4px 28px rgba(0,0,0,0.5);">
          <span style="font-size:30px;margin-left:5px;color:#0f172a;">▶</span>
        </a>
      </mj-text>
      <mj-spacer height="14px" />
      <mj-text align="center" color="#ffffff" font-size="14px" font-weight="600" letter-spacing="0.5px" padding="0">▶ Watch the video</mj-text>
    </mj-column>
  </mj-section>
If the background image above is empty, use background-color="${accent}" instead.`
    : "";

  const videoLinkForPlain = videoUrl.trim() && design_level === "plain"
    ? `\n\nInclude a simple inline text link to the video: "▶ Watch here: ${videoUrl.trim()}"`
    : "";

  // ── Allowed image URLs ────────────────────────────────────────────────────
  const allowedUrls: string[] = [];
  if (logoUrl)      allowedUrls.push(`"${logoUrl}" (logo)`);
  if (heroImageUrl && design_level !== "plain") allowedUrls.push(`"${heroImageUrl}" (hero banner)`);
  if (videoThumb && design_level !== "plain")   allowedUrls.push(`"${videoThumb}" (video thumbnail — use ONLY inside the VIDEO BLOCK section bg)`);
  products.forEach((p, i) => {
    if (p.image_url && design_level !== "plain") allowedUrls.push(`"${p.image_url}" (product ${i+1}: ${p.name})`);
  });
  const urlRules = allowedUrls.length
    ? `These are the ONLY external image URLs you may use:\n${allowedUrls.map(u => "  • " + u).join("\n")}`
    : "Do NOT use any external image URLs.";

  // Framework copy guidance
  const frameworkGuide: Record<CopyFramework, string> = {
    AIDA: `Write using AIDA: Attention (bold headline that stops the scroll) → Interest (what's in it for them) → Desire (make them want it) → Action (one clear CTA).`,
    PAS:  `Write using PAS: Problem (name the pain the reader feels) → Agitate (make them feel the cost of inaction) → Solution (position the offer as the clear answer).`,
    BAB:  `Write using BAB: Before (reader's current frustrating state) → After (vivid picture of life after the solution) → Bridge (your product/service is that bridge).`,
    storytelling: `Write in a personal, conversational tone — like a message from a real person. Short sentences. Empathy first. One clear, low-friction ask at the end.`,
    direct: `Write direct, benefit-first copy. Lead with the most valuable thing immediately. No warm-up. Every sentence earns its place.`,
  };

  // ── PLAIN TEXT email ──────────────────────────────────────────────────────
  if (design_level === "plain") {
    return `You are an elite email copywriter and marketing strategist. Write a ${email_type} email.

BRIEF: ${description}
BRAND: ${brandName}
EMAIL TYPE: ${email_type}
COPY FRAMEWORK: ${frameworkGuide[framework]}
${espHeader}

Generate a COMPLETE, VALID MJML 4 email that looks like a personal plain-text message — NOT a marketing flyer.

DESIGN RULES (strict):
• Background: #ffffff everywhere — no colored sections, no colored header strip
• Font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif — 15px, color #111827, line-height 1.8
• Single column, max-width 580px, padding 40px 32px
• ${logoUrl ? `Logo: small <mj-image src="${logoUrl}" width="100px" align="left" padding="0 0 28px 0" /> — left-aligned for a personal feel` : "No logo — purely text"}
• NO hero image, NO colored backgrounds, NO big buttons, NO product cards, NO decorative elements
• The CTA is a simple inline text link styled: color:${accent};font-weight:600;text-decoration:underline;
• Footer: tiny 12px #9ca3af text only — <a href="${esp.unsubscribe}">Unsubscribe</a>${esp.viewBrowser ? ` · <a href="${esp.viewBrowser}">View in browser</a>` : ""}

COPY RULES:
• ${frameworkGuide[framework]}
• Write genuinely — no corporate jargon, no exclamation-mark spam
• Subject line: write 3 subject line options as HTML comments at the very top: <!-- SUBJECT: option1 | option2 | option3 -->
• Greeting: use ${esp.firstName} where appropriate (e.g. "Hi ${esp.firstName},")
• ${linksGuide}${videoLinkForPlain}

OUTPUT: ONLY raw MJML XML starting with <mjml> and ending with </mjml>. Nothing else.`.trim();
  }

  // ── MODERATE design email ──────────────────────────────────────────────────
  if (design_level === "moderate") {
    const logoBlock = logoUrl
      ? `<mj-image src="${logoUrl}" width="130px" alt="${brandName}" align="center" padding="0 0 4px 0" />`
      : `<mj-text align="center" padding="0"><span style="font-size:22px;font-weight:800;color:#ffffff;">${brandName}</span></mj-text>`;

    return `You are an elite email designer and marketing strategist. Generate a clean, professional ${email_type} email.

BRIEF: ${description}
BRAND: ${brandName}
EMAIL TYPE: ${email_type}
COPY FRAMEWORK: ${frameworkGuide[framework]}
${espHeader}

DESIGN PHILOSOPHY: Clean, content-first. No heavy visuals. Strong typography, ample whitespace, one clear CTA.
${urlRules}

━━━━━━━━━━━━━━━━━━━━━━━
DESIGN SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━
Font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif
Background: #f4f4f5 | Card: #ffffff | Accent: ${accent} | Muted: #6b7280

LAYOUT:
1. HEADER: mj-section bg="${accent}" padding="20px 0"
   • ${logoBlock}

2. INTRO: mj-section bg="#ffffff" padding="40px 32px"
   • Bold 26px headline (${accent} first word or accent underline via <span>)
   • 16px #374151 body paragraph — ${frameworkGuide[framework]}
   • mj-spacer 20px
   • <mj-button background-color="${accent}" border-radius="8px" font-size="15px" padding="12px 32px" href="${primaryCtaUrl || "{{CTA_URL}}"}">CTA BUTTON</mj-button>

${videoBlockSpec ? `2b.${videoBlockSpec}\n\n` : ""}3. CONTENT SECTION: 2-3 short content blocks (mj-section bg="#ffffff" with mj-divider between each)
   • Each: small bold label (${accent} color, 11px uppercase), heading 18px, 14px body text

4. FOOTER: mj-section bg="#f9fafb" padding="24px"
   • 12px #9ca3af centred text
   • <a href="${esp.unsubscribe}" style="color:${accent};">Unsubscribe</a>${esp.viewBrowser ? ` · <a href="${esp.viewBrowser}" style="color:${accent};">View in browser</a>` : ""}

LINKS:
${linksGuide}

COPY RULES:
• ${frameworkGuide[framework]}
• Write real campaign-specific copy — no placeholders
• Greeting: use ${esp.firstName} where appropriate
• Subject line options as first comment: <!-- SUBJECT: opt1 | opt2 | opt3 -->

OUTPUT: ONLY raw MJML XML from <mjml> to </mjml>. Nothing else.`.trim();
  }

  // ── RICH design email ──────────────────────────────────────────────────────
  const logoBlock = logoUrl
    ? `<mj-image src="${logoUrl}" width="150px" alt="${brandName}" align="center" padding="0 0 6px 0" />`
    : `<mj-text align="center" padding="0"><span style="font-size:26px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">${brandName}</span></mj-text>`;

  const heroSpec = heroImageUrl
    ? `HERO: <mj-section background-url="${heroImageUrl}" background-size="cover" background-position="center" background-color="${accent}" padding="60px 40px">
   • Semi-transparent overlay via mj-text: <div style="background:rgba(0,0,0,0.42);margin:-20px;padding:50px 24px;text-align:center;">
   • White bold headline 38px (font-weight:900) — punchy, campaign-specific
   • White 17px subtext, opacity:0.9
   • </div>
   • <mj-spacer height="24px"/>
   • White pill CTA: <mj-button background-color="#ffffff" color="${accent}" border-radius="50px" font-size="16px" font-weight="700" padding="14px 40px" href="{{CTA_URL}}">`
    : `HERO: <mj-section background-color="${accent}" padding="56px 40px">
   • Bold white headline 38px (font-weight:900)
   • White 17px subtext
   • <mj-spacer height="22px"/>
   • White pill CTA: <mj-button background-color="#ffffff" color="${accent}" border-radius="50px" font-size="16px" font-weight="700" padding="14px 40px" href="{{CTA_URL}}">`;

  const realProducts = products.filter(p => p.name.trim());
  const productLayout = realProducts.length === 2 ? "TWO-COLUMN" : realProducts.length === 3 ? "THREE-COLUMN" : "SINGLE-COLUMN";

  const productCards = realProducts.map((p, i) => {
    const imgLine = p.image_url
      ? `   - TOP: <mj-image src="${p.image_url}" width="100%" padding="0" alt="${p.name}" />`
      : `   - TOP: large relevant emoji (54px centered) inside mj-text — pick a highly relevant emoji for "${p.name}"`;
    return `  Product ${i+1}: "${p.name}"${p.price ? ` | $${p.price}` : ""}${p.description ? ` | ${p.description}` : ""}
${imgLine}
   - NAME: bold 17px #111827 centered
   - PRICE: ${accent} badge <span style="background:${accent};color:#fff;font-size:14px;font-weight:700;padding:4px 14px;border-radius:20px;">${p.price || "View price"}</span>
   - DESC: 13px #6b7280 centered, line-height:1.5
   - CTA LINK: <a href="{{CTA_URL}}" style="color:${accent};font-weight:700;font-size:14px;text-decoration:none;">Shop Now →</a>
   - BOTTOM BAR: <div style="height:4px;background:${accent};border-radius:0 0 12px 12px;"></div>`;
  }).join("\n");

  return `You are the world's best email designer AND marketing strategist. Generate a complete ${email_type} email.

BRIEF: ${description}
BRAND: ${brandName}
EMAIL TYPE: ${email_type}
COPY FRAMEWORK: ${frameworkGuide[framework]}
${espHeader}
${urlRules}

━━━━━━━━━━━━━━━━━━━
DESIGN SYSTEM
━━━━━━━━━━━━━━━━━━━
Font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif
Body bg: #f4f4f5 | Cards: #ffffff | Accent: ${accent} | Dark accent: ${dark}
Card style: border-radius:12px, border:1px solid #e5e7eb

REQUIRED SECTIONS:
1. HEADER: mj-section bg="${accent}" padding="20px 0"
   • ${logoBlock}

2. ${heroSpec}

${videoBlockSpec ? `2b.${videoBlockSpec}\n` : ""}3. BENEFITS BAR: mj-section bg="#ffffff" padding="22px 16px"
   • 3 mj-columns — each: emoji (32px), bold 14px stat, 12px #6b7280 label
   • Pick 3 benefits that genuinely match this campaign (shipping, guarantee, social proof, speed, quality, savings…)

${realProducts.length > 0 ? `4. PRODUCTS (${productLayout} layout):
   mj-section bg="#f4f4f5" padding="28px 14px"
   • Section subheading: bold 20px #111827 centered
   • mj-spacer 14px
${productCards}

5. ` : "4. "}CTA STRIP: mj-section bg="${accent}" padding="48px 32px"
   • Bold 24px white headline (urgency/benefit)
   • 15px white/80% supporting line
   • mj-spacer 20px
   • <mj-button background-color="#ffffff" color="${accent}" border-radius="50px" font-size="16px" font-weight="700" padding="14px 40px" href="${primaryCtaUrl || "{{CTA_URL}}"}">BUTTON</mj-button>

LAST. FOOTER: mj-section bg="#f9fafb" padding="26px 24px"
   • © 2025 ${brandName}. All rights reserved. — 12px #9ca3af
   • <a href="${esp.unsubscribe}" style="color:${accent};">Unsubscribe</a>${esp.viewBrowser ? ` · <a href="${esp.viewBrowser}" style="color:${accent};">View in browser</a>` : ""} — 12px
   • "Sent with ♥ by Zilo" — 11px #d1d5db
${filledLinks.length > 1 ? `   • Additional footer links: ${filledLinks.slice(1).map(l => `<a href="${l.url}" style="color:${accent};">${l.label}</a>`).join(" · ")}` : ""}

LINKS:
${linksGuide}

COPY RULES:
• ${frameworkGuide[framework]}
• Write REAL compelling copy specific to this campaign. Zero placeholders.
• Greeting: use ${esp.firstName} where appropriate (e.g. "Hi ${esp.firstName},")
• Subject options as first comment: <!-- SUBJECT: opt1 | opt2 | opt3 -->

OUTPUT: ONLY raw MJML XML from <mjml> to </mjml>. Nothing else.`.trim();
}

// ── Image prompt builders ─────────────────────────────────────────────────────

function heroImagePrompt(emailType: string, description: string, brand: string, accent: string): string {
  const moods: Record<string, string> = {
    "Flash sale":           "Dynamic urgency. Vibrant saturated colors. Shopping excitement. Studio product lighting.",
    "Seasonal campaign":    "Festive warm atmosphere. Seasonal mood. Celebratory and rich.",
    "Event invitation":     "Elegant venue or atmospheric scene. Upscale, premium feel. Soft bokeh.",
    "Product announcement": "Clean studio reveal aesthetic. Minimalist. Exciting product focus.",
    "Welcome":              "Warm, friendly, optimistic. Soft natural daylight. Inviting.",
    "Newsletter":           "Clean editorial lifestyle. Professional workspace or lifestyle scene.",
    "Promotional":          "Bold commercial photography. Eye-catching. Modern and aspirational.",
  };
  const mood = moods[emailType] ?? "Professional, modern, aspirational commercial photography.";
  return (
    `${mood} ` +
    `Wide landscape hero banner image for a ${emailType} email campaign. ` +
    `Topic: ${description}. Brand: ${brand}. Color palette inspired by ${accent}. ` +
    `Photorealistic. High resolution. No text, no words, no logos, no watermarks.`
  );
}

function productImagePrompt(name: string, desc: string, emailType: string, accent: string): string {
  return (
    `Professional product photography. Clean white or very light studio background. ` +
    `Perfect studio lighting. Square format. ` +
    `Product: ${name}. ${desc ? `Details: ${desc}. ` : ""}` +
    `Style: modern commercial ${emailType.toLowerCase()} campaign imagery. ` +
    `Color accent reference: ${accent}. ` +
    `Photorealistic. High resolution. No text, no watermarks, no logos.`
  );
}

async function generateImage(
  prompt: string,
  imageType: "hero" | "product",
  auth: string,
): Promise<string | null> {
  try {
    const res = await fetch(`${BACKEND}/email-marketing/generate-image`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify({ prompt, image_type: imageType }),
    });
    if (!res.ok) return null;
    const { url } = await res.json() as { url?: string };
    return url ?? null;
  } catch {
    return null;
  }
}

// ── Route handler ─────────────────────────────────────────────────────────────

// Image gen + MJML compile can take 60–120s for rich emails
export const maxDuration = 180;

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";

  let body: {
    description?: string;
    brand?: string;
    products?: Product[];
    theme?: string;
    logo_url?: string;
    hero_image_url?: string;
    video_url?: string;
    links?: EmailLink[];
    provider?: string;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const {
    description = "",
    brand = "",
    products: rawProducts = [],
    theme = "zilo",
    logo_url = "",
    hero_image_url: userHeroUrl = "",
    video_url = "",
    links = [],
    provider = "platform",
  } = body;

  if (!description.trim()) {
    return NextResponse.json({ error: "description is required" }, { status: 400 });
  }

  const accent = THEME_COLORS[theme] ?? "#009b3a";

  // 1. Classify the campaign (local, instant)
  const analysis = analyzeEmailType(description, rawProducts, userHeroUrl.trim());

  // 2. Auto-generate images for rich emails when user didn't provide them
  let heroImageUrl = userHeroUrl.trim();
  const products   = rawProducts.map(p => ({ ...p }));
  const aiImages: { hero: boolean; products: number[] } = { hero: false, products: [] };

  if (analysis.design_level === "rich") {
    const heroTask = !heroImageUrl
      ? generateImage(heroImagePrompt(analysis.email_type, description, brand, accent), "hero", auth)
      : Promise.resolve<string | null>(null);

    const productTasks = products.map((p, i) =>
      p.name.trim() && !p.image_url?.trim()
        ? generateImage(productImagePrompt(p.name, p.description, analysis.email_type, accent), "product", auth)
        : Promise.resolve<string | null>(null)
    );

    // Run all image generation in parallel
    const [heroUrl, ...productUrls] = await Promise.all([heroTask, ...productTasks]);

    if (heroUrl) { heroImageUrl = heroUrl; aiImages.hero = true; }
    productUrls.forEach((url, i) => {
      if (url) { products[i] = { ...products[i], image_url: url }; aiImages.products.push(i); }
    });
  }

  // 3. Build the MJML prompt with all available images + links + video + provider
  const prompt = buildPrompt(description, brand, products, theme, logo_url.trim(), heroImageUrl, analysis, links, video_url, provider);

  // 4. Call Claude to write the MJML
  try {
    const res = await fetch(`${BACKEND}/assistant/ai-draft`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify({ prompt, model: "claude-sonnet-4-6" }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({})) as { detail?: string };
      return NextResponse.json({ error: err.detail ?? "AI service error" }, { status: res.status });
    }

    const data = await res.json() as { reply?: string };
    let mjml = (data.reply ?? "").trim();
    mjml = mjml.replace(/^```(?:mjml|xml|html)?\s*/i, "").replace(/\s*```$/i, "").trim();

    if (!mjml.startsWith("<mjml>")) {
      return NextResponse.json({ error: "AI did not return valid MJML" }, { status: 502 });
    }

    // Extract subject options from AI comment <!-- SUBJECT: a | b | c -->
    const subjectMatch = mjml.match(/<!--\s*SUBJECT:\s*([^>]+?)-->/i);
    const subjectOptions = subjectMatch
      ? subjectMatch[1].split("|").map(s => s.trim()).filter(Boolean)
      : [];

    return NextResponse.json({
      mjml,
      analysis,
      subject_options: subjectOptions,
      ai_images: aiImages,  // tells frontend which images were AI-generated
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

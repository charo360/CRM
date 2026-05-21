import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";

type Product = { name: string; price: string; description: string; image_url?: string };

const THEME_COLORS: Record<string, string> = {
  zilo:   "#009b3a",
  indigo: "#6366f1",
  red:    "#ef4444",
  green:  "#10b981",
  blue:   "#3b82f6",
  amber:  "#f59e0b",
  dark:   "#0f172a",
  purple: "#8b5cf6",
  orange: "#f97316",
};

const THEME_DARK: Record<string, string> = {
  zilo:   "#007a2e",
  indigo: "#4f46e5",
  red:    "#dc2626",
  green:  "#059669",
  blue:   "#2563eb",
  amber:  "#d97706",
  dark:   "#020617",
  purple: "#7c3aed",
  orange: "#ea580c",
};

function buildPrompt(
  description: string,
  brand: string,
  products: Product[],
  theme: string,
  logoUrl: string,
  heroImageUrl: string,
): string {
  const accent = THEME_COLORS[theme] ?? "#009b3a";
  const dark   = THEME_DARK[theme]   ?? "#007a2e";
  const brandName = brand || "the brand";

  // ── Logo block ──────────────────────────────────────────────────────────────
  const logoBlock = logoUrl
    ? `<mj-image src="${logoUrl}" width="150px" alt="${brandName}" align="center" padding="0 0 6px 0" />`
    : `<mj-text align="center" padding="0"><span style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;font-size:26px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">${brandName}</span></mj-text>`;

  // ── Allowed external URLs list ───────────────────────────────────────────────
  const allowedUrls: string[] = [];
  if (logoUrl)      allowedUrls.push(`"${logoUrl}" (logo)`);
  if (heroImageUrl) allowedUrls.push(`"${heroImageUrl}" (hero banner)`);
  products.forEach((p, i) => { if (p.image_url) allowedUrls.push(`"${p.image_url}" (product ${i+1}: ${p.name})`); });
  const urlRules = allowedUrls.length
    ? `ALLOWED external image URLs (use EXACTLY as written, these are the ONLY ones permitted):\n${allowedUrls.map(u => "  • " + u).join("\n")}`
    : "NO external image URLs are allowed — use emoji/color placeholders instead.";

  // ── Hero section spec ────────────────────────────────────────────────────────
  const heroSpec = heroImageUrl
    ? `HERO BANNER — use background-url="${heroImageUrl}" on the mj-section:
• <mj-section background-url="${heroImageUrl}" background-size="cover" background-position="center center" background-color="${accent}" padding="60px 40px">
• Add a semi-transparent dark overlay using mj-text with <div style="background:rgba(0,0,0,0.45);margin:-20px;padding:40px 20px;border-radius:0;">…text…</div>
• Large bold white headline (36px, font-weight:800) — campaign-specific, punchy
• White subtext (18px, opacity:0.9) — one compelling sentence
• White pill button: <mj-button background-color="#ffffff" color="${accent}" border-radius="50px" font-size="16px" font-weight="700" padding="14px 40px" href="{{CTA_URL}}">CTA TEXT</mj-button>`
    : `HERO BANNER — full-width color block:
• <mj-section background-color="${accent}" padding="52px 40px">
• Large bold white headline (36px, font-weight:800) — campaign-specific, punchy
• White subtext (18px, opacity 80%) — one compelling sentence
• <mj-spacer height="20px" />
• White pill button: <mj-button background-color="#ffffff" color="${accent}" border-radius="50px" font-size="16px" font-weight="700" padding="14px 40px" href="{{CTA_URL}}">CTA TEXT</mj-button>`;

  // ── Products spec ────────────────────────────────────────────────────────────
  const realProducts = products.filter(p => p.name.trim());
  const hasProducts  = realProducts.length > 0;
  const productLayout = realProducts.length === 2 ? "TWO-COLUMN side by side" :
                        realProducts.length === 3 ? "THREE-COLUMN side by side" :
                        "ONE-COLUMN stacked (full-width cards)";

  const productDetails = realProducts.map((p, i) => {
    const lines = [`  Product ${i+1}: "${p.name}"`];
    if (p.price)     lines.push(`    price: "${p.price}"`);
    if (p.description) lines.push(`    description: "${p.description}"`);
    if (p.image_url)  lines.push(`    image: USE <mj-image src="${p.image_url}" width="100%" border-radius="12px 12px 0 0" padding="0" alt="${p.name}" />`);
    else              lines.push(`    image: USE a large thematically-relevant emoji (52px centered) as placeholder — no <mj-image>`);
    return lines.join("\n");
  }).join("\n");

  const productSection = hasProducts ? `
SECTION — PRODUCTS (layout: ${productLayout})
• Outer mj-section: background-color="#f4f4f5", padding="32px 16px"
• Section heading: bold 22px #111827 centered, campaign-relevant sub-heading (e.g. "Featured Products", "Shop the Collection")
• mj-spacer height="16px"
${realProducts.length <= 3 ? `• Use ${realProducts.length} mj-column(s) in one mj-section, container-background-color="#ffffff" for each` : `• Stack one product per mj-section row`}
Each product card:
${productDetails}
  - Product name: bold 17px #111827, align="center", padding="12px 16px 4px"
  - Price: <span style="background:${accent};color:#fff;font-size:14px;font-weight:700;padding:4px 14px;border-radius:20px;display:inline-block;"> shown in centered mj-text
  - Description: 13px #6b7280 centered, padding="6px 16px 10px", line-height:1.5
  - Bottom accent bar: <div style="height:4px;background:${accent};border-radius:0 0 12px 12px;margin:0 0 0 0;"></div> inside mj-text
  - "Shop Now →": <a href="{{CTA_URL}}" style="color:${accent};font-weight:700;font-size:14px;text-decoration:none;display:block;text-align:center;padding:0 0 16px;">Shop Now →</a>
` : "";

  return `You are the world's best email marketing designer specialising in MJML 4.
Generate a COMPLETE, PRODUCTION-READY, VISUALLY STUNNING MJML 4 email — Fortune-500 quality.
Study the brief carefully and write real, campaign-specific marketing copy throughout. Zero placeholder text.

===== CAMPAIGN BRIEF =====
Brand          : ${brandName}
Campaign purpose: ${description}
Accent colour  : ${accent}
Dark accent    : ${dark}
${logoUrl       ? `Logo image URL  : ${logoUrl}` : "Logo            : text-only (no image URL provided)"}
${heroImageUrl  ? `Hero image URL  : ${heroImageUrl}` : "Hero            : colour block (no hero image URL provided)"}
Products       : ${realProducts.length ? `${realProducts.length} — layout: ${productLayout}` : "none — general promotional email"}
==========================

━━━━━━━━━━━━━━━━━━━━━━━
DESIGN SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━
Font      : -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif
Body bg   : #f4f4f5   |   Card bg: #ffffff   |   Email width: 600px
Primary   : #111827   |   Muted: #6b7280     |   Border: #e5e7eb
Card style: border-radius:12px, border:1px solid #e5e7eb, overflow:hidden via container-background-color

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED LAYOUT (exact order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — HEADER STRIP
• mj-section background-color="${accent}", padding="20px 0 16px"
• Single centered column
• ${logoBlock}
• Optional: 13px white italic tagline below brand name if brand is known

SECTION 2 — ${heroSpec}

SECTION 3 — BENEFITS BAR
• mj-section background-color="#ffffff", padding="24px 20px"
• Three mj-columns, each containing: large emoji (34px), bold short stat/benefit text (14px #111827), tiny grey label (12px #6b7280)
• Choose 3 benefits relevant to this specific campaign (free shipping, returns policy, social proof, speed, quality, etc.)

${productSection}
SECTION — CTA STRIP
• mj-section background-color="${accent}", padding="48px 32px"
• Bold 24px white headline — urgency/benefit statement specific to the campaign
• 15px white/80% subtext — supporting one-liner
• mj-spacer height="20px"
• <mj-button background-color="#ffffff" color="${accent}" border-radius="50px" font-size="16px" font-weight="700" padding="14px 40px" href="{{CTA_URL}}">BUTTON TEXT</mj-button>

SECTION — FOOTER
• mj-section background-color="#f9fafb", padding="28px 24px"
• "© 2025 ${brandName}. All rights reserved." — 12px #9ca3af centered
• mj-spacer height="6px"
• <a href="{{UNSUBSCRIBE_URL}}" style="color:${accent};font-size:12px;text-decoration:none;">Unsubscribe</a> &nbsp;·&nbsp; <a href="{{VIEW_IN_BROWSER_URL}}" style="color:${accent};font-size:12px;text-decoration:none;">View in browser</a>
• mj-spacer height="6px"
• "Sent with ♥ by Zilo" — 11px #d1d5db

━━━━━━━━━━━━━━━━━━
ABSOLUTE RULES
━━━━━━━━━━━━━━━━━━
1. Output ONLY raw MJML XML. Nothing before <mjml>, nothing after </mjml>. No markdown.
2. Response MUST start with <mjml> and end with </mjml> — no exceptions.
3. Use <mj-head><mj-attributes> to set global font-family and button defaults.
4. ONLY valid MJML 4 components: mj-section, mj-column, mj-text, mj-button, mj-image, mj-spacer, mj-divider.
5. Every mj-section MUST have a background-color attribute.
6. ${urlRules}
7. No Google Fonts, no external CSS, no <link> tags.
8. Write REAL compelling marketing copy for every headline, subtext, and CTA — tailored precisely to the campaign brief. No "Lorem ipsum", no "[Your headline here]".
9. The final email MUST look genuinely stunning — bold, colorful, visually compelling, campaign-specific.
`.trim();
}

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";

  let body: {
    description?: string;
    brand?: string;
    products?: Product[];
    theme?: string;
    logo_url?: string;
    hero_image_url?: string;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const {
    description = "",
    brand = "",
    products = [],
    theme = "zilo",
    logo_url = "",
    hero_image_url = "",
  } = body;

  if (!description.trim()) {
    return NextResponse.json({ error: "description is required" }, { status: 400 });
  }

  const prompt = buildPrompt(description, brand, products, theme, logo_url.trim(), hero_image_url.trim());

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
      return NextResponse.json(
        { error: err.detail ?? "AI service error" },
        { status: res.status },
      );
    }

    const data = await res.json() as { reply?: string };
    let mjml = (data.reply ?? "").trim();

    // Strip any accidental markdown fences
    mjml = mjml.replace(/^```(?:mjml|xml|html)?\s*/i, "").replace(/\s*```$/i, "").trim();

    if (!mjml.startsWith("<mjml>")) {
      return NextResponse.json({ error: "AI did not return valid MJML" }, { status: 502 });
    }

    return NextResponse.json({ mjml });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

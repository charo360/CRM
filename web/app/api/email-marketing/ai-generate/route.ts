import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";

type Product = { name: string; price: string; description: string };

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
): string {
  const accent = THEME_COLORS[theme] ?? "#009b3a";
  const dark   = THEME_DARK[theme]   ?? "#007a2e";

  const brandName = brand || "the brand";

  const logoBlock = logoUrl
    ? `<mj-image src="${logoUrl}" width="150px" alt="${brandName}" align="center" padding="0 0 6px 0" />`
    : `<mj-text align="center" padding="0"><span style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;font-size:26px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">${brandName}</span></mj-text>`;

  const productLines = products.filter(p => p.name.trim());
  const hasProducts = productLines.length > 0;

  const productBlock = hasProducts
    ? productLines.map((p, i) =>
        `Product ${i + 1}: name="${p.name}"${p.price ? `, price="${p.price}"` : ""}${p.description ? `, description="${p.description}"` : ""}`
      ).join("\n")
    : "No specific products — general promotional / brand email.";

  // decide layout hint for products
  const productLayout = productLines.length === 2 ? "TWO-COLUMN (side by side)" :
                        productLines.length === 3 ? "THREE-COLUMN (side by side)" :
                        "ONE-COLUMN stacked";

  return `You are the world's best email marketing designer. You specialise in MJML 4 (the responsive email framework).
Your job: produce a COMPLETE, PRODUCTION-READY, VISUALLY STUNNING MJML 4 email template.
Fortune-500 quality — the kind of email that wins awards and gets clicks.

===== CAMPAIGN BRIEF =====
Brand / company : ${brandName}
Campaign purpose: ${description}
Accent colour   : ${accent}
Dark accent     : ${dark}
${logoUrl ? `Logo image URL  : ${logoUrl}` : "Logo            : text-based (no image URL)"}
Products        : ${productLines.length ? `${productLines.length} product(s) — layout: ${productLayout}` : "none — general email"}
${productBlock}
==========================

━━━━━━━━━━━━━━━━━━━━━━━
DESIGN SYSTEM (mandatory)
━━━━━━━━━━━━━━━━━━━━━━━
Font stack  : -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif
Body bg     : #f4f4f5
Card bg     : #ffffff
Primary text: #111827
Muted text  : #6b7280
Email width : 600px
Padding     : 20px column padding throughout

━━━━━━━━━━━━━━━━━━━━━
REQUIRED LAYOUT (in order)
━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — HEADER STRIP
• mj-section background-color="${accent}", padding="24px 0"
• Single centered column
• ${logoUrl
    ? `Logo: <mj-image src="${logoUrl}" width="150px" alt="${brandName}" align="center" padding="0 0 4px 0" />`
    : `Brand name: bold 26px white text`}
• Thin white separator line or spacer below

SECTION 2 — HERO BANNER
• mj-section background-color="${accent}", padding="48px 40px 52px"
• Large bold white headline (32px, font-weight:800, line-height:1.2) — write a punchy, campaign-specific headline based on the brief
• White subtext (17px, opacity-80, margin-top:12px) — one compelling sentence about the offer
• Centered "Shop Now" / CTA pill button: background-color="#ffffff", color="${accent}", border-radius="50px", font-size="16px", font-weight="700", padding="14px 40px", inner-padding="0", href="{{CTA_URL}}" — add margin-top:24px via a mj-spacer

SECTION 3 — TRUST / HIGHLIGHT BAR (skip if products section follows)
• mj-section background-color="#ffffff", padding="24px 20px"
• Three mini stat/benefit items in a 3-column row using mj-column: each with a large emoji (36px), bold number/text, small grey label — things relevant to the brand/campaign (e.g. "Free shipping", "30-day returns", "10,000+ customers")

${hasProducts ? `SECTION 4 — PRODUCTS
Layout: ${productLayout}
• mj-section background-color="#f4f4f5", padding="32px 20px"
• Section heading: bold 22px #111827 centred, "Featured Products" or campaign-relevant heading
• mj-spacer height="16px"
${productLines.length <= 3 ? `• Use ${productLines.length} mj-column(s) side by side inside one mj-section` : `• Stack products one per row`}
Each product card (implemented as mj-column with inner content):
  - White card area: padding="0", background-color="#ffffff", border-radius="12px", border="1px solid #e5e7eb" (use container-background-color on mj-column)
  - TOP ACCENT BAR: <mj-text padding="0"><div style="height:5px;background:${accent};border-radius:12px 12px 0 0;margin:0;"></div></mj-text>
  - PRODUCT EMOJI: <mj-text align="center" padding="20px 16px 8px"><span style="font-size:52px;display:block;text-align:center;">RELEVANT_EMOJI</span></mj-text> — choose a highly relevant emoji for each product
  - PRODUCT NAME: mj-text, bold 17px #111827, align="center", padding="0 16px 4px"
  ${productLines.some(p => p.price) ? `  - PRICE BADGE: mj-text, align="center", padding="0 16px 8px" — <span style="background:${accent};color:#fff;font-size:15px;font-weight:700;padding:4px 14px;border-radius:20px;">${accent}</span>` : ""}
  - DESCRIPTION: mj-text, 13px #6b7280, align="center", padding="0 16px 12px", line-height:1.5
  - SHOP LINK: <mj-text align="center" padding="0 16px 20px"><a href="{{CTA_URL}}" style="color:${accent};font-weight:700;font-size:14px;text-decoration:none;">Shop Now →</a></mj-text>

` : ""}
SECTION ${hasProducts ? 5 : 4} — CTA SECTION
• mj-section background-color="#ffffff", padding="48px 32px"
• Centred 20px bold #111827 headline: write a persuasive urgency/benefit statement
• 15px #6b7280 body text: supporting sentence
• mj-spacer height="20px"
• mj-button background-color="${accent}" color="#ffffff" border-radius="8px" font-size="16px" font-weight="700" padding="14px 40px" href="{{CTA_URL}}" inner-padding="0"

SECTION ${hasProducts ? 6 : 5} — FOOTER
• mj-section background-color="#f9fafb", padding="32px 24px"
• "© 2025 ${brandName}. All rights reserved." — 12px #9ca3af, centred
• mj-spacer height="8px"
• Links row: <a href="{{UNSUBSCRIBE_URL}}" style="color:${accent};font-size:12px;text-decoration:none;">Unsubscribe</a> &nbsp;·&nbsp; <a href="{{VIEW_IN_BROWSER_URL}}" style="color:${accent};font-size:12px;text-decoration:none;">View in browser</a>
• mj-spacer height="8px"
• "Sent with ♥ by Zilo" — 11px #d1d5db

━━━━━━━━━━━━━━━━━━
ABSOLUTE RULES
━━━━━━━━━━━━━━━━━━
1. Output ONLY raw MJML XML. No markdown fences, no explanation, nothing before <mjml> or after </mjml>.
2. Response MUST start exactly with <mjml> and end exactly with </mjml>.
3. Use <mj-head><mj-attributes> to set global font-family, font-size defaults, and mj-button defaults.
4. ONLY valid MJML 4 components: mj-section, mj-column, mj-text, mj-button, mj-image, mj-spacer, mj-divider.
5. ${logoUrl ? `"${logoUrl}" is the ONLY external URL allowed as an image src.` : "Zero external image URLs — no img src pointing to the web."}
6. No Google Fonts, no external CSS, no <link> tags.
7. Every mj-section MUST have a background-color attribute.
8. Write REAL, compelling marketing copy — headlines, subtext, CTAs — tailored to the campaign brief. No placeholder text like "Lorem ipsum" or generic "[Insert text]".
9. Product emojis must be thematically relevant (🎧 for headphones, 👟 for shoes, 💄 for beauty, etc.).
10. The final email must be genuinely beautiful, professional, and campaign-specific.
`.trim();
}

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";

  let body: { description?: string; brand?: string; products?: Product[]; theme?: string; logo_url?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { description = "", brand = "", products = [], theme = "zilo", logo_url = "" } = body;

  if (!description.trim()) {
    return NextResponse.json({ error: "description is required" }, { status: 400 });
  }

  const prompt = buildPrompt(description, brand, products, theme, logo_url.trim());

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

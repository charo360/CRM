import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";

type Product = { name: string; price: string; description: string };

const THEME_COLORS: Record<string, string> = {
  indigo: "#6366f1",
  red:    "#ef4444",
  green:  "#10b981",
  blue:   "#3b82f6",
  amber:  "#f59e0b",
  dark:   "#0f172a",
  purple: "#8b5cf6",
  orange: "#f97316",
};

function buildPrompt(
  description: string,
  brand: string,
  products: Product[],
  theme: string,
): string {
  const accent = THEME_COLORS[theme] ?? "#6366f1";
  const productBlock = products.length
    ? products
        .map(
          (p, i) =>
            `Product ${i + 1}: ${p.name}${p.price ? ` | Price: ${p.price}` : ""}${p.description ? ` | ${p.description}` : ""}`,
        )
        .join("\n")
    : "No specific products — make it a general promotional email.";

  return `You are an expert email marketing designer specialising in MJML (the responsive email framework).

Your task: generate a COMPLETE, VALID MJML 4 email template based on the user's brief below.

===== USER BRIEF =====
Brand / company: ${brand || "the brand"}
Email description: ${description}
Accent / primary colour: ${accent}
Products to feature:
${productBlock}
======================

STRICT OUTPUT RULES — follow every one:
1. Output ONLY the raw MJML XML. No markdown fences, no explanation, no text before or after.
2. The response must start with <mjml> and end with </mjml> and nothing else.
3. Use a <mj-head> with <mj-attributes> to set consistent font-family, text colour, and a default <mj-button> style using the accent colour ${accent}.
4. Structure: header section (brand name + tagline) → product/content section(s) → single clear CTA button → footer with unsubscribe link.
5. For each product, create a visually distinct card inside a <mj-text> block using inline HTML tables. Use a coloured emoji or icon div as a placeholder image (NO <mj-image> pointing to real URLs).
6. Use ${accent} as the dominant colour for the header background, buttons, and accents.
7. Keep the footer light grey (#f9fafb background) with 12px grey text and two links: "Unsubscribe" and "View in browser" coloured ${accent}.
8. Use {{CTA_URL}} as a placeholder wherever a link href should go.
9. Do NOT use any external image URLs. Do NOT reference fonts from Google Fonts.
10. The email must look professional, modern, and visually engaging.
11. Strictly valid MJML 4 syntax — only use real MJML components (mj-section, mj-column, mj-text, mj-button, mj-spacer, mj-divider, mj-raw, mj-html-attributes).
`.trim();
}

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization") ?? "";

  let body: { description?: string; brand?: string; products?: Product[]; theme?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { description = "", brand = "", products = [], theme = "indigo" } = body;

  if (!description.trim()) {
    return NextResponse.json({ error: "description is required" }, { status: 400 });
  }

  const prompt = buildPrompt(description, brand, products, theme);

  try {
    const res = await fetch(`${BACKEND}/assistant/ai-draft`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify({ prompt, model: "claude-sonnet-4.6" }),
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

    // Strip any accidental markdown fences the model might add
    mjml = mjml.replace(/^```(?:mjml|xml)?\s*/i, "").replace(/\s*```$/i, "").trim();

    if (!mjml.startsWith("<mjml>")) {
      return NextResponse.json({ error: "AI did not return valid MJML" }, { status: 502 });
    }

    return NextResponse.json({ mjml });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

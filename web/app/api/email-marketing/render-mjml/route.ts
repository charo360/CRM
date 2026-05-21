import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const mjml2html = require("mjml") as (
  mjml: string,
  opts?: { validationLevel?: "strict" | "soft" | "skip" }
) => { html: string; errors: Array<{ formattedMessage: string }> };

export async function POST(req: NextRequest) {
  try {
    const { mjml } = await req.json();
    if (!mjml || typeof mjml !== "string") {
      return NextResponse.json({ error: "mjml string required" }, { status: 400 });
    }
    const result = mjml2html(mjml, { validationLevel: "soft" });
    if (result.errors?.length) {
      console.warn("[render-mjml] warnings:", result.errors.map((e) => e.formattedMessage));
    }
    return NextResponse.json({ html: result.html });
  } catch (e) {
    console.error("[render-mjml] error:", e);
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

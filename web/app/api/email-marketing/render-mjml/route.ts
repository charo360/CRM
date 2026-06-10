import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

type MjmlResult = { html: string; errors: Array<{ formattedMessage: string }> };
type MjmlFn = (mjml: string, opts?: { validationLevel?: "strict" | "soft" | "skip" }) => Promise<MjmlResult> | MjmlResult;

let _mjml2html: MjmlFn | null = null;

async function getMjml2html(): Promise<MjmlFn> {
  if (_mjml2html) return _mjml2html;
  const mod = await import("mjml");
  _mjml2html = (typeof mod.default === "function" ? mod.default : mod) as unknown as MjmlFn;
  return _mjml2html;
}

export async function POST(req: NextRequest) {
  try {
    const { mjml } = await req.json();
    if (!mjml || typeof mjml !== "string") {
      return NextResponse.json({ error: "mjml string required" }, { status: 400 });
    }
    const mjml2html = await getMjml2html();
    const result = await mjml2html(mjml, { validationLevel: "soft" });
    if (result.errors?.length) {
      console.warn("[render-mjml] warnings:", result.errors.map((e) => e.formattedMessage));
    }
    return NextResponse.json({ html: result.html });
  } catch (e) {
    console.error("[render-mjml] error:", e);
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

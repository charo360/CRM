import { NextResponse } from "next/server";
import { buildInternalCrmApiUrl } from "@/lib/server-crm-api";

async function loadSetupFrom(url: string) {
  const res = await fetch(url, {
    signal: AbortSignal.timeout(12_000),
    cache: "no-store",
  });
  const text = await res.text();
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text || res.statusText };
  }
  return { res, data };
}

export async function GET() {
  const urls: string[] = [buildInternalCrmApiUrl("/stripe/setup")];
  const pub = (process.env.NEXT_PUBLIC_API_URL || "").trim();
  if (pub.startsWith("http://") || pub.startsWith("https://")) {
    const base = pub.replace(/\/$/, "");
    const alt = `${base}/stripe/setup`;
    if (!urls.includes(alt)) urls.push(alt);
  }

  let lastError: string | null = null;
  for (const url of urls) {
    try {
      const { res, data } = await loadSetupFrom(url);
      if (res.ok || res.status < 500) {
        return NextResponse.json(data, { status: res.status });
      }
      lastError = typeof data === "object" && data && "detail" in data ? String((data as { detail: unknown }).detail) : res.statusText;
    } catch (e) {
      lastError = e instanceof Error ? e.message : String(e);
    }
  }

  return NextResponse.json(
    {
      detail: `Could not load Stripe setup: ${lastError ?? "backend unreachable"}. Start the API on port 8000 and set BACKEND_INTERNAL_URL in web/.env.local if needed.`,
      platform_available: false,
    },
    { status: 503 },
  );
}

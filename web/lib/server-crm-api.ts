import type { NextRequest } from "next/server";

/**
 * Build an absolute CRM API URL for Route Handlers. `NEXT_PUBLIC_API_URL` may be
 * `http://127.0.0.1:8000/api`, `http://localhost:3000/proxy`, or a same-origin path `/proxy`.
 */
export function buildServerCrmApiUrl(req: NextRequest, path: string): string {
  const raw = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api").trim();
  const suffix = path.startsWith("/") ? path : `/${path}`;
  const base = raw.replace(/\/$/, "");
  if (base.startsWith("http://") || base.startsWith("https://")) {
    return `${base}${suffix}`;
  }
  const rel = (base.startsWith("/") ? base : `/${base}`).replace(/\/$/, "");
  return `${req.nextUrl.origin}${rel}${suffix}`;
}

/** Direct FastAPI URL for server-to-server calls (avoids /proxy self-fetch issues). */
export function buildInternalCrmApiUrl(path: string): string {
  const origin = (process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${origin}/api${suffix}`;
}

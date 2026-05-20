import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

// Server-side only — not exposed to the browser.
// In production on Render, set this to your backend's internal/public URL.
const BACKEND_ORIGIN = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";

/** This app’s directory (…/CRM/web). */
const WEB_PACKAGE_ROOT = path.dirname(fileURLToPath(import.meta.url));

// On Vercel, outputFileTracingRoot is set to the repo root (/vercel/path0).
// turbopack.root must match it exactly — use the parent dir (repo root) on Vercel,
// or the web dir locally (to avoid Turbopack picking up a parent package-lock.json).
const TURBO_ROOT = process.env.VERCEL
  ? path.join(WEB_PACKAGE_ROOT, "..")
  : WEB_PACKAGE_ROOT;

const nextConfig: NextConfig = {
  outputFileTracingRoot: TURBO_ROOT,
  turbopack: {
    root: TURBO_ROOT,
  },
  async rewrites() {
    return [
      {
        // /proxy/:path* → http://localhost:8000/api/:path*
        // Browser calls /proxy/... (same origin, no mixed-content issue).
        // Next.js server makes the HTTP call internally.
        source: "/proxy/:path*",
        destination: `${BACKEND_ORIGIN}/api/:path*`,
      },
      {
        // /api/media/presentations/:file → backend static mount
        source: "/api/media/presentations/:file*",
        destination: `${BACKEND_ORIGIN}/api/media/presentations/:file*`,
      },
    ];
  },
};

export default nextConfig;

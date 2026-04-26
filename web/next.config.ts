import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

// Server-side only — not exposed to the browser.
// In production on Render, set this to your backend's internal/public URL.
const BACKEND_ORIGIN = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";

/** This app’s directory (…/CRM/web). Required when another lockfile exists higher on disk (e.g. C:\\Users\\…\\package-lock.json) or Turbopack infers the wrong monorepo root and every App Router page 404s. */
const WEB_PACKAGE_ROOT = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  turbopack: {
    root: WEB_PACKAGE_ROOT,
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
    ];
  },
};

export default nextConfig;

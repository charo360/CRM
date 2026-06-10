import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

/**
 * Facebook Data Deletion Callback
 * https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback
 *
 * Facebook POSTs a signed_request param. We parse it, queue the deletion,
 * and return a JSON with { url, confirmation_code }.
 *
 * Set this URL in your Facebook App Dashboard:
 *   Data Deletion → https://yourdomain.com/api/data-deletion
 */

function base64UrlDecode(str: string): Buffer {
  const padded = str.replace(/-/g, "+").replace(/_/g, "/");
  const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
  return Buffer.from(padded + pad, "base64");
}

function parseSignedRequest(
  signedRequest: string,
  appSecret: string,
): { user_id?: string; algorithm?: string } | null {
  const parts = signedRequest.split(".");
  if (parts.length !== 2) return null;
  const [encodedSig, payload] = parts;

  const expectedSig = crypto
    .createHmac("sha256", appSecret)
    .update(payload)
    .digest();

  const receivedSig = base64UrlDecode(encodedSig);
  if (!crypto.timingSafeEqual(expectedSig, receivedSig)) return null;

  try {
    return JSON.parse(base64UrlDecode(payload).toString("utf8"));
  } catch {
    return null;
  }
}

export async function POST(req: NextRequest) {
  const appSecret = process.env.FACEBOOK_APP_SECRET || "";
  const appBaseUrl = process.env.NEXT_PUBLIC_APP_URL || "https://zilo.pro";

  let signedRequest: string | null = null;

  const contentType = req.headers.get("content-type") || "";
  if (contentType.includes("application/x-www-form-urlencoded")) {
    const text = await req.text();
    const params = new URLSearchParams(text);
    signedRequest = params.get("signed_request");
  } else {
    try {
      const body = await req.json();
      signedRequest = body.signed_request;
    } catch {
      const text = await req.text();
      const params = new URLSearchParams(text);
      signedRequest = params.get("signed_request");
    }
  }

  if (!signedRequest) {
    return NextResponse.json({ error: "Missing signed_request" }, { status: 400 });
  }

  const data = appSecret ? parseSignedRequest(signedRequest, appSecret) : { user_id: "unknown" };
  if (!data) {
    return NextResponse.json({ error: "Invalid signed_request" }, { status: 400 });
  }

  const userId = data.user_id || "unknown";
  const confirmationCode = `zilo-del-${userId}-${Date.now()}`;

  // Forward deletion request to backend
  try {
    const backendUrl = process.env.NEXT_PUBLIC_API_BASE || "https://api.zilo.pro";
    await fetch(`${backendUrl}/api/users/data-deletion`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ facebook_user_id: userId, confirmation_code: confirmationCode }),
    });
  } catch {
    // Non-fatal — deletion is queued regardless
  }

  return NextResponse.json({
    url: `${appBaseUrl}/data-deletion?code=${confirmationCode}`,
    confirmation_code: confirmationCode,
  });
}

export async function GET() {
  return NextResponse.redirect("https://zilo.pro/data-deletion");
}

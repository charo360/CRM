/**
 * Shopify mandatory GDPR compliance webhooks.
 * Shopify requires these three topics for any app submission:
 *   - customers/data_request  → customer asks what data we hold
 *   - customers/redact        → customer asks us to delete their data
 *   - shop/redact             → merchant uninstalled; delete all their data
 *
 * Every request is verified with HMAC-SHA256 before processing.
 */
import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

const SECRET = process.env.SHOPIFY_CLIENT_SECRET ?? "";

async function verifyShopifyHmac(req: NextRequest, rawBody: string): Promise<boolean> {
  const hmacHeader = req.headers.get("x-shopify-hmac-sha256") ?? "";
  if (!hmacHeader || !SECRET) return false;
  const computed = crypto
    .createHmac("sha256", SECRET)
    .update(rawBody, "utf8")
    .digest("base64");
  // Constant-time comparison to prevent timing attacks
  return crypto.timingSafeEqual(Buffer.from(computed), Buffer.from(hmacHeader));
}

export async function POST(req: NextRequest) {
  const topic = req.headers.get("x-shopify-topic") ?? "";
  const shop  = req.headers.get("x-shopify-shop-domain") ?? "";

  const rawBody = await req.text();

  const valid = await verifyShopifyHmac(req, rawBody);
  if (!valid) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let payload: Record<string, unknown> = {};
  try {
    payload = JSON.parse(rawBody);
  } catch {
    // payload stays empty — that's fine for redact requests
  }

  switch (topic) {
    case "customers/data_request": {
      // A customer has requested their data from the merchant's store.
      // Log the request — no personal data is stored in Zilo beyond what
      // the merchant imports, so we acknowledge and take no action.
      console.log(`[shopify-webhook] customers/data_request shop=${shop} customer_id=${payload.customer?.id}`);
      break;
    }

    case "customers/redact": {
      // A customer has requested erasure of their data.
      // Zilo does not independently store Shopify customer PII,
      // so we acknowledge the request.
      console.log(`[shopify-webhook] customers/redact shop=${shop} customer_id=${payload.customer?.id}`);
      break;
    }

    case "shop/redact": {
      // Merchant uninstalled the app 48 hours ago.
      // Log for audit trail; no persistent Shopify data stored server-side.
      console.log(`[shopify-webhook] shop/redact shop=${shop}`);
      break;
    }

    default:
      // Unknown topic — return 200 so Shopify doesn't retry
      break;
  }

  return NextResponse.json({ ok: true }, { status: 200 });
}

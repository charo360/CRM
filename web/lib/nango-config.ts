/**
 * Integration config keys must match the Integration unique name in your Nango dashboard.
 * Override with env if you use different IDs (e.g. `outlook` instead of `google-mail`).
 */
export const NANGO_INTEGRATION_IDS = {
  slack: process.env.NEXT_PUBLIC_NANGO_ID_SLACK || "slack",
  email: process.env.NEXT_PUBLIC_NANGO_ID_EMAIL || "google-mail",
  calendar: process.env.NEXT_PUBLIC_NANGO_ID_CALENDAR || "google-calendar",
  shopify: process.env.NEXT_PUBLIC_NANGO_ID_SHOPIFY || "shopify",
  microsoft: process.env.NEXT_PUBLIC_NANGO_ID_MICROSOFT || "microsoft",
  stripe: process.env.NEXT_PUBLIC_NANGO_ID_STRIPE || "stripe",
  klaviyo: process.env.NEXT_PUBLIC_NANGO_ID_KLAVIYO || "klaviyo",
  mailchimp: process.env.NEXT_PUBLIC_NANGO_ID_MAILCHIMP || "mailchimp",
  brevo: process.env.NEXT_PUBLIC_NANGO_ID_BREVO || "brevo",
} as const;

export type NangoIntegrationKey = keyof typeof NANGO_INTEGRATION_IDS;

/** Must match `NANGO_API_URL` on the server when self-hosting (defaults to Nango Cloud). */
export const NANGO_PUBLIC_API_URL = process.env.NEXT_PUBLIC_NANGO_API_URL || "https://api.nango.dev";

/** Connect iframe origin; use your self-hosted URL if not using Nango Cloud UI. */
export const NANGO_PUBLIC_CONNECT_UI_URL =
  process.env.NEXT_PUBLIC_NANGO_CONNECT_UI_URL || "https://connect.nango.dev";

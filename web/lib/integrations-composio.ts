/**
 * Composio toolkit slugs shown on Integrations — kept in sync with backend composio_service._APP_NAMES.
 * Used for connection status defaults and OAuth connect/disconnect flows.
 */

export const COMPOSIO_SOCIAL_TOOLKITS = [
  "facebook",
  "instagram",
  "youtube",
  "linkedin",
  "twitter",
  "tiktok",
  "reddit",
  "pinterest",
  "whatsapp",
  "telegram",
  "googlebusiness",
] as const;

export const COMPOSIO_CRM_TOOLKITS = [
  "hubspot",
  "salesforce",
  "pipedrive",
  "apollo",
  "instantly",
] as const;

export const COMPOSIO_COMMS_TOOLKITS = [
  "gmail",
  "outlook",
  "googlecalendar",
  "calendly",
  "zoom",
  "slack",
] as const;

export const COMPOSIO_MARKETING_TOOLKITS = [
  "klaviyo",
  "mailchimp",
  "brevo",
] as const;

export const COMPOSIO_ANALYTICS_TOOLKITS = [
  "googleads",
  "metaads",
  "googleanalytics",
  "googlesearchconsole",
] as const;

export const COMPOSIO_COMMERCE_TOOLKITS = ["shopify", "quickbooks", "stripe"] as const;

export const COMPOSIO_WORKSPACE_TOOLKITS = ["googlesheets", "notion"] as const;

/** Every Composio toolkit surfaced on the Integrations page. */
export const INTEGRATIONS_COMPOSIO_TOOLKITS = [
  ...COMPOSIO_SOCIAL_TOOLKITS,
  ...COMPOSIO_CRM_TOOLKITS,
  ...COMPOSIO_COMMS_TOOLKITS,
  ...COMPOSIO_MARKETING_TOOLKITS,
  ...COMPOSIO_ANALYTICS_TOOLKITS,
  ...COMPOSIO_COMMERCE_TOOLKITS,
  ...COMPOSIO_WORKSPACE_TOOLKITS,
] as const;

export type IntegrationsComposioToolkit = (typeof INTEGRATIONS_COMPOSIO_TOOLKITS)[number];

export function buildComposioDisconnectedStatus(): Record<string, boolean> {
  return Object.fromEntries(INTEGRATIONS_COMPOSIO_TOOLKITS.map((t) => [t, false]));
}

const COMPOSIO_STATUS_STORAGE_KEY = "zilo:integrations:composio-status";
const COMPOSIO_STATUS_STORAGE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

/** Last-known Composio flags — instant paint on Integrations before network returns. */
export function readStoredComposioStatus(): Record<string, boolean> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(COMPOSIO_STATUS_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { at?: number; connected?: Record<string, boolean> };
    if (!parsed.connected || typeof parsed.connected !== "object") return null;
    if (Date.now() - (parsed.at ?? 0) > COMPOSIO_STATUS_STORAGE_TTL_MS) return null;
    return parsed.connected;
  } catch {
    return null;
  }
}

export function writeStoredComposioStatus(connected: Record<string, boolean>): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(
      COMPOSIO_STATUS_STORAGE_KEY,
      JSON.stringify({ at: Date.now(), connected }),
    );
  } catch {
    /* ignore quota / private mode */
  }
}

export function isComposioSocialToolkit(toolkit: string): boolean {
  return (COMPOSIO_SOCIAL_TOOLKITS as readonly string[]).includes(toolkit);
}

/** API-key toolkits — Composio connect prompts for your key (no OAuth popup). */
export const COMPOSIO_API_KEY_TOOLKITS = new Set(["apollo", "instantly", "brevo", "klaviyo"]);

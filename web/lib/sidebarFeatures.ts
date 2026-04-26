/**
 * Optional sidebar links (Workspace is fixed: Overview, Zilo Chat, Automations, Integrations, Features, Settings).
 * Stored at user.settings.features. Default is OFF — users turn items on under Features so the sidebar stays short.
 */

export const SIDEBAR_FEATURE_DEFAULTS: Record<string, boolean> = {
  nav_messages: false,
  nav_customers: false,
  nav_contacts: false,
  nav_suppliers: false,
  nav_followups: false,
  nav_sales: false,
  nav_orders: false,
  nav_bookings: false,
  nav_payments: false,
  nav_broadcast: false,
  nav_social_scheduler: false,
  nav_meta_ads: false,
  nav_google_ads: false,
  nav_x_ads: false,
  nav_google_business: false,
  nav_analytics: false,
  nav_team_analytics: false,
  nav_whatsapp: false,
  nav_team: false,
  nav_shop: false,
  nav_imports: false,
  nav_kds: false,
  nav_invoices: false,
  nav_inventory: false,
  nav_finance: false,
  nav_quotes: false,
  nav_loyalty: false,
  nav_nps: false,
  nav_social_inbox: false,
  nav_email: false,
  nav_calendar: false,
  nav_shopify: false,
  nav_design_templates: false,
  nav_seo: false,
};

/** Map route href → settings key */
export const HREF_TO_FEATURE_KEY: Record<string, string> = {
  "/dashboard/messages": "nav_messages",
  "/dashboard/customers": "nav_customers",
  "/dashboard/contacts": "nav_contacts",
  "/dashboard/suppliers": "nav_suppliers",
  "/dashboard/followups": "nav_followups",
  "/dashboard/sales": "nav_sales",
  "/dashboard/orders": "nav_orders",
  "/dashboard/bookings": "nav_bookings",
  "/dashboard/reservations": "nav_bookings",
  "/dashboard/payments": "nav_payments",
  "/dashboard/broadcast": "nav_broadcast",
  "/dashboard/social-scheduler": "nav_social_scheduler",
  "/dashboard/meta-ads": "nav_meta_ads",
  "/dashboard/google-ads": "nav_google_ads",
  "/dashboard/x-ads": "nav_x_ads",
  "/dashboard/google-business": "nav_google_business",
  "/dashboard/integrations": "nav_integrations",
  "/dashboard/analytics": "nav_analytics",
  "/dashboard/team-analytics": "nav_team_analytics",
  "/dashboard/whatsapp": "nav_whatsapp",
  "/dashboard/team": "nav_team",
  "/dashboard/shop": "nav_shop",
  "/dashboard/imports": "nav_imports",
  "/dashboard/kds": "nav_kds",
  "/dashboard/invoices": "nav_invoices",
  "/dashboard/inventory": "nav_inventory",
  "/dashboard/finance": "nav_finance",
  "/dashboard/quotes": "nav_quotes",
  "/dashboard/loyalty": "nav_loyalty",
  "/dashboard/nps": "nav_nps",
  "/dashboard/social-inbox": "nav_social_inbox",
  "/dashboard/email": "nav_email",
  "/dashboard/calendar": "nav_calendar",
  "/dashboard/shopify": "nav_shopify",
  "/dashboard/design-templates": "nav_design_templates",
  "/dashboard/seo": "nav_seo",
};

export function mergeSidebarFeatures(raw: unknown): Record<string, boolean> {
  const out = { ...SIDEBAR_FEATURE_DEFAULTS };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (k in out && typeof v === "boolean") out[k] = v;
  }
  return out;
}

export function isSidebarHrefEnabled(href: string, features: Record<string, boolean>): boolean {
  const key = HREF_TO_FEATURE_KEY[href];
  if (!key) return true;
  return features[key] === true;
}

export type FeatureToggleRow = {
  key: string;
  label: string;
  description: string;
};

export const FEATURE_TOGGLE_GROUPS: { title: string; items: FeatureToggleRow[] }[] = [
  {
    title: "Main",
    items: [
      { key: "nav_messages", label: "Messages", description: "Inbox and conversations" },
      { key: "nav_customers", label: "Customers / pipeline", description: "People & pipeline" },
      { key: "nav_contacts", label: "Contacts", description: "Contact records" },
      { key: "nav_suppliers", label: "Suppliers", description: "Vendor relationships" },
      { key: "nav_followups", label: "Follow-ups", description: "Reminders" },
    ],
  },
  {
    title: "Sales & revenue",
    items: [
      { key: "nav_sales", label: "Sales", description: "Revenue / POS tab" },
      { key: "nav_orders", label: "Orders", description: "Order list" },
      { key: "nav_bookings", label: "Bookings / Reservations", description: "Shown when your industry uses them" },
      { key: "nav_payments", label: "Payments", description: "Payment tracking" },
      { key: "nav_invoices", label: "Invoices", description: "Create and send invoices" },
      { key: "nav_quotes", label: "Quotes / Proposals", description: "Send quotes to customers" },
      { key: "nav_finance", label: "Finance / P&L", description: "Income, expenses, profit & loss" },
    ],
  },
  {
    title: "Sales & growth",
    items: [
      { key: "nav_broadcast", label: "Broadcast", description: "Campaigns to your list — retention and promos" },
      { key: "nav_social_scheduler", label: "Social scheduler", description: "Plan posts across networks" },
      { key: "nav_meta_ads", label: "Meta Ads", description: "Facebook & Instagram campaign planning" },
      { key: "nav_google_ads", label: "Google Ads", description: "Search & Performance Max planning" },
      { key: "nav_x_ads", label: "X Ads", description: "Promoted posts & campaigns on X (Twitter)" },
      { key: "nav_google_business", label: "Google Business Profile", description: "Maps & local presence via Integrations" },
      { key: "nav_social_inbox", label: "Social Inbox", description: "Unified DMs from all social platforms via Zernio" },
      { key: "nav_seo", label: "SEO & Blog", description: "Site audit, AI keyword research, blog writer, and auto-publish" },
    ],
  },
  {
    title: "Business",
    items: [
      { key: "nav_analytics", label: "Analytics", description: "Dashboard metrics" },
      { key: "nav_team_analytics", label: "Team analytics", description: "Team performance" },
      { key: "nav_whatsapp", label: "WhatsApp", description: "WA tools" },
      { key: "nav_team", label: "Team", description: "Members & roles" },
      { key: "nav_shop", label: "Shop / catalog", description: "Storefront (label varies by type)" },
      { key: "nav_imports", label: "Imports", description: "Bulk upload" },
      { key: "nav_inventory", label: "Inventory / Stock", description: "Track products and stock levels" },
      { key: "nav_loyalty", label: "Customer Loyalty", description: "Points and rewards program" },
      { key: "nav_nps", label: "Customer Feedback / NPS", description: "Surveys and satisfaction scores" },
    ],
  },
  {
    title: "Productivity",
    items: [
      { key: "nav_email", label: "Email Inbox", description: "Gmail or Outlook inbox with AI draft & auto-reply" },
      { key: "nav_calendar", label: "Calendar", description: "Google or Outlook calendar with event management" },
      { key: "nav_shopify", label: "Shopify", description: "Orders, inventory, customers, abandoned carts & discounts" },
    { key: "nav_design_templates", label: "Design library", description: "Chat-generated graphics, PDFs, and decks plus optional manual template metadata" },
    ],
  },
  {
    title: "Display",
    items: [{ key: "nav_kds", label: "KDS display", description: "Kitchen screen (F&B types)" }],
  },
];

/** Business preset — sales, customers, invoices, analytics */
export const PRESET_BUSINESS: Partial<Record<string, boolean>> = {
  nav_messages: true,
  nav_customers: true,
  nav_contacts: true,
  nav_suppliers: false,
  nav_followups: true,
  nav_sales: true,
  nav_orders: true,
  nav_bookings: false,
  nav_payments: true,
  nav_invoices: true,
  nav_quotes: true,
  nav_finance: true,
  nav_broadcast: true,
  nav_social_scheduler: false,
  nav_meta_ads: false,
  nav_google_ads: false,
  nav_x_ads: false,
  nav_google_business: false,
  nav_social_inbox: false,
  nav_analytics: true,
  nav_team_analytics: false,
  nav_whatsapp: true,
  nav_team: false,
  nav_shop: false,
  nav_imports: false,
  nav_inventory: false,
  nav_loyalty: false,
  nav_nps: false,
  nav_kds: false,
};

/** Personal preset — social, scheduling, broadcast */
export const PRESET_PERSONAL: Partial<Record<string, boolean>> = {
  nav_messages: true,
  nav_customers: false,
  nav_contacts: true,
  nav_suppliers: false,
  nav_followups: true,
  nav_sales: false,
  nav_orders: false,
  nav_bookings: false,
  nav_payments: false,
  nav_invoices: false,
  nav_quotes: false,
  nav_finance: false,
  nav_broadcast: true,
  nav_social_scheduler: true,
  nav_meta_ads: false,
  nav_google_ads: false,
  nav_social_inbox: true,
  nav_analytics: false,
  nav_team_analytics: false,
  nav_whatsapp: true,
  nav_team: false,
  nav_shop: false,
  nav_imports: false,
  nav_inventory: false,
  nav_loyalty: false,
  nav_nps: false,
  nav_kds: false,
};

/** Quick-add bundle: common tools without turning everything on */
export const PRESET_STARTER: Partial<Record<string, boolean>> = {
  nav_messages: true,
  nav_customers: true,
  nav_contacts: false,
  nav_suppliers: false,
  nav_followups: true,
  nav_sales: false,
  nav_orders: false,
  nav_bookings: false,
  nav_payments: false,
  nav_broadcast: false,
  nav_social_scheduler: false,
  nav_meta_ads: false,
  nav_google_ads: false,
  nav_x_ads: false,
  nav_google_business: false,
  nav_analytics: false,
  nav_team_analytics: false,
  nav_whatsapp: true,
  nav_team: false,
  nav_shop: false,
  nav_imports: false,
  nav_kds: false,
};

/** Every optional key set from a partial (defaults for missing keys = `defaultValue`, usually false). */
export function applyAllFromPartial(preset: Partial<Record<string, boolean>>, defaultValue = false): Record<string, boolean> {
  const out = { ...SIDEBAR_FEATURE_DEFAULTS };
  for (const k of Object.keys(out)) {
    out[k] = k in preset ? Boolean(preset[k]) : defaultValue;
  }
  return out;
}

/** Enable every optional sidebar link (full workspace). */
export function allSidebarFeaturesOn(): Record<string, boolean> {
  const out = { ...SIDEBAR_FEATURE_DEFAULTS };
  for (const k of Object.keys(out)) out[k] = true;
  return out;
}

/**
 * Optional sidebar links (Workspace is fixed: Overview, Zilo Chat, Automations, Integrations, Features, Settings).
 * Stored at user.settings.features. Default is OFF — users turn items on under Features so the sidebar stays short.
 */

export const SIDEBAR_FEATURE_DEFAULTS: Record<string, boolean> = {
  nav_messages: false,
  nav_customers: false,
  nav_contacts: false,
  nav_suppliers: false,
  nav_investors: false,
  nav_partners: false,
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
  nav_collaboration: false,
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
  nav_email_marketing: false,
  nav_sms_marketing: false,
  nav_ai_scout: false,
  nav_behavior_tracker: false,
  nav_field_agents: false,
  nav_smart_notes: false,
  nav_calendar: false,
  nav_shopify: false,
  nav_design_templates: false,
  nav_documents: false,
  nav_seo_hub: false,
  nav_seo: false,
  nav_growth: false,
  nav_client_portal: false,
  nav_store: false,
};

/** Map route href → settings key */
export const HREF_TO_FEATURE_KEY: Record<string, string> = {
  "/dashboard/messages": "nav_messages",
  "/dashboard/customers": "nav_customers",
  "/dashboard/contacts": "nav_contacts",
  "/dashboard/suppliers": "nav_suppliers",
  "/dashboard/investors": "nav_investors",
  "/dashboard/partners": "nav_partners",
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
  "/dashboard/collaboration": "nav_collaboration",
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
  "/dashboard/email-marketing": "nav_email_marketing",
  "/dashboard/sms-marketing": "nav_sms_marketing",
  "/dashboard/action-mode": "nav_ai_scout",
  "/dashboard/marketing/behavior-discounts": "nav_behavior_tracker",
  "/dashboard/field-agents": "nav_field_agents",
  "/dashboard/smart-notes": "nav_smart_notes",
  "/dashboard/calendar": "nav_calendar",
  "/dashboard/shopify": "nav_shopify",
  "/dashboard/design-templates": "nav_design_templates",
  "/dashboard/documents": "nav_documents",
  "/dashboard/seo-hub": "nav_seo_hub",
  "/dashboard/seo": "nav_seo",
  "/dashboard/growth": "nav_growth",
  "/dashboard/client-portal": "nav_client_portal",
  "/dashboard/store": "nav_store",
};

export function mergeSidebarFeatures(raw: unknown): Record<string, boolean> {
  const out = { ...SIDEBAR_FEATURE_DEFAULTS };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
  const r = raw as Record<string, unknown>;
  for (const [k, v] of Object.entries(r)) {
    if (k in out && typeof v === "boolean") out[k] = v;
  }
  if (!out.nav_team && out.nav_collaboration) {
    out.nav_collaboration = false;
  }
  // Legacy: Team covered collaboration before nav_collaboration existed — keep both on.
  if (out.nav_team && !("nav_collaboration" in r)) {
    out.nav_collaboration = true;
  }
  // SEO Hub + SEO & Blog merged into one sidebar item — either flag turns on Website & SEO.
  if (out.nav_seo_hub === true) {
    out.nav_seo = true;
  }
  return out;
}

export function isSidebarHrefEnabled(href: string, features: Record<string, boolean>): boolean {
  if (href === "/dashboard/team" || href === "/dashboard/collaboration") {
    return true;
  }
  if (href === "/dashboard/seo") {
    return features.nav_seo === true || features.nav_seo_hub === true;
  }
  const key = HREF_TO_FEATURE_KEY[href];
  if (!key) return true;
  return features[key] === true;
}

export type FeatureToggleRow = {
  key: string;
  label: string;
  description: string;
  /** Extra terms for search (e.g. sms, text) */
  keywords?: string[];
};

export const FEATURE_TOGGLE_GROUPS: { title: string; items: FeatureToggleRow[] }[] = [
  {
    title: "Main",
    items: [
      { key: "nav_messages", label: "Messages", description: "Inbox and conversations" },
      { key: "nav_customers", label: "Customers / pipeline", description: "People & pipeline" },
      { key: "nav_contacts", label: "Contacts", description: "Contact records" },
      { key: "nav_suppliers", label: "Suppliers", description: "Vendor relationships" },
      { key: "nav_investors", label: "Investors", description: "Funding pipeline and investor relationships" },
      { key: "nav_partners", label: "Partners", description: "Strategic and channel partnerships" },
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
      { key: "nav_broadcast", label: "Broadcast", description: "Campaigns to your list — retention and promos", keywords: ["whatsapp", "bulk", "promo", "campaign"] },
      { key: "nav_sms_marketing", label: "SMS Marketing", description: "Zilo notifications + your own business SMS — set up under Setup", keywords: ["sms", "text", "message", "marketing", "sender", "notification"] },
      { key: "nav_ai_scout", label: "AI Scout", description: "Autonomous agents — find leads, funding, social opportunities, and run tasks for you", keywords: ["scout", "ai", "agents", "action mode", "leads", "automation"] },
      { key: "nav_behavior_tracker", label: "Behavior Tracker", description: "GA4-powered discount campaigns triggered by visitor behavior on your site", keywords: ["behavior", "discount", "ga4", "tracking", "conversion", "cart"] },
      { key: "nav_social_scheduler", label: "Social scheduler", description: "Plan posts across networks" },
      { key: "nav_meta_ads", label: "Meta Ads", description: "Facebook & Instagram campaign planning" },
      { key: "nav_google_ads", label: "Google Ads", description: "Search & Performance Max planning" },
      { key: "nav_x_ads", label: "X Ads", description: "Promoted posts & campaigns on X (Twitter)" },
      { key: "nav_google_business", label: "Google Business Profile", description: "Maps & local presence via Integrations" },
      { key: "nav_social_inbox", label: "Social Inbox", description: "Unified DMs from all your connected social platforms" },
      { key: "nav_seo", label: "SEOhub", description: "Coach, keywords, content, autoblog site, and audits — one workspace" },
    ],
  },
  {
    title: "Business",
    items: [
      { key: "nav_analytics", label: "Analytics", description: "Dashboard metrics" },
      { key: "nav_team_analytics", label: "Team analytics", description: "Team performance" },
      { key: "nav_whatsapp", label: "WhatsApp", description: "WA tools" },
      { key: "nav_field_agents", label: "Field Agents", description: "Assign and track field rep tasks — check-ins, routes, and activity", keywords: ["field", "agents", "reps", "tasks", "check-in", "routes", "mobile"] },
      { key: "nav_smart_notes", label: "Zilo Notetaker", description: "AI meeting note-taker — auto-records and transcribes calendar meetings", keywords: ["notes", "meeting", "transcribe", "record", "notetaker", "ai"] },
      { key: "nav_team", label: "Team", description: "Members, roles, and team settings" },
      {
        key: "nav_collaboration",
        label: "Collaboration",
        description: "Workspaces, channel access, and routing — turns on automatically when Team is on",
      },
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
      { key: "nav_email", label: "Email Inbox", description: "Gmail or Outlook inbox with AI draft & auto-reply", keywords: ["gmail", "outlook", "inbox"] },
      { key: "nav_email_marketing", label: "Email Marketing", description: "Create and send email campaigns to your contacts", keywords: ["email", "newsletter", "campaign", "mail"] },
      { key: "nav_calendar", label: "Calendar", description: "Google or Outlook calendar with event management" },
      { key: "nav_shopify", label: "Shopify", description: "Orders, inventory, customers, abandoned carts & discounts" },
    { key: "nav_design_templates", label: "Design library", description: "Chat-generated graphics, PDFs, and decks plus optional manual template metadata" },
    { key: "nav_documents", label: "Documents", description: "AI-generated PDFs, Word docs, and presentations from Zilo Chat" },
    { key: "nav_growth", label: "Growth Suite", description: "Daily digest, autopilot follow-ups, deal room, competitor intel, voice input" },
    { key: "nav_client_portal", label: "Client Portal", description: "Share a portal link with clients to view their invoices, proposals & orders" },
    { key: "nav_store", label: "My Store", description: "Manage your WooCommerce store — products, orders, and payments" },
    ],
  },
  {
    title: "Display",
    items: [{ key: "nav_kds", label: "KDS display", description: "Kitchen screen (F&B types)" }],
  },
];

/** All toggle rows flat — useful for search / counts */
export function getAllFeatureToggleRows(): (FeatureToggleRow & { group: string })[] {
  return FEATURE_TOGGLE_GROUPS.flatMap((group) =>
    group.items.map((row) => ({ ...row, group: group.title }))
  );
}

/** Filter toggle groups by search query (label, description, group, keywords). */
export function filterFeatureToggleGroups(
  query: string,
  groups: { title: string; items: FeatureToggleRow[] }[] = FEATURE_TOGGLE_GROUPS
): { title: string; items: FeatureToggleRow[] }[] {
  const q = query.trim().toLowerCase();
  if (!q) return groups;
  const terms = q.split(/\s+/).filter(Boolean);
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((row) => {
        const haystack = [
          row.label,
          row.description,
          group.title,
          ...(row.keywords ?? []),
        ]
          .join(" ")
          .toLowerCase();
        return terms.every((term) => haystack.includes(term));
      }),
    }))
    .filter((g) => g.items.length > 0);
}

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
  nav_team: true,
  nav_collaboration: true,
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
  nav_team: true,
  nav_collaboration: true,
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
  nav_team: true,
  nav_collaboration: true,
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
  if (out.nav_team && !("nav_collaboration" in preset)) {
    out.nav_collaboration = true;
  }
  if (!out.nav_team) {
    out.nav_collaboration = false;
  }
  return out;
}

/** Enable every optional sidebar link (full workspace). */
export function allSidebarFeaturesOn(): Record<string, boolean> {
  const out = { ...SIDEBAR_FEATURE_DEFAULTS };
  for (const k of Object.keys(out)) out[k] = true;
  return out;
}

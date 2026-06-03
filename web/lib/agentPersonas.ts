/**
 * Friendly specialist personas for Zilo Chat UI.
 * Backend still routes by agent id; users see a first name + specialty tag for confidence.
 * Keep in sync when adding agents in backend `agents.py` AGENT_REGISTRY.
 */

export type AgentPersona = {
  /** First name shown in the UI */
  firstName: string;
  /** Short tag for compact badges, e.g. "Meta Ads" */
  tag: string;
  /** Full specialty line for tooltips, e.g. "Meta Ads specialist" */
  role: string;
  /** Tailwind classes for badge background/text */
  cls: string;
};

const DEFAULT: AgentPersona = {
  firstName: "Zilo",
  tag: "Guide",
  role: "Your CRM guide",
  cls: "bg-brand/15 text-brand-dark",
};

/**
 * Each specialist has a unique first name + tag. Names are intentionally **balanced**
 * between traditionally male and female first names (~50/50). Owner-requested names
 * stay on flagship roles (Elena, Rose, Angela, Ruby, Eve, Doris, Maureen, Stephen).
 * `general` stays Zilo (brand).
 */
const MAP: Record<string, AgentPersona> = {
  general: {
    firstName: "Zilo",
    tag: "Guide",
    role: "Your guide for everything in your business",
    cls: "bg-brand/15 text-brand-dark",
  },
  meta_ads: {
    firstName: "Elena",
    tag: "Meta Ads",
    role: "Meta Ads specialist — Facebook & Instagram campaigns",
    cls: "bg-blue-100 text-blue-800",
  },
  google_ads: {
    firstName: "Rose",
    tag: "Google Ads",
    role: "Google Ads specialist",
    cls: "bg-yellow-100 text-yellow-800",
  },
  x_ads: {
    firstName: "Angela",
    tag: "X Ads",
    role: "X (Twitter) Ads specialist",
    cls: "bg-slate-800 text-white",
  },
  social_media: {
    firstName: "Ruby",
    tag: "Social",
    role: "Social & organic content specialist",
    cls: "bg-pink-100 text-pink-800",
  },
  creative: {
    firstName: "Eve",
    tag: "Creative",
    role: "Creative & design specialist",
    cls: "bg-fuchsia-100 text-fuchsia-800",
  },
  design: {
    firstName: "Eve",
    tag: "Creative",
    role: "Creative & design specialist",
    cls: "bg-fuchsia-100 text-fuchsia-800",
  },
  sales: {
    firstName: "Stephen",
    tag: "Sales",
    role: "Sales & revenue specialist",
    cls: "bg-emerald-100 text-emerald-800",
  },
  customers: {
    firstName: "Doris",
    tag: "Customers",
    role: "Customers & CRM specialist",
    cls: "bg-brand/15 text-brand-dark",
  },
  orders: {
    firstName: "Daniel",
    tag: "Orders",
    role: "Orders & fulfillment specialist",
    cls: "bg-orange-100 text-orange-800",
  },
  broadcasts: {
    firstName: "Marcus",
    tag: "Broadcasts",
    role: "Broadcast messaging specialist",
    cls: "bg-cyan-100 text-cyan-800",
  },
  follow_ups: {
    firstName: "Dana",
    tag: "Follow-ups",
    role: "Follow-ups specialist",
    cls: "bg-amber-100 text-amber-800",
  },
  bookings: {
    firstName: "Brian",
    tag: "Bookings",
    role: "Bookings & appointments specialist",
    cls: "bg-teal-100 text-teal-800",
  },
  finance: {
    firstName: "Miranda",
    tag: "Finance",
    role: "Finance specialist",
    cls: "bg-green-100 text-green-800",
  },
  automations: {
    firstName: "Aaron",
    tag: "Automations",
    role: "Automations specialist",
    cls: "bg-brand/15 text-brand-dark",
  },
  shopify: {
    firstName: "Tyler",
    tag: "Shopify",
    role: "Shopify store specialist",
    cls: "bg-[#96BF48]/20 text-[#3a6000]",
  },
  shopify_orders: {
    firstName: "Chris",
    tag: "Shopify orders",
    role: "Shopify orders specialist",
    cls: "bg-lime-100 text-lime-800",
  },
  shopify_products: {
    firstName: "Morgan",
    tag: "Shopify products",
    role: "Shopify products specialist",
    cls: "bg-lime-100 text-lime-800",
  },
  shopify_analytics: {
    firstName: "Jason",
    tag: "Shopify analytics",
    role: "Shopify analytics specialist",
    cls: "bg-green-100 text-green-900",
  },
  stripe: {
    firstName: "Simon",
    tag: "Stripe",
    role: "Stripe payments specialist",
    cls: "bg-[#635BFF]/10 text-[#635BFF]",
  },
  klaviyo: {
    firstName: "Kim",
    tag: "Klaviyo",
    role: "Klaviyo email specialist",
    cls: "bg-green-50 text-green-800",
  },
  mailchimp: {
    firstName: "Max",
    tag: "Mailchimp",
    role: "Mailchimp specialist",
    cls: "bg-yellow-50 text-yellow-900",
  },
  brevo: {
    firstName: "Bea",
    tag: "Brevo",
    role: "Brevo specialist",
    cls: "bg-emerald-50 text-emerald-900",
  },
  slack: {
    firstName: "Steve",
    tag: "Slack",
    role: "Slack specialist",
    cls: "bg-[#4A154B]/10 text-[#4A154B]",
  },
  gmail: {
    firstName: "Grace",
    tag: "Gmail",
    role: "Gmail specialist",
    cls: "bg-red-50 text-red-700",
  },
  microsoft: {
    firstName: "Mike",
    tag: "Microsoft",
    role: "Microsoft 365 specialist",
    cls: "bg-blue-50 text-blue-800",
  },
  google_calendar: {
    firstName: "Cara",
    tag: "Calendar",
    role: "Google Calendar specialist",
    cls: "bg-emerald-50 text-emerald-800",
  },
  google_sheets: {
    firstName: "Gavin",
    tag: "Sheets",
    role: "Google Sheets specialist",
    cls: "bg-green-50 text-green-800",
  },
  notion: {
    firstName: "Nina",
    tag: "Notion",
    role: "Notion specialist",
    cls: "bg-slate-100 text-slate-800",
  },
  telegram: {
    firstName: "Tom",
    tag: "Telegram",
    role: "Telegram specialist",
    cls: "bg-sky-100 text-sky-800",
  },
  messages: {
    firstName: "Maya",
    tag: "Messages",
    role: "Messages & inbox specialist",
    cls: "bg-blue-100 text-blue-800",
  },
  contacts: {
    firstName: "Adam",
    tag: "Contacts",
    role: "Contacts specialist",
    cls: "bg-brand/15 text-brand-dark",
  },
  suppliers: {
    firstName: "Sydney",
    tag: "Suppliers",
    role: "Suppliers specialist",
    cls: "bg-stone-100 text-stone-800",
  },
  payments: {
    firstName: "Paul",
    tag: "Payments",
    role: "Payments specialist",
    cls: "bg-emerald-100 text-emerald-900",
  },
  invoices: {
    firstName: "Ivy",
    tag: "Invoices",
    role: "Invoices specialist",
    cls: "bg-teal-100 text-teal-800",
  },
  quotes: {
    firstName: "Quentin",
    tag: "Quotes",
    role: "Quotes specialist",
    cls: "bg-cyan-100 text-cyan-900",
  },
  analytics: {
    firstName: "Anna",
    tag: "Analytics",
    role: "Analytics specialist",
    cls: "bg-brand/15 text-brand-dark",
  },
  team_analytics: {
    firstName: "Theo",
    tag: "Team analytics",
    role: "Team analytics specialist",
    cls: "bg-brand/15 text-brand-dark",
  },
  team: {
    firstName: "Tanya",
    tag: "Team",
    role: "Team & access specialist",
    cls: "bg-slate-200 text-slate-800",
  },
  inventory: {
    firstName: "Ian",
    tag: "Inventory",
    role: "Inventory specialist",
    cls: "bg-orange-100 text-orange-900",
  },
  loyalty: {
    firstName: "Lucy",
    tag: "Loyalty",
    role: "Loyalty specialist",
    cls: "bg-rose-100 text-rose-800",
  },
  nps: {
    firstName: "Nicole",
    tag: "Feedback",
    role: "Customer feedback (NPS) specialist",
    cls: "bg-fuchsia-100 text-fuchsia-900",
  },
  social_inbox: {
    firstName: "Ines",
    tag: "Social inbox",
    role: "Social inbox specialist",
    cls: "bg-pink-100 text-pink-800",
  },
  social_scheduler: {
    firstName: "Samuel",
    tag: "Scheduler",
    role: "Social scheduling specialist",
    cls: "bg-brand/10 text-brand-dark",
  },
  social_monitor: {
    firstName: "Monica",
    tag: "Social insights",
    role: "Social performance specialist",
    cls: "bg-pink-50 text-pink-900",
  },
  whatsapp: {
    firstName: "William",
    tag: "WhatsApp",
    role: "WhatsApp specialist",
    cls: "bg-green-100 text-green-800",
  },
  shop: {
    firstName: "Scott",
    tag: "Shop",
    role: "Shop & catalog specialist",
    cls: "bg-amber-100 text-amber-900",
  },
  document: {
    firstName: "Maureen",
    tag: "Documents",
    role: "Documents & business writing specialist",
    cls: "bg-violet-100 text-violet-900",
  },
  forms: {
    firstName: "Fiona",
    tag: "Forms",
    role: "Forms & feedback specialist",
    cls: "bg-purple-100 text-purple-900 border border-purple-200",
  },
  zilo_support: {
    firstName: "Zoe",
    tag: "Zilo Support",
    role: "Zilo Support specialist",
    cls: "bg-emerald-100 text-emerald-900 border border-emerald-300",
  },
};

function titleCaseId(raw: string): string {
  return raw
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Resolve persona for an agent id from the API (falls back to title-cased id). */
export function getAgentPersona(agentId: string | null | undefined): AgentPersona {
  if (!agentId || typeof agentId !== "string") return DEFAULT;
  const key = agentId.trim().toLowerCase();
  return MAP[key] ?? {
    firstName: titleCaseId(key),
    tag: "Specialist",
    role: `${titleCaseId(key)} specialist`,
    cls: "bg-slate-100 text-slate-700",
  };
}

/** Compact badge: "Elena · Meta Ads" or "Zilo" for general. */
export function personaBadgeLabel(agentId: string | null | undefined): string {
  const p = getAgentPersona(agentId);
  if (!agentId || agentId === "general") return "Zilo";
  return `${p.firstName} · ${p.tag}`;
}

/** Handoff line between messages when the specialist changes. */
export function personaHandoffLine(agentId: string | null | undefined): string {
  const p = getAgentPersona(agentId);
  if (!agentId || agentId === "general") return "Zilo";
  return `${p.firstName} — ${p.role}`;
}

/** Thinking state: first name + specialty hint */
export function personaThinkingLabel(agentId: string | null | undefined): string {
  const p = getAgentPersona(agentId);
  if (!agentId || agentId === "general") return "Zilo";
  return `${p.firstName} (${p.tag})`;
}

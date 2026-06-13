/** Marketing plan matrix — keep in sync with landing pricing table. */
export const PLAN_SLUGS = ["starter", "standard", "pro"] as const;
export type PlanSlug = (typeof PLAN_SLUGS)[number];

export const PLAN_LABELS: Record<PlanSlug, string> = {
  starter: "Starter",
  standard: "Growth",
  pro: "Pro",
};

export const LANDING_USD = { starter: 49, standard: 79, pro: 200 } as const;
export const LANDING_MESSAGE_CAPS = { starter: 5000, standard: 10000, pro: 25000 } as const;
export const TRIAL_CREDITS = 100;
export const TRIAL_DAYS = process.env.NEXT_PUBLIC_BILLING_TRIAL_DAYS || "14";

export type PlanRow = {
  label: string;
  starter: string | boolean;
  growth: string | boolean;
  pro: string | boolean;
};

export const PRICING_ROWS: PlanRow[] = [
  { label: "Price", starter: "$49/mo", growth: "$79/mo", pro: "$200/mo" },
  { label: "Messages", starter: "5,000", growth: "10,000", pro: "25,000" },
  { label: "Customers", starter: "Unlimited", growth: "Unlimited", pro: "Unlimited" },
  { label: "AI replies", starter: true, growth: true, pro: true },
  { label: "Follow-ups & broadcasts", starter: true, growth: true, pro: true },
  { label: "Priority support", starter: false, growth: true, pro: false },
  { label: "Dedicated support", starter: false, growth: false, pro: true },
  { label: "Advanced analytics", starter: false, growth: false, pro: true },
  { label: "Custom templates", starter: false, growth: false, pro: true },
];

export function formatUsdMonthlyPrice(slug: PlanSlug): string {
  return `$${LANDING_USD[slug]}/mo`;
}

// TODO: this is a temporary function to redirect the user to the billing page
export function plansCtaHref(isAuthenticated: boolean, dashboardAccess: boolean): string {
  if (!isAuthenticated) return "/plans";
  if (dashboardAccess) return "/dashboard/billing";
  return "/dashboard/billing";
}

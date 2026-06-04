"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { CreditCard, ExternalLink, Loader2, Sparkles } from "lucide-react";
import { PricingTable } from "@/components/billing/PricingTable";
import { useSubscription } from "@/hooks/useSubscription";
import { subscriptionApi, type SubscriptionPlan } from "@/lib/api";
import { PLAN_LABELS, PLAN_SLUGS, formatUsdMonthlyPrice, type PlanSlug } from "@/lib/billing/plans";

const INCLUDED_ALL_PLANS = [
  "AI replies (autoreply & drafted WhatsApp responses)",
  "Follow-ups and broadcasts",
  "Unlimited customers",
  "Outbound messaging up to your plan's monthly cap",
];

function BillingPageContent() {
  const searchParams = useSearchParams();
  const { entitlements, loading, refresh, dashboardAccess, paidActive, trialActive } = useSubscription();
  const trialAvailable = entitlements?.trial_available ?? false;
  const [checkoutPlans, setCheckoutPlans] = useState<SubscriptionPlan[]>([]);
  const [invoices, setInvoices] = useState<
    Array<{ id: string; number?: string; status?: string; hosted_invoice_url?: string }>
  >([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (searchParams.get("checkout") === "success") {
      toast.success("Subscription updated. It may take a moment to reflect.");
      void refresh();
    }
  }, [searchParams, refresh]);

  useEffect(() => {
    subscriptionApi.plans().then(setCheckoutPlans).catch(() => setCheckoutPlans([]));
  }, []);

  const checkoutById = Object.fromEntries(checkoutPlans.map((p) => [p.id, p]));
  const checkoutCurrency = checkoutPlans[0]?.currency;
  const regionalCheckout =
    checkoutCurrency && checkoutCurrency !== "USD" && checkoutPlans.length > 0;

  useEffect(() => {
    if (!paidActive) return;
    subscriptionApi
      .invoices()
      .then((r) => setInvoices(r.invoices || []))
      .catch(() => setInvoices([]));
  }, [paidActive]);

  const startTrial = useCallback(async () => {
    setBusy("trial");
    try {
      await subscriptionApi.startTrial();
      toast.success("Free trial started");
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start trial");
    } finally {
      setBusy(null);
    }
  }, [refresh]);

  const subscribe = useCallback(async (planId: string) => {
    setBusy(planId);
    try {
      const { url } = await subscriptionApi.checkout(planId);
      window.location.href = url;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Checkout unavailable");
      setBusy(null);
    }
  }, []);

  const openPortal = useCallback(async () => {
    setBusy("portal");
    try {
      const { url } = await subscriptionApi.portal();
      window.location.href = url;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Billing portal unavailable");
      setBusy(null);
    }
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand-dark" />
      </div>
    );
  }

  const planName = entitlements?.subscription_plan
    ? PLAN_LABELS[entitlements.subscription_plan as PlanSlug]
    : undefined;
  const usage = entitlements?.usage;
  const cap = usage?.outbound_messages_cap ?? 0;
  const used = usage?.outbound_messages_month ?? 0;
  const pct = cap > 0 ? Math.min(100, Math.round((used / cap) * 100)) : 0;

  return (
    <div className="mx-auto max-w-5xl space-y-10 p-6 pb-16">
      <div>
        <h1 className="text-2xl font-bold text-brand-ink">Billing</h1>
        <p className="mt-1 text-slate-600">
          {dashboardAccess
            ? "Manage your plan, usage, and invoices."
            : "Choose a plan or start your free trial to unlock the dashboard."}
        </p>
      </div>

      {!dashboardAccess && !trialActive && (
        <section className="rounded-2xl border border-brand/25 bg-brand/5 p-6">
          <h2 className="text-lg font-semibold text-brand-ink">
            {trialAvailable ? "Get access" : "Trial ended"}
          </h2>
          <p className="mt-2 text-sm text-slate-700">
            {trialAvailable
              ? "Start your free trial or subscribe to use the CRM dashboard and messaging features."
              : "Your free trial has ended. Choose a paid plan below to unlock the dashboard and messaging again."}
          </p>
          <ul className="mt-4 list-inside list-disc space-y-1 text-sm text-slate-800">
            {INCLUDED_ALL_PLANS.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {trialAvailable && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void startTrial()}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-brand-dark px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand hover:text-brand-ink disabled:opacity-60"
            >
              {busy === "trial" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Start free trial
            </button>
          )}
        </section>
      )}

      {dashboardAccess && (
        <section className="grid gap-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:grid-cols-2">
          <div>
            <p className="text-sm font-medium text-slate-500">Current plan</p>
            <p className="mt-1 text-xl font-semibold text-brand-ink">
              {trialActive ? "Free trial" : planName || entitlements?.effective_plan || "—"}
            </p>
            {trialActive && entitlements?.trial_ends_at && (
              <p className="mt-1 text-sm text-slate-600">
                Trial ends {new Date(entitlements.trial_ends_at).toLocaleDateString()}
              </p>
            )}
            {paidActive && entitlements?.subscription_cancel_at_period_end && (
              <p className="mt-2 text-sm text-amber-700">Cancels at end of billing period</p>
            )}
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500">Outbound messages this month</p>
            <p className="mt-1 text-xl font-semibold text-brand-ink">
              {used.toLocaleString()} / {cap > 0 ? cap.toLocaleString() : "—"}
              {trialActive && cap > 0 ? (
                <span className="ml-2 text-sm font-normal text-slate-500">
                  ({cap.toLocaleString()} messages included)
                </span>
              ) : null}
            </p>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-brand-dark transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
          {paidActive && (
            <div className="md:col-span-2 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void openPortal()}
                disabled={busy !== null}
                className="inline-flex items-center gap-2 rounded-xl border border-brand-dark/30 bg-white px-4 py-2 text-sm font-semibold text-brand-ink hover:bg-brand/5"
              >
                {busy === "portal" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />}
                Manage subscription
              </button>
              <Link href="/dashboard" className="inline-flex items-center text-sm font-semibold text-brand-dark hover:text-brand-ink hover:underline">
                Back to dashboard
              </Link>
            </div>
          )}
        </section>
      )}

      <section>
        <h2 className="text-lg font-semibold text-brand-ink">
          {paidActive ? "Change plan" : trialActive ? "Upgrade plan" : "Plans"}
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          {trialActive
            ? "Subscribe anytime — checkout opens in Stripe. Your trial stays active until it ends or you upgrade."
            : "USD reference pricing (same as our homepage). Regional amounts apply in Stripe when your account uses another currency."}
        </p>
        <div className="mt-6">
          <PricingTable highlightGrowth />
        </div>
        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {PLAN_SLUGS.map((slug) => (
            <button
              key={slug}
              type="button"
              disabled={busy !== null}
              onClick={() => void subscribe(slug)}
              className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-brand-dark hover:ring-1 hover:ring-brand/20 disabled:opacity-60"
            >
              <p className="font-semibold text-brand-ink">{PLAN_LABELS[slug]}</p>
              <p className="mt-1 text-lg font-bold text-brand-dark">{formatUsdMonthlyPrice(slug)}</p>
              <p className="mt-2 text-xs text-slate-500">Subscribe via secure checkout</p>
            </button>
          ))}
        </div>
        {regionalCheckout ? (
          <p className="mt-3 text-xs text-slate-500">
            Your account is set to {checkoutCurrency}. Stripe checkout may show regional prices (e.g.{" "}
            {checkoutById.starter?.amount_display ?? "local pricing"}) instead of the USD reference above.
          </p>
        ) : null}
      </section>

      {paidActive && invoices.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-brand-ink">Invoices</h2>
          <ul className="mt-4 divide-y divide-slate-100">
            {invoices.map((inv) => (
              <li key={inv.id} className="flex items-center justify-between py-3 text-sm">
                <span>
                  {inv.number || inv.id} · {inv.status}
                </span>
                {inv.hosted_invoice_url && (
                  <a
                    href={inv.hosted_invoice_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-brand-dark hover:text-brand-ink hover:underline"
                  >
                    View <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-2xl border border-brand/15 bg-brand/5 p-6 text-sm text-slate-600">
        <p className="font-medium text-brand-ink">What&apos;s included on paid plans</p>
        <ul className="mt-2 list-inside list-disc space-y-1">
          {INCLUDED_ALL_PLANS.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="mt-4 font-medium text-brand-ink">Tier-specific (paid only)</p>
        <ul className="mt-2 list-inside list-disc space-y-1">
          <li>Priority support — Growth</li>
          <li>Dedicated support, advanced analytics, custom templates — Pro</li>
        </ul>
        <p className="mt-4">
          <Link href="/plans" className="font-semibold text-brand-dark hover:text-brand-ink hover:underline">
            View public plans page
          </Link>
        </p>
      </section>
    </div>
  );
}

export default function DashboardBillingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center p-6">
          <Loader2 className="h-8 w-8 animate-spin text-brand-dark" />
        </div>
      }
    >
      <BillingPageContent />
    </Suspense>
  );
}
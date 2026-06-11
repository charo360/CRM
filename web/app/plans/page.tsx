"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { PricingTable } from "@/components/billing/PricingTable";
import { ZiloLogo } from "@/components/ZiloLogo";
import { subscriptionApi, type SubscriptionPlan } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import { PLAN_LABELS, TRIAL_CREDITS, TRIAL_DAYS, formatUsdMonthlyPrice, type PlanSlug } from "@/lib/billing/plans";

export default function PlansPage() {
  const loggedIn = isAuthenticated();
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);

  useEffect(() => {
    subscriptionApi.publicPlans("USD").then(setPlans).catch(() => setPlans([]));
  }, []);

  const billingHref = loggedIn ? "/dashboard/billing" : "/login?next=/dashboard/billing";

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2">
            <ZiloLogo className="h-8 w-auto" />
          </Link>
          <div className="flex items-center gap-3">
            {!loggedIn && (
              <Link href="/login" className="text-sm font-medium text-slate-600 hover:text-slate-900">
                Sign in
              </Link>
            )}
            <Link
              href={billingHref}
              className="inline-flex items-center gap-2 rounded-xl bg-[#009B3A] px-4 py-2 text-sm font-semibold text-white hover:bg-[#007a2e]"
            >
              {loggedIn ? "Billing" : "Free trial"}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Plans &amp; billing</h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-600">
            Same pricing as our homepage. New accounts get a {TRIAL_DAYS}-day free trial with {TRIAL_CREDITS.toLocaleString()} outbound messages; then subscribe to keep access.
          </p>
        </div>

        <PricingTable />

        {plans.length > 0 && (
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {plans.map((plan) => (
              <div
                key={plan.id}
                className={`rounded-2xl border bg-white p-6 shadow-sm ${
                  plan.id === "standard" ? "border-sky-300 ring-2 ring-sky-100" : "border-slate-200"
                }`}
              >
                <h3 className="text-lg font-semibold text-slate-900">
                  {PLAN_LABELS[plan.id as PlanSlug] ?? plan.name}
                </h3>
                <p className="mt-2 text-2xl font-bold text-slate-900">
                  {formatUsdMonthlyPrice(plan.id as PlanSlug)}
                </p>
                <ul className="mt-4 space-y-2 text-sm text-slate-600">
                  {plan.features.slice(0, 5).map((f) => (
                    <li key={f}>• {f}</li>
                  ))}
                </ul>
                <Link
                  href={loggedIn ? billingHref : `/login?next=/dashboard/billing&plan=${plan.id}`}
                  className="mt-6 inline-flex w-full items-center justify-center rounded-xl border border-[#007a2e] bg-[#009B3A] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#4CD137] hover:text-[#0a2614]"
                >
                  {loggedIn ? "Manage in billing" : "Sign up to subscribe"}
                </Link>
              </div>
            ))}
          </div>
        )}

        <p className="mt-8 text-center text-xs text-slate-500">
          USD reference; regional pricing applies at checkout. Payment requires an account.
        </p>
      </main>
    </div>
  );
}

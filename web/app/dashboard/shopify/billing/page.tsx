"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Check as CheckIcon } from "lucide-react";

import { getToken } from "@/lib/auth";
import { API_BASE } from "@/lib/api";

interface Plan {
  id: string;
  name: string;
  price: number;
  trial_days: number;
  messages: number;
  features: string[];
}

const PLAN_HIGHLIGHTS: Record<string, { color: string; badge: string | null }> = {
  starter: { color: "border-gray-200", badge: null },
  growth:  { color: "border-[#4F46E5]", badge: "Most Popular" },
  pro:     { color: "border-gray-200", badge: null },
};

export default function ShopifyBillingPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-gray-50"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" /></div>}>
      <BillingContent />
    </Suspense>
  );
}

function BillingContent() {
  const params     = useSearchParams();
  const router     = useRouter();
  const shop       = params.get("shop") || "";
  const isReinstall = params.get("reinstall") === "1";
  const billingError = params.get("billing_error") || "";

  const [plans, setPlans]         = useState<Plan[]>([]);
  const [loading, setLoading]     = useState(true);
  const [subscribing, setSubscribing] = useState<string | null>(null);
  const [error, setError]         = useState(billingError || "");

  useEffect(() => {
    fetch(`${API_BASE}/shopify/billing/plans`)
      .then((r) => r.json())
      .then((data) => setPlans(data.plans || []))
      .catch(() => setError("Failed to load plans. Please refresh."))
      .finally(() => setLoading(false));
  }, []);

  async function subscribe(planId: string) {
    setSubscribing(planId);
    setError("");
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/shopify/billing/create`, {
        method:  "POST",
        headers: { 
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body:    JSON.stringify({ plan_id: planId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Subscription failed");
      if (data.confirmation_url) {
        window.location.href = data.confirmation_url;
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong. Please try again.");
      setSubscribing(null);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-16 px-4">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 text-sm font-medium px-4 py-1.5 rounded-full mb-4">
            {isReinstall ? "Welcome back — reactivate your plan" : `Installing Zilo CRM for ${shop}`}
          </div>
          <h1 className="text-4xl font-bold text-gray-900 mb-3">
            Choose your plan
          </h1>
          <p className="text-gray-500 text-lg">
            All plans include a {plans[0]?.trial_days ?? 14}-day free trial.
            No charge until your trial ends.
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-8 bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm text-center">
            {errorMessage(error)}
          </div>
        )}

        {/* Plan cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {plans.map((plan) => {
            const meta = PLAN_HIGHLIGHTS[plan.id] ?? { color: "border-gray-200", badge: null };
            const isPopular = !!meta.badge;
            const isLoading = subscribing === plan.id;

            return (
              <div
                key={plan.id}
                className={`relative bg-white rounded-2xl border-2 ${meta.color} shadow-sm flex flex-col`}
              >
                {isPopular && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                    <span className="bg-indigo-600 text-white text-xs font-semibold px-4 py-1 rounded-full">
                      {meta.badge}
                    </span>
                  </div>
                )}

                <div className="p-7 flex-1">
                  <h2 className="text-xl font-bold text-gray-900 mb-1">{plan.name}</h2>
                  <div className="flex items-end gap-1 mb-6">
                    <span className="text-4xl font-extrabold text-gray-900">
                      ${plan.price.toFixed(0)}
                    </span>
                    <span className="text-gray-500 mb-1">/month</span>
                  </div>

                  <ul className="space-y-3">
                    {plan.features.map((f) => (
                      <li key={f} className="flex items-start gap-2 text-sm text-gray-700">
                        <CheckIcon className="h-4 w-4 text-indigo-600 mt-0.5 shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="px-7 pb-7">
                  <button
                    onClick={() => subscribe(plan.id)}
                    disabled={!!subscribing}
                    className={`w-full py-3 rounded-xl font-semibold text-sm transition
                      ${isPopular
                        ? "bg-indigo-600 text-white hover:bg-indigo-700"
                        : "bg-gray-900 text-white hover:bg-gray-800"}
                      disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2`}
                  >
                    {isLoading ? (
                      <>
                        <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                        Redirecting…
                      </>
                    ) : (
                      `Start ${plan.trial_days}-day free trial`
                    )}
                  </button>
                  <p className="text-xs text-gray-400 text-center mt-2">
                    Billed through Shopify · Cancel anytime
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer note */}
        <p className="text-center text-sm text-gray-400 mt-10">
          Prices are billed in USD through Shopify. Your subscription includes access to
          all Zilo CRM features including AI assistant, broadcasts, analytics, and more.
          Pricing may be updated in the future — you&apos;ll always be notified before any changes.
        </p>
      </div>
    </div>
  );
}

function errorMessage(code: string): string {
  const map: Record<string, string> = {
    declined:           "You declined the subscription. Choose a plan below to continue.",
    activation_failed:  "We could not activate your subscription. Please try again.",
    charge_lookup_failed: "Could not verify your subscription status. Please try again.",
    shop_not_found:     "Store not found. Please reinstall the app.",
    missing_params:     "Invalid billing session. Please reinstall the app.",
  };
  return map[code] || `Billing error (${code}). Please try again or contact support.`;
}

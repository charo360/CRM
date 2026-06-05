"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { subscriptionApi } from "@/lib/api";
import { useSubscription } from "@/hooks/useSubscription";

export function EntitlementBanner() {
  const { entitlements, trialActive, paidActive, refresh } = useSubscription();
  const [busy, setBusy] = useState(false);

  const startTrial = useCallback(async () => {
    setBusy(true);
    try {
      await subscriptionApi.startTrial();
      toast.success("Free trial started");
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not start trial");
    } finally {
      setBusy(false);
    }
  }, [refresh]);
  const trialAvailable = entitlements?.trial_available ?? false;
  if (paidActive || trialActive) return null;

  return (
    <div className="border-b border-brand/20 bg-brand/5 px-4 py-3 sm:px-6">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 text-sm">
        <p className="text-slate-700">
          {trialAvailable
            ? "Start your 14-day trial to unlock messaging, broadcasts, automations, and AI features."
            : "Your trial has ended. You can keep exploring in read-only mode and upgrade to unlock sending and automation features."}
        </p>
        <div className="flex items-center gap-2">
          {trialAvailable && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void startTrial()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand disabled:opacity-60"
            >
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              Start 14-day trial
            </button>
          )}
          <Link
            href="/dashboard/billing"
            className="rounded-lg border border-brand-dark/20 bg-white px-3 py-1.5 text-xs font-semibold text-brand-ink hover:bg-brand/10"
          >
            View plans
          </Link>
        </div>
      </div>
    </div>
  );
}

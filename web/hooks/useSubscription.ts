"use client";

import { useCallback, useEffect, useState } from "react";
import { subscriptionApi, type Entitlements } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";

function featureEnabled(entitlements: Entitlements | null, keys: string[], fallback: boolean): boolean {
  if (!entitlements) return false;
  for (const key of keys) {
    if (entitlements.features?.[key] === true) return true;
  }
  return fallback;
}

export function useSubscription() {
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!isAuthenticated()) {
      setEntitlements(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const ent = await subscriptionApi.entitlements();
      setEntitlements(ent);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load subscription");
      setEntitlements(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    entitlements,
    loading,
    error,
    refresh,
    dashboardAccess: isAuthenticated(),
    canAccessApp: isAuthenticated(),
    canSendMessages: featureEnabled(entitlements, ["can_send_messages", "send_messages"], !!(entitlements?.paid_active || entitlements?.trial_active)),
    canUseAi: featureEnabled(entitlements, ["can_use_ai", "use_ai"], !!(entitlements?.paid_active || entitlements?.trial_active)),
    canCreateBroadcasts: featureEnabled(entitlements, ["can_create_broadcasts", "create_broadcasts"], !!(entitlements?.paid_active || entitlements?.trial_active)),
    canUseAutomations: featureEnabled(entitlements, ["can_use_automations", "use_automations"], !!(entitlements?.paid_active || entitlements?.trial_active)),
    paidActive: entitlements?.paid_active ?? false,
    trialActive: entitlements?.trial_active ?? false,
  };
}

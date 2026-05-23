"use client";

import { useCallback, useEffect, useState } from "react";
import { subscriptionApi, type Entitlements } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";

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
    dashboardAccess: entitlements?.dashboard_access ?? false,
    paidActive: entitlements?.paid_active ?? false,
    trialActive: entitlements?.trial_active ?? false,
  };
}

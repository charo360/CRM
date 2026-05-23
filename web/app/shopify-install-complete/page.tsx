"use client";

import { useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { setToken } from "@/lib/auth";

/**
 * Landing page after a Shopify App Store install.
 *
 * The backend OAuth callback redirects here with:
 *   ?token=<zilo-jwt>&shop=<shop>&reinstall=0|1
 *
 * This page stores the token in localStorage then forwards the merchant
 * to the Shopify billing selection page so they can choose a plan.
 * Using Shopify Billing API — no off-platform charges.
 */
export default function ShopifyInstallComplete() {
  const params = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const token = params.get("token");
    const shop = params.get("shop") || "";
    const reinstall = params.get("reinstall") || "0";

    if (token) {
      setToken(token);
    }

    router.replace(
      `/dashboard/shopify/billing?shop=${encodeURIComponent(shop)}&reinstall=${reinstall}`
    );
  }, [params, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mx-auto mb-4" />
        <p className="text-gray-500 text-sm">Setting up your account…</p>
      </div>
    </div>
  );
}

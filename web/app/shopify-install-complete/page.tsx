"use client";

import { useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { setToken } from "@/lib/auth";

function InstallCompleteContent() {
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

export default function ShopifyInstallComplete() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    }>
      <InstallCompleteContent />
    </Suspense>
  );
}

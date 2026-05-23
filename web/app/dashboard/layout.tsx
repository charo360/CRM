"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Toaster } from "sonner";
import { isAuthenticated } from "@/lib/auth";
import { subscriptionApi } from "@/lib/api";
import { BusinessProvider } from "@/contexts/BusinessContext";
import { ZernioAccountsProvider } from "@/contexts/ZernioAccountsContext";
import Sidebar from "@/components/Sidebar";
import Navbar from "@/components/Navbar";
import AssistantLauncher from "@/components/AssistantLauncher";
import CommandBar from "@/components/CommandBar";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";

/**
 * Auth uses localStorage, which is absent on the server. Without a client-only gate,
 * the server renders `null` while the client renders the shell — a hydration mismatch.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (isAuthenticated()) return;
    const id = window.setTimeout(() => {
      router.replace("/login");
    }, 0);
    return () => window.clearTimeout(id);
  }, [mounted, router]);

  useEffect(() => {
    if (!mounted || !isAuthenticated()) return;
    if (pathname?.startsWith("/dashboard/billing")) return;
    let cancelled = false;
    subscriptionApi
      .entitlements()
      .then((ent) => {
        if (!cancelled && !ent.dashboard_access) {
          router.replace("/dashboard/billing");
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [mounted, pathname, router]);

  if (mounted && !isAuthenticated()) {
    return null;
  }

  return (
    <BusinessProvider>
      <ZernioAccountsProvider>
        <div className="flex h-screen bg-slate-50" suppressHydrationWarning>
          {!mounted ? (
            <aside
              className="flex w-56 shrink-0 flex-col overflow-y-auto border-r border-brand-dark/20 bg-[#071a10] text-slate-100 min-h-screen"
              aria-hidden
            />
          ) : (
            <Sidebar />
          )}

          <div className="flex flex-1 flex-col overflow-hidden">
            {mounted && <Navbar />}
            <main className="flex-1 overflow-auto bg-slate-50 text-slate-900">{children}</main>
          </div>
        </div>
        {mounted && <AssistantLauncher />}
        {mounted && <CommandBar />}
        {mounted && <OnboardingWizard />}
        <Toaster richColors position="top-center" />
      </ZernioAccountsProvider>
    </BusinessProvider>
  );
}

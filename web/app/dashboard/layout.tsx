"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Toaster } from "sonner";
import { isAuthenticated } from "@/lib/auth";
import { subscriptionApi } from "@/lib/api";
import { BusinessProvider } from "@/contexts/BusinessContext";
import { ZernioAccountsProvider } from "@/contexts/ZernioAccountsContext";
import { MeetingRecorderProvider } from "@/contexts/MeetingRecorderContext";
import Sidebar from "@/components/Sidebar";
import Navbar from "@/components/Navbar";
import AssistantLauncher from "@/components/AssistantLauncher";
import CommandBar from "@/components/CommandBar";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";
import MeetingOverlay from "@/components/MeetingOverlay";

/**
 * Auth uses localStorage, which is absent on the server. Without a client-only gate,
 * the server renders `null` while the client renders the shell — a hydration mismatch.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  // Defer auth redirect to the next macrotask so the App Router action queue is ready
  // (avoids "Router action dispatched before initialization" during dev / HMR).
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
        <MeetingRecorderProvider>
          <div className="flex h-[100dvh] min-h-screen bg-slate-50" suppressHydrationWarning>
            {mounted && mobileNavOpen && (
              <button
                type="button"
                aria-label="Close navigation menu"
                className="fixed inset-0 z-40 bg-black/50 lg:hidden"
                onClick={() => setMobileNavOpen(false)}
              />
            )}

            {!mounted ? (
              <aside
                className="hidden w-56 shrink-0 flex-col overflow-y-auto border-r border-brand-dark/20 bg-[#071a10] text-slate-100 min-h-screen lg:flex"
                aria-hidden
              />
            ) : (
              <Sidebar mobileOpen={mobileNavOpen} onMobileClose={() => setMobileNavOpen(false)} />
            )}

            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
              {mounted && (
                <Navbar
                  onMenuClick={() => setMobileNavOpen(true)}
                  onSearchClick={() =>
                    window.dispatchEvent(
                      new KeyboardEvent("keydown", { key: "k", metaKey: true, ctrlKey: true, bubbles: true })
                    )
                  }
                />
              )}

              <main className="flex-1 overflow-x-hidden overflow-y-auto bg-slate-50 text-slate-900">{children}</main>
            </div>
          </div>
          {mounted && <AssistantLauncher />}
          {mounted && <CommandBar />}
          {mounted && <OnboardingWizard />}
          {mounted && <MeetingOverlay />}
          <Toaster richColors position="top-center" />
        </MeetingRecorderProvider>
      </ZernioAccountsProvider>
    </BusinessProvider>
  );
}

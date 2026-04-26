"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Toaster } from "sonner";
import { isAuthenticated } from "@/lib/auth";
import { BusinessProvider } from "@/contexts/BusinessContext";
import Sidebar from "@/components/Sidebar";
import AssistantLauncher from "@/components/AssistantLauncher";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";

/**
 * Auth uses localStorage, which is absent on the server. Without a client-only gate,
 * the server renders `null` while the client renders the shell — a hydration mismatch.
 * Browser extensions that inject nodes into the layout can also trigger warnings; we
 * set suppressHydrationWarning on the shell for that case.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (!isAuthenticated()) {
      router.replace("/login");
    }
  }, [router]);

  if (mounted && !isAuthenticated()) {
    return null;
  }

  return (
    <BusinessProvider>
      <div className="flex h-screen bg-slate-50" suppressHydrationWarning>
        {!mounted ? (
          <aside
            className="flex w-56 shrink-0 flex-col overflow-y-auto border-r border-brand-dark/20 bg-[#071a10] text-slate-100 min-h-screen"
            aria-hidden
          />
        ) : (
          <Sidebar />
        )}
        <main className="flex-1 overflow-auto bg-slate-50 text-slate-900">{children}</main>
      </div>
      {mounted && <AssistantLauncher />}
      {mounted && <OnboardingWizard />}
      <Toaster richColors position="top-center" />
    </BusinessProvider>
  );
}

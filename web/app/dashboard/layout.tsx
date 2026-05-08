"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Toaster } from "sonner";
import { isAuthenticated } from "@/lib/auth";
import { BusinessProvider } from "@/contexts/BusinessContext";
import Sidebar from "@/components/Sidebar";
import Navbar from "@/components/Navbar";
import AssistantLauncher from "@/components/AssistantLauncher";
import CommandBar from "@/components/CommandBar";
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
  }, []);

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

  if (mounted && !isAuthenticated()) {
    return null;
  }

  return (
    <BusinessProvider>
      <div className="flex h-screen bg-slate-50" suppressHydrationWarning>
        {/* Sidebar */}
        {!mounted ? (
          <aside
            className="flex w-56 shrink-0 flex-col overflow-y-auto border-r border-brand-dark/20 bg-[#071a10] text-slate-100 min-h-screen"
            aria-hidden
          />
        ) : (
          <Sidebar />
        )}
        
        {/* Right side - Navbar and Main Content */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Sticky Navbar */}
          {mounted && <Navbar />}
          
          {/* Main Content */}
          <main className="flex-1 overflow-auto bg-slate-50 text-slate-900">{children}</main>
        </div>
      </div>
      {mounted && <AssistantLauncher />}
      {mounted && <CommandBar />}
      {mounted && <OnboardingWizard />}
      <Toaster richColors position="top-center" />
    </BusinessProvider>
  );
}

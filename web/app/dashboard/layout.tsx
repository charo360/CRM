"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Toaster } from "sonner";
import { isAuthenticated } from "@/lib/auth";
import { BusinessProvider } from "@/contexts/BusinessContext";
import Sidebar from "@/components/Sidebar";
import AssistantLauncher from "@/components/AssistantLauncher";

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
            className="flex flex-col w-56 min-h-screen bg-slate-900 text-slate-100 shrink-0 overflow-y-auto"
            aria-hidden
          />
        ) : (
          <Sidebar />
        )}
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
      {mounted && <AssistantLauncher />}
      <Toaster richColors position="top-center" />
    </BusinessProvider>
  );
}

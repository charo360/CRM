"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { adminApi } from "@/lib/api";
import {
  Users,
  BarChart2,
  Settings,
  LogOut,
  Shield,
  ChevronRight,
  MessageCircle,
  Flag,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/admin", label: "Users", icon: Users, exact: true },
  { href: "/admin/analytics", label: "Analytics", icon: BarChart2 },
  { href: "/admin/whatsapp", label: "WhatsApp", icon: MessageCircle },
  { href: "/admin/shops", label: "Reported shops", icon: Flag },
  { href: "/admin/settings", label: "Settings", icon: Settings },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checking, setChecking] = useState(true);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    if (pathname === "/admin/login") { setChecking(false); return; }
    adminApi.canAccess().then((r) => {
      if (r.access) { setAuthed(true); setChecking(false); }
      else router.replace("/admin/login");
    }).catch(() => router.replace("/admin/login"));
  }, [pathname, router]);

  if (pathname === "/admin/login") return <>{children}</>;
  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0e1a]">
        <div className="text-slate-400 text-sm animate-pulse">Verifying admin session…</div>
      </div>
    );
  }
  if (!authed) return null;

  return (
    <div className="flex min-h-screen bg-[#f0f2f5]">
      {/* Sidebar */}
      <aside className="w-60 min-h-screen bg-[#0a0e1a] flex flex-col shrink-0 border-r border-white/5">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-white/10 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shrink-0">
            <Shield size={15} className="text-white" />
          </div>
          <div>
            <p className="text-white font-semibold text-sm leading-tight">Zilo Admin</p>
            <p className="text-slate-500 text-[10px]">Platform management</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  active
                    ? "bg-indigo-600/20 text-indigo-400"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
                )}
              >
                <Icon size={15} />
                <span className="flex-1">{label}</span>
                {active && <ChevronRight size={12} className="text-indigo-400" />}
              </Link>
            );
          })}
        </nav>

        {/* Logout */}
        <div className="px-3 pb-5 border-t border-white/10 pt-3">
          <button
            onClick={() => { adminApi.logout(); router.replace("/admin/login"); }}
            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm font-medium text-slate-400 hover:bg-white/5 hover:text-red-400 transition-colors"
          >
            <LogOut size={15} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-h-screen overflow-auto">
        {/* Top bar */}
        <header className="h-14 bg-white border-b border-slate-200 flex items-center px-6 gap-3 shrink-0">
          <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
            {NAV.find((n) => (n.exact ? pathname === n.href : pathname.startsWith(n.href)))?.label ?? "Admin"}
          </span>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}

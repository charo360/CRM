"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  ShoppingCart,
  Users,
  CreditCard,
  Radio,
  Upload,
  Store,
  Monitor,
  LogOut,
  Zap,
  Bell,
  TrendingUp,
  Calendar,
  BarChart2,
  Megaphone,
  MessageSquare,
} from "lucide-react";
import { clearToken } from "@/lib/auth";
import { useRouter } from "next/navigation";

const NAV_GROUPS = [
  {
    label: "Main",
    items: [
      { href: "/dashboard", label: "Overview", icon: LayoutDashboard, exact: true },
      { href: "/dashboard/messages", label: "Messages", icon: MessageSquare },
      { href: "/dashboard/customers", label: "Customers", icon: Users },
      { href: "/dashboard/followups", label: "Follow-ups", icon: Bell },
    ],
  },
  {
    label: "Sales",
    items: [
      { href: "/dashboard/sales", label: "Sales", icon: TrendingUp },
      { href: "/dashboard/orders", label: "Orders", icon: ShoppingCart },
      { href: "/dashboard/bookings", label: "Bookings", icon: Calendar },
      { href: "/dashboard/payments", label: "Payments", icon: CreditCard },
    ],
  },
  {
    label: "Marketing",
    items: [
      { href: "/dashboard/broadcast", label: "Broadcast", icon: Megaphone },
    ],
  },
  {
    label: "Business",
    items: [
      { href: "/dashboard/analytics", label: "Analytics", icon: BarChart2 },
      { href: "/dashboard/channels", label: "Channels", icon: Radio },
      { href: "/dashboard/shop", label: "Shop", icon: Store },
      { href: "/dashboard/imports", label: "Imports", icon: Upload },
    ],
  },
  {
    label: "Display",
    items: [
      { href: "/kds", label: "KDS Display", icon: Monitor },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  function isActive(href: string, exact?: boolean) {
    if (exact) return pathname === href;
    return pathname.startsWith(href);
  }

  return (
    <aside className="flex flex-col w-56 min-h-screen bg-slate-900 text-slate-100 shrink-0 overflow-y-auto">
      {/* Logo */}
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-800">
        <div className="w-7 h-7 rounded-lg bg-indigo-500 flex items-center justify-center shrink-0">
          <Zap size={14} className="text-white" />
        </div>
        <span className="font-semibold text-sm tracking-tight">Zilo CRM</span>
      </div>

      {/* Nav groups */}
      <nav className="flex-1 px-3 py-3 space-y-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 px-3 mb-1">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map(({ href, label, icon: Icon, exact }) => (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                    isActive(href, exact)
                      ? "bg-indigo-600 text-white"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  )}
                >
                  <Icon size={15} />
                  {label}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Logout */}
      <div className="px-3 pb-4 border-t border-slate-800 pt-3">
        <button
          onClick={handleLogout}
          className="flex items-center gap-2.5 px-3 py-2 w-full rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
        >
          <LogOut size={15} />
          Log out
        </button>
      </div>
    </aside>
  );
}

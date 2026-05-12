"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { ZiloLogo } from "@/components/ZiloLogo";
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
  Bell,
  TrendingUp,
  Calendar,
  BarChart2,
  Megaphone,
  MessageSquare,
  Settings,
  UserCheck,
  Truck,
  Plug,
  Sparkles,
  Workflow,
  Layers,
  CalendarClock,
  Target,
  LineChart,
  FileText,
  Package,
  PieChart,
  ClipboardList,
  Star,
  MessageCircle,
  Inbox,
  Mail,
  CalendarDays,
  ShoppingBag,
  Hash,
  MapPinned,
  Search,
  FolderKanban,
  Image,
  Zap,
  FileInput,
  Globe,
  Globe2,
} from "lucide-react";
import { clearToken } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { useBusiness } from "@/contexts/BusinessContext";
import { isSidebarHrefEnabled } from "@/lib/sidebarFeatures";

/** Always visible for every account — channels & connections included for everyone. */
function coreNavItems(overviewLabel: string) {
  return [
    { href: "/dashboard", label: overviewLabel, icon: LayoutDashboard, exact: true as const },
    { href: "/dashboard/assistant", label: "Zilo Chat", icon: Sparkles },
    { href: "/dashboard/field-agents", label: "Field Agents", icon: Globe },
    { href: "/dashboard/workflows", label: "Automations", icon: Workflow },
    { href: "/dashboard/integrations", label: "Integrations", icon: Plug },
    { href: "/dashboard/features", label: "Features", icon: Layers },
    { href: "/dashboard/settings", label: "Settings", icon: Settings },
  ] as const;
}

const MAIN_NAV = [
  { href: "/dashboard/messages", label: "Messages", icon: MessageSquare },
  { href: "/dashboard/customers", label: "Customers", icon: Users },
  { href: "/dashboard/contacts", label: "Contacts", icon: UserCheck },
  { href: "/dashboard/suppliers", label: "Suppliers", icon: Truck },
  { href: "/dashboard/followups", label: "Follow-ups", icon: Bell },
] as const;

const BUSINESS_NAV_BASE = [
  { href: "/dashboard/analytics", label: "Analytics", icon: BarChart2 },
  { href: "/dashboard/team-analytics", label: "Team Analytics", icon: Radio },
  { href: "/dashboard/whatsapp", label: "WhatsApp", icon: MessageSquare },
  { href: "/dashboard/team", label: "Team", icon: Users },
  { href: "/dashboard/collaboration", label: "Collaboration", icon: FolderKanban },
  { href: "/dashboard/shop", label: "Shop", icon: Store },
  { href: "/dashboard/imports", label: "Imports", icon: Upload },
] as const;

const DISPLAY_NAV = [{ href: "/dashboard/kds", label: "KDS Display", icon: Monitor }] as const;

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { showBookingsNav, bookingsNavLabel, bookingsNavHref, ui, sidebarFeatures } = useBusiness();
  const workspaceNav = coreNavItems(ui.overviewTitle);

  const mainNav = MAIN_NAV.map((item) =>
    item.href === "/dashboard/customers" ? { ...item, label: ui.customersNavLabel } : item
  );

  const businessNav = BUSINESS_NAV_BASE.map((item) =>
    item.href === "/dashboard/shop" ? { ...item, label: ui.shopNavLabel } : item
  );

  const salesNav = [
    { href: "/dashboard/sales", label: ui.salesNavLabel, icon: TrendingUp },
    { href: "/dashboard/orders", label: "Orders", icon: ShoppingCart },
    ...(showBookingsNav
      ? [{ href: bookingsNavHref, label: bookingsNavLabel, icon: Calendar }]
      : []),
    { href: "/dashboard/payments", label: "Payments", icon: CreditCard },
    { href: "/dashboard/invoices", label: "Invoices", icon: FileText },
    { href: "/dashboard/quotes", label: "Quotes", icon: ClipboardList },
    { href: "/dashboard/finance", label: "Finance / P&L", icon: PieChart },
  ].filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const mainNavFiltered = mainNav.filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const salesAndGrowthNav = [
    { href: "/dashboard/broadcast", label: "Broadcast", icon: Megaphone },
    { href: "/dashboard/social-scheduler", label: "Social scheduler", icon: CalendarClock },
    { href: "/dashboard/meta-ads", label: "Meta Ads", icon: Target },
    { href: "/dashboard/google-ads", label: "Google Ads", icon: LineChart },
    { href: "/dashboard/x-ads", label: "X Ads", icon: Hash },
    { href: "/dashboard/google-business", label: "Google Business", icon: MapPinned },
    { href: "/dashboard/social-inbox", label: "Social Inbox", icon: Inbox },
    { href: "/dashboard/seo", label: "Website & SEO", icon: Search },
  ].filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const businessNavFiltered = [
    ...businessNav,
    { href: "/dashboard/inventory", label: "Inventory", icon: Package },
    { href: "/dashboard/loyalty", label: "Loyalty", icon: Star },
    { href: "/dashboard/nps", label: "Feedback / NPS", icon: MessageCircle },
  ].filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const displayNavFiltered = DISPLAY_NAV.filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const productivityNav = [
    { href: "/dashboard/email", label: "Email", icon: Mail },
    { href: "/dashboard/calendar", label: "Calendar", icon: CalendarDays },
    { href: "/dashboard/shopify", label: "Shopify", icon: ShoppingBag },
    { href: "/dashboard/design-templates", label: "Design Library", icon: Image },
    { href: "/dashboard/documents", label: "Documents", icon: FileText },
    { href: "/dashboard/forms", label: "Forms", icon: FileInput },
    { href: "/dashboard/growth", label: "Growth Suite", icon: Zap },
    { href: "/dashboard/client-portal", label: "Client Portal", icon: Users },
    { href: "/dashboard/client-sites", label: "Client Sites", icon: Globe2 },
  ].filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const NAV_GROUPS = [
    { label: "Workspace", items: [...workspaceNav] },
    ...(mainNavFiltered.length
      ? [{ label: "Main", items: mainNavFiltered }]
      : []),
    ...(salesNav.length ? [{ label: "Sales", items: salesNav }] : []),
    ...(salesAndGrowthNav.length ? [{ label: "Sales & growth", items: salesAndGrowthNav }] : []),
    ...(businessNavFiltered.length ? [{ label: "Business", items: businessNavFiltered }] : []),
    ...(productivityNav.length ? [{ label: "Productivity", items: productivityNav }] : []),
    ...(ui.showKdsNav && displayNavFiltered.length
      ? [{ label: "Display", items: displayNavFiltered }]
      : []),
  ];

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  const bookingsSectionActive =
    pathname === "/dashboard/bookings" || pathname === "/dashboard/reservations";

  function linkActive(href: string, exact?: boolean) {
    if (href === "/dashboard/bookings" || href === "/dashboard/reservations") {
      return bookingsSectionActive;
    }
    if (exact) return pathname === href;
    return pathname.startsWith(href);
  }

  return (
    <aside className="flex flex-col w-56 min-h-screen bg-[#071a10] text-slate-100 shrink-0 border-r border-brand-dark/25">
      {/* Logo - Sticky Header */}
      <div className="sticky top-0 z-10 flex items-center gap-1 px-5 py-4 border-b border-white/10 bg-[#071a10]">
        <ZiloLogo size={28} className="shrink-0" />
        <span className="font-semibold text-sm tracking-tight">Zilo</span>
      </div>

      {/* Nav groups - Scrollable */}
      <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-light/35 px-3 mb-1">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item: { href: string; label: string; icon: React.ElementType; exact?: boolean }) => {
                const { href, label, icon: Icon } = item;
                const exact = "exact" in item ? item.exact : undefined;
                return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                    linkActive(href, exact)
                      ? "bg-brand text-brand-ink shadow-sm shadow-brand/20"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
                  )}
                >
                  <Icon size={15} />
                  {label}
                </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer - Sticky */}
      <div className="sticky bottom-0 z-10 bg-[#071a10] border-t border-white/10 pt-3 pb-4 px-3 space-y-2">
        {/* ⌘K hint */}
        <button
          type="button"
          onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, ctrlKey: true, bubbles: true }))}
          className="flex w-full items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-slate-400 transition hover:bg-white/10 hover:text-slate-200"
        >
          <Search size={12} className="shrink-0" />
          <span className="flex-1">Ask Zilo anything…</span>
          <kbd className="rounded border border-white/20 bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">⌘K</kbd>
        </button>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="flex items-center gap-2.5 px-3 py-2 w-full rounded-lg text-sm font-medium text-slate-400 hover:bg-white/5 hover:text-slate-100 transition-colors"
        >
          <LogOut size={15} />
          Log out
        </button>
      </div>
    </aside>
  );
}

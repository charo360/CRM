"use client";

import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ZiloLogo } from "@/components/ZiloLogo";
import {
  X,
  Sun,
  BookOpen,
  ListChecks,
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
  Activity,
  Radar,
  Crosshair,
  Smartphone,
  NotebookPen,
  Landmark,
  Handshake,
  Scale,
  Wallet,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { clearToken } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { useBusiness } from "@/contexts/BusinessContext";
import { isSidebarHrefEnabled } from "@/lib/sidebarFeatures";

const ZILO_NAV = [
  { href: "/dashboard", label: "Zilo Briefing", icon: Sun, exact: true as const },
  { href: "/dashboard/assistant", label: "Zilo Chat", icon: Sparkles },
  { href: "/dashboard/rex/decisions", label: "Decision Room", icon: Scale },
  { href: "/dashboard/rex/journal", label: "Journal", icon: BookOpen },
  { href: "/dashboard/rex/notebook", label: "Notebook", icon: NotebookPen },
] as const;

/** Rarely-used Zilo utility links — shown near logout, not in main nav */
const ZILO_UTILITY_NAV = [
  { href: "/dashboard/rex/ledger", label: "Action Log", icon: ListChecks },
  { href: "/dashboard/rex/team", label: "Zilo's team", icon: Users },
] as const;

/** Workspace links (Overview replaced by Zilo Briefing above). */
function coreNavItems() {
  return [
    { href: "/dashboard/delegate", label: "Delegate", icon: Workflow },
    { href: "/dashboard/workplan", label: "Work Plan", icon: ClipboardList },
    { href: "/dashboard/integrations", label: "Integrations", icon: Plug },
    { href: "/dashboard/features", label: "Features", icon: Layers },
    { href: "/dashboard/billing", label: "Billing", icon: CreditCard },
    { href: "/dashboard/manage-payment", label: "Manage payment", icon: Wallet },
    { href: "/dashboard/settings", label: "Settings", icon: Settings },
  ] as const;
}

const MAIN_NAV = [
  { href: "/dashboard/messages", label: "Messages", icon: MessageSquare },
  { href: "/dashboard/customers", label: "Customers", icon: Users },
  { href: "/dashboard/contacts", label: "Contacts", icon: UserCheck },
  { href: "/dashboard/suppliers", label: "Suppliers", icon: Truck },
  { href: "/dashboard/investors", label: "Investors", icon: Landmark },
  { href: "/dashboard/partners", label: "Partners", icon: Handshake },
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


const SIDEBAR_COLLAPSED_STORAGE_KEY = "zilo-sidebar-collapsed";

function CollapsedHoverLabel({
  label,
  target,
  show,
}: {
  label: string;
  target: HTMLElement | null;
  show: boolean;
}) {
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!show || !target) return;
    const update = () => {
      const r = target.getBoundingClientRect();
      setPos({ top: r.top + r.height / 2, left: r.right + 10 });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [show, target, label]);

  if (!show || typeof document === "undefined") return null;

  return createPortal(
    <div
      role="tooltip"
      className="fixed z-[200] -translate-y-1/2 pointer-events-none whitespace-nowrap rounded-md border border-white/15 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white shadow-lg"
      style={{ top: pos.top, left: pos.left }}
    >
      {label}
    </div>,
    document.body
  );
}

type SidebarNavLinkProps = {
  href: string;
  label: string;
  icon: React.ElementType;
  active: boolean;
  collapsed: boolean;
  badge?: number;
  compact?: boolean;
};

function SidebarNavLink({ href, label, icon: Icon, active, collapsed, badge = 0, compact }: SidebarNavLinkProps) {
  const [hoverTarget, setHoverTarget] = useState<HTMLElement | null>(null);
  const iconSize = compact ? 13 : 15;

  return (
    <>
      <Link
        href={href}
        onMouseEnter={(e) => collapsed && setHoverTarget(e.currentTarget)}
        onMouseLeave={() => setHoverTarget(null)}
        onFocus={(e) => collapsed && setHoverTarget(e.currentTarget)}
        onBlur={() => setHoverTarget(null)}
        className={cn(
          "relative flex items-center rounded-lg font-medium transition-colors",
          compact ? "gap-2.5 px-3 py-1.5 text-xs" : "gap-2.5 px-3 py-2 text-sm",
          collapsed && "justify-center px-2",
          active
            ? compact
              ? "bg-brand/20 text-brand-light"
              : "bg-brand text-brand-ink shadow-sm shadow-brand/20"
            : compact
              ? "text-slate-500 hover:bg-white/5 hover:text-slate-300"
              : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
        )}
      >
        <Icon size={iconSize} className="shrink-0" />
        {!collapsed && <span className="flex-1">{label}</span>}
        {badge > 0 && (
          <span
            className={cn(
              "rounded-full bg-amber-400 font-bold text-brand-ink",
              collapsed
                ? "absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center px-1 text-[9px]"
                : "px-1.5 py-0.5 text-[10px]"
            )}
          >
            {badge}
          </span>
        )}
      </Link>
      <CollapsedHoverLabel label={label} target={hoverTarget} show={collapsed && hoverTarget !== null} />
    </>
  );
}


function SidebarIconButton({
  label,
  collapsed,
  onClick,
  children,
  className,
}: {
  label: string;
  collapsed: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  const [hoverTarget, setHoverTarget] = useState<HTMLElement | null>(null);

  return (
    <>
      <button
        type="button"
        onClick={onClick}
        onMouseEnter={(e) => collapsed && setHoverTarget(e.currentTarget)}
        onMouseLeave={() => setHoverTarget(null)}
        onFocus={(e) => collapsed && setHoverTarget(e.currentTarget)}
        onBlur={() => setHoverTarget(null)}
        className={className}
      >
        {children}
      </button>
      <CollapsedHoverLabel label={label} target={hoverTarget} show={collapsed && hoverTarget !== null} />
    </>
  );
}

type SidebarProps = {
  mobileOpen?: boolean;
  onMobileClose?: () => void;
};

export default function Sidebar({ mobileOpen = false, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [ziloStagedCount, setZiloStagedCount] = useState(0);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
      if (stored === "1") setCollapsed(true);
    } catch {
      /* ignore */
    }
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }
  const { showBookingsNav, bookingsNavLabel, bookingsNavHref, ui, sidebarFeatures } = useBusiness();
  const workspaceNav = coreNavItems();

  useEffect(() => {
    api.get<{ counts?: { staged?: number } }>("/rex/home?background=false")
      .then((d) => setZiloStagedCount(d.counts?.staged ?? 0))
      .catch(() => setZiloStagedCount(0));
  }, [pathname]);

  useEffect(() => {
    function handleCountChange(e: Event) {
      const customEvent = e as CustomEvent<number>;
      setZiloStagedCount(customEvent.detail ?? 0);
    }
    window.addEventListener("zilo-staged-count-change", handleCountChange);
    return () => window.removeEventListener("zilo-staged-count-change", handleCountChange);
  }, []);

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
    { href: "/dashboard/action-mode", label: "AI Scout", icon: Crosshair },
    { href: "/dashboard/broadcast", label: "Broadcast", icon: Megaphone },
    { href: "/dashboard/sms-marketing", label: "SMS Marketing", icon: Smartphone },
    { href: "/dashboard/social-scheduler", label: "Social scheduler", icon: CalendarClock },
    { href: "/dashboard/meta-ads", label: "Meta Ads", icon: Target },
    { href: "/dashboard/google-ads", label: "Google Ads", icon: LineChart },
    { href: "/dashboard/x-ads", label: "X Ads", icon: Hash },
    { href: "/dashboard/google-business", label: "Google Business", icon: MapPinned },
    { href: "/dashboard/social-inbox", label: "Social Inbox", icon: Inbox },
    { href: "/dashboard/seo", label: "SEOhub", icon: Search },
    { href: "/dashboard/marketing/behavior-discounts", label: "Behavior Tracker", icon: Activity },
  ].filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const businessNavFiltered = [
    ...businessNav,
    { href: "/dashboard/field-agents", label: "Field Agents", icon: Globe },
    { href: "/dashboard/smart-notes", label: "Zilo Notetaker", icon: NotebookPen },
    { href: "/dashboard/inventory", label: "Inventory", icon: Package },
    { href: "/dashboard/loyalty", label: "Loyalty", icon: Star },
    { href: "/dashboard/nps", label: "Feedback / NPS", icon: MessageCircle },
  ].filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const displayNavFiltered = DISPLAY_NAV.filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const productivityNav = [
    { href: "/dashboard/email", label: "Email", icon: Mail },
    { href: "/dashboard/email-marketing", label: "Email Marketing", icon: Megaphone },
    { href: "/dashboard/calendar", label: "Calendar", icon: CalendarDays },
    { href: "/dashboard/shopify", label: "Shopify", icon: ShoppingBag },
    { href: "/dashboard/smart-discovery", label: "Smart Discovery", icon: Radar },
    { href: "/dashboard/design-templates", label: "Design Library", icon: Image },
    { href: "/dashboard/documents", label: "Documents", icon: FileText },
    { href: "/dashboard/forms", label: "Forms", icon: FileInput },
    { href: "/dashboard/growth", label: "Growth Suite", icon: Zap },
    { href: "/dashboard/client-portal", label: "Client Portal", icon: Users },
    { href: "/dashboard/client-sites", label: "Client Sites", icon: Globe2 },
    { href: "/dashboard/store", label: "My Store", icon: ShoppingCart },
  ].filter((item) => isSidebarHrefEnabled(item.href, sidebarFeatures));

  const NAV_GROUPS = [
    { label: "Zilo", items: [...ZILO_NAV] },
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

  const desktopCollapsed = collapsed && !mobileOpen;

  const asideClassName = cn(
    "flex flex-col min-h-screen bg-[#071a10] text-slate-100 shrink-0 border-r border-brand-dark/25 transition-[width] duration-200 ease-out",
    desktopCollapsed ? "w-[4.25rem]" : "w-56"
  );

  const navContent = (
    <>
      {/* Logo - Sticky Header */}
      <div
        className={cn(
          "sticky top-0 z-10 flex items-center border-b border-white/10 bg-[#071a10] py-4",
          desktopCollapsed ? "justify-between gap-1 px-2" : "justify-between gap-1 px-4"
        )}
      >
        <div className={cn("flex min-w-0 items-center", "gap-1.5")}>
          <ZiloLogo size={28} className="shrink-0" />
          {!desktopCollapsed && <span className="text-sm font-semibold tracking-tight">Zilo</span>}
        </div>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={toggleCollapsed}
            className="hidden rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-slate-100 lg:inline-flex"
            aria-label={desktopCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={desktopCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {desktopCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
          {onMobileClose && (
            <button
              type="button"
              onClick={onMobileClose}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-slate-100 lg:hidden"
              aria-label="Close menu"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {ziloStagedCount > 0 && !desktopCollapsed && (
        <div className="mx-3 mt-3 rounded-lg border border-brand/20 bg-brand/10 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-brand-light/70">Zilo</p>
          <p className="mt-1 text-xs leading-snug text-slate-200">
            <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-amber-400 align-middle" />
            {ziloStagedCount} item{ziloStagedCount === 1 ? "" : "s"} in briefing
          </p>
        </div>
      )}

      {/* Nav groups - Scrollable */}
      <nav className={cn("flex-1 space-y-4 overflow-y-auto py-3", desktopCollapsed ? "px-1.5" : "px-3")}>
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            {!desktopCollapsed && (
              <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-brand-light/35">
                {group.label}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item: { href: string; label: string; icon: React.ElementType; exact?: boolean }) => {
                const { href, label, icon: Icon } = item;
                const exact = "exact" in item ? item.exact : undefined;
                const badge = group.label === "Zilo" && href === "/dashboard" ? ziloStagedCount : 0;
                return (
                  <SidebarNavLink
                    key={href}
                    href={href}
                    label={label}
                    icon={Icon}
                    active={linkActive(href, exact)}
                    collapsed={desktopCollapsed}
                    badge={badge}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer - Sticky */}
      <div
        className={cn(
          "sticky bottom-0 z-10 space-y-2 border-t border-white/10 bg-[#071a10] pb-4 pt-3",
          desktopCollapsed ? "px-2" : "px-3"
        )}
      >
        <SidebarIconButton
          label="Ask Zilo anything…"
          collapsed={desktopCollapsed}
          onClick={() =>
            window.dispatchEvent(
              new KeyboardEvent("keydown", { key: "k", metaKey: true, ctrlKey: true, bubbles: true })
            )
          }
          className={cn(
            "flex w-full items-center rounded-lg border border-white/10 bg-white/5 text-left text-xs text-slate-400 transition hover:bg-white/10 hover:text-slate-200",
            desktopCollapsed ? "justify-center px-2 py-2.5" : "gap-2 px-3 py-2"
          )}
        >
          <Search size={12} className="shrink-0" />
          {!desktopCollapsed && <span className="flex-1">Ask Zilo anything…</span>}
          {!desktopCollapsed && (
            <kbd className="rounded border border-white/20 bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">⌘K</kbd>
          )}
        </SidebarIconButton>

        <div className="space-y-0.5 border-t border-white/10 pt-2">
          {ZILO_UTILITY_NAV.map(({ href, label, icon: Icon }) => (
            <SidebarNavLink
              key={href}
              href={href}
              label={label}
              icon={Icon}
              active={linkActive(href)}
              collapsed={desktopCollapsed}
              compact
            />
          ))}
        </div>

        <SidebarIconButton
          label="Log out"
          collapsed={desktopCollapsed}
          onClick={handleLogout}
          className={cn(
            "flex w-full items-center rounded-lg text-sm font-medium text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-100",
            desktopCollapsed ? "justify-center px-2 py-2" : "gap-2.5 px-3 py-2"
          )}
        >
          <LogOut size={15} className="shrink-0" />
          {!desktopCollapsed && "Log out"}
        </SidebarIconButton>
      </div>
    </>
  );

  return (
    <>
      <aside className={cn(asideClassName, "hidden lg:flex")}>{navContent}</aside>
      <aside
        className={cn(
          asideClassName,
          "fixed inset-y-0 left-0 z-50 h-[100dvh] w-[min(18rem,85vw)] transform transition-transform duration-200 ease-out lg:hidden",
          mobileOpen ? "translate-x-0" : "-translate-x-full pointer-events-none"
        )}
        aria-hidden={!mobileOpen}
      >
        {navContent}
      </aside>
    </>
  );
}

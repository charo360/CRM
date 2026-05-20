"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  ShoppingBag, TrendingUp, Users, Package, RefreshCw, Loader2,
  ShoppingCart, Tag, ChevronDown, ChevronRight, Check, X,
  AlertTriangle, Copy, Plus, Trash2, Sparkles, ArrowUpRight,
  BarChart3, Clock, MapPin, Mail, Search, Filter, Zap,
  CheckCircle2, XCircle, Circle, RotateCcw, ExternalLink,
  DollarSign, Percent, Calendar, Eye, TrendingDown, Star,
  Wand2,
} from "lucide-react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { ShopifyOrder, ShopifyProduct, ShopifyCustomer, ShopifyCheckout, ShopifyPriceRule, ShopifyLocation } from "@/app/api/shopify/route";
import GrowthTab from "./_growth-tab";

// ── Types ─────────────────────────────────────────────────────────────────────

type Tab = "overview" | "orders" | "products" | "customers" | "abandoned" | "discounts" | "growth";
type Period = "today" | "week" | "month";

type OverviewData = {
  connected: boolean;
  period: Period;
  stats: {
    revenue: number; orderCount: number; aov: number;
    fulfilled: number; unfulfilled: number; pending: number; refunds: number;
    productCount: number; customerCount: number; fulfillmentRate: number;
  };
  revenueByDay: { date: string; amount: number }[];
  topProducts: { title: string; revenue: number; units: number }[];
  recentOrders: ShopifyOrder[];
};

// ── API helpers ───────────────────────────────────────────────────────────────

function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {} as Record<string, string>;
}
async function shopGet(params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`/api/shopify?${qs}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function shopPost(body: unknown) {
  const res = await fetch("/api/shopify", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function aiDraft(prompt: string): Promise<string> {
  const BACKEND = process.env.NEXT_PUBLIC_API_URL || "/api";
  const t = getToken();
  try {
    const res = await fetch(`${BACKEND}/assistant/ai-draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
      body: JSON.stringify({ prompt }),
    });
    if (!res.ok) return "";
    const d = await res.json() as { reply?: string; draft?: string; text?: string };
    return d.reply ?? d.draft ?? d.text ?? "";
  } catch { return ""; }
}

// ── Formatting ────────────────────────────────────────────────────────────────

function fmtMoney(n: number | string, currency = "USD") {
  const num = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(num)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(num);
}
function fmtDate(iso: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "2-digit" });
}
function fmtDateTime(iso: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(() => toast.success("Copied!"));
}

// ── Status badges ─────────────────────────────────────────────────────────────

function FinancialBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    paid: "bg-emerald-50 text-emerald-600 border-emerald-200",
    pending: "bg-amber-50 text-amber-600 border-amber-200",
    refunded: "bg-rose-50 text-rose-600 border-rose-200",
    partially_refunded: "bg-orange-50 text-orange-600 border-orange-200",
    voided: "bg-slate-100 text-slate-500 border-slate-200",
    authorized: "bg-blue-50 text-blue-600 border-blue-200",
  };
  return (
    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border capitalize", map[status] ?? "bg-slate-100 text-slate-400 border-slate-200")}>
      {status?.replace(/_/g, " ")}
    </span>
  );
}

function FulfillmentBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-amber-50 text-amber-600 border-amber-200">Unfulfilled</span>;
  if (status === "fulfilled") return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-emerald-50 text-emerald-600 border-emerald-200">Fulfilled</span>;
  if (status === "partial") return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-blue-50 text-blue-600 border-blue-200">Partial</span>;
  return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-slate-100 text-slate-400 border-slate-200 capitalize">{status}</span>;
}

function StockBadge({ qty }: { qty: number }) {
  if (qty <= 0) return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-50 text-rose-600 border border-rose-200">Out of stock</span>;
  if (qty < 5) return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-50 text-rose-600 border border-rose-200">Critical: {qty}</span>;
  if (qty < 20) return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 border border-amber-200">Low: {qty}</span>;
  return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-200">{qty} in stock</span>;
}

// ── No connection ─────────────────────────────────────────────────────────────

function NoShopify({
  shop, setShop, onOAuth,
  connecting,
}: {
  shop: string; setShop: (v: string) => void;
  onOAuth: () => void;
  connecting: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 text-center px-8 py-16">
      <div className="w-16 h-16 rounded-2xl bg-brand/10 border border-brand/20 flex items-center justify-center">
        <ShoppingBag size={28} className="text-brand" />
      </div>
      <div>
        <p className="font-bold text-slate-800 text-base">Connect your Shopify store</p>
        <p className="text-sm text-slate-500 mt-1.5 max-w-xs leading-relaxed">
          Enter your store name and click Connect — you’ll be taken to Shopify to approve access.
        </p>
      </div>

      {/* OAuth form */}
      <div className="w-full max-w-sm space-y-3 text-left">
        <div>
          <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5 block">Store name</label>
          <div className="flex items-center bg-slate-100 border border-slate-200 rounded-xl overflow-hidden focus-within:ring-1 focus-within:ring-brand transition-all">
            <input
              value={shop}
              onChange={(e) => setShop(e.target.value.replace(/\.myshopify\.com.*/, ""))}
              onKeyDown={(e) => e.key === "Enter" && !connecting && shop.trim() && onOAuth()}
              placeholder="yourstore"
              className="flex-1 bg-transparent px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-500 outline-none"
              disabled={connecting}
            />
            <span className="px-3 text-slate-500 text-sm select-none">.myshopify.com</span>
          </div>
        </div>
        <button
          onClick={onOAuth}
          disabled={connecting || !shop.trim()}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-brand hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
        >
          {connecting ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
          {connecting ? "Connecting…" : "Connect with Shopify"}
        </button>

      </div>
      <div className="grid grid-cols-2 gap-3 text-left mt-2 max-w-sm">
        {[
          ["📦", "Order management", "Fulfill, cancel, track every order"],
          ["📉", "Abandoned cart recovery", "AI-written recovery emails"],
          ["🏷️", "Discount codes", "Create promos with one click"],
          ["📊", "Revenue analytics", "Daily charts, top products, AOV"],
          ["🔔", "Low stock alerts", "Never run out unexpectedly"],
          ["👥", "Customer LTV", "Know your best customers"],
        ].map(([icon, title, desc]) => (
          <div key={title} className="bg-slate-100 rounded-xl p-3 border border-slate-100">
            <p className="text-sm mb-1">{icon} <span className="font-medium text-slate-800">{title}</span></p>
            <p className="text-[11px] text-slate-500">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Revenue chart (pure CSS) ──────────────────────────────────────────────────

function RevenueChart({ data }: { data: { date: string; amount: number }[] }) {
  if (!data.length) return <div className="h-24 flex items-center justify-center text-slate-600 text-xs">No data</div>;
  const max = Math.max(...data.map((d) => d.amount), 1);
  return (
    <div className="flex items-end gap-1 h-24 w-full">
      {data.map((d) => {
        const pct = Math.max((d.amount / max) * 100, 2);
        return (
          <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group" title={`${d.date}: ${fmtMoney(d.amount)}`}>
            <div className="w-full bg-brand rounded-sm hover:bg-brand transition-colors" style={{ height: `${pct}%` }} />
            <span className="text-[8px] text-slate-700 group-hover:text-slate-500 transition-colors hidden md:block">
              {new Date(d.date + "T00:00:00").getDate()}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, sub, color = "text-brand" }: {
  icon: React.ElementType; label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">{label}</span>
        <Icon size={14} className={color} />
      </div>
      <p className="text-xl font-bold text-slate-900">{value}</p>
      {sub && <p className="text-[11px] text-slate-600">{sub}</p>}
    </div>
  );
}

// ── Overview tab ──────────────────────────────────────────────────────────────

function OverviewTab({ period, setPeriod }: { period: Period; setPeriod: (p: Period) => void }) {
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await shopGet({ action: "overview", period });
      setData(d as OverviewData);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setLoading(false); }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex-1 flex items-center justify-center"><Loader2 size={24} className="animate-spin text-slate-600" /></div>;
  if (!data?.stats) return null;
  const { stats, revenueByDay, topProducts, recentOrders } = data;

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      {/* Period selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">Period:</span>
        {(["today", "week", "month"] as Period[]).map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={cn("text-xs px-3 py-1.5 rounded-lg capitalize font-medium transition-colors", period === p ? "bg-brand-dark text-white" : "bg-slate-100 text-slate-400 hover:bg-slate-200")}
          >
            {p === "today" ? "Today" : p === "week" ? "7 days" : "This month"}
          </button>
        ))}
        <button onClick={load} className="ml-auto p-1.5 text-slate-500 hover:text-slate-700 transition-colors"><RefreshCw size={13} /></button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon={DollarSign} label="Revenue" value={fmtMoney(stats.revenue)} sub={`${stats.orderCount} orders`} color="text-emerald-600" />
        <StatCard icon={ShoppingCart} label="Avg Order Value" value={fmtMoney(stats.aov)} sub="per order" color="text-brand" />
        <StatCard icon={CheckCircle2} label="Fulfillment Rate" value={`${stats.fulfillmentRate}%`} sub={`${stats.unfulfilled} pending`} color="text-blue-600" />
        <StatCard icon={TrendingDown} label="Refunds" value={String(stats.refunds)} sub={`${stats.pending} payment pending`} color="text-rose-600" />
      </div>

      {/* Secondary row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white border border-slate-200 rounded-2xl p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">Products</p>
          <p className="text-lg font-bold">{stats.productCount}</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">Customers</p>
          <p className="text-lg font-bold">{stats.customerCount.toLocaleString()}</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">Unfulfilled</p>
          <p className={cn("text-lg font-bold", stats.unfulfilled > 0 ? "text-amber-600" : "text-slate-700")}>{stats.unfulfilled}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Revenue chart */}
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-2xl p-4">
          <p className="text-xs font-semibold text-slate-400 mb-3 flex items-center gap-1.5"><BarChart3 size={12} /> Revenue by day</p>
          <RevenueChart data={revenueByDay} />
        </div>

        {/* Top products */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4">
          <p className="text-xs font-semibold text-slate-400 mb-3 flex items-center gap-1.5"><TrendingUp size={12} /> Top products</p>
          {topProducts.length === 0 ? (
            <p className="text-xs text-slate-600 py-4 text-center">No data</p>
          ) : (
            <div className="space-y-2.5">
              {topProducts.map((p, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-600 w-4">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-slate-700 truncate">{p.title}</p>
                    <p className="text-[10px] text-slate-600">{p.units} units</p>
                  </div>
                  <span className="text-xs font-semibold text-emerald-600">{fmtMoney(p.revenue)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent orders */}
      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
          <p className="text-xs font-semibold text-slate-400">Recent orders</p>
          <span className="text-[10px] text-slate-600">{recentOrders.length} shown</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200">
                {["Order", "Customer", "Items", "Total", "Payment", "Fulfillment", "Date"].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentOrders.map((o) => (
                <tr key={o.id} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-2.5 font-semibold text-brand">{o.name}</td>
                  <td className="px-4 py-2.5 text-slate-700">{o.customer ? `${o.customer.first_name} ${o.customer.last_name}` : o.email ?? "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500">{o.line_items?.length ?? 0}</td>
                  <td className="px-4 py-2.5 font-semibold text-slate-800">{fmtMoney(o.total_price, o.currency)}</td>
                  <td className="px-4 py-2.5"><FinancialBadge status={o.financial_status} /></td>
                  <td className="px-4 py-2.5"><FulfillmentBadge status={o.fulfillment_status} /></td>
                  <td className="px-4 py-2.5 text-slate-500">{timeAgo(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── Orders tab ────────────────────────────────────────────────────────────────

type CJOrderStatus = {
  found: boolean;
  cj_order_num?: string;
  status?: string;
  tracking_num?: string | null;
  carrier?: string | null;
};

const CJ_STATUS_LABELS: Record<string, string> = {
  created:          "Sent to CJ",
  IN_PRODUCTION:    "In Production",
  PICKED:           "Picked",
  PACKED:           "Packed",
  IN_TRANSIT:       "Shipped",
  DELIVERED:        "Delivered",
  synced_to_shopify:"Tracking Synced",
};

function OrdersTab() {
  const [orders, setOrders] = useState<ShopifyOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [fulfillmentFilter, setFulfillmentFilter] = useState("any");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [selected, setSelected] = useState<ShopifyOrder | null>(null);
  const [acting, setActing] = useState<string | null>(null);
  const [cjStatus, setCjStatus] = useState<CJOrderStatus | null>(null);
  const [cjFulfilling, setCjFulfilling] = useState(false);
  const [aeOrderStatus, setAeOrderStatus] = useState<CJOrderStatus | null>(null);
  const [aeFulfilling, setAeFulfilling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { action: "orders", status: "any", limit: "100" };
      if (fulfillmentFilter !== "any") params.fulfillment_status = fulfillmentFilter;
      if (search) params.search = search;
      const d = await shopGet(params) as { orders: ShopifyOrder[] };
      setOrders(d.orders ?? []);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setLoading(false); }
  }, [fulfillmentFilter, search]);

  useEffect(() => { load(); }, [load]);

  async function loadCjStatus(orderId: string) {
    setCjStatus(null);
    try {
      const token = getToken();
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
      const r = await fetch(`${apiBase}/cj/order-status/${orderId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) setCjStatus(await r.json() as CJOrderStatus);
    } catch { /* silent */ }
  }

  async function loadAeStatus(orderId: string) {
    setAeOrderStatus(null);
    try {
      const token = getToken();
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
      const r = await fetch(`${apiBase}/aliexpress/order-status/${orderId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) setAeOrderStatus(await r.json() as CJOrderStatus);
    } catch { /* silent */ }
  }

  async function fulfillViaAE(order: ShopifyOrder) {
    setAeFulfilling(true);
    try {
      const token = getToken();
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
      const r = await fetch(`${apiBase}/aliexpress/fulfill/${order.id}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await r.json() as { success?: boolean; ae_order_id?: string; detail?: string };
      if (!r.ok) throw new Error(data.detail || "AliExpress fulfillment failed");
      toast.success(`Order sent to AliExpress! Ref: ${data.ae_order_id}`);
      await loadAeStatus(String(order.id));
    } catch (e) { toast.error(e instanceof Error ? e.message : "AliExpress fulfillment failed"); }
    finally { setAeFulfilling(false); }
  }

  async function fulfillViaCJ(order: ShopifyOrder) {
    setCjFulfilling(true);
    try {
      const token = getToken();
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
      const r = await fetch(`${apiBase}/cj/fulfill/${order.id}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await r.json() as { success?: boolean; cj_order_num?: string; detail?: string };
      if (!r.ok) throw new Error(data.detail || "CJ fulfillment failed");
      toast.success(`Order sent to CJ! Ref: ${data.cj_order_num}`);
      await loadCjStatus(String(order.id));
    } catch (e) { toast.error(e instanceof Error ? e.message : "CJ fulfillment failed"); }
    finally { setCjFulfilling(false); }
  }

  async function fulfill(order: ShopifyOrder) {
    setActing(String(order.id));
    try {
      await shopPost({ action: "fulfill", orderId: String(order.id) });
      toast.success(`${order.name} fulfilled!`);
      await load();
      if (selected?.id === order.id) setSelected(null);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Fulfill failed"); }
    finally { setActing(null); }
  }

  async function cancel(order: ShopifyOrder) {
    if (!confirm(`Cancel ${order.name}? This will attempt a refund.`)) return;
    setActing(String(order.id));
    try {
      await shopPost({ action: "cancel", orderId: String(order.id) });
      toast.success(`${order.name} cancelled`);
      await load();
      if (selected?.id === order.id) setSelected(null);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Cancel failed"); }
    finally { setActing(null); }
  }

  const filterButtons = [
    { id: "any", label: "All" },
    { id: "unfulfilled", label: "Unfulfilled" },
    { id: "partial", label: "Partial" },
    { id: "fulfilled", label: "Fulfilled" },
  ];

  const unfulfilled = orders.filter((o) => !o.fulfillment_status).length;

  return (
    <div className="flex-1 flex overflow-hidden">
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2 flex-wrap">
          <form onSubmit={(e) => { e.preventDefault(); setSearch(searchInput); }} className="flex items-center gap-2 bg-slate-100 rounded-xl px-3 py-1.5 border border-slate-200">
            <Search size={12} className="text-slate-500" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Order # or customer…"
              className="bg-transparent text-xs text-slate-700 placeholder-slate-400 outline-none w-40"
            />
            {searchInput && <button type="button" onClick={() => { setSearchInput(""); setSearch(""); }}><X size={11} className="text-slate-500" /></button>}
          </form>
          <div className="flex items-center bg-slate-100 rounded-xl p-0.5 gap-0.5">
            {filterButtons.map((f) => (
              <button
                key={f.id}
                onClick={() => setFulfillmentFilter(f.id)}
                className={cn("text-xs px-3 py-1.5 rounded-lg font-medium transition-colors", fulfillmentFilter === f.id ? "bg-brand-dark text-white" : "text-slate-500 hover:text-slate-900")}
              >
                {f.label}
                {f.id === "unfulfilled" && unfulfilled > 0 && (
                  <span className="ml-1 text-[10px] bg-amber-500 text-white px-1 rounded-full">{unfulfilled}</span>
                )}
              </button>
            ))}
          </div>
          <button onClick={load} className="ml-auto p-1.5 text-slate-500 hover:text-slate-700 transition-colors"><RefreshCw size={13} /></button>
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex-1 flex items-center justify-center"><Loader2 size={22} className="animate-spin text-slate-600" /></div>
        ) : orders.length === 0 ? (
          <div className="flex-1 flex items-center justify-center flex-col gap-2 text-slate-600">
            <ShoppingCart size={28} />
            <p className="text-sm">No orders found</p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white border-b border-slate-200">
                <tr>
                  {["Order", "Customer", "Items", "Total", "Payment", "Fulfillment", "Date", "Actions"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr
                    key={o.id}
                    onClick={() => {
                      const next = selected?.id === o.id ? null : o;
                      setSelected(next);
                      if (next) { loadCjStatus(String(next.id)); loadAeStatus(String(next.id)); }
                      else { setCjStatus(null); setAeOrderStatus(null); }
                    }}
                    className={cn("border-b border-slate-100 hover:bg-slate-50 transition-colors cursor-pointer", selected?.id === o.id && "bg-slate-100")}
                  >
                    <td className="px-4 py-3 font-semibold text-brand">{o.name}</td>
                    <td className="px-4 py-3">
                      <p className="text-slate-800">{o.customer ? `${o.customer.first_name} ${o.customer.last_name}` : "—"}</p>
                      <p className="text-[10px] text-slate-600">{o.email ?? o.customer?.email ?? ""}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-400">{o.line_items?.length ?? 0} item{o.line_items?.length !== 1 ? "s" : ""}</td>
                    <td className="px-4 py-3 font-semibold text-slate-800">{fmtMoney(o.total_price, o.currency)}</td>
                    <td className="px-4 py-3"><FinancialBadge status={o.financial_status} /></td>
                    <td className="px-4 py-3"><FulfillmentBadge status={o.fulfillment_status} /></td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{fmtDate(o.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        {!o.fulfillment_status && o.financial_status === "paid" && (
                          <button
                            onClick={(e) => { e.stopPropagation(); fulfill(o); }}
                            disabled={acting === String(o.id)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-700/30 hover:bg-emerald-700/50 text-emerald-600 text-[10px] font-medium border border-emerald-700/40 disabled:opacity-50 transition-colors"
                          >
                            {acting === String(o.id) ? <Loader2 size={9} className="animate-spin" /> : <Check size={9} />}
                            Fulfill
                          </button>
                        )}
                        {o.financial_status !== "refunded" && o.financial_status !== "voided" && !o.fulfillment_status && (
                          <button
                            onClick={(e) => { e.stopPropagation(); cancel(o); }}
                            disabled={acting === String(o.id)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-50 hover:bg-rose-50 text-rose-600 text-[10px] font-medium border border-rose-200 disabled:opacity-50 transition-colors"
                          >
                            <X size={9} /> Cancel
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Order detail panel */}
      {selected && (
        <div className="w-80 border-l border-slate-200 bg-white flex flex-col overflow-y-auto shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
            <span className="font-semibold text-sm">{selected.name}</span>
            <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-slate-900"><X size={14} /></button>
          </div>
          <div className="px-4 py-4 space-y-4 flex-1 overflow-y-auto">
            {/* Status */}
            <div className="flex items-center gap-2 flex-wrap">
              <FinancialBadge status={selected.financial_status} />
              <FulfillmentBadge status={selected.fulfillment_status} />
            </div>
            {/* Customer */}
            <div>
              <p className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Customer</p>
              <p className="text-sm font-medium text-slate-800">{selected.customer ? `${selected.customer.first_name} ${selected.customer.last_name}` : "Guest"}</p>
              <p className="text-xs text-slate-500">{selected.email ?? selected.customer?.email}</p>
              {selected.customer?.orders_count && (
                <p className="text-[10px] text-slate-600 mt-0.5">{selected.customer.orders_count} orders · {fmtMoney(selected.customer.total_spent ?? "0")} lifetime</p>
              )}
            </div>
            {/* Line items */}
            <div>
              <p className="text-[10px] text-slate-500 mb-2 uppercase tracking-wider">Items</p>
              <div className="space-y-2">
                {selected.line_items?.map((li) => (
                  <div key={li.id} className="flex items-start gap-2 bg-slate-100 rounded-xl p-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-slate-800 font-medium truncate">{li.title}</p>
                      {li.variant_title && li.variant_title !== "Default Title" && (
                        <p className="text-[10px] text-slate-500">{li.variant_title}</p>
                      )}
                      {li.sku && <p className="text-[10px] text-slate-600">SKU: {li.sku}</p>}
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-xs font-semibold">{fmtMoney(li.price)}</p>
                      <p className="text-[10px] text-slate-500">×{li.quantity}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {/* Totals */}
            <div className="border-t border-slate-200 pt-3 space-y-1.5">
              {parseFloat(selected.total_discounts ?? "0") > 0 && (
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Discount</span>
                  <span className="text-rose-600">-{fmtMoney(selected.total_discounts, selected.currency)}</span>
                </div>
              )}
              <div className="flex justify-between text-sm font-bold">
                <span className="text-slate-700">Total</span>
                <span>{fmtMoney(selected.total_price, selected.currency)}</span>
              </div>
            </div>
            {/* Shipping */}
            {selected.shipping_address && (
              <div>
                <p className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Ship to</p>
                <p className="text-xs text-slate-700">{selected.shipping_address.first_name} {selected.shipping_address.last_name}</p>
                <p className="text-[11px] text-slate-500">{selected.shipping_address.address1}</p>
                <p className="text-[11px] text-slate-500">{selected.shipping_address.city}, {selected.shipping_address.country} {selected.shipping_address.zip}</p>
              </div>
            )}
            {/* Note */}
            {selected.note && (
              <div>
                <p className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Note</p>
                <p className="text-xs text-slate-400 bg-slate-100 rounded-xl p-2">{selected.note}</p>
              </div>
            )}
            <p className="text-[10px] text-slate-600">Placed {fmtDateTime(selected.created_at)}</p>

            {/* AliExpress Fulfillment Status */}
            {aeOrderStatus?.found && (
              <div className="border border-slate-200 rounded-xl p-3 space-y-1.5">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">AliExpress</p>
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
                    aeOrderStatus.status === "FINISH" || aeOrderStatus.status === "synced_to_shopify"
                      ? "bg-emerald-50 text-emerald-600 border-emerald-200"
                      : aeOrderStatus.status === "PLACE_ORDER_SUCCESS" || aeOrderStatus.status === "IN_CANCEL"
                        ? "bg-blue-50 text-blue-600 border-blue-200"
                        : "bg-amber-50 text-amber-600 border-amber-200"
                  )}>
                    {aeOrderStatus.status === "FINISH" ? "Delivered"
                      : aeOrderStatus.status === "PLACE_ORDER_SUCCESS" ? "Shipped"
                      : aeOrderStatus.status === "synced_to_shopify" ? "Tracking Synced"
                      : aeOrderStatus.status ?? "Sent"}
                  </span>
                  <span className="text-[10px] text-slate-500">{aeOrderStatus.ae_order_id ?? aeOrderStatus.cj_order_num}</span>
                </div>
                {aeOrderStatus.tracking_num && (
                  <p className="text-[10px] text-slate-500">{aeOrderStatus.carrier} · <span className="font-mono text-slate-700">{aeOrderStatus.tracking_num}</span></p>
                )}
              </div>
            )}

            {/* CJ Fulfillment Status */}
            {cjStatus?.found && (
              <div className="border border-slate-200 rounded-xl p-3 space-y-1.5">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">CJ Dropshipping</p>
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
                    cjStatus.status === "DELIVERED" || cjStatus.status === "synced_to_shopify"
                      ? "bg-emerald-50 text-emerald-600 border-emerald-200"
                      : cjStatus.status === "IN_TRANSIT" || cjStatus.status === "PACKED" || cjStatus.status === "PICKED"
                        ? "bg-blue-50 text-blue-600 border-blue-200"
                        : "bg-amber-50 text-amber-600 border-amber-200"
                  )}>
                    {CJ_STATUS_LABELS[cjStatus.status ?? ""] ?? cjStatus.status}
                  </span>
                  <span className="text-[10px] text-slate-500">{cjStatus.cj_order_num}</span>
                </div>
                {cjStatus.tracking_num && (
                  <div>
                    <p className="text-[10px] text-slate-500">{cjStatus.carrier} · <span className="font-mono text-slate-700">{cjStatus.tracking_num}</span></p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="px-4 pb-4 space-y-2 border-t border-slate-200 pt-3">
            {/* Fulfill buttons — CJ and AliExpress for paid unfulfilled orders */}
            {selected.financial_status === "paid" && !selected.fulfillment_status && !cjStatus?.found && (
              <button
                onClick={() => fulfillViaCJ(selected)}
                disabled={cjFulfilling}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold disabled:opacity-50 transition-colors"
              >
                {cjFulfilling ? <><Loader2 size={13} className="animate-spin" /> Sending to CJ…</> : <><Package size={13} /> Fulfill via CJ</>}
              </button>
            )}
            {selected.financial_status === "paid" && !selected.fulfillment_status && !aeOrderStatus?.found && (
              <button
                onClick={() => fulfillViaAE(selected)}
                disabled={aeFulfilling}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-xs font-semibold disabled:opacity-50 transition-colors"
              >
                {aeFulfilling ? <><Loader2 size={13} className="animate-spin" /> Sending to AliExpress…</> : <><TrendingUp size={13} /> Fulfill via AliExpress</>}
              </button>
            )}
            {!selected.fulfillment_status && selected.financial_status === "paid" && (
              <button
                onClick={() => fulfill(selected)}
                disabled={acting === String(selected.id)}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-slate-100 hover:bg-emerald-50 text-emerald-700 text-xs font-medium border border-slate-200 hover:border-emerald-200 disabled:opacity-50 transition-colors"
              >
                {acting === String(selected.id) ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                Mark Fulfilled (manual)
              </button>
            )}
            {selected.financial_status !== "refunded" && !selected.fulfillment_status && (
              <button
                onClick={() => cancel(selected)}
                disabled={acting === String(selected.id)}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-slate-100 hover:bg-rose-50 text-rose-600 text-xs font-medium border border-slate-200 hover:border-rose-200 disabled:opacity-50 transition-colors"
              >
                <X size={13} /> Cancel & Refund
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Products tab ──────────────────────────────────────────────────────────────

// ── CJdropshipping types ──────────────────────────────────────────────────────
type CJProduct = {
  cj_pid: string;
  title: string;
  category: string;
  cost_price: number;
  suggested_price: number;
  image_url: string;
  is_free_shipping: boolean;
  supplier: string;
  listed_count: number;
};

// ── AliExpress types ──────────────────────────────────────────────────────────
type AEProduct = {
  ae_pid: string;
  title: string;
  category: string;
  cost_price: number;
  suggested_price: number;
  image_url: string;
  orders_count: number;
  shipping_time: string;
  store_name: string;
  detail_url: string;
};

// ── AI Product Finder types ───────────────────────────────────────────────────
type ProductSuggestion = {
  title: string;
  description: string;
  product_type?: string;
  price: string;
  compare_at_price?: string;
  tags?: string;
  vendor?: string;
  imageQuery?: string;
  variants?: { title: string; price: string; compare_at_price?: string; inventory_quantity?: number }[];
};

const PRICE_RANGES = ["Under $20", "$20–$50", "$50–$150", "$150–$500", "$500+"] as const;
const PRODUCT_COUNTS = [5, 8, 12, 20] as const;

async function runAIProductSearch(
  category: string, keywords: string, count: number, priceRange: string
): Promise<ProductSuggestion[]> {
  const prompt = `You are a product sourcing expert for ecommerce stores.
Generate ${count} unique, sellable product ideas for a "${category}" store.

IMPORTANT: Return ONLY a valid JSON array — no markdown, no explanation, just raw JSON.

Each product must follow this exact schema:
{
  "title": "Exact Product Name",
  "description": "2–3 sentence compelling product description that highlights key benefits",
  "product_type": "Category",
  "price": "XX.XX",
  "compare_at_price": "XX.XX",
  "tags": "comma, separated, tags",
  "vendor": "Realistic Brand Name",
  "imageQuery": "3-4 word image search query",
  "variants": [
    { "title": "Default Title", "price": "XX.XX", "inventory_quantity": 10 }
  ]
}

Store niche: ${category}
Style/keywords: ${keywords || "general bestsellers"}
Price range: ${priceRange}

Rules:
- Vary price points across the ${count} products
- Add size/color/material variants for wearable or configurable products
- Use realistic brand names (not generic "Brand")
- Tags must be relevant and lowercase
- compare_at_price should be 20–40% higher than price (original price / sale effect)
- imageQuery must be concise and descriptive (e.g. "minimalist leather wallet" not "product")`;

  const token = getToken();
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
  const r = await fetch(`${apiBase}/assistant/ai-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ prompt }),
  });
  if (!r.ok) throw new Error("AI generation failed");
  const data = await r.json() as { reply?: string; draft?: string; content?: string };
  const text = data.reply ?? data.draft ?? data.content ?? "";
  const match = text.match(/\[[\s\S]*\]/);
  if (!match) throw new Error("AI returned unexpected format — try again");
  return JSON.parse(match[0]) as ProductSuggestion[];
}

function ProductsTab() {
  // ── Existing state ──────────────────────────────────────────────────────────
  const [products, setProducts] = useState<ShopifyProduct[]>([]);
  const [locations, setLocations] = useState<ShopifyLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<{ variantId: number; inventoryItemId: number; current: number } | null>(null);
  const [newQty, setNewQty] = useState("");
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  // ── Bulk delete state ────────────────────────────────────────────────────────
  const [selectedProducts, setSelectedProducts] = useState<Set<number>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // ── AI finder state ─────────────────────────────────────────────────────────
  const [finderOpen, setFinderOpen] = useState(false);
  const [finderTab, setFinderTab] = useState<"ai" | "cj" | "ae">("ai");
  const [category, setCategory] = useState("");
  const [keywords, setKeywords] = useState("");
  const [count, setCount] = useState<number>(8);
  const [priceRange, setPriceRange] = useState("$20–$50");
  const [generating, setGenerating] = useState(false);
  const [suggestions, setSuggestions] = useState<ProductSuggestion[]>([]);
  const [addingIdx, setAddingIdx] = useState<number | null>(null);
  const [addedIdxs, setAddedIdxs] = useState<Set<number>>(new Set());

  // ── Shared sourcing state ───────────────────────────────────────────────────
  const [srcKeyword, setSrcKeyword] = useState("");
  const [srcMaxPrice, setSrcMaxPrice] = useState("");

  // ── CJ source state ──────────────────────────────────────────────────────────
  const [cjKeyword, setCjKeyword] = useState("");
  const [cjMaxPrice, setCjMaxPrice] = useState("");
  const [cjSearching, setCjSearching] = useState(false);
  const [cjResults, setCjResults] = useState<CJProduct[]>([]);
  const [cjImportingIdx, setCjImportingIdx] = useState<number | null>(null);
  const [cjImportedIdxs, setCjImportedIdxs] = useState<Set<number>>(new Set());

  // ── AliExpress source state ──────────────────────────────────────────────────
  const [aeKeyword, setAeKeyword] = useState("");
  const [aeMaxPrice, setAeMaxPrice] = useState("");
  const [aeSearching, setAeSearching] = useState(false);
  const [aeResults, setAeResults] = useState<AEProduct[]>([]);
  const [aeImportingIdx, setAeImportingIdx] = useState<number | null>(null);
  const [aeImportedIdxs, setAeImportedIdxs] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pd, ld] = await Promise.all([
        shopGet({ action: "products", limit: "100" }) as Promise<{ products: ShopifyProduct[] }>,
        shopGet({ action: "locations" }) as Promise<{ locations: ShopifyLocation[] }>,
      ]);
      setProducts(pd.products ?? []);
      setLocations(ld.locations ?? []);
      // Auto-detect category from existing products
      if (!category) {
        const types = (pd.products ?? []).map((p: ShopifyProduct) => p.product_type).filter(Boolean);
        if (types.length > 0) {
          const freq: Record<string, number> = {};
          types.forEach((t: string) => { freq[t] = (freq[t] ?? 0) + 1; });
          const top = Object.entries(freq).sort((a, b) => b[1] - a[1])[0]?.[0];
          if (top) setCategory(top);
        }
      }
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setLoading(false); }
  }, [category]);

  useEffect(() => { load(); }, [load]);

  async function updateInventory() {
    if (!editing || !newQty.trim()) return;
    const loc = locations.find((l) => l.active);
    if (!loc) { toast.error("No active location found"); return; }
    setSaving(true);
    try {
      await shopPost({
        action: "adjust_inventory",
        inventoryItemId: String(editing.inventoryItemId),
        locationId: String(loc.id),
        available: parseInt(newQty),
      });
      toast.success("Inventory updated");
      setEditing(null);
      setNewQty("");
      await load();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setSaving(false); }
  }

  async function bulkDelete() {
    if (!selectedProducts.size) return;
    if (!confirm(`Delete ${selectedProducts.size} product${selectedProducts.size > 1 ? "s" : ""}? This cannot be undone.`)) return;
    setBulkDeleting(true);
    try {
      const res = await shopPost({
        action: "bulk_delete_products",
        productIds: [...selectedProducts].map(String),
      }) as { ok: boolean; deleted: number; failed: number };
      if (res.failed > 0) {
        toast.error(`${res.failed} product(s) failed to delete`);
      } else {
        toast.success(`${res.deleted} product${res.deleted > 1 ? "s" : ""} deleted`);
      }
      setSelectedProducts(new Set());
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBulkDeleting(false);
    }
  }

  async function searchCJ(keywordOverride?: string) {
    const kw = keywordOverride ?? srcKeyword ?? cjKeyword;
    if (!kw.trim()) { toast.error("Enter a search keyword"); return; }
    if (keywordOverride) { setSrcKeyword(keywordOverride); setCjKeyword(keywordOverride); }
    const maxP = srcMaxPrice || cjMaxPrice;
    setCjSearching(true);
    setCjResults([]);
    setCjImportedIdxs(new Set());
    try {
      const token = getToken();
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
      const params = new URLSearchParams({ keyword: kw, page_size: "20" });
      if (maxP) params.set("max_price", maxP);
      const r = await fetch(`${apiBase}/cj/products?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json() as { products: CJProduct[]; total: number };
      setCjResults(data.products ?? []);
      if (!data.products?.length) toast.info("No products found — try different keywords");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "CJ search failed");
    } finally {
      setCjSearching(false);
    }
  }

  async function importFromCJ(p: CJProduct, idx: number) {
    setCjImportingIdx(idx);
    try {
      await shopPost({
        action: "create_product",
        product: {
          title:        p.title,
          description:  `Sourced from CJdropshipping. Category: ${p.category}`,
          vendor:       p.supplier || "CJdropshipping",
          product_type: p.category,
          price:        String(p.suggested_price),
          compare_at_price: String(Math.round(p.suggested_price * 1.3 * 100) / 100),
          tags:         `dropship,cj,${p.category.toLowerCase()}`,
          variants:     [{ title: "Default Title", price: String(p.suggested_price), inventory_quantity: 50 }],
        },
      });
      setCjImportedIdxs((prev) => new Set(prev).add(idx));
      toast.success(`"${p.title.slice(0, 40)}" added to Shopify`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setCjImportingIdx(null);
    }
  }

  async function searchAE(keywordOverride?: string) {
    const kw = keywordOverride ?? srcKeyword ?? aeKeyword;
    if (!kw.trim()) { toast.error("Enter a search keyword"); return; }
    if (keywordOverride) { setSrcKeyword(keywordOverride); setAeKeyword(keywordOverride); }
    const maxP = srcMaxPrice || aeMaxPrice;
    setAeSearching(true);
    setAeResults([]);
    setAeImportedIdxs(new Set());
    try {
      const token = getToken();
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
      const params = new URLSearchParams({ keyword: kw, page_size: "20" });
      if (maxP) params.set("max_price", maxP);
      const r = await fetch(`${apiBase}/ae/products?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json() as { products: AEProduct[]; total: number };
      setAeResults(data.products ?? []);
      if (!data.products?.length) toast.info("No products found — try different keywords");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "AliExpress search failed");
    } finally {
      setAeSearching(false);
    }
  }

  async function importFromAE(p: AEProduct, idx: number) {
    setAeImportingIdx(idx);
    try {
      await shopPost({
        action: "create_product",
        product: {
          title:        p.title,
          description:  `Sourced from AliExpress. Category: ${p.category}`,
          vendor:       p.store_name || "AliExpress",
          product_type: p.category,
          price:        String(p.suggested_price),
          compare_at_price: String(Math.round(p.suggested_price * 1.3 * 100) / 100),
          tags:         `dropship,aliexpress,${p.category.toLowerCase()}`,
          variants:     [{ title: "Default Title", price: String(p.suggested_price), inventory_quantity: 50 }],
        },
      });
      setAeImportedIdxs((prev) => new Set(prev).add(idx));
      toast.success(`"${p.title.slice(0, 40)}" added to Shopify`);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setAeImportingIdx(null);
    }
  }

  async function handleGenerate() {
    if (!category.trim()) { toast.error("Enter a store category first"); return; }
    setGenerating(true);
    setSuggestions([]);
    setAddedIdxs(new Set());
    try {
      const results = await runAIProductSearch(category, keywords, count, priceRange);
      setSuggestions(results);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function addToStore(s: ProductSuggestion, idx: number) {
    setAddingIdx(idx);
    try {
      await shopPost({ action: "create_product", product: s });
      setAddedIdxs((prev) => new Set([...prev, idx]));
      toast.success(`"${s.title}" added to your Shopify store`);
      await load(); // refresh product list
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to add product");
    } finally {
      setAddingIdx(null);
    }
  }

  const filtered = products.filter((p) => !search || p.title.toLowerCase().includes(search.toLowerCase()));
  const allVariants = products.flatMap((p) => p.variants.map((v) => ({ ...v, productTitle: p.title, productId: p.id })));
  const lowStock = allVariants.filter((v) => v.inventory_quantity < 5).length;
  const outOfStock = allVariants.filter((v) => v.inventory_quantity <= 0).length;

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Alert bar */}
      {(lowStock > 0 || outOfStock > 0) && (
        <div className="px-4 py-2.5 bg-amber-50 border-b border-amber-200 flex items-center gap-2">
          <AlertTriangle size={13} className="text-amber-600" />
          <span className="text-xs text-amber-700">
            {outOfStock > 0 && <span className="font-semibold">{outOfStock} out of stock</span>}
            {outOfStock > 0 && lowStock > outOfStock && " · "}
            {lowStock > outOfStock && <span>{lowStock - outOfStock} running low</span>}
          </span>
        </div>
      )}

      {/* Toolbar */}
      <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
        <div className="flex items-center gap-2 bg-slate-100 rounded-xl px-3 py-1.5 border border-slate-200">
          <Search size={12} className="text-slate-500" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search products…" className="bg-transparent text-xs text-slate-700 placeholder-slate-400 outline-none w-36" />
        </div>
        <span className="text-xs text-slate-600">{filtered.length} products</span>
        {selectedProducts.size > 0 && (
          <button
            onClick={() => void bulkDelete()}
            disabled={bulkDeleting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-red-600 hover:bg-red-500 text-white disabled:opacity-50 transition-colors"
          >
            {bulkDeleting ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
            Delete {selectedProducts.size} selected
          </button>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button onClick={load} className="p-1.5 text-slate-500 hover:text-slate-700"><RefreshCw size={13} /></button>
          <button
            onClick={() => { setFinderOpen((o) => !o); setSuggestions([]); }}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors border",
              finderOpen
                ? "bg-brand-dark text-white border-brand"
                : "bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200"
            )}
          >
            <Wand2 size={12} />
            {finderOpen ? "Hide Finder" : "AI Product Finder"}
          </button>
        </div>
      </div>

      {/* AI Product Finder Panel */}
      {finderOpen && (
        <div className="border-b border-slate-200 bg-slate-50">
          {/* Tab switcher */}
          <div className="flex items-center gap-1 px-4 pt-3 pb-0">
            <button
              onClick={() => setFinderTab("ai")}
              className={cn(
                "px-3 py-1.5 rounded-t-lg text-xs font-medium transition-colors border-b-2",
                finderTab === "ai" ? "border-brand text-brand bg-white" : "border-transparent text-slate-500 hover:text-slate-700"
              )}
            >
              <span className="flex items-center gap-1.5"><Sparkles size={11} /> AI Ideas</span>
            </button>
            <button
              onClick={() => setFinderTab(finderTab === "ae" ? "ae" : "cj")}
              className={cn(
                "px-3 py-1.5 rounded-t-lg text-xs font-medium transition-colors border-b-2",
                (finderTab === "cj" || finderTab === "ae") ? "border-brand text-brand bg-white" : "border-transparent text-slate-500 hover:text-slate-700"
              )}
            >
              <span className="flex items-center gap-1.5"><Package size={11} /> Source Products</span>
            </button>
          </div>

          {/* Config row */}
          {finderTab === "ai" && <>
          <div className="px-4 pt-4 pb-3 flex flex-wrap gap-3 items-end">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Store Category / Niche</label>
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="e.g. Men's Streetwear, Organic Skincare, Home Gym..."
                className="bg-slate-100 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 placeholder-slate-500 outline-none focus:ring-1 focus:ring-brand w-64"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Style / Keywords</label>
              <input
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                placeholder="e.g. minimalist, eco-friendly, premium..."
                className="bg-slate-100 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 placeholder-slate-500 outline-none focus:ring-1 focus:ring-brand w-52"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Price Range</label>
              <select
                value={priceRange}
                onChange={(e) => setPriceRange(e.target.value)}
                className="bg-slate-100 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 outline-none focus:ring-1 focus:ring-brand"
              >
                {PRICE_RANGES.map((r) => <option key={r}>{r}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">How many</label>
              <select
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                className="bg-slate-100 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 outline-none focus:ring-1 focus:ring-brand"
              >
                {PRODUCT_COUNTS.map((n) => <option key={n} value={n}>{n} products</option>)}
              </select>
            </div>
            <button
              onClick={handleGenerate}
              disabled={generating || !category.trim()}
              className="flex items-center gap-2 px-4 py-2 bg-brand-dark hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-medium transition-colors"
            >
              {generating
                ? <><Loader2 size={12} className="animate-spin" /> Researching…</>
                : <><Sparkles size={12} /> Find Products</>}
            </button>
          </div>

          {/* Generating skeleton */}
          {finderTab === "ai" && generating && (
            <div className="px-4 pb-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
              {Array.from({ length: count > 8 ? 4 : count > 4 ? 3 : 2 }).map((_, i) => (
                <div key={i} className="bg-slate-100 rounded-2xl p-4 animate-pulse flex flex-col gap-2">
                  <div className="h-24 bg-slate-200 rounded-xl" />
                  <div className="h-3 bg-slate-200 rounded w-3/4" />
                  <div className="h-2 bg-slate-200 rounded w-1/2" />
                  <div className="h-2 bg-slate-200 rounded w-full" />
                  <div className="h-2 bg-slate-200 rounded w-2/3" />
                </div>
              ))}
            </div>
          )}

          {/* Suggestions grid */}
          {finderTab === "ai" && !generating && suggestions.length > 0 && (
            <div className="px-4 pb-4">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs text-slate-400">
                  <span className="font-semibold text-slate-800">{suggestions.length}</span> products found for <span className="text-brand">{category}</span>
                  {" · "}<span className="text-slate-600">{addedIdxs.size} added to store</span>
                </p>
                <button onClick={handleGenerate} className="text-xs text-brand hover:text-brand/50 flex items-center gap-1">
                  <RefreshCw size={11} /> Regenerate
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
                {suggestions.map((s, idx) => {
                  const added = addedIdxs.has(idx);
                  const adding = addingIdx === idx;
                  const discount = s.compare_at_price
                    ? Math.round((1 - parseFloat(s.price) / parseFloat(s.compare_at_price)) * 100)
                    : 0;
                  return (
                    <div
                      key={idx}
                      className={cn(
                        "bg-slate-100 border rounded-2xl p-3 flex flex-col gap-2 transition-all",
                        added ? "border-emerald-200 bg-emerald-50" : "border-slate-200/60 hover:border-slate-300"
                      )}
                    >
                      {/* Image placeholder with category icon */}
                      <div className="h-20 bg-slate-200 rounded-xl flex items-center justify-center relative overflow-hidden">
                        <div className="text-center">
                          <Package size={22} className="text-slate-500 mx-auto mb-1" />
                          <p className="text-[9px] text-slate-600 leading-tight px-2">{s.imageQuery || s.product_type}</p>
                        </div>
                        {discount > 0 && (
                          <span className="absolute top-1.5 right-1.5 bg-rose-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full">
                            -{discount}%
                          </span>
                        )}
                        {added && (
                          <div className="absolute inset-0 bg-emerald-100/80 flex items-center justify-center rounded-xl">
                            <CheckCircle2 size={20} className="text-emerald-600" />
                          </div>
                        )}
                      </div>

                      {/* Product info */}
                      <div className="flex-1">
                        <p className="text-xs font-semibold text-slate-800 leading-tight mb-0.5 line-clamp-2">{s.title}</p>
                        {s.vendor && <p className="text-[10px] text-slate-500 mb-1">{s.vendor}</p>}
                        <p className="text-[10px] text-slate-400 leading-relaxed line-clamp-3">{s.description}</p>
                      </div>

                      {/* Tags */}
                      {s.tags && (
                        <div className="flex flex-wrap gap-1">
                          {s.tags.split(",").slice(0, 3).map((t) => (
                            <span key={t} className="text-[9px] bg-slate-200 text-slate-500 px-1.5 py-0.5 rounded-full">
                              {t.trim()}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Price + variants */}
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-800">${s.price}</span>
                        {s.compare_at_price && (
                          <span className="text-[10px] text-slate-600 line-through">${s.compare_at_price}</span>
                        )}
                        {s.variants && s.variants.length > 1 && (
                          <span className="text-[9px] text-slate-500 ml-auto">{s.variants.length} variants</span>
                        )}
                      </div>

                      {/* Add to store */}
                      <button
                        onClick={() => addToStore(s, idx)}
                        disabled={added || adding}
                        className={cn(
                          "w-full py-1.5 rounded-xl text-xs font-medium transition-colors flex items-center justify-center gap-1.5",
                          added
                            ? "bg-emerald-50 text-emerald-600 border border-emerald-200 cursor-default"
                            : "bg-brand-dark hover:bg-brand text-white disabled:opacity-50"
                        )}
                      >
                        {adding ? (
                          <><Loader2 size={11} className="animate-spin" /> Adding…</>
                        ) : added ? (
                          <><Check size={11} /> Added to store</>
                        ) : (
                          <><Plus size={11} /> Add to Shopify</>
                        )}
                      </button>
                      {/* Source on CJ */}
                      <button
                        onClick={() => {
                          setSrcKeyword(s.title);
                          setCjKeyword(s.title);
                          setFinderTab("cj");
                          searchCJ(s.title);
                        }}
                        className="w-full py-1 rounded-xl text-[10px] font-medium border border-slate-200 text-slate-500 hover:border-brand hover:text-brand transition-colors flex items-center justify-center gap-1"
                      >
                        <Package size={10} /> Source on CJ
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Empty state after generate with no results */}
          {finderTab === "ai" && !generating && suggestions.length === 0 && (
            <div className="px-4 pb-5 flex flex-col items-center gap-2 text-center py-6">
              <Sparkles size={24} className="text-brand mb-1" />
              <p className="text-sm font-medium text-slate-700">AI Product Research</p>
              <p className="text-xs text-slate-500 max-w-xs">
                Tell the AI your store niche and it will suggest ready-to-sell products with descriptions, pricing, and tags — add them to Shopify with one click.
              </p>
            </div>
          )}
          </>}

          {/* Unified Sourcing Panel */}
          {(finderTab === "cj" || finderTab === "ae") && (
            <div className="flex flex-col" style={{maxHeight: "500px"}}>
              {/* Search bar + supplier toggle — sticky */}
              <div className="px-4 pt-3 pb-3 border-b border-slate-200 flex-shrink-0 space-y-2">
                {/* Supplier pill toggle */}
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold mr-1">Source from</span>
                  <button
                    onClick={() => setFinderTab("cj")}
                    className={cn(
                      "flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-semibold border transition-all",
                      finderTab === "cj"
                        ? "bg-[#FF6600] text-white border-[#FF6600] shadow-sm"
                        : "bg-white text-slate-500 border-slate-200 hover:border-[#FF6600] hover:text-[#FF6600]"
                    )}
                  >
                    <Package size={10} /> CJdropshipping
                  </button>
                  <button
                    onClick={() => setFinderTab("ae")}
                    className={cn(
                      "flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-semibold border transition-all",
                      finderTab === "ae"
                        ? "bg-[#E62222] text-white border-[#E62222] shadow-sm"
                        : "bg-white text-slate-500 border-slate-200 hover:border-[#E62222] hover:text-[#E62222]"
                    )}
                  >
                    <TrendingUp size={10} /> AliExpress
                  </button>
                </div>

                {/* Search inputs */}
                <div className="flex flex-wrap gap-2 items-end">
                  <input
                    value={srcKeyword}
                    onChange={(e) => setSrcKeyword(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") finderTab === "cj" ? searchCJ() : searchAE(); }}
                    placeholder="e.g. phone case, wireless earbuds, yoga mat..."
                    className="bg-slate-100 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 placeholder-slate-500 outline-none focus:ring-1 focus:ring-brand w-72"
                  />
                  <input
                    value={srcMaxPrice}
                    onChange={(e) => setSrcMaxPrice(e.target.value)}
                    placeholder="Max cost (USD)"
                    className="bg-slate-100 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 placeholder-slate-500 outline-none focus:ring-1 focus:ring-brand w-32"
                  />
                  <button
                    onClick={() => finderTab === "cj" ? searchCJ() : searchAE()}
                    disabled={(finderTab === "cj" ? cjSearching : aeSearching) || !srcKeyword.trim()}
                    className={cn(
                      "flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors",
                      finderTab === "cj" ? "bg-[#FF6600] hover:bg-[#e05a00]" : "bg-[#E62222] hover:bg-[#c71c1c]"
                    )}
                  >
                    {(finderTab === "cj" ? cjSearching : aeSearching)
                      ? <><Loader2 size={12} className="animate-spin" /> Searching…</>
                      : <><Search size={12} /> Search {finderTab === "cj" ? "CJ" : "AliExpress"}</>}
                  </button>
                </div>
              </div>

              {/* Scrollable results */}
              <div className="overflow-y-auto flex-1 px-4 pb-4 pt-3">

                {/* Skeleton */}
                {(finderTab === "cj" ? cjSearching : aeSearching) && (
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
                    {Array.from({ length: 8 }).map((_, i) => (
                      <div key={i} className="bg-slate-100 rounded-2xl p-3 animate-pulse flex flex-col gap-2">
                        <div className="h-24 bg-slate-200 rounded-xl" />
                        <div className="h-3 bg-slate-200 rounded w-3/4" />
                        <div className="h-2 bg-slate-200 rounded w-1/2" />
                        <div className="h-6 bg-slate-200 rounded-xl mt-auto" />
                      </div>
                    ))}
                  </div>
                )}

                {/* CJ Results */}
                {finderTab === "cj" && !cjSearching && cjResults.length > 0 && (
                  <>
                    <p className="text-xs text-slate-500 mb-3">
                      <span className="font-semibold text-slate-800">{cjResults.length}</span> real supplier products · <span className="text-brand">{cjImportedIdxs.size} imported</span>
                    </p>
                    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
                      {cjResults.map((p, idx) => {
                        const imported = cjImportedIdxs.has(idx);
                        const importing = cjImportingIdx === idx;
                        const marginPct = p.suggested_price > 0 ? Math.round((p.suggested_price - p.cost_price) / p.suggested_price * 100) : 0;
                        return (
                          <div key={idx} className={cn(
                            "bg-white border rounded-2xl p-3 flex flex-col gap-2 transition-all",
                            imported ? "border-emerald-200 bg-emerald-50" : "border-slate-200 hover:border-slate-300 hover:shadow-sm"
                          )}>
                            <div className="h-24 bg-slate-100 rounded-xl overflow-hidden relative flex items-center justify-center">
                              {p.image_url
                                ? <img src={p.image_url} alt={p.title} className="w-full h-full object-cover" />
                                : <Package size={24} className="text-slate-400" />}
                              <span className="absolute top-1 right-1 bg-[#FF6600] text-white text-[8px] font-bold px-1.5 py-0.5 rounded-full">CJ</span>
                              {p.is_free_shipping && <span className="absolute bottom-1 left-1 bg-emerald-500 text-white text-[8px] font-bold px-1.5 py-0.5 rounded-full">FREE SHIP</span>}
                              {imported && <div className="absolute inset-0 bg-emerald-100/80 flex items-center justify-center rounded-xl"><CheckCircle2 size={20} className="text-emerald-600" /></div>}
                            </div>
                            <div className="flex-1">
                              <p className="text-xs font-semibold text-slate-800 leading-tight line-clamp-2 mb-0.5">{p.title}</p>
                              <p className="text-[10px] text-slate-400">{p.category}</p>
                            </div>
                            <div className="bg-slate-50 rounded-xl p-2 flex items-center justify-between">
                              <div><p className="text-[9px] text-slate-400 uppercase">Cost</p><p className="text-xs font-bold text-slate-700">${p.cost_price.toFixed(2)}</p></div>
                              <div className="text-center"><p className="text-[9px] text-emerald-600 font-semibold">{marginPct}% margin</p></div>
                              <div className="text-right"><p className="text-[9px] text-slate-400 uppercase">Sell at</p><p className="text-xs font-bold text-brand">${p.suggested_price.toFixed(2)}</p></div>
                            </div>
                            <button onClick={() => importFromCJ(p, idx)} disabled={imported || importing}
                              className={cn("w-full py-1.5 rounded-xl text-xs font-medium transition-colors flex items-center justify-center gap-1.5",
                                imported ? "bg-emerald-50 text-emerald-600 border border-emerald-200 cursor-default" : "bg-brand-dark hover:bg-brand text-white disabled:opacity-50")}>
                              {importing ? <><Loader2 size={11} className="animate-spin" /> Importing…</> : imported ? <><Check size={11} /> Imported</> : <><Plus size={11} /> Import to Shopify</>}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}

                {/* AliExpress Results */}
                {finderTab === "ae" && !aeSearching && aeResults.length > 0 && (
                  <>
                    <p className="text-xs text-slate-500 mb-3">
                      <span className="font-semibold text-slate-800">{aeResults.length}</span> real supplier products · <span className="text-brand">{aeImportedIdxs.size} imported</span>
                    </p>
                    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
                      {aeResults.map((p, idx) => {
                        const imported  = aeImportedIdxs.has(idx);
                        const importing = aeImportingIdx === idx;
                        const marginPct = p.cost_price > 0 ? Math.round((p.suggested_price - p.cost_price) / p.suggested_price * 100) : 0;
                        return (
                          <div key={idx} className={cn("border rounded-2xl p-3 flex flex-col gap-2 transition-all bg-white",
                            imported ? "border-emerald-200 bg-emerald-50" : "border-slate-200 hover:border-slate-300 hover:shadow-sm")}>
                            <div className="h-24 rounded-xl overflow-hidden bg-slate-100 relative flex-shrink-0 flex items-center justify-center">
                              {p.image_url
                                ? <img src={p.image_url} alt={p.title} className="w-full h-full object-cover" />
                                : <TrendingUp size={22} className="text-slate-400" />}
                              <span className="absolute top-1 right-1 bg-[#E62222] text-white text-[8px] font-bold px-1.5 py-0.5 rounded-full">AE</span>
                              {imported && <div className="absolute inset-0 bg-emerald-100/80 flex items-center justify-center rounded-xl"><CheckCircle2 size={20} className="text-emerald-600" /></div>}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-semibold text-slate-800 leading-tight line-clamp-2 mb-0.5">{p.title}</p>
                              <p className="text-[10px] text-slate-400 truncate">{p.store_name || p.category}</p>
                              {p.orders_count > 0 && <p className="text-[10px] text-emerald-600 font-medium">{p.orders_count.toLocaleString()} orders</p>}
                              {p.shipping_time && <p className="text-[10px] text-slate-400">Ships in {p.shipping_time}d</p>}
                            </div>
                            <div className="bg-slate-50 rounded-xl p-2 flex items-center justify-between">
                              <div><p className="text-[9px] text-slate-400 uppercase">Cost</p><p className="text-xs font-bold text-slate-700">${p.cost_price.toFixed(2)}</p></div>
                              <div className="text-center"><p className="text-[9px] text-emerald-600 font-semibold">{marginPct}% margin</p></div>
                              <div className="text-right"><p className="text-[9px] text-slate-400 uppercase">Sell at</p><p className="text-xs font-bold text-brand">${p.suggested_price.toFixed(2)}</p></div>
                            </div>
                            <button onClick={() => importFromAE(p, idx)} disabled={imported || importing}
                              className={cn("w-full py-1.5 rounded-xl text-xs font-medium transition-colors flex items-center justify-center gap-1.5",
                                imported ? "bg-emerald-50 text-emerald-600 border border-emerald-200 cursor-default" : "bg-brand-dark hover:bg-brand text-white disabled:opacity-50")}>
                              {importing ? <><Loader2 size={11} className="animate-spin" /> Importing…</> : imported ? <><Check size={11} /> Imported</> : <><Plus size={11} /> Import to Shopify</>}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}

                {/* Empty state */}
                {!cjSearching && !aeSearching && (finderTab === "cj" ? cjResults : aeResults).length === 0 && (
                  <div className="flex flex-col items-center gap-2 text-center py-8">
                    <Package size={28} className="text-slate-300 mb-1" />
                    <p className="text-sm font-medium text-slate-600">Source Real Products from {finderTab === "cj" ? "CJdropshipping" : "AliExpress"}</p>
                    <p className="text-xs text-slate-400 max-w-sm">
                      {finderTab === "cj"
                        ? "Search 500,000+ supplier products with real images, cost prices, and shipping info."
                        : "Search millions of AliExpress products sorted by bestseller ranking and order volume."}
                      {" "}Import any product to your Shopify store instantly.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Product table */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center"><Loader2 size={22} className="animate-spin text-slate-600" /></div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-white border-b border-slate-200">
              <tr>
                <th className="px-4 py-2.5 w-8">
                  <input
                    type="checkbox"
                    className="rounded border-slate-300 text-brand cursor-pointer"
                    checked={filtered.length > 0 && filtered.every((p) => selectedProducts.has(p.id))}
                    onChange={(e) => {
                      if (e.target.checked) setSelectedProducts(new Set(filtered.map((p) => p.id)));
                      else setSelectedProducts(new Set());
                    }}
                  />
                </th>
                {["Product", "SKU", "Price", "Stock", "Status", "Action"].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((product) =>
                product.variants.map((variant, vi) => (
                  <tr key={variant.id} className={cn("border-b border-slate-100 hover:bg-slate-50 transition-colors", selectedProducts.has(product.id) && "bg-red-50/40")}>
                    <td className="px-4 py-3 w-8">
                      {vi === 0 && (
                        <input
                          type="checkbox"
                          className="rounded border-slate-300 text-brand cursor-pointer"
                          checked={selectedProducts.has(product.id)}
                          onChange={(e) => {
                            const next = new Set(selectedProducts);
                            if (e.target.checked) next.add(product.id); else next.delete(product.id);
                            setSelectedProducts(next);
                          }}
                        />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {vi === 0 ? (
                        <div className="flex items-center gap-2">
                          {product.image?.src && (
                            <img src={product.image.src} alt="" className="w-8 h-8 rounded-lg object-cover bg-slate-100" />
                          )}
                          <div>
                            <p className="font-medium text-slate-800">{product.title}</p>
                            {product.product_type && <p className="text-[10px] text-slate-600">{product.product_type}</p>}
                          </div>
                        </div>
                      ) : (
                        <p className="text-slate-500 pl-10">↳ {variant.title}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-500 font-mono">{variant.sku || "—"}</td>
                    <td className="px-4 py-3 font-semibold text-slate-800">{fmtMoney(variant.price)}</td>
                    <td className="px-4 py-3">
                      {editing?.variantId === variant.id ? (
                        <div className="flex items-center gap-1.5">
                          <input
                            value={newQty}
                            onChange={(e) => setNewQty(e.target.value)}
                            type="number"
                            autoFocus
                            className="w-16 bg-slate-200 text-xs text-slate-800 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-brand border border-slate-300"
                          />
                          <button onClick={updateInventory} disabled={saving} className="p-1 text-emerald-600 hover:text-emerald-300 disabled:opacity-50">
                            {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                          </button>
                          <button onClick={() => { setEditing(null); setNewQty(""); }} className="p-1 text-slate-500 hover:text-slate-700"><X size={11} /></button>
                        </div>
                      ) : (
                        <StockBadge qty={variant.inventory_quantity} />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] font-medium capitalize", product.status === "active" ? "text-emerald-600" : "text-slate-500")}>
                        {product.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => { setEditing({ variantId: variant.id, inventoryItemId: variant.inventory_item_id, current: variant.inventory_quantity }); setNewQty(String(variant.inventory_quantity)); }}
                        className="text-[10px] text-brand hover:text-brand/50 flex items-center gap-1 transition-colors"
                      >
                        <RotateCcw size={10} /> Update stock
                      </button>
                    </td>
                  </tr>
                ))
              )}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-slate-600 text-xs">
                    No products found. Use <span className="text-brand">AI Product Finder</span> above to add products.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Customers tab ─────────────────────────────────────────────────────────────

type CustomerSegment = "all" | "vip" | "new" | "at-risk";

function CustomersTab() {
  const [customers, setCustomers] = useState<ShopifyCustomer[]>([]);
  const [loading, setLoading] = useState(true);
  const [segment, setSegment] = useState<CustomerSegment>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<ShopifyCustomer | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await shopGet({ action: "customers", limit: "100" }) as { customers: ShopifyCustomer[] };
      setCustomers(d.customers ?? []);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  function segmentFilter(c: ShopifyCustomer): boolean {
    if (segment === "vip") return c.orders_count >= 3 || parseFloat(c.total_spent ?? "0") >= 500;
    if (segment === "new") return c.orders_count === 1;
    if (segment === "at-risk") {
      const lastOrder = new Date(c.updated_at);
      const daysSince = (Date.now() - lastOrder.getTime()) / 86400000;
      return daysSince > 90 && c.orders_count > 1;
    }
    return true;
  }

  const filtered = customers
    .filter(segmentFilter)
    .filter((c) => !search || `${c.first_name} ${c.last_name} ${c.email}`.toLowerCase().includes(search.toLowerCase()));

  const vipCount = customers.filter((c) => c.orders_count >= 3 || parseFloat(c.total_spent ?? "0") >= 500).length;
  const newCount = customers.filter((c) => c.orders_count === 1).length;
  const atRiskCount = customers.filter((c) => {
    const days = (Date.now() - new Date(c.updated_at).getTime()) / 86400000;
    return days > 90 && c.orders_count > 1;
  }).length;

  return (
    <div className="flex-1 flex overflow-hidden">
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-2 bg-slate-100 rounded-xl px-3 py-1.5 border border-slate-200">
            <Search size={12} className="text-slate-500" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search customers…" className="bg-transparent text-xs text-slate-700 placeholder-slate-400 outline-none w-36" />
          </div>
          <div className="flex items-center bg-slate-100 rounded-xl p-0.5 gap-0.5">
            {([
              ["all", "All", customers.length],
              ["vip", "⭐ VIP", vipCount],
              ["new", "New", newCount],
              ["at-risk", "At-risk", atRiskCount],
            ] as [CustomerSegment, string, number][]).map(([id, label, count]) => (
              <button
                key={id}
                onClick={() => setSegment(id)}
                className={cn("text-xs px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center gap-1", segment === id ? "bg-brand-dark text-white" : "text-slate-500 hover:text-slate-900")}
              >
                {label}
                <span className={cn("text-[10px] px-1 rounded-full", segment === id ? "bg-white/20 text-white" : "bg-slate-200 text-slate-400")}>{count}</span>
              </button>
            ))}
          </div>
          <button onClick={load} className="ml-auto p-1.5 text-slate-500 hover:text-slate-700"><RefreshCw size={13} /></button>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center"><Loader2 size={22} className="animate-spin text-slate-600" /></div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white border-b border-slate-200">
                <tr>
                  {["Customer", "Location", "Orders", "Lifetime Value", "Last Order", "Status"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => {
                  const isVip = c.orders_count >= 3 || parseFloat(c.total_spent ?? "0") >= 500;
                  const daysSince = (Date.now() - new Date(c.updated_at).getTime()) / 86400000;
                  const isAtRisk = daysSince > 90 && c.orders_count > 1;
                  return (
                    <tr
                      key={c.id}
                      onClick={() => setSelected(selected?.id === c.id ? null : c)}
                      className={cn("border-b border-slate-100 hover:bg-slate-50 transition-colors cursor-pointer", selected?.id === c.id && "bg-slate-100")}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-full bg-brand-dark/30 flex items-center justify-center text-[10px] font-bold text-brand shrink-0">
                            {(c.first_name?.[0] ?? c.email?.[0] ?? "?").toUpperCase()}
                          </div>
                          <div>
                            <p className="font-medium text-slate-800">{c.first_name} {c.last_name}</p>
                            <p className="text-[10px] text-slate-500">{c.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{c.default_address?.city ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-700">{c.orders_count}</td>
                      <td className="px-4 py-3 font-semibold text-emerald-600">{fmtMoney(c.total_spent)}</td>
                      <td className="px-4 py-3 text-slate-500">{c.last_order_name ?? fmtDate(c.updated_at)}</td>
                      <td className="px-4 py-3">
                        {isVip ? <span className="text-[10px] font-semibold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">⭐ VIP</span>
                          : isAtRisk ? <span className="text-[10px] font-semibold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200">At-risk</span>
                          : c.orders_count === 1 ? <span className="text-[10px] font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">New</span>
                          : <span className="text-[10px] text-slate-500">Regular</span>
                        }
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Customer detail */}
      {selected && (
        <div className="w-72 border-l border-slate-200 bg-white flex flex-col overflow-y-auto shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
            <span className="font-semibold text-sm">{selected.first_name} {selected.last_name}</span>
            <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-slate-900"><X size={14} /></button>
          </div>
          <div className="px-4 py-4 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-slate-100 rounded-xl p-3 text-center">
                <p className="text-[10px] text-slate-500">Orders</p>
                <p className="text-lg font-bold">{selected.orders_count}</p>
              </div>
              <div className="bg-slate-100 rounded-xl p-3 text-center">
                <p className="text-[10px] text-slate-500">Lifetime value</p>
                <p className="text-sm font-bold text-emerald-600">{fmtMoney(selected.total_spent)}</p>
              </div>
            </div>
            <div className="space-y-1.5">
              {selected.email && <p className="text-xs text-slate-400 flex items-center gap-2"><Mail size={11} className="text-slate-600" />{selected.email}</p>}
              {selected.phone && <p className="text-xs text-slate-400">{selected.phone}</p>}
              {selected.default_address?.city && <p className="text-xs text-slate-400 flex items-center gap-2"><MapPin size={11} className="text-slate-600" />{selected.default_address.city}, {selected.default_address.country}</p>}
              <p className="text-xs text-slate-600">Customer since {fmtDate(selected.created_at)}</p>
              <p className="text-xs text-slate-600 flex items-center gap-1">
                {selected.accepts_marketing ? <CheckCircle2 size={11} className="text-emerald-500" /> : <XCircle size={11} className="text-slate-600" />}
                {selected.accepts_marketing ? "Subscribed to marketing" : "Not subscribed"}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Abandoned carts tab ───────────────────────────────────────────────────────

function AbandonedTab() {
  const [carts, setCarts] = useState<ShopifyCheckout[]>([]);
  const [loading, setLoading] = useState(true);
  const [drafting, setDrafting] = useState<number | null>(null);
  const [draftEmails, setDraftEmails] = useState<Record<number, string>>({});
  const [showDraft, setShowDraft] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await shopGet({ action: "abandoned", limit: "50" }) as { carts: ShopifyCheckout[] };
      setCarts(d.carts ?? []);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function generateRecoveryEmail(cart: ShopifyCheckout) {
    setDrafting(cart.id);
    try {
      const items = cart.line_items.map((li) => `${li.quantity}× ${li.title} (${fmtMoney(li.price)})`).join(", ");
      const draft = await aiDraft(
        `Write a friendly, persuasive abandoned cart recovery email.
Customer: ${cart.email}
Cart value: ${fmtMoney(cart.total_price, cart.currency)}
Items: ${items}
Abandoned: ${timeAgo(cart.updated_at)}
Recovery link: ${cart.abandoned_checkout_url ?? "[checkout link]"}

Write a subject line then the email body. Keep it personal, create urgency, mention the items, include the checkout link. Max 120 words total.`
      );
      setDraftEmails((prev) => ({ ...prev, [cart.id]: draft }));
      setShowDraft(cart.id);
    } catch { toast.error("Draft failed"); }
    finally { setDrafting(null); }
  }

  const totalValue = carts.reduce((s, c) => s + parseFloat(c.total_price ?? "0"), 0);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Summary bar */}
      <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-4">
        <div>
          <span className="text-xs text-slate-500">Abandoned carts: </span>
          <span className="text-sm font-bold text-slate-800">{carts.length}</span>
        </div>
        <div>
          <span className="text-xs text-slate-500">Recoverable value: </span>
          <span className="text-sm font-bold text-amber-600">{fmtMoney(totalValue)}</span>
        </div>
        <button onClick={load} className="ml-auto p-1.5 text-slate-500 hover:text-slate-700"><RefreshCw size={13} /></button>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center"><Loader2 size={22} className="animate-spin text-slate-600" /></div>
      ) : carts.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-600">
          <ShoppingCart size={28} />
          <p className="text-sm">No abandoned carts — great!</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {carts.map((cart) => (
            <div key={cart.id} className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-slate-800">{cart.email}</p>
                    <span className="text-[10px] text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                      {fmtMoney(cart.total_price, cart.currency)}
                    </span>
                    <span className="text-[10px] text-slate-600">{timeAgo(cart.updated_at)}</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {cart.line_items.map((li) => `${li.quantity}× ${li.title}`).join(" · ")}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {cart.abandoned_checkout_url && (
                    <a href={cart.abandoned_checkout_url} target="_blank" rel="noopener noreferrer" className="p-1.5 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors" title="Open checkout">
                      <ExternalLink size={13} />
                    </a>
                  )}
                  <button
                    onClick={() => generateRecoveryEmail(cart)}
                    disabled={drafting === cart.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-brand-dark/20 hover:bg-brand/30 text-brand text-xs font-medium border border-brand-dark/30 disabled:opacity-50 transition-colors"
                  >
                    {drafting === cart.id ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
                    Recovery email
                  </button>
                </div>
              </div>

              {/* Draft email */}
              {showDraft === cart.id && draftEmails[cart.id] && (
                <div className="border-t border-slate-200 px-4 py-3 space-y-2 bg-slate-50">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-brand/50 flex items-center gap-1"><Sparkles size={10} /> AI Recovery Email</span>
                    <div className="flex items-center gap-2">
                      <button onClick={() => copyToClipboard(draftEmails[cart.id])} className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-800 transition-colors">
                        <Copy size={10} /> Copy
                      </button>
                      <button onClick={() => setShowDraft(null)} className="text-slate-600 hover:text-slate-400"><X size={12} /></button>
                    </div>
                  </div>
                  <pre className="text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed bg-slate-50 rounded-xl p-3 border border-slate-200">
                    {draftEmails[cart.id]}
                  </pre>
                  <button
                    onClick={() => generateRecoveryEmail(cart)}
                    className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-700 transition-colors"
                  >
                    <RotateCcw size={10} /> Regenerate
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Discounts tab ─────────────────────────────────────────────────────────────

function DiscountsTab() {
  const [discounts, setDiscounts] = useState<(ShopifyPriceRule & { codes?: { code: string; usage_count: number }[] })[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [genCode, setGenCode] = useState(false);

  const [form, setForm] = useState({
    code: "", valueType: "percentage" as "percentage" | "fixed_amount",
    value: "", minPurchase: "", usageLimit: "", endsAt: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await shopGet({ action: "discounts" }) as { discounts: typeof discounts };
      setDiscounts(d.discounts ?? []);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function generateCode() {
    setGenCode(true);
    try {
      const adjectives = ["FLASH", "MEGA", "SUPER", "EPIC", "SUMMER", "WINTER", "VIP", "WELCOME", "SAVE"];
      const rand = adjectives[Math.floor(Math.random() * adjectives.length)];
      const num = Math.floor(Math.random() * 90) + 10;
      setForm((f) => ({ ...f, code: `${rand}${num}` }));
    } finally { setGenCode(false); }
  }

  async function createDiscount() {
    if (!form.code || !form.value) { toast.error("Code and value required"); return; }
    setCreating(true);
    try {
      await shopPost({
        action: "create_discount",
        code: form.code,
        valueType: form.valueType,
        value: parseFloat(form.value),
        ...(form.minPurchase ? { minPurchase: parseFloat(form.minPurchase) } : {}),
        ...(form.usageLimit ? { usageLimit: parseInt(form.usageLimit) } : {}),
        ...(form.endsAt ? { endsAt: form.endsAt } : {}),
      });
      toast.success("Discount created!");
      setShowCreate(false);
      setForm({ code: "", valueType: "percentage", value: "", minPurchase: "", usageLimit: "", endsAt: "" });
      await load();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setCreating(false); }
  }

  async function deleteDiscount(id: number) {
    if (!confirm("Delete this discount?")) return;
    setDeleting(id);
    try {
      await shopPost({ action: "delete_discount", priceRuleId: String(id) });
      toast.success("Deleted");
      await load();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setDeleting(null); }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
        <p className="text-xs text-slate-500">{discounts.length} price rules</p>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold transition-colors"
        >
          <Plus size={12} /> New discount
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="px-4 py-4 border-b border-slate-200 bg-slate-50">
          <p className="text-sm font-semibold mb-3">Create Discount Code</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {/* Code */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Code</label>
              <div className="flex items-center gap-1">
                <input
                  value={form.code}
                  onChange={(e) => setForm((f) => ({ ...f, code: e.target.value.toUpperCase() }))}
                  placeholder="SAVE20"
                  className="flex-1 bg-slate-100 text-sm text-slate-800 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-200 font-mono uppercase"
                />
                <button onClick={generateCode} disabled={genCode} className="p-2 rounded-xl bg-slate-100 border border-slate-200 text-slate-400 hover:text-brand transition-colors" title="Generate code">
                  <Zap size={12} />
                </button>
              </div>
            </div>
            {/* Type */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Type</label>
              <div className="flex items-center gap-1 bg-slate-100 border border-slate-200 rounded-xl p-0.5">
                <button onClick={() => setForm((f) => ({ ...f, valueType: "percentage" }))} className={cn("flex-1 py-1.5 rounded-lg text-xs font-medium flex items-center justify-center gap-1 transition-colors", form.valueType === "percentage" ? "bg-brand-dark text-white" : "text-slate-400")}>
                  <Percent size={10} /> %
                </button>
                <button onClick={() => setForm((f) => ({ ...f, valueType: "fixed_amount" }))} className={cn("flex-1 py-1.5 rounded-lg text-xs font-medium flex items-center justify-center gap-1 transition-colors", form.valueType === "fixed_amount" ? "bg-brand-dark text-white" : "text-slate-400")}>
                  <DollarSign size={10} /> Fixed
                </button>
              </div>
            </div>
            {/* Value */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Value ({form.valueType === "percentage" ? "%" : "$"})</label>
              <input value={form.value} onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))} placeholder="20" type="number" className="w-full bg-slate-100 text-sm text-slate-800 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-200" />
            </div>
            {/* Min purchase */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Min purchase ($)</label>
              <input value={form.minPurchase} onChange={(e) => setForm((f) => ({ ...f, minPurchase: e.target.value }))} placeholder="0" type="number" className="w-full bg-slate-100 text-sm text-slate-800 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-200" />
            </div>
            {/* Usage limit */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Usage limit</label>
              <input value={form.usageLimit} onChange={(e) => setForm((f) => ({ ...f, usageLimit: e.target.value }))} placeholder="Unlimited" type="number" className="w-full bg-slate-100 text-sm text-slate-800 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-200" />
            </div>
            {/* Expires */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Expires</label>
              <input value={form.endsAt} onChange={(e) => setForm((f) => ({ ...f, endsAt: e.target.value }))} type="date" className="w-full bg-slate-100 text-sm text-slate-800 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-200" />
            </div>
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-xl text-xs text-slate-400 hover:text-slate-900 transition-colors">Cancel</button>
            <button onClick={createDiscount} disabled={creating} className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold disabled:opacity-50 transition-colors">
              {creating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
              Create
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center"><Loader2 size={22} className="animate-spin text-slate-600" /></div>
      ) : discounts.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-600">
          <Tag size={28} />
          <p className="text-sm">No discount codes yet</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-white border-b border-slate-200">
              <tr>
                {["Code", "Discount", "Used / Limit", "Expires", "Created", ""].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {discounts.map((d) => {
                const code = d.codes?.[0]?.code ?? d.title;
                const isExpired = d.ends_at && new Date(d.ends_at) < new Date();
                return (
                  <tr key={d.id} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-brand bg-brand-ink/50 px-2 py-0.5 rounded-lg border border-brand-ink/50">{code}</span>
                        <button onClick={() => copyToClipboard(code)} className="text-slate-600 hover:text-slate-700 transition-colors"><Copy size={11} /></button>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-semibold text-emerald-600">
                      {d.value_type === "percentage" ? `${Math.abs(parseFloat(d.value))}% off` : `${fmtMoney(Math.abs(parseFloat(d.value)))} off`}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {d.times_used} / {d.usage_limit ?? "∞"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {d.ends_at ? (
                        <span className={cn(isExpired && "text-rose-600")}>{fmtDate(d.ends_at)}{isExpired && " (expired)"}</span>
                      ) : "No expiry"}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{fmtDate(d.created_at)}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => deleteDiscount(d.id)}
                        disabled={deleting === d.id}
                        className="p-1.5 rounded-lg text-slate-600 hover:text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-50"
                      >
                        {deleting === d.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ShopifyPage() {
  return (
    <Suspense fallback={
      <div className="flex-1 flex items-center justify-center bg-white">
        <Loader2 size={24} className="animate-spin text-slate-600" />
      </div>
    }>
      <ShopifyPageInner />
    </Suspense>
  );
}

function ShopifyPageInner() {
  const [tab, setTab] = useState<Tab>("overview");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [period, setPeriod] = useState<Period>("month");
  const [connecting, setConnecting] = useState(false);
  const [shop, setShop] = useState("");
  const searchParams = useSearchParams();

  useEffect(() => {
    shopGet({ action: "overview", period: "today" })
      .then((d: { connected?: boolean }) => setConnected(d.connected ?? false))
      .catch(() => setConnected(false));
  }, []);

  // Handle OAuth callback redirect params
  useEffect(() => {
    const ok  = searchParams.get("shopify_connected");
    const err = searchParams.get("shopify_error");
    if (ok === "1") {
      toast.success("Shopify connected!");
      setConnected(true);
      window.history.replaceState({}, "", "/dashboard/shopify");
    } else if (err) {
      const msgs: Record<string, string> = {
        invalid_hmac:       "Security check failed — try connecting again.",
        invalid_state:      "Session expired — try connecting again.",
        token_exchange_failed: "Couldn't reach Shopify — check your connection.",
        no_token:           "Shopify didn't return a token — try again.",
        app_not_configured: "Shopify app is not configured on the server.",
      };
      toast.error(msgs[err] ?? `Shopify error: ${err}`);
      window.history.replaceState({}, "", "/dashboard/shopify");
    }
  }, [searchParams]);

  async function connectViaOAuth() {
    const storeName = shop.trim().replace(/\.myshopify\.com.*/, "");
    if (!storeName) { toast.error("Enter your store name."); return; }
    setConnecting(true);
    try {
      const authToken = getToken();
      const res = await fetch(`/api/shopify/oauth/start?shop=${encodeURIComponent(storeName)}`, {
        headers: { Authorization: `Bearer ${authToken ?? ""}` },
      });
      const data = await res.json().catch(() => ({}) as Record<string, unknown>) as { auth_url?: string; detail?: string };
      if (!res.ok || !data.auth_url) {
        toast.error(typeof data.detail === "string" ? data.detail : "Couldn't start Shopify OAuth. Is the app configured?");
        setConnecting(false);
        return;
      }
      // Open OAuth in popup
      const popup = window.open(data.auth_url, "shopify-oauth", "width=1024,height=768,noopener,noreferrer");
      if (!popup) { window.location.href = data.auth_url; return; }

      toast.success("Approve access in the Shopify popup, then return here.");

      // Poll until popup closes, then recheck connection
      await new Promise<void>((resolve) => {
        const poll = window.setInterval(() => {
          if (popup.closed) { window.clearInterval(poll); resolve(); }
        }, 800);
      });
      await new Promise((r) => setTimeout(r, 1200));
      const check = await shopGet({ action: "overview", period: "today" }).catch(() => ({ connected: false })) as { connected?: boolean };
      if (check.connected) {
        setConnected(true);
        toast.success("Shopify connected!");
      } else {
        toast.info("Didn't detect a connection yet — refresh the page after approving.");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "OAuth failed");
    } finally {
      setConnecting(false);
    }
  }


  if (connected === null) {
    return (
      <div className="flex-1 flex items-center justify-center bg-white">
        <Loader2 size={24} className="animate-spin text-slate-600" />
      </div>
    );
  }

  if (connected === false) {
    return (
      <div className="flex-1 overflow-y-auto bg-white text-slate-900">
        <NoShopify
          shop={shop} setShop={setShop}
          onOAuth={connectViaOAuth}
          connecting={connecting}
        />
      </div>
    );
  }

  const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "orders", label: "Orders", icon: ShoppingCart },
    { id: "products", label: "Products", icon: Package },
    { id: "customers", label: "Customers", icon: Users },
    { id: "abandoned", label: "Abandoned", icon: AlertTriangle },
    { id: "discounts", label: "Discounts", icon: Tag },
    { id: "growth", label: "Growth", icon: TrendingUp },
  ];

  return (
    <div className="flex flex-col h-full bg-slate-50 text-slate-900 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 border-b border-slate-200 bg-white flex items-center gap-3">
        <div className="w-6 h-6 rounded-lg bg-brand/20 flex items-center justify-center">
          <ShoppingBag size={13} className="text-brand" />
        </div>
        <span className="font-semibold text-sm">Shopify</span>
        <span className="text-[10px] text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">Connected</span>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 bg-slate-50 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-3 text-xs font-medium whitespace-nowrap border-b-2 transition-colors",
              tab === id ? "text-brand border-brand" : "text-slate-500 border-transparent hover:text-slate-700"
            )}
          >
            <Icon size={12} />{label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {tab === "overview"   && <OverviewTab period={period} setPeriod={setPeriod} />}
        {tab === "orders"     && <OrdersTab />}
        {tab === "products"   && <ProductsTab />}
        {tab === "customers"  && <CustomersTab />}
        {tab === "abandoned"  && <AbandonedTab />}
        {tab === "discounts"  && <DiscountsTab />}
        {tab === "growth"     && <GrowthTab />}
      </div>
    </div>
  );
}


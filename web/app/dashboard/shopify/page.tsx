"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  return t ? { Authorization: `Bearer ${t}` } : {};
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
    paid: "bg-emerald-900/40 text-emerald-400 border-emerald-800/40",
    pending: "bg-amber-900/40 text-amber-400 border-amber-800/40",
    refunded: "bg-rose-900/40 text-rose-400 border-rose-800/40",
    partially_refunded: "bg-orange-900/40 text-orange-400 border-orange-800/40",
    voided: "bg-slate-800 text-slate-500 border-slate-700",
    authorized: "bg-blue-900/40 text-blue-400 border-blue-800/40",
  };
  return (
    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border capitalize", map[status] ?? "bg-slate-800 text-slate-400 border-slate-700")}>
      {status?.replace(/_/g, " ")}
    </span>
  );
}

function FulfillmentBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-amber-900/40 text-amber-400 border-amber-800/40">Unfulfilled</span>;
  if (status === "fulfilled") return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-emerald-900/40 text-emerald-400 border-emerald-800/40">Fulfilled</span>;
  if (status === "partial") return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-blue-900/40 text-blue-400 border-blue-800/40">Partial</span>;
  return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-slate-800 text-slate-400 border-slate-700 capitalize">{status}</span>;
}

function StockBadge({ qty }: { qty: number }) {
  if (qty <= 0) return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-900/40 text-rose-400 border border-rose-800/40">Out of stock</span>;
  if (qty < 5) return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-rose-900/40 text-rose-400 border border-rose-800/40">Critical: {qty}</span>;
  if (qty < 20) return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400 border border-amber-800/40">Low: {qty}</span>;
  return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-900/40 text-emerald-400 border border-emerald-800/40">{qty} in stock</span>;
}

// ── No connection ─────────────────────────────────────────────────────────────

function NoShopify() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-5 text-center px-8 py-16">
      <div className="w-16 h-16 rounded-2xl bg-[#96bf48]/10 border border-[#96bf48]/20 flex items-center justify-center">
        <ShoppingBag size={28} className="text-[#96bf48]" />
      </div>
      <div>
        <p className="font-bold text-slate-200 text-base">Connect your Shopify store</p>
        <p className="text-sm text-slate-500 mt-2 max-w-xs leading-relaxed">
          Get orders, inventory, customers, abandoned carts, and AI-powered recovery tools — all in one place.
        </p>
      </div>
      <a
        href="/dashboard/integrations"
        className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#96bf48] hover:bg-[#7da33a] text-white text-sm font-semibold transition-colors"
      >
        <Zap size={14} /> Connect Shopify
      </a>
      <div className="grid grid-cols-2 gap-3 text-left mt-2 max-w-sm">
        {[
          ["📦", "Order management", "Fulfill, cancel, track every order"],
          ["📉", "Abandoned cart recovery", "AI-written recovery emails"],
          ["🏷️", "Discount codes", "Create promos with one click"],
          ["📊", "Revenue analytics", "Daily charts, top products, AOV"],
          ["🔔", "Low stock alerts", "Never run out unexpectedly"],
          ["👥", "Customer LTV", "Know your best customers"],
        ].map(([icon, title, desc]) => (
          <div key={title} className="bg-slate-800/60 rounded-xl p-3 border border-slate-700/50">
            <p className="text-sm mb-1">{icon} <span className="font-medium text-slate-200">{title}</span></p>
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
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">{label}</span>
        <Icon size={14} className={color} />
      </div>
      <p className="text-xl font-bold text-slate-100">{value}</p>
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
            className={cn("text-xs px-3 py-1.5 rounded-lg capitalize font-medium transition-colors", period === p ? "bg-brand-dark text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700")}
          >
            {p === "today" ? "Today" : p === "week" ? "7 days" : "This month"}
          </button>
        ))}
        <button onClick={load} className="ml-auto p-1.5 text-slate-500 hover:text-slate-300 transition-colors"><RefreshCw size={13} /></button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon={DollarSign} label="Revenue" value={fmtMoney(stats.revenue)} sub={`${stats.orderCount} orders`} color="text-emerald-400" />
        <StatCard icon={ShoppingCart} label="Avg Order Value" value={fmtMoney(stats.aov)} sub="per order" color="text-brand" />
        <StatCard icon={CheckCircle2} label="Fulfillment Rate" value={`${stats.fulfillmentRate}%`} sub={`${stats.unfulfilled} pending`} color="text-blue-400" />
        <StatCard icon={TrendingDown} label="Refunds" value={String(stats.refunds)} sub={`${stats.pending} payment pending`} color="text-rose-400" />
      </div>

      {/* Secondary row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">Products</p>
          <p className="text-lg font-bold">{stats.productCount}</p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">Customers</p>
          <p className="text-lg font-bold">{stats.customerCount.toLocaleString()}</p>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">Unfulfilled</p>
          <p className={cn("text-lg font-bold", stats.unfulfilled > 0 ? "text-amber-400" : "text-slate-300")}>{stats.unfulfilled}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Revenue chart */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <p className="text-xs font-semibold text-slate-400 mb-3 flex items-center gap-1.5"><BarChart3 size={12} /> Revenue by day</p>
          <RevenueChart data={revenueByDay} />
        </div>

        {/* Top products */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <p className="text-xs font-semibold text-slate-400 mb-3 flex items-center gap-1.5"><TrendingUp size={12} /> Top products</p>
          {topProducts.length === 0 ? (
            <p className="text-xs text-slate-600 py-4 text-center">No data</p>
          ) : (
            <div className="space-y-2.5">
              {topProducts.map((p, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-600 w-4">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-slate-300 truncate">{p.title}</p>
                    <p className="text-[10px] text-slate-600">{p.units} units</p>
                  </div>
                  <span className="text-xs font-semibold text-emerald-400">{fmtMoney(p.revenue)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent orders */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <p className="text-xs font-semibold text-slate-400">Recent orders</p>
          <span className="text-[10px] text-slate-600">{recentOrders.length} shown</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-800">
                {["Order", "Customer", "Items", "Total", "Payment", "Fulfillment", "Date"].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentOrders.map((o) => (
                <tr key={o.id} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-2.5 font-semibold text-brand">{o.name}</td>
                  <td className="px-4 py-2.5 text-slate-300">{o.customer ? `${o.customer.first_name} ${o.customer.last_name}` : o.email ?? "—"}</td>
                  <td className="px-4 py-2.5 text-slate-500">{o.line_items?.length ?? 0}</td>
                  <td className="px-4 py-2.5 font-semibold text-slate-200">{fmtMoney(o.total_price, o.currency)}</td>
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

function OrdersTab() {
  const [orders, setOrders] = useState<ShopifyOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [fulfillmentFilter, setFulfillmentFilter] = useState("any");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [selected, setSelected] = useState<ShopifyOrder | null>(null);
  const [acting, setActing] = useState<string | null>(null);

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
        <div className="px-4 py-3 border-b border-slate-800 flex items-center gap-2 flex-wrap">
          <form onSubmit={(e) => { e.preventDefault(); setSearch(searchInput); }} className="flex items-center gap-2 bg-slate-800 rounded-xl px-3 py-1.5 border border-slate-700">
            <Search size={12} className="text-slate-500" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Order # or customer…"
              className="bg-transparent text-xs text-slate-200 placeholder-slate-500 outline-none w-40"
            />
            {searchInput && <button type="button" onClick={() => { setSearchInput(""); setSearch(""); }}><X size={11} className="text-slate-500" /></button>}
          </form>
          <div className="flex items-center bg-slate-800 rounded-xl p-0.5 gap-0.5">
            {filterButtons.map((f) => (
              <button
                key={f.id}
                onClick={() => setFulfillmentFilter(f.id)}
                className={cn("text-xs px-3 py-1.5 rounded-lg font-medium transition-colors", fulfillmentFilter === f.id ? "bg-brand-dark text-white" : "text-slate-500 hover:text-slate-100")}
              >
                {f.label}
                {f.id === "unfulfilled" && unfulfilled > 0 && (
                  <span className="ml-1 text-[10px] bg-amber-500 text-white px-1 rounded-full">{unfulfilled}</span>
                )}
              </button>
            ))}
          </div>
          <button onClick={load} className="ml-auto p-1.5 text-slate-500 hover:text-slate-300 transition-colors"><RefreshCw size={13} /></button>
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
              <thead className="sticky top-0 bg-slate-950 border-b border-slate-800">
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
                    onClick={() => setSelected(selected?.id === o.id ? null : o)}
                    className={cn("border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors cursor-pointer", selected?.id === o.id && "bg-slate-800/50")}
                  >
                    <td className="px-4 py-3 font-semibold text-brand">{o.name}</td>
                    <td className="px-4 py-3">
                      <p className="text-slate-200">{o.customer ? `${o.customer.first_name} ${o.customer.last_name}` : "—"}</p>
                      <p className="text-[10px] text-slate-600">{o.email ?? o.customer?.email ?? ""}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-400">{o.line_items?.length ?? 0} item{o.line_items?.length !== 1 ? "s" : ""}</td>
                    <td className="px-4 py-3 font-semibold text-slate-200">{fmtMoney(o.total_price, o.currency)}</td>
                    <td className="px-4 py-3"><FinancialBadge status={o.financial_status} /></td>
                    <td className="px-4 py-3"><FulfillmentBadge status={o.fulfillment_status} /></td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{fmtDate(o.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        {!o.fulfillment_status && o.financial_status === "paid" && (
                          <button
                            onClick={(e) => { e.stopPropagation(); fulfill(o); }}
                            disabled={acting === String(o.id)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-700/30 hover:bg-emerald-700/50 text-emerald-400 text-[10px] font-medium border border-emerald-700/40 disabled:opacity-50 transition-colors"
                          >
                            {acting === String(o.id) ? <Loader2 size={9} className="animate-spin" /> : <Check size={9} />}
                            Fulfill
                          </button>
                        )}
                        {o.financial_status !== "refunded" && o.financial_status !== "voided" && !o.fulfillment_status && (
                          <button
                            onClick={(e) => { e.stopPropagation(); cancel(o); }}
                            disabled={acting === String(o.id)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-900/20 hover:bg-rose-900/40 text-rose-400 text-[10px] font-medium border border-rose-800/30 disabled:opacity-50 transition-colors"
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
        <div className="w-80 border-l border-slate-800 bg-slate-900 flex flex-col overflow-y-auto shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
            <span className="font-semibold text-sm">{selected.name}</span>
            <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-slate-100"><X size={14} /></button>
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
              <p className="text-sm font-medium text-slate-200">{selected.customer ? `${selected.customer.first_name} ${selected.customer.last_name}` : "Guest"}</p>
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
                  <div key={li.id} className="flex items-start gap-2 bg-slate-800/50 rounded-xl p-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-slate-200 font-medium truncate">{li.title}</p>
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
            <div className="border-t border-slate-800 pt-3 space-y-1.5">
              {parseFloat(selected.total_discounts ?? "0") > 0 && (
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Discount</span>
                  <span className="text-rose-400">-{fmtMoney(selected.total_discounts, selected.currency)}</span>
                </div>
              )}
              <div className="flex justify-between text-sm font-bold">
                <span className="text-slate-300">Total</span>
                <span>{fmtMoney(selected.total_price, selected.currency)}</span>
              </div>
            </div>
            {/* Shipping */}
            {selected.shipping_address && (
              <div>
                <p className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Ship to</p>
                <p className="text-xs text-slate-300">{selected.shipping_address.first_name} {selected.shipping_address.last_name}</p>
                <p className="text-[11px] text-slate-500">{selected.shipping_address.address1}</p>
                <p className="text-[11px] text-slate-500">{selected.shipping_address.city}, {selected.shipping_address.country} {selected.shipping_address.zip}</p>
              </div>
            )}
            {/* Note */}
            {selected.note && (
              <div>
                <p className="text-[10px] text-slate-500 mb-1 uppercase tracking-wider">Note</p>
                <p className="text-xs text-slate-400 bg-slate-800/50 rounded-xl p-2">{selected.note}</p>
              </div>
            )}
            <p className="text-[10px] text-slate-600">Placed {fmtDateTime(selected.created_at)}</p>
          </div>
          {/* Actions */}
          <div className="px-4 pb-4 space-y-2 border-t border-slate-800 pt-3">
            {!selected.fulfillment_status && selected.financial_status === "paid" && (
              <button
                onClick={() => fulfill(selected)}
                disabled={acting === String(selected.id)}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-semibold disabled:opacity-50 transition-colors"
              >
                {acting === String(selected.id) ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                Mark as Fulfilled
              </button>
            )}
            {selected.financial_status !== "refunded" && !selected.fulfillment_status && (
              <button
                onClick={() => cancel(selected)}
                disabled={acting === String(selected.id)}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-slate-800 hover:bg-rose-900/30 text-rose-400 text-xs font-medium border border-slate-700 hover:border-rose-800/40 disabled:opacity-50 transition-colors"
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
  const data = await r.json() as { draft?: string; content?: string };
  const text = data.draft ?? data.content ?? "";
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

  // ── AI finder state ─────────────────────────────────────────────────────────
  const [finderOpen, setFinderOpen] = useState(false);
  const [category, setCategory] = useState("");
  const [keywords, setKeywords] = useState("");
  const [count, setCount] = useState<number>(8);
  const [priceRange, setPriceRange] = useState("$20–$50");
  const [generating, setGenerating] = useState(false);
  const [suggestions, setSuggestions] = useState<ProductSuggestion[]>([]);
  const [addingIdx, setAddingIdx] = useState<number | null>(null);
  const [addedIdxs, setAddedIdxs] = useState<Set<number>>(new Set());

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
        <div className="px-4 py-2.5 bg-amber-900/20 border-b border-amber-800/30 flex items-center gap-2">
          <AlertTriangle size={13} className="text-amber-400" />
          <span className="text-xs text-amber-300">
            {outOfStock > 0 && <span className="font-semibold">{outOfStock} out of stock</span>}
            {outOfStock > 0 && lowStock > outOfStock && " · "}
            {lowStock > outOfStock && <span>{lowStock - outOfStock} running low</span>}
          </span>
        </div>
      )}

      {/* Toolbar */}
      <div className="px-4 py-3 border-b border-slate-800 flex items-center gap-2">
        <div className="flex items-center gap-2 bg-slate-800 rounded-xl px-3 py-1.5 border border-slate-700">
          <Search size={12} className="text-slate-500" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search products…" className="bg-transparent text-xs text-slate-200 placeholder-slate-500 outline-none w-36" />
        </div>
        <span className="text-xs text-slate-600">{filtered.length} products</span>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={load} className="p-1.5 text-slate-500 hover:text-slate-300"><RefreshCw size={13} /></button>
          <button
            onClick={() => { setFinderOpen((o) => !o); setSuggestions([]); }}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors border",
              finderOpen
                ? "bg-brand-dark text-white border-brand"
                : "bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700"
            )}
          >
            <Wand2 size={12} />
            {finderOpen ? "Hide Finder" : "AI Product Finder"}
          </button>
        </div>
      </div>

      {/* AI Product Finder Panel */}
      {finderOpen && (
        <div className="border-b border-slate-800 bg-slate-900/60">
          {/* Config row */}
          <div className="px-4 pt-4 pb-3 flex flex-wrap gap-3 items-end">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Store Category / Niche</label>
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="e.g. Men's Streetwear, Organic Skincare, Home Gym..."
                className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:ring-1 focus:ring-brand w-64"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Style / Keywords</label>
              <input
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                placeholder="e.g. minimalist, eco-friendly, premium..."
                className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:ring-1 focus:ring-brand w-52"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Price Range</label>
              <select
                value={priceRange}
                onChange={(e) => setPriceRange(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-brand"
              >
                {PRICE_RANGES.map((r) => <option key={r}>{r}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">How many</label>
              <select
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-brand"
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
          {generating && (
            <div className="px-4 pb-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
              {Array.from({ length: count > 8 ? 4 : count > 4 ? 3 : 2 }).map((_, i) => (
                <div key={i} className="bg-slate-800/60 rounded-2xl p-4 animate-pulse flex flex-col gap-2">
                  <div className="h-24 bg-slate-700 rounded-xl" />
                  <div className="h-3 bg-slate-700 rounded w-3/4" />
                  <div className="h-2 bg-slate-700 rounded w-1/2" />
                  <div className="h-2 bg-slate-700 rounded w-full" />
                  <div className="h-2 bg-slate-700 rounded w-2/3" />
                </div>
              ))}
            </div>
          )}

          {/* Suggestions grid */}
          {!generating && suggestions.length > 0 && (
            <div className="px-4 pb-4">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs text-slate-400">
                  <span className="font-semibold text-slate-200">{suggestions.length}</span> products found for <span className="text-brand">{category}</span>
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
                        "bg-slate-800/60 border rounded-2xl p-3 flex flex-col gap-2 transition-all",
                        added ? "border-emerald-800/60 bg-emerald-950/20" : "border-slate-700/60 hover:border-slate-600"
                      )}
                    >
                      {/* Image placeholder with category icon */}
                      <div className="h-20 bg-slate-700/60 rounded-xl flex items-center justify-center relative overflow-hidden">
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
                          <div className="absolute inset-0 bg-emerald-950/60 flex items-center justify-center rounded-xl">
                            <CheckCircle2 size={20} className="text-emerald-400" />
                          </div>
                        )}
                      </div>

                      {/* Product info */}
                      <div className="flex-1">
                        <p className="text-xs font-semibold text-slate-200 leading-tight mb-0.5 line-clamp-2">{s.title}</p>
                        {s.vendor && <p className="text-[10px] text-slate-500 mb-1">{s.vendor}</p>}
                        <p className="text-[10px] text-slate-400 leading-relaxed line-clamp-3">{s.description}</p>
                      </div>

                      {/* Tags */}
                      {s.tags && (
                        <div className="flex flex-wrap gap-1">
                          {s.tags.split(",").slice(0, 3).map((t) => (
                            <span key={t} className="text-[9px] bg-slate-700/60 text-slate-500 px-1.5 py-0.5 rounded-full">
                              {t.trim()}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Price + variants */}
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-200">${s.price}</span>
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
                            ? "bg-emerald-900/30 text-emerald-400 border border-emerald-800/40 cursor-default"
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
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Empty state after generate with no results */}
          {!generating && suggestions.length === 0 && (
            <div className="px-4 pb-5 flex flex-col items-center gap-2 text-center py-6">
              <Sparkles size={24} className="text-brand mb-1" />
              <p className="text-sm font-medium text-slate-300">AI Product Research</p>
              <p className="text-xs text-slate-500 max-w-xs">
                Tell the AI your store niche and it will suggest ready-to-sell products with descriptions, pricing, and tags — add them to Shopify with one click.
              </p>
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
            <thead className="sticky top-0 bg-slate-950 border-b border-slate-800">
              <tr>
                {["Product", "SKU", "Price", "Stock", "Status", "Action"].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((product) =>
                product.variants.map((variant, vi) => (
                  <tr key={variant.id} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                    <td className="px-4 py-3">
                      {vi === 0 ? (
                        <div className="flex items-center gap-2">
                          {product.image?.src && (
                            <img src={product.image.src} alt="" className="w-8 h-8 rounded-lg object-cover bg-slate-800" />
                          )}
                          <div>
                            <p className="font-medium text-slate-200">{product.title}</p>
                            {product.product_type && <p className="text-[10px] text-slate-600">{product.product_type}</p>}
                          </div>
                        </div>
                      ) : (
                        <p className="text-slate-500 pl-10">↳ {variant.title}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-500 font-mono">{variant.sku || "—"}</td>
                    <td className="px-4 py-3 font-semibold text-slate-200">{fmtMoney(variant.price)}</td>
                    <td className="px-4 py-3">
                      {editing?.variantId === variant.id ? (
                        <div className="flex items-center gap-1.5">
                          <input
                            value={newQty}
                            onChange={(e) => setNewQty(e.target.value)}
                            type="number"
                            autoFocus
                            className="w-16 bg-slate-700 text-xs text-slate-200 rounded-lg px-2 py-1 outline-none focus:ring-1 focus:ring-brand border border-slate-600"
                          />
                          <button onClick={updateInventory} disabled={saving} className="p-1 text-emerald-400 hover:text-emerald-300 disabled:opacity-50">
                            {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                          </button>
                          <button onClick={() => { setEditing(null); setNewQty(""); }} className="p-1 text-slate-500 hover:text-slate-300"><X size={11} /></button>
                        </div>
                      ) : (
                        <StockBadge qty={variant.inventory_quantity} />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] font-medium capitalize", product.status === "active" ? "text-emerald-400" : "text-slate-500")}>
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
        <div className="px-4 py-3 border-b border-slate-800 flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-2 bg-slate-800 rounded-xl px-3 py-1.5 border border-slate-700">
            <Search size={12} className="text-slate-500" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search customers…" className="bg-transparent text-xs text-slate-200 placeholder-slate-500 outline-none w-36" />
          </div>
          <div className="flex items-center bg-slate-800 rounded-xl p-0.5 gap-0.5">
            {([
              ["all", "All", customers.length],
              ["vip", "⭐ VIP", vipCount],
              ["new", "New", newCount],
              ["at-risk", "At-risk", atRiskCount],
            ] as [CustomerSegment, string, number][]).map(([id, label, count]) => (
              <button
                key={id}
                onClick={() => setSegment(id)}
                className={cn("text-xs px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center gap-1", segment === id ? "bg-brand-dark text-white" : "text-slate-500 hover:text-slate-100")}
              >
                {label}
                <span className={cn("text-[10px] px-1 rounded-full", segment === id ? "bg-white/20 text-white" : "bg-slate-700 text-slate-400")}>{count}</span>
              </button>
            ))}
          </div>
          <button onClick={load} className="ml-auto p-1.5 text-slate-500 hover:text-slate-300"><RefreshCw size={13} /></button>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center"><Loader2 size={22} className="animate-spin text-slate-600" /></div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-950 border-b border-slate-800">
                <tr>
                  {["Customer", "Location", "Orders", "Lifetime Value", "Last Order", "Status"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((c, i) => {
                  const isVip = c.orders_count >= 3 || parseFloat(c.total_spent ?? "0") >= 500;
                  const daysSince = (Date.now() - new Date(c.updated_at).getTime()) / 86400000;
                  const isAtRisk = daysSince > 90 && c.orders_count > 1;
                  return (
                    <tr
                      key={c.id}
                      onClick={() => setSelected(selected?.id === c.id ? null : c)}
                      className={cn("border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors cursor-pointer", selected?.id === c.id && "bg-slate-800/50")}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-full bg-brand-dark/30 flex items-center justify-center text-[10px] font-bold text-brand shrink-0">
                            {(c.first_name?.[0] ?? c.email?.[0] ?? "?").toUpperCase()}
                          </div>
                          <div>
                            <p className="font-medium text-slate-200">{c.first_name} {c.last_name}</p>
                            <p className="text-[10px] text-slate-500">{c.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{c.default_address?.city ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-300">{c.orders_count}</td>
                      <td className="px-4 py-3 font-semibold text-emerald-400">{fmtMoney(c.total_spent)}</td>
                      <td className="px-4 py-3 text-slate-500">{c.last_order_name ?? fmtDate(c.updated_at)}</td>
                      <td className="px-4 py-3">
                        {isVip ? <span className="text-[10px] font-semibold text-amber-400 bg-amber-900/30 px-2 py-0.5 rounded-full border border-amber-800/30">⭐ VIP</span>
                          : isAtRisk ? <span className="text-[10px] font-semibold text-rose-400 bg-rose-900/30 px-2 py-0.5 rounded-full border border-rose-800/30">At-risk</span>
                          : c.orders_count === 1 ? <span className="text-[10px] font-semibold text-blue-400 bg-blue-900/30 px-2 py-0.5 rounded-full border border-blue-800/30">New</span>
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
        <div className="w-72 border-l border-slate-800 bg-slate-900 flex flex-col overflow-y-auto shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
            <span className="font-semibold text-sm">{selected.first_name} {selected.last_name}</span>
            <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-slate-100"><X size={14} /></button>
          </div>
          <div className="px-4 py-4 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-slate-800/50 rounded-xl p-3 text-center">
                <p className="text-[10px] text-slate-500">Orders</p>
                <p className="text-lg font-bold">{selected.orders_count}</p>
              </div>
              <div className="bg-slate-800/50 rounded-xl p-3 text-center">
                <p className="text-[10px] text-slate-500">Lifetime value</p>
                <p className="text-sm font-bold text-emerald-400">{fmtMoney(selected.total_spent)}</p>
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
      <div className="px-4 py-3 border-b border-slate-800 flex items-center gap-4">
        <div>
          <span className="text-xs text-slate-500">Abandoned carts: </span>
          <span className="text-sm font-bold text-slate-200">{carts.length}</span>
        </div>
        <div>
          <span className="text-xs text-slate-500">Recoverable value: </span>
          <span className="text-sm font-bold text-amber-400">{fmtMoney(totalValue)}</span>
        </div>
        <button onClick={load} className="ml-auto p-1.5 text-slate-500 hover:text-slate-300"><RefreshCw size={13} /></button>
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
            <div key={cart.id} className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-slate-200">{cart.email}</p>
                    <span className="text-[10px] text-amber-400 bg-amber-900/30 px-2 py-0.5 rounded-full border border-amber-800/30">
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
                    <a href={cart.abandoned_checkout_url} target="_blank" rel="noopener noreferrer" className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors" title="Open checkout">
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
                <div className="border-t border-slate-800 px-4 py-3 space-y-2 bg-slate-800/30">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-brand/50 flex items-center gap-1"><Sparkles size={10} /> AI Recovery Email</span>
                    <div className="flex items-center gap-2">
                      <button onClick={() => copyToClipboard(draftEmails[cart.id])} className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-200 transition-colors">
                        <Copy size={10} /> Copy
                      </button>
                      <button onClick={() => setShowDraft(null)} className="text-slate-600 hover:text-slate-400"><X size={12} /></button>
                    </div>
                  </div>
                  <pre className="text-xs text-slate-300 whitespace-pre-wrap font-sans leading-relaxed bg-slate-900/50 rounded-xl p-3 border border-slate-800">
                    {draftEmails[cart.id]}
                  </pre>
                  <button
                    onClick={() => generateRecoveryEmail(cart)}
                    className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
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
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
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
        <div className="px-4 py-4 border-b border-slate-800 bg-slate-900/50">
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
                  className="flex-1 bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700 font-mono uppercase"
                />
                <button onClick={generateCode} disabled={genCode} className="p-2 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-brand transition-colors" title="Generate code">
                  <Zap size={12} />
                </button>
              </div>
            </div>
            {/* Type */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Type</label>
              <div className="flex items-center gap-1 bg-slate-800 border border-slate-700 rounded-xl p-0.5">
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
              <input value={form.value} onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))} placeholder="20" type="number" className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700" />
            </div>
            {/* Min purchase */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Min purchase ($)</label>
              <input value={form.minPurchase} onChange={(e) => setForm((f) => ({ ...f, minPurchase: e.target.value }))} placeholder="0" type="number" className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700" />
            </div>
            {/* Usage limit */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Usage limit</label>
              <input value={form.usageLimit} onChange={(e) => setForm((f) => ({ ...f, usageLimit: e.target.value }))} placeholder="Unlimited" type="number" className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700" />
            </div>
            {/* Expires */}
            <div>
              <label className="text-[10px] text-slate-500 mb-1 block">Expires</label>
              <input value={form.endsAt} onChange={(e) => setForm((f) => ({ ...f, endsAt: e.target.value }))} type="date" className="w-full bg-slate-800 text-sm text-slate-200 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700" />
            </div>
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-xl text-xs text-slate-400 hover:text-slate-100 transition-colors">Cancel</button>
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
            <thead className="sticky top-0 bg-slate-950 border-b border-slate-800">
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
                  <tr key={d.id} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-brand bg-brand-ink/50 px-2 py-0.5 rounded-lg border border-brand-ink/50">{code}</span>
                        <button onClick={() => copyToClipboard(code)} className="text-slate-600 hover:text-slate-300 transition-colors"><Copy size={11} /></button>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-semibold text-emerald-400">
                      {d.value_type === "percentage" ? `${Math.abs(parseFloat(d.value))}% off` : `${fmtMoney(Math.abs(parseFloat(d.value)))} off`}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {d.times_used} / {d.usage_limit ?? "∞"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {d.ends_at ? (
                        <span className={cn(isExpired && "text-rose-400")}>{fmtDate(d.ends_at)}{isExpired && " (expired)"}</span>
                      ) : "No expiry"}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{fmtDate(d.created_at)}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => deleteDiscount(d.id)}
                        disabled={deleting === d.id}
                        className="p-1.5 rounded-lg text-slate-600 hover:text-rose-400 hover:bg-rose-900/20 transition-colors disabled:opacity-50"
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
  const [tab, setTab] = useState<Tab>("overview");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [period, setPeriod] = useState<Period>("month");

  useEffect(() => {
    shopGet({ action: "overview", period: "today" })
      .then((d: { connected?: boolean }) => setConnected(d.connected ?? false))
      .catch(() => setConnected(false));
  }, []);

  if (connected === null) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-950">
        <Loader2 size={24} className="animate-spin text-slate-600" />
      </div>
    );
  }

  if (connected === false) {
    return (
      <div className="flex-1 overflow-y-auto bg-slate-950 text-slate-100">
        <NoShopify />
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
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 border-b border-slate-800 bg-slate-900/80 flex items-center gap-3">
        <div className="w-6 h-6 rounded-lg bg-[#96bf48]/20 flex items-center justify-center">
          <ShoppingBag size={13} className="text-[#96bf48]" />
        </div>
        <span className="font-semibold text-sm">Shopify</span>
        <span className="text-[10px] text-emerald-400 bg-emerald-900/30 px-2 py-0.5 rounded-full border border-emerald-800/30">Connected</span>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800 bg-slate-900/60 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-3 text-xs font-medium whitespace-nowrap border-b-2 transition-colors",
              tab === id ? "text-brand border-brand" : "text-slate-500 border-transparent hover:text-slate-300"
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

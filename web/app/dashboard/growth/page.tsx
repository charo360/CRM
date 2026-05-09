"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  TrendingUp, TrendingDown, Users, Bell, Zap, Target,
  RefreshCw, ArrowUpRight, Clock, CheckCircle, XCircle,
  Loader2, ChevronRight, BarChart2, Globe, Mic, Sparkles,
} from "lucide-react";
import Link from "next/link";

interface DigestData {
  generated_at: string;
  revenue: { today: number; yesterday: number; delta: number; orders_today: number };
  cold_customers: { count: number; items: { id: string; name: string }[] };
  top_products: { name: string; count: number }[];
  followups_due_today: { count: number; items: { customer_name: string; notes?: string }[] };
  overdue_followups: { count: number; items: { customer_name: string; days_overdue: number }[] };
  new_customers: { count: number; items: { id: string; name: string }[] };
}

export default function GrowthPage() {
  const { currency } = useBusiness();
  const [digest, setDigest] = useState<DigestData | null>(null);
  const [loading, setLoading] = useState(true);
  const [pulse, setPulse] = useState<string | null>(null);

  useEffect(() => { loadDigest(); loadPulse(); }, []);

  async function loadDigest() {
    setLoading(true);
    try {
      const data = await api.get<DigestData>("/growth/digest");
      setDigest(data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }

  async function loadPulse() {
    try {
      const data = await api.get<{ message: string }>("/growth/pulse/preview");
      setPulse(data.message || null);
    } catch { /* ignore */ }
  }

  const features = [
    { href: "/dashboard/action-mode", icon: Sparkles, label: "Action Mode", desc: "AI runs your business — finds funding, leads & handles admin", color: "text-amber-600", bg: "bg-amber-50", badge: "NEW" },
    { href: "/dashboard/growth/autopilot", icon: Zap, label: "Follow-up Autopilot", desc: "AI-drafted messages for cold leads — approve or skip", color: "text-amber-600", bg: "bg-amber-50" },
    { href: "/dashboard/growth/deal-room", icon: Target, label: "Deal Room", desc: "Share proposals with view tracking and e-sign", color: "text-blue-600", bg: "bg-blue-50" },
    { href: "/dashboard/growth/competitors", icon: Globe, label: "Competitor Intel", desc: "Weekly AI insights on your competitors", color: "text-purple-600", bg: "bg-purple-50" },
    { href: "/dashboard/growth/voice", icon: Mic, label: "Voice to Document", desc: "Record a voice note → AI generates a full document", color: "text-rose-600", bg: "bg-rose-50" },
    { href: "/dashboard/client-portal", icon: Users, label: "Client Portal", desc: "Clients view their invoices, proposals & orders", color: "text-green-600", bg: "bg-green-50" },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Growth Suite</h1>
          <p className="text-sm text-slate-500 mt-1">Your daily AI-powered business health dashboard</p>
        </div>
        <button onClick={loadDigest} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Live Pulse */}
      {pulse && (
        <div className="bg-slate-800 text-slate-100 rounded-xl px-5 py-3 text-sm font-medium flex items-center gap-2">
          <BarChart2 size={15} className="text-slate-400 shrink-0" />
          {pulse}
        </div>
      )}

      {/* Daily Digest */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse h-24" />
          ))}
        </div>
      ) : digest ? (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="Revenue Today"
              value={formatCurrency(digest.revenue.today, currency)}
              delta={digest.revenue.delta}
              currency={currency}
              icon={TrendingUp}
              color="text-emerald-600"
              bg="bg-emerald-50"
            />
            <StatCard
              label="Orders Today"
              value={String(digest.revenue.orders_today)}
              icon={BarChart2}
              color="text-blue-600"
              bg="bg-blue-50"
            />
            <StatCard
              label="Cold Customers"
              value={String(digest.cold_customers.count)}
              icon={Users}
              color="text-orange-600"
              bg="bg-orange-50"
              cta={{ label: "View Autopilot", href: "/dashboard/growth/autopilot" }}
            />
            <StatCard
              label="Follow-ups Due"
              value={String(digest.followups_due_today.count + digest.overdue_followups.count)}
              icon={Bell}
              color="text-rose-600"
              bg="bg-rose-50"
              cta={{ label: "View Follow-ups", href: "/dashboard/followups" }}
            />
          </div>

          {/* Middle row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Top products */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h3 className="font-semibold text-slate-800 mb-3 text-sm">🏆 Top Products This Month</h3>
              {digest.top_products.length > 0 ? (
                <ul className="space-y-2">
                  {digest.top_products.map((p, i) => (
                    <li key={i} className="flex items-center justify-between text-sm">
                      <span className="text-slate-700 truncate max-w-[160px]">{p.name}</span>
                      <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-medium">{p.count}x</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-400">No orders this month yet</p>
              )}
            </div>

            {/* Cold customers */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-slate-800 text-sm">❄️ Cold Customers (30+ days)</h3>
                <Link href="/dashboard/growth/autopilot" className="text-xs text-brand-dark hover:underline flex items-center gap-0.5">
                  Re-engage <ArrowUpRight size={11} />
                </Link>
              </div>
              {digest.cold_customers.items.length > 0 ? (
                <ul className="space-y-1.5">
                  {digest.cold_customers.items.map((c) => (
                    <li key={c.id} className="text-sm text-slate-700 flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-orange-400 shrink-0" />
                      {c.name}
                    </li>
                  ))}
                  {digest.cold_customers.count > 5 && (
                    <li className="text-xs text-slate-400">+{digest.cold_customers.count - 5} more</li>
                  )}
                </ul>
              ) : (
                <p className="text-sm text-slate-400">No cold customers 🎉</p>
              )}
            </div>

            {/* Overdue follow-ups */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-slate-800 text-sm">⚠️ Overdue Follow-ups</h3>
                <Link href="/dashboard/followups" className="text-xs text-brand-dark hover:underline flex items-center gap-0.5">
                  View all <ArrowUpRight size={11} />
                </Link>
              </div>
              {digest.overdue_followups.items.length > 0 ? (
                <ul className="space-y-1.5">
                  {digest.overdue_followups.items.map((fu, i) => (
                    <li key={i} className="text-sm text-slate-700 flex items-center justify-between">
                      <span className="truncate max-w-[140px]">{fu.customer_name}</span>
                      <span className="text-xs text-rose-500 font-medium shrink-0">{fu.days_overdue}d overdue</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-400">All caught up! ✅</p>
              )}
            </div>
          </div>

          {/* New customers */}
          {digest.new_customers.count > 0 && (
            <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4 flex items-center gap-4">
              <div className="w-9 h-9 bg-emerald-100 rounded-lg flex items-center justify-center shrink-0">
                <Users size={18} className="text-emerald-600" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-emerald-800">
                  🆕 {digest.new_customers.count} new customer{digest.new_customers.count !== 1 ? "s" : ""} in the last 48 hours
                </p>
                <p className="text-xs text-emerald-600 mt-0.5">
                  {digest.new_customers.items.map(c => c.name).join(", ")}
                  {digest.new_customers.count > 5 ? ` +${digest.new_customers.count - 5} more` : ""}
                </p>
              </div>
              <Link href="/dashboard/customers" className="text-xs text-emerald-700 font-medium hover:underline shrink-0 flex items-center gap-1">
                View <ArrowUpRight size={11} />
              </Link>
            </div>
          )}
        </>
      ) : null}

      {/* Feature cards */}
      <div>
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Growth Tools</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map(({ href, icon: Icon, label, desc, color, bg, badge }) => (
            <Link key={href} href={href}
              className="bg-white rounded-xl border border-slate-200 p-5 hover:border-brand/40 hover:shadow-sm transition-all group relative">
              {badge && (
                <span className="absolute top-3 right-3 text-[10px] bg-amber-100 text-amber-700 font-bold px-1.5 py-0.5 rounded-full">
                  {badge}
                </span>
              )}
              <div className={`w-9 h-9 ${bg} rounded-lg flex items-center justify-center mb-3`}>
                <Icon size={18} className={color} />
              </div>
              <p className="font-semibold text-slate-800 text-sm group-hover:text-brand-dark">{label}</p>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">{desc}</p>
              <div className="flex items-center gap-1 mt-3 text-xs text-brand-dark font-medium">
                Open <ChevronRight size={12} />
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, delta, currency, icon: Icon, color, bg, cta }: {
  label: string; value: string; delta?: number; currency?: string;
  icon: React.ElementType; color: string; bg: string;
  cta?: { label: string; href: string };
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-slate-500 font-medium">{label}</span>
        <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
          <Icon size={15} className={color} />
        </div>
      </div>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
      {delta !== undefined && (
        <p className={`text-xs mt-1 flex items-center gap-1 ${delta >= 0 ? "text-emerald-600" : "text-rose-500"}`}>
          {delta >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
          {delta >= 0 ? "+" : ""}{formatCurrency(delta, currency || "USD")} vs yesterday
        </p>
      )}
      {cta && (
        <Link href={cta.href} className="text-xs text-brand-dark hover:underline flex items-center gap-1 mt-2">
          {cta.label} <ArrowUpRight size={10} />
        </Link>
      )}
    </div>
  );
}

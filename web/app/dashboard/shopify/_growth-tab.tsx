"use client";

/**
 * Growth Intelligence tab — answers the real marketing questions:
 * CAC vs LTV, repeat rate, revenue at risk, channel attribution, trust audit.
 */

import { useCallback, useEffect, useState } from "react";
import {
  TrendingUp, TrendingDown, AlertTriangle, Sparkles, RefreshCw,
  Loader2, DollarSign, Users, Repeat2, ShoppingCart, Mail,
  CheckCircle2, XCircle, ArrowRight, Copy, RotateCcw, Zap,
  BarChart3, Target, Shield, Megaphone, MessageSquare, Hash, MapPinned,
} from "lucide-react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

type GrowthData = {
  connected: boolean;
  repeatRate: number;
  repeatCustomers: number;
  totalCustomers: number;
  atRiskCount: number;
  revenueAtRisk: number;
  avgLtv: number;
  aov: number;
  newCust: number;
  returningCust: number;
  channelRevenue: { channel: string; revenue: number }[];
  subscriberRate: number;
  subscribers: number;
  avgOrderGap: number | null;
  newCustomerTrend: { week: string; count: number }[];
};

type CACInputs = {
  adSpend: string;
  newCustomers: string;
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
  const t = getToken();
  const h: Record<string, string> = {};
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
}

async function shopGet(params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`/api/shopify?${qs}`, { headers: authHeaders() });
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

function fmt(n: number, currency = "USD") {
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
}

function pct(n: number) { return `${n}%`; }

// ── Score ring ────────────────────────────────────────────────────────────────

function ScoreRing({ score, label, size = 80 }: { score: number; label: string; size?: number }) {
  const r = (size / 2) - 8;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const color = score >= 70 ? "#10b981" : score >= 40 ? "#f59e0b" : "#f43f5e";
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e293b" strokeWidth={8} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={8}
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" />
      </svg>
      <div className="text-center -mt-12 mb-3">
        <p className="text-xl font-bold" style={{ color }}>{score}</p>
        <p className="text-[10px] text-slate-500">/100</p>
      </div>
      <p className="text-xs text-slate-400 text-center">{label}</p>
    </div>
  );
}

// ── Metric card ───────────────────────────────────────────────────────────────

function MCard({ icon: Icon, label, value, sub, color = "text-slate-400", alert = false }: {
  icon: React.ElementType; label: string; value: string; sub?: string; color?: string; alert?: boolean;
}) {
  return (
    <div className={cn("rounded-2xl border p-4 flex flex-col gap-2", alert ? "border-amber-800/40 bg-amber-900/10" : "border-slate-800 bg-slate-900")}>
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">{label}</span>
        <Icon size={13} className={color} />
      </div>
      <p className="text-xl font-bold">{value}</p>
      {sub && <p className="text-[11px] text-slate-600">{sub}</p>}
    </div>
  );
}

// ── CAC Calculator ────────────────────────────────────────────────────────────

function CACCalculator({ avgLtv, aov }: { avgLtv: number; aov: number }) {
  const [inputs, setInputs] = useState<CACInputs>({ adSpend: "", newCustomers: "" });

  const spend    = parseFloat(inputs.adSpend) || 0;
  const newCusts = parseFloat(inputs.newCustomers) || 0;
  const cac      = newCusts > 0 ? spend / newCusts : 0;
  const ltvCac   = cac > 0 && avgLtv > 0 ? avgLtv / cac : 0;
  const payback  = cac > 0 && aov > 0 ? Math.ceil(cac / aov) : 0;

  const ltvCacColor = ltvCac >= 3 ? "text-emerald-400" : ltvCac >= 1 ? "text-amber-400" : "text-rose-400";
  const ltvCacLabel = ltvCac >= 3 ? "Healthy — great ROI" : ltvCac >= 1 ? "Marginal — needs improvement" : cac > 0 ? "Losing money — fix now" : "Enter spend above";

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Target size={13} className="text-brand" />
        <p className="text-sm font-semibold">CAC vs LTV Calculator</p>
      </div>
      <p className="text-xs text-slate-500 leading-relaxed">
        The golden ratio is <span className="text-emerald-400 font-medium">LTV:CAC ≥ 3:1</span>. Below 1:1 means you're spending more to acquire a customer than they're worth.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] text-slate-500 mb-1 block">Monthly ad spend ($)</label>
          <input
            value={inputs.adSpend}
            onChange={(e) => setInputs((p) => ({ ...p, adSpend: e.target.value }))}
            type="number"
            placeholder="e.g. 2000"
            className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700"
          />
        </div>
        <div>
          <label className="text-[10px] text-slate-500 mb-1 block">New customers acquired</label>
          <input
            value={inputs.newCustomers}
            onChange={(e) => setInputs((p) => ({ ...p, newCustomers: e.target.value }))}
            type="number"
            placeholder="e.g. 40"
            className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-slate-800/60 rounded-xl p-3 text-center">
          <p className="text-[10px] text-slate-500 mb-1">Your CAC</p>
          <p className="text-base font-bold text-slate-200">{cac > 0 ? fmt(cac) : "—"}</p>
        </div>
        <div className="bg-slate-800/60 rounded-xl p-3 text-center">
          <p className="text-[10px] text-slate-500 mb-1">Avg LTV</p>
          <p className="text-base font-bold text-emerald-400">{avgLtv > 0 ? fmt(avgLtv) : "—"}</p>
        </div>
        <div className={cn("rounded-xl p-3 text-center border", ltvCac >= 3 ? "bg-emerald-900/20 border-emerald-800/40" : ltvCac >= 1 ? "bg-amber-900/20 border-amber-800/40" : cac > 0 ? "bg-rose-900/20 border-rose-800/40" : "bg-slate-800/60 border-transparent")}>
          <p className="text-[10px] text-slate-500 mb-1">LTV:CAC</p>
          <p className={cn("text-base font-bold", ltvCacColor)}>{ltvCac > 0 ? `${ltvCac.toFixed(1)}:1` : "—"}</p>
        </div>
        <div className="bg-slate-800/60 rounded-xl p-3 text-center">
          <p className="text-[10px] text-slate-500 mb-1">Payback</p>
          <p className="text-base font-bold text-slate-200">{payback > 0 ? `${payback} orders` : "—"}</p>
        </div>
      </div>

      {cac > 0 && (
        <div className={cn("rounded-xl px-3 py-2 text-xs flex items-center gap-2", ltvCac >= 3 ? "bg-emerald-900/20 text-emerald-400" : ltvCac >= 1 ? "bg-amber-900/20 text-amber-400" : "bg-rose-900/20 text-rose-400")}>
          {ltvCac >= 3 ? <CheckCircle2 size={12} /> : ltvCac >= 1 ? <AlertTriangle size={12} /> : <XCircle size={12} />}
          {ltvCacLabel}
        </div>
      )}
    </div>
  );
}

// ── Channel attribution bar ───────────────────────────────────────────────────

function ChannelBars({ channels }: { channels: { channel: string; revenue: number }[] }) {
  const total = channels.reduce((s, c) => s + c.revenue, 0);
  if (total === 0) return (
    <div className="text-xs text-slate-600 py-6 text-center">
      No channel data yet. Tag orders with source (facebook, google, email, whatsapp) to see attribution.
    </div>
  );

  const COLORS: Record<string, string> = {
    "Meta Ads": "bg-blue-500",
    "Google Ads": "bg-amber-500",
    "Email": "bg-brand",
    "WhatsApp": "bg-emerald-500",
    "Organic": "bg-teal-500",
    "Direct / Other": "bg-slate-600",
  };

  return (
    <div className="space-y-2.5">
      {channels.map(({ channel, revenue }) => {
        const share = Math.round((revenue / total) * 100);
        return (
          <div key={channel} className="flex items-center gap-3">
            <span className="text-xs text-slate-400 w-24 truncate shrink-0">{channel}</span>
            <div className="flex-1 bg-slate-800 rounded-full h-2">
              <div className={cn("h-2 rounded-full", COLORS[channel] ?? "bg-slate-500")} style={{ width: `${share}%` }} />
            </div>
            <span className="text-xs text-slate-400 w-8 text-right">{share}%</span>
            <span className="text-xs text-slate-600 w-16 text-right">{fmt(revenue)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Trust signal checklist ────────────────────────────────────────────────────

type TrustItem = { label: string; desc: string; crmLink?: string; checked: boolean };

function TrustChecklist() {
  const [checks, setChecks] = useState<TrustItem[]>([
    { label: "Shipping policy visible", desc: "Customers need to know when they'll receive the order", checked: false },
    { label: "Return/refund policy", desc: "Clear return policy increases purchase confidence by up to 30%", checked: false },
    { label: "Product reviews enabled", desc: "93% of consumers read reviews before buying", checked: false },
    { label: "Mobile checkout tested", desc: "79% of Shopify traffic is mobile — a broken checkout kills conversions", checked: false },
    { label: "Trust badges on checkout", desc: "SSL seal, payment logos, and security badges reduce cart abandonment", checked: false },
    { label: "Live chat or contact info visible", desc: "Customers abandon when they can't quickly get answers", checked: false },
    { label: "Email capture popup/offer", desc: "Grow your list — email converts 3-5× better than social ads", crmLink: "/dashboard/broadcast", checked: false },
    { label: "WhatsApp chat button", desc: "Instant response channel — critical in African & Asian markets", crmLink: "/dashboard/whatsapp", checked: false },
    { label: "Abandoned cart sequence active", desc: "Recover 5-15% of abandoned carts automatically", crmLink: "/dashboard/shopify", checked: false },
    { label: "Loyalty/rewards program", desc: "Repeat buyers spend 67% more than new ones", crmLink: "/dashboard/loyalty", checked: false },
  ]);

  const score = Math.round((checks.filter((c) => c.checked).length / checks.length) * 100);

  function toggle(i: number) {
    setChecks((prev) => prev.map((c, idx) => idx === i ? { ...c, checked: !c.checked } : c));
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">Trust Signal Audit</p>
          <p className="text-xs text-slate-500 mt-0.5">{checks.filter((c) => c.checked).length}/{checks.length} implemented</p>
        </div>
        <ScoreRing score={score} label="Trust score" size={72} />
      </div>

      <div className="space-y-2">
        {checks.map((item, i) => (
          <div
            key={item.label}
            onClick={() => toggle(i)}
            className={cn(
              "flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all",
              item.checked ? "border-emerald-800/40 bg-emerald-900/10" : "border-slate-800 bg-slate-900/50 hover:border-slate-700"
            )}
          >
            <div className={cn("mt-0.5 shrink-0 rounded-full w-4 h-4 flex items-center justify-center border", item.checked ? "bg-emerald-600 border-emerald-600" : "border-slate-600")}>
              {item.checked && <CheckCircle2 size={12} className="text-white" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className={cn("text-xs font-medium", item.checked ? "text-emerald-300 line-through opacity-70" : "text-slate-200")}>{item.label}</p>
              <p className="text-[11px] text-slate-600 mt-0.5">{item.desc}</p>
            </div>
            {item.crmLink && !item.checked && (
              <a
                href={item.crmLink}
                onClick={(e) => e.stopPropagation()}
                className="shrink-0 text-[10px] text-brand hover:text-brand/50 flex items-center gap-0.5 transition-colors"
              >
                Setup <ArrowRight size={9} />
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Conversion gap meter ──────────────────────────────────────────────────────

function ConversionGap({ aov }: { aov: number }) {
  const [visitors, setVisitors] = useState("");
  const [orders, setOrders] = useState("");

  const v = parseFloat(visitors) || 0;
  const o = parseFloat(orders) || 0;
  const convRate = v > 0 ? (o / v) * 100 : 0;
  const gap      = Math.max(0, 2.5 - convRate); // vs 2.5% industry avg
  const lostOrders = v > 0 ? Math.floor((gap / 100) * v) : 0;
  const lostRevenue = lostOrders * aov;

  const color = convRate >= 2.5 ? "text-emerald-400" : convRate >= 1.4 ? "text-amber-400" : "text-rose-400";
  const barPct = Math.min((convRate / 4) * 100, 100);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-4">
      <div className="flex items-center gap-2">
        <BarChart3 size={13} className="text-brand" />
        <p className="text-sm font-semibold">Conversion Rate Gap</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] text-slate-500 mb-1 block">Monthly visitors</label>
          <input value={visitors} onChange={(e) => setVisitors(e.target.value)} type="number" placeholder="e.g. 5000"
            className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700" />
        </div>
        <div>
          <label className="text-[10px] text-slate-500 mb-1 block">Monthly orders</label>
          <input value={orders} onChange={(e) => setOrders(e.target.value)} type="number" placeholder="e.g. 70"
            className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-3 py-2 outline-none focus:ring-1 focus:ring-brand border border-slate-700" />
        </div>
      </div>

      {/* Benchmark bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">Your rate</span>
          <span className={cn("font-bold", color)}>{convRate > 0 ? `${convRate.toFixed(2)}%` : "—"}</span>
        </div>
        <div className="relative h-3 bg-slate-800 rounded-full overflow-hidden">
          <div className="absolute left-0 h-full bg-slate-700 rounded-full" style={{ width: "35%" }} title="Shopify avg 1.4%" />
          <div className="absolute left-0 h-full bg-slate-600 rounded-full" style={{ width: "62.5%" }} title="Industry avg 2.5%" />
          {convRate > 0 && (
            <div className={cn("absolute left-0 h-full rounded-full", convRate >= 2.5 ? "bg-emerald-500" : convRate >= 1.4 ? "bg-amber-500" : "bg-rose-500")} style={{ width: `${barPct}%` }} />
          )}
        </div>
        <div className="flex justify-between text-[10px] text-slate-600">
          <span>0%</span>
          <span className="text-slate-500">Shopify avg 1.4%</span>
          <span className="text-slate-500">Industry avg 2.5%</span>
          <span>4%+</span>
        </div>
      </div>

      {lostRevenue > 0 && (
        <div className="bg-rose-900/20 border border-rose-800/30 rounded-xl px-3 py-2.5 text-xs">
          <p className="text-rose-400 font-semibold flex items-center gap-1.5">
            <TrendingDown size={12} /> Conversion gap costs you ~{fmt(lostRevenue)}/mo
          </p>
          <p className="text-slate-500 mt-1">
            Closing {gap.toFixed(1)}pp gap = ~{lostOrders} extra orders at your current traffic.
            Focus on: faster mobile load, trust badges, and abandoned cart recovery.
          </p>
        </div>
      )}
    </div>
  );
}

// ── AI action plan ────────────────────────────────────────────────────────────

function AIActionPlan({ data }: { data: GrowthData }) {
  const [plan, setPlan] = useState("");
  const [loading, setLoading] = useState(false);

  async function generate() {
    setLoading(true);
    try {
      const p = await aiDraft(`You are a Shopify growth expert. Create a focused 30-day action plan based on these store metrics:

- Total customers: ${data.totalCustomers}
- Repeat purchase rate: ${data.repeatRate}% (industry avg 27%)
- At-risk customers: ${data.atRiskCount} worth ${fmt(data.revenueAtRisk)} in potential revenue
- Average LTV: ${fmt(data.avgLtv)}
- Average order value: ${fmt(data.aov)}
- Email subscribers: ${data.subscriberRate}% of customers (${data.subscribers})
- New vs returning (30d): ${data.newCust} new, ${data.returningCust} returning
- Top channel: ${data.channelRevenue[0]?.channel ?? "unknown"}

Write a specific 30-day action plan with exactly 3 prioritized actions. For each:
1. What to do (specific, actionable)
2. Why it matters for this store's numbers
3. Expected impact

Keep it under 200 words. Be direct, no fluff.`);
      setPlan(p);
    } catch { toast.error("AI failed"); }
    finally { setLoading(false); }
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles size={13} className="text-brand" />
          <p className="text-sm font-semibold">30-Day Growth Plan</p>
        </div>
        <button
          onClick={generate}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-medium disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
          {plan ? "Regenerate" : "Generate plan"}
        </button>
      </div>

      {!plan && !loading && (
        <p className="text-xs text-slate-600 leading-relaxed">
          AI analyses your repeat rate, at-risk revenue, LTV, and channel mix — then writes a specific 3-action plan to grow this month.
        </p>
      )}

      {loading && (
        <div className="flex items-center gap-2 py-4 justify-center text-slate-600">
          <Loader2 size={16} className="animate-spin" />
          <span className="text-xs">Analysing your store…</span>
        </div>
      )}

      {plan && (
        <div className="bg-slate-800/40 rounded-xl p-4 border border-slate-700/50">
          <pre className="text-xs text-slate-300 whitespace-pre-wrap font-sans leading-relaxed">{plan}</pre>
        </div>
      )}
    </div>
  );
}

// ── Multi-channel checker ─────────────────────────────────────────────────────

function ChannelPresence() {
  const channels = [
    { icon: MessageSquare, label: "WhatsApp", desc: "Highest open rate (98%) — direct customer conversations", href: "/dashboard/whatsapp", key: "whatsapp" },
    { icon: Mail, label: "Email marketing", desc: "Own your list — $42 ROI per $1 spent", href: "/dashboard/broadcast", key: "email" },
    { icon: Megaphone, label: "Meta Ads", desc: "Largest social ad audience, great for retargeting", href: "/dashboard/meta-ads", key: "meta" },
    { icon: BarChart3, label: "Google Ads", desc: "Capture high-intent search traffic", href: "/dashboard/google-ads", key: "google" },
    { icon: Hash, label: "X Ads", desc: "Reach engaged audiences on X (Twitter)", href: "/dashboard/x-ads", key: "xads" },
    { icon: MapPinned, label: "Google Business", desc: "Local visibility, reviews, and Maps discovery", href: "/dashboard/google-business", key: "gbp" },
    { icon: Zap, label: "Abandoned cart sequence", desc: "Recover 5-15% of lost revenue automatically", href: "/dashboard/shopify?tab=abandoned", key: "abandoned" },
    { icon: TrendingUp, label: "Loyalty programme", desc: "Repeat buyers spend 67% more than first-timers", href: "/dashboard/loyalty", key: "loyalty" },
  ];

  const [active, setActive] = useState<Set<string>>(new Set());

  function toggle(key: string) {
    setActive((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  const score = Math.round((active.size / channels.length) * 100);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Shield size={13} className="text-cyan-400" />
            <p className="text-sm font-semibold">Multi-channel Presence</p>
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">Stores relying on a single channel are one algorithm change away from failure</p>
        </div>
        <div className="text-right">
          <p className={cn("text-xl font-bold", score >= 60 ? "text-emerald-400" : score >= 40 ? "text-amber-400" : "text-rose-400")}>{score}%</p>
          <p className="text-[10px] text-slate-600">active</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {channels.map(({ icon: Icon, label, desc, href, key }) => {
          const on = active.has(key);
          return (
            <div
              key={key}
              onClick={() => toggle(key)}
              className={cn(
                "flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all",
                on ? "border-emerald-800/40 bg-emerald-900/10" : "border-slate-800 hover:border-slate-700"
              )}
            >
              <Icon size={13} className={on ? "text-emerald-400 mt-0.5 shrink-0" : "text-slate-500 mt-0.5 shrink-0"} />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-slate-200">{label}</p>
                <p className="text-[10px] text-slate-600 mt-0.5">{desc}</p>
              </div>
              {on
                ? <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
                : <a href={href} onClick={(e) => e.stopPropagation()} className="text-[10px] text-brand hover:text-brand/50 shrink-0 flex items-center gap-0.5">Setup <ArrowRight size={9} /></a>
              }
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main Growth tab ───────────────────────────────────────────────────────────

export default function GrowthTab() {
  const [data, setData] = useState<GrowthData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await shopGet({ action: "growth" });
      setData(d as GrowthData);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <Loader2 size={24} className="animate-spin text-slate-600" />
        <p className="text-xs text-slate-600">Analysing your store…</p>
      </div>
    </div>
  );

  if (!data) return null;

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      {/* Refresh */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">Growth Intelligence</p>
          <p className="text-xs text-slate-500 mt-0.5">Based on last 90 days · {data.totalCustomers} customers</p>
        </div>
        <button onClick={load} className="p-1.5 text-slate-500 hover:text-slate-300 transition-colors"><RefreshCw size={13} /></button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MCard icon={Repeat2} label="Repeat purchase rate" value={pct(data.repeatRate)}
          sub={`${data.repeatCustomers} repeat buyers`}
          color={data.repeatRate >= 27 ? "text-emerald-400" : "text-amber-400"}
          alert={data.repeatRate < 20} />
        <MCard icon={TrendingDown} label="Revenue at risk" value={data.revenueAtRisk > 0 ? fmt(data.revenueAtRisk) : "$0"}
          sub={`${data.atRiskCount} at-risk customers`}
          color="text-rose-400" alert={data.revenueAtRisk > 500} />
        <MCard icon={Users} label="Avg customer LTV" value={fmt(data.avgLtv)}
          sub="lifetime spend per customer" color="text-brand" />
        <MCard icon={Mail} label="Marketing subscribers" value={pct(data.subscriberRate)}
          sub={`${data.subscribers} opted in`}
          color={data.subscriberRate >= 30 ? "text-emerald-400" : "text-amber-400"} />
      </div>

      {/* New vs Returning */}
      {(data.newCust > 0 || data.returningCust > 0) && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <p className="text-xs font-semibold text-slate-400 mb-3">New vs Returning (last 30 days)</p>
          <div className="flex items-center gap-3">
            <div className="flex-1 space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 w-24">New customers</span>
                <div className="flex-1 bg-slate-800 rounded-full h-2">
                  <div className="h-2 bg-blue-500 rounded-full" style={{ width: `${data.newCust + data.returningCust > 0 ? Math.round((data.newCust / (data.newCust + data.returningCust)) * 100) : 0}%` }} />
                </div>
                <span className="text-xs font-semibold text-blue-400 w-8 text-right">{data.newCust}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 w-24">Returning</span>
                <div className="flex-1 bg-slate-800 rounded-full h-2">
                  <div className="h-2 bg-emerald-500 rounded-full" style={{ width: `${data.newCust + data.returningCust > 0 ? Math.round((data.returningCust / (data.newCust + data.returningCust)) * 100) : 0}%` }} />
                </div>
                <span className="text-xs font-semibold text-emerald-400 w-8 text-right">{data.returningCust}</span>
              </div>
            </div>
            <div className="text-center pl-3 border-l border-slate-800">
              <p className="text-xl font-bold text-emerald-400">
                {data.newCust + data.returningCust > 0 ? Math.round((data.returningCust / (data.newCust + data.returningCust)) * 100) : 0}%
              </p>
              <p className="text-[10px] text-slate-600">returning</p>
              <p className="text-[10px] text-slate-600">target: 40%+</p>
            </div>
          </div>
          {data.avgOrderGap && (
            <p className="text-[11px] text-slate-600 mt-2">Avg days between orders: ~{data.avgOrderGap} days</p>
          )}
        </div>
      )}

      {/* CAC Calculator */}
      <CACCalculator avgLtv={data.avgLtv} aov={data.aov} />

      {/* Conversion gap */}
      <ConversionGap aov={data.aov} />

      {/* Channel attribution */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <BarChart3 size={13} className="text-amber-400" />
          <p className="text-sm font-semibold">Revenue by Channel</p>
          <span className="text-[10px] text-slate-600 ml-1">from order tags</span>
        </div>
        <ChannelBars channels={data.channelRevenue} />
      </div>

      {/* Multi-channel presence */}
      <ChannelPresence />

      {/* Trust checklist */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4">
        <TrustChecklist />
      </div>

      {/* AI action plan */}
      <AIActionPlan data={data} />
    </div>
  );
}

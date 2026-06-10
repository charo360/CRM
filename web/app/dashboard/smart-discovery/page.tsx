"use client";

import { useState, useCallback } from "react";
import { getToken } from "@/lib/auth";
import {
  Search, TrendingUp, TrendingDown, Minus, Zap, ShoppingBag,
  BarChart2, AlertCircle, Loader2, ArrowUpRight, Package, Star
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";

function apiUrl(path: string) {
  const base = API.endsWith("/api") ? API : `${API}/api`;
  return `${base}${path}`;
}

async function apiFetch<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(apiUrl(path), {
    headers: { Authorization: `Bearer ${token ?? ""}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" })) as { detail?: string };
    throw new Error(String(err.detail ?? "Request failed"));
  }
  return res.json() as Promise<T>;
}

// ── Types ─────────────────────────────────────────────────────────────────────

type TrendPoint = { date: string; value: number };

type TrendData = {
  keyword: string;
  trend: TrendPoint[];
  score: number;
  change_pct: number;
  direction: "rising" | "falling" | "stable" | "unknown";
  rising_queries: { query: string; value: string }[];
};

type CJProduct = {
  cj_pid: string;
  title: string;
  category: string;
  cost: number;
  sell_price: number;
  margin: number;
  orders: number;
  free_ship: boolean;
  image: string;
  opportunity_score?: number;
};

type FbAd = {
  id: string;
  page: string;
  created: string;
  body: string;
  snapshot_url: string;
};

type AnalysisResult = {
  niche: string;
  country: string;
  trend: TrendData;
  rising: { query: string; value: string }[];
  fb_ads: { available: boolean; total: number; sample_ads: FbAd[]; reason?: string };
  products: CJProduct[];
  summary: {
    trend_direction: string;
    trend_change_pct: number;
    active_fb_ads: number;
    top_cj_orders: number;
  };
};

// ── Small components ──────────────────────────────────────────────────────────

function TrendBadge({ direction, pct }: { direction: string; pct: number }) {
  if (direction === "rising") return (
    <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[11px] font-semibold text-green-700">
      <TrendingUp size={11} /> +{pct}%
    </span>
  );
  if (direction === "falling") return (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-600">
      <TrendingDown size={11} /> {pct}%
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
      <Minus size={11} /> Stable
    </span>
  );
}

function MiniSparkline({ data }: { data: TrendPoint[] }) {
  if (!data.length) return null;
  const max = Math.max(...data.map(d => d.value), 1);
  const w = 120, h = 36;
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - (d.value / max) * h;
    return `${x},${y}`;
  }).join(" ");
  const last = data[data.length - 1];
  const color = last.value > data[0].value ? "#16a34a" : last.value < data[0].value ? "#dc2626" : "#64748b";
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function ScoreBadge({ score }: { score: number }) {
  const color = score >= 70 ? "bg-green-500" : score >= 45 ? "bg-amber-500" : "bg-slate-400";
  return (
    <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${color} text-white text-[13px] font-bold`}>
      {score}
    </div>
  );
}

function StatCard({ label, value, sub, icon }: { label: string; value: string | number; sub?: string; icon: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-dark/10 text-brand-dark">
        {icon}
      </div>
      <div>
        <p className="text-[11px] text-slate-500">{label}</p>
        <p className="text-lg font-bold text-slate-900 leading-tight">{value}</p>
        {sub && <p className="text-[10px] text-slate-400">{sub}</p>}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SmartDiscoveryPage() {
  const [niche, setNiche]     = useState("");
  const [country, setCountry] = useState("US");
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState<AnalysisResult | null>(null);
  const [error, setError]     = useState<string | null>(null);

  const analyze = useCallback(async () => {
    const q = niche.trim();
    if (!q) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await apiFetch<AnalysisResult>(
        `/market/winning-products?niche=${encodeURIComponent(q)}&country=${country}&limit=10`
      );
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }, [niche, country]);

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6 max-w-6xl mx-auto">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
          <Zap size={20} className="text-brand-dark" /> Smart Discovery
        </h1>
        <p className="mt-0.5 text-[13px] text-slate-500">
          Google Trends + CJ sales data + Facebook Ad spend — find winning products before your competitors do.
        </p>
      </div>

      {/* Search bar */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={niche}
            onChange={e => setNiche(e.target.value)}
            onKeyDown={e => e.key === "Enter" && void analyze()}
            placeholder="Enter a niche or product — e.g. 'women fitness gear', 'pet accessories'"
            className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-4 text-sm shadow-sm outline-none focus:border-brand-dark focus:ring-1 focus:ring-brand-dark"
          />
        </div>
        <select
          value={country}
          onChange={e => setCountry(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm outline-none focus:border-brand-dark"
        >
          <option value="US">🇺🇸 US</option>
          <option value="GB">🇬🇧 UK</option>
          <option value="CA">🇨🇦 Canada</option>
          <option value="AU">🇦🇺 Australia</option>
          <option value="DE">🇩🇪 Germany</option>
          <option value="KE">🇰🇪 Kenya</option>
          <option value="NG">🇳🇬 Nigeria</option>
          <option value="ZA">🇿🇦 South Africa</option>
        </select>
        <button
          onClick={() => void analyze()}
          disabled={loading || !niche.trim()}
          className="flex items-center gap-2 rounded-xl bg-brand-dark px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-dark/90 disabled:opacity-50"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />}
          {loading ? "Analyzing…" : "Find Winners"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle size={15} /> {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex flex-col items-center gap-3 py-16 text-slate-400">
          <Loader2 size={32} className="animate-spin text-brand-dark" />
          <p className="text-sm">Checking Google Trends, CJ sales data, and Facebook ads…</p>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="flex flex-col gap-6">

          {/* Summary stat cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="Trend Score"
              value={result.trend.score}
              sub={`${result.summary.trend_change_pct > 0 ? "+" : ""}${result.summary.trend_change_pct}% vs prior period`}
              icon={<TrendingUp size={16} />}
            />
            <StatCard
              label="Top CJ Orders"
              value={result.summary.top_cj_orders.toLocaleString()}
              sub="on best product (30d)"
              icon={<ShoppingBag size={16} />}
            />
            <StatCard
              label="Active FB Ads"
              value={result.fb_ads.available ? result.fb_ads.total.toLocaleString() : "—"}
              sub={result.fb_ads.available ? "competitors advertising" : result.fb_ads.reason ?? "Token not configured"}
              icon={<BarChart2 size={16} />}
            />
            <StatCard
              label="Products Found"
              value={result.products.length}
              sub="with opportunity scores"
              icon={<Package size={16} />}
            />
          </div>

          {/* Trend + Rising Queries */}
          <div className="grid gap-4 sm:grid-cols-2">

            {/* Google Trends chart */}
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-[13px] font-semibold text-slate-800">Google Trends — last 12 weeks</h2>
                <TrendBadge direction={result.trend.direction} pct={result.summary.trend_change_pct} />
              </div>
              {result.trend.trend.length > 0 ? (
                <div className="flex items-end gap-1 h-20">
                  {result.trend.trend.slice(-12).map((pt, i) => {
                    const max = Math.max(...result.trend.trend.map(d => d.value), 1);
                    const pct = (pt.value / max) * 100;
                    const color = result.trend.direction === "rising" ? "bg-green-500" :
                                  result.trend.direction === "falling" ? "bg-red-400" : "bg-slate-400";
                    return (
                      <div key={i} className="flex flex-1 flex-col items-center gap-0.5 group relative">
                        <div className={`w-full rounded-sm ${color} opacity-80 group-hover:opacity-100`} style={{ height: `${Math.max(pct, 4)}%` }} />
                        <div className="absolute -top-7 left-1/2 -translate-x-1/2 hidden group-hover:block rounded bg-slate-800 px-1.5 py-0.5 text-[9px] text-white whitespace-nowrap z-10">
                          {pt.date}: {pt.value}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[12px] text-slate-400 py-4 text-center">No trend data available for this keyword.</p>
              )}
            </div>

            {/* Rising queries */}
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="mb-3 text-[13px] font-semibold text-slate-800">Rising Searches</h2>
              {result.rising.length > 0 ? (
                <ul className="space-y-1.5">
                  {result.rising.slice(0, 8).map((q, i) => (
                    <li key={i} className="flex items-center justify-between">
                      <span className="text-[12px] text-slate-700">{q.query}</span>
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-700">
                        {q.value === "Breakout" ? "🔥 Breakout" : `+${q.value}%`}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[12px] text-slate-400">No rising queries found.</p>
              )}
            </div>
          </div>

          {/* Winning Products */}
          <div>
            <h2 className="mb-3 text-[13px] font-semibold text-slate-800 flex items-center gap-2">
              <Star size={14} className="text-amber-500" /> Winning Products — ranked by opportunity score
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {result.products.map((p, i) => (
                <div key={p.cj_pid || i} className="flex gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm hover:border-brand-dark/30 transition-colors">
                  {p.image ? (
                    <img src={p.image} alt={p.title} className="h-16 w-16 shrink-0 rounded-lg object-cover bg-slate-100" />
                  ) : (
                    <div className="h-16 w-16 shrink-0 rounded-lg bg-slate-100 flex items-center justify-center text-slate-300">
                      <Package size={24} />
                    </div>
                  )}
                  <div className="flex flex-1 flex-col justify-between min-w-0">
                    <div className="flex items-start justify-between gap-1">
                      <p className="text-[12px] font-medium text-slate-800 leading-snug line-clamp-2">{p.title}</p>
                      {p.opportunity_score !== undefined && <ScoreBadge score={p.opportunity_score} />}
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
                      <span className="text-[11px] text-slate-500">Cost <strong className="text-slate-700">${p.cost.toFixed(2)}</strong></span>
                      <span className="text-[11px] text-green-700">Margin <strong>${p.margin.toFixed(2)}</strong></span>
                      <span className="text-[11px] text-slate-500">{p.orders.toLocaleString()} orders</span>
                      {p.free_ship && <span className="text-[10px] text-blue-600 font-medium">Free ship</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Facebook Ads sample */}
          {result.fb_ads.available && result.fb_ads.sample_ads.length > 0 && (
            <div>
              <h2 className="mb-3 text-[13px] font-semibold text-slate-800 flex items-center gap-2">
                <BarChart2 size={14} className="text-blue-500" /> Competitor Facebook Ads ({result.fb_ads.total}+ active)
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {result.fb_ads.sample_ads.map((ad, i) => (
                  <div key={ad.id || i} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-slate-800 truncate">{ad.page}</span>
                      {ad.snapshot_url && (
                        <a href={ad.snapshot_url} target="_blank" rel="noreferrer"
                          className="text-[10px] text-blue-600 hover:underline flex items-center gap-0.5">
                          View <ArrowUpRight size={9} />
                        </a>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-600 leading-snug line-clamp-4">{ad.body || "No ad copy preview available."}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!result.fb_ads.available && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] text-amber-700">
              <strong>Facebook Ad Library:</strong> {result.fb_ads.reason ?? "Add FACEBOOK_AD_LIBRARY_TOKEN to your server environment to unlock competitor ad intelligence."}
            </div>
          )}

        </div>
      )}

      {/* Empty state */}
      {!result && !loading && !error && (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-dark/10">
            <Zap size={28} className="text-brand-dark" />
          </div>
          <div>
            <p className="text-[15px] font-semibold text-slate-800">Find your next winning product</p>
            <p className="mt-1 text-[13px] text-slate-500 max-w-sm">
              Enter a niche above. We check Google Trends for rising demand, CJ for real sales volume, and Facebook for competitor ad spend — giving each product an opportunity score.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 justify-center">
            {["women fitness gear", "pet accessories", "kitchen gadgets", "home office", "baby products"].map(s => (
              <button key={s} onClick={() => { setNiche(s); }}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[12px] text-slate-600 hover:border-brand-dark hover:text-brand-dark">
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}

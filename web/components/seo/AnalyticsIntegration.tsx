"use client";
import React, { useState, useEffect, useCallback } from "react";
import { seoApi } from "@/lib/api";
import { getToken } from "@/lib/auth";

// ── helpers ──────────────────────────────────────────────────────────────────

const API_BASE = (() => {
  const raw = process.env.NEXT_PUBLIC_API_URL ?? "";
  return raw.endsWith("/api") ? raw.slice(0, -4) : raw.replace(/\/$/, "");
})();

async function composioFetch(path: string, method = "GET", body?: unknown) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) return null;
  return res.json();
}

// ── types ─────────────────────────────────────────────────────────────────────

type ConnStatus = "unknown" | "connected" | "disconnected";

interface GscQuery  { query: string; clicks: number; impressions: number; ctr: number; position: number }
interface GscPage   { page:  string; clicks: number; impressions: number; ctr: number; position: number }
interface GscDevice { device: string; clicks: number; impressions: number; ctr: number; position: number }
interface GscCountry{ country: string; clicks: number; impressions: number; ctr: number; position: number }
interface GscTrend  { date: string; clicks: number; impressions: number }
interface GscSitemap{ path: string; last_submitted: string; last_downloaded: string; is_pending: boolean; warnings: number; errors: number; submitted: number; indexed: number }

interface GscData {
  connected: boolean; error?: string; site_url?: string; period_days?: number;
  summary?: { total_clicks: number; total_impressions: number; avg_ctr: number; avg_position: number };
  top_queries?: GscQuery[];
  top_pages?: GscPage[];
  devices?: GscDevice[];
  countries?: GscCountry[];
  trend?: GscTrend[];
}

interface Ga4Data {
  connected: boolean; error?: string; property_id?: string; period_days?: number;
  summary?: { total_sessions: number; total_users: number; total_views: number };
  daily?: { date: string; sessions: number; users: number; views: number; bounce_rate: number; avg_session_duration: number }[];
}

// ── small UI atoms ────────────────────────────────────────────────────────────

function MetricCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-800">{value}</p>
      {sub && <p className="text-[10px] text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function ConnectButton({ toolkit, label, busy, onStatusChange }: {
  toolkit: string; label: string; busy: boolean;
  onStatusChange: (toolkit: string, status: ConnStatus) => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleConnect = async () => {
    setLoading(true);
    const data = await composioFetch(`/composio/connect/${toolkit}`, "POST", {
      redirect_base: window.location.origin,
    });
    setLoading(false);
    if (!data?.redirect_url) return;
    const popup = window.open(data.redirect_url, "_blank", "width=600,height=700");
    const poll = setInterval(async () => {
      if (popup?.closed) {
        clearInterval(poll);
        const status = await composioFetch(`/composio/connections/${toolkit}`);
        onStatusChange(toolkit, status?.connected ? "connected" : "disconnected");
      }
    }, 1000);
  };

  return (
    <button onClick={handleConnect} disabled={loading || busy}
      className="text-xs px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 transition-colors">
      {loading ? "Opening…" : `Connect ${label}`}
    </button>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function AnalyticsIntegration() {
  const [statuses, setStatuses] = useState<Record<string, ConnStatus>>({
    googlesearchconsole: "unknown",
    googleanalytics: "unknown",
    googleads: "unknown",
  });

  const [gscData, setGscData] = useState<GscData | null>(null);
  const [gscLoading, setGscLoading] = useState(false);
  const [gscSiteUrl, setGscSiteUrl] = useState("");
  const [gscActiveUrl, setGscActiveUrl] = useState("");
  const [gscInputUrl, setGscInputUrl] = useState("");
  const [gscDays, setGscDays] = useState(28);
  const [gscSearchType, setGscSearchType] = useState<"web" | "image" | "video" | "news">("web");
  const [savedSites, setSavedSites] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem("gsc_saved_sites") ?? "[]") as string[]; }
    catch { return []; }
  });
  const [discoveredSites, setDiscoveredSites] = useState<{ url: string; level: string }[]>([]);
  const [listingSites, setListingSites] = useState(false);
  const [sitemaps, setSitemaps] = useState<GscSitemap[] | null>(null);
  const [sitemapsNote, setSitemapsNote] = useState<string | null>(null);
  const [sitemapsLoading, setSitemapsLoading] = useState(false);

  const [ga4Data, setGa4Data] = useState<Ga4Data | null>(null);
  const [ga4Loading, setGa4Loading] = useState(false);
  const [ga4PropertyId, setGa4PropertyId] = useState("");

  const [busy, setBusy] = useState<string | null>(null);

  // ── status ───────────────────────────────────────────────────────────────

  const refreshStatuses = useCallback(async () => {
    const data = await composioFetch("/composio/connections");
    if (!data) return;
    const c = data.connected as Record<string, boolean> ?? {};
    setStatuses({
      googlesearchconsole: c.googlesearchconsole ? "connected" : "disconnected",
      googleanalytics: c.googleanalytics ? "connected" : "disconnected",
      googleads: c.googleads ? "connected" : "disconnected",
    });
  }, []);

  useEffect(() => { refreshStatuses(); }, [refreshStatuses]);

  const handleStatusChange = useCallback((toolkit: string, s: ConnStatus) => {
    setStatuses(prev => ({ ...prev, [toolkit]: s }));
  }, []);

  const handleDisconnect = async (toolkit: string) => {
    setBusy(toolkit);
    await composioFetch(`/composio/connections/${toolkit}`, "DELETE");
    handleStatusChange(toolkit, "disconnected");
    setBusy(null);
  };

  // ── GSC fetch ─────────────────────────────────────────────────────────────

  const fetchGscData = useCallback(async (siteUrl?: string, days?: number, searchType?: string) => {
    const url = siteUrl || gscSiteUrl || undefined;
    if (url) setGscActiveUrl(url);
    setGscLoading(true);
    try {
      const d = await seoApi.getSearchConsoleData(url, days ?? gscDays, searchType ?? gscSearchType);
      setGscData(d);
      if (d.site_url) { setGscSiteUrl(d.site_url); setGscActiveUrl(d.site_url); }
    } catch { setGscData(null); }
    setGscLoading(false);
  }, [gscSiteUrl, gscDays, gscSearchType]);

  // ── sitemaps ──────────────────────────────────────────────────────────────

  const fetchSitemaps = useCallback(async (siteUrl?: string) => {
    setSitemapsLoading(true);
    try {
      const d = await seoApi.listSearchConsoleSitemaps(siteUrl || gscActiveUrl || undefined);
      setSitemaps(d.sitemaps ?? []);
      setSitemapsNote((d as Record<string, unknown>).note as string ?? null);
    } catch { setSitemaps([]); setSitemapsNote(null); }
    setSitemapsLoading(false);
  }, [gscActiveUrl]);

  // ── saved sites ───────────────────────────────────────────────────────────

  const saveSite = useCallback((url: string) => {
    setSavedSites(prev => {
      if (prev.includes(url)) return prev;
      const next = [...prev, url];
      localStorage.setItem("gsc_saved_sites", JSON.stringify(next));
      return next;
    });
  }, []);

  const removeSite = useCallback((url: string) => {
    setSavedSites(prev => {
      const next = prev.filter(s => s !== url);
      localStorage.setItem("gsc_saved_sites", JSON.stringify(next));
      return next;
    });
  }, []);

  const handleListSites = useCallback(async () => {
    setListingSites(true);
    try {
      const d = await seoApi.listSearchConsoleSites();
      setDiscoveredSites(d.sites ?? []);
    } catch { setDiscoveredSites([]); }
    setListingSites(false);
  }, []);

  // ── GA4 fetch ─────────────────────────────────────────────────────────────

  const fetchGa4Data = useCallback(async () => {
    if (!ga4PropertyId.trim()) return;
    setGa4Loading(true);
    try {
      const d = await seoApi.getGa4Data(ga4PropertyId.trim());
      setGa4Data(d);
    } catch { setGa4Data(null); }
    setGa4Loading(false);
  }, [ga4PropertyId]);

  // ── platform card helpers ──────────────────────────────────────────────────

  const statusBadge = (s: ConnStatus) =>
    s === "connected" ? (
      <span className="text-[10px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">● Connected</span>
    ) : s === "disconnected" ? (
      <span className="text-[10px] bg-red-100 text-red-600 px-2 py-0.5 rounded-full font-medium">● Disconnected</span>
    ) : (
      <span className="text-[10px] bg-slate-100 text-slate-400 px-2 py-0.5 rounded-full font-medium">Checking…</span>
    );

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">

      {/* ── Platform connection cards ────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Google Search Console */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="font-semibold text-slate-800 text-sm">Search Console</p>
              <p className="text-xs text-slate-400">Google Search Console</p>
            </div>
            {statusBadge(statuses.googlesearchconsole)}
          </div>
          {statuses.googlesearchconsole === "connected" ? (
            <button onClick={() => handleDisconnect("googlesearchconsole")} disabled={!!busy}
              className="text-xs px-3 py-1.5 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 font-medium disabled:opacity-50">
              {busy === "googlesearchconsole" ? "Disconnecting…" : "Disconnect"}
            </button>
          ) : (
            <ConnectButton toolkit="googlesearchconsole" label="Search Console" busy={!!busy} onStatusChange={handleStatusChange} />
          )}
        </div>

        {/* Google Analytics 4 */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="font-semibold text-slate-800 text-sm">Google Analytics 4</p>
              <p className="text-xs text-slate-400">GA4 traffic & conversions</p>
            </div>
            {statusBadge(statuses.googleanalytics)}
          </div>
          {statuses.googleanalytics === "connected" ? (
            <button onClick={() => handleDisconnect("googleanalytics")} disabled={!!busy}
              className="text-xs px-3 py-1.5 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 font-medium disabled:opacity-50">
              {busy === "googleanalytics" ? "Disconnecting…" : "Disconnect"}
            </button>
          ) : (
            <ConnectButton toolkit="googleanalytics" label="Analytics 4" busy={!!busy} onStatusChange={handleStatusChange} />
          )}
        </div>

        {/* Google Ads */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="font-semibold text-slate-800 text-sm">Google Ads</p>
              <p className="text-xs text-slate-400">Paid search performance</p>
            </div>
            {statusBadge(statuses.googleads)}
          </div>
          {statuses.googleads === "connected" ? (
            <button onClick={() => handleDisconnect("googleads")} disabled={!!busy}
              className="text-xs px-3 py-1.5 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 font-medium disabled:opacity-50">
              {busy === "googleads" ? "Disconnecting…" : "Disconnect"}
            </button>
          ) : (
            <ConnectButton toolkit="googleads" label="Google Ads" busy={!!busy} onStatusChange={handleStatusChange} />
          )}
        </div>
      </div>

      {/* ── Google Search Console data panel ────────────────────────────── */}
      {statuses.googlesearchconsole === "connected" && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          {/* header */}
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <h3 className="text-lg font-semibold text-slate-800">
              Search Console — {gscDays === 1 ? "Last 24 Hours" : `Last ${gscDays} Days`}
              {gscDays === 1 && <span className="ml-2 text-xs font-normal text-slate-400">(GSC data has ~2 day lag)</span>}
            </h3>
            <div className="flex items-center gap-2 flex-wrap">
              {/* search type filter */}
              <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs">
                {(["web", "image", "video", "news"] as const).map(t => (
                  <button key={t} onClick={() => { setGscSearchType(t); fetchGscData(undefined, undefined, t); }}
                    className={`px-3 py-1.5 font-medium capitalize transition-colors ${gscSearchType === t ? "bg-indigo-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>
                    {t}
                  </button>
                ))}
              </div>
              {/* day range */}
              <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs">
                {([1, 7, 28, 90] as const).map(d => (
                  <button key={d} onClick={() => { setGscDays(d); fetchGscData(undefined, d); }}
                    className={`px-3 py-1.5 font-medium transition-colors ${gscDays === d ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>
                    {d === 1 ? "24h" : `${d}d`}
                  </button>
                ))}
              </div>
              <button onClick={() => fetchGscData()} disabled={gscLoading}
                className="text-xs px-3 py-1.5 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 font-medium disabled:opacity-50">
                {gscLoading ? "Loading…" : "↻ Refresh"}
              </button>
            </div>
          </div>

          {/* site URL input + saved sites */}
          <div className="mb-4 space-y-2">
            <div className="flex gap-2">
              <input
                type="text" value={gscInputUrl} onChange={e => setGscInputUrl(e.target.value)}
                placeholder="https://yourdomain.com/ or sc-domain:yourdomain.com"
                className="flex-1 text-xs border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => { if (gscInputUrl.trim()) { saveSite(gscInputUrl.trim()); fetchGscData(gscInputUrl.trim()); setGscInputUrl(""); } }}
                className="text-xs px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
                Load
              </button>
              <button onClick={handleListSites} disabled={listingSites}
                className="text-xs px-3 py-2 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 font-medium disabled:opacity-50">
                {listingSites ? "Listing…" : "List my sites"}
              </button>
            </div>

            {/* discovered sites */}
            {discoveredSites.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {discoveredSites.map(s => (
                  <button key={s.url} onClick={() => { saveSite(s.url); fetchGscData(s.url); }}
                    className="text-[11px] bg-blue-50 border border-blue-100 text-blue-700 px-2.5 py-1 rounded-full hover:bg-blue-100 font-medium">
                    + {s.url}
                  </button>
                ))}
              </div>
            )}

            {/* saved site chips */}
            {savedSites.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {savedSites.map(s => (
                  <div key={s} className="flex items-center gap-1">
                    <button onClick={() => fetchGscData(s)}
                      className={`text-[11px] px-2.5 py-1 rounded-full border font-medium transition-colors ${gscActiveUrl === s ? "bg-blue-600 text-white border-blue-600" : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"}`}>
                      {s}
                    </button>
                    <button onClick={() => removeSite(s)} className="text-slate-300 hover:text-red-400 text-xs leading-none">×</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* loading skeleton */}
          {gscLoading && (
            <div className="animate-pulse space-y-3">{[1, 2, 3].map(i => <div key={i} className="h-10 bg-slate-100 rounded" />)}</div>
          )}

          {/* error */}
          {!gscLoading && gscData?.error && (
            <div className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">{gscData.error}</div>
          )}

          {/* data */}
          {!gscLoading && gscData?.summary && (() => {
            const queries = gscData.top_queries ?? [];
            const pages   = gscData.top_pages ?? [];

            const quickWins = queries.filter(q => q.position >= 4 && q.position <= 15 && q.impressions >= 50)
              .sort((a, b) => b.impressions - a.impressions).slice(0, 5);
            const ctrOpts   = queries.filter(q => q.impressions >= 100 && q.ctr < 2)
              .sort((a, b) => b.impressions - a.impressions).slice(0, 5);
            const lowPages  = pages.filter(p => p.impressions >= 200 && p.ctr < 1)
              .sort((a, b) => b.impressions - a.impressions).slice(0, 3);

            return (
              <>
                {/* SEO Opportunities */}
                {(quickWins.length > 0 || ctrOpts.length > 0 || lowPages.length > 0) && (
                  <div className="mb-5 space-y-3">
                    <h4 className="text-sm font-bold text-slate-800">🎯 SEO Opportunities</h4>

                    {quickWins.length > 0 && (
                      <div className="bg-green-50 border border-green-100 rounded-xl p-4">
                        <p className="text-xs font-semibold text-green-800 mb-2">⚡ Quick Wins — Rank 4–15 with good impressions (small push = page 1)</p>
                        <div className="space-y-1.5">
                          {quickWins.map((q, i) => (
                            <div key={i} className="flex items-center justify-between text-xs">
                              <span className="text-slate-700 font-medium truncate max-w-[60%]">{q.query}</span>
                              <span className="text-green-700 font-semibold">Pos {q.position} · {q.impressions.toLocaleString()} impr</span>
                            </div>
                          ))}
                        </div>
                        <p className="text-[10px] text-green-600 mt-2">Add these keywords to page titles, H1s and internal links to improve ranking.</p>
                      </div>
                    )}

                    {ctrOpts.length > 0 && (
                      <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
                        <p className="text-xs font-semibold text-amber-800 mb-2">👀 Low CTR — High impressions, few clicks (fix meta titles/descriptions)</p>
                        <div className="space-y-1.5">
                          {ctrOpts.map((q, i) => (
                            <div key={i} className="flex items-center justify-between text-xs">
                              <span className="text-slate-700 font-medium truncate max-w-[60%]">{q.query}</span>
                              <span className="text-amber-700 font-semibold">{q.ctr}% CTR · {q.impressions.toLocaleString()} impr</span>
                            </div>
                          ))}
                        </div>
                        <p className="text-[10px] text-amber-600 mt-2">Rewrite page titles to be more compelling and match search intent.</p>
                      </div>
                    )}

                    {lowPages.length > 0 && (
                      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
                        <p className="text-xs font-semibold text-blue-800 mb-2">📄 Pages with wasted impressions (visible but not clicked)</p>
                        <div className="space-y-1.5">
                          {lowPages.map((p, i) => (
                            <div key={i} className="flex items-center justify-between text-xs">
                              <span className="text-slate-700 font-medium truncate max-w-[60%]">{p.page.replace(/^https?:\/\/[^/]+/, "") || "/"}</span>
                              <span className="text-blue-700 font-semibold">{p.ctr}% CTR · {p.impressions.toLocaleString()} impr</span>
                            </div>
                          ))}
                        </div>
                        <p className="text-[10px] text-blue-600 mt-2">Add a clear value proposition in the meta description to drive more clicks.</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Summary cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                  <MetricCard label="Total Clicks" value={gscData.summary!.total_clicks.toLocaleString()} />
                  <MetricCard label="Impressions" value={gscData.summary!.total_impressions.toLocaleString()} />
                  <MetricCard label="Avg CTR" value={`${gscData.summary!.avg_ctr}%`} />
                  <MetricCard label="Avg Position" value={gscData.summary!.avg_position} sub="lower = better" />
                </div>

                {/* Top Queries */}
                {queries.length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-sm font-semibold text-slate-700 mb-2">Top Queries</h4>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead><tr className="border-b border-slate-100 text-slate-400">
                          <th className="text-left py-2 pr-3 font-medium">Query</th>
                          <th className="text-right py-2 px-2 font-medium">Clicks</th>
                          <th className="text-right py-2 px-2 font-medium">Impr</th>
                          <th className="text-right py-2 px-2 font-medium">CTR</th>
                          <th className="text-right py-2 pl-2 font-medium">Pos</th>
                        </tr></thead>
                        <tbody>
                          {queries.map((q, i) => (
                            <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                              <td className="py-2 pr-3 text-slate-700 max-w-[220px] truncate">{q.query}</td>
                              <td className="py-2 px-2 text-right font-medium text-slate-800">{q.clicks}</td>
                              <td className="py-2 px-2 text-right text-slate-500">{q.impressions.toLocaleString()}</td>
                              <td className="py-2 px-2 text-right text-slate-500">{q.ctr}%</td>
                              <td className="py-2 pl-2 text-right text-slate-500">{q.position}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Top Pages */}
                {pages.length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-sm font-semibold text-slate-700 mb-2">Top Pages</h4>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead><tr className="border-b border-slate-100 text-slate-400">
                          <th className="text-left py-2 pr-3 font-medium">Page</th>
                          <th className="text-right py-2 px-2 font-medium">Clicks</th>
                          <th className="text-right py-2 px-2 font-medium">Impr</th>
                          <th className="text-right py-2 px-2 font-medium">CTR</th>
                          <th className="text-right py-2 pl-2 font-medium">Pos</th>
                        </tr></thead>
                        <tbody>
                          {pages.map((p, i) => (
                            <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                              <td className="py-2 pr-3 text-slate-700 max-w-[220px] truncate">{p.page.replace(/^https?:\/\/[^/]+/, "") || "/"}</td>
                              <td className="py-2 px-2 text-right font-medium text-slate-800">{p.clicks}</td>
                              <td className="py-2 px-2 text-right text-slate-500">{p.impressions.toLocaleString()}</td>
                              <td className="py-2 px-2 text-right text-slate-500">{p.ctr}%</td>
                              <td className="py-2 pl-2 text-right text-slate-500">{p.position}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Devices */}
                {(gscData.devices ?? []).length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-sm font-semibold text-slate-700 mb-2">By Device</h4>
                    <div className="space-y-1.5">
                      {gscData.devices!.map((d, i) => {
                        const maxClicks = Math.max(...gscData.devices!.map(x => x.clicks), 1);
                        return (
                          <div key={i} className="flex items-center gap-2 text-xs">
                            <span className="w-20 text-slate-500 capitalize">{d.device}</span>
                            <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                              <div className="h-full bg-blue-400 rounded-full" style={{ width: `${(d.clicks / maxClicks) * 100}%` }} />
                            </div>
                            <span className="w-16 text-right text-slate-700 font-medium">{d.clicks} clicks</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Countries */}
                {(gscData.countries ?? []).length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-sm font-semibold text-slate-700 mb-2">Top Countries</h4>
                    <div className="space-y-1.5">
                      {gscData.countries!.slice(0, 8).map((c, i) => {
                        const maxClicks = Math.max(...gscData.countries!.map(x => x.clicks), 1);
                        return (
                          <div key={i} className="flex items-center gap-2 text-xs">
                            <span className="w-24 text-slate-500 uppercase text-[10px]">{c.country}</span>
                            <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                              <div className="h-full bg-indigo-400 rounded-full" style={{ width: `${(c.clicks / maxClicks) * 100}%` }} />
                            </div>
                            <span className="w-16 text-right text-slate-700 font-medium">{c.clicks} clicks</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Sitemaps */}
                <div className="mt-4 pt-4 border-t border-slate-100">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-semibold text-slate-700">🗺️ Sitemaps</h4>
                    <button onClick={() => fetchSitemaps()} disabled={sitemapsLoading}
                      className="text-xs px-3 py-1 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 font-medium disabled:opacity-50">
                      {sitemapsLoading ? "Loading…" : sitemaps === null ? "Load Sitemaps" : "↻ Refresh"}
                    </button>
                  </div>

                  {sitemapsLoading && (
                    <div className="animate-pulse space-y-2">{[1, 2].map(i => <div key={i} className="h-10 bg-slate-100 rounded" />)}</div>
                  )}

                  {!sitemapsLoading && sitemaps !== null && sitemaps.length === 0 && (
                    <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 text-xs text-amber-800 space-y-1">
                      <p className="font-medium">⚠️ {sitemapsNote ?? "No sitemaps have been submitted to Search Console yet."}</p>
                      <p>Submitting a sitemap helps Google discover and index all your pages faster.</p>
                      <a href={`https://search.google.com/search-console/sitemaps?resource_id=${encodeURIComponent(gscActiveUrl)}`}
                        target="_blank" rel="noreferrer"
                        className="inline-block mt-1 px-3 py-1 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-medium">
                        Submit a Sitemap in GSC ↗
                      </a>
                    </div>
                  )}

                  {!sitemapsLoading && (sitemaps ?? []).length > 0 && (
                    <div className="space-y-2">
                      {sitemaps!.map((s, i) => {
                        const hasIssues = s.errors > 0 || s.warnings > 0;
                        return (
                          <div key={i} className={`rounded-lg border p-3 ${s.errors > 0 ? "border-red-200 bg-red-50" : s.warnings > 0 ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-slate-50"}`}>
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium text-slate-800 truncate">{s.path}</p>
                                <p className="text-[10px] text-slate-400 mt-0.5">
                                  Submitted {s.last_submitted ? new Date(s.last_submitted).toLocaleDateString() : "—"} · Last fetched {s.last_downloaded ? new Date(s.last_downloaded).toLocaleDateString() : "—"}
                                </p>
                              </div>
                              <div className="flex gap-1.5 flex-shrink-0">
                                {s.errors > 0 && <span className="text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded font-medium">{s.errors} error{s.errors > 1 ? "s" : ""}</span>}
                                {s.warnings > 0 && <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium">{s.warnings} warning{s.warnings > 1 ? "s" : ""}</span>}
                                {s.is_pending && <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">Pending</span>}
                                {!hasIssues && !s.is_pending && <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-medium">✓ OK</span>}
                              </div>
                            </div>
                            {s.submitted > 0 && (
                              <div className="mt-2 flex justify-between text-[10px] text-slate-500">
                                <span>{s.submitted.toLocaleString()} URLs discovered by Google</span>
                                <span className="text-slate-400 cursor-help" title="Full indexing detail available in GSC Index Coverage report">Index coverage → GSC ↗</span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Daily trend sparkline */}
                {(gscData.trend ?? []).length > 1 && (
                  <div className="mt-4 pt-4 border-t border-slate-100">
                    <h4 className="text-sm font-semibold text-slate-700 mb-2">Daily Clicks Trend</h4>
                    <div className="flex items-end gap-0.5 h-16 bg-slate-50 rounded-lg px-3 py-2">
                      {(() => {
                        const max = Math.max(...gscData.trend!.map(t => t.clicks), 1);
                        return gscData.trend!.map((t, i) => (
                          <div key={i} title={`${t.date}: ${t.clicks} clicks`}
                            className="flex-1 bg-blue-400 rounded-sm hover:bg-blue-600 transition-colors cursor-pointer min-w-[2px]"
                            style={{ height: `${Math.max((t.clicks / max) * 100, 2)}%` }} />
                        ));
                      })()}
                    </div>
                    <div className="flex justify-between text-[10px] text-slate-400 mt-1 px-1">
                      <span>{gscData.trend![0].date}</span>
                      <span>{gscData.trend![gscData.trend!.length - 1].date}</span>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {/* ── Google Analytics 4 data panel ───────────────────────────────── */}
      {statuses.googleanalytics === "connected" && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h3 className="text-lg font-semibold text-slate-800 mb-4">Google Analytics 4</h3>
          <div className="flex gap-2 mb-4">
            <input
              type="text" value={ga4PropertyId} onChange={e => setGa4PropertyId(e.target.value)}
              placeholder="GA4 Property ID (e.g. 123456789)"
              className="flex-1 text-xs border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button onClick={fetchGa4Data} disabled={ga4Loading || !ga4PropertyId.trim()}
              className="text-xs px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50">
              {ga4Loading ? "Loading…" : "Load"}
            </button>
          </div>

          {ga4Loading && <div className="animate-pulse space-y-3">{[1, 2].map(i => <div key={i} className="h-10 bg-slate-100 rounded" />)}</div>}

          {!ga4Loading && ga4Data?.error && (
            <div className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">{ga4Data.error}</div>
          )}

          {!ga4Loading && ga4Data?.summary && (
            <div className="grid grid-cols-3 gap-3">
              <MetricCard label="Sessions" value={ga4Data.summary.total_sessions.toLocaleString()} />
              <MetricCard label="Users" value={ga4Data.summary.total_users.toLocaleString()} />
              <MetricCard label="Page Views" value={ga4Data.summary.total_views.toLocaleString()} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

"use client";
import React, { useState, useEffect, useCallback } from "react";
import { seoApi } from "@/lib/api";
import { getToken } from "@/lib/auth";

// ── Types ─────────────────────────────────────────────────────────────────────
interface AnalyticsEvent { id: string; type: string; created_at: string; }
type ConnStatus = "loading" | "connected" | "disconnected";

interface GscData {
  site_url?: string;
  summary?: { total_clicks: number; total_impressions: number; avg_ctr: number; avg_position: number };
  top_queries?: { query: string; clicks: number; impressions: number; ctr: number; position: number }[];
  top_pages?: { page: string; clicks: number; impressions: number; ctr: number; position: number }[];
  devices?: { device: string; clicks: number; impressions: number; ctr: number; position: number }[];
  countries?: { country: string; clicks: number; impressions: number; ctr: number; position: number }[];
  trend?: { date: string; clicks: number; impressions: number }[];
  error?: string;
}
interface Ga4Data {
  summary?: { total_sessions: number; total_users: number; total_views: number };
  daily?: { date: string; sessions: number; users: number; views: number; bounce_rate: number; avg_session_duration: number }[];
  error?: string;
}
interface AdsData {
  summary?: { total_spend: number; total_clicks: number; total_impressions: number; avg_ctr: number; avg_cpc: number };
  campaigns?: { id: string; name: string; status: string; impressions: number; clicks: number; cost: number; ctr: number; avg_cpc: number }[];
  error?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const round1 = (n: number) => Math.round(n * 10) / 10;

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api")
  .replace(/\/+$/, "")
  .replace(/\/api$/, "");

async function composioFetch(path: string, method = "GET") {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api${path}`, {
    method,
    headers: { Authorization: `Bearer ${token ?? ""}` },
  });
  return res.ok ? res.json() : null;
}

async function composioConnect(toolkit: string, extraBody: Record<string, string> = {}): Promise<string | null> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/composio/connect/${toolkit}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token ?? ""}`, "Content-Type": "application/json" },
    body: JSON.stringify({ redirect_base: window.location.origin, ...extraBody }),
  });
  if (!res.ok) return null;
  const data = await res.json() as { redirect_url?: string };
  return data.redirect_url ?? null;
}

// ── Metric Card ───────────────────────────────────────────────────────────────
function MetricCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-slate-50 rounded-xl p-4 text-center">
      <div className="text-2xl font-bold text-slate-800">{value}</div>
      <div className="text-xs font-medium text-slate-600 mt-0.5">{label}</div>
      {sub && <div className="text-[10px] text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}

// ── Connect Button ────────────────────────────────────────────────────────────
function ConnectButton({
  toolkit, label, busy, onStatusChange, customerId,
}: {
  toolkit: string; label: string; busy: boolean;
  onStatusChange: (t: string, s: ConnStatus) => void;
  customerId?: string;
}) {
  const [working, setWorking] = useState(false);

  const handleConnect = async () => {
    setWorking(true);
    try {
      const extraBody: Record<string, string> = {};
      if (toolkit === "googleads" && customerId) extraBody.customer_id = customerId;
      const url = await composioConnect(toolkit, extraBody);
      if (!url) { setWorking(false); return; }
      const popup = window.open(url, "composio-connect", "width=980,height=760,noopener,noreferrer");
      if (!popup) { window.location.href = url; return; }
      let popupClosed = false;
      const poll = window.setInterval(async () => {
        const data = await composioFetch(`/composio/connections/${toolkit}`);
        if (data?.connected) {
          window.clearInterval(poll);
          onStatusChange(toolkit, "connected");
          setWorking(false);
          return;
        }
        if (!popupClosed && popup.closed) {
          popupClosed = true;
          window.clearInterval(poll);
          // Retry up to 8 times over ~20s — Composio can take several seconds to register
          for (let i = 0; i < 8; i++) {
            await new Promise(r => setTimeout(r, 2500));
            const fresh = await composioFetch(`/composio/connections/${toolkit}`);
            if (fresh?.connected) {
              onStatusChange(toolkit, "connected");
              setWorking(false);
              return;
            }
          }
          onStatusChange(toolkit, "disconnected");
          setWorking(false);
        }
      }, 3000);
    } catch { setWorking(false); }
  };

  return (
    <button
      onClick={handleConnect}
      disabled={busy || working}
      className="w-full py-2 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 transition-colors"
    >
      {working ? "Opening…" : `Connect ${label}`}
    </button>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function AnalyticsIntegration() {
  const [statuses, setStatuses] = useState<Record<string, ConnStatus>>({
    googlesearchconsole: "loading",
    googleanalytics: "loading",
    googleads: "loading",
  });
  const [events, setEvents] = useState<AnalyticsEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(true);

  const [gscData, setGscData] = useState<GscData | null>(null);
  const [gscLoading, setGscLoading] = useState(false);
  const [gscSiteUrl, setGscSiteUrl] = useState("");
  const [gscActiveUrl, setGscActiveUrl] = useState("");
  const [savedSites, setSavedSites] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem("gsc_saved_sites") ?? "[]") as string[]; }
    catch { return []; }
  });
  const [gscInputUrl, setGscInputUrl] = useState("");
  const [gscDays, setGscDays] = useState(28);
  const [gscSearchType, setGscSearchType] = useState<"web"|"image"|"video"|"news">("web");
  const [discoveredSites, setDiscoveredSites] = useState<{ url: string; level: string }[]>([]);
  const [listingSites, setListingSites] = useState(false);
  const [sitemaps, setSitemaps] = useState<{ path: string; last_submitted: string; last_downloaded: string; is_pending: boolean; warnings: number; errors: number; submitted: number; indexed: number }[] | null>(null);
  const [sitemapsNote, setSitemapsNote] = useState<string | null>(null);
  const [sitemapsLoading, setSitemapsLoading] = useState(false);
  const [indexingData, setIndexingData] = useState<{
    total_inspected?: number; indexed?: number; not_indexed?: number; sitemap_url?: string; error?: string;
    reasons?: { reason: string; label: string; color: string; fix: string | null; count: number; urls: string[] }[];
  } | null>(null);
  const [indexingLoading, setIndexingLoading] = useState(false);
  const [ga4Data, setGa4Data] = useState<Ga4Data | null>(null);
  const [ga4Loading, setGa4Loading] = useState(false);
  const [ga4PropertyId, setGa4PropertyId] = useState("");
  const [ga4Days, setGa4Days] = useState(28);
  const [adsData, setAdsData] = useState<AdsData | null>(null);
  const [adsLoading, setAdsLoading] = useState(false);
  const [adsCustomerId, setAdsCustomerId] = useState("");
  const [adsDays, setAdsDays] = useState(30);
  const [adsConnectId, setAdsConnectId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

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

  const handleStatusChange = useCallback((toolkit: string, s: ConnStatus) => {
    setStatuses(prev => ({ ...prev, [toolkit]: s }));
  }, []);

  const handleDisconnect = async (toolkit: string) => {
    setBusy(toolkit);
    await composioFetch(`/composio/connections/${toolkit}`, "DELETE");
    handleStatusChange(toolkit, "disconnected");
    setBusy(null);
  };

  const fetchSitemaps = useCallback(async (siteUrl?: string) => {
    setSitemapsLoading(true);
    try {
      const d = await seoApi.listSearchConsoleSitemaps(siteUrl || gscActiveUrl || undefined);
      setSitemaps(d.sitemaps ?? []);
      setSitemapsNote((d as Record<string, unknown>).note as string ?? null);
    } catch { setSitemaps([]); setSitemapsNote(null); }
    setSitemapsLoading(false);
  }, [gscActiveUrl]);

  const fetchIndexingData = useCallback(async (siteUrl?: string, sitemapUrl?: string) => {
    setIndexingLoading(true);
    setIndexingData(null);
    try {
      const d = await seoApi.getPageIndexingStatus(
        siteUrl || gscActiveUrl || undefined,
        sitemapUrl,
        20,
      );
      setIndexingData(d);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to fetch indexing data";
      setIndexingData({ error: msg });
    }
    setIndexingLoading(false);
  }, [gscActiveUrl]);

  const handleListSites = useCallback(async () => {
    setListingSites(true);
    try {
      const d = await seoApi.listSearchConsoleSites();
      setDiscoveredSites(d.sites ?? []);
    } catch { setDiscoveredSites([]); }
    setListingSites(false);
  }, []);

  const saveSite = useCallback((url: string) => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setSavedSites(prev => {
      if (prev.includes(trimmed)) return prev;
      const next = [...prev, trimmed];
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

  const fetchGa4Data = useCallback(async (days?: number) => {
    if (!ga4PropertyId.trim()) return;
    setGa4Loading(true);
    try {
      const d = await seoApi.getGa4Data(ga4PropertyId.trim(), days ?? ga4Days);
      setGa4Data(d);
    } catch { setGa4Data(null); }
    setGa4Loading(false);
  }, [ga4PropertyId, ga4Days]);

  const fetchAdsData = useCallback(async (days?: number) => {
    if (!adsCustomerId.trim()) return;
    setAdsLoading(true);
    try {
      const d = await seoApi.getGoogleAdsData(adsCustomerId.trim(), days ?? adsDays);
      setAdsData(d);
    } catch { setAdsData(null); }
    setAdsLoading(false);
  }, [adsCustomerId, adsDays]);

  useEffect(() => {
    refreshStatuses();
    seoApi.analyticsEvents(50).then(d => setEvents(d as AnalyticsEvent[])).catch(() => {}).finally(() => setEventsLoading(false));
  }, [refreshStatuses]);

  // Auto-fetch GSC when connected
  useEffect(() => {
    if (statuses.googlesearchconsole === "connected") fetchGscData();
  }, [statuses.googlesearchconsole, fetchGscData]);

  const isLoading = Object.values(statuses).some(s => s === "loading");

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-7 bg-slate-200 rounded w-1/3" />
        <div className="grid grid-cols-3 gap-4">
          {[1,2,3].map(i => <div key={i} className="h-36 bg-slate-100 rounded-xl" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-800">Analytics &amp; Tracking</h2>
        <p className="text-sm text-slate-500 mt-1">
          Connect Google tools to pull real traffic, ranking and ad data into your dashboard.
        </p>
      </div>

      {/* Platform connection cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Google Search Console */}
        <div className={`bg-white rounded-xl border p-5 flex flex-col gap-3 ${statuses.googlesearchconsole === "connected" ? "border-green-200" : "border-slate-200"}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xl">🔍</span>
              <span className="font-semibold text-slate-800 text-sm">Search Console</span>
            </div>
            {statuses.googlesearchconsole === "connected"
              ? <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">✓ Connected</span>
              : <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full font-medium">Not connected</span>
            }
          </div>
          <p className="text-xs text-slate-500 flex-1">Real keyword impressions, CTR, and search positions from Google.</p>
          {statuses.googlesearchconsole === "connected" ? (
            <button
              onClick={() => handleDisconnect("googlesearchconsole")}
              disabled={busy === "googlesearchconsole"}
              className="w-full py-1.5 bg-red-50 text-red-600 text-xs rounded-lg hover:bg-red-100 font-medium disabled:opacity-50"
            >
              {busy === "googlesearchconsole" ? "Disconnecting…" : "Disconnect"}
            </button>
          ) : (
            <ConnectButton toolkit="googlesearchconsole" label="Search Console" busy={!!busy} onStatusChange={handleStatusChange} />
          )}
        </div>

        {/* Google Analytics 4 */}
        <div className={`bg-white rounded-xl border p-5 flex flex-col gap-3 ${statuses.googleanalytics === "connected" ? "border-green-200" : "border-slate-200"}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xl">📊</span>
              <span className="font-semibold text-slate-800 text-sm">Google Analytics 4</span>
            </div>
            {statuses.googleanalytics === "connected"
              ? <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">✓ Connected</span>
              : <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full font-medium">Not connected</span>
            }
          </div>
          <p className="text-xs text-slate-500 flex-1">Sessions, users, page views and bounce rates from your GA4 property.</p>
          {statuses.googleanalytics === "connected" ? (
            <button
              onClick={() => handleDisconnect("googleanalytics")}
              disabled={busy === "googleanalytics"}
              className="w-full py-1.5 bg-red-50 text-red-600 text-xs rounded-lg hover:bg-red-100 font-medium disabled:opacity-50"
            >
              {busy === "googleanalytics" ? "Disconnecting…" : "Disconnect"}
            </button>
          ) : (
            <ConnectButton toolkit="googleanalytics" label="Analytics" busy={!!busy} onStatusChange={handleStatusChange} />
          )}
        </div>

        {/* Google Ads */}
        <div className={`bg-white rounded-xl border p-5 flex flex-col gap-3 ${statuses.googleads === "connected" ? "border-green-200" : "border-slate-200"}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xl">💰</span>
              <span className="font-semibold text-slate-800 text-sm">Google Ads</span>
            </div>
            {statuses.googleads === "connected"
              ? <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">✓ Connected</span>
              : <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full font-medium">Not connected</span>
            }
          </div>
          <p className="text-xs text-slate-500 flex-1">Paid campaign spend, clicks, impressions and cost-per-click.</p>
          {statuses.googleads === "connected" ? (
            <button
              onClick={() => handleDisconnect("googleads")}
              disabled={busy === "googleads"}
              className="w-full py-1.5 bg-red-50 text-red-600 text-xs rounded-lg hover:bg-red-100 font-medium disabled:opacity-50"
            >
              {busy === "googleads" ? "Disconnecting…" : "Disconnect"}
            </button>
          ) : (
            <>
              <input
                type="text"
                value={adsConnectId}
                onChange={e => setAdsConnectId(e.target.value)}
                placeholder="Customer ID (e.g. 123-456-7890)"
                className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs font-mono outline-none focus:border-blue-500"
              />
              <ConnectButton toolkit="googleads" label="Google Ads" busy={!!busy} onStatusChange={handleStatusChange} customerId={adsConnectId} />
            </>
          )}
        </div>
      </div>

      {/* Search Console Data */}
      {statuses.googlesearchconsole === "connected" && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-800">Search Console — Last {gscDays} Days</h3>
            <div className="flex items-center gap-2">
              <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs">
                {(["web","image","video","news"] as const).map(t => (
                  <button key={t} onClick={() => { setGscSearchType(t); fetchGscData(undefined, undefined, t); }}
                    className={`px-3 py-1.5 font-medium capitalize transition-colors ${
                      gscSearchType === t ? "bg-indigo-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                    }`}>{t}</button>
                ))}
              </div>
              <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs">
                {[7, 28, 90].map(d => (
                  <button key={d} onClick={() => { setGscDays(d); fetchGscData(undefined, d); }}
                    className={`px-3 py-1.5 font-medium transition-colors ${
                      gscDays === d ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                    }`}>{d}d</button>
                ))}
              </div>
              <button onClick={() => fetchGscData()} disabled={gscLoading}
                className="text-xs px-3 py-1.5 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 font-medium disabled:opacity-50">
                {gscLoading ? "Loading…" : "↻ Refresh"}
              </button>
            </div>
          </div>

          {/* Saved sites + add new */}
          <div className="mb-4 space-y-3">
            {/* Saved site chips */}
            {savedSites.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {savedSites.map(site => (
                  <div
                    key={site}
                    className={`flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full border text-xs font-medium cursor-pointer transition-colors ${
                      gscActiveUrl === site
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-white text-slate-700 border-slate-200 hover:border-blue-400 hover:text-blue-600"
                    }`}
                    onClick={() => { setGscSiteUrl(site); fetchGscData(site); }}
                  >
                    <span className="truncate max-w-[200px]">{site.replace(/^https?:\/\//, "")}</span>
                    <button
                      onClick={e => { e.stopPropagation(); removeSite(site); if (gscActiveUrl === site) { setGscData(null); setGscActiveUrl(""); } }}
                      className={`ml-0.5 rounded-full w-4 h-4 flex items-center justify-center hover:bg-black/20 ${gscActiveUrl === site ? "text-white" : "text-slate-400"}`}
                    >×</button>
                  </div>
                ))}
              </div>
            )}

            {/* Discovered sites from GSC account */}
            {discoveredSites.length > 0 && (
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                <p className="text-xs font-medium text-blue-700 mb-2">Sites found in your Search Console account — click to load:</p>
                <div className="flex flex-wrap gap-2">
                  {discoveredSites.map(s => (
                    <button
                      key={s.url}
                      onClick={() => { saveSite(s.url); fetchGscData(s.url); setGscInputUrl(""); }}
                      className="text-xs px-3 py-1 bg-white border border-blue-200 text-blue-700 rounded-full hover:bg-blue-600 hover:text-white hover:border-blue-600 font-medium transition-colors"
                    >
                      {s.url.replace(/^https?:\/\//, "").replace(/^sc-domain:/, "")} {s.level === "siteOwner" ? "(owner)" : ""}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Add new URL row */}
            <div className="flex gap-2">
              <input
                type="url"
                placeholder="Add site URL (e.g. https://yourdomain.com)"
                value={gscInputUrl}
                onChange={e => setGscInputUrl(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && gscInputUrl.trim()) { saveSite(gscInputUrl); setGscSiteUrl(gscInputUrl); fetchGscData(gscInputUrl); setGscInputUrl(""); } }}
                className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => { if (gscInputUrl.trim()) { saveSite(gscInputUrl); setGscSiteUrl(gscInputUrl); fetchGscData(gscInputUrl); setGscInputUrl(""); } }}
                disabled={gscLoading || !gscInputUrl.trim()}
                className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 whitespace-nowrap"
              >
                {gscLoading ? "Fetching…" : "+ Add & Fetch"}
              </button>
              <button
                onClick={handleListSites}
                disabled={listingSites}
                className="px-3 py-2 bg-slate-100 text-slate-600 text-sm rounded-lg hover:bg-slate-200 font-medium disabled:opacity-50 whitespace-nowrap"
                title="Auto-discover your verified properties"
              >
                {listingSites ? "Finding…" : "List my sites"}
              </button>
            </div>
            <p className="text-xs text-slate-400">Click <strong>List my sites</strong> to auto-discover your verified properties, or paste a URL manually.</p>
          </div>

          {gscLoading && <div className="animate-pulse space-y-3">{[1,2,3].map(i=><div key={i} className="h-10 bg-slate-100 rounded"/>)}</div>}

          {!gscLoading && gscData?.error && (
            <div className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">{gscData.error}</div>
          )}

          {!gscLoading && gscData?.summary && (
            <>
              {/* ── Insights ────────────────────────────────────────────── */}
              {(() => {
                const queries = gscData.top_queries ?? [];
                const pages   = gscData.top_pages ?? [];

                const quickWins = queries
                  .filter(q => q.position >= 4 && q.position <= 15 && q.impressions >= 50)
                  .sort((a, b) => b.impressions - a.impressions)
                  .slice(0, 5);

                const ctrOpts = queries
                  .filter(q => q.impressions >= 100 && q.ctr < 2)
                  .sort((a, b) => b.impressions - a.impressions)
                  .slice(0, 5);

                const lowPages = pages
                  .filter(p => p.impressions >= 200 && p.ctr < 1)
                  .sort((a, b) => b.impressions - a.impressions)
                  .slice(0, 3);

                if (!quickWins.length && !ctrOpts.length && !lowPages.length) return null;
                return (
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
                );
              })()}

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                <MetricCard label="Total Clicks" value={gscData.summary.total_clicks.toLocaleString()} />
                <MetricCard label="Impressions" value={gscData.summary.total_impressions.toLocaleString()} />
                <MetricCard label="Avg CTR" value={`${gscData.summary.avg_ctr}%`} />
                <MetricCard label="Avg Position" value={gscData.summary.avg_position} sub="lower = better" />
              </div>

              {/* Top Queries */}
              {(gscData.top_queries ?? []).length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-slate-700 mb-2">Top Queries</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-slate-600">
                      <thead><tr className="text-left border-b border-slate-100">
                        <th className="pb-2 font-medium">Query</th>
                        <th className="pb-2 font-medium text-right">Clicks</th>
                        <th className="pb-2 font-medium text-right">Impressions</th>
                        <th className="pb-2 font-medium text-right">CTR</th>
                        <th className="pb-2 font-medium text-right">Position</th>
                      </tr></thead>
                      <tbody>
                        {gscData.top_queries!.map((q, i) => (
                          <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                            <td className="py-1.5 font-medium text-slate-800 max-w-[200px] truncate">{q.query}</td>
                            <td className="py-1.5 text-right">{q.clicks}</td>
                            <td className="py-1.5 text-right">{q.impressions.toLocaleString()}</td>
                            <td className="py-1.5 text-right">{q.ctr}%</td>
                            <td className="py-1.5 text-right">{q.position}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Top Pages */}
              {(gscData.top_pages ?? []).length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-slate-700 mb-2">Top Pages</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-slate-600">
                      <thead><tr className="text-left border-b border-slate-100">
                        <th className="pb-2 font-medium">Page</th>
                        <th className="pb-2 font-medium text-right">Clicks</th>
                        <th className="pb-2 font-medium text-right">Impressions</th>
                        <th className="pb-2 font-medium text-right">CTR</th>
                        <th className="pb-2 font-medium text-right">Position</th>
                      </tr></thead>
                      <tbody>
                        {gscData.top_pages!.map((p, i) => (
                          <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                            <td className="py-1.5 font-medium text-slate-800 max-w-[240px] truncate">{p.page.replace(/^https?:\/\/[^/]+/, "")}</td>
                            <td className="py-1.5 text-right">{p.clicks}</td>
                            <td className="py-1.5 text-right">{p.impressions.toLocaleString()}</td>
                            <td className="py-1.5 text-right">{p.ctr}%</td>
                            <td className="py-1.5 text-right">{p.position}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Devices + Countries side by side */}
              {((gscData.devices ?? []).length > 0 || (gscData.countries ?? []).length > 0) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                  {(gscData.devices ?? []).length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-slate-700 mb-2">By Device</h4>
                      <div className="space-y-2">
                        {gscData.devices!.map((d, i) => {
                          const maxClicks = Math.max(...gscData.devices!.map(x => x.clicks), 1);
                          return (
                            <div key={i}>
                              <div className="flex justify-between text-xs mb-0.5">
                                <span className="capitalize text-slate-700 font-medium">{d.device}</span>
                                <span className="text-slate-500">{d.clicks} clicks · {d.ctr}% CTR</span>
                              </div>
                              <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${(d.clicks / maxClicks) * 100}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  {(gscData.countries ?? []).length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-slate-700 mb-2">Top Countries</h4>
                      <div className="space-y-2">
                        {gscData.countries!.map((c, i) => {
                          const maxClicks = Math.max(...gscData.countries!.map(x => x.clicks), 1);
                          return (
                            <div key={i}>
                              <div className="flex justify-between text-xs mb-0.5">
                                <span className="uppercase text-slate-700 font-medium">{c.country}</span>
                                <span className="text-slate-500">{c.clicks} clicks</span>
                              </div>
                              <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                <div className="h-full bg-green-500 rounded-full" style={{ width: `${(c.clicks / maxClicks) * 100}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Sitemaps */}
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-semibold text-slate-700">🗺️ Sitemaps</h4>
                  <button
                    onClick={() => fetchSitemaps()}
                    disabled={sitemapsLoading}
                    className="text-xs px-3 py-1 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 font-medium disabled:opacity-50"
                  >
                    {sitemapsLoading ? "Loading…" : sitemaps === null ? "Load Sitemaps" : "↻ Refresh"}
                  </button>
                </div>

                {sitemapsLoading && (
                  <div className="animate-pulse space-y-2">{[1,2].map(i => <div key={i} className="h-10 bg-slate-100 rounded" />)}</div>
                )}

                {!sitemapsLoading && sitemaps !== null && sitemaps.length === 0 && (
                  <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 text-xs text-amber-800 space-y-1">
                    <p className="font-medium">⚠️ {sitemapsNote ?? "No sitemaps have been submitted to Search Console yet."}</p>
                    <p>Submitting a sitemap helps Google discover and index all your pages faster.</p>
                    <a
                      href={`https://search.google.com/search-console/sitemaps?resource_id=${encodeURIComponent(gscActiveUrl)}`}
                      target="_blank" rel="noreferrer"
                      className="inline-block mt-1 px-3 py-1 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-medium"
                    >
                      Submit a Sitemap in GSC ↗
                    </a>
                  </div>
                )}

                {!sitemapsLoading && (sitemaps ?? []).length > 0 && (
                  <div className="space-y-2">
                    {sitemaps!.map((s, i) => {
                      const indexRatio = s.submitted > 0 ? Math.round((s.indexed / s.submitted) * 100) : 0;
                      const hasIssues = s.errors > 0 || s.warnings > 0;
                      const zeroIndexed = s.submitted > 0 && s.indexed === 0;
                      // Build a GSC deep-link for this sitemap
                      const gscSitemapLink = gscActiveUrl
                        ? `https://search.google.com/search-console/sitemaps?resource_id=${encodeURIComponent(gscActiveUrl)}`
                        : "https://search.google.com/search-console/sitemaps";
                      return (
                        <div key={i} className={`rounded-lg border p-3 ${
                          s.errors > 0 ? "border-red-200 bg-red-50" :
                          s.warnings > 0 ? "border-amber-200 bg-amber-50" :
                          "border-slate-200 bg-slate-50"
                        }`}>
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-medium text-slate-800 truncate">{s.path}</p>
                              <p className="text-[10px] text-slate-400 mt-0.5">
                                Submitted {s.last_submitted ? new Date(s.last_submitted).toLocaleDateString() : "—"} · Last fetched {s.last_downloaded ? new Date(s.last_downloaded).toLocaleDateString() : "—"}
                              </p>
                            </div>
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                              {s.errors > 0 && <span className="text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded font-medium">{s.errors} error{s.errors > 1 ? "s" : ""}</span>}
                              {s.warnings > 0 && <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium">{s.warnings} warning{s.warnings > 1 ? "s" : ""}</span>}
                              {s.is_pending && <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">Pending</span>}
                              {!hasIssues && !s.is_pending && <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-medium">✓ OK</span>}
                              <a
                                href={gscSitemapLink}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[10px] text-blue-600 hover:underline whitespace-nowrap ml-1"
                                title="Open in Google Search Console"
                              >
                                View in GSC ↗
                              </a>
                            </div>
                          </div>
                          {s.submitted > 0 && (
                            <div className="mt-2">
                              <div className="flex justify-between text-[10px] text-slate-500 mb-1">
                                <span>
                                  <strong>{s.submitted.toLocaleString()}</strong> URLs in sitemap ·{" "}
                                  <strong className={s.indexed > 0 ? "text-green-700" : "text-red-600"}>{s.indexed.toLocaleString()} indexed via sitemap</strong>
                                </span>
                                <span>{indexRatio}%</span>
                              </div>
                              <div className="h-1.5 bg-white rounded-full overflow-hidden border border-slate-200">
                                <div
                                  className={`h-full rounded-full ${
                                    indexRatio >= 80 ? "bg-green-500" : indexRatio >= 50 ? "bg-amber-400" : "bg-red-400"
                                  }`}
                                  style={{ width: `${Math.max(indexRatio, indexRatio === 0 ? 0 : 4)}%` }}
                                />
                              </div>
                            </div>
                          )}
                          {/* Explain zero-indexed state so user knows what to fix */}
                          {zeroIndexed && (
                            <div className="mt-2 text-[10px] text-amber-800 bg-amber-100 rounded px-2 py-1.5 space-y-1">
                              <p className="font-semibold">⚠️ None of the sitemap URLs are indexed yet.</p>
                              <p>
                                Note: Google may have indexed other pages it discovered via links — check the full count
                                in <strong>Page Indexing</strong> inside GSC. For sitemap URLs specifically, common causes
                                are: <strong>noindex tags</strong>, <strong>robots.txt blocking</strong>, or Google needs
                                more time. Click <strong>View in GSC ↗</strong> → Not Indexed → see the 4 reasons.
                              </p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Page Indexing Breakdown */}
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h4 className="text-sm font-semibold text-slate-700">🔍 Page Indexing Breakdown</h4>
                    <p className="text-[10px] text-slate-400 mt-0.5">Inspects your sitemap URLs via Google&apos;s URL Inspection API to show exactly why pages aren&apos;t indexed.</p>
                  </div>
                  <button
                    onClick={() => fetchIndexingData(gscActiveUrl || undefined, sitemaps?.[0]?.path)}
                    disabled={indexingLoading}
                    className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium disabled:opacity-50 whitespace-nowrap"
                  >
                    {indexingLoading ? "Inspecting…" : indexingData ? "↻ Re-run" : "Run Analysis"}
                  </button>
                </div>

                {indexingLoading && (
                  <div className="space-y-2 animate-pulse">
                    <div className="h-4 bg-slate-100 rounded w-1/2" />
                    {[1,2,3].map(i => <div key={i} className="h-16 bg-slate-100 rounded-xl" />)}
                  </div>
                )}

                {!indexingLoading && indexingData?.error && (
                  <div className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">{indexingData.error}</div>
                )}

                {!indexingLoading && indexingData && !indexingData.error && (
                  <>
                    {/* Summary bar */}
                    <div className="flex gap-4 mb-4 text-xs">
                      <div className="flex items-center gap-1.5 bg-green-50 border border-green-100 rounded-lg px-3 py-2">
                        <span className="text-green-600 font-bold text-base">{indexingData.indexed ?? 0}</span>
                        <span className="text-green-700">Indexed</span>
                      </div>
                      <div className="flex items-center gap-1.5 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                        <span className="text-red-600 font-bold text-base">{indexingData.not_indexed ?? 0}</span>
                        <span className="text-red-700">Not indexed</span>
                      </div>
                      <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-500">
                        {indexingData.total_inspected ?? 0} URLs inspected
                      </div>
                    </div>

                    {/* Reasons list */}
                    <div className="space-y-3">
                      {(indexingData.reasons ?? []).map((r, i) => {
                        const colorMap: Record<string, { bg: string; border: string; badge: string; badgeText: string; bar: string }> = {
                          green:  { bg: "bg-green-50",  border: "border-green-200",  badge: "bg-green-100",  badgeText: "text-green-700",  bar: "bg-green-500"  },
                          red:    { bg: "bg-red-50",    border: "border-red-200",    badge: "bg-red-100",    badgeText: "text-red-700",    bar: "bg-red-500"    },
                          amber:  { bg: "bg-amber-50",  border: "border-amber-200",  badge: "bg-amber-100",  badgeText: "text-amber-700",  bar: "bg-amber-400"  },
                          blue:   { bg: "bg-blue-50",   border: "border-blue-200",   badge: "bg-blue-100",   badgeText: "text-blue-700",   bar: "bg-blue-400"   },
                          slate:  { bg: "bg-slate-50",  border: "border-slate-200",  badge: "bg-slate-100",  badgeText: "text-slate-600",  bar: "bg-slate-400"  },
                        };
                        const c = colorMap[r.color] ?? colorMap.slate;
                        return (
                          <div key={i} className={`rounded-xl border p-4 ${c.bg} ${c.border}`}>
                            <div className="flex items-center justify-between mb-2">
                              <span className={`text-xs font-semibold ${c.badgeText}`}>{r.label}</span>
                              <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${c.badge} ${c.badgeText}`}>{r.count} page{r.count !== 1 ? "s" : ""}</span>
                            </div>
                            {r.fix && (
                              <p className="text-[11px] text-slate-700 mb-2 leading-relaxed">{r.fix}</p>
                            )}
                            {r.urls.length > 0 && (
                              <div className="space-y-0.5">
                                <p className="text-[10px] text-slate-400 font-medium">Example URLs:</p>
                                {r.urls.map((u, j) => (
                                  <a key={j} href={u} target="_blank" rel="noreferrer"
                                    className="block text-[10px] text-blue-600 hover:underline truncate max-w-full">
                                    {u.replace(/^https?:\/\//, "")}
                                  </a>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                    <p className="text-[10px] text-slate-400 mt-2">
                      Inspected first {indexingData.total_inspected} URLs from {indexingData.sitemap_url?.replace(/^https?:\/\//, "")}.
                    </p>
                  </>
                )}

                {!indexingLoading && !indexingData && (
                  <div className="text-center py-6 text-slate-400 text-xs">
                    <p className="text-2xl mb-1">🔍</p>
                    <p>Click <strong>Run Analysis</strong> to inspect your sitemap URLs and see exactly why pages aren&apos;t indexed.</p>
                  </div>
                )}
              </div>

              {/* Daily trend sparkline */}
              {(gscData.trend ?? []).length > 1 && (
                <div>
                  <h4 className="text-sm font-semibold text-slate-700 mb-2">Daily Clicks Trend</h4>
                  <div className="flex items-end gap-0.5 h-16 bg-slate-50 rounded-lg px-3 py-2">
                    {(() => {
                      const max = Math.max(...gscData.trend!.map(t => t.clicks), 1);
                      return gscData.trend!.map((t, i) => (
                        <div key={i} title={`${t.date}: ${t.clicks} clicks`}
                          className="flex-1 bg-blue-400 rounded-sm hover:bg-blue-600 transition-colors cursor-pointer min-w-[2px]"
                          style={{ height: `${Math.max((t.clicks / max) * 100, 4)}%` }}
                        />
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
          )}
        </div>
      )}

      {/* GA4 Data */}
      {statuses.googleanalytics === "connected" && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-800">Google Analytics 4 — Last {ga4Days} Days</h3>
            <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs">
              {[7, 28, 90].map(d => (
                <button key={d} onClick={() => { setGa4Days(d); fetchGa4Data(d); }}
                  className={`px-3 py-1.5 font-medium transition-colors ${
                    ga4Days === d ? "bg-orange-500 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                  }`}>{d}d</button>
              ))}
            </div>
          </div>

          <div className="flex gap-3 mb-3">
            <input
              type="text"
              placeholder="GA4 Property ID (e.g. 123456789)"
              value={ga4PropertyId}
              onChange={e => setGa4PropertyId(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") fetchGa4Data(); }}
              className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
            <button
              onClick={() => fetchGa4Data()}
              disabled={ga4Loading || !ga4PropertyId.trim()}
              className="px-4 py-2 bg-orange-500 text-white text-sm rounded-lg hover:bg-orange-600 font-medium disabled:opacity-50"
            >
              {ga4Loading ? "Loading…" : "Fetch Data"}
            </button>
          </div>
          <p className="text-xs text-slate-400 mb-4">Find your Property ID in GA4 → Admin → Property Settings.</p>

          {ga4Loading && <div className="animate-pulse space-y-3">{[1,2].map(i=><div key={i} className="h-10 bg-slate-100 rounded"/>)}</div>}

          {!ga4Loading && ga4Data?.error && (
            <div className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">{ga4Data.error}</div>
          )}

          {!ga4Loading && ga4Data?.summary && (() => {
            const daily = ga4Data.daily ?? [];
            const avgBounce = daily.length ? round1(daily.reduce((s, d) => s + d.bounce_rate, 0) / daily.length) : 0;
            const avgDur = daily.length ? Math.round(daily.reduce((s, d) => s + d.avg_session_duration, 0) / daily.length) : 0;
            const durMin = Math.floor(avgDur / 60);
            const durSec = avgDur % 60;
            return (
              <>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
                  <MetricCard label="Sessions" value={ga4Data.summary!.total_sessions.toLocaleString()} />
                  <MetricCard label="Users" value={ga4Data.summary!.total_users.toLocaleString()} />
                  <MetricCard label="Page Views" value={ga4Data.summary!.total_views.toLocaleString()} />
                  <MetricCard label="Avg Bounce" value={`${avgBounce}%`} sub="lower = better" />
                  <MetricCard label="Avg Session" value={`${durMin}m ${durSec}s`} sub="time on site" />
                </div>

                {daily.length > 1 && (
                  <div className="mb-2">
                    <h4 className="text-sm font-semibold text-slate-700 mb-2">Daily Sessions Trend</h4>
                    <div className="flex items-end gap-0.5 h-16 bg-slate-50 rounded-lg px-3 py-2">
                      {(() => {
                        const max = Math.max(...daily.map(d => d.sessions), 1);
                        return daily.map((d, i) => (
                          <div key={i} title={`${d.date}: ${d.sessions} sessions`}
                            className="flex-1 bg-orange-400 rounded-sm hover:bg-orange-600 transition-colors cursor-pointer min-w-[2px]"
                            style={{ height: `${Math.max((d.sessions / max) * 100, 4)}%` }}
                          />
                        ));
                      })()}
                    </div>
                    <div className="flex justify-between text-[10px] text-slate-400 mt-1 px-1">
                      <span>{daily[0]?.date?.replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3")}</span>
                      <span>{daily[daily.length - 1]?.date?.replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3")}</span>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {/* Google Ads Data */}
      {statuses.googleads === "connected" && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-800">Google Ads — Last {adsDays} Days</h3>
            <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs">
              {[7, 30, 90].map(d => (
                <button key={d} onClick={() => { setAdsDays(d); fetchAdsData(d); }}
                  className={`px-3 py-1.5 font-medium transition-colors ${
                    adsDays === d ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                  }`}>{d}d</button>
              ))}
            </div>
          </div>

          <div className="flex gap-3 mb-3">
            <input
              type="text"
              placeholder="Customer ID (e.g. 123-456-7890)"
              value={adsCustomerId}
              onChange={e => setAdsCustomerId(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") fetchAdsData(); }}
              className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={() => fetchAdsData()}
              disabled={adsLoading || !adsCustomerId.trim()}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50"
            >
              {adsLoading ? "Loading…" : "Fetch Data"}
            </button>
          </div>
          <p className="text-xs text-slate-400 mb-4">Find your Customer ID in Google Ads → top-right corner (format: 123-456-7890).</p>

          {adsLoading && <div className="animate-pulse space-y-3">{[1,2].map(i=><div key={i} className="h-10 bg-slate-100 rounded"/>)}</div>}

          {!adsLoading && adsData?.error && (
            <div className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-4 py-3">{adsData.error}</div>
          )}

          {!adsLoading && adsData?.summary && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
                <MetricCard label="Total Spend" value={`$${adsData.summary.total_spend.toLocaleString()}`} />
                <MetricCard label="Clicks" value={adsData.summary.total_clicks.toLocaleString()} />
                <MetricCard label="Impressions" value={adsData.summary.total_impressions.toLocaleString()} />
                <MetricCard label="Avg CTR" value={`${adsData.summary.avg_ctr}%`} />
                <MetricCard label="Avg CPC" value={`$${adsData.summary.avg_cpc}`} />
              </div>

              {(adsData.campaigns ?? []).length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-slate-700 mb-2">Top Campaigns</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-slate-600">
                      <thead><tr className="text-left border-b border-slate-100">
                        <th className="pb-2 font-medium">Campaign</th>
                        <th className="pb-2 font-medium text-right">Spend</th>
                        <th className="pb-2 font-medium text-right">Clicks</th>
                        <th className="pb-2 font-medium text-right">Impr.</th>
                        <th className="pb-2 font-medium text-right">CTR</th>
                        <th className="pb-2 font-medium text-right">CPC</th>
                      </tr></thead>
                      <tbody>
                        {adsData.campaigns!.map((c, i) => (
                          <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                            <td className="py-1.5 font-medium text-slate-800 max-w-[180px] truncate">{c.name}</td>
                            <td className="py-1.5 text-right">${c.cost.toLocaleString()}</td>
                            <td className="py-1.5 text-right">{c.clicks.toLocaleString()}</td>
                            <td className="py-1.5 text-right">{c.impressions.toLocaleString()}</td>
                            <td className="py-1.5 text-right">{c.ctr}%</td>
                            <td className="py-1.5 text-right">${c.avg_cpc}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Zilo Activity Log */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-800 mb-1">Zilo Activity Log</h3>
        <p className="text-xs text-slate-500 mb-4">Actions tracked inside your Zilo workspace — audits, posts, keywords.</p>
        {eventsLoading ? (
          <div className="animate-pulse space-y-2">{[1,2,3].map(i=><div key={i} className="h-10 bg-slate-100 rounded"/>)}</div>
        ) : events.length === 0 ? (
          <div className="text-center py-10 text-slate-400">
            <p className="text-3xl mb-2">📋</p>
            <p className="text-sm">No activity recorded yet.</p>
            <p className="text-xs mt-1">Run an audit, generate keywords or publish a post to start tracking.</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {events.map(ev => (
              <div key={ev.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg text-sm">
                <div className="flex items-center gap-3">
                  <span className="text-base">
                    {ev.type === "post_created" ? "📝" : ev.type === "post_published" ? "🚀"
                      : ev.type === "audit_run" ? "🔍" : ev.type === "keywords_saved" ? "🎯" : "📌"}
                  </span>
                  <span className="text-slate-700 capitalize">{ev.type.replace(/_/g, " ")}</span>
                </div>
                <span className="text-xs text-slate-400">{new Date(ev.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

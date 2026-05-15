"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import BlogRenderer from "@/components/seo/BlogRenderer";
import {
  seoApi,
  blogApi,
  type SeoAudit,
  type SeoAuditIssue,
  type SeoKeyword,
  type BlogPost,
  type BlogGenerateResult,
  type ContentCalendarItem,
  type SeoSummary,
  type SeoBusinessContext,
} from "@/lib/api";
import OnboardingChecklist from "@/components/seo/OnboardingChecklist";
import SuccessMetrics from "@/components/seo/SuccessMetrics";
import IndustryTemplateSelector from "@/components/seo/IndustryTemplateSelector";
import ROITracking from "@/components/seo/ROITracking";
import AutoScheduler from "@/components/seo/AutoScheduler";
import AnalyticsIntegration from "@/components/seo/AnalyticsIntegration";
import LocalSEO from "@/components/seo/LocalSEO";
import SocialIntegration from "@/components/seo/SocialIntegration";
import SeoHubWorkspace from "@/components/seo/SeoHubWorkspace";
import { toast } from "sonner";
import AutoblogPanel from "@/components/seo/AutoblogPanel";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  CalendarDays,
  Clock,
  MapPin,
  PenLine,
  Rss,
  Search,
  Share2,
  Sparkles,
  TrendingUp,
  Wrench,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Tabs ─────────────────────────────────────────────────────────────────────

type Tab =
  | "hub"
  | "overview"
  | "audit"
  | "keywords"
  | "blog"
  | "calendar"
  | "autoblog"
  | "roi"
  | "scheduler"
  | "analytics"
  | "local"
  | "social";

const SEO_TABS: Tab[] = [
  "hub",
  "keywords",
  "blog",
  "calendar",
  "scheduler",
  "autoblog",
  "social",
  "local",
  "analytics",
  "overview",
  "audit",
  "roi",
];

function normalizeSeoTabParam(raw: string | null): Tab {
  if (!raw) return "hub";
  if (raw === "agent") return "hub";
  if (SEO_TABS.includes(raw as Tab)) return raw as Tab;
  return "hub";
}

/** Left-to-right = typical workflow: coach → research → write → plan → automate → distribute → measure → improve */
const SEO_TAB_DEFS: { id: Tab; label: string; short: string; desc: string; Icon: LucideIcon }[] = [
  { id: "hub", label: "Start here", short: "Start", desc: "Coach & tracker", Icon: Sparkles },
  { id: "keywords", label: "Keywords", short: "Keys", desc: "Research topics", Icon: Search },
  { id: "blog", label: "Write posts", short: "Write", desc: "Drafts & articles", Icon: PenLine },
  { id: "calendar", label: "Calendar", short: "Plan", desc: "Content calendar", Icon: CalendarDays },
  { id: "scheduler", label: "Schedule", short: "Sched", desc: "When posts go live", Icon: Clock },
  { id: "autoblog", label: "Autoblog", short: "Auto", desc: "Hands-off blog site", Icon: Rss },
  { id: "social", label: "Social", short: "Social", desc: "Share & syndicate", Icon: Share2 },
  { id: "local", label: "Local SEO", short: "Local", desc: "Maps & listings", Icon: MapPin },
  { id: "analytics", label: "Analytics", short: "Data", desc: "Traffic & tracking", Icon: Activity },
  { id: "overview", label: "Stats", short: "Stats", desc: "Progress overview", Icon: BarChart3 },
  { id: "audit", label: "Audit", short: "Audit", desc: "Site health check", Icon: Wrench },
  { id: "roi", label: "ROI", short: "ROI", desc: "Results & value", Icon: TrendingUp },
];

type CalendarWritePayload = { title: string; keywords: string[] };

// ── Helpers ───────────────────────────────────────────────────────────────────

function HelpTooltip({ text }: { text: string }) {
  return (
    <span className="group relative inline-block ml-1">
      <span className="text-slate-400 hover:text-slate-600 cursor-help text-xs">ⓘ</span>
      <span className="invisible group-hover:visible absolute left-0 top-5 z-10 w-48 bg-slate-800 text-white text-xs rounded-lg px-3 py-2 shadow-lg">
        {text}
      </span>
    </span>
  );
}

function ScoreBadge({ score, grade }: { score: number; grade: string }) {
  const color =
    score >= 90 ? "bg-green-100 text-green-700 border-green-200"
    : score >= 75 ? "bg-blue-100 text-blue-700 border-blue-200"
    : score >= 60 ? "bg-yellow-100 text-yellow-700 border-yellow-200"
    : score >= 40 ? "bg-orange-100 text-orange-700 border-orange-200"
    : "bg-red-100 text-red-700 border-red-200";
  const label = score >= 90 ? "Excellent" : score >= 75 ? "Good" : score >= 60 ? "Fair" : score >= 40 ? "Needs work" : "Poor";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${color}`}>
      {label} · {score}/100
    </span>
  );
}

function IssuePill({ type }: { type: SeoAuditIssue["type"] }) {
  const styles = {
    critical: "bg-red-100 text-red-700",
    warning: "bg-yellow-100 text-yellow-700",
    info: "bg-blue-100 text-blue-700",
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase ${styles[type]}`}>
      {type}
    </span>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <p className="text-xs text-slate-500 font-medium">{label}</p>
      <p className="text-2xl font-bold text-slate-800 mt-1">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function BusinessSnapshotBar({ profile }: { profile: SeoBusinessContext | null }) {
  const name = profile?.business_name?.trim();
  const industry = profile?.business_type?.trim()?.replace(/-/g, " ");
  const loc = profile?.location?.trim();
  const lang = profile?.language?.trim();
  const linedUp = Boolean(name || industry || loc);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-slate-200/90 bg-slate-50/50 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:px-4 sm:py-3">
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Business context</p>
        <p className="truncate text-sm font-semibold text-slate-900">
          {name || (industry ? industry.charAt(0).toUpperCase() + industry.slice(1) : "Add your business")}
        </p>
        <p className="text-xs leading-snug text-slate-500">
          {linedUp ? (
            <>
              {[industry, loc].filter(Boolean).join(" · ") || "Industry & area from Settings"}
              {lang ? <span className="text-slate-400"> · {lang}</span> : null}
            </>
          ) : (
            <>Add name and location in Settings so keywords and content match your brand.</>
          )}
        </p>
      </div>
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2">
        <Link
          href="/dashboard/settings"
          className="inline-flex items-center justify-center rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50"
        >
          Business settings
        </Link>
        {profile?.live_keyword_data && (
          <span className="inline-flex items-center rounded-md border border-emerald-100 bg-white px-2 py-1 text-[10px] font-medium text-emerald-800">
            Live search data
          </span>
        )}
      </div>
    </div>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

type SeoMemory = {
  audit_history: { date: string; score: number; url: string; critical_issues: string[] }[];
  published_count: number;
  draft_count: number;
  published_topics: { title: string; tags: string[]; keywords: string[] }[];
  score_trend: "improving" | "declining" | "stable";
  analysis: { working: string[]; not_working: string[]; next_month_focus: string[]; score_trend: string };
  kw_months: string[];
};

function OverviewTab({ summary, onJump, profile }: { summary: SeoSummary | null; onJump: (t: Tab) => void; profile: SeoBusinessContext | null }) {
  const [suggestions, setSuggestions] = useState<{ priority: string; action: string; detail: string }[]>([]);
  const [loadingSugg, setLoadingSugg] = useState(true);
  const [memory, setMemory] = useState<SeoMemory | null>(null);
  const [loadingMem, setLoadingMem] = useState(true);
  const [showTemplates, setShowTemplates] = useState(false);

  const extSummary = summary as (SeoSummary & { audit_trend?: { date: string; score: number; url: string }[] }) | null;

  useEffect(() => {
    seoApi.improvementSuggestions()
      .then(r => setSuggestions(r.suggestions ?? []))
      .catch(() => {})
      .finally(() => setLoadingSugg(false));
    seoApi.getSeoMemory()
      .then(setMemory)
      .catch(() => {})
      .finally(() => setLoadingMem(false));
  }, []);

  if (!summary) return <p className="text-slate-400 text-sm">Loading summary…</p>;

  const trend = extSummary?.audit_trend ?? [];

  const priorityStyle = (p: string) =>
    p === "high" ? "bg-red-50 border-red-100 text-red-700"
    : p === "medium" ? "bg-yellow-50 border-yellow-100 text-yellow-700"
    : "bg-slate-50 border-slate-100 text-slate-500";

  return (
    <div className="space-y-6">
      {/* Success Metrics Dashboard */}
      <SuccessMetrics />

      {/* Onboarding Checklist - show for new users */}
      {(summary.total_posts === 0 || !profile?.business_type) && (
        <OnboardingChecklist profile={profile} />
      )}

      {/* Industry Template Selector - show if no business type set */}
      {!profile?.business_type && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-800">Get Started Faster</h3>
              <p className="text-sm text-slate-500 mt-1">
                Choose your industry to get pre-configured SEO strategies
              </p>
            </div>
            <button
              onClick={() => setShowTemplates(!showTemplates)}
              className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 font-medium"
            >
              {showTemplates ? "Hide Templates" : "Browse Templates"}
            </button>
          </div>
          
          {showTemplates && (
            <IndustryTemplateSelector
              onSelect={(template) => {
                // This would update the user's profile
                window.location.href = "/dashboard/settings";
              }}
            />
          )}
        </div>
      )}

      {/* Quick Stats */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-800">Quick Overview</h3>
          <div className="flex gap-2">
            <button
              onClick={() => onJump("keywords")}
              className="px-3 py-1.5 bg-purple-100 text-purple-700 text-xs rounded-lg hover:bg-purple-200 font-medium"
            >
              Keywords
            </button>
            <button
              onClick={() => onJump("calendar")}
              className="px-3 py-1.5 bg-emerald-100 text-emerald-700 text-xs rounded-lg hover:bg-emerald-200 font-medium"
            >
              Calendar
            </button>
            <button
              onClick={() => onJump("blog")}
              className="px-3 py-1.5 bg-blue-100 text-blue-700 text-xs rounded-lg hover:bg-blue-200 font-medium"
            >
              Posts
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard label="Total Blog Posts" value={summary.total_posts ?? 0} />
          <StatCard label="Published" value={summary.published_posts ?? 0} />
          <StatCard label="Drafts" value={summary.draft_posts ?? 0} />
          <StatCard label="Site Audits Run" value={summary.total_audits ?? 0} />
        </div>
      </div>

      {/* Score trend */}
      {trend.length > 1 && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-1">Audit Score Trend</p>
          <div className="flex items-end gap-2 h-20">
            {trend.map((t, i) => {
              const h = Math.max(8, Math.round((t.score / 100) * 80));
              const color = t.score >= 75 ? "bg-green-400" : t.score >= 50 ? "bg-yellow-400" : "bg-red-400";
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1" title={`${t.url}\n${t.score}/100 · ${t.date?.slice(0, 10) ?? ""}`}>
                  <span className="text-[9px] text-slate-400 font-medium">{t.score}</span>
                  <div className={`w-full rounded-t-sm ${color}`} style={{ height: `${h}px` }} />
                </div>
              );
            })}
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-slate-400">{trend[0]?.date?.slice(0, 10) ?? ""}</span>
            <span className="text-[10px] text-slate-400">{trend[trend.length - 1]?.date?.slice(0, 10) ?? ""}</span>
          </div>
        </div>
      )}

      {summary.avg_seo_score !== null && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-2">Average SEO Score (last 5 audits)</p>
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-slate-100 rounded-full h-3">
              <div className="h-3 rounded-full bg-green-500 transition-all" style={{ width: `${summary.avg_seo_score}%` }} />
            </div>
            <span className="text-lg font-bold text-slate-800">{summary.avg_seo_score}/100</span>
          </div>
        </div>
      )}

      {summary.last_audit && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-3">Last Audit</p>
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-medium text-slate-800 break-all">{summary.last_audit.url}</p>
              <p className="text-xs text-slate-400 mt-0.5">{summary.last_audit.created_at ? new Date(summary.last_audit.created_at).toLocaleString() : ""}</p>
            </div>
            <ScoreBadge score={summary.last_audit.score ?? 0} grade={summary.last_audit.grade ?? ""} />
          </div>
          <div className="mt-3 flex gap-4 text-xs text-slate-500">
            <span>{(summary.last_audit.issues ?? []).filter(i => i.type === "critical").length} critical</span>
            <span>{(summary.last_audit.issues ?? []).filter(i => i.type === "warning").length} warnings</span>
            <span>{(summary.last_audit.issues ?? []).filter(i => i.type === "info").length} info</span>
          </div>
        </div>
      )}

      {/* SEO Memory — progressive improvement */}
      {(loadingMem || memory) && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-slate-700">🧠 SEO Memory — what worked this cycle</p>
            {loadingMem && <span className="text-[10px] text-slate-400">Analysing history…</span>}
            {memory && (
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                memory.score_trend === "improving" ? "bg-green-100 text-green-700"
                : memory.score_trend === "declining" ? "bg-red-100 text-red-600"
                : "bg-slate-100 text-slate-500"
              }`}>
                {memory.score_trend === "improving" ? "📈 Score improving"
                  : memory.score_trend === "declining" ? "📉 Score declining"
                  : "➡ Score stable"}
              </span>
            )}
          </div>

          {memory && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* What's working */}
              <div className="rounded-xl bg-green-50 border border-green-100 p-3">
                <p className="text-xs font-bold text-green-800 mb-2">✅ Working</p>
                {memory.analysis.working.length === 0
                  ? <p className="text-xs text-green-700 opacity-60">No data yet — publish posts and run audits to track progress.</p>
                  : <ul className="space-y-1">
                    {memory.analysis.working.map((w, i) => (
                      <li key={i} className="text-xs text-green-800 flex gap-1.5"><span className="shrink-0 mt-0.5">•</span>{w}</li>
                    ))}
                  </ul>
                }
              </div>

              {/* What's not working */}
              <div className="rounded-xl bg-red-50 border border-red-100 p-3">
                <p className="text-xs font-bold text-red-700 mb-2">⚠ Needs fixing</p>
                {memory.analysis.not_working.length === 0
                  ? <p className="text-xs text-red-700 opacity-60">Run an audit to find issues.</p>
                  : <ul className="space-y-1">
                    {memory.analysis.not_working.map((w, i) => (
                      <li key={i} className="text-xs text-red-800 flex gap-1.5"><span className="shrink-0 mt-0.5">•</span>{w}</li>
                    ))}
                  </ul>
                }
              </div>

              {/* Next month focus */}
              <div className="rounded-xl bg-blue-50 border border-blue-100 p-3">
                <p className="text-xs font-bold text-blue-800 mb-2">🎯 Next month</p>
                {memory.analysis.next_month_focus.length === 0
                  ? <p className="text-xs text-blue-700 opacity-60">Suggestions will appear once you have audit + content history.</p>
                  : <ul className="space-y-1">
                    {memory.analysis.next_month_focus.map((w, i) => (
                      <li key={i} className="text-xs text-blue-800 flex gap-1.5"><span className="shrink-0 mt-0.5">→</span>{w}</li>
                    ))}
                  </ul>
                }
                {memory.analysis.next_month_focus.length > 0 && (
                  <button
                    onClick={() => onJump("calendar")}
                    className="mt-3 text-[10px] px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-semibold"
                  >
                    Plan next month →
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Published topics history */}
          {memory && memory.published_topics.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-600 mb-2">📝 Published this cycle ({memory.published_count} posts)</p>
              <div className="flex flex-wrap gap-1.5">
                {memory.published_topics.map((t, i) => (
                  <span key={i} className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full border border-slate-200">
                    {t.title.length > 45 ? t.title.slice(0, 45) + "…" : t.title}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Monthly improvement suggestions */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-semibold text-slate-700">💡 Improvement suggestions for next month</p>
          {loadingSugg && <span className="text-[10px] text-slate-400">Analysing…</span>}
        </div>
        {suggestions.length === 0 && !loadingSugg && (
          <p className="text-xs text-slate-400">Run an audit and save keywords to get personalised suggestions.</p>
        )}
        <div className="space-y-2">
          {suggestions.map((s, i) => (
            <div key={i} className={`flex gap-3 items-start rounded-lg border p-3 ${priorityStyle(s.priority)}`}>
              <span className="text-[10px] font-bold uppercase shrink-0 mt-0.5">{s.priority}</span>
              <div>
                <p className="text-xs font-semibold">{s.action}</p>
                <p className="text-xs opacity-80 mt-0.5">{s.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Audit Tab ─────────────────────────────────────────────────────────────────

function AuditTab() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [rerunningId, setRerunningId] = useState<string | null>(null);
  const [audit, setAudit] = useState<SeoAudit | null>(null);
  const [fixes, setFixes] = useState<{ field: string; issue: string; fix: string; example: string }[] | null>(null);
  const [fixLoading, setFixLoading] = useState(false);
  const [history, setHistory] = useState<SeoAudit[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    seoApi.listAudits().then(setHistory).catch(() => {});
  }, []);

  async function runAudit(targetUrl?: string) {
    const auditUrl = (targetUrl ?? url).trim();
    if (!auditUrl) return;
    if (!targetUrl) setUrl(auditUrl);
    setLoading(true); setErr(""); setAudit(null); setFixes(null);
    try {
      const result = await seoApi.audit(auditUrl);
      setAudit(result);
      setHistory(h => [result, ...h.filter(a => a.url !== result.url).slice(0, 49)]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Audit failed");
    } finally {
      setLoading(false);
    }
  }

  async function rerunAudit(historyAudit: SeoAudit) {
    const auditUrl = historyAudit.url ?? "";
    if (!auditUrl) return;
    setUrl(auditUrl);
    setRerunningId(historyAudit.id ?? null);
    setErr(""); setAudit(null); setFixes(null);
    try {
      const result = await seoApi.audit(auditUrl);
      setAudit(result);
      setHistory(h => [result, ...h.filter(a => a.id !== historyAudit.id).slice(0, 49)]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Audit failed");
    } finally {
      setRerunningId(null);
    }
  }

  async function getAiFixes() {
    if (!audit) return;
    setFixLoading(true);
    try {
      const res = await seoApi.aiFixSuggestions(audit.url ?? "");
      setFixes(res.suggestions as { field: string; issue: string; fix: string; example: string; }[]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "AI fix failed");
    } finally {
      setFixLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <p className="text-sm font-semibold text-slate-800 mb-1">Check any website</p>
        <p className="text-xs text-slate-500 mb-3">Paste a page URL — we&apos;ll score titles, headings, meta, and images in seconds.</p>
        <div className="flex gap-2">
          <input
            className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder="https://yourclientsite.com"
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runAudit()}
          />
          <button
            onClick={() => runAudit()}
            disabled={loading || !url.trim()}
            className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg font-semibold hover:bg-emerald-700 disabled:opacity-50 shrink-0"
          >
            {loading ? "Auditing…" : "Audit"}
          </button>
        </div>
        {err && <p className="text-red-500 text-xs mt-2">{err}</p>}
      </div>

      {audit && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-semibold text-slate-800 break-all">{audit.url}</p>
              <p className="text-xs text-slate-400 mt-0.5">{audit.word_count} words · {audit.total_images} images · {audit.images_missing_alt} missing alt</p>
            </div>
            <ScoreBadge score={audit.score ?? 0} grade={audit.grade ?? ""} />
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">Main heading<HelpTooltip text="H1 tag = main page title. Should have exactly 1 per page." /></p>
              <p className={`text-xl font-bold ${audit.h1_count === 1 ? "text-green-600" : "text-red-500"}`}>{audit.h1_count}</p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">Subheadings<HelpTooltip text="H2 tags = section titles. Break up your content for easier reading." /></p>
              <p className="text-xl font-bold text-slate-700">{audit.h2_count}</p>
            </div>
            <div className="bg-slate-50 rounded-lg p-3">
              <p className="text-xs text-slate-500">Issues</p>
              <p className={`text-xl font-bold ${audit.issues.length === 0 ? "text-green-600" : "text-orange-500"}`}>{audit.issues.length}</p>
            </div>
          </div>

          {audit.issues.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Issues Found</p>
              {audit.issues.map((issue, i) => (
                <div key={i} className="flex gap-3 items-start border border-slate-100 rounded-lg p-3">
                  <IssuePill type={issue.type} />
                  <div>
                    <p className="text-xs font-medium text-slate-700">{issue.field}</p>
                    <p className="text-xs text-slate-500">{issue.message}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={getAiFixes}
            disabled={fixLoading}
            className="w-full py-2 bg-slate-800 text-white text-sm rounded-lg font-medium hover:bg-slate-900 disabled:opacity-50"
          >
            {fixLoading ? "Getting AI fixes…" : "Get AI Fix Suggestions"}
          </button>

          {fixes && fixes.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">AI Recommendations</p>
              {fixes.map((f, i) => (
                <div key={i} className="bg-green-50 border border-green-100 rounded-lg p-3 space-y-1">
                  <p className="text-xs font-bold text-green-800 uppercase">{f.field}</p>
                  <p className="text-xs text-slate-600"><span className="font-medium">Issue:</span> {f.issue}</p>
                  <p className="text-xs text-slate-600"><span className="font-medium">Fix:</span> {f.fix}</p>
                  {f.example && (
                    <p className="text-xs text-slate-500 italic bg-white rounded p-2 border border-green-100">{f.example}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-sm font-semibold text-slate-700 mb-3">Audit History</p>
          <div className="space-y-2">
            {history.slice(0, 10).map((a) => (
              <div key={a.id} className="flex items-center justify-between gap-3 py-2 border-b border-slate-50 last:border-0">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-slate-700 truncate">{a.url}</p>
                  <p className="text-xs text-slate-400">{a.created_at ? new Date(a.created_at).toLocaleDateString() : ""}</p>
                </div>
                <ScoreBadge score={a.score ?? 0} grade={a.grade ?? ""} />
                <button
                  onClick={() => rerunAudit(a)}
                  disabled={rerunningId === a.id || loading}
                  title="Re-run audit"
                  className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium text-slate-600 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 disabled:opacity-50 transition-colors shrink-0"
                >
                  <RefreshCw size={10} className={rerunningId === a.id ? "animate-spin" : ""} />
                  {rerunningId === a.id ? "Running…" : "Re-run"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Keywords Tab ──────────────────────────────────────────────────────────────

function KeywordsTab({ profile, onJump, onPushToCalendar }: { profile: SeoBusinessContext | null; onJump: (t: Tab) => void; onPushToCalendar?: (kws: SeoKeyword[]) => void }) {
  const [businessType, setBusinessType] = useState("");
  const [location, setLocation] = useState("");
  const [loading, setLoading] = useState(false);
  const [keywords, setKeywords] = useState<SeoKeyword[]>([]);
  const [keywordSource, setKeywordSource] = useState<"dataforseo" | "ai" | "saved" | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMonth, setSavedMonth] = useState<string | null>(null);
  const [savedKeywordSets, setSavedKeywordSets] = useState<{ month: string; count: number; business_type: string; location: string; saved_at: string }[]>([]);
  const [loadingSavedSets, setLoadingSavedSets] = useState(false);
  const [err, setErr] = useState("");
  const [excludedCount, setExcludedCount] = useState(0);
  const [kwPublishing, setKwPublishing] = useState<Record<number, "idle" | "generating" | "publishing" | "done" | "error">>({});
  const [kwPublishUrl, setKwPublishUrl] = useState<Record<number, string>>({});

  async function publishKeywordToBlog(kw: SeoKeyword, idx: number) {
    setKwPublishing(p => ({ ...p, [idx]: "generating" }));
    try {
      const post = await seoApi.generateBlog({
        topic: kw.content_idea || kw.keyword,
        keywords: [kw.keyword],
        tone: "professional",
        length: "medium",
        business_name: profile?.business_name,
        language: profile?.language || "English",
        include_faq: true,
      });
      setKwPublishing(p => ({ ...p, [idx]: "publishing" }));
      const result = await blogApi.publishFromSeo({
        title: post.title,
        content: post.content,
        keywords: post.keywords || [kw.keyword],
        excerpt: post.meta_description,
      });
      setKwPublishUrl(p => ({ ...p, [idx]: result.post_url }));
      setKwPublishing(p => ({ ...p, [idx]: "done" }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Publish failed — is your Autoblog activated?");
      setKwPublishing(p => ({ ...p, [idx]: "error" }));
    }
  }

  useEffect(() => {
    if (!profile) return;
    setBusinessType((t) => (t.trim() ? t : profile.business_type));
    setLocation((t) => (t.trim() ? t : profile.location));
  }, [profile]);

  useEffect(() => {
    loadSavedKeywordSets();
  }, []);

  async function generate() {
    setLoading(true);
    setErr("");
    setSavedMonth(null);
    try {
      const res = await seoApi.generateKeywords(businessType.trim(), location.trim());
      const list = res.keywords as SeoKeyword[];
      setKeywords(list);
      setKeywordSource(res.keyword_source);
      setExcludedCount(res.excluded_count ?? 0);
      const { ok, month } = await saveForMonthQuiet(list);
      if (ok && month) {
        toast.success(`Saved for ${month}`, {
          description: `${list.length} keyword ideas — reload anytime under Earlier saved lists.`,
        });
      } else if (list.length > 0) {
        toast.error("Could not save to the cloud", {
          description: "Your list is still on screen — tap Save again or check your connection.",
        });
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadSavedKeywordSets() {
    setLoadingSavedSets(true);
    try {
      setSavedKeywordSets(await seoApi.listSavedKeywords());
    } catch {
      setSavedKeywordSets([]);
    } finally {
      setLoadingSavedSets(false);
    }
  }

  /** Persist keyword rows (includes search_volume, difficulty, intent when present). */
  async function persistKeywordsToServer(toSave: SeoKeyword[]) {
    const res = await seoApi.saveKeywords({
      keywords: toSave as unknown as Record<string, unknown>[],
      business_type: businessType.trim() || profile?.business_type || "",
      location: location.trim() || profile?.location || "",
    });
    setSavedMonth(res.month);
    await loadSavedKeywordSets();
    return res;
  }

  async function saveForMonthQuiet(toSave: SeoKeyword[]): Promise<{ ok: boolean; month?: string }> {
    if (!toSave.length) return { ok: false };
    try {
      const res = await persistKeywordsToServer(toSave);
      return { ok: true, month: res.month };
    } catch {
      return { ok: false };
    }
  }

  async function saveForMonth() {
    if (!keywords.length) return;
    setSaving(true);
    setErr("");
    try {
      const res = await persistKeywordsToServer(keywords);
      toast.success(`Saved for ${res.month}`, {
        description: `${keywords.length} phrases kept (volumes included when present).`,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  async function loadKeywordSet(month: string) {
    try {
      const res = await seoApi.getSavedKeywords(month);
      const savedKeywords = res.keywords as unknown as SeoKeyword[];
      setKeywords(savedKeywords);
      setKeywordSource("saved");
      setSavedMonth(month);
      setBusinessType(res.business_type || profile?.business_type || "");
      setLocation(res.location || profile?.location || "");
      setErr("");
      toast.success(`Loaded ${savedKeywords.length} keywords`, {
        description: `Saved list for ${month} — volumes and intent restored when stored.`,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load saved keywords");
    }
  }

  const difficultyColor = (d: string) =>
    d === "low" ? "text-green-600" : d === "medium" ? "text-yellow-600" : "text-red-500";

  const intentColor = (i: string) =>
    i === "transactional" ? "bg-green-100 text-green-700"
    : i === "local" ? "bg-blue-100 text-blue-700"
    : i === "informational" ? "bg-purple-100 text-purple-700"
    : "bg-slate-100 text-slate-600";

  const usingProfile =
    Boolean(profile?.business_name?.trim()) ||
    Boolean(profile?.business_type?.trim()) ||
    Boolean(profile?.location?.trim());

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">Keywords for your business</p>
          <p className="text-xs text-slate-500 mt-1">
            {usingProfile
              ? "We’ll use your Settings profile (below). One tap — optional tweaks in “Fine-tune”."
              : "Add your business in Settings for best results — or fine-tune below."}
          </p>
          {usingProfile && (
            <p className="text-xs text-slate-600 mt-2 rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
              <span className="font-medium text-slate-700">Using:</span>{" "}
              {[profile?.business_name?.trim(), profile?.business_type?.replace(/-/g, " "), profile?.location?.trim()]
                .filter(Boolean)
                .join(" · ") || "Saved profile"}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="w-full sm:w-auto min-h-[44px] px-6 py-3 bg-emerald-600 text-white text-sm font-semibold rounded-xl hover:bg-emerald-700 disabled:opacity-50 shadow-sm"
        >
          {loading ? "Finding keywords…" : "Get keyword ideas"}
        </button>

        <details className="group rounded-xl border border-slate-100 bg-slate-50/50">
          <summary className="cursor-pointer text-xs font-semibold text-slate-600 px-3 py-2.5 list-none flex items-center justify-between [&::-webkit-details-marker]:hidden">
            Fine-tune industry or location
            <span className="text-slate-400 group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div className="px-3 pb-3 pt-0 grid grid-cols-1 sm:grid-cols-2 gap-3 border-t border-slate-100 bg-white rounded-b-xl">
            <div className="pt-3">
              <label className="text-xs text-slate-500 font-medium block mb-1">Industry</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                placeholder="e.g. hair salon, law firm"
                value={businessType}
                onChange={e => setBusinessType(e.target.value)}
              />
            </div>
            <div className="pt-3">
              <label className="text-xs text-slate-500 font-medium block mb-1">Location</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                placeholder="City or region"
                value={location}
                onChange={e => setLocation(e.target.value)}
              />
            </div>
          </div>
        </details>

        <p className="text-[11px] text-slate-400">
          After you run a search, keywords are <span className="font-medium text-slate-500">saved for the current month</span>
          (phrase, volume when available, difficulty, intent, content idea). Reload another month from the list below if you need it.
          Blank fields use Settings.
          {profile?.live_keyword_data ? " Live Google volumes when DataForSEO is enabled." : ""}
        </p>
        {err && <p className="text-red-500 text-xs">{err}</p>}
      </div>

      {keywords.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 flex-wrap min-w-0">
              <p className="text-sm font-semibold text-slate-700">
                {keywords.length} fresh keyword ideas
                <HelpTooltip text="These are phrases people search on Google. Already-researched keywords are automatically excluded so you always get new ideas." />
              </p>
              {excludedCount > 0 && (
                <span className="text-[10px] text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-100">
                  {excludedCount} already known — skipped
                </span>
              )}
              {keywordSource === "dataforseo" && (
                <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-800 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded-full">
                  Live data · DataForSEO
                </span>
              )}
              {keywordSource === "ai" && (
                <span className="text-[10px] font-medium text-slate-500 bg-slate-50 px-2 py-0.5 rounded-full">
                  AI suggestions{profile?.live_keyword_data ? " (DataForSEO unavailable or no results)" : ""}
                </span>
              )}
              {keywordSource === "saved" && (
                <span className="text-[10px] font-medium text-slate-600 bg-violet-50 border border-violet-100 px-2 py-0.5 rounded-full">
                  Loaded from saved month
                </span>
              )}
            </div>
          </div>

          {savedMonth && (
            <div className="mx-5 mt-4 rounded-xl border border-emerald-200/90 bg-emerald-50/80 px-4 py-3">
              <p className="text-sm font-semibold text-emerald-900">Saved for {savedMonth}</p>
              <p className="text-xs text-emerald-800/90 mt-1 leading-relaxed">
                {keywords.length} phrases on file (volumes and intent kept when available). Reload an older month from the list below if you need past research.
              </p>
            </div>
          )}

          <div className="px-5 pt-4 pb-2">
            <button
              type="button"
              onClick={() => {
                toast.message("Opening your calendar", {
                  description: "We'll build your schedule from these keyword ideas.",
                });
                onPushToCalendar?.(keywords);
                onJump("calendar");
              }}
              className="flex w-full min-h-[48px] items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700"
            >
              <CalendarDays className="h-4 w-4 shrink-0 opacity-95" aria-hidden />
              Continue to calendar — plan posts from these topics
              <ArrowRight className="h-4 w-4 shrink-0 opacity-90" aria-hidden />
            </button>
            <p className="mt-2 text-center text-[11px] text-slate-500">
              Your list is already saved for this month when possible — this step just opens the planner with these topics.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 px-5 pb-4">
            <button
              type="button"
              onClick={saveForMonth}
              disabled={saving}
              className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 bg-white font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save again (overwrites this month)"}
            </button>
          </div>

          {savedKeywordSets.length > 0 && (
            <div className="px-5 py-3 border-t border-slate-100 bg-slate-50">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Earlier saved lists (volumes kept)</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {savedKeywordSets.map(set => (
                  <div key={set.month} className="rounded-xl border border-slate-200 bg-white p-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">{set.month}</p>
                      <p className="text-[11px] text-slate-500">{set.count} keywords · {set.business_type || "No industry"}{set.location ? ` · ${set.location}` : ""}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => loadKeywordSet(set.month)}
                      className="text-[10px] px-3 py-1 bg-slate-800 text-white rounded-lg hover:bg-slate-900"
                    >
                      Load
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="divide-y divide-slate-50">
            {keywords.map((kw, i) => (
              <div key={i} className="px-5 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium text-slate-800">{kw.keyword}</p>
                      {/* Tracking status badge */}
                      {(kw as any).status === "published" && (
                        <span className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 border border-green-200">✓ Published</span>
                      )}
                      {(kw as any).status === "draft" && (
                        <span className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">Draft exists</span>
                      )}
                      {/* Strategy type badge */}
                      {(kw as any).strategy_type && (
                        <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                          {String((kw as any).strategy_type).replace(/-/g, " ")}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600 mt-0.5">💡 {kw.content_idea}</p>
                    {kw.search_volume != null && kw.search_volume > 0 && (
                      <p className="text-[11px] text-slate-500 mt-1">
                        ~{kw.search_volume.toLocaleString()} searches/mo
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2 shrink-0 items-center flex-wrap justify-end">
                    <span className={`text-xs font-semibold capitalize ${difficultyColor(String(kw.difficulty ?? ""))}`}>
                      {kw.difficulty === "low" ? "Easy" : kw.difficulty === "medium" ? "Medium" : "Hard"}
                    </span>
                    {kwPublishing[i] === "done" ? (
                      <a href={kwPublishUrl[i]} target="_blank" rel="noopener noreferrer"
                        className="text-[10px] px-2 py-1 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 whitespace-nowrap">
                        ✓ View post →
                      </a>
                    ) : (
                      <button
                        onClick={() => publishKeywordToBlog(kw, i)}
                        disabled={kwPublishing[i] === "generating" || kwPublishing[i] === "publishing"}
                        className="text-[10px] px-2 py-1 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-60 whitespace-nowrap"
                      >
                        {kwPublishing[i] === "generating" ? "Writing…" : kwPublishing[i] === "publishing" ? "Publishing…" : "→ Publish"}
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <span className="text-[10px] text-slate-500 font-medium">Priority:</span>
                  <div className="flex gap-1">
                    {Array.from({ length: 5 }, (_, p) => (
                      <div key={p} className={`h-1.5 w-3 rounded-full ${p < (kw.priority ?? 0) ? "bg-green-500" : "bg-slate-200"}`} />
                    ))}
                  </div>
                  {(kw as any).intent && (
                    <span className={`ml-1 text-[10px] px-1.5 py-0.5 rounded-full font-medium ${intentColor(String((kw as any).intent))}`}>
                      {(kw as any).intent}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Blog Templates ────────────────────────────────────────────────────────────

const BLOG_TEMPLATES = [
  {
    id: "how-to",
    name: "How-to Guide",
    icon: "🔧",
    desc: "Step-by-step instructions",
    structure: "Intro → Steps 1-5 → Pro tips → FAQ → Conclusion",
    hint: "Structure as a practical how-to guide with clearly numbered steps, a tips box, and a strong conclusion with a CTA.",
  },
  {
    id: "listicle",
    name: "Top 5 List",
    icon: "📋",
    desc: "Engaging numbered list",
    structure: "Hook → 5-7 items with details → Summary → CTA",
    hint: "Structure as a compelling listicle with a punchy hook, numbered items each with a heading and 2-3 sentences, and a summary.",
  },
  {
    id: "case-study",
    name: "Success Story",
    icon: "⭐",
    desc: "Problem → Solution → Results",
    structure: "The Challenge → Our Approach → Results → Takeaways",
    hint: "Structure as a case study: relatable problem, the solution taken, concrete results with numbers, and key takeaways.",
  },
  {
    id: "local",
    name: "Local Authority",
    icon: "📍",
    desc: "Rank in your city/area",
    structure: "Local intro → Area insights → Expert tips → Local CTA",
    hint: "Reference the specific city or region, provide local context and tips, and establish the business as a trusted local authority.",
  },
  {
    id: "educational",
    name: "Deep Dive",
    icon: "🎓",
    desc: "Educate your audience",
    structure: "What is it? → Why it matters → How it works → Common mistakes → FAQ",
    hint: "Structure as an educational article: explain concepts clearly, use examples, debunk common myths, and provide actionable takeaways.",
  },
  {
    id: "comparison",
    name: "Comparison / vs.",
    icon: "⚖️",
    desc: "Compare options clearly",
    structure: "Overview → Option A vs B → Pros & Cons table → Verdict",
    hint: "Structure as a comparison piece: introduce the options, compare them across key criteria with a pros/cons style, and give a clear recommendation.",
  },
] as const;

type BlogTemplateId = (typeof BLOG_TEMPLATES)[number]["id"];

// ── Blog Tab ──────────────────────────────────────────────────────────────────

function BlogTab({ profile, prefillTopic }: { profile: SeoBusinessContext | null; prefillTopic?: CalendarWritePayload }) {
  const [tab, setTab] = useState<"write" | "posts">("posts");
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [loadingPosts, setLoadingPosts] = useState(true);

  // Generator form
  const [topic, setTopic] = useState("");
  const [keywords, setKeywords] = useState("");
  const [tone, setTone] = useState("professional");
  const [length, setLength] = useState("medium");
  const [businessName, setBusinessName] = useState("");
  const [blogLanguage, setBlogLanguage] = useState("English");
  const [includeFaq, setIncludeFaq] = useState(true);
  const [imageUrl, setImageUrl] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<BlogGenerateResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState<BlogTemplateId | null>(null);

  // One-click publish-to-site state
  const [publishingSiteId, setPublishingSiteId] = useState<string | null>(null);
  const [publishedUrls, setPublishedUrls] = useState<Record<string, string>>({});

  // Read modal
  const [readPost, setReadPost] = useState<BlogPost | null>(null);

  // Publish modal
  const [publishPost, setPublishPost] = useState<BlogPost | null>(null);
  const [publishPlatform, setPublishPlatform] = useState("wordpress");
  const [wpUrl, setWpUrl] = useState("");
  const [wpUser, setWpUser] = useState("");
  const [wpPass, setWpPass] = useState("");
  const [shopifyDomain, setShopifyDomain] = useState("");
  const [shopifyToken, setShopifyToken] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<string>("");

  const [editingPost, setEditingPost] = useState<BlogPost | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editMetaTitle, setEditMetaTitle] = useState("");
  const [editMetaDescription, setEditMetaDescription] = useState("");
  const [editImageUrl, setEditImageUrl] = useState("");
  const [editKeywords, setEditKeywords] = useState("");
  const [editTags, setEditTags] = useState("");
  const [editing, setEditing] = useState(false);
  const [editingError, setEditingError] = useState("");
  const [credsSaved, setCredsSaved] = useState(false);

  const loadPosts = useCallback(async () => {
    setLoadingPosts(true);
    try { setPosts(await seoApi.listPosts()); } catch { /* ignore */ }
    finally { setLoadingPosts(false); }
  }, []);

  useEffect(() => { loadPosts(); }, [loadPosts]);

  useEffect(() => {
    if (!profile) return;
    setBusinessName((n) => (n.trim() ? n : profile.business_name));
    if (profile.language?.trim()) setBlogLanguage(profile.language.trim());
  }, [profile]);

  // Pre-fill from calendar "Write post" click
  useEffect(() => {
    if (!prefillTopic) return;
    setTopic(prefillTopic.title);
    setKeywords(prefillTopic.keywords.join(", "));
    setTab("write");
  }, [prefillTopic]);

  // Load saved publish credentials when platform changes
  useEffect(() => {
    setCredsSaved(false);
    seoApi.getPublishCredentials(publishPlatform).then(creds => {
      if (!creds?.platform) return;
      if (publishPlatform === "wordpress") {
        if (creds.wp_url) setWpUrl(creds.wp_url);
        if (creds.wp_username) setWpUser(creds.wp_username);
        if (creds.wp_password) setWpPass(creds.wp_password);
      } else if (publishPlatform === "shopify") {
        if (creds.shopify_domain) setShopifyDomain(creds.shopify_domain);
        if (creds.shopify_token) setShopifyToken(creds.shopify_token);
      }
      setCredsSaved(true);
    }).catch(() => {});
  }, [publishPlatform]);

  async function publishToSite(post: BlogPost) {
    setPublishingSiteId(post.id);
    try {
      const result = await blogApi.publishFromSeo({
        title: post.title,
        content: post.content,
        keywords: post.keywords ?? [],
        excerpt: post.meta_description,
      });
      setPublishedUrls(prev => ({ ...prev, [post.id]: result.post_url }));
      toast.success("Published to your website!");
      await loadPosts();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Publish failed — is Autoblog activated?");
    } finally {
      setPublishingSiteId(null);
    }
  }

  async function generate() {
    if (!topic.trim()) return;
    setGenerating(true); setErr(""); setGenerated(null);
    const tpl = BLOG_TEMPLATES.find(t => t.id === selectedTemplate);
    const enrichedTopic = tpl ? `${topic.trim()} [${tpl.hint}]` : topic.trim();
    try {
      const res = await seoApi.generateBlog({
        topic: enrichedTopic,
        keywords: keywords.split(",").map(k => k.trim()).filter(Boolean),
        tone,
        length,
        business_name: businessName,
        language: blogLanguage,
        include_faq: includeFaq,
      });
      setGenerated(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function saveAsDraft() {
    if (!generated) return;
    setSaving(true);
    try {
      await seoApi.createPost({
        title: generated.title,
        content: generated.content,
        meta_title: generated.meta_title,
        meta_description: generated.meta_description,
        image_url: imageUrl || undefined,
        keywords: generated.keywords || [],
        tags: generated.tags,
        status: "draft",
        platform: "internal",
      });
      await loadPosts();
      setTab("posts");
      setGenerated(null);
      setImageUrl("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function deletePost(id: string) {
    if (!confirm("Delete this post?")) return;
    try {
      await seoApi.deletePost(id);
      setPosts(p => p.filter(x => x.id !== id));
    } catch { /* ignore */ }
  }

  function openEditModal(post: BlogPost) {
    setEditingPost(post);
    setEditTitle(post.title);
    setEditContent(post.content);
    setEditMetaTitle(post.meta_title);
    setEditMetaDescription(post.meta_description);
    setEditImageUrl(post.image_url || "");
    setEditKeywords((post.keywords ?? []).join(", "));
    setEditTags((post.tags ?? []).join(", "));
    setEditingError("");
  }

  function closeEditModal() {
    setEditingPost(null);
    setEditImageUrl("");
    setEditingError("");
  }

  async function savePostEdits() {
    if (!editingPost) return;
    setEditing(true);
    setEditingError("");
    try {
      const updated = await seoApi.updatePost(editingPost.id, {
        title: editTitle,
        content: editContent,
        meta_title: editMetaTitle,
        meta_description: editMetaDescription,
        image_url: editImageUrl || undefined,
        keywords: editKeywords.split(",").map(k => k.trim()).filter(Boolean),
        tags: editTags.split(",").map(t => t.trim()).filter(Boolean),
      });
      setPosts(current => current.map(p => p.id === updated.id ? updated : p));
      if (readPost?.id === updated.id) setReadPost(updated);
      if (publishPost?.id === updated.id) setPublishPost(updated);
      setEditingPost(updated);
      closeEditModal();
    } catch (e) {
      setEditingError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setEditing(false);
    }
  }

  async function doPublish() {
    if (!publishPost) return;
    setPublishing(true); setPublishResult("");
    try {
      // Persist credentials so user doesn't re-enter next time
      seoApi.savePublishCredentials({
        platform: publishPlatform,
        wp_url: wpUrl || undefined,
        wp_username: wpUser || undefined,
        wp_password: wpPass || undefined,
        shopify_domain: shopifyDomain || undefined,
        shopify_token: shopifyToken || undefined,
      }).catch(() => {});

      const res = await seoApi.publishPost({
        post_id: publishPost.id,
        platform: publishPlatform,
        wp_url: wpUrl || undefined,
        wp_username: wpUser || undefined,
        wp_password: wpPass || undefined,
        shopify_domain: shopifyDomain || undefined,
        shopify_token: shopifyToken || undefined,
      });
      if (res.ok) {
        setPublishResult(`Published! ${res.post_url || ""}`);
        await loadPosts();
      } else {
        setPublishResult(`Error: ${res.error || "Unknown error"}`);
      }
    } catch (e) {
      setPublishResult(e instanceof Error ? e.message : "Failed");
    } finally {
      setPublishing(false);
    }
  }

  const statusColor = (s: string) =>
    s === "published" ? "bg-green-100 text-green-700"
    : s === "scheduled" ? "bg-blue-100 text-blue-700"
    : "bg-slate-100 text-slate-600";

  const topicStarters = useMemo(() => {
    if (!profile) return [];
    const bn = profile.business_name?.trim();
    const bt = profile.business_type?.trim()?.replace(/-/g, " ") || "your services";
    const loc = profile.location?.trim();
    const city = loc ? loc.split(",")[0]?.trim() : "";
    const geo = city ? ` in ${city}` : "";
    const ideas: string[] = [];
    if (bn) ideas.push(`Why customers choose ${bn} for ${bt}${geo}`);
    ideas.push(`5 practical ${bt} tips every customer should know${geo}`);
    ideas.push(city ? `${bt} in ${city}: what to look for` : `${bt}: a simple guide for first-time buyers`);
    return ideas.slice(0, 4);
  }, [profile]);

  return (
    <div className="space-y-5">
      <div className="flex gap-2">
        {(["posts", "write"] as const).map(t => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${tab === t ? "bg-emerald-600 text-white shadow-sm" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"}`}
          >
            {t === "posts" ? "My posts" : "Write post"}
          </button>
        ))}
      </div>

      {tab === "write" && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
          <div>
            <p className="text-sm font-semibold text-slate-800">Draft a blog post</p>
            <p className="text-xs text-slate-500 mt-1">
              Your business name and story come from Settings automatically — just pick a topic.
            </p>
          </div>

          {/* Template picker */}
          <div>
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-2">Article style</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {BLOG_TEMPLATES.map(t => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSelectedTemplate(selectedTemplate === t.id ? null : t.id)}
                  className={cn(
                    "rounded-xl border p-3 text-left transition-all",
                    selectedTemplate === t.id
                      ? "border-emerald-500 bg-emerald-50 shadow-sm"
                      : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                  )}
                >
                  <span className="text-lg leading-none">{t.icon}</span>
                  <p className="text-xs font-semibold text-slate-800 mt-1.5">{t.name}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">{t.desc}</p>
                </button>
              ))}
            </div>
            {selectedTemplate && (() => {
              const tpl = BLOG_TEMPLATES.find(t => t.id === selectedTemplate);
              return tpl ? (
                <p className="mt-2 rounded-lg border border-emerald-100 bg-emerald-50/60 px-3 py-2 text-[11px] text-emerald-800">
                  <span className="font-semibold">Structure:</span> {tpl.structure}
                </p>
              ) : null;
            })()}
          </div>

          {topicStarters.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-2">Ideas for you</p>
              <div className="flex flex-wrap gap-2">
                {topicStarters.map((s, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setTopic(s)}
                    className="text-left text-xs px-3 py-2.5 rounded-xl border border-emerald-100 bg-emerald-50/40 text-slate-700 hover:bg-emerald-50 transition-colors max-w-full sm:max-w-[340px] leading-snug"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="text-xs text-slate-500 font-medium block mb-1">What should this article cover?</label>
            <input
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              placeholder="Or type any topic you want…"
              value={topic}
              onChange={e => setTopic(e.target.value)}
            />
          </div>

          <details className="group rounded-xl border border-slate-100 bg-slate-50/50">
            <summary className="cursor-pointer text-xs font-semibold text-slate-600 px-3 py-2.5 list-none flex items-center justify-between [&::-webkit-details-marker]:hidden">
              Keywords, tone, length & language
              <span className="text-slate-400 group-open:rotate-180 transition-transform">▼</span>
            </summary>
            <div className="px-3 pb-3 pt-1 space-y-3 border-t border-slate-100 bg-white rounded-b-xl">
              <div className="pt-2">
                <label className="text-xs text-slate-500 font-medium block mb-1">Target keywords (optional)</label>
                <input
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="Comma-separated"
                  value={keywords}
                  onChange={e => setKeywords(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-500 font-medium block mb-1">Tone</label>
                  <select
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    value={tone}
                    onChange={e => setTone(e.target.value)}
                  >
                    <option value="professional">Professional</option>
                    <option value="friendly">Friendly</option>
                    <option value="casual">Casual</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-500 font-medium block mb-1">Length</label>
                  <select
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    value={length}
                    onChange={e => setLength(e.target.value)}
                  >
                    <option value="short">Short (~400 words)</option>
                    <option value="medium">Medium (~800 words)</option>
                    <option value="long">Long (~1500 words)</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-500 font-medium block mb-1">Business name</label>
                  <input
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    placeholder="From Settings by default"
                    value={businessName}
                    onChange={e => setBusinessName(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-500 font-medium block mb-1">Language</label>
                  <select
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    value={blogLanguage}
                    onChange={e => setBlogLanguage(e.target.value)}
                  >
                    <option value="English">English</option>
                    <option value="Swahili">Swahili</option>
                    <option value="French">French</option>
                    <option value="Spanish">Spanish</option>
                    <option value="Arabic">Arabic</option>
                  </select>
                </div>
              </div>
              <div className="space-y-3">
                <label className="block text-xs text-slate-500 font-medium">Optional featured image URL</label>
                <input
                  type="url"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="https://..."
                  value={imageUrl}
                  onChange={e => setImageUrl(e.target.value)}
                />
                <p className="text-xs text-slate-400">Paste a hero image URL for a premium blog preview.</p>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeFaq}
                  onChange={e => setIncludeFaq(e.target.checked)}
                  className="rounded border-slate-300"
                />
                <span className="text-sm text-slate-600">Include FAQ section (great for Google)</span>
              </label>
            </div>
          </details>

          <button
            type="button"
            onClick={generate}
            disabled={generating || !topic.trim()}
            className="w-full sm:w-auto min-h-[44px] px-6 py-3 bg-emerald-600 text-white text-sm font-semibold rounded-xl hover:bg-emerald-700 disabled:opacity-50 shadow-sm"
          >
            {generating ? "Writing…" : "Generate draft"}
          </button>
          {err && <p className="text-red-500 text-xs">{err}</p>}

          {generated && (
            <div className="space-y-3 pt-2 border-t border-slate-100">
              {/* Action bar */}
              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={async () => {
                    setSaving(true);
                    try {
                      const saved = await seoApi.createPost({
                        title: generated.title, content: generated.content,
                        meta_title: generated.meta_title, meta_description: generated.meta_description,
                        image_url: imageUrl || undefined,
                        keywords: generated.keywords || [], tags: generated.tags,
                        status: "draft", platform: "internal",
                      });
                      const result = await blogApi.publishFromSeo({
                        title: saved.title, content: saved.content,
                        keywords: saved.keywords ?? [], excerpt: saved.meta_description,
                      });
                      toast.success("Published to your website!");
                      setPublishedUrls(prev => ({ ...prev, [saved.id]: result.post_url }));
                      await loadPosts(); setTab("posts"); setGenerated(null); setImageUrl("");
                    } catch (e) { toast.error(e instanceof Error ? e.message : "Publish failed"); }
                    finally { setSaving(false); }
                  }}
                  disabled={saving}
                  className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50"
                >
                  {saving ? "Publishing…" : "🚀 Publish to My Site"}
                </button>
                <button
                  onClick={saveAsDraft}
                  disabled={saving}
                  className="px-4 py-2 bg-slate-100 text-slate-700 text-sm rounded-xl font-medium hover:bg-slate-200 disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save as Draft"}
                </button>
              </div>

              {/* Beautiful rendered article */}
              <div className="max-h-[600px] overflow-y-auto rounded-xl">
                <BlogRenderer
                  title={generated.title}
                  content={generated.content}
                  templateId={selectedTemplate ?? undefined}
                  wordCount={generated.word_count}
                  tags={generated.tags}
                  keywords={generated.keywords}
                  metaTitle={generated.meta_title}
                  metaDescription={generated.meta_description}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "posts" && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          {loadingPosts ? (
            <p className="p-5 text-sm text-slate-400">Loading posts…</p>
          ) : posts.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-slate-400 text-sm">No blog posts yet.</p>
              <button onClick={() => setTab("write")} className="mt-3 px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg font-medium">
                Write Your First Post
              </button>
            </div>
          ) : (
            <div className="divide-y divide-slate-50">
              {posts.map(post => (
                <div key={post.id} className="px-5 py-4 flex items-start justify-between gap-3 hover:bg-slate-50/50 transition-colors">
                  <div className="min-w-0 flex-1 cursor-pointer" onClick={() => setReadPost(post)}>
                    <p className="text-sm font-semibold text-slate-800 hover:text-emerald-700 transition-colors">{post.title}</p>
                    {post.image_url && (
                      <img src={post.image_url} alt={post.title} className="w-full h-20 object-cover rounded-xl mt-3 border border-slate-200" />
                    )}
                    {(post.keywords ?? []).length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1">
                        {(post.keywords ?? []).slice(0, 4).map((kw, index) => (
                          <span key={`${post.id}-kw-${index}`} className="text-[10px] px-2 py-1 bg-slate-100 text-slate-600 rounded-full">{kw}</span>
                        ))}
                      </div>
                    )}
                    <p className="text-xs text-slate-400 mt-2">
                      {post.created_at ? new Date(post.created_at).toLocaleDateString() : ""}
                      {(post as BlogPost & { word_count?: number }).word_count ? ` · ${(post as BlogPost & { word_count?: number }).word_count} words` : ""}
                    </p>
                    {(post.tags ?? []).length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {(post.tags ?? []).slice(0, 3).map(t => (
                          <span key={t} className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">{t}</span>
                        ))}
                      </div>
                    )}
                    <p className="text-[10px] text-slate-300 mt-1">Click to read →</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${statusColor(post.status ?? "")}`}>{post.status}</span>
                    <button
                      onClick={() => openEditModal(post)}
                      className="text-xs px-2 py-1 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200"
                    >
                      Edit
                    </button>
                    {post.status !== "published" && (
                      publishedUrls[post.id] ? (
                        <a
                          href={publishedUrls[post.id]}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs px-2 py-1 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium whitespace-nowrap"
                        >
                          ✓ View live →
                        </a>
                      ) : (
                        <button
                          onClick={() => publishToSite(post)}
                          disabled={publishingSiteId === post.id}
                          className="text-xs px-2 py-1 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-60 font-medium whitespace-nowrap"
                        >
                          {publishingSiteId === post.id ? "Publishing…" : "🚀 Publish"}
                        </button>
                      )
                    )}
                    <button
                      onClick={() => deletePost(post.id)}
                      className="text-xs px-2 py-1 bg-red-50 text-red-500 rounded-lg hover:bg-red-100"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Read / Preview Modal */}
      {readPost && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-start justify-end p-0 sm:p-4">
          <div className="bg-white w-full sm:w-[680px] h-full sm:h-[calc(100vh-2rem)] sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden">
            {/* Header */}
            <div className="px-5 py-4 border-b border-slate-100 flex items-start justify-between gap-3 shrink-0">
              <div className="min-w-0">
                <p className="text-base font-bold text-slate-800 leading-snug">{readPost.title}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {readPost.created_at ? new Date(readPost.created_at).toLocaleDateString() : ""}
                  {(readPost as BlogPost & { word_count?: number }).word_count
                    ? ` · ${(readPost as BlogPost & { word_count?: number }).word_count} words`
                    : ""}
                  {" · "}
                  <span className={`font-medium ${readPost.status === "published" ? "text-green-600" : "text-slate-500"}`}>{readPost.status}</span>
                </p>
              </div>
              <button
                onClick={() => setReadPost(null)}
                className="text-slate-400 hover:text-slate-700 text-2xl leading-none shrink-0 mt-0.5"
              >×</button>
            </div>

            {readPost.calendar_week != null && (
              <div className="px-5 py-2 bg-slate-50 border-b border-slate-100 shrink-0">
                <p className="text-[10px] text-slate-500 uppercase tracking-wide">Calendar post · Week {readPost.calendar_week}{readPost.calendar_day ? ` · ${readPost.calendar_day}` : ""}</p>
              </div>
            )}
            <div className="flex-1 overflow-y-auto p-4">
              <BlogRenderer
                title={readPost.title}
                content={readPost.content}
                templateId={(readPost as BlogPost & { template_id?: string }).template_id}
                tags={readPost.tags}
                keywords={readPost.keywords}
                metaTitle={readPost.meta_title}
                metaDescription={readPost.meta_description}
                publishedUrl={publishedUrls[readPost.id]}
              />
            </div>

            {/* Footer actions */}
            <div className="px-5 py-3 border-t border-slate-100 flex items-center gap-2 shrink-0 bg-white flex-wrap">
              {readPost.status !== "published" && (
                publishedUrls[readPost.id] ? (
                  <a href={publishedUrls[readPost.id]} target="_blank" rel="noopener noreferrer"
                    className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg font-medium hover:bg-green-700">
                    ✓ View live →
                  </a>
                ) : (
                  <button
                    onClick={async () => { await publishToSite(readPost); setReadPost(null); }}
                    disabled={publishingSiteId === readPost.id}
                    className="px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-60"
                  >
                    {publishingSiteId === readPost.id ? "Publishing…" : "🚀 Publish to My Site"}
                  </button>
                )
              )}
              <button
                onClick={() => {
                  setTopic(readPost.title);
                  setKeywords((readPost.tags ?? []).join(", "));
                  setTab("write");
                  setReadPost(null);
                }}
                className="px-4 py-2 bg-slate-100 text-slate-700 text-sm rounded-lg font-medium hover:bg-slate-200"
              >
                Rewrite
              </button>
              <button
                onClick={() => { openEditModal(readPost); setReadPost(null); }}
                className="px-3 py-2 bg-slate-100 text-slate-700 text-sm rounded-lg font-medium hover:bg-slate-200"
              >
                Edit Post
              </button>
              <button
                onClick={async () => { await deletePost(readPost.id); setReadPost(null); }}
                className="px-3 py-2 bg-red-50 text-red-500 text-sm rounded-lg font-medium hover:bg-red-100 ml-auto"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Post Modal */}
      {editingPost && (
        <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-lg font-bold text-slate-800">Edit Blog Post</p>
                <p className="text-sm text-slate-500">Save changes to the generated blog post content and SEO metadata.</p>
              </div>
              <button onClick={closeEditModal} className="text-slate-400 hover:text-slate-700 text-xl">×</button>
            </div>

            <div className="grid grid-cols-1 gap-4">
              <div>
                <label className="text-xs font-semibold text-slate-500 mb-1 block">Title</label>
                <input
                  value={editTitle}
                  onChange={e => setEditTitle(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 mb-1 block">SEO meta title</label>
                <input
                  value={editMetaTitle}
                  onChange={e => setEditMetaTitle(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 mb-1 block">Meta description</label>
                <textarea
                  value={editMetaDescription}
                  onChange={e => setEditMetaDescription(e.target.value)}
                  rows={3}
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 mb-1 block">Featured image URL</label>
                <input
                  type="url"
                  value={editImageUrl}
                  onChange={e => setEditImageUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <p className="text-xs text-slate-400 mt-1">Optional hero image shown in the premium blog preview.</p>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 mb-1 block">Keywords (comma-separated)</label>
                <input
                  value={editKeywords}
                  onChange={e => setEditKeywords(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <p className="text-xs text-slate-400 mt-1">Add the target keywords that this post should rank for.</p>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 mb-1 block">Tags (comma-separated)</label>
                <input
                  value={editTags}
                  onChange={e => setEditTags(e.target.value)}
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 mb-1 block">Content</label>
                <textarea
                  value={editContent}
                  onChange={e => setEditContent(e.target.value)}
                  rows={12}
                  className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
                />
              </div>
            </div>

            {editingError && <p className="text-sm text-red-600">{editingError}</p>}

            <div className="flex items-center gap-3">
              <button
                onClick={savePostEdits}
                disabled={editing}
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
              >
                {editing ? "Saving…" : "Save changes"}
              </button>
              <button
                onClick={closeEditModal}
                className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-200"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Publish Modal — simplified: Zilo site is primary, custom WP is advanced */}
      {publishPost && (
        <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-base font-bold text-slate-800">Publish Post</p>
              <button onClick={() => setPublishPost(null)} className="text-slate-400 hover:text-slate-600 text-xl">×</button>
            </div>
            <p className="text-sm text-slate-600 font-medium truncate">{publishPost.title}</p>

            {/* Primary: publish to provisioned Zilo site */}
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 space-y-3">
              <p className="text-xs font-semibold text-emerald-900">Publish to My Website</p>
              <p className="text-xs text-emerald-800">One click — posts directly to your Zilo website. No credentials needed.</p>
              {publishResult && !publishResult.startsWith("Error") && (
                <a href={publishResult.replace("Published! ", "")} target="_blank" rel="noopener noreferrer"
                  className="text-xs text-green-700 underline font-medium block">
                  ✓ View live post →
                </a>
              )}
              {publishResult?.startsWith("Error") && (
                <p className="text-xs text-red-600">{publishResult}</p>
              )}
              <button
                onClick={async () => {
                  setPublishing(true); setPublishResult("");
                  try {
                    const result = await blogApi.publishFromSeo({
                      title: publishPost.title, content: publishPost.content,
                      keywords: publishPost.keywords ?? [], excerpt: publishPost.meta_description,
                    });
                    setPublishResult(`Published! ${result.post_url}`);
                    setPublishedUrls(prev => ({ ...prev, [publishPost.id]: result.post_url }));
                    toast.success("Published to your website!");
                    await loadPosts();
                  } catch (e) { setPublishResult(`Error: ${e instanceof Error ? e.message : "Failed"}`); }
                  finally { setPublishing(false); }
                }}
                disabled={publishing}
                className="w-full py-2.5 bg-emerald-600 text-white text-sm rounded-xl font-semibold hover:bg-emerald-700 disabled:opacity-50"
              >
                {publishing ? "Publishing…" : "🚀 Publish to My Site"}
              </button>
            </div>

            {/* Advanced: manual credentials */}
            <details className="group rounded-xl border border-slate-200">
              <summary className="cursor-pointer px-4 py-3 text-xs font-semibold text-slate-500 list-none flex items-center justify-between [&::-webkit-details-marker]:hidden">
                Advanced — publish to another WordPress / Shopify
                <span className="text-slate-400 group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <div className="px-4 pb-4 pt-1 space-y-3 border-t border-slate-100">
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  value={publishPlatform} onChange={e => setPublishPlatform(e.target.value)}>
                  <option value="wordpress">WordPress</option>
                  <option value="shopify">Shopify</option>
                </select>
                {publishPlatform === "wordpress" && (
                  <>
                    {credsSaved && <p className="text-[10px] text-emerald-600 font-medium">✓ Credentials loaded from last time</p>}
                    <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="WordPress URL" value={wpUrl} onChange={e => setWpUrl(e.target.value)} />
                    <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Username" value={wpUser} onChange={e => setWpUser(e.target.value)} />
                    <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Application Password" type="password" value={wpPass} onChange={e => setWpPass(e.target.value)} />
                  </>
                )}
                {publishPlatform === "shopify" && (
                  <>
                    {credsSaved && <p className="text-[10px] text-emerald-600 font-medium">✓ Credentials loaded from last time</p>}
                    <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="mystore.myshopify.com" value={shopifyDomain} onChange={e => setShopifyDomain(e.target.value)} />
                    <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Access Token" type="password" value={shopifyToken} onChange={e => setShopifyToken(e.target.value)} />
                  </>
                )}
                <button onClick={doPublish} disabled={publishing}
                  className="w-full py-2 bg-slate-800 text-white text-sm rounded-lg font-medium hover:bg-slate-900 disabled:opacity-50">
                  {publishing ? "Publishing…" : `Publish to ${publishPlatform === "wordpress" ? "WordPress" : "Shopify"}`}
                </button>
              </div>
            </details>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Content Calendar Tab ──────────────────────────────────────────────────────

type DraftStatus = { [title: string]: "generating" | "done" | "error" };

function CalendarTab({ profile, onJump, prefillKeywords, onWritePost }: {
  profile: SeoBusinessContext | null;
  onJump: (t: Tab) => void;
  prefillKeywords?: SeoKeyword[];
  onWritePost?: (p: CalendarWritePayload) => void;
}) {
  const [businessType, setBusinessType] = useState("");
  const [location, setLocation] = useState("");
  const [postsPerWeek, setPostsPerWeek] = useState(2);
  const [weeks, setWeeks] = useState(4);
  const [loading, setLoading] = useState(false);
  const [calendar, setCalendar] = useState<ContentCalendarItem[]>([]);
  const [err, setErr] = useState("");

  // Bulk draft generation state
  const [draftStatus, setDraftStatus] = useState<DraftStatus>({});
  const [generatingDrafts, setGeneratingDrafts] = useState(false);
  const [draftsDone, setDraftsDone] = useState(0);
  const [draftsTotal, setDraftsTotal] = useState(0);
  const [generationMode, setGenerationMode] = useState<"all" | "one-by-one">("all");

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = window.localStorage.getItem("seo-calendar-v1");
      if (saved) setCalendar(JSON.parse(saved));
    } catch {
      // ignore invalid local data
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem("seo-calendar-v1", JSON.stringify(calendar));
    } catch {
      // ignore storage write failures
    }
  }, [calendar]);

  useEffect(() => {
    if (!profile) return;
    setBusinessType((t) => (t.trim() ? t : profile.business_type));
    setLocation((t) => (t.trim() ? t : profile.location));
  }, [profile]);

  // Auto-generate calendar when keywords are pushed from Keywords tab
  const prefillRef = useRef<SeoKeyword[] | undefined>(undefined);
  useEffect(() => {
    if (prefillKeywords && prefillKeywords !== prefillRef.current && calendar.length === 0) {
      prefillRef.current = prefillKeywords;
      void generate();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillKeywords]);

  async function generate() {
    setLoading(true); setErr(""); setDraftStatus({});
    try {
      const res = await seoApi.contentCalendar(businessType.trim(), postsPerWeek, weeks, location.trim());
      setCalendar(res.calendar);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  // Generate all drafts for a subset (week) or all items at once
  function getPendingItems(items: ContentCalendarItem[]) {
    return items.filter(it => draftStatus[it.title] !== "done" && draftStatus[it.title] !== "generating");
  }

  async function generateDrafts(items: ContentCalendarItem[], mode: "all" | "one-by-one" = generationMode) {
    if (!items.length || generatingDrafts) return;
    const targets = mode === "one-by-one" ? getPendingItems(items).slice(0, 1) : items;
    if (!targets.length) return;

    setGeneratingDrafts(true);
    setDraftsTotal(targets.length);
    setDraftsDone(0);

    // Mark all selected targets as generating
    const init: DraftStatus = {};
    targets.forEach(it => { init[it.title] = "generating"; });
    setDraftStatus(prev => ({ ...prev, ...init }));

    if (mode === "one-by-one") {
      const item = targets[0];
      try {
        const res = await seoApi.generateCalendarDrafts({
          items: [{
            title: item.title,
            keywords: item.keywords ?? [],
            topic: String(item.topic ?? ""),
            week: item.week,
            day: String(item.day ?? ""),
          }],
          tone: "professional",
          length: "medium",
        });
        const status = res.drafts?.[0]?.status === "error" ? "error" : "done";
        setDraftStatus(prev => ({ ...prev, [item.title]: status }));
      } catch {
        setDraftStatus(prev => ({ ...prev, [item.title]: "error" }));
      } finally {
        setDraftsDone(1);
      }
    } else {
      // Send in batches of 5 to avoid timeout
      const BATCH = 5;
      for (let i = 0; i < targets.length; i += BATCH) {
        const batch = targets.slice(i, i + BATCH);
        try {
          const res = await seoApi.generateCalendarDrafts({
            items: batch.map(it => ({
              title: it.title,
              keywords: it.keywords ?? [],
              topic: String(it.topic ?? ""),
              week: it.week,
              day: String(it.day ?? ""),
            })),
            tone: "professional",
            length: "medium",
          });
          const updates: DraftStatus = {};
          res.drafts.forEach(d => {
            updates[d.title] = d.status === "error" ? "error" : "done";
          });
          setDraftStatus(prev => ({ ...prev, ...updates }));
          setDraftsDone(prev => prev + batch.length);
        } catch {
          const updates: DraftStatus = {};
          batch.forEach(it => { updates[it.title] = "error"; });
          setDraftStatus(prev => ({ ...prev, ...updates }));
          setDraftsDone(prev => prev + batch.length);
        }
      }
    }

    setGeneratingDrafts(false);
  }

  const trafficColor = (t: string) =>
    t === "high" ? "text-green-600" : t === "medium" ? "text-yellow-600" : "text-slate-400";

  const weeks_grouped = Array.from(new Set(calendar.map(c => c.week))).sort();

  const usingProfile =
    Boolean(profile?.business_name?.trim()) ||
    Boolean(profile?.business_type?.trim()) ||
    Boolean(profile?.location?.trim());

  const allDone = calendar.length > 0 &&
    calendar.every(it => draftStatus[it.title] === "done");

  const anyGenerating = Object.values(draftStatus).some(s => s === "generating");

  return (
    <div className="space-y-5">
      {/* Control card */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">Your content calendar</p>
          <p className="text-xs text-slate-500 mt-1">
            Step 1 — generate the plan. Step 2 — write all posts in one click. The AI already knows what to write.
          </p>
          {usingProfile && (
            <p className="text-xs text-slate-600 mt-2 rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
              <span className="font-medium text-slate-700">Using:</span>{" "}
              {[profile?.business_name?.trim(), profile?.business_type?.replace(/-/g, " "), profile?.location?.trim()]
                .filter(Boolean)
                .join(" · ") || "Saved profile"}
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <button
            type="button"
            onClick={generate}
            disabled={loading || generatingDrafts}
            className="min-h-[44px] px-6 py-3 bg-emerald-600 text-white text-sm font-semibold rounded-xl hover:bg-emerald-700 disabled:opacity-50 shadow-sm"
          >
            {loading ? "Building calendar…" : calendar.length > 0 ? "Regenerate calendar" : "Generate my calendar"}
          </button>

          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span>Generation mode:</span>
            <button
              type="button"
              onClick={() => setGenerationMode("all")}
              className={`px-3 py-2 rounded-xl border ${generationMode === "all" ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-200"}`}
            >
              All at once
            </button>
            <button
              type="button"
              onClick={() => setGenerationMode("one-by-one")}
              className={`px-3 py-2 rounded-xl border ${generationMode === "one-by-one" ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-200"}`}
            >
              One by one
            </button>
          </div>

          {calendar.length > 0 && !allDone && (
            <button
              type="button"
              onClick={() => generateDrafts(calendar, generationMode)}
              disabled={generatingDrafts}
              className="min-h-[44px] px-6 py-3 bg-slate-800 text-white text-sm font-semibold rounded-xl hover:bg-slate-900 disabled:opacity-50 shadow-sm flex items-center gap-2"
            >
              {generatingDrafts ? (
                <>
                  <span className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  Writing {draftsDone}/{draftsTotal} posts…
                </>
              ) : generationMode === "one-by-one" ? "✨ Write one by one" : "✨ Write all posts"}
            </button>
          )}

          {allDone && (
            <button
              onClick={() => onJump("blog")}
              className="min-h-[44px] px-6 py-3 bg-green-600 text-white text-sm font-semibold rounded-xl hover:bg-green-700 shadow-sm"
            >
              📖 Review & publish drafts →
            </button>
          )}
        </div>

        {generatingDrafts && (
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs text-slate-500">
              <span>Generating blog posts…</span>
              <span>{draftsDone}/{draftsTotal}</span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-2">
              <div
                className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${draftsTotal > 0 ? (draftsDone / draftsTotal) * 100 : 0}%` }}
              />
            </div>
          </div>
        )}

        <details className="group rounded-xl border border-slate-100 bg-slate-50/50">
          <summary className="cursor-pointer text-xs font-semibold text-slate-600 px-3 py-2.5 list-none flex items-center justify-between [&::-webkit-details-marker]:hidden">
            Schedule & fine-tune
            <span className="text-slate-400 group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div className="px-3 pb-3 pt-0 grid grid-cols-1 sm:grid-cols-2 gap-3 border-t border-slate-100 bg-white rounded-b-xl">
            <div className="pt-3">
              <label className="text-xs text-slate-500 font-medium block mb-1">Industry</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                placeholder="Optional override"
                value={businessType}
                onChange={e => setBusinessType(e.target.value)}
              />
            </div>
            <div className="pt-3">
              <label className="text-xs text-slate-500 font-medium block mb-1">Location</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                placeholder="Optional"
                value={location}
                onChange={e => setLocation(e.target.value)}
              />
            </div>
            <div className="pt-1">
              <label className="text-xs text-slate-500 font-medium block mb-1">Posts per week</label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                value={postsPerWeek}
                onChange={e => setPostsPerWeek(Number(e.target.value))}
              >
                {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div className="pt-1">
              <label className="text-xs text-slate-500 font-medium block mb-1">Weeks</label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                value={weeks}
                onChange={e => setWeeks(Number(e.target.value))}
              >
                {[2, 4, 6, 8, 12].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
        </details>

        <p className="text-[11px] text-slate-400">Leave fields blank to use your saved Settings profile.</p>
        {err && <p className="text-red-500 text-xs">{err}</p>}
      </div>

      {/* Calendar weeks */}
      {calendar.length > 0 && (
        <div className="space-y-4">
          {weeks_grouped.map(week => {
            const weekItems = calendar.filter(c => c.week === week);
            const weekDone = weekItems.every(it => draftStatus[it.title] === "done");
            const weekGenerating = weekItems.some(it => draftStatus[it.title] === "generating");

            return (
              <div key={week} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                {/* Week header */}
                <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-slate-700">Week {week}</p>
                    {weekDone && <span className="text-[10px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-semibold">All drafted ✓</span>}
                    {weekGenerating && <span className="text-[10px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full font-semibold animate-pulse">Writing…</span>}
                  </div>
                  {!weekDone && !anyGenerating && (
                    <button
                      type="button"
                      onClick={() => generateDrafts(weekItems, generationMode)}
                      className="text-[10px] px-2.5 py-1 bg-slate-800 text-white rounded-lg hover:bg-slate-900 font-semibold whitespace-nowrap"
                    >
                      {generationMode === "one-by-one" ? `Write week ${week} one-by-one` : `Write week ${week}`}
                    </button>
                  )}
                  {weekDone && !weekGenerating && (
                    <button
                      onClick={() => onJump("blog")}
                      className="text-[10px] px-2.5 py-1 bg-green-600 text-white rounded-lg hover:bg-green-700 font-semibold whitespace-nowrap"
                    >
                      Review drafts →
                    </button>
                  )}
                </div>

                {/* Calendar items */}
                <div className="divide-y divide-slate-50">
                  {weekItems.map((item, i) => {
                    const status = draftStatus[item.title];
                    return (
                      <div key={i} className={`px-5 py-3 transition-colors ${status === "done" ? "bg-green-50/40" : status === "error" ? "bg-red-50/30" : ""}`}>
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                              <span className="text-xs text-slate-400 font-medium">{item.day}</span>
                              <span className={`text-xs font-medium capitalize ${trafficColor(String(item.estimated_traffic ?? ""))}`}>
                                {item.estimated_traffic as string} traffic
                              </span>
                              {status === "done" && <span className="text-[10px] text-green-600 font-semibold">✓ Draft ready</span>}
                              {status === "generating" && <span className="text-[10px] text-blue-500 font-semibold animate-pulse">Writing…</span>}
                              {status === "error" && <span className="text-[10px] text-red-500 font-semibold">⚠ Failed</span>}
                            </div>
                            <p className="text-sm font-semibold text-slate-800">{item.title}</p>
                            <p className="text-xs text-slate-400 mt-0.5">{item.topic as string}</p>
                            <div className="flex gap-1 mt-1 flex-wrap">
                              {(item.keywords ?? []).map(kw => (
                                <span key={kw} className="text-[10px] bg-green-50 text-green-700 px-1.5 py-0.5 rounded">{kw}</span>
                              ))}
                            </div>
                          </div>

                          <div className="flex flex-col items-end gap-1.5 shrink-0">
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-50 text-purple-600 font-medium">{item.intent as string}</span>
                            {/* If no draft yet — manual write button */}
                            {!status && onWritePost && (
                              <button
                                type="button"
                                onClick={() => onWritePost({ title: item.title, keywords: item.keywords ?? [] })}
                                className="text-[10px] px-2 py-1 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 font-medium whitespace-nowrap"
                              >
                                Edit & write
                              </button>
                            )}
                            {status === "done" && (
                              <button
                                type="button"
                                onClick={() => onJump("blog")}
                                className="text-[10px] px-2 py-1 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium whitespace-nowrap"
                              >
                                View draft →
                              </button>
                            )}
                            {status === "error" && (
                              <button
                                type="button"
                                onClick={() => generateDrafts([item])}
                                className="text-[10px] px-2 py-1 bg-red-100 text-red-600 rounded-lg hover:bg-red-200 font-medium whitespace-nowrap"
                              >
                                Retry
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

function SeoPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = useMemo(() => normalizeSeoTabParam(searchParams.get("tab")), [searchParams]);
  const [showQuickStart, setShowQuickStart] = useState(true);
  const [summary, setSummary] = useState<SeoSummary | null>(null);
  const [seoProfile, setSeoProfile] = useState<SeoBusinessContext | null>(null);
  // Cross-tab state: keywords pushed to calendar, calendar item to write
  const [pushedKeywords, setPushedKeywords] = useState<SeoKeyword[] | undefined>(undefined);
  const [calendarWritePayload, setCalendarWritePayload] = useState<CalendarWritePayload | undefined>(undefined);

  const changeTab = useCallback(
    (next: Tab) => {
      void Promise.resolve(router.replace(`${pathname}?tab=${next}`, { scroll: false })).catch(() => {});
    },
    [pathname, router]
  );

  useEffect(() => {
    seoApi.businessContext().then(setSeoProfile).catch(() => {});
  }, []);

  useEffect(() => {
    seoApi.summary().then(setSummary).catch(() => {});
  }, [tab]);

  function handlePushToCalendar(kws: SeoKeyword[]) {
    setPushedKeywords(kws);
  }

  function handleWritePost(payload: CalendarWritePayload) {
    setCalendarWritePayload(payload);
    changeTab("blog");
  }

  return (
    <div className="min-h-[calc(100vh-3rem)] bg-[#f4f6f9]">
      <div
        className={cn(
          "mx-auto px-3 pb-10 pt-3 sm:px-5 sm:pb-12 sm:pt-4",
          tab === "hub" ? "max-w-7xl" : "max-w-6xl"
        )}
      >
        {/* Top band — executive header + business (compact) */}
        <section className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
          <div className="border-b border-slate-100 bg-gradient-to-br from-white via-slate-50/50 to-emerald-50/20 px-4 py-4 sm:px-6 sm:py-5">
            <div className="flex flex-col gap-1">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Marketing</p>
              <h1 className="text-lg font-semibold tracking-tight text-slate-900 sm:text-xl">Website &amp; SEO</h1>
              <p className="max-w-2xl text-xs leading-relaxed text-slate-500 sm:text-[13px]">
                Search, content, and publishing in one workspace. Data from Settings is applied automatically.
              </p>
            </div>
            <div className="mt-4">
              <BusinessSnapshotBar profile={seoProfile} />
            </div>
          </div>
        </section>

        {showQuickStart && summary && tab !== "hub" && (summary.total_posts ?? 0) === 0 && (summary.total_audits ?? 0) === 0 && (
          <div className="relative mt-3 rounded-xl border border-slate-200 bg-white px-4 py-3.5 shadow-sm sm:px-5">
            <button
              type="button"
              onClick={() => setShowQuickStart(false)}
              className="absolute right-3 top-3 rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
              aria-label="Dismiss"
            >
              ×
            </button>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Getting started</p>
            <p className="mb-3 text-xs text-slate-600">
              Follow this path once — each step opens the right tab. You can return anytime from the strip below.
            </p>
            <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-2 lg:grid-cols-4 sm:gap-3">
              <div className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
                <span className="font-semibold text-slate-800">1.</span> Confirm business in{" "}
                <Link href="/dashboard/settings" className="font-medium text-emerald-700 underline-offset-2 hover:underline">
                  Settings
                </Link>
                .
              </div>
              <button
                type="button"
                onClick={() => { changeTab("keywords"); setShowQuickStart(false); }}
                className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-left transition-colors hover:border-emerald-200 hover:bg-emerald-50/50"
              >
                <span className="font-semibold text-slate-800">2.</span> Run <span className="font-medium text-emerald-800">Keywords</span> — ideas save for the month.
              </button>
              <button
                type="button"
                onClick={() => { changeTab("calendar"); setShowQuickStart(false); }}
                className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-left transition-colors hover:border-emerald-200 hover:bg-emerald-50/50"
              >
                <span className="font-semibold text-slate-800">3.</span> Open <span className="font-medium text-emerald-800">Calendar</span> to plan posts (tap Continue from Keywords when you have a list).
              </button>
              <button
                type="button"
                onClick={() => { changeTab("blog"); setShowQuickStart(false); }}
                className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-left transition-colors hover:border-emerald-200 hover:bg-emerald-50/50"
              >
                <span className="font-semibold text-slate-800">4.</span> <span className="font-medium text-emerald-800">Write posts</span> or enable Autoblog when you are ready.
              </button>
            </div>
          </div>
        )}

        {/* Bottom pack — sticky tabs + content (single card) */}
        <section className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_4px_24px_rgba(15,23,42,0.06)]">
          <div className="sticky top-0 z-20 border-b border-slate-100 bg-white/90 backdrop-blur-md supports-[backdrop-filter]:bg-white/80">
            <nav
              className="flex gap-0 overflow-x-auto px-1 py-0 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
              aria-label="Website and SEO sections"
            >
              {SEO_TAB_DEFS.map(({ id, label, short, desc, Icon }) => {
                const active = tab === id;
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => changeTab(id)}
                    title={desc}
                    className={cn(
                      "group relative flex min-w-0 flex-shrink-0 items-center gap-2 border-b-2 px-2.5 py-2.5 text-left transition-colors sm:px-3 sm:py-3",
                      active
                        ? "border-emerald-600 text-slate-900"
                        : "border-transparent text-slate-500 hover:border-slate-200 hover:text-slate-800"
                    )}
                  >
                    <Icon
                      className={cn(
                        "h-3.5 w-3.5 flex-shrink-0 sm:h-4 sm:w-4",
                        active ? "text-emerald-700" : "text-slate-400 group-hover:text-slate-600"
                      )}
                      aria-hidden
                    />
                    <span className="flex min-w-0 flex-col gap-0">
                      <span className="text-[11px] font-semibold leading-tight sm:text-xs">
                        <span className="sm:hidden">{short}</span>
                        <span className="hidden sm:inline">{label}</span>
                      </span>
                      <span className="hidden text-[10px] leading-tight text-slate-400 sm:block">{desc}</span>
                    </span>
                  </button>
                );
              })}
            </nav>
          </div>

          <div className="bg-slate-50/40 px-3 py-4 sm:px-5 sm:py-6">
            <div
              key={tab}
              className="motion-safe:animate-[seo-tab-content_0.22s_ease-out] motion-reduce:animate-none"
            >
              {tab === "hub" && <SeoHubWorkspace onOpenTab={changeTab} />}
              {tab === "overview" && <OverviewTab summary={summary} onJump={changeTab} profile={seoProfile} />}
              {tab === "audit" && <AuditTab />}
              {tab === "keywords" && (
                <KeywordsTab profile={seoProfile} onJump={changeTab} onPushToCalendar={handlePushToCalendar} />
              )}
              {tab === "blog" && <BlogTab profile={seoProfile} prefillTopic={calendarWritePayload} />}
              {tab === "calendar" && (
                <CalendarTab
                  profile={seoProfile}
                  onJump={changeTab}
                  prefillKeywords={pushedKeywords}
                  onWritePost={handleWritePost}
                />
              )}
              {tab === "autoblog" && <AutoblogPanel embedded />}
              {tab === "roi" && <ROITracking />}
              {tab === "scheduler" && <AutoScheduler />}
              {tab === "analytics" && <AnalyticsIntegration />}
              {tab === "local" && <LocalSEO />}
              {tab === "social" && <SocialIntegration />}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default function SeoPage() {
  return (
    <Suspense fallback={null}>
      <SeoPageInner />
    </Suspense>
  );
}

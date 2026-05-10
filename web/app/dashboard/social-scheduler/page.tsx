"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  marketingApi,
  socialSchedulerApi,
  type ScheduledPost,
  type ScheduledPostAsset,
  type SocialAnalytics,
} from "@/lib/api";
import { MarketingApiBanner } from "@/components/marketing/MarketingApiBanner";
import { BulkScheduleSection } from "@/components/marketing/BulkScheduleSection";
import { type SocialChannel, fileToPreviewDataUrl } from "@/lib/marketing-stubs";
import {
  POST_KIND_LABELS,
  PLACEMENT_PRESETS,
  presetById,
  type PostKind,
  type PostPlacementId,
} from "@/lib/social-post-presets";
import { formatDateTime } from "@/lib/utils";
import {
  AlertCircle,
  BarChart2,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Clock,
  Copy,
  Eye,
  FileText,
  Image as ImageIcon,
  Loader2,
  MessageCircle,
  MousePointer,
  Pencil,
  Plus,
  RefreshCw,
  Share2,
  Sparkles,
  ThumbsUp,
  Trash2,
  TrendingUp,
  Upload,
  X,
} from "lucide-react";

// ── Constants ─────────────────────────────────────────────────────────────────

const CHANNELS: { id: SocialChannel; label: string }[] = [
  { id: "facebook", label: "Facebook" },
  { id: "instagram", label: "Instagram" },
  { id: "linkedin", label: "LinkedIn" },
  { id: "x", label: "X" },
  { id: "tiktok", label: "TikTok" },
];

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  scheduled: "bg-brand/15 text-brand-dark",
  published: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

const STATUS_NEXT: Record<string, ScheduledPost["status"]> = {
  draft: "scheduled",
  scheduled: "draft",
  published: "draft",
  failed: "scheduled",
};

const STATUS_ICON: Record<string, React.ReactNode> = {
  draft: <FileText size={10} />,
  scheduled: <Clock size={10} />,
  published: <CheckCircle2 size={10} />,
  failed: <AlertCircle size={10} />,
};

const CHAR_LIMITS: Record<SocialChannel, number> = {
  x: 280,
  facebook: 63206,
  instagram: 2200,
  linkedin: 3000,
  tiktok: 2200,
};

const BEST_TIMES: Record<SocialChannel, string> = {
  facebook: "Wed–Thu 1–3 PM",
  instagram: "Tue–Fri 11 AM, 2 PM",
  linkedin: "Tue–Thu 8–10 AM",
  x: "Mon–Fri 9 AM, 12 PM",
  tiktok: "Tue–Fri 7–9 PM",
};

const PERIOD_OPTIONS = [7, 30, 90] as const;
type Period = (typeof PERIOD_OPTIONS)[number];

const CHANNEL_COLOURS: Record<string, string> = {
  facebook: "bg-blue-100 text-blue-700",
  instagram: "bg-pink-100 text-pink-700",
  linkedin: "bg-sky-100 text-sky-700",
  x: "bg-slate-100 text-slate-700",
  tiktok: "bg-purple-100 text-purple-700",
};

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

// ── Analytics tab ─────────────────────────────────────────────────────────────

function AnalyticsTab() {
  const [days, setDays] = React.useState<Period>(30);
  const [channel, setChannel] = React.useState<string>("");
  const [data, setData] = React.useState<SocialAnalytics | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [lastFetched, setLastFetched] = React.useState<Date | null>(null);

  const load = React.useCallback(async (d: Period, ch: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await socialSchedulerApi.analytics(d, ch || undefined);
      setData(result);
      setLastFetched(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load(days, channel);
  }, [load, days, channel]);

  const channelEntries = Object.entries(data?.by_channel ?? {}).sort(
    (a, b) => b[1].reach - a[1].reach
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border border-slate-200 bg-white overflow-hidden">
          {PERIOD_OPTIONS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setDays(p)}
              className={`px-4 py-1.5 text-xs font-medium ${
                days === p ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {p}d
            </button>
          ))}
        </div>
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 outline-none focus:border-brand"
        >
          <option value="">All platforms</option>
          {CHANNELS.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void load(days, channel)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
        {lastFetched && (
          <span className="text-[11px] text-slate-400">
            Updated {lastFetched.toLocaleTimeString()}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && !data && (
        <div className="flex justify-center py-16 text-slate-400">
          <Loader2 className="animate-spin" size={24} />
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              {
                label: "Total reach",
                value: fmt(data.totals.reach),
                icon: Eye,
                color: "text-brand",
              },
              {
                label: "Total likes",
                value: fmt(data.totals.likes),
                icon: ThumbsUp,
                color: "text-pink-500",
              },
              {
                label: "Comments",
                value: fmt(data.totals.comments),
                icon: MessageCircle,
                color: "text-amber-500",
              },
              {
                label: "Avg engagement rate",
                value: `${data.avg_engagement_rate}%`,
                icon: TrendingUp,
                color: "text-emerald-500",
              },
            ].map((c) => (
              <div
                key={c.label}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className={`mb-1 ${c.color}`}>
                  <c.icon size={16} />
                </div>
                <p className="text-xl font-bold text-slate-900">{c.value}</p>
                <p className="text-[11px] text-slate-500 mt-0.5">{c.label}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Shares", value: fmt(data.totals.shares), icon: Share2 },
              { label: "Clicks", value: fmt(data.totals.clicks), icon: MousePointer },
              {
                label: "Avg reach / post",
                value: fmt(data.avg_reach_per_post),
                icon: BarChart2,
              },
            ].map((c) => (
              <div
                key={c.label}
                className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm flex items-center gap-3"
              >
                <c.icon size={18} className="text-slate-400 shrink-0" />
                <div>
                  <p className="text-lg font-bold text-slate-900">{c.value}</p>
                  <p className="text-[11px] text-slate-500">{c.label}</p>
                </div>
              </div>
            ))}
          </div>

          {channelEntries.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
              <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  By platform
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[600px] text-sm">
                  <thead className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    <tr className="border-b border-slate-100">
                      <th className="px-4 py-2 text-left">Platform</th>
                      <th className="px-4 py-2 text-right">Posts</th>
                      <th className="px-4 py-2 text-right">Reach</th>
                      <th className="px-4 py-2 text-right">Likes</th>
                      <th className="px-4 py-2 text-right">Comments</th>
                      <th className="px-4 py-2 text-right">Shares</th>
                      <th className="px-4 py-2 text-right">Clicks</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {channelEntries.map(([ch, stats]) => (
                      <tr key={ch} className="hover:bg-slate-50/80">
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-md px-2 py-0.5 text-[11px] font-semibold capitalize ${
                              CHANNEL_COLOURS[ch] ?? "bg-slate-100 text-slate-700"
                            }`}
                          >
                            {ch}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right text-slate-700">{stats.posts}</td>
                        <td className="px-4 py-3 text-right font-medium text-slate-900">
                          {fmt(stats.reach)}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-700">
                          {fmt(stats.likes)}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-700">
                          {fmt(stats.comments)}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-700">
                          {fmt(stats.shares)}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-700">
                          {fmt(stats.clicks)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-3 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Published posts — engagement
              </h3>
              {data.unsynced_posts > 0 && (
                <span className="text-[11px] text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
                  {data.unsynced_posts} post{data.unsynced_posts > 1 ? "s" : ""} awaiting sync
                </span>
              )}
            </div>
            {data.top_posts.length === 0 ? (
              <p className="px-4 py-10 text-center text-sm text-slate-400">
                No published posts in the last {days} days.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-sm">
                  <thead className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    <tr className="border-b border-slate-100">
                      <th className="px-4 py-2 text-left">Post</th>
                      <th className="px-4 py-2 text-left">Channels</th>
                      <th className="px-4 py-2 text-right">Reach</th>
                      <th className="px-4 py-2 text-right">Likes</th>
                      <th className="px-4 py-2 text-right">Comments</th>
                      <th className="px-4 py-2 text-right">Shares</th>
                      <th className="px-4 py-2 text-right">Clicks</th>
                      <th className="px-4 py-2 text-right">Synced</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.top_posts.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-50/80">
                        <td className="px-4 py-3 max-w-[200px]">
                          <p className="truncate font-medium text-slate-900">
                            {p.title || "Untitled"}
                          </p>
                          <p className="text-[10px] text-slate-400">
                            {new Date(p.date).toLocaleDateString(undefined, {
                              month: "short",
                              day: "numeric",
                            })}
                          </p>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {p.channels.map((ch) => (
                              <span
                                key={ch}
                                className={`rounded px-1.5 py-0.5 text-[10px] font-medium capitalize ${
                                  CHANNEL_COLOURS[ch] ?? "bg-slate-100 text-slate-700"
                                }`}
                              >
                                {ch}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right font-medium text-slate-900">
                          {fmt(p.reach)}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-700">{fmt(p.likes)}</td>
                        <td className="px-4 py-3 text-right text-slate-700">
                          {fmt(p.comments)}
                        </td>
                        <td className="px-4 py-3 text-right text-slate-700">{fmt(p.shares)}</td>
                        <td className="px-4 py-3 text-right text-slate-700">{fmt(p.clicks)}</td>
                        <td className="px-4 py-3 text-right">
                          {p.engagement_synced_at ? (
                            <span className="text-[10px] text-emerald-600">
                              {new Date(p.engagement_synced_at).toLocaleTimeString(undefined, {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          ) : (
                            <span className="text-[10px] text-amber-500">Pending</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p className="text-[11px] text-slate-400 text-center">
            Showing {data.total_posts} published post{data.total_posts !== 1 ? "s" : ""} · Metrics
            sync automatically every 30 min after publishing
          </p>
        </>
      )}
    </div>
  );
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function SummaryCards({ rows }: { rows: ScheduledPost[] }) {
  const counts = {
    total: rows.length,
    scheduled: rows.filter((r) => r.status === "scheduled").length,
    published: rows.filter((r) => r.status === "published").length,
    draft: rows.filter((r) => r.status === "draft").length,
  };
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        { label: "Total posts", value: counts.total, icon: CalendarClock, color: "text-brand" },
        { label: "Scheduled", value: counts.scheduled, icon: Clock, color: "text-blue-500" },
        {
          label: "Published",
          value: counts.published,
          icon: CheckCircle2,
          color: "text-emerald-500",
        },
        { label: "Drafts", value: counts.draft, icon: FileText, color: "text-slate-400" },
      ].map((c) => (
        <div
          key={c.label}
          className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
        >
          <div className={`mb-1 ${c.color}`}>
            <c.icon size={16} />
          </div>
          <p className="text-xl font-bold text-slate-900">{c.value}</p>
          <p className="text-[11px] text-slate-500 mt-0.5">{c.label}</p>
        </div>
      ))}
    </div>
  );
}

// ── Live post preview (shown inside the drawer) ───────────────────────────────

function PostPreview({ modal }: { modal: Partial<ScheduledPost> }) {
  const firstAsset = modal.assets?.[0];
  const imgSrc = firstAsset?.preview_data_url ?? modal.image_url;
  const isVideo = firstAsset?.mime_type?.startsWith("video/");
  const channels = (modal.channels ?? []) as SocialChannel[];

  const scheduledDate = modal.scheduled_at ? new Date(modal.scheduled_at) : null;
  const validDate = scheduledDate && !isNaN(scheduledDate.getTime());

  return (
    <div className="p-4 space-y-5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        Post preview
      </p>

      {/* Social card mock */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        {/* Author row */}
        <div className="flex items-center gap-2.5 px-3 pt-3 pb-2">
          <div className="h-8 w-8 rounded-full bg-brand/20 flex items-center justify-center text-xs font-bold text-brand-dark shrink-0">
            P
          </div>
          <div className="min-w-0">
            <p className="text-[12px] font-semibold text-slate-900 truncate">Your Page</p>
            <p className="text-[10px] text-slate-400">
              {validDate
                ? scheduledDate!.toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "Scheduled"}
            </p>
          </div>
        </div>

        {/* Caption */}
        <div className="px-3 pb-2">
          {modal.title ? (
            <p className="text-[12px] font-semibold text-slate-900 truncate">{modal.title}</p>
          ) : null}
          {modal.body ? (
            <p className="mt-0.5 text-[11px] text-slate-700 line-clamp-4 whitespace-pre-wrap">
              {modal.body}
            </p>
          ) : (
            <p className="text-[11px] text-slate-400 italic">Start typing to preview…</p>
          )}
        </div>

        {/* Media */}
        {imgSrc && !isVideo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imgSrc} alt="" className="w-full aspect-video object-cover" />
        ) : isVideo ? (
          <div className="w-full aspect-video bg-slate-900 flex items-center justify-center">
            <p className="text-white text-xs font-medium">Video</p>
          </div>
        ) : (
          <div className="w-full aspect-video bg-gradient-to-br from-slate-100 to-slate-50 flex items-center justify-center">
            <ImageIcon size={22} className="text-slate-300" />
          </div>
        )}

        {/* Engagement bar */}
        <div className="flex items-center gap-4 px-3 py-2 border-t border-slate-100 text-[10px] text-slate-400">
          <span className="flex items-center gap-1">
            <ThumbsUp size={10} /> Like
          </span>
          <span className="flex items-center gap-1">
            <MessageCircle size={10} /> Comment
          </span>
          <span className="flex items-center gap-1">
            <Share2 size={10} /> Share
          </span>
        </div>
      </div>

      {/* Publishing to */}
      {channels.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">
            Publishing to
          </p>
          <div className="flex flex-wrap gap-1.5">
            {channels.map((ch) => (
              <span
                key={ch}
                className={`rounded-md px-2 py-0.5 text-[10px] font-semibold capitalize ${
                  CHANNEL_COLOURS[ch] ?? "bg-slate-100 text-slate-700"
                }`}
              >
                {ch}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Char count bars */}
      {channels.length > 0 && (modal.body ?? "").length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-2">
            Character limits
          </p>
          <div className="space-y-2">
            {channels.map((ch) => {
              const limit = CHAR_LIMITS[ch] ?? 9999;
              const len = (modal.body ?? "").length;
              const pct = Math.min((len / limit) * 100, 100);
              const over = len > limit;
              return (
                <div key={ch}>
                  <div className="flex justify-between text-[10px] mb-0.5">
                    <span className="capitalize font-medium text-slate-600">{ch}</span>
                    <span className={over ? "font-semibold text-red-500" : "text-slate-400"}>
                      {len.toLocaleString()}/{limit.toLocaleString()}
                    </span>
                  </div>
                  <div className="h-1 w-full rounded-full bg-slate-200 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-200 ${
                        over ? "bg-red-500" : pct > 90 ? "bg-amber-400" : "bg-brand"
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Best times */}
      {channels.some((ch) => BEST_TIMES[ch]) && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">
            Best posting times
          </p>
          <div className="space-y-1.5">
            {channels
              .filter((ch) => BEST_TIMES[ch])
              .map((ch) => (
                <div key={ch} className="flex items-start gap-1.5 text-[10px] text-slate-500">
                  <Clock size={9} className="mt-0.5 shrink-0 text-slate-400" />
                  <span>
                    <span className="font-semibold capitalize">{ch}</span>: {BEST_TIMES[ch]}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function emptyForm(): Partial<ScheduledPost> {
  return {
    title: "",
    body: "",
    channels: ["facebook"],
    scheduled_at: new Date(Date.now() + 3600_000).toISOString().slice(0, 16),
    status: "draft",
    placement_id: "ig_feed_square",
    link_url: "",
  };
}

function rowPreview(r: ScheduledPost): { url?: string; video: boolean; count: number } {
  const a = r.assets;
  if (a?.length) {
    const first = a[0];
    return {
      url: first.preview_data_url,
      video: first.mime_type.startsWith("video/"),
      count: a.length,
    };
  }
  if (r.image_url) {
    return { url: r.image_url, video: false, count: 1 };
  }
  return { url: undefined, video: false, count: 0 };
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SocialSchedulerPage() {
  const [rows, setRows] = useState<ScheduledPost[]>([]);
  const [modal, setModal] = useState<Partial<ScheduledPost> | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [hydrated, setHydrated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"posts" | "analytics">("posts");

  // Drawer UX state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [titleError, setTitleError] = useState(false);
  const [bodyError, setBodyError] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [mediaDragOver, setMediaDragOver] = useState(false);
  const mediaInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const { posts } = await socialSchedulerApi.list();
      setRows(posts);
    } catch {
      setRows([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
    setHydrated(true);
  }, [refresh]);

  // Reset helper state when drawer closes
  useEffect(() => {
    if (!modal) {
      setAiPrompt("");
      setAiError(null);
      setAiLoading(false);
      setSaveError(null);
      setTitleError(false);
      setBodyError(false);
      setShowAdvanced(false);
      setMediaDragOver(false);
    }
  }, [modal]);

  // Escape key closes drawer
  useEffect(() => {
    if (!modal) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setDrawerOpen(false);
        setTimeout(() => setModal(null), 300);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [modal]);

  const filtered = useMemo(() => {
    if (filter === "all") return rows;
    return rows.filter((r) => r.status === filter);
  }, [rows, filter]);

  // ── Close drawer with animation ──────────────────────────────────────────────

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setTimeout(() => setModal(null), 300);
  }, []);

  // ── Open helpers (trigger slide-in animation) ────────────────────────────────

  function openNew() {
    setModal(emptyForm());
    requestAnimationFrame(() => requestAnimationFrame(() => setDrawerOpen(true)));
  }

  function openEdit(row: ScheduledPost) {
    const at = row.scheduled_at.includes("T")
      ? row.scheduled_at.slice(0, 16)
      : row.scheduled_at;
    setModal({ ...row, scheduled_at: at });
    requestAnimationFrame(() => requestAnimationFrame(() => setDrawerOpen(true)));
  }

  // ── Actions ──────────────────────────────────────────────────────────────────

  async function duplicatePost(row: ScheduledPost) {
    try {
      await socialSchedulerApi.create({
        title: `${row.title} (copy)`,
        body: row.body,
        channels: row.channels as SocialChannel[],
        scheduled_at: new Date(Date.now() + 3600_000).toISOString(),
        status: "draft",
        post_kind: row.post_kind,
        placement_id: row.placement_id,
        placement_width: row.placement_width,
        placement_height: row.placement_height,
        link_url: row.link_url,
        assets: row.assets,
        image_url: row.image_url,
      });
      await refresh();
      toast.success("Post duplicated");
    } catch {
      toast.error("Failed to duplicate post");
    }
  }

  async function quickToggleStatus(row: ScheduledPost) {
    try {
      await socialSchedulerApi.update(row.id, { status: STATUS_NEXT[row.status] ?? "draft" });
      await refresh();
    } catch {
      toast.error("Failed to update status");
    }
  }

  function toggleChannel(ch: SocialChannel) {
    if (!modal) return;
    const cur = new Set(modal.channels ?? []);
    if (cur.has(ch)) cur.delete(ch);
    else cur.add(ch);
    setModal({ ...modal, channels: Array.from(cur) as SocialChannel[] });
  }

  function removeModalAsset(idx: number) {
    if (!modal) return;
    const assets = [...(modal.assets ?? [])];
    assets.splice(idx, 1);
    setModal({ ...modal, assets });
  }

  async function handleMediaFiles(fileList: FileList | null) {
    if (!fileList?.length) return;
    const newAssets: ScheduledPostAsset[] = [];
    for (const file of Array.from(fileList)) {
      if (!file.type.startsWith("image/") && !file.type.startsWith("video/")) continue;
      const isVid = file.type.startsWith("video/");
      const preview = !isVid ? await fileToPreviewDataUrl(file) : undefined;
      newAssets.push({ file_name: file.name, mime_type: file.type, preview_data_url: preview });
    }
    if (newAssets.length === 0) return;
    setModal((prev) =>
      prev ? { ...prev, assets: [...(prev.assets ?? []), ...newAssets] } : prev
    );
  }

  async function saveModal() {
    if (!modal) return;

    const titleMissing = !modal.title?.trim();
    const bodyMissing = !modal.body?.trim();

    if (titleMissing || bodyMissing) {
      setTitleError(titleMissing);
      setBodyError(bodyMissing);
      setSaveError("Please fill in the required fields marked above.");
      return;
    }

    setTitleError(false);
    setBodyError(false);
    setSaveError(null);

    const preset = presetById(modal.placement_id as PostPlacementId | undefined);
    const w = modal.placement_id === "custom" ? (modal.placement_width ?? 1080) : preset.width;
    const h = modal.placement_id === "custom" ? (modal.placement_height ?? 1080) : preset.height;

    const payload = {
      title: modal.title!.trim(),
      body: modal.body!.trim(),
      channels: (modal.channels?.length ? modal.channels : ["facebook"]) as SocialChannel[],
      scheduled_at: modal.scheduled_at
        ? new Date(modal.scheduled_at).toISOString()
        : new Date().toISOString(),
      status: (modal.status ?? "draft") as ScheduledPost["status"],
      post_kind: modal.post_kind,
      placement_id: modal.placement_id,
      placement_width: w,
      placement_height: h,
      link_url: modal.link_url?.trim() || undefined,
      assets: modal.assets,
      image_url: modal.image_url,
    };

    setSaving(true);
    try {
      if (modal.id) {
        await socialSchedulerApi.update(modal.id, payload);
      } else {
        await socialSchedulerApi.create(payload);
      }
      await refresh();
      toast.success(modal.id ? "Post updated" : "Post scheduled");
      closeDrawer();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to save post";
      setSaveError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function runAiDraft() {
    if (!modal || !aiPrompt.trim()) return;
    setAiLoading(true);
    setAiError(null);
    try {
      const channels = (modal.channels?.length ? modal.channels : ["facebook"]) as string[];
      const { title, body } = await marketingApi.draftSocialPost({
        prompt: aiPrompt.trim(),
        channels,
      });
      setModal({ ...modal, title, body });
    } catch (e) {
      setAiError(e instanceof Error ? e.message : "Could not generate draft");
    } finally {
      setAiLoading(false);
    }
  }

  // ── Loading state ────────────────────────────────────────────────────────────

  if (!hydrated) {
    return (
      <div className="flex justify-center py-24 text-slate-400">
        <Loader2 className="animate-spin" size={24} />
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-4 sm:p-6 pb-16">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-brand-dark">
            <CalendarClock size={20} />
            <span className="text-[11px] font-semibold uppercase tracking-wide">Marketing</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Social scheduler</h1>
          <p className="mt-1 text-sm text-slate-500">
            Text, image, video, carousel, and link posts — each with a{" "}
            <strong className="text-slate-700">placement / size</strong> preset. Use{" "}
            <strong className="text-slate-700">Draft with AI</strong> to generate title and caption
            from a short brief.
          </p>
        </div>
        {activeTab === "posts" && (
          <button
            type="button"
            onClick={openNew}
            className="flex items-center justify-center gap-1.5 rounded-xl bg-brand-dark px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand transition-colors"
          >
            <Plus size={16} /> New post
          </button>
        )}
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 rounded-xl border border-slate-200 bg-slate-100 p-1 w-fit">
        {(["posts", "analytics"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {tab === "posts" ? <CalendarClock size={14} /> : <BarChart2 size={14} />}
            {tab === "posts" ? "Posts" : "Analytics"}
          </button>
        ))}
      </div>

      <MarketingApiBanner product="Social scheduling" />

      {activeTab === "analytics" && <AnalyticsTab />}

      {activeTab === "posts" && (
        <>
          {rows.length > 0 && <SummaryCards rows={rows} />}

          <BulkScheduleSection onCommitted={refresh} />

          {/* Filter pills */}
          <div className="flex flex-wrap items-center gap-2">
            {(["all", "draft", "scheduled", "published", "failed"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                  filter === f
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {f}
              </button>
            ))}
          </div>

          {/* Posts table */}
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50/80 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="w-14 px-4 py-3"> </th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Channels</th>
                  <th className="px-4 py-3">When</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="w-28 px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-16 text-center">
                      <div className="flex flex-col items-center gap-3 text-slate-400">
                        <CalendarClock size={32} className="opacity-30" />
                        <p className="text-sm">No posts yet.</p>
                        <button
                          type="button"
                          onClick={openNew}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand"
                        >
                          <Plus size={13} /> Create your first post
                        </button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filtered.map((r) => {
                    const pv = rowPreview(r);
                    const pk = r.post_kind as PostKind | undefined;
                    const place = presetById(r.placement_id as PostPlacementId | undefined);
                    const dim =
                      r.placement_id === "custom" && r.placement_width && r.placement_height
                        ? `${r.placement_width}×${r.placement_height}`
                        : `${place.width}×${place.height}`;
                    return (
                      <tr key={r.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="px-4 py-3">
                          <div className="relative h-10 w-10">
                            {pv.url && !pv.video ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={pv.url}
                                alt=""
                                className="h-10 w-10 rounded-md border border-slate-200 object-cover"
                              />
                            ) : pv.video ? (
                              <div className="flex h-10 w-10 items-center justify-center rounded-md border border-slate-200 bg-slate-900 text-[9px] font-bold text-white">
                                VID
                              </div>
                            ) : (
                              <div className="flex h-10 w-10 items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50">
                                <ImageIcon size={14} className="text-slate-300" />
                              </div>
                            )}
                            {pv.count > 1 ? (
                              <span className="absolute -bottom-1 -right-1 rounded-full bg-brand-dark px-1 text-[9px] font-bold text-white">
                                {pv.count}
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-[11px] text-slate-700">
                          {pk ? (POST_KIND_LABELS as Record<string, string>)[pk] ?? pk : "—"}
                          {r.link_url ? (
                            <p className="mt-0.5 truncate text-[10px] text-brand-dark">
                              {r.link_url}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 text-[11px] text-slate-600">
                          <p className="font-medium text-slate-800">{place.label}</p>
                          <p className="text-[10px] text-slate-500">
                            {dim}px · {place.aspect}
                          </p>
                        </td>
                        <td className="px-4 py-3">
                          <p className="font-medium text-slate-900">{r.title}</p>
                          <p className="line-clamp-1 text-xs text-slate-500">{r.body}</p>
                          {r.assets?.length ? (
                            <p className="mt-0.5 line-clamp-2 text-[10px] text-slate-400">
                              {r.assets.map((a) => a.file_name).join(" · ")}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {r.channels.map((c) => (
                              <span
                                key={c}
                                className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium capitalize ${
                                  CHANNEL_COLOURS[c] ?? "bg-slate-100 text-slate-700"
                                }`}
                              >
                                {c}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                          {formatDateTime(r.scheduled_at)}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            title="Click to toggle status"
                            onClick={() => void quickToggleStatus(r)}
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium cursor-pointer hover:opacity-75 transition-opacity ${
                              STATUS_STYLE[r.status] ?? "bg-slate-100"
                            }`}
                          >
                            {STATUS_ICON[r.status]}
                            {r.status}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => openEdit(r)}
                            className="mr-0.5 inline-flex rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                            title="Edit"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={() => void duplicatePost(r)}
                            className="mr-0.5 inline-flex rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                            title="Duplicate"
                          >
                            <Copy size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              if (confirm("Delete this post?")) {
                                try {
                                  await socialSchedulerApi.delete(r.id);
                                  await refresh();
                                  toast.success("Post deleted");
                                } catch {
                                  toast.error("Failed to delete post");
                                }
                              }
                            }}
                            className="inline-flex rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500"
                            title="Delete"
                          >
                            <Trash2 size={13} />
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <section className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 text-xs text-slate-600">
            <p className="font-semibold text-slate-800">Ready for integration</p>
            <ul className="mt-2 list-inside list-disc space-y-1">
              <li>
                OAuth per network under Integrations → token refresh and page/account pickers.
              </li>
              <li>
                Bulk designs: batch upload to storage, then attach returned media IDs to each
                scheduled row.
              </li>
              <li>
                Worker: cron or queue consumes scheduled rows and updates status to
                published/failed.
              </li>
            </ul>
          </section>
        </>
      )}

      {/* ── Post drawer ─────────────────────────────────────────────────────────── */}
      {modal && (
        <>
          {/* Backdrop */}
          <div
            aria-hidden="true"
            className={`fixed inset-0 z-40 bg-black/40 transition-opacity duration-300 ${
              drawerOpen ? "opacity-100" : "opacity-0"
            }`}
            onClick={closeDrawer}
          />

          {/* Drawer panel */}
          <div
            role="dialog"
            aria-modal="true"
            aria-label={modal.id ? "Edit post" : "New post"}
            className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col bg-white shadow-2xl transition-transform duration-300 ease-out ${
              drawerOpen ? "translate-x-0" : "translate-x-full"
            }`}
          >
            {/* Drawer header */}
            <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  {modal.id ? "Edit post" : "New scheduled post"}
                </h2>
                {(modal.channels ?? []).length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {((modal.channels ?? []) as SocialChannel[]).map((ch) => (
                      <span
                        key={ch}
                        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold capitalize ${
                          CHANNEL_COLOURS[ch] ?? "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {ch}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={closeDrawer}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Drawer body: form + live preview */}
            <div className="flex flex-1 overflow-hidden">
              {/* ── Form panel ── */}
              <div className="flex-1 overflow-y-auto">
                <div className="divide-y divide-slate-100">
                  {/* AI Draft */}
                  <div className="px-5 py-5">
                    <div className="rounded-xl border border-brand/20 bg-gradient-to-br from-brand/8 to-violet-50/60 p-4">
                      <div className="flex items-center gap-2 text-brand-dark">
                        <Sparkles size={15} className="shrink-0" />
                        <span className="text-xs font-semibold">Draft with AI</span>
                      </div>
                      <p className="mt-1 text-[11px] text-slate-500">
                        Describe your post — tone, offer, CTA. Selected channels are sent to the
                        model.
                      </p>
                      <textarea
                        className="mt-2.5 min-h-[64px] w-full rounded-lg border border-brand/25 bg-white px-3 py-2 text-sm outline-none focus:border-brand resize-none"
                        value={aiPrompt}
                        onChange={(e) => setAiPrompt(e.target.value)}
                        placeholder="e.g. Announce 20% off weekend brunch, friendly tone, end with 'book on WhatsApp'"
                        disabled={aiLoading}
                      />
                      {aiError ? (
                        <p className="mt-1.5 text-xs text-red-600">{aiError}</p>
                      ) : null}
                      <button
                        type="button"
                        disabled={aiLoading || !aiPrompt.trim()}
                        onClick={() => void runAiDraft()}
                        className="mt-2.5 inline-flex items-center gap-2 rounded-lg bg-brand-dark px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
                      >
                        {aiLoading ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Sparkles size={13} />
                        )}
                        {aiLoading ? "Generating…" : "Generate title & caption"}
                      </button>
                    </div>
                  </div>

                  {/* Content */}
                  <div className="px-5 py-5 space-y-4">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Content
                    </p>

                    {/* Title */}
                    <div>
                      <label className="text-xs font-medium text-slate-700">
                        Title <span className="text-red-400">*</span>
                      </label>
                      <input
                        className={`mt-1.5 w-full rounded-lg border px-3 py-2 text-sm outline-none transition-colors focus:border-brand ${
                          titleError
                            ? "border-red-400 bg-red-50/40 focus:border-red-400"
                            : "border-slate-200"
                        }`}
                        value={modal.title ?? ""}
                        onChange={(e) => {
                          setModal({ ...modal, title: e.target.value });
                          if (e.target.value.trim()) setTitleError(false);
                        }}
                        placeholder="Spring promo launch"
                      />
                      {titleError && (
                        <p className="mt-1 text-xs text-red-500">Title is required.</p>
                      )}
                    </div>

                    {/* Caption */}
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-medium text-slate-700">
                          Caption <span className="text-red-400">*</span>
                        </label>
                        <span
                          className={`text-[10px] font-medium ${(() => {
                            const activeChannels = (modal.channels ?? []) as SocialChannel[];
                            const limit = activeChannels.length
                              ? Math.min(...activeChannels.map((c) => CHAR_LIMITS[c] ?? 9999))
                              : 9999;
                            const len = (modal.body ?? "").length;
                            return len > limit
                              ? "text-red-500"
                              : len > limit * 0.9
                                ? "text-amber-500"
                                : "text-slate-400";
                          })()}`}
                        >
                          {(modal.body ?? "").length}
                          {" / "}
                          {(() => {
                            const activeChannels = (modal.channels ?? []) as SocialChannel[];
                            return activeChannels.length
                              ? Math.min(
                                  ...activeChannels.map((c) => CHAR_LIMITS[c] ?? 9999)
                                ).toLocaleString()
                              : "∞";
                          })()}
                        </span>
                      </div>
                      <textarea
                        className={`mt-1.5 min-h-[110px] w-full resize-y rounded-lg border px-3 py-2.5 text-sm leading-relaxed outline-none transition-colors focus:border-brand ${
                          bodyError
                            ? "border-red-400 bg-red-50/40 focus:border-red-400"
                            : "border-slate-200"
                        }`}
                        value={modal.body ?? ""}
                        onChange={(e) => {
                          setModal({ ...modal, body: e.target.value });
                          if (e.target.value.trim()) setBodyError(false);
                        }}
                        placeholder="Write your post caption… hashtags welcome."
                      />
                      {bodyError && (
                        <p className="mt-1 text-xs text-red-500">Caption is required.</p>
                      )}
                    </div>
                  </div>

                  {/* Media */}
                  <div className="px-5 py-5 space-y-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Media
                    </p>

                    {/* Existing assets grid */}
                    {((modal.assets?.length ?? 0) > 0 || modal.image_url) && (
                      <div className="flex flex-wrap gap-2">
                        {modal.assets?.length
                          ? modal.assets.map((a, i) => (
                              <div key={i} className="group relative">
                                {a.preview_data_url && a.mime_type.startsWith("image/") ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img
                                    src={a.preview_data_url}
                                    alt=""
                                    className="h-16 w-16 rounded-lg border border-slate-200 object-cover"
                                  />
                                ) : (
                                  <div className="flex h-16 w-16 items-center justify-center rounded-lg border border-slate-200 bg-slate-100 text-[9px] font-bold text-slate-500">
                                    {a.mime_type.startsWith("video/") ? "VIDEO" : "FILE"}
                                  </div>
                                )}
                                <button
                                  type="button"
                                  onClick={() => removeModalAsset(i)}
                                  className="absolute -right-1.5 -top-1.5 hidden h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white shadow-sm group-hover:flex"
                                  title="Remove"
                                >
                                  <X size={10} />
                                </button>
                                <p className="mt-0.5 max-w-[64px] truncate text-[9px] text-slate-500">
                                  {a.file_name}
                                </p>
                              </div>
                            ))
                          : modal.image_url
                            ? (
                                <div className="group relative">
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img
                                    src={modal.image_url}
                                    alt="Design"
                                    className="h-16 w-16 rounded-lg border border-slate-200 object-cover"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => setModal({ ...modal, image_url: undefined })}
                                    className="absolute -right-1.5 -top-1.5 hidden h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white shadow-sm group-hover:flex"
                                  >
                                    <X size={10} />
                                  </button>
                                </div>
                              )
                            : null}
                      </div>
                    )}

                    {/* Drop zone */}
                    <div
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && mediaInputRef.current?.click()}
                      onClick={() => mediaInputRef.current?.click()}
                      onDragOver={(e) => {
                        e.preventDefault();
                        setMediaDragOver(true);
                      }}
                      onDragLeave={() => setMediaDragOver(false)}
                      onDrop={(e) => {
                        e.preventDefault();
                        setMediaDragOver(false);
                        void handleMediaFiles(e.dataTransfer.files);
                      }}
                      className={`flex cursor-pointer items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-5 text-center transition-all duration-150 ${
                        mediaDragOver
                          ? "border-brand bg-brand/5 text-brand-dark"
                          : "border-slate-200 bg-slate-50/50 text-slate-500 hover:border-brand/50 hover:bg-brand/5"
                      }`}
                    >
                      <Upload
                        size={18}
                        className={`shrink-0 transition-colors ${mediaDragOver ? "text-brand" : "text-slate-400"}`}
                      />
                      <div className="text-left">
                        <p className="text-xs font-medium text-slate-700">
                          Drop media or click to browse
                        </p>
                        <p className="text-[11px] text-slate-400">
                          PNG, JPG, WebP, GIF, MP4, MOV… Multiple files for carousel.
                        </p>
                      </div>
                      <input
                        ref={mediaInputRef}
                        type="file"
                        accept="image/*,video/*"
                        multiple
                        className="hidden"
                        onChange={(e) => {
                          void handleMediaFiles(e.target.files);
                          e.target.value = "";
                        }}
                      />
                    </div>
                  </div>

                  {/* Channels */}
                  <div className="px-5 py-5 space-y-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Channels
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {CHANNELS.map((c) => {
                        const on = (modal.channels ?? []).includes(c.id);
                        return (
                          <button
                            key={c.id}
                            type="button"
                            onClick={() => toggleChannel(c.id)}
                            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                              on
                                ? "bg-brand-dark text-white"
                                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                            }`}
                          >
                            {c.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Schedule */}
                  <div className="px-5 py-5 space-y-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Schedule
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-medium text-slate-700">Date & time</label>
                        <input
                          type="datetime-local"
                          className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                          value={modal.scheduled_at?.slice(0, 16) ?? ""}
                          onChange={(e) => setModal({ ...modal, scheduled_at: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-slate-700">Status</label>
                        <select
                          className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                          value={modal.status ?? "draft"}
                          onChange={(e) =>
                            setModal({
                              ...modal,
                              status: e.target.value as ScheduledPost["status"],
                            })
                          }
                        >
                          <option value="draft">Draft</option>
                          <option value="scheduled">Scheduled</option>
                          <option value="published">Published (manual)</option>
                          <option value="failed">Failed (manual)</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  {/* Advanced settings (collapsible) */}
                  <div className="px-5 py-4">
                    <button
                      type="button"
                      onClick={() => setShowAdvanced((v) => !v)}
                      className="flex w-full items-center justify-between rounded-lg py-1 text-xs font-semibold text-slate-500 hover:text-slate-700 transition-colors"
                    >
                      <span className="flex items-center gap-1.5">
                        <ChevronDown
                          size={14}
                          className={`transition-transform duration-200 ${showAdvanced ? "rotate-180" : ""}`}
                        />
                        Advanced settings
                      </span>
                      {(modal.post_kind ?? modal.link_url ?? modal.placement_id) && (
                        <span className="rounded-full bg-brand/15 px-2 py-0.5 text-[10px] text-brand-dark">
                          configured
                        </span>
                      )}
                    </button>

                    {showAdvanced && (
                      <div className="mt-4 space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="text-xs font-medium text-slate-700">
                              Post type
                            </label>
                            <select
                              className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                              value={modal.post_kind ?? ""}
                              onChange={(e) =>
                                setModal({
                                  ...modal,
                                  post_kind: (e.target.value || undefined) as
                                    | PostKind
                                    | undefined,
                                })
                              }
                            >
                              <option value="">Auto / unset</option>
                              {(Object.keys(POST_KIND_LABELS) as PostKind[]).map((k) => (
                                <option key={k} value={k}>
                                  {POST_KIND_LABELS[k]}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div>
                            <label className="text-xs font-medium text-slate-700">Link URL</label>
                            <input
                              className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                              value={modal.link_url ?? ""}
                              onChange={(e) =>
                                setModal({ ...modal, link_url: e.target.value })
                              }
                              placeholder="https://"
                            />
                          </div>
                        </div>

                        <div>
                          <label className="text-xs font-medium text-slate-700">
                            Placement / target size
                          </label>
                          <select
                            className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                            value={modal.placement_id ?? "ig_feed_square"}
                            onChange={(e) =>
                              setModal({
                                ...modal,
                                placement_id: e.target.value as PostPlacementId,
                              })
                            }
                          >
                            {PLACEMENT_PRESETS.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.label} — {p.width}×{p.height}px ({p.aspect})
                              </option>
                            ))}
                          </select>
                        </div>

                        {modal.placement_id === "custom" && (
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="text-xs font-medium text-slate-700">
                                Width (px)
                              </label>
                              <input
                                type="number"
                                min={1}
                                className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                                value={modal.placement_width ?? 1080}
                                onChange={(e) =>
                                  setModal({
                                    ...modal,
                                    placement_width: Number(e.target.value) || 1080,
                                  })
                                }
                              />
                            </div>
                            <div>
                              <label className="text-xs font-medium text-slate-700">
                                Height (px)
                              </label>
                              <input
                                type="number"
                                min={1}
                                className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                                value={modal.placement_height ?? 1080}
                                onChange={(e) =>
                                  setModal({
                                    ...modal,
                                    placement_height: Number(e.target.value) || 1080,
                                  })
                                }
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* ── Preview panel (desktop only) ── */}
              <div className="hidden md:flex w-64 shrink-0 flex-col overflow-y-auto border-l border-slate-100 bg-slate-50">
                <PostPreview modal={modal} />
              </div>
            </div>

            {/* Drawer footer */}
            <div className="shrink-0 border-t border-slate-100 bg-white px-5 py-4">
              {saveError && (
                <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-600">
                  <AlertCircle size={13} className="mt-0.5 shrink-0" />
                  {saveError}
                </div>
              )}
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={closeDrawer}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void saveModal()}
                  className="inline-flex items-center gap-2 rounded-xl bg-brand-dark px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand disabled:opacity-60 transition-colors"
                >
                  {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {saving ? "Saving…" : modal.id ? "Update post" : "Save post"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

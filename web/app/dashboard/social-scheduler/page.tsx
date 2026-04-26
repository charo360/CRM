"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { marketingApi } from "@/lib/api";
import { MarketingApiBanner } from "@/components/marketing/MarketingApiBanner";
import { BulkScheduleSection } from "@/components/marketing/BulkScheduleSection";
import {
  type ScheduledPost,
  type SocialChannel,
  listScheduledPosts,
  upsertScheduledPost,
  deleteScheduledPost,
} from "@/lib/marketing-stubs";
import {
  POST_KIND_LABELS,
  PLACEMENT_PRESETS,
  presetById,
  type PostKind,
  type PostPlacementId,
} from "@/lib/social-post-presets";
import { formatDateTime } from "@/lib/utils";
import {
  CalendarClock,
  Plus,
  Trash2,
  Pencil,
  Loader2,
  Image as ImageIcon,
  X,
  Sparkles,
  Copy,
  Clock,
  CheckCircle2,
  FileText,
  AlertCircle,
} from "lucide-react";

const CHANNELS: { id: SocialChannel; label: string }[] = [
  { id: "facebook", label: "Facebook" },
  { id: "instagram", label: "Instagram" },
  { id: "linkedin", label: "LinkedIn" },
  { id: "x", label: "X" },
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
};

const BEST_TIMES: Record<SocialChannel, string> = {
  facebook: "Wed–Thu 1–3 PM",
  instagram: "Tue–Fri 11 AM, 2 PM",
  linkedin: "Tue–Thu 8–10 AM",
  x: "Mon–Fri 9 AM, 12 PM",
};

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
        { label: "Published", value: counts.published, icon: CheckCircle2, color: "text-emerald-500" },
        { label: "Drafts", value: counts.draft, icon: FileText, color: "text-slate-400" },
      ].map((c) => (
        <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className={`mb-1 ${c.color}`}><c.icon size={16} /></div>
          <p className="text-xl font-bold text-slate-900">{c.value}</p>
          <p className="text-[11px] text-slate-500 mt-0.5">{c.label}</p>
        </div>
      ))}
    </div>
  );
}

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
  return {
    url: r.media_preview_data_url,
    video: false,
    count: r.media_file_name || r.media_preview_data_url ? 1 : 0,
  };
}

export default function SocialSchedulerPage() {
  const [rows, setRows] = useState<ScheduledPost[]>([]);
  const [modal, setModal] = useState<Partial<ScheduledPost> | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [hydrated, setHydrated] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setRows(listScheduledPosts());
  }, []);

  useEffect(() => {
    refresh();
    setHydrated(true);
  }, [refresh]);

  useEffect(() => {
    if (!modal) {
      setAiPrompt("");
      setAiError(null);
      setAiLoading(false);
    }
  }, [modal]);

  const filtered = useMemo(() => {
    if (filter === "all") return rows;
    return rows.filter((r) => r.status === filter);
  }, [rows, filter]);

  function openNew() {
    setModal(emptyForm());
  }

  function duplicatePost(row: ScheduledPost) {
    upsertScheduledPost({
      ...row,
      id: undefined,
      title: `${row.title} (copy)`,
      status: "draft",
      scheduled_at: new Date(Date.now() + 3600_000).toISOString(),
    });
    refresh();
  }

  function quickToggleStatus(row: ScheduledPost) {
    upsertScheduledPost({ ...row, status: STATUS_NEXT[row.status] ?? "draft" });
    refresh();
  }

  function openEdit(row: ScheduledPost) {
    const at = row.scheduled_at.includes("T")
      ? row.scheduled_at.slice(0, 16)
      : row.scheduled_at;
    setModal({ ...row, scheduled_at: at });
  }

  function saveModal() {
    if (!modal?.title?.trim() || !modal.body?.trim()) return;
    const preset = presetById(modal.placement_id);
    const w =
      modal.placement_id === "custom"
        ? modal.placement_width ?? 1080
        : preset.width;
    const h =
      modal.placement_id === "custom"
        ? modal.placement_height ?? 1080
        : preset.height;

    upsertScheduledPost({
      id: modal.id,
      title: modal.title.trim(),
      body: modal.body.trim(),
      channels: (modal.channels?.length ? modal.channels : ["facebook"]) as SocialChannel[],
      scheduled_at: modal.scheduled_at
        ? new Date(modal.scheduled_at).toISOString()
        : new Date().toISOString(),
      status: modal.status ?? "draft",
      post_kind: modal.post_kind,
      placement_id: modal.placement_id,
      placement_width: w,
      placement_height: h,
      link_url: modal.link_url?.trim() || undefined,
      assets: modal.assets,
      media_file_name: modal.media_file_name,
      media_preview_data_url: modal.media_preview_data_url,
    });
    refresh();
    setModal(null);
  }

  function toggleChannel(ch: SocialChannel) {
    if (!modal) return;
    const cur = new Set(modal.channels ?? []);
    if (cur.has(ch)) cur.delete(ch);
    else cur.add(ch);
    setModal({ ...modal, channels: Array.from(cur) as SocialChannel[] });
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

  if (!hydrated) {
    return (
      <div className="flex justify-center py-24 text-slate-400">
        <Loader2 className="animate-spin" size={24} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:p-6 pb-16">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-brand-dark">
            <CalendarClock size={20} />
            <span className="text-[11px] font-semibold uppercase tracking-wide">Marketing</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Social scheduler</h1>
          <p className="mt-1 text-sm text-slate-500">
            Text, image, video, carousel, and link posts — each with a <strong className="text-slate-700">placement / size</strong>{" "}
            preset (feed, story, reel, 16:9, custom pixels, and more). Use <strong className="text-slate-700">Draft with AI</strong> in
            the post editor to generate title and caption from a short brief.
          </p>
        </div>
        <button
          type="button"
          onClick={openNew}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-dark px-4 py-2 text-sm font-semibold text-white hover:bg-brand"
        >
          <Plus size={16} />
          New post
        </button>
      </div>

      <MarketingApiBanner product="Social scheduling" />

      {rows.length > 0 && <SummaryCards rows={rows} />}

      <BulkScheduleSection onCommitted={refresh} />

      <div className="flex flex-wrap items-center gap-2">
        {(["all", "draft", "scheduled", "published", "failed"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`rounded-full px-3 py-1 text-xs font-medium capitalize ${
              filter === f ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

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
              <th className="px-4 py-3 w-28 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                  No posts yet. Create one — media upload and account linking will use your integration layer.
                </td>
              </tr>
            ) : (
              filtered.map((r) => {
                const pv = rowPreview(r);
                const pk = r.post_kind;
                const place = presetById(r.placement_id);
                const dim =
                  r.placement_id === "custom" && r.placement_width && r.placement_height
                    ? `${r.placement_width}×${r.placement_height}`
                    : `${place.width}×${place.height}`;
                return (
                <tr key={r.id} className="hover:bg-slate-50/80">
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
                    {pk ? POST_KIND_LABELS[pk] : "—"}
                    {r.link_url ? (
                      <p className="mt-0.5 truncate text-[10px] text-brand-dark">{r.link_url}</p>
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
                    ) : r.media_file_name ? (
                      <p className="mt-0.5 text-[10px] text-slate-400">File: {r.media_file_name}</p>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {r.channels.map((c) => (
                        <span
                          key={c}
                          className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-700"
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDateTime(r.scheduled_at)}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      title="Click to toggle status"
                      onClick={() => quickToggleStatus(r)}
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium cursor-pointer hover:opacity-75 transition-opacity ${STATUS_STYLE[r.status] ?? "bg-slate-100"}`}
                    >
                      {STATUS_ICON[r.status]}
                      {r.status}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button type="button" onClick={() => openEdit(r)}
                      className="mr-0.5 inline-flex rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" title="Edit">
                      <Pencil size={13} />
                    </button>
                    <button type="button" onClick={() => duplicatePost(r)}
                      className="mr-0.5 inline-flex rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" title="Duplicate">
                      <Copy size={13} />
                    </button>
                    <button type="button"
                      onClick={() => { if (confirm("Delete this post?")) { deleteScheduledPost(r.id); refresh(); } }}
                      className="inline-flex rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500" title="Delete">
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
          <li>OAuth per network under Integrations → token refresh and page/account pickers.</li>
          <li>Bulk designs: batch upload to storage, then attach returned media IDs to each scheduled row.</li>
          <li>Worker: cron or queue consumes scheduled rows and updates status to published/failed.</li>
        </ul>
      </section>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <h2 className="text-lg font-semibold text-slate-900">{modal.id ? "Edit post" : "New scheduled post"}</h2>
              <button type="button" onClick={() => setModal(null)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-3 p-4">
              <div className="rounded-lg border border-brand/15 bg-brand/10 p-3">
                <div className="flex items-center gap-2 text-brand-ink">
                  <Sparkles size={16} className="shrink-0" />
                  <span className="text-xs font-semibold">Draft with AI</span>
                </div>
                <p className="mt-1 text-[11px] text-brand-ink/85">
                  Describe the post (offer, tone, CTA). Selected channels below are sent to the model. Edits the title and caption
                  fields.
                </p>
                <textarea
                  className="mt-2 min-h-[72px] w-full rounded-lg border border-brand/25 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  placeholder="e.g. Announce 20% off weekend brunch, tagline friendly, end with book on WhatsApp"
                  disabled={aiLoading}
                />
                {aiError ? <p className="mt-1 text-xs text-red-600">{aiError}</p> : null}
                <button
                  type="button"
                  disabled={aiLoading || !aiPrompt.trim()}
                  onClick={() => void runAiDraft()}
                  className="mt-2 inline-flex items-center gap-2 rounded-lg bg-brand-dark px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {aiLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles size={14} />}
                  {aiLoading ? "Generating…" : "Generate title & caption"}
                </button>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-700">Title</label>
                <input
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                  value={modal.title ?? ""}
                  onChange={(e) => setModal({ ...modal, title: e.target.value })}
                  placeholder="Spring promo launch"
                />
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">Caption</label>
                  <span className={`text-[10px] font-medium ${
                    (() => {
                      const activeChannels = (modal.channels ?? []) as SocialChannel[];
                      const limit = activeChannels.length
                        ? Math.min(...activeChannels.map((c) => CHAR_LIMITS[c] ?? 9999))
                        : 9999;
                      const len = (modal.body ?? "").length;
                      return len > limit ? "text-red-500" : len > limit * 0.9 ? "text-amber-500" : "text-slate-400";
                    })()
                  }`}>
                    {(modal.body ?? "").length} / {(() => {
                      const activeChannels = (modal.channels ?? []) as SocialChannel[];
                      return activeChannels.length
                        ? Math.min(...activeChannels.map((c) => CHAR_LIMITS[c] ?? 9999))
                        : "∞";
                    })()}
                  </span>
                </div>
                <textarea
                  className="mt-1 min-h-[100px] w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                  value={modal.body ?? ""}
                  onChange={(e) => setModal({ ...modal, body: e.target.value })}
                  placeholder="Write the post… hashtags optional."
                />
                {(modal.channels ?? []).length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-2">
                    {((modal.channels ?? []) as SocialChannel[]).map((ch) => BEST_TIMES[ch] ? (
                      <span key={ch} className="inline-flex items-center gap-1 text-[10px] text-slate-400">
                        <Clock size={9} />
                        <span className="capitalize font-medium text-slate-500">{ch}</span> best: {BEST_TIMES[ch]}
                      </span>
                    ) : null)}
                  </div>
                )}
              </div>
              <div>
                <label className="text-xs font-medium text-slate-700">Channels</label>
                <div className="mt-2 flex flex-wrap gap-2">
                  {CHANNELS.map((c) => {
                    const on = (modal.channels ?? []).includes(c.id);
                    return (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => toggleChannel(c.id)}
                        className={`rounded-full px-3 py-1 text-xs font-medium ${
                          on ? "bg-brand-dark text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                        }`}
                      >
                        {c.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-700">Schedule</label>
                <input
                  type="datetime-local"
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                  value={modal.scheduled_at?.slice(0, 16) ?? ""}
                  onChange={(e) => setModal({ ...modal, scheduled_at: e.target.value })}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-700">Status</label>
                <select
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                  value={modal.status ?? "draft"}
                  onChange={(e) =>
                    setModal({ ...modal, status: e.target.value as ScheduledPost["status"] })
                  }
                >
                  <option value="draft">Draft</option>
                  <option value="scheduled">Scheduled</option>
                  <option value="published">Published (manual)</option>
                  <option value="failed">Failed (manual)</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs font-medium text-slate-700">Post type</label>
                  <select
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                    value={modal.post_kind ?? ""}
                    onChange={(e) =>
                      setModal({
                        ...modal,
                        post_kind: (e.target.value || undefined) as PostKind | undefined,
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
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                    value={modal.link_url ?? ""}
                    onChange={(e) => setModal({ ...modal, link_url: e.target.value })}
                    placeholder="https://"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-700">Placement / target size</label>
                <select
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                  value={modal.placement_id ?? "ig_feed_square"}
                  onChange={(e) =>
                    setModal({ ...modal, placement_id: e.target.value as PostPlacementId })
                  }
                >
                  {PLACEMENT_PRESETS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label} — {p.width}×{p.height}px ({p.aspect})
                    </option>
                  ))}
                </select>
              </div>
              {modal.placement_id === "custom" ? (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs font-medium text-slate-700">Width (px)</label>
                    <input
                      type="number"
                      min={1}
                      className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                      value={modal.placement_width ?? 1080}
                      onChange={(e) =>
                        setModal({ ...modal, placement_width: Number(e.target.value) || 1080 })
                      }
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-700">Height (px)</label>
                    <input
                      type="number"
                      min={1}
                      className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand"
                      value={modal.placement_height ?? 1080}
                      onChange={(e) =>
                        setModal({ ...modal, placement_height: Number(e.target.value) || 1080 })
                      }
                    />
                  </div>
                </div>
              ) : null}
              {(modal.media_preview_data_url || modal.media_file_name || (modal.assets && modal.assets.length > 0)) && (
                <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <div className="flex flex-wrap gap-2">
                    {modal.assets?.length
                      ? modal.assets.map((a, i) => (
                          <div key={i} className="text-[10px] text-slate-600">
                            {a.preview_data_url && a.mime_type.startsWith("image/") ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={a.preview_data_url}
                                alt=""
                                className="mb-0.5 h-16 w-16 rounded border border-slate-200 object-cover"
                              />
                            ) : (
                              <div className="mb-0.5 flex h-16 w-16 items-center justify-center rounded border bg-white text-[9px] font-medium text-slate-500">
                                {a.mime_type.startsWith("video/") ? "VIDEO" : "FILE"}
                              </div>
                            )}
                            <span className="line-clamp-2">{a.file_name}</span>
                          </div>
                        ))
                      : null}
                    {!modal.assets?.length && modal.media_preview_data_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={modal.media_preview_data_url}
                        alt=""
                        className="h-20 w-20 rounded-md border border-slate-200 object-cover"
                      />
                    ) : null}
                  </div>
                  {modal.media_file_name && !modal.assets?.length ? (
                    <p className="text-[11px] text-slate-600">
                      <span className="font-medium">Design file:</span> {modal.media_file_name}
                    </p>
                  ) : null}
                  <p className="text-[10px] text-slate-400">
                    Large videos may store filename only until your upload API runs.
                  </p>
                </div>
              )}
              <div className="flex items-center gap-2 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
                <ImageIcon size={14} />
                Single-post media upload uses the same pipeline as bulk — Graph / container APIs on integration.
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-100 px-4 py-3">
              <button
                type="button"
                onClick={() => setModal(null)}
                className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveModal}
                className="rounded-lg bg-brand-dark px-4 py-2 text-sm font-semibold text-white hover:bg-brand"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

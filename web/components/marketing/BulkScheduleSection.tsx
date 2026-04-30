"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  type ScheduledPostStatus,
  type SocialChannel,
  type PostAsset,
  upsertScheduledPost,
  fileToPreviewDataUrl,
} from "@/lib/marketing-stubs";
import {
  PLACEMENT_PRESETS,
  POST_KIND_LABELS,
  presetById,
  derivePostKind,
  type PostKind,
  type PostPlacementId,
} from "@/lib/social-post-presets";
import { Upload, Trash2, Layers, Clock, Sparkles, Loader2, Plus, Type, Link2, Film } from "lucide-react";

const CHANNELS: { id: SocialChannel; label: string }[] = [
  { id: "facebook", label: "FB" },
  { id: "instagram", label: "IG" },
  { id: "linkedin", label: "LI" },
  { id: "x", label: "X" },
  { id: "tiktok", label: "TT" },
];

const POST_KIND_OPTIONS: { id: PostKind | "auto"; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "text", label: "Text" },
  { id: "image", label: "Image" },
  { id: "video", label: "Video" },
  { id: "carousel", label: "Carousel" },
  { id: "link", label: "Link" },
  { id: "mixed", label: "Mixed" },
];

type DraftAsset = { key: string; file: File; previewUrl: string };

type BulkDraft = {
  key: string;
  assets: DraftAsset[];
  title: string;
  body: string;
  channels: SocialChannel[];
  scheduled_at: string;
  status: ScheduledPostStatus;
  placement_id: PostPlacementId;
  custom_w: number;
  custom_h: number;
  post_kind: PostKind | "auto";
  link_url: string;
};

function stripExtension(name: string) {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(0, i) : name;
}

function defaultDatetimeLocal(): string {
  return new Date(Date.now() + 3600_000).toISOString().slice(0, 16);
}

function newDraft(partial: Partial<BulkDraft> & Pick<BulkDraft, "key">): BulkDraft {
  return {
    assets: [],
    title: "",
    body: "",
    channels: ["facebook", "instagram"],
    scheduled_at: defaultDatetimeLocal(),
    status: "draft",
    placement_id: "ig_feed_square",
    custom_w: 1080,
    custom_h: 1080,
    post_kind: "auto",
    link_url: "https://",
    ...partial,
  };
}

export function BulkScheduleSection({ onCommitted }: { onCommitted: () => void }) {
  const [drafts, setDrafts] = useState<BulkDraft[]>([]);
  const [busy, setBusy] = useState(false);
  const [applyCaption, setApplyCaption] = useState("");
  const [applyChannels, setApplyChannels] = useState<SocialChannel[]>(["facebook", "instagram"]);
  const [applyPlacement, setApplyPlacement] = useState<PostPlacementId>("ig_feed_square");
  const inputRef = useRef<HTMLInputElement>(null);
  const appendTargetRef = useRef<string | null>(null);

  const revokeDraftAssets = useCallback((row: BulkDraft) => {
    row.assets.forEach((a) => URL.revokeObjectURL(a.previewUrl));
  }, []);

  const revokePreviews = useCallback(
    (rows: BulkDraft[]) => {
      rows.forEach(revokeDraftAssets);
    },
    [revokeDraftAssets]
  );

  const draftsRef = useRef(drafts);
  draftsRef.current = drafts;
  useEffect(() => {
    return () => revokePreviews(draftsRef.current);
  }, [revokePreviews]);

  function pushDrafts(next: BulkDraft[]) {
    setDrafts(next);
  }

  function addFilesFromList(fileList: FileList | null, targetRowKey?: string | null) {
    if (!fileList?.length) return;
    const files = Array.from(fileList).filter(
      (f) => f.type.startsWith("image/") || f.type.startsWith("video/")
    );
    if (files.length === 0) return;

    if (targetRowKey) {
      setDrafts((d) =>
        d.map((row) => {
          if (row.key !== targetRowKey) return row;
          const extra: DraftAsset[] = files.map((file, i) => ({
            key: `${row.key}_a_${Date.now()}_${i}`,
            file,
            previewUrl: URL.createObjectURL(file),
          }));
          return { ...row, assets: [...row.assets, ...extra] };
        })
      );
      appendTargetRef.current = null;
      return;
    }

    const nextRows: BulkDraft[] = files.map((file, i) => {
      const key = `${Date.now()}_${i}_${file.name}`;
      return newDraft({
        key,
        title: stripExtension(file.name),
        body: applyCaption,
        channels: [...applyChannels],
        placement_id: applyPlacement,
        assets: [
          {
            key: `${key}_a0`,
            file,
            previewUrl: URL.createObjectURL(file),
          },
        ],
      });
    });
    setDrafts((d) => [...d, ...nextRows]);
  }

  function addTextOnlyRow() {
    const key = `text_${Date.now()}`;
    pushDrafts([
      ...drafts,
      newDraft({
        key,
        title: "Text post",
        body: applyCaption,
        channels: [...applyChannels],
        placement_id: applyPlacement,
        post_kind: "text",
      }),
    ]);
  }

  function addLinkPostRow() {
    const key = `link_${Date.now()}`;
    pushDrafts([
      ...drafts,
      newDraft({
        key,
        title: "Link post",
        body: applyCaption,
        channels: [...applyChannels],
        placement_id: "linkedin_link",
        post_kind: "link",
        link_url: "https://",
      }),
    ]);
  }

  function removeDraft(key: string) {
    setDrafts((d) => {
      const row = d.find((x) => x.key === key);
      if (row) revokeDraftAssets(row);
      return d.filter((x) => x.key !== key);
    });
  }

  function removeAsset(rowKey: string, assetKey: string) {
    setDrafts((d) =>
      d.map((row) => {
        if (row.key !== rowKey) return row;
        const victim = row.assets.find((a) => a.key === assetKey);
        if (victim) URL.revokeObjectURL(victim.previewUrl);
        return { ...row, assets: row.assets.filter((a) => a.key !== assetKey) };
      })
    );
  }

  function updateDraft(key: string, patch: Partial<BulkDraft>) {
    setDrafts((d) => d.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function applyCaptionChannelsPlacementToAll() {
    setDrafts((d) =>
      d.map((row) => ({
        ...row,
        body: applyCaption,
        channels: [...applyChannels],
        placement_id: applyPlacement,
      }))
    );
  }

  function staggerTimesOneHour() {
    setDrafts((d) => {
      if (d.length === 0) return d;
      const base = new Date(d[0].scheduled_at || defaultDatetimeLocal());
      return d.map((row, i) => {
        const t = new Date(base.getTime() + i * 3600_000);
        return { ...row, scheduled_at: t.toISOString().slice(0, 16) };
      });
    });
  }

  async function scheduleAll() {
    const ready = drafts.filter((r) => r.title.trim());
    if (ready.length === 0) {
      alert("Add at least one row with a title (upload media, text-only, or link).");
      return;
    }
    setBusy(true);
    try {
      for (const r of ready) {
        const assetsOut: PostAsset[] = [];
        for (const a of r.assets) {
          const isVid = a.file.type.startsWith("video/");
          const preview = !isVid ? await fileToPreviewDataUrl(a.file) : undefined;
          assetsOut.push({
            file_name: a.file.name,
            mime_type: a.file.type,
            preview_data_url: preview,
          });
        }

        const hasVid = r.assets.some((x) => x.file.type.startsWith("video/"));
        const hasImg = r.assets.some((x) => x.file.type.startsWith("image/"));
        let kind: PostKind =
          r.post_kind === "auto" ? derivePostKind(r.assets.length, hasVid, hasImg) : r.post_kind;
        if (kind === "link" && !r.link_url?.trim()) {
          kind = r.assets.length ? derivePostKind(r.assets.length, hasVid, hasImg) : "text";
        }

        const preset = presetById(r.placement_id);
        const w = r.placement_id === "custom" ? r.custom_w : preset.width;
        const h = r.placement_id === "custom" ? r.custom_h : preset.height;

        upsertScheduledPost({
          title: r.title.trim(),
          body: r.body.trim() || " ",
          channels: r.channels.length ? r.channels : ["facebook"],
          scheduled_at: new Date(r.scheduled_at).toISOString(),
          status: r.status,
          post_kind: kind,
          placement_id: r.placement_id,
          placement_width: w,
          placement_height: h,
          link_url: kind === "link" ? r.link_url.trim() : undefined,
          assets: assetsOut.length ? assetsOut : undefined,
          media_file_name: assetsOut[0]?.file_name,
          media_preview_data_url: assetsOut[0]?.preview_data_url,
        });
      }
      revokePreviews(drafts);
      setDrafts([]);
      onCommitted();
    } finally {
      setBusy(false);
    }
  }

  function toggleDraftChannel(key: string, ch: SocialChannel) {
    const row = drafts.find((d) => d.key === key);
    if (!row) return;
    const set = new Set(row.channels);
    if (set.has(ch)) set.delete(ch);
    else set.add(ch);
    updateDraft(key, { channels: Array.from(set) as SocialChannel[] });
  }

  function openAppendForRow(rowKey: string) {
    appendTargetRef.current = rowKey;
    inputRef.current?.click();
  }

  return (
    <section className="rounded-xl border border-brand/30 bg-gradient-to-b from-brand/10 to-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-2 text-brand-ink">
          <Layers size={18} />
          <h2 className="text-sm font-semibold text-slate-900">Bulk schedule</h2>
        </div>
        <p className="max-w-xl text-[11px] text-slate-500">
          Images &amp; videos (any common format), text-only, and link posts. Pick <strong>placement / size</strong> per
          row — matches feed, story, reel, landscape, and custom pixels.
        </p>
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={addTextOnlyRow}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        >
          <Type size={12} />
          Text-only row
        </button>
        <button
          type="button"
          onClick={addLinkPostRow}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        >
          <Link2 size={12} />
          Link post row
        </button>
      </div>

      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onClick={() => {
          appendTargetRef.current = null;
          inputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDrop={(e) => {
          e.preventDefault();
          addFilesFromList(e.dataTransfer.files, null);
        }}
        className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-brand/30 bg-white/80 px-4 py-8 text-center transition hover:border-brand hover:bg-brand/5"
      >
        <Upload className="mb-2 h-8 w-8 text-brand" />
        <p className="text-sm font-medium text-slate-800">Drop media here or click to browse</p>
        <p className="mt-1 text-[11px] text-slate-500">
          Images (PNG, JPG, WebP, GIF, SVG) &amp; video (MP4, WebM, MOV, …). One row per file — use{" "}
          <strong>Add media</strong> on a row for carousels.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="image/*,video/*"
          multiple
          className="hidden"
          onChange={(e) => {
            addFilesFromList(e.target.files, appendTargetRef.current);
            e.target.value = "";
          }}
        />
      </div>

      <div className="mt-4 grid gap-3 rounded-lg border border-slate-200 bg-slate-50/80 p-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Apply caption to all</label>
          <textarea
            className="mt-1 min-h-[52px] w-full rounded-md border border-slate-200 px-2 py-1.5 text-xs outline-none focus:border-brand"
            placeholder="Base caption for new rows / apply to all"
            value={applyCaption}
            onChange={(e) => setApplyCaption(e.target.value)}
          />
        </div>
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Default placement for new uploads</label>
          <select
            className="mt-1 w-full rounded-md border border-slate-200 px-2 py-1.5 text-[11px] outline-none focus:border-brand"
            value={applyPlacement}
            onChange={(e) => setApplyPlacement(e.target.value as PostPlacementId)}
          >
            {PLACEMENT_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label} · {p.width}×{p.height}px · {p.aspect}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Default channels</label>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {CHANNELS.map((c) => {
              const on = applyChannels.includes(c.id);
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => {
                    setApplyChannels((prev) => {
                      const s = new Set(prev);
                      if (s.has(c.id)) s.delete(c.id);
                      else s.add(c.id);
                      return Array.from(s) as SocialChannel[];
                    });
                  }}
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    on ? "bg-brand-dark text-white" : "bg-slate-200 text-slate-600"
                  }`}
                >
                  {c.label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 lg:col-span-3">
          <button
            type="button"
            onClick={applyCaptionChannelsPlacementToAll}
            disabled={drafts.length === 0}
            className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-[10px] font-semibold text-brand-dark shadow-sm ring-1 ring-slate-200 hover:bg-brand/10 disabled:opacity-40"
          >
            <Sparkles size={11} />
            Apply caption, channels &amp; placement to all
          </button>
          <button
            type="button"
            onClick={staggerTimesOneHour}
            disabled={drafts.length < 2}
            className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-[10px] font-semibold text-slate-700 shadow-sm ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-40"
          >
            <Clock size={11} />
            Stagger +1h each
          </button>
        </div>
      </div>

      {drafts.length > 0 ? (
        <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full min-w-[1100px] text-left text-[11px]">
            <thead className="border-b border-slate-100 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-2 py-2">Media</th>
                <th className="px-2 py-2">Post type</th>
                <th className="min-w-[200px] px-2 py-2">Placement / size</th>
                <th className="px-2 py-2">Title</th>
                <th className="px-2 py-2">Caption</th>
                <th className="px-2 py-2">Link</th>
                <th className="px-2 py-2">Ch</th>
                <th className="px-2 py-2">When</th>
                <th className="px-2 py-2">St</th>
                <th className="w-24 px-2 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {drafts.map((r) => (
                <tr key={r.key} className="align-top">
                  <td className="p-2">
                    <div className="flex flex-col gap-1">
                      <div className="flex flex-wrap gap-1">
                        {r.assets.length === 0 ? (
                          <div className="flex h-14 w-14 items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50 text-slate-400">
                            {r.post_kind === "link" ? <Link2 size={18} /> : <Type size={18} />}
                          </div>
                        ) : (
                          r.assets.map((a) => (
                            <div key={a.key} className="relative">
                              {a.file.type.startsWith("video/") ? (
                                <video
                                  src={a.previewUrl}
                                  className="h-14 w-14 rounded-md border border-slate-200 object-cover"
                                  muted
                                  playsInline
                                />
                              ) : (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img
                                  src={a.previewUrl}
                                  alt=""
                                  className="h-14 w-14 rounded-md border border-slate-200 object-cover"
                                />
                              )}
                              <button
                                type="button"
                                onClick={() => removeAsset(r.key, a.key)}
                                className="absolute -right-1 -top-1 rounded-full bg-red-500 px-0.5 text-[9px] text-white"
                              >
                                ×
                              </button>
                            </div>
                          ))
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => openAppendForRow(r.key)}
                        className="inline-flex items-center gap-0.5 text-[10px] font-medium text-brand-dark hover:underline"
                      >
                        <Plus size={11} /> Add media
                      </button>
                    </div>
                  </td>
                  <td className="p-2">
                    <select
                      className="w-full min-w-[88px] rounded border border-slate-200 px-1 py-1 text-[10px]"
                      value={r.post_kind}
                      onChange={(e) => updateDraft(r.key, { post_kind: e.target.value as PostKind | "auto" })}
                    >
                      {POST_KIND_OPTIONS.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="p-2">
                    <select
                      className="mb-1 w-full rounded border border-slate-200 px-1 py-1 text-[10px]"
                      value={r.placement_id}
                      onChange={(e) => updateDraft(r.key, { placement_id: e.target.value as PostPlacementId })}
                    >
                      {PLACEMENT_PRESETS.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label} ({p.width}×{p.height})
                        </option>
                      ))}
                    </select>
                    {r.placement_id === "custom" ? (
                      <div className="flex gap-1">
                        <input
                          type="number"
                          min={1}
                          className="w-16 rounded border border-slate-200 px-1 text-[10px]"
                          placeholder="W"
                          value={r.custom_w}
                          onChange={(e) => updateDraft(r.key, { custom_w: Number(e.target.value) || 1080 })}
                        />
                        <span className="text-slate-400">×</span>
                        <input
                          type="number"
                          min={1}
                          className="w-16 rounded border border-slate-200 px-1 text-[10px]"
                          placeholder="H"
                          value={r.custom_h}
                          onChange={(e) => updateDraft(r.key, { custom_h: Number(e.target.value) || 1080 })}
                        />
                        <span className="text-[9px] text-slate-400">px</span>
                      </div>
                    ) : (
                      <p className="text-[9px] text-slate-400">
                        {presetById(r.placement_id).aspect} · {presetById(r.placement_id).networks}
                      </p>
                    )}
                  </td>
                  <td className="p-2">
                    <input
                      className="w-full min-w-[80px] rounded border border-slate-200 px-1.5 py-1 text-[11px]"
                      value={r.title}
                      onChange={(e) => updateDraft(r.key, { title: e.target.value })}
                    />
                  </td>
                  <td className="p-2">
                    <textarea
                      className="w-full min-w-[120px] rounded border border-slate-200 px-1.5 py-1 text-[11px] leading-snug"
                      rows={2}
                      value={r.body}
                      onChange={(e) => updateDraft(r.key, { body: e.target.value })}
                      placeholder="Caption"
                    />
                  </td>
                  <td className="p-2">
                    <input
                      className="w-full min-w-[100px] rounded border border-slate-200 px-1 py-1 text-[10px]"
                      value={r.link_url}
                      onChange={(e) => updateDraft(r.key, { link_url: e.target.value })}
                      placeholder="https://…"
                      title="Used when post type is Link (or your API maps URL previews)"
                    />
                  </td>
                  <td className="p-2">
                    <div className="flex flex-wrap gap-0.5">
                      {CHANNELS.map((c) => {
                        const on = r.channels.includes(c.id);
                        return (
                          <button
                            key={c.id}
                            type="button"
                            onClick={() => toggleDraftChannel(r.key, c.id)}
                            className={`rounded px-1 py-0.5 text-[9px] font-medium ${
                              on ? "bg-brand-dark text-white" : "bg-slate-100 text-slate-500"
                            }`}
                          >
                            {c.label}
                          </button>
                        );
                      })}
                    </div>
                  </td>
                  <td className="p-2">
                    <input
                      type="datetime-local"
                      className="w-full min-w-[128px] rounded border border-slate-200 px-1 py-1 text-[10px]"
                      value={r.scheduled_at.slice(0, 16)}
                      onChange={(e) => updateDraft(r.key, { scheduled_at: e.target.value })}
                    />
                  </td>
                  <td className="p-2">
                    <select
                      className="w-full rounded border border-slate-200 px-1 py-1 text-[10px]"
                      value={r.status}
                      onChange={(e) => updateDraft(r.key, { status: e.target.value as ScheduledPostStatus })}
                    >
                      <option value="draft">Draft</option>
                      <option value="scheduled">Scheduled</option>
                    </select>
                  </td>
                  <td className="p-2">
                    <button
                      type="button"
                      onClick={() => removeDraft(r.key)}
                      className="rounded p-1 text-red-500 hover:bg-red-50"
                      title="Remove row"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {drafts.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-[10px] text-slate-500">
            <Film size={12} className="mr-0.5 inline text-slate-400" />
            Long videos won&apos;t store a preview in the browser — filename &amp; MIME are saved for your uploader API.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                if (confirm("Remove all bulk rows?")) {
                  revokePreviews(drafts);
                  setDrafts([]);
                }
              }}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
            >
              Clear bulk
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void scheduleAll()}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-dark px-4 py-2 text-xs font-semibold text-white hover:bg-brand disabled:opacity-50"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : null}
              Add {drafts.length} to queue
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

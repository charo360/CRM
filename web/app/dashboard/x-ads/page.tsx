"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MarketingApiBanner } from "@/components/marketing/MarketingApiBanner";
import { assistantApi, marketingApi, type XAdsCampaignDraft } from "@/lib/api";
import { getCurrency } from "@/lib/auth";
import { formatDateTime } from "@/lib/utils";
import {
  Hash,
  Plus,
  Trash2,
  Pencil,
  Loader2,
  X,
  BarChart3,
  RefreshCw,
  Copy,
  Play,
  Pause,
  TrendingUp,
  DollarSign,
  Layers,
  Sparkles,
  Send,
} from "lucide-react";

const X_OBJECTIVES = [
  { id: "reach", label: "Reach", color: "bg-sky-100 text-sky-800" },
  { id: "engagements", label: "Engagements", color: "bg-blue-100 text-blue-800" },
  { id: "website_clicks", label: "Website clicks", color: "bg-emerald-100 text-emerald-800" },
  { id: "followers", label: "Followers", color: "bg-violet-100 text-violet-800" },
  { id: "app_installs", label: "App installs", color: "bg-orange-100 text-orange-800" },
  { id: "video_views", label: "Video views", color: "bg-rose-100 text-rose-800" },
];

const STATUS_BADGE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  active: "bg-emerald-100 text-emerald-700",
  paused: "bg-amber-100 text-amber-800",
  ended: "bg-slate-200 text-slate-500",
};

const STATUS_FILTERS = ["all", "active", "paused", "draft", "ended"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

type ModalState = {
  id?: string;
  name?: string;
  objective?: string;
  daily_budget?: number;
  currency?: string;
  status?: string;
  targeting?: string;
  strategy?: string;
};

function objMeta(id: string) {
  return X_OBJECTIVES.find((o) => o.id === id) ?? { label: id, color: "bg-slate-100 text-slate-600" };
}

function sourceLabel(source?: string) {
  if (source === "x_ads_agent") return "From Zilo Chat";
  if (source === "x_ads_ui") return "Created here";
  return null;
}

/** Notes JSON: align with assistant `save_x_ads_campaign_draft` (audience / targeting overlap). */
function parseXNotes(notes: string): { targeting: string; strategy: string } {
  try {
    const p = JSON.parse(notes) as Record<string, unknown>;
    const targeting = String(p.targeting ?? p.audience ?? "").trim();
    const strategy = String(p.strategy ?? "").trim();
    return { targeting, strategy };
  } catch {
    return { targeting: (notes || "").trim(), strategy: "" };
  }
}

function buildXNotes(targeting: string, strategy: string): string {
  const t = targeting.trim();
  const s = strategy.trim();
  return JSON.stringify({
    audience: t,
    strategy: s,
    targeting: t,
    start_date: "",
    end_date: "",
    creative_format: "",
    products_advertised: "",
    creative_assets_plan: "",
    ad_preview: "",
  });
}

function SummaryCards({ rows }: { rows: XAdsCampaignDraft[] }) {
  const currency = getCurrency();
  const active = rows.filter((r) => r.status === "active").length;
  const drafts = rows.filter((r) => r.status === "draft").length;
  const totalBudget = rows.filter((r) => r.status === "active").reduce((s, r) => s + r.daily_budget, 0);
  const cards = [
    { label: "Campaigns", value: rows.length, icon: Layers, color: "text-slate-700" },
    { label: "Active", value: active, icon: TrendingUp, color: "text-emerald-500" },
    { label: "Drafts", value: drafts, icon: Pencil, color: "text-slate-400" },
    { label: "Daily budget (active)", value: `${currency} ${totalBudget.toFixed(0)}`, icon: DollarSign, color: "text-sky-600" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className={`mb-1 ${c.color}`}>
            <c.icon size={16} />
          </div>
          <p className="text-xl font-bold text-slate-900">{c.value}</p>
          <p className="mt-0.5 text-[11px] text-slate-500">{c.label}</p>
        </div>
      ))}
    </div>
  );
}

interface AISuggestion {
  name: string;
  objective: string;
  daily_budget: number;
  currency: string;
  targeting: string;
  strategy: string;
}

interface ChatMsg {
  role: "user" | "assistant";
  text: string;
  suggestion?: AISuggestion;
}

const X_AI_PROMPT = `You are an X (Twitter) Ads specialist helping businesses run campaigns on X.

When the user describes their goal, respond with:
1. Short positioning for X (timeline, communities, spaces)
2. Targeting ideas (interests, followers lookalikes, keywords)
3. Creative angle for a promoted post or video

ALWAYS end with a JSON block:
\`\`\`json
{
  "name": "Campaign name",
  "objective": "reach|engagements|website_clicks|followers|app_installs|video_views",
  "daily_budget": <number>,
  "currency": "USD",
  "targeting": "locations, interests, keywords — one line",
  "strategy": "one sentence creative angle"
}
\`\`\``;

function extractSuggestion(reply: string): AISuggestion | null {
  const match = reply.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const p = JSON.parse(match[1].trim());
    if (p.name && p.objective) return p as AISuggestion;
  } catch {
    /* ignore */
  }
  return null;
}

function stripJson(text: string) {
  return text.replace(/```(?:json)?[\s\S]*?```/g, "").trim();
}

function AIBuilderDrawer({ onApply, onClose }: { onApply: (s: AISuggestion) => void; onClose: () => void }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [convId, setConvId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const currency = getCurrency();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);
    const prompt =
      messages.length === 0
        ? `${X_AI_PROMPT}\n\n---\nUser goal: ${text}\n\nDefault currency: ${currency}`
        : text;
    try {
      const res = await assistantApi.chat({
        message: prompt,
        conversation_id: convId,
        agent: "x_ads",
        auto_approve: true,
      });
      setConvId(res.conversation_id);
      const suggestion = extractSuggestion(res.reply);
      const clean = stripJson(res.reply);
      setMessages((prev) => [...prev, { role: "assistant", text: clean, suggestion: suggestion ?? undefined }]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: e instanceof Error ? e.message : "Something went wrong. Try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div className="flex max-h-[min(92vh,640px)] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-sky-600" />
            <h3 className="font-semibold text-slate-900">X Ads — AI Builder</h3>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100">
            <X size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 && (
            <p className="text-xs text-slate-500">
              Describe who you want to reach and what you sell — we&apos;ll suggest an X campaign outline you can
              save as a draft.
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${
                  m.role === "user" ? "bg-slate-900 text-white" : "border border-slate-200 bg-slate-50 text-slate-800"
                }`}
              >
                <p className="whitespace-pre-wrap">{m.text}</p>
                {m.suggestion && (
                  <button
                    type="button"
                    onClick={() => onApply(m.suggestion!)}
                    className="mt-2 w-full rounded-lg bg-sky-600 py-1.5 text-xs font-semibold text-white hover:bg-sky-700"
                  >
                    Use this plan
                  </button>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <p className="flex items-center gap-2 text-xs text-slate-500">
              <Loader2 size={12} className="animate-spin" /> Thinking…
            </p>
          )}
          <div ref={bottomRef} />
        </div>
        <div className="flex gap-2 border-t border-slate-100 p-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), void send())}
            placeholder="e.g. Promote our winter sale to parents in Texas…"
            className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500"
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={loading || !input.trim()}
            className="rounded-lg bg-slate-900 px-3 py-2 text-white hover:bg-slate-800 disabled:opacity-40"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

function CampaignModal({
  modal,
  saving,
  onClose,
  onChange,
  onSave,
}: {
  modal: ModalState;
  saving: boolean;
  onClose: () => void;
  onChange: (m: ModalState) => void;
  onSave: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/45 p-4">
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="font-semibold text-slate-900">{modal.id ? "Edit campaign" : "New X campaign"}</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>
        <div className="space-y-4 p-5">
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Name</label>
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500"
              value={modal.name ?? ""}
              onChange={(e) => onChange({ ...modal, name: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Objective</label>
            <select
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500"
              value={modal.objective ?? "reach"}
              onChange={(e) => onChange({ ...modal, objective: e.target.value })}
            >
              {X_OBJECTIVES.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Daily budget</label>
              <input
                type="number"
                min={0}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={modal.daily_budget ?? 0}
                onChange={(e) => onChange({ ...modal, daily_budget: Number(e.target.value) || 0 })}
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Currency</label>
              <input
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={modal.currency ?? getCurrency()}
                onChange={(e) => onChange({ ...modal, currency: e.target.value })}
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Targeting notes</label>
            <textarea
              rows={3}
              className="mt-1 w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="Geo, interests, keywords, follower lookalikes…"
              value={modal.targeting ?? ""}
              onChange={(e) => onChange({ ...modal, targeting: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Status</label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {(["draft", "active", "paused", "ended"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onChange({ ...modal, status: s })}
                  className={`rounded-full px-3 py-1 text-xs font-medium capitalize ${
                    modal.status === s ? STATUS_BADGE[s] + " ring-1 ring-inset ring-current" : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">
            Cancel
          </button>
          <button
            type="button"
            disabled={saving || !modal.name?.trim()}
            onClick={onSave}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            {modal.id ? "Save" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function XAdsPage() {
  const [rows, setRows] = useState<XAdsCampaignDraft[]>([]);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [aiOpen, setAiOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currency = getCurrency();

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const { drafts } = await marketingApi.listXAdsDrafts();
      setRows(drafts);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function openNew() {
    setModal({
      name: "",
      objective: "reach",
      daily_budget: 50,
      currency,
      status: "draft",
      targeting: "",
      strategy: "",
    });
  }

  function openEdit(r: XAdsCampaignDraft) {
    const p = parseXNotes(r.notes ?? "{}");
    setModal({
      id: r.id,
      name: r.name,
      objective: r.objective,
      daily_budget: r.daily_budget,
      currency: r.currency,
      status: r.status,
      targeting: p.targeting,
      strategy: p.strategy,
    });
  }

  async function handleDuplicate(r: XAdsCampaignDraft) {
    setSaving(true);
    setError(null);
    try {
      await marketingApi.createXAdsDraft({
        name: `${r.name} (copy)`,
        objective: r.objective,
        daily_budget: r.daily_budget,
        currency: r.currency,
        notes: r.notes,
        status: "draft",
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Duplicate failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleStatus(r: XAdsCampaignDraft) {
    const next = r.status === "active" ? "paused" : "active";
    try {
      await marketingApi.updateXAdsDraft(r.id, { status: next });
      setRows((prev) => prev.map((x) => (x.id === r.id ? { ...x, status: next } : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Status update failed");
    }
  }

  async function save() {
    if (!modal?.name?.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const notes = buildXNotes(modal.targeting ?? "", modal.strategy ?? "");
      const payload = {
        name: modal.name.trim(),
        objective: modal.objective ?? "reach",
        daily_budget: Number(modal.daily_budget) || 0,
        currency: modal.currency ?? currency,
        notes,
        status: modal.status ?? "draft",
      };
      if (modal.id) {
        await marketingApi.updateXAdsDraft(modal.id, payload);
      } else {
        await marketingApi.createXAdsDraft(payload);
      }
      await refresh();
      setModal(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this campaign draft?")) return;
    setError(null);
    try {
      await marketingApi.deleteXAdsDraft(id);
      setRows((prev) => prev.filter((r) => r.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  function applyAI(s: AISuggestion) {
    setModal({
      name: s.name,
      objective: s.objective,
      daily_budget: s.daily_budget,
      currency: s.currency || currency,
      status: "draft",
      targeting: s.targeting,
      strategy: s.strategy,
    });
    setAiOpen(false);
  }

  const filtered = statusFilter === "all" ? rows : rows.filter((r) => r.status === statusFilter);

  if (loading) {
    return (
      <div className="flex justify-center py-24 text-slate-400">
        <Loader2 className="animate-spin" size={24} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-4 pb-16 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-sky-700">
            <Hash size={18} />
            <span className="text-[11px] font-semibold uppercase tracking-wide">Marketing</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">X Ads</h1>
          <p className="mt-1 text-sm text-slate-500">
            Plan promoted posts and campaigns for X (Twitter). Drafts are saved to your workspace — including plans from
            the <strong className="font-medium text-slate-700">X Ads</strong> agent in Zilo Chat.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            type="button"
            onClick={() => setAiOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-sky-300 bg-sky-50 px-4 py-2 text-sm font-semibold text-sky-800 hover:bg-sky-100"
          >
            <Sparkles size={14} /> AI Builder
          </button>
          <button
            type="button"
            onClick={openNew}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
          >
            <Plus size={15} /> New campaign
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <MarketingApiBanner product="X Ads" />

      {rows.length > 0 && <SummaryCards rows={rows} />}

      <div className="flex flex-wrap gap-1.5">
        {STATUS_FILTERS.map((f) => {
          const count = f === "all" ? rows.length : rows.filter((r) => r.status === f).length;
          return (
            <button
              key={f}
              type="button"
              onClick={() => setStatusFilter(f)}
              className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                statusFilter === f ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {f} {count > 0 && <span className="opacity-70">({count})</span>}
            </button>
          );
        })}
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 py-16 text-center">
          <Hash size={32} className="mx-auto mb-3 text-slate-300" />
          <p className="text-sm font-medium text-slate-500">No X campaigns yet</p>
          <p className="mt-1 text-xs text-slate-400">Create one or open the AI Builder</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50/80 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">Campaign</th>
                  <th className="px-4 py-3">Objective</th>
                  <th className="px-4 py-3">Budget / day</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((r) => {
                  const canToggle = r.status === "active" || r.status === "paused";
                  const line = parseXNotes(r.notes ?? "{}").targeting;
                  return (
                    <tr key={r.id} className="hover:bg-slate-50/60">
                      <td className="max-w-[220px] px-4 py-3">
                        <p className="truncate font-medium text-slate-900">{r.name}</p>
                        <p className="mt-0.5 text-[11px] text-slate-400">
                          {r.created_at ? formatDateTime(r.created_at) : "—"}
                          {sourceLabel(r.source) ? ` · ${sourceLabel(r.source)}` : ""}
                        </p>
                        {line ? <p className="mt-0.5 truncate text-[10px] text-slate-500">{line}</p> : null}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${objMeta(r.objective).color}`}>
                          {objMeta(r.objective).label}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-700">
                        {r.currency} {r.daily_budget.toFixed(0)}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          disabled={!canToggle}
                          onClick={() => void handleToggleStatus(r)}
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${STATUS_BADGE[r.status] ?? ""} ${
                            canToggle ? "cursor-pointer hover:opacity-80" : "cursor-default"
                          }`}
                        >
                          {r.status === "active" && <Pause size={9} />}
                          {r.status === "paused" && <Play size={9} />}
                          {r.status}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => openEdit(r)}
                            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDuplicate(r)}
                            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                          >
                            <Copy size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDelete(r.id)}
                            className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <section className="space-y-1 rounded-xl border border-slate-200 bg-slate-50/50 p-4 text-xs text-slate-600">
        <p className="mb-2 font-semibold text-slate-800">Next steps</p>
        <p>• Wire X Ads API (OAuth 2.0) and map ad accounts to your workspace.</p>
        <p>• Sync spend, impressions, and engagements for reporting.</p>
        <p>
          • Open{" "}
          <a href="/dashboard/assistant" className="font-medium text-[#009B3A] hover:underline">
            Zilo Chat
          </a>{" "}
          with the <strong>X Ads</strong> specialist for creative angles, targeting, and saving drafts.
        </p>
      </section>

      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        <div className="flex items-start gap-3">
          <BarChart3 className="mt-0.5 h-5 w-5 shrink-0 text-slate-400" />
          <div>
            <p className="font-medium text-slate-800">Reporting</p>
            <p className="mt-1 text-xs text-slate-500">
              Aggregate performance charts will appear here once the X Ads reporting API is connected.
            </p>
          </div>
        </div>
      </div>

      {modal && (
        <CampaignModal modal={modal} saving={saving} onClose={() => setModal(null)} onChange={setModal} onSave={() => void save()} />
      )}
      {aiOpen && <AIBuilderDrawer onApply={applyAI} onClose={() => setAiOpen(false)} />}
    </div>
  );
}

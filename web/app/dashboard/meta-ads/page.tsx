"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MarketingApiBanner } from "@/components/marketing/MarketingApiBanner";
import { marketingApi, assistantApi, zernioAdsApi, adHealthApi, type MetaAdsCampaignDraft, type ZernioAdsInsights, type ZernioCampaignMetrics, type AdHealthCampaign, type AdAlertRule, type AdAlertHistoryEntry } from "@/lib/api";
import { getCurrency } from "@/lib/auth";
import { formatDateTime } from "@/lib/utils";
import {
  Target,
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
  Users,
  DollarSign,
  Layers,
  Sparkles,
  Send,
  ChevronRight,
  Wand2,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Bell,
  BellOff,
  Settings,
  Clock,
  Zap,
} from "lucide-react";

// ── Constants ──────────────────────────────────────────────────────────────────

const OBJECTIVES = [
  { id: "awareness", label: "Brand awareness", color: "bg-brand/15 text-brand-dark" },
  { id: "traffic", label: "Traffic", color: "bg-blue-100 text-blue-700" },
  { id: "leads", label: "Leads", color: "bg-emerald-100 text-emerald-700" },
  { id: "sales", label: "Sales / conversions", color: "bg-orange-100 text-orange-700" },
  { id: "engagement", label: "Engagement", color: "bg-pink-100 text-pink-700" },
  { id: "video_views", label: "Video views", color: "bg-red-100 text-red-700" },
];

const STATUS_BADGE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  active: "bg-emerald-100 text-emerald-700",
  paused: "bg-amber-100 text-amber-800",
  ended: "bg-slate-200 text-slate-500",
};

const STATUS_FILTERS = ["all", "active", "paused", "draft", "ended"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

type ModalState = Partial<MetaAdsCampaignDraft> & {
  id?: string;
  start_date?: string;
  end_date?: string;
  audience?: string;
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function objectiveMeta(id: string) {
  return OBJECTIVES.find((o) => o.id === id) ?? { label: id, color: "bg-slate-100 text-slate-600" };
}

function sourceLabel(source?: string) {
  if (source === "meta_ads_agent") return "From Zilo Chat";
  if (source === "meta_ads_ui") return "Created here";
  return null;
}

function metaNotesToParts(notes: string) {
  try {
    const parsed = JSON.parse(notes);
    return {
      audience: parsed.audience ?? "",
      strategy: parsed.strategy ?? "",
      start_date: parsed.start_date ?? "",
      end_date: parsed.end_date ?? "",
      creative_format: parsed.creative_format ?? "",
      products_advertised: parsed.products_advertised ?? "",
      creative_assets_plan: parsed.creative_assets_plan ?? "",
      ad_preview: parsed.ad_preview ?? "",
    };
  } catch {
    return {
      audience: "",
      strategy: notes,
      start_date: "",
      end_date: "",
      creative_format: "",
      products_advertised: "",
      creative_assets_plan: "",
      ad_preview: "",
    };
  }
}

function partsToMetaNotes(parts: {
  audience?: string;
  strategy?: string;
  start_date?: string;
  end_date?: string;
  creative_format?: string;
  products_advertised?: string;
  creative_assets_plan?: string;
  ad_preview?: string;
}) {
  return JSON.stringify({
    audience: parts.audience ?? "",
    strategy: parts.strategy ?? "",
    start_date: parts.start_date ?? "",
    end_date: parts.end_date ?? "",
    creative_format: parts.creative_format ?? "",
    products_advertised: parts.products_advertised ?? "",
    creative_assets_plan: parts.creative_assets_plan ?? "",
    ad_preview: parts.ad_preview ?? "",
  });
}

// ── Summary cards ──────────────────────────────────────────────────────────────

function SummaryCards({ rows }: { rows: MetaAdsCampaignDraft[] }) {
  const active = rows.filter((r) => r.status === "active").length;
  const drafts = rows.filter((r) => r.status === "draft").length;
  const totalBudget = rows.filter((r) => r.status === "active").reduce((s, r) => s + r.daily_budget, 0);
  const currency = rows[0]?.currency ?? getCurrency();

  const cards = [
    { label: "Total campaigns", value: rows.length, icon: Layers, color: "text-brand" },
    { label: "Active", value: active, icon: TrendingUp, color: "text-emerald-500" },
    { label: "Drafts", value: drafts, icon: Pencil, color: "text-slate-400" },
    { label: "Daily budget (active)", value: `${currency} ${totalBudget.toFixed(2)}`, icon: DollarSign, color: "text-blue-500" },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
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

// ── AI Campaign Builder ────────────────────────────────────────────────────────

interface AICampaignSuggestion {
  name: string;
  objective: string;
  daily_budget: number;
  currency: string;
  audience: string;
  strategy: string;
  start_date: string;
  end_date: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  suggestion?: AICampaignSuggestion;
}

function extractSuggestion(reply: string): AICampaignSuggestion | null {
  const match = reply.match(/```(?:json|campaign-json)?\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const parsed = JSON.parse(match[1].trim());
    if (parsed.name && parsed.objective) return parsed as AICampaignSuggestion;
  } catch {
    // not valid JSON
  }
  return null;
}

function stripJsonBlock(text: string) {
  return text.replace(/```(?:json|campaign-json)?[\s\S]*?```/g, "").trim();
}

const AI_SYSTEM_PROMPT = `You are a Meta Ads strategist helping create high-converting Facebook and Instagram campaigns.

When the user describes their business or campaign goal, you will:
1. Give 2-3 sentences of sharp strategy advice
2. Recommend the best audience demographics (location, age range, interests)
3. Explain WHY this audience wins for their goal

ALWAYS end your reply with a JSON block in this exact format (no extra text after it):
\`\`\`json
{
  "name": "descriptive campaign name",
  "objective": "awareness|traffic|leads|sales|engagement|video_views",
  "daily_budget": <number in local currency>,
  "currency": "KES",
  "audience": "specific demographics, age range, interests, location",
  "strategy": "one sentence on the winning creative/angle",
  "start_date": "",
  "end_date": ""
}
\`\`\``;

function AICampaignBuilderDrawer({
  onApply,
  onClose,
  currency,
}: {
  onApply: (s: AICampaignSuggestion) => void;
  onClose: () => void;
  currency: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [convId, setConvId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);

    const prompt = messages.length === 0
      ? `${AI_SYSTEM_PROMPT}\n\n---\nUser goal: ${text}\n\nDefault currency: ${currency}`
      : text;

    try {
      const res = await assistantApi.chat({
        message: prompt,
        conversation_id: convId,
        agent: "meta_ads",
        auto_approve: true,
      });
      setConvId(res.conversation_id);
      const suggestion = extractSuggestion(res.reply);
      const clean = stripJsonBlock(res.reply);
      setMessages((prev) => [...prev, { role: "assistant", text: clean, suggestion: suggestion ?? undefined }]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: e instanceof Error ? e.message : "Failed to get a response. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/30" onClick={onClose} />

      {/* Drawer */}
      <div className="flex flex-col w-full max-w-md bg-white shadow-2xl h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-[#1877F2]/5 to-transparent">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-[#1877F2] flex items-center justify-center">
              <Sparkles size={13} className="text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800">AI Campaign Builder</p>
              <p className="text-[11px] text-slate-500">Describe your goal — AI fills everything</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:bg-slate-100">
            <X size={18} />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="space-y-3 text-center pt-6">
              <div className="w-12 h-12 rounded-2xl bg-[#1877F2]/10 flex items-center justify-center mx-auto">
                <Wand2 size={22} className="text-[#1877F2]" />
              </div>
              <p className="text-sm font-medium text-slate-700">Tell me about your campaign</p>
              <p className="text-xs text-slate-400 leading-relaxed">
                Describe your business, goal, and target customers. I&apos;ll suggest the best audience, budget, and strategy — then fill the form for you.
              </p>
              <div className="space-y-2 text-left mt-4">
                {[
                  "I run a restaurant in Nairobi and want more table bookings from young professionals",
                  "Promote my online clothing store to women aged 18-35 interested in fashion",
                  "Get leads for my real estate project targeting high-income buyers in Kenya",
                ].map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    onClick={() => setInput(ex)}
                    className="w-full text-left rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:border-[#1877F2]/40 hover:bg-[#1877F2]/5 transition-colors"
                  >
                    <ChevronRight size={11} className="inline mr-1 text-slate-400" />
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] space-y-2`}>
                <div
                  className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-[#1877F2] text-white rounded-br-sm"
                      : "bg-slate-100 text-slate-800 rounded-bl-sm"
                  }`}
                >
                  {m.text}
                </div>

                {m.suggestion && (
                  <div className="bg-white border border-[#1877F2]/20 rounded-xl p-3 space-y-2 shadow-sm">
                    <div className="flex items-center gap-1.5 text-[#1877F2]">
                      <Sparkles size={12} />
                      <span className="text-[11px] font-semibold uppercase tracking-wide">Campaign ready</span>
                    </div>
                    <div className="space-y-1.5 text-xs text-slate-700">
                      <p><span className="text-slate-400">Name</span> · {m.suggestion.name}</p>
                      <p><span className="text-slate-400">Objective</span> · {m.suggestion.objective}</p>
                      <p><span className="text-slate-400">Budget</span> · {m.suggestion.currency} {m.suggestion.daily_budget}/day</p>
                      <p><span className="text-slate-400">Audience</span> · {m.suggestion.audience}</p>
                      {m.suggestion.strategy && (
                        <p><span className="text-slate-400">Strategy</span> · {m.suggestion.strategy}</p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => onApply(m.suggestion!)}
                      className="w-full mt-1 rounded-lg bg-[#1877F2] py-2 text-xs font-semibold text-white hover:bg-[#166fe5] transition-colors"
                    >
                      Fill campaign form with this →
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-slate-100 rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-2 text-sm text-slate-500">
                <Loader2 size={13} className="animate-spin" />
                Analysing your goal…
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-100 px-4 py-3">
          <div className="flex items-end gap-2">
            <textarea
              rows={2}
              className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm resize-none outline-none focus:border-[#1877F2] focus:ring-1 focus:ring-[#1877F2]/30"
              placeholder="Describe your business and campaign goal…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <button
              type="button"
              disabled={!input.trim() || loading}
              onClick={() => void send()}
              className="rounded-xl bg-[#1877F2] p-2.5 text-white hover:bg-[#166fe5] disabled:opacity-40 transition-colors"
            >
              <Send size={16} />
            </button>
          </div>
          <p className="text-[10px] text-slate-400 mt-1.5 text-center">Press Enter to send · Shift+Enter for new line</p>
        </div>
      </div>
    </div>
  );
}

// ── Campaign modal ─────────────────────────────────────────────────────────────

function CampaignModal({
  modal,
  saving,
  error,
  onClose,
  onChange,
  onSave,
}: {
  modal: ModalState;
  saving: boolean;
  error: string | null;
  onClose: () => void;
  onChange: (m: ModalState) => void;
  onSave: () => void;
}) {
  const parts = metaNotesToParts(modal.notes ?? "{}");

  function setPart(key: string, value: string) {
    const updated = { ...parts, [key]: value };
    onChange({ ...modal, notes: partsToMetaNotes(updated) });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-800">
            {modal.id ? "Edit campaign" : "New campaign"}
          </h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{error}</div>
          )}

          {/* Name */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Campaign name *</label>
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2] focus:ring-1 focus:ring-[#1877F2]/30"
              placeholder="e.g. Ramadan Sales Push"
              value={modal.name ?? ""}
              onChange={(e) => onChange({ ...modal, name: e.target.value })}
            />
          </div>

          {/* Objective */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Objective</label>
            <div className="mt-1.5 grid grid-cols-2 gap-1.5">
              {OBJECTIVES.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => onChange({ ...modal, objective: o.id })}
                  className={`rounded-lg border px-3 py-2 text-xs font-medium text-left transition-colors ${
                    modal.objective === o.id
                      ? "border-[#1877F2] bg-[#1877F2]/5 text-[#1877F2]"
                      : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          {/* Budget + Currency */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Daily budget</label>
              <input
                type="number"
                min={0}
                step={1}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2] focus:ring-1 focus:ring-[#1877F2]/30"
                value={modal.daily_budget ?? ""}
                onChange={(e) => onChange({ ...modal, daily_budget: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Currency</label>
              <select
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2]"
                value={modal.currency ?? "KES"}
                onChange={(e) => onChange({ ...modal, currency: e.target.value })}
              >
                <option>KES</option>
                <option>USD</option>
                <option>EUR</option>
                <option>GBP</option>
                <option>ZAR</option>
                <option>NGN</option>
              </select>
            </div>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Start date</label>
              <input
                type="date"
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2]"
                value={parts.start_date}
                onChange={(e) => setPart("start_date", e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">End date</label>
              <input
                type="date"
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2]"
                value={parts.end_date}
                onChange={(e) => setPart("end_date", e.target.value)}
              />
            </div>
          </div>

          {/* Audience */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Target audience</label>
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2] focus:ring-1 focus:ring-[#1877F2]/30"
              placeholder="e.g. Kenya, ages 25-45, interested in food & restaurants"
              value={parts.audience}
              onChange={(e) => setPart("audience", e.target.value)}
            />
          </div>

          {/* Strategy notes */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Strategy / notes</label>
            <textarea
              rows={3}
              className="mt-1 w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2] focus:ring-1 focus:ring-[#1877F2]/30"
              placeholder="Creative angles, targeting notes, or ideas from Zilo Chat…"
              value={parts.strategy}
              onChange={(e) => setPart("strategy", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Creative format</label>
              <input
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2]"
                placeholder="e.g. image, video, carousel"
                value={parts.creative_format}
                onChange={(e) => setPart("creative_format", e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Products in ad</label>
              <input
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2]"
                placeholder="Which SKUs or offers this push focuses on"
                value={parts.products_advertised}
                onChange={(e) => setPart("products_advertised", e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Creative assets</label>
            <input
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2]"
              placeholder="e.g. owner_will_upload · zilo_generated_copy_only"
              value={parts.creative_assets_plan}
              onChange={(e) => setPart("creative_assets_plan", e.target.value)}
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Ad copy preview (from Zilo Chat)</label>
            <textarea
              rows={5}
              className="mt-1 w-full resize-y rounded-lg border border-slate-200 px-3 py-2 font-mono text-[12px] leading-relaxed outline-none focus:border-[#1877F2] focus:ring-1 focus:ring-[#1877F2]/30"
              placeholder="Headlines, primary text, CTA — Markdown ok"
              value={parts.ad_preview}
              onChange={(e) => setPart("ad_preview", e.target.value)}
            />
          </div>

          {/* Status */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Status</label>
            <div className="mt-1.5 flex gap-1.5">
              {["draft", "active", "paused", "ended"].map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onChange({ ...modal, status: s })}
                  className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                    modal.status === s
                      ? STATUS_BADGE[s] + " ring-1 ring-inset ring-current"
                      : "bg-slate-100 text-slate-500 hover:bg-slate-200"
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
            className="inline-flex items-center gap-2 rounded-lg bg-[#1877F2] px-4 py-2 text-sm font-semibold text-white hover:bg-[#166fe5] disabled:opacity-50"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            {saving ? "Saving…" : modal.id ? "Save changes" : "Create campaign"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Campaigns table ────────────────────────────────────────────────────────────

function CampaignsTable({
  rows,
  onEdit,
  onDuplicate,
  onDelete,
  onToggleStatus,
}: {
  rows: MetaAdsCampaignDraft[];
  onEdit: (r: MetaAdsCampaignDraft) => void;
  onDuplicate: (r: MetaAdsCampaignDraft) => void;
  onDelete: (id: string) => void;
  onToggleStatus: (r: MetaAdsCampaignDraft) => void;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 py-16 text-center">
        <Target size={32} className="mx-auto mb-3 text-slate-300" />
        <p className="text-sm font-medium text-slate-500">No campaigns here</p>
        <p className="text-xs text-slate-400 mt-1">Create one above or ask the Meta Ads agent in Zilo Chat</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px] text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50/80 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Campaign</th>
              <th className="px-4 py-3">Objective</th>
              <th className="px-4 py-3">Audience</th>
              <th className="px-4 py-3">Daily budget</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => {
              const obj = objectiveMeta(r.objective ?? "");
              const parts = metaNotesToParts(r.notes ?? "{}");
              const canToggle = r.status === "active" || r.status === "paused";
              return (
                <tr key={r.id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="px-4 py-3 max-w-[200px]">
                    <p className="font-medium text-slate-900 truncate">{r.name}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      {r.created_at ? formatDateTime(r.created_at) : "—"}
                      {sourceLabel(r.source) ? ` · ${sourceLabel(r.source)}` : ""}
                    </p>
                    {parts.start_date && (
                      <p className="text-[11px] text-slate-400">
                        {parts.start_date}{parts.end_date ? ` → ${parts.end_date}` : ""}
                      </p>
                    )}
                    {(parts.products_advertised || parts.creative_format) && (
                      <p className="text-[11px] text-slate-400 line-clamp-2">
                        {parts.creative_format ? `${parts.creative_format}` : ""}
                        {parts.creative_format && parts.products_advertised ? " · " : ""}
                        {parts.products_advertised || ""}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${obj.color}`}>
                      {obj.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 max-w-[160px]">
                    {parts.audience ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-600">
                        <Users size={10} className="shrink-0" />
                        <span className="truncate">{parts.audience}</span>
                      </span>
                    ) : (
                      <span className="text-[11px] text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-700">
                    {r.currency} {r.daily_budget.toFixed(2)}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={!canToggle}
                      onClick={() => onToggleStatus(r)}
                      title={canToggle ? (r.status === "active" ? "Pause" : "Activate") : undefined}
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${
                        STATUS_BADGE[r.status] ?? ""
                      } ${canToggle ? "cursor-pointer hover:opacity-80" : "cursor-default"}`}
                    >
                      {r.status === "active" && <Pause size={9} />}
                      {r.status === "paused" && <Play size={9} />}
                      <span className="capitalize">{r.status}</span>
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => onEdit(r)}
                        title="Edit"
                        className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        type="button"
                        onClick={() => onDuplicate(r)}
                        title="Duplicate"
                        className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      >
                        <Copy size={13} />
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(r.id)}
                        title="Delete"
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
  );
}

// ── Health tab ────────────────────────────────────────────────────────────────

const ZONE_META = {
  healthy:           { label: "Healthy",          color: "bg-emerald-100 text-emerald-700", icon: CheckCircle2,  bar: "bg-emerald-500" },
  warning:           { label: "Warning",          color: "bg-amber-100 text-amber-800",    icon: AlertTriangle, bar: "bg-amber-400"   },
  critical:          { label: "Critical",         color: "bg-red-100 text-red-700",        icon: XCircle,       bar: "bg-red-500"     },
  insufficient_data: { label: "Insufficient data", color: "bg-slate-100 text-slate-500",   icon: Clock,         bar: "bg-slate-300"   },
};

const CONDITION_LABELS: Record<string, string> = {
  health_score: "Health score", ctr: "CTR (%)", roas: "ROAS (×)",
  cpc: "CPC ($)", cpm: "CPM ($)", spend: "Spend ($)", clicks: "Clicks",
};
const OPERATOR_LABELS: Record<string, string> = { lt: "below", gt: "above", lte: "≤", gte: "≥" };

function HealthScoreBar({ score, zone }: { score: number; zone: string }) {
  const meta = ZONE_META[zone as keyof typeof ZONE_META] ?? ZONE_META.insufficient_data;
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${meta.bar}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs font-semibold text-slate-700 tabular-nums w-7 text-right">{score}</span>
    </div>
  );
}

function RuleFormModal({
  initial,
  onSave,
  onClose,
}: {
  initial?: Partial<AdAlertRule>;
  onSave: (data: Omit<AdAlertRule, "id" | "is_default" | "created_at">) => Promise<void>;
  onClose: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: initial?.name ?? "",
    condition: initial?.condition ?? "health_score",
    operator: initial?.operator ?? "lt",
    value: String(initial?.value ?? 40),
    action: initial?.action ?? "auto_pause",
    min_spend: String(initial?.min_spend ?? 5),
    min_impressions: String(initial?.min_impressions ?? 300),
    notify_whatsapp: initial?.notify_whatsapp ?? true,
    enabled: initial?.enabled ?? true,
  });

  async function submit() {
    if (!form.name.trim()) { setErr("Name is required"); return; }
    setSaving(true); setErr(null);
    try {
      await onSave({
        name: form.name.trim(),
        condition: form.condition,
        operator: form.operator,
        value: parseFloat(form.value) || 0,
        action: form.action as "auto_pause" | "alert_only",
        min_spend: parseFloat(form.min_spend) || 0,
        min_impressions: parseInt(form.min_impressions) || 0,
        notify_whatsapp: form.notify_whatsapp,
        enabled: form.enabled,
      });
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const sel = "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2]";
  const inp = "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-[#1877F2] focus:ring-1 focus:ring-[#1877F2]/30";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-800">{initial?.id ? "Edit rule" : "New alert rule"}</h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"><X size={18} /></button>
        </div>
        <div className="space-y-4 p-5">
          {err && <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{err}</div>}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Rule name *</label>
            <input className={`mt-1 ${inp}`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Pause if ROAS below 1.5" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Metric</label>
              <select className={`mt-1 ${sel}`} value={form.condition} onChange={e => setForm(f => ({ ...f, condition: e.target.value }))}>
                {Object.entries(CONDITION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Is</label>
              <select className={`mt-1 ${sel}`} value={form.operator} onChange={e => setForm(f => ({ ...f, operator: e.target.value }))}>
                <option value="lt">Below</option>
                <option value="lte">≤</option>
                <option value="gt">Above</option>
                <option value="gte">≥</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Value</label>
              <input type="number" step="any" className={`mt-1 ${inp}`} value={form.value} onChange={e => setForm(f => ({ ...f, value: e.target.value }))} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Min spend ($)</label>
              <input type="number" min={0} className={`mt-1 ${inp}`} value={form.min_spend} onChange={e => setForm(f => ({ ...f, min_spend: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Min impressions</label>
              <input type="number" min={0} className={`mt-1 ${inp}`} value={form.min_impressions} onChange={e => setForm(f => ({ ...f, min_impressions: e.target.value }))} />
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Action</label>
            <div className="mt-1.5 grid grid-cols-2 gap-2">
              {[
                { v: "auto_pause", label: "Auto-pause campaign", icon: Pause, color: "border-red-300 bg-red-50 text-red-700" },
                { v: "alert_only", label: "Alert only (WhatsApp)", icon: Bell, color: "border-amber-300 bg-amber-50 text-amber-800" },
              ].map(o => (
                <button key={o.v} type="button" onClick={() => setForm(f => ({ ...f, action: o.v as "auto_pause" | "alert_only" }))}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${form.action === o.v ? o.color + " ring-1 ring-inset ring-current" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
                  <o.icon size={12} />{o.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">WhatsApp alert</label>
            <button type="button" onClick={() => setForm(f => ({ ...f, notify_whatsapp: !f.notify_whatsapp }))}
              className={`relative w-10 h-5 rounded-full transition-colors ${form.notify_whatsapp ? "bg-brand" : "bg-slate-200"}`}>
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${form.notify_whatsapp ? "translate-x-5" : ""}`} />
            </button>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">Cancel</button>
          <button type="button" disabled={saving || !form.name.trim()} onClick={() => void submit()}
            className="inline-flex items-center gap-2 rounded-lg bg-[#1877F2] px-4 py-2 text-sm font-semibold text-white hover:bg-[#166fe5] disabled:opacity-50">
            {saving && <Loader2 size={13} className="animate-spin" />}
            {saving ? "Saving…" : initial?.id ? "Update rule" : "Create rule"}
          </button>
        </div>
      </div>
    </div>
  );
}

function HealthTab() {
  const [report, setReport] = useState<{ campaigns: AdHealthCampaign[]; summary: { critical: number; warning: number; healthy: number; total: number }; error?: string | null } | null>(null);
  const [rules, setRules] = useState<AdAlertRule[]>([]);
  const [history, setHistory] = useState<AdAlertHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const [section, setSection] = useState<"overview" | "rules" | "history">("overview");
  const [ruleModal, setRuleModal] = useState<Partial<AdAlertRule> | null>(null);
  const [deletingRule, setDeletingRule] = useState<string | null>(null);
  const [togglingRule, setTogglingRule] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const [rep, rul, hist] = await Promise.all([
        adHealthApi.report(days),
        adHealthApi.listRules(),
        adHealthApi.history(30),
      ]);
      setReport(rep);
      setRules(rul.rules);
      setHistory(hist.history);
      if (rep.error) setErr(rep.error);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { void load(); }, [load]);

  async function saveRule(data: Omit<AdAlertRule, "id" | "is_default" | "created_at">) {
    if (ruleModal?.id) {
      await adHealthApi.updateRule(ruleModal.id, data);
    } else {
      await adHealthApi.createRule(data);
    }
    const { rules: r } = await adHealthApi.listRules();
    setRules(r);
  }

  async function deleteRule(id: string) {
    if (!confirm("Delete this alert rule?")) return;
    setDeletingRule(id);
    try {
      await adHealthApi.deleteRule(id);
      setRules(r => r.filter(x => x.id !== id));
    } finally {
      setDeletingRule(null);
    }
  }

  async function toggleRule(rule: AdAlertRule) {
    setTogglingRule(rule.id);
    try {
      const { rule: updated } = await adHealthApi.updateRule(rule.id, { enabled: !rule.enabled });
      setRules(r => r.map(x => x.id === rule.id ? updated : x));
    } finally {
      setTogglingRule(null);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm animate-pulse">
              <div className="h-2 w-16 rounded bg-slate-200 mb-3" />
              <div className="h-7 w-10 rounded bg-slate-200" />
            </div>
          ))}
        </div>
        <div className="flex justify-center py-8 text-slate-400"><Loader2 className="animate-spin" size={22} /></div>
      </div>
    );
  }

  const summary = report?.summary ?? { critical: 0, warning: 0, healthy: 0, total: 0 };

  return (
    <div className="space-y-5">
      {/* Summary cards */}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
        {[
          { label: "Total campaigns", value: summary.total, icon: Layers,       color: "text-slate-600" },
          { label: "Critical 🔴",     value: summary.critical, icon: XCircle,       color: "text-red-500"     },
          { label: "Warning 🟡",      value: summary.warning,  icon: AlertTriangle, color: "text-amber-500"   },
          { label: "Healthy 🟢",      value: summary.healthy,  icon: CheckCircle2,  color: "text-emerald-500" },
        ].map(c => (
          <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className={`mb-1 ${c.color}`}><c.icon size={15} /></div>
            <p className="text-2xl font-bold text-slate-900">{c.value}</p>
            <p className="text-[11px] text-slate-500 mt-0.5">{c.label}</p>
          </div>
        ))}
      </div>

      {err && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">{err}</div>
      )}

      {/* Sub-tabs */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 text-xs">
          {(["overview", "rules", "history"] as const).map(s => (
            <button key={s} type="button" onClick={() => setSection(s)}
              className={`rounded-md px-3 py-1.5 font-medium capitalize transition-colors ${section === s ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
              {s === "rules" ? `Rules (${rules.length})` : s === "history" ? `History (${history.length})` : "Overview"}
            </button>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 text-xs">
          {([7, 14, 30] as const).map(d => (
            <button key={d} type="button" onClick={() => setDays(d)}
              className={`rounded-md px-3 py-1.5 font-medium transition-colors ${days === d ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
              {d}d
            </button>
          ))}
        </div>
        <button type="button" onClick={() => void load()} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
          <RefreshCw size={11} />Refresh
        </button>
        {section === "rules" && (
          <button type="button" onClick={() => setRuleModal({})}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[#1877F2] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#166fe5]">
            <Plus size={12} />New rule
          </button>
        )}
      </div>

      {/* Overview: campaign health cards */}
      {section === "overview" && (
        <div>
          {(!report?.campaigns || report.campaigns.length === 0) ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center">
              <ShieldAlert size={32} className="mx-auto mb-3 text-slate-300" />
              <p className="text-sm font-medium text-slate-500">No live campaigns found</p>
              <p className="text-xs text-slate-400 mt-1">Create campaigns in your Zernio account to see health scores here.</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-sm">
                  <thead className="border-b border-slate-100 bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3 text-left">Campaign</th>
                      <th className="px-4 py-3 text-left">Health</th>
                      <th className="px-4 py-3 text-right">Spend</th>
                      <th className="px-4 py-3 text-right">CTR</th>
                      <th className="px-4 py-3 text-right">ROAS</th>
                      <th className="px-4 py-3 text-right">Conversions</th>
                      <th className="px-4 py-3 text-left">Issues</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {report.campaigns.map(c => {
                      const zm = ZONE_META[c.zone] ?? ZONE_META.insufficient_data;
                      const ZIcon = zm.icon;
                      return (
                        <tr key={c.campaign_id} className="hover:bg-slate-50">
                          <td className="px-4 py-3">
                            <p className="font-medium text-slate-800 max-w-[160px] truncate">{c.name}</p>
                            <p className="text-[11px] text-slate-400 capitalize">{c.platform}</p>
                          </td>
                          <td className="px-4 py-3">
                            <div className="space-y-1">
                              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${zm.color}`}>
                                <ZIcon size={9} />{zm.label}
                              </span>
                              <HealthScoreBar score={c.health_score} zone={c.zone} />
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right text-slate-700">${fmt(c.spend)}</td>
                          <td className="px-4 py-3 text-right text-slate-700">{c.ctr.toFixed(2)}%</td>
                          <td className={`px-4 py-3 text-right font-medium ${c.roas >= 2 ? "text-emerald-600" : c.roas > 0 && c.roas < 1 ? "text-red-600" : "text-slate-700"}`}>
                            {c.roas > 0 ? `${c.roas.toFixed(2)}×` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right text-slate-700">{c.conversions}</td>
                          <td className="px-4 py-3 max-w-[240px]">
                            <ul className="space-y-0.5">
                              {c.issues.slice(0, 2).map((issue, i) => (
                                <li key={i} className={`text-[11px] ${issue.startsWith("✓") ? "text-emerald-600" : "text-slate-500"}`}>{issue}</li>
                              ))}
                            </ul>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Rules manager */}
      {section === "rules" && (
        <div className="space-y-3">
          {rules.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center">
              <Settings size={28} className="mx-auto mb-2 text-slate-300" />
              <p className="text-sm text-slate-500">No rules yet — click "New rule" to create one</p>
            </div>
          ) : rules.map(rule => {
            const actionMeta = rule.action === "auto_pause"
              ? { label: "Auto-pause", icon: Pause, color: "text-red-600 bg-red-50" }
              : { label: "Alert only", icon: Bell, color: "text-amber-700 bg-amber-50" };
            const ActionIcon = actionMeta.icon;
            return (
              <div key={rule.id} className={`flex items-start gap-3 rounded-xl border bg-white p-4 shadow-sm transition-opacity ${rule.enabled ? "" : "opacity-50"}`}>
                <div className={`mt-0.5 rounded-lg p-1.5 ${actionMeta.color}`}>
                  <ActionIcon size={13} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-slate-800">{rule.name}</p>
                    {rule.is_default && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">default</span>}
                    {!rule.enabled && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-400">disabled</span>}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    When <strong>{CONDITION_LABELS[rule.condition] ?? rule.condition}</strong> is <strong>{OPERATOR_LABELS[rule.operator] ?? rule.operator} {rule.value}</strong>
                    {rule.min_spend > 0 ? ` · min $${rule.min_spend} spend` : ""}
                    {rule.min_impressions > 0 ? ` · min ${rule.min_impressions} impressions` : ""}
                    {rule.notify_whatsapp ? " · 📱 WhatsApp alert" : ""}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button type="button" onClick={() => void toggleRule(rule)} disabled={!!togglingRule}
                    title={rule.enabled ? "Disable" : "Enable"}
                    className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
                    {togglingRule === rule.id ? <Loader2 size={13} className="animate-spin" /> : rule.enabled ? <BellOff size={13} /> : <Bell size={13} />}
                  </button>
                  <button type="button" onClick={() => setRuleModal(rule)}
                    className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
                    <Pencil size={13} />
                  </button>
                  <button type="button" onClick={() => void deleteRule(rule.id)} disabled={deletingRule === rule.id}
                    className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500">
                    {deletingRule === rule.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Alert history timeline */}
      {section === "history" && (
        <div>
          {history.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center">
              <Clock size={28} className="mx-auto mb-2 text-slate-300" />
              <p className="text-sm text-slate-500">No alert history yet — the monitor runs every 30 minutes</p>
            </div>
          ) : (
            <div className="space-y-2">
              {history.map(h => {
                const isAutoPause = h.action === "auto_pause";
                return (
                  <div key={h.id} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
                    <div className={`mt-0.5 rounded-full p-1.5 ${isAutoPause ? "bg-red-100 text-red-600" : "bg-amber-100 text-amber-700"}`}>
                      {isAutoPause ? <Zap size={11} /> : <Bell size={11} />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-medium text-slate-800">{h.campaign_name}</p>
                          <p className="text-xs text-slate-500">
                            Rule: <strong>{h.rule_name}</strong> · {isAutoPause ? "Auto-paused" : "Alert sent"}
                            {h.health_score != null && ` · Score ${h.health_score}/100`}
                          </p>
                          {h.metrics && (
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              {h.metrics.spend != null && `Spend $${h.metrics.spend.toFixed(2)}`}
                              {h.metrics.ctr != null && ` · CTR ${h.metrics.ctr.toFixed(2)}%`}
                              {h.metrics.roas != null && h.metrics.roas > 0 && ` · ROAS ${h.metrics.roas.toFixed(2)}×`}
                            </p>
                          )}
                        </div>
                        <span className="text-[11px] text-slate-400 shrink-0 whitespace-nowrap">
                          {new Date(h.fired_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {ruleModal !== null && (
        <RuleFormModal
          initial={ruleModal}
          onSave={saveRule}
          onClose={() => setRuleModal(null)}
        />
      )}
    </div>
  );
}

// ── Reporting tab ──────────────────────────────────────────────────────────────

const PLATFORM_FILTERS = ["all", "facebook", "instagram", "google", "tiktok", "linkedin"] as const;
type PlatformFilter = (typeof PLATFORM_FILTERS)[number];

function fmt(n: number, decimals = 2) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(decimals);
}

function ReportingTab({ rows }: { rows: MetaAdsCampaignDraft[] }) {
  const [insights, setInsights] = useState<ZernioAdsInsights | null>(null);
  const [loadingInsights, setLoadingInsights] = useState(false);
  const [insightsError, setInsightsError] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  const [platform, setPlatform] = useState<PlatformFilter>("all");
  const [toggleLoading, setToggleLoading] = useState<string | null>(null);

  const fetchInsights = useCallback(async () => {
    setLoadingInsights(true);
    setInsightsError(null);
    try {
      const data = await zernioAdsApi.insights(platform === "all" ? undefined : platform, days);
      setInsights(data);
      if (data.error) setInsightsError(data.error);
    } catch (e) {
      setInsightsError(e instanceof Error ? e.message : "Failed to load insights");
    } finally {
      setLoadingInsights(false);
    }
  }, [platform, days]);

  useEffect(() => { void fetchInsights(); }, [fetchInsights]);

  async function toggleCampaign(c: { id: string; status: string; platform?: string }) {
    const next = c.status === "active" ? "paused" : "active";
    setToggleLoading(c.id);
    try {
      await zernioAdsApi.updateCampaignStatus(c.id, next as "active" | "paused", c.platform);
      setInsights((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          campaigns: prev.campaigns.map((x) => x.id === c.id ? { ...x, status: next } : x),
        };
      });
    } catch (e) {
      setInsightsError(e instanceof Error ? e.message : "Status update failed");
    } finally {
      setToggleLoading(null);
    }
  }

  const summaryCards = insights
    ? [
        { label: `Total spend (${days}d)`, value: `$${fmt(insights.spend)}`, icon: DollarSign, color: "text-brand" },
        { label: "Impressions", value: fmt(insights.impressions, 0), icon: Users, color: "text-blue-500" },
        { label: "Clicks", value: fmt(insights.clicks, 0), icon: TrendingUp, color: "text-emerald-500" },
        { label: "CTR", value: `${insights.ctr.toFixed(2)}%`, icon: BarChart3, color: "text-orange-500" },
        { label: "CPC", value: `$${insights.cpc.toFixed(3)}`, icon: DollarSign, color: "text-purple-500" },
        { label: "Conversions", value: fmt(insights.conversions, 0), icon: TrendingUp, color: "text-pink-500" },
      ]
    : [];

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
          {([7, 14, 30, 60, 90] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${days === d ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              {d}d
            </button>
          ))}
        </div>

        <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
          {PLATFORM_FILTERS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPlatform(p)}
              className={`rounded-md px-3 py-1 text-xs font-medium capitalize transition-colors ${platform === p ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              {p}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => void fetchInsights()}
          disabled={loadingInsights}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {loadingInsights ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Refresh
        </button>
      </div>

      {insightsError && !loadingInsights && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {insightsError.includes("not configured")
            ? "Zernio Ads API key not configured on the server."
            : insightsError}
        </div>
      )}

      {/* Metrics cards */}
      {loadingInsights ? (
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm animate-pulse">
              <div className="h-2 w-16 rounded bg-slate-200 mb-3" />
              <div className="h-6 w-20 rounded bg-slate-200" />
            </div>
          ))}
        </div>
      ) : insights && (
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {summaryCards.map((c) => (
            <div key={c.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className={`mb-1 ${c.color}`}><c.icon size={14} /></div>
              <p className="text-xl font-bold text-slate-900">{c.value}</p>
              <p className="text-[11px] text-slate-500 mt-0.5">{c.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Live campaigns table */}
      {insights && insights.campaigns.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-700">Live campaigns ({insights.total_campaigns})</p>
            <span className="text-[11px] text-slate-400">via Zernio Ads API · {days}d window</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-sm">
              <thead className="border-b border-slate-100 bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2.5 text-left">Campaign</th>
                  <th className="px-4 py-2.5 text-left">Platform</th>
                  <th className="px-4 py-2.5 text-right">Spend</th>
                  <th className="px-4 py-2.5 text-right">Impressions</th>
                  <th className="px-4 py-2.5 text-right">Clicks</th>
                  <th className="px-4 py-2.5 text-right">CTR</th>
                  <th className="px-4 py-2.5 text-right">CPC</th>
                  <th className="px-4 py-2.5 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {insights.campaigns.map((c) => {
                  const m = c.metrics ?? {} as ZernioCampaignMetrics;
                  const spend = m.spend ?? c.spend ?? 0;
                  const impr = m.impressions ?? c.impressions ?? 0;
                  const clicks = m.clicks ?? c.clicks ?? 0;
                  const ctr = m.ctr ?? (impr > 0 ? clicks / impr * 100 : 0);
                  const cpc = m.cpc ?? (clicks > 0 ? spend / clicks : 0);
                  const isActive = c.status === "active";
                  const isToggling = toggleLoading === c.id;
                  return (
                    <tr key={c.id} className="hover:bg-slate-50">
                      <td className="px-4 py-2.5 font-medium text-slate-800 max-w-[180px] truncate">{c.name}</td>
                      <td className="px-4 py-2.5">
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 capitalize">
                          {c.platform || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-700">${fmt(spend)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-700">{fmt(impr, 0)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-700">{fmt(clicks, 0)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-700">{ctr.toFixed(2)}%</td>
                      <td className="px-4 py-2.5 text-right text-slate-700">${cpc.toFixed(3)}</td>
                      <td className="px-4 py-2.5 text-center">
                        <button
                          type="button"
                          onClick={() => void toggleCampaign(c)}
                          disabled={isToggling}
                          title={isActive ? "Pause" : "Activate"}
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                            isActive ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-200" : "bg-amber-100 text-amber-800 hover:bg-amber-200"
                          } disabled:opacity-50`}
                        >
                          {isToggling
                            ? <Loader2 size={9} className="animate-spin" />
                            : isActive ? <Pause size={9} /> : <Play size={9} />}
                          <span className="capitalize">{c.status}</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Drafts breakdown (local) */}
      {rows.filter((r) => r.status === "active").length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-700">Campaign drafts (local)</p>
          </div>
          <table className="w-full text-sm">
            <thead className="border-b border-slate-100 bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2.5 text-left">Name</th>
                <th className="px-4 py-2.5 text-left">Objective</th>
                <th className="px-4 py-2.5 text-right">Daily budget</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.filter((r) => r.status === "active").map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-medium text-slate-800">{r.name}</td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${objectiveMeta(r.objective ?? "").color}`}>
                      {objectiveMeta(r.objective ?? "").label}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-600">{r.currency} {r.daily_budget.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loadingInsights && (!insights || insights.campaigns.length === 0) && !insightsError && (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
          <BarChart3 className="mx-auto mb-2 h-8 w-8 text-slate-300" />
          <p className="font-medium">No live campaigns found</p>
          <p className="text-xs mt-1 text-slate-400">
            Create ads on Facebook, Instagram, or other platforms via your Zernio account to see metrics here.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MetaAdsPage() {
  const [rows, setRows] = useState<MetaAdsCampaignDraft[]>([]);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [tab, setTab] = useState<"campaigns" | "reporting" | "health">("campaigns");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiOpen, setAiOpen] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const { drafts } = await marketingApi.listMetaAdsDrafts();
      setRows(drafts);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const currency = getCurrency();

  function openNew() {
    setModal({ name: "", objective: "awareness", daily_budget: 500, currency, status: "draft", notes: "{}" });
  }

  function applyAISuggestion(s: AICampaignSuggestion) {
    setModal({
      name: s.name,
      objective: s.objective,
      daily_budget: s.daily_budget,
      currency: s.currency || currency,
      status: "draft",
      notes: partsToMetaNotes({
        audience: s.audience,
        strategy: s.strategy,
        start_date: s.start_date,
        end_date: s.end_date,
      }),
    });
    setAiOpen(false);
  }

  function openEdit(r: MetaAdsCampaignDraft) {
    setModal({ id: r.id, name: r.name, objective: r.objective, daily_budget: r.daily_budget, currency: r.currency, status: r.status, notes: r.notes ?? "{}" });
  }

  async function handleDuplicate(r: MetaAdsCampaignDraft) {
    setSaving(true);
    try {
      await marketingApi.createMetaAdsDraft({
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

  async function handleToggleStatus(r: MetaAdsCampaignDraft) {
    const next = r.status === "active" ? "paused" : "active";
    try {
      await marketingApi.updateMetaAdsDraft(r.id, { status: next });
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
      const payload = {
        name: modal.name.trim(),
        objective: modal.objective ?? "awareness",
        daily_budget: Number(modal.daily_budget) || 0,
        currency: modal.currency ?? currency,
        notes: modal.notes ?? "{}",
        status: modal.status ?? "draft",
      };
      if (modal.id) {
        await marketingApi.updateMetaAdsDraft(modal.id, payload);
      } else {
        await marketingApi.createMetaAdsDraft(payload);
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
      await marketingApi.deleteMetaAdsDraft(id);
      setRows((prev) => prev.filter((r) => r.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
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
    <div className="mx-auto max-w-5xl space-y-5 p-4 sm:p-6 pb-16">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-[#1877F2]">
            <Target size={18} />
            <span className="text-[11px] font-semibold uppercase tracking-wide">Marketing</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Meta Ads</h1>
          <p className="mt-1 text-sm text-slate-500">
            Plan and track campaigns — including drafts saved by the{" "}
            <strong className="font-medium text-slate-700">Meta Ads</strong> agent in Zilo Chat.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setAiOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-[#1877F2]/30 bg-[#1877F2]/5 px-4 py-2 text-sm font-semibold text-[#1877F2] hover:bg-[#1877F2]/10"
          >
            <Sparkles size={14} />
            AI Builder
          </button>
          <button
            type="button"
            onClick={openNew}
            className="inline-flex items-center gap-2 rounded-lg bg-[#1877F2] px-4 py-2 text-sm font-semibold text-white hover:bg-[#166fe5]"
          >
            <Plus size={15} />
            New campaign
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>
      )}

      <MarketingApiBanner product="Meta Ads" />

      {/* Summary cards */}
      {rows.length > 0 && <SummaryCards rows={rows} />}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 text-sm w-fit">
        {(["campaigns", "reporting", "health"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 font-medium capitalize transition-colors ${
              tab === t ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {t === "health" && <ShieldAlert size={13} />}
            {t === "health" ? "Health & Alerts" : t}
          </button>
        ))}
      </div>

      {tab === "reporting" ? (
        <ReportingTab rows={rows} />
      ) : tab === "health" ? (
        <HealthTab />
      ) : (
        <>
          {/* Status filter */}
          <div className="flex flex-wrap gap-1.5">
            {STATUS_FILTERS.map((f) => {
              const count = f === "all" ? rows.length : rows.filter((r) => r.status === f).length;
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => setStatusFilter(f)}
                  className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                    statusFilter === f
                      ? "bg-[#1877F2] text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {f} {count > 0 && <span className="opacity-70">({count})</span>}
                </button>
              );
            })}
          </div>

          <CampaignsTable
            rows={filtered}
            onEdit={openEdit}
            onDuplicate={handleDuplicate}
            onDelete={handleDelete}
            onToggleStatus={handleToggleStatus}
          />
        </>
      )}

      {/* Integration checklist */}
      <section className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 text-xs text-slate-600 space-y-1">
        <p className="font-semibold text-slate-800 mb-2">Integration status</p>
        <p>✅ Campaign drafts saved to MongoDB (shared with Zilo Chat agent)</p>
        <p>✅ Live metrics via Zernio Ads API (Facebook, Instagram, Google, TikTok, LinkedIn)</p>
        <p>✅ Pause / Activate campaigns directly from Reporting tab</p>
        <p>✅ Post boosting and Click-to-WhatsApp ads via Zernio</p>
      </section>

      {modal && (
        <CampaignModal
          modal={modal}
          saving={saving}
          error={error}
          onClose={() => setModal(null)}
          onChange={setModal}
          onSave={() => void save()}
        />
      )}

      {aiOpen && (
        <AICampaignBuilderDrawer
          currency={currency}
          onApply={applyAISuggestion}
          onClose={() => setAiOpen(false)}
        />
      )}
    </div>
  );
}

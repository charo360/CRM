"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MarketingApiBanner } from "@/components/marketing/MarketingApiBanner";
import { assistantApi, api } from "@/lib/api";
import {
  type AdsCampaign,
  listGoogleCampaigns,
  upsertGoogleCampaign,
  deleteGoogleCampaign,
} from "@/lib/marketing-stubs";
import { getCurrency } from "@/lib/auth";
import { formatDateTime } from "@/lib/utils";
import {
  Search,
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
  ChevronRight,
  Wand2,
  MousePointerClick,
  Tag,
  Wifi,
  WifiOff,
  AlertCircle,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────────

const CAMPAIGN_TYPES = [
  { id: "search", label: "Search", blurb: "Text ads on Google Search", color: "bg-blue-100 text-blue-700" },
  { id: "performance_max", label: "Performance Max", blurb: "All Google channels, AI-driven", color: "bg-brand/15 text-brand-dark" },
  { id: "display", label: "Display", blurb: "Image ads across websites", color: "bg-cyan-100 text-cyan-700" },
  { id: "video", label: "Video / YouTube", blurb: "Video ads on YouTube", color: "bg-red-100 text-red-700" },
  { id: "shopping", label: "Shopping", blurb: "Product listings in search", color: "bg-orange-100 text-orange-700" },
  { id: "demand_gen", label: "Demand Gen", blurb: "Discovery & Gmail ads", color: "bg-brand/15 text-brand-dark" },
];

const BIDDING_STRATEGIES = [
  "Target CPA",
  "Target ROAS",
  "Maximize Clicks",
  "Maximize Conversions",
  "Maximize Conversion Value",
  "Target Impression Share",
  "Manual CPC",
];

const STATUS_BADGE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  active: "bg-emerald-100 text-emerald-700",
  paused: "bg-amber-100 text-amber-800",
  ended: "bg-slate-200 text-slate-500",
};

const STATUS_FILTERS = ["all", "active", "paused", "draft", "ended"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

interface GoogleCampaignExt extends AdsCampaign {
  keywords?: string;
  negative_keywords?: string;
  bidding_strategy?: string;
  target_cpa?: number;
  audience?: string;
}

type ModalState = Partial<GoogleCampaignExt>;

// ── Helpers ────────────────────────────────────────────────────────────────────

function typeMeta(id: string) {
  return CAMPAIGN_TYPES.find((t) => t.id === id) ?? { label: id, blurb: "", color: "bg-slate-100 text-slate-600" };
}

function loadExt(id: string): Partial<GoogleCampaignExt> {
  try {
    const raw = localStorage.getItem(`zilo_gads_ext_${id}`);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveExt(id: string, ext: Partial<GoogleCampaignExt>) {
  localStorage.setItem(`zilo_gads_ext_${id}`, JSON.stringify(ext));
}

function removeExt(id: string) {
  localStorage.removeItem(`zilo_gads_ext_${id}`);
}

function mergeExt(rows: AdsCampaign[]): GoogleCampaignExt[] {
  return rows.map((r) => ({ ...r, ...loadExt(r.id) }));
}

// ── Summary cards ──────────────────────────────────────────────────────────────

function SummaryCards({ rows }: { rows: GoogleCampaignExt[] }) {
  const currency = getCurrency();
  const active = rows.filter((r) => r.status === "active").length;
  const drafts = rows.filter((r) => r.status === "draft").length;
  const totalBudget = rows.filter((r) => r.status === "active").reduce((s, r) => s + r.daily_budget, 0);

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        { label: "Total campaigns", value: rows.length, icon: Layers, color: "text-brand" },
        { label: "Active", value: active, icon: TrendingUp, color: "text-emerald-500" },
        { label: "Drafts", value: drafts, icon: Pencil, color: "text-slate-400" },
        { label: "Daily budget (active)", value: `${currency} ${totalBudget.toFixed(0)}`, icon: DollarSign, color: "text-blue-500" },
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

// ── AI Builder ─────────────────────────────────────────────────────────────────

interface AISuggestion {
  name: string;
  objective: string;
  daily_budget: number;
  currency: string;
  keywords: string;
  negative_keywords: string;
  bidding_strategy: string;
  target_cpa?: number;
  audience: string;
  strategy: string;
}

interface ChatMsg { role: "user" | "assistant"; text: string; suggestion?: AISuggestion; }

const GOOGLE_AI_PROMPT = `You are a Google Ads expert helping businesses create high-performing campaigns.

When the user describes their business or goal, respond with:
1. Campaign strategy (2-3 sentences — search intent, match types, ad copy angle)
2. Top keyword recommendations with match types
3. Bidding strategy explanation

ALWAYS end with a JSON block in this exact format:
\`\`\`json
{
  "name": "Campaign name",
  "objective": "search|performance_max|display|video|shopping|demand_gen",
  "daily_budget": <number>,
  "currency": "KES",
  "keywords": "keyword 1 [broad], \\"keyword 2\\" [phrase], [exact keyword 3]",
  "negative_keywords": "keyword to exclude, another exclusion",
  "bidding_strategy": "Target CPA|Target ROAS|Maximize Clicks|...",
  "target_cpa": <number or null>,
  "audience": "who this targets — demographics, in-market segments",
  "strategy": "one sentence on the winning ad angle"
}
\`\`\``;

function extractSuggestion(reply: string): AISuggestion | null {
  const match = reply.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const p = JSON.parse(match[1].trim());
    if (p.name && p.objective) return p as AISuggestion;
  } catch { /* ignore */ }
  return null;
}

function stripJson(text: string) {
  return text.replace(/```(?:json)?[\s\S]*?```/g, "").trim();
}

function AIBuilderDrawer({
  onApply,
  onClose,
}: {
  onApply: (s: AISuggestion) => void;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [convId, setConvId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const currency = getCurrency();

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);
    const prompt = messages.length === 0
      ? `${GOOGLE_AI_PROMPT}\n\nDefault currency: ${currency}\n\nUser goal: ${text}`
      : text;
    try {
      const res = await assistantApi.chat({ message: prompt, conversation_id: convId, agent: "general", auto_approve: true });
      setConvId(res.conversation_id);
      const suggestion = extractSuggestion(res.reply);
      setMessages((prev) => [...prev, { role: "assistant", text: stripJson(res.reply), suggestion: suggestion ?? undefined }]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: "assistant", text: e instanceof Error ? e.message : "Failed. Please try again." }]);
    } finally { setLoading(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex flex-col w-full max-w-md bg-white shadow-2xl h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-emerald-500/5 to-transparent">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center">
              <Sparkles size={13} className="text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800">AI Campaign Builder</p>
              <p className="text-[11px] text-slate-500">Describe your goal — AI picks keywords + strategy</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:bg-slate-100"><X size={18} /></button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="space-y-3 text-center pt-6">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto">
                <Wand2 size={22} className="text-emerald-600" />
              </div>
              <p className="text-sm font-medium text-slate-700">Tell me about your business</p>
              <p className="text-xs text-slate-400 leading-relaxed">I'll suggest the best keywords, bidding strategy, and campaign structure for Google Ads.</p>
              <div className="space-y-2 text-left mt-4">
                {[
                  "I sell furniture in Nairobi and want leads from people searching to buy sofas",
                  "Tech startup looking for sign-ups — people searching for project management tools",
                  "Restaurant in Westlands wanting more lunch reservations from nearby offices",
                ].map((ex) => (
                  <button key={ex} type="button" onClick={() => setInput(ex)}
                    className="w-full text-left rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:border-emerald-300 hover:bg-emerald-50/50 transition-colors">
                    <ChevronRight size={11} className="inline mr-1 text-slate-400" />{ex}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className="max-w-[85%] space-y-2">
                <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  m.role === "user" ? "bg-emerald-600 text-white rounded-br-sm" : "bg-slate-100 text-slate-800 rounded-bl-sm"
                }`}>{m.text}</div>

                {m.suggestion && (
                  <div className="bg-white border border-emerald-200 rounded-xl p-3 space-y-2 shadow-sm">
                    <div className="flex items-center gap-1.5 text-emerald-600">
                      <Sparkles size={12} />
                      <span className="text-[11px] font-semibold uppercase tracking-wide">Campaign ready</span>
                    </div>
                    <div className="space-y-1.5 text-xs text-slate-700">
                      <p><span className="text-slate-400">Name</span> · {m.suggestion.name}</p>
                      <p><span className="text-slate-400">Type</span> · {typeMeta(m.suggestion.objective).label}</p>
                      <p><span className="text-slate-400">Budget</span> · {m.suggestion.currency} {m.suggestion.daily_budget}/day</p>
                      <p><span className="text-slate-400">Bidding</span> · {m.suggestion.bidding_strategy}</p>
                      {m.suggestion.keywords && (
                        <p className="leading-relaxed"><span className="text-slate-400">Keywords</span> · {m.suggestion.keywords.slice(0, 120)}{m.suggestion.keywords.length > 120 ? "…" : ""}</p>
                      )}
                      {m.suggestion.audience && (
                        <p><span className="text-slate-400">Audience</span> · {m.suggestion.audience}</p>
                      )}
                    </div>
                    <button type="button" onClick={() => onApply(m.suggestion!)}
                      className="w-full mt-1 rounded-lg bg-emerald-600 py-2 text-xs font-semibold text-white hover:bg-emerald-700 transition-colors">
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
                <Loader2 size={13} className="animate-spin" />Finding best keywords…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-100 px-4 py-3">
          <div className="flex items-end gap-2">
            <textarea rows={2}
              className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm resize-none outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-400/30"
              placeholder="Describe your product, goal, or target customer…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}
            />
            <button type="button" disabled={!input.trim() || loading} onClick={() => void send()}
              className="rounded-xl bg-emerald-600 p-2.5 text-white hover:bg-emerald-700 disabled:opacity-40 transition-colors">
              <Send size={16} />
            </button>
          </div>
          <p className="text-[10px] text-slate-400 mt-1.5 text-center">Enter to send · Shift+Enter for new line</p>
        </div>
      </div>
    </div>
  );
}

// ── Campaign modal ─────────────────────────────────────────────────────────────

function CampaignModal({
  modal, saving, onClose, onChange, onSave,
}: {
  modal: ModalState;
  saving: boolean;
  onClose: () => void;
  onChange: (m: ModalState) => void;
  onSave: () => void;
}) {
  const currency = getCurrency();

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-800">{modal.id ? "Edit campaign" : "New campaign"}</h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"><X size={18} /></button>
        </div>

        <div className="space-y-4 p-5">
          {/* Name */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Campaign name *</label>
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-400/30"
              placeholder="e.g. Nairobi Furniture Search"
              value={modal.name ?? ""}
              onChange={(e) => onChange({ ...modal, name: e.target.value })} />
          </div>

          {/* Campaign type */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Campaign type</label>
            <div className="mt-1.5 grid grid-cols-2 gap-1.5">
              {CAMPAIGN_TYPES.map((t) => (
                <button key={t.id} type="button" onClick={() => onChange({ ...modal, objective: t.id })}
                  className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                    modal.objective === t.id
                      ? "border-emerald-500 bg-emerald-50 text-emerald-700"
                      : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                  }`}>
                  <p className="text-xs font-medium">{t.label}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">{t.blurb}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Budget + Currency */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Daily budget</label>
              <input type="number" min={0} step={1}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500"
                value={modal.daily_budget ?? ""}
                onChange={(e) => onChange({ ...modal, daily_budget: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Currency</label>
              <select className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500"
                value={modal.currency ?? currency}
                onChange={(e) => onChange({ ...modal, currency: e.target.value })}>
                <option>KES</option><option>USD</option><option>EUR</option><option>GBP</option><option>ZAR</option><option>NGN</option>
              </select>
            </div>
          </div>

          {/* Bidding */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Bidding strategy</label>
              <select className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500"
                value={modal.bidding_strategy ?? "Maximize Clicks"}
                onChange={(e) => onChange({ ...modal, bidding_strategy: e.target.value })}>
                {BIDDING_STRATEGIES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Target CPA (optional)</label>
              <input type="number" min={0} step={1}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500"
                placeholder="e.g. 500"
                value={modal.target_cpa ?? ""}
                onChange={(e) => onChange({ ...modal, target_cpa: e.target.value ? Number(e.target.value) : undefined })} />
            </div>
          </div>

          {/* Keywords */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide flex items-center gap-1">
              <Tag size={10} />Keywords
            </label>
            <textarea rows={3}
              className="mt-1 w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-400/30 font-mono text-xs"
              placeholder={`[exact match keyword]\n"phrase match keyword"\nbroad match keyword`}
              value={modal.keywords ?? ""}
              onChange={(e) => onChange({ ...modal, keywords: e.target.value })} />
            <p className="text-[10px] text-slate-400 mt-1">Use [brackets] for exact, "quotes" for phrase, plain for broad match</p>
          </div>

          {/* Negative keywords */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Negative keywords</label>
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500"
              placeholder="free, DIY, cheap (comma-separated)"
              value={modal.negative_keywords ?? ""}
              onChange={(e) => onChange({ ...modal, negative_keywords: e.target.value })} />
          </div>

          {/* Audience */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Target audience / location</label>
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500"
              placeholder="e.g. Nairobi, Kenya — in-market: home furnishings"
              value={modal.audience ?? ""}
              onChange={(e) => onChange({ ...modal, audience: e.target.value })} />
          </div>

          {/* Status */}
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Status</label>
            <div className="mt-1.5 flex gap-1.5">
              {["draft", "active", "paused", "ended"].map((s) => (
                <button key={s} type="button" onClick={() => onChange({ ...modal, status: s as AdsCampaign["status"] })}
                  className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                    modal.status === s ? STATUS_BADGE[s] + " ring-1 ring-inset ring-current" : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                  }`}>{s}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
          <button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">Cancel</button>
          <button type="button" disabled={saving || !modal.name?.trim()} onClick={onSave}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
            {saving && <Loader2 size={14} className="animate-spin" />}
            {modal.id ? "Save changes" : "Create campaign"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Types for live ads data ────────────────────────────────────────────────────

interface LiveAdsCampaign {
  id: string;
  name: string;
  status: string;
  impressions: number;
  clicks: number;
  cost: number;
  ctr: number;
  avg_cpc: number;
}

interface LiveAdsSummary {
  total_spend: number;
  total_clicks: number;
  total_impressions: number;
  avg_ctr: number;
  avg_cpc: number;
}

interface AdsApiResponse {
  connected: boolean;
  error?: string;
  customer_id?: string;
  period_days?: number;
  summary?: LiveAdsSummary;
  campaigns?: LiveAdsCampaign[];
}

// ── Reporting tab ──────────────────────────────────────────────────────────────

function ReportingTab({ rows }: { rows: GoogleCampaignExt[] }) {
  const currency = getCurrency();
  const [customerId, setCustomerId] = useState(() => localStorage.getItem("zilo_gads_cid") || "");
  const [days, setDays] = useState(30);
  const [liveData, setLiveData] = useState<AdsApiResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchLive = async () => {
    const cid = customerId.trim();
    if (!cid) return;
    localStorage.setItem("zilo_gads_cid", cid);
    setLoading(true);
    try {
      const res = await api.get<AdsApiResponse>(`/analytics/google-ads?customer_id=${encodeURIComponent(cid)}&days=${days}`);
      setLiveData(res);
    } catch (e) {
      setLiveData({ connected: false, error: e instanceof Error ? e.message : "Request failed" });
    } finally {
      setLoading(false);
    }
  };

  const s = liveData?.summary;

  return (
    <div className="space-y-5">

      {/* ── Live data panel ── */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Live Analytics</h3>
            <p className="text-xs text-slate-400 mt-0.5">Pulled directly from Google Ads API via your connected account</p>
          </div>
          {liveData?.connected === true && (
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full">
              <Wifi size={11} /> Connected
            </span>
          )}
          {liveData?.connected === false && (
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-red-600 bg-red-50 px-2.5 py-1 rounded-full">
              <WifiOff size={11} /> Not connected
            </span>
          )}
        </div>

        {/* Customer ID + controls */}
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            placeholder="Google Ads Customer ID (e.g. 123-456-7890)"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-400/30 font-mono"
          />
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-emerald-500 w-32">
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button
            onClick={fetchLive}
            disabled={loading || !customerId.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {loading ? "Fetching…" : "Fetch Data"}
          </button>
        </div>

        {/* Error state */}
        {liveData?.error && (
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <AlertCircle size={15} className="text-amber-600 mt-0.5 shrink-0" />
            <div>
              <p className="text-xs font-semibold text-amber-800">Could not fetch data</p>
              <p className="text-xs text-amber-700 mt-0.5">{liveData.error}</p>
              {!liveData.connected && (
                <p className="text-xs text-amber-600 mt-1">Connect Google Ads via <strong>Integrations → Google Ads</strong> first.</p>
              )}
            </div>
          </div>
        )}

        {/* Summary metrics */}
        {s && (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {[
              { label: "Total Spend", value: `${currency} ${s.total_spend.toFixed(2)}`, color: "text-blue-600" },
              { label: "Clicks", value: s.total_clicks.toLocaleString(), color: "text-emerald-600" },
              { label: "Impressions", value: s.total_impressions.toLocaleString(), color: "text-slate-700" },
              { label: "Avg CTR", value: `${s.avg_ctr.toFixed(2)}%`, color: "text-purple-600" },
              { label: "Avg CPC", value: `${currency} ${s.avg_cpc.toFixed(2)}`, color: "text-orange-600" },
            ].map((m) => (
              <div key={m.label} className="rounded-lg border border-slate-100 bg-slate-50 p-3 text-center">
                <p className={`text-lg font-bold ${m.color}`}>{m.value}</p>
                <p className="text-[11px] text-slate-500 mt-0.5">{m.label}</p>
              </div>
            ))}
          </div>
        )}

        {/* Campaign breakdown table */}
        {liveData?.campaigns && liveData.campaigns.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-slate-200">
            <div className="border-b border-slate-100 px-4 py-3 flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-700">Campaign Breakdown</p>
              <span className="text-xs text-slate-400">Last {liveData.period_days} days</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px] text-sm">
                <thead className="border-b border-slate-100 bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-2.5 text-left">Campaign</th>
                    <th className="px-4 py-2.5 text-right">Spend</th>
                    <th className="px-4 py-2.5 text-right">Clicks</th>
                    <th className="px-4 py-2.5 text-right">Impressions</th>
                    <th className="px-4 py-2.5 text-right">CTR</th>
                    <th className="px-4 py-2.5 text-right">Avg CPC</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {liveData.campaigns.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50">
                      <td className="px-4 py-2.5">
                        <p className="font-medium text-slate-900">{c.name}</p>
                        <span className="text-[10px] text-slate-400 capitalize">{c.status.toLowerCase()}</span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-700 font-medium">{currency} {c.cost.toFixed(2)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-600">{c.clicks.toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-right text-slate-600">{c.impressions.toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-right text-slate-600">{c.ctr.toFixed(2)}%</td>
                      <td className="px-4 py-2.5 text-right text-slate-600">{currency} {c.avg_cpc.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!liveData && !loading && (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
            <BarChart3 className="mx-auto mb-2 h-8 w-8 text-slate-300" />
            <p className="text-sm font-medium text-slate-500">Enter your Customer ID and click Fetch Data</p>
            <p className="text-xs text-slate-400 mt-1">Find it in Google Ads → top-right corner (format: 123-456-7890)</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function GoogleAdsPage() {
  const [rows, setRows] = useState<GoogleCampaignExt[]>([]);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [tab, setTab] = useState<"campaigns" | "reporting">("campaigns");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [aiOpen, setAiOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const currency = getCurrency();

  const refresh = useCallback(() => setRows(mergeExt(listGoogleCampaigns())), []);

  useEffect(() => { refresh(); }, [refresh]);

  function openNew() {
    setModal({ name: "", objective: "search", daily_budget: 500, currency, status: "draft", bidding_strategy: "Maximize Clicks" });
  }

  function openEdit(r: GoogleCampaignExt) {
    setModal({ ...r });
  }

  function handleDuplicate(r: GoogleCampaignExt) {
    const copy = upsertGoogleCampaign({ ...r, id: undefined, name: `${r.name} (copy)`, status: "draft", spend: 0, impressions: 0, clicks: 0 });
    saveExt(copy.id, { keywords: r.keywords, negative_keywords: r.negative_keywords, bidding_strategy: r.bidding_strategy, target_cpa: r.target_cpa, audience: r.audience });
    refresh();
  }

  function handleToggleStatus(r: GoogleCampaignExt) {
    const next = r.status === "active" ? "paused" : "active";
    upsertGoogleCampaign({ ...r, status: next });
    refresh();
  }

  function save() {
    if (!modal?.name?.trim()) return;
    setSaving(true);
    const saved = upsertGoogleCampaign({
      id: modal.id,
      name: modal.name.trim(),
      objective: modal.objective ?? "search",
      daily_budget: Number(modal.daily_budget) || 0,
      currency: modal.currency ?? currency,
      status: modal.status ?? "draft",
      spend: modal.spend ?? 0,
      impressions: modal.impressions ?? 0,
      clicks: modal.clicks ?? 0,
    });
    saveExt(saved.id, {
      keywords: modal.keywords,
      negative_keywords: modal.negative_keywords,
      bidding_strategy: modal.bidding_strategy,
      target_cpa: modal.target_cpa,
      audience: modal.audience,
    });
    refresh();
    setModal(null);
    setSaving(false);
  }

  function handleDelete(id: string) {
    if (!confirm("Delete this campaign?")) return;
    deleteGoogleCampaign(id);
    removeExt(id);
    refresh();
  }

  function applyAI(s: AISuggestion) {
    setModal({
      name: s.name,
      objective: s.objective,
      daily_budget: s.daily_budget,
      currency: s.currency || currency,
      status: "draft",
      bidding_strategy: s.bidding_strategy,
      target_cpa: s.target_cpa,
      keywords: s.keywords,
      negative_keywords: s.negative_keywords,
      audience: s.audience,
    });
    setAiOpen(false);
  }

  const filtered = statusFilter === "all" ? rows : rows.filter((r) => r.status === statusFilter);

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-4 sm:p-6 pb-16">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-emerald-600">
            <Search size={18} />
            <span className="text-[11px] font-semibold uppercase tracking-wide">Marketing</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Google Ads</h1>
          <p className="mt-1 text-sm text-slate-500">
            Search, Performance Max, Display, and more — build and track campaigns, get AI keyword suggestions.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <button type="button" onClick={refresh}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
            <RefreshCw size={14} />Refresh
          </button>
          <button type="button" onClick={() => setAiOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-100">
            <Sparkles size={14} />AI Builder
          </button>
          <button type="button" onClick={openNew}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700">
            <Plus size={15} />New campaign
          </button>
        </div>
      </div>

      <MarketingApiBanner product="Google Ads" />

      {rows.length > 0 && <SummaryCards rows={rows} />}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 text-sm w-fit">
        {(["campaigns", "reporting"] as const).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)}
            className={`rounded-md px-4 py-1.5 font-medium capitalize transition-colors ${
              tab === t ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}>{t}</button>
        ))}
      </div>

      {tab === "reporting" ? (
        <ReportingTab rows={rows} />
      ) : (
        <>
          {/* Filter */}
          <div className="flex flex-wrap gap-1.5">
            {STATUS_FILTERS.map((f) => {
              const count = f === "all" ? rows.length : rows.filter((r) => r.status === f).length;
              return (
                <button key={f} type="button" onClick={() => setStatusFilter(f)}
                  className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                    statusFilter === f ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}>
                  {f} {count > 0 && <span className="opacity-70">({count})</span>}
                </button>
              );
            })}
          </div>

          {/* Table */}
          {filtered.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 py-16 text-center">
              <Search size={32} className="mx-auto mb-3 text-slate-300" />
              <p className="text-sm font-medium text-slate-500">No campaigns here</p>
              <p className="text-xs text-slate-400 mt-1">Create one above or use the AI Builder</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead className="border-b border-slate-100 bg-slate-50/80 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Campaign</th>
                      <th className="px-4 py-3">Type</th>
                      <th className="px-4 py-3">Bidding</th>
                      <th className="px-4 py-3">Daily budget</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filtered.map((r) => {
                      const canToggle = r.status === "active" || r.status === "paused";
                      return (
                        <tr key={r.id} className="hover:bg-slate-50/60 transition-colors">
                          <td className="px-4 py-3 max-w-[200px]">
                            <p className="font-medium text-slate-900 truncate">{r.name}</p>
                            <p className="text-[11px] text-slate-400 mt-0.5">{formatDateTime(r.created_at)}</p>
                            {r.keywords && (
                              <p className="text-[10px] text-slate-400 mt-0.5 truncate flex items-center gap-1">
                                <MousePointerClick size={9} />{r.keywords.slice(0, 60)}{r.keywords.length > 60 ? "…" : ""}
                              </p>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${typeMeta(r.objective).color}`}>
                              {typeMeta(r.objective).label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-600">
                            {r.bidding_strategy ?? "—"}
                            {r.target_cpa ? <span className="text-slate-400 ml-1">· CPA {r.currency} {r.target_cpa}</span> : null}
                          </td>
                          <td className="px-4 py-3 font-medium text-slate-700">{r.currency} {r.daily_budget.toFixed(0)}</td>
                          <td className="px-4 py-3">
                            <button type="button" disabled={!canToggle} onClick={() => handleToggleStatus(r)}
                              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${STATUS_BADGE[r.status] ?? ""} ${canToggle ? "cursor-pointer hover:opacity-80" : "cursor-default"}`}>
                              {r.status === "active" && <Pause size={9} />}
                              {r.status === "paused" && <Play size={9} />}
                              <span className="capitalize">{r.status}</span>
                            </button>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center justify-end gap-1">
                              <button type="button" onClick={() => openEdit(r)} title="Edit"
                                className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Pencil size={13} /></button>
                              <button type="button" onClick={() => handleDuplicate(r)} title="Duplicate"
                                className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Copy size={13} /></button>
                              <button type="button" onClick={() => handleDelete(r.id)} title="Delete"
                                className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500"><Trash2 size={13} /></button>
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
        </>
      )}

      {/* Checklist */}
      <section className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 text-xs text-slate-600 space-y-1">
        <p className="font-semibold text-slate-800 mb-2">Integration checklist</p>
        <p>â¢ Campaign drafts saved locally (shared with AI builder)</p>
        <p>â Google Ads API OAuth â store refresh token per workspace</p>
        <p>â Map customer ID â developer token + GAQL for reports</p>
        <p>â Mutate campaigns/ad groups/keywords with API resource names</p>
      </section>

      {modal && (
        <CampaignModal modal={modal} saving={saving} onClose={() => setModal(null)} onChange={setModal} onSave={save} />
      )}

      {aiOpen && <AIBuilderDrawer onApply={applyAI} onClose={() => setAiOpen(false)} />}
    </div>
  );
}

"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  assistantApi,
  teamApi,
  customersApi,
  messagesApi,
  type AssistantConversation,
  type AssistantDocument,
  type AssistantMessage,
  type AssistantModel,
  type AssistantStep,
  type AssistantChatResponse,
  type Customer,
  type TeamMember,
} from "@/lib/api";
import { getAgentPersona, personaBadgeLabel, personaHandoffLine, personaThinkingLabel } from "@/lib/agentPersonas";
import {
  Loader2,
  Send,
  Wrench,
  AlertTriangle,
  CheckCircle2,
  Paperclip,
  FileText,
  Image as ImageIcon,
  X as XIcon,
  ShieldCheck,
  Download,
  MessageCircle,
  Search,
  CheckCheck,
  Bot,
  PencilLine,
  UserPlus,
} from "lucide-react";
import { ZiloLogo } from "@/components/ZiloLogo";
import { getBusinessId, getUser } from "@/lib/auth";
import { downloadAsset } from "@/lib/utils";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  conversationId?: string | null;
  /** Fired when a new conversation id is created, or pass `null` when the thread is reset (e.g. agent switch). */
  onConversationChange?: (id: string | null) => void;
  compact?: boolean;
  /** Pre-fill the message input on mount (e.g. from a template clone). */
  initialMessage?: string;
}


/** Maps raw tool names → friendly activity labels shown during streaming and in steps trail */
const TOOL_LABELS: Record<string, string> = {
  // Customers
  list_customers:        "Checking customers…",
  get_customer:          "Looking up customer…",
  create_customer:       "Creating customer…",
  update_customer:       "Updating customer…",
  delete_customer:       "Removing customer…",
  // Orders
  list_orders:           "Checking orders…",
  update_order_status:   "Updating order status…",
  // Products
  list_products:         "Checking products…",
  get_product_images:    "Loading product images…",
  create_product:        "Creating product…",
  update_product:        "Updating product…",
  delete_product:        "Removing product…",
  // Follow-ups
  list_followups:        "Checking follow-ups…",
  create_followup:       "Scheduling follow-up…",
  // Sales & Finance
  record_sale:           "Recording sale…",
  get_analytics_summary: "Pulling analytics…",
  // Broadcasts
  list_broadcasts:       "Checking broadcasts…",
  create_broadcast:      "Sending broadcast…",
  // Messaging
  send_whatsapp_message: "Sending WhatsApp message…",
  // Team
  list_team:             "Checking team…",
  // Web
  web_search:            "Searching the web…",
  // Documents
  create_business_document: "Designing document…",
  create_presentation:   "Building presentation…",
  generate_document:     "Generating document…",
  get_document_style:    "Loading document style…",
  save_document_style:   "Saving document style…",
  // Google Sheets
  sheets_list:           "Listing spreadsheets…",
  sheets_read:           "Reading spreadsheet…",
  sheets_append:         "Writing to spreadsheet…",
  sheets_update:         "Updating spreadsheet…",
  sheets_create:         "Creating spreadsheet…",
  // Notion
  notion_search:         "Searching Notion…",
  notion_read_page:      "Reading Notion page…",
  notion_create_page:    "Creating Notion page…",
  notion_append_blocks:  "Writing to Notion…",
  notion_query_database: "Querying Notion database…",
  // Integrations
  integrations_status:   "Checking integrations…",
  get_owner_info:        "Getting business info…",
  list_design_library_assets: "Loading design assets…",
  // Shopify
  list_shopify_orders:   "Fetching Shopify orders…",
  list_shopify_products: "Fetching Shopify products…",
  get_shopify_analytics: "Pulling Shopify analytics…",
  shopify_add_product:   "Adding Shopify product…",
  shopify_update_product:"Updating Shopify product…",
  // Stripe
  list_stripe_payments:  "Fetching Stripe payments…",
  // Email marketing
  list_klaviyo_flows:    "Checking Klaviyo flows…",
  // Automations
  list_automations:      "Checking automations…",
  create_automation:     "Creating automation…",
  toggle_automation:     "Toggling automation…",
  // Video generation
  create_kling_video:        "Creating AI video…",
  get_kling_video_status:    "Rendering video…",
  create_video:              "Creating video…",
  get_video_status:          "Rendering video…",
};

function friendlyToolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) + "…";
}

// Per-integration quick prompts shown when that app is connected
const INTEGRATION_PROMPTS: Record<string, string[]> = {
  shopify: ["Show my Shopify orders from today", "What are my top Shopify products?", "Shopify revenue this week"],
  stripe: ["Summarise my Stripe payments this month", "Are there any overdue Stripe invoices?"],
  klaviyo: ["What Klaviyo flows should I set up first?", "Help me build a Klaviyo win-back sequence"],
  mailchimp: ["Draft a Mailchimp newsletter for this week", "Which Mailchimp campaigns performed best?"],
  brevo: ["Set up a Brevo welcome email + SMS sequence", "How do I improve Brevo deliverability?"],
  slack: ["List my Slack channels and show IDs", "Post today's order summary to my #sales channel"],
  gmail: ["Draft a follow-up email to my top customers", "Help me write a customer outreach template"],
  microsoft: ["Sync my overdue follow-ups to Outlook Calendar", "Set up Microsoft Teams alerts for Zilo"],
  google_calendar: ["Convert my overdue follow-ups to calendar events", "Schedule a customer check-in for this week"],
  telegram: ["Check my Telegram bot connection", "What can my Telegram bot do?"],
};

/** Must stay in sync with `LEGACY_MODEL_ALIASES` in backend `assistant/models.py`. */
const LEGACY_ASSISTANT_MODEL_ID: Record<string, string> = {
  "claude-3.5-sonnet": "claude-opus-4-7",
  "claude-opus-4-6": "claude-opus-4-7",
};

/** Remap deprecated rows from cached or older API responses before rendering the `<select>`. */
const DEPRECATED_ASSISTANT_MODEL_ROW: Record<string, { id: string; label: string }> = {
  "claude-3.5-sonnet": { id: "claude-opus-4-7", label: "Claude Opus 4.7 (max quality)" },
  "claude-opus-4-6": { id: "claude-opus-4-7", label: "Claude Opus 4.7 (max quality)" },
};

function sanitizeAssistantModels(raw: AssistantModel[]): AssistantModel[] {
  const out: AssistantModel[] = [];
  const seen = new Set<string>();
  for (const m of raw) {
    const mapped = DEPRECATED_ASSISTANT_MODEL_ROW[m.id];
    const row: AssistantModel = mapped ? { ...m, id: mapped.id, label: mapped.label } : { ...m };
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    out.push(row);
  }
  return out;
}

function pickAssistantModelId(
  requested: string | undefined | null,
  list: AssistantModel[],
  fallbackId: string
): string {
  if (!list.length) return fallbackId || "";
  const ids = new Set(list.map((m) => m.id));
  const r = (requested || "").trim();
  if (r && ids.has(r)) return r;
  const mapped = r ? LEGACY_ASSISTANT_MODEL_ID[r] : undefined;
  if (mapped && ids.has(mapped)) return mapped;
  if (fallbackId && ids.has(fallbackId)) return fallbackId;
  return list[0]?.id || "";
}

function assistantModelStorageKey(): string {
  const bid = getBusinessId();
  const u = getUser();
  const uid = (u?._id as string) || "";
  const scope = bid || uid || "anon";
  return `zilo.assistant_llm_model:v1:${scope}`;
}

function readPersistedAssistantModelId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(assistantModelStorageKey());
  } catch {
    return null;
  }
}

function persistAssistantModelId(id: string) {
  if (typeof window === "undefined" || !id) return;
  try {
    localStorage.setItem(assistantModelStorageKey(), id);
  } catch {
    /* quota / private mode */
  }
}

const BASE_PROMPTS = [
  "What's my revenue this week?",
  "Show me overdue follow-ups",
  "Draft a promo broadcast for my VIP customers",
  "Which orders are still pending?",
  "Help me set up a Facebook ad campaign",
  "Automate follow-ups for customers who haven't replied in 3 days",
  "Who are my top customers this month?",
  "Generate a sales report as a PDF",
  "Which products are low on stock?",
  "Create an invoice for a customer",
  "How is my team performing this month?",
  "Draft a quote for a new customer",
  "Show me my customer satisfaction insights",
  "Which customers haven't bought in 60+ days?",
  "Help me write a loyalty reward message",
  "Schedule a WhatsApp check-in with my top 5 customers",
];

export default function AssistantChat({ conversationId, onConversationChange, compact, initialMessage }: Props) {
  const [models, setModels] = useState<AssistantModel[]>([]);
  const [modelId, setModelId] = useState<string>("");
  /** Last resolved agent id (for specialist persona badge). */
  const [activeAgent, setActiveAgent] = useState<string>("general");
  const [connectedIntegrations, setConnectedIntegrations] = useState<string[]>([]);
  const [quickPrompts, setQuickPrompts] = useState<string[]>(BASE_PROMPTS.slice(0, 8));
  const [promptsPersonalized, setPromptsPersonalized] = useState(false);
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState(initialMessage ?? "");
  const [sending, setSending] = useState(false);
  const [loadingConv, setLoadingConv] = useState(false);
  // Streaming state
  const [streamingText, setStreamingText] = useState("");
  const [streamingTools, setStreamingTools] = useState<string[]>([]);
  /** Agent id from stream "thinking" event — drives named specialist label while waiting. */
  const [streamingAgentId, setStreamingAgentId] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<
    null | { tool: string; arguments: Record<string, unknown>; reason: string }
  >(null);
  const [convId, setConvId] = useState<string | null>(conversationId ?? null);
  const [convVisibility, setConvVisibility] = useState<"team" | "private">("team");
  const [shareOpen, setShareOpen] = useState(false);
  const [shareMembers, setShareMembers] = useState<TeamMember[]>([]);
  const [sharePick, setSharePick] = useState<string[]>([]);
  const [shareBusy, setShareBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<AssistantDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const streamReaderRef = useRef<ReadableStreamDefaultReader<string> | null>(null);

  useEffect(() => {
    assistantApi
      .models()
      .then((r) => {
        const list = sanitizeAssistantModels(r.models ?? []);
        setModels(list);
        const fallback =
          r.default && list.some((m) => m.id === r.default) ? r.default : list[0]?.id || "";
        const stored = readPersistedAssistantModelId();
        const picked = pickAssistantModelId(stored ?? undefined, list, fallback);
        setModelId(picked);
        if (stored && picked !== stored) persistAssistantModelId(picked);
      })
      .catch((err: unknown) => {
        const detail = err instanceof Error && err.message ? err.message : "Could not reach the CRM API.";
        setError(
          `${detail} If the API is running, restart the backend after changing .env, confirm NEXT_PUBLIC_API_URL matches it, and set at least one key: OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, or GROK_API_KEY.`,
        );
      });

    // Load personalized suggestions in background — chips already visible with BASE_PROMPTS
    assistantApi
      .suggestions()
      .then((r) => {
        if (r.suggestions && r.suggestions.length >= 4) {
          setQuickPrompts(r.suggestions.slice(0, 8));
          setPromptsPersonalized(r.personalized ?? false);
        }
      })
      .catch(() => {
        // Keep BASE_PROMPTS fallback already set in initial state
      });

    // Also load connected integrations (still used for secondary extras)
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (token) {
      const integrationIds = "shopify,stripe,klaviyo,mailchimp,brevo,slack,google-mail,microsoft,google-calendar";
      fetch(`/api/nango/connections?integrations=${integrationIds}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((d: { connected?: Record<string, boolean> }) => {
          const nango = d.connected ?? {};
          const map: Record<string, string> = {
            "google-mail": "gmail",
            "google-calendar": "google_calendar",
          };
          const active = Object.entries(nango)
            .filter(([, v]) => v)
            .map(([k]) => map[k] ?? k);
          setConnectedIntegrations(active);
        })
        .catch(() => { });
    }
  }, []);

  /** Keep `<select>` value in sync when the API drops old model ids (e.g. Opus 4.6). */
  useEffect(() => {
    if (!models.length || !modelId) return;
    const fallback = models[0]?.id || "";
    const next = pickAssistantModelId(modelId, models, fallback);
    if (next !== modelId) {
      setModelId(next);
      persistAssistantModelId(next);
    }
  }, [models, modelId]);

  const loadConversation = useCallback(async (id: string) => {
    setLoadingConv(true);
    try {
      const conv: AssistantConversation = await assistantApi.getConversation(id);
      const msgs = conv.messages || [];
      setMessages(msgs);
      setConvVisibility(conv.visibility === "private" ? "private" : "team");
      // Model choice persists via localStorage; do not override with conv.model when switching threads.
      const lastAsst = [...msgs].reverse().find((m) => m.role === "assistant" && m.agent);
      if (lastAsst?.agent) setActiveAgent(lastAsst.agent);
      else setActiveAgent("general");
      const docs = await assistantApi.listDocuments(id).catch(() => ({ documents: [] }));
      setDocuments(docs.documents || []);
    } catch {
      setError("Could not load that conversation");
    } finally {
      setLoadingConv(false);
    }
  }, []);

  useEffect(() => {
    if (!shareOpen) return;
    const u = getUser();
    const myId = u?._id as string | undefined;
    teamApi
      .list()
      .then((list) => {
        const withLogin = (list || []).filter((m) => m.user_id && m.user_id !== myId);
        setShareMembers(withLogin);
      })
      .catch(() => setShareMembers([]));
  }, [shareOpen]);

  async function submitShare() {
    if (!convId || !sharePick.length) return;
    setShareBusy(true);
    try {
      await assistantApi.shareConversation(convId, sharePick);
      setConvVisibility("private");
      setShareOpen(false);
      setSharePick([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Share failed");
    } finally {
      setShareBusy(false);
    }
  }

  async function onFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setError(null);
    setUploading(true);
    try {
      const res = await assistantApi.uploadDocument(file, convId);
      if (!convId) {
        setConvId(res.conversation_id);
        onConversationChange?.(res.conversation_id);
      }
      setDocuments((prev) => [...prev, res.document]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function removeDocument(docId: string) {
    try {
      await assistantApi.deleteDocument(docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch {
      /* ignore */
    }
  }

  // Load conversation once on mount (or when the id prop changes).
  // We intentionally do NOT include convId so the check "!== convId" doesn't
  // prevent loading when the component remounts with the same id.
  useEffect(() => {
    if (!conversationId) return;
    setConvId(conversationId);
    void loadConversation(conversationId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function send(messageOverride?: string, autoApprove = false) {
    const msg = (messageOverride ?? input).trim();
    if (!msg || sending) return;
    setInput("");
    setError(null);
    setSending(true);
    setStreamingText("");
    setStreamingTools([]);
    setStreamingAgentId(null);

    // Optimistic user bubble
    setMessages((prev) => [...prev, { role: "user", content: msg }]);

    // Cancel any previous stream
    if (streamReaderRef.current) {
      try { await streamReaderRef.current.cancel(); } catch { /* ignore */ }
      streamReaderRef.current = null;
    }

    try {
      const stream = assistantApi.chatStream({
        message: msg,
        conversation_id: convId,
        model: modelId || undefined,
        auto_approve: autoApprove,
      });
      const reader = stream.getReader();
      streamReaderRef.current = reader;

      let fullReply = "";
      let donePayload: AssistantChatResponse | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        try {
          const event = JSON.parse(value) as {
            type: string;
            text?: string;
            tool?: string;
            agent?: string;
            agent_label?: string;
            reply?: string;
            steps?: AssistantStep[];
            model?: string | null;
            needs_confirmation?: null | { tool: string; arguments: Record<string, unknown>; reason: string };
            active_agent?: string;
            active_agent_label?: string;
            reply_suggestions?: string[];
            conversation_id?: string;
            message?: string;
          };

          if (event.type === "thinking") {
            if (event.agent) setStreamingAgentId(event.agent);
          } else if (event.type === "tool_start") {
            setStreamingTools((prev) => [...prev, event.tool ?? ""]);
          } else if (event.type === "token") {
            fullReply += event.text ?? "";
            setStreamingText(fullReply);
          } else if (event.type === "done") {
            donePayload = {
              conversation_id: event.conversation_id ?? convId ?? "",
              reply: event.reply ?? fullReply,
              steps: event.steps ?? [],
              model: event.model ?? null,
              needs_confirmation: event.needs_confirmation ?? null,
              active_agent: event.active_agent ?? "general",
              active_agent_label: event.active_agent_label ?? "Zilo",
              reply_suggestions: event.reply_suggestions,
            };
          } else if (event.type === "error") {
            throw new Error(event.message ?? "Stream error");
          }
        } catch (parseErr) {
          // Non-JSON line — skip
        }
      }

      if (donePayload) {
        if (!convId) {
          setConvId(donePayload.conversation_id);
          onConversationChange?.(donePayload.conversation_id);
        }
        if (donePayload.active_agent) setActiveAgent(donePayload.active_agent);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: donePayload!.reply,
            steps: donePayload!.steps,
            agent: donePayload!.active_agent,
            suggestions: donePayload!.reply_suggestions?.length ? donePayload!.reply_suggestions : undefined,
          },
        ]);
        setPendingConfirm(donePayload.needs_confirmation || null);
      } else if (fullReply) {
        // Stream ended without a done event — use accumulated text
        setMessages((prev) => [...prev, { role: "assistant", content: fullReply }]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send");
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setSending(false);
      setStreamingText("");
      setStreamingTools([]);
      setStreamingAgentId(null);
      streamReaderRef.current = null;
    }
  }

  // Merge integration-specific extras into the personalized prompts (keep max 8)
  const mergedPrompts = (() => {
    const extras: string[] = [];
    for (const key of connectedIntegrations) {
      const pool = INTEGRATION_PROMPTS[key];
      if (pool) extras.push(pool[0]);
    }
    if (!extras.length) return quickPrompts.slice(0, 8);
    const base = quickPrompts.slice(0, Math.max(4, 8 - extras.length));
    return [...base, ...extras].slice(0, 8);
  })();

  const empty = messages.length === 0 && !loadingConv;
  const headerPersona = getAgentPersona(activeAgent);

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 bg-white/80 px-4 py-2.5 backdrop-blur">
        <div className="flex items-center gap-1">
          <ZiloLogo size={28} className="shrink-0" />
          <div>
            <div className="text-sm font-semibold text-slate-900">Zilo Chat</div>
            <div className="text-[10px] text-slate-400">
              {compact ? "Ask me anything" : "Named specialists for each area — Zilo picks who fits best"}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Which named specialist is active (router picks; user always sees a person + specialty). */}
          <span
            className={`inline-flex max-w-[14rem] items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${headerPersona.cls}`}
            title={
              activeAgent === "general"
                ? "Zilo is your main guide. A named specialist will join when your question needs one."
                : `${headerPersona.firstName} — ${headerPersona.role}. Zilo chose this expert for this part of the chat.`
            }
          >
            <Bot size={10} />
            <span className="truncate">{personaBadgeLabel(activeAgent)}</span>
          </span>
          {convId ? (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                convVisibility === "private"
                  ? "bg-amber-100 text-amber-800"
                  : "bg-slate-100 text-slate-600"
              }`}
              title={convVisibility === "private" ? "Only invited teammates see this thread" : "Visible to everyone on your business account"}
            >
              {convVisibility === "private" ? "Private" : "Team"}
            </span>
          ) : null}
          {convId ? (
            <button
              type="button"
              onClick={() => setShareOpen(true)}
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-[10.5px] text-slate-600 hover:border-brand/50 hover:text-brand-dark"
              title="Invite teammates to this chat"
            >
              <UserPlus size={11} /> Share
            </button>
          ) : null}
          {!compact && (
            <Link
              href="/dashboard/assistant/audit"
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-[10.5px] text-slate-500 hover:border-brand/50 hover:text-brand-dark"
              title="View audit log"
            >
              <ShieldCheck size={11} /> Audit
            </Link>
          )}
          <select
            value={modelId}
            onChange={(e) => {
              const v = e.target.value;
              setModelId(v);
              persistAssistantModelId(v);
            }}
            disabled={!models.length}
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 focus:outline-none disabled:opacity-50"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
            {!models.length && <option>No models</option>}
          </select>
        </div>
      </div>

      {shareOpen ? (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Share chat"
        >
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-5 shadow-xl">
            <h3 className="text-sm font-semibold text-slate-900">Share this Zilo chat</h3>
            <p className="mt-1 text-xs text-slate-500">
              Selected teammates can open this thread. The chat becomes private to you and invited people.
            </p>
            <div className="mt-4 max-h-48 space-y-2 overflow-y-auto">
              {shareMembers.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No teammates with a web login yet. Add people under Team, then share again.
                </p>
              ) : (
                shareMembers.map((m) => (
                  <label key={m.id} className="flex cursor-pointer items-center gap-2 text-sm text-slate-800">
                    <input
                      type="checkbox"
                      className="rounded border-slate-300"
                      checked={sharePick.includes(m.user_id!)}
                      onChange={(e) => {
                        const id = m.user_id!;
                        if (e.target.checked) setSharePick((p) => [...p, id]);
                        else setSharePick((p) => p.filter((x) => x !== id));
                      }}
                    />
                    <span>{m.name}</span>
                    <span className="text-xs text-slate-400">({m.role})</span>
                  </label>
                ))
              )}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                onClick={() => {
                  setShareOpen(false);
                  setSharePick([]);
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={shareBusy || !sharePick.length}
                className="rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-dark disabled:opacity-40"
                onClick={() => void submitShare()}
              >
                {shareBusy ? "Sharing…" : "Share"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Messages — centered ChatGPT/Claude column */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          {empty ? (
            <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
              <ZiloLogo size={56} className="shrink-0" />
              <div>
                <p className="text-2xl font-semibold text-slate-900">How can I help today?</p>
                <p className="mx-auto mt-2 max-w-lg text-sm text-slate-500">
                  Ask anything — I&apos;ll bring in the right context and tools as we go. Attach a document and I&apos;ll read it with you.
                </p>
              </div>

              {/* Suggestions header with personalized badge */}
              <div className="flex w-full max-w-2xl items-center justify-between px-0.5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  {promptsPersonalized ? "Suggested for you" : "Quick start"}
                </p>
                {promptsPersonalized && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-semibold text-brand-dark">
                    <svg viewBox="0 0 10 10" className="h-2.5 w-2.5 fill-current"><circle cx="5" cy="5" r="5" /></svg>
                    Personalized
                  </span>
                )}
              </div>

              {/* Suggestion chips — skeleton while loading */}
              <div className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
                {loadingPrompts
                  ? Array.from({ length: 8 }).map((_, i) => (
                      <div
                        key={i}
                        className="h-11 animate-pulse rounded-xl border border-slate-100 bg-slate-100"
                      />
                    ))
                  : mergedPrompts.map((p) => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => void send(p)}
                        className="rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-left text-sm text-slate-700 shadow-sm transition hover:border-brand/50 hover:bg-brand/10 hover:shadow"
                      >
                        {p}
                      </button>
                    ))}
              </div>
              <div className="flex items-center gap-2 text-[11px] text-slate-400">
                <Paperclip size={11} /> Click the paperclip below to attach a PDF, DOCX, or image.
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((m, i) => {
                // Detect agent switch: show a subtle transition divider before the new assistant message
                const prevAsst = messages.slice(0, i).reverse().find((x) => x.role === "assistant");
                const agentChanged =
                  m.role === "assistant" &&
                  m.agent &&
                  prevAsst?.agent &&
                  m.agent !== prevAsst.agent;
                return (
                  <React.Fragment key={i}>
                    {agentChanged && m.agent && (
                      <div className="flex items-center gap-2 py-1">
                        <div className="h-px flex-1 bg-slate-100" />
                        <span
                          className={`inline-flex max-w-[min(100%,20rem)] items-center gap-1 rounded-full px-2 py-0.5 text-center text-[10px] font-medium ${getAgentPersona(m.agent).cls}`}
                          title={getAgentPersona(m.agent).role}
                        >
                          <Bot size={9} />
                          <span className="truncate">{personaHandoffLine(m.agent)}</span>
                        </span>
                        <div className="h-px flex-1 bg-slate-100" />
                      </div>
                    )}
                    <MessageBubble
                      msg={m}
                      onSuggestionSend={(text) => void send(text)}
                      onUserResend={
                        m.role === "user"
                          ? (editedText) => {
                              setMessages((prev) => prev.slice(0, i));
                              void send(editedText);
                            }
                          : undefined
                      }
                    />
                  </React.Fragment>
                );
              })}
              {sending && (
                <div className="flex items-start gap-3">
                  <ZiloLogo size={28} className="mt-1 shrink-0 self-start" />
                  <div className="min-w-0 flex-1 space-y-2">
                    {/* Tool activity badges */}
                    {streamingTools.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {streamingTools.map((tool, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600 animate-pulse"
                          >
                            <Loader2 size={10} className="animate-spin text-brand" />
                            {friendlyToolLabel(tool)}
                          </span>
                        ))}
                      </div>
                    )}
                    {/* Video rendering skeleton — shown while Kling is generating */}
                    {streamingTools.some(t => t === "create_kling_video" || t === "get_kling_video_status" || t === "create_video" || t === "get_video_status") && (
                      <VideoRenderingCard />
                    )}
                    {/* Streaming reply text */}
                    {streamingText ? (
                      <div className="text-[14px] leading-relaxed text-slate-800">
                        <MarkdownBody content={streamingText} />
                        <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-slate-400" />
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-xs text-slate-400">
                        <Loader2 className="animate-spin" size={12} />
                        {streamingAgentId ? (
                          <span title={getAgentPersona(streamingAgentId).role}>
                            <span
                              className={`mr-1 inline-flex max-w-[18rem] items-center gap-0.5 truncate rounded-full px-1.5 py-px text-[9px] font-semibold ${getAgentPersona(streamingAgentId).cls}`}
                            >
                              <Bot size={8} />
                              {personaThinkingLabel(streamingAgentId)}
                            </span>
                            is thinking…
                          </span>
                        ) : (
                          "Zilo is thinking…"
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Confirmation banner */}
      {pendingConfirm && (
        <div className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
          <div className="mb-1 flex items-center gap-1.5 font-semibold">
            <AlertTriangle size={12} /> Confirm {pendingConfirm.tool}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void send("yes", true)}
              className="flex items-center gap-1 rounded-md bg-green-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-green-700"
            >
              <CheckCircle2 size={11} /> Yes, do it
            </button>
            <button
              type="button"
              onClick={() => setPendingConfirm(null)}
              className="rounded-md border border-amber-300 bg-white px-2.5 py-1 text-[11px] font-semibold text-amber-900 hover:bg-amber-100"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</div>
      )}

      {/* Composer — centered Claude/ChatGPT-style pill */}
      <div className="border-t border-slate-100 bg-gradient-to-b from-white to-slate-50/40">
        <div className="mx-auto w-full max-w-3xl px-4 pb-4 pt-3">
          {/* Attachment chips */}
          {documents.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {documents.map((d) => (
                <div
                  key={d.id}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-700 shadow-sm"
                  title={`${d.filename} · ${d.kind.toUpperCase()} · ${Math.round(d.size / 1024)} KB`}
                >
                  {d.kind === "image" ? (
                    <ImageIcon size={11} className="text-brand" />
                  ) : (
                    <FileText size={11} className="text-brand" />
                  )}
                  <span className="max-w-[180px] truncate">{d.filename}</span>
                  <button
                    type="button"
                    onClick={() => void removeDocument(d.id)}
                    className="text-slate-400 hover:text-red-600"
                    aria-label="Remove attachment"
                  >
                    <XIcon size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
            className="flex items-end gap-2 rounded-3xl border border-slate-200 bg-white px-2.5 py-2 shadow-[0_2px_14px_rgba(15,23,42,0.06)] focus-within:border-brand/50 focus-within:shadow-[0_2px_18px_rgba(99,102,241,0.12)]"
          >
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".pdf,.docx,.txt,.md,.csv,image/png,image/jpeg,image/webp,image/gif"
              onChange={onFilePicked}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-brand-dark disabled:opacity-50"
              aria-label="Attach document"
              title="Attach PDF, DOCX, TXT, CSV, or image"
            >
              {uploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
            </button>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              rows={1}
              placeholder={
                documents.length > 0
                  ? "Ask a question about the attached document…"
                  : "Message Zilo Chat…"
              }
              className="max-h-40 flex-1 resize-none bg-transparent px-1 py-2 text-[14px] text-slate-900 placeholder:text-slate-400 focus:outline-none"
            />
            <button
              type="submit"
              disabled={!input.trim() || sending}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white transition hover:bg-brand disabled:bg-slate-200 disabled:text-slate-400"
              aria-label="Send"
            >
              {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </button>
          </form>
          <p className="mt-2 text-center text-[10.5px] text-slate-400">
            Zilo brings in a named specialist for the task (e.g. Elena for Meta Ads, Stephen for sales). You&apos;ll confirm anything sensitive before it runs.
          </p>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// WhatsApp customer picker modal
// ─────────────────────────────────────────────────────────────────────────────
function WhatsAppPickerModal({
  content,
  onClose,
}: {
  content: string;
  onClose: () => void;
}) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    customersApi.list().then((list) => {
      setCustomers(list.filter((c) => c.phone_number));
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const filtered = customers.filter(
    (c) =>
      c.name.toLowerCase().includes(query.toLowerCase()) ||
      c.phone_number.includes(query)
  );

  async function handleSend(customer: Customer) {
    if (sending || sent === customer.id) return;
    setSending(customer.id);
    setError("");
    try {
      await messagesApi.send(customer.phone_number, content, customer.name);
      setSent(customer.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Send failed");
    } finally {
      setSending(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-green-100">
              <MessageCircle size={15} className="text-green-600" />
            </div>
            <div>
              <p className="text-[13px] font-semibold text-slate-800">Send via WhatsApp</p>
              <p className="text-[10.5px] text-slate-400">Choose a customer to send this reply to</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <XIcon size={15} />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 pt-3 pb-2">
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <Search size={13} className="shrink-0 text-slate-400" />
            <input
              autoFocus
              placeholder="Search by name or phone…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1 bg-transparent text-[13px] text-slate-800 placeholder-slate-400 outline-none"
            />
          </div>
        </div>

        {/* Customer list */}
        <div className="max-h-72 overflow-y-auto px-2 pb-3">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 size={16} className="animate-spin text-slate-300" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="py-8 text-center text-[12px] text-slate-400">No customers found</p>
          ) : (
            filtered.map((c) => {
              const isSent = sent === c.id;
              const isSending = sending === c.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => void handleSend(c)}
                  disabled={isSending || isSent}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-slate-50 disabled:opacity-70"
                >
                  {/* Avatar */}
                  {c.profile_picture ? (
                    <img src={c.profile_picture} alt="" className="h-8 w-8 rounded-full object-cover" />
                  ) : (
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand/15 text-[12px] font-semibold text-brand-dark">
                      {c.name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-slate-800">{c.name}</p>
                    <p className="text-[11px] text-slate-400">{c.phone_number}</p>
                  </div>
                  <div className="shrink-0">
                    {isSending ? (
                      <Loader2 size={14} className="animate-spin text-green-500" />
                    ) : isSent ? (
                      <CheckCheck size={14} className="text-green-500" />
                    ) : (
                      <MessageCircle size={14} className="text-slate-300 group-hover:text-green-500" />
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Error */}
        {error && (
          <p className="border-t border-slate-100 px-5 py-3 text-[11.5px] text-red-500">{error}</p>
        )}
      </div>
    </div>
  );
}

/**
 * Finds the LAST contiguous option list (≥ 2 items in the same format) in an assistant
 * message and returns the markdown before it, the markdown after it, and the parsed
 * options. Recognises three formats (whichever the model used):
 *   • bullet + bold:    `- **Label** — description`
 *   • lettered:         `A. text` / `A) text` / `(A) text` / `- A. text`
 *   • numbered:         `1. text` / `2) text` / `- 1. text`
 * The list does NOT have to sit at the very end — trailing prose ("👇 tap one") is kept
 * and rendered after the chip row. The click payload is the meaningful text only
 * (bold label or item text without the letter/number prefix).
 */
const MULTI_SELECT_RE =
  /\b(select all that apply|choose one or more|pick any|you can select multiple|select as many|tick all|check all that apply|pick all|you may select more than one)\b/i;

function extractInlineOptionList(content: string):
  | { before: string; after: string; options: { label: string; display: string }[]; multiSelect: boolean }
  | null {
  if (!content) return null;
  const lines = content.split("\n");

  const bulletRe = /^\s*[-*+]\s+\S/;
  const letterAnyRe = /^\s*(?:[-*+]\s+)?\(?[A-Za-z][.):\]]\s+\S/;
  const numberAnyRe = /^\s*(?:[-*+]\s+)?\(?\d{1,2}[.):\]]\s+\S/;
  const isOptionLine = (s: string) =>
    bulletRe.test(s) || letterAnyRe.test(s) || numberAnyRe.test(s);

  // Find the LAST run of ≥ 2 option lines anywhere in the message. Blank lines
  // within a run are allowed as long as the next non-blank line is also an option
  // line — this merges multi-paragraph option lists (e.g. 3 templates + a blank
  // line + 2 meta options like "See more / Surprise me") into a single chip set.
  let bestStart = -1;
  let bestEnd = -1;
  let i = 0;
  while (i < lines.length) {
    if (!isOptionLine(lines[i])) { i++; continue; }
    let j = i + 1;
    let lastOption = i;
    while (j < lines.length) {
      if (isOptionLine(lines[j])) { lastOption = j; j++; continue; }
      if (!lines[j].trim()) {
        let k = j + 1;
        while (k < lines.length && !lines[k].trim()) k++;
        if (k < lines.length && isOptionLine(lines[k])) { j = k; continue; }
      }
      break;
    }
    if (lastOption - i + 1 >= 2) {
      // Count actual option lines (skip blanks merged into the run).
      let count = 0;
      for (let p = i; p <= lastOption; p++) if (isOptionLine(lines[p])) count++;
      if (count >= 2) { bestStart = i; bestEnd = lastOption; }
    }
    i = lastOption + 1;
  }
  if (bestStart < 0) return null;

  // Keep only the option lines themselves (drop interleaved blanks before parsing).
  const optionLines = lines
    .slice(bestStart, bestEnd + 1)
    .filter((ln) => ln.trim() && isOptionLine(ln));
  const stripMd = (s: string) =>
    s.replace(/\*\*([^*]+?)\*\*/g, "$1").replace(/__([^_]+?)__/g, "$1").trim();

  // Try bold-bullet first (richest pattern).
  const boldRe = /^\s*[-*+]\s+(?:[^A-Za-z0-9*\s][^A-Za-z0-9*]*\s*)?\*\*([^*]+?)\*\*/;
  const boldParsed: { label: string; display: string }[] = [];
  let boldOk = true;
  for (const ln of optionLines) {
    const m = boldRe.exec(ln);
    if (!m || !m[1].trim()) { boldOk = false; break; }
    boldParsed.push({
      label: m[1].trim(),
      display: stripMd(ln.replace(/^\s*[-*+]\s+/, "")),
    });
  }
  let parsed: { label: string; display: string }[] | null =
    boldOk && boldParsed.length >= 2 ? boldParsed : null;

  // Then lettered (A. / A) / (A))
  if (!parsed) {
    const letterRe = /^\s*(?:[-*+]\s+)?\(?([A-Za-z])[.):\]]\s+(.+)$/;
    const letterParsed: { label: string; display: string }[] = [];
    let ok = true;
    for (const ln of optionLines) {
      const m = letterRe.exec(ln);
      const text = m ? m[2].trim() : "";
      if (!m || !text) { ok = false; break; }
      letterParsed.push({
        label: stripMd(text),
        display: stripMd(ln.replace(/^\s*[-*+]\s+/, "")),
      });
    }
    if (ok && letterParsed.length >= 2) parsed = letterParsed;
  }

  // Then numbered (1. / 1) / (1))
  if (!parsed) {
    const numRe = /^\s*(?:[-*+]\s+)?\(?(\d{1,2})[.):\]]\s+(.+)$/;
    const numParsed: { label: string; display: string }[] = [];
    let ok = true;
    for (const ln of optionLines) {
      const m = numRe.exec(ln);
      const text = m ? m[2].trim() : "";
      if (!m || !text) { ok = false; break; }
      numParsed.push({
        label: stripMd(text),
        display: stripMd(ln.replace(/^\s*[-*+]\s+/, "")),
      });
    }
    if (ok && numParsed.length >= 2) parsed = numParsed;
  }

  if (!parsed || parsed.length > 10) return null;

  // ── Informational-list guard ────────────────────────────────────────────────
  // Only promote to clickable chips when items look like genuine user choices.
  // Informational lists (facts, summaries, confirmations) stay as plain markdown.
  const isFactItem = (label: string, display?: string) => {
    const plain = label.replace(/\*\*/g, "").trim();
    // "Key: value" or "Key — value" patterns (e.g. "Duration: 2 weeks", "Budget: KES 500")
    if (/^[A-Za-z][^:]{0,35}:\s+\S/.test(plain)) return true;
    // "Key — value" patterns (e.g. "Duration — 2 weeks") — but NOT "A — Title" (single-letter option labels)
    { const m = /^([A-Za-z][^—]{0,35})—\s+\S/.exec(plain); if (m && m[1].trim().length > 1) return true; }
    // Starts with a quote (e.g. Message Preview: "Hello...")
    if (/^["'"']/.test(plain)) return true;
    // Very long labels (>55 chars) are descriptions, not action chips
    if (plain.length > 55) return true;
    // Contains currency/numbers suggesting it's a data point
    if (/\b(KES|USD|EUR|GBP|\$|€|£)\s*[\d,]+/.test(plain)) return true;
    // Short labels like "A.", "B.", "1." come from bold-letter patterns in concept pitches.
    // Check the full display text — if it's long or contains "key: value" patterns it's a description.
    if (plain.length <= 3 && display) {
      const plainDisplay = display.replace(/\*\*/g, "").trim();
      if (plainDisplay.length > 55) return true;
      if (/^[A-Za-z0-9][^:]{0,35}:\s+\S/.test(plainDisplay)) return true;
    }
    return false;
  };
  const factCount = parsed.filter((o) => isFactItem(o.label, o.display)).length;
  // If more than half are facts, don't promote to chips
  if (factCount > parsed.length / 2) return null;

  // If the message reads as a confirmation/summary (saved, created, updated, etc.)
  // never show chips — it's a report, not a choice prompt
  const lowerContent = content.toLowerCase();
  const isConfirmation =
    /\b(successfully saved|has been saved|successfully created|has been created|successfully updated|campaign saved|draft saved|order saved|has been scheduled)\b/.test(lowerContent);
  if (isConfirmation) return null;

  let beforeEnd = bestStart;
  while (beforeEnd > 0 && !lines[beforeEnd - 1].trim()) beforeEnd--;
  const before = lines.slice(0, beforeEnd).join("\n").replace(/\s+$/, "");

  let afterStart = bestEnd + 1;
  while (afterStart < lines.length && !lines[afterStart].trim()) afterStart++;
  const after = lines.slice(afterStart).join("\n").replace(/^\s+|\s+$/g, "");

  const multiSelect = MULTI_SELECT_RE.test(content);
  return { before, after, options: parsed, multiSelect };
}


// ── Inline form ──────────────────────────────────────────────────────────────
// The AI embeds a fenced JSON block: :::form\n{...}\n:::
// We parse it out, render real input fields, and submit the answers back.

interface FormField {
  id: string;
  label: string;
  placeholder?: string;
  type?: "text" | "number" | "textarea";
  unit?: string;
}

interface InlineFormDef {
  title?: string;
  fields: FormField[];
  before: string;  // content before the :::form block
  after: string;   // content after the :::form block
}

function extractInlineForm(content: string): InlineFormDef | null {
  if (!content) return null;
  const match = content.match(/^([\s\S]*?):::form\s*\n([\s\S]*?)\n:::([\s\S]*)$/m);
  if (!match) return null;
  try {
    const parsed = JSON.parse(match[2]);
    if (!Array.isArray(parsed.fields) || parsed.fields.length === 0) return null;
    return {
      title: parsed.title ?? undefined,
      fields: parsed.fields,
      before: match[1].trim(),
      after: match[3].trim(),
    };
  } catch {
    return null;
  }
}

function InlineForm({
  form,
  onSubmit,
}: {
  form: InlineFormDef;
  onSubmit: (text: string) => void;
}) {
  const [values, setValues] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(form.fields.map((f) => [f.id, ""]))
  );
  const [submitted, setSubmitted] = React.useState(false);

  const handleSubmit = () => {
    const lines = form.fields
      .map((f) => {
        const v = (values[f.id] ?? "").trim();
        return `${f.label}: ${v || "—"}`;
      })
      .join("\n");
    onSubmit(lines);
    setSubmitted(true);
  };

  const allFilled = form.fields.every((f) => (values[f.id] ?? "").trim() !== "");

  if (submitted) {
    return (
      <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[13px] text-slate-500">
        ✓ Answers submitted
      </div>
    );
  }

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-brand/25 bg-white shadow-sm">
      {form.title && (
        <div className="border-b border-brand/15 bg-brand/5 px-4 py-2.5 text-[12px] font-semibold text-brand-dark">
          {form.title}
        </div>
      )}
      <div className="divide-y divide-slate-100">
        {form.fields.map((f) => (
          <div key={f.id} className="flex items-start gap-3 px-4 py-2.5">
            <label className="w-40 shrink-0 pt-1.5 text-[12px] font-medium leading-snug text-slate-600">
              {f.label}
              {f.unit && <span className="ml-1 text-slate-400">({f.unit})</span>}
            </label>
            {f.type === "textarea" ? (
              <textarea
                rows={2}
                value={values[f.id] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.id]: e.target.value }))}
                placeholder={f.placeholder ?? ""}
                className="flex-1 resize-none rounded-lg border border-slate-200 px-2.5 py-1.5 text-[13px] text-slate-800 outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
              />
            ) : (
              <input
                type={f.type === "number" ? "number" : "text"}
                value={values[f.id] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.id]: e.target.value }))}
                placeholder={f.placeholder ?? ""}
                className="flex-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[13px] text-slate-800 outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
              />
            )}
          </div>
        ))}
      </div>
      <div className="flex justify-end border-t border-slate-100 px-4 py-2.5">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!allFilled}
          className="rounded-xl bg-brand px-5 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:bg-brand-dark disabled:opacity-40"
        >
          Submit answers
        </button>
      </div>
    </div>
  );
}

function MessageBubble({
  msg,
  onSuggestionSend,
  onUserResend,
}: {
  msg: AssistantMessage;
  onSuggestionSend?: (text: string) => void;
  onUserResend?: (text: string) => void;
}) {
  const [exporting, setExporting] = useState<"pdf" | "docx" | null>(null);
  const [showWaPicker, setShowWaPicker] = useState(false);
  const [editingUserPrompt, setEditingUserPrompt] = useState(false);
  const [editedUserPrompt, setEditedUserPrompt] = useState(msg.content ?? "");
  const [checkedOptions, setCheckedOptions] = useState<Set<string>>(new Set());

  // Inline form — takes priority over chip options when detected
  const inlineForm = useMemo(() => {
    if (msg.role !== "assistant") return null;
    return extractInlineForm(msg.content ?? "");
  }, [msg.role, msg.content]);

  // Promote bullet/lettered/numbered option lists to tap-to-send chips with A/B/C
  // letter badges, unless the backend already supplied msg.suggestions (avoid dupes)
  // or we're rendering a form instead.
  const inlineOptions = useMemo(() => {
    if (msg.role !== "assistant") return null;
    if (inlineForm) return null;
    if (msg.suggestions && msg.suggestions.length > 0) return null;
    return extractInlineOptionList(msg.content ?? "");
  }, [msg.role, msg.content, msg.suggestions, inlineForm]);

  async function handleExport(format: "pdf" | "docx") {
    if (!msg.content || exporting) return;
    setExporting(format);
    try {
      // Derive a filename from the first heading or first line
      const firstLine = msg.content.split("\n").find((l) => l.trim())?.replace(/^#+\s*/, "") ?? "zilo-export";
      await assistantApi.exportDocument(msg.content, format, firstLine.slice(0, 60));
    } catch (e) {
      alert(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(null);
    }
  }

  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] space-y-1.5">
          {editingUserPrompt ? (
            <div className="rounded-2xl rounded-br-md border border-slate-200 bg-white p-2.5 shadow-sm">
              <textarea
                value={editedUserPrompt}
                onChange={(e) => setEditedUserPrompt(e.target.value)}
                rows={3}
                className="w-full resize-y rounded-lg border border-slate-200 px-2.5 py-2 text-[13px] text-slate-900 focus:border-brand/50 focus:outline-none"
              />
              <div className="mt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setEditingUserPrompt(false);
                    setEditedUserPrompt(msg.content ?? "");
                  }}
                  className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!editedUserPrompt.trim() || !onUserResend}
                  onClick={() => {
                    if (!onUserResend || !editedUserPrompt.trim()) return;
                    setEditingUserPrompt(false);
                    onUserResend(editedUserPrompt.trim());
                  }}
                  className="rounded-md bg-brand px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
                >
                  Resend
                </button>
              </div>
            </div>
          ) : (
            <div className="whitespace-pre-wrap rounded-2xl rounded-br-md bg-slate-100 px-4 py-2.5 text-[14px] text-slate-900">
              {msg.content}
            </div>
          )}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => {
                setEditedUserPrompt(msg.content ?? "");
                setEditingUserPrompt((v) => !v);
              }}
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-medium text-slate-500 hover:border-slate-300 hover:text-slate-700"
            >
              <PencilLine size={9} />
              Edit & resend
            </button>
          </div>
        </div>
      </div>
    );
  }
  if (msg.role === "assistant") {
    const hasContent = (msg.content ?? "").length > 80;
    return (
      <div className="flex justify-start">
        <div className="flex w-full max-w-full gap-3">
          <ZiloLogo size={28} className="mt-1 shrink-0 self-start" />
          <div className="min-w-0 flex-1 space-y-1.5">
            {msg.steps && msg.steps.length > 0 && <StepsTrail steps={msg.steps} />}
            <div className="text-[14px] leading-relaxed text-slate-800">
              {msg.content ? (
                inlineForm && onSuggestionSend ? (
                  <>
                    {inlineForm.before && <MarkdownBody content={inlineForm.before} />}
                    <InlineForm form={inlineForm} onSubmit={onSuggestionSend} />
                    {inlineForm.after && <MarkdownBody content={inlineForm.after} />}
                  </>
                ) : inlineOptions && onSuggestionSend ? (
                  <>
                    {inlineOptions.before && <MarkdownBody content={inlineOptions.before} />}
                    <div className="mt-2 flex flex-col items-stretch gap-1.5">
                      {inlineOptions.options.map((opt, i) => {
                        const letter = String.fromCharCode(65 + i);
                        if (inlineOptions.multiSelect) {
                          const checked = checkedOptions.has(opt.label);
                          return (
                            <button
                              key={`${i}-${opt.label}`}
                              type="button"
                              onClick={() =>
                                setCheckedOptions((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(opt.label)) next.delete(opt.label);
                                  else next.add(opt.label);
                                  return next;
                                })
                              }
                              className={`group flex items-center gap-2.5 rounded-xl border px-2.5 py-2 text-left text-[13px] leading-snug shadow-sm transition ${
                                checked
                                  ? "border-brand bg-brand/10 text-brand-dark"
                                  : "border-brand/30 bg-white text-brand-ink hover:border-brand hover:bg-brand/5"
                              }`}
                            >
                              <span
                                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition ${
                                  checked
                                    ? "border-brand bg-brand text-white"
                                    : "border-slate-300 bg-white group-hover:border-brand"
                                }`}
                              >
                                {checked && (
                                  <svg viewBox="0 0 10 8" className="h-3 w-3 fill-current">
                                    <path d="M1 4l3 3 5-6" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                )}
                              </span>
                              <span className="min-w-0 flex-1 break-words font-medium">{opt.display}</span>
                            </button>
                          );
                        }
                        return (
                          <button
                            key={`${i}-${opt.label}`}
                            type="button"
                            onClick={() => onSuggestionSend(opt.label)}
                            className="group flex items-center gap-2.5 rounded-xl border border-brand/30 bg-white px-2.5 py-2 text-left text-[13px] leading-snug text-brand-ink shadow-sm transition hover:border-brand hover:bg-brand/10"
                          >
                            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[12px] font-bold text-brand-dark group-hover:bg-brand group-hover:text-white">
                              {letter}
                            </span>
                            <span className="min-w-0 flex-1 break-words font-medium">{opt.display}</span>
                          </button>
                        );
                      })}
                      {inlineOptions.multiSelect && checkedOptions.size > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            const selected = inlineOptions.options
                              .filter((o) => checkedOptions.has(o.label))
                              .map((o) => o.label)
                              .join(", ");
                            onSuggestionSend(selected);
                            setCheckedOptions(new Set());
                          }}
                          className="mt-1 self-end rounded-xl bg-brand px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:bg-brand-dark"
                        >
                          Confirm ({checkedOptions.size} selected)
                        </button>
                      )}
                    </div>
                    {inlineOptions.after && (
                      <div className="mt-2">
                        <MarkdownBody content={inlineOptions.after} />
                      </div>
                    )}
                  </>
                ) : (
                  <MarkdownBody content={msg.content} />
                )
              ) : (
                <span className="italic text-slate-400">(no reply)</span>
              )}
            </div>
            <VideoPreview steps={msg.steps} />
            <DocumentPreview steps={msg.steps} />
            {msg.suggestions &&
              msg.suggestions.length > 0 &&
              onSuggestionSend && (
                <div className="mt-3 space-y-1.5">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    Suggested next step — tap to send
                  </p>
                  <div className="flex flex-col gap-2">
                    {msg.suggestions.map((chip) => (
                      <button
                        key={chip}
                        type="button"
                        onClick={() => onSuggestionSend(chip)}
                        className="rounded-xl border-2 border-brand/30 bg-white px-3.5 py-2.5 text-left text-[13px] font-medium leading-snug text-brand-ink shadow-sm transition hover:border-brand hover:bg-brand/10"
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            {hasContent && (
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <span className="text-[10px] text-slate-400">Download as</span>
                <button
                  type="button"
                  onClick={() => void handleExport("pdf")}
                  disabled={!!exporting}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-medium text-slate-600 hover:border-brand/50 hover:text-brand-dark disabled:opacity-50"
                >
                  {exporting === "pdf" ? <Loader2 size={9} className="animate-spin" /> : <Download size={9} />}
                  PDF
                </button>
                <button
                  type="button"
                  onClick={() => void handleExport("docx")}
                  disabled={!!exporting}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-medium text-slate-600 hover:border-brand/50 hover:text-brand-dark disabled:opacity-50"
                >
                  {exporting === "docx" ? <Loader2 size={9} className="animate-spin" /> : <Download size={9} />}
                  Word
                </button>
                <span className="text-[10px] text-slate-300">|</span>
                <button
                  type="button"
                  onClick={() => setShowWaPicker(true)}
                  className="inline-flex items-center gap-1 rounded-md border border-green-200 bg-white px-2 py-0.5 text-[10.5px] font-medium text-green-700 hover:bg-green-50 hover:border-green-400"
                >
                  <MessageCircle size={9} />
                  Send via WhatsApp
                </button>
              </div>
            )}
            {showWaPicker && msg.content && (
              <WhatsAppPickerModal
                content={msg.content}
                onClose={() => setShowWaPicker(false)}
              />
            )}
          </div>
        </div>
      </div>
    );
  }
  return null;
}

function MarkdownBody({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <h3 className="mb-2 mt-1 text-base font-semibold text-slate-900" {...p} />,
          h2: (p) => <h3 className="mb-2 mt-1 text-base font-semibold text-slate-900" {...p} />,
          h3: (p) => <h3 className="mb-2 mt-1 text-[15px] font-semibold text-slate-900" {...p} />,
          p: (p) => <p className="mb-2 leading-relaxed last:mb-0" {...p} />,
          ul: (p) => <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0" {...p} />,
          ol: (p) => <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0" {...p} />,
          li: (p) => <li className="leading-relaxed" {...p} />,
          strong: (p) => <strong className="font-semibold text-slate-900" {...p} />,
          em: (p) => <em className="text-slate-600" {...p} />,
          code: (p) => (
            <code
              className="rounded bg-slate-200/70 px-1 py-0.5 font-mono text-[12px] text-slate-800"
              {...p}
            />
          ),
          hr: () => <hr className="my-3 border-slate-200" />,
          a: ({ href, children, ...rest }) => {
            const isDoc = typeof href === "string" && /\.(pdf|docx|pptx)(\?|$)/i.test(href);
            if (isDoc) {
              const name = (typeof children === "string" ? children : "document").replace(/[^\w\-. ]/g, "_");
              return (
                <a
                  href={href}
                  className="text-brand-dark underline hover:text-brand-dark"
                  onClick={(e) => {
                    e.preventDefault();
                    void downloadAsset(href, name).catch(() => window.open(href, "_blank", "noopener,noreferrer"));
                  }}
                  {...rest}
                >
                  {children}
                </a>
              );
            }
            return <a href={href} className="text-brand-dark underline hover:text-brand-dark" target="_blank" rel="noreferrer" {...rest}>{children}</a>;
          },
          // ── Image: preserve aspect ratio; avoid stretched or broken previews ──
          img: ({ src, alt }) => {
            const raw = typeof src === "string" ? src.trim() : "";
            if (!raw || raw === "undefined" || raw === "null") {
              return null;
            }
            const cleanAlt = alt && alt !== "undefined" && alt !== "null" ? String(alt) : "";
            return (
              <span className="my-3 block max-w-full">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={raw}
                  alt={cleanAlt || "Image"}
                  className="h-auto w-full max-w-full rounded-xl border border-slate-200 object-contain shadow-md"
                  style={{ display: "block", maxHeight: "min(70vh, 560px)" }}
                  loading="lazy"
                  decoding="async"
                  onError={(e) => {
                    const target = e.currentTarget;
                    target.style.display = "none";
                    const link = document.createElement("a");
                    link.href = raw;
                    link.target = "_blank";
                    link.rel = "noreferrer";
                    link.textContent = "View image (open in new tab)";
                    link.className = "text-brand-dark underline text-sm";
                    target.parentNode?.appendChild(link);
                  }}
                />
                <span className="mt-1.5 flex items-center gap-2 text-[11px] text-slate-400">
                  {cleanAlt && <span>{cleanAlt}</span>}
                  <a
                    href={raw}
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand-dark underline hover:opacity-80"
                  >
                    Open full size
                  </a>
                  <button
                    type="button"
                    onClick={() => {
                      void downloadAsset(raw, cleanAlt || "design").catch(() => {
                        window.open(raw, "_blank", "noopener,noreferrer");
                      });
                    }}
                    className="inline-flex items-center gap-1 text-brand-dark underline hover:opacity-80"
                  >
                    <Download size={11} />
                    Download
                  </button>
                </span>
              </span>
            );
          },
          table: (p) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-[12.5px]" {...p} />
            </div>
          ),
          thead: (p) => <thead className="bg-slate-100 text-[11px] uppercase tracking-wide text-slate-600" {...p} />,
          th: (p) => <th className="border border-slate-200 px-2 py-1.5 text-left font-semibold" {...p} />,
          tr: (p) => <tr className="even:bg-white odd:bg-slate-50/40" {...p} />,
          td: (p) => <td className="border border-slate-200 px-2 py-1.5 align-top" {...p} />,
          blockquote: (p) => (
            <blockquote className="my-2 border-l-2 border-brand/50 bg-brand/5 px-3 py-1 text-slate-700" {...p} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function StepsTrail({ steps }: { steps: AssistantStep[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {steps.map((s, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-medium text-slate-500"
          title={s.tool}
        >
          <Wrench size={8} className="text-brand shrink-0" />
          {friendlyToolLabel(s.tool).replace(/…$/, "")}
        </span>
      ))}
    </div>
  );
}

function DocumentPreview({ steps }: { steps?: AssistantStep[] }) {
  const [collapsed, setCollapsed] = React.useState(false);
  const [wordLoading, setWordLoading] = React.useState(false);

  const docStep = useMemo(
    () =>
      [...(steps ?? [])].reverse().find(
        (s) =>
          (s.tool === "generate_document" || s.tool === "create_business_document") &&
          (s.result as Record<string, unknown>)?.html_preview,
      ),
    [steps],
  );

  if (!docStep) return null;

  const result = docStep.result as Record<string, unknown>;
  const htmlPreview = result.html_preview as string;
  const filename = (result.filename as string | undefined) ?? "document";
  const s3Url = (result.download_url ?? result.pdf_url) as string | undefined;
  const contentMd = result.content_md as string | undefined;

  /** Download as Word — reuses the existing assistantApi.exportDocument helper */
  const handleDownloadWord = async () => {
    if (!contentMd) return;
    setWordLoading(true);
    try {
      const baseName = filename.replace(/\.\w+$/, "");
      await assistantApi.exportDocument(contentMd, "docx", baseName);
    } catch (err) {
      console.error("[DocumentPreview] Word download failed", err);
    } finally {
      setWordLoading(false);
    }
  };

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 shadow-sm">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-700">
          <FileText size={13} className="text-brand shrink-0" />
          Document Preview
        </div>
        <div className="flex items-center gap-2">
          {s3Url && (
            <button
              type="button"
              onClick={() =>
                void downloadAsset(s3Url, filename).catch(() =>
                  window.open(s3Url, "_blank", "noopener,noreferrer")
                )
              }
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-medium text-slate-600 hover:border-brand/50 hover:text-brand-dark"
            >
              <Download size={10} />
              PDF
            </button>
          )}
          {contentMd && (
            <button
              type="button"
              onClick={() => void handleDownloadWord()}
              disabled={wordLoading}
              className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10.5px] font-medium text-blue-700 hover:border-blue-400 hover:bg-blue-100 disabled:opacity-50"
            >
              {wordLoading ? (
                <Loader2 size={10} className="animate-spin" />
              ) : (
                <Download size={10} />
              )}
              Word
            </button>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="text-[10.5px] font-medium text-slate-400 hover:text-slate-600"
          >
            {collapsed ? "Show" : "Hide"}
          </button>
        </div>
      </div>

      {/* Rendered document — injected via srcDoc so CSS is isolated and no fetch needed */}
      {!collapsed && (
        <iframe
          srcDoc={htmlPreview}
          title="Document Preview"
          className="w-full border-0 bg-white"
          style={{ height: "700px" }}
          sandbox="allow-same-origin"
        />
      )}
    </div>
  );
}

function VideoRenderingCard() {
  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-slate-200 shadow-sm">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0 fill-brand animate-pulse" aria-hidden>
          <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-9Zm4.5.5v8l5-4-5-4Z" />
        </svg>
        <span className="text-[12px] font-semibold text-slate-700">Rendering video…</span>
        <Loader2 size={11} className="ml-auto animate-spin text-brand" />
      </div>
      <div className="flex aspect-video items-center justify-center bg-slate-900">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <div className="relative flex h-14 w-14 items-center justify-center rounded-full bg-slate-800">
            <svg viewBox="0 0 16 16" className="h-7 w-7 fill-slate-500 animate-pulse" aria-hidden>
              <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-9Zm4.5.5v8l5-4-5-4Z" />
            </svg>
            <span className="absolute inset-0 rounded-full border-2 border-brand/40 animate-ping" />
          </div>
          <p className="text-[11px] font-medium">AI video generating — this takes 2–4 min</p>
          <div className="h-1 w-40 overflow-hidden rounded-full bg-slate-700">
            <div className="h-full w-1/3 rounded-full bg-brand animate-[loading-bar_1.8s_ease-in-out_infinite]" />
          </div>
        </div>
      </div>
    </div>
  );
}

function VideoPreview({ steps }: { steps?: AssistantStep[] }) {
  const videoStep = useMemo(
    () =>
      [...(steps ?? [])].reverse().find(
        (s) =>
          (s.tool === "get_video_status" &&
            (s.result as Record<string, unknown>)?.status === "done" &&
            (s.result as Record<string, unknown>)?.url) ||
          (s.tool === "get_kling_video_status" &&
            (s.result as Record<string, unknown>)?.status === "success" &&
            (s.result as Record<string, unknown>)?.url),
      ),
    [steps],
  );

  if (!videoStep) return null;

  const result = videoStep.result as Record<string, unknown>;
  const url = result.url as string;
  const title = (result.title as string | undefined) ?? "Promo Video";
  const aspectRatio = (result.aspect_ratio as string | undefined) ?? "16:9";

  // Determine container max-width based on aspect ratio
  const isPortrait = aspectRatio === "9:16";
  const isSquare = aspectRatio === "1:1";
  const containerClass = isPortrait
    ? "mx-auto max-w-[270px]" // Portrait: 9:16 = narrow
    : isSquare
      ? "mx-auto max-w-[480px]" // Square: 1:1
      : ""; // Landscape: full width

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-700">
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0 fill-brand" aria-hidden>
            <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-9Zm4.5.5v8l5-4-5-4Z" />
          </svg>
          {title}
        </div>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-medium text-slate-600 hover:border-brand/50 hover:text-brand-dark"
        >
          <Download size={10} />
          Download
        </a>
      </div>
      {/* Video player */}
      <div className="bg-black">
        <div className={containerClass}>
          <video
            src={url}
            controls
            playsInline
            className="block h-auto w-full"
          />
        </div>
      </div>
    </div>
  );
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

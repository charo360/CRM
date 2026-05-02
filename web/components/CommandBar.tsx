"use client";

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ZiloLogo } from "@/components/ZiloLogo";
import { assistantApi } from "@/lib/api";
import { getBusinessContext } from "@/lib/assistantContext";
import {
  ArrowRight,
  Clock,
  Command,
  ExternalLink,
  Loader2,
  Search,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";

// ─── Quick-action suggestions ────────────────────────────────────────────────
const QUICK_ACTIONS = [
  { icon: "📊", label: "Revenue this week", prompt: "What's my revenue this week?" },
  { icon: "💬", label: "Unread comments", prompt: "Show me unread social media comments" },
  { icon: "🔁", label: "Overdue follow-ups", prompt: "Show me overdue follow-ups" },
  { icon: "📣", label: "Draft a broadcast", prompt: "Draft a WhatsApp broadcast for my customers" },
  { icon: "📅", label: "Schedule a post", prompt: "Help me schedule a social media post" },
  { icon: "📦", label: "Low stock", prompt: "Which products are low on stock?" },
  { icon: "⭐", label: "Top customers", prompt: "Who are my top customers this month?" },
  { icon: "📈", label: "Engagement stats", prompt: "Show me my social media engagement stats" },
  { icon: "🧠", label: "Smart follow-up", prompt: "Draft a personalized follow-up to my recent customers" },
];

const LS_RECENT_KEY = "zilo.cmdbar.recent";
const MAX_RECENT = 6;

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(LS_RECENT_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveRecent(query: string) {
  try {
    const prev = loadRecent().filter((q) => q !== query);
    localStorage.setItem(LS_RECENT_KEY, JSON.stringify([query, ...prev].slice(0, MAX_RECENT)));
  } catch {}
}

// ─── Tool narration map ───────────────────────────────────────────────────────
const TOOL_LABELS: Record<string, string> = {
  get_live_social_posts: "Fetching live social posts…",
  get_social_post_analytics: "Pulling post analytics…",
  get_analytics_summary: "Analysing performance data…",
  list_customers: "Checking customers…",
  list_orders: "Checking orders…",
  list_followups: "Checking follow-ups…",
  create_broadcast: "Preparing broadcast…",
  web_search: "Searching the web…",
  get_owner_info: "Loading business info…",
  integrations_status: "Checking integrations…",
  list_products: "Checking inventory…",
  slack_workspace_info: "Checking Slack workspace…",
  slack_list_channels: "Loading Slack channels…",
  slack_post_message: "Posting to Slack…",
  record_sale: "Recording sale…",
  send_whatsapp_message: "Sending message…",
  list_scheduled_posts: "Loading scheduled posts…",
};

function toolLabel(name: string) {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) + "…";
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function CommandBar() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState<"idle" | "streaming" | "done" | "error">("idle");
  const [streamText, setStreamText] = useState("");
  const [streamTools, setStreamTools] = useState<string[]>([]);
  const [streamAgent, setStreamAgent] = useState<string | null>(null);
  const [convId, setConvId] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const [context, setContext] = useState<{
    new_customers?: number;
    orders?: number;
    top_product?: string;
    total_revenue_window?: number;
  }>({});
  const [pulseKey, setPulseKey] = useState<keyof typeof context | null>(null);
  const [rotatingSuggestions, setRotatingSuggestions] = useState<typeof QUICK_ACTIONS>([]);
  const [visibleStats, setVisibleStats] = useState<(keyof typeof context)[]>(["new_customers", "orders"]);
  const inputRef = useRef<HTMLInputElement>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<string> | null>(null);
  const responseRef = useRef<HTMLDivElement>(null);
  const abortedRef = useRef(false);

  // ── Open/close ──────────────────────────────────────────────────────────────
  const openBar = useCallback(() => {
    abortedRef.current = false;
    setConvId(null); // always start fresh
    setOpen(true);
    setQuery("");
    setPhase("idle");
    setStreamText("");
    setStreamTools([]);
    setStreamAgent(null);
    setRecent(loadRecent());
    // Show all suggestions
    setRotatingSuggestions(QUICK_ACTIONS);
    // Rotate which 2 stats to show
    const allStats: (keyof typeof context)[] = ["new_customers", "orders", "top_product", "total_revenue_window"];
    const shuffled = allStats.sort(() => Math.random() - 0.5);
    setVisibleStats(shuffled.slice(0, 2));
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  const closeBar = useCallback(() => {
    abortedRef.current = true;
    readerRef.current?.cancel().catch(() => {});
    readerRef.current = null;
    setOpen(false);
  }, []);

  // ── Global ⌘K / Ctrl+K listener ────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        open ? closeBar() : openBar();
      }
      if (e.key === "Escape" && open) closeBar();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, openBar, closeBar]);

  // ── Real-time business context via direct API ─────────────────────────────
  useEffect(() => {
    if (!open) return;
    let intervalId: NodeJS.Timeout;
    const fetchContext = async () => {
      try {
        const data = await getBusinessContext();
        setContext(data);
      } catch {
        // silently fail; keep existing values
      }
    };
    fetchContext(); // initial
    intervalId = setInterval(fetchContext, 15000); // every 15s
    return () => clearInterval(intervalId);
  }, [open]);

  // ── Auto-scroll response ────────────────────────────────────────────────────
  useEffect(() => {
    if (streamText && responseRef.current) {
      responseRef.current.scrollTop = responseRef.current.scrollHeight;
    }
  }, [streamText]);

  // ── Submit ──────────────────────────────────────────────────────────────────
  const submit = useCallback(
    async (msg: string) => {
      const trimmed = msg.trim();
      if (!trimmed || phase === "streaming") return;

      saveRecent(trimmed);
      setPhase("streaming");
      setStreamText("");
      setStreamTools([]);
      setStreamAgent(null);

      abortedRef.current = false;
      try {
        const stream = assistantApi.chatStream({
          message: trimmed,
          conversation_id: convId,
          auto_approve: true,
        });
        const reader = stream.getReader();
        readerRef.current = reader;

        let fullReply = "";
        let newConvId = convId;

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
              conversation_id?: string;
              reply?: string;
              message?: string;
            };

            if (event.type === "thinking") {
              setStreamAgent(event.agent_label ?? event.agent ?? null);
            } else if (event.type === "tool_start" && event.tool) {
              setStreamTools((prev) => [...new Set([...prev, event.tool!])]);
            } else if (event.type === "token") {
              fullReply += event.text ?? "";
              setStreamText(fullReply);
            } else if (event.type === "done") {
              fullReply = event.reply ?? fullReply;
              newConvId = event.conversation_id ?? newConvId;
              setStreamText(fullReply);
              setConvId(newConvId);
            } else if (event.type === "error") {
              throw new Error(event.message ?? "Something went wrong");
            }
          } catch {
            // non-JSON chunk — skip
          }
        }

        setPhase("done");
      } catch (err) {
        if (abortedRef.current) return; // user cancelled — don't overwrite phase
        console.error("CommandBar stream error", err);
        setStreamText((err as Error)?.message ?? "Something went wrong. Please try again.");
        setPhase("error");
      }
    },
    [phase, convId],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit(query);
  };

  const pickSuggestion = (prompt: string) => {
    setQuery(prompt);
    submit(prompt);
  };

  if (!open) return null;

  const showSuggestions = phase === "idle" && !query.trim();
  const showResponse = phase !== "idle";

  return (
    <>
      {/* ── Backdrop ─────────────────────────────────────────────────────────── */}
      <div
        className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]"
        style={{ background: "rgba(7,26,16,0.72)", backdropFilter: "blur(6px)" }}
        onMouseDown={(e) => { if (e.target === e.currentTarget) closeBar(); }}
      >
        {/* ── Panel ──────────────────────────────────────────────────────────── */}
        <div
          className="relative flex w-full max-w-2xl flex-col overflow-hidden rounded-2xl shadow-2xl"
          style={{
            background: "rgba(255,255,255,0.97)",
            border: "1px solid rgba(0,155,58,0.18)",
            boxShadow: "0 32px 80px rgba(7,26,16,0.35), 0 0 0 1px rgba(76,209,55,0.12)",
          }}
        >
          {/* ── Header: input ────────────────────────────────────────────────── */}
          <form onSubmit={handleSubmit} className="flex items-center gap-3 px-4 py-3.5">
            {phase === "streaming" ? (
              <Loader2 size={20} className="shrink-0 animate-spin text-brand-dark" />
            ) : (
              <ZiloLogo size={22} className="shrink-0" />
            )}
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") { e.stopPropagation(); closeBar(); }
              }}
              placeholder={phase === "streaming" ? "Zilo is working…" : "Ask Zilo anything…"}
              disabled={phase === "streaming"}
              className="min-w-0 flex-1 bg-transparent text-base font-medium text-slate-800 placeholder:text-slate-400 outline-none disabled:opacity-60"
              autoComplete="off"
              spellCheck={false}
            />
            {/* Keyboard hint */}
            {phase === "idle" && (
              <kbd className="hidden shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500 sm:flex">
                <Command size={10} />K
              </kbd>
            )}
            {(query || phase !== "idle") && (
              <button
                type="button"
                onClick={() => {
                  if (phase === "streaming") {
                    abortedRef.current = true;
                    readerRef.current?.cancel().catch(() => {});
                    readerRef.current = null;
                    setPhase("done");
                  } else {
                    setQuery("");
                    setPhase("idle");
                    setStreamText("");
                    setStreamTools([]);
                    inputRef.current?.focus();
                  }
                }}
                className="shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                <X size={16} />
              </button>
            )}
            {query && phase === "idle" && (
              <button
                type="submit"
                className="shrink-0 flex items-center gap-1.5 rounded-lg bg-brand-dark px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-dark/90"
              >
                <Zap size={14} />
                Ask
              </button>
            )}
          </form>

          {/* ── Divider ──────────────────────────────────────────────────────── */}
          <div className="h-px w-full bg-slate-100" />

          {/* ── Streaming narration bar ───────────────────────────────────────── */}
          {phase === "streaming" && (
            <div className="flex items-center gap-2 bg-brand-dark/5 px-4 py-2 text-xs text-brand-dark">
              <span className="flex h-1.5 w-1.5 shrink-0 rounded-full bg-brand-dark">
                <span className="inline-block h-1.5 w-1.5 animate-ping rounded-full bg-brand-dark opacity-75" />
              </span>
              <span className="font-medium">
                {streamTools.length > 0
                  ? toolLabel(streamTools[streamTools.length - 1])
                  : streamAgent
                  ? `Routing to ${streamAgent}…`
                  : "Thinking…"}
              </span>
              {streamTools.length > 1 && (
                <span className="ml-auto text-slate-400">
                  {streamTools.length} steps
                </span>
              )}
            </div>
          )}

          {/* ── Streaming / done response ─────────────────────────────────────── */}
          {showResponse && (
            <div
              ref={responseRef}
              className="max-h-[50vh] overflow-y-auto px-5 py-4"
            >
              {streamText ? (
                <div className="prose prose-sm prose-slate max-w-none text-slate-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {streamText}
                  </ReactMarkdown>
                </div>
              ) : phase === "streaming" ? (
                <div className="flex gap-1 pt-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:0ms]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:150ms]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:300ms]" />
                </div>
              ) : null}
            </div>
          )}

          {/* ── Tool trail pills ─────────────────────────────────────────────── */}
          {showResponse && streamTools.length > 0 && (
            <div className="flex flex-wrap gap-1.5 border-t border-slate-100 px-4 py-2.5">
              {streamTools.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-500"
                >
                  <Sparkles size={10} className="text-brand-dark" />
                  {t.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}

          {/* ── Done footer: open in chat ─────────────────────────────────────── */}
          {phase === "done" && convId && (
            <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-2.5">
              <span className="text-xs text-slate-400">Response complete</span>
              <Link
                href={`/dashboard/assistant?conversation_id=${convId}`}
                onClick={closeBar}
                className="flex items-center gap-1.5 rounded-lg bg-brand-dark px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-dark/90"
              >
                Open full chat
                <ExternalLink size={12} />
              </Link>
            </div>
          )}

          {/* ── Quick actions (shown when idle + no query) ────────────────────── */}
          {showSuggestions && (
            <div className="px-4 pb-4 pt-2">
              {/* Zilo remembers */}
              <div className="mb-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand-dark">
                  <Sparkles size={11} />
                  Zilo remembers
                </div>
                <div className="grid grid-cols-2 gap-1.5 text-xs text-slate-600">
                  {visibleStats.map((key) => {
                    const labels: Record<typeof key, string> = {
                      new_customers: "New customers",
                      orders: "Orders",
                      top_product: "Top product",
                      total_revenue_window: "Revenue (7d)",
                    };
                    const value = context[key];
                    return (
                      <div
                        key={key}
                        className={`rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 transition-all ${pulseKey === key ? "ring-2 ring-brand-dark/50 ring-offset-1" : ""}`}
                      >
                        <div className="font-medium text-slate-800">{labels[key]}</div>
                        <div className="text-slate-500">
                          {key === "total_revenue_window" && value ? `$${value}` : value ?? "…"}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Recent (max 2) */}
              {recent.length > 0 && (
                <div className="mb-3">
                  <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    <Clock size={11} />
                    Recent
                  </div>
                  <div className="flex flex-col gap-0.5">
                    {recent.slice(0, 2).map((r) => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => pickSuggestion(r)}
                        className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-100"
                      >
                        <Search size={13} className="shrink-0 text-slate-400" />
                        <span className="truncate">{r}</span>
                        <ArrowRight size={13} className="ml-auto shrink-0 text-slate-300" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Rotating suggestions (6 items) */}
              <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                <Sparkles size={11} />
                Suggestions
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                {rotatingSuggestions.map((a) => (
                  <button
                    key={a.prompt}
                    type="button"
                    onClick={() => pickSuggestion(a.prompt)}
                    className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-left text-xs font-medium text-slate-700 transition hover:border-brand-dark/30 hover:bg-brand-dark/5 hover:text-brand-dark"
                  >
                    <span className="text-sm leading-none">{a.icon}</span>
                    <span className="truncate">{a.label}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── Bottom hint ───────────────────────────────────────────────────── */}
          {phase === "idle" && (
            <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2">
              <span className="text-[11px] text-slate-400">
                Press <kbd className="rounded border border-slate-200 bg-slate-100 px-1 py-0.5 font-mono text-[10px]">↵ Enter</kbd> to ask
              </span>
              <span className="text-[11px] text-slate-400">
                <kbd className="rounded border border-slate-200 bg-slate-100 px-1 py-0.5 font-mono text-[10px]">Esc</kbd> to close
              </span>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

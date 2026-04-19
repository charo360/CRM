"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  assistantApi,
  type AssistantConversation,
  type AssistantMessage,
  type AssistantModel,
  type AssistantStep,
} from "@/lib/api";
import { Loader2, Send, Sparkles, Wrench, AlertTriangle, CheckCircle2 } from "lucide-react";

interface Props {
  conversationId?: string | null;
  onConversationChange?: (id: string) => void;
  compact?: boolean;
}

const QUICK_PROMPTS = [
  "How many new customers did I get this week?",
  "Show me overdue follow-ups",
  "Draft a promo broadcast for my VIPs",
  "What's my revenue today?",
];

export default function AssistantChat({ conversationId, onConversationChange, compact }: Props) {
  const [models, setModels] = useState<AssistantModel[]>([]);
  const [modelId, setModelId] = useState<string>("");
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingConv, setLoadingConv] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<
    null | { tool: string; arguments: Record<string, unknown>; reason: string }
  >(null);
  const [convId, setConvId] = useState<string | null>(conversationId ?? null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    assistantApi
      .models()
      .then((r) => {
        setModels(r.models);
        if (r.models.length) setModelId(r.default || r.models[0].id);
      })
      .catch(() => setError("AI models not configured. Set at least one provider API key on the backend."));
  }, []);

  const loadConversation = useCallback(async (id: string) => {
    setLoadingConv(true);
    try {
      const conv: AssistantConversation = await assistantApi.getConversation(id);
      setMessages(conv.messages || []);
      if (conv.model) setModelId(conv.model);
    } catch {
      setError("Could not load that conversation");
    } finally {
      setLoadingConv(false);
    }
  }, []);

  useEffect(() => {
    if (conversationId && conversationId !== convId) {
      setConvId(conversationId);
      void loadConversation(conversationId);
    }
  }, [conversationId, convId, loadConversation]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function send(messageOverride?: string, autoApprove = false) {
    const msg = (messageOverride ?? input).trim();
    if (!msg || sending) return;
    setInput("");
    setError(null);
    setSending(true);
    // Optimistic user bubble
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    try {
      const res = await assistantApi.chat({
        message: msg,
        conversation_id: convId,
        model: modelId || undefined,
        auto_approve: autoApprove,
      });
      if (!convId) {
        setConvId(res.conversation_id);
        onConversationChange?.(res.conversation_id);
      }
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.reply, steps: res.steps },
      ]);
      setPendingConfirm(res.needs_confirmation || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send");
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setSending(false);
    }
  }

  const empty = messages.length === 0 && !loadingConv;

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 text-white">
            <Sparkles size={14} />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900">Assistant</div>
            <div className="text-[10px] text-slate-400">{compact ? "Ask me anything" : "Chat with your CRM"}</div>
          </div>
        </div>
        <select
          value={modelId}
          onChange={(e) => setModelId(e.target.value)}
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

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3">
        {empty && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-500 text-white">
              <Sparkles size={22} />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800">How can I help?</p>
              <p className="mt-1 text-xs text-slate-500">
                I can look up customers, send WhatsApp messages, create follow-ups, run broadcasts, and more.
              </p>
            </div>
            <div className="grid w-full max-w-md grid-cols-1 gap-2">
              {QUICK_PROMPTS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => void send(p)}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 hover:border-indigo-300 hover:bg-indigo-50"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-3">
          {messages.map((m, i) => (
            <MessageBubble key={i} msg={m} />
          ))}
          {sending && (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Loader2 className="animate-spin" size={12} /> thinking…
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

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        className="flex items-end gap-2 border-t border-slate-100 p-3"
      >
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
          placeholder="Ask anything about your business…"
          className="max-h-32 flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
        />
        <button
          type="submit"
          disabled={!input.trim() || sending}
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
          aria-label="Send"
        >
          {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ msg }: { msg: AssistantMessage }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 px-3.5 py-2 text-sm text-white shadow-sm">
          {msg.content}
        </div>
      </div>
    );
  }
  if (msg.role === "assistant") {
    return (
      <div className="flex justify-start">
        <div className="max-w-[90%] space-y-1.5">
          {msg.steps && msg.steps.length > 0 && <StepsTrail steps={msg.steps} />}
          <div className="whitespace-pre-wrap rounded-2xl rounded-bl-md bg-slate-100 px-3.5 py-2 text-sm text-slate-800">
            {msg.content || <span className="italic text-slate-400">(no reply)</span>}
          </div>
        </div>
      </div>
    );
  }
  return null;
}

function StepsTrail({ steps }: { steps: AssistantStep[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-200"
      >
        <Wrench size={9} /> {steps.length} tool{steps.length !== 1 ? "s" : ""} called
      </button>
      {open && (
        <ul className="mt-1 space-y-1 text-[10px] text-slate-500">
          {steps.map((s, i) => (
            <li key={i} className="rounded-md bg-slate-50 px-2 py-1 font-mono">
              <span className="text-indigo-600">{s.tool}</span>(
              {Object.entries(s.arguments || {})
                .map(([k, v]) => `${k}: ${truncate(JSON.stringify(v), 40)}`)
                .join(", ")}
              )
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

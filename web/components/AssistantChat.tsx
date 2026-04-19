"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  assistantApi,
  type AssistantConversation,
  type AssistantDocument,
  type AssistantMessage,
  type AssistantModel,
  type AssistantStep,
} from "@/lib/api";
import {
  Loader2,
  Send,
  Sparkles,
  Wrench,
  AlertTriangle,
  CheckCircle2,
  Paperclip,
  FileText,
  Image as ImageIcon,
  X as XIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
  const [documents, setDocuments] = useState<AssistantDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
      const docs = await assistantApi.listDocuments(id).catch(() => ({ documents: [] }));
      setDocuments(docs.documents || []);
    } catch {
      setError("Could not load that conversation");
    } finally {
      setLoadingConv(false);
    }
  }, []);

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
      <div className="flex items-center justify-between border-b border-slate-100 bg-white/80 px-4 py-2.5 backdrop-blur">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 text-white">
            <Sparkles size={14} />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900">Zilo Chat</div>
            <div className="text-[10px] text-slate-400">
              {compact ? "Ask me anything" : "Chat with your CRM · attach documents"}
            </div>
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

      {/* Messages — centered ChatGPT/Claude column */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          {empty ? (
            <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-500 text-white shadow-lg">
                <Sparkles size={26} />
              </div>
              <div>
                <p className="text-2xl font-semibold text-slate-900">How can I help today?</p>
                <p className="mx-auto mt-2 max-w-lg text-sm text-slate-500">
                  Ask about customers, orders, follow-ups, or broadcasts — or attach a
                  document and I’ll read through it with you.
                </p>
              </div>
              <div className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
                {QUICK_PROMPTS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => void send(p)}
                    className="rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-left text-sm text-slate-700 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-50/60 hover:shadow"
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
              {messages.map((m, i) => (
                <MessageBubble key={i} msg={m} />
              ))}
              {sending && (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Loader2 className="animate-spin" size={12} /> Zilo is thinking…
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
                    <ImageIcon size={11} className="text-indigo-500" />
                  ) : (
                    <FileText size={11} className="text-indigo-500" />
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
            className="flex items-end gap-2 rounded-3xl border border-slate-200 bg-white px-2.5 py-2 shadow-[0_2px_14px_rgba(15,23,42,0.06)] focus-within:border-indigo-300 focus-within:shadow-[0_2px_18px_rgba(99,102,241,0.12)]"
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
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-indigo-600 disabled:opacity-50"
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
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white transition hover:bg-indigo-600 disabled:bg-slate-200 disabled:text-slate-400"
              aria-label="Send"
            >
              {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </button>
          </form>
          <p className="mt-2 text-center text-[10.5px] text-slate-400">
            Zilo may call tools on your CRM. Confirm destructive actions before they run.
          </p>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: AssistantMessage }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-slate-100 px-4 py-2.5 text-[14px] text-slate-900">
          {msg.content}
        </div>
      </div>
    );
  }
  if (msg.role === "assistant") {
    return (
      <div className="flex justify-start">
        <div className="flex w-full max-w-full gap-3">
          <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 text-white">
            <Sparkles size={13} />
          </div>
          <div className="min-w-0 flex-1 space-y-1.5">
            {msg.steps && msg.steps.length > 0 && <StepsTrail steps={msg.steps} />}
            <div className="text-[14px] leading-relaxed text-slate-800">
              {msg.content ? (
                <MarkdownBody content={msg.content} />
              ) : (
                <span className="italic text-slate-400">(no reply)</span>
              )}
            </div>
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
          a: (p) => (
            <a className="text-indigo-600 underline hover:text-indigo-700" target="_blank" rel="noreferrer" {...p} />
          ),
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
            <blockquote className="my-2 border-l-2 border-indigo-300 bg-indigo-50/50 px-3 py-1 text-slate-700" {...p} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
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

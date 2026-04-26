"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Inbox, RefreshCw, Search, Send, Sparkles, X, ChevronLeft,
  Loader2, Mail, MailOpen, Clock, Bot, ToggleLeft, ToggleRight,
  Star, Archive, Reply, Pencil, Zap, Check, AlertCircle,
  ArrowUpRight, Paperclip, ChevronDown, MessageSquarePlus,
} from "lucide-react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

type Thread = {
  id: string;
  subject: string;
  from: string;
  date: string;
  snippet: string;
  unread: boolean;
  messageCount: number;
  provider: "gmail" | "microsoft";
  starred?: boolean;
};

type Message = {
  id: string;
  from: string;
  to: string;
  subject: string;
  date: string;
  body: string;
  unread: boolean;
};

type AutoreplyRule = {
  enabled: boolean;
  tone: "professional" | "friendly" | "concise";
  extraContext: string;
};

type Tab = "all" | "unread" | "starred";

// ── API helpers ───────────────────────────────────────────────────────────────

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiGet(path: string) {
  const res = await fetch(path, { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(path: string, body: unknown) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function buildRaw(opts: { to: string; subject: string; body: string; inReplyTo?: string }) {
  const lines = [
    `To: ${opts.to}`,
    `Subject: ${opts.subject}`,
    `Content-Type: text/plain; charset="UTF-8"`,
    `MIME-Version: 1.0`,
    ...(opts.inReplyTo ? [`In-Reply-To: ${opts.inReplyTo}`, `References: ${opts.inReplyTo}`] : []),
    "",
    opts.body,
  ];
  return btoa(unescape(encodeURIComponent(lines.join("\r\n"))))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function formatDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (diffDays === 0) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diffDays < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function stripHtml(html: string) {
  if (typeof document !== "undefined") {
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    return tmp.textContent ?? tmp.innerText ?? "";
  }
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

function initials(from: string) {
  const name = from.split("<")[0].trim() || from;
  return name.split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2) || "?";
}

const AVATAR_COLORS = [
  "bg-brand", "bg-brand", "bg-emerald-500", "bg-amber-500",
  "bg-rose-500", "bg-cyan-500", "bg-pink-500", "bg-orange-500",
];
function avatarColor(from: string) {
  let h = 0;
  for (let i = 0; i < from.length; i++) h = (h * 31 + from.charCodeAt(i)) & 0xffffffff;
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}

// ── No-connection state ───────────────────────────────────────────────────────

function NoConnection({ inline = false }: { inline?: boolean }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-4 text-center px-8", inline ? "h-full" : "py-16")}>
      <div className="w-14 h-14 rounded-2xl bg-slate-800 flex items-center justify-center">
        <Mail size={26} className="text-slate-400" />
      </div>
      <div>
        <p className="font-semibold text-slate-200 text-sm">No email connected</p>
        <p className="text-xs text-slate-500 mt-1 leading-relaxed">
          Connect Gmail or Outlook in{" "}
          <a href="/dashboard/integrations" className="text-brand underline underline-offset-2">
            Integrations
          </a>{" "}
          to unlock your inbox.
        </p>
      </div>
    </div>
  );
}

// ── Compose modal ─────────────────────────────────────────────────────────────

function ComposeModal({
  provider,
  onClose,
  onSent,
  prefillTo = "",
  prefillSubject = "",
  prefillBody = "",
}: {
  provider: "gmail" | "microsoft" | null;
  onClose: () => void;
  onSent: () => void;
  prefillTo?: string;
  prefillSubject?: string;
  prefillBody?: string;
}) {
  const [to, setTo] = useState(prefillTo);
  const [subject, setSubject] = useState(prefillSubject);
  const [body, setBody] = useState(prefillBody);
  const [sending, setSending] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [tone, setTone] = useState<"professional" | "friendly" | "concise">("professional");

  async function send() {
    if (!to.trim() || !subject.trim()) { toast.error("To and Subject are required"); return; }
    setSending(true);
    try {
      if (provider === "gmail") {
        const raw = buildRaw({ to, subject, body });
        await apiPost("/api/email", { action: "send", raw });
      } else {
        await apiPost("/api/email", { action: "send", to, subject, replyBody: body });
      }
      toast.success("Sent!");
      onSent();
      onClose();
    } catch { toast.error("Send failed"); }
    finally { setSending(false); }
  }

  async function aiWrite() {
    if (!subject.trim()) { toast.error("Enter a subject first"); return; }
    setDrafting(true);
    try {
      const data = await apiPost("/api/email/draft", {
        threadSubject: subject,
        latestMessage: body || "(no prior content)",
        tone,
      }) as { draft: string };
      setBody(data.draft);
    } catch { toast.error("AI draft failed"); }
    finally { setDrafting(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:justify-end bg-black/40 backdrop-blur-sm p-4 md:pb-6 md:pr-6">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full md:w-[480px] shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Pencil size={13} className="text-brand" />
            <span className="text-sm font-semibold">New Email</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-100"><X size={15} /></button>
        </div>

        {/* Fields */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="To"
            className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-4 py-2.5 outline-none focus:ring-1 focus:ring-brand border border-slate-700"
          />
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl px-4 py-2.5 outline-none focus:ring-1 focus:ring-brand border border-slate-700"
          />

          {/* Tone selector */}
          <div className="flex items-center gap-1.5 pt-1">
            <span className="text-[10px] text-slate-500">Tone:</span>
            {(["professional", "friendly", "concise"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTone(t)}
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded-full capitalize transition-colors",
                  tone === t ? "bg-brand-dark text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                )}
              >
                {t}
              </button>
            ))}
          </div>

          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Write your message…"
            rows={10}
            className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl border border-slate-700 p-3 outline-none focus:ring-1 focus:ring-brand resize-none leading-relaxed"
          />
        </div>

        {/* Footer */}
        <div className="flex items-center gap-2 px-4 pb-4 pt-2 border-t border-slate-800">
          <button
            onClick={aiWrite}
            disabled={drafting}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 font-medium disabled:opacity-50 transition-colors"
          >
            {drafting ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} className="text-brand" />}
            AI Write
          </button>
          <div className="flex-1" />
          <button onClick={onClose} className="px-3 py-2 text-xs text-slate-400 hover:text-slate-100 transition-colors">
            Discard
          </button>
          <button
            onClick={send}
            disabled={sending}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-medium disabled:opacity-50 transition-colors"
          >
            {sending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function EmailPage() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [provider, setProvider] = useState<"gmail" | "microsoft" | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [tab, setTab] = useState<Tab>("all");

  const [selected, setSelected] = useState<Thread | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [threadLoading, setThreadLoading] = useState(false);

  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [showReply, setShowReply] = useState(false);

  const [draftTone, setDraftTone] = useState<"professional" | "friendly" | "concise">("professional");
  const [extraContext, setExtraContext] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [showDraftSettings, setShowDraftSettings] = useState(false);

  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const [loadingQuick, setLoadingQuick] = useState(false);

  const [autoreply, setAutoreply] = useState<AutoreplyRule>({ enabled: false, tone: "professional", extraContext: "" });

  const [showCompose, setShowCompose] = useState(false);

  // Starred stored locally (since no API for starring in our layer)
  const [starred, setStarred] = useState<Set<string>>(new Set());

  const replyRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const loadThreads = useCallback(async (q = "") => {
    setLoading(true);
    try {
      const data = await apiGet(`/api/email?q=${encodeURIComponent(q)}&limit=50`);
      setConnected(data.connected);
      setProvider(data.provider ?? null);
      setThreads(data.threads ?? []);
    } catch {
      toast.error("Failed to load inbox");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadThreads(); }, [loadThreads]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("email_autoreply");
      if (saved) setAutoreply(JSON.parse(saved) as AutoreplyRule);
      const savedStarred = localStorage.getItem("email_starred");
      if (savedStarred) setStarred(new Set(JSON.parse(savedStarred) as string[]));
    } catch { /* ignore */ }
  }, []);

  function saveAutoreply(rule: AutoreplyRule) {
    setAutoreply(rule);
    localStorage.setItem("email_autoreply", JSON.stringify(rule));
  }

  function toggleStar(threadId: string) {
    setStarred((prev) => {
      const next = new Set(prev);
      next.has(threadId) ? next.delete(threadId) : next.add(threadId);
      localStorage.setItem("email_starred", JSON.stringify([...next]));
      return next;
    });
  }

  // Filtered threads for current tab
  const filteredThreads = threads.filter((t) => {
    if (tab === "unread") return t.unread;
    if (tab === "starred") return starred.has(t.id);
    return true;
  });

  const unreadCount = threads.filter((t) => t.unread).length;
  const starredCount = threads.filter((t) => starred.has(t.id)).length;

  async function openThread(thread: Thread) {
    setSelected(thread);
    setMessages([]);
    setReplyText("");
    setShowReply(false);
    setQuickReplies([]);
    setShowDraftSettings(false);
    setThreadLoading(true);
    try {
      const data = await apiPost("/api/email", { action: "get_thread", threadId: thread.id }) as { messages: Message[] };
      const msgs = data.messages ?? [];
      setMessages(msgs);
      // Mark read
      if (thread.unread && msgs.length) {
        const last = msgs[msgs.length - 1];
        await apiPost("/api/email", { action: "mark_read", messageId: last.id });
        setThreads((prev) => prev.map((t) => t.id === thread.id ? { ...t, unread: false } : t));
      }
      // Auto-generate quick replies
      if (msgs.length) generateQuickReplies(thread.subject, msgs[msgs.length - 1]);
      // Scroll to bottom
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch {
      toast.error("Failed to load thread");
    } finally {
      setThreadLoading(false);
    }
  }

  async function generateQuickReplies(subject: string, latest: Message) {
    setLoadingQuick(true);
    try {
      const data = await apiPost("/api/email/draft", {
        threadSubject: subject,
        latestMessage: stripHtml(latest.body).slice(0, 800),
        senderName: latest.from,
        tone: "concise",
        extraContext: "Generate 3 very short reply options (max 15 words each), separated by ||. Do not number them. Just the reply text.",
      }) as { draft: string };
      const raw = data.draft ?? "";
      const options = raw.split("||").map((s) => s.trim()).filter(Boolean).slice(0, 3);
      setQuickReplies(options);
    } catch { /* ignore */ }
    finally { setLoadingQuick(false); }
  }

  async function handleAiDraft() {
    if (!selected || !messages.length) return;
    setDrafting(true);
    try {
      const latest = messages[messages.length - 1];
      const data = await apiPost("/api/email/draft", {
        threadSubject: selected.subject,
        latestMessage: stripHtml(latest.body).slice(0, 1500),
        senderName: latest.from,
        tone: draftTone,
        extraContext,
      }) as { draft: string };
      setReplyText(data.draft);
      setShowReply(true);
      setTimeout(() => replyRef.current?.focus(), 50);
    } catch { toast.error("AI draft failed"); }
    finally { setDrafting(false); }
  }

  async function handleSend() {
    if (!selected || !replyText.trim()) return;
    setSending(true);
    try {
      const latest = messages[messages.length - 1];
      const subject = selected.subject.startsWith("Re:") ? selected.subject : `Re: ${selected.subject}`;
      if (provider === "gmail") {
        await apiPost("/api/email", { action: "send", raw: buildRaw({ to: latest.from, subject, body: replyText, inReplyTo: latest.id }) });
      } else {
        await apiPost("/api/email", { action: "send", to: latest.from, subject, replyBody: replyText });
      }
      toast.success("Sent!");
      setReplyText("");
      setShowReply(false);
      await openThread(selected);
    } catch { toast.error("Send failed"); }
    finally { setSending(false); }
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setActiveSearch(searchInput);
    loadThreads(searchInput);
  }

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "c") { e.preventDefault(); setShowCompose(true); }
      if (e.key === "r" && selected) { e.preventDefault(); setShowReply(true); setTimeout(() => replyRef.current?.focus(), 50); }
      if (e.key === "Escape") { setSelected(null); setShowReply(false); }
      if (e.key === "s" && selected) { e.preventDefault(); toggleStar(selected.id); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  return (
    <div className="flex h-full bg-slate-950 text-slate-100 overflow-hidden">

      {/* ── Left pane ─────────────────────────────────────────────────────── */}
      <div className={cn(
        "flex flex-col border-r border-slate-800 bg-slate-900 shrink-0 transition-all duration-200",
        selected ? "w-72 hidden md:flex" : "w-full md:w-80"
      )}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-slate-800">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Inbox size={15} className="text-brand" />
              <span className="font-semibold text-sm">Inbox</span>
              {provider && (
                <span className="text-[10px] text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full">
                  {provider === "gmail" ? "Gmail" : "Outlook"}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setShowCompose(true)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-brand-dark hover:bg-brand text-white text-xs font-medium transition-colors"
                title="Compose (C)"
              >
                <Pencil size={11} /> Compose
              </button>
              <button onClick={() => loadThreads(activeSearch)} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-800 transition-colors" title="Refresh">
                <RefreshCw size={12} />
              </button>
            </div>
          </div>

          {/* Search */}
          <form onSubmit={handleSearch}>
            <div className="flex items-center gap-2 bg-slate-800 rounded-xl px-3 py-2 border border-slate-700/50">
              <Search size={12} className="text-slate-500 shrink-0" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search emails…"
                className="flex-1 bg-transparent text-xs text-slate-200 placeholder-slate-500 outline-none min-w-0"
              />
              {searchInput && (
                <button type="button" onClick={() => { setSearchInput(""); setActiveSearch(""); loadThreads(""); }}>
                  <X size={11} className="text-slate-500" />
                </button>
              )}
            </div>
          </form>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-800">
          {([
            { id: "all", label: "All" },
            { id: "unread", label: "Unread", count: unreadCount },
            { id: "starred", label: "Starred", count: starredCount },
          ] as { id: Tab; label: string; count?: number }[]).map(({ id, label, count }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex-1 py-2.5 text-xs font-medium flex items-center justify-center gap-1 transition-colors border-b-2",
                tab === id
                  ? "text-brand border-brand"
                  : "text-slate-500 border-transparent hover:text-slate-300"
              )}
            >
              {label}
              {count != null && count > 0 && (
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full font-semibold",
                  tab === id ? "bg-brand-dark text-white" : "bg-slate-800 text-slate-400"
                )}>{count}</span>
              )}
            </button>
          ))}
        </div>

        {/* Auto-reply bar */}
        <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <Bot size={12} />
            Auto-reply
          </div>
          <button
            onClick={() => saveAutoreply({ ...autoreply, enabled: !autoreply.enabled })}
            className={cn("flex items-center gap-1 text-[11px] font-medium transition-colors", autoreply.enabled ? "text-emerald-400" : "text-slate-600")}
          >
            {autoreply.enabled ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
            {autoreply.enabled ? "On" : "Off"}
          </button>
        </div>

        {/* Thread list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin text-slate-600" /></div>
          ) : connected === false ? (
            <NoConnection />
          ) : filteredThreads.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-slate-600">
              <MailOpen size={24} />
              <p className="text-xs">{tab === "unread" ? "All caught up!" : tab === "starred" ? "No starred emails" : "No emails"}</p>
            </div>
          ) : (
            filteredThreads.map((thread) => {
              const isStarred = starred.has(thread.id);
              const initStr = initials(thread.from);
              const color = avatarColor(thread.from);
              return (
                <div
                  key={thread.id}
                  onClick={() => openThread(thread)}
                  className={cn(
                    "group w-full text-left px-3 py-3 border-b border-slate-800/60 hover:bg-slate-800/40 transition-colors cursor-pointer relative",
                    selected?.id === thread.id && "bg-slate-800/70",
                    thread.unread && "border-l-2 border-l-brand"
                  )}
                >
                  <div className="flex items-start gap-2.5">
                    {/* Avatar */}
                    <div className={cn("w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold text-white shrink-0", color)}>
                      {initStr}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1">
                        <span className={cn("text-xs truncate", thread.unread ? "font-semibold text-slate-100" : "text-slate-300 font-medium")}>
                          {thread.from.split("<")[0].trim() || thread.from}
                        </span>
                        <span className="text-[10px] text-slate-600 shrink-0">{formatDate(thread.date)}</span>
                      </div>
                      <p className={cn("text-[11px] truncate mt-0.5", thread.unread ? "text-slate-200 font-medium" : "text-slate-400")}>
                        {thread.subject}
                      </p>
                      <p className="text-[10px] text-slate-600 mt-0.5 line-clamp-1">{thread.snippet}</p>
                    </div>
                  </div>

                  {/* Hover quick actions */}
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-1 bg-slate-800 rounded-lg p-1 shadow-lg border border-slate-700">
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleStar(thread.id); }}
                      className={cn("p-1 rounded transition-colors", isStarred ? "text-amber-400" : "text-slate-500 hover:text-amber-400")}
                      title="Star (S)"
                    >
                      <Star size={11} fill={isStarred ? "currentColor" : "none"} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); openThread(thread); setShowReply(true); }}
                      className="p-1 rounded text-slate-500 hover:text-brand transition-colors"
                      title="Quick reply"
                    >
                      <Reply size={11} />
                    </button>
                  </div>

                  {thread.unread && (
                    <span className="absolute right-2 bottom-2 w-1.5 h-1.5 rounded-full bg-brand" />
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Keyboard hint */}
        <div className="px-3 py-2 border-t border-slate-800 flex items-center gap-3 flex-wrap">
          {[["C", "Compose"], ["R", "Reply"], ["S", "Star"], ["Esc", "Close"]].map(([k, label]) => (
            <span key={k} className="text-[10px] text-slate-700 flex items-center gap-1">
              <kbd className="text-[9px] bg-slate-800 text-slate-500 px-1 py-0.5 rounded font-mono">{k}</kbd>
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* ── Right pane ────────────────────────────────────────────────────── */}
      {selected ? (
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Thread header */}
          <div className="px-4 py-3 border-b border-slate-800 bg-slate-900/80 flex items-center gap-3">
            <button onClick={() => setSelected(null)} className="md:hidden p-1.5 rounded-lg text-slate-400 hover:bg-slate-800">
              <ChevronLeft size={16} />
            </button>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-sm truncate">{selected.subject}</p>
              <p className="text-xs text-slate-500 truncate">{selected.from}</p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => toggleStar(selected.id)}
                className={cn("p-2 rounded-lg transition-colors", starred.has(selected.id) ? "text-amber-400" : "text-slate-500 hover:text-amber-400 hover:bg-slate-800")}
                title="Star"
              >
                <Star size={14} fill={starred.has(selected.id) ? "currentColor" : "none"} />
              </button>
              {selected.messageCount > 1 && (
                <span className="text-[10px] text-slate-500 bg-slate-800 px-2 py-1 rounded-lg">
                  {selected.messageCount} messages
                </span>
              )}
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {threadLoading ? (
              <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-slate-600" /></div>
            ) : messages.length === 0 ? (
              <div className="text-center text-slate-600 text-sm py-10">No messages</div>
            ) : (
              <>
                {messages.map((msg, i) => {
                  const isLast = i === messages.length - 1;
                  return (
                    <div key={msg.id} className={cn("rounded-2xl border p-4 transition-all", isLast ? "border-slate-700 bg-slate-900" : "border-slate-800/40 bg-slate-900/40")}>
                      <div className="flex items-start justify-between gap-3 mb-3">
                        <div className="flex items-center gap-2.5">
                          <div className={cn("w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0", avatarColor(msg.from))}>
                            {initials(msg.from)}
                          </div>
                          <div>
                            <p className="text-xs font-semibold text-slate-200">{msg.from.split("<")[0].trim()}</p>
                            <p className="text-[10px] text-slate-500">To: {msg.to.split(",")[0]}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 text-[10px] text-slate-500 shrink-0">
                          <Clock size={10} />
                          {new Date(msg.date).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </div>
                      </div>
                      <div
                        className="text-sm text-slate-300 leading-relaxed"
                        dangerouslySetInnerHTML={{ __html: msg.body.includes("<") ? msg.body : msg.body.replace(/\n/g, "<br/>") }}
                      />
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Quick replies */}
          {!showReply && messages.length > 0 && (
            <div className="px-4 pb-3 flex items-center gap-2 flex-wrap border-t border-slate-800 pt-3">
              <span className="text-[10px] text-slate-500 shrink-0">Quick reply:</span>
              {loadingQuick ? (
                <Loader2 size={12} className="animate-spin text-slate-600" />
              ) : (
                quickReplies.map((qr, i) => (
                  <button
                    key={i}
                    onClick={() => { setReplyText(qr); setShowReply(true); setTimeout(() => replyRef.current?.focus(), 50); }}
                    className="text-[11px] px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition-colors"
                  >
                    {qr}
                  </button>
                ))
              )}
              <button
                onClick={() => { setShowReply(true); setTimeout(() => replyRef.current?.focus(), 50); }}
                className="flex items-center gap-1 text-[11px] px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-brand-ink/30 border border-slate-700 hover:border-brand-dark/40 text-brand transition-colors ml-auto"
              >
                <Reply size={11} /> Reply
              </button>
            </div>
          )}

          {/* Reply composer */}
          {showReply && (
            <div className="border-t border-slate-800 bg-slate-900/80 p-4 space-y-3">
              {/* AI draft settings */}
              {showDraftSettings && (
                <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-brand/50 flex items-center gap-1.5"><Sparkles size={11} /> AI Draft</span>
                    <button onClick={() => setShowDraftSettings(false)}><X size={12} className="text-slate-500" /></button>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500 w-8">Tone</span>
                    {(["professional", "friendly", "concise"] as const).map((t) => (
                      <button key={t} onClick={() => setDraftTone(t)} className={cn("text-[10px] px-2 py-0.5 rounded-lg capitalize transition-colors", draftTone === t ? "bg-brand-dark text-white" : "bg-slate-700 text-slate-400 hover:bg-slate-600")}>
                        {t}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-500 w-8">Hint</span>
                    <input
                      value={extraContext}
                      onChange={(e) => setExtraContext(e.target.value)}
                      placeholder="e.g. mention 30-day return policy"
                      className="flex-1 text-[11px] bg-slate-700 text-slate-200 placeholder-slate-500 rounded-lg px-3 py-1.5 outline-none focus:ring-1 focus:ring-brand"
                    />
                  </div>
                  <button onClick={handleAiDraft} disabled={drafting} className="w-full py-1.5 rounded-lg bg-brand-dark hover:bg-brand text-white text-xs font-medium flex items-center justify-center gap-1.5 disabled:opacity-50 transition-colors">
                    {drafting ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                    {drafting ? "Writing…" : "Generate"}
                  </button>
                </div>
              )}

              {autoreply.enabled && (
                <div className="flex items-center gap-2 text-[11px] text-emerald-400 bg-emerald-900/20 border border-emerald-800/40 rounded-xl px-3 py-2">
                  <Zap size={11} /> Auto-reply active for new emails
                </div>
              )}

              <div className="relative">
                <textarea
                  ref={replyRef}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Write a reply…"
                  rows={4}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleSend(); }
                  }}
                  className="w-full bg-slate-800 text-sm text-slate-200 placeholder-slate-500 rounded-xl border border-slate-700 p-3 pr-10 outline-none focus:ring-1 focus:ring-brand resize-none leading-relaxed"
                />
                <span className="absolute right-3 bottom-2 text-[9px] text-slate-600">⌘↵ send</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowDraftSettings((v) => !v)}
                  className={cn("flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium transition-colors", showDraftSettings ? "bg-brand-dark/20 text-brand/50 border border-brand-dark/30" : "bg-slate-800 text-slate-400 hover:bg-slate-700")}
                >
                  <Sparkles size={12} /> AI Draft
                </button>
                <button onClick={() => { setShowReply(false); setReplyText(""); }} className="px-3 py-2 rounded-xl text-xs text-slate-500 hover:text-slate-300 transition-colors">
                  Cancel
                </button>
                <div className="flex-1" />
                <button
                  onClick={handleSend}
                  disabled={sending || !replyText.trim()}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-brand-dark hover:bg-brand text-white text-xs font-semibold disabled:opacity-40 transition-colors"
                >
                  {sending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                  {sending ? "Sending…" : "Send"}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : connected === false ? (
        <div className="flex-1 flex items-center justify-center"><NoConnection inline /></div>
      ) : connected === true ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-700">
          <MailOpen size={40} className="text-slate-800" />
          <p className="text-sm text-slate-600">Select a conversation</p>
          <button
            onClick={() => setShowCompose(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-sm text-slate-400 transition-colors mt-2"
          >
            <Pencil size={14} /> Compose new email
          </button>
        </div>
      ) : null}

      {/* ── Auto-reply settings drawer ─────────────────────────────────────── */}
      {autoreply.enabled && (
        <div className="w-60 border-l border-slate-800 bg-slate-900 flex-col p-4 space-y-4 hidden xl:flex shrink-0">
          <div className="flex items-center gap-2">
            <Bot size={13} className="text-brand" />
            <span className="text-xs font-semibold">Auto-reply</span>
            <span className="ml-auto text-[10px] text-emerald-400 font-medium bg-emerald-900/30 px-2 py-0.5 rounded-full">Live</span>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Zilo will automatically reply to new emails with your selected tone and context.
          </p>
          <div className="space-y-1.5">
            <p className="text-[10px] text-slate-500">Tone</p>
            <div className="flex flex-wrap gap-1.5">
              {(["professional", "friendly", "concise"] as const).map((t) => (
                <button key={t} onClick={() => saveAutoreply({ ...autoreply, tone: t })} className={cn("text-[10px] px-2.5 py-1 rounded-lg capitalize transition-colors", autoreply.tone === t ? "bg-brand-dark text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700")}>
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-1.5">
            <p className="text-[10px] text-slate-500">Business context</p>
            <textarea
              value={autoreply.extraContext}
              onChange={(e) => saveAutoreply({ ...autoreply, extraContext: e.target.value })}
              placeholder="Hours, policies, FAQs…"
              rows={5}
              className="w-full bg-slate-800 text-[11px] text-slate-300 placeholder-slate-600 rounded-xl border border-slate-700 p-2.5 outline-none focus:ring-1 focus:ring-brand resize-none"
            />
          </div>
          <button onClick={() => saveAutoreply({ ...autoreply, enabled: false })} className="flex items-center gap-1.5 text-[11px] text-rose-500 hover:text-rose-400 transition-colors">
            <AlertCircle size={11} /> Turn off
          </button>
        </div>
      )}

      {/* Compose modal */}
      {showCompose && (
        <ComposeModal
          provider={provider}
          onClose={() => setShowCompose(false)}
          onSent={() => loadThreads(activeSearch)}
        />
      )}
    </div>
  );
}

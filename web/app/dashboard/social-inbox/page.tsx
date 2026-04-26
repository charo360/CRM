"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { zernioApi } from "@/lib/api";
import {
  Inbox, RefreshCw, Send,
  MessageCircle, Globe, ChevronLeft, CheckCircle, XCircle, Loader2
} from "lucide-react";

type Account = { id: string; platform: string; name: string; username?: string; avatar?: string };
type Conversation = { id: string; platform: string; participant_name?: string; participant?: string; last_message?: string; last_message_at?: string; unread?: number; avatar?: string };
type Message = { id: string; content: string; direction: "in" | "out"; created_at: string; sender?: string };

const PLATFORM_ICON: Record<string, React.ReactNode> = {
  instagram: (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5 text-pink-500">
      <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
    </svg>
  ),
  facebook: (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5 text-blue-600">
      <path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.791-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.97h-1.513c-1.491 0-1.956.93-1.956 1.883v2.252h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/>
    </svg>
  ),
  twitter: (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5 text-sky-500">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.742l7.73-8.835L1.254 2.25H8.08l4.26 5.632zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>
  ),
  whatsapp: <MessageCircle size={14} className="text-green-500" />,
  telegram: <Send size={14} className="text-sky-400" />,
};

const PLATFORM_COLOR: Record<string, string> = {
  instagram: "bg-pink-50 text-pink-700 border-pink-200",
  facebook: "bg-blue-50 text-blue-700 border-blue-200",
  twitter: "bg-sky-50 text-sky-700 border-sky-200",
  whatsapp: "bg-green-50 text-green-700 border-green-200",
  telegram: "bg-sky-50 text-sky-600 border-sky-200",
};

function PlatformBadge({ platform }: { platform: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs border capitalize ${PLATFORM_COLOR[platform] || "bg-slate-50 text-slate-600 border-slate-200"}`}>
      {PLATFORM_ICON[platform] || <Globe size={12} />} {platform}
    </span>
  );
}

function timeAgo(dateStr?: string) {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function SocialInboxPage() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [platformFilter, setPlatformFilter] = useState("");
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<"ok" | "err" | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [status, accs] = await Promise.all([
        zernioApi.status(),
        zernioApi.accounts().catch(() => ({})),
      ]);
      const isConnected = (status as { connected?: boolean }).connected === true;
      setConnected(isConnected);
      if (isConnected) {
        const accsData = (accs as { data?: Account[] | { accounts?: Account[] } });
        const list = Array.isArray(accsData.data) ? accsData.data :
          (accsData.data as { accounts?: Account[] })?.accounts || [];
        setAccounts(list);
        // Load inbox
        const inbox = await zernioApi.inbox(platformFilter || undefined);
        const convs = (inbox as { data?: Conversation[]; conversations?: Conversation[] });
        setConversations(
          Array.isArray(convs.data) ? convs.data :
          Array.isArray(convs.conversations) ? convs.conversations : []
        );
      }
    } finally { setLoading(false); }
  }, [platformFilter]);

  useEffect(() => { load(); }, [load]);

  async function openConversation(conv: Conversation) {
    setSelected(conv);
    setLoadingMsgs(true);
    setMessages([]);
    try {
      const data = await zernioApi.conversation(conv.id);
      const msgs = (data as { data?: Message[]; messages?: Message[] });
      setMessages(
        Array.isArray(msgs.data) ? msgs.data :
        Array.isArray(msgs.messages) ? msgs.messages : []
      );
    } finally { setLoadingMsgs(false); }
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
  }

  async function sendReply() {
    if (!selected || !reply.trim()) return;
    setSending(true);
    setSendResult(null);
    try {
      await zernioApi.send(selected.id, reply.trim());
      setReply("");
      setSendResult("ok");
      await openConversation(selected);
    } catch {
      setSendResult("err");
    } finally { setSending(false); }
  }

  const platforms = [...new Set(conversations.map(c => c.platform).filter(Boolean))];

  const filteredConvs = platformFilter
    ? conversations.filter(c => c.platform === platformFilter)
    : conversations;

  // Not connected state
  if (connected === false) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50">
        <div className="text-center space-y-3 max-w-sm px-6">
          <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto">
            <Inbox size={28} className="text-slate-400" />
          </div>
          <p className="text-base font-semibold text-slate-700">Social Inbox coming soon</p>
          <p className="text-sm text-slate-400 leading-relaxed">
            Your social media channels are being set up. Once activated, all your messages from Facebook, Instagram, WhatsApp, and more will appear here.
          </p>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {loading ? "Checking…" : "Refresh"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-0px)] overflow-hidden">
      {/* Left panel — conversation list */}
      <div className={`flex flex-col border-r border-slate-200 bg-white ${selected ? "hidden md:flex w-80" : "flex w-full md:w-80"}`}>
        {/* Header */}
        <div className="p-4 border-b border-slate-100">
          <div className="flex items-center justify-between mb-3">
            <h1 className="font-bold text-slate-800 flex items-center gap-2">
              <Inbox size={18} className="text-brand-dark" /> Social Inbox
            </h1>
            <button onClick={load} className="text-slate-400 hover:text-slate-700">
              <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
          {/* Connected accounts */}
          {accounts.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {accounts.map(a => (
                <span key={a.id} className="flex items-center gap-1 px-2 py-0.5 bg-green-50 border border-green-200 rounded-full text-xs text-green-700">
                  <CheckCircle size={10} /> {a.name || a.platform}
                </span>
              ))}
            </div>
          )}
          {/* Platform filter */}
          {platforms.length > 1 && (
            <div className="flex gap-1 flex-wrap">
              <button onClick={() => setPlatformFilter("")}
                className={`px-2 py-0.5 rounded-full text-xs border capitalize ${platformFilter === "" ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200"}`}>
                All
              </button>
              {platforms.map(p => (
                <button key={p} onClick={() => setPlatformFilter(p)}
                  className={`px-2 py-0.5 rounded-full text-xs border capitalize ${platformFilter === p ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200"}`}>
                  {p}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-40 text-slate-400">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : filteredConvs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2 p-4 text-center">
              <Inbox size={36} className="opacity-30" />
              <p className="text-sm">No conversations yet.</p>
              <p className="text-xs">Connect your social accounts in Zernio and messages will appear here.</p>
            </div>
          ) : (
            filteredConvs.map(conv => (
              <button key={conv.id} onClick={() => openConversation(conv)}
                className={`w-full text-left px-4 py-3 border-b border-slate-50 hover:bg-slate-50 transition-colors ${selected?.id === conv.id ? "bg-brand/10 border-l-2 border-l-brand" : ""}`}>
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-full bg-slate-200 flex items-center justify-center shrink-0 text-sm font-bold text-slate-600">
                    {(conv.participant_name || conv.participant || "?")[0]?.toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <p className="font-medium text-slate-800 text-sm truncate">
                        {conv.participant_name || conv.participant || "Unknown"}
                      </p>
                      <span className="text-xs text-slate-400 shrink-0">{timeAgo(conv.last_message_at)}</span>
                    </div>
                    <p className="text-xs text-slate-500 truncate mt-0.5">{conv.last_message || "No messages"}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <PlatformBadge platform={conv.platform} />
                      {conv.unread ? (
                        <span className="bg-brand-dark text-white text-xs rounded-full px-1.5 py-0.5 font-bold">{conv.unread}</span>
                      ) : null}
                    </div>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right panel — messages */}
      {selected ? (
        <div className="flex flex-col flex-1 bg-slate-50">
          {/* Conv header */}
          <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200">
            <button onClick={() => setSelected(null)} className="md:hidden text-slate-400 hover:text-slate-700">
              <ChevronLeft size={20} />
            </button>
            <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-sm font-bold text-slate-600">
              {(selected.participant_name || selected.participant || "?")[0]?.toUpperCase()}
            </div>
            <div>
              <p className="font-semibold text-slate-800 text-sm">{selected.participant_name || selected.participant}</p>
              <PlatformBadge platform={selected.platform} />
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {loadingMsgs ? (
              <div className="flex items-center justify-center h-40 text-slate-400">
                <Loader2 size={20} className="animate-spin" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-slate-400">No messages</div>
            ) : (
              messages.map(msg => (
                <div key={msg.id} className={`flex ${msg.direction === "out" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[70%] px-3 py-2 rounded-2xl text-sm ${msg.direction === "out" ? "bg-brand-dark text-white rounded-br-sm" : "bg-white text-slate-800 border border-slate-200 rounded-bl-sm shadow-sm"}`}>
                    <p>{msg.content}</p>
                    <p className={`text-xs mt-1 ${msg.direction === "out" ? "text-brand/30" : "text-slate-400"}`}>
                      {timeAgo(msg.created_at)}
                    </p>
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Reply box */}
          <div className="bg-white border-t border-slate-200 p-3">
            {sendResult === "ok" && (
              <p className="text-xs text-green-600 flex items-center gap-1 mb-2"><CheckCircle size={12} /> Message sent</p>
            )}
            {sendResult === "err" && (
              <p className="text-xs text-red-500 flex items-center gap-1 mb-2"><XCircle size={12} /> Failed to send. Try again.</p>
            )}
            <div className="flex gap-2 items-end">
              <textarea
                className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand"
                rows={2}
                placeholder={`Reply on ${selected.platform}...`}
                value={reply}
                onChange={e => setReply(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendReply(); } }}
              />
              <button onClick={sendReply} disabled={sending || !reply.trim()}
                className="p-2.5 bg-brand-dark text-white rounded-xl hover:bg-brand disabled:opacity-40 transition-colors">
                {sending ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-1">Enter to send · Shift+Enter for new line</p>
          </div>
        </div>
      ) : (
        <div className="hidden md:flex flex-1 items-center justify-center bg-slate-50">
          <div className="text-center text-slate-400 space-y-2">
            <Inbox size={48} className="mx-auto opacity-20" />
            <p className="text-sm">Select a conversation to read messages</p>
          </div>
        </div>
      )}
    </div>
  );
}

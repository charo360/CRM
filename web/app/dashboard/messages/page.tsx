"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { customersApi, messagesApi, Customer, Message } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { Search, Send, Loader2, MessageSquare, RefreshCw } from "lucide-react";

type Channel = "whatsapp" | "instagram";

const CHANNEL_CONFIG: Record<Channel, { label: string; color: string; bg: string; dot: string }> = {
  whatsapp:  { label: "WhatsApp",  color: "text-[#25D366]",  bg: "bg-[#25D366]/10",  dot: "bg-[#25D366]" },
  instagram: { label: "Instagram", color: "text-[#E1306C]",  bg: "bg-[#E1306C]/10",  dot: "bg-[#E1306C]" },
};

const POLL_INTERVAL = 6000;

export default function MessagesPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [channel, setChannel] = useState<Channel>("whatsapp");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [search, setSearch] = useState("");
  const [loadingCustomers, setLoadingCustomers] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load customer list
  useEffect(() => {
    customersApi.list()
      .then((list) => {
        // Sort by most recent activity
        list.sort((a, b) => {
          const at = a.last_contacted ? new Date(a.last_contacted).getTime() : 0;
          const bt = b.last_contacted ? new Date(b.last_contacted).getTime() : 0;
          return bt - at;
        });
        setCustomers(list);
      })
      .finally(() => setLoadingCustomers(false));
  }, []);

  // Load messages for selected customer
  const loadMessages = useCallback(async (customerId: string) => {
    try {
      const msgs = await messagesApi.forCustomer(customerId);
      // Most recent last
      setMessages([...msgs].reverse());
      // Mark as read
      messagesApi.markRead(customerId).catch(() => {});
    } catch {
      // ignore
    }
  }, []);

  // When customer selected
  useEffect(() => {
    if (!selectedId) return;
    setLoadingMessages(true);
    setMessages([]);
    loadMessages(selectedId).finally(() => setLoadingMessages(false));

    // Poll for new messages
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => loadMessages(selectedId), POLL_INTERVAL);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [selectedId, loadMessages]);

  // Scroll to bottom when messages update
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim() || !selectedId) return;
    const selected = customers.find((c) => c.id === selectedId);
    if (!selected) return;
    setSending(true);
    try {
      await messagesApi.send(selected.phone_number, draft.trim(), selected.name);
      setDraft("");
      await loadMessages(selectedId);
    } catch (err) {
      console.error(err);
    } finally {
      setSending(false);
    }
  }

  const filteredCustomers = customers.filter((c) => {
    const q = search.toLowerCase();
    return !q || c.name.toLowerCase().includes(q) || c.phone_number.includes(q);
  });

  const selectedCustomer = customers.find((c) => c.id === selectedId);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left — customer list */}
      <div className="w-72 shrink-0 border-r border-slate-200 flex flex-col bg-white">
        {/* Channel switcher */}
        <div className="p-3 border-b border-slate-100">
          <div className="flex rounded-lg bg-slate-100 p-1 gap-1">
            {(["whatsapp", "instagram"] as Channel[]).map((ch) => {
              const cfg = CHANNEL_CONFIG[ch];
              return (
                <button key={ch} onClick={() => setChannel(ch)}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                    channel === ch ? "bg-white shadow-sm text-slate-800" : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot}`} />
                  {cfg.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Search */}
        <div className="px-3 py-2 border-b border-slate-100">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search conversations…"
              className="w-full pl-7 pr-2 py-1.5 text-xs border border-slate-200 rounded-lg outline-none focus:ring-1 focus:ring-indigo-500 bg-slate-50" />
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {loadingCustomers ? (
            Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-slate-50 animate-pulse">
                <div className="w-9 h-9 rounded-full bg-slate-100 shrink-0" />
                <div className="flex-1 space-y-1">
                  <div className="h-3 bg-slate-100 rounded w-3/4" />
                  <div className="h-2 bg-slate-100 rounded w-1/2" />
                </div>
              </div>
            ))
          ) : filteredCustomers.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-10">No conversations</p>
          ) : (
            filteredCustomers.map((c) => {
              const isSelected = selectedId === c.id;
              const unread = (c.unread_count || 0) > 0;
              return (
                <button key={c.id} onClick={() => setSelectedId(c.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 border-b border-slate-50 text-left transition-colors ${
                    isSelected ? "bg-indigo-50 border-l-2 border-l-indigo-500" : "hover:bg-slate-50"
                  }`}
                >
                  {/* Avatar */}
                  <div className="relative shrink-0">
                    <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center">
                      {c.profile_picture ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={c.profile_picture} alt={c.name} className="w-9 h-9 rounded-full object-cover" />
                      ) : (
                        <span className="text-indigo-600 font-semibold text-xs">{c.name.charAt(0).toUpperCase()}</span>
                      )}
                    </div>
                    {/* Channel dot */}
                    <span className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-white ${CHANNEL_CONFIG[channel].dot}`} />
                  </div>
                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <p className={`text-sm truncate ${unread ? "font-bold text-slate-900" : "font-medium text-slate-700"}`}>
                        {c.name}
                      </p>
                      {c.last_contacted && (
                        <span className="text-[10px] text-slate-400 shrink-0">{timeAgo(c.last_contacted)}</span>
                      )}
                    </div>
                    <p className="text-xs text-slate-400 truncate mt-0.5">
                      {c.last_message || c.phone_number}
                    </p>
                  </div>
                  {unread && (
                    <span className="w-4 h-4 rounded-full bg-indigo-600 text-white text-[9px] font-bold flex items-center justify-center shrink-0">
                      {c.unread_count}
                    </span>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right — chat */}
      {!selectedId ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 bg-slate-50 text-slate-400">
          <MessageSquare size={48} className="opacity-30" />
          <p className="text-base font-medium">Select a conversation</p>
          <p className="text-sm">Pick a customer from the left to view messages</p>
        </div>
      ) : (
        <div className="flex-1 flex flex-col bg-slate-50">
          {/* Chat header */}
          <div className="flex items-center justify-between px-5 py-3 bg-white border-b border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center">
                {selectedCustomer?.profile_picture ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={selectedCustomer.profile_picture} alt={selectedCustomer.name} className="w-9 h-9 rounded-full object-cover" />
                ) : (
                  <span className="text-indigo-600 font-semibold text-sm">
                    {selectedCustomer?.name.charAt(0).toUpperCase()}
                  </span>
                )}
              </div>
              <div>
                <p className="font-semibold text-slate-900 text-sm">{selectedCustomer?.name}</p>
                <p className="text-xs text-slate-400">{selectedCustomer?.phone_number}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${CHANNEL_CONFIG[channel].bg} ${CHANNEL_CONFIG[channel].color}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${CHANNEL_CONFIG[channel].dot}`} />
                {CHANNEL_CONFIG[channel].label}
              </span>
              <button onClick={() => selectedId && loadMessages(selectedId)}
                className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100">
                <RefreshCw size={14} />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-2">
            {loadingMessages ? (
              <div className="flex justify-center py-10">
                <Loader2 size={24} className="animate-spin text-slate-400" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-2 text-slate-400">
                <MessageSquare size={32} className="opacity-30" />
                <p className="text-sm">No messages yet</p>
              </div>
            ) : (
              messages.map((msg) => {
                const isOut = msg.direction === "outgoing";
                return (
                  <div key={msg.id} className={`flex ${isOut ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[72%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                      isOut
                        ? "bg-indigo-600 text-white rounded-br-sm"
                        : "bg-white text-slate-800 shadow-sm border border-slate-100 rounded-bl-sm"
                    }`}>
                      {msg.image_url && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={msg.image_url} alt="attachment" className="rounded-lg mb-1.5 max-w-full" />
                      )}
                      <p>{msg.content}</p>
                      <p className={`text-[10px] mt-1 ${isOut ? "text-indigo-200" : "text-slate-400"} text-right`}>
                        {msg.created_at ? timeAgo(msg.created_at) : ""}
                      </p>
                    </div>
                  </div>
                );
              })
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <form onSubmit={handleSend}
            className="flex items-end gap-2 px-4 py-3 bg-white border-t border-slate-200">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(e as unknown as React.FormEvent); } }}
              placeholder={`Message via ${CHANNEL_CONFIG[channel].label}…`}
              rows={1}
              className="flex-1 px-4 py-2.5 text-sm border border-slate-200 rounded-2xl outline-none focus:ring-2 focus:ring-indigo-500 resize-none max-h-32"
              style={{ minHeight: "42px" }}
            />
            <button type="submit" disabled={sending || !draft.trim()}
              className="w-10 h-10 rounded-full bg-indigo-600 text-white flex items-center justify-center hover:bg-indigo-700 disabled:opacity-50 transition-colors shrink-0">
              {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

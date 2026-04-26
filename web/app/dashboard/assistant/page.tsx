"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AssistantChat from "@/components/AssistantChat";
import { assistantApi, type AssistantConversationSummary } from "@/lib/api";
import { Plus, MessageSquare, Trash2, Loader2, Pencil, Check, X, Bot } from "lucide-react";

// Agent label + colour for sidebar badges (matches AGENT_COLORS in AssistantChat.tsx)
const AGENT_META: Record<string, { label: string; cls: string }> = {
  general:           { label: "Zilo",             cls: "bg-brand/15 text-brand-dark" },
  sales:             { label: "Sales",            cls: "bg-emerald-100 text-emerald-700" },
  customers:         { label: "Customers",        cls: "bg-brand/15 text-brand-dark" },
  orders:            { label: "Orders",           cls: "bg-orange-100 text-orange-700" },
  broadcasts:        { label: "Broadcasts",       cls: "bg-cyan-100 text-cyan-700" },
  follow_ups:        { label: "Follow-ups",       cls: "bg-amber-100 text-amber-700" },
  bookings:          { label: "Bookings",         cls: "bg-teal-100 text-teal-700" },
  finance:           { label: "Finance",          cls: "bg-green-100 text-green-700" },
  automations:       { label: "Automations",      cls: "bg-brand/15 text-brand-dark" },
  meta_ads:          { label: "Meta Ads",         cls: "bg-blue-100 text-blue-700" },
  google_ads:        { label: "Google Ads",       cls: "bg-yellow-100 text-yellow-700" },
  x_ads:             { label: "X Ads",            cls: "bg-slate-800 text-white" },
  social_media:      { label: "Social",           cls: "bg-pink-100 text-pink-700" },
  shopify:           { label: "Shopify",          cls: "bg-lime-100 text-lime-800" },
  shopify_orders:    { label: "Shopify Orders",   cls: "bg-lime-100 text-lime-800" },
  shopify_products:  { label: "Shopify Products", cls: "bg-lime-100 text-lime-800" },
  shopify_analytics: { label: "Shopify Analytics",cls: "bg-lime-100 text-lime-800" },
  stripe:            { label: "Stripe",           cls: "bg-brand/10 text-brand-dark" },
  klaviyo:           { label: "Klaviyo",          cls: "bg-green-50 text-green-700" },
  mailchimp:         { label: "Mailchimp",        cls: "bg-yellow-50 text-yellow-700" },
  brevo:             { label: "Brevo",            cls: "bg-emerald-50 text-emerald-700" },
  slack:             { label: "Slack",            cls: "bg-brand/10 text-brand-dark" },
  gmail:             { label: "Gmail",            cls: "bg-red-50 text-red-600" },
  microsoft:         { label: "Microsoft",        cls: "bg-blue-50 text-blue-700" },
  google_calendar:   { label: "Calendar",         cls: "bg-emerald-50 text-emerald-600" },
  telegram:          { label: "Telegram",         cls: "bg-sky-100 text-sky-700" },
  // Platform features
  messages:          { label: "Messages",         cls: "bg-blue-100 text-blue-700" },
  contacts:          { label: "Contacts",         cls: "bg-brand/15 text-brand-dark" },
  suppliers:         { label: "Suppliers",        cls: "bg-stone-100 text-stone-700" },
  payments:          { label: "Payments",         cls: "bg-emerald-100 text-emerald-800" },
  invoices:          { label: "Invoices",         cls: "bg-teal-100 text-teal-700" },
  quotes:            { label: "Quotes",           cls: "bg-cyan-100 text-cyan-800" },
  analytics:         { label: "Analytics",        cls: "bg-brand/15 text-brand-dark" },
  team_analytics:    { label: "Team Analytics",   cls: "bg-brand/15 text-brand-dark" },
  team:              { label: "Team",             cls: "bg-slate-200 text-slate-700" },
  inventory:         { label: "Inventory",        cls: "bg-orange-100 text-orange-700" },
  loyalty:           { label: "Loyalty",          cls: "bg-rose-100 text-rose-700" },
  nps:               { label: "Feedback",         cls: "bg-fuchsia-100 text-fuchsia-700" },
  social_inbox:      { label: "Social Inbox",     cls: "bg-pink-100 text-pink-700" },
  social_scheduler:  { label: "Scheduler",        cls: "bg-brand/10 text-brand-dark" },
  whatsapp:          { label: "WhatsApp",         cls: "bg-green-100 text-green-700" },
  shop:              { label: "Shop",             cls: "bg-amber-100 text-amber-700" },
};

// ── helpers ──────────────────────────────────────────────────────────────────
function timeAgo(iso?: string): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d === 1) return "yesterday";
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function groupByDate(list: AssistantConversationSummary[]) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const startOf7Days = startOfToday - 6 * 86400000;
  const startOf30Days = startOfToday - 29 * 86400000;

  const groups: { label: string; items: AssistantConversationSummary[] }[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Previous 7 days", items: [] },
    { label: "This month", items: [] },
    { label: "Older", items: [] },
  ];

  for (const c of list) {
    const t = c.updated_at ? new Date(c.updated_at).getTime() : 0;
    if (t >= startOfToday) groups[0].items.push(c);
    else if (t >= startOfYesterday) groups[1].items.push(c);
    else if (t >= startOf7Days) groups[2].items.push(c);
    else if (t >= startOf30Days) groups[3].items.push(c);
    else groups[4].items.push(c);
  }
  return groups.filter((g) => g.items.length > 0);
}

export default function AssistantPage() {
  const [conversations, setConversations] = useState<AssistantConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  // Bumped every time the user explicitly clicks "New" so the chat component
  // remounts with a clean slate even if activeId was already null.
  const [newNonce, setNewNonce] = useState(0);
  // Track whether the initial auto-select has already happened so re-loads
  // (e.g. after saving a new message) don't override an intentional "New" click.
  const initialLoadDone = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const list = await assistantApi.listConversations();
      // Latest first (backend already sorts by updated_at desc, but be safe)
      list.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
      setConversations(list);
      // Auto-select the most recent conversation only on the very first load.
      if (!initialLoadDone.current && list.length) {
        setActiveId(list[0].id);
      }
      initialLoadDone.current = true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not load conversations";
      setLoadError(msg);
      setConversations([]);
      // Still allow a new chat even when the list endpoint fails.
      if (!initialLoadDone.current) {
        setActiveId(null);
        initialLoadDone.current = true;
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onDelete(id: string) {
    if (!confirm("Delete this conversation?")) return;
    await assistantApi.deleteConversation(id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeId === id) setActiveId(null);
  }

  function startEdit(c: AssistantConversationSummary) {
    setEditingId(c.id);
    setEditingTitle(c.title);
  }

  async function saveEdit() {
    if (!editingId) return;
    const title = editingTitle.trim();
    if (!title) {
      setEditingId(null);
      return;
    }
    try {
      await assistantApi.renameConversation(editingId, title);
      setConversations((prev) =>
        prev.map((c) => (c.id === editingId ? { ...c, title } : c))
      );
    } catch {
      /* leave silent */
    }
    setEditingId(null);
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {loadError ? (
        <div
          className="flex shrink-0 items-center justify-between gap-3 border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-950"
          role="alert"
        >
          <p className="min-w-0">
            <span className="font-semibold">Could not load past chats.</span>{" "}
            <span className="text-amber-900/90">
              You can still talk to Zilo — use <strong>New chat</strong> in the left sidebar. If this persists, restart
              the API server and check the backend log for assistant route errors.
            </span>
            <span className="mt-0.5 block font-mono text-xs text-amber-900/80">{loadError}</span>
          </p>
          <button
            type="button"
            onClick={() => void load()}
            className="shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-950 shadow-sm hover:bg-amber-100"
          >
            Retry
          </button>
        </div>
      ) : null}
      <div className="flex min-h-0 flex-1">
      {/* Conversations sidebar */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-slate-50">
        {/* New chat button */}
        <div className="px-3 pt-3 pb-2">
          <button
            type="button"
            onClick={() => {
              setActiveId(null);
              setEditingId(null);
              setNewNonce((n) => n + 1);
            }}
            className="flex w-full items-center gap-2.5 rounded-lg bg-[#009B3A] px-3 py-2 text-[13px] font-medium text-white shadow-sm ring-2 ring-transparent transition hover:bg-[#4CD137] hover:text-[#0a2614] hover:ring-[#4CD137]/40 active:scale-[0.98]"
          >
            <Plus size={15} className="shrink-0" aria-hidden />
            New chat
          </button>
          <p className="mt-2 text-center text-[10px] leading-snug text-slate-500">
            Start here — type a message on the right, or pick a past chat below.
          </p>
        </div>

        {/* Section label */}
        <div className="px-3 pb-1 pt-2">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Recent</p>
        </div>

        {/* Conversation list — grouped by date */}
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {loading ? (
            <div className="flex justify-center py-6">
              <Loader2 size={14} className="animate-spin text-slate-400" aria-hidden />
            </div>
          ) : conversations.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
              <MessageSquare size={22} className="text-slate-300" aria-hidden />
              <p className="text-[11px] leading-relaxed text-slate-500">
                {loadError ? (
                  <>
                    List unavailable — open <strong className="text-slate-700">New chat</strong> above, then type on
                    the right.
                  </>
                ) : (
                  <>
                    No past chats yet.
                    <br />
                    Click <strong className="text-slate-700">New chat</strong>, then send your first message →
                  </>
                )}
              </p>
            </div>
          ) : (
            groupByDate(conversations).map((group) => (
              <div key={group.label}>
                {/* Date group header */}
                <p className="mt-3 mb-0.5 px-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                  {group.label}
                </p>
                {group.items.map((c) => {
                  const editing = editingId === c.id;
                  const active = activeId === c.id;
                  return (
                    <div
                      key={c.id}
                      className={`group relative flex cursor-pointer flex-col rounded-lg px-2.5 py-2 transition-colors ${
                        active
                          ? "bg-white font-semibold text-brand-dark shadow-sm"
                          : "text-slate-700 hover:bg-white hover:text-slate-900"
                      }`}
                      onClick={() => !editing && setActiveId(c.id)}
                      onDoubleClick={(e) => { e.stopPropagation(); startEdit(c); }}
                    >
                      {editing ? (
                        <div className="flex items-center gap-1">
                          <input
                            autoFocus
                            value={editingTitle}
                            onChange={(e) => setEditingTitle(e.target.value)}
                            onClick={(e) => e.stopPropagation()}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") void saveEdit();
                              if (e.key === "Escape") setEditingId(null);
                            }}
                            className="flex-1 rounded border border-brand/50 bg-white px-1.5 py-0.5 text-[12px] text-slate-900 outline-none focus:ring-1 focus:ring-brand"
                          />
                          <button type="button" onClick={(e) => { e.stopPropagation(); void saveEdit(); }} className="text-green-600 hover:text-green-700" aria-label="Save"><Check size={12} /></button>
                          <button type="button" onClick={(e) => { e.stopPropagation(); setEditingId(null); }} className="text-slate-400 hover:text-slate-600" aria-label="Cancel"><X size={12} /></button>
                        </div>
                      ) : (
                        <>
                          {/* Title row */}
                          <div className="flex items-center gap-1.5">
                            <span className="flex-1 truncate text-[13px] font-medium leading-snug">
                              {c.title}
                            </span>
                            {c.agent && c.agent !== "general" && AGENT_META[c.agent] && (
                              <span className={`inline-flex shrink-0 items-center gap-0.5 rounded-full px-1.5 py-px text-[8.5px] font-semibold ${
                                AGENT_META[c.agent].cls
                              }`}>
                                <Bot size={7} />{AGENT_META[c.agent].label}
                              </span>
                            )}
                            {/* Actions — appear on hover */}
                            <div className="relative hidden shrink-0 items-center gap-0.5 group-hover:flex">
                              <button type="button" onClick={(e) => { e.stopPropagation(); startEdit(c); }} className="rounded p-0.5 text-slate-400 hover:text-brand-dark" aria-label="Rename"><Pencil size={11} /></button>
                              <button type="button" onClick={(e) => { e.stopPropagation(); void onDelete(c.id); }} className="rounded p-0.5 text-slate-400 hover:text-red-600" aria-label="Delete"><Trash2 size={11} /></button>
                            </div>
                          </div>
                          {/* Sub-row: time ago */}
                          <span className="mt-0.5 text-[10px] text-slate-400 group-hover:text-slate-500">
                            {timeAgo(c.updated_at)}
                          </span>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Chat pane */}
      <main className="min-w-0 flex-1 overflow-hidden bg-white">
        <AssistantChat
          key={activeId ?? `new-${newNonce}`}
          conversationId={activeId}
          onConversationChange={(id) => {
            setActiveId(id);
            if (!id) return;
            setLoadError(null);
            // Optimistically add the new conversation so it appears instantly.
            setConversations((prev) => {
              if (prev.some((c) => c.id === id)) return prev;
              const stub: AssistantConversationSummary = {
                id,
                title: "New chat",
                updated_at: new Date().toISOString(),
                message_count: 1,
              };
              return [stub, ...prev];
            });
            // Reload after smart-title background task finishes (~3 s).
            setTimeout(() => void load(), 3200);
          }}
        />
      </main>
      </div>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AssistantChat from "@/components/AssistantChat";
import { assistantApi, type AssistantConversationSummary } from "@/lib/api";
import { Plus, MessageSquare, Trash2, Loader2, Pencil, Check, X } from "lucide-react";

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
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Conversations sidebar */}
      <aside className="flex w-64 flex-col border-r border-slate-200 bg-slate-50">
        {/* New chat button */}
        <div className="px-3 pt-3 pb-2">
          <button
            type="button"
            onClick={() => {
              setActiveId(null);
              setEditingId(null);
              setNewNonce((n) => n + 1);
            }}
            className="flex w-full items-center gap-2.5 rounded-lg bg-indigo-600 px-3 py-2 text-[13px] font-medium text-white transition hover:bg-indigo-700 active:scale-[0.98]"
          >
            <Plus size={15} className="text-white" />
            New chat
          </button>
        </div>

        {/* Section label */}
        <div className="px-3 pb-1 pt-2">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Recent</p>
        </div>

        {/* Conversation list — grouped by date */}
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {loading ? (
            <div className="flex justify-center py-6">
              <Loader2 size={14} className="animate-spin text-white/30" />
            </div>
          ) : conversations.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
              <MessageSquare size={22} className="text-slate-300" />
              <p className="text-[11px] text-slate-400">No conversations yet.<br />Start one above.</p>
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
                          ? "bg-white font-semibold text-indigo-700 shadow-sm"
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
                            className="flex-1 rounded border border-indigo-300 bg-white px-1.5 py-0.5 text-[12px] text-slate-900 outline-none focus:ring-1 focus:ring-indigo-400"
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
                            {/* Actions — appear on hover */}
                            <div className="relative hidden shrink-0 items-center gap-0.5 group-hover:flex">
                              <button type="button" onClick={(e) => { e.stopPropagation(); startEdit(c); }} className="rounded p-0.5 text-slate-400 hover:text-indigo-600" aria-label="Rename"><Pencil size={11} /></button>
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
      <main className="flex-1 overflow-hidden">
        <AssistantChat
          key={activeId ?? `new-${newNonce}`}
          conversationId={activeId}
          onConversationChange={(id) => {
            setActiveId(id);
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
  );
}

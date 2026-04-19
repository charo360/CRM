"use client";

import { useCallback, useEffect, useState } from "react";
import AssistantChat from "@/components/AssistantChat";
import { assistantApi, type AssistantConversationSummary } from "@/lib/api";
import { Plus, MessageSquare, Trash2, Loader2, Pencil, Check, X } from "lucide-react";

export default function AssistantPage() {
  const [conversations, setConversations] = useState<AssistantConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await assistantApi.listConversations();
      // Latest first (backend already sorts by updated_at desc, but be safe)
      list.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
      setConversations(list);
      if (!activeId && list.length) setActiveId(list[0].id);
    } finally {
      setLoading(false);
    }
  }, [activeId]);

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
      <aside className="flex w-60 flex-col border-r border-slate-200 bg-slate-50">
        <div className="flex items-center justify-between border-b border-slate-200 px-2.5 py-1.5">
          <div className="text-[12px] font-semibold uppercase tracking-wide text-slate-600">
            Conversations
          </div>
          <button
            type="button"
            onClick={() => {
              setActiveId(null);
              setEditingId(null);
            }}
            className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-2 py-0.5 text-[10.5px] font-semibold text-white hover:bg-indigo-700"
          >
            <Plus size={11} /> New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto py-0.5">
          {loading ? (
            <div className="flex justify-center p-4 text-slate-400">
              <Loader2 size={14} className="animate-spin" />
            </div>
          ) : conversations.length === 0 ? (
            <p className="px-3 py-4 text-[11px] text-slate-400">No conversations yet.</p>
          ) : (
            conversations.map((c) => {
              const editing = editingId === c.id;
              return (
                <div
                  key={c.id}
                  className={`group flex items-center gap-1.5 px-2.5 py-1 text-[12px] leading-tight cursor-pointer hover:bg-white ${
                    activeId === c.id
                      ? "bg-white font-semibold text-indigo-700"
                      : "text-slate-700"
                  }`}
                  onClick={() => !editing && setActiveId(c.id)}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    startEdit(c);
                  }}
                >
                  <MessageSquare size={11} className="shrink-0 text-slate-400" />
                  {editing ? (
                    <>
                      <input
                        autoFocus
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void saveEdit();
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        className="flex-1 rounded border border-indigo-300 bg-white px-1 py-0.5 text-[12px] outline-none focus:ring-1 focus:ring-indigo-400"
                      />
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void saveEdit();
                        }}
                        className="text-green-600 hover:text-green-700"
                        aria-label="Save"
                      >
                        <Check size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingId(null);
                        }}
                        className="text-slate-400 hover:text-slate-600"
                        aria-label="Cancel"
                      >
                        <X size={12} />
                      </button>
                    </>
                  ) : (
                    <>
                      <span className="truncate flex-1">{c.title}</span>
                      <div className="hidden items-center gap-0.5 group-hover:flex">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            startEdit(c);
                          }}
                          className="text-slate-400 hover:text-indigo-600"
                          aria-label="Rename"
                        >
                          <Pencil size={10.5} />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            void onDelete(c.id);
                          }}
                          className="text-slate-400 hover:text-red-600"
                          aria-label="Delete"
                        >
                          <Trash2 size={10.5} />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* Chat pane */}
      <main className="flex-1 overflow-hidden">
        <AssistantChat
          key={activeId ?? "new"}
          conversationId={activeId}
          onConversationChange={(id) => {
            setActiveId(id);
            void load();
          }}
        />
      </main>
    </div>
  );
}

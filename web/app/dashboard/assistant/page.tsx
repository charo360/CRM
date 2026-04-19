"use client";

import { useCallback, useEffect, useState } from "react";
import AssistantChat from "@/components/AssistantChat";
import { assistantApi, type AssistantConversationSummary } from "@/lib/api";
import { Plus, MessageSquare, Trash2, Loader2 } from "lucide-react";

export default function AssistantPage() {
  const [conversations, setConversations] = useState<AssistantConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await assistantApi.listConversations();
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

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r border-slate-200 bg-slate-50">
        <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
          <div className="text-sm font-semibold text-slate-800">Conversations</div>
          <button
            type="button"
            onClick={() => setActiveId(null)}
            className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-indigo-700"
          >
            <Plus size={12} /> New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto py-1">
          {loading ? (
            <div className="flex justify-center p-4 text-slate-400">
              <Loader2 size={16} className="animate-spin" />
            </div>
          ) : conversations.length === 0 ? (
            <p className="px-3 py-4 text-[11px] text-slate-400">No conversations yet.</p>
          ) : (
            conversations.map((c) => (
              <div
                key={c.id}
                className={`group flex items-center gap-2 px-3 py-2 text-xs cursor-pointer hover:bg-white ${
                  activeId === c.id ? "bg-white font-semibold text-indigo-700" : "text-slate-700"
                }`}
                onClick={() => setActiveId(c.id)}
              >
                <MessageSquare size={12} className="shrink-0 text-slate-400" />
                <span className="truncate flex-1">{c.title}</span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    void onDelete(c.id);
                  }}
                  className="hidden text-slate-400 hover:text-red-600 group-hover:block"
                  aria-label="Delete"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))
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

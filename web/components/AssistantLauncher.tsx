"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Sparkles, X } from "lucide-react";
import AssistantChat from "./AssistantChat";

const LS_KEY = "assistant.last_conv";

export default function AssistantLauncher() {
  const [open, setOpen] = useState(false);
  const [convId, setConvId] = useState<string | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    try {
      setConvId(localStorage.getItem(LS_KEY));
    } catch {}
  }, []);

  // Hide on the dedicated page to avoid two chats on screen
  if (pathname?.startsWith("/dashboard/assistant")) return null;
  if (pathname === "/login" || pathname === "/") return null;

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-5 right-5 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 text-white shadow-lg hover:shadow-xl"
          aria-label="Open assistant"
        >
          <Sparkles size={20} />
        </button>
      )}
      {open && (
        <div className="fixed bottom-5 right-5 z-40 flex h-[560px] w-[400px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center justify-between bg-gradient-to-r from-indigo-500 to-purple-500 px-3 py-2 text-white">
            <div className="text-sm font-semibold">Zilo Chat</div>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close">
              <X size={16} />
            </button>
          </div>
          <div className="flex-1 min-h-0">
            <AssistantChat
              compact
              conversationId={convId}
              onConversationChange={(id) => {
                setConvId(id);
                try {
                  localStorage.setItem(LS_KEY, id);
                } catch {}
              }}
            />
          </div>
        </div>
      )}
    </>
  );
}

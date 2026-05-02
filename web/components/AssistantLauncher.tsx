"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";
import { ZiloLogo } from "@/components/ZiloLogo";
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
  const liftOnInbox = pathname?.startsWith("/dashboard/social-inbox");
  const launcherPosClass = liftOnInbox ? "bottom-28 right-5" : "bottom-5 right-5";

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`fixed ${launcherPosClass} z-40 flex items-center justify-center rounded-xl border border-slate-200 bg-white p-2 shadow-lg transition hover:border-slate-300 hover:shadow-xl`}
          aria-label="Open assistant"
        >
          <ZiloLogo size={40} />
        </button>
      )}
      {open && (
        <div className={`fixed ${launcherPosClass} z-40 flex h-[560px] w-[400px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl`}>
          <div className="flex items-center justify-between bg-gradient-to-r from-brand-dark to-brand px-3 py-2 text-white">
            <div className="flex items-center gap-1">
              <ZiloLogo size={28} className="shrink-0 rounded-md bg-white/15 p-0.5" />
              <div className="text-sm font-semibold">Zilo Chat</div>
            </div>
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
                  if (id) localStorage.setItem(LS_KEY, id);
                  else localStorage.removeItem(LS_KEY);
                } catch {}
              }}
            />
          </div>
        </div>
      )}
    </>
  );
}

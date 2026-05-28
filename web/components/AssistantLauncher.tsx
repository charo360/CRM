"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
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

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Hide on the dedicated page to avoid two chats on screen
  if (pathname?.startsWith("/dashboard/assistant")) return null;
  if (pathname === "/login" || pathname === "/") return null;
  const liftOnInbox = pathname?.startsWith("/dashboard/social-inbox");
  const launcherPosClass = liftOnInbox ? "bottom-28 right-4 sm:right-5" : "bottom-4 right-4 sm:bottom-5 sm:right-5";

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
        <div
          className={`fixed z-50 flex flex-col overflow-hidden bg-white
            inset-0
            sm:inset-x-auto sm:bottom-5 sm:right-5 sm:top-auto sm:h-[min(560px,calc(100dvh-5.5rem))] sm:w-[400px] sm:rounded-2xl sm:border sm:border-slate-200 sm:shadow-2xl
            ${liftOnInbox ? "sm:bottom-28" : ""}`}
        >
          <div className="flex min-h-0 flex-1 flex-col">
            <AssistantChat
              compact
              conversationId={convId}
              onClose={() => setOpen(false)}
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

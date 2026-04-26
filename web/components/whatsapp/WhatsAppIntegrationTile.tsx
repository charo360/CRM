"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { whatsappApi, type WhatsAppStatus } from "@/lib/api";
import { CheckCircle, Loader2, QrCode, Phone } from "lucide-react";
import { WhatsAppQrModal } from "./WhatsAppQrModal";

export function WaGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.435 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
    </svg>
  );
}

/** Compact body for Integrations grid — matches Slack/Email single-CTA tiles. */
export function WhatsAppIntegrationControls() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showQr, setShowQr] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const data = await whatsappApi.status();
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    const interval = setInterval(loadStatus, 10000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  return (
    <>
      {showQr && (
        <WhatsAppQrModal
          onConnected={() => {
            setShowQr(false);
            void loadStatus();
          }}
          onClose={() => setShowQr(false)}
        />
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-1.5 py-0.5 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          …
        </div>
      ) : status?.connected ? (
        <div className="space-y-2">
          <div className="flex items-center gap-1 text-[11px] font-medium text-green-700">
            <CheckCircle size={12} className="shrink-0" />
            <span className="truncate">
              Connected
              {status.number ? (
                <span className="ml-1 font-normal text-slate-500">
                  <Phone size={10} className="mr-0.5 inline opacity-80" />
                  {status.number}
                </span>
              ) : null}
            </span>
          </div>
          <Link
            href="/dashboard/whatsapp"
            className="flex w-full items-center justify-center rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-center text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            Manage
          </Link>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowQr(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-[#25D366] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#20bd5a]"
        >
          <QrCode size={12} />
          Connect
        </button>
      )}
    </>
  );
}

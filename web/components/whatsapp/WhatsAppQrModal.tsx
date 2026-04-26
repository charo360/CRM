"use client";

import { useEffect, useRef, useState } from "react";
import { whatsappApi } from "@/lib/api";
import { Loader2, QrCode, X } from "lucide-react";

export function WhatsAppQrModal({
  onConnected,
  onClose,
}: {
  onConnected: () => void;
  onClose: () => void;
}) {
  const [qrBase64, setQrBase64] = useState("");
  const [starting, setStarting] = useState(true);
  const [error, setError] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const didInit = useRef(false);
  const onConnectedRef = useRef(onConnected);
  onConnectedRef.current = onConnected;

  function stopPolls() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (refreshRef.current) {
      clearInterval(refreshRef.current);
      refreshRef.current = null;
    }
  }

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const t = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft]);

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;

    function startStatusPoll() {
      pollRef.current = setInterval(async () => {
        try {
          const s = await whatsappApi.status();
          if (s.connected) {
            stopPolls();
            onConnectedRef.current();
          }
        } catch {
          /* ignore */
        }
      }, 5000);
    }

    function startQrRefresh() {
      setSecondsLeft(20);
      refreshRef.current = setInterval(async () => {
        try {
          const data = await whatsappApi.qrFetch();
          if (data.qr_base64) setQrBase64(data.qr_base64);
          setSecondsLeft(20);
        } catch {
          /* ignore */
        }
      }, 20000);
    }

    async function init() {
      setStarting(true);
      setError("");
      try {
        const data = await whatsappApi.qrStart();
        if (data.qr_base64) {
          setQrBase64(data.qr_base64);
        } else {
          setError("QR code not available. Please try again.");
        }
        setStarting(false);
        startStatusPoll();
        startQrRefresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to generate QR code");
        setStarting(false);
      }
    }

    void init();
    return () => stopPolls();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-green-100">
              <QrCode size={18} className="text-green-600" />
            </div>
            <div>
              <p className="text-[14px] font-semibold text-slate-800">Scan with WhatsApp</p>
              <p className="text-[11px] text-slate-400">Open WhatsApp → Linked Devices → Link a Device</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              stopPolls();
              onClose();
            }}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-col items-center gap-4 px-6 py-6">
          {starting ? (
            <div className="flex h-56 w-56 flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-200">
              <Loader2 size={28} className="animate-spin text-slate-300" />
              <p className="text-[12px] text-slate-400">Generating QR code…</p>
            </div>
          ) : error ? (
            <div className="flex h-56 w-56 flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-red-200 bg-red-50">
              <p className="text-center text-[12px] text-red-500">{error}</p>
            </div>
          ) : qrBase64 ? (
            <div className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={qrBase64.startsWith("data:") ? qrBase64 : `data:image/png;base64,${qrBase64}`}
                alt="WhatsApp QR Code"
                className="h-56 w-56 rounded-xl border border-slate-200"
              />
              <div className="mt-2 flex items-center justify-center gap-1.5">
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-400" />
                <p className="text-[11px] text-slate-500">
                  Refreshes in <span className="font-semibold text-slate-700">{secondsLeft}s</span>
                </p>
              </div>
            </div>
          ) : (
            <div className="flex h-56 w-56 flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-200">
              <p className="text-[12px] text-slate-400">QR code not available</p>
            </div>
          )}

          <ol className="w-full space-y-1.5 text-[12px] text-slate-500">
            <li className="flex items-start gap-2">
              <span className="font-bold text-green-600">1.</span> Open WhatsApp on your phone
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-green-600">2.</span> Tap Menu (⋮) → Linked Devices
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-green-600">3.</span> Tap &quot;Link a Device&quot; and scan the QR code above
            </li>
          </ol>
        </div>

        <div className="rounded-b-2xl border-t border-slate-100 bg-slate-50 px-5 py-3">
          <p className="text-center text-[11px] text-slate-400">Waiting for scan… this page will update automatically</p>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { whatsappApi, type WhatsAppStatus, contactsApi } from "@/lib/api";
import {
  MessageSquare, Wifi, WifiOff, RefreshCw, Phone,
  Users, Download, QrCode, X, CheckCircle2, Loader2,
} from "lucide-react";

// ─── QR Code Modal ────────────────────────────────────────────────────────────
function QrModal({ onConnected, onClose }: { onConnected: () => void; onClose: () => void }) {
  const [qrBase64, setQrBase64] = useState("");
  const [starting, setStarting] = useState(true);
  const [error, setError] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolls = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (refreshRef.current) clearInterval(refreshRef.current);
  }, []);

  // Poll connection status every 5s
  const startStatusPoll = useCallback(() => {
    pollRef.current = setInterval(async () => {
      try {
        const s = await whatsappApi.status();
        if (s.connected) {
          stopPolls();
          onConnected();
        }
      } catch { /* ignore */ }
    }, 5000);
  }, [onConnected, stopPolls]);

  // Refresh QR every 20s (QR codes expire)
  const startQrRefresh = useCallback(() => {
    setSecondsLeft(20);
    refreshRef.current = setInterval(async () => {
      try {
        const data = await whatsappApi.qrFetch();
        if (data.qr_base64) setQrBase64(data.qr_base64);
        setSecondsLeft(20);
      } catch { /* ignore */ }
    }, 20000);
  }, []);

  // Countdown timer display
  useEffect(() => {
    if (secondsLeft <= 0) return;
    const t = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft]);

  useEffect(() => {
    async function init() {
      setStarting(true);
      setError("");
      try {
        const data = await whatsappApi.qrStart();
        setQrBase64(data.qr_base64 || "");
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
  }, [startStatusPoll, startQrRefresh, stopPolls]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl bg-white shadow-2xl">
        {/* Header */}
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
          <button type="button" onClick={() => { stopPolls(); onClose(); }}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100">
            <X size={16} />
          </button>
        </div>

        {/* QR area */}
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
                <div className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
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
            <li className="flex items-start gap-2"><span className="font-bold text-green-600">1.</span> Open WhatsApp on your phone</li>
            <li className="flex items-start gap-2"><span className="font-bold text-green-600">2.</span> Tap Menu (⋮) → Linked Devices</li>
            <li className="flex items-start gap-2"><span className="font-bold text-green-600">3.</span> Tap "Link a Device" and scan the QR code above</li>
          </ol>
        </div>

        <div className="rounded-b-2xl border-t border-slate-100 bg-slate-50 px-5 py-3">
          <p className="text-center text-[11px] text-slate-400">
            Waiting for scan… this page will update automatically
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function WhatsAppPage() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showQr, setShowQr] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const data = await whatsappApi.status();
      setStatus(data);
    } catch (e) {
      console.error("Failed to load WhatsApp status:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    const interval = setInterval(loadStatus, 10000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  async function handleDisconnect() {
    if (!confirm("Disconnect WhatsApp? This will stop auto-replies.")) return;
    try {
      await whatsappApi.disconnect();
      await loadStatus();
    } catch { alert("Failed to disconnect"); }
  }

  async function handleSync() {
    setSyncing(true);
    try {
      await whatsappApi.sync();
      alert("Sync started! Check contacts page in a few minutes.");
    } catch { alert("Failed to start sync"); }
    finally { setSyncing(false); }
  }

  if (loading) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-200 rounded w-1/3" />
          <div className="h-32 bg-slate-200 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {showQr && (
        <QrModal
          onConnected={() => { setShowQr(false); void loadStatus(); }}
          onClose={() => setShowQr(false)}
        />
      )}

      <div>
        <h1 className="text-2xl font-bold text-slate-900">WhatsApp Integration</h1>
        <p className="text-slate-500 text-sm mt-1">Connect your WhatsApp Business account</p>
      </div>

      {/* Status Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${status?.connected ? "bg-green-500 animate-pulse" : "bg-red-400"}`} />
            <h2 className="text-lg font-semibold text-slate-900">Connection Status</h2>
          </div>
          <button onClick={() => void loadStatus()}
            className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-50">
            <RefreshCw size={16} />
          </button>
        </div>

        {status?.connected ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-green-700">
              <CheckCircle2 size={20} />
              <span className="font-semibold">Connected</span>
              {status.number && (
                <span className="ml-2 text-sm text-slate-500">
                  <Phone size={13} className="inline mr-1" />{status.number}
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-slate-500 text-xs">Messages Today</p>
                <p className="font-bold text-slate-900 mt-0.5">{status.daily_sent || 0} / {status.daily_limit || "∞"}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-slate-500 text-xs">Monthly</p>
                <p className="font-bold text-slate-900 mt-0.5">{status.messages_sent || 0} / {status.messages_limit || "∞"}</p>
              </div>
            </div>
            <div className="flex gap-2 pt-1">
              <button onClick={handleSync} disabled={syncing}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                <Users size={15} className={syncing ? "animate-spin" : ""} />
                Sync Contacts
              </button>
              <button onClick={handleDisconnect}
                className="px-4 py-2 border border-red-200 text-red-600 text-sm font-medium rounded-lg hover:bg-red-50">
                Disconnect
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="flex items-center gap-2 text-red-600">
              <WifiOff size={18} />
              <span className="font-medium">Not Connected</span>
            </div>

            {/* QR connect — primary */}
            <button
              onClick={() => setShowQr(true)}
              className="flex w-full items-center gap-4 rounded-xl border-2 border-green-200 bg-green-50 p-4 text-left hover:border-green-400 hover:bg-green-100 transition-colors"
            >
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-green-600 text-white">
                <QrCode size={22} />
              </div>
              <div>
                <p className="font-semibold text-slate-800">Connect with QR Code</p>
                <p className="text-sm text-slate-500">Open WhatsApp → Linked Devices → scan the QR</p>
              </div>
            </button>

            <p className="text-center text-xs text-slate-400">
              No phone number or pairing code needed — just scan and you&apos;re connected.
            </p>
          </div>
        )}
      </div>

      {/* Contact Tools */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Contact Management</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button onClick={() => { contactsApi.backfillNames(); alert("Name backfill started!"); }}
            className="flex items-center gap-3 p-4 border border-slate-200 rounded-lg hover:bg-slate-50 text-left">
            <Users size={20} className="text-indigo-600" />
            <div>
              <p className="font-medium text-slate-900">Fix Contact Names</p>
              <p className="text-sm text-slate-500">Update "Contact XXXX" names from WhatsApp</p>
            </div>
          </button>
          <button onClick={() => { contactsApi.refreshProfilePictures(); alert("Profile picture refresh started!"); }}
            className="flex items-center gap-3 p-4 border border-slate-200 rounded-lg hover:bg-slate-50 text-left">
            <Download size={20} className="text-green-600" />
            <div>
              <p className="font-medium text-slate-900">Refresh Profile Pictures</p>
              <p className="text-sm text-slate-500">Download latest profile photos</p>
            </div>
          </button>
        </div>
      </div>

      {/* Usage Stats */}
      {status?.connected && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Usage Statistics</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-2xl font-bold text-slate-900">{status.daily_sent || 0}</p>
              <p className="text-sm text-slate-500">Messages Today</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-2xl font-bold text-slate-900">{status.messages_remaining || "∞"}</p>
              <p className="text-sm text-slate-500">Remaining This Month</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <p className="text-2xl font-bold text-slate-900">{status.plan || "Free"}</p>
              <p className="text-sm text-slate-500">Current Plan</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

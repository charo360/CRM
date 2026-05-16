"use client";

import { useCallback, useEffect, useState } from "react";
import { whatsappApi, type WhatsAppStatus, contactsApi } from "@/lib/api";
import { WhatsAppQrModal } from "@/components/whatsapp/WhatsAppQrModal";
import {
  WifiOff, RefreshCw, Phone,
  Users, Download, QrCode, CheckCircle2, Loader2,
} from "lucide-react";

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
    <div className="p-6 w-full max--4xl mx-auto space-y-6">
      {showQr && (
        <WhatsAppQrModal
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
                className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm font-medium rounded-lg hover:bg-brand disabled:opacity-50">
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
            <Users size={20} className="text-brand-dark" />
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

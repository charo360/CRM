"use client";

import { useEffect, useState } from "react";
import { whatsappApi, WhatsAppStatus, contactsApi } from "@/lib/api";
import { MessageSquare, Wifi, WifiOff, RefreshCw, Phone, Users, Download } from "lucide-react";

export default function WhatsAppPage() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [pairingCode, setPairingCode] = useState("");
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 10000); // Check every 10s
    return () => clearInterval(interval);
  }, []);

  async function loadStatus() {
    try {
      const data = await whatsappApi.status();
      setStatus(data);
    } catch (e) {
      console.error("Failed to load WhatsApp status:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleConnect() {
    if (!phoneNumber.trim()) {
      alert("Please enter your phone number");
      return;
    }
    setConnecting(true);
    try {
      const result = await whatsappApi.connect(phoneNumber);
      if (result.pairing_code) {
        setPairingCode(result.pairing_code);
      }
      await loadStatus();
    } catch (e) {
      console.error("Failed to connect:", e);
      alert("Failed to connect WhatsApp");
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    if (!confirm("Disconnect WhatsApp? This will stop auto-replies.")) return;
    try {
      await whatsappApi.disconnect();
      setPairingCode("");
      await loadStatus();
    } catch (e) {
      console.error("Failed to disconnect:", e);
      alert("Failed to disconnect");
    }
  }

  async function handleSync() {
    setSyncing(true);
    try {
      await whatsappApi.sync();
      alert("Sync started! Check contacts page in a few minutes.");
    } catch (e) {
      console.error("Failed to sync:", e);
      alert("Failed to start sync");
    } finally {
      setSyncing(false);
    }
  }

  async function handleBackfillNames() {
    try {
      await contactsApi.backfillNames();
      alert("Name backfill started!");
    } catch (e) {
      console.error("Failed to backfill names:", e);
      alert("Failed to backfill names");
    }
  }

  async function handleRefreshPictures() {
    try {
      await contactsApi.refreshProfilePictures();
      alert("Profile picture refresh started!");
    } catch (e) {
      console.error("Failed to refresh pictures:", e);
      alert("Failed to refresh profile pictures");
    }
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
      <div>
        <h1 className="text-2xl font-bold text-slate-900">WhatsApp Integration</h1>
        <p className="text-slate-500 text-sm mt-1">Connect your WhatsApp Business account</p>
      </div>

      {/* Status Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${status?.connected ? "bg-green-500" : "bg-red-500"}`} />
            <h2 className="text-lg font-semibold text-slate-900">Connection Status</h2>
          </div>
          <button
            onClick={loadStatus}
            className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-50"
          >
            <RefreshCw size={16} />
          </button>
        </div>

        {status?.connected ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-green-700">
              <Wifi size={20} />
              <span className="font-medium">Connected</span>
            </div>
            {status.number && (
              <p className="text-sm text-slate-600">
                <Phone size={14} className="inline mr-1" />
                {status.number}
              </p>
            )}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-slate-500">Messages Today</p>
                <p className="font-semibold text-slate-900">{status.daily_sent || 0} / {status.daily_limit || "∞"}</p>
              </div>
              <div>
                <p className="text-slate-500">Monthly Limit</p>
                <p className="font-semibold text-slate-900">{status.messages_sent || 0} / {status.messages_limit || "∞"}</p>
              </div>
            </div>
            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSync}
                disabled={syncing}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                <Users size={16} className={syncing ? "animate-spin" : ""} />
                Sync Contacts
              </button>
              <button
                onClick={handleDisconnect}
                className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700"
              >
                Disconnect
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-red-700">
              <WifiOff size={20} />
              <span className="font-medium">Not Connected</span>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Phone Number (with country code)
                </label>
                <input
                  type="tel"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="+254700000000"
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <button
                onClick={handleConnect}
                disabled={connecting}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                <MessageSquare size={16} />
                {connecting ? "Connecting..." : "Connect WhatsApp"}
              </button>
            </div>
          </div>
        )}

        {pairingCode && (
          <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <h3 className="font-medium text-blue-900 mb-2">Pairing Code</h3>
            <div className="flex items-center gap-3">
              <code className="text-2xl font-mono font-bold text-blue-700 bg-white px-3 py-2 rounded border">
                {pairingCode}
              </code>
              <button
                onClick={() => navigator.clipboard.writeText(pairingCode)}
                className="text-sm text-blue-600 hover:underline"
              >
                Copy
              </button>
            </div>
            <p className="text-sm text-blue-700 mt-2">
              Enter this code in WhatsApp → Settings → Linked Devices → Link a Device
            </p>
          </div>
        )}
      </div>

      {/* Tools */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Contact Management</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button
            onClick={handleBackfillNames}
            className="flex items-center gap-3 p-4 border border-slate-200 rounded-lg hover:bg-slate-50 text-left"
          >
            <Users size={20} className="text-indigo-600" />
            <div>
              <p className="font-medium text-slate-900">Fix Contact Names</p>
              <p className="text-sm text-slate-500">Update "Contact XXXX" names from WhatsApp</p>
            </div>
          </button>
          <button
            onClick={handleRefreshPictures}
            className="flex items-center gap-3 p-4 border border-slate-200 rounded-lg hover:bg-slate-50 text-left"
          >
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

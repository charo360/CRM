"use client";

import { useEffect, useState, useCallback } from "react";
import { whatsappApi, WhatsAppStatus } from "@/lib/api";
import {
  CheckCircle2, XCircle, Loader2, ExternalLink,
  Smartphone, RefreshCw, Wifi, WifiOff, Copy,
} from "lucide-react";

// ── Instagram SVG ─────────────────────────────────────────────────────────────
function InstagramIcon({ size = 24, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

// ── Channel registry ──────────────────────────────────────────────────────────
// Add future channels here — one object per channel, nothing else changes.

type ChannelId = "whatsapp" | "instagram";

interface ChannelDef {
  id: ChannelId;
  name: string;
  description: string;
  icon: React.ReactNode;
  accentBorder: string;
  accentBg: string;
  accentButton: string;
}

const CHANNELS: ChannelDef[] = [
  {
    id: "whatsapp",
    name: "WhatsApp",
    description:
      "Connect your WhatsApp number to send and receive messages, automate replies, and manage orders in real time.",
    icon: <Smartphone size={26} className="text-[#25D366]" />,
    accentBorder: "border-[#25D366]/40",
    accentBg: "bg-[#25D366]/5",
    accentButton: "bg-[#25D366] hover:bg-[#1ebe59]",
  },
  {
    id: "instagram",
    name: "Instagram",
    description:
      "Connect your Instagram Business account to manage DMs, automate replies, and track customer conversations.",
    icon: <InstagramIcon size={26} className="text-[#E1306C]" />,
    accentBorder: "border-[#E1306C]/40",
    accentBg: "bg-[#E1306C]/5",
    accentButton: "bg-gradient-to-r from-[#833ab4] via-[#fd1d1d] to-[#fcb045] hover:opacity-90",
  },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ChannelsPage() {
  const [waStatus, setWaStatus] = useState<WhatsAppStatus | null>(null);
  const [waLoading, setWaLoading] = useState(true);
  const [activeModal, setActiveModal] = useState<ChannelId | null>(null);
  // Instagram: simulated connected state (wire to real OAuth when ready)
  const [igConnected, setIgConnected] = useState(false);
  const [igAccount, setIgAccount] = useState("");

  const loadWaStatus = useCallback(async () => {
    setWaLoading(true);
    try {
      const s = await whatsappApi.status();
      setWaStatus(s);
    } catch {
      setWaStatus(null);
    } finally {
      setWaLoading(false);
    }
  }, []);

  useEffect(() => { loadWaStatus(); }, [loadWaStatus]);

  async function handleDisconnect() {
    if (!confirm("Disconnect WhatsApp?")) return;
    await whatsappApi.disconnect().catch(() => {});
    await loadWaStatus();
  }

  async function handleSync() {
    await whatsappApi.sync().catch(() => {});
    await loadWaStatus();
  }

  function openModal(id: ChannelId) {
    if (id === "whatsapp" && waStatus?.connected) {
      handleDisconnect();
      return;
    }
    if (id === "instagram" && igConnected) {
      setIgConnected(false);
      return;
    }
    setActiveModal(id);
  }

  const waConnected = waStatus?.connected ?? false;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Channels</h1>
          <p className="text-slate-500 text-sm mt-1">
            Connect your messaging platforms. All conversations flow into the{" "}
            <a href="/dashboard/messages" className="text-indigo-600 hover:underline">unified inbox</a>.
          </p>
        </div>
        {waConnected && (
          <button onClick={handleSync}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
            <RefreshCw size={14} /> Sync contacts
          </button>
        )}
      </div>

      {/* Channel cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* WhatsApp */}
        {(() => {
          const ch = CHANNELS[0];
          return (
            <ChannelCard
              channel={ch}
              connected={waConnected}
              loading={waLoading}
              accountLabel={waStatus?.number}
              stats={waConnected ? [
                `${waStatus?.daily_sent ?? 0} / ${waStatus?.daily_limit ?? 500} msgs today`,
                `Plan: ${waStatus?.plan ?? "free"}`,
              ] : undefined}
              onAction={() => openModal(ch.id)}
            />
          );
        })()}

        {/* Instagram */}
        {(() => {
          const ch = CHANNELS[1];
          return (
            <ChannelCard
              channel={ch}
              connected={igConnected}
              loading={false}
              accountLabel={igAccount || undefined}
              onAction={() => openModal(ch.id)}
            />
          );
        })()}
      </div>

      {/* Modals */}
      {activeModal === "whatsapp" && (
        <Modal title="Connect WhatsApp" onClose={() => setActiveModal(null)}>
          <WhatsAppConnectFlow onConnected={() => { setActiveModal(null); loadWaStatus(); }} />
        </Modal>
      )}

      {activeModal === "instagram" && (
        <Modal title="Connect Instagram" onClose={() => setActiveModal(null)}>
          <InstagramConnectFlow
            onConnected={(handle) => { setIgAccount(handle); setIgConnected(true); setActiveModal(null); }}
          />
        </Modal>
      )}
    </div>
  );
}

// ── Channel card ──────────────────────────────────────────────────────────────

function ChannelCard({
  channel, connected, loading, accountLabel, stats, onAction,
}: {
  channel: ChannelDef;
  connected: boolean;
  loading: boolean;
  accountLabel?: string;
  stats?: string[];
  onAction: () => void;
}) {
  return (
    <div className={`rounded-2xl border-2 p-6 flex flex-col gap-4 transition-shadow hover:shadow-md ${channel.accentBorder} ${channel.accentBg}`}>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {channel.icon}
          <div>
            <h2 className="font-bold text-slate-900">{channel.name}</h2>
            {connected && accountLabel && (
              <p className="text-xs text-slate-500 mt-0.5">{accountLabel}</p>
            )}
          </div>
        </div>
        {loading ? (
          <Loader2 size={16} className="animate-spin text-slate-400 mt-1" />
        ) : connected ? (
          <span className="flex items-center gap-1 text-xs font-medium text-green-700 bg-green-100 px-2 py-0.5 rounded-full">
            <Wifi size={11} /> Connected
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
            <WifiOff size={11} /> Not connected
          </span>
        )}
      </div>

      <p className="text-sm text-slate-600 leading-relaxed">{channel.description}</p>

      {connected && stats && (
        <div className="flex gap-3 text-xs text-slate-500 border-t border-white/60 pt-3 flex-wrap">
          {stats.map((s, i) => <span key={i} className="flex items-center gap-1"><CheckCircle2 size={11} className="text-green-500" />{s}</span>)}
        </div>
      )}

      <button
        onClick={onAction}
        disabled={loading}
        className={`w-full py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all disabled:opacity-50 text-white ${
          connected
            ? "bg-slate-700 hover:bg-red-600"
            : channel.accentButton
        }`}
      >
        {loading && <Loader2 size={14} className="animate-spin" />}
        {connected ? "Disconnect" : `Connect ${channel.name}`}
      </button>
    </div>
  );
}

// ── WhatsApp connect flow (phone number pairing) ──────────────────────────────

function WhatsAppConnectFlow({ onConnected }: { onConnected: () => void }) {
  const [phone, setPhone] = useState("");
  const [step, setStep] = useState<"input" | "code" | "done">("input");
  const [pairingCode, setPairingCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await whatsappApi.connect(phone);
      if (res.pairing_code) {
        setPairingCode(res.pairing_code);
        setStep("code");
      } else if (res.status === "connected") {
        onConnected();
      } else {
        setError(res.message || "Could not connect. Try again.");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }

  function copyCode() {
    navigator.clipboard.writeText(pairingCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (step === "input") {
    return (
      <div className="space-y-5">
        <div className="flex flex-col items-center gap-2 py-2">
          <div className="w-14 h-14 rounded-2xl bg-[#25D366] flex items-center justify-center">
            <Smartphone size={28} className="text-white" />
          </div>
          <p className="text-sm text-slate-600 text-center max-w-xs">
            Enter the WhatsApp number you want to connect. You'll get a pairing code to link it — no QR scan needed.
          </p>
        </div>

        <form onSubmit={handleConnect} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">WhatsApp phone number</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => { setPhone(e.target.value); setError(""); }}
              placeholder="+254700000000"
              required
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#25D366]"
            />
            <p className="text-xs text-slate-400 mt-1">Include country code, e.g. +254 for Kenya</p>
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

          <button type="submit" disabled={loading || !phone.trim()}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-[#25D366] text-white font-semibold rounded-xl hover:bg-[#1ebe59] disabled:opacity-50 text-sm">
            {loading && <Loader2 size={14} className="animate-spin" />}
            {loading ? "Connecting…" : "Get pairing code"}
          </button>
        </form>
      </div>
    );
  }

  if (step === "code") {
    return (
      <div className="space-y-5 text-center">
        <div className="flex flex-col items-center gap-2 py-2">
          <div className="w-14 h-14 rounded-2xl bg-[#25D366] flex items-center justify-center">
            <Smartphone size={28} className="text-white" />
          </div>
          <p className="font-semibold text-slate-800">Enter this code in WhatsApp</p>
          <p className="text-xs text-slate-500">
            Open WhatsApp → Settings → Linked Devices → Link a Device → Link with phone number
          </p>
        </div>

        <div className="flex items-center justify-center gap-3">
          <div className="bg-slate-900 text-white text-3xl font-mono font-bold tracking-[0.3em] px-6 py-4 rounded-2xl">
            {pairingCode}
          </div>
          <button onClick={copyCode}
            className="p-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-500 transition-colors"
            title="Copy code">
            <Copy size={16} />
          </button>
        </div>

        {copied && <p className="text-xs text-green-600">Copied!</p>}

        <p className="text-xs text-slate-400">The code expires in a few minutes.</p>

        <div className="flex gap-2">
          <button onClick={() => setStep("input")}
            className="flex-1 py-2 text-sm border border-slate-200 rounded-xl text-slate-600 hover:bg-slate-50">
            Use different number
          </button>
          <button onClick={onConnected}
            className="flex-1 py-2 text-sm bg-[#25D366] text-white rounded-xl font-semibold hover:bg-[#1ebe59]">
            I've linked it ✓
          </button>
        </div>
      </div>
    );
  }

  return null;
}

// ── Instagram connect flow ────────────────────────────────────────────────────

function InstagramConnectFlow({ onConnected }: { onConnected: (handle: string) => void }) {
  const OAUTH_URL = process.env.NEXT_PUBLIC_INSTAGRAM_OAUTH_URL || "#";

  return (
    <div className="flex flex-col items-center gap-5 py-4">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#833ab4] via-[#fd1d1d] to-[#fcb045] flex items-center justify-center">
        <InstagramIcon size={32} className="text-white" />
      </div>
      <div className="text-center space-y-2">
        <p className="font-semibold text-slate-800">Connect Instagram Business</p>
        <p className="text-sm text-slate-500 max-w-xs">
          You'll be redirected to Meta to authorize Zilo to read and send messages from your Instagram Business account.
        </p>
      </div>
      <a href={OAUTH_URL} target="_blank" rel="noopener noreferrer"
        className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-[#833ab4] via-[#fd1d1d] to-[#fcb045] text-white font-semibold text-sm rounded-xl hover:opacity-90 transition-opacity">
        <ExternalLink size={15} />
        Authorize on Instagram
      </a>
      {/* Dev-only simulate */}
      <button onClick={() => onConnected("mybusiness")}
        className="text-xs text-indigo-600 hover:underline">
        Simulate connected (dev only)
      </button>
    </div>
  );
}

// ── Shared modal ──────────────────────────────────────────────────────────────

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="font-bold text-slate-900">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import { whatsappApi, WhatsAppStatus } from "@/lib/api";
import {
  CheckCircle2,
  Loader2,
  ExternalLink,
  Smartphone,
  RefreshCw,
  Wifi,
  WifiOff,
  Mail,
  Send,
  Building2,
  Inbox,
} from "lucide-react";

function FacebookGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
    </svg>
  );
}

// ── Slack glyph (brand not in all Lucide builds) ─────────────────────────────
function SlackGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834V5.042zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.122 2.521a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zm-1.269 0a2.528 2.528 0 0 1-2.521 2.521 2.527 2.527 0 0 1-2.521-2.521V2.522A2.528 2.528 0 0 1 15.165 0a2.528 2.528 0 0 1 2.521 2.522v6.312zm-2.521 10.122a2.527 2.527 0 0 1 2.521 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.521-2.522v-2.521h2.521zm0-1.269a2.527 2.527 0 0 1-2.521-2.521 2.528 2.528 0 0 1 2.521-2.521h6.313A2.528 2.528 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.521h-6.313z" />
    </svg>
  );
}

// ── Instagram SVG (brand gradient in modals) ─────────────────────────────────
function InstagramIcon({ size = 24, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

// ── Native channels (in-page connect / demo flows) ───────────────────────────

type NativeChannelId = "whatsapp" | "instagram";

interface NativeChannelDef {
  id: NativeChannelId;
  name: string;
  description: string;
  icon: React.ReactNode;
  accentBorder: string;
  accentBg: string;
  accentButton: string;
}

const NATIVE_CHANNELS: NativeChannelDef[] = [
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
      "Connect your Instagram Business account for DMs. For ads-scale publishing, also use Social Channels (Zernio) in Integrations.",
    icon: <InstagramIcon size={26} className="text-[#E1306C]" />,
    accentBorder: "border-[#E1306C]/40",
    accentBg: "bg-[#E1306C]/5",
    accentButton: "bg-gradient-to-r from-[#833ab4] via-[#fd1d1d] to-[#fcb045] hover:opacity-90",
  },
];

// ── Channels wired through Integrations (Nango, Telegram bot, Zernio) ──────

interface IntegrationChannelDef {
  id: string;
  name: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  accentBorder: string;
  accentBg: string;
  footnote?: string;
}

const INTEGRATION_CHANNELS: IntegrationChannelDef[] = [
  {
    id: "facebook_messenger",
    name: "Facebook & Messenger",
    description:
      "Connect your Facebook Page to manage Page inbox and Messenger conversations alongside other social networks (via Zernio).",
    href: "/dashboard/integrations#integrations-social",
    icon: <FacebookGlyph className="h-[26px] w-[26px] text-[#1877F2]" />,
    accentBorder: "border-[#1877F2]/40",
    accentBg: "bg-[#1877F2]/5",
    footnote: "Messenger is included when you connect your Facebook Page.",
  },
  {
    id: "telegram",
    name: "Telegram",
    description: "Connect a bot with your token from @BotFather — free bot messaging alongside your CRM.",
    href: "/dashboard/integrations#integrations-messaging",
    icon: <Send size={26} className="text-[#229ED9]" />,
    accentBorder: "border-[#229ED9]/40",
    accentBg: "bg-sky-50/80",
  },
  {
    id: "slack",
    name: "Slack",
    description: "Send workspace notifications and keep your team in the loop when things happen in Zilo.",
    href: "/dashboard/integrations#integrations-slack",
    icon: <SlackGlyph className="h-[26px] w-[26px] text-[#4A154B]" />,
    accentBorder: "border-[#4A154B]/35",
    accentBg: "bg-[#4A154B]/5",
  },
  {
    id: "gmail",
    name: "Gmail",
    description: "Connect Google Mail for inbox features, drafts, and email workflows inside Zilo.",
    href: "/dashboard/integrations#integrations-gmail",
    icon: <Mail size={26} className="text-red-500" />,
    accentBorder: "border-red-200",
    accentBg: "bg-red-50/60",
  },
  {
    id: "microsoft",
    name: "Microsoft 365",
    description: "Outlook mail, calendar, and contacts — same place you run your business email today.",
    href: "/dashboard/integrations#integrations-microsoft",
    icon: <Building2 size={26} className="text-[#0078D4]" />,
    accentBorder: "border-[#0078D4]/35",
    accentBg: "bg-[#0078D4]/5",
  },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ChannelsPage() {
  const [waStatus, setWaStatus] = useState<WhatsAppStatus | null>(null);
  const [waLoading, setWaLoading] = useState(true);
  const [activeModal, setActiveModal] = useState<NativeChannelId | null>(null);
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

  useEffect(() => {
    void loadWaStatus();
  }, [loadWaStatus]);

  async function handleDisconnect() {
    if (!confirm("Disconnect WhatsApp?")) return;
    await whatsappApi.disconnect().catch(() => {});
    await loadWaStatus();
  }

  async function handleSync() {
    await whatsappApi.sync().catch(() => {});
    await loadWaStatus();
  }

  function openModal(id: NativeChannelId) {
    if (id === "whatsapp" && waStatus?.connected) {
      void handleDisconnect();
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
    <div className="mx-auto max-w-5xl space-y-8 p-6 text-slate-900">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Channels</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Connect the places customers reach you — WhatsApp, Instagram, Facebook &amp; Messenger, Telegram, Slack,
            email, and every network available through{" "}
            <Link href="/dashboard/integrations" className="font-medium text-[#009B3A] hover:underline">
              Integrations
            </Link>
            . Messages still land in your{" "}
            <a href="/dashboard/messages" className="font-medium text-[#009B3A] hover:underline">
              unified inbox
            </a>{" "}
            where supported.
          </p>
        </div>
        {waConnected && (
          <button
            type="button"
            onClick={() => void handleSync()}
            className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw size={14} aria-hidden /> Sync contacts
          </button>
        )}
      </div>

      <section>
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500">Connect here</h2>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <ChannelCard
            channel={NATIVE_CHANNELS[0]}
            connected={waConnected}
            loading={waLoading}
            accountLabel={waStatus?.number}
            stats={
              waConnected
                ? [
                    `${waStatus?.daily_sent ?? 0} / ${waStatus?.daily_limit ?? 500} msgs today`,
                    `Plan: ${waStatus?.plan ?? "free"}`,
                  ]
                : undefined
            }
            onAction={() => openModal("whatsapp")}
          />
          <ChannelCard
            channel={NATIVE_CHANNELS[1]}
            connected={igConnected}
            loading={false}
            accountLabel={igAccount || undefined}
            onAction={() => openModal("instagram")}
          />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
          Connect in Integrations
        </h2>
        <p className="mb-4 text-xs leading-relaxed text-slate-500">
          Slack, Gmail, Microsoft 365, Telegram bots, and Meta social surfaces (Facebook Page, Instagram, Messenger,
          WhatsApp Business API) are authorized from the Integrations page — we deep-link you to the right block.
        </p>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {INTEGRATION_CHANNELS.map((ch) => (
            <IntegrationBridgeCard key={ch.id} channel={ch} />
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-slate-50/80 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
              <Inbox size={20} className="text-[#009B3A]" aria-hidden />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">More social networks (Zernio)</h3>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                X (Twitter), LinkedIn, TikTok, YouTube, Pinterest, Reddit, Bluesky, Threads, Google Business, Snapchat,
                Discord, and more — connect once in{" "}
                <strong className="text-slate-800">Integrations → Social Channels</strong> for paid cross-posting and
                inbox routing where available.
              </p>
            </div>
          </div>
          <Link
            href="/dashboard/integrations#integrations-social"
            className="inline-flex shrink-0 items-center justify-center gap-2 self-start rounded-xl bg-[#009B3A] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#4CD137] hover:text-[#0a2614] sm:self-center"
          >
            Open social channels
            <ExternalLink size={14} aria-hidden />
          </Link>
        </div>
        <p className="mt-3 text-[11px] text-slate-500">
          Tip: use{" "}
          <Link href="/dashboard/social-inbox" className="font-medium text-[#009B3A] hover:underline">
            Social Inbox
          </Link>{" "}
          and{" "}
          <Link href="/dashboard/social-scheduler" className="font-medium text-[#009B3A] hover:underline">
            Social scheduler
          </Link>{" "}
          after accounts are linked.
        </p>
      </section>

      {/* Modals */}
      {activeModal === "whatsapp" && (
        <Modal title="Connect WhatsApp" onClose={() => setActiveModal(null)}>
          <WhatsAppConnectFlow
            onConnected={() => {
              setActiveModal(null);
              void loadWaStatus();
            }}
          />
        </Modal>
      )}

      {activeModal === "instagram" && (
        <Modal title="Connect Instagram" onClose={() => setActiveModal(null)}>
          <InstagramConnectFlow
            onConnected={(handle) => {
              setIgAccount(handle);
              setIgConnected(true);
              setActiveModal(null);
            }}
          />
        </Modal>
      )}
    </div>
  );
}

// ── Native channel card ───────────────────────────────────────────────────────

function ChannelCard({
  channel,
  connected,
  loading,
  accountLabel,
  stats,
  onAction,
}: {
  channel: NativeChannelDef;
  connected: boolean;
  loading: boolean;
  accountLabel?: string;
  stats?: string[];
  onAction: () => void;
}) {
  return (
    <div
      className={`flex flex-col gap-4 rounded-2xl border-2 p-6 transition-shadow hover:shadow-md ${channel.accentBorder} ${channel.accentBg}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {channel.icon}
          <div>
            <h2 className="font-bold text-slate-900">{channel.name}</h2>
            {connected && accountLabel ? <p className="mt-0.5 text-xs text-slate-500">{accountLabel}</p> : null}
          </div>
        </div>
        {loading ? (
          <Loader2 size={16} className="mt-1 animate-spin text-slate-400" aria-hidden />
        ) : connected ? (
          <span className="flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
            <Wifi size={11} aria-hidden /> Connected
          </span>
        ) : (
          <span className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            <WifiOff size={11} aria-hidden /> Not connected
          </span>
        )}
      </div>

      <p className="text-sm leading-relaxed text-slate-600">{channel.description}</p>

      {connected && stats && stats.length > 0 ? (
        <div className="flex flex-wrap gap-3 border-t border-white/60 pt-3 text-xs text-slate-500">
          {stats.map((s, i) => (
            <span key={i} className="flex items-center gap-1">
              <CheckCircle2 size={11} className="text-green-500" aria-hidden />
              {s}
            </span>
          ))}
        </div>
      ) : null}

      <button
        type="button"
        onClick={onAction}
        disabled={loading}
        className={`flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-semibold text-white transition-all disabled:opacity-50 ${
          connected ? "bg-slate-700 hover:bg-red-600" : channel.accentButton
        }`}
      >
        {loading ? <Loader2 size={14} className="animate-spin" aria-hidden /> : null}
        {connected ? "Disconnect" : `Connect ${channel.name}`}
      </button>
    </div>
  );
}

// ── Integration deep-link card ────────────────────────────────────────────────

function IntegrationBridgeCard({ channel }: { channel: IntegrationChannelDef }) {
  return (
    <div
      className={`flex flex-col gap-3 rounded-2xl border-2 p-6 transition-shadow hover:shadow-md ${channel.accentBorder} ${channel.accentBg}`}
    >
      <div className="flex items-start gap-3">
        {channel.icon}
        <div className="min-w-0 flex-1">
          <h2 className="font-bold text-slate-900">{channel.name}</h2>
          <span className="mt-1 inline-flex w-fit rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-600 ring-1 ring-slate-200">
            Integrations
          </span>
        </div>
      </div>
      <p className="text-sm leading-relaxed text-slate-600">{channel.description}</p>
      {channel.footnote ? <p className="text-[11px] text-slate-500">{channel.footnote}</p> : null}
      <Link
        href={channel.href}
        className="mt-auto flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-[#009B3A]/30 hover:bg-emerald-50/50"
      >
        Set up in Integrations
        <ExternalLink size={14} className="text-slate-500" aria-hidden />
      </Link>
    </div>
  );
}

// ── WhatsApp connect flow ─────────────────────────────────────────────────────

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
    void navigator.clipboard.writeText(pairingCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (step === "input") {
    return (
      <div className="space-y-5">
        <div className="flex flex-col items-center gap-2 py-2">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#25D366]">
            <Smartphone size={28} className="text-white" aria-hidden />
          </div>
          <p className="max-w-xs text-center text-sm text-slate-600">
            Enter the WhatsApp number you want to connect. You&apos;ll get a pairing code to link it — no QR scan
            needed.
          </p>
        </div>

        <form onSubmit={handleConnect} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">WhatsApp phone number</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => {
                setPhone(e.target.value);
                setError("");
              }}
              placeholder="+254700000000"
              required
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-[#25D366]"
            />
            <p className="mt-1 text-xs text-slate-400">Include country code, e.g. +254 for Kenya</p>
          </div>

          {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p> : null}

          <button
            type="submit"
            disabled={loading || !phone.trim()}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#25D366] py-2.5 text-sm font-semibold text-white hover:bg-[#1ebe59] disabled:opacity-50"
          >
            {loading ? <Loader2 size={14} className="animate-spin" aria-hidden /> : null}
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
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#25D366]">
            <Smartphone size={28} className="text-white" aria-hidden />
          </div>
          <p className="font-semibold text-slate-800">Enter this code in WhatsApp</p>
          <p className="text-xs text-slate-500">
            Open WhatsApp → Settings → Linked Devices → Link a Device → Link with phone number
          </p>
        </div>

        <div className="flex items-center justify-center gap-3">
          <div className="rounded-2xl bg-slate-900 px-6 py-4 font-mono text-3xl font-bold tracking-[0.3em] text-white">
            {pairingCode}
          </div>
          <button
            type="button"
            onClick={copyCode}
            className="rounded-xl border border-slate-200 p-2.5 text-slate-500 transition-colors hover:bg-slate-50"
            title="Copy code"
          >
            Copy
          </button>
        </div>

        {copied ? <p className="text-xs text-green-600">Copied!</p> : null}

        <p className="text-xs text-slate-400">The code expires in a few minutes.</p>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setStep("input")}
            className="flex-1 rounded-xl border border-slate-200 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Use different number
          </button>
          <button
            type="button"
            onClick={onConnected}
            className="flex-1 rounded-xl bg-[#25D366] py-2 text-sm font-semibold text-white hover:bg-[#1ebe59]"
          >
            I&apos;ve linked it ✓
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
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[#833ab4] via-[#fd1d1d] to-[#fcb045]">
        <InstagramIcon size={32} className="text-white" />
      </div>
      <div className="space-y-2 text-center">
        <p className="font-semibold text-slate-800">Connect Instagram Business</p>
        <p className="max-w-xs text-sm text-slate-500">
          You&apos;ll be redirected to Meta to authorize Zilo to read and send messages from your Instagram Business
          account.
        </p>
      </div>
      <a
        href={OAUTH_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#833ab4] via-[#fd1d1d] to-[#fcb045] px-6 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90"
      >
        <ExternalLink size={15} aria-hidden />
        Authorize on Instagram
      </a>
      <button type="button" onClick={() => onConnected("mybusiness")} className="text-xs text-[#009B3A] hover:underline">
        Simulate connected (dev only)
      </button>
    </div>
  );
}

// ── Shared modal ──────────────────────────────────────────────────────────────

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h3 className="font-bold text-slate-900">{title}</h3>
          <button type="button" onClick={onClose} className="text-xl leading-none text-slate-400 hover:text-slate-600">
            ×
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

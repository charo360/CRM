"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState, useCallback, useMemo, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { API_BASE, telegramApi, type TelegramConnection, paystackApi, type PaystackConnection, payheroApi, type PayheroConnection, type PayheroChannel, supplierApi, type SupplierConnections, composioSocialApi, unipileApi, whatsappApi, browserApi, type WhatsAppStatus, type BrowserOperatorStatus, type ComposioFacebookPage, type ComposioLinkedInAuthor, type ComposioSocialSettings, type UnipileCheckpointResponse, type UnipileLinkedInContract } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { WaGlyph, WhatsAppIntegrationControls } from "@/components/whatsapp/WhatsAppIntegrationTile";
import { INTEGRATIONS_SOCIAL_PLATFORMS } from "@/components/ZernioSocialPanel";
import {
  buildComposioDisconnectedStatus,
  COMPOSIO_API_KEY_TOOLKITS,
  COMPOSIO_SOCIAL_TOOLKITS,
  INTEGRATIONS_COMPOSIO_TOOLKITS,
  isComposioSocialToolkit,
  readStoredComposioStatus,
  writeStoredComposioStatus,
} from "@/lib/integrations-composio";
import { useZernioAccounts } from "@/contexts/ZernioAccountsContext";
import { Plug, Mail, Calendar, CheckCircle, CheckCircle2, Loader2, AlertCircle, X, ExternalLink, Shield, Globe, RefreshCw } from "lucide-react";

// ── Glyphs ────────────────────────────────────────────────────────────────────



function SlackGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834V5.042zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.122 2.521a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zm-1.269 0a2.528 2.528 0 0 1-2.521 2.521 2.527 2.527 0 0 1-2.521-2.521V2.522A2.528 2.528 0 0 1 15.165 0a2.528 2.528 0 0 1 2.521 2.522v6.312zm-2.521 10.122a2.527 2.527 0 0 1 2.521 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.521-2.522v-2.521h2.521zm0-1.269a2.527 2.527 0 0 1-2.521-2.521 2.528 2.528 0 0 1 2.521-2.521h6.313A2.528 2.528 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.521h-6.313z" />
    </svg>
  );
}

function TelegramGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
    </svg>
  );
}

function ShopifyGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M15.337.009c-.07-.005-.14.012-.198.048a.27.27 0 0 0-.11.15c-.37 1.14-1.142 1.74-1.86 2.003C12.26.6 11.244 0 9.863 0 6.41 0 4.75 4.39 4.176 6.607c-1.263.392-2.17.672-2.248.698C1.305 7.59 1.28 7.618 1.25 8.22L0 20.583 17.335 24 24 22.405 21.088.545c-.02-.147-.14-.26-.29-.267-.147-.006-2.625-.198-5.46-.269zm-1.71.906c.562-.208 1.12-.584 1.498-1.244 1.248.18 2.49.543 2.49.543l.547 4.267c-1.19.37-2.508.78-3.84 1.196L12.87 1.74c.244-.253.497-.576.757-.825zm-3.764.085c1.047 0 1.82.523 2.355 1.544l.944 4.63c-1.04.323-2.09.648-3.092.959L9.5 3.856C9.77 2.045 10.46 1 11.863 1zm7.773 21.11L3.36 19.22l-1.104-10.5 1.55-.482c.07 2.518.854 4.073 2.307 4.073.793 0 1.49-.585 1.94-1.42.397.667.957 1.065 1.658 1.065 1.07 0 1.872-.965 2.265-2.377.413.76 1.027 1.208 1.782 1.208.963 0 1.787-.788 2.244-2.02.4.738.993 1.184 1.738 1.184 1.475 0 2.29-1.736 2.406-4.593l1.24-.385 1.456 14.938z" />
    </svg>
  );
}

function StripeGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M13.976 9.15c-2.172-.806-3.356-1.426-3.356-2.409 0-.831.683-1.305 1.901-1.305 2.227 0 4.515.858 6.09 1.631l.89-5.494C18.252.975 15.697 0 12.165 0 9.667 0 7.589.654 6.104 1.872 4.56 3.147 3.757 4.992 3.757 7.218c0 4.039 2.467 5.76 6.476 7.219 2.585.92 3.445 1.574 3.445 2.583 0 .98-.84 1.545-2.354 1.545-1.875 0-4.965-.921-6.99-2.109l-.9 5.555C5.175 22.99 8.385 24 11.714 24c2.641 0 4.843-.624 6.328-1.813 1.664-1.305 2.525-3.236 2.525-5.732 0-4.128-2.524-5.851-6.594-7.305h.003z" />
    </svg>
  );
}

function PaystackGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M4.8 9.6h14.4a1.2 1.2 0 0 0 0-2.4H4.8a1.2 1.2 0 0 0 0 2.4zm0 3.6h14.4a1.2 1.2 0 0 0 0-2.4H4.8a1.2 1.2 0 0 0 0 2.4zm0 3.6h8.4a1.2 1.2 0 0 0 0-2.4H4.8a1.2 1.2 0 0 0 0 2.4z" />
    </svg>
  );
}

function PayHeroGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm1 14.5V16h-2v.5a.5.5 0 0 1-1 0V16H9a.5.5 0 0 1 0-1h1v-2H9a.5.5 0 0 1 0-1h1V9.5a.5.5 0 0 1 1 0V12h1.5c1.378 0 2.5 1.122 2.5 2.5S13.878 17 12.5 17H13v-.5a.5.5 0 0 1 0 0zm-.5-1H11v-2h1.5a1.5 1.5 0 0 1 0 3z" />
    </svg>
  );
}

function MicrosoftGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M11.4 24H0V12.6h11.4V24zM24 24H12.6V12.6H24V24zM11.4 11.4H0V0h11.4v11.4zM24 11.4H12.6V0H24v11.4z" />
    </svg>
  );
}

function KlaviyoGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M20.442 0H3.558A3.558 3.558 0 0 0 0 3.558v16.884A3.558 3.558 0 0 0 3.558 24h16.884A3.558 3.558 0 0 0 24 20.442V3.558A3.558 3.558 0 0 0 20.442 0zM12 18.5c-3.59 0-6.5-2.91-6.5-6.5S8.41 5.5 12 5.5s6.5 2.91 6.5 6.5-2.91 6.5-6.5 6.5z"/>
    </svg>
  );
}

function MailchimpGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M21.478 15.43c.203-.192.31-.484.266-.794-.06-.41-.41-.772-.895-.875a1.233 1.233 0 0 0-.246-.025c-.23 0-.453.064-.633.178a7.86 7.86 0 0 1-.244-1.988c0-4.363-3.566-7.926-7.932-7.926-4.367 0-7.933 3.563-7.933 7.926 0 4.364 3.566 7.927 7.933 7.927 1.98 0 3.792-.73 5.172-1.93.056.012.112.018.169.018.276 0 .54-.11.737-.307l2.606-2.21zM11.794 5.5c3.716 0 6.733 3.015 6.733 6.726 0 .678-.1 1.331-.284 1.948a1.247 1.247 0 0 0-.624-.165c-.154 0-.303.027-.44.077a6.543 6.543 0 0 1-5.385 2.835 6.543 6.543 0 0 1-6.545-6.541A6.543 6.543 0 0 1 11.794 5.5z"/>
    </svg>
  );
}

function BrevoGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.248-6.5 9.004a.75.75 0 0 1-1.228-.036L6.41 12.74a.75.75 0 0 1 1.228-.864l2.896 4.118 5.896-8.164a.75.75 0 1 1 1.132.418z"/>
    </svg>
  );
}

function BrandMarkGlyph({ bg, fg, label, className }: { bg: string; fg: string; label: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <rect width="24" height="24" rx="5" fill={bg} />
      <text x="12" y="16" textAnchor="middle" fontSize={label.length > 2 ? 7 : 10} fontWeight="700" fill={fg} fontFamily="system-ui,sans-serif">
        {label}
      </text>
    </svg>
  );
}

function ApolloGlyph({ className }: { className?: string }) {
  return <BrandMarkGlyph bg="#111827" fg="#FCD34D" label="A" className={className} />;
}

function InstantlyGlyph({ className }: { className?: string }) {
  return <BrandMarkGlyph bg="#0066FF" fg="#fff" label="IN" className={className} />;
}

function SalesforceGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="#00A1E0" aria-hidden>
      <path d="M12 3c-2.2 0-4.1 1.2-5.1 3-2.2.3-3.9 2.2-3.9 4.5 0 1.1.4 2.1 1 2.9 1.1 1.5 3 2.4 5 2.4 1.2 0 2.3-.3 3.3-.9.8 1.2 2.2 2 3.7 2 2.5 0 4.5-2 4.5-4.5 0-.6-.1-1.1-.3-1.6 1.4-.9 2.3-2.5 2.3-4.3C21.5 5.5 19 3 12 3z" />
    </svg>
  );
}

function HubSpotGlyph({ className }: { className?: string }) {
  return <BrandMarkGlyph bg="#FF7A59" fg="#fff" label="HS" className={className} />;
}

function PipedriveGlyph({ className }: { className?: string }) {
  return <BrandMarkGlyph bg="#017737" fg="#fff" label="PD" className={className} />;
}

function CalendlyGlyph({ className }: { className?: string }) {
  return <BrandMarkGlyph bg="#006BFF" fg="#fff" label="C" className={className} />;
}

function ZoomGlyph({ className }: { className?: string }) {
  return <BrandMarkGlyph bg="#2D8CFF" fg="#fff" label="Z" className={className} />;
}

function QuickBooksGlyph({ className }: { className?: string }) {
  return <BrandMarkGlyph bg="#2CA01C" fg="#fff" label="QB" className={className} />;
}

// ── Tile primitives ───────────────────────────────────────────────────────────

type BadgeDef = { label: string; className: string };

type SmallTileProps = {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  borderClass: string;
  badge?: BadgeDef;
  children: ReactNode;
};

function IntegrationSection({
  id,
  title,
  description,
  badge,
  children,
}: {
  id?: string;
  title: string;
  description?: string;
  badge?: BadgeDef;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm sm:p-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700">{title}</h2>
          {description ? (
            <p className="mt-1 max-w-2xl text-[11px] leading-relaxed text-slate-500">{description}</p>
          ) : null}
        </div>
        {badge ? (
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${badge.className}`}>
            {badge.label}
          </span>
        ) : null}
      </div>
      {children}
    </section>
  );
}

const INTEGRATION_NAV = [
  { id: "integrations-messaging", label: "Messaging" },
  { id: "integrations-social", label: "Social" },
  { id: "integrations-crm", label: "CRM & Sales" },
  { id: "integrations-comms", label: "Email & Meetings" },
  { id: "integrations-payments", label: "Payments" },
  { id: "integrations-marketing", label: "Marketing" },
  { id: "integrations-analytics", label: "Analytics" },
  { id: "integrations-commerce", label: "Commerce" },
  { id: "integrations-workspace", label: "Workspace" },
  { id: "integrations-automation", label: "Automation" },
  { id: "integrations-suppliers", label: "Suppliers" },
] as const;

function SmallTile({ icon, title, subtitle, borderClass, badge, children }: SmallTileProps) {
  return (
    <div className={`flex h-full min-h-[130px] flex-col rounded-lg border p-3 shadow-sm ${borderClass}`}>
      <div className="flex items-start gap-2">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white/90 shadow-sm">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <h3 className="text-[13px] font-semibold leading-tight text-slate-900">{title}</h3>
            {badge && (
              <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${badge.className}`}>
                {badge.label}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="mt-0.5 text-[10px] leading-snug text-slate-500">{subtitle}</p>
          )}
        </div>
      </div>
      <div className="mt-auto pt-2.5">{children}</div>
    </div>
  );
}

// ── Composio tile controls ────────────────────────────────────────────────────

type ComposioTileControlsProps = {
  connected: boolean;
  busy: boolean;
  statusLoading?: boolean;
  connectLabel: string;
  connectClass: string;
  onConnect: () => void;
  onDisconnect: () => void;
};

function ComposioTileControls({
  connected,
  busy,
  statusLoading = false,
  connectLabel,
  connectClass,
  onConnect,
  onDisconnect,
}: ComposioTileControlsProps) {
  if (statusLoading) {
    return (
      <div className="flex items-center justify-center gap-1.5 py-0.5 text-[11px] text-slate-400">
        <Loader2 size={12} className="animate-spin" />
        Checking…
      </div>
    );
  }
  if (connected) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
          <CheckCircle size={12} /> Connected
        </div>
        <button
          type="button"
          onClick={onDisconnect}
          disabled={busy}
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
        >
          {busy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
        </button>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={onConnect}
      disabled={busy}
      className={`flex w-full items-center justify-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50 ${connectClass}`}
    >
      {busy ? <Loader2 size={11} className="animate-spin" /> : <><span>{connectLabel}</span><ExternalLink size={9} /></>}
    </button>
  );
}

// ── Telegram (free bot) ───────────────────────────────────────────────────────

function TelegramStatus({ connection, onChanged }: { connection?: TelegramConnection; onChanged: () => void }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleConnect() {
    const t = token.trim();
    if (!t) return;
    setBusy(true); setErr(null);
    try { await telegramApi.connect(t); setToken(""); onChanged(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Could not connect"); }
    finally { setBusy(false); }
  }

  async function handleDisconnect() {
    if (!confirm("Disconnect this Telegram bot?")) return;
    setBusy(true); setErr(null);
    try { await telegramApi.disconnect(); onChanged(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Could not disconnect"); }
    finally { setBusy(false); }
  }

  if (connection?.connected && connection.bot_username) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
          <CheckCircle size={12} /> @{connection.bot_username}
        </div>
        <button type="button" onClick={handleDisconnect} disabled={busy}
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">
          {busy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
        </button>
        {err && <p className="flex items-center gap-1 text-[10px] text-red-600"><AlertCircle size={10} /> {err}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] leading-snug text-slate-500">
        Token from{" "}
        <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="font-medium text-[#229ED9] hover:underline">
          @BotFather
        </a>
      </p>
      <input type="password" value={token} onChange={(e) => setToken(e.target.value)}
        placeholder="123456:ABC…" autoComplete="off"
        className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] font-mono outline-none focus:border-[#229ED9]" />
      <button type="button" onClick={handleConnect} disabled={busy || !token.trim()}
        className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#229ED9] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#1b8bc0] disabled:opacity-50">
        {busy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect
      </button>
      {err && <p className="flex items-center gap-1 text-[10px] text-red-600"><AlertCircle size={10} /> {err}</p>}
    </div>
  );
}

// ── Paystack (API key) ────────────────────────────────────────────────────────

function PaystackStatus({ connection, onChanged }: { connection?: PaystackConnection; onChanged: () => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleConnect() {
    const k = key.trim();
    if (!k) return;
    setBusy(true); setErr(null);
    try { await paystackApi.connect(k); setKey(""); onChanged(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Could not connect"); }
    finally { setBusy(false); }
  }

  async function handleDisconnect() {
    if (!confirm("Disconnect Paystack?")) return;
    setBusy(true); setErr(null);
    try { await paystackApi.disconnect(); onChanged(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Could not disconnect"); }
    finally { setBusy(false); }
  }

  if (connection?.connected) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
          <CheckCircle size={12} />
          {connection.business_name ? connection.business_name : "Connected"}
        </div>
        <button type="button" onClick={handleDisconnect} disabled={busy}
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">
          {busy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
        </button>
        {err && <p className="flex items-center gap-1 text-[10px] text-red-600"><AlertCircle size={10} /> {err}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] leading-snug text-slate-500">
        Secret Key from your{" "}
        <a href="https://dashboard.paystack.com/#/settings/developer" target="_blank" rel="noreferrer"
          className="font-medium text-[#00C3F7] hover:underline">
          Paystack Dashboard
        </a>
      </p>
      <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
        placeholder="sk_live_…" autoComplete="off"
        className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] font-mono outline-none focus:border-[#00C3F7]" />
      <button type="button" onClick={handleConnect} disabled={busy || !key.trim()}
        className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#00C3F7] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#00a8d6] disabled:opacity-50">
        {busy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect
      </button>
      {err && <p className="flex items-center gap-1 text-[10px] text-red-600"><AlertCircle size={10} /> {err}</p>}
    </div>
  );
}

// ── PayHero (Basic Auth + Channel selector) ───────────────────────────────────

function PayHeroStatus({ connection, onChanged }: { connection?: PayheroConnection; onChanged: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Channel selection state
  const [channels, setChannels] = useState<PayheroChannel[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [selectedChannel, setSelectedChannel] = useState<string>("");
  const [savingChannel, setSavingChannel] = useState(false);

  // Load channels when connected
  useEffect(() => {
    if (!connection?.connected) return;
    setLoadingChannels(true);
    payheroApi.channels()
      .then(res => {
        setChannels(res.channels ?? []);
        if (res.selected_channel_id) setSelectedChannel(String(res.selected_channel_id));
      })
      .catch(() => {})
      .finally(() => setLoadingChannels(false));
  }, [connection?.connected]);

  async function handleConnect() {
    if (!username.trim() || !password.trim()) return;
    setBusy(true); setErr(null);
    try { await payheroApi.connect(username.trim(), password.trim()); setUsername(""); setPassword(""); onChanged(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Could not connect"); }
    finally { setBusy(false); }
  }

  async function handleDisconnect() {
    if (!confirm("Disconnect PayHero?")) return;
    setBusy(true); setErr(null);
    try { await payheroApi.disconnect(); onChanged(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Could not disconnect"); }
    finally { setBusy(false); }
  }

  async function handleSaveChannel() {
    if (!selectedChannel) return;
    setSavingChannel(true); setErr(null);
    try {
      await payheroApi.setChannel(selectedChannel);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save channel");
    } finally {
      setSavingChannel(false);
    }
  }

  if (connection?.connected) {
    const savedChannelId = connection.channel_id ? String(connection.channel_id) : null;
    const isChannelSaved = savedChannelId && selectedChannel === savedChannelId;

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
          <CheckCircle size={12} />
          {connection.username || "Connected"}
        </div>

        {/* Channel selector */}
        <div className="space-y-1">
          <p className="text-[10px] text-slate-500">Select your M-Pesa channel (paybill / till):</p>
          {loadingChannels ? (
            <p className="flex items-center gap-1 text-[10px] text-slate-400"><Loader2 size={10} className="animate-spin" /> Loading channels…</p>
          ) : channels.length === 0 ? (
            <p className="text-[10px] text-slate-400">No channels found in your PayHero account.</p>
          ) : (
            <div className="flex gap-1.5">
              <select
                value={selectedChannel}
                onChange={e => setSelectedChannel(e.target.value)}
                className="flex-1 rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#1DB954]"
              >
                <option value="">— Pick a channel —</option>
                {channels.map(ch => (
                  <option key={ch.id} value={String(ch.id)}>
                    {ch.name}{ch.paybill ? ` (${ch.paybill})` : ch.short_code ? ` (${ch.short_code})` : ""}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleSaveChannel}
                disabled={savingChannel || !selectedChannel || isChannelSaved === true}
                className="flex items-center gap-1 rounded-lg bg-[#1DB954] px-2 py-1 text-[10px] font-semibold text-white hover:bg-[#17a34a] disabled:opacity-50"
              >
                {savingChannel ? <Loader2 size={10} className="animate-spin" /> : <CheckCircle2 size={10} />}
                {isChannelSaved ? "Saved" : "Save"}
              </button>
            </div>
          )}
          {savedChannelId && (
            <p className="text-[10px] text-green-700">
              ✓ Payments to this channel auto-confirm orders &amp; send receipts
            </p>
          )}
        </div>

        <button type="button" onClick={handleDisconnect} disabled={busy}
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">
          {busy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
        </button>
        {err && <p className="flex items-center gap-1 text-[10px] text-red-600"><AlertCircle size={10} /> {err}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] leading-snug text-slate-500">
        API credentials from your{" "}
        <a href="https://app.payhero.co.ke/" target="_blank" rel="noreferrer"
          className="font-medium text-[#1DB954] hover:underline">
          PayHero Dashboard
        </a>
        {" "}→ API Keys
      </p>
      <input type="text" value={username} onChange={(e) => setUsername(e.target.value)}
        placeholder="API Username" autoComplete="off"
        className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#1DB954]" />
      <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
        placeholder="API Password" autoComplete="off"
        className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#1DB954]" />
      <button type="button" onClick={handleConnect} disabled={busy || !username.trim() || !password.trim()}
        className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#1DB954] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#17a34a] disabled:opacity-50">
        {busy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect
      </button>
      {err && <p className="flex items-center gap-1 text-[10px] text-red-600"><AlertCircle size={10} /> {err}</p>}
    </div>
  );
}

// ── Browser Operator (extension session — read-only status) ────────────────────

function BrowserOperatorStatusTile() {
  const [status, setStatus] = useState<BrowserOperatorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      setStatus(await browserApi.status());
    } catch {
      setStatus({ connected: false });
    } finally {
      setLoading(false);
      if (manual) setRefreshing(false);
    }
  }, []);

  // Poll while the section is open so the badge flips live once the user connects.
  useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 8000);
    return () => window.clearInterval(t);
  }, [load]);

  const connected = !!status?.connected;
  const lastActive = status?.last_command_at
    ? new Date(status.last_command_at).toLocaleString()
    : null;

  return (
    <SmallTile
      title="Browser Operator"
      subtitle="AI controls your browser to post & extract data"
      borderClass="border-[#2563eb]/20 bg-[#2563eb]/5"
      badge={
        connected
          ? { label: "Live", className: "bg-green-100 text-green-700" }
          : { label: "Companion", className: "bg-slate-100 text-slate-500" }
      }
      icon={<Globe className="h-5 w-5 text-[#2563eb]" />}
    >
      {loading ? (
        <div className="flex items-center justify-center gap-1.5 py-0.5 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" /> Checking…
        </div>
      ) : connected ? (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
            <CheckCircle size={12} /> Connected
          </div>
          {lastActive && (
            <p className="text-[10px] leading-snug text-slate-500">Last active {lastActive}</p>
          )}
          <button
            type="button"
            onClick={() => void load(true)}
            disabled={refreshing}
            className="flex w-full items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {refreshing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />} Refresh
          </button>
        </div>
      ) : (
        <div className="space-y-1.5">
          <p className="text-[10px] leading-snug text-slate-500">
            Install the Zilo Browser Operator extension and keep this dashboard open —
            it connects automatically. No IDs to enter.
          </p>
          <button
            type="button"
            onClick={() => void load(true)}
            disabled={refreshing}
            className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#2563eb] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#1d4ed8] disabled:opacity-50"
          >
            {refreshing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />} Check status
          </button>
        </div>
      )}
    </SmallTile>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IntegrationsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-slate-400">Loading…</div>}>
      <IntegrationsPageInner />
    </Suspense>
  );
}

const COMPOSIO_SOCIAL_IDS = new Set<string>(COMPOSIO_SOCIAL_TOOLKITS);

function composioSocialToolkit(platformId: string): string {
  return platformId;
}

const COMPOSIO_DISCONNECTED_STATUS = buildComposioDisconnectedStatus();

/** OR-merge social settings into Composio status (social tiles use both sources). */
function mergeComposioSocialIntoStatus(
  status: Record<string, boolean>,
  settings: ComposioSocialSettings | null,
): Record<string, boolean> {
  if (!settings) return status;
  const next = { ...status };
  const pairs: Array<[string, boolean]> = [
    ["facebook", !!settings.facebook?.connected],
    ["instagram", !!settings.instagram?.connected],
    ["youtube", !!settings.youtube?.connected],
    ["linkedin", !!settings.linkedin?.connected],
    ["twitter", !!settings.twitter?.connected],
    ["tiktok", !!settings.tiktok?.connected],
  ];
  for (const [key, connected] of pairs) {
    if (connected) next[key] = true;
  }
  return next;
}

const COMPOSIO_STATUS_TIMEOUT_MS = 12_000;

function friendlyApiError(message: string): string {
  const cleaned = message.replace(/^\d{3}:\s*/, "").trim();
  return cleaned || message;
}

async function fetchComposioConnections(token: string) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), COMPOSIO_STATUS_TIMEOUT_MS);
  try {
    return await fetch("/api/composio/connections", {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timer);
  }
}

interface ZernioAccount { id: string; platform: string; name?: string; username?: string; }

function IntegrationsPageInner() {
  const [tgConn, setTgConn] = useState<TelegramConnection>({ connected: false });
  const [psConn, setPsConn] = useState<PaystackConnection>({ connected: false });
  const [phConn, setPhConn] = useState<PayheroConnection>({ connected: false });
  const [waConn, setWaConn] = useState<WhatsAppStatus | null>(null);
  const { accounts: rawZernioAccounts, apiConnected: zernioApiOk, refresh: refreshZernioCtx, connect: zernioCtxConnect, disconnect: zernioCtxDisconnect } = useZernioAccounts();
  const zernioAccounts = rawZernioAccounts as ZernioAccount[];
  const [zernioConnecting, setZernioConnecting] = useState<string | null>(null);
  const [zernioDisconnecting, setZernioDisconnecting] = useState<string | null>(null);
  const [composioFbPages, setComposioFbPages] = useState<ComposioFacebookPage[]>([]);
  const [showComposioFbPagePicker, setShowComposioFbPagePicker] = useState(false);
  const [fbLoadingPages, setFbLoadingPages] = useState(false);
  const [fbCompletingPageId, setFbCompletingPageId] = useState<string | null>(null);
  const [composioLiAuthors, setComposioLiAuthors] = useState<ComposioLinkedInAuthor[]>([]);
  const [showComposioLiAuthorPicker, setShowComposioLiAuthorPicker] = useState(false);
  const [liLoadingAuthors, setLiLoadingAuthors] = useState(false);
  const [liAuthorLoadError, setLiAuthorLoadError] = useState<string | null>(null);
  const [liCompletingAuthorUrn, setLiCompletingAuthorUrn] = useState<string | null>(null);
  const [composioSocial, setComposioSocial] = useState<ComposioSocialSettings | null>(null);

  const refreshZernio = useCallback(async () => {
    await refreshZernioCtx();
  }, [refreshZernioCtx]);

  async function zernioConnect(platformId: string) {
    if (COMPOSIO_SOCIAL_IDS.has(platformId)) return;
    setZernioConnecting(platformId);
    try {
      const redirectUrl = `${window.location.origin}/dashboard/integrations?connected=${encodeURIComponent(platformId)}`;
      const { authUrl } = await zernioCtxConnect(platformId, redirectUrl, false);
      if (authUrl) {
        const popup = window.open(authUrl, "zernio-connect", "width=980,height=760,noopener,noreferrer");
        if (!popup) {
          // Popup blocked: continue in same tab so OAuth can still complete.
          window.location.href = authUrl;
          return;
        }
        setBanner({
          type: "success",
          msg: `Finish ${platformId} connection in the popup, then return here.`,
        });
        const poll = window.setInterval(() => {
          void refreshZernio();
          if (popup.closed) {
            window.clearInterval(poll);
            setTimeout(() => void refreshZernio(), 1200);
          }
        }, 3000);
      } else {
        setBanner({ type: "error", msg: "Could not get connection URL. Please try again." });
      }
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to connect. Please try again." });
    } finally {
      setZernioConnecting(null);
    }
  }

  async function zernioDisconnect(accountId: string, label: string) {
    if (!confirm(`Disconnect ${label}?`)) return;
    setZernioDisconnecting(accountId);
    try {
      await zernioCtxDisconnect(accountId);
      await refreshZernio();
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : `Failed to disconnect ${label}.` });
    } finally {
      setZernioDisconnecting(null);
    }
  }

  const refreshComposioSocial = useCallback(async () => {
    try {
      const settings = await composioSocialApi.settings();
      setComposioSocial(settings);
      setComposioStatus((prev) => mergeComposioSocialIntoStatus(prev, settings));
    } catch {
      setComposioSocial(null);
    }
  }, []);

  const loadComposioFacebookPages = useCallback(async (autoSelectSingle = true) => {
    setFbLoadingPages(true);
    try {
      const res = await composioSocialApi.facebookPages();
      const pages = res.pages || [];
      setComposioFbPages(pages);
      if (pages.length === 0) {
        setShowComposioFbPagePicker(false);
        setBanner({ type: "error", msg: "No Facebook Pages found for this account." });
        return pages;
      }
      if (pages.length === 1 && autoSelectSingle) {
        await composioSocialApi.selectFacebookPage(pages[0].id);
        await refreshComposioSocial();
        setShowComposioFbPagePicker(false);
        setBanner({ type: "success", msg: `${pages[0].name || "Facebook Page"} selected for publishing.` });
        return pages;
      }
      setShowComposioFbPagePicker(true);
      setBanner({ type: "success", msg: "Select a Facebook Page below to finish connecting." });
      return pages;
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Could not load Facebook pages." });
      return [];
    } finally {
      setFbLoadingPages(false);
    }
  }, [refreshComposioSocial]);

  async function completeComposioFacebookPageSelect(page: ComposioFacebookPage) {
    setFbCompletingPageId(page.id);
    try {
      await composioSocialApi.selectFacebookPage(page.id, page.name, page.instagram_user_id);
      setBanner({ type: "success", msg: `${page.name || "Facebook Page"} selected for publishing.` });
      setShowComposioFbPagePicker(false);
      setComposioFbPages([]);
      await refreshComposioSocial();
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to save Facebook Page." });
    } finally {
      setFbCompletingPageId(null);
    }
  }

  const loadLinkedInContracts = useCallback(async (autoSelectSingle = true) => {
    setLiLoadingContracts(true);
    try {
      const res = await unipileApi.linkedinContracts();
      const contracts = res.contracts || [];
      setLiContracts(contracts);
      if (contracts.length === 0) {
        setShowLiContractPicker(false);
        return contracts;
      }
      const alreadySelected = contracts.some((c) => c.selected) || !!res.selected_contract_id;
      if (alreadySelected) {
        setShowLiContractPicker(false);
        return contracts;
      }
      const salesNav = contracts.filter((c) => c.product === "sales_navigator");
      if (autoSelectSingle && salesNav.length === 1) {
        await unipileApi.selectLinkedInContract(salesNav[0].id, {
          name: salesNav[0].name,
          product: salesNav[0].product,
        });
        await refreshComposioSocial();
        setShowLiContractPicker(false);
        setBanner({ type: "success", msg: `${salesNav[0].name} selected for Sales Navigator.` });
        return contracts;
      }
      if (autoSelectSingle && contracts.length === 1) {
        await unipileApi.selectLinkedInContract(contracts[0].id, {
          name: contracts[0].name,
          product: contracts[0].product,
        });
        await refreshComposioSocial();
        setShowLiContractPicker(false);
        setBanner({ type: "success", msg: `${contracts[0].name} selected.` });
        return contracts;
      }
      setShowLiContractPicker(true);
      setBanner({ type: "success", msg: "Select your Sales Navigator or Recruiter contract below." });
      return contracts;
    } catch (e) {
      setBanner({
        type: "error",
        msg: e instanceof Error ? e.message : "Could not load LinkedIn contracts.",
      });
      return [];
    } finally {
      setLiLoadingContracts(false);
    }
  }, [refreshComposioSocial]);

  async function completeLinkedInContractSelect(contract: UnipileLinkedInContract) {
    setLiSelectingContractId(contract.id);
    try {
      await unipileApi.selectLinkedInContract(contract.id, {
        name: contract.name,
        product: contract.product,
      });
      setShowLiContractPicker(false);
      setLiContracts([]);
      await refreshComposioSocial();
      setBanner({ type: "success", msg: `${contract.name} selected for LinkedIn.` });
    } catch (e) {
      setBanner({
        type: "error",
        msg: e instanceof Error ? e.message : "Failed to save LinkedIn contract.",
      });
    } finally {
      setLiSelectingContractId(null);
    }
  }

  async function finishLinkedInMessagingConnect() {
    setLiMsgEmail("");
    setLiMsgPassword("");
    setLiMsgCookie("");
    setLiMsgMethod("password");
    setLiCheckpoint(null);
    setLiCheckpointCode("");
    setLiPremiumShowMore(false);
    await refreshComposioSocial();
    await loadLinkedInContracts(true);
    setBanner((prev) => prev ?? { type: "success", msg: "LinkedIn Premium connected." });
  }

  async function unipileConnectLinkedInHosted() {
    setUnipileBusy(true);
    try {
      const redirectBase = typeof window !== "undefined" ? window.location.origin : "";
      const { authUrl } = await unipileApi.connectLinkedIn(redirectBase);
      if (!authUrl) throw new Error("No Unipile auth URL returned.");
      const popup = window.open(authUrl, "unipile-connect", "width=980,height=760,noopener,noreferrer");
      if (!popup) {
        window.location.href = authUrl;
        return;
      }
      setBanner({
        type: "success",
        msg: "Sign in on LinkedIn — use Google, Apple, or your usual method. Close the popup when done.",
      });
      await new Promise<void>((resolve) => {
        const tick = window.setInterval(() => {
          if (popup.closed) {
            window.clearInterval(tick);
            resolve();
          }
        }, 500);
      });
      for (let i = 0; i < 12; i += 1) {
        await refreshComposioSocial();
        const status = await unipileApi.status().catch(() => null);
        if (status?.connected) {
          await finishLinkedInMessagingConnect();
          return;
        }
        await new Promise((r) => window.setTimeout(r, 1500));
      }
      setBanner({
        type: "error",
        msg: "Messaging not connected yet. Finish login in the popup, or try again.",
      });
    } catch (e) {
      setBanner({
        type: "error",
        msg: e instanceof Error ? e.message : "Failed to start LinkedIn messaging connection.",
      });
    } finally {
      setUnipileBusy(false);
    }
  }

  async function submitLinkedInCookie() {
    if (!liMsgCookie.trim()) {
      setBanner({ type: "error", msg: "Paste your LinkedIn li_at cookie." });
      return;
    }
    setUnipileBusy(true);
    try {
      const ua = typeof navigator !== "undefined" ? navigator.userAgent : undefined;
      const res = await unipileApi.connectLinkedInCookie(liMsgCookie.trim(), ua);
      if (res.checkpoint && res.account_id) {
        setLiMsgCookie("");
        setLiCheckpoint({
          checkpoint: true,
          account_id: res.account_id,
          checkpoint_type: res.checkpoint_type || "VERIFICATION",
          message: res.message || "Complete LinkedIn verification to finish connecting.",
        });
        setBanner({ type: "success", msg: res.message || "Complete verification to finish connecting." });
        return;
      }
      if (res.connected || res.success) {
        await finishLinkedInMessagingConnect();
      }
    } catch (e) {
      setBanner({
        type: "error",
        msg: e instanceof Error ? e.message : "Failed to connect with LinkedIn cookie.",
      });
    } finally {
      setUnipileBusy(false);
    }
  }

  async function submitLinkedInMessagingCredentials() {
    if (!liMsgEmail.trim() || !liMsgPassword) {
      setBanner({ type: "error", msg: "Enter your LinkedIn email and password." });
      return;
    }
    setUnipileBusy(true);
    try {
      const res = await unipileApi.connectLinkedInCredentials(liMsgEmail.trim(), liMsgPassword);
      if (res.checkpoint && res.account_id) {
        setLiMsgPassword("");
        setLiCheckpoint({
          checkpoint: true,
          account_id: res.account_id,
          checkpoint_type: res.checkpoint_type || "VERIFICATION",
          message: res.message || "Complete LinkedIn verification to finish connecting.",
        });
        setBanner({ type: "success", msg: res.message || "Complete verification to finish connecting." });
        return;
      }
      if (res.connected || res.success) {
        await finishLinkedInMessagingConnect();
      }
    } catch (e) {
      setBanner({
        type: "error",
        msg: e instanceof Error ? e.message : "Failed to connect LinkedIn messaging.",
      });
    } finally {
      setUnipileBusy(false);
    }
  }

  async function submitLinkedInCheckpoint(code?: string) {
    if (!liCheckpoint?.account_id) return;
    const token = (code ?? liCheckpointCode).trim();
    if (!token && liCheckpoint.checkpoint_type !== "IN_APP_VALIDATION") {
      setBanner({ type: "error", msg: "Enter the verification code." });
      return;
    }
    setUnipileBusy(true);
    try {
      const res = await unipileApi.solveLinkedInCheckpoint(liCheckpoint.account_id, token);
      if (res.checkpoint && res.account_id) {
        setLiCheckpointCode("");
        setLiCheckpoint({
          checkpoint: true,
          account_id: res.account_id,
          checkpoint_type: res.checkpoint_type || "VERIFICATION",
          message: res.message || "Complete LinkedIn verification.",
        });
        setBanner({ type: "success", msg: res.message || "Another verification step is required." });
        return;
      }
      if (res.connected || res.success) {
        await finishLinkedInMessagingConnect();
      }
    } catch (e) {
      setBanner({
        type: "error",
        msg: e instanceof Error ? e.message : "Verification failed.",
      });
    } finally {
      setUnipileBusy(false);
    }
  }

  async function pollLinkedInInAppApproval() {
    if (!liCheckpoint?.account_id) return;
    setUnipileBusy(true);
    try {
      const res = await unipileApi.pollLinkedInAccount(liCheckpoint.account_id);
      if (res.pending) {
        setBanner({
          type: "error",
          msg: "Still waiting — approve the login in your LinkedIn mobile app, then try again.",
        });
        return;
      }
      if (res.connected || res.success) {
        await finishLinkedInMessagingConnect();
      }
    } catch (e) {
      setBanner({
        type: "error",
        msg: e instanceof Error ? e.message : "Could not verify LinkedIn approval.",
      });
    } finally {
      setUnipileBusy(false);
    }
  }

  async function unipileDisconnectLinkedIn() {
    setUnipileBusy(true);
    try {
      await unipileApi.disconnectLinkedIn();
      setLiMsgEmail("");
      setLiMsgPassword("");
      setLiMsgCookie("");
      setLiMsgMethod("password");
      setLiCheckpoint(null);
      setLiCheckpointCode("");
      setLiPremiumShowMore(false);
      await refreshComposioSocial();
      setBanner({ type: "success", msg: "LinkedIn Premium disconnected." });
    } catch (e) {
      setBanner({
        type: "error",
        msg: e instanceof Error ? e.message : "Failed to disconnect LinkedIn messaging.",
      });
    } finally {
      setUnipileBusy(false);
    }
  }

  const loadComposioLinkedInAuthors = useCallback(async (autoSelectSingle = true) => {
    setLiLoadingAuthors(true);
    setLiAuthorLoadError(null);
    try {
      const res = await composioSocialApi.linkedinAuthors();
      const authors = res.authors || [];
      setComposioLiAuthors(authors);
      if (!authors.length) {
        const errMsg = friendlyApiError(res.error || "No LinkedIn posting identities found.");
        setLiAuthorLoadError(errMsg);
        setShowComposioLiAuthorPicker(true);
        setBanner({ type: "error", msg: errMsg });
        return authors;
      }
      if (authors.length === 1 && autoSelectSingle) {
        await composioSocialApi.selectLinkedInAuthor(
          authors[0].urn, authors[0].name, authors[0].provider, authors[0].org_id,
        );
        await refreshComposioSocial();
        setShowComposioLiAuthorPicker(false);
        setBanner({ type: "success", msg: `${authors[0].name} selected for LinkedIn posting.` });
        return authors;
      }
      setShowComposioLiAuthorPicker(true);
      return authors;
    } catch (e) {
      const raw =
        e instanceof Error && e.name === "AbortError"
          ? "LinkedIn is taking too long to respond. Please try again in a moment."
          : e instanceof Error
            ? e.message
            : "Could not load LinkedIn identities.";
      const errMsg = friendlyApiError(raw);
      setLiAuthorLoadError(errMsg);
      setShowComposioLiAuthorPicker(true);
      setBanner({ type: "error", msg: errMsg });
      return [];
    } finally {
      setLiLoadingAuthors(false);
    }
  }, [refreshComposioSocial]);

  const openLinkedInAuthorPicker = useCallback(() => {
    setShowComposioLiAuthorPicker(true);
    setLiAuthorLoadError(null);
    void loadComposioLinkedInAuthors(false);
  }, [loadComposioLinkedInAuthors]);

  async function completeComposioLinkedInAuthorSelect(author: ComposioLinkedInAuthor) {
    setLiCompletingAuthorUrn(author.urn);
    try {
      await composioSocialApi.selectLinkedInAuthor(author.urn, author.name, author.provider, author.org_id);
      setBanner({ type: "success", msg: `${author.name} selected for LinkedIn posting.` });
      setShowComposioLiAuthorPicker(false);
      setComposioLiAuthors([]);
      await refreshComposioSocial();
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to save LinkedIn identity." });
    } finally {
      setLiCompletingAuthorUrn(null);
    }
  }

  async function composioConnectSocial(platformId: string) {
    const toolkit = composioSocialToolkit(platformId);
    const platform = INTEGRATIONS_SOCIAL_PLATFORMS.find((p) => p.id === platformId);
    const platformLabel = platform?.label ?? toolkit;
    if (composioStatusLoading) {
      setBanner({ type: "error", msg: "Still checking your connections — wait a moment, then try again." });
      return;
    }
    const alreadyConnected =
      !!composioStatus[toolkit]
      || (platformId === "linkedin" && !!composioSocial?.linkedin?.connected);
    if (alreadyConnected) {
      setBanner({ type: "success", msg: `${platformLabel} is already connected.` });
      return;
    }
    const connected = await composioConnect(toolkit);
    if (!connected) return;
    await refreshComposioSocial();
    if (platformId === "facebook") {
      const settings = await composioSocialApi.settings().catch(() => null);
      if (settings?.facebook.connected && !settings.facebook.page_id) {
        await loadComposioFacebookPages(true);
      }
    }
    if (platformId === "linkedin") {
      const settings = await composioSocialApi.settings().catch(() => null);
      if (settings?.linkedin?.connected && !settings.linkedin.author_urn) {
        setShowComposioLiAuthorPicker(true);
        await loadComposioLinkedInAuthors(true);
      }
    }
  }

  async function openFacebookPagePicker() {
    setShowComposioFbPagePicker(true);
    await loadComposioFacebookPages(false);
  }

  const [composioStatus, setComposioStatus] = useState<Record<string, boolean>>(
    () => ({ ...COMPOSIO_DISCONNECTED_STATUS }),
  );
  const [composioStatusLoading, setComposioStatusLoading] = useState(true);

  // Apply cached status AFTER mount (not during render). Reading localStorage in the
  // useState initializer made the first client render differ from SSR (which has no
  // localStorage), causing a hydration mismatch on the connected count + badges.
  useEffect(() => {
    const stored = readStoredComposioStatus();
    if (stored && Object.values(stored).some(Boolean)) {
      setComposioStatus((prev) => ({ ...prev, ...stored }));
      setComposioStatusLoading(false);
    }
  }, []);
  const [composioStatusRefreshing, setComposioStatusRefreshing] = useState(false);
  const [composioBusy, setComposioBusy] = useState<string | null>(null);
  const [unipileBusy, setUnipileBusy] = useState(false);
  const [liMsgEmail, setLiMsgEmail] = useState("");
  const [liMsgPassword, setLiMsgPassword] = useState("");
  const [liMsgCookie, setLiMsgCookie] = useState("");
  const [liMsgMethod, setLiMsgMethod] = useState<"cookie" | "password" | "hosted">("password");
  const [liPremiumShowMore, setLiPremiumShowMore] = useState(false);
  const [liCheckpoint, setLiCheckpoint] = useState<UnipileCheckpointResponse | null>(null);
  const [liCheckpointCode, setLiCheckpointCode] = useState("");
  const [liContracts, setLiContracts] = useState<UnipileLinkedInContract[]>([]);
  const [showLiContractPicker, setShowLiContractPicker] = useState(false);
  const [liLoadingContracts, setLiLoadingContracts] = useState(false);
  const [liSelectingContractId, setLiSelectingContractId] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ type: "success" | "error"; msg: string } | null>(null);
  const [googleAdsCustomerId, setGoogleAdsCustomerId] = useState("");
  const [shopifyShop, setShopifyShop]     = useState("");
  const [shopifyDomain, setShopifyDomain] = useState("");
  const [shopifyToken, setShopifyToken]   = useState("");
  const [shopifyFormOpen, setShopifyFormOpen] = useState<"none" | "oauth" | "manual">("none");
  const [shopifyBusy, setShopifyBusy] = useState(false);

  // ── Supplier connections ──────────────────────────────────────────────────
  const [supplierStatus, setSupplierStatus] = useState<SupplierConnections>({ cj: false, aliexpress: false });
  const [cjEmail, setCjEmail] = useState("");
  const [cjApiKey, setCjApiKey] = useState("");
  const [cjBusy, setCjBusy] = useState(false);
  const [aeBusy, setAeBusy] = useState(false);
  const [aeAppKey, setAeAppKey] = useState("");
  const [aeAppSecret, setAeAppSecret] = useState("");
  const [aeAccessToken, setAeAccessToken] = useState("");
  const [aeManualOpen, setAeManualOpen] = useState(false);

  const refreshSuppliers = useCallback(() => {
    supplierApi.connections().then(setSupplierStatus).catch(() => {});
  }, []);

  async function connectCJ() {
    if (!cjEmail.trim() || !cjApiKey.trim()) return;
    setCjBusy(true);
    try {
      await supplierApi.connectCJ(cjEmail.trim(), cjApiKey.trim());
      setCjEmail(""); setCjApiKey("");
      refreshSuppliers();
      setBanner({ type: "success", msg: "CJ Dropshipping connected." });
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to connect CJ." });
    } finally { setCjBusy(false); }
  }

  async function disconnectCJ() {
    if (!confirm("Disconnect CJ Dropshipping?")) return;
    setCjBusy(true);
    try { await supplierApi.disconnectCJ(); refreshSuppliers(); }
    catch { /* ignore */ } finally { setCjBusy(false); }
  }

  async function connectAEOAuth() {
    setAeBusy(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/aliexpress/oauth/start`, {
        headers: { Authorization: `Bearer ${token ?? ""}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to start AliExpress OAuth" })) as { detail?: string };
        setBanner({ type: "error", msg: String(err.detail ?? "Failed to start AliExpress OAuth") });
        return;
      }
      const data = await res.json() as { auth_url: string };
      const popup = window.open(data.auth_url, "ae-connect", "width=980,height=760,noopener,noreferrer");
      if (!popup) { window.location.href = data.auth_url; return; }
      setBanner({ type: "success", msg: "Finish connecting in the popup, then return here." });
      const onMsg = (e: MessageEvent) => {
        if (e.origin !== window.location.origin) return;
        if (e.data?.type === "ae_connected") { refreshSuppliers(); setBanner({ type: "success", msg: "AliExpress connected!" }); }
        if (e.data?.type === "ae_connect_failed") setBanner({ type: "error", msg: e.data.msg || "AliExpress connection failed." });
        window.removeEventListener("message", onMsg);
      };
      window.addEventListener("message", onMsg);
      const poll = window.setInterval(() => {
        void refreshSuppliers();
        if (popup.closed) { window.clearInterval(poll); setTimeout(() => void refreshSuppliers(), 1200); }
      }, 3000);
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to connect AliExpress." });
    } finally { setAeBusy(false); }
  }

  async function disconnectAE() {
    if (!confirm("Disconnect AliExpress?")) return;
    setAeBusy(true);
    try { await supplierApi.disconnectAliExpress(); refreshSuppliers(); }
    catch { /* ignore */ } finally { setAeBusy(false); }
  }

  async function connectAEManual() {
    if (!aeAccessToken.trim()) return;
    setAeBusy(true);
    try {
      await supplierApi.connectAliExpress(aeAppKey.trim(), aeAppSecret.trim(), aeAccessToken.trim());
      setAeAppKey(""); setAeAppSecret(""); setAeAccessToken("");
      setAeManualOpen(false);
      refreshSuppliers();
      setBanner({ type: "success", msg: "AliExpress manually connected." });
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to manually connect AliExpress." });
    } finally { setAeBusy(false); }
  }

  const searchParams = useSearchParams();

  const refreshTg = useCallback(() => {
    telegramApi.connection().then(setTgConn).catch(() => {});
  }, []);

  const refreshPs = useCallback(() => {
    paystackApi.connection().then(setPsConn).catch(() => {});
  }, []);

  const refreshPh = useCallback(() => {
    payheroApi.connection().then(setPhConn).catch(() => {});
  }, []);

  const applyComposioConnected = useCallback(
    (connected: Record<string, boolean>) => {
      setComposioStatus((prev) =>
        mergeComposioSocialIntoStatus(
          {
            ...COMPOSIO_DISCONNECTED_STATUS,
            ...Object.fromEntries(
              Object.keys(COMPOSIO_DISCONNECTED_STATUS).map((key) => [
                key,
                connected[key] ?? COMPOSIO_DISCONNECTED_STATUS[key],
              ]),
            ),
          },
          composioSocial,
        ),
      );
      writeStoredComposioStatus(connected);
    },
    [composioSocial],
  );

  const refreshComposio = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setComposioStatus({ ...COMPOSIO_DISCONNECTED_STATUS });
      setComposioStatusLoading(false);
      return;
    }
    setComposioStatusRefreshing(true);

    // Stale-while-revalidate: paint last-known state instantly from the cache
    // endpoint, then revalidate against live Composio in the background. The
    // tiles must never sit on "Checking…" waiting for the slow live call.
    let painted = false;
    try {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), 4_000);
      try {
        const cacheRes = await fetch("/api/composio/connections?cached=1", {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (cacheRes.ok) {
          const cacheData = (await cacheRes.json()) as { connected?: Record<string, boolean> };
          applyComposioConnected(cacheData.connected || {});
          painted = true;
        }
      } finally {
        window.clearTimeout(timer);
      }
    } catch {
      /* keep stored / current state */
    } finally {
      // Cache is authoritative for the first paint — stop blocking the UI
      // regardless of whether anything is connected yet.
      setComposioStatusLoading(false);
    }

    try {
      const res = await fetchComposioConnections(token);
      if (res.ok) {
        const data = (await res.json()) as { connected?: Record<string, boolean> };
        applyComposioConnected(data.connected || {});
      }
    } catch {
      /* keep cached / stored state on failure */
    } finally {
      setComposioStatusLoading(false);
      setComposioStatusRefreshing(false);
      if (!painted) {
        // Cache call failed but live may have succeeded — ensure no stuck state.
        setComposioStatusLoading(false);
      }
    }
  }, [applyComposioConnected]);

  const refreshWa = useCallback((status?: WhatsAppStatus | null) => {
    if (status !== undefined) {
      setWaConn(status);
      return;
    }
    whatsappApi.status().then(setWaConn).catch(() => setWaConn(null));
  }, []);

  async function fetchComposioToolkitConnected(toolkit: string): Promise<boolean> {
    const token = getToken();
    if (!token) return false;
    try {
      const res = await fetch(`/api/composio/connections/${toolkit}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return false;
      const data = (await res.json()) as { connected?: boolean };
      return !!data.connected;
    } catch {
      return false;
    }
  }

  async function cleanupComposioPending(toolkit: string): Promise<void> {
    const token = getToken();
    if (!token) return;
    try {
      await fetch(`/api/composio/connections/${toolkit}/cleanup`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      /* best-effort */
    }
  }

  async function waitForComposioConnection(toolkit: string, attempts = 8): Promise<boolean> {
    for (let i = 0; i < attempts; i += 1) {
      const connected = await fetchComposioToolkitConnected(toolkit);
      if (connected) return true;
      await new Promise((r) => setTimeout(r, Math.min(1500 + i * 750, 5000)));
      await refreshComposio();
    }
    return fetchComposioToolkitConnected(toolkit);
  }

  async function composioConnect(toolkit: string, silent = false, extraBody: Record<string, string> = {}): Promise<boolean> {
    const label = toolkit.charAt(0).toUpperCase() + toolkit.slice(1);
    if (composioStatusLoading) {
      if (!silent) {
        setBanner({ type: "error", msg: "Still checking your connections — wait a moment, then try again." });
      }
      return false;
    }
    if (composioStatus[toolkit]) {
      if (!silent) setBanner({ type: "success", msg: `${label} is already connected.` });
      return true;
    }
    setComposioBusy(toolkit);
    const wasConnected = await fetchComposioToolkitConnected(toolkit);
    if (wasConnected) {
      setComposioBusy(null);
      await refreshComposio();
      if (!silent) setBanner({ type: "success", msg: `${label} is already connected.` });
      return true;
    }
    try {
      const token = getToken();
      const res = await fetch(`/api/composio/connect/${toolkit}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token ?? ""}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ redirect_base: window.location.origin, ...extraBody }),
      });
      if (!res.ok) {
        const err = (await res.json().catch(() => ({} as { detail?: unknown }))) as { detail?: unknown };
        const rawDetail = err.detail;
        const errMsg = typeof rawDetail === "string"
          ? rawDetail
          : rawDetail && typeof rawDetail === "object"
            ? ((rawDetail as Record<string, unknown>).message as string) || JSON.stringify(rawDetail)
            : "Could not start connection. Please try again.";
        if (!silent) setBanner({ type: "error", msg: errMsg });
        return false;
      }
      const data = (await res.json()) as { redirect_url?: string };
      if (!data.redirect_url) {
        if (!silent) setBanner({ type: "error", msg: "No redirect URL returned from Composio." });
        return false;
      }
      // Do not use noopener — OAuth callback closes this popup via window.opener.
      const popup = window.open(data.redirect_url, "composio-connect", "width=980,height=760");
      if (!popup) { window.location.href = data.redirect_url; return false; }

      if (!silent) setBanner({ type: "success", msg: "Finish connecting in the popup — it will close automatically when done." });

      await new Promise<void>((resolve) => {
        let poll: any;
        const finish = () => {
          window.removeEventListener("message", onMessage);
          window.clearInterval(poll);
          resolve();
        };
        const onMessage = (event: MessageEvent) => {
          if (event.origin !== window.location.origin) return;
          if (event.data?.type === "composio-connected" && event.data?.toolkit === toolkit) {
            finish();
          }
        };
        window.addEventListener("message", onMessage);
        poll = window.setInterval(() => {
          if (popup.closed) finish();
        }, 500);
      });

      await refreshComposio();
      const nowConnected = await waitForComposioConnection(toolkit);

      if (nowConnected && !wasConnected) {
        if (!silent) setBanner({ type: "success", msg: `${label} connected successfully.` });
      } else if (!nowConnected && !wasConnected) {
        if (!isComposioSocialToolkit(toolkit)) {
          await cleanupComposioPending(toolkit);
        }
        await refreshComposio();
        if (!silent) {
          setBanner({
            type: "error",
            msg: `${label} was not connected. Complete login in the popup, or try again.`,
          });
        }
        return false;
      }

      await refreshComposio();

      // Auto-link Calendar when Gmail connects (same Google account)
      if (toolkit === "gmail" && nowConnected) {
        const freshStatus = await fetch("/api/composio/connections", {
          headers: { Authorization: `Bearer ${token ?? ""}` },
        }).then(r => r.json()).catch(() => ({ connected: {} })) as { connected: Record<string, boolean> };

        if (freshStatus.connected?.gmail && !freshStatus.connected?.googlecalendar) {
          setBanner({ type: "success", msg: "Gmail connected! Now linking Google Calendar…" });
          await composioConnect("googlecalendar", false);
        }
      }

      return nowConnected;
    } catch (e) {
      if (!silent) setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to connect." });
      return false;
    } finally {
      setComposioBusy(null);
    }
  }

  async function shopifyConnectOAuth() {
    const storeName = shopifyShop.trim().replace(/\.myshopify\.com.*/, "");
    if (!storeName) { setBanner({ type: "error", msg: "Enter your store name." }); return; }
    setShopifyBusy(true);
    try {
      const authTok = getToken();
      const res = await fetch(`/api/shopify/oauth/start?shop=${encodeURIComponent(storeName)}`, {
        headers: { Authorization: `Bearer ${authTok ?? ""}` },
      });
      const data = await res.json().catch(() => ({}) as Record<string, unknown>) as { auth_url?: string; detail?: string };
      if (!res.ok || !data.auth_url) {
        setBanner({ type: "error", msg: typeof data.detail === "string" ? data.detail : "Couldn't start Shopify OAuth. Is the app configured?" });
        return;
      }
      const popup = window.open(data.auth_url, "shopify-oauth", "width=1024,height=768,noopener,noreferrer");
      if (!popup) { window.location.href = data.auth_url; return; }
      setBanner({ type: "success", msg: "Approve access in the Shopify popup." });
      await new Promise<void>((resolve) => {
        const poll = window.setInterval(() => { if (popup.closed) { window.clearInterval(poll); resolve(); } }, 800);
      });
      await new Promise((r) => setTimeout(r, 1200));
      const check = await fetch("/api/composio/connections", { headers: { Authorization: `Bearer ${authTok ?? ""}` } })
        .then((r) => r.json()).catch(() => ({ connected: {} })) as { connected: Record<string, boolean> };
      if (check.connected?.shopify) {
        setComposioStatus((prev) => ({ ...prev, shopify: true }));
        setBanner({ type: "success", msg: "Shopify connected!" });
        setShopifyFormOpen("none");
      } else {
        setBanner({ type: "error", msg: "Didn't detect connection yet — refresh the page after approving." });
      }
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "OAuth failed" });
    } finally {
      setShopifyBusy(false);
    }
  }

  async function shopifyConnectDirect() {
    const domain = shopifyDomain.trim();
    const token  = shopifyToken.trim();
    if (!domain || !token) { setBanner({ type: "error", msg: "Enter your store domain and API token." }); return; }
    setShopifyBusy(true);
    try {
      const authTok = getToken();
      const res = await fetch("/api/shopify/connect-direct", {
        method: "POST",
        headers: { Authorization: `Bearer ${authTok ?? ""}`, "Content-Type": "application/json" },
        body: JSON.stringify({ domain, token }),
      });
      const data = await res.json().catch(() => ({}) as Record<string, unknown>) as Record<string, unknown>;
      if (!res.ok) {
        setBanner({ type: "error", msg: typeof data.detail === "string" ? data.detail : "Connection failed — check domain and token." });
        return;
      }
      const shopName = typeof data.shop_name === "string" ? data.shop_name : domain;
      setBanner({ type: "success", msg: `Shopify connected to ${shopName}!` });
      setShopifyFormOpen("none");
      setShopifyDomain(""); setShopifyToken("");
      setComposioStatus((prev) => ({ ...prev, shopify: true }));
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Connection failed" });
    } finally {
      setShopifyBusy(false);
    }
  }

  async function shopifyDisconnectDirect() {
    if (!confirm("Disconnect Shopify?")) return;
    setShopifyBusy(true);
    try {
      const authTok = getToken();
      const res = await fetch("/api/shopify/connect-direct", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${authTok ?? ""}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({})) as { detail?: string };
        setBanner({ type: "error", msg: (data.detail as string) || "Disconnect failed. Please try again." });
        return;
      }
      setComposioStatus((prev) => ({ ...prev, shopify: false }));
      setBanner({ type: "success", msg: "Shopify disconnected." });
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Disconnect failed" });
    } finally {
      setShopifyBusy(false);
    }
  }

  async function composioDisconnect(toolkit: string, label: string) {
    if (!confirm(`Disconnect ${label}?`)) return;
    setComposioBusy(toolkit);
    try {
      const token = getToken();
      const res = await fetch(`/api/composio/connections/${toolkit}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token ?? ""}` },
      });
      if (!res.ok) {
        const err = (await res.json().catch(() => ({} as { detail?: string }))) as { detail?: string };
        setBanner({ type: "error", msg: err.detail || `Failed to disconnect ${label}.` });
        return;
      }
      // Optimistically clear the tile. The social-settings merge is additive-only
      // (it can set true but never false), so we must explicitly drop the toolkit
      // here — otherwise a stale composioSocial value resurrects the connection.
      setComposioStatus((prev) => ({ ...prev, [toolkit]: false }));
      if (isComposioSocialToolkit(toolkit)) {
        setComposioSocial((prev) => {
          if (!prev) return prev;
          const cleared = { ...prev } as ComposioSocialSettings;
          const platform = (cleared as unknown as Record<string, { connected?: boolean } | undefined>)[toolkit];
          if (platform) {
            (cleared as unknown as Record<string, unknown>)[toolkit] = { ...platform, connected: false };
          }
          return cleared;
        });
        if (toolkit === "facebook") {
          setShowComposioFbPagePicker(false);
          setComposioFbPages([]);
        }
        // Refresh social settings first so the subsequent connections refresh
        // (which OR-merges composioSocial) sees the cleared state.
        await refreshComposioSocial();
      }
      await refreshComposio();
      // Final authoritative write: refreshComposio's internal applyComposioConnected
      // closes over a possibly-stale composioSocial and may re-OR the tile on. This
      // last functional update runs after those, so the disconnected tile stays off.
      setComposioStatus((prev) => ({ ...prev, [toolkit]: false }));
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : `Failed to disconnect ${label}.` });
    } finally {
      setComposioBusy(null);
    }
  }

  const liAuthorAutoPrompted = useRef(false);

  useEffect(() => { refreshTg(); refreshPs(); refreshPh(); refreshWa(); void refreshZernio(); void refreshComposio(); void refreshComposioSocial(); refreshSuppliers(); }, [refreshTg, refreshPs, refreshPh, refreshWa, refreshZernio, refreshComposio, refreshComposioSocial, refreshSuppliers]);

  // LinkedIn is a 2-step flow: OAuth connect, then pick posting identity (like Facebook Page).
  // Wait until connection status finishes loading — avoids stampeding Composio on page open.
  useEffect(() => {
    if (composioStatusLoading) return;
    if (liAuthorAutoPrompted.current) return;
    if (!composioSocial?.linkedin?.connected || composioSocial.linkedin.author_urn) return;
    liAuthorAutoPrompted.current = true;
    setShowComposioLiAuthorPicker(true);
    void loadComposioLinkedInAuthors(true);
  }, [composioSocial?.linkedin?.connected, composioSocial?.linkedin?.author_urn, composioStatusLoading, loadComposioLinkedInAuthors]);

  // Hard safety net — tiles can never sit on "Checking…" longer than this.
  useEffect(() => {
    const t = window.setTimeout(() => setComposioStatusLoading(false), 5_000);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(() => {
    const connected = searchParams.get("connected");
    const error = searchParams.get("error");
    if (connected) {
      // OAuth finished inside the Composio popup — notify parent and close.
      const inOAuthPopup =
        typeof window !== "undefined" &&
        (window.name === "composio-connect" || (window.opener && !window.opener.closed));
      if (inOAuthPopup) {
        try {
          window.opener?.postMessage({ type: "composio-connected", toolkit: connected }, window.location.origin);
        } catch {
          /* ignore */
        }
        window.close();
        return;
      }

      void (async () => {
        if (connected === "unipile-linkedin") {
          await refreshComposioSocial();
          await loadLinkedInContracts(true);
          setBanner({ type: "success", msg: "LinkedIn Premium connected. Refresh if inbox is empty." });
          window.history.replaceState({}, "", window.location.pathname);
          return;
        }
        await refreshComposio();
        const label = connected.charAt(0).toUpperCase() + connected.slice(1);
        const ok = await fetchComposioToolkitConnected(connected);
        if (ok) {
          setBanner({ type: "success", msg: `${label} connected successfully.` });
          refreshTg();
          void refreshZernio();
          void refreshComposioSocial();
          if (connected === "facebook") {
            void loadComposioFacebookPages(true);
          }
          if (connected === "linkedin") {
            setShowComposioLiAuthorPicker(true);
            void loadComposioLinkedInAuthors(true);
          }
        } else {
          await cleanupComposioPending(connected);
          await refreshComposio();
          setBanner({
            type: "error",
            msg: `${label} was not connected. Complete login in the popup, or try again.`,
          });
        }
        window.history.replaceState({}, "", window.location.pathname);
      })();
    } else if (error) {
      const msgs: Record<string, string> = {
        oauth_denied: "You cancelled the login. Please try again.",
        token_exchange: "Authentication failed. Please try again.",
        invalid_state: "Session expired. Please try again.",
        server_error: "Server error. Please try again.",
      };
      setBanner({ type: "error", msg: msgs[error] || "Connection failed. Please try again." });
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [searchParams, refreshTg, refreshZernio, refreshComposio, refreshComposioSocial, loadComposioFacebookPages, loadComposioLinkedInAuthors]);

  const FREE_BADGE: BadgeDef = { label: "Free", className: "bg-emerald-100 text-emerald-700" };

  const isComposioToolkitPending = (toolkit: string) =>
    composioStatusLoading && !composioStatus[toolkit];

  const integrationsConnectedCount = useMemo(() => {
    let n = 0;
    for (const t of INTEGRATIONS_COMPOSIO_TOOLKITS) {
      if (composioStatus[t]) n += 1;
    }
    if (composioSocial?.linkedin_premium?.connected || composioSocial?.linkedin?.messaging_connected) {
      n += 1;
    }
    if (tgConn.connected) n += 1;
    if (psConn.connected) n += 1;
    if (phConn.connected) n += 1;
    if (waConn?.connected) n += 1;
    if (supplierStatus.cj) n += 1;
    if (supplierStatus.aliexpress) n += 1;
    return n;
  }, [composioStatus, composioSocial, tgConn, psConn, phConn, waConn, supplierStatus]);

  function ComposioAppTile({
    toolkit,
    title,
    subtitle,
    borderClass,
    icon,
    connectClass,
    connectLabel,
    extra,
    apiKeyHint,
  }: {
    toolkit: string;
    title: string;
    subtitle: string;
    borderClass: string;
    icon: ReactNode;
    connectClass: string;
    connectLabel?: string;
    extra?: ReactNode;
    apiKeyHint?: boolean;
  }) {
    const showApiKeyHint = apiKeyHint ?? COMPOSIO_API_KEY_TOOLKITS.has(toolkit);
    return (
      <SmallTile title={title} subtitle={subtitle} borderClass={borderClass} icon={icon}>
        {showApiKeyHint && !composioStatus[toolkit] ? (
          <p className="mb-1.5 text-[9px] leading-snug text-slate-500">
            Composio will ask for your API key — paste it from {title} settings.
          </p>
        ) : null}
        {extra}
        <ComposioTileControls
          connected={!!composioStatus[toolkit]}
          busy={composioBusy === toolkit}
          statusLoading={isComposioToolkitPending(toolkit)}
          connectLabel={connectLabel ?? `Connect ${title}`}
          connectClass={connectClass}
          onConnect={() => void composioConnect(toolkit)}
          onDisconnect={() => void composioDisconnect(toolkit, title)}
        />
      </SmallTile>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl min-w-0 space-y-5 p-4 sm:p-6">

      {/* Header */}
      <div className="rounded-xl border border-slate-200/90 bg-gradient-to-br from-white to-slate-50/80 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-brand/15 text-brand-dark">
              <Plug size={18} />
            </div>
            <h1 className="text-xl font-bold text-slate-900">Integrations</h1>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500 sm:text-sm">
              For founders and early-stage teams — connect only what you need. Run ads and Apollo for leads, Brevo for email, Stripe for payments, or pick your own mix. Every app below uses Composio (except WhatsApp QR, Paystack, PayHero, and suppliers).
            </p>
            <p className="mt-2 flex max-w-2xl items-start gap-1.5 text-[11px] leading-relaxed text-slate-500 sm:text-xs">
              <Shield size={14} className="mt-0.5 shrink-0 text-emerald-600" aria-hidden />
              <span>
                We&apos;ve partnered with{" "}
                <a
                  href="https://composio.dev"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-brand-dark"
                >
                  Composio
                </a>{" "}
                to help ensure high security for your data and connected accounts.
              </span>
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-center shadow-sm">
            <p className="text-lg font-bold text-brand-dark">{integrationsConnectedCount}</p>
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Connected</p>
            {composioStatusRefreshing ? (
              <p className="mt-0.5 text-[9px] text-slate-400">Refreshing…</p>
            ) : null}
          </div>
        </div>
        <nav className="mt-4 flex flex-wrap gap-1.5" aria-label="Integration sections">
          {INTEGRATION_NAV.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-semibold text-slate-600 transition-colors hover:border-brand/30 hover:bg-brand/5 hover:text-brand-dark"
            >
              {item.label}
            </a>
          ))}
        </nav>
      </div>

      {/* Banner */}
      {banner && (
        <div className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-xs font-medium ${
          banner.type === "success" ? "border-green-200 bg-green-50 text-green-800" : "border-red-200 bg-red-50 text-red-800"
        }`}>
          {banner.type === "success" ? <CheckCircle size={14} className="mt-0.5 shrink-0" /> : <AlertCircle size={14} className="mt-0.5 shrink-0" />}
          <span>{banner.msg}</span>
          <button onClick={() => setBanner(null)} className="ml-auto opacity-50 hover:opacity-100">✕</button>
        </div>
      )}

      {showLiContractPicker && (
        <section className="rounded-lg border border-[#0A66C2]/30 bg-[#0A66C2]/5 px-3 py-3">
          <div className="mb-2 space-y-1.5">
            <h3 className="text-xs font-semibold text-[#004182]">Select LinkedIn Premium contract</h3>
            <p className="text-[11px] text-[#004182]">
              Choose Sales Navigator or Recruiter so InMail and search use the right subscription.
            </p>
          </div>
          {liLoadingContracts ? (
            <div className="flex items-center gap-1.5 text-[11px] text-[#004182]">
              <Loader2 size={12} className="animate-spin" /> Loading contracts...
            </div>
          ) : liContracts.length ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {liContracts.map((contract) => (
                <button
                  key={contract.id}
                  type="button"
                  onClick={() => void completeLinkedInContractSelect(contract)}
                  disabled={liSelectingContractId === contract.id}
                  className="flex items-center justify-between rounded-lg border border-[#0A66C2]/20 bg-white px-3 py-2 text-left text-xs hover:bg-[#0A66C2]/10 disabled:opacity-60"
                >
                  <span>
                    <span className="block font-semibold text-slate-800">{contract.name}</span>
                    <span className="text-[10px] text-slate-500 capitalize">
                      {contract.product?.replace(/_/g, " ")}
                      {contract.selected ? " · active" : ""}
                    </span>
                  </span>
                  {liSelectingContractId === contract.id ? (
                    <Loader2 size={12} className="animate-spin text-[#0A66C2]" />
                  ) : (
                    <CheckCircle size={12} className="text-[#0A66C2]" />
                  )}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-[#004182]">No contracts found. You may not have Sales Navigator or Recruiter on this account.</p>
          )}
        </section>
      )}

      {showComposioFbPagePicker && (
        <section className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-3">
          <div className="mb-2 space-y-1.5">
            <h3 className="text-xs font-semibold text-blue-900">Select Facebook Page</h3>
            <p className="text-[11px] text-blue-800">Choose which Facebook Page to use for publishing posts.</p>
            <div className="rounded border border-blue-200/50 bg-blue-100/50 p-2 text-[10px] leading-relaxed text-blue-800">
              💡 <strong>Missing a page?</strong> Make sure you have authorized that page and granted all permissions during the Facebook connection flow. If needed, disconnect and reconnect Facebook.
            </div>
          </div>
          {fbLoadingPages ? (
            <div className="flex items-center gap-1.5 text-[11px] text-blue-800">
              <Loader2 size={12} className="animate-spin text-blue-700" /> Loading your pages...
            </div>
          ) : composioFbPages.length ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {composioFbPages.map((page) => (
                <button
                  key={page.id}
                  type="button"
                  onClick={() => void completeComposioFacebookPageSelect(page)}
                  disabled={fbCompletingPageId === page.id}
                  className="flex items-center justify-between rounded-lg border border-blue-200 bg-white px-3 py-2 text-left text-xs hover:bg-blue-100 hover:border-blue-300 disabled:opacity-60 disabled:cursor-not-allowed transition-colors duration-150 cursor-pointer"
                >
                  <div className="pointer-events-none">
                    <p className="font-semibold text-slate-900">{page.name || "Untitled Page"}</p>
                    <p className="text-[10px] text-slate-500">{page.username ? `@${page.username}` : page.category || "Facebook Page"}</p>
                  </div>
                  {fbCompletingPageId === page.id ? (
                    <Loader2 size={12} className="animate-spin text-blue-700 shrink-0" />
                  ) : (
                    <span className="text-blue-700 font-semibold shrink-0 pointer-events-none">Select</span>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-blue-900">No pages found. Try reconnecting Facebook.</p>
          )}
        </section>
      )}

      <IntegrationSection
        id="integrations-messaging"
        title="Messaging"
        description="Fast setup for WhatsApp and Telegram. Use Social Channels below for Business API and OAuth."
        badge={FREE_BADGE}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SmallTile
            title="WhatsApp" subtitle="QR-link · quick setup for small teams"
            borderClass="border-[#25D366]/30 bg-[#25D366]/10" badge={FREE_BADGE}
            icon={<WaGlyph className="h-5 w-5 text-[#25D366]" />}
          >
            <WhatsAppIntegrationControls onChanged={(s) => refreshWa(s)} />
          </SmallTile>

          <SmallTile
            title="Telegram" subtitle="Manual bot token · quick tests"
            borderClass="border-[#229ED9]/20 bg-sky-50/50" badge={FREE_BADGE}
            icon={<TelegramGlyph className="h-5 w-5 text-[#229ED9]" />}
          >
            <TelegramStatus connection={tgConn} onChanged={refreshTg} />
          </SmallTile>
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-social"
        title="Social Channels"
        description="Publish, listen, and reply across social platforms. LinkedIn Premium adds inbox, InMail, and Sales Navigator. Connect only the channels you use."
        badge={{ label: "Composio", className: "bg-brand/10 text-brand-dark ring-1 ring-brand/20" }}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {INTEGRATIONS_SOCIAL_PLATFORMS.map((p) => {
            if (p.id === "linkedin_premium") {
              const liPremium = composioSocial?.linkedin_premium;
              const liConnected = !!liPremium?.connected || !!composioSocial?.linkedin?.messaging_connected;
              const subtitle = liConnected
                ? (liPremium?.name ? `Connected · ${liPremium.name}` : "Connected")
                : "Email + password below";
              return (
                <SmallTile
                  key={p.id}
                  title={p.label}
                  subtitle={subtitle}
                  borderClass={liConnected ? `${p.border} ${p.bg}` : "border-slate-200"}
                  badge={{ label: "Premium", className: "bg-amber-100 text-amber-800 ring-1 ring-amber-200" }}
                  icon={<div className="h-5 w-5">{p.logo}</div>}
                >
                  <div className="space-y-1.5">
                    {liConnected ? (
                      <div className="space-y-1">
                        {liPremiumShowMore ? (
                          <>
                            {(liPremium?.contract_name || composioSocial?.linkedin?.contract_name) ? (
                              <p className="text-[10px] text-slate-600">
                                Contract: <span className="font-semibold">{liPremium?.contract_name || composioSocial?.linkedin?.contract_name}</span>
                              </p>
                            ) : null}
                            {(liPremium?.inmail_balance || composioSocial?.linkedin?.inmail_balance) ? (
                              <p className="text-[10px] text-slate-500">
                                InMail: {(liPremium?.inmail_balance || composioSocial?.linkedin?.inmail_balance)?.sales_navigator ?? "—"} Sales Nav credits
                              </p>
                            ) : null}
                            <button
                              type="button"
                              disabled={unipileBusy || liLoadingContracts}
                              onClick={() => {
                                setShowLiContractPicker(true);
                                void loadLinkedInContracts(false);
                              }}
                              className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                            >
                              {liLoadingContracts ? "Loading…" : (liPremium?.contract_id || composioSocial?.linkedin?.contract_id) ? "Change contract" : "Select contract"}
                            </button>
                          </>
                        ) : null}
                        <button
                          type="button"
                          disabled={unipileBusy}
                          onClick={() => void unipileDisconnectLinkedIn()}
                          className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                        >
                          {unipileBusy ? <Loader2 size={11} className="animate-spin" /> : <><X size={11} /><span>Disconnect</span></>}
                        </button>
                      </div>
                    ) : liCheckpoint ? (
                      <div className="space-y-1.5">
                        <p className="text-[10px] text-slate-600">{liCheckpoint.message}</p>
                        {liCheckpoint.checkpoint_type === "IN_APP_VALIDATION" ? (
                          <div className="space-y-1">
                            <button
                              type="button"
                              disabled={unipileBusy}
                              onClick={() => void pollLinkedInInAppApproval()}
                              className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#0A66C2] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#004182] disabled:opacity-50"
                            >
                              {unipileBusy ? <Loader2 size={11} className="animate-spin" /> : <span>I approved in the app</span>}
                            </button>
                            <button
                              type="button"
                              disabled={unipileBusy}
                              onClick={() => void submitLinkedInCheckpoint("TRY_ANOTHER_WAY")}
                              className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                            >
                              Use SMS / authenticator instead
                            </button>
                          </div>
                        ) : (
                          <div className="space-y-1">
                            <input
                              type="text"
                              value={liCheckpointCode}
                              onChange={(e) => setLiCheckpointCode(e.target.value)}
                              placeholder={liCheckpoint.checkpoint_type === "PHONE_REGISTER" ? "(+1)5551234567" : "Verification code"}
                              autoComplete="one-time-code"
                              className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#0A66C2]"
                            />
                            <button
                              type="button"
                              disabled={unipileBusy || !liCheckpointCode.trim()}
                              onClick={() => void submitLinkedInCheckpoint()}
                              className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#0A66C2] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#004182] disabled:opacity-50"
                            >
                              {unipileBusy ? <Loader2 size={11} className="animate-spin" /> : <span>Verify</span>}
                            </button>
                          </div>
                        )}
                        <button
                          type="button"
                          disabled={unipileBusy}
                          onClick={() => { setLiCheckpoint(null); setLiCheckpointCode(""); }}
                          className="w-full text-[10px] font-medium text-slate-500 hover:text-slate-700"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : liMsgMethod === "cookie" ? (
                      <div className="space-y-1">
                        {liPremiumShowMore ? (
                          <ol className="list-decimal space-y-0.5 pl-4 text-[9px] text-slate-500">
                            <li>Log into linkedin.com (Google sign-in is fine)</li>
                            <li>F12 → Application → Cookies → copy <span className="font-mono">li_at</span></li>
                          </ol>
                        ) : null}
                        <input
                          type="password"
                          value={liMsgCookie}
                          onChange={(e) => setLiMsgCookie(e.target.value)}
                          placeholder="li_at cookie"
                          autoComplete="off"
                          className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] font-mono outline-none focus:border-[#0A66C2]"
                        />
                        <button
                          type="button"
                          disabled={unipileBusy || !liMsgCookie.trim()}
                          onClick={() => void submitLinkedInCookie()}
                          className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#0A66C2] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#004182] disabled:opacity-50"
                        >
                          {unipileBusy ? <Loader2 size={11} className="animate-spin" /> : <><Plug size={11} /><span>Connect</span></>}
                        </button>
                        <button
                          type="button"
                          disabled={unipileBusy}
                          onClick={() => { setLiMsgMethod("password"); setLiMsgCookie(""); }}
                          className="w-full text-[10px] font-medium text-slate-500 hover:text-slate-700"
                        >
                          Use email + password
                        </button>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <input
                          type="email"
                          value={liMsgEmail}
                          onChange={(e) => setLiMsgEmail(e.target.value)}
                          placeholder="LinkedIn email"
                          autoComplete="username"
                          className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#0A66C2]"
                        />
                        <input
                          type="password"
                          value={liMsgPassword}
                          onChange={(e) => setLiMsgPassword(e.target.value)}
                          placeholder="LinkedIn password"
                          autoComplete="current-password"
                          className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#0A66C2]"
                        />
                        <button
                          type="button"
                          disabled={unipileBusy || !liMsgEmail.trim() || !liMsgPassword}
                          onClick={() => void submitLinkedInMessagingCredentials()}
                          className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#0A66C2] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#004182] disabled:opacity-50"
                        >
                          {unipileBusy ? <Loader2 size={11} className="animate-spin" /> : <><Plug size={11} /><span>Connect</span></>}
                        </button>
                        <button
                          type="button"
                          disabled={unipileBusy}
                          onClick={() => { setLiMsgMethod("cookie"); setLiMsgEmail(""); setLiMsgPassword(""); }}
                          className="w-full text-[10px] font-medium text-slate-500 hover:text-slate-700"
                        >
                          Google login? Use cookie
                        </button>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => setLiPremiumShowMore((v) => !v)}
                      className="w-full text-[10px] font-medium text-[#0A66C2] hover:text-[#004182]"
                    >
                      {liPremiumShowMore ? "Less" : "More"}
                    </button>
                    {liPremiumShowMore ? (
                      <div className="space-y-1 text-[9px] leading-snug text-slate-500">
                        <p>One connect for posting, inbox, InMail, Sales Navigator, and connection requests. Requires Sales Nav or Recruiter.</p>
                        {!liConnected && liMsgMethod === "password" ? (
                          <button
                            type="button"
                            disabled={unipileBusy}
                            onClick={() => void unipileConnectLinkedInHosted()}
                            className="text-[10px] font-medium text-slate-500 hover:text-slate-700 disabled:opacity-50"
                          >
                            Or use Unipile popup
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </SmallTile>
              );
            }

            if (COMPOSIO_SOCIAL_IDS.has(p.id)) {
              const connected = composioStatus[p.id] === true || (p.id === "linkedin" && !!composioSocial?.linkedin?.connected);
              const fbPageName = p.id === "facebook" ? composioSocial?.facebook.page_name : null;
              const igProfile = p.id === "instagram" ? composioSocial?.instagram : null;
              const igUsername = igProfile?.username || null;
              const igLinked = p.id === "instagram" ? (igProfile?.user_id || igUsername) : null;
              const liAuthor = p.id === "linkedin" ? composioSocial?.linkedin?.author_name : null;
              const needsPage = p.id === "facebook" && connected && !composioSocial?.facebook.page_id;
              const needsLiAuthor = p.id === "linkedin" && connected && !composioSocial?.linkedin?.author_urn;
              const subtitle = connected
                ? needsPage
                  ? "Select a Page to publish"
                  : needsLiAuthor
                    ? "Step 2 · Choose who to post as"
                    : p.id === "facebook" && fbPageName
                      ? fbPageName
                      : p.id === "instagram" && igUsername
                        ? `@${igUsername}`
                        : p.id === "instagram" && igLinked
                          ? "Business account linked"
                        : p.id === "linkedin" && liAuthor
                          ? `Posting as ${liAuthor}`
                          : p.id === "linkedin"
                            ? "Connected — schedule posts"
                            : "Connected via Composio"
                : p.id === "linkedin"
                  ? "Step 1 · Connect, then choose posting identity"
                  : p.id === "whatsapp"
                    ? "Business API · secure OAuth"
                    : p.id === "telegram"
                      ? "Easy connect via Composio"
                      : p.id === "reddit"
                        ? "Customer intent & communities"
                        : "Connect via Composio";
              return (
                <SmallTile
                  key={p.id}
                  title={p.label}
                  subtitle={subtitle}
                  borderClass={connected ? `${p.border} ${p.bg}` : "border-slate-200"}
                  badge={p.id === "linkedin" ? { label: "Included", className: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" } : undefined}
                  icon={<div className="h-5 w-5">{p.logo}</div>}
                >
                  <div className="space-y-1.5">
                    {p.id === "linkedin" && !connected ? (
                      <p className="text-[9px] text-slate-500">Posting only — use Premium for inbox & Sales Nav.</p>
                    ) : null}
                    {p.id === "instagram" && connected && (igProfile?.username || igProfile?.name || igProfile?.profile_picture_url) ? (
                      <div className="flex items-center gap-2 rounded-lg border border-pink-200 bg-pink-50/60 px-2.5 py-2">
                        {igProfile?.profile_picture_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={igProfile.profile_picture_url}
                            alt={igProfile?.username ? `@${igProfile.username}` : "Instagram profile"}
                            className="h-9 w-9 flex-shrink-0 rounded-full object-cover ring-1 ring-pink-200"
                          />
                        ) : (
                          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-pink-100 text-pink-600 ring-1 ring-pink-200">
                            <CheckCircle2 size={16} />
                          </div>
                        )}
                        <div className="min-w-0">
                          {igProfile?.name ? (
                            <p className="truncate text-[11px] font-semibold text-slate-800">{igProfile.name}</p>
                          ) : null}
                          {igProfile?.username ? (
                            <p className="truncate text-[10px] text-slate-500">@{igProfile.username}</p>
                          ) : null}
                          {typeof igProfile?.followers_count === "number" ? (
                            <p className="text-[9px] text-slate-400">{igProfile.followers_count.toLocaleString()} followers</p>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                    <ComposioTileControls
                      connected={connected}
                      busy={composioBusy === p.id}
                      statusLoading={composioStatusLoading && !connected}
                      connectLabel={p.id === "linkedin" ? "Connect LinkedIn" : `Connect ${p.label}`}
                      connectClass="bg-brand-dark hover:bg-brand"
                      onConnect={() => void composioConnectSocial(p.id)}
                      onDisconnect={() => void composioDisconnect(p.id, p.label)}
                    />
                    {p.id === "facebook" && connected && (
                      <button
                        type="button"
                        onClick={() => void openFacebookPagePicker()}
                        className="flex w-full items-center justify-center rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        {composioSocial?.facebook.page_id ? "Change Page" : "Select Page"}
                      </button>
                    )}
                    {p.id === "linkedin" && connected && (
                      <>
                        <button
                          type="button"
                          onClick={() => openLinkedInAuthorPicker()}
                          disabled={liLoadingAuthors && showComposioLiAuthorPicker}
                          className="flex w-full items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                        >
                          {liLoadingAuthors && showComposioLiAuthorPicker ? (
                            <>
                              <Loader2 size={12} className="animate-spin" />
                              Loading…
                            </>
                          ) : (
                            composioSocial?.linkedin?.author_urn ? "Change posting identity" : "Select posting identity"
                          )}
                        </button>
                        {showComposioLiAuthorPicker ? (
                          <div className="rounded-lg border border-[#0A66C2]/30 bg-[#0A66C2]/5 px-2.5 py-2">
                            <div className="mb-1.5 flex items-start justify-between gap-2">
                              <p className="text-[10px] font-semibold text-[#004182]">Who should we post as?</p>
                              <button
                                type="button"
                                onClick={() => {
                                  setShowComposioLiAuthorPicker(false);
                                  setLiAuthorLoadError(null);
                                  setComposioLiAuthors([]);
                                }}
                                className="shrink-0 text-[10px] text-slate-400 hover:text-slate-600"
                                aria-label="Close"
                              >
                                ✕
                              </button>
                            </div>
                            {liLoadingAuthors ? (
                              <div className="flex items-center gap-1.5 text-[10px] text-[#004182]">
                                <Loader2 size={11} className="animate-spin" /> Loading identities…
                              </div>
                            ) : composioLiAuthors.length ? (
                              <div className="space-y-1.5">
                                {composioLiAuthors.map((author) => (
                                  <button
                                    key={author.urn}
                                    type="button"
                                    onClick={() => void completeComposioLinkedInAuthorSelect(author)}
                                    disabled={liCompletingAuthorUrn === author.urn}
                                    className="flex w-full items-center justify-between rounded-md border border-[#0A66C2]/20 bg-white px-2 py-1.5 text-left text-[10px] hover:bg-[#0A66C2]/10 disabled:opacity-60"
                                  >
                                    <span>
                                      <span className="block font-semibold text-slate-900">{author.name}</span>
                                      <span className="text-[9px] text-slate-500 capitalize">
                                        {author.type === "organization" ? "Company page" : "Personal profile"}
                                      </span>
                                    </span>
                                    {liCompletingAuthorUrn === author.urn ? (
                                      <Loader2 size={11} className="animate-spin shrink-0" />
                                    ) : (
                                      <span className="shrink-0 font-semibold text-[#0A66C2]">Select</span>
                                    )}
                                  </button>
                                ))}
                              </div>
                            ) : (
                              <p className="text-[10px] leading-snug text-red-700">
                                {liAuthorLoadError || "No identities found. Disconnect LinkedIn and connect again."}
                              </p>
                            )}
                          </div>
                        ) : null}
                      </>
                    )}
                  </div>
                </SmallTile>
              );
            }

            return null;
          })}
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-crm"
        title="CRM & Sales"
        description="Pick one CRM plus outreach tools that match how you sell. Example: Apollo for leads + Instantly or Brevo for email sequences."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <ComposioAppTile
            toolkit="hubspot"
            title="HubSpot"
            subtitle="CRM, deals, email & marketing hub"
            borderClass="border-[#FF7A59]/25 bg-[#FF7A59]/5"
            icon={<HubSpotGlyph className="h-5 w-5" />}
            connectClass="bg-[#FF7A59] hover:bg-[#e56a4a]"
          />
          <ComposioAppTile
            toolkit="salesforce"
            title="Salesforce"
            subtitle="Enterprise CRM & pipeline"
            borderClass="border-[#00A1E0]/25 bg-[#00A1E0]/5"
            icon={<SalesforceGlyph className="h-5 w-5" />}
            connectClass="bg-[#00A1E0] hover:bg-[#0088c2]"
          />
          <ComposioAppTile
            toolkit="pipedrive"
            title="Pipedrive"
            subtitle="Simple sales pipeline for SMBs"
            borderClass="border-[#017737]/25 bg-[#017737]/5"
            icon={<PipedriveGlyph className="h-5 w-5" />}
            connectClass="bg-[#017737] hover:bg-[#015c2c]"
          />
          <ComposioAppTile
            toolkit="apollo"
            title="Apollo"
            subtitle="B2B lead database & enrichment"
            borderClass="border-slate-300/60 bg-slate-50"
            icon={<ApolloGlyph className="h-5 w-5" />}
            connectClass="bg-slate-800 hover:bg-slate-700"
          />
          <ComposioAppTile
            toolkit="instantly"
            title="Instantly"
            subtitle="Cold email campaigns & sequences (Apollo alternative)"
            borderClass="border-[#0066FF]/20 bg-[#0066FF]/5"
            icon={<InstantlyGlyph className="h-5 w-5" />}
            connectClass="bg-[#0066FF] hover:bg-[#0052cc]"
          />
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-comms"
        title="Email & Meetings"
        description="Email, calendar, scheduling, and video — keep customer conversations in one place."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <div id="integrations-gmail" className="min-w-0">
            <ComposioAppTile
              toolkit="gmail"
              title="Gmail"
              subtitle="Read, send & draft emails"
              borderClass="border-red-200 bg-red-50/50"
              icon={<Mail size={18} className="text-red-500" />}
              connectClass="bg-red-500 hover:bg-red-600"
            />
          </div>
          <div id="integrations-microsoft" className="min-w-0">
            <ComposioAppTile
              toolkit="outlook"
              title="Microsoft"
              subtitle="Outlook, Calendar & Contacts"
              borderClass="border-[#0078D4]/20 bg-[#0078D4]/5"
              icon={<MicrosoftGlyph className="h-5 w-5 text-[#0078D4]" />}
              connectClass="bg-[#0078D4] hover:bg-[#006abc]"
              connectLabel="Connect Microsoft"
            />
          </div>
          <div id="integrations-google-calendar" className="min-w-0">
            <ComposioAppTile
              toolkit="googlecalendar"
              title="Google Calendar"
              subtitle="Events, meetings & scheduling"
              borderClass="border-emerald-200 bg-emerald-50/50"
              icon={<Calendar size={18} className="text-emerald-600" />}
              connectClass="bg-emerald-600 hover:bg-emerald-700"
              connectLabel="Connect Calendar"
            />
          </div>
          <ComposioAppTile
            toolkit="calendly"
            title="Calendly"
            subtitle="Booking links & appointment scheduling"
            borderClass="border-[#006BFF]/20 bg-[#006BFF]/5"
            icon={<CalendlyGlyph className="h-5 w-5" />}
            connectClass="bg-[#006BFF] hover:bg-[#0056cc]"
          />
          <ComposioAppTile
            toolkit="zoom"
            title="Zoom"
            subtitle="Video meetings & webinars"
            borderClass="border-[#2D8CFF]/20 bg-[#2D8CFF]/5"
            icon={<ZoomGlyph className="h-5 w-5" />}
            connectClass="bg-[#2D8CFF] hover:bg-[#1a7ae6]"
          />
          <div id="integrations-slack" className="min-w-0">
            <ComposioAppTile
              toolkit="slack"
              title="Slack"
              subtitle="Team notifications & alerts"
              borderClass="border-[#4A154B]/20 bg-[#4A154B]/5"
              icon={<SlackGlyph className="h-5 w-5 text-[#4A154B]" />}
              connectClass="bg-[#4A154B] hover:bg-[#3e1240]"
            />
          </div>
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-payments"
        title="Payments"
        description="Accept payments locally and internationally."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SmallTile
            title="Stripe" subtitle="International payments &amp; subscriptions"
            borderClass="border-[#635BFF]/20 bg-[#635BFF]/5"
            icon={<StripeGlyph className="h-5 w-5 text-[#635BFF]" />}
          >
            <ComposioTileControls
              connected={composioStatus.stripe}
              busy={composioBusy === "stripe"}
              statusLoading={isComposioToolkitPending("stripe")}
              connectLabel="Connect Stripe"
              connectClass="bg-[#635BFF] hover:bg-[#4f46e5]"
              onConnect={() => void composioConnect("stripe")}
              onDisconnect={() => void composioDisconnect("stripe", "Stripe")}
            />
          </SmallTile>

          <SmallTile
            title="Paystack" subtitle="Payments across Africa — NGN, KES, GHS &amp; more"
            borderClass="border-[#00C3F7]/20 bg-[#00C3F7]/5"
            icon={<PaystackGlyph className="h-5 w-5 text-[#00C3F7]" />}
          >
            <PaystackStatus connection={psConn} onChanged={refreshPs} />
          </SmallTile>

          <SmallTile
            title="PayHero" subtitle="M-Pesa STK push &amp; mobile money — Kenya"
            borderClass="border-[#1DB954]/20 bg-[#1DB954]/5"
            icon={<PayHeroGlyph className="h-5 w-5 text-[#1DB954]" />}
          >
            <PayHeroStatus connection={phConn} onChanged={refreshPh} />
          </SmallTile>
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-marketing"
        title="Email Marketing"
        description="Reach leads after Apollo or ads — newsletters, drips, and automations. Many teams start with Brevo or Mailchimp."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <ComposioAppTile
            toolkit="klaviyo"
            title="Klaviyo"
            subtitle="Best for e-commerce & Shopify stores"
            borderClass="border-[#00A500]/20 bg-[#00A500]/5"
            icon={<KlaviyoGlyph className="h-5 w-5 text-[#00A500]" />}
            connectClass="bg-[#00A500] hover:bg-[#008000]"
          />
          <ComposioAppTile
            toolkit="mailchimp"
            title="Mailchimp"
            subtitle="Email campaigns & automations"
            borderClass="border-[#FFE01B]/40 bg-[#FFE01B]/10"
            icon={<MailchimpGlyph className="h-5 w-5 text-[#241C15]" />}
            connectClass="bg-[#241C15] hover:bg-black"
          />
          <ComposioAppTile
            toolkit="brevo"
            title="Brevo"
            subtitle="Email, SMS & marketing automation"
            borderClass="border-[#0B996E]/20 bg-[#0B996E]/5"
            icon={<BrevoGlyph className="h-5 w-5 text-[#0B996E]" />}
            connectClass="bg-[#0B996E] hover:bg-[#097a58]"
          />
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-analytics"
        title="Advertising & Analytics"
        description="Run Meta or Google Ads, then measure with GA4 and Search Console. Connect when you are ready to spend on growth."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SmallTile
            title="Google Ads" subtitle="Campaigns, spend &amp; conversion tracking"
            borderClass="border-[#4285F4]/20 bg-[#4285F4]/5"
            icon={
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none">
                <path d="M2.428 13.74L8.37 3.37a3.428 3.428 0 0 1 5.937 3.43l-5.941 10.37a3.428 3.428 0 0 1-5.938-3.43z" fill="#FBBC04"/>
                <path d="M15.632 3.37l-5.941 10.37a3.428 3.428 0 0 0 5.938 3.43L21.57 7.2a3.428 3.428 0 0 0-5.938-3.83z" fill="#4285F4"/>
                <circle cx="4.143" cy="17.143" r="3.428" fill="#34A853"/>
              </svg>
            }
          >
            {!composioStatus.googleads && (
              <input
                type="text"
                value={googleAdsCustomerId}
                onChange={e => setGoogleAdsCustomerId(e.target.value)}
                placeholder="Customer ID (e.g. 123-456-7890)"
                className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs font-mono outline-none focus:border-[#4285F4] mb-1"
              />
            )}
            <ComposioTileControls
              connected={composioStatus.googleads}
              busy={composioBusy === "googleads"}
              statusLoading={isComposioToolkitPending("googleads")}
              connectLabel="Connect Google Ads"
              connectClass="bg-[#4285F4] hover:bg-[#3367d6]"
              onConnect={() => void composioConnect("googleads", false, { customer_id: googleAdsCustomerId })}
              onDisconnect={() => void composioDisconnect("googleads", "Google Ads")}
            />
          </SmallTile>

          <SmallTile
            title="Meta Ads" subtitle="Facebook &amp; Instagram campaigns via Composio"
            borderClass="border-[#1877F2]/20 bg-[#1877F2]/5"
            icon={
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069z" className="text-[#1877F2]"/>
              </svg>
            }
          >
            <ComposioTileControls
              connected={composioStatus.metaads}
              busy={composioBusy === "metaads"}
              statusLoading={isComposioToolkitPending("metaads")}
              connectLabel="Connect Meta Ads"
              connectClass="bg-[#1877F2] hover:bg-[#0d65c7]"
              onConnect={() => void composioConnect("metaads")}
              onDisconnect={() => void composioDisconnect("metaads", "Meta Ads")}
            />
          </SmallTile>

          <SmallTile
            title="Google Analytics 4" subtitle="Visitor counts, sessions &amp; top pages"
            borderClass="border-[#E37400]/20 bg-[#E37400]/5"
            icon={
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none">
                <rect x="2" y="14" width="4" height="8" rx="1" fill="#E37400"/>
                <rect x="9" y="8" width="4" height="14" rx="1" fill="#E37400" opacity="0.7"/>
                <rect x="16" y="2" width="4" height="20" rx="1" fill="#E37400" opacity="0.45"/>
              </svg>
            }
          >
            <ComposioTileControls
              connected={composioStatus.googleanalytics}
              busy={composioBusy === "googleanalytics"}
              statusLoading={isComposioToolkitPending("googleanalytics")}
              connectLabel="Connect GA4"
              connectClass="bg-[#E37400] hover:bg-[#c46200]"
              onConnect={() => void composioConnect("googleanalytics")}
              onDisconnect={() => void composioDisconnect("googleanalytics", "Google Analytics 4")}
            />
          </SmallTile>

          <SmallTile
            title="Search Console" subtitle="Rankings, impressions &amp; click-through rates"
            borderClass="border-[#0F9D58]/20 bg-[#0F9D58]/5"
            icon={
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none">
                <circle cx="11" cy="11" r="7" stroke="#0F9D58" strokeWidth="2"/>
                <path d="M16.5 16.5L21 21" stroke="#0F9D58" strokeWidth="2" strokeLinecap="round"/>
                <path d="M8 11h6M11 8v6" stroke="#0F9D58" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            }
          >
            <ComposioTileControls
              connected={composioStatus.googlesearchconsole}
              busy={composioBusy === "googlesearchconsole"}
              statusLoading={isComposioToolkitPending("googlesearchconsole")}
              connectLabel="Connect Search Console"
              connectClass="bg-[#0F9D58] hover:bg-[#0b7a44]"
              onConnect={() => void composioConnect("googlesearchconsole")}
              onDisconnect={() => void composioDisconnect("googlesearchconsole", "Search Console")}
            />
          </SmallTile>
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-commerce"
        title="Commerce & Accounting"
        description="Online store, orders, and bookkeeping for your business."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SmallTile
            title="Shopify" subtitle="Sync orders, customers &amp; products"
            borderClass="border-[#96BF48]/30 bg-[#96BF48]/10"
            icon={<ShopifyGlyph className="h-5 w-5 text-[#5A8E00]" />}
          >
            {isComposioToolkitPending("shopify") ? (
              <div className="flex items-center justify-center gap-1.5 py-0.5 text-[11px] text-slate-400">
                <Loader2 size={12} className="animate-spin" />
                Checking…
              </div>
            ) : composioStatus.shopify ? (
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
                  <CheckCircle size={12} /> Connected
                </div>
                <button type="button" onClick={() => void shopifyDisconnectDirect()} disabled={shopifyBusy}
                  className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">
                  {shopifyBusy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
                </button>
              </div>
            ) : shopifyFormOpen === "oauth" ? (
              <div className="space-y-1.5">
                <div className="flex items-center bg-white border border-slate-200 rounded-lg overflow-hidden focus-within:ring-1 focus-within:ring-[#96BF48]">
                  <input value={shopifyShop} onChange={(e) => setShopifyShop(e.target.value.replace(/\.myshopify\.com.*/, ""))}
                    placeholder="yourstore" className="flex-1 px-2 py-1.5 text-[11px] outline-none" disabled={shopifyBusy} />
                  <span className="px-1.5 text-[10px] text-slate-400 select-none">.myshopify.com</span>
                </div>
                <div className="flex gap-1.5">
                  <button type="button" onClick={() => void shopifyConnectOAuth()} disabled={shopifyBusy || !shopifyShop.trim()}
                    className="flex-1 flex items-center justify-center gap-1 rounded-lg bg-[#5A8E00] hover:bg-[#4a7500] px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
                    {shopifyBusy ? <Loader2 size={11} className="animate-spin" /> : "Connect"}
                  </button>
                  <button type="button" onClick={() => setShopifyFormOpen("none")}
                    className="px-2 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-500 hover:bg-slate-50">Cancel</button>
                </div>
              </div>
            ) : (
              <button type="button" onClick={() => setShopifyFormOpen("oauth")} disabled={shopifyBusy}
                className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#5A8E00] hover:bg-[#4a7500] px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
                Connect Shopify
              </button>
            )}
          </SmallTile>

          <ComposioAppTile
            toolkit="quickbooks"
            title="QuickBooks"
            subtitle="Invoices, expenses & bookkeeping"
            borderClass="border-[#2CA01C]/25 bg-[#2CA01C]/5"
            icon={<QuickBooksGlyph className="h-5 w-5" />}
            connectClass="bg-[#2CA01C] hover:bg-[#238016]"
          />
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-workspace"
        title="Workspace"
        description="Spreadsheets and docs your team already uses."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <div id="integrations-google-sheets" className="min-w-0">
            <ComposioAppTile
              toolkit="googlesheets"
              title="Google Sheets"
              subtitle="Sync data to & from spreadsheets"
              borderClass="border-[#0F9D58]/20 bg-[#0F9D58]/5"
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <rect width="24" height="24" rx="3" fill="#0F9D58"/>
                  <rect x="5" y="4" width="14" height="16" rx="1" fill="white"/>
                  <rect x="7" y="7" width="10" height="1.5" rx="0.5" fill="#0F9D58"/>
                  <rect x="7" y="10" width="10" height="1.5" rx="0.5" fill="#0F9D58"/>
                  <rect x="7" y="13" width="10" height="1.5" rx="0.5" fill="#0F9D58"/>
                  <rect x="7" y="16" width="6" height="1.5" rx="0.5" fill="#0F9D58"/>
                </svg>
              }
              connectClass="bg-[#0F9D58] hover:bg-[#0b7a44]"
              connectLabel="Connect Sheets"
            />
          </div>
          <div id="integrations-notion" className="min-w-0">
            <ComposioAppTile
              toolkit="notion"
              title="Notion"
              subtitle="Sync pages, databases & notes"
              borderClass="border-slate-300/60 bg-slate-50/80"
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                  <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.14c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.934.653.934 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.374-1.54 1.447-1.632z"/>
                </svg>
              }
              connectClass="bg-slate-900 hover:bg-slate-700"
            />
          </div>
        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-suppliers"
        title="Supplier Accounts"
        description="Dropshipping and product sourcing for e-commerce stores."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">

          {/* CJ Dropshipping */}
          <SmallTile
            title="CJ Dropshipping" subtitle="Source products &amp; auto-fulfill orders"
            borderClass="border-[#FF6600]/20 bg-[#FF6600]/5"
            icon={
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none">
                <rect width="24" height="24" rx="4" fill="#FF6600"/>
                <text x="4" y="17" fontSize="11" fontWeight="bold" fill="white" fontFamily="sans-serif">CJ</text>
              </svg>
            }
          >
            {supplierStatus.cj ? (
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
                  <CheckCircle size={12} /> Connected
                </div>
                <button type="button" onClick={() => void disconnectCJ()} disabled={cjBusy}
                  className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">
                  {cjBusy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
                </button>
              </div>
            ) : (
              <div className="space-y-1.5">
                <input type="email" value={cjEmail} onChange={e => setCjEmail(e.target.value)}
                  placeholder="CJ account email" autoComplete="off"
                  className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#FF6600]" />
                <input type="password" value={cjApiKey} onChange={e => setCjApiKey(e.target.value)}
                  placeholder="API key" autoComplete="off"
                  className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] font-mono outline-none focus:border-[#FF6600]" />
                <button type="button" onClick={() => void connectCJ()} disabled={cjBusy || !cjEmail.trim() || !cjApiKey.trim()}
                  className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#FF6600] hover:bg-[#e05a00] px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
                  {cjBusy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect
                </button>
              </div>
            )}
          </SmallTile>

          {/* AliExpress */}
          <SmallTile
            title="AliExpress DS" subtitle="Source products &amp; auto-fulfill via DS API"
            borderClass="border-[#E62222]/20 bg-[#E62222]/5"
            icon={
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none">
                <rect width="24" height="24" rx="4" fill="#E62222"/>
                <text x="3" y="16" fontSize="8.5" fontWeight="bold" fill="white" fontFamily="sans-serif">AliEx</text>
              </svg>
            }
          >
            {supplierStatus.aliexpress ? (
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
                  <CheckCircle size={12} /> Connected
                </div>
                <button type="button" onClick={() => void disconnectAE()} disabled={aeBusy}
                  className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">
                  {aeBusy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
                </button>
              </div>
            ) : aeManualOpen ? (
              <div className="space-y-1.5">
                <input type="text" value={aeAppKey} onChange={e => setAeAppKey(e.target.value)}
                  placeholder="App Key (optional)" autoComplete="off"
                  className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#E62222]" />
                <input type="password" value={aeAppSecret} onChange={e => setAeAppSecret(e.target.value)}
                  placeholder="App Secret (optional)" autoComplete="off"
                  className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#E62222]" />
                <input type="password" value={aeAccessToken} onChange={e => setAeAccessToken(e.target.value)}
                  placeholder="Access Token (required)" autoComplete="off"
                  className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#E62222]" />
                <div className="flex gap-1">
                  <button type="button" onClick={() => void connectAEManual()} disabled={aeBusy || !aeAccessToken.trim()}
                    className="flex-1 flex items-center justify-center gap-1 rounded-lg bg-[#E62222] hover:bg-[#c71c1c] py-1.5 text-xs font-semibold text-white disabled:opacity-50">
                    {aeBusy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect
                  </button>
                  <button type="button" onClick={() => setAeManualOpen(false)} disabled={aeBusy}
                    className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-1.5">
                <button type="button" onClick={() => void connectAEOAuth()} disabled={aeBusy}
                  className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#E62222] hover:bg-[#c71c1c] px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
                  {aeBusy ? <Loader2 size={11} className="animate-spin" /> : <><span>Connect AliExpress</span><ExternalLink size={9} /></>}
                </button>
                <div className="text-center">
                  <button type="button" onClick={() => setAeManualOpen(true)}
                    className="text-[10px] text-slate-500 hover:text-[#E62222] hover:underline bg-transparent border-0 cursor-pointer">
                    Connect manually with token
                  </button>
                </div>
              </div>
            )}
          </SmallTile>

        </div>
      </IntegrationSection>

      <IntegrationSection
        id="integrations-automation"
        title="Automation"
        description="Let Zilo act inside your own browser — post, click, and pull data from any site."
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <div id="integrations-browser-operator" className="min-w-0">
            <BrowserOperatorStatusTile />
          </div>
        </div>
      </IntegrationSection>

      {/* Footer */}
      <section className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-[11px] leading-relaxed text-slate-600">
        <p>
          <strong className="font-semibold text-slate-800">Pick your stack.</strong> You do not need every tile — connect what you use (e.g. Apollo + Meta Ads + Brevo + Gmail + Stripe) and add more when you are ready.
        </p>
        <p className="mt-1.5">
          OAuth tokens and API keys are handled through our Composio partnership — encrypted, scoped per app, and isolated to your account.
        </p>
        <p className="mt-1.5">
          WhatsApp inbox and broadcasts:{" "}
          <Link href="/dashboard/whatsapp" className="font-medium text-brand-dark hover:underline">WhatsApp</Link>
          {" "}in the sidebar. Account settings:{" "}
          <Link href="/dashboard/settings" className="font-medium text-brand-dark hover:underline">Settings</Link>.
        </p>
      </section>
    </div>
  );
}

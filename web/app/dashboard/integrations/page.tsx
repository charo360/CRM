"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState, useCallback, useMemo, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { NANGO_INTEGRATION_IDS } from "@/lib/nango-config";
import { openNangoConnect } from "@/lib/nango-connect";
import {
  API_BASE,
  telegramApi,
  type TelegramConnection,
  paystackApi,
  type PaystackConnection,
  flutterwaveApi,
  type FlutterwaveConnection,
  stripeConnectApi,
  type StripeConnection,
  type StripeConnectStatus as StripeLifecycleStatus,
  payheroApi,
  type PayheroConnection,
  type PayheroChannel,
  supplierApi,
  type SupplierConnections,
} from "@/lib/api";
import { PayHeroUsagePanel } from "@/components/billing/PayHeroUsagePanel";
import { getToken } from "@/lib/auth";
import { confirmDialog } from "@/lib/confirmDialog";
import { WaGlyph, WhatsAppIntegrationControls } from "@/components/whatsapp/WhatsAppIntegrationTile";
import { SOCIAL_PLATFORMS } from "@/components/ZernioSocialPanel";
import { zernioApi } from "@/lib/api";
import { useZernioAccounts } from "@/contexts/ZernioAccountsContext";
import { Plug, Mail, Calendar, CheckCircle, CheckCircle2, Loader2, AlertCircle, X, ExternalLink } from "lucide-react";

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

function FlutterwaveGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M4 6.5h16v2.2H4V6.5zm0 4.4h10.8v2.2H4v-2.2zm0 4.4h7.2v2.2H4v-2.2zM18.2 15.3l3.8 2.5-3.8 2.5v-5z" />
    </svg>
  );
}

const FLW_CURRENCY_COUNTRY: Record<string, string> = {
  NGN: "NG",
  KES: "KE",
  GHS: "GH",
  ZAR: "ZA",
  USD: "US",
  EUR: "FR",
  GBP: "GB",
  XAF: "CM",
  XOF: "SN",
  TZS: "TZ",
  UGX: "UG",
  ZMW: "ZM",
};

/** Default Connect country per currency (must be in backend STRIPE_CONNECT_COUNTRIES). */
const STRIPE_CURRENCY_COUNTRY: Record<string, string> = {
  USD: "US",
  EUR: "IE",
  GBP: "GB",
  CAD: "CA",
  AUD: "AU",
  NZD: "NZ",
  CHF: "CH",
  SEK: "SE",
  NOK: "NO",
  DKK: "DK",
  PLN: "PL",
  CZK: "CZ",
  HUF: "HU",
  RON: "RO",
  BGN: "BG",
  MXN: "MX",
  BRL: "BR",
  SGD: "SG",
  HKD: "HK",
  JPY: "JP",
  INR: "IN",
  MYR: "MY",
  THB: "TH",
  ZAR: "ZA",
};

const regionDisplay =
  typeof Intl !== "undefined" ? new Intl.DisplayNames(["en"], { type: "region" }) : null;

function countryLabel(code: string | undefined): string {
  if (!code) return "";
  try {
    return regionDisplay?.of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
}

function payoutBankLabel(code: string | undefined): string {
  const c = String(code ?? "").trim();
  if (!c || /^\d+$/.test(c)) return "Bank transfer";
  return c;
}

function displayEmail(email: string | undefined | null, maxLocal = 12): string {
  const e = String(email ?? "").trim();
  if (!e) return "—";
  const at = e.indexOf("@");
  if (at <= 0) {
    return e.length > 22 ? `${e.slice(0, 19)}…` : e;
  }
  const local = e.slice(0, at);
  const domain = e.slice(at);
  if (local.length <= maxLocal) return e;
  return `${local.slice(0, maxLocal)}…${domain}`;
}

function IntegrationEmailValue({ email }: { email?: string | null }) {
  const full = String(email ?? "").trim();
  if (!full) return <>—</>;
  const short = displayEmail(full);
  return (
    <span className="inline-block max-w-[9.5rem] truncate align-bottom" title={full}>
      {short}
    </span>
  );
}

function maskAccountEnding(value: string | undefined | null, visible = 4): string {
  const raw = String(value ?? "").trim();
  if (!raw) return "—";
  const digits = raw.replace(/\D/g, "");
  if (digits.length >= visible) return `•••• ${digits.slice(-visible)}`;
  return raw.length > visible ? `•••• ${raw.slice(-visible)}` : raw;
}

function IntegrationStatusPill({
  label,
  tone = "success",
}: {
  label: string;
  tone?: "success" | "warning" | "info";
}) {
  const styles =
    tone === "success"
      ? "border-emerald-200/80 bg-emerald-50 text-emerald-800"
      : tone === "warning"
        ? "border-amber-200/80 bg-amber-50 text-amber-800"
        : "border-sky-200/80 bg-sky-50 text-sky-800";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide ${styles}`}
    >
      <CheckCircle size={11} className="shrink-0" />
      {label}
    </span>
  );
}

function IntegrationDetailCard({ children }: { children: ReactNode }) {
  return (
    <div className="space-y-1.5 rounded-lg border border-slate-200/90 bg-white px-3 py-2.5 text-[11px] shadow-sm">
      {children}
    </div>
  );
}

function IntegrationDetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-800">{value}</span>
    </div>
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

// ── Nango tile controls ───────────────────────────────────────────────────────

type NangoTileControlsProps = {
  connected: boolean | null;
  connectLabel: string;
  connectClass: string;
  onConnect: () => Promise<void>;
  onDisconnect: () => Promise<void>;
};

function NangoTileControls({ connected, connectLabel, connectClass, onConnect, onDisconnect }: NangoTileControlsProps) {
  if (connected === null) {
    return (
      <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
        <Loader2 size={11} className="animate-spin" /> Checking…
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
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50"
        >
          <X size={11} /> Disconnect
        </button>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={onConnect}
      className={`w-full rounded-lg px-2.5 py-1.5 text-center text-xs font-semibold text-white ${connectClass}`}
    >
      {connectLabel}
    </button>
  );
}

// ── Composio tile controls ────────────────────────────────────────────────────

type ComposioTileControlsProps = {
  connected: boolean | null;
  busy: boolean;
  connectLabel: string;
  connectClass: string;
  onConnect: () => void;
  onDisconnect: () => void;
};

function ComposioTileControls({ connected, busy, connectLabel, connectClass, onConnect, onDisconnect }: ComposioTileControlsProps) {
  if (connected === null) {
    return (
      <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
        <Loader2 size={11} className="animate-spin" /> Checking…
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

function PaystackStatus({ connection, onChanged }: { connection?: PaystackConnection; onChanged: () => void }) {
  const [setup, setSetup] = useState<{
    platform_available: boolean;
    currencies: string[];
    default_currency: string;
    payout_types?: Array<"bank" | "mobile_money">;
    mobile_money_currencies?: string[];
  } | null>(null);
  const [setupLoading, setSetupLoading] = useState(false);
  const [currency, setCurrency] = useState("NGN");
  const [payoutType, setPayoutType] = useState<"bank" | "mobile_money">("bank");
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [payoutOptions, setPayoutOptions] = useState<Array<{ code: string; name: string }>>([]);
  const [selectedSettlement, setSelectedSettlement] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [subaccountName, setSubaccountName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setSetupLoading(true);
    paystackApi
      .setup()
      .then((s) => {
        setSetup(s);
        if (s?.default_currency) setCurrency(s.default_currency);
        setPayoutType("bank");
      })
      .catch(() => setSetup(null))
      .finally(() => setSetupLoading(false));
  }, []);

  const mobileMoneyCurrencies = useMemo(
    () =>
      setup?.mobile_money_currencies?.length
        ? setup.mobile_money_currencies
        : ["KES", "GHS", "XOF"],
    [setup?.mobile_money_currencies],
  );
  const mobileMoneySupported = mobileMoneyCurrencies.includes(currency);

  useEffect(() => {
    if (payoutType === "mobile_money" && !mobileMoneySupported) {
      setPayoutType("bank");
    }
  }, [currency, payoutType, mobileMoneySupported]);

  useEffect(() => {
    if (!setup?.platform_available) return;
    if (payoutType === "mobile_money" && !mobileMoneySupported) {
      setPayoutOptions([]);
      setSelectedSettlement("");
      setErr(
        `Mobile money subaccounts are not available for ${currency} on Paystack. Use Bank, or switch currency to ${mobileMoneyCurrencies.join(", ")}.`,
      );
      return;
    }
    setOptionsLoading(true);
    setErr(null);
    paystackApi
      .payoutOptions({ currency, payout_type: payoutType })
      .then((res) => {
        if (res.supported === false && res.hint) {
          setPayoutOptions([]);
          setSelectedSettlement("");
          setErr(res.hint);
          return;
        }
        const opts = res.options ?? [];
        setPayoutOptions(opts);
        if (opts.length) {
          setSelectedSettlement((prev) => (opts.some((o) => o.code === prev) ? prev : opts[0].code));
        } else {
          setSelectedSettlement("");
          setErr(
            `Paystack returned no ${payoutType === "mobile_money" ? "mobile money" : "bank"} options for ${currency}. Try another currency or check PAYSTACK_PLATFORM_SECRET_KEY.`,
          );
        }
      })
      .catch((e) => {
        setPayoutOptions([]);
        setSelectedSettlement("");
        setErr(e instanceof Error ? e.message : "Could not load Paystack payout options");
      })
      .finally(() => setOptionsLoading(false));
  }, [setup?.platform_available, currency, payoutType, mobileMoneySupported, mobileMoneyCurrencies]);

  async function handleConnect() {
    if (payoutType === "mobile_money" && !mobileMoneySupported) {
      setErr(
        `Mobile money is not available for ${currency}. Switch to Bank or use ${mobileMoneyCurrencies.join(", ")}.`,
      );
      return;
    }
    if (!selectedSettlement || !payoutOptions.length) {
      setErr("Choose a payout provider from the Paystack list before connecting.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await paystackApi.connect({
        currency,
        payout_type: payoutType,
        settlement_bank: selectedSettlement,
        account_number: accountNumber.trim(),
        business_name: subaccountName.trim(),
      });
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not connect");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    const ok = await confirmDialog({
      title: "Disconnect Paystack?",
      text: "Payments across Africa (NGN, KES, GHS and more) will no longer run through your Paystack account in this CRM. Checkout links and payment webhooks will stop until you connect again.",
      confirmText: "Yes, disconnect",
      cancelText: "Keep connected",
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await paystackApi.disconnect();
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not disconnect");
    } finally {
      setBusy(false);
    }
  }

  const platformAvailable = Boolean(setup?.platform_available || connection?.platform_available);
  const canSubmitPlatform =
    Boolean(selectedSettlement) &&
    Boolean(accountNumber.trim()) &&
    Boolean(subaccountName.trim()) &&
    payoutOptions.length > 0 &&
    !optionsLoading &&
    (payoutType !== "mobile_money" || mobileMoneySupported);

  if (connection?.connected) {
    const payoutLabel =
      connection.payout_type === "mobile_money" ? "M-Pesa" : payoutBankLabel(connection.settlement_bank);
    return (
      <div className="space-y-2">
        <div className="space-y-1">
          <IntegrationStatusPill label="Connected" />
          <p className="text-[12px] font-semibold text-slate-900">
            {connection.business_name || connection.subaccount_name || "Paystack"}
          </p>
        </div>
        <IntegrationDetailCard>
          <IntegrationDetailRow label="Payout" value={payoutLabel} />
          <IntegrationDetailRow
            label={connection.payout_type === "mobile_money" ? "Phone" : "Account"}
            value={maskAccountEnding(connection.account_number)}
          />
          {connection.default_currency ? (
            <IntegrationDetailRow label="Currency" value={connection.default_currency} />
          ) : null}
        </IntegrationDetailCard>
        <button
          type="button"
          onClick={handleDisconnect}
          disabled={busy}
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
        >
          {busy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
        </button>
        {err && (
          <p className="flex items-center gap-1 text-[10px] text-red-600">
            <AlertCircle size={10} /> {err}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {platformAvailable ? (
        <>
          <p className="text-[10px] leading-snug text-slate-500">
            Create your Paystack subaccount for payouts in Zilo.
          </p>
          <label className="text-[9px] font-medium text-slate-500">Currency</label>
          <select
            value={currency}
            onChange={(e) => {
              const next = e.target.value;
              setCurrency(next);
              if (!mobileMoneyCurrencies.includes(next)) {
                setPayoutType("bank");
              }
            }}
            disabled={setupLoading || !setup?.currencies?.length}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#00C3F7] disabled:opacity-60"
          >
            {(setup?.currencies?.length ? setup.currencies : ["NGN", "KES", "GHS", "ZAR", "USD"]).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <label className="text-[9px] font-medium text-slate-500">Payout type</label>
          <select
            value={payoutType === "mobile_money" && !mobileMoneySupported ? "bank" : payoutType}
            onChange={(e) => setPayoutType(e.target.value as "bank" | "mobile_money")}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#00C3F7]"
          >
            <option value="bank">Bank</option>
            {mobileMoneySupported ? (
              <option value="mobile_money">Mobile Money</option>
            ) : null}
          </select>
          {!mobileMoneySupported && (
            <p className="text-[9px] leading-snug text-slate-400">
              Mobile money on Paystack is only for {mobileMoneyCurrencies.join(", ")}.
            </p>
          )}
          <label className="text-[9px] font-medium text-slate-500">
            {payoutType === "mobile_money" ? "Mobile money provider" : "Bank name"}
          </label>
          {optionsLoading ? (
            <p className="flex items-center gap-1 text-[10px] text-slate-400">
              <Loader2 size={10} className="animate-spin" /> Loading Paystack options…
            </p>
          ) : payoutOptions.length === 0 ? (
            <p className="text-[10px] text-amber-700">
              {err || "No payout options found for this currency/type."}
            </p>
          ) : (
            <select
              value={selectedSettlement}
              onChange={(e) => setSelectedSettlement(e.target.value)}
              className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#00C3F7]"
            >
              {payoutOptions.map((o) => (
                <option key={o.code} value={o.code}>
                  {o.name}
                </option>
              ))}
            </select>
          )}
          <label className="text-[9px] font-medium text-slate-500">Account number</label>
          <input
            value={accountNumber}
            onChange={(e) => setAccountNumber(e.target.value)}
            placeholder="Account number"
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#00C3F7]"
          />
          <label className="text-[9px] font-medium text-slate-500">Subaccount name</label>
          <input
            value={subaccountName}
            onChange={(e) => setSubaccountName(e.target.value)}
            placeholder="eg. Nairobi Branch"
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#00C3F7]"
          />
        </>
      ) : (
        <p className="text-[10px] leading-snug text-slate-500">
          Paystack is not enabled on this server yet. Ask your administrator to set{" "}
          <span className="font-mono text-[9px]">PAYSTACK_PLATFORM_SECRET_KEY</span>.
        </p>
      )}
      {platformAvailable ? (
      <button
        type="button"
        onClick={handleConnect}
        disabled={busy || !canSubmitPlatform}
        className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#00C3F7] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#00a8d6] disabled:opacity-50"
      >
        {busy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect
      </button>
      ) : null}
      {err && (
        <p className="flex items-center gap-1 text-[10px] text-red-600">
          <AlertCircle size={10} /> {err}
        </p>
      )}
    </div>
  );
}

// ── Flutterwave (platform subaccount) ─────────────────────────────────────────

function FlutterwaveStatus({ connection, onChanged }: { connection?: FlutterwaveConnection; onChanged: () => void }) {
  const [setup, setSetup] = useState<{
    platform_available: boolean;
    currencies: string[];
    default_currency: string;
    merchant_split_percent?: number;
  } | null>(null);
  const [setupLoading, setSetupLoading] = useState(false);
  const [currency, setCurrency] = useState("NGN");
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [payoutOptions, setPayoutOptions] = useState<Array<{ code: string; name: string }>>([]);
  const [selectedBank, setSelectedBank] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessEmail, setBusinessEmail] = useState("");
  const [businessPhone, setBusinessPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const country = FLW_CURRENCY_COUNTRY[currency] || "";

  useEffect(() => {
    setSetupLoading(true);
    flutterwaveApi
      .setup()
      .then((s) => {
        setSetup(s);
        if (s?.default_currency) setCurrency(s.default_currency);
      })
      .catch(() => setSetup(null))
      .finally(() => setSetupLoading(false));
  }, []);

  useEffect(() => {
    if (!setup?.platform_available || !country) return;
    setOptionsLoading(true);
    setErr(null);
    flutterwaveApi
      .payoutOptions({ currency })
      .then((res) => {
        const opts = res.options ?? [];
        setPayoutOptions(opts);
        if (opts.length) {
          setSelectedBank((prev) => (opts.some((o) => o.code === prev) ? prev : opts[0].code));
        } else {
          setSelectedBank("");
          setErr(`No banks returned for ${currency}.`);
        }
      })
      .catch((e) => {
        setPayoutOptions([]);
        setSelectedBank("");
        setErr(e instanceof Error ? e.message : "Could not load banks");
      })
      .finally(() => setOptionsLoading(false));
  }, [setup?.platform_available, currency, country]);

  async function handleConnect() {
    if (!selectedBank || !payoutOptions.length) {
      setErr("Choose a bank before connecting.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await flutterwaveApi.connect({
        currency,
        country,
        account_bank: selectedBank,
        account_number: accountNumber.trim(),
        business_name: businessName.trim(),
        business_email: businessEmail.trim(),
        business_contact: businessPhone.trim(),
      });
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not connect");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    const ok = await confirmDialog({
      title: "Disconnect Flutterwave?",
      text: "Card and bank checkout links for this workspace will stop until you connect again.",
      confirmText: "Yes, disconnect",
      cancelText: "Keep connected",
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await flutterwaveApi.disconnect();
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not disconnect");
    } finally {
      setBusy(false);
    }
  }

  const platformAvailable = Boolean(setup?.platform_available || connection?.platform_available);
  const setupUnreachable = !setupLoading && setup === null && !connection?.platform_available;
  const keysMissingOnServer = !setupLoading && setup && !setup.platform_available && !connection?.platform_available;
  const canSubmit =
    Boolean(selectedBank) &&
    Boolean(accountNumber.trim()) &&
    Boolean(businessName.trim()) &&
    Boolean(businessEmail.trim()) &&
    Boolean(businessPhone.trim()) &&
    payoutOptions.length > 0 &&
    !optionsLoading;

  if (connection?.connected) {
    return (
      <div className="space-y-2">
        <div className="space-y-1">
          <IntegrationStatusPill label="Connected" />
          <p className="text-[12px] font-semibold text-slate-900">{connection.business_name || "Flutterwave"}</p>
        </div>
        <IntegrationDetailCard>
          <IntegrationDetailRow label="Payout" value={payoutBankLabel(connection.settlement_bank)} />
          <IntegrationDetailRow label="Account" value={maskAccountEnding(connection.account_number)} />
          {connection.default_currency ? (
            <IntegrationDetailRow label="Currency" value={connection.default_currency} />
          ) : null}
          {connection.business_email ? (
            <IntegrationDetailRow label="Contact" value={<IntegrationEmailValue email={connection.business_email} />} />
          ) : null}
        </IntegrationDetailCard>
        <button
          type="button"
          onClick={handleDisconnect}
          disabled={busy}
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
        >
          {busy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
        </button>
        {err && (
          <p className="flex items-center gap-1 text-[10px] text-red-600">
            <AlertCircle size={10} /> {err}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {platformAvailable ? (
        <>
          <p className="text-[10px] leading-snug text-slate-500">
            Create a Flutterwave subaccount for payouts. Platform fee is configured on the server (
            {setup?.merchant_split_percent ?? 90}% to you by default).
          </p>
          <label className="text-[9px] font-medium text-slate-500">Currency</label>
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            disabled={setupLoading || !setup?.currencies?.length}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#F5A623] disabled:opacity-60"
          >
            {(setup?.currencies?.length ? setup.currencies : ["NGN", "KES", "GHS"]).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          {!country && (
            <p className="text-[10px] text-amber-700">No country mapping for {currency}.</p>
          )}
          <label className="text-[9px] font-medium text-slate-500">Bank</label>
          {optionsLoading ? (
            <p className="flex items-center gap-1 text-[10px] text-slate-400">
              <Loader2 size={10} className="animate-spin" /> Loading banks…
            </p>
          ) : (
            <select
              value={selectedBank}
              onChange={(e) => setSelectedBank(e.target.value)}
              className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#F5A623]"
            >
              {payoutOptions.map((o) => (
                <option key={o.code} value={o.code}>
                  {o.name}
                </option>
              ))}
            </select>
          )}
          <label className="text-[9px] font-medium text-slate-500">Account number</label>
          <input
            value={accountNumber}
            onChange={(e) => setAccountNumber(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#F5A623]"
          />
          <label className="text-[9px] font-medium text-slate-500">Business name</label>
          <input
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#F5A623]"
          />
          <label className="text-[9px] font-medium text-slate-500">Business email</label>
          <input
            type="email"
            value={businessEmail}
            onChange={(e) => setBusinessEmail(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#F5A623]"
          />
          <label className="text-[9px] font-medium text-slate-500">Business phone</label>
          <input
            value={businessPhone}
            onChange={(e) => setBusinessPhone(e.target.value)}
            placeholder="+234…"
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#F5A623]"
          />
        </>
      ) : setupLoading ? (
        <p className="flex items-center gap-1 text-[10px] text-slate-400">
          <Loader2 size={10} className="animate-spin" /> Checking Flutterwave on server…
        </p>
      ) : setupUnreachable ? (
        <p className="text-[10px] leading-snug text-amber-800">
          Could not reach the API for Flutterwave setup. Start the backend on port 8000 and restart it after editing{" "}
          <span className="font-mono text-[9px]">backend/.env</span> (Next uses{" "}
          <span className="font-mono text-[9px]">BACKEND_INTERNAL_URL</span>).
        </p>
      ) : keysMissingOnServer ? (
        <p className="text-[10px] leading-snug text-slate-500">
          Flutterwave is not enabled on this server. Set{" "}
          <span className="font-mono text-[9px]">FLUTTERWAVE_PLATFORM_SECRET_KEY</span> in{" "}
          <span className="font-mono text-[9px]">backend/.env</span> and restart the API.{" "}
          <span className="font-mono text-[9px]">FLUTTERWAVE_SECRET_HASH</span> is for webhooks only.
        </p>
      ) : (
        <p className="text-[10px] leading-snug text-slate-500">
          Flutterwave setup could not be loaded. Refresh the page or check the backend logs.
        </p>
      )}
      {platformAvailable ? (
        <button
          type="button"
          onClick={handleConnect}
          disabled={busy || !canSubmit}
          className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#F5A623] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#e09510] disabled:opacity-50"
        >
          {busy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect
        </button>
      ) : null}
      {err && (
        <p className="flex items-center gap-1 text-[10px] text-red-600">
          <AlertCircle size={10} /> {err}
        </p>
      )}
    </div>
  );
}

// ── Stripe Connect (platform destination charges) ───────────────────────────

const STRIPE_PLATFORM_PROFILE_URL =
  "https://dashboard.stripe.com/settings/connect/platform-profile";

function stripeConnectErrHint(message: string | null): {
  platformProfile: boolean;
  actionUrl: string;
  display: string;
} | null {
  if (!message) return null;
  const lower = message.toLowerCase();
  const platformProfile =
    lower.includes("platform profile") ||
    lower.includes("platform-profile") ||
    lower.includes("managing losses") ||
    lower.includes("stripe_platform_profile");
  const countryUnsupported =
    lower.includes("card_payments") ||
    lower.includes("stripe_connect_country") ||
    lower.includes("not supported for stripe");
  if (!platformProfile && !countryUnsupported) return null;
  if (countryUnsupported) {
    return {
      platformProfile: false,
      actionUrl: "https://stripe.com/global",
      display: message.replace(/^\d{3}:\s*/, ""),
    };
  }
  return {
    platformProfile: true,
    actionUrl: STRIPE_PLATFORM_PROFILE_URL,
    display: message.replace(/^\d{3}:\s*/, ""),
  };
}

function stripeIsLinked(connection?: StripeConnection): boolean {
  return Boolean(
    connection?.connected ||
      connection?.checkout_ready ||
      connection?.charges_enabled ||
      (connection?.account_id && connection.account_id.startsWith("acct_")),
  );
}

function stripeStatusLabel(status: StripeLifecycleStatus | undefined, connection?: StripeConnection): string {
  const s =
    status ??
    (connection?.checkout_ready || connection?.charges_enabled
      ? "ready"
      : connection?.connected
        ? connection.details_submitted && !connection.charges_enabled
          ? "verification_pending"
          : "onboarding"
        : "not_connected");
  switch (s) {
    case "ready":
      return "Connected — checkout enabled";
    case "verification_pending":
      return "Verification in progress";
    case "onboarding":
      return "Onboarding in progress";
    default:
      return "Not connected";
  }
}

function StripeConnectStatus({
  connection,
  connectionHydrated = false,
  onChanged,
}: {
  connection?: StripeConnection;
  connectionHydrated?: boolean;
  onChanged: () => void;
}) {
  const [setup, setSetup] = useState<{
    platform_available: boolean;
    currencies: string[];
    countries: string[];
    default_currency: string;
    default_country?: string;
    connect_note?: string;
    merchant_transfer_percent?: number;
    platform_fee_percent?: number;
  } | null>(null);
  const [setupLoading, setSetupLoading] = useState(false);
  const [currency, setCurrency] = useState("USD");
  const [country, setCountry] = useState("US");
  const [businessEmail, setBusinessEmail] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const stripeErrHint = stripeConnectErrHint(err);

  async function handleRefreshStatus() {
    setSyncing(true);
    setErr(null);
    try {
      onChanged();
    } finally {
      setSyncing(false);
    }
  }

  function StripeConnectErrorBanner() {
    if (!err) return null;
    if (stripeErrHint && !stripeErrHint.platformProfile) {
      return (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[10px] text-amber-900">
          <p className="font-medium">Country not supported for Stripe card checkout</p>
          <p className="mt-0.5 leading-snug">{stripeErrHint.display}</p>
          <p className="mt-0.5 leading-snug">
            Use a supported country in the dropdown, or connect <strong>Paystack</strong> / <strong>PayHero</strong> for
            Kenya and similar markets.
          </p>
          <a
            href={stripeErrHint.actionUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 inline-flex items-center gap-0.5 font-semibold text-[#635BFF] underline"
          >
            Stripe global availability <ExternalLink size={9} />
          </a>
        </div>
      );
    }
    if (stripeErrHint?.platformProfile) {
      return (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[10px] text-amber-900">
          <p className="font-medium">Platform Stripe setup required</p>
          <p className="mt-0.5 leading-snug">
            Merchant onboarding is blocked until the CRM operator completes Connect platform profile on the
            Stripe account that owns <span className="font-mono text-[9px]">STRIPE_PLATFORM_SECRET_KEY</span>{" "}
            (loss liability for connected accounts). This is not fixed by changing business name or country here.
          </p>
          <a
            href={stripeErrHint.actionUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 inline-flex items-center gap-0.5 font-semibold text-[#635BFF] underline"
          >
            Open Stripe Connect platform profile <ExternalLink size={9} />
          </a>
        </div>
      );
    }
    return (
      <p className="flex items-center gap-1 text-[10px] text-red-600">
        <AlertCircle size={10} /> {err}
      </p>
    );
  }

  useEffect(() => {
    setSetupLoading(true);
    stripeConnectApi
      .setup()
      .then((s) => {
        setSetup(s);
        if (s?.default_currency) setCurrency(s.default_currency);
        if (s?.default_country && s.countries?.includes(s.default_country)) {
          setCountry(s.default_country);
        }
      })
      .catch(() => setSetup(null))
      .finally(() => setSetupLoading(false));
  }, []);

  useEffect(() => {
    const allowed = setup?.countries ?? [];
    const mapped = STRIPE_CURRENCY_COUNTRY[currency];
    if (mapped && allowed.includes(mapped)) {
      setCountry(mapped);
    } else if (allowed.length && !allowed.includes(country)) {
      setCountry(allowed[0]);
    }
  }, [currency, setup?.countries]);

  async function openOnboarding(getUrl: () => Promise<string>) {
    const url = await getUrl();
    if (!url) throw new Error("No onboarding URL returned");
    const popup = window.open(url, "stripe-connect", "width=980,height=760,noopener,noreferrer");
    if (!popup) {
      window.location.href = url;
      return;
    }
    const poll = window.setInterval(() => {
      void onChanged();
      if (popup.closed) {
        window.clearInterval(poll);
        setTimeout(() => void onChanged(), 1500);
      }
    }, 3000);
  }

  async function handleConnect() {
    setBusy(true);
    setErr(null);
    try {
      const res = await stripeConnectApi.connect({
        email: businessEmail.trim(),
        business_name: businessName.trim(),
        currency,
        country,
      });
      onChanged();
      if (res.onboarding_url) {
        await openOnboarding(async () => res.onboarding_url);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not connect");
    } finally {
      setBusy(false);
    }
  }

  async function handleContinueOnboarding() {
    setBusy(true);
    setErr(null);
    try {
      await openOnboarding(async () => {
        const res = await stripeConnectApi.accountLink();
        return res.onboarding_url;
      });
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not open Stripe onboarding");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    const ok = await confirmDialog({
      title: "Disconnect Stripe Connect?",
      text: "Stripe checkout for orders will stop until you connect again. Your Stripe account is not deleted.",
      confirmText: "Yes, disconnect",
      cancelText: "Keep connected",
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await stripeConnectApi.disconnect();
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not disconnect");
    } finally {
      setBusy(false);
    }
  }

  const linked = stripeIsLinked(connection);
  const platformAvailable = Boolean(setup?.platform_available || connection?.platform_available || linked);
  const setupUnreachable =
    connectionHydrated &&
    !linked &&
    !setupLoading &&
    setup === null &&
    !connection?.platform_available;
  const keysMissingOnServer =
    !linked && !setupLoading && setup && !setup.platform_available && !connection?.platform_available;
  const canSubmit =
    Boolean(businessEmail.trim()) &&
    Boolean(businessName.trim()) &&
    Boolean(country) &&
    Boolean(currency);

  if (linked && connection) {
    const lifecycle: StripeLifecycleStatus =
      connection.status ??
      (connection.checkout_ready || connection.charges_enabled
        ? "ready"
        : connection.details_submitted && !connection.charges_enabled
          ? "verification_pending"
          : "onboarding");
    const ready = lifecycle === "ready";
    const pendingVerify = lifecycle === "verification_pending";
    const statusTone = ready ? "success" : pendingVerify ? "info" : "warning";
    const statusPill = ready ? "Active" : pendingVerify ? "Under review" : "Setup";
    const settlement =
      connection.default_currency || connection.country
        ? [
            connection.default_currency,
            connection.country ? countryLabel(connection.country) : null,
          ]
            .filter(Boolean)
            .join(" · ")
        : null;
    return (
      <div className="space-y-2">
        <div className="space-y-1">
          <IntegrationStatusPill label={statusPill} tone={statusTone} />
          <p className="text-[12px] font-semibold text-slate-900">
            {connection.business_name || "Stripe"}
          </p>
        </div>
        <p className="text-[10px] leading-snug text-slate-600">
          {ready
            ? "Accepts card payments on orders."
            : pendingVerify
              ? "Stripe is reviewing your account."
              : "Complete onboarding to accept payments."}
          {settlement ? <span className="text-slate-500"> · {settlement}</span> : null}
        </p>
        {connection.connect_email ? (
          <p className="text-[10px] text-slate-500">
            <IntegrationEmailValue email={connection.connect_email} />
          </p>
        ) : null}
        {!ready && (
          <button
            type="button"
            onClick={() => void handleContinueOnboarding()}
            disabled={busy}
            className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#635BFF] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#4f46e5] disabled:opacity-50"
          >
            {busy ? <Loader2 size={11} className="animate-spin" /> : <ExternalLink size={11} />}
            {pendingVerify ? "Open Stripe" : "Continue setup"}
          </button>
        )}
        {!ready ? (
          <button
            type="button"
            onClick={() => void handleRefreshStatus()}
            disabled={syncing}
            className="flex w-full items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {syncing ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Refresh status
          </button>
        ) : null}
        <button
          type="button"
          onClick={handleDisconnect}
          disabled={busy}
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-red-700 disabled:opacity-50"
        >
          {busy ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />} Disconnect
        </button>
        <StripeConnectErrorBanner />
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {platformAvailable ? (
        <>
          <p className="text-[10px] leading-snug text-slate-500">
            Express Connect — Stripe handles KYC, tax, and bank verification. Destination charges; merchant ~
            {setup?.merchant_transfer_percent ?? 90}% (platform fee ~{setup?.platform_fee_percent ?? 10}%).
            {setup?.connect_note ? (
              <span className="mt-0.5 block text-amber-800/90">{setup.connect_note}</span>
            ) : null}
          </p>
          <label className="text-[9px] font-medium text-slate-500">Currency</label>
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            disabled={setupLoading || !setup?.currencies?.length}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#635BFF] disabled:opacity-60"
          >
            {(setup?.currencies?.length ? setup.currencies : ["USD", "EUR", "GBP"]).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <label className="text-[9px] font-medium text-slate-500">Country</label>
          <select
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#635BFF]"
          >
            {(setup?.countries?.length ? setup.countries : ["US", "GB", "IE"]).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <label className="text-[9px] font-medium text-slate-500">Business email</label>
          <input
            type="email"
            value={businessEmail}
            onChange={(e) => setBusinessEmail(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#635BFF]"
          />
          <label className="text-[9px] font-medium text-slate-500">Business name</label>
          <input
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] outline-none focus:border-[#635BFF]"
          />
        </>
      ) : !connectionHydrated || setupLoading ? (
        <p className="flex items-center gap-1 text-[10px] text-slate-400">
          <Loader2 size={10} className="animate-spin" /> Loading…
        </p>
      ) : setupUnreachable ? (
        <p className="text-[10px] leading-snug text-slate-500">
          Stripe setup is temporarily unavailable. Ensure the API server is running, then click Connect Stripe.
        </p>
      ) : keysMissingOnServer ? (
        <p className="text-[10px] leading-snug text-slate-500">
          Stripe Connect is not enabled. Set{" "}
          <span className="font-mono text-[9px]">STRIPE_PLATFORM_SECRET_KEY</span> and webhook secrets in{" "}
          <span className="font-mono text-[9px]">backend/.env</span>.
        </p>
      ) : (
        <p className="text-[10px] leading-snug text-slate-500">Stripe setup could not be loaded.</p>
      )}
      {platformAvailable ? (
        <button
          type="button"
          onClick={() => void handleConnect()}
          disabled={busy || !canSubmit}
          className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#635BFF] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#4f46e5] disabled:opacity-50"
        >
          {busy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect Stripe
        </button>
      ) : null}
      <StripeConnectErrorBanner />
    </div>
  );
}

// ── PayHero (Basic Auth + Channel selector) ───────────────────────────────────

function PayHeroStatus({ connection, onChanged }: { connection?: PayheroConnection; onChanged: () => void }) {
  const [apiToken, setApiToken] = useState("");
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
    if (!apiToken.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await payheroApi.connect({ api_token: apiToken.trim() });
      setApiToken("");
      await onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not connect");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    const ok = await confirmDialog({
      title: "Disconnect PayHero?",
      text: "M-Pesa STK push and automatic payment confirmation will stop for this workspace. Your API credentials and selected payment channel will be removed from the CRM.",
      confirmText: "Yes, disconnect",
      cancelText: "Keep connected",
    });
    if (!ok) return;
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
        <div className="space-y-1">
          <IntegrationStatusPill label="Connected" />
          <p className="text-[12px] font-semibold text-slate-900">{connection.username || "PayHero"}</p>
        </div>

        {/* Channel selector */}
        <div className="space-y-1">
          <p className="text-[10px] font-medium text-slate-600">M-Pesa channel</p>
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
                {channels.map((ch) => (
                  <option key={ch.id} value={String(ch.id)}>
                    {ch.name}
                    {ch.paybill ? ` · Paybill ${ch.paybill}` : ch.short_code ? ` · Till ${ch.short_code}` : ""}
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

        <PayHeroUsagePanel connected />

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
        In{" "}
        <a href="https://app.payhero.co.ke/" target="_blank" rel="noreferrer"
          className="font-medium text-[#1DB954] hover:underline">
          PayHero Dashboard
        </a>
        {" "}→ <strong>API Keys</strong> → Create key → copy the <strong>Basic Authorization token</strong> (not your login password).
      </p>
      <input
        type="password"
        value={apiToken}
        onChange={(e) => setApiToken(e.target.value)}
        placeholder="Paste Basic Auth token"
        autoComplete="off"
        className="w-full rounded-md border border-slate-200 px-2 py-1 text-[10px] font-mono outline-none focus:border-[#1DB954]"
      />
      <button
        type="button"
        onClick={() => void handleConnect()}
        disabled={busy || !apiToken.trim()}
        className="flex w-full items-center justify-center gap-1 rounded-lg bg-[#1DB954] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[#17a34a] disabled:opacity-50"
      >
        {busy ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />} Connect
      </button>
      {err && <p className="flex items-center gap-1 text-[10px] text-red-600"><AlertCircle size={10} /> {err}</p>}
    </div>
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

const NANGO_IDS = {
  slack: NANGO_INTEGRATION_IDS.slack,
  email: NANGO_INTEGRATION_IDS.email,
  calendar: NANGO_INTEGRATION_IDS.calendar,
  shopify: NANGO_INTEGRATION_IDS.shopify,
  microsoft: NANGO_INTEGRATION_IDS.microsoft,
  stripe: NANGO_INTEGRATION_IDS.stripe,
  klaviyo: NANGO_INTEGRATION_IDS.klaviyo,
  mailchimp: NANGO_INTEGRATION_IDS.mailchimp,
  brevo: NANGO_INTEGRATION_IDS.brevo,
  google_sheets: NANGO_INTEGRATION_IDS.google_sheets,
  notion: NANGO_INTEGRATION_IDS.notion,
} as const;

type NangoKey = keyof typeof NANGO_IDS;

interface ZernioAccount { id: string; platform: string; name?: string; username?: string; }
interface FacebookHeadlessPage { id: string; name?: string; username?: string; category?: string; }

function toFacebookHeadlessPage(input: Record<string, unknown>): FacebookHeadlessPage | null {
  const rawId = input.id;
  if (typeof rawId !== "string" || !rawId.trim()) return null;
  return {
    id: rawId,
    name: typeof input.name === "string" ? input.name : undefined,
    username: typeof input.username === "string" ? input.username : undefined,
    category: typeof input.category === "string" ? input.category : undefined,
  };
}

function IntegrationsPageInner() {
  const [tgConn, setTgConn] = useState<TelegramConnection>({ connected: false });
  const [psConn, setPsConn] = useState<PaystackConnection>({ connected: false });
  const [fwConn, setFwConn] = useState<FlutterwaveConnection>({ connected: false });
  const [stConn, setStConn] = useState<StripeConnection>({ connected: false });
  const [stConnHydrated, setStConnHydrated] = useState(false);
  const [phConn, setPhConn] = useState<PayheroConnection>({ connected: false });
  const { accounts: rawZernioAccounts, apiConnected: zernioApiOk, refresh: refreshZernioCtx, connect: zernioCtxConnect, disconnect: zernioCtxDisconnect } = useZernioAccounts();
  const zernioAccounts = rawZernioAccounts as ZernioAccount[];
  const [zernioConnecting, setZernioConnecting] = useState<string | null>(null);
  const [zernioDisconnecting, setZernioDisconnecting] = useState<string | null>(null);
  const [fbHeadlessPages, setFbHeadlessPages] = useState<FacebookHeadlessPage[]>([]);
  const [fbHeadlessParams, setFbHeadlessParams] = useState<{
    tempToken: string;
    connectToken: string;
    userProfile: Record<string, unknown>;
  } | null>(null);
  const [fbLoadingPages, setFbLoadingPages] = useState(false);
  const [fbCompletingPageId, setFbCompletingPageId] = useState<string | null>(null);

  const refreshZernio = useCallback(async () => {
    await refreshZernioCtx();
  }, [refreshZernioCtx]);

  async function zernioConnect(platformId: string) {
    setZernioConnecting(platformId);
    try {
      const redirectUrl = `${window.location.origin}/dashboard/integrations?connected=${encodeURIComponent(platformId)}`;
      const isHeadlessFacebook = platformId === "facebook";
      const { authUrl } = await zernioCtxConnect(platformId, redirectUrl, isHeadlessFacebook);
      if (authUrl) {
        if (isHeadlessFacebook) {
          // Headless flow must remain in same tab to receive callback params here.
          window.location.href = authUrl;
          return;
        }
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

  async function completeFacebookHeadlessConnect(page: FacebookHeadlessPage) {
    if (!fbHeadlessParams) return;
    setFbCompletingPageId(page.id);
    try {
      await zernioApi.facebookHeadlessComplete({
        temp_token: fbHeadlessParams.tempToken,
        connect_token: fbHeadlessParams.connectToken,
        page_id: page.id,
        user_profile: fbHeadlessParams.userProfile,
        redirect_url: `${window.location.origin}/dashboard/integrations?connected=facebook`,
      });
      setBanner({ type: "success", msg: `${page.name || "Facebook page"} connected successfully.` });
      setFbHeadlessPages([]);
      setFbHeadlessParams(null);
      await refreshZernio();
      window.history.replaceState({}, "", window.location.pathname);
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to complete Facebook connection." });
    } finally {
      setFbCompletingPageId(null);
    }
  }
  const [nangoStatus, setNangoStatus] = useState<Record<NangoKey, boolean | null>>({
    slack: null, email: null, calendar: null, shopify: null,
    microsoft: null, stripe: null, klaviyo: null, mailchimp: null, brevo: null,
    google_sheets: null, notion: null,
  });
  const [composioStatus, setComposioStatus] = useState<Record<string, boolean | null>>({
    gmail: null,
    googlecalendar: null,
    outlook: null,
    // Productivity
    slack: null,
    googlesheets: null,
    notion: null,
    // E-commerce / Payments
    shopify: null,
    stripe: null,
    // Marketing
    klaviyo: null,
    mailchimp: null,
    brevo: null,
    // Advertising
    googleads: null,
    // Analytics
    googleanalytics: null,
    googlesearchconsole: null,
  });
  const [composioBusy, setComposioBusy] = useState<string | null>(null);
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

  const refreshFw = useCallback(() => {
    flutterwaveApi.connection().then(setFwConn).catch(() => {});
  }, []);

  const refreshSt = useCallback(() => {
    return stripeConnectApi
      .connection()
      .then((c) => {
        setStConn(c);
        setStConnHydrated(true);
      })
      .catch(() => {
        setStConn({ connected: false, status: "not_connected" });
        setStConnHydrated(true);
      });
  }, []);

  const refreshPh = useCallback(async () => {
    try {
      const c = await payheroApi.connection();
      setPhConn(c);
    } catch {
      setPhConn({ connected: false });
    }
  }, []);

  const refreshNango = useCallback(async () => {
    const token = getToken();
    const _nangoFalse = { slack: false, email: false, calendar: false, shopify: false, microsoft: false, stripe: false, klaviyo: false, mailchimp: false, brevo: false, google_sheets: false, notion: false };
    if (!token) { setNangoStatus(_nangoFalse); return; }
    const ids = Object.values(NANGO_IDS).join(",");
    try {
      const res = await fetch(`/api/nango/connections?integrations=${ids}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { setNangoStatus(_nangoFalse); return; }
      const data = (await res.json()) as { connected: Record<string, boolean> };
      setNangoStatus({
        slack: data.connected[NANGO_IDS.slack] ?? false,
        email: data.connected[NANGO_IDS.email] ?? false,
        calendar: data.connected[NANGO_IDS.calendar] ?? false,
        shopify: data.connected[NANGO_IDS.shopify] ?? false,
        microsoft: data.connected[NANGO_IDS.microsoft] ?? false,
        stripe: data.connected[NANGO_IDS.stripe] ?? false,
        klaviyo: data.connected[NANGO_IDS.klaviyo] ?? false,
        mailchimp: data.connected[NANGO_IDS.mailchimp] ?? false,
        brevo: data.connected[NANGO_IDS.brevo] ?? false,
        google_sheets: data.connected[NANGO_IDS.google_sheets] ?? false,
        notion: data.connected[NANGO_IDS.notion] ?? false,
      });
    } catch {
      setNangoStatus({ slack: false, email: false, calendar: false, shopify: false, microsoft: false, stripe: false, klaviyo: false, mailchimp: false, brevo: false, google_sheets: false, notion: false });
    }
  }, []);

  const refreshComposio = useCallback(async () => {
    const token = getToken();
    const _allFalse: Record<string, boolean> = {
      gmail: false, googlecalendar: false, outlook: false,
      slack: false, googlesheets: false, notion: false,
      shopify: false, stripe: false,
      klaviyo: false, mailchimp: false, brevo: false,
      googleads: false,
      googleanalytics: false,
      googlesearchconsole: false,
    };
    if (!token) { setComposioStatus(_allFalse); return; }
    try {
      const res = await fetch("/api/composio/connections", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { setComposioStatus(_allFalse); return; }
      const data = (await res.json()) as { connected: Record<string, boolean> };
      setComposioStatus({
        gmail:          data.connected["gmail"]         ?? false,
        googlecalendar: data.connected["googlecalendar"] ?? false,
        outlook:        data.connected["outlook"]       ?? false,
        slack:          data.connected["slack"]         ?? false,
        googlesheets:   data.connected["googlesheets"]  ?? false,
        notion:         data.connected["notion"]        ?? false,
        shopify:        data.connected["shopify"]       ?? false,
        stripe:         data.connected["stripe"]        ?? false,
        klaviyo:        data.connected["klaviyo"]       ?? false,
        mailchimp:      data.connected["mailchimp"]     ?? false,
        brevo:          data.connected["brevo"]         ?? false,
        googleads:          data.connected["googleads"]          ?? false,
        googleanalytics:     data.connected["googleanalytics"]     ?? false,
        googlesearchconsole: data.connected["googlesearchconsole"] ?? false,
      });
    } catch {
      setComposioStatus(_allFalse);
    }
  }, []);

  async function composioConnect(toolkit: string, silent = false, extraBody: Record<string, string> = {}) {
    setComposioBusy(toolkit);
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
        return;
      }
      const data = (await res.json()) as { redirect_url?: string };
      if (!data.redirect_url) {
        if (!silent) setBanner({ type: "error", msg: "No redirect URL returned from Composio." });
        return;
      }
      const popup = window.open(data.redirect_url, "composio-connect", "width=980,height=760,noopener,noreferrer");
      if (!popup) { window.location.href = data.redirect_url; return; }

      if (!silent) setBanner({ type: "success", msg: "Finish connecting in the popup, then return here." });

      await new Promise<void>((resolve) => {
        const poll = window.setInterval(async () => {
          void refreshComposio();
          if (popup.closed) {
            window.clearInterval(poll);
            await new Promise(r => setTimeout(r, 1200));
            await refreshComposio();
            resolve();
          }
        }, 3000);
      });

      // Auto-link Calendar when Gmail connects (same Google account)
      if (toolkit === "gmail") {
        const freshStatus = await fetch("/api/composio/connections", {
          headers: { Authorization: `Bearer ${token ?? ""}` },
        }).then(r => r.json()).catch(() => ({ connected: {} })) as { connected: Record<string, boolean> };

        if (freshStatus.connected?.gmail && !freshStatus.connected?.googlecalendar) {
          setBanner({ type: "success", msg: "Gmail connected! Now linking Google Calendar…" });
          await composioConnect("googlecalendar", false);
        }
      }
    } catch (e) {
      if (!silent) setBanner({ type: "error", msg: e instanceof Error ? e.message : "Failed to connect." });
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
      void refreshComposio();
    } catch (e) {
      setBanner({ type: "error", msg: e instanceof Error ? e.message : `Failed to disconnect ${label}.` });
    } finally {
      setComposioBusy(null);
    }
  }

  useEffect(() => { refreshTg(); refreshPs(); refreshFw(); refreshSt(); refreshPh(); void refreshNango(); void refreshZernio(); void refreshComposio(); refreshSuppliers(); }, [refreshTg, refreshPs, refreshFw, refreshSt, refreshPh, refreshNango, refreshZernio, refreshComposio, refreshSuppliers]);

  const router = useRouter();

  useEffect(() => {
    const stripeParam = searchParams.get("stripe");
    if (stripeParam !== "return" && stripeParam !== "refresh") return;

    void (async () => {
      let linked: StripeConnection | null = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        if (attempt > 0) await new Promise((r) => setTimeout(r, 1200));
        try {
          linked = await stripeConnectApi.connection();
          setStConn(linked);
          if (linked.connected) break;
        } catch {
          linked = null;
        }
      }

      if (stripeParam === "return") {
        if (linked?.connected) {
          setBanner({
            type: "success",
            msg: linked.checkout_ready
              ? "Stripe Connect is ready — you can take card payments on orders."
              : "Returned from Stripe. Finish any remaining steps in Stripe, then click Refresh status.",
          });
        } else {
          setBanner({
            type: "error",
            msg:
              "Returned from Stripe, but this workspace is not linked. Keep the backend running, then click Connect Stripe here (same business email). Onboarding only counts when started from this Integrations page.",
          });
        }
      } else {
        setBanner({
          type: "error",
          msg: "Stripe onboarding link expired. Click Continue Stripe setup to open a fresh link.",
        });
      }
    })();

    const next = new URLSearchParams(searchParams.toString());
    next.delete("stripe");
    const q = next.toString();
    router.replace(q ? `/dashboard/integrations?${q}` : "/dashboard/integrations", { scroll: false });
  }, [searchParams, router]);

  useEffect(() => {
    const platform = searchParams.get("platform");
    const step = searchParams.get("step");
    const tempToken = searchParams.get("tempToken");
    const connectToken = searchParams.get("connect_token");
    const userProfileRaw = searchParams.get("userProfile");

    if (platform === "facebook" && step === "select_page" && tempToken && connectToken && userProfileRaw) {
      const parseUserProfile = () => {
        try {
          return JSON.parse(userProfileRaw) as Record<string, unknown>;
        } catch {
          return JSON.parse(decodeURIComponent(userProfileRaw)) as Record<string, unknown>;
        }
      };
      const userProfile = parseUserProfile();
      setFbHeadlessParams({ tempToken, connectToken, userProfile });
      setFbLoadingPages(true);
      zernioApi
        .facebookHeadlessPages({ temp_token: tempToken, connect_token: connectToken })
        .then((res) => {
          const pages = (res.pages || [])
            .map((p) => toFacebookHeadlessPage(p))
            .filter((p): p is FacebookHeadlessPage => p !== null);
          setFbHeadlessPages(pages);
          if (!pages.length) {
            setBanner({ type: "error", msg: "No Facebook pages were returned for this account." });
          } else {
            setBanner({ type: "success", msg: "Select a Facebook Page below to finish connecting." });
          }
        })
        .catch((e) => {
          setBanner({ type: "error", msg: e instanceof Error ? e.message : "Could not load Facebook pages." });
        })
        .finally(() => setFbLoadingPages(false));
      return;
    }

    const connected = searchParams.get("connected");
    const error = searchParams.get("error");
    if (connected) {
      // If this page loaded inside an OAuth popup, close it so the parent window
      // picks up the connection via its polling loop.
      if (typeof window !== "undefined" && window.opener && !window.opener.closed) {
        window.close();
        return;
      }
      setBanner({ type: "success", msg: `${connected.charAt(0).toUpperCase() + connected.slice(1)} connected!` });
      refreshTg(); void refreshNango(); void refreshZernio(); void refreshComposio();
      window.history.replaceState({}, "", window.location.pathname);
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
  }, [searchParams, refreshTg, refreshNango, refreshZernio]);

  async function nangoConnect(key: NangoKey) {
    await openNangoConnect([NANGO_IDS[key]], { onAfterConnect: refreshNango });
  }

  async function nangoDisconnect(key: NangoKey) {
    const label = key.charAt(0).toUpperCase() + key.slice(1);
    if (!confirm(`Disconnect ${label}?`)) return;
    const token = getToken();
    if (!token) return;
    const res = await fetch("/api/nango/connections", {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ integration_id: NANGO_IDS[key] }),
    });
    if (!res.ok) {
      const err = (await res.json().catch(() => ({} as { error?: string }))) as { error?: string };
      alert(err.error || "Failed to disconnect");
      return;
    }
    void refreshNango();
  }

  const FREE_BADGE: BadgeDef = { label: "Free", className: "bg-emerald-100 text-emerald-700" };

  return (
    <div className="mx-auto w-full max--4xl min-w-0 space-y-6 p-4 sm:p-6">

      {/* Header */}
      <div>
        <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-brand/15 text-brand-dark">
          <Plug size={18} />
        </div>
        <h1 className="text-xl font-bold text-slate-900">Integrations</h1>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 sm:text-sm">
          Connect your messaging channels, social media, e-commerce, payments, and marketing tools.
        </p>
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

      {fbHeadlessParams && (
        <section className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-3">
          <div className="mb-2">
            <h3 className="text-xs font-semibold text-blue-900">Finish Facebook Connection</h3>
            <p className="text-[11px] text-blue-800">Choose which Facebook Page to connect to your CRM.</p>
          </div>
          {fbLoadingPages ? (
            <div className="flex items-center gap-1.5 text-[11px] text-blue-800">
              <Loader2 size={12} className="animate-spin" /> Loading your pages...
            </div>
          ) : fbHeadlessPages.length ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {fbHeadlessPages.map((page) => (
                <button
                  key={page.id}
                  type="button"
                  onClick={() => void completeFacebookHeadlessConnect(page)}
                  disabled={fbCompletingPageId === page.id}
                  className="flex items-center justify-between rounded-lg border border-blue-200 bg-white px-3 py-2 text-left text-xs hover:bg-blue-100 disabled:opacity-60"
                >
                  <div>
                    <p className="font-semibold text-slate-900">{page.name || "Untitled Page"}</p>
                    <p className="text-[10px] text-slate-500">{page.username ? `@${page.username}` : page.category || "Facebook Page"}</p>
                  </div>
                  {fbCompletingPageId === page.id ? <Loader2 size={12} className="animate-spin text-blue-700" /> : <span className="text-blue-700 font-semibold">Connect</span>}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-blue-900">No pages found. Try reconnecting Facebook.</p>
          )}
        </section>
      )}

      {/* ── Section 1: Messaging (Free) ──────────────────────────────────── */}
      <section id="integrations-messaging" className="scroll-mt-24">
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Messaging</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SmallTile
            title="WhatsApp" subtitle="QR-link · messages &amp; automations"
            borderClass="border-[#25D366]/30 bg-[#25D366]/10" badge={FREE_BADGE}
            icon={<WaGlyph className="h-5 w-5 text-[#25D366]" />}
          >
            <WhatsAppIntegrationControls />
          </SmallTile>

          <SmallTile
            title="Telegram" subtitle="Bot token from @BotFather"
            borderClass="border-[#229ED9]/20 bg-sky-50/50" badge={FREE_BADGE}
            icon={<TelegramGlyph className="h-5 w-5 text-[#229ED9]" />}
          >
            <TelegramStatus connection={tgConn} onChanged={refreshTg} />
          </SmallTile>
        </div>
      </section>

      {/* ── Section 2: Social Channels ───────────────────────────────────── */}
      <section id="integrations-social" className="scroll-mt-24">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Social Channels</h2>
          <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-brand-dark ring-1 ring-brand/20">Advanced · Paid</span>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {SOCIAL_PLATFORMS.map((p) => {
            const account = zernioAccounts.find((a) => a.platform.toLowerCase() === p.id);
            const isConnected = !!account;
            return (
              <SmallTile
                key={p.id}
                title={p.label}
                subtitle={isConnected ? (account.username ? `@${account.username}` : account.name ?? "Connected") : "Ready to connect"}
                borderClass={isConnected ? `${p.border} ${p.bg}` : "border-slate-200"}
                icon={<div className="h-5 w-5">{p.logo}</div>}
              >
                {isConnected ? (
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
                      <CheckCircle2 size={12} /> Connected
                    </div>
                    <button
                      type="button"
                      disabled={zernioDisconnecting === account!.id}
                      onClick={() => void zernioDisconnect(account!.id, p.label)}
                      className="flex w-full items-center justify-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      {zernioDisconnecting === account!.id ? <Loader2 size={11} className="animate-spin" /> : <><X size={11} /><span>Disconnect</span></>}
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={zernioConnecting === p.id}
                    onClick={() => void zernioConnect(p.id)}
                    className="flex w-full items-center justify-center gap-1 rounded-lg bg-brand-dark px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-brand disabled:opacity-50"
                  >
                    {zernioConnecting === p.id
                      ? <Loader2 size={11} className="animate-spin" />
                      : <><span>Connect</span><ExternalLink size={9} /></>}
                  </button>
                )}
              </SmallTile>
            );
          })}
        </div>
        <p className="mt-2 text-[10px] text-slate-400">
          Powered by third-party social connection infrastructure.
        </p>
      </section>

      {/* ── Section 3: Payments ──────────────────────────────────────────── */}
      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Payments</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SmallTile
            title="Stripe"
            subtitle={
              stripeIsLinked(stConn)
                ? stConn.checkout_ready || stConn.charges_enabled
                  ? "Card checkout enabled"
                  : "Connected — finish setup in Stripe"
                : "International cards & payouts"
            }
            borderClass="border-[#635BFF]/20 bg-[#635BFF]/5"
            icon={<StripeGlyph className="h-5 w-5 text-[#635BFF]" />}
          >
            <StripeConnectStatus
              connection={stConn}
              connectionHydrated={stConnHydrated}
              onChanged={refreshSt}
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
            title="Flutterwave" subtitle="Card &amp; bank — Africa multi-currency splits"
            borderClass="border-[#F5A623]/25 bg-[#F5A623]/8"
            icon={<FlutterwaveGlyph className="h-5 w-5 text-[#E09510]" />}
          >
            <FlutterwaveStatus connection={fwConn} onChanged={refreshFw} />
          </SmallTile>

          <SmallTile
            title="PayHero" subtitle="M-Pesa STK push &amp; mobile money — Kenya"
            borderClass="border-[#1DB954]/20 bg-[#1DB954]/5"
            icon={<PayHeroGlyph className="h-5 w-5 text-[#1DB954]" />}
          >
            <PayHeroStatus connection={phConn} onChanged={refreshPh} />
          </SmallTile>
        </div>
      </section>

      {/* ── Section 4: Email Marketing ───────────────────────────────────── */}
      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Email Marketing</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SmallTile
            title="Klaviyo" subtitle="Best for e-commerce &amp; Shopify stores"
            borderClass="border-[#00A500]/20 bg-[#00A500]/5"
            icon={<KlaviyoGlyph className="h-5 w-5 text-[#00A500]" />}
          >
            <ComposioTileControls
              connected={composioStatus.klaviyo}
              busy={composioBusy === "klaviyo"}
              connectLabel="Connect Klaviyo"
              connectClass="bg-[#00A500] hover:bg-[#008000]"
              onConnect={() => void composioConnect("klaviyo")}
              onDisconnect={() => void composioDisconnect("klaviyo", "Klaviyo")}
            />
          </SmallTile>

          <SmallTile
            title="Mailchimp" subtitle="Email campaigns &amp; automations"
            borderClass="border-[#FFE01B]/40 bg-[#FFE01B]/10"
            icon={<MailchimpGlyph className="h-5 w-5 text-[#241C15]" />}
          >
            <ComposioTileControls
              connected={composioStatus.mailchimp}
              busy={composioBusy === "mailchimp"}
              connectLabel="Connect Mailchimp"
              connectClass="bg-[#241C15] hover:bg-black"
              onConnect={() => void composioConnect("mailchimp")}
              onDisconnect={() => void composioDisconnect("mailchimp", "Mailchimp")}
            />
          </SmallTile>

          <SmallTile
            title="Brevo" subtitle="Email, SMS &amp; marketing automation"
            borderClass="border-[#0B996E]/20 bg-[#0B996E]/5"
            icon={<BrevoGlyph className="h-5 w-5 text-[#0B996E]" />}
          >
            <ComposioTileControls
              connected={composioStatus.brevo}
              busy={composioBusy === "brevo"}
              connectLabel="Connect Brevo"
              connectClass="bg-[#0B996E] hover:bg-[#097a58]"
              onConnect={() => void composioConnect("brevo")}
              onDisconnect={() => void composioDisconnect("brevo", "Brevo")}
            />
          </SmallTile>
        </div>
      </section>

      {/* ── Section 5: Productivity ──────────────────────────────────────── */}
      <section id="integrations-productivity" className="scroll-mt-24">
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Productivity</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <div id="integrations-slack" className="min-w-0">
            <SmallTile
              title="Slack" subtitle="Workspace notifications"
              borderClass="border-[#4A154B]/20 bg-[#4A154B]/5"
              icon={<SlackGlyph className="h-5 w-5 text-[#4A154B]" />}
            >
              <ComposioTileControls
                connected={composioStatus.slack}
                busy={composioBusy === "slack"}
                connectLabel="Connect Slack"
                connectClass="bg-[#4A154B] hover:bg-[#3e1240]"
                onConnect={() => void composioConnect("slack")}
                onDisconnect={() => void composioDisconnect("slack", "Slack")}
              />
            </SmallTile>
          </div>

          <div id="integrations-gmail" className="min-w-0">
            <SmallTile
              title="Gmail" subtitle="Read, send &amp; draft emails"
              borderClass="border-red-200 bg-red-50/50"
              icon={<Mail size={18} className="text-red-500" />}
            >
              <ComposioTileControls
                connected={composioStatus.gmail}
                busy={composioBusy === "gmail"}
                connectLabel="Connect Gmail"
                connectClass="bg-red-500 hover:bg-red-600"
                onConnect={() => void composioConnect("gmail")}
                onDisconnect={() => void composioDisconnect("gmail", "Gmail")}
              />
            </SmallTile>
          </div>

          <div id="integrations-microsoft" className="min-w-0">
            <SmallTile
              title="Microsoft" subtitle="Outlook, Calendar &amp; Contacts"
              borderClass="border-[#0078D4]/20 bg-[#0078D4]/5"
              icon={<MicrosoftGlyph className="h-5 w-5 text-[#0078D4]" />}
            >
              <ComposioTileControls
                connected={composioStatus.outlook}
                busy={composioBusy === "outlook"}
                connectLabel="Connect Microsoft"
                connectClass="bg-[#0078D4] hover:bg-[#006abc]"
                onConnect={() => void composioConnect("outlook")}
                onDisconnect={() => void composioDisconnect("outlook", "Microsoft")}
              />
            </SmallTile>
          </div>

          <div id="integrations-google-calendar" className="min-w-0">
            <SmallTile
              title="Google Calendar" subtitle="Events, meetings &amp; scheduling"
              borderClass="border-emerald-200 bg-emerald-50/50"
              icon={<Calendar size={18} className="text-emerald-600" />}
            >
              <ComposioTileControls
                connected={composioStatus.googlecalendar}
                busy={composioBusy === "googlecalendar"}
                connectLabel="Connect Calendar"
                connectClass="bg-emerald-600 hover:bg-emerald-700"
                onConnect={() => void composioConnect("googlecalendar")}
                onDisconnect={() => void composioDisconnect("googlecalendar", "Google Calendar")}
              />
            </SmallTile>
          </div>

          <div id="integrations-google-sheets" className="min-w-0">
            <SmallTile
              title="Google Sheets" subtitle="Sync data to &amp; from spreadsheets"
              borderClass="border-[#0F9D58]/20 bg-[#0F9D58]/5"
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none">
                  <rect width="24" height="24" rx="3" fill="#0F9D58"/>
                  <rect x="5" y="4" width="14" height="16" rx="1" fill="white"/>
                  <rect x="7" y="7" width="10" height="1.5" rx="0.5" fill="#0F9D58"/>
                  <rect x="7" y="10" width="10" height="1.5" rx="0.5" fill="#0F9D58"/>
                  <rect x="7" y="13" width="10" height="1.5" rx="0.5" fill="#0F9D58"/>
                  <rect x="7" y="16" width="6" height="1.5" rx="0.5" fill="#0F9D58"/>
                </svg>
              }
            >
              <ComposioTileControls
                connected={composioStatus.googlesheets}
                busy={composioBusy === "googlesheets"}
                connectLabel="Connect Sheets"
                connectClass="bg-[#0F9D58] hover:bg-[#0b7a44]"
                onConnect={() => void composioConnect("googlesheets")}
                onDisconnect={() => void composioDisconnect("googlesheets", "Google Sheets")}
              />
            </SmallTile>
          </div>

          <div id="integrations-notion" className="min-w-0">
            <SmallTile
              title="Notion" subtitle="Sync pages, databases &amp; notes"
              borderClass="border-slate-300/60 bg-slate-50/80"
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.14c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.934.653.934 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.374-1.54 1.447-1.632z"/>
                </svg>
              }
            >
              <ComposioTileControls
                connected={composioStatus.notion}
                busy={composioBusy === "notion"}
                connectLabel="Connect Notion"
                connectClass="bg-slate-900 hover:bg-slate-700"
                onConnect={() => void composioConnect("notion")}
                onDisconnect={() => void composioDisconnect("notion", "Notion")}
              />
            </SmallTile>
          </div>
        </div>
      </section>

      {/* ── Section 5b: Advertising & Analytics ─────────────────────────── */}
      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Advertising &amp; Analytics</h2>
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
              connectLabel="Connect Google Ads"
              connectClass="bg-[#4285F4] hover:bg-[#3367d6]"
              onConnect={() => void composioConnect("googleads", false, { customer_id: googleAdsCustomerId })}
              onDisconnect={() => void composioDisconnect("googleads", "Google Ads")}
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
              connectLabel="Connect Search Console"
              connectClass="bg-[#0F9D58] hover:bg-[#0b7a44]"
              onConnect={() => void composioConnect("googlesearchconsole")}
              onDisconnect={() => void composioDisconnect("googlesearchconsole", "Search Console")}
            />
          </SmallTile>
        </div>
      </section>

      {/* ── Section 6: E-commerce ────────────────────────────────────────── */}
      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">E-commerce</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <SmallTile
            title="Shopify" subtitle="Sync orders, customers &amp; products"
            borderClass="border-[#96BF48]/30 bg-[#96BF48]/10"
            icon={<ShopifyGlyph className="h-5 w-5 text-[#5A8E00]" />}
          >
            {composioStatus.shopify === null ? (
              <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
                <Loader2 size={11} className="animate-spin" /> Checking…
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
        </div>
      </section>

      {/* ── Section 7: Supplier Accounts ───────────────────────────────────── */}
      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Supplier Accounts</h2>
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
      </section>

      {/* Footer */}
      <section className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[11px] leading-relaxed text-slate-600">
        Need usage stats and contact tools? Open{" "}
        <Link href="/dashboard/whatsapp" className="font-medium text-brand-dark hover:underline">WhatsApp</Link>{" "}
        in the sidebar. Team and shop options are in{" "}
        <Link href="/dashboard/settings" className="font-medium text-brand-dark hover:underline">Settings</Link>.
      </section>
    </div>
  );
}

"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { NANGO_INTEGRATION_IDS } from "@/lib/nango-config";
import { openNangoConnect } from "@/lib/nango-connect";
import { telegramApi, type TelegramConnection, paystackApi, type PaystackConnection, payheroApi, type PayheroConnection } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { WaGlyph, WhatsAppIntegrationControls } from "@/components/whatsapp/WhatsAppIntegrationTile";
import { SOCIAL_PLATFORMS } from "@/components/ZernioSocialPanel";
import { zernioApi } from "@/lib/api";
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

// ── PayHero (Basic Auth) ──────────────────────────────────────────────────────

function PayHeroStatus({ connection, onChanged }: { connection?: PayheroConnection; onChanged: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

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

  if (connection?.connected) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-green-700 text-[11px] font-medium">
          <CheckCircle size={12} />
          {connection.username || "Connected"}
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
  const [phConn, setPhConn] = useState<PayheroConnection>({ connected: false });
  const [zernioAccounts, setZernioAccounts] = useState<ZernioAccount[]>([]);
  const [zernioApiOk, setZernioApiOk] = useState<boolean | null>(null);
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
    try {
      const status = await zernioApi.status();
      setZernioApiOk(status.connected === true);
      if (status.connected) setZernioAccounts((status.accounts as ZernioAccount[]) ?? []);
      else setZernioAccounts([]);
    } catch {
      setZernioApiOk(false);
      setZernioAccounts([]);
    }
  }, []);

  async function zernioConnect(platformId: string) {
    setZernioConnecting(platformId);
    try {
      const redirectUrl = `${window.location.origin}/dashboard/integrations?connected=${encodeURIComponent(platformId)}`;
      const isHeadlessFacebook = platformId === "facebook";
      const { authUrl } = await zernioApi.connect(platformId, redirectUrl, isHeadlessFacebook);
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
      await zernioApi.disconnect(accountId);
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
  const [banner, setBanner] = useState<{ type: "success" | "error"; msg: string } | null>(null);
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

  const refreshNango = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const ids = Object.values(NANGO_IDS).join(",");
    try {
      const res = await fetch(`/api/nango/connections?integrations=${ids}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
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

  useEffect(() => { refreshTg(); refreshPs(); refreshPh(); void refreshNango(); void refreshZernio(); }, [refreshTg, refreshPs, refreshPh, refreshNango, refreshZernio]);

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
      setBanner({ type: "success", msg: `${connected.charAt(0).toUpperCase() + connected.slice(1)} connected!` });
      refreshTg(); void refreshNango(); void refreshZernio();
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
    <div className="mx-auto max-w-4xl min-w-0 space-y-6 p-4 sm:p-6">

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
            title="Stripe" subtitle="International payments &amp; subscriptions"
            borderClass="border-[#635BFF]/20 bg-[#635BFF]/5"
            icon={<StripeGlyph className="h-5 w-5 text-[#635BFF]" />}
          >
            <NangoTileControls
              connected={nangoStatus.stripe} connectLabel="Connect Stripe"
              connectClass="bg-[#635BFF] hover:bg-[#4f46e5]"
              onConnect={() => nangoConnect("stripe")}
              onDisconnect={() => nangoDisconnect("stripe")}
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
            <NangoTileControls
              connected={nangoStatus.klaviyo} connectLabel="Connect Klaviyo"
              connectClass="bg-[#00A500] hover:bg-[#008000]"
              onConnect={() => nangoConnect("klaviyo")}
              onDisconnect={() => nangoDisconnect("klaviyo")}
            />
          </SmallTile>

          <SmallTile
            title="Mailchimp" subtitle="Email campaigns &amp; automations"
            borderClass="border-[#FFE01B]/40 bg-[#FFE01B]/10"
            icon={<MailchimpGlyph className="h-5 w-5 text-[#241C15]" />}
          >
            <NangoTileControls
              connected={nangoStatus.mailchimp} connectLabel="Connect Mailchimp"
              connectClass="bg-[#241C15] hover:bg-black"
              onConnect={() => nangoConnect("mailchimp")}
              onDisconnect={() => nangoDisconnect("mailchimp")}
            />
          </SmallTile>

          <SmallTile
            title="Brevo" subtitle="Email, SMS &amp; marketing automation"
            borderClass="border-[#0B996E]/20 bg-[#0B996E]/5"
            icon={<BrevoGlyph className="h-5 w-5 text-[#0B996E]" />}
          >
            <NangoTileControls
              connected={nangoStatus.brevo} connectLabel="Connect Brevo"
              connectClass="bg-[#0B996E] hover:bg-[#097a58]"
              onConnect={() => nangoConnect("brevo")}
              onDisconnect={() => nangoDisconnect("brevo")}
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
              <NangoTileControls
                connected={nangoStatus.slack} connectLabel="Connect Slack"
                connectClass="bg-[#4A154B] hover:bg-[#3e1240]"
                onConnect={() => nangoConnect("slack")}
                onDisconnect={() => nangoDisconnect("slack")}
              />
            </SmallTile>
          </div>

          <div id="integrations-gmail" className="min-w-0">
            <SmallTile
              title="Gmail" subtitle="Google Mail &amp; inbox"
              borderClass="border-red-200 bg-red-50/50"
              icon={<Mail size={18} className="text-red-500" />}
            >
              <NangoTileControls
                connected={nangoStatus.email} connectLabel="Connect Gmail"
                connectClass="bg-red-500 hover:bg-red-600"
                onConnect={() => nangoConnect("email")}
                onDisconnect={() => nangoDisconnect("email")}
              />
            </SmallTile>
          </div>

          <div id="integrations-microsoft" className="min-w-0">
            <SmallTile
              title="Microsoft" subtitle="Outlook, Calendar &amp; Contacts"
              borderClass="border-[#0078D4]/20 bg-[#0078D4]/5"
              icon={<MicrosoftGlyph className="h-5 w-5 text-[#0078D4]" />}
            >
              <NangoTileControls
                connected={nangoStatus.microsoft} connectLabel="Connect Microsoft"
                connectClass="bg-[#0078D4] hover:bg-[#006abc]"
                onConnect={() => nangoConnect("microsoft")}
                onDisconnect={() => nangoDisconnect("microsoft")}
              />
            </SmallTile>
          </div>

          <div id="integrations-google-calendar" className="min-w-0">
            <SmallTile
              title="Google Calendar" subtitle="Meetings &amp; scheduling"
              borderClass="border-emerald-200 bg-emerald-50/50"
              icon={<Calendar size={18} className="text-emerald-600" />}
            >
              <NangoTileControls
                connected={nangoStatus.calendar} connectLabel="Connect Calendar"
                connectClass="bg-emerald-600 hover:bg-emerald-700"
                onConnect={() => nangoConnect("calendar")}
                onDisconnect={() => nangoDisconnect("calendar")}
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
              <NangoTileControls
                connected={nangoStatus.google_sheets} connectLabel="Connect Sheets"
                connectClass="bg-[#0F9D58] hover:bg-[#0b7a44]"
                onConnect={() => nangoConnect("google_sheets")}
                onDisconnect={() => nangoDisconnect("google_sheets")}
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
              <NangoTileControls
                connected={nangoStatus.notion} connectLabel="Connect Notion"
                connectClass="bg-slate-900 hover:bg-slate-700"
                onConnect={() => nangoConnect("notion")}
                onDisconnect={() => nangoDisconnect("notion")}
              />
            </SmallTile>
          </div>
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
            <NangoTileControls
              connected={nangoStatus.shopify} connectLabel="Connect Shopify"
              connectClass="bg-[#5A8E00] hover:bg-[#4a7500]"
              onConnect={() => nangoConnect("shopify")}
              onDisconnect={() => nangoDisconnect("shopify")}
            />
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

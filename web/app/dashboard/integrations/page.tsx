"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { NANGO_INTEGRATION_IDS } from "@/lib/nango-config";
import { openNangoConnect } from "@/lib/nango-connect";
import { metaApi, type MetaConnection } from "@/lib/api";
import { Plug, Mail, Calendar, CheckCircle, Loader2 } from "lucide-react";

function SlackGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834V5.042zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.122 2.521a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zm-1.269 0a2.528 2.528 0 0 1-2.521 2.521 2.527 2.527 0 0 1-2.521-2.521V2.522A2.528 2.528 0 0 1 15.165 0a2.528 2.528 0 0 1 2.521 2.522v6.312zm-2.521 10.122a2.527 2.527 0 0 1 2.521 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.521-2.522v-2.521h2.521zm0-1.269a2.527 2.527 0 0 1-2.521-2.521 2.528 2.528 0 0 1 2.521-2.521h6.313A2.528 2.528 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.521h-6.313z" />
    </svg>
  );
}

function MessengerGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M12 0C5.373 0 0 4.975 0 11.111c0 3.497 1.745 6.616 4.472 8.652V24l4.086-2.242c1.09.301 2.246.464 3.442.464 6.627 0 12-4.975 12-11.111S18.627 0 12 0zm1.191 14.963l-3.055-3.26-5.963 3.26L10.732 8l3.131 3.26L19.752 8l-6.561 6.963z" />
    </svg>
  );
}

function InstagramGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z" />
    </svg>
  );
}

type SmallTileProps = {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  borderClass: string;
  children: ReactNode;
};

function SmallTile({ icon, title, subtitle, borderClass, children }: SmallTileProps) {
  return (
    <div className={`flex flex-col rounded-xl border p-3 shadow-sm ${borderClass}`}>
      <div className="flex items-start gap-2.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/90 shadow-sm">{icon}</div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-tight text-slate-900">{title}</h3>
          {subtitle ? <p className="mt-0.5 text-[11px] leading-snug text-slate-500">{subtitle}</p> : null}
        </div>
      </div>
      <div className="mt-2.5">{children}</div>
    </div>
  );
}

type MetaConnectFormProps = {
  channel: "messenger" | "instagram";
  connection?: MetaConnection;
  onConnected: () => void;
  onDisconnected: () => void;
};

function MetaConnectForm({ channel, connection, onConnected, onDisconnected }: MetaConnectFormProps) {
  const [open, setOpen] = useState(false);
  const [pageId, setPageId] = useState("");
  const [token, setToken] = useState("");
  const [igId, setIgId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const isInstagram = channel === "instagram";

  async function handleConnect() {
    if (!pageId.trim() || !token.trim()) {
      setError("Page ID and Access Token are required");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await metaApi.connect({
        page_id: pageId.trim(),
        page_access_token: token.trim(),
        channel,
        instagram_id: isInstagram ? (igId.trim() || pageId.trim()) : undefined,
      });
      setOpen(false);
      setPageId(""); setToken(""); setIgId("");
      onConnected();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setSaving(false);
    }
  }

  async function handleDisconnect() {
    if (!confirm(`Disconnect ${channel}? Auto-replies on this channel will stop.`)) return;
    try {
      await metaApi.disconnect(channel);
      onDisconnected();
    } catch {
      alert("Failed to disconnect");
    }
  }

  if (connection?.connected) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 text-green-700 text-xs font-medium">
          <CheckCircle size={13} />
          Connected · Page {connection.page_id}
        </div>
        <button
          onClick={handleDisconnect}
          className="w-full rounded-lg bg-red-600 px-2.5 py-1.5 text-center text-xs font-semibold text-white hover:bg-red-700"
        >
          Disconnect
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className={`w-full rounded-lg px-2.5 py-1.5 text-center text-xs font-semibold text-white ${
            isInstagram
              ? "bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600"
              : "bg-[#0084ff] hover:bg-[#006ecc]"
          }`}
        >
          Connect
        </button>
      ) : (
        <div className="space-y-1.5">
          <input
            className="w-full rounded border border-slate-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-400"
            placeholder={isInstagram ? "Instagram Account ID" : "Page ID (e.g. 114174821715288)"}
            value={pageId}
            onChange={e => setPageId(e.target.value)}
          />
          {isInstagram && (
            <input
              className="w-full rounded border border-slate-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-400"
              placeholder="Instagram User ID (if different from Page ID)"
              value={igId}
              onChange={e => setIgId(e.target.value)}
            />
          )}
          <input
            className="w-full rounded border border-slate-200 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-400"
            placeholder="Page Access Token"
            value={token}
            onChange={e => setToken(e.target.value)}
            type="password"
          />
          {error && <p className="text-[10px] text-red-600">{error}</p>}
          <div className="flex gap-1.5">
            <button
              onClick={handleConnect}
              disabled={saving}
              className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-indigo-600 px-2 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving && <Loader2 size={11} className="animate-spin" />}
              Save
            </button>
            <button
              onClick={() => { setOpen(false); setError(""); }}
              className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function IntegrationsPage() {
  const [metaConns, setMetaConns] = useState<MetaConnection[]>([]);

  useEffect(() => {
    metaApi.connections().then(setMetaConns).catch(() => {});
  }, []);

  function refresh() {
    metaApi.connections().then(setMetaConns).catch(() => {});
  }

  function getConn(channel: "messenger" | "instagram") {
    return metaConns.find(c => c.channel === channel);
  }

  return (
    <div className="mx-auto max-w-3xl min-w-0 space-y-6 p-4 sm:p-6">
      <div>
        <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600">
          <Plug size={18} />
        </div>
        <h1 className="text-xl font-bold text-slate-900">Integrations</h1>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 sm:text-sm">
          Connect messaging channels and productivity tools to your CRM.
        </p>
      </div>

      {/* Meta Channels */}
      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Messenger · Instagram</h2>
        <div className="grid gap-2.5 sm:grid-cols-2">
          <SmallTile
            title="Messenger"
            subtitle="Facebook Page DMs → auto-reply"
            borderClass="border-[#0084ff]/20 bg-blue-50/50"
            icon={<MessengerGlyph className="h-5 w-5 text-[#0084ff]" />}
          >
            <MetaConnectForm
              channel="messenger"
              connection={getConn("messenger")}
              onConnected={refresh}
              onDisconnected={refresh}
            />
          </SmallTile>

          <SmallTile
            title="Instagram DMs"
            subtitle="Instagram Business DMs → auto-reply"
            borderClass="border-pink-200 bg-pink-50/50"
            icon={<InstagramGlyph className="h-5 w-5 text-pink-600" />}
          >
            <MetaConnectForm
              channel="instagram"
              connection={getConn("instagram")}
              onConnected={refresh}
              onDisconnected={refresh}
            />
          </SmallTile>
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          Get your Page ID and Access Token from{" "}
          <a href="https://developers.facebook.com" target="_blank" rel="noopener noreferrer" className="font-medium text-indigo-600 hover:underline">
            Meta for Developers
          </a>{" "}
          → your app → Messenger → Settings → Generate Token.
        </p>
      </section>

      {/* Slack · Email · Calendar */}
      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Slack · Email · Calendar</h2>
        <div className="grid gap-2.5 sm:grid-cols-3">
          <SmallTile
            title="Slack"
            subtitle="Workspace alerts & threads"
            borderClass="border-slate-200 bg-slate-50/80"
            icon={<SlackGlyph className="h-5 w-5 text-[#4A154B]" />}
          >
            <button
              type="button"
              onClick={() => openNangoConnect([NANGO_INTEGRATION_IDS.slack])}
              className="w-full rounded-lg bg-[#4A154B] px-2.5 py-1.5 text-center text-xs font-semibold text-white hover:bg-[#3e1240]"
            >
              Connect
            </button>
          </SmallTile>

          <SmallTile
            title="Email"
            subtitle="Gmail / Outlook via Nango"
            borderClass="border-slate-200 bg-slate-50/80"
            icon={<Mail size={18} className="text-slate-600" />}
          >
            <button
              type="button"
              onClick={() => openNangoConnect([NANGO_INTEGRATION_IDS.email])}
              className="w-full rounded-lg bg-slate-800 px-2.5 py-1.5 text-center text-xs font-semibold text-white hover:bg-slate-900"
            >
              Connect
            </button>
          </SmallTile>

          <SmallTile
            title="Calendar"
            subtitle="Google / Microsoft"
            borderClass="border-slate-200 bg-slate-50/80"
            icon={<Calendar size={18} className="text-emerald-600" />}
          >
            <button
              type="button"
              onClick={() => openNangoConnect([NANGO_INTEGRATION_IDS.calendar])}
              className="w-full rounded-lg bg-emerald-600 px-2.5 py-1.5 text-center text-xs font-semibold text-white hover:bg-emerald-700"
            >
              Connect
            </button>
          </SmallTile>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[11px] leading-relaxed text-slate-600">
        <strong className="text-slate-800">WhatsApp</strong> is under{" "}
        <Link href="/dashboard/whatsapp" className="font-medium text-indigo-600 hover:underline">
          Business → WhatsApp
        </Link>
        . Team &amp; shop settings live in{" "}
        <Link href="/dashboard/settings" className="font-medium text-indigo-600 hover:underline">
          Settings
        </Link>
        .
      </section>
    </div>
  );
}

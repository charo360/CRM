"use client";

import { useEffect, useState } from "react";
import {
  ChefHat, Copy, Check, ExternalLink, Lock, Unlock, Eye, EyeOff, Loader2, AlertTriangle,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "/api";

function authHeader(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchMe(): Promise<{ id: string; business_id?: string }> {
  const res = await fetch(`${API}/auth/me`, { headers: authHeader() });
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

async function fetchKdsSettings(businessId: string) {
  const res = await fetch(`${API}/kds/${businessId}/settings`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to load");
  return res.json() as Promise<{ kds_pin: string; kds_enabled: boolean }>;
}

async function saveKdsPin(businessId: string, pin: string) {
  const res = await fetch(`${API}/kds/${businessId}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ kds_pin: pin }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to save");
  }
  return res.json();
}

export default function KdsSettingsPage() {
  const [businessId, setBusinessId] = useState<string | null>(null);
  const [currentPin, setCurrentPin] = useState("");
  const [pinInput, setPinInput]     = useState("");
  const [showPin, setShowPin]       = useState(false);
  const [saving, setSaving]         = useState(false);
  const [saveError, setSaveError]   = useState("");
  const [saveOk, setSaveOk]         = useState(false);
  const [loading, setLoading]       = useState(true);
  const [copied, setCopied]         = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const me = await fetchMe();
        const bid = me.business_id || me.id;
        setBusinessId(bid);
        const s = await fetchKdsSettings(bid);
        setCurrentPin(s.kds_pin || "");
        setPinInput(s.kds_pin || "");
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const kdsUrl = businessId
    ? `${typeof window !== "undefined" ? window.location.origin : ""}/kds/${businessId}`
    : "";

  async function handleSave() {
    if (!businessId) return;
    const trimmed = pinInput.trim();
    if (trimmed && (trimmed.length < 4 || trimmed.length > 8 || !/^\d+$/.test(trimmed))) {
      setSaveError("PIN must be 4–8 digits");
      return;
    }
    setSaving(true);
    setSaveError("");
    setSaveOk(false);
    try {
      await saveKdsPin(businessId, trimmed);
      setCurrentPin(trimmed);
      setSaveOk(true);
      setTimeout(() => setSaveOk(false), 3000);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function copyUrl() {
    if (!kdsUrl) return;
    navigator.clipboard.writeText(kdsUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="animate-spin text-slate-400" size={22} />
      </div>
    );
  }

  const isEnabled = Boolean(currentPin);

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-500 text-white shadow">
          <ChefHat size={20} />
        </div>
        <div>
          <h1 className="text-lg font-bold text-slate-900">Kitchen Display System</h1>
          <p className="text-sm text-slate-500">Real-time order board for kitchen staff. No login required — PIN protected.</p>
        </div>
      </div>

      {/* Status card */}
      <div className={`mb-6 flex items-center gap-3 rounded-xl border px-4 py-3 ${
        isEnabled ? "border-green-200 bg-green-50" : "border-slate-200 bg-slate-50"
      }`}>
        {isEnabled ? (
          <>
            <Unlock size={16} className="text-green-600" />
            <p className="text-sm text-green-800 font-medium">KDS is <strong>active</strong> — share the URL below with your kitchen staff.</p>
          </>
        ) : (
          <>
            <Lock size={16} className="text-slate-500" />
            <p className="text-sm text-slate-600">Set a PIN below to enable the KDS.</p>
          </>
        )}
      </div>

      {/* PIN setup */}
      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-slate-800">KDS Access PIN</h2>
        <p className="mb-4 text-xs text-slate-500">
          Staff enter this PIN on the KDS screen. Set to blank to disable access.
        </p>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <input
              type={showPin ? "text" : "password"}
              inputMode="numeric"
              value={pinInput}
              onChange={(e) => {
                setPinInput(e.target.value.replace(/\D/g, "").slice(0, 8));
                setSaveError("");
              }}
              placeholder="4–8 digit PIN"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 pr-9 text-sm text-slate-900 tracking-widest outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-100"
            />
            <button
              type="button"
              onClick={() => setShowPin(!showPin)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              {showPin ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-orange-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-orange-600 active:scale-[0.97] disabled:opacity-60"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : saveOk ? <Check size={13} /> : null}
            {saveOk ? "Saved!" : "Save PIN"}
          </button>
        </div>
        {saveError && (
          <p className="mt-2 flex items-center gap-1 text-xs text-red-600">
            <AlertTriangle size={11} /> {saveError}
          </p>
        )}
      </div>

      {/* KDS URL share */}
      {isEnabled && (
        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-1 text-sm font-semibold text-slate-800">KDS Display URL</h2>
          <p className="mb-3 text-xs text-slate-500">
            Share this link with kitchen staff. Open it on any tablet or browser in the kitchen.
          </p>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={kdsUrl}
              className="flex-1 truncate rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 outline-none"
            />
            <button
              type="button"
              onClick={copyUrl}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:border-orange-300 hover:text-orange-600"
            >
              {copied ? <Check size={13} className="text-green-600" /> : <Copy size={13} />}
              {copied ? "Copied!" : "Copy"}
            </button>
            <a
              href={kdsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:border-orange-300 hover:text-orange-600"
            >
              <ExternalLink size={13} />
              Open
            </a>
          </div>
        </div>
      )}

      {/* How it works */}
      <div className="rounded-xl border border-slate-100 bg-slate-50 p-5">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">How it works</h2>
        <ol className="space-y-2 text-xs text-slate-600">
          <li className="flex gap-2"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-orange-500 text-[10px] font-bold text-white">1</span>Set a 4–8 digit PIN above and save it.</li>
          <li className="flex gap-2"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-orange-500 text-[10px] font-bold text-white">2</span>Share the KDS URL with kitchen staff — open it on a tablet or mounted screen.</li>
          <li className="flex gap-2"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-orange-500 text-[10px] font-bold text-white">3</span>Staff enter the PIN to unlock the display. Orders appear automatically and refresh every 5 seconds.</li>
          <li className="flex gap-2"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-orange-500 text-[10px] font-bold text-white">4</span>Tap <strong>Confirm → Preparing → Ready → Done</strong> on each card as the order progresses. Done orders disappear from the board.</li>
        </ol>
        <div className="mt-4 flex flex-wrap gap-2 text-[10px]">
          {[
            { c: "bg-red-500", l: "New" },
            { c: "bg-orange-500", l: "Confirmed" },
            { c: "bg-yellow-500", l: "Preparing" },
            { c: "bg-green-600", l: "Ready" },
          ].map(({ c, l }) => (
            <span key={l} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-white font-semibold ${c}`}>
              {l}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

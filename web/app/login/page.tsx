"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { setToken, setUser } from "@/lib/auth";
import { Zap, Loader2, Phone, Copy, CheckCircle2, RefreshCw } from "lucide-react";

type Step = "phone" | "pairing" | "waiting";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [pairingCode, setPairingCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pollCount, setPollCount] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.post<{
        session_token?: string;
        pairing_code?: string;
        access_token?: string;
        token?: string;
        user?: Record<string, unknown>;
        already_connected?: boolean;
        connected?: boolean;
      }>("/auth/whatsapp-start", { phone_number: phone.trim() });

      // Already connected — JWT issued directly
      const jwt = res.access_token || res.token;
      if (jwt && res.user) {
        setToken(jwt);
        setUser(res.user);
        router.push("/dashboard");
        return;
      }

      if (res.session_token) {
        setSessionToken(res.session_token);
        setPairingCode(res.pairing_code || "");
        setStep("pairing");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start. Check your phone number.");
    } finally {
      setLoading(false);
    }
  }

  function handleLinked() {
    setStep("waiting");
    setPollCount(0);
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.post<{
          access_token?: string;
          token?: string;
          user?: Record<string, unknown>;
          status?: string;
        }>("/auth/whatsapp-check", { session_token: sessionToken });

        const jwt = res.access_token || res.token;
        if (jwt && res.user) {
          if (pollRef.current) clearInterval(pollRef.current);
          setToken(jwt);
          setUser(res.user);
          router.push("/dashboard");
        }
      } catch {
        // keep polling
      }
      setPollCount((n) => {
        if (n >= 30) {
          if (pollRef.current) clearInterval(pollRef.current);
          setError("Timed out waiting for WhatsApp connection. Please try again.");
          setStep("phone");
        }
        return n + 1;
      });
    }, 3000);
  }

  function copyCode() {
    navigator.clipboard.writeText(pairingCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-indigo-600 flex items-center justify-center mb-3">
            <Zap size={24} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Zilo CRM</h1>
          <p className="text-sm text-slate-500 mt-1">Business management dashboard</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">

          {/* Step 1 — Phone number */}
          {step === "phone" && (
            <form onSubmit={handleStart} className="space-y-4">
              <div>
                <h2 className="text-base font-semibold text-slate-900 mb-1">Sign in with WhatsApp</h2>
                <p className="text-xs text-slate-500">Enter your WhatsApp phone number to continue</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Phone number</label>
                <div className="relative">
                  <Phone size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => { setPhone(e.target.value); setError(""); }}
                    placeholder="+254 700 000 000"
                    required
                    className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 placeholder:text-slate-400"
                  />
                </div>
                <p className="text-xs text-slate-400 mt-1">Include country code, e.g. +254</p>
              </div>
              {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-medium py-2.5 rounded-lg transition-colors text-sm"
              >
                {loading ? <Loader2 size={15} className="animate-spin" /> : <Phone size={15} />}
                Continue
              </button>
            </form>
          )}

          {/* Step 2 — Pairing code */}
          {step === "pairing" && (
            <div className="space-y-5">
              <div>
                <h2 className="text-base font-semibold text-slate-900 mb-1">Link your WhatsApp</h2>
                <p className="text-xs text-slate-500">Open WhatsApp → Linked Devices → Link a Device → Link with phone number</p>
              </div>

              {pairingCode && (
                <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 text-center">
                  <p className="text-xs text-indigo-500 font-medium mb-2">Your pairing code</p>
                  <p className="text-3xl font-bold tracking-widest text-indigo-700 font-mono">{pairingCode}</p>
                  <button
                    onClick={copyCode}
                    className="mt-3 flex items-center gap-1.5 mx-auto text-xs text-indigo-600 hover:text-indigo-800"
                  >
                    {copied ? <CheckCircle2 size={13} /> : <Copy size={13} />}
                    {copied ? "Copied!" : "Copy code"}
                  </button>
                </div>
              )}

              <ol className="text-xs text-slate-500 space-y-1.5 list-decimal list-inside">
                <li>Open WhatsApp on your phone</li>
                <li>Tap ⋮ Menu → Linked Devices</li>
                <li>Tap <strong>Link a Device</strong></li>
                <li>Choose <strong>Link with phone number</strong></li>
                <li>Enter the code above</li>
              </ol>

              {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

              <div className="flex gap-2">
                <button
                  onClick={() => setStep("phone")}
                  className="flex-1 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50"
                >
                  Back
                </button>
                <button
                  onClick={handleLinked}
                  className="flex-1 py-2 text-sm bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700"
                >
                  I&apos;ve entered the code
                </button>
              </div>
            </div>
          )}

          {/* Step 3 — Waiting */}
          {step === "waiting" && (
            <div className="space-y-5 text-center">
              <div className="w-16 h-16 rounded-full bg-indigo-50 flex items-center justify-center mx-auto">
                <RefreshCw size={28} className="text-indigo-600 animate-spin" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Waiting for WhatsApp…</h2>
                <p className="text-xs text-slate-500 mt-1">Checking connection every 3 seconds</p>
              </div>
              {error && (
                <div>
                  <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
                  <button
                    onClick={() => { setStep("phone"); setError(""); }}
                    className="mt-3 text-sm text-indigo-600 hover:underline"
                  >
                    Start over
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <p className="text-center text-xs text-slate-400 mt-6">
          Kitchen Display?{" "}
          <a href="/kds" className="text-indigo-600 hover:underline">
            Open KDS
          </a>
        </p>
      </div>
    </div>
  );
}

"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { setToken, setUser } from "@/lib/auth";
import { ZiloLogo } from "@/components/ZiloLogo";
import { Zap, Loader2, Phone, Copy, CheckCircle2, RefreshCw, Mail, Lock, Building2, User } from "lucide-react";

type Step = "phone" | "pairing" | "waiting";
type AuthMode = "email" | "whatsapp";
type EmailStep = "login" | "register";

function normalizeUser(u: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!u) return {};
  const out = { ...u };
  if (out.id && !out._id) out._id = out.id;
  return out;
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("email");
  const [emailStep, setEmailStep] = useState<EmailStep>("login");

  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [pairingCode, setPairingCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [, setPollCount] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [ownerName, setOwnerName] = useState("");

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function applyAuthResponse(res: { access_token?: string; token?: string; must_change_password?: boolean; user?: Record<string, unknown> }) {
    const jwt = res.access_token || res.token;
    if (jwt && res.user) {
      setToken(jwt);
      setUser(normalizeUser(res.user));
      router.push(res.must_change_password ? "/change-password" : "/dashboard");
      return true;
    }
    return false;
  }

  async function handleEmailLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await authApi.loginWeb({ email: email.trim(), password });
      if (!applyAuthResponse(res)) {
        setError("Unexpected response from server");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleEmailRegister(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await authApi.registerWeb({
        email: email.trim(),
        password,
        business_name: businessName.trim(),
        owner_name: ownerName.trim() || undefined,
      });
      if (!applyAuthResponse(res)) {
        setError("Unexpected response from server");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not create account");
    } finally {
      setLoading(false);
    }
  }

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await authApi.whatsappStart(phone.trim());

      const jwt = res.access_token || res.token;
      if (jwt && res.user) {
        setToken(jwt);
        setUser(normalizeUser(res.user));
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
        const res = await authApi.whatsappCheck(sessionToken);

        const jwt = res.access_token || res.token;
        if (jwt && res.user) {
          if (pollRef.current) clearInterval(pollRef.current);
          setToken(jwt);
          setUser(normalizeUser(res.user));
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
        <div className="mb-8 flex flex-col items-center">
          <div className="flex items-center gap-1">
            <ZiloLogo size={48} className="shrink-0" priority />
            <h1 className="text-2xl font-bold leading-none text-slate-900">Zilo</h1>
          </div>
          <p className="mt-2 text-sm text-slate-500">Web workspace · Sell on every channel · AI</p>
        </div>

        <div className="flex rounded-xl border border-slate-200 bg-slate-100 p-1 mb-4">
          <button
            type="button"
            onClick={() => {
              setMode("email");
              setError("");
            }}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-colors ${
              mode === "email" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-800"
            }`}
          >
            Email
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("whatsapp");
              setError("");
              setStep("phone");
            }}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-colors ${
              mode === "whatsapp" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-800"
            }`}
          >
            WhatsApp
          </button>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
          {mode === "email" && (
            <>
              <div className="flex gap-2 mb-4 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setEmailStep("login");
                    setError("");
                  }}
                  className={`flex-1 py-1.5 rounded-lg font-medium ${
                    emailStep === "login" ? "bg-brand/25 text-brand-ink ring-1 ring-brand/30" : "text-slate-500 hover:bg-slate-50"
                  }`}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEmailStep("register");
                    setError("");
                  }}
                  className={`flex-1 py-1.5 rounded-lg font-medium ${
                    emailStep === "register" ? "bg-brand/25 text-brand-ink ring-1 ring-brand/30" : "text-slate-500 hover:bg-slate-50"
                  }`}
                >
                  Create account
                </button>
              </div>

              {emailStep === "login" && (
                <form onSubmit={handleEmailLogin} className="space-y-4">
                  <p className="text-xs text-slate-500">
                    Use the email and password you registered with. Link WhatsApp anytime under{" "}
                    <strong>Integrations</strong>.
                  </p>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Email</label>
                    <div className="relative">
                      <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          setError("");
                        }}
                        required
                        className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#4CD137] focus:ring-offset-0"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Password</label>
                    <div className="relative">
                      <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => {
                          setPassword(e.target.value);
                          setError("");
                        }}
                        required
                        className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#4CD137] focus:ring-offset-0"
                      />
                    </div>
                  </div>
                  {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#007a2e] bg-[#009B3A] py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-60"
                  >
                    {loading ? <Loader2 size={15} className="animate-spin" /> : <Mail size={15} />}
                    Sign in
                  </button>
                </form>
              )}

              {emailStep === "register" && (
                <form onSubmit={handleEmailRegister} className="space-y-3">
                  <p className="text-xs text-slate-500">
                    Create your workspace, then open <strong>Integrations</strong> to connect WhatsApp and other
                    channels.
                  </p>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Email</label>
                    <input
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        setError("");
                      }}
                      required
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#4CD137] focus:ring-offset-0"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Password (min 8 characters)</label>
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={password}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        setError("");
                      }}
                      required
                      minLength={8}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#4CD137] focus:ring-offset-0"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1 flex items-center gap-1">
                      <Building2 size={12} /> Business name
                    </label>
                    <input
                      type="text"
                      value={businessName}
                      onChange={(e) => setBusinessName(e.target.value)}
                      required
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#4CD137] focus:ring-offset-0"
                      placeholder="Your company or brand"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1 flex items-center gap-1">
                      <User size={12} /> Your name <span className="text-slate-400 font-normal">(optional)</span>
                    </label>
                    <input
                      type="text"
                      value={ownerName}
                      onChange={(e) => setOwnerName(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#4CD137] focus:ring-offset-0"
                    />
                  </div>
                  {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#007a2e] bg-[#009B3A] py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-60"
                  >
                    {loading ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />}
                    Create account
                  </button>
                </form>
              )}
            </>
          )}

          {mode === "whatsapp" && step === "phone" && (
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
                    onChange={(e) => {
                      setPhone(e.target.value);
                      setError("");
                    }}
                    placeholder="+1 555 000 0000"
                    required
                    className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-[#4CD137] focus:ring-offset-0 placeholder:text-slate-400"
                  />
                </div>
                <p className="text-xs text-slate-400 mt-1">Include country code, e.g. +1</p>
              </div>
              {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#007a2e] bg-[#009B3A] py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-60"
              >
                {loading ? <Loader2 size={15} className="animate-spin" /> : <Phone size={15} />}
                Continue
              </button>
            </form>
          )}

          {mode === "whatsapp" && step === "pairing" && (
            <div className="space-y-5">
              <div>
                <h2 className="text-base font-semibold text-slate-900 mb-1">Link your WhatsApp</h2>
                <p className="text-xs text-slate-500">Open WhatsApp → Linked Devices → Link a Device → Link with phone number</p>
              </div>

              {pairingCode && (
                <div className="rounded-xl border border-[#4CD137]/35 bg-[#4CD137]/12 p-4 text-center">
                  <p className="mb-2 text-xs font-medium text-[#065a24]">Your pairing code</p>
                  <p className="font-mono text-3xl font-bold tracking-widest text-[#009B3A]">{pairingCode}</p>
                  <button
                    type="button"
                    onClick={copyCode}
                    className="mx-auto mt-3 flex items-center gap-1.5 text-xs font-medium text-[#009B3A] hover:text-[#0a2614]"
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
                  type="button"
                  onClick={() => setStep("phone")}
                  className="flex-1 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={handleLinked}
                  className="flex-1 rounded-lg border border-[#007a2e] bg-[#009B3A] py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[#4CD137] hover:text-[#0a2614]"
                >
                  I&apos;ve entered the code
                </button>
              </div>
            </div>
          )}

          {mode === "whatsapp" && step === "waiting" && (
            <div className="space-y-5 text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#4CD137]/15">
                <RefreshCw size={28} className="animate-spin text-[#009B3A]" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-900">Waiting for WhatsApp…</h2>
                <p className="text-xs text-slate-500 mt-1">Checking connection every 3 seconds</p>
              </div>
              {error && (
                <div>
                  <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
                  <button
                    type="button"
                    onClick={() => {
                      setStep("phone");
                      setError("");
                    }}
                    className="mt-3 text-sm font-medium text-[#009B3A] hover:underline"
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
          <a href="/kds" className="font-medium text-[#009B3A] hover:underline">
            Open KDS
          </a>
        </p>
      </div>
    </div>
  );
}

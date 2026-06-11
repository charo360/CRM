"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { setToken, setUser } from "@/lib/auth";
import { ZiloLogo } from "@/components/ZiloLogo";
import {
  Zap,
  Loader2,
  Phone,
  Copy,
  CheckCircle2,
  RefreshCw,
  Mail,
  Lock,
  Building2,
  User,
  Eye,
  EyeOff,
  MessageSquare,
  BarChart2,
  Sparkles,
} from "lucide-react";

const LOGIN_HERO_IMAGE =
  "https://images.unsplash.com/photo-1522071820081-009f0129c71c?auto=format&fit=crop&w=1600&q=80";

const LOGIN_FEATURES = [
  { icon: MessageSquare, text: "Auto-replies across WhatsApp, email, and social" },
  { icon: BarChart2, text: "Orders, invoices, and payments in one workspace" },
  { icon: Sparkles, text: "AI-assisted marketing, ads, and follow-ups" },
] as const;

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
  const [showPassword, setShowPassword] = useState(false);
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
      const next =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("next") || "/dashboard"
          : "/dashboard";
      router.push(res.must_change_password ? "/change-password" : next);
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

  const inputClass =
    "w-full py-2.5 text-sm border border-slate-200 rounded-lg outline-none focus:border-[#009B3A] transition-colors";
  const inputWithIconClass = `${inputClass} pl-9 pr-3`;

  return (
    <div className="min-h-screen flex">
      <aside className="relative hidden lg:flex lg:w-[44%] xl:w-1/2 flex-col justify-between p-10 xl:p-14 text-white overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url('${LOGIN_HERO_IMAGE}')` }}
        />
        <div className="absolute inset-0 bg-slate-950/78" />

        <div className="relative z-10">
          <div className="flex items-center gap-2">
            <ZiloLogo size={40} className="shrink-0" priority />
            <span className="text-xl font-semibold tracking-tight">Zilo</span>
          </div>
        </div>

        <div className="relative z-10 max-w-md space-y-8">
          <div>
            {/* <p className="text-xs font-medium uppercase tracking-widest text-white/60 mb-3">Web workspace</p> */}
            <h1 className="text-3xl xl:text-4xl font-semibold leading-tight tracking-tight">
              Sell on every{" "}
              <span className="text-brand">channel</span>. Run everything from one{" "}
              <span className="text-brand">place</span>.
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-white/75">
              Sign in to manage conversations, orders, marketing, and AI tools — without jumping between apps.
            </p>
          </div>

          <ul className="space-y-4">
            {LOGIN_FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-sm text-white/85">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/20 bg-white/10">
                  <Icon size={16} className="text-[#4CD137]" />
                </span>
                <span className="leading-snug pt-1">{text}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-xs text-white/40">
          {/* Photo{" "} */}
          <a
            href="https://unsplash.com/photos/5fNmWej4tAA"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-white/60"
          >
            {/* Unsplash */}
          </a>
        </p>
      </aside>

      <main className="flex flex-1 flex-col min-h-screen bg-white">
        <div className="flex flex-1 items-center justify-center px-6 py-10 sm:px-10">
          <div className="w-full max-w-sm">
            <div className="mb-8 flex flex-col items-center lg:items-start">
              <div className="flex items-center gap-2">
                <ZiloLogo size={40} className="shrink-0" priority />
                <h1 className="text-2xl font-semibold leading-none text-slate-900">Zilo</h1>
              </div>
              <p className="mt-2 text-sm text-slate-500 text-center lg:text-left">
                Web workspace · Sell on every channel · AI
              </p>
            </div>

            <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1 mb-6">
              <button
                type="button"
                onClick={() => {
                  setMode("email");
                  setError("");
                }}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                  mode === "email"
                    ? "bg-white text-slate-900 border border-slate-200"
                    : "text-slate-600 hover:text-slate-800 border border-transparent"
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
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                  mode === "whatsapp"
                    ? "bg-white text-slate-900 border border-slate-200"
                    : "text-slate-600 hover:text-slate-800 border border-transparent"
                }`}
              >
                WhatsApp
              </button>
            </div>

            <div className="space-y-4">
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
                        className={inputWithIconClass}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Password</label>
                    <div className="relative">
                      <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type={showPassword ? "text" : "password"}
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => {
                          setPassword(e.target.value);
                          setError("");
                        }}
                        required
                        className={`${inputWithIconClass} pr-10`}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>
                  {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#007a2e] bg-[#009B3A] py-2.5 text-sm font-medium text-white transition hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-60"
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
                      className={`${inputClass} px-3`}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">Password (min 8 characters)</label>
                    <div className="relative">
                      <input
                        type={showPassword ? "text" : "password"}
                        autoComplete="new-password"
                        value={password}
                        onChange={(e) => {
                          setPassword(e.target.value);
                          setError("");
                        }}
                        required
                        minLength={8}
                        className={`${inputClass} px-3 pr-10`}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
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
                      className={`${inputClass} px-3`}
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
                      className={`${inputClass} px-3`}
                    />
                  </div>
                  {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#007a2e] bg-[#009B3A] py-2.5 text-sm font-medium text-white transition hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-60"
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
                    className={`${inputWithIconClass} placeholder:text-slate-400`}
                  />
                </div>
                <p className="text-xs text-slate-400 mt-1">Include country code, e.g. +1</p>
              </div>
              {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#007a2e] bg-[#009B3A] py-2.5 text-sm font-medium text-white transition hover:bg-[#4CD137] hover:text-[#0a2614] disabled:opacity-60"
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
                  className="flex-1 rounded-lg border border-[#007a2e] bg-[#009B3A] py-2 text-sm font-medium text-white transition hover:bg-[#4CD137] hover:text-[#0a2614]"
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

            <p className="text-center lg:text-left text-xs text-slate-400 mt-8">
              Kitchen Display?{" "}
              <a href="/kds" className="font-medium text-[#009B3A] hover:underline">
                Open KDS
              </a>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

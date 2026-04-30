"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { getToken, getUser, setUser, clearToken } from "@/lib/auth";
import { ZiloLogo } from "@/components/ZiloLogo";
import { Lock, Eye, EyeOff, CheckCircle2, Loader2 } from "lucide-react";

const REQUIREMENTS = [
  { label: "At least 8 characters", test: (p: string) => p.length >= 8 },
  { label: "Contains a number", test: (p: string) => /\d/.test(p) },
  { label: "Contains a letter", test: (p: string) => /[a-zA-Z]/.test(p) },
];

export default function ChangePasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  const allMet = REQUIREMENTS.every(r => r.test(password));
  const matches = password === confirm && confirm.length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!allMet) return;
    if (!matches) { setError("Passwords do not match"); return; }
    setLoading(true);
    setError("");
    try {
      await authApi.changePassword(password);
      const user = getUser();
      if (user) setUser({ ...user, must_change_password: false });
      setDone(true);
      setTimeout(() => router.replace("/dashboard"), 1800);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update password");
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="text-center space-y-3">
          <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto">
            <CheckCircle2 size={32} className="text-green-600" />
          </div>
          <h2 className="text-xl font-bold text-slate-900">Password updated!</h2>
          <p className="text-slate-500 text-sm">Taking you to the dashboard…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <ZiloLogo className="h-8 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-slate-900">Set your password</h1>
          <p className="text-slate-500 text-sm mt-2">
            You were added with a temporary password. Please set a new one before continuing.
          </p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-5">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">New password</label>
              <div className="relative">
                <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                  required
                  className="w-full pl-9 pr-10 py-2.5 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-brand focus:border-brand"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Confirm password</label>
              <div className="relative">
                <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type={showPassword ? "text" : "password"}
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  placeholder="Repeat password"
                  required
                  className={`w-full pl-9 pr-3 py-2.5 text-sm border rounded-lg focus:ring-2 focus:ring-brand focus:border-brand ${
                    confirm && !matches ? "border-red-300" : "border-slate-200"
                  }`}
                />
              </div>
              {confirm && !matches && (
                <p className="text-xs text-red-500 mt-1">Passwords do not match</p>
              )}
            </div>

            {/* Requirements checklist */}
            <ul className="space-y-1.5">
              {REQUIREMENTS.map(r => (
                <li key={r.label} className={`flex items-center gap-2 text-xs ${r.test(password) ? "text-green-600" : "text-slate-400"}`}>
                  <CheckCircle2 size={13} className={r.test(password) ? "text-green-500" : "text-slate-300"} />
                  {r.label}
                </li>
              ))}
            </ul>

            {error && (
              <p className="text-sm text-red-500 bg-red-50 rounded-lg px-3 py-2">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading || !allMet || !matches}
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-brand-dark text-white font-semibold rounded-xl hover:bg-brand disabled:opacity-50 text-sm transition-colors"
            >
              {loading && <Loader2 size={15} className="animate-spin" />}
              Set Password & Continue
            </button>
          </form>

          <button
            onClick={() => { clearToken(); router.replace("/login"); }}
            className="w-full text-center text-xs text-slate-400 hover:text-slate-600 transition-colors"
          >
            Sign out and log in as a different account
          </button>
        </div>
      </div>
    </div>
  );
}

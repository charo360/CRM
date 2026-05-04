"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { adminApi } from "@/lib/api";
import { Shield } from "lucide-react";

export default function AdminLoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await adminApi.login(password);
      router.replace("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-md bg-white border border-slate-200 rounded-2xl p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-brand/10 flex items-center justify-center">
            <Shield className="text-brand-dark" size={18} />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Admin Login</h1>
            <p className="text-xs text-slate-500">Separate access for platform administrators</p>
          </div>
        </div>

        <div>
          <label className="text-sm text-slate-700 font-medium block mb-1">Admin password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
            placeholder="Enter admin password"
            autoFocus
          />
        </div>

        {error && (
          <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !password.trim()}
          className="w-full py-2.5 rounded-lg bg-brand-dark text-white text-sm font-semibold disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign in to Admin"}
        </button>
      </form>
    </div>
  );
}


"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Monitor, Loader2 } from "lucide-react";

// The PIN is stored in env. Businesses set their KDS PIN in settings.
// For now we resolve it client-side against NEXT_PUBLIC_KDS_PIN.
// In production this should hit /api/kds/verify endpoint.
const KDS_PIN = process.env.NEXT_PUBLIC_KDS_PIN || "1234";

export default function KDSGatePage() {
  const router = useRouter();
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function handleDigit(d: string) {
    if (pin.length >= 6) return;
    const next = pin + d;
    setPin(next);
    setError("");
    if (next.length >= KDS_PIN.length) {
      verify(next);
    }
  }

  function handleDelete() {
    setPin((p) => p.slice(0, -1));
    setError("");
  }

  function verify(code: string) {
    setLoading(true);
    setTimeout(() => {
      if (code === KDS_PIN) {
        router.push("/kds/board");
      } else {
        setError("Wrong PIN. Try again.");
        setPin("");
      }
      setLoading(false);
    }, 300);
  }

  const digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"];

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center gap-8 px-4">
      <div className="flex flex-col items-center gap-3">
        <div className="w-14 h-14 rounded-2xl bg-brand-dark flex items-center justify-center">
          <Monitor size={28} className="text-white" />
        </div>
        <h1 className="text-2xl font-bold text-white">Kitchen Display</h1>
        <p className="text-slate-400 text-sm">Enter PIN to access</p>
      </div>

      {/* PIN dots */}
      <div className="flex gap-3">
        {Array.from({ length: KDS_PIN.length }).map((_, i) => (
          <div
            key={i}
            className={`w-4 h-4 rounded-full transition-colors ${
              i < pin.length ? "bg-brand" : "bg-slate-700"
            }`}
          />
        ))}
      </div>

      {error && (
        <p className="text-red-400 text-sm font-medium">{error}</p>
      )}

      {/* Numpad */}
      <div className="grid grid-cols-3 gap-3 w-56">
        {digits.map((d, i) => {
          if (d === "") return <div key={i} />;
          const isDelete = d === "⌫";
          return (
            <button
              key={i}
              onClick={() => (isDelete ? handleDelete() : handleDigit(d))}
              disabled={loading}
              className={`h-14 rounded-xl text-lg font-semibold transition-colors ${
                isDelete
                  ? "bg-slate-800 text-slate-400 hover:bg-slate-700"
                  : "bg-slate-800 text-white hover:bg-slate-700 active:bg-brand-dark"
              }`}
            >
              {loading && !isDelete ? <Loader2 size={18} className="animate-spin mx-auto" /> : d}
            </button>
          );
        })}
      </div>

      <p className="text-slate-600 text-xs mt-4">
        No login required · Staff view only
      </p>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { use } from "react";
import { CheckCircle, XCircle, Eye, FileText, Loader2, AlertCircle } from "lucide-react";

interface DealData {
  title: string;
  file_url: string;
  recipient_name?: string;
  token: string;
  status: string;
}

export default function DealRoomViewer({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [deal, setDeal] = useState<DealData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [signing, setSigning] = useState(false);
  const [signed, setSigned] = useState(false);

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

  useEffect(() => {
    fetch(`${API_BASE}/growth/deal/${token}/view`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(d => { setDeal(d); if (d.status === "signed") setSigned(true); })
      .catch(e => setError(e === 410 ? "This link has expired." : "Deal not found."))
      .finally(() => setLoading(false));
  }, [token]);

  async function sign() {
    setSigning(true);
    try {
      await fetch(`${API_BASE}/growth/deal/${token}/sign`, { method: "POST" });
      setSigned(true);
      setDeal(d => d ? { ...d, status: "signed" } : d);
    } catch { } finally { setSigning(false); }
  }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <Loader2 size={32} className="text-slate-400 animate-spin" />
    </div>
  );

  if (error || !deal) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="text-center">
        <AlertCircle size={40} className="mx-auto text-slate-300 mb-3" />
        <p className="text-slate-600 font-medium">{error || "Not found"}</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="font-bold text-slate-900 text-lg">{deal.title}</h1>
            {deal.recipient_name && (
              <p className="text-sm text-slate-500 mt-0.5">For {deal.recipient_name}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {signed ? (
              <span className="flex items-center gap-1.5 text-sm font-medium text-emerald-600 bg-emerald-50 px-3 py-1.5 rounded-lg">
                <CheckCircle size={15} /> Signed
              </span>
            ) : (
              <button onClick={sign} disabled={signing}
                className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 font-medium disabled:opacity-50">
                {signing ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
                Sign & Accept
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Document preview */}
      <div className="max-w-4xl mx-auto p-6">
        {deal.file_url ? (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
            <iframe
              src={deal.file_url}
              className="w-full"
              style={{ height: "80vh" }}
              title={deal.title}
            />
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 p-16 text-center">
            <FileText size={40} className="mx-auto text-slate-300 mb-3" />
            <p className="text-slate-500">Document preview unavailable</p>
          </div>
        )}

        {/* Footer */}
        {!signed && (
          <div className="mt-6 bg-white rounded-xl border border-slate-200 p-5 flex items-center justify-between">
            <div>
              <p className="font-semibold text-slate-800 text-sm">Ready to proceed?</p>
              <p className="text-xs text-slate-500 mt-0.5">By signing, you accept the terms outlined in this document.</p>
            </div>
            <button onClick={sign} disabled={signing}
              className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 text-white text-sm rounded-lg hover:bg-emerald-700 font-semibold disabled:opacity-50">
              {signing ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
              Sign & Accept
            </button>
          </div>
        )}

        {signed && (
          <div className="mt-6 bg-emerald-50 border border-emerald-100 rounded-xl p-5 text-center">
            <CheckCircle size={28} className="mx-auto text-emerald-500 mb-2" />
            <p className="font-semibold text-emerald-800">Document signed successfully</p>
            <p className="text-sm text-emerald-600 mt-1">The sender has been notified.</p>
          </div>
        )}
      </div>
    </div>
  );
}

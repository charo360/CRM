"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Zap, Check, X, Edit2, Send, RefreshCw, Loader2, Phone, MessageSquare } from "lucide-react";

interface QueueItem {
  customer_id: string;
  customer_name: string;
  phone: string;
  days_since_contact: number;
  draft_message: string;
  channel: string;
}

export default function AutopilotPage() {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [processing, setProcessing] = useState<Record<string, boolean>>({});
  const [done, setDone] = useState<Set<string>>(new Set());

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const data = await api.get<{ queue: QueueItem[] }>("/growth/autopilot/queue");
      setQueue(data.queue);
    } catch { } finally { setLoading(false); }
  }

  async function handleAction(item: QueueItem, action: "approve" | "skip" | "edit") {
    setProcessing(p => ({ ...p, [item.customer_id]: true }));
    try {
      await api.post("/growth/autopilot/action", {
        customer_id: item.customer_id,
        action,
        message: action === "edit" ? editing[item.customer_id] : item.draft_message,
      });
      setDone(d => new Set([...d, item.customer_id]));
    } catch { } finally {
      setProcessing(p => ({ ...p, [item.customer_id]: false }));
    }
  }

  const visible = queue.filter(i => !done.has(i.customer_id));

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Zap size={22} className="text-amber-500" /> Follow-up Autopilot
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            AI-drafted re-engagement messages for cold leads. Approve to send, edit to customize, or skip.
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50">
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse h-32" />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
          <div className="w-12 h-12 bg-emerald-50 rounded-full flex items-center justify-center mx-auto mb-3">
            <Check size={22} className="text-emerald-500" />
          </div>
          <p className="font-semibold text-slate-800">All caught up!</p>
          <p className="text-sm text-slate-500 mt-1">No cold leads need follow-up right now.</p>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-500">{visible.length} customer{visible.length !== 1 ? "s" : ""} need re-engagement</p>
          {visible.map((item) => {
            const isEditing = item.customer_id in editing;
            const msg = isEditing ? editing[item.customer_id] : item.draft_message;
            const busy = processing[item.customer_id];
            return (
              <div key={item.customer_id} className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-semibold text-slate-800">{item.customer_name}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      {item.phone && (
                        <span className="text-xs text-slate-400 flex items-center gap-1">
                          <Phone size={10} /> {item.phone}
                        </span>
                      )}
                      <span className="text-xs text-orange-500 font-medium">
                        {item.days_since_contact}d since last contact
                      </span>
                    </div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    item.channel === "whatsapp" ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"
                  }`}>
                    {item.channel === "whatsapp" ? "WhatsApp" : "Email"}
                  </span>
                </div>

                {/* Draft message */}
                {isEditing ? (
                  <textarea
                    value={msg}
                    onChange={e => setEditing(ed => ({ ...ed, [item.customer_id]: e.target.value }))}
                    className="w-full text-sm border border-slate-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-brand/30"
                    rows={3}
                  />
                ) : (
                  <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 leading-relaxed">{msg}</p>
                )}

                {/* Actions */}
                <div className="flex items-center gap-2">
                  {isEditing ? (
                    <>
                      <button
                        onClick={() => handleAction(item, "edit")}
                        disabled={busy}
                        className="flex items-center gap-1.5 px-4 py-1.5 bg-brand-dark text-white text-xs rounded-lg hover:bg-brand disabled:opacity-50 font-medium"
                      >
                        {busy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                        Send Edited
                      </button>
                      <button
                        onClick={() => setEditing(ed => { const n = { ...ed }; delete n[item.customer_id]; return n; })}
                        className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => handleAction(item, "approve")}
                        disabled={busy}
                        className="flex items-center gap-1.5 px-4 py-1.5 bg-brand-dark text-white text-xs rounded-lg hover:bg-brand disabled:opacity-50 font-medium"
                      >
                        {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                        Approve & Send
                      </button>
                      <button
                        onClick={() => setEditing(ed => ({ ...ed, [item.customer_id]: item.draft_message }))}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
                      >
                        <Edit2 size={11} /> Edit
                      </button>
                      <button
                        onClick={() => handleAction(item, "skip")}
                        disabled={busy}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-500"
                      >
                        <X size={11} /> Skip (7d)
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

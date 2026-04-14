"use client";

import { useEffect, useState } from "react";
import { broadcastApi, Broadcast, BroadcastTemplate } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/utils";
import { Megaphone, Plus, Trash2, Send, Users, CheckCircle2, Clock, X, Loader2 } from "lucide-react";

const AUDIENCE_FILTERS = [
  { id: "all", label: "All Customers", desc: "Everyone in your CRM" },
  { id: "new", label: "New Customers", desc: "Joined in the last 30 days" },
  { id: "returning", label: "Returning", desc: "2+ purchases" },
  { id: "vip", label: "VIP Only", desc: "Tagged as VIP" },
];

const STATUS_COLORS: Record<string, string> = {
  sent:      "bg-green-100 text-green-700",
  scheduled: "bg-blue-100 text-blue-700",
  draft:     "bg-slate-100 text-slate-600",
  failed:    "bg-red-100 text-red-600",
};

export default function BroadcastPage() {
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [templates, setTemplates] = useState<BroadcastTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCompose, setShowCompose] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    filter_type: "all",
    message: "",
    name: "",
    scheduled_at: "",
  });

  async function load() {
    setLoading(true);
    try {
      const [b, t] = await Promise.all([broadcastApi.list(), broadcastApi.templates()]);
      setBroadcasts(b);
      setTemplates(t);
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!form.message.trim()) return;
    setSaving(true);
    try {
      await broadcastApi.create({
        message: form.message,
        filter_type: form.filter_type,
        name: form.name || undefined,
        scheduled_at: form.scheduled_at || undefined,
      });
      setShowCompose(false);
      setForm({ filter_type: "all", message: "", name: "", scheduled_at: "" });
      await load();
    } finally { setSaving(false); }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this broadcast?")) return;
    await broadcastApi.delete(id);
    await load();
  }

  function applyTemplate(t: BroadcastTemplate) {
    setForm((f) => ({ ...f, message: t.message }));
  }

  const totalSent = broadcasts.reduce((s, b) => s + (b.sent_count || 0), 0);
  const totalRecipients = broadcasts.reduce((s, b) => s + (b.recipients_count || 0), 0);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Broadcast</h1>
          <p className="text-slate-500 text-sm mt-1">
            Send bulk messages to your customers via WhatsApp
          </p>
        </div>
        <button
          onClick={() => setShowCompose(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700"
        >
          <Plus size={15} /> New Broadcast
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <Stat label="Total Broadcasts" value={broadcasts.length} icon={Megaphone} color="text-indigo-600" bg="bg-indigo-50" />
        <Stat label="Messages Sent" value={totalSent} icon={Send} color="text-green-600" bg="bg-green-50" />
        <Stat label="Total Reached" value={totalRecipients} icon={Users} color="text-blue-600" bg="bg-blue-50" />
      </div>

      {/* Broadcasts list */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-900">Sent Broadcasts</h2>
        </div>
        {loading ? (
          <div className="divide-y divide-slate-100">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="px-5 py-4 animate-pulse">
                <div className="h-4 bg-slate-100 rounded w-1/2 mb-2" />
                <div className="h-3 bg-slate-100 rounded w-3/4" />
              </div>
            ))}
          </div>
        ) : broadcasts.length === 0 ? (
          <div className="flex flex-col items-center py-16 gap-3 text-slate-400">
            <Megaphone size={36} />
            <p className="text-sm">No broadcasts yet. Send your first one!</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {broadcasts.map((b) => (
              <div key={b.id} className="px-5 py-4 flex items-start gap-4 hover:bg-slate-50">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    {b.name && <p className="font-semibold text-slate-800 text-sm">{b.name}</p>}
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[b.status] || STATUS_COLORS.draft}`}>
                      {b.status}
                    </span>
                    <span className="text-xs text-slate-400 capitalize">{b.filter_type} audience</span>
                  </div>
                  <p className="text-sm text-slate-600 line-clamp-2">{b.message}</p>
                  <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                    <span className="flex items-center gap-1">
                      <Users size={11} /> {b.recipients_count} recipients
                    </span>
                    <span className="flex items-center gap-1">
                      <CheckCircle2 size={11} className="text-green-500" /> {b.sent_count} sent
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock size={11} /> {timeAgo(b.created_at)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(b.id)}
                  className="text-slate-300 hover:text-red-500 transition-colors shrink-0 mt-0.5"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Compose modal */}
      {showCompose && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 sticky top-0 bg-white">
              <h3 className="font-bold text-slate-900">New Broadcast</h3>
              <button onClick={() => setShowCompose(false)}><X size={20} className="text-slate-400" /></button>
            </div>
            <form onSubmit={handleSend} className="p-6 space-y-5">
              {/* Name */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Campaign name (optional)</label>
                <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. June Promo" className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>

              {/* Audience */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-2">Audience</label>
                <div className="grid grid-cols-2 gap-2">
                  {AUDIENCE_FILTERS.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, filter_type: a.id }))}
                      className={`text-left px-3 py-2.5 rounded-xl border transition-colors ${
                        form.filter_type === a.id ? "border-indigo-500 bg-indigo-50" : "border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <p className="text-sm font-medium text-slate-800">{a.label}</p>
                      <p className="text-xs text-slate-400">{a.desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Templates */}
              {templates.length > 0 && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-2">Use a template</label>
                  <div className="flex gap-2 flex-wrap">
                    {templates.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => applyTemplate(t)}
                        className="px-3 py-1.5 text-xs font-medium border border-slate-200 rounded-lg hover:bg-indigo-50 hover:border-indigo-300 text-slate-700 transition-colors"
                      >
                        {t.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Message */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Message *</label>
                <textarea
                  value={form.message}
                  onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
                  required
                  rows={5}
                  placeholder="Type your message here… You can use {name} to personalise."
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
                <p className="text-xs text-slate-400 mt-1">{form.message.length} characters</p>
              </div>

              {/* Schedule */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Schedule (optional)</label>
                <input
                  type="datetime-local"
                  value={form.scheduled_at}
                  onChange={(e) => setForm((f) => ({ ...f, scheduled_at: e.target.value }))}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <p className="text-xs text-slate-400 mt-1">Leave empty to send immediately</p>
              </div>

              <button type="submit" disabled={saving || !form.message.trim()}
                className="w-full flex items-center justify-center gap-2 py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm">
                {saving && <Loader2 size={15} className="animate-spin" />}
                {form.scheduled_at ? "Schedule Broadcast" : "Send Now"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, icon: Icon, color, bg }: { label: string; value: number; icon: React.ElementType; color: string; bg: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm text-slate-500 font-medium">{label}</p>
        <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
          <Icon size={16} className={color} />
        </div>
      </div>
      <p className="text-2xl font-bold text-slate-900">{value.toLocaleString()}</p>
    </div>
  );
}

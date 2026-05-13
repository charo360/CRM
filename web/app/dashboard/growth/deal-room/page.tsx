"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Target, Plus, Eye, CheckCircle, XCircle, Clock, Copy, ExternalLink, Loader2, FileText, AlertCircle } from "lucide-react";

interface DealRoom {
  _id: string;
  title: string;
  token: string;
  recipient_name?: string;
  recipient_email?: string;
  status: string;
  views: number;
  created_at: string;
  expires_at: string;
  signed_at?: string;
}

const STATUS_STYLES: Record<string, string> = {
  sent: "bg-blue-100 text-blue-700",
  viewed: "bg-amber-100 text-amber-700",
  signed: "bg-emerald-100 text-emerald-700",
  declined: "bg-rose-100 text-rose-700",
};

const STATUS_ICONS: Record<string, React.ElementType> = {
  sent: Clock,
  viewed: Eye,
  signed: CheckCircle,
  declined: XCircle,
};

export default function DealRoomPage() {
  const [rooms, setRooms] = useState<DealRoom[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    title: "",
    description: "",
    recipient_name: "",
    recipient_email: "",
    file_url: "",
    expires_days: 30,
  });

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<{ deal_rooms: DealRoom[] }>("/growth/deal-room");
      setRooms(r.deal_rooms);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load deal rooms");
    } finally { setLoading(false); }
  }

  async function create() {
    if (!form.title.trim()) return;
    setCreating(true);
    setError("");
    try {
      await api.post("/growth/deal-room", form);
      setShowForm(false);
      setForm({ title: "", description: "", recipient_name: "", recipient_email: "", file_url: "", expires_days: 30 });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create deal room");
    } finally { setCreating(false); }
  }

  function copyLink(token: string) {
    const url = `${window.location.origin}/deal/${token}`;
    navigator.clipboard.writeText(url);
    setCopied(token);
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Target size={22} className="text-blue-500" /> Deal Room
          </h1>
          <p className="text-sm text-slate-500 mt-1">Share proposals with clients and track when they view and sign.</p>
        </div>
        <button onClick={() => { setShowForm(true); setError(""); }}
          className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm rounded-lg hover:bg-brand font-medium">
          <Plus size={15} /> New Deal Room
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3">
          <AlertCircle size={15} className="shrink-0" /> {error}
        </div>
      )}

      {/* Create form */}
      {showForm && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
          <h3 className="font-semibold text-slate-800">Create Deal Room</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2">
              <label className="text-xs font-medium text-slate-600 block mb-1">Deal Title *</label>
              <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                placeholder="e.g. Proposal for BlueLine Co."
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/30" />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs font-medium text-slate-600 block mb-1">Description / Message <span className="text-slate-400 font-normal">(optional)</span></label>
              <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Brief summary or terms for the client…"
                rows={2}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/30 resize-none" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Recipient Name <span className="text-slate-400 font-normal">(optional)</span></label>
              <input value={form.recipient_name} onChange={e => setForm(f => ({ ...f, recipient_name: e.target.value }))}
                placeholder="John Smith"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/30" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Recipient Email <span className="text-slate-400 font-normal">(optional)</span></label>
              <input value={form.recipient_email} onChange={e => setForm(f => ({ ...f, recipient_email: e.target.value }))}
                placeholder="john@company.com"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/30" />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs font-medium text-slate-600 block mb-1">Document / File URL <span className="text-slate-400 font-normal">(optional — paste a link to a PDF, Google Doc, etc.)</span></label>
              <input value={form.file_url} onChange={e => setForm(f => ({ ...f, file_url: e.target.value }))}
                placeholder="https://docs.google.com/… or any file link"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/30" />
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <button onClick={create} disabled={creating || !form.title.trim()}
              className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm rounded-lg hover:bg-brand disabled:opacity-50 font-medium">
              {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Create & Get Link
            </button>
            <button onClick={() => { setShowForm(false); setError(""); }}
              className="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Deal rooms list */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse h-20" />
          ))}
        </div>
      ) : rooms.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-10 text-center">
          <FileText size={32} className="mx-auto text-slate-300 mb-3" />
          <p className="font-semibold text-slate-700">No deal rooms yet</p>
          <p className="text-sm text-slate-400 mt-1">Create one to share a proposal with a client.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {rooms.map(room => {
            const StatusIcon = STATUS_ICONS[room.status] || Clock;
            return (
              <div key={room._id} className="bg-white rounded-xl border border-slate-200 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-slate-800 truncate">{room.title}</p>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex items-center gap-1 shrink-0 ${STATUS_STYLES[room.status] || "bg-slate-100 text-slate-500"}`}>
                        <StatusIcon size={10} /> {room.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 mt-1">
                      {room.recipient_name && (
                        <span className="text-xs text-slate-500">To: {room.recipient_name}</span>
                      )}
                      <span className="text-xs text-slate-400 flex items-center gap-1">
                        <Eye size={10} /> {room.views} view{room.views !== 1 ? "s" : ""}
                      </span>
                      <span className="text-xs text-slate-400">
                        Expires {new Date(room.expires_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button onClick={() => copyLink(room.token)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                      <Copy size={11} /> {copied === room.token ? "Copied!" : "Copy Link"}
                    </button>
                    <a href={`/deal/${room.token}`} target="_blank" rel="noopener noreferrer"
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                      <ExternalLink size={11} /> Preview
                    </a>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { broadcastApi, Broadcast, BroadcastTemplate, BroadcastAutomation, aiApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import {
  Megaphone, Plus, Trash2, Send, Clock, CheckCircle2, Loader2,
  Sparkles, Copy, Edit, Play, Pause, RotateCcw
} from "lucide-react";

type Tab = "broadcasts" | "templates" | "automations";
type StatusConfig = Record<string, { label: string; color: string; icon: React.ElementType }>;

export default function BroadcastPage() {
  const [activeTab, setActiveTab] = useState<Tab>("broadcasts");
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [templates, setTemplates] = useState<BroadcastTemplate[]>([]);
  const [automations, setAutomations] = useState<BroadcastAutomation[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [form, setForm] = useState({
    name: "",
    message: "",
    filter_type: "all_customers",
    scheduled_at: "",
  });

  useEffect(() => {
    loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  async function loadData() {
    setLoading(true);
    try {
      if (activeTab === "broadcasts") {
        const data = await broadcastApi.list();
        setBroadcasts(data);
      } else if (activeTab === "templates") {
        const data = await broadcastApi.templates();
        setTemplates(data);
      } else if (activeTab === "automations") {
        const data = await broadcastApi.automations();
        setAutomations(data);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleAIDraft() {
    if (!form.filter_type) return;
    setDrafting(true);
    try {
      const response = await aiApi.draftMessage({
        customer_id: "broadcast",
        custom_instructions: `Create a broadcast message for ${form.filter_type.replace("_", " ")}`,
        tone: "friendly",
      });
      setForm(f => ({ ...f, message: response.message }));
    } catch (e) {
      console.error("Failed to generate AI draft:", e);
      alert("Failed to generate AI draft");
    } finally {
      setDrafting(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await broadcastApi.create(form);
      setShowCreate(false);
      setForm({ name: "", message: "", filter_type: "all_customers", scheduled_at: "" });
      await loadData();
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this item?")) return;
    try {
      if (activeTab === "broadcasts") {
        await broadcastApi.delete(id);
      } else if (activeTab === "templates") {
        await broadcastApi.deleteTemplate(id);
      } else if (activeTab === "automations") {
        await broadcastApi.deleteAutomation(id);
      }
      await loadData();
    } catch (e) {
      console.error("Failed to delete:", e);
      alert("Failed to delete");
    }
  }

  async function handleResend(id: string) {
    try {
      await broadcastApi.resend(id);
      alert("Broadcast resent successfully!");
      await loadData();
    } catch (e) {
      console.error("Failed to resend:", e);
      alert("Failed to resend broadcast");
    }
  }

  const statusConfig: StatusConfig = {
    pending: { label: "Pending", color: "bg-yellow-100 text-yellow-700", icon: Clock },
    sending: { label: "Sending", color: "bg-blue-100 text-blue-700", icon: Send },
    completed: { label: "Completed", color: "bg-green-100 text-green-700", icon: CheckCircle2 },
    failed: { label: "Failed", color: "bg-red-100 text-red-700", icon: Trash2 },
    active: { label: "Active", color: "bg-green-100 text-green-700", icon: Play },
    paused: { label: "Paused", color: "bg-gray-100 text-gray-700", icon: Pause },
  };

  const tabs = [
    { id: "broadcasts" as Tab, label: "Broadcasts", count: broadcasts.length },
    { id: "templates" as Tab, label: "Templates", count: templates.length },
    { id: "automations" as Tab, label: "Automations", count: automations.length },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Broadcast Center</h1>
          <p className="text-slate-500 text-sm mt-1">Manage bulk messaging, templates, and automations</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus size={15} /> New {activeTab.slice(0, -1)}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {tabs.map(({ id, label, count }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === id
                ? "bg-white border-b-2 border-indigo-600 text-indigo-600"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {label} ({count})
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {activeTab === "broadcasts" && (
          <BroadcastsTable
            broadcasts={broadcasts}
            loading={loading}
            onDelete={handleDelete}
            onResend={handleResend}
            statusConfig={statusConfig}
          />
        )}
        {activeTab === "templates" && (
          <TemplatesTable
            templates={templates}
            loading={loading}
            onDelete={handleDelete}
            onUse={(template) => {
              setForm(f => ({ ...f, message: template.message, name: template.name ?? "" }));
              setShowCreate(true);
            }}
          />
        )}
        {activeTab === "automations" && (
          <AutomationsTable
            automations={automations}
            loading={loading}
            onDelete={handleDelete}
            statusConfig={statusConfig}
          />
        )}
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">Create {activeTab.slice(0, -1)}</h3>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-600 text-xl">
                ×
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Campaign name"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
                />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-sm font-medium text-slate-700">Message *</label>
                  <button
                    type="button"
                    onClick={handleAIDraft}
                    disabled={drafting}
                    className="flex items-center gap-1 text-xs text-purple-600 hover:text-purple-700 disabled:opacity-50"
                  >
                    <Sparkles size={12} className={drafting ? "animate-spin" : ""} />
                    AI Draft
                  </button>
                </div>
                <textarea
                  value={form.message}
                  onChange={(e) => setForm(f => ({ ...f, message: e.target.value }))}
                  placeholder="Type your message here… You can use {name} to personalise."
                  required
                  rows={5}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
                <p className="text-xs text-slate-400 mt-1">{form.message.length} characters</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Schedule (optional)</label>
                <input
                  type="datetime-local"
                  value={form.scheduled_at}
                  onChange={(e) => setForm(f => ({ ...f, scheduled_at: e.target.value }))}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <p className="text-xs text-slate-400 mt-1">Leave empty to send immediately</p>
              </div>

              <button
                type="submit"
                disabled={creating || !form.message.trim()}
                className="w-full flex items-center justify-center gap-2 py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 disabled:opacity-50 text-sm"
              >
                {creating && <Loader2 size={15} className="animate-spin" />}
                {form.scheduled_at ? "Schedule Broadcast" : "Send Now"}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function BroadcastsTable({
  broadcasts,
  loading,
  onDelete,
  onResend,
  statusConfig,
}: {
  broadcasts: Broadcast[];
  loading: boolean;
  onDelete: (id: string) => void;
  onResend: (id: string) => void;
  statusConfig: StatusConfig;
}) {
  if (loading) return <div className="p-8 text-center text-slate-400"><Loader2 className="animate-spin mx-auto" /></div>;
  if (!broadcasts.length) return <div className="p-8 text-center text-slate-400">No broadcasts yet. Create one to get started.</div>;

  return (
    <table className="w-full text-sm">
      <thead className="bg-slate-50 border-b border-slate-200">
        <tr>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Name</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Recipients</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Status</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Sent</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Created</th>
          <th className="px-4 py-3" />
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {broadcasts.map((b) => {
          const cfg = statusConfig[b.status] ?? { label: b.status, color: "bg-slate-100 text-slate-600", icon: Clock };
          const Icon = cfg.icon;
          return (
            <tr key={b.id} className="hover:bg-slate-50">
              <td className="px-4 py-3 font-medium text-slate-800">{b.name || "Untitled"}</td>
              <td className="px-4 py-3 text-slate-600">{b.recipients_count}</td>
              <td className="px-4 py-3">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
                  <Icon size={11} /> {cfg.label}
                </span>
              </td>
              <td className="px-4 py-3 text-slate-600">{b.sent_count}</td>
              <td className="px-4 py-3 text-slate-400">{formatDate(b.created_at)}</td>
              <td className="px-4 py-3">
                <div className="flex gap-1 justify-end">
                  <button onClick={() => onResend(b.id)} className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-100 hover:text-indigo-600" title="Resend">
                    <RotateCcw size={13} />
                  </button>
                  <button onClick={() => onDelete(b.id)} className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600" title="Delete">
                    <Trash2 size={13} />
                  </button>
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function TemplatesTable({
  templates,
  loading,
  onDelete,
  onUse,
}: {
  templates: BroadcastTemplate[];
  loading: boolean;
  onDelete: (id: string) => void;
  onUse: (template: BroadcastTemplate) => void;
}) {
  if (loading) return <div className="p-8 text-center text-slate-400"><Loader2 className="animate-spin mx-auto" /></div>;
  if (!templates.length) return <div className="p-8 text-center text-slate-400">No templates yet.</div>;

  return (
    <table className="w-full text-sm">
      <thead className="bg-slate-50 border-b border-slate-200">
        <tr>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Name</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Preview</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Created</th>
          <th className="px-4 py-3" />
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {templates.map((t) => (
          <tr key={t.id} className="hover:bg-slate-50">
            <td className="px-4 py-3 font-medium text-slate-800">{t.name}</td>
            <td className="px-4 py-3 text-slate-500 max-w-xs truncate">{t.message}</td>
            <td className="px-4 py-3 text-slate-400">{formatDate(t.created_at)}</td>
            <td className="px-4 py-3">
              <div className="flex gap-1 justify-end">
                <button onClick={() => onUse(t)} className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-100 hover:text-indigo-600" title="Use template">
                  <Copy size={13} />
                </button>
                <button onClick={() => onDelete(t.id)} className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600" title="Delete">
                  <Trash2 size={13} />
                </button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AutomationsTable({
  automations,
  loading,
  onDelete,
  statusConfig,
}: {
  automations: BroadcastAutomation[];
  loading: boolean;
  onDelete: (id: string) => void;
  statusConfig: StatusConfig;
}) {
  if (loading) return <div className="p-8 text-center text-slate-400"><Loader2 className="animate-spin mx-auto" /></div>;
  if (!automations.length) return <div className="p-8 text-center text-slate-400">No automations yet.</div>;

  return (
    <table className="w-full text-sm">
      <thead className="bg-slate-50 border-b border-slate-200">
        <tr>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Name</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Type</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Status</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Last Run</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Next Run</th>
          <th className="px-4 py-3" />
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {automations.map((a) => {
          const cfg = statusConfig[a.status] ?? { label: a.status, color: "bg-slate-100 text-slate-600", icon: Clock };
          const Icon = cfg.icon;
          return (
            <tr key={a.id} className="hover:bg-slate-50">
              <td className="px-4 py-3 font-medium text-slate-800">{a.name}</td>
              <td className="px-4 py-3 text-slate-600 capitalize">{a.type.replace("_", " ")}</td>
              <td className="px-4 py-3">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
                  <Icon size={11} /> {cfg.label}
                </span>
              </td>
              <td className="px-4 py-3 text-slate-400">{a.last_run ? formatDate(a.last_run) : "—"}</td>
              <td className="px-4 py-3 text-slate-400">{a.next_run ? formatDate(a.next_run) : "—"}</td>
              <td className="px-4 py-3">
                <button onClick={() => onDelete(a.id)} className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600" title="Delete">
                  <Trash2 size={13} />
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
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

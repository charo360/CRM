"use client";
import { useEffect, useState, useCallback } from "react";
import { fieldAgentsApi, customersApi } from "@/lib/api";
import Link from "next/link";
import {
  Users, ClipboardList, CheckCircle2, AlertTriangle, Plus, X, Check,
  RefreshCw, Edit2, Trash2, LogIn, LogOut, Activity, ChevronDown,
  MapPin, Phone, Mail, Clock, Target,
} from "lucide-react";

// ── types ─────────────────────────────────────────────────────────────────────
type Agent = {
  id: string; name: string; email: string; phone_number: string;
  role: string; status: string;
  tasks_total: number; tasks_pending: number; tasks_completed: number; tasks_overdue: number;
};
type Task = {
  id: string; assigned_to: string; agent_name: string; title: string;
  task_type: string; customer_id: string; customer_name: string;
  notes: string; due_date: string; priority: string; status: string;
  outcome: string; created_at: string;
};
type ActivityItem = {
  id: string; agent_name: string; description: string; type: string; created_at: string;
};
type Summary = {
  total_agents: number; active_today: number;
  tasks: { total: number; pending: number; in_progress: number; completed: number; overdue: number };
};
type Customer = { id: string; name: string; phone_number: string };

// ── constants ─────────────────────────────────────────────────────────────────
const TASK_TYPES = ["visit","call","demo","collect_payment","delivery","survey","other"];
const PRIORITIES = ["low","medium","high"];
const STATUSES   = ["pending","in_progress","completed","missed","cancelled"];

const PRIORITY_COLORS: Record<string, string> = {
  high:   "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low:    "bg-slate-100 text-slate-600",
};
const STATUS_COLORS: Record<string, string> = {
  pending:     "bg-blue-100 text-blue-700",
  in_progress: "bg-amber-100 text-amber-700",
  completed:   "bg-green-100 text-green-700",
  missed:      "bg-red-100 text-red-700",
  cancelled:   "bg-slate-100 text-slate-500",
};

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
function formatDate(s: string) {
  if (!s) return "—";
  return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
function isOverdue(task: Task) {
  return task.due_date && !["completed","cancelled","missed"].includes(task.status) &&
    new Date(task.due_date) < new Date();
}

// ── empty form ────────────────────────────────────────────────────────────────
function emptyTask(): Partial<Task> & { customCustomer: string } {
  return { assigned_to: "", title: "", task_type: "visit", customer_id: "", customer_name: "",
           notes: "", due_date: "", priority: "medium", customCustomer: "" };
}

// ── Agent card ────────────────────────────────────────────────────────────────
function AgentCard({ agent, onSelect, selected }: { agent: Agent; onSelect: () => void; selected: boolean }) {
  const completion = agent.tasks_total > 0
    ? Math.round((agent.tasks_completed / agent.tasks_total) * 100) : 0;
  return (
    <div
      onClick={onSelect}
      className={`bg-white rounded-xl border p-4 cursor-pointer transition-all hover:border-brand-dark/40 ${
        selected ? "border-brand-dark ring-1 ring-brand-dark/20" : "border-slate-200"
      }`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-brand/10 flex items-center justify-center font-bold text-brand-dark text-sm shrink-0">
            {agent.name.split(" ").map(n => n[0]).join("").slice(0,2).toUpperCase()}
          </div>
          <div>
            <p className="font-semibold text-slate-800 text-sm">{agent.name}</p>
            <p className="text-xs text-slate-400 capitalize">{agent.role}</p>
          </div>
        </div>
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
          agent.status === "active" ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"
        }`}>{agent.status}</span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center mb-3">
        {[
          { label: "Pending", val: agent.tasks_pending, color: "text-blue-600" },
          { label: "Done",    val: agent.tasks_completed, color: "text-green-600" },
          { label: "Overdue", val: agent.tasks_overdue, color: agent.tasks_overdue > 0 ? "text-red-600" : "text-slate-400" },
        ].map(({ label, val, color }) => (
          <div key={label} className="bg-slate-50 rounded-lg py-2">
            <p className={`text-lg font-bold ${color}`}>{val}</p>
            <p className="text-[10px] text-slate-400">{label}</p>
          </div>
        ))}
      </div>

      <div>
        <div className="flex justify-between text-xs text-slate-500 mb-1">
          <span>Completion</span><span>{completion}%</span>
        </div>
        <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div className="h-full bg-brand-dark rounded-full transition-all" style={{ width: `${completion}%` }} />
        </div>
      </div>

      {agent.phone_number && (
        <div className="mt-3 flex items-center gap-1.5 text-xs text-slate-400">
          <Phone size={11} />{agent.phone_number}
        </div>
      )}
    </div>
  );
}

// ── Task row ──────────────────────────────────────────────────────────────────
function TaskRow({ task, onEdit, onDelete, onCheckIn, onCheckOut }: {
  task: Task;
  onEdit: () => void;
  onDelete: () => void;
  onCheckIn: () => void;
  onCheckOut: () => void;
}) {
  const overdue = isOverdue(task);
  return (
    <tr className="hover:bg-slate-50">
      <td className="px-4 py-3">
        <div>
          <p className="text-sm font-medium text-slate-800 flex items-center gap-1.5">
            {task.title}
            {overdue && <AlertTriangle size={12} className="text-red-500 shrink-0" />}
          </p>
          {task.customer_name && <p className="text-xs text-slate-400 mt-0.5">{task.customer_name}</p>}
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-slate-600 capitalize">{task.task_type.replace("_"," ")}</td>
      <td className="px-4 py-3 text-sm text-slate-600">{task.agent_name}</td>
      <td className="px-4 py-3">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${PRIORITY_COLORS[task.priority] || ""}`}>
          {task.priority}
        </span>
      </td>
      <td className="px-4 py-3">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[task.status] || ""}`}>
          {task.status.replace("_"," ")}
        </span>
      </td>
      <td className={`px-4 py-3 text-xs tabular-nums ${overdue ? "text-red-500 font-medium" : "text-slate-400"}`}>
        {formatDate(task.due_date)}
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex justify-end items-center gap-1">
          {task.status === "pending" && (
            <button onClick={onCheckIn} title="Check in"
              className="p-1.5 rounded-lg text-slate-400 hover:text-green-600 hover:bg-green-50" >
              <LogIn size={14} />
            </button>
          )}
          {task.status === "in_progress" && (
            <button onClick={onCheckOut} title="Check out"
              className="p-1.5 rounded-lg text-slate-400 hover:text-brand-dark hover:bg-brand/10">
              <LogOut size={14} />
            </button>
          )}
          <button onClick={onEdit}   title="Edit"   className="p-1.5 rounded-lg text-slate-400 hover:text-brand-dark"><Edit2 size={14} /></button>
          <button onClick={onDelete} title="Delete" className="p-1.5 rounded-lg text-slate-400 hover:text-red-500"><Trash2 size={14} /></button>
        </div>
      </td>
    </tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function FieldAgentsPage() {
  const [tab, setTab] = useState<"overview"|"tasks"|"agents"|"activity">("overview");
  const [agents,   setAgents]   = useState<Agent[]>([]);
  const [tasks,    setTasks]    = useState<Task[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [summary,  setSummary]  = useState<Summary | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [statusFilter,  setStatusFilter]  = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");

  // Task modal
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [editingTask,   setEditingTask]   = useState<Task | null>(null);
  const [taskForm,      setTaskForm]      = useState(emptyTask());
  const [saving, setSaving] = useState(false);

  // Check-in / check-out modal
  const [checkModal, setCheckModal] = useState<{ task: Task; mode: "in"|"out" } | null>(null);
  const [checkForm,  setCheckForm]  = useState({ location_note: "", notes: "", outcome: "", status: "completed" });
  const [checkSaving, setCheckSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ag, tk, act, sum, cust] = await Promise.all([
        fieldAgentsApi.listAgents(),
        fieldAgentsApi.listTasks(),
        fieldAgentsApi.listActivity({ limit: 40 }),
        fieldAgentsApi.summary(),
        customersApi.list(),
      ]);
      setAgents(ag as Agent[]);
      setTasks(tk as Task[]);
      setActivity(act as ActivityItem[]);
      setSummary(sum as Summary);
      setCustomers((cust as Customer[]).slice(0, 200));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── Task modal helpers ──────────────────────────────────────────────────
  function openNewTask(agentId?: string) {
    setEditingTask(null);
    setTaskForm({ ...emptyTask(), assigned_to: agentId || "" });
    setShowTaskModal(true);
  }
  function openEditTask(t: Task) {
    setEditingTask(t);
    setTaskForm({ ...t, customCustomer: "" });
    setShowTaskModal(true);
  }
  async function saveTask() {
    setSaving(true);
    try {
      const payload = {
        assigned_to:   taskForm.assigned_to,
        title:         taskForm.title,
        task_type:     taskForm.task_type,
        customer_id:   taskForm.customer_id || undefined,
        customer_name: taskForm.customer_name || undefined,
        notes:         taskForm.notes,
        due_date:      taskForm.due_date || undefined,
        priority:      taskForm.priority,
        location:      (taskForm as Record<string, unknown>).location as string || "",
        status:        taskForm.status,
        outcome:       taskForm.outcome,
      };
      if (editingTask) await fieldAgentsApi.updateTask(editingTask.id, payload as Record<string, unknown>);
      else             await fieldAgentsApi.createTask(payload as Record<string, unknown>);
      setShowTaskModal(false);
      await load();
    } finally { setSaving(false); }
  }
  async function deleteTask(t: Task) {
    if (!confirm(`Delete task "${t.title}"?`)) return;
    await fieldAgentsApi.deleteTask(t.id);
    await load();
  }

  // ── Check-in / out helpers ──────────────────────────────────────────────
  function openCheckIn(t: Task)  { setCheckModal({ task: t, mode: "in"  }); setCheckForm({ location_note: "", notes: "", outcome: "", status: "completed" }); }
  function openCheckOut(t: Task) { setCheckModal({ task: t, mode: "out" }); setCheckForm({ location_note: "", notes: "", outcome: "", status: "completed" }); }
  async function submitCheck() {
    if (!checkModal) return;
    setCheckSaving(true);
    try {
      if (checkModal.mode === "in")
        await fieldAgentsApi.checkIn(checkModal.task.id,  { location_note: checkForm.location_note, notes: checkForm.notes });
      else
        await fieldAgentsApi.checkOut(checkModal.task.id, { outcome: checkForm.outcome, notes: checkForm.notes, status: checkForm.status });
      setCheckModal(null);
      await load();
    } finally { setCheckSaving(false); }
  }

  // ── Filtered tasks ──────────────────────────────────────────────────────
  const filteredTasks = tasks.filter(t => {
    if (selectedAgent  && t.assigned_to !== selectedAgent)  return false;
    if (statusFilter   && t.status      !== statusFilter)    return false;
    if (priorityFilter && t.priority    !== priorityFilter)  return false;
    return true;
  });

  const s = summary;

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Target className="text-brand-dark" size={24} /> Field Agents
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Assign tasks, track visits, and monitor your field team</p>
        </div>
        <button onClick={() => openNewTask()}
          className="flex items-center gap-2 bg-brand-dark text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand">
          <Plus size={16} /> Assign Task
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 gap-1">
        {(["overview","tasks","agents","activity"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px capitalize transition-colors ${
              tab === t ? "border-brand-dark text-brand-dark" : "border-transparent text-slate-500 hover:text-slate-700"
            }`}>{t}</button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48 text-slate-400">Loading…</div>
      ) : (
        <>
          {/* ── Overview tab ── */}
          {tab === "overview" && s && (
            <div className="space-y-5">
              {/* KPIs */}
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                {[
                  { label: "Total Agents",   val: s.total_agents,        color: "text-brand-dark",  bg: "bg-brand/10" },
                  { label: "Active Today",   val: s.active_today,        color: "text-green-600",   bg: "bg-green-50" },
                  { label: "Pending Tasks",  val: s.tasks.pending,       color: "text-blue-600",    bg: "bg-blue-50" },
                  { label: "In Progress",    val: s.tasks.in_progress,   color: "text-amber-600",   bg: "bg-amber-50" },
                  { label: "Overdue",        val: s.tasks.overdue,       color: s.tasks.overdue > 0 ? "text-red-600" : "text-slate-400", bg: s.tasks.overdue > 0 ? "bg-red-50" : "bg-slate-50" },
                ].map(({ label, val, color, bg }) => (
                  <div key={label} className={`rounded-xl border border-slate-200 p-4 ${bg}`}>
                    <p className="text-xs text-slate-500 font-medium">{label}</p>
                    <p className={`text-2xl font-bold mt-1 ${color}`}>{val}</p>
                  </div>
                ))}
              </div>

              {/* Agent grid */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="font-semibold text-slate-800">Your Field Team</h2>
                  <Link href="/dashboard/team" className="text-xs text-brand-dark hover:underline">Manage team →</Link>
                </div>
                {agents.length === 0 ? (
                  <div className="bg-white rounded-xl border border-slate-200 p-10 text-center text-slate-400">
                    <Users size={40} className="mx-auto mb-3 opacity-30" />
                    <p className="text-sm">No team members yet.</p>
                    <Link href="/dashboard/team" className="text-brand-dark text-sm font-medium hover:underline mt-1 inline-block">Add team members →</Link>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {agents.map(a => (
                      <AgentCard key={a.id} agent={a} selected={selectedAgent === a.id}
                        onSelect={() => { setSelectedAgent(a.id === selectedAgent ? "" : a.id); setTab("tasks"); }} />
                    ))}
                  </div>
                )}
              </div>

              {/* Overdue alert */}
              {s.tasks.overdue > 0 && (
                <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl p-4">
                  <AlertTriangle className="text-red-500 shrink-0" size={18} />
                  <div>
                    <p className="text-sm font-semibold text-red-700">{s.tasks.overdue} overdue task{s.tasks.overdue > 1 ? "s" : ""}</p>
                    <button onClick={() => { setStatusFilter(""); setTab("tasks"); }}
                      className="text-xs text-red-600 hover:underline mt-0.5">View all tasks →</button>
                  </div>
                </div>
              )}

              {/* Recent activity */}
              {activity.length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200">
                  <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-800 text-sm">Recent Activity</h2>
                    <button onClick={() => setTab("activity")} className="text-xs text-brand-dark hover:underline">View all</button>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {activity.slice(0,6).map(a => (
                      <div key={a.id} className="px-5 py-3 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-7 h-7 rounded-full bg-brand/10 flex items-center justify-center text-xs font-bold text-brand-dark shrink-0">
                            {a.agent_name?.[0]?.toUpperCase() || "?"}
                          </div>
                          <p className="text-sm text-slate-700">{a.description}</p>
                        </div>
                        <span className="text-xs text-slate-400 shrink-0 ml-3">{timeAgo(a.created_at)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Tasks tab ── */}
          {tab === "tasks" && (
            <div className="space-y-4">
              {/* Filters */}
              <div className="flex flex-wrap gap-2 items-center">
                <select value={selectedAgent} onChange={e => setSelectedAgent(e.target.value)}
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm">
                  <option value="">All agents</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
                <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm">
                  <option value="">All statuses</option>
                  {STATUSES.map(s => <option key={s} value={s} className="capitalize">{s.replace("_"," ")}</option>)}
                </select>
                <select value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}
                  className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm">
                  <option value="">All priorities</option>
                  {PRIORITIES.map(p => <option key={p} value={p} className="capitalize">{p}</option>)}
                </select>
                <span className="ml-auto text-xs text-slate-400">{filteredTasks.length} tasks</span>
                <button onClick={() => openNewTask(selectedAgent || undefined)}
                  className="flex items-center gap-1.5 bg-brand-dark text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-brand">
                  <Plus size={14} /> New Task
                </button>
              </div>

              {filteredTasks.length === 0 ? (
                <div className="bg-white rounded-xl border border-slate-200 p-12 text-center text-slate-400">
                  <ClipboardList size={40} className="mx-auto mb-3 opacity-30" />
                  <p className="text-sm">No tasks found. Assign one to get started.</p>
                </div>
              ) : (
                <div className="bg-white rounded-xl border overflow-x-auto">
                  <table className="w-full text-sm min-w-[780px]">
                    <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                      <tr>
                        <th className="text-left px-4 py-3">Task</th>
                        <th className="text-left px-4 py-3">Type</th>
                        <th className="text-left px-4 py-3">Agent</th>
                        <th className="text-left px-4 py-3">Priority</th>
                        <th className="text-left px-4 py-3">Status</th>
                        <th className="text-left px-4 py-3">Due</th>
                        <th className="text-right px-4 py-3"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {filteredTasks.map(t => (
                        <TaskRow key={t.id} task={t}
                          onEdit={() => openEditTask(t)}
                          onDelete={() => deleteTask(t)}
                          onCheckIn={() => openCheckIn(t)}
                          onCheckOut={() => openCheckOut(t)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── Agents tab ── */}
          {tab === "agents" && (
            <div className="space-y-4">
              {agents.length === 0 ? (
                <div className="bg-white rounded-xl border border-slate-200 p-12 text-center text-slate-400">
                  <Users size={40} className="mx-auto mb-3 opacity-30" />
                  <p className="text-sm">No team members yet.</p>
                  <Link href="/dashboard/team" className="text-brand-dark text-sm font-medium hover:underline mt-1 inline-block">Add from Team Settings →</Link>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {agents.map(a => (
                    <AgentCard key={a.id} agent={a} selected={selectedAgent === a.id}
                      onSelect={() => { setSelectedAgent(a.id === selectedAgent ? "" : a.id); setTab("tasks"); }} />
                  ))}
                </div>
              )}
              <p className="text-xs text-slate-400 text-center">
                Field agents are your team members. <Link href="/dashboard/team" className="text-brand-dark hover:underline">Manage team</Link>
              </p>
            </div>
          )}

          {/* ── Activity tab ── */}
          {tab === "activity" && (
            <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100">
              {activity.length === 0 ? (
                <div className="p-12 text-center text-slate-400">
                  <Activity size={40} className="mx-auto mb-3 opacity-30" />
                  <p className="text-sm">No activity yet. Assign tasks and check in to see the feed.</p>
                </div>
              ) : activity.map(a => (
                <div key={a.id} className="px-5 py-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-brand/10 flex items-center justify-center text-xs font-bold text-brand-dark shrink-0">
                      {a.agent_name?.[0]?.toUpperCase() || "?"}
                    </div>
                    <div>
                      <p className="text-sm text-slate-700">{a.description}</p>
                      <p className="text-xs text-slate-400">{a.agent_name}</p>
                    </div>
                  </div>
                  <span className="text-xs text-slate-400 shrink-0 ml-4">{timeAgo(a.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Assign / Edit Task Modal ── */}
      {showTaskModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowTaskModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="p-5 border-b border-slate-100 flex items-center justify-between sticky top-0 bg-white z-10">
              <h2 className="text-base font-semibold">{editingTask ? "Edit Task" : "Assign Task"}</h2>
              <button onClick={() => setShowTaskModal(false)} className="text-slate-400 hover:text-slate-700"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              {/* Agent */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Assign to Agent</label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  value={taskForm.assigned_to}
                  onChange={e => setTaskForm(f => ({ ...f, assigned_to: e.target.value }))}>
                  <option value="">Select agent…</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>

              {/* Title */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Task Title</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  placeholder="e.g. Visit client to collect payment"
                  value={taskForm.title || ""}
                  onChange={e => setTaskForm(f => ({ ...f, title: e.target.value }))} />
              </div>

              <div className="grid grid-cols-2 gap-3">
                {/* Type */}
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Task Type</label>
                  <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={taskForm.task_type}
                    onChange={e => setTaskForm(f => ({ ...f, task_type: e.target.value }))}>
                    {TASK_TYPES.map(t => <option key={t} value={t} className="capitalize">{t.replace("_"," ")}</option>)}
                  </select>
                </div>
                {/* Priority */}
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Priority</label>
                  <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={taskForm.priority}
                    onChange={e => setTaskForm(f => ({ ...f, priority: e.target.value }))}>
                    {PRIORITIES.map(p => <option key={p} value={p} className="capitalize">{p}</option>)}
                  </select>
                </div>
              </div>

              {/* Customer */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Customer <span className="text-slate-400">(optional)</span></label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  value={taskForm.customer_id || ""}
                  onChange={e => {
                    const cust = customers.find(c => c.id === e.target.value);
                    setTaskForm(f => ({ ...f, customer_id: e.target.value, customer_name: cust?.name || "" }));
                  }}>
                  <option value="">No customer linked</option>
                  {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {/* Due date */}
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Due Date</label>
                  <input type="date" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={taskForm.due_date || ""}
                    onChange={e => setTaskForm(f => ({ ...f, due_date: e.target.value }))} />
                </div>
                {/* Status (edit only) */}
                {editingTask && (
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Status</label>
                    <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                      value={taskForm.status || "pending"}
                      onChange={e => setTaskForm(f => ({ ...f, status: e.target.value }))}>
                      {STATUSES.map(s => <option key={s} value={s} className="capitalize">{s.replace("_"," ")}</option>)}
                    </select>
                  </div>
                )}
              </div>

              {/* Notes */}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Notes <span className="text-slate-400">(optional)</span></label>
                <textarea rows={2} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none"
                  placeholder="Instructions, address, context…"
                  value={taskForm.notes || ""}
                  onChange={e => setTaskForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
            </div>
            <div className="p-5 border-t border-slate-100 flex justify-end gap-3 sticky bottom-0 bg-white">
              <button onClick={() => setShowTaskModal(false)} className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900">Cancel</button>
              <button onClick={saveTask}
                disabled={saving || !taskForm.assigned_to || !taskForm.title?.trim()}
                className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50 flex items-center gap-1.5">
                {saving ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                {saving ? "Saving…" : editingTask ? "Update Task" : "Assign Task"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Check-in / Check-out Modal ── */}
      {checkModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setCheckModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-base font-semibold flex items-center gap-2">
                {checkModal.mode === "in" ? <LogIn size={16} className="text-green-600" /> : <LogOut size={16} className="text-brand-dark" />}
                {checkModal.mode === "in" ? "Check In" : "Check Out"}
              </h2>
              <button onClick={() => setCheckModal(null)} className="text-slate-400 hover:text-slate-700"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-sm text-slate-600">
                <span className="font-medium">{checkModal.task.title}</span>
                {checkModal.task.customer_name && <span className="text-slate-400"> · {checkModal.task.customer_name}</span>}
              </p>
              {checkModal.mode === "in" && (
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Location note <span className="text-slate-400">(optional)</span></label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    placeholder="e.g. Arrived at office, Westlands"
                    value={checkForm.location_note}
                    onChange={e => setCheckForm(f => ({ ...f, location_note: e.target.value }))} />
                </div>
              )}
              {checkModal.mode === "out" && (
                <>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Outcome</label>
                    <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                      placeholder="e.g. Payment collected, Follow-up needed"
                      value={checkForm.outcome}
                      onChange={e => setCheckForm(f => ({ ...f, outcome: e.target.value }))} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Mark task as</label>
                    <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                      value={checkForm.status}
                      onChange={e => setCheckForm(f => ({ ...f, status: e.target.value }))}>
                      <option value="completed">Completed</option>
                      <option value="missed">Missed</option>
                      <option value="in_progress">Still in progress</option>
                    </select>
                  </div>
                </>
              )}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Notes <span className="text-slate-400">(optional)</span></label>
                <textarea rows={2} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none"
                  value={checkForm.notes}
                  onChange={e => setCheckForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
            </div>
            <div className="p-5 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setCheckModal(null)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={submitCheck} disabled={checkSaving}
                className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50 flex items-center gap-1.5">
                {checkSaving ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                {checkSaving ? "Saving…" : checkModal.mode === "in" ? "Check In" : "Check Out"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

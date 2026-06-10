"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  ClipboardList,
  Plus,
  Calendar,
  AlertCircle,
  CheckCircle,
  FileText,
  User,
  Bot,
  Play,
  RotateCcw,
  Sparkles,
  Loader2,
  Check,
  PlusCircle,
  Scale,
  Zap,
  HelpCircle,
  ArrowRight,
  Eye,
  Info,
  GripVertical,
  Trash2
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SubTask {
  title: string;
  done: boolean;
}

interface Task {
  id: string;
  title: string;
  due_date?: string;
  source: string;
  status: "pending" | "in_progress" | "done" | "overdue";
  owner: "founder" | "zilo";
  context?: string;
  progress?: string;
  result?: string;
  zilo_status?: "running" | "scheduled" | "waiting" | "done";
  sub_tasks?: SubTask[];
  project_id?: string;
  project_step_index?: number;
  created_at: string;
  completed_at?: string;
}

interface ProjectStep {
  name: string;
  owner: "founder" | "zilo";
  status: "done" | "running" | "pending" | "overdue";
  due_date?: string;
}

interface Project {
  id: string;
  name: string;
  due_date: string;
  goal: string;
  steps: ProjectStep[];
  created_at: string;
}

interface WorkDraft {
  id: string;
  label?: string;
  draft?: string;
  detail?: string;
  approval?: "pending" | "approved" | "rejected";
  channel?: string;
}

interface TaskWork {
  status: string; // not_run | running | completed | done | unavailable | ...
  result_summary?: string;
  progress?: { total: number; done: number };
  pending?: number;
  staged_count?: number;
  drafts: WorkDraft[];
  demo?: boolean;
  delegation_id?: string;
}

// Convert an ISO string into a value a <input type="datetime-local"> accepts.
const toLocalInputValue = (iso?: string) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const getProjectColorScheme = (name: string) => {
  if (!name) return {
    border: "border-slate-200",
    bg: "bg-slate-50/50",
    text: "text-slate-800",
    badge: "bg-slate-100 text-slate-700 border-slate-200",
    progress: "bg-slate-500",
    borderL: "border-l-slate-400"
  };
  
  const hash = name.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const schemes = [
    {
      border: "border-indigo-200/80",
      bg: "bg-indigo-50/20",
      text: "text-indigo-800",
      badge: "bg-indigo-50 text-indigo-700 border-indigo-200/50",
      progress: "bg-indigo-600",
      borderL: "border-l-indigo-500"
    },
    {
      border: "border-purple-200/80",
      bg: "bg-purple-50/20",
      text: "text-purple-800",
      badge: "bg-purple-50 text-purple-700 border-purple-200/50",
      progress: "bg-purple-600",
      borderL: "border-l-purple-500"
    },
    {
      border: "border-emerald-200/80",
      bg: "bg-emerald-50/20",
      text: "text-emerald-800",
      badge: "bg-emerald-50 text-emerald-700 border-emerald-200/50",
      progress: "bg-emerald-600",
      borderL: "border-l-emerald-500"
    },
    {
      border: "border-amber-200/80",
      bg: "bg-amber-50/20",
      text: "text-amber-800",
      badge: "bg-amber-50 text-amber-700 border-amber-200/50",
      progress: "bg-amber-500",
      borderL: "border-l-amber-500"
    },
    {
      border: "border-rose-200/80",
      bg: "bg-rose-50/20",
      text: "text-rose-800",
      badge: "bg-rose-50 text-rose-700 border-rose-200/50",
      progress: "bg-rose-600",
      borderL: "border-l-rose-500"
    },
    {
      border: "border-cyan-200/80",
      bg: "bg-cyan-50/20",
      text: "text-cyan-800",
      badge: "bg-cyan-50 text-cyan-700 border-cyan-200/50",
      progress: "bg-cyan-600",
      borderL: "border-l-cyan-500"
    }
  ];
  return schemes[hash % schemes.length];
};

// Keep in sync with NON_DELEGATABLE_REASONS in backend/rex/workplan/routes.py.
const NON_DELEGATABLE_KEYWORDS = [
  "meet", "meeting", "call", "phone", "contract", "nda", "sign",
  "negotiate", "negotiation", "hire", "pricing decision", "audit", "pay",
];

const isDelegatableTitle = (title: string) =>
  !NON_DELEGATABLE_KEYWORDS.some((kw) => title.toLowerCase().includes(kw));

// Format an absolute short date, guarding against missing/invalid values.
const formatShortDate = (value?: string) => {
  if (!value) return "No date";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "No date";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

// Human relative label for a due date, e.g. "Due today", "Due in 5 days", "3 days overdue".
const formatRelativeDue = (value?: string) => {
  if (!value) return "No due date";
  const due = new Date(value);
  if (isNaN(due.getTime())) return "No due date";
  const now = new Date();
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round(
    (startOfDay(due).getTime() - startOfDay(now).getTime()) / (1000 * 60 * 60 * 24)
  );
  if (diffDays === 0) return "Due today";
  if (diffDays === 1) return "Due tomorrow";
  if (diffDays > 1) return `Due in ${diffDays} days`;
  if (diffDays === -1) return "1 day overdue";
  return `${Math.abs(diffDays)} days overdue`;
};

export default function WorkPlanPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"today" | "week" | "all">("all");
  const [quickInput, setQuickInput] = useState("");
  const [parsing, setParsing] = useState(false);

  // Add Task Modal
  const [showAddTask, setShowAddTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskOwner, setTaskOwner] = useState<"founder" | "zilo">("founder");
  const [taskDue, setTaskDue] = useState("");
  const [taskContext, setTaskContext] = useState("");
  const [taskSubTasks, setTaskSubTasks] = useState<string[]>([]);
  const [newSubTask, setNewSubTask] = useState("");

  // Add Project Modal / Suggester
  const [showAddProject, setShowAddProject] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectGoal, setProjectGoal] = useState("");
  const [projectDue, setProjectDue] = useState("");
  const [suggestedSteps, setSuggestedSteps] = useState<any[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const [confirmingProject, setConfirmingProject] = useState(false);

  // Log Update Modal
  const [logTaskId, setLogTaskId] = useState<string | null>(null);
  const [logText, setLogText] = useState("");
  const [loggingUpdate, setLoggingUpdate] = useState(false);

  // Zilo real-work review modal
  const [workTask, setWorkTask] = useState<Task | null>(null);
  const [workData, setWorkData] = useState<TaskWork | null>(null);
  const [workLoading, setWorkLoading] = useState(false);
  const [runningTask, setRunningTask] = useState(false);
  const [approvingWork, setApprovingWork] = useState(false);

  // Inline due-date editing
  const [editingDateId, setEditingDateId] = useState<string | null>(null);
  const [editingDateValue, setEditingDateValue] = useState("");

  // Audit Log Modal
  const [activeAuditTask, setActiveAuditTask] = useState<Task | null>(null);

  // Drag and Drop Delegation/Reassignment states
  const [isDragging, setIsDragging] = useState(false);
  const [isDraggingDelegatable, setIsDraggingDelegatable] = useState(true);
  const [activeDropLane, setActiveDropLane] = useState<"founder" | "zilo" | null>(null);

  const handleDragStart = (e: React.DragEvent, task: Task, owner: "founder" | "zilo") => {
    e.dataTransfer.setData("text/plain", task.id);
    e.dataTransfer.setData("owner", owner);
    setIsDragging(true);
    // Check if task is delegatable (same keyword rule as backend)
    setIsDraggingDelegatable(isDelegatableTitle(task.title));
  };

  const handleDragEnd = () => {
    setIsDragging(false);
    setActiveDropLane(null);
    setIsDraggingDelegatable(true);
  };

  const handleDragOver = (e: React.DragEvent, lane: "founder" | "zilo") => {
    e.preventDefault();
    if (activeDropLane !== lane) {
      setActiveDropLane(lane);
    }
  };

  const handleDragLeave = () => {
    setActiveDropLane(null);
  };

  const handleDrop = async (e: React.DragEvent, targetLane: "founder" | "zilo") => {
    e.preventDefault();
    const taskId = e.dataTransfer.getData("text/plain");
    const originalOwner = e.dataTransfer.getData("owner");

    handleDragEnd();

    if (!taskId || originalOwner === targetLane) return;

    if (targetLane === "zilo") {
      // Block non-delegatable tasks client-side so the red "no-drop" state
      // is truthful instead of relying solely on a backend warning.
      const task = tasks.find((t) => t.id === taskId);
      if (task && !isDelegatableTitle(task.title)) {
        toast.warning("This task needs you personally. Zilo can't take it on.");
        return;
      }
      await handleDelegate(taskId);
    } else {
      await handleReassign(taskId);
    }
  };

  // Dynamic header state
  const [formattedDate, setFormattedDate] = useState("");

  useEffect(() => {
    const d = new Date();
    const wd = d.toLocaleDateString("en-US", { weekday: "long" });
    const ms = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    setFormattedDate(`${wd} ${ms}`);
  }, []);

  const loadData = useCallback(async () => {
    try {
      const data = await api.get<{ tasks: Task[]; projects: Project[] }>("/rex/workplan");
      setTasks(data.tasks);
      setProjects(data.projects);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load work plan");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleQuickSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickInput.trim()) return;
    setParsing(true);
    try {
      await api.post<any>("/rex/workplan/parse-input", { text: quickInput });
      toast.success("Zilo parsed your update successfully!");
      setQuickInput("");
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to parse update");
    } finally {
      setParsing(false);
    }
  };

  const handleAddTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    try {
      const res = await api.post<{ warning?: string }>("/rex/workplan/tasks", {
        title: taskTitle,
        owner: taskOwner,
        due_date: taskDue || null,
        context: taskContext || null,
        sub_tasks: taskSubTasks,
      });
      if (res?.warning) {
        toast.warning(res.warning);
      } else {
        toast.success("Task created.");
      }
      setShowAddTask(false);
      setTaskTitle("");
      setTaskDue("");
      setTaskContext("");
      setTaskSubTasks([]);
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create task");
    }
  };

  const handleCompleteTask = async (taskId: string) => {
    try {
      await api.post(`/rex/workplan/tasks/${taskId}/complete`, {});
      toast.success("Task completed!");
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to complete task");
    }
  };

  const handleToggleSubtask = async (taskId: string, subIndex: number) => {
    try {
      await api.post(`/rex/workplan/tasks/${taskId}/subtask/${subIndex}/toggle`, {});
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to toggle step");
    }
  };

  const handleDelegate = async (taskId: string) => {
    try {
      const res = await api.post<{ ok: boolean; warning?: string }>(`/rex/workplan/tasks/${taskId}/delegate`, {});
      if (res.warning) {
        toast.warning(res.warning);
      } else {
        toast.success("Delegated to Zilo.");
      }
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delegation failed");
    }
  };

  const handleReassign = async (taskId: string) => {
    try {
      await api.post(`/rex/workplan/tasks/${taskId}/reassign`, {});
      toast.success("Task reassigned to you.");
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Reassignment failed");
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    try {
      await api.delete(`/rex/workplan/tasks/${taskId}`);
      toast.success("Task deleted.");
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete task");
    }
  };

  const handleDeleteProject = async (projectId: string) => {
    try {
      await api.delete(`/rex/workplan/projects/${projectId}`);
      toast.success("Project deleted.");
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete project");
    }
  };

  const refreshWork = async (taskId: string) => {
    try {
      const data = await api.get<TaskWork>(`/rex/workplan/tasks/${taskId}/work`);
      setWorkData(data);
      return data;
    } catch {
      return null;
    }
  };

  const openWork = async (task: Task) => {
    setWorkTask(task);
    setWorkData(null);
    setWorkLoading(true);
    try {
      await refreshWork(task.id);
    } finally {
      setWorkLoading(false);
    }
  };

  const handleRunTask = async (task: Task) => {
    setRunningTask(true);
    try {
      const res = await api.post<{ started: boolean; demo?: boolean; message?: string }>(
        `/rex/workplan/tasks/${task.id}/run`, {}
      );
      if (!res.started) {
        toast.message(res.message || "Execution isn't available here.");
      } else {
        toast.success("Zilo is working on it…");
        // Poll for staged drafts while the agent runs in the background.
        for (let i = 0; i < 6; i++) {
          await new Promise((r) => setTimeout(r, 1500));
          const data = await refreshWork(task.id);
          if (data && (data.status === "completed" || (data.drafts?.length ?? 0) > 0)) break;
        }
        void loadData();
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to run task");
    } finally {
      setRunningTask(false);
    }
  };

  const handleApproveWork = async (task: Task) => {
    setApprovingWork(true);
    try {
      const res = await api.post<{ ok: boolean; result_summary?: string }>(
        `/rex/workplan/tasks/${task.id}/approve-work`, {}
      );
      toast.success(res.result_summary || "Approved and sent.");
      setWorkTask(null);
      setWorkData(null);
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to approve work");
    } finally {
      setApprovingWork(false);
    }
  };

  const startEditDate = (task: Task) => {
    setEditingDateId(task.id);
    setEditingDateValue(toLocalInputValue(task.due_date));
  };

  const handleSaveDueDate = async (taskId: string) => {
    try {
      const due = editingDateValue ? new Date(editingDateValue).toISOString() : "";
      await api.patch(`/rex/workplan/tasks/${taskId}`, { due_date: due });
      setEditingDateId(null);
      setEditingDateValue("");
      toast.success("Due date updated.");
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update date");
    }
  };

  const handleLogSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!logTaskId || !logText.trim()) return;
    setLoggingUpdate(true);
    try {
      await api.post(`/rex/workplan/tasks/${logTaskId}/log`, { update_text: logText });
      toast.success("Task update logged.");
      setLogTaskId(null);
      setLogText("");
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to log update");
    } finally {
      setLoggingUpdate(false);
    }
  };

  const handleSuggestSteps = async () => {
    if (!projectName.trim() || !projectGoal.trim() || !projectDue.trim()) {
      toast.error("Please fill in project name, goal and due date");
      return;
    }
    setSuggesting(true);
    try {
      const res = await api.post<any>("/rex/workplan/projects", {
        name: projectName,
        goal: projectGoal,
        due_date: projectDue,
        confirm: false,
      });
      setSuggestedSteps(res.suggested_steps);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to generate steps");
    } finally {
      setSuggesting(false);
    }
  };

  const handleConfirmProject = async () => {
    setConfirmingProject(true);
    try {
      await api.post("/rex/workplan/projects", {
        name: projectName,
        goal: projectGoal,
        due_date: projectDue,
        confirm: true,
      });
      toast.success("Project created with suggested steps!");
      setShowAddProject(false);
      setProjectName("");
      setProjectGoal("");
      setProjectDue("");
      setSuggestedSteps([]);
      void loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to confirm project");
    } finally {
      setConfirmingProject(false);
    }
  };

  const addSubTaskItem = () => {
    if (newSubTask.trim()) {
      setTaskSubTasks([...taskSubTasks, newSubTask.trim()]);
      setNewSubTask("");
    }
  };

  const filterTasks = (list: Task[]) => {
    return list.filter((t) => {
      // If completed on a previous day, hide from active lanes
      if (t.status === "done" && t.completed_at) {
        const completedDate = new Date(t.completed_at).toDateString();
        const todayDate = new Date().toDateString();
        if (completedDate !== todayDate) {
          return false;
        }
      }
      
      if (filter === "all") return true;
      if (!t.due_date) return false;
      const due = new Date(t.due_date);
      const now = new Date();
      const diffTime = due.getTime() - now.getTime();
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      
      if (filter === "today") return diffDays <= 1;
      if (filter === "week") return diffDays <= 7;
      return true;
    });
  };

  const myTasks = filterTasks(tasks.filter((t) => t.owner === "founder"));
  const ziloTasks = filterTasks(tasks.filter((t) => t.owner === "zilo"));

  // Dynamic stats calculation
  const dueTodayCount = tasks.filter(t => {
    if (!t.due_date || t.status === "done") return false;
    return new Date(t.due_date).toDateString() === new Date().toDateString();
  }).length;

  const ziloDoneCount = tasks.filter(t => t.owner === "zilo" && t.status === "done").length;

  // Visual Helpers matching screenshots exactly
  const getDueStyle = (task: Task) => {
    if (task.status === "done") return "border-slate-200 bg-slate-50/50 opacity-60";
    if (!task.due_date) return "border-slate-200 bg-white text-slate-800";
    const due = new Date(task.due_date);
    const now = new Date();
    
    // Checks if overdue (due < now and not today)
    const isToday = due.toDateString() === now.toDateString();
    if (due < now && !isToday) {
      return "border-slate-200 border-l-4 border-l-red-500 bg-white text-slate-800";
    }
    
    if (isToday) {
      return "border-slate-200 border-l-4 border-l-amber-500 bg-white text-slate-800";
    }
    
    return "border-slate-200 bg-white text-slate-800";
  };

  const getZiloDueStyle = (task: Task) => {
    if (task.status === "done") {
      return "border-slate-200 border-l-4 border-l-emerald-500 bg-white text-slate-800 opacity-70";
    }
    if (task.zilo_status === "running") {
      return "border-slate-200 border-l-4 border-l-blue-500 bg-white text-slate-800";
    }
    return "border-slate-200 bg-white text-slate-800";
  };

  const getDueBadgeStyle = (task: Task) => {
    if (task.status === "done") return "text-slate-500 bg-slate-100 border-slate-200";
    if (!task.due_date) return "text-slate-500 bg-slate-100 border-slate-200";
    const due = new Date(task.due_date);
    const now = new Date();
    
    const isToday = due.toDateString() === now.toDateString();
    if (due < now && !isToday) return "text-red-700 bg-red-50 border-red-200/50";
    if (isToday) return "text-amber-700 bg-amber-50 border-amber-200/50";
    return "text-orange-800 bg-orange-50/50 border-orange-200/40";
  };

  const getDueBadgeLabel = (task: Task) => {
    if (task.status === "done") return "Done";
    if (!task.due_date) return "No due date";
    const due = new Date(task.due_date);
    const now = new Date();
    const isToday = due.toDateString() === now.toDateString();
    
    if (due < now && !isToday) return "Overdue";
    if (isToday) return "Due today";
    
    // Check if Friday
    if (due.getDay() === 5) return "Due Friday";
    
    return due.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  const getSourceIcon = (source: string) => {
    const s = source.toLowerCase();
    if (s.includes("calendar")) return <Calendar size={13} className="text-slate-400 shrink-0" />;
    if (s.includes("decision")) return <Zap size={13} className="text-slate-400 shrink-0" />;
    if (s.includes("notes") || s.includes("meeting")) return <FileText size={13} className="text-slate-400 shrink-0" />;
    return <Info size={13} className="text-slate-400 shrink-0" />;
  };

  // Inline due-date editor, shown under a card header while that card is being edited.
  const renderDueEditor = (task: Task) => {
    if (editingDateId !== task.id) return null;
    return (
      <div className="flex flex-wrap items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg p-2.5">
        <input
          type="datetime-local"
          value={editingDateValue}
          onChange={(e) => setEditingDateValue(e.target.value)}
          className="bg-white border border-slate-200 rounded-md px-2 py-1 text-xs text-slate-800 focus:outline-none focus:border-emerald-500"
        />
        <button
          onClick={() => handleSaveDueDate(task.id)}
          className="rounded-md bg-slate-900 text-white px-3 py-1 text-xs font-semibold hover:bg-slate-800 cursor-pointer"
        >
          Save
        </button>
        {task.due_date && (
          <button
            onClick={() => { setEditingDateValue(""); handleSaveDueDate(task.id); }}
            className="rounded-md border border-slate-200 bg-white text-slate-500 px-2 py-1 text-xs font-semibold hover:bg-slate-50 cursor-pointer"
          >
            Clear
          </button>
        )}
        <button
          onClick={() => { setEditingDateId(null); setEditingDateValue(""); }}
          className="rounded-md border border-slate-200 bg-white text-slate-500 px-2 py-1 text-xs font-semibold hover:bg-slate-50 cursor-pointer"
        >
          Cancel
        </button>
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-slate-50 text-slate-800 p-6 lg:p-8 font-sans">
      {/* Top Header */}
      <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 pb-5 shrink-0">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Work Plan</h1>
          <p className="text-sm text-slate-500 mt-1">
            {formattedDate} · {dueTodayCount} {dueTodayCount === 1 ? "task" : "tasks"} due today · Zilo handled {ziloDoneCount} {ziloDoneCount === 1 ? "thing" : "things"} overnight
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-100 p-1 rounded-xl border border-slate-200">
            {(["today", "week", "all"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  "px-4 py-1.5 rounded-lg text-xs font-semibold capitalize transition cursor-pointer",
                  filter === f
                    ? "bg-white text-slate-900 border border-slate-200/80 shadow-sm font-bold"
                    : "text-slate-500 hover:text-slate-800"
                )}
              >
                {f === "today" ? "Today" : f === "week" ? "This week" : "All"}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowAddTask(true)}
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 transition cursor-pointer shadow-sm animate-fade-in"
          >
            <Plus size={14} className="text-slate-500" />
            Add task
          </button>
          <button
            onClick={() => setShowAddProject(true)}
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 transition cursor-pointer shadow-sm"
          >
            <PlusCircle size={14} className="text-slate-500" />
            New project
          </button>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-6 pt-5">
        
        {/* Quick Zilo Command Bar */}
        <div className="bg-emerald-50/40 border border-emerald-100 rounded-xl p-4 shadow-sm">
          <form onSubmit={handleQuickSubmit} className="flex gap-3">
            <div className="relative flex-1">
              <input
                type="text"
                value={quickInput}
                onChange={(e) => setQuickInput(e.target.value)}
                placeholder="Tell Zilo: 'I signed the NDA', 'Called 3 leads', or paste investor meeting notes here..."
                className="w-full bg-white border border-slate-200 rounded-lg pl-3 pr-10 py-2.5 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
              />
              <Sparkles size={16} className="absolute right-3.5 top-3.5 text-emerald-600/70" />
            </div>
            <button
              type="submit"
              disabled={parsing || !quickInput.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-white border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition disabled:opacity-50 cursor-pointer shadow-sm"
            >
              {parsing ? <Loader2 size={15} className="animate-spin text-slate-500" /> : <Sparkles size={15} className="text-slate-500" />}
              Update Zilo
            </button>
          </form>
        </div>

        {/* Lanes View */}
        {loading ? (
          <div className="flex h-60 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-emerald-600" />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 min-h-[450px]">
            {/* Founder Column */}
            <div
              onDragOver={(e) => handleDragOver(e, "founder")}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, "founder")}
              className={cn(
                "flex flex-col border overflow-hidden shadow-sm transition-all duration-300 rounded-xl",
                activeDropLane === "founder"
                  ? "border-emerald-500 bg-emerald-50/20 scale-[1.01]"
                  : "border-slate-200/80 bg-slate-50/50"
              )}
            >
              <div className="flex items-center justify-between border-b border-slate-200/80 bg-emerald-50/60 px-4 py-3 shrink-0">
                <div className="flex items-center gap-2">
                  <span title="Founder" className="text-emerald-700"><User size={15} /></span>
                  <h2 className="text-xs font-bold uppercase tracking-wider text-emerald-800">MY TASKS · {myTasks.length}</h2>
                </div>
                <span className="text-[11px] font-semibold text-emerald-700">Only you can do these</span>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {myTasks.length === 0 ? (
                  <p className="text-center text-xs text-slate-400 py-10">No tasks in your lane.</p>
                ) : (
                  myTasks.map((task) => {
                    const isProjectTask = task.source.startsWith("Project: ");
                    const pScheme = isProjectTask ? getProjectColorScheme(task.source.replace("Project: ", "")) : null;

                    return (
                      <div
                        key={task.id}
                        draggable={task.status !== "done"}
                        onDragStart={(e) => handleDragStart(e, task, "founder")}
                        onDragEnd={handleDragEnd}
                        className={cn(
                          "group relative rounded-xl border p-4 transition duration-300 shadow-sm flex flex-col gap-3 cursor-grab active:cursor-grabbing",
                          getDueStyle(task),
                          pScheme && task.status !== "done" && `${pScheme.bg} ${pScheme.border}`
                        )}
                      >
                        <div className="flex justify-between items-start gap-4">
                          <div className="flex-1">
                            <h3 className={cn(
                              "text-sm font-bold text-slate-800 leading-snug",
                              task.status === "done" && "line-through text-slate-400"
                            )}>
                              {task.title}
                            </h3>
                            {task.source.startsWith("Project: ") && (
                              <div className="flex flex-wrap items-center gap-2 mt-2">
                                <span className={cn("rounded px-2 py-0.5 text-[10px] font-bold border", getProjectColorScheme(task.source.replace("Project: ", "")).badge)}>
                                  {task.source.replace("Project: ", "")}
                                </span>
                              </div>
                            )}
                            <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-2">
                              {getSourceIcon(task.source)}
                              <span>{task.source}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <button
                              onClick={() => startEditDate(task)}
                              title="Click to set or change the due date"
                              className={cn("rounded px-2 py-0.5 text-[10px] font-bold border whitespace-nowrap hover:ring-1 hover:ring-slate-300 cursor-pointer transition", getDueBadgeStyle(task))}
                            >
                              {getDueBadgeLabel(task)}
                            </button>
                            {task.status !== "done" && (
                              <span className="text-slate-300 group-hover:text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity duration-200 cursor-grab shrink-0">
                                <GripVertical size={14} />
                              </span>
                            )}
                          </div>
                        </div>

                        {renderDueEditor(task)}

                        {task.context && (
                          <p className="text-xs text-slate-500 italic bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                            {task.context}
                          </p>
                        )}

                        {/* Progress bar (data-driven from subtasks) */}
                        {task.sub_tasks && task.sub_tasks.length > 0 && (
                          <div className="space-y-2 border-t border-slate-100 pt-2.5">
                            <div className="flex justify-between text-xs font-semibold text-slate-500">
                              <span />
                              <span>{task.progress || `${task.sub_tasks.filter(s => s.done).length} of ${task.sub_tasks.length} done`}</span>
                            </div>
                            <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                              <div
                                className="bg-lime-600 h-full transition-all duration-300"
                                style={{ width: `${(task.sub_tasks.filter(s => s.done).length / task.sub_tasks.length) * 100}%` }}
                              />
                            </div>
                          </div>
                        )}

                        {/* Card Buttons */}
                        {task.status !== "done" && (
                          <div className="flex items-center gap-2 mt-1 border-t border-slate-100 pt-2.5">
                            <button
                              onClick={() => handleCompleteTask(task.id)}
                              className="rounded-lg border border-slate-200 bg-white text-slate-700 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 shadow-sm transition cursor-pointer"
                            >
                              Done
                            </button>
                            <button
                              onClick={() => setLogTaskId(task.id)}
                              className="rounded-lg border border-slate-200 bg-white text-slate-700 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 shadow-sm transition cursor-pointer"
                            >
                              Log update
                            </button>
                            {isDelegatableTitle(task.title) && (
                              <button
                                onClick={() => handleDelegate(task.id)}
                                className="rounded-lg border border-slate-200 bg-white text-slate-700 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 shadow-sm transition cursor-pointer"
                              >
                                Delegate
                              </button>
                            )}
                            <button
                              onClick={() => handleDeleteTask(task.id)}
                              title="Delete task"
                              className="ml-auto rounded-lg border border-slate-200 bg-white text-slate-400 hover:text-red-500 px-2.5 py-1.5 text-xs font-semibold hover:bg-slate-50 shadow-sm transition cursor-pointer"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Zilo Column */}
            <div
              onDragOver={(e) => handleDragOver(e, "zilo")}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, "zilo")}
              className={cn(
                "flex flex-col border overflow-hidden shadow-sm transition-all duration-300 rounded-xl",
                activeDropLane === "zilo"
                  ? isDraggingDelegatable
                    ? "border-sky-500 bg-sky-50/20 scale-[1.01]"
                    : "border-red-400 bg-red-50/20 scale-[1.01] cursor-no-drop"
                  : "border-slate-200/80 bg-slate-50/50"
              )}
            >
              <div className="flex items-center justify-between border-b border-slate-200/80 bg-sky-50/60 px-4 py-3 shrink-0">
                <div className="flex items-center gap-2">
                  <span title="Zilo" className="text-sky-700"><Bot size={15} /></span>
                  <h2 className="text-xs font-bold uppercase tracking-wider text-sky-800">ZILO'S TASKS · {ziloTasks.length}</h2>
                </div>
                <span className="text-[11px] font-semibold text-sky-700">Zilo is handling these</span>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {ziloTasks.length === 0 ? (
                  <p className="text-center text-xs text-slate-400 py-10">Zilo has no active tasks.</p>
                ) : (
                  ziloTasks.map((task) => {
                    const isMeridianWatch = task.title.toLowerCase().includes("watch");

                    let ziloBadge = "Scheduled";
                    let ziloBadgeStyle = "bg-slate-50 text-slate-700 border-slate-200";

                    if (task.status === "done") {
                      ziloBadge = "Done";
                      ziloBadgeStyle = "bg-emerald-50 text-emerald-700 border-emerald-100";
                    } else if (isMeridianWatch) {
                      ziloBadge = "Watching";
                      ziloBadgeStyle = "bg-sky-50 text-sky-700 border-sky-100";
                    } else if (task.zilo_status === "running") {
                      ziloBadge = "Running";
                      ziloBadgeStyle = "bg-blue-50 text-blue-700 border-blue-100";
                    } else if (task.zilo_status === "scheduled") {
                      ziloBadge = "Scheduled · 6am";
                      ziloBadgeStyle = "bg-slate-50 text-slate-700 border-slate-200";
                    }

                    const isProjectTask = task.source.startsWith("Project: ");
                    const pScheme = isProjectTask ? getProjectColorScheme(task.source.replace("Project: ", "")) : null;

                    return (
                      <div
                        key={task.id}
                        draggable={task.status !== "done"}
                        onDragStart={(e) => handleDragStart(e, task, "zilo")}
                        onDragEnd={handleDragEnd}
                        className={cn(
                          "group relative rounded-xl border p-4 transition duration-300 shadow-sm flex flex-col gap-3 cursor-grab active:cursor-grabbing",
                          getZiloDueStyle(task),
                          pScheme && task.status !== "done" && `${pScheme.bg} ${pScheme.border}`
                        )}
                      >
                        <div className="flex justify-between items-start gap-4">
                          <div className="flex-1">
                            <h3 className={cn(
                              "text-sm font-bold text-slate-800 leading-snug",
                              task.status === "done" && "line-through text-slate-400"
                            )}>
                              {task.title}
                            </h3>
                            {task.source.startsWith("Project: ") && (
                              <div className="flex flex-wrap items-center gap-2 mt-2">
                                <span className={cn("rounded px-2 py-0.5 text-[10px] font-bold border", getProjectColorScheme(task.source.replace("Project: ", "")).badge)}>
                                  {task.source.replace("Project: ", "")}
                                </span>
                              </div>
                            )}
                            <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-2">
                              {getSourceIcon(task.source)}
                              <span>{task.source}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className={cn("rounded px-2 py-0.5 text-[10px] font-bold border whitespace-nowrap", ziloBadgeStyle)}>
                              {ziloBadge}
                            </span>
                            {task.status !== "done" && (
                              <button
                                onClick={() => startEditDate(task)}
                                title="Set or change the due date"
                                className="text-slate-300 hover:text-slate-500 cursor-pointer shrink-0"
                              >
                                <Calendar size={13} />
                              </button>
                            )}
                            {task.status !== "done" && (
                              <span className="text-slate-300 group-hover:text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity duration-200 cursor-grab shrink-0">
                                <GripVertical size={14} />
                              </span>
                            )}
                          </div>
                        </div>

                        {renderDueEditor(task)}

                        {/* Progress Bar (data-driven from subtasks) */}
                        {task.status !== "done" && task.sub_tasks && task.sub_tasks.length > 0 && (
                          <div className="space-y-1">
                            <div className="flex justify-between text-xs font-semibold text-slate-500">
                              <span />
                              <span>{task.progress || `${task.sub_tasks.filter(s => s.done).length} of ${task.sub_tasks.length} done`}</span>
                            </div>
                            <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                              <div
                                className="bg-sky-500 h-full transition-all duration-300"
                                style={{ width: `${(task.sub_tasks.filter(s => s.done).length / task.sub_tasks.length) * 100}%` }}
                              />
                            </div>
                          </div>
                        )}

                        {/* Buttons section */}
                        <div className="flex items-center gap-2 border-t border-slate-100 pt-2.5 mt-1">
                          {task.status !== "done" && (
                            <button
                              onClick={() => openWork(task)}
                              className="flex items-center gap-1.5 rounded-lg border border-sky-200 bg-sky-50 text-sky-800 px-3 py-1.5 text-xs font-semibold hover:bg-sky-100 shadow-sm transition cursor-pointer"
                            >
                              <Sparkles size={12} />
                              Review work
                            </button>
                          )}
                          <button
                            onClick={() => setActiveAuditTask(task)}
                            className="rounded-lg border border-slate-200 bg-white text-slate-700 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 shadow-sm transition cursor-pointer"
                          >
                            View log
                          </button>
                          {task.status !== "done" && (
                            <button
                              onClick={() => handleReassign(task.id)}
                              className="rounded-lg border border-slate-200 bg-white text-slate-700 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 shadow-sm transition cursor-pointer ml-auto text-slate-400 hover:text-slate-600"
                            >
                              Reassign
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        )}

        {/* Dynamic bottom notification banner */}
        <div className="bg-emerald-50/50 border border-emerald-100 p-4 rounded-xl flex items-center justify-center gap-2.5 text-xs text-emerald-800 font-medium shrink-0 shadow-sm">
          <span className="text-sm">💡</span>
          <span>Zilo updates this plan automatically every morning from your calendar, emails, and notes. You just do the work.</span>
        </div>

        {/* Projects Section */}
        <div className="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-200 pb-2 pt-2">
          Projects
        </div>

        <section className="space-y-6">
          {loading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-emerald-600" />
            </div>
          ) : projects.length === 0 ? (
            <p className="text-center text-xs text-slate-500 py-6">No projects defined. Create one to suggest steps.</p>
          ) : (
            projects.map((proj) => {
              const totalSteps = proj.steps.length;
              const completedSteps = proj.steps.filter((s) => s.status === "done").length;
              const pct = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;

              const colorScheme = getProjectColorScheme(proj.name);

              return (
                <div key={proj.id} className={cn("bg-white border rounded-xl p-5 space-y-4 shadow-sm", colorScheme.border)}>
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
                    <div>
                      <h3 className="text-base font-bold text-slate-900 leading-snug">{proj.name}</h3>
                      <p className="text-xs text-slate-500 mt-1">
                        Due {formatShortDate(proj.due_date)} · {completedSteps} of {totalSteps} steps done
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={cn("border rounded-full px-2.5 py-0.5 text-xs font-semibold shadow-sm", colorScheme.badge)}>
                        {formatRelativeDue(proj.due_date)}
                      </span>
                      <button
                        onClick={() => handleDeleteProject(proj.id)}
                        title="Delete project"
                        className="text-slate-300 hover:text-red-500 transition cursor-pointer"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {/* Progress Bar */}
                  <div className="space-y-1">
                    <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                      <div
                        className={cn("h-full transition-all duration-500", colorScheme.progress)}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>

                  {/* Steps list */}
                  <div className="space-y-1 pt-2">
                    {proj.steps.map((step, idx) => {
                      let stepStatusLabel = "Done";
                      let stepStatusStyle = "text-slate-400";

                      if (step.status === "running") {
                        stepStatusLabel = "In progress";
                        stepStatusStyle = "text-sky-600 font-bold";
                      } else if (step.status === "pending") {
                        stepStatusLabel = step.due_date ? formatShortDate(step.due_date) : "Pending";
                        stepStatusStyle = "text-amber-600 font-medium";
                      }

                      return (
                        <div
                          key={idx}
                          className="flex items-center justify-between py-2.5 border-t border-slate-100 text-xs"
                        >
                          <div className="flex items-center gap-3">
                            {/* Step icon */}
                            {step.status === "done" && (
                              <div className="flex items-center justify-center w-5 h-5 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-100">
                                <Check size={12} className="stroke-[3]" />
                              </div>
                            )}
                            {step.status === "running" && (
                              <div className="flex items-center justify-center w-5 h-5 rounded-full bg-sky-50 text-sky-600 border border-sky-100">
                                <ArrowRight size={12} className="stroke-[3]" />
                              </div>
                            )}
                            {step.status === "pending" && (
                              <div className="flex items-center justify-center w-5 h-5 rounded-full bg-slate-50 text-slate-300 border border-slate-200">
                                <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                              </div>
                            )}

                            <span className={cn(
                              "text-slate-700 font-medium",
                              step.status === "done" && "line-through text-slate-400"
                            )}>
                              {step.name}
                            </span>
                          </div>
                          <div className="flex items-center gap-4">
                            {/* Owner Badge */}
                            {step.owner === "founder" ? (
                              <span className="bg-emerald-50 text-emerald-700 border border-emerald-100 rounded-md px-2 py-0.5 text-[10px] font-bold">
                                Me
                              </span>
                            ) : (
                              <span className="bg-sky-50 text-sky-700 border border-sky-100 rounded-md px-2 py-0.5 text-[10px] font-bold">
                                Zilo
                              </span>
                            )}
                            <span className={cn("w-20 text-right text-xs", stepStatusStyle)}>
                              {stepStatusLabel}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })
          )}
        </section>
      </div>

      {/* Add Task Modal */}
      {showAddTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <PlusCircle className="text-emerald-600" size={18} />
              Add new work plan task
            </h2>
            <form onSubmit={handleAddTask} className="space-y-4 text-sm">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600">Task Title</label>
                <input
                  type="text"
                  required
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder="e.g. Call accountant"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600">Owner / Lane</label>
                <select
                  value={taskOwner}
                  onChange={(e) => setTaskOwner(e.target.value as any)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none"
                >
                  <option value="founder">My Lane (Founder)</option>
                  <option value="zilo">Zilo Lane</option>
                </select>
                {taskOwner === "zilo" && (
                  <div className="bg-sky-50 border border-sky-100 rounded-lg p-2.5 space-y-1 text-[11px] leading-relaxed text-slate-700 mt-1.5">
                    <p className="font-bold text-sky-800">🤖 Zilo Lane Guidelines:</p>
                    <ul className="list-disc pl-3.5 space-y-0.5 text-slate-600">
                      <li><strong>What Zilo can do:</strong> Outreach drafts, invoice reminders, client response watching, CRM data updates.</li>
                      <li><strong>What Zilo cannot do:</strong> Signing legal docs/NDAs, phone calls, live meetings, financial payments.</li>
                    </ul>
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600">Due Date</label>
                <input
                  type="datetime-local"
                  value={taskDue}
                  onChange={(e) => setTaskDue(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600">Context Explanation</label>
                <textarea
                  value={taskContext}
                  onChange={(e) => setTaskContext(e.target.value)}
                  placeholder="Why this matters right now..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none h-16 resize-none"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-600">Sub-steps Checklist (Optional)</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newSubTask}
                    onChange={(e) => setNewSubTask(e.target.value)}
                    placeholder="Add step..."
                    className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-800 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={addSubTaskItem}
                    className="rounded-lg bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-sm cursor-pointer"
                  >
                    Add
                  </button>
                </div>
                {taskSubTasks.length > 0 && (
                  <ul className="space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                    {taskSubTasks.map((t, idx) => (
                      <li key={idx} className="text-xs text-slate-600 flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        {t}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="flex gap-3 justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddTask(false)}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50 transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-bold text-white hover:bg-slate-800 transition cursor-pointer"
                >
                  Create Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Log Update Modal */}
      {logTaskId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <FileText className="text-emerald-600" size={18} />
              Log task update
            </h2>
            <form onSubmit={handleLogSubmit} className="space-y-4 text-sm">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600">What happened?</label>
                <textarea
                  required
                  value={logText}
                  onChange={(e) => setLogText(e.target.value)}
                  placeholder="e.g. 'Called 3. Two interested. One said call back next week.'"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:border-emerald-500 h-24 resize-none"
                />
                <p className="text-[10px] text-slate-400 mt-1 italic leading-normal">
                  Zilo will automatically update progress, create follow-up tasks, and update Notebook contacts based on your input.
                </p>
              </div>

              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setLogTaskId(null)}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50 transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loggingUpdate}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-bold text-white hover:bg-slate-800 transition disabled:opacity-50 flex items-center gap-1.5 cursor-pointer"
                >
                  {loggingUpdate && <Loader2 size={13} className="animate-spin" />}
                  Log Update
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Project Modal / Suggester */}
      {showAddProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-xl w-full p-6 space-y-4 max-h-[90vh] overflow-y-auto shadow-xl">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Sparkles className="text-emerald-600" size={18} />
              Create new project with Zilo AI steps
            </h2>
            <div className="space-y-4 text-sm">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600">Project Name</label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. ProductHunt Launch"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600">Project Goal</label>
                <input
                  type="text"
                  value={projectGoal}
                  onChange={(e) => setProjectGoal(e.target.value)}
                  placeholder="What is the main goal in one sentence?"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600">Target Launch Date</label>
                <input
                  type="date"
                  value={projectDue}
                  onChange={(e) => setProjectDue(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleSuggestSteps}
                  disabled={suggesting}
                  className="rounded-lg bg-emerald-50 border border-emerald-100 text-emerald-800 px-4 py-2 text-xs font-semibold hover:bg-emerald-100 transition disabled:opacity-50 flex items-center gap-1.5 cursor-pointer"
                >
                  {suggesting && <Loader2 size={13} className="animate-spin" />}
                  Suggest Project Steps
                </button>
              </div>

              {suggestedSteps.length > 0 && (
                <div className="space-y-3 border-t border-slate-100 pt-3.5">
                  <p className="text-xs font-bold text-slate-800">Zilo suggested steps:</p>
                  <ul className="space-y-2 bg-slate-50 p-3 rounded-lg border border-slate-200/60">
                    {suggestedSteps.map((step, idx) => (
                      <li key={idx} className="flex justify-between items-center text-xs">
                        <div className="flex items-center gap-1.5">
                          {step.owner === "founder" ? <span className="text-emerald-700"><User size={12} /></span> : <span className="text-sky-700"><Bot size={12} /></span>}
                          <span className="text-slate-700 font-medium">{step.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200/40">
                            {formatShortDate(step.due_date)}
                          </span>
                          <span className="text-[10px] rounded bg-slate-100 px-1.5 py-0.5 text-slate-500 font-mono capitalize">
                            {step.owner}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>

                  <div className="flex gap-3 justify-end pt-2">
                    <button
                      type="button"
                      onClick={() => {
                        setSuggestedSteps([]);
                      }}
                      className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50 transition cursor-pointer"
                    >
                      Clear Suggestions
                    </button>
                    <button
                      type="button"
                      onClick={handleConfirmProject}
                      disabled={confirmingProject}
                      className="rounded-lg bg-slate-900 text-white px-4 py-2 text-xs font-bold hover:bg-slate-800 transition disabled:opacity-50 flex items-center gap-1.5 cursor-pointer"
                    >
                      {confirmingProject && <Loader2 size={13} className="animate-spin" />}
                      Confirm project steps & create
                    </button>
                  </div>
                </div>
              )}

              {suggestedSteps.length === 0 && (
                <div className="flex gap-3 justify-end border-t border-slate-100 pt-3.5">
                  <button
                    type="button"
                    onClick={() => setShowAddProject(false)}
                    className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50 transition cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Zilo Work Review Modal — real output from the Delegate engine */}
      {workTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Bot className="text-sky-700" size={18} />
              Zilo&apos;s Work
            </h2>
            <p className="text-xs font-bold text-slate-800">{workTask.title}</p>

            {workLoading ? (
              <div className="flex h-32 items-center justify-center">
                <Loader2 className="h-5 w-5 animate-spin text-sky-600" />
              </div>
            ) : workData?.demo ? (
              <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-xs text-amber-800">
                Task execution needs a live workspace and isn&apos;t available in demo mode.
              </div>
            ) : !workData || workData.status === "not_run" ? (
              <div className="space-y-3">
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-600">
                  Zilo hasn&apos;t run this task yet. Run it now and Zilo will gather the relevant contacts and stage drafts for your review.
                </div>
                <button
                  onClick={() => handleRunTask(workTask)}
                  disabled={runningTask}
                  className="flex items-center gap-1.5 rounded-lg bg-slate-900 text-white px-4 py-2 text-xs font-bold hover:bg-slate-800 transition disabled:opacity-50 cursor-pointer"
                >
                  {runningTask ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                  Run now
                </button>
              </div>
            ) : (
              <div className="space-y-3 text-xs text-slate-700">
                {workData.result_summary && (
                  <p className="bg-sky-50 border border-sky-100 rounded-lg p-3 text-sky-800 font-medium">
                    {workData.result_summary}
                  </p>
                )}
                {(workData.status === "running" || runningTask) && (
                  <div className="flex items-center gap-2 text-slate-500">
                    <Loader2 size={13} className="animate-spin" />
                    Zilo is working{workData.progress ? ` — ${workData.progress.done}/${workData.progress.total}` : "…"}
                  </div>
                )}

                {workData.drafts.length === 0 ? (
                  <p className="text-slate-400 italic py-4 text-center">No drafts staged yet.</p>
                ) : (
                  <div className="space-y-3 max-h-[50vh] overflow-y-auto">
                    {workData.drafts.map((d) => (
                      <div key={d.id} className="border border-slate-200 rounded-xl p-3 bg-slate-50 space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-bold text-slate-800">{d.label || "Contact"}</p>
                          <span className="flex items-center gap-1.5 shrink-0">
                            {d.channel && (
                              <span className="text-[10px] text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200 capitalize">{d.channel}</span>
                            )}
                            <span className={cn(
                              "text-[10px] px-1.5 py-0.5 rounded border font-semibold capitalize",
                              d.approval === "approved" ? "bg-emerald-50 text-emerald-700 border-emerald-100" :
                              d.approval === "rejected" ? "bg-red-50 text-red-700 border-red-100" :
                              "bg-amber-50 text-amber-700 border-amber-100"
                            )}>
                              {d.approval || "pending"}
                            </span>
                          </span>
                        </div>
                        {d.detail && <p className="text-[10px] text-slate-400">{d.detail}</p>}
                        <div className="bg-white p-2.5 rounded-lg border border-slate-200 font-mono text-[11px] whitespace-pre-wrap text-slate-700">
                          {d.draft || "(empty draft)"}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex items-center gap-2 justify-between pt-1">
                  <button
                    onClick={() => refreshWork(workTask.id)}
                    className="rounded-lg border border-slate-200 bg-white text-slate-600 px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 transition cursor-pointer"
                  >
                    Refresh
                  </button>
                  {workData.drafts.length > 0 && (workData.pending ?? 0) > 0 && (
                    <button
                      onClick={() => handleApproveWork(workTask)}
                      disabled={approvingWork}
                      className="flex items-center gap-1.5 rounded-lg bg-emerald-600 text-white px-4 py-2 text-xs font-bold hover:bg-emerald-700 transition disabled:opacity-50 cursor-pointer"
                    >
                      {approvingWork && <Loader2 size={13} className="animate-spin" />}
                      Approve &amp; send all
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="flex justify-end border-t border-slate-100 pt-3">
              <button
                type="button"
                onClick={() => { setWorkTask(null); setWorkData(null); }}
                className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50 shadow-sm transition cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Audit Log / View Log Modal */}
      {activeAuditTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Scale className="text-emerald-600" size={18} />
              Zilo Task Audit Log
            </h2>
            <div className="space-y-4 text-xs">
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg space-y-2">
                <p className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">Task:</p>
                <p className="text-slate-800 text-sm font-semibold">{activeAuditTask.title}</p>
                <p className="text-slate-500 text-xs mt-1">{activeAuditTask.context || "No context provided"}</p>
              </div>

              {activeAuditTask.result && (
                <div className="bg-emerald-50/50 border border-emerald-100 p-3 rounded-lg space-y-1">
                  <p className="text-emerald-700 font-semibold uppercase tracking-wider text-[10px]">Result:</p>
                  <p className="text-slate-700 text-xs">{activeAuditTask.result}</p>
                </div>
              )}

              <div className="space-y-2">
                <p className="text-slate-400 font-semibold uppercase tracking-wider text-[10px]">Audit Trail:</p>
                <ul className="space-y-2 pl-2 border-l-2 border-slate-200">
                  <li className="relative pl-3">
                    <span className="absolute -left-[11px] top-1.5 h-1.5 w-1.5 rounded-full bg-slate-400" />
                    <p className="font-semibold text-slate-600">Task created via {activeAuditTask.source}</p>
                    <p className="text-[10px] text-slate-400">{new Date(activeAuditTask.created_at).toLocaleString()}</p>
                  </li>
                  <li className="relative pl-3">
                    <span className="absolute -left-[11px] top-1.5 h-1.5 w-1.5 rounded-full bg-slate-400" />
                    <p className="font-semibold text-slate-600">Assigned to {activeAuditTask.owner}</p>
                    <p className="text-[10px] text-slate-400">System initialization</p>
                  </li>
                  {activeAuditTask.status === "done" && (
                    <li className="relative pl-3">
                      <span className="absolute -left-[11px] top-1.5 h-1.5 w-1.5 rounded-full bg-emerald-600" />
                      <p className="font-semibold text-emerald-600">Status updated to Done</p>
                      {activeAuditTask.completed_at && (
                        <p className="text-[10px] text-slate-400">{new Date(activeAuditTask.completed_at).toLocaleString()}</p>
                      )}
                    </li>
                  )}
                </ul>
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => setActiveAuditTask(null)}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-50 transition cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

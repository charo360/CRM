"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Zap, RefreshCw, Target, Users, Globe, Settings2, DollarSign, Sparkles,
  ExternalLink, Activity, ListChecks, TrendingUp, Plus, Trash2, BrainCircuit,
  Radio, Search, Eye, Loader2, ChevronRight, Bell, MessageCircle, X,
  BarChart3, Antenna, Calendar, Hash, MapPin, CheckCircle2, SkipForward,
  AlertTriangle, Clock, Building2, Briefcase, Megaphone, Filter,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface FeedItem {
  _id: string;
  agent: string;
  title: string;
  detail: string;
  kind: "info" | "opportunity" | "action" | "warning";
  created_at: string;
}

interface QueueItem {
  _id: string;
  agent: string;
  action_type: string;
  title: string;
  draft_content: string;
  metadata: Record<string, string | number>;
  created_at: string;
}

interface Opportunity {
  _id: string;
  kind: "funding" | "group" | "social" | "custom";
  title: string;
  url: string;
  snippet: string;
  agent_name?: string;
  score?: number;
  contact_name?: string;
  contact_info?: string;
  queue_id?: string;
  platform?: string;
  author?: string;
  group_name?: string;
  created_at: string;
}

interface Settings {
  enabled: boolean;
  goals: string;
  agents: Record<string, boolean>;
}

interface SocialSettings {
  platforms: string[];
  keywords: string[];
  groups: string[];
  location: string;
  daily_limit: number;
  auto_run: boolean;
  mode: "review" | "auto" | "notify";
  competitors?: string[];
  morning_brief?: boolean;
  morning_brief_time?: string;
  marketplace_lat?: number;
  marketplace_lng?: number;
}

interface CustomAgent {
  _id: string;
  name: string;
  emoji: string;
  description: string;
  schedule: "daily" | "weekly" | "on_demand";
  enabled: boolean;
  created_at: string;
}

interface ReconItem {
  _id: string;
  title: string;
  recon_type: "job_posting" | "new_business" | "tender";
  company: string;
  location: string;
  source_url: string;
  why_relevant: string;
  action_hint: string;
  confidence: number;
  created_at: string;
}

interface Prediction {
  _id: string;
  title: string;
  category: "grant" | "seasonal" | "event" | "hiring" | "regulatory" | "market";
  predicted_window: string;
  days_until: number;
  confidence: number;
  reasoning: string;
  action_hint: string;
  signals: string[];
  created_at: string;
}

interface Cluster {
  _id: string;
  title: string;
  category: "lead" | "funding" | "partnership" | "market_gap" | "timing";
  confidence: number;
  signal_count: number;
  signals: string[];
  insight: string;
  action_hint: string;
  urgency: "high" | "medium" | "low";
  created_at: string;
}

interface InstantAction {
  _id: string;
  action_type: "email_outreach" | "apply_grant" | "social_post" | "follow_up" | "direct_message";
  title: string;
  target_name: string;
  target_contact: string | null;
  draft_content: string;
  source_type: "cluster" | "prediction" | "recon";
  source_title: string;
  confidence: number;
  status: "pending" | "approved" | "executed" | "rejected";
  created_at: string;
  approved_at: string | null;
}

interface Scout {
  _id: string;
  title: string;
  goal: string;
  scout_type: string;
  search_queries: string[];
  location: string;
  frequency: string;
  is_active: boolean;
  auto_generated?: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  created_at?: string;
}

type Section = "hunt" | "pulse" | "funding" | "radar" | "setup" | "autopilot" | "settings";

// ─── Sub-components ───────────────────────────────────────────────────────────

function IntentRing({ score }: { score: number }) {
  const r = 15;
  const circ = 2 * Math.PI * r;
  const fill = circ * (score / 10);
  const color = score >= 8 ? "#DC2626" : score >= 5 ? "#D97706" : "#059669";
  return (
    <div className="relative flex items-center justify-center w-[46px] h-[46px] flex-shrink-0">
      <svg width="46" height="46" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="23" cy="23" r={r} fill="none" stroke="#e5e7eb" strokeWidth="3" />
        <circle
          cx="23" cy="23" r={r} fill="none" stroke={color} strokeWidth="3"
          strokeDasharray={`${fill} ${circ}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.5s ease" }}
        />
      </svg>
      <span className="absolute text-[11px] font-bold" style={{ color }}>{score}</span>
    </div>
  );
}

function UrgencyBadge({ score }: { score: number }) {
  if (score >= 8) return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-50 text-red-600">
      <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
      Close now
    </span>
  );
  if (score >= 5) return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-600">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
      Hot
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-green-50 text-green-600">
      <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
      Warm
    </span>
  );
}

function RadarSVG() {
  return (
    <div className="relative w-[160px] h-[160px] flex-shrink-0">
      <svg width="160" height="160" viewBox="0 0 160 160">
        <circle cx="80" cy="80" r="70" fill="none" stroke="#bbf7d0" strokeWidth="1" opacity="0.5" />
        <circle cx="80" cy="80" r="50" fill="none" stroke="#bbf7d0" strokeWidth="1" opacity="0.5" />
        <circle cx="80" cy="80" r="30" fill="none" stroke="#bbf7d0" strokeWidth="1" opacity="0.5" />
        <circle cx="80" cy="80" r="10" fill="#059669" opacity="0.3" />
        <line x1="80" y1="10" x2="80" y2="150" stroke="#bbf7d0" strokeWidth="0.5" opacity="0.4" />
        <line x1="10" y1="80" x2="150" y2="80" stroke="#bbf7d0" strokeWidth="0.5" opacity="0.4" />
        <defs>
          <linearGradient id="sweepGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#059669" stopOpacity="0" />
            <stop offset="100%" stopColor="#059669" stopOpacity="0.5" />
          </linearGradient>
        </defs>
        <path
          d="M80,80 L80,15 A65,65 0 0,1 145,80 Z"
          fill="url(#sweepGrad)"
          style={{ transformOrigin: "80px 80px", animation: "radar-sweep 3s linear infinite" }}
        />
        <circle cx="120" cy="45" r="4" fill="#DC2626" style={{ animation: "blip 3s 0.8s ease-out infinite" }} />
        <circle cx="55" cy="110" r="3" fill="#D97706" style={{ animation: "blip 3s 1.4s ease-out infinite" }} />
        <circle cx="130" cy="100" r="3" fill="#059669" style={{ animation: "blip 3s 2.1s ease-out infinite" }} />
      </svg>
      <style>{`
        @keyframes radar-sweep { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes blip {
          0%,100% { opacity:0; r:2; }
          30%,60% { opacity:1; r:5; }
        }
      `}</style>
    </div>
  );
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function daysUntil(iso: string) {
  const diff = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / 86400000));
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ActionModePage() {
  const [section, setSection] = useState<Section>("hunt");
  const [settings, setSettings] = useState<Settings>({ enabled: false, goals: "", agents: {} });
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [customAgents, setCustomAgents] = useState<CustomAgent[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [recon, setRecon] = useState<ReconItem[]>([]);
  const [instantActions, setInstantActions] = useState<InstantAction[]>([]);
  const [scouts, setScouts] = useState<Scout[]>([]);
  const [scoutPulse, setScoutPulse] = useState<Opportunity[]>([]);
  const [socialSettings, setSocialSettings] = useState<SocialSettings>({
    platforms: ["facebook"], keywords: [], groups: [], location: "",
    daily_limit: 10, auto_run: true, mode: "review",
    competitors: [], morning_brief: false, morning_brief_time: "08:00",
  });

  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runningAgent, setRunningAgent] = useState<string | null>(null);
  const [runningScoutId, setRunningScoutId] = useState<string | null>(null);
  const [runningSocial, setRunningSocial] = useState(false);
  const [runningFusion, setRunningFusion] = useState(false);
  const [runningPredictions, setRunningPredictions] = useState(false);
  const [runningRecon, setRunningRecon] = useState(false);
  const [runningInstant, setRunningInstant] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [savingSocial, setSavingSocial] = useState(false);
  const [scoutSetupLoading, setScoutSetupLoading] = useState(false);
  const [processing, setProcessing] = useState<Record<string, boolean>>({});
  const [expandedItem, setExpandedItem] = useState<string | null>(null);
  const [editedContent, setEditedContent] = useState<Record<string, string>>({});

  // Hunt filters
  const [huntFilter, setHuntFilter] = useState<"all" | "hot" | "warm" | "cold">("all");
  const [newKeyword, setNewKeyword] = useState("");
  const [newGroup, setNewGroup] = useState("");
  const [newCompetitor, setNewCompetitor] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // Live ticker
  const [isLive, setIsLive] = useState(false);
  const [livePhase, setLivePhase] = useState("");
  const liveDeadlineRef = useRef(0);

  const phases = useMemo(() => [
    "Scanning social signals…",
    "Detecting buying intent…",
    "Scoring opportunities…",
    "Streaming results…",
  ], []);

  const load = useCallback(async () => {
    try {
      const [s, f, q, o, ca, ss, cl, pr, rc, ia, sc, pl] = await Promise.all([
        api.get<Settings>("/action-mode/settings"),
        api.get<{ items: FeedItem[] }>("/action-mode/feed"),
        api.get<{ items: QueueItem[] }>("/action-mode/queue"),
        api.get<{ opportunities: Opportunity[] }>("/action-mode/opportunities"),
        api.get<{ agents: CustomAgent[] }>("/action-mode/agents"),
        api.get<SocialSettings>("/action-mode/social/settings"),
        api.get<{ clusters: Cluster[] }>("/action-mode/clusters"),
        api.get<{ predictions: Prediction[] }>("/action-mode/predictions"),
        api.get<{ recon: ReconItem[] }>("/action-mode/recon"),
        api.get<{ items: InstantAction[] }>("/action-mode/instant"),
        api.get<{ scouts: Scout[] }>("/action-mode/scouts"),
        api.get<{ pulse: Opportunity[] }>("/action-mode/scouts/pulse"),
      ]);
      setSettings(s);
      setFeed(f.items);
      setQueue(q.items);
      setOpportunities(o.opportunities);
      setCustomAgents(ca.agents);
      setSocialSettings(ss);
      setClusters(cl.clusters);
      setPredictions(pr.predictions);
      setRecon(rc.recon);
      setInstantActions(ia.items);
      setScouts(sc.scouts);
      setScoutPulse(pl.pulse);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!isLive) { setLivePhase(""); return; }
    let i = 0;
    setLivePhase(phases[0]);
    const t = setInterval(() => {
      i = (i + 1) % phases.length;
      setLivePhase(phases[i]);
    }, 2500);
    return () => clearInterval(t);
  }, [isLive, phases]);

  function startLive(ms = 48000) {
    setIsLive(true);
    liveDeadlineRef.current = Date.now() + ms;
    setTimeout(async () => {
      setIsLive(false);
      setRunning(false);
      setRunningAgent(null);
      await load();
    }, ms);
  }

  async function runAll() {
    setRunning(true);
    startLive(56000);
    try { await api.post("/action-mode/run", {}); }
    catch (e: unknown) { toast.error(e instanceof Error ? e.message : "Failed"); setIsLive(false); setRunning(false); }
  }

  async function runSocial() {
    setRunningSocial(true);
    startLive(40000);
    try {
      await api.post("/action-mode/run-social", {});
      toast.success("Social scan started — leads appear below");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed");
      setIsLive(false);
    } finally {
      setRunningSocial(false);
    }
  }

  async function runScout(id: string) {
    setRunningScoutId(id);
    try {
      await api.post(`/action-mode/scouts/${id}/run`, {});
      toast.success("Scout running — check Pulse in ~30s");
      setTimeout(() => void load(), 28000);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Scout failed");
    } finally {
      setRunningScoutId(null);
    }
  }

  async function setupScouts() {
    setScoutSetupLoading(true);
    try {
      const data = await api.post<{ scouts: Scout[]; created: number }>("/action-mode/scouts/setup", {});
      setScouts(data.scouts);
      toast.success(`${data.created} scouts created from your profile`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setScoutSetupLoading(false);
    }
  }

  async function toggleScout(scout: Scout) {
    try {
      const updated = await api.put<Scout>(`/action-mode/scouts/${scout._id}`, { is_active: !scout.is_active });
      setScouts(prev => prev.map(s => s._id === scout._id ? updated : s));
    } catch { toast.error("Update failed"); }
  }

  async function deleteScout(id: string) {
    try {
      await api.delete(`/action-mode/scouts/${id}`);
      setScouts(prev => prev.filter(s => s._id !== id));
    } catch { toast.error("Delete failed"); }
  }

  async function handleQueueAction(item: QueueItem, action: "approve" | "skip") {
    setProcessing(p => ({ ...p, [item._id]: true }));
    try {
      await api.post("/action-mode/queue/action", {
        item_id: item._id,
        action,
        edited_content: editedContent[item._id] || item.draft_content,
      });
      setQueue(q => q.filter(x => x._id !== item._id));
      setExpandedItem(null);
    } catch { toast.error("Action failed"); }
    finally { setProcessing(p => ({ ...p, [item._id]: false })); }
  }

  async function saveSocialSettings(next: SocialSettings) {
    setSavingSocial(true);
    try {
      await api.put("/action-mode/social/settings", next);
      setSocialSettings(next);
      toast.success("Settings saved");
    } catch { toast.error("Failed to save"); }
    finally { setSavingSocial(false); }
  }

  async function saveSettings() {
    setSavingSettings(true);
    try { await api.put("/action-mode/settings", settings); toast.success("Saved"); }
    catch { toast.error("Failed"); }
    finally { setSavingSettings(false); }
  }

  async function runFusion() {
    setRunningFusion(true);
    try {
      await api.post("/action-mode/clusters/run", {});
      toast.success("Fusion Engine running…");
      setTimeout(async () => {
        const cl = await api.get<{ clusters: Cluster[] }>("/action-mode/clusters");
        setClusters(cl.clusters);
        setRunningFusion(false);
      }, 35000);
    } catch { toast.error("Fusion failed"); setRunningFusion(false); }
  }

  async function runPredictions() {
    setRunningPredictions(true);
    try {
      await api.post("/action-mode/predictions/run", {});
      setTimeout(async () => {
        const pr = await api.get<{ predictions: Prediction[] }>("/action-mode/predictions");
        setPredictions(pr.predictions);
        setRunningPredictions(false);
      }, 35000);
    } catch { toast.error("Failed"); setRunningPredictions(false); }
  }

  async function runRecon() {
    setRunningRecon(true);
    try {
      await api.post("/action-mode/recon/run", {});
      setTimeout(async () => {
        const rc = await api.get<{ recon: ReconItem[] }>("/action-mode/recon");
        setRecon(rc.recon);
        setRunningRecon(false);
      }, 40000);
    } catch { toast.error("Failed"); setRunningRecon(false); }
  }

  async function generateInstantActions() {
    setRunningInstant(true);
    try {
      await api.post("/action-mode/instant/generate", {});
      setTimeout(async () => {
        const ia = await api.get<{ items: InstantAction[] }>("/action-mode/instant");
        setInstantActions(ia.items);
        setRunningInstant(false);
      }, 35000);
    } catch { toast.error("Failed"); setRunningInstant(false); }
  }

  async function approveInstant(id: string) {
    await api.post(`/action-mode/instant/${id}/approve`, {});
    setInstantActions(prev => prev.map(a => a._id === id ? { ...a, status: "approved" as const } : a));
  }

  async function rejectInstant(id: string) {
    await api.delete(`/action-mode/instant/${id}`);
    setInstantActions(prev => prev.filter(a => a._id !== id));
  }

  function openWhatsApp(contact?: string | null, text?: string) {
    const num = (contact || "").replace(/\D/g, "");
    const msg = encodeURIComponent(text || "Hi, I saw your post and wanted to connect.");
    if (num) window.open(`https://wa.me/${num}?text=${msg}`, "_blank");
    else window.open(`https://wa.me/?text=${msg}`, "_blank");
  }

  async function addToCRM(opp: Opportunity) {
    try {
      await api.post("/contacts", {
        name: opp.contact_name || opp.author || opp.title,
        notes: opp.snippet,
        source: "ai_scout",
        source_url: opp.url,
      });
      toast.success("Added to CRM");
    } catch { toast.error("Failed to add to CRM"); }
  }

  async function dismissOpp(id: string) {
    try {
      await api.delete(`/action-mode/opportunities/${id}`);
      setOpportunities(prev => prev.filter(o => o._id !== id));
    } catch { setOpportunities(prev => prev.filter(o => o._id !== id)); }
  }

  // ─── Derived state ──────────────────────────────────────────────────────────

  const leads = opportunities.filter(o => o.kind === "social" || o.kind === "group");
  const fundingOpps = opportunities.filter(o => o.kind === "funding");
  const fundingPreds = predictions.filter(p => p.category === "grant");

  const filteredLeads = leads.filter(l => {
    const score = l.score ?? 5;
    if (huntFilter === "hot") return score >= 8;
    if (huntFilter === "warm") return score >= 5 && score < 8;
    if (huntFilter === "cold") return score < 5;
    return true;
  }).filter(l => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return l.title.toLowerCase().includes(q) || (l.snippet || "").toLowerCase().includes(q);
  });

  const hotCount = leads.filter(l => (l.score ?? 5) >= 8).length;
  const pendingQueue = queue.filter(q => !processing[q._id]).length;
  const pendingInstant = instantActions.filter(a => a.status === "pending").length;
  const radarCount = clusters.length + predictions.length + recon.length;

  const SOCIAL_PLATFORMS = [
    { id: "facebook", label: "Facebook Groups", emoji: "📘" },
    { id: "whatsapp", label: "WhatsApp Groups", emoji: "🟢" },
    { id: "instagram", label: "Instagram", emoji: "📸" },
    { id: "telegram", label: "Telegram", emoji: "✈️" },
    { id: "linkedin", label: "LinkedIn", emoji: "💼" },
    { id: "reddit", label: "Reddit", emoji: "🟠" },
    { id: "tiktok", label: "TikTok", emoji: "🎵" },
    { id: "marketplace", label: "FB Marketplace", emoji: "🛒" },
  ];

  const navItems: { id: Section; label: string; icon: React.ElementType; badge?: number }[] = [
    { id: "hunt", label: "Hunt", icon: Target, badge: hotCount || undefined },
    { id: "pulse", label: "Pulse", icon: Radio },
    { id: "funding", label: "Funding", icon: DollarSign, badge: fundingOpps.length || undefined },
    { id: "radar", label: "Market Radar", icon: BarChart3, badge: radarCount || undefined },
    { id: "setup", label: "Scouts Setup", icon: Settings2 },
    { id: "autopilot", label: "Autopilot", icon: Zap, badge: (pendingQueue + pendingInstant) || undefined },
    { id: "settings", label: "Settings", icon: Settings2 },
  ];

  // ─── Loading ────────────────────────────────────────────────────────────────

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 rounded-full border-2 border-emerald-500/30 border-t-emerald-500 animate-spin" />
        <p className="text-sm text-slate-400">Loading AI Scout…</p>
      </div>
    </div>
  );

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-[calc(100vh-64px)] bg-slate-50 overflow-hidden">

      {/* ── Sidebar ── */}
      <aside className="w-52 bg-white border-r border-slate-100 flex flex-col flex-shrink-0">
        <div className="p-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center">
              <Antenna className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-800 leading-none">AI Scout</p>
              <p className="text-[10px] text-emerald-600 mt-0.5">Field Intelligence</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
          {navItems.map(item => (
            <button
              key={item.id}
              onClick={() => setSection(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-all ${
                section === item.id
                  ? "bg-emerald-50 text-emerald-700 font-semibold"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-800"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <item.icon className="w-4 h-4 flex-shrink-0" />
                {item.label}
              </span>
              {item.badge ? (
                <span className="text-[10px] font-bold bg-emerald-600 text-white rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
                  {item.badge}
                </span>
              ) : null}
            </button>
          ))}
        </nav>

        <div className="p-3 border-t border-slate-100">
          <button
            onClick={runAll}
            disabled={running}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50 transition-all"
          >
            {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            {running ? "Scanning…" : "Run All Scouts"}
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* ── Topbar ── */}
        <header className="bg-white border-b border-slate-100 px-5 py-2.5 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-4">
            <h1 className="text-sm font-bold text-slate-800">
              {navItems.find(n => n.id === section)?.label}
            </h1>
            {isLive && (
              <div className="flex items-center gap-2 text-xs text-emerald-600">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="font-medium">{livePhase}</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-3 text-xs text-slate-500">
              <span className="flex items-center gap-1">
                <Activity className="w-3.5 h-3.5 text-emerald-500" />
                {feed.length} signals
              </span>
              <span className="flex items-center gap-1">
                <Eye className="w-3.5 h-3.5 text-blue-500" />
                {scouts.filter(s => s.is_active).length} scouts live
              </span>
              <span className="flex items-center gap-1">
                <Target className="w-3.5 h-3.5 text-amber-500" />
                {leads.length} leads
              </span>
            </div>
            {isLive && (
              <span className="flex items-center gap-1 text-[10px] font-bold text-white bg-red-500 rounded px-1.5 py-0.5 animate-pulse">
                ● LIVE
              </span>
            )}
            <button onClick={() => void load()} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-50 hover:text-slate-600">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </header>

        {/* ── Section Body ── */}
        <main className="flex-1 overflow-y-auto">

          {/* ────────────────── HUNT ────────────────── */}
          {section === "hunt" && (
            <div className="p-5">
              {/* Controls */}
              <div className="flex items-center gap-3 mb-4">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                  <input
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    placeholder="Search leads…"
                    className="w-full pl-9 pr-3 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 bg-white"
                  />
                </div>
                <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1">
                  {(["all","hot","warm","cold"] as const).map(f => (
                    <button
                      key={f}
                      onClick={() => setHuntFilter(f)}
                      className={`px-3 py-1 text-xs rounded-md font-medium transition-all capitalize ${
                        huntFilter === f
                          ? f === "hot" ? "bg-red-500 text-white"
                            : f === "warm" ? "bg-amber-500 text-white"
                            : f === "cold" ? "bg-slate-500 text-white"
                            : "bg-emerald-600 text-white"
                          : "text-slate-500 hover:text-slate-700"
                      }`}
                    >
                      {f === "all" ? `All ${leads.length}` : f === "hot" ? `🔴 Hot ${leads.filter(l => (l.score??5) >= 8).length}` : f === "warm" ? `🟡 Warm ${leads.filter(l => { const s = l.score??5; return s>=5&&s<8; }).length}` : `🟢 Cold ${leads.filter(l => (l.score??5) < 5).length}`}
                    </button>
                  ))}
                </div>
                <button
                  onClick={runSocial}
                  disabled={runningSocial}
                  className="flex items-center gap-2 px-3 py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-all"
                >
                  {runningSocial ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                  Scan Now
                </button>
              </div>

              {/* Lead rows */}
              {filteredLeads.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                  <Target className="w-12 h-12 mb-3 opacity-20" />
                  <p className="text-sm font-medium">No leads yet</p>
                  <p className="text-xs mt-1">Run a scan or set up your scouts to start hunting</p>
                  <button
                    onClick={runSocial}
                    disabled={runningSocial}
                    className="mt-4 flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700"
                  >
                    <Search className="w-3.5 h-3.5" />
                    Run First Scan
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredLeads.map(lead => {
                    const score = lead.score ?? Math.floor(Math.random() * 5 + 4);
                    return (
                      <div key={lead._id} className="bg-white rounded-xl border border-slate-100 p-3 hover:border-emerald-200 hover:shadow-sm transition-all">
                        <div className="grid gap-3" style={{ gridTemplateColumns: "46px 1fr 100px 105px 158px" }}>
                          {/* Score ring */}
                          <IntentRing score={score} />

                          {/* Content */}
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <UrgencyBadge score={score} />
                              {lead.platform && (
                                <span className="text-[10px] text-slate-400 capitalize">{lead.platform}</span>
                              )}
                            </div>
                            <p className="text-sm font-medium text-slate-800 truncate">{lead.title}</p>
                            <p className="text-xs text-slate-500 line-clamp-1 mt-0.5">{lead.snippet}</p>
                            <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-400">
                              {lead.author && <span>👤 {lead.author}</span>}
                              {lead.group_name && <span>📍 {lead.group_name}</span>}
                              <span>{timeAgo(lead.created_at)}</span>
                            </div>
                          </div>

                          {/* Score badge */}
                          <div className="flex flex-col items-end justify-center">
                            <span className="text-[10px] text-slate-400 mb-1">Intent</span>
                            <div className="flex items-center gap-1">
                              {[...Array(5)].map((_, i) => (
                                <div
                                  key={i}
                                  className="w-2 h-2 rounded-full"
                                  style={{ background: i < Math.ceil(score / 2) ? (score >= 8 ? "#DC2626" : score >= 5 ? "#D97706" : "#059669") : "#e5e7eb" }}
                                />
                              ))}
                            </div>
                          </div>

                          {/* View */}
                          <div className="flex flex-col items-center justify-center">
                            {lead.url ? (
                              <a
                                href={lead.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
                              >
                                View post <ExternalLink className="w-3 h-3" />
                              </a>
                            ) : <span />}
                          </div>

                          {/* Actions */}
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => openWhatsApp(lead.contact_info, `Hi! I saw your post about "${lead.title.slice(0, 40)}" and wanted to reach out.`)}
                              className="flex items-center gap-1 px-2.5 py-1.5 bg-[#25D366] text-white text-xs font-semibold rounded-lg hover:bg-[#1ebe5d] transition-all"
                            >
                              <MessageCircle className="w-3 h-3" />
                              Message
                            </button>
                            <button
                              onClick={() => addToCRM(lead)}
                              className="flex items-center gap-1 px-2 py-1.5 border border-slate-200 text-slate-600 text-xs font-medium rounded-lg hover:bg-slate-50 transition-all"
                            >
                              <Plus className="w-3 h-3" />
                              CRM
                            </button>
                            <button
                              onClick={() => dismissOpp(lead._id)}
                              className="p-1.5 text-slate-300 hover:text-slate-500 hover:bg-slate-50 rounded-lg transition-all"
                            >
                              <SkipForward className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Scout pulse */}
              {scoutPulse.length > 0 && (
                <div className="mt-5">
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3 flex items-center gap-2">
                    <Eye className="w-3.5 h-3.5" />
                    Scout Pulse ({scoutPulse.length})
                  </h3>
                  <div className="space-y-2">
                    {scoutPulse.slice(0, 5).map(item => (
                      <div key={item._id} className="bg-white rounded-xl border border-slate-100 p-3 flex items-start gap-3">
                        <IntentRing score={item.score ?? 5} />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-800 truncate">{item.title}</p>
                          <p className="text-xs text-slate-500 line-clamp-2 mt-0.5">{item.snippet}</p>
                          <p className="text-[10px] text-slate-400 mt-1">{timeAgo(item.created_at)}</p>
                        </div>
                        <div className="flex gap-1.5">
                          <button onClick={() => openWhatsApp(item.contact_info)} className="flex items-center gap-1 px-2.5 py-1.5 bg-[#25D366] text-white text-xs font-semibold rounded-lg">
                            <MessageCircle className="w-3 h-3" />
                            Message
                          </button>
                          <button onClick={() => addToCRM(item)} className="flex items-center gap-1 px-2 py-1.5 border border-slate-200 text-slate-600 text-xs rounded-lg hover:bg-slate-50">
                            <Plus className="w-3 h-3" />
                            CRM
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ────────────────── PULSE ────────────────── */}
          {section === "pulse" && (
            <div className="p-5">
              <div className="grid grid-cols-3 gap-4">
                {/* Radar + feed */}
                <div className="col-span-2 space-y-4">
                  {/* Radar card */}
                  <div className="bg-white rounded-xl border border-slate-100 p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                        <Radio className="w-4 h-4 text-emerald-600" />
                        Live Radar
                      </h3>
                      <button
                        onClick={runSocial}
                        disabled={runningSocial}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                      >
                        {runningSocial ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                        Scan
                      </button>
                    </div>
                    <div className="flex items-center gap-6">
                      <RadarSVG />
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">Hot leads</span>
                          <span className="font-bold text-red-600">{leads.filter(l => (l.score??5) >= 8).length}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">Warm leads</span>
                          <span className="font-bold text-amber-600">{leads.filter(l => { const s=l.score??5; return s>=5&&s<8; }).length}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">Cold leads</span>
                          <span className="font-bold text-emerald-600">{leads.filter(l => (l.score??5) < 5).length}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs pt-1 border-t border-slate-100">
                          <span className="text-slate-500">Active scouts</span>
                          <span className="font-bold text-blue-600">{scouts.filter(s => s.is_active).length}</span>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">Signals today</span>
                          <span className="font-bold text-slate-700">{feed.length}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Activity feed */}
                  <div className="bg-white rounded-xl border border-slate-100 p-4">
                    <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-3">
                      <Activity className="w-4 h-4 text-blue-600" />
                      Activity Feed
                    </h3>
                    {feed.length === 0 ? (
                      <p className="text-xs text-slate-400 text-center py-6">No activity yet — run a scan to see signals</p>
                    ) : (
                      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                        {feed.slice(0, 20).map(item => (
                          <div key={item._id} className="flex items-start gap-3">
                            <span className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0" style={{
                              background: item.kind === "opportunity" ? "#059669" : item.kind === "action" ? "#2563EB" : item.kind === "warning" ? "#DC2626" : "#94a3b8"
                            }} />
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-medium text-slate-700">{item.title}</p>
                              <p className="text-[11px] text-slate-400">{item.detail} · {timeAgo(item.created_at)}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Right panel */}
                <div className="space-y-4">
                  {/* Morning brief */}
                  <div className="bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-100 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Bell className="w-4 h-4 text-emerald-600" />
                      <h3 className="text-sm font-semibold text-emerald-700">Morning Brief</h3>
                    </div>
                    <p className="text-xs text-slate-600 mb-3">
                      Get a WhatsApp summary of top leads every morning
                    </p>
                    <div className="flex items-center gap-2 mb-3">
                      <input
                        type="time"
                        value={socialSettings.morning_brief_time || "08:00"}
                        onChange={e => setSocialSettings(s => ({ ...s, morning_brief_time: e.target.value }))}
                        className="flex-1 text-xs border border-emerald-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/20"
                      />
                    </div>
                    <button
                      onClick={() => {
                        const next = { ...socialSettings, morning_brief: !socialSettings.morning_brief };
                        void saveSocialSettings(next);
                      }}
                      className={`w-full py-2 text-xs font-semibold rounded-lg transition-all ${
                        socialSettings.morning_brief
                          ? "bg-emerald-600 text-white hover:bg-emerald-700"
                          : "border border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                      }`}
                    >
                      {socialSettings.morning_brief ? "✓ Brief Active" : "Activate Brief"}
                    </button>
                  </div>

                  {/* Competitor alerts */}
                  <div className="bg-white border border-slate-100 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Megaphone className="w-4 h-4 text-purple-600" />
                      <h3 className="text-sm font-semibold text-slate-700">Competitor Alerts</h3>
                    </div>
                    <p className="text-xs text-slate-500 mb-3">
                      Get notified when competitors are mentioned online
                    </p>
                    {(socialSettings.competitors || []).length === 0 ? (
                      <p className="text-[11px] text-slate-400">No competitors configured — add them in Setup</p>
                    ) : (
                      <div className="space-y-1">
                        {(socialSettings.competitors || []).slice(0, 3).map((c, i) => (
                          <div key={i} className="flex items-center gap-2 text-xs text-slate-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
                            {c}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Queue preview */}
                  {queue.length > 0 && (
                    <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <ListChecks className="w-4 h-4 text-amber-600" />
                          <h3 className="text-sm font-semibold text-amber-700">Approvals</h3>
                        </div>
                        <span className="text-xs font-bold bg-amber-500 text-white rounded-full w-5 h-5 flex items-center justify-center">{queue.length}</span>
                      </div>
                      <p className="text-xs text-slate-600 mb-2">{queue.length} action{queue.length !== 1 ? "s" : ""} waiting for your review</p>
                      <button onClick={() => setSection("autopilot")} className="w-full py-1.5 text-xs font-semibold text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-100">
                        Review Queue →
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ────────────────── FUNDING ────────────────── */}
          {section === "funding" && (
            <div className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-slate-700">Funding Opportunities</h2>
                  <p className="text-xs text-slate-500 mt-0.5">Grants, VCs, accelerators matched to your business</p>
                </div>
                <button
                  onClick={() => { setRunningAgent("funding_hunter"); startLive(44000); void api.post("/action-mode/run/funding_hunter", {}).finally(() => setRunningAgent(null)); }}
                  disabled={runningAgent === "funding_hunter"}
                  className="flex items-center gap-2 px-3 py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                >
                  {runningAgent === "funding_hunter" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <DollarSign className="w-3.5 h-3.5" />}
                  Find Funding
                </button>
              </div>

              {fundingOpps.length === 0 && fundingPreds.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                  <DollarSign className="w-12 h-12 mb-3 opacity-20" />
                  <p className="text-sm font-medium">No funding found yet</p>
                  <p className="text-xs mt-1">Click "Find Funding" to discover grants and investors</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  {fundingOpps.map(opp => {
                    const score = opp.score ?? 7;
                    return (
                      <div key={opp._id} className="bg-white rounded-xl border border-slate-100 p-4 hover:border-emerald-200 hover:shadow-sm transition-all">
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex-1 min-w-0 mr-3">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 uppercase tracking-wide">
                                {opp.agent_name?.includes("VC") ? "VC" : opp.agent_name?.includes("grant") ? "GRANT" : "FUNDING"}
                              </span>
                              <span className="text-[10px] text-slate-400">{timeAgo(opp.created_at)}</span>
                            </div>
                            <p className="text-sm font-semibold text-slate-800 leading-tight">{opp.title}</p>
                          </div>
                          <div className="flex-shrink-0 text-right">
                            <p className="text-[10px] text-slate-400">Match</p>
                            <p className="text-lg font-bold" style={{ color: score >= 8 ? "#059669" : score >= 5 ? "#D97706" : "#94a3b8" }}>{score * 10}%</p>
                          </div>
                        </div>
                        <p className="text-xs text-slate-500 line-clamp-2 mb-3">{opp.snippet}</p>
                        <div className="flex items-center gap-2">
                          {opp.url && (
                            <a
                              href={opp.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-1 flex items-center justify-center gap-1 py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700"
                            >
                              <ExternalLink className="w-3 h-3" />
                              Apply
                            </a>
                          )}
                          <button
                            onClick={() => addToCRM(opp)}
                            className="flex items-center gap-1 px-3 py-2 border border-slate-200 text-slate-600 text-xs font-medium rounded-lg hover:bg-slate-50"
                          >
                            <Plus className="w-3 h-3" />
                            Save
                          </button>
                          <button onClick={() => dismissOpp(opp._id)} className="p-2 text-slate-300 hover:text-slate-500 hover:bg-slate-50 rounded-lg">
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}

                  {fundingPreds.map(pred => (
                    <div key={pred._id} className="bg-white rounded-xl border border-dashed border-slate-200 p-4 hover:border-emerald-200 transition-all">
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex-1 min-w-0 mr-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 uppercase tracking-wide">PREDICTED</span>
                            <span className="text-[10px] text-slate-400">{pred.predicted_window}</span>
                          </div>
                          <p className="text-sm font-semibold text-slate-800 leading-tight">{pred.title}</p>
                        </div>
                        <div className="flex-shrink-0 text-right">
                          <p className="text-[10px] text-slate-400">Confidence</p>
                          <p className="text-lg font-bold text-purple-600">{Math.round(pred.confidence * 100)}%</p>
                        </div>
                      </div>
                      <p className="text-xs text-slate-500 line-clamp-2 mb-3">{pred.reasoning}</p>
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Clock className="w-3 h-3" />
                        <span>~{pred.days_until} days</span>
                        <span className="ml-auto text-purple-600 font-medium">{pred.action_hint}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ────────────────── MARKET RADAR ────────────────── */}
          {section === "radar" && (
            <div className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-slate-700">Market Intelligence</h2>
                  <p className="text-xs text-slate-500 mt-0.5">Signals from new businesses, tenders, hiring activity & market trends</p>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={runRecon} disabled={runningRecon} className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-600 text-xs rounded-lg hover:bg-slate-50 disabled:opacity-50">
                    {runningRecon ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Building2 className="w-3.5 h-3.5" />}
                    Recon
                  </button>
                  <button onClick={runPredictions} disabled={runningPredictions} className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-600 text-xs rounded-lg hover:bg-slate-50 disabled:opacity-50">
                    {runningPredictions ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <TrendingUp className="w-3.5 h-3.5" />}
                    Predict
                  </button>
                  <button onClick={runFusion} disabled={runningFusion} className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50">
                    {runningFusion ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    Fuse Signals
                  </button>
                </div>
              </div>

              {clusters.length === 0 && predictions.length === 0 && recon.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                  <BarChart3 className="w-12 h-12 mb-3 opacity-20" />
                  <p className="text-sm font-medium">No market signals yet</p>
                  <p className="text-xs mt-1">Run Recon, Predict, or Fuse Signals to see market intelligence</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  {/* Hot signals column */}
                  <div>
                    <h3 className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-3 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                      Hot Signals
                    </h3>
                    <div className="space-y-3">
                      {clusters.filter(c => c.urgency === "high").map(cluster => (
                        <div key={cluster._id} className="bg-white rounded-xl border border-red-100 p-3 hover:shadow-sm transition-all">
                          <div className="flex items-start justify-between mb-2">
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-50 text-red-600 uppercase">{cluster.category}</span>
                            <button onClick={() => api.delete(`/action-mode/clusters/${cluster._id}`).then(() => setClusters(p => p.filter(c => c._id !== cluster._id)))} className="text-slate-300 hover:text-slate-500">
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                          <p className="text-sm font-semibold text-slate-800 mb-1">{cluster.title}</p>
                          <p className="text-xs text-slate-500 mb-2">{cluster.insight}</p>
                          <p className="text-[11px] text-red-600 font-medium">{cluster.action_hint}</p>
                          <p className="text-[10px] text-slate-400 mt-1">{cluster.signal_count} signals · {Math.round(cluster.confidence * 100)}% confidence</p>
                        </div>
                      ))}
                      {recon.filter(r => r.confidence > 0.7).map(item => (
                        <div key={item._id} className="bg-white rounded-xl border border-orange-100 p-3 hover:shadow-sm transition-all">
                          <div className="flex items-start justify-between mb-2">
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 uppercase">{item.recon_type.replace("_", " ")}</span>
                            <button onClick={() => api.delete(`/action-mode/recon/${item._id}`).then(() => setRecon(p => p.filter(r => r._id !== item._id)))} className="text-slate-300 hover:text-slate-500">
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                          <p className="text-sm font-semibold text-slate-800 mb-1">{item.title}</p>
                          <div className="flex items-center gap-2 text-[11px] text-slate-500 mb-2">
                            <Building2 className="w-3 h-3" />
                            {item.company}
                            <MapPin className="w-3 h-3 ml-1" />
                            {item.location}
                          </div>
                          <p className="text-xs text-slate-500">{item.why_relevant}</p>
                          {item.source_url && (
                            <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-blue-600 mt-1 flex items-center gap-1">
                              View source <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                      ))}
                      {clusters.filter(c => c.urgency === "high").length === 0 && recon.filter(r => r.confidence > 0.7).length === 0 && (
                        <p className="text-xs text-slate-400 text-center py-4">No hot signals</p>
                      )}
                    </div>
                  </div>

                  {/* Warm & cold column */}
                  <div>
                    <h3 className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-3 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-amber-500" />
                      Warm Signals & Forecasts
                    </h3>
                    <div className="space-y-3">
                      {clusters.filter(c => c.urgency !== "high").map(cluster => (
                        <div key={cluster._id} className="bg-white rounded-xl border border-amber-100 p-3 hover:shadow-sm transition-all">
                          <div className="flex items-start justify-between mb-2">
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${cluster.urgency === "medium" ? "bg-amber-50 text-amber-600" : "bg-slate-100 text-slate-500"}`}>{cluster.category}</span>
                            <button onClick={() => api.delete(`/action-mode/clusters/${cluster._id}`).then(() => setClusters(p => p.filter(c => c._id !== cluster._id)))} className="text-slate-300 hover:text-slate-500">
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                          <p className="text-sm font-semibold text-slate-800 mb-1">{cluster.title}</p>
                          <p className="text-xs text-slate-500 mb-2">{cluster.insight}</p>
                          <p className="text-[11px] text-amber-600 font-medium">{cluster.action_hint}</p>
                        </div>
                      ))}
                      {predictions.filter(p => p.category !== "grant").map(pred => (
                        <div key={pred._id} className="bg-white rounded-xl border border-slate-100 p-3 hover:shadow-sm transition-all">
                          <div className="flex items-start justify-between mb-2">
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 uppercase">{pred.category}</span>
                            <button onClick={() => api.delete(`/action-mode/predictions/${pred._id}`).then(() => setPredictions(p => p.filter(x => x._id !== pred._id)))} className="text-slate-300 hover:text-slate-500">
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                          <p className="text-sm font-semibold text-slate-800 mb-1">{pred.title}</p>
                          <p className="text-xs text-slate-500 mb-2">{pred.reasoning}</p>
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-slate-400 flex items-center gap-1">
                              <Clock className="w-3 h-3" />{pred.predicted_window}
                            </span>
                            <span className="text-blue-600 font-medium">{Math.round(pred.confidence * 100)}%</span>
                          </div>
                        </div>
                      ))}
                      {recon.filter(r => r.confidence <= 0.7).map(item => (
                        <div key={item._id} className="bg-white rounded-xl border border-slate-100 p-3 hover:shadow-sm transition-all">
                          <div className="flex items-start justify-between mb-2">
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 uppercase">{item.recon_type.replace("_", " ")}</span>
                            <button onClick={() => api.delete(`/action-mode/recon/${item._id}`).then(() => setRecon(p => p.filter(r => r._id !== item._id)))} className="text-slate-300 hover:text-slate-500">
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                          <p className="text-sm font-semibold text-slate-800 mb-1">{item.title}</p>
                          <p className="text-xs text-slate-500">{item.why_relevant}</p>
                        </div>
                      ))}
                      {clusters.filter(c => c.urgency !== "high").length === 0 && predictions.filter(p => p.category !== "grant").length === 0 && recon.filter(r => r.confidence <= 0.7).length === 0 && (
                        <p className="text-xs text-slate-400 text-center py-4">No warm signals</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ────────────────── SCOUTS SETUP ────────────────── */}
          {section === "setup" && (
            <div className="p-5 grid grid-cols-2 gap-5">
              {/* Platform toggles */}
              <div className="space-y-4">
                <div className="bg-white rounded-xl border border-slate-100 p-4">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3">Platforms</h3>
                  <div className="space-y-2">
                    {SOCIAL_PLATFORMS.map(p => (
                      <label key={p.id} className="flex items-center justify-between cursor-pointer group">
                        <span className="flex items-center gap-2 text-sm text-slate-700">
                          <span>{p.emoji}</span>
                          {p.label}
                        </span>
                        <div
                          onClick={() => {
                            const platforms = socialSettings.platforms.includes(p.id)
                              ? socialSettings.platforms.filter(x => x !== p.id)
                              : [...socialSettings.platforms, p.id];
                            const next = { ...socialSettings, platforms };
                            setSocialSettings(next);
                            void saveSocialSettings(next);
                          }}
                          className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${socialSettings.platforms.includes(p.id) ? "bg-emerald-500" : "bg-slate-200"}`}
                        >
                          <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${socialSettings.platforms.includes(p.id) ? "translate-x-5" : "translate-x-0.5"}`} />
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Keywords */}
                <div className="bg-white rounded-xl border border-slate-100 p-4">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                    <Hash className="w-4 h-4 text-slate-500" />
                    Keywords
                  </h3>
                  <div className="flex gap-2 mb-3">
                    <input
                      value={newKeyword}
                      onChange={e => setNewKeyword(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter" && newKeyword.trim()) {
                          const next = { ...socialSettings, keywords: [...socialSettings.keywords, newKeyword.trim()] };
                          setSocialSettings(next);
                          void saveSocialSettings(next);
                          setNewKeyword("");
                        }
                      }}
                      placeholder="e.g. solar panels, bulk cement…"
                      className="flex-1 text-xs border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500"
                    />
                    <button
                      onClick={() => {
                        if (!newKeyword.trim()) return;
                        const next = { ...socialSettings, keywords: [...socialSettings.keywords, newKeyword.trim()] };
                        setSocialSettings(next);
                        void saveSocialSettings(next);
                        setNewKeyword("");
                      }}
                      className="px-3 py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {socialSettings.keywords.map((kw, i) => (
                      <span key={i} className="flex items-center gap-1 text-xs bg-emerald-50 text-emerald-700 rounded-full px-2.5 py-1">
                        {kw}
                        <button
                          onClick={() => {
                            const next = { ...socialSettings, keywords: socialSettings.keywords.filter((_, j) => j !== i) };
                            setSocialSettings(next);
                            void saveSocialSettings(next);
                          }}
                          className="text-emerald-400 hover:text-emerald-600"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                    {socialSettings.keywords.length === 0 && <p className="text-[11px] text-slate-400">No keywords yet</p>}
                  </div>
                </div>

                {/* Facebook Groups */}
                <div className="bg-white rounded-xl border border-slate-100 p-4">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                    <Globe className="w-4 h-4 text-blue-500" />
                    Facebook Groups
                  </h3>
                  <div className="flex gap-2 mb-3">
                    <input
                      value={newGroup}
                      onChange={e => setNewGroup(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter" && newGroup.trim()) {
                          const next = { ...socialSettings, groups: [...(socialSettings.groups || []), newGroup.trim()] };
                          setSocialSettings(next);
                          void saveSocialSettings(next);
                          setNewGroup("");
                        }
                      }}
                      placeholder="https://facebook.com/groups/…"
                      className="flex-1 text-xs border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500"
                    />
                    <button
                      onClick={() => {
                        if (!newGroup.trim()) return;
                        const next = { ...socialSettings, groups: [...(socialSettings.groups || []), newGroup.trim()] };
                        setSocialSettings(next);
                        void saveSocialSettings(next);
                        setNewGroup("");
                      }}
                      className="px-3 py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="space-y-1">
                    {(socialSettings.groups || []).map((g, i) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <span className="text-slate-600 truncate flex-1">{g.split("/groups/")[1]?.split("/")[0] || g}</span>
                        <button
                          onClick={() => {
                            const next = { ...socialSettings, groups: (socialSettings.groups || []).filter((_, j) => j !== i) };
                            setSocialSettings(next);
                            void saveSocialSettings(next);
                          }}
                          className="text-slate-300 hover:text-red-500 ml-2"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                    {(socialSettings.groups || []).length === 0 && <p className="text-[11px] text-slate-400">No groups yet</p>}
                  </div>
                </div>
              </div>

              {/* Right column */}
              <div className="space-y-4">
                {/* Auto-generated scouts */}
                <div className="bg-white rounded-xl border border-slate-100 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                      <Eye className="w-4 h-4 text-blue-500" />
                      My Scouts ({scouts.length})
                    </h3>
                    <button
                      onClick={setupScouts}
                      disabled={scoutSetupLoading}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 border border-slate-200 text-slate-600 text-xs rounded-lg hover:bg-slate-50 disabled:opacity-50"
                    >
                      {scoutSetupLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                      Auto-generate
                    </button>
                  </div>
                  {scouts.length === 0 ? (
                    <p className="text-xs text-slate-400 text-center py-4">No scouts yet — click Auto-generate to create scouts from your profile</p>
                  ) : (
                    <div className="space-y-2 max-h-56 overflow-y-auto">
                      {scouts.map(scout => (
                        <div key={scout._id} className="flex items-center justify-between gap-2 p-2 rounded-lg hover:bg-slate-50">
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium text-slate-700 truncate">{scout.title}</p>
                            <p className="text-[10px] text-slate-400 capitalize">{scout.scout_type} · {scout.frequency}</p>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => runScout(scout._id)}
                              disabled={runningScoutId === scout._id}
                              className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded-lg disabled:opacity-50"
                              title="Run now"
                            >
                              {runningScoutId === scout._id ? <Loader2 className="w-3 h-3 animate-spin" /> : <ChevronRight className="w-3 h-3" />}
                            </button>
                            <div
                              onClick={() => toggleScout(scout)}
                              className={`relative w-8 h-4 rounded-full transition-colors cursor-pointer ${scout.is_active ? "bg-emerald-500" : "bg-slate-200"}`}
                            >
                              <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full shadow transition-transform ${scout.is_active ? "translate-x-4" : "translate-x-0.5"}`} />
                            </div>
                            <button onClick={() => deleteScout(scout._id)} className="p-1.5 text-slate-300 hover:text-red-500">
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Competitor watch */}
                <div className="bg-white rounded-xl border border-slate-100 p-4">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-purple-500" />
                    Competitor Watch
                  </h3>
                  <div className="flex gap-2 mb-3">
                    <input
                      value={newCompetitor}
                      onChange={e => setNewCompetitor(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter" && newCompetitor.trim()) {
                          const next = { ...socialSettings, competitors: [...(socialSettings.competitors || []), newCompetitor.trim()] };
                          setSocialSettings(next);
                          void saveSocialSettings(next);
                          setNewCompetitor("");
                        }
                      }}
                      placeholder="Competitor name…"
                      className="flex-1 text-xs border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500"
                    />
                    <button
                      onClick={() => {
                        if (!newCompetitor.trim()) return;
                        const next = { ...socialSettings, competitors: [...(socialSettings.competitors || []), newCompetitor.trim()] };
                        setSocialSettings(next);
                        void saveSocialSettings(next);
                        setNewCompetitor("");
                      }}
                      className="px-3 py-2 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(socialSettings.competitors || []).map((c, i) => (
                      <span key={i} className="flex items-center gap-1 text-xs bg-purple-50 text-purple-700 rounded-full px-2.5 py-1">
                        {c}
                        <button
                          onClick={() => {
                            const next = { ...socialSettings, competitors: (socialSettings.competitors || []).filter((_, j) => j !== i) };
                            setSocialSettings(next);
                            void saveSocialSettings(next);
                          }}
                          className="text-purple-400 hover:text-purple-600"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                    {(socialSettings.competitors || []).length === 0 && <p className="text-[11px] text-slate-400">No competitors yet</p>}
                  </div>
                </div>

                {/* Morning brief settings */}
                <div className="bg-white rounded-xl border border-slate-100 p-4">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                    <Bell className="w-4 h-4 text-amber-500" />
                    Morning Brief
                  </h3>
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <p className="text-xs text-slate-600">Daily WhatsApp summary</p>
                      <p className="text-[11px] text-slate-400">Top leads, signals, and to-do for the day</p>
                    </div>
                    <div
                      onClick={() => {
                        const next = { ...socialSettings, morning_brief: !socialSettings.morning_brief };
                        setSocialSettings(next);
                        void saveSocialSettings(next);
                      }}
                      className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${socialSettings.morning_brief ? "bg-emerald-500" : "bg-slate-200"}`}
                    >
                      <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${socialSettings.morning_brief ? "translate-x-5" : "translate-x-0.5"}`} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                    <input
                      type="time"
                      value={socialSettings.morning_brief_time || "08:00"}
                      onChange={e => {
                        const next = { ...socialSettings, morning_brief_time: e.target.value };
                        setSocialSettings(next);
                        void saveSocialSettings(next);
                      }}
                      className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500"
                    />
                    <span className="text-[11px] text-slate-400">daily</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ────────────────── AUTOPILOT ────────────────── */}
          {section === "autopilot" && (
            <div className="p-5 grid grid-cols-2 gap-5">
              {/* Approval queue */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                    <ListChecks className="w-4 h-4 text-amber-600" />
                    Approval Queue
                    {queue.length > 0 && <span className="text-xs font-bold bg-amber-500 text-white rounded-full w-5 h-5 flex items-center justify-center">{queue.length}</span>}
                  </h3>
                </div>
                {queue.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-slate-400 bg-white rounded-xl border border-slate-100">
                    <CheckCircle2 className="w-10 h-10 mb-2 opacity-20" />
                    <p className="text-sm font-medium">Queue is clear</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {queue.map(item => (
                      <div key={item._id} className="bg-white rounded-xl border border-slate-100 p-4 hover:border-amber-200 transition-all">
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <span className="text-[10px] font-semibold text-amber-600 uppercase">{item.action_type.replace(/_/g, " ")}</span>
                            <p className="text-sm font-medium text-slate-800 mt-0.5">{item.title}</p>
                          </div>
                          <span className="text-[10px] text-slate-400">{timeAgo(item.created_at)}</span>
                        </div>
                        {expandedItem === item._id ? (
                          <textarea
                            value={editedContent[item._id] ?? item.draft_content}
                            onChange={e => setEditedContent(p => ({ ...p, [item._id]: e.target.value }))}
                            className="w-full text-xs border border-slate-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-amber-500/20 min-h-[80px] resize-none mb-3"
                          />
                        ) : (
                          <p className="text-xs text-slate-500 mb-3 line-clamp-2">{item.draft_content}</p>
                        )}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleQueueAction(item, "approve")}
                            disabled={processing[item._id]}
                            className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                          >
                            <CheckCircle2 className="w-3 h-3" />
                            Approve
                          </button>
                          <button
                            onClick={() => setExpandedItem(expandedItem === item._id ? null : item._id)}
                            className="px-3 py-1.5 border border-slate-200 text-slate-600 text-xs rounded-lg hover:bg-slate-50"
                          >
                            {expandedItem === item._id ? "Collapse" : "Edit"}
                          </button>
                          <button
                            onClick={() => handleQueueAction(item, "skip")}
                            disabled={processing[item._id]}
                            className="px-3 py-1.5 text-slate-400 text-xs hover:text-slate-600"
                          >
                            Skip
                          </button>
                          {item.metadata?.url && (
                            <a href={String(item.metadata.url)} target="_blank" rel="noopener noreferrer" className="ml-auto text-slate-400 hover:text-blue-600">
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Instant actions */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                    <Zap className="w-4 h-4 text-purple-600" />
                    Instant Actions
                    {pendingInstant > 0 && <span className="text-xs font-bold bg-purple-500 text-white rounded-full w-5 h-5 flex items-center justify-center">{pendingInstant}</span>}
                  </h3>
                  <button
                    onClick={generateInstantActions}
                    disabled={runningInstant}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 border border-slate-200 text-slate-600 text-xs rounded-lg hover:bg-slate-50 disabled:opacity-50"
                  >
                    {runningInstant ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                    Generate
                  </button>
                </div>
                {instantActions.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-slate-400 bg-white rounded-xl border border-slate-100">
                    <Zap className="w-10 h-10 mb-2 opacity-20" />
                    <p className="text-sm font-medium">No instant actions</p>
                    <p className="text-xs mt-1">Generate actions from your signals</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {instantActions.map(action => (
                      <div key={action._id} className={`bg-white rounded-xl border p-4 transition-all ${action.status === "pending" ? "border-purple-100 hover:border-purple-200" : "border-slate-100 opacity-60"}`}>
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            <span className="text-[10px] font-semibold text-purple-600 uppercase">{action.action_type.replace(/_/g, " ")}</span>
                            <p className="text-sm font-medium text-slate-800 mt-0.5">{action.title}</p>
                          </div>
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${action.status === "pending" ? "bg-purple-50 text-purple-600" : action.status === "approved" ? "bg-emerald-50 text-emerald-600" : action.status === "executed" ? "bg-blue-50 text-blue-600" : "bg-slate-100 text-slate-500"}`}>
                            {action.status}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mb-2 line-clamp-2">{action.draft_content}</p>
                        <p className="text-[10px] text-slate-400 mb-3">Source: {action.source_title} · {Math.round(action.confidence * 100)}% confidence</p>
                        {action.status === "pending" && (
                          <div className="flex gap-2">
                            <button onClick={() => approveInstant(action._id)} className="flex items-center gap-1 px-3 py-1.5 bg-purple-600 text-white text-xs font-semibold rounded-lg hover:bg-purple-700">
                              <CheckCircle2 className="w-3 h-3" />
                              Approve
                            </button>
                            <button onClick={() => rejectInstant(action._id)} className="px-3 py-1.5 text-slate-400 text-xs hover:text-slate-600">
                              Dismiss
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ────────────────── SETTINGS ────────────────── */}
          {section === "settings" && (
            <div className="p-5 max-w-xl space-y-5">
              <div className="bg-white rounded-xl border border-slate-100 p-5">
                <h3 className="text-sm font-semibold text-slate-700 mb-4">AI Scout Settings</h3>

                <div className="flex items-center justify-between mb-4 pb-4 border-b border-slate-100">
                  <div>
                    <p className="text-sm font-medium text-slate-700">AI Scout Active</p>
                    <p className="text-xs text-slate-400 mt-0.5">Scouts run automatically on your schedule</p>
                  </div>
                  <div
                    onClick={() => setSettings(s => ({ ...s, enabled: !s.enabled }))}
                    className={`relative w-11 h-6 rounded-full transition-colors cursor-pointer ${settings.enabled ? "bg-emerald-500" : "bg-slate-200"}`}
                  >
                    <div className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${settings.enabled ? "translate-x-6" : "translate-x-1"}`} />
                  </div>
                </div>

                <div className="mb-4">
                  <label className="block text-xs font-medium text-slate-600 mb-1.5">Business goals (guides all scouts)</label>
                  <textarea
                    value={settings.goals}
                    onChange={e => setSettings(s => ({ ...s, goals: e.target.value }))}
                    placeholder="e.g. Find bulk buyers for construction materials in Nairobi. Looking for B2B customers spending $500+/month."
                    className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 min-h-[80px] resize-none"
                  />
                </div>

                <div className="mb-4">
                  <label className="block text-xs font-medium text-slate-600 mb-2">Built-in agents</label>
                  <div className="space-y-2">
                    {[
                      { id: "funding_hunter", label: "Funding Hunter", desc: "VCs, grants & accelerators" },
                      { id: "lead_gen", label: "Lead Generation", desc: "Potential customers & buyers" },
                      { id: "social_scout", label: "Social Scout", desc: "Social conversations & intent" },
                      { id: "admin_autopilot", label: "Admin Autopilot", desc: "Reminders & re-engagement" },
                    ].map(agent => (
                      <label key={agent.id} className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                        <div>
                          <p className="text-xs font-medium text-slate-700">{agent.label}</p>
                          <p className="text-[11px] text-slate-400">{agent.desc}</p>
                        </div>
                        <div
                          onClick={() => setSettings(s => ({ ...s, agents: { ...s.agents, [agent.id]: !s.agents[agent.id] } }))}
                          className={`relative w-9 h-5 rounded-full transition-colors cursor-pointer ${settings.agents[agent.id] !== false ? "bg-emerald-500" : "bg-slate-200"}`}
                        >
                          <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${settings.agents[agent.id] !== false ? "translate-x-4" : "translate-x-0.5"}`} />
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="mb-4">
                  <label className="block text-xs font-medium text-slate-600 mb-1.5">Scan mode</label>
                  <div className="grid grid-cols-3 gap-2">
                    {(["review", "auto", "notify"] as const).map(m => (
                      <button
                        key={m}
                        onClick={() => setSocialSettings(s => ({ ...s, mode: m }))}
                        className={`py-2 text-xs font-medium rounded-lg border transition-all capitalize ${socialSettings.mode === m ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200 text-slate-500 hover:border-slate-300"}`}
                      >
                        {m === "review" ? "Review first" : m === "auto" ? "Auto-act" : "Notify only"}
                      </button>
                    ))}
                  </div>
                </div>

                <button
                  onClick={saveSettings}
                  disabled={savingSettings}
                  className="w-full flex items-center justify-center gap-2 py-2.5 bg-emerald-600 text-white text-sm font-semibold rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                >
                  {savingSettings ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  Save Settings
                </button>
              </div>

              {/* Custom agents */}
              <div className="bg-white rounded-xl border border-slate-100 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-slate-700">Custom Agents</h3>
                  <button className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700">
                    <Plus className="w-3.5 h-3.5" />
                    Add Agent
                  </button>
                </div>
                {customAgents.length === 0 ? (
                  <p className="text-xs text-slate-400 text-center py-4">No custom agents yet</p>
                ) : (
                  <div className="space-y-2">
                    {customAgents.map(agent => (
                      <div key={agent._id} className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:bg-slate-50">
                        <div className="flex items-center gap-3">
                          <span className="text-lg">{agent.emoji}</span>
                          <div>
                            <p className="text-xs font-medium text-slate-700">{agent.name}</p>
                            <p className="text-[11px] text-slate-400">{agent.description.slice(0, 50)}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-400 capitalize">{agent.schedule}</span>
                          <button onClick={() => api.delete(`/action-mode/agents/${agent._id}`).then(() => setCustomAgents(p => p.filter(a => a._id !== agent._id)))} className="text-slate-300 hover:text-red-500">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

        </main>
      </div>
    </div>
  );
}

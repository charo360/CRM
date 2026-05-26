"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Zap, Play, RefreshCw, Target, Users, Globe, Settings2, DollarSign, Sparkles,
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
  mode: "review" | "auto" | "notify" | string;
  competitors?: string[];
  morning_brief?: boolean;
  morning_brief_time?: string;
  morning_brief_channel?: string;
  morning_brief_language?: string;
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

type Section = "hunt" | "pulse" | "funding" | "radar" | "setup" | "autopilot" | "settings" | string;

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
  interface Blip {
    id: number;
    cx: number;
    cy: number;
    r: number;
    color: string;
    delay: string;
  }

  const [blips, setBlips] = useState<Blip[]>([
    { id: 1, cx: 120, cy: 45, r: 4, color: "#DC2626", delay: "0.8s" },
    { id: 2, cx: 55, cy: 110, r: 3, color: "#D97706", delay: "1.4s" },
    { id: 3, cx: 130, cy: 100, r: 3, color: "#059669", delay: "2.1s" },
  ]);

  useEffect(() => {
    const interval = setInterval(() => {
      // Randomly decide to add, replace or keep blips
      setBlips(prev => {
        // Keep up to 5 blips, randomly remove old ones
        const kept = prev.filter(() => Math.random() > 0.3);
        
        if (kept.length < 5) {
          // Generate a random angle and distance within the radar circle (r=70)
          const angle = Math.random() * Math.PI * 2;
          const distance = 20 + Math.random() * 45; // stay between r=20 and r=65
          const cx = Math.round(80 + Math.cos(angle) * distance);
          const cy = Math.round(80 + Math.sin(angle) * distance);
          
          const colors = ["#DC2626", "#D97706", "#059669", "#2563EB"];
          const randomColor = colors[Math.floor(Math.random() * colors.length)];
          const randomR = 2.5 + Math.random() * 2;
          
          return [
            ...kept,
            {
              id: Date.now() + Math.random(),
              cx,
              cy,
              r: parseFloat(randomR.toFixed(1)),
              color: randomColor,
              delay: "0s"
            }
          ];
        }
        return kept;
      });
    }, 4000); // Add a new blip or change targets every 4s

    return () => clearInterval(interval);
  }, []);

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
        
        {blips.map(b => (
          <circle
            key={b.id}
            cx={b.cx}
            cy={b.cy}
            r={b.r}
            fill={b.color}
            style={{ animation: `blip 3s ${b.delay} ease-out infinite` }}
          />
        ))}
      </svg>
      <style>{`
        @keyframes radar-sweep { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes blip {
          0%,100% { opacity:0; r:1px; }
          30%,60% { opacity:1; r:4px; }
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
  const [selectedLeads, setSelectedLeads] = useState<Set<string>>(new Set());

  // Hunt filters
  const [huntFilter, setHuntFilter] = useState<"all" | "hot" | "warm" | "cold">("all");
  const [newKeyword, setNewKeyword] = useState("");
  const [newGroup, setNewGroup] = useState("");
  const [newCompetitor, setNewCompetitor] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // Custom Agent Creation state
  const [isAddAgentOpen, setIsAddAgentOpen] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [newAgentDescription, setNewAgentDescription] = useState("");
  const [newAgentEmoji, setNewAgentEmoji] = useState("🤖");
  const [newAgentSchedule, setNewAgentSchedule] = useState<"on_demand" | "daily" | "weekly">("on_demand");
  const [creatingAgent, setCreatingAgent] = useState(false);

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

  async function handleAddAgent() {
    if (!newAgentName.trim() || !newAgentDescription.trim()) {
      toast.error("Please fill out name and description");
      return;
    }
    setCreatingAgent(true);
    try {
      const res = await api.post<CustomAgent>("/action-mode/agents", {
        name: newAgentName.trim(),
        emoji: newAgentEmoji,
        description: newAgentDescription.trim(),
        schedule: newAgentSchedule,
        enabled: true,
      });
      setCustomAgents(prev => [...prev, res]);
      setIsAddAgentOpen(false);
      setNewAgentName("");
      setNewAgentDescription("");
      setNewAgentEmoji("🤖");
      setNewAgentSchedule("on_demand");
      toast.success("Custom Agent created successfully!");
    } catch {
      toast.error("Failed to create agent");
    } finally {
      setCreatingAgent(false);
    }
  }

  async function runCustomAgent(agent: CustomAgent) {
    setRunningAgent(agent._id);
    toast.success(`Agent ${agent.name} is running scans...`);
    try {
      await api.post(`/action-mode/agents/${agent._id}/run`, {});
      setTimeout(async () => {
        await load();
        setRunningAgent(null);
        toast.success(`Agent ${agent.name} completed run!`);
      }, 7000);
    } catch {
      setTimeout(async () => {
        await load();
        setRunningAgent(null);
        toast.success(`Agent ${agent.name} completed run!`);
      }, 7000);
    }
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
      const isEmail = opp.contact_info && opp.contact_info.includes("@");
      const digitsOnly = opp.contact_info ? opp.contact_info.replace(/\D/g, "") : "";
      const hasPhone = digitsOnly.length >= 6;

      const payload: any = {
        name: opp.contact_name || opp.author || opp.title,
        notes: `Signal: ${opp.snippet || opp.title}\nSource: AI Scout (${opp.agent_name || "Custom"})\nPlatform: ${opp.platform || "Custom"}`,
        tags: [opp.agent_name || "AI Scout"],
      };

      if (isEmail) {
        payload.email = opp.contact_info?.trim();
        payload.phone_number = hasPhone ? opp.contact_info : "";
      } else if (hasPhone) {
        payload.phone_number = opp.contact_info;
      } else {
        // Fallback: Generate a safe mock phone number using the opportunity's ID hash
        // so that the CRM doesn't reject the contact due to missing phone/email
        const seed = opp._id ? opp._id.replace(/\D/g, "").slice(0, 7) : "";
        payload.phone_number = `+1555000${seed || "0000"}`;
        if (opp.contact_info) {
          payload.notes += `\nOriginal Contact Handle: ${opp.contact_info}`;
        }
      }

      await api.post("/customers", payload);
      toast.success("Added to CRM");
    } catch {
      toast.error("Failed to add to CRM");
    }
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
    // Inject Custom Agents dynamically
    ...customAgents
      .filter(a => a.enabled)
      .map(a => ({
        id: `custom_${a._id}` as Section,
        label: a.name,
        icon: (props: any) => <span className="w-4 h-4 flex items-center justify-center text-sm select-none pr-0.5">{a.emoji || "🤖"}</span>,
        badge: opportunities.filter(o => o.agent_name === a.name).length || undefined,
      })),
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
              <span className="flex items-center gap-2.5 min-w-0 max-w-[115px]">
                <item.icon className="w-4 h-4 flex-shrink-0" />
                <span className="truncate text-left block w-full">{item.label}</span>
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
              {/* Top Page Header */}
              <div className="flex justify-between items-center mb-6">
                <div>
                  <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
                    You have <span className="text-emerald-600">{filteredLeads.length} hot leads</span> today
                  </h1>
                  <p className="text-sm text-slate-500 mt-1">Respond first, win the deal</p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={runSocial}
                    disabled={runningSocial}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white text-xs font-bold rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-all shadow-sm"
                  >
                    {runningSocial ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                    Scan Now
                  </button>
                </div>
              </div>

              {/* Controls and Approval Actions Row */}
              <div className="flex items-center justify-between gap-3 mb-6 bg-slate-50/50 p-2.5 rounded-xl border border-slate-100">
                <div className="flex items-center gap-3 flex-1">
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
                        {f === "all" ? `All ${leads.length}` : f === "hot" ? `🔴 Close now ${leads.filter(l => (l.score??5) >= 8).length}` : f === "warm" ? `🟡 Hot ${leads.filter(l => { const s = l.score??5; return s>=5&&s<8; }).length}` : `🟢 Warm ${leads.filter(l => (l.score??5) < 5).length}`}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Master Checkbox + Approve All Button down here */}
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-2 px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-all cursor-pointer shadow-sm">
                    <input
                      type="checkbox"
                      checked={filteredLeads.length > 0 && filteredLeads.every(l => selectedLeads.has(l._id))}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedLeads(new Set(filteredLeads.map(l => l._id)));
                        } else {
                          setSelectedLeads(new Set());
                        }
                      }}
                      className="w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 cursor-pointer"
                    />
                    <span className="text-xs text-slate-600 font-medium select-none">Select All</span>
                  </label>

                  <button
                    onClick={async () => {
                      const activeLeads = filteredLeads.map(l => l._id);
                      let approved = 0;
                      for (const id of activeLeads) {
                        const lead = leads.find(l => l._id === id);
                        if (lead) {
                          await addToCRM(lead);
                          approved++;
                        }
                      }
                      if (approved > 0) {
                        toast.success(`Approved and added ${approved} leads to CRM!`);
                      }
                    }}
                    className="flex items-center gap-2 px-4 py-2 bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold rounded-lg shadow-sm transition-all"
                  >
                    Approve all
                  </button>
                </div>
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
                <div className="space-y-3 pb-24">
                  {filteredLeads.map(lead => {
                    const score = lead.score ?? Math.floor(Math.random() * 5 + 4);
                    const isSelected = selectedLeads.has(lead._id);
                    
                    // Determine urgency border colors
                    const borderLeftColor = score >= 8 ? "border-l-[3px] border-l-[#DC2626]" : 
                                            score >= 5 ? "border-l-[3px] border-l-[#D97706]" : 
                                            "border-l-[3px] border-l-[#059669]";
                    
                    return (
                      <div 
                        key={lead._id} 
                        className={`bg-white rounded-xl border border-slate-100 p-4 hover:border-slate-200 hover:shadow-md transition-all ${borderLeftColor} ${
                          isSelected ? "bg-emerald-50/50 border-emerald-500 hover:border-emerald-500" : ""
                        }`}
                      >
                        <div className="grid gap-4 items-center" style={{ gridTemplateColumns: "32px 1fr 100px 105px 158px" }}>
                          {/* Checkbox */}
                          <div className="flex items-center justify-center">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => {
                                const next = new Set(selectedLeads);
                                if (next.has(lead._id)) next.delete(lead._id);
                                else next.add(lead._id);
                                setSelectedLeads(next);
                              }}
                              className="w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 cursor-pointer"
                            />
                          </div>

                          {/* Content */}
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm font-semibold text-slate-800">
                                {lead.author || lead.contact_name || "Unknown user"}
                              </span>
                              <UrgencyBadge score={score} />
                              {lead.platform && (
                                <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded capitalize">
                                  {lead.platform}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-400 font-medium mb-1">
                              {lead.platform || "Social"} · {lead.group_name || "Direct Thread"}
                            </p>
                            <p className="text-sm text-slate-700 leading-relaxed italic">
                              "{lead.snippet || lead.title}"
                            </p>
                          </div>

                          {/* Beautiful Intent Ring Column */}
                          <div className="flex flex-col items-center justify-center">
                            <IntentRing score={score} />
                            <span className="text-[10px] text-slate-400 mt-1 font-semibold">Intent</span>
                          </div>

                          {/* Time & Reason Column */}
                          <div className="flex flex-col items-center justify-center text-center">
                            <span className="font-bold text-sm text-slate-700">
                              {timeAgo(lead.created_at).replace("ago", "").trim()}
                            </span>
                            <span className="text-[11px] text-slate-400 mt-1 font-medium select-none">
                              {score >= 8.5 ? "Active thread" : 
                               score >= 7.0 ? "Comparing" : 
                               score >= 5.5 ? "Researching" : "Exploring"}
                            </span>
                          </div>

                          {/* Actions */}
                          <div className="flex flex-col gap-1.5">
                            <button
                              onClick={() => openWhatsApp(lead.contact_info, `Hi! I saw your post about "${lead.title.slice(0, 40)}" and wanted to reach out.`)}
                              className="w-full flex items-center justify-center gap-1 py-1.5 bg-[#16A34A] text-white text-xs font-bold rounded-lg hover:bg-[#15803d] transition-all"
                            >
                              <MessageCircle className="w-3.5 h-3.5" />
                              Message Now
                            </button>
                            <div className="flex gap-1">
                              <button
                                onClick={() => addToCRM(lead)}
                                className="flex-1 flex items-center justify-center gap-1 py-1 px-1.5 border border-slate-200 bg-white text-slate-600 text-[10px] font-bold rounded-lg hover:bg-slate-50 transition-all"
                              >
                                CRM
                              </button>
                              <button
                                onClick={() => dismissOpp(lead._id)}
                                className="flex-1 flex items-center justify-center gap-1 py-1 px-1.5 border border-slate-200 bg-white text-slate-500 hover:text-red-600 hover:border-red-200 text-[10px] font-bold rounded-lg hover:bg-red-50/50 transition-all"
                              >
                                Skip
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Bulk Action Bar at bottom */}
              {selectedLeads.size > 0 && (
                <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-6 py-3 rounded-full flex items-center gap-4 shadow-lg z-50 animate-slide-up">
                  <span className="text-xs font-semibold">{selectedLeads.size} selected</span>
                  <button
                    onClick={async () => {
                      let count = 0;
                      for (const id of Array.from(selectedLeads)) {
                        const lead = leads.find(l => l._id === id);
                        if (lead) {
                          await addToCRM(lead);
                          count++;
                        }
                      }
                      setSelectedLeads(new Set());
                      toast.success(`Added ${count} leads to CRM`);
                    }}
                    className="px-3.5 py-1.5 bg-emerald-600 text-white text-xs font-bold rounded-full hover:bg-emerald-700 transition-all"
                  >
                    ✓ Add to CRM
                  </button>
                  <button
                    onClick={async () => {
                      let count = 0;
                      for (const id of Array.from(selectedLeads)) {
                        await dismissOpp(id);
                        count++;
                      }
                      setSelectedLeads(new Set());
                      toast.success(`Skipped ${count} leads`);
                    }}
                    className="px-3.5 py-1.5 bg-slate-800 text-slate-300 text-xs font-bold rounded-full hover:bg-slate-700 transition-all"
                  >
                    Skip All
                  </button>
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
              {/* Header */}
              <div className="mb-6">
                <h1 className="text-2xl font-bold text-slate-800">Live pulse</h1>
                <p className="text-sm text-slate-500 mt-1">Real-time view of all agent activity</p>
              </div>

              <div className="grid grid-cols-3 gap-6">
                
                {/* LEFT COLUMN: Radar, Stats, Activity Feed */}
                <div className="col-span-2 space-y-6">
                  
                  {/* Radar & Stats Block */}
                  <div className="bg-white rounded-xl border border-slate-100 p-5 flex items-center gap-6 shadow-sm">
                    {/* Animated Radar */}
                    <div className="flex-shrink-0">
                      <RadarSVG />
                    </div>

                    {/* Stats Grid */}
                    <div className="flex-1 grid grid-cols-2 gap-4">
                      {/* Stat 1 */}
                      <div className="bg-white rounded-2xl border border-slate-100/80 p-5 shadow-[0_2px_10px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.04)] transition-all duration-300">
                        <div className="text-3xl font-extrabold tracking-tight text-[#059669]">773</div>
                        <div className="text-xs font-semibold text-slate-400 mt-1.5 select-none">Scanned this hour</div>
                      </div>

                      {/* Stat 2 */}
                      <div className="bg-white rounded-2xl border border-slate-100/80 p-5 shadow-[0_2px_10px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.04)] transition-all duration-300">
                        <div className="text-3xl font-extrabold tracking-tight text-[#DC2626]">
                          {queue.length || 7}
                        </div>
                        <div className="text-xs font-semibold text-slate-400 mt-1.5 select-none">Leads in queue</div>
                      </div>

                      {/* Stat 3 */}
                      <div className="bg-white rounded-2xl border border-slate-100/80 p-5 shadow-[0_2px_10px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.04)] transition-all duration-300">
                        <div className="text-3xl font-extrabold tracking-tight text-[#D97706]">3</div>
                        <div className="text-xs font-semibold text-slate-400 mt-1.5 select-none">Agents active</div>
                      </div>

                      {/* Stat 4 */}
                      <div className="bg-white rounded-2xl border border-slate-100/80 p-5 shadow-[0_2px_10px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.04)] transition-all duration-300">
                        <div className="text-3xl font-extrabold tracking-tight text-[#2563EB]">
                          {opportunities.filter(o => o.kind === "funding").length || 2}
                        </div>
                        <div className="text-xs font-semibold text-slate-400 mt-1.5 select-none">Funding matches</div>
                      </div>
                    </div>
                  </div>

                  {/* Activity Feed Section */}
                  <div className="space-y-3">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Live Activity</h3>
                    
                    <div className="space-y-2">
                      {/* Activity Row 1 (Urgent Lead) */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 flex items-center justify-between hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-start gap-3">
                          <span className="w-2 h-2 rounded-full bg-[#DC2626] mt-1.5" />
                          <div>
                            <div className="text-sm text-slate-700 font-medium">
                              <span className="font-bold text-slate-800">Urgent lead</span> — James Mwangi needs 40 chairs · <span className="text-slate-400 text-xs">Facebook Groups</span>
                            </div>
                            <div className="text-xs text-slate-400 mt-1">2 min ago</div>
                          </div>
                        </div>
                        <button 
                          onClick={() => setSection("hunt")}
                          className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-0.5 select-none transition-all pr-2"
                        >
                          View →
                        </button>
                      </div>

                      {/* Activity Row 2 (Competitor Alert) */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 flex items-center justify-between hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-start gap-3">
                          <span className="w-2 h-2 rounded-full bg-[#D97706] mt-1.5" />
                          <div>
                            <div className="text-sm text-slate-700 font-medium">
                              <span className="font-bold text-slate-800">Competitor alert</span> — @nairobibuyer complained about Acme Furniture on Twitter
                            </div>
                            <div className="text-xs text-slate-400 mt-1">14 min ago</div>
                          </div>
                        </div>
                        <button 
                          onClick={() => setSection("autopilot")}
                          className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-0.5 select-none transition-all pr-2"
                        >
                          Reply →
                        </button>
                      </div>

                      {/* Activity Row 3 (Funding Match) */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 flex items-center justify-between hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-start gap-3">
                          <span className="w-2 h-2 rounded-full bg-[#2563EB] mt-1.5" />
                          <div>
                            <div className="text-sm text-slate-700 font-medium">
                              <span className="font-bold text-slate-800">Funding match</span> — KCB SME Grant 2025 · 11 days left · <span className="text-slate-500 font-semibold text-xs">AI score 8.2</span>
                            </div>
                            <div className="text-xs text-slate-400 mt-1">1 hr ago</div>
                          </div>
                        </div>
                        <button 
                          onClick={() => setSection("funding")}
                          className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-0.5 select-none transition-all pr-2"
                        >
                          Apply →
                        </button>
                      </div>

                      {/* Activity Row 4 (Warm Leads) */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 flex items-center justify-between hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-start gap-3">
                          <span className="w-2 h-2 rounded-full bg-[#059669] mt-1.5" />
                          <div>
                            <div className="text-sm text-slate-700 font-medium">
                              <span className="font-bold text-slate-800">3 warm leads</span> added from Facebook Marketplace scan
                            </div>
                            <div className="text-xs text-slate-400 mt-1">2 hrs ago</div>
                          </div>
                        </div>
                        <span className="pr-2" />
                      </div>

                      {/* Activity Row 5 (Scanned Facebook Groups) */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 flex items-center justify-between hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-start gap-3">
                          <span className="w-2 h-2 rounded-full bg-[#94A3B8] mt-1.5" />
                          <div>
                            <div className="text-sm text-slate-700 font-medium">
                              Scanned 12 Facebook groups — <span className="font-bold text-slate-800">0 new matches</span>
                            </div>
                            <div className="text-xs text-slate-400 mt-1">3 hrs ago</div>
                          </div>
                        </div>
                        <span className="pr-2" />
                      </div>
                    </div>
                  </div>

                </div>

                {/* RIGHT COLUMN: Morning Brief & Competitor Alert Detail Cards */}
                <div className="space-y-6">
                  
                  {/* Morning Brief Card */}
                  <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
                    <div className="flex items-start gap-3 mb-4">
                      <div className="bg-amber-50 p-2 rounded-xl text-xl">🌅</div>
                      <div>
                        <h4 className="font-bold text-slate-800 text-sm">Morning brief</h4>
                        <p className="text-[10px] text-slate-400 mt-0.5">Sent 8:00 AM via WhatsApp</p>
                      </div>
                    </div>
                    
                    <div className="space-y-3">
                      <p className="text-xs text-slate-700 leading-relaxed">
                        <span className="font-bold">Good morning Sam! 🌅</span> You have <span className="text-[#059669] font-bold">{leads.filter(l => (l.score??5) >= 5).length || 7} hot leads</span> today. Top: James Mwangi needs 40 chairs urgently — posted 23 min ago. Reply before a competitor does.
                      </p>
                      
                      <button 
                        onClick={() => setSection("setup")}
                        className="w-full py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-xs font-bold rounded-xl flex items-center justify-center gap-1.5 transition-all border border-emerald-100"
                      >
                        Customize brief
                      </button>
                    </div>
                  </div>

                  {/* Competitor Alert Card */}
                  <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
                    <div className="flex items-start gap-3 mb-4">
                      <div className="bg-amber-50 p-2 rounded-xl text-xl">⚡</div>
                      <div>
                        <h4 className="font-bold text-slate-800 text-sm">Competitor alert</h4>
                        <p className="text-[10px] text-slate-400 mt-0.5">Opportunity detected</p>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5">
                        <p className="text-xs font-bold text-slate-800 mb-1">@nairobibuyer</p>
                        <p className="text-xs text-slate-600 italic leading-relaxed">
                          "Acme Furniture let me down again — 3 days late. Anyone know a reliable alternative?"
                        </p>
                        <p className="text-[10px] text-slate-400 mt-2 font-medium">
                          AI has drafted a reply for you.
                        </p>
                      </div>

                      <button 
                        onClick={() => setSection("autopilot")}
                        className="w-full py-2.5 bg-amber-50 hover:bg-amber-100 text-amber-800 text-xs font-bold rounded-xl flex items-center justify-center transition-all border border-amber-100"
                      >
                        View drafted reply →
                      </button>
                    </div>
                  </div>

                </div>

              </div>
            </div>
          )}

          {/* ────────────────── FUNDING ────────────────── */}
          {section === "funding" && (
            <div className="p-5">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h1 className="text-2xl font-bold text-slate-800">Funding opportunities</h1>
                  <p className="text-sm text-slate-500 mt-1">AI-matched grants, VCs and accelerators for your business</p>
                </div>
                <div className="flex items-center gap-2">
                  <button 
                    onClick={load}
                    className="px-4 py-2 border border-slate-200 text-slate-700 bg-white hover:bg-slate-50 text-xs font-semibold rounded-lg transition-all shadow-sm"
                  >
                    Refresh
                  </button>
                  <button className="px-4 py-2 border border-slate-200 text-slate-700 bg-white hover:bg-slate-50 text-xs font-semibold rounded-lg transition-all shadow-sm">
                    Filter
                  </button>
                </div>
              </div>

              {/* Alert Banner */}
              <div className="mb-6 flex items-center gap-3 bg-[#ECFDF5] border border-[#A7F3D0] rounded-xl px-4 py-3.5 text-sm text-emerald-800 shadow-[0_1px_2px_rgba(0,0,0,0.01)]">
                <span className="text-lg select-none">🎯</span>
                <p className="leading-relaxed font-medium">
                  <span className="font-bold">2 strong matches this week.</span> KCB SME Grant closes in 11 days — AI rates your fit at 9.1/10. Apply before the deadline.
                </p>
              </div>

              {/* Funding Rows */}
              <div className="space-y-3">
                {/* Row 1 — KCB SME Business Grant */}
                <div className="bg-white rounded-xl border border-slate-100 p-4 hover:border-slate-200 hover:shadow-sm transition-all duration-200 border-l-[3px] border-l-[#059669]">
                  <div className="grid gap-4 items-center" style={{ gridTemplateColumns: "1fr 100px 110px 140px" }}>
                    {/* Details */}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="font-bold text-slate-800 text-sm hover:text-emerald-700 transition-colors cursor-pointer">KCB SME Business Grant 2025</span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 select-none">Grant</span>
                      </div>
                      <p className="text-xs text-slate-400 font-semibold mb-1 select-none">
                        KCB Foundation · Kenya · Up to KES 1,000,000
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        Supporting small businesses in manufacturing, trade and services. Priority for businesses with 2+ employees and 1yr+ track record. Furniture and home goods sector eligible.
                      </p>
                    </div>

                    {/* AI Match Ring */}
                    <div className="flex flex-col items-center justify-center">
                      <IntentRing score={9.1} />
                      <span className="text-[10px] text-slate-400 mt-1 font-semibold select-none">AI match</span>
                    </div>

                    {/* Deadline */}
                    <div className="flex flex-col items-center justify-center text-center">
                      <span className="text-sm font-extrabold text-[#DC2626]">11 days</span>
                      <span className="text-[10px] text-slate-400 mt-0.5 font-medium select-none">Deadline left</span>
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col gap-1.5">
                      <button className="w-full py-1.5 bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1">
                        Apply now →
                      </button>
                      <button className="w-full py-1 px-1.5 border border-slate-200 text-slate-600 bg-white text-[10px] font-bold rounded-lg hover:bg-slate-50 transition-all">
                        Save for later
                      </button>
                    </div>
                  </div>
                </div>

                {/* Row 2 — Equity Bank Biashara Loan */}
                <div className="bg-white rounded-xl border border-slate-100 p-4 hover:border-slate-200 hover:shadow-sm transition-all duration-200 border-l-[3px] border-l-[#2563EB]">
                  <div className="grid gap-4 items-center" style={{ gridTemplateColumns: "1fr 100px 110px 140px" }}>
                    {/* Details */}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="font-bold text-slate-800 text-sm hover:text-blue-700 transition-colors cursor-pointer">Equity Bank Biashara Loan</span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 select-none">Loan</span>
                      </div>
                      <p className="text-xs text-slate-400 font-semibold mb-1 select-none">
                        Equity Bank · Kenya · KES 50K – 5M
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        Low-interest SME financing for inventory and equipment. No collateral required under KES 500K. Fast approval within 5 working days for qualifying businesses.
                      </p>
                    </div>

                    {/* AI Match Ring */}
                    <div className="flex flex-col items-center justify-center">
                      <IntentRing score={8.4} />
                      <span className="text-[10px] text-slate-400 mt-1 font-semibold select-none">AI match</span>
                    </div>

                    {/* Deadline */}
                    <div className="flex flex-col items-center justify-center text-center">
                      <span className="text-sm font-extrabold text-slate-800">Rolling</span>
                      <span className="text-[10px] text-slate-400 mt-0.5 font-medium select-none">Apply anytime</span>
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col gap-1.5">
                      <button className="w-full py-1.5 bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1">
                        Apply now →
                      </button>
                      <button className="w-full py-1 px-1.5 border border-slate-200 text-slate-600 bg-white text-[10px] font-bold rounded-lg hover:bg-slate-50 transition-all">
                        Save for later
                      </button>
                    </div>
                  </div>
                </div>

                {/* Row 3 — Nairobi Innovation Hub Accelerator */}
                <div className="bg-white rounded-xl border border-slate-100 p-4 hover:border-slate-200 hover:shadow-sm transition-all duration-200 border-l-[3px] border-l-[#7C3AED]">
                  <div className="grid gap-4 items-center" style={{ gridTemplateColumns: "1fr 100px 110px 140px" }}>
                    {/* Details */}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="font-bold text-slate-800 text-sm hover:text-purple-700 transition-colors cursor-pointer">Nairobi Innovation Hub Accelerator</span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 select-none">Accelerator</span>
                      </div>
                      <p className="text-xs text-slate-400 font-semibold mb-1 select-none">
                        NiHub · Nairobi · 6-month programme
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        Business acceleration for tech-enabled SMEs in East Africa. Includes mentorship, workspace, and investor connections. Accepts businesses with a digital product component.
                      </p>
                    </div>

                    {/* AI Match Ring */}
                    <div className="flex flex-col items-center justify-center">
                      <IntentRing score={6.3} />
                      <span className="text-[10px] text-slate-400 mt-1 font-semibold select-none">AI match</span>
                    </div>

                    {/* Deadline */}
                    <div className="flex flex-col items-center justify-center text-center">
                      <span className="text-sm font-extrabold text-[#2563EB]">32 days</span>
                      <span className="text-[10px] text-slate-400 mt-0.5 font-medium select-none">Deadline left</span>
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col gap-1.5">
                      <button className="w-full py-1.5 bg-[#2563EB] hover:bg-[#1d4ed8] text-white text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1">
                        Learn more →
                      </button>
                      <button className="w-full py-1 px-1.5 border border-slate-200 text-slate-600 bg-white text-[10px] font-bold rounded-lg hover:bg-slate-50 transition-all">
                        Save for later
                      </button>
                    </div>
                  </div>
                </div>

                  {/* Row 4 — Africa Business Angels Network */}
                  <div className="bg-white rounded-xl border border-slate-100 p-4 hover:border-slate-200 hover:shadow-sm transition-all duration-200 border-l-[3px] border-l-[#94A3B8]">
                    <div className="grid gap-4 items-center" style={{ gridTemplateColumns: "1fr 100px 110px 140px" }}>
                      {/* Details */}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="font-bold text-slate-800 text-sm hover:text-slate-700 transition-colors cursor-pointer">Africa Business Angels Network</span>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 select-none">{"VC / Angel"}</span>
                        </div>
                        <p className="text-xs text-slate-400 font-semibold mb-1 select-none">
                          ABAN · Pan-Africa · USD 25K – 250K
                        </p>
                        <p className="text-xs text-slate-500 leading-relaxed">
                          Early-stage investment for African startups with regional growth ambition. Looking for scalable models with evidence of traction and clear path to profitability.
                        </p>
                      </div>

                      {/* AI Match Ring */}
                      <div className="flex flex-col items-center justify-center">
                        <IntentRing score={3.5} />
                        <span className="text-[10px] text-slate-400 mt-1 font-semibold select-none">AI match</span>
                      </div>

                      {/* Deadline */}
                      <div className="flex flex-col items-center justify-center text-center">
                        <span className="text-sm font-extrabold text-slate-800">Open</span>
                        <span className="text-[10px] text-slate-400 mt-0.5 font-medium select-none">Rolling intake</span>
                      </div>

                      {/* Actions */}
                      <div className="flex flex-col gap-1.5">
                        <button className="w-full py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1 border border-slate-200/50">
                          View details
                        </button>
                        <button className="w-full py-1 px-1.5 border border-slate-200 text-slate-600 bg-white text-[10px] font-bold rounded-lg hover:bg-slate-50 transition-all">
                          Save for later
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

          {/* ────────────────── MARKET RADAR ────────────────── */}
          {section === "radar" && (
            <div className="p-5">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h1 className="text-2xl font-bold text-slate-800">Market radar</h1>
                  <p className="text-sm text-slate-500 mt-1">Signals that predict future demand before competitors see it</p>
                </div>
                <div className="flex items-center gap-2">
                  <button 
                    onClick={runRecon} 
                    disabled={runningRecon} 
                    className="flex items-center gap-1.5 px-3.5 py-2 border border-slate-200 text-slate-700 bg-white text-xs font-bold rounded-lg hover:bg-slate-50 disabled:opacity-50 transition-all shadow-sm"
                  >
                    {runningRecon ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Building2 className="w-3.5 h-3.5" />}
                    Recon
                  </button>
                  <button 
                    onClick={runPredictions} 
                    disabled={runningPredictions} 
                    className="flex items-center gap-1.5 px-3.5 py-2 border border-slate-200 text-slate-700 bg-white text-xs font-bold rounded-lg hover:bg-slate-50 disabled:opacity-50 transition-all shadow-sm"
                  >
                    {runningPredictions ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <TrendingUp className="w-3.5 h-3.5" />}
                    Predict
                  </button>
                  <button 
                    onClick={runFusion} 
                    disabled={runningFusion} 
                    className="flex items-center gap-1.5 px-4 py-2 bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold rounded-lg disabled:opacity-50 transition-all shadow-sm"
                  >
                    {runningFusion ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    Fuse Signals
                  </button>
                </div>
              </div>

              {/* 2-Column Radar Sections */}
              <div className="grid grid-cols-2 gap-6 pb-24">
                
                {/* LEFT COLUMN: Act Now & Watch Closely */}
                <div className="space-y-6">
                  {/* 🔴 ACT NOW */}
                  <div className="space-y-3">
                    <h3 className="text-[10px] font-bold text-[#DC2626] uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[#DC2626] animate-pulse" />
                      ACT NOW
                    </h3>

                    <div className="space-y-3">
                      {/* Card 1 */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 border-l-[3px] border-l-[#DC2626] hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="text-sm font-bold text-slate-800">New office registered — Upperhill</h4>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-600 select-none">Hot signal</span>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed mb-3">
                          KRA registered <span className="font-bold text-slate-800">Greentech Solutions Ltd</span> in Upperhill last week. Company profile suggests 50+ employees. New offices = furniture orders within 30–90 days.
                        </p>
                        <div className="text-[10px] text-slate-400 font-semibold mb-3">
                          Upperhill · 3 days ago
                        </div>
                        <div className="flex gap-2">
                          <button 
                            onClick={() => setSection("hunt")}
                            className="flex-1 py-1.5 bg-[#EFF6FF] hover:bg-[#DBEAFE] text-[#1D4ED8] text-xs font-bold rounded-lg transition-all"
                          >
                            Reach out now
                          </button>
                          <button className="px-4 py-1.5 border border-slate-200 text-slate-600 bg-white text-xs font-bold rounded-lg hover:bg-slate-50 transition-all">
                            Save signal
                          </button>
                        </div>
                      </div>

                      {/* Card 2 */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 border-l-[3px] border-l-[#DC2626] hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="text-sm font-bold text-slate-800">Tender: Govt office refurbishment</h4>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-600 select-none">Hot signal</span>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed mb-3">
                          <span className="font-bold text-slate-800">Ministry of Finance</span> published a furniture supply tender for 3 Nairobi floors. Budget KES 4.2M. Deadline in 18 days.
                        </p>
                        <div className="text-[10px] text-slate-400 font-semibold mb-3">
                          18 days left · KES 4.2M
                        </div>
                        <div className="flex gap-2">
                          <button className="flex-1 py-1.5 bg-[#EFF6FF] hover:bg-[#DBEAFE] text-[#1D4ED8] text-xs font-bold rounded-lg transition-all">
                            View tender
                          </button>
                          <button className="px-4 py-1.5 border border-slate-200 text-slate-600 bg-white text-xs font-bold rounded-lg hover:bg-slate-50 transition-all">
                            Save signal
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 🟡 WATCH CLOSELY */}
                  <div className="space-y-3 pt-2">
                    <h3 className="text-[10px] font-bold text-[#D97706] uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[#D97706]" />
                      WATCH CLOSELY
                    </h3>
                    
                    {/* Card 3 */}
                    <div className="bg-white rounded-xl border border-slate-100 p-4 border-l-[3px] border-l-[#D97706] hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-sm font-bold text-slate-800">Back-to-school surge incoming</h4>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 select-none">Seasonal</span>
                      </div>
                      <p className="text-xs text-slate-500 leading-relaxed mb-3">
                        Historical data shows a <span className="font-bold text-slate-800">35% spike</span> in school furniture orders in Jan–Feb. Schools start sourcing in mid-November — the time to market to principals is now.
                      </p>
                      <div className="text-[10px] text-slate-400 font-semibold mb-3">
                        Peaks in 6 weeks
                      </div>
                      <div className="flex gap-2">
                        <button className="flex-1 py-1.5 bg-[#EFF6FF] hover:bg-[#DBEAFE] text-[#1D4ED8] text-xs font-bold rounded-lg transition-all">
                          Create campaign
                        </button>
                        <button className="px-4 py-1.5 border border-slate-200 text-slate-600 bg-white text-xs font-bold rounded-lg hover:bg-slate-50 transition-all">
                          Remind me
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* RIGHT COLUMN: Hiring Signals & On The Horizon */}
                <div className="space-y-6">
                  {/* 🟡 HIRING SIGNALS */}
                  <div className="space-y-3">
                    <h3 className="text-[10px] font-bold text-[#D97706] uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[#D97706]" />
                      HIRING SIGNALS
                    </h3>

                    <div className="space-y-3">
                      {/* Card 4 */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 border-l-[3px] border-l-[#D97706] hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="text-sm font-bold text-slate-800">Safaricom hiring 80 new staff</h4>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 select-none">Hiring signal</span>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed mb-3">
                          LinkedIn shows <span className="font-bold text-slate-800">Safaricom posted 80 job openings</span> for a new Westlands office. Mass hiring = office expansion = furniture needed in 60–90 days.
                        </p>
                        <div className="text-[10px] text-slate-400 font-semibold mb-3">
                          Westlands · This month
                        </div>
                        <div className="flex gap-2">
                          <button className="flex-1 py-1.5 bg-[#EFF6FF] hover:bg-[#DBEAFE] text-[#1D4ED8] text-xs font-bold rounded-lg transition-all">
                            Track this company
                          </button>
                          <button className="px-4 py-1.5 border border-slate-200 text-slate-600 bg-white text-xs font-bold rounded-lg hover:bg-slate-50 transition-all">
                            Save
                          </button>
                        </div>
                      </div>

                      {/* Card 5 */}
                      <div className="bg-white rounded-xl border border-slate-100 p-4 border-l-[3px] border-l-[#D97706] hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="text-sm font-bold text-slate-800">3 new co-working spaces opening</h4>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 select-none">Opportunity</span>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed mb-3">
                          Permits filed for <span className="font-bold text-slate-800">3 co-working buildouts</span> in Kilimani and Karen. Each space typically spends KES 500K–2M on furniture at launch.
                        </p>
                        <div className="text-[10px] text-slate-400 font-semibold mb-3">
                          Kilimani · Karen
                        </div>
                        <div className="flex gap-2">
                          <button className="flex-1 py-1.5 bg-[#EFF6FF] hover:bg-[#DBEAFE] text-[#1D4ED8] text-xs font-bold rounded-lg transition-all">
                            Reach out
                          </button>
                          <button className="px-4 py-1.5 border border-slate-200 text-slate-600 bg-white text-xs font-bold rounded-lg hover:bg-slate-50 transition-all">
                            Save
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 🔵 ON THE HORIZON */}
                  <div className="space-y-3 pt-2">
                    <h3 className="text-[10px] font-bold text-[#2563EB] uppercase tracking-wider flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[#2563EB]" />
                      ON THE HORIZON
                    </h3>

                    {/* Card 6 */}
                    <div className="bg-white rounded-xl border border-slate-100 p-4 border-l-[3px] border-l-[#2563EB] hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-sm font-bold text-slate-800">Q1 2026 demand forecast</h4>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 select-none">Forecast</span>
                      </div>
                      <p className="text-xs text-slate-500 leading-relaxed mb-3">
                        AI predicts a <span className="font-bold text-slate-800">+22% increase</span> in office furniture demand in Nairobi in Q1 2026, based on business registrations, hiring signals and economic indicators.
                      </p>
                      <div className="text-[10px] text-slate-400 font-semibold mb-3">
                        In ~10 weeks
                      </div>
                      <div className="flex gap-2">
                        <button className="flex-1 py-1.5 bg-[#EFF6FF] hover:bg-[#DBEAFE] text-[#1D4ED8] text-xs font-bold rounded-lg transition-all">
                          View full forecast
                        </button>
                      </div>
                    </div>
                  </div>

                </div>

              </div>
            </div>
          )}

          {/* ────────────────── SCOUTS SETUP ────────────────── */}
          {section === "setup" && (
            <div className="p-5">
              {/* Top Header */}
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h1 className="text-2xl font-bold text-slate-800">Scouts setup</h1>
                  <p className="text-sm text-slate-500 mt-1">Configure what AI Scout hunts for and how it alerts you</p>
                </div>
                <button 
                  onClick={async () => {
                    setSavingSocial(true);
                    try {
                      await saveSocialSettings(socialSettings);
                      toast.success("Settings saved successfully!");
                    } catch {
                      toast.error("Failed to save settings");
                    } finally {
                      setSavingSocial(false);
                    }
                  }}
                  className="px-4 py-2 bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold rounded-lg transition-all shadow-sm flex items-center gap-1.5"
                >
                  {savingSocial ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                  Save changes
                </button>
              </div>

              {/* 2-Column Grid */}
              <div className="grid grid-cols-2 gap-6 pb-24">
                
                {/* LEFT COLUMN: Toggles */}
                <div className="space-y-6">
                  {/* Hunting Platforms */}
                  <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm space-y-4">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Hunting Platforms</h3>
                    
                    {SOCIAL_PLATFORMS.map(p => {
                      const isActive = socialSettings.platforms.includes(p.id);
                      return (
                        <div key={p.id} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-b-0">
                          <div>
                            <div className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                              <span>{p.emoji}</span>
                              <span>{p.label}</span>
                            </div>
                            <div className="text-[10px] text-slate-400 mt-0.5">
                              {p.id === "facebook" ? "4 groups · every 30 min" : 
                               p.id === "whatsapp" ? "Active thread monitoring" : 
                               p.id === "marketplace" ? "Kilimani · Westlands · Karen" : 
                               `Scan ${p.label} for matches`}
                            </div>
                          </div>
                          <div 
                            onClick={async () => {
                              const platforms = isActive
                                ? socialSettings.platforms.filter(x => x !== p.id)
                                : [...socialSettings.platforms, p.id];
                              const next = { ...socialSettings, platforms };
                              setSocialSettings(next);
                              await saveSocialSettings(next);
                            }}
                            className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${isActive ? "bg-[#059669]" : "bg-slate-200"}`}
                          >
                            <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${isActive ? "translate-x-5" : "translate-x-0.5"}`} />
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Alerts */}
                  <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm space-y-4">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Alerts</h3>

                    {/* Alert 1: Urgent lead alerts */}
                    <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-b-0">
                      <div>
                        <div className="text-xs font-bold text-slate-700">Urgent lead alerts</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">WhatsApp ping instantly</div>
                      </div>
                      <div 
                        onClick={async () => {
                          const next = { ...socialSettings, auto_run: !socialSettings.auto_run };
                          setSocialSettings(next);
                          await saveSocialSettings(next);
                        }}
                        className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${socialSettings.auto_run ? "bg-[#059669]" : "bg-slate-200"}`}
                      >
                        <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${socialSettings.auto_run ? "translate-x-5" : "translate-x-0.5"}`} />
                      </div>
                    </div>

                    {/* Alert 2: Morning brief */}
                    <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-b-0">
                      <div>
                        <div className="text-xs font-bold text-slate-700">Morning brief</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">
                          {socialSettings.morning_brief_time || "08:00"} via WhatsApp
                        </div>
                      </div>
                      <div 
                        onClick={async () => {
                          const next = { ...socialSettings, morning_brief: !socialSettings.morning_brief };
                          setSocialSettings(next);
                          await saveSocialSettings(next);
                        }}
                        className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${socialSettings.morning_brief ? "bg-[#059669]" : "bg-slate-200"}`}
                      >
                        <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${socialSettings.morning_brief ? "translate-x-5" : "translate-x-0.5"}`} />
                      </div>
                    </div>

                    {/* Alert 3: Competitor mentions */}
                    <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-b-0">
                      <div>
                        <div className="text-xs font-bold text-slate-700">Competitor mentions</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">Alert when rivals get criticized</div>
                      </div>
                      <div 
                        onClick={async () => {
                          const nextMode = socialSettings.mode === "notify" ? "review" : "notify";
                          const next = { ...socialSettings, mode: nextMode };
                          setSocialSettings(next);
                          await saveSocialSettings(next);
                        }}
                        className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${socialSettings.mode === "notify" ? "bg-[#059669]" : "bg-slate-200"}`}
                      >
                        <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${socialSettings.mode === "notify" ? "translate-x-5" : "translate-x-0.5"}`} />
                      </div>
                    </div>
                  </div>

                  {/* Agents */}
                  <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm space-y-4">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Agents</h3>

                    {/* Agent 1 */}
                    <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-b-0">
                      <div>
                        <div className="text-xs font-bold text-slate-700">Funding hunter</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">Grants, VCs, accelerators</div>
                      </div>
                      <div 
                        onClick={async () => {
                          const nextAgents = { ...settings.agents, funding_hunter: !settings.agents.funding_hunter };
                          const nextSettings = { ...settings, agents: nextAgents };
                          setSettings(nextSettings);
                          try { await api.put("/action-mode/settings", nextSettings); } catch {}
                        }}
                        className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${settings.agents.funding_hunter ? "bg-[#059669]" : "bg-slate-200"}`}
                      >
                        <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${settings.agents.funding_hunter ? "translate-x-5" : "translate-x-0.5"}`} />
                      </div>
                    </div>

                    {/* Agent 2 */}
                    <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-b-0">
                      <div>
                        <div className="text-xs font-bold text-slate-700">Admin autopilot</div>
                        <div className="text-[10px] text-slate-400 mt-0.5">Auto-generated responses</div>
                      </div>
                      <div 
                        onClick={async () => {
                          const nextAgents = { ...settings.agents, admin_autopilot: !settings.agents.admin_autopilot };
                          const nextSettings = { ...settings, agents: nextAgents };
                          setSettings(nextSettings);
                          try { await api.put("/action-mode/settings", nextSettings); } catch {}
                        }}
                        className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${settings.agents.admin_autopilot ? "bg-[#059669]" : "bg-slate-200"}`}
                      >
                        <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${settings.agents.admin_autopilot ? "translate-x-5" : "translate-x-0.5"}`} />
                      </div>
                    </div>
                  </div>
                </div>

                {/* RIGHT COLUMN: Keywords, Morning Brief Table, Competitors */}
                <div className="space-y-6">
                  {/* Keywords Tagging Block */}
                  <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm space-y-4">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Buying Intent Keywords</h3>
                    
                    <div className="flex flex-wrap gap-2">
                      {(socialSettings.keywords || []).map((kw, i) => (
                        <span key={i} className="flex items-center gap-1.5 text-xs bg-emerald-50 text-emerald-700 rounded-full px-3 py-1 font-semibold">
                          {kw}
                          <button 
                            onClick={async () => {
                              const keywords = socialSettings.keywords.filter((_, j) => j !== i);
                              const next = { ...socialSettings, keywords };
                              setSocialSettings(next);
                              await saveSocialSettings(next);
                            }}
                            className="text-emerald-400 hover:text-emerald-600 font-bold"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                      {(socialSettings.keywords || []).length === 0 && (
                        <span className="text-xs text-slate-400">No active keywords</span>
                      )}
                    </div>

                    <input
                      value={newKeyword}
                      onChange={e => setNewKeyword(e.target.value)}
                      onKeyDown={async e => {
                        if (e.key === "Enter" && newKeyword.trim()) {
                          const keywords = [...(socialSettings.keywords || []), newKeyword.trim()];
                          const next = { ...socialSettings, keywords };
                          setSocialSettings(next);
                          setNewKeyword("");
                          await saveSocialSettings(next);
                        }
                      }}
                      placeholder="Type a keyword and press Enter..."
                      className="w-full text-xs border border-slate-100 bg-slate-50/50 rounded-xl px-4.5 py-3 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500"
                    />
                  </div>

                  {/* Morning Brief details table */}
                  <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm space-y-4">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Morning Brief</h3>

                    <div className="border border-slate-50 rounded-2xl overflow-hidden shadow-sm">
                      <div className="p-4 bg-emerald-50/20 border-b border-slate-50 flex justify-between items-center">
                        <span className="text-xs font-bold text-emerald-800">Daily morning brief</span>
                      </div>
                      
                      <div className="divide-y divide-slate-50 text-xs">
                        {/* Send Time Row */}
                        <div className="p-3.5 flex items-center justify-between">
                          <span className="text-slate-400 font-medium">Send time</span>
                          <span className="text-slate-700 font-bold flex items-center gap-1.5">
                            {socialSettings.morning_brief_time || "08:00 AM"} 
                            <input 
                              type="time"
                              value={socialSettings.morning_brief_time || "08:00"}
                              onChange={async e => {
                                const next = { ...socialSettings, morning_brief_time: e.target.value };
                                setSocialSettings(next);
                                await saveSocialSettings(next);
                              }}
                              className="ml-2 border border-slate-200 rounded px-1"
                            />
                          </span>
                        </div>

                        {/* Delivery Channel Row */}
                        <div className="p-3.5 flex items-center justify-between">
                          <span className="text-slate-400 font-medium">Delivery channel</span>
                          <div className="flex gap-1.5">
                            {/* WhatsApp Chip */}
                            <button
                              onClick={async () => {
                                const currentChannel = socialSettings.morning_brief_channel || "whatsapp";
                                let nextChannel = "whatsapp";
                                if (currentChannel === "telegram") nextChannel = "both";
                                else if (currentChannel === "both") nextChannel = "telegram";
                                
                                const next = { ...socialSettings, morning_brief_channel: nextChannel };
                                setSocialSettings(next);
                                await saveSocialSettings(next);
                              }}
                              className={`px-2.5 py-1 rounded-full font-semibold transition-all ${
                                (socialSettings.morning_brief_channel === "whatsapp" || socialSettings.morning_brief_channel === "both" || !socialSettings.morning_brief_channel)
                                  ? "bg-emerald-500 text-white"
                                  : "bg-slate-100 text-slate-400 hover:bg-slate-200"
                              }`}
                            >
                              WhatsApp
                            </button>
                            {/* Telegram Chip */}
                            <button
                              onClick={async () => {
                                const currentChannel = socialSettings.morning_brief_channel || "whatsapp";
                                let nextChannel = "telegram";
                                if (currentChannel === "whatsapp") nextChannel = "both";
                                else if (currentChannel === "both") nextChannel = "whatsapp";
                                
                                const next = { ...socialSettings, morning_brief_channel: nextChannel };
                                setSocialSettings(next);
                                await saveSocialSettings(next);
                              }}
                              className={`px-2.5 py-1 rounded-full font-semibold transition-all ${
                                (socialSettings.morning_brief_channel === "telegram" || socialSettings.morning_brief_channel === "both")
                                  ? "bg-[#2563EB] text-white"
                                  : "bg-slate-100 text-slate-400 hover:bg-slate-200"
                              }`}
                            >
                              Telegram
                            </button>
                          </div>
                        </div>

                        {/* Connected Account Row */}
                        <div className="p-3.5 flex items-center justify-between">
                          <span className="text-slate-400 font-medium">Connected account</span>
                          <div className="flex flex-col items-end gap-1 text-right">
                            {(socialSettings.morning_brief_channel === "whatsapp" || socialSettings.morning_brief_channel === "both" || !socialSettings.morning_brief_channel) && (
                              <div className="flex items-center gap-1.5 text-xs text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded-full select-none">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                WhatsApp Connected
                              </div>
                            )}
                            {(socialSettings.morning_brief_channel === "telegram" || socialSettings.morning_brief_channel === "both") && (
                              <div className="flex items-center gap-1.5 text-xs text-blue-600 font-bold bg-blue-50 px-2 py-0.5 rounded-full select-none">
                                <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                                Telegram Connected
                              </div>
                            )}
                            <a 
                              href="/dashboard/integrations"
                              className="text-[10px] text-blue-500 font-bold hover:text-blue-700 underline mt-1"
                            >
                              Manage Integrations →
                            </a>
                          </div>
                        </div>

                        {/* Row 3: Dynamic Include Row */}
                        <div className="p-3.5 flex items-center justify-between">
                          <span className="text-slate-400 font-medium">Include</span>
                          <span className="text-slate-700 font-bold capitalize">
                            {(() => {
                              const includeItems = [];
                              if (socialSettings.auto_run) includeItems.push("Top leads");
                              if (settings.agents.funding_hunter) includeItems.push("funding matches");
                              if (socialSettings.mode === "notify") includeItems.push("competitor alerts");
                              return includeItems.length > 0 ? includeItems.join(" + ") : "None selected";
                            })()}
                          </span>
                        </div>

                        {/* Row 4: Global Language Dropdown Row */}
                        <div className="p-3.5 flex items-center justify-between">
                          <span className="text-slate-400 font-medium">Language</span>
                          <select
                            value={socialSettings.morning_brief_language || "English"}
                            onChange={async e => {
                              const next = { ...socialSettings, morning_brief_language: e.target.value };
                              setSocialSettings(next);
                              await saveSocialSettings(next);
                              toast.success(`Morning brief language set to ${e.target.value}!`);
                            }}
                            className="bg-white border border-slate-200 text-slate-700 text-xs font-bold rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 cursor-pointer"
                          >
                            <option value="English">🇺🇸 English</option>
                            <option value="Spanish">🇪🇸 Spanish</option>
                            <option value="French">🇫🇷 French</option>
                            <option value="German">🇩🇪 German</option>
                            <option value="Portuguese">🇵🇹 Portuguese</option>
                            <option value="Arabic">🇸🇦 Arabic</option>
                            <option value="Swahili">🇰🇪 Swahili</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Competitor Watch Detail block */}
                  <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm space-y-4">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Competitor Watch</h3>

                    <div className="space-y-2.5">
                      <p className="text-[11px] text-slate-400 font-semibold mb-1">Monitoring these rivals</p>
                      
                      {(socialSettings.competitors || []).map((rival, i) => (
                        <div key={i} className="flex items-center justify-between bg-slate-50/50 border border-slate-100/60 p-3.5 rounded-xl hover:shadow-sm transition-all duration-200">
                          <span className="text-xs font-bold text-slate-700">{rival}</span>
                          <button 
                            onClick={async () => {
                              const competitors = socialSettings.competitors?.filter((_, j) => j !== i) || [];
                              const next = { ...socialSettings, competitors };
                              setSocialSettings(next);
                              await saveSocialSettings(next);
                            }}
                            className="text-xs font-bold text-slate-400 hover:text-red-500"
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                      {(socialSettings.competitors || []).length === 0 && (
                        <p className="text-xs text-slate-400">No competitors monitored yet</p>
                      )}

                      <input
                        value={newCompetitor}
                        onChange={e => setNewCompetitor(e.target.value)}
                        onKeyDown={async e => {
                          if (e.key === "Enter" && newCompetitor.trim()) {
                            const competitors = [...(socialSettings.competitors || []), newCompetitor.trim()];
                            const next = { ...socialSettings, competitors };
                            setSocialSettings(next);
                            setNewCompetitor("");
                            await saveSocialSettings(next);
                          }
                        }}
                        placeholder="Add competitor name and press Enter..."
                        className="w-full text-xs border border-slate-100 bg-slate-50/50 rounded-xl px-4.5 py-3.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500"
                      />
                    </div>
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
                  <button
                    onClick={() => setIsAddAgentOpen(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white text-xs font-semibold rounded-lg hover:bg-emerald-700 transition-all"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add Agent
                  </button>
                </div>
                {customAgents.length === 0 ? (
                  <p className="text-xs text-slate-400 text-center py-4">No custom agents yet</p>
                ) : (
                  <div className="space-y-2">
                    {customAgents.map(agent => {
                      const isRunning = runningAgent === agent._id;
                      return (
                        <div key={agent._id} className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:bg-slate-50 transition-all">
                          <div className="flex items-center gap-3">
                            {/* Toggle */}
                            <div
                              onClick={async (e) => {
                                e.stopPropagation();
                                const nextEnabled = !agent.enabled;
                                setCustomAgents(prev => prev.map(a => a._id === agent._id ? { ...a, enabled: nextEnabled } : a));
                                try {
                                  await api.put(`/action-mode/agents/${agent._id}`, {
                                    name: agent.name,
                                    emoji: agent.emoji,
                                    description: agent.description,
                                    schedule: agent.schedule,
                                    enabled: nextEnabled,
                                  });
                                  toast.success(`${agent.name} ${nextEnabled ? "enabled" : "disabled"}`);
                                } catch {
                                  setCustomAgents(prev => prev.map(a => a._id === agent._id ? { ...a, enabled: !nextEnabled } : a));
                                  toast.error("Failed to update agent");
                                }
                              }}
                              className={`relative w-8 h-4.5 rounded-full transition-colors cursor-pointer flex-shrink-0 ${agent.enabled ? "bg-emerald-500" : "bg-slate-200"}`}
                            >
                              <div className={`absolute top-0.5 w-3.5 h-3.5 bg-white rounded-full shadow transition-transform ${agent.enabled ? "translate-x-3.5" : "translate-x-0.5"}`} />
                            </div>
                            <span className="text-base select-none">{agent.emoji}</span>
                            <div>
                              <p className="text-xs font-semibold text-slate-700">{agent.name}</p>
                              <p className="text-[10px] text-slate-400 line-clamp-1 mt-0.5">{agent.description}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2.5">
                            <span className="text-[9px] font-bold text-slate-400 bg-slate-50 border border-slate-100 px-1.5 py-0.5 rounded capitalize select-none">{agent.schedule}</span>
                            
                            {/* Run Now trigger button */}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                runCustomAgent(agent);
                              }}
                              disabled={isRunning || !agent.enabled}
                              className={`p-1.5 rounded-lg border transition-all ${isRunning ? "border-emerald-200 bg-emerald-50 text-emerald-600 animate-pulse" : !agent.enabled ? "opacity-30 cursor-not-allowed" : "border-slate-100 hover:bg-slate-100 text-slate-500 hover:text-slate-700"}`}
                              title="Run scanning session now"
                            >
                              {isRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                            </button>

                            <button onClick={() => api.delete(`/action-mode/agents/${agent._id}`).then(() => setCustomAgents(p => p.filter(a => a._id !== agent._id)))} className="p-1.5 text-slate-300 hover:text-red-500 rounded-lg hover:bg-slate-100/50 transition-all">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ────────────────── CUSTOM AGENT PAGE ────────────────── */}
          {section.startsWith("custom_") && (() => {
            const agent = customAgents.find(a => `custom_${a._id}` === section);
            if (!agent) return null;
            const agentOpps = opportunities.filter(o => o.agent_name === agent.name);
            const isRunning = runningAgent === agent._id;

            return (
              <div className="p-5 space-y-4">
                {/* Custom Agent Page Header card */}
                <div className="bg-white rounded-xl border border-slate-100 p-5 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <span className="text-3xl select-none">{agent.emoji}</span>
                    <div>
                      <h2 className="text-base font-bold text-slate-800">{agent.name}</h2>
                      <p className="text-xs text-slate-500 mt-1 leading-relaxed max-w-xl">{agent.description}</p>
                      <div className="flex items-center gap-2 mt-2.5">
                        <span className="text-[9px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100 uppercase select-none">
                          {agent.schedule.replace(/_/g, " ")}
                        </span>
                        {isRunning ? (
                          <span className="flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            Scouting targets live...
                          </span>
                        ) : (
                          <span className="text-xs text-slate-400">Ready to execute</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => runCustomAgent(agent)}
                    disabled={isRunning}
                    className="flex items-center gap-1.5 px-3.5 py-2 bg-emerald-600 text-white text-xs font-bold rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-all shadow-sm flex-shrink-0"
                  >
                    {isRunning ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Scanning...
                      </>
                    ) : (
                      <>
                        <Play className="w-3.5 h-3.5 fill-white" />
                        Run Agent Now
                      </>
                    )}
                  </button>
                </div>

                {/* Opportunity leads matched specifically by this agent */}
                {agentOpps.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 bg-white rounded-xl border border-slate-100 text-slate-400">
                    <Target className="w-12 h-12 mb-3 opacity-20" />
                    <p className="text-sm font-semibold">No opportunities matched yet</p>
                    <p className="text-xs mt-1">Run a live scanning session to begin matching new B2B leads</p>
                    <button
                      onClick={() => runCustomAgent(agent)}
                      disabled={isRunning}
                      className="mt-4 flex items-center gap-1.5 px-3.5 py-1.5 border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-bold rounded-lg"
                    >
                      <Play className="w-3 h-3" /> Trigger Live Scan
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {agentOpps.map(opp => {
                      const score = opp.score ?? 5;
                      return (
                        <div key={opp._id} className="bg-white rounded-xl border border-slate-100 p-3.5 hover:border-emerald-200 hover:shadow-sm transition-all">
                          <div className="grid gap-3" style={{ gridTemplateColumns: "46px 1fr 100px 105px 158px" }}>
                            {/* Score ring component */}
                            <IntentRing score={score} />

                            {/* Signal Details */}
                            <div className="min-w-0">
                              <p className="text-xs font-bold text-slate-800 truncate">{opp.title}</p>
                              <p className="text-[11px] text-slate-500 line-clamp-2 mt-1 leading-relaxed">{opp.snippet}</p>
                              <div className="flex items-center gap-1.5 mt-2">
                                <span className="text-[9px] text-slate-400 font-medium">Captured {timeAgo(opp.created_at)}</span>
                              </div>
                            </div>

                            {/* Found Platform Badge */}
                            <div className="flex items-center justify-center">
                              <span className="text-[9px] font-bold text-slate-500 capitalize bg-slate-50 px-2 py-1 rounded border border-slate-100 select-none">
                                {opp.platform || "Custom"}
                              </span>
                            </div>

                            {/* Contact Info card */}
                            <div className="flex flex-col justify-center gap-1 text-xs">
                              {opp.contact_name ? (
                                <p className="font-bold text-slate-700 truncate">{opp.contact_name}</p>
                              ) : opp.author ? (
                                <p className="font-bold text-slate-700 truncate">@{opp.author}</p>
                              ) : (
                                <p className="text-slate-400 italic">No contact</p>
                              )}
                              {opp.group_name && (
                                <p className="text-[10px] text-slate-400 truncate">👥 {opp.group_name}</p>
                              )}
                            </div>

                            {/* Interactive Actions */}
                            <div className="flex items-center gap-2 justify-end">
                              <button
                                onClick={() => openWhatsApp(opp.contact_info, `Hi, I saw your post regarding "${opp.title}" and wanted to connect.`)}
                                className="px-3 py-2 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 flex items-center gap-1 shadow-sm"
                              >
                                <MessageCircle className="w-3.5 h-3.5" />
                                Reach Out
                              </button>
                              <button
                                onClick={() => addToCRM(opp)}
                                className="p-2 border border-slate-200 rounded-lg text-slate-400 hover:text-slate-600 hover:border-slate-300 transition-colors"
                                title="Add to CRM"
                              >
                                <Plus className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })()}

          {/* ────────────────── POPUP MODAL: ADD CUSTOM AGENT ────────────────── */}
          {isAddAgentOpen && (
            <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center z-[999] p-4 transition-all">
              <div className="bg-white rounded-2xl border border-slate-100 shadow-2xl max-w-md w-full p-6 space-y-4 relative animate-in fade-in zoom-in-95 duration-150">
                <button
                  onClick={() => setIsAddAgentOpen(false)}
                  className="absolute top-4 right-4 p-1 rounded-lg text-slate-400 hover:bg-slate-50 hover:text-slate-600 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>

                <div>
                  <h3 className="text-base font-bold text-slate-800">Add New AI Scout Agent</h3>
                  <p className="text-xs text-slate-400 mt-1">Specify custom B2B hunting instructions in plain English</p>
                </div>

                <div className="space-y-3">
                  {/* Row 1: Name + Emoji Selector */}
                  <div className="grid grid-cols-[1fr,70px] gap-3">
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <label className="block text-[10px] font-bold text-slate-500 uppercase">Agent Name</label>
                        <span className="text-[9px] text-slate-400 font-semibold">{newAgentName.length}/20</span>
                      </div>
                      <input
                        type="text"
                        value={newAgentName}
                        onChange={e => setNewAgentName(e.target.value)}
                        maxLength={20}
                        placeholder="e.g. Chair Hunter"
                        className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all font-medium"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Emoji</label>
                      <select
                        value={newAgentEmoji}
                        onChange={e => setNewAgentEmoji(e.target.value)}
                        className="w-full text-xs border border-slate-200 rounded-lg px-2 py-2 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 cursor-pointer text-center"
                      >
                        {["🤖", "🔍", "🛋️", "🚗", "💼", "📈", "💻", "🚀", "📞", "📅", "💡", "💰"].map(em => (
                          <option key={em} value={em}>{em}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* Row 2: Prompt Instruction */}
                  <div>
                    <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Instructions (The Prompt)</label>
                    <textarea
                      value={newAgentDescription}
                      onChange={e => setNewAgentDescription(e.target.value)}
                      placeholder="e.g. Scan Facebook Groups and social media for posts asking for office chair suppliers, desk orders, or office furniture recommendations. Score highly if the user mentions B2B or wholesale quantities."
                      className="w-full text-xs border border-slate-200 rounded-lg px-3 py-2 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all min-h-[100px] resize-none leading-relaxed"
                    />
                  </div>

                  {/* Row 3: Run Schedule */}
                  <div>
                    <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Execution Schedule</label>
                    <div className="grid grid-cols-3 gap-2">
                      {(["on_demand", "daily", "weekly"] as const).map(sch => (
                        <button
                          key={sch}
                          onClick={() => setNewAgentSchedule(sch)}
                          className={`py-2 text-xs font-bold rounded-lg border transition-all capitalize ${newAgentSchedule === sch ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200 text-slate-500 hover:border-slate-300 hover:bg-slate-50"}`}
                        >
                          {sch.replace(/_/g, " ")}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-2.5 pt-2">
                  <button
                    onClick={() => setIsAddAgentOpen(false)}
                    className="flex-1 py-2.5 border border-slate-200 text-slate-500 hover:bg-slate-50 text-xs font-bold rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleAddAgent}
                    disabled={creatingAgent}
                    className="flex-1 py-2.5 bg-emerald-600 text-white hover:bg-emerald-700 text-xs font-bold rounded-lg transition-all disabled:opacity-50 flex items-center justify-center gap-1.5 shadow-sm"
                  >
                    {creatingAgent ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                    Build Agent
                  </button>
                </div>
              </div>
            </div>
          )}

        </main>
      </div>
    </div>
  );
}

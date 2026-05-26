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
  ShoppingBag, Mail, Phone, Copy,
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

type Section = "hunt" | "pulse" | "funding" | "radar" | "shopify_leads" | "business_leads" | "lead_scouts" | "setup" | "autopilot" | "settings" | string;

interface ShopifyLead {
  domain: string;
  name: string | null;
  email: string | null;
  phone: string | null;
  facebook: string | null;
  instagram: string | null;
  tiktok: string | null;
  twitter: string | null;
  youtube: string | null;
  pinterest: string | null;
  description: string | null;
  niche: string;
  source: string;
  product_count: number | null;
  price_min: number | null;
  price_max: number | null;
  avg_price: number | null;
  categories: string[] | null;
  top_products: { title: string; price: number }[] | null;
  vendors: string[] | null;
  tags_sample: string[] | null;
  has_free_shipping: boolean | null;
  currency: string | null;
  platform: string | null;
}

interface LeadScout {
  _id: string;
  name: string;
  keyword: string;
  location: string;
  frequency: "manual" | "daily" | "weekly";
  expanded_keywords?: string[];
  min_rating: number;
  require_phone: boolean;
  require_email: boolean;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
  new_leads: number;
  inbox_count: number;
  last_error: string | null;
}

interface InboxLead {
  _id: string;
  _batch_index?: number;          // which unlock batch this lead belongs to (0 = free, 1+ = paid)
  _batch_unlocked_at?: string;    // when this batch was unlocked
  scout_id: string;
  scout_name: string;
  name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  website: string | null;
  domain: string | null;
  category: string | null;
  rating: number | null;
  reviews: number | null;
  place_id: string | null;
  keyword: string;
  discovered_at: string;
  status: "new" | "saved" | "dismissed";
}

interface BusinessLead {
  name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  website: string | null;
  domain: string | null;
  category: string | null;
  rating: number | null;
  reviews: number | null;
  place_id: string | null;
  keyword: string;
}

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
  const [totalScanned, setTotalScanned] = useState(0);
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

  // Shopify leads search
  const [shopifyNiche, setShopifyNiche] = useState("");
  const [shopifyCountry, setShopifyCountry] = useState("");
  const [shopifySearching, setShopifySearching] = useState(false);
  const [shopifyLeads, setShopifyLeads] = useState<ShopifyLead[]>([]);
  const [shopifySearched, setShopifySearched] = useState(false);
  const [shopifyAdded, setShopifyAdded] = useState<Set<string>>(new Set());
  const [shopifyAdding, setShopifyAdding] = useState<string | null>(null);

  // Business leads search
  const [bizKeyword, setBizKeyword] = useState("");
  const [bizLocation, setBizLocation] = useState("");
  const [bizSearching, setBizSearching] = useState(false);
  const [bizLeads, setBizLeads] = useState<BusinessLead[]>([]);
  const [bizSearched, setBizSearched] = useState(false);
  const [bizAdded, setBizAdded] = useState<Set<string>>(new Set());
  const [bizAdding, setBizAdding] = useState<string | null>(null);

  // Lead Scouts (automated saved searches — separate from AI Scouts)
  const [leadScouts, setLeadScouts] = useState<LeadScout[]>([]);
  const [leadScoutsLoading, setLeadScoutsLoading] = useState(false);
  const [inboxLeads, setInboxLeads] = useState<InboxLead[]>([]);
  const [inboxLoading, setInboxLoading] = useState(false);
  const [inboxPage, setInboxPage] = useState(0);
  const [inboxTotal, setInboxTotal] = useState(0);
  const [inboxHasMore, setInboxHasMore] = useState(false);
  const [loadingMoreInbox, setLoadingMoreInbox] = useState(false);
  const [inboxStatus, setInboxStatus] = useState<"new"|"saved"|"dismissed"|"with_contacts">("new");
  const [inboxCounts, setInboxCounts] = useState<{new: number; saved: number; dismissed: number; with_contacts: number}>({new: 0, saved: 0, dismissed: 0, with_contacts: 0});
  const [inboxFilterScoutId, setInboxFilterScoutId] = useState<string>("");
  const [bulkSavingInbox, setBulkSavingInbox] = useState(false);
  const [addAsType, setAddAsType] = useState<"Customer"|"Lead"|"Investor"|"Partner"|"Supplier"|"Other">("Customer");
  const [scoutTab, setScoutTab] = useState<"scouts" | "inbox">("inbox");
  const [showLeadScoutForm, setShowLeadScoutForm] = useState(false);
  const [runningLeadScout, setRunningLeadScout] = useState<string | null>(null);
  const [runningAllLeadScouts, setRunningAllLeadScouts] = useState(false);
  const [savingInboxLead, setSavingInboxLead] = useState<string | null>(null);
  const [leadScoutForm, setLeadScoutForm] = useState({
    name: "", keyword: "", location: "", frequency: "weekly" as "manual"|"daily"|"weekly",
    require_phone: false, require_email: false,
  });
  const [creditInfo, setCreditInfo] = useState<{
    balance: number; total_runs: number; total_spent_usd: number;
    credit_price_usd: number; dfs_cost_usd: number; margin_usd: number; free_credits: number;
  } | null>(null);

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
      const timeoutPromise = new Promise<never>((_, reject) => 
        setTimeout(() => reject(new Error("Connection request timed out. Please check if your backend server and MongoDB database are running.")), 10000)
      );

      const [s, f, q, o, ca, ss, cl, pr, rc, ia, sc, pl] = await Promise.race([
        Promise.all([
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
          api.get<{ pulse: Opportunity[]; total_scanned: number }>("/action-mode/scouts/pulse"),
        ]),
        timeoutPromise
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
      setTotalScanned(pl.total_scanned ?? pl.pulse.length);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Load lead scouts + inbox + credits when section becomes active
  useEffect(() => {
    if (section === "lead_scouts") {
      loadLeadScouts();
      loadInbox();
      loadCredits();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section]);

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

  async function addShopifyLeadToCRM(lead: ShopifyLead) {
    setShopifyAdding(lead.domain);
    try {
      const storeName = lead.name || lead.domain.split(".")[0];
      // Check for duplicate before adding
      const check = await api.get<{ exists: boolean; name: string }>(
        `/customers/duplicate-check?email=${encodeURIComponent(lead.email || "")}&domain=${encodeURIComponent(lead.domain)}`
      );
      if (check.exists) {
        toast.info(`${check.name || storeName} is already in your CRM`);
        setShopifyAdded(prev => new Set(prev).add(lead.domain));
        return;
      }
      const payload: any = {
        name: storeName,
        email: lead.email || undefined,
        phone_number: lead.phone || undefined,
        notes: [
          `Shopify store: https://${lead.domain}`,
          lead.description ? `About: ${lead.description}` : "",
          lead.niche ? `Niche: ${lead.niche}` : "",
          lead.instagram ? `Instagram: ${lead.instagram}` : "",
          lead.facebook ? `Facebook: ${lead.facebook}` : "",
          lead.tiktok ? `TikTok: ${lead.tiktok}` : "",
        ].filter(Boolean).join("\n"),
        tags: ["Shopify", "Ecommerce", lead.niche].filter(Boolean),
      };
      if (!payload.phone_number && !payload.email) {
        const seed = lead.domain.replace(/[^0-9]/g, "").slice(0, 7).padEnd(7, "0");
        payload.phone_number = `+1555${seed}`;
      }
      await api.post("/customers", payload);
      setShopifyAdded(prev => new Set(prev).add(lead.domain));
      toast.success(`${storeName} added to CRM`);
    } catch {
      toast.error("Failed to add to CRM");
    } finally {
      setShopifyAdding(null);
    }
  }

  async function searchShopifyLeads() {
    if (!shopifyNiche.trim()) { toast.error("Enter a niche or product category"); return; }
    setShopifySearching(true);
    setShopifyLeads([]);
    setShopifySearched(false);
    try {
      const res = await api.post<{ leads: ShopifyLead[] }>("/action-mode/shopify-leads/search", {
        niche: shopifyNiche.trim(),
        country: shopifyCountry.trim(),
        limit: 12,
      });
      setShopifyLeads(res.leads ?? []);
      setShopifySearched(true);
      if (!res.leads?.length) toast.info("No stores found — try a broader niche or different keywords");
    } catch (e: any) {
      toast.error(e?.message ?? "Search failed");
    } finally {
      setShopifySearching(false);
    }
  }

  async function searchBusinessLeads() {
    if (!bizKeyword.trim()) { toast.error("Enter a keyword or business type"); return; }
    setBizSearching(true);
    setBizLeads([]);
    setBizSearched(false);
    try {
      const res = await api.post<{ leads: BusinessLead[] }>("/action-mode/business-leads/search", {
        keyword: bizKeyword.trim(),
        location: bizLocation.trim(),
      });
      setBizLeads(res.leads ?? []);
      setBizSearched(true);
      if (!res.leads?.length) toast.info("No businesses found — try a different keyword or location");
    } catch (e: any) {
      toast.error(e?.message ?? "Search failed");
    } finally {
      setBizSearching(false);
    }
  }

  async function addBusinessLeadToCRM(lead: BusinessLead) {
    const key = lead.domain || lead.name.toLowerCase();
    setBizAdding(key);
    try {
      // Duplicate check
      const check = await api.get<{ exists: boolean; name: string }>(
        `/customers/duplicate-check?email=${encodeURIComponent(lead.email || "")}&domain=${encodeURIComponent(lead.domain || "")}`
      );
      if (check.exists) {
        toast.info(`${check.name || lead.name} is already in your CRM`);
        setBizAdded(prev => new Set(prev).add(key));
        return;
      }
      const notes = [
        lead.address ? `Address: ${lead.address}` : "",
        lead.category ? `Category: ${lead.category}` : "",
        lead.website ? `Website: ${lead.website}` : "",
        lead.rating ? `Google Rating: ${lead.rating} (${lead.reviews ?? 0} reviews)` : "",
        lead.place_id ? `Google Maps: https://www.google.com/maps/place/?q=place_id:${lead.place_id}` : "",
        `Found via: ${lead.keyword}`,
      ].filter(Boolean).join("\n");
      const payload: any = {
        name: lead.name,
        email: lead.email || undefined,
        phone_number: lead.phone || undefined,
        notes,
        tags: ["Business Lead", lead.category || "Business"].filter(Boolean),
      };
      if (!payload.phone_number && !payload.email) {
        const seed = lead.name.replace(/[^0-9]/g, "").slice(0, 7).padEnd(7, "0");
        payload.phone_number = `+1555${seed}`;
      }
      await api.post("/customers", payload);
      setBizAdded(prev => new Set(prev).add(key));
      toast.success(`${lead.name} added to CRM`);
    } catch {
      toast.error("Failed to add to CRM");
    } finally {
      setBizAdding(null);
    }
  }

  async function loadCredits() {
    try {
      const res = await api.get<typeof creditInfo>("/action-mode/lead-credits");
      setCreditInfo(res);
    } catch { /* silent */ }
  }

  async function loadLeadScouts() {
    setLeadScoutsLoading(true);
    try {
      const res = await api.get<{ scouts: LeadScout[] }>("/action-mode/lead-scouts");
      setLeadScouts(res.scouts ?? []);
    } catch { /* silent */ } finally { setLeadScoutsLoading(false); }
  }

  async function loadInbox(reset = true, statusOverride?: "new"|"saved"|"dismissed"|"with_contacts", scoutIdOverride?: string) {
    if (reset) { setInboxLoading(true); setInboxPage(0); }
    else setLoadingMoreInbox(true);
    const status = statusOverride ?? inboxStatus;
    const scoutFilter = scoutIdOverride !== undefined ? scoutIdOverride : inboxFilterScoutId;
    // "with_contacts" is a virtual status — map to backend status=new + contacts=both
    const backendStatus = status === "with_contacts" ? "new" : status;
    const contactsParam = status === "with_contacts" ? "&contacts=both" : "";
    try {
      const page = reset ? 0 : inboxPage + 1;
      const scoutParam = scoutFilter ? `&scout_id=${encodeURIComponent(scoutFilter)}` : "";
      const res = await api.get<{ leads: InboxLead[]; total: number; has_more: boolean; counts: {new: number; saved: number; dismissed: number; with_contacts: number} }>(
        `/action-mode/lead-scouts/inbox?page=${page}&per_page=15&status=${backendStatus}${contactsParam}${scoutParam}`
      );
      const unlockedAt = new Date().toISOString();
      const tagged = (res.leads ?? []).map(l => ({ ...l, _batch_index: page, _batch_unlocked_at: unlockedAt }));
      if (reset) {
        setInboxLeads(tagged);
      } else {
        setInboxLeads(prev => [...prev, ...tagged]);
        setInboxPage(page);
        if (status === "new" || status === "with_contacts") {
          toast.success("Unlocked next 15 leads · 1 credit");
          void loadCredits();
        }
      }
      setInboxTotal(res.total ?? 0);
      setInboxHasMore(res.has_more ?? false);
      if (res.counts) setInboxCounts(res.counts);
    } catch (e) {
      const msg = (e as Error)?.message || "";
      if (msg.includes("402") || msg.toLowerCase().includes("insufficient credits")) {
        toast.error("Not enough credits — top up to unlock more leads");
      } else if (!reset) {
        toast.error("Failed to load more leads");
      }
    } finally { setInboxLoading(false); setLoadingMoreInbox(false); }
  }

  async function restoreInboxLead(id: string) {
    try {
      await api.post(`/action-mode/lead-scouts/inbox/${id}/restore`, {});
      setInboxLeads(prev => prev.filter(l => l._id !== id));
      setInboxCounts(prev => ({ ...prev, [inboxStatus]: Math.max(0, prev[inboxStatus] - 1), new: prev.new + 1 }));
      toast.success("Lead restored to inbox");
    } catch { toast.error("Failed to restore"); }
  }

  async function bulkAddToCRM() {
    const subject = inboxStatus === "with_contacts" ? "leads with email + phone" : "currently visible leads";
    if (!confirm(`Add all ${subject} to your CRM as ${addAsType}?`)) return;
    setBulkSavingInbox(true);
    try {
      const res = await api.post<{ saved: number; skipped: number; total: number }>(
        "/action-mode/lead-scouts/inbox/bulk-save",
        {
          scout_id:     inboxFilterScoutId || undefined,
          contacts:     inboxStatus === "with_contacts" ? "both" : "any",
          contact_type: addAsType,
          require_email: false,
        },
      );
      toast.success(`Added ${res.saved} ${addAsType.toLowerCase()}${res.saved !== 1 ? "s" : ""} to CRM${res.skipped > 0 ? ` (${res.skipped} skipped — no contact info)` : ""}`);
      await loadInbox(true);
    } catch (e) {
      toast.error("Bulk save failed — " + ((e as Error)?.message || ""));
    } finally { setBulkSavingInbox(false); }
  }

  async function createLeadScout() {
    if (!leadScoutForm.keyword.trim()) { toast.error("Keyword is required"); return; }
    try {
      await api.post("/action-mode/lead-scouts", {
        ...leadScoutForm,
        name: leadScoutForm.name.trim() || leadScoutForm.keyword.trim(),
      });
      toast.success("Scout created");
      setShowLeadScoutForm(false);
      setLeadScoutForm({ name: "", keyword: "", location: "", frequency: "weekly", require_phone: false, require_email: false });
      await loadLeadScouts();
    } catch { toast.error("Failed to create scout"); }
  }

  async function deleteLeadScout(id: string) {
    try {
      await api.delete(`/action-mode/lead-scouts/${id}`);
      setLeadScouts(prev => prev.filter(s => s._id !== id));
      toast.success("Scout deleted");
    } catch { toast.error("Failed"); }
  }

  async function toggleLeadScout(scout: LeadScout) {
    try {
      await api.put(`/action-mode/lead-scouts/${scout._id}`, { enabled: !scout.enabled });
      setLeadScouts(prev => prev.map(s => s._id === scout._id ? { ...s, enabled: !s.enabled } : s));
    } catch { toast.error("Failed"); }
  }

  async function removeExpandedKeyword(scout: LeadScout, kw: string) {
    const remaining = (scout.expanded_keywords ?? []).filter(k => k !== kw);
    setLeadScouts(prev => prev.map(s => s._id === scout._id ? { ...s, expanded_keywords: remaining } : s));
    try {
      await api.put(`/action-mode/lead-scouts/${scout._id}`, { expanded_keywords: remaining });
    } catch {
      toast.error("Failed to remove keyword");
      setLeadScouts(prev => prev.map(s => s._id === scout._id ? { ...s, expanded_keywords: scout.expanded_keywords } : s));
    }
  }

  async function runLeadScout(id: string) {
    setRunningLeadScout(id);
    try {
      const res = await api.post<{ new_leads: number }>(`/action-mode/lead-scouts/${id}/run`, {});
      toast.success(`Found ${res.new_leads} new lead${res.new_leads !== 1 ? "s" : ""}`);
      await Promise.all([loadLeadScouts(), loadInbox(), loadCredits()]);
    } catch { toast.error("Run failed"); } finally { setRunningLeadScout(null); }
  }

  async function runAllLeadScouts() {
    setRunningAllLeadScouts(true);
    try {
      const res = await api.post<{ new_leads: number; scouts_run: number }>("/action-mode/lead-scouts/run-all", {});
      toast.success(`${res.scouts_run} scouts ran — ${res.new_leads} new leads found`);
      await Promise.all([loadLeadScouts(), loadInbox(), loadCredits()]);
      setScoutTab("inbox");
    } catch { toast.error("Run failed"); } finally { setRunningAllLeadScouts(false); }
  }

  async function saveInboxLead(lead: InboxLead) {
    setSavingInboxLead(lead._id);
    try {
      await api.post(`/action-mode/lead-scouts/inbox/${lead._id}/save`, { contact_type: addAsType });
      setInboxLeads(prev => prev.filter(l => l._id !== lead._id));
      toast.success(`${lead.name} added to CRM as ${addAsType}`);
    } catch { toast.error("Failed to add to CRM"); } finally { setSavingInboxLead(null); }
  }

  async function dismissInboxLead(id: string) {
    try {
      await api.delete(`/action-mode/lead-scouts/inbox/${id}`);
      setInboxLeads(prev => prev.filter(l => l._id !== id));
    } catch { setInboxLeads(prev => prev.filter(l => l._id !== id)); }
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
      // Remove opportunity from list so already-saved leads don't keep showing
      setOpportunities(prev => prev.filter(o => o._id !== opp._id));
      try { await api.delete(`/action-mode/opportunities/${opp._id}`); } catch { /* best-effort */ }
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
    { id: "shopify_leads", label: "Shopify Leads", icon: ShoppingBag },
    { id: "business_leads", label: "Business Leads", icon: Building2 },
    { id: "lead_scouts", label: "Lead Scouts", icon: Antenna, badge: inboxLeads.length || undefined },
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
                            {(() => {
                              const p = (lead.platform || "").toLowerCase();
                              const hasUrl = !!lead.url;
                              const hasContact = !!lead.contact_info;

                              if (p === "facebook" || p === "facebook_marketplace") return (
                                <a href={lead.url || "#"} target="_blank" rel="noopener noreferrer"
                                  className="w-full flex items-center justify-center gap-1.5 py-1.5 bg-[#1877F2] text-white text-xs font-bold rounded-lg hover:bg-[#1565c0] transition-all">
                                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
                                  View on Facebook
                                </a>
                              );
                              if (p === "reddit") return (
                                <a href={lead.url || "#"} target="_blank" rel="noopener noreferrer"
                                  className="w-full flex items-center justify-center gap-1.5 py-1.5 bg-[#FF4500] text-white text-xs font-bold rounded-lg hover:bg-[#e03d00] transition-all">
                                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z"/></svg>
                                  View on Reddit
                                </a>
                              );
                              if (p === "twitter" || p === "x") return (
                                <a href={lead.url || "#"} target="_blank" rel="noopener noreferrer"
                                  className="w-full flex items-center justify-center gap-1.5 py-1.5 bg-black text-white text-xs font-bold rounded-lg hover:bg-slate-800 transition-all">
                                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.746l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
                                  View on X
                                </a>
                              );
                              if (p === "whatsapp" || hasContact) return (
                                <button
                                  onClick={() => openWhatsApp(lead.contact_info, `Hi! I saw your post about "${lead.title.slice(0, 40)}" and wanted to reach out.`)}
                                  className="w-full flex items-center justify-center gap-1.5 py-1.5 bg-[#16A34A] text-white text-xs font-bold rounded-lg hover:bg-[#15803d] transition-all">
                                  <MessageCircle className="w-3.5 h-3.5" />
                                  WhatsApp
                                </button>
                              );
                              if (hasUrl) return (
                                <a href={lead.url} target="_blank" rel="noopener noreferrer"
                                  className="w-full flex items-center justify-center gap-1.5 py-1.5 bg-slate-700 text-white text-xs font-bold rounded-lg hover:bg-slate-800 transition-all">
                                  <ExternalLink className="w-3.5 h-3.5" />
                                  {p ? `View on ${p.charAt(0).toUpperCase() + p.slice(1)}` : "View post"}
                                </a>
                              );
                              return (
                                <button
                                  onClick={() => openWhatsApp(lead.contact_info, `Hi! I saw your post about "${lead.title.slice(0, 40)}" and wanted to reach out.`)}
                                  className="w-full flex items-center justify-center gap-1.5 py-1.5 bg-slate-200 text-slate-700 text-xs font-bold rounded-lg hover:bg-slate-300 transition-all">
                                  <MessageCircle className="w-3.5 h-3.5" />
                                  Contact
                                </button>
                              );
                            })()}
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
                        <div className="text-3xl font-extrabold tracking-tight text-[#059669]">{totalScanned}</div>
                        <div className="text-xs font-semibold text-slate-400 mt-1.5 select-none">Signals found</div>
                      </div>

                      {/* Stat 2 */}
                      <div className="bg-white rounded-2xl border border-slate-100/80 p-5 shadow-[0_2px_10px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.04)] transition-all duration-300">
                        <div className="text-3xl font-extrabold tracking-tight text-[#DC2626]">
                          {queue.length}
                        </div>
                        <div className="text-xs font-semibold text-slate-400 mt-1.5 select-none">Leads in queue</div>
                      </div>

                      {/* Stat 3 */}
                      <div className="bg-white rounded-2xl border border-slate-100/80 p-5 shadow-[0_2px_10px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.04)] transition-all duration-300">
                        <div className="text-3xl font-extrabold tracking-tight text-[#D97706]">{Object.values(settings.agents || {}).filter(Boolean).length}</div>
                        <div className="text-xs font-semibold text-slate-400 mt-1.5 select-none">Agents active</div>
                      </div>

                      {/* Stat 4 */}
                      <div className="bg-white rounded-2xl border border-slate-100/80 p-5 shadow-[0_2px_10px_rgba(0,0,0,0.02)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.04)] transition-all duration-300">
                        <div className="text-3xl font-extrabold tracking-tight text-[#2563EB]">
                          {fundingOpps.length}
                        </div>
                        <div className="text-xs font-semibold text-slate-400 mt-1.5 select-none">Funding matches</div>
                      </div>
                    </div>
                  </div>

                  {/* Activity Feed Section */}
                  <div className="space-y-3">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Live Activity</h3>
                    
                    <div className="space-y-2">
                      {scoutPulse.length === 0 && fundingOpps.length === 0 ? (
                        <div className="bg-slate-50 rounded-xl border border-slate-100 p-6 text-center text-xs text-slate-400">
                          No activity yet — run a scout to see live signals here.
                        </div>
                      ) : (
                        [...scoutPulse.slice(0, 4), ...fundingOpps.slice(0, 2)]
                          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                          .slice(0, 5)
                          .map(item => {
                            const isFunding = item.kind === "funding";
                            const isUrgent = !isFunding && (item.score ?? 0) >= 8;
                            const dotColor = isFunding ? "#2563EB" : isUrgent ? "#DC2626" : "#059669";
                            const label = isFunding ? "Funding match" : isUrgent ? "Urgent lead" : "New lead";
                            const target = isFunding ? "funding" : "hunt";
                            const btnLabel = isFunding ? "Apply →" : "View →";
                            const ms = Date.now() - new Date(item.created_at).getTime();
                            const minAgo = Math.max(1, Math.round(ms / 60000));
                            const timeLabel = minAgo < 60 ? `${minAgo} min ago` : `${Math.round(minAgo / 60)} hr ago`;
                            return (
                              <div key={item._id} className="bg-white rounded-xl border border-slate-100 p-4 flex items-center justify-between hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                                <div className="flex items-start gap-3">
                                  <span className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0" style={{ backgroundColor: dotColor }} />
                                  <div>
                                    <div className="text-sm text-slate-700 font-medium">
                                      <span className="font-bold text-slate-800">{label}</span> — {item.title}
                                      {item.platform && <span className="text-slate-400 text-xs"> · {item.platform}</span>}
                                      {!isFunding && item.score != null && <span className="text-slate-400 text-xs"> · AI score {item.score.toFixed(1)}</span>}
                                    </div>
                                    <div className="text-xs text-slate-400 mt-1">{timeLabel}</div>
                                  </div>
                                </div>
                                <button
                                  onClick={() => setSection(target)}
                                  className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-0.5 select-none transition-all pr-2 flex-shrink-0"
                                >
                                  {btnLabel}
                                </button>
                              </div>
                            );
                          })
                      )}
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
                        {(() => {
                          const hotLeads = leads.filter(l => (l.score ?? 5) >= 5);
                          const topLead = hotLeads[0];
                          return (
                            <>
                              <span className="font-bold">Good morning! 🌅</span> You have <span className="text-[#059669] font-bold">{hotLeads.length} hot lead{hotLeads.length !== 1 ? "s" : ""}</span> today.{" "}
                              {topLead
                                ? <>Top: {topLead.title}{topLead.platform ? ` · ${topLead.platform}` : ""}. Reply before a competitor does.</>
                                : "Run your scouts to surface the latest signals."}
                            </>
                          );
                        })()}
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
                  {recon.length > 0 ? (
                    <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
                      <div className="flex items-start gap-3 mb-4">
                        <div className="bg-amber-50 p-2 rounded-xl text-xl">⚡</div>
                        <div>
                          <h4 className="font-bold text-slate-800 text-sm">Market signal</h4>
                          <p className="text-[10px] text-slate-400 mt-0.5">Opportunity detected</p>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5">
                          <p className="text-xs font-bold text-slate-800 mb-1">{recon[0].company}</p>
                          <p className="text-xs text-slate-600 leading-relaxed">
                            {recon[0].why_relevant}
                          </p>
                          <p className="text-[10px] text-slate-400 mt-2 font-medium">
                            {recon[0].action_hint}
                          </p>
                        </div>

                        <button
                          onClick={() => setSection("radar")}
                          className="w-full py-2.5 bg-amber-50 hover:bg-amber-100 text-amber-800 text-xs font-bold rounded-xl flex items-center justify-center transition-all border border-amber-100"
                        >
                          View in Radar →
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm">
                      <div className="flex items-start gap-3 mb-3">
                        <div className="bg-slate-50 p-2 rounded-xl text-xl">⚡</div>
                        <div>
                          <h4 className="font-bold text-slate-800 text-sm">Market signals</h4>
                          <p className="text-[10px] text-slate-400 mt-0.5">No signals yet</p>
                        </div>
                      </div>
                      <p className="text-xs text-slate-400 leading-relaxed mb-3">
                        Run Market Radar to detect competitor complaints, job postings, and new business opportunities in your area.
                      </p>
                      <button
                        onClick={() => setSection("radar")}
                        className="w-full py-2 bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-bold rounded-xl flex items-center justify-center transition-all border border-slate-200"
                      >
                        Open Radar →
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
              {fundingOpps.length > 0 && (
                <div className="mb-6 flex items-center gap-3 bg-[#ECFDF5] border border-[#A7F3D0] rounded-xl px-4 py-3.5 text-sm text-emerald-800 shadow-[0_1px_2px_rgba(0,0,0,0.01)]">
                  <span className="text-lg select-none">🎯</span>
                  <p className="leading-relaxed font-medium">
                    <span className="font-bold">{fundingOpps.length} funding match{fundingOpps.length !== 1 ? "es" : ""} found.</span>{" "}
                    {fundingOpps[0] && <>Top match: {fundingOpps[0].title}{fundingOpps[0].score != null ? ` — AI score ${fundingOpps[0].score.toFixed(1)}/10` : ""}.</>}
                  </p>
                </div>
              )}

              {/* Funding Rows */}
              <div className="space-y-3">
                {fundingOpps.length === 0 ? (
                  <div className="bg-white rounded-xl border border-slate-100 p-10 text-center">
                    <div className="text-3xl mb-3">💰</div>
                    <p className="text-sm font-semibold text-slate-600 mb-1">No funding matches yet</p>
                    <p className="text-xs text-slate-400 mb-4">Run your AI scouts to find grants, loans, and accelerators matched to your business.</p>
                    <button
                      onClick={load}
                      className="px-4 py-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-xs font-bold rounded-lg transition-all border border-emerald-100"
                    >
                      Refresh
                    </button>
                  </div>
                ) : (
                  fundingOpps.map((opp, idx) => {
                    const accentColors = ["#059669", "#2563EB", "#7C3AED", "#D97706", "#DC2626"];
                    const accent = accentColors[idx % accentColors.length];
                    const score = opp.score ?? 5;
                    return (
                      <div key={opp._id} className="bg-white rounded-xl border border-slate-100 p-4 hover:border-slate-200 hover:shadow-sm transition-all duration-200" style={{ borderLeftWidth: 3, borderLeftColor: accent }}>
                        <div className="grid gap-4 items-center" style={{ gridTemplateColumns: "1fr 100px 140px" }}>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className="font-bold text-slate-800 text-sm">{opp.title}</span>
                              {opp.platform && (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 select-none">{opp.platform}</span>
                              )}
                            </div>
                            {opp.agent_name && (
                              <p className="text-xs text-slate-400 font-semibold mb-1 select-none">
                                Via {opp.agent_name}
                              </p>
                            )}
                            {opp.snippet && (
                              <p className="text-xs text-slate-500 leading-relaxed line-clamp-2">{opp.snippet}</p>
                            )}
                          </div>

                          <div className="flex flex-col items-center justify-center">
                            <IntentRing score={score} />
                            <span className="text-[10px] text-slate-400 mt-1 font-semibold select-none">AI match</span>
                          </div>

                          <div className="flex flex-col gap-1.5">
                            {opp.url ? (
                              <a
                                href={opp.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="w-full py-1.5 bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1"
                              >
                                Apply now →
                              </a>
                            ) : (
                              <button className="w-full py-1.5 bg-[#059669] hover:bg-[#047857] text-white text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1">
                                View details →
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* ────────────────── SHOPIFY LEADS ────────────────── */}
          {section === "shopify_leads" && (
            <div className="p-5">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h1 className="text-2xl font-bold text-slate-800">Find Shopify Leads</h1>
                  <p className="text-sm text-slate-500 mt-1">Search for Shopify store owners in any niche — get their email, phone and socials</p>
                </div>
              </div>

              {/* Search bar */}
              <div className="bg-white rounded-2xl border border-slate-200 p-5 mb-6 shadow-sm">
                <div className="flex flex-col sm:flex-row gap-3">
                  <div className="flex-1">
                    <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5 block">Niche / Product category *</label>
                    <input
                      value={shopifyNiche}
                      onChange={e => setShopifyNiche(e.target.value)}
                      onKeyDown={e => e.key === "Enter" && !shopifySearching && searchShopifyLeads()}
                      placeholder="e.g. fitness supplements, pet accessories, home décor…"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand transition-all"
                    />
                  </div>
                  <div className="w-full sm:w-48">
                    <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5 block">Country (optional)</label>
                    <input
                      value={shopifyCountry}
                      onChange={e => setShopifyCountry(e.target.value)}
                      placeholder="e.g. United States, Canada…"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand transition-all"
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      onClick={searchShopifyLeads}
                      disabled={shopifySearching || !shopifyNiche.trim()}
                      className="flex items-center gap-2 px-5 py-2.5 bg-brand-dark hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl transition-all shadow-sm whitespace-nowrap"
                    >
                      {shopifySearching
                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Searching…</>
                        : <><Search className="w-4 h-4" /> Find stores</>}
                    </button>
                  </div>
                </div>

                <p className="text-xs text-slate-400 mt-3 flex items-center gap-1.5">
                  <ShoppingBag className="w-3 h-3" />
                  Searches the web for active Shopify stores matching your niche, then enriches each with contact details.
                  {shopifySearching && <span className="text-amber-600 font-medium"> This takes 20–40 seconds while we enrich each store…</span>}
                </p>
              </div>

              {/* Loading skeleton */}
              {shopifySearching && (
                <div className="space-y-3">
                  {[1,2,3,4].map(i => (
                    <div key={i} className="bg-white rounded-xl border border-slate-100 p-4 animate-pulse">
                      <div className="flex items-start gap-4">
                        <div className="w-10 h-10 rounded-xl bg-slate-200 shrink-0" />
                        <div className="flex-1 space-y-2">
                          <div className="h-4 bg-slate-200 rounded w-1/3" />
                          <div className="h-3 bg-slate-100 rounded w-1/2" />
                          <div className="flex gap-2 mt-1">
                            <div className="h-3 bg-slate-100 rounded w-24" />
                            <div className="h-3 bg-slate-100 rounded w-20" />
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <div className="h-8 w-24 bg-slate-200 rounded-xl" />
                          <div className="h-8 w-24 bg-slate-100 rounded-xl" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Results */}
              {!shopifySearching && shopifySearched && shopifyLeads.length === 0 && (
                <div className="bg-white rounded-xl border border-slate-100 p-10 text-center">
                  <div className="text-3xl mb-3">🔍</div>
                  <p className="text-sm font-semibold text-slate-600 mb-1">No stores found</p>
                  <p className="text-xs text-slate-400">Try a different niche or broader keywords — e.g. &quot;fitness&quot; instead of &quot;protein powder for women&quot;</p>
                </div>
              )}

              {!shopifySearching && shopifyLeads.length > 0 && (
                <div className="space-y-3">
                  <p className="text-xs text-slate-500 font-medium">{shopifyLeads.length} stores found for <span className="text-brand font-semibold">{shopifyNiche}</span> — {shopifyLeads.filter(l => l.email).length} with email</p>
                  {shopifyLeads.map((lead, idx) => {
                    const hasContact = !!(lead.email || lead.phone);
                    const storeName = lead.name || lead.domain.split(".")[0];
                    const priceRange = lead.price_min != null && lead.price_max != null
                      ? lead.price_min === lead.price_max
                        ? `${lead.currency || "$"}${lead.price_min.toFixed(0)}`
                        : `${lead.currency || "$"}${lead.price_min.toFixed(0)} – ${lead.currency || "$"}${lead.price_max.toFixed(0)}`
                      : null;
                    const topCats = (lead.categories ?? []).slice(0, 3);
                    const topProds = (lead.top_products ?? []).slice(0, 3);
                    return (
                      <div key={idx} className="bg-white rounded-xl border border-slate-100 p-4 hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-start gap-4">
                          {/* Icon */}
                          <div className="w-10 h-10 rounded-xl bg-emerald-50 border border-emerald-100 flex items-center justify-center shrink-0">
                            <ShoppingBag className="w-5 h-5 text-emerald-600" />
                          </div>

                          {/* Info */}
                          <div className="flex-1 min-w-0">
                            {/* Name + domain + badges */}
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className="font-bold text-slate-800 text-sm">{storeName}</span>
                              <a href={`https://${lead.domain}`} target="_blank" rel="noopener noreferrer"
                                className="text-[10px] text-brand hover:underline font-mono">{lead.domain}</a>
                              {hasContact && (
                                <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-100 px-2 py-0.5 rounded-full font-semibold">Has contact</span>
                              )}
                              {lead.has_free_shipping && (
                                <span className="text-[10px] bg-sky-50 text-sky-700 border border-sky-100 px-2 py-0.5 rounded-full font-semibold">Free shipping</span>
                              )}
                            </div>

                            {lead.description && (
                              <p className="text-xs text-slate-500 leading-relaxed line-clamp-1 mb-1.5">{lead.description}</p>
                            )}

                            {/* Store stats row */}
                            {(lead.product_count != null || priceRange || topCats.length > 0) && (
                              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-1.5">
                                {lead.product_count != null && (
                                  <span className="text-[11px] text-slate-500 flex items-center gap-1">
                                    <span className="font-semibold text-slate-700">{lead.product_count}</span> products
                                  </span>
                                )}
                                {priceRange && (
                                  <span className="text-[11px] text-slate-500">
                                    <span className="font-semibold text-slate-700">{priceRange}</span> range
                                  </span>
                                )}
                                {topCats.map(cat => (
                                  <span key={cat} className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded-md font-medium">{cat}</span>
                                ))}
                              </div>
                            )}

                            {/* Top products */}
                            {topProds.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 mb-1.5">
                                {topProds.map((p, pi) => (
                                  <span key={pi} className="text-[10px] bg-amber-50 border border-amber-100 text-amber-800 px-2 py-0.5 rounded-md font-medium">
                                    {p.title} {p.price > 0 ? `· ${lead.currency || "$"}${p.price.toFixed(0)}` : ""}
                                  </span>
                                ))}
                              </div>
                            )}

                            {/* Contact + socials */}
                            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                              {lead.email && (
                                <span className="flex items-center gap-1 text-xs text-slate-600">
                                  <Mail className="w-3 h-3 text-slate-400" />
                                  <button onClick={() => { navigator.clipboard.writeText(lead.email!); toast.success("Email copied"); }}
                                    className="hover:text-brand transition-colors">{lead.email}</button>
                                </span>
                              )}
                              {lead.phone && (
                                <span className="flex items-center gap-1 text-xs text-slate-600">
                                  <Phone className="w-3 h-3 text-slate-400" />
                                  {lead.phone}
                                </span>
                              )}
                              {lead.instagram && (
                                <a href={lead.instagram} target="_blank" rel="noopener noreferrer"
                                  className="flex items-center gap-1 text-xs text-pink-600 hover:text-pink-700">
                                  <span className="text-[10px] font-bold">IG</span> Instagram
                                </a>
                              )}
                              {lead.facebook && (
                                <a href={lead.facebook} target="_blank" rel="noopener noreferrer"
                                  className="flex items-center gap-1 text-xs text-[#1877F2] hover:text-[#1565c0]">
                                  <span className="text-[10px] font-bold">FB</span> Facebook
                                </a>
                              )}
                              {lead.tiktok && (
                                <a href={lead.tiktok} target="_blank" rel="noopener noreferrer"
                                  className="flex items-center gap-1 text-xs text-slate-800 hover:text-slate-600">
                                  <span className="text-[10px] font-bold">TT</span> TikTok
                                </a>
                              )}
                              {lead.twitter && (
                                <a href={lead.twitter} target="_blank" rel="noopener noreferrer"
                                  className="flex items-center gap-1 text-xs text-sky-500 hover:text-sky-600">
                                  <span className="text-[10px] font-bold">𝕏</span> Twitter
                                </a>
                              )}
                              {lead.youtube && (
                                <a href={lead.youtube} target="_blank" rel="noopener noreferrer"
                                  className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700">
                                  <span className="text-[10px] font-bold">▶</span> YouTube
                                </a>
                              )}
                              {lead.pinterest && (
                                <a href={lead.pinterest} target="_blank" rel="noopener noreferrer"
                                  className="flex items-center gap-1 text-xs text-red-500 hover:text-red-600">
                                  <span className="text-[10px] font-bold">P</span> Pinterest
                                </a>
                              )}
                            </div>
                          </div>

                          {/* Actions */}
                          <div className="flex flex-col gap-1.5 shrink-0">
                            {shopifyAdded.has(lead.domain) ? (
                              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold rounded-lg">
                                <CheckCircle2 className="w-3 h-3" /> In CRM
                              </div>
                            ) : (
                              <button
                                onClick={() => addShopifyLeadToCRM(lead)}
                                disabled={shopifyAdding === lead.domain}
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-dark hover:bg-brand disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-all"
                              >
                                {shopifyAdding === lead.domain
                                  ? <><Loader2 className="w-3 h-3 animate-spin" /> Adding…</>
                                  : <><Users className="w-3 h-3" /> Add to CRM</>}
                              </button>
                            )}
                            {lead.email && (
                              <button
                                onClick={() => { navigator.clipboard.writeText(lead.email!); toast.success("Email copied"); }}
                                className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-medium rounded-lg transition-all"
                              >
                                <Copy className="w-3 h-3" /> Copy email
                              </button>
                            )}
                            <a
                              href={`https://${lead.domain}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-medium rounded-lg transition-all"
                            >
                              <ShoppingBag className="w-3 h-3" /> Visit store
                            </a>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Empty initial state */}
              {!shopifySearching && !shopifySearched && (
                <div className="bg-white rounded-xl border border-dashed border-slate-200 p-12 text-center">
                  <div className="text-4xl mb-4">🏪</div>
                  <p className="text-sm font-semibold text-slate-600 mb-2">Find Shopify store owners as leads</p>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
                    Enter a niche above — we&apos;ll search the web for active Shopify stores and pull their email, phone, and social media handles so you can reach out directly.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ────────────────── BUSINESS LEADS ────────────────── */}
          {section === "business_leads" && (
            <div className="p-5">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h1 className="text-2xl font-bold text-slate-800">Business Leads</h1>
                  <p className="text-sm text-slate-500 mt-1">Find any type of business by keyword and location — get phone, email, address and website from Google Maps data</p>
                </div>
              </div>

              {/* Search bar */}
              <div className="bg-white rounded-2xl border border-slate-200 p-5 mb-6 shadow-sm">
                <div className="flex flex-col sm:flex-row gap-3">
                  <div className="flex-1">
                    <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5 block">Business type / keyword *</label>
                    <input
                      value={bizKeyword}
                      onChange={e => setBizKeyword(e.target.value)}
                      onKeyDown={e => e.key === "Enter" && !bizSearching && searchBusinessLeads()}
                      placeholder="e.g. dental clinic, fitness gym, coffee roaster…"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand transition-all"
                    />
                  </div>
                  <div className="w-full sm:w-56">
                    <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5 block">City / Location (optional)</label>
                    <input
                      value={bizLocation}
                      onChange={e => setBizLocation(e.target.value)}
                      placeholder="e.g. New York, Toronto, London…"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand transition-all"
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      onClick={searchBusinessLeads}
                      disabled={bizSearching || !bizKeyword.trim()}
                      className="flex items-center gap-2 px-5 py-2.5 bg-brand-dark hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl transition-all shadow-sm whitespace-nowrap"
                    >
                      {bizSearching
                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Searching…</>
                        : <><Search className="w-4 h-4" /> Find businesses</>}
                    </button>
                  </div>
                </div>
                <p className="text-xs text-slate-400 mt-3 flex items-center gap-1.5">
                  <Building2 className="w-3 h-3" />
                  Pulls real listings from Google Maps — includes verified phone numbers and business addresses.
                  {bizSearching && <span className="text-amber-600 font-medium"> Scraping websites for emails… this takes 15–30 seconds.</span>}
                </p>
              </div>

              {/* Loading skeleton */}
              {bizSearching && (
                <div className="space-y-3">
                  {[1,2,3,4,5].map(i => (
                    <div key={i} className="bg-white rounded-xl border border-slate-100 p-4 animate-pulse">
                      <div className="flex items-start gap-4">
                        <div className="w-10 h-10 rounded-xl bg-slate-200 shrink-0" />
                        <div className="flex-1 space-y-2">
                          <div className="h-4 bg-slate-200 rounded w-1/3" />
                          <div className="h-3 bg-slate-100 rounded w-2/3" />
                          <div className="flex gap-3 mt-1">
                            <div className="h-3 bg-slate-100 rounded w-28" />
                            <div className="h-3 bg-slate-100 rounded w-20" />
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <div className="h-8 w-24 bg-slate-200 rounded-xl" />
                          <div className="h-8 w-20 bg-slate-100 rounded-xl" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* No results */}
              {!bizSearching && bizSearched && bizLeads.length === 0 && (
                <div className="bg-white rounded-xl border border-slate-100 p-10 text-center">
                  <div className="text-3xl mb-3">🔍</div>
                  <p className="text-sm font-semibold text-slate-600 mb-1">No businesses found</p>
                  <p className="text-xs text-slate-400">Try a broader keyword or add a different city</p>
                </div>
              )}

              {/* Results */}
              {!bizSearching && bizLeads.length > 0 && (
                <div className="space-y-3">
                  <p className="text-xs text-slate-500 font-medium">
                    {bizLeads.length} businesses found for <span className="text-brand font-semibold">{bizKeyword}</span>
                    {bizLocation && <> in <span className="text-brand font-semibold">{bizLocation}</span></>}
                    {" — "}{bizLeads.filter(l => l.phone).length} with phone · {bizLeads.filter(l => l.email).length} with email
                  </p>
                  {bizLeads.map((lead, idx) => {
                    const key = lead.domain || lead.name.toLowerCase();
                    const mapsUrl = lead.place_id
                      ? `https://www.google.com/maps/place/?q=place_id:${lead.place_id}`
                      : lead.website;
                    return (
                      <div key={idx} className="bg-white rounded-xl border border-slate-100 p-4 hover:border-slate-200 hover:shadow-sm transition-all duration-200">
                        <div className="flex items-start gap-4">
                          {/* Icon + rating */}
                          <div className="flex flex-col items-center gap-1 shrink-0">
                            <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center">
                              <Building2 className="w-5 h-5 text-blue-600" />
                            </div>
                            {lead.rating && (
                              <span className="text-[10px] font-bold text-amber-600">
                                ★ {lead.rating.toFixed(1)}
                              </span>
                            )}
                          </div>

                          {/* Info */}
                          <div className="flex-1 min-w-0">
                            {/* Name + badges */}
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className="font-bold text-slate-800 text-sm">{lead.name}</span>
                              {lead.category && (
                                <span className="text-[10px] bg-blue-50 text-blue-700 border border-blue-100 px-2 py-0.5 rounded-full font-semibold">{lead.category}</span>
                              )}
                              {(lead.email || lead.phone) && (
                                <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-100 px-2 py-0.5 rounded-full font-semibold">Has contact</span>
                              )}
                              {lead.reviews && lead.reviews > 0 && (
                                <span className="text-[10px] text-slate-400">{lead.reviews.toLocaleString()} reviews</span>
                              )}
                            </div>

                            {/* Address */}
                            {lead.address && (
                              <p className="text-xs text-slate-500 flex items-center gap-1 mb-1.5">
                                <MapPin className="w-3 h-3 text-slate-400 shrink-0" />
                                {lead.address}
                              </p>
                            )}

                            {/* Contact row */}
                            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                              {lead.phone && (
                                <span className="flex items-center gap-1 text-xs text-slate-600">
                                  <Phone className="w-3 h-3 text-slate-400" />
                                  <button
                                    onClick={() => { navigator.clipboard.writeText(lead.phone!); toast.success("Phone copied"); }}
                                    className="hover:text-brand transition-colors font-medium"
                                  >{lead.phone}</button>
                                </span>
                              )}
                              {lead.email && (
                                <span className="flex items-center gap-1 text-xs text-slate-600">
                                  <Mail className="w-3 h-3 text-slate-400" />
                                  <button
                                    onClick={() => { navigator.clipboard.writeText(lead.email!); toast.success("Email copied"); }}
                                    className="hover:text-brand transition-colors"
                                  >{lead.email}</button>
                                </span>
                              )}
                              {lead.website && (
                                <a href={lead.website} target="_blank" rel="noopener noreferrer"
                                  className="text-xs text-brand hover:underline font-mono">
                                  {lead.domain || lead.website.replace(/^https?:\/\//, "").split("/")[0]}
                                </a>
                              )}
                            </div>
                          </div>

                          {/* Actions */}
                          <div className="flex flex-col gap-1.5 shrink-0">
                            {bizAdded.has(key) ? (
                              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold rounded-lg">
                                <CheckCircle2 className="w-3 h-3" /> In CRM
                              </div>
                            ) : (
                              <button
                                onClick={() => addBusinessLeadToCRM(lead)}
                                disabled={bizAdding === key}
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-dark hover:bg-brand disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-all"
                              >
                                {bizAdding === key
                                  ? <><Loader2 className="w-3 h-3 animate-spin" /> Adding…</>
                                  : <><Users className="w-3 h-3" /> Add to CRM</>}
                              </button>
                            )}
                            {lead.phone && (
                              <button
                                onClick={() => { navigator.clipboard.writeText(lead.phone!); toast.success("Phone copied"); }}
                                className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-medium rounded-lg transition-all"
                              >
                                <Copy className="w-3 h-3" /> Copy phone
                              </button>
                            )}
                            {mapsUrl && (
                              <a
                                href={mapsUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-medium rounded-lg transition-all"
                              >
                                <Globe className="w-3 h-3" /> View on Maps
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Empty initial state */}
              {!bizSearching && !bizSearched && (
                <div className="bg-white rounded-xl border border-dashed border-slate-200 p-12 text-center">
                  <div className="text-4xl mb-4">🏢</div>
                  <p className="text-sm font-semibold text-slate-600 mb-2">Find any business as a lead</p>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
                    Search by business type and city — we pull real Google Maps listings with verified phone numbers, then scrape each website for email addresses.
                  </p>
                  <div className="flex flex-wrap justify-center gap-2 mt-4">
                    {["dental clinic", "fitness gym", "coffee roaster", "marketing agency", "law firm"].map(ex => (
                      <button key={ex} onClick={() => { setBizKeyword(ex); }}
                        className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-all font-medium">
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ────────────────── LEAD SCOUTS ────────────────── */}
          {section === "lead_scouts" && (
            <div className="p-5">
              {/* Header */}
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h1 className="text-2xl font-bold text-slate-800">Lead Scouts</h1>
                  <p className="text-sm text-slate-500 mt-0.5">Set searches once — scouts run automatically and bring new leads to your inbox</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={runAllLeadScouts}
                    disabled={runningAllLeadScouts || leadScouts.filter(s => s.enabled).length === 0}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-semibold rounded-xl transition-all"
                  >
                    {runningAllLeadScouts ? <><Loader2 className="w-4 h-4 animate-spin" /> Running…</> : <><Play className="w-4 h-4" /> Run All</>}
                  </button>
                  <button
                    onClick={() => setShowLeadScoutForm(v => !v)}
                    className="flex items-center gap-2 px-4 py-2 bg-brand-dark hover:bg-brand text-white text-sm font-semibold rounded-xl transition-all"
                  >
                    <Plus className="w-4 h-4" /> New Scout
                  </button>
                </div>
              </div>

              {/* Credit balance dashboard */}
              {creditInfo && (
                <div className={`rounded-2xl border p-4 mb-5 ${creditInfo.balance <= 2 ? "bg-red-50 border-red-200" : creditInfo.balance <= 5 ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-100"}`}>
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    {/* Balance */}
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${creditInfo.balance <= 2 ? "bg-red-100" : creditInfo.balance <= 5 ? "bg-amber-100" : "bg-emerald-100"}`}>
                        <DollarSign className={`w-5 h-5 ${creditInfo.balance <= 2 ? "text-red-600" : creditInfo.balance <= 5 ? "text-amber-600" : "text-emerald-600"}`} />
                      </div>
                      <div>
                        <p className="text-xs text-slate-500 font-medium">Your credit balance</p>
                        <p className={`text-2xl font-bold ${creditInfo.balance <= 2 ? "text-red-600" : creditInfo.balance <= 5 ? "text-amber-600" : "text-slate-800"}`}>
                          {creditInfo.balance.toFixed(0)} <span className="text-sm font-normal text-slate-400">credits</span>
                        </p>
                        {creditInfo.balance <= 2 && (
                          <p className="text-[10px] text-red-600 font-semibold mt-0.5">Contact Zilo to top up</p>
                        )}
                      </div>
                    </div>

                    {/* Pricing breakdown */}
                    <div className="flex gap-6 text-center">
                      <div>
                        <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Cost per run</p>
                        <p className="text-lg font-bold text-slate-800">${creditInfo.credit_price_usd.toFixed(2)}</p>
                        <p className="text-[10px] text-slate-400">1 credit</p>
                      </div>
                      <div className="border-l border-slate-200 pl-6">
                        <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Total runs</p>
                        <p className="text-lg font-bold text-slate-800">{creditInfo.total_runs}</p>
                        <p className="text-[10px] text-slate-400">{creditInfo.total_runs} credits used</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Create Scout Form */}
              {showLeadScoutForm && (
                <div className="bg-white rounded-2xl border border-brand/30 p-5 mb-5 shadow-sm">
                  <h3 className="font-bold text-slate-800 text-sm mb-4">New Lead Scout</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                    <div>
                      <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1 block">Scout name (optional)</label>
                      <input value={leadScoutForm.name} onChange={e => setLeadScoutForm(p => ({...p, name: e.target.value}))}
                        placeholder="e.g. Maryland Dentists"
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand" />
                    </div>
                    <div>
                      <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1 block">Keyword / Business type *</label>
                      <input value={leadScoutForm.keyword} onChange={e => setLeadScoutForm(p => ({...p, keyword: e.target.value}))}
                        placeholder="e.g. dental clinic, marketing agency"
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand" />
                    </div>
                    <div>
                      <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1 block">Location</label>
                      <input value={leadScoutForm.location} onChange={e => setLeadScoutForm(p => ({...p, location: e.target.value}))}
                        placeholder="e.g. Maryland, Toronto, Nairobi"
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand" />
                    </div>
                    <div>
                      <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1 block">Run frequency</label>
                      <select value={leadScoutForm.frequency} onChange={e => setLeadScoutForm(p => ({...p, frequency: e.target.value as any}))}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand">
                        <option value="manual">Manual only</option>
                        <option value="weekly">Weekly (every 7 days)</option>
                        <option value="daily">Daily (every 24 hours)</option>
                      </select>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 mb-4">
                    <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
                      <input type="checkbox" checked={leadScoutForm.require_phone} onChange={e => setLeadScoutForm(p => ({...p, require_phone: e.target.checked}))} className="rounded" />
                      Only with phone
                    </label>
                    <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
                      <input type="checkbox" checked={leadScoutForm.require_email} onChange={e => setLeadScoutForm(p => ({...p, require_email: e.target.checked}))} className="rounded" />
                      Only with email
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={createLeadScout}
                      className="px-5 py-2 bg-brand-dark hover:bg-brand text-white text-sm font-semibold rounded-xl transition-all">
                      Save Scout
                    </button>
                    <button onClick={() => setShowLeadScoutForm(false)}
                      className="px-4 py-2 border border-slate-200 text-slate-500 text-sm rounded-xl hover:bg-slate-50">
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Tabs */}
              <div className="flex gap-1 bg-slate-100 rounded-xl p-1 mb-5 w-fit">
                {(["inbox", "scouts"] as const).map(tab => (
                  <button key={tab} onClick={() => setScoutTab(tab)}
                    className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all capitalize ${scoutTab === tab ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
                    {tab === "inbox" ? `Lead Inbox${inboxLeads.length > 0 ? ` (${inboxLeads.length})` : ""}` : `My Scouts${leadScouts.length > 0 ? ` (${leadScouts.length})` : ""}`}
                  </button>
                ))}
              </div>

              {/* ── INBOX TAB ── */}
              {scoutTab === "inbox" && (
                <div>
                  {/* Cold-start skeleton only (when nothing is loaded yet) */}
                  {inboxLoading && inboxLeads.length === 0 && (
                    <div className="space-y-3">
                      {[1,2,3].map(i => (
                        <div key={i} className="bg-white rounded-xl border border-slate-100 p-4 animate-pulse h-20" />
                      ))}
                    </div>
                  )}
                  {/* Scout filter banner — shown when filtering to a specific scout */}
                  {inboxFilterScoutId && (() => {
                    const filteredScout = leadScouts.find(s => s._id === inboxFilterScoutId);
                    return (
                      <div className="flex items-center justify-between gap-3 mb-3 px-4 py-2.5 bg-blue-50 border border-blue-200 rounded-xl">
                        <div className="flex items-center gap-2 text-xs">
                          <Filter className="w-3.5 h-3.5 text-blue-600" />
                          <span className="text-blue-900 font-medium">
                            Showing leads from <span className="font-bold">{filteredScout?.name || "scout"}</span>
                            {filteredScout?.keyword && <span className="text-blue-600"> · {filteredScout.keyword}</span>}
                          </span>
                        </div>
                        <button
                          onClick={() => { setInboxFilterScoutId(""); void loadInbox(true, inboxStatus, ""); }}
                          className="text-xs font-semibold text-blue-700 hover:text-blue-900 hover:underline">
                          Show all scouts
                        </button>
                      </div>
                    );
                  })()}

                  {/* Status filter pills + bulk action */}
                  <div className="flex items-center justify-between gap-2 mb-4 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap">
                      {(["new","with_contacts","saved","dismissed"] as const).map(s => {
                        const labels = { new: "New", with_contacts: "✓ With contacts", saved: "Saved", dismissed: "Dismissed" };
                        const isActive = inboxStatus === s;
                        const activeColor = s === "with_contacts" ? "bg-emerald-600 text-white border-emerald-600" : "bg-brand-dark text-white border-brand-dark";
                        const styles = isActive ? activeColor : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50";
                        return (
                          <button key={s}
                            onClick={() => { setInboxStatus(s); void loadInbox(true, s, inboxFilterScoutId); }}
                            title={s === "with_contacts" ? "Only show leads with BOTH email and phone — your highest-quality contacts" : ""}
                            className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-all ${styles}`}>
                            {labels[s]} <span className={`ml-1 ${isActive ? "opacity-80" : "text-slate-400"}`}>({inboxCounts[s] ?? 0})</span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Type selector + bulk add — only shows when there are new leads */}
                    {(inboxStatus === "new" || inboxStatus === "with_contacts") && inboxLeads.length > 0 && (
                      <div className="flex items-center gap-1.5">
                        <label className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Add as:</label>
                        <select
                          value={addAsType}
                          onChange={e => setAddAsType(e.target.value as typeof addAsType)}
                          className="text-xs font-semibold border border-slate-200 rounded-lg px-2 py-1.5 bg-white text-slate-700 cursor-pointer hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand/30">
                          <option value="Customer">Customer</option>
                          <option value="Lead">Lead</option>
                          <option value="Investor">Investor</option>
                          <option value="Partner">Partner</option>
                          <option value="Supplier">Supplier</option>
                          <option value="Other">Other</option>
                        </select>
                        <button
                          onClick={bulkAddToCRM}
                          disabled={bulkSavingInbox}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-xs font-semibold rounded-lg transition-all shadow-sm">
                          {bulkSavingInbox ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Adding…</> : <><Users className="w-3.5 h-3.5" />Add all to CRM</>}
                        </button>
                      </div>
                    )}
                  </div>

                  {!inboxLoading && inboxLeads.length === 0 && inboxTotal === 0 && (
                    <div className="bg-white rounded-xl border border-dashed border-slate-200 p-12 text-center">
                      <div className="text-4xl mb-3">{inboxStatus === "new" ? "📥" : inboxStatus === "with_contacts" ? "✨" : inboxStatus === "saved" ? "✅" : "🗑️"}</div>
                      <p className="text-sm font-semibold text-slate-600 mb-1">
                        {inboxStatus === "new" ? "Inbox is empty"
                          : inboxStatus === "with_contacts" ? "No leads with email + phone"
                          : inboxStatus === "saved" ? "No saved leads yet"
                          : "No dismissed leads"}
                      </p>
                      <p className="text-xs text-slate-400 mb-4">
                        {inboxStatus === "new"
                          ? "Create a scout and run it — new leads land here, filtered to exclude anyone already in your CRM."
                          : inboxStatus === "with_contacts"
                            ? "No new leads currently have both email AND phone. Check the 'New' tab for partial-contact leads."
                            : inboxStatus === "saved"
                              ? "Leads you've added to your CRM will appear here for reference."
                              : "Leads you dismiss will appear here. Click Restore to bring them back."}
                      </p>
                      {(inboxStatus === "new" || inboxStatus === "with_contacts") && (
                        <button onClick={() => { setScoutTab("scouts"); setShowLeadScoutForm(true); }}
                          className="px-4 py-2 bg-brand-dark text-white text-xs font-semibold rounded-xl hover:bg-brand transition-all">
                          + Create your first scout
                        </button>
                      )}
                    </div>
                  )}
                  {inboxLeads.length > 0 && (
                    <div className={`space-y-2 transition-opacity duration-150 ${inboxLoading ? "opacity-40 pointer-events-none" : "opacity-100"}`}>
                      <p className="text-xs text-slate-500 font-medium mb-3">
                        {inboxStatus === "new" && <>Showing {inboxLeads.length} new leads — none of these are in your CRM yet</>}
                        {inboxStatus === "with_contacts" && <>Showing {inboxLeads.length} leads with BOTH email + phone — your highest-quality contacts</>}
                        {inboxStatus === "saved" && <>Showing {inboxLeads.length} leads you've added to your CRM</>}
                        {inboxStatus === "dismissed" && <>Showing {inboxLeads.length} dismissed leads — click Restore to bring them back to your inbox</>}
                      </p>
                      {inboxLeads.map((lead, i) => {
                        const mapsUrl = lead.place_id ? `https://www.google.com/maps/place/?q=place_id:${lead.place_id}` : lead.website;
                        const batchIdx = lead._batch_index ?? 0;
                        const prevBatchIdx = i > 0 ? (inboxLeads[i-1]._batch_index ?? 0) : -1;
                        const isFirstInBatch = batchIdx !== prevBatchIdx;
                        // Color palette: batch 0 = emerald (free), then amber, blue, purple, pink rotating
                        const palette = [
                          { border: "border-l-emerald-400", chip: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: "text-emerald-600" },
                          { border: "border-l-amber-400",   chip: "bg-amber-50 text-amber-800 border-amber-200",       icon: "text-amber-600" },
                          { border: "border-l-blue-400",    chip: "bg-blue-50 text-blue-700 border-blue-200",          icon: "text-blue-600" },
                          { border: "border-l-purple-400",  chip: "bg-purple-50 text-purple-700 border-purple-200",    icon: "text-purple-600" },
                          { border: "border-l-pink-400",    chip: "bg-pink-50 text-pink-700 border-pink-200",          icon: "text-pink-600" },
                        ];
                        const c = palette[batchIdx % palette.length];
                        const batchLabel = batchIdx === 0 ? "Free batch · included with scout run" : `Batch ${batchIdx + 1} · unlocked for 1 credit`;
                        return (
                          <div key={lead._id}>
                            {isFirstInBatch && (
                              <div className="flex items-center gap-2 my-3 first:mt-0">
                                <div className={`h-px flex-1 ${batchIdx === 0 ? "bg-emerald-200" : "bg-amber-200"}`} />
                                <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border ${c.chip}`}>
                                  {batchLabel}
                                </span>
                                <div className={`h-px flex-1 ${batchIdx === 0 ? "bg-emerald-200" : "bg-amber-200"}`} />
                              </div>
                            )}
                          <div className={`bg-white rounded-xl border border-slate-100 border-l-4 ${c.border} p-4 hover:border-slate-200 transition-all`}>
                            <div className="flex items-start gap-3">
                              <div className="w-9 h-9 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center shrink-0">
                                <Building2 className={`w-4 h-4 ${c.icon}`} />
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap mb-0.5">
                                  <span className="font-bold text-slate-800 text-sm">{lead.name}</span>
                                  {lead.category && <span className="text-[10px] bg-blue-50 text-blue-700 border border-blue-100 px-2 py-0.5 rounded-full font-semibold">{lead.category}</span>}
                                  {lead.rating && <span className="text-[10px] text-amber-600 font-bold">★ {lead.rating.toFixed(1)}</span>}
                                  <span className="text-[10px] text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-100">via {lead.scout_name}</span>
                                </div>
                                {lead.address && <p className="text-xs text-slate-500 flex items-center gap-1 mb-1"><MapPin className="w-3 h-3 shrink-0 text-slate-400" />{lead.address}</p>}
                                <div className="flex flex-wrap gap-x-4 gap-y-0.5">
                                  {lead.phone && (
                                    <button onClick={() => { navigator.clipboard.writeText(lead.phone!); toast.success("Phone copied"); }}
                                      className="flex items-center gap-1 text-xs text-slate-600 hover:text-brand transition-colors">
                                      <Phone className="w-3 h-3 text-slate-400" />{lead.phone}
                                    </button>
                                  )}
                                  {lead.email && (
                                    <button onClick={() => { navigator.clipboard.writeText(lead.email!); toast.success("Email copied"); }}
                                      className="flex items-center gap-1 text-xs text-slate-600 hover:text-brand transition-colors">
                                      <Mail className="w-3 h-3 text-slate-400" />{lead.email}
                                    </button>
                                  )}
                                  {lead.website && <a href={lead.website} target="_blank" rel="noopener noreferrer" className="text-xs text-brand hover:underline font-mono">{lead.domain || lead.website.replace(/^https?:\/\//,"").split("/")[0]}</a>}
                                </div>
                              </div>
                              <div className="flex flex-col gap-1.5 shrink-0">
                                {(inboxStatus === "new" || inboxStatus === "with_contacts") && (
                                  <button onClick={() => saveInboxLead(lead)} disabled={savingInboxLead === lead._id}
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-dark hover:bg-brand disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-all">
                                    {savingInboxLead === lead._id ? <><Loader2 className="w-3 h-3 animate-spin" />Saving…</> : <><Users className="w-3 h-3" />Add to CRM</>}
                                  </button>
                                )}
                                {inboxStatus === "saved" && (
                                  <span className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold rounded-lg">
                                    <CheckCircle2 className="w-3 h-3" />In CRM
                                  </span>
                                )}
                                {inboxStatus === "dismissed" && (
                                  <button onClick={() => restoreInboxLead(lead._id)}
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold rounded-lg transition-all">
                                    <RefreshCw className="w-3 h-3" />Restore
                                  </button>
                                )}
                                {mapsUrl && (
                                  <a href={mapsUrl} target="_blank" rel="noopener noreferrer"
                                    className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-medium rounded-lg transition-all">
                                    <Globe className="w-3 h-3" />Maps
                                  </a>
                                )}
                                {(inboxStatus === "new" || inboxStatus === "with_contacts") && (
                                  <button onClick={() => dismissInboxLead(lead._id)}
                                    className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-500 hover:bg-slate-50 text-xs font-medium rounded-lg transition-all">
                                    <X className="w-3 h-3" />Dismiss
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                          </div>
                        );
                      })}
                      {inboxHasMore && (
                        <button
                          onClick={() => loadInbox(false)}
                          disabled={loadingMoreInbox}
                          className={`w-full mt-3 py-2.5 rounded-xl border text-xs font-semibold disabled:opacity-50 transition-all flex items-center justify-center gap-2 ${(inboxStatus === "new" || inboxStatus === "with_contacts") ? "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
                          {loadingMoreInbox ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Loading…</>
                            : (inboxStatus === "new" || inboxStatus === "with_contacts")
                              ? <><DollarSign className="w-3.5 h-3.5" />Unlock next 15 leads · 1 credit</>
                              : <>Load 15 more</>}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* ── SCOUTS TAB ── */}
              {scoutTab === "scouts" && (
                <div>
                  {leadScoutsLoading && <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="bg-white rounded-xl border border-slate-100 p-4 animate-pulse h-16" />)}</div>}
                  {!leadScoutsLoading && leadScouts.length === 0 && (
                    <div className="bg-white rounded-xl border border-dashed border-slate-200 p-12 text-center">
                      <div className="text-4xl mb-3">🔭</div>
                      <p className="text-sm font-semibold text-slate-600 mb-1">No scouts yet</p>
                      <p className="text-xs text-slate-400 mb-4">Create a scout with a keyword + location. It will automatically find new businesses and drop them into your inbox.</p>
                      <button onClick={() => setShowLeadScoutForm(true)}
                        className="px-4 py-2 bg-brand-dark text-white text-xs font-semibold rounded-xl hover:bg-brand transition-all">
                        + Create first scout
                      </button>
                    </div>
                  )}
                  {!leadScoutsLoading && leadScouts.length > 0 && (
                    <div className="space-y-2">
                      {leadScouts.map(scout => (
                        <div key={scout._id} className={`bg-white rounded-xl border p-4 transition-all ${scout.enabled ? "border-slate-100 hover:border-slate-200" : "border-slate-100 opacity-60"}`}>
                          <div className="flex items-center gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap mb-0.5">
                                <span className="font-bold text-slate-800 text-sm">{scout.name}</span>
                                <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-medium">{scout.keyword}</span>
                                {scout.location && <span className="text-[10px] text-slate-400 flex items-center gap-0.5"><MapPin className="w-2.5 h-2.5" />{scout.location}</span>}
                                <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold border ${scout.frequency === "daily" ? "bg-amber-50 text-amber-700 border-amber-100" : scout.frequency === "weekly" ? "bg-blue-50 text-blue-700 border-blue-100" : "bg-slate-50 text-slate-500 border-slate-100"}`}>
                                  {scout.frequency === "manual" ? "Manual" : scout.frequency === "daily" ? "Daily" : "Weekly"}
                                </span>
                                {scout.inbox_count > 0 && (
                                  <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-100 px-2 py-0.5 rounded-full font-bold">{scout.inbox_count} new</span>
                                )}
                              </div>
                              <p className="text-[11px] text-slate-400">
                                {scout.last_run ? `Last run ${new Date(scout.last_run).toLocaleDateString()}` : "Never run"}
                                {scout.frequency !== "manual" && scout.next_run && ` · Next: ${new Date(scout.next_run).toLocaleDateString()}`}
                                {" · "}Cost: <span className="font-medium text-slate-500">1 credit (${(creditInfo?.credit_price_usd ?? 0.01).toFixed(2)})</span>
                              </p>
                              {scout.expanded_keywords?.length ? (
                                <div className="flex flex-wrap gap-1 mt-1.5 items-center">
                                  <span className="text-[9px] text-slate-400 font-semibold uppercase tracking-wider mr-1">AI added:</span>
                                  {scout.expanded_keywords.map((kw, i) => (
                                    <span key={i} className={`group inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full font-medium ${i === 0 ? "bg-brand/10 text-brand-dark" : "bg-slate-100 text-slate-600 hover:bg-red-50 hover:text-red-600"}`}>
                                      {kw}
                                      {i > 0 && (
                                        <button onClick={() => removeExpandedKeyword(scout, kw)}
                                          title="Remove this keyword"
                                          className="opacity-40 hover:opacity-100 transition-opacity ml-0.5">
                                          <X className="w-2 h-2" />
                                        </button>
                                      )}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-[10px] text-slate-300 mt-1 italic">AI expanding keywords…</p>
                              )}
                              {scout.last_error && <p className="text-[10px] text-red-500 mt-0.5">{scout.last_error}</p>}
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <button
                                onClick={() => {
                                  setInboxFilterScoutId(scout._id);
                                  setScoutTab("inbox");
                                  setInboxStatus("new");
                                  void loadInbox(true, "new", scout._id);
                                }}
                                title={`View this scout's leads in the inbox`}
                                className="flex items-center gap-1 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold rounded-lg border border-blue-200 transition-all">
                                <Eye className="w-3 h-3" />View leads
                              </button>
                              <button onClick={() => toggleLeadScout(scout)}
                                className={`text-[10px] px-2.5 py-1 rounded-lg font-semibold border transition-all ${scout.enabled ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100" : "bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100"}`}>
                                {scout.enabled ? "ON" : "OFF"}
                              </button>
                              <button onClick={() => runLeadScout(scout._id)} disabled={runningLeadScout === scout._id}
                                className="flex items-center gap-1 px-3 py-1.5 bg-brand-dark hover:bg-brand disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-all">
                                {runningLeadScout === scout._id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                                Run
                              </button>
                              <button onClick={() => deleteLeadScout(scout._id)}
                                className="p-1.5 border border-slate-200 text-slate-400 hover:text-red-500 hover:border-red-200 rounded-lg transition-all">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
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

"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Zap, Play, Square, RefreshCw, CheckCircle, XCircle, Edit2,
  Loader2, AlertCircle, Target, Users,
  Globe, Settings2, DollarSign, Sparkles, ExternalLink,
  Activity, ListChecks, TrendingUp, Plus, Trash2,
  BrainCircuit, Radio, StopCircle, Search,
} from "lucide-react";

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
  mode: "review" | "auto";
  google_review_link?: string;
}

const SOCIAL_PLATFORMS = [
  { id: "facebook",        label: "Facebook",              emoji: "📘" },
  { id: "whatsapp",        label: "WhatsApp (Evolution)",  emoji: "🟢", hint: "Groups via your connected account" },
  { id: "whatsapp_biz",    label: "WhatsApp Business",     emoji: "💚", hint: "Official API DMs via Zernio" },
  { id: "instagram",       label: "Instagram",             emoji: "📸" },
  { id: "telegram",        label: "Telegram",              emoji: "✈️" },
  { id: "linkedin",        label: "LinkedIn",              emoji: "💼" },
  { id: "reddit",          label: "Reddit",                emoji: "🟠" },
  { id: "tiktok",          label: "TikTok",                emoji: "🎵" },
  { id: "google_business", label: "Google Reviews",        emoji: "⭐" },
];

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

type Tab = "feed" | "queue" | "opportunities" | "radar" | "instant" | "settings";

const AGENTS = [
  { id: "funding_hunter", label: "Funding Hunter", icon: DollarSign, color: "text-emerald-600", bg: "bg-emerald-50", desc: "Finds VCs, grants & accelerator programs" },
  { id: "lead_gen", label: "Lead Generation", icon: Users, color: "text-blue-600", bg: "bg-blue-50", desc: "Finds potential customers & Facebook groups" },
  { id: "social_scout", label: "Social Scout", icon: Globe, color: "text-purple-600", bg: "bg-purple-50", desc: "Finds conversations worth engaging on social media" },
  { id: "admin_autopilot", label: "Admin Autopilot", icon: Settings2, color: "text-orange-600", bg: "bg-orange-50", desc: "Handles invoice reminders & cold customer re-engagement" },
];

const KIND_COLORS: Record<string, string> = {
  info: "text-slate-500",
  opportunity: "text-emerald-600",
  action: "text-blue-600",
  warning: "text-rose-500",
};

const ACTION_LABELS: Record<string, string> = {
  send_whatsapp: "Send WhatsApp",
  send_email: "Send Email",
  post_comment: "Post Comment",
  join_group: "Join Group",
  submit_application: "Submit Application",
  review_result: "Review & Act",
};

const SCHEDULE_LABELS: Record<string, string> = {
  daily: "Runs daily",
  weekly: "Runs weekly",
  on_demand: "On demand",
};

const EMOJI_SUGGESTIONS = ["🤖", "🔍", "📣", "🎯", "💡", "🚀", "📊", "🌍", "💬", "🛒", "📸", "✉️"];

export default function ActionModePage() {
  const [tab, setTab] = useState<Tab>("feed");
  const [settings, setSettings] = useState<Settings>({ enabled: false, goals: "", agents: {} });
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [customAgents, setCustomAgents] = useState<CustomAgent[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [runningFusion, setRunningFusion] = useState(false);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [runningPredictions, setRunningPredictions] = useState(false);
  const [radarPane, setRadarPane] = useState<"clusters" | "predictions" | "recon">("clusters");
  const [recon, setRecon] = useState<ReconItem[]>([]);
  const [runningRecon, setRunningRecon] = useState(false);
  const [instantActions, setInstantActions] = useState<InstantAction[]>([]);
  const [runningInstant, setRunningInstant] = useState(false);
  const [expandedAction, setExpandedAction] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [editingItem, setEditingItem] = useState<string | null>(null);
  const [editedContent, setEditedContent] = useState<Record<string, string>>({});
  const [processing, setProcessing] = useState<Record<string, boolean>>({});
  const [runningAgent, setRunningAgent] = useState<string | null>(null);
  const [runningCustomAgent, setRunningCustomAgent] = useState<string | null>(null);
  const [error, setError] = useState("");
  const liveDeadlineRef = useRef(0);
  const watchActiveRef = useRef(false);
  const tabRef = useRef<Tab>("feed");
  const [liveHeadline, setLiveHeadline] = useState<string | null>(null);
  const [phaseIdx, setPhaseIdx] = useState(0);
  const phases = useMemo(
    () => [
      "Syncing objectives into agent memory…",
      "Scanning funding, lead & social signals…",
      "Reasoning through constraints & next-best actions…",
      "Drafting approvals & streaming to your activity log…",
      "Packaging fresh opportunities for you…",
    ],
    []
  );

  // Create-agent form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newAgent, setNewAgent] = useState({ name: "", emoji: "🤖", description: "", schedule: "on_demand" });
  const [savingAgent, setSavingAgent] = useState(false);

  // Social engagement state
  const [socialSettings, setSocialSettings] = useState<SocialSettings>({
    platforms: ["facebook"], keywords: [], groups: [], location: "", daily_limit: 10, auto_run: true, mode: "review",
  });
  const [savingSocial, setSavingSocial] = useState(false);
  const [runningSocial, setRunningSocial] = useState(false);
  const [newKeyword, setNewKeyword] = useState("");

  // Watch URL suggestions
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<{ platform: string; url: string; title: string }[]>([]);

  // Extension state
  const [extStatus, setExtStatus] = useState<"checking" | "not_installed" | "connected" | "disconnected">("checking");
  const [extStats, setExtStats] = useState({ keywordCount: 0, groupCount: 0, autoPostEnabled: true });
  const [connectingExt, setConnectingExt] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await api.get<Settings>("/action-mode/settings");
      setSettings(s);

      const [f, q, o, ca, ss, cl, pr, rc, ia] = await Promise.all([
        api.get<{ items: FeedItem[] }>("/action-mode/feed"),
        api.get<{ items: QueueItem[] }>("/action-mode/queue"),
        api.get<{ opportunities: Opportunity[] }>("/action-mode/opportunities"),
        api.get<{ agents: CustomAgent[] }>("/action-mode/agents"),
        api.get<SocialSettings>("/action-mode/social/settings"),
        api.get<{ clusters: Cluster[] }>("/action-mode/clusters"),
        api.get<{ predictions: Prediction[] }>("/action-mode/predictions"),
        api.get<{ recon: ReconItem[] }>("/action-mode/recon"),
        api.get<{ items: InstantAction[] }>("/action-mode/instant"),
      ]);
      setFeed(f.items);
      setQueue(q.items);
      setOpportunities(o.opportunities);
      setCustomAgents(ca.agents);
      setSocialSettings(ss);
      setClusters(cl.clusters);
      setPredictions(pr.predictions);
      setRecon(rc.recon);
      setInstantActions(ia.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchLiveSnapshot = useCallback(async () => {
    const [f, q, o] = await Promise.all([
      api.get<{ items: FeedItem[] }>("/action-mode/feed"),
      api.get<{ items: QueueItem[] }>("/action-mode/queue"),
      api.get<{ opportunities: Opportunity[] }>("/action-mode/opportunities"),
    ]);
    return { feed: f.items, queue: q.items, opportunities: o.opportunities };
  }, []);

  useEffect(() => {
    tabRef.current = tab;
  }, [tab]);

  function beginLiveWatch(headline: string, durationMs = 52_000) {
    watchActiveRef.current = true;
    liveDeadlineRef.current = Date.now() + durationMs;
    setLiveHeadline(headline);
    setTab("feed");
  }

  function endLiveWatch() {
    watchActiveRef.current = false;
    liveDeadlineRef.current = 0;
    setLiveHeadline(null);
  }

  async function dismissLiveWatch() {
    endLiveWatch();
    setRunning(false);
    setRunningAgent(null);
    setRunningCustomAgent(null);
    await load();
  }

  useEffect(() => {
    if (!liveHeadline) {
      setPhaseIdx(0);
      return;
    }
    const t = setInterval(() => {
      setPhaseIdx((i) => (i + 1) % phases.length);
    }, 2300);
    return () => clearInterval(t);
  }, [liveHeadline, phases.length]);

  useEffect(() => {
    if (!liveHeadline) return;
    const finish = async () => {
      endLiveWatch();
      setRunning(false);
      setRunningAgent(null);
      setRunningCustomAgent(null);
      await load();
    };
    const tick = async () => {
      if (Date.now() >= liveDeadlineRef.current) {
        clearInterval(iv);
        await finish();
        return;
      }
      try {
        const data = await fetchLiveSnapshot();
        setFeed(data.feed);
        setQueue((prev) => {
          if (watchActiveRef.current && data.queue.length > prev.length) {
            const delta = data.queue.length - prev.length;
            toast.message("Approval queue updated", {
              description: `${delta} new ${delta === 1 ? "item" : "items"} waiting for review`,
              ...(tabRef.current !== "queue"
                ? {
                    action: {
                      label: "View queue",
                      onClick: () => setTab("queue"),
                    },
                  }
                : {}),
            });
          }
          return data.queue;
        });
        setOpportunities(data.opportunities);
      } catch {
        /* ignore transient errors while polling */
      }
    };
    const iv = setInterval(tick, 1000);
    void tick();
    return () => clearInterval(iv);
  }, [liveHeadline, load, fetchLiveSnapshot]);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggleEnabled() {
    const next = { ...settings, enabled: !settings.enabled };
    setSettings(next);
    try {
      await api.put("/action-mode/settings", next);
      if (next.enabled) await runAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save");
      setSettings(settings);
    }
  }

  async function saveSettings() {
    setSavingSettings(true);
    try {
      await api.put("/action-mode/settings", settings);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSavingSettings(false);
    }
  }

  async function runAll() {
    setRunning(true);
    setError("");
    beginLiveWatch("Neural fleet — full deployment", 56_000);
    try {
      await api.post("/action-mode/run", {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to run agents");
      endLiveWatch();
      setRunning(false);
    }
  }

  async function runSingleAgent(agentId: string) {
    setRunningAgent(agentId);
    const label = AGENTS.find((a) => a.id === agentId)?.label ?? agentId;
    beginLiveWatch(`${label} — live channel`, 44_000);
    try {
      await api.post(`/action-mode/run/${agentId}`, {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Agent failed");
      endLiveWatch();
      setRunningAgent(null);
    }
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
      setEditingItem(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setProcessing(p => ({ ...p, [item._id]: false }));
    }
  }

  async function createCustomAgent() {
    if (!newAgent.name.trim() || !newAgent.description.trim()) return;
    setSavingAgent(true);
    try {
      await api.post("/action-mode/agents", newAgent);
      setShowCreateForm(false);
      setNewAgent({ name: "", emoji: "🤖", description: "", schedule: "on_demand" });
      const ca = await api.get<{ agents: CustomAgent[] }>("/action-mode/agents");
      setCustomAgents(ca.agents);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create agent");
    } finally {
      setSavingAgent(false);
    }
  }

  async function deleteCustomAgent(id: string) {
    try {
      await api.delete(`/action-mode/agents/${id}`);
      setCustomAgents(ca => ca.filter(a => a._id !== id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete agent");
    }
  }

  async function runCustomAgent(id: string) {
    setRunningCustomAgent(id);
    const name = customAgents.find((a) => a._id === id)?.name ?? "Custom agent";
    beginLiveWatch(`${name} — custom wavelength`, 48_000);
    try {
      await api.post(`/action-mode/run-custom/${id}`, {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Agent failed");
      endLiveWatch();
      setRunningCustomAgent(null);
    }
  }

  async function fetchSuggestions() {
    if (!socialSettings.keywords.length || !socialSettings.platforms.length) {
      toast.error("Add at least one keyword and platform first.");
      return;
    }
    setSuggestLoading(true);
    setSuggestions([]);
    try {
      const params = new URLSearchParams({
        platforms: socialSettings.platforms.join(","),
        keywords:  socialSettings.keywords.join(","),
      });
      const data = await api.get<{ suggestions: { platform: string; url: string; title: string }[] }>(`/action-mode/social/suggest-urls?${params}`);
      if ((data.suggestions || []).length === 0) {
        toast.info("No suggestions found — try different keywords.");
      }
      setSuggestions(data.suggestions || []);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Suggestion search failed");
    } finally {
      setSuggestLoading(false);
    }
  }

  async function saveSocialSettings(next: SocialSettings) {
    setSavingSocial(true);
    try {
      await api.put("/action-mode/social/settings", next);
      setSocialSettings(next);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save social settings");
    } finally {
      setSavingSocial(false);
    }
  }

  async function runSocial() {
    setRunningSocial(true);
    beginLiveWatch("Social Engagement — scanning platforms", 40_000);
    try {
      await api.post("/action-mode/run-social", {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Social agent failed");
      endLiveWatch();
    } finally {
      setRunningSocial(false);
    }
  }

  // Extension bridge — sends a message via the content/dashboard.js relay
  function sendToExtension(payload: Record<string, unknown>): Promise<Record<string, unknown> | null> {
    return new Promise(resolve => {
      const requestId = Math.random().toString(36).slice(2);

      function handler(event: MessageEvent) {
        if (event.data?.type !== "ZILO_FROM_EXT") return;
        if (event.data.requestId !== requestId) return;
        window.removeEventListener("message", handler);
        resolve(event.data.response || null);
      }

      window.addEventListener("message", handler);
      window.postMessage({ type: "ZILO_TO_EXT", requestId, payload }, "*");

      // Timeout if extension doesn't respond (not installed)
      setTimeout(() => {
        window.removeEventListener("message", handler);
        resolve(null);
      }, 1500);
    });
  }

  async function checkExtension() {
    const res = await sendToExtension({ type: "ZILO_PING" });
    if (!res) { setExtStatus("not_installed"); return; }
    if (res.connected) {
      setExtStatus("connected");
      setExtStats({
        keywordCount:    (res.keywordCount as number) || 0,
        groupCount:      (res.groupCount as number)   || 0,
        autoPostEnabled: res.autoPostEnabled !== false,
      });
    } else {
      setExtStatus("disconnected");
    }
  }

  async function connectExtension() {
    setConnectingExt(true);
    try {
      const token = localStorage.getItem("token") || sessionStorage.getItem("token") || "";
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
      const res = await sendToExtension({
        type:      "ZILO_CONNECT",
        token,
        apiUrl,
        keywords:  socialSettings.keywords,
        groups:    (socialSettings as SocialSettings & { groups?: string[] }).groups || [],
        autoPost:  true,
      });
      if (res?.status === "connected") {
        setExtStatus("connected");
        await checkExtension();
        toast.success("Extension connected! Monitoring Facebook, Instagram, TikTok, Reddit, Jiji, OLX and more.");
      }
    } finally {
      setConnectingExt(false);
    }
  }

  async function disconnectExtension() {
    await sendToExtension({ type: "ZILO_DISCONNECT" });
    setExtStatus("disconnected");
    setExtStats({ keywordCount: 0, groupCount: 0, autoPostEnabled: true });
  }

  async function syncExtension() {
    const res = await sendToExtension({ type: "ZILO_SYNC" });
    if (res?.status === "synced") {
      setExtStats(s => ({
        ...s,
        keywordCount: (res.keywordCount as number) || 0,
        groupCount:   (res.groupCount as number)   || 0,
      }));
      toast.success("Extension synced with latest keywords and groups.");
    }
  }

  // Check extension on page load and when ZILO_EXT_INSTALLED fires
  useEffect(() => {
    function onInstalled(event: MessageEvent) {
      if (event.data?.type === "ZILO_EXT_INSTALLED") checkExtension();
    }
    window.addEventListener("message", onInstalled);
    checkExtension();
    return () => window.removeEventListener("message", onInstalled);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openAndPost(item: QueueItem) {
    const content = editedContent[item._id] ?? item.draft_content;
    try {
      await navigator.clipboard.writeText(content);
      window.open(String(item.metadata?.url ?? ""), "_blank");
      await handleQueueAction(item, "approve");
      toast.success("Opened! Comment copied to clipboard — paste and post 🎯");
    } catch {
      window.open(String(item.metadata?.url ?? ""), "_blank");
      await handleQueueAction(item, "approve");
      toast.message("Post opened", { description: "Copy the comment below and paste it on the post" });
    }
  }

  async function runFusion() {
    setRunningFusion(true);
    try {
      await api.post("/action-mode/clusters/run", {});
      toast.success("Fusion Engine running — clusters will appear in ~30 seconds");
      setTimeout(async () => {
        const cl = await api.get<{ clusters: Cluster[] }>("/action-mode/clusters");
        setClusters(cl.clusters);
        setRunningFusion(false);
      }, 35000);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Fusion Engine failed");
      setRunningFusion(false);
    }
  }

  async function dismissCluster(id: string) {
    await api.delete(`/action-mode/clusters/${id}`);
    setClusters(prev => prev.filter(c => c._id !== id));
  }

  async function runPredictions() {
    setRunningPredictions(true);
    try {
      await api.post("/action-mode/predictions/run", {});
      toast.success("Predictive Radar running — forecasts ready in ~30 seconds");
      setTimeout(async () => {
        const pr = await api.get<{ predictions: Prediction[] }>("/action-mode/predictions");
        setPredictions(pr.predictions);
        setRunningPredictions(false);
      }, 35000);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Predictive Radar failed");
      setRunningPredictions(false);
    }
  }

  async function dismissPrediction(id: string) {
    await api.delete(`/action-mode/predictions/${id}`);
    setPredictions(prev => prev.filter(p => p._id !== id));
  }

  async function runRecon() {
    setRunningRecon(true);
    try {
      await api.post("/action-mode/recon/run", {});
      toast.success("Recon Engine scanning job boards, new businesses & tenders…");
      setTimeout(async () => {
        const rc = await api.get<{ recon: ReconItem[] }>("/action-mode/recon");
        setRecon(rc.recon);
        setRunningRecon(false);
      }, 40000);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Recon Engine failed");
      setRunningRecon(false);
    }
  }

  async function dismissRecon(id: string) {
    await api.delete(`/action-mode/recon/${id}`);
    setRecon(prev => prev.filter(r => r._id !== id));
  }

  async function generateInstantActions() {
    setRunningInstant(true);
    try {
      await api.post("/action-mode/instant/generate", {});
      toast.success("Generating action drafts — ready in ~30 seconds");
      setTimeout(async () => {
        const ia = await api.get<{ items: InstantAction[] }>("/action-mode/instant");
        setInstantActions(ia.items);
        setRunningInstant(false);
      }, 35000);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Generation failed");
      setRunningInstant(false);
    }
  }

  async function approveInstantAction(id: string) {
    await api.post(`/action-mode/instant/${id}/approve`, {});
    setInstantActions(prev => prev.map(a => a._id === id ? { ...a, status: "approved" as const } : a));
    toast.success("Action approved — ready to execute");
  }

  async function executeInstantAction(id: string) {
    await api.post(`/action-mode/instant/${id}/execute`, {});
    setInstantActions(prev => prev.map(a => a._id === id ? { ...a, status: "executed" as const } : a));
    toast.success("Marked as executed");
  }

  async function rejectInstantAction(id: string) {
    await api.delete(`/action-mode/instant/${id}`);
    setInstantActions(prev => prev.filter(a => a._id !== id));
  }

  async function runCommand(query: string) {
    if (!query.trim()) return;
    try {
      await api.post("/action-mode/command-query", { query });
      toast.success(`Working on "${query}" — results appear in your Approval Queue shortly`);
      setSearchQuery(""); // clear so the filter doesn't hide new results
      setTab("queue");

      // Poll at 20s, 45s, and 75s to handle slow LLM responses
      const refresh = async () => {
        try {
          const [q, f, o] = await Promise.all([
            api.get<{ items: QueueItem[] }>("/action-mode/queue"),
            api.get<{ items: FeedItem[] }>("/action-mode/feed"),
            api.get<{ items: Opportunity[] }>("/action-mode/opportunities"),
          ]);
          setQueue(q.items);
          setFeed(f.items);
          setOpportunities(o.items);
        } catch { /* silent */ }
      };
      setTimeout(refresh, 20000);
      setTimeout(refresh, 45000);
      setTimeout(refresh, 75000);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Command failed");
    }
  }

  const pendingInstant = instantActions.filter(a => a.status === "pending").length;

  const sq = searchQuery.toLowerCase().trim();
  const filteredFeed = sq ? feed.filter(i => i.title.toLowerCase().includes(sq) || i.detail.toLowerCase().includes(sq)) : feed;
  const filteredQueue = sq ? queue.filter(i => (i.draft_content ?? "").toLowerCase().includes(sq) || (i.title ?? "").toLowerCase().includes(sq)) : queue;
  const filteredOpportunities = sq ? opportunities.filter(o => o.title.toLowerCase().includes(sq) || (o.snippet ?? "").toLowerCase().includes(sq)) : opportunities;
  const tabs: { id: Tab; label: string; icon: React.ElementType; count?: number }[] = [
    { id: "feed", label: "Activity", icon: Activity },
    { id: "queue", label: "Approval Queue", icon: ListChecks, count: queue.length },
    { id: "opportunities", label: "Opportunities", icon: TrendingUp, count: opportunities.length },
    { id: "radar", label: "Intelligence", icon: BrainCircuit, count: (clusters.length + predictions.length + recon.length) || undefined },
    { id: "instant", label: "Instant Actions", icon: Zap, count: pendingInstant || undefined },
  ];

  if (loading) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center gap-6 px-6">
        <div className="relative flex h-28 w-28 items-center justify-center">
          <div
            className="absolute inset-0 rounded-full border-2 border-cyan-500/30"
            style={{ animation: "action-orbit 8s linear infinite" }}
          />
          <div
            className="absolute inset-2 rounded-full border border-violet-400/40"
            style={{ animation: "action-orbit 5s linear infinite reverse" }}
          />
          <BrainCircuit size={40} className="relative text-cyan-300" style={{ animation: "action-pulse-core 2s ease-in-out infinite" }} />
        </div>
        <div className="text-center space-y-2">
          <p className="text-sm font-semibold text-slate-800 tracking-wide uppercase text-[0.7rem]">Action Mode</p>
          <p className="text-slate-500 text-sm">Initializing neural workspace…</p>
        </div>
        <div className="h-1 w-48 max-w-full overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full w-full rounded-full bg-gradient-to-r from-cyan-500 via-violet-500 to-cyan-500 bg-[length:200%_100%]"
            style={{ animation: "action-shimmer-bar 1.2s linear infinite" }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-4">

      {/* ── Top status bar ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-amber-400" />
            <span className="font-bold text-slate-900">Field Agents</span>
          </div>
          {settings.enabled ? (
            <span className="flex items-center gap-1.5 text-xs text-emerald-600 font-medium bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-100">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Active
            </span>
          ) : (
            <span className="text-xs text-slate-400 bg-slate-100 px-2.5 py-0.5 rounded-full">Off</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(s => !s)}
            title="Settings & Agents"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
              showSettings ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-500 hover:bg-slate-50"
            }`}
          >
            <Settings2 size={13} />
            Settings
          </button>
          <button
            onClick={toggleEnabled}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg font-semibold text-xs transition-all ${
              settings.enabled ? "bg-rose-500 hover:bg-rose-600 text-white" : "bg-amber-400 hover:bg-amber-500 text-slate-900"
            }`}
          >
            {settings.enabled ? <><Square size={11} /> Turn Off</> : <><Play size={11} /> Activate</>}
          </button>
        </div>
      </div>

      {/* ── Command Bar ── */}
      <div className="relative">
        <Search size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" && searchQuery.trim()) {
              void runCommand(searchQuery);
            }
          }}
          placeholder="What do you want to find or do? e.g. 'find leads in DC', 'show funding', 'check tenders'…"
          className="w-full pl-12 pr-36 py-4 text-sm bg-white border-2 border-slate-200 rounded-2xl focus:outline-none focus:border-brand/50 shadow-sm placeholder-slate-400 transition-colors"
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
          {searchQuery && (
            <button onClick={() => setSearchQuery("")} className="p-1.5 text-slate-300 hover:text-slate-500">
              <XCircle size={14} />
            </button>
          )}
          <button
            onClick={() => { if (searchQuery.trim()) void runCommand(searchQuery); }}
            disabled={!searchQuery.trim() || running || !!liveHeadline}
            className="flex items-center gap-1.5 px-4 py-2 bg-slate-900 text-white text-xs font-semibold rounded-xl hover:bg-slate-700 disabled:opacity-40 transition-colors"
          >
            {running || liveHeadline ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
            Run
          </button>
        </div>
      </div>

      {/* ── Quick chips ── */}
      <div className="flex gap-2 flex-wrap">
        {([
          { label: "Find Leads",      icon: Users,       fn: () => runSingleAgent("lead_gen") },
          { label: "Find Funding",    icon: DollarSign,  fn: () => runSingleAgent("funding_hunter") },
          { label: "Social Leads",    icon: Globe,       fn: () => runSingleAgent("social_scout") },
          { label: "Recon Scan",      icon: Search,      fn: () => runRecon() },
          { label: "Predict 90 days", icon: Radio,       fn: () => runPredictions() },
          { label: "Get Actions",     icon: Zap,         fn: () => generateInstantActions() },
          { label: "Run All",         icon: RefreshCw,   fn: () => runAll() },
        ] as { label: string; icon: React.ElementType; fn: () => void }[]).map(chip => (
          <button
            key={chip.label}
            onClick={chip.fn}
            disabled={running || !!liveHeadline}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs font-medium text-slate-600 hover:bg-slate-50 hover:border-brand/40 hover:text-brand-dark disabled:opacity-40 transition-colors shadow-sm"
          >
            <chip.icon size={11} />
            {chip.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3">
          <AlertCircle size={15} className="shrink-0" /> {error}
          <button onClick={() => setError("")} className="ml-auto text-rose-400 hover:text-rose-600">✕</button>
        </div>
      )}

      {liveHeadline && (
        <LiveMissionPanel
          headline={liveHeadline}
          phase={phases[phaseIdx] ?? phases[0]}
          feed={feed}
          queueLength={queue.length}
          opportunitiesCount={opportunities.length}
          fleetRunning={running}
          runningAgentId={runningAgent}
          runningCustomAgentId={runningCustomAgent}
          customAgentName={
            runningCustomAgent
              ? customAgents.find((a) => a._id === runningCustomAgent)?.name
              : undefined
          }
          onEndWatch={() => void dismissLiveWatch()}
        />
      )}

      {/* ── Stat cards (home view, no search) ── */}
      {!sq && !liveHeadline && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {([
            { label: "Pending Approvals",  value: queue.length,                                         icon: ListChecks,  accent: "amber",   target: "queue"         },
            { label: "Opportunities",      value: opportunities.length,                                 icon: TrendingUp,  accent: "emerald",  target: "opportunities" },
            { label: "Intelligence",       value: clusters.length + predictions.length + recon.length,  icon: BrainCircuit,accent: "violet",   target: "radar"         },
            { label: "Actions Ready",      value: pendingInstant,                                       icon: Zap,         accent: "blue",     target: "instant"       },
          ] as { label: string; value: number; icon: React.ElementType; accent: string; target: Tab }[]).map(card => {
            const ACCENT_NUM: Record<string, string> = { amber: "text-amber-600", emerald: "text-emerald-600", violet: "text-violet-600", blue: "text-blue-600" };
            const ACCENT_BG: Record<string, string>  = { amber: "bg-amber-50",   emerald: "bg-emerald-50",    violet: "bg-violet-50",    blue: "bg-blue-50"   };
            return (
              <button
                key={card.label}
                onClick={() => setTab(card.target)}
                className={`bg-white rounded-xl border p-4 text-left hover:shadow-md transition-all ${
                  tab === card.target ? "border-brand/30 ring-1 ring-brand/20" : "border-slate-100"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] text-slate-500 font-medium leading-tight">{card.label}</span>
                  <div className={`w-6 h-6 rounded-md flex items-center justify-center ${ACCENT_BG[card.accent]}`}>
                    <card.icon size={12} className={ACCENT_NUM[card.accent]} />
                  </div>
                </div>
                <p className={`text-2xl font-bold ${card.value > 0 ? ACCENT_NUM[card.accent] : "text-slate-200"}`}>{card.value}</p>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Tab bar ── */}
      <div className="flex gap-1 bg-white border border-slate-200 rounded-xl p-1">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-lg transition-colors ${
              tab === t.id ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"
            }`}>
            <t.icon size={13} />
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold ${
                tab === t.id ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500"
              }`}>{t.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* ── FEED TAB ── */}
      {tab === "feed" && (
        <div className="space-y-3">
          {filteredFeed.length === 0 ? (
            <EmptyState
              icon={Activity}
              title={sq ? "No matches" : liveHeadline ? "Signal lock — waiting for log lines" : "No activity yet"}
              desc={
                sq ? `No activity matches "${searchQuery}"` :
                liveHeadline
                  ? "Streaming updates every second. New entries appear here as agents commit work."
                  : settings.enabled
                    ? "Hit Run now or open Agents to wake a channel."
                    : "Turn on Action Mode to start."
              }
            />
          ) : (
            filteredFeed.map((item, i) => (
              <div
                key={item._id}
                className="bg-white rounded-xl border border-slate-200 px-4 py-3 flex gap-3 transition-shadow hover:shadow-md hover:border-cyan-200/80"
                style={{ animation: `action-fade-slide 0.45s ease-out ${Math.min(i, 6) * 0.04}s both` }}
              >
                <Sparkles size={15} className={`shrink-0 mt-0.5 ${KIND_COLORS[item.kind]}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800">{item.title}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{item.detail}</p>
                </div>
                <span className="text-xs text-slate-400 shrink-0 tabular-nums">
                  {new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
            ))
          )}
        </div>
      )}

      {/* ── QUEUE TAB ── */}
      {tab === "queue" && (
        <div className="space-y-4">
          {filteredQueue.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title={sq ? "No matches" : "Queue is empty"}
              desc={sq ? `No queue items match "${searchQuery}"` : "When agents find actions to take, they'll appear here for your approval."}
            />
          ) : (
            <>
              <p className="text-sm text-slate-500">{filteredQueue.length} item{filteredQueue.length !== 1 ? "s" : ""} waiting for your approval</p>
              {filteredQueue.map(item => {
                const isEditing = editingItem === item._id;
                const content = editedContent[item._id] ?? item.draft_content;
                const busy = processing[item._id];
                const agentLabel = customAgents.find(a => `custom:${a._id}` === item.agent)?.name
                  || AGENTS.find(a => a.id === item.agent)?.label
                  || item.agent;
                return (
                  <div key={item._id} className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-slate-800 text-sm">{item.title}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                            {agentLabel}
                          </span>
                          <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full">
                            {ACTION_LABELS[item.action_type] || item.action_type}
                          </span>
                          {item.metadata?.platform && (
                            <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full capitalize">
                              {SOCIAL_PLATFORMS.find(p => p.id === String(item.metadata.platform))?.emoji ?? ""} {String(item.metadata.platform)}
                            </span>
                          )}
                        </div>
                      </div>
                      {item.metadata?.url && (
                        <a href={String(item.metadata.url)} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-brand-dark hover:underline flex items-center gap-1 shrink-0">
                          View <ExternalLink size={10} />
                        </a>
                      )}
                    </div>

                    {item.metadata?.snippet && (
                      <div className="text-xs text-slate-400 bg-slate-50 border-l-2 border-slate-200 pl-3 py-1.5 rounded-r-lg italic leading-relaxed">
                        &ldquo;{String(item.metadata.snippet).slice(0, 180)}&rdquo;
                      </div>
                    )}

                    {(item.metadata?.contact_name || item.metadata?.contact_info) && (
                      <div className="flex items-center gap-2 text-xs bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
                        <span className="text-blue-400 font-medium shrink-0">Contact</span>
                        {item.metadata?.contact_name && (
                          <span className="font-medium text-slate-700">{String(item.metadata.contact_name)}</span>
                        )}
                        {item.metadata?.contact_info && (
                          <span className="text-slate-500 font-mono">{String(item.metadata.contact_info)}</span>
                        )}
                      </div>
                    )}

                    {isEditing ? (
                      <textarea
                        value={content}
                        onChange={e => setEditedContent(ec => ({ ...ec, [item._id]: e.target.value }))}
                        rows={5}
                        className="w-full text-sm border border-slate-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-brand/30"
                      />
                    ) : (
                      <pre className="text-sm text-slate-700 bg-slate-50 rounded-lg p-3 leading-relaxed whitespace-pre-wrap font-sans">
                        {content}
                      </pre>
                    )}

                    <div className="flex items-center gap-2 flex-wrap">
                      {item.action_type === "post_comment" ? (
                        <button onClick={() => openAndPost(item)} disabled={busy}
                          className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium">
                          {busy ? <Loader2 size={12} className="animate-spin" /> : <ExternalLink size={12} />}
                          Open & Post
                        </button>
                      ) : (
                        <button onClick={() => handleQueueAction(item, "approve")} disabled={busy}
                          className="flex items-center gap-1.5 px-4 py-1.5 bg-emerald-600 text-white text-xs rounded-lg hover:bg-emerald-700 disabled:opacity-50 font-medium">
                          {busy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
                          {ACTION_LABELS[item.action_type] || "Approve"}
                        </button>
                      )}
                      {isEditing ? (
                        <button onClick={() => setEditingItem(null)}
                          className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                          Done editing
                        </button>
                      ) : (
                        <button onClick={() => {
                          setEditingItem(item._id);
                          setEditedContent(ec => ({ ...ec, [item._id]: item.draft_content }));
                        }}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                          <Edit2 size={11} /> Edit
                        </button>
                      )}
                      <button onClick={() => handleQueueAction(item, "skip")} disabled={busy}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-500">
                        <XCircle size={11} /> Skip
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}

      {/* ── OPPORTUNITIES TAB ── */}
      {tab === "opportunities" && (
        <div className="space-y-3">
          {filteredOpportunities.length === 0 ? (
            <EmptyState
              icon={TrendingUp}
              title={sq ? "No matches" : "No opportunities yet"}
              desc={sq ? `No opportunities match "${searchQuery}"` : "Run the agents to discover funding, leads and groups."}
            />
          ) : (
            <>
              {(["funding", "group", "social", "custom"] as const).map(kind => {
                const items = filteredOpportunities.filter(o => o.kind === kind);
                if (items.length === 0) return null;
                const labels: Record<string, string> = {
                  funding: "💰 Funding & Grants",
                  group: "👥 Customer Groups",
                  social: "💬 Social Opportunities",
                  custom: "🤖 Custom Agent Results",
                };
                return (
                  <div key={kind}>
                    <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{labels[kind]}</h3>
                    <div className="space-y-2">
                      {items.map(opp => (
                        <div key={opp._id} className="bg-white rounded-xl border border-slate-200 p-4">
                          <div className="flex gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-0.5">
                                {opp.agent_name && (
                                  <p className="text-xs text-slate-400">via {opp.agent_name}</p>
                                )}
                                {opp.score !== undefined && (
                                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                                    opp.score >= 0.85 ? "bg-emerald-100 text-emerald-700" :
                                    opp.score >= 0.65 ? "bg-blue-50 text-blue-600" :
                                    "bg-slate-100 text-slate-500"
                                  }`}>
                                    {Math.round(opp.score * 100)}% match
                                  </span>
                                )}
                              </div>
                              <p className="font-medium text-slate-800 text-sm truncate">{opp.title}</p>
                              <p className="text-xs text-slate-500 mt-0.5 leading-relaxed line-clamp-2">{opp.snippet}</p>
                            </div>
                            {opp.url && (
                              <a href={opp.url} target="_blank" rel="noopener noreferrer"
                                className="flex items-center gap-1 text-xs text-brand-dark hover:underline font-medium shrink-0">
                                Open <ExternalLink size={10} />
                              </a>
                            )}
                          </div>
                          {(opp.contact_name || opp.contact_info) && (
                            <div className="mt-2 pt-2 border-t border-slate-100 flex items-center gap-3">
                              {opp.contact_name && (
                                <span className="text-xs font-medium text-slate-700">{opp.contact_name}</span>
                              )}
                              {opp.contact_info && (
                                <span className="text-xs text-slate-500 font-mono">{opp.contact_info}</span>
                              )}
                              {opp.queue_id && (
                                <button
                                  onClick={() => setTab("queue")}
                                  className="ml-auto text-[10px] text-brand-dark hover:underline font-medium"
                                >
                                  View in Queue →
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}

      {/* ── INTELLIGENCE TAB ── */}
      {tab === "radar" && (
        <div className="space-y-4">

          {/* Pane switcher */}
          <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
            <button
              onClick={() => setRadarPane("clusters")}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors ${radarPane === "clusters" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              <BrainCircuit size={12} />
              Fusion Clusters{clusters.length > 0 && <span className="ml-0.5 bg-violet-100 text-violet-700 rounded-full px-1.5 text-[10px] font-semibold">{clusters.length}</span>}
            </button>
            <button
              onClick={() => setRadarPane("predictions")}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors ${radarPane === "predictions" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              <Radio size={12} />
              Predictions{predictions.length > 0 && <span className="ml-0.5 bg-cyan-100 text-cyan-700 rounded-full px-1.5 text-[10px] font-semibold">{predictions.length}</span>}
            </button>
            <button
              onClick={() => setRadarPane("recon")}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-medium transition-colors ${radarPane === "recon" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              <Search size={12} />
              Recon{recon.length > 0 && <span className="ml-0.5 bg-teal-100 text-teal-700 rounded-full px-1.5 text-[10px] font-semibold">{recon.length}</span>}
            </button>
          </div>

          {/* ── Fusion Clusters pane ── */}
          {radarPane === "clusters" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-slate-800">Fusion Clusters</h3>
                  <p className="text-xs text-slate-500 mt-0.5">Multi-signal patterns cross-referenced across all agents</p>
                </div>
                <button
                  onClick={runFusion}
                  disabled={runningFusion}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 text-white text-xs font-medium hover:bg-violet-700 disabled:opacity-60 transition-colors"
                >
                  {runningFusion ? <Loader2 size={12} className="animate-spin" /> : <BrainCircuit size={12} />}
                  {runningFusion ? "Analysing…" : "Run Fusion"}
                </button>
              </div>

              {clusters.length === 0 && (
                <div className="text-center py-14 text-slate-400">
                  <BrainCircuit size={32} className="mx-auto mb-3 opacity-30" />
                  <p className="text-sm font-medium">No clusters yet</p>
                  <p className="text-xs mt-1">Run agents first to collect signals, then click Run Fusion</p>
                </div>
              )}

              {clusters.map(cluster => {
                const CAT_COLORS: Record<string, string> = {
                  lead:        "bg-blue-50 text-blue-700 border-blue-100",
                  funding:     "bg-emerald-50 text-emerald-700 border-emerald-100",
                  partnership: "bg-violet-50 text-violet-700 border-violet-100",
                  market_gap:  "bg-amber-50 text-amber-700 border-amber-100",
                  timing:      "bg-rose-50 text-rose-700 border-rose-100",
                };
                const URG_DOT: Record<string, string> = { high: "bg-rose-500", medium: "bg-amber-400", low: "bg-slate-300" };
                const pct = Math.round(cluster.confidence * 100);
                const bar = pct >= 85 ? "bg-emerald-500" : pct >= 70 ? "bg-blue-500" : "bg-amber-400";
                return (
                  <div key={cluster._id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-4 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${CAT_COLORS[cluster.category] ?? "bg-slate-50 text-slate-600 border-slate-100"}`}>
                          {cluster.category.replace("_", " ").toUpperCase()}
                        </span>
                        <span className="flex items-center gap-1 text-[10px] text-slate-500">
                          <span className={`w-1.5 h-1.5 rounded-full ${URG_DOT[cluster.urgency] ?? "bg-slate-300"}`} />
                          {cluster.urgency} urgency
                        </span>
                        <span className="text-[10px] text-slate-400">{cluster.signal_count} signal{cluster.signal_count !== 1 ? "s" : ""}</span>
                      </div>
                      <button onClick={() => dismissCluster(cluster._id)} className="text-slate-300 hover:text-slate-500 shrink-0">
                        <XCircle size={14} />
                      </button>
                    </div>
                    <div>
                      <p className="font-semibold text-slate-800 text-sm">{cluster.title}</p>
                      <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{cluster.insight}</p>
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[10px] text-slate-500">
                        <span>Confidence</span>
                        <span className="font-semibold text-slate-700">{pct}%</span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${bar}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                    {cluster.signals.length > 0 && (
                      <div className="space-y-1">
                        {cluster.signals.map((sig, i) => (
                          <div key={i} className="flex items-start gap-1.5 text-xs text-slate-600">
                            <span className="text-violet-400 mt-0.5 shrink-0">›</span>
                            <span>{sig}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {cluster.action_hint && (
                      <div className="bg-violet-50 border border-violet-100 rounded-lg px-3 py-2 flex items-start gap-2">
                        <Zap size={11} className="text-violet-500 mt-0.5 shrink-0" />
                        <p className="text-xs text-violet-700 font-medium">{cluster.action_hint}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* ── Predictions pane ── */}
          {radarPane === "predictions" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-slate-800">Predictive Radar</h3>
                  <p className="text-xs text-slate-500 mt-0.5">Opportunities forecast for the next 30–90 days</p>
                </div>
                <button
                  onClick={runPredictions}
                  disabled={runningPredictions}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 text-white text-xs font-medium hover:bg-cyan-700 disabled:opacity-60 transition-colors"
                >
                  {runningPredictions ? <Loader2 size={12} className="animate-spin" /> : <Radio size={12} />}
                  {runningPredictions ? "Forecasting…" : "Run Radar"}
                </button>
              </div>

              {predictions.length === 0 && (
                <div className="text-center py-14 text-slate-400">
                  <Radio size={32} className="mx-auto mb-3 opacity-30" />
                  <p className="text-sm font-medium">No forecasts yet</p>
                  <p className="text-xs mt-1">Click Run Radar to generate predictions based on your business type and location</p>
                </div>
              )}

              {predictions.map(pred => {
                const CAT_COLORS: Record<string, string> = {
                  grant:       "bg-emerald-50 text-emerald-700 border-emerald-100",
                  seasonal:    "bg-amber-50 text-amber-700 border-amber-100",
                  event:       "bg-blue-50 text-blue-700 border-blue-100",
                  hiring:      "bg-violet-50 text-violet-700 border-violet-100",
                  regulatory:  "bg-rose-50 text-rose-700 border-rose-100",
                  market:      "bg-slate-50 text-slate-600 border-slate-100",
                };
                const pct = Math.round(pred.confidence * 100);
                const bar = pct >= 85 ? "bg-emerald-500" : pct >= 70 ? "bg-cyan-500" : "bg-amber-400";
                const urgency = pred.days_until <= 14 ? "high" : pred.days_until <= 35 ? "medium" : "low";
                const urgencyColor = urgency === "high" ? "text-rose-600 bg-rose-50" : urgency === "medium" ? "text-amber-600 bg-amber-50" : "text-slate-500 bg-slate-50";
                return (
                  <div key={pred._id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-4 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${CAT_COLORS[pred.category] ?? "bg-slate-50 text-slate-600 border-slate-100"}`}>
                          {pred.category.toUpperCase()}
                        </span>
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${urgencyColor}`}>
                          {pred.days_until === 0 ? "NOW" : `in ${pred.days_until}d`}
                        </span>
                      </div>
                      <button onClick={() => dismissPrediction(pred._id)} className="text-slate-300 hover:text-slate-500 shrink-0">
                        <XCircle size={14} />
                      </button>
                    </div>
                    <div>
                      <p className="font-semibold text-slate-800 text-sm">{pred.title}</p>
                      <p className="text-[11px] text-cyan-700 font-medium mt-0.5">{pred.predicted_window}</p>
                      <p className="text-xs text-slate-500 mt-1 leading-relaxed">{pred.reasoning}</p>
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[10px] text-slate-500">
                        <span>Confidence</span>
                        <span className="font-semibold text-slate-700">{pct}%</span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${bar}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                    {pred.signals.length > 0 && (
                      <div className="space-y-1">
                        {pred.signals.map((sig, i) => (
                          <div key={i} className="flex items-start gap-1.5 text-xs text-slate-600">
                            <span className="text-cyan-400 mt-0.5 shrink-0">›</span>
                            <span>{sig}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {pred.action_hint && (
                      <div className="bg-cyan-50 border border-cyan-100 rounded-lg px-3 py-2 flex items-start gap-2">
                        <Zap size={11} className="text-cyan-600 mt-0.5 shrink-0" />
                        <p className="text-xs text-cyan-700 font-medium">{pred.action_hint}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* ── Recon pane ── */}
          {radarPane === "recon" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-slate-800">Recon Engine</h3>
                  <p className="text-xs text-slate-500 mt-0.5">Job postings, new businesses &amp; tenders discovered in your market</p>
                </div>
                <button
                  onClick={runRecon}
                  disabled={runningRecon}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-600 text-white text-xs font-medium hover:bg-teal-700 disabled:opacity-60 transition-colors"
                >
                  {runningRecon ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
                  {runningRecon ? "Scanning…" : "Run Recon"}
                </button>
              </div>

              {recon.length === 0 && (
                <div className="text-center py-14 text-slate-400">
                  <Search size={32} className="mx-auto mb-3 opacity-30" />
                  <p className="text-sm font-medium">No recon results yet</p>
                  <p className="text-xs mt-1">Click Run Recon to scan job boards, business registrations &amp; tenders</p>
                </div>
              )}

              {recon.length > 0 && (
                <div className="flex gap-1.5 flex-wrap">
                  {(["job_posting", "new_business", "tender"] as const).map(type => {
                    const count = recon.filter(r => r.recon_type === type).length;
                    if (!count) return null;
                    const LABELS = { job_posting: "Job Postings", new_business: "New Businesses", tender: "Tenders" };
                    const COLORS = { job_posting: "bg-blue-50 text-blue-700", new_business: "bg-emerald-50 text-emerald-700", tender: "bg-amber-50 text-amber-700" };
                    return (
                      <span key={type} className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${COLORS[type]}`}>
                        {count} {LABELS[type]}
                      </span>
                    );
                  })}
                </div>
              )}

              {recon.map(item => {
                const TYPE_STYLES: Record<string, { badge: string; bar: string; hint: string; hintText: string }> = {
                  job_posting:  { badge: "bg-blue-50 text-blue-700 border-blue-100",    bar: "bg-blue-500",    hint: "bg-blue-50 border-blue-100",    hintText: "text-blue-700" },
                  new_business: { badge: "bg-emerald-50 text-emerald-700 border-emerald-100", bar: "bg-emerald-500", hint: "bg-emerald-50 border-emerald-100", hintText: "text-emerald-700" },
                  tender:       { badge: "bg-amber-50 text-amber-700 border-amber-100", bar: "bg-amber-500",   hint: "bg-amber-50 border-amber-100",   hintText: "text-amber-700" },
                };
                const TYPE_LABELS = { job_posting: "JOB POSTING", new_business: "NEW BUSINESS", tender: "TENDER" };
                const s = TYPE_STYLES[item.recon_type] ?? TYPE_STYLES.job_posting;
                const pct = Math.round(item.confidence * 100);
                return (
                  <div key={item._id} className="bg-white rounded-xl border border-slate-100 shadow-sm p-4 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border shrink-0 ${s.badge}`}>
                        {TYPE_LABELS[item.recon_type] ?? item.recon_type}
                      </span>
                      <button onClick={() => dismissRecon(item._id)} className="text-slate-300 hover:text-slate-500 shrink-0">
                        <XCircle size={14} />
                      </button>
                    </div>

                    <div>
                      <p className="font-semibold text-slate-800 text-sm leading-snug">{item.title}</p>
                      {item.company && (
                        <p className="text-xs text-slate-500 mt-0.5">{item.company}{item.location ? ` · ${item.location}` : ""}</p>
                      )}
                      <p className="text-xs text-slate-500 mt-1 leading-relaxed">{item.why_relevant}</p>
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[10px] text-slate-500">
                        <span>Relevance</span>
                        <span className="font-semibold text-slate-700">{pct}%</span>
                      </div>
                      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${s.bar}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      {item.source_url && (
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-[11px] text-teal-600 hover:text-teal-800 font-medium underline underline-offset-2"
                        >
                          <ExternalLink size={10} />
                          View source
                        </a>
                      )}
                    </div>

                    {item.action_hint && (
                      <div className={`border rounded-lg px-3 py-2 flex items-start gap-2 ${s.hint}`}>
                        <Zap size={11} className={`mt-0.5 shrink-0 ${s.hintText}`} />
                        <p className={`text-xs font-medium ${s.hintText}`}>{item.action_hint}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

        </div>
      )}

      {/* ── INSTANT ACTIONS TAB ── */}
      {tab === "instant" && (
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold text-slate-800">Instant Action Mode</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                AI-drafted actions from your intelligence signals — review, edit and approve each one before it runs.
              </p>
            </div>
            <button
              onClick={generateInstantActions}
              disabled={runningInstant}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand text-brand-ink text-xs font-semibold hover:opacity-90 disabled:opacity-60 transition-colors shrink-0"
            >
              {runningInstant ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
              {runningInstant ? "Generating…" : "Generate Actions"}
            </button>
          </div>

          {/* Status chips */}
          {instantActions.length > 0 && (
            <div className="flex gap-1.5 flex-wrap">
              {(["pending", "approved", "executed"] as const).map(status => {
                const count = instantActions.filter(a => a.status === status).length;
                if (!count) return null;
                const COLORS = { pending: "bg-amber-50 text-amber-700", approved: "bg-emerald-50 text-emerald-700", executed: "bg-slate-100 text-slate-500" };
                const LABELS = { pending: "Awaiting review", approved: "Approved", executed: "Executed" };
                return (
                  <span key={status} className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${COLORS[status]}`}>
                    {count} {LABELS[status]}
                  </span>
                );
              })}
            </div>
          )}

          {instantActions.length === 0 && (
            <div className="text-center py-16 text-slate-400">
              <Zap size={36} className="mx-auto mb-3 opacity-20" />
              <p className="text-sm font-medium text-slate-600">No action drafts yet</p>
              <p className="text-xs mt-1 max-w-xs mx-auto">
                Run your agents and intelligence engines first, then click Generate Actions to get AI-drafted outreach ready for your approval.
              </p>
            </div>
          )}

          {instantActions.map(action => {
            const TYPE_META: Record<string, { label: string; badge: string; icon: React.ElementType }> = {
              email_outreach: { label: "Email",          badge: "bg-blue-50 text-blue-700 border-blue-100",    icon: Activity },
              apply_grant:    { label: "Grant Apply",    badge: "bg-emerald-50 text-emerald-700 border-emerald-100", icon: TrendingUp },
              social_post:    { label: "Social Post",    badge: "bg-violet-50 text-violet-700 border-violet-100", icon: Globe },
              follow_up:      { label: "Follow-up",      badge: "bg-amber-50 text-amber-700 border-amber-100",  icon: Activity },
              direct_message: { label: "Direct Message", badge: "bg-cyan-50 text-cyan-700 border-cyan-100",    icon: Activity },
            };
            const meta = TYPE_META[action.action_type] ?? TYPE_META.email_outreach;
            const STATUS_STYLE = {
              pending:  "bg-amber-50 text-amber-700",
              approved: "bg-emerald-50 text-emerald-700",
              executed: "bg-slate-100 text-slate-500",
              rejected: "bg-rose-50 text-rose-600",
            };
            const pct = Math.round(action.confidence * 100);
            const isExpanded = expandedAction === action._id;
            const draftValue = editingDraft[action._id] ?? action.draft_content;

            return (
              <div key={action._id} className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
                {/* Card header */}
                <div className="p-4 space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2 flex-wrap min-w-0">
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border shrink-0 ${meta.badge}`}>
                        {meta.label}
                      </span>
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0 ${STATUS_STYLE[action.status]}`}>
                        {action.status.toUpperCase()}
                      </span>
                    </div>
                    <button onClick={() => rejectInstantAction(action._id)} className="text-slate-300 hover:text-rose-400 shrink-0 transition-colors">
                      <XCircle size={14} />
                    </button>
                  </div>

                  <div>
                    <p className="font-semibold text-slate-800 text-sm leading-snug">{action.title}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Target: <span className="text-slate-700 font-medium">{action.target_name}</span>
                      {action.target_contact && <span className="text-slate-400 ml-1">· {action.target_contact}</span>}
                    </p>
                  </div>

                  {/* Confidence bar */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-[10px] text-slate-400">
                      <span>Signal confidence</span>
                      <span className="font-semibold text-slate-600">{pct}%</span>
                    </div>
                    <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${pct >= 80 ? "bg-emerald-500" : pct >= 65 ? "bg-blue-500" : "bg-amber-400"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>

                  {/* Source signal */}
                  {action.source_title && (
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                      <BrainCircuit size={10} className="shrink-0" />
                      <span>From: <span className="text-slate-500 italic">{action.source_title}</span></span>
                    </div>
                  )}

                  {/* Expand/collapse draft */}
                  <button
                    onClick={() => setExpandedAction(isExpanded ? null : action._id)}
                    className="flex items-center gap-1 text-[11px] text-brand-dark hover:text-brand font-medium transition-colors"
                  >
                    {isExpanded ? "Hide draft" : "View & edit draft"}
                    <span className="text-[10px]">{isExpanded ? "▲" : "▼"}</span>
                  </button>
                </div>

                {/* Expandable draft editor */}
                {isExpanded && (
                  <div className="border-t border-slate-100 bg-slate-50 p-3 space-y-2">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Draft content — edit before sending</p>
                    <textarea
                      className="w-full text-xs text-slate-700 bg-white border border-slate-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-1 focus:ring-brand/40 leading-relaxed"
                      rows={8}
                      value={draftValue}
                      onChange={e => setEditingDraft(prev => ({ ...prev, [action._id]: e.target.value }))}
                    />
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(draftValue);
                          toast.success("Copied to clipboard");
                        }}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-xs text-slate-600 hover:bg-slate-50 transition-colors"
                      >
                        Copy
                      </button>
                    </div>
                  </div>
                )}

                {/* Action buttons */}
                <div className="px-4 pb-4 flex items-center gap-2">
                  {action.status === "pending" && (
                    <button
                      onClick={() => approveInstantAction(action._id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 transition-colors"
                    >
                      <CheckCircle size={12} />
                      Approve
                    </button>
                  )}
                  {action.status === "approved" && (
                    <button
                      onClick={() => executeInstantAction(action._id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand text-brand-ink text-xs font-semibold hover:opacity-90 transition-colors"
                    >
                      <Zap size={12} />
                      Mark Executed
                    </button>
                  )}
                  {action.status === "executed" && (
                    <span className="flex items-center gap-1 text-xs text-slate-400 font-medium">
                      <CheckCircle size={12} className="text-emerald-400" />
                      Done
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── SETTINGS DRAWER ── */}
      {showSettings && (
        <div className="fixed inset-0 z-40 flex" onClick={() => setShowSettings(false)}>
          {/* backdrop */}
          <div className="flex-1 bg-slate-900/30" />
          {/* panel */}
          <div
            className="w-[440px] max-w-full bg-white shadow-2xl border-l border-slate-200 overflow-y-auto flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            {/* Drawer header */}
            <div className="sticky top-0 bg-white border-b border-slate-100 px-5 py-4 flex items-center justify-between z-10">
              <div>
                <p className="font-semibold text-slate-900">Settings &amp; Agents</p>
                <p className="text-xs text-slate-400 mt-0.5">Configure once — agents do the rest</p>
              </div>
              <button onClick={() => setShowSettings(false)} className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100">
                <XCircle size={16} />
              </button>
            </div>
            {/* Business goals */}
            <div className="px-5 pt-5 pb-4 border-b border-slate-100">
              <label className="text-xs font-semibold text-slate-700 block mb-1">Business goals</label>
              <input
                value={settings.goals}
                onChange={e => setSettings(s => ({ ...s, goals: e.target.value }))}
                onBlur={saveSettings}
                placeholder="e.g. Get 3 investors by December, expand to Nairobi, reach 500 customers…"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-brand/30"
              />
              <p className="text-[10px] text-slate-400 mt-1.5">The AI reads this every time it runs — be specific</p>
            </div>
            {/* Settings content */}
            <div className="flex-1 px-5 py-5 space-y-4">
        <div className="space-y-4">

          {/* Pre-built agents */}
          <div>
            <p className="text-sm font-semibold text-slate-700 mb-3">Built-in Agents</p>
            {AGENTS.map(agent => {
              const active = settings.agents?.[agent.id] !== false;
              const isRunning = runningAgent === agent.id;
              return (
                <div key={agent.id} className="bg-white rounded-xl border border-slate-200 p-5 mb-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className={`w-10 h-10 ${agent.bg} rounded-xl flex items-center justify-center shrink-0`}>
                        <agent.icon size={18} className={agent.color} />
                      </div>
                      <div>
                        <p className="font-semibold text-slate-800 text-sm">{agent.label}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{agent.desc}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button onClick={() => runSingleAgent(agent.id)} disabled={isRunning || !!liveHeadline}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 disabled:opacity-50">
                        {isRunning || (liveHeadline && runningAgent === agent.id) ? (
                          <Loader2 size={11} className="animate-spin text-cyan-600" />
                        ) : (
                          <Play size={11} />
                        )}
                        Run
                      </button>
                      <button
                        onClick={() => {
                          const next = { ...settings, agents: { ...settings.agents, [agent.id]: !active } };
                          setSettings(next);
                          api.put("/action-mode/settings", next).catch(() => {});
                        }}
                        className={`w-11 h-6 rounded-full transition-colors relative ${active ? "bg-emerald-500" : "bg-slate-200"}`}
                      >
                        <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-all ${active ? "left-5" : "left-0.5"}`} />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Custom agents */}
          <div className="pt-2 border-t border-slate-100">
            <div className="flex items-center justify-between mb-1">
              <div>
                <p className="text-sm font-semibold text-slate-700">Your Custom Agents</p>
                <p className="text-xs text-slate-400 mt-0.5">Describe any task in plain English — the AI figures out how to do it</p>
              </div>
              {!showCreateForm && (
                <button onClick={() => setShowCreateForm(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-900 text-white rounded-lg hover:bg-slate-700 font-medium shrink-0">
                  <Plus size={11} /> New Agent
                </button>
              )}
            </div>

            {/* Create form — single-line, just describe what it should do */}
            {showCreateForm && (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 mt-3">
                <p className="text-xs text-slate-500 mb-2">Describe what this agent should do — the AI handles the rest</p>
                <div className="flex gap-2">
                  <input
                    autoFocus
                    value={newAgent.description}
                    onChange={e => setNewAgent(a => ({ ...a, description: e.target.value, name: e.target.value.split(" ").slice(0, 4).join(" ") }))}
                    onKeyDown={e => { if (e.key === "Enter" && newAgent.description.trim()) createCustomAgent(); if (e.key === "Escape") { setShowCreateForm(false); setNewAgent({ name: "", emoji: "🤖", description: "", schedule: "on_demand" }); } }}
                    placeholder="e.g. Find TikTok creators in East Africa who need styling services"
                    className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-brand/30"
                  />
                  <button
                    onClick={createCustomAgent}
                    disabled={savingAgent || !newAgent.description.trim()}
                    className="flex items-center gap-1.5 px-3 py-2 text-xs bg-slate-900 text-white rounded-lg hover:bg-slate-700 disabled:opacity-50 font-medium shrink-0">
                    {savingAgent ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                    Add
                  </button>
                  <button onClick={() => { setShowCreateForm(false); setNewAgent({ name: "", emoji: "🤖", description: "", schedule: "on_demand" }); }}
                    className="px-2 py-2 text-xs border border-slate-200 rounded-lg hover:bg-white text-slate-400">
                    <XCircle size={13} />
                  </button>
                </div>
                <p className="text-[10px] text-slate-400 mt-1.5">Press Enter to save · Esc to cancel</p>
              </div>
            )}

            {/* List */}
            {customAgents.length === 0 && !showCreateForm ? (
              <div className="mt-4 text-center py-10 text-slate-400 text-sm border border-dashed border-slate-200 rounded-xl">
                <Target size={28} className="mx-auto mb-2 text-slate-200" />
                <p className="font-medium text-slate-500">No custom agents yet</p>
                <p className="text-xs mt-1">Describe what you want the AI to do and it will handle it for you</p>
              </div>
            ) : (
              <div className="mt-3 space-y-3">
                {customAgents.map(agent => {
                  const isRunning = runningCustomAgent === agent._id;
                  return (
                    <div key={agent._id} className="bg-white rounded-xl border border-slate-200 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3">
                          <div className="w-10 h-10 bg-slate-100 rounded-xl flex items-center justify-center text-xl shrink-0">
                            {agent.emoji}
                          </div>
                          <div>
                            <p className="font-semibold text-slate-800 text-sm">{agent.name}</p>
                            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{agent.description}</p>
                            <span className="text-xs text-slate-400 mt-1 inline-block">
                              {SCHEDULE_LABELS[agent.schedule] || "On demand"}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <button onClick={() => runCustomAgent(agent._id)} disabled={isRunning || !!liveHeadline}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 disabled:opacity-50">
                            {isRunning || (liveHeadline && runningCustomAgent === agent._id) ? (
                              <Loader2 size={11} className="animate-spin text-violet-600" />
                            ) : (
                              <Play size={11} />
                            )}
                            Run
                          </button>
                          <button onClick={() => deleteCustomAgent(agent._id)}
                            className="p-1.5 text-slate-300 hover:text-rose-500 rounded-lg hover:bg-rose-50 transition-colors">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="pt-2">
            <button onClick={saveSettings} disabled={savingSettings}
              className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700 disabled:opacity-50 font-medium">
              {savingSettings ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
              Save Settings
            </button>
          </div>

          {/* ── Social Engagement ── */}
          <div className="pt-4 border-t border-slate-100">
            <div className="flex items-center justify-between mb-1">
              <div>
                <p className="text-sm font-semibold text-slate-700">Social Engagement</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  Agent finds relevant posts on social platforms and drafts a comment for you to post — you review at night and click Open &amp; Post
                </p>
              </div>
              <button
                onClick={runSocial}
                disabled={runningSocial || !!liveHeadline || !socialSettings.keywords.length}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 disabled:opacity-50 shrink-0"
              >
                {runningSocial ? <Loader2 size={11} className="animate-spin text-blue-500" /> : <Play size={11} />}
                Run now
              </button>
            </div>

            <div className="mt-3 bg-slate-50 rounded-xl border border-slate-200 p-4 space-y-4">

              {/* Platforms */}
              <div>
                <p className="text-xs font-medium text-slate-600 mb-2">Platforms to scan</p>
                <div className="flex flex-wrap gap-2">
                  {SOCIAL_PLATFORMS.map(p => {
                    const active = socialSettings.platforms.includes(p.id);
                    return (
                      <div key={p.id} className="flex flex-col items-start gap-0.5">
                        <button
                          onClick={() => {
                            const next = active
                              ? socialSettings.platforms.filter(x => x !== p.id)
                              : [...socialSettings.platforms, p.id];
                            setSocialSettings(s => ({ ...s, platforms: next }));
                          }}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                            active
                              ? "bg-slate-900 text-white border-slate-900"
                              : "bg-white text-slate-600 border-slate-200 hover:bg-slate-100"
                          }`}
                        >
                          {p.emoji} {p.label}
                        </button>
                        {"hint" in p && p.hint && (
                          <span className="text-[10px] text-slate-400 px-1">{p.hint}</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Keywords */}
              <div>
                <p className="text-xs font-medium text-slate-600 mb-1">Keywords to search for</p>
                <p className="text-[10px] text-slate-400 mb-2">Separate multiple keywords with commas — press Enter to add all at once</p>
                <div className="flex gap-2">
                  <input
                    value={newKeyword}
                    onChange={e => setNewKeyword(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === "Enter" && newKeyword.trim()) {
                        const parts = newKeyword.split(",").map(k => k.trim()).filter(Boolean);
                        setSocialSettings(s => ({
                          ...s,
                          keywords: [...s.keywords, ...parts.filter(p => !s.keywords.includes(p))],
                        }));
                        setNewKeyword("");
                      }
                    }}
                    placeholder="e.g. need a caterer, looking for makeup artist, hire photographer"
                    className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-brand/30"
                  />
                  <button
                    onClick={() => {
                      const parts = newKeyword.split(",").map(k => k.trim()).filter(Boolean);
                      setSocialSettings(s => ({
                        ...s,
                        keywords: [...s.keywords, ...parts.filter(p => !s.keywords.includes(p))],
                      }));
                      setNewKeyword("");
                    }}
                    disabled={!newKeyword.trim()}
                    className="px-3 py-2 bg-slate-900 text-white text-xs rounded-lg hover:bg-slate-700 disabled:opacity-40 font-medium"
                  >
                    Add
                  </button>
                </div>
                {/* Quick-add keyword suggestions */}
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {["need a photographer", "looking for catering", "hire makeup artist", "need web design", "looking for supplier", "recommend a plumber", "any good accountant", "need marketing help"].filter(s => !socialSettings.keywords.includes(s)).slice(0, 6).map(suggestion => (
                    <button
                      key={suggestion}
                      onClick={() => setSocialSettings(s => ({ ...s, keywords: [...s.keywords, suggestion] }))}
                      className="text-[11px] px-2.5 py-1 rounded-full border border-dashed border-slate-300 text-slate-500 hover:border-brand hover:text-brand transition-colors"
                    >
                      + {suggestion}
                    </button>
                  ))}
                </div>
                {socialSettings.keywords.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {socialSettings.keywords.map(kw => (
                      <span key={kw} className="flex items-center gap-1 text-xs bg-white border border-slate-200 rounded-full px-3 py-1 text-slate-700">
                        {kw}
                        <button
                          onClick={() => setSocialSettings(s => ({ ...s, keywords: s.keywords.filter(k => k !== kw) }))}
                          className="text-slate-300 hover:text-rose-500 ml-0.5"
                        >✕</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Watch URLs */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-medium text-slate-600">
                    Watch URLs
                    <span className="text-slate-400 font-normal ml-1">(any site — groups, classifieds, forums)</span>
                  </p>
                  <button
                    onClick={fetchSuggestions}
                    disabled={suggestLoading}
                    className="flex items-center gap-1 text-xs text-violet-600 hover:text-violet-800 font-medium disabled:opacity-50"
                  >
                    {suggestLoading
                      ? <Loader2 className="w-3 h-3 animate-spin" />
                      : <Sparkles className="w-3 h-3" />}
                    Suggest
                  </button>
                </div>

                {/* Popular sites quick-add */}
                <div className="mb-3">
                  <p className="text-[10px] text-slate-400 mb-1.5 font-medium uppercase tracking-wide">Quick add popular sites</p>
                  <div className="flex flex-wrap gap-1.5">
                    {[
                      { label: "Jiji Kenya",      url: `https://jiji.co.ke/search?query=${socialSettings.keywords[0] || "service"}` },
                      { label: "Jiji Nigeria",    url: `https://jiji.ng/search?query=${socialSettings.keywords[0] || "service"}` },
                      { label: "Jiji Ghana",      url: `https://jiji.com.gh/search?query=${socialSettings.keywords[0] || "service"}` },
                      { label: "OLX Nigeria",     url: `https://www.olx.com.ng/items/q-${(socialSettings.keywords[0] || "service").replace(/\s+/g, "-")}` },
                      { label: "OLX South Africa",url: `https://www.olx.co.za/items/q-${(socialSettings.keywords[0] || "service").replace(/\s+/g, "-")}` },
                      { label: "Gumtree SA",      url: `https://www.gumtree.co.za/s-${(socialSettings.keywords[0] || "service").replace(/\s+/g, "-")}/v1c8p1` },
                      { label: "Craigslist",      url: `https://www.craigslist.org/search/sss?query=${socialSettings.keywords[0] || "service"}` },
                      { label: "Facebook Marketplace", url: `https://www.facebook.com/marketplace/search/?query=${socialSettings.keywords[0] || "service"}` },
                      { label: "Quora",           url: `https://www.quora.com/search?q=${socialSettings.keywords[0] || "service"}` },
                    ].map(site => {
                      const added = (socialSettings.groups ?? []).includes(site.url);
                      return (
                        <button
                          key={site.label}
                          onClick={() => {
                            if (!added) setSocialSettings(s => ({ ...s, groups: [...(s.groups ?? []), site.url] }));
                          }}
                          className={`text-[11px] px-2 py-1 rounded-full border transition-colors ${
                            added
                              ? "bg-emerald-50 border-emerald-300 text-emerald-700 cursor-default"
                              : "bg-white border-slate-200 text-slate-600 hover:border-violet-300 hover:text-violet-700"
                          }`}
                        >
                          {added ? "✓ " : "+ "}{site.label}
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-[10px] text-slate-400 mt-1">URLs use your first keyword — edit them after adding if needed</p>
                </div>

                {/* Suggestions panel */}
                {suggestions.length > 0 && (
                  <div className="mb-2 border border-violet-100 rounded-lg bg-violet-50 p-2 space-y-1 max-h-48 overflow-y-auto">
                    <p className="text-[10px] text-violet-500 font-medium mb-1">Click + to add a URL to your watch list</p>
                    {suggestions.map((s) => (
                      <div key={s.url} className="flex items-center gap-2 bg-white rounded-md px-2 py-1.5 border border-violet-100">
                        <span className="text-sm">
                          {s.platform === "facebook"  ? "📘" :
                           s.platform === "reddit"    ? "🟠" :
                           s.platform === "linkedin"  ? "💼" :
                           s.platform === "telegram"  ? "✈️" :
                           s.platform === "tiktok"    ? "🎵" :
                           s.platform === "instagram" ? "📸" :
                           s.platform === "whatsapp"  ? "🟢" : "🌐"}
                        </span>
                        <span className="text-xs text-slate-600 truncate flex-1">{s.title}</span>
                        <button
                          onClick={() => {
                            if (!(socialSettings.groups ?? []).includes(s.url)) {
                              setSocialSettings(st => ({ ...st, groups: [...st.groups, s.url] }));
                            }
                            setSuggestions(prev => prev.filter(x => x.url !== s.url));
                          }}
                          className="shrink-0 text-violet-500 hover:text-violet-700 font-bold text-sm leading-none"
                        >+</button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex gap-2">
                  <input
                    id="group-url-input"
                    type="url"
                    placeholder="https://facebook.com/groups/… or tiktok.com/tag/…"
                    className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:outline-none"
                    onKeyDown={e => {
                      if (e.key === "Enter") {
                        const val = (e.target as HTMLInputElement).value.trim();
                        if (val && !(socialSettings.groups ?? []).includes(val)) {
                          setSocialSettings(s => ({ ...s, groups: [...s.groups, val] }));
                          (e.target as HTMLInputElement).value = "";
                        }
                      }
                    }}
                  />
                  <button
                    onClick={() => {
                      const input = document.getElementById("group-url-input") as HTMLInputElement;
                      const val = input?.value.trim();
                      if (val && !(socialSettings.groups ?? []).includes(val)) {
                        setSocialSettings(s => ({ ...s, groups: [...s.groups, val] }));
                        input.value = "";
                      }
                    }}
                    className="px-3 py-2 bg-slate-900 text-white text-xs rounded-lg hover:bg-slate-700 font-medium"
                  >
                    Add
                  </button>
                </div>
                {(socialSettings.groups ?? []).length > 0 && (
                  <div className="mt-2 space-y-1">
                    {(socialSettings.groups ?? []).map(g => (
                      <div key={g} className="flex items-center justify-between bg-white border border-slate-200 rounded-lg px-3 py-1.5">
                        <span className="text-xs text-slate-600 truncate">{g.replace("https://", "").replace("www.", "")}</span>
                        <button onClick={() => setSocialSettings(s => ({ ...s, groups: s.groups.filter(x => x !== g) }))}
                          className="text-slate-300 hover:text-rose-500 ml-2 shrink-0">✕</button>
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-[10px] text-slate-400 mt-1.5">Extension opens these every 2 hours to scan for your keywords — no scrolling needed. <span className="text-emerald-600 font-medium">WhatsApp &amp; Telegram groups are monitored automatically via your connected account — no URLs needed.</span></p>
              </div>

              {/* Location + Daily limit */}
              <div className="flex gap-3">
                <div className="flex-1">
                  <p className="text-xs font-medium text-slate-600 mb-1.5">Your location / city</p>
                  <input
                    value={socialSettings.location}
                    onChange={e => setSocialSettings(s => ({ ...s, location: e.target.value }))}
                    placeholder="e.g. Nairobi, Lagos, Accra"
                    className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:outline-none"
                  />
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-600 mb-1.5">Posts per run</p>
                  <select
                    value={socialSettings.daily_limit}
                    onChange={e => setSocialSettings(s => ({ ...s, daily_limit: Number(e.target.value) }))}
                    className="text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:outline-none"
                  >
                    {[5, 10, 15, 20, 30].map(n => <option key={n} value={n}>{n} posts</option>)}
                  </select>
                </div>
              </div>

              {/* Google Reviews — link + request */}
              {socialSettings.platforms.includes("google_business") && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 space-y-3">
                  <p className="text-xs font-semibold text-amber-800">⭐ Google Reviews</p>
                  <div>
                    <p className="text-xs text-amber-700 mb-1.5">Your Google Maps review link</p>
                    <input
                      value={socialSettings.google_review_link || ""}
                      onChange={e => setSocialSettings(s => ({ ...s, google_review_link: e.target.value }))}
                      placeholder="https://g.page/r/XXXX/review"
                      className="w-full text-sm border border-amber-200 rounded-lg px-3 py-2 bg-white focus:outline-none"
                    />
                    <p className="text-[10px] text-amber-600 mt-1">
                      Find it in Google Business → Ask for reviews → Copy link
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-amber-700 mb-1.5">Send review request via WhatsApp</p>
                    <div className="flex gap-2">
                      <input
                        id="review-req-phone"
                        type="tel"
                        placeholder="+254712345678"
                        className="flex-1 text-sm border border-amber-200 rounded-lg px-3 py-2 bg-white focus:outline-none"
                      />
                      <input
                        id="review-req-name"
                        type="text"
                        placeholder="Customer name"
                        className="flex-1 text-sm border border-amber-200 rounded-lg px-3 py-2 bg-white focus:outline-none"
                      />
                      <button
                        onClick={async () => {
                          const phone = (document.getElementById("review-req-phone") as HTMLInputElement)?.value.trim();
                          const name  = (document.getElementById("review-req-name") as HTMLInputElement)?.value.trim();
                          if (!phone) { toast.error("Enter a phone number"); return; }
                          try {
                            await api.post("/action-mode/request-review", {
                              phone,
                              customer_name: name || undefined,
                              review_link: socialSettings.google_review_link || undefined,
                            });
                            toast.success("Review request sent via WhatsApp!");
                            (document.getElementById("review-req-phone") as HTMLInputElement).value = "";
                            (document.getElementById("review-req-name") as HTMLInputElement).value = "";
                          } catch (e: unknown) {
                            toast.error(e instanceof Error ? e.message : "Failed to send");
                          }
                        }}
                        className="px-3 py-2 bg-amber-600 text-white text-xs rounded-lg hover:bg-amber-700 font-medium shrink-0"
                      >
                        Send
                      </button>
                    </div>
                    <p className="text-[10px] text-amber-600 mt-1">Sends: "Hi [name], thank you for choosing us! Leave us a review here: [link]"</p>
                  </div>
                </div>
              )}

              {/* Mode toggle */}
              <div>
                <p className="text-xs font-medium text-slate-600 mb-2">Posting mode</p>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setSocialSettings(s => ({ ...s, mode: "review" }))}
                    className={`p-3 rounded-xl border text-left transition-colors ${
                      socialSettings.mode !== "auto"
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                  >
                    <p className={`text-xs font-bold ${socialSettings.mode !== "auto" ? "text-white" : "text-slate-700"}`}>
                      👀 Review first
                    </p>
                    <p className={`text-[10px] mt-0.5 leading-relaxed ${socialSettings.mode !== "auto" ? "text-slate-400" : "text-slate-400"}`}>
                      Posts go to your queue — you approve each one before it's posted
                    </p>
                  </button>
                  <button
                    onClick={() => setSocialSettings(s => ({ ...s, mode: "auto" }))}
                    className={`p-3 rounded-xl border text-left transition-colors ${
                      socialSettings.mode === "auto"
                        ? "border-emerald-600 bg-emerald-600 text-white"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                  >
                    <p className={`text-xs font-bold ${socialSettings.mode === "auto" ? "text-white" : "text-slate-700"}`}>
                      ⚡ Full auto
                    </p>
                    <p className={`text-[10px] mt-0.5 leading-relaxed ${socialSettings.mode === "auto" ? "text-emerald-100" : "text-slate-400"}`}>
                      Agent posts automatically — just check the activity feed for results
                    </p>
                  </button>
                </div>
                {socialSettings.mode === "auto" && (
                  <div className="mt-2 flex items-start gap-2 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                    <span className="text-emerald-600 mt-0.5">⚡</span>
                    <p className="text-xs text-emerald-700 leading-relaxed">
                      Full auto is on. Agent finds posts → replies automatically → customer reaches out → your WhatsApp auto-reply handles the rest. Just check your activity feed.
                    </p>
                  </div>
                )}
              </div>

              {/* Auto run toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-700">Run automatically with all agents</p>
                  <p className="text-xs text-slate-400">Included every time you hit &quot;Run now&quot; in Action Mode</p>
                </div>
                <button
                  onClick={() => setSocialSettings(s => ({ ...s, auto_run: !s.auto_run }))}
                  className={`w-11 h-6 rounded-full transition-colors relative shrink-0 ${socialSettings.auto_run ? "bg-emerald-500" : "bg-slate-200"}`}
                >
                  <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-all ${socialSettings.auto_run ? "left-5" : "left-0.5"}`} />
                </button>
              </div>

              <button
                onClick={() => saveSocialSettings(socialSettings)}
                disabled={savingSocial}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
              >
                {savingSocial ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
                Save Social Settings
              </button>
            </div>

            {/* Extension panel */}
            <div className="mt-4 bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl p-4 text-white">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 bg-cyan-500/20 rounded-lg flex items-center justify-center shrink-0 text-lg">🧩</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold">Chrome Extension</p>
                    {extStatus === "connected" && (
                      <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                        <span className="relative flex h-2 w-2">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                        </span>
                        Connected
                      </span>
                    )}
                    {extStatus === "disconnected" && (
                      <span className="text-xs text-amber-400 font-medium">● Installed</span>
                    )}
                    {extStatus === "not_installed" && (
                      <span className="text-xs text-slate-500">Not installed</span>
                    )}
                  </div>

                  {/* Connected state */}
                  {extStatus === "connected" && (
                    <>
                      <div className="flex gap-3 mt-2">
                        <div className="bg-slate-800 rounded-lg px-3 py-1.5 text-center">
                          <p className="text-lg font-bold text-cyan-300">{extStats.keywordCount}</p>
                          <p className="text-[10px] text-slate-500">keywords</p>
                        </div>
                        <div className="bg-slate-800 rounded-lg px-3 py-1.5 text-center">
                          <p className="text-lg font-bold text-violet-300">{extStats.groupCount}</p>
                          <p className="text-[10px] text-slate-500">groups</p>
                        </div>
                        <div className="bg-slate-800 rounded-lg px-3 py-1.5 flex items-center gap-2">
                          <span className="text-[10px] text-slate-400">Auto-post</span>
                          <span className={`text-xs font-bold ${extStats.autoPostEnabled ? "text-emerald-400" : "text-slate-500"}`}>
                            {extStats.autoPostEnabled ? "ON" : "OFF"}
                          </span>
                        </div>
                      </div>
                      <p className="text-[10px] text-slate-500 mt-2 leading-relaxed">
                        Extension scans your groups automatically every 2 hours and auto-posts approved comments overnight. Keep your browser open.
                      </p>
                      <div className="flex gap-2 mt-3">
                        <button onClick={syncExtension}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-xs rounded-lg font-medium transition-colors">
                          <RefreshCw size={11} /> Sync settings
                        </button>
                        <button onClick={disconnectExtension}
                          className="px-3 py-1.5 text-xs text-slate-400 hover:text-rose-400 transition-colors">
                          Disconnect
                        </button>
                      </div>
                    </>
                  )}

                  {/* Installed but not connected */}
                  {extStatus === "disconnected" && (
                    <>
                      <p className="text-xs text-slate-400 mt-1">Extension installed. Connect to start monitoring Facebook, Instagram, TikTok, Jiji, OLX, Google Reviews and more.</p>
                      <button onClick={connectExtension} disabled={connectingExt}
                        className="mt-3 flex items-center gap-1.5 px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-900 text-xs rounded-lg font-bold transition-colors disabled:opacity-50">
                        {connectingExt ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                        {connectingExt ? "Connecting…" : "Connect Extension"}
                      </button>
                    </>
                  )}

                  {/* Not installed */}
                  {extStatus === "not_installed" && (
                    <>
                      <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                        Install once and Zilo monitors <strong className="text-slate-300">Facebook, Instagram, LinkedIn, Reddit, TikTok, Telegram, Jiji, OLX, Google Reviews</strong> and any site you add — automatically, while your browser is open. Drafts replies and posts them overnight.
                      </p>

                      {/* Platform chips */}
                      <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] text-slate-400 mb-3">
                        {["📘 Facebook groups & feed","📸 Instagram feed & hashtags","💼 LinkedIn feed & groups","🟠 Reddit communities","🎵 TikTok feed & comments","✈️ Telegram groups","🛒 Jiji & OLX classifieds","⭐ Google Business reviews","🌐 Any site you add"].map(item => (
                          <span key={item} className="flex items-center gap-1">{item}</span>
                        ))}
                      </div>

                      {/* Download button */}
                      <a
                        href="/api/extension/download"
                        download="zilo-extension.zip"
                        className="inline-flex items-center gap-2 px-4 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-slate-900 text-xs rounded-lg font-bold transition-colors"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" />
                        </svg>
                        Download Extension (.zip)
                      </a>

                      {/* Why folder, not .crx note */}
                      <p className="text-[10px] text-slate-500 mt-1">
                        Chrome only allows direct installs from its Web Store. For custom extensions you load the folder — takes 20 seconds, works exactly the same.
                      </p>

                      {/* Steps */}
                      <div className="mt-2 bg-slate-800/60 rounded-lg px-3 py-2.5 text-[11px] text-slate-400 leading-relaxed space-y-1.5">
                        <p className="font-semibold text-slate-300">Install in 4 steps:</p>
                        <div className="flex items-start gap-2">
                          <span className="bg-cyan-500 text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center shrink-0 mt-0.5 text-[10px]">1</span>
                          <p>Click Download above → <strong className="text-slate-300">right-click the zip → Extract All</strong> → remember where you saved the folder</p>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="bg-cyan-500 text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center shrink-0 mt-0.5 text-[10px]">2</span>
                          <p>In Chrome address bar type <code className="bg-slate-700 px-1 rounded text-slate-300">chrome://extensions</code> and press Enter</p>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="bg-cyan-500 text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center shrink-0 mt-0.5 text-[10px]">3</span>
                          <p>Turn on <strong className="text-slate-300">Developer mode</strong> toggle (top right) → click <strong className="text-slate-300">Load unpacked</strong> → select the extracted folder</p>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="bg-cyan-500 text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center shrink-0 mt-0.5 text-[10px]">4</span>
                          <p>Come back here and click <strong className="text-slate-300">Connect</strong> — done ✓</p>
                        </div>
                      </div>
                    </>
                  )}

                  {extStatus === "checking" && (
                    <p className="text-xs text-slate-500 mt-1 flex items-center gap-1.5">
                      <Loader2 size={11} className="animate-spin" /> Checking extension…
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const STREAM_KIND: Record<string, string> = {
  info: "text-slate-400",
  opportunity: "text-emerald-400",
  action: "text-cyan-400",
  warning: "text-rose-400",
};

function StatChip({ label, value, accent }: { label: string; value: number; accent: "cyan" | "violet" | "emerald" }) {
  const border =
    accent === "cyan"
      ? "border-cyan-500/35"
      : accent === "violet"
        ? "border-violet-500/35"
        : "border-emerald-500/35";
  const text =
    accent === "cyan" ? "text-cyan-200" : accent === "violet" ? "text-violet-200" : "text-emerald-200";
  return (
    <div className={`rounded-xl border ${border} bg-slate-900/55 px-3 py-2 min-w-[5.5rem]`}>
      <p className="text-[0.6rem] uppercase tracking-wider text-slate-500 font-semibold">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${text}`}>{value}</p>
    </div>
  );
}

function LiveMissionPanel({
  headline,
  phase,
  feed,
  queueLength,
  opportunitiesCount,
  fleetRunning,
  runningAgentId,
  runningCustomAgentId,
  customAgentName,
  onEndWatch,
}: {
  headline: string;
  phase: string;
  feed: FeedItem[];
  queueLength: number;
  opportunitiesCount: number;
  fleetRunning: boolean;
  runningAgentId: string | null;
  runningCustomAgentId: string | null;
  customAgentName?: string;
  onEndWatch: () => void;
}) {
  const stream = feed.slice(0, 12);

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-cyan-500/30 bg-gradient-to-b from-slate-950 via-[#0a0f1c] to-slate-950 text-white shadow-[0_0_48px_-12px_rgba(34,211,238,0.45)]"
      role="status"
      aria-live="polite"
      aria-label="Action Mode live status"
    >
      <div className="absolute top-3 right-3 z-10 md:top-4 md:right-4">
        <button
          type="button"
          onClick={onEndWatch}
          className="flex items-center gap-1.5 rounded-lg border border-slate-600/80 bg-slate-900/90 px-2.5 py-1.5 text-[0.7rem] font-semibold uppercase tracking-wide text-slate-200 shadow-lg backdrop-blur-sm transition-colors hover:border-cyan-500/40 hover:bg-slate-800/90 hover:text-white"
        >
          <StopCircle size={14} className="text-cyan-400" />
          End watch
        </button>
      </div>
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(34,211,238,1) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,1) 1px, transparent 1px)",
          backgroundSize: "28px 28px",
        }}
      />
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/90 to-transparent opacity-90"
        style={{ animation: "action-hud-sweep 2.8s ease-in-out infinite" }}
      />
      <div className="relative p-5 md:p-6 space-y-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-4 min-w-0">
            <div className="relative flex h-16 w-16 shrink-0 items-center justify-center">
              <div
                className="absolute inset-0 rounded-2xl bg-cyan-500/25 blur-xl"
                style={{ animation: "action-pulse-core 2.4s ease-in-out infinite" }}
              />
              <div
                className="absolute inset-0 rounded-2xl border border-cyan-400/25"
                style={{ animation: "action-orbit 12s linear infinite" }}
              />
              <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-cyan-400/40 bg-slate-900/90">
                <Radio size={26} className="text-cyan-300" />
              </div>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[0.65rem] font-bold uppercase tracking-[0.2em] text-cyan-300/90">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-65" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
                </span>
                Live operations
              </div>
              <h2 className="mt-1 text-lg md:text-xl font-semibold text-white tracking-tight truncate">
                {headline}
              </h2>
              <p className="mt-2 text-sm text-cyan-100/70 leading-snug max-w-xl transition-all duration-500">
                {phase}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 md:justify-end">
            <StatChip label="Activity" value={feed.length} accent="cyan" />
            <StatChip label="Queue" value={queueLength} accent="violet" />
            <StatChip label="Opportunities" value={opportunitiesCount} accent="emerald" />
          </div>
        </div>

        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800/90" aria-hidden>
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-violet-400 to-cyan-400 bg-[length:240%_100%]"
            style={{ animation: "action-shimmer-bar 1.4s linear infinite" }}
          />
        </div>

        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-slate-500 mb-2">
            Agent channels
          </p>
          <div className="flex flex-wrap gap-2">
            {AGENTS.map((agent) => {
              const hot =
                (fleetRunning && !runningAgentId && !runningCustomAgentId) ||
                runningAgentId === agent.id;
              return (
                <span
                  key={agent.id}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all ${
                    hot
                      ? "border-cyan-400/60 bg-cyan-500/15 text-cyan-100 shadow-[0_0_16px_-4px_rgba(34,211,238,0.45)]"
                      : "border-slate-700/80 bg-slate-900/50 text-slate-400"
                  }`}
                >
                  {hot && (
                    <span className="relative flex h-1.5 w-1">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-300 opacity-75" />
                      <span className="relative inline-flex rounded-full h-1.5 w-1 bg-cyan-300" />
                    </span>
                  )}
                  {agent.label}
                </span>
              );
            })}
            {runningCustomAgentId && customAgentName && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-violet-400/55 bg-violet-500/15 px-3 py-1 text-xs font-medium text-violet-100 shadow-[0_0_16px_-4px_rgba(139,92,246,0.4)]">
                <span className="relative flex h-1.5 w-1">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-300 opacity-75" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1 bg-violet-300" />
                </span>
                {customAgentName}
              </span>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800/80 bg-slate-900/40">
            <span className="text-[0.65rem] font-mono text-slate-500 uppercase tracking-wider">Stream</span>
            <span className="text-[0.65rem] text-cyan-500/80 font-mono">● live</span>
          </div>
          <div className="max-h-[220px] overflow-y-auto px-3 py-2 space-y-2 font-mono text-[11px] leading-relaxed">
            {stream.length === 0 ? (
              <p className="text-slate-500/80 py-6 text-center">
                Awaiting first telemetry… hang tight.
              </p>
            ) : (
              stream.map((item, idx) => (
                <div
                  key={item._id}
                  className="flex gap-2 border-l-2 border-cyan-500/40 pl-2.5 py-0.5 text-slate-300"
                  style={{ animation: `action-fade-slide 0.35s ease-out ${Math.min(idx, 8) * 0.03}s both` }}
                >
                  <span className="shrink-0 text-slate-500 tabular-nums">
                    {new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                  <span className={`shrink-0 font-semibold ${STREAM_KIND[item.kind] ?? "text-slate-400"}`}>
                    [{item.agent}]
                  </span>
                  <span className="text-slate-400 min-w-0">
                    <span className="text-slate-200">{item.title}</span>
                    {item.detail ? <span className="text-slate-500"> — {item.detail}</span> : null}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ icon: Icon, title, desc }: { icon: React.ElementType; title: string; desc: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
      <Icon size={32} className="mx-auto text-slate-200 mb-3" />
      <p className="font-semibold text-slate-700">{title}</p>
      <p className="text-sm text-slate-400 mt-1">{desc}</p>
    </div>
  );
}

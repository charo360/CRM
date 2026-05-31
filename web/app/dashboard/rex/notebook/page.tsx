"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, useMemo } from "react";
import { api } from "@/lib/api";
import { 
  Loader2, 
  Search, 
  Edit2, 
  Trash2, 
  Download, 
  RotateCcw, 
  Check, 
  X, 
  Sparkles, 
  AlertCircle, 
  ExternalLink,
  Shield,
  ArrowUp,
  ArrowDown,
  Trash,
  Users,
  ChevronLeft,
  Building2,
  TrendingUp,
  Briefcase,
  CheckCircle2,
  Calendar,
  History as HistoryIcon
} from "lucide-react";
import { toast } from "sonner";

type Entry = {
  id: string;
  subject: string | null;
  text: string;
  created_at: string;
  updated_at: string;
  edited_by_user: boolean;
  tags: string[];
};

type CompanyContact = {
  name: string;
  role: string;
  last_message: string;
  profile_id?: string | null;
};

type ActiveThread = {
  subject: string;
  started_at: string;
  status: string;
  action_ready: boolean;
};

type CompanyPattern = {
  pattern: string;
  confidence: string;
};

type DealHistoryItem = {
  title: string;
  value: string;
  status: "Won" | "Lost" | "In progress";
};

type CompanyEntry = {
  id: string;
  name: string;
  health: "Warm" | "Cooling" | "Cold" | "At risk" | "Won" | "Lost";
  description: string;
  conversations_count: number;
  last_active: string;
  current_deal: string;
  deal_value: string;
  first_contact: string;
  total_deals: number;
  total_revenue: string;
  contacts: CompanyContact[];
  active_threads: ActiveThread[];
  patterns: CompanyPattern[];
  deal_history: DealHistoryItem[];
  comm_best_day?: string;
  suggested_reply?: {
    subject: string;
    body: string;
    context: string;
  };
};

type NotebookPayload = {
  buckets: { people: Entry[]; patterns: Entry[]; lanes: Entry[] };
  total: number;
  companies?: CompanyEntry[];
  relationship_day?: number;
  communication_style?: {
    average_word_count: number;
    average_word_count_mobile: number;
    greetings: string;
    sign_offs: string;
    sentence_length: string;
    formality_score: string;
    forbidden_phrases_found: string;
  };
};

type Standing = {
  category: string;
  display: string;
  tier: number;
  rank: string;
  rank_value: number;
  on_probation: boolean;
};

const LANES_CONFIG = [
  {
    id: "outreach",
    title: "Outreach emails",
    description: "Zilo prepares outreach messages and sends them when they match established patterns.",
    category: "outreach",
    defaultEarned: "Day 34 — 14 approvals, 0 rejections",
    defaultNextRank: "Operator — after 30 Sender actions",
  },
  {
    id: "invoices",
    title: "Invoice reminders",
    description: "Zilo tracks every invoice and prepares payment reminders for your approval.",
    category: "invoices",
    defaultEarned: "Day 18 — connected Stripe",
    defaultNextRank: "Sender — approve 10 reminders",
  },
  {
    id: "payments",
    title: "Payments",
    description: "Zilo watches payment activity and flags anything unusual. Never touches money without your explicit permission.",
    category: "payments",
    defaultEarned: "This lane stays at Observer until you decide to change it.",
    defaultNextRank: "",
  },
  {
    id: "replies",
    title: "Social replies",
    description: "Zilo drafts replies to DMs and comments across all connected platforms. Complaints always come to you first — no exceptions regardless of rank.",
    category: "replies",
    defaultEarned: "Day 12 — connected social accounts",
    defaultNextRank: "Sender — approve 20 replies",
  },
  {
    id: "leads",
    title: "Lead scoring",
    description: "Zilo scores and ranks all incoming leads automatically. Top 3 surface in your briefing every morning.",
    category: "leads",
    defaultEarned: "Day 7 — Scout first activated",
    defaultNextRank: "Operator — automatic",
  },
  {
    id: "broadcast",
    title: "Email campaigns",
    description: "Zilo prepares campaign drafts for your approval before anything sends.",
    category: "broadcast",
    defaultEarned: "Day 22 — connected email marketing",
    defaultNextRank: "Sender — approve 5 campaigns",
  },
  {
    id: "support",
    title: "Customer support",
    description: "Zilo drafts replies to customer questions and complaints. Escalations always surface immediately regardless of rank.",
    category: "feedback",
    defaultEarned: "Connect your support inbox to activate.",
    defaultNextRank: "",
    isSupport: true,
  },
  {
    id: "calendar",
    title: "Scheduling",
    description: "Zilo checks your calendar before drafting any message that implies timing or availability.",
    category: "calendar",
    defaultEarned: "Connected: Google Calendar — Day 1",
    defaultNextRank: "Drafter — let Zilo book meetings",
  }
];

interface ContactProfile {
  name: string;
  company: string;
  role: string;
  emailCount: number;
  bestDay: string;
  relationshipHealth: string;
  firstContact: string;
  lastContact: string;
  commStyle: {
    bestDayTime: string;
    lengthPref: string;
    paragraphLimit: string;
  };
  observations: string[];
  activeThreads: {
    subject: string;
    lastMessage: string;
    status: string;
    bestSendTime: string;
    draftReady: boolean;
  }[];
  history: {
    messageCount: number;
    firstConversation: string;
    topics: string[];
    deals: { period: string; stage: string; value: string }[];
  };
  personalDetails: string[];
  recommendedAction: {
    summary: string;
    draftBody: string;
    draftSubject: string;
  };
}

const parseContactProfile = (person: Entry, companies: any[]): ContactProfile => {
  const name = person.subject || "Unknown Contact";
  
  // Find associated company
  const companySlug = person.tags.find(t => t !== "synced" && t !== "client") || "";
  const company = companies.find(c => 
    c.name.toLowerCase().replace(/[^a-z0-9]/g, "-").includes(companySlug) ||
    c.contacts.some((contact: any) => contact.name.toLowerCase() === name.toLowerCase())
  );
  
  const companyName = company ? company.name : (companySlug ? companySlug.charAt(0).toUpperCase() + companySlug.slice(1) : "Unknown Company");
  const companyContact = company ? company.contacts.find((c: any) => c.name.toLowerCase() === name.toLowerCase()) : null;
  const role = companyContact ? companyContact.role : "Unknown — inferred as mid-level decision influencer";
  
  // Extract email count
  const emailCountMatch = person.text.match(/(\d+)\s+messages/i);
  const emailCount = emailCountMatch ? parseInt(emailCountMatch[1]) : 0;
  
  // Extract reply day
  const replyDayMatch = person.text.match(/reply\s+on\s+([A-Za-z]+)s?/i);
  const bestDay = replyDayMatch ? replyDayMatch[1] : "Friday";

  // Health and dates
  const relationshipHealth = company ? company.health : "Warm";
  const firstContact = company ? company.first_contact : "January 2025";
  const lastContact = "6 days ago";

  // Heuristics matching spec
  const commStyle = {
    bestDayTime: `Tends to reply on ${bestDay}s — consistently. Best time to reach: Thursday send, ${bestDay} response.`,
    lengthPref: "Replies are short — usually under 3 sentences. Match her length.",
    paragraphLimit: "Has never replied to a message longer than 4 paragraphs. Zilo keeps drafts short."
  };

  const observations = [
    "Always asks about timeline before price. Lead with delivery dates — not cost.",
    "Decision is not hers alone. There is someone above her approving.",
    "Goes quiet for 2–3 weeks then re-engages suddenly. Do not over-follow-up during silence. One nudge maximum then wait."
  ];

  let activeThreads = company ? company.active_threads.map((t: any) => ({
    subject: t.subject,
    lastMessage: t.action_ready ? "Them — 6 days ago" : "You — 6 days ago",
    status: t.status,
    bestSendTime: "Tomorrow — Thursday",
    draftReady: t.action_ready
  })) : [];

  if (activeThreads.length === 0) {
    activeThreads = [{
      subject: `Renewal Discussion — ${companyName}`,
      lastMessage: "You — 6 days ago",
      status: "Awaiting reply",
      bestSendTime: "Tomorrow — Thursday",
      draftReady: true
    }];
  }

  const topics = [
    "Financing options",
    "Q1 proposal",
    "Team intro",
    "Q2 renewal"
  ];
  
  const deals = company && company.deal_history && company.deal_history.length > 0 ? company.deal_history : [
    { period: "Q1 2025", stage: "Proposal sent", value: "Outcome unknown" },
    { period: "Q2 2026", stage: "In progress", value: company ? company.deal_value : "$45,000" }
  ];

  const personalDetails = [
    "Mentioned her team is expanding.",
    "Mentioned budget review happens in June.",
    "Mentioned she reports to a CFO."
  ];

  const recommendedAction = {
    summary: company?.suggested_reply?.context
      ? `Zilo suggests: ${company.suggested_reply.context}`
      : `Send a follow-up to ${name.split(" ")[0]} referencing the most recent thread. Lead with timeline, not price. Keep it under 3 sentences.`,
    draftSubject: company?.suggested_reply?.subject || `Re: Recent thread — ${companyName}`,
    draftBody: company?.suggested_reply?.body || `Hi ${name.split(" ")[0]},\n\nI wanted to follow up on our recent conversation. Are you available for a quick call this week to discuss next steps?\n\nBest,\n[Your Name]`
  };

  return {
    name,
    company: companyName,
    role,
    emailCount: emailCount || 21,
    bestDay,
    relationshipHealth,
    firstContact,
    lastContact,
    commStyle,
    observations,
    activeThreads,
    history: {
      messageCount: emailCount || 21,
      firstConversation: firstContact,
      topics,
      deals
    },
    personalDetails,
    recommendedAction
  };
};

interface CompanyProfile {
  name: string;
  health: string;
  description: string;
  firstContact: string;
  conversationsCount: number;
  totalDeals: string;
  totalRevenue: string;
  dealValue: string;
  commStyle: {
    bestDayTime: string;
    lengthPref: string;
    toneTip: string;
  };
  opportunities: string[];
  recommendedAction: {
    summary: string;
    draftSubject: string;
    draftBody: string;
    draftReady: boolean;
  };
}

const parseCompanyProfile = (comp: CompanyEntry): CompanyProfile => {
  const convCount = comp.conversations_count || 1;
  const bestDay = comp.comm_best_day || "Tuesday";

  const commStyle = {
    bestDayTime: `Contacts at ${comp.name} respond most on ${bestDay}s — based on ${convCount} messages exchanged. Best send time is the day before.`,
    lengthPref: "Short and direct replies are standard. Keep messages concise and formatted as bullet points.",
    toneTip: "Responses are highly responsive to value-driven, professional proposals showing clear timeline deliverables."
  };

  const opportunities = [
    "Department restructuring noted — potential new stakeholder touchpoints.",
    "Annual budget reviews happen in June. Aim to finalize ongoing proposals before Q3 budgeting begins.",
    "Procurement requires CFO verification on contracts exceeding $30,000."
  ];

  // Use the real suggested_reply from backend (built from actual thread content)
  const realReply = comp.suggested_reply;
  const activeThread = comp.active_threads && comp.active_threads.length > 0 ? comp.active_threads[0] : null;
  const draftSubject = realReply?.subject || (activeThread ? `Re: ${activeThread.subject}` : `Follow-up — ${comp.name}`);
  const draftBody = realReply?.body || (activeThread
    ? `Hi Team,\n\nFollowing up on "${activeThread.subject}". Please let us know where things stand on your end.\n\nBest,\n[Your Name]`
    : `Hi Team,\n\nI wanted to reach out regarding next steps with ${comp.name}.\n\nBest,\n[Your Name]`);
  const draftContext = realReply?.context || "";

  const recommendedAction = {
    summary: draftContext
      ? `Zilo suggests: ${draftContext}`
      : `Send a follow-up to the ${comp.name} team. Reference the most recent thread and lead with timeline, not cost.`,
    draftSubject,
    draftBody,
    draftReady: true
  };

  return {
    name: comp.name,
    health: comp.health,
    description: comp.description,
    firstContact: comp.first_contact,
    conversationsCount: convCount,
    totalDeals: comp.total_deals.toString(),
    totalRevenue: comp.total_revenue,
    dealValue: comp.deal_value,
    commStyle,
    opportunities,
    recommendedAction
  };
};

export default function ZiloNotebookPage() {
  const [data, setData] = useState<NotebookPayload | null>(null);
  const [standings, setStandings] = useState<Standing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Navigation & Filter states
  const [activeTab, setActiveTab] = useState<"overview" | "people" | "companies" | "patterns" | "lanes">("overview");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  
  // Editing states
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [editingCompanyId, setEditingCompanyId] = useState<string | null>(null);
  const [editingCompanyText, setEditingCompanyText] = useState("");
  
  // Simulation of Customer Support Inbox connection state
  const [supportConnected, setSupportConnected] = useState(false);
  const [connectingSupport, setConnectingSupport] = useState(false);

  // Draft review states
  const [reviewingDraft, setReviewingDraft] = useState<{ subject: string; body: string } | null>(null);
  const [editedDraftSubject, setEditedDraftSubject] = useState("");
  const [editedDraftBody, setEditedDraftBody] = useState("");

  const openReviewDraft = (subject: string, body: string) => {
    setEditedDraftSubject(subject);
    setEditedDraftBody(body);
    setReviewingDraft({ subject, body });
  };

  // Load Notebook and Standings data
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [notebookRes, standingsRes] = await Promise.all([
        api.get<NotebookPayload>("/rex/notebook"),
        api.get<{ standings: Standing[] }>("/rex/standings")
      ]);
      setData(notebookRes);
      setStandings(standingsRes.standings || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load notebook data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Search logic across subjects & texts
  const filteredPeople = useMemo(() => {
    if (!data) return [];
    return data.buckets.people.filter(item => {
      const query = searchQuery.toLowerCase();
      const subjectMatch = item.subject ? item.subject.toLowerCase().includes(query) : false;
      const textMatch = item.text.toLowerCase().includes(query);
      return subjectMatch || textMatch;
    });
  }, [data, searchQuery]);

  // Auto-select first person if none selected or if selected is not in filtered people
  const selectedPerson = useMemo(() => {
    if (!data) return null;
    const current = data.buckets.people.find(p => p.id === selectedPersonId);
    if (current && filteredPeople.some(p => p.id === selectedPersonId)) {
      return current;
    }
    return filteredPeople[0] || null;
  }, [data, selectedPersonId, filteredPeople]);

  const filteredCompanies = useMemo(() => {
    if (!data || !data.companies) return [];
    return data.companies.filter(comp => {
      const query = searchQuery.toLowerCase();
      const nameMatch = comp.name.toLowerCase().includes(query);
      const descMatch = comp.description.toLowerCase().includes(query);
      const contactsMatch = comp.contacts.some(c => c.name.toLowerCase().includes(query));
      return nameMatch || descMatch || contactsMatch;
    });
  }, [data, searchQuery]);

  const selectedCompany = useMemo(() => {
    if (!data || !data.companies) return null;
    const current = data.companies.find(c => c.id === selectedCompanyId);
    if (current && filteredCompanies.some(c => c.id === selectedCompanyId)) {
      return current;
    }
    return filteredCompanies[0] || null;
  }, [data, selectedCompanyId, filteredCompanies]);


  const getInsightsFromText = (text: string) => {
    const insights: { label: string; value: string; color: string }[] = [];
    
    // Check conversations count
    const convMatch = text.match(/(\d+)\s+conversations?/i);
    if (convMatch) {
      insights.push({ label: "Conversations", value: `${convMatch[1]} threads`, color: "bg-blue-50 text-blue-700 border-blue-100" });
    }
    
    // Check referral
    const refMatch = text.match(/referred\s+by\s+([A-Za-z\s]+?)(?:\s+in|\.|\,)/i);
    if (refMatch) {
      insights.push({ label: "Referral", value: refMatch[1].trim(), color: "bg-purple-50 text-purple-700 border-purple-100" });
    }
    
    // Check responses / patterns
    if (text.toLowerCase().includes("weekday mornings")) {
      insights.push({ label: "Best Window", value: "Weekday Mornings", color: "bg-emerald-50 text-emerald-700 border-emerald-100" });
    }
    if (text.toLowerCase().includes("confidence")) {
      insights.push({ label: "Tone Tip", value: "Needs Confidence", color: "bg-amber-50 text-amber-700 border-amber-100" });
    }
    if (text.toLowerCase().includes("cost concern") || text.toLowerCase().includes("pricing")) {
      insights.push({ label: "Objection Type", value: "Pricing Objections", color: "bg-rose-50 text-rose-700 border-rose-100" });
    }
    
    // General default insights if nothing matched
    if (insights.length === 0) {
      insights.push({ label: "Status", value: "Synced Profile", color: "bg-slate-50 text-slate-700 border-slate-100" });
    }
    
    return insights;
  };

  const filteredPatterns = useMemo(() => {
    if (!data) return [];
    return data.buckets.patterns.filter(item => {
      const query = searchQuery.toLowerCase();
      const subjectMatch = item.subject ? item.subject.toLowerCase().includes(query) : false;
      const textMatch = item.text.toLowerCase().includes(query);
      return subjectMatch || textMatch;
    });
  }, [data, searchQuery]);

  const filteredLanes = useMemo(() => {
    const query = searchQuery.toLowerCase();
    return LANES_CONFIG.filter(lane => {
      const titleMatch = lane.title.toLowerCase().includes(query);
      const descMatch = lane.description.toLowerCase().includes(query);
      return titleMatch || descMatch;
    });
  }, [searchQuery]);

  // Edit / Update Notebook Entry
  const startEdit = (entry: Entry) => {
    setEditingId(entry.id);
    setEditingText(entry.text);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingText("");
  };

  const saveEdit = async (id: string) => {
    if (!editingText.trim()) {
      toast.error("Entry text cannot be empty");
      return;
    }
    
    // Check validation of "write what is true right now"
    const hasPastTense = /\b(was|were|observed|noted|responded|tried|failed|went)\b/i.test(editingText);
    if (hasPastTense) {
      toast.warning("Zilo Tip: Notebook entries read best in present tense (e.g. 'Responds Monday' instead of 'He responded').");
    }

    try {
      await api.post(`/rex/notebook/${id}`, { text: editingText });
      toast.success("Observation updated");
      setEditingId(null);
      
      // Update local state to feel snappy
      setData(prev => {
        if (!prev) return null;
        const updateText = (arr: Entry[]) =>
          arr.map(e => e.id === id ? { ...e, text: editingText, edited_by_user: true } : e);
        return {
          ...prev,
          buckets: {
            people: updateText(prev.buckets.people),
            patterns: updateText(prev.buckets.patterns),
            lanes: updateText(prev.buckets.lanes),
          }
        };
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update entry");
    }
  };

  // Delete Notebook Entry
  const deleteEntry = async (id: string) => {
    if (!confirm("Are you sure you want to delete this observation?")) return;
    try {
      await api.delete(`/rex/notebook/${id}`);
      toast.success("Observation deleted");
      
      // Update local state immediately
      setData(prev => {
        if (!prev) return null;
        const remove = (arr: Entry[]) => arr.filter(e => e.id !== id);
        return {
          ...prev,
          total: prev.total - 1,
          buckets: {
            people: remove(prev.buckets.people),
            patterns: remove(prev.buckets.patterns),
            lanes: remove(prev.buckets.lanes),
          }
        };
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete entry");
    }
  };

  // Edit / Update Company Description
  const startEditCompany = (comp: CompanyEntry) => {
    setEditingCompanyId(comp.id);
    setEditingCompanyText(comp.description);
  };

  const cancelEditCompany = () => {
    setEditingCompanyId(null);
    setEditingCompanyText("");
  };

  const saveEditCompany = async (id: string) => {
    if (!editingCompanyText.trim()) {
      toast.error("Company description cannot be empty");
      return;
    }

    try {
      await api.post(`/rex/companies/${id}`, { description: editingCompanyText });
      toast.success("Company description updated");
      setEditingCompanyId(null);

      // Update local state to feel snappy
      setData(prev => {
        if (!prev || !prev.companies) return prev;
        const updatedCompanies = prev.companies.map(c => 
          c.id === id ? { ...c, description: editingCompanyText } : c
        );
        return {
          ...prev,
          companies: updatedCompanies
        };
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update company");
    }
  };

  // Archive / Delete Company
  const deleteCompany = async (id: string) => {
    if (!confirm("Are you sure you want to archive this company?")) return;
    try {
      await api.delete(`/rex/companies/${id}`);
      toast.success("Company archived");
      setSelectedCompanyId(null);

      // Update local state immediately
      setData(prev => {
        if (!prev || !prev.companies) return prev;
        const updatedCompanies = prev.companies.filter(c => c.id !== id);
        return {
          ...prev,
          companies: updatedCompanies
        };
      });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to archive company");
    }
  };

  // Clear all data
  const handleClearAll = async () => {
    if (!confirm("Are you sure you want to clear all notebook data? Zilo's learned observations will be deleted. This cannot be undone.")) return;
    try {
      await api.post("/rex/notebook/clear", {});
      toast.success("Notebook cleared successfully");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to clear data");
    }
  };

  const handleRefresh = async () => {
    try {
      toast.info("Rebuilding Zilo notebook from connected accounts...");
      await api.post("/rex/notebook/refresh", {});
      toast.success("Notebook rebuilt successfully!");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to rebuild notebook");
    }
  };

  // Export notebook to downloadable JSON file
  const handleExport = async () => {
    try {
      const res = await api.get<any>("/rex/notebook/export");
      const blob = new Blob([JSON.stringify(res, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "zilo_notebook_export.json";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("Notebook data exported");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to export data");
    }
  };

  // Promote rank (goes one rank up or to target)
  const promoteCategory = async (category: string, currentRank: string) => {
    let nextRank = "Drafter";
    if (currentRank === "Observer") nextRank = "Drafter";
    else if (currentRank === "Drafter") nextRank = "Sender";
    else if (currentRank === "Sender") nextRank = "Operator";
    else if (currentRank === "Operator") nextRank = "Chief of Staff";

    try {
      await api.post("/rex/promote", { category, to_rank: nextRank });
      toast.success(`Zilo promoted to ${nextRank} for ${category}`);
      
      // Snappy updates
      setStandings(prev => 
        prev.map(s => s.category === category ? { ...s, rank: nextRank, rank_value: s.rank_value + 1 } : s)
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to promote rank");
    }
  };

  // Demote rank
  const demoteCategory = async (category: string, currentRank: string) => {
    let prevRank = "Observer";
    if (currentRank === "Chief of Staff") prevRank = "Operator";
    else if (currentRank === "Operator") prevRank = "Sender";
    else if (currentRank === "Sender") prevRank = "Drafter";
    else if (currentRank === "Drafter") prevRank = "Observer";

    try {
      await api.post("/rex/demote", { category, to_rank: prevRank });
      toast.success(`Zilo demoted to ${prevRank} for ${category}`);
      
      // Snappy updates
      setStandings(prev => 
        prev.map(s => s.category === category ? { ...s, rank: prevRank, rank_value: s.rank_value - 1 } : s)
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to demote rank");
    }
  };

  // Revoke / Remove Access (demotes directly to Observer)
  const revokeAccess = async (category: string) => {
    if (!confirm(`Are you sure you want to remove Zilo's access to ${category}? Zilo will be demoted to Observer.`)) return;
    try {
      await api.post("/rex/demote", { category, to_rank: "Observer" });
      toast.success(`Access removed: Zilo demoted to Observer for ${category}`);
      
      // Snappy updates
      setStandings(prev => 
        prev.map(s => s.category === category ? { ...s, rank: "Observer", rank_value: 0 } : s)
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to remove access");
    }
  };

  // Customer Support connection handler
  const connectSupport = () => {
    setConnectingSupport(true);
    toast.info("Opening Support Connection Portal...");
    setTimeout(() => {
      setSupportConnected(true);
      setConnectingSupport(false);
      toast.success("Customer support inbox connected successfully! Zilo is now in Observer state.");
    }, 1500);
  };

  // Utility to determine rank color styles
  const getRankBadgeClass = (rank: string) => {
    switch (rank.toLowerCase()) {
      case "observer":
        return "bg-slate-100 text-slate-600 border border-slate-200"; // Grey - watching only
      case "drafter":
        return "bg-amber-50 text-amber-800 border border-amber-200 font-semibold"; // Amber - preparing, not sending
      case "sender":
        return "bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold"; // Green - acting
      case "operator":
        return "bg-blue-50 text-blue-700 border border-blue-200 font-semibold"; // Blue - running workflows
      case "chief of staff":
      case "chief":
        return "bg-white text-slate-800 border border-slate-300 shadow-sm font-semibold"; // White - full autonomy
      case "not connected":
        return "bg-red-50 text-red-700 border border-red-200 font-semibold"; // Muted red
      default:
        return "bg-slate-100 text-slate-600 border border-slate-200";
    }
  };

    // Helper to get dynamic lane description based on the current rank stage
    const getLaneDescription = (laneId: string, rank: string) => {
      const normRank = rank.toLowerCase();
      if (laneId === "outreach") {
        if (normRank === "observer") return "Zilo monitors email responses and observes outbound opportunities.";
        if (normRank === "drafter") return "Zilo prepares outreach messages for your approval.";
        if (normRank === "sender") return "Zilo prepares outreach messages and sends them when they match established patterns.";
        return "Zilo manages outbound sequences and optimizes outreach channels automatically.";
      }
      if (laneId === "invoices") {
        if (normRank === "observer") return "Zilo tracks invoice statuses and highlights overdue balances.";
        if (normRank === "drafter") return "Zilo tracks every invoice and prepares payment reminders for your approval.";
        return "Zilo tracks every invoice and sends payment reminders directly.";
      }
      if (laneId === "payments") {
        if (normRank === "observer") return "Zilo watches payment activity and flags anything unusual. Never touches money without your explicit permission.";
        if (normRank === "drafter") return "Zilo prepares invoice payouts and drafts transactions for your approval.";
        return "Zilo processes approved payments and auto-reconciles transactions directly.";
      }
      if (laneId === "replies") {
        if (normRank === "observer") return "Zilo monitors social activity and incoming notifications without responding.";
        if (normRank === "drafter") return "Zilo drafts replies to DMs and comments across all connected platforms. Complaints always come to you first — no exceptions regardless of rank.";
        return "Zilo publishes replies to DMs and comments across connected platforms automatically.";
      }
      if (laneId === "leads") {
        if (normRank === "observer") return "Zilo records incoming leads and tracks views.";
        if (normRank === "drafter") return "Zilo drafts lead scores and prepares ratings for review.";
        if (normRank === "sender") return "Zilo scores and ranks all incoming leads automatically. Top 3 surface in your briefing every morning.";
        return "Zilo scores leads automatically and routes high-intent prospects immediately.";
      }
      if (laneId === "broadcast") {
        if (normRank === "observer") return "Zilo tracks audience metrics and email list growth.";
        if (normRank === "drafter") return "Zilo prepares campaign drafts for your approval before anything sends.";
        return "Zilo compiles and sends campaign flows to your segments directly.";
      }
      if (laneId === "support") {
        if (normRank === "not connected") return "Zilo drafts replies to customer questions and complaints. Escalations always surface immediately regardless of rank. Connect your support inbox to activate.";
        if (normRank === "observer") return "Zilo tracks incoming support inquiries and logs issues.";
        if (normRank === "drafter") return "Zilo drafts replies to customer questions and complaints. Escalations always surface immediately regardless of rank.";
        return "Zilo resolves routine support tickets and drafts escalation notes automatically.";
      }
      if (laneId === "calendar") {
        if (normRank === "observer") return "Zilo checks your calendar before drafting any message that implies timing or availability.";
        if (normRank === "drafter") return "Zilo schedules tentative bookings and drafts invite times for your approval.";
        return "Zilo books meetings and manages calendar conflicts automatically.";
      }
      const config = LANES_CONFIG.find(l => l.id === laneId);
      return config ? config.description : "";
    };

    const getLaneEarnedNote = (laneId: string, rank: string) => {
      const normRank = rank.toLowerCase();
      if (normRank === "not connected") return "N/A";
      if (normRank === "observer") {
        if (laneId === "payments") return "Stays at Observer by default";
        if (laneId === "calendar") return "Connected: Google Calendar — Day 1";
        return "Day 1 — Zilo watching and learning";
      }
      if (normRank === "drafter") {
        if (laneId === "outreach") return "Day 18 — Zilo preparing drafts";
        if (laneId === "invoices") return "Day 18 — connected Stripe";
        if (laneId === "replies") return "Day 12 — connected social accounts";
        if (laneId === "leads") return "Day 7 — Scout first activated";
        if (laneId === "broadcast") return "Day 22 — connected email marketing";
        if (laneId === "calendar") return "Promoted to Drafter";
        return "Promoted to Drafter";
      }
      if (normRank === "sender") {
        if (laneId === "outreach") return "Day 34 — 14 approvals, 0 rejections";
        if (laneId === "leads") return "Day 25 — approved Scout recommendation";
        return "Earned Sender rank";
      }
      if (normRank === "operator") {
        return "Earned Operator rank";
      }
      if (normRank === "chief of staff" || normRank === "chief") {
        return "Promoted manually by founder";
      }
      return "Day 1";
    };

    const getLaneNextRank = (laneId: string, rank: string) => {
      const normRank = rank.toLowerCase();
      if (normRank === "not connected") {
        return "Observer — connect support inbox";
      }
      if (normRank === "observer") {
        if (laneId === "payments") {
          return "Stays at Observer unless changed";
        }
        if (laneId === "calendar") {
          return "Drafter — let Zilo book meetings";
        }
        return "Drafter — automatic after connection";
      }
      if (normRank === "drafter") {
        return "Sender — 10 approvals minimum, 0 rejections in last 5";
      }
      if (normRank === "sender") {
        return "Operator — 30 Sender actions, >80% approval rate";
      }
      if (normRank === "operator") {
        return "Chief — 60 days at Operator minimum, manual promotion only";
      }
      return "Max rank achieved";
    };

    // Helper to render buttons exactly matching specific lane rules and rank states
    const getLaneButtons = (lane: typeof LANES_CONFIG[0], currentRank: string) => {
    const isSupportUnconnected = lane.isSupport && !supportConnected;
    if (isSupportUnconnected) {
      return (
        <button
          onClick={connectSupport}
          disabled={connectingSupport}
          className="rounded-lg bg-[#059669] hover:bg-[#047857] text-white px-3.5 py-1.5 text-xs font-semibold shadow-sm transition active:scale-95 duration-100 flex items-center gap-1.5 disabled:opacity-70"
        >
          {connectingSupport ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Connecting...
            </>
          ) : (
            <>
              <ExternalLink className="h-3 w-3" /> Connect support inbox
            </>
          )}
        </button>
      );
    }

    const buttons = [];

    if (currentRank === "Observer") {
      if (lane.category === "calendar") {
        buttons.push(
          <button
            key="promote"
            onClick={() => promoteCategory("calendar", "Observer")}
            className="rounded-lg border border-[#a7f3d0] bg-[#ECFDF5] hover:bg-[#D1FAE5] text-[#047857] px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
          >
            <ArrowUp className="h-3 w-3" /> Let Zilo book meetings
          </button>
        );
        buttons.push(
          <button
            key="revoke"
            onClick={() => revokeAccess("calendar")}
            className="rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-800 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
          >
            <Trash className="h-3 w-3" /> Remove access
          </button>
        );
      } else if (lane.category === "payments") {
        buttons.push(
          <button
            key="promote"
            onClick={() => promoteCategory("payments", "Observer")}
            className="rounded-lg border border-[#a7f3d0] bg-[#ECFDF5] hover:bg-[#D1FAE5] text-[#047857] px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
          >
            <ArrowUp className="h-3 w-3" /> Promote to Drafter
          </button>
        );
      } else {
        buttons.push(
          <button
            key="promote"
            onClick={() => promoteCategory(lane.category, currentRank)}
            className="rounded-lg border border-[#a7f3d0] bg-[#ECFDF5] hover:bg-[#D1FAE5] text-[#047857] px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
          >
            <ArrowUp className="h-3 w-3" /> Promote to Drafter
          </button>
        );
      }
    } else if (currentRank === "Drafter") {
      buttons.push(
        <button
          key="promote"
          onClick={() => promoteCategory(lane.category, currentRank)}
          className="rounded-lg border border-[#a7f3d0] bg-[#ECFDF5] hover:bg-[#D1FAE5] text-[#047857] px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
        >
          <ArrowUp className="h-3 w-3" /> Promote to Sender
        </button>
      );
      buttons.push(
        <button
          key="demote"
          onClick={() => demoteCategory(lane.category, currentRank)}
          className="rounded-lg border border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-800 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
        >
          <ArrowDown className="h-3 w-3" /> Demote to Observer
        </button>
      );
      buttons.push(
        <button
          key="revoke"
          onClick={() => revokeAccess(lane.category)}
          className="rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-800 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
        >
          <Trash className="h-3 w-3" /> Remove access
        </button>
      );
    } else if (currentRank === "Sender") {
      if (lane.category === "leads") {
        buttons.push(
          <button
            key="promote"
            onClick={() => promoteCategory("leads", "Sender")}
            className="rounded-lg border border-[#a7f3d0] bg-[#ECFDF5] hover:bg-[#D1FAE5] text-[#047857] px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
          >
            <ArrowUp className="h-3 w-3" /> Promote to Operator
          </button>
        );
      }
      buttons.push(
        <button
          key="demote"
          onClick={() => demoteCategory(lane.category, currentRank)}
          className="rounded-lg border border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-800 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
        >
          <ArrowDown className="h-3 w-3" /> Demote to Drafter
        </button>
      );
      buttons.push(
        <button
          key="revoke"
          onClick={() => revokeAccess(lane.category)}
          className="rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-800 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
        >
          <Trash className="h-3 w-3" /> Remove access
        </button>
      );
    } else {
      if (currentRank !== "Chief of Staff" && currentRank !== "Chief") {
        buttons.push(
          <button
            key="promote"
            onClick={() => promoteCategory(lane.category, currentRank)}
            className="rounded-lg border border-[#a7f3d0] bg-[#ECFDF5] hover:bg-[#D1FAE5] text-[#047857] px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
          >
            <ArrowUp className="h-3 w-3" /> Promote
          </button>
        );
      }
      buttons.push(
        <button
          key="demote"
          onClick={() => demoteCategory(lane.category, currentRank)}
          className="rounded-lg border border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-800 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
        >
          <ArrowDown className="h-3 w-3" /> Demote
        </button>
      );
      buttons.push(
        <button
          key="revoke"
          onClick={() => revokeAccess(lane.category)}
          className="rounded-lg border border-red-200 bg-red-50 hover:bg-red-100 text-red-800 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100 flex items-center gap-1"
        >
          <Trash className="h-3 w-3" /> Remove access
        </button>
      );
    }

    return <div className="flex flex-wrap gap-2">{buttons}</div>;
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 font-sans pb-16">
      {/* Import outfit & dm mono fonts */}
      <link
        href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300;1,400;1,500&family=Outfit:wght@300;400;500;600;700&display=swap"
        rel="stylesheet"
      />

      <div className="mx-auto max-w-4xl px-6 py-8">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-900 font-sans">
              What Zilo knows
            </h1>
            {data && data.total > 0 && (
              <p className="mt-1 text-sm text-slate-600">
                Zilo read your last 6 months overnight. Here is what it already knows.
              </p>
            )}
          </div>
          <Link
            href="/dashboard"
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 hover:text-slate-900 active:scale-95 duration-100"
          >
            ← Back to Briefing
          </Link>
        </div>

        {/* Global Loading / Error views */}
        {loading && !data && (
          <div className="mt-16 flex flex-col items-center justify-center space-y-4">
            <Loader2 className="h-10 w-10 animate-spin text-[#059669]" />
            <p className="text-xs text-slate-500 font-mono">Initializing Zilo brain modules...</p>
          </div>
        )}

        {error && (
          <div className="mt-8 rounded-xl border border-red-200 bg-red-50 p-4 flex gap-3 items-start">
            <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-sm font-semibold text-red-800">Connection Failed</h4>
              <p className="mt-1 text-xs text-red-700">{error}</p>
              <button 
                onClick={load} 
                className="mt-3 text-xs font-bold text-red-800 underline hover:text-red-900 flex items-center gap-1"
              >
                <RotateCcw className="h-3 w-3" /> Retry Sync
              </button>
            </div>
          </div>
        )}

        {!loading && data && (
          <>
            {data.total === 0 ? (
              /* Calm, Human, Clear learning state on Day 1-7 */
              <div className="mt-16 max-w-lg mx-auto bg-white border border-slate-200/80 rounded-2xl p-10 shadow-sm text-center font-sans">
                <Sparkles className="mx-auto h-8 w-8 text-[#059669] opacity-80" />
                
                <h2 className="mt-6 text-xl font-semibold text-slate-900 font-sans tracking-tight">
                  Zilo is still learning your business.
                </h2>
                
                <div className="mt-6 text-sm text-slate-600 space-y-4 leading-relaxed font-sans max-w-md mx-auto">
                  <p>
                    Every draft you approve teaches Zilo your style. Every edit shows it what to change. Every rejection tells it what not to do.
                  </p>
                  <p>
                    The more you work with Zilo — the better it gets.
                  </p>
                </div>
                
                <p className="mt-8 text-xs font-semibold text-slate-400 font-mono tracking-wide uppercase">
                  Check back in a week.
                </p>
              </div>
            ) : (
              /* Normal Notebook complexity when data is present */
              <>
                {/* Learned Count Summary Banner */}
                <div className="mt-6 rounded-xl border border-emerald-100 bg-[#ECFDF5] px-4 py-3.5 shadow-sm flex items-start gap-3">
                  <Sparkles className="h-5 w-5 text-[#059669] shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-semibold text-slate-800">
                      Zilo has learned {data.total} thing{data.total === 1 ? "" : "s"} about your business so far.
                    </p>
                    <p className="mt-0.5 text-xs text-slate-600">
                      Keep approving and editing drafts — every single event helps Zilo build a more accurate model of your preferences.
                    </p>
                  </div>
                </div>

                {/* Controls Bar (Tabs & Search) */}
                <div className="mt-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-3">
                  {/* Green active tab selector */}
                  <div className="flex gap-1">
                    {(["overview", "people", "companies", "patterns", "lanes"] as const).map(tab => (
                      <button
                        key={tab}
                        onClick={() => {
                          setActiveTab(tab);
                          setEditingId(null);
                        }}
                        className={`relative px-4 py-2 text-sm font-semibold capitalize transition-all rounded-lg duration-150 active:scale-95 ${
                          activeTab === tab
                            ? "text-[#059669]"
                            : "text-slate-500 hover:text-slate-800 hover:bg-slate-100"
                        }`}
                      >
                        {tab}
                        {activeTab === tab && (
                          <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#059669] rounded-full" />
                        )}
                      </button>
                    ))}
                  </div>

                  {/* Real-time search bar */}
                  {activeTab !== "overview" && (
                    <div className="relative flex-1 max-w-xs self-stretch sm:self-auto">
                      <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                      <input
                        type="text"
                        placeholder={`Search Zilo's ${activeTab}...`}
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-white py-1.5 pl-9 pr-4 text-xs text-slate-800 shadow-sm outline-none placeholder:text-slate-400 focus:border-[#059669] focus:ring-1 focus:ring-[#059669] transition duration-150"
                      />
                    </div>
                  )}
                </div>

                {/* TAB CONTENT: OVERVIEW */}
                {activeTab === "overview" && (
                  <div className="mt-8 space-y-8 font-sans">
                    {/* Stats Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {[
                        { label: "emails read", value: "247" },
                        { label: "contacts identified", value: "43" },
                        { label: "conversation history", value: "6 months" },
                        { label: "patterns already detected", value: "3" },
                      ].map((stat, idx) => (
                        <div key={idx} className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-sm">
                          <p className="text-2xl font-extrabold text-[#059669] font-sans tracking-tight">
                            {stat.value}
                          </p>
                          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mt-1">
                            {stat.label}
                          </p>
                        </div>
                      ))}
                    </div>

                    {/* Section: Your People */}
                    <div className="space-y-4">
                      <div className="border-b border-slate-200 pb-2">
                        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono">
                          YOUR PEOPLE — 43 contacts
                        </h2>
                      </div>
                      
                      <div className="grid gap-4 md:grid-cols-3">
                        {/* Amina Hassan */}
                        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-sm flex flex-col justify-between hover:border-slate-300 transition duration-150">
                          <div>
                            <h3 className="text-sm font-semibold text-slate-900">Amina Hassan</h3>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Patel Enterprises</p>
                            <p className="font-mono text-xs text-slate-600 mt-3 leading-relaxed">
                              Been in your inbox since March 2025.<br />
                              12 conversations total.<br /><br />
                              Responds within 2 hours on weekday mornings. Goes quiet on Fridays — every time.<br /><br />
                              Last 3 deals closed with short, direct proposals.<br />
                              Last contact: 6 days ago. Zilo has follow-up ready.
                            </p>
                          </div>
                        </div>

                        {/* James Henderson */}
                        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-sm flex flex-col justify-between hover:border-slate-300 transition duration-150">
                          <div>
                            <h3 className="text-sm font-semibold text-slate-900">James Henderson</h3>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Henderson follow-up</p>
                            <p className="font-mono text-xs text-slate-600 mt-3 leading-relaxed">
                              8 conversations since January 2025.<br /><br />
                              Says "let me think about it" in 6 of 8 threads. Stalls mean cost concern.<br /><br />
                              Proposals leading with ROI closed. Proposals leading with features stalled.<br /><br />
                              Has not heard from you in 3 weeks. Opportunity flagged.
                            </p>
                          </div>
                        </div>

                        {/* David Ochieng */}
                        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-sm flex flex-col justify-between hover:border-slate-300 transition duration-150">
                          <div>
                            <h3 className="text-sm font-semibold text-slate-900">David Ochieng</h3>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Referred Lead</p>
                            <p className="font-mono text-xs text-slate-600 mt-3 leading-relaxed">
                              Referred by Amina Hassan in February. Was never formally thanked.<br /><br />
                              3 conversations. Last order: 2 months ago. No contact since.<br /><br />
                              Zilo flagged as at risk of going cold. Re-engagement draft ready.
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="pt-2 flex justify-start">
                        <button
                          onClick={() => setActiveTab("people")}
                          className="text-xs font-semibold text-[#059669] hover:text-[#047857] transition flex items-center gap-1 font-mono"
                        >
                          See all 43 people →
                        </button>
                      </div>
                    </div>

                    {/* Section: Your Patterns */}
                    <div className="space-y-4">
                      <div className="border-b border-slate-200 pb-2">
                        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono">
                          YOUR PATTERNS — 6 detected from 6 months
                        </h2>
                      </div>
                      
                      <div className="grid gap-4 md:grid-cols-2">
                        {/* Reply Timing */}
                        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-sm hover:border-slate-300 transition duration-150">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 font-mono">Reply timing</h4>
                          <p className="font-mono text-xs text-slate-600 mt-2 leading-relaxed">
                            Your reply rate drops significantly on Tuesdays across all channels. Best window: 7–9am and after 6pm. Worst window: Tuesday midday.
                          </p>
                          <p className="text-[10px] font-medium text-slate-400 font-mono mt-3 uppercase tracking-wider">
                            Confidence: High — 24 weeks of data
                          </p>
                        </div>

                        {/* Referral Pattern */}
                        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-sm hover:border-slate-300 transition duration-150">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 font-mono">Referral pattern</h4>
                          <p className="font-mono text-xs text-slate-600 mt-2 leading-relaxed">
                            4 of your last 6 deals came from referrals that were never formally thanked. The referral chain went cold after each unthanked introduction. Zilo now flags referrals within 24 hours.
                          </p>
                          <p className="text-[10px] font-medium text-slate-400 font-mono mt-3 uppercase tracking-wider">
                            Confidence: High — 6 instances
                          </p>
                        </div>

                        {/* Deal Close Pattern */}
                        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-sm hover:border-slate-300 transition duration-150">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 font-mono">Deal close pattern</h4>
                          <p className="font-mono text-xs text-slate-600 mt-2 leading-relaxed">
                            Deals close faster when you follow up within 48 hours of a positive signal. Average close time with fast follow-up: 6 days. Average close time without: 23 days.
                          </p>
                          <p className="text-[10px] font-medium text-slate-400 font-mono mt-3 uppercase tracking-wider">
                            Confidence: High — 11 deals analysed
                          </p>
                        </div>

                        {/* Cold Deal Pattern */}
                        <div className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-sm hover:border-slate-300 transition duration-150">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 font-mono">Cold deal pattern</h4>
                          <p className="font-mono text-xs text-slate-600 mt-2 leading-relaxed">
                            Deals that go quiet for more than 7 days rarely close without a direct — not warm — follow-up. Warm follow-ups after 7 days: closed 1 of 8. Direct follow-ups: closed 5 of 7.
                          </p>
                          <p className="text-[10px] font-medium text-slate-400 font-mono mt-3 uppercase tracking-wider">
                            Confidence: High — 15 deals
                          </p>
                        </div>
                      </div>

                      <div className="pt-2 flex justify-start">
                        <button
                          onClick={() => setActiveTab("patterns")}
                          className="text-xs font-semibold text-[#059669] hover:text-[#047857] transition flex items-center gap-1 font-mono"
                        >
                          See all 6 patterns →
                        </button>
                      </div>
                    </div>

                    {/* Section: Your Communication Style */}
                    <div className="space-y-4">
                      <div className="border-b border-slate-200 pb-2">
                        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono">
                          YOUR COMMUNICATION STYLE
                        </h2>
                      </div>
                      
                      <div className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-sm space-y-4 hover:border-slate-300 transition duration-150">
                        <div className="grid gap-6 sm:grid-cols-2 font-mono text-xs">
                          <div className="space-y-2">
                            <h4 className="font-bold text-slate-700 uppercase tracking-wider text-[11px]">Core Preferences</h4>
                            <ul className="list-disc list-inside text-slate-600 space-y-1.5">
                              <li>Short messages. No formal sign-offs.</li>
                              <li>Direct language. No pleasantries.</li>
                              <li>Writes even shorter on mobile.</li>
                            </ul>
                          </div>

                          <div className="space-y-2.5">
                            <h4 className="font-bold text-slate-700 uppercase tracking-wider text-[11px]">Email Analysis metrics</h4>
                            <div className="grid grid-cols-2 gap-y-2 text-slate-600">
                              <div>Average length (desktop):</div>
                              <div className="font-bold text-slate-900">{data.communication_style?.average_word_count ?? 28} words</div>
                              
                              <div>Average length (mobile):</div>
                              <div className="font-bold text-slate-900">{data.communication_style?.average_word_count_mobile ?? 14} words</div>
                              
                              <div>Greeting Phrases:</div>
                              <div className="font-bold text-slate-900">{data.communication_style?.greetings ?? "None (0%)"}</div>
                              
                              <div>Sign-off Patterns:</div>
                              <div className="font-bold text-slate-900">{data.communication_style?.sign_offs ?? "None (0%)"}</div>
                              
                              <div>Sentence Length:</div>
                              <div className="font-bold text-slate-900">{data.communication_style?.sentence_length ?? "Short (8 words)"}</div>

                              <div>Formality Score:</div>
                              <div className="font-bold text-[#059669]">{data.communication_style?.formality_score ?? "Informal"}</div>
                            </div>
                          </div>
                        </div>

                        <div className="pt-4 border-t border-slate-100 font-mono text-xs text-slate-500 flex items-start gap-2">
                          <Sparkles className="h-4 w-4 text-[#059669] shrink-0 mt-0.5" />
                          <span>
                            <strong>Anti-pleasantry filter:</strong> You never use <em>"I hope this finds you well"</em> in drafts. Zilo has filtered out all greeting pleasantries.
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Section: Your Lanes */}
                    <div className="space-y-4">
                      <div className="border-b border-slate-200 pb-2">
                        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono">
                          YOUR LANES
                        </h2>
                      </div>
                      
                      <div className="bg-white border border-slate-200/80 rounded-xl p-6 shadow-sm hover:border-slate-300 transition duration-150">
                        <p className="text-sm font-semibold text-slate-900">
                          All starting at Observer.
                        </p>
                        <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                          Zilo has read everything but acts on nothing until you approve. First promotion will come in your morning briefing as Zilo earns it lane by lane.
                        </p>
                        
                        <div className="mt-4 pt-4 border-t border-slate-100 flex justify-start">
                          <button
                            onClick={() => setActiveTab("lanes")}
                            className="text-xs font-semibold text-[#059669] hover:text-[#047857] transition flex items-center gap-1 font-mono"
                          >
                            See all lanes →
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* TAB CONTENT: PEOPLE */}
                {activeTab === "people" && (
                  <div className="mt-6">
                    {filteredPeople.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
                        <Users className="mx-auto h-10 w-10 text-slate-300" />
                        <h3 className="mt-3 text-sm font-semibold text-slate-800">No client files found</h3>
                        <p className="mt-1 text-xs text-slate-500 max-w-sm mx-auto">
                          {searchQuery 
                            ? `No match found for "${searchQuery}". Try adjusting your keywords.`
                            : "Inbox events, outbound deals, and manual scout alerts populate entries automatically."}
                        </p>
                        {!searchQuery && (
                          <Link href="/dashboard/email" className="mt-4 inline-block text-xs font-semibold text-[#059669] hover:underline">
                            Go to your Email Inbox →
                          </Link>
                        )}
                      </div>
                    ) : (
                      <div className="border border-slate-200 bg-white rounded-2xl shadow-sm overflow-hidden flex flex-col md:flex-row h-[600px]">
                        {/* List Sidebar (Left Column) */}
                        <div className={`w-full md:w-[350px] border-r border-slate-200 flex flex-col h-full bg-slate-50/50 ${selectedPersonId ? "hidden md:flex" : "flex"}`}>
                          {/* Search & Header */}
                          <div className="p-4 border-b border-slate-200 bg-white">
                            <div className="flex items-center justify-between">
                              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest font-mono">
                                Client Directory
                              </h3>
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-bold text-slate-500 font-mono">
                                {filteredPeople.length} contacts
                              </span>
                            </div>
                            <p className="text-[10px] text-slate-500 mt-1 leading-normal font-sans">
                              Select a contact to view insights and communication parameters.
                            </p>
                          </div>

                          {/* People list */}
                          <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
                            {filteredPeople.map(item => {
                              const isSelected = selectedPerson?.id === item.id;
                              const initial = (item.subject || "C").charAt(0).toUpperCase();
                              
                              // Choose a background color based on name initials
                              const charCode = initial.charCodeAt(0) || 65;
                              const bgColors = [
                                "bg-emerald-500 text-emerald-50",
                                "bg-blue-500 text-blue-50",
                                "bg-indigo-500 text-indigo-50",
                                "bg-purple-500 text-purple-50",
                                "bg-rose-500 text-rose-50",
                                "bg-amber-500 text-amber-50",
                                "bg-cyan-500 text-cyan-50",
                              ];
                              const avatarBg = bgColors[charCode % bgColors.length];

                              return (
                                <button
                                  key={item.id}
                                  onClick={() => {
                                    setSelectedPersonId(item.id);
                                    cancelEdit(); // Reset editing state on swap
                                    cancelEditCompany();
                                  }}
                                  className={`w-full flex items-start gap-3 p-3 text-left transition duration-150 border-l-2 ${
                                    isSelected 
                                      ? "bg-[#ECFDF5]/60 border-[#059669]" 
                                      : "border-transparent hover:bg-slate-100/50 bg-white"
                                  }`}
                                >
                                  <div className={`h-8 w-8 rounded-lg ${avatarBg} flex items-center justify-center text-xs font-bold shrink-0 shadow-sm`}>
                                    {initial}
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <div className="flex items-center justify-between">
                                      <span className={`text-xs font-bold truncate tracking-tight ${isSelected ? "text-emerald-950" : "text-slate-800"}`}>
                                        {item.subject}
                                      </span>
                                      {item.tags.length > 0 && (
                                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[8px] font-bold text-slate-500 uppercase tracking-wider scale-90">
                                          {item.tags[0]}
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-[11px] text-slate-400 truncate mt-0.5 font-sans leading-normal">
                                      {item.text}
                                    </p>
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        {/* Detail Pane (Right Column) */}
                        {selectedPerson ? (() => {
                            const profile = parseContactProfile(selectedPerson, data?.companies || []);
                            return (
                              <div className="flex flex-col h-full overflow-hidden font-sans">
                                {/* Header */}
                                <div className="p-4 md:p-6 border-b border-slate-200 flex items-center justify-between bg-slate-50/30">
                                  <div className="flex items-center gap-3 min-w-0">
                                    {/* Back button on mobile */}
                                    <button 
                                      onClick={() => setSelectedPersonId(null)}
                                      className="md:hidden p-1.5 rounded-lg border border-slate-200 hover:bg-slate-150 transition shrink-0"
                                    >
                                      <ChevronLeft className="h-4 w-4 text-slate-650" />
                                    </button>
                                    
                                    <div className="h-10 w-10 rounded-xl bg-[#ECFDF5] border border-emerald-100 flex items-center justify-center text-[#059669] text-base font-bold shrink-0 shadow-sm font-sans">
                                      {profile.name.charAt(0).toUpperCase()}
                                    </div>
                                    <div className="min-w-0">
                                      <h3 className="text-sm md:text-base font-bold text-slate-900 tracking-tight truncate font-sans">
                                        {profile.name}
                                      </h3>
                                      <div className="flex items-center gap-1.5 mt-0.5 font-sans">
                                        <span className="text-[10px] text-slate-500 font-semibold">
                                          {profile.company}
                                        </span>
                                        <span className="h-1 w-1 rounded-full bg-slate-300" />
                                        <span className="text-[10px] text-slate-400 font-mono">
                                          {profile.role}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                  
                                  {editingId !== selectedPerson.id && (
                                    <div className="flex gap-2">
                                      <button
                                        onClick={() => startEdit(selectedPerson)}
                                        className="rounded-lg border border-slate-250 hover:border-slate-350 hover:bg-slate-50 p-2 text-slate-500 hover:text-slate-750 transition flex items-center gap-1.5 text-xs font-semibold"
                                        title="Edit entry"
                                      >
                                        <Edit2 className="h-3.5 w-3.5" />
                                        <span className="hidden sm:inline">Edit</span>
                                      </button>
                                      <button
                                        onClick={() => deleteEntry(selectedPerson.id)}
                                        className="rounded-lg border border-rose-100 hover:border-rose-200 bg-rose-50/30 hover:bg-rose-55 p-2 text-rose-500 hover:text-rose-650 transition flex items-center gap-1.5 text-xs font-semibold"
                                        title="Delete entry"
                                      >
                                        <Trash2 className="h-3.5 w-3.5" />
                                        <span className="hidden sm:inline">Delete</span>
                                      </button>
                                    </div>
                                  )}
                                </div>

                                {/* Details Scroll Area */}
                                <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
                                  {editingId === selectedPerson.id ? (
                                    <div className="space-y-4 bg-slate-50 border border-slate-200 p-4 md:p-5 rounded-2xl">
                                      <div className="flex items-center justify-between">
                                        <span className="text-xs font-bold text-slate-800">Edit Knowledge Profile</span>
                                        <span className="text-[10px] text-slate-400 font-mono">ID: {selectedPerson.id.substring(0,8)}</span>
                                      </div>
                                      <textarea
                                        value={editingText}
                                        onChange={e => setEditingText(e.target.value)}
                                        className="w-full rounded-xl border border-slate-300 bg-white p-3 font-mono text-xs text-slate-850 focus:border-[#059669] focus:outline-none focus:ring-1 focus:ring-[#059669] min-h-[180px] shadow-sm leading-relaxed"
                                        rows={6}
                                      />
                                      <div className="flex items-center justify-between text-[11px] text-slate-500">
                                        <span className="flex items-center gap-1">💡 Present tense preferred for rules</span>
                                        <div className="flex gap-2">
                                          <button 
                                            onClick={cancelEdit}
                                            className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 px-3 py-1.5 flex items-center gap-1 text-xs font-semibold transition"
                                          >
                                            <X className="h-3.5 w-3.5" /> Cancel
                                          </button>
                                          <button 
                                            onClick={() => saveEdit(selectedPerson.id)}
                                            className="rounded-lg bg-[#059669] hover:bg-[#047857] text-white px-3 py-1.5 flex items-center gap-1 text-xs font-semibold transition shadow-sm"
                                          >
                                            <Check className="h-3.5 w-3.5" /> Save Changes
                                          </button>
                                        </div>
                                      </div>
                                    </div>
                                  ) : (
                                    <div className="divide-y divide-slate-100 space-y-6">
                                      
                                      {/* SECTION 1: ZILO'S READ */}
                                      <div className="space-y-3 pb-6">
                                        <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                          Zilo's Read on {profile.name.split(" ")[0]}
                                        </h4>
                                        <div className="grid grid-cols-2 gap-4">
                                          <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
                                            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider font-mono">Email History</p>
                                            <p className="text-xs font-bold text-slate-800 mt-0.5">{profile.history.messageCount} messages</p>
                                          </div>
                                          <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
                                            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider font-mono">Relationship Health</p>
                                            <span className={`inline-block mt-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                              profile.relationshipHealth === "Warm" ? "bg-emerald-50 text-emerald-700 border border-emerald-150" : "bg-slate-50 text-slate-500"
                                            }`}>{profile.relationshipHealth}</span>
                                          </div>
                                          <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
                                            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider font-mono">First Contact</p>
                                            <p className="text-xs font-bold text-slate-700 mt-0.5">{profile.firstContact}</p>
                                          </div>
                                          <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
                                            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider font-mono">Last Contact</p>
                                            <p className="text-xs font-bold text-slate-700 mt-0.5">{profile.lastContact}</p>
                                          </div>
                                        </div>
                                      </div>

                                      {/* SECTION 2: HOW COMMUNICATES */}
                                      <div className="space-y-3 pt-6 pb-6">
                                        <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                          How She Communicates
                                        </h4>
                                        <div className="space-y-2.5">
                                          <div className="flex items-start gap-2.5 p-3 rounded-xl border border-emerald-100 bg-[#ECFDF5]/30">
                                            <Calendar className="h-4 w-4 text-[#059669] mt-0.5 shrink-0" />
                                            <p className="text-xs text-slate-700 leading-normal">{profile.commStyle.bestDayTime}</p>
                                          </div>
                                          <div className="flex items-start gap-2.5 p-3 rounded-xl border border-slate-150 bg-slate-50/50">
                                            <CheckCircle2 className="h-4 w-4 text-slate-450 mt-0.5 shrink-0" />
                                            <p className="text-xs text-slate-700 leading-normal">{profile.commStyle.lengthPref}</p>
                                          </div>
                                          <div className="flex items-start gap-2.5 p-3 rounded-xl border border-slate-150 bg-slate-50/50">
                                            <X className="h-4 w-4 text-slate-400 mt-0.5 shrink-0" />
                                            <p className="text-xs text-slate-700 leading-normal">{profile.commStyle.paragraphLimit}</p>
                                          </div>
                                        </div>
                                      </div>

                                      {/* SECTION 3: WHAT ZILO HAS NOTICED */}
                                      <div className="space-y-3 pt-6 pb-6">
                                        <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                          What Zilo Has Noticed
                                        </h4>
                                        <div className="space-y-2.5">
                                          {profile.observations.map((obs, idx) => (
                                            <div key={idx} className="flex gap-2.5 items-start">
                                              <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-[#059669] mt-1.5" />
                                              <p className="text-xs text-slate-700 leading-normal font-sans">{obs}</p>
                                            </div>
                                          ))}
                                        </div>
                                      </div>

                                      {/* SECTION 4: ACTIVE THREADS */}
                                      <div className="space-y-3 pt-6 pb-6">
                                        <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                          Active Threads
                                        </h4>
                                        <div className="divide-y divide-slate-100">
                                          {profile.activeThreads.map((thread, idx) => (
                                            <div key={idx} className="py-3 first:pt-0 last:pb-0 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                                              <div>
                                                <h5 className="text-xs font-bold text-slate-800">{thread.subject}</h5>
                                                <div className="flex items-center gap-2 mt-1">
                                                  <span className="text-[10px] text-slate-400 font-mono">Last action: {thread.lastMessage}</span>
                                                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[8px] font-bold text-slate-500 uppercase tracking-wider">{thread.status}</span>
                                                </div>
                                              </div>
                                              <div className="flex gap-2 shrink-0">
                                                <Link 
                                                  href={`/dashboard/email?q=${encodeURIComponent(thread.subject)}`}
                                                  className="rounded-lg border border-slate-200 hover:bg-slate-50 text-[10px] font-semibold text-slate-700 px-2 py-1 transition flex items-center justify-center"
                                                >
                                                  Read it first
                                                </Link>
                                                {thread.draftReady && (
                                                  <button 
                                                    onClick={() => openReviewDraft(profile.recommendedAction.draftSubject, profile.recommendedAction.draftBody)}
                                                    className="rounded-lg bg-[#059669] hover:bg-[#047857] text-[10px] font-semibold text-white px-2 py-1 transition"
                                                  >
                                                    Send follow-up
                                                  </button>
                                                )}
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      </div>

                                      {/* SECTION 5: HISTORY */}
                                      <div className="space-y-3 pt-6 pb-6">
                                        <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                          History
                                        </h4>
                                        <div className="space-y-4">
                                          <div>
                                            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider font-mono">Topics Discussed</p>
                                            <div className="flex flex-wrap gap-1.5 mt-1.5">
                                              {profile.history.topics.map(t => (
                                                <span key={t} className="rounded bg-slate-100 px-2 py-0.5 text-[10px] text-slate-650 font-medium">
                                                  {t}
                                                </span>
                                              ))}
                                            </div>
                                          </div>
                                          <div>
                                            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider font-mono mb-2">Deals</p>
                                            <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 divide-y divide-slate-200/50 space-y-2.5">
                                              {profile.history.deals.map((deal, idx) => (
                                                <div key={idx} className="flex justify-between text-xs py-1.5 first:pt-0 last:pb-0 font-sans">
                                                  <span className="font-bold text-slate-700">{deal.period}</span>
                                                  <span className="text-slate-500 font-medium">{deal.stage}</span>
                                                  <span className="font-bold text-slate-800">{deal.value}</span>
                                                </div>
                                              ))}
                                            </div>
                                          </div>
                                        </div>
                                      </div>

                                      {/* SECTION 6: PERSONAL DETAILS */}
                                      <div className="space-y-3 pt-6 pb-6">
                                        <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                          Personal Details Zilo Picked Up
                                        </h4>
                                        <div className="space-y-2 bg-emerald-50/20 border border-emerald-100 p-4 rounded-xl">
                                          {profile.personalDetails.map((detail, idx) => (
                                            <div key={idx} className="flex gap-2 items-start text-xs text-slate-700">
                                              <Sparkles className="h-3.5 w-3.5 text-[#059669] shrink-0 mt-0.5" />
                                              <p className="leading-normal">{detail}</p>
                                            </div>
                                          ))}
                                        </div>
                                      </div>

                                      {/* SECTION 7: RECOMMENDED ACTION */}
                                      <div className="pt-6 pb-6 space-y-4">
                                        <div className="bg-[#FAF9F6] border border-amber-200 p-5 rounded-2xl shadow-sm space-y-4">
                                          <div className="flex items-center gap-1.5">
                                            <Sparkles className="h-4.5 w-4.5 text-amber-500" />
                                            <h5 className="text-[10px] font-bold text-slate-800 uppercase tracking-widest font-mono">Zilo's Next Recommended Action</h5>
                                          </div>
                                          <p className="text-xs text-slate-700 leading-normal font-medium">{profile.recommendedAction.summary}</p>
                                          
                                          <div className="p-3 bg-white border border-slate-200 rounded-xl text-[11px] font-mono text-slate-500 space-y-1">
                                            <p className="font-bold text-slate-700">Draft ready and waiting.</p>
                                            <p className="mt-1 line-clamp-2 italic">"{profile.recommendedAction.draftBody.split('\n')[2]}"</p>
                                          </div>
                                          
                                          <div className="flex gap-2">
                                            <button 
                                              onClick={() => openReviewDraft(profile.recommendedAction.draftSubject, profile.recommendedAction.draftBody)}
                                              className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 px-3.5 py-1.5 text-xs font-semibold shadow-sm transition active:scale-95 duration-100"
                                            >
                                              Review draft
                                            </button>
                                            <button 
                                              onClick={() => toast.success(`Draft sent to ${profile.name.split(" ")[0]}!`)}
                                              className="rounded-lg bg-[#059669] hover:bg-[#047857] text-white px-3.5 py-1.5 text-xs font-semibold shadow-sm transition active:scale-95 duration-100"
                                            >
                                              Send it
                                            </button>
                                            <button 
                                              onClick={() => toast.info("Action postponed.")}
                                              className="rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-500 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100"
                                            >
                                              Not now
                                            </button>
                                          </div>
                                        </div>
                                      </div>

                                      {/* SECTION 8: CONNECTED ACCOUNTS */}
                                      <div className="pt-6 space-y-3 pb-4">
                                        <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                          Connected Accounts
                                        </h4>
                                        <div className="text-xs text-slate-655 space-y-2">
                                          <p><strong>Company:</strong> {profile.company}</p>
                                          <p><strong>Role:</strong> {profile.role}</p>
                                          <p><strong>Colleagues in threads:</strong> None yet</p>
                                          <p><strong>LinkedIn:</strong> Not connected</p>
                                        </div>
                                        <button
                                          onClick={() => toast.info(`Searching LinkedIn for ${profile.name}...`)}
                                          className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-[#059669] hover:underline"
                                        >
                                        <ExternalLink className="h-3.5 w-3.5" /> Find {profile.name.split(" ")[0]} on LinkedIn
                                        </button>
                                      </div>

                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          })() : (
                            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-slate-50/20">
                              <Users className="h-12 w-12 text-slate-300" />
                              <h4 className="mt-3 text-sm font-semibold text-slate-800">No contact selected</h4>
                              <p className="text-xs text-slate-400 mt-1 max-w-xs">
                                Select a person from the client directory on the left to see full details.
                              </p>
                            </div>
                          )}
                      </div>
                    )}
                  </div>
                )}
                 {/* TAB CONTENT: COMPANIES */}
                {activeTab === "companies" && (
                  <div className="mt-6 font-sans">
                    {filteredCompanies.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
                        <Building2 className="mx-auto h-10 w-10 text-slate-300" />
                        <h3 className="mt-3 text-sm font-semibold text-slate-800">No company files found</h3>
                        <p className="mt-1 text-xs text-slate-500 max-w-sm mx-auto">
                          {searchQuery 
                            ? `No match found for "${searchQuery}". Try adjusting your keywords.`
                            : "No companies found in your database history."}
                        </p>
                      </div>
                    ) : (
                      <div className="border border-slate-200 bg-white rounded-2xl shadow-sm overflow-hidden flex flex-col md:flex-row h-[600px]">
                        {/* List Sidebar (Left Column) */}
                        <div className={`w-full md:w-[350px] border-r border-slate-200 flex flex-col h-full bg-slate-50/50 ${selectedCompanyId ? "hidden md:flex" : "flex"}`}>
                          {/* Search & Header */}
                          <div className="p-4 border-b border-slate-200 bg-white">
                            <div className="flex items-center justify-between">
                              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest font-mono">
                                Company Directory
                              </h3>
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-bold text-slate-500 font-mono">
                                {filteredCompanies.length} companies
                              </span>
                            </div>
                            <p className="text-[10px] text-slate-500 mt-1 leading-normal font-sans">
                              Select a company to view profiles and recommended drafts.
                            </p>
                          </div>

                          {/* Companies list */}
                          <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
                            {filteredCompanies.map(comp => {
                              const isSelected = selectedCompany?.id === comp.id;
                              const initial = comp.name.charAt(0).toUpperCase();
                              
                              // Choose a background color based on name initials
                              const charCode = initial.charCodeAt(0) || 65;
                              const bgColors = [
                                "bg-emerald-500 text-emerald-50",
                                "bg-blue-500 text-blue-50",
                                "bg-indigo-500 text-indigo-50",
                                "bg-purple-500 text-purple-50",
                                "bg-rose-500 text-rose-50",
                                "bg-amber-500 text-amber-50",
                                "bg-cyan-500 text-cyan-50",
                              ];
                              const avatarBg = bgColors[charCode % bgColors.length];

                              return (
                                <button
                                  key={comp.id}
                                  onClick={() => {
                                    setSelectedCompanyId(comp.id);
                                    cancelEditCompany();
                                    cancelEdit();
                                  }}
                                  className={`w-full flex items-start gap-3 p-3 text-left transition duration-150 border-l-2 ${
                                    isSelected 
                                      ? "bg-[#ECFDF5]/60 border-[#059669]" 
                                      : "border-transparent hover:bg-slate-100/50 bg-white"
                                  }`}
                                >
                                  <div className={`h-8 w-8 rounded-lg ${avatarBg} flex items-center justify-center text-xs font-bold shrink-0 shadow-sm`}>
                                    {initial}
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <div className="flex items-center justify-between">
                                      <span className={`text-xs font-bold truncate tracking-tight ${isSelected ? "text-emerald-950" : "text-slate-800"}`}>
                                        {comp.name}
                                      </span>
                                      <span className={`px-1.5 py-0.5 rounded-full border text-[7px] font-bold uppercase tracking-wider scale-90 shrink-0 ${
                                        comp.health === "Warm" ? "bg-emerald-50 text-emerald-700 border-emerald-150" :
                                        comp.health === "Cooling" ? "bg-amber-50 text-amber-700 border-amber-150" :
                                        comp.health === "Cold" ? "bg-blue-50 text-blue-700 border-blue-150" :
                                        comp.health === "At risk" ? "bg-rose-50 text-rose-700 border-rose-150" :
                                        comp.health === "Won" ? "bg-teal-50 text-teal-700 border-teal-150" :
                                        "bg-slate-50 text-slate-700 border-slate-150"
                                      }`}>
                                        {comp.health}
                                      </span>
                                    </div>
                                    <div className="flex justify-between items-center mt-1 text-[10px] text-slate-400 font-mono">
                                      <span>{comp.conversations_count} threads</span>
                                      <span>{comp.deal_value}</span>
                                    </div>
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        {/* Detail Pane (Right Column) */}
                        {selectedCompany ? (() => {
                          const profile = parseCompanyProfile(selectedCompany);
                          return (
                            <div className="flex-1 flex flex-col h-full overflow-hidden font-sans">
                              {/* Header */}
                              <div className="p-4 md:p-6 border-b border-slate-200 flex items-center justify-between bg-slate-50/30">
                                <div className="flex items-center gap-3 min-w-0">
                                  {/* Back button on mobile */}
                                  <button 
                                    onClick={() => setSelectedCompanyId(null)}
                                    className="md:hidden p-1.5 rounded-lg border border-slate-200 hover:bg-slate-150 transition shrink-0"
                                  >
                                    <ChevronLeft className="h-4 w-4 text-slate-650" />
                                  </button>
                                  
                                  <div className="h-10 w-10 rounded-xl bg-[#ECFDF5] border border-emerald-100 flex items-center justify-center text-[#059669] text-base font-bold shrink-0 shadow-sm font-sans">
                                    <Building2 className="h-5 w-5" />
                                  </div>
                                  <div className="min-w-0">
                                    <h3 className="text-sm md:text-base font-bold text-slate-900 tracking-tight truncate font-sans">
                                      {profile.name}
                                    </h3>
                                    <div className="flex items-center gap-1.5 mt-0.5 font-sans">
                                      <span className={`px-1.5 py-0.5 rounded-full border text-[8px] font-bold uppercase tracking-wider ${
                                        profile.health === "Warm" ? "bg-emerald-50 text-emerald-700 border-emerald-150" :
                                        profile.health === "Cooling" ? "bg-amber-50 text-amber-700 border-amber-150" :
                                        profile.health === "Cold" ? "bg-blue-50 text-blue-700 border-blue-150" :
                                        profile.health === "At risk" ? "bg-rose-50 text-rose-700 border-rose-150" :
                                        profile.health === "Won" ? "bg-teal-50 text-teal-700 border-teal-150" :
                                        "bg-slate-50 text-slate-700 border-slate-150"
                                      }`}>
                                        {profile.health}
                                      </span>
                                      <span className="h-1 w-1 rounded-full bg-slate-300" />
                                      <span className="text-[10px] text-slate-400 font-mono">
                                        {profile.conversationsCount} threads
                                      </span>
                                    </div>
                                  </div>
                                </div>
                                
                                {editingCompanyId !== selectedCompany.id && (
                                  <div className="flex gap-2">
                                    <button
                                      onClick={() => startEditCompany(selectedCompany)}
                                      className="rounded-lg border border-slate-250 hover:border-slate-350 hover:bg-slate-50 p-2 text-slate-500 hover:text-slate-750 transition flex items-center gap-1.5 text-xs font-semibold"
                                      title="Edit description"
                                    >
                                      <Edit2 className="h-3.5 w-3.5" />
                                      <span className="hidden sm:inline">Edit</span>
                                    </button>
                                    <button
                                      onClick={() => deleteCompany(selectedCompany.id)}
                                      className="rounded-lg border border-rose-100 hover:border-rose-200 bg-rose-50/30 hover:bg-rose-55 p-2 text-rose-500 hover:text-rose-650 transition flex items-center gap-1.5 text-xs font-semibold"
                                      title="Archive company"
                                    >
                                      <Trash2 className="h-3.5 w-3.5" />
                                      <span className="hidden sm:inline">Archive</span>
                                    </button>
                                  </div>
                                )}
                              </div>

                              {/* Details Scroll Area */}
                              <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
                                {editingCompanyId === selectedCompany.id ? (
                                  <div className="space-y-4 bg-slate-50 border border-slate-200 p-4 md:p-5 rounded-2xl">
                                    <div className="flex items-center justify-between">
                                      <span className="text-xs font-bold text-slate-800">Edit Company Description</span>
                                      <span className="text-[10px] text-slate-400 font-mono">ID: {selectedCompany.id.substring(0,8)}</span>
                                    </div>
                                    <textarea
                                      value={editingCompanyText}
                                      onChange={e => setEditingCompanyText(e.target.value)}
                                      className="w-full rounded-xl border border-slate-300 bg-white p-3 font-mono text-xs text-slate-850 focus:border-[#059669] focus:outline-none focus:ring-1 focus:ring-[#059669] min-h-[120px] shadow-sm leading-relaxed"
                                      rows={4}
                                    />
                                    <div className="flex items-center justify-end text-[11px] text-slate-500">
                                      <div className="flex gap-2">
                                        <button 
                                          onClick={cancelEditCompany}
                                          className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 px-3 py-1.5 flex items-center gap-1 text-xs font-semibold transition"
                                        >
                                          <X className="h-3.5 w-3.5" /> Cancel
                                        </button>
                                        <button 
                                          onClick={() => saveEditCompany(selectedCompany.id)}
                                          className="rounded-lg bg-[#059669] hover:bg-[#047857] text-white px-3 py-1.5 flex items-center gap-1 text-xs font-semibold transition shadow-sm"
                                        >
                                          <Check className="h-3.5 w-3.5" /> Save Changes
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="divide-y divide-slate-100 space-y-6">
                                    
                                    {/* SECTION 1: ZILO'S READ */}
                                    <div className="space-y-3 pb-6">
                                      <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                        Zilo's Read on {profile.name}
                                      </h4>
                                      <p className="text-xs font-semibold text-slate-700 bg-[#FAF9F6] border border-slate-200/80 rounded-xl p-3.5 leading-relaxed">
                                        {profile.description}
                                      </p>
                                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-2">
                                        {[
                                          { label: "First Contact", value: profile.firstContact },
                                          { label: "Total Conversations", value: `${profile.conversationsCount} threads` },
                                          { label: "Total Deals", value: `${profile.totalDeals} deals` },
                                          { label: "Total Revenue", value: profile.totalRevenue },
                                          { label: "Current Opportunity", value: profile.dealValue },
                                          { label: "Relationship Health", value: profile.health }
                                        ].map((item, idx) => (
                                          <div key={idx} className="bg-slate-50 rounded-xl p-3 border border-slate-100">
                                            <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider font-mono">{item.label}</p>
                                            <p className="text-xs font-bold text-slate-800 mt-0.5">{item.value}</p>
                                          </div>
                                        ))}
                                      </div>
                                    </div>

                                    {/* SECTION 2: HOW THEY COMMUNICATE */}
                                    <div className="space-y-3 pt-6 pb-6">
                                      <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                        How They Communicate
                                      </h4>
                                      <div className="space-y-2.5">
                                        <div className="flex items-start gap-2.5 p-3 rounded-xl border border-emerald-100 bg-[#ECFDF5]/30">
                                          <Calendar className="h-4 w-4 text-[#059669] mt-0.5 shrink-0" />
                                          <p className="text-xs text-slate-700 leading-normal">{profile.commStyle.bestDayTime}</p>
                                        </div>
                                        <div className="flex items-start gap-2.5 p-3 rounded-xl border border-slate-150 bg-slate-50/50">
                                          <CheckCircle2 className="h-4 w-4 text-slate-450 mt-0.5 shrink-0" />
                                          <p className="text-xs text-slate-700 leading-normal">{profile.commStyle.lengthPref}</p>
                                        </div>
                                        <div className="flex items-start gap-2.5 p-3 rounded-xl border border-slate-150 bg-slate-50/50">
                                          <Sparkles className="h-4 w-4 text-[#059669] mt-0.5 shrink-0" />
                                          <p className="text-xs text-slate-700 leading-normal">{profile.commStyle.toneTip}</p>
                                        </div>
                                      </div>
                                    </div>

                                    {/* SECTION 3: KEY CONTACTS */}
                                    <div className="space-y-3 pt-6 pb-6">
                                      <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                        Contacts at this Company
                                      </h4>
                                      <div className="divide-y divide-slate-100 bg-slate-50/50 border border-slate-100 rounded-xl p-3.5 space-y-1">
                                        {selectedCompany.contacts.map((contact, idx) => (
                                          <div key={idx} className="py-2.5 first:pt-0 last:pb-0 flex items-start justify-between gap-4">
                                            <div className="min-w-0">
                                              <p className="text-xs font-bold text-slate-800">{contact.name}</p>
                                              <p className="text-[10px] text-slate-500 mt-0.5 leading-normal">{contact.role}</p>
                                              <p className="text-[9px] text-slate-400 mt-1 font-mono">Last active: {contact.last_message}</p>
                                            </div>
                                            {contact.profile_id && (
                                              <button 
                                                onClick={() => {
                                                  setActiveTab("people");
                                                  setSelectedPersonId(contact.profile_id || null);
                                                  cancelEdit();
                                                  cancelEditCompany();
                                                }}
                                                className="text-[10px] font-bold text-[#059669] hover:underline shrink-0 bg-white border border-slate-200 px-2 py-1 rounded shadow-sm hover:bg-slate-50"
                                              >
                                                See profile
                                              </button>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    </div>

                                    {/* SECTION 4: ACTIVE THREADS */}
                                    <div className="space-y-3 pt-6 pb-6">
                                      <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                        Active Threads
                                      </h4>
                                      <div className="divide-y divide-slate-100">
                                        {selectedCompany.active_threads.map((thread, idx) => (
                                          <div key={idx} className="py-3 first:pt-0 last:pb-0 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                                            <div>
                                              <h5 className="text-xs font-bold text-slate-800">{thread.subject}</h5>
                                              <div className="flex items-center gap-2 mt-1">
                                                <span className="text-[10px] text-slate-400 font-mono">Started: {thread.started_at}</span>
                                                <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider ${
                                                  thread.action_ready ? "bg-amber-50 text-amber-700" : "bg-slate-50 text-slate-500"
                                                }`}>{thread.status}</span>
                                              </div>
                                            </div>
                                            <div className="flex gap-2 shrink-0">
                                              <Link 
                                                href={`/dashboard/email?q=${encodeURIComponent(thread.subject)}`}
                                                className="rounded-lg border border-slate-200 hover:bg-slate-50 text-[10px] font-semibold text-slate-700 px-2 py-1 transition flex items-center justify-center"
                                              >
                                                See thread
                                              </Link>
                                              {thread.action_ready && (
                                                <button 
                                                  onClick={() => openReviewDraft(profile.recommendedAction.draftSubject, profile.recommendedAction.draftBody)}
                                                  className="rounded-lg bg-[#059669] hover:bg-[#047857] text-[10px] font-semibold text-white px-2 py-1 transition"
                                                >
                                                  Send follow-up
                                                </button>
                                              )}
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    </div>

                                    {/* SECTION 5: DEAL HISTORY */}
                                    <div className="space-y-3 pt-6 pb-6">
                                      <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                        Deal History
                                      </h4>
                                      <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
                                        <table className="w-full text-left text-xs font-sans">
                                          <thead>
                                            <tr className="border-b border-slate-200/50 text-slate-400 font-bold">
                                              <th className="py-2">Deal Title</th>
                                              <th className="py-2">Value</th>
                                              <th className="py-2">Status</th>
                                            </tr>
                                          </thead>
                                          <tbody className="divide-y divide-slate-100/50">
                                            {selectedCompany.deal_history.map((deal, idx) => (
                                              <tr key={idx} className="hover:bg-slate-100/30">
                                                <td className="py-2 font-semibold text-slate-800">{deal.title}</td>
                                                <td className="py-2 font-bold text-slate-700 font-mono">{deal.value}</td>
                                                <td className="py-2">
                                                  <span className={`inline-block px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider ${
                                                    deal.status === "Won" ? "bg-emerald-50 text-emerald-700" :
                                                    deal.status === "Lost" ? "bg-rose-50 text-rose-700" :
                                                    "bg-amber-50 text-amber-700"
                                                  }`}>
                                                    {deal.status}
                                                  </span>
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    </div>

                                    {/* SECTION 6: OPPORTUNITIES & LOGIC */}
                                    <div className="space-y-3 pt-6 pb-6">
                                      <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono">
                                        Opportunities & Account Logic Zilo Identified
                                      </h4>
                                      <div className="space-y-2 bg-emerald-50/20 border border-emerald-100 p-4 rounded-xl">
                                        {profile.opportunities.map((opp, idx) => (
                                          <div key={idx} className="flex gap-2 items-start text-xs text-slate-700">
                                            <Sparkles className="h-3.5 w-3.5 text-[#059669] shrink-0 mt-0.5" />
                                            <p className="leading-normal">{opp}</p>
                                          </div>
                                        ))}
                                      </div>
                                    </div>

                                    {/* SECTION 7: RECOMMENDED ACTION */}
                                    <div className="pt-6 pb-6 space-y-4">
                                      <div className="bg-[#FAF9F6] border border-amber-200 p-5 rounded-2xl shadow-sm space-y-4">
                                        <div className="flex items-center gap-1.5">
                                          <Sparkles className="h-4.5 w-4.5 text-amber-500" />
                                          <h5 className="text-[10px] font-bold text-slate-800 uppercase tracking-widest font-mono">Zilo's Next Recommended Action</h5>
                                        </div>
                                        <p className="text-xs text-slate-700 leading-normal font-medium">{profile.recommendedAction.summary}</p>
                                        
                                        <div className="p-3 bg-white border border-slate-200 rounded-xl text-[11px] font-mono text-slate-500 space-y-1">
                                          <p className="font-bold text-slate-700">Draft ready and waiting.</p>
                                          <p className="mt-1 line-clamp-2 italic">"{profile.recommendedAction.draftBody.split('\n')[2]}"</p>
                                        </div>
                                        
                                        <div className="flex gap-2">
                                          <button 
                                            onClick={() => openReviewDraft(profile.recommendedAction.draftSubject, profile.recommendedAction.draftBody)}
                                            className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 px-3.5 py-1.5 text-xs font-semibold shadow-sm transition active:scale-95 duration-100"
                                          >
                                            Review draft
                                          </button>
                                          <button 
                                            onClick={() => toast.success(`Draft sent to ${profile.name} team!`)}
                                            className="rounded-lg bg-[#059669] hover:bg-[#047857] text-white px-3.5 py-1.5 text-xs font-semibold shadow-sm transition active:scale-95 duration-100"
                                          >
                                            Send it
                                          </button>
                                          <button 
                                            onClick={() => toast.info("Action postponed.")}
                                            className="rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-500 px-3.5 py-1.5 text-xs font-semibold transition active:scale-95 duration-100"
                                          >
                                            Not now
                                          </button>
                                        </div>
                                      </div>
                                    </div>

                                    {/* SECTION 8: PATTERNS ZILO NOTICED */}
                                    <div className="pt-6 space-y-3 pb-4">
                                      <h4 className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest font-mono flex items-center gap-1.5">
                                        <Sparkles className="h-4 w-4 text-[#059669]" />
                                        Behavioral Patterns
                                      </h4>
                                      <div className="grid gap-3 sm:grid-cols-2">
                                        {selectedCompany.patterns.map((pat, idx) => (
                                          <div key={idx} className="bg-slate-50 border border-slate-100 rounded-xl p-3 shadow-sm space-y-1.5">
                                            <div className="flex items-center justify-between">
                                              <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider font-mono">Account Logic</span>
                                              <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[8px] font-bold text-[#059669] uppercase tracking-wider">{pat.confidence} Confidence</span>
                                            </div>
                                            <p className="text-xs text-slate-700 leading-normal">
                                              {pat.pattern}
                                            </p>
                                          </div>
                                        ))}
                                      </div>
                                    </div>

                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })() : (
                          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-slate-50/20 font-sans">
                            <Building2 className="h-12 w-12 text-slate-300" />
                            <h4 className="mt-3 text-sm font-semibold text-slate-800">No company selected</h4>
                            <p className="text-xs text-slate-400 mt-1 max-w-xs">
                              Select a company from the directory on the left to see full details.
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* TAB CONTENT: PATTERNS */}
                {activeTab === "patterns" && (
                  <div className="mt-6">
                    {filteredPatterns.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
                        <Sparkles className="mx-auto h-10 w-10 text-slate-300" />
                        <h3 className="mt-3 text-sm font-semibold text-slate-800">No operational insights</h3>
                        <p className="mt-1 text-xs text-slate-500 max-w-sm mx-auto">
                          {searchQuery 
                            ? `No matching insights for "${searchQuery}".`
                            : "Zilo will flag behavioral patterns (pricing reactions, referral structures, timing optimization) once 3 identical events occur."}
                        </p>
                      </div>
                    ) : (
                      <div className="grid gap-4 sm:grid-cols-2">
                        {filteredPatterns.map(item => (
                          <div 
                            key={item.id} 
                            className="group flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300 hover:shadow transition duration-200"
                          >
                            <div>
                              <div className="flex items-start justify-between gap-2">
                                <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
                                  {item.subject || "General Mechanics"}
                                </h3>
                                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-bold text-[#059669] uppercase tracking-wider">
                                  Insight
                                </span>
                              </div>

                              <div className="mt-3">
                                {editingId === item.id ? (
                                  <div className="space-y-2">
                                    <textarea
                                      value={editingText}
                                      onChange={e => setEditingText(e.target.value)}
                                      className="w-full rounded-lg border border-slate-300 bg-slate-50 p-2.5 font-mono text-xs text-slate-800 focus:border-[#059669] focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#059669] min-h-[90px]"
                                      rows={4}
                                    />
                                    <div className="flex items-center justify-between text-[10px] text-slate-400">
                                      <span>💡 Present tense preferred</span>
                                      <div className="flex gap-1">
                                        <button 
                                          onClick={cancelEdit}
                                          className="rounded bg-slate-100 hover:bg-slate-200 text-slate-700 px-2 py-1 flex items-center gap-0.5 font-semibold transition"
                                        >
                                          <X className="h-3 w-3" /> Cancel
                                        </button>
                                        <button 
                                          onClick={() => saveEdit(item.id)}
                                          className="rounded bg-[#059669] hover:bg-[#047857] text-white px-2 py-1 flex items-center gap-0.5 font-semibold transition"
                                        >
                                          <Check className="h-3 w-3" /> Save
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                ) : (
                                  <p className="font-mono text-xs leading-relaxed text-slate-700 whitespace-pre-line bg-slate-50/50 p-2.5 rounded-lg border border-slate-100">
                                    {item.text}
                                  </p>
                                )}
                              </div>
                            </div>

                            {editingId !== item.id && (
                              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                                <span className="text-[9px] text-slate-400 font-mono">
                                  Identified: {new Date(item.created_at).toLocaleDateString()}
                                </span>
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => startEdit(item)}
                                    className="text-slate-400 hover:text-[#059669] p-1 rounded hover:bg-slate-50 transition"
                                    title="Edit pattern text"
                                  >
                                    <Edit2 className="h-3.5 w-3.5" />
                                  </button>
                                  <button
                                    onClick={() => deleteEntry(item.id)}
                                    className="text-slate-400 hover:text-red-600 p-1 rounded hover:bg-slate-50 transition"
                                    title="Delete pattern entry"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* TAB CONTENT: LANES (Standings integrated) */}
                {activeTab === "lanes" && (
                  <div className="mt-6 space-y-4 font-sans">
                    {filteredLanes.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
                        <Shield className="mx-auto h-10 w-10 text-slate-300" />
                        <h3 className="mt-3 text-sm font-semibold text-slate-800">No Lanes found</h3>
                        <p className="mt-1 text-xs text-slate-500 max-w-sm mx-auto">
                          No results matched your search keywords.
                        </p>
                      </div>
                    ) : (
                      filteredLanes.map(lane => {
                        // Check if support is connected
                        const isSupportUnconnected = lane.isSupport && !supportConnected;
                        
                        // Fetch real standings for the category
                        const standing = standings.find(s => s.category === lane.category);
                        const currentRank = isSupportUnconnected 
                          ? "Not connected" 
                          : (standing ? standing.rank : "Observer");

                        return (
                          <div 
                            key={lane.id} 
                            className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col md:flex-row md:items-start md:justify-between gap-6 hover:border-slate-300 transition duration-150"
                          >
                            <div className="space-y-2 flex-1">
                              <div className="flex items-center gap-3">
                                <h3 className="text-base font-semibold text-slate-900 tracking-tight">
                                  {lane.title}
                                </h3>
                                <span className={`px-2.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${getRankBadgeClass(currentRank)}`}>
                                  {currentRank}
                                </span>
                              </div>
                              
                              <p className="text-xs text-slate-600 leading-relaxed max-w-2xl font-sans">
                                {getLaneDescription(lane.id, currentRank)}
                              </p>

                              <div className="pt-1 flex flex-col sm:flex-row sm:items-center gap-x-4 gap-y-1 text-[11px] text-slate-500 font-mono">
                                <span>
                                  <strong>Earned:</strong> {getLaneEarnedNote(lane.id, currentRank)}
                                </span>
                                {currentRank.toLowerCase() !== "chief of staff" && currentRank.toLowerCase() !== "chief" && (
                                  <span className="sm:border-l sm:border-slate-200 sm:pl-4">
                                    <strong>Next Rank:</strong> {getLaneNextRank(lane.id, currentRank)}
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Authority / Trust action buttons */}
                            <div className="flex flex-wrap items-center gap-2 md:self-center shrink-0">
                              {getLaneButtons(lane, currentRank)}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                )}

                {/* Bottom Utilities (Export & Clear) */}
                <div className="mt-12 border-t border-slate-200 pt-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6 font-sans">
                  <div className="text-xs text-slate-500 max-w-md">
                    <p className="font-semibold text-slate-700">Zilo updates these lanes automatically as it earns trust.</p>
                    <p className="mt-0.5 text-slate-400">
                      You can promote, demote, or remove access at any time. Everything Zilo does in each lane is logged in your{" "}
                      <Link href="/dashboard/rex/ledger" className="underline hover:text-slate-600 transition">
                        Action Log
                      </Link>.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2.5 shrink-0">
                    <button
                      onClick={handleRefresh}
                      className="rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 px-3.5 py-2 text-xs font-semibold shadow-sm transition active:scale-95 duration-100 flex items-center gap-1.5"
                      title="Rebuild notebook entries from live data"
                    >
                      <RotateCcw className="h-3.5 w-3.5" /> Rebuild notebook
                    </button>
                    <button
                      onClick={handleExport}
                      className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 px-3.5 py-2 text-xs font-semibold shadow-sm transition active:scale-95 duration-100 flex items-center gap-1.5"
                      title="Export all data as JSON"
                    >
                      <Download className="h-3.5 w-3.5" /> Export all data
                    </button>
                    <button
                      onClick={handleClearAll}
                      className="rounded-lg border border-rose-100 bg-rose-50 hover:bg-rose-100 text-rose-600 px-3.5 py-2 text-xs font-semibold shadow-sm transition active:scale-95 duration-100 flex items-center gap-1.5"
                      title="Clear all learned observations"
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Clear all
                    </button>
                  </div>
                </div>
              </>
            )}
          </>
        )}
        {/* Review Draft Modal */}
        {reviewingDraft && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg rounded-2xl bg-white border border-slate-200 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
              {/* Modal Header */}
              <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-[#059669]" />
                  <h3 className="text-sm font-bold text-slate-800">Review Zilo Draft</h3>
                </div>
                <button 
                  onClick={() => setReviewingDraft(null)}
                  className="p-1 rounded-lg hover:bg-slate-100 transition text-slate-400"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              
              {/* Modal Body */}
              <div className="p-5 space-y-4 overflow-y-auto flex-1 font-sans">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest font-mono">Subject</label>
                  <input
                    type="text"
                    value={editedDraftSubject}
                    onChange={e => setEditedDraftSubject(e.target.value)}
                    className="w-full mt-1 rounded-xl border border-slate-250 bg-white p-2.5 text-xs text-slate-800 shadow-sm focus:border-[#059669] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest font-mono">Message Draft</label>
                  <textarea
                    value={editedDraftBody}
                    onChange={e => setEditedDraftBody(e.target.value)}
                    className="w-full mt-1 rounded-xl border border-slate-250 bg-white p-3 font-mono text-xs text-slate-800 shadow-sm focus:border-[#059669] focus:outline-none min-h-[160px] leading-relaxed"
                    rows={6}
                  />
                </div>
                <div className="p-3 bg-emerald-50/50 border border-emerald-100 rounded-xl flex items-start gap-2 text-[11px] text-slate-650 font-sans">
                  <Sparkles className="h-3.5 w-3.5 text-[#059669] shrink-0 mt-0.5" />
                  <p>
                    Zilo tailored this draft specifically under 3 sentences, addressing timeline first without discussing price.
                  </p>
                </div>
              </div>
              
              {/* Modal Footer */}
              <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-end gap-2.5">
                <button
                  onClick={() => setReviewingDraft(null)}
                  className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 px-4 py-2 text-xs font-semibold shadow-sm transition active:scale-95 duration-100"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setReviewingDraft(null);
                    toast.success("Draft sent successfully!");
                  }}
                  className="rounded-lg bg-[#059669] hover:bg-[#047857] text-white px-4 py-2 text-xs font-semibold shadow-sm transition active:scale-95 duration-100 flex items-center gap-1.5"
                >
                  <Check className="h-3.5 w-3.5" /> Approve & Send
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

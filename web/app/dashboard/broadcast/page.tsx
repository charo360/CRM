"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  broadcastApi,
  Broadcast,
  BroadcastAutomation,
  BroadcastPerformance,
  BroadcastTemplate,
  Customer,
  CustomerGroup,
  Product,
  aiApi,
  customerGroupsApi,
  customersApi,
  productsApi,
  uploadApi,
} from "@/lib/api";
import { getBusinessType } from "@/lib/auth";
import { formatDate, formatDateTime, resolveMediaUrl } from "@/lib/utils";
import {
  Megaphone,
  Plus,
  Trash2,
  Loader2,
  Sparkles,
  Copy,
  RotateCcw,
  BarChart3,
  OctagonX,
  Users,
  ImagePlus,
  X,
  Package,
  Zap,
} from "lucide-react";

type Tab = "broadcasts" | "templates" | "automations";

const BROADCAST_MAX = 200;

const AUDIENCE_OPTIONS: { id: string; label: string }[] = [
  { id: "all", label: "All customers" },
  { id: "returning", label: "Returning" },
  { id: "vip", label: "VIP" },
  { id: "new", label: "New" },
  { id: "custom", label: "Pick customers" },
  { id: "group", label: "Saved list" },
];

function tagMatches(c: Customer, filter: string): boolean {
  if (filter === "all") return true;
  const raw = c.tags;
  const s = Array.isArray(raw) ? raw.join(" ") : String(raw ?? "");
  if (filter === "returning") return s.includes("Returning");
  if (filter === "vip") return s.includes("VIP");
  if (filter === "new") return s.includes("New");
  return false;
}

function countAudience(
  customers: Customer[],
  audience: string,
  group: CustomerGroup | null,
  customIds: string[]
): number {
  if (audience === "custom" && customIds.length > 0) return customIds.length;
  if (audience === "group" && group) return group.count ?? group.customer_ids.length;
  return customers.filter((c) => tagMatches(c, audience)).length;
}

function normalizeAutomation(row: Record<string, unknown>): BroadcastAutomation {
  const id = String(row.id ?? row._id ?? "");
  return { ...(row as unknown as BroadcastAutomation), id };
}

export default function BroadcastPage() {
  const [activeTab, setActiveTab] = useState<Tab>("broadcasts");
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [templates, setTemplates] = useState<BroadcastTemplate[]>([]);
  const [automations, setAutomations] = useState<BroadcastAutomation[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [groups, setGroups] = useState<CustomerGroup[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);

  const [showBroadcastModal, setShowBroadcastModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [showAutomationModal, setShowAutomationModal] = useState(false);
  const [showGroupModal, setShowGroupModal] = useState(false);
  const [perfForId, setPerfForId] = useState<string | null>(null);
  const [perfData, setPerfData] = useState<BroadcastPerformance | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);

  const [broadcastSearch, setBroadcastSearch] = useState("");

  const [bName, setBName] = useState("");
  const [bMessage, setBMessage] = useState("");
  const [bAudience, setBAudience] = useState("all");
  const [bGroupId, setBGroupId] = useState("");
  const [bCustomIds, setBCustomIds] = useState<string[]>([]);
  const [bImages, setBImages] = useState<string[]>([]);
  const [bSchedule, setBSchedule] = useState("");
  const [bAiPrompt, setBAiPrompt] = useState("");
  const [bSaving, setBSaving] = useState(false);
  const [bAiLoading, setBAiLoading] = useState(false);
  const [bUploading, setBUploading] = useState(false);
  const [custPickSearch, setCustPickSearch] = useState("");

  const [tplName, setTplName] = useState("");
  const [tplMessage, setTplMessage] = useState("");
  const [tplSaving, setTplSaving] = useState(false);

  const [autoType, setAutoType] = useState<"auto_followup" | "recurring">("auto_followup");
  const [autoBroadcastId, setAutoBroadcastId] = useState("");
  const [autoFollowMsg, setAutoFollowMsg] = useState("");
  const [autoDelayDays, setAutoDelayDays] = useState("2");
  const [recMessage, setRecMessage] = useState("");
  const [recFilter, setRecFilter] = useState("all");
  const [recurrence, setRecurrence] = useState<"weekly" | "monthly">("weekly");
  const [recHour, setRecHour] = useState("9");
  const [autoSaving, setAutoSaving] = useState(false);

  const [gName, setGName] = useState("");
  const [gIds, setGIds] = useState<string[]>([]);
  const [gSearch, setGSearch] = useState("");
  const [gSaving, setGSaving] = useState(false);

  const [catIds, setCatIds] = useState<string[]>([]);
  const [catAudience, setCatAudience] = useState("all");
  const [catGroupId, setCatGroupId] = useState("");
  const [catCustomIds, setCatCustomIds] = useState<string[]>([]);
  const [catCatSending, setCatCatSending] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [b, t, a, c, g, p] = await Promise.all([
        broadcastApi.list(),
        broadcastApi.templates(),
        broadcastApi.automations(),
        customersApi.list(),
        customerGroupsApi.list(),
        productsApi.list(),
      ]);
      setBroadcasts(b);
      setTemplates(t);
      setAutomations((a as unknown as Record<string, unknown>[]).map(normalizeAutomation));
      setCustomers(c);
      setGroups(g);
      setProducts(p);
    } catch (e) {
      console.error(e);
      alert("Failed to load broadcast data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  function openBroadcastModal() {
    setBName("");
    setBMessage("");
    setBAudience("all");
    setBGroupId("");
    setBCustomIds([]);
    setBImages([]);
    setBSchedule("");
    setBAiPrompt("");
    setCustPickSearch("");
    setShowBroadcastModal(true);
  }

  async function handleGenerateBroadcastAi() {
    const prompt = bAiPrompt.trim() || "Write a short friendly WhatsApp promo for our customers with a clear call to action. Use {{name}} for personalization.";
    setBAiLoading(true);
    try {
      const res = await aiApi.generateBroadcastMessage({
        prompt,
        business_type: getBusinessType(),
      });
      setBMessage(res.message);
    } catch {
      alert("Could not generate message");
    } finally {
      setBAiLoading(false);
    }
  }

  async function onPickImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBUploading(true);
    try {
      const buf = await file.arrayBuffer();
      const b64 = btoa(new Uint8Array(buf).reduce((acc, x) => acc + String.fromCharCode(x), ""));
      const { image_url } = await uploadApi.imageBase64(b64, file.name || "broadcast.jpg");
      setBImages((prev) => [...prev, image_url]);
    } catch {
      alert("Upload failed");
    } finally {
      setBUploading(false);
    }
  }

  function addProductImage(url: string | null | undefined) {
    if (!url) return;
    setBImages((prev) => (prev.includes(url) ? prev : [...prev, url]));
  }

  async function submitBroadcast() {
    const msg = bMessage.trim();
    if (!msg) {
      alert("Enter a message");
      return;
    }
    const n = countAudience(
      customers,
      bAudience,
      bAudience === "group" ? groups.find((g) => g.id === bGroupId) ?? null : null,
      bCustomIds
    );
    if (n === 0) {
      alert("No customers match this audience.");
      return;
    }
    if (bAudience === "custom" && bCustomIds.length === 0) {
      alert("Select at least one customer.");
      return;
    }
    if (bAudience === "group" && !bGroupId) {
      alert("Choose a saved list.");
      return;
    }

    let filter_type = bAudience;
    let customer_ids: string[] | undefined;
    if (bAudience === "group") {
      const g = groups.find((x) => x.id === bGroupId);
      if (!g?.customer_ids?.length) {
        alert("This list has no customers.");
        return;
      }
      filter_type = "custom";
      customer_ids = g.customer_ids;
    } else if (bAudience === "custom") {
      customer_ids = bCustomIds;
    }

    const capped = Math.min(n, BROADCAST_MAX);
    const ok = confirm(
      bSchedule
        ? `Schedule to ${capped} customer${capped !== 1 ? "s" : ""}?${n > BROADCAST_MAX ? `\n\nOnly the first ${BROADCAST_MAX} recipients are included (safety cap).` : ""}`
        : `Send now to ${capped} customer${capped !== 1 ? "s" : ""}?${n > BROADCAST_MAX ? `\n\nOnly the first ${BROADCAST_MAX} recipients are included (safety cap).` : ""}`
    );
    if (!ok) return;

    setBSaving(true);
    try {
      const scheduled_at = bSchedule
        ? new Date(bSchedule).toISOString()
        : undefined;
      const created = await broadcastApi.create({
        message: msg,
        name: bName.trim() || undefined,
        filter_type,
        customer_ids,
        image_urls: bImages.length ? bImages : undefined,
        image_url: bImages[0],
        scheduled_at,
      });
      setBroadcasts((prev) => [created, ...prev]);
      setShowBroadcastModal(false);
      if (!scheduled_at) startPolling(created.id);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to send");
    } finally {
      setBSaving(false);
    }
  }

  function startPolling(broadcastId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    let tries = 0;
    pollRef.current = setInterval(async () => {
      tries += 1;
      try {
        const list = await broadcastApi.list();
        setBroadcasts(list);
        const row = list.find((x) => x.id === broadcastId);
        if (row?.status === "completed" || row?.status === "cancelled" || tries >= 8) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }, 3000);
  }

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function submitTemplate() {
    if (!tplName.trim() || !tplMessage.trim()) {
      alert("Name and message are required");
      return;
    }
    setTplSaving(true);
    try {
      const t = await broadcastApi.createTemplate({
        name: tplName.trim(),
        message: tplMessage.trim(),
      });
      setTemplates((prev) => [t, ...prev]);
      setShowTemplateModal(false);
      setTplName("");
      setTplMessage("");
    } catch {
      alert("Failed to save template");
    } finally {
      setTplSaving(false);
    }
  }

  async function submitAutomation() {
    setAutoSaving(true);
    try {
      if (autoType === "auto_followup") {
        if (!autoBroadcastId || !autoFollowMsg.trim()) {
          alert("Choose a broadcast and enter a follow-up message");
          setAutoSaving(false);
          return;
        }
        await broadcastApi.autoFollowup({
          broadcast_id: autoBroadcastId,
          follow_up_message: autoFollowMsg.trim(),
          delay_days: Math.max(1, parseInt(autoDelayDays, 10) || 2),
        });
      } else {
        if (!recMessage.trim()) {
          alert("Enter a recurring message");
          setAutoSaving(false);
          return;
        }
        await broadcastApi.recurring({
          message: recMessage.trim(),
          filter_type: recFilter,
          recurrence,
          send_hour: Math.min(23, Math.max(0, parseInt(recHour, 10) || 9)),
        });
      }
      const a = await broadcastApi.automations();
      setAutomations((a as unknown as Record<string, unknown>[]).map(normalizeAutomation));
      setShowAutomationModal(false);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setAutoSaving(false);
    }
  }

  async function submitGroup() {
    if (!gName.trim() || gIds.length === 0) {
      alert("Name and at least one customer required");
      return;
    }
    setGSaving(true);
    try {
      await customerGroupsApi.create({ name: gName.trim(), customer_ids: gIds });
      const list = await customerGroupsApi.list();
      setGroups(list);
      setShowGroupModal(false);
      setGName("");
      setGIds([]);
    } catch {
      alert("Failed to create list");
    } finally {
      setGSaving(false);
    }
  }

  async function openPerformance(id: string) {
    setPerfForId(id);
    setPerfData(null);
    setPerfLoading(true);
    try {
      setPerfData(await broadcastApi.performance(id));
    } catch {
      alert("Could not load stats");
    } finally {
      setPerfLoading(false);
    }
  }

  async function sendCatalogBlast() {
    if (catIds.length === 0) {
      alert("Select at least one product");
      return;
    }
    const n = countAudience(
      customers,
      catAudience,
      catAudience === "group" ? groups.find((g) => g.id === catGroupId) ?? null : null,
      catAudience === "custom" ? catCustomIds : []
    );
    if (n === 0) {
      alert("No customers match this audience");
      return;
    }
    if (catAudience === "group" && !catGroupId) {
      alert("Choose a saved list");
      return;
    }
    if (catAudience === "custom" && catCustomIds.length === 0) {
      alert("Pick at least one customer");
      return;
    }
    if (!confirm(`Send catalog (${catIds.length} items) to ${Math.min(n, BROADCAST_MAX)} customers?`)) return;
    setCatCatSending(true);
    try {
      let customer_ids: string[] | undefined;
      let filter_type = catAudience;
      if (catAudience === "group") {
        const g = groups.find((x) => x.id === catGroupId);
        filter_type = "custom";
        customer_ids = g?.customer_ids;
      } else if (catAudience === "custom") {
        filter_type = "custom";
        customer_ids = catCustomIds;
      }
      await productsApi.broadcastCatalog({
        product_ids: catIds.slice(0, 10),
        filter_type,
        customer_ids,
      });
      await loadAll();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Catalog broadcast failed");
    } finally {
      setCatCatSending(false);
    }
  }

  const filteredBroadcasts = broadcasts.filter(
    (b) =>
      !broadcastSearch.trim() ||
      b.message.toLowerCase().includes(broadcastSearch.toLowerCase()) ||
      (b.name || "").toLowerCase().includes(broadcastSearch.toLowerCase())
  );

  const completedBroadcasts = broadcasts.filter((b) => b.status === "completed");

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Broadcast Center</h1>
          <p className="text-slate-500 text-sm mt-1">
            Bulk WhatsApp messaging, templates, automations — same tools as the mobile app
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void loadAll()}
            className="px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
          >
            Refresh
          </button>
          {activeTab === "broadcasts" && (
            <button
              type="button"
              onClick={openBroadcastModal}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700"
            >
              <Plus size={16} /> New broadcast
            </button>
          )}
          {activeTab === "templates" && (
            <button
              type="button"
              onClick={() => setShowTemplateModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700"
            >
              <Plus size={16} /> New template
            </button>
          )}
          {activeTab === "automations" && (
            <button
              type="button"
              onClick={() => setShowAutomationModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700"
            >
              <Zap size={16} /> New automation
            </button>
          )}
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {(
          [
            ["broadcasts", "Broadcasts", broadcasts.length],
            ["templates", "Templates", templates.length],
            ["automations", "Automations", automations.length],
          ] as const
        ).map(([id, label, count]) => (
          <button
            key={id}
            type="button"
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

      {activeTab === "broadcasts" && (
        <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
            <Package size={18} className="text-indigo-600" />
            Catalog blast
          </div>
          <p className="text-xs text-slate-500">
            Send product images and prices to a segment (max 10 products per send). Matches the app’s catalog broadcast.
          </p>
          <div className="flex flex-wrap gap-2">
            <select
              value={catAudience}
              onChange={(e) => setCatAudience(e.target.value)}
              className="text-sm border border-slate-200 rounded-lg px-2 py-1.5"
            >
              {AUDIENCE_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
            {catAudience === "group" && (
              <select
                value={catGroupId}
                onChange={(e) => setCatGroupId(e.target.value)}
                className="text-sm border border-slate-200 rounded-lg px-2 py-1.5 min-w-[160px]"
              >
                <option value="">Select list…</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name} ({g.count})
                  </option>
                ))}
              </select>
            )}
            {catAudience === "custom" && (
              <div className="w-full max-h-32 overflow-y-auto border border-slate-100 rounded-lg text-xs">
                {customers.slice(0, 60).map((c) => (
                  <label key={c.id} className="flex items-center gap-2 px-2 py-0.5 cursor-pointer hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={catCustomIds.includes(c.id)}
                      onChange={(e) =>
                        setCatCustomIds((prev) =>
                          e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id)
                        )
                      }
                    />
                    {c.name}
                  </label>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2 max-h-36 overflow-y-auto">
            {products.map((p) => (
              <label key={p.id} className="flex items-center gap-1.5 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={catIds.includes(p.id)}
                  onChange={(e) => {
                    setCatIds((prev) =>
                      e.target.checked ? [...prev, p.id] : prev.filter((x) => x !== p.id)
                    );
                  }}
                />
                <span className="truncate max-w-[140px]">{p.name}</span>
              </label>
            ))}
          </div>
          <button
            type="button"
            disabled={catCatSending || catIds.length === 0}
            onClick={() => void sendCatalogBlast()}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-lg bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {catCatSending ? <Loader2 size={14} className="animate-spin" /> : <Megaphone size={14} />}
            Send catalog broadcast
          </button>
        </div>
      )}

      {activeTab === "broadcasts" && (
        <div className="relative">
          <input
            type="search"
            placeholder="Search broadcasts…"
            value={broadcastSearch}
            onChange={(e) => setBroadcastSearch(e.target.value)}
            className="w-full sm:w-72 px-3 py-2 text-sm border border-slate-200 rounded-lg mb-3"
          />
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden min-h-[200px]">
        {loading ? (
          <div className="p-12 flex justify-center text-slate-400">
            <Loader2 className="animate-spin" size={28} />
          </div>
        ) : activeTab === "broadcasts" ? (
          <BroadcastsTable
            rows={filteredBroadcasts}
            onDelete={async (id) => {
              if (!confirm("Delete this broadcast log?")) return;
              await broadcastApi.delete(id);
              await loadAll();
            }}
            onResend={async (id) => {
              if (!confirm("Resend to the same audience?")) return;
              try {
                await broadcastApi.resend(id);
                await loadAll();
              } catch (e) {
                alert(e instanceof Error ? e.message : "Resend failed");
              }
            }}
            onCancel={async (id) => {
              if (!confirm("Stop sending? Messages already sent stay delivered.")) return;
              try {
                await broadcastApi.cancel(id);
                await loadAll();
              } catch (e) {
                alert(e instanceof Error ? e.message : "Could not stop");
              }
            }}
            onPerf={(id) => void openPerformance(id)}
          />
        ) : activeTab === "templates" ? (
          <TemplatesTable
            rows={templates}
            onDelete={async (id) => {
              if (!confirm("Delete template?")) return;
              await broadcastApi.deleteTemplate(id);
              await loadAll();
            }}
            onUse={(t) => {
              setBMessage(t.message);
              setBName(t.name || "");
              setShowBroadcastModal(true);
            }}
          />
        ) : (
          <AutomationsTable
            rows={automations}
            onDelete={async (id) => {
              if (!confirm("Delete this automation?")) return;
              await broadcastApi.deleteAutomation(id);
              await loadAll();
            }}
          />
        )}
      </div>

      {showBroadcastModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40"
          onMouseDown={(e) => e.target === e.currentTarget && setShowBroadcastModal(false)}
        >
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <h2 className="font-semibold text-slate-900">New broadcast</h2>
              <button type="button" onClick={() => setShowBroadcastModal(false)} className="p-2 text-slate-400 hover:text-slate-700">
                <X size={18} />
              </button>
            </div>
            <div className="p-4 space-y-3 text-sm">
              <button
                type="button"
                onClick={() => setShowGroupModal(true)}
                className="text-xs text-indigo-600 hover:underline"
              >
                + New customer list
              </button>
              <label className="block">
                <span className="text-xs font-medium text-slate-500">Name (optional)</span>
                <input
                  value={bName}
                  onChange={(e) => setBName(e.target.value)}
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg"
                  placeholder="Campaign name"
                />
              </label>
              <div>
                <span className="text-xs font-medium text-slate-500">Audience</span>
                <div className="flex flex-wrap gap-2 mt-1">
                  {AUDIENCE_OPTIONS.map((o) => (
                    <button
                      key={o.id}
                      type="button"
                      onClick={() => {
                        setBAudience(o.id);
                        if (o.id !== "group") setBGroupId("");
                      }}
                      className={`px-2.5 py-1 rounded-lg text-xs border ${
                        bAudience === o.id
                          ? "border-indigo-500 bg-indigo-50 text-indigo-800"
                          : "border-slate-200 text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
                {bAudience === "group" && (
                  <select
                    value={bGroupId}
                    onChange={(e) => setBGroupId(e.target.value)}
                    className="mt-2 w-full text-sm border border-slate-200 rounded-lg px-2 py-1.5"
                  >
                    <option value="">Select list…</option>
                    {groups.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.name} ({g.count})
                      </option>
                    ))}
                  </select>
                )}
                {bAudience === "custom" && (
                  <div className="mt-2 border border-slate-100 rounded-lg max-h-40 overflow-y-auto">
                    <input
                      type="search"
                      placeholder="Search…"
                      value={custPickSearch}
                      onChange={(e) => setCustPickSearch(e.target.value)}
                      className="w-full px-2 py-1.5 text-xs border-b border-slate-100"
                    />
                    {customers
                      .filter((c) => {
                        const q = custPickSearch.toLowerCase();
                        if (!q) return true;
                        return c.name.toLowerCase().includes(q) || (c.phone_number || "").includes(q);
                      })
                      .slice(0, 80)
                      .map((c) => (
                        <label key={c.id} className="flex items-center gap-2 px-2 py-1 text-xs cursor-pointer hover:bg-slate-50">
                          <input
                            type="checkbox"
                            checked={bCustomIds.includes(c.id)}
                            onChange={(e) => {
                              setBCustomIds((prev) =>
                                e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id)
                              );
                            }}
                          />
                          {c.name}
                        </label>
                      ))}
                  </div>
                )}
                <p className="text-xs text-slate-500 mt-1">
                  Targeting ~{countAudience(customers, bAudience, groups.find((g) => g.id === bGroupId) ?? null, bCustomIds)}{" "}
                  customers (cap {BROADCAST_MAX} per send)
                </p>
              </div>
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-slate-500">AI draft</span>
                  <button
                    type="button"
                    disabled={bAiLoading}
                    onClick={() => void handleGenerateBroadcastAi()}
                    className="text-xs flex items-center gap-1 text-purple-600 hover:text-purple-800"
                  >
                    {bAiLoading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                    Generate
                  </button>
                </div>
                <input
                  value={bAiPrompt}
                  onChange={(e) => setBAiPrompt(e.target.value)}
                  placeholder="What should the message say? (optional)"
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg text-xs"
                />
              </div>
              <label className="block">
                <span className="text-xs font-medium text-slate-500">Message *</span>
                <textarea
                  value={bMessage}
                  onChange={(e) => setBMessage(e.target.value)}
                  rows={5}
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                  placeholder="Hi {{name}}, …"
                  required
                />
                <p className="text-[11px] text-slate-400 mt-0.5">Use {"{{name}}"} for the customer&apos;s name</p>
              </label>
              <div>
                <span className="text-xs font-medium text-slate-500">Images (optional)</span>
                <div className="flex flex-wrap gap-2 mt-1">
                  <label className="inline-flex items-center gap-1 px-2 py-1 rounded-lg border border-dashed border-slate-300 text-xs cursor-pointer hover:bg-slate-50">
                    <ImagePlus size={14} />
                    {bUploading ? "…" : "Upload"}
                    <input type="file" accept="image/*" className="hidden" onChange={(e) => void onPickImage(e)} />
                  </label>
                  {products.slice(0, 12).map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => addProductImage(p.image_url || p.images?.[0])}
                      className="text-xs px-2 py-1 rounded border border-slate-200 truncate max-w-[120px]"
                    >
                      + {p.name}
                    </button>
                  ))}
                </div>
                {bImages.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {bImages.map((url) => (
                      <div key={url} className="relative w-14 h-14 rounded border border-slate-100 overflow-hidden">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={resolveMediaUrl(url) || url} alt="" className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => setBImages((prev) => prev.filter((u) => u !== url))}
                          className="absolute top-0 right-0 bg-black/50 text-white text-[10px] px-0.5"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <label className="block">
                <span className="text-xs font-medium text-slate-500">Schedule (optional)</span>
                <input
                  type="datetime-local"
                  value={bSchedule}
                  onChange={(e) => setBSchedule(e.target.value)}
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg"
                />
              </label>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-slate-100 bg-slate-50/80">
              <button type="button" onClick={() => setShowBroadcastModal(false)} className="px-3 py-2 text-sm text-slate-600">
                Cancel
              </button>
              <button
                type="button"
                disabled={bSaving}
                onClick={() => void submitBroadcast()}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white disabled:opacity-50"
              >
                {bSaving && <Loader2 size={14} className="animate-spin" />}
                {bSchedule ? "Schedule" : "Send"}
              </button>
            </div>
          </div>
        </div>
      )}

      {showTemplateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40"
          onMouseDown={(e) => e.target === e.currentTarget && setShowTemplateModal(false)}
        >
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <h2 className="font-semibold text-slate-900">New template</h2>
              <button type="button" onClick={() => setShowTemplateModal(false)} className="p-2 text-slate-400">
                <X size={18} />
              </button>
            </div>
            <div className="p-4 space-y-3 text-sm">
              <label className="block">
                <span className="text-xs font-medium text-slate-500">Name *</span>
                <input
                  value={tplName}
                  onChange={(e) => setTplName(e.target.value)}
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-500">Message *</span>
                <textarea
                  value={tplMessage}
                  onChange={(e) => setTplMessage(e.target.value)}
                  rows={5}
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg"
                />
              </label>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-slate-100">
              <button type="button" onClick={() => setShowTemplateModal(false)} className="px-3 py-2 text-sm text-slate-600">
                Cancel
              </button>
              <button
                type="button"
                disabled={tplSaving}
                onClick={() => void submitTemplate()}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white"
              >
                {tplSaving && <Loader2 size={14} className="animate-spin" />}
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {showAutomationModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40"
          onMouseDown={(e) => e.target === e.currentTarget && setShowAutomationModal(false)}
        >
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <h2 className="font-semibold text-slate-900">New automation</h2>
              <button type="button" onClick={() => setShowAutomationModal(false)} className="p-2 text-slate-400">
                <X size={18} />
              </button>
            </div>
            <div className="p-4 space-y-3 text-sm">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setAutoType("auto_followup")}
                  className={`flex-1 py-2 rounded-lg text-xs font-medium border ${
                    autoType === "auto_followup" ? "border-indigo-500 bg-indigo-50" : "border-slate-200"
                  }`}
                >
                  Auto follow-up
                </button>
                <button
                  type="button"
                  onClick={() => setAutoType("recurring")}
                  className={`flex-1 py-2 rounded-lg text-xs font-medium border ${
                    autoType === "recurring" ? "border-indigo-500 bg-indigo-50" : "border-slate-200"
                  }`}
                >
                  Recurring
                </button>
              </div>
              {autoType === "auto_followup" ? (
                <>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">After broadcast (completed)</span>
                    <select
                      value={autoBroadcastId}
                      onChange={(e) => setAutoBroadcastId(e.target.value)}
                      className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5"
                    >
                      <option value="">Select…</option>
                      {completedBroadcasts.map((b) => (
                        <option key={b.id} value={b.id}>
                          {(b.name || b.message.slice(0, 40)) + "…"}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">Follow-up message *</span>
                    <textarea
                      value={autoFollowMsg}
                      onChange={(e) => setAutoFollowMsg(e.target.value)}
                      rows={4}
                      className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">Delay (days)</span>
                    <input
                      type="number"
                      min={1}
                      value={autoDelayDays}
                      onChange={(e) => setAutoDelayDays(e.target.value)}
                      className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5"
                    />
                  </label>
                </>
              ) : (
                <>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">Message *</span>
                    <textarea
                      value={recMessage}
                      onChange={(e) => setRecMessage(e.target.value)}
                      rows={4}
                      className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">Audience</span>
                    <select
                      value={recFilter}
                      onChange={(e) => setRecFilter(e.target.value)}
                      className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5"
                    >
                      <option value="all">All</option>
                      <option value="returning">Returning</option>
                      <option value="vip">VIP</option>
                      <option value="new">New</option>
                    </select>
                  </label>
                  <div className="flex gap-2">
                    <label className="flex-1">
                      <span className="text-xs font-medium text-slate-500">Repeat</span>
                      <select
                        value={recurrence}
                        onChange={(e) => setRecurrence(e.target.value as "weekly" | "monthly")}
                        className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5"
                      >
                        <option value="weekly">Weekly</option>
                        <option value="monthly">Monthly</option>
                      </select>
                    </label>
                    <label className="w-24">
                      <span className="text-xs font-medium text-slate-500">Hour (0–23)</span>
                      <input
                        type="number"
                        min={0}
                        max={23}
                        value={recHour}
                        onChange={(e) => setRecHour(e.target.value)}
                        className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5"
                      />
                    </label>
                  </div>
                </>
              )}
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-slate-100">
              <button type="button" onClick={() => setShowAutomationModal(false)} className="px-3 py-2 text-sm text-slate-600">
                Cancel
              </button>
              <button
                type="button"
                disabled={autoSaving}
                onClick={() => void submitAutomation()}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white"
              >
                {autoSaving && <Loader2 size={14} className="animate-spin" />}
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {showGroupModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40"
          onMouseDown={(e) => e.target === e.currentTarget && setShowGroupModal(false)}
        >
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full border border-slate-200">
            <div className="px-4 py-3 border-b border-slate-100 font-semibold text-slate-900">New customer list</div>
            <div className="p-4 space-y-2 text-sm">
              <input
                value={gName}
                onChange={(e) => setGName(e.target.value)}
                placeholder="List name"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg"
              />
              <input
                value={gSearch}
                onChange={(e) => setGSearch(e.target.value)}
                placeholder="Search customers…"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs"
              />
              <div className="max-h-48 overflow-y-auto border border-slate-100 rounded-lg">
                {customers
                  .filter((c) => {
                    const q = gSearch.toLowerCase();
                    if (!q) return true;
                    return c.name.toLowerCase().includes(q) || (c.phone_number || "").includes(q);
                  })
                  .slice(0, 100)
                  .map((c) => (
                    <label key={c.id} className="flex items-center gap-2 px-2 py-1 text-xs cursor-pointer hover:bg-slate-50">
                      <input
                        type="checkbox"
                        checked={gIds.includes(c.id)}
                        onChange={(e) =>
                          setGIds((prev) =>
                            e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id)
                          )
                        }
                      />
                      {c.name}
                    </label>
                  ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t">
              <button type="button" onClick={() => setShowGroupModal(false)} className="px-3 py-2 text-sm text-slate-600">
                Cancel
              </button>
              <button
                type="button"
                disabled={gSaving}
                onClick={() => void submitGroup()}
                className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white"
              >
                {gSaving ? <Loader2 size={14} className="animate-spin" /> : "Save list"}
              </button>
            </div>
          </div>
        </div>
      )}

      {perfForId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40"
          onMouseDown={(e) => e.target === e.currentTarget && setPerfForId(null)}
        >
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-5 border border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2">
                <BarChart3 size={18} /> Performance
              </h3>
              <button type="button" onClick={() => setPerfForId(null)} className="text-slate-400">
                <X size={18} />
              </button>
            </div>
            {perfLoading ? (
              <Loader2 className="animate-spin mx-auto text-slate-400" />
            ) : perfData ? (
              <ul className="text-sm space-y-2 text-slate-700">
                <li>Sent: {perfData.sent_count}</li>
                <li>Recipients: {perfData.recipients_count}</li>
                <li>Replies (3d window): {perfData.replies}</li>
                <li>Reply rate: {perfData.reply_rate}%</li>
              </ul>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

function BroadcastsTable({
  rows,
  onDelete,
  onResend,
  onCancel,
  onPerf,
}: {
  rows: Broadcast[];
  onDelete: (id: string) => void;
  onResend: (id: string) => void;
  onCancel: (id: string) => void;
  onPerf: (id: string) => void;
}) {
  if (!rows.length) {
    return <div className="p-10 text-center text-slate-400">No broadcasts yet. Create one or send a catalog blast above.</div>;
  }
  return (
    <table className="w-full text-sm">
      <thead className="bg-slate-50 border-b border-slate-200">
        <tr>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Name / preview</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Audience</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Status</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Sent</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Created</th>
          <th className="px-4 py-3" />
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {rows.map((b) => (
          <tr key={b.id} className="hover:bg-slate-50">
            <td className="px-4 py-3 max-w-xs">
              <p className="font-medium text-slate-800 truncate">{b.name || "Untitled"}</p>
              <p className="text-slate-500 text-xs line-clamp-2">{b.message}</p>
            </td>
            <td className="px-4 py-3 text-slate-600 capitalize text-xs">{b.filter_type}</td>
            <td className="px-4 py-3">
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">{b.status}</span>
            </td>
            <td className="px-4 py-3 text-slate-600">
              {b.sent_count}/{b.recipients_count}
            </td>
            <td className="px-4 py-3 text-slate-400 text-xs">{formatDateTime(typeof b.created_at === "string" ? b.created_at : String(b.created_at))}</td>
            <td className="px-4 py-3">
              <div className="flex flex-wrap gap-1 justify-end">
                <button
                  type="button"
                  onClick={() => onPerf(b.id)}
                  className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-100 hover:text-indigo-600"
                  title="Stats"
                >
                  <BarChart3 size={14} />
                </button>
                {["pending", "sending", "scheduled"].includes(b.status) && (
                  <button
                    type="button"
                    onClick={() => onCancel(b.id)}
                    className="p-1.5 rounded-lg text-slate-400 hover:bg-amber-100 hover:text-amber-700"
                    title="Stop"
                  >
                    <OctagonX size={14} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => onResend(b.id)}
                  className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-100 hover:text-indigo-600"
                  title="Resend"
                >
                  <RotateCcw size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(b.id)}
                  className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TemplatesTable({
  rows,
  onDelete,
  onUse,
}: {
  rows: BroadcastTemplate[];
  onDelete: (id: string) => void;
  onUse: (t: BroadcastTemplate) => void;
}) {
  if (!rows.length) {
    return <div className="p-10 text-center text-slate-400">No templates yet.</div>;
  }
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
        {rows.map((t) => (
          <tr key={t.id} className="hover:bg-slate-50">
            <td className="px-4 py-3 font-medium text-slate-800">{t.name}</td>
            <td className="px-4 py-3 text-slate-500 max-w-xs truncate">{t.message}</td>
            <td className="px-4 py-3 text-slate-400">{formatDate(t.created_at)}</td>
            <td className="px-4 py-3">
              <div className="flex gap-1 justify-end">
                <button
                  type="button"
                  onClick={() => onUse(t)}
                  className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-100 hover:text-indigo-600"
                  title="Use in broadcast"
                >
                  <Copy size={13} />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(t.id)}
                  className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600"
                >
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
  rows,
  onDelete,
}: {
  rows: BroadcastAutomation[];
  onDelete: (id: string) => void;
}) {
  if (!rows.length) {
    return <div className="p-10 text-center text-slate-400">No automations yet. Add auto follow-up or recurring sends.</div>;
  }
  return (
    <table className="w-full text-sm">
      <thead className="bg-slate-50 border-b border-slate-200">
        <tr>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Type</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Detail</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Status</th>
          <th className="px-4 py-3 text-left font-semibold text-slate-600">Runs</th>
          <th className="px-4 py-3" />
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {rows.map((a) => (
          <tr key={a.id} className="hover:bg-slate-50">
            <td className="px-4 py-3 capitalize text-slate-800">{a.type?.replace(/_/g, " ") || "—"}</td>
            <td className="px-4 py-3 text-slate-600 text-xs max-w-md">
              {a.type === "auto_followup" && (
                <>
                  After broadcast · delay {a.delay_days ?? "?"}d
                  {a.follow_up_message && (
                    <span className="block text-slate-400 truncate mt-0.5">{a.follow_up_message}</span>
                  )}
                </>
              )}
              {a.type === "recurring" && (
                <>
                  Every {a.recurrence || "?"} @ {a.send_hour ?? "?"}:00 · {a.filter_type || "all"}
                  {a.message && <span className="block text-slate-400 truncate mt-0.5">{a.message}</span>}
                </>
              )}
            </td>
            <td className="px-4 py-3 text-xs">{a.status}</td>
            <td className="px-4 py-3 text-xs">{a.runs ?? 0}</td>
            <td className="px-4 py-3">
              <button
                type="button"
                onClick={() => onDelete(a.id)}
                className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600"
              >
                <Trash2 size={13} />
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

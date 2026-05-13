"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import {
  Globe, Plus, RefreshCw, ExternalLink, ShoppingCart,
  Loader2, AlertCircle, CheckCircle2, Clock, Settings,
  Store, ClipboardList, BookOpen, Copy, Check, X,
  ChevronRight, FileInput, MessageSquare, Mail, User,
  Calendar, CornerDownRight, Send, Trash2, EyeOff, FileText, Phone, Save,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface SiteFeatures {
  shop: boolean;
  forms: boolean;
  blog: boolean;
}

interface Comment {
  id: number;
  post_id: number;
  post_title: string;
  post_link: string;
  author: string;
  email: string;
  content: string;
  date: string;
  status: string;
  parent: number;
}

interface WpPost {
  id: number;
  title: string;
  status: string;
  date: string;
  link: string;
}

interface FormEntry {
  id?: number | string;
  fields?: Record<string, string>;
  date?: string;
  [key: string]: unknown;
}

interface ClientSite {
  client_id: string;
  business_name: string;
  client_email: string;
  industry: string;
  location: string;
  blog_url: string | null;
  wp_slug: string;
  active: boolean;
  plan: string;
  posts_count: number;
  orders_count?: number;
  products_count?: number;
  features: SiteFeatures;
  created_at: string;
  last_posted_at: string | null;
  last_synced?: string;
  whatsapp_number?: string;
}

interface ListResponse {
  sites: ClientSite[];
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
      <CheckCircle2 size={10} /> Active
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500 border border-slate-200">
      <Clock size={10} /> Paused
    </span>
  );
}

const FEATURE_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  shop:  { icon: <Store size={12} />,       label: "Shop",  color: "bg-blue-50 text-blue-700 border-blue-200" },
  forms: { icon: <ClipboardList size={12} />, label: "Forms", color: "bg-purple-50 text-purple-700 border-purple-200" },
  blog:  { icon: <BookOpen size={12} />,    label: "Blog",  color: "bg-emerald-50 text-emerald-700 border-emerald-200" },
};

const INDUSTRIES = [
  "Retail", "Food & Beverage", "Health & Beauty", "Salon / Beauty", "Fashion", "Technology",
  "Education", "Real Estate", "Finance", "Consulting", "Photography",
  "Events", "Fitness", "Restaurant", "Hotel", "Legal", "Other",
];

// ── Main Component ────────────────────────────────────────────────────────────

export default function ClientSitesPage() {
  const [sites, setSites] = useState<ClientSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Create modal state — matches /api/blog/create body
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [form, setForm] = useState({
    business_name: "",
    client_email: "",
    industry: "",
    location: "",
  });

  // Per-site UI state keyed by wp_slug
  const [syncing, setSyncing] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [reseeding, setReseeding] = useState<string | null>(null);
  const [recreating, setRecreating] = useState<string | null>(null);
  const [activating, setActivating] = useState<string | null>(null);
  const [engagementSlug, setEngagementSlug] = useState<string | null>(null);
  const [engagementTab, setEngagementTab] = useState<"comments" | "contacts" | "posts">("comments");
  const [comments, setComments] = useState<Comment[]>([]);
  const [formEntries, setFormEntries] = useState<FormEntry[]>([]);
  const [wpPosts, setWpPosts] = useState<WpPost[]>([]);
  const [engagementLoading, setEngagementLoading] = useState(false);
  const [pendingCounts, setPendingCounts] = useState<Record<string, number>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<ListResponse>("/blog/clients");
      setSites(data.sites);
      // Fetch pending comment counts in background — non-fatal
      api.get<{ counts: Record<string, number> }>("/blog/clients/pending-counts")
        .then((r) => setPendingCounts(r.counts || {}))
        .catch(() => {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load client sites");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function createSite() {
    if (!form.business_name.trim() || !form.client_email.trim()) {
      setCreateError("Business name and email are required");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      // Reuse the existing /blog/provision endpoint (idempotent)
      await api.post("/blog/create", {
        client_id: form.client_email.split("@")[0],
        business_name: form.business_name.trim(),
        client_email: form.client_email.trim(),
        industry: form.industry || "General",
        location: form.location || "",
      });
      setShowCreate(false);
      setForm({ business_name: "", client_email: "", industry: "", location: "" });
      await load();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "Failed to create site");
    } finally {
      setCreating(false);
    }
  }

  async function syncSite(slug: string) {
    setSyncing(slug);
    try {
      const res = await api.post<{ stats: Record<string, number> }>(`/blog/clients/${slug}/sync`, {});
      setSites((s) => s.map((site) =>
        site.wp_slug === slug
          ? { ...site, posts_count: res.stats.posts_count ?? site.posts_count, orders_count: res.stats.orders_count, products_count: res.stats.products_count, last_synced: new Date().toISOString() }
          : site
      ));
    } catch { /* ignore */ }
    finally { setSyncing(null); }
  }

  function copyUrl(url: string, slug: string) {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(slug);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  async function recreatePages(slug: string) {
    setRecreating(slug);
    try {
      await api.post(`/blog/clients/${slug}/recreate-pages`, {});
    } catch { /* non-fatal */ }
    finally { setRecreating(null); }
  }

  async function activatePlugins(slug: string) {
    setActivating(slug);
    try {
      await api.post(`/blog/clients/${slug}/activate-plugins`, {});
    } catch { /* non-fatal */ }
    finally { setActivating(null); }
  }

  async function reseedSite(slug: string, type: "products" | "forms") {
    const key = `${slug}:${type}`;
    setReseeding(key);
    try {
      await api.post(`/blog/clients/${slug}/reseed-${type}`, {});
    } catch { /* ignore — non-fatal */ }
    finally { setReseeding(null); }
  }

  async function openEngagement(slug: string, tab: "comments" | "contacts" | "posts") {
    if (engagementSlug === slug && engagementTab === tab) {
      setEngagementSlug(null);
      return;
    }
    setEngagementSlug(slug);
    setEngagementTab(tab);
    setEngagementLoading(true);
    setComments([]); setFormEntries([]); setWpPosts([]);
    try {
      if (tab === "comments") {
        const data = await api.get<{ comments: Comment[] }>(`/blog/clients/${slug}/comments`);
        setComments(data.comments || []);
      } else if (tab === "posts") {
        const data = await api.get<{ posts: WpPost[] }>(`/blog/clients/${slug}/posts`);
        setWpPosts(data.posts || []);
      } else {
        const data = await api.get<{ entries: FormEntry[] }>(`/blog/clients/${slug}/form-entries`);
        setFormEntries(data.entries || []);
      }
    } catch { /* non-fatal */ }
    finally { setEngagementLoading(false); }
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Globe size={22} className="text-emerald-600" />
            Client Sites
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Each client gets a full website — shop, forms &amp; blog — on their own subdomain.
          </p>
        </div>
        <button
          onClick={() => { setShowCreate(true); setCreateError(""); }}
          className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-700 transition-colors"
        >
          <Plus size={15} /> New Client Site
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3">
          <AlertCircle size={15} className="shrink-0" /> {error}
          <button onClick={() => setError("")} className="ml-auto text-rose-400 hover:text-rose-600"><X size={14} /></button>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
            <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-slate-100">
              <h2 className="text-lg font-bold text-slate-900">Create Client Site</h2>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-700"><X size={18} /></button>
            </div>
            <div className="px-6 py-5 space-y-4">
              {createError && (
                <div className="flex items-center gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
                  <AlertCircle size={13} className="shrink-0" /> {createError}
                </div>
              )}
              <div>
                <label className="text-xs font-semibold text-slate-600 block mb-1.5">Business / Client Name *</label>
                <input
                  autoFocus
                  value={form.business_name}
                  onChange={(e) => setForm((f) => ({ ...f, business_name: e.target.value }))}
                  placeholder="Jane's Boutique"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600 block mb-1.5">Client Email *</label>
                <input
                  type="email"
                  value={form.client_email}
                  onChange={(e) => setForm((f) => ({ ...f, client_email: e.target.value }))}
                  placeholder="jane@example.com"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-slate-600 block mb-1.5">Industry</label>
                  <select
                    value={form.industry}
                    onChange={(e) => setForm((f) => ({ ...f, industry: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300 bg-white"
                  >
                    <option value="">Select…</option>
                    {INDUSTRIES.map((i) => <option key={i} value={i}>{i}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-600 block mb-1.5">Location</label>
                  <input
                    value={form.location}
                    onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
                    placeholder="Nairobi, KE"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                  />
                </div>
              </div>
              <p className="text-xs text-slate-400 bg-slate-50 rounded-lg px-3 py-2">
                WordPress will create the subsite, activate WooCommerce and WPForms automatically via WP-CLI.
              </p>
            </div>
            <div className="flex gap-2 justify-end px-6 pb-5">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">Cancel</button>
              <button
                onClick={createSite}
                disabled={creating || !form.business_name.trim() || !form.client_email.trim()}
                className="flex items-center gap-2 px-5 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-50"
              >
                {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                Create Site
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Site grid */}
      {loading ? (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          {[1, 2, 3].map((i) => <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse h-52" />)}
        </div>
      ) : sites.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-slate-200 p-16 text-center">
          <Globe size={40} className="mx-auto text-slate-200 mb-3" />
          <p className="font-semibold text-slate-600 text-lg">No client sites yet</p>
          <p className="text-sm text-slate-400 mt-1 mb-6 max-w-sm mx-auto">
            Each client gets their own subdomain with a shop, survey forms and a blog.
          </p>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-700"
          >
            <Plus size={14} /> Create First Site
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          {sites.map((site) => (
            <SiteCard
              key={site.wp_slug}
              site={site}
              syncing={syncing === site.wp_slug}
              copied={copied === site.wp_slug}
              expanded={expanded === site.wp_slug}
              reseedingProducts={reseeding === `${site.wp_slug}:products`}
              reseedingForms={reseeding === `${site.wp_slug}:forms`}
              recreatingPages={recreating === site.wp_slug}
              activatingPlugins={activating === site.wp_slug}
              engagementOpen={engagementSlug === site.wp_slug}
              engagementTab={engagementTab}
              engagementLoading={engagementLoading && engagementSlug === site.wp_slug}
              comments={engagementSlug === site.wp_slug ? comments : []}
              formEntries={engagementSlug === site.wp_slug ? formEntries : []}
              wpPosts={engagementSlug === site.wp_slug ? wpPosts : []}
              pendingCount={pendingCounts[site.wp_slug] ?? 0}
              onSync={() => syncSite(site.wp_slug)}
              onCopy={() => site.blog_url && copyUrl(site.blog_url, site.wp_slug)}
              onToggleExpand={() => setExpanded((e) => (e === site.wp_slug ? null : site.wp_slug))}
              onReseedProducts={() => reseedSite(site.wp_slug, "products")}
              onReseedForms={() => reseedSite(site.wp_slug, "forms")}
              onRecreatePages={() => recreatePages(site.wp_slug)}
              onActivatePlugins={() => activatePlugins(site.wp_slug)}
              onOpenEngagement={(tab) => openEngagement(site.wp_slug, tab)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Site Card ─────────────────────────────────────────────────────────────────

interface SiteCardProps {
  site: ClientSite;
  syncing: boolean;
  copied: boolean;
  expanded: boolean;
  reseedingProducts: boolean;
  reseedingForms: boolean;
  recreatingPages: boolean;
  activatingPlugins: boolean;
  engagementOpen: boolean;
  engagementTab: "comments" | "contacts" | "posts";
  engagementLoading: boolean;
  comments: Comment[];
  formEntries: FormEntry[];
  wpPosts: WpPost[];
  pendingCount: number;
  onSync: () => void;
  onCopy: () => void;
  onToggleExpand: () => void;
  onReseedProducts: () => void;
  onReseedForms: () => void;
  onRecreatePages: () => void;
  onActivatePlugins: () => void;
  onOpenEngagement: (tab: "comments" | "contacts" | "posts") => void;
}

function WhatsAppEditor({ wpSlug, initial }: { wpSlug: string; initial: string }) {
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");

  async function save() {
    setSaving(true); setSaved(false); setErr("");
    try {
      const res = await api.patch<{ whatsapp_number: string; wp_updated: boolean }>(
        `/blog/clients/${wpSlug}/whatsapp`,
        { whatsapp_number: value },
      );
      setValue(res.whatsapp_number);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-1.5 pt-1 border-t border-slate-200">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider pt-2 flex items-center gap-1.5">
        <Phone size={11} /> WhatsApp Number
      </p>
      <p className="text-[10px] text-slate-400">
        This number powers the &ldquo;Chat on WhatsApp&rdquo; button on the contact page.
      </p>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-xs">+</span>
          <input
            type="tel"
            value={value}
            onChange={(e) => { setValue(e.target.value); setSaved(false); }}
            placeholder="254712345678"
            className="w-full pl-5 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-200"
          />
        </div>
        <button
          onClick={save}
          disabled={saving || !value.trim()}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors font-medium shrink-0"
        >
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
      {saved && (
        <p className="flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
          <Check size={10} /> Saved — contact page updated live
        </p>
      )}
      {err && <p className="text-[10px] text-rose-500">{err}</p>}
      {value && (
        <a
          href={`https://wa.me/${value.replace(/\D/g, "")}`}
          target="_blank" rel="noopener noreferrer"
          className="text-[10px] text-emerald-600 hover:underline flex items-center gap-1"
        >
          <ExternalLink size={9} /> Test link: wa.me/{value.replace(/\D/g, "")}
        </a>
      )}
    </div>
  );
}

function SiteCard({ site, syncing, copied, expanded, reseedingProducts, reseedingForms, recreatingPages, activatingPlugins,
  engagementOpen, engagementTab, engagementLoading, comments, formEntries, wpPosts, pendingCount,
  onSync, onCopy, onToggleExpand, onReseedProducts, onReseedForms, onRecreatePages, onActivatePlugins, onOpenEngagement }: SiteCardProps) {
  const enabledFeatures = Object.entries(site.features || { shop: true, forms: true, blog: true }).filter(([, v]) => v);
  const siteUrl = site.blog_url || "";

  return (
    <div className="bg-white rounded-xl border border-slate-200 flex flex-col hover:border-slate-300 transition-colors shadow-sm">
      <div className="p-5 flex flex-col gap-3">
        {/* Title + status */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <p className="font-semibold text-slate-800 text-sm truncate">{site.business_name}</p>
              <ActiveBadge active={site.active} />
            </div>
            {siteUrl ? (
              <a href={siteUrl} target="_blank" rel="noopener noreferrer"
                className="text-xs font-mono text-emerald-600 hover:text-emerald-800 hover:underline truncate block">
                {siteUrl.replace(/^https?:\/\//, "")}
              </a>
            ) : (
              <span className="text-xs text-slate-400 font-mono">{site.wp_slug}.zilo.pro</span>
            )}
            {site.industry && <p className="text-xs text-slate-400 mt-0.5">{site.industry}{site.location ? ` · ${site.location}` : ""}</p>}
          </div>
          {siteUrl && (
            <a href={siteUrl} target="_blank" rel="noopener noreferrer"
              className="shrink-0 p-1.5 text-slate-300 hover:text-slate-600 hover:bg-slate-50 rounded-lg transition-colors">
              <ExternalLink size={14} />
            </a>
          )}
        </div>

        {/* Feature pills */}
        <div className="flex flex-wrap gap-1.5">
          {enabledFeatures.map(([key]) => {
            const m = FEATURE_META[key];
            return m ? (
              <span key={key} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${m.color}`}>
                {m.icon} {m.label}
              </span>
            ) : null;
          })}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-50">
          <StatCell label="Posts" value={site.posts_count ?? 0} icon={<BookOpen size={11} />} />
          <StatCell label="Orders" value={site.orders_count ?? 0} icon={<ShoppingCart size={11} />} />
          <StatCell label="Products" value={site.products_count ?? 0} icon={<Store size={11} />} />
        </div>
      </div>

      {/* Actions */}
      <div className="px-4 pb-4 flex items-center gap-1.5 border-t border-slate-50 pt-3">
        <button onClick={onCopy} disabled={!siteUrl}
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors disabled:opacity-40">
          {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
          {copied ? "Copied!" : "Copy URL"}
        </button>
        <button onClick={onSync} disabled={syncing}
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors disabled:opacity-50">
          <RefreshCw size={12} className={syncing ? "animate-spin" : ""} /> Sync
        </button>
        <button onClick={() => onOpenEngagement("comments")}
          className={`relative flex items-center gap-1 px-2.5 py-1.5 text-xs border rounded-lg transition-colors ${
            engagementOpen && engagementTab === "comments"
              ? "border-blue-300 bg-blue-50 text-blue-700"
              : "border-slate-200 hover:bg-slate-50 text-slate-600"
          }`}>
          <MessageSquare size={12} /> Comments
          {pendingCount > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 flex items-center justify-center bg-rose-500 text-white text-[9px] font-bold rounded-full px-1 leading-none">
              {pendingCount > 99 ? "99+" : pendingCount}
            </span>
          )}
        </button>
        <button onClick={() => onOpenEngagement("contacts")}
          className={`flex items-center gap-1 px-2.5 py-1.5 text-xs border rounded-lg transition-colors ${
            engagementOpen && engagementTab === "contacts"
              ? "border-purple-300 bg-purple-50 text-purple-700"
              : "border-slate-200 hover:bg-slate-50 text-slate-600"
          }`}>
          <Mail size={12} /> Contacts
        </button>
        <button onClick={() => onOpenEngagement("posts")}
          className={`flex items-center gap-1 px-2.5 py-1.5 text-xs border rounded-lg transition-colors ${
            engagementOpen && engagementTab === "posts"
              ? "border-emerald-300 bg-emerald-50 text-emerald-700"
              : "border-slate-200 hover:bg-slate-50 text-slate-600"
          }`}>
          <FileText size={12} /> Posts
        </button>
        <button onClick={onToggleExpand}
          className="flex items-center gap-1 px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors ml-auto">
          <Settings size={12} />
          <ChevronRight size={11} className={`transition-transform ${expanded ? "rotate-90" : ""}`} />
        </button>
      </div>

      {/* Engagement panel */}
      {engagementOpen && (
        <div className="border-t border-slate-100 bg-slate-50 rounded-b-xl">
          {engagementLoading ? (
            <div className="flex items-center justify-center py-10 gap-2 text-slate-400 text-sm">
              <Loader2 size={16} className="animate-spin" /> Loading…
            </div>
          ) : engagementTab === "comments" ? (
            <CommentsPanel comments={comments} wpSlug={site.wp_slug} />
          ) : engagementTab === "posts" ? (
            <PostsPanel posts={wpPosts} wpSlug={site.wp_slug} />
          ) : (
            <div className="px-4 py-3 space-y-2">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Get in Touch Submissions</p>
              {formEntries.length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-6">No submissions yet</p>
              ) : formEntries.map((entry, i) => (
                <div key={entry.id ?? i} className="bg-white rounded-lg border border-slate-200 p-3 space-y-1">
                  {entry.date && (
                    <span className="flex items-center gap-1 text-[10px] text-slate-400 mb-1">
                      <Calendar size={10} /> {new Date(entry.date).toLocaleDateString()}
                    </span>
                  )}
                  {entry.fields ? (
                    Object.entries(entry.fields).map(([k, v]) => {
                      const key = k.toLowerCase();
                      const isPhone = key.includes("phone") || key.includes("whatsapp") || key.includes("mobile") || key.includes("number");
                      const phone = isPhone ? String(v).replace(/[^\d+]/g, "") : "";
                      return (
                        <div key={k} className="flex gap-2 text-xs items-center">
                          <span className="text-slate-400 min-w-[80px] shrink-0">{k}:</span>
                          {isPhone && phone ? (
                            <a
                              href={`https://wa.me/${phone.replace(/^\+/, "")}`}
                              target="_blank" rel="noopener noreferrer"
                              className="text-emerald-600 hover:text-emerald-800 font-medium hover:underline flex items-center gap-1"
                            >
                              {String(v)}
                              <ExternalLink size={9} className="opacity-60" />
                            </a>
                          ) : (
                            <span className="text-slate-700">{String(v)}</span>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <pre className="text-[10px] text-slate-500 whitespace-pre-wrap break-all">
                      {JSON.stringify(entry, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Expanded quick-links */}
      {expanded && (
        <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 rounded-b-xl space-y-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Quick Links</p>
          <div className="grid grid-cols-1 gap-2">
            <QuickLink href={`${siteUrl}/wp-admin`} icon={<Settings size={13} />} label="WP Admin" sub="Client's WordPress dashboard" />
            {siteUrl && (
              <QuickLink href={`${siteUrl}/contact`} icon={<Mail size={13} />} label="Contact Page" sub="Public contact page on the site" />
            )}
            {site.features?.shop && (
              <QuickLink href={`${siteUrl}/wp-admin/admin.php?page=wc-admin`} icon={<ShoppingCart size={13} />} label="WooCommerce" sub="Orders, products, settings" />
            )}
            {site.features?.blog && (
              <QuickLink href={`${siteUrl}/wp-admin/edit.php`} icon={<BookOpen size={13} />} label="Blog Posts" sub="Write and manage posts" />
            )}
            {site.features?.forms && (
              <QuickLink href={`${siteUrl}/wp-admin/admin.php?page=wpforms-overview`} icon={<FileInput size={13} />} label="WPForms" sub="Forms &amp; survey responses" />
            )}
          </div>
          {/* AI Reseed actions */}
          <div className="pt-2 border-t border-slate-200">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">AI Actions</p>
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={onReseedProducts}
                disabled={reseedingProducts}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-100 disabled:opacity-50 transition-colors font-medium"
                title="AI generates industry-specific products and pushes them to WooCommerce"
              >
                {reseedingProducts ? <Loader2 size={11} className="animate-spin" /> : <Store size={11} />}
                {reseedingProducts ? "Generating…" : "AI Reseed Products"}
              </button>
              <button
                onClick={onReseedForms}
                disabled={reseedingForms}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded-lg hover:bg-purple-100 disabled:opacity-50 transition-colors font-medium"
                title="AI generates industry-specific forms and pushes them to WPForms"
              >
                {reseedingForms ? <Loader2 size={11} className="animate-spin" /> : <FileInput size={11} />}
                {reseedingForms ? "Generating…" : "AI Reseed Forms"}
              </button>
              <button
                onClick={onRecreatePages}
                disabled={recreatingPages}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg hover:bg-emerald-100 disabled:opacity-50 transition-colors font-medium"
                title="Creates missing Contact, Forms and Survey pages on this site"
              >
                {recreatingPages ? <Loader2 size={11} className="animate-spin" /> : <Globe size={11} />}
                {recreatingPages ? "Creating…" : "Recreate Pages"}
              </button>
              <button
                onClick={onActivatePlugins}
                disabled={activatingPlugins}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-orange-50 text-orange-700 border border-orange-200 rounded-lg hover:bg-orange-100 disabled:opacity-50 transition-colors font-medium"
                title="Activates WPForms + WooCommerce on this subsite — fixes forms showing as raw text"
              >
                {activatingPlugins ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
                {activatingPlugins ? "Activating…" : "Activate Plugins"}
              </button>
            </div>
          </div>

          <WhatsAppEditor wpSlug={site.wp_slug} initial={site.whatsapp_number ?? ""} />

          <div className="text-xs text-slate-400 flex flex-wrap gap-3">
            <span>Email: <span className="text-slate-600">{site.client_email}</span></span>
            {site.last_synced && <span>Synced: {new Date(site.last_synced).toLocaleDateString()}</span>}
            {site.last_posted_at && <span>Last post: {new Date(site.last_posted_at).toLocaleDateString()}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCell({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="text-center">
      <div className="flex items-center justify-center gap-1 text-slate-400 text-[10px] mb-0.5">{icon} {label}</div>
      <p className="font-bold text-slate-800 text-sm">{value.toLocaleString()}</p>
    </div>
  );
}

function QuickLink({ href, icon, label, sub }: { href: string; icon: React.ReactNode; label: string; sub: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer"
      className="flex items-center gap-2.5 px-3 py-2 bg-white rounded-lg border border-slate-200 hover:border-slate-300 hover:bg-slate-50 transition-colors group">
      <span className="text-slate-500 group-hover:text-slate-700">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-slate-700">{label}</p>
        <p className="text-[10px] text-slate-400 truncate">{sub}</p>
      </div>
      <ExternalLink size={11} className="text-slate-300 group-hover:text-slate-500 shrink-0" />
    </a>
  );
}

function PostsPanel({ posts, wpSlug }: { posts: WpPost[]; wpSlug: string }) {
  const [items, setItems] = useState(posts);
  useEffect(() => { setItems(posts); }, [posts]);

  if (items.length === 0) {
    return (
      <div className="px-4 py-3">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Blog Posts</p>
        <p className="text-xs text-slate-400 text-center py-6">No posts yet</p>
      </div>
    );
  }

  return (
    <div className="px-4 py-3 space-y-2">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Blog Posts</p>
      {items.map((post) => (
        <PostRow key={post.id} post={post} wpSlug={wpSlug}
          onRemove={(id) => setItems((prev) => prev.filter((p) => p.id !== id))}
          onDraft={(id) => setItems((prev) => prev.map((p) => p.id === id ? { ...p, status: "draft" } : p))}
        />
      ))}
    </div>
  );
}

function PostRow({ post, wpSlug, onRemove, onDraft }: {
  post: WpPost;
  wpSlug: string;
  onRemove: (id: number) => void;
  onDraft: (id: number) => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [unpublishing, setUnpublishing] = useState(false);
  const [err, setErr] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);

  async function deletePost() {
    setDeleting(true); setErr("");
    try {
      await api.delete(`/blog/clients/${wpSlug}/posts/${post.id}`);
      onRemove(post.id);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Failed to delete"); }
    finally { setDeleting(false); setConfirmDel(false); }
  }

  async function unpublishPost() {
    setUnpublishing(true); setErr("");
    try {
      await api.post(`/blog/clients/${wpSlug}/posts/${post.id}/unpublish`, {});
      onDraft(post.id);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "Failed to unpublish"); }
    finally { setUnpublishing(false); }
  }

  const isDraft = post.status === "draft";

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-3 space-y-1.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-slate-700 truncate"
            dangerouslySetInnerHTML={{ __html: post.title || "Untitled" }} />
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`text-[9px] font-semibold rounded-full px-1.5 py-0.5 uppercase tracking-wide ${
              isDraft ? "bg-slate-100 text-slate-500" : "bg-emerald-100 text-emerald-700"
            }`}>{isDraft ? "Draft" : "Published"}</span>
            <span className="text-[10px] text-slate-400 flex items-center gap-1">
              <Calendar size={9} /> {new Date(post.date).toLocaleDateString()}
            </span>
          </div>
        </div>
        {post.link && !isDraft && (
          <a href={post.link} target="_blank" rel="noopener noreferrer"
            className="text-[10px] text-blue-500 hover:underline shrink-0 flex items-center gap-0.5 mt-0.5">
            <ExternalLink size={9} /> View
          </a>
        )}
      </div>
      {err && <p className="text-[10px] text-rose-500">{err}</p>}
      <div className="flex items-center gap-3 pt-0.5">
        {!isDraft && (
          <button onClick={unpublishPost} disabled={unpublishing}
            className="flex items-center gap-1 text-[10px] text-amber-600 hover:text-amber-800 font-medium transition-colors disabled:opacity-50">
            {unpublishing ? <Loader2 size={10} className="animate-spin" /> : <EyeOff size={10} />}
            {unpublishing ? "Unpublishing…" : "Unpublish"}
          </button>
        )}
        {!confirmDel ? (
          <button onClick={() => setConfirmDel(true)}
            className="flex items-center gap-1 text-[10px] text-rose-500 hover:text-rose-700 font-medium transition-colors">
            <Trash2 size={10} /> Delete
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500">Permanently delete?</span>
            <button onClick={deletePost} disabled={deleting}
              className="text-[10px] font-semibold text-white bg-rose-500 hover:bg-rose-600 rounded px-1.5 py-0.5 disabled:opacity-50">
              {deleting ? "Deleting…" : "Yes, delete"}
            </button>
            <button onClick={() => setConfirmDel(false)}
              className="text-[10px] text-slate-400 hover:text-slate-600">Cancel</button>
          </div>
        )}
      </div>
    </div>
  );
}

function CommentsPanel({ comments, wpSlug }: { comments: Comment[]; wpSlug: string }) {
  if (comments.length === 0) {
    return (
      <div className="px-4 py-3">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Blog Comments</p>
        <p className="text-xs text-slate-400 text-center py-6">No comments yet</p>
      </div>
    );
  }

  // Group by post_id
  const groups = new Map<number, { title: string; link: string; comments: Comment[] }>();
  for (const c of comments) {
    if (!groups.has(c.post_id)) {
      groups.set(c.post_id, { title: c.post_title, link: c.post_link, comments: [] });
    }
    groups.get(c.post_id)!.comments.push(c);
  }

  const pending = comments.filter((c) => c.status === "hold" || c.status === "pending").length;

  return (
    <div className="px-4 py-3 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Blog Comments
        </p>
        {pending > 0 && (
          <span className="text-[10px] font-semibold bg-amber-100 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5">
            {pending} awaiting moderation
          </span>
        )}
      </div>
      {Array.from(groups.entries()).map(([postId, group]) => (
        <div key={postId} className="space-y-2">
          {/* Post header */}
          <div className="flex items-center gap-2">
            <BookOpen size={11} className="text-slate-400 shrink-0" />
            <span className="text-xs font-semibold text-slate-700 truncate flex-1"
              dangerouslySetInnerHTML={{ __html: group.title }} />
            {group.link && (
              <a href={group.link} target="_blank" rel="noopener noreferrer"
                className="text-[10px] text-blue-500 hover:underline shrink-0 flex items-center gap-0.5">
                <ExternalLink size={9} /> View post
              </a>
            )}
          </div>
          {/* Comments under this post — only top-level (parent=0), replies indented */}
          {group.comments.filter((c) => c.parent === 0).map((c) => (
            <div key={c.id} className="space-y-1.5 pl-3 border-l-2 border-slate-200">
              <CommentCard comment={c} wpSlug={wpSlug} />
              {/* Replies to this comment */}
              {group.comments.filter((r) => r.parent === c.id).map((reply) => (
                <div key={reply.id} className="pl-3 border-l-2 border-blue-100">
                  <CommentCard comment={reply} wpSlug={wpSlug} isReply />
                </div>
              ))}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function CommentCard({ comment, wpSlug, isReply = false, onDeleted }: {
  comment: Comment; wpSlug: string; isReply?: boolean; onDeleted?: (id: number) => void;
}) {
  const [showReply, setShowReply] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState("");
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);

  async function sendReply() {
    if (!replyText.trim()) return;
    setSending(true);
    setErr("");
    try {
      await api.post(`/blog/clients/${wpSlug}/comments/${comment.id}/reply`, { content: replyText });
      setSent(true);
      setReplyText("");
      setShowReply(false);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to send reply");
    } finally {
      setSending(false);
    }
  }

  async function approveComment() {
    setApproving(true);
    try {
      await api.post(`/blog/clients/${wpSlug}/comments/${comment.id}/approve`, {});
      setApproved(true);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to approve");
    } finally {
      setApproving(false);
    }
  }

  async function deleteComment() {
    setDeleting(true); setErr("");
    try {
      await api.delete(`/blog/clients/${wpSlug}/comments/${comment.id}`);
      setDeleted(true);
      onDeleted?.(comment.id);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setDeleting(false); setConfirmDel(false);
    }
  }

  if (deleted) return null;

  const isPending = !approved && (comment.status === "hold" || comment.status === "pending");

  return (
    <div className={`bg-white rounded-lg border p-3 space-y-2 ${isPending ? "border-amber-200 bg-amber-50/40" : "border-slate-200"}`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
          <User size={11} className="text-slate-400" /> {comment.author || "Anonymous"}
        </span>
        <div className="flex items-center gap-2">
          {isPending && (
            <span className="text-[9px] font-semibold bg-amber-100 text-amber-700 border border-amber-200 rounded-full px-1.5 py-0.5 uppercase tracking-wide">
              Pending
            </span>
          )}
          <span className="flex items-center gap-1 text-[10px] text-slate-400">
            <Calendar size={10} /> {new Date(comment.date).toLocaleDateString()}
          </span>
        </div>
      </div>
      <p className="text-xs text-slate-600 leading-relaxed">
        {comment.content.replace(/<[^>]*>/g, "")}
      </p>
      {comment.email && <p className="text-[10px] text-slate-400">{comment.email}</p>}

      {sent && (
        <p className="flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
          <Check size={10} /> Reply posted
        </p>
      )}

      {err && !showReply && <p className="text-[10px] text-rose-500">{err}</p>}

      {approved && (
        <p className="flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
          <Check size={10} /> Approved — now visible on the blog
        </p>
      )}

      {!sent && !isReply && (
        <>
          <div className="flex items-center gap-3 flex-wrap">
            {isPending && (
              <button
                onClick={approveComment}
                disabled={approving}
                className="flex items-center gap-1 text-[10px] text-emerald-700 hover:text-emerald-900 font-medium transition-colors disabled:opacity-50"
              >
                {approving ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                {approving ? "Approving…" : "Approve"}
              </button>
            )}
            <button
              onClick={() => setShowReply((v) => !v)}
              className="flex items-center gap-1 text-[10px] text-blue-600 hover:text-blue-800 font-medium transition-colors"
            >
              <CornerDownRight size={10} /> {showReply ? "Cancel" : "Reply"}
            </button>
            {!confirmDel ? (
              <button onClick={() => setConfirmDel(true)}
                className="flex items-center gap-1 text-[10px] text-rose-500 hover:text-rose-700 font-medium transition-colors ml-auto">
                <Trash2 size={10} /> Delete
              </button>
            ) : (
              <div className="flex items-center gap-2 ml-auto">
                <span className="text-[10px] text-slate-500">Delete this comment?</span>
                <button onClick={deleteComment} disabled={deleting}
                  className="text-[10px] font-semibold text-white bg-rose-500 hover:bg-rose-600 rounded px-1.5 py-0.5 disabled:opacity-50">
                  {deleting ? "Deleting…" : "Yes"}
                </button>
                <button onClick={() => setConfirmDel(false)} className="text-[10px] text-slate-400 hover:text-slate-600">No</button>
              </div>
            )}
          </div>
          {showReply && (
            <div className="space-y-1.5 pt-1">
              <textarea
                rows={2}
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                placeholder="Write your reply…"
                className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-200"
              />
              {err && <p className="text-[10px] text-rose-500">{err}</p>}
              <button
                onClick={sendReply}
                disabled={sending || !replyText.trim()}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium"
              >
                {sending ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
                {sending ? "Sending…" : "Send Reply"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

"use client";

import React, { useEffect, useState } from "react";
import { blogApi, type BlogStatus, type BlogPost } from "@/lib/api";
import {
  Rss,
  Globe,
  Zap,
  CheckCircle,
  XCircle,
  RefreshCw,
  ExternalLink,
  PenLine,
  Calendar,
  TrendingUp,
  Loader2,
  AlertCircle,
} from "lucide-react";

const INDUSTRIES = [
  { value: "startup", label: "Startup / Tech" },
  { value: "retail", label: "Retail / Shop" },
  { value: "restaurant", label: "Restaurant / Food" },
  { value: "health", label: "Health / Wellness" },
  { value: "beauty", label: "Beauty / Salon" },
  { value: "real_estate", label: "Real Estate" },
  { value: "education", label: "Education / Coaching" },
  { value: "finance", label: "Finance / Accounting" },
  { value: "legal", label: "Legal Services" },
  { value: "logistics", label: "Logistics / Delivery" },
  { value: "hospitality", label: "Hospitality / Hotel" },
  { value: "services", label: "General Services" },
];

function Badge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
        active
          ? "bg-green-100 text-green-700 border border-green-200"
          : "bg-slate-100 text-slate-500 border border-slate-200"
      }`}
    >
      {active ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
      {active ? "Active" : "Paused"}
    </span>
  );
}

export default function BlogPage() {
  const [blog, setBlog] = useState<BlogStatus | null>(null);
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Activate form state
  const [form, setForm] = useState({
    business_name: "",
    client_email: "",
    industry: "startup",
    location: "",
  });

  useEffect(() => {
    fetchBlog();
  }, []);

  async function fetchBlog() {
    setLoading(true);
    try {
      const data = await blogApi.getMyBlog();
      setBlog(data);
      if (data.connected && data.wp_slug) {
        const postsData = await blogApi.getPosts(data.wp_slug);
        setPosts(postsData.posts ?? []);
      }
    } catch {
      setError("Failed to load blog data.");
    } finally {
      setLoading(false);
    }
  }

  async function handleActivate(e: React.FormEvent) {
    e.preventDefault();
    setActivating(true);
    setError("");
    setSuccess("");
    try {
      // Use user email as client_id seed
      const clientId = `user-${Date.now()}`;
      await blogApi.create({
        client_id: clientId,
        business_name: form.business_name,
        client_email: form.client_email,
        industry: form.industry,
        location: form.location,
      });
      setSuccess("Blog activated! Your WordPress subsite is being set up.");
      await fetchBlog();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to activate blog.");
    } finally {
      setActivating(false);
    }
  }

  async function handlePublishNow() {
    if (!blog?.wp_slug) return;
    setPublishing(true);
    setError("");
    setSuccess("");
    try {
      const result = await blogApi.publishNow(blog.wp_slug);
      setSuccess(`Published: "${result.topic}"`);
      await fetchBlog();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to publish post.");
    } finally {
      setPublishing(false);
    }
  }

  async function handleToggleActive() {
    if (!blog?.wp_slug) return;
    setError("");
    try {
      if (blog.active) {
        await blogApi.deactivate(blog.wp_slug);
        setSuccess("Blog paused.");
      } else {
        await blogApi.activate(blog.wp_slug);
        setSuccess("Blog resumed.");
      }
      await fetchBlog();
    } catch {
      setError("Failed to update blog status.");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 bg-indigo-100 rounded-xl">
          <Rss className="w-6 h-6 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Autoblogging</h1>
          <p className="text-sm text-slate-500">
            AI writes and publishes SEO blog posts daily from your customer conversations.
          </p>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
          <CheckCircle className="w-4 h-4 shrink-0" />
          {success}
        </div>
      )}

      {!blog?.connected ? (
        /* ── Activation Form ────────────────────────────────────────────────── */
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <Zap className="w-5 h-5 text-amber-500" />
            <h2 className="text-lg font-semibold text-slate-800">Activate Your Blog</h2>
          </div>

          <div className="mb-6 p-4 bg-indigo-50 rounded-xl text-sm text-indigo-700 space-y-1">
            <p className="font-semibold">What happens when you activate:</p>
            <ul className="list-disc list-inside space-y-0.5 text-indigo-600">
              <li>A WordPress subsite is created at <span className="font-mono text-xs">your-business.blogs.zilo.pro</span></li>
              <li>AI analyses your WhatsApp chats to find blog topics</li>
              <li>1–7 SEO posts are published weekly (based on your plan)</li>
              <li>Posts target local Google searches in your city</li>
            </ul>
          </div>

          <form onSubmit={handleActivate} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Business Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={form.business_name}
                  onChange={e => setForm(f => ({ ...f, business_name: e.target.value }))}
                  placeholder="e.g. Mama Njeri's Kitchen"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Business Email <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  required
                  value={form.client_email}
                  onChange={e => setForm(f => ({ ...f, client_email: e.target.value }))}
                  placeholder="you@business.com"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Industry <span className="text-red-500">*</span>
                </label>
                <select
                  value={form.industry}
                  onChange={e => setForm(f => ({ ...f, industry: e.target.value }))}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {INDUSTRIES.map(i => (
                    <option key={i.value} value={i.value}>{i.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  City / Location <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={form.location}
                  onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
                  placeholder="e.g. Nairobi, Westlands"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={activating}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {activating ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Activating…</>
              ) : (
                <><Zap className="w-4 h-4" /> Activate My Blog</>
              )}
            </button>
          </form>
        </div>
      ) : (
        /* ── Blog Dashboard ─────────────────────────────────────────────────── */
        <div className="space-y-6">
          {/* Status card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 rounded-xl">
                  <Globe className="w-5 h-5 text-green-600" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-slate-800">Your Blog</h2>
                    <Badge active={blog.active ?? true} />
                  </div>
                  <a
                    href={blog.blog_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-indigo-600 hover:underline flex items-center gap-1 mt-0.5"
                  >
                    {blog.blog_url}
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={handleToggleActive}
                  className="text-xs border border-slate-300 rounded-lg px-3 py-1.5 hover:bg-slate-50 transition text-slate-600"
                >
                  {blog.active ? "Pause" : "Resume"}
                </button>
                <button
                  onClick={handlePublishNow}
                  disabled={publishing}
                  className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-1.5 rounded-lg transition disabled:opacity-60"
                >
                  {publishing ? (
                    <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Publishing…</>
                  ) : (
                    <><PenLine className="w-3.5 h-3.5" /> Publish Now</>
                  )}
                </button>
              </div>
            </div>

            {/* Stats row */}
            <div className="mt-6 grid grid-cols-3 gap-4">
              <div className="bg-slate-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-indigo-600">{blog.posts_count ?? 0}</p>
                <p className="text-xs text-slate-500 mt-1">Posts Published</p>
              </div>
              <div className="bg-slate-50 rounded-xl p-4 text-center">
                <p className="text-sm font-semibold text-slate-700 capitalize">{blog.industry ?? "—"}</p>
                <p className="text-xs text-slate-500 mt-1">Industry</p>
              </div>
              <div className="bg-slate-50 rounded-xl p-4 text-center">
                <p className="text-sm font-semibold text-slate-700">
                  {blog.last_posted_at
                    ? new Date(blog.last_posted_at).toLocaleDateString()
                    : "No posts yet"}
                </p>
                <p className="text-xs text-slate-500 mt-1">Last Published</p>
              </div>
            </div>

            {/* Info row */}
            <div className="mt-4 flex flex-wrap gap-3">
              <span className="inline-flex items-center gap-1 text-xs text-slate-500 bg-slate-100 rounded-full px-3 py-1">
                <Calendar className="w-3 h-3" /> Daily posts at 9 AM EAT
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-slate-500 bg-slate-100 rounded-full px-3 py-1">
                <TrendingUp className="w-3 h-3" /> SEO-optimised for {blog.location}
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-slate-500 bg-slate-100 rounded-full px-3 py-1">
                <RefreshCw className="w-3 h-3" /> Topics from your WhatsApp chats
              </span>
            </div>
          </div>

          {/* Recent Posts */}
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="font-semibold text-slate-800">Recent Posts</h3>
              <span className="text-xs text-slate-400">{posts.length} post{posts.length !== 1 ? "s" : ""}</span>
            </div>

            {posts.length === 0 ? (
              <div className="px-6 py-12 text-center">
                <PenLine className="w-8 h-8 text-slate-300 mx-auto mb-3" />
                <p className="text-sm text-slate-500">No posts yet.</p>
                <p className="text-xs text-slate-400 mt-1">
                  Your first post will be published tomorrow at 9 AM, or click <strong>Publish Now</strong>.
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {posts.map((post, i) => (
                  <li key={i} className="px-6 py-4 flex items-start justify-between gap-4 hover:bg-slate-50 transition">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">{post.title}</p>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {(post.keywords ?? []).slice(0, 3).map((kw, j) => (
                          <span key={j} className="text-xs bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full">
                            {kw}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-xs text-slate-400 whitespace-nowrap">
                        {new Date(post.published_at).toLocaleDateString()}
                      </span>
                      <a
                        href={post.post_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-500 hover:text-indigo-700"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Globe, Plus, Trash2, RefreshCw, Loader2, TrendingUp, AlertCircle } from "lucide-react";

interface Competitor { _id: string; name: string; website?: string; industry?: string; }
interface Insight { _id: string; competitor_name: string; summary: string; created_at: string; }

export default function CompetitorsPage() {
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [form, setForm] = useState({ name: "", website: "", industry: "" });
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [c, i] = await Promise.all([
        api.get<{ competitors: Competitor[] }>("/growth/competitors"),
        api.get<{ insights: Insight[] }>("/growth/competitors/insights"),
      ]);
      setCompetitors(c.competitors);
      setInsights(i.insights);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally { setLoading(false); }
  }

  async function addCompetitor() {
    if (!form.name.trim()) return;
    setAdding(true);
    setError("");
    try {
      await api.post("/growth/competitors", form);
      setForm({ name: "", website: "", industry: "" });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to add competitor");
    } finally { setAdding(false); }
  }

  async function remove(id: string) {
    try {
      await api.delete(`/growth/competitors/${id}`);
      setCompetitors(c => c.filter(x => x._id !== id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to remove");
    }
  }

  async function refreshInsights() {
    if (competitors.length === 0) return;
    setRefreshing(true);
    setError("");
    try {
      const data = await api.post<{ insights: Insight[] }>("/growth/competitors/insights/refresh", {});
      setInsights(data.insights);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to refresh insights");
    } finally { setRefreshing(false); }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Globe size={22} className="text-purple-500" /> Competitor Intelligence
          </h1>
          <p className="text-sm text-slate-500 mt-1">Track competitors and get weekly AI-powered insights from public data.</p>
        </div>
        <button onClick={refreshInsights} disabled={refreshing || competitors.length === 0}
          className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm rounded-lg hover:bg-brand disabled:opacity-50 font-medium">
          {refreshing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Refresh Insights
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3">
          <AlertCircle size={15} className="shrink-0" /> {error}
        </div>
      )}

      {/* Add competitor */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h3 className="font-semibold text-slate-800 text-sm mb-3">Track a Competitor</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            placeholder="Competitor name *"
            className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/30" />
          <input value={form.website} onChange={e => setForm(f => ({ ...f, website: e.target.value }))}
            placeholder="Website (optional)"
            className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/30" />
          <input value={form.industry} onChange={e => setForm(f => ({ ...f, industry: e.target.value }))}
            placeholder="Industry (optional)"
            className="text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/30" />
        </div>
        <button onClick={addCompetitor} disabled={adding || !form.name.trim()}
          className="mt-3 flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm rounded-lg hover:bg-brand disabled:opacity-50 font-medium">
          {adding ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Add
        </button>
      </div>

      {/* Tracked competitors */}
      {competitors.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <h3 className="font-semibold text-slate-800 text-sm mb-3">Tracked Competitors</h3>
          <div className="flex flex-wrap gap-2">
            {competitors.map(c => (
              <div key={c._id} className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
                <span className="text-sm font-medium text-slate-700">{c.name}</span>
                {c.website && <span className="text-xs text-slate-400">{c.website}</span>}
                <button onClick={() => remove(c._id)} className="text-slate-300 hover:text-rose-400 transition-colors">
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Insights */}
      <div>
        <h3 className="font-semibold text-slate-800 text-sm mb-3 flex items-center gap-2">
          <TrendingUp size={14} className="text-purple-500" /> Latest Insights
        </h3>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 animate-pulse h-24" />
            ))}
          </div>
        ) : insights.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
            <AlertCircle size={28} className="mx-auto text-slate-300 mb-2" />
            <p className="text-sm text-slate-500">
              {competitors.length === 0
                ? "Add competitors above, then click Refresh Insights to get AI analysis."
                : "No insights yet. Click Refresh Insights to analyse your competitors."}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {insights.map(ins => (
              <div key={ins._id} className="bg-white rounded-xl border border-slate-200 p-5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-purple-600 bg-purple-50 px-2 py-0.5 rounded-full">
                    {ins.competitor_name}
                  </span>
                  <span className="text-xs text-slate-400">{new Date(ins.created_at).toLocaleDateString()}</span>
                </div>
                <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{ins.summary}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

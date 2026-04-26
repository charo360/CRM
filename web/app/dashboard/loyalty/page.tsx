"use client";
import { useEffect, useState, useCallback } from "react";
import { loyaltyApi } from "@/lib/api";
import { Star, Plus, Users, Settings, RefreshCw, Trophy, Gift } from "lucide-react";

type Member = { id: string; customer_id: string; customer_name: string; points: number; lifetime_points: number; tier: string; updated_at: string };
type LoyaltySettings = { points_per_kes: number; kes_per_point: number; tiers: { name: string; min_points: number; color: string }[]; enabled: boolean };
type Summary = { total_members: number; total_active_points: number; members_by_tier: Record<string, number> };

const TIER_COLOR: Record<string, string> = { Bronze: "text-amber-700 bg-amber-50", Silver: "text-slate-500 bg-slate-100", Gold: "text-yellow-600 bg-yellow-50", Platinum: "text-brand-dark bg-brand/10" };

export default function LoyaltyPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [settings, setSettings] = useState<LoyaltySettings | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"members" | "settings">("members");
  const [txnModal, setTxnModal] = useState<Member | null>(null);
  const [txnForm, setTxnForm] = useState({ type: "earn", points: 100, reason: "" });
  const [manualModal, setManualModal] = useState(false);
  const [manualForm, setManualForm] = useState({ customer_id: "", customer_name: "", type: "earn", points: 100, reason: "" });
  const [settingsForm, setSettingsForm] = useState({ points_per_kes: 0.01, kes_per_point: 0.5 });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [mem, set, sum] = await Promise.all([loyaltyApi.listMembers(), loyaltyApi.getSettings(), loyaltyApi.summary()]);
      setMembers(mem as Member[]);
      const s = set as LoyaltySettings;
      setSettings(s);
      setSettingsForm({ points_per_kes: s.points_per_kes, kes_per_point: s.kes_per_point });
      setSummary(sum as Summary);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function recordTxn() {
    if (!txnModal) return;
    await loyaltyApi.addTransaction({ customer_id: txnModal.customer_id, ...txnForm });
    setTxnModal(null);
    await load();
  }

  async function addManual() {
    if (!manualForm.customer_id) return;
    await loyaltyApi.addTransaction({ ...manualForm });
    setManualModal(false);
    await load();
  }

  async function saveSettings() {
    setSaving(true);
    try { await loyaltyApi.updateSettings(settingsForm); await load(); }
    finally { setSaving(false); }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Star className="text-yellow-500" size={24} /> Customer Loyalty
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Reward your best customers with points and perks</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => { setManualModal(true); setManualForm({ customer_id: "", customer_name: "", type: "earn", points: 100, reason: "" }); }}
            className="flex items-center gap-2 border border-slate-200 text-slate-700 px-3 py-2 rounded-lg text-sm hover:bg-slate-50">
            <Plus size={15} /> Add Points
          </button>
        </div>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-2 text-slate-500 text-xs mb-1"><Users size={14} /> Members</div>
            <p className="text-2xl font-bold text-slate-800">{summary.total_members}</p>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-2 text-slate-500 text-xs mb-1"><Trophy size={14} /> Active Points</div>
            <p className="text-2xl font-bold text-brand-dark">{summary.total_active_points.toLocaleString()}</p>
          </div>
          {Object.entries(summary.members_by_tier).map(([tier, count]) => (
            <div key={tier} className="bg-white rounded-xl border p-4">
              <div className="text-xs text-slate-500 mb-1">{tier}</div>
              <p className="text-2xl font-bold text-slate-800">{count}</p>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 rounded-lg p-1 w-fit">
        {(["members","settings"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium capitalize transition-colors ${tab === t ? "bg-white shadow text-slate-800" : "text-slate-500 hover:text-slate-700"}`}>
            {t === "members" ? <span className="flex items-center gap-1.5"><Users size={14} /> Members</span> : <span className="flex items-center gap-1.5"><Settings size={14} /> Settings</span>}
          </button>
        ))}
        <button onClick={load} className="ml-2 text-slate-400 hover:text-slate-700 px-2"><RefreshCw size={14} /></button>
      </div>

      {/* Members tab */}
      {tab === "members" && (
        loading ? (
          <div className="flex items-center justify-center h-40 text-slate-400">Loading...</div>
        ) : members.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
            <Star size={40} className="opacity-30" />
            <p>No loyalty members yet. Add points for your first customer!</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-3">Customer</th>
                  <th className="text-right px-4 py-3">Points</th>
                  <th className="text-right px-4 py-3">Lifetime</th>
                  <th className="text-left px-4 py-3">Tier</th>
                  <th className="text-right px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {members.map(m => (
                  <tr key={m.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{m.customer_name || "—"}</p>
                      <p className="text-xs text-slate-400">{m.customer_id.slice(0,8)}...</p>
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-brand-dark">{m.points.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-slate-500">{m.lifetime_points.toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${TIER_COLOR[m.tier] || "bg-slate-100 text-slate-600"}`}>
                        {m.tier}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => { setTxnModal(m); setTxnForm({ type: "earn", points: 100, reason: "" }); }}
                        className="text-slate-400 hover:text-brand-dark text-xs flex items-center gap-1 ml-auto">
                        <Gift size={14} /> Points
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Settings tab */}
      {tab === "settings" && settings && (
        <div className="bg-white rounded-xl border p-6 space-y-6 max-w-lg">
          <h3 className="font-semibold text-slate-800">Points Configuration</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Points per KES spent</label>
              <input type="number" step="0.001" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                value={settingsForm.points_per_kes} onChange={e => setSettingsForm(f => ({ ...f, points_per_kes: +e.target.value }))} />
              <p className="text-xs text-slate-400 mt-1">e.g. 0.01 = 1 point per KES 100 spent</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">KES per point (redemption)</label>
              <input type="number" step="0.1" min="0" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                value={settingsForm.kes_per_point} onChange={e => setSettingsForm(f => ({ ...f, kes_per_point: +e.target.value }))} />
              <p className="text-xs text-slate-400 mt-1">e.g. 0.5 = 1 point = KES 0.50</p>
            </div>
          </div>
          <div>
            <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-3">Tiers</h4>
            <div className="space-y-2">
              {settings.tiers.map(t => (
                <div key={t.name} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <span className="font-medium text-sm" style={{ color: t.color }}>{t.name}</span>
                  <span className="text-xs text-slate-500">{t.min_points.toLocaleString()}+ points</span>
                </div>
              ))}
            </div>
          </div>
          <button onClick={saveSettings} disabled={saving}
            className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50">
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      )}

      {/* Txn Modal */}
      {txnModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setTxnModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100">
              <h2 className="text-lg font-semibold">Add Points — {txnModal.customer_name}</h2>
              <p className="text-sm text-slate-500 mt-1">Current balance: {txnModal.points} pts</p>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Type</label>
                <div className="flex gap-2">
                  {["earn","redeem"].map(t => (
                    <button key={t} onClick={() => setTxnForm(f => ({ ...f, type: t }))}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium capitalize border ${txnForm.type === t ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200"}`}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Points</label>
                <input type="number" min="1" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={txnForm.points}
                  onChange={e => setTxnForm(f => ({ ...f, points: +e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Reason</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={txnForm.reason}
                  onChange={e => setTxnForm(f => ({ ...f, reason: e.target.value }))} placeholder="Purchase, bonus, referral..." />
              </div>
            </div>
            <div className="p-6 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => setTxnModal(null)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={recordTxn} className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand">
                Record
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual add modal */}
      {manualModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setManualModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100"><h2 className="text-lg font-semibold">Add Points for Customer</h2></div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Customer ID (or phone)</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={manualForm.customer_id}
                  onChange={e => setManualForm(f => ({ ...f, customer_id: e.target.value }))} placeholder="Customer ID..." />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Customer name</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={manualForm.customer_name}
                  onChange={e => setManualForm(f => ({ ...f, customer_name: e.target.value }))} placeholder="Jane Wanjiku" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Points</label>
                <input type="number" min="1" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={manualForm.points}
                  onChange={e => setManualForm(f => ({ ...f, points: +e.target.value }))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Reason</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={manualForm.reason}
                  onChange={e => setManualForm(f => ({ ...f, reason: e.target.value }))} />
              </div>
            </div>
            <div className="p-6 border-t flex justify-end gap-3">
              <button onClick={() => setManualModal(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={addManual} disabled={!manualForm.customer_id} className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50">
                Add Points
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

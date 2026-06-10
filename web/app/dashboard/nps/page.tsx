"use client";
import { useEffect, useState, useCallback } from "react";
import { feedbackApi } from "@/lib/api";
import { MessageCircle, Plus, Trash2, RefreshCw, ThumbsUp, Minus, ThumbsDown, Star, Copy, Check, ExternalLink, PencilLine } from "lucide-react";
import { toast } from "sonner";

type SurveyQuestion = { id: string; text: string; type: "nps" | "rating" | "text" | "choice"; options?: string[] };
type Survey = { id: string; title: string; description: string; active: boolean; response_count: number; created_at: string; questions?: SurveyQuestion[] };
type Survey = { id: string; title: string; description: string; active: boolean; response_count: number; created_at: string; form_id?: string; slug?: string };
type NPSData = { nps_score: number; total_responses: number; promoters: number; passives: number; detractors: number; promoter_pct: number; detractor_pct: number; recent_comments: { name: string; score: number; comment: string }[] };
type Response = { id: string; customer_name: string; nps_score?: number; nps_category?: string; comment: string; created_at: string };
type SurveyForm = { title: string; description: string; active: boolean; questions: SurveyQuestion[] };
type ResponseAnswer = { question_id: string; answer: string | number };
type ResponseForm = { survey_id: string; customer_name: string; customer_phone: string; nps_score: number; comment: string; answers: ResponseAnswer[] };

const emptySurveyForm = (): SurveyForm => ({ title: "", description: "", active: true, questions: [] });
const emptyResponseForm = (surveyId = ""): ResponseForm => ({
  survey_id: surveyId,
  customer_name: "",
  customer_phone: "",
  nps_score: 8,
  comment: "",
  answers: [],
});

function NPSGauge({ score }: { score: number }) {
  const color = score >= 50 ? "text-green-600" : score >= 0 ? "text-amber-600" : "text-red-600";
  const label = score >= 50 ? "Excellent" : score >= 0 ? "Good" : "Needs improvement";
  return (
    <div className="flex flex-col items-center justify-center">
      <div className={`text-6xl font-bold ${color}`}>{score}</div>
      <div className="text-sm text-slate-500 mt-1">NPS Score</div>
      <div className={`text-xs font-medium mt-0.5 ${color}`}>{label}</div>
    </div>
  );
}

export default function NPSPage() {
  const [surveys, setSurveys] = useState<Survey[]>([]);
  const [nps, setNps] = useState<NPSData | null>(null);
  const [responses, setResponses] = useState<Response[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"dashboard" | "surveys" | "responses">("dashboard");
  const [selectedSurvey, setSelectedSurvey] = useState<string>("");
  const [showSurveyModal, setShowSurveyModal] = useState(false);
  const [surveyForm, setSurveyForm] = useState<SurveyForm>(emptySurveyForm());
  const [editingSurveyId, setEditingSurveyId] = useState<string | null>(null);
  const [showResponseModal, setShowResponseModal] = useState(false);
  const [responseForm, setResponseForm] = useState<ResponseForm>(emptyResponseForm());
  const [saving, setSaving] = useState(false);
  const [copiedSurveyId, setCopiedSurveyId] = useState<string>("");

  const copySurveyLink = (slug: string, id: string) => {
    const url = `${window.location.origin}/f/${slug}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedSurveyId(id);
      setTimeout(() => setCopiedSurveyId(""), 2000);
    });
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sv, np, rs] = await Promise.all([
        feedbackApi.listSurveys(),
        feedbackApi.nps(selectedSurvey || undefined),
        feedbackApi.listResponses(selectedSurvey || undefined),
      ]);
      setSurveys(sv as Survey[]);
      setNps(np as NPSData);
      setResponses(rs as Response[]);
    } finally { setLoading(false); }
  }, [selectedSurvey]);

  useEffect(() => { load(); }, [load]);

  async function createSurvey() {
    setSaving(true);
    try {
      const res = await feedbackApi.createSurvey(surveyForm) as any;
      setShowSurveyModal(false);
      await load();
      setTab("surveys");
      if (res && res.slug) {
        toast.success("NPS Survey created! Copy link to share.");
      } else {
        toast.success("NPS Survey created successfully!");
      }
    } catch (err: any) {
      toast.error(err?.message || "Failed to create survey");
    } finally {
      setSaving(false);
    }
  }

  async function updateSurvey() {
    if (!editingSurveyId) return;
    setSaving(true);
    try { await feedbackApi.updateSurvey(editingSurveyId, surveyForm); setShowSurveyModal(false); setEditingSurveyId(null); await load(); }
    finally { setSaving(false); }
  }

  async function deleteSurvey(id: string) {
    if (!confirm("Delete this survey and all responses?")) return;
    await feedbackApi.deleteSurvey(id);
    await load();
  }

  async function submitResponse() {
    setSaving(true);
    try {
      const res = await feedbackApi.submitResponse({ ...responseForm });
      setShowResponseModal(false);
      await load();
      const responseId = typeof res.id === "string" ? res.id : typeof res._id === "string" ? res._id : "";
      if (responseId) {
        const base = (typeof window !== 'undefined' && (process.env.NEXT_PUBLIC_APP_URL || window.location.origin)) || '';
        const url = `${base.replace(/\/$/, '')}/feedback/response/${responseId}`;
        try { await navigator.clipboard.writeText(url); alert('Response saved — link copied to clipboard:\n' + url); } catch { alert('Response saved — link: ' + url); }
      } else {
        alert('Response saved');
      }
    } finally { setSaving(false); }
  }

  const NPS_COLOR: Record<string, string> = { promoter: "text-green-600", passive: "text-amber-600", detractor: "text-red-600" };
  const NPS_ICON: Record<string, typeof ThumbsUp> = { promoter: ThumbsUp, passive: Minus, detractor: ThumbsDown };

  const addQuestion = () => {
    setSurveyForm((f) => ({
      ...f,
      questions: [
        ...(f.questions || []),
        { id: `q_${Date.now()}`, text: "", type: "text", options: [] },
      ],
    }));
  };

  const updateQuestion = (id: string, patch: Partial<SurveyQuestion>) => {
    setSurveyForm((f) => ({
      ...f,
      questions: (f.questions || []).map((q: SurveyQuestion) => {
        if (q.id !== id) return q;
        const next = { ...q, ...patch };
        if (patch.type && patch.type !== "choice") next.options = [];
        if (patch.type === "choice" && (!next.options || next.options.length === 0)) next.options = ["Option 1", "Option 2"];
        return next;
      }),
    }));
  };

  const removeQuestion = (id: string) => {
    setSurveyForm((f) => ({
      ...f,
      questions: (f.questions || []).filter((q: SurveyQuestion) => q.id !== id),
    }));
  };

  const addChoiceOption = (questionId: string) => {
    setSurveyForm((f) => ({
      ...f,
      questions: (f.questions || []).map((q: SurveyQuestion) =>
        q.id === questionId ? { ...q, options: [...(q.options || []), `Option ${(q.options || []).length + 1}`] } : q
      ),
    }));
  };

  const updateChoiceOption = (questionId: string, index: number, value: string) => {
    setSurveyForm((f) => ({
      ...f,
      questions: (f.questions || []).map((q: SurveyQuestion) =>
        q.id === questionId
          ? { ...q, options: (q.options || []).map((opt, i) => (i === index ? value : opt)) }
          : q
      ),
    }));
  };

  const removeChoiceOption = (questionId: string, index: number) => {
    setSurveyForm((f) => ({
      ...f,
      questions: (f.questions || []).map((q: SurveyQuestion) =>
        q.id === questionId
          ? { ...q, options: (q.options || []).filter((_, i) => i !== index) }
          : q
      ),
    }));
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <MessageCircle className="text-brand-dark" size={24} /> Customer Feedback & NPS
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">Measure customer satisfaction and collect feedback</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => { setShowResponseModal(true); setResponseForm(emptyResponseForm(surveys[0]?.id || "")); }}
            className="flex items-center gap-2 border border-slate-200 text-slate-700 px-3 py-2 rounded-lg text-sm hover:bg-slate-50">
            <Plus size={15} /> Log Response
          </button>
          <button onClick={() => { setShowSurveyModal(true); setEditingSurveyId(null); setSurveyForm(emptySurveyForm()); }}
            className="flex items-center gap-2 bg-brand-dark text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-brand">
            <Plus size={15} /> New Survey
          </button>
        </div>
      </div>

      {/* Survey filter */}
      <div className="flex gap-2 flex-wrap items-center">
        <span className="text-xs text-slate-500">Filter by survey:</span>
        <button onClick={() => setSelectedSurvey("")}
          className={`px-3 py-1 rounded-full text-xs border ${selectedSurvey === "" ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200"}`}>
          All
        </button>
        {surveys.map(s => (
          <button key={s.id} onClick={() => setSelectedSurvey(s.id)}
            className={`px-3 py-1 rounded-full text-xs border ${selectedSurvey === s.id ? "bg-brand-dark text-white border-brand-dark" : "bg-white text-slate-600 border-slate-200"}`}>
            {s.title}
          </button>
        ))}
        <button onClick={load} className="ml-auto text-slate-400 hover:text-slate-700"><RefreshCw size={16} /></button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 rounded-lg p-1 w-fit">
        {(["dashboard","surveys","responses"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium capitalize ${tab === t ? "bg-white shadow text-slate-800" : "text-slate-500 hover:text-slate-700"}`}>
            {t}
          </button>
        ))}
      </div>

      {/* Dashboard tab */}
      {tab === "dashboard" && (
        loading ? <div className="flex items-center justify-center h-40 text-slate-400">Loading...</div> :
        !nps || nps.total_responses === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
            <MessageCircle size={40} className="opacity-30" />
            <p>No responses yet. Log your first NPS response!</p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-white rounded-xl border p-6 flex items-center justify-center">
                <NPSGauge score={nps.nps_score} />
              </div>
              <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                <div className="flex items-center gap-2 text-green-700 text-xs font-medium mb-2"><ThumbsUp size={14} /> Promoters (9-10)</div>
                <p className="text-3xl font-bold text-green-800">{nps.promoters}</p>
                <p className="text-xs text-green-600">{nps.promoter_pct}% of responses</p>
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                <div className="flex items-center gap-2 text-amber-700 text-xs font-medium mb-2"><Minus size={14} /> Passives (7-8)</div>
                <p className="text-3xl font-bold text-amber-800">{nps.passives}</p>
                <p className="text-xs text-amber-600">{100 - nps.promoter_pct - nps.detractor_pct}% of responses</p>
              </div>
              <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                <div className="flex items-center gap-2 text-red-700 text-xs font-medium mb-2"><ThumbsDown size={14} /> Detractors (0-6)</div>
                <p className="text-3xl font-bold text-red-800">{nps.detractors}</p>
                <p className="text-xs text-red-600">{nps.detractor_pct}% of responses</p>
              </div>
            </div>
            {/* Score breakdown */}
            <div className="bg-white rounded-xl border p-4">
              <h3 className="font-semibold text-slate-700 mb-3 text-sm">NPS Scale</h3>
              <div className="flex gap-1">
                {[0,1,2,3,4,5,6,7,8,9,10].map(s => (
                  <div key={s} className={`flex-1 text-center py-2 rounded text-xs font-medium ${s >= 9 ? "bg-green-100 text-green-700" : s >= 7 ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"}`}>
                    {s}
                  </div>
                ))}
              </div>
              <div className="flex justify-between mt-1 text-xs text-slate-400">
                <span>Detractors</span><span>Passives</span><span>Promoters</span>
              </div>
            </div>
            {/* Recent comments */}
            {nps.recent_comments.length > 0 && (
              <div className="bg-white rounded-xl border p-4">
                <h3 className="font-semibold text-slate-700 mb-3 text-sm">Recent Comments</h3>
                <div className="space-y-3">
                  {nps.recent_comments.map((c, i) => {
                    const cat = c.score >= 9 ? "promoter" : c.score >= 7 ? "passive" : "detractor";
                    const Icon = NPS_ICON[cat];
                    return (
                      <div key={i} className="flex gap-3 items-start">
                        <Icon size={16} className={`mt-0.5 shrink-0 ${NPS_COLOR[cat]}`} />
                        <div>
                          <p className="text-sm text-slate-800">&ldquo;{c.comment}&rdquo;</p>
                          <p className="text-xs text-slate-400 mt-0.5">{c.name} — Score: {c.score}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )
      )}

      {/* Surveys tab */}
      {tab === "surveys" && (
        surveys.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
            <Star size={40} className="opacity-30" />
            <p>No surveys yet. Create your first survey!</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {surveys.map(s => (
              <div key={s.id} className="bg-white rounded-xl border p-5 flex flex-col gap-3 hover:border-slate-300 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-slate-800 text-sm truncate">{s.title}</p>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${s.active ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"}`}>
                        {s.active ? "Active" : "Inactive"}
                      </span>
                    </div>
                    {s.description && (
                      <p className="text-xs text-slate-500 mt-1 line-clamp-2">{s.description}</p>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 font-medium whitespace-nowrap">{s.response_count} response{s.response_count !== 1 ? "s" : ""}</p>
                </div>
                
                {s.slug && (
                  <div className="flex items-center gap-1.5 bg-slate-50 rounded-lg px-3 py-1.5 text-xs text-slate-500 font-mono truncate">
                    <span className="flex-1 truncate">/f/{s.slug}</span>
                    <button
                      onClick={() => copySurveyLink(s.slug!, s.id)}
                      className="shrink-0 text-slate-400 hover:text-slate-700 transition-colors"
                      title="Copy public link"
                    >
                      {copiedSurveyId === s.id ? <Check size={13} className="text-green-600 animate-in fade-in" /> : <Copy size={13} />}
                    </button>
                    <a
                      href={`/f/${s.slug}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 text-slate-400 hover:text-slate-700 transition-colors"
                      title="Open public form"
                    >
                      <ExternalLink size={12} />
                    </a>
                  </div>
                )}

                <div className="flex items-center gap-2 pt-1 border-t border-slate-100">
                  {s.form_id && (
                    <a
                      href={`/dashboard/forms/${s.form_id}`}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 font-medium"
                    >
                      <PencilLine size={11} /> Open Builder
                    </a>
                  )}
                  <button
                    onClick={() => deleteSurvey(s.id)}
                    className="ml-auto p-1.5 text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors"
                    title="Delete survey"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => { setShowSurveyModal(true); setSurveyForm({ title: s.title, description: s.description, active: !!s.active, questions: s.questions || [] }); setEditingSurveyId(s.id); }} className="text-slate-600 hover:text-slate-800">Edit</button>
                  <button onClick={() => { const base = (typeof window !== 'undefined' && (process.env.NEXT_PUBLIC_APP_URL || window.location.origin)) || ''; const url = `${base.replace(/\/$/, '')}/feedback/survey/${s.id}`; try { navigator.clipboard.writeText(url); alert('Survey link copied to clipboard:\n' + url); } catch { alert('Survey link: ' + url); } }} className="text-slate-600 hover:text-slate-800">Get link</button>
                  <button onClick={() => deleteSurvey(s.id)} className="text-slate-400 hover:text-red-500"><Trash2 size={16} /></button>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* Responses tab */}
      {tab === "responses" && (
        responses.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
            <MessageCircle size={40} className="opacity-30" />
            <p>No responses yet.</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-3">Customer</th>
                  <th className="text-left px-4 py-3">NPS Score</th>
                  <th className="text-left px-4 py-3">Comment</th>
                  <th className="text-left px-4 py-3">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {responses.map(r => {
                  const cat = r.nps_category || "passive";
                  return (
                    <tr key={r.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-800">{r.customer_name || "Anonymous"}</td>
                      <td className="px-4 py-3">
                        {r.nps_score !== undefined && (
                          <span className={`font-bold ${NPS_COLOR[cat]}`}>{r.nps_score}/10</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600 max-w-[250px] truncate">{r.comment || "—"}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{new Date(r.created_at).toLocaleDateString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Survey modal */}
      {showSurveyModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowSurveyModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100"><h2 className="text-lg font-semibold">{editingSurveyId ? "Edit Survey" : "New Survey"}</h2></div>
            <div className="p-6 space-y-4 max-h-[calc(90vh-9rem)] overflow-y-auto">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Title *</label>
                <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={surveyForm.title}
                  onChange={e => setSurveyForm(f => ({ ...f, title: e.target.value }))} placeholder="Customer Satisfaction Survey" />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
                <textarea className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" rows={2} value={surveyForm.description}
                  onChange={e => setSurveyForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-medium text-slate-600">Questions</label>
                  <button onClick={addQuestion} className="flex items-center gap-1 text-xs text-brand-dark font-medium">
                    <Plus size={14} /> Add question
                  </button>
                </div>
                <div className="space-y-3">
                  {(surveyForm.questions || []).map((q: SurveyQuestion, index: number) => (
                    <div key={q.id} className="border border-slate-200 rounded-lg p-3 space-y-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-slate-500">Question {index + 1}</span>
                        <button onClick={() => removeQuestion(q.id)} className="text-slate-400 hover:text-red-500">
                          <Trash2 size={15} />
                        </button>
                      </div>
                      <input
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                        value={q.text}
                        onChange={e => updateQuestion(q.id, { text: e.target.value })}
                        placeholder="Ask a question"
                      />
                      <select
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                        value={q.type}
                        onChange={e => updateQuestion(q.id, { type: e.target.value as SurveyQuestion["type"] })}
                      >
                        <option value="text">Text answer</option>
                        <option value="choice">Multiple choice</option>
                        <option value="rating">Rating 1-5</option>
                        <option value="nps">NPS 0-10</option>
                      </select>
                      {q.type === "choice" && (
                        <div className="space-y-2">
                          {(q.options || []).map((opt, optionIndex) => (
                            <div key={`${q.id}-${optionIndex}`} className="flex gap-2">
                              <input
                                className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm"
                                value={opt}
                                onChange={e => updateChoiceOption(q.id, optionIndex, e.target.value)}
                                placeholder={`Option ${optionIndex + 1}`}
                              />
                              <button onClick={() => removeChoiceOption(q.id, optionIndex)} className="px-2 text-slate-400 hover:text-red-500">
                                <Trash2 size={15} />
                              </button>
                            </div>
                          ))}
                          <button onClick={() => addChoiceOption(q.id)} className="text-xs text-brand-dark font-medium">
                            Add option
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {(surveyForm.questions || []).length === 0 && (
                    <p className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg p-3">
                      Add questions for customers to answer from their shared link.
                    </p>
                  )}
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={surveyForm.active} onChange={e => setSurveyForm(f => ({ ...f, active: e.target.checked }))} className="rounded" />
                Active
              </label>
            </div>
            <div className="p-6 border-t flex justify-end gap-3">
              <button onClick={() => setShowSurveyModal(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={editingSurveyId ? updateSurvey : createSurvey} disabled={saving || !surveyForm.title}
                className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50">
                {saving ? "Saving..." : editingSurveyId ? "Save Survey" : "Create Survey"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Response modal */}
      {showResponseModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowResponseModal(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-100"><h2 className="text-lg font-semibold">Log Customer Response</h2></div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Survey</label>
                <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={responseForm.survey_id}
                  onChange={e => setResponseForm(f => ({ ...f, survey_id: e.target.value }))}>
                  <option value="">Select survey...</option>
                  {surveys.filter(s => s.active).map(s => <option key={s.id} value={s.id}>{s.title}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Customer name</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={responseForm.customer_name}
                    onChange={e => setResponseForm(f => ({ ...f, customer_name: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Phone</label>
                  <input className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={responseForm.customer_phone}
                    onChange={e => setResponseForm(f => ({ ...f, customer_phone: e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-2">
                  NPS Score: <strong>{responseForm.nps_score}</strong>/10
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    {responseForm.nps_score >= 9 ? "😊 Promoter" : responseForm.nps_score >= 7 ? "😐 Passive" : "😞 Detractor"}
                  </span>
                </label>
                <input type="range" min="0" max="10" step="1" className="w-full accent-brand-dark" value={responseForm.nps_score}
                  onChange={e => setResponseForm(f => ({ ...f, nps_score: +e.target.value }))} />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>Not likely</span><span>Very likely</span>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Comment</label>
                <textarea className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" rows={2} value={responseForm.comment}
                  onChange={e => setResponseForm(f => ({ ...f, comment: e.target.value }))} placeholder="What can we improve?" />
              </div>

              {/* Dynamic survey questions */}
              {responseForm.survey_id && (() => {
                const cur = surveys.find(s => s.id === responseForm.survey_id);
                if (!cur || !cur.questions || cur.questions.length === 0) return null;
                return (
                  <div>
                    <h4 className="text-sm font-medium text-slate-700 mb-2">Survey questions</h4>
                    <div className="space-y-3">
                      {cur.questions.map((q) => {
                        const existing = responseForm.answers.find((a) => a.question_id === q.id);
                        const val = existing ? existing.answer : '';
                        const setAnswer = (v: string | number) => setResponseForm((f) => {
                          const answers = [...f.answers];
                          const qi = answers.findIndex((a) => a.question_id === q.id);
                          const entry = { question_id: q.id, answer: v };
                          if (qi === -1) answers.push(entry); else answers[qi] = entry;
                          return { ...f, answers };
                        });
                        return (
                          <div key={q.id}>
                            <label className="block text-xs text-slate-600 mb-1">{q.text || 'Question'}</label>
                            {q.type === 'text' && (
                              <input className="w-full border border-slate-200 rounded px-3 py-2 text-sm" value={val}
                                onChange={e => setAnswer(e.target.value)} />
                            )}
                            {q.type === 'nps' && (
                              <input type="range" min="0" max="10" value={val || responseForm.nps_score}
                                onChange={e => setAnswer(+e.target.value)} className="w-full" />
                            )}
                            {q.type === 'rating' && (
                              <select className="w-full border border-slate-200 rounded px-2 py-1 text-sm" value={val}
                                onChange={e => setAnswer(e.target.value)}>
                                <option value="">Select</option>
                                {[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
                              </select>
                            )}
                            {q.type === 'choice' && (
                              <select className="w-full border border-slate-200 rounded px-2 py-1 text-sm" value={val}
                                onChange={e => setAnswer(e.target.value)}>
                                <option value="">Select</option>
                                {(q.options||[]).map((opt: string, oi: number) => <option key={oi} value={opt}>{opt}</option>)}
                              </select>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })()}
            </div>
            <div className="p-6 border-t flex justify-end gap-3">
              <button onClick={() => setShowResponseModal(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
              <button onClick={submitResponse} disabled={saving || !responseForm.survey_id}
                className="px-4 py-2 bg-brand-dark text-white rounded-lg text-sm font-medium hover:bg-brand disabled:opacity-50">
                {saving ? "Saving..." : "Submit"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

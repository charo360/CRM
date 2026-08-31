"use client";
import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";

type SurveyAnswerValue = string | number;
type AnswerValue = SurveyAnswerValue | { label: string; value: string };

type SurveyQuestion = {
  id?: string;
  _id?: string;
  question_id?: string;
  key?: string;
  title?: string;
  text?: string;
  type: "text" | "nps" | "rating" | "choice";
  options?: string[];
};

type Survey = {
  id?: string;
  _id?: string;
  title: string;
  description?: string;
  questions?: SurveyQuestion[];
};

type FeedbackAnswer = {
  question_id: string;
  answer: AnswerValue;
};

type FeedbackPayload = {
  survey_id: string;
  request_token?: string;
  customer_name?: string;
  customer_phone?: string;
  nps_score?: number;
  answers: FeedbackAnswer[];
};

type FeedbackResponse = {
  id?: string;
  _id?: string;
};

function questionId(q: SurveyQuestion): string {
  return q.id || q._id || q.question_id || q.key || String(q.title || q.text || Math.random());
}

export default function SurveyClient({ surveyId }: { surveyId: string }) {
  const [survey, setSurvey] = useState<Survey | null>(null);
  const [loading, setLoading] = useState(true);
  const [answers, setAnswers] = useState<Record<string, SurveyAnswerValue | "">>({});
  const [extraFields, setExtraFields] = useState<Array<{ id: string; label: string; value: string }>>([]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    api.get<Survey>(`/feedback/public/surveys/${surveyId}`).then((s) => {
      if (!mounted) return;
      setSurvey(s);
      // initialize answers map
      const a: Record<string, SurveyAnswerValue | ""> = {};
      (s.questions || []).forEach((q) => {
        a[questionId(q)] = "";
      });
      setAnswers(a);
    }).catch((e) => {
      console.error(e);
    }).finally(() => setLoading(false));
    return () => { mounted = false; };
  }, [surveyId]);

  const setAnswer = (qid: string, val: SurveyAnswerValue | "") => setAnswers((prev) => ({ ...prev, [qid]: val }));

  const addExtra = () => setExtraFields((prev) => [...prev, { id: `custom_${Date.now()}`, label: "Custom field", value: "" }]);
  const removeExtra = (id: string) => setExtraFields((prev) => prev.filter((f) => f.id !== id));

  const submit = async () => {
    if (!survey) return;
    setSubmitting(true);
    try {
      const payload: FeedbackPayload = {
        survey_id: survey.id || survey._id || surveyId,
        customer_name: name || undefined,
        customer_phone: phone || undefined,
        answers: [],
      };
      const requestToken = typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("request")
        : null;
      if (requestToken) payload.request_token = requestToken;
      // push survey answers
      for (const q of (survey.questions || [])) {
        const qid = questionId(q);
        const a = answers[qid];
        if (a !== "" && a !== undefined) payload.answers.push({ question_id: qid, answer: a });
        if (q.type === "nps" && a !== "" && a !== undefined) {
          const score = Number(a);
          if (!Number.isNaN(score)) payload.nps_score = score;
        }
      }
      // push extra fields
      for (const f of extraFields) {
        payload.answers.push({ question_id: f.id, answer: { label: f.label, value: f.value } });
      }

      const res = await api.post<FeedbackResponse>(`/feedback/public/responses`, payload);
      const responseId = res?.id || res?._id;
      const base = (typeof window !== 'undefined' && (process.env.NEXT_PUBLIC_APP_URL || window.location.origin)) || '';
      const url = responseId ? `${base.replace(/\/$/, '')}/feedback/response/${responseId}` : null;
      if (url) {
        try { await navigator.clipboard.writeText(url); alert('Response submitted — link copied to clipboard:\n' + url); }
        catch { alert('Response submitted — link: ' + url); }
      } else {
        alert('Response submitted');
      }
    } catch (err: unknown) {
      alert('Submit failed: ' + (err instanceof Error ? err.message : String(err)));
    } finally { setSubmitting(false); }
  };

  if (loading) return <div className="p-6">Loading...</div>;
  if (!survey) return <div className="p-6">Survey not found</div>;

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-semibold">{survey.title}</h1>
      <p className="text-sm text-slate-500 mb-4">{survey.description}</p>

      <div className="mb-4">
        <label className="block text-xs">Your name</label>
        <input className="w-full border rounded px-2 py-1" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="mb-4">
        <label className="block text-xs">Phone</label>
        <input className="w-full border rounded px-2 py-1" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </div>

      <div className="space-y-4">
        {(survey.questions || []).map((q) => {
          const qid = questionId(q);
          const val = answers[qid] ?? "";
          return (
            <div key={qid}>
              <label className="block text-sm font-medium">{q.text || q.title || 'Question'}</label>
              {q.type === 'text' && (
                <input className="w-full border rounded px-2 py-1" value={val} onChange={(e) => setAnswer(qid, e.target.value)} />
              )}
              {q.type === 'nps' && (
                <input type="range" min={0} max={10} value={val || 5} onChange={(e) => setAnswer(qid, +e.target.value)} />
              )}
              {q.type === 'rating' && (
                <select className="w-full border rounded px-2 py-1" value={val} onChange={(e) => setAnswer(qid, e.target.value)}>
                  <option value="">Select</option>
                  {[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              )}
              {q.type === 'choice' && (
                <select className="w-full border rounded px-2 py-1" value={val} onChange={(e) => setAnswer(qid, e.target.value)}>
                  <option value="">Select</option>
                  {(q.options||[]).map((opt: string, i: number) => <option key={i} value={opt}>{opt}</option>)}
                </select>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-6">
        <h4 className="font-medium mb-2">Custom fields</h4>
        {extraFields.map(f => (
          <div key={f.id} className="flex gap-2 mb-2">
            <input className="flex-1 border rounded px-2 py-1" value={f.label} onChange={(e) => setExtraFields(prev => prev.map(x => x.id === f.id ? { ...x, label: e.target.value } : x))} />
            <input className="flex-1 border rounded px-2 py-1" value={f.value} onChange={(e) => setExtraFields(prev => prev.map(x => x.id === f.id ? { ...x, value: e.target.value } : x))} />
            <button onClick={() => removeExtra(f.id)} className="px-3 bg-red-100 text-red-700 rounded">Remove</button>
          </div>
        ))}
        <button onClick={addExtra} className="px-3 py-2 border rounded">Add field</button>
      </div>

      <div className="mt-6">
        <button onClick={submit} disabled={submitting} className="px-4 py-2 bg-brand-dark text-white rounded">
          {submitting ? 'Submitting...' : 'Submit'}
        </button>
      </div>
    </div>
  );
}

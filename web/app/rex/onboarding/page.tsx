"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Stage =
  | "welcome"
  | "question_1"
  | "question_2"
  | "question_3"
  | "question_4"
  | "question_5"
  | "question_6"
  | "scanning"
  | "i_see_it"
  | "complete";

interface StartResp {
  welcome: string;
  state: string;
  question: string | null;
}

interface AnswerResp {
  next_prompt: string;
  state: string;
  question: string | null;
  i_see_it: string | null;
  complete: boolean;
}

interface Preferences {
  business_type?: string;
  website_url?: string;
  pain_point?: string;
  channel?: string;
  directness?: string;
  good_week?: string;
  scan_findings?: Record<string, unknown>;
  website_insights?: Record<string, unknown>;
  i_see_it_moment?: string | null;
}

// ── Rex bubble ────────────────────────────────────────────────────────────
function RexBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 mb-6">
      <div className="w-9 h-9 rounded-full bg-slate-900 text-white flex items-center justify-center text-sm font-semibold shrink-0">
        R
      </div>
      <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 text-slate-900 whitespace-pre-line leading-relaxed max-w-prose">
        {children}
      </div>
    </div>
  );
}

function YouBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-end mb-6">
      <div className="bg-slate-900 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-prose">
        {children}
      </div>
    </div>
  );
}

export default function RexOnboardingPage() {
  const [stage, setStage] = useState<Stage>("welcome");
  const [transcript, setTranscript] = useState<{ who: "rex" | "you"; text: string }[]>([]);
  const [currentRexPrompt, setCurrentRexPrompt] = useState<string>("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [iSeeIt, setISeeIt] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [transcript, currentRexPrompt, iSeeIt]);

  function appendRex(text: string) {
    setTranscript((t) => [...t, { who: "rex", text }]);
  }
  function appendYou(text: string) {
    setTranscript((t) => [...t, { who: "you", text }]);
  }

  async function begin() {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.post<StartResp>("/rex/onboarding/start", {});
      appendRex(resp.welcome);
      setCurrentRexPrompt(resp.question || "");
      setStage("question_1");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start");
    } finally {
      setLoading(false);
    }
  }

  async function submitAnswer(questionNum: number, value: string, displayValue?: string) {
    setLoading(true);
    setError(null);
    try {
      appendYou(displayValue ?? value ?? "(skipped)");
      setInput("");
      const resp = await api.post<AnswerResp>(`/rex/onboarding/answer/${questionNum}`, { value });
      if (resp.i_see_it) {
        setISeeIt(resp.i_see_it);
        setStage("i_see_it");
        const prefs = await api.get<{ preferences: Preferences }>("/rex/onboarding/preferences");
        setPreferences(prefs.preferences);
      } else if (resp.complete) {
        appendRex(resp.next_prompt);
        setStage("complete");
      } else {
        appendRex(resp.next_prompt);
        setCurrentRexPrompt(resp.question || "");
        const nextStage = `question_${questionNum + 1}` as Stage;
        setStage(nextStage);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit");
    } finally {
      setLoading(false);
    }
  }

  async function reset() {
    setLoading(true);
    try {
      await api.post("/rex/onboarding/reset", {});
      setTranscript([]);
      setCurrentRexPrompt("");
      setInput("");
      setISeeIt(null);
      setPreferences(null);
      setError(null);
      setStage("welcome");
    } finally {
      setLoading(false);
    }
  }

  // Free-text questions
  const textQuestions: Record<number, Stage> = { 1: "question_1", 2: "question_2", 3: "question_3", 6: "question_6" };

  const currentQNum =
    stage === "question_1" ? 1 :
    stage === "question_2" ? 2 :
    stage === "question_3" ? 3 :
    stage === "question_4" ? 4 :
    stage === "question_5" ? 5 :
    stage === "question_6" ? 6 : 0;

  const isTextQuestion = currentQNum in textQuestions;
  const placeholderByQ: Record<number, string> = {
    1: "e.g., Marketing agency, e-commerce store, consulting…",
    2: "e.g., mycompany.com — or leave blank",
    3: "Be specific. What's the one thing?",
    6: "e.g., 3 new deals closed, inbox at zero, no fires…",
  };

  return (
    <div className="min-h-screen bg-white flex justify-center">
      <div className="w-full max-w-2xl px-6 py-10 flex flex-col">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-slate-900">Rex</h1>
          <p className="text-sm text-slate-500 mt-1">Day 0 — let&apos;s get to know each other.</p>
        </div>

        {/* Transcript */}
        <div ref={scrollerRef} className="flex-1 overflow-y-auto pr-1 mb-6">
          {transcript.map((m, i) =>
            m.who === "rex" ? (
              <RexBubble key={i}>{m.text}</RexBubble>
            ) : (
              <YouBubble key={i}>{m.text}</YouBubble>
            )
          )}

          {stage === "i_see_it" && iSeeIt && (
            <>
              <RexBubble>{iSeeIt}</RexBubble>
              {preferences && (
                <div className="mt-8 border border-slate-200 rounded-2xl p-5 bg-slate-50">
                  <div className="text-xs uppercase tracking-wide text-slate-500 mb-3">What I learned</div>
                  <dl className="space-y-2 text-sm">
                    <Row label="Business" value={preferences.business_type} />
                    <Row label="Website" value={preferences.website_url || "—"} />
                    <Row label="Pain point" value={preferences.pain_point} />
                    <Row label="Channel" value={preferences.channel} />
                    <Row label="Directness" value={preferences.directness} />
                    <Row label="Good week" value={preferences.good_week} />
                  </dl>
                  {preferences.website_insights && Object.keys(preferences.website_insights).length > 0 && (
                    <details className="mt-4">
                      <summary className="text-xs text-slate-500 cursor-pointer">Website insights (raw)</summary>
                      <pre className="text-xs bg-white border border-slate-200 rounded p-3 mt-2 overflow-auto">
                        {JSON.stringify(preferences.website_insights, null, 2)}
                      </pre>
                    </details>
                  )}
                  {preferences.scan_findings && (
                    <details className="mt-2">
                      <summary className="text-xs text-slate-500 cursor-pointer">Background scan (raw)</summary>
                      <pre className="text-xs bg-white border border-slate-200 rounded p-3 mt-2 overflow-auto">
                        {JSON.stringify(preferences.scan_findings, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              )}
              <div className="mt-6">
                <button
                  onClick={reset}
                  className="text-sm text-slate-500 hover:text-slate-900 underline underline-offset-4"
                >
                  Start over
                </button>
              </div>
            </>
          )}
        </div>

        {/* Input area */}
        {stage === "welcome" && (
          <div>
            <RexBubble>
              Before I start — give me five minutes. I want to know who you are and what&apos;s on your mind.
              When we&apos;re done, you&apos;ll see what I can already do.
            </RexBubble>
            <button
              onClick={begin}
              disabled={loading}
              className="bg-slate-900 hover:bg-slate-800 text-white font-medium px-5 py-3 rounded-xl disabled:opacity-50"
            >
              {loading ? "Starting…" : "Let&apos;s go"}
            </button>
          </div>
        )}

        {isTextQuestion && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (loading) return;
              submitAnswer(currentQNum, input.trim());
            }}
            className="flex gap-2"
          >
            <input
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={placeholderByQ[currentQNum]}
              className="flex-1 border border-slate-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-slate-900"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || (currentQNum !== 2 && !input.trim())}
              className="bg-slate-900 hover:bg-slate-800 text-white font-medium px-5 py-3 rounded-xl disabled:opacity-50"
            >
              {loading ? "…" : currentQNum === 2 && !input.trim() ? "Skip" : "Send"}
            </button>
          </form>
        )}

        {stage === "question_4" && (
          <ChoiceButtons
            options={[
              { value: "whatsapp", label: "WhatsApp" },
              { value: "telegram", label: "Telegram" },
              { value: "email", label: "Email" },
              { value: "in_app", label: "Inside the app" },
            ]}
            disabled={loading}
            onPick={(opt) => submitAnswer(4, opt.value, opt.label)}
          />
        )}

        {stage === "question_5" && (
          <ChoiceButtons
            options={[
              { value: "straight", label: "Tell me straight — no softening" },
              { value: "context", label: "Give me context before the bad news" },
            ]}
            disabled={loading}
            onPick={(opt) => submitAnswer(5, opt.value, opt.label)}
          />
        )}

        {error && (
          <div className="mt-4 text-sm text-red-600 border border-red-200 bg-red-50 rounded-lg px-3 py-2">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | undefined }) {
  return (
    <div className="flex gap-3">
      <dt className="w-28 shrink-0 text-slate-500">{label}</dt>
      <dd className="text-slate-900">{value || "—"}</dd>
    </div>
  );
}

function ChoiceButtons({
  options,
  onPick,
  disabled,
}: {
  options: { value: string; label: string }[];
  onPick: (opt: { value: string; label: string }) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onPick(opt)}
          disabled={disabled}
          className="text-left border border-slate-300 hover:border-slate-900 hover:bg-slate-50 rounded-xl px-4 py-3 disabled:opacity-50"
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

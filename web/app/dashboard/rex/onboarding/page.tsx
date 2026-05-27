"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────
type Stage =
  | "welcome"
  | "question_1" | "question_2" | "question_3"
  | "scanning"
  | "question_4" | "question_5" | "question_6"
  | "i_see_it"
  | "complete";

interface StartResp { welcome: string; state: string; question: string | null }
interface AnswerResp {
  next_prompt: string; state: string; question: string | null;
  i_see_it: string | null; complete: boolean;
}
interface Prefs {
  business_type?: string; website_url?: string; pain_point?: string;
  channel?: string; directness?: string; good_week?: string;
  scan_findings?: Record<string, number>;
  website_insights?: {
    company_name?: string; tech_stack?: string; has_blog?: boolean;
    social_links?: string[]; contact_email?: string;
  };
}

type Line = { who: "zilo" | "you" | "system"; text: string; animate?: boolean };

// ─── Typing animation ────────────────────────────────────────────────────
function useTypewriter(text: string, enabled: boolean, speedMs = 18) {
  const [shown, setShown] = useState(enabled ? "" : text);
  useEffect(() => {
    if (!enabled) { setShown(text); return; }
    setShown("");
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, speedMs);
    return () => clearInterval(id);
  }, [text, enabled, speedMs]);
  return shown;
}

function ZiloLine({ text, animate = false, onDone }: { text: string; animate?: boolean; onDone?: () => void }) {
  const shown = useTypewriter(text, animate);
  const done = shown.length >= text.length;
  useEffect(() => { if (done && onDone) onDone(); }, [done, onDone]);
  return (
    <div className="mb-7">
      <div className="text-[10px] tracking-[0.2em] font-mono text-emerald-400/70 mb-1">ZILO</div>
      <div className="text-zinc-100 whitespace-pre-line leading-relaxed text-[15px]">
        {shown}
        {animate && !done && <span className="inline-block w-2 h-4 bg-emerald-400 ml-1 animate-pulse" />}
      </div>
    </div>
  );
}

function YouLine({ text }: { text: string }) {
  return (
    <div className="mb-7">
      <div className="text-[10px] tracking-[0.2em] font-mono text-zinc-500 mb-1">YOU</div>
      <div className="text-zinc-300 leading-relaxed text-[15px]">{text}</div>
    </div>
  );
}

function SystemLine({ text }: { text: string }) {
  return (
    <div className="mb-5 font-mono text-[12px] text-zinc-500">
      <span className="text-emerald-400/60">›</span> {text}
    </div>
  );
}

// ─── Scanning theatre ────────────────────────────────────────────────────
function ScanTheatre({ url, onDone }: { url: string; onDone: () => void }) {
  const [steps, setSteps] = useState<string[]>([]);
  useEffect(() => {
    let cancelled = false;
    const seq: string[] = url
      ? [
          `connecting to ${stripUrl(url)}…`,
          "reading homepage",
          "looking for product, contact, story",
          "checking tech stack",
          "done",
        ]
      : [
          "no site to read",
          "no inbox yet either",
          "noted",
        ];
    (async () => {
      for (const s of seq) {
        if (cancelled) return;
        setSteps((prev) => [...prev, s]);
        await sleep(550);
      }
      if (!cancelled) {
        await sleep(400);
        onDone();
      }
    })();
    return () => { cancelled = true; };
  }, [url, onDone]);

  return (
    <div className="mb-7 font-mono text-[12px] text-zinc-500 space-y-1">
      {steps.map((s, i) => (
        <div key={i}>
          <span className="text-emerald-400/60">›</span> {s}
        </div>
      ))}
    </div>
  );
}

function stripUrl(u: string) {
  return u.replace(/^https?:\/\//, "").replace(/\/$/, "");
}
function sleep(ms: number) { return new Promise((r) => setTimeout(r, ms)); }

// ─── Main ────────────────────────────────────────────────────────────────
export default function ZiloOnboardingPage() {
  const [stage, setStage] = useState<Stage>("welcome");
  const [lines, setLines] = useState<Line[]>([]);
  const [pendingZilo, setPendingZilo] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [iSeeIt, setISeeIt] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [websiteUrl, setWebsiteUrl] = useState("");
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [lines, pendingZilo, iSeeIt, stage]);

  const flushPendingZilo = useCallback(() => {
    if (pendingZilo == null) return;
    setLines((l) => [...l, { who: "zilo", text: pendingZilo, animate: false }]);
    setPendingZilo(null);
  }, [pendingZilo]);

  async function begin() {
    setLoading(true); setError(null);
    try {
      const r = await api.post<StartResp>("/rex/onboarding/start", {});
      setPendingZilo(r.welcome);
      setStage("question_1");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start");
    } finally { setLoading(false); }
  }

  async function submit(qnum: number, value: string, display?: string) {
    setLoading(true); setError(null);
    try {
      // Lock the previous Zilo line so it stops animating (if still typing)
      flushPendingZilo();
      setLines((l) => [...l, { who: "you", text: (display ?? value) || "(skipped)" }]);
      setInput("");
      if (qnum === 2) setWebsiteUrl(value);

      const r = await api.post<AnswerResp>(`/rex/onboarding/answer/${qnum}`, { value });

      // Q3 just finished → start the scanning theatre before showing Q4
      if (qnum === 3) {
        setStage("scanning");
        // Hold next prompt; ScanTheatre's onDone will reveal it
        (window as unknown as { __nextZiloPrompt?: string }).__nextZiloPrompt = r.next_prompt;
        return;
      }

      if (r.i_see_it) {
        setISeeIt(r.i_see_it);
        setStage("i_see_it");
        const pr = await api.get<{ preferences: Prefs }>("/rex/onboarding/preferences");
        setPrefs(pr.preferences);
        return;
      }

      if (r.complete) {
        setPendingZilo(r.next_prompt);
        setStage("complete");
        return;
      }

      setPendingZilo(r.next_prompt);
      const nextStage = `question_${qnum + 1}` as Stage;
      setStage(nextStage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit");
    } finally { setLoading(false); }
  }

  function scanDone() {
    const w = window as unknown as { __nextZiloPrompt?: string };
    if (w.__nextZiloPrompt) {
      setPendingZilo(w.__nextZiloPrompt);
      delete w.__nextZiloPrompt;
    }
    setStage("question_4");
  }

  async function reset() {
    setLoading(true);
    try {
      await api.post("/rex/onboarding/reset", {});
      setLines([]); setPendingZilo(null); setInput(""); setISeeIt(null); setPrefs(null);
      setError(null); setWebsiteUrl(""); setStage("welcome");
    } finally { setLoading(false); }
  }

  const currentQNum =
    stage === "question_1" ? 1 : stage === "question_2" ? 2 :
    stage === "question_3" ? 3 : stage === "question_4" ? 4 :
    stage === "question_5" ? 5 : stage === "question_6" ? 6 : 0;

  const isTextQ = [1, 2, 3, 6].includes(currentQNum);
  const placeholderByQ: Record<number, string> = {
    1: "What you build. Who you sell to. Short.",
    2: "URL — or hit skip",
    3: "Be specific. Don't generalize.",
    6: "The week you sleep well.",
  };

  // What the website-insights line should say in the closing card (subtle)
  const closingFooter =
    prefs?.website_insights && (prefs.website_insights.tech_stack || ((prefs.website_insights.social_links?.length ?? 0) > 0))
      ? [
          prefs.website_insights.tech_stack && `${prefs.website_insights.tech_stack.toLowerCase()}`,
          prefs.website_insights.has_blog === false && "no blog",
          prefs.website_insights.contact_email && prefs.website_insights.contact_email,
        ].filter(Boolean).join(" · ")
      : "";

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex justify-center">
      <div className="w-full max-w-2xl px-6 py-12 flex flex-col">
        {/* Header */}
        <div className="mb-10 flex items-baseline justify-between">
          <div className="font-mono text-[11px] tracking-[0.3em] text-zinc-500">ZILO // DAY 0</div>
          <div className="font-mono text-[10px] tracking-[0.2em] text-zinc-700">
            {stage === "i_see_it" || stage === "complete" ? "—" :
             stage === "scanning" ? "SCAN" :
             currentQNum ? `${currentQNum}/6` : "—"}
          </div>
        </div>

        {/* Transcript */}
        <div ref={scrollerRef} className="flex-1 overflow-y-auto pr-1">
          {lines.map((m, i) =>
            m.who === "zilo"  ? <ZiloLine key={i} text={m.text} /> :
            m.who === "you"  ? <YouLine key={i} text={m.text} /> :
                               <SystemLine key={i} text={m.text} />
          )}

          {pendingZilo !== null && (
            <ZiloLine
              key={`pending-${lines.length}`}
              text={pendingZilo}
              animate
              onDone={() => {
                setLines((l) => [...l, { who: "zilo", text: pendingZilo }]);
                setPendingZilo(null);
              }}
            />
          )}

          {stage === "scanning" && <ScanTheatre url={websiteUrl} onDone={scanDone} />}

          {stage === "i_see_it" && iSeeIt && (
            <>
              <ZiloLine text={iSeeIt} animate />
              <div className="mt-10 border-t border-zinc-800 pt-6">
                <div className="font-mono text-[10px] tracking-[0.2em] text-zinc-600 mb-3">SAVED</div>
                <div className="font-mono text-[12px] text-zinc-500 space-y-1">
                  {prefs?.business_type && <div>· {prefs.business_type}</div>}
                  {prefs?.pain_point && <div>· {prefs.pain_point}</div>}
                  {prefs?.channel && <div>· reach via {prefs.channel}</div>}
                  {prefs?.directness && <div>· {prefs.directness === "straight" ? "straight up" : "context first"}</div>}
                  {closingFooter && <div>· {closingFooter}</div>}
                </div>
                <div className="mt-8 flex items-center gap-4">
                  <button
                    onClick={reset}
                    className="font-mono text-[12px] text-zinc-500 hover:text-emerald-400 tracking-wider"
                  >
                    start over
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Input zone */}
        {stage === "welcome" && (
          <div className="mt-2">
            <ZiloLine text="Before I start — give me a minute. Six questions. I'm not building a profile. I'm trying to figure out what you actually need from me." />
            <button
              onClick={begin}
              disabled={loading}
              className="font-mono text-[12px] tracking-[0.2em] text-emerald-400 hover:text-emerald-300 border border-emerald-400/30 hover:border-emerald-400 px-5 py-3 disabled:opacity-50"
            >
              {loading ? "…" : "BEGIN ›"}
            </button>
          </div>
        )}

        {isTextQ && pendingZilo === null && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (loading) return;
              submit(currentQNum, input.trim());
            }}
            className="mt-4 flex gap-2"
          >
            <input
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={placeholderByQ[currentQNum]}
              className="flex-1 bg-transparent border-b border-zinc-800 focus:border-emerald-400 px-1 py-3 text-zinc-100 placeholder-zinc-600 focus:outline-none transition-colors"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || (currentQNum !== 2 && !input.trim())}
              className="font-mono text-[12px] tracking-[0.2em] text-emerald-400 hover:text-emerald-300 disabled:text-zinc-700 px-3"
            >
              {currentQNum === 2 && !input.trim() ? "SKIP ›" : "SEND ›"}
            </button>
          </form>
        )}

        {stage === "question_4" && pendingZilo === null && (
          <ChoiceList
            options={[
              { value: "whatsapp", label: "whatsapp" },
              { value: "telegram", label: "telegram" },
              { value: "email", label: "email" },
              { value: "in_app", label: "inside the app" },
            ]}
            disabled={loading}
            onPick={(o) => submit(4, o.value, o.label)}
          />
        )}

        {stage === "question_5" && pendingZilo === null && (
          <ChoiceList
            options={[
              { value: "straight", label: "straight up. no softening." },
              { value: "context", label: "set the table first." },
            ]}
            disabled={loading}
            onPick={(o) => submit(5, o.value, o.label)}
          />
        )}

        {error && (
          <div className="mt-4 font-mono text-[12px] text-red-400 border border-red-900/50 bg-red-950/30 px-3 py-2">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

function ChoiceList({
  options, onPick, disabled,
}: {
  options: { value: string; label: string }[];
  onPick: (o: { value: string; label: string }) => void;
  disabled?: boolean;
}) {
  return (
    <div className="mt-4 flex flex-col gap-1">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onPick(o)}
          disabled={disabled}
          className="text-left font-mono text-[13px] text-zinc-400 hover:text-emerald-400 border-l-2 border-zinc-800 hover:border-emerald-400 pl-4 py-2 disabled:opacity-50 transition-colors"
        >
          › {o.label}
        </button>
      ))}
    </div>
  );
}

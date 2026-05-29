"use client";

import { useState, useRef } from "react";
import { api } from "@/lib/api";
import { Mic, Square, Loader2, Send, FileText, AlertCircle, CheckCircle } from "lucide-react";
import { useRouter } from "next/navigation";

type RecordState = "idle" | "recording" | "transcribing" | "done" | "error";

export default function VoicePage() {
  const [state, setState] = useState<RecordState>("idle");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(0);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const router = useRouter();

  async function startRecording() {
    setError("");
    setTranscript("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => { stream.getTracks().forEach(t => t.stop()); processAudio(); };
      mr.start(100);
      mediaRef.current = mr;
      setState("recording");
      setSeconds(0);
      timerRef.current = setInterval(() => setSeconds(s => s + 1), 1000);
    } catch {
      setError("Microphone access denied. Please allow microphone access.");
      setState("error");
    }
  }

  function stopRecording() {
    if (timerRef.current) clearInterval(timerRef.current);
    mediaRef.current?.stop();
    setState("transcribing");
  }

  async function processAudio() {
    try {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      const arrayBuffer = await blob.arrayBuffer();
      const b64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
      const res = await api.post<{ text: string }>("/growth/voice/transcribe", {
        audio_b64: b64,
        mime_type: "audio/webm",
      });
      setTranscript(res.text || "");
      setState("done");
    } catch {
      setError("Transcription failed. Please try again.");
      setState("error");
    }
  }

  function sendToChat() {
    if (!transcript) return;
    const encoded = encodeURIComponent(transcript);
    router.push(`/dashboard/assistant?prefill=${encoded}`);
  }

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Mic size={22} className="text-rose-500" /> Voice to Document
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Record a voice note describing what you need — the AI will transcribe it and generate a full document or SOW.
        </p>
      </div>

      {/* How it works */}
      <div className="bg-rose-50 border border-rose-100 rounded-xl p-4">
        <p className="text-xs font-semibold text-rose-700 uppercase tracking-wide mb-2">How it works</p>
        <ol className="space-y-1 text-sm text-rose-800">
          <li>1. Hit <strong>Record</strong> and describe what you need in plain speech</li>
          <li>2. AI transcribes your voice note</li>
          <li>3. Review and send to Zilo Chat to generate the full document</li>
        </ol>
        <p className="text-xs text-rose-600 mt-2 italic">
          Example: "I met John from BlueLine, we agreed on a $5K SOW for a website redesign, delivery in 3 weeks, 50% upfront…"
        </p>
      </div>

      {/* Recorder */}
      <div className="bg-white rounded-xl border border-slate-200 p-8 flex flex-col items-center gap-6">
        {state === "idle" && (
          <button onClick={startRecording}
            className="w-20 h-20 rounded-full bg-rose-500 hover:bg-rose-600 text-white flex items-center justify-center shadow-lg hover:shadow-xl transition-all">
            <Mic size={32} />
          </button>
        )}
        {state === "recording" && (
          <>
            <div className="relative">
              <div className="w-20 h-20 rounded-full bg-rose-500 animate-pulse flex items-center justify-center">
                <div className="w-20 h-20 rounded-full bg-rose-400 animate-ping absolute" />
                <Mic size={32} className="text-white relative z-10" />
              </div>
            </div>
            <p className="text-2xl font-mono font-bold text-slate-800">{fmt(seconds)}</p>
            <p className="text-sm text-slate-500">Recording… speak clearly</p>
            <button onClick={stopRecording}
              className="flex items-center gap-2 px-6 py-2.5 bg-brand-dark text-white rounded-lg hover:bg-brand font-medium transition-colors">
              <Square size={14} fill="white" /> Stop Recording
            </button>
          </>
        )}
        {state === "transcribing" && (
          <div className="flex flex-col items-center gap-3">
            <Loader2 size={40} className="text-rose-400 animate-spin" />
            <p className="text-sm text-slate-600">Transcribing your voice note…</p>
          </div>
        )}
        {state === "error" && (
          <div className="flex flex-col items-center gap-3 text-center">
            <AlertCircle size={40} className="text-rose-400" />
            <p className="text-sm text-rose-600">{error}</p>
            <button onClick={() => setState("idle")}
              className="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50">
              Try Again
            </button>
          </div>
        )}
        {state === "done" && (
          <div className="w-full space-y-3">
            <div className="flex items-center gap-2 text-emerald-600">
              <CheckCircle size={16} /> <span className="text-sm font-medium">Transcription complete</span>
            </div>
            <textarea
              value={transcript}
              onChange={e => setTranscript(e.target.value)}
              rows={5}
              className="w-full text-sm border border-slate-200 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-brand/30 resize-none"
            />
            <div className="flex gap-2">
              <button onClick={sendToChat}
                className="flex items-center gap-2 px-4 py-2 bg-brand-dark text-white text-sm rounded-lg hover:bg-brand font-medium">
                <Send size={13} /> Send to Zilo Chat
              </button>
              <button onClick={() => setState("idle")}
                className="px-4 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                Record Again
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

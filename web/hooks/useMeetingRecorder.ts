import { useState, useRef, useCallback } from "react";
import { smartNotesApi, API_BASE } from "@/lib/api";
import { getToken } from "@/lib/auth";

// Inline AudioWorklet: extracts 16-bit PCM from the mixed audio stream.
// Runs in its own thread — no GC pauses on the main thread.
const WORKLET_SRC = `
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0]?.[0];
    if (ch?.length) {
      const i16 = new Int16Array(ch.length);
      for (let i = 0; i < ch.length; i++) {
        i16[i] = Math.max(-32768, Math.min(32767, Math.round(ch[i] * 32767)));
      }
      this.port.postMessage(i16.buffer, [i16.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
`;

export interface MeetingInfo {
  id?: string;
  title: string;
  start?: string;
  end?: string;
  meet_url?: string;
  attendees?: string[];
  keyterms?: string[]; // custom words/names to bias Deepgram toward
}

export type RecordState = "idle" | "recording" | "tagging" | "processing" | "done" | "error";

export interface SpeakerSegment {
  speaker: string; // "0", "1", "2" — numeric string from Deepgram
  text: string;
  start: number;
  end: number;
}

interface DgWord {
  word: string;
  punctuated_word?: string;
  speaker?: number;
  start: number;
  end: number;
}

export function useMeetingRecorder() {
  const [recordState,    setRecordState]    = useState<RecordState>("idle");
  const [elapsed,        setElapsed]        = useState("0:00");
  const [liveTranscript, setLiveTranscript] = useState("");
  const [interimText,    setInterimText]    = useState(""); // words in flight (not yet final)
  const [statusMsg,      setStatusMsg]      = useState(""); // "Connecting…" etc.
  const [segments,       setSegments]       = useState<SpeakerSegment[]>([]);
  const [speakerTags,    setSpeakerTags]    = useState<Record<string, string>>({});
  const [error,          setError]          = useState("");
  const [savedNote,      setSavedNote]      = useState<Record<string, unknown> | null>(null);

  // Media / WS refs
  const wsRef           = useRef<WebSocket | null>(null);
  const audioCtxRef     = useRef<AudioContext | null>(null);
  const displayStreamRef= useRef<MediaStream | null>(null);
  const micStreamRef    = useRef<MediaStream | null>(null);
  const workletNodeRef  = useRef<AudioWorkletNode | null>(null);

  // Accumulation refs
  const startTimeRef    = useRef<number>(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const segmentsRef     = useRef<SpeakerSegment[]>([]);
  const transcriptRef   = useRef<string>("");   // confirmed final text only
  const interimAccRef   = useRef<string>("");   // running accumulation of all interim words
  const meetingRef      = useRef<MeetingInfo | null>(null);

  // ── Cleanup ────────────────────────────────────────────────────────────────

  const cleanupMedia = useCallback(() => {
    clearInterval(elapsedTimerRef.current!);
    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    displayStreamRef.current?.getTracks().forEach(t => t.stop());
    displayStreamRef.current = null;
    micStreamRef.current?.getTracks().forEach(t => t.stop());
    micStreamRef.current = null;
  }, []);

  // ── Note generation ────────────────────────────────────────────────────────

  const doGenerate = useCallback(async (
    transcript: string,
    utterances?: { speaker: string; text: string }[],
  ): Promise<Record<string, unknown> | null> => {
    const m = meetingRef.current;
    const title = m?.title || `Recording ${new Date().toLocaleDateString()}`;

    // Nothing to send — recording was too short or silent
    const hasContent = (utterances?.length ?? 0) > 0 || transcript.trim().length > 0;
    if (!hasContent) {
      setError("No speech detected — try recording for longer or speak closer to the mic.");
      setRecordState("error");
      return null;
    }

    setRecordState("processing");
    try {
      const notes = await smartNotesApi.generate({
        ...(utterances?.length ? { utterances } : { transcript }),
        title,
        meeting_start: m?.start,
        meeting_end:   m?.end,
        attendees:     m?.attendees,
      });
      const savedTranscript = utterances?.length
        ? utterances.map(u => `${u.speaker}: ${u.text}`).join("\n")
        : transcript;
      const aiCleanedTranscript = (notes as Record<string, unknown>).cleaned_transcript as string;
      const saved = await smartNotesApi.save({
        title,
        meeting_start:         m?.start,
        meeting_end:           m?.end,
        meeting_url:           m?.meet_url,
        attendees:             m?.attendees,
        transcript:            aiCleanedTranscript || savedTranscript,
        summary:               (notes as Record<string, unknown>).summary as string ?? "",
        action_items:          (notes as Record<string, unknown>).action_items as string[] ?? [],
        raw_calendar_event_id: m?.id,
      });
      setSavedNote(saved as Record<string, unknown>);
      setRecordState("done");
      return saved as Record<string, unknown>;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate notes.");
      setRecordState("error");
      return null;
    }
  }, []);

  const generateWithSpeakers = useCallback(async () => {
    const named = segmentsRef.current.map(s => ({
      speaker: speakerTags[s.speaker] || `Speaker ${s.speaker}`,
      text: s.text,
    }));
    return doGenerate("", named);
  }, [speakerTags, doGenerate]);

  const generateWithPlainTranscript = useCallback(async () => {
    return doGenerate(transcriptRef.current);
  }, [doGenerate]);

  // ── After recording stops ──────────────────────────────────────────────────

  const afterStop = useCallback(() => {
    cleanupMedia();
    const segs = segmentsRef.current;
    if (segs.length > 0) {
      const uniqueSpeakers = [...new Set(segs.map(s => s.speaker))];
      const m = meetingRef.current;
      const names = (m?.attendees ?? []).map(e => e.split("@")[0]);
      const tags: Record<string, string> = {};
      uniqueSpeakers.forEach((spk, i) => { tags[spk] = i === 0 ? "You" : (names[i] ?? ""); });
      setSpeakerTags(tags);
      setRecordState("tagging");
    } else {
      // Use confirmed transcript, falling back to accumulated interim text
      const text = transcriptRef.current.trim() || interimAccRef.current.trim();
      doGenerate(text);
    }
  }, [cleanupMedia, doGenerate]);

  // ── Deepgram message handler ───────────────────────────────────────────────

  const onDgMessage = useCallback((raw: string) => {
    let msg: Record<string, unknown>;
    try { msg = JSON.parse(raw); } catch { return; }

    if (msg.type === "error") {
      setError(`Deepgram: ${String(msg.message ?? "streaming error")}`);
      return;
    }
    if (msg.type !== "Results") return;

    const channel = msg.channel as { alternatives?: Array<{ transcript?: string; words?: DgWord[] }> } | undefined;
    const alt = channel?.alternatives?.[0];
    const words = alt?.words;

    // Show interim (not-yet-final) text immediately as a preview
    if (!msg.is_final) {
      const interim = alt?.transcript ?? "";
      if (interim.trim()) {
        setInterimText(interim);
        // Keep a running accumulation as fallback in case recording is stopped
        // before any is_final result comes through
        interimAccRef.current = (interimAccRef.current + " " + interim).trim();
      }
      return;
    }

    // is_final — clear interim preview, commit to segments
    setInterimText("");
    if (!words?.length) return;

    // Group words into per-speaker segments
    const newSegs: SpeakerSegment[] = [];
    let cur: SpeakerSegment | null = null;
    for (const w of words) {
      const spk = String(w.speaker ?? 0);
      const text = w.punctuated_word ?? w.word;
      if (!cur || cur.speaker !== spk) {
        if (cur) newSegs.push(cur);
        cur = { speaker: spk, text, start: w.start, end: w.end };
      } else {
        cur.text += ` ${text}`;
        cur.end = w.end;
      }
    }
    if (cur) newSegs.push(cur);

    // Merge into accumulated list (merge with last segment if same speaker)
    const all = [...segmentsRef.current];
    for (const s of newSegs) {
      const last = all[all.length - 1];
      if (last && last.speaker === s.speaker) {
        last.text += ` ${s.text}`;
        last.end = s.end;
      } else {
        all.push({ ...s });
      }
    }
    segmentsRef.current = all;
    setSegments([...all]);

    // Build readable live transcript
    const display = all.map(s => `[Speaker ${s.speaker}] ${s.text}`).join("\n");
    transcriptRef.current = display;
    setLiveTranscript(display);
  }, []);

  // ── Start recording ────────────────────────────────────────────────────────

  const startRecording = useCallback(async (meeting?: MeetingInfo & { recordMicOnly?: boolean; speakerMode?: boolean }) => {
    if (meeting) meetingRef.current = meeting;
    setError(""); setLiveTranscript(""); setInterimText(""); setSegments([]); setSavedNote(null); setStatusMsg("");
    segmentsRef.current = []; transcriptRef.current = ""; interimAccRef.current = "";

    const micOnly = meeting?.recordMicOnly ?? false;
    const speakerMode = meeting?.speakerMode ?? false;

    try {
      let displayStream: MediaStream | null = null;
      if (!micOnly) {
        try {
          // Capture system audio (tab) + mic
          displayStream = await navigator.mediaDevices.getDisplayMedia({ audio: true, video: true });
          displayStreamRef.current = displayStream;
          displayStream.getVideoTracks().forEach(t => t.stop()); // video not needed
        } catch (e) {
          console.warn("[MeetingRecorder] getDisplayMedia failed or was cancelled. Falling back to Mic only mode.", e);
        }
      }

      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: { 
          echoCancellation: !speakerMode, 
          noiseSuppression: !speakerMode, 
          autoGainControl: true 
        },
      });
      micStreamRef.current = micStream;

      // 16 kHz AudioContext — browser resamples the 48 kHz streams automatically
      const ctx = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = ctx;

      // Load PCM extractor worklet via Blob URL (no separate file needed)
      const blobUrl = URL.createObjectURL(new Blob([WORKLET_SRC], { type: "application/javascript" }));
      await ctx.audioWorklet.addModule(blobUrl);
      URL.revokeObjectURL(blobUrl);

      // Mix display + mic into a single destination
      const dest = ctx.createMediaStreamDestination();
      if (displayStream) {
        const dispTracks = displayStream.getAudioTracks();
        if (dispTracks.length > 0) ctx.createMediaStreamSource(new MediaStream(dispTracks)).connect(dest);
      }
      ctx.createMediaStreamSource(micStream).connect(dest);

      // Connect mixed stream → PCM worklet
      const worklet = new AudioWorkletNode(ctx, "pcm-processor");
      workletNodeRef.current = worklet;
      ctx.createMediaStreamSource(dest.stream).connect(worklet);

      // Open WebSocket to backend Deepgram proxy
      const wsBase = API_BASE.replace(/^http/, "ws");
      const token = getToken() ?? "";
      const keyterms = meetingRef.current?.keyterms ?? [];
      const keytermsParams = keyterms
        .filter(t => t.trim())
        .map(t => `&keyterms=${encodeURIComponent(t.trim())}`)
        .join("");
      const ws = new WebSocket(
        `${wsBase}/smart-notes/stream?token=${encodeURIComponent(token)}${keytermsParams}`
      );
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      setStatusMsg("Connecting to Deepgram…");

      ws.onopen = () => {
        setStatusMsg(""); // connected — clear status
        // Only forward PCM once the WS is open
        worklet.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
          if (ws.readyState === WebSocket.OPEN) ws.send(e.data);
        };
      };

      ws.onmessage = e => { if (typeof e.data === "string") onDgMessage(e.data); };
      ws.onerror   = () => setError("WebSocket error — check that DEEPGRAM_API_KEY is set in backend/.env");
      ws.onclose   = () => { /* handled by stopRecording */ };

      // Start elapsed timer
      setRecordState("recording");
      startTimeRef.current = Date.now();
      elapsedTimerRef.current = setInterval(() => {
        const s = Math.floor((Date.now() - startTimeRef.current) / 1000);
        setElapsed(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
      }, 1_000);

    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg.includes("Permission") ? "Permission denied — allow mic & screen share." : msg);
      setRecordState("error");
      cleanupMedia();
    }
  }, [onDgMessage, cleanupMedia]);

  // ── Stop recording ─────────────────────────────────────────────────────────

  const stopRecording = useCallback(() => {
    clearInterval(elapsedTimerRef.current!);
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.close(1000, "done");
    wsRef.current = null;
    afterStop();
  }, [afterStop]);

  // ── Reset ──────────────────────────────────────────────────────────────────

  const reset = useCallback(() => {
    clearInterval(elapsedTimerRef.current!);
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    cleanupMedia();
    setRecordState("idle"); setElapsed("0:00"); setLiveTranscript("");
    setInterimText(""); setStatusMsg("");
    setSegments([]); setSpeakerTags({}); setError(""); setSavedNote(null);
    segmentsRef.current = []; transcriptRef.current = ""; interimAccRef.current = "";
    meetingRef.current = null;
  }, [cleanupMedia]);

  return {
    recordState, elapsed, liveTranscript, interimText, statusMsg, segments,
    speakerTags, setSpeakerTags,
    error, savedNote,
    startRecording, stopRecording,
    generateWithSpeakers, generateWithPlainTranscript,
    reset,
  };
}

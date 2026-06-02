"use client";

/**
 * MeetingOverlay — floating card that auto-appears 2 min before a calendar meeting.
 * Recording: getDisplayMedia (tab audio) + getUserMedia (mic) mixed via AudioContext.
 * Transcription: Deepgram Nova-2 streaming — real-time words with speaker labels.
 * After stop: speaker tagging UI appears immediately (no post-processing wait).
 */

import { useEffect, useRef, useState } from "react";
import { smartNotesApi } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useGlobalMeetingRecorder } from "@/contexts/MeetingRecorderContext";

interface Meeting {
  id: string;
  title: string;
  start: string;
  end: string;
  meet_url: string;
  attendees: string[];
  description: string;
}

const POLL_MS     = 60_000;
const SHOW_BEFORE = 2 * 60 * 1000;

export default function MeetingOverlay() {
  const router = useRouter();
  const rec = useGlobalMeetingRecorder();

  const [meeting,      setMeeting]      = useState<Meeting | null>(null);
  const [isUpcoming,   setIsUpcoming]   = useState(false);
  const [countdown,    setCountdown]    = useState("");
  const [expanded,     setExpanded]     = useState(false);
  const [keytermsInput,setKeytermsInput]= useState("");
  const [recordMicOnly,setRecordMicOnly]= useState(false); // Default to false (screen audio capture) for active Zoom/Meet calendar invitations

  const activeMeetingRef = useRef<Meeting | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const dismissedMeetingsRef = useRef<Set<string>>(new Set());

  // Auto-scroll live transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [rec.liveTranscript]);

  // Calendar polling — stop when actively recording
  const checkUpcoming = async () => {
    if (rec.recordState !== "idle") return;
    try {
      const res = await smartNotesApi.upcoming();
      if (!res.connected) return;
      const now = Date.now();
      for (const raw of res.meetings) {
        const m = raw as unknown as Meeting;
        if (!m.meet_url || dismissedMeetingsRef.current.has(m.id)) continue;
        const startMs = new Date(m.start).getTime();
        const endMs   = new Date(m.end).getTime();
        if (now > endMs) continue;
        if (startMs - now <= SHOW_BEFORE && now < endMs) {
          if (activeMeetingRef.current?.id !== m.id) {
            activeMeetingRef.current = m;
            setMeeting(m);
            setIsUpcoming(true);
            // Pre-fill keyterms with attendee first names
            const names = m.attendees.map(e => e.split("@")[0]).filter(Boolean);
            if (names.length) setKeytermsInput(names.join(", "));
          }
          return;
        }
      }
    } catch { /* silent */ }
  };

  useEffect(() => {
    checkUpcoming();
    const iv = setInterval(checkUpcoming, POLL_MS);
    return () => clearInterval(iv);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rec.recordState]);

  // Countdown to meeting start
  useEffect(() => {
    if (!isUpcoming || !meeting) return;
    const update = () => {
      const diff = new Date(meeting.start).getTime() - Date.now();
      if (diff <= 0) { setCountdown("Starting now"); return; }
      setCountdown(`${Math.floor(diff / 60_000)}:${String(Math.floor((diff % 60_000) / 1000)).padStart(2, "0")}`);
    };
    update();
    const iv = setInterval(update, 1_000);
    return () => clearInterval(iv);
  }, [isUpcoming, meeting]);

  const handleJoinRecord = async () => {
    if (!meeting) return;
    if (meeting.meet_url) window.open(meeting.meet_url, "_blank");
    setIsUpcoming(false);
    setExpanded(true);
    const keyterms = keytermsInput.split(/[,\n]+/).map(s => s.trim()).filter(Boolean);
    await rec.startRecording({
      id: meeting.id, title: meeting.title,
      start: meeting.start, end: meeting.end,
      meet_url: meeting.meet_url, attendees: meeting.attendees,
      keyterms,
      recordMicOnly,
    });
  };

  const dismiss = () => {
    if (meeting) {
      dismissedMeetingsRef.current.add(meeting.id);
    }
    rec.reset();
    setMeeting(null); setIsUpcoming(false);
    activeMeetingRef.current = null;
    setCountdown(""); setExpanded(false);
  };

  const isVisible = isUpcoming || rec.recordState !== "idle";
  if (!isVisible) return null;

  const currentMeeting = meeting || rec.activeMeeting || (rec.recordState !== "idle" ? {
    id: "manual",
    title: "Manual Recording",
    start: new Date().toISOString(),
    end: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
    meet_url: "",
    attendees: [],
    description: "",
  } : null);

  if (!currentMeeting) return null;

  const { 
    recordState, elapsed, liveTranscript, interimText, statusMsg, segments, speakerTags, setSpeakerTags, error,
    customAttendees, setCustomAttendees 
  } = rec;
  const isRecording = recordState === "recording";
  const speakerList = Object.keys(speakerTags);
  const attendeeOptions = [
    "You",
    ...(currentMeeting.attendees ?? []).map(e => e.split("@")[0]),
    ...(customAttendees ?? [])
  ].filter((v, i, self) => v && self.indexOf(v) === i);

  return (
    <div className={`fixed bottom-6 right-6 z-[9999] rounded-2xl shadow-2xl border border-gray-200 bg-white overflow-hidden transition-all duration-200 ${
      (expanded && isRecording) || recordState === "tagging" ? "w-96" : "w-80"
    }`}>
      {/* Header */}
      <div className={`px-4 py-3 flex items-center justify-between ${isRecording ? "bg-red-600" : "bg-brand-dark"}`}>
        <div className="flex items-center gap-2">
          {isRecording && <span className="w-2 h-2 rounded-full bg-white animate-pulse" />}
          <span className="text-white text-sm font-semibold">
            {isUpcoming              ? "Upcoming meeting" :
             isRecording             ? `Recording · ${elapsed}` :
             recordState === "tagging"    ? `Tag speakers (${speakerList.length} found)` :
             recordState === "processing" ? "Generating notes…" :
             recordState === "done"       ? "Notes ready" :
             recordState === "error"      ? "Error" : "Meeting"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {isRecording && (
            <button
              onClick={() => setExpanded(v => !v)}
              className="text-white/70 hover:text-white text-xs border border-white/30 rounded px-1.5 py-0.5"
            >
              {expanded ? "−" : "live"}
            </button>
          )}
          <button onClick={dismiss} className="text-white/80 hover:text-white text-lg leading-none">×</button>
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-3">
        <p className="text-sm font-medium text-gray-900 truncate">{currentMeeting.title}</p>

        {/* Live transcript — real-time Deepgram words */}
        {isRecording && expanded && (
          <div className="bg-gray-50 rounded-lg p-2.5 h-40 overflow-y-auto">
            {liveTranscript || interimText ? (
              <>
                <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">{liveTranscript}</p>
                {interimText && <p className="text-xs text-gray-400 italic">{interimText}</p>}
                <div ref={transcriptEndRef} />
              </>
            ) : (
              <p className="text-xs text-gray-400 italic">
                {statusMsg || "Listening… words appear as you speak."}
              </p>
            )}
          </div>
        )}

        {/* Upcoming — show countdown + Join & Record button */}
        {isUpcoming && (
          <>
            <p className="text-xs text-gray-500">Starts in <span className="font-semibold text-brand-dark">{countdown}</span></p>
            {meeting.attendees.length > 0 && (
              <p className="text-xs text-gray-400 truncate">
                With: {meeting.attendees.slice(0, 3).join(", ")}
                {meeting.attendees.length > 3 && ` +${meeting.attendees.length - 3}`}
              </p>
            )}
            <div>
              <p className="text-[10px] text-gray-400 mb-1">Names / terms to recognise:</p>
              <input
                type="text"
                value={keytermsInput}
                onChange={e => setKeytermsInput(e.target.value)}
                placeholder="e.g. Zilo, Samuel, Mweni"
                className="w-full text-xs border border-gray-200 rounded-md px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-dark/40 mb-2"
              />
              <label className="flex items-center gap-1.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={recordMicOnly}
                  onChange={e => setRecordMicOnly(e.target.checked)}
                  className="rounded border-gray-300 text-brand-dark focus:ring-brand-dark/40 w-3 h-3"
                />
                <span className="text-[10px] text-gray-500 font-medium">Record MY microphone only (does not capture participants)</span>
              </label>
            </div>
            <button
              onClick={handleJoinRecord}
              className="w-full py-2 rounded-lg bg-brand-dark hover:opacity-90 text-white text-sm font-semibold transition-colors"
            >
              Join &amp; Record
            </button>
            <p className="text-[10px] text-gray-400 text-center">
              {recordMicOnly 
                ? "⚠️ Captures your microphone ONLY — will NOT record other participants" 
                : "Captures your mic AND the meeting audio (choose 'Share tab/system audio')"
              }
            </p>
          </>
        )}

        {/* Recording — stop button */}
        {isRecording && (
          <button
            onClick={rec.stopRecording}
            className="w-full py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-semibold transition-colors"
          >
            Stop &amp; Tag Speakers
          </button>
        )}

        {/* Speaker tagging — immediate after stop (no AssemblyAI wait) */}
        {recordState === "tagging" && (
          <div className="space-y-3 max-h-[350px] overflow-y-auto pr-1">
            <p className="text-xs text-gray-400">Assign names to each voice — then generate your notes.</p>

            {/* Pull Attendees / Pasted Link block */}
            <div className="bg-gray-50 rounded-lg p-2 border border-gray-200/60 space-y-1.5">
              <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block">Pull Attendees from Meeting Link</label>
              <input
                type="text"
                placeholder="Paste link or names (e.g. Alice, Bob)..."
                className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-brand-dark/40 bg-white"
                onKeyDown={async (e) => {
                  if (e.key === "Enter") {
                    const val = (e.target as HTMLInputElement).value.trim();
                    if (!val) return;
                    if (val.includes("http") || val.includes("meet.") || val.includes("zoom")) {
                      try {
                        const res = await smartNotesApi.upcoming();
                        const matched = res.meetings.find(m => m.meet_url && val.includes(String(m.meet_url)));
                        if (matched && matched.attendees) {
                          const list = matched.attendees.map((email: string) => email.split("@")[0]);
                          setCustomAttendees(prev => [...new Set([...prev, ...list])]);
                          (e.target as HTMLInputElement).value = "";
                        } else {
                          alert("Meeting link not found in calendar. Paste names directly instead (e.g. Alice, Bob).");
                        }
                      } catch {
                        alert("Failed to query calendar meetings.");
                      }
                    } else {
                      const list = val.split(/[,\n;]+/).map(s => s.trim()).filter(Boolean);
                      if (list.length) {
                        setCustomAttendees(prev => [...new Set([...prev, ...list])]);
                        (e.target as HTMLInputElement).value = "";
                      }
                    }
                  }
                }}
              />
              <p className="text-[9px] text-gray-400 leading-none">Press Enter to pull calendar attendees or split names by commas</p>
            </div>

            <div className="space-y-3 pt-1">
              {speakerList.map(spk => {
                const preview = segments.find(s => s.speaker === spk)?.text ?? "";
                return (
                  <div key={spk} className="space-y-1.5 bg-white p-2 border border-gray-100 rounded-lg shadow-sm">
                    <div className="flex items-center gap-1.5">
                      <div className="w-5 h-5 rounded-full bg-brand-dark flex items-center justify-center text-[10px] font-bold text-white shrink-0">
                        {spk}
                      </div>
                      <p className="text-[10px] text-gray-400 italic truncate flex-1">&ldquo;{preview}&rdquo;</p>
                    </div>
                    <input
                      type="text"
                      list={`spk-${spk}-list`}
                      value={speakerTags[spk] ?? ""}
                      onChange={e => setSpeakerTags(prev => ({ ...prev, [spk]: e.target.value }))}
                      placeholder="Enter name"
                      className="w-full text-xs border border-gray-200 rounded-md px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-dark/40"
                    />
                    <datalist id={`spk-${spk}-list`}>
                      {attendeeOptions.map(opt => <option key={opt} value={opt} />)}
                    </datalist>

                    {/* Suggestion Badges */}
                    {attendeeOptions.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-0.5">
                        {attendeeOptions.map(opt => (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => setSpeakerTags(prev => ({ ...prev, [spk]: opt }))}
                            className={`text-[9px] px-1.5 py-0.5 rounded-full border transition-colors ${
                              speakerTags[spk] === opt
                                ? "bg-brand-dark border-brand-dark text-white font-medium"
                                : "bg-gray-50 hover:bg-gray-100 border-gray-200 text-gray-500"
                            }`}
                          >
                            {opt}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex gap-2 pt-2">
              <button
                onClick={rec.generateWithSpeakers}
                className="flex-1 py-2 rounded-lg bg-brand-dark hover:opacity-90 text-white text-sm font-semibold transition-colors"
              >
                Generate with Speakers
              </button>
              <button
                onClick={rec.generateWithPlainTranscript}
                className="px-3 py-2 rounded-lg border border-gray-200 text-gray-500 text-xs hover:bg-gray-50 transition-colors"
              >
                Skip
              </button>
            </div>
          </div>
        )}

        {/* Processing */}
        {recordState === "processing" && (
          <div className="flex items-center justify-center gap-2 py-2">
            <div className="w-4 h-4 border-2 border-brand-dark border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-gray-500">Building structured notes…</p>
          </div>
        )}

        {/* Done */}
        {recordState === "done" && (
          <>
            <p className="text-xs text-green-700">Notes saved.</p>
            {rec.savedNote && (
              <button
                onClick={() => { router.push("/dashboard/smart-notes"); dismiss(); }}
                className="w-full py-2 rounded-lg bg-brand-dark hover:opacity-90 text-white text-sm font-semibold transition-colors"
              >
                View Notes
              </button>
            )}
          </>
        )}

        {/* Error */}
        {recordState === "error" && (
          <p className="text-xs text-red-600">{error || "Something went wrong."}</p>
        )}
      </div>
    </div>
  );
}

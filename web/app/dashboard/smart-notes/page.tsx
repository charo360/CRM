"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { smartNotesApi } from "@/lib/api";
import { useMeetingRecorder } from "@/hooks/useMeetingRecorder";
import { cn } from "@/lib/utils";

interface Note {
  id: string;
  title: string;
  meeting_start: string | null;
  meeting_end: string | null;
  summary: string;
  action_items: string[];
  attendees: string[];
  created_at: string;
}

interface NoteDetail extends Note {
  transcript: string;
  key_points?: string[];
  decisions?: string[];
  next_steps?: string;
  meeting_url?: string;
}

export default function SmartNotesPage() {
  const [notes,         setNotes]         = useState<Note[]>([]);
  const [loading,       setLoading]       = useState(true);
  const [selected,      setSelected]      = useState<NoteDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deleting,      setDeleting]      = useState<string | null>(null);
  const [keytermsInput, setKeytermsInput] = useState(""); // e.g. "Zilo, Samuel, Mweni"
  const [recordMicOnly, setRecordMicOnly] = useState(true); // Default to microphone-only for seamless recordings
  const [editingTitle,  setEditingTitle]  = useState(false);
  const [titleValue,    setTitleValue]    = useState("");
  const [renaming,      setRenaming]      = useState(false);

  const rec = useMeetingRecorder();
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll live transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [rec.liveTranscript]);

  // Add saved note to list when done
  useEffect(() => {
    if (rec.recordState === "done" && rec.savedNote) {
      const n = rec.savedNote as unknown as Note;
      setNotes(prev => [n, ...prev.filter(x => x.id !== n.id)]);
      const detail = rec.savedNote as unknown as NoteDetail;
      setSelected(detail);
      setTitleValue(detail.title);
      setEditingTitle(false);
    }
  }, [rec.recordState, rec.savedNote]);

  useEffect(() => { loadNotes(); }, []);

  const loadNotes = async () => {
    setLoading(true);
    try {
      const res = await smartNotesApi.list();
      setNotes((res.notes ?? []) as unknown as Note[]);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const openNote = async (id: string) => {
    setDetailLoading(true);
    setEditingTitle(false);
    try {
      const doc = await smartNotesApi.get(id) as unknown as NoteDetail;
      setSelected(doc);
      setTitleValue(doc.title);
    } catch { /* ignore */ }
    finally { setDetailLoading(false); }
  };

  const saveTitle = async () => {
    if (!selected || !titleValue.trim() || titleValue.trim() === selected.title) {
      setEditingTitle(false);
      return;
    }
    setRenaming(true);
    try {
      const updated = await smartNotesApi.update(selected.id, { title: titleValue.trim() });
      const upDoc = updated as unknown as NoteDetail;
      setSelected(upDoc);
      setTitleValue(upDoc.title);
      setNotes(prev => prev.map(n => n.id === upDoc.id ? { ...n, title: upDoc.title } : n));
    } catch {
      // ignore
    } finally {
      setRenaming(false);
      setEditingTitle(false);
    }
  };

  const deleteNote = async (id: string) => {
    setDeleting(id);
    try {
      await smartNotesApi.delete(id);
      setNotes(prev => prev.filter(n => n.id !== id));
      if (selected?.id === id) setSelected(null);
    } catch { /* ignore */ }
    finally { setDeleting(null); }
  };

  const fmtDate = (iso: string | null) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  };

  const fmtDuration = (start: string | null, end: string | null) => {
    if (!start || !end) return null;
    const mins = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60_000);
    return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
  };

  const { recordState, elapsed, liveTranscript, interimText, statusMsg, segments, speakerTags, setSpeakerTags, error: recError } = rec;

  const showDetailPanel =
    detailLoading ||
    recordState === "recording" ||
    recordState === "tagging" ||
    recordState === "processing" ||
    selected !== null;

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] min-h-0 overflow-hidden bg-gray-50 md:min-h-screen md:h-full">
      {/* ── Left panel ── */}
      <div
        className={cn(
          "flex w-full max-w-sm flex-col border-r border-gray-200 bg-white",
          showDetailPanel ? "hidden md:flex" : "flex"
        )}
      >
        <div className="border-b border-gray-100 px-4 py-4 sm:px-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold text-gray-900">Smart Notes</h1>
              <p className="text-xs text-gray-500 mt-0.5">AI-generated meeting notes</p>
            </div>
            {!loading && (
              <span className="text-xs text-gray-400">{notes.length} note{notes.length !== 1 ? "s" : ""}</span>
            )}
          </div>

          {/* Recording controls */}
          <div className="mt-3">
            {recordState === "idle" && (
              <>
                <input
                  type="text"
                  value={keytermsInput}
                  onChange={e => setKeytermsInput(e.target.value)}
                  placeholder="Company, names to recognise… (e.g. Zilo, Samuel)"
                  className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-brand-dark/40 mb-2"
                />
                <label className="flex items-center gap-2 px-1 mb-3 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={recordMicOnly}
                    onChange={e => setRecordMicOnly(e.target.checked)}
                    className="rounded border-gray-300 text-brand-dark focus:ring-brand-dark/40 w-3.5 h-3.5"
                  />
                  <span className="text-xs text-gray-500 font-medium">Record microphone only (no screen share)</span>
                </label>
                <button
                  onClick={() => {
                    const keyterms = keytermsInput.split(/[,\n]+/).map(s => s.trim()).filter(Boolean);
                    rec.startRecording({ title: `Recording ${new Date().toLocaleDateString()}`, keyterms, recordMicOnly });
                  }}
                  className="w-full py-2 rounded-lg bg-brand-dark hover:opacity-90 text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
                >
                  <span className="w-2 h-2 rounded-full bg-white" />
                  Record Now
                </button>
              </>
            )}
            {recordState === "recording" && (
              <button
                onClick={rec.stopRecording}
                className="w-full py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-semibold transition-colors flex items-center justify-center gap-2"
              >
                <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                Stop · {elapsed}
              </button>
            )}
            {recordState === "processing" && (
              <div className="w-full py-2 rounded-lg bg-gray-100 text-gray-500 text-sm flex items-center justify-center gap-2">
                <div className="w-3 h-3 border-2 border-t-transparent border-brand-dark rounded-full animate-spin" />
                Generating notes…
              </div>
            )}
            {recordState === "tagging" && (
              <div className="w-full py-2 rounded-lg bg-brand/20 text-brand-dark text-sm font-semibold flex items-center justify-center gap-2 border border-brand-dark/30">
                <span className="w-2 h-2 rounded-full bg-brand-dark" />
                Tag speakers in panel →
              </div>
            )}
            {recordState === "done" && (
              <button
                onClick={rec.reset}
                className="w-full py-2 rounded-lg bg-gray-100 text-gray-600 text-sm hover:bg-gray-200 transition-colors"
              >
                Record another
              </button>
            )}
            {recError && <p className="text-xs text-red-500 mt-1.5">{recError}</p>}
          </div>
        </div>

        {/* Note list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <div className="w-5 h-5 border-2 border-brand-dark border-t-transparent rounded-full animate-spin" />
            </div>
          ) : notes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3 px-6 text-center">
              <div className="w-12 h-12 rounded-full bg-brand/10 flex items-center justify-center text-2xl">📝</div>
              <p className="text-sm text-gray-500">No notes yet. Hit <strong>Record Now</strong> above or wait for a calendar meeting to auto-trigger the overlay.</p>
            </div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {notes.map(n => (
                <li
                  key={n.id}
                  onClick={() => openNote(n.id)}
                  className={`px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors ${
                    selected?.id === n.id ? "bg-brand/10 border-l-2 border-brand-dark" : ""
                  }`}
                >
                  <p className="text-sm font-medium text-gray-900 truncate">{n.title}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{fmtDate(n.meeting_start ?? n.created_at)}</p>
                  {fmtDuration(n.meeting_start, n.meeting_end) && (
                    <p className="text-xs text-gray-400">{fmtDuration(n.meeting_start, n.meeting_end)}</p>
                  )}
                  {n.summary && (
                    <p className="text-xs text-gray-400 mt-1 line-clamp-2">{n.summary}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* ── Right panel ── */}
      <div
        className={cn(
          "min-w-0 flex-1 overflow-y-auto",
          !showDetailPanel && "hidden md:block"
        )}
      >
        {detailLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-6 h-6 border-2 border-brand-dark border-t-transparent rounded-full animate-spin" />
          </div>

        ) : recordState === "recording" ? (
          <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
            <div className="flex items-center gap-3 mb-6">
              <span className="w-3 h-3 rounded-full bg-red-500 animate-pulse" />
              <h2 className="text-lg font-bold text-gray-900">Recording · {elapsed}</h2>
            </div>
            <div className="bg-gray-50 rounded-xl p-5 min-h-64">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Live Transcript</p>
                {statusMsg && <p className="text-xs text-brand-dark animate-pulse">{statusMsg}</p>}
              </div>
              {liveTranscript || interimText ? (
                <>
                  <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{liveTranscript}</p>
                  {interimText && (
                    <p className="text-sm text-gray-400 italic leading-relaxed">{interimText}</p>
                  )}
                  <div ref={transcriptEndRef} />
                </>
              ) : (
                <p className="text-sm text-gray-400 italic">
                  {statusMsg || "Listening… words appear as you speak."}
                </p>
              )}
            </div>
            <button
              onClick={rec.stopRecording}
              className="mt-4 w-full py-2.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-semibold transition-colors"
            >
              Stop &amp; Tag Speakers
            </button>
          </div>

        ) : recordState === "tagging" ? (
          <div className="mx-auto max-w-lg px-4 py-8 sm:px-6 sm:py-10">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-full bg-brand/20 flex items-center justify-center">
                <span className="text-brand-dark text-lg">🎙️</span>
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Tag the speakers</h2>
                <p className="text-sm text-gray-500">
                  {Object.keys(speakerTags).length} speaker{Object.keys(speakerTags).length !== 1 ? "s" : ""} detected — assign names then generate
                </p>
              </div>
            </div>

            <div className="mt-6 space-y-4 mb-8">
              {Object.keys(speakerTags).map(spk => {
                const preview = segments.find(s => s.speaker === spk)?.text ?? "";
                return (
                  <div key={spk} className="bg-white rounded-xl border border-gray-200 p-4">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-9 h-9 rounded-full bg-brand-dark flex items-center justify-center text-sm font-bold text-white shrink-0">
                        {spk}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-400 mb-0.5">Speaker {spk} · sample:</p>
                        <p className="text-xs text-gray-500 italic truncate">&ldquo;{preview}&rdquo;</p>
                      </div>
                    </div>
                    <input
                      type="text"
                      list={`spk-${spk}-opts`}
                      value={speakerTags[spk] ?? ""}
                      onChange={e => setSpeakerTags(prev => ({ ...prev, [spk]: e.target.value }))}
                      placeholder="Enter name (e.g. You, John, Sarah…)"
                      className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-dark/40"
                    />
                    <datalist id={`spk-${spk}-opts`}>
                      <option value="You" />
                    </datalist>
                  </div>
                );
              })}
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                onClick={rec.generateWithSpeakers}
                className="flex-1 rounded-xl bg-brand-dark py-3 text-sm font-semibold text-white transition-colors hover:opacity-90"
              >
                Generate with Speakers
              </button>
              <button
                onClick={rec.generateWithPlainTranscript}
                className="rounded-xl border border-gray-200 px-5 py-3 text-sm text-gray-500 transition-colors hover:bg-gray-50"
              >
                Skip
              </button>
            </div>
          </div>

        ) : recordState === "processing" ? (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <div className="w-8 h-8 border-2 border-brand-dark border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-gray-500">Generating structured notes…</p>
          </div>

        ) : !selected ? (
          <div className="hidden h-full flex-col items-center justify-center gap-4 px-12 text-center md:flex">
            <div className="w-16 h-16 rounded-full bg-brand/10 flex items-center justify-center text-3xl">🎙️</div>
            <h2 className="text-lg font-semibold text-gray-700">Select a note</h2>
            <p className="text-sm text-gray-400 max-w-xs">
              When a calendar meeting starts, the recording overlay will appear automatically.
              Or click <strong>Record Now</strong> to capture any meeting on demand.
            </p>
          </div>

        ) : (
          <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
            <div className="mb-6 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="mb-2 flex items-center gap-2 md:hidden">
                  <button
                    type="button"
                    onClick={() => setSelected(null)}
                    className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100"
                    aria-label="Back to notes"
                  >
                    <ArrowLeft size={18} />
                  </button>
                  <span className="text-sm font-medium text-gray-500">Notes</span>
                </div>
                {editingTitle ? (
                  <input
                    type="text"
                    value={titleValue}
                    onChange={e => setTitleValue(e.target.value)}
                    onBlur={saveTitle}
                    onKeyDown={e => {
                      if (e.key === "Enter") saveTitle();
                      if (e.key === "Escape") {
                        setTitleValue(selected.title);
                        setEditingTitle(false);
                      }
                    }}
                    autoFocus
                    disabled={renaming}
                    className="text-xl font-bold text-gray-900 sm:text-2xl border-b border-brand-dark/40 focus:outline-none focus:border-brand-dark pb-0.5 bg-transparent w-full"
                  />
                ) : (
                  <div className="flex items-center gap-2 group">
                    <h2 
                      onClick={() => setEditingTitle(true)}
                      className="text-xl font-bold text-gray-900 sm:text-2xl cursor-pointer hover:text-brand-dark hover:underline decoration-brand-dark/30 underline-offset-4"
                    >
                      {selected.title}
                    </h2>
                    <button 
                      onClick={() => setEditingTitle(true)}
                      className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-brand-dark text-xs p-1 rounded transition-opacity"
                      aria-label="Rename note"
                    >
                      ✏️
                    </button>
                  </div>
                )}
                <p className="text-sm text-gray-500 mt-1">
                  {fmtDate(selected.meeting_start)}
                  {selected.meeting_end && ` · ${fmtDuration(selected.meeting_start, selected.meeting_end)}`}
                </p>
                {selected.attendees?.length > 0 && (
                  <p className="text-xs text-gray-400 mt-1">Attendees: {selected.attendees.join(", ")}</p>
                )}
              </div>
              <button
                onClick={() => deleteNote(selected.id)}
                disabled={deleting === selected.id}
                className="shrink-0 px-3 py-1.5 rounded-lg border border-red-200 text-red-600 text-xs hover:bg-red-50 transition-colors disabled:opacity-50"
              >
                {deleting === selected.id ? "Deleting…" : "Delete"}
              </button>
            </div>

            {selected.summary && (
              <Section title="Summary">
                <p className="text-sm text-gray-700 leading-relaxed">{selected.summary}</p>
              </Section>
            )}
            {selected.key_points && selected.key_points.length > 0 && (
              <Section title="Key Points">
                <ul className="space-y-1">
                  {selected.key_points.map((kp, i) => (
                    <li key={i} className="flex gap-2 text-sm text-gray-700">
                      <span className="text-brand-dark mt-0.5">•</span><span>{kp}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {selected.action_items?.length > 0 && (
              <Section title="Action Items">
                <ul className="space-y-2">
                  {selected.action_items.map((ai, i) => (
                    <li key={i} className="flex gap-2 items-start">
                      <span className="mt-0.5 w-4 h-4 rounded border border-gray-300 shrink-0 flex items-center justify-center text-[10px]">□</span>
                      <span className="text-sm text-gray-700">{ai}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {selected.decisions && selected.decisions.length > 0 && (
              <Section title="Decisions">
                <ul className="space-y-1">
                  {selected.decisions.map((d, i) => (
                    <li key={i} className="text-sm text-gray-700 flex gap-2">
                      <span className="text-green-500">✓</span><span>{d}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {selected.next_steps && (
              <Section title="Next Steps">
                <p className="text-sm text-gray-700 leading-relaxed">{selected.next_steps}</p>
              </Section>
            )}
            {selected.transcript && (
              <Section title="Transcript">
                <div className="bg-gray-50 rounded-lg p-4 max-h-72 overflow-y-auto">
                  <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap font-mono">{selected.transcript}</p>
                </div>
              </Section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{title}</h3>
      {children}
    </div>
  );
}

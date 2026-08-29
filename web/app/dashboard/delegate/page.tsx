"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, settingsApi, customersApi, type Customer } from "@/lib/api";
import { applyPersonalSignature, personalProfileFromSettings, type PersonalProfile } from "@/lib/emailSignature";
import { toast } from "sonner";
import {
  Plus,
  Play,
  Zap,
  Shield,
  Loader2,
  Check,
  CircleDashed,
  Pause,
  Trash2,
  ListChecks,
  X,
  RefreshCw,
  Pencil,
  ExternalLink,
  ArrowRight,
  Copy,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ───────────────────────────────────────────────────────────────────

type Interpretation = {
  interpreted_task: string;
  action: string;
  output: string;
  criteria_summary: string;
  contact_count: number;
  plain_summary: string;
  needs_detail: boolean;
  detail_prompt: string;
  category: string;
  rank_note?: string;
};

type Subtask = {
  id?: string;
  label: string;
  detail: string;
  status: string;
  draft?: string;
  approval?: "pending" | "approved" | "rejected";
  reviewed_at?: string;
  source?: "scouted" | "crm" | "email";
  send_status?: "sent" | "saved" | "failed" | "no_channel" | "skipped" | "manual_copy" | null;
  send_channel?:
    | "whatsapp"
    | "email"
    | "instagram"
    | "facebook"
    | "telegram"
    | "linkedin"
    | "slack"
    | "bird"
    | "crm"
    | "manual"
    | "reddit"
    | "web"
    | null;
  reply_channel?: string | null;
  send_error?: string;
  sent_at?: string;
  regeneration_count?: number;
  user_edited?: boolean;
  contact_id?: string;
  message_id?: string;
  url?: string;
  outreach_url?: string;
  outreach_mode?: "manual_web" | "auto";
  lead_group?: string;
  parent_label?: string;
  at?: string;
  email?: string;
  phone?: string;
};

const LEAD_GROUP_LABELS: Record<string, string> = {
  crm: "From your CRM",
  email: "Email inbox",
  reddit: "Reddit",
  linkedin: "LinkedIn",
  social: "Social",
  scouted: "Scouted leads",
};

const LEAD_GROUP_ORDER = ["email", "scouted", "reddit", "linkedin", "social", "crm"];

type Schedule = { frequency: string; time: string; timezone?: string };

type OpportunityTriggerFilter = "reddit" | "scouted" | "any" | "first_message" | "client_message";

type TriggerChannel =
  | "any"
  | "whatsapp"
  | "slack"
  | "instagram"
  | "facebook"
  | "telegram"
  | "linkedin"
  | "email"
  | "bird";

type Delegation = {
  id: string;
  task: string;
  interpreted: Interpretation;
  mode: "once" | "schedule" | "on_opportunity";
  schedule?: Schedule | null;
  trigger_filter?: OpportunityTriggerFilter | null;
  trigger_channel?: TriggerChannel | null;
  schedule_label: string;
  status: "running" | "scheduled" | "completed" | "paused" | "watching";
  rank: string;
  rank_note?: string;
  progress: { total: number; done: number };
  subtasks: Subtask[];
  staged_count: number;
  result_summary?: string;
  result_contacts?: string[];
  runs?: { ran_at: string; staged_count: number; summary: string; contacts?: string[] }[];
  next_run_at?: string | null;
  last_run_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

const TRIGGER_FILTERS: { value: OpportunityTriggerFilter; label: string; hint: string; group: string }[] = [
  {
    value: "client_message",
    label: "A client sends a message",
    hint: "Every inbound message on WhatsApp, Slack, Instagram, Messenger, Telegram, LinkedIn, email, or Bird. You approve each draft.",
    group: "Client messages",
  },
  {
    value: "first_message",
    label: "A client's first message only",
    hint: "Once per contact — ideal for welcome messages. Same channels as above.",
    group: "Client messages",
  },
  {
    value: "reddit",
    label: "Scouting finds a Reddit lead",
    hint: "Copy-paste outreach on Reddit threads.",
    group: "Scouted leads",
  },
  {
    value: "scouted",
    label: "Scouting finds a web lead",
    hint: "Any URL from Zilo Scout or deal alerts.",
    group: "Scouted leads",
  },
  {
    value: "any",
    label: "Any scouted lead (Reddit + web)",
    hint: "Does not include client inbox messages.",
    group: "Scouted leads",
  },
];

const TRIGGER_CHANNELS: { value: TriggerChannel; label: string }[] = [
  { value: "any", label: "Any channel" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "slack", label: "Slack" },
  { value: "instagram", label: "Instagram" },
  { value: "facebook", label: "Facebook Messenger" },
  { value: "telegram", label: "Telegram" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "email", label: "Email" },
  { value: "bird", label: "Bird" },
];

const CLIENT_MESSAGE_TRIGGERS = new Set<OpportunityTriggerFilter>(["client_message", "first_message"]);

type AutomationStatus = {
  now_utc: string;
  scheduler_interval_minutes: number;
  due_scheduled_count: number;
  watching_event_automations: number;
  automations: Array<{
    id: string;
    task: string;
    mode: string;
    status: string;
    is_due?: boolean;
    next_run_at?: string | null;
    schedule_label?: string;
  }>;
};

const FREQUENCIES: { value: string; label: string }[] = [
  { value: "every_monday", label: "Every Monday" },
  { value: "every_day", label: "Every day" },
  { value: "every_friday", label: "Every Friday" },
  { value: "first_of_month", label: "First of month" },
  { value: "every_weekday", label: "Every weekday" },
  { value: "every_sunday", label: "Every Sunday" },
];

const MAX_DRAFT_REGENERATIONS = 3;

const TIMES: { value: string; label: string }[] = [
  { value: "06:00", label: "at 6:00am" },
  { value: "07:00", label: "at 7:00am" },
  { value: "08:00", label: "at 8:00am" },
  { value: "09:00", label: "at 9:00am" },
  { value: "18:00", label: "at 6:00pm" },
  { value: "21:00", label: "at 9:00pm" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

// The founder's IANA timezone — scheduled times are interpreted in this zone.
const browserTimezone =
  (typeof Intl !== "undefined" && Intl.DateTimeFormat().resolvedOptions().timeZone) || "UTC";

// Short label like "EDT" for the timezone hint next to the time picker.
function tzShortLabel(): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZoneName: "short",
    }).formatToParts(new Date());
    return parts.find((p) => p.type === "timeZoneName")?.value || browserTimezone;
  } catch {
    return browserTimezone;
  }
}

function relTime(iso?: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Date.now() - t;
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  const hrs = Math.round(abs / 3600000);
  const days = Math.round(abs / 86400000);
  const ago = diff >= 0;
  let s: string;
  if (mins < 1) s = "just now";
  else if (mins < 60) s = `${mins} min`;
  else if (hrs < 24) s = `${hrs} hour${hrs === 1 ? "" : "s"}`;
  else s = `${days} day${days === 1 ? "" : "s"}`;
  if (s === "just now") return s;
  return ago ? `${s} ago` : `in ${s}`;
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function statusDotClass(d: Delegation): string {
  if (d.status === "running") return "bg-emerald-500";
  if (d.status === "scheduled" || d.status === "watching") return "bg-blue-500";
  if (d.status === "paused") return "bg-amber-500";
  return "bg-slate-300";
}

function isActive(d: Delegation): boolean {
  return (
    d.status === "running" ||
    d.status === "scheduled" ||
    d.status === "watching" ||
    d.status === "paused"
  );
}

function isAutomation(d: Delegation): boolean {
  return d.mode === "schedule" || d.mode === "on_opportunity";
}

function whenSummary(d: Delegation): string {
  if (d.mode === "schedule") return d.schedule_label.replace(/^Automation · /i, "");
  if (d.mode === "on_opportunity") {
    if (d.trigger_filter && CLIENT_MESSAGE_TRIGGERS.has(d.trigger_filter)) {
      const ch = d.trigger_channel && d.trigger_channel !== "any"
        ? TRIGGER_CHANNELS.find((c) => c.value === d.trigger_channel)?.label ?? d.trigger_channel
        : null;
      const base =
        d.trigger_filter === "first_message"
          ? "When a client's first message arrives"
          : "When a client sends a message";
      return ch ? `${base} on ${ch}` : base;
    }
    return d.schedule_label.replace(/^Automation · when /i, "When ").replace(/ appear$/i, " appear");
  }
  return "Now";
}

type CustomerContact = Customer & {
  slack_channel_id?: string | null;
};

const SYNTHETIC_PHONE_PREFIXES = ["meta_", "telegram_", "linkedin_", "bird_", "slack_"] as const;

function normalizeContactChannel(raw?: string | null): string {
  const ch = (raw || "").trim().toLowerCase();
  const aliases: Record<string, string> = {
    messenger: "facebook",
    fb: "facebook",
    ig: "instagram",
    wa: "whatsapp",
    gmail: "email",
    mail: "email",
  };
  return aliases[ch] || ch;
}

function isRealWhatsAppPhone(phone?: string | null): boolean {
  const p = (phone || "").trim();
  if (!p) return false;
  const lower = p.toLowerCase();
  if (SYNTHETIC_PHONE_PREFIXES.some((prefix) => lower.startsWith(prefix))) return false;
  return p.replace(/\D/g, "").length >= 8;
}

function channelFromSyntheticPhone(phone?: string | null): string | null {
  const p = (phone || "").trim().toLowerCase();
  if (p.startsWith("meta_instagram_")) return "instagram";
  if (p.startsWith("meta_messenger_") || p.startsWith("meta_facebook_")) return "facebook";
  if (p.startsWith("telegram_")) return "telegram";
  if (p.startsWith("linkedin_")) return "linkedin";
  if (p.startsWith("bird_")) return "bird";
  if (p.startsWith("slack_")) return "slack";
  return null;
}

function replyChannelFromCustomer(c: CustomerContact): string {
  if (c.slack_channel_id) return "slack";
  const ch = normalizeContactChannel(c.channel || c.source);
  if (ch && ch !== "crm" && ch !== "unknown" && ch !== "scouted") return ch;
  const synthetic = channelFromSyntheticPhone(c.phone_number);
  if (synthetic) return synthetic;
  if (c.email && !isRealWhatsAppPhone(c.phone_number)) return "email";
  if (isRealWhatsAppPhone(c.phone_number)) return "whatsapp";
  return ch || "";
}

function customerMatchesTriggerChannel(
  c: CustomerContact,
  triggerChannel?: TriggerChannel | null
): boolean {
  const want = (triggerChannel || "any").trim().toLowerCase();
  if (!want || want === "any" || want === "all") return true;
  return normalizeContactChannel(replyChannelFromCustomer(c)) === normalizeContactChannel(want);
}

/** Bold the criteria substring within the plain summary. */
function ConfirmationText({ interp }: { interp: Interpretation }) {
  const text = interp.plain_summary || "";
  const criteria = interp.criteria_summary?.trim();
  if (!criteria || !text.toLowerCase().includes(criteria.toLowerCase())) {
    return <span>{text}</span>;
  }
  const idx = text.toLowerCase().indexOf(criteria.toLowerCase());
  return (
    <span>
      {text.slice(0, idx)}
      <span className="font-medium text-slate-900">{text.slice(idx, idx + criteria.length)}</span>
      {text.slice(idx + criteria.length)}
    </span>
  );
}

// ── New delegation form ──────────────────────────────────────────────────────

function NewDelegationForm({
  onCreated,
  presetTask,
}: {
  onCreated: (d: Delegation) => void;
  presetTask?: string;
}) {
  const [task, setTask] = useState(presetTask || "");
  const [runKind, setRunKind] = useState<"once" | "automation">("once");
  const [whenType, setWhenType] = useState<"schedule" | "event">("event");
  const [frequency, setFrequency] = useState("every_monday");
  const [time, setTime] = useState("07:00");
  const [triggerFilter, setTriggerFilter] = useState<OpportunityTriggerFilter>("client_message");
  const [triggerChannel, setTriggerChannel] = useState<TriggerChannel>("any");
  const [interp, setInterp] = useState<Interpretation | null>(null);
  const [interpreting, setInterpreting] = useState(false);
  const [creating, setCreating] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reqId = useRef(0);

  const runInterpret = useCallback(async (value: string) => {
    const text = value.trim();
    if (text.length < 4) {
      setInterp(null);
      return;
    }
    const myId = ++reqId.current;
    setInterpreting(true);
    try {
      const res = await api.post<Interpretation>("/delegate/interpret", { task: text });
      if (myId === reqId.current) setInterp(res);
    } catch (e) {
      if (myId === reqId.current) {
        setInterp(null);
        toast.error(e instanceof Error ? e.message : "Couldn't interpret task");
      }
    } finally {
      if (myId === reqId.current) setInterpreting(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runInterpret(task), 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [task, runInterpret]);

  const whenLabel = useMemo(() => {
    if (runKind === "once") return "Now";
    if (whenType === "event") {
      const row = TRIGGER_FILTERS.find((x) => x.value === triggerFilter);
      let label = row?.label ?? triggerFilter;
      if (CLIENT_MESSAGE_TRIGGERS.has(triggerFilter) && triggerChannel !== "any") {
        const ch = TRIGGER_CHANNELS.find((c) => c.value === triggerChannel)?.label ?? triggerChannel;
        label = `${label} (${ch})`;
      }
      return label;
    }
    const f = FREQUENCIES.find((x) => x.value === frequency)?.label ?? frequency;
    const t = TIMES.find((x) => x.value === time)?.label ?? `at ${time}`;
    return `${f} ${t}`;
  }, [runKind, whenType, frequency, time, triggerFilter, triggerChannel]);

  const reset = () => {
    setTask("");
    setRunKind("once");
    setWhenType("event");
    setInterp(null);
  };

  const create = async () => {
    if (!task.trim() || creating) return;
    setCreating(true);
    try {
      const mode =
        runKind === "once"
          ? "once"
          : whenType === "schedule"
          ? "schedule"
          : "on_opportunity";
      const body =
        mode === "schedule"
          ? { task: task.trim(), mode, schedule: { frequency, time, timezone: browserTimezone } }
          : mode === "on_opportunity"
          ? {
              task: task.trim(),
              mode,
              trigger_filter: triggerFilter,
              trigger_channel: CLIENT_MESSAGE_TRIGGERS.has(triggerFilter) ? triggerChannel : "any",
            }
          : { task: task.trim(), mode: "once" };
      const d = await api.post<Delegation>("/delegate", body);
      toast.success(
        runKind === "automation"
          ? "Automation saved — Zilo will run it on that trigger."
          : "Delegated. Zilo is on it."
      );
      onCreated(d);
      reset();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't delegate");
    } finally {
      setCreating(false);
    }
  };

  const rankNote = interp?.rank_note || "Drafter rank — drafts staged for your approval before anything sends";
  const taskReady = task.trim().length >= 4;
  const interpretReady = !taskReady || (interp !== null && !interpreting);
  const canSubmit = Boolean(task.trim()) && !creating && !interp?.needs_detail && interpretReady;

  return (
    <div className="px-6 py-6 sm:px-8">
      <h2 className="text-[15px] font-medium text-slate-900">New task or automation</h2>
      <p className="mt-0.5 text-xs text-slate-500">
        Describe what Zilo should do, then pick when — or leave it as a one-time task.
      </p>

      {/* Then — what */}
      <div className="mt-6">
        <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Then — what should Zilo do?
        </label>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={3}
          autoFocus
          placeholder="e.g. Draft Reddit outreach for leads that match our ICP"
          className="mt-2 w-full resize-none rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-300"
        />
      </div>

      {/* Once vs Automation */}
      <div className="mt-5">
        <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          How should this run?
        </label>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setRunKind("once")}
            className={cn(
              "flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors",
              runKind === "once"
                ? "border-slate-900 bg-slate-50 font-medium text-slate-900"
                : "border-slate-200 text-slate-600 hover:border-slate-300"
            )}
          >
            <Play size={14} /> Do it now
          </button>
          <button
            type="button"
            onClick={() => setRunKind("automation")}
            className={cn(
              "flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors",
              runKind === "automation"
                ? "border-slate-900 bg-slate-50 font-medium text-slate-900"
                : "border-slate-200 text-slate-600 hover:border-slate-300"
            )}
          >
            <Zap size={14} /> Automation
          </button>
        </div>
      </div>

      {runKind === "automation" && (
        <div className="mt-5 space-y-4 rounded-lg border border-orange-100 bg-orange-50/40 p-4">
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              When
            </label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setWhenType("event")}
                className={cn(
                  "rounded-lg border px-3 py-2 text-sm transition-colors",
                  whenType === "event"
                    ? "border-orange-300 bg-white font-medium text-slate-900"
                    : "border-orange-100 bg-white/60 text-slate-600 hover:border-orange-200"
                )}
              >
                Something happens
              </button>
              <button
                type="button"
                onClick={() => setWhenType("schedule")}
                className={cn(
                  "rounded-lg border px-3 py-2 text-sm transition-colors",
                  whenType === "schedule"
                    ? "border-orange-300 bg-white font-medium text-slate-900"
                    : "border-orange-100 bg-white/60 text-slate-600 hover:border-orange-200"
                )}
              >
                On a schedule
              </button>
            </div>
          </div>

          {whenType === "event" ? (
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-medium text-slate-600">Trigger</label>
                <select
                  value={triggerFilter}
                  onChange={(e) => setTriggerFilter(e.target.value as OpportunityTriggerFilter)}
                  className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-slate-400 focus:outline-none"
                >
                  <optgroup label="Client messages">
                    {TRIGGER_FILTERS.filter((f) => f.group === "Client messages").map((f) => (
                      <option key={f.value} value={f.value}>
                        {f.label}
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="Scouted leads">
                    {TRIGGER_FILTERS.filter((f) => f.group === "Scouted leads").map((f) => (
                      <option key={f.value} value={f.value}>
                        {f.label}
                      </option>
                    ))}
                  </optgroup>
                </select>
                <p className="mt-2 text-[11px] text-slate-500">
                  {TRIGGER_FILTERS.find((f) => f.value === triggerFilter)?.hint ??
                    "Runs when the trigger matches. You still approve every draft before send."}
                </p>
              </div>
              {CLIENT_MESSAGE_TRIGGERS.has(triggerFilter) && (
                <div>
                  <label className="text-[11px] font-medium text-slate-600">Channel (optional)</label>
                  <select
                    value={triggerChannel}
                    onChange={(e) => setTriggerChannel(e.target.value as TriggerChannel)}
                    className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-slate-400 focus:outline-none"
                  >
                    {TRIGGER_CHANNELS.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                  <p className="mt-2 text-[11px] text-slate-500">
                    Limit this automation to one inbox, or leave as any channel.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div>
              <label className="text-[11px] font-medium text-slate-600">Repeat</label>
              <div className="mt-1.5 grid grid-cols-2 gap-2">
                <select
                  value={frequency}
                  onChange={(e) => setFrequency(e.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-slate-400 focus:outline-none"
                >
                  {FREQUENCIES.map((f) => (
                    <option key={f.value} value={f.value}>
                      {f.label}
                    </option>
                  ))}
                </select>
                <select
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-slate-400 focus:outline-none"
                >
                  {TIMES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
              <p className="mt-2 text-[11px] text-slate-500">
                Runs at {TIMES.find((x) => x.value === time)?.label ?? time} {tzShortLabel()} ({browserTimezone}).
                Only new leads since the last run — no duplicate drafts.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Confirmation box */}
      <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50/70 p-4">
        <div className="flex items-center gap-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Zilo understood this as
          </p>
          {interpreting && <Loader2 size={11} className="animate-spin text-slate-400" />}
        </div>
        <div className="mt-2 text-sm leading-relaxed text-slate-700">
          {!task.trim() ? (
            <span className="text-slate-400">Start typing and Zilo will restate the task here.</span>
          ) : interp?.needs_detail ? (
            <span className="text-amber-700">{interp.detail_prompt}</span>
          ) : interp ? (
            <>
              {runKind === "automation" ? (
                <>
                  <span className="font-medium text-slate-900">When </span>
                  <span className="font-medium text-orange-800">{whenLabel.toLowerCase()}</span>
                  <span className="font-medium text-slate-900">, then </span>
                  <ConfirmationText interp={interp} />
                  <span className="text-slate-500"> Drafts wait for your approval.</span>
                </>
              ) : (
                <>
                  <ConfirmationText interp={interp} />{" "}
                  <span className="text-slate-500">Run once, right now.</span>
                </>
              )}
            </>
          ) : (
            <span className="text-slate-400">Interpreting…</span>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="mt-5 flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="flex items-start gap-1.5 text-[11px] text-slate-500 sm:max-w-sm">
          <Shield size={13} className="mt-0.5 shrink-0 text-slate-400" />
          {rankNote}
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={reset}
            className="rounded-lg px-3 py-2 text-sm text-slate-500 hover:text-slate-700"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canSubmit}
            onClick={create}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
          >
            {creating ? <Loader2 size={14} className="animate-spin" /> : null}
            {runKind === "automation" ? "Save automation" : "Delegate now"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Badge ─────────────────────────────────────────────────────────────────────

function ModeBadge({ d }: { d: Delegation }) {
  if (isAutomation(d)) {
    return (
      <span className="shrink-0 rounded-full bg-orange-50 px-2.5 py-0.5 text-[11px] font-medium text-orange-700">
        {d.schedule_label || "Automation"}
      </span>
    );
  }
  return (
    <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-medium text-emerald-600">
      One-time
    </span>
  );
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="h-[3px] w-full overflow-hidden rounded-full bg-slate-100">
      <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}

function pendingCount(d: Delegation): number {
  return d.subtasks.filter((s) => (s.approval ?? "pending") === "pending").length;
}

function delegationStatusLine(d: Delegation): string {
  const total = d.progress?.total ?? 0;
  const pending = pendingCount(d);

  if (d.status === "running") {
    return `Started ${relTime(d.started_at)} · Zilo is working through ${total} contact${total === 1 ? "" : "s"}`;
  }
  if (d.status === "paused") return "Paused — Zilo stopped after the current step";
  if (d.mode === "schedule") {
    const last = d.last_run_at ? ` · Last run ${fmtDate(d.last_run_at)}` : "";
    const review = pending > 0 ? ` · ${pending} awaiting review` : "";
    return `Next run ${relTime(d.next_run_at)}${last}${review}`;
  }
  if (d.mode === "on_opportunity") {
    const last = d.last_run_at ? ` · Last draft ${relTime(d.last_run_at)}` : "";
    const review = pending > 0 ? ` · ${pending} awaiting review` : "";
    const prefix =
      d.trigger_filter && CLIENT_MESSAGE_TRIGGERS.has(d.trigger_filter) ? "Listening" : "Watching";
    return `${prefix} — ${whenSummary(d)}${last}${review}`;
  }
  if (d.status === "completed") {
    return `Completed ${relTime(d.completed_at)} · ${d.result_summary ?? ""}`;
  }
  return "";
}

function hasDraftContent(d: Delegation): boolean {
  return d.subtasks.some((s) => Boolean(s.draft?.trim()));
}

function isWebManualLead(s: Subtask): boolean {
  if (s.outreach_mode === "manual_web") return true;
  if (s.email || s.phone) return false;
  if (s.send_channel && s.send_channel !== "web" && s.send_channel !== "reddit" && s.send_channel !== "manual") {
    return false;
  }
  const url = (s.outreach_url || s.url || "").toLowerCase();
  if (!url) return false;
  if (s.lead_group === "reddit" || url.includes("reddit.com")) return true;
  return s.source === "scouted" && !s.contact_id;
}

function extractCopyMessage(draft: string): string {
  const text = draft.trim();
  if (!text) return "";
  const low = text.toLowerCase();
  for (const marker of ["suggested opener:", "opener:", "message:", "draft:"]) {
    const idx = low.indexOf(marker);
    if (idx >= 0) return text.slice(idx + marker.length).trim();
  }
  return text;
}

function webLinkForSubtask(s: Subtask): string {
  return (s.outreach_url || s.url || "").trim();
}

function channelLabel(ch?: string | null): string {
  const map: Record<string, string> = {
    whatsapp: "WhatsApp",
    email: "Email",
    instagram: "Instagram",
    facebook: "Facebook Messenger",
    telegram: "Telegram",
    linkedin: "LinkedIn",
    slack: "Slack",
    bird: "Bird",
    reddit: "Reddit",
    web: "Web",
  };
  return map[(ch || "").toLowerCase()] || ch || "message";
}

function draftDestination(s: Subtask): { href: string; label: string; external?: boolean } | null {
  if (s.approval !== "approved") return null;
  const cid = s.contact_id;
  if (s.send_status === "sent" && cid) {
    const ch = s.send_channel;
    if (ch === "whatsapp") {
      return {
        href: `/dashboard/messages?customer=${encodeURIComponent(cid)}`,
        label: "View in Messages",
      };
    }
    if (ch === "email") {
      return {
        href: `/dashboard/customers/${cid}?tab=emails`,
        label: "View contact & emails",
      };
    }
    if (ch === "instagram" || ch === "facebook" || ch === "linkedin" || ch === "telegram" || ch === "slack") {
      return {
        href: `/dashboard/social-inbox?customer=${encodeURIComponent(cid)}`,
        label: `View in Social Inbox`,
      };
    }
  }
  if ((s.send_status === "saved" || (s.send_status === "sent" && cid)) && cid) {
    return { href: `/dashboard/customers/${cid}`, label: "View in CRM" };
  }
  const webLink = webLinkForSubtask(s);
  if (
    webLink &&
    isWebManualLead(s) &&
    (s.send_status === "manual_copy" || (s.send_status === "saved" && !s.email && !s.phone))
  ) {
    const isReddit = s.lead_group === "reddit" || webLink.includes("reddit.com");
    return {
      href: webLink,
      label: isReddit ? "Open on Reddit" : "Open source link",
      external: true,
    };
  }
  if (s.url && s.send_status === "saved" && isWebManualLead(s)) {
    return { href: s.url, label: "View source", external: true };
  }
  return null;
}

function sendStatusLabel(s: Subtask): string | null {
  if (s.approval !== "approved") return null;
  if (s.send_status === "sent") {
    if (s.send_channel) return `Sent via ${channelLabel(s.send_channel)}`;
    return "Sent";
  }
  if (s.send_status === "saved") return "Saved to your CRM";
  if (s.send_status === "manual_copy") {
    if (s.send_channel === "reddit") return "Copy message and paste on Reddit";
    if (s.send_channel === "web") return "Copy message and paste on the source site";
    return "Copy message and paste manually";
  }
  if (s.send_status === "failed") return s.send_error ? `Send failed: ${s.send_error}` : "Send failed";
  if (s.send_status === "no_channel") return s.send_error || "No channel available — add phone/email";
  return null;
}

function toastForApproval(session: Delegation, draftId: string) {
  const idx = session.subtasks.findIndex((s, i) => (s.id ?? String(i)) === draftId);
  const st = idx >= 0 ? session.subtasks[idx] : null;
  if (!st) {
    toast.success("Approved.");
    return;
  }
  const label = sendStatusLabel(st);
  const dest = draftDestination(st);
  if (st.send_status === "sent") {
    toast.success(dest ? `${label || "Sent."} — use the link below to open it.` : label || "Sent.");
  } else if (st.send_status === "saved") {
    toast.success(dest ? "Saved to CRM — tap View in CRM below." : "Approved and saved to your CRM.");
  } else if (st.send_status === "manual_copy") {
    toast.success("Approved — copy the message below and paste it on Reddit or the source link.");
  } else if (st.send_status === "failed" || st.send_status === "no_channel") {
    toast.error(label || "Approved but could not send.");
  } else {
    toast.success("Approved.");
  }
}

// ── Draft review ──────────────────────────────────────────────────────────────

function DraftCard({
  s,
  draftId,
  busy,
  regenerating,
  personalProfile,
  appendIfMissing,
  onApprove,
  onReject,
  onSave,
  onRegenerate,
}: {
  s: Subtask;
  draftId: string;
  busy: boolean;
  regenerating: boolean;
  personalProfile: PersonalProfile;
  appendIfMissing: boolean;
  onApprove: (draftId: string) => Promise<void>;
  onReject: (draftId: string) => void;
  onSave: (draftId: string, draft: string) => Promise<void>;
  onRegenerate: (draftId: string, feedback: string) => Promise<void>;
}) {
  const approval = s.approval ?? "pending";
  const rawDraft = s.draft?.trim();
  const draftText = rawDraft
    ? applyPersonalSignature(rawDraft, personalProfile, { appendIfMissing })
    : "";
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draftText || "");
  const [feedback, setFeedback] = useState("");
  const regenCount = s.regeneration_count ?? 0;
  const atRegenCap = regenCount >= MAX_DRAFT_REGENERATIONS;
  const dirty = editing && text.trim() !== (draftText || "");

  useEffect(() => {
    if (editing) return;
    setText(draftText || "");
    if (!draftText) setEditing(false);
  }, [draftText, s.id, editing]);

  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3",
        approval === "approved"
          ? "border-emerald-200 bg-emerald-50/40"
          : approval === "rejected"
          ? "border-slate-200 bg-slate-50/60 opacity-75"
          : "border-slate-200 bg-white"
      )}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0">
          {approval === "approved" ? (
            <Check size={14} className="text-emerald-600" />
          ) : approval === "rejected" ? (
            <X size={14} className="text-slate-400" />
          ) : (
            <CircleDashed size={14} className="text-slate-400" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <span className="text-sm font-medium text-slate-900">{s.label}</span>
          {s.parent_label && s.parent_label !== s.label && (
            <p className="mt-0.5 truncate text-[11px] text-slate-400">From: {s.parent_label}</p>
          )}
          {s.reply_channel && !isWebManualLead(s) && (
            <p className="mt-1 text-[11px] text-slate-500">
              {s.reply_channel === "email" || s.source === "email"
                ? `Reply via ${channelLabel("email")} after you approve`
                : `Reply on ${channelLabel(s.reply_channel)} after you approve`}
              {s.parent_label && s.parent_label !== s.label ? ` · ${s.parent_label}` : ""}
            </p>
          )}
          {isWebManualLead(s) && (
            <p className="mt-1 text-[11px] font-medium text-orange-700">
              {s.lead_group === "reddit" || webLinkForSubtask(s).includes("reddit.com")
                ? "Reddit — copy & paste on the thread"
                : "Web lead — copy & paste on the source site"}
            </p>
          )}
          <span className="ml-0 mt-0.5 block text-xs text-slate-500 sm:ml-2 sm:mt-0 sm:inline">
            {approval === "approved"
              ? sendStatusLabel(s) || "Approved"
              : approval === "rejected"
              ? "Skipped"
              : "Awaiting review"}
          </span>
          {s.user_edited && approval === "pending" && (
            <span className="ml-2 text-[10px] text-slate-400">(edited)</span>
          )}
        </div>
      </div>

      {draftText && approval === "pending" && (
        <div className="mt-3 space-y-2">
          {editing ? (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              className="w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2.5 text-sm leading-relaxed text-slate-800 focus:border-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-300"
            />
          ) : (
            <div className="rounded-md border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-sm leading-relaxed whitespace-pre-wrap text-slate-700">
              {draftText}
            </div>
          )}

          {isWebManualLead(s) && webLinkForSubtask(s) ? (
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={webLinkForSubtask(s)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-orange-200 bg-orange-50 px-3 py-1.5 text-xs font-medium text-orange-800 hover:bg-orange-100"
              >
                Open on {webLinkForSubtask(s).includes("reddit.com") ? "Reddit" : "source site"}
                <ExternalLink size={12} />
              </a>
              <button
                type="button"
                onClick={() => {
                  const msg = extractCopyMessage(draftText);
                  if (!msg) return;
                  void navigator.clipboard.writeText(msg).then(
                    () => toast.success("Message copied — paste it on Reddit or the thread"),
                    () => toast.error("Could not copy to clipboard")
                  );
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                <Copy size={12} /> Copy message
              </button>
            </div>
          ) : null}

          <input
            type="text"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Tell Zilo what to change (optional, for regenerate)"
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-xs text-slate-700 placeholder:text-slate-400 focus:border-slate-400 focus:outline-none"
          />

          <div className="flex flex-wrap gap-2">
            {!editing ? (
              <button
                type="button"
                disabled={busy || regenerating}
                onClick={() => setEditing(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                <Pencil size={12} /> Edit
              </button>
            ) : (
              <>
                <button
                  type="button"
                  disabled={busy || !dirty || !text.trim()}
                  onClick={() => {
                    onSave(draftId, text.trim());
                    setEditing(false);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  Save edit
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setText(draftText || "");
                    setEditing(false);
                  }}
                  className="rounded-lg px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700"
                >
                  Cancel
                </button>
              </>
            )}
            {!atRegenCap && (
              <button
                type="button"
                disabled={busy || regenerating || editing}
                onClick={() => onRegenerate(draftId, feedback.trim())}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                {regenerating ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <RefreshCw size={12} />
                )}
                Regenerate
                {regenCount > 0 ? ` (${regenCount}/${MAX_DRAFT_REGENERATIONS})` : ""}
              </button>
            )}
            {atRegenCap && (
              <span className="self-center text-[11px] text-slate-400">Regenerate limit reached — edit manually</span>
            )}
            <button
              type="button"
              disabled={busy || regenerating}
              onClick={async () => {
                if (editing && dirty && text.trim()) {
                  await onSave(draftId, text.trim());
                  setEditing(false);
                }
                await onApprove(draftId);
              }}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              <Check size={14} /> Approve
            </button>
            <button
              type="button"
              disabled={busy || regenerating || editing}
              onClick={() => onReject(draftId)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3.5 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              <X size={14} /> Skip
            </button>
          </div>
        </div>
      )}

      {draftText && approval !== "pending" && (
        <div className="mt-3 space-y-2">
          <div className="rounded-md border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-sm leading-relaxed whitespace-pre-wrap text-slate-700">
            {draftText}
          </div>
          <div className="flex flex-wrap gap-2">
            {(s.send_status === "manual_copy" || isWebManualLead(s)) && (
              <button
                type="button"
                onClick={() => {
                  const msg = extractCopyMessage(draftText);
                  if (!msg) return;
                  void navigator.clipboard.writeText(msg).then(
                    () => toast.success("Message copied"),
                    () => toast.error("Could not copy")
                  );
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <Copy size={14} /> Copy message
              </button>
            )}
            {(() => {
              const dest = draftDestination(s);
              if (!dest) return null;
              const btnClass =
                "inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-medium text-white hover:bg-slate-800";
              if (dest.external) {
                return (
                  <a href={dest.href} target="_blank" rel="noopener noreferrer" className={btnClass}>
                    {dest.label} <ExternalLink size={14} />
                  </a>
                );
              }
              return (
                <Link href={dest.href} className={btnClass}>
                  {dest.label} <ArrowRight size={14} />
                </Link>
              );
            })()}
            {s.contact_id && s.send_status === "manual_copy" && (
              <Link
                href={`/dashboard/customers/${s.contact_id}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3.5 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                View in CRM <ArrowRight size={14} />
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DraftReviewPanel({
  d,
  busy,
  regeneratingId,
  personalProfile,
  appendIfMissing,
  onApprove,
  onReject,
  onSave,
  onRegenerate,
  onApproveAll,
  onRunAgain,
}: {
  d: Delegation;
  busy: boolean;
  regeneratingId: string | null;
  personalProfile: PersonalProfile;
  appendIfMissing: boolean;
  onApprove: (draftId: string) => Promise<void>;
  onReject: (draftId: string) => void;
  onSave: (draftId: string, draft: string) => Promise<void>;
  onRegenerate: (draftId: string, feedback: string) => Promise<void>;
  onApproveAll: () => void;
  onRunAgain: () => void;
}) {
  const pending = pendingCount(d);
  const withDrafts = hasDraftContent(d);

  if (d.subtasks.length === 0) return null;

  return (
    <div id="draft-review" className="mt-6 scroll-mt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Review drafts
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            One card per person or company — edit individually, approve one by one or all at once.
          </p>
        </div>
        {pending > 0 && withDrafts && (
          <button
            type="button"
            disabled={busy}
            onClick={onApproveAll}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Approve all ({pending})
          </button>
        )}
      </div>

      {!withDrafts && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/70 px-4 py-3 text-sm text-amber-900">
          <p>Draft text isn&apos;t stored for this run. Run again to generate drafts you can review and approve.</p>
          <button
            type="button"
            disabled={busy}
            onClick={onRunAgain}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            <Play size={14} /> Run again
          </button>
        </div>
      )}

      <div className="mt-3 space-y-5">
        {(() => {
          const grouped = new Map<string, { s: Subtask; draftId: string; i: number }[]>();
          d.subtasks.forEach((s, i) => {
            const g = s.lead_group || (s.source === "crm" ? "crm" : "scouted");
            const list = grouped.get(g) || [];
            list.push({ s, draftId: s.id ?? String(i), i });
            grouped.set(g, list);
          });
          const keys = [
            ...LEAD_GROUP_ORDER.filter((k) => grouped.has(k)),
            ...[...grouped.keys()].filter((k) => !LEAD_GROUP_ORDER.includes(k)),
          ];
          if (keys.length <= 1 && d.subtasks.length > 0) {
            return d.subtasks.map((s, i) => {
              const draftId = s.id ?? String(i);
              return (
                <DraftCard
                  key={draftId}
                  s={s}
                  draftId={draftId}
                  busy={busy}
                  regenerating={regeneratingId === draftId}
                  personalProfile={personalProfile}
                  appendIfMissing={appendIfMissing}
                  onApprove={onApprove}
                  onReject={onReject}
                  onSave={onSave}
                  onRegenerate={onRegenerate}
                />
              );
            });
          }
          return keys.map((g) => (
            <div key={g}>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                {LEAD_GROUP_LABELS[g] || g} ({grouped.get(g)?.length ?? 0})
              </p>
              <div className="space-y-3">
                {(grouped.get(g) || []).map(({ s, draftId }) => (
                  <DraftCard
                    key={draftId}
                    s={s}
                    draftId={draftId}
                    busy={busy}
                    regenerating={regeneratingId === draftId}
                    personalProfile={personalProfile}
                    appendIfMissing={appendIfMissing}
                    onApprove={onApprove}
                    onReject={onReject}
                    onSave={onSave}
                    onRegenerate={onRegenerate}
                  />
                ))}
              </div>
            </div>
          ));
        })()}
      </div>

      {pending === 0 && withDrafts && (
        <p className="mt-3 text-sm text-emerald-700">All drafts reviewed.</p>
      )}
    </div>
  );
}

// ── Automation health (testing) ─────────────────────────────────────────────

function AutomationHealthPanel({
  status,
  error,
  loading,
  onRefresh,
  onRunDueScheduled,
}: {
  status: AutomationStatus | null;
  error?: boolean;
  loading: boolean;
  onRefresh: () => void;
  onRunDueScheduled: () => void;
}) {
  if (error && !status) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50/80 p-3 text-[11px] text-amber-900">
        <p className="font-semibold">Automation status unavailable</p>
        <p className="mt-1 text-amber-800/90">Couldn&apos;t load the scheduler diagnostics.</p>
        <button
          type="button"
          disabled={loading}
          onClick={onRefresh}
          className="mt-2 w-full rounded-md border border-amber-200 bg-white px-2 py-1.5 font-medium text-amber-900 hover:bg-amber-50 disabled:opacity-50"
        >
          Retry
        </button>
      </div>
    );
  }
  if (!status) return null;
  const due = status.due_scheduled_count ?? 0;
  const watching = status.watching_event_automations ?? 0;
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 text-[11px] text-slate-600">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-slate-700">Automation engine</p>
          <p className="mt-1">
            Scheduler checks every {status.scheduler_interval_minutes} min
            {due > 0 ? (
              <span className="font-medium text-amber-700"> · {due} scheduled run{due === 1 ? "" : "s"} due now</span>
            ) : (
              <span> · no scheduled runs waiting</span>
            )}
          </p>
          {watching > 0 && (
            <p className="mt-0.5">{watching} event automation{watching === 1 ? "" : "s"} watching</p>
          )}
        </div>
        <button
          type="button"
          disabled={loading}
          onClick={onRefresh}
          className="shrink-0 rounded p-1 text-slate-400 hover:bg-white hover:text-slate-600"
          title="Refresh status"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      {due > 0 && (
        <button
          type="button"
          disabled={loading}
          onClick={onRunDueScheduled}
          className="mt-2 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Run due scheduled now
        </button>
      )}
    </div>
  );
}

// ── Detail view ────────────────────────────────────────────────────────────────

function DetailView({
  d,
  busy,
  personalProfile,
  appendIfMissing,
  onPause,
  onResume,
  onDelete,
  onRunNow,
  onApproveDraft,
  onRejectDraft,
  onSaveDraft,
  onRegenerateDraft,
  onApproveAllDrafts,
  onRunAgain,
  onSimulateEvent,
  regeneratingId,
  scrollToReview,
}: {
  d: Delegation;
  busy: boolean;
  personalProfile: PersonalProfile;
  appendIfMissing: boolean;
  onPause: () => void;
  onResume: () => void;
  onDelete: () => void;
  onRunNow: () => void;
  onApproveDraft: (draftId: string) => Promise<void>;
  onRejectDraft: (draftId: string) => void;
  onSaveDraft: (draftId: string, draft: string) => Promise<void>;
  onRegenerateDraft: (draftId: string, feedback: string) => Promise<void>;
  onApproveAllDrafts: () => void;
  onRunAgain: () => void;
  onSimulateEvent?: (
    customerId: string,
    message: string,
    options?: { isFirst?: boolean }
  ) => Promise<void>;
  regeneratingId: string | null;
  scrollToReview?: boolean;
}) {
  const [testOpen, setTestOpen] = useState(false);
  const [customers, setCustomers] = useState<CustomerContact[]>([]);
  const [testCustomerId, setTestCustomerId] = useState("");
  const [testMessage, setTestMessage] = useState("Hi — I wanted to ask about pricing.");
  const [testTreatAsFirst, setTestTreatAsFirst] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const isFirstMessageAutomation = d.trigger_filter === "first_message";
  const canSimulate =
    d.mode === "on_opportunity" &&
    d.trigger_filter &&
    CLIENT_MESSAGE_TRIGGERS.has(d.trigger_filter) &&
    !!onSimulateEvent;

  const filteredTestCustomers = useMemo(() => {
    if (!d.trigger_channel || d.trigger_channel === "any") return customers;
    return customers.filter((c) => customerMatchesTriggerChannel(c, d.trigger_channel));
  }, [customers, d.trigger_channel]);

  useEffect(() => {
    if (!testOpen || customers.length > 0) return;
    customersApi.list().then((rows) => setCustomers(rows as CustomerContact[])).catch(() => {
      toast.error("Couldn't load contacts for test event");
    });
  }, [testOpen, customers.length]);

  useEffect(() => {
    if (testCustomerId && !filteredTestCustomers.some((c) => c.id === testCustomerId)) {
      setTestCustomerId("");
    }
  }, [filteredTestCustomers, testCustomerId]);

  const running = d.status === "running";
  const scheduled = d.mode === "schedule";
  const automation = isAutomation(d);
  const total = d.progress?.total ?? 0;
  const done = d.progress?.done ?? 0;
  const pending = pendingCount(d);

  useEffect(() => {
    if (!scrollToReview) return;
    requestAnimationFrame(() => {
      document.getElementById("draft-review")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [scrollToReview, d.id]);

  const statusLine = delegationStatusLine(d);

  return (
    <div className="px-6 py-6 sm:px-8">
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-[15px] font-medium text-slate-900">{d.task}</h2>
        <ModeBadge d={d} />
      </div>
      <p className="mt-1 text-xs text-slate-500">{statusLine}</p>

      {/* Progress */}
      {(running || (total > 0 && d.status !== "completed")) && (
        <div className="mt-5">
          <ProgressBar done={done} total={total} />
          <p className="mt-1.5 text-right text-[11px] text-slate-500">
            {done} of {total} done
          </p>
        </div>
      )}

      {/* What Zilo has done */}
      {d.subtasks.length > 0 && (
        <div className="mt-6">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            What Zilo has done so far
          </p>
          <div className="mt-2 space-y-1.5">
            {d.subtasks.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                {s.status === "done" ? (
                  <Check size={14} className="shrink-0 text-emerald-500" />
                ) : (
                  <CircleDashed size={14} className="shrink-0 text-slate-400" />
                )}
                <span className="text-slate-700">{s.label}</span>
                <span className="text-slate-400">— {s.detail}</span>
                <span className="ml-auto text-[11px] text-slate-400">{relTime(s.at)}</span>
              </div>
            ))}
            {running && done < total && (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <CircleDashed size={14} className="shrink-0 animate-pulse" />
                {total - done} more contact{total - done === 1 ? "" : "s"} pending
              </div>
            )}
          </div>
        </div>
      )}

      {/* Draft review */}
      {(d.status === "completed" || d.status === "watching" || pending > 0 || hasDraftContent(d)) && (
        <DraftReviewPanel
          d={d}
          busy={busy}
          regeneratingId={regeneratingId}
          personalProfile={personalProfile}
          appendIfMissing={appendIfMissing}
          onApprove={onApproveDraft}
          onReject={onRejectDraft}
          onSave={onSaveDraft}
          onRegenerate={onRegenerateDraft}
          onApproveAll={onApproveAllDrafts}
          onRunAgain={onRunAgain}
        />
      )}

      {/* Completed result */}
      {d.status === "completed" && d.result_summary && (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-sm text-emerald-800">
          {d.result_summary}
        </div>
      )}

      {/* Actions */}
      <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
        {scheduled || automation ? (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={onRunNow}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              <Play size={14} /> Run now
            </button>
            {d.status === "paused" ? (
              <button
                type="button"
                disabled={busy}
                onClick={onResume}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <Play size={14} /> Resume
              </button>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={onPause}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <Pause size={14} /> Pause
              </button>
            )}
            {canSimulate && (
              <button
                type="button"
                disabled={busy}
                onClick={() => setTestOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-sm text-orange-900 hover:bg-orange-100 disabled:opacity-50"
              >
                <Zap size={14} /> Test event
              </button>
            )}
          </>
        ) : (
          <>
            {running && (
              <button
                type="button"
                disabled={busy}
                onClick={onPause}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <Pause size={14} /> Pause
              </button>
            )}
            {d.status === "paused" && (
              <button
                type="button"
                disabled={busy}
                onClick={onResume}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              >
                <Play size={14} /> Resume
              </button>
            )}
            {d.status === "completed" && (
              <button
                type="button"
                disabled={busy}
                onClick={onRunAgain}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <Play size={14} /> Run again
              </button>
            )}
          </>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={onDelete}
          className="ml-auto inline-flex items-center gap-1.5 px-2 py-2 text-sm text-slate-400 hover:text-red-500 disabled:opacity-50"
        >
          <Trash2 size={14} /> Delete
        </button>
      </div>

      {testOpen && canSimulate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-lg">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-slate-900">Test client-message trigger</h3>
              <button type="button" onClick={() => setTestOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Simulates an inbound message without a live webhook. Pick a contact on the channel this automation listens to.
            </p>
            {d.trigger_channel && d.trigger_channel !== "any" && (
              <p className="mt-2 text-[11px] text-orange-800">
                Filtered to {channelLabel(d.trigger_channel)} contacts only.
              </p>
            )}
            <label className="mt-4 block text-[11px] font-medium text-slate-600">Contact</label>
            <select
              value={testCustomerId}
              onChange={(e) => setTestCustomerId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="">Select a contact…</option>
              {filteredTestCustomers.map((c) => {
                const ch = replyChannelFromCustomer(c);
                const chLabel = ch ? channelLabel(ch) : null;
                return (
                  <option key={c.id} value={c.id}>
                    {c.name || c.phone_number || c.email || c.id}
                    {chLabel ? ` · ${chLabel}` : ""}
                  </option>
                );
              })}
            </select>
            {filteredTestCustomers.length === 0 && customers.length > 0 && (
              <p className="mt-2 text-[11px] text-amber-700">
                No contacts match {channelLabel(d.trigger_channel)}. Connect that channel or choose &quot;Any channel&quot; on the automation.
              </p>
            )}
            <label className="mt-3 block text-[11px] font-medium text-slate-600">Sample message</label>
            <textarea
              value={testMessage}
              onChange={(e) => setTestMessage(e.target.value)}
              rows={3}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
            />
            {isFirstMessageAutomation && (
              <label className="mt-3 flex cursor-pointer items-start gap-2 text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={testTreatAsFirst}
                  onChange={(e) => setTestTreatAsFirst(e.target.checked)}
                  className="mt-0.5 rounded border-slate-300"
                />
                <span>
                  Treat as this contact&apos;s first message
                  <span className="mt-0.5 block text-[11px] text-slate-500">
                    Required for welcome automations when the contact already has inbox history.
                  </span>
                </span>
              </label>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setTestOpen(false)}
                className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!testCustomerId || testLoading}
                onClick={async () => {
                  if (!onSimulateEvent) return;
                  setTestLoading(true);
                  try {
                    await onSimulateEvent(testCustomerId, testMessage, {
                      isFirst: isFirstMessageAutomation ? testTreatAsFirst : undefined,
                    });
                    setTestOpen(false);
                    setTestTreatAsFirst(false);
                  } finally {
                    setTestLoading(false);
                  }
                }}
                className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              >
                {testLoading ? "Running…" : "Fire trigger"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Active card (below the panel) ────────────────────────────────────────────

function ActiveCard({
  d,
  onOpen,
  onReview,
  onPause,
}: {
  d: Delegation;
  onOpen: () => void;
  onReview: () => void;
  onPause: () => void;
}) {
  const running = d.status === "running";
  const total = d.progress?.total ?? 0;
  const done = d.progress?.done ?? 0;
  const pending = pendingCount(d);
  const showReview = pending > 0 || hasDraftContent(d);
  const meta = running
    ? `Started ${relTime(d.started_at)} · working through ${total} contact${total === 1 ? "" : "s"}`
    : d.mode === "schedule"
    ? `Next run ${relTime(d.next_run_at)}${d.last_run_at ? ` · Last run ${fmtDate(d.last_run_at)} — ${d.staged_count} staged` : ""}`
    : isAutomation(d)
    ? whenSummary(d)
    : d.result_summary ?? "";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <button onClick={onOpen} className="text-left text-[13px] font-medium text-slate-900 hover:underline">
          {d.task}
        </button>
        <ModeBadge d={d} />
      </div>
      <p className="mt-1 text-xs text-slate-500">{meta}</p>
      {running && (
        <div className="mt-3">
          <ProgressBar done={done} total={total} />
        </div>
      )}
      <div className="mt-3 flex items-center gap-3 border-t border-slate-100 pt-3 text-xs">
        {showReview && (
          <button onClick={onReview} className="font-medium text-slate-700 hover:text-slate-900">
            Review drafts{pending > 0 ? ` (${pending})` : ""}
          </button>
        )}
        {running && (
          <button onClick={onPause} className="text-slate-500 hover:text-slate-700">
            Pause
          </button>
        )}
        <button onClick={onOpen} className="text-slate-500 hover:text-slate-700">
          View log
        </button>
      </div>
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────

function DelegatePageContent() {
  const searchParams = useSearchParams();
  const presetTask = searchParams.get("task") || "";
  const [delegations, setDelegations] = useState<Delegation[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [view, setView] = useState<"new" | "detail">("new");
  const [busy, setBusy] = useState(false);
  const [scrollToReview, setScrollToReview] = useState(false);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const [personalProfile, setPersonalProfile] = useState<PersonalProfile>({
    name: "",
    title: "",
    company: "",
  });
  const [appendSignatureToDrafts, setAppendSignatureToDrafts] = useState(true);
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null);
  const [automationStatusLoading, setAutomationStatusLoading] = useState(false);
  const [automationStatusError, setAutomationStatusError] = useState(false);

  const loadAutomationStatus = useCallback(async () => {
    setAutomationStatusLoading(true);
    try {
      const data = await api.get<AutomationStatus>("/delegate/automation-status");
      setAutomationStatus(data);
      setAutomationStatusError(false);
    } catch {
      setAutomationStatus(null);
      setAutomationStatusError(true);
    } finally {
      setAutomationStatusLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    try {
      const [data, settingsRes] = await Promise.all([
        api.get<Delegation[]>("/delegate"),
        settingsApi.get().catch(() => null),
      ]);
      setDelegations(data);
      setPersonalProfile(personalProfileFromSettings(settingsRes || undefined));
      setAppendSignatureToDrafts(settingsRes?.append_signature_to_drafts !== false);
    } catch {
      toast.error("Couldn't load delegations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    loadAutomationStatus();
  }, [load, loadAutomationStatus]);

  // Open the form pre-filled when arriving with ?task=
  useEffect(() => {
    if (presetTask) setView("new");
  }, [presetTask]);

  // Poll while work is in progress (2s) or automations are watching (5s).
  const pollFast = useMemo(
    () =>
      delegations.some((d) => d.status === "running" || pendingCount(d) > 0),
    [delegations]
  );
  const pollWatching = useMemo(
    () => delegations.some((d) => d.status === "watching"),
    [delegations]
  );
  useEffect(() => {
    if (!pollFast && !pollWatching) return;
    const intervalMs = pollFast ? 2000 : 5000;
    const t = setInterval(load, intervalMs);
    return () => clearInterval(t);
  }, [pollFast, pollWatching, load]);

  const active = delegations.find((d) => d.id === activeId) || null;
  const activeList = delegations.filter(isActive);
  const doneList = delegations.filter((d) => d.status === "completed");

  const openDelegation = (id: string, opts?: { review?: boolean }) => {
    setActiveId(id);
    setView("detail");
    setScrollToReview(Boolean(opts?.review));
    if (opts?.review) {
      setTimeout(() => setScrollToReview(false), 600);
    }
  };

  const newDelegation = () => {
    setActiveId(null);
    setView("new");
  };

  const onCreated = (d: Delegation) => {
    setDelegations((prev) => [d, ...prev]);
    setActiveId(d.id);
    setView("detail");
    if (isAutomation(d)) void loadAutomationStatus();
  };

  const applyDelegation = (d: Delegation) => {
    setDelegations((prev) => prev.map((x) => (x.id === d.id ? d : x)));
  };

  const mutate = async (fn: () => Promise<Delegation | { session: Delegation } | void>, optimisticId?: string) => {
    setBusy(true);
    try {
      const res = await fn();
      if (res && "session" in res && res.session?.id) {
        applyDelegation(res.session);
      } else if (res && "id" in res && (res as Delegation).id) {
        applyDelegation(res as Delegation);
      } else if (optimisticId) {
        await load();
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const pause = (id: string) => mutate(() => api.post<Delegation>(`/delegate/${id}/pause`, {}));
  const resume = (id: string) => mutate(() => api.post<Delegation>(`/delegate/${id}/resume`, {}));
  const runNow = (id: string) =>
    mutate(async () => {
      await api.post(`/delegate/${id}/run`, {});
      toast.success("Running now.");
      setTimeout(load, 800);
    }, id);

  const runDueScheduled = () =>
    mutate(async () => {
      const res = await api.post<{ triggered: number }>("/delegate/run-due-scheduled", {});
      toast.success(
        res.triggered > 0
          ? `Scheduler ran ${res.triggered} due automation${res.triggered === 1 ? "" : "s"}.`
          : "No scheduled automations were due right now."
      );
      await load();
      await loadAutomationStatus();
    });

  const simulateEvent = (
    delegationId: string,
    customerId: string,
    message: string,
    options?: { isFirst?: boolean }
  ) =>
    mutate(async () => {
      const body: { customer_id: string; message: string; is_first?: boolean } = {
        customer_id: customerId,
        message,
      };
      if (options?.isFirst !== undefined) body.is_first = options.isFirst;
      const res = await api.post<{ result: { message?: string; matched?: boolean }; session?: Delegation }>(
        `/delegate/${delegationId}/simulate-event`,
        body
      );
      if (res.session) applyDelegation(res.session);
      if (res.result?.matched === false) {
        toast.warning(res.result?.message || "Automation ran but did not stage a new draft.");
      } else {
        toast.success(res.result?.message || "Test event fired.");
      }
      await load();
      await loadAutomationStatus();
    }, delegationId);
  const remove = (id: string) =>
    mutate(async () => {
      await api.delete(`/delegate/${id}`);
      setDelegations((prev) => prev.filter((x) => x.id !== id));
      if (activeId === id) newDelegation();
      toast.success("Deleted.");
    }, id);

  const approveDraft = async (delegationId: string, draftId: string) => {
    await mutate(async () => {
      const res = await api.post<{ session: Delegation }>(
        `/delegate/${delegationId}/drafts/${draftId}/approve`,
        {}
      );
      if (res.session) toastForApproval(res.session, draftId);
      return res;
    });
  };

  const rejectDraft = (delegationId: string, draftId: string) =>
    mutate(async () => {
      const res = await api.post<{ session: Delegation }>(
        `/delegate/${delegationId}/drafts/${draftId}/reject`,
        {}
      );
      toast.success("Skipped.");
      return res;
    });

  const saveDraft = async (delegationId: string, draftId: string, draft: string) => {
    await mutate(async () => {
      const res = await api.patch<{ session: Delegation }>(
        `/delegate/${delegationId}/drafts/${draftId}`,
        { draft }
      );
      toast.success("Draft saved.");
      return res;
    });
  };

  const regenerateDraft = async (delegationId: string, draftId: string, feedback: string) => {
    setRegeneratingId(draftId);
    try {
      await mutate(async () => {
        const res = await api.post<{ session: Delegation }>(
          `/delegate/${delegationId}/drafts/${draftId}/regenerate`,
          { feedback }
        );
        toast.success("New draft ready.");
        return res;
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Couldn't regenerate";
      if (msg.includes("429") || msg.toLowerCase().includes("maximum")) {
        toast.error(`Regenerate limit (${MAX_DRAFT_REGENERATIONS}) reached — edit manually.`);
      }
    } finally {
      setRegeneratingId(null);
    }
  };

  const approveAllDrafts = (delegationId: string) =>
    mutate(async () => {
      const res = await api.post<{ session: Delegation }>(
        `/delegate/${delegationId}/drafts/approve-all`,
        {}
      );
      const sent = res.session?.subtasks.filter((s) => s.send_status === "sent").length ?? 0;
      const saved = res.session?.subtasks.filter((s) => s.send_status === "saved").length ?? 0;
      const failed = res.session?.subtasks.filter((s) => s.send_status === "failed" || s.send_status === "no_channel").length ?? 0;
      if (failed > 0) toast.warning(`Approved all — ${sent} sent, ${saved} saved to CRM, ${failed} need attention.`);
      else toast.success(`Approved all — ${sent} sent${saved ? `, ${saved} saved to CRM` : ""}.`);
      return res;
    });

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-white text-slate-900">
      <div className="flex flex-col lg:flex-row">
        {/* Sidebar */}
        <aside className="w-full shrink-0 border-b border-slate-200 lg:w-[220px] lg:border-b-0 lg:border-r">
          <div className="space-y-5 p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Delegate</p>
            <button
              type="button"
              onClick={newDelegation}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
            >
              <Plus size={15} /> New delegation
            </button>

            <AutomationHealthPanel
              status={automationStatus}
              error={automationStatusError}
              loading={automationStatusLoading || busy}
              onRefresh={loadAutomationStatus}
              onRunDueScheduled={runDueScheduled}
            />

            {activeList.length > 0 && (
              <div className="space-y-1">
                <p className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Active
                </p>
                {activeList.map((d) => (
                  <SidebarItem
                    key={d.id}
                    d={d}
                    active={d.id === activeId && view === "detail"}
                    onClick={() => openDelegation(d.id)}
                  />
                ))}
              </div>
            )}

            {doneList.length > 0 && (
              <div className="space-y-1">
                <p className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Done</p>
                {doneList.map((d) => (
                  <SidebarItem
                    key={d.id}
                    d={d}
                    active={d.id === activeId && view === "detail"}
                    onClick={() => openDelegation(d.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* Main + cards */}
        <main className="min-w-0 flex-1">
          {loading ? (
            <div className="flex justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-slate-300" />
            </div>
          ) : view === "detail" && active ? (
            <DetailView
              d={active}
              busy={busy}
              personalProfile={personalProfile}
              appendIfMissing={appendSignatureToDrafts}
              scrollToReview={scrollToReview}
              regeneratingId={regeneratingId}
              onPause={() => pause(active.id)}
              onResume={() => resume(active.id)}
              onDelete={() => remove(active.id)}
              onRunNow={() => runNow(active.id)}
              onRunAgain={() => runNow(active.id)}
              onSimulateEvent={(customerId, message, options) =>
                simulateEvent(active.id, customerId, message, options)
              }
              onApproveDraft={(draftId) => approveDraft(active.id, draftId)}
              onRejectDraft={(draftId) => rejectDraft(active.id, draftId)}
              onSaveDraft={(draftId, draft) => saveDraft(active.id, draftId, draft)}
              onRegenerateDraft={(draftId, feedback) => regenerateDraft(active.id, draftId, feedback)}
              onApproveAllDrafts={() => approveAllDrafts(active.id)}
            />
          ) : (
            <NewDelegationForm key={presetTask} onCreated={onCreated} presetTask={presetTask} />
          )}

          {/* Active delegation cards */}
          {!loading && activeList.length > 0 && (
            <div className="border-t border-slate-100 px-6 py-6 sm:px-8">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Active tasks & automations
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {activeList.map((d) => (
                  <ActiveCard
                    key={d.id}
                    d={d}
                    onOpen={() => openDelegation(d.id)}
                    onReview={() => openDelegation(d.id, { review: true })}
                    onPause={() => pause(d.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Empty state */}
          {!loading && delegations.length === 0 && view === "new" && (
            <div className="border-t border-slate-100 px-6 py-10 text-center sm:px-8">
              <ListChecks className="mx-auto h-7 w-7 text-slate-300" />
              <p className="mx-auto mt-3 max-w-sm text-sm text-slate-500">
                Describe what Zilo should do, or save it as an automation with a when trigger.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default function DelegatePage() {
  return (
    <Suspense fallback={<div className="flex-1 flex items-center justify-center"><span className="text-slate-400 text-sm">Loading…</span></div>}>
      <DelegatePageContent />
    </Suspense>
  );
}

function SidebarItem({
  d,
  active,
  onClick,
}: {
  d: Delegation;
  active: boolean;
  onClick: () => void;
}) {
  const meta =
    d.status === "completed"
      ? `Completed ${fmtDate(d.completed_at)}`
      : d.status === "running"
      ? "Running"
      : d.status === "watching"
      ? whenSummary(d)
      : d.status === "scheduled"
      ? whenSummary(d)
      : d.status === "paused"
      ? "Paused"
      : isAutomation(d)
      ? whenSummary(d)
      : `Completed ${fmtDate(d.completed_at)}`;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-lg px-2.5 py-2 text-left transition-colors",
        active ? "border border-slate-200 bg-slate-50" : "hover:bg-slate-50"
      )}
    >
      <p className="truncate text-xs font-medium text-slate-800">{d.task}</p>
      <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-500">
        <span className={cn("inline-block h-1.5 w-1.5 rounded-full", statusDotClass(d))} />
        {meta}
      </p>
    </button>
  );
}

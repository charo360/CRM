"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Pencil, X } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { WorkflowFlowDiagram } from "./workflow-flow-diagram";

export interface WorkflowEditTrigger {
  type: string;
  condition?: string;
}

export interface WorkflowEditStep {
  id: string;
  action: string;
  params: Record<string, unknown>;
  delay_minutes?: number;
}

export interface WorkflowEditable {
  id: string;
  name: string;
  description?: string;
  trigger: WorkflowEditTrigger;
  steps: WorkflowEditStep[];
  enabled: boolean;
}

const TRIGGER_OPTIONS: { value: string; label: string }[] = [
  { value: "incoming_message", label: "When a customer sends a message" },
  { value: "intent_detected", label: "When AI detects an intent" },
  { value: "tag_added", label: "When a tag is added" },
  { value: "customer_created", label: "When a new customer is created" },
  { value: "pipeline_stage_changed", label: "When pipeline stage changes" },
];

const PIPELINE_STAGES = ["lead", "prospect", "active", "won", "lost"];

function normalizeSteps(steps: WorkflowEditStep[]): WorkflowEditStep[] {
  return steps.map((s, i) => ({
    id: s.id || `step_${i + 1}`,
    action: s.action,
    params: { ...(s.params || {}) },
    delay_minutes: s.delay_minutes ?? 0,
  }));
}

function StepFields({
  step,
  index,
  onChange,
}: {
  step: WorkflowEditStep;
  index: number;
  onChange: (s: WorkflowEditStep) => void;
}) {
  const p = step.params;

  const setParam = (key: string, value: unknown) => {
    onChange({ ...step, params: { ...step.params, [key]: value } });
  };

  switch (step.action) {
    case "send_message": {
      const dest = (p.destination as string) || "customer_whatsapp";
      return (
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">Message text</label>
            <textarea
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-[100px] focus:outline-none focus:ring-2 focus:ring-brand"
              value={String(p.message ?? "")}
              onChange={(e) => setParam("message", e.target.value)}
              placeholder="Hi {customer_name}! … Use {business_name}, {phone} as placeholders."
            />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">Where to send</label>
            <select
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand bg-white"
              value={dest}
              onChange={(e) => setParam("destination", e.target.value)}
            >
              <option value="customer_whatsapp">Customer — WhatsApp</option>
              <option value="owner_push">You only — phone push alert (no WhatsApp to customer)</option>
              <option value="email" disabled>
                Customer — email (coming soon)
              </option>
            </select>
            <p className="text-[11px] text-slate-400 mt-1">
              WhatsApp requires the contact to have a phone number. Push uses your logged-in app notifications.
            </p>
          </div>
          {dest === "owner_push" && (
            <div>
              <label className="block text-[11px] font-medium text-slate-500 mb-1">Push title</label>
              <input
                type="text"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
                value={String(p.title ?? "Automation")}
                onChange={(e) => setParam("title", e.target.value)}
              />
            </div>
          )}
        </div>
      );
    }
    case "notify_owner":
      return (
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">Title</label>
            <input
              type="text"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
              value={String(p.title ?? "")}
              onChange={(e) => setParam("title", e.target.value)}
            />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">Message</label>
            <textarea
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-[72px] focus:outline-none focus:ring-2 focus:ring-brand"
              value={String(p.message ?? "")}
              onChange={(e) => setParam("message", e.target.value)}
            />
          </div>
        </div>
      );
    case "tag_contact":
      return (
        <div>
          <label className="block text-[11px] font-medium text-slate-500 mb-1">Tag name</label>
          <input
            type="text"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            value={String(p.tag ?? "")}
            onChange={(e) => setParam("tag", e.target.value)}
          />
        </div>
      );
    case "create_followup":
      return (
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">Note</label>
            <textarea
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-[64px] focus:outline-none focus:ring-2 focus:ring-brand"
              value={String(p.note ?? "")}
              onChange={(e) => setParam("note", e.target.value)}
            />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">Due in (hours)</label>
            <input
              type="number"
              min={1}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
              value={Number(p.due_hours ?? 24)}
              onChange={(e) => setParam("due_hours", parseInt(e.target.value, 10) || 24)}
            />
          </div>
        </div>
      );
    case "move_pipeline_stage":
      return (
        <div>
          <label className="block text-[11px] font-medium text-slate-500 mb-1">Stage</label>
          <select
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand bg-white"
            value={String(p.stage ?? "lead")}
            onChange={(e) => setParam("stage", e.target.value)}
          >
            {PIPELINE_STAGES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      );
    case "wait":
      return (
        <div>
          <label className="block text-[11px] font-medium text-slate-500 mb-1">Wait (hours)</label>
          <input
            type="number"
            min={0.1}
            step={0.5}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            value={Number(p.hours ?? 1)}
            onChange={(e) => setParam("hours", parseFloat(e.target.value) || 1)}
          />
        </div>
      );
    case "assign_owner":
      return (
        <div>
          <label className="block text-[11px] font-medium text-slate-500 mb-1">Team member name (partial match)</label>
          <input
            type="text"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            value={String(p.member_name ?? "")}
            onChange={(e) => setParam("member_name", e.target.value)}
          />
        </div>
      );
    case "escalate_to_human":
      return (
        <div>
          <label className="block text-[11px] font-medium text-slate-500 mb-1">Reason</label>
          <input
            type="text"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            value={String(p.reason ?? "")}
            onChange={(e) => setParam("reason", e.target.value)}
          />
        </div>
      );
    case "if_no_reply":
      return <p className="text-xs text-slate-500">Continues only if the customer has not replied since the workflow started.</p>;
    default:
      return (
        <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-2 py-1.5">
          This step type can’t be edited in the visual editor yet. Use AI rebuild or contact support.
        </p>
      );
  }
}

export function WorkflowEditModal({
  workflow,
  open,
  onClose,
  onSaved,
}: {
  workflow: WorkflowEditable | null;
  open: boolean;
  onClose: () => void;
  onSaved: (wf: WorkflowEditable) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [triggerType, setTriggerType] = useState("incoming_message");
  const [condition, setCondition] = useState("always");
  const [steps, setSteps] = useState<WorkflowEditStep[]>([]);
  const [runsEnabled, setRunsEnabled] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!workflow || !open) return;
    setName(workflow.name);
    setDescription(workflow.description ?? "");
    setTriggerType(workflow.trigger?.type || "incoming_message");
    setCondition(workflow.trigger?.condition ?? "always");
    setSteps(normalizeSteps(workflow.steps as WorkflowEditStep[]));
    setRunsEnabled(workflow.enabled !== false);
  }, [workflow, open]);

  if (!open || !workflow) return null;

  async function handleSave() {
    const n = name.trim();
    if (!n) {
      toast.error("Name is required");
      return;
    }
    if (!steps.length) {
      toast.error("Add at least one step");
      return;
    }
    setSaving(true);
    try {
      const body = {
        name: n,
        description: description.trim(),
        enabled: runsEnabled,
        trigger: { type: triggerType, condition: condition.trim() || "always" },
        steps: steps.map((s) => ({
          id: s.id,
          action: s.action,
          params: s.params,
          delay_minutes: s.delay_minutes ?? 0,
        })),
      };
      const updated = await api.put<WorkflowEditable>(`/workflows/${workflow!.id}`, body);
      toast.success("Automation updated");
      onSaved(updated);
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function updateStep(i: number, next: WorkflowEditStep) {
    setSteps((prev) => prev.map((s, j) => (j === i ? next : s)));
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/45 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Pencil size={18} className="text-brand-dark" />
            <h2 className="text-base font-semibold text-slate-800">Edit automation</h2>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100 text-slate-500">
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-4 space-y-4 flex-1">
          <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5">
            <div>
              <p className="text-sm font-medium text-slate-800">Automation runs</p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                When off, triggers are ignored until you turn this back on.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={runsEnabled}
              onClick={() => setRunsEnabled((v) => !v)}
              className={cn(
                "relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                runsEnabled ? "bg-brand-dark" : "bg-slate-300"
              )}
            >
              <span
                className={cn(
                  "pointer-events-none absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-200",
                  runsEnabled ? "translate-x-[1.375rem]" : "translate-x-0"
                )}
              />
            </button>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">Name</label>
            <input
              type="text"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">Description (optional)</label>
            <input
              type="text"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3 space-y-2">
            <p className="text-[11px] font-semibold text-slate-600 uppercase tracking-wide">When this runs</p>
            <select
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand"
              value={triggerType}
              onChange={(e) => setTriggerType(e.target.value)}
            >
              {TRIGGER_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <div>
              <label className="block text-[11px] font-medium text-slate-500 mb-1">Condition</label>
              <input
                type="text"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                placeholder="always, message_contains('price'), …"
              />
            </div>
          </div>

          <WorkflowFlowDiagram
            compact
            trigger={{ type: triggerType, condition: condition.trim() || "always" }}
            steps={steps.map((s) => ({
              action: s.action,
              params: s.params,
              delay_minutes: s.delay_minutes,
            }))}
          />

          <div className="space-y-4">
            <p className="text-[11px] font-semibold text-slate-600 uppercase tracking-wide">Steps</p>
            {steps.map((step, i) => (
              <div key={step.id} className="rounded-xl border border-[#009B3A]/20 bg-emerald-50/40 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-slate-900">
                    Step {i + 1}: {step.action.replace(/_/g, " ")}
                  </span>
                  <label className="flex items-center gap-1 text-[11px] text-slate-500">
                    Delay (min)
                    <input
                      type="number"
                      min={0}
                      className="w-14 border border-slate-200 rounded px-1 py-0.5 text-xs"
                      value={step.delay_minutes ?? 0}
                      onChange={(e) =>
                        updateStep(i, {
                          ...step,
                          delay_minutes: parseInt(e.target.value, 10) || 0,
                        })
                      }
                    />
                  </label>
                </div>
                <StepFields step={step} index={i} onChange={(next) => updateStep(i, next)} />
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-slate-100 bg-slate-50/80">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-brand-dark text-white hover:bg-brand disabled:opacity-60"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            Save changes
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { Zap, ChevronRight, Clock, Flag } from "lucide-react";
import { cn } from "@/lib/utils";

const TRIGGER_LABELS: Record<string, string> = {
  incoming_message: "Message received",
  intent_detected: "Intent detected",
  tag_added: "Tag added",
  customer_created: "New customer",
  pipeline_stage_changed: "Stage changed",
};

const ACTION_LABELS: Record<string, string> = {
  send_message: "Send message",
  tag_contact: "Tag contact",
  assign_owner: "Assign owner",
  notify_owner: "Notify you",
  create_followup: "Create follow-up",
  move_pipeline_stage: "Move pipeline",
  escalate_to_human: "Escalate",
  wait: "Wait",
  if_no_reply: "If no reply",
};

function actionLabel(action: string) {
  return ACTION_LABELS[action] ?? action.replace(/_/g, " ");
}

function sendDestHint(params: Record<string, unknown> | undefined) {
  if (!params) return "";
  const d = String(params.destination ?? "customer_whatsapp").toLowerCase();
  if (d === "owner_push" || d === "notify_me") return "Push to you";
  if (d === "customer_whatsapp") return "WhatsApp";
  return d.replace(/_/g, " ");
}

export interface FlowTrigger {
  type: string;
  condition?: string;
}

export interface FlowStep {
  action: string;
  params?: Record<string, unknown>;
  delay_minutes?: number;
}

export function WorkflowFlowDiagram({
  trigger,
  steps,
  className,
  compact,
}: {
  trigger: FlowTrigger;
  steps: FlowStep[];
  className?: string;
  compact?: boolean;
}) {
  const triggerTitle = TRIGGER_LABELS[trigger.type] ?? trigger.type.replace(/_/g, " ");
  const cond =
    trigger.condition && trigger.condition !== "always" ? trigger.condition : null;

  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white",
        compact ? "p-3" : "p-4",
        className,
      )}
      aria-label="Automation flow"
    >
      <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-3">
        {compact ? "Flow" : "Workflow map"}
      </p>

      {/* Mobile: vertical stack */}
      <div className="flex flex-col gap-0 md:hidden">
        <FlowNode kind="trigger" compact={compact} title={triggerTitle} subtitle={cond} />
        {steps.map((step, i) => (
          <div key={i}>
            <Connector />
            {step.delay_minutes != null && step.delay_minutes > 0 ? (
              <>
                <DelayChip minutes={step.delay_minutes} compact={compact} />
                <Connector />
              </>
            ) : null}
            <FlowNode
              kind="step"
              compact={compact}
              index={i + 1}
              title={actionLabel(step.action)}
              subtitle={step.action === "send_message" ? sendDestHint(step.params) : undefined}
            />
          </div>
        ))}
        <Connector />
        <FlowNode kind="end" compact={compact} title="Done" subtitle="Automation completes" />
      </div>

      {/* Desktop: horizontal scroll */}
      <div className="hidden md:flex items-stretch gap-0 overflow-x-auto pb-1 pt-0.5">
        <div className="w-[158px] shrink-0">
          <FlowNode kind="trigger" compact={compact} title={triggerTitle} subtitle={cond} />
        </div>
        {steps.map((step, i) => (
          <div key={i} className="flex shrink-0 items-stretch">
            <ConnectorHorizontal />
            {step.delay_minutes != null && step.delay_minutes > 0 ? (
              <>
                <div className="flex w-[88px] shrink-0 flex-col items-center justify-center px-1">
                  <DelayChip minutes={step.delay_minutes} compact={compact} horizontal />
                </div>
                <ConnectorHorizontal />
              </>
            ) : null}
            <div className="w-[158px] shrink-0">
              <FlowNode
                kind="step"
                compact={compact}
                index={i + 1}
                title={actionLabel(step.action)}
                subtitle={step.action === "send_message" ? sendDestHint(step.params) : undefined}
              />
            </div>
          </div>
        ))}
        <ConnectorHorizontal />
        <div className="w-[120px] shrink-0">
          <FlowNode kind="end" compact={compact} title="Done" subtitle="Complete" />
        </div>
      </div>
    </div>
  );
}

function FlowNode({
  kind,
  title,
  subtitle,
  index,
  compact,
}: {
  kind: "trigger" | "step" | "end";
  title: string;
  subtitle?: string | null;
  index?: number;
  compact?: boolean;
}) {
  const isTrigger = kind === "trigger";
  const isEnd = kind === "end";
  return (
    <div
      className={cn(
        "rounded-xl border shadow-sm text-left",
        compact ? "px-3 py-2.5" : "px-3 py-3",
        isTrigger && "border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50/80",
        kind === "step" && "border-[#009B3A]/25 bg-white",
        isEnd && "border-slate-200 bg-slate-50/90",
      )}
    >
      <div className="flex items-start gap-2">
        {isTrigger ? (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-800">
            <Zap className="h-4 w-4" aria-hidden />
          </span>
        ) : isEnd ? (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-200 text-slate-600">
            <Flag className="h-4 w-4" aria-hidden />
          </span>
        ) : (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#009B3A] text-xs font-bold text-white">
            {index}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            {isTrigger ? "When" : isEnd ? "End" : "Then"}
          </p>
          <p className={cn("font-semibold text-slate-900 leading-snug", compact ? "text-xs" : "text-sm")}>
            {title}
          </p>
          {subtitle ? (
            <p className="mt-0.5 line-clamp-2 font-mono text-[10px] leading-snug text-slate-600">{subtitle}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function DelayChip({ minutes, compact, horizontal }: { minutes: number; compact?: boolean; horizontal?: boolean }) {
  return (
    <div
      className={cn(
        "flex items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm",
        horizontal ? "mx-1 px-2 py-1" : "my-1 py-1.5",
        compact ? "text-[10px]" : "text-xs",
      )}
    >
      <Clock className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden />
      <span className="font-medium tabular-nums">Wait {minutes}m</span>
    </div>
  );
}

function Connector() {
  return (
    <div className="flex justify-center py-0.5" aria-hidden>
      <div className="h-4 w-px bg-gradient-to-b from-slate-300 to-slate-200" />
    </div>
  );
}

function ConnectorHorizontal() {
  return (
    <div className="flex w-6 shrink-0 items-center justify-center self-center" aria-hidden>
      <ChevronRight className="h-5 w-5 text-slate-300" />
    </div>
  );
}

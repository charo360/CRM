import type { AssistantMessage, AssistantStep } from "@/lib/api";

export type PlanSlide = Record<string, unknown>;

export function clonePlanSlides(slides: PlanSlide[]): PlanSlide[] {
  return slides.map((s) => ({
    ...s,
    body: [...((s.body as string[] | undefined) ?? [])],
  }));
}

export function normalizeSlidesForGeneration(slides: PlanSlide[]): PlanSlide[] {
  return slides.map((s, i) => {
    const body = ((s.body as string[] | undefined) ?? [])
      .map((b) => String(b).trim())
      .filter(Boolean)
      .slice(0, 3);
    const prompt =
      (s.image_prompt as string | undefined) ||
      (s.image_concept as string | undefined) ||
      "";
    return {
      ...s,
      title: String(s.title ?? `Slide ${i + 1}`).trim(),
      layout: (s.layout as string | undefined) || (i === 0 ? "title" : "content"),
      body,
      is_title: i === 0,
      ...(prompt ? { image_prompt: prompt, image_concept: prompt } : {}),
    };
  });
}

export function slidesPlanDirty(source: PlanSlide[], draft: PlanSlide[]): boolean {
  if (!draft.length) return false;
  return (
    JSON.stringify(normalizeSlidesForGeneration(source)) !==
    JSON.stringify(normalizeSlidesForGeneration(draft))
  );
}

export function findPlanStep(steps?: AssistantStep[]) {
  return [...(steps ?? [])]
    .reverse()
    .find(
      (s) =>
        s.tool === "plan_visual_presentation" &&
        (s.result as Record<string, unknown>)?.plan_ready &&
        (s.result as Record<string, unknown>)?.slides,
    );
}

export function hasSuccessfulDeck(steps?: AssistantStep[]) {
  return [...(steps ?? [])].some(
    (s) =>
      (s.tool === "create_visual_presentation" || s.tool === "regenerate_slide") &&
      (s.result as Record<string, unknown>)?.success &&
      (s.result as Record<string, unknown>)?.url,
  );
}

export function isPlanSuperseded(messages: AssistantMessage[], messageIndex: number): boolean {
  for (let i = messageIndex + 1; i < messages.length; i++) {
    const m = messages[i];
    if (m.role === "user" && /approved.*slide plan/i.test(m.content ?? "")) {
      return true;
    }
    if (hasSuccessfulDeck(m.steps)) {
      return true;
    }
  }
  return false;
}

export function planAwaitingApproval(messages: AssistantMessage[], messageIndex: number): boolean {
  return Boolean(findPlanStep(messages[messageIndex]?.steps)) && !isPlanSuperseded(messages, messageIndex);
}

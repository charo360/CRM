"use client";

import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { orshotApi, type OrshotTemplateField } from "@/lib/api";

type Props = {
  open: boolean;
  onClose: () => void;
  templateId: number;
  initialModifications: Record<string, string>;
  /** Posts markdown into the chat (user message) with the new render. */
  onSendToChat: (markdown: string) => void;
};

function isImageField(f: OrshotTemplateField) {
  const t = (f.type || "").toLowerCase();
  return t.includes("image");
}

export function OrshotDesignEditModal({
  open,
  onClose,
  templateId,
  initialModifications,
  onSendToChat,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [fields, setFields] = useState<OrshotTemplateField[]>([]);
  const [templateName, setTemplateName] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setErr(null);
    setLoading(true);
    orshotApi
      .getTemplate(templateId)
      .then((res) => {
        if (cancelled) return;
        setFields(res.fields || []);
        setTemplateName(res.name || `Template ${templateId}`);
        const next: Record<string, string> = {};
        for (const f of res.fields || []) {
          const k = f.key || "";
          if (!k) continue;
          if (initialModifications[k] !== undefined) {
            next[k] = initialModifications[k];
          } else if (f.example != null && String(f.example)) {
            next[k] = String(f.example);
          } else {
            next[k] = "";
          }
        }
        setValues(next);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to load template");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, templateId, initialModifications]);

  async function handleRender() {
    setSaving(true);
    setErr(null);
    try {
      const mods: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(values)) {
        if (v.trim() !== "") mods[k] = v;
      }
      const r = await orshotApi.render({ template_id: templateId, modifications: mods });
      const url = r.image_url;
      if (!url) throw new Error("No image URL returned");
      const label = templateName || "Design";
      onSendToChat(`Here is the design after manual edits:\n\n![${label}](${url})`);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Render failed");
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/45 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="max-h-[min(90vh,720px)] w-full max-w-xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="orshot-edit-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 id="orshot-edit-title" className="text-lg font-semibold text-slate-900">
              Edit design
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Template #{templateId}
              {templateName ? ` · ${templateName}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>
        <p className="mb-4 text-[13px] leading-snug text-slate-600">
          Adjust text or image URLs, then <strong>Render and send to chat</strong>. That posts your update as the
          next message so you can keep iterating with the assistant.
        </p>
        {loading && (
          <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
            <Loader2 className="animate-spin" size={18} /> Loading fields…
          </div>
        )}
        {err && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{err}</p>}
        {!loading && fields.length > 0 && (
          <div className="space-y-3.5">
            {fields.map((f) => {
              const k = f.key || "";
              if (!k) return null;
              const img = isImageField(f);
              return (
                <label key={k} className="block">
                  <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    {k}
                    {f.page_number != null ? (
                      <span className="ml-1 font-normal normal-case text-slate-400">(page {f.page_number})</span>
                    ) : null}
                  </span>
                  {f.help_text ? (
                    <span className="mb-1 block text-[11px] text-slate-400">{f.help_text}</span>
                  ) : null}
                  {img ? (
                    <input
                      type="url"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-900 placeholder:text-slate-400"
                      placeholder="https://…"
                      value={values[k] ?? ""}
                      onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
                    />
                  ) : (
                    <textarea
                      className="w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-900 placeholder:text-slate-400"
                      rows={f.example && String(f.example).includes("\n") ? 4 : 2}
                      value={values[k] ?? ""}
                      onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
                    />
                  )}
                </label>
              );
            })}
            <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
              <button
                type="button"
                disabled={saving}
                onClick={() => void handleRender()}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-95 disabled:opacity-50"
              >
                {saving ? <Loader2 className="animate-spin" size={16} /> : null}
                Render and send to chat
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        {!loading && !err && fields.length === 0 && (
          <p className="py-4 text-sm text-slate-500">No editable fields returned for this template.</p>
        )}
      </div>
    </div>
  );
}

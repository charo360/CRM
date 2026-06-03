"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { api } from "@/lib/api";
import { WORLD_COUNTRIES, getCountryByCode } from "@/lib/worldCountries";
import { cn } from "@/lib/utils";

export type SmsFormValues = Record<string, string | boolean>;

type SchemaField = {
  key: string;
  label: string;
  type: string;
  required?: boolean;
  placeholder?: string;
  helpText?: string;
  options?: { value: string; label: string }[];
  rows?: number;
};

type ApplicationSchema = {
  country: string;
  region: string;
  regionLabel: string;
  notice: string;
  fields: SchemaField[];
};

const EMPTY_FORM: SmsFormValues = {
  business_country: "",
  business_name: "",
  sender_name: "",
  legal_business_name: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
  website: "",
  use_case: "",
  expected_volume: "under_1k",
  business_street: "",
  business_city: "",
  business_state: "",
  business_postal: "",
  tax_id: "",
  entity_type: "",
  message_flow: "",
  sample_message_1: "",
  sample_message_2: "",
  privacy_policy_url: "",
  terms_url: "",
  consent_description: "",
  gdpr_ack: false,
  business_registration_number: "",
};

const INPUT_CLASS =
  "w-full border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none transition-colors focus:border-brand";

function fieldSpansFullWidth(field: SchemaField) {
  return (
    field.type === "textarea" ||
    field.type === "country" ||
    field.type === "checkbox" ||
    field.key === "message_flow" ||
    field.key === "consent_description"
  );
}

type Props = {
  defaultCountry: string;
  prefill?: Partial<SmsFormValues>;
  submitting: boolean;
  onSubmit: (values: SmsFormValues) => void;
};

export function SmsApplicationForm({ defaultCountry, prefill, submitting, onSubmit }: Props) {
  const [values, setValues] = useState<SmsFormValues>({
    ...EMPTY_FORM,
    ...prefill,
    business_country: prefill?.business_country || defaultCountry || "",
  });
  const [schema, setSchema] = useState<ApplicationSchema | null>(null);
  const [loadingSchema, setLoadingSchema] = useState(false);

  useEffect(() => {
    if (!defaultCountry && !prefill) return;
    setValues((prev) => ({
      ...prev,
      ...prefill,
      business_country: prev.business_country || prefill?.business_country || defaultCountry || "",
    }));
  }, [defaultCountry, prefill]);

  const effectiveCountry = String(values.business_country || defaultCountry || "");

  const loadSchema = useCallback(async (country: string) => {
    setLoadingSchema(true);
    try {
      const q = country ? `?country=${encodeURIComponent(country)}` : "";
      const res = await api.get<ApplicationSchema>(`/sms-marketing/application/schema${q}`);
      setSchema(res);
    } catch {
      setSchema(null);
    } finally {
      setLoadingSchema(false);
    }
  }, []);

  useEffect(() => {
    void loadSchema(effectiveCountry);
  }, [effectiveCountry, loadSchema]);

  function setField(key: string, val: string | boolean) {
    setValues((prev) => ({ ...prev, [key]: val }));
  }

  function handleSubmit() {
    onSubmit({
      ...values,
      business_country: String(values.business_country || defaultCountry || ""),
    });
  }

  const fields = schema?.fields ?? [];

  function renderField(field: SchemaField) {
    const label = (
      <label className="block text-xs font-medium text-slate-700">
        {field.label}
        {field.required ? <span className="text-red-500"> *</span> : null}
      </label>
    );

    if (field.type === "country") {
      return (
        <div key={field.key} className="space-y-1 sm:col-span-2">
          {label}
          <select
            className={`${INPUT_CLASS} mt-0.5`}
            value={String(values.business_country || "")}
            onChange={(e) => setField("business_country", e.target.value)}
          >
            <option value="">Select country</option>
            {WORLD_COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
          {!values.business_country && defaultCountry ? (
            <p className="text-xs text-slate-400">
              Or use your account country ({getCountryByCode(defaultCountry)?.name || defaultCountry}) from
              Settings.
            </p>
          ) : null}
        </div>
      );
    }

    if (field.type === "checkbox") {
      return (
        <label
          key={field.key}
          className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-3 text-sm text-slate-700 sm:col-span-2"
        >
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-dark focus:ring-0"
            checked={Boolean(values[field.key])}
            onChange={(e) => setField(field.key, e.target.checked)}
          />
          <span>
            {field.label}
            {field.required ? <span className="text-red-500"> *</span> : null}
          </span>
        </label>
      );
    }

    if (field.type === "textarea") {
      return (
        <div key={field.key} className="space-y-1 sm:col-span-2">
          {label}
          <textarea
            className={`${INPUT_CLASS} mt-0.5 resize-none`}
            rows={field.rows ?? 3}
            placeholder={field.placeholder}
            value={String(values[field.key] ?? "")}
            onChange={(e) => setField(field.key, e.target.value)}
          />
          {field.helpText ? <p className="text-xs leading-relaxed text-slate-400">{field.helpText}</p> : null}
        </div>
      );
    }

    if (field.type === "select") {
      return (
        <div key={field.key} className="space-y-1">
          {label}
          <select
            className={`${INPUT_CLASS} mt-0.5`}
            value={String(values[field.key] ?? "")}
            onChange={(e) => setField(field.key, e.target.value)}
          >
            {!field.required ? <option value="">Select…</option> : null}
            {(field.options ?? []).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {field.helpText ? <p className="text-xs text-slate-400">{field.helpText}</p> : null}
        </div>
      );
    }

    const inputType =
      field.type === "email" ? "email" : field.type === "tel" ? "tel" : field.type === "url" ? "url" : "text";

    return (
      <div key={field.key} className={cn("space-y-1", fieldSpansFullWidth(field) && "sm:col-span-2")}>
        {label}
        <input
          type={inputType}
          className={cn(INPUT_CLASS, "mt-0.5", field.key === "sender_name" && "uppercase")}
          placeholder={field.placeholder}
          maxLength={field.key === "sender_name" ? 11 : undefined}
          value={String(values[field.key] ?? "")}
          onChange={(e) => setField(field.key, e.target.value)}
        />
        {field.helpText ? <p className="text-xs text-slate-400">{field.helpText}</p> : null}
      </div>
    );
  }

  return (
    <div className="w-full mx-auto space-y-4">
      {loadingSchema && !schema ? (
        <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin text-brand-dark" aria-hidden />
          Loading application form…
        </div>
      ) : null}

      {schema ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
          <p className="font-medium">{schema.regionLabel}</p>
          <p className="mt-1 leading-relaxed text-blue-800">{schema.notice}</p>
        </div>
      ) : null}

      {fields.length > 0 ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4 sm:p-5">
          <p className="mb-4 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Application details
          </p>
          <div className="grid gap-4 sm:grid-cols-2">{fields.map(renderField)}</div>
        </div>
      ) : null}

      <button
        type="button"
        disabled={submitting || loadingSchema || fields.length === 0}
        onClick={handleSubmit}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-brand-dark bg-brand-dark py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand hover:text-brand-ink disabled:opacity-50 sm:w-auto sm:min-w-[200px] sm:px-6"
      >
        {submitting ? (
          <>
            <Loader2 size={16} className="animate-spin" aria-hidden />
            Submitting…
          </>
        ) : (
          <>
            <Send size={16} aria-hidden />
            Submit application
          </>
        )}
      </button>
    </div>
  );
}

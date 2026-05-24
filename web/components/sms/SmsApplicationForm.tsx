"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
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

  return (
    <div className="grid gap-3 max-w-lg">
      {loadingSchema && !schema && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={14} className="animate-spin" /> Loading form…
        </div>
      )}

      {schema && (
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-900">
          <p className="font-medium">{schema.regionLabel}</p>
          <p className="text-blue-800 mt-0.5">{schema.notice}</p>
        </div>
      )}

      {fields.map((field) => {
        if (field.type === "country") {
          return (
            <div key={field.key}>
              <label className="text-sm font-medium text-slate-700">{field.label}{field.required ? " *" : ""}</label>
              <select
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                value={String(values.business_country || "")}
                onChange={(e) => setField("business_country", e.target.value)}
              >
                <option value="">Select country</option>
                {WORLD_COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </select>
              {!values.business_country && defaultCountry && (
                <p className="text-xs text-slate-400 mt-1">
                  Or use your account country ({getCountryByCode(defaultCountry)?.name || defaultCountry}) from Settings.
                </p>
              )}
            </div>
          );
        }

        if (field.type === "checkbox") {
          return (
            <label key={field.key} className="flex items-start gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="mt-1"
                checked={Boolean(values[field.key])}
                onChange={(e) => setField(field.key, e.target.checked)}
              />
              <span>{field.label}{field.required ? " *" : ""}</span>
            </label>
          );
        }

        if (field.type === "textarea") {
          return (
            <div key={field.key}>
              <label className="text-sm font-medium text-slate-700">{field.label}{field.required ? " *" : ""}</label>
              <textarea
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                rows={field.rows ?? 3}
                placeholder={field.placeholder}
                value={String(values[field.key] ?? "")}
                onChange={(e) => setField(field.key, e.target.value)}
              />
              {field.helpText && <p className="text-xs text-slate-400 mt-1">{field.helpText}</p>}
            </div>
          );
        }

        if (field.type === "select") {
          return (
            <div key={field.key}>
              <label className="text-sm font-medium text-slate-700">{field.label}{field.required ? " *" : ""}</label>
              <select
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                value={String(values[field.key] ?? "")}
                onChange={(e) => setField(field.key, e.target.value)}
              >
                {!field.required && <option value="">Select…</option>}
                {(field.options ?? []).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          );
        }

        const inputType = field.type === "email" ? "email" : field.type === "tel" ? "tel" : field.type === "url" ? "url" : "text";
        return (
          <div key={field.key}>
            <label className="text-sm font-medium text-slate-700">{field.label}{field.required ? " *" : ""}</label>
            <input
              type={inputType}
              className={cn("mt-1 w-full border rounded-lg px-3 py-2 text-sm", field.key === "sender_name" && "uppercase")}
              placeholder={field.placeholder}
              maxLength={field.key === "sender_name" ? 11 : undefined}
              value={String(values[field.key] ?? "")}
              onChange={(e) => setField(field.key, e.target.value)}
            />
            {field.helpText && <p className="text-xs text-slate-400 mt-1">{field.helpText}</p>}
          </div>
        );
      })}

      <button
        type="button"
        disabled={submitting || loadingSchema}
        onClick={handleSubmit}
        className="py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-dark disabled:opacity-50"
      >
        {submitting ? "Submitting…" : "Submit application"}
      </button>
    </div>
  );
}

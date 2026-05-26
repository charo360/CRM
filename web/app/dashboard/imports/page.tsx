"use client";

import { useState, useRef } from "react";
import { Upload, FileText, CheckCircle2, XCircle, Loader2, Download } from "lucide-react";
import { api } from "@/lib/api";

type ImportType = "customers" | "products";
type RowStatus = "success" | "error" | "pending";

interface ParsedRow {
  data: Record<string, string>;
  status: RowStatus;
  error?: string;
}

const IMPORT_CONFIGS = {
  customers: {
    label: "Customers",
    requiredFields: ["name", "phone_number"],
    optionalFields: ["email", "notes", "tags"],
    endpoint: "/customers",
    template: "name,phone_number,email,notes,tags\nJane Doe,+12025550100,jane@example.com,VIP customer,vip",
  },
  products: {
    label: "Products",
    requiredFields: ["name", "price"],
    optionalFields: ["description", "category"],
    endpoint: "/products",
    template: "name,price,description,category\nCoffee,250,Fresh brewed coffee,Beverages",
  },
};

export default function ImportsPage() {
  const [importType, setImportType] = useState<ImportType>("customers");
  const [rows, setRows] = useState<ParsedRow[]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);
  const [done, setDone] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const config = IMPORT_CONFIGS[importType];

  function handleFile(file: File) {
    setDone(false);
    setRows([]);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const lines = text.trim().split(/\r?\n/);
      if (lines.length < 2) return;
      const hdrs = lines[0].split(",").map((h) => h.trim().toLowerCase());
      setHeaders(hdrs);
      const parsed = lines.slice(1).map((line) => {
        const vals = line.split(",").map((v) => v.trim());
        const data: Record<string, string> = {};
        hdrs.forEach((h, i) => { data[h] = vals[i] || ""; });
        const missing = config.requiredFields.filter((f) => !data[f]);
        return {
          data,
          status: missing.length ? "error" : "pending",
          error: missing.length ? `Missing: ${missing.join(", ")}` : undefined,
        } as ParsedRow;
      });
      setRows(parsed);
    };
    reader.readAsText(file);
  }

  async function runImport() {
    const validRows = rows.filter((r) => r.status !== "error");
    if (!validRows.length) return;
    setImporting(true);

    const updated = [...rows];
    for (let i = 0; i < updated.length; i++) {
      if (updated[i].status === "error") continue;
      try {
        const body: Record<string, unknown> = { ...updated[i].data };
        if (importType === "products") body.price = parseFloat(body.price as string) || 0;
        await api.post(config.endpoint, body);
        updated[i] = { ...updated[i], status: "success" };
      } catch (err: unknown) {
        updated[i] = {
          ...updated[i],
          status: "error",
          error: err instanceof Error ? err.message : "Failed",
        };
      }
      setRows([...updated]);
    }
    setImporting(false);
    setDone(true);
  }

  function downloadTemplate() {
    const blob = new Blob([config.template], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${importType}-template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const successCount = rows.filter((r) => r.status === "success").length;
  const errorCount = rows.filter((r) => r.status === "error").length;
  const pendingCount = rows.filter((r) => r.status === "pending").length;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Imports</h1>
        <p className="text-slate-500 text-sm mt-1">Bulk import customers or products from a CSV file</p>
      </div>

      {/* Type selector */}
      <div className="flex gap-3">
        {(["customers", "products"] as ImportType[]).map((t) => (
          <button
            key={t}
            onClick={() => { setImportType(t); setRows([]); setDone(false); }}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
              importType === t
                ? "bg-brand-dark text-white"
                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {IMPORT_CONFIGS[t].label}
          </button>
        ))}
      </div>

      {/* Drop zone */}
      {rows.length === 0 && (
        <div
          className="border-2 border-dashed border-slate-300 rounded-2xl p-10 flex flex-col items-center gap-4 cursor-pointer hover:border-brand hover:bg-brand/5 transition-colors"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
          }}
        >
          <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center">
            <Upload size={24} className="text-slate-500" />
          </div>
          <div className="text-center">
            <p className="font-semibold text-slate-700">Drop your CSV here or click to browse</p>
            <p className="text-sm text-slate-400 mt-1">
              Required columns:{" "}
              <span className="font-mono text-xs">{config.requiredFields.join(", ")}</span>
            </p>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); downloadTemplate(); }}
            className="flex items-center gap-1.5 text-sm text-brand-dark hover:underline"
          >
            <Download size={14} /> Download template
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
        </div>
      )}

      {/* Preview table */}
      {rows.length > 0 && (
        <div className="space-y-4">
          {/* Summary bar */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex gap-4 text-sm">
              <span className="text-slate-600">{rows.length} rows</span>
              {successCount > 0 && <span className="text-green-600 font-medium">✓ {successCount} imported</span>}
              {errorCount > 0 && <span className="text-red-600 font-medium">✗ {errorCount} errors</span>}
              {pendingCount > 0 && <span className="text-slate-500">{pendingCount} ready</span>}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => { setRows([]); setDone(false); if (fileRef.current) fileRef.current.value = ""; }}
                className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50"
              >
                Clear
              </button>
              {!done && pendingCount > 0 && (
                <button
                  onClick={runImport}
                  disabled={importing}
                  className="flex items-center gap-2 px-4 py-1.5 text-sm bg-brand-dark text-white rounded-lg font-medium hover:bg-brand disabled:opacity-60"
                >
                  {importing && <Loader2 size={14} className="animate-spin" />}
                  {importing ? "Importing…" : `Import ${pendingCount} rows`}
                </button>
              )}
              {done && (
                <span className="flex items-center gap-1.5 text-sm text-green-700 font-medium">
                  <CheckCircle2 size={16} /> Import complete
                </span>
              )}
            </div>
          </div>

          {/* Table */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase w-8">#</th>
                    {headers.map((h) => (
                      <th key={h} className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase">{h}</th>
                    ))}
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.slice(0, 50).map((row, i) => (
                    <tr key={i} className={row.status === "error" ? "bg-red-50" : row.status === "success" ? "bg-green-50" : ""}>
                      <td className="px-4 py-2.5 text-slate-400">{i + 1}</td>
                      {headers.map((h) => (
                        <td key={h} className="px-4 py-2.5 text-slate-700">{row.data[h] || "—"}</td>
                      ))}
                      <td className="px-4 py-2.5">
                        {row.status === "success" && (
                          <span className="flex items-center gap-1 text-green-700"><CheckCircle2 size={13} /> Imported</span>
                        )}
                        {row.status === "error" && (
                          <span className="flex items-center gap-1 text-red-600"><XCircle size={13} /> {row.error}</span>
                        )}
                        {row.status === "pending" && (
                          <span className="flex items-center gap-1 text-slate-400"><FileText size={13} /> Ready</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length > 50 && (
                <p className="px-4 py-2 text-xs text-slate-400 border-t border-slate-100">
                  Showing first 50 of {rows.length} rows
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

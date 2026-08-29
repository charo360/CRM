"use client";

import { useCallback, useEffect, useState } from "react";
import { adminApi, type AdminWhatsAppConnection } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import {
  Activity,
  CheckCircle2,
  MessageCircle,
  RefreshCw,
  Server,
  WifiOff,
} from "lucide-react";

function StatusBadge({ status, connected }: Pick<AdminWhatsAppConnection, "status" | "connected">) {
  const normalized = status.toLowerCase();
  const className = connected
    ? "bg-emerald-100 text-emerald-700"
    : ["pending", "pairing", "qr_ready", "qr_pending", "starting"].includes(normalized)
      ? "bg-amber-100 text-amber-800"
      : "bg-rose-100 text-rose-700";
  const label = connected ? "Connected" : normalized.replaceAll("_", " ") || "Pending";

  return <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-medium capitalize ${className}`}>{label}</span>;
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">{label}</p>
          <p className="text-3xl font-bold text-slate-900 mt-1">{value}</p>
        </div>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon size={18} />
        </div>
      </div>
    </div>
  );
}

export default function AdminWhatsAppPage() {
  const [connections, setConnections] = useState<AdminWhatsAppConnection[]>([]);
  const [provider, setProvider] = useState("WAHA");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const loadConnections = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const data = await adminApi.listWhatsAppConnections();
      setConnections(data.connections || []);
      setProvider((data.provider || "WAHA").toUpperCase());
      setLastUpdated(data.refreshed_at || new Date().toISOString());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load WhatsApp connection status.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadConnections();
    const refreshTimer = window.setInterval(() => void loadConnections(), 30_000);
    return () => window.clearInterval(refreshTimer);
  }, [loadConnections]);

  const connected = connections.filter((connection) => connection.connected).length;
  const needsAttention = connections.length - connected;

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <MessageCircle size={19} className="text-emerald-600" />
            <h1 className="text-xl font-bold text-slate-900">WhatsApp connections</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">Live, read-only connection health for every business using {provider}.</p>
        </div>
        <button
          onClick={() => void loadConnections(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-2 h-9 px-3 rounded-lg bg-white border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Businesses linked" value={loading ? "—" : connections.length} icon={MessageCircle} color="bg-indigo-100 text-indigo-700" />
        <StatCard label="Connected now" value={loading ? "—" : connected} icon={CheckCircle2} color="bg-emerald-100 text-emerald-700" />
        <StatCard label="Need attention" value={loading ? "—" : needsAttention} icon={WifiOff} color="bg-rose-100 text-rose-700" />
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Activity size={15} className="text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-800">Connection status</h2>
          </div>
          <p className="text-xs text-slate-400">Refreshes every 30 seconds{lastUpdated ? ` · Updated ${formatDateTime(lastUpdated)}` : ""}</p>
        </div>

        {error ? (
          <div className="m-5 p-3 rounded-lg bg-rose-50 border border-rose-100 text-sm text-rose-700">{error}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-sm">
              <thead className="bg-slate-50">
                <tr>
                  {["Business", "WhatsApp number", "Status", "Session", "Node", "Last change"].map((heading) => (
                    <th key={heading} className="px-4 py-2.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading ? (
                  Array.from({ length: 4 }).map((_, row) => (
                    <tr key={row}>
                      {Array.from({ length: 6 }).map((__, column) => (
                        <td key={column} className="px-4 py-3"><div className="h-3 bg-slate-100 rounded animate-pulse" /></td>
                      ))}
                    </tr>
                  ))
                ) : connections.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">No WhatsApp connections have been created yet.</td>
                  </tr>
                ) : (
                  connections.map((connection) => (
                    <tr key={connection.business_id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-800">{connection.business_name}</p>
                        <p className="text-xs text-slate-400 mt-0.5">{connection.owner_name || connection.email || "—"}</p>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{connection.whatsapp_number || connection.account_phone || "—"}</td>
                      <td className="px-4 py-3"><StatusBadge status={connection.status} connected={connection.connected} /></td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-500">{connection.session_name || "—"}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1 text-xs text-slate-500"><Server size={12} />{connection.node === null ? "—" : `WAHA ${connection.node + 1}`}</span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">{connection.last_change_at ? formatDateTime(connection.last_change_at) : "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

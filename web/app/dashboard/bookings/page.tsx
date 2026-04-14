"use client";

import { useEffect, useState } from "react";
import { bookingsApi, Booking } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { Calendar, Clock, CheckCircle2, XCircle, Loader2, ChevronDown } from "lucide-react";

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  pending:   { label: "Pending",   color: "bg-amber-100 text-amber-700" },
  confirmed: { label: "Confirmed", color: "bg-blue-100 text-blue-700" },
  completed: { label: "Completed", color: "bg-green-100 text-green-700" },
  cancelled: { label: "Cancelled", color: "bg-red-100 text-red-600" },
  no_show:   { label: "No Show",   color: "bg-slate-100 text-slate-500" },
};

const PAYMENT_COLORS: Record<string, string> = {
  paid:    "bg-green-100 text-green-700",
  partial: "bg-blue-100 text-blue-700",
  unpaid:  "bg-amber-100 text-amber-700",
};

const STATUS_FILTERS = ["All", "pending", "confirmed", "completed", "cancelled"];

export default function BookingsPage() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("All");
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try { setBookings(await bookingsApi.list()); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function updateStatus(id: string, status: string) {
    setUpdatingId(id);
    try { await bookingsApi.update(id, { status: status as Booking["status"] }); await load(); }
    finally { setUpdatingId(null); }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this booking?")) return;
    await bookingsApi.delete(id);
    await load();
  }

  const filtered = bookings.filter(
    (b) => statusFilter === "All" || b.status === statusFilter
  );

  const totalRevenue = bookings
    .filter((b) => b.payment_status === "paid")
    .reduce((s, b) => s + (b.total_price || b.price), 0);

  const todayStr = new Date().toISOString().split("T")[0];
  const todayCount = bookings.filter((b) => b.date === todayStr).length;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Bookings</h1>
        <p className="text-slate-500 text-sm mt-1">
          {bookings.length} total · {todayCount} today · {formatCurrency(totalRevenue)} collected
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => {
          const count = bookings.filter((b) => b.status === key).length;
          return (
            <button
              key={key}
              onClick={() => setStatusFilter(statusFilter === key ? "All" : key)}
              className={`rounded-xl border p-3 text-left transition-colors hover:shadow-sm ${
                statusFilter === key ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white"
              }`}
            >
              <p className="text-xl font-bold text-slate-900">{count}</p>
              <p className="text-xs text-slate-500 mt-0.5">{cfg.label}</p>
            </button>
          );
        })}
      </div>

      {/* Filter */}
      <div className="relative w-48">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="w-full appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-slate-700">
          {STATUS_FILTERS.map((s) => <option key={s}>{s}</option>)}
        </select>
        <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {["Booking #", "Customer", "Service", "Staff", "Date & Time", "Price", "Status", "Payment", "Actions"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}>{Array.from({ length: 9 }).map((_, j) => (
                      <td key={j} className="px-4 py-3"><div className="h-4 bg-slate-100 rounded animate-pulse" /></td>
                    ))}</tr>
                  ))
                : filtered.map((b) => {
                    const sc = STATUS_CONFIG[b.status] || STATUS_CONFIG.pending;
                    const pc = PAYMENT_COLORS[b.payment_status] || PAYMENT_COLORS.unpaid;
                    const isUpdating = updatingId === b.id;
                    return (
                      <tr key={b.id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-mono text-xs text-slate-700">#{b.booking_number}</td>
                        <td className="px-4 py-3">
                          <p className="font-medium text-slate-800">{b.customer_name}</p>
                          {b.customer_phone && <p className="text-xs text-slate-400">{b.customer_phone}</p>}
                        </td>
                        <td className="px-4 py-3 text-slate-700">{b.service_name}</td>
                        <td className="px-4 py-3 text-slate-600 text-xs">{b.staff_name || "—"}</td>
                        <td className="px-4 py-3">
                          <p className="text-slate-800 font-medium">{formatDate(b.date)}</p>
                          <p className="text-xs text-slate-400 flex items-center gap-1"><Clock size={10} />{b.time}</p>
                        </td>
                        <td className="px-4 py-3 font-semibold text-slate-900">
                          {formatCurrency(b.total_price || b.price)}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sc.color}`}>{sc.label}</span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${pc}`}>{b.payment_status}</span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1">
                            {b.status === "pending" && (
                              <button onClick={() => updateStatus(b.id, "confirmed")} disabled={isUpdating}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-green-100 hover:text-green-700 transition-colors" title="Confirm">
                                {isUpdating ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
                              </button>
                            )}
                            {["pending", "confirmed"].includes(b.status) && (
                              <button onClick={() => updateStatus(b.id, "cancelled")} disabled={isUpdating}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600 transition-colors" title="Cancel">
                                <XCircle size={13} />
                              </button>
                            )}
                            {b.status === "confirmed" && (
                              <button onClick={() => updateStatus(b.id, "completed")} disabled={isUpdating}
                                className="px-2 py-1 text-xs bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors">
                                Complete
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <div className="flex flex-col items-center py-16 gap-3 text-slate-400">
              <Calendar size={36} />
              <p className="text-sm">No bookings found</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

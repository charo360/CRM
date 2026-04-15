"use client";

import { useEffect, useState } from "react";
import {
  bookingsApi,
  Booking,
  customersApi,
  productsApi,
  type BookingCreatePayload,
  type Customer,
  type Product,
} from "@/lib/api";
import { formatCurrency, formatDateSafe } from "@/lib/utils";
import {
  Calendar,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  ChevronDown,
  Bell,
  RefreshCw,
  Search,
  Trash2,
  UserX,
  Plus,
  X,
} from "lucide-react";
import { useBusiness } from "@/contexts/BusinessContext";

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

const STATUS_FILTERS = ["All", "pending", "confirmed", "completed", "cancelled", "no_show"];

/** YYYY-MM-DD for “today” stats — prefers `date`, then check-in (rental / WhatsApp rows). */
function bookingCalendarDay(b: Booking): string {
  const raw = (b.date || "").trim();
  if (raw) return raw.length >= 10 ? raw.slice(0, 10) : raw;
  const ci = b.checkin_date;
  if (ci != null && String(ci).trim() !== "") {
    const s = String(ci).trim();
    return s.length >= 10 ? s.slice(0, 10) : s;
  }
  return "";
}

function localDateStr(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function BookingsPage() {
  const { bookingsNavLabel, businessType } = useBusiness();
  const reservationMode = bookingsNavLabel === "Reservations";
  const singular = reservationMode ? "reservation" : "booking";
  const pluralLower = reservationMode ? "reservations" : "bookings";
  const guestOrCustomer = reservationMode ? "Guest" : "Customer";
  const serviceColumnLabel =
    !reservationMode ? "Service" : businessType === "hotel" ? "Room / package" : "Table / service";
  /** Match mobile: hotels & property rentals use check-in/out; restaurants keep date + time. */
  const showCheckinCheckout = businessType === "hotel" || businessType === "rental";

  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [remindingId, setRemindingId] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [custSearch, setCustSearch] = useState("");
  const [walkIn, setWalkIn] = useState(false);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [serviceId, setServiceId] = useState<string>("");
  const [manualServiceName, setManualServiceName] = useState("");
  const [date, setDate] = useState(localDateStr());
  const [time, setTime] = useState("09:00");
  const [checkin, setCheckin] = useState("");
  const [checkout, setCheckout] = useState("");
  const [staffName, setStaffName] = useState("");
  const [notes, setNotes] = useState("");
  const [priceInput, setPriceInput] = useState<string>("");

  useEffect(() => {
    if (!createOpen) return;
    let cancelled = false;
    (async () => {
      try {
        const [c, p] = await Promise.all([customersApi.list(), productsApi.list()]);
        if (!cancelled) {
          setCustomers(c);
          setProducts(p);
        }
      } catch {
        if (!cancelled) {
          setCustomers([]);
          setProducts([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [createOpen]);

  useEffect(() => {
    if (!createOpen) return;
    setWalkIn(false);
    setSelectedCustomerId(null);
    setCustSearch("");
    setServiceId("");
    setManualServiceName("");
    setDate(localDateStr());
    setTime("09:00");
    setCheckin("");
    setCheckout("");
    setStaffName("");
    setNotes("");
    setPriceInput("");
  }, [createOpen]);

  useEffect(() => {
    if (!createOpen || !serviceId || serviceId === "manual") return;
    const p = products.find((x) => x.id === serviceId);
    if (p) setPriceInput(String(p.price ?? ""));
  }, [createOpen, serviceId, products]);

  async function load(showSkeleton = true) {
    if (showSkeleton) setLoading(true);
    try {
      setBookings(await bookingsApi.list());
    } finally {
      if (showSkeleton) setLoading(false);
    }
  }

  useEffect(() => {
    load(true);
  }, []);

  async function updateStatus(id: string, status: string) {
    setUpdatingId(id);
    try {
      const updated = await bookingsApi.update(id, { status: status as Booking["status"] });
      setBookings((prev) => prev.map((b) => (b.id === id ? updated : b)));
    } catch (e) {
      alert(e instanceof Error ? e.message : `Failed to update ${singular}`);
      await load(false);
    } finally {
      setUpdatingId(null);
    }
  }

  async function updatePaymentStatus(id: string, payment_status: Booking["payment_status"]) {
    setUpdatingId(id);
    try {
      const updated = await bookingsApi.update(id, { payment_status });
      setBookings((prev) => prev.map((b) => (b.id === id ? updated : b)));
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to update payment");
      await load(false);
    } finally {
      setUpdatingId(null);
    }
  }

  async function sendReminder(id: string) {
    setRemindingId(id);
    try {
      await bookingsApi.sendReminder(id);
      alert("Reminder sent!");
    } catch {
      alert("Failed to send reminder");
    } finally {
      setRemindingId(null);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm(`Delete this ${singular}? This cannot be undone.`)) return;
    setUpdatingId(id);
    try {
      await bookingsApi.delete(id);
      setBookings((prev) => prev.filter((b) => b.id !== id));
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleCreateBooking() {
    if (!walkIn && !selectedCustomerId) {
      alert(`Select a ${guestOrCustomer.toLowerCase()} or mark walk-in.`);
      return;
    }
    const isManual = serviceId === "manual";
    const hasCatalog = Boolean(serviceId && serviceId !== "manual");
    if (!isManual && !hasCatalog) {
      alert(`Select a ${serviceColumnLabel.toLowerCase()} or use custom.`);
      return;
    }
    if (isManual && !manualServiceName.trim()) {
      alert("Enter a name for the custom service.");
      return;
    }
    if (showCheckinCheckout) {
      if (!checkin.trim() || !checkout.trim()) {
        alert("Set check-in and check-out dates.");
        return;
      }
    } else if (!date.trim() || !time.trim()) {
      alert("Set date and time.");
      return;
    }

    const catalogProduct = hasCatalog ? products.find((p) => p.id === serviceId) : undefined;
    let priceNum = parseFloat(priceInput.replace(/,/g, ""));
    if (Number.isNaN(priceNum)) priceNum = 0;
    if (priceNum === 0 && catalogProduct) priceNum = catalogProduct.price ?? 0;

    const payload: BookingCreatePayload = {
      date: showCheckinCheckout ? checkin.trim() : date.trim(),
      time: showCheckinCheckout ? "00:00" : time.trim(),
      price: priceNum,
      ...(notes.trim() ? { notes: notes.trim() } : {}),
      ...(staffName.trim() ? { staff_name: staffName.trim() } : {}),
    };
    if (hasCatalog) {
      payload.service_id = serviceId;
    } else {
      payload.service_id = "";
      payload.service_name = manualServiceName.trim();
    }
    if (walkIn) {
      payload.customer_name = "Walk-in Customer";
    } else if (selectedCustomerId) {
      payload.customer_id = selectedCustomerId;
    }
    if (showCheckinCheckout) {
      payload.checkin_date = checkin.trim();
      payload.checkout_date = checkout.trim();
    }

    setCreateLoading(true);
    try {
      const created = await bookingsApi.create(payload);
      setBookings((prev) => [created, ...prev]);
      setCreateOpen(false);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to create");
    } finally {
      setCreateLoading(false);
    }
  }

  const filtered = bookings.filter((b) => {
    const matchStatus = statusFilter === "All" || b.status === statusFilter;
    const q = search.trim().toLowerCase();
    const matchSearch =
      !q ||
      b.customer_name.toLowerCase().includes(q) ||
      (b.customer_phone || "").toLowerCase().includes(q) ||
      String(b.booking_number).toLowerCase().includes(q) ||
      b.service_name.toLowerCase().includes(q);
    return matchStatus && matchSearch;
  });

  const totalRevenue = bookings
    .filter((b) => b.payment_status === "paid")
    .reduce((s, b) => s + (b.total_price || b.price), 0);

  const todayStr = new Date().toISOString().split("T")[0];
  const todayCount = bookings.filter((b) => bookingCalendarDay(b) === todayStr).length;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{bookingsNavLabel}</h1>
          <p className="text-slate-500 text-sm mt-1">
            {bookings.length} total · {todayCount} today · {formatCurrency(totalRevenue)} collected
          </p>
        </div>
        <div className="flex flex-wrap gap-2 self-start">
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm"
          >
            <Plus size={16} />
            New {singular}
          </button>
          <button
            type="button"
            onClick={() => load(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => {
          const count = bookings.filter((b) => b.status === key).length;
          return (
            <button
              type="button"
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

      {/* Search + filter */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={
              reservationMode
                ? businessType === "hotel"
                  ? "Search guest, phone, reservation #, room…"
                  : "Search name, phone, reservation #, table or service…"
                : "Search name, phone, booking #, service…"
            }
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="relative w-full sm:w-48">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full appearance-none pl-3 pr-8 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-slate-700"
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {s === "All" ? "All statuses" : STATUS_CONFIG[s]?.label ?? s}
              </option>
            ))}
          </select>
          <ChevronDown
            size={13}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                {[
                  reservationMode ? "Reservation #" : "Booking #",
                  reservationMode ? "Guest" : "Customer",
                  serviceColumnLabel,
                  "Staff",
                  "Date & Time",
                  "Price",
                  "Status",
                  "Payment",
                  "Actions",
                ].map((h) => (
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
                          {b.checkin_date && b.checkout_date ? (
                            <>
                              <p className="text-slate-800 font-medium">
                                {formatDateSafe(b.checkin_date)} → {formatDateSafe(b.checkout_date)}
                              </p>
                              {typeof b.nights === "number" && b.nights > 0 ? (
                                <p className="text-xs text-slate-400">
                                  {b.nights} night{b.nights !== 1 ? "s" : ""}
                                </p>
                              ) : (
                                <p className="text-xs text-slate-400 flex items-center gap-1">
                                  <Clock size={10} />
                                  {b.time}
                                </p>
                              )}
                            </>
                          ) : (
                            <>
                              <p className="text-slate-800 font-medium">{formatDateSafe(b.date)}</p>
                              <p className="text-xs text-slate-400 flex items-center gap-1">
                                <Clock size={10} />
                                {b.time}
                              </p>
                            </>
                          )}
                        </td>
                        <td className="px-4 py-3 font-semibold text-slate-900">
                          {formatCurrency(b.total_price || b.price)}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sc.color}`}>{sc.label}</span>
                        </td>
                        <td className="px-4 py-3 min-w-[120px]">
                          <label className="sr-only">Payment status</label>
                          <select
                            aria-label={`Payment for booking ${b.booking_number}`}
                            value={b.payment_status || "unpaid"}
                            disabled={isUpdating}
                            onChange={(e) =>
                              void updatePaymentStatus(b.id, e.target.value as Booking["payment_status"])
                            }
                            className={`w-full max-w-[130px] text-xs font-medium capitalize rounded-lg border border-slate-200 px-2 py-1.5 pr-6 bg-white cursor-pointer focus:ring-2 focus:ring-indigo-500 focus:border-indigo-400 outline-none disabled:opacity-50 disabled:cursor-wait ${pc}`}
                          >
                            <option value="unpaid">Unpaid</option>
                            <option value="partial">Partial</option>
                            <option value="paid">Paid</option>
                          </select>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1">
                            {b.status === "pending" && (
                              <button type="button" onClick={() => updateStatus(b.id, "confirmed")} disabled={isUpdating}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-green-100 hover:text-green-700 transition-colors" title="Confirm">
                                {isUpdating ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
                              </button>
                            )}
                            {["pending", "confirmed"].includes(b.status) && (
                              <button type="button" onClick={() => updateStatus(b.id, "cancelled")} disabled={isUpdating}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-red-100 hover:text-red-600 transition-colors disabled:opacity-50" title="Cancel">
                                {isUpdating ? <Loader2 size={13} className="animate-spin" /> : <XCircle size={13} />}
                              </button>
                            )}
                            {["pending", "confirmed"].includes(b.status) && (
                              <button
                                type="button"
                                onClick={() => updateStatus(b.id, "no_show")}
                                disabled={isUpdating}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors disabled:opacity-50"
                                title="Mark no-show"
                              >
                                {isUpdating ? <Loader2 size={13} className="animate-spin" /> : <UserX size={13} />}
                              </button>
                            )}
                            {b.status === "confirmed" && (
                              <button type="button" onClick={() => updateStatus(b.id, "completed")} disabled={isUpdating}
                                className="px-2 py-1 text-xs bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 inline-flex items-center gap-1">
                                {isUpdating ? <Loader2 size={12} className="animate-spin" /> : null}
                                Complete
                              </button>
                            )}
                            {["pending", "confirmed"].includes(b.status) && (
                              <button type="button" onClick={() => sendReminder(b.id)} disabled={remindingId === b.id}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-amber-100 hover:text-amber-600 transition-colors" title="Send reminder">
                                {remindingId === b.id ? <Loader2 size={13} className="animate-spin" /> : <Bell size={13} />}
                              </button>
                            )}
                            {["cancelled", "completed", "no_show"].includes(b.status) && (
                              <button
                                type="button"
                                onClick={() => handleDelete(b.id)}
                                disabled={isUpdating}
                                className="p-1.5 rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors disabled:opacity-50"
                                title={`Delete ${singular}`}
                              >
                                {isUpdating ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
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
              <p className="text-sm">No {pluralLower} found</p>
            </div>
          )}
        </div>
      </div>

      {createOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="new-booking-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) setCreateOpen(false);
          }}
        >
          <div
            className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] flex flex-col overflow-hidden border border-slate-200"
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-100 shrink-0">
              <h2 id="new-booking-title" className="text-lg font-semibold text-slate-900">
                New {singular}
              </h2>
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="p-2 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4 text-sm flex-1 min-h-0 overflow-y-auto overscroll-y-contain">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">{guestOrCustomer}</p>
                <label className="flex items-center gap-2 mb-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={walkIn}
                    onChange={(e) => {
                      setWalkIn(e.target.checked);
                      if (e.target.checked) setSelectedCustomerId(null);
                    }}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-slate-700">Walk-in (no saved contact)</span>
                </label>
                {!walkIn &&
                  (() => {
                    const selectedCustomer = customers.find(
                      (c) => String(c.id) === String(selectedCustomerId ?? "")
                    );
                    const filtered = customers
                      .filter((c) => {
                        const q = custSearch.trim().toLowerCase();
                        if (!q) return true;
                        return (
                          c.name.toLowerCase().includes(q) ||
                          (c.phone_number || "").toLowerCase().includes(q)
                        );
                      })
                      .slice(0, 100);

                    if (selectedCustomerId) {
                      return (
                        <div className="rounded-xl border border-indigo-200 bg-indigo-50/90 px-3 py-3 flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700 mb-0.5">
                              Selected {guestOrCustomer}
                            </p>
                            {selectedCustomer ? (
                              <>
                                <p className="font-semibold text-slate-900 truncate">{selectedCustomer.name}</p>
                                {selectedCustomer.phone_number && (
                                  <p className="text-xs text-slate-600 mt-0.5">{selectedCustomer.phone_number}</p>
                                )}
                              </>
                            ) : (
                              <p className="text-sm text-slate-600">Customer #{selectedCustomerId}</p>
                            )}
                          </div>
                          <button
                            type="button"
                            onClick={() => setSelectedCustomerId(null)}
                            className="shrink-0 text-sm font-medium text-indigo-700 hover:text-indigo-900 px-2 py-1 rounded-lg hover:bg-indigo-100/80 touch-manipulation"
                          >
                            Change
                          </button>
                        </div>
                      );
                    }

                    return (
                      <>
                        <input
                          type="search"
                          placeholder={`Search ${guestOrCustomer.toLowerCase()}s…`}
                          value={custSearch}
                          onChange={(e) => setCustSearch(e.target.value)}
                          className="w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 mb-2"
                        />
                        <div
                          className="max-h-44 overflow-y-auto overscroll-y-contain rounded-lg border border-slate-200 bg-slate-50/50 divide-y divide-slate-200/80 touch-pan-y"
                          style={{ WebkitOverflowScrolling: "touch" }}
                        >
                          {filtered.length === 0 ? (
                            <p className="px-3 py-4 text-xs text-slate-500 text-center">No matches</p>
                          ) : (
                            filtered.map((c) => {
                              const cid = String(c.id);
                              return (
                                <button
                                  key={cid}
                                  type="button"
                                  onClick={(e) => {
                                    e.preventDefault();
                                    setSelectedCustomerId(cid);
                                  }}
                                  className="w-full text-left px-3 py-2.5 min-h-[44px] touch-manipulation select-none hover:bg-white active:bg-indigo-50/80"
                                >
                                  <span className="font-medium text-slate-800">{c.name}</span>
                                  {c.phone_number && (
                                    <span className="block text-xs text-slate-500">{c.phone_number}</span>
                                  )}
                                </button>
                              );
                            })
                          )}
                        </div>
                      </>
                    );
                  })()}
              </div>

              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">{serviceColumnLabel}</p>
                <div className="flex flex-wrap gap-2 mb-2">
                  {products.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => {
                        setServiceId(p.id);
                        setManualServiceName("");
                      }}
                      className={`px-2.5 py-1 rounded-lg text-xs border transition-colors ${
                        serviceId === p.id
                          ? "border-indigo-500 bg-indigo-50 text-indigo-800"
                          : "border-slate-200 text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {p.name}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setServiceId("manual")}
                    className={`px-2.5 py-1 rounded-lg text-xs border transition-colors ${
                      serviceId === "manual"
                        ? "border-indigo-500 bg-indigo-50 text-indigo-800"
                        : "border-dashed border-slate-300 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    Custom…
                  </button>
                </div>
                {serviceId === "manual" && (
                  <input
                    type="text"
                    placeholder="Service name"
                    value={manualServiceName}
                    onChange={(e) => setManualServiceName(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                )}
              </div>

              {showCheckinCheckout ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">Check-in</span>
                    <input
                      type="date"
                      value={checkin}
                      onChange={(e) => setCheckin(e.target.value)}
                      className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">Check-out</span>
                    <input
                      type="date"
                      value={checkout}
                      onChange={(e) => setCheckout(e.target.value)}
                      className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg"
                    />
                  </label>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">Date</span>
                    <input
                      type="date"
                      value={date}
                      onChange={(e) => setDate(e.target.value)}
                      className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-slate-500">Time</span>
                    <input
                      type="time"
                      value={time}
                      onChange={(e) => setTime(e.target.value)}
                      className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg"
                    />
                  </label>
                </div>
              )}

              <label className="block">
                <span className="text-xs font-medium text-slate-500">Staff (optional)</span>
                <input
                  type="text"
                  value={staffName}
                  onChange={(e) => setStaffName(e.target.value)}
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Name"
                />
              </label>

              <label className="block">
                <span className="text-xs font-medium text-slate-500">Price ({singular})</span>
                <input
                  type="text"
                  inputMode="decimal"
                  value={priceInput}
                  onChange={(e) => setPriceInput(e.target.value)}
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="0"
                />
              </label>

              <label className="block">
                <span className="text-xs font-medium text-slate-500">Notes (optional)</span>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                  className="mt-1 w-full px-3 py-2 border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </label>
            </div>

            <div className="flex justify-end gap-2 px-5 py-4 border-t border-slate-100 bg-slate-50/80 rounded-b-xl shrink-0">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={createLoading}
                onClick={() => void handleCreateBooking()}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {createLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ChefHat, Clock, Truck, UtensilsCrossed, ShoppingBag, Check, Loader2, RefreshCw } from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────────
interface KdsItem {
  product_name?: string;
  name?: string;
  quantity: number;
  modifiers?: string[];
}

interface KdsOrder {
  id: string;
  order_number: string | number;
  customer_name: string;
  fulfillment_status: string;
  delivery_type: string;
  table_number: string;
  delivery_address: string;
  assigned_to: string;
  notes: string;
  items: KdsItem[];
  total_amount: number;
  elapsed_seconds: number;
  created_at: string;
}

// ── Status config ──────────────────────────────────────────────────────────────
const STATUSES = ["New", "Confirmed", "Preparing", "Ready"] as const;
type Status = (typeof STATUSES)[number];

const STATUS_CONFIG: Record<Status, { bg: string; border: string; badge: string; next: string | null; nextLabel: string }> = {
  New:       { bg: "bg-red-50",    border: "border-red-400",    badge: "bg-red-500 text-white",      next: "Confirmed", nextLabel: "Confirm" },
  Confirmed: { bg: "bg-orange-50", border: "border-orange-400", badge: "bg-orange-500 text-white",   next: "Preparing", nextLabel: "Start Preparing" },
  Preparing: { bg: "bg-yellow-50", border: "border-yellow-400", badge: "bg-yellow-500 text-white",   next: "Ready",     nextLabel: "Mark Ready" },
  Ready:     { bg: "bg-green-50",  border: "border-green-400",  badge: "bg-green-600 text-white",    next: "Done",      nextLabel: "Done ✓" },
};

const COLUMN_HEADERS: Record<Status, { label: string; color: string }> = {
  New:       { label: "🔴 New",       color: "bg-red-500" },
  Confirmed: { label: "🟠 Confirmed", color: "bg-orange-500" },
  Preparing: { label: "🟡 Preparing", color: "bg-yellow-500" },
  Ready:     { label: "🟢 Ready",     color: "bg-green-600" },
};

// ── Elapsed time helper ────────────────────────────────────────────────────────
function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${s}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

function elapsedColor(seconds: number): string {
  if (seconds > 1800) return "text-red-600 font-bold";
  if (seconds > 900)  return "text-orange-600 font-semibold";
  return "text-slate-500";
}

// ── API ────────────────────────────────────────────────────────────────────────
const API = process.env.NEXT_PUBLIC_API_URL || "/api";

async function fetchOrders(businessId: string, pin: string): Promise<KdsOrder[]> {
  const res = await fetch(`${API}/kds/${businessId}/orders?pin=${encodeURIComponent(pin)}`);
  if (res.status === 401) throw new Error("invalid_pin");
  if (!res.ok) throw new Error("fetch_failed");
  const data = await res.json();
  return data.orders ?? [];
}

async function advanceStatus(businessId: string, pin: string, orderId: string, status: string): Promise<void> {
  const res = await fetch(`${API}/kds/${businessId}/orders/${orderId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pin, status }),
  });
  if (!res.ok) throw new Error("update_failed");
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function KdsPage() {
  const params = useParams();
  const businessId = params?.businessId as string;

  const [pin, setPin]       = useState("");
  const [pinInput, setPinInput] = useState("");
  const [pinError, setPinError] = useState("");
  const [orders, setOrders] = useState<KdsOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load PIN from sessionStorage on mount
  useEffect(() => {
    const stored = sessionStorage.getItem(`kds_pin_${businessId}`);
    if (stored) setPin(stored);
  }, [businessId]);

  const load = useCallback(async (p: string) => {
    if (!p || !businessId) return;
    setLoading(true);
    try {
      const data = await fetchOrders(businessId, p);
      setOrders(data);
      setLastRefresh(new Date());
    } catch (e) {
      if (e instanceof Error && e.message === "invalid_pin") {
        setPin("");
        setPinError("Incorrect PIN");
        sessionStorage.removeItem(`kds_pin_${businessId}`);
      }
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  // Start polling when PIN is set
  useEffect(() => {
    if (!pin) return;
    void load(pin);
    intervalRef.current = setInterval(() => void load(pin), 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [pin, load]);

  // Tick elapsed times every second
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  async function handleAdvance(order: KdsOrder, nextStatus: string) {
    setUpdating(order.id);
    try {
      await advanceStatus(businessId, pin, order.id, nextStatus);
      setOrders((prev) =>
        nextStatus === "Done"
          ? prev.filter((o) => o.id !== order.id)
          : prev.map((o) => o.id === order.id ? { ...o, fulfillment_status: nextStatus } : o)
      );
    } catch {
      /* silently ignore; next poll will correct */
    } finally {
      setUpdating(null);
    }
  }

  // ── PIN screen ───────────────────────────────────────────────────────────────
  if (!pin) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4">
        <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-2xl">
          <div className="mb-6 flex flex-col items-center gap-2">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-500 text-white shadow">
              <ChefHat size={28} />
            </div>
            <h1 className="text-xl font-bold text-slate-900">Kitchen Display</h1>
            <p className="text-sm text-slate-500">Enter your KDS PIN to continue</p>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!pinInput.trim()) return;
              setPinError("");
              const p = pinInput.trim();
              sessionStorage.setItem(`kds_pin_${businessId}`, p);
              setPin(p);
            }}
          >
            <input
              type="password"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={8}
              autoFocus
              value={pinInput}
              onChange={(e) => setPinInput(e.target.value.replace(/\D/g, ""))}
              placeholder="PIN"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-2xl font-bold tracking-[0.5em] text-slate-900 outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-200"
            />
            {pinError && <p className="mt-2 text-center text-sm text-red-600">{pinError}</p>}
            <button
              type="submit"
              className="mt-4 w-full rounded-xl bg-orange-500 py-3 text-base font-semibold text-white transition hover:bg-orange-600 active:scale-[0.98]"
            >
              Enter
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── KDS board ────────────────────────────────────────────────────────────────
  const columns: Record<Status, KdsOrder[]> = {
    New:       orders.filter((o) => o.fulfillment_status === "New" || !o.fulfillment_status),
    Confirmed: orders.filter((o) => o.fulfillment_status === "Confirmed"),
    Preparing: orders.filter((o) => o.fulfillment_status === "Preparing"),
    Ready:     orders.filter((o) => o.fulfillment_status === "Ready"),
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-900 text-white">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-700 bg-slate-800 px-6 py-3">
        <div className="flex items-center gap-3">
          <ChefHat size={22} className="text-orange-400" />
          <span className="text-lg font-bold tracking-wide">Kitchen Display</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-400">
          {loading && <Loader2 size={13} className="animate-spin" />}
          {lastRefresh && (
            <span className="flex items-center gap-1">
              <RefreshCw size={11} /> {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <span className="rounded-full bg-slate-700 px-2.5 py-0.5">
            {orders.length} active order{orders.length !== 1 ? "s" : ""}
          </span>
          <button
            type="button"
            onClick={() => {
              sessionStorage.removeItem(`kds_pin_${businessId}`);
              setPin("");
              setPinInput("");
            }}
            className="rounded-full border border-slate-600 px-3 py-1 text-[11px] text-slate-400 hover:border-red-500 hover:text-red-400"
          >
            Lock
          </button>
        </div>
      </header>

      {/* Kanban columns */}
      <div className="flex flex-1 gap-3 overflow-x-auto p-4">
        {STATUSES.map((status) => {
          const col = columns[status];
          const cfg = STATUS_CONFIG[status];
          const hdr = COLUMN_HEADERS[status];
          return (
            <div key={status} className="flex min-w-[280px] max-w-[320px] flex-1 flex-col gap-3">
              {/* Column header */}
              <div className={`flex items-center justify-between rounded-xl px-3 py-2 ${hdr.color}`}>
                <span className="text-sm font-bold">{hdr.label}</span>
                <span className="rounded-full bg-black/20 px-2 py-0.5 text-xs font-bold">{col.length}</span>
              </div>

              {/* Order cards */}
              <div className="flex flex-col gap-2 overflow-y-auto">
                {col.length === 0 && (
                  <div className="flex flex-col items-center gap-1 rounded-xl border border-dashed border-slate-700 py-8 text-center text-xs text-slate-600">
                    <Check size={18} className="text-slate-700" />
                    <span>No orders</span>
                  </div>
                )}
                {col.map((order) => {
                  const elapsed = order.elapsed_seconds + tick - tick; // tick forces re-render
                  const liveElapsed = Math.max(
                    0,
                    order.elapsed_seconds + Math.floor((Date.now() - new Date(order.created_at).getTime()) / 1000) - order.elapsed_seconds
                  );
                  const nextStatus = cfg.next;
                  const isUpdating = updating === order.id;

                  return (
                    <div
                      key={order.id}
                      className={`rounded-xl border-l-4 ${cfg.border} ${cfg.bg} p-3 shadow-sm`}
                    >
                      {/* Order header */}
                      <div className="mb-2 flex items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-sm font-bold text-slate-800">
                              #{order.order_number || order.id.slice(-6).toUpperCase()}
                            </span>
                            <span className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-px text-[10px] font-semibold ${cfg.badge}`}>
                              {status}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-slate-600">{order.customer_name}</p>
                        </div>
                        <span className={`flex items-center gap-0.5 text-[11px] ${elapsedColor(liveElapsed)}`}>
                          <Clock size={10} />{formatElapsed(liveElapsed)}
                        </span>
                      </div>

                      {/* Delivery type badge */}
                      <div className="mb-2 flex flex-wrap gap-1">
                        {order.delivery_type === "delivery" && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">
                            <Truck size={9} /> Delivery
                          </span>
                        )}
                        {(order.delivery_type === "dine-in" || order.delivery_type === "dine_in") && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-brand/15 px-2 py-0.5 text-[10px] font-semibold text-brand-dark">
                            <UtensilsCrossed size={9} /> Dine-in {order.table_number ? `· T${order.table_number}` : ""}
                          </span>
                        )}
                        {order.delivery_type === "pickup" && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                            <ShoppingBag size={9} /> Pickup
                          </span>
                        )}
                        {order.assigned_to && (
                          <span className="inline-flex items-center rounded-full bg-brand/15 px-2 py-0.5 text-[10px] font-semibold text-brand-dark">
                            👤 {order.assigned_to}
                          </span>
                        )}
                      </div>

                      {/* Items */}
                      <ul className="mb-2 space-y-0.5 border-t border-slate-200 pt-2">
                        {order.items.map((item, idx) => (
                          <li key={idx} className="flex items-start gap-1.5 text-xs text-slate-800">
                            <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded bg-slate-800 text-[9px] font-bold text-white">
                              {item.quantity}
                            </span>
                            <span className="leading-snug">
                              {item.product_name || item.name || "Item"}
                              {item.modifiers?.length ? (
                                <span className="ml-1 text-slate-500">({item.modifiers.join(", ")})</span>
                              ) : null}
                            </span>
                          </li>
                        ))}
                      </ul>

                      {/* Notes */}
                      {order.notes && (
                        <p className="mb-2 rounded-lg bg-yellow-50 px-2 py-1 text-[10px] italic text-yellow-800 border border-yellow-200">
                          📝 {order.notes}
                        </p>
                      )}

                      {/* Advance button */}
                      {nextStatus && (
                        <button
                          type="button"
                          disabled={isUpdating}
                          onClick={() => void handleAdvance(order, nextStatus)}
                          className={`mt-1 flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-semibold transition active:scale-[0.97] ${
                            nextStatus === "Done"
                              ? "bg-green-600 text-white hover:bg-green-700"
                              : "bg-slate-800 text-white hover:bg-slate-700"
                          }`}
                        >
                          {isUpdating ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            cfg.nextLabel
                          )}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

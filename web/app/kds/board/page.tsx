"use client";

import { useEffect, useState, useCallback } from "react";
import { ordersApi, Order } from "@/lib/api";
import { elapsedMinutes } from "@/lib/utils";
import { Clock, ChefHat, RefreshCw } from "lucide-react";

type FulfillmentStatus = "New" | "Confirmed" | "Preparing" | "Ready" | "Done";

const STATUS_CONFIG: Record<
  FulfillmentStatus,
  { label: string; bg: string; border: string; badge: string; text: string }
> = {
  New:       { label: "New",       bg: "bg-red-950",    border: "border-red-500",    badge: "bg-red-500",    text: "text-red-300" },
  Confirmed: { label: "Confirmed", bg: "bg-orange-950", border: "border-orange-500", badge: "bg-orange-500", text: "text-orange-300" },
  Preparing: { label: "Preparing", bg: "bg-yellow-950", border: "border-yellow-500", badge: "bg-yellow-400", text: "text-yellow-300" },
  Ready:     { label: "Ready",     bg: "bg-green-950",  border: "border-green-500",  badge: "bg-green-500",  text: "text-green-300" },
  Done:      { label: "Done",      bg: "bg-slate-900",  border: "border-slate-700",  badge: "bg-slate-600",  text: "text-slate-400" },
};

const ACTIVE_STATUSES: FulfillmentStatus[] = ["New", "Confirmed", "Preparing", "Ready"];
const POLL_INTERVAL = 8000; // 8 seconds

export default function KDSBoardPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const fetchOrders = useCallback(async (options?: { showFullPageSpinner?: boolean }) => {
    const spin = options?.showFullPageSpinner ?? false;
    if (spin) setLoading(true);
    try {
      const all = await ordersApi.list();
      // Show only active (non-Done) orders on KDS
      const active = all.filter((o) =>
        ACTIVE_STATUSES.includes((o.fulfillment_status || "New") as FulfillmentStatus)
      );
      // Sort: New first, then by created_at ascending (oldest first)
      active.sort((a, b) => {
        const statusOrder = ACTIVE_STATUSES;
        const ai = statusOrder.indexOf((a.fulfillment_status || "New") as FulfillmentStatus);
        const bi = statusOrder.indexOf((b.fulfillment_status || "New") as FulfillmentStatus);
        if (ai !== bi) return ai - bi;
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      });
      setOrders(active);
      setLastRefresh(new Date());
    } catch (e) {
      console.error(e);
    } finally {
      if (spin) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders({ showFullPageSpinner: true });
    const interval = setInterval(() => fetchOrders({ showFullPageSpinner: false }), POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchOrders]);

  async function advanceStatus(order: Order) {
    const flow: FulfillmentStatus[] = ["New", "Confirmed", "Preparing", "Ready", "Done"];
    const current = (order.fulfillment_status || "New") as FulfillmentStatus;
    const nextIndex = flow.indexOf(current) + 1;
    if (nextIndex >= flow.length) return;
    const next = flow[nextIndex];
    setUpdatingId(order.id);
    try {
      await ordersApi.updateProgress(order.id, { fulfillment_status: next });
      await fetchOrders({ showFullPageSpinner: false });
    } finally {
      setUpdatingId(null);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <RefreshCw size={32} className="text-slate-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <ChefHat size={24} className="text-indigo-400" />
          <h1 className="text-xl font-bold">Kitchen Display</h1>
        </div>
        <div className="flex items-center gap-6">
          {/* Status legend */}
          <div className="hidden md:flex items-center gap-4 text-xs text-slate-400">
            {ACTIVE_STATUSES.map((s) => (
              <span key={s} className="flex items-center gap-1.5">
                <span className={`w-2.5 h-2.5 rounded-full ${STATUS_CONFIG[s].badge}`} />
                {s}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-1.5 text-slate-500 text-xs">
            <RefreshCw size={12} />
            {lastRefresh.toLocaleTimeString()}
          </div>
          <span className="text-slate-400 text-sm font-semibold">
            {orders.length} active
          </span>
        </div>
      </header>

      {/* Board */}
      {orders.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-600">
          <ChefHat size={48} />
          <p className="text-lg font-medium">No active orders</p>
          <p className="text-sm">New orders will appear here automatically</p>
        </div>
      ) : (
        <div className="flex-1 p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 auto-rows-max">
          {orders.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              onAdvance={() => advanceStatus(order)}
              isUpdating={updatingId === order.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function OrderCard({
  order,
  onAdvance,
  isUpdating,
}: {
  order: Order;
  onAdvance: () => void;
  isUpdating: boolean;
}) {
  const status = (order.fulfillment_status || "New") as FulfillmentStatus;
  const cfg = STATUS_CONFIG[status];
  const elapsed = elapsedMinutes(order.created_at);
  const isUrgent = elapsed > 15 && status !== "Ready";

  const flow: FulfillmentStatus[] = ["New", "Confirmed", "Preparing", "Ready"];
  const nextStatus = flow[flow.indexOf(status) + 1];

  const items = order.items && order.items.length > 0 ? order.items : null;

  return (
    <div
      className={`rounded-xl border-2 ${cfg.bg} ${cfg.border} flex flex-col overflow-hidden`}
    >
      {/* Card header */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded-full text-white ${cfg.badge}`}
          >
            {cfg.label}
          </span>
          <span className="text-white font-bold text-sm">
            #{order.order_number || order.id.slice(-4)}
          </span>
        </div>
        <div
          className={`flex items-center gap-1 text-xs font-medium ${
            isUrgent ? "text-red-400" : cfg.text
          }`}
        >
          <Clock size={12} />
          {elapsed}m
        </div>
      </div>

      {/* Items */}
      <div className="px-4 pb-3 flex-1 space-y-2">
        {items ? (
          items.map((item, i) => (
            <div key={i} className="flex justify-between items-start gap-2">
              <div>
                <p className="text-white text-sm font-medium leading-tight">
                  {item.quantity}× {item.product_name}
                </p>
                {item.modifiers && item.modifiers.length > 0 && (
                  <p className="text-slate-400 text-xs">{item.modifiers.join(", ")}</p>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="flex justify-between items-start gap-2">
            <p className="text-white text-sm font-medium">
              {order.quantity}× {order.product}
            </p>
          </div>
        )}

        {order.notes && (
          <p className="text-xs text-amber-300 bg-amber-950 rounded px-2 py-1 mt-2">
            📝 {order.notes}
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-white/10 flex items-center justify-between gap-2">
        <div className="text-xs text-slate-400 space-y-0.5">
          {order.delivery_type && (
            <p>
              {order.delivery_type === "dine-in" || order.delivery_type === "dine in"
                ? `🪑 Table ${order.table_number || "?"}`
                : order.delivery_type === "delivery"
                ? "🚗 Delivery"
                : "🛍 Pickup"}
            </p>
          )}
          {order.assigned_to && <p>👤 {order.assigned_to}</p>}
        </div>

        {nextStatus && (
          <button
            type="button"
            onClick={onAdvance}
            disabled={isUpdating}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-opacity disabled:opacity-50 ${
              cfg.badge
            } hover:opacity-80`}
          >
            {isUpdating ? "..." : `→ ${nextStatus}`}
          </button>
        )}
        {!nextStatus && (
          <span className="text-xs text-slate-500 italic">Ready ✓</span>
        )}
      </div>
    </div>
  );
}

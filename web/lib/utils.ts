import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

const API_ORIGIN =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL
    ? process.env.NEXT_PUBLIC_API_URL.replace(/\/?api\/?$/, "")
    : "http://localhost:8000";

/** Resolve relative upload paths from the API for `<img src>`. */
export function resolveMediaUrl(url: string | undefined | null): string | null {
  if (!url || typeof url !== "string") return null;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${API_ORIGIN}${url.startsWith("/") ? "" : "/"}${url}`;
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number | undefined | null, currency = "KES") {
  const n =
    typeof amount === "number" && !Number.isNaN(amount)
      ? amount
      : Number(amount);
  const safe = Number.isFinite(n) ? n : 0;
  const currencyConfig: Record<string, { symbol: string; locale: string }> = {
    KES: { symbol: "KSh", locale: "en-KE" },
    USD: { symbol: "$", locale: "en-US" },
    EUR: { symbol: "€", locale: "en-EU" },
    GBP: { symbol: "£", locale: "en-GB" },
    NGN: { symbol: "₦", locale: "en-NG" },
    ZAR: { symbol: "R", locale: "en-ZA" },
    GHS: { symbol: "₵", locale: "en-GH" },
    UGX: { symbol: "USh", locale: "en-UG" },
    TZS: { symbol: "TSh", locale: "en-TZ" },
  };

  const config = currencyConfig[currency] || { symbol: currency, locale: "en-US" };
  return `${config.symbol} ${safe.toLocaleString(config.locale, { minimumFractionDigits: 0 })}`;
}

export function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString("en-KE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Calendar display; empty or invalid input becomes an em dash (lists, AI-created rows). */
export function formatDateSafe(dateStr: string | undefined | null) {
  if (dateStr == null || String(dateStr).trim() === "") return "—";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return String(dateStr).trim() || "—";
  return formatDate(dateStr);
}

/** Date + time for reminders, messages, etc. */
export function formatDateTime(dateStr: string) {
  return new Date(dateStr).toLocaleString("en-KE", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Value for `<input type="datetime-local" />` in the user's local timezone. */
export function toDatetimeLocalValue(isoOrDate: string | Date | undefined | null): string {
  if (isoOrDate == null || isoOrDate === "") return "";
  const d = typeof isoOrDate === "string" ? new Date(isoOrDate) : isoOrDate;
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function elapsedMinutes(dateStr: string) {
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 60000);
}

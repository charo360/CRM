import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency = "KES") {
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
  return `${config.symbol} ${amount.toLocaleString(config.locale, { minimumFractionDigits: 0 })}`;
}

export function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString("en-KE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
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

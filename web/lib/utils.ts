import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { API_BASE } from "./api";

function crmApiOrigin(): string {
  if (API_BASE.startsWith("http://") || API_BASE.startsWith("https://")) {
    return API_BASE.replace(/\/api$/, "");
  }
  return "";
}

/** Resolve relative upload paths from the API for `<img src>`. */
export function resolveMediaUrl(url: string | undefined | null): string | null {
  if (!url || typeof url !== "string") return null;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  // Same-origin proxy: Next rewrites `/api/media/...` and `/proxy/...` to the backend.
  if (!crmApiOrigin() && url.startsWith("/api/")) return url;
  const origin = crmApiOrigin() || "http://localhost:8000";
  return `${origin}${url.startsWith("/") ? "" : "/"}${url}`;
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
/** Normalise a server datetime string: if it has no timezone indicator treat it as UTC. */
function asUtc(dateStr: string): string {
  return dateStr && !dateStr.includes("+") && !dateStr.endsWith("Z")
    ? dateStr + "Z"
    : dateStr;
}

export function formatDateTime(dateStr: string) {
  return new Date(asUtc(dateStr)).toLocaleString("en-KE", {
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
  const diff = Date.now() - new Date(asUtc(dateStr)).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function elapsedMinutes(dateStr: string) {
  return Math.floor((Date.now() - new Date(asUtc(dateStr)).getTime()) / 60000);
}

/**
 * Save a blob via a hidden anchor — avoids navigation flashes in SPA chat UIs.
 */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  a.rel = "noopener";
  a.style.cssText = "position:fixed;left:-9999px;top:-9999px;opacity:0;pointer-events:none";
  document.body.appendChild(a);
  a.click();
  requestAnimationFrame(() => {
    a.remove();
    URL.revokeObjectURL(blobUrl);
  });
}

/**
 * Trigger a browser save dialog for a remote file.
 * S3 URLs go through `/api/download-proxy`; same-origin / backend URLs fetch directly.
 */
export async function downloadAsset(url: string, name: string): Promise<void> {
  const resolved = resolveMediaUrl(url) || url;
  const safeBase = (name || "download").replace(/[^a-z0-9_\-. ]/gi, "_").trim() || "download";
  const isLocalPresentation = /\/api\/media\/presentations\//i.test(resolved);
  const useProxy =
    !isLocalPresentation &&
    (/amazonaws\.com/i.test(resolved) || /\/api\/images\/s3\//i.test(resolved));

  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  const fetchUrl =
    resolved.startsWith("/") && typeof window !== "undefined"
      ? `${window.location.origin}${resolved}`
      : resolved;

  let res: Response;
  if (isLocalPresentation) {
    res = await fetch(fetchUrl, { headers: authHeaders });
  } else if (useProxy) {
    const proxyGetUrl =
      `${API_BASE}/download-proxy?url=${encodeURIComponent(resolved)}&filename=${encodeURIComponent(safeBase)}`;
    res = await fetch(proxyGetUrl, { method: "GET", headers: authHeaders });
    if (res.status === 405) {
      res = await fetch(`${API_BASE}/download-proxy`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders },
        body: JSON.stringify({ url: resolved, filename: safeBase }),
      });
    }
  } else {
    res = await fetch(fetchUrl, { headers: authHeaders });
  }
  if (!res.ok) throw new Error(`Download failed (HTTP ${res.status})`);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const cdMatch = cd.match(/filename="?([^";]+)"?/i);
  let filename = cdMatch?.[1];
  if (!filename) {
    const pathExt = resolved.split("?")[0].split(".").pop()?.toLowerCase() ?? "";
    const mimeMap: Record<string, string> = {
      "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif",
      "video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm",
      "application/pdf": "pdf",
      "application/vnd.ms-powerpoint": "ppt",
      "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    };
    const ext = pathExt || mimeMap[blob.type] || "bin";
    filename = `${safeBase}.${ext}`;
  }
  triggerBlobDownload(blob, filename);
}

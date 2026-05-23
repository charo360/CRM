import { getToken } from "./auth";

/**
 * Browser calls use `NEXT_PUBLIC_API_URL` + path (e.g. `/seo-agent/chat`).
 * FastAPI mounts everything under `/api`, so the base must end with `/api`, unless
 * using the Next rewrite (`/proxy` → backend `/api/*`). Render/env values often
 * omit `/api` — that produces 404 on routes like the SEO coach.
 */
export function normalizeCrmApiBase(raw: string): string {
  const t = raw.trim().replace(/\/+$/, "");
  if (!t) return "http://127.0.0.1:8000/api";
  if (t.endsWith("/proxy") || t === "/proxy") return t;
  if (t.endsWith("/api")) return t;
  if (t.startsWith("http://") || t.startsWith("https://")) return `${t}/api`;
  return t;
}

export const API_BASE = normalizeCrmApiBase(process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api");

function formatErrorBody(res: Response, rawText: string): string {
  let err: { detail?: unknown; error?: unknown; message?: unknown; details?: unknown } = {};
  try {
    err = rawText ? (JSON.parse(rawText) as typeof err) : {};
  } catch {
    err = { detail: rawText || res.statusText };
  }
  const d = (err.detail ?? err.error ?? err.message) as unknown;
  const msg =
    typeof d === "string"
      ? d
      : Array.isArray(d)
        ? d
            .map((x: { msg?: string }) => (typeof x === "object" && x && "msg" in x ? x.msg : String(x)))
            .join("; ")
        : typeof d === "object" && d !== null
          ? JSON.stringify(d)
          : rawText || res.statusText || "Request failed";
  return msg ? `${res.status}: ${msg}` : `${res.status}: Request failed`;
}

/** Zernio / some gateways return 429 with { details: { retryAfterSeconds } }. */
function parseRetryAfterMs429(rawText: string): number {
  try {
    const j = JSON.parse(rawText) as {
      details?: { retryAfterSeconds?: number };
      retry_after?: number;
      retryAfter?: number;
    };
    const sec = j?.details?.retryAfterSeconds ?? j?.retry_after ?? j?.retryAfter;
    if (typeof sec === "number" && Number.isFinite(sec) && sec >= 0) {
      return Math.min(120_000, Math.max(500, (sec + 0.25) * 1000));
    }
  } catch {
    /* ignore */
  }
  return 2000;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const maxAttempts = 5;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
    });

    if (res.ok) {
      return res.json() as Promise<T>;
    }

    const rawText = await res.text();

    if (res.status === 429 && attempt < maxAttempts) {
      const ra = res.headers.get("Retry-After");
      let waitMs = parseRetryAfterMs429(rawText);
      if (ra) {
        const n = parseInt(ra, 10);
        if (!Number.isNaN(n) && n > 0) {
          waitMs = Math.min(120_000, n * 1000);
        }
      }
      await new Promise((r) => setTimeout(r, waitMs));
      continue;
    }

    throw new Error(formatErrorBody(res, rawText));
  }

  throw new Error("429: Too many retries");
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, init ?? {}),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ── Types ────────────────────────────────────────────────────────────────────

export interface OrderItem {
  product_name: string;
  quantity: number;
  unit_price: number;
  price: number;
  modifiers?: string[];
}

export interface Order {
  id: string;
  order_number: string | null;
  customer_name: string;
  customer_phone: string;
  product: string;
  quantity: number;
  price: number;
  total_amount: number;
  payment_status: string;
  delivery_status: string;
  fulfillment_status: string | null;
  delivery_type: string | null;
  delivery_address: string | null;
  table_number: string | null;
  assigned_to: string | null;
  items: OrderItem[] | null;
  notes: string | null;
  created_at: string;
  status: string | null;
  amount_paid?: number | null;
  amount_remaining?: number | null;
}

export type OrderPayment = {
  id: string;
  order_id: string;
  amount: number;
  method: string;
  note: string;
  created_at: string;
};

export interface Customer {
  id: string;
  name: string;
  phone_number: string;
  email?: string;
  status?: string;
  stage?: string;
  total_spent: number;
  purchase_count: number;
  last_contacted: string | null;
  last_message?: string | null;
  created_at: string;
  tags?: string[];
  notes?: string | null;
  auto_reply?: boolean;
  unread_count?: number;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
  profile_picture?: string | null;
}

/** Matches backend `ProductResponse` / `ProductCreate` (shop catalog). */
export interface ProductVariant {
  name: string;
  price: number;
}

export interface ProductModifierOption {
  name: string;
  price_delta: number;
}

export interface ProductModifierGroup {
  name: string;
  required?: boolean;
  multi_select?: boolean;
  options: ProductModifierOption[];
}

export interface Product {
  id: string;
  name: string;
  price: number;
  discount_price?: number | null;
  description?: string | null;
  category?: string | null;
  sub_category?: string | null;
  image_url?: string | null;
  images?: string[];
  in_stock?: boolean;
  stock_quantity?: number | null;
  variants?: ProductVariant[];
  modifier_groups?: ProductModifierGroup[];
  unit?: string | null;
  moq?: number | null;
  pricing_tiers?: Array<{ min_qty: number; price: number }>;
  created_at?: string;
  ai_failed?: boolean;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  phone_number?: string | null;
  role: string;
  user_id?: string | null;
  permissions?: string[];
  status?: string;
  created_at?: string;
  temp_password?: string | null;
}

export interface AdminUser {
  id: string;
  email: string;
  owner_name: string;
  business_name: string;
  phone_number?: string;
  role: string;
  business_id?: string | null;
  subscription_active?: boolean;
  setup_complete?: boolean;
  created_at?: string;
  last_login?: string;
}

export interface FollowUp {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  reminder_date: string;
  message: string | null;
  status: string;
  type: "call" | "whatsapp" | "meeting" | "email";
  outcome?: string | null;
  outcome_note?: string | null;
  is_auto_sequence?: boolean;
  sequence_day?: number;
  created_at: string;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
}

export interface Sale {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  item: string;
  amount: number;
  payment_method: string;
  receipt_sent: boolean;
  is_credit?: boolean;
  due_date?: string;
  paid_date?: string;
  source?: string;
  created_at: string;
}

export interface Expense {
  id: string;
  category: string;
  amount: number;
  description?: string;
  created_at: string;
}

export interface Broadcast {
  id: string;
  message: string;
  name?: string;
  filter_type: string;
  recipients_count: number;
  sent_count: number;
  status: string;
  scheduled_at?: string;
  created_at: string;
  image_url?: string | null;
  image_urls?: string[] | null;
}

export interface BroadcastPerformance {
  broadcast_id: string;
  sent_count: number;
  recipients_count: number;
  replies: number;
  reply_rate: number;
}

export interface BroadcastTemplate {
  id: string;
  name: string;
  message: string;
  image_url?: string | null;
  created_at: string;
}

/** Backend `broadcast_automations` docs (auto_followup & recurring). */
export interface BroadcastAutomation {
  id: string;
  name?: string;
  type: string;
  message?: string;
  broadcast_id?: string;
  follow_up_message?: string;
  delay_days?: number;
  filter_type?: string;
  recurrence?: string;
  send_hour?: number;
  image_urls?: string[];
  status: string;
  last_run?: string;
  next_run?: string;
  runs?: number;
  created_at: string;
}

export interface CustomerGroup {
  id: string;
  name: string;
  customer_ids: string[];
  count: number;
  created_at: string;
}

export interface BroadcastCreateBody {
  message: string;
  name?: string;
  filter_type: string;
  customer_ids?: string[];
  image_url?: string;
  image_urls?: string[];
  scheduled_at?: string;
  template_id?: string;
}

export interface Booking {
  id: string;
  booking_number: string;
  customer_id: string | null;
  customer_name: string;
  customer_phone?: string;
  service_id: string;
  service_name: string;
  staff_name?: string;
  date: string;
  time: string;
  checkin_date?: string | null;
  checkout_date?: string | null;
  nights?: number | null;
  status: "pending" | "confirmed" | "completed" | "cancelled" | "no_show";
  payment_status: "unpaid" | "partial" | "paid";
  price: number;
  total_price?: number;
  notes?: string;
  created_at: string;
}

/** Body for `POST /bookings` — aligned with mobile `bookingsAPI.createBooking`. */
export interface BookingCreatePayload {
  customer_id?: string;
  customer_name?: string;
  service_id?: string;
  service_name?: string;
  date: string;
  time?: string;
  checkin_date?: string;
  checkout_date?: string;
  staff_name?: string;
  capacity?: number;
  notes?: string;
  price?: number;
  addons?: { name: string; price: number }[];
}

export interface AnalyticsSummary {
  unread_messages: number;
  followups_today: number;
  sales_today: number;
  sales_count_today: number;
  bookings_today?: number;
  total_customers: number;
  total_revenue?: number;
  total_sales?: number;
}

export interface Message {
  id: string;
  customer_id: string;
  direction: "incoming" | "outgoing";
  content: string;
  message_type?: string;
  image_url?: string;
  status?: string;
  created_at: string;
  channel?: "whatsapp" | "instagram";
}

export interface WhatsAppStatus {
  connected: boolean;
  status: string;
  number?: string;
  messages_sent: number;
  messages_limit: number;
  messages_remaining: number;
  daily_sent: number;
  daily_limit: number;
  plan: string;
}

export interface WhatsAppConnection {
  connected: boolean;
  status: string;
  phone_number?: string;
  pairing_code?: string;
  qr_code?: string;
}

export interface BusinessSettings {
  business_name?: string;
  owner_name?: string;
  business_type?: string;
  country?: string;
  country_code?: string;
  currency?: string;
  currency_symbol?: string;
  primary_language?: string;
  business_description?: string;
  products_services?: string;
  business_location?: string;
  business_hours?: string;
  delivery_info?: string;
  special_offers?: string;
  payment_methods?: Array<{ name: string; details: string }>;
  faqs?: string;
  auto_reply_enabled?: boolean;
  auto_reply_audience?: string;
  ai_model?: string;
  notification_enabled?: boolean;
  notification_time?: string;
  daily_alert_count?: number;
  message_tone?: string;
  daily_pulse_enabled?: boolean;
  daily_pulse_time?: string;
  restaurant_has_reservations?: boolean;
  /** Optional sidebar modules; omit = all enabled. */
  features?: Record<string, boolean>;
  account_mode?: string;
  /** Web onboarding wizard; `false` = show wizard for new web signups. */
  onboarding_v1_completed?: boolean | null;
  /** Google Analytics 4 Measurement ID (G-XXXXXXXXXX) */
  ga4_measurement_id?: string;
  /** Enable/disable behavior-triggered discount campaigns */
  behavior_discounts_enabled?: boolean;
}

/** Backend `/business-knowledge` payload (journey + AI fields). */
export type BusinessKnowledge = Record<string, unknown>;

export interface Contact {
  id: string;
  name: string;
  phone_number: string;
  profile_picture?: string;
  is_customer: boolean;
  auto_created: boolean;
  last_message?: string;
  last_contacted?: string;
  created_at: string;
}

export interface FollowUpSuggestion {
  customer_id: string;
  customer_name: string;
  customer_phone: string;
  suggested_message: string;
  interests: string[];
  sentiment: string;
  priority: "high" | "medium" | "low";
  reason: string;
}

export interface DraftRequest {
  customer_id: string;
  custom_instructions?: string;
  tone?: string;
  mode?: "auto" | "personal";
  regenerate_count?: number;
}

export interface DraftResponse {
  message: string;
  confidence: number;
  reason: string;
}

// ── API helpers ──────────────────────────────────────────────────────────────

export const ordersApi = {
  list: () => api.get<Order[]>("/orders"),
  create: (body: Partial<Order> & { customer_id: string }) => api.post<Order>("/orders", body),
  updateProgress: (id: string, body: { fulfillment_status?: string; assigned_to?: string }) =>
    api.patch<Order>(`/orders/${id}/progress`, body),
  /**
   * Backend `PUT /orders/{id}` reads `payment_status`, `delivery_status`, and `notes` from **query
   * parameters** (same as the mobile app), not from a JSON body.
   */
  updateStatus: (id: string, body: { payment_status?: string; delivery_status?: string; notes?: string; payment_method?: string }) => {
    const q = new URLSearchParams();
    if (body.payment_status != null && body.payment_status !== "") {
      q.set("payment_status", body.payment_status);
    }
    if (body.delivery_status != null && body.delivery_status !== "") {
      q.set("delivery_status", body.delivery_status);
    }
    if (body.notes !== undefined) {
      q.set("notes", body.notes);
    }
    if (body.payment_method != null && body.payment_method !== "") {
      q.set("payment_method", body.payment_method);
    }
    const qs = q.toString();
    return api.put<Order>(`/orders/${encodeURIComponent(id)}${qs ? `?${qs}` : ""}`, {});
  },
  convertToSale: (id: string, paymentMethod: string) =>
    api.post<{ id: string }>(`/orders/${id}/convert-to-sale?payment_method=${encodeURIComponent(paymentMethod)}`, {}),
  delete: (id: string) => api.delete<void>(`/orders/${id}`),
  recordPayment: (id: string, body: { amount: number; method: string; note?: string }) =>
    api.post<{ amount_paid: number; amount_remaining: number; payment_status: string; payment: OrderPayment }>(`/orders/${id}/payments`, body),
  getPayments: (id: string) => api.get<OrderPayment[]>(`/orders/${id}/payments`),
};

export const customersApi = {
  list: () => api.get<Customer[]>("/customers"),
  get: (id: string) => api.get<Customer>(`/customers/${id}`),
  create: (body: Partial<Customer>) => api.post<Customer>("/customers", body),
  update: (id: string, body: Partial<Customer>) => api.put<Customer>(`/customers/${id}`, body),
  delete: (id: string) => api.delete<void>(`/customers/${id}`),
};

export const customerGroupsApi = {
  list: () => api.get<CustomerGroup[]>("/customer-groups"),
  create: (body: { name: string; customer_ids: string[] }) =>
    api.post<CustomerGroup>("/customer-groups", body),
  delete: (id: string) => api.delete<void>(`/customer-groups/${id}`),
};

export const productsApi = {
  list: () => api.get<Product[]>("/products"),
  get: (id: string) => api.get<Product>(`/products/${id}`),
  create: (body: Record<string, unknown>) => api.post<Product>("/products", body),
  update: (id: string, body: Record<string, unknown>) => api.put<Product>(`/products/${id}`, body),
  delete: (id: string) => api.delete<void>(`/products/${id}`),
  /** Same as mobile: WhatsApp catalog blast to a segment. */
  broadcastCatalog: (body: { product_ids: string[]; filter_type: string; customer_ids?: string[] }) =>
    api.post<{ broadcast_id?: string; status?: string }>("/products/broadcast-catalog", body),
  /** AI: one new catalog item per image (same as mobile `uploadProducts`). */
  uploadWithAI: async (files: File[]) => {
    const token = getToken();
    const form = new FormData();
    for (const f of files) form.append("files", f);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 120_000);
    try {
      const res = await fetch(`${API_BASE}/products/upload`, {
        method: "POST",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: form,
        signal: controller.signal,
      });
      if (!res.ok) {
        const rawText = await res.text();
        throw new Error(formatErrorBody(res, rawText));
      }
      return res.json() as Promise<{
        status: string;
        uploaded_count: number;
        products_created: number;
        products: Product[];
      }>;
    } finally {
      clearTimeout(timer);
    }
  },
  addImages: async (productId: string, files: File[]) => {
    const token = getToken();
    const form = new FormData();
    for (const f of files) form.append("files", f);
    const res = await fetch(`${API_BASE}/products/${encodeURIComponent(productId)}/images`, {
      method: "POST",
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: form,
    });
    if (!res.ok) {
      const rawText = await res.text();
      throw new Error(formatErrorBody(res, rawText));
    }
    return res.json() as Promise<{ status: string; images_added: number; total_images: number }>;
  },
  deleteImage: async (productId: string, imageIndex: number) => {
    const token = getToken();
    const res = await fetch(
      `${API_BASE}/products/${encodeURIComponent(productId)}/images/${imageIndex}`,
      {
        method: "DELETE",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      }
    );
    if (!res.ok) {
      const rawText = await res.text();
      throw new Error(formatErrorBody(res, rawText));
    }
    return res.json() as Promise<{ status: string; remaining_images: number }>;
  },
  aiDescription: (body: {
    product_name: string;
    category?: string;
    business_type?: string;
    current_description?: string;
    mode?: "generate" | "improve";
  }) => api.post<{ status: string; description: string }>("/products/ai-description", body),
};

/** Design library — same multipart pattern as `productsApi.addImages` (`files` field). */
export const designTemplatesApi = {
  uploadBrandKitImages: async (
    files: File[],
    fields: { material_type: string; name_base: string; is_default_logo: boolean }
  ) => {
    const token = getToken();
    const form = new FormData();
    for (const f of files) form.append("files", f);
    form.append("material_type", fields.material_type);
    form.append("name_base", fields.name_base.trim());
    form.append("is_default_logo", fields.is_default_logo ? "true" : "false");
    const res = await fetch(`${API_BASE}/design-templates/brand-assets`, {
      method: "POST",
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: form,
    });
    if (!res.ok) {
      const rawText = await res.text();
      throw new Error(formatErrorBody(res, rawText));
    }
    return res.json() as Promise<{ status: string; created: number; items: unknown[] }>;
  },
  uploadBrandKitFile: async (
    file: File,
    fields: { name: string; material_type: string; is_default_logo: boolean }
  ) => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    form.append("name", fields.name.trim());
    form.append("material_type", fields.material_type);
    form.append("is_default_logo", fields.is_default_logo ? "true" : "false");
    const res = await fetch(`${API_BASE}/design-templates/brand-asset`, {
      method: "POST",
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: form,
    });
    if (!res.ok) {
      const rawText = await res.text();
      throw new Error(formatErrorBody(res, rawText));
    }
    return res.json() as Promise<Record<string, unknown>>;
  },
};

export const teamApi = {
  list: () => api.get<TeamMember[]>("/team/members"),
  create: (member: Partial<TeamMember>) => api.post<TeamMember>("/team/members", member),
  update: (id: string, member: Partial<TeamMember>) => api.put<TeamMember>(`/team/members/${id}`, member),
  delete: (id: string) => api.delete<void>(`/team/members/${id}`),
};

const ADMIN_PANEL_TOKEN_KEY = "admin_panel_token";
const getAdminPanelToken = (): string | null =>
  typeof window === "undefined" ? null : localStorage.getItem(ADMIN_PANEL_TOKEN_KEY);
const setAdminPanelToken = (token: string) => {
  if (typeof window !== "undefined") localStorage.setItem(ADMIN_PANEL_TOKEN_KEY, token);
};
const clearAdminPanelToken = () => {
  if (typeof window !== "undefined") localStorage.removeItem(ADMIN_PANEL_TOKEN_KEY);
};

function adminHeaders(): Record<string, string> {
  const t = getAdminPanelToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

// Admin API uses Next.js same-origin routes (/api/admin/...) so there are
// no CORS or direct-backend reachability issues.
export const adminApi = {
  login: async (password: string) => {
    const res = await fetch("/api/admin/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const raw = await res.text();
    if (!res.ok) throw new Error(formatErrorBody(res, raw));
    const data = (raw ? JSON.parse(raw) : {}) as { token?: string };
    if (!data.token) throw new Error("No admin token returned");
    setAdminPanelToken(data.token);
    return { ok: true };
  },
  logout: () => clearAdminPanelToken(),
  canAccess: async () => {
    const token = getAdminPanelToken();
    if (!token) return { access: false };
    const res = await fetch("/api/admin/auth/verify", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return { access: false };
    return (await res.json()) as { access: boolean };
  },
  getMetrics: async (params?: { period?: "all" | "today" | "week" | "month" | "3months" | "custom"; start?: string; end?: string }) => {
    const token = getAdminPanelToken();
    if (!token) throw new Error("No admin session");
    const qs = new URLSearchParams();
    if (params?.period) qs.set("period", params.period);
    if (params?.start) qs.set("start", params.start);
    if (params?.end) qs.set("end", params.end);
    const s = qs.toString();
    const res = await fetch(`/api/admin/metrics${s ? `?${s}` : ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const raw = await res.text();
    if (!res.ok) throw new Error(formatErrorBody(res, raw));
    return (raw ? JSON.parse(raw) : {}) as {
      period: string;
      total_users: number;
      subscribed_users: number;
      setup_done_users: number;
      total_earnings: number;
      sales_count: number;
      start?: string | null;
      end?: string | null;
    };
  },
  listUsers: async (params?: { q?: string; limit?: number; skip?: number }) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (typeof params?.limit === "number") qs.set("limit", String(params.limit));
    if (typeof params?.skip === "number") qs.set("skip", String(params.skip));
    const s = qs.toString();
    const res = await fetch(`/api/admin/users${s ? `?${s}` : ""}`, {
      headers: adminHeaders(),
    });
    const raw = await res.text();
    if (!res.ok) throw new Error(formatErrorBody(res, raw));
    return (raw ? JSON.parse(raw) : {}) as { users: AdminUser[]; total: number; limit: number; skip: number };
  },
  updateUser: async (id: string, body: Partial<AdminUser>) => {
    const res = await fetch(`/api/admin/users/${id}`, {
      method: "PATCH",
      headers: { ...adminHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const raw = await res.text();
    if (!res.ok) throw new Error(formatErrorBody(res, raw));
    return (raw ? JSON.parse(raw) : {}) as { user: AdminUser };
  },
  deleteUser: async (id: string) => {
    const res = await fetch(`/api/admin/users/${id}`, {
      method: "DELETE",
      headers: adminHeaders(),
    });
    const raw = await res.text();
    if (!res.ok) throw new Error(formatErrorBody(res, raw));
    return (raw ? JSON.parse(raw) : {}) as { ok: boolean };
  },
  refreshFavicon: async (id: string) => {
    const res = await fetch(`/api/admin/users/${id}/refresh-favicon`, {
      method: "POST",
      headers: adminHeaders(),
    });
    const raw = await res.text();
    if (!res.ok) throw new Error(formatErrorBody(res, raw));
    return (raw ? JSON.parse(raw) : {}) as { status: string; site: string };
  },
};

export interface CollaborationWorkspace {
  id: string;
  name: string;
  description: string;
  member_user_ids: string[];
  linked_conversation_id?: string | null;
  assets?: Array<{
    id: string;
    type: string;
    title: string;
    url: string;
    note: string;
    created_at?: string;
    created_by?: string;
  }>;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ChannelAccessGrant {
  user_id: string;
  channel: string;
  level: string;
}

export interface InboundRoutingRule {
  id?: string;
  name: string;
  enabled?: boolean;
  keywords: string[];
  channels: string[];
  assignee_user_id: string;
}

export const collaborationApi = {
  listWorkspaces: () => api.get<{ workspaces: CollaborationWorkspace[] }>("/business/collaboration/workspaces"),
  createWorkspace: (body: {
    name: string;
    description?: string;
    member_user_ids?: string[];
    linked_conversation_id?: string | null;
  }) => api.post<Record<string, unknown>>("/business/collaboration/workspaces", body),
  getWorkspace: (id: string) => api.get<CollaborationWorkspace>(`/business/collaboration/workspaces/${id}`),
  patchWorkspace: (
    id: string,
    body: Partial<{
      name: string;
      description: string;
      member_user_ids: string[];
      linked_conversation_id: string | null;
    }>,
  ) => api.patch<{ status: string }>(`/business/collaboration/workspaces/${id}`, body),
  deleteWorkspace: (id: string) => api.delete<{ status: string }>(`/business/collaboration/workspaces/${id}`),
  addWorkspaceAsset: (id: string, body: { type?: string; title?: string; url?: string; note?: string }) =>
    api.post<{ asset: Record<string, unknown> }>(`/business/collaboration/workspaces/${id}/assets`, body),
  getChannelAccess: () =>
    api.get<{ channels: string[]; grants: ChannelAccessGrant[]; hint?: string }>(
      "/business/collaboration/channel-access",
    ),
  putChannelAccess: (grants: ChannelAccessGrant[]) =>
    api.put<{ status: string; count: number }>("/business/collaboration/channel-access", { grants }),
  getInboundRouting: () =>
    api.get<{
      enabled: boolean;
      replace_existing: boolean;
      default_assignee: string;
      rules: InboundRoutingRule[];
    }>("/business/collaboration/inbound-routing"),
  putInboundRouting: (body: {
    enabled: boolean;
    replace_existing?: boolean;
    default_assignee?: string;
    rules: InboundRoutingRule[];
  }) => api.put<{ status: string }>("/business/collaboration/inbound-routing", body),
  previewInboundRouting: (body: { text: string; subject?: string; channel?: string }) =>
    api.post<{
      assignee_user_id: string;
      matched_rule: string | null;
      used_default: boolean;
    }>("/business/collaboration/inbound-routing/preview", body),
};

export const authApi = {
  whatsappStart: (phoneNumber: string) =>
    api.post<{ session_token?: string; pairing_code?: string; access_token?: string; token?: string; user?: Record<string, unknown> }>(
      "/auth/whatsapp-start", { phone_number: phoneNumber }
    ),
  whatsappCheck: (sessionToken: string) =>
    api.post<{ access_token?: string; token?: string; user?: Record<string, unknown>; status?: string }>(
      "/auth/whatsapp-check", { session_token: sessionToken }
    ),
  /** Web: email + password — then link WhatsApp under Integrations. */
  registerWeb: (body: { email: string; password: string; business_name: string; owner_name?: string }) =>
    api.post<{
      token?: string;
      access_token?: string;
      user?: Record<string, unknown>;
    }>("/auth/register-web", body),
  loginWeb: (body: { email: string; password: string }) =>
    api.post<{
      token?: string;
      access_token?: string;
      must_change_password?: boolean;
      user?: Record<string, unknown>;
    }>("/auth/login-web", body),
  changePassword: (new_password: string) =>
    api.post<{ status: string }>("/auth/change-password", { new_password }),
  register: (data: { business_name: string; owner_name: string }) =>
    api.post<Record<string, unknown>>("/auth/register", data),
  me: () => api.get<Record<string, unknown>>("/auth/me"),
};

export interface FollowupSuggestionStats {
  neglected_week: number;
  neglected_month: number;
  new_no_followup: number;
  vip_neglected: number;
  total_needing_attention: number;
}

export const followupsApi = {
  list: (params?: { status?: string; assigned_to?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.assigned_to) q.set("assigned_to", params.assigned_to);
    const qs = q.toString();
    return api.get<FollowUp[]>(`/followups${qs ? `?${qs}` : ""}`);
  },
  create: (body: Record<string, unknown>) => api.post<FollowUp>("/followups", body),
  update: (id: string, body: Record<string, unknown>) => api.put<FollowUp>(`/followups/${id}`, body),
  delete: (id: string) => api.delete<void>(`/followups/${id}`),
  snooze: (id: string, days: number) =>
    api.post(`/followups/${id}/snooze?days=${days}`, {}),
  bulkSnooze: (ids: string[], days: number) =>
    api.post<{ status: string; updated: number }>("/followups/bulk-snooze", { ids, days }),
  bulkDelete: (ids: string[]) =>
    api.post<{ status: string; deleted: number }>("/followups/bulk-delete", { ids }),
  suggestionStats: () => api.get<FollowupSuggestionStats>("/stats/followup-suggestions"),
  analytics: (days: number) => api.get<Record<string, unknown>>(`/followups/analytics?days=${days}`),
};

export const salesApi = {
  list: () => api.get<Sale[]>("/sales"),
  create: (body: {
    customer_id: string;
    item: string;
    amount: number;
    payment_method?: string;
    send_receipt?: boolean;
    receipt_message?: string;
    is_credit?: boolean;
    due_date?: string;
  }) => api.post<Sale>("/sales", body),
  markPaid: (id: string, paymentMethod = "Cash") =>
    api.put<Sale>(`/sales/${id}/mark-paid?payment_method=${encodeURIComponent(paymentMethod)}`, {}),
  resendReceipt: (id: string) => api.post<{ status: string }>(`/sales/${id}/resend-receipt`, {}),
};

export const expensesApi = {
  list: () => api.get<Expense[]>("/expenses"),
  create: (body: Partial<Expense>) => api.post<Expense>("/expenses", body),
  delete: (id: string) => api.delete<void>(`/expenses/${id}`),
};

export const bookingsApi = {
  list: () => api.get<Booking[]>("/bookings"),
  create: (body: BookingCreatePayload) => api.post<Booking>("/bookings", body),
  update: (id: string, body: Partial<Booking>) => api.put<Booking>(`/bookings/${id}`, body),
  delete: (id: string) => api.delete<void>(`/bookings/${id}`),
  sendReminder: (id: string) => api.post<{ success: boolean }>(`/bookings/${id}/reminder`, {}),
};

export const analyticsApi = {
  summary: () => api.get<AnalyticsSummary>("/analytics/summary"),
};

export const messagesApi = {
  forCustomer: (customerId: string, limit = 50) =>
    api.get<Message[]>(`/customers/${customerId}/messages?limit=${limit}`),
  send: (toNumber: string, message: string, customerName?: string) =>
    api.post<{ status: string }>(
      `/messages/send?to_number=${encodeURIComponent(toNumber)}&message=${encodeURIComponent(message)}${customerName ? `&customer_name=${encodeURIComponent(customerName)}` : ""}`,
      {}
    ),
  markRead: (customerId: string) =>
    api.post<void>(`/customers/${customerId}/messages/read`, {}),
};

export interface MetaConnection {
  channel: "messenger" | "instagram";
  page_id: string;
  connected: boolean;
}

export interface TelegramConnection {
  connected: boolean;
  bot_username?: string;
}

export const telegramApi = {
  connection: () => api.get<TelegramConnection>("/telegram/connection"),
  connect: (bot_token: string) =>
    api.post<{ status: string; connected: boolean; bot_username: string }>(
      "/telegram/connect",
      { bot_token }
    ),
  disconnect: () =>
    api.delete<{ status: string; connected: boolean }>("/telegram/connect"),
};

export interface PaystackConnection {
  connected: boolean;
  business_name?: string;
}

export const paystackApi = {
  connection: () => api.get<PaystackConnection>("/paystack/connection"),
  connect: (secret_key: string) =>
    api.post<{ status: string; connected: boolean; business_name: string }>(
      "/paystack/connect",
      { secret_key }
    ),
  disconnect: () =>
    api.delete<{ status: string; connected: boolean }>("/paystack/connect"),
};

export interface PayheroConnection {
  connected: boolean;
  username?: string;
  channel_id?: number | string | null;
}

export interface PayheroChannel {
  id: number;
  name: string;
  description?: string;
  channel_type?: string;
  paybill?: string;
  short_code?: string;
}

export const payheroApi = {
  connection: () => api.get<PayheroConnection>("/payhero/connection"),
  connect: (username: string, password: string) =>
    api.post<{ status: string; connected: boolean; username: string }>(
      "/payhero/connect",
      { username, password }
    ),
  disconnect: () =>
    api.delete<{ status: string; connected: boolean }>("/payhero/connect"),
  channels: () =>
    api.get<{ channels: PayheroChannel[]; selected_channel_id?: number | string | null }>(
      "/payhero/channels"
    ),
  setChannel: (channel_id: number | string) =>
    api.post<{ status: string; channel_id: number | string }>(
      "/payhero/channel",
      { channel_id }
    ),
  stkPush: (phone: string, amount: number, external_reference?: string, customer_name?: string) =>
    api.post<{ status: string; payhero_response: unknown }>(
      "/payhero/stk-push",
      { phone, amount, external_reference, customer_name }
    ),
};

// ── Supplier connections (CJ + AliExpress per-user credentials) ──────────────
export interface SupplierConnections {
  cj: boolean;
  aliexpress: boolean;
}

export const supplierApi = {
  connections: () => api.get<SupplierConnections>("/supplier-connections"),
  connectCJ: (email: string, api_key: string) =>
    api.post<{ connected: boolean }>("/supplier-connections/cj", { email, api_key }),
  disconnectCJ: () =>
    api.delete<{ connected: boolean }>("/supplier-connections/cj"),
  connectAliExpress: (app_key: string, app_secret: string, access_token: string) =>
    api.post<{ connected: boolean }>("/supplier-connections/aliexpress", { app_key, app_secret, access_token }),
  disconnectAliExpress: () =>
    api.delete<{ connected: boolean }>("/supplier-connections/aliexpress"),
};

// ── Assistant ────────────────────────────────────────────────────────────────
export interface AssistantModel {
  id: string;
  label: string;
  provider: string;
}

export interface AssistantStep {
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

export interface AssistantMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  steps?: AssistantStep[];
  tool_calls?: unknown;
  /** Which specialist agent produced this assistant message */
  agent?: string;
  /** Tap-to-send follow-ups (e.g. Meta / Google Ads step-by-step) */
  suggestions?: string[];
  /** Documents attached to this user message (shown as chips in the bubble) */
  documents?: AssistantDocument[];
}

export interface AssistantAgent {
  id: string;
  label: string;
  description: string;
}

export interface AssistantConversationSummary {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
  /** Specialist agent for this thread (`general` = default Zilo) */
  agent?: string;
  visibility?: "team" | "private";
  shared_with?: string[];
  created_by?: string;
}

export interface AssistantConversation {
  id: string;
  title: string;
  model: string | null;
  messages: AssistantMessage[];
  agent?: string;
  visibility?: "team" | "private";
  shared_with?: string[];
  created_by?: string;
}

export interface AssistantChatResponse {
  conversation_id: string;
  reply: string;
  steps: AssistantStep[];
  model: string | null;
  needs_confirmation: null | { tool: string; arguments: Record<string, unknown>; reason: string };
  /** Agent that handled this turn — updates every message (seamless handoff) */
  active_agent: string;
  active_agent_label: string;
  /** Shown as tap chips below the assistant reply (advertising specialists) */
  reply_suggestions?: string[];
}

export interface AssistantAuditEntry {
  id: string;
  conversation_id?: string | null;
  tool: string;
  arguments: Record<string, unknown>;
  result_summary?: string | null;
  status: string;
  /** Which specialist agent triggered this action */
  agent?: string | null;
  success?: boolean;
  created_at: string;
}

export interface AssistantDocument {
  id: string;
  filename: string;
  kind: string;
  mime_type: string;
  size: number;
  text_len: number;
  has_text: boolean;
  created_at?: string;
  public_url?: string;
}

export const assistantApi = {
  models: () =>
    api.get<{ default: string; models: AssistantModel[] }>(
      `/assistant/models?_=${Date.now()}`,
      { cache: "no-store" },
    ),
  agents: () => api.get<{ agents: AssistantAgent[] }>("/assistant/agents"),
  suggestions: () =>
    api.get<{ suggestions: string[]; personalized: boolean }>("/assistant/suggestions"),
  businessContext: () =>
    api.get<{
      new_customers?: number;
      orders?: number;
      top_product?: string;
      total_revenue_window?: number;
    }>("/assistant/context"),
  listConversations: () => api.get<AssistantConversationSummary[]>("/assistant/conversations"),
  getConversation: (id: string) => api.get<AssistantConversation>(`/assistant/conversations/${id}`),
  deleteConversation: (id: string) =>
    api.delete<{ status: string }>(`/assistant/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    api.patch<{ status: string; id: string; title?: string }>(
      `/assistant/conversations/${id}`,
      { title }
    ),
  patchConversation: (
    id: string,
    body: { title?: string; visibility?: "team" | "private" },
  ) => api.patch<{ status: string; id: string }>(`/assistant/conversations/${id}`, body),
  shareConversation: (id: string, userIds: string[]) =>
    api.post<{ status: string; shared_with: string[] }>(`/assistant/conversations/${id}/share`, {
      user_ids: userIds,
    }),
  chat: (body: {
    message: string;
    conversation_id?: string | null;
    model?: string;
    auto_approve?: boolean;
    agent?: string;
    visibility?: "team" | "private";
  }) => api.post<AssistantChatResponse>("/assistant/chat", body),

  /** Streaming version — returns a ReadableStream of SSE events. */
  chatStream: (body: {
    message: string;
    conversation_id?: string | null;
    model?: string;
    auto_approve?: boolean;
    agent?: string;
    visibility?: "team" | "private";
    signal?: AbortSignal;
  }): ReadableStream<string> => {
    const { signal, ...bodyRest } = body;
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    let controller!: ReadableStreamDefaultController<string>;
    const stream = new ReadableStream<string>({
      start(c) { controller = c; },
    });
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/assistant/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(bodyRest),
          signal,
        });
        if (!res.ok || !res.body) {
          const text = await res.text().catch(() => res.statusText);
          controller.error(new Error(`${res.status}: ${text}`));
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const part of parts) {
            const line = part.trim();
            if (line.startsWith("data: ")) controller.enqueue(line.slice(6));
          }
        }
        controller.close();
      } catch (e) {
        controller.error(e);
      }
    })();
    return stream;
  },
  generatePresentationStream: (body: {
    topic: string;
    slides: Record<string, unknown>[];
    conversation_id?: string | null;
    message_index?: number;
    edited?: boolean;
    signal?: AbortSignal;
  }): ReadableStream<string> => {
    const { signal, ...bodyRest } = body;
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    let controller!: ReadableStreamDefaultController<string>;
    const stream = new ReadableStream<string>({
      start(c) { controller = c; },
    });
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/assistant/presentation/generate/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(bodyRest),
          signal,
        });
        if (!res.ok || !res.body) {
          const text = await res.text().catch(() => res.statusText);
          controller.error(new Error(`${res.status}: ${text}`));
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const part of parts) {
            const line = part.trim();
            if (line.startsWith("data: ")) controller.enqueue(line.slice(6));
          }
        }
        controller.close();
      } catch (e) {
        controller.error(e);
      }
    })();
    return stream;
  },
  regeneratePresentationSlideStream: (body: {
    conversation_id: string;
    message_index: number;
    slide_index: number;
    instruction: string;
    slides: Record<string, unknown>[];
    image_urls: string[];
    topic?: string;
    text_edited?: boolean;
    signal?: AbortSignal;
  }): ReadableStream<string> => {
    const { signal, ...bodyRest } = body;
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    let controller!: ReadableStreamDefaultController<string>;
    const stream = new ReadableStream<string>({
      start(c) { controller = c; },
    });
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/assistant/presentation/regenerate-slide/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(bodyRest),
          signal,
        });
        if (!res.ok || !res.body) {
          const text = await res.text().catch(() => res.statusText);
          controller.error(new Error(`${res.status}: ${text}`));
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const part of parts) {
            const line = part.trim();
            if (line.startsWith("data: ")) controller.enqueue(line.slice(6));
          }
        }
        controller.close();
      } catch (e) {
        controller.error(e);
      }
    })();
    return stream;
  },
  updatePresentationPlan: (body: {
    conversation_id: string;
    message_index: number;
    topic: string;
    slides: Record<string, unknown>[];
  }) =>
    api.post<{
      success: boolean;
      slides: Record<string, unknown>[];
      topic: string;
      user_edited: boolean;
      saved_at: string;
    }>("/assistant/presentation/plan/update", body),
  listDocuments: (conversationId: string) =>
    api.get<{ documents: AssistantDocument[] }>(
      `/assistant/conversations/${conversationId}/documents`
    ),
  deleteDocument: (docId: string) =>
    api.delete<{ status: string }>(`/assistant/documents/${docId}`),
  audit: (limit = 50) =>
    api.get<AssistantAuditEntry[]>(`/assistant/audit?limit=${limit}`),
  exportDocument: async (
    content: string,
    format: "pdf" | "docx",
    filename?: string
  ): Promise<void> => {
    const token = getToken();
    const res = await fetch(`${API_BASE}/assistant/export`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content, format, filename: filename || "zilo-export" }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === "string" ? err.detail : "Export failed");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filename || "zilo-export"}.${format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  },
  uploadDocumentWithProgress: (
    file: File,
    conversationId: string | null | undefined,
    onProgress: (pct: number) => void,
  ): Promise<{ conversation_id: string; document: AssistantDocument }> => {
    return new Promise((resolve, reject) => {
      const token = getToken();
      const form = new FormData();
      form.append("file", file);
      const qs = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : "";
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/assistant/upload${qs}`);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable) onProgress(Math.round((ev.loaded / ev.total) * 100));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); } catch { reject(new Error("Invalid response")); }
        } else {
          try { reject(new Error(JSON.parse(xhr.responseText)?.detail ?? xhr.statusText)); } catch { reject(new Error(xhr.statusText)); }
        }
      };
      xhr.onerror = () => reject(new Error("Upload failed"));
      xhr.send(form);
    });
  },
  uploadDocument: async (file: File, conversationId?: string | null) => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    const qs = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : "";
    const res = await fetch(`${API_BASE}/assistant/upload${qs}`, {
      method: "POST",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === "string" ? err.detail : "Upload failed");
    }
    return res.json() as Promise<{ conversation_id: string; document: AssistantDocument }>;
  },
};

// ── Shotstack (unified video/image/voice generation) ─────────────────────────────

export interface ShotstackAsset {
  type: "image" | "video" | "title" | "audio" | "voice";
  src?: string;
  text?: string;
  style?: Record<string, unknown>;
  start?: number;
  length?: number;
  position?: string;
  transition?: Record<string, unknown>;
}

export interface ShotstackTemplate {
  id?: string;
  name: string;
  description?: string;
  type: "image" | "voice" | "combined";
  format: string;
  dimensions: { width: number; height: number };
  duration?: number;
  assets: ShotstackAsset[];
  voice?: {
    text?: string;
    voice?: string;
    start?: number;
    length?: number;
    effect?: string;
  };
  background?: string;
  music?: string;
  created_at?: string;
  updated_at?: string;
  user_id?: string;
}

export interface ShotstackRenderRequest {
  template_id?: string;
  template?: ShotstackTemplate;
  modifications?: Record<string, unknown>;
  output_format?: string;
  webhook_url?: string;
}

export interface ShotstackRenderResponse {
  id: string;
  status: string;
  message?: string;
  render_url?: string;
  expires_at?: string;
  template_name?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ShotstackVoice {
  id: string;
  name: string;
  language: string;
  gender: "male" | "female";
}

export const shotstackApi = {
  // Templates
  listTemplates: (type?: string) =>
    api.get<{ templates: ShotstackTemplate[] }>(`/shotstack/templates${type ? `?type=${type}` : ""}`),
  getTemplate: (id: string) => api.get<{ template: ShotstackTemplate }>(`/shotstack/templates/${id}`),
  createTemplate: (template: Omit<ShotstackTemplate, "id" | "created_at" | "updated_at" | "user_id">) =>
    api.post<{ template: ShotstackTemplate }>("/shotstack/templates", template),
  updateTemplate: (id: string, template: Partial<ShotstackTemplate>) =>
    api.put<{ template: ShotstackTemplate }>(`/shotstack/templates/${id}`, template),
  deleteTemplate: (id: string) => api.delete<{ status: string; id: string }>(`/shotstack/templates/${id}`),
  
  // Rendering
  render: (request: ShotstackRenderRequest) =>
    api.post<ShotstackRenderResponse>("/shotstack/render", request),
  getRenderStatus: (id: string) => api.get<ShotstackRenderResponse>(`/shotstack/render/${id}`),
  listRenders: (limit?: number, status?: string) =>
    api.get<{ renders: ShotstackRenderResponse[] }>(`/shotstack/renders${status ? `?status=${status}` : ""}`),
  deleteRender: (id: string) => api.delete<{ status: string; id: string }>(`/shotstack/render/${id}`),
  
  // Utilities
  listVoices: () => api.get<{ voices: { english: ShotstackVoice[]; other: ShotstackVoice[] } }>("/shotstack/voices"),
  searchStock: (query: string, type: string = "video", limit?: number) =>
    api.get<{ results: unknown[] }>(`/shotstack/stock?query=${encodeURIComponent(query)}&type=${type}${limit ? `&limit=${limit}` : ""}`),
};


/** Meta Ads campaign drafts — Mongo-backed, shared with the Meta Ads assistant agent. */
export interface MetaAdsCampaignDraft {
  id: string;
  name: string;
  objective: string;
  daily_budget: number;
  currency: string;
  notes: string;
  status: string;
  /** e.g. `meta_ads_agent` (chat) or `meta_ads_ui` (this page) */
  source?: string;
  created_at: string | null;
}

/** X Ads campaign drafts — same document shape as Meta; `source` is `x_ads_agent` or `x_ads_ui`. */
export type XAdsCampaignDraft = MetaAdsCampaignDraft;

export const marketingApi = {
  listMetaAdsDrafts: () => api.get<{ drafts: MetaAdsCampaignDraft[] }>("/marketing/meta-ads/drafts"),
  createMetaAdsDraft: (body: {
    name: string;
    objective?: string;
    daily_budget?: number;
    currency?: string;
    notes?: string;
    status?: string;
  }) => api.post<{ draft: MetaAdsCampaignDraft }>("/marketing/meta-ads/drafts", body),
  updateMetaAdsDraft: (
    id: string,
    body: Partial<{
      name: string;
      objective: string;
      daily_budget: number;
      currency: string;
      notes: string;
      status: string;
    }>
  ) => api.patch<{ draft: MetaAdsCampaignDraft }>(`/marketing/meta-ads/drafts/${id}`, body),
  deleteMetaAdsDraft: (id: string) =>
    api.delete<{ status: string; id: string }>(`/marketing/meta-ads/drafts/${id}`),
  listXAdsDrafts: () => api.get<{ drafts: XAdsCampaignDraft[] }>("/marketing/x-ads/drafts"),
  createXAdsDraft: (body: {
    name: string;
    objective?: string;
    daily_budget?: number;
    currency?: string;
    notes?: string;
    status?: string;
  }) => api.post<{ draft: XAdsCampaignDraft }>("/marketing/x-ads/drafts", body),
  updateXAdsDraft: (
    id: string,
    body: Partial<{
      name: string;
      objective: string;
      daily_budget: number;
      currency: string;
      notes: string;
      status: string;
    }>
  ) => api.patch<{ draft: XAdsCampaignDraft }>(`/marketing/x-ads/drafts/${id}`, body),
  deleteXAdsDraft: (id: string) =>
    api.delete<{ status: string; id: string }>(`/marketing/x-ads/drafts/${id}`),
  /** AI-generated title + caption for the social scheduler (uses server AI config). */
  draftSocialPost: (body: { prompt: string; channels?: string[] }) =>
    api.post<{ title: string; body: string }>("/marketing/social-post-draft", body),
};

// ── Social Scheduler API (MongoDB-backed) ─────────────────────────────────────

export interface ScheduledPostAsset {
  file_name: string;
  mime_type: string;
  preview_data_url?: string;
  s3_url?: string;
}

export interface ScheduledPost {
  id: string;
  title: string;
  body: string;
  channels: string[];
  scheduled_at: string;
  status: "draft" | "scheduled" | "published" | "failed";
  created_at: string;
  updated_at?: string;
  post_kind?: string;
  placement_id?: string;
  placement_width?: number;
  placement_height?: number;
  link_url?: string;
  assets?: ScheduledPostAsset[];
  image_url?: string;
  publish_error?: string;
  zernio_post_id?: string;
  engagement_synced_at?: string;
  engagement?: {
    likes: number;
    comments: number;
    shares: number;
    reach: number;
    clicks: number;
    saves: number;
  };
}

export type ScheduledPostInput = Omit<ScheduledPost, "id" | "created_at" | "updated_at">;

export interface SocialAnalytics {
  period_days: number;
  total_posts: number;
  unsynced_posts: number;
  totals: { likes: number; comments: number; shares: number; reach: number; clicks: number; saves: number };
  by_channel: Record<string, { likes: number; comments: number; shares: number; reach: number; clicks: number; posts: number }>;
  top_posts: Array<{
    id: string; title: string; channels: string[]; date: string;
    likes: number; comments: number; shares: number; reach: number; clicks: number;
    engagement_score: number; zernio_post_id?: string; engagement_synced_at?: string;
  }>;
  avg_reach_per_post: number;
  avg_engagement_rate: number;
}

export type SocialPostPublishResult = {
  success: boolean;
  zernio_post_id?: string | null;
  error?: string | null;
  crm_status?: string;
};

export const socialSchedulerApi = {
  list: (status?: string) =>
    api.get<{ posts: ScheduledPost[] }>(`/marketing/social-posts${status ? `?status=${status}` : ""}`),
  get: (id: string) =>
    api.get<{ post: ScheduledPost }>(`/marketing/social-posts/${id}`),
  create: (body: Partial<ScheduledPostInput> & { title: string; body: string }) =>
    api.post<{ post: ScheduledPost; publish?: SocialPostPublishResult }>(
      "/marketing/social-posts",
      body,
    ),
  update: (id: string, body: Partial<ScheduledPostInput>) =>
    api.patch<{ post: ScheduledPost; publish?: SocialPostPublishResult }>(
      `/marketing/social-posts/${id}`,
      body,
    ),
  delete: (id: string) =>
    api.delete<{ status: string; id: string }>(`/marketing/social-posts/${id}`),
  analytics: (days = 30, channel?: string) =>
    api.get<SocialAnalytics>(
      `/marketing/social-posts/analytics?days=${days}${channel ? `&channel=${channel}` : ""}`
    ),
};

export const metaApi = {
  connections: () => api.get<MetaConnection[]>("/meta/connections"),
  connect: (body: { page_id: string; page_access_token: string; channel: string; instagram_id?: string }) =>
    api.post<{ status: string; channel: string; page_id: string }>("/meta/connect", body),
  disconnect: (channel: string) => api.delete<{ status: string }>(`/meta/disconnect/${channel}`),
  oauthStart: (channel: "messenger" | "instagram") =>
    api.get<{ url: string; redirect_uri: string }>(`/meta/oauth/start?channel=${channel}`),
};

export const whatsappApi = {
  status: () => api.get<WhatsAppStatus>("/whatsapp/status"),
  connect: (phoneNumber: string) =>
    api.post<{ pairing_code?: string; status: string; message?: string }>("/whatsapp/connect", { phone_number: phoneNumber }),
  disconnect: () => api.post<{ status: string }>("/whatsapp/disconnect", {}),
  sync: () => api.post<{ status: string }>("/whatsapp/sync", {}),
  /** Start a QR-code based connection. Returns base64 QR image. */
  qrStart: () => api.post<{ status: string; qr_base64: string }>("/whatsapp/qr-start", {}),
  /** Fetch a refreshed QR code for the pending instance. */
  qrFetch: () => api.get<{ qr_base64: string }>("/whatsapp/qr"),
};

export const onboardingApi = {
  analyzeWebsite: (body: { url: string; business_type?: string }) =>
    api.post<{
      status: string;
      url: string;
      business_name: string;
      summary: string;
      business_about_draft: string;
      products_services_hint: string;
      services: { name: string; description: string; price: string }[];
      location: string;
      contact_email: string;
      contact_phone: string;
      website_url: string;
      where_to_fill: { label: string; path: string; tip: string }[];
    }>("/onboarding/analyze-website", body),
};

export const settingsApi = {
  get: () => api.get<BusinessSettings>("/settings"),
  update: (settings: Partial<BusinessSettings>) => api.put<BusinessSettings>("/settings", settings),
  /** Same as mobile: AI draft for business knowledge “About” / description. */
  generateAiAbout: (body: {
    business_type: string;
    current_description?: string;
    mode?: "generate" | "improve";
  }) =>
    api.post<{ status: string; description: string }>("/settings/ai-about", {
      business_type: body.business_type,
      current_description: body.current_description,
      mode: body.mode ?? "generate",
    }),
};

export const businessKnowledgeApi = {
  get: () => api.get<BusinessKnowledge>("/business-knowledge"),
  update: (body: Partial<BusinessKnowledge>) =>
    api.put<{ status: string }>("/business-knowledge", body),
};

export const contactsApi = {
  list: () => api.get<Contact[]>("/contacts"),
  suggestions: () => api.get<Contact[]>("/contacts/suggestions"),
  addAsCustomer: (id: string) => api.post<Customer>(`/contacts/${id}/add-as-customer`, {}),
  delete: (id: string) => api.delete<void>(`/contacts/${id}`),
  scanSuggestions: () => api.post<{ status: string }>("/contacts/scan-suggestions", {}),
  backfillNames: () => api.post<{ status: string }>("/customers/backfill-names", {}),
  refreshProfilePictures: () => api.post<{ status: string }>("/customers/refresh-profile-pictures", {}),
};

export const broadcastApi = {
  list: () => api.get<Broadcast[]>("/broadcasts"),
  create: (body: BroadcastCreateBody) => api.post<Broadcast>("/broadcasts", body),
  resend: (id: string) =>
    api.post<{ status: string; broadcast_id: string; recipients_count: number }>(`/broadcasts/${id}/resend`, {}),
  cancel: (id: string) => api.post<{ status: string }>(`/broadcasts/${id}/cancel`, {}),
  delete: (id: string) => api.delete<void>(`/broadcasts/${id}`),
  performance: (id: string) => api.get<BroadcastPerformance>(`/broadcasts/${id}/performance`),
  templates: () => api.get<BroadcastTemplate[]>("/broadcast-templates"),
  createTemplate: (body: { name: string; message: string; image_url?: string }) =>
    api.post<BroadcastTemplate>("/broadcast-templates", body),
  deleteTemplate: (id: string) => api.delete<void>(`/broadcast-templates/${id}`),
  automations: () => api.get<BroadcastAutomation[]>("/broadcasts/automations"),
  deleteAutomation: (id: string) => api.delete<void>(`/broadcasts/automations/${id}`),
  autoFollowup: (body: { broadcast_id: string; follow_up_message: string; delay_days?: number }) =>
    api.post<{ status: string; automation_id: string }>("/broadcasts/auto-followup", body),
  recurring: (body: {
    message: string;
    filter_type?: string;
    image_urls?: string[];
    recurrence?: "weekly" | "monthly";
    send_hour?: number;
  }) => api.post<{ status: string; automation_id: string }>("/broadcasts/recurring", body),
};

export const uploadApi = {
  imageBase64: (base64_data: string, filename = "image.jpg") =>
    api.post<{ image_url: string }>("/upload-image", { base64_data, filename }),
};

export const aiApi = {
  draftMessage: (request: DraftRequest) => api.post<DraftResponse>("/ai/draft-message", request),
  /** Same as mobile `POST /ai/generate-broadcast-message`. */
  generateBroadcastMessage: (body: { prompt: string; business_type?: string }) =>
    api.post<{ message: string }>("/ai/generate-broadcast-message", body),
  sendAutoMessage: (customerId: string, message: string) =>
    api.post<{ status: string }>("/ai/send-auto-message", { customer_id: customerId, message }),
  getDailyInsights: (limit = 10) => api.get<Record<string, unknown>[]>(`/analysis/daily-insights?limit=${limit}`),
  runAnalysisNow: () => api.post<{ status: string }>("/analysis/run-now", {}),
};

export const kdsApi = {
  listByBusiness: (businessId: string) =>
    fetch(`${API_BASE}/orders?business_id=${businessId}`).then((r) => r.json()) as Promise<Order[]>,
};

// ── Invoices ──────────────────────────────────────────────────────────────────
export const INVOICE_API_BASE = API_BASE;
export const invoicesApi = {
  list: (params?: { status?: string; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.q) qs.set("q", params.q);
    const s = qs.toString();
    return api.get<Record<string, unknown>[]>(`/invoices${s ? `?${s}` : ""}`);
  },
  create: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/invoices", body),
  get: (id: string) => api.get<Record<string, unknown>>(`/invoices/${id}`),
  update: (id: string, body: Record<string, unknown>) => api.put<Record<string, unknown>>(`/invoices/${id}`, body),
  setStatus: (id: string, status: string) => api.patch<{ status: string }>(`/invoices/${id}/status`, { status }),
  delete: (id: string) => api.delete<{ deleted: boolean }>(`/invoices/${id}`),
  duplicate: (id: string) => api.post<Record<string, unknown>>(`/invoices/${id}/duplicate`, {}),
  recordPayment: (id: string, body: { amount: number; method?: string; note?: string }) =>
    api.post<Record<string, unknown>>(`/invoices/${id}/payment`, body),
  rotateShare: (id: string) => api.post<{ share_token: string }>(`/invoices/${id}/share`, {}),
  getPublic: (token: string) => api.get<Record<string, unknown>>(`/invoices/public/${token}`),
  summary: () => api.get<Record<string, unknown>>("/invoices/meta/summary"),
  getBranding: () => api.get<Record<string, unknown>>("/invoices/meta/branding"),
  saveBranding: (body: Record<string, unknown>) =>
    api.put<Record<string, unknown>>("/invoices/meta/branding", body),
  aiDraft: (body: { prompt: string; currency?: string; customer_name?: string }) =>
    api.post<{ customer_name: string; items: Array<{ name: string; description?: string; qty: number; unit_price: number; amount: number }>; notes: string; terms: string }>("/invoices/ai/draft", body),
};

// ── Inventory ─────────────────────────────────────────────────────────────────
export const inventoryApi = {
  listProducts: (params?: { category?: string; low_stock?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.category) q.set("category", params.category);
    if (params?.low_stock) q.set("low_stock", "true");
    return api.get<Record<string, unknown>[]>(`/inventory/products${q.toString() ? `?${q}` : ""}`);
  },
  createProduct: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/inventory/products", body),
  updateProduct: (id: string, body: Record<string, unknown>) => api.put<Record<string, unknown>>(`/inventory/products/${id}`, body),
  deleteProduct: (id: string) => api.delete<{ deleted: boolean }>(`/inventory/products/${id}`),
  recordMovement: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/inventory/movements", body),
  listMovements: (productId?: string) => api.get<Record<string, unknown>[]>(`/inventory/movements${productId ? `?product_id=${productId}` : ""}`),
  summary: () => api.get<Record<string, unknown>>("/inventory/summary"),
};

// ── Finance ───────────────────────────────────────────────────────────────────
export const financeApi = {
  listEntries: (params?: { type?: string; from_date?: string; to_date?: string }) => {
    const q = new URLSearchParams();
    if (params?.type) q.set("type", params.type);
    if (params?.from_date) q.set("from_date", params.from_date);
    if (params?.to_date) q.set("to_date", params.to_date);
    return api.get<Record<string, unknown>[]>(`/finance/entries${q.toString() ? `?${q}` : ""}`);
  },
  createEntry: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/finance/entries", body),
  updateEntry: (id: string, body: Record<string, unknown>) => api.put<Record<string, unknown>>(`/finance/entries/${id}`, body),
  deleteEntry: (id: string) => api.delete<{ deleted: boolean }>(`/finance/entries/${id}`),
  summary: (params?: { from_date?: string; to_date?: string }) => {
    const q = new URLSearchParams();
    if (params?.from_date) q.set("from_date", params.from_date);
    if (params?.to_date) q.set("to_date", params.to_date);
    return api.get<Record<string, unknown>>(`/finance/summary${q.toString() ? `?${q}` : ""}`);
  },
  categories: () => api.get<{ income: string[]; expense: string[] }>("/finance/categories"),
  monthly: (months?: number) => {
    const q = months ? `?months=${months}` : "";
    return api.get<Record<string, unknown>[]>(`/finance/monthly${q}`);
  },
  exportCsv: async (params?: { type?: string; from_date?: string; to_date?: string }) => {
    const q = new URLSearchParams();
    if (params?.type) q.set("type", params.type);
    if (params?.from_date) q.set("from_date", params.from_date);
    if (params?.to_date) q.set("to_date", params.to_date);
    const token = getToken();
    const res = await fetch(`${API_BASE}/finance/export${q.toString() ? `?${q}` : ""}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Export failed: ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "finance_export.csv";
    a.click();
    URL.revokeObjectURL(url);
  },
};

// ── Quotes ────────────────────────────────────────────────────────────────────
export const quotesApi = {
  list: (params?: { status?: string; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.q) qs.set("q", params.q);
    const s = qs.toString();
    return api.get<Record<string, unknown>[]>(`/quotes${s ? `?${s}` : ""}`);
  },
  create: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/quotes", body),
  get: (id: string) => api.get<Record<string, unknown>>(`/quotes/${id}`),
  update: (id: string, body: Record<string, unknown>) => api.put<Record<string, unknown>>(`/quotes/${id}`, body),
  setStatus: (id: string, status: string) => api.patch<{ status: string }>(`/quotes/${id}/status`, { status }),
  duplicate: (id: string) => api.post<Record<string, unknown>>(`/quotes/${id}/duplicate`, {}),
  rotateShare: (id: string) => api.post<{ share_token: string }>(`/quotes/${id}/share`, {}),
  convertToInvoice: (id: string) => api.post<{ invoice_id: string; invoice: Record<string, unknown> }>(`/quotes/${id}/convert-to-invoice`, {}),
  delete: (id: string) => api.delete<{ deleted: boolean }>(`/quotes/${id}`),
  getPublic: (token: string) => api.get<Record<string, unknown>>(`/quotes/public/${token}`),
  summary: () => api.get<Record<string, unknown>>("/quotes/meta/summary"),
  getBranding: () => api.get<Record<string, unknown>>("/quotes/meta/branding"),
  aiDraft: (body: { prompt: string; currency?: string; customer_name?: string }) =>
    api.post<{ customer_name: string; items: Array<{ name: string; description?: string; qty: number; unit_price: number; amount: number }>; notes: string; terms: string }>("/quotes/ai/draft", body),
};

// ── Loyalty ───────────────────────────────────────────────────────────────────
export const loyaltyApi = {
  getSettings: () => api.get<Record<string, unknown>>("/loyalty/settings"),
  updateSettings: (body: Record<string, unknown>) => api.put<Record<string, unknown>>("/loyalty/settings", body),
  listMembers: (tier?: string) => api.get<Record<string, unknown>[]>(`/loyalty/members${tier ? `?tier=${tier}` : ""}`),
  getMember: (customerId: string) => api.get<Record<string, unknown>>(`/loyalty/members/${customerId}`),
  addTransaction: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/loyalty/transactions", body),
  listTransactions: (customerId?: string) => api.get<Record<string, unknown>[]>(`/loyalty/transactions${customerId ? `?customer_id=${customerId}` : ""}`),
  summary: () => api.get<Record<string, unknown>>("/loyalty/summary"),
};

// ── Feedback / NPS ────────────────────────────────────────────────────────────
export const feedbackApi = {
  listSurveys: (active?: boolean) => api.get<Record<string, unknown>[]>(`/feedback/surveys${active !== undefined ? `?active=${active}` : ""}`),
  createSurvey: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/feedback/surveys", body),
  updateSurvey: (id: string, body: Record<string, unknown>) => api.put<Record<string, unknown>>(`/feedback/surveys/${id}`, body),
  deleteSurvey: (id: string) => api.delete<{ deleted: boolean }>(`/feedback/surveys/${id}`),
  listResponses: (surveyId?: string) => api.get<Record<string, unknown>[]>(`/feedback/responses${surveyId ? `?survey_id=${surveyId}` : ""}`),
  submitResponse: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/feedback/responses", body),
  nps: (surveyId?: string) => api.get<Record<string, unknown>>(`/feedback/nps${surveyId ? `?survey_id=${surveyId}` : ""}`),
};

export interface ZernioCommentAutoReplyRule {
  keyword: string;
  message: string;
}

export interface ZernioCommentAutoReplyStep {
  type: "text" | "image" | "video" | "file";
  message?: string | null;
  media_url?: string | null;
  delay_seconds?: number;
}

export interface ZernioCommentAutoReplySettings {
  enabled: boolean;
  engine_mode: "native_ai_all_posts" | "manychat_per_post" | "hybrid";
  apply_all_posts: boolean;
  post_ids: string[];
  manychat_post_ids: string[];
  default_message: string;
  keyword_rules: ZernioCommentAutoReplyRule[];
  chain_steps: ZernioCommentAutoReplyStep[];
  reply_only_unreplied: boolean;
}

// ── Zernio Social Inbox ───────────────────────────────────────────────────────
export const zernioApi = {
  status: () => api.get<{ connected: boolean; profile_id?: string; accounts?: unknown[] }>("/zernio/status"),
  accounts: () => api.get<{ accounts: unknown[] }>("/zernio/accounts"),
  connect: (platform: string, redirectUrl?: string, headless?: boolean) => {
    const q = [
      redirectUrl ? `redirect_url=${encodeURIComponent(redirectUrl)}` : "",
      headless ? "headless=true" : "",
    ].filter(Boolean).join("&");
    return api.get<{ authUrl: string; platform: string }>(
      `/zernio/connect/${platform}${q ? `?${q}` : ""}`
    );
  },
  facebookHeadlessPages: (body: { temp_token: string; connect_token: string }) =>
    api.post<{ pages: Array<Record<string, unknown>> }>("/zernio/connect/facebook/headless/pages", body),
  facebookHeadlessComplete: (body: {
    temp_token: string;
    connect_token: string;
    page_id: string;
    user_profile: Record<string, unknown>;
    redirect_url?: string;
  }) => api.post<{ connected: boolean; account?: Record<string, unknown> }>("/zernio/connect/facebook/headless/complete", body),
  disconnect: (accountId: string) => api.delete<Record<string, unknown>>(`/zernio/accounts/${accountId}`),
  inbox: (platform?: string) => api.get<Record<string, unknown>>(`/zernio/inbox${platform ? `?platform=${platform}` : ""}`),
  conversation: (id: string, accountId?: string) =>
    api.get<Record<string, unknown>>(`/zernio/inbox/${id}${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ""}`),
  send: (
    conversation_id: string,
    message: string,
    account_id?: string,
    platform?: string,
    messaging_type?: "RESPONSE" | "UPDATE" | "MESSAGE_TAG",
    message_tag?: "HUMAN_AGENT"
  ) =>
    api.post<Record<string, unknown>>("/zernio/inbox/send", {
      conversation_id,
      message,
      ...(account_id ? { account_id } : {}),
      ...(platform ? { platform } : {}),
      ...(messaging_type ? { messaging_type } : {}),
      ...(message_tag ? { message_tag } : {}),
    }),
  newConversation: (platform: string, recipient: string, message: string) => api.post<Record<string, unknown>>("/zernio/inbox/new", { platform, recipient, message }),
  posts: (platform?: string) => api.get<Record<string, unknown>>(`/zernio/posts${platform ? `?platform=${platform}` : ""}`),
  analytics: (opts?: {
    platform?: string;
    account_id?: string;
    post_id?: string;
    metrics?: string;
    limit?: number;
    page?: number;
    from_date?: string;
    to_date?: string;
  }) => {
    const q = new URLSearchParams();
    if (opts?.platform) q.set("platform", opts.platform);
    if (opts?.account_id) q.set("account_id", opts.account_id);
    if (opts?.post_id) q.set("post_id", opts.post_id);
    if (opts?.metrics) q.set("metrics", opts.metrics);
    if (typeof opts?.limit === "number") q.set("limit", String(opts.limit));
    if (typeof opts?.page === "number") q.set("page", String(opts.page));
    if (opts?.from_date) q.set("from_date", opts.from_date);
    if (opts?.to_date) q.set("to_date", opts.to_date);
    return api.get<Record<string, unknown>>(`/zernio/analytics${q.toString() ? `?${q.toString()}` : ""}`);
  },
  analyticsByPostId: (post_id: string, opts?: { platform?: string; account_id?: string; profile_id?: string; metrics?: string }) => {
    const q = new URLSearchParams();
    if (opts?.platform) q.set("platform", opts.platform);
    if (opts?.account_id) q.set("account_id", opts.account_id);
    if (opts?.profile_id) q.set("profile_id", opts.profile_id);
    if (opts?.metrics) q.set("metrics", opts.metrics);
    return api.get<Record<string, unknown>>(`/zernio/analytics/${encodeURIComponent(post_id)}${q.toString() ? `?${q.toString()}` : ""}`);
  },
  commentedPosts: (opts?: { platform?: string; account_id?: string; min_comments?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (opts?.platform) q.set("platform", opts.platform);
    if (opts?.account_id) q.set("account_id", opts.account_id);
    if (typeof opts?.min_comments === "number") q.set("min_comments", String(opts.min_comments));
    if (typeof opts?.limit === "number") q.set("limit", String(opts.limit));
    return api.get<Record<string, unknown>>(`/zernio/comments${q.toString() ? `?${q.toString()}` : ""}`);
  },
  postComments: (post_id: string, account_id: string, opts?: { platform?: string; limit?: number }) => {
    const q = new URLSearchParams({ account_id });
    if (opts?.platform) q.set("platform", opts.platform);
    if (typeof opts?.limit === "number") q.set("limit", String(opts.limit));
    return api.get<Record<string, unknown>>(`/zernio/comments/${encodeURIComponent(post_id)}?${q.toString()}`);
  },
  replyToComment: (post_id: string, body: { account_id: string; comment_id: string; message: string }) =>
    api.post<Record<string, unknown>>(`/zernio/comments/${encodeURIComponent(post_id)}/reply`, body),
  getCommentAutoReplySettings: () =>
    api.get<ZernioCommentAutoReplySettings>("/zernio/comments/autoreply/settings"),
  updateCommentAutoReplySettings: (body: Partial<ZernioCommentAutoReplySettings>) =>
    api.put<ZernioCommentAutoReplySettings>("/zernio/comments/autoreply/settings", body),
};

// ── SEO + Auto-Blogging ───────────────────────────────────────────────────────

export interface SeoAuditIssue {
  type: "critical" | "warning" | "info";
  field: string;
  message: string;
}

export interface SeoAudit {
  id: string;
  url: string;
  score: number;
  grade: string;
  title: string;
  meta_description: string;
  h1_count: number;
  h2_count: number;
  word_count: number;
  total_images: number;
  images_missing_alt: number;
  issues: SeoAuditIssue[];
  created_at: string;
}

export interface SeoKeyword {
  keyword: string;
  intent: string;
  difficulty: string;
  priority: number;
  content_idea: string;
  search_volume?: number | null;
  local_country?: string | null;
  global_search_volume?: number | null;
  top_region?: string | null;
  top_region_volume?: number | null;
  cpc?: number | null;
  competition?: string | null;
  keyword_difficulty_score?: number | null;
}

export interface ContentLink {
  title: string;
  url: string;
  published_at: string;
}

export interface SerpRankingEntry {
  keyword: string;
  domain: string;
  position: number | null;
  global_position?: number | null;
  checked_at: string;
  location_code?: number;
  search_volume?: number | null;
  local_country?: string | null;
  global_search_volume?: number | null;
  top_region?: string | null;
  top_region_volume?: number | null;
  cpc?: number | null;
  difficulty?: string | null;
  trend?: "rising" | "declining" | "stable" | null;
  content_idea?: string | null;
  posts?: ContentLink[];
}

export interface AiVisibilityAudit {
  url: string;
  ai_score: number | null;
  grade: string;
  issues_count: number;
  created_at: string;
}

export interface BlogPost {
  id: string;
  title: string;
  content: string;
  meta_title: string;
  meta_description: string;
  image_url?: string;
  keywords?: string[];
  tags: string[];
  status: "draft" | "scheduled" | "published";
  scheduled_at?: string;
  platform: string;
  created_at: string;
  updated_at: string;
  published_at?: string;
  site_post_url?: string;
  /** Calendar generation metadata */
  calendar_week?: number;
  calendar_day?: string;
  word_count?: number;
  /** Social shares tracking */
  social_shares?: {
    platform: string;
    account_id: string;
    social_post_id: string;
    caption: string;
    link_url: string;
    shared_at: string;
  }[];
}

export interface BlogGenerateResult {
  title: string;
  content: string;
  meta_title: string;
  meta_description: string;
  image_url?: string;
  tags: string[];
  word_count: number;
  topic: string;
  keywords: string[];
}

export interface ContentCalendarItem {
  week: number;
  day: string;
  title: string;
  topic: string;
  keywords: string[];
  intent: string;
  estimated_traffic: string;
}

export interface SeoBusinessContext {
  business_type: string;
  location: string;
  language: string;
  business_name: string;
  /** Combined description + products/services for AI prompts (may be empty). */
  context_snippet: string;
  /** True when DATAFORSEO_TOKEN is set — Keywords tab can use live Google metrics. */
  live_keyword_data?: boolean;
  website_url?: string;
}

export interface SeoSummary {
  total_posts: number;
  published_posts: number;
  draft_posts: number;
  scheduled_posts: number;
  autoblog_posts: number;
  keywords_saved: number;
  rankings_tracked: number;
  total_audits: number;
  avg_seo_score: number | null;
  last_audit: SeoAudit | null;
}

export const seoApi = {
  // Audit
  audit: (url: string) => api.post<SeoAudit>("/seo/audit", { url }),
  listAudits: () => api.get<SeoAudit[]>("/seo/audits"),
  aiFixSuggestions: (url: string) =>
    api.post<{ url: string; score: number; grade: string; suggestions: { field: string; issue: string; fix: string; example: string }[] }>("/seo/audit/ai-fix", { url }),

  // Keywords — empty fields use saved business profile on the server
  generateKeywords: (business_type?: string, location?: string, language?: string) =>
    api.post<{
      keywords: SeoKeyword[];
      business_type: string;
      location: string;
      keyword_source: "dataforseo" | "vebapi" | "ai";
      excluded_count?: number;
    }>("/seo/keywords", {
      business_type: business_type ?? "",
      location: location ?? "",
      language: language ?? "",
    }),

  // Blog generation
  generateBlog: (body: {
    topic: string;
    keywords?: string[];
    tone?: string;
    length?: string;
    language?: string;
    business_name?: string;
    include_faq?: boolean;
    model_pref?: string;
    existing_titles?: string[];
  }) => api.post<BlogGenerateResult>("/seo/blog/generate", body),

  addContentLink: (keyword: string, domain: string, title: string, url: string) =>
    api.post<{ ok: boolean }>("/seo/content-links", { keyword, domain, title, url }),

  suggestAngles: (keyword: string, existingTitles: string[]) =>
    api.post<{ keyword: string; angles: { title: string; angle: string }[] }>("/seo/suggest-angles", { keyword, existing_titles: existingTitles }),

  // Blog CRUD
  listPosts: () => api.get<BlogPost[]>("/seo/blog/posts"),
  getPost: (id: string) => api.get<BlogPost>(`/seo/blog/posts/${id}`),
  createPost: (body: Partial<BlogPost>) => api.post<BlogPost>("/seo/blog/posts", body),
  updatePost: (id: string, body: Partial<BlogPost>) => api.patch<BlogPost>(`/seo/blog/posts/${id}`, body),
  deletePost: (id: string) => api.delete<{ ok: boolean }>(`/seo/blog/posts/${id}`),
  shareBlogToSocial: (post_id: string, body: { platform: string; account_id: string; caption: string; link_url?: string; image_url?: string }) =>
    api.post<{ ok: boolean; social_post_id: string; platform: string }>(`/seo/blog/posts/${post_id}/share-social`, body),

  // Auto-share settings
  getAutoShareSettings: () =>
    api.get<{ enabled: boolean; trigger: string; account_ids: string[]; account_platforms: Record<string, string> }>("/seo/social-auto-share/settings"),
  updateAutoShareSettings: (body: { enabled: boolean; trigger: string; account_ids: string[]; account_platforms: Record<string, string> }) =>
    api.put<{ ok: boolean; settings: Record<string, unknown> }>("/seo/social-auto-share/settings", body),

  // Publish
  publishPost: (body: {
    post_id: string;
    platform: string;
    wp_url?: string;
    wp_username?: string;
    wp_password?: string;
    shopify_domain?: string;
    shopify_token?: string;
  }) => api.post<{ ok: boolean; platform: string; post_url?: string; error?: string }>("/seo/blog/publish", body),

  // Content calendar — empty business_type / location → server uses profile
  contentCalendar: (business_type?: string, posts_per_week?: number, weeks?: number, location?: string) =>
    api.post<{ calendar: ContentCalendarItem[]; weeks: number; posts_per_week: number }>(
      `/seo/blog/content-calendar?business_type=${encodeURIComponent(business_type ?? "")}&posts_per_week=${posts_per_week ?? 2}&weeks=${weeks ?? 4}&location=${encodeURIComponent(location ?? "")}`,
      {}
    ),

  /** Saved business type, location, language, name — same sources as Settings / Business Knowledge. */
  businessContext: () => api.get<SeoBusinessContext>("/seo/context"),
  summary: () => api.get<SeoSummary & { audit_trend: { date: string; score: number; url: string }[] }>("/seo/summary"),

  // Saved keywords (persisted per month)
  saveKeywords: (body: { keywords: Record<string, unknown>[]; month?: string; business_type?: string; location?: string }) =>
    api.post<{ ok: boolean; month: string; count: number }>("/seo/keywords/save", body),
  listSavedKeywords: () =>
    api.get<{ month: string; count: number; business_type: string; location: string; saved_at: string }[]>("/seo/keywords/saved"),
  getSavedKeywords: (month: string) =>
    api.get<{ month: string; keywords: Record<string, unknown>[]; business_type: string; location: string }>(`/seo/keywords/saved/${month}`),

  // Publish credentials (saved so user doesn't re-enter)
  savePublishCredentials: (body: {
    platform: string;
    wp_url?: string; wp_username?: string; wp_password?: string;
    shopify_domain?: string; shopify_token?: string;
  }) => api.put<{ ok: boolean }>("/seo/publish-credentials", body),
  getPublishCredentials: (platform: string) =>
    api.get<{ platform?: string; wp_url?: string; wp_username?: string; wp_password?: string; shopify_domain?: string; shopify_token?: string; updated_at?: string }>(`/seo/publish-credentials/${platform}`),

  // Monthly improvement suggestions
  improvementSuggestions: () =>
    api.get<{ suggestions: { priority: string; action: string; detail: string }[]; generated_at: string }>("/seo/improvement-suggestions"),

  // Bulk calendar draft generation
  generateCalendarDrafts: (body: {
    items: { title: string; keywords: string[]; topic?: string; week: number; day: string }[];
    tone?: string;
    length?: string;
  }) => api.post<{
    drafts: { post_id?: string; title: string; week: number; day: string; status: string; word_count?: number; error?: string }[];
    total: number;
  }>("/seo/calendar/generate-drafts", body),

  // SEO memory — progressive improvement history
  getSeoMemory: () => api.get<{
    audit_history: { date: string; score: number; url: string; critical_issues: string[] }[];
    published_count: number;
    draft_count: number;
    published_topics: { title: string; tags: string[]; keywords: string[] }[];
    draft_topics: { title: string; tags: string[]; keywords: string[] }[];
    score_trend: "improving" | "declining" | "stable";
    analysis: {
      working: string[];
      not_working: string[];
      next_month_focus: string[];
      score_trend: string;
    };
    kw_months: string[];
  }>("/seo/seo-memory"),

  /** Local SEO (mock/contextual data — same handlers as CRM backend `/seo/local/*`). */
  getLocalListings: () => api.get<{ listings: Record<string, unknown>[] }>("/seo/local/listings"),
  getLocalKeywords: () => api.get<{ keywords: Record<string, unknown>[] }>("/seo/local/keywords"),
  getLocalCompetitors: () => api.get<{ competitors: Record<string, unknown>[] }>("/seo/local/competitors"),
  getLocalScore: () => api.get<Record<string, unknown>>("/seo/local/score"),
  addLocalListing: (body: {
    platform: string;
    name: string;
    address: string;
    phone?: string;
    website?: string;
  }) => api.post<{ success: boolean; listing: Record<string, unknown> }>("/seo/local/listings", body),
  updateLocalListing: (id: string, body: Partial<{ platform: string; name: string; address: string; phone: string; website: string; status: string; rating: number; reviews: number }>) =>
    api.patch<{ success: boolean; listing: Record<string, unknown> }>(`/seo/local/listings/${id}`, body),
  deleteLocalListing: (id: string) =>
    api.delete<{ ok: boolean }>(`/seo/local/listings/${id}`),

  // Analytics events log
  analyticsEvents: (limit = 50) =>
    api.get<{ id: string; type: string; created_at: string; payload?: Record<string, unknown> }[]>(`/seo/analytics/events?limit=${limit}`),

  // Page indexing breakdown (URL Inspection API)
  getPageIndexingStatus: (siteUrl?: string, sitemapUrl?: string, maxUrls = 20) =>
    api.get<{
      connected: boolean; error?: string;
      total_inspected?: number; indexed?: number; not_indexed?: number;
      sitemap_url?: string;
      reasons?: {
        reason: string; label: string; color: string; fix: string | null;
        count: number; urls: string[];
      }[];
    }>(
      `/seo/analytics/search-console/indexing?max_urls=${maxUrls}` +
      (siteUrl ? `&site_url=${encodeURIComponent(siteUrl)}` : "") +
      (sitemapUrl ? `&sitemap_url=${encodeURIComponent(sitemapUrl)}` : "")
    ),

  // List sitemaps for a GSC property
  listSearchConsoleSitemaps: (siteUrl?: string) =>
    api.get<{
      connected: boolean; site_url?: string; error?: string;
      sitemaps: { path: string; last_submitted: string; last_downloaded: string; is_pending: boolean; warnings: number; errors: number; submitted: number; indexed: number }[];
    }>(`/seo/analytics/search-console/sitemaps${siteUrl ? `?site_url=${encodeURIComponent(siteUrl)}` : ""}`),

  // List verified GSC properties
  listSearchConsoleSites: () =>
    api.get<{ connected: boolean; sites: { url: string; level: string }[]; error?: string }>("/seo/analytics/search-console/sites"),

  // Google Search Console (via Composio)
  getSearchConsoleData: (siteUrl?: string, days = 28, searchType = "web") =>
    api.get<{
      connected: boolean; error?: string; site_url?: string; period_days?: number;
      summary?: { total_clicks: number; total_impressions: number; avg_ctr: number; avg_position: number };
      top_queries?: { query: string; clicks: number; impressions: number; ctr: number; position: number }[];
      top_pages?: { page: string; clicks: number; impressions: number; ctr: number; position: number }[];
      devices?: { device: string; clicks: number; impressions: number; ctr: number; position: number }[];
      countries?: { country: string; clicks: number; impressions: number; ctr: number; position: number }[];
      trend?: { date: string; clicks: number; impressions: number }[];
    }>(`/seo/analytics/search-console?days=${days}&search_type=${searchType}${siteUrl ? `&site_url=${encodeURIComponent(siteUrl)}` : ""}`),

  // Google Analytics 4 (via Composio)
  getGa4Data: (propertyId?: string, days = 28) =>
    api.get<{
      connected: boolean; error?: string; property_id?: string; period_days?: number;
      summary?: { total_sessions: number; total_users: number; total_views: number };
      daily?: { date: string; sessions: number; users: number; views: number; bounce_rate: number; avg_session_duration: number }[];
    }>(`/seo/analytics/ga4${propertyId ? `?property_id=${encodeURIComponent(propertyId)}&days=${days}` : `?days=${days}`}`),

  // Google Ads (via Composio)
  getGoogleAdsData: (customerId?: string, days = 30) =>
    api.get<{
      connected: boolean; error?: string; customer_id?: string; period_days?: number;
      summary?: { total_spend: number; total_clicks: number; total_impressions: number; avg_ctr: number; avg_cpc: number };
      campaigns?: { id: string; name: string; status: string; impressions: number; clicks: number; cost: number; ctr: number; avg_cpc: number }[];
    }>(`/seo/analytics/google-ads${customerId ? `?customer_id=${encodeURIComponent(customerId)}&days=${days}` : `?days=${days}`}`),

  // Scheduled posts queue
  scheduledPosts: () =>
    api.get<{ id: string; title: string; scheduled_at: string; platform: string; status: string; content_preview: string }[]>("/seo/blog/scheduled"),

  /** Batch-schedule calendar topics — creates or promotes draft→scheduled with a publish date. */
  scheduleCalendarPosts: (items: { title: string; keywords: string[]; scheduled_at: string; topic?: string; week?: number; day?: string }[]) =>
    api.post<{ ok: boolean; scheduled: number; results: { post_id: string; title: string; action: string }[] }>("/seo/blog/schedule-batch", { items }),

  /** Scrape a website (homepage + sub-pages) and use LLM to write rich content for all Settings fields. */
  scrapeWebsite: (url: string) =>
    api.post<{
      url: string;
      pages_scraped: number;
      extracted: {
        business_name?: string;
        business_description?: string;
        products_services?: string;
        business_location?: string;
        business_type?: string;
        business_hours?: string;
        pricing_info?: string;
        faqs?: string;
        special_offers?: string;
        delivery_info?: string;
      };
    }>("/seo/scrape-website", { url }),

  // SERP Rankings
  getRankings: (keyword?: string, domain?: string, limit = 200) =>
    api.get<{ rankings: SerpRankingEntry[] }>(
      `/seo/serp/rankings?limit=${limit}${keyword ? `&keyword=${encodeURIComponent(keyword)}` : ""}${domain ? `&domain=${encodeURIComponent(domain)}` : ""}`
    ),
  getRankingTrends: (keyword: string, domain: string, days = 30) =>
    api.get<{ trends: { date: string; position: number | null; checks: number }[]; keyword: string; domain: string }>(
      `/seo/serp/rankings/trends?keyword=${encodeURIComponent(keyword)}&domain=${encodeURIComponent(domain)}&days=${days}`
    ),
  checkRanking: (keyword: string, domain: string, country?: string, article_url?: string, article_title?: string) =>
    api.post<{ keyword: string; domain: string; position: number | null; article_url?: string; article_title?: string; country: string; checked_at: string; top_results: { pos: number; domain: string; url: string }[]; total_results: number }>(
      "/seo/serp/check", { keyword, domain, country, article_url, article_title }
    ),
  bulkCheckRankings: (keywords: Partial<SeoKeyword>[], domain: string, country?: string) =>
    api.post<{ results: { keyword: string; position: number | null; checked_at: string }[]; domain: string; checked: number; failed: number }>(
      "/seo/serp/bulk-check", { keywords, domain, country }
    ),
  refreshAllRankings: (country?: string) =>
    api.post<{ checked: number; failed: number; results: { keyword: string; position: number | null; checked_at: string }[] }>(
      "/seo/serp/refresh-all", { country }
    ),
  backfillVolumes: () =>
    api.post<{ updated: number }>("/seo/serp/backfill-volumes", {}),
  deleteRanking: (keyword: string, domain: string) =>
    api.delete<{ deleted: number }>(`/seo/serp/rankings?keyword=${encodeURIComponent(keyword)}&domain=${encodeURIComponent(domain)}`),

  // AI Visibility Audit History
  getAiAudits: (limit = 30) =>
    api.get<{ audits: AiVisibilityAudit[] }>(`/seo/ai-audits?limit=${limit}`),

  // AI-Powered Analysis
  getGscAiAnalysis: (site_url: string, days = 28) =>
    api.get<{
      analysis: {
        overall_health: "good" | "warning" | "critical";
        health_reason: string;
        summary: string;
        wins: { title: string; detail: string; metric: string }[];
        concerns: { title: string; detail: string; action: string }[];
        opportunities: { title: string; action: string; estimated_impact: "low" | "medium" | "high" }[];
        priority_actions: string[];
      };
      raw_data: { total_clicks: number; total_impressions: number; avg_ctr: number; avg_position: number };
      period_days: number;
    }>(`/seo/analytics/search-console/ai-analysis?site_url=${encodeURIComponent(site_url)}&days=${days}`),

  getRankAiDiagnosis: () =>
    api.get<{
      movers: { keyword: string; current_position: number; previous_position: number; change: number; direction: string; last_checked: string }[];
      stable_count: number;
      improved_count: number;
      declined_count: number;
      diagnosis: {
        overall_trend: string;
        overall_summary: string;
        diagnoses: { keyword: string; direction: string; change: number; diagnosis: string; action: string }[];
        top_priority: string;
      } | null;
      overall_trend: string;
      summary?: string;
    }>("/seo/serp/ai-diagnosis"),

  generateBlogSchema: (payload: { post_id?: string; title?: string; content?: string; keywords?: string[]; url?: string; author?: string }) =>
    api.post<{ schemas: object[]; script_tags: string; count: number }>("/seo/blog/schema", payload),

  getInternalLinkSuggestions: () =>
    api.get<{
      suggestions: {
        from_post_id: string;
        from_post_title: string;
        to_post_id: string;
        to_post_title: string;
        anchor_text: string;
        reason: string;
        priority: "high" | "medium" | "low";
        where_to_add: string;
      }[];
      summary: string;
      posts_analyzed: number;
    }>("/seo/blog/internal-links"),
};

// ── Zernio Live Ads ───────────────────────────────────────────────────────────

export interface ZernioCampaignMetrics {
  spend: number;
  impressions: number;
  reach: number;
  clicks: number;
  ctr: number;
  cpc: number;
  cpm: number;
  engagement?: number;
  conversions?: number;
  roas?: number;
}

export interface ZernioCampaign {
  id: string;
  name: string;
  status: string;
  platform?: string;
  objective?: string;
  daily_budget?: number;
  metrics?: ZernioCampaignMetrics;
  /** Some API responses nest metrics directly on campaign */
  spend?: number;
  impressions?: number;
  clicks?: number;
  reach?: number;
}

export interface ZernioAdsInsights {
  period_days: number;
  total_campaigns: number;
  spend: number;
  impressions: number;
  clicks: number;
  reach: number;
  conversions: number;
  ctr: number;
  cpc: number;
  cpm: number;
  campaigns: ZernioCampaign[];
  error?: string | null;
}

export const zernioAdsApi = {
  insights: (platform?: string, days = 30) => {
    const q = new URLSearchParams({ days: String(days) });
    if (platform) q.set("platform", platform);
    return api.get<ZernioAdsInsights>(`/marketing/meta-ads/insights?${q}`);
  },
  liveCampaigns: (platform?: string, status?: string, days = 30) => {
    const q = new URLSearchParams({ days: String(days) });
    if (platform) q.set("platform", platform);
    if (status) q.set("status", status);
    return api.get<{ campaigns: ZernioCampaign[]; error?: string }>(`/marketing/meta-ads/live-campaigns?${q}`);
  },
  updateCampaignStatus: (campaignId: string, status: "active" | "paused", platform?: string) =>
    api.post<Record<string, unknown>>(`/marketing/meta-ads/campaigns/${campaignId}/status`, { status, platform }),
  updateCampaignBudget: (campaignId: string, body: { daily_budget?: number; lifetime_budget?: number; bid_strategy?: string; platform?: string }) =>
    api.put<Record<string, unknown>>(`/marketing/meta-ads/campaigns/${campaignId}/budget`, body),
  accounts: () => api.get<{ accounts: unknown[]; error?: string }>("/marketing/meta-ads/accounts"),
  boostPost: (body: { post_id: string; platform: string; daily_budget: number; duration_days: number; objective?: string; audience?: Record<string, unknown> }) =>
    api.post<Record<string, unknown>>("/marketing/meta-ads/boost", body),
  createCtwa: (body: { platform: string; whatsapp_number: string; creative: Record<string, unknown>; daily_budget: number; duration_days: number; audience?: Record<string, unknown> }) =>
    api.post<Record<string, unknown>>("/marketing/meta-ads/ctwa", body),
};

// ── Ad Health Monitor ─────────────────────────────────────────────────────────

export interface AdHealthCampaign {
  campaign_id: string;
  name: string;
  status: string;
  platform: string;
  health_score: number;
  zone: "healthy" | "warning" | "critical" | "insufficient_data";
  issues: string[];
  spend: number;
  impressions: number;
  clicks: number;
  ctr: number;
  cpc: number;
  roas: number;
  conversions: number;
}

export interface AdHealthReport {
  campaigns: AdHealthCampaign[];
  summary: { critical: number; warning: number; healthy: number; total: number };
  days: number;
  error?: string | null;
}

export interface AdAlertRule {
  id: string;
  name: string;
  condition: string;
  operator: string;
  value: number;
  action: "auto_pause" | "alert_only";
  min_spend: number;
  min_impressions: number;
  notify_whatsapp: boolean;
  enabled: boolean;
  is_default: boolean;
  created_at: string | null;
}

export interface AdAlertHistoryEntry {
  id: string;
  campaign_id: string;
  campaign_name: string;
  rule_name: string;
  action: string;
  health_score: number | null;
  zone: string;
  metrics: { spend?: number; ctr?: number; roas?: number };
  fired_at: string;
}

export const adHealthApi = {
  report: (days = 7, zone?: string) => {
    const q = new URLSearchParams({ days: String(days) });
    if (zone) q.set("zone", zone);
    return api.get<AdHealthReport>(`/marketing/ad-health?${q}`);
  },
  history: (limit = 50) =>
    api.get<{ history: AdAlertHistoryEntry[] }>(`/marketing/ad-health/history?limit=${limit}`),
  listRules: () =>
    api.get<{ rules: AdAlertRule[] }>("/marketing/ad-health/rules"),
  createRule: (body: Omit<AdAlertRule, "id" | "is_default" | "created_at">) =>
    api.post<{ rule: AdAlertRule }>("/marketing/ad-health/rules", body),
  updateRule: (id: string, body: Partial<AdAlertRule>) =>
    api.patch<{ rule: AdAlertRule }>(`/marketing/ad-health/rules/${id}`, body),
  deleteRule: (id: string) =>
    api.delete<{ status: string; id: string }>(`/marketing/ad-health/rules/${id}`),
};

// ── SEO LangGraph Agent ───────────────────────────────────────────────────────

export interface SeoAgentToolStep {
  tool: string;
  args?: Record<string, unknown>;
  output?: string;
}

export interface SeoAgentChatResponse {
  reply: string;
  conversation_id: string;
  tool_steps: SeoAgentToolStep[];
}

export interface SeoAgentConversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface SeoAgentConversationDetail extends SeoAgentConversation {
  messages: { role: "user" | "assistant"; content: string; tool_steps?: SeoAgentToolStep[]; ts: string }[];
}

export interface SeoBriefAction {
  id: string;
  priority: number;
  type: "write_post" | "run_audit" | "research_keywords" | "check_rankings" | "fix_issue";
  title: string;
  reason: string;
  effort: string;
  keyword?: string | null;
  url?: string | null;
  agent_prompt: string;
}

export interface SeoBrief {
  health_score: number;
  health_grade: string;
  status_summary: string;
  wins: string[];
  gaps: string[];
  actions: SeoBriefAction[];
  generated_at: string;
  next_check: string;
  data_snapshot: {
    published_posts: number;
    draft_posts: number;
    keywords_tracked: number;
    keywords_without_post: number;
    audit_score: number | null;
    days_since_audit: number | null;
    rankings_tracked: number;
  };
}

// ── Zilo Autoblogging ─────────────────────────────────────────────────────────

export interface BlogStatus {
  connected: boolean;
  /** Mongo/autoblog `client_id` — always the authenticated user id. Use for deactivate/activate/publish-now/posts. */
  client_id?: string;
  blog_url?: string;
  wp_slug?: string;
  industry?: string;
  location?: string;
  plan?: string;
  posts_count?: number;
  last_posted_at?: string;
  active?: boolean;
}

export interface AutoblogPost {
  title: string;
  post_url: string;
  published_at: string;
  keywords?: string[];
}

export interface KeywordTrackerRow {
  keyword: string;
  search_volume: number;
  difficulty: string;
  intent: string;
  content_idea: string;
  posts: { title: string; url: string; published_at: string }[];
  created_at: string;
  updated_at: string;
  position: number | null;
  position_checked_at: string | null;
  ranked_domain: string | null;
}

export const blogApi = {
  getMyBlog: () => api.get<BlogStatus & { connected: boolean }>("/blog/my"),
  getStatus: (clientId: string) => api.get<BlogStatus>(`/blog/status/${clientId}`),
  create: (body: { client_id: string; business_name: string; client_email: string; industry: string; location: string }) =>
    api.post<{ status: string; blog_url: string; wp_slug: string }>("/blog/create", body),
  /** Idempotent — call after settings save or onboarding. Auto-uses user._id as client_id. */
  provision: (body: { business_name: string; client_email: string; industry: string; location: string }) =>
    api.post<{ status: string; connected: boolean; blog_url?: string; wp_slug?: string }>("/blog/provision", body),
  publishNow: (client_id: string) =>
    api.post<{ status: string; topic: string; post_url: string; post_id: number; template_used?: string }>("/blog/publish-now", { client_id }),
  getPosts: (clientId: string) =>
    api.get<{ posts: AutoblogPost[] }>(`/blog/posts/${clientId}`),
  deactivate: (clientId: string) =>
    request<{ status: string }>(`/blog/deactivate/${clientId}`, { method: "PATCH" }),
  activate: (clientId: string) =>
    request<{ status: string }>(`/blog/activate/${clientId}`, { method: "PATCH" }),
  /** Publish a pre-written SEO post directly to the user's WordPress subsite. */
  publishFromSeo: (body: { title: string; content: string; keywords?: string[]; excerpt?: string; post_id?: string }) =>
    api.post<{ status: string; post_url: string; post_id: number; blog_url: string }>("/blog/publish-from-seo", body),
  /** Keyword tracker — save a keyword to the tracker table. */
  saveKeywordToTracker: (body: { keyword: string; search_volume?: number; difficulty?: string; intent?: string; content_idea?: string }) =>
    api.post<{ ok: boolean }>("/blog/keyword-tracker/save", body),
  /** Link a published post to a tracked keyword. */
  linkPostToKeyword: (params: { keyword: string; post_title: string; post_url: string }) =>
    api.post<{ ok: boolean }>(`/blog/keyword-tracker/link-post?keyword=${encodeURIComponent(params.keyword)}&post_title=${encodeURIComponent(params.post_title)}&post_url=${encodeURIComponent(params.post_url)}`, {}),
  /** Get all tracked keywords with their linked blog posts. */
  getKeywordTracker: () =>
    api.get<{ keywords: KeywordTrackerRow[] }>("/blog/keyword-tracker"),
  /** Batch-fetch real search volumes from DataForSEO for keywords missing volumes. */
  enrichVolumes: () =>
    api.post<{ ok: boolean; updated: number; checked: number; message?: string }>("/blog/keyword-tracker/enrich-volumes", {}),
  /** Delete a keyword from the tracker permanently. */
  deleteKeyword: (keyword: string) =>
    request<{ ok: boolean; message: string }>(`/blog/keyword-tracker/${encodeURIComponent(keyword)}`, { method: "DELETE" }),
  /** Regenerate and upload a custom favicon for the user's WordPress subsite. */
  refreshFavicon: () =>
    api.post<{ status: string; message: string }>("/blog/refresh-favicon", {}),
};

export interface SeoCacheToolStat {
  tool: string;
  cached: number;
  hits: number;
  ttl_days: number;
}

export interface SeoCacheStats {
  total_cached: number;
  valid_cached: number;
  expired_cached: number;
  api_calls_saved: number;
  oldest_entry: string | null;
  newest_entry: string | null;
  by_tool: SeoCacheToolStat[];
  error?: string;
}

export const seoAgentApi = {
  chat: (message: string, conversation_id?: string, history?: { role: string; content: string }[]) =>
    api.post<SeoAgentChatResponse>("/seo-agent/chat", {
      message,
      conversation_id: conversation_id ?? null,
      history: history ?? [],
    }),

  listConversations: () => api.get<SeoAgentConversation[]>("/seo-agent/conversations"),

  getConversation: (id: string) => api.get<SeoAgentConversationDetail>(`/seo-agent/conversations/${id}`),

  deleteConversation: (id: string) => api.delete<{ ok: boolean }>(`/seo-agent/conversations/${id}`),

  status: () => api.get<{ available: boolean; tools: string[] }>("/seo-agent/status"),

  brief: (refresh = false) =>
    api.get<SeoBrief>(`/seo-agent/brief${refresh ? "?refresh=true" : ""}`),

  executeAction: (agent_prompt: string, conversation_id?: string) =>
    api.post<SeoAgentChatResponse>("/seo-agent/execute-action", {
      agent_prompt,
      conversation_id: conversation_id ?? null,
    }),

  cacheStats: () => api.get<SeoCacheStats>("/seo-agent/cache/stats"),

  clearCache: (tool = "") =>
    api.delete<{ ok: boolean; deleted: number }>(
      `/seo-agent/cache${tool ? `?tool=${encodeURIComponent(tool)}` : ""}`
    ),
};

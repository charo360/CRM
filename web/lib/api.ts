import { getToken } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

function formatErrorBody(res: Response, rawText: string): string {
  let err: { detail?: unknown } = {};
  try {
    err = rawText ? (JSON.parse(rawText) as { detail?: unknown }) : {};
  } catch {
    err = { detail: rawText || res.statusText };
  }
  const d = err.detail as unknown;
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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const rawText = await res.text();
    throw new Error(formatErrorBody(res, rawText));
  }
  return res.json();
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
}

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
  role: string;
  user_id?: string | null;
  permissions?: string[];
  created_at?: string;
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
  updateStatus: (id: string, body: { payment_status?: string; delivery_status?: string; notes?: string }) => {
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
    const qs = q.toString();
    return api.put<Order>(`/orders/${encodeURIComponent(id)}${qs ? `?${qs}` : ""}`, {});
  },
  convertToSale: (id: string, paymentMethod: string) =>
    api.post<{ id: string }>(`/orders/${id}/convert-to-sale?payment_method=${encodeURIComponent(paymentMethod)}`, {}),
  delete: (id: string) => api.delete<void>(`/orders/${id}`),
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
      user?: Record<string, unknown>;
    }>("/auth/login-web", body),
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
}

export interface AssistantConversation {
  id: string;
  title: string;
  model: string | null;
  messages: AssistantMessage[];
  agent?: string;
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
}

export const assistantApi = {
  models: () =>
    api.get<{ default: string; models: AssistantModel[] }>(
      `/assistant/models?_=${Date.now()}`,
      { cache: "no-store" },
    ),
  agents: () => api.get<{ agents: AssistantAgent[] }>("/assistant/agents"),
  listConversations: () => api.get<AssistantConversationSummary[]>("/assistant/conversations"),
  getConversation: (id: string) => api.get<AssistantConversation>(`/assistant/conversations/${id}`),
  deleteConversation: (id: string) =>
    api.delete<{ status: string }>(`/assistant/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    api.patch<{ status: string; id: string; title: string }>(
      `/assistant/conversations/${id}`,
      { title }
    ),
  chat: (body: {
    message: string;
    conversation_id?: string | null;
    model?: string;
    auto_approve?: boolean;
    agent?: string;
  }) => api.post<AssistantChatResponse>("/assistant/chat", body),

  /** Streaming version — returns a ReadableStream of SSE events. */
  chatStream: (body: {
    message: string;
    conversation_id?: string | null;
    model?: string;
    auto_approve?: boolean;
    agent?: string;
  }): ReadableStream<string> => {
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
          body: JSON.stringify(body),
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

// ── Orshot (design templates — schema + render for assistant chat manual edit) ─

export interface OrshotTemplateField {
  key?: string | null;
  type?: string | null;
  help_text?: string | null;
  example?: string | null;
  page_number?: number;
  page_id?: string | null;
}

export interface OrshotTemplateSchemaResponse {
  success: boolean;
  template_id?: number;
  name?: string;
  description?: string;
  canvas_width?: number;
  canvas_height?: number;
  thumbnail_url?: string;
  pages?: unknown[];
  fields: OrshotTemplateField[];
}

export const orshotApi = {
  getTemplate: (templateId: number) =>
    api.get<OrshotTemplateSchemaResponse>(`/orshot/templates/${templateId}`),
  render: (body: {
    template_id: number;
    modifications: Record<string, unknown>;
    response_type?: "url" | "base64" | "binary";
    response_format?: "png" | "jpg" | "jpeg" | "webp" | "pdf";
  }) =>
    api.post<{ success: boolean; image_url?: string; image_urls?: string[] }>("/orshot/render", body),
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
      summary: string;
      business_about_draft: string;
      products_services_hint: string;
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
export const invoicesApi = {
  list: (status?: string) => api.get<Record<string, unknown>[]>(`/invoices${status ? `?status=${status}` : ""}`),
  create: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/invoices", body),
  get: (id: string) => api.get<Record<string, unknown>>(`/invoices/${id}`),
  update: (id: string, body: Record<string, unknown>) => api.put<Record<string, unknown>>(`/invoices/${id}`, body),
  setStatus: (id: string, status: string) => api.patch<{ status: string }>(`/invoices/${id}/status`, { status }),
  delete: (id: string) => api.delete<{ deleted: boolean }>(`/invoices/${id}`),
  summary: () => api.get<Record<string, unknown>>("/invoices/meta/summary"),
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
};

// ── Quotes ────────────────────────────────────────────────────────────────────
export const quotesApi = {
  list: (status?: string) => api.get<Record<string, unknown>[]>(`/quotes${status ? `?status=${status}` : ""}`),
  create: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/quotes", body),
  get: (id: string) => api.get<Record<string, unknown>>(`/quotes/${id}`),
  update: (id: string, body: Record<string, unknown>) => api.put<Record<string, unknown>>(`/quotes/${id}`, body),
  setStatus: (id: string, status: string) => api.patch<{ status: string }>(`/quotes/${id}/status`, { status }),
  convertToInvoice: (id: string) => api.post<Record<string, unknown>>(`/quotes/${id}/convert-to-invoice`, {}),
  delete: (id: string) => api.delete<{ deleted: boolean }>(`/quotes/${id}`),
  summary: () => api.get<Record<string, unknown>>("/quotes/meta/summary"),
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

// ── Zernio Social Inbox ───────────────────────────────────────────────────────
export const zernioApi = {
  status: () => api.get<{ connected: boolean; profile_id?: string; accounts?: unknown[] }>("/zernio/status"),
  accounts: () => api.get<{ accounts: unknown[] }>("/zernio/accounts"),
  connect: (platform: string) => api.get<{ authUrl: string; platform: string }>(`/zernio/connect/${platform}`),
  disconnect: (accountId: string) => api.delete<Record<string, unknown>>(`/zernio/accounts/${accountId}`),
  inbox: (platform?: string) => api.get<Record<string, unknown>>(`/zernio/inbox${platform ? `?platform=${platform}` : ""}`),
  conversation: (id: string) => api.get<Record<string, unknown>>(`/zernio/inbox/${id}`),
  send: (conversation_id: string, message: string) => api.post<Record<string, unknown>>("/zernio/inbox/send", { conversation_id, message }),
  newConversation: (platform: string, recipient: string, message: string) => api.post<Record<string, unknown>>("/zernio/inbox/new", { platform, recipient, message }),
  posts: (platform?: string) => api.get<Record<string, unknown>>(`/zernio/posts${platform ? `?platform=${platform}` : ""}`),
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
}

export interface BlogPost {
  id: string;
  title: string;
  content: string;
  meta_title: string;
  meta_description: string;
  tags: string[];
  status: "draft" | "scheduled" | "published";
  scheduled_at?: string;
  platform: string;
  created_at: string;
  updated_at: string;
  published_at?: string;
}

export interface BlogGenerateResult {
  title: string;
  content: string;
  meta_title: string;
  meta_description: string;
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

export interface SeoSummary {
  total_posts: number;
  published_posts: number;
  draft_posts: number;
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

  // Keywords
  generateKeywords: (business_type: string, location?: string, language?: string) =>
    api.post<{ keywords: SeoKeyword[]; business_type: string; location: string }>("/seo/keywords", {
      business_type,
      location: location ?? "",
      language: language ?? "English",
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
  }) => api.post<BlogGenerateResult>("/seo/blog/generate", body),

  // Blog CRUD
  listPosts: () => api.get<BlogPost[]>("/seo/blog/posts"),
  getPost: (id: string) => api.get<BlogPost>(`/seo/blog/posts/${id}`),
  createPost: (body: Partial<BlogPost>) => api.post<BlogPost>("/seo/blog/posts", body),
  updatePost: (id: string, body: Partial<BlogPost>) => api.patch<BlogPost>(`/seo/blog/posts/${id}`, body),
  deletePost: (id: string) => api.delete<{ ok: boolean }>(`/seo/blog/posts/${id}`),

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

  // Content calendar
  contentCalendar: (business_type: string, posts_per_week?: number, weeks?: number, location?: string) =>
    api.post<{ calendar: ContentCalendarItem[]; weeks: number; posts_per_week: number }>(
      `/seo/blog/content-calendar?business_type=${encodeURIComponent(business_type)}&posts_per_week=${posts_per_week ?? 2}&weeks=${weeks ?? 4}&location=${encodeURIComponent(location ?? "")}`,
      {}
    ),

  // Summary
  summary: () => api.get<SeoSummary>("/seo/summary"),
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
};

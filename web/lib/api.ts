import { getToken } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

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
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
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

export interface Product {
  id: string;
  name: string;
  price: number;
  description?: string;
  category?: string;
  images?: string[];
  in_stock?: boolean;
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
}

export interface BroadcastTemplate {
  id: string;
  name: string;
  message: string;
  created_at: string;
}

export interface BroadcastAutomation {
  id: string;
  name: string;
  type: "follow_up" | "recurring";
  message: string;
  trigger_days?: number;
  schedule_time?: string;
  filter_type: string;
  status: "active" | "paused";
  last_run?: string;
  next_run?: string;
  created_at: string;
}

export interface Booking {
  id: string;
  booking_number: string;
  customer_id: string;
  customer_name: string;
  customer_phone?: string;
  service_id: string;
  service_name: string;
  staff_name?: string;
  date: string;
  time: string;
  status: "pending" | "confirmed" | "completed" | "cancelled" | "no_show";
  payment_status: "unpaid" | "partial" | "paid";
  price: number;
  total_price?: number;
  notes?: string;
  created_at: string;
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
  business_type?: string;
  country?: string;
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
}

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
  updateStatus: (id: string, body: { payment_status?: string; delivery_status?: string; notes?: string }) =>
    api.put<Order>(`/orders/${id}`, body),
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

export const productsApi = {
  list: () => api.get<Product[]>("/products"),
  create: (body: Partial<Product>) => api.post<Product>("/products", body),
  update: (id: string, body: Partial<Product>) => api.put<Product>(`/products/${id}`, body),
  delete: (id: string) => api.delete<void>(`/products/${id}`),
};

export const teamApi = {
  list: () => api.get<TeamMember[]>("/team/members"),
  create: (member: Partial<TeamMember>) => api.post<TeamMember>("/team/members", member),
  update: (id: string, member: Partial<TeamMember>) => api.put<TeamMember>(`/team/members/${id}`, member),
  delete: (id: string) => api.delete<void>(`/team/members/${id}`),
};

export const authApi = {
  whatsappStart: (phoneNumber: string) =>
    api.post<{ session_token?: string; pairing_code?: string; access_token?: string; user?: Record<string, unknown> }>(
      "/auth/whatsapp-start", { phone_number: phoneNumber }
    ),
  whatsappCheck: (sessionToken: string) =>
    api.post<{ access_token?: string; user?: Record<string, unknown>; status?: string }>(
      "/auth/whatsapp-check", { session_token: sessionToken }
    ),
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

export const whatsappApi = {
  status: () => api.get<WhatsAppStatus>("/whatsapp/status"),
  connect: (phoneNumber: string) =>
    api.post<{ pairing_code?: string; status: string; message?: string }>("/whatsapp/connect", { phone_number: phoneNumber }),
  disconnect: () => api.post<{ status: string }>("/whatsapp/disconnect", {}),
  sync: () => api.post<{ status: string }>("/whatsapp/sync", {}),
};

export const settingsApi = {
  get: () => api.get<BusinessSettings>("/settings"),
  update: (settings: Partial<BusinessSettings>) => api.put<BusinessSettings>("/settings", settings),
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
  create: (body: { message: string; filter_type: string; name?: string; scheduled_at?: string }) =>
    api.post<Broadcast>("/broadcasts", body),
  resend: (id: string) => api.post<Broadcast>(`/broadcasts/${id}/resend`, {}),
  delete: (id: string) => api.delete<void>(`/broadcasts/${id}`),
  templates: () => api.get<BroadcastTemplate[]>("/broadcast-templates"),
  createTemplate: (body: { name: string; message: string }) =>
    api.post<BroadcastTemplate>("/broadcast-templates", body),
  deleteTemplate: (id: string) => api.delete<void>(`/broadcast-templates/${id}`),
  automations: () => api.get<BroadcastAutomation[]>("/broadcast-automations"),
  createAutomation: (automation: Partial<BroadcastAutomation>) =>
    api.post<BroadcastAutomation>("/broadcast-automations", automation),
  updateAutomation: (id: string, automation: Partial<BroadcastAutomation>) =>
    api.put<BroadcastAutomation>(`/broadcast-automations/${id}`, automation),
  deleteAutomation: (id: string) => api.delete<void>(`/broadcast-automations/${id}`),
};

export const aiApi = {
  draftMessage: (request: DraftRequest) => api.post<DraftResponse>("/ai/draft-message", request),
  sendAutoMessage: (customerId: string, message: string) =>
    api.post<{ status: string }>("/ai/send-auto-message", { customer_id: customerId, message }),
  getDailyInsights: (limit = 10) => api.get<Record<string, unknown>[]>(`/analysis/daily-insights?limit=${limit}`),
  runAnalysisNow: () => api.post<{ status: string }>("/analysis/run-now", {}),
};

export const kdsApi = {
  listByBusiness: (businessId: string) =>
    fetch(`${API_BASE}/orders?business_id=${businessId}`).then((r) => r.json()) as Promise<Order[]>,
};

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
  created_at: string;
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

// ── API helpers ──────────────────────────────────────────────────────────────

export const ordersApi = {
  list: () => api.get<Order[]>("/orders"),
  updateProgress: (id: string, body: { fulfillment_status?: string; assigned_to?: string }) =>
    api.patch<Order>(`/orders/${id}/progress`, body),
  updateStatus: (id: string, body: { payment_status?: string; delivery_status?: string; notes?: string }) =>
    api.put<Order>(`/orders/${id}`, body),
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
};

export const authApi = {
  login: (email: string, password: string) =>
    api.post<{ access_token: string; user: Record<string, unknown> }>("/auth/login", { email, password }),
  register: (data: { name: string; email: string; password: string; phone?: string }) =>
    api.post<{ access_token: string; user: Record<string, unknown> }>("/auth/register", data),
  me: () => api.get<Record<string, unknown>>("/auth/me"),
};

export const followupsApi = {
  list: () => api.get<FollowUp[]>("/followups"),
  create: (body: Partial<FollowUp>) => api.post<FollowUp>("/followups", body),
  update: (id: string, body: Partial<FollowUp>) => api.put<FollowUp>(`/followups/${id}`, body),
  delete: (id: string) => api.delete<void>(`/followups/${id}`),
  snooze: (id: string, days: number) => api.post<FollowUp>(`/followups/${id}/snooze`, { days }),
  analytics: () => api.get<Record<string, unknown>>("/followups/analytics"),
};

export const salesApi = {
  list: () => api.get<Sale[]>("/sales"),
  create: (body: Partial<Sale>) => api.post<Sale>("/sales", body),
  markPaid: (id: string) => api.put<Sale>(`/sales/${id}/mark-paid`, {}),
};

export const expensesApi = {
  list: () => api.get<Expense[]>("/expenses"),
  create: (body: Partial<Expense>) => api.post<Expense>("/expenses", body),
  delete: (id: string) => api.delete<void>(`/expenses/${id}`),
};

export const broadcastApi = {
  list: () => api.get<Broadcast[]>("/broadcasts"),
  create: (body: { message: string; filter_type: string; name?: string; scheduled_at?: string }) =>
    api.post<Broadcast>("/broadcasts", body),
  delete: (id: string) => api.delete<void>(`/broadcasts/${id}`),
  templates: () => api.get<BroadcastTemplate[]>("/broadcast-templates"),
  createTemplate: (body: { name: string; message: string }) =>
    api.post<BroadcastTemplate>("/broadcast-templates", body),
};

export const bookingsApi = {
  list: () => api.get<Booking[]>("/bookings"),
  update: (id: string, body: Partial<Booking>) => api.put<Booking>(`/bookings/${id}`, body),
  delete: (id: string) => api.delete<void>(`/bookings/${id}`),
};

export const analyticsApi = {
  summary: () => api.get<AnalyticsSummary>("/analytics/summary"),
};

export const messagesApi = {
  forCustomer: (customerId: string, limit = 50) =>
    api.get<Message[]>(`/customers/${customerId}/messages?limit=${limit}`),
  send: (toNumber: string, message: string, customerName?: string) =>
    api.post<{ status: string }>(`/messages/send?to_number=${encodeURIComponent(toNumber)}&message=${encodeURIComponent(message)}${customerName ? `&customer_name=${encodeURIComponent(customerName)}` : ""}`, {}),
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

export const kdsApi = {
  listByBusiness: (businessId: string) =>
    fetch(`${API_BASE}/orders?business_id=${businessId}`).then((r) => r.json()) as Promise<Order[]>,
};

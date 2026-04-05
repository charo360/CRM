import axios from 'axios';
import { offlineCache } from '../utils/offlineCache';
import { offlineQueue } from '../utils/offlineQueue';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || 'https://crm-1-pnfo.onrender.com';

export const apiClient = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
    'Bypass-Tunnel-Reminder': 'true',
    'ngrok-skip-browser-warning': 'true',
  },
  timeout: 60000,
});

// Helper for file uploads using native fetch (more reliable than Axios for multipart on RN)
const uploadFetch = async (path: string, formData: FormData, timeoutMs = 30000) => {
  const token = apiClient.defaults.headers.common['Authorization'];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}/api${path}`, {
      method: 'POST',
      headers: {
        'Bypass-Tunnel-Reminder': 'true',
        'ngrok-skip-browser-warning': 'true',
        ...(token ? { 'Authorization': token as string } : {}),
      },
      body: formData,
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  } catch (err: any) {
    if (err.name === 'AbortError') {
      throw new Error('Upload timed out — please try again with fewer images');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
};

// Human-readable description for queued mutations
function _getQueueDescription(method: string, url: string, data?: any): string {
  const name = data?.customer_name || data?.name || data?.product_name || data?.product || '';
  const label = name ? ` "${name}"` : '';
  if (url.includes('/orders')) {
    if (method === 'post') return `New order${label} saved offline`;
    if (method === 'delete') return `Order deletion saved offline`;
    return `Order update saved offline`;
  }
  if (url.includes('/sales')) {
    if (method === 'post') return `New sale${label} saved offline`;
    if (method === 'delete') return `Sale deletion saved offline`;
    return `Sale update saved offline`;
  }
  if (url.includes('/bookings')) {
    if (method === 'post') return `New booking${label} saved offline`;
    if (method === 'delete') return `Booking cancellation saved offline`;
    return `Booking update saved offline`;
  }
  if (url.includes('/customers')) {
    if (method === 'post') return `New customer${label} saved offline`;
    if (method === 'delete') return `Customer deletion saved offline`;
    return `Customer update${label} saved offline`;
  }
  if (url.includes('/expenses')) {
    if (method === 'post') return `New expense saved offline`;
    return `Expense update saved offline`;
  }
  if (url.includes('/products')) {
    if (method === 'post') return `New product${label} saved offline`;
    if (method === 'delete') return `Product deletion saved offline`;
    return `Product update${label} saved offline`;
  }
  if (url.includes('/settings') || url.includes('/business-knowledge')) {
    return `Settings update saved offline`;
  }
  return `${method.toUpperCase()} ${url} (offline)`;
}

// Resolve which cache key a mutation URL should update
function _getMutationCacheKey(url: string): string | null {
  if (url.match(/\/orders/) && !url.includes('convert-to-sale')) return 'orders';
  if (url.match(/\/sales/)) return 'sales';
  if (url.match(/\/bookings/) && !url.includes('reminder')) return 'bookings';
  if (url.match(/\/customers/)) return 'customers';
  if (url.match(/\/expenses/)) return 'expenses';
  if (url.match(/\/products/)) return 'products';
  return null;
}

// Extract entity ID from URL like /orders/abc123 → 'abc123'
function _extractEntityId(url: string): string | null {
  const match = url.match(/\/[a-z-]+\/([^/?]+)/);
  return match ? match[1] : null;
}

// After queuing a mutation, immediately patch the cached list so the UI shows it
async function _updateCacheAfterMutation(method: string, url: string, data: any, tempId: string) {
  const cacheKey = _getMutationCacheKey(url);
  if (!cacheKey) return;

  const cached = await offlineCache.getStale(cacheKey);
  if (!cached) return;

  // Resolve the actual list array (handles both [] and { items: [] } shapes)
  let list: any[] | null = null;
  let listKey: string | null = null;
  if (Array.isArray(cached)) {
    list = [...cached];
  } else if (cached && typeof cached === 'object') {
    for (const key of Object.keys(cached)) {
      if (Array.isArray((cached as any)[key])) {
        list = [...(cached as any)[key]];
        listKey = key;
        break;
      }
    }
  }
  if (!list) return;

  const entityId = _extractEntityId(url);
  let updatedList: any[];

  if (method === 'delete' && entityId) {
    updatedList = list.filter((item: any) => item.id !== entityId);
  } else if ((method === 'put' || method === 'patch') && entityId) {
    updatedList = list.map((item: any) =>
      item.id === entityId ? { ...item, ...(data || {}), _queued: true } : item
    );
  } else if (method === 'post') {
    const newItem = { ...(data || {}), id: tempId, _queued: true, created_at: new Date().toISOString() };
    updatedList = [newItem, ...list];
  } else {
    return;
  }

  const updatedCache = listKey ? { ...(cached as object), [listKey]: updatedList } : updatedList;
  await offlineCache.set(cacheKey, updatedCache);
  console.log(`[OfflineCache] Patched cache "${cacheKey}" for offline ${method.toUpperCase()} ${url}`);
}

// URL → cache key mapping for GET responses
const URL_CACHE_MAP: Record<string, string> = {
  '/customers': 'customers',
  '/customers?sort_by=recently_contacted': 'customers_recent',
  '/products': 'products',
  '/dashboard/summary': 'dashboard',
  '/bookings': 'bookings',
  '/orders': 'orders',
  '/sales': 'sales',
  '/expenses': 'expenses',
  '/settings': 'settings',
  '/business-knowledge': 'business_knowledge',
  '/contacts': 'contacts',
  '/auth/me': 'auth_me',
};

function getCacheKey(url: string): string | null {
  if (!url) return null;
  // Strip query string for matching, but keep full url for unique storage
  const base = url.split('?')[0];
  // Try full url first, then base
  return URL_CACHE_MAP[url] || URL_CACHE_MAP[base] || null;
}

// Request interceptor for logging
apiClient.interceptors.request.use(
  (config) => {
    config.headers['ngrok-skip-browser-warning'] = 'true';
    config.headers['Bypass-Tunnel-Reminder'] = 'true';
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor — caches GET responses, serves stale cache when offline
apiClient.interceptors.response.use(
  (response) => {
    console.log(`API Response Success: ${response.status}`);
    // Cache successful GET responses
    const method = response.config?.method?.toLowerCase();
    const url = response.config?.url || '';
    if (method === 'get' && response.data) {
      const cacheKey = getCacheKey(url);
      if (cacheKey) {
        offlineCache.set(cacheKey, response.data);
      }
    }
    return response;
  },
  async (error) => {
    const isNetworkError = !error.response; // No response = no internet
    const method = error.config?.method?.toLowerCase();
    const url = error.config?.url || '';

    // On network error for GET: serve stale cache
    if (isNetworkError && method === 'get') {
      const cacheKey = getCacheKey(url);
      if (cacheKey) {
        const cached = await offlineCache.getStale(cacheKey);
        if (cached) {
          console.log(`[OfflineCache] Serving stale cache for: ${url}`);
          return {
            data: cached,
            status: 200,
            statusText: 'OK (cached)',
            headers: {},
            config: error.config,
            cached: true,
          };
        }
      }
    }

    // On network error for mutations: enqueue for later sync + return optimistic success
    if (isNetworkError && method && ['post', 'put', 'patch', 'delete'].includes(method)) {
      // Skip auth, AI, and file-upload endpoints from queuing
      const skipPatterns = ['/auth/', '/ai/', '/analysis/', '/ai-description', '/ai-about', '/upload', '/send-', '/broadcast'];
      const shouldSkip = skipPatterns.some((p) => url.includes(p));
      if (!shouldSkip) {
        const requestData = error.config?.data ? JSON.parse(error.config.data) : undefined;
        const description = _getQueueDescription(method, url, requestData);
        await offlineQueue.enqueue({
          method: method.toUpperCase() as any,
          url,
          data: requestData,
          description,
        });
        console.log(`[OfflineQueue] Queued: ${description}`);
        // Patch the cached list immediately so fetchData() returns the new item
        const tempId = `offline_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
        await _updateCacheAfterMutation(method, url, requestData, tempId);
        // Return optimistic success so the UI updates normally instead of showing error
        return {
          data: { ...(requestData || {}), id: tempId, _queued: true },
          status: 200,
          statusText: 'Queued (offline)',
          headers: {},
          config: error.config,
          _offlineQueued: true,
        };
      }
    }

    if (error.response) {
      console.error('=== API ERROR DETAILS ===');
      console.error('Error message:', error.message);
      console.error('Error config:', error.config?.url);
      console.error('Error response:', JSON.stringify(error.response?.data));
      console.error('Error status:', error.response?.status);
    } else {
      console.warn(`[Offline] Network error on ${method?.toUpperCase()} ${url}`);
    }
    return Promise.reject(error);
  }
);

// Register queue sync handler — replays mutations using apiClient
offlineQueue.registerSyncHandler(async (mutation) => {
  await apiClient.request({
    method: mutation.method,
    url: mutation.url,
    data: mutation.data,
  });
});

// ============ AI API Methods ============

export const aiAPI = {
  /**
   * Draft an AI-generated follow-up message for a customer
   */
  draftMessage: async (customerId: string, tone: string = 'friendly', customInstructions?: string) => {
    const response = await apiClient.post('/ai/draft-message', {
      customer_id: customerId,
      tone,
      custom_instructions: customInstructions
    });
    return response.data;
  },

  /**
   * Send an auto-drafted message (requires auto-reply enabled)
   */
  sendAutoMessage: async (customerId: string, message: string) => {
    const response = await apiClient.post('/ai/send-auto-message', {
      customer_id: customerId,
      message
    });
    return response.data;
  },

  /**
   * Get today's customer insights from AI analysis
   */
  getDailyInsights: async (limit: number = 10) => {
    const response = await apiClient.get('/analysis/daily-insights', {
      params: { limit }
    });
    return response.data;
  },

  /**
   * Manually trigger customer analysis
   */
  runAnalysisNow: async () => {
    const response = await apiClient.post('/analysis/run-now');
    return response.data;
  }
};

// ============ Settings API Methods ============

export const settingsAPI = {
  /**
   * Get user settings
   */
  getSettings: async () => {
    const response = await apiClient.get('/settings');
    return response.data;
  },

  /**
   * Update user settings
   */
  updateSettings: async (settings: {
    auto_reply_enabled?: boolean;
    notification_enabled?: boolean;
    notification_time?: string;
    daily_alert_count?: number;
    message_tone?: string;
    push_token?: string;
    daily_pulse_enabled?: boolean;
    daily_pulse_time?: string;
    currency?: string;
    country_code?: string;
    ai_model?: string;
    auto_reply_audience?: 'everyone' | 'customers_only' | 'new_contacts_only';
    business_type?: string;
  }) => {
    const response = await apiClient.put('/settings', settings);
    return response.data;
  },

  /**
   * Register push notification token
   */
  registerPushToken: async (pushToken: string) => {
    const response = await apiClient.post('/notifications/register-token', {
      push_token: pushToken
    });
    return response.data;
  },

  /**
   * Send test notification
   */
  sendTestNotification: async () => {
    const response = await apiClient.post('/notifications/send-test');
    return response.data;
  },

  /**
   * Get business knowledge
   */
  getBusinessKnowledge: async () => {
    const response = await apiClient.get('/business-knowledge');
    return response.data;
  },

  /**
   * Update business knowledge
   */
  updateBusinessKnowledge: async (knowledge: {
    products_services?: string;
    pricing_info?: string;
    business_hours?: string;
    delivery_info?: string;
    faqs?: string;
    special_offers?: string;
    business_description?: string;
  }) => {
    const response = await apiClient.put('/business-knowledge', knowledge);
    return response.data;
  },

  /**
   * Generate AI description for business About section
   */
  generateBusinessAbout: async (params: {
    business_type: string;
    current_description?: string;
    mode?: 'generate' | 'improve';
  }) => {
    const response = await apiClient.post('/settings/ai-about', {
      business_type: params.business_type,
      current_description: params.current_description,
      mode: params.mode || 'generate',
    });
    return response.data;
  }
};

// ============ WhatsApp API Methods ============

export const whatsappAPI = {
  /**
   * Start WhatsApp pairing: returns 8-digit code for Linked Devices
   */
  connect: async (phoneNumber: string) => {
    const response = await apiClient.post('/whatsapp/connect', { phone_number: phoneNumber });
    return response.data;
  },

  /**
   * Get WhatsApp connection status and message usage
   */
  getStatus: async () => {
    const response = await apiClient.get('/whatsapp/status');
    return response.data;
  },

  /**
   * Sync WhatsApp contacts and chat history into the CRM
   */
  sync: async () => {
    const response = await apiClient.post('/whatsapp/sync', {}, { timeout: 180000 });
    return response.data;
  },

  /**
   * Disconnect WhatsApp instance
   */
  disconnect: async () => {
    const response = await apiClient.post('/whatsapp/disconnect');
    return response.data;
  },

  /**
   * Send a WhatsApp message to a customer
   */
  sendMessage: async (toNumber: string, message: string, customerName?: string) => {
    const response = await apiClient.post('/messages/send', null, {
      params: { to_number: toNumber, message, customer_name: customerName },
    });
    return response.data;
  },

  /**
   * Send a media file (image/document) to a customer via WhatsApp
   */
  sendMedia: async (toNumber: string, fileUri: string, fileName: string, mimeType: string, caption?: string, customerName?: string) => {
    const formData = new FormData();
    formData.append('file', {
      uri: fileUri,
      name: fileName,
      type: mimeType,
    } as any);
    formData.append('to_number', toNumber);
    formData.append('caption', caption || '');
    if (customerName) formData.append('customer_name', customerName);
    return await uploadFetch('/messages/send-media', formData);
  },

  /**
   * Get message history for a customer
   */
  getMessages: async (customerId: string) => {
    const response = await apiClient.get(`/customers/${customerId}/messages`);
    return response.data;
  },
};

// ============ Messages API Methods ============

export const messagesAPI = {
  /**
   * Store a message in the database
   */
  storeMessage: async (customerId: string, content: string, direction: 'incoming' | 'outgoing') => {
    const response = await apiClient.post(`/customers/${customerId}/messages`, {
      customer_id: customerId,
      direction,
      content,
      message_type: 'text'
    });
    return response.data;
  },

  /**
   * Get message history for a customer
   */
  getMessages: async (customerId: string) => {
    const response = await apiClient.get(`/customers/${customerId}/messages`);
    return response.data;
  }
};

// ============ Contact Classification API ============

export const classificationAPI = {
  scanContacts: async () => {
    const response = await apiClient.post('/contacts/classify');
    return response.data;
  },
  getPending: async () => {
    const response = await apiClient.get('/contacts/pending');
    return response.data;
  },
  confirm: async (customerId: string, action: 'approve' | 'reject', type: 'customer' | 'supplier') => {
    const response = await apiClient.post(`/contacts/${customerId}/confirm`, { action, type });
    return response.data;
  },
  dismiss: async (customerId: string) => {
    const response = await apiClient.post(`/contacts/${customerId}/dismiss`);
    return response.data;
  },
};

// ============ Suppliers API Methods ============

export const suppliersAPI = {
  getInsights: async () => {
    const response = await apiClient.get('/suppliers/insights');
    return response.data;
  },
  getSuppliers: async () => {
    const response = await apiClient.get('/suppliers');
    return response.data;
  },
  getCategories: async () => {
    const response = await apiClient.get('/suppliers/categories');
    return response.data;
  },
  tagSupplier: async (customerId: string) => {
    const response = await apiClient.post(`/suppliers/${customerId}/tag`);
    return response.data;
  },
  updateSupplier: async (customerId: string, data: {
    supplier_category?: string;
    products_supplied?: string[];
    payment_terms?: string;
    lead_time?: string;
    rating?: number;
  }) => {
    const response = await apiClient.put(`/suppliers/${customerId}`, data);
    return response.data;
  },
  removeSupplier: async (customerId: string) => {
    const response = await apiClient.delete(`/suppliers/${customerId}`);
    return response.data;
  },
};

// ============ Products API Methods ============

export const productsAPI = {
  /**
   * Upload multiple product images with AI analysis
   */
  uploadProducts: async (files: any[]) => {
    const formData = new FormData();

    files.forEach((file, index) => {
      // Expo ImagePicker returns type: "image" which is not a valid MIME type
      let mimeType = file.mimeType || file.type || 'image/jpeg';
      if (mimeType === 'image' || !mimeType.includes('/')) {
        mimeType = 'image/jpeg';
      }
      const fileName = file.fileName || file.uri.split('/').pop() || `product_${index}.jpg`;
      formData.append('files', {
        uri: file.uri,
        type: mimeType,
        name: fileName,
      } as any);
    });

    // Use 120s timeout — AI image analysis can take a while
    return await uploadFetch('/products/upload', formData, 120000);
  },

  /**
   * Get all products
   */
  getProducts: async (category?: string, inStock?: boolean) => {
    const params: any = {};
    if (category) params.category = category;
    if (inStock !== undefined) params.in_stock = inStock;

    const response = await apiClient.get('/products', { params });
    return response.data;
  },

  /**
   * Get single product
   */
  getProduct: async (productId: string) => {
    const response = await apiClient.get(`/products/${productId}`);
    return response.data;
  },

  /**
   * Create a new product
   */
  createProduct: async (product: {
    name: string;
    price: number;
    discount_price?: number;
    category?: string;
    description?: string;
    in_stock?: boolean;
  }) => {
    const response = await apiClient.post('/products', product);
    return response.data;
  },

  /**
   * Update product
   */
  updateProduct: async (productId: string, updates: {
    name?: string;
    price?: number;
    discount_price?: number;
    category?: string;
    description?: string;
    in_stock?: boolean;
  }) => {
    const response = await apiClient.put(`/products/${productId}`, updates);
    return response.data;
  },

  /**
   * Delete product
   */
  deleteProduct: async (productId: string) => {
    const response = await apiClient.delete(`/products/${productId}`);
    return response.data;
  },

  /**
   * Add images to an existing product
   */
  addProductImages: async (productId: string, files: any[]) => {
    const formData = new FormData();
    files.forEach((file, index) => {
      let mimeType = file.mimeType || file.type || 'image/jpeg';
      if (mimeType === 'image' || !mimeType.includes('/')) {
        mimeType = 'image/jpeg';
      }
      const fileName = file.fileName || file.uri.split('/').pop() || `photo_${index}.jpg`;
      formData.append('files', {
        uri: file.uri,
        type: mimeType,
        name: fileName,
      } as any);
    });
    return await uploadFetch(`/products/${productId}/images`, formData);
  },

  /**
   * Delete a specific image from a product
   */
  deleteProductImage: async (productId: string, imageIndex: number) => {
    const response = await apiClient.delete(`/products/${productId}/images/${imageIndex}`);
    return response.data;
  },

  /**
   * Send product to customer via WhatsApp API (with image)
   */
  sendProductToCustomer: async (productId: string, customerId: string) => {
    const response = await apiClient.post(`/products/${productId}/send`, null, {
      params: { customer_id: customerId }
    });
    return response.data;
  },

  /**
   * Send multiple products as a catalog to customer via WhatsApp
   */
  sendCatalog: async (customerId: string, productIds: string[]) => {
    const response = await apiClient.post('/products/send-catalog', {
      customer_id: customerId,
      product_ids: productIds,
    });
    return response.data;
  },

  /**
   * Broadcast a product catalog to multiple customers
   */
  broadcastCatalog: async (productIds: string[], filterType: string, customerIds?: string[]) => {
    const response = await apiClient.post('/products/broadcast-catalog', {
      product_ids: productIds,
      filter_type: filterType,
      customer_ids: customerIds,
    });
    return response.data;
  },

  /**
   * Generate AI description for product based on business type
   */
  generateAIDescription: async (params: {
    product_name: string;
    category?: string;
    business_type?: string;
    current_description?: string;
    mode?: 'generate' | 'improve';
  }) => {
    const response = await apiClient.post('/products/ai-description', {
      product_name: params.product_name,
      category: params.category,
      business_type: params.business_type,
      current_description: params.current_description,
      mode: params.mode || 'generate',
    });
    return response.data;
  }
};

// ============ DASHBOARD API ============
export const dashboardAPI = {
  getSummary: async () => {
    const response = await apiClient.get('/dashboard/summary');
    return response.data;
  },
};

// ============ MESSAGE HELPERS ============
export const messageHelpers = {
  markRead: async (customerId: string) => {
    const response = await apiClient.post(`/customers/${customerId}/messages/read`);
    return response.data;
  },
  search: async (customerId: string, query: string) => {
    const response = await apiClient.get(`/customers/${customerId}/messages/search`, { params: { q: query } });
    return response.data;
  },
  getTimeline: async (customerId: string) => {
    const response = await apiClient.get(`/customers/${customerId}/timeline`);
    return response.data;
  },
};

// ============ TEAM MANAGEMENT ============
export const teamAPI = {
  /**
   * Invite a new team member
   */
  inviteMember: async (data: { phone_number: string; name: string; role: string; email?: string }) => {
    const response = await apiClient.post('/team/invite', data);
    return response.data;
  },

  /**
   * Get all team members
   */
  getMembers: async () => {
    const response = await apiClient.get('/team/members');
    return response.data;
  },

  /**
   * Update team member
   */
  updateMember: async (memberId: string, updates: { name?: string; role?: string; status?: string }) => {
    const response = await apiClient.put(`/team/members/${memberId}`, updates);
    return response.data;
  },

  /**
   * Remove team member
   */
  removeMember: async (memberId: string) => {
    const response = await apiClient.delete(`/team/members/${memberId}`);
    return response.data;
  },

  /**
   * Assign conversation to team member
   */
  assignConversation: async (data: { customer_id: string; assigned_to: string | null; assigned_by: string; notes?: string }) => {
    const response = await apiClient.post('/conversations/assign', data);
    return response.data;
  },

  /**
   * Get all conversation assignments
   */
  getAssignments: async () => {
    const response = await apiClient.get('/conversations/assignments');
    return response.data;
  },

  /**
   * Get my assigned conversations
   */
  getMyAssignments: async () => {
    const response = await apiClient.get('/conversations/my-assignments');
    return response.data;
  },

  /**
   * Get activity logs
   */
  getActivityLogs: async (params?: { limit?: number; user_id?: string; entity_type?: string }) => {
    const response = await apiClient.get('/activity/logs', { params });
    return response.data;
  },
};

// ============ BOOKINGS ============
export const bookingsAPI = {
  getBookings: async (status?: string) => {
    const response = await apiClient.get('/bookings', { params: status ? { status } : undefined });
    return response.data;
  },

  createBooking: async (data: {
    customer_id?: string;
    customer_name?: string;
    service_id: string;
    date: string;
    time?: string;
    checkin_date?: string;
    checkout_date?: string;
    staff_name?: string;
    capacity?: number;
    notes?: string;
    price?: number;
  }) => {
    const response = await apiClient.post('/bookings', data);
    return response.data;
  },

  updateBooking: async (bookingId: string, data: {
    status?: string;
    payment_status?: string;
    staff_name?: string;
    notes?: string;
  }) => {
    const response = await apiClient.put(`/bookings/${bookingId}`, data);
    return response.data;
  },

  deleteBooking: async (bookingId: string) => {
    const response = await apiClient.delete(`/bookings/${bookingId}`);
    return response.data;
  },

  sendReminder: async (bookingId: string) => {
    const response = await apiClient.post(`/bookings/${bookingId}/reminder`);
    return response.data;
  },
};

// ============ ORDERS ============
export const ordersAPI = {
  /**
   * Get all orders (cached offline)
   */
  getOrders: async (params?: { limit?: number; customer_id?: string }) => {
    const response = await apiClient.get('/orders', { params });
    return response.data;
  },

  /**
   * Create a new order (works offline — will be queued)
   */
  createOrder: async (data: {
    customer_id?: string;
    customer_name?: string;
    product: string;
    quantity: number;
    price: number;
    payment_method?: string;
    notes?: string;
  }) => {
    const response = await apiClient.post('/orders', data);
    return response.data;
  },

  /**
   * Update order payment status (works offline — will be queued)
   */
  updatePaymentStatus: async (orderId: string, payment_status: string) => {
    const response = await apiClient.put(`/orders/${orderId}?payment_status=${payment_status}`);
    return response.data;
  },

  /**
   * Update order delivery status (works offline — will be queued)
   */
  updateDeliveryStatus: async (orderId: string, delivery_status: string) => {
    const response = await apiClient.put(`/orders/${orderId}?delivery_status=${delivery_status}`);
    return response.data;
  },

  /**
   * Convert order to sale (requires internet — skip queue)
   */
  convertToSale: async (orderId: string, payment_method: string) => {
    const response = await apiClient.post(`/orders/${orderId}/convert-to-sale?payment_method=${encodeURIComponent(payment_method)}`);
    return response.data;
  },

  /**
   * Delete an order (works offline — will be queued)
   */
  deleteOrder: async (orderId: string) => {
    const response = await apiClient.delete(`/orders/${orderId}`);
    return response.data;
  },
};

// ============ SALES ============
export const salesAPI = {
  /**
   * Get all sales
   */
  getSales: async (params?: { limit?: number; customer_id?: string }) => {
    const response = await apiClient.get('/sales', { params });
    return response.data;
  },

  /**
   * Create a new sale (works offline - will be queued)
   */
  createSale: async (data: {
    customer_id?: string;
    customer_name?: string;
    product_id?: string;
    product_name?: string;
    amount: number;
    quantity?: number;
    payment_method?: string;
    notes?: string;
    sale_date?: string;
  }) => {
    const response = await apiClient.post('/sales', data);
    return response.data;
  },

  /**
   * Update a sale
   */
  updateSale: async (saleId: string, data: {
    amount?: number;
    payment_method?: string;
    notes?: string;
  }) => {
    const response = await apiClient.put(`/sales/${saleId}`, data);
    return response.data;
  },

  /**
   * Delete a sale
   */
  deleteSale: async (saleId: string) => {
    const response = await apiClient.delete(`/sales/${saleId}`);
    return response.data;
  },
};

// ============ ACCOUNT MANAGEMENT ============
export const accountAPI = {
  /**
   * Permanently delete user account and all data (GDPR/CCPA)
   */
  deleteAccount: async () => {
    const response = await apiClient.delete('/account');
    return response.data;
  },

  /**
   * Export all user data as JSON (GDPR data portability)
   */
  exportData: async () => {
    const response = await apiClient.get('/account/export');
    return response.data;
  },
};

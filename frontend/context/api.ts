import axios from 'axios';

// Expo public variables are embedded when an update is bundled.  A missing
// value must never send a production install to its own localhost instance.
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

// Request interceptor for logging
apiClient.interceptors.request.use(
  (config) => {
    // Force ngrok bypass headers on every request to avoid 503 interstitial page
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

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    console.log(`API Response Success: ${response.status}`);
    return response;
  },
  (error) => {
    console.error('=== API ERROR DETAILS ===');
    console.error('Error message:', error.message);
    console.error('Error config:', error.config?.url);
    console.error('Error response:', error.response?.data);
    console.error('Error status:', error.response?.status);
    console.error('Full error:', JSON.stringify(error, null, 2));
    return Promise.reject(error);
  }
);

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

  /** Refresh an expiring pairing code without resetting the linked-device session. */
  refreshPairingCode: async (phoneNumber: string) => {
    const response = await apiClient.post('/whatsapp/refresh', { phone_number: phoneNumber });
    return response.data;
  },

  /** Fetch the current QR fallback for a pending WhatsApp link. */
  getQr: async () => {
    const response = await apiClient.get('/whatsapp/qr');
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
  /** Upload product photos and create reviewable product drafts. */
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

    // Allow time for remote image storage on slower mobile connections.
    return await uploadFetch('/products/upload', formData, 120000);
  },

  /** Get optional AI suggestions for one existing product photo. */
  suggestProductDetails: async (productId: string) => {
    const response = await apiClient.post(`/products/${productId}/suggest-details`);
    return response.data;
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
  }
};

// ============ Public Storefront API Methods ============

export const storefrontAPI = {
  getMyStorefront: async () => {
    const response = await apiClient.get('/storefront/me');
    return response.data as {
      slug: string;
      public_url: string;
      payment_provider: string;
      available_payment_providers: string[];
      preferred_slug: string;
      name_taken: boolean;
      name_reserved: boolean;
    };
  },

  // Used during sign-up, before there is an account to authenticate with.
  checkNameAvailable: async (name: string) => {
    const response = await apiClient.get('/storefront/name-available', { params: { name } });
    return response.data as {
      slug: string;
      available: boolean;
      reason: '' | 'invalid' | 'reserved' | 'taken';
    };
  },
};

// ============ Paystack (Kenya merchant payouts) ============

export type PaystackPayoutType = 'bank' | 'mobile_money';

export interface PaystackPayoutOption {
  code: string;
  name: string;
}

export interface PaystackConnection {
  connected: boolean;
  business_name: string | null;
  default_currency: string | null;
  payout_type: PaystackPayoutType | null;
  subaccount_code: string | null;
  subaccount_name: string | null;
  settlement_bank: string | null;
  account_number: string | null;
  auth_mode: string | null;
  platform_managed: boolean;
  platform_available: boolean;
}

export const paystackAPI = {
  getSetup: async () => {
    const response = await apiClient.get('/paystack/setup');
    return response.data as {
      platform_available: boolean;
      platform_country: string;
      currencies: string[];
      default_currency: string;
      payout_types: PaystackPayoutType[];
      mobile_money_currencies: string[];
    };
  },

  getConnection: async () => {
    const response = await apiClient.get('/paystack/connection');
    return response.data as PaystackConnection;
  },

  getPayoutOptions: async (payoutType: PaystackPayoutType) => {
    const response = await apiClient.get('/paystack/payout-options', {
      params: { currency: 'KES', payout_type: payoutType },
    });
    return response.data as {
      currency: string;
      payout_type: PaystackPayoutType;
      options: PaystackPayoutOption[];
      supported: boolean;
      hint?: string;
    };
  },

  connectKenya: async (payload: {
    business_name: string;
    payout_type: PaystackPayoutType;
    settlement_bank: string;
    account_number: string;
  }) => {
    const response = await apiClient.post('/paystack/connect', {
      ...payload,
      currency: 'KES',
    });
    return response.data as PaystackConnection;
  },

  disconnect: async () => {
    const response = await apiClient.delete('/paystack/connect');
    return response.data as { connected: boolean; status: string };
  },
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
  inviteMember: async (data: { phone_number?: string; name: string; role: string; email?: string }) => {
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

// ============ Bookings API Methods ============

export const bookingsAPI = {
  getBookings: async (params?: { customer_id?: string; status?: string }) => {
    const response = await apiClient.get('/bookings', { params });
    return response.data;
  },

  createBooking: async (booking: Record<string, any>) => {
    const response = await apiClient.post('/bookings', booking);
    return response.data;
  },

  updateBooking: async (bookingId: string, updates: Record<string, any>) => {
    const response = await apiClient.put(`/bookings/${bookingId}`, updates);
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

// ============ Workflows API Methods ============

export const workflowsAPI = {
  list: async () => {
    const response = await apiClient.get('/workflows');
    return response.data;
  },

  create: async (workflow: Record<string, any>) => {
    const response = await apiClient.post('/workflows', workflow);
    return response.data;
  },

  toggle: async (workflowId: string) => {
    const response = await apiClient.post(`/workflows/${workflowId}/toggle`);
    return response.data;
  },

  delete: async (workflowId: string) => {
    const response = await apiClient.delete(`/workflows/${workflowId}`);
    return response.data;
  },

  buildFromDescription: async (description: string) => {
    const response = await apiClient.post('/workflows/build/from-description', { description });
    return response.data;
  },
};

// ============ Feedback API Methods ============

export const feedbackAPI = {
  listSurveys: async () => {
    const response = await apiClient.get('/feedback/surveys');
    return response.data;
  },

  getSurvey: async (surveyId: string) => {
    const response = await apiClient.get(`/feedback/surveys/${surveyId}`);
    return response.data;
  },

  createSurvey: async (payload: {
    title: string;
    description?: string;
    active?: boolean;
    questions: Array<{ id: string; text: string; type: 'nps' | 'rating' | 'text' | 'choice'; options?: string[] }>;
  }) => {
    const response = await apiClient.post('/feedback/surveys', payload);
    return response.data;
  },

  submitResponse: async (payload: {
    survey_id: string;
    customer_id?: string;
    answers: Array<{ question_id: string; answer: any }>;
    customer_name?: string;
    customer_phone?: string;
    nps_score?: number;
    comment?: string;
  }) => {
    const response = await apiClient.post('/feedback/responses', payload);
    return response.data;
  },

  getResponse: async (responseId: string) => {
    const response = await apiClient.get(`/feedback/responses/${responseId}`);
    return response.data;
  },

  getCustomerResponses: async (customerId: string) => {
    const response = await apiClient.get(`/feedback/customer/${customerId}`);
    return response.data;
  },

  sendSurveyLink: async (surveyId: string, customerId: string, deliveryMode: 'link' | 'whatsapp_chat' = 'link') => {
    const response = await apiClient.post(`/feedback/surveys/${surveyId}/send`, {
      customer_id: customerId,
      delivery_mode: deliveryMode,
    });
    return response.data;
  },
};

// ============ Loyalty API Methods ============

export const loyaltyAPI = {
  getPoints: async (customerId: string) => {
    const response = await apiClient.get(`/loyalty/${customerId}`);
    return response.data;
  },

  addPoints: async (customerId: string, amount: number, reason?: string) => {
    const response = await apiClient.post(`/loyalty/${customerId}/add`, {
      points: amount,
      reason,
    });
    return response.data;
  },

  getHistory: async (customerId: string) => {
    const response = await apiClient.get(`/loyalty/${customerId}/history`);
    return response.data;
  },
};

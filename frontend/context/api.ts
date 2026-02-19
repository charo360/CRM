import axios from 'axios';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || 'http://localhost:8000';

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
const uploadFetch = async (path: string, formData: FormData) => {
  const token = apiClient.defaults.headers.common['Authorization'];
  const res = await fetch(`${API_URL}/api${path}`, {
    method: 'POST',
    headers: {
      'Bypass-Tunnel-Reminder': 'true',
      'ngrok-skip-browser-warning': 'true',
      ...(token ? { 'Authorization': token as string } : {}),
    },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return res.json();
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

    return await uploadFetch('/products/upload', formData);
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

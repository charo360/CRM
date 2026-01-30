import axios from 'axios';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Request interceptor for logging
apiClient.interceptors.request.use(
  (config) => {
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

// ============ Products API Methods ============

export const productsAPI = {
  /**
   * Upload multiple product images with AI analysis
   */
  uploadProducts: async (files: any[]) => {
    const formData = new FormData();

    files.forEach((file, index) => {
      formData.append('files', {
        uri: file.uri,
        type: file.type || 'image/jpeg',
        name: file.fileName || `product_${index}.jpg`,
      } as any);
    });

    const response = await apiClient.post('/products/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
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
   * Update product
   */
  updateProduct: async (productId: string, updates: {
    name?: string;
    price?: number;
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
   * Send product to customer
   */
  sendProductToCustomer: async (productId: string, customerId: string) => {
    const response = await apiClient.post(`/products/${productId}/send`, null, {
      params: { customer_id: customerId }
    });
    return response.data;
  }
};

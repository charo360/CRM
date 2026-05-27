/**
 * AI Scout API Client
 * Connects HTML pages to backend /api/action-mode/* endpoints
 */

const API_BASE = 'http://127.0.0.1:8000/api';

// Get auth token from localStorage
function getToken() {
  return localStorage.getItem('token') || localStorage.getItem('access_token');
}

// Make authenticated API request
async function request(path, options = {}) {
  const token = getToken();
  
  const config = {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...(options.headers || {})
    }
  };

  const response = await fetch(`${API_BASE}${path}`, config);
  
  if (!response.ok) {
    const text = await response.text();
    let errorMsg = `${response.status}: ${response.statusText}`;
    try {
      const json = JSON.parse(text);
      errorMsg = json.detail || json.error || json.message || errorMsg;
    } catch (e) {
      errorMsg = text || errorMsg;
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

// API methods
const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { 
    method: 'POST', 
    body: JSON.stringify(body) 
  }),
  put: (path, body) => request(path, { 
    method: 'PUT', 
    body: JSON.stringify(body) 
  }),
  delete: (path) => request(path, { method: 'DELETE' })
};

// AI Scout specific API calls
const scoutApi = {
  // Load all data
  loadAll: async () => {
    const [
      settings,
      feed,
      queue,
      opportunities,
      agents,
      socialSettings,
      clusters,
      predictions,
      recon,
      instantActions,
      scouts,
      pulse
    ] = await Promise.all([
      api.get('/action-mode/settings'),
      api.get('/action-mode/feed'),
      api.get('/action-mode/queue'),
      api.get('/action-mode/opportunities'),
      api.get('/action-mode/agents'),
      api.get('/action-mode/social/settings'),
      api.get('/action-mode/clusters'),
      api.get('/action-mode/predictions'),
      api.get('/action-mode/recon'),
      api.get('/action-mode/instant'),
      api.get('/action-mode/scouts'),
      api.get('/action-mode/scouts/pulse')
    ]);

    return {
      settings,
      feed: feed.items || [],
      queue: queue.items || [],
      opportunities: opportunities.opportunities || [],
      agents: agents.agents || [],
      socialSettings,
      clusters: clusters.clusters || [],
      predictions: predictions.predictions || [],
      recon: recon.recon || [],
      instantActions: instantActions.items || [],
      scouts: scouts.scouts || [],
      pulse: pulse.pulse || []
    };
  },

  // Get opportunities (leads)
  getOpportunities: () => api.get('/action-mode/opportunities'),

  // Get social settings
  getSocialSettings: () => api.get('/action-mode/social/settings'),

  // Update social settings
  updateSocialSettings: (settings) => api.put('/action-mode/social/settings', settings),

  // Run social scan
  runSocial: () => api.post('/action-mode/run-social', {}),

  // Run all scouts
  runAll: () => api.post('/action-mode/run', {}),

  // Run specific scout
  runScout: (id) => api.post(`/action-mode/scouts/${id}/run`, {}),

  // Setup scouts
  setupScouts: () => api.post('/action-mode/scouts/setup', {}),

  // Toggle scout
  toggleScout: (id, isActive) => api.put(`/action-mode/scouts/${id}`, { is_active: isActive }),

  // Delete scout
  deleteScout: (id) => api.delete(`/action-mode/scouts/${id}`),

  // Dismiss opportunity
  dismissOpportunity: (id) => api.delete(`/action-mode/opportunities/${id}`),

  // Add to CRM
  addToCRM: (data) => api.post('/contacts', {
    name: data.name || data.title,
    phone: data.contact_info || data.phone,
    notes: data.snippet || data.description,
    source: 'ai_scout',
    source_url: data.url
  }),

  // Get feed
  getFeed: () => api.get('/action-mode/feed'),

  // Get clusters
  getClusters: () => api.get('/action-mode/clusters'),

  // Get predictions
  getPredictions: () => api.get('/action-mode/predictions'),

  // Get recon
  getRecon: () => api.get('/action-mode/recon'),

  // Delete cluster
  deleteCluster: (id) => api.delete(`/action-mode/clusters/${id}`),

  // Delete prediction
  deletePrediction: (id) => api.delete(`/action-mode/predictions/${id}`),

  // Delete recon
  deleteRecon: (id) => api.delete(`/action-mode/recon/${id}`),

  // Update settings
  updateSettings: (settings) => api.put('/action-mode/settings', settings),

  // Queue actions
  approveQueueItem: (itemId, content) => api.post('/action-mode/queue/action', {
    item_id: itemId,
    action: 'approve',
    edited_content: content
  }),

  skipQueueItem: (itemId) => api.post('/action-mode/queue/action', {
    item_id: itemId,
    action: 'skip'
  }),

  // Run fusion engine
  runFusion: () => api.post('/action-mode/clusters/run', {}),

  // Run predictions
  runPredictions: () => api.post('/action-mode/predictions/run', {}),

  // Run recon
  runRecon: () => api.post('/action-mode/recon/run', {}),

  // Generate instant actions
  generateInstantActions: () => api.post('/action-mode/instant/generate', {}),

  // Approve instant action
  approveInstantAction: (id) => api.post(`/action-mode/instant/${id}/approve`, {}),

  // Reject instant action
  rejectInstantAction: (id) => api.delete(`/action-mode/instant/${id}`)
};

// Helper: Format time ago
function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60000);
  
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// Helper: Show toast notification
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 20px;
    background: ${type === 'error' ? '#DC2626' : type === 'success' ? '#059669' : '#2563EB'};
    color: white;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    z-index: 10000;
    animation: slideIn 0.3s ease-out;
  `;
  
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease-out';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// Add animation styles
if (!document.getElementById('toast-styles')) {
  const style = document.createElement('style');
  style.id = 'toast-styles';
  style.textContent = `
    @keyframes slideIn {
      from { transform: translateX(400px); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(400px); opacity: 0; }
    }
  `;
  document.head.appendChild(style);
}

/**
 * Zilo Behavior Tracker
 * Tracks visitor behavior and triggers discount campaigns
 * 
 * Installation:
 * Add this script to your website after the GA4 tracking code:
 * <script src="https://yourdomain.com/tracking/zilo-behavior-tracker.js"></script>
 * <script>
 *   ZiloBehaviorTracker.init({
 *     businessId: 'YOUR_BUSINESS_ID',
 *     apiUrl: 'https://crm.zilo.pro/api'
 *   });
 * </script>
 */

(function(window) {
  'use strict';

  const ZiloBehaviorTracker = {
    config: {
      businessId: null,
      apiUrl: null,
      visitorId: null,
    },
    
    sessionStartTime: Date.now(),
    pageViewCount: 0,
    viewedProducts: new Set(),
    cartValue: 0,
    exitIntentTriggered: false,
    
    /**
     * Initialize the tracker
     */
    init: function(options) {
      if (!options.businessId || !options.apiUrl) {
        console.error('[Zilo] businessId and apiUrl are required');
        return;
      }
      
      this.config.businessId = options.businessId;
      this.config.apiUrl = options.apiUrl.replace(/\/$/, '');
      this.config.visitorId = this.getOrCreateVisitorId();
      
      this.setupTracking();
      console.log('[Zilo] Behavior tracker initialized');
    },
    
    /**
     * Get or create a unique visitor ID
     */
    getOrCreateVisitorId: function() {
      let visitorId = localStorage.getItem('zilo_visitor_id');
      
      if (!visitorId) {
        // Try to get GA4 client_id if available
        if (window.gtag && window.dataLayer) {
          try {
            gtag('get', 'G-*', 'client_id', function(clientId) {
              if (clientId) {
                visitorId = clientId;
                localStorage.setItem('zilo_visitor_id', visitorId);
              }
            });
          } catch (e) {
            console.warn('[Zilo] Could not get GA4 client_id');
          }
        }
        
        // Fallback: generate random ID
        if (!visitorId) {
          visitorId = 'visitor_' + Math.random().toString(36).substr(2, 9) + Date.now();
          localStorage.setItem('zilo_visitor_id', visitorId);
        }
      }
      
      return visitorId;
    },
    
    /**
     * Setup all tracking listeners
     */
    setupTracking: function() {
      // Track page view
      this.trackPageView();
      
      // Track exit intent
      document.addEventListener('mouseleave', this.handleExitIntent.bind(this));
      
      // Track time on site
      setInterval(this.checkTimeOnSite.bind(this), 30000); // Every 30 seconds
      
      // Listen for GA4 events
      if (window.dataLayer) {
        this.interceptGA4Events();
      }
      
      // Track scroll depth
      this.trackScrollDepth();
      
      // Check for pending discount offers
      this.checkPendingOffers();

      // Inject floating storefront customer support chat widget
      this.injectChatWidget();
    },
    
    /**
     * Track page view
     */
    trackPageView: function() {
      this.pageViewCount++;
      
      // First-time visitor
      if (this.pageViewCount === 1) {
        this.trackEvent('first_time_visitor', {});
      }
      
      // Page views threshold
      if (this.pageViewCount === 3 || this.pageViewCount === 5) {
        this.trackEvent('page_views_threshold', {
          page_views: this.pageViewCount,
        });
      }
    },
    
    /**
     * Handle exit intent
     */
    handleExitIntent: function(e) {
      if (e.clientY <= 0 && !this.exitIntentTriggered) {
        this.exitIntentTriggered = true;
        this.trackEvent('exit_intent', {
          page_views: this.pageViewCount,
          time_on_site: this.getTimeOnSite(),
        });
      }
    },
    
    /**
     * Check time on site
     */
    checkTimeOnSite: function() {
      const timeOnSite = this.getTimeOnSite();
      
      if (timeOnSite >= 120 && timeOnSite % 30 === 0) {
        this.trackEvent('time_on_site', {
          time_on_site: timeOnSite,
        });
      }
    },
    
    /**
     * Get time on site in seconds
     */
    getTimeOnSite: function() {
      return Math.floor((Date.now() - this.sessionStartTime) / 1000);
    },
    
    /**
     * Intercept GA4 events
     */
    interceptGA4Events: function() {
      const originalPush = window.dataLayer.push;
      const self = this;
      
      window.dataLayer.push = function() {
        const args = Array.prototype.slice.call(arguments);
        
        // Check for GA4 events
        args.forEach(function(item) {
          if (item && item[0] === 'event') {
            const eventName = item[1];
            const eventParams = item[2] || {};
            
            switch (eventName) {
              case 'add_to_cart':
                self.handleAddToCart(eventParams);
                break;
              case 'view_item':
                self.handleViewItem(eventParams);
                break;
              case 'begin_checkout':
                self.handleBeginCheckout(eventParams);
                break;
              case 'purchase':
                self.handlePurchase(eventParams);
                break;
            }
          }
        });
        
        return originalPush.apply(window.dataLayer, arguments);
      };
    },
    
    /**
     * Handle add to cart event
     */
    handleAddToCart: function(params) {
      const value = params.value || params.price || 0;
      this.cartValue += value;
      
      // Track cart addition
      this.trackEvent('browsed_product', {
        product_id: params.item_id || params.product_id,
        product_name: params.item_name || params.product_name,
        cart_value: this.cartValue,
      });
      
      // Set timeout to detect cart abandonment (5 minutes)
      setTimeout(() => {
        if (this.cartValue > 0) {
          this.trackEvent('cart_abandoned', {
            cart_value: this.cartValue,
          });
        }
      }, 300000);
    },
    
    /**
     * Handle view item event
     */
    handleViewItem: function(params) {
      const productId = params.item_id || params.product_id;
      if (productId) {
        this.viewedProducts.add(productId);
        
        // If viewed same product multiple times
        if (this.viewedProducts.size >= 2) {
          this.trackEvent('browsed_product', {
            product_id: productId,
            product_name: params.item_name || params.product_name,
            view_count: this.viewedProducts.size,
          });
        }
        
        // Check if high-value product
        const price = params.price || params.value || 0;
        if (price > 100) {
          this.trackEvent('high_value_visitor', {
            product_id: productId,
            product_price: price,
          });
        }
      }
    },
    
    /**
     * Handle begin checkout event
     */
    handleBeginCheckout: function(params) {
      this.cartValue = 0;
    },
    
    /**
     * Handle purchase event
     */
    handlePurchase: function(params) {
      this.cartValue = 0;
      this.viewedProducts.clear();
    },
    
    /**
     * Track scroll depth
     */
    trackScrollDepth: function() {
      let maxScroll = 0;
      const self = this;
      
      window.addEventListener('scroll', function() {
        const scrollPercent = Math.round(
          (window.scrollY / (document.documentElement.scrollHeight - window.innerHeight)) * 100
        );
        
        if (scrollPercent > maxScroll) {
          maxScroll = scrollPercent;
          
          if (maxScroll >= 75 && maxScroll < 80) {
            self.trackEvent('high_engagement', {
              scroll_depth: maxScroll,
              time_on_site: self.getTimeOnSite(),
            });
          }
        }
      });
    },
    
    /**
     * Track event to backend
     */
    trackEvent: function(eventType, eventData) {
      const url = `${this.config.apiUrl}/marketing/behavior-discounts/track/${this.config.businessId}`;
      
      fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          visitor_id: this.config.visitorId,
          event_type: eventType,
          event_data: {
            ...eventData,
            page_views: this.pageViewCount,
            time_on_site: this.getTimeOnSite(),
            current_page: window.location.pathname,
            referrer: document.referrer,
            user_agent: navigator.userAgent,
          },
        }),
      })
      .then(response => response.json())
      .then(data => {
        if (data.triggered && data.offer) {
          this.showDiscountOffer(data.offer);
        }
      })
      .catch(error => {
        console.error('[Zilo] Failed to track event:', error);
      });
    },
    
    /**
     * Check for pending discount offers
     */
    checkPendingOffers: function() {
      const url = `${this.config.apiUrl}/marketing/behavior-discounts/check?visitor_id=${this.config.visitorId}`;
      
      fetch(url)
        .then(response => response.json())
        .then(data => {
          if (data.offer) {
            this.showDiscountOffer(data.offer);
          }
        })
        .catch(error => {
          console.error('[Zilo] Failed to check offers:', error);
        });
    },
    
    /**
     * Show discount offer popup
     */
    showDiscountOffer: function(offer) {
      // Create popup HTML
      const popup = document.createElement('div');
      popup.id = 'zilo-discount-popup';
      popup.innerHTML = `
        <div style="position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 999999; display: flex; align-items: center; justify-content: center; padding: 1rem;">
          <div style="background: white; border-radius: 1rem; max-width: 28rem; width: 100%; padding: 2rem; position: relative; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); animation: slideIn 0.3s ease-out;">
            <button onclick="document.getElementById('zilo-discount-popup').remove()" style="position: absolute; top: 1rem; right: 1rem; background: none; border: none; font-size: 1.5rem; cursor: pointer; color: #64748b;">&times;</button>
            
            <div style="text-align: center;">
              <div style="width: 4rem; height: 4rem; background: linear-gradient(135deg, #10b981, #059669); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                <span style="font-size: 2rem;">🎁</span>
              </div>
              
              <h3 style="font-size: 1.5rem; font-weight: bold; color: #0f172a; margin-bottom: 0.5rem;">
                Special Offer Just For You! 🎉
              </h3>
              
              <p style="color: #64748b; margin-bottom: 1.5rem;">
                ${offer.message}
              </p>
              
              <div style="background: linear-gradient(135deg, #dcfce7, #d1fae5); border: 2px solid #86efac; border-radius: 0.75rem; padding: 1rem; margin-bottom: 1.5rem;">
                <p style="font-size: 0.75rem; color: #64748b; margin-bottom: 0.25rem;">Your Discount Code:</p>
                <div style="display: flex; align-items: center; justify-content: center; gap: 0.5rem;">
                  <code style="font-size: 1.5rem; font-weight: bold; color: #059669; letter-spacing: 0.1em;">
                    ${offer.discount_code}
                  </code>
                  <button onclick="navigator.clipboard.writeText('${offer.discount_code}'); this.innerHTML='✓'" style="padding: 0.5rem; background: #dcfce7; border: none; border-radius: 0.5rem; cursor: pointer;">
                    📋
                  </button>
                </div>
              </div>
              
              <div style="font-size: 2rem; font-weight: bold; color: #059669; margin-bottom: 1.5rem;">
                ${offer.discount_type === 'percentage' ? offer.discount_value + '%' : '$' + offer.discount_value} OFF
              </div>
              
              <button onclick="document.getElementById('zilo-discount-popup').remove()" style="width: 100%; background: linear-gradient(135deg, #10b981, #059669); color: white; font-weight: 600; padding: 0.75rem 1.5rem; border-radius: 0.75rem; border: none; cursor: pointer; font-size: 1rem;">
                Continue Shopping
              </button>
            </div>
          </div>
        </div>
        
        <style>
          @keyframes slideIn {
            from {
              opacity: 0;
              transform: scale(0.9) translateY(-20px);
            }
            to {
              opacity: 1;
              transform: scale(1) translateY(0);
            }
          }
        </style>
      `;
      
      document.body.appendChild(popup);
      
      // Mark as shown
      fetch(`${this.config.apiUrl}/marketing/behavior-discounts/mark-shown`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          visitor_id: this.config.visitorId,
          campaign_id: offer.campaign_id,
          offer_type: offer.delivery_method,
        }),
      });
    },

    /**
     * Inject floating storefront customer support chat widget
     */
    injectChatWidget: function() {
      const self = this;
      const configUrl = `${this.config.apiUrl}/shopify/store-chat-widget/config/${this.config.businessId}`;

      fetch(configUrl)
        .then(response => response.json())
        .then(data => {
          if (!data || !data.enabled) {
            return; // Chat widget disabled by merchant
          }
          self.renderChatWidget(data);
        })
        .catch(error => {
          console.error('[Zilo] Failed to fetch chat widget configuration:', error);
        });
    },

    /**
     * Render the chat widget UI elements
     */
    renderChatWidget: function(config) {
      const self = this;
      const brandColor = config.brand_color || '#10b981';
      const welcomeMsg = config.welcome_message || 'Hi there! 👋 Welcome to our store. How can we help you today?';
      const bizName = config.business_name || 'Support Team';
      const whatsapp = config.whatsapp_number || '';

      // 1. Create Floating Button (Bubble)
      const bubble = document.createElement('div');
      bubble.id = 'zilo-chat-bubble';
      bubble.innerHTML = `
        <button id="zilo-chat-bubble-btn" style="
          position: fixed;
          bottom: 24px;
          right: 24px;
          width: 60px;
          height: 60px;
          border-radius: 30px;
          background: ${brandColor};
          color: white;
          border: none;
          box-shadow: 0 4px 15px rgba(0,0,0,0.15);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 999998;
          transition: transform 0.2s ease-in-out, background 0.2s ease;
        ">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" style="width: 28px; height: 28px;">
            <path fill-rule="evenodd" d="M4.848 2.771A49.144 49.144 0 0 1 12 2.25c2.43 0 4.817.178 7.152.52 1.978.292 3.348 2.024 3.348 3.97v6.02c0 1.946-1.37 3.678-3.348 3.97a48.901 48.901 0 0 1-3.476.383.39.39 0 0 0-.297.17l-2.755 4.13a.75.75 0 0 1-1.248 0l-2.755-4.13a.39.39 0 0 0-.297-.17 48.9 48.9 0 0 1-3.476-.384c-1.978-.29-3.348-2.024-3.348-3.97V6.741c0-1.946 1.37-3.68 3.348-3.97ZM6.75 8.25a.75.75 0 0 1 .75-.75h9a.75.75 0 0 1 0 1.5h-9a.75.75 0 0 1-.75-.75Zm.75 3.5a.75.75 0 0 0 0 1.5h6a.75.75 0 0 0 0-1.5h-6Z" clip-rule="evenodd" />
          </svg>
        </button>
      `;

      // 2. Create Chat Box Window Panel
      const panel = document.createElement('div');
      panel.id = 'zilo-chat-panel';
      panel.style.cssText = `
        position: fixed;
        bottom: 96px;
        right: 24px;
        width: 360px;
        max-width: calc(100vw - 48px);
        height: 520px;
        max-height: calc(100vh - 140px);
        background: white;
        border-radius: 16px;
        box-shadow: 0 8px 30px rgba(0,0,0,0.15);
        display: none;
        flex-direction: column;
        overflow: hidden;
        z-index: 999999;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        transition: opacity 0.3s ease, transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        opacity: 0;
        transform: translateY(20px) scale(0.95);
      `;

      panel.innerHTML = `
        <!-- Panel Header -->
        <div style="background: ${brandColor}; color: white; padding: 20px 24px; position: relative;">
          <h4 style="margin: 0; font-size: 1.15rem; font-weight: 700;">${bizName} Support</h4>
          <p style="margin: 4px 0 0; font-size: 0.85rem; opacity: 0.9; display: flex; align-items: center; gap: 6px;">
            <span style="width: 8px; height: 8px; background: #22c55e; border-radius: 50%; display: inline-block;"></span>
            We typically reply instantly
          </p>
          <button id="zilo-chat-close-btn" style="position: absolute; top: 18px; right: 18px; background: none; border: none; color: white; font-size: 1.5rem; cursor: pointer; opacity: 0.85; transition: opacity 0.2s;">&times;</button>
        </div>

        <!-- Panel Body -->
        <div style="flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 20px;">
          <!-- Welcome Message -->
          <div style="background: #f1f5f9; border-radius: 12px; padding: 14px 16px; font-size: 0.95rem; color: #334155; line-height: 1.4;">
            ${welcomeMsg}
          </div>

          <!-- CRM Contact Form -->
          <div id="zilo-chat-form-container" style="display: flex; flex-direction: column; gap: 14px;">
            <p style="margin: 0; font-size: 0.85rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">Start a Conversation</p>
            
            <div style="display: flex; flex-direction: column; gap: 4px;">
              <input type="text" id="zilo-chat-input-name" placeholder="Your Name" style="width: 100%; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 14px; font-size: 0.9rem; box-sizing: border-box; outline: none; transition: border-color 0.2s;">
            </div>

            <div style="display: flex; flex-direction: column; gap: 4px;">
              <input type="text" id="zilo-chat-input-contact" placeholder="Email or Phone Number" style="width: 100%; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 14px; font-size: 0.9rem; box-sizing: border-box; outline: none; transition: border-color 0.2s;">
            </div>

            <div style="display: flex; flex-direction: column; gap: 4px;">
              <textarea id="zilo-chat-input-message" placeholder="How can we help you?" rows="3" style="width: 100%; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 14px; font-size: 0.9rem; box-sizing: border-box; resize: none; outline: none; transition: border-color 0.2s; font-family: inherit;"></textarea>
            </div>

            <!-- Submit Buttons -->
            <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 4px;">
              <button id="zilo-chat-submit-crm" style="width: 100%; background: ${brandColor}; color: white; border: none; border-radius: 8px; padding: 12px; font-weight: 600; font-size: 0.95rem; cursor: pointer; transition: filter 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px;">
                Send Message
              </button>

              ${whatsapp ? `
                <div style="text-align: center; color: #94a3b8; font-size: 0.8rem; margin: 2px 0;">— OR —</div>
                <button id="zilo-chat-submit-whatsapp" style="width: 100%; background: #25d366; color: white; border: none; border-radius: 8px; padding: 12px; font-weight: 600; font-size: 0.95rem; cursor: pointer; transition: background 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px;">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" style="width: 18px; height: 18px;">
                    <path fill-rule="evenodd" d="M1.5 5.625c0-1.036.84-1.875 1.875-1.875h17.25c1.035 0 1.875.84 1.875 1.875v12.75c0 1.035-.84 1.875-1.875 1.875H3.375A1.875 1.875 0 0 1 1.5 18.375V5.625ZM21 9.375V5.625a.375.375 0 0 0-.375-.375H3.375a.375.375 0 0 0-.375.375v3.75h18Zm0 1.5H3v7.5c0 .207.168.375.375.375h17.25c.207 0 .375-.168.375-.375v-7.5Z" />
                  </svg>
                  Chat on WhatsApp
                </button>
              ` : ''}
            </div>
          </div>

          <!-- Successful State message (initially hidden) -->
          <div id="zilo-chat-success-container" style="display: none; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 20px 0; gap: 12px; animation: slideIn 0.3s ease;">
            <div style="width: 48px; height: 48px; background: #dcfce7; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #22c55e; font-size: 1.5rem;">✓</div>
            <h5 style="margin: 0; font-size: 1.1rem; color: #0f172a; font-weight: bold;">Message Sent!</h5>
            <p style="margin: 0; font-size: 0.9rem; color: #64748b; line-height: 1.4;">Thank you for reaching out. Our customer support team has received your message and will respond shortly.</p>
            <button id="zilo-chat-success-reset" style="margin-top: 8px; background: none; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px 12px; font-size: 0.8rem; color: #64748b; cursor: pointer;">Send another message</button>
          </div>
        </div>

        <!-- Panel Footer -->
        <div style="background: #f8fafc; border-top: 1px solid #f1f5f9; padding: 12px; text-align: center; font-size: 0.75rem; color: #94a3b8;">
          Powered by <a href="https://zilo.pro" target="_blank" style="color: ${brandColor}; text-decoration: none; font-weight: 600;">Zilo CRM</a>
        </div>
      `;

      // 3. Append elements to body
      document.body.appendChild(bubble);
      document.body.appendChild(panel);

      // 4. Toggle Actions & Listeners
      const bubbleBtn = document.getElementById('zilo-chat-bubble-btn');
      const closeBtn = document.getElementById('zilo-chat-close-btn');
      const crmSubmit = document.getElementById('zilo-chat-submit-crm');
      const waSubmit = document.getElementById('zilo-chat-submit-whatsapp');
      const successReset = document.getElementById('zilo-chat-success-reset');

      const nameInput = document.getElementById('zilo-chat-input-name');
      const contactInput = document.getElementById('zilo-chat-input-contact');
      const msgInput = document.getElementById('zilo-chat-input-message');
      const formContainer = document.getElementById('zilo-chat-form-container');
      const successContainer = document.getElementById('zilo-chat-success-container');

      // Expand / Collapse logic
      let isOpen = false;
      function togglePanel() {
        isOpen = !isOpen;
        if (isOpen) {
          panel.style.display = 'flex';
          // Force layout refresh before opacity change
          panel.offsetHeight; 
          panel.style.opacity = '1';
          panel.style.transform = 'translateY(0) scale(1)';
          bubbleBtn.style.transform = 'scale(0.9) rotate(45deg)';
        } else {
          panel.style.opacity = '0';
          panel.style.transform = 'translateY(20px) scale(0.95)';
          bubbleBtn.style.transform = 'scale(1) rotate(0deg)';
          setTimeout(() => {
            if (!isOpen) panel.style.display = 'none';
          }, 300);
        }
      }

      bubbleBtn.addEventListener('click', togglePanel);
      closeBtn.addEventListener('click', togglePanel);

      // Focus effect styles
      [nameInput, contactInput, msgInput].forEach(inp => {
        inp.addEventListener('focus', () => { inp.style.borderColor = brandColor; });
        inp.addEventListener('blur', () => { inp.style.borderColor = '#cbd5e1'; });
      });

      // Submit direct Inquiry to Zilo CRM Inbox
      crmSubmit.addEventListener('click', function() {
        const name = nameInput.value.trim();
        const contact = contactInput.value.trim();
        const message = msgInput.value.trim();

        if (!name || !contact || !message) {
          alert('Please fill out all fields before sending.');
          return;
        }

        crmSubmit.disabled = true;
        crmSubmit.innerHTML = 'Sending...';

        const submitUrl = `${self.config.apiUrl}/shopify/store-chat-widget/message/${self.config.businessId}`;
        fetch(submitUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, contact, message })
        })
        .then(response => response.json())
        .then(res => {
          crmSubmit.disabled = false;
          crmSubmit.innerHTML = 'Send Message';
          
          if (res.status === 'success') {
            // Switch to successful state
            formContainer.style.display = 'none';
            successContainer.style.display = 'flex';
            // Clear message input
            msgInput.value = '';
          } else {
            alert('Failed to send message. Please try again.');
          }
        })
        .catch(err => {
          console.error('[Zilo] Submit inquiry error:', err);
          crmSubmit.disabled = false;
          crmSubmit.innerHTML = 'Send Message';
          alert('A connection error occurred. Please try again.');
        });
      });

      // Reset form to send another message
      if (successReset) {
        successReset.addEventListener('click', function() {
          successContainer.style.display = 'none';
          formContainer.style.display = 'flex';
        });
      }

      // WhatsApp Prefilled Redirect Link Action
      if (waSubmit) {
        waSubmit.addEventListener('click', function() {
          const name = nameInput.value.trim();
          const message = msgInput.value.trim();
          
          let text = `Hello! I'm visiting your website.`;
          if (name) text += ` My name is ${name}.`;
          if (message) text += ` ${message}`;

          const waUrl = `https://wa.me/${whatsapp}?text=${encodeURIComponent(text)}`;
          window.open(waUrl, '_blank');
        });
      }
    },
  };
  
  // Expose to global scope
  window.ZiloBehaviorTracker = ZiloBehaviorTracker;
  
})(window);

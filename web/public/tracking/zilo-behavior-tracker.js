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
  };
  
  // Expose to global scope
  window.ZiloBehaviorTracker = ZiloBehaviorTracker;
  
})(window);

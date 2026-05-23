"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

interface GA4BehaviorTrackerProps {
  businessId: string;
  visitorId: string;
  enabled?: boolean;
}

/**
 * GA4 Behavior Tracker
 * Tracks visitor behavior and sends events to trigger discount campaigns
 */
export default function GA4BehaviorTracker({
  businessId,
  visitorId,
  enabled = true,
}: GA4BehaviorTrackerProps) {
  const pathname = usePathname();
  const sessionStartTime = useRef<number>(Date.now());
  const pageViewCount = useRef<number>(0);
  const viewedProducts = useRef<Set<string>>(new Set());
  const cartValue = useRef<number>(0);
  const exitIntentTriggered = useRef<boolean>(false);

  useEffect(() => {
    if (!enabled || !businessId || !visitorId) return;

    // Track page view
    pageViewCount.current += 1;
    trackPageView();

    // Check for first-time visitor
    if (pageViewCount.current === 1) {
      trackEvent("first_time_visitor", {});
    }

    // Check for page views threshold
    if (pageViewCount.current === 3) {
      trackEvent("page_views_threshold", {
        page_views: pageViewCount.current,
      });
    }

    // Track time on site every 30 seconds
    const timeInterval = setInterval(() => {
      const timeOnSite = Math.floor((Date.now() - sessionStartTime.current) / 1000);
      if (timeOnSite >= 120 && timeOnSite % 30 === 0) {
        trackEvent("time_on_site", {
          time_on_site: timeOnSite,
        });
      }
    }, 30000);

    // Track exit intent
    const handleMouseLeave = (e: MouseEvent) => {
      if (e.clientY <= 0 && !exitIntentTriggered.current) {
        exitIntentTriggered.current = true;
        trackEvent("exit_intent", {
          page_views: pageViewCount.current,
          time_on_site: Math.floor((Date.now() - sessionStartTime.current) / 1000),
        });
      }
    };

    document.addEventListener("mouseleave", handleMouseLeave);

    return () => {
      clearInterval(timeInterval);
      document.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, [pathname, businessId, visitorId, enabled]);

  // Listen for GA4 events from the website
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    const handleGA4Event = (event: CustomEvent) => {
      const { event_name, event_params } = event.detail;

      switch (event_name) {
        case "add_to_cart":
          handleAddToCart(event_params);
          break;
        case "view_item":
          handleViewItem(event_params);
          break;
        case "begin_checkout":
          handleBeginCheckout(event_params);
          break;
        case "purchase":
          handlePurchase(event_params);
          break;
      }
    };

    window.addEventListener("ga4_event" as any, handleGA4Event as EventListener);

    return () => {
      window.removeEventListener("ga4_event" as any, handleGA4Event as EventListener);
    };
  }, [enabled, businessId, visitorId]);

  const trackEvent = async (eventType: string, eventData: Record<string, any>) => {
    try {
      const response = await fetch(`/api/marketing/behavior-discounts/track/${businessId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          visitor_id: visitorId,
          event_type: eventType,
          event_data: {
            ...eventData,
            page_views: pageViewCount.current,
            time_on_site: Math.floor((Date.now() - sessionStartTime.current) / 1000),
            current_page: pathname,
          },
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.triggered && data.offer) {
          // Discount was triggered! Handle based on delivery method
          handleDiscountOffer(data.offer);
        }
      }
    } catch (error) {
      console.error("Failed to track behavior event:", error);
    }
  };

  const trackPageView = () => {
    // Send page view event to GA4
    if (typeof window !== "undefined" && window.gtag) {
      window.gtag("event", "page_view", {
        page_path: pathname,
      });
    }
  };

  const handleAddToCart = (params: any) => {
    const value = params.value || params.price || 0;
    cartValue.current += value;

    // Track cart addition
    trackEvent("browsed_product", {
      product_id: params.item_id || params.product_id,
      product_name: params.item_name || params.product_name,
      cart_value: cartValue.current,
    });

    // Set timeout to detect cart abandonment (5 minutes)
    setTimeout(() => {
      if (cartValue.current > 0) {
        trackEvent("cart_abandoned", {
          cart_value: cartValue.current,
        });
      }
    }, 300000); // 5 minutes
  };

  const handleViewItem = (params: any) => {
    const productId = params.item_id || params.product_id;
    if (productId) {
      viewedProducts.current.add(productId);

      // If viewed same product multiple times
      if (viewedProducts.current.size >= 2) {
        trackEvent("browsed_product", {
          product_id: productId,
          product_name: params.item_name || params.product_name,
          view_count: viewedProducts.current.size,
        });
      }

      // Check if high-value product
      const price = params.price || params.value || 0;
      if (price > 100) {
        trackEvent("high_value_visitor", {
          product_id: productId,
          product_price: price,
        });
      }
    }
  };

  const handleBeginCheckout = (params: any) => {
    // Clear cart abandonment tracking
    cartValue.current = 0;
  };

  const handlePurchase = (params: any) => {
    // Clear cart
    cartValue.current = 0;
    viewedProducts.current.clear();
  };

  const handleDiscountOffer = (offer: any) => {
    // Emit custom event for the discount widget to catch
    const event = new CustomEvent("discount_offer_triggered", {
      detail: offer,
    });
    window.dispatchEvent(event);
  };

  // This component doesn't render anything
  return null;
}

// Extend Window interface for TypeScript
declare global {
  interface Window {
    gtag: (
      command: string,
      targetId: string,
      config?: Record<string, unknown>
    ) => void;
  }
}

/**
 * Google Analytics 4 Event Tracking Utilities
 * Use these functions to track custom events throughout the application
 */

interface GAEvent {
  action: string;
  category: string;
  label?: string;
  value?: number;
}

/**
 * Send a custom event to Google Analytics 4
 */
export const trackEvent = ({ action, category, label, value }: GAEvent) => {
  if (typeof window !== "undefined" && window.gtag) {
    window.gtag("event", action, {
      event_category: category,
      event_label: label,
      value: value,
    });
  }
};

/**
 * Track page views manually (useful for SPAs)
 */
export const trackPageView = (url: string) => {
  if (typeof window !== "undefined" && window.gtag) {
    window.gtag("config", process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID || "", {
      page_path: url,
    });
  }
};

/**
 * Track user interactions
 */
export const trackClick = (elementName: string, location?: string) => {
  trackEvent({
    action: "click",
    category: "engagement",
    label: location ? `${elementName} - ${location}` : elementName,
  });
};

/**
 * Track form submissions
 */
export const trackFormSubmit = (formName: string, success: boolean) => {
  trackEvent({
    action: success ? "form_submit_success" : "form_submit_error",
    category: "forms",
    label: formName,
  });
};

/**
 * Track conversions (e.g., sign-ups, purchases)
 */
export const trackConversion = (conversionType: string, value?: number) => {
  trackEvent({
    action: "conversion",
    category: "conversions",
    label: conversionType,
    value: value,
  });
};

/**
 * Track feature usage
 */
export const trackFeatureUse = (featureName: string, action?: string) => {
  trackEvent({
    action: action || "use",
    category: "features",
    label: featureName,
  });
};

/**
 * Track errors
 */
export const trackError = (errorMessage: string, errorLocation?: string) => {
  trackEvent({
    action: "error",
    category: "errors",
    label: errorLocation ? `${errorLocation}: ${errorMessage}` : errorMessage,
  });
};

/**
 * Track search queries
 */
export const trackSearch = (searchTerm: string, resultsCount?: number) => {
  trackEvent({
    action: "search",
    category: "search",
    label: searchTerm,
    value: resultsCount,
  });
};

/**
 * Track social shares
 */
export const trackShare = (platform: string, contentType?: string) => {
  trackEvent({
    action: "share",
    category: "social",
    label: contentType ? `${platform} - ${contentType}` : platform,
  });
};

/**
 * Track video interactions
 */
export const trackVideo = (action: "play" | "pause" | "complete", videoName: string) => {
  trackEvent({
    action: `video_${action}`,
    category: "video",
    label: videoName,
  });
};

/**
 * Track file downloads
 */
export const trackDownload = (fileName: string, fileType?: string) => {
  trackEvent({
    action: "download",
    category: "downloads",
    label: fileType ? `${fileName} (${fileType})` : fileName,
  });
};

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

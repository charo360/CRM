/**
 * Zilo Browser Operator — Dashboard Bridge
 * Injected only on the Zilo CRM web app pages.
 *
 * The backend WebSocket requires a short-lived JWT that can only be minted by an
 * authenticated CRM session. This bridge reads the logged-in user's CRM token from
 * the dashboard's localStorage and hands it (plus the same-origin API base) to the
 * service worker, which then mints the ws-token and connects. No manual IDs needed.
 */

(function () {
  "use strict";

  function readCrmAuth() {
    let crmToken = null;
    try {
      crmToken = window.localStorage.getItem("token");
    } catch (e) {
      // localStorage may be blocked; nothing we can do
    }
    if (!crmToken) return null;
    // The web app proxies the backend at <origin>/proxy → backend /api/*
    const apiBase = `${window.location.origin}/proxy`;
    return { crmToken, apiBase };
  }

  function pushAuthToBackground() {
    const auth = readCrmAuth();
    if (!auth) return;
    chrome.runtime.sendMessage(
      { type: "CRM_AUTH", crmToken: auth.crmToken, apiBase: auth.apiBase },
      () => {
        // Swallow "receiving end does not exist" while SW spins up
        void chrome.runtime.lastError;
      }
    );
  }

  // Let the dashboard detect that the operator is installed (optional UI hook).
  try {
    window.postMessage({ type: "ZILO_OPERATOR_INSTALLED", version: "1.0.1" }, "*");
  } catch (e) {
    /* ignore */
  }

  // Push on load, when the tab regains focus, and when login state may have changed.
  pushAuthToBackground();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") pushAuthToBackground();
  });
  window.addEventListener("focus", pushAuthToBackground);
})();

/**
 * Zilo Browser Operator - Background Service Worker (Manifest V3)
 * Manages the authenticated WebSocket connection to the Zilo CRM backend and routes
 * automation commands to the active tab's content script.
 *
 * Auth flow (no manual IDs):
 *   1. The dashboard bridge (dashboard.js) supplies the logged-in CRM token + API base.
 *   2. We mint a short-lived browser-ws JWT from GET {apiBase}/browser/ws-token.
 *   3. We open ws(s)://{ws_url}/api/browser/ws/{user_id}?token={ws_token}.
 *   4. On expiry/4401 we re-mint and reconnect automatically.
 */

const RECONNECT_MS = 5000;
const KEEPALIVE_ALARM = "zilo-operator-keepalive";

let ws = null;
let reconnectTimer = null;
let isConnected = false;

// Cached connection material (also mirrored in chrome.storage.local)
let crmToken = null; // CRM session JWT, from the dashboard bridge
let apiBase = null; // e.g. https://app.zilo.app/proxy  (proxies to backend /api)
let userId = null; // resolved by the backend when minting the ws-token
let wsToken = null; // short-lived browser-ws JWT
let wsBaseUrl = null; // backend public origin for the socket, from ws-token response

// ---------------------------------------------------------------------------
// Storage helpers
// ---------------------------------------------------------------------------
function loadState() {
  return new Promise((resolve) => {
    chrome.storage.local.get(
      ["crmToken", "apiBase", "userId", "wsToken", "wsBaseUrl", "serverUrl"],
      (r) => {
        crmToken = r.crmToken || crmToken;
        apiBase = r.apiBase || apiBase;
        userId = r.userId || userId;
        wsToken = r.wsToken || wsToken;
        wsBaseUrl = r.wsBaseUrl || wsBaseUrl;
        resolve(r);
      }
    );
  });
}

function saveState(patch) {
  return new Promise((resolve) => chrome.storage.local.set(patch, resolve));
}

// ---------------------------------------------------------------------------
// Token minting
// ---------------------------------------------------------------------------
// Resolve the API base used to mint the ws-token. Prefer the base handed over by
// the dashboard bridge; fall back to a manually configured server URL from the popup.
async function resolveApiBase() {
  if (apiBase) return apiBase;
  const { serverUrl } = await new Promise((res) =>
    chrome.storage.local.get(["serverUrl"], res)
  );
  if (serverUrl) {
    // Manual override points straight at the backend, whose API lives under /api.
    return `${serverUrl.replace(/\/+$/, "")}/api`;
  }
  return null;
}

async function mintWsToken() {
  const base = await resolveApiBase();
  if (!base) {
    console.warn("[Zilo Operator] No API base yet — open and log into your Zilo dashboard.");
    return false;
  }
  if (!crmToken) {
    console.warn("[Zilo Operator] No CRM token yet — open and log into your Zilo dashboard.");
    return false;
  }

  try {
    const res = await fetch(`${base.replace(/\/+$/, "")}/browser/ws-token`, {
      method: "GET",
      headers: { Authorization: `Bearer ${crmToken}` },
    });
    if (!res.ok) {
      console.error(`[Zilo Operator] ws-token request failed: HTTP ${res.status}`);
      if (res.status === 401) {
        // CRM session expired — drop it so we stop hammering and wait for a fresh one.
        crmToken = null;
        await saveState({ crmToken: null });
      }
      return false;
    }
    const data = await res.json();
    userId = String(data.user_id || "");
    wsToken = data.ws_token || null;
    wsBaseUrl = data.ws_url || wsBaseUrl;
    await saveState({ userId, wsToken, wsBaseUrl });
    console.log(`[Zilo Operator] Minted ws-token for user ${userId}.`);
    return Boolean(userId && wsToken);
  } catch (err) {
    console.error("[Zilo Operator] ws-token fetch error:", err);
    return false;
  }
}

function buildSocketUrl() {
  const base = (wsBaseUrl || "http://localhost:8000").replace(/\/+$/, "");
  const wsBase = base.replace(/^http/, "ws"); // http→ws, https→wss
  return `${wsBase}/api/browser/ws/${encodeURIComponent(userId)}?token=${encodeURIComponent(wsToken)}`;
}

// ---------------------------------------------------------------------------
// WebSocket lifecycle
// ---------------------------------------------------------------------------
async function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  await loadState();

  if (!wsToken || !userId) {
    const minted = await mintWsToken();
    if (!minted) {
      scheduleReconnect();
      return;
    }
  }

  const url = buildSocketUrl();
  console.log(`[Zilo Operator] Connecting: ${url.replace(/token=[^&]+/, "token=***")}`);

  try {
    ws = new WebSocket(url);

    ws.onopen = () => {
      console.log("[Zilo Operator] WebSocket connected.");
      isConnected = true;
      clearTimeout(reconnectTimer);
      broadcastStatus({ status: "connected", userId });
    };

    ws.onmessage = async (event) => {
      let command;
      try {
        command = JSON.parse(event.data);
      } catch (e) {
        return; // ignore non-JSON / keepalive noise
      }
      if (!command || !command.action) return; // ignore server-side acks/pings
      try {
        const result = await executeCommand(command);
        ws.send(
          JSON.stringify({
            commandId: command.id,
            success: !result.error,
            result,
          })
        );
      } catch (err) {
        console.error("[Zilo Operator] Command handling error:", err);
        try {
          ws.send(
            JSON.stringify({ commandId: command.id, success: false, result: { error: String(err) } })
          );
        } catch (_) {
          /* socket gone */
        }
      }
    };

    ws.onclose = async (event) => {
      isConnected = false;
      broadcastStatus({ status: "disconnected" });
      // 4401 = unauthorized → ws-token expired/invalid. Drop it and re-mint on retry.
      if (event.code === 4401) {
        console.warn("[Zilo Operator] Unauthorized (token expired). Re-minting on reconnect.");
        wsToken = null;
        userId = null;
        await saveState({ wsToken: null, userId: null });
      } else {
        console.log(`[Zilo Operator] WebSocket closed (code ${event.code}). Retrying…`);
      }
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error("[Zilo Operator] WebSocket error:", err);
      isConnected = false;
    };
  } catch (exc) {
    console.error("[Zilo Operator] Connection exception:", exc);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connectWebSocket, RECONNECT_MS);
}

function disconnect() {
  clearTimeout(reconnectTimer);
  if (ws) {
    try {
      ws.close(1000, "Client disconnect");
    } catch (_) {
      /* ignore */
    }
  }
  ws = null;
  isConnected = false;
}

// ---------------------------------------------------------------------------
// Command execution
// ---------------------------------------------------------------------------
async function executeCommand(command) {
  const { action, url } = command;
  console.log(`[Zilo Operator] Executing: ${action}`, command);

  if (action === "navigate") {
    try {
      const tab = await new Promise((resolve) => {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          if (tabs && tabs[0]) {
            chrome.tabs.update(tabs[0].id, { url }, (t) => resolve(t));
          } else {
            chrome.tabs.create({ url }, (t) => resolve(t));
          }
        });
      });
      return { status: "navigated", url: tab.url };
    } catch (err) {
      return { error: `Navigation failed: ${err.message}` };
    }
  }

  try {
    const activeTab = await getActiveTab();
    if (!activeTab) return { error: "No active browser tab found to control." };
    return await sendToTabWithRetry(activeTab.id, command);
  } catch (err) {
    return { error: `Execution error on tab: ${err.message}` };
  }
}

function getActiveTab() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      resolve(tabs && tabs[0] ? tabs[0] : null);
    });
  });
}

async function sendToTabWithRetry(tabId, message, retries = 1) {
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch (err) {
    if (retries > 0) {
      console.log("[Zilo Operator] Injecting content script dynamically…");
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
      await new Promise((r) => setTimeout(r, 250));
      return await sendToTabWithRetry(tabId, message, retries - 1);
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Messaging with popup / dashboard bridge
// ---------------------------------------------------------------------------
function broadcastStatus(data) {
  chrome.runtime.sendMessage({ type: "STATUS_UPDATE", ...data }).catch(() => {});
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  // Dashboard bridge handing us the logged-in CRM credentials.
  if (request.type === "CRM_AUTH") {
    const changed = request.crmToken !== crmToken || request.apiBase !== apiBase;
    crmToken = request.crmToken || crmToken;
    apiBase = request.apiBase || apiBase;
    saveState({ crmToken, apiBase }).then(() => {
      // New/refreshed credentials → (re)establish the session.
      if (changed || !isConnected) {
        wsToken = null; // force a fresh mint with the latest CRM token
        userId = null;
        connectWebSocket();
      }
      sendResponse({ status: "ok" });
    });
    return true;
  }

  // Manual override from the popup (server URL for self-hosted/dev).
  if (request.type === "SET_SERVER") {
    chrome.storage.local.set({ serverUrl: request.serverUrl }, () => {
      wsToken = null;
      userId = null;
      connectWebSocket();
      sendResponse({ status: "ok" });
    });
    return true;
  }

  if (request.type === "RECONNECT") {
    disconnect();
    connectWebSocket();
    sendResponse({ status: "reconnecting" });
    return true;
  }

  if (request.type === "GET_STATUS") {
    sendResponse({ isConnected, userId, hasCrmToken: Boolean(crmToken) });
    return false;
  }
  return false;
});

// ---------------------------------------------------------------------------
// MV3 keepalive — the worker idles out after ~30s; an alarm wakes it to keep the
// socket alive and to recover the connection if it was torn down while suspended.
// ---------------------------------------------------------------------------
chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.5 }); // 30s (Chrome minimum)

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== KEEPALIVE_ALARM) return;
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "ping" })); // ignored by backend, keeps SW warm
    } catch (_) {
      scheduleReconnect();
    }
  } else {
    connectWebSocket();
  }
});

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------
chrome.runtime.onInstalled.addListener(() => {
  console.log("[Zilo Operator] Installed.");
  connectWebSocket();
});

chrome.runtime.onStartup.addListener(() => {
  console.log("[Zilo Operator] Started.");
  connectWebSocket();
});

// Cold-start of the service worker itself.
connectWebSocket();

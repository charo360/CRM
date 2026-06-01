/**
 * Zilo Browser Operator - Background Service Worker (Manifest V3)
 * Manages WebSocket connection to Zilo CRM backend and routes automation commands.
 */

let ws = null;
let reconnectTimer = null;
let userId = "user_default"; // Fallback, will be updated via popup or storage
let isConnected = false;

// Resolve backend WS URL
function getWebSocketUrl() {
  // Can be configured via chrome.storage, default to localhost for development
  return new Promise((resolve) => {
    chrome.storage.local.get(["wsUrl", "userId"], (result) => {
      if (result.userId) {
        userId = result.userId;
      }
      const base = result.wsUrl || "ws://localhost:8000";
      // Map http/https to ws/wss
      const wsBase = base.replace(/^http/, "ws");
      resolve(`${wsBase}/api/browser/ws/${userId}`);
    });
  });
}

// Initialize and connect WebSocket
async function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  const url = await getWebSocketUrl();
  console.log(`[Zilo Background] Connecting to WebSocket: ${url}`);

  try {
    ws = new WebSocket(url);

    ws.onopen = () => {
      console.log("[Zilo Background] WebSocket connection established successfully.");
      isConnected = true;
      clearTimeout(reconnectTimer);
      broadcastStatus({ status: "connected", userId, url });
    };

    ws.onmessage = async (event) => {
      console.log("[Zilo Background] Message received from server:", event.data);
      try {
        const command = JSON.parse(event.data);
        const result = await executeCommand(command);
        ws.send(JSON.stringify({
          commandId: command.id,
          success: !result.error,
          result: result
        }));
      } catch (err) {
        console.error("[Zilo Background] Error processing server message:", err);
      }
    };

    ws.onclose = (event) => {
      console.log(`[Zilo Background] WebSocket closed (code: ${event.code}). Retrying in 5s...`);
      isConnected = false;
      broadcastStatus({ status: "disconnected" });
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error("[Zilo Background] WebSocket error:", err);
      isConnected = false;
    };

  } catch (exc) {
    console.error("[Zilo Background] Connection exception:", exc);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connectWebSocket, 5000);
}

// Execute incoming automation command
async function executeCommand(command) {
  const { action, selector, text, url } = command;
  console.log(`[Zilo Background] Executing command: ${action}`, command);

  if (action === "navigate") {
    try {
      const tab = await new Promise((resolve, reject) => {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          if (tabs && tabs[0]) {
            chrome.tabs.update(tabs[0].id, { url }, (updatedTab) => resolve(updatedTab));
          } else {
            chrome.tabs.create({ url }, (newTab) => resolve(newTab));
          }
        });
      });
      return { status: "navigated", url: tab.url };
    } catch (err) {
      return { error: `Navigation failed: ${err.message}` };
    }
  }

  // Other actions require content script injection
  try {
    const activeTab = await getActiveTab();
    if (!activeTab) {
      return { error: "No active browser tab found to control." };
    }

    // Ping content script first, inject if not responding
    const response = await sendToTabWithRetry(activeTab.id, command);
    return response;
  } catch (err) {
    return { error: `Execution error on tab: ${err.message}` };
  }
}

// Helpers
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
      console.log("[Zilo Background] Injecting content script dynamically...");
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["content.js"]
      });
      // Sleep 250ms for injection completion
      await new Promise(r => setTimeout(r, 250));
      return await sendToTabWithRetry(tabId, message, retries - 1);
    }
    throw err;
  }
}

function broadcastStatus(data) {
  // Send status update to popup if open
  chrome.runtime.sendMessage({ type: "STATUS_UPDATE", ...data }).catch(() => {});
}

// Listen for popup messages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "CONNECT_REQUEST") {
    chrome.storage.local.set({ userId: request.userId, wsUrl: request.wsUrl }, () => {
      connectWebSocket();
      sendResponse({ status: "initiating" });
    });
    return true; // Keep channel open
  }
  if (request.type === "GET_STATUS") {
    sendResponse({ isConnected, userId });
  }
});

// Startup trigger
chrome.runtime.onInstalled.addListener(() => {
  console.log("[Zilo Background] Extension installed.");
  connectWebSocket();
});

chrome.runtime.onStartup.addListener(() => {
  console.log("[Zilo Background] Extension started.");
  connectWebSocket();
});

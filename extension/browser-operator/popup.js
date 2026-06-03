/**
 * Zilo Browser Control - Popup Script
 * Coordinates with the background service worker to display and update connection status.
 */

document.addEventListener("DOMContentLoaded", () => {
  const statusBadge = document.getElementById("status-badge");
  const userIdInput = document.getElementById("user-id");
  const wsUrlInput = document.getElementById("ws-url");
  const connectBtn = document.getElementById("connect-btn");

  // Load stored options
  chrome.storage.local.get(["userId", "wsUrl"], (result) => {
    if (result.userId) {
      userIdInput.value = result.userId;
    }
    if (result.wsUrl) {
      wsUrlInput.value = result.wsUrl;
    }

    // Query status from background
    chrome.runtime.sendMessage({ type: "GET_STATUS" }, (response) => {
      if (response) {
        updateStatusUI(response.isConnected, response.userId);
      }
    });
  });

  // Handle connect request
  connectBtn.addEventListener("click", () => {
    const userId = userIdInput.value.trim();
    const wsUrl = wsUrlInput.value.trim() || "http://localhost:8000";

    if (!userId) {
      alert("Please provide a valid Zilo User ID to authenticate the session.");
      return;
    }

    connectBtn.textContent = "Connecting...";
    connectBtn.disabled = true;

    chrome.runtime.sendMessage(
      { type: "CONNECT_REQUEST", userId, wsUrl },
      (response) => {
        console.log("[Zilo Popup] Connection initiated response:", response);
        setTimeout(() => {
          chrome.runtime.sendMessage({ type: "GET_STATUS" }, (statusResponse) => {
            if (statusResponse) {
              updateStatusUI(statusResponse.isConnected, statusResponse.userId);
            }
            connectBtn.disabled = false;
            connectBtn.textContent = "Connect Session";
          });
        }, 1500);
      }
    );
  });

  // Listen for status broadcast from background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "STATUS_UPDATE") {
      updateStatusUI(message.status === "connected", message.userId);
    }
  });

  function updateStatusUI(isConnected, userId) {
    if (isConnected) {
      statusBadge.textContent = "Connected";
      statusBadge.className = "badge connected";
      if (userId) {
        userIdInput.value = userId;
      }
    } else {
      statusBadge.textContent = "Disconnected";
      statusBadge.className = "badge disconnected";
    }
  }
});

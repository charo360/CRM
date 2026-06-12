/**
 * Zilo Browser Operator - Popup Script
 * Shows live connection status and offers a manual reconnect + an advanced
 * server-URL override for self-hosted/local backends. The CRM token itself is
 * supplied automatically by the dashboard bridge, so there is nothing to type
 * in the normal flow.
 */

document.addEventListener("DOMContentLoaded", () => {
  const statusBadge = document.getElementById("status-badge");
  const userIdEl = document.getElementById("user-id");
  const hintEl = document.getElementById("hint");
  const reconnectBtn = document.getElementById("reconnect-btn");
  const serverUrlInput = document.getElementById("server-url");
  const saveServerBtn = document.getElementById("save-server-btn");

  // Load any stored manual server URL.
  chrome.storage.local.get(["serverUrl"], (r) => {
    if (r.serverUrl) serverUrlInput.value = r.serverUrl;
  });

  // Initial status.
  chrome.runtime.sendMessage({ type: "GET_STATUS" }, (res) => {
    if (chrome.runtime.lastError || !res) return;
    updateStatusUI(res.isConnected, res.userId, res.hasCrmToken);
  });

  reconnectBtn.addEventListener("click", () => {
    reconnectBtn.textContent = "Reconnecting…";
    reconnectBtn.disabled = true;
    chrome.runtime.sendMessage({ type: "RECONNECT" }, () => {
      setTimeout(refreshStatus, 1200);
    });
  });

  saveServerBtn.addEventListener("click", () => {
    const serverUrl = serverUrlInput.value.trim();
    if (!serverUrl) return;
    saveServerBtn.textContent = "Connecting…";
    saveServerBtn.disabled = true;
    chrome.runtime.sendMessage({ type: "SET_SERVER", serverUrl }, () => {
      setTimeout(refreshStatus, 1200);
    });
  });

  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "STATUS_UPDATE") {
      updateStatusUI(message.status === "connected", message.userId);
    }
  });

  function refreshStatus() {
    chrome.runtime.sendMessage({ type: "GET_STATUS" }, (res) => {
      reconnectBtn.disabled = false;
      reconnectBtn.textContent = "Reconnect";
      saveServerBtn.disabled = false;
      saveServerBtn.textContent = "Save & Connect";
      if (chrome.runtime.lastError || !res) return;
      updateStatusUI(res.isConnected, res.userId, res.hasCrmToken);
    });
  }

  function updateStatusUI(isConnected, userId, hasCrmToken) {
    if (isConnected) {
      statusBadge.textContent = "Connected";
      statusBadge.className = "badge connected";
      hintEl.style.display = "none";
    } else {
      statusBadge.textContent = "Disconnected";
      statusBadge.className = "badge disconnected";
      hintEl.style.display = "block";
      if (hasCrmToken === false) {
        hintEl.innerHTML =
          "Open and log into your <strong>Zilo dashboard</strong> in any tab — " +
          "the operator connects automatically. No IDs to enter.";
      }
    }
    userIdEl.textContent = userId ? userId : "—";
  }
});

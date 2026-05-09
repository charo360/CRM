/**
 * Zilo Social Monitor — WhatsApp Web Content Script
 * Runs on: web.whatsapp.com
 *
 * How it works:
 * - WhatsApp Web decrypts messages and renders them in the DOM
 * - We read the visible text (same as a human reading the screen)
 * - MutationObserver catches new messages as they arrive
 * - Keyword matches are sent to the Zilo CRM service worker
 * - No encryption is touched — we only read what's already displayed
 */

const SEEN_IDS = new Set();

function getGroupName() {
  // WhatsApp Web shows the chat title in the header
  return (
    document.querySelector('[data-testid="conversation-info-header-chat-title"]')?.innerText?.trim() ||
    document.querySelector('header ._3W2ap, header span[title]')?.innerText?.trim() ||
    document.querySelector('header [role="button"] span')?.innerText?.trim() ||
    "WhatsApp Group"
  );
}

function processMessages() {
  // Each message bubble has a data-id attribute — stable unique ID
  const messages = document.querySelectorAll(
    '[data-id], div[class*="message-in"], div[class*="message-out"]'
  );

  messages.forEach(msg => {
    const msgId =
      msg.getAttribute("data-id") ||
      msg.getAttribute("data-key-id") ||
      null;

    // Only process incoming messages (from others, not our own replies)
    const isOutgoing =
      msg.getAttribute("data-id")?.startsWith("true_") ||
      msg.classList.toString().includes("message-out");
    if (isOutgoing) return;

    if (!msgId || SEEN_IDS.has(msgId)) return;
    SEEN_IDS.add(msgId);

    // Extract message text — WhatsApp uses copyable-text class for actual content
    const textEl =
      msg.querySelector(".copyable-text span[dir]") ||
      msg.querySelector('[data-testid="msg-container"] span[dir]') ||
      msg.querySelector("span.selectable-text") ||
      msg.querySelector(".copyable-text");

    const text = textEl?.innerText?.trim() || msg.innerText?.trim() || "";
    if (!text || text.length < 5) return;

    // Sender name (in group chats, shown above the message)
    const sender =
      msg.querySelector("[data-testid='author']")?.innerText?.trim() ||
      msg.querySelector("._2v7iX, ._3Tw1q")?.innerText?.trim() ||
      "Unknown";

    const groupName = getGroupName();

    // Skip system messages
    if (
      text.startsWith("Messages and calls are end-to-end encrypted") ||
      text.startsWith("You created group") ||
      text.length < 8
    ) return;

    chrome.runtime.sendMessage({
      type: "NEW_POST",
      payload: {
        platform:    "whatsapp",
        postId:      msgId,
        text,
        url:         window.location.href,
        author:      sender,
        groupName,
        detectedAt:  new Date().toISOString(),
      },
    });
  });
}

// Watch for new messages arriving
const observer = new MutationObserver(() => processMessages());
observer.observe(document.body, { childList: true, subtree: true });

// Initial scan when page loads
setTimeout(processMessages, 3000);

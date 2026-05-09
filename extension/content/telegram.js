/**
 * Zilo Social Monitor — Telegram Web Content Script
 * Runs on: web.telegram.org (both /a and /k versions)
 *
 * Monitors messages in groups and channels as they load.
 * Works by reading the already-decrypted message text from the DOM —
 * same as a human reading their Telegram Web.
 */

const SEEN_IDS = new Set();

// Telegram Web has two versions — /a (newer) and /k (older)
const IS_VERSION_A = window.location.pathname.startsWith('/a');

function getChatName() {
  return (
    document.querySelector('.chat-info .peer-title')?.innerText?.trim() ||
    document.querySelector('.chat-title')?.innerText?.trim() ||
    document.querySelector('#column-center .info .peer-title')?.innerText?.trim() ||
    document.querySelector('.sidebar-header .peer-title')?.innerText?.trim() ||
    'Telegram Group'
  );
}

function processMessages() {
  // Version A uses .message class, version K uses .bubble
  const msgSelector = IS_VERSION_A
    ? '.message:not(.service)'
    : '.bubble:not(.service-msg)';

  const messages = document.querySelectorAll(msgSelector);

  messages.forEach(msg => {
    // Stable message ID from data attribute
    const msgId =
      msg.getAttribute('data-mid') ||
      msg.getAttribute('data-message-id') ||
      msg.id ||
      null;

    // Skip our own outgoing messages
    const isOutgoing =
      msg.classList.contains('out') ||
      msg.classList.contains('is-out') ||
      msg.getAttribute('data-is-out') === 'true';
    if (isOutgoing) return;

    if (!msgId || SEEN_IDS.has(msgId)) return;
    SEEN_IDS.add(msgId);

    // Extract message text
    const textEl =
      msg.querySelector('.text-content') ||
      msg.querySelector('.message-text') ||
      msg.querySelector('.text-entity-container') ||
      msg.querySelector('p') ||
      msg;

    const text = textEl?.innerText?.trim() || '';
    if (!text || text.length < 8) return;

    // Skip system messages
    if (
      text.startsWith('joined the group') ||
      text.startsWith('left the group') ||
      text.startsWith('pinned a message')
    ) return;

    // Author name
    const author =
      msg.querySelector('.peer-title')?.innerText?.trim() ||
      msg.querySelector('.sender-title')?.innerText?.trim() ||
      msg.querySelector('.name')?.innerText?.trim() ||
      'Unknown';

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:   'telegram',
        postId:     `tg_${msgId}`,
        text,
        url:        window.location.href,
        author,
        groupName:  getChatName(),
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

// Watch for new messages as they arrive
const observer = new MutationObserver(() => processMessages());
observer.observe(document.body, { childList: true, subtree: true });

// Initial scan after page settles
setTimeout(processMessages, 3000);
setInterval(processMessages, 4 * 60 * 1000);

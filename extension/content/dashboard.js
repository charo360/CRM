/**
 * Zilo Extension — Dashboard Bridge
 * Injected on the Zilo CRM web app pages.
 *
 * Acts as a secure bridge between the CRM dashboard (web page)
 * and the extension service worker.
 *
 * The web page cannot talk to the extension directly — this script
 * relays messages both ways via window.postMessage.
 */

// Signal to the dashboard that the extension is installed
window.postMessage({ type: 'ZILO_EXT_INSTALLED', version: '1.0.0' }, '*');

// Relay messages FROM dashboard TO extension
window.addEventListener('message', event => {
  if (event.source !== window) return;
  if (!event.data?.type?.startsWith('ZILO_TO_EXT')) return;

  const { requestId, payload } = event.data;

  chrome.runtime.sendMessage(payload, response => {
    window.postMessage({
      type:      'ZILO_FROM_EXT',
      requestId: requestId,
      response:  response || null,
      error:     chrome.runtime.lastError?.message || null,
    }, '*');
  });
});

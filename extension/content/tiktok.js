/**
 * Zilo Social Monitor — TikTok Content Script
 * Runs on: tiktok.com
 *
 * TikTok uses heavily obfuscated, frequently-changing CSS class names.
 * We anchor exclusively to data-e2e attributes — TikTok's own internal
 * test attributes which are far more stable across deploys.
 *
 * Monitors:
 * - Video captions in the main feed / For You page
 * - Search results
 * - Comments on individual video pages
 */

const SEEN_IDS = new Set();

// ── Extract post URL from a video container ────────────────────────────────

function extractVideoUrl(container) {
  const link = container.querySelector('a[href*="/video/"]');
  if (link) {
    try { return new URL(link.href, window.location.origin).href.split('?')[0]; }
    catch { return link.href.split('?')[0]; }
  }
  // On single video pages the URL IS the post URL
  if (window.location.pathname.includes('/video/')) {
    return window.location.href.split('?')[0];
  }
  return window.location.href;
}

function makeId(text, url) {
  const raw = (url + text.slice(0, 60)).replace(/\s/g, '');
  return btoa(unescape(encodeURIComponent(raw))).slice(0, 28);
}

// ── Scan video captions in feed / search ──────────────────────────────────

function scanCaptions() {
  // data-e2e selectors TikTok uses for captions
  const captionEls = document.querySelectorAll(
    '[data-e2e="video-desc"], ' +
    '[data-e2e="browse-video-desc"], ' +
    '[data-e2e="search-card-video-caption"]'
  );

  captionEls.forEach(el => {
    const text   = el.innerText?.trim();
    const url    = extractVideoUrl(el.closest('article, [data-e2e="recommend-list-item-container"], div') || document.body);
    const postId = makeId(text || '', url);

    if (!text || text.length < 8 || SEEN_IDS.has(postId)) return;
    SEEN_IDS.add(postId);

    // Author: username element near the caption
    const author =
      el.closest('article, [data-e2e*="item"]')
        ?.querySelector('[data-e2e="video-author-uniqueid"], [data-e2e*="author"] span')
        ?.innerText?.trim() || 'Unknown';

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:   'tiktok',
        postId,
        text,
        url,
        author,
        groupName:  getTikTokContext(),
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

// ── Scan comments on a video page ─────────────────────────────────────────

function scanComments() {
  if (!window.location.pathname.includes('/video/')) return;

  const commentEls = document.querySelectorAll(
    '[data-e2e="comment-level-1-text"], ' +
    '[data-e2e="comment-item-content"]'
  );

  commentEls.forEach(el => {
    const text   = el.innerText?.trim();
    const postId = makeId(text || '', window.location.href);

    if (!text || text.length < 5 || SEEN_IDS.has(postId)) return;
    SEEN_IDS.add(postId);

    const author =
      el.closest('[data-e2e="comment-level-1"]')
        ?.querySelector('[data-e2e="comment-username-1"]')
        ?.innerText?.trim() || 'Unknown';

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:   'tiktok',
        postId,
        text,
        url:        window.location.href.split('?')[0],
        author,
        groupName:  'TikTok Comment',
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

function getTikTokContext() {
  const path = window.location.pathname;
  if (path.includes('/search'))  return 'TikTok Search';
  if (path.includes('/video/'))  return 'TikTok Video';
  if (path.includes('/tag/'))    return `TikTok #${path.split('/tag/')[1]?.split('/')[0]}`;
  return 'TikTok Feed';
}

function processAll() {
  scanCaptions();
  scanComments();
}

const observer = new MutationObserver(() => processAll());
observer.observe(document.body, { childList: true, subtree: true });

setTimeout(processAll, 2500);
setInterval(processAll, 4 * 60 * 1000);

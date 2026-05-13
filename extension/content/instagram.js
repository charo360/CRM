/**
 * Zilo Social Monitor — Instagram Content Script
 * Runs on: instagram.com
 *
 * Monitors:
 * - Home feed posts + captions
 * - Explore page posts
 * - Hashtag pages
 * - Post comment sections (when user opens a post)
 *
 * Uses structural selectors + aria attributes over class names
 * because Instagram's generated class names change frequently.
 */

const SEEN_IDS = new Set();

function extractPostUrl(article) {
  // Post permalink is always in an <a href="/p/..."> inside the article
  const link = article.querySelector('a[href*="/p/"]');
  if (link) {
    try {
      return new URL(link.href, window.location.origin).href.split('?')[0];
    } catch {
      return link.href.split('?')[0];
    }
  }
  return window.location.href;
}

function makePostId(article) {
  const url = extractPostUrl(article);
  if (url !== window.location.href) return url;
  const text = article.innerText.trim().slice(0, 80);
  return btoa(unescape(encodeURIComponent(text))).slice(0, 24);
}

function extractCaption(article) {
  // Instagram captions sit in <h1> (post page) or <span dir="auto"> (feed)
  const candidates = [
    article.querySelector('h1'),
    article.querySelector('span[dir="auto"]'),
    article.querySelector('div[dir="auto"] span'),
    article.querySelector('li span'),
  ];
  for (const el of candidates) {
    const text = el?.innerText?.trim();
    if (text && text.length > 5) return text;
  }
  return article.innerText.trim().slice(0, 500);
}

function extractAuthor(article) {
  // Username appears in a link like /username/ near the top of the article
  const userLink = article.querySelector(
    'header a[role="link"], a[href^="/"][href$="/"] span'
  );
  return userLink?.innerText?.trim() || 'Unknown';
}

function processArticles() {
  const articles = document.querySelectorAll('article');

  articles.forEach(article => {
    const postId = makePostId(article);
    if (SEEN_IDS.has(postId)) return;
    SEEN_IDS.add(postId);

    const caption = extractCaption(article);
    if (!caption || caption.length < 8) return;

    // Skip ads
    const isAd = article.querySelector('[aria-label*="Sponsored"], [data-testid*="ad"]');
    if (isAd) return;

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:   'instagram',
        postId,
        text:       caption,
        url:        extractPostUrl(article),
        author:     extractAuthor(article),
        groupName:  getPageContext(),
        detectedAt: new Date().toISOString(),
      },
    });
  });

  // Also scan comments if user is on a post page
  if (window.location.pathname.includes('/p/')) {
    scanPostComments();
  }
}

function scanPostComments() {
  // Comment list items — each commenter's text is in a span
  const commentEls = document.querySelectorAll(
    'ul li span[dir="auto"], div[role="list"] span[dir="auto"]'
  );
  commentEls.forEach(el => {
    const text = el.innerText?.trim();
    if (!text || text.length < 10) return;

    const id = `comment_${btoa(unescape(encodeURIComponent(text.slice(0, 40)))).slice(0, 20)}`;
    if (SEEN_IDS.has(id)) return;
    SEEN_IDS.add(id);

    // Author: look for a username link near this element
    const author = el.closest('li')?.querySelector('a[role="link"]')?.innerText?.trim() || 'Unknown';

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:   'instagram',
        postId:     id,
        text,
        url:        window.location.href.split('?')[0],
        author,
        groupName:  'Instagram Comment',
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

function getPageContext() {
  const path = window.location.pathname;
  if (path.startsWith('/explore/tags/')) {
    return `#${path.split('/').filter(Boolean)[2] || 'explore'}`;
  }
  if (path.startsWith('/explore')) return 'Instagram Explore';
  if (path.startsWith('/p/'))     return 'Instagram Post';
  return 'Instagram Feed';
}

const observer = new MutationObserver(() => processArticles());
observer.observe(document.body, { childList: true, subtree: true });

setTimeout(processArticles, 2500);
setInterval(processArticles, 4 * 60 * 1000);

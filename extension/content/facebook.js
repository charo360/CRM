/**
 * Zilo Social Monitor — Facebook Groups Content Script
 * Runs on: facebook.com/groups/*
 *
 * What it does:
 * - Watches for new posts in the group feed using MutationObserver
 * - Extracts post text + permalink URL (no auth tokens, no cookies)
 * - Sends matches to the service worker which checks against the user's keywords
 */

const SEEN_IDS = new Set();

function getGroupName() {
  const h1 = document.querySelector('h1');
  return h1 ? h1.innerText.trim() : document.title.replace(' | Facebook', '').trim();
}

function extractPostUrl(article) {
  // Facebook post permalinks appear on the timestamp link or "Share" link
  const links = article.querySelectorAll('a[href]');
  for (const a of links) {
    const href = a.href || '';
    if (
      href.includes('/posts/') ||
      href.includes('/permalink/') ||
      href.includes('?story_fbid=')
    ) {
      // Clean tracking params
      try {
        const u = new URL(href);
        return u.origin + u.pathname;
      } catch {
        return href.split('?')[0];
      }
    }
  }
  return window.location.href;
}

function makePostId(article) {
  const url = extractPostUrl(article);
  if (url !== window.location.href) return url;
  // Fallback: hash the first 80 chars of text
  const text = article.innerText.trim().slice(0, 80);
  return btoa(unescape(encodeURIComponent(text))).slice(0, 24);
}

function processArticles() {
  const articles = document.querySelectorAll('div[role="article"]');

  articles.forEach(article => {
    const postId = makePostId(article);
    if (SEEN_IDS.has(postId)) return;
    SEEN_IDS.add(postId);

    const text = article.innerText.trim();
    if (text.length < 20) return; // Skip empty / nav articles

    // Author: first <strong> inside the article
    const author = article.querySelector('strong')?.innerText?.trim() || 'Unknown';

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform: 'facebook',
        postId,
        text,
        url: extractPostUrl(article),
        author,
        groupName: getGroupName(),
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

// Observe DOM mutations — catches posts loaded dynamically as user scrolls
const observer = new MutationObserver(() => processArticles());
observer.observe(document.body, { childList: true, subtree: true });

// Initial scan after page load
setTimeout(processArticles, 2000);

// Periodic re-scan every 4 minutes in case mutations were missed
setInterval(processArticles, 4 * 60 * 1000);

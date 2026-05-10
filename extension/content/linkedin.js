/**
 * Zilo Social Monitor — LinkedIn Content Script
 * Runs on: linkedin.com/feed, linkedin.com/groups
 */

const SEEN_IDS = new Set();

function extractPostUrl(article) {
  const links = article.querySelectorAll('a[href]');
  for (const a of links) {
    const href = a.href || '';
    if (href.includes('/posts/') || href.includes('activity-')) {
      return href.split('?')[0];
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

function processArticles() {
  // LinkedIn uses data-id on feed updates, and role="article" on posts
  const articles = document.querySelectorAll(
    'div[data-urn], div.feed-shared-update-v2, article'
  );

  articles.forEach(article => {
    const postId = makePostId(article);
    if (SEEN_IDS.has(postId)) return;
    SEEN_IDS.add(postId);

    const text = article.innerText.trim();
    if (text.length < 20) return;

    const author =
      article.querySelector('.update-components-actor__name')?.innerText?.trim() ||
      article.querySelector('[aria-label] span')?.innerText?.trim() ||
      'Unknown';

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform: 'linkedin',
        postId,
        text,
        url: extractPostUrl(article),
        author,
        groupName: document.title.replace(' | LinkedIn', '').trim(),
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

const observer = new MutationObserver(() => processArticles());
observer.observe(document.body, { childList: true, subtree: true });

setTimeout(processArticles, 2000);
setInterval(processArticles, 4 * 60 * 1000);

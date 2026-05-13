/**
 * Zilo Social Monitor — Reddit Content Script
 * Runs on: reddit.com/r/*
 * Reddit has stable selectors making this the most reliable platform.
 */

const SEEN_IDS = new Set();

function processArticles() {
  // Reddit post feed items
  const posts = document.querySelectorAll(
    'article, div[data-testid="post-container"], shreddit-post'
  );

  posts.forEach(post => {
    // Reddit uses data-fullname like "t3_abc123" as stable ID
    const postId =
      post.getAttribute('data-fullname') ||
      post.getAttribute('id') ||
      post.querySelector('a[data-click-id="body"]')?.href?.split('?')[0] ||
      post.innerText.trim().slice(0, 40);

    if (!postId || SEEN_IDS.has(postId)) return;
    SEEN_IDS.add(postId);

    const text = post.innerText.trim();
    if (text.length < 15) return;

    // Post URL
    const link = post.querySelector('a[data-click-id="body"], a[slot="full-post-link"]');
    const url = link ? new URL(link.href, window.location.origin).href : window.location.href;

    // Author
    const author =
      post.querySelector('[data-testid="post_author_link"]')?.innerText?.trim() ||
      post.querySelector('a[href*="/user/"]')?.innerText?.trim() ||
      'Unknown';

    const subreddit = window.location.pathname.split('/')[2] || 'Unknown';

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform: 'reddit',
        postId,
        text,
        url,
        author,
        groupName: `r/${subreddit}`,
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

const observer = new MutationObserver(() => processArticles());
observer.observe(document.body, { childList: true, subtree: true });

setTimeout(processArticles, 1500);
setInterval(processArticles, 4 * 60 * 1000);

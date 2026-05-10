/**
 * Zilo Social Monitor — Google Business Profile Content Script
 * Runs on: business.google.com
 *
 * Monitors the Reviews tab for new customer reviews.
 * Sends each unseen review to the Zilo queue so AI can draft a reply.
 * Anchors to aria-labels and text content — more stable than class names
 * on Google's frequently-updated Material UI.
 */

const SEEN_IDS = new Set();

// ── Extract star rating from a review card ────────────────────────────────

function getStarRating(card) {
  // Google renders stars as aria-label="X stars" on an img or span
  const starEl =
    card.querySelector('[aria-label*="star"]') ||
    card.querySelector('[role="img"][aria-label]');
  if (starEl) {
    const m = starEl.getAttribute('aria-label')?.match(/(\d)/);
    if (m) return parseInt(m[1], 10);
  }
  // Count filled star icons as fallback
  const filled = card.querySelectorAll('[data-value], .filled-star, [class*="full"]');
  return filled.length || 0;
}

// ── Build a stable ID from reviewer + text ───────────────────────────────

function makeId(reviewer, text) {
  const raw = (reviewer + text.slice(0, 50)).replace(/\s/g, '');
  return btoa(unescape(encodeURIComponent(raw))).slice(0, 28);
}

// ── Main review scanner ───────────────────────────────────────────────────

function scanReviews() {
  // Google Business review cards — try multiple selector strategies
  const cards = document.querySelectorAll(
    '[data-review-id], ' +
    '[class*="review-list-item"], ' +
    '[jsdata*="review"], ' +
    // Newer Google Business UI uses these containers
    'div[class*="VjZXId"], ' +
    'li[class*="review"]'
  );

  // Fallback: find all sections that contain a star aria-label and text
  const targets = cards.length > 0 ? Array.from(cards) : findReviewCardsFallback();

  targets.forEach(card => {
    // Reviewer name
    const reviewer =
      card.querySelector('[class*="author"], [class*="reviewer"], [class*="name"], h3, strong')
          ?.innerText?.trim() ||
      card.querySelector('a[href*="maps/contrib"]')?.innerText?.trim() ||
      'Anonymous';

    // Review text
    const textEl =
      card.querySelector('[class*="review-text"], [class*="body"], [jsname="fbQN7e"], p, span[dir]');
    const text = textEl?.innerText?.trim() || '';

    if (!text || text.length < 4) return;

    const reviewId =
      card.getAttribute('data-review-id') ||
      card.getAttribute('data-id') ||
      makeId(reviewer, text);

    if (SEEN_IDS.has(reviewId)) return;
    SEEN_IDS.add(reviewId);

    const stars   = getStarRating(card);
    const postId  = `gbp_${reviewId}`;

    // Skip if already replied (reply text exists in card)
    const hasReply = card.querySelector('[class*="owner-response"], [class*="reply"], [aria-label*="response"]');
    const alreadyReplied = !!hasReply && hasReply.innerText?.trim().length > 0;

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:      'google_business',
        postId,
        text,
        url:           window.location.href,
        author:        reviewer,
        groupName:     'Google Review',
        detectedAt:    new Date().toISOString(),
        stars,
        alreadyReplied,
      },
    });
  });
}

// ── Fallback: locate review cards by star icon proximity ─────────────────

function findReviewCardsFallback() {
  const starEls = document.querySelectorAll('[aria-label*="star" i]');
  const cards   = new Set();
  starEls.forEach(el => {
    // Walk up to find a card-like ancestor
    let node = el;
    for (let i = 0; i < 6; i++) {
      node = node.parentElement;
      if (!node) break;
      const tag  = node.tagName?.toLowerCase();
      const role = node.getAttribute('role');
      if (tag === 'li' || tag === 'article' || role === 'listitem' || role === 'article') {
        cards.add(node);
        break;
      }
    }
  });
  return Array.from(cards);
}

const observer = new MutationObserver(() => scanReviews());
observer.observe(document.body, { childList: true, subtree: true });

setTimeout(scanReviews, 3000);
setInterval(scanReviews, 4 * 60 * 1000);

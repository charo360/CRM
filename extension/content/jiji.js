/**
 * Zilo Social Monitor — Jiji Classifieds Content Script
 * Runs on: jiji.com.gh, jiji.ng, jiji.co.ke, jiji.co.tz, jiji.co.ug, jiji.co.zm
 *
 * Scans listing cards for buyer intent posts ("looking for", "wanted", etc.)
 * and any listing that matches the user's saved keywords.
 */

const SEEN_IDS = new Set();

function makeId(url, title) {
  const raw = (url + title.slice(0, 40)).replace(/\s/g, '');
  return btoa(unescape(encodeURIComponent(raw))).slice(0, 28);
}

function getSiteContext() {
  const host = window.location.hostname;
  if (host.includes('.ng'))  return 'Jiji Nigeria';
  if (host.includes('.ke'))  return 'Jiji Kenya';
  if (host.includes('.gh'))  return 'Jiji Ghana';
  if (host.includes('.tz'))  return 'Jiji Tanzania';
  if (host.includes('.ug'))  return 'Jiji Uganda';
  if (host.includes('.zm'))  return 'Jiji Zambia';
  return 'Jiji';
}

function scanListings() {
  // Jiji listing card selectors (stable across their deploys)
  const cards = document.querySelectorAll(
    'article.b-list-advert__item, ' +
    '.b-advert-tile, ' +
    '[class*="qa-advert-list-item"], ' +
    'li[class*="advert"], ' +
    '[data-id][class*="item"]'
  );

  cards.forEach(card => {
    // Title
    const titleEl =
      card.querySelector('h2.qa-advert-title, .b-advert-tile__title, [class*="title"] h2, [class*="title"] h3') ||
      card.querySelector('h2, h3');
    const title = titleEl?.innerText?.trim() || '';

    // Description snippet
    const descEl = card.querySelector('.b-advert-tile__description, [class*="description"], p');
    const desc   = descEl?.innerText?.trim() || '';

    const text = [title, desc].filter(Boolean).join(' — ');
    if (!text || text.length < 8) return;

    // Link
    const linkEl = card.querySelector('a[href]');
    const url    = linkEl
      ? new URL(linkEl.getAttribute('href'), window.location.origin).href.split('?')[0]
      : window.location.href;

    const postId = makeId(url, title);
    if (SEEN_IDS.has(postId)) return;
    SEEN_IDS.add(postId);

    // Price
    const priceEl = card.querySelector('.b-advert-tile__price, [class*="price"], [data-price]');
    const price   = priceEl?.innerText?.trim() || '';

    // Location
    const locEl = card.querySelector('.b-advert-tile__region, [class*="region"], [class*="location"]');
    const loc   = locEl?.innerText?.trim() || '';

    // Seller
    const sellerEl = card.querySelector('[class*="user-name"], [class*="seller"]');
    const seller   = sellerEl?.innerText?.trim() || 'Seller';

    const fullText = [text, price ? `Price: ${price}` : '', loc ? `Location: ${loc}` : ''].filter(Boolean).join(' | ');

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:   'jiji',
        postId:     `jiji_${postId}`,
        text:       fullText,
        url,
        author:     seller,
        groupName:  getSiteContext(),
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

const observer = new MutationObserver(() => scanListings());
observer.observe(document.body, { childList: true, subtree: true });

setTimeout(scanListings, 2500);
setInterval(scanListings, 4 * 60 * 1000);

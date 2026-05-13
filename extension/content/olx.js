/**
 * Zilo Social Monitor — OLX Classifieds Content Script
 * Runs on: olx.com.ng, olx.co.za, olx.co.ke, olx.com.gh, olx.co.tz
 *
 * OLX uses data-aut-id attributes for testing — far more stable than class names.
 */

const SEEN_IDS = new Set();

function makeId(url, title) {
  const raw = (url + title.slice(0, 40)).replace(/\s/g, '');
  return btoa(unescape(encodeURIComponent(raw))).slice(0, 28);
}

function getSiteContext() {
  const host = window.location.hostname;
  if (host.includes('.ng'))  return 'OLX Nigeria';
  if (host.includes('.za'))  return 'OLX South Africa';
  if (host.includes('.ke'))  return 'OLX Kenya';
  if (host.includes('.gh'))  return 'OLX Ghana';
  if (host.includes('.tz'))  return 'OLX Tanzania';
  return 'OLX';
}

function scanListings() {
  // OLX uses data-aut-id for major elements — stable across redesigns
  const cards = document.querySelectorAll(
    '[data-aut-id="itemBox"], ' +
    '[data-aut-id="itemList"] li, ' +
    'li[class*="item"], ' +
    '[class*="listing-item"], ' +
    '[class*="AdCard"]'
  );

  cards.forEach(card => {
    const titleEl =
      card.querySelector('[data-aut-id="itemTitle"]') ||
      card.querySelector('span[class*="title"], h2, h3');
    const title = titleEl?.innerText?.trim() || '';
    if (!title || title.length < 4) return;

    const linkEl = card.querySelector('a[href]');
    const url    = linkEl
      ? new URL(linkEl.getAttribute('href'), window.location.origin).href.split('?')[0]
      : window.location.href;

    const postId = makeId(url, title);
    if (SEEN_IDS.has(postId)) return;
    SEEN_IDS.add(postId);

    const priceEl  = card.querySelector('[data-aut-id="itemPrice"], [class*="price"]');
    const price    = priceEl?.innerText?.trim() || '';

    const locEl    = card.querySelector('[data-aut-id="item-location"], [class*="location"]');
    const location = locEl?.innerText?.trim() || '';

    const descEl   = card.querySelector('[data-aut-id="itemDetails"], [class*="description"], p');
    const desc     = descEl?.innerText?.trim() || '';

    const fullText = [title, desc, price ? `Price: ${price}` : '', location ? `📍 ${location}` : '']
      .filter(Boolean).join(' | ');

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:   'olx',
        postId:     `olx_${postId}`,
        text:       fullText,
        url,
        author:     'Seller',
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

/**
 * Zilo Social Monitor — Service Worker
 *
 * Three jobs:
 * 1. MONITOR  — receives posts from content scripts, keyword-matches, sends to CRM queue
 * 2. SCANNER  — every 2 hours opens each saved group in a background tab and scans it
 * 3. AUTO-POST — every 5 min, fetches CRM-approved items, opens each URL in a
 *                background tab, injects the poster script, closes tab when done
 */

// ── Constants ─────────────────────────────────────────────────────────────────

const SENT_URLS      = new Set();   // dedupe monitor sends this session
const POSTING_URLS   = new Set();   // prevent double-posting same URL concurrently

const MONITOR_RATE_WINDOW = 60_000;
const MONITOR_MAX_PM = 5;
let monitorSentPM = 0;
let monitorWindowStart = Date.now();

const POST_INTERVAL_MS = 25_000;

// ── Helpers ───────────────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function resetMonitorRate() {
  if (Date.now() - monitorWindowStart > MONITOR_RATE_WINDOW) {
    monitorSentPM = 0;
    monitorWindowStart = Date.now();
  }
}

function isMonitorRateLimited() {
  resetMonitorRate();
  return monitorSentPM >= MONITOR_MAX_PM;
}

function keywordMatch(text, keywords) {
  const lower = text.toLowerCase();
  return keywords.filter(kw => kw && lower.includes(kw.toLowerCase().trim()));
}

function normalizeGroup(g) {
  if (typeof g === 'string') return { url: g, name: g.replace(/.*\/groups\//, '').replace(/-/g, ' ') };
  return g;
}

async function getConfig() {
  return new Promise(resolve => {
    chrome.storage.sync.get(
      ['ziloToken', 'ziloApiUrl', 'keywords', 'autoPostEnabled', 'groups'],
      result => resolve({
        token:           result.ziloToken || '',
        apiUrl:          (result.ziloApiUrl || 'http://localhost:8000/api').replace(/\/$/, ''),
        keywords:        Array.isArray(result.keywords) ? result.keywords : [],
        autoPostEnabled: result.autoPostEnabled !== false,
        groups:          (result.groups || []).map(normalizeGroup),
      })
    );
  });
}

function authHeaders(token) {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

// ── Monitor: send matched post to CRM ────────────────────────────────────────

async function sendMatchToCRM(post, matchedKeywords, config) {
  const res = await fetch(`${config.apiUrl}/action-mode/extension/post`, {
    method:  'POST',
    headers: authHeaders(config.token),
    body:    JSON.stringify({
      text:             post.text.slice(0, 1000),
      url:              post.url,
      author:           post.author,
      group_name:       post.groupName,
      platform:         post.platform,
      matched_keywords: matchedKeywords,
      timestamp:        post.detectedAt,
    }),
  });
  if (!res.ok) throw new Error(`CRM ${res.status}`);
  return res.json();
}

function notify(title, message) {
  chrome.notifications.create({
    type:     'basic',
    iconUrl:  'icons/icon48.png',
    title,
    message,
    priority: 1,
  });
}

// ── Dashboard bridge + group management messages ──────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  // PING — dashboard checks if extension is installed
  if (message.type === 'ZILO_PING') {
    chrome.storage.sync.get(['ziloToken', 'keywords', 'groups', 'autoPostEnabled'], result => {
      sendResponse({
        status:          'installed',
        connected:       !!result.ziloToken,
        keywordCount:    (result.keywords || []).length,
        groupCount:      (result.groups || []).length,
        autoPostEnabled: result.autoPostEnabled !== false,
      });
    });
    return true;
  }

  // CONNECT — dashboard sends token + full settings to extension
  if (message.type === 'ZILO_CONNECT') {
    chrome.storage.sync.set({
      ziloToken:       message.token       || '',
      ziloApiUrl:      message.apiUrl      || 'http://localhost:8000/api',
      keywords:        message.keywords    || [],
      groups:          (message.groups || []).map(normalizeGroup),
      autoPostEnabled: message.autoPost    !== false,
    }, () => {
      sendResponse({ status: 'connected' });
    });
    return true;
  }

  // SYNC — pull latest settings from CRM and store them
  if (message.type === 'ZILO_SYNC') {
    (async () => {
      const config = await getConfig();
      if (!config.token) { sendResponse({ status: 'not_connected' }); return; }
      try {
        const res = await fetch(`${config.apiUrl}/action-mode/social/settings`, {
          headers: authHeaders(config.token),
        });
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        const groups = (data.groups || []).map(normalizeGroup);
        await chrome.storage.sync.set({
          keywords: data.keywords || [],
          groups,
        });
        sendResponse({
          status:       'synced',
          keywordCount: (data.keywords || []).length,
          groupCount:   groups.length,
        });
      } catch (err) {
        sendResponse({ status: 'error', message: err.message });
      }
    })();
    return true;
  }

  // DISCONNECT — clear extension storage
  if (message.type === 'ZILO_DISCONNECT') {
    chrome.storage.sync.clear(() => sendResponse({ status: 'disconnected' }));
    return true;
  }

  // TOGGLE_AUTO_POST
  if (message.type === 'ZILO_TOGGLE_AUTO_POST') {
    chrome.storage.sync.set({ autoPostEnabled: message.enabled }, () => {
      sendResponse({ status: 'ok', autoPostEnabled: message.enabled });
    });
    return true;
  }

  // GET_GROUPS — popup loads saved groups + last scan time
  if (message.type === 'GET_GROUPS') {
    chrome.storage.sync.get(['groups'], result => {
      const groups = (result.groups || []).map(normalizeGroup);
      chrome.storage.local.get(['lastScanTime'], local => {
        sendResponse({ groups, lastScanTime: local.lastScanTime || null });
      });
    });
    return true;
  }

  // ADD_GROUP
  if (message.type === 'ADD_GROUP') {
    chrome.storage.sync.get(['groups'], result => {
      const groups = (result.groups || []).map(normalizeGroup);
      if (groups.find(g => g.url === message.url)) {
        sendResponse({ status: 'exists', groups });
        return;
      }
      groups.push({ url: message.url, name: message.name || message.url });
      chrome.storage.sync.set({ groups }, () => sendResponse({ status: 'added', groups }));
    });
    return true;
  }

  // REMOVE_GROUP
  if (message.type === 'REMOVE_GROUP') {
    chrome.storage.sync.get(['groups'], result => {
      const groups = (result.groups || []).map(normalizeGroup).filter(g => g.url !== message.url);
      chrome.storage.sync.set({ groups }, () => sendResponse({ status: 'removed', groups }));
    });
    return true;
  }

  // SCAN_NOW — user triggered scan from popup
  if (message.type === 'SCAN_NOW') {
    (async () => {
      const config = await getConfig();
      if (!config.token) { sendResponse({ status: 'not_connected' }); return; }
      if (!config.groups.length) { sendResponse({ status: 'no_groups' }); return; }
      sendResponse({ status: 'scanning', count: config.groups.length });
      runGroupScan(config); // fire and forget
    })();
    return true;
  }

  // DISCOVER_GROUPS — open FB search, extract group suggestions
  if (message.type === 'DISCOVER_GROUPS') {
    (async () => {
      const config = await getConfig();
      if (!config.keywords.length) { sendResponse({ status: 'no_keywords', groups: [] }); return; }
      const query = config.keywords.slice(0, 2).join(' ');
      const searchUrl = `https://www.facebook.com/search/groups/?q=${encodeURIComponent(query)}`;
      let tab;
      try {
        tab = await chrome.tabs.create({ url: searchUrl, active: false });
        await waitForTabLoad(tab.id, 15_000).catch(() => {});
        await sleep(5_000); // wait for FB React to render results
        const results = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func:   extractFacebookGroups,
        });
        const groups = results?.[0]?.result || [];
        sendResponse({ status: 'ok', groups });
      } catch (err) {
        sendResponse({ status: 'error', message: err.message, groups: [] });
      } finally {
        if (tab?.id) chrome.tabs.remove(tab.id).catch(() => {});
      }
    })();
    return true;
  }
});

// ── Monitor message handler ───────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'NEW_POST') {
    const post = message.payload;
    if (!post?.text || !post?.url) return;
    if (SENT_URLS.has(post.url))   return;

    (async () => {
      const config = await getConfig();
      if (!config.token || !config.keywords.length) {
        sendResponse({ status: 'not_configured' }); return;
      }

      const matched = keywordMatch(post.text, config.keywords);
      if (!matched.length) { sendResponse({ status: 'no_match' }); return; }
      if (isMonitorRateLimited()) { sendResponse({ status: 'rate_limited' }); return; }

      SENT_URLS.add(post.url);
      monitorSentPM++;

      try {
        const result = await sendMatchToCRM(post, matched, config);
        if (result.status === 'queued') {
          notify(
            `🎯 Match on ${post.platform}`,
            `"${post.text.slice(0, 100)}…"\nKeywords: ${matched.join(', ')}`
          );
        }
        sendResponse({ status: result.status });
      } catch (err) {
        SENT_URLS.delete(post.url);
        sendResponse({ status: 'error', message: err.message });
      }
    })();
    return true;
  }

  if (message.type === 'SYNC_KEYWORDS') {
    (async () => {
      const config = await getConfig();
      if (!config.token) { sendResponse({ status: 'not_connected' }); return; }
      try {
        const res = await fetch(`${config.apiUrl}/action-mode/social/settings`, {
          headers: authHeaders(config.token),
        });
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        await chrome.storage.sync.set({ keywords: data.keywords || [] });
        sendResponse({ status: 'synced', count: (data.keywords || []).length });
      } catch (err) {
        sendResponse({ status: 'error', message: err.message });
      }
    })();
    return true;
  }
});

// ── Group scanner ─────────────────────────────────────────────────────────────

chrome.alarms.create('scanGroups', { periodInMinutes: 120 });

chrome.alarms.onAlarm.addListener(async alarm => {
  if (alarm.name !== 'scanGroups') return;
  const config = await getConfig();
  if (!config.token || !config.groups.length) return;
  await runGroupScan(config);
});

async function runGroupScan(config) {
  let totalFound = 0;

  for (const group of config.groups) {
    let tab;
    try {
      tab = await chrome.tabs.create({ url: group.url, active: false });
      await waitForTabLoad(tab.id, 15_000).catch(() => {});
      await sleep(4_000);

      const isFacebook = group.url.includes('facebook.com');

      if (isFacebook) {
        const results = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func:   facebookGroupScanner,
          args:   [config.keywords],
        }).catch(() => []);

        const matches = results?.[0]?.result || [];
        for (const post of matches) {
          if (SENT_URLS.has(post.url)) continue;
          try {
            SENT_URLS.add(post.url);
            const result = await sendMatchToCRM(post, post.matchedKeywords, config);
            if (result.status === 'queued') totalFound++;
          } catch { SENT_URLS.delete(post.url); }
        }
      } else {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func:   universalScanner,
          args:   [config.keywords],
        }).catch(() => {});
        await sleep(6_000);
      }

    } catch (err) {
      console.error('[Zilo scan]', err.message);
    } finally {
      if (tab?.id) chrome.tabs.remove(tab.id).catch(() => {});
    }

    await sleep(3_000);
  }

  await chrome.storage.local.set({ lastScanTime: new Date().toISOString() });

  if (totalFound > 0) {
    notify('🎯 Zilo Scan Complete', `Found ${totalFound} matching post${totalFound !== 1 ? 's' : ''} in your groups`);
  }

  return totalFound;
}

// ── Facebook group scanner (injected into group tab, returns matches) ─────────
// Runs inside the FB group page. Must be self-contained — no external refs.

function facebookGroupScanner(keywords) {
  const articles = document.querySelectorAll('div[role="article"]');
  const results  = [];
  const kwLower  = keywords.map(k => k.toLowerCase().trim()).filter(Boolean);
  const seen     = new Set();

  articles.forEach(article => {
    const text = article.innerText?.trim() || '';
    if (text.length < 30) return;

    const textLower = text.toLowerCase();
    const matched   = kwLower.filter(kw => textLower.includes(kw));
    if (!matched.length) return;

    let url = location.href;
    for (const a of article.querySelectorAll('a[href]')) {
      const h = a.href || '';
      if (h.includes('/posts/') || h.includes('/permalink/') || h.includes('?story_fbid=')) {
        try { url = new URL(h).origin + new URL(h).pathname; } catch {}
        break;
      }
    }

    const key = url + text.slice(0, 40);
    if (seen.has(key)) return;
    seen.add(key);

    results.push({
      text:            text.slice(0, 1000),
      url,
      author:          article.querySelector('strong')?.innerText?.trim() || 'Unknown',
      groupName:       document.querySelector('h1')?.innerText?.trim() ||
                       document.title.replace(' | Facebook', '').trim(),
      platform:        'facebook',
      matchedKeywords: matched,
      detectedAt:      new Date().toISOString(),
    });
  });

  return results;
}

// ── Facebook group discovery (injected into FB search results page) ───────────

function extractFacebookGroups() {
  const groups = [];
  const seen   = new Set();
  const skip   = new Set(['feed', 'create', 'discover', 'joins', 'requests', 'search', 'notifications']);

  document.querySelectorAll('a[href*="/groups/"]').forEach(a => {
    const href  = a.href || '';
    const match = href.match(/facebook\.com\/groups\/([^/?#&]+)/);
    if (!match) return;

    const groupId = match[1];
    if (skip.has(groupId) || seen.has(groupId)) return;
    seen.add(groupId);

    // Walk up to find the card container and extract a clean name
    let name = '';
    let node = a;
    for (let i = 0; i < 6 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const spans = node.querySelectorAll('span[dir="auto"]');
      for (const s of spans) {
        const t = s.innerText?.trim();
        if (t && t.length > 3 && t.length < 80 && !/^\d+$/.test(t)) { name = t; break; }
      }
      if (name) break;
    }
    if (!name) name = a.innerText?.trim() || '';
    if (!name || name.length < 2) return;

    groups.push({
      url:  `https://www.facebook.com/groups/${groupId}`,
      name: name.slice(0, 60),
    });
  });

  return groups.slice(0, 12);
}

// ── Auto-poster: alarm setup ──────────────────────────────────────────────────

chrome.alarms.create('autoPost', { periodInMinutes: 5 });

chrome.alarms.onAlarm.addListener(async alarm => {
  if (alarm.name !== 'autoPost') return;
  const config = await getConfig();
  if (!config.token || !config.autoPostEnabled) return;
  await runAutoPostBatch(config);
});

chrome.runtime.onStartup.addListener(async () => {
  const config = await getConfig();
  if (config.token && config.autoPostEnabled) {
    await sleep(8000);
    await runAutoPostBatch(config);
  }
});

// ── Auto-poster: core batch runner ────────────────────────────────────────────

async function runAutoPostBatch(config) {
  let items;
  try {
    const res = await fetch(`${config.apiUrl}/action-mode/extension/approved-posts`, {
      headers: authHeaders(config.token),
    });
    if (!res.ok) return;
    const data = await res.json();
    items = data.items || [];
  } catch {
    return;
  }

  if (!items.length) return;

  notify(
    '⚡ Zilo — Auto-posting started',
    `${items.length} approved comment${items.length !== 1 ? 's' : ''} queued to post`
  );

  let posted = 0;
  for (const item of items) {
    const url      = item.metadata?.url;
    const comment  = item.draft_content;
    const platform = item.metadata?.platform || 'facebook';

    if (!url || !comment || POSTING_URLS.has(url)) continue;
    POSTING_URLS.add(url);

    const success = await postInTab(url, comment, platform, config, item.metadata || {});

    if (success) {
      await markPosted(item._id, config);
      posted++;
    }

    POSTING_URLS.delete(url);

    if (posted < items.length) {
      await sleep(POST_INTERVAL_MS + Math.random() * 10_000);
    }
  }

  if (posted > 0) {
    notify(
      '✅ Zilo — Auto-posting done',
      `${posted} comment${posted !== 1 ? 's' : ''} posted successfully`
    );
  }
}

// ── Open tab + inject poster ──────────────────────────────────────────────────

async function postInTab(url, comment, platform, config, metadata = {}) {
  let tab;
  try {
    tab = await chrome.tabs.create({ url, active: false });
    await waitForTabLoad(tab.id, 15_000);
    await sleep(2500 + Math.random() * 1500);

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func:   posterScript,
      args:   [comment, platform, metadata],
    });

    const result = results?.[0]?.result;
    return result?.success === true;

  } catch (err) {
    console.error('[Zilo auto-post] Error:', err.message);
    return false;
  } finally {
    if (tab?.id) {
      await sleep(2000);
      chrome.tabs.remove(tab.id).catch(() => {});
    }
  }
}

function waitForTabLoad(tabId, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Tab load timeout')), timeoutMs);

    function listener(id, changeInfo) {
      if (id === tabId && changeInfo.status === 'complete') {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

// ── Mark posted in CRM ────────────────────────────────────────────────────────

async function markPosted(itemId, config) {
  try {
    await fetch(`${config.apiUrl}/action-mode/extension/mark-posted`, {
      method:  'POST',
      headers: authHeaders(config.token),
      body:    JSON.stringify({ item_id: itemId }),
    });
  } catch { /* non-critical */ }
}

// ── Universal scanner (injected into every non-Facebook Watch URL tab) ────────

function universalScanner(keywords) {
  if (!keywords || !keywords.length) return;

  const SEEN_KEY   = '__zilo_universal_seen__';
  const seen       = new Set(window[SEEN_KEY] || []);
  window[SEEN_KEY] = seen;

  function makeId(text, url) {
    const raw = (url + text.slice(0, 50)).replace(/\s/g, '');
    try { return btoa(unescape(encodeURIComponent(raw))).slice(0, 28); } catch { return Math.random().toString(36).slice(2); }
  }

  function kwMatch(text) {
    const lower = text.toLowerCase();
    return keywords.filter(k => k && lower.includes(k.toLowerCase().trim()));
  }

  const cardSelectors = [
    'article', 'li[class*="item"]', 'li[class*="listing"]', 'li[class*="result"]',
    '[class*="listing-item"]', '[class*="advert"]', '[class*="AdCard"]',
    '[class*="product-card"]', '[class*="search-result"]', '[class*="post-item"]',
    '[class*="ad-item"]', '[data-aut-id="itemBox"]', '[data-testid*="listing"]',
    '[class*="classifieds"] li', '[class*="grid"] [class*="card"]',
  ];

  let cards = [];
  for (const sel of cardSelectors) {
    const found = Array.from(document.querySelectorAll(sel));
    if (found.length > 0) { cards = found; break; }
  }

  if (cards.length === 0) {
    const bodyText = document.body.innerText?.trim() || '';
    const matched  = kwMatch(bodyText);
    if (matched.length > 0) {
      const id = makeId(bodyText, window.location.href);
      if (!seen.has(id)) {
        seen.add(id);
        chrome.runtime.sendMessage({
          type: 'NEW_POST',
          payload: {
            platform:   'web',
            postId:     `web_${id}`,
            text:       bodyText.slice(0, 600),
            url:        window.location.href.split('?')[0],
            author:     window.location.hostname,
            groupName:  document.title?.slice(0, 60) || window.location.hostname,
            detectedAt: new Date().toISOString(),
          },
        });
      }
    }
    return;
  }

  cards.forEach(card => {
    const text = card.innerText?.trim() || '';
    if (!text || text.length < 12) return;

    const matched = kwMatch(text);
    if (!matched.length) return;

    const link = card.querySelector('a[href]');
    const url  = link
      ? (() => { try { return new URL(link.href, window.location.origin).href.split('?')[0]; } catch { return window.location.href; } })()
      : window.location.href.split('?')[0];

    const id = makeId(url, text);
    if (seen.has(id)) return;
    seen.add(id);

    const titleEl = card.querySelector('h1, h2, h3, h4, [class*="title"]');
    const title   = titleEl?.innerText?.trim() || text.slice(0, 80);

    chrome.runtime.sendMessage({
      type: 'NEW_POST',
      payload: {
        platform:   'web',
        postId:     `web_${id}`,
        text:       text.slice(0, 600),
        url,
        author:     window.location.hostname,
        groupName:  document.title?.slice(0, 60) || window.location.hostname,
        title,
        detectedAt: new Date().toISOString(),
      },
    });
  });
}

// ── Poster script (injected into the tab) ────────────────────────────────────

function posterScript(commentText, platform, metadata = {}) {
  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function jitter(base) { return base + Math.random() * base * 0.4; }

  async function typeText(el, text) {
    el.focus();
    await sleep(jitter(200));
    document.execCommand('selectAll', false);
    document.execCommand('insertText', false, text);
    el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text }));
    await sleep(jitter(400));
  }

  async function waitFor(selector, timeout = 8000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const el = document.querySelector(selector);
      if (el) return el;
      await sleep(300);
    }
    return null;
  }

  async function postFacebook() {
    const trigger = await waitFor(
      '[aria-label*="comment" i], [aria-placeholder*="comment" i], [data-lexical-editor="true"]',
      8000
    );
    if (!trigger) return { success: false, error: 'Comment box not found' };
    trigger.click();
    await sleep(jitter(600));
    const box = document.querySelector(
      '[contenteditable="true"][aria-label*="comment" i], ' +
      '[contenteditable="true"][aria-placeholder*="comment" i], ' +
      '[contenteditable="true"][role="textbox"]'
    ) || trigger;
    await typeText(box, commentText);
    const submitBtn = document.querySelector('[aria-label="Comment" i], button[type="submit"]');
    if (submitBtn) {
      submitBtn.click();
    } else {
      box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
    }
    await sleep(jitter(1500));
    return { success: true };
  }

  async function postLinkedIn() {
    const trigger = await waitFor(
      '[placeholder*="comment" i], .comments-comment-box__input, [aria-label*="comment" i]',
      8000
    );
    if (!trigger) return { success: false, error: 'Comment box not found' };
    trigger.click();
    await sleep(jitter(600));
    const box = document.querySelector(
      '[contenteditable="true"].ql-editor, ' +
      '[contenteditable="true"][aria-label*="comment" i], ' +
      '.comments-comment-box__detach-trigger [contenteditable="true"]'
    ) || trigger;
    await typeText(box, commentText);
    const submitBtn = document.querySelector(
      'button.comments-comment-box__submit-button, button[aria-label*="Post comment" i]'
    );
    if (submitBtn) submitBtn.click();
    await sleep(jitter(1500));
    return { success: true };
  }

  async function postReddit() {
    const trigger = await waitFor(
      '[placeholder*="comment" i], [data-click-id="text"], shreddit-composer',
      8000
    );
    if (!trigger) return { success: false, error: 'Comment box not found' };
    trigger.click();
    await sleep(jitter(600));
    const textarea = document.querySelector('textarea[id*="comment"], .public-DraftEditor-content, [contenteditable="true"]');
    if (!textarea) return { success: false, error: 'Textarea not found' };
    if (textarea.tagName === 'TEXTAREA') {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(textarea, commentText);
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      await typeText(textarea, commentText);
    }
    await sleep(jitter(500));
    const submitBtn = document.querySelector('button[type="submit"]:not([disabled]), button.save[type="submit"]');
    if (submitBtn) submitBtn.click();
    await sleep(jitter(1500));
    return { success: true };
  }

  async function postInstagram() {
    const trigger = await waitFor(
      'textarea[placeholder*="comment" i], textarea[aria-label*="comment" i], form textarea',
      8000
    );
    if (!trigger) return { success: false, error: 'Instagram comment box not found' };
    trigger.click();
    trigger.focus();
    await sleep(jitter(500));
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    nativeSetter.call(trigger, commentText);
    trigger.dispatchEvent(new Event('input', { bubbles: true }));
    trigger.dispatchEvent(new Event('change', { bubbles: true }));
    await sleep(jitter(600));
    const postBtn = await waitFor('button[type="submit"]:not([disabled]), form button:not([disabled])', 3000);
    if (postBtn) {
      postBtn.click();
    } else {
      trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
    }
    await sleep(jitter(1500));
    return { success: true };
  }

  async function postTelegram() {
    const input = await waitFor(
      '#editable-message-text, div[contenteditable="true"].input-message-input, ' +
      '.composer_rich_textarea, div[contenteditable="true"][role="textbox"]',
      8000
    );
    if (!input) return { success: false, error: 'Telegram input not found' };
    input.focus();
    await sleep(jitter(400));
    await typeText(input, commentText);
    await sleep(jitter(400));
    const sendBtn = document.querySelector('.btn-send:not(.is-hidden), button.send[data-testid="send"]');
    if (sendBtn) {
      sendBtn.click();
    } else {
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
    }
    await sleep(jitter(1000));
    return { success: true };
  }

  async function postWhatsApp() {
    const input = await waitFor(
      '[data-testid="conversation-compose-box-input"], ' +
      'div[contenteditable="true"][data-tab="10"], footer div[contenteditable="true"]',
      8000
    );
    if (!input) return { success: false, error: 'WhatsApp input not found' };
    input.focus();
    await sleep(jitter(400));
    await typeText(input, commentText);
    await sleep(jitter(300));
    const sendBtn = document.querySelector(
      '[data-testid="send"], button[data-testid="compose-btn-send"], span[data-icon="send"]'
    );
    if (sendBtn) {
      sendBtn.click();
    } else {
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
    }
    await sleep(jitter(1000));
    return { success: true };
  }

  async function postGoogleReply() {
    const reviewerName = metadata?.author || '';
    await sleep(jitter(1000));
    const allButtons   = Array.from(document.querySelectorAll('button, [role="button"]'));
    const replyButtons = allButtons.filter(b => {
      const txt = b.textContent?.trim().toLowerCase();
      const lbl = b.getAttribute('aria-label')?.toLowerCase() || '';
      return txt === 'reply' || txt === 'respond' || lbl.includes('reply') || lbl.includes('respond');
    });
    let targetReplyBtn = null;
    if (reviewerName && replyButtons.length > 1) {
      for (const btn of replyButtons) {
        let node = btn;
        for (let i = 0; i < 10; i++) {
          node = node.parentElement;
          if (!node) break;
          if (node.innerText?.includes(reviewerName)) { targetReplyBtn = btn; break; }
        }
        if (targetReplyBtn) break;
      }
    }
    if (!targetReplyBtn) targetReplyBtn = replyButtons[0];
    if (!targetReplyBtn) return { success: false, error: 'No reply button found' };
    targetReplyBtn.click();
    await sleep(jitter(800));
    const replyBox = await waitFor(
      'textarea[aria-label*="reply" i], textarea[placeholder*="reply" i], ' +
      '[contenteditable="true"][aria-label*="reply" i], [contenteditable="true"][aria-multiline="true"]',
      6000
    );
    if (!replyBox) return { success: false, error: 'Reply input not found' };
    if (replyBox.tagName === 'TEXTAREA') {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(replyBox, commentText);
      replyBox.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      await typeText(replyBox, commentText);
    }
    await sleep(jitter(600));
    const submitBtn = await waitFor(
      'button[aria-label*="Post reply" i], button[aria-label*="Submit" i], div[role="button"][aria-label*="Post" i]',
      3000
    );
    if (submitBtn) {
      submitBtn.click();
    } else {
      const nearby = Array.from(document.querySelectorAll('button')).find(b => /post|submit|reply/i.test(b.textContent?.trim()));
      if (nearby) nearby.click();
    }
    await sleep(jitter(1500));
    return { success: true };
  }

  async function postTikTok() {
    const trigger = await waitFor(
      '[data-e2e="comment-input"], div[contenteditable="true"][data-e2e*="comment"], ' +
      '[placeholder*="comment" i][contenteditable="true"]',
      8000
    );
    if (!trigger) return { success: false, error: 'TikTok comment box not found' };
    trigger.click();
    trigger.focus();
    await sleep(jitter(500));
    await typeText(trigger, commentText);
    await sleep(jitter(400));
    const postBtn = document.querySelector('[data-e2e="comment-post"], button[data-e2e*="post"], div[data-e2e="comment-submit"]');
    if (postBtn) {
      postBtn.click();
    } else {
      trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
    }
    await sleep(jitter(1500));
    return { success: true };
  }

  try {
    if (platform === 'facebook')       return postFacebook();
    if (platform === 'instagram')      return postInstagram();
    if (platform === 'linkedin')       return postLinkedIn();
    if (platform === 'reddit')         return postReddit();
    if (platform === 'whatsapp')       return postWhatsApp();
    if (platform === 'telegram')       return postTelegram();
    if (platform === 'tiktok')         return postTikTok();
    if (platform === 'google_business') return postGoogleReply();
    return postFacebook();
  } catch (err) {
    return { success: false, error: err.message };
  }
}

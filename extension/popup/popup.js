const $ = id => document.getElementById(id);

const PLATFORM_LABELS = {
  facebook: '📘 Facebook',
  linkedin: '💼 LinkedIn',
  reddit:   '🟠 Reddit',
};

function showMsg(elId, text, type = 'success') {
  const el = $(elId);
  el.textContent = text;
  el.className   = `msg ${type}`;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 3500);
}

function renderKeywords(keywords) {
  const list = $('kw-list');
  $('kw-count').textContent = keywords.length;
  if (!keywords.length) {
    list.innerHTML = '<span class="empty-kw">No keywords yet — add them in Zilo CRM → Action Mode → Social Engagement</span>';
    return;
  }
  list.innerHTML = keywords.map(kw => `<span class="kw-chip">${kw}</span>`).join('');
}

function renderPlatforms(platforms) {
  const el     = $('platforms-display');
  const active = (platforms || []).length ? platforms : ['facebook', 'linkedin', 'reddit'];
  el.innerHTML = active
    .map(p => `<span class="platform-badge">${PLATFORM_LABELS[p] || p}</span>`)
    .join('');
}

function renderGroups(groups) {
  const list = $('group-list');
  $('group-count').textContent = groups.length;

  if (!groups.length) {
    list.innerHTML = '<span class="empty-kw">No groups yet — click Discover or paste a URL below</span>';
    return;
  }

  list.innerHTML = groups.map(g => {
    const name = g.name || g.url || g;
    const url  = g.url  || g;
    return `<div class="group-item">
      <span class="group-name" title="${url}">${name}</span>
      <button class="remove-group" data-url="${url}">✕</button>
    </div>`;
  }).join('');

  list.querySelectorAll('.remove-group').forEach(btn => {
    btn.addEventListener('click', () => {
      chrome.runtime.sendMessage({ type: 'REMOVE_GROUP', url: btn.dataset.url }, res => {
        if (res?.groups) renderGroups(res.groups);
      });
    });
  });
}

function renderLastScan(lastScanTime) {
  const el = $('scan-status');
  if (!lastScanTime) { el.textContent = 'Not scanned yet'; return; }
  const diff = Date.now() - new Date(lastScanTime).getTime();
  const mins = Math.floor(diff / 60_000);
  const hrs  = Math.floor(mins / 60);
  if (hrs > 0)       el.textContent = `Last scan: ${hrs}h ago`;
  else if (mins > 0) el.textContent = `Last scan: ${mins}m ago`;
  else               el.textContent = 'Last scan: just now';
}

function showConnected(apiUrl, keywords, platforms) {
  $('setup-view').classList.remove('active');
  $('connected-view').classList.add('active');
  $('api-url-display').textContent = apiUrl.replace(/^https?:\/\//, '').replace(/\/api$/, '');
  renderKeywords(keywords || []);
  renderPlatforms(platforms || []);
}

function showSetup(apiUrl = '') {
  $('connected-view').classList.remove('active');
  $('setup-view').classList.add('active');
  if (apiUrl) $('api-url').value = apiUrl;
}

// ── Init ─────────────────────────────────────────────────────────────────────

chrome.storage.sync.get(['ziloToken', 'ziloApiUrl', 'keywords', 'platforms'], result => {
  if (result.ziloToken) {
    showConnected(result.ziloApiUrl || '', result.keywords || [], result.platforms || []);
    // Load groups + last scan time
    chrome.runtime.sendMessage({ type: 'GET_GROUPS' }, res => {
      renderGroups(res?.groups || []);
      renderLastScan(res?.lastScanTime || null);
    });
  } else {
    showSetup(result.ziloApiUrl || '');
  }
});

// ── Connect ───────────────────────────────────────────────────────────────────

$('connect-btn').addEventListener('click', async () => {
  const token = $('api-token').value.trim();
  let apiUrl  = $('api-url').value.trim().replace(/\/$/, '');
  if (!apiUrl) apiUrl = 'http://localhost:8000/api';
  if (!token) { showMsg('setup-msg', 'Paste your token first', 'error'); return; }

  $('connect-btn').disabled    = true;
  $('connect-btn').textContent = 'Connecting…';

  try {
    const res = await fetch(`${apiUrl}/action-mode/social/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`Auth failed (${res.status})`);
    const data = await res.json();

    await chrome.storage.sync.set({
      ziloToken:  token,
      ziloApiUrl: apiUrl,
      keywords:   data.keywords || [],
      platforms:  data.platforms || ['facebook'],
    });

    showConnected(apiUrl, data.keywords || [], data.platforms || []);
    chrome.runtime.sendMessage({ type: 'GET_GROUPS' }, res => {
      renderGroups(res?.groups || []);
      renderLastScan(res?.lastScanTime || null);
    });
  } catch (err) {
    showMsg('setup-msg', err.message, 'error');
  } finally {
    $('connect-btn').disabled    = false;
    $('connect-btn').textContent = 'Connect to Zilo CRM';
  }
});

// ── Sync keywords ─────────────────────────────────────────────────────────────

$('sync-btn').addEventListener('click', () => {
  $('sync-btn').disabled    = true;
  $('sync-btn').textContent = 'Syncing…';

  chrome.runtime.sendMessage({ type: 'SYNC_KEYWORDS' }, response => {
    $('sync-btn').disabled    = false;
    $('sync-btn').textContent = '↻ Sync keywords from CRM';

    if (response?.status === 'synced') {
      chrome.storage.sync.get(['keywords', 'platforms'], result => {
        renderKeywords(result.keywords || []);
        renderPlatforms(result.platforms || []);
        showMsg('sync-msg', `✓ Synced ${response.count} keyword${response.count !== 1 ? 's' : ''}`, 'success');
      });
    } else {
      showMsg('sync-msg', response?.message || 'Sync failed', 'error');
    }
  });
});

// ── Groups: add manually ──────────────────────────────────────────────────────

$('add-group-btn').addEventListener('click', () => {
  let url = $('group-url-input').value.trim();
  if (!url) return;

  if (!url.startsWith('http')) url = 'https://' + url;
  try { new URL(url); } catch { showMsg('groups-msg', 'Invalid URL', 'error'); return; }

  // Extract a readable name from the URL
  const match = url.match(/facebook\.com\/groups\/([^/?#]+)/);
  const name  = match
    ? match[1].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
    : url;

  chrome.runtime.sendMessage({ type: 'ADD_GROUP', url, name }, res => {
    if (res?.status === 'exists') {
      showMsg('groups-msg', 'Group already added', 'error');
    } else if (res?.groups) {
      renderGroups(res.groups);
      $('group-url-input').value = '';
      showMsg('groups-msg', `✓ "${name}" added`, 'success');
    }
  });
});

// Allow Enter key in the URL input
$('group-url-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') $('add-group-btn').click();
});

// ── Groups: discover ──────────────────────────────────────────────────────────

$('discover-btn').addEventListener('click', () => {
  $('discover-btn').textContent = '⏳ Searching…';
  $('discover-btn').disabled    = true;
  $('discover-results').style.display = 'none';

  chrome.runtime.sendMessage({ type: 'DISCOVER_GROUPS' }, res => {
    $('discover-btn').textContent = '🔍 Discover';
    $('discover-btn').disabled    = false;

    if (!res?.groups?.length) {
      showMsg('groups-msg', res?.message || 'No groups found — try adding one manually', 'error');
      return;
    }

    const listEl = $('discover-list');
    listEl.innerHTML = res.groups.map(g =>
      `<div class="discover-item">
        <span class="discover-name" title="${g.url}">${g.name}</span>
        <button class="add-discovered"
          data-url="${g.url}"
          data-name="${g.name.replace(/"/g, '&quot;')}">+ Add</button>
      </div>`
    ).join('');

    listEl.querySelectorAll('.add-discovered').forEach(btn => {
      btn.addEventListener('click', () => {
        const url  = btn.dataset.url;
        const name = btn.dataset.name;
        chrome.runtime.sendMessage({ type: 'ADD_GROUP', url, name }, res => {
          if (res?.groups) {
            renderGroups(res.groups);
            btn.textContent = '✓ Added';
            btn.disabled    = true;
          }
        });
      });
    });

    $('discover-results').style.display = 'block';
  });
});

// ── Groups: scan now ──────────────────────────────────────────────────────────

$('scan-now-btn').addEventListener('click', () => {
  $('scan-now-btn').disabled    = true;
  $('scan-now-btn').textContent = '⏳ Opening groups…';

  chrome.runtime.sendMessage({ type: 'SCAN_NOW' }, res => {
    if (res?.status === 'no_groups') {
      showMsg('groups-msg', 'Add groups to scan first', 'error');
      $('scan-now-btn').disabled    = false;
      $('scan-now-btn').textContent = '⚡ Scan Groups Now';
    } else if (res?.status === 'not_connected') {
      showMsg('groups-msg', 'Not connected to CRM', 'error');
      $('scan-now-btn').disabled    = false;
      $('scan-now-btn').textContent = '⚡ Scan Groups Now';
    } else if (res?.status === 'scanning') {
      $('scan-status').textContent = `Scanning ${res.count} group${res.count !== 1 ? 's' : ''} in background…`;
      showMsg('groups-msg', `✓ Scanning ${res.count} group${res.count !== 1 ? 's' : ''} — check your CRM queue shortly`, 'success');
      setTimeout(() => {
        $('scan-now-btn').disabled    = false;
        $('scan-now-btn').textContent = '⚡ Scan Groups Now';
        renderLastScan(new Date().toISOString());
      }, 4000);
    } else {
      $('scan-now-btn').disabled    = false;
      $('scan-now-btn').textContent = '⚡ Scan Groups Now';
    }
  });
});

// ── Auto-post toggle ──────────────────────────────────────────────────────────

function renderAutoPostToggle(enabled) {
  const toggle = $('auto-post-toggle');
  const knob   = $('auto-post-knob');
  toggle.style.background = enabled ? '#10b981' : '#e2e8f0';
  knob.style.left         = enabled ? '18px' : '2px';
}

chrome.storage.sync.get(['autoPostEnabled'], result => {
  renderAutoPostToggle(result.autoPostEnabled !== false);
});

$('auto-post-row').addEventListener('click', () => {
  chrome.storage.sync.get(['autoPostEnabled'], result => {
    const next = result.autoPostEnabled === false;
    chrome.storage.sync.set({ autoPostEnabled: next });
    renderAutoPostToggle(next);
  });
});

// ── Disconnect ────────────────────────────────────────────────────────────────

$('disconnect-btn').addEventListener('click', () => {
  chrome.storage.sync.remove(['ziloToken', 'keywords', 'platforms'], () => {
    chrome.storage.sync.get(['ziloApiUrl'], result => showSetup(result.ziloApiUrl || ''));
  });
});

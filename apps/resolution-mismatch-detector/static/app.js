// --- State ---
let isRunning = false;
let pollTimer = null;
let logCursor = 0;
let currentMode = null;
let oddsFormat = localStorage.getItem('oddsFormat') || 'pct';

// --- Odds ---
function fmtPrice(prob) {
  if (prob == null || isNaN(prob)) return '--';
  prob = parseFloat(prob);
  if (oddsFormat === 'american') {
    if (prob <= 0 || prob >= 1) return '--';
    return prob >= 0.5
      ? String(Math.round(-(prob / (1 - prob)) * 100))
      : '+' + Math.round(((1 - prob) / prob) * 100);
  }
  if (oddsFormat === 'decimal') {
    return prob <= 0 ? '--' : (1 / prob).toFixed(2);
  }
  return `${(prob * 100).toFixed(0)}%`;
}

// --- DOM ---
const logPanel = document.getElementById('logPanel');
const statusText = document.getElementById('statusText');

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

// --- Log ---
function addLog(message, level = 'info') {
  const entry = document.createElement('div');
  entry.className = `log-entry ${level}`;
  entry.innerHTML = `<span class="time">${new Date().toLocaleTimeString()}</span>${escapeHtml(message)}`;
  logPanel.appendChild(entry);
  logPanel.scrollTop = logPanel.scrollHeight;
}

// --- Progress strip ---
function showProgress(mode, phase, pct) {
  const strip = document.getElementById('progressStrip');
  strip.style.display = 'block';
  document.getElementById('psMode').textContent = mode;
  document.getElementById('psPhase').textContent = phase || '';
  document.getElementById('psPct').textContent = `${pct}%`;
  document.getElementById('psFill').style.width = `${pct}%`;
}

function hideProgress() {
  document.getElementById('progressStrip').style.display = 'none';
}

// --- Polling ---
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(pollProgress, 1000);
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function pollProgress() {
  fetch(`/api/progress?since=${logCursor}`)
    .then(r => r.json())
    .then(data => {
      for (const log of data.logs) addLog(log.message, log.level);
      logCursor = data.log_cursor;

      if (data.running) {
        showProgress(data.mode, data.phase, data.percent);
      }

      if (data.done) {
        stopPolling();
        onDone(data.summary);
      }
    })
    .catch(() => {});
}

// --- Run a mode ---
function runMode(mode) {
  if (isRunning) return;
  isRunning = true;
  currentMode = mode;
  logCursor = 0;
  logPanel.innerHTML = '';

  document.querySelectorAll('.action-btn').forEach(b => b.disabled = true);
  showProgress(mode, 'Starting...', 0);

  fetch(`/api/run/${mode}`, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        addLog(data.error, 'error');
        onDone({ error: data.error });
      } else {
        startPolling();
      }
    })
    .catch(err => {
      addLog(`Request failed: ${err}`, 'error');
      onDone({ error: String(err) });
    });
}

function onDone(summary) {
  isRunning = false;
  stopPolling();
  document.querySelectorAll('.action-btn').forEach(b => b.disabled = false);

  if (summary.error) {
    addLog(`Error: ${summary.error}`, 'error');
    showProgress(currentMode, 'Error', 100);
  } else {
    addLog('Done.', 'success');
    const parts = [];
    if (summary.markets_cached) parts.push(`${summary.markets_cached} cached`);
    if (summary.new_markets) parts.push(`${summary.new_markets} new`);
    if (summary.markets_analyzed) parts.push(`${summary.markets_analyzed} analyzed`);
    if (summary.mismatches_found) parts.push(`${summary.mismatches_found} mismatches`);
    if (summary.rule_changes) parts.push(`${summary.rule_changes} rule changes`);
    if (summary.unanalyzed) parts.push(`${summary.unanalyzed} unanalyzed`);
    if (summary.calls) parts.push(`${summary.calls} Claude calls`);
    if (summary.note) parts.push(summary.note);
    if (parts.length) addLog(parts.join(' | '), 'success');
    showProgress(currentMode, 'Complete', 100);
  }

  // Hide after 5 seconds
  setTimeout(hideProgress, 5000);

  loadResults();
  loadStatus();
}

// --- Cancel ---
document.getElementById('psCancel').addEventListener('click', () => {
  fetch('/api/cancel', { method: 'POST' }).then(r => r.json()).then(() => {
    addLog('Cancelling...', 'warn');
  });
});

// --- Action buttons ---
document.querySelectorAll('.action-btn').forEach(btn => {
  btn.addEventListener('click', () => runMode(btn.dataset.mode));
});

// --- Status ---
function loadStatus() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      const c = data.cache || {};
      const el = document.getElementById('cacheInfo');
      if (c.total_markets > 0) {
        const age = c.last_fetched ? timeAgo(c.last_fetched) : 'never';
        el.innerHTML = `
          <span class="cache-count">${c.polymarket}</span> Poly /
          <span class="cache-count">${c.kalshi}</span> Kalshi cached &mdash;
          <span class="cache-count">${c.analyzed}</span> analyzed,
          <span class="${c.unanalyzed > 0 ? 'cache-stale' : 'cache-fresh'}">${c.unanalyzed} unanalyzed</span>
          &mdash; fetched ${age}
        `;
      } else {
        el.textContent = 'No data cached. Fetch Polymarket or Kalshi to start.';
      }
    })
    .catch(() => {});
}

function timeAgo(isoStr) {
  const d = new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z'));
  const mins = Math.floor((new Date() - d) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// --- Tabs ---
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
    if (tab.dataset.tab === 'results') loadResults();
    if (tab.dataset.tab === 'report') loadReport();
    if (tab.dataset.tab === 'markets') loadMarkets();
  });
});

// --- Odds toggle ---
document.querySelectorAll('.otog').forEach(btn => {
  if (btn.dataset.fmt === oddsFormat) {
    document.querySelectorAll('.otog').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }
  btn.addEventListener('click', () => {
    document.querySelectorAll('.otog').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    oddsFormat = btn.dataset.fmt;
    localStorage.setItem('oddsFormat', oddsFormat);
    renderResults();
    loadMarkets();
  });
});


// ===========================================
// Mismatches
// ===========================================
let resultsData = null;
let resultsSevFilter = 'all';

function loadResults() {
  fetch('/api/results').then(r => r.json()).then(data => {
    resultsData = data;
    renderResults();
  }).catch(() => {});
}

function renderResults() {
  if (!resultsData) return;
  const container = document.getElementById('resultsContent');
  const all = [
    ...resultsData.high.map(a => ({...a, _sev: 'high'})),
    ...resultsData.medium.map(a => ({...a, _sev: 'medium'})),
    ...resultsData.low.map(a => ({...a, _sev: 'low'})),
  ];
  const filtered = resultsSevFilter === 'all' ? all : all.filter(a => a._sev === resultsSevFilter);
  filtered.sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));

  const countEl = document.getElementById('resultsCount');
  if (countEl) countEl.textContent = `${filtered.length} mismatches (${resultsData.high.length}H / ${resultsData.medium.length}M / ${resultsData.low.length}L)`;

  if (!filtered.length) {
    container.innerHTML = '<p class="muted">No mismatches found. Run "Analyze" to scan cached markets.</p>';
    return;
  }
  container.innerHTML = filtered.map(a => {
    const price = fmtPrice(a.market_price);
    const vol = a.market_volume ? `$${Number(a.market_volume).toLocaleString(undefined, {maximumFractionDigits:0})}` : '';
    const cats = a.mismatch_categories || '[]';
    const rules = a.resolution_rules || '';
    const rp = rules.length > 300 ? rules.substring(0, 300) + '...' : rules;
    return `
      <div class="result-card ${a._sev}">
        <div class="title">${escapeHtml(a.market_title)}</div>
        <div class="meta">
          <span class="badge ${a._sev}">${a._sev}</span>
          <span>${escapeHtml(a.market_platform)}</span>
          <span>Price: ${price}</span>
          ${vol ? `<span>${vol}</span>` : ''}
          <span>Priority: ${(a.priority_score || 0).toFixed(2)}</span>
          ${a.market_end_date ? `<span>Ends: ${a.market_end_date.split('T')[0]}</span>` : ''}
        </div>
        <div class="detail"><strong>Retail assumes:</strong> ${escapeHtml(a.retail_assumption || 'N/A')}</div>
        <div class="detail"><strong>Rules say:</strong> ${escapeHtml(a.actual_resolution || 'N/A')}</div>
        <div class="detail"><strong>Categories:</strong> ${escapeHtml(cats)}</div>
        ${rp ? `<div class="rules-preview">${escapeHtml(rp)}</div>` : ''}
      </div>`;
  }).join('');
}

document.querySelectorAll('.rfilt').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.rfilt').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    resultsSevFilter = btn.dataset.sev;
    renderResults();
  });
});


// ===========================================
// Markets Explorer
// ===========================================
let marketsState = { platform: '', query: '', sort: 'volume', offset: 0, limit: 50 };

function loadMarkets() {
  const { platform, query, sort, offset, limit } = marketsState;
  const params = new URLSearchParams({ sort, limit, offset });
  if (platform) params.set('platform', platform);
  if (query) params.set('q', query);

  fetch(`/api/markets?${params}`).then(r => r.json()).then(data => {
    renderMarketsList(data.markets);
    document.getElementById('marketsMeta').textContent =
      `Showing ${data.offset + 1}-${Math.min(data.offset + data.markets.length, data.total)} of ${data.total.toLocaleString()}`;
    renderPager(data);
  }).catch(() => {});
}

function renderMarketsList(markets) {
  const el = document.getElementById('marketsList');
  if (!markets.length) {
    el.innerHTML = '<p class="muted" style="padding:20px">No markets found.</p>';
    return;
  }
  el.innerHTML = markets.map(m => {
    const price = fmtPrice(m.current_yes_price);
    const vol = m.volume ? `$${Number(m.volume).toLocaleString(undefined,{maximumFractionDigits:0})}` : '--';
    let status = '';
    if (m.mismatch_severity === 'high') status = '<span style="color:var(--red)">&#9679;</span>';
    else if (m.mismatch_severity === 'medium') status = '<span style="color:var(--yellow)">&#9679;</span>';
    else if (m.analyzed) status = '<span style="color:var(--green)">&#10003;</span>';
    return `
      <div class="market-row" data-id="${escapeHtml(m.id)}">
        <span class="m-platform ${m.platform}">${m.platform === 'polymarket' ? 'POLY' : 'KAL'}</span>
        <span class="m-title">${escapeHtml(m.title)}</span>
        <span class="m-price">${price}</span>
        <span class="m-vol">${vol}</span>
        <span class="m-status">${status}</span>
      </div>`;
  }).join('');
  el.querySelectorAll('.market-row').forEach(row => {
    row.addEventListener('click', () => openMarketDetail(row.dataset.id));
  });
}

function renderPager(data) {
  const el = document.getElementById('marketsPager');
  const page = Math.floor(data.offset / data.limit) + 1;
  const totalPages = Math.ceil(data.total / data.limit);
  el.innerHTML = `
    <button class="pager-btn" id="pgPrev" ${data.offset > 0 ? '' : 'disabled'}>Prev</button>
    <span class="pager-info">${page} / ${totalPages}</span>
    <button class="pager-btn" id="pgNext" ${data.offset + data.limit < data.total ? '' : 'disabled'}>Next</button>`;
  document.getElementById('pgPrev')?.addEventListener('click', () => {
    marketsState.offset = Math.max(0, marketsState.offset - marketsState.limit);
    loadMarkets();
  });
  document.getElementById('pgNext')?.addEventListener('click', () => {
    marketsState.offset += marketsState.limit;
    loadMarkets();
  });
}

function openMarketDetail(marketId) {
  fetch(`/api/markets/${encodeURIComponent(marketId)}`).then(r => r.json()).then(data => {
    const m = data.market;
    const a = data.analysis;
    const p = data.position;
    const price = fmtPrice(m.current_yes_price);
    const vol = m.volume ? `$${Number(m.volume).toLocaleString()}` : 'N/A';

    let analysisHtml = '<p class="muted">Not analyzed yet</p>';
    if (a) {
      analysisHtml = `<div class="detail-analysis">
        <div class="da-row"><span class="da-label">Mismatch</span><span>${a.mismatch_found ? 'YES' : 'No'}</span></div>
        <div class="da-row"><span class="da-label">Severity</span><span class="badge ${a.severity}">${a.severity}</span></div>
        <div class="da-row"><span class="da-label">Categories</span><span>${escapeHtml(a.mismatch_categories || '[]')}</span></div>
        ${a.retail_assumption ? `<div class="da-row"><span class="da-label">Retail assumes</span><span>${escapeHtml(a.retail_assumption)}</span></div>` : ''}
        ${a.actual_resolution ? `<div class="da-row"><span class="da-label">Rules say</span><span>${escapeHtml(a.actual_resolution)}</span></div>` : ''}
        <div class="da-row"><span class="da-label">Priority</span><span>${(a.priority_score || 0).toFixed(2)}</span></div>
      </div>`;
    }

    document.getElementById('marketDetailContent').innerHTML = `
      <div class="detail-title">${escapeHtml(m.title)}</div>
      <div class="detail-meta">
        <span class="badge" style="background:${m.platform === 'polymarket' ? '#8b5cf622' : '#06b6d422'};color:${m.platform === 'polymarket' ? '#8b5cf6' : '#06b6d4'}">${m.platform}</span>
        <span>Price: ${price}</span>
        <span>Volume: ${vol}</span>
        <span>Ends: ${m.end_date || 'N/A'}</span>
      </div>
      <div class="detail-section"><h3>Resolution Rules</h3><div class="content">${escapeHtml(m.resolution_rules || 'No rules')}</div></div>
      <div class="detail-section"><h3>Analysis</h3>${analysisHtml}</div>
      ${p ? `<div class="detail-section"><h3>Position</h3><div class="detail-analysis">
        <div class="da-row"><span class="da-label">Side</span><span>${p.side}</span></div>
        <div class="da-row"><span class="da-label">Avg Price</span><span>${p.avg_price}</span></div>
        <div class="da-row"><span class="da-label">Qty</span><span>${p.quantity}</span></div>
      </div></div>` : ''}`;
    document.getElementById('marketDetailOverlay').style.display = 'flex';
  });
}

// Market search (debounced)
let searchTimer = null;
document.getElementById('marketSearch').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    marketsState.query = e.target.value;
    marketsState.offset = 0;
    loadMarkets();
  }, 300);
});

document.querySelectorAll('.ptab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ptab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    marketsState.platform = btn.dataset.platform;
    marketsState.offset = 0;
    loadMarkets();
  });
});

document.getElementById('marketSort').addEventListener('change', (e) => {
  marketsState.sort = e.target.value;
  marketsState.offset = 0;
  loadMarkets();
});

document.getElementById('detailClose').addEventListener('click', () => {
  document.getElementById('marketDetailOverlay').style.display = 'none';
});
document.getElementById('marketDetailOverlay').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) e.currentTarget.style.display = 'none';
});


// ===========================================
// Report
// ===========================================
function loadReport() {
  fetch('/api/report/latest').then(r => r.json()).then(data => {
    document.getElementById('reportContent').textContent = data.content;
  }).catch(() => {});
}


// --- Init ---
loadStatus();

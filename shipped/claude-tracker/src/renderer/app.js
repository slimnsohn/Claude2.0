// =========================================================================
// Claude Tracker — Renderer (hardened)
// =========================================================================

const COMPACT = { w: 540, h: 170 };
const EXPANDED = { w: 620, h: 560 };

let isExpanded = false;
let pollTimer = null;
let countdownTimer = null;
let chart = null;
let currentRange = 24;
let latestData = null;
let settings = { alwaysOnTop: true, pollMinutes: 5, warnPct: 75, dangerPct: 90 };

const $ = (id) => document.getElementById(id);
const el = {
  viewLogin:      $('viewLogin'),
  viewCompact:    $('viewCompact'),
  viewDashboard:  $('viewDashboard'),
  viewSettings:   $('viewSettings'),
  statusDot:      $('statusDot'),
  barSession:     $('barSession'),
  pctSession:     $('pctSession'),
  timerSession:   $('timerSession'),
  barWeekly:      $('barWeekly'),
  pctWeekly:      $('pctWeekly'),
  timerWeekly:    $('timerWeekly'),
  dashSessionPct:   $('dashSessionPct'),
  dashSessionTimer: $('dashSessionTimer'),
  dashWeeklyPct:    $('dashWeeklyPct'),
  dashWeeklyTimer:  $('dashWeeklyTimer'),
  dashExtraPct:     $('dashExtraPct'),
  dashExtraSub:     $('dashExtraSub'),
  dashPoints:       $('dashPoints'),
  dashSpan:         $('dashSpan'),
  btnRefresh:     $('btnRefresh'),
  btnExpand:      $('btnExpand'),
  btnSettings:    $('btnSettings'),
  btnMin:         $('btnMin'),
  btnClose:       $('btnClose'),
  btnLoginAuto:   $('btnLoginAuto'),
  btnSettingsDone: $('btnSettingsDone'),
  btnLogout:      $('btnLogout'),
  btnClearHistory: $('btnClearHistory'),
  resizeHandle:   $('resizeHandle'),
};

// =========================================================================
// Init
// =========================================================================
async function init() {
  settings = await window.api.getSettings();
  bindEvents();
  initResizeHandle();

  const creds = await window.api.getCredentials();
  if (creds.hasSession && creds.hasOrg) {
    showView('compact');
    fetchAndUpdate();
    startPolling();
  } else {
    showView('login');
  }

  window.api.onRefresh(() => fetchAndUpdate());
  window.api.onLoggedOut(() => {
    stopPolling();
    showView('login');
    setStatus('off');
  });
}

// =========================================================================
// Views
// =========================================================================
function showView(name) {
  el.viewLogin.classList.toggle('hidden', name !== 'login');
  el.viewCompact.classList.toggle('hidden', name !== 'compact');
  el.viewDashboard.classList.toggle('hidden', name !== 'dashboard');

  if (name === 'compact') {
    isExpanded = false;
    window.api.resize(COMPACT);
    el.btnExpand.textContent = '◳';
  } else if (name === 'dashboard') {
    isExpanded = true;
    window.api.resize(EXPANDED);
    el.btnExpand.textContent = '◱';
    renderChart();
  } else if (name === 'login') {
    isExpanded = false;
    window.api.resize({ w: COMPACT.w, h: 150 });
  }
}

function setStatus(state) {
  // Only allow known state values
  const allowed = ['ok', 'warn', 'off'];
  const s = allowed.includes(state) ? state : 'off';
  el.statusDot.className = `dot dot-${s}`;
  el.statusDot.title = s === 'ok' ? 'Connected' : s === 'warn' ? 'High usage' : 'Disconnected';
}

// =========================================================================
// Font scaling — scale all text proportionally when window is resized
// =========================================================================
const BASE_WIDTH = 540;
const BASE_FONT = 12;

function scaleFont(width) {
  const scale = Math.max(0.75, width / BASE_WIDTH);
  document.documentElement.style.fontSize = (BASE_FONT * scale) + 'px';
}

// =========================================================================
// Resize Handle — drag bottom-right corner to resize window
// =========================================================================
function initResizeHandle() {
  const handle = el.resizeHandle;
  if (!handle) return;

  let startX, startY, startW, startH;

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    e.stopPropagation();
    startX = e.screenX;
    startY = e.screenY;
    startW = window.outerWidth;
    startH = window.outerHeight;

    const onMouseMove = (e) => {
      const newW = Math.max(200, startW + (e.screenX - startX));
      const newH = Math.max(100, startH + (e.screenY - startY));
      window.api.resize({ w: newW, h: newH });
      scaleFont(newW);
    };

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });
}

// =========================================================================
// Events
// =========================================================================
function bindEvents() {
  el.btnMin.onclick = () => window.api.minimize();
  el.btnClose.onclick = () => window.api.closeApp();

  el.btnRefresh.onclick = () => {
    el.btnRefresh.style.opacity = '0.4';
    fetchAndUpdate().finally(() => { el.btnRefresh.style.opacity = '1'; });
  };

  el.btnExpand.onclick = () => {
    if (isExpanded) showView('compact');
    else showView('dashboard');
  };

  el.btnLoginAuto.onclick = async () => {
    el.btnLoginAuto.textContent = 'Waiting for login...';
    el.btnLoginAuto.disabled = true;
    try {
      // Single atomic call — login, validate, and save all happen in main process.
      // The session key NEVER enters the renderer.
      const res = await window.api.login();
      if (res.success) {
        showView('compact');
        fetchAndUpdate();
        startPolling();
        return;
      }
      el.btnLoginAuto.textContent = 'Try again';
    } catch { el.btnLoginAuto.textContent = 'Try again'; }
    el.btnLoginAuto.disabled = false;
  };

  el.btnSettings.onclick = () => {
    $('setAlwaysOnTop').checked = settings.alwaysOnTop;
    $('setPollMin').value = settings.pollMinutes;
    $('setWarn').value = settings.warnPct;
    $('setDanger').value = settings.dangerPct;
    el.viewSettings.classList.remove('hidden');
  };

  el.btnSettingsDone.onclick = async () => {
    settings.alwaysOnTop = $('setAlwaysOnTop').checked;
    settings.pollMinutes = Math.max(1, Math.min(60, parseInt($('setPollMin').value) || 5));
    settings.warnPct = Math.max(1, Math.min(99, parseInt($('setWarn').value) || 75));
    settings.dangerPct = Math.max(1, Math.min(99, parseInt($('setDanger').value) || 90));
    await window.api.saveSettings(settings);
    el.viewSettings.classList.add('hidden');
    stopPolling();
    startPolling();
  };

  el.btnLogout.onclick = async () => {
    await window.api.logout();
    stopPolling();
    el.viewSettings.classList.add('hidden');
    showView('login');
    setStatus('off');
  };

  el.btnClearHistory.onclick = async () => {
    await window.api.clearHistory();
    if (chart) renderChart();
  };

  document.querySelectorAll('.range-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const h = btn.dataset.hours;
      currentRange = h ? parseInt(h) : null;
      renderChart();
    };
  });
}

// =========================================================================
// Polling
// =========================================================================
function startPolling() {
  stopPolling();
  const ms = (settings.pollMinutes || 5) * 60 * 1000;
  pollTimer = setInterval(() => fetchAndUpdate(), ms);
  countdownTimer = setInterval(() => updateTimers(), 1000);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
}

// =========================================================================
// Fetch & update — data is already sanitized by main process
// =========================================================================
async function fetchAndUpdate() {
  try {
    const result = await window.api.fetchUsage();
    latestData = result;
    setStatus('ok');
    updateUI(result);
    if (isExpanded) renderChart();
  } catch (e) {
    console.error('Fetch error:', e);
    if (e.message === 'SessionExpired' || e.message === 'Not authenticated') {
      setStatus('off');
      showView('login');
      stopPolling();
    }
  }
}

// =========================================================================
// UI updates — all data pre-sanitized, all DOM via .textContent (no innerHTML)
// =========================================================================
function updateUI(data) {
  if (!data) return;

  const sessionPct = data.sessionPct;
  const sessionResets = data.sessionResetsAt;
  const weeklyPct = data.weeklyPct;
  const weeklyResets = data.weeklyResetsAt;
  const extraInfo = data.extraUsage;

  updateBar('Session', sessionPct, sessionResets);
  updateBar('Weekly', weeklyPct, weeklyResets);

  el.dashSessionPct.textContent = sessionPct != null ? `${Math.round(sessionPct)}%` : '—';
  el.dashSessionTimer.textContent = sessionResets ? `resets ${formatResetTime(sessionResets)}` : 'resets —';
  el.dashWeeklyPct.textContent = weeklyPct != null ? `${Math.round(weeklyPct)}%` : '—';
  el.dashWeeklyTimer.textContent = weeklyResets ? `resets ${formatResetTime(weeklyResets)}` : 'resets —';

  if (extraInfo && extraInfo.is_enabled) {
    el.dashExtraPct.textContent = `${Math.round(extraInfo.utilization || 0)}%`;
    const usedDollars = ((extraInfo.used_cents || 0) / 100).toFixed(2);
    const limitDollars = ((extraInfo.limit_cents || 0) / 100).toFixed(2);
    el.dashExtraSub.textContent = `$${usedDollars} / $${limitDollars}`;
  } else {
    el.dashExtraPct.textContent = extraInfo?.is_enabled === false ? 'OFF' : '—';
    el.dashExtraSub.textContent = extraInfo?.is_enabled === false ? 'not enabled' : '—';
  }

  const maxPct = Math.max(sessionPct || 0, weeklyPct || 0);
  if (maxPct >= settings.dangerPct) setStatus('off');
  else if (maxPct >= settings.warnPct) setStatus('warn');
  else setStatus('ok');

  checkAlerts(sessionPct, weeklyPct);
}

function updateBar(type, pct, resetsAt) {
  const bar = el[`bar${type}`];
  const pctEl = el[`pct${type}`];
  const timerEl = el[`timer${type}`];
  if (!bar || !pctEl || !timerEl) return;
  const fill = bar.querySelector('.bar-fill');

  if (pct == null) {
    fill.style.width = '0%';
    pctEl.textContent = '—';
    timerEl.textContent = '—';
    timerEl.dataset.resetsAt = '';
    return;
  }

  const clamped = Math.min(100, Math.max(0, pct));
  fill.style.width = `${clamped}%`;
  fill.className = 'bar-fill';
  if (pct >= settings.dangerPct) fill.classList.add('danger');
  else if (pct >= settings.warnPct) fill.classList.add('warn');

  pctEl.textContent = `${Math.round(pct)}%`;
  timerEl.textContent = resetsAt ? formatCountdown(resetsAt) : '—';
  timerEl.dataset.resetsAt = resetsAt || '';
}

// =========================================================================
// Timers
// =========================================================================
function updateTimers() {
  [el.timerSession, el.timerWeekly].forEach(t => {
    if (t && t.dataset.resetsAt) {
      t.textContent = formatCountdown(t.dataset.resetsAt);
    }
  });
}

function formatCountdown(isoStr) {
  const diff = new Date(isoStr) - Date.now();
  if (!Number.isFinite(diff) || diff <= 0) return 'resetting...';
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  if (h > 24) {
    const d = Math.floor(h / 24);
    return `${d}d ${h % 24}h`;
  }
  return `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
}

function formatResetTime(isoStr) {
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return '—';
  const diffH = (d - Date.now()) / 3600000;
  if (diffH < 24) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

// =========================================================================
// Alerts
// =========================================================================
let alertedSession = false;
let alertedWeekly = false;

function checkAlerts(sessionPct, weeklyPct) {
  if (sessionPct != null && sessionPct >= settings.dangerPct && !alertedSession) {
    alertedSession = true;
    window.api.notify('Claude Session Usage', `Session at ${Math.round(sessionPct)}% — approaching limit`);
  }
  if (weeklyPct != null && weeklyPct >= settings.dangerPct && !alertedWeekly) {
    alertedWeekly = true;
    window.api.notify('Claude Weekly Usage', `Weekly at ${Math.round(weeklyPct)}% — approaching limit`);
  }
  if (sessionPct != null && sessionPct < settings.warnPct) alertedSession = false;
  if (weeklyPct != null && weeklyPct < settings.warnPct) alertedWeekly = false;
}

// =========================================================================
// Chart
// =========================================================================
async function renderChart() {
  const history = await window.api.getHistory(currentRange ? { hours: currentRange } : {});

  el.dashPoints.textContent = String(history.length);
  if (history.length > 1) {
    const first = new Date(history[0].ts);
    const last = new Date(history[history.length - 1].ts);
    const spanH = (last - first) / 3600000;
    if (spanH > 48) el.dashSpan.textContent = `${Math.round(spanH / 24)} days`;
    else if (spanH > 1) el.dashSpan.textContent = `${Math.round(spanH)} hours`;
    else el.dashSpan.textContent = `${Math.round(spanH * 60)} min`;
  } else {
    el.dashSpan.textContent = 'collecting...';
  }

  const labels = history.map(h => new Date(h.ts));
  const sessionData = history.map(h => h.session);
  const weeklyData = history.map(h => h.weekly);

  const ctx = $('usageChart').getContext('2d');
  if (chart) chart.destroy();

  const g1 = ctx.createLinearGradient(0, 0, 0, 300);
  g1.addColorStop(0, 'rgba(124, 108, 255, 0.3)');
  g1.addColorStop(1, 'rgba(124, 108, 255, 0.02)');
  const g2 = ctx.createLinearGradient(0, 0, 0, 300);
  g2.addColorStop(0, 'rgba(62, 207, 207, 0.25)');
  g2.addColorStop(1, 'rgba(62, 207, 207, 0.02)');

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Session', data: sessionData, borderColor: '#7c6cff', backgroundColor: g1, borderWidth: 1.5, fill: true, tension: 0.3, pointRadius: 0, pointHitRadius: 6 },
        { label: 'Weekly', data: weeklyData, borderColor: '#3ecfcf', backgroundColor: g2, borderWidth: 1.5, fill: true, tension: 0.3, pointRadius: 0, pointHitRadius: 6 },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        legend: {
          display: true, position: 'top',
          labels: { color: '#5a6078', font: { family: "'JetBrains Mono'", size: 9 }, boxWidth: 12, boxHeight: 2, padding: 8 }
        },
        tooltip: {
          backgroundColor: '#141622', borderColor: '#1e2235', borderWidth: 1,
          titleFont: { family: "'JetBrains Mono'", size: 10 },
          bodyFont: { family: "'JetBrains Mono'", size: 10 },
          titleColor: '#5a6078', bodyColor: '#c8cdd8', padding: 8, displayColors: true,
          callbacks: {
            title: (items) => items.length ? new Date(items[0].parsed.x).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '',
            label: (item) => ` ${item.dataset.label}: ${item.parsed.y != null ? Math.round(item.parsed.y) + '%' : 'n/a'}`
          }
        }
      },
      scales: {
        x: {
          type: 'time',
          time: { displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' } },
          grid: { color: 'rgba(30,34,53,0.6)', drawBorder: false },
          ticks: { color: '#5a6078', font: { family: "'JetBrains Mono'", size: 9 }, maxTicksLimit: 8, maxRotation: 0 },
          border: { display: false }
        },
        y: {
          min: 0, max: 100,
          grid: { color: 'rgba(30,34,53,0.6)', drawBorder: false },
          ticks: { color: '#5a6078', font: { family: "'JetBrains Mono'", size: 9 }, callback: v => v + '%', stepSize: 25 },
          border: { display: false }
        }
      }
    }
  });
}

// =========================================================================
// Boot
// =========================================================================
init();

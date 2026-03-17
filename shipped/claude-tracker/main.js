const { app, BrowserWindow, ipcMain, Tray, Menu, session, shell, Notification, safeStorage } = require('electron');
const path = require('path');
const os = require('os');
const Store = require('electron-store');
const crypto = require('crypto');

// ===========================================================================
// SECURITY CONFIGURATION
// ===========================================================================

// Strict UUID v4 pattern for org IDs
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Session keys start with 'sk-ant-sid' — reject anything else
const SESSION_KEY_RE = /^sk-ant-sid[0-9]{2}-[A-Za-z0-9_-]{20,200}$/;

// Only these origins may ever be loaded in ANY BrowserWindow
const ALLOWED_FETCH_ORIGINS = ['https://claude.ai'];
const ALLOWED_LOGIN_ORIGINS = [
  'https://claude.ai',
  'https://accounts.google.com',
  'https://appleid.apple.com',
  'https://github.com',
  'https://login.microsoftonline.com',
];

// Only these domains may be opened via shell.openExternal
const ALLOWED_EXTERNAL_DOMAINS = ['claude.ai', 'github.com'];

// Max string lengths for IPC inputs
const MAX_SESSION_KEY_LEN = 300;
const MAX_ORG_ID_LEN = 50;
const MAX_NOTIFICATION_LEN = 200;

// Dimensions
const COMPACT = { w: 540, h: 170 };
const EXPANDED = { w: 620, h: 560 };
const WIN_MIN = { w: 200, h: 100 };
const WIN_MAX = { w: 1200, h: 900 };

// History
const MAX_HISTORY = 8640;

// ===========================================================================
// STORAGE — no electron-store encryption (it uses deprecated crypto APIs).
// Session key is protected by safeStorage or manual AES-256-GCM fallback.
// ===========================================================================
const store = new Store();

// Random fallback key for when safeStorage (OS keychain) is unavailable.
// Generated once on first run and persisted. Only used for session key.
let _fallbackKey = store.get('_fk');
if (!_fallbackKey || typeof _fallbackKey !== 'string' || _fallbackKey.length !== 64) {
  _fallbackKey = crypto.randomBytes(32).toString('hex');  // 64 hex chars = 256 bits
  store.set('_fk', _fallbackKey);
  if (!safeStorage.isEncryptionAvailable()) {
    console.warn('[tracker] safeStorage unavailable — session key protection is limited');
  }
}
const FALLBACK_KEY_BUF = Buffer.from(_fallbackKey, 'hex');

function fallbackEncrypt(plaintext) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', FALLBACK_KEY_BUF, iv);
  const enc = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, enc]).toString('base64');
}

function fallbackDecrypt(b64) {
  const buf = Buffer.from(b64, 'base64');
  if (buf.length < 28) return null;  // 12 iv + 16 tag minimum
  const iv = buf.subarray(0, 12);
  const tag = buf.subarray(12, 28);
  const enc = buf.subarray(28);
  const decipher = crypto.createDecipheriv('aes-256-gcm', FALLBACK_KEY_BUF, iv);
  decipher.setAuthTag(tag);
  return decipher.update(enc, undefined, 'utf8') + decipher.final('utf8');
}

const CHROME_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

// Debug only when running from source — never in packaged builds
const DEBUG = !app.isPackaged && (process.env.DEBUG_LOG === '1' || process.argv.includes('--debug'));
function log(...a) { if (DEBUG) console.log('[tracker]', ...a); }

let mainWindow = null;
let tray = null;

// ===========================================================================
// SESSION KEY — OS keychain preferred
// ===========================================================================
function saveSessionKey(key) {
  if (typeof key !== 'string' || key.length > MAX_SESSION_KEY_LEN) return;
  if (safeStorage.isEncryptionAvailable()) {
    const encrypted = safeStorage.encryptString(key);
    store.set('sessionKeyEnc', encrypted.toString('base64'));
    store.delete('sessionKeyFb');
  } else {
    store.set('sessionKeyFb', fallbackEncrypt(key));
    store.delete('sessionKeyEnc');
  }
}

function loadSessionKey() {
  // Prefer safeStorage (OS keychain)
  const enc = store.get('sessionKeyEnc');
  if (enc && safeStorage.isEncryptionAvailable()) {
    try { return safeStorage.decryptString(Buffer.from(enc, 'base64')); } catch { /* fall through */ }
  }
  // Fallback: AES-256-GCM
  const fb = store.get('sessionKeyFb');
  if (fb) {
    try { return fallbackDecrypt(fb); } catch { /* corrupted */ }
  }
  return null;
}

function clearSessionKey() {
  store.delete('sessionKeyEnc');
  store.delete('sessionKeyFb');
}

// ===========================================================================
// COOKIE MANAGEMENT
// ===========================================================================
async function setSessionCookie(key) {
  if (typeof key !== 'string' || !key) return;
  await session.defaultSession.cookies.set({
    url: 'https://claude.ai', name: 'sessionKey', value: key,
    domain: '.claude.ai', path: '/', secure: true, httpOnly: true
  });
}

async function clearAllClaudeCookies() {
  const cookies = await session.defaultSession.cookies.get({ url: 'https://claude.ai' });
  for (const c of cookies) await session.defaultSession.cookies.remove('https://claude.ai', c.name);
  await session.defaultSession.clearStorageData({
    storages: ['localstorage', 'sessionstorage', 'cachestorage', 'indexeddb'],
    origin: 'https://claude.ai'
  });
}

// ===========================================================================
// VALIDATORS
// ===========================================================================
function isValidOrgId(id) {
  return typeof id === 'string' && UUID_RE.test(id) && id.length <= MAX_ORG_ID_LEN;
}

function isValidSessionKey(key) {
  return typeof key === 'string' && key.length > 10 && key.length <= MAX_SESSION_KEY_LEN && SESSION_KEY_RE.test(key);
}

function sanitizeString(s, maxLen) {
  if (typeof s !== 'string') return '';
  return s.slice(0, maxLen).replace(/[\x00-\x1f]/g, '');
}

function clampNumber(v, min, max, fallback) {
  const n = Number(v);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, Math.floor(n)));
}

// ===========================================================================
// FETCH VIA HIDDEN WINDOW (Cloudflare bypass)
// ===========================================================================
function fetchViaWindow(url, timeoutMs = 20000) {
  let parsed;
  try { parsed = new URL(url); } catch { return Promise.reject(new Error('Invalid URL')); }
  if (!ALLOWED_FETCH_ORIGINS.includes(parsed.origin)) {
    return Promise.reject(new Error('Blocked: origin not in allowlist'));
  }

  return new Promise((resolve, reject) => {
    const win = new BrowserWindow({
      width: 800, height: 600, show: false,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
        webgl: false,
        images: false,
        webviewTag: false,
        allowRunningInsecureContent: false,
        experimentalFeatures: false,
      }
    });

    win.webContents.on('will-navigate', (event) => event.preventDefault());
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));

    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) { settled = true; win.close(); reject(new Error('Timeout')); }
    }, timeoutMs);

    win.webContents.on('did-finish-load', async () => {
      if (settled) return;
      try {
        const body = await win.webContents.executeJavaScript(
          'document.body.innerText || document.body.textContent'
        );
        settled = true; clearTimeout(timer); win.close();

        if (!body || body.includes('Just a moment') || body.includes('Enable JavaScript')) {
          reject(new Error('CloudflareBlocked')); return;
        }
        if (body.length > 1024 * 1024) { reject(new Error('ResponseTooLarge')); return; }

        resolve(JSON.parse(body));
      } catch (e) {
        if (!settled) { settled = true; clearTimeout(timer); win.close(); reject(e); }
      }
    });

    win.webContents.on('did-fail-load', (ev, code) => {
      if (!settled) { settled = true; clearTimeout(timer); win.close(); reject(new Error(`LoadFailed: ${code}`)); }
    });

    win.loadURL(url);
  });
}

// ===========================================================================
// HISTORY
// ===========================================================================
function appendHistory(snapshot) {
  const ts = Number(snapshot.ts);
  if (!Number.isFinite(ts)) return;
  const clean = {
    ts,
    session: typeof snapshot.session === 'number' && Number.isFinite(snapshot.session) ? snapshot.session : null,
    weekly: typeof snapshot.weekly === 'number' && Number.isFinite(snapshot.weekly) ? snapshot.weekly : null,
  };
  const history = store.get('usageHistory', []);
  if (!Array.isArray(history)) { store.set('usageHistory', [clean]); return; }
  history.push(clean);
  while (history.length > MAX_HISTORY) history.shift();
  store.set('usageHistory', history);
}

// ===========================================================================
// WINDOW CREATION
// ===========================================================================
function createMainWindow() {
  const saved = store.get('windowPos');
  const opts = {
    width: COMPACT.w, height: COMPACT.h,
    frame: false, transparent: true, alwaysOnTop: true,
    resizable: true, skipTaskbar: false,
    minWidth: WIN_MIN.w, minHeight: WIN_MIN.h,
    maxWidth: WIN_MAX.w, maxHeight: WIN_MAX.h,
    ...(saved && Number.isFinite(saved.x) && Number.isFinite(saved.y) && { x: saved.x, y: saved.y }),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
      webviewTag: false,
      allowRunningInsecureContent: false,
      experimentalFeatures: false,
    }
  };

  mainWindow = new BrowserWindow(opts);

  // Lock main window to local file:// only
  mainWindow.webContents.on('will-navigate', (event, navUrl) => {
    if (!navUrl.startsWith('file://')) event.preventDefault();
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));

  mainWindow.loadFile('src/renderer/index.html');

  mainWindow.on('move', () => {
    if (!mainWindow) return;
    const b = mainWindow.getBounds();
    store.set('windowPos', { x: b.x, y: b.y });
  });
  mainWindow.on('closed', () => { mainWindow = null; });

  if (!app.isPackaged && process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
}

function createTray() {
  try {
    const iconFile = process.platform === 'darwin' ? 'tray-mac.png' : 'tray.png';
    const iconPath = path.join(__dirname, 'assets', iconFile);
    const fs = require('fs');
    tray = fs.existsSync(iconPath) ? new Tray(iconPath) : new Tray(require('electron').nativeImage.createEmpty());

    tray.setToolTip('Claude Tracker');
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: 'Show', click: () => { mainWindow ? mainWindow.show() : createMainWindow(); } },
      { label: 'Refresh', click: () => { mainWindow?.webContents.send('refresh'); } },
      { type: 'separator' },
      { label: 'Log Out', click: async () => {
        clearSessionKey(); store.delete('orgId');
        await clearAllClaudeCookies();
        mainWindow?.webContents.send('logged-out');
      }},
      { type: 'separator' },
      { label: 'Exit', click: () => app.quit() }
    ]));
    tray.on('click', () => { mainWindow?.isVisible() ? mainWindow.hide() : mainWindow?.show(); });
  } catch (e) { console.error('Tray error:', e); }
}

// ===========================================================================
// IPC HANDLERS
// ===========================================================================

ipcMain.handle('get-credentials', () => {
  const sk = loadSessionKey();
  // If session key exists in store but can't be decrypted, clear stale data
  if (!sk && (store.get('sessionKeyEnc') || store.get('sessionKeyFb'))) {
    log('Clearing undecryptable session key');
    clearSessionKey();
    store.delete('orgId');
  }
  return { hasSession: !!sk, hasOrg: !!store.get('orgId') };
});

ipcMain.handle('logout', async () => {
  clearSessionKey(); store.delete('orgId');
  await clearAllClaudeCookies();
  return true;
});

let loginInProgress = false;

ipcMain.handle('detect-session-key', async () => {
  // SECURITY: Prevent concurrent login windows
  if (loginInProgress) return { success: false, error: 'Login already in progress' };
  loginInProgress = true;

  try { await session.defaultSession.cookies.remove('https://claude.ai', 'sessionKey'); } catch {}

  return new Promise((resolve) => {
    // Wrap resolve to always reset the flag
    const done_resolve = (val) => { loginInProgress = false; resolve(val); };

    const loginWin = new BrowserWindow({
      width: 1000, height: 700, title: 'Log in to Claude',
      webPreferences: {
        nodeIntegration: false, contextIsolation: true, sandbox: true,
        webviewTag: false, allowRunningInsecureContent: false,
      }
    });

    loginWin.webContents.on('will-navigate', (event, navUrl) => {
      try {
        const p = new URL(navUrl);
        if (!ALLOWED_LOGIN_ORIGINS.some(o => p.origin === o)) { event.preventDefault(); }
      } catch { event.preventDefault(); }
    });
    // Deny all popups — OAuth redirects use navigation, not window.open
    loginWin.webContents.setWindowOpenHandler(({ url: pu }) => {
      // If a popup is requested to an allowed origin, navigate the login window instead
      try {
        if (ALLOWED_LOGIN_ORIGINS.some(o => new URL(pu).origin === o)) {
          loginWin.loadURL(pu);
        }
      } catch {}
      return { action: 'deny' };
    });

    const loginTimeout = setTimeout(() => { loginWin.close(); }, 5 * 60 * 1000);

    let done = false;
    const onCookie = async (ev, cookie, cause, removed) => {
      if (
        cookie.name === 'sessionKey' &&
        (cookie.domain === '.claude.ai' || cookie.domain === 'claude.ai') &&
        !removed && cookie.value && cookie.value.length <= MAX_SESSION_KEY_LEN
      ) {
        done = true; clearTimeout(loginTimeout);
        session.defaultSession.cookies.removeListener('changed', onCookie);
        loginWin.close();

        const capturedKey = cookie.value;

        // ---- SECURITY: Validate + save entirely in main process ----
        // The session key NEVER crosses the IPC bridge to the renderer.
        if (!isValidSessionKey(capturedKey)) {
          done_resolve({ success: false, error: 'Invalid key format' });
          return;
        }

        try {
          await setSessionCookie(capturedKey);
          const data = await fetchViaWindow('https://claude.ai/api/organizations');
          if (Array.isArray(data) && data.length > 0) {
            const orgId = String(data[0].uuid || data[0].id || '');
            if (!isValidOrgId(orgId)) {
              done_resolve({ success: false, error: 'Invalid org' });
              return;
            }
            saveSessionKey(capturedKey);
            store.set('orgId', orgId);
            done_resolve({ success: true });
            return;
          }
          done_resolve({ success: false, error: 'No org found' });
        } catch (e) {
          await session.defaultSession.cookies.remove('https://claude.ai', 'sessionKey').catch(() => {});
          done_resolve({ success: false, error: 'Validation failed' });
        }
      }
    };
    session.defaultSession.cookies.on('changed', onCookie);
    loginWin.on('closed', () => {
      clearTimeout(loginTimeout);
      session.defaultSession.cookies.removeListener('changed', onCookie);
      if (!done) done_resolve({ success: false });
    });
    loginWin.loadURL('https://claude.ai/login');
  });
});

ipcMain.handle('fetch-usage', async () => {
  const sessionKey = loadSessionKey();
  const orgId = store.get('orgId');
  if (!sessionKey || !orgId) throw new Error('Not authenticated');
  if (!isValidOrgId(orgId)) { store.delete('orgId'); throw new Error('Invalid org ID'); }

  await setSessionCookie(sessionKey);

  // encodeURIComponent even though UUID is safe — defense in depth
  const usageUrl = `https://claude.ai/api/organizations/${encodeURIComponent(orgId)}/usage`;

  const usageRes = await fetchViaWindow(usageUrl).catch(e => {
    const msg = e?.message || '';
    if (msg.includes('Cloudflare') || msg.includes('Blocked')) {
      clearSessionKey(); store.delete('orgId');
      mainWindow?.webContents.send('logged-out');
      throw new Error('SessionExpired');
    }
    throw new Error('FetchFailed');
  });

  const data = usageRes;
  if (!data || typeof data !== 'object') throw new Error('InvalidResponse');

  // Build sanitized result — NEVER pass raw API response to renderer
  const result = {
    sessionPct: null, sessionResetsAt: null,
    weeklyPct: null, weeklyResetsAt: null,
    extraUsage: null,
  };

  // Helper to extract utilization + resets_at from a period object
  function extractPeriod(obj) {
    if (!obj || typeof obj !== 'object') return null;
    const u = Number(obj.utilization);
    if (!Number.isFinite(u)) return null;
    return {
      pct: u,
      resets: typeof obj.resets_at === 'string' ? sanitizeString(obj.resets_at, 40) : null,
    };
  }

  // Session usage: try five_hour (current API) → current_period (legacy) → top-level
  const session = extractPeriod(data.five_hour)
    || extractPeriod(data.current_period)
    || extractPeriod(data);
  if (session) {
    result.sessionPct = session.pct;
    result.sessionResetsAt = session.resets;
  }

  // Weekly usage: try seven_day (current API) → weekly (legacy)
  const weekly = extractPeriod(data.seven_day)
    || extractPeriod(data.weekly);
  if (weekly) {
    result.weeklyPct = weekly.pct;
    result.weeklyResetsAt = weekly.resets;
  }

  // Extra usage: inline in response (current API) or from separate overage endpoint (legacy)
  const extra = data.extra_usage;
  if (extra && typeof extra === 'object') {
    if (extra.is_enabled) {
      const u = Number(extra.utilization);
      const limit = Number(extra.monthly_limit);
      const used = Number(extra.used_credits);
      result.extraUsage = {
        is_enabled: true,
        utilization: Number.isFinite(u) ? u : 0,
        used_cents: Number.isFinite(used) ? Math.round(used) : 0,
        limit_cents: Number.isFinite(limit) ? Math.round(limit) : 0,
      };
    } else {
      result.extraUsage = { is_enabled: false };
    }
  }

  appendHistory({ ts: Date.now(), session: result.sessionPct, weekly: result.weeklyPct });
  return result;
});

ipcMain.handle('get-history', (ev, args) => {
  const history = store.get('usageHistory', []);
  if (!Array.isArray(history)) return [];
  if (args && typeof args === 'object' && args.hours) {
    const hours = clampNumber(args.hours, 0.1, 8760, 24);
    const cutoff = Date.now() - (hours * 3600000);
    return history.filter(h => h && typeof h.ts === 'number' && h.ts >= cutoff);
  }
  return history;
});

ipcMain.handle('clear-history', () => { store.set('usageHistory', []); return true; });

ipcMain.on('minimize', () => mainWindow?.hide());
ipcMain.on('close-app', () => app.quit());

ipcMain.on('resize', (ev, args) => {
  if (!mainWindow || !args || typeof args !== 'object') return;
  const w = clampNumber(args.w, WIN_MIN.w, WIN_MAX.w, COMPACT.w);
  const h = clampNumber(args.h, WIN_MIN.h, WIN_MAX.h, COMPACT.h);
  const b = mainWindow.getBounds();
  mainWindow.setBounds({ x: b.x, y: b.y, width: w, height: h });
});

ipcMain.on('set-always-on-top', (ev, val) => mainWindow?.setAlwaysOnTop(!!val, 'floating'));

ipcMain.on('open-url', (ev, url) => {
  if (typeof url !== 'string') return;
  try {
    const p = new URL(url);
    if (p.protocol !== 'https:') return;
    if (!ALLOWED_EXTERNAL_DOMAINS.some(d => p.hostname === d || p.hostname.endsWith('.' + d))) return;
    shell.openExternal(url);
  } catch {}
});

ipcMain.on('show-notification', (ev, args) => {
  if (!args || typeof args !== 'object') return;
  const title = sanitizeString(args.title, MAX_NOTIFICATION_LEN);
  const body = sanitizeString(args.body, MAX_NOTIFICATION_LEN);
  if (!title) return;
  if (Notification.isSupported()) new Notification({ title, body, silent: false }).show();
});

ipcMain.handle('get-settings', () => ({
  alwaysOnTop: !!store.get('s.alwaysOnTop', true),
  pollMinutes: clampNumber(store.get('s.pollMinutes'), 1, 60, 5),
  warnPct: clampNumber(store.get('s.warnPct'), 1, 99, 75),
  dangerPct: clampNumber(store.get('s.dangerPct'), 1, 99, 90),
}));

ipcMain.handle('save-settings', (ev, s) => {
  if (!s || typeof s !== 'object') return false;
  store.set('s.alwaysOnTop', !!s.alwaysOnTop);
  store.set('s.pollMinutes', clampNumber(s.pollMinutes, 1, 60, 5));
  store.set('s.warnPct', clampNumber(s.warnPct, 1, 99, 75));
  store.set('s.dangerPct', clampNumber(s.dangerPct, 1, 99, 90));
  mainWindow?.setAlwaysOnTop(!!s.alwaysOnTop, 'floating');
  return true;
});

// ===========================================================================
// GLOBAL WEBCONTENTS HARDENING
// ===========================================================================
app.on('web-contents-created', (event, contents) => {
  // Deny popups from all windows by default
  contents.setWindowOpenHandler(() => ({ action: 'deny' }));

  // Deny all permission requests (camera, mic, geolocation, notifications, etc.)
  contents.session.setPermissionRequestHandler((wc, perm, cb) => cb(false));
  contents.session.setPermissionCheckHandler(() => false);

  // Block navigation to unexpected origins
  contents.on('will-navigate', (navEvent, navUrl) => {
    if (navUrl.startsWith('file://')) return;
    try {
      const p = new URL(navUrl);
      const all = [...ALLOWED_FETCH_ORIGINS, ...ALLOWED_LOGIN_ORIGINS];
      if (all.includes(p.origin)) return;
    } catch {}
    navEvent.preventDefault();
  });
});

// ===========================================================================
// APP LIFECYCLE
// ===========================================================================
app.on('ready', () => {
  session.defaultSession.setUserAgent(CHROME_UA);

  // Enforce CSP at session level (in addition to HTML meta tag)
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    // Only inject CSP for our own renderer pages
    if (details.url.startsWith('file://')) {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'none'"
          ]
        }
      });
    } else {
      callback({});
    }
  });
});

app.whenReady().then(async () => {
  const sk = loadSessionKey();
  if (sk) await setSessionCookie(sk);
  createMainWindow();
  createTray();
  mainWindow?.setAlwaysOnTop(!!store.get('s.alwaysOnTop', true), 'floating');
});

app.on('window-all-closed', () => {});
app.on('activate', () => { if (!mainWindow) createMainWindow(); });

const lock = app.requestSingleInstanceLock();
if (!lock) { app.quit(); } else {
  app.on('second-instance', () => {
    if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); }
  });
}

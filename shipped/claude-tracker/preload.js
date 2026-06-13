const { contextBridge, ipcRenderer } = require('electron');

// Track listeners so we can clean up and prevent stacking
let refreshHandler = null;
let loggedOutHandler = null;

contextBridge.exposeInMainWorld('api', {
  // Auth — session key NEVER enters the renderer process
  getCredentials: () => ipcRenderer.invoke('get-credentials'),
  login: () => ipcRenderer.invoke('detect-session-key'),  // Atomic: login → validate → save, all in main
  logout: () => ipcRenderer.invoke('logout'),

  // Data
  fetchUsage: () => ipcRenderer.invoke('fetch-usage'),
  getHistory: (opts) => {
    const clean = {};
    if (opts && typeof opts === 'object' && typeof opts.hours === 'number') {
      clean.hours = opts.hours;
    }
    return ipcRenderer.invoke('get-history', clean);
  },
  clearHistory: () => ipcRenderer.invoke('clear-history'),

  // Window — fixed payloads only, no arbitrary forwarding
  minimize: () => ipcRenderer.send('minimize'),
  closeApp: () => ipcRenderer.send('close-app'),
  resize: (size) => {
    if (!size || typeof size !== 'object') return;
    ipcRenderer.send('resize', {
      w: typeof size.w === 'number' ? size.w : 540,
      h: typeof size.h === 'number' ? size.h : 170,
    });
  },
  setAlwaysOnTop: (v) => ipcRenderer.send('set-always-on-top', !!v),
  openUrl: (url) => {
    if (typeof url !== 'string') return;
    ipcRenderer.send('open-url', url);
  },
  notify: (title, body) => {
    if (typeof title !== 'string' || typeof body !== 'string') return;
    ipcRenderer.send('show-notification', {
      title: title.slice(0, 200),
      body: body.slice(0, 200),
    });
  },

  // Settings
  getSettings: () => ipcRenderer.invoke('get-settings'),
  saveSettings: (s) => {
    if (!s || typeof s !== 'object') return Promise.resolve(false);
    return ipcRenderer.invoke('save-settings', {
      alwaysOnTop: !!s.alwaysOnTop,
      pollMinutes: typeof s.pollMinutes === 'number' ? s.pollMinutes : 5,
      warnPct: typeof s.warnPct === 'number' ? s.warnPct : 75,
      dangerPct: typeof s.dangerPct === 'number' ? s.dangerPct : 90,
    });
  },

  // Events — clean up previous listener to prevent stacking
  onRefresh: (cb) => {
    if (refreshHandler) ipcRenderer.removeListener('refresh', refreshHandler);
    refreshHandler = () => cb();
    ipcRenderer.on('refresh', refreshHandler);
  },
  onLoggedOut: (cb) => {
    if (loggedOutHandler) ipcRenderer.removeListener('logged-out', loggedOutHandler);
    loggedOutHandler = () => cb();
    ipcRenderer.on('logged-out', loggedOutHandler);
  },
});

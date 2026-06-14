'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {
  app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, screen, shell, nativeImage, clipboard,
} = require('electron');

const { route } = require('./src/core/router.js');
const { parseBookmarks, mergeSites } = require('./src/core/bookmarks.js');
const { scanStartMenu } = require('./src/core/startmenu.js');
const { scanFolders } = require('./src/core/folders.js');
const { BUILTIN_SITES } = require('./src/core/sites.js');
const { createIndexer } = require('./src/indexer.js');
const { launchItem } = require('./src/launch.js');
const { createLogger } = require('./src/log.js');
const { buildHome } = require('./src/core/sections.js');
const { record } = require('./src/core/history.js');
const { mergeConfig, seedPinned } = require('./src/core/config.js');
const { loadConfig, saveConfig: persistConfig } = require('./src/configStore.js');
const { loadHistory, saveHistory: persistHistory } = require('./src/historyStore.js');
const { TRAY_ICON_DATA_URL } = require('./assets/tray-icon.js');

const WIN_W = 680;
const WIN_H = 460;
const HOTKEYS = ['Alt+Space', 'Ctrl+Alt+Space', 'Ctrl+Shift+Space'];
const WORKSPACE_DIR = 'C:\\Users\\slims\\Desktop\\Claude 2.0';

const log = createLogger(path.join(__dirname, 'data', 'launcher.log'));
const CONFIG_PATH = path.join(__dirname, 'data', 'config.json');
const HISTORY_PATH = path.join(__dirname, 'data', 'history.json');

// ---------- single instance ----------
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  let win = null;
  let tray = null;
  let quitting = false;
  let config = mergeConfig({});
  let history = { version: 1, items: {} };

  // ---------- index sources (real fs wired in) ----------
  function listDirSync(dir) {
    return fs.readdirSync(dir, { withFileTypes: true }).map((d) => ({
      name: d.name,
      isDirectory: d.isDirectory(),
    }));
  }

  const startMenuRoots = [
    path.join(process.env.APPDATA || '', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
    path.join(process.env.ProgramData || 'C:\\ProgramData', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
  ];

  const bookmarksPath = path.join(
    process.env.LOCALAPPDATA || '',
    'Google', 'Chrome', 'User Data', 'Default', 'Bookmarks'
  );

  let lastGoodBookmarks = [];
  let bookmarksErrorLogged = false;
  function scanSites() {
    try {
      lastGoodBookmarks = parseBookmarks(fs.readFileSync(bookmarksPath, 'utf8'));
      bookmarksErrorLogged = false;
    } catch (err) {
      if (!bookmarksErrorLogged) {
        log.error(`Chrome bookmarks unavailable, using built-ins + last good: ${err.message}`);
        bookmarksErrorLogged = true;
      }
    }
    return mergeSites(lastGoodBookmarks, BUILTIN_SITES);
  }

  function folderRoots() {
    const roots = ['desktop', 'documents', 'downloads'].map((name) => {
      try {
        return app.getPath(name);
      } catch {
        return null;
      }
    }).filter(Boolean);
    roots.push(WORKSPACE_DIR);
    return roots;
  }

  function scanAllFolders() {
    const items = scanFolders(folderRoots(), { listDirSync, maxDepth: 2 });
    const seen = new Set();
    return items.filter((i) => { // workspace sits on the Desktop, so roots overlap
      if (seen.has(i.id)) return false;
      seen.add(i.id);
      return true;
    });
  }

  function watchSites(onChange) {
    try {
      // Chrome rewrites Bookmarks via temp-file rename; watch the directory.
      const watcher = fs.watch(path.dirname(bookmarksPath), (event, filename) => {
        // filename can be null on Windows; err toward rescanning (debounced).
        if (!filename || filename === 'Bookmarks') onChange();
      });
      return () => watcher.close();
    } catch (err) {
      log.error(`Cannot watch bookmarks dir: ${err.message}`);
      return () => {};
    }
  }

  const indexer = createIndexer({
    scanApps: () => scanStartMenu(startMenuRoots, { listDirSync }),
    scanSites,
    scanFolders: scanAllFolders,
    watchSites,
    log,
  });

  // ---------- window ----------
  function createWindow() {
    win = new BrowserWindow({
      width: WIN_W,
      height: WIN_H,
      show: false,
      frame: false,
      transparent: true,
      resizable: false,
      skipTaskbar: true,
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });
    win.setAlwaysOnTop(true, 'screen-saver');
    win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
    win.on('blur', () => hideWindow());
    win.on('close', (e) => {
      if (!quitting) {
        e.preventDefault();
        hideWindow();
      }
    });
  }

  function showWindow() {
    if (!win) return;
    const wa = screen.getPrimaryDisplay().workArea;
    win.setPosition(
      wa.x + Math.round((wa.width - WIN_W) / 2),
      wa.y + Math.round(wa.height * 0.18)
    );
    win.show();
    win.focus();
    win.webContents.send('window:shown');
  }

  function hideWindow() {
    if (win && win.isVisible()) win.hide();
  }

  function toggleWindow() {
    if (win && win.isVisible()) hideWindow();
    else showWindow();
  }

  // ---------- hotkey ----------
  function registerHotkey() {
    for (const key of HOTKEYS) {
      try {
        if (globalShortcut.register(key, toggleWindow)) {
          log.info(`Hotkey registered: ${key}`);
          return key;
        }
      } catch (err) {
        log.error(`Hotkey ${key} failed: ${err.message}`);
      }
    }
    log.error('No hotkey could be registered; use the tray icon.');
    return null;
  }

  // ---------- app lifecycle ----------
  app.on('second-instance', () => showWindow());

  app.whenReady().then(() => {
    createWindow();

    const hotkey = registerHotkey();

    const icon = nativeImage.createFromDataURL(TRAY_ICON_DATA_URL);
    tray = new Tray(icon);
    tray.setToolTip(`Nautilus — ${hotkey || 'no hotkey (click to open)'}`);
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: 'Show Nautilus', click: showWindow },
      { label: 'Refresh Index', click: () => indexer.refresh() },
      { type: 'separator' },
      {
        label: 'Exit',
        click: () => {
          quitting = true;
          app.quit();
        },
      },
    ]));
    tray.on('click', toggleWindow);

    indexer.start();

    // Config + history. indexer.start() refreshes synchronously, so getItems()
    // is already populated here and the first-run seed can match installed apps.
    history = loadHistory(HISTORY_PATH, log);
    const loaded = loadConfig(CONFIG_PATH, log);
    config = loaded.config;
    if (!loaded.existed) {
      config = mergeConfig({ ...config, pinned: seedPinned(indexer.getItems()) });
      try { persistConfig(CONFIG_PATH, config); } catch (err) { log.error(`config seed save failed: ${err.message}`); }
      log.info(`First run: seeded ${config.pinned.length} pinned app(s).`);
    }

    // Auto-start at login via wscript+launch.vbs so no terminal ever appears.
    app.setLoginItemSettings({
      openAtLogin: true,
      name: 'Nautilus',
      path: 'C:\\Windows\\System32\\wscript.exe',
      args: [path.join(__dirname, 'launch.vbs')], // Electron quotes args itself
    });

    log.info(`Nautilus started. Indexed ${indexer.getItems().length} items.`);
  });

  app.on('window-all-closed', () => {
    // tray app: stay alive
  });

  app.on('before-quit', () => {
    quitting = true;
    globalShortcut.unregisterAll();
    indexer.stop();
  });

  // ---------- icons ----------
  const iconCache = new Map(); // target -> data URL ('' = extraction failed)
  async function attachIcons(results) {
    return Promise.all(results.map(async (item) => {
      if (item.type !== 'app' && item.type !== 'folder') return item;
      if (!iconCache.has(item.target)) {
        try {
          const img = await app.getFileIcon(item.target, { size: 'normal' });
          iconCache.set(item.target, img.isEmpty() ? '' : img.toDataURL());
        } catch {
          iconCache.set(item.target, '');
        }
      }
      const icon = iconCache.get(item.target);
      return icon ? { ...item, icon } : item;
    }));
  }

  // ---------- IPC ----------
  ipcMain.handle('search', async (event, query) => {
    const { results, enterAction } = route(query, indexer.getItems());
    return { results: await attachIcons(results), enterAction };
  });

  ipcMain.handle('launch', async (event, item) => {
    const result = await launchItem(item, { shell, clipboard });
    if (result.ok) {
      hideWindow();
      history = record(history, item, Date.now());
      try { persistHistory(HISTORY_PATH, history); } catch (err) { log.error(`history save failed: ${err.message}`); }
    } else {
      log.error(`Launch failed for ${item.title}: ${result.error}`);
    }
    return result;
  });

  ipcMain.handle('getHome', async () => {
    const rows = buildHome({ config, history, index: indexer.getItems() });
    const items = await attachIcons(rows.filter((r) => r.kind === 'item').map((r) => r.item));
    let k = 0;
    return rows.map((r) => (r.kind === 'item' ? { kind: 'item', item: items[k++] } : r));
  });

  ipcMain.handle('getConfig', async () => config);

  ipcMain.handle('saveConfig', async (event, incoming) => {
    config = mergeConfig(incoming);
    try { persistConfig(CONFIG_PATH, config); } catch (err) { log.error(`config save failed: ${err.message}`); }
    return config;
  });

  ipcMain.handle('searchIndex', async (event, query) => {
    const { results } = route(query, indexer.getItems());
    return { results: await attachIcons(results) };
  });

  ipcMain.on('window:hide', () => hideWindow());
}

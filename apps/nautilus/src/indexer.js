'use strict';

const DEBOUNCE_MS = 500;

// Holds the merged in-memory index. Each source keeps its last good result
// so one flaky scanner (e.g. a mid-write bookmarks file) never empties the list.
function createIndexer({
  scanApps,
  scanSites,
  scanFolders,
  watchSites,
  log,
  intervalMs = 5 * 60 * 1000,
}) {
  const sources = { apps: [], sites: [], folders: [] };
  let interval = null;
  let debounce = null;
  let unwatch = null;

  function runScanner(name, fn) {
    try {
      sources[name] = fn();
    } catch (err) {
      log.error(`${name} scan failed, keeping last good (${sources[name].length} items): ${err.message}`);
    }
  }

  function refresh() {
    runScanner('apps', scanApps);
    runScanner('sites', scanSites);
    runScanner('folders', scanFolders);
  }

  function onSitesChanged() {
    clearTimeout(debounce);
    debounce = setTimeout(() => runScanner('sites', scanSites), DEBOUNCE_MS);
  }

  return {
    start() {
      refresh();
      interval = setInterval(refresh, intervalMs);
      if (watchSites) unwatch = watchSites(onSitesChanged);
    },
    stop() {
      clearInterval(interval);
      clearTimeout(debounce);
      if (unwatch) unwatch();
    },
    refresh,
    getItems: () => [...sources.apps, ...sources.sites, ...sources.folders],
  };
}

module.exports = { createIndexer };

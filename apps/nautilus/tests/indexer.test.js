const { test, mock } = require('node:test');
const assert = require('node:assert');
const { createIndexer } = require('../src/indexer.js');

function items(type, ...titles) {
  return titles.map((t) => ({ id: `${type}:${t}`, type, title: t, subtitle: '', target: t }));
}

const silentLog = { info: () => {}, error: () => {} };

test('start() populates merged items from all scanners', () => {
  const idx = createIndexer({
    scanApps: () => items('app', 'Chrome'),
    scanSites: () => items('site', 'Gmail'),
    scanFolders: () => items('folder', 'Downloads'),
    log: silentLog,
  });
  idx.start();
  const titles = idx.getItems().map((i) => i.title).sort();
  assert.deepStrictEqual(titles, ['Chrome', 'Downloads', 'Gmail']);
  idx.stop();
});

test('a failing scanner keeps other sources and logs the error', () => {
  const errors = [];
  const idx = createIndexer({
    scanApps: () => { throw new Error('start menu unreadable'); },
    scanSites: () => items('site', 'Gmail'),
    scanFolders: () => items('folder', 'Downloads'),
    log: { info: () => {}, error: (m) => errors.push(m) },
  });
  idx.start();
  assert.deepStrictEqual(idx.getItems().map((i) => i.title).sort(), ['Downloads', 'Gmail']);
  assert.ok(errors.length >= 1);
  idx.stop();
});

test('a scanner that fails on refresh keeps its last good items', () => {
  let call = 0;
  const idx = createIndexer({
    scanApps: () => {
      call++;
      if (call > 1) throw new Error('flaky');
      return items('app', 'Chrome');
    },
    scanSites: () => [],
    scanFolders: () => [],
    log: silentLog,
  });
  idx.start();
  idx.refresh();
  assert.deepStrictEqual(idx.getItems().map((i) => i.title), ['Chrome']);
  idx.stop();
});

test('interval triggers periodic refresh', () => {
  mock.timers.enable({ apis: ['setInterval', 'setTimeout'] });
  let scans = 0;
  const idx = createIndexer({
    scanApps: () => { scans++; return []; },
    scanSites: () => [],
    scanFolders: () => [],
    log: silentLog,
    intervalMs: 1000,
  });
  idx.start();
  assert.strictEqual(scans, 1);
  mock.timers.tick(3000);
  assert.strictEqual(scans, 4);
  idx.stop();
  mock.timers.tick(5000);
  assert.strictEqual(scans, 4, 'stop() must clear the interval');
  mock.timers.reset();
});

test('sites watch change re-scans sites only, debounced 500ms', () => {
  mock.timers.enable({ apis: ['setInterval', 'setTimeout'] });
  let siteScans = 0;
  let appScans = 0;
  let onChange;
  const idx = createIndexer({
    scanApps: () => { appScans++; return []; },
    scanSites: () => { siteScans++; return items('site', `Gmail${siteScans}`); },
    scanFolders: () => [],
    watchSites: (cb) => { onChange = cb; return () => {}; },
    log: silentLog,
  });
  idx.start();
  assert.strictEqual(siteScans, 1);
  onChange();
  onChange();
  onChange();
  assert.strictEqual(siteScans, 1, 'debounce: no immediate rescan');
  mock.timers.tick(600);
  assert.strictEqual(siteScans, 2, 'one rescan after debounce window');
  assert.strictEqual(appScans, 1, 'apps not rescanned on bookmark change');
  assert.deepStrictEqual(idx.getItems().map((i) => i.title), ['Gmail2']);
  idx.stop();
  mock.timers.reset();
});

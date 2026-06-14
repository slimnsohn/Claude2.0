const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { loadHistory, saveHistory } = require('../src/historyStore.js');

function tmp() {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'nautilus-hist-')), 'history.json');
}

test('loadHistory returns empty when file missing', () => {
  assert.deepStrictEqual(loadHistory(tmp()), { version: 1, items: {} });
});

test('saveHistory then loadHistory round-trips', () => {
  const p = tmp();
  const h = { version: 1, items: { 'app:C:\\a.lnk': { type: 'app', title: 'A', subtitle: '', target: 'C:\\a.lnk', count: 3, lastLaunched: 9 } } };
  saveHistory(p, h);
  assert.deepStrictEqual(loadHistory(p), h);
});

test('loadHistory falls back to empty on corrupt JSON or bad shape', () => {
  const p = tmp();
  fs.writeFileSync(p, 'garbage');
  assert.deepStrictEqual(loadHistory(p), { version: 1, items: {} });
  fs.writeFileSync(p, '{"items": 5}');
  assert.deepStrictEqual(loadHistory(p), { version: 1, items: {} });
});

test('loadHistory invokes log.error on corrupt JSON (not on missing file)', () => {
  const corrupt = tmp();
  fs.writeFileSync(corrupt, 'garbage');
  let corruptLogged = false;
  loadHistory(corrupt, { error: () => { corruptLogged = true; } });
  assert.strictEqual(corruptLogged, true);

  let missingLogged = false;
  loadHistory(tmp(), { error: () => { missingLogged = true; } }); // tmp() path has no file
  assert.strictEqual(missingLogged, false);
});

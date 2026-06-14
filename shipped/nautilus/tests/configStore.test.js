const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { loadConfig, saveConfig } = require('../src/configStore.js');
const { DEFAULT_CONFIG } = require('../src/core/config.js');

function tmp() {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'nautilus-cfg-')), 'config.json');
}

test('loadConfig returns defaults and existed:false when file is missing', () => {
  const { config, existed } = loadConfig(tmp());
  assert.strictEqual(existed, false);
  assert.deepStrictEqual(config, DEFAULT_CONFIG);
});

test('saveConfig then loadConfig round-trips a merged config', () => {
  const p = tmp();
  saveConfig(p, { sections: { recent: { limit: 2 } }, pinned: [{ type: 'app', title: 'A', target: 'C:\\a.lnk' }] });
  const { config, existed } = loadConfig(p);
  assert.strictEqual(existed, true);
  assert.strictEqual(config.sections.recent.limit, 2);
  assert.strictEqual(config.pinned[0].target, 'C:\\a.lnk');
});

test('loadConfig falls back to defaults on corrupt JSON', () => {
  const p = tmp();
  fs.writeFileSync(p, '{ not json');
  const { config, existed } = loadConfig(p);
  assert.strictEqual(existed, false);
  assert.deepStrictEqual(config, DEFAULT_CONFIG);
});

test('loadConfig invokes log.error on corrupt JSON (not on missing file)', () => {
  const corrupt = tmp();
  fs.writeFileSync(corrupt, '{ not json');
  let corruptLogged = false;
  loadConfig(corrupt, { error: () => { corruptLogged = true; } });
  assert.strictEqual(corruptLogged, true);

  let missingLogged = false;
  loadConfig(tmp(), { error: () => { missingLogged = true; } }); // tmp() path has no file
  assert.strictEqual(missingLogged, false);
});

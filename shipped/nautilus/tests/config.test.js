'use strict';

const { test } = require('node:test');
const assert = require('node:assert');
const { DEFAULT_CONFIG, mergeConfig, seedPinned } = require('../src/core/config.js');

test('mergeConfig fills all defaults from empty input', () => {
  const c = mergeConfig({});
  assert.deepStrictEqual(c, DEFAULT_CONFIG);
  assert.strictEqual(c.sections.recent.limit, 5);
  assert.strictEqual(c.sections.pinned.limit, 8);
});

test('mergeConfig keeps valid overrides', () => {
  const c = mergeConfig({ sections: { recent: { enabled: false, typeFilter: 'app', limit: 3 } } });
  assert.deepStrictEqual(c.sections.recent, { enabled: false, typeFilter: 'app', limit: 3 });
  assert.deepStrictEqual(c.sections.frequent, DEFAULT_CONFIG.sections.frequent);
});

test('mergeConfig coerces bad values to defaults', () => {
  const c = mergeConfig({ sections: { recent: { typeFilter: 'bogus', limit: -2 }, frequent: { limit: 1.5 } } });
  assert.strictEqual(c.sections.recent.typeFilter, 'all');
  assert.strictEqual(c.sections.recent.limit, 5);
  assert.strictEqual(c.sections.frequent.limit, 5);
});

test('mergeConfig drops malformed pinned entries and normalizes good ones', () => {
  const c = mergeConfig({ pinned: [
    { type: 'app', title: 'Cursor', target: 'C:\\a\\Cursor.lnk' },
    { type: 'claude', title: 'x', target: 'https://claude.ai' },   // not pinnable
    { type: 'site', target: 'https://github.com' },                // missing title -> defaults to target
    { type: 'folder' },                                            // no target -> dropped
    null,
  ] });
  assert.deepStrictEqual(c.pinned, [
    { type: 'app', title: 'Cursor', subtitle: '', target: 'C:\\a\\Cursor.lnk' },
    { type: 'site', title: 'https://github.com', subtitle: '', target: 'https://github.com' },
  ]);
});

test('mergeConfig is idempotent', () => {
  const once = mergeConfig({ sections: { recent: { limit: 9 } } });
  assert.deepStrictEqual(mergeConfig(once), once);
});

test('mergeConfig handles null/undefined input', () => {
  assert.deepStrictEqual(mergeConfig(null), DEFAULT_CONFIG);
  assert.deepStrictEqual(mergeConfig(undefined), DEFAULT_CONFIG);
});

test('seedPinned handles a null/empty index without throwing', () => {
  assert.deepStrictEqual(seedPinned(null, ['Cursor']), []);
  assert.deepStrictEqual(seedPinned([], ['Cursor']), []);
});

test('seedPinned skips app entries with a missing title', () => {
  const index = [
    { id: 'a', type: 'app', subtitle: '', target: 'C:\\notitle.lnk' }, // no title
    { id: 'b', type: 'app', title: 'Cursor', subtitle: 'Programs', target: 'C:\\Cursor.lnk' },
  ];
  assert.deepStrictEqual(seedPinned(index, ['Cursor']), [
    { type: 'app', title: 'Cursor', subtitle: 'Programs', target: 'C:\\Cursor.lnk' },
  ]);
});

test('seedPinned matches apps by case-insensitive title (exact preferred, then substring)', () => {
  const index = [
    { id: 'a', type: 'app', title: 'Cursor', subtitle: 'Programs', target: 'C:\\Cursor.lnk' },
    { id: 'b', type: 'app', title: 'Microsoft Excel', subtitle: 'Office', target: 'C:\\Excel.lnk' },
    { id: 'c', type: 'folder', title: 'Notepad docs', subtitle: '', target: 'C:\\nd' },
  ];
  const pins = seedPinned(index, ['Cursor', 'Excel', 'Notepad']);
  // Cursor: exact app match; Excel: substring app match; Notepad: no APP match -> skipped
  assert.deepStrictEqual(pins, [
    { type: 'app', title: 'Cursor', subtitle: 'Programs', target: 'C:\\Cursor.lnk' },
    { type: 'app', title: 'Microsoft Excel', subtitle: 'Office', target: 'C:\\Excel.lnk' },
  ]);
});

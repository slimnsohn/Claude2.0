const { test } = require('node:test');
const assert = require('node:assert');
const { BUILTIN_SITES } = require('../src/core/sites.js');

test('built-in sites have valid item shape and https targets', () => {
  assert.ok(BUILTIN_SITES.length > 0);
  for (const s of BUILTIN_SITES) {
    assert.strictEqual(s.type, 'site');
    assert.ok(s.id && s.title && s.target, JSON.stringify(s));
    assert.ok(s.target.startsWith('https://'), s.target);
  }
});

test('built-ins cover the core jump targets: gmail, claude, espn, youtube', () => {
  const titles = BUILTIN_SITES.map((s) => s.title.toLowerCase());
  for (const wanted of ['gmail', 'claude', 'espn', 'youtube']) {
    assert.ok(titles.includes(wanted), `missing ${wanted}`);
  }
});
